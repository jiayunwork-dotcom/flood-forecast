"""
水文降雨径流模型与洪水预报 - 交互式分析工具
基于Dash + Plotly的Web界面
"""

import base64
import io
import json
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional, Dict

import dash
from dash import dcc, html, dash_table, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

from hydrology.data_manager import DataManager
from hydrology.runoff_models import get_runoff_model
from hydrology.routing_models import RoutingModel, calculate_metrics
from hydrology.calibration import ModelCalibrator
from hydrology.forecast import Forecaster
from hydrology.frequency_analysis import FrequencyAnalysis
from hydrology.multi_event import MultiEventEvaluator


app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True
)
app.title = "水文降雨径流模型与洪水预报分析系统"

data_mgr = DataManager()
calibration_result = None
multi_eval_result = None
multi_compare_result = None
loocv_result = None
frequency_analyzer = FrequencyAnalysis()
freq_result_data = None

SAMPLE_DATA_CSV = """date,rainfall,evaporation,runoff
2020-06-01,0,2.5,5.2
2020-06-02,0,2.8,4.8
2020-06-03,0,3.0,4.5
2020-06-04,12.5,2.7,5.0
2020-06-05,28.3,2.2,8.5
2020-06-06,45.6,1.8,25.3
2020-06-07,18.2,2.0,52.8
2020-06-08,5.5,2.3,78.5
2020-06-09,0.8,2.6,65.2
2020-06-10,0,2.9,42.1
2020-06-11,0,3.1,28.5
2020-06-12,0,3.0,18.2
2020-06-13,0,2.8,12.5
2020-06-14,0,2.6,9.0
2020-06-15,0,2.5,7.2
2020-06-16,0,2.4,6.0
2020-06-17,8.5,2.3,6.8
2020-06-18,35.2,2.0,15.6
2020-06-19,52.8,1.5,45.2
2020-06-20,22.5,1.8,98.5
2020-06-21,3.8,2.1,125.6
2020-06-22,0,2.4,95.8
2020-06-23,0,2.7,65.2
2020-06-24,0,2.9,42.5
2020-06-25,0,3.0,28.8
2020-06-26,0,2.8,20.5
2020-06-27,0,2.6,15.2
2020-06-28,0,2.5,11.8
2020-06-29,0,2.4,9.5
2020-06-30,0,2.3,8.0
"""

ANNUAL_PEAKS = [
    125.6, 98.5, 78.2, 156.3, 112.5, 89.6, 145.2, 68.9, 132.8, 178.5,
    95.6, 122.3, 85.9, 165.4, 108.7, 72.1, 138.9, 152.6, 99.3, 118.4,
    142.7, 82.5, 168.2, 105.6, 76.8
]


def generate_test_data():
    global data_mgr
    df = pd.read_csv(io.StringIO(SAMPLE_DATA_CSV))
    df['date'] = pd.to_datetime(df['date'])
    data_mgr.raw_data = df
    data_mgr.data = df
    data_mgr.time_step = 'day'
    data_mgr.time_delta = pd.Timedelta(days=1)
    data_mgr.set_basin_params(500.0, 50.0, 0.002, '壤土')
    data_mgr.split_flood_events(rain_threshold=3.0, min_duration_hours=12)
    return data_mgr


generate_test_data()


def create_empty_figure(title=""):
    fig = go.Figure()
    fig.update_layout(title=title, template="plotly_white",
                      height=400, margin=dict(l=60, r=20, t=50, b=50))
    return fig


STATION_NAMES = ['上游A', '中游B', '中游C', '下游D', '出口E']
STATION_MILEAGES = [0, 15, 28, 42, 60]
DEFAULT_WARNING_LEVELS = [5.0, 4.8, 5.2, 4.5, 4.0]
DEFAULT_GUARANTEE_LEVELS = [6.5, 6.2, 6.8, 6.0, 5.5]
STATION_COLORS = ['#e53935', '#fb8c00', '#43a047', '#1e88e5', '#8e24aa']
AVG_FLOW_VELOCITY = 1.5

monitoring_state = {
    'running': False,
    'time_step': 0,
    'stations': [
        {'name': STATION_NAMES[i], 'mileage': STATION_MILEAGES[i],
         'warning_level': DEFAULT_WARNING_LEVELS[i],
         'guarantee_level': DEFAULT_GUARANTEE_LEVELS[i],
         'water_level': [], 'flow': [],
         'current_warning_level': 5,
         'peak_detected': False,
         'peak_time_idx': None,
         'estimated_peak_arrival': None,
         'actual_peak_arrival': None}
        for i in range(5)
    ],
    'warnings': [],
    'decisions': [],
    'peak_deviations': [],
    'logs': []
}


def get_warning_level(exceedance: float) -> int:
    if exceedance <= 0:
        return 0
    elif exceedance <= 0.5:
        return 4
    elif exceedance <= 1.5:
        return 3
    elif exceedance <= 3.0:
        return 2
    else:
        return 1


def get_warning_info(level: int):
    level_map = {
        4: {'name': 'Ⅳ级', 'color': '#1976d2', 'bg': '#e3f2fd'},
        3: {'name': 'Ⅲ级', 'color': '#f9a825', 'bg': '#fff8e1'},
        2: {'name': 'Ⅱ级', 'color': '#ef6c00', 'bg': '#fff3e0'},
        1: {'name': 'Ⅰ级', 'color': '#c62828', 'bg': '#ffebee'},
        0: {'name': '正常', 'color': '#2e7d32', 'bg': '#e8f5e9'}
    }
    return level_map.get(level, level_map[0])


def generate_flood_data(t: int, station_idx: int) -> tuple:
    base_level = 2.5
    mileage = STATION_MILEAGES[station_idx]
    travel_steps = calculate_travel_time_steps(0, mileage)
    peak_center = 20 + travel_steps
    spread = 9 + station_idx * 0.5
    amplitude = 5.8 - station_idx * 0.25

    if t < peak_center - spread:
        flood_component = 0
    elif t <= peak_center:
        progress = (t - (peak_center - spread)) / spread
        flood_component = amplitude * (np.sin(np.pi * progress / 2)) ** 1.2
    else:
        if t > peak_center + spread * 1.5:
            flood_component = 0
        else:
            progress = (t - peak_center) / (spread * 1.5)
            flood_component = amplitude * np.exp(-3.0 * progress) * (1 - progress * 0.3)

    noise = np.random.normal(0, 0.05)
    water_level = base_level + flood_component + noise
    water_level = max(2.0, min(water_level, 9.0))

    flow_base = 20 + station_idx * 15
    flow_amplitude = 300 - station_idx * 25
    flow = flow_base + (flow_amplitude * max(0, water_level - base_level) / 5.0) + np.random.normal(0, 4)
    flow = max(10, flow)

    return round(water_level, 2), round(flow, 1)


def calculate_travel_time_steps(from_mileage: float, to_mileage: float) -> float:
    distance_km = to_mileage - from_mileage
    distance_m = distance_km * 1000
    time_seconds = distance_m / AVG_FLOW_VELOCITY
    return time_seconds / (3.0 * 3600)

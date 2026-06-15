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

RESOURCE_TYPES = ['冲锋舟', '编织袋', '救生衣', '抽水泵', '应急帐篷']
RESOURCE_UNITS = ['艘', '条', '件', '台', '顶']
DEFAULT_RESOURCE_STOCK = [50, 2000, 300, 30, 20]

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
    'logs': [],
    'resources': {
        'stock': DEFAULT_RESOURCE_STOCK.copy(),
        'allocated': [0] * 5,
        'history': [],
        'details': []
    },
    'correlation': {
        'last_data_length': 0,
        'corr_matrix': None,
        'lag_corr_cache': {}
    }
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


def calculate_auto_allocation():
    resources = monitoring_state['resources']
    stock = resources['stock']
    allocated = [0] * 5
    details = []

    active_warnings = [w for w in monitoring_state['warnings']
                      if w['level'] <= 2 and not w.get('dismissed')]

    if not active_warnings:
        resources['details'] = ["无Ⅱ级及以上预警，无需调配"]
        resources['allocated'] = allocated
        return

    level_1_stations = [w['station_idx'] for w in active_warnings if w['level'] == 1]
    level_2_stations = [w['station_idx'] for w in active_warnings if w['level'] == 2]

    has_level_1 = len(level_1_stations) > 0
    multi_level_2 = len(level_2_stations) >= 2
    single_level_2 = len(level_2_stations) == 1 and not has_level_1

    if has_level_1:
        for idx in level_1_stations:
            for r in range(5):
                avail = stock[r] - allocated[r]
                qty = avail
                if qty > 0:
                    allocated[r] += qty
                    details.append(
                        f"向{STATION_NAMES[idx]}调配{RESOURCE_TYPES[r]}{qty}{RESOURCE_UNITS[r]}（全部库存）"
                    )
    elif multi_level_2:
        for r in range(5):
            qty = int(stock[r] * 0.5)
            for idx in level_2_stations:
                per_station = qty // len(level_2_stations)
                if per_station > 0:
                    allocated[r] += per_station
                    details.append(
                        f"向{STATION_NAMES[idx]}调配{RESOURCE_TYPES[r]}{per_station}{RESOURCE_UNITS[r]}"
                    )
            remaining = qty % len(level_2_stations)
            if remaining > 0:
                allocated[r] += remaining
                details.append(
                    f"向{STATION_NAMES[level_2_stations[0]]}追加调配{RESOURCE_TYPES[r]}{remaining}{RESOURCE_UNITS[r]}"
                )
    elif single_level_2:
        idx = level_2_stations[0]
        upstream_idx = max(0, idx - 1)
        downstream_idx = min(4, idx + 1)
        for r in range(5):
            twenty_pct = int(stock[r] * 0.2)
            if twenty_pct > 0:
                if upstream_idx != idx:
                    allocated[r] += twenty_pct
                    details.append(
                        f"向上游{STATION_NAMES[upstream_idx]}调配{RESOURCE_TYPES[r]}{twenty_pct}{RESOURCE_UNITS[r]}"
                    )
                if downstream_idx != idx and downstream_idx != upstream_idx:
                    allocated[r] += twenty_pct
                    details.append(
                        f"向下游{STATION_NAMES[downstream_idx]}调配{RESOURCE_TYPES[r]}{twenty_pct}{RESOURCE_UNITS[r]}"
                    )

    for r in range(5):
        allocated[r] = min(allocated[r], stock[r])

    resources['allocated'] = allocated
    resources['details'] = details

    history_record = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'time_step': monitoring_state['time_step'],
        'details': details.copy(),
        'allocation': allocated.copy(),
        'warning_level': 'Ⅰ级' if has_level_1 else ('多站Ⅱ级' if multi_level_2 else '单站Ⅱ级')
    }
    resources['history'].insert(0, history_record)


def render_allocation_details():
    details = monitoring_state['resources']['details']
    if not details:
        return html.Div("暂无调配记录",
            style={'color': '#999', 'fontStyle': 'italic',
                   'padding': '10px', 'textAlign': 'center',
                   'backgroundColor': '#f5f5f5', 'borderRadius': '4px'})

    items = []
    for d in details:
        items.append(html.Div(f"• {d}", style={'marginBottom': '4px'}))
    return html.Div(items)


def render_allocation_history():
    history = monitoring_state['resources']['history']
    if not history:
        return html.Div("暂无历史记录",
            style={'color': '#999', 'fontStyle': 'italic',
                   'padding': '10px', 'textAlign': 'center',
                   'backgroundColor': '#f5f5f5', 'borderRadius': '4px'})

    items = []
    for h in history:
        badge_color = '#c62828' if 'Ⅰ级' in h['warning_level'] else '#ef6c00'
        items.append(html.Div([
            html.Div([
                html.Strong(f"[{h['timestamp']}]", style={'color': '#333'}),
                html.Span(f" T{h['time_step']} ", style={'color': '#666'}),
                html.Span(h['warning_level'],
                          style={'backgroundColor': badge_color, 'color': '#fff',
                                 'padding': '1px 6px', 'borderRadius': '8px',
                                 'fontSize': '11px'})
            ], style={'marginBottom': '4px', 'fontSize': '11px'}),
            html.Div([
                html.Div(f"  • {d}", style={'fontSize': '11px', 'color': '#555'})
                for d in h['details'][:3]
            ])
        ], style={'marginBottom': '10px', 'paddingBottom': '8px',
                  'borderBottom': '1px dashed #ddd'}))

    return html.Div(items, style={'maxHeight': '150px', 'overflowY': 'auto'})


def plot_correlation_heatmap(corr_matrix):
    station_names = [st['name'] for st in monitoring_state['stations']]

    fig = go.Figure(data=go.Heatmap(
        z=corr_matrix,
        x=station_names,
        y=station_names,
        zmin=-1,
        zmax=1,
        colorscale='RdBu_r',
        reversescale=True,
        text=[[f"{val:.2f}" for val in row] for row in corr_matrix],
        texttemplate="%{text}",
        textfont={"size": 12},
        hoverongaps=False,
        colorbar=dict(
            title="相关系数",
            titleside="right",
            tickvals=[-1, -0.5, 0, 0.5, 1],
            ticktext=["-1.0", "-0.5", "0.0", "0.5", "1.0"]
        )
    ))

    for i in range(len(station_names)):
        for j in range(len(station_names)):
            if i == j:
                fig.add_annotation(
                    x=station_names[j],
                    y=station_names[i],
                    text="1.00",
                    showarrow=False,
                    font=dict(color="white", size=12, weight="bold")
                )

    fig.update_layout(
        title="站点间水位相关系数热力图",
        xaxis_title="站点",
        yaxis_title="站点",
        height=350,
        template='plotly_white',
        margin=dict(l=60, r=20, t=50, b=50)
    )

    return fig


def plot_lag_correlation(data_matrix, ref_station):
    station_names = [st['name'] for st in monitoring_state['stations']]
    ref_name = station_names[ref_station]

    max_lag = 10
    lags = list(range(max_lag + 1))
    colors = ['#e53935', '#fb8c00', '#43a047', '#1e88e5', '#8e24aa']

    fig = go.Figure()

    ref_data = np.array(data_matrix[ref_station])
    n = len(ref_data)

    for i in range(5):
        if i == ref_station:
            continue

        target_data = np.array(data_matrix[i])
        corr_values = []

        for lag in lags:
            if lag == 0:
                x = ref_data
                y = target_data
            else:
                x = ref_data[:-lag]
                y = target_data[lag:]

            min_len = min(len(x), len(y))
            if min_len >= 5:
                x = x[:min_len]
                y = y[:min_len]
                corr = np.corrcoef(x, y)[0, 1]
                if np.isnan(corr):
                    corr = 0
            else:
                corr = 0
            corr_values.append(corr)

        fig.add_trace(go.Scatter(
            x=lags,
            y=corr_values,
            mode='lines+markers',
            name=f"{ref_name} → {station_names[i]}",
            line=dict(color=colors[i], width=2),
            marker=dict(size=8, color=colors[i])
        ))

    fig.add_hline(y=0, line_dash="dash", line_color="#999", line_width=1)

    fig.update_layout(
        title=f"滞后相关分析（参考站：{ref_name}）",
        xaxis_title="滞后时步（滞后k步后参考站与对比站的相关系数）",
        yaxis_title="互相关系数",
        yaxis_range=[-1.1, 1.1],
        height=300,
        template='plotly_white',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=60, r=20, t=50, b=60)
    )

    return fig

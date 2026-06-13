"""
洪水预报模块
- 基于预报降雨的产流汇流计算
- 实时校正 (误差自回归模型)
- 预报不确定性与置信区间
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from .runoff_models import get_runoff_model
from .routing_models import RoutingModel


class Forecaster:
    """洪水预报器"""

    def __init__(self, dt_hours: float = 1.0, area_km2: float = 1.0):
        self.dt_hours = dt_hours
        self.area_km2 = area_km2
        self.correction_coeffs: List[float] = [0.5, 0.3, 0.2]
        self.decay_factor = 0.8
        self.error_history: List[float] = []
        self.last_correction_time = None
        self.confidence_alpha = 0.90
        self.historical_errors: List[float] = []

    def set_correction_params(self, coeffs: List[float], decay_factor: float = 0.8):
        """设置校正参数"""
        self.correction_coeffs = list(coeffs)
        self.decay_factor = float(decay_factor)

    def set_historical_errors(self, errors: List[float]):
        """设置历史率定误差，用于置信区间估计"""
        self.historical_errors = [float(e) for e in errors if np.isfinite(e)]

    def forecast(self, forecast_rainfall: np.ndarray,
                 initial_conditions: Dict,
                 model_params: Dict,
                 runoff_model_type: str = '蓄满产流',
                 routing_method: str = 'Nash',
                 forecast_evaporation: Optional[np.ndarray] = None) -> Dict:
        """
        执行洪水预报

        参数:
            forecast_rainfall: 预报降雨量序列 (mm)
            initial_conditions: 初始条件 {'W0', 'Qg0', 'WU0', 'WL0', 'WD0'}
            model_params: 已率定的模型参数
            runoff_model_type: 产流模型类型
            routing_method: 汇流方法

        返回:
            预报结果字典
        """
        forecast_rainfall = np.array(forecast_rainfall, dtype=float)
        n = len(forecast_rainfall)

        if forecast_evaporation is None:
            forecast_evaporation = np.zeros(n)
        else:
            forecast_evaporation = np.array(forecast_evaporation, dtype=float)

        params = dict(model_params)
        for k, v in initial_conditions.items():
            params.setdefault(k, v)

        runoff_model = get_runoff_model(runoff_model_type, self.dt_hours, self.area_km2)
        runoff_result = runoff_model.run(forecast_rainfall, forecast_evaporation, **params)

        routing_model = RoutingModel(self.dt_hours, self.area_km2)
        routing_result = routing_model.run(
            runoff_result['runoff_surface'],
            runoff_result['runoff_underground'],
            routing_method,
            **params
        )

        Q_forecast = routing_result['Q_total']

        ci_lower, ci_upper = self._calculate_confidence_interval(Q_forecast)

        peak_idx = int(np.argmax(Q_forecast))
        peak_flow = float(Q_forecast[peak_idx])
        peak_time_hours = peak_idx * self.dt_hours

        return {
            'Q_forecast': Q_forecast,
            'Q_surface': routing_result['Q_surface'],
            'Q_underground': routing_result['Q_underground'],
            'runoff_total': runoff_result['runoff_total'],
            'runoff_surface': runoff_result['runoff_surface'],
            'runoff_underground': runoff_result['runoff_underground'],
            'soil_storage': runoff_result.get('soil_storage', np.zeros(n)),
            'cumulative_runoff': runoff_result.get('cumulative_runoff', np.cumsum(runoff_result['runoff_total'])),
            'ci_lower': ci_lower,
            'ci_upper': ci_upper,
            'peak_flow': peak_flow,
            'peak_time_idx': peak_idx,
            'peak_time_hours': peak_time_hours,
            'unit_hydrograph': routing_result['unit_hydrograph']
        }

    def _calculate_confidence_interval(self, Q_forecast: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """基于历史误差统计计算置信区间"""
        n = len(Q_forecast)
        if len(self.historical_errors) < 10:
            sigma = np.maximum(np.std(Q_forecast) * 0.15, 0.01)
        else:
            sigma = np.std(self.historical_errors)
            sigma = max(sigma, 0.01)

        z_score = 1.645 if self.confidence_alpha == 0.90 else 1.96
        margin = z_score * sigma

        ci_lower = np.maximum(Q_forecast - margin, 0.0)
        ci_upper = Q_forecast + margin

        return ci_lower, ci_upper

    def realtime_correction(self, forecast: np.ndarray,
                            observed: np.ndarray,
                            current_time_idx: int,
                            correction_coeff: Optional[List[float]] = None) -> Dict:
        """
        实时校正 - 误差自回归模型

        参数:
            forecast: 原始预报流量序列
            observed: 已观测到的流量序列 (与forecast同时段长度，前面为实测值，后面为NaN)
            current_time_idx: 当前时间步索引 (已观测到的最后一个时段)
            correction_coeff: 自回归系数，默认[0.5, 0.3, 0.2]

        返回:
            校正后预报结果
        """
        forecast = np.array(forecast, dtype=float).copy()
        observed = np.array(observed, dtype=float).copy()
        n = len(forecast)

        if correction_coeff is None:
            coeffs = self.correction_coeffs.copy()
        else:
            coeffs = list(correction_coeff)

        errors = np.zeros(n)
        for i in range(min(current_time_idx + 1, n)):
            if not np.isnan(observed[i]):
                errors[i] = observed[i] - forecast[i]

        if self.last_correction_time is not None:
            elapsed = (current_time_idx - self.last_correction_time) * self.dt_hours
            decay_steps = int(elapsed / 6.0)
            decay = self.decay_factor ** decay_steps
            coeffs = [c * decay for c in coeffs]
        self.last_correction_time = current_time_idx

        corrected = forecast.copy()
        p = len(coeffs)

        for i in range(current_time_idx + 1, n):
            correction = 0.0
            for j in range(min(p, i - current_time_idx)):
                err_idx = i - j - 1
                if err_idx >= 0:
                    if err_idx <= current_time_idx and not np.isnan(observed[err_idx]):
                        e = observed[err_idx] - forecast[err_idx]
                    else:
                        e = errors[err_idx]
                    correction += coeffs[j] * e
            corrected[i] = forecast[i] + correction
            corrected[i] = max(corrected[i], 0.0)
            errors[i] = correction

        return {
            'Q_forecast_raw': forecast,
            'Q_forecast_corrected': corrected,
            'errors': errors,
            'correction_coefficients': coeffs
        }

    def compare_with_warning_level(self, Q_forecast: np.ndarray,
                                   warning_level: float) -> Dict:
        """
        对比预报流量与警戒水位/流量

        参数:
            Q_forecast: 预报流量序列
            warning_level: 警戒流量 (m³/s)

        返回:
            超过警戒信息
        """
        Q = np.array(Q_forecast)
        above_mask = Q >= warning_level
        above_count = int(np.sum(above_mask))

        first_above_idx = None
        if above_count > 0:
            first_above_idx = int(np.where(above_mask)[0][0])

        max_above = float(np.max(Q)) - warning_level if above_count > 0 else 0.0

        return {
            'warning_level': warning_level,
            'exceed_count': above_count,
            'exceed_duration_hours': above_count * self.dt_hours,
            'first_exceed_idx': first_above_idx,
            'first_exceed_hours': first_above_idx * self.dt_hours if first_above_idx is not None else None,
            'max_exceed': max(max_above, 0.0),
            'will_exceed': above_count > 0
        }

"""
多场次分析与模型评估模块
- 批量运行多个历史洪水场次
- 统计各场次NSE/洪峰相对误差/峰现时间误差
- 计算合格率
- 实测vs模拟洪峰散点图 / 误差分布直方图
- 不同产流模型对比
- 留一交叉验证 (LOOCV)
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from copy import deepcopy

from .runoff_models import get_runoff_model
from .routing_models import RoutingModel, calculate_metrics
from .calibration import ModelCalibrator


class MultiEventEvaluator:
    """多场次模型评估"""

    def __init__(self, dt_hours: float = 1.0, area_km2: float = 1.0):
        self.dt_hours = dt_hours
        self.area_km2 = area_km2
        self.results: List[Dict] = []
        self.summary: Optional[Dict] = None

    def run_batch(self, event_list: List[pd.DataFrame],
                  model_params: Dict,
                  runoff_model_type: str = '蓄满产流',
                  routing_method: str = 'Nash') -> Dict:
        """
        批量运行多个场次

        参数:
            event_list: 场次洪水数据列表
            model_params: 模型参数
            runoff_model_type: 产流模型类型
            routing_method: 汇流方法

        返回:
            评估汇总结果
        """
        self.results = []

        for i, event_df in enumerate(event_list):
            result = self._run_single_event(event_df, model_params,
                                            runoff_model_type, routing_method)
            result['event_id'] = i + 1
            result['event_name'] = f'洪水{i + 1}'
            if 'start_time' in event_df.attrs:
                result['start_time'] = str(event_df.attrs['start_time'])
            self.results.append(result)

        self.summary = self._compute_summary()
        return self.summary

    def _run_single_event(self, event_df: pd.DataFrame, model_params: Dict,
                          runoff_model_type: str, routing_method: str) -> Dict:
        rainfall = event_df['rainfall'].fillna(0).values
        evaporation = event_df['evaporation'].fillna(0).values if 'evaporation' in event_df.columns else None
        Q_obs = event_df['runoff'].values if 'runoff' in event_df.columns else None

        runoff_model = get_runoff_model(runoff_model_type, self.dt_hours, self.area_km2)
        runoff_result = runoff_model.run(rainfall, evaporation, **model_params)

        routing_model = RoutingModel(self.dt_hours, self.area_km2)
        routing_result = routing_model.run(
            runoff_result['runoff_surface'],
            runoff_result['runoff_underground'],
            routing_method,
            **model_params
        )

        Q_cal = routing_result['Q_total']
        metrics = {}
        peak_obs = None
        peak_cal = None
        if Q_obs is not None and not np.isnan(Q_obs).all():
            metrics = calculate_metrics(Q_obs, Q_cal)
            peak_obs = float(metrics.get('peak_obs', 0.0))
            peak_cal = float(metrics.get('peak_cal', 0.0))

        return {
            'Q_obs': Q_obs.tolist() if Q_obs is not None else None,
            'Q_cal': Q_cal.tolist(),
            'metrics': metrics,
            'NSE': float(metrics.get('NSE', np.nan)),
            'DC': float(metrics.get('DC', np.nan)),
            'peak_obs': peak_obs,
            'peak_cal': peak_cal,
            'peak_error_pct': float(metrics.get('peak_error', np.nan)),
            'peak_time_error': float(metrics.get('peak_time_error', np.nan)),
            'relative_error_pct': float(metrics.get('relative_error', np.nan))
        }

    def _compute_summary(self) -> Dict:
        """计算评估汇总统计"""
        if not self.results:
            return {}

        nse_values = [r['NSE'] for r in self.results if np.isfinite(r['NSE'])]
        peak_errors = [r['peak_error_pct'] for r in self.results if np.isfinite(r['peak_error_pct'])]
        time_errors = [r['peak_time_error'] for r in self.results if np.isfinite(r['peak_time_error'])]
        rel_errors = [r['relative_error_pct'] for r in self.results if np.isfinite(r['relative_error_pct'])]
        peaks_obs = [r['peak_obs'] for r in self.results if r['peak_obs'] is not None]
        peaks_cal = [r['peak_cal'] for r in self.results if r['peak_cal'] is not None]

        peak_pass = sum(1 for e in peak_errors if abs(e) < 20.0)
        peak_pass_rate = peak_pass / len(peak_errors) * 100.0 if peak_errors else 0.0

        return {
            'n_events': len(self.results),
            'nse_mean': float(np.mean(nse_values)) if nse_values else np.nan,
            'nse_std': float(np.std(nse_values)) if nse_values else np.nan,
            'nse_min': float(np.min(nse_values)) if nse_values else np.nan,
            'nse_max': float(np.max(nse_values)) if nse_values else np.nan,
            'peak_error_mean': float(np.mean(peak_errors)) if peak_errors else np.nan,
            'peak_error_abs_mean': float(np.mean(np.abs(peak_errors))) if peak_errors else np.nan,
            'peak_time_error_mean': float(np.mean(time_errors)) if time_errors else np.nan,
            'relative_error_mean': float(np.mean(rel_errors)) if rel_errors else np.nan,
            'peak_pass_rate_pct': float(peak_pass_rate),
            'peak_pass_count': int(peak_pass),
            'peaks_obs': peaks_obs,
            'peaks_cal': peaks_cal,
            'nse_values': nse_values,
            'peak_errors': peak_errors,
            'time_errors': time_errors,
            'results': self.results
        }

    def compare_models(self, event_list: List[pd.DataFrame],
                       models_config: List[Dict]) -> Dict:
        """
        对比不同产流模型在同批场次上的表现

        参数:
            event_list: 场次洪水数据列表
            models_config: 模型配置列表，每项含 {'runoff_type', 'params', 'name'}

        返回:
            对比结果
        """
        comparison = {}
        for cfg in models_config:
            name = cfg.get('name', cfg['runoff_type'])
            summary = self.run_batch(
                event_list, cfg['params'],
                cfg['runoff_type'],
                cfg.get('routing_method', 'Nash')
            )
            comparison[name] = {
                'summary': summary,
                'config': cfg
            }
        return comparison

    def leave_one_out_cv(self, event_list: List[pd.DataFrame],
                         runoff_model_type: str = '蓄满产流',
                         routing_method: str = 'Nash',
                         param_names: Optional[List[str]] = None,
                         param_bounds: Optional[List[Tuple]] = None,
                         max_generations: int = 300) -> Dict:
        """
        留一交叉验证 (LOOCV)
        用N-1场率定，1场验证，轮换

        参数:
            event_list: 场次洪水数据列表
            runoff_model_type: 产流模型类型
            routing_method: 汇流方法
            param_names: 参数名列表
            param_bounds: 参数边界列表
            max_generations: 最大进化代数

        返回:
            交叉验证结果
        """
        n = len(event_list)
        if n < 2:
            return {'error': '至少需要2场洪水进行交叉验证'}

        cv_results = []

        for i in range(n):
            train_events = [event_list[j] for j in range(n) if j != i]
            test_event = event_list[i]

            calibrator = ModelCalibrator(self.dt_hours, self.area_km2)

            try:
                cal_result = calibrator.calibrate(
                    train_events,
                    runoff_model_type=runoff_model_type,
                    routing_method=routing_method,
                    param_names=param_names,
                    param_bounds=param_bounds,
                    algorithm='SCE-UA',
                    max_generations=max_generations,
                    n_complexes=2
                )
                best_params = cal_result['best_params']

                test_result = self._run_single_event(
                    test_event, best_params, runoff_model_type, routing_method
                )

                cv_results.append({
                    'fold': i + 1,
                    'test_event': i + 1,
                    'NSE_calibration': cal_result['best_NSE'],
                    'NSE_validation': test_result['NSE'],
                    'peak_error_validation': test_result['peak_error_pct'],
                    'peak_time_error_validation': test_result['peak_time_error'],
                    'params': best_params
                })
            except Exception as e:
                cv_results.append({
                    'fold': i + 1,
                    'test_event': i + 1,
                    'error': str(e)
                })

        valid_nse = [r['NSE_validation'] for r in cv_results if 'NSE_validation' in r and np.isfinite(r['NSE_validation'])]
        valid_peak_err = [r['peak_error_validation'] for r in cv_results if 'peak_error_validation' in r and np.isfinite(r['peak_error_validation'])]

        return {
            'folds': cv_results,
            'n_folds': n,
            'mean_validation_NSE': float(np.mean(valid_nse)) if valid_nse else np.nan,
            'std_validation_NSE': float(np.std(valid_nse)) if valid_nse else np.nan,
            'mean_peak_error': float(np.mean(valid_peak_err)) if valid_peak_err else np.nan
        }

    def get_scatter_data(self) -> Dict:
        """获取实测vs模拟洪峰散点图数据"""
        if not self.summary or 'peaks_obs' not in self.summary:
            return {}

        peaks_obs = self.summary['peaks_obs']
        peaks_cal = self.summary['peaks_cal']

        if not peaks_obs:
            return {}

        max_val = max(max(peaks_obs), max(peaks_cal)) * 1.1

        return {
            'observed': peaks_obs,
            'simulated': peaks_cal,
            'one2one_x': [0, max_val],
            'one2one_y': [0, max_val],
            'max_val': max_val
        }

    def get_error_histogram_data(self, nbins: int = 10) -> Dict:
        """获取误差分布直方图数据"""
        if not self.summary or 'peak_errors' not in self.summary:
            return {}

        errors = self.summary['peak_errors']
        if not errors:
            return {}

        hist, bin_edges = np.histogram(errors, bins=nbins)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

        return {
            'errors': errors,
            'histogram': hist.tolist(),
            'bin_edges': bin_edges.tolist(),
            'bin_centers': bin_centers.tolist(),
            'mean': float(np.mean(errors)),
            'std': float(np.std(errors))
        }

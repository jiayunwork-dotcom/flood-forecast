"""
产流模型模块
- 蓄满产流模型 (SCS-CN / 蓄水容量曲线)
- 超渗产流模型 (Green-Ampt入渗)
- 混合产流模型
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple


class RunoffModel:
    """产流计算基类"""

    def __init__(self, dt_hours: float = 1.0, area_km2: float = 1.0):
        self.dt_hours = dt_hours
        self.area_km2 = area_km2

    def run(self, rainfall: np.ndarray, evaporation: Optional[np.ndarray] = None,
            **params) -> Dict:
        raise NotImplementedError


class SaturationExcessModel(RunoffModel):
    """
    蓄满产流模型
    基于流域蓄水容量曲线(抛物线分布) + 三层蒸散发模型

    参数:
        WM: 流域最大蓄水容量 (mm)
        B:  蓄水容量曲线分布指数
        WU0: 上层初始蓄水量 (mm)
        WL0: 下层初始蓄水量 (mm)
        WD0: 深层初始蓄水量 (mm)
        K:  蒸散发折算系数
        C:  深层蒸散发系数
    """

    DEFAULT_PARAMS = {
        'WM': 150.0,
        'B': 0.3,
        'WU0': 20.0,
        'WL0': 60.0,
        'WD0': 20.0,
        'K': 1.0,
        'C': 0.15,
        'WUM': 20.0,
        'WLM': 60.0
    }

    def run(self, rainfall: np.ndarray, evaporation: Optional[np.ndarray] = None,
            **params) -> Dict:
        p = np.array(rainfall, dtype=float).copy()
        n = len(p)

        if evaporation is None:
            E_pan = np.zeros(n)
        else:
            E_pan = np.array(evaporation, dtype=float).copy()

        for k, v in self.DEFAULT_PARAMS.items():
            params.setdefault(k, v)

        WM = float(params['WM'])
        B = float(params['B'])
        WU = float(params['WU0'])
        WL = float(params['WL0'])
        WD = float(params['WD0'])
        K = float(params.get('K_ET', params.get('K', 1.0)))
        C = float(params['C'])
        WUM = float(params['WUM'])
        WLM = float(params['WLM'])
        WDM = max(WM - WUM - WLM, 1.0)

        R_total = np.zeros(n)
        R_surface = np.zeros(n)
        R_underground = np.zeros(n)
        E_actual = np.zeros(n)
        W_storage = np.zeros(n)

        WMM = WM * (1.0 + B)

        for i in range(n):
            P_i = max(p[i], 0.0)
            Ep_i = max(E_pan[i] * K, 0.0) if i < len(E_pan) else 0.0

            if P_i > 0:
                W = WU + WL + WD
                W = min(W, WM)

                if W + P_i <= WM:
                    a = WMM * (1.0 - (1.0 - W / WM) ** (1.0 / (1.0 + B)))
                    if P_i + a <= WMM:
                        R = P_i + W - WM + WM * (1.0 - (P_i + a) / WMM) ** (1.0 + B)
                    else:
                        R = P_i + W - WM
                else:
                    R = P_i + W - WM

                R = max(R, 0.0)
                P_e = max(P_i - R, 0.0)

                if WU + P_e < WUM:
                    WU += P_e
                else:
                    rest = WU + P_e - WUM
                    WU = WUM
                    if WL + rest < WLM:
                        WL += rest
                    else:
                        WD += (WL + rest - WLM)
                        WL = WLM
            else:
                R = 0.0

            if Ep_i > 0:
                if WU >= Ep_i:
                    E = Ep_i
                    WU -= E
                else:
                    E1 = WU
                    WU = 0.0
                    E2 = (Ep_i - E1) * WL / WLM if WLM > 0 else 0.0
                    E2 = min(E2, WL)
                    WL -= E2
                    if E1 + E2 < Ep_i:
                        E3 = C * (Ep_i - E1 - E2)
                        E3 = min(E3, WD)
                        WD -= E3
                        E = E1 + E2 + E3
                    else:
                        E = E1 + E2
                E_actual[i] = E

            R_total[i] = R
            R_surface[i] = R * 0.7 if R > 0 else 0.0
            R_underground[i] = R * 0.3 if R > 0 else 0.0
            W_storage[i] = min(WU + WL + WD, WM)

        cum_R = np.cumsum(R_total)
        runoff_coef = np.where(cum_R > 0, cum_R / np.maximum(np.cumsum(p), 1e-6), 0.0)

        return {
            'runoff_total': R_total,
            'runoff_surface': R_surface,
            'runoff_underground': R_underground,
            'evaporation_actual': E_actual,
            'soil_storage': W_storage,
            'cumulative_runoff': cum_R,
            'runoff_coefficient': runoff_coef,
            'params': params
        }


class GreenAmptModel(RunoffModel):
    """
    超渗产流模型 - Green-Ampt入渗方程

    参数:
        Ks: 饱和导水率 (mm/h)
        Sf: 湿润锋吸力 (mm)
        theta_i: 初始含水率 (体积分数)
        theta_s: 饱和含水率 (体积分数)
    """

    DEFAULT_PARAMS = {
        'Ks': 5.0,
        'Sf': 50.0,
        'theta_i': 0.20,
        'theta_s': 0.45
    }

    def run(self, rainfall: np.ndarray, evaporation: Optional[np.ndarray] = None,
            **params) -> Dict:
        p = np.array(rainfall, dtype=float).copy()
        n = len(p)

        for k, v in self.DEFAULT_PARAMS.items():
            params.setdefault(k, v)

        Ks = float(params['Ks'])
        Sf = float(params['Sf'])
        theta_i = float(params['theta_i'])
        theta_s = float(params['theta_s'])
        d_theta = max(theta_s - theta_i, 0.001)

        R_surface = np.zeros(n)
        infiltration = np.zeros(n)
        cum_infil = 0.0
        wetting_front = 0.0

        for i in range(n):
            P_i = max(p[i], 0.0)
            intensity = P_i / self.dt_hours if self.dt_hours > 0 else 0.0

            if P_i > 0 and d_theta > 0:
                if cum_infil > 0:
                    f_cap = Ks * (1.0 + Sf * d_theta / cum_infil)
                else:
                    f_cap = 1e6

                f_cap = min(f_cap, 1e6)
                f_actual = min(intensity, f_cap)
                infil_i = f_actual * self.dt_hours
                infil_i = min(infil_i, P_i)

                cum_infil += infil_i
                wetting_front = cum_infil / d_theta if d_theta > 0 else 0

                R_surface[i] = max(P_i - infil_i, 0.0)
                infiltration[i] = infil_i
            else:
                infiltration[i] = 0.0
                R_surface[i] = 0.0

        R_underground = np.zeros(n)
        for i in range(n):
            R_underground[i] = infiltration[i] * 0.05

        R_total = R_surface + R_underground
        cum_R = np.cumsum(R_total)
        runoff_coef = np.where(cum_R > 0, cum_R / np.maximum(np.cumsum(p), 1e-6), 0.0)

        return {
            'runoff_total': R_total,
            'runoff_surface': R_surface,
            'runoff_underground': R_underground,
            'infiltration': infiltration,
            'cumulative_runoff': cum_R,
            'runoff_coefficient': runoff_coef,
            'wetting_front_depth': np.full(n, wetting_front),
            'params': params
        }


class MixedRunoffModel(RunoffModel):
    """
    混合产流模型
    蓄满产流处理地下径流(壤中流+地下径流)
    超渗产流处理地表径流
    """

    DEFAULT_PARAMS = {
        'WM': 150.0,
        'B': 0.3,
        'WU0': 20.0,
        'WL0': 60.0,
        'WD0': 20.0,
        'K': 1.0,
        'C': 0.15,
        'WUM': 20.0,
        'WLM': 60.0,
        'Ks': 5.0,
        'Sf': 50.0,
        'theta_i': 0.20,
        'theta_s': 0.45,
        'sat_ratio': 0.3
    }

    def run(self, rainfall: np.ndarray, evaporation: Optional[np.ndarray] = None,
            **params) -> Dict:
        for k, v in self.DEFAULT_PARAMS.items():
            params.setdefault(k, v)

        sat_ratio = float(params.pop('sat_ratio', 0.3))
        sat_ratio = np.clip(sat_ratio, 0.0, 1.0)

        sat_params = {k: params[k] for k in params if k in SaturationExcessModel.DEFAULT_PARAMS}
        ga_params = {k: params[k] for k in params if k in GreenAmptModel.DEFAULT_PARAMS}

        sat_model = SaturationExcessModel(self.dt_hours, self.area_km2)
        ga_model = GreenAmptModel(self.dt_hours, self.area_km2)

        sat_result = sat_model.run(rainfall, evaporation, **sat_params)
        ga_result = ga_model.run(rainfall, evaporation, **ga_params)

        R_surface = ga_result['runoff_surface'] * (1 - sat_ratio) + \
                    sat_result['runoff_surface'] * sat_ratio
        R_underground = sat_result['runoff_underground']
        R_total = R_surface + R_underground

        cum_R = np.cumsum(R_total)
        p_arr = np.array(rainfall, dtype=float)
        runoff_coef = np.where(cum_R > 0, cum_R / np.maximum(np.cumsum(p_arr), 1e-6), 0.0)

        return {
            'runoff_total': R_total,
            'runoff_surface': R_surface,
            'runoff_underground': R_underground,
            'evaporation_actual': sat_result.get('evaporation_actual', np.zeros_like(R_total)),
            'soil_storage': sat_result.get('soil_storage', np.zeros_like(R_total)),
            'cumulative_runoff': cum_R,
            'runoff_coefficient': runoff_coef,
            'sat_result': sat_result,
            'ga_result': ga_result,
            'params': params
        }


def get_runoff_model(model_type: str, dt_hours: float = 1.0,
                     area_km2: float = 1.0) -> RunoffModel:
    """工厂函数获取产流模型"""
    models = {
        '蓄满产流': SaturationExcessModel,
        'SaturationExcess': SaturationExcessModel,
        '超渗产流': GreenAmptModel,
        'GreenAmpt': GreenAmptModel,
        '混合产流': MixedRunoffModel,
        'Mixed': MixedRunoffModel
    }
    cls = models.get(model_type, SaturationExcessModel)
    return cls(dt_hours, area_km2)

"""
汇流模型模块
- Nash瞬时单位线
- Muskingum河道演算
- 线性水库(地下水汇流)
"""

import numpy as np
from scipy.special import gamma as gamma_func
from typing import Dict, Optional, List, Tuple


class UnitHydrograph:
    """单位线法汇流"""

    @staticmethod
    def nash_uh(n: float, K: float, dt: float, n_points: int = 50) -> np.ndarray:
        """
        Nash瞬时单位线 (n个线性水库串联)

        参数:
            n: 线性水库个数
            K: 每个水库的调蓄系数 (小时)
            dt: 时段长 (小时)
            n_points: 单位线时段数

        返回:
            单位线纵标 (m³/s per mm) - 已归一化
        """
        n = max(0.5, float(n))
        K = max(0.1, float(K))
        dt = max(0.01, float(dt))

        t = np.arange(1, n_points + 1) * dt
        u = (t ** (n - 1)) * np.exp(-t / K) / (K ** n * gamma_func(n))
        u = u * dt

        if u.sum() > 0:
            u = u / u.sum()

        return u

    @staticmethod
    def estimate_nk_from_moments(uh: np.ndarray, dt: float) -> Tuple[float, float]:
        """
        矩法从实测单位线反推Nash单位线参数n和K
        一阶矩 = n*K, 二阶中心矩 = n*K²
        """
        uh = np.array(uh, dtype=float)
        if uh.sum() == 0:
            return 2.0, 3.0

        t = np.arange(1, len(uh) + 1) * dt
        uh_norm = uh / uh.sum()

        m1 = np.sum(t * uh_norm)
        m2 = np.sum((t - m1) ** 2 * uh_norm)

        if m2 > 0 and m1 > 0:
            K = m2 / m1
            n = m1 / K if K > 0 else 2.0
        else:
            n, K = 2.0, 3.0

        return max(0.5, n), max(0.1, K)

    @staticmethod
    def convolve(runoff_mm: np.ndarray, unit_hydrograph: np.ndarray,
                 area_km2: float, dt_hours: float) -> np.ndarray:
        """
        产流量(mm)与单位线卷积计算流量过程

        参数:
            runoff_mm: 时段产流量 (mm)
            unit_hydrograph: 单位线纵标 (归一化, 或m³/s/mm)
            area_km2: 流域面积 (km²)
            dt_hours: 时段长 (小时)

        返回:
            流量过程 (m³/s)
        """
        r = np.array(runoff_mm, dtype=float)
        uh = np.array(unit_hydrograph, dtype=float)

        if uh.sum() > 0 and abs(uh.sum() - 1.0) > 0.01:
            conv_factor = area_km2 / (3.6 * dt_hours)
            uh_norm = uh / uh.sum()
        else:
            conv_factor = area_km2 / (3.6 * dt_hours)
            uh_norm = uh if uh.sum() > 0 else np.array([1.0])

        q = np.convolve(r, uh_norm)[:len(r)]
        q = q * conv_factor

        return q


class MuskingumModel:
    """Muskingum河道演算"""

    @staticmethod
    def check_stability(K: float, X: float, dt: float) -> Tuple[bool, float]:
        """
        检查Muskingum稳定性条件: 2KX ≤ dt ≤ 2K(1-X)

        返回:
            (是否稳定, 推荐细分时段内子时段数)
        """
        lower = 2.0 * K * X
        upper = 2.0 * K * (1.0 - X)
        if lower <= dt <= upper:
            return True, 1

        n_sub = max(1, int(np.ceil(dt / lower))) if lower > 0 else 1
        n_sub = max(n_sub, int(np.ceil(dt / max(upper, 1e-6))))
        return False, n_sub

    @staticmethod
    def route(inflow: np.ndarray, K: float, X: float, dt: float,
              Q0: Optional[float] = None) -> np.ndarray:
        """
        Muskingum河道演算

        参数:
            inflow: 入流过程 (m³/s)
            K: 槽蓄常数 (小时)
            X: 流量比重因子 (0-0.5)
            dt: 时段长 (小时)
            Q0: 初始出流 (m³/s)

        返回:
            出流过程 (m³/s)
        """
        I = np.array(inflow, dtype=float)
        n = len(I)

        stable, n_sub = MuskingumModel.check_stability(K, X, dt)
        if not stable and n_sub > 1:
            dt_sub = dt / n_sub
            I_sub = np.repeat(I, n_sub)
            result = MuskingumModel._route_single(I_sub, K, X, dt_sub, Q0)
            idx = np.arange(0, len(result), n_sub)
            return result[idx][:n]

        return MuskingumModel._route_single(I, K, X, dt, Q0)

    @staticmethod
    def _route_single(I: np.ndarray, K: float, X: float, dt: float,
                      Q0: Optional[float]) -> np.ndarray:
        n = len(I)
        Q = np.zeros(n)
        Q[0] = Q0 if Q0 is not None else I[0]

        C1 = (dt - 2 * K * X) / (2 * K * (1 - X) + dt)
        C2 = (dt + 2 * K * X) / (2 * K * (1 - X) + dt)
        C3 = (2 * K * (1 - X) - dt) / (2 * K * (1 - X) + dt)

        for i in range(1, n):
            Q[i] = C1 * I[i] + C2 * I[i - 1] + C3 * Q[i - 1]
            Q[i] = max(Q[i], 0.0)

        return Q


class LinearReservoir:
    """一阶线性水库模型 (用于地下水汇流)"""

    @staticmethod
    def route(runoff_mm: np.ndarray, Kg: float, area_km2: float,
              dt_hours: float, Qg0: float = 0.0) -> np.ndarray:
        """
        线性水库出流演算

        参数:
            runoff_mm: 地下水产流量 (mm)
            Kg: 地下水退水常数 (小时)
            area_km2: 流域面积 (km²)
            dt_hours: 时段长 (小时)
            Qg0: 初始地下径流 (m³/s)

        返回:
            地下径流过程 (m³/s)
        """
        r = np.array(runoff_mm, dtype=float)
        n = len(r)

        conv_factor = area_km2 / (3.6 * dt_hours)
        inflow = r * conv_factor

        alpha = np.exp(-dt_hours / max(Kg, 0.01))
        Qg = np.zeros(n)
        Qg[0] = Qg0

        for i in range(1, n):
            Qg[i] = alpha * Qg[i - 1] + (1 - alpha) * inflow[i - 1]
            Qg[i] = max(Qg[i], 0.0)

        return Qg


class RoutingModel:
    """完整汇流模型"""

    def __init__(self, dt_hours: float = 1.0, area_km2: float = 1.0):
        self.dt_hours = dt_hours
        self.area_km2 = area_km2

    def run(self, surface_runoff: np.ndarray, underground_runoff: np.ndarray,
            method: str = 'Nash', **params) -> Dict:
        """
        汇流计算

        参数:
            surface_runoff: 地表产流量 (mm)
            underground_runoff: 地下产流量 (mm)
            method: 汇流方法 ('Nash', 'Muskingum', 'ManualUH')
            params: 汇流参数

        返回:
            汇流结果字典
        """
        surface_runoff = np.array(surface_runoff, dtype=float)
        underground_runoff = np.array(underground_runoff, dtype=float)
        n = len(surface_runoff)

        if method in ('Nash', '单位线'):
            nash_n = float(params.get('n', 2.0))
            nash_K = float(params.get('K_uh', params.get('K', 3.0)))
            uh_points = min(int(10 * nash_K / max(self.dt_hours, 0.1)), 100)
            uh_points = max(uh_points, 10)
            uh = UnitHydrograph.nash_uh(nash_n, nash_K, self.dt_hours, uh_points)
            Q_surface = UnitHydrograph.convolve(surface_runoff, uh, self.area_km2, self.dt_hours)

        elif method in ('ManualUH', '手动单位线'):
            uh = np.array(params.get('unit_hydrograph', [1.0]), dtype=float)
            Q_surface = UnitHydrograph.convolve(surface_runoff, uh, self.area_km2, self.dt_hours)
            uh = uh

        elif method in ('Muskingum', '马斯京根'):
            K_musk = float(params.get('K_musk', 6.0))
            X_musk = float(params.get('X_musk', 0.2))
            Q_surface_raw = UnitHydrograph.convolve(
                surface_runoff, np.array([1.0]), self.area_km2, self.dt_hours
            )
            Q_surface = MuskingumModel.route(Q_surface_raw, K_musk, X_musk, self.dt_hours)
            uh = UnitHydrograph.nash_uh(2.0, 3.0, self.dt_hours, 20)

        else:
            uh = UnitHydrograph.nash_uh(2.0, 3.0, self.dt_hours, 20)
            Q_surface = UnitHydrograph.convolve(surface_runoff, uh, self.area_km2, self.dt_hours)

        Kg = float(params.get('Kg', 48.0))
        baseflow = float(params.get('baseflow', 0.0))
        Q_underground = LinearReservoir.route(
            underground_runoff, Kg, self.area_km2, self.dt_hours, baseflow
        )

        Q_total = Q_surface + Q_underground

        return {
            'Q_total': Q_total,
            'Q_surface': Q_surface,
            'Q_underground': Q_underground,
            'unit_hydrograph': uh,
            'params': params
        }


def calculate_metrics(Q_obs: np.ndarray, Q_cal: np.ndarray) -> Dict:
    """
    计算模拟效果评价指标

    返回:
        NSE, DC, 洪峰相对误差, 峰现时间误差(时段), 相对误差
    """
    Q_obs = np.array(Q_obs, dtype=float)
    Q_cal = np.array(Q_cal, dtype=float)

    valid_mask = ~np.isnan(Q_obs) & ~np.isnan(Q_cal)
    if valid_mask.sum() < 2:
        return {'NSE': np.nan, 'DC': np.nan, 'peak_error': np.nan,
                'peak_time_error': np.nan, 'relative_error': np.nan}

    Qo = Q_obs[valid_mask]
    Qc = Q_cal[valid_mask]

    Qo_mean = np.mean(Qo)
    if np.sum((Qo - Qo_mean) ** 2) > 0:
        NSE = 1.0 - np.sum((Qo - Qc) ** 2) / np.sum((Qo - Qo_mean) ** 2)
    else:
        NSE = np.nan

    DC = NSE

    if np.sum(np.abs(Qo)) > 0:
        relative_error = np.sum(np.abs(Qo - Qc)) / np.sum(np.abs(Qo)) * 100.0
    else:
        relative_error = np.nan

    peak_obs_idx = np.argmax(Q_obs[valid_mask])
    peak_cal_idx = np.argmax(Q_cal[valid_mask])
    peak_obs = Qo[peak_obs_idx]
    peak_cal = Qc[peak_cal_idx]

    if peak_obs > 0:
        peak_error = (peak_cal - peak_obs) / peak_obs * 100.0
    else:
        peak_error = np.nan

    peak_time_error = peak_cal_idx - peak_obs_idx

    return {
        'NSE': float(NSE) if not np.isnan(NSE) else 0.0,
        'DC': float(DC) if not np.isnan(DC) else 0.0,
        'peak_error': float(peak_error) if not np.isnan(peak_error) else 0.0,
        'peak_time_error': int(peak_time_error),
        'relative_error': float(relative_error) if not np.isnan(relative_error) else 0.0,
        'peak_obs': float(peak_obs),
        'peak_cal': float(peak_cal)
    }

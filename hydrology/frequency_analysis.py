"""
频率分析模块
- 分布拟合: 皮尔逊III型(P-III) / 对数正态分布 / 广义极值(GEV)
- 参数估计: 矩法 / 最大似然法 / 线性矩法
- 适线检验: K-S检验 / 卡方检验 / P-P图 / Q-Q图
- 设计洪水: 重现期对应设计值 / 同频率放大法
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import gamma as gamma_func
from scipy.optimize import minimize
from typing import Dict, List, Tuple, Optional


class PearsonIIIDistribution:
    """皮尔逊III型分布 (P-III)"""

    @staticmethod
    def pdf(x, alpha, beta, loc):
        """概率密度函数"""
        x = np.asarray(x, dtype=float)
        with np.errstate(invalid='ignore', divide='ignore'):
            z = (x - loc) / beta
            result = np.where(z > 0,
                              (z ** (alpha - 1) * np.exp(-z)) / (beta * gamma_func(alpha)),
                              0.0)
        return result

    @staticmethod
    def cdf(x, alpha, beta, loc):
        """累积分布函数 (使用正则化不完全伽马函数)"""
        x = np.asarray(x, dtype=float)
        from scipy.special import gammainc
        z = np.maximum((x - loc) / beta, 0)
        return gammainc(alpha, z)

    @staticmethod
    def ppf(p, alpha, beta, loc):
        """分位数函数 (百分位点)"""
        from scipy.special import gammaincinv
        p = np.asarray(p, dtype=float)
        p = np.clip(p, 1e-10, 1 - 1e-10)
        z = gammaincinv(alpha, p)
        return loc + beta * z

    @staticmethod
    def fit_moments(data):
        """矩法估计参数"""
        data = np.asarray(data, dtype=float)
        n = len(data)
        mean = np.mean(data)
        var = np.var(data, ddof=1) if n > 1 else 1.0
        std = np.sqrt(var)

        if n > 2 and std > 0:
            m3 = np.sum((data - mean) ** 3) / n
            Cs = m3 / (std ** 3) if std > 0 else 0
        else:
            Cs = 0.0

        if abs(Cs) < 1e-6:
            Cs = 0.1

        alpha = 4.0 / (Cs ** 2)
        beta = std * abs(Cs) / 2.0
        beta = beta if Cs >= 0 else -beta
        loc = mean - 2.0 * std / Cs if Cs != 0 else mean - std * 2

        return alpha, beta, loc, {'mean': mean, 'std': std, 'Cs': Cs, 'Cv': std / mean if mean > 0 else 0}

    @staticmethod
    def fit_mle(data):
        """最大似然估计"""
        data = np.asarray(data, dtype=float)
        data_sorted = np.sort(data)
        mean = np.mean(data)
        std = np.std(data)

        def neg_log_lik(params):
            alpha, beta, loc = params
            if alpha <= 0 or beta <= 0 or np.any(data <= loc):
                return 1e10
            pdf_vals = PearsonIIIDistribution.pdf(data, alpha, beta, loc)
            pdf_vals = np.maximum(pdf_vals, 1e-300)
            return -np.sum(np.log(pdf_vals))

        init = [2.0, std * 0.5, np.min(data) * 0.9]
        try:
            result = minimize(neg_log_lik, init, method='Nelder-Mead',
                              options={'maxiter': 5000})
            alpha, beta, loc = result.x
        except Exception:
            alpha, beta, loc, _ = PearsonIIIDistribution.fit_moments(data)

        Cv = std / mean if mean > 0 else 0
        Cs = 2.0 * std / (mean - loc) if (mean - loc) != 0 else 0
        return alpha, beta, loc, {'mean': mean, 'std': std, 'Cs': Cs, 'Cv': Cv}

    @staticmethod
    def fit_lmoments(data):
        """线性矩法估计参数"""
        data = np.sort(np.asarray(data, dtype=float))
        n = len(data)

        b0 = np.mean(data)
        if n < 2:
            return PearsonIIIDistribution.fit_moments(data)

        j = np.arange(1, n)
        w1 = (j - 1) / (n - 1)
        b1 = np.sum(w1 * data[1:]) / n

        if n < 3:
            t3 = 0
        else:
            j2 = np.arange(2, n)
            w2 = ((j2 - 1) * (j2 - 2)) / ((n - 1) * (n - 2))
            b2 = np.sum(w2 * data[2:]) / n
            l1 = b0
            l2 = 2 * b1 - b0
            l3 = 6 * b2 - 6 * b1 + b0
            t3 = l3 / l2 if l2 > 0 else 0

        mean = b0
        l2 = max(2 * b1 - b0, 1e-6)
        tau3 = np.clip(t3, -0.99, 0.99)

        Cs = 2.0 * tau3 / (1 - tau3 ** 2) if abs(tau3) < 1 else 2.0
        alpha = 4.0 / (Cs ** 2)
        std = l2 * np.sqrt(np.pi) * gamma_func(alpha) / gamma_func(alpha + 0.5)
        beta = std * abs(Cs) / 2.0
        beta = beta if Cs >= 0 else -beta
        loc = mean - alpha * beta

        Cv = std / mean if mean > 0 else 0
        return alpha, beta, loc, {'mean': mean, 'std': std, 'Cs': Cs, 'Cv': Cv}


class LognormalDistribution:
    """对数正态分布"""

    @staticmethod
    def fit(data):
        """拟合对数正态分布"""
        data = np.asarray(data, dtype=float)
        log_data = np.log(np.maximum(data, 1e-10))
        mu = np.mean(log_data)
        sigma = np.std(log_data, ddof=1) if len(data) > 1 else 1.0
        return mu, sigma

    @staticmethod
    def pdf(x, mu, sigma):
        x = np.asarray(x, dtype=float)
        with np.errstate(invalid='ignore', divide='ignore'):
            result = np.where(x > 0,
                              np.exp(-(np.log(x) - mu) ** 2 / (2 * sigma ** 2)) /
                              (x * sigma * np.sqrt(2 * np.pi)),
                              0.0)
        return result

    @staticmethod
    def cdf(x, mu, sigma):
        x = np.asarray(x, dtype=float)
        return stats.lognorm.cdf(x, s=sigma, scale=np.exp(mu))

    @staticmethod
    def ppf(p, mu, sigma):
        p = np.asarray(p, dtype=float)
        return stats.lognorm.ppf(p, s=sigma, scale=np.exp(mu))


class GEVDistribution:
    """广义极值分布 (GEV)"""

    @staticmethod
    def fit(data):
        """拟合GEV分布"""
        data = np.asarray(data, dtype=float)
        c, loc, scale = stats.genextreme.fit(data)
        return c, loc, scale

    @staticmethod
    def pdf(x, c, loc, scale):
        return stats.genextreme.pdf(x, c, loc=loc, scale=scale)

    @staticmethod
    def cdf(x, c, loc, scale):
        return stats.genextreme.cdf(x, c, loc=loc, scale=scale)

    @staticmethod
    def ppf(p, c, loc, scale):
        return stats.genextreme.ppf(p, c, loc=loc, scale=scale)


class FrequencyAnalysis:
    """频率分析主类"""

    STANDARD_RETURN_PERIODS = [2, 5, 10, 20, 50, 100, 200, 500, 1000]

    def __init__(self):
        self.data: Optional[np.ndarray] = None
        self.data_years: Optional[List[int]] = None
        self.distributions: Dict = {}
        self.fits: Dict = {}
        self.warnings: List[str] = []

    def load_annual_maxima(self, values: List[float], years: Optional[List[int]] = None):
        """
        加载年最大洪峰流量序列

        参数:
            values: 洪峰流量序列 (m³/s)
            years: 对应年份 (可选)
        """
        self.data = np.asarray(values, dtype=float)
        self.data_years = years if years else list(range(len(values)))
        self.warnings = []

        if len(self.data) < 20:
            self.warnings.append(f'样本量仅{len(self.data)}年，不足20年，结果可信度较低！')

        self.distributions = {}
        self.fits = {}

    def fit_distribution(self, dist_type: str = 'P-III',
                         method: str = 'moments') -> Dict:
        """
        拟合分布

        参数:
            dist_type: 分布类型 ('P-III', 'Lognormal', 'GEV')
            method: 估计方法 ('moments', 'mle', 'lmoments')

        返回:
            拟合结果
        """
        if self.data is None:
            raise ValueError('请先加载年最大洪峰流量数据')

        data = self.data.copy()
        result = {'type': dist_type, 'method': method}

        if dist_type == 'P-III':
            if method == 'mle':
                alpha, beta, loc, stats_info = PearsonIIIDistribution.fit_mle(data)
            elif method == 'lmoments':
                alpha, beta, loc, stats_info = PearsonIIIDistribution.fit_lmoments(data)
            else:
                alpha, beta, loc, stats_info = PearsonIIIDistribution.fit_moments(data)

            result['params'] = {'alpha': alpha, 'beta': beta, 'loc': loc}
            result['stats'] = stats_info

            if 2.0 <= stats_info['Cs'] / stats_info['Cv'] <= 3.5:
                result['Cs_Cv_ratio'] = stats_info['Cs'] / stats_info['Cv'] if stats_info['Cv'] > 0 else np.nan
            else:
                ratio = stats_info['Cs'] / stats_info['Cv'] if stats_info['Cv'] > 0 else 0
                result['Cs_Cv_ratio'] = ratio
                self.warnings.append(f'P-III分布Cs/Cv比值={ratio:.2f}，超出中国水文经验范围2~3.5')

            def cdf_fn(x):
                return PearsonIIIDistribution.cdf(x, alpha, beta, loc)

            def ppf_fn(p):
                return PearsonIIIDistribution.ppf(p, alpha, beta, loc)

            def pdf_fn(x):
                return PearsonIIIDistribution.pdf(x, alpha, beta, loc)

        elif dist_type == 'Lognormal':
            mu, sigma = LognormalDistribution.fit(data)
            result['params'] = {'mu': mu, 'sigma': sigma}
            result['stats'] = {'mean': np.mean(data), 'std': np.std(data)}

            def cdf_fn(x):
                return LognormalDistribution.cdf(x, mu, sigma)

            def ppf_fn(p):
                return LognormalDistribution.ppf(p, mu, sigma)

            def pdf_fn(x):
                return LognormalDistribution.pdf(x, mu, sigma)

        elif dist_type == 'GEV':
            c, loc, scale = GEVDistribution.fit(data)
            result['params'] = {'c': c, 'loc': loc, 'scale': scale}
            result['stats'] = {'mean': np.mean(data), 'std': np.std(data)}

            def cdf_fn(x):
                return GEVDistribution.cdf(x, c, loc, scale)

            def ppf_fn(p):
                return GEVDistribution.ppf(p, c, loc, scale)

            def pdf_fn(x):
                return GEVDistribution.pdf(x, c, loc, scale)

        else:
            raise ValueError(f'不支持的分布类型: {dist_type}')

        self.fits[dist_type] = {
            'result': result,
            'cdf': cdf_fn,
            'ppf': ppf_fn,
            'pdf': pdf_fn
        }
        return result

    def empirical_cdf(self) -> Tuple[np.ndarray, np.ndarray]:
        """计算经验频率 (Weibull公式)"""
        if self.data is None:
            return np.array([]), np.array([])
        n = len(self.data)
        sorted_data = np.sort(self.data)[::-1]
        ranks = np.arange(1, n + 1)
        p_empirical = ranks / (n + 1)
        return sorted_data, p_empirical

    def ks_test(self, dist_type: str) -> Dict:
        """Kolmogorov-Smirnov适线检验"""
        if dist_type not in self.fits:
            self.fit_distribution(dist_type)

        sorted_data, p_empirical = self.empirical_cdf()
        sorted_data_asc = np.sort(self.data)
        cdf_fn = self.fits[dist_type]['cdf']
        p_theory = cdf_fn(sorted_data_asc)

        p_empirical_asc = np.arange(1, len(sorted_data_asc) + 1) / (len(sorted_data_asc) + 1)
        D = np.max(np.abs(p_theory - p_empirical_asc))
        n = len(self.data)
        D_crit = 1.36 / np.sqrt(n)
        p_value = np.exp(-2 * n * D ** 2) if D > 0 else 1.0

        return {
            'D_statistic': float(D),
            'D_critical_05': float(D_crit),
            'p_value': float(p_value),
            'pass': bool(D < D_crit)
        }

    def chi_square_test(self, dist_type: str, bins: int = 10) -> Dict:
        """卡方适线检验"""
        if dist_type not in self.fits:
            self.fit_distribution(dist_type)

        data = self.data
        cdf_fn = self.fits[dist_type]['cdf']

        edges = np.linspace(np.min(data), np.max(data), bins + 1)
        observed, _ = np.histogram(data, bins=edges)

        p_theory = cdf_fn(edges)
        expected = np.diff(p_theory) * len(data)
        expected = np.maximum(expected, 1.0)

        chi2 = np.sum((observed - expected) ** 2 / expected)
        dof = bins - 1 - len(self.fits[dist_type]['result']['params'])
        dof = max(dof, 1)
        p_value = 1.0 - stats.chi2.cdf(chi2, dof)

        return {
            'chi2_statistic': float(chi2),
            'dof': int(dof),
            'p_value': float(p_value),
            'pass': bool(p_value > 0.05)
        }

    def get_design_values(self, dist_type: str,
                          return_periods: Optional[List[int]] = None) -> Dict:
        """
        计算指定重现期的设计洪峰流量

        参数:
            dist_type: 分布类型
            return_periods: 重现期列表 (年)

        返回:
            设计值字典
        """
        if dist_type not in self.fits:
            self.fit_distribution(dist_type)

        if return_periods is None:
            return_periods = self.STANDARD_RETURN_PERIODS

        ppf_fn = self.fits[dist_type]['ppf']
        result = {}
        for T in return_periods:
            p = 1.0 - 1.0 / T
            design_value = ppf_fn(p)
            result[T] = float(design_value)

        return result

    def get_frequency_curve_data(self, dist_type: str) -> Dict:
        """获取频率曲线绘制数据"""
        if dist_type not in self.fits:
            self.fit_distribution(dist_type)

        ppf_fn = self.fits[dist_type]['ppf']
        cdf_fn = self.fits[dist_type]['cdf']

        sorted_data, p_empirical = self.empirical_cdf()

        T_plot = np.logspace(np.log10(1.1), np.log10(2000), 200)
        p_plot = 1.0 - 1.0 / T_plot
        Q_theory = ppf_fn(p_plot)

        T_empirical = 1.0 / p_empirical

        return {
            'T_theory': T_plot.tolist(),
            'Q_theory': Q_theory.tolist(),
            'T_empirical': T_empirical.tolist(),
            'Q_empirical': sorted_data.tolist(),
            'p_empirical': p_empirical.tolist(),
            'p_theory': cdf_fn(sorted_data).tolist()
        }

    def design_flood_hydrograph(self, typical_hydrograph: np.ndarray,
                                design_peak: float,
                                method: str = 'same_frequency') -> np.ndarray:
        """
        设计洪水过程线

        参数:
            typical_hydrograph: 典型洪水过程线
            design_peak: 设计洪峰流量
            method: 放大方法 ('same_frequency' 同频率, 'typical' 典型放大)

        返回:
            设计洪水过程线
        """
        typical = np.asarray(typical_hydrograph, dtype=float)
        typical_peak = np.max(typical)

        if method == 'typical' or typical_peak <= 0:
            scale = design_peak / typical_peak if typical_peak > 0 else 1.0
            return typical * scale

        typical_volume = np.trapz(typical, dx=1)
        typical_base = np.min(typical) * len(typical)
        typical_runoff = typical_volume - typical_base

        design_ratio_peak = design_peak / typical_peak if typical_peak > 0 else 1.0

        result = np.zeros_like(typical)
        for i in range(len(typical)):
            if typical[i] > typical_peak * 0.5:
                result[i] = typical[i] * design_ratio_peak
            else:
                result[i] = typical[i] * (0.5 + 0.5 * design_ratio_peak)

        return result

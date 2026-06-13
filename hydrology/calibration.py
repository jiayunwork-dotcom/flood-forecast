"""
参数率定模块
- NSE目标函数
- SCE-UA (竞争复形进化算法) 全局优化
- 遗传算法 (GA)
- 多场次联合率定
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Callable, Optional
from copy import deepcopy

from .runoff_models import get_runoff_model
from .routing_models import RoutingModel, calculate_metrics


class OptimizationCallback:
    """优化过程回调，记录收敛历史"""

    def __init__(self):
        self.history: List[Dict] = []
        self.best_nse = -np.inf
        self.best_params = None

    def __call__(self, params: np.ndarray, nse: float, iteration: int):
        if nse > self.best_nse:
            self.best_nse = nse
            self.best_params = params.copy()
        self.history.append({
            'iteration': iteration,
            'nse': nse,
            'best_nse': self.best_nse,
            'params': params.copy()
        })


class CalibrationObjective:
    """率定目标函数计算"""

    def __init__(self, event_data_list: List[pd.DataFrame],
                 runoff_model_type: str, routing_method: str,
                 param_names: List[str], param_bounds: List[Tuple[float, float]],
                 dt_hours: float, area_km2: float):
        self.event_data_list = event_data_list
        self.runoff_model_type = runoff_model_type
        self.routing_method = routing_method
        self.param_names = param_names
        self.param_bounds = param_bounds
        self.dt_hours = dt_hours
        self.area_km2 = area_km2

    def evaluate(self, params_array: np.ndarray) -> float:
        """计算目标函数值 (返回NSE，最大化)"""
        params = dict(zip(self.param_names, params_array))

        all_nse = []
        for event_df in self.event_data_list:
            try:
                nse = self._single_event_nse(event_df, params)
                if not np.isnan(nse) and np.isfinite(nse):
                    all_nse.append(nse)
            except Exception:
                continue

        if not all_nse:
            return -999.0

        return float(np.mean(all_nse))

    def _single_event_nse(self, event_df: pd.DataFrame, params: Dict) -> float:
        if 'runoff' not in event_df.columns or event_df['runoff'].isna().all():
            return np.nan

        rainfall = event_df['rainfall'].fillna(0).values
        evaporation = event_df['evaporation'].fillna(0).values if 'evaporation' in event_df.columns else None
        Q_obs = event_df['runoff'].values

        runoff_model = get_runoff_model(self.runoff_model_type, self.dt_hours, self.area_km2)
        runoff_result = runoff_model.run(rainfall, evaporation, **params)

        routing_model = RoutingModel(self.dt_hours, self.area_km2)
        routing_result = routing_model.run(
            runoff_result['runoff_surface'],
            runoff_result['runoff_underground'],
            self.routing_method,
            **params
        )

        metrics = calculate_metrics(Q_obs, routing_result['Q_total'])
        return metrics['NSE']


class SCEUAOptimizer:
    """
    SCE-UA 竞争复形进化全局优化算法
    参考: Duan et al. (1992)
    """

    def __init__(self, objective: Callable,
                 param_bounds: List[Tuple[float, float]],
                 n_complexes: int = 2,
                 population_size: int = 0,
                 max_generations: int = 1000,
                 callback: Optional[OptimizationCallback] = None,
                 seed: int = 42):
        self.objective = objective
        self.param_bounds = np.array(param_bounds, dtype=float)
        self.n_params = len(param_bounds)
        self.n_complexes = max(1, n_complexes)
        self.n_points_per_complex = max(2 * self.n_params + 1, 5)
        self.pop_size = max(population_size, self.n_complexes * self.n_points_per_complex)
        self.max_generations = max_generations
        self.callback = callback
        self.rng = np.random.RandomState(seed)
        self.converged = False
        self.convergence_gen = 0

    def optimize(self) -> Tuple[np.ndarray, float]:
        lb = self.param_bounds[:, 0]
        ub = self.param_bounds[:, 1]

        population = np.zeros((self.pop_size, self.n_params))
        fitness = np.zeros(self.pop_size)

        for i in range(self.pop_size):
            population[i] = lb + self.rng.random(self.n_params) * (ub - lb)
            fitness[i] = self.objective(population[i])
            if self.callback:
                self.callback(population[i], fitness[i], 0)

        best_idx = np.argmax(fitness)
        best_x = population[best_idx].copy()
        best_f = fitness[best_idx]

        no_improve_count = 0

        for gen in range(1, self.max_generations + 1):
            order = np.argsort(-fitness)
            population = population[order]
            fitness = fitness[order]

            for c in range(self.n_complexes):
                start = c * self.n_points_per_complex
                end = start + self.n_points_per_complex
                complex_pts = population[start:end].copy()
                complex_fit = fitness[start:end].copy()

                new_pt, new_fit = self._evolve_complex(complex_pts, complex_fit, lb, ub)

                worst_idx = start + self.n_points_per_complex - 1
                if new_fit > fitness[worst_idx]:
                    population[worst_idx] = new_pt
                    fitness[worst_idx] = new_fit

            curr_best_idx = np.argmax(fitness)
            curr_best_f = fitness[curr_best_idx]

            if curr_best_f > best_f:
                best_f = curr_best_f
                best_x = population[curr_best_idx].copy()
                no_improve_count = 0
            else:
                if curr_best_f - best_f < 0.001:
                    no_improve_count += 1
                else:
                    no_improve_count = 0

            if self.callback:
                self.callback(best_x, best_f, gen)

            if no_improve_count >= 50:
                self.converged = True
                self.convergence_gen = gen
                break

        return best_x, best_f

    def _evolve_complex(self, complex_pts: np.ndarray, complex_fit: np.ndarray,
                        lb: np.ndarray, ub: np.ndarray) -> Tuple[np.ndarray, float]:
        n = len(complex_pts)
        order = np.argsort(-complex_fit)

        parents_idx = order[:self.n_params + 1]
        parents = complex_pts[parents_idx]
        parents_fit = complex_fit[parents_idx]

        centroid = np.mean(parents[:-1], axis=0)

        worst_idx = parents_idx[-1]
        worst_pt = parents[-1]

        reflection = 2.0 * centroid - worst_pt
        reflection = np.clip(reflection, lb, ub)
        reflection_fit = self.objective(reflection)

        if reflection_fit > complex_fit[worst_idx]:
            expansion = centroid + 2.0 * (reflection - centroid)
            expansion = np.clip(expansion, lb, ub)
            expansion_fit = self.objective(expansion)
            if expansion_fit > reflection_fit:
                return expansion, expansion_fit
            else:
                return reflection, reflection_fit
        else:
            contraction = centroid + 0.5 * (worst_pt - centroid)
            contraction_fit = self.objective(contraction)
            if contraction_fit > complex_fit[worst_idx]:
                return contraction, contraction_fit

        mutation = lb + self.rng.random(self.n_params) * (ub - lb)
        mutation_fit = self.objective(mutation)
        return mutation, mutation_fit


class GeneticAlgorithmOptimizer:
    """遗传算法优化器"""

    def __init__(self, objective: Callable,
                 param_bounds: List[Tuple[float, float]],
                 pop_size: int = 100,
                 crossover_rate: float = 0.8,
                 mutation_rate: float = 0.1,
                 max_generations: int = 500,
                 callback: Optional[OptimizationCallback] = None,
                 seed: int = 42):
        self.objective = objective
        self.param_bounds = np.array(param_bounds, dtype=float)
        self.n_params = len(param_bounds)
        self.pop_size = pop_size
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate
        self.max_generations = max_generations
        self.callback = callback
        self.rng = np.random.RandomState(seed)
        self.converged = False
        self.convergence_gen = 0

    def optimize(self) -> Tuple[np.ndarray, float]:
        lb = self.param_bounds[:, 0]
        ub = self.param_bounds[:, 1]

        population = lb + self.rng.random((self.pop_size, self.n_params)) * (ub - lb)
        fitness = np.array([self.objective(p) for p in population])

        best_idx = np.argmax(fitness)
        best_x = population[best_idx].copy()
        best_f = fitness[best_idx]

        no_improve_count = 0

        for gen in range(1, self.max_generations + 1):
            new_population = np.zeros_like(population)
            new_fitness = np.zeros(self.pop_size)

            new_population[0] = best_x.copy()
            new_fitness[0] = best_f

            for i in range(1, self.pop_size, 2):
                p1 = self._tournament_select(population, fitness)
                p2 = self._tournament_select(population, fitness)

                if self.rng.random() < self.crossover_rate:
                    c1, c2 = self._crossover(p1, p2)
                else:
                    c1, c2 = p1.copy(), p2.copy()

                c1 = self._mutate(c1, lb, ub)
                c2 = self._mutate(c2, lb, ub)

                new_population[i] = c1
                new_fitness[i] = self.objective(c1)
                if i + 1 < self.pop_size:
                    new_population[i + 1] = c2
                    new_fitness[i + 1] = self.objective(c2)

            population = new_population
            fitness = new_fitness

            curr_best_idx = np.argmax(fitness)
            curr_best_f = fitness[curr_best_idx]

            if curr_best_f > best_f:
                best_f = curr_best_f
                best_x = population[curr_best_idx].copy()
                no_improve_count = 0
            else:
                if curr_best_f - best_f < 0.001:
                    no_improve_count += 1
                else:
                    no_improve_count = 0

            if self.callback:
                self.callback(best_x, best_f, gen)

            if no_improve_count >= 100:
                self.converged = True
                self.convergence_gen = gen
                break

        return best_x, best_f

    def _tournament_select(self, population: np.ndarray, fitness: np.ndarray,
                           k: int = 3) -> np.ndarray:
        idx = self.rng.choice(len(population), size=k, replace=False)
        best_local = np.argmax(fitness[idx])
        return population[idx[best_local]].copy()

    def _crossover(self, p1: np.ndarray, p2: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        alpha = self.rng.random(self.n_params)
        c1 = alpha * p1 + (1 - alpha) * p2
        c2 = (1 - alpha) * p1 + alpha * p2
        return c1, c2

    def _mutate(self, x: np.ndarray, lb: np.ndarray, ub: np.ndarray) -> np.ndarray:
        for i in range(self.n_params):
            if self.rng.random() < self.mutation_rate:
                sigma = 0.1 * (ub[i] - lb[i])
                x[i] += self.rng.normal(0, sigma)
                x[i] = np.clip(x[i], lb[i], ub[i])
        return x


class ModelCalibrator:
    """模型参数率定主类"""

    def __init__(self, dt_hours: float = 1.0, area_km2: float = 1.0):
        self.dt_hours = dt_hours
        self.area_km2 = area_km2
        self.callback = OptimizationCallback()
        self.result: Optional[Dict] = None

    @staticmethod
    def get_default_param_config(runoff_type: str, routing_method: str) -> Dict:
        """获取默认参数配置和范围"""
        sat_params = {
            'WM': (100.0, 200.0, 150.0),
            'B': (0.1, 0.4, 0.3),
            'K': (0.5, 2.0, 1.0),
            'C': (0.05, 0.3, 0.15)
        }
        ga_params = {
            'Ks': (0.5, 15.0, 5.0),
            'Sf': (10.0, 200.0, 50.0),
            'theta_i': (0.10, 0.35, 0.20),
            'theta_s': (0.35, 0.55, 0.45)
        }
        routing_params = {
            'n': (1.0, 5.0, 2.0),
            'K': (1.0, 48.0, 6.0),
            'Kg': (12.0, 120.0, 48.0)
        }

        if runoff_type in ('蓄满产流', 'SaturationExcess'):
            runoff_params = sat_params
        elif runoff_type in ('超渗产流', 'GreenAmpt'):
            runoff_params = ga_params
        else:
            runoff_params = {**sat_params, **ga_params,
                             'sat_ratio': (0.1, 0.9, 0.3)}

        all_params = {**runoff_params, **routing_params}
        param_names = list(all_params.keys())
        param_bounds = [(v[0], v[1]) for v in all_params.values()]
        param_defaults = {k: v[2] for k, v in all_params.items()}

        return {
            'names': param_names,
            'bounds': param_bounds,
            'defaults': param_defaults
        }

    def calibrate(self, event_data_list: List[pd.DataFrame],
                  runoff_model_type: str = '蓄满产流',
                  routing_method: str = 'Nash',
                  param_names: Optional[List[str]] = None,
                  param_bounds: Optional[List[Tuple[float, float]]] = None,
                  algorithm: str = 'SCE-UA',
                  max_generations: int = 500,
                  n_complexes: int = 2,
                  pop_size: int = 0,
                  **algo_kwargs) -> Dict:
        """
        执行参数率定

        参数:
            event_data_list: 场次洪水数据列表
            runoff_model_type: 产流模型类型
            routing_method: 汇流方法
            param_names: 待率定参数名列表
            param_bounds: 参数上下界列表
            algorithm: 优化算法 ('SCE-UA' 或 'GA')
            max_generations: 最大进化代数
            n_complexes: SCE-UA复形数
            pop_size: 种群大小
        """
        if param_names is None or param_bounds is None:
            config = self.get_default_param_config(runoff_model_type, routing_method)
            param_names = config['names']
            param_bounds = config['bounds']

        objective_func = CalibrationObjective(
            event_data_list, runoff_model_type, routing_method,
            param_names, param_bounds, self.dt_hours, self.area_km2
        )

        self.callback = OptimizationCallback()

        if algorithm.upper() in ('SCE-UA', 'SCEUA', 'SCE'):
            optimizer = SCEUAOptimizer(
                objective_func.evaluate,
                param_bounds,
                n_complexes=n_complexes,
                population_size=pop_size,
                max_generations=max_generations,
                callback=self.callback
            )
        else:
            optimizer = GeneticAlgorithmOptimizer(
                objective_func.evaluate,
                param_bounds,
                pop_size=max(pop_size, 100),
                max_generations=max_generations,
                callback=self.callback,
                **algo_kwargs
            )

        best_params_array, best_nse = optimizer.optimize()
        best_params = dict(zip(param_names, best_params_array))

        event_results = []
        for i, event_df in enumerate(event_data_list):
            result = self._run_single_event(event_df, best_params, runoff_model_type, routing_method)
            event_results.append(result)

        self.result = {
            'best_params': best_params,
            'best_NSE': best_nse,
            'param_names': param_names,
            'param_bounds': param_bounds,
            'convergence_history': self.callback.history,
            'converged': optimizer.converged,
            'convergence_generation': getattr(optimizer, 'convergence_gen', max_generations),
            'event_results': event_results,
            'algorithm': algorithm,
            'runoff_model': runoff_model_type,
            'routing_method': routing_method
        }

        return self.result

    def _run_single_event(self, event_df: pd.DataFrame, params: Dict,
                          runoff_type: str, routing_method: str) -> Dict:
        rainfall = event_df['rainfall'].fillna(0).values
        evaporation = event_df['evaporation'].fillna(0).values if 'evaporation' in event_df.columns else None
        Q_obs = event_df['runoff'].values if 'runoff' in event_df.columns else None

        runoff_model = get_runoff_model(runoff_type, self.dt_hours, self.area_km2)
        runoff_result = runoff_model.run(rainfall, evaporation, **params)

        routing_model = RoutingModel(self.dt_hours, self.area_km2)
        routing_result = routing_model.run(
            runoff_result['runoff_surface'],
            runoff_result['runoff_underground'],
            routing_method,
            **params
        )

        Q_cal = routing_result['Q_total']
        metrics = {}
        if Q_obs is not None and not np.isnan(Q_obs).all():
            metrics = calculate_metrics(Q_obs, Q_cal)

        return {
            'Q_obs': Q_obs,
            'Q_cal': Q_cal,
            'Q_surface': routing_result['Q_surface'],
            'Q_underground': routing_result['Q_underground'],
            'runoff_total': runoff_result['runoff_total'],
            'metrics': metrics,
            'dates': event_df['date'].tolist() if 'date' in event_df.columns else None
        }

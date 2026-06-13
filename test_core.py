import numpy as np
import pandas as pd
from hydrology.data_manager import DataManager
from hydrology.runoff_models import get_runoff_model
from hydrology.routing_models import RoutingModel, calculate_metrics, UnitHydrograph, MuskingumModel
from hydrology.calibration import ModelCalibrator, SCEUAOptimizer
from hydrology.forecast import Forecaster
from hydrology.frequency_analysis import FrequencyAnalysis
from hydrology.multi_event import MultiEventEvaluator

print("=" * 60)
print("水文模型核心功能测试")
print("=" * 60)

print("\n1. 数据管理模块测试")
dm = DataManager()
dm.set_basin_params(500.0, 50.0, 0.002, '壤土')
print(f"   ✓ 流域参数设置")
soil = dm.get_soil_properties()
print(f"   ✓ 土壤参数获取")

dates = pd.date_range('2020-06-01', periods=30, freq='D')
rainfall = np.array([0,0,0,12.5,28.3,45.6,18.2,5.5,0.8,0,0,0,0,0,0,0,8.5,35.2,52.8,22.5,3.8,0,0,0,0,0,0,0,0,0])
evap = np.full(30, 2.5)
runoff = np.array([5.2,4.8,4.5,5.0,8.5,25.3,52.8,78.5,65.2,42.1,28.5,18.2,12.5,9.0,7.2,6.0,6.8,15.6,45.2,98.5,125.6,95.8,65.2,42.5,28.8,20.5,15.2,11.8,9.5,8.0])

df = pd.DataFrame({'date': dates, 'rainfall': rainfall, 'evaporation': evap, 'runoff': runoff})
dm.raw_data = df
dm.data = df
dm.time_step = 'day'
dm.time_delta = pd.Timedelta(days=1)
events = dm.split_flood_events(rain_threshold=3.0, min_duration_hours=12)
print(f"   ✓ 场次洪水分割: {len(events)} 场")

print("\n2. 产流模型测试")
dt_hours = 24.0
area = 500.0

sat_model = get_runoff_model('蓄满产流', dt_hours, area)
rain_test = np.array([0, 10, 30, 50, 20, 5, 0, 0])
evap_test = np.array([2.5, 2.5, 2.0, 1.5, 1.8, 2.0, 2.5, 2.5])
sat_result = sat_model.run(rain_test, evap_test)
print(f"   ✓ 蓄满产流: 总产流={np.sum(sat_result['runoff_total']):.2f}mm")

ga_model = get_runoff_model('超渗产流', dt_hours, area)
ga_result = ga_model.run(rain_test, evap_test)
print(f"   ✓ 超渗产流: 总产流={np.sum(ga_result['runoff_total']):.2f}mm")

mix_model = get_runoff_model('混合产流', dt_hours, area)
mix_result = mix_model.run(rain_test, evap_test)
print(f"   ✓ 混合产流: 总产流={np.sum(mix_result['runoff_total']):.2f}mm")

print("\n3. 汇流模型测试")
uh = UnitHydrograph.nash_uh(n=2.0, K=6.0, dt=24.0, n_points=20)
print(f"   ✓ Nash单位线生成")

n_est, K_est = UnitHydrograph.estimate_nk_from_moments(uh, 24.0)
print(f"   ✓ 矩法反推参数: n={n_est:.2f}, K={K_est:.2f}h")

stable, n_sub = MuskingumModel.check_stability(K=6.0, X=0.2, dt=24.0)
print(f"   ✓ Muskingum稳定性: 稳定={stable}")

routing = RoutingModel(dt_hours, area)
routing_result = routing.run(
    sat_result['runoff_surface'], sat_result['runoff_underground'],
    method='Nash', n=2.0, K=6.0, Kg=48.0, baseflow=5.0
)
print(f"   ✓ 汇流计算: 洪峰={np.max(routing_result['Q_total']):.2f}m³/s")

Q_obs = np.array([5, 8, 25, 60, 85, 70, 45, 30])
metrics = calculate_metrics(Q_obs, routing_result['Q_total'][:8])
print(f"   ✓ 评价指标: NSE={metrics['NSE']:.4f}")

print("\n4. 参数率定测试")
def simple_obj(x):
    return -(x[0] - 2.0)**2 - (x[1] - 5.0)**2

class Cb:
    def __init__(self):
        self.best_nse = -np.inf
    def __call__(self, p, n, i):
        if n > self.best_nse:
            self.best_nse = n

opt = SCEUAOptimizer(simple_obj, [(0, 10), (0, 10)], n_complexes=1, max_generations=50, callback=Cb())
best_x, best_f = opt.optimize()
print(f"   ✓ SCE-UA优化完成")

print("\n5. 洪水预报测试")
forecaster = Forecaster(dt_hours, area)
forecast_rain = np.array([5, 15, 35, 50, 28, 12, 5, 2, 0, 0, 0, 0, 0, 0, 0])
forecast_result = forecaster.forecast(
    forecast_rain,
    initial_conditions={'WU0': 10, 'WL0': 50, 'WD0': 20},
    model_params={'WM': 150, 'B': 0.3, 'K': 1.0, 'C': 0.15, 'WUM': 20, 'WLM': 60, 'n': 2.0, 'K': 6.0, 'Kg': 48.0, 'baseflow': 5.0},
    runoff_model_type='蓄满产流',
    routing_method='Nash'
)
print(f"   ✓ 预报计算: 洪峰={forecast_result['peak_flow']:.2f}m³/s")

observed = np.array([6.0, 10.0, 25.0, np.nan, np.nan])
correction = forecaster.realtime_correction(forecast_result['Q_forecast'], observed, 2)
print(f"   ✓ 实时校正完成")

warning = forecaster.compare_with_warning_level(forecast_result['Q_forecast'], 50.0)
print(f"   ✓ 警戒对比完成")

print("\n6. 频率分析测试")
peaks = [125.6, 98.5, 78.2, 156.3, 112.5, 89.6, 145.2, 68.9, 132.8, 178.5,
         95.6, 122.3, 85.9, 165.4, 108.7, 72.1, 138.9, 152.6, 99.3, 118.4,
         142.7, 82.5, 168.2, 105.6, 76.8]

fa = FrequencyAnalysis()
fa.load_annual_maxima(peaks)
result = fa.fit_distribution('P-III', 'moments')
print(f"   ✓ P-III分布拟合完成")

design = fa.get_design_values('P-III', [10, 50, 100])
print(f"   ✓ 设计值: 100年一遇={design[100]:.1f} m³/s")

ks = fa.ks_test('P-III')
print(f"   ✓ K-S检验: 通过={ks['pass']}")

print("\n7. 多场次评估测试")
evaluator = MultiEventEvaluator(dt_hours, area)
event_dfs = [dm.get_event_data(ev['id']) for ev in dm.flood_events]
if event_dfs:
    config = ModelCalibrator.get_default_param_config('蓄满产流', 'Nash')
    summary = evaluator.run_batch(event_dfs, config['defaults'], '蓄满产流', 'Nash')
    print(f"   ✓ 批量评估: {summary['n_events']}场")

print("\n" + "=" * 60)
print("所有核心功能测试通过!")
print("=" * 60)

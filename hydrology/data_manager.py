"""
数据管理模块
- CSV水文气象数据导入与校验
- 流域基本参数管理
- 场次洪水分割与管理
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple


class DataManager:
    """水文数据管理类"""

    REQUIRED_COLUMNS = ['date', 'rainfall', 'evaporation']
    OPTIONAL_COLUMNS = ['runoff', 'temperature']

    SOIL_TYPES = {
        '砂土': {'Ks': 10.0, 'porosity': 0.40, 'field_capacity': 0.10},
        '壤土': {'Ks': 2.0, 'porosity': 0.45, 'field_capacity': 0.25},
        '粘土': {'Ks': 0.2, 'porosity': 0.50, 'field_capacity': 0.40}
    }

    def __init__(self):
        self.raw_data: Optional[pd.DataFrame] = None
        self.data: Optional[pd.DataFrame] = None
        self.time_step: str = 'unknown'
        self.time_delta: Optional[timedelta] = None
        self.basin_params: Dict = {
            'area': 0.0,
            'river_length': 0.0,
            'slope': 0.0,
            'soil_type': '壤土'
        }
        self.flood_events: List[Dict] = []

    def import_csv(self, file_path: str) -> Dict:
        """
        导入CSV格式水文气象数据

        参数:
            file_path: CSV文件路径

        返回:
            导入结果信息字典
        """
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            return {'success': False, 'message': f'读取文件失败: {str(e)}'}

        df.columns = [c.strip().lower() for c in df.columns]

        col_mapping = {
            '日期': 'date', '时间': 'date', 'datetime': 'date',
            '降雨量': 'rainfall', '降水': 'rainfall', 'precipitation': 'rainfall', 'p': 'rainfall',
            '蒸发量': 'evaporation', '蒸发': 'evaporation', 'eva': 'evaporation', 'e': 'evaporation',
            '实测径流': 'runoff', '流量': 'runoff', 'runoff': 'runoff', 'q': 'runoff',
            '气温': 'temperature', '温度': 'temperature', 'temp': 'temperature', 't': 'temperature'
        }
        df = df.rename(columns=col_mapping)

        missing_required = [c for c in self.REQUIRED_COLUMNS if c not in df.columns]
        if missing_required:
            return {'success': False,
                    'message': f'缺少必需列: {missing_required}。必需列: 日期/降雨量(mm)/蒸发量(mm)'}

        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        if df['date'].isna().any():
            return {'success': False, 'message': '日期列存在无法解析的时间格式'}

        df = df.sort_values('date').reset_index(drop=True)

        for col in ['rainfall', 'evaporation', 'runoff', 'temperature']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        self.raw_data = df.copy()
        self.data = df.copy()

        self._detect_time_step()
        self._check_continuity()

        info = {
            'success': True,
            'message': f'成功导入 {len(df)} 条记录',
            'rows': len(df),
            'time_step': self.time_step,
            'date_range': f"{df['date'].min().strftime('%Y-%m-%d %H:%M')} ~ {df['date'].max().strftime('%Y-%m-%d %H:%M')}",
            'columns': list(df.columns),
            'missing_count': int(df.isna().sum().sum()),
            'has_runoff': 'runoff' in df.columns and not df['runoff'].isna().all()
        }
        return info

    def _detect_time_step(self):
        """自动检测时间步长"""
        if self.data is None or len(self.data) < 2:
            self.time_step = 'unknown'
            self.time_delta = None
            return

        diffs = self.data['date'].diff().dropna()
        median_diff = diffs.median()

        if median_diff <= timedelta(minutes=90):
            self.time_step = 'hour'
        else:
            self.time_step = 'day'
        self.time_delta = median_diff

    def _check_continuity(self):
        """检查数据连续性，填充缺失时间点并标记为NaN"""
        if self.data is None or len(self.data) < 2 or self.time_delta is None:
            return

        full_range = pd.date_range(
            start=self.data['date'].min(),
            end=self.data['date'].max(),
            freq=self.time_delta
        )
        self.data = self.data.set_index('date').reindex(full_range).reset_index()
        self.data = self.data.rename(columns={'index': 'date'})

    def set_basin_params(self, area: float, river_length: float, slope: float, soil_type: str):
        """
        设置流域基本参数

        参数:
            area: 流域面积 (km²)
            river_length: 河道长度 (km)
            slope: 平均坡度 (‰或小数)
            soil_type: 土壤类型 (砂土/壤土/粘土)
        """
        if soil_type not in self.SOIL_TYPES:
            raise ValueError(f'土壤类型必须是: {list(self.SOIL_TYPES.keys())}')

        self.basin_params = {
            'area': float(area),
            'river_length': float(river_length),
            'slope': float(slope),
            'soil_type': soil_type
        }

    def get_soil_properties(self) -> Dict:
        """获取土壤水力参数"""
        return self.SOIL_TYPES.get(self.basin_params['soil_type'], self.SOIL_TYPES['壤土']).copy()

    def split_flood_events(self, rain_threshold: float = 5.0,
                           baseflow_threshold: float = 0.0,
                           min_duration_hours: int = 6,
                           gap_hours: int = 24) -> List[Dict]:
        """
        自动分割场次洪水

        参数:
            rain_threshold: 降雨开始阈值 (mm/时段)
            baseflow_threshold: 基流阈值，低于此值认为洪水结束 (m³/s)
            min_duration_hours: 最小洪水历时 (小时)
            gap_hours: 两场洪水最小间隔时间 (小时)

        返回:
            场次洪水列表
        """
        if self.data is None:
            return []

        df = self.data.copy()
        hours_per_step = self.time_delta.total_seconds() / 3600 if self.time_delta else 24
        min_steps = max(1, int(min_duration_hours / hours_per_step))
        gap_steps = max(1, int(gap_hours / hours_per_step))

        rain_mask = df['rainfall'].fillna(0) >= rain_threshold
        in_event = False
        event_start = None
        last_rain_idx = 0

        events = []
        for i in range(len(df)):
            if rain_mask.iloc[i] and not in_event:
                in_event = True
                event_start = i
            if rain_mask.iloc[i]:
                last_rain_idx = i
            if in_event:
                if i - last_rain_idx >= gap_steps:
                    if 'runoff' in df.columns:
                        runoff_vals = df['runoff'].iloc[i:min(i + gap_steps, len(df))].fillna(0)
                        if (runoff_vals <= baseflow_threshold).all() or i == len(df) - 1:
                            if i - event_start >= min_steps:
                                events.append((event_start, min(i, len(df) - 1)))
                            in_event = False
                    else:
                        if i - event_start >= min_steps:
                            events.append((event_start, min(i, len(df) - 1)))
                        in_event = False

        if in_event and len(df) - 1 - event_start >= min_steps:
            events.append((event_start, len(df) - 1))

        self.flood_events = []
        for idx, (s, e) in enumerate(events):
            event_df = df.iloc[s:e + 1].copy()
            total_rain = float(event_df['rainfall'].fillna(0).sum())
            if 'runoff' in event_df.columns and not event_df['runoff'].isna().all():
                peak_flow = float(event_df['runoff'].max())
                peak_idx = event_df['runoff'].idxmax()
                peak_time = event_df.loc[peak_idx, 'date']
                hours = (event_df['date'].iloc[-1] - event_df['date'].iloc[0]).total_seconds() / 3600
            else:
                peak_flow = np.nan
                peak_time = None
                hours = (event_df['date'].iloc[-1] - event_df['date'].iloc[0]).total_seconds() / 3600

            pa = self._calculate_Pa(event_df, df, s)

            event_info = {
                'id': idx + 1,
                'name': f'洪水{idx + 1}',
                'start_time': event_df['date'].iloc[0],
                'end_time': event_df['date'].iloc[-1],
                'Pa': round(pa, 2),
                'total_rainfall': round(total_rain, 2),
                'peak_flow': round(peak_flow, 2) if not np.isnan(peak_flow) else None,
                'peak_time': peak_time,
                'duration_hours': round(hours, 1),
                'start_idx': s,
                'end_idx': e,
                'data': event_df
            }
            self.flood_events.append(event_info)

        return self.flood_events

    def _calculate_Pa(self, event_df: pd.DataFrame, full_df: pd.DataFrame, start_idx: int,
                      K: float = 0.85, Pa_max: float = 100.0) -> float:
        """计算前期影响雨量Pa"""
        days_before = min(15, start_idx)
        if days_before <= 0:
            return 0.0

        prev_rain = full_df['rainfall'].iloc[start_idx - days_before:start_idx].fillna(0).values
        Pa = 0.0
        for i, p in enumerate(reversed(prev_rain)):
            Pa = (Pa + p) * K
        return min(Pa, Pa_max)

    def get_event_data(self, event_id: int) -> Optional[pd.DataFrame]:
        """获取指定场次洪水数据"""
        for ev in self.flood_events:
            if ev['id'] == event_id:
                return ev['data'].copy()
        return None

    def get_data_overview(self) -> Dict:
        """获取数据概览信息用于绘图"""
        if self.data is None:
            return {}

        df = self.data.copy()
        df['cum_rainfall'] = df['rainfall'].fillna(0).cumsum()

        return {
            'dates': df['date'].dt.strftime('%Y-%m-%d %H:%M').tolist(),
            'rainfall': df['rainfall'].fillna(0).tolist(),
            'cum_rainfall': df['cum_rainfall'].tolist(),
            'runoff': df['runoff'].tolist() if 'runoff' in df.columns else [],
            'evaporation': df['evaporation'].fillna(0).tolist(),
            'has_runoff': 'runoff' in df.columns and not df['runoff'].isna().all()
        }

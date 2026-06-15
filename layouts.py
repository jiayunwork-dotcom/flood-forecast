"""
页面布局模块
"""

from app_base import *


def generate_data_summary(info=None):
    if data_mgr.data is None:
        return "暂无数据，请导入CSV或加载示例数据"

    df = data_mgr.data
    summary = [
        html.Strong("数据基本信息:"), html.Br(),
        f"时间步长: {data_mgr.time_step}", html.Br(),
        f"记录条数: {len(df)}", html.Br(),
    ]
    if not df.empty:
        summary += [
            f"时间范围: {df['date'].min().strftime('%Y-%m-%d')} ~ {df['date'].max().strftime('%Y-%m-%d')}",
            html.Br(),
            f"总降雨量: {df['rainfall'].sum():.1f} mm", html.Br(),
        ]
        if 'runoff' in df.columns and not df['runoff'].isna().all():
            summary += [
                f"最大流量: {df['runoff'].max():.1f} m³/s", html.Br(),
                f"场次洪水数: {len(data_mgr.flood_events)}",
            ]

    basin = data_mgr.basin_params
    if basin['area'] > 0:
        summary += [
            html.Hr(),
            html.Strong("流域参数:"), html.Br(),
            f"流域面积: {basin['area']} km²", html.Br(),
            f"河道长度: {basin['river_length']} km", html.Br(),
            f"平均坡度: {basin['slope']}", html.Br(),
            f"土壤类型: {basin['soil_type']}",
        ]

    return html.Div(summary)


def layout_data_tab():
    return dbc.Card([
        dbc.CardHeader(html.H4("一、流域数据管理", className="mb-0")),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("1. 导入水文气象数据 (CSV)", className="fw-bold"),
                    dcc.Upload(
                        id='upload-csv',
                        children=html.Div(['拖拽CSV文件到此处或 ', html.A('点击选择文件')]),
                        style={
                            'width': '100%', 'height': '60px', 'lineHeight': '60px',
                            'borderWidth': '1px', 'borderStyle': 'dashed',
                            'borderRadius': '5px', 'textAlign': 'center',
                            'margin': '10px 0', 'backgroundColor': '#f8f9fa'
                        }
                    ),
                    dbc.Button("加载示例数据", id="btn-load-sample",
                               color="secondary", size="sm", className="me-2"),
                    html.Span(id='upload-status', className="text-success ms-2"),
                ], md=6),
                dbc.Col([
                    html.Label("2. 流域基本参数", className="fw-bold"),
                    dbc.Row([
                        dbc.Col([
                            html.Label("流域面积 (km²)"),
                            dbc.Input(id='basin-area', type='number', value=500.0, step=10),
                        ]),
                        dbc.Col([
                            html.Label("河道长度 (km)"),
                            dbc.Input(id='river-length', type='number', value=50.0, step=1),
                        ]),
                    ], className="mb-2"),
                    dbc.Row([
                        dbc.Col([
                            html.Label("平均坡度"),
                            dbc.Input(id='basin-slope', type='number', value=0.002, step=0.001),
                        ]),
                        dbc.Col([
                            html.Label("土壤类型"),
                            dcc.Dropdown(
                                id='soil-type',
                                options=[{'label': s, 'value': s} for s in ['砂土', '壤土', '粘土']],
                                value='壤土'
                            ),
                        ]),
                    ]),
                    dbc.Button("保存流域参数", id="btn-save-basin",
                               color="primary", size="sm", className="mt-2"),
                    html.Span(id='basin-status', className="text-success ms-2"),
                ], md=6),
            ]),
            html.Hr(),
            dbc.Row([
                dbc.Col([
                    html.Label("3. 场次洪水分割参数", className="fw-bold"),
                    dbc.Row([
                        dbc.Col([
                            html.Label("降雨阈值 (mm/时段)"),
                            dbc.Input(id='rain-threshold', type='number', value=3.0, step=0.5),
                        ]),
                        dbc.Col([
                            html.Label("最小历时 (小时)"),
                            dbc.Input(id='min-duration', type='number', value=12, step=1),
                        ]),
                        dbc.Col([
                            html.Label("间隔小时数"),
                            dbc.Input(id='gap-hours', type='number', value=24, step=1),
                        ]),
                        dbc.Col([
                            html.Label("基流阈值 (m³/s)"),
                            dbc.Input(id='baseflow-threshold', type='number', value=0.0, step=0.5),
                        ]),
                    ], className="mb-2"),
                    dbc.Button("自动分割洪水场次", id="btn-split-events", color="info", size="sm"),
                ], md=12),
            ]),
            html.Hr(),
            dbc.Row([
                dbc.Col([
                    html.Label("4. 场次洪水列表", className="fw-bold"),
                    dcc.Dropdown(id='event-selector', placeholder="选择场次洪水..."),
                    html.Div(id='event-info', className="mt-2", style={'fontSize': '14px'}),
                ], md=6),
                dbc.Col([
                    html.Label("数据概览统计", className="fw-bold"),
                    html.Div(id='data-summary', className="small",
                             style={'backgroundColor': '#f8f9fa', 'padding': '10px', 'borderRadius': '5px'}),
                ], md=6),
            ]),
            html.Hr(),
            html.Label("5. 数据可视化", className="fw-bold"),
            dcc.Tabs(id='viz-tabs', value='rainfall', children=[
                dcc.Tab(label='降雨径流过程', value='rainfall'),
                dcc.Tab(label='累积降雨曲线', value='cumulative'),
            ]),
            dcc.Graph(id='overview-plot', figure=create_empty_figure(), style={'height': '450px'}),
        ])
    ], className="mb-4")


def layout_runoff_tab():
    return dbc.Card([
        dbc.CardHeader(html.H4("二、产流模型计算", className="mb-0")),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("产流模型类型", className="fw-bold"),
                    dcc.Dropdown(
                        id='runoff-model-type',
                        options=[
                            {'label': '蓄满产流 (蓄水容量曲线)', 'value': '蓄满产流'},
                            {'label': '超渗产流 (Green-Ampt)', 'value': '超渗产流'},
                            {'label': '混合产流 (蓄满+超渗)', 'value': '混合产流'},
                        ],
                        value='蓄满产流'
                    ),
                ], md=6),
                dbc.Col([
                    html.Label("选择场次洪水", className="fw-bold"),
                    dcc.Dropdown(id='runoff-event-selector', placeholder="选择场次洪水..."),
                ], md=6),
            ], className="mb-3"),
            html.Label("模型参数设置", className="fw-bold"),
            html.Div(id='runoff-params-container', className="mb-3"),
            dbc.Button("运行产流计算", id="btn-run-runoff", color="primary", className="mb-3"),
            html.Hr(),
            html.Label("产流计算结果", className="fw-bold"),
            dcc.Tabs(id='runoff-result-tabs', value='runoff', children=[
                dcc.Tab(label='各时段产流量', value='runoff'),
                dcc.Tab(label='累积产流/产流系数', value='cumulative'),
            ]),
            dcc.Graph(id='runoff-plot', figure=create_empty_figure(), style={'height': '450px'}),
            html.Div(id='runoff-summary', className="mt-2",
                     style={'backgroundColor': '#f8f9fa', 'padding': '10px', 'borderRadius': '5px'}),
            html.Hr(),
            html.Label("参数敏感性分析", className="fw-bold"),
            dbc.Row([
                dbc.Col([
                    html.Label("选择分析参数"),
                    dcc.Dropdown(id='sensitivity-param-select', placeholder="选择要分析的参数..."),
                ], md=4),
                dbc.Col([
                    html.Label("汇流方法"),
                    dcc.Dropdown(id='sensitivity-routing-method',
                                 options=[
                                     {'label': 'Nash瞬时单位线', 'value': 'Nash'},
                                     {'label': 'Muskingum河道演算', 'value': 'Muskingum'},
                                 ], value='Nash'),
                ], md=4),
                dbc.Col([
                    html.Label("采样数量"),
                    dbc.Input(id='sensitivity-n-samples', type='number', value=10, min=5, max=20, step=1),
                ], md=4),
            ], className="mb-3"),
            dbc.Button("运行参数敏感性分析", id="btn-run-sensitivity",
                       color="info", className="mb-3"),
            dcc.Loading(id="sensitivity-loading", type="default", children=[
                html.Label("敏感性分析结果 - 流量过程线叠加图", className="fw-bold"),
                dcc.Graph(id='sensitivity-plot', figure=create_empty_figure(),
                          style={'height': '500px'}),
                html.Label("各参数取值对应的评价指标", className="fw-bold mt-2"),
                html.Div(id='sensitivity-table', className="mb-3"),
            ]),
        ])
    ], className="mb-4")


def layout_routing_tab():
    return dbc.Card([
        dbc.CardHeader(html.H4("三、汇流模型计算", className="mb-0")),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("汇流方法", className="fw-bold"),
                    dcc.Dropdown(
                        id='routing-method',
                        options=[
                            {'label': 'Nash瞬时单位线', 'value': 'Nash'},
                            {'label': 'Muskingum河道演算', 'value': 'Muskingum'},
                            {'label': '手动单位线', 'value': 'ManualUH'},
                        ],
                        value='Nash'
                    ),
                ], md=6),
                dbc.Col([
                    html.Label("选择场次洪水", className="fw-bold"),
                    dcc.Dropdown(id='routing-event-selector', placeholder="选择场次洪水..."),
                ], md=6),
            ], className="mb-3"),
            html.Label("汇流参数设置", className="fw-bold"),
            html.Div(id='routing-params-container', className="mb-3"),
            dbc.Button("运行汇流计算", id="btn-run-routing", color="primary", className="mb-3"),
            html.Hr(),
            html.Label("汇流结果对比", className="fw-bold"),
            dcc.Graph(id='routing-plot', figure=create_empty_figure(), style={'height': '450px'}),
            html.Div(id='routing-metrics', className="mt-2",
                     style={'backgroundColor': '#f8f9fa', 'padding': '10px', 'borderRadius': '5px'}),
        ])
    ], className="mb-4")


def layout_calibration_tab():
    return dbc.Card([
        dbc.CardHeader(html.H4("四、参数自动率定", className="mb-0")),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("产流模型", className="fw-bold"),
                    dcc.Dropdown(id='cal-runoff-model',
                                 options=[{'label': '蓄满产流', 'value': '蓄满产流'},
                                          {'label': '超渗产流', 'value': '超渗产流'},
                                          {'label': '混合产流', 'value': '混合产流'}],
                                 value='蓄满产流'),
                ], md=3),
                dbc.Col([
                    html.Label("汇流方法", className="fw-bold"),
                    dcc.Dropdown(id='cal-routing-method',
                                 options=[{'label': 'Nash单位线', 'value': 'Nash'},
                                          {'label': 'Muskingum', 'value': 'Muskingum'}],
                                 value='Nash'),
                ], md=3),
                dbc.Col([
                    html.Label("优化算法", className="fw-bold"),
                    dcc.Dropdown(id='cal-algorithm',
                                 options=[{'label': 'SCE-UA全局优化', 'value': 'SCE-UA'},
                                          {'label': '遗传算法 GA', 'value': 'GA'}],
                                 value='SCE-UA'),
                ], md=3),
                dbc.Col([
                    html.Label("最大迭代代数", className="fw-bold"),
                    dbc.Input(id='cal-max-gen', type='number', value=300, min=50, step=50),
                ], md=3),
            ], className="mb-3"),
            html.Label("选择参与率定的场次洪水 (可多选，多场次联合率定)", className="fw-bold"),
            dcc.Checklist(id='cal-event-checklist',
                          labelStyle={'display': 'inline-block', 'marginRight': '20px'},
                          className="mb-3"),
            html.Label("率定参数范围设置", className="fw-bold"),
            html.Div(id='cal-params-container', className="mb-3"),
            dbc.Button("开始参数率定", id="btn-run-calibration", color="success", className="mb-3"),
            dcc.Loading(id="cal-loading", type="default", children=[
                html.Hr(),
                html.Label("率定结果", className="fw-bold"),
                dbc.Row([
                    dbc.Col([
                        html.Div(id='cal-summary',
                                 style={'backgroundColor': '#e8f5e9', 'padding': '15px',
                                        'borderRadius': '5px', 'maxHeight': '400px', 'overflowY': 'auto'}),
                    ], md=4),
                    dbc.Col([
                        dcc.Graph(id='cal-convergence-plot',
                                  figure=create_empty_figure("参数收敛曲线"),
                                  style={'height': '300px'}),
                    ], md=8),
                ], className="mb-3"),
                dcc.Graph(id='cal-compare-plot',
                          figure=create_empty_figure("最优模拟与实测对比"),
                          style={'height': '400px'}),
            ]),
            html.Hr(),
            html.Label("参数不确定性分析", className="fw-bold"),
            dbc.Row([
                dbc.Col([
                    html.Label("蒙特卡洛采样次数"),
                    dbc.Input(id='uncertainty-n-samples', type='number',
                              value=200, min=100, max=1000, step=50),
                ], md=4),
                dbc.Col([
                    html.Label("扰动幅度 (%)"),
                    dbc.Input(id='uncertainty-perturbation', type='number',
                              value=10, min=5, max=30, step=1),
                ], md=4),
                dbc.Col([
                    html.Label("置信水平 (%)"),
                    dbc.Input(id='uncertainty-confidence', type='number',
                              value=90, min=80, max=99, step=1),
                ], md=4),
            ], className="mb-3"),
            dbc.Button("运行不确定性分析", id="btn-run-uncertainty",
                       color="warning", className="mb-3"),
            dcc.Loading(id="uncertainty-loading", type="default", children=[
                html.Label("置信带包络图", className="fw-bold"),
                dcc.Graph(id='uncertainty-plot',
                          figure=create_empty_figure(),
                          style={'height': '450px'}),
                html.Label("参数敏感性排名 (按NSE变化幅度)", className="fw-bold mt-2"),
                html.Div(id='uncertainty-sensitivity-rank', className="mb-3"),
            ]),
        ])
    ], className="mb-4")


def layout_forecast_tab():
    return dbc.Card([
        dbc.CardHeader(html.H4("五、洪水预报", className="mb-0")),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("预报降雨数据 (mm，逗号或换行分隔)", className="fw-bold"),
                    dcc.Textarea(id='forecast-rain-input',
                                 value='5, 15, 35, 50, 28, 12, 5, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0',
                                 style={'width': '100%', 'height': '80px'}),
                ], md=6),
                dbc.Col([
                    html.Label("警戒流量 (m³/s)", className="fw-bold"),
                    dbc.Input(id='warning-level', type='number', value=80.0, step=5),
                    html.Label("置信水平 (%)", className="fw-bold mt-2"),
                    dcc.Slider(id='confidence-level', min=80, max=99, value=90,
                               marks={i: f'{i}%' for i in [80, 85, 90, 95, 99]}),
                ], md=3),
                dbc.Col([
                    html.Label("初始土壤蓄水量 (mm)", className="fw-bold"),
                    dbc.Input(id='init-W0', type='number', value=80.0, step=5),
                    html.Label("初始地下径流 (m³/s)", className="fw-bold mt-2"),
                    dbc.Input(id='init-Qg0', type='number', value=5.0, step=0.5),
                ], md=3),
            ], className="mb-3"),
            html.Label("多方案对比 - 选择产流模型 (2-3种，Ctrl/Shift多选)", className="fw-bold"),
            dcc.Checklist(id='forecast-model-types',
                          options=[
                              {'label': '蓄满产流', 'value': '蓄满产流'},
                              {'label': '超渗产流', 'value': '超渗产流'},
                              {'label': '混合产流', 'value': '混合产流'},
                          ],
                          value=['蓄满产流'],
                          labelStyle={'display': 'inline-block', 'marginRight': '30px'},
                          className="mb-3"),
            html.Label("汇流方法", className="fw-bold"),
            dcc.Dropdown(id='forecast-routing-method',
                         options=[
                             {'label': 'Nash瞬时单位线', 'value': 'Nash'},
                             {'label': 'Muskingum河道演算', 'value': 'Muskingum'},
                         ], value='Nash', className="mb-3"),
            html.Label("实时校正设置 (可选 - 输入已观测流量，NaN表示未观测)", className="fw-bold"),
            dcc.Textarea(id='observed-q-input',
                         placeholder='输入实测流量(逗号分隔)，如: 5, 8, 15, NaN, NaN, NaN...',
                         style={'width': '100%', 'height': '50px'}),
            dbc.Row([
                dbc.Col([
                    html.Label("校正系数 (自回归系数)", className="fw-bold"),
                    dbc.Input(id='corr-coeffs', type='text', value='0.5,0.3,0.2'),
                ], md=6),
                dbc.Col([
                    html.Label("衰减因子 (每6小时)", className="fw-bold"),
                    dbc.Input(id='corr-decay', type='number', value=0.8, step=0.05, min=0, max=1),
                ], md=6),
            ], className="mb-3"),
            dbc.Button("运行洪水预报", id="btn-run-forecast", color="warning", className="mb-3"),
            html.Hr(),
            html.Label("预报结果 (多方案对比)", className="fw-bold"),
            dcc.Graph(id='forecast-plot', figure=create_empty_figure(), style={'height': '500px'}),
            html.Label("各方案预报结果对比表", className="fw-bold mt-2"),
            html.Div(id='forecast-compare-table', className="mb-3"),
            html.Div(id='forecast-summary', className="mt-2",
                     style={'backgroundColor': '#fff3e0', 'padding': '15px', 'borderRadius': '5px'}),
        ])
    ], className="mb-4")


def layout_frequency_tab():
    return dbc.Card([
        dbc.CardHeader(html.H4("六、重现期频率分析", className="mb-0")),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("年最大洪峰流量序列 (m³/s，逗号分隔)", className="fw-bold"),
                    dcc.Textarea(id='annual-peaks-input',
                                 value=','.join(map(str, ANNUAL_PEAKS)),
                                 style={'width': '100%', 'height': '80px'}),
                ], md=6),
                dbc.Col([
                    html.Label("分布类型", className="fw-bold"),
                    dcc.Dropdown(id='dist-type',
                                 options=[{'label': '皮尔逊III型 (P-III)', 'value': 'P-III'},
                                          {'label': '对数正态分布', 'value': 'Lognormal'},
                                          {'label': '广义极值 (GEV)', 'value': 'GEV'}],
                                 value='P-III'),
                    html.Label("参数估计方法", className="fw-bold mt-2"),
                    dcc.Dropdown(id='fit-method',
                                 options=[{'label': '矩法', 'value': 'moments'},
                                          {'label': '最大似然法', 'value': 'mle'},
                                          {'label': '线性矩法', 'value': 'lmoments'}],
                                 value='moments'),
                ], md=3),
                dbc.Col([
                    html.Label("设计重现期 (年)", className="fw-bold"),
                    dcc.Dropdown(id='design-return-period',
                                 options=[{'label': f'{T}年一遇', 'value': T}
                                          for T in [2, 5, 10, 20, 50, 100, 200, 500, 1000]],
                                 value=100),
                    dbc.Button("执行频率分析", id="btn-run-frequency",
                               color="primary", className="mt-4"),
                ], md=3),
            ], className="mb-3"),
            html.Hr(),
            dbc.Row([
                dbc.Col([
                    html.Label("频率曲线", className="fw-bold"),
                    dcc.Graph(id='frequency-curve-plot',
                              figure=create_empty_figure(), style={'height': '450px'}),
                ], md=8),
                dbc.Col([
                    html.Label("分析结果", className="fw-bold"),
                    html.Div(id='frequency-results',
                             style={'backgroundColor': '#f8f9fa', 'padding': '15px',
                                    'borderRadius': '5px', 'height': '450px', 'overflowY': 'auto'}),
                ], md=4),
            ]),
            html.Label("适线检验", className="fw-bold mt-3"),
            dcc.Tabs(id='fit-test-tabs', value='ks', children=[
                dcc.Tab(label='K-S检验 / 卡方检验', value='ks'),
                dcc.Tab(label='P-P图 & Q-Q图', value='ppqq'),
            ]),
            dcc.Graph(id='fit-test-plot', figure=create_empty_figure(), style={'height': '400px'}),
        ])
    ], className="mb-4")


def layout_multi_event_tab():
    return dbc.Card([
        dbc.CardHeader(html.H4("七、多场次分析与模型评估", className="mb-0")),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("选择要批量评估的场次", className="fw-bold"),
                    dcc.Checklist(id='multi-event-checklist',
                                  labelStyle={'display': 'inline-block', 'marginRight': '20px'},
                                  className="mb-3"),
                ], md=12),
            ]),
            dbc.Row([
                dbc.Col([
                    html.Label("产流模型对比 (多选)", className="fw-bold"),
                    dcc.Checklist(id='compare-model-types',
                                  options=[{'label': '蓄满产流', 'value': '蓄满产流'},
                                           {'label': '超渗产流', 'value': '超渗产流'},
                                           {'label': '混合产流', 'value': '混合产流'}],
                                  value=['蓄满产流'],
                                  labelStyle={'display': 'inline-block', 'marginRight': '20px'}),
                ], md=6),
                dbc.Col([
                    html.Label("交叉验证", className="fw-bold"), html.Br(),
                    dbc.Button("留一交叉验证 (LOOCV)", id="btn-run-loocv",
                               color="secondary", size="sm"),
                ], md=6),
            ], className="mb-3"),
            dbc.Button("批量评估模型", id="btn-run-multi-eval", color="primary", className="mb-3"),
            dcc.Loading(id="multi-loading", type="default", children=[
                html.Hr(),
                html.Label("各场次评估结果", className="fw-bold"),
                html.Div(id='multi-event-table', className="mb-3"),
                dcc.Tabs(id='multi-viz-tabs', value='scatter', children=[
                    dcc.Tab(label='实测vs模拟洪峰散点图', value='scatter'),
                    dcc.Tab(label='误差分布直方图', value='histogram'),
                    dcc.Tab(label='模型对比', value='compare'),
                    dcc.Tab(label='交叉验证结果', value='cv'),
                ]),
                dcc.Graph(id='multi-viz-plot',
                          figure=create_empty_figure(), style={'height': '450px'}),
            ]),
        ])
    ], className="mb-4")


def layout_report_tab():
    return dbc.Card([
        dbc.CardHeader(html.H4("八、分析报告导出", className="mb-0")),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("报告标题", className="fw-bold"),
                    dbc.Input(id='report-title', type='text', value='水文分析报告'),
                ], md=6),
                dbc.Col([
                    html.Label("选择报告包含内容", className="fw-bold"),
                    dcc.Checklist(id='report-sections',
                                  options=[{'label': '流域概况', 'value': 'basin'},
                                           {'label': '数据概览', 'value': 'data'},
                                           {'label': '模型参数', 'value': 'params'},
                                           {'label': '率定结果', 'value': 'calibration'},
                                           {'label': '预报结果', 'value': 'forecast'},
                                           {'label': '频率分析', 'value': 'frequency'},
                                           {'label': '图表', 'value': 'charts'}],
                                  value=['basin', 'data', 'calibration', 'forecast', 'frequency', 'charts'],
                                  labelStyle={'display': 'inline-block', 'marginRight': '20px'}),
                ], md=6),
            ], className="mb-3"),
            dbc.Button("生成HTML报告并下载", id="btn-generate-html", color="success", className="me-2"),
            html.Hr(),
            html.Label("报告预览", className="fw-bold"),
            html.Div(id='report-preview',
                     style={'backgroundColor': '#ffffff', 'border': '1px solid #ddd',
                            'padding': '30px', 'borderRadius': '5px',
                            'minHeight': '500px', 'overflowY': 'auto'}),
            dcc.Download(id='download-report'),
        ])
    ], className="mb-4")


def layout_monitoring_tab():
    station_table_header = [
        html.Thead(html.Tr([
            html.Th("站点名称", style={'width': '12%'}),
            html.Th("里程桩号(km)", style={'width': '13%'}),
            html.Th("警戒水位(m)", style={'width': '13%'}),
            html.Th("保证水位(m)", style={'width': '13%'}),
            html.Th("当前水位(m)", style={'width': '12%'}),
            html.Th("当前流量(m³/s)", style={'width': '13%'}),
            html.Th("预计洪峰到达", style={'width': '13%'}),
            html.Th("状态", style={'width': '11%'}),
        ]))
    ]

    station_rows = []
    for i in range(5):
        st = monitoring_state['stations'][i]
        station_rows.append(html.Tr([
            html.Td(dbc.Input(id=f'mon-station-name-{i}', type='text',
                              value=st['name'], size='sm', readonly=True)),
            html.Td(dbc.Input(id=f'mon-station-mileage-{i}', type='number',
                              value=st['mileage'], step=1, size='sm', readonly=True)),
            html.Td(dbc.Input(id=f'mon-station-warning-{i}', type='number',
                              value=st['warning_level'], step=0.1, size='sm')),
            html.Td(dbc.Input(id=f'mon-station-guarantee-{i}', type='number',
                              value=st['guarantee_level'], step=0.1, size='sm')),
            html.Td(html.Span(id=f'mon-current-level-{i}', children='--',
                              className='fw-bold', style={'fontSize': '14px'})),
            html.Td(html.Span(id=f'mon-current-flow-{i}', children='--',
                              className='fw-bold', style={'fontSize': '14px'})),
            html.Td(html.Span(id=f'mon-peak-arrival-{i}', children='--',
                              style={'fontSize': '13px', 'color': '#1565c0'})),
            html.Td(html.Div(id=f'mon-status-light-{i}', children=[
                html.Div(style={
                    'width': '18px', 'height': '18px', 'borderRadius': '50%',
                    'backgroundColor': '#4caf50', 'display': 'inline-block',
                    'boxShadow': '0 0 6px #4caf50', 'verticalAlign': 'middle'
                }),
                html.Span('正常', style={'marginLeft': '6px', 'fontSize': '12px'})
            ])),
        ]))

    station_table = dbc.Table(
        station_table_header + [html.Tbody(station_rows)],
        bordered=True, hover=True, responsive=True, size='sm',
        style={'backgroundColor': '#ffffff'}
    )

    basin_schematic = html.Div([
        html.Label("流域示意（上游→下游）", className="fw-bold mb-2 d-block"),
        html.Div([
            html.Div([
                html.Span(st['name'], style={
                    'backgroundColor': STATION_COLORS[i],
                    'color': '#fff', 'padding': '3px 8px', 'borderRadius': '4px',
                    'fontSize': '11px', 'fontWeight': 'bold', 'display': 'inline-block',
                    'minWidth': '50px', 'textAlign': 'center'
                })
            ], style={'display': 'inline-block', 'textAlign': 'center',
                      'width': '18%', 'verticalAlign': 'middle'})
            for i, st in enumerate(monitoring_state['stations'])
        ] + [
            html.Div('→' * 3, style={'display': 'inline-block',
                                     'width': '2.5%', 'color': '#999',
                                     'textAlign': 'center', 'verticalAlign': 'middle'})
            for _ in range(4)
        ], style={'whiteSpace': 'nowrap', 'overflowX': 'auto',
                  'padding': '8px', 'backgroundColor': '#e3f2fd',
                  'borderRadius': '4px', 'marginBottom': '10px'})
    ])

    control_buttons = html.Div([
        dbc.Button("开始模拟", id='btn-mon-start', color='success',
                   size='md', className='me-2'),
        dbc.Button("暂停", id='btn-mon-pause', color='warning',
                   size='md', className='me-2'),
        dbc.Button("重置", id='btn-mon-reset', color='danger',
                   size='md', className='me-2'),
        html.Span(id='mon-sim-status', children='就绪',
                  className='ms-2 fw-bold', style={'fontSize': '14px'}),
        html.Span(id='mon-time-step',
                  children=f" | 时间步: T0",
                  className='ms-2', style={'color': '#666'}),
    ], className='mb-3')

    dismiss_buttons = []
    for i in range(5):
        for j in range(1, 5):
            dismiss_buttons.append(
                html.Div(
                    dbc.Button(f"解除-{i}-{j}",
                               id=f'mon-dismiss-warning-{i}-{j}',
                               size="sm", color="secondary", outline=True),
                    style={'display': 'none'}
                )
            )

    return dbc.Card([
        dbc.CardHeader(html.H4("九、实时监测与预警决策支持", className="mb-0")),
        dbc.CardBody([
            dcc.Interval(id='mon-interval', interval=3000, disabled=True, n_intervals=0),
            dcc.Download(id='mon-download-log'),
            html.Div(dismiss_buttons, style={'display': 'none'}),

            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H6("站点管理与流域示意", className="mb-0 fw-bold"),
                            basin_schematic,
                        ]),
                        dbc.CardBody([
                            station_table,
                            html.Div(id='mon-save-status',
                                     className='mt-2 text-success small'),
                            dbc.Button("保存站点参数", id='btn-mon-save-stations',
                                       color='primary', size='sm', className='mt-2'),
                        ])
                    ], className='mb-4'),

                    dbc.Card([
                        dbc.CardHeader([
                            html.H6("实时数据模拟", className="mb-0 fw-bold"),
                            control_buttons,
                        ]),
                        dbc.CardBody([
                            dcc.Graph(id='mon-water-level-plot',
                                      figure=create_empty_figure("实时水位过程线"),
                                      style={'height': '400px'}),
                        ])
                    ], className='mb-4'),

                    dbc.Card([
                        dbc.CardHeader([
                            html.H6("决策建议", className="mb-0 fw-bold"),
                            dbc.Button("导出预警日志", id='btn-mon-export-log',
                                       color='info', size='sm', className='float-end'),
                        ]),
                        dbc.CardBody([
                            html.Div(id='mon-decision-area', children=[
                                html.Div("暂无决策建议（出现Ⅱ级及以上预警时自动生成）",
                                         style={'color': '#999', 'fontStyle': 'italic',
                                                'padding': '20px', 'textAlign': 'center'})
                            ], style={
                                'maxHeight': '200px', 'overflowY': 'auto',
                                'backgroundColor': '#fafafa', 'borderRadius': '4px',
                                'padding': '10px'
                            }),
                        ])
                    ]),

                ], md=8),

                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H6("预警研判面板", className="mb-0 fw-bold")),
                        dbc.CardBody([
                            html.Div(id='mon-warning-count',
                                     className='mb-2 small text-muted'),
                            html.Div(id='mon-warning-cards', children=[
                                html.Div("暂无预警信息",
                                         style={'color': '#999', 'fontStyle': 'italic',
                                                'padding': '30px', 'textAlign': 'center',
                                                'backgroundColor': '#f5f5f5',
                                                'borderRadius': '4px'})
                            ], style={
                                'maxHeight': '450px', 'overflowY': 'auto'
                            }),
                        ])
                    ], className='mb-4'),

                    dbc.Card([
                        dbc.CardHeader(html.H6("洪水演进偏差表", className="mb-0 fw-bold")),
                        dbc.CardBody([
                            html.Div(id='mon-deviation-table', children=[
                                html.Div("暂无偏差记录（洪峰到达后自动记录）",
                                         style={'color': '#999', 'fontStyle': 'italic',
                                                'padding': '15px', 'textAlign': 'center',
                                                'backgroundColor': '#f5f5f5',
                                                'borderRadius': '4px'})
                            ]),
                        ])
                    ]),

                ], md=4),
            ]),
        ])
    ], className="mb-4")

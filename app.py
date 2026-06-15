"""
水文降雨径流模型与洪水预报 - 交互式分析工具
主应用入口
"""

from app_base import *
from layouts import *
from callbacks import register_callbacks


app.layout = dbc.Container([
    html.H1("水文降雨径流模型与洪水预报分析系统", className="text-center my-4",
            style={'color': '#0d47a1'}),
    html.P("支持流域水文数据管理 / 产流汇流模型计算 / 参数自动率定 / 洪水预报 / 频率分析 的完整工作流程",
           className="text-center text-muted mb-4"),
    dcc.Tabs(id='main-tabs', value='data', children=[
        dcc.Tab(label='1.数据管理', value='data', children=[
            html.Div([layout_data_tab()], className="mt-4")
        ]),
        dcc.Tab(label='2.产流模型', value='runoff', children=[
            html.Div([layout_runoff_tab()], className="mt-4")
        ]),
        dcc.Tab(label='3.汇流模型', value='routing', children=[
            html.Div([layout_routing_tab()], className="mt-4")
        ]),
        dcc.Tab(label='4.参数率定', value='calibration', children=[
            html.Div([layout_calibration_tab()], className="mt-4")
        ]),
        dcc.Tab(label='5.洪水预报', value='forecast', children=[
            html.Div([layout_forecast_tab()], className="mt-4")
        ]),
        dcc.Tab(label='6.频率分析', value='frequency', children=[
            html.Div([layout_frequency_tab()], className="mt-4")
        ]),
        dcc.Tab(label='7.多场次评估', value='multi', children=[
            html.Div([layout_multi_event_tab()], className="mt-4")
        ]),
        dcc.Tab(label='8.报告导出', value='report', children=[
            html.Div([layout_report_tab()], className="mt-4")
        ]),
        dcc.Tab(label='9.实时监测与预警', value='monitoring', children=[
            html.Div([layout_monitoring_tab()], className="mt-4")
        ]),
    ]),
], fluid=True, style={'maxWidth': '1400px'})


register_callbacks(app)


if __name__ == '__main__':
    print("=" * 60)
    print("水文降雨径流模型与洪水预报分析系统")
    print("访问地址: http://127.0.0.1:8050")
    print("=" * 60)
    try:
        app.run(debug=False, host='0.0.0.0', port=8050)
    except AttributeError:
        app.run_server(debug=False, host='0.0.0.0', port=8050)

"""
Dash回调函数模块
"""

from app_base import *
from layouts import *


def get_event_options():
    events = data_mgr.flood_events if data_mgr.flood_events else []
    options = []
    values = []
    for ev in events:
        label = f"{ev['name']} - {ev['start_time'].strftime('%Y-%m-%d')} | 雨量{ev['total_rainfall']:.0f}mm"
        if ev['peak_flow']:
            label += f" | 洪峰{ev['peak_flow']:.0f}m³/s"
        options.append({'label': label, 'value': ev['id']})
        values.append(ev['id'])
    if not options:
        options = [{'label': '暂无场次，请运行洪水分割', 'value': -1}]
        values = []
    return options, values


def register_callbacks(app):
    # ============================================================
    # 数据管理相关回调
    # ============================================================

    @app.callback(
        [Output('upload-status', 'children'),
         Output('data-summary', 'children')],
        [Input('upload-csv', 'contents'),
         Input('upload-csv', 'filename'),
         Input('btn-load-sample', 'n_clicks')]
    )
    def handle_data_upload(contents, filename, btn_sample):
        ctx = callback_context
        if not ctx.triggered:
            return "", generate_data_summary()

        trigger = ctx.triggered[0]['prop_id']

        if trigger == 'btn-load-sample.n_clicks':
            generate_test_data()
            return "✓ 已加载示例数据", generate_data_summary()

        if contents is None:
            return "", generate_data_summary()

        try:
            content_type, content_string = contents.split(',')
            decoded = base64.b64decode(content_string)
            temp_file = io.StringIO(decoded.decode('utf-8'))
            global data_mgr
            data_mgr = DataManager()
            result = data_mgr.import_csv(temp_file)
            if result['success']:
                data_mgr.set_basin_params(500.0, 50.0, 0.002, '壤土')
                data_mgr.split_flood_events(rain_threshold=3.0, min_duration_hours=12)
                return f"✓ {result['message']}", generate_data_summary(result)
            else:
                return f"✗ {result['message']}", generate_data_summary()
        except Exception as e:
            return f"✗ 导入失败: {str(e)}", generate_data_summary()

    # 拆分场次选择器更新，避免初始调用问题
    @app.callback(
        Output('event-selector', 'options'),
        [Input('btn-split-events', 'n_clicks'),
         Input('btn-save-basin', 'n_clicks'),
         Input('btn-load-sample', 'n_clicks'),
         Input('upload-status', 'children')],
        prevent_initial_call=True
    )
    def update_event_selector(n1, n2, n3, us):
        options, _ = get_event_options()
        return options

    @app.callback(
        Output('runoff-event-selector', 'options'),
        [Input('btn-split-events', 'n_clicks'),
         Input('btn-save-basin', 'n_clicks'),
         Input('btn-load-sample', 'n_clicks'),
         Input('upload-status', 'children')],
        prevent_initial_call=True
    )
    def update_runoff_event_selector(n1, n2, n3, us):
        options, _ = get_event_options()
        return options

    @app.callback(
        Output('routing-event-selector', 'options'),
        [Input('btn-split-events', 'n_clicks'),
         Input('btn-save-basin', 'n_clicks'),
         Input('btn-load-sample', 'n_clicks'),
         Input('upload-status', 'children')],
        prevent_initial_call=True
    )
    def update_routing_event_selector(n1, n2, n3, us):
        options, _ = get_event_options()
        return options

    @app.callback(
        [Output('cal-event-checklist', 'options'),
         Output('cal-event-checklist', 'value')],
        [Input('btn-split-events', 'n_clicks'),
         Input('btn-save-basin', 'n_clicks'),
         Input('btn-load-sample', 'n_clicks'),
         Input('upload-status', 'children')],
        prevent_initial_call=True
    )
    def update_cal_event_checklist(n1, n2, n3, us):
        options, values = get_event_options()
        return options, values

    @app.callback(
        [Output('multi-event-checklist', 'options'),
         Output('multi-event-checklist', 'value')],
        [Input('btn-split-events', 'n_clicks'),
         Input('btn-save-basin', 'n_clicks'),
         Input('btn-load-sample', 'n_clicks'),
         Input('upload-status', 'children')],
        prevent_initial_call=True
    )
    def update_multi_event_checklist(n1, n2, n3, us):
        options, values = get_event_options()
        return options, values

    @app.callback(
        Output('basin-status', 'children'),
        [Input('btn-save-basin', 'n_clicks')],
        [State('basin-area', 'value'),
         State('river-length', 'value'),
         State('basin-slope', 'value'),
         State('soil-type', 'value')],
        prevent_initial_call=True
    )
    def save_basin_params(n_clicks, area, length, slope, soil_type):
        try:
            data_mgr.set_basin_params(area, length, slope, soil_type)
            return f"✓ 已保存: 面积{area}km², 河长{length}km, 坡度{slope}, 土壤{soil_type}"
        except Exception as e:
            return f"✗ {str(e)}"

    @app.callback(
        [Output('event-info', 'children'),
         Output('event-selector', 'value')],
        [Input('btn-split-events', 'n_clicks'),
         Input('event-selector', 'value')],
        [State('rain-threshold', 'value'),
         State('min-duration', 'value'),
         State('gap-hours', 'value'),
         State('baseflow-threshold', 'value')]
    )
    def split_and_show_events(n_clicks, event_id, rain_thr, min_dur, gap_hr, base_thr):
        ctx = callback_context
        trigger = ctx.triggered[0]['prop_id'] if ctx.triggered else ''

        if trigger == 'btn-split-events.n_clicks':
            try:
                events = data_mgr.split_flood_events(
                    rain_threshold=rain_thr or 3.0,
                    min_duration_hours=min_dur or 12,
                    gap_hours=gap_hr or 6,
                    baseflow_threshold=base_thr
                )
                if events:
                    first_id = events[0]['id']
                    return show_single_event(first_id), first_id
            except Exception:
                pass
            return "未识别到有效场次", None

        if event_id and event_id != -1:
            return show_single_event(event_id), event_id
        return "请选择场次洪水", None

    def show_single_event(event_id):
        for ev in data_mgr.flood_events:
            if ev['id'] == event_id:
                info = [
                    html.Strong(f"{ev['name']}:"), html.Br(),
                    f"起止时间: {ev['start_time'].strftime('%Y-%m-%d')} ~ {ev['end_time'].strftime('%Y-%m-%d')}", html.Br(),
                    f"洪水历时: {ev['duration_hours']:.0f} 小时", html.Br(),
                    f"前期影响雨量Pa: {ev['Pa']:.1f} mm", html.Br(),
                    f"总降雨量: {ev['total_rainfall']:.1f} mm", html.Br(),
                ]
                if ev['peak_flow']:
                    info += [
                        f"洪峰流量: {ev['peak_flow']:.1f} m³/s", html.Br(),
                        f"峰现时间: {ev['peak_time'].strftime('%Y-%m-%d %H:%M') if ev['peak_time'] else 'N/A'}",
                    ]
                return html.Div(info)
        return "未找到该场次"

    @app.callback(
        Output('overview-plot', 'figure'),
        [Input('viz-tabs', 'value'),
         Input('event-selector', 'value')]
    )
    def plot_overview(tab_value, event_id):
        if data_mgr.data is None:
            return create_empty_figure("暂无数据")

        if tab_value == 'rainfall':
            if event_id and event_id != -1:
                df = data_mgr.get_event_data(event_id)
            else:
                df = data_mgr.data
            if df is None:
                return create_empty_figure()

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                subplot_titles=['降雨过程', '径流过程'],
                                vertical_spacing=0.05, row_heights=[0.4, 0.6])
            fig.add_trace(go.Bar(x=df['date'], y=df['rainfall'].fillna(0),
                                 name='降雨量 (mm)', marker_color='#1976d2'), row=1, col=1)
            if 'runoff' in df.columns and not df['runoff'].isna().all():
                fig.add_trace(go.Scatter(x=df['date'], y=df['runoff'],
                                         name='实测流量 (m³/s)', mode='lines',
                                         line=dict(color='#d32f2f', width=2)), row=2, col=1)
            fig.update_yaxes(title_text='降雨量 (mm)', row=1, col=1, autorange='reversed')
            fig.update_yaxes(title_text='流量 (m³/s)', row=2, col=1)
            fig.update_layout(height=450, template='plotly_white', showlegend=True)
            return fig

        else:
            df = data_mgr.data.copy()
            df['cum_rain'] = df['rainfall'].fillna(0).cumsum()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df['date'], y=df['cum_rain'],
                                     name='累积降雨 (mm)', fill='tozeroy',
                                     line=dict(color='#1976d2', width=2)))
            fig.update_layout(title='累积降雨曲线', yaxis_title='累积降雨量 (mm)',
                              height=450, template='plotly_white')
            return fig

    # ============================================================
    # 产流模型回调
    # ============================================================

    @app.callback(
        Output('runoff-params-container', 'children'),
        [Input('runoff-model-type', 'value')]
    )
    def render_runoff_params(model_type):
        default_config = ModelCalibrator.get_default_param_config(model_type, 'Nash')
        defaults = default_config['defaults']
        bounds = dict(zip(default_config['names'], default_config['bounds']))

        sat_params = ['WM', 'WUM', 'WLM', 'B', 'K_ET', 'C']
        ga_params = ['Ks', 'Sf', 'theta_i', 'theta_s']
        mix_param = ['sat_ratio']

        all_params = sat_params + ga_params + mix_param

        if model_type == '蓄满产流':
            visible = set(sat_params)
        elif model_type == '超渗产流':
            visible = set(ga_params)
        else:
            visible = set(all_params)

        param_labels = {
            'WM': 'WM 最大蓄水容量 (mm)',
            'WUM': 'WUM 上层蓄水容量 (mm)',
            'WLM': 'WLM 下层蓄水容量 (mm)',
            'B': 'B 蓄水容量分布指数',
            'K_ET': 'K 蒸散发折算系数',
            'C': 'C 深层蒸散发系数',
            'Ks': 'Ks 饱和导水率 (mm/h)',
            'Sf': 'Sf 湿润锋吸力 (mm)',
            'theta_i': 'θi 初始含水率',
            'theta_s': 'θs 饱和含水率',
            'sat_ratio': '饱和区域比例',
        }

        param_defaults_full = {
            'WM': 150.0, 'WUM': 20.0, 'WLM': 60.0, 'B': 0.3, 'K_ET': 1.0, 'C': 0.15,
            'Ks': 5.0, 'Sf': 50.0, 'theta_i': 0.20, 'theta_s': 0.45, 'sat_ratio': 0.3,
        }
        param_bounds_full = {
            'WM': (100, 250), 'WUM': (10, 40), 'WLM': (30, 100), 'B': (0.1, 0.4),
            'K_ET': (0.5, 1.5), 'C': (0.05, 0.3),
            'Ks': (0.5, 15.0), 'Sf': (10, 200), 'theta_i': (0.10, 0.35),
            'theta_s': (0.35, 0.55), 'sat_ratio': (0.1, 0.9),
        }

        rows = []
        row_inputs = []
        count = 0
        for p in all_params:
            is_visible = p in visible
            value = defaults.get(p, param_defaults_full.get(p, 0))
            lo, hi = param_bounds_full.get(p, (0, 1000))
            step = 0.01 if p in ['B', 'C', 'K_ET', 'theta_i', 'theta_s', 'sat_ratio'] else 1
            style = {} if is_visible else {'display': 'none'}
            row_inputs.append(dbc.Col([
                html.Div([
                    html.Label(param_labels.get(p, p)),
                    dbc.Input(id=f'param-{p}', type='number',
                              value=round(value, 4), step=step, min=lo, max=hi)
                ], style=style)
            ], width=4))
            count += 1
            if count % 3 == 0:
                rows.append(dbc.Row(row_inputs, className="mb-2"))
                row_inputs = []

        if row_inputs:
            rows.append(dbc.Row(row_inputs, className="mb-2"))

        return rows

    @app.callback(
        [Output('runoff-plot', 'figure'),
         Output('runoff-summary', 'children')],
        [Input('btn-run-runoff', 'n_clicks'),
         Input('runoff-result-tabs', 'value')],
        [State('runoff-model-type', 'value'),
         State('runoff-event-selector', 'value'),
         State('param-WM', 'value'),
         State('param-WUM', 'value'),
         State('param-WLM', 'value'),
         State('param-B', 'value'),
         State('param-K_ET', 'value'),
         State('param-C', 'value'),
         State('param-Ks', 'value'),
         State('param-Sf', 'value'),
         State('param-theta_i', 'value'),
         State('param-theta_s', 'value'),
         State('param-sat_ratio', 'value')],
        prevent_initial_call=True
    )
    def run_runoff_calc(n_clicks, result_tab, model_type, event_id,
                        WM, WUM, WLM, B, K_ET, C, Ks, Sf, theta_i, theta_s, sat_ratio):
        if n_clicks is None or event_id is None or event_id == -1:
            return create_empty_figure("请选择场次并运行计算"), "请先选择场次洪水并设置参数"

        event_df = data_mgr.get_event_data(event_id)
        if event_df is None:
            return create_empty_figure(), "未找到场次数据"

        rainfall = event_df['rainfall'].fillna(0).values
        evaporation = event_df['evaporation'].fillna(0).values if 'evaporation' in event_df.columns else None

        dt_hours = data_mgr.time_delta.total_seconds() / 3600 if data_mgr.time_delta else 24
        area = data_mgr.basin_params['area'] or 1.0

        model = get_runoff_model(model_type, dt_hours, area)
        default_config = ModelCalibrator.get_default_param_config(model_type, 'Nash')
        defaults = default_config['defaults']

        params = dict(defaults)
        if WM is not None:
            params['WM'] = float(WM)
        if WUM is not None:
            params['WUM'] = float(WUM)
        if WLM is not None:
            params['WLM'] = float(WLM)
        if B is not None:
            params['B'] = float(B)
        if K_ET is not None:
            params['K_ET'] = float(K_ET)
            params['K'] = float(K_ET)
        if C is not None:
            params['C'] = float(C)
        if Ks is not None:
            params['Ks'] = float(Ks)
        if Sf is not None:
            params['Sf'] = float(Sf)
        if theta_i is not None:
            params['theta_i'] = float(theta_i)
        if theta_s is not None:
            params['theta_s'] = float(theta_s)
        if sat_ratio is not None:
            params['sat_ratio'] = float(sat_ratio)

        result = model.run(rainfall, evaporation, **params)

        fig = go.Figure()
        if result_tab == 'runoff':
            fig.add_trace(go.Bar(x=event_df['date'], y=result['runoff_total'],
                                 name='总产流量 (mm)', marker_color='#e65100'))
            fig.add_trace(go.Bar(x=event_df['date'], y=result['runoff_surface'],
                                 name='地表径流 (mm)', marker_color='#1565c0'))
            fig.add_trace(go.Bar(x=event_df['date'], y=result['runoff_underground'],
                                 name='地下径流 (mm)', marker_color='#2e7d32'))
            fig.update_layout(barmode='stack', title='各时段产流量',
                              yaxis_title='产流量 (mm)', height=450, template='plotly_white')
        else:
            x = list(range(len(result['cumulative_runoff'])))
            fig.add_trace(go.Scatter(x=x, y=result['cumulative_runoff'],
                                     name='累积产流 (mm)', line=dict(color='#e65100', width=2)))
            fig.add_trace(go.Scatter(x=x, y=result['runoff_coefficient'] * 100,
                                     name='产流系数 (%)', line=dict(color='#1565c0', width=2),
                                     yaxis='y2'))
            fig.update_layout(
                title='累积产流与产流系数',
                yaxis=dict(title='累积产流 (mm)'),
                yaxis2=dict(title='产流系数 (%)', overlaying='y', side='right'),
                height=450, template='plotly_white'
            )

        total_runoff = float(np.sum(result['runoff_total']))
        total_rain = float(np.sum(rainfall))
        coef = total_runoff / total_rain * 100 if total_rain > 0 else 0

        summary = [
            html.Strong("产流统计:"), html.Br(),
            f"总降雨量: {total_rain:.1f} mm", html.Br(),
            f"总产流量: {total_runoff:.1f} mm", html.Br(),
            f"平均产流系数: {coef:.1f}%", html.Br(),
            f"最大时段产流量: {float(np.max(result['runoff_total'])):.2f} mm",
        ]
        return fig, html.Div(summary)

    # ============================================================
    # 汇流模型回调
    # ============================================================

    @app.callback(
        Output('routing-params-container', 'children'),
        [Input('routing-method', 'value')]
    )
    def render_routing_params(method):
        rows = []
        param_defaults = {
            'n': 2.0, 'K': 6.0, 'Kg': 48.0, 'baseflow': 5.0,
            'K_musk': 6.0, 'X_musk': 0.2
        }
        param_labels = {
            'n': 'n 水库个数', 'K': 'K 调蓄系数 (小时)',
            'Kg': 'Kg 地下水退水常数 (小时)', 'baseflow': '初始基流 (m³/s)',
            'K_musk': 'K 槽蓄常数 (小时)', 'X_musk': 'X 流量比重因子 (0~0.5)',
        }

        if method == 'Nash':
            params = ['n', 'K', 'Kg', 'baseflow']
        elif method == 'Muskingum':
            params = ['K_musk', 'X_musk', 'Kg', 'baseflow']
        else:
            params = ['Kg', 'baseflow']

        row_inputs = []
        for i, p in enumerate(params):
            row_inputs.append(dbc.Col([
                html.Label(param_labels.get(p, p)),
                dbc.Input(id=f'rparam-{p}', type='number', value=param_defaults[p], step=0.1)
            ], width=3))
            if (i + 1) % 4 == 0:
                rows.append(dbc.Row(row_inputs, className="mb-2"))
                row_inputs = []
        if row_inputs:
            rows.append(dbc.Row(row_inputs, className="mb-2"))

        return rows

    @app.callback(
        [Output('routing-plot', 'figure'),
         Output('routing-metrics', 'children')],
        [Input('btn-run-routing', 'n_clicks')],
        [State('routing-method', 'value'),
         State('routing-event-selector', 'value')],
        prevent_initial_call=True
    )
    def run_routing_calc(n_clicks, method, event_id):
        if n_clicks is None or event_id is None or event_id == -1:
            return create_empty_figure("请选择场次并运行计算"), "请先选择场次洪水并设置参数"

        event_df = data_mgr.get_event_data(event_id)
        if event_df is None:
            return create_empty_figure(), "未找到场次数据"

        rainfall = event_df['rainfall'].fillna(0).values
        evaporation = event_df['evaporation'].fillna(0).values if 'evaporation' in event_df.columns else None
        Q_obs = event_df['runoff'].values if 'runoff' in event_df.columns else None

        dt_hours = data_mgr.time_delta.total_seconds() / 3600 if data_mgr.time_delta else 24
        area = data_mgr.basin_params['area'] or 1.0

        default_config = ModelCalibrator.get_default_param_config('蓄满产流', method)
        params = default_config['defaults']

        runoff_model = get_runoff_model('蓄满产流', dt_hours, area)
        runoff_result = runoff_model.run(rainfall, evaporation, **params)

        routing_model = RoutingModel(dt_hours, area)
        routing_result = routing_model.run(
            runoff_result['runoff_surface'],
            runoff_result['runoff_underground'],
            method, **params
        )

        Q_cal = routing_result['Q_total']

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=event_df['date'], y=Q_cal,
                                 name='计算流量 (m³/s)', line=dict(color='#1565c0', width=2.5)))
        if Q_obs is not None and not np.isnan(Q_obs).all():
            fig.add_trace(go.Scatter(x=event_df['date'], y=Q_obs,
                                     name='实测流量 (m³/s)',
                                     line=dict(color='#c62828', width=2.5, dash='dash')))
        fig.add_trace(go.Scatter(x=event_df['date'], y=routing_result['Q_surface'],
                                 name='地表径流', fill='tozeroy',
                                 line=dict(color='#64b5f6', width=1)))
        fig.add_trace(go.Scatter(x=event_df['date'], y=routing_result['Q_underground'],
                                 name='地下径流', fill='tonexty',
                                 line=dict(color='#81c784', width=1)))

        fig.update_layout(title='汇流计算结果对比',
                          yaxis_title='流量 (m³/s)', height=450, template='plotly_white')

        metrics_text = [html.Strong("模拟评价指标:"), html.Br()]
        if Q_obs is not None and not np.isnan(Q_obs).all():
            metrics = calculate_metrics(Q_obs, Q_cal)
            metrics_text += [
                f"纳什效率系数 NSE: {metrics['NSE']:.4f}", html.Br(),
                f"确定性系数 DC: {metrics['DC']:.4f}", html.Br(),
                f"洪峰相对误差: {metrics['peak_error']:.2f}%", html.Br(),
                f"峰现时间误差: {metrics['peak_time_error']} 时段", html.Br(),
                f"平均相对误差: {metrics['relative_error']:.2f}%", html.Br(),
                f"实测洪峰: {metrics['peak_obs']:.1f} m³/s | 模拟洪峰: {metrics['peak_cal']:.1f} m³/s",
            ]
        else:
            metrics_text.append("无实测数据进行对比")

        return fig, html.Div(metrics_text)

    # ============================================================
    # 参数率定回调
    # ============================================================

    @app.callback(
        Output('cal-params-container', 'children'),
        [Input('cal-runoff-model', 'value')]
    )
    def render_cal_params(runoff_type):
        config = ModelCalibrator.get_default_param_config(runoff_type, 'Nash')
        names = config['names']
        bounds = config['bounds']
        defaults = config['defaults']

        rows = [dbc.Row([
            dbc.Col(html.Strong("参数名"), width=3),
            dbc.Col(html.Strong("下界"), width=3),
            dbc.Col(html.Strong("上界"), width=3),
            dbc.Col(html.Strong("初始值"), width=3),
        ], className="mb-1")]

        for name, (lo, hi) in zip(names, bounds):
            default = defaults[name]
            rows.append(dbc.Row([
                dbc.Col(html.Label(name), width=3),
                dbc.Col(dbc.Input(id=f'cal-{name}-low', type='number',
                                  value=round(lo, 3), step=0.01), width=3),
                dbc.Col(dbc.Input(id=f'cal-{name}-high', type='number',
                                  value=round(hi, 3), step=0.01), width=3),
                dbc.Col(dbc.Input(id=f'cal-{name}-init', type='number',
                                  value=round(default, 3), step=0.01), width=3),
            ], className="mb-1"))

        return rows

    @app.callback(
        [Output('cal-summary', 'children'),
         Output('cal-convergence-plot', 'figure'),
         Output('cal-compare-plot', 'figure')],
        [Input('btn-run-calibration', 'n_clicks')],
        [State('cal-runoff-model', 'value'),
         State('cal-routing-method', 'value'),
         State('cal-algorithm', 'value'),
         State('cal-max-gen', 'value'),
         State('cal-event-checklist', 'value')],
        prevent_initial_call=True
    )
    def run_calibration(n_clicks, runoff_type, routing_method, algorithm, max_gen, event_ids):
        global calibration_result
        if not event_ids or all(i == -1 for i in event_ids):
            return (html.Div("请选择至少一场洪水"),
                    create_empty_figure(),
                    create_empty_figure())

        event_list = []
        for eid in event_ids:
            ev = data_mgr.get_event_data(eid)
            if ev is not None:
                event_list.append(ev)

        if not event_list:
            return (html.Div("未获取到有效场次数据"),
                    create_empty_figure(),
                    create_empty_figure())

        config = ModelCalibrator.get_default_param_config(runoff_type, routing_method)
        names = config['names']
        bounds = config['bounds']

        dt_hours = data_mgr.time_delta.total_seconds() / 3600 if data_mgr.time_delta else 24
        area = data_mgr.basin_params['area'] or 1.0

        calibrator = ModelCalibrator(dt_hours, area)
        result = calibrator.calibrate(
            event_list,
            runoff_model_type=runoff_type,
            routing_method=routing_method,
            param_names=names,
            param_bounds=bounds,
            algorithm=algorithm,
            max_generations=max_gen,
            n_complexes=2
        )
        calibration_result = result

        summary_content = [
            html.Strong("✓ 率定完成", style={'color': '#2e7d32', 'fontSize': '16px'}),
            html.Br(), html.Br(),
            html.Strong(f"算法: {result['algorithm']}"), html.Br(),
            f"收敛: {'是' if result['converged'] else '否'} (第{result['convergence_generation']}代)",
            html.Hr(),
            html.Strong("最优NSE: "), f"{result['best_NSE']:.4f}", html.Br(),
            html.Hr(),
            html.Strong("最优参数组合:"), html.Br(),
        ]
        for k, v in result['best_params'].items():
            summary_content.append(f"  {k} = {v:.4f}")
            summary_content.append(html.Br())

        summary_content += [html.Hr(), html.Strong("各场次表现:"), html.Br()]
        for i, er in enumerate(result['event_results']):
            summary_content.append(
                f"  场次{i + 1}: NSE={er['metrics'].get('NSE', np.nan):.3f}, "
                f"洪峰误差={er['metrics'].get('peak_error', np.nan):.1f}%"
            )
            summary_content.append(html.Br())

        conv_fig = go.Figure()
        if result['convergence_history']:
            iters = [h['iteration'] for h in result['convergence_history']]
            best_nses = [h['best_nse'] for h in result['convergence_history']]
            nses = [h['nse'] for h in result['convergence_history']]
            conv_fig.add_trace(go.Scatter(x=iters, y=best_nses, mode='lines',
                                          name='最优NSE', line=dict(color='#e65100', width=2.5)))
            conv_fig.add_trace(go.Scatter(x=iters, y=nses, mode='markers',
                                          name='当前NSE', marker=dict(color='#90caf9', size=3), opacity=0.6))
        conv_fig.update_layout(title='参数收敛曲线', xaxis_title='迭代代数',
                               yaxis_title='NSE', height=300, template='plotly_white')

        compare_fig = go.Figure()
        for i, er in enumerate(result['event_results']):
            x = list(range(len(er['Q_cal'])))
            compare_fig.add_trace(go.Scatter(x=x, y=er['Q_cal'],
                                             name=f'场次{i + 1} 模拟', line=dict(width=2)))
            if er['Q_obs'] is not None:
                compare_fig.add_trace(go.Scatter(x=x, y=er['Q_obs'],
                                                 name=f'场次{i + 1} 实测',
                                                 line=dict(dash='dash', width=2)))
        compare_fig.update_layout(title='多场次模拟与实测对比', xaxis_title='时段',
                                  yaxis_title='流量 (m³/s)', height=400, template='plotly_white')

        return html.Div(summary_content), conv_fig, compare_fig

    # ============================================================
    # 洪水预报回调
    # ============================================================

    @app.callback(
        [Output('forecast-plot', 'figure'),
         Output('forecast-summary', 'children')],
        [Input('btn-run-forecast', 'n_clicks')],
        [State('forecast-rain-input', 'value'),
         State('warning-level', 'value'),
         State('confidence-level', 'value'),
         State('init-W0', 'value'),
         State('init-Qg0', 'value'),
         State('observed-q-input', 'value'),
         State('corr-coeffs', 'value'),
         State('corr-decay', 'value')],
        prevent_initial_call=True
    )
    def run_forecast(n_clicks, rain_str, warning_level, confidence, W0, Qg0, obs_str, coeff_str, decay):
        try:
            rainfall = np.array([float(x.strip()) for x in rain_str.replace('\n', ',').split(',') if x.strip()])
        except Exception:
            return create_empty_figure(), "降雨数据格式错误"

        if len(rainfall) == 0:
            return create_empty_figure(), "请输入降雨数据"

        dt_hours = data_mgr.time_delta.total_seconds() / 3600 if data_mgr.time_delta else 24
        area = data_mgr.basin_params['area'] or 1.0

        params = {}
        if calibration_result:
            params = calibration_result['best_params'].copy()
        else:
            config = ModelCalibrator.get_default_param_config('蓄满产流', 'Nash')
            params = config['defaults']

        params['WU0'] = W0 * 0.2
        params['WL0'] = W0 * 0.6
        params['WD0'] = W0 * 0.2
        params['baseflow'] = Qg0

        forecaster = Forecaster(dt_hours, area)
        forecaster.confidence_alpha = confidence / 100.0

        if calibration_result and calibration_result['event_results']:
            errors = []
            for er in calibration_result['event_results']:
                if er['Q_obs'] is not None:
                    Qo = np.array(er['Q_obs'])
                    Qc = np.array(er['Q_cal'])
                    valid = ~np.isnan(Qo) & ~np.isnan(Qc)
                    errors.extend((Qo[valid] - Qc[valid]).tolist())
            forecaster.set_historical_errors(errors)

        result = forecaster.forecast(
            rainfall,
            initial_conditions={'WU0': params['WU0'], 'WL0': params['WL0'], 'WD0': params['WD0']},
            model_params=params,
            runoff_model_type='蓄满产流',
            routing_method='Nash'
        )

        Q_raw = result['Q_forecast']
        Q_lower = result['ci_lower']
        Q_upper = result['ci_upper']

        observed = None
        Q_corrected = None
        if obs_str and obs_str.strip():
            try:
                observed = []
                for s in obs_str.replace('\n', ',').split(','):
                    s = s.strip()
                    if s.lower() == 'nan' or s == '':
                        observed.append(np.nan)
                    else:
                        observed.append(float(s))
                observed = np.array(observed)
                if len(observed) < len(Q_raw):
                    observed = np.concatenate([observed, np.full(len(Q_raw) - len(observed), np.nan)])

                coeffs = [float(x.strip()) for x in coeff_str.split(',') if x.strip()]
                forecaster.set_correction_params(coeffs, decay)

                current_idx = int(np.sum(~np.isnan(observed))) - 1 if observed is not None else -1
                if current_idx >= 0:
                    correction_result = forecaster.realtime_correction(Q_raw, observed, current_idx, coeffs)
                    Q_corrected = correction_result['Q_forecast_corrected']
            except Exception:
                pass

        Q_for_warning = Q_corrected if Q_corrected is not None else Q_raw
        warning_info = forecaster.compare_with_warning_level(Q_for_warning, warning_level)

        fig = go.Figure()
        x = list(range(len(Q_raw)))

        fig.add_trace(go.Scatter(x=x, y=Q_upper, fill=None, mode='lines',
                                 line=dict(color='rgba(100,181,246,0)'), showlegend=False))
        fig.add_trace(go.Scatter(x=x, y=Q_lower, fill='tonexty', mode='lines',
                                 line=dict(color='rgba(100,181,246,0)'),
                                 name=f'{confidence}%置信区间',
                                 fillcolor='rgba(100,181,246,0.3)'))

        fig.add_trace(go.Scatter(x=x, y=Q_raw, mode='lines+markers',
                                 name='预报流量(原始)',
                                 line=dict(color='#1565c0', width=2.5), marker=dict(size=6)))

        if Q_corrected is not None:
            fig.add_trace(go.Scatter(x=x, y=Q_corrected, mode='lines+markers',
                                     name='预报流量(校正后)',
                                     line=dict(color='#e65100', width=2.5), marker=dict(size=6)))

        if observed is not None:
            obs_x = [i for i, v in enumerate(observed) if not np.isnan(v)]
            obs_y = [observed[i] for i in obs_x]
            fig.add_trace(go.Scatter(x=obs_x, y=obs_y, mode='markers',
                                     name='实测流量',
                                     marker=dict(color='#c62828', size=10, symbol='star')))

        fig.add_hline(y=warning_level, line_dash="dash", line_color="#ff6f00",
                      annotation_text=f"警戒流量 {warning_level} m³/s")

        fig.update_layout(title='洪水预报结果',
                          xaxis_title='预报时段', yaxis_title='流量 (m³/s)',
                          height=500, template='plotly_white', hovermode='x unified')

        summary = [
            html.Strong("预报结果摘要:"), html.Br(), html.Br(),
            html.Strong(f"预报洪峰流量: {result['peak_flow']:.1f} m³/s"), html.Br(),
            f"峰现时间: 第 {result['peak_time_idx']} 时段 ({result['peak_time_hours']:.0f} 小时后)",
            html.Br(),
        ]
        if Q_corrected is not None:
            peak_corr = float(np.max(Q_corrected))
            summary += [html.Strong(f"校正后洪峰: {peak_corr:.1f} m³/s"), html.Br()]

        summary += [
            html.Hr(), html.Strong("警戒对比:"), html.Br(),
            f"超过警戒: {'是' if warning_info['will_exceed'] else '否'}", html.Br(),
        ]
        if warning_info['will_exceed']:
            summary += [
                f"首次超警: 第 {warning_info['first_exceed_idx']} 时段", html.Br(),
                f"超警持续: {warning_info['exceed_duration_hours']:.0f} 小时", html.Br(),
                f"最大超警: {warning_info['max_exceed']:.1f} m³/s",
            ]

        return fig, html.Div(summary)

    # ============================================================
    # 频率分析回调
    # ============================================================

    @app.callback(
        [Output('frequency-curve-plot', 'figure'),
         Output('frequency-results', 'children'),
         Output('fit-test-plot', 'figure')],
        [Input('btn-run-frequency', 'n_clicks'),
         Input('fit-test-tabs', 'value')],
        [State('annual-peaks-input', 'value'),
         State('dist-type', 'value'),
         State('fit-method', 'value'),
         State('design-return-period', 'value')],
        prevent_initial_call=True
    )
    def run_frequency_analysis(n_clicks, test_tab, peaks_str, dist_type, fit_method, return_period):
        global freq_result_data
        try:
            peaks = np.array([float(x.strip()) for x in peaks_str.replace('\n', ',').split(',') if x.strip()])
        except Exception:
            return create_empty_figure(), html.Div("数据格式错误"), create_empty_figure()

        if len(peaks) == 0:
            return create_empty_figure(), html.Div("请输入数据"), create_empty_figure()

        freq_analyzer = FrequencyAnalysis()
        freq_analyzer.load_annual_maxima(peaks.tolist())
        fit_result = freq_analyzer.fit_distribution(dist_type, fit_method)

        freq_result_data = {'analyzer': freq_analyzer, 'dist_type': dist_type}

        curve_data = freq_analyzer.get_frequency_curve_data(dist_type)

        curve_fig = go.Figure()
        curve_fig.add_trace(go.Scatter(x=curve_data['T_empirical'], y=curve_data['Q_empirical'],
                                       mode='markers', name='经验频率点',
                                       marker=dict(color='#1565c0', size=10, symbol='circle-open')))
        curve_fig.add_trace(go.Scatter(x=curve_data['T_theory'], y=curve_data['Q_theory'],
                                       mode='lines', name=f'{dist_type}理论曲线',
                                       line=dict(color='#e65100', width=2.5)))

        T_marks = [2, 5, 10, 20, 50, 100, 200, 500, 1000]
        curve_fig.update_xaxes(type='log', title_text='重现期 T (年)',
                               tickvals=T_marks, ticktext=[f'{t}' for t in T_marks])
        curve_fig.update_layout(title=f'{dist_type} 频率曲线 (方法: {fit_method})',
                                yaxis_title='洪峰流量 (m³/s)',
                                height=450, template='plotly_white')

        design_values = freq_analyzer.get_design_values(dist_type)
        ks_test = freq_analyzer.ks_test(dist_type)
        chi2_test = freq_analyzer.chi_square_test(dist_type)

        results_content = [
            html.Strong("数据统计:"), html.Br(),
            f"样本量: {len(peaks)} 年", html.Br(),
            f"均值: {np.mean(peaks):.1f} m³/s", html.Br(),
            f"标准差: {np.std(peaks):.1f} m³/s", html.Br(),
            f"Cv: {np.std(peaks) / np.mean(peaks):.3f}", html.Br(),
        ]

        for w in freq_analyzer.warnings:
            results_content += [html.Br(), html.Span(f"⚠ {w}", style={'color': '#f57f17'})]

        results_content += [
            html.Hr(), html.Strong("分布参数:"), html.Br(),
        ]
        for k, v in fit_result.get('params', {}).items():
            results_content.append(f"  {k} = {v:.4f}")
            results_content.append(html.Br())
        if 'Cs_Cv_ratio' in fit_result:
            results_content.append(f"  Cs/Cv = {fit_result['Cs_Cv_ratio']:.2f}")
            results_content.append(html.Br())

        results_content += [
            html.Hr(), html.Strong("设计洪峰流量:"), html.Br(),
        ]
        for T in [2, 5, 10, 20, 50, 100, 200, 500, 1000]:
            results_content.append(f"  {T:4d}年一遇: {design_values.get(T, np.nan):.1f} m³/s")
            results_content.append(html.Br())

        results_content += [
            html.Hr(), html.Strong(f"{return_period}年一遇设计值: "),
            html.Span(f"{design_values.get(return_period, np.nan):.1f} m³/s",
                      style={'color': '#e65100', 'fontWeight': 'bold', 'fontSize': '16px'}),
        ]

        if test_tab == 'ks':
            test_fig = go.Figure()
            test_fig.add_annotation(
                text="<br>".join([
                    "Kolmogorov-Smirnov 检验",
                    f"D = {ks_test['D_statistic']:.4f}",
                    f"D_crit(0.05) = {ks_test['D_critical_05']:.4f}",
                    f"P-value = {ks_test['p_value']:.4f}",
                    f"结果: {'通过' if ks_test['pass'] else '未通过'}",
                    "",
                    "Chi-Square 检验",
                    f"χ² = {chi2_test['chi2_statistic']:.4f}",
                    f"自由度 = {chi2_test['dof']}",
                    f"P-value = {chi2_test['p_value']:.4f}",
                    f"结果: {'通过' if chi2_test['pass'] else '未通过'}",
                ]),
                x=0.5, y=0.5, xref="paper", yref="paper",
                showarrow=False, font=dict(size=14), align="left"
            )
            test_fig.update_layout(title='适线检验结果', template='plotly_white', height=400)

            test_content = [
                html.Strong("K-S检验:"), html.Br(),
                f"D统计量: {ks_test['D_statistic']:.4f}", html.Br(),
                f"D临界值(α=0.05): {ks_test['D_critical_05']:.4f}", html.Br(),
                f"P值: {ks_test['p_value']:.4f}", html.Br(),
                f"检验结果: {'通过 ✓' if ks_test['pass'] else '未通过 ✗'}",
                html.Hr(),
                html.Strong("卡方检验:"), html.Br(),
                f"χ²统计量: {chi2_test['chi2_statistic']:.4f}", html.Br(),
                f"自由度: {chi2_test['dof']}", html.Br(),
                f"P值: {chi2_test['p_value']:.4f}", html.Br(),
                f"检验结果: {'通过 ✓' if chi2_test['pass'] else '未通过 ✗'}",
            ]
            return curve_fig, html.Div(results_content + [html.Hr()] + test_content), test_fig
        else:
            sorted_data, p_emp = freq_analyzer.empirical_cdf()
            cdf_fn = freq_analyzer.fits[dist_type]['cdf']
            ppf_fn = freq_analyzer.fits[dist_type]['ppf']
            p_theory_cdf = cdf_fn(sorted_data)
            q_theory = ppf_fn(p_emp)

            test_fig = make_subplots(rows=1, cols=2,
                                     subplot_titles=['P-P图 (概率-概率)', 'Q-Q图 (分位数-分位数)'])
            test_fig.add_trace(go.Scatter(x=p_emp, y=p_theory_cdf, mode='markers',
                                           name='数据点', marker=dict(color='#1565c0', size=8)),
                               row=1, col=1)
            test_fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode='lines',
                                           name='1:1线', line=dict(color='#e65100', dash='dash')),
                               row=1, col=1)

            test_fig.add_trace(go.Scatter(x=sorted_data, y=q_theory, mode='markers',
                                           name='数据点', marker=dict(color='#2e7d32', size=8)),
                               row=1, col=2)
            q_min, q_max = min(sorted_data.min(), q_theory.min()), max(sorted_data.max(), q_theory.max())
            test_fig.add_trace(go.Scatter(x=[q_min, q_max], y=[q_min, q_max], mode='lines',
                                           name='1:1线', line=dict(color='#e65100', dash='dash')),
                               row=1, col=2)

            test_fig.update_xaxes(title_text='经验概率', row=1, col=1)
            test_fig.update_yaxes(title_text='理论概率', row=1, col=1)
            test_fig.update_xaxes(title_text='经验分位数', row=1, col=2)
            test_fig.update_yaxes(title_text='理论分位数', row=1, col=2)
            test_fig.update_layout(height=400, template='plotly_white', showlegend=False)
            return curve_fig, html.Div(results_content), test_fig

    # ============================================================
    # 多场次评估回调
    # ============================================================

    @app.callback(
        [Output('multi-event-table', 'children'),
         Output('multi-viz-plot', 'figure')],
        [Input('btn-run-multi-eval', 'n_clicks'),
         Input('btn-run-loocv', 'n_clicks'),
         Input('multi-viz-tabs', 'value')],
        [State('multi-event-checklist', 'value'),
         State('compare-model-types', 'value')]
    )
    def run_multi_eval(n_eval, n_loocv, viz_tab, event_ids, model_types):
        global multi_eval_result, multi_compare_result, loocv_result
        ctx = callback_context
        if not ctx.triggered:
            return "", create_empty_figure("批量评估结果")

        trigger = ctx.triggered[0]['prop_id']

        if trigger == 'btn-run-loocv.n_clicks':
            if not event_ids or all(i == -1 for i in event_ids):
                return html.Div("请选择至少2场洪水"), create_empty_figure()

            event_list = [data_mgr.get_event_data(eid) for eid in event_ids
                          if data_mgr.get_event_data(eid) is not None]
            if len(event_list) < 2:
                return html.Div("至少需要2场洪水进行交叉验证"), create_empty_figure()

            dt_hours = data_mgr.time_delta.total_seconds() / 3600 if data_mgr.time_delta else 24
            area = data_mgr.basin_params['area'] or 1.0

            evaluator = MultiEventEvaluator(dt_hours, area)
            config = ModelCalibrator.get_default_param_config('蓄满产流', 'Nash')
            loocv_result = evaluator.leave_one_out_cv(
                event_list, '蓄满产流', 'Nash',
                config['names'], config['bounds'], max_generations=200
            )

            content = [html.Strong("留一交叉验证 (LOOCV) 结果:"), html.Hr()]
            if 'error' in loocv_result:
                content.append(loocv_result['error'])
            else:
                content += [
                    f"验证场次: {loocv_result['n_folds']} 场", html.Br(),
                    f"平均验证NSE: {loocv_result.get('mean_validation_NSE', np.nan):.4f}", html.Br(),
                    f"验证NSE标准差: {loocv_result.get('std_validation_NSE', np.nan):.4f}", html.Br(),
                    f"平均洪峰误差: {loocv_result.get('mean_peak_error', np.nan):.2f}%",
                    html.Hr(),
                    html.Strong("各折结果:"), html.Br(),
                ]
                for f in loocv_result.get('folds', []):
                    if 'error' in f:
                        content.append(f"  Fold {f['fold']}: 错误 - {f['error']}")
                    else:
                        content.append(
                            f"  Fold {f['fold']} (验证场次{f['test_event']}): "
                            f"率定NSE={f['NSE_calibration']:.3f}, 验证NSE={f['NSE_validation']:.3f}"
                        )
                    content.append(html.Br())

            if viz_tab == 'cv':
                fig = go.Figure()
                if 'folds' in loocv_result:
                    fold_nums = [f['fold'] for f in loocv_result['folds'] if 'NSE_validation' in f]
                    cal_nses = [f['NSE_calibration'] for f in loocv_result['folds'] if 'NSE_calibration' in f]
                    val_nses = [f['NSE_validation'] for f in loocv_result['folds'] if 'NSE_validation' in f]
                    fig.add_trace(go.Bar(x=fold_nums, y=cal_nses, name='率定NSE', marker_color='#1565c0'))
                    fig.add_trace(go.Bar(x=fold_nums, y=val_nses, name='验证NSE', marker_color='#e65100'))
                fig.update_layout(title='留一交叉验证 - NSE对比', barmode='group',
                                  xaxis_title='Fold', yaxis_title='NSE',
                                  height=450, template='plotly_white')
                return html.Div(content), fig

        if trigger == 'btn-run-multi-eval.n_clicks':
            if not event_ids or all(i == -1 for i in event_ids):
                return html.Div("请选择场次洪水"), create_empty_figure()

            event_list = [data_mgr.get_event_data(eid) for eid in event_ids
                          if data_mgr.get_event_data(eid) is not None]
            if not event_list:
                return html.Div("未获取到有效场次"), create_empty_figure()

            dt_hours = data_mgr.time_delta.total_seconds() / 3600 if data_mgr.time_delta else 24
            area = data_mgr.basin_params['area'] or 1.0

            model_params = {}
            if calibration_result:
                model_params = calibration_result['best_params'].copy()
            else:
                config = ModelCalibrator.get_default_param_config('蓄满产流', 'Nash')
                model_params = config['defaults']

            evaluator = MultiEventEvaluator(dt_hours, area)

            if len(model_types) > 1:
                cfgs = []
                for mt in model_types:
                    cfg_p = ModelCalibrator.get_default_param_config(mt, 'Nash')
                    cfgs.append({'runoff_type': mt, 'params': cfg_p['defaults'],
                                 'routing_method': 'Nash', 'name': mt})
                multi_compare_result = evaluator.compare_models(event_list, cfgs)
            else:
                summary = evaluator.run_batch(event_list, model_params, model_types[0], 'Nash')
                multi_eval_result = evaluator

        if viz_tab == 'compare' and multi_compare_result:
            content = [html.Strong("不同模型对比结果:"), html.Hr()]
            for name, data in multi_compare_result.items():
                s = data['summary']
                content += [
                    html.Strong(f"{name}:"), html.Br(),
                    f"  平均NSE: {s.get('nse_mean', np.nan):.4f}", html.Br(),
                    f"  洪峰合格率: {s.get('peak_pass_rate_pct', np.nan):.1f}%",
                    html.Br(), html.Br(),
                ]

            fig = go.Figure()
            for name, data in multi_compare_result.items():
                s = data['summary']
                if 'peaks_obs' in s and 'peaks_cal' in s:
                    fig.add_trace(go.Scatter(x=s['peaks_obs'], y=s['peaks_cal'],
                                             mode='markers', name=name, marker=dict(size=10)))

            if fig.data:
                all_peaks = []
                for name, data in multi_compare_result.items():
                    all_peaks.extend(data['summary'].get('peaks_obs', []))
                    all_peaks.extend(data['summary'].get('peaks_cal', []))
                if all_peaks:
                    max_v = max(all_peaks) * 1.1
                    fig.add_trace(go.Scatter(x=[0, max_v], y=[0, max_v], mode='lines',
                                             name='1:1线', line=dict(dash='dash', color='red')))
            fig.update_layout(title='不同模型 - 实测vs模拟洪峰',
                              xaxis_title='实测洪峰 (m³/s)', yaxis_title='模拟洪峰 (m³/s)',
                              height=450, template='plotly_white')
            return html.Div(content), fig

        if multi_eval_result and multi_eval_result.summary:
            s = multi_eval_result.summary
            rows_data = []
            for r in s.get('results', []):
                rows_data.append({
                    '场次': r.get('event_name', ''),
                    'NSE': f"{r.get('NSE', np.nan):.3f}",
                    '洪峰误差(%)': f"{r.get('peak_error_pct', np.nan):.1f}",
                    '峰现误差(时段)': f"{r.get('peak_time_error', np.nan):.0f}",
                    '相对误差(%)': f"{r.get('relative_error_pct', np.nan):.1f}",
                })

            table = dash_table.DataTable(
                data=rows_data,
                columns=[{'name': c, 'id': c} for c in rows_data[0].keys()] if rows_data else [],
                style_table={'overflowX': 'auto'},
                style_header={'backgroundColor': '#e3f2fd', 'fontWeight': 'bold'},
                style_cell={'textAlign': 'center', 'padding': '8px'},
            )

            summary_content = html.Div([
                html.Strong("评估汇总:"), html.Br(),
                f"场次数量: {s['n_events']}", html.Br(),
                f"平均NSE: {s.get('nse_mean', np.nan):.4f} (±{s.get('nse_std', np.nan):.3f})", html.Br(),
                f"洪峰合格率(<20%): {s.get('peak_pass_count', 0)}/{s['n_events']} = {s.get('peak_pass_rate_pct', np.nan):.1f}%",
                html.Hr(),
                table,
            ])

            fig = go.Figure()
            if viz_tab == 'scatter':
                scatter = multi_eval_result.get_scatter_data()
                if scatter:
                    fig.add_trace(go.Scatter(x=scatter['observed'], y=scatter['simulated'],
                                             mode='markers', name='场次洪峰',
                                             marker=dict(size=12, color='#1565c0')))
                    fig.add_trace(go.Scatter(x=scatter['one2one_x'], y=scatter['one2one_y'],
                                             mode='lines', name='1:1线',
                                             line=dict(color='#e65100', dash='dash', width=2)))
                fig.update_layout(title='实测 vs 模拟洪峰散点图',
                                  xaxis_title='实测洪峰 (m³/s)', yaxis_title='模拟洪峰 (m³/s)',
                                  height=450, template='plotly_white')

            elif viz_tab == 'histogram':
                hist = multi_eval_result.get_error_histogram_data()
                if hist:
                    fig.add_trace(go.Bar(x=hist['bin_centers'], y=hist['histogram'],
                                         marker_color='#1565c0', name='频数'))
                    fig.add_vline(x=hist['mean'], line_dash="dash", line_color="red",
                                  annotation_text=f"均值={hist['mean']:.1f}%")
                fig.update_layout(title='洪峰相对误差分布直方图',
                                  xaxis_title='洪峰相对误差 (%)', yaxis_title='频数',
                                  height=450, template='plotly_white')

            return summary_content, fig

        return "", create_empty_figure("请运行批量评估或交叉验证")

    # ============================================================
    # 报告导出回调
    # ============================================================

    @app.callback(
        [Output('report-preview', 'children'),
         Output('download-report', 'data')],
        [Input('btn-generate-html', 'n_clicks')],
        [State('report-title', 'value'),
         State('report-sections', 'value')],
        prevent_initial_call=True
    )
    def generate_report(n_clicks, title, sections):
        content = []
        content.append(html.H1(title, style={'textAlign': 'center', 'color': '#0d47a1'}))
        content.append(html.P(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                              style={'textAlign': 'center', 'color': 'gray'}))
        content.append(html.Hr())

        if 'basin' in sections:
            basin = data_mgr.basin_params
            content += [
                html.H2("一、流域概况"),
                html.Ul([
                    html.Li(f"流域面积: {basin.get('area', 0)} km²"),
                    html.Li(f"河道长度: {basin.get('river_length', 0)} km"),
                    html.Li(f"平均坡度: {basin.get('slope', 0)}"),
                    html.Li(f"土壤类型: {basin.get('soil_type', '壤土')}"),
                ]),
            ]

        if 'data' in sections and data_mgr.data is not None:
            df = data_mgr.data
            content += [
                html.H2("二、数据概览"),
                html.Ul([
                    html.Li(f"时间步长: {data_mgr.time_step}"),
                    html.Li(f"记录条数: {len(df)}"),
                    html.Li(f"时间范围: {df['date'].min().strftime('%Y-%m-%d')} ~ {df['date'].max().strftime('%Y-%m-%d')}"),
                    html.Li(f"总降雨量: {df['rainfall'].sum():.1f} mm"),
                    html.Li(f"场次洪水数: {len(data_mgr.flood_events)}"),
                ]),
            ]

        if 'params' in sections and calibration_result:
            content += [
                html.H2("三、模型参数"),
                html.Ul([html.Li(f"{k} = {v:.4f}") for k, v in calibration_result['best_params'].items()]),
            ]

        if 'calibration' in sections and calibration_result:
            content += [
                html.H2("四、率定结果"),
                html.Ul([
                    html.Li(f"算法: {calibration_result['algorithm']}"),
                    html.Li(f"最优NSE: {calibration_result['best_NSE']:.4f}"),
                    html.Li(f"收敛代数: {calibration_result['convergence_generation']}"),
                    html.Li(f"是否收敛: {'是' if calibration_result['converged'] else '否'}"),
                ]),
            ]

        if 'frequency' in sections and freq_result_data:
            content += [
                html.H2("五、频率分析结果"),
                html.Ul([
                    html.Li(f"分布类型: {freq_result_data['dist_type']}"),
                    html.Li(f"样本量: {len(freq_result_data['analyzer'].annual_maxima)} 年"),
                ]),
            ]

        html_report = html.Div(content, style={'maxWidth': '900px', 'margin': '0 auto', 'padding': '20px'})

        report_str = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }}
h1 {{ color: #0d47a1; text-align: center; }} h2 {{ color: #1565c0; border-bottom: 2px solid #e3f2fd; padding-bottom: 5px; }}
hr {{ border: 1px solid #e0e0e0; }}</style></head><body>
<h1>{title}</h1><p style="text-align:center;color:gray;">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p><hr>"""
        for c in content:
            if isinstance(c, html.H2):
                report_str += f"<h2>{c.children}</h2>"
            elif isinstance(c, html.Ul):
                items = "".join([f"<li>{li.children}</li>" for li in c.children])
                report_str += f"<ul>{items}</ul>"
            elif isinstance(c, html.Hr):
                report_str += "<hr>"
        report_str += "</body></html>"

        return html_report, dcc.send_string(report_str, f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")

    # ============================================================
    # 参数敏感性分析回调
    # ============================================================

    @app.callback(
        Output('sensitivity-param-select', 'options'),
        [Input('runoff-model-type', 'value')]
    )
    def update_sensitivity_param_options(model_type):
        config = ModelCalibrator.get_default_param_config(model_type, 'Nash')
        param_labels = {
            'WM': 'WM 最大蓄水容量',
            'WUM': 'WUM 上层蓄水容量',
            'WLM': 'WLM 下层蓄水容量',
            'B': 'B 蓄水容量分布指数',
            'K_ET': 'K 蒸散发折算系数',
            'C': 'C 深层蒸散发系数',
            'Ks': 'Ks 饱和导水率',
            'Sf': 'Sf 湿润锋吸力',
            'theta_i': 'θi 初始含水率',
            'theta_s': 'θs 饱和含水率',
            'sat_ratio': '饱和区域比例',
            'n': 'n 水库个数(Nash)',
            'K_uh': 'K 调蓄系数(Nash)',
            'Kg': 'Kg 地下水退水常数',
        }
        options = []
        for name in config['names']:
            label = param_labels.get(name, name)
            options.append({'label': f'{label} ({name})', 'value': name})
        return options

    @app.callback(
        [Output('sensitivity-plot', 'figure'),
         Output('sensitivity-table', 'children')],
        [Input('btn-run-sensitivity', 'n_clicks')],
        [State('runoff-model-type', 'value'),
         State('runoff-event-selector', 'value'),
         State('sensitivity-param-select', 'value'),
         State('sensitivity-routing-method', 'value'),
         State('sensitivity-n-samples', 'value'),
         State('param-WM', 'value'),
         State('param-WUM', 'value'),
         State('param-WLM', 'value'),
         State('param-B', 'value'),
         State('param-K_ET', 'value'),
         State('param-C', 'value'),
         State('param-Ks', 'value'),
         State('param-Sf', 'value'),
         State('param-theta_i', 'value'),
         State('param-theta_s', 'value'),
         State('param-sat_ratio', 'value')],
        prevent_initial_call=True
    )
    def run_sensitivity_analysis(n_clicks, model_type, event_id, target_param, routing_method, n_samples,
                                 WM, WUM, WLM, B, K_ET, C, Ks, Sf, theta_i, theta_s, sat_ratio):
        if n_clicks is None or event_id is None or event_id == -1 or target_param is None:
            return create_empty_figure("请选择参数和场次后运行分析"), "请先选择要分析的参数和场次洪水"

        event_df = data_mgr.get_event_data(event_id)
        if event_df is None:
            return create_empty_figure(), "未找到场次数据"

        rainfall = event_df['rainfall'].fillna(0).values
        evaporation = event_df['evaporation'].fillna(0).values if 'evaporation' in event_df.columns else None
        Q_obs = event_df['runoff'].values if 'runoff' in event_df.columns else None

        dt_hours = data_mgr.time_delta.total_seconds() / 3600 if data_mgr.time_delta else 24
        area = data_mgr.basin_params['area'] or 1.0

        config = ModelCalibrator.get_default_param_config(model_type, routing_method)
        bounds = dict(zip(config['names'], config['bounds']))
        defaults = config['defaults']

        base_params = dict(defaults)
        param_inputs = {
            'WM': WM, 'WUM': WUM, 'WLM': WLM, 'B': B, 'K_ET': K_ET, 'K': K_ET, 'C': C,
            'Ks': Ks, 'Sf': Sf, 'theta_i': theta_i, 'theta_s': theta_s, 'sat_ratio': sat_ratio
        }
        for k, v in param_inputs.items():
            if v is not None and k in base_params:
                base_params[k] = float(v)

        if target_param not in bounds:
            return create_empty_figure(), f"参数 {target_param} 不在率定范围内"

        lo, hi = bounds[target_param]
        n_samples = max(int(n_samples), 5)
        param_values = np.linspace(lo, hi, n_samples)

        colors = px.colors.qualitative.Plotly if hasattr(px, 'colors') else [
            '#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A',
            '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52'
        ]
        while len(colors) < len(param_values):
            colors += colors

        runoff_model = get_runoff_model(model_type, dt_hours, area)
        routing_model = RoutingModel(dt_hours, area)

        results = []
        for i, pval in enumerate(param_values):
            params = dict(base_params)
            params[target_param] = float(pval)
            try:
                runoff_result = runoff_model.run(rainfall, evaporation, **params)
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
                peak_idx = int(np.argmax(Q_cal))
                peak_flow = float(Q_cal[peak_idx])
                peak_time_idx = peak_idx
                results.append({
                    'param_value': float(pval),
                    'Q_cal': Q_cal,
                    'NSE': metrics.get('NSE', np.nan),
                    'peak_flow': peak_flow,
                    'peak_time_idx': peak_time_idx,
                    'color': colors[i % len(colors)]
                })
            except Exception as e:
                results.append({
                    'param_value': float(pval),
                    'Q_cal': None,
                    'NSE': np.nan,
                    'peak_flow': np.nan,
                    'peak_time_idx': np.nan,
                    'color': colors[i % len(colors)],
                    'error': str(e)
                })

        fig = go.Figure()
        x = list(range(len(rainfall)))
        if Q_obs is not None and not np.isnan(Q_obs).all():
            fig.add_trace(go.Scatter(x=x, y=Q_obs, mode='lines',
                                     name='实测流量',
                                     line=dict(color='#212121', width=3, dash='dash')))

        for r in results:
            if r['Q_cal'] is not None:
                fig.add_trace(go.Scatter(
                    x=x, y=r['Q_cal'], mode='lines',
                    name=f"{target_param}={r['param_value']:.3f}",
                    line=dict(color=r['color'], width=2)
                ))

        fig.update_layout(
            title=f"参数敏感性分析 - {target_param} 变化对流量过程的影响",
            xaxis_title='时段',
            yaxis_title='流量 (m³/s)',
            height=500,
            template='plotly_white',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        rows_data = []
        for r in results:
            nse_str = f"{r['NSE']:.4f}" if not np.isnan(r['NSE']) else "N/A"
            peak_str = f"{r['peak_flow']:.2f}" if not np.isnan(r['peak_flow']) else "N/A"
            time_str = f"第{r['peak_time_idx']}时段" if not np.isnan(r['peak_time_idx']) else "N/A"
            rows_data.append({
                f'{target_param}取值': f"{r['param_value']:.4f}",
                'NSE': nse_str,
                '洪峰流量(m³/s)': peak_str,
                '洪峰时间': time_str
            })

        table = dash_table.DataTable(
            data=rows_data,
            columns=[{'name': c, 'id': c} for c in rows_data[0].keys()] if rows_data else [],
            style_table={'overflowX': 'auto'},
            style_header={'backgroundColor': '#e3f2fd', 'fontWeight': 'bold'},
            style_cell={'textAlign': 'center', 'padding': '8px'},
        )

        return fig, table

    # ============================================================
    # 参数不确定性分析回调
    # ============================================================

    @app.callback(
        [Output('uncertainty-plot', 'figure'),
         Output('uncertainty-sensitivity-rank', 'children')],
        [Input('btn-run-uncertainty', 'n_clicks')],
        [State('uncertainty-n-samples', 'value'),
         State('uncertainty-perturbation', 'value'),
         State('uncertainty-confidence', 'value')],
        prevent_initial_call=True
    )
    def run_uncertainty_analysis(n_clicks, n_samples, perturbation_pct, confidence_pct):
        global calibration_result
        if n_clicks is None:
            return create_empty_figure("请先完成参数率定再运行分析"), "请先率定参数"

        if calibration_result is None:
            return create_empty_figure("请先完成参数率定再运行分析"), "请先率定参数"

        best_params = calibration_result['best_params']
        runoff_type = calibration_result['runoff_model']
        routing_method = calibration_result['routing_method']
        param_names = calibration_result['param_names']
        param_bounds = dict(zip(param_names, calibration_result['param_bounds']))

        event_results = calibration_result['event_results']
        if not event_results:
            return create_empty_figure("率定结果中无数值场次"), "无数值场次"

        dt_hours = data_mgr.time_delta.total_seconds() / 3600 if data_mgr.time_delta else 24
        area = data_mgr.basin_params['area'] or 1.0

        n_samples = max(int(n_samples), 100)
        perturbation = float(perturbation_pct) / 100.0
        confidence = float(confidence_pct) / 100.0
        alpha_low = (1.0 - confidence) / 2.0
        alpha_high = 1.0 - alpha_low

        runoff_model = get_runoff_model(runoff_type, dt_hours, area)
        routing_model = RoutingModel(dt_hours, area)

        first_event = event_results[0]
        dates = first_event.get('dates')
        n_steps = len(first_event['Q_cal'])
        Q_obs = first_event.get('Q_obs')

        event_df_list = []
        if data_mgr.flood_events:
            for ev in data_mgr.flood_events:
                ev_df = data_mgr.get_event_data(ev['id'])
                if ev_df is not None and len(ev_df) == n_steps:
                    event_df_list.append(ev_df)
                    if len(event_df_list) >= len(event_results):
                        break

        if not event_df_list and data_mgr.flood_events:
            for ev in data_mgr.flood_events:
                ev_df = data_mgr.get_event_data(ev['id'])
                if ev_df is not None:
                    event_df_list.append(ev_df)
                    break

        if not event_df_list:
            return create_empty_figure(), "无法获取场次数据，请先分割场次洪水"

        all_Q_simulations = []
        all_NSEs = []
        param_NSE_changes = {name: [] for name in param_names}

        rng = np.random.RandomState(42)
        base_params = dict(best_params)
        base_NSE = calibration_result['best_NSE']

        for sample_idx in range(n_samples):
            perturbed_params = dict(base_params)
            for name in param_names:
                val = base_params[name]
                lo, hi = param_bounds.get(name, (val * 0.5, val * 1.5))
                delta = val * perturbation * (2 * rng.random() - 1)
                new_val = np.clip(val + delta, lo, hi)
                perturbed_params[name] = float(new_val)

            sample_nses = []
            sample_qs = []
            for ev_df in event_df_list:
                rainfall = ev_df['rainfall'].fillna(0).values
                evaporation = ev_df['evaporation'].fillna(0).values if 'evaporation' in ev_df.columns else None
                Q_ev = ev_df['runoff'].values if 'runoff' in ev_df.columns else None
                try:
                    rr = runoff_model.run(rainfall, evaporation, **perturbed_params)
                    rr_result = routing_model.run(
                        rr['runoff_surface'], rr['runoff_underground'],
                        routing_method, **perturbed_params
                    )
                    Q_cal = rr_result['Q_total']
                    if len(sample_qs) == 0:
                        sample_qs = Q_cal.tolist()
                    if Q_ev is not None and not np.isnan(Q_ev).all():
                        m = calculate_metrics(Q_ev, Q_cal)
                        sample_nses.append(m['NSE'])
                except Exception:
                    pass

            if sample_qs and len(sample_qs) == n_steps:
                all_Q_simulations.append(sample_qs)

            if sample_nses:
                avg_nse = float(np.mean(sample_nses))
                all_NSEs.append(avg_nse)
                for name in param_names:
                    delta_pct = (perturbed_params[name] - base_params[name]) / base_params[name] * 100.0 if base_params[name] != 0 else 0
                    nse_change = (avg_nse - base_NSE) / max(abs(base_NSE), 1e-6) * 100.0
                    param_NSE_changes[name].append({
                        'param_delta_pct': delta_pct,
                        'nse_change_pct': nse_change,
                        'abs_nse_change': abs(nse_change)
                    })

        sensitivity_ranking = []
        for name in param_names:
            changes = param_NSE_changes[name]
            if changes:
                avg_abs_change = float(np.mean([c['abs_nse_change'] for c in changes]))
                max_abs_change = float(np.max([c['abs_nse_change'] for c in changes]))
                sensitivity_ranking.append({
                    'param': name,
                    'avg_abs_nse_change_pct': avg_abs_change,
                    'max_abs_nse_change_pct': max_abs_change
                })
        sensitivity_ranking.sort(key=lambda x: x['avg_abs_nse_change_pct'], reverse=True)

        fig = go.Figure()

        if all_Q_simulations:
            Q_array = np.array(all_Q_simulations)
            Q_mean = np.mean(Q_array, axis=0)
            Q_low = np.percentile(Q_array, alpha_low * 100, axis=0)
            Q_high = np.percentile(Q_array, alpha_high * 100, axis=0)

            x = list(range(n_steps))
            x_dates = dates if dates else x

            fig.add_trace(go.Scatter(
                x=x_dates, y=Q_high, fill=None, mode='lines',
                line=dict(color='rgba(158,158,158,0)'),
                showlegend=False
            ))
            fig.add_trace(go.Scatter(
                x=x_dates, y=Q_low, fill='tonexty', mode='lines',
                line=dict(color='rgba(158,158,158,0)'),
                name=f'{int(confidence_pct)}%置信区间',
                fillcolor='rgba(158,158,158,0.4)'
            ))

            fig.add_trace(go.Scatter(
                x=x_dates, y=Q_mean, mode='lines',
                name='模拟均值',
                line=dict(color='#1565c0', width=2.5)
            ))

            if Q_obs is not None and not np.isnan(Q_obs).all():
                fig.add_trace(go.Scatter(
                    x=x_dates, y=Q_obs, mode='lines',
                    name='实测流量',
                    line=dict(color='#c62828', width=2.5, dash='dash')
                ))

        fig.update_layout(
            title=f"蒙特卡洛不确定性分析 (采样{n_samples}次, ±{perturbation_pct}%扰动)",
            xaxis_title='时间/时段',
            yaxis_title='流量 (m³/s)',
            height=450,
            template='plotly_white'
        )

        rank_content = [html.Strong("参数敏感性排名 (按NSE平均变化幅度从大到小):"), html.Br(), html.Br()]
        for i, sr in enumerate(sensitivity_ranking):
            rank_content += [
                f"{i + 1}. {sr['param']}: ",
                html.Strong(f"平均NSE变化 {sr['avg_abs_nse_change_pct']:.2f}%"),
                f" (最大变化 {sr['max_abs_nse_change_pct']:.2f}%)",
                html.Br()
            ]

        if not sensitivity_ranking:
            rank_content.append("未计算到有效的敏感性数据")

        rank_div = html.Div(rank_content, style={
            'backgroundColor': '#fff8e1',
            'padding': '15px',
            'borderRadius': '5px'
        })

        return fig, rank_div

    # ============================================================
    # 洪水预报多方案对比回调
    # ============================================================

    @app.callback(
        [Output('forecast-plot', 'figure'),
         Output('forecast-summary', 'children'),
         Output('forecast-compare-table', 'children')],
        [Input('btn-run-forecast', 'n_clicks')],
        [State('forecast-rain-input', 'value'),
         State('warning-level', 'value'),
         State('confidence-level', 'value'),
         State('init-W0', 'value'),
         State('init-Qg0', 'value'),
         State('observed-q-input', 'value'),
         State('corr-coeffs', 'value'),
         State('corr-decay', 'value'),
         State('forecast-model-types', 'value'),
         State('forecast-routing-method', 'value')],
        prevent_initial_call=True
    )
    def run_forecast_multi(n_clicks, rain_str, warning_level, confidence, W0, Qg0, obs_str, coeff_str, decay,
                           model_types, routing_method):
        try:
            rainfall = np.array([float(x.strip()) for x in rain_str.replace('\n', ',').split(',') if x.strip()])
        except Exception:
            return create_empty_figure(), "降雨数据格式错误", ""

        if len(rainfall) == 0:
            return create_empty_figure(), "请输入降雨数据", ""

        if not model_types:
            return create_empty_figure(), "请至少选择一种产流模型", ""

        if len(model_types) > 3:
            model_types = model_types[:3]

        dt_hours = data_mgr.time_delta.total_seconds() / 3600 if data_mgr.time_delta else 24
        area = data_mgr.basin_params['area'] or 1.0

        observed = None
        if obs_str and obs_str.strip():
            try:
                observed = []
                for s in obs_str.replace('\n', ',').split(','):
                    s = s.strip()
                    if s.lower() == 'nan' or s == '':
                        observed.append(np.nan)
                    else:
                        observed.append(float(s))
                observed = np.array(observed)
            except Exception:
                observed = None

        coeffs = [0.5, 0.3, 0.2]
        try:
            coeffs = [float(x.strip()) for x in coeff_str.split(',') if x.strip()]
        except Exception:
            pass

        line_styles = {
            '蓄满产流': dict(dash='solid', width=3),
            '超渗产流': dict(dash='dash', width=3),
            '混合产流': dict(dash='dot', width=3),
        }
        color_map = {
            '蓄满产流': '#1565c0',
            '超渗产流': '#e65100',
            '混合产流': '#2e7d32',
        }

        fig = go.Figure()
        compare_rows = []
        summary_content = []

        all_forecast_results = {}

        for mt in model_types:
            params = {}
            if calibration_result and calibration_result.get('runoff_model') == mt:
                params = calibration_result['best_params'].copy()
            else:
                config = ModelCalibrator.get_default_param_config(mt, routing_method)
                params = config['defaults']

            params['WU0'] = W0 * 0.2 if W0 else params.get('WU0', 20.0)
            params['WL0'] = W0 * 0.6 if W0 else params.get('WL0', 60.0)
            params['WD0'] = W0 * 0.2 if W0 else params.get('WD0', 20.0)
            params['baseflow'] = Qg0 if Qg0 else params.get('baseflow', 5.0)

            forecaster = Forecaster(dt_hours, area)
            forecaster.confidence_alpha = confidence / 100.0

            result = forecaster.forecast(
                rainfall,
                initial_conditions={'WU0': params['WU0'], 'WL0': params['WL0'], 'WD0': params['WD0']},
                model_params=params,
                runoff_model_type=mt,
                routing_method=routing_method
            )

            Q_raw = result['Q_forecast']
            Q_corrected = None
            if observed is not None and len(observed) > 0:
                try:
                    obs_arr = observed.copy()
                    if len(obs_arr) < len(Q_raw):
                        obs_arr = np.concatenate([obs_arr, np.full(len(Q_raw) - len(obs_arr), np.nan)])
                    current_idx = int(np.sum(~np.isnan(obs_arr))) - 1 if obs_arr is not None else -1
                    if current_idx >= 0:
                        forecaster.set_correction_params(coeffs, decay)
                        correction_result = forecaster.realtime_correction(Q_raw, obs_arr, current_idx, coeffs)
                        Q_corrected = correction_result['Q_forecast_corrected']
                except Exception:
                    pass

            Q_for_display = Q_corrected if Q_corrected is not None else Q_raw
            all_forecast_results[mt] = {
                'Q': Q_for_display,
                'Q_raw': Q_raw,
                'Q_corrected': Q_corrected,
                'result': result
            }

            warning_info = forecaster.compare_with_warning_level(Q_for_display, warning_level or 0)
            peak_idx = int(np.argmax(Q_for_display))
            peak_flow = float(Q_for_display[peak_idx])
            peak_time_hours = peak_idx * dt_hours

            ls = line_styles.get(mt, dict(width=2))
            color = color_map.get(mt, '#666666')

            fig.add_trace(go.Scatter(
                x=list(range(len(Q_for_display))), y=Q_for_display, mode='lines+markers',
                name=f'{mt}预报流量',
                line=dict(color=color, **ls),
                marker=dict(size=5)
            ))

            compare_rows.append({
                '模型类型': mt,
                '预报洪峰(m³/s)': f"{peak_flow:.2f}",
                '峰现时间': f"第{peak_idx}时段 ({peak_time_hours:.0f}h)",
                '是否超警': '是 ✓' if warning_info['will_exceed'] else '否',
                '首次超警时段': f"第{warning_info['first_exceed_idx']}时段" if warning_info['first_exceed_idx'] is not None else '-',
            })

        if warning_level:
            fig.add_hline(y=warning_level, line_dash="dash", line_color="#ff6f00",
                          annotation_text=f"警戒流量 {warning_level} m³/s")

        if observed is not None:
            obs_x = [i for i, v in enumerate(observed) if not np.isnan(v)]
            obs_y = [observed[i] for i in obs_x]
            if obs_x:
                fig.add_trace(go.Scatter(x=obs_x, y=obs_y, mode='markers',
                                         name='实测流量',
                                         marker=dict(color='#c62828', size=10, symbol='star')))

        fig.update_layout(
            title='洪水预报多方案对比',
            xaxis_title='预报时段',
            yaxis_title='流量 (m³/s)',
            height=500,
            template='plotly_white',
            hovermode='x unified'
        )

        summary_content += [
            html.Strong("多方案预报结果摘要:"), html.Br(), html.Br()
        ]
        for mt, fr in all_forecast_results.items():
            res = fr['result']
            summary_content += [
                html.Strong(f"{mt}:"), html.Br(),
                f"  洪峰流量: {res['peak_flow']:.1f} m³/s", html.Br(),
                f"  峰现时间: 第 {res['peak_time_idx']} 时段 ({res['peak_time_hours']:.0f} 小时后)",
                html.Br(),
            ]
            if fr['Q_corrected'] is not None:
                peak_corr = float(np.max(fr['Q_corrected']))
                summary_content += [f"  校正后洪峰: {peak_corr:.1f} m³/s", html.Br()]

        compare_table = dash_table.DataTable(
            data=compare_rows,
            columns=[{'name': c, 'id': c} for c in compare_rows[0].keys()] if compare_rows else [],
            style_table={'overflowX': 'auto'},
            style_header={'backgroundColor': '#ffe0b2', 'fontWeight': 'bold'},
            style_cell={'textAlign': 'center', 'padding': '8px'},
            style_data_conditional=[
                {
                    'if': {'filter_query': '{是否超警} eq "是 ✓"'},
                    'backgroundColor': '#ffccbc',
                    'color': '#bf360c',
                    'fontWeight': 'bold'
                }
            ]
        )

        return fig, html.Div(summary_content), compare_table

from dash import Dash, Input, Output, State, callback_context, dash_table, dcc, html, no_update
from flask import session

from financeiro import services

SIDEBAR_STYLE = {
    "width": "240px",
    "background": "#1f2937",
    "color": "white",
    "padding": "20px 14px",
    "minHeight": "100vh",
}
CONTENT_STYLE = {
    "flex": "1",
    "padding": "24px",
    "background": "#f3f4f6",
    "minHeight": "100vh",
}
CARD_STYLE = {
    "background": "white",
    "borderRadius": "12px",
    "padding": "18px",
    "boxShadow": "0 2px 8px rgba(0,0,0,0.08)",
}
BUTTON_PRIMARY = {"background": "#2563eb", "color": "white", "border": "0", "padding": "10px 14px", "borderRadius": "8px", "cursor": "pointer"}
BUTTON_DARK = {"background": "#111827", "color": "white", "border": "0", "padding": "10px 14px", "borderRadius": "8px", "cursor": "pointer"}
BUTTON_DANGER = {"background": "#dc2626", "color": "white", "border": "0", "padding": "10px 14px", "borderRadius": "8px", "cursor": "pointer"}
INPUT_STYLE = {"width": "100%", "padding": "10px", "borderRadius": "8px", "border": "1px solid #d1d5db"}

_dash_app = None


def get_financeiro_dash():
    return _dash_app


def _options():
    ctx = services.options_context()
    return {
        "contas": [{"label": item["nome"], "value": item["id"]} for item in ctx["contas"]],
        "centros": [{"label": item["nome"], "value": item["id"]} for item in ctx["centros"]],
        "categorias": [{"label": item["nome"], "value": item["id"]} for item in ctx["categorias"]],
        "subcategorias": [{"label": f"{item['nome']} ({item['categoria']})", "value": item["id"]} for item in ctx["subcategorias"]],
    }


def _datatable(table_id, columns, data):
    return dash_table.DataTable(
        id=table_id,
        columns=columns,
        data=data,
        page_size=10,
        row_selectable="single",
        selected_rows=[],
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "left", "padding": "8px", "fontFamily": "Arial", "fontSize": 13},
        style_header={"backgroundColor": "#e5e7eb", "fontWeight": "bold"},
    )


def _toolbar(prefix):
    return html.Div([
        html.Button("Incluir", id=f"{prefix}-add", n_clicks=0, style=BUTTON_PRIMARY),
        html.Button("Editar", id=f"{prefix}-edit", n_clicks=0, style=BUTTON_DARK),
        html.Button("Excluir", id=f"{prefix}-delete", n_clicks=0, style=BUTTON_DANGER),
    ], style={"display": "flex", "gap": "10px", "marginBottom": "14px"})


def _dashboard_page():
    totals = services.get_dashboard_totals()
    return html.Div([
        html.H3("Dashboard Financeiro"),
        html.Div([
            html.Div([html.Small("Saldo Geral"), html.H2(services.money(totals["saldo_geral"]))], style=CARD_STYLE),
            html.Div([html.Small("Total a Pagar"), html.H2(services.money(totals["total_pagar"]))], style=CARD_STYLE),
            html.Div([html.Small("Total a Receber"), html.H2(services.money(totals["total_receber"]))], style=CARD_STYLE),
        ], style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit,minmax(220px,1fr))", "gap": "16px", "marginBottom": "18px"}),
        html.Div([
            html.H4("Ultimos Lancamentos"),
            _datatable("dash-lancamentos", [
                {"name": "Data", "id": "data"}, {"name": "Descricao", "id": "descricao"}, {"name": "Tipo", "id": "tipo"}, {"name": "Valor", "id": "valor_label"}, {"name": "Conta", "id": "conta"}, {"name": "Status", "id": "status"}
            ], services.list_lancamentos()[:15]),
        ], style=CARD_STYLE),
    ])


def _contas_page():
    data = services.list_accounts()
    return html.Div([
        html.H3("Contas Correntes"),
        html.Div(id="contas-msg", style={"marginBottom": "12px", "color": "#1d4ed8"}),
        html.Div([
            html.Div([
                dcc.Input(id="conta-id", type="hidden"),
                html.Label("Nome"), dcc.Input(id="conta-nome", style=INPUT_STYLE),
                html.Label("Saldo Atual", style={"marginTop": "8px"}), dcc.Input(id="conta-saldo", style=INPUT_STYLE),
                html.Div(_toolbar("contas"), style={"marginTop": "14px"}),
            ], style=CARD_STYLE),
            html.Div([_datatable("contas-table", [{"name": "ID", "id": "id"}, {"name": "Conta", "id": "nome"}, {"name": "Saldo", "id": "saldo_label"}], data)], style=CARD_STYLE),
        ], style={"display": "grid", "gridTemplateColumns": "320px 1fr", "gap": "16px"}),
    ])


def _lancamentos_page():
    opts = _options()
    data = services.list_lancamentos()
    return html.Div([
        html.H3("Lancamentos Financeiros"),
        html.Div(id="lancamentos-msg", style={"marginBottom": "12px", "color": "#1d4ed8"}),
        html.Div([
            html.Div([
                dcc.Input(id="lanc-id", type="hidden"),
                html.Label("Data"), dcc.Input(id="lanc-data", type="text", placeholder="YYYY-MM-DD", style=INPUT_STYLE),
                html.Label("Descricao", style={"marginTop": "8px"}), dcc.Input(id="lanc-descricao", style=INPUT_STYLE),
                html.Div(id="lanc-sugestao", style={"marginTop": "6px", "fontSize": 12, "color": "#475569"}),
                html.Label("Valor", style={"marginTop": "8px"}), dcc.Input(id="lanc-valor", style=INPUT_STYLE),
                html.Label("Tipo", style={"marginTop": "8px"}), dcc.Dropdown(options=[{"label": x, "value": x} for x in services.TIPOS_LANCAMENTO], id="lanc-tipo", value="PAGAR"),
                html.Label("Conta", style={"marginTop": "8px"}), dcc.Dropdown(options=opts["contas"], id="lanc-conta"),
                html.Label("Centro de Custo", style={"marginTop": "8px"}), dcc.Dropdown(options=opts["centros"], id="lanc-centro"),
                html.Label("Categoria", style={"marginTop": "8px"}), dcc.Dropdown(options=opts["categorias"], id="lanc-categoria"),
                html.Label("Subcategoria", style={"marginTop": "8px"}), dcc.Dropdown(options=opts["subcategorias"], id="lanc-subcategoria"),
                html.Label("Status", style={"marginTop": "8px"}), dcc.Dropdown(options=[{"label": x, "value": x} for x in services.STATUS_LANCAMENTO], id="lanc-status", value="ABERTO"),
                html.Label("Origem", style={"marginTop": "8px"}), dcc.Dropdown(options=[{"label": x, "value": x} for x in services.ORIGENS_LANCAMENTO], id="lanc-origem", value="MANUAL"),
                html.Div(_toolbar("lanc"), style={"marginTop": "14px"}),
                html.Button("Marcar Pago/Reabrir", id="lanc-toggle", n_clicks=0, style=BUTTON_DARK),
            ], style=CARD_STYLE),
            html.Div([
                html.Div([
                    dcc.Input(id="filtro-data-inicial", placeholder="Data inicial", style=INPUT_STYLE),
                    dcc.Input(id="filtro-data-final", placeholder="Data final", style=INPUT_STYLE),
                    dcc.Dropdown(id="filtro-conta", options=opts["contas"], placeholder="Conta"),
                    dcc.Dropdown(id="filtro-centro", options=opts["centros"], placeholder="Centro de custo"),
                    dcc.Dropdown(id="filtro-status", options=[{"label": x, "value": x} for x in services.STATUS_LANCAMENTO], placeholder="Status"),
                    html.Button("Filtrar", id="lanc-filtrar", n_clicks=0, style=BUTTON_PRIMARY),
                ], style={"display": "grid", "gridTemplateColumns": "repeat(6, minmax(120px,1fr))", "gap": "10px", "marginBottom": "12px"}),
                _datatable("lanc-table", [
                    {"name": "ID", "id": "id"}, {"name": "Data", "id": "data"}, {"name": "Descricao", "id": "descricao"}, {"name": "Tipo", "id": "tipo"}, {"name": "Valor", "id": "valor_label"}, {"name": "Conta", "id": "conta"}, {"name": "Centro", "id": "centro_custo"}, {"name": "Status", "id": "status"}
                ], data),
            ], style=CARD_STYLE),
        ], style={"display": "grid", "gridTemplateColumns": "360px 1fr", "gap": "16px"}),
    ])


def _duplicatas_page():
    opts = _options()
    return html.Div([
        html.H3("Duplicatas"),
        html.Div(id="duplicatas-msg", style={"marginBottom": "12px", "color": "#1d4ed8"}),
        html.Div([
            html.Div([
                dcc.Input(id="dup-id", type="hidden"),
                html.Label("Descricao"), dcc.Input(id="dup-descricao", style=INPUT_STYLE),
                html.Label("Valor Total", style={"marginTop": "8px"}), dcc.Input(id="dup-valor", style=INPUT_STYLE),
                html.Label("Quantidade de Parcelas", style={"marginTop": "8px"}), dcc.Input(id="dup-qtde", type="number", min=1, step=1, value=1, style=INPUT_STYLE),
                html.Label("Tipo", style={"marginTop": "8px"}), dcc.Dropdown(options=[{"label": x, "value": x} for x in services.TIPOS_LANCAMENTO], id="dup-tipo", value="PAGAR"),
                html.Label("Primeiro Vencimento", style={"marginTop": "8px"}), dcc.Input(id="dup-primeiro-venc", placeholder="YYYY-MM-DD", style=INPUT_STYLE),
                html.Div(_toolbar("dup"), style={"marginTop": "14px"}),
            ], style=CARD_STYLE),
            html.Div([
                html.Div([html.H4("Duplicatas"), _datatable("dup-table", [{"name": "ID", "id": "id"}, {"name": "Descricao", "id": "descricao"}, {"name": "Tipo", "id": "tipo"}, {"name": "Total", "id": "valor_total_label"}, {"name": "Parcelas", "id": "quantidade_parcelas"}], services.list_duplicatas())], style={"marginBottom": "16px"}),
                html.Div([html.H4("Parcelas"), _datatable("parcelas-table", [{"name": "ID", "id": "id"}, {"name": "Duplicata", "id": "duplicata"}, {"name": "Parcela", "id": "numero_parcela"}, {"name": "Vencimento", "id": "data_vencimento"}, {"name": "Valor", "id": "valor_label"}, {"name": "Status", "id": "status"}], services.list_parcelas())]),
                html.Div([
                    dcc.Dropdown(id="parcela-conta", options=opts["contas"], placeholder="Conta corrente"),
                    dcc.Dropdown(id="parcela-centro", options=opts["centros"], placeholder="Centro de custo"),
                    dcc.Dropdown(id="parcela-categoria", options=opts["categorias"], placeholder="Categoria"),
                    dcc.Dropdown(id="parcela-subcategoria", options=opts["subcategorias"], placeholder="Subcategoria"),
                    html.Button("Gerar Lancamento da Parcela", id="parcela-gerar", n_clicks=0, style=BUTTON_PRIMARY),
                    html.Button("Baixar Parcela", id="parcela-baixar", n_clicks=0, style=BUTTON_DARK),
                ], style={"display": "grid", "gridTemplateColumns": "repeat(6, minmax(120px,1fr))", "gap": "10px", "marginTop": "12px"}),
            ], style=CARD_STYLE),
        ], style={"display": "grid", "gridTemplateColumns": "340px 1fr", "gap": "16px"}),
    ])

def _importacao_page():
    opts = _options()
    return html.Div([
        html.H3("Importacao de Extrato"),
        html.Div(id="extrato-msg", style={"marginBottom": "12px", "color": "#1d4ed8"}),
        html.Div([
            html.Div([
                html.Label("Conta Corrente"), dcc.Dropdown(id="extrato-conta", options=opts["contas"]),
                dcc.Upload(id="extrato-upload", children=html.Div(["Arraste CSV/OFX aqui ou clique para selecionar"]), style={"marginTop": "12px", "padding": "24px", "border": "2px dashed #94a3b8", "borderRadius": "12px", "textAlign": "center", "background": "#f8fafc"}),
                html.Button("Importar Arquivo", id="extrato-importar", n_clicks=0, style={**BUTTON_PRIMARY, "marginTop": "12px"}),
                html.Hr(),
                html.H4("Inclusao Manual"),
                dcc.Input(id="extrato-id", type="hidden"),
                dcc.Input(id="extrato-data", placeholder="YYYY-MM-DD", style=INPUT_STYLE),
                dcc.Input(id="extrato-descricao", placeholder="Descricao", style={**INPUT_STYLE, "marginTop": "8px"}),
                dcc.Input(id="extrato-valor", placeholder="Valor", style={**INPUT_STYLE, "marginTop": "8px"}),
                html.Div(_toolbar("extrato"), style={"marginTop": "14px"}),
            ], style=CARD_STYLE),
            html.Div([_datatable("extrato-table", [{"name": "ID", "id": "id"}, {"name": "Data", "id": "data"}, {"name": "Descricao", "id": "descricao"}, {"name": "Valor", "id": "valor_label"}, {"name": "Conta", "id": "conta"}, {"name": "Conciliado", "id": "conciliado"}, {"name": "Sugestao", "id": "sugestao"}], services.list_extrato())], style=CARD_STYLE),
        ], style={"display": "grid", "gridTemplateColumns": "360px 1fr", "gap": "16px"}),
    ])


def _conciliacao_page():
    opts = _options()
    extratos = [item for item in services.list_extrato(status="NAO")]
    return html.Div([
        html.H3("Conciliacao Bancaria"),
        html.Div(id="conciliacao-msg", style={"marginBottom": "12px", "color": "#1d4ed8"}),
        html.Div([
            html.Div([_datatable("conc-extrato-table", [{"name": "ID", "id": "id"}, {"name": "Data", "id": "data"}, {"name": "Descricao", "id": "descricao"}, {"name": "Valor", "id": "valor_label"}, {"name": "Conta", "id": "conta"}], extratos)], style=CARD_STYLE),
            html.Div([
                html.Label("Lancamento para vincular"),
                dcc.Dropdown(id="conc-lancamento", options=[], placeholder="Selecione o extrato primeiro"),
                html.Button("Conciliar", id="conciliar-btn", n_clicks=0, style={**BUTTON_PRIMARY, "marginTop": "12px"}),
                html.Hr(),
                html.Div([html.Small("Filtro rapido"), dcc.Dropdown(id="conc-filtro-conta", options=opts["contas"], placeholder="Conta")]),
                html.Div([html.Small("Lancamentos em aberto/pagos"), _datatable("conc-lanc-table", [{"name": "ID", "id": "id"}, {"name": "Data", "id": "data"}, {"name": "Descricao", "id": "descricao"}, {"name": "Valor", "id": "valor_label"}, {"name": "Conta", "id": "conta"}, {"name": "Status", "id": "status"}], services.list_lancamentos())], style={"marginTop": "12px"}),
            ], style=CARD_STYLE),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}),
    ])


def _padroes_page():
    opts = _options()
    return html.Div([
        html.H3("Cadastro de Extrato Padrao"),
        html.Div(id="padroes-msg", style={"marginBottom": "12px", "color": "#1d4ed8"}),
        html.Div([
            html.Div([
                dcc.Input(id="padrao-id", type="hidden"),
                html.Label("Descricao padrao"), dcc.Input(id="padrao-descricao", style=INPUT_STYLE),
                html.Label("Categoria", style={"marginTop": "8px"}), dcc.Dropdown(id="padrao-categoria", options=opts["categorias"]),
                html.Label("Subcategoria", style={"marginTop": "8px"}), dcc.Dropdown(id="padrao-subcategoria", options=opts["subcategorias"]),
                html.Label("Centro de custo", style={"marginTop": "8px"}), dcc.Dropdown(id="padrao-centro", options=opts["centros"]),
                html.Div(_toolbar("padrao"), style={"marginTop": "14px"}),
            ], style=CARD_STYLE),
            html.Div([_datatable("padroes-table", [{"name": "ID", "id": "id"}, {"name": "Descricao", "id": "descricao_padrao"}, {"name": "Categoria", "id": "categoria"}, {"name": "Subcategoria", "id": "subcategoria"}, {"name": "Centro", "id": "centro_custo"}], services.list_padroes())], style=CARD_STYLE),
        ], style={"display": "grid", "gridTemplateColumns": "360px 1fr", "gap": "16px"}),
    ])


def _page_content(pathname):
    page = pathname or "/financeiro/dashboard"
    session["last_fin_page"] = page
    if page in {"/financeiro", "/financeiro/", "/financeiro/dashboard"}:
        return _dashboard_page()
    if page == "/financeiro/contas":
        return _contas_page()
    if page == "/financeiro/lancamentos":
        return _lancamentos_page()
    if page == "/financeiro/duplicatas":
        return _duplicatas_page()
    if page == "/financeiro/importacao":
        return _importacao_page()
    if page == "/financeiro/conciliacao":
        return _conciliacao_page()
    if page == "/financeiro/padroes":
        return _padroes_page()
    return html.Div([html.H3("Pagina nao encontrada")])


def init_financeiro_dash(server):
    global _dash_app
    if _dash_app is not None:
        return _dash_app

    app = Dash(__name__, server=server, url_base_pathname="/financeiro/", suppress_callback_exceptions=True, title="Financeiro SGME")
    app.layout = html.Div([
        dcc.Location(id="fin-url"),
        html.Div([
            html.Div([
                html.H2("Financeiro", style={"fontSize": "22px", "marginBottom": "18px"}),
                dcc.Link("Dashboard", href="/financeiro/dashboard", style={"display": "block", "color": "white", "padding": "10px 12px", "textDecoration": "none"}),
                dcc.Link("Contas Correntes", href="/financeiro/contas", style={"display": "block", "color": "white", "padding": "10px 12px", "textDecoration": "none"}),
                dcc.Link("Lancamentos", href="/financeiro/lancamentos", style={"display": "block", "color": "white", "padding": "10px 12px", "textDecoration": "none"}),
                dcc.Link("Duplicatas", href="/financeiro/duplicatas", style={"display": "block", "color": "white", "padding": "10px 12px", "textDecoration": "none"}),
                dcc.Link("Importacao de Extrato", href="/financeiro/importacao", style={"display": "block", "color": "white", "padding": "10px 12px", "textDecoration": "none"}),
                dcc.Link("Conciliacao", href="/financeiro/conciliacao", style={"display": "block", "color": "white", "padding": "10px 12px", "textDecoration": "none"}),
                dcc.Link("Extrato Padrao", href="/financeiro/padroes", style={"display": "block", "color": "white", "padding": "10px 12px", "textDecoration": "none"}),
            ], style=SIDEBAR_STYLE),
            html.Div(id="fin-page", style=CONTENT_STYLE),
        ], style={"display": "flex"}),
    ])

    @app.callback(Output("fin-page", "children"), Input("fin-url", "pathname"))
    def render_page(pathname):
        return _page_content(pathname)

    @app.callback(Output("conta-id", "value"), Output("conta-nome", "value"), Output("conta-saldo", "value"), Input("contas-table", "selected_rows"), State("contas-table", "data"), prevent_initial_call=True)
    def select_conta(rows, data):
        if not rows:
            return "", "", ""
        item = data[rows[0]]
        return item["id"], item["nome"], item["saldo_atual"]

    @app.callback(Output("contas-msg", "children"), Output("contas-table", "data"), Output("conta-id", "value"), Output("conta-nome", "value"), Output("conta-saldo", "value"), Input("contas-add", "n_clicks"), Input("contas-edit", "n_clicks"), Input("contas-delete", "n_clicks"), State("conta-id", "value"), State("conta-nome", "value"), State("conta-saldo", "value"), prevent_initial_call=True)
    def manage_conta(_, __, ___, conta_id, nome, saldo):
        action = callback_context.triggered_id
        try:
            if action == "contas-add":
                services.save_account(None, nome, saldo)
                msg = "Conta incluida com sucesso."
            elif action == "contas-edit":
                services.save_account(conta_id, nome, saldo)
                msg = "Conta editada com sucesso."
            elif action == "contas-delete":
                services.delete_account(conta_id)
                msg = "Conta excluida com sucesso."
            else:
                return no_update, no_update, no_update, no_update, no_update
            return msg, services.list_accounts(), "", "", ""
        except Exception as exc:
            return str(exc), services.list_accounts(), conta_id, nome, saldo

    @app.callback(Output("lanc-sugestao", "children"), Input("lanc-descricao", "value"), prevent_initial_call=True)
    def suggest_lancamento(descricao):
        sugestao = services.suggest_category(descricao)
        if not sugestao:
            return ""
        return f"Sugestao automatica: {sugestao['categoria_nome']} / {sugestao['subcategoria_nome'] or '-'} / {sugestao['centro_custo_nome'] or '-'} ({sugestao['origem']})"

    @app.callback(Output("lanc-id", "value"), Output("lanc-data", "value"), Output("lanc-descricao", "value"), Output("lanc-valor", "value"), Output("lanc-tipo", "value"), Output("lanc-conta", "value"), Output("lanc-centro", "value"), Output("lanc-categoria", "value"), Output("lanc-subcategoria", "value"), Output("lanc-status", "value"), Output("lanc-origem", "value"), Input("lanc-table", "selected_rows"), State("lanc-table", "data"), prevent_initial_call=True)
    def select_lancamento(rows, data):
        if not rows:
            return "", "", "", "", "PAGAR", None, None, None, None, "ABERTO", "MANUAL"
        item = data[rows[0]]
        return item["id"], item["data"], item["descricao"], item["valor"], item["tipo"], item["conta_corrente_id"], item["centro_custo_id"], item["categoria_id"], item["subcategoria_id"], item["status"], item["origem"]

    @app.callback(Output("lancamentos-msg", "children"), Output("lanc-table", "data"), Output("lanc-id", "value"), Output("lanc-data", "value"), Output("lanc-descricao", "value"), Output("lanc-valor", "value"), Input("lanc-add", "n_clicks"), Input("lanc-edit", "n_clicks"), Input("lanc-delete", "n_clicks"), Input("lanc-toggle", "n_clicks"), Input("lanc-filtrar", "n_clicks"), State("lanc-id", "value"), State("lanc-data", "value"), State("lanc-descricao", "value"), State("lanc-valor", "value"), State("lanc-tipo", "value"), State("lanc-conta", "value"), State("lanc-centro", "value"), State("lanc-categoria", "value"), State("lanc-subcategoria", "value"), State("lanc-status", "value"), State("lanc-origem", "value"), State("filtro-data-inicial", "value"), State("filtro-data-final", "value"), State("filtro-conta", "value"), State("filtro-centro", "value"), State("filtro-status", "value"), prevent_initial_call=True)
    def manage_lancamentos(_, __, ___, ____, _____, lanc_id, data, descricao, valor, tipo, conta, centro, categoria, subcategoria, status, origem, data_inicial, data_final, filtro_conta, filtro_centro, filtro_status):
        action = callback_context.triggered_id
        try:
            msg = ""
            if action == "lanc-add":
                services.save_lancamento(None, {"data": data, "descricao": descricao, "valor": valor, "tipo": tipo, "conta_corrente_id": conta, "centro_custo_id": centro, "categoria_id": categoria, "subcategoria_id": subcategoria, "status": status, "origem": origem})
                msg = "Lancamento incluido com sucesso."
            elif action == "lanc-edit":
                services.save_lancamento(lanc_id, {"data": data, "descricao": descricao, "valor": valor, "tipo": tipo, "conta_corrente_id": conta, "centro_custo_id": centro, "categoria_id": categoria, "subcategoria_id": subcategoria, "status": status, "origem": origem})
                msg = "Lancamento editado com sucesso."
            elif action == "lanc-delete":
                services.delete_lancamento(lanc_id)
                msg = "Lancamento excluido com sucesso."
            elif action == "lanc-toggle":
                services.toggle_paid(lanc_id)
                msg = "Status do lancamento atualizado."
            data_rows = services.list_lancamentos(data_inicial, data_final, filtro_conta, filtro_centro, filtro_status)
            return msg, data_rows, "", "", "", ""
        except Exception as exc:
            return str(exc), services.list_lancamentos(data_inicial, data_final, filtro_conta, filtro_centro, filtro_status), lanc_id, data, descricao, valor

    @app.callback(Output("dup-id", "value"), Output("dup-descricao", "value"), Output("dup-valor", "value"), Output("dup-qtde", "value"), Output("dup-tipo", "value"), Input("dup-table", "selected_rows"), State("dup-table", "data"), prevent_initial_call=True)
    def select_dup(rows, data):
        if not rows:
            return "", "", "", 1, "PAGAR"
        item = data[rows[0]]
        return item["id"], item["descricao"], item["valor_total"], item["quantidade_parcelas"], item["tipo"]

    @app.callback(Output("duplicatas-msg", "children"), Output("dup-table", "data"), Output("parcelas-table", "data"), Output("dup-id", "value"), Output("dup-descricao", "value"), Output("dup-valor", "value"), Input("dup-add", "n_clicks"), Input("dup-edit", "n_clicks"), Input("dup-delete", "n_clicks"), Input("parcela-gerar", "n_clicks"), Input("parcela-baixar", "n_clicks"), State("dup-id", "value"), State("dup-descricao", "value"), State("dup-valor", "value"), State("dup-qtde", "value"), State("dup-tipo", "value"), State("dup-primeiro-venc", "value"), State("parcelas-table", "selected_rows"), State("parcelas-table", "data"), State("parcela-conta", "value"), State("parcela-centro", "value"), State("parcela-categoria", "value"), State("parcela-subcategoria", "value"), prevent_initial_call=True)
    def manage_dup(_, __, ___, ____, _____, dup_id, descricao, valor, qtde, tipo, venc, parcela_rows, parcelas_data, conta, centro, categoria, subcategoria):
        action = callback_context.triggered_id
        try:
            if action == "dup-add":
                services.save_duplicata(None, {"descricao": descricao, "valor_total": valor, "quantidade_parcelas": qtde, "tipo": tipo, "primeiro_vencimento": venc})
                msg = "Duplicata incluida com sucesso."
            elif action == "dup-edit":
                services.save_duplicata(dup_id, {"descricao": descricao, "valor_total": valor, "quantidade_parcelas": qtde, "tipo": tipo, "primeiro_vencimento": venc})
                msg = "Duplicata editada com sucesso."
            elif action == "dup-delete":
                services.delete_duplicata(dup_id)
                msg = "Duplicata excluida com sucesso."
            else:
                if not parcela_rows:
                    raise ValueError("Selecione uma parcela.")
                parcela_id = parcelas_data[parcela_rows[0]]["id"]
                if action == "parcela-gerar":
                    services.gerar_lancamento_parcela(parcela_id, {"conta_corrente_id": conta, "centro_custo_id": centro, "categoria_id": categoria, "subcategoria_id": subcategoria})
                    msg = "Lancamento da parcela gerado com sucesso."
                else:
                    services.baixar_parcela(parcela_id)
                    msg = "Parcela baixada com sucesso."
            return msg, services.list_duplicatas(), services.list_parcelas(), "", "", ""
        except Exception as exc:
            return str(exc), services.list_duplicatas(), services.list_parcelas(), dup_id, descricao, valor

    @app.callback(Output("extrato-msg", "children"), Output("extrato-table", "data"), Output("extrato-id", "value"), Output("extrato-data", "value"), Output("extrato-descricao", "value"), Output("extrato-valor", "value"), Input("extrato-importar", "n_clicks"), Input("extrato-add", "n_clicks"), Input("extrato-edit", "n_clicks"), Input("extrato-delete", "n_clicks"), State("extrato-upload", "contents"), State("extrato-upload", "filename"), State("extrato-id", "value"), State("extrato-conta", "value"), State("extrato-data", "value"), State("extrato-descricao", "value"), State("extrato-valor", "value"), State("extrato-table", "selected_rows"), State("extrato-table", "data"), prevent_initial_call=True)
    def manage_extrato(_, __, ___, ____, contents, filename, extrato_id, conta, data, descricao, valor, rows, table_data):
        action = callback_context.triggered_id
        try:
            if action == "extrato-importar":
                resumo = services.import_statement(contents, filename, conta)
                msg = f"Importacao concluida: {resumo['importados']} importado(s), {resumo['ignorados']} ignorado(s), {resumo['classificados']} classificado(s)."
            elif action == "extrato-add":
                services.save_extrato_manual(data, descricao, valor, conta)
                msg = "Extrato incluido com sucesso."
            elif action == "extrato-edit":
                services.save_extrato(extrato_id, data, descricao, valor, conta)
                msg = "Extrato editado com sucesso."
            elif action == "extrato-delete":
                if not rows:
                    raise ValueError("Selecione um item de extrato.")
                services.delete_extrato(table_data[rows[0]]["id"])
                msg = "Extrato excluido com sucesso."
            else:
                return no_update, no_update, no_update, no_update, no_update, no_update
            return msg, services.list_extrato(), "", "", "", ""
        except Exception as exc:
            return str(exc), services.list_extrato(), extrato_id, data, descricao, valor

    @app.callback(Output("extrato-id", "value"), Output("extrato-data", "value"), Output("extrato-descricao", "value"), Output("extrato-valor", "value"), Output("extrato-conta", "value"), Input("extrato-table", "selected_rows"), State("extrato-table", "data"), prevent_initial_call=True)
    def select_extrato(rows, data):
        if not rows:
            return "", "", "", "", None
        item = data[rows[0]]
        return item["id"], item["data"], item["descricao"], item["valor"], item["conta_corrente_id"]

    @app.callback(Output("conc-lancamento", "options"), Output("conc-lanc-table", "data"), Input("conc-extrato-table", "selected_rows"), Input("conc-filtro-conta", "value"), State("conc-extrato-table", "data"), prevent_initial_call=True)
    def fill_conc_options(rows, conta, extrato_data):
        conta_id = conta
        if rows:
            conta_id = extrato_data[rows[0]]["conta_corrente_id"]
        lancamentos = services.list_lancamentos(conta_id=conta_id)
        options = [{"label": f"#{item['id']} {item['data']} - {item['descricao']} - {item['valor_label']}", "value": item["id"]} for item in lancamentos]
        return options, lancamentos

    @app.callback(Output("conciliacao-msg", "children"), Output("conc-extrato-table", "data"), Input("conciliar-btn", "n_clicks"), State("conc-extrato-table", "selected_rows"), State("conc-extrato-table", "data"), State("conc-lancamento", "value"), prevent_initial_call=True)
    def conciliar(_, rows, extratos, lancamento_id):
        try:
            if not rows:
                raise ValueError("Selecione um item de extrato para conciliar.")
            services.conciliar_extrato(extratos[rows[0]]["id"], lancamento_id)
            return "Extrato conciliado com sucesso.", services.list_extrato(status="NAO")
        except Exception as exc:
            return str(exc), services.list_extrato(status="NAO")

    @app.callback(Output("padrao-id", "value"), Output("padrao-descricao", "value"), Output("padrao-categoria", "value"), Output("padrao-subcategoria", "value"), Output("padrao-centro", "value"), Input("padroes-table", "selected_rows"), State("padroes-table", "data"), prevent_initial_call=True)
    def select_padrao(rows, data):
        if not rows:
            return "", "", None, None, None
        item = data[rows[0]]
        return item["id"], item["descricao_padrao"], item["categoria_id"], item["subcategoria_id"], item["centro_custo_id"]

    @app.callback(Output("padroes-msg", "children"), Output("padroes-table", "data"), Output("padrao-id", "value"), Output("padrao-descricao", "value"), Input("padrao-add", "n_clicks"), Input("padrao-edit", "n_clicks"), Input("padrao-delete", "n_clicks"), State("padrao-id", "value"), State("padrao-descricao", "value"), State("padrao-categoria", "value"), State("padrao-subcategoria", "value"), State("padrao-centro", "value"), prevent_initial_call=True)
    def manage_padroes(_, __, ___, padrao_id, descricao, categoria, subcategoria, centro):
        action = callback_context.triggered_id
        try:
            if action == "padrao-add":
                services.save_padrao(None, descricao, categoria, subcategoria, centro)
                msg = "Padrao incluido com sucesso."
            elif action == "padrao-edit":
                services.save_padrao(padrao_id, descricao, categoria, subcategoria, centro)
                msg = "Padrao editado com sucesso."
            elif action == "padrao-delete":
                services.delete_padrao(padrao_id)
                msg = "Padrao excluido com sucesso."
            else:
                return no_update, no_update, no_update, no_update
            return msg, services.list_padroes(), "", ""
        except Exception as exc:
            return str(exc), services.list_padroes(), padrao_id, descricao

    _dash_app = app
    return app








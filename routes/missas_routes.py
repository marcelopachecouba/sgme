from flask import Blueprint, render_template, redirect, request, send_file, url_for, flash
from flask_login import login_required, current_user
from models import CasalMinisterio, db, Missa, Escala
from datetime import datetime, date
import calendar
from utils.auth import admin_required
from services.paroquia_scope_service import get_missa_or_404
from services.escala_imagem_service import gerar_imagem_calendario_escala
from services.public_url_service import build_public_url

missas_bp = Blueprint("missas", __name__)


def _normalizar_periodo(periodo, horario=None):
    valor = (periodo or "").strip().lower()
    if valor in {"manha", "tarde", "noite"}:
        return valor

    if horario:
        try:
            hora = int(horario.split(":", 1)[0])
            if hora < 12:
                return "manha"
            if hora < 18:
                return "tarde"
            return "noite"
        except Exception:
            pass

    return None


def _ler_data_parametro(valor):
    texto = (valor or "").strip()
    if not texto:
        return None, ""

    try:
        return datetime.strptime(texto, "%Y-%m-%d").date(), texto
    except ValueError:
        return None, ""


def _iterar_meses(inicio, fim):
    atual = date(inicio.year, inicio.month, 1)
    limite = date(fim.year, fim.month, 1)

    while atual <= limite:
        yield atual.year, atual.month
        if atual.month == 12:
            atual = date(atual.year + 1, 1, 1)
        else:
            atual = date(atual.year, atual.month + 1, 1)


def _montar_calendario_periodo(ano, mes, data_inicio, data_fim):
    semanas_base = calendar.monthcalendar(ano, mes)
    semanas_filtradas = []

    for semana in semanas_base:
        semana_filtrada = []
        possui_dia_no_periodo = False
        for dia in semana:
            if not dia:
                semana_filtrada.append(0)
                continue

            data_atual = date(ano, mes, dia)
            if data_inicio <= data_atual <= data_fim:
                semana_filtrada.append(dia)
                possui_dia_no_periodo = True
            else:
                semana_filtrada.append(0)

        if possui_dia_no_periodo:
            semanas_filtradas.append(semana_filtrada)

    colunas_visiveis = []
    for indice in range(7):
        if any(semana[indice] != 0 for semana in semanas_filtradas):
            colunas_visiveis.append(indice)

    if not colunas_visiveis:
        colunas_visiveis = list(range(7))

    semanas_visiveis = [
        [semana[indice] for indice in colunas_visiveis]
        for semana in semanas_filtradas
    ]

    return {
        "cal": semanas_visiveis,
        "colunas_visiveis": colunas_visiveis,
    }

@missas_bp.route("/missas")
@login_required
def missas():
    hoje = date.today()
    data_inicial_str = (request.args.get("data_inicial") or "").strip()
    data_final_str = (request.args.get("data_final") or "").strip()
    comunidade_filtro = (request.args.get("comunidade") or "").strip()

    try:
        data_inicial = datetime.strptime(data_inicial_str, "%Y-%m-%d").date() if data_inicial_str else hoje
    except ValueError:
        data_inicial = hoje
        data_inicial_str = hoje.strftime("%Y-%m-%d")

    try:
        data_final = datetime.strptime(data_final_str, "%Y-%m-%d").date() if data_final_str else None
    except ValueError:
        data_final = None
        data_final_str = ""

    query = Missa.query.filter(
        Missa.id_paroquia == current_user.id_paroquia,
        Missa.data >= data_inicial,
    )

    if data_final:
        query = query.filter(Missa.data <= data_final)

    if comunidade_filtro:
        query = query.filter(Missa.comunidade.ilike(f"%{comunidade_filtro}%"))

    lista = query.order_by(Missa.data.asc(), Missa.horario.asc(), Missa.id.asc()).all()
    for missa in lista:
        missa.periodo_exibicao = _normalizar_periodo(missa.periodo, missa.horario) or "-"
    return render_template(
        "missas.html",
        missas=lista,
        data_inicial=data_inicial_str or hoje.strftime("%Y-%m-%d"),
        data_final=data_final_str,
        comunidade_filtro=comunidade_filtro,
        link_publico_escala=build_public_url("publico.calendario_paroquia", id=current_user.id_paroquia),
    )


@missas_bp.route("/missas/calendario")
@login_required
def calendario_missas():
    hoje = date.today()
    mes = int(request.args.get("mes", hoje.month))
    ano = int(request.args.get("ano", hoje.year))
    data_inicio, data_inicio_str = _ler_data_parametro(request.args.get("data_inicio"))
    data_fim, data_fim_str = _ler_data_parametro(request.args.get("data_fim"))

    modo_periodo = bool(data_inicio or data_fim)
    if modo_periodo:
        if not data_inicio and data_fim:
            data_inicio = data_fim
            data_inicio_str = data_fim_str
        if not data_fim and data_inicio:
            data_fim = data_inicio
            data_fim_str = data_inicio_str
        if data_inicio and data_fim and data_fim < data_inicio:
            data_inicio, data_fim = data_fim, data_inicio
            data_inicio_str = data_inicio.strftime("%Y-%m-%d")
            data_fim_str = data_fim.strftime("%Y-%m-%d")
    else:
        data_inicio_str = ""
        data_fim_str = ""

    cal = calendar.monthcalendar(ano, mes)

    query = Missa.query.filter(Missa.id_paroquia == current_user.id_paroquia)
    if modo_periodo and data_inicio and data_fim:
        query = query.filter(Missa.data >= data_inicio, Missa.data <= data_fim)
    else:
        query = query.filter(
            db.extract("month", Missa.data) == mes,
            db.extract("year", Missa.data) == ano
        )

    missas = query.order_by(Missa.data.asc(), Missa.horario.asc(), Missa.id.asc()).all()
    missas_ids = [m.id for m in missas]

    casal_map = {}
    casais = CasalMinisterio.query.filter_by(
        id_paroquia=current_user.id_paroquia,
        ativo=True
    ).all()
    for c in casais:
        casal_map[c.id_ministro_1] = c.id_ministro_2
        casal_map[c.id_ministro_2] = c.id_ministro_1

    escalas_por_missa = {}
    if missas_ids:
        escalas = Escala.query.filter(
            Escala.id_paroquia == current_user.id_paroquia,
            Escala.id_missa.in_(missas_ids)
        ).all()
        for e in escalas:
            escalas_por_missa.setdefault(e.id_missa, []).append(e)

    estrutura = {}
    estrutura_impressao = {}
    calendarios_periodo = []
    estruturas_periodo = {}

    if modo_periodo and data_inicio and data_fim:
        for ano_mes, mes_mes in _iterar_meses(data_inicio, data_fim):
            calendario_periodo = _montar_calendario_periodo(ano_mes, mes_mes, data_inicio, data_fim)
            estruturas_periodo[(ano_mes, mes_mes)] = {}
            calendarios_periodo.append({
                "ano": ano_mes,
                "mes": mes_mes,
                "cal": calendario_periodo["cal"],
                "colunas_visiveis": calendario_periodo["colunas_visiveis"],
                "estrutura": estruturas_periodo[(ano_mes, mes_mes)],
            })

    for missa in missas:
        dia = missa.data.day

        if dia not in estrutura:
            estrutura[dia] = []

        escalas = escalas_por_missa.get(missa.id, [])
        
        ministros = []
        ministros_ids = set()
        for e in escalas:
            if e.ministro:
                ministros_ids.add(e.ministro.id)

        for e in escalas:
            if e.ministro:
               parceiro_id = casal_map.get(e.ministro.id)
               ministros.append({
                   "nome": e.ministro.nome,
                   "eh_casal": bool(parceiro_id and parceiro_id in ministros_ids)
               })

        periodo_exibicao = _normalizar_periodo(missa.periodo, missa.horario) or "-"
        item_missa = {
            "id": missa.id,
            "data": missa.data,
            "horario": missa.horario,
            "periodo": periodo_exibicao,
            "comunidade": missa.comunidade,
            "ministros": ministros
        }

        estrutura[dia].append(item_missa)

        if modo_periodo:
            estrutura_mes = estruturas_periodo.setdefault((missa.data.year, missa.data.month), {})
            estrutura_mes.setdefault(missa.data.day, []).append(item_missa)
        else:
            semana_mes = ((missa.data.day - 1) // 7) + 1
            chave = (missa.data.weekday(), missa.horario or "", periodo_exibicao)
            if chave not in estrutura_impressao:
                estrutura_impressao[chave] = {
                    "dia_semana": missa.data.weekday(),
                    "horario": missa.horario,
                    "periodo": periodo_exibicao,
                    "semanas": {},
                    "max_ministros": 0,
                }

            estrutura_impressao[chave]["semanas"][semana_mes] = {
                "data": missa.data,
                "ministros": [m["nome"] for m in ministros],
            }
            estrutura_impressao[chave]["max_ministros"] = max(
                estrutura_impressao[chave]["max_ministros"],
                len(ministros)
            )

    grupos_impressao = sorted(
        estrutura_impressao.values(),
        key=lambda g: (g["dia_semana"], g["horario"] or "", g["periodo"] or "")
    )

    return render_template(
        "calendario_missas.html",
        cal=cal,
        estrutura=estrutura,
        grupos_impressao=grupos_impressao,
        calendarios_periodo=calendarios_periodo,
        mes=mes,
        ano=ano,
        modo_periodo=modo_periodo,
        data_inicio=data_inicio_str,
        data_fim=data_fim_str,
    )


@missas_bp.route("/missas/calendario/imagem")
@login_required
@admin_required
def calendario_missas_imagem():
    hoje = date.today()
    mes = int(request.args.get("mes", hoje.month))
    ano = int(request.args.get("ano", hoje.year))
    cal = calendar.monthcalendar(ano, mes)

    missas = Missa.query.filter(
        Missa.id_paroquia == current_user.id_paroquia,
        db.extract("month", Missa.data) == mes,
        db.extract("year", Missa.data) == ano
    ).all()
    missas_ids = [m.id for m in missas]

    escalas_por_missa = {}
    if missas_ids:
        escalas = Escala.query.filter(
            Escala.id_paroquia == current_user.id_paroquia,
            Escala.id_missa.in_(missas_ids)
        ).all()
        for e in escalas:
            escalas_por_missa.setdefault(e.id_missa, []).append(e)

    estrutura = {}
    for missa in missas:
        dia = missa.data.day
        estrutura.setdefault(dia, [])
        estrutura[dia].append({
            "id": missa.id,
            "horario": missa.horario,
            "periodo": _normalizar_periodo(missa.periodo, missa.horario) or "-",
            "comunidade": missa.comunidade,
            "ministros": [
                {"nome": e.ministro.nome}
                for e in escalas_por_missa.get(missa.id, [])
                if e.ministro and e.ministro.nome
            ],
        })

    arquivo = gerar_imagem_calendario_escala(mes=mes, ano=ano, cal=cal, estrutura=estrutura)
    nome_arquivo = f"calendario-escala-{ano:04d}-{mes:02d}.png"
    return send_file(arquivo, mimetype="image/png", download_name=nome_arquivo, as_attachment=False)


@missas_bp.route("/missas/calendario/imagem-periodo")
@login_required
@admin_required
def calendario_missas_imagem_periodo():
    data_inicio, data_inicio_str = _ler_data_parametro(request.args.get("data_inicio"))
    data_fim, data_fim_str = _ler_data_parametro(request.args.get("data_fim"))

    if not data_inicio and not data_fim:
        flash("Informe o periodo para gerar a imagem da escala.", "warning")
        return redirect(url_for("missas.calendario_missas"))

    if not data_inicio:
        data_inicio = data_fim
        data_inicio_str = data_fim_str
    if not data_fim:
        data_fim = data_inicio
        data_fim_str = data_inicio_str
    if data_fim < data_inicio:
        data_inicio, data_fim = data_fim, data_inicio
        data_inicio_str = data_inicio.strftime("%Y-%m-%d")
        data_fim_str = data_fim.strftime("%Y-%m-%d")

    missas = Missa.query.filter(
        Missa.id_paroquia == current_user.id_paroquia,
        Missa.data >= data_inicio,
        Missa.data <= data_fim,
    ).order_by(Missa.data.asc(), Missa.horario.asc(), Missa.id.asc()).all()
    missas_ids = [m.id for m in missas]

    escalas_por_missa = {}
    if missas_ids:
        escalas = Escala.query.filter(
            Escala.id_paroquia == current_user.id_paroquia,
            Escala.id_missa.in_(missas_ids)
        ).all()
        for e in escalas:
            escalas_por_missa.setdefault(e.id_missa, []).append(e)

    calendarios_periodo = []
    estruturas_periodo = {}
    for ano_mes, mes_mes in _iterar_meses(data_inicio, data_fim):
        calendario_periodo = _montar_calendario_periodo(ano_mes, mes_mes, data_inicio, data_fim)
        estruturas_periodo[(ano_mes, mes_mes)] = {}
        calendarios_periodo.append({
            "ano": ano_mes,
            "mes": mes_mes,
            "cal": calendario_periodo["cal"],
            "colunas_visiveis": calendario_periodo["colunas_visiveis"],
            "estrutura": estruturas_periodo[(ano_mes, mes_mes)],
        })

    for missa in missas:
        estrutura_mes = estruturas_periodo.setdefault((missa.data.year, missa.data.month), {})
        estrutura_mes.setdefault(missa.data.day, []).append({
            "id": missa.id,
            "horario": missa.horario,
            "periodo": _normalizar_periodo(missa.periodo, missa.horario) or "-",
            "comunidade": missa.comunidade,
            "ministros": [
                {"nome": e.ministro.nome}
                for e in escalas_por_missa.get(missa.id, [])
                if e.ministro and e.ministro.nome
            ],
        })

    arquivo = gerar_imagem_calendario_escala(
        mes=None,
        ano=None,
        cal=None,
        estrutura=None,
        calendarios_periodo=calendarios_periodo,
        titulo_periodo=(data_inicio, data_fim),
    )
    nome_arquivo = f"calendario-escala-periodo-{data_inicio.strftime('%Y%m%d')}-{data_fim.strftime('%Y%m%d')}.png"
    return send_file(arquivo, mimetype="image/png", download_name=nome_arquivo, as_attachment=False)

from utils.auth import admin_required
@missas_bp.route("/missas/nova", methods=["GET", "POST"])
@login_required
@admin_required
def nova_missa():
    if request.method == "POST":
        data = datetime.strptime(request.form["data"], "%Y-%m-%d")
        horario = request.form["horario"]
        periodo = _normalizar_periodo(request.form.get("periodo"), horario)
        comunidade = request.form["comunidade"]
        qtd = request.form["qtd"]

        missa = Missa(
            data=data,
            horario=horario,
            periodo=periodo,
            comunidade=comunidade,
            qtd_ministros=qtd,
            id_paroquia=current_user.id_paroquia
        )

        db.session.add(missa)
        db.session.commit()
        return redirect(url_for("missas.missas"))

    return render_template("nova_missa.html")


from utils.auth import admin_required
@missas_bp.route("/missas/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required

def editar_missa(id):

    missa = get_missa_or_404(id, current_user.id_paroquia)

    if request.method == "POST":

        missa.data = datetime.strptime(request.form["data"], "%Y-%m-%d")
        missa.horario = request.form["horario"]
        missa.periodo = _normalizar_periodo(request.form.get("periodo"), missa.horario)
        missa.comunidade = request.form["comunidade"]
        missa.qtd_ministros = int(request.form["qtd"])

        db.session.commit()

        flash("Missa atualizada com sucesso!")
        return redirect(url_for("missas.missas"))

    missa.periodo_exibicao = _normalizar_periodo(missa.periodo, missa.horario)
    return render_template("editar_missa.html", missa=missa)

from utils.auth import admin_required
@missas_bp.route("/missas/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_missa(id):

    missa = get_missa_or_404(id, current_user.id_paroquia)

    # Remove escalas vinculadas primeiro
    Escala.query.filter_by(id_missa=missa.id).delete()

    db.session.delete(missa)
    db.session.commit()

    flash("Missa excluída com sucesso!")
    return redirect(url_for("missas.missas"))



@missas_bp.route("/missas/visao")
@login_required
def visao_missas():

    missas = Missa.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Missa.data, Missa.horario).all()

    missas_ids = [m.id for m in missas]
    ministros_por_missa = {}
    if missas_ids:
        escalas = Escala.query.filter(
            Escala.id_paroquia == current_user.id_paroquia,
            Escala.id_missa.in_(missas_ids)
        ).order_by(Escala.id.asc()).all()

        for escala in escalas:
            if not escala.ministro:
                continue
            ministros_por_missa.setdefault(escala.id_missa, []).append(escala.ministro.nome)

    estrutura = {}

    for missa in missas:
        missa.ministros_nomes = ministros_por_missa.get(missa.id, [])
        missa.periodo_exibicao = _normalizar_periodo(missa.periodo, missa.horario) or "-"

        data = missa.data
        semana = (data.day - 1) // 7 + 1
        dia_semana = data.weekday()  # 0=segunda
        horario = missa.horario

        if semana not in estrutura:
            estrutura[semana] = {}

        if dia_semana not in estrutura[semana]:
            estrutura[semana][dia_semana] = {}

        if horario not in estrutura[semana][dia_semana]:
            estrutura[semana][dia_semana][horario] = []

        estrutura[semana][dia_semana][horario].append(missa)

    return render_template(
        "visao_missas.html",
        estrutura=estrutura
    )

# ======================
# ESCALA MANUAL
# ======================

from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_required, current_user
from models import CasalMinisterio, db, Missa, Escala
from datetime import datetime, date
import calendar
from utils.auth import admin_required
from services.paroquia_scope_service import get_missa_or_404

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

@missas_bp.route("/missas")
@login_required
def missas():
    lista = Missa.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Missa.data.asc(), Missa.horario.asc(), Missa.id.asc()).all()
    for missa in lista:
        missa.periodo_exibicao = _normalizar_periodo(missa.periodo, missa.horario) or "-"
    return render_template("missas.html", missas=lista)


@missas_bp.route("/missas/calendario")
@login_required
def calendario_missas():

    hoje = date.today()

    mes = int(request.args.get("mes", hoje.month))
    ano = int(request.args.get("ano", hoje.year))

    cal = calendar.monthcalendar(ano, mes)

    missas = Missa.query.filter(
        Missa.id_paroquia == current_user.id_paroquia,
        db.extract("month", Missa.data) == mes,
        db.extract("year", Missa.data) == ano
    ).all()

    casal_map = {}
    casais = CasalMinisterio.query.filter_by(
        id_paroquia=current_user.id_paroquia,
        ativo=True
    ).all()
    for c in casais:
        casal_map[c.id_ministro_1] = c.id_ministro_2
        casal_map[c.id_ministro_2] = c.id_ministro_1

    estrutura = {}
    estrutura_impressao = {}

    for missa in missas:

        dia = missa.data.day

        if dia not in estrutura:
            estrutura[dia] = []

        escalas = Escala.query.filter_by(id_missa=missa.id).all()
        
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

        estrutura[dia].append({
            "horario": missa.horario,
            "periodo": periodo_exibicao,
            "comunidade": missa.comunidade,
            "ministros": ministros
        })

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
        mes=mes,
        ano=ano
    )

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

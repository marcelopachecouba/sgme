from collections import defaultdict
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import extract
from werkzeug.utils import secure_filename

from models import (
    Ministro,
    PresencaReuniao,
    ReuniaoFormacao,
    Presenca,
    Missa,
    db
)

from services.firebase_storage_service import upload_arquivo
from utils.auth import admin_required


presencas_bp = Blueprint("presencas", __name__)


# ---------------------------------------------------------
# FUNÇÕES AUXILIARES
# ---------------------------------------------------------

def _parse_data(valor):
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _listar_ministros_paroquia():
    return Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Ministro.nome.asc()).all()


def _salvar_upload(campo_arquivo):

    arquivo = request.files.get(campo_arquivo)

    if not arquivo or arquivo.filename == "":
        return None

    nome_original = secure_filename(arquivo.filename)

    if not nome_original:
        return None

    arquivo.stream.seek(0)

    return upload_arquivo(arquivo)


# ---------------------------------------------------------
# CHECKIN AUTOMÁTICO DA MISSA
# ---------------------------------------------------------

@presencas_bp.route("/checkin/<int:missa_id>")
@login_required
def checkin_missa(missa_id):

    missa = Missa.query.filter_by(
        id=missa_id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()

    presenca = Presenca.query.filter_by(
        ministro_id=current_user.id,
        id_missa=missa_id
    ).first()

    if not presenca:

        presenca = Presenca(
            ministro_id=current_user.id,
            id_missa=missa_id,
            presente=True
        )

        db.session.add(presenca)

    else:

        presenca.presente = True

    db.session.commit()

    flash("Presença confirmada.")

    return redirect("/minhas-escalas")


# ---------------------------------------------------------
# HISTÓRICO DO MINISTRO
# ---------------------------------------------------------

@presencas_bp.route("/historico-presencas")
@login_required
def historico_presencas():

    presencas = db.session.query(
        Presenca,
        Missa
    ).join(
        Missa,
        Presenca.missa_id == Missa.id
    ).filter(
        Presenca.ministro_id == current_user.id
    ).order_by(
        Missa.data.desc()
    ).all()

    return render_template(
        "historico_presencas.html",
        presencas=presencas
    )


# ---------------------------------------------------------
# LISTAR PRESENÇAS DE REUNIÕES
# ---------------------------------------------------------

@presencas_bp.route("/presencas")
@login_required
def listar_presencas():

    reunioes = ReuniaoFormacao.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(
        ReuniaoFormacao.data.desc(),
        ReuniaoFormacao.id.desc()
    ).all()

    return render_template(
        "presencas.html",
        reunioes=reunioes
    )


# ---------------------------------------------------------
# RELATÓRIO DE PRESENÇAS
# ---------------------------------------------------------

@presencas_bp.route("/presencas/relatorio")
@login_required
def relatorio_presencas():

    ano_atual = datetime.utcnow().year
    ano = request.args.get("ano", type=int) or ano_atual

    anos_rows = db.session.query(
        extract("year", ReuniaoFormacao.data)
    ).filter(
        ReuniaoFormacao.id_paroquia == current_user.id_paroquia
    ).distinct().order_by(
        extract("year", ReuniaoFormacao.data).desc()
    ).all()

    anos_disponiveis = sorted(
        {
            int(row[0])
            for row in anos_rows
            if row and row[0] is not None
        },
        reverse=True
    )

    if ano not in anos_disponiveis:
        anos_disponiveis = sorted({ano, *anos_disponiveis}, reverse=True)

    ministros = _listar_ministros_paroquia()

    reunioes_ano = ReuniaoFormacao.query.filter(
        ReuniaoFormacao.id_paroquia == current_user.id_paroquia,
        extract("year", ReuniaoFormacao.data) == ano
    ).order_by(
        ReuniaoFormacao.data.asc(),
        ReuniaoFormacao.id.asc()
    ).all()

    datas = sorted({r.data for r in reunioes_ano})

    presencas_rows = db.session.query(
        PresencaReuniao.id_ministro,
        ReuniaoFormacao.data
    ).join(
        ReuniaoFormacao,
        PresencaReuniao.id_reuniao == ReuniaoFormacao.id
    ).filter(
        PresencaReuniao.id_paroquia == current_user.id_paroquia,
        ReuniaoFormacao.id_paroquia == current_user.id_paroquia,
        PresencaReuniao.presente.is_(True),
        extract("year", ReuniaoFormacao.data) == ano
    ).all()

    presenca_map = defaultdict(set)

    for ministro_id, data in presencas_rows:
        presenca_map[ministro_id].add(data)

    return render_template(
        "presencas_relatorio.html",
        ano=ano,
        anos_disponiveis=anos_disponiveis,
        datas=datas,
        ministros=ministros,
        presenca_map=presenca_map
    )


# ---------------------------------------------------------
# IMPRIMIR LISTA DE PRESENÇA
# ---------------------------------------------------------

@presencas_bp.route("/presencas/imprimir/<int:reuniao_id>")
@login_required
def imprimir_presenca(reuniao_id):

    reuniao = ReuniaoFormacao.query.filter_by(
        id=reuniao_id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()

    ministros_presentes = sorted(
        [
            p.ministro.nome
            for p in reuniao.presencas
            if p.presente and p.ministro and p.ministro.nome
        ],
        key=lambda nome: nome.lower()
    )

    return render_template(
        "presenca_impressao.html",
        reuniao=reuniao,
        ministros_presentes=ministros_presentes
    )


# ---------------------------------------------------------
# NOVA PRESENÇA
# ---------------------------------------------------------

@presencas_bp.route("/presencas/nova", methods=["GET", "POST"])
@login_required
@admin_required
def nova_presenca():

    ministros = _listar_ministros_paroquia()

    if request.method == "POST":

        data_evento = _parse_data(request.form.get("data"))
        assunto = (request.form.get("assunto") or "").strip()
        tipo = (request.form.get("tipo") or "reuniao").strip()
        observacao = (request.form.get("observacao") or "").strip() or None
        video_url = (request.form.get("video_url") or "").strip() or None

        presentes_ids = {
            int(x)
            for x in request.form.getlist("presentes")
            if x.isdigit()
        }

        if not data_evento or not assunto:

            flash("Informe data e assunto.")

            return render_template(
                "presenca_form.html",
                ministros=ministros,
                reuniao=None
            )

        reuniao = ReuniaoFormacao(
            data=data_evento,
            assunto=assunto,
            tipo=tipo if tipo in {"reuniao", "formacao"} else "reuniao",
            observacao=observacao,
            video_url=video_url,
            id_paroquia=current_user.id_paroquia
        )

        try:

            reuniao.foto_url = _salvar_upload("foto")
            reuniao.video_arquivo_url = _salvar_upload("video_arquivo")

        except Exception:

            flash("Erro ao enviar arquivos para o Firebase.")

            return render_template(
                "presenca_form.html",
                ministros=ministros,
                reuniao=None
            )

        db.session.add(reuniao)
        db.session.flush()

        ministros_validos = {m.id for m in ministros}

        for ministro_id in presentes_ids.intersection(ministros_validos):

            db.session.add(
                PresencaReuniao(
                    id_reuniao=reuniao.id,
                    id_ministro=ministro_id,
                    id_paroquia=current_user.id_paroquia,
                    presente=True
                )
            )

        db.session.commit()

        flash("Presença registrada.")

        return redirect(url_for("presencas.listar_presencas"))

    return render_template(
        "presenca_form.html",
        ministros=ministros,
        reuniao=None
    )


# ---------------------------------------------------------
# EXCLUIR PRESENÇA
# ---------------------------------------------------------

@presencas_bp.route("/presencas/excluir/<int:reuniao_id>", methods=["POST"])
@login_required
@admin_required
def excluir_presenca(reuniao_id):

    reuniao = ReuniaoFormacao.query.filter_by(
        id=reuniao_id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()

    db.session.delete(reuniao)
    db.session.commit()

    flash("Registro de presença excluído.")

    return redirect(url_for("presencas.listar_presencas"))

import math
from collections import defaultdict
from datetime import date, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import extract
from werkzeug.utils import secure_filename

from models import (
    Ministro,
    PresencaReuniao,
    ReuniaoFormacao,
    Presenca,
    Missa,
    Escala,
    db
)

from services.firebase_storage_service import upload_arquivo
from services.firebase_service import enviar_push
from services.public_url_service import build_public_url
from services.whatsapp_service import gerar_link_whatsapp_telefone
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


def _obter_reuniao_or_404(reuniao_id):
    return ReuniaoFormacao.query.filter_by(
        id=reuniao_id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()


def _link_confirmacao_reuniao(reuniao, ministro):
    return build_public_url(
        "presencas.checkin_reuniao_publico_localizacao",
        reuniao_id=reuniao.id,
        token_publico=ministro.token_publico,
    )


def _mensagem_confirmacao_reuniao(reuniao, ministro, link_confirmacao):
    tipo = "Formacao" if reuniao.tipo == "formacao" else "Reuniao"
    return (
        f"Olá {ministro.nome},\n\n"
        f"Segue o link para confirmar sua presenca.\n\n"
        f"{tipo}: {reuniao.assunto}\n"
        f"Data: {reuniao.data.strftime('%d/%m/%Y')}\n\n"
        f"Confirmar presenca:\n{link_confirmacao}"
    )


def _salvar_upload(campo_arquivo):

    arquivo = request.files.get(campo_arquivo)

    if not arquivo or arquivo.filename == "":
        return None

    nome_original = secure_filename(arquivo.filename)

    if not nome_original:
        return None

    arquivo.stream.seek(0)

    return upload_arquivo(arquivo)


def _distancia_metros(lat1, lon1, lat2, lon2):
    raio_terra = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return raio_terra * c


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

    escala = Escala.query.filter_by(
        id_missa=missa_id,
        id_ministro=current_user.id,
        id_paroquia=current_user.id_paroquia
    ).first()

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

    if escala:
        escala.confirmado = True
        escala.presente = True

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


@presencas_bp.route("/presencas/links/<int:reuniao_id>")
@login_required
@admin_required
def links_confirmacao_reuniao(reuniao_id):

    reuniao = _obter_reuniao_or_404(reuniao_id)

    ministros = _listar_ministros_paroquia()
    links_ministros = []

    for ministro in ministros:
        link = _link_confirmacao_reuniao(reuniao, ministro)
        whatsapp_link = None
        if ministro.telefone:
            whatsapp_link = gerar_link_whatsapp_telefone(
                ministro.telefone,
                _mensagem_confirmacao_reuniao(reuniao, ministro, link),
            )

        links_ministros.append({
            "ministro": ministro,
            "link": link,
            "whatsapp_link": whatsapp_link,
            "tem_push": bool(ministro.firebase_token),
        })

    return render_template(
        "presencas_links.html",
        reuniao=reuniao,
        links_ministros=links_ministros
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
        latitude = (request.form.get("latitude") or "").strip() or None
        longitude = (request.form.get("longitude") or "").strip() or None

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
            latitude=latitude,
            longitude=longitude,
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


@presencas_bp.route("/presencas/editar/<int:reuniao_id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_presenca(reuniao_id):

    reuniao = _obter_reuniao_or_404(reuniao_id)
    ministros = _listar_ministros_paroquia()

    if request.method == "POST":
        data_evento = _parse_data(request.form.get("data"))
        assunto = (request.form.get("assunto") or "").strip()
        tipo = (request.form.get("tipo") or "reuniao").strip()
        observacao = (request.form.get("observacao") or "").strip() or None
        video_url = (request.form.get("video_url") or "").strip() or None
        latitude = (request.form.get("latitude") or "").strip() or None
        longitude = (request.form.get("longitude") or "").strip() or None

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
                reuniao=reuniao,
                presentes_ids=presentes_ids,
            )

        reuniao.data = data_evento
        reuniao.assunto = assunto
        reuniao.tipo = tipo if tipo in {"reuniao", "formacao"} else "reuniao"
        reuniao.observacao = observacao
        reuniao.video_url = None if request.form.get("remover_video_url") else video_url
        reuniao.latitude = latitude
        reuniao.longitude = longitude

        if request.form.get("remover_foto"):
            reuniao.foto_url = None

        if request.form.get("remover_video_arquivo"):
            reuniao.video_arquivo_url = None

        try:
            nova_foto = _salvar_upload("foto")
            if nova_foto:
                reuniao.foto_url = nova_foto

            novo_video_arquivo = _salvar_upload("video_arquivo")
            if novo_video_arquivo:
                reuniao.video_arquivo_url = novo_video_arquivo
        except Exception:
            flash("Erro ao enviar arquivos para o Firebase.")
            return render_template(
                "presenca_form.html",
                ministros=ministros,
                reuniao=reuniao,
                presentes_ids=presentes_ids,
            )

        ministros_validos = {m.id for m in ministros}
        PresencaReuniao.query.filter_by(
            id_reuniao=reuniao.id,
            id_paroquia=current_user.id_paroquia
        ).delete(synchronize_session=False)

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

        flash("Registro de presenca atualizado.")
        return redirect(url_for("presencas.listar_presencas"))

    presentes_ids = {
        p.id_ministro
        for p in reuniao.presencas
        if p.presente
    }

    return render_template(
        "presenca_form.html",
        ministros=ministros,
        reuniao=reuniao,
        presentes_ids=presentes_ids,
    )


@presencas_bp.route("/presencas/checkin/<int:reuniao_id>/<token_publico>", methods=["GET", "POST"])
def checkin_reuniao_publico_localizacao(reuniao_id, token_publico):

    reuniao = ReuniaoFormacao.query.filter_by(id=reuniao_id).first_or_404()
    ministro = Ministro.query.filter_by(
        token_publico=token_publico,
        id_paroquia=reuniao.id_paroquia
    ).first_or_404()

    if request.method == "POST":
        payload = request.get_json(silent=True) or request.form
        latitude = payload.get("latitude")
        longitude = payload.get("longitude")

        if reuniao.data != date.today():
            return jsonify(
                ok=False,
                mensagem=(
                    f"Este link so pode confirmar presenca na data da reuniao "
                    f"({reuniao.data.strftime('%d/%m/%Y')})."
                )
            ), 400

        if not reuniao.latitude or not reuniao.longitude:
            return jsonify(
                ok=False,
                mensagem="Esta reuniao nao possui localizacao cadastrada."
            ), 400

        try:
            lat_usuario = float(latitude)
            lon_usuario = float(longitude)
            lat_reuniao = float(reuniao.latitude)
            lon_reuniao = float(reuniao.longitude)
        except (TypeError, ValueError):
            return jsonify(ok=False, mensagem="Localizacao invalida."), 400

        distancia = _distancia_metros(
            lat_usuario,
            lon_usuario,
            lat_reuniao,
            lon_reuniao
        )
        raio_maximo = 300

        if distancia > raio_maximo:
            return jsonify(
                ok=False,
                mensagem=(
                    f"Voce esta a {int(distancia)}m da reuniao. "
                    f"Aproximacao maxima: {raio_maximo}m."
                )
            ), 400

        presenca = PresencaReuniao.query.filter_by(
            id_reuniao=reuniao.id,
            id_ministro=ministro.id,
            id_paroquia=reuniao.id_paroquia
        ).first()

        if not presenca:
            presenca = PresencaReuniao(
                id_reuniao=reuniao.id,
                id_ministro=ministro.id,
                id_paroquia=reuniao.id_paroquia,
                presente=True
            )
            db.session.add(presenca)
        else:
            presenca.presente = True

        db.session.commit()

        return jsonify(
            ok=True,
            mensagem=(
                f"Presenca confirmada para {ministro.nome} em "
                f"{reuniao.data.strftime('%d/%m/%Y')}."
            )
        )

    return render_template(
        "checkin_reuniao_publico.html",
        reuniao=reuniao,
        ministro=ministro
    )


@presencas_bp.route("/presencas/links/<int:reuniao_id>/push/<int:ministro_id>", methods=["POST"])
@login_required
@admin_required
def enviar_push_confirmacao_reuniao(reuniao_id, ministro_id):

    reuniao = _obter_reuniao_or_404(reuniao_id)
    ministro = Ministro.query.filter_by(
        id=ministro_id,
        id_paroquia=current_user.id_paroquia
    ).first_or_404()

    if not ministro.firebase_token:
        flash(f"{ministro.nome} nao possui token de push cadastrado.")
        return redirect(url_for("presencas.links_confirmacao_reuniao", reuniao_id=reuniao.id))

    link = _link_confirmacao_reuniao(reuniao, ministro)
    tipo = "Formacao" if reuniao.tipo == "formacao" else "Reuniao"

    enviar_push(
        ministro.firebase_token,
        f"Confirmacao de Presenca - {tipo}",
        (
            f"{reuniao.assunto} em {reuniao.data.strftime('%d/%m/%Y')}. "
            "Toque para abrir o link de confirmacao."
        ),
        url=link,
    )

    flash(f"Push enviado para {ministro.nome}.")
    return redirect(url_for("presencas.links_confirmacao_reuniao", reuniao_id=reuniao.id))


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

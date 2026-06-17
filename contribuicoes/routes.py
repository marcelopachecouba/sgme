from datetime import datetime
from flask import current_app
from flask import flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import login_required

from contribuicoes import contribuicoes_bp
from extensions import db
from models import Comunidade

from .models import CategoriaContribuicao, Contribuicao, Dizimista
from .services import (
    ContribuicaoError,
    buscar_dizimista_por_cpf,
    consulta_relatorio,
    criar_ou_atualizar_dizimista,
    demonstrativo_anual,
    gerar_excel,
    gerar_pdf_comprovante,
    gerar_pdf_relatorio,
    gerar_pix_contribuicao,
    historico_dizimista,
    listar_categorias,
    normalizar_cpf,
    ranking_por_comunidade,
    ranking_por_contribuinte,
    totais_dashboard,
)


from flask import jsonify
from extensions import db

from contribuicoes.services import confirmar_pagamento_pix
from contribuicoes.models import Contribuicao


from rifas.payments import get_pix_gateway


@contribuicoes_bp.route("/", methods=["GET", "POST"])
@contribuicoes_bp.route("/consultar", methods=["GET", "POST"])
@contribuicoes_bp.route("/contribuir", methods=["GET", "POST"])
def consultar():

    if request.method == "GET":
        return render_template("contribuicoes/consultar.html")

    cpf = normalizar_cpf(request.form.get("cpf"))
    dizimista = buscar_dizimista_por_cpf(cpf)
    if dizimista is None:
        return redirect(url_for("contribuicoes.cadastro", cpf=cpf))
    return redirect(url_for("contribuicoes.contribuicao", dizimista_id=dizimista.id))


@contribuicoes_bp.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    comunidades = Comunidade.query.order_by(Comunidade.nome.asc()).all()

    if request.method == "POST":
        try:
            dizimista = criar_ou_atualizar_dizimista(
                cpf=request.form.get("cpf"),
                nome=request.form.get("nome"),
                telefone=request.form.get("telefone"),
                whatsapp=request.form.get("whatsapp"),
                email=request.form.get("email"),
                comunidade_id=request.form.get("comunidade_id"),
                cep=request.form.get("cep"),
                endereco=request.form.get("endereco"),
                numero=request.form.get("numero"),
                bairro=request.form.get("bairro"),
                cidade=request.form.get("cidade"),
            )
            db.session.commit()
            return redirect(url_for("contribuicoes.contribuicao", dizimista_id=dizimista.id))
        except ContribuicaoError as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template(
        "contribuicoes/cadastro.html",
        cpf=normalizar_cpf(request.args.get("cpf")),
        comunidades=comunidades,
    )


@contribuicoes_bp.route("/contribuicao/<int:dizimista_id>", methods=["GET", "POST"])
def contribuicao(dizimista_id):
    dizimista = db.session.get(Dizimista, dizimista_id)
    if dizimista is None:
        flash("Contribuinte nao encontrado.", "warning")
        return redirect(url_for("contribuicoes.consultar"))

    categorias = listar_categorias()
    if request.method == "POST":
        try:
            result = gerar_pix_contribuicao(
                dizimista_id=dizimista.id,
                categoria_codigo=request.form.get("categoria_codigo"),
                valor=request.form.get("valor"),
                competencia=request.form.get("competencia"),
                descricao=request.form.get("descricao"),
            )
            return redirect(url_for("contribuicoes.pix", contribuicao_id=result.contribuicao_id))
        except ContribuicaoError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except Exception as exc:
            db.session.rollback()
            flash(f"Erro ao gerar PIX: {exc}", "danger")

    return render_template("contribuicoes/contribuicao.html", dizimista=dizimista, categorias=categorias)


@contribuicoes_bp.route("/pix/<int:contribuicao_id>")
def pix(contribuicao_id):
    contribuicao = db.session.get(Contribuicao, contribuicao_id)
    if contribuicao is None:
        flash("Contribuicao nao encontrada.", "warning")
        return redirect(url_for("contribuicoes.consultar"))
    return render_template("contribuicoes/pix.html", contribuicao=contribuicao)


@contribuicoes_bp.route("/segunda-via-pix/<int:contribuicao_id>", methods=["GET", "POST"])
def segunda_via_pix(contribuicao_id):
    antiga = db.session.get(Contribuicao, contribuicao_id)
    if antiga is None:
        flash("Contribuicao nao encontrada.", "warning")
        return redirect(url_for("contribuicoes.consultar"))
    if request.method == "GET":
        return redirect(url_for("contribuicoes.pix", contribuicao_id=antiga.id))
    if antiga.status == "pago":
        flash("Esta contribuicao ja foi paga.", "info")
        return redirect(url_for("contribuicoes.pix", contribuicao_id=antiga.id))

    result = gerar_pix_contribuicao(
        dizimista_id=antiga.dizimista_id,
        categoria_codigo=antiga.categoria.codigo,
        valor=antiga.valor,
        competencia=antiga.competencia,
        descricao=antiga.descricao,
    )
    antiga.status = "cancelado"
    antiga.cancelado_em = datetime.utcnow()
    db.session.commit()
    return redirect(url_for("contribuicoes.pix", contribuicao_id=result.contribuicao_id))


@contribuicoes_bp.route("/historico/<int:dizimista_id>")
def historico(dizimista_id):
    try:
        dizimista, contribuicoes = historico_dizimista(dizimista_id)
    except ContribuicaoError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("contribuicoes.consultar"))
    return render_template("contribuicoes/historico.html", dizimista=dizimista, contribuicoes=contribuicoes)


@contribuicoes_bp.route("/dashboard")
@login_required
def dashboard():
    recentes = db.session.execute(
        db.select(Contribuicao).order_by(Contribuicao.data_geracao.desc()).limit(20)
    ).scalars().all()
    return render_template(
        "contribuicoes/dashboard.html",
        totais=totais_dashboard(),
        recentes=recentes,
        filtros=request.args.to_dict(),
    )


@contribuicoes_bp.route("/ranking")
@login_required
def ranking():
    return render_template(
        "contribuicoes/ranking.html",
        comunidades=ranking_por_comunidade(),
        contribuintes=ranking_por_contribuinte(),
    )


@contribuicoes_bp.route("/relatorios")
@login_required
def relatorios():
    contribuicoes = consulta_relatorio(request.args)
    comunidades = Comunidade.query.order_by(Comunidade.nome.asc()).all()
    categorias = listar_categorias(ativas=False)
    dizimistas = Dizimista.query.order_by(Dizimista.nome.asc()).limit(300).all()
    return render_template(
        "contribuicoes/dashboard.html",
        totais=totais_dashboard(),
        recentes=contribuicoes,
        relatorio=True,
        filtros=request.args.to_dict(),
        comunidades=comunidades,
        categorias=categorias,
        dizimistas=dizimistas,
    )


@contribuicoes_bp.route("/relatorios/excel")
@login_required
def relatorio_excel():
    output = gerar_excel(consulta_relatorio(request.args))
    return send_file(
        output,
        as_attachment=True,
        download_name="contribuicoes.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@contribuicoes_bp.route("/relatorios/pdf")
@login_required
def relatorio_pdf():
    output = gerar_pdf_relatorio(consulta_relatorio(request.args))
    return send_file(output, as_attachment=True, download_name="contribuicoes.pdf", mimetype="application/pdf")


@contribuicoes_bp.route("/comprovante/<int:contribuicao_id>")
def comprovante(contribuicao_id):
    contribuicao = db.session.get(Contribuicao, contribuicao_id)
    if contribuicao is None:
        flash("Contribuicao nao encontrada.", "warning")
        return redirect(url_for("contribuicoes.consultar"))
    return render_template("contribuicoes/comprovante.html", contribuicao=contribuicao)


@contribuicoes_bp.route("/comprovante/<int:contribuicao_id>/pdf")
def comprovante_pdf(contribuicao_id):
    contribuicao = db.session.get(Contribuicao, contribuicao_id)
    if contribuicao is None:
        flash("Contribuicao nao encontrada.", "warning")
        return redirect(url_for("contribuicoes.consultar"))
    output = gerar_pdf_comprovante(contribuicao)
    db.session.commit()
    return send_file(output, as_attachment=True, download_name=f"comprovante-{contribuicao.id}.pdf", mimetype="application/pdf")


@contribuicoes_bp.route("/demonstrativo/<int:dizimista_id>/<int:ano>")
def demonstrativo(dizimista_id, ano):
    try:
        dizimista, contribuicoes, total = demonstrativo_anual(dizimista_id, ano)
    except ContribuicaoError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("contribuicoes.consultar"))
    return render_template(
        "contribuicoes/historico.html",
        dizimista=dizimista,
        contribuicoes=contribuicoes,
        total_anual=total,
        ano=ano,
    )


@contribuicoes_bp.route("/demonstrativo/<int:dizimista_id>/<int:ano>/pdf")
def demonstrativo_pdf(dizimista_id, ano):
    try:
        dizimista, contribuicoes, _ = demonstrativo_anual(dizimista_id, ano)
    except ContribuicaoError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("contribuicoes.consultar"))
    output = gerar_pdf_relatorio(contribuicoes, titulo=f"Demonstrativo Anual {ano} - {dizimista.nome}")
    return send_file(output, as_attachment=True, download_name=f"demonstrativo-{ano}-{dizimista.id}.pdf", mimetype="application/pdf")


# Compatibilidade com rotas antigas do rascunho inicial.
@contribuicoes_bp.route("/cadastrar_dizimista", methods=["GET", "POST"])
def cadastrar_dizimista():
    if request.method == "GET":
        return redirect(url_for("contribuicoes.cadastro", cpf=normalizar_cpf(request.args.get("cpf"))))
    return cadastro()


@contribuicoes_bp.route("/gerar_pix", methods=["GET", "POST"])
def gerar_pix():
    dizimista_id = request.values.get("dizimista_id")
    cpf = request.values.get("cpf")

    if not dizimista_id and cpf:
        dizimista = buscar_dizimista_por_cpf(cpf)
        if dizimista:
            dizimista_id = dizimista.id

    if not dizimista_id:
        return redirect(url_for("contribuicoes.consultar"))

    if request.method == "GET":
        return redirect(url_for("contribuicoes.contribuicao", dizimista_id=int(dizimista_id)))

    return contribuicao(int(dizimista_id))


@contribuicoes_bp.route(
    "/verificar_pix/<int:contribuicao_id>"
)
def verificar_pix_manual(contribuicao_id):

    from contribuicoes.services import verificar_contribuicao

    pago = verificar_contribuicao(
        contribuicao_id
    )

    if pago:

        return {

            "sucesso": True,

            "mensagem":
            "Pagamento confirmado."

        }

    return {

        "sucesso": False,

        "mensagem":
        "Pagamento ainda não localizado."

    }

@contribuicoes_bp.route(
    "/status/<int:contribuicao_id>"
)
def status(contribuicao_id):

    contribuicao = Contribuicao.query.get_or_404(
        contribuicao_id
    )

    # já está pago
    if contribuicao.status == "pago":

        return jsonify({
            "pago": True
        })

    gateway = get_pix_gateway()

    try:

        retorno = gateway.consultar_cobranca(
            contribuicao.txid
        )

        if retorno:

            status = (
                retorno.get("status") or ""
            ).upper()

            if status in (
                "CONCLUIDA",
                "LIQUIDADA"
            ):

                confirmar_pagamento_pix(
                    retorno
                )

                db.session.commit()

                return jsonify({
                    "pago": True
                })

            pixs = retorno.get(
                "pix",
                []
            )

            if pixs:

                confirmar_pagamento_pix(
                    pixs[0]
                )

                db.session.commit()

                return jsonify({
                    "pago": True
                })

    except Exception as e:

        current_app.logger.exception(e)

    return jsonify({
        "pago": False
    })
from flask import session
from ofertas.utils import login_ofertas_required

from datetime import datetime
from flask import current_app
from flask import flash, jsonify, redirect, render_template, request, send_file, url_for

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
@login_ofertas_required
def dashboard():
    query = db.select(
        Contribuicao
    )

    if not session.get("administrador"):

        query = query.where(
            Contribuicao.comunidade_id ==
            session["comunidade_id"]
        )

    recentes = db.session.execute(

        query.order_by(
            Contribuicao.data_geracao.desc()
        )

        .limit(20)

    ).scalars().all()

    return render_template(
        "contribuicoes/dashboard.html",
        totais=totais_dashboard(),
        recentes=recentes,
        filtros=request.args.to_dict(),
    )


@contribuicoes_bp.route("/ranking")
@login_ofertas_required
def ranking():
    return render_template(
        "contribuicoes/ranking.html",
        comunidades=ranking_por_comunidade(),
        contribuintes=ranking_por_contribuinte(),
    )


@contribuicoes_bp.route("/relatorios")
@login_ofertas_required
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
@login_ofertas_required
def relatorio_excel():
    output = gerar_excel(consulta_relatorio(request.args))
    return send_file(
        output,
        as_attachment=True,
        download_name="contribuicoes.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@contribuicoes_bp.route("/relatorios/pdf")
@login_ofertas_required
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

#@contribuicoes_bp.route("/inicio")
#@login_ofertas_required
#def inicio():

#    return render_template(
#        "contribuicoes/index.html"
#    )

@contribuicoes_bp.route("/api/buscar-cpf/<cpf>")
def api_buscar_cpf(cpf):

    dizimista = buscar_dizimista_por_cpf(cpf)

    if not dizimista:
        return jsonify({
            "encontrado": False
        })

    historico = historico_dizimista(dizimista.id)[1]

    total_ano = sum(
        float(c.valor)
        for c in historico
        if c.status == "pago"
    )

    return jsonify({

        "encontrado": True,

        "id": dizimista.id,

        "nome": dizimista.nome,

        "telefone": dizimista.telefone,

        "whatsapp": dizimista.whatsapp,

        "email": dizimista.email,

        "comunidade":
        dizimista.comunidade.nome
        if dizimista.comunidade
        else "",

        "total_ano": total_ano

    })

@contribuicoes_bp.route("/api/gerar-pix", methods=["POST"])
def api_gerar_pix():

    dados = request.json

    result = gerar_pix_contribuicao(

        dizimista_id=dados["dizimista_id"],

        categoria_codigo=dados["categoria"],

        valor=dados["valor"],

        competencia=dados["competencia"]

    )

    return jsonify({

        "id": result.contribuicao_id,

        "txid": result.txid,

        "qr": result.qr_code_base64,

        "pix": result.copia_cola_pix

    })

@contribuicoes_bp.route("/api/status/<int:id>")
def api_status(id):

    c = db.session.get(
        Contribuicao,
        id
    )

    return jsonify({

        "status": c.status

    })

@contribuicoes_bp.route("/app")
def app_contribuicoes():

    cpf = request.args.get("cpf")

    dizimista = None

    if cpf:

        dizimista = buscar_dizimista_por_cpf(cpf)
    categorias = listar_categorias()

    comunidades = (
        Comunidade.query
        .filter_by(ativa=True)
        .order_by(Comunidade.nome)
        .all()
    )

    competencia_atual = datetime.now().strftime("%Y-%m")

    return render_template(
        "contribuicoes/contribuicao_unica.html",
        categorias=categorias,
        comunidades=comunidades,
        competencia_atual=competencia_atual,
        dizimista=dizimista
    )

@contribuicoes_bp.route("/api/cadastrar", methods=["POST"])
def api_cadastrar():


    dados = request.json

    try:

        dizimista = criar_ou_atualizar_dizimista(

            cpf=dados.get("cpf"),

            nome=dados.get("nome"),

            telefone=dados.get("telefone"),

            whatsapp=dados.get("whatsapp"),

            email=dados.get("email"),

            comunidade_id=dados.get("comunidade_id")

        )

        db.session.commit()

        return jsonify({

            "sucesso": True,

            "id": dizimista.id,

            "nome": dizimista.nome,

            "telefone": dizimista.telefone,

            "comunidade":
                dizimista.comunidade.nome
                if dizimista.comunidade
                else ""

        })

    except Exception as e:

        db.session.rollback()

        return jsonify({

            "sucesso": False,

            "erro": str(e)

        }), 400

@contribuicoes_bp.route("/dizimistas")
@login_ofertas_required
def dizimistas():


    filtro = request.args.get("q", "").strip()

    query = Dizimista.query

    if filtro:

        query = query.filter(

            db.or_(

                Dizimista.nome.ilike(f"%{filtro}%"),

                Dizimista.cpf.ilike(f"%{filtro}%")

            )

        )

    consulta = Dizimista.query

    if not session.get("administrador"):

        consulta = consulta.filter(
            Dizimista.comunidade_id ==
            session["comunidade_id"]
        )

    dizimistas = (
        consulta
        .order_by(Dizimista.nome)
        .all()
    )

    return render_template(

        "contribuicoes/dizimistas.html",

        dizimistas=dizimistas,

        filtro=filtro

    )

@contribuicoes_bp.route("/dizimista/<int:id>")
@login_ofertas_required
def ficha_dizimista(id):

    dizimista = db.session.get(
        Dizimista,
        id
    )

    if (
        not session.get("administrador")
        and
        dizimista.comunidade_id != session["comunidade_id"]
    ):

        flash(
            "Acesso negado.",
            "danger"
        )

        return redirect(
            url_for(
                "contribuicoes.dizimistas"
            )
        )    

    if dizimista is None:

        flash(
            "Dizimista não encontrado.",
            "warning"
        )

        return redirect(
            url_for(
                "contribuicoes.dizimistas"
            )
        )

    contribuicoes = (
        Contribuicao.query
        .filter_by(
            dizimista_id=id
        )
        .order_by(
            Contribuicao.data_geracao.desc()
        )
        .all()
    )

    total_ano = sum(
        float(c.valor)
        for c in contribuicoes
        if c.status == "pago"
    )

    ultima_contribuicao = (
        contribuicoes[0]
        if contribuicoes else None
    )

    ano_atual = datetime.now().year

    return render_template(

        "contribuicoes/ficha_dizimista.html",

        dizimista=dizimista,

        contribuicoes=contribuicoes,

        total_ano=total_ano,

        ultima_contribuicao=ultima_contribuicao,

        ano_atual=ano_atual

    )

@contribuicoes_bp.route(
    "/editar-dizimista/<int:id>",
    methods=["GET", "POST"]
)
@login_ofertas_required
def editar_dizimista(id):

    dizimista = db.session.get(
        Dizimista,
        id
    )

    if (
        not session.get("administrador")
        and
        dizimista.comunidade_id != session["comunidade_id"]
    ):

        flash(
            "Acesso negado.",
            "danger"
        )

        return redirect(
            url_for(
                "contribuicoes.dizimistas"
            )
        )    

    if dizimista is None:

        flash(
            "Dizimista não encontrado.",
            "warning"
        )

        return redirect(
            url_for(
                "contribuicoes.dizimistas"
            )
        )

    comunidades = (
        Comunidade.query
        .order_by(
            Comunidade.nome
        )
        .all()
    )

    if request.method == "POST":

        try:

            dizimista.nome = request.form.get("nome")
            dizimista.telefone = request.form.get("telefone")
            dizimista.whatsapp = request.form.get("whatsapp")
            dizimista.email = request.form.get("email")
            dizimista.comunidade_id = request.form.get("comunidade_id")

            db.session.commit()

            flash(
                "Cadastro atualizado com sucesso.",
                "success"
            )

            return redirect(
                url_for(
                    "contribuicoes.ficha_dizimista",
                    id=dizimista.id
                )
            )

        except Exception as e:

            db.session.rollback()

            flash(
                str(e),
                "danger"
            )

    return render_template(
        "contribuicoes/editar_dizimista.html",
        dizimista=dizimista,
        comunidades=comunidades
    )

@contribuicoes_bp.route("/")
@login_ofertas_required
def inicio():

    return render_template(
        "contribuicoes/index.html",

        usuario=session.get("usuario"),

        administrador=session.get("administrador"),

        comunidade_id=session.get("comunidade_id")
    )

@contribuicoes_bp.route("/historico_publico/<int:id>")
def historico_publico(id):

    from sqlalchemy import func

    dizimista = db.session.get(
        Dizimista,
        id
    )

    if not dizimista:

        flash(
            "Dizimista não encontrado.",
            "warning"
        )

        return redirect(
            url_for(
                "contribuicoes.app_contribuicoes"
            )
        )

    # Histórico (somente pagos)
    contribuicoes = (
        Contribuicao.query
        .filter(
            Contribuicao.dizimista_id == id,
            Contribuicao.status == "pago"
        )
        .order_by(
            Contribuicao.data_geracao.desc()
        )
        .all()
    )

    # Total do ano
    total_ano = sum(
        float(c.valor)
        for c in contribuicoes
    )

    # Resumo por categoria
    resumo_categoria = db.session.execute(

        db.select(
            CategoriaContribuicao.descricao,
            func.sum(Contribuicao.valor)
        )

        .join(
            CategoriaContribuicao,
            CategoriaContribuicao.id ==
            Contribuicao.categoria_id
        )

        .where(
            Contribuicao.dizimista_id == id,
            Contribuicao.status == "pago"
        )

        .group_by(
            CategoriaContribuicao.descricao
        )

        .order_by(
            CategoriaContribuicao.descricao
        )

    ).all()

    return render_template(

        "contribuicoes/historico_publico.html",

        dizimista=dizimista,

        contribuicoes=contribuicoes,

        total_ano=total_ano,

        resumo_categoria=resumo_categoria

    )
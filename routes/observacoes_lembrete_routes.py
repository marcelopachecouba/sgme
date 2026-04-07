from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import ObservacaoLembrete, db
from utils.auth import admin_required


observacoes_lembrete_bp = Blueprint("observacoes_lembrete", __name__)


def _listar_observacoes():
    return ObservacaoLembrete.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(
        ObservacaoLembrete.data_cadastro.desc(),
        ObservacaoLembrete.id.desc(),
    ).all()


def _descricao_form():
    return (request.form.get("descricao") or "").strip()


@observacoes_lembrete_bp.route("/observacoes-lembrete", methods=["GET", "POST"])
@login_required
@admin_required
def listar_criar_observacoes():
    if request.method == "POST":
        descricao = _descricao_form()
        ativo = bool(request.form.get("ativo"))

        if not descricao:
            flash("Informe uma observacao antes de salvar.")
            return render_template(
                "observacoes_lembrete.html",
                observacoes=_listar_observacoes(),
                observacao_em_edicao=None,
                form_data={"descricao": descricao, "ativo": ativo},
            )

        observacao = ObservacaoLembrete(
            descricao=descricao,
            ativo=ativo,
            id_paroquia=current_user.id_paroquia,
        )
        db.session.add(observacao)
        db.session.commit()
        flash("Observacao de lembrete salva com sucesso.")
        return redirect(url_for("observacoes_lembrete.listar_criar_observacoes"))

    return render_template(
        "observacoes_lembrete.html",
        observacoes=_listar_observacoes(),
        observacao_em_edicao=None,
        form_data={"descricao": "", "ativo": True},
    )


@observacoes_lembrete_bp.route("/observacoes-lembrete/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_observacao(id):
    observacao = ObservacaoLembrete.query.filter_by(
        id=id,
        id_paroquia=current_user.id_paroquia,
    ).first_or_404()

    if request.method == "POST":
        descricao = _descricao_form()
        ativo = bool(request.form.get("ativo"))

        if not descricao:
            flash("Informe uma observacao antes de editar.")
            return render_template(
                "observacoes_lembrete.html",
                observacoes=_listar_observacoes(),
                observacao_em_edicao=observacao,
                form_data={"descricao": descricao, "ativo": ativo},
            )

        observacao.descricao = descricao
        observacao.ativo = ativo
        db.session.commit()
        flash("Observacao de lembrete atualizada com sucesso.")
        return redirect(url_for("observacoes_lembrete.listar_criar_observacoes"))

    return render_template(
        "observacoes_lembrete.html",
        observacoes=_listar_observacoes(),
        observacao_em_edicao=observacao,
        form_data={"descricao": observacao.descricao, "ativo": observacao.ativo},
    )


@observacoes_lembrete_bp.route("/observacoes-lembrete/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_observacao(id):
    observacao = ObservacaoLembrete.query.filter_by(
        id=id,
        id_paroquia=current_user.id_paroquia,
    ).first_or_404()

    db.session.delete(observacao)
    db.session.commit()
    flash("Observacao de lembrete excluida com sucesso.")
    return redirect(url_for("observacoes_lembrete.listar_criar_observacoes"))

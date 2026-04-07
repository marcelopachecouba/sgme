from models import ObservacaoLembrete


def listar_observacoes_ativas(id_paroquia=None):
    query = ObservacaoLembrete.query.filter(ObservacaoLembrete.ativo.is_(True))

    if id_paroquia is not None:
        query = query.filter(ObservacaoLembrete.id_paroquia == id_paroquia)

    return query.order_by(
        ObservacaoLembrete.data_cadastro.desc(),
        ObservacaoLembrete.id.desc(),
    ).all()


def listar_textos_observacoes_ativas(id_paroquia=None):
    textos = []

    for item in listar_observacoes_ativas(id_paroquia=id_paroquia):
        descricao = (item.descricao or "").strip()
        if descricao:
            textos.append(descricao)

    return textos


def anexar_observacoes_ativas(mensagem, id_paroquia=None):
    textos = listar_textos_observacoes_ativas(id_paroquia=id_paroquia)
    if not textos:
        return mensagem

    mensagem_base = (mensagem or "").rstrip()
    bloco_observacoes = "\n".join(textos)

    if not mensagem_base:
        return bloco_observacoes

    return f"{mensagem_base}\n\n{bloco_observacoes}"

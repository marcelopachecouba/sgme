from flask import Flask, render_template, redirect, request, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config import Config
from models import db, Usuario, Paroquia, Ministro, Missa, Escala, Indisponibilidade, EscalaFixa
from datetime import datetime, date
from calendar import monthrange
from datetime import timedelta
import calendar
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import base64
import io
import qrcode
from io import BytesIO

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,Image
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet
from flask import send_file
import tempfile
import os

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# ======================
# LOGIN CONFIG
# ======================

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# ======================
# BANCO INICIAL
# ======================

with app.app_context():
    db.create_all()

    if not Usuario.query.first():
        paroquia = Paroquia(nome="Paróquia São José")
        db.session.add(paroquia)
        db.session.commit()

        user = Usuario(
            nome="Marcelo",
            email="marcelosouzapacheco@gmail.com",
            tipo="SUPERADMIN",
            id_paroquia=paroquia.id
        )
        user.set_senha("123456")
        db.session.add(user)
        db.session.commit()

# ======================
# LOGIN
# ======================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        senha = request.form["senha"]

        user = Usuario.query.filter_by(email=email).first()

        if user and user.check_senha(senha):
            login_user(user)
            return redirect(url_for("home"))
        else:
            flash("Email ou senha inválidos.")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ======================
# DASHBOARD
# ======================

@app.route("/")
@login_required
def home():

    hoje = date.today()
    inicio_mes = hoje.replace(day=1)

    if hoje.month == 12:
        proximo_mes = hoje.replace(year=hoje.year + 1, month=1, day=1)
    else:
        proximo_mes = hoje.replace(month=hoje.month + 1, day=1)

    dados = db.session.query(
        Ministro.nome,
        db.func.count(Escala.id)
    ).join(Escala, Escala.id_ministro == Ministro.id)\
     .join(Missa, Missa.id == Escala.id_missa)\
     .filter(
        Escala.id_paroquia == current_user.id_paroquia,
        Missa.data >= inicio_mes,
        Missa.data < proximo_mes
     )\
     .group_by(Ministro.nome)\
     .all()

    nomes = [d[0] for d in dados]
    valores = [d[1] for d in dados]

    fig, ax = plt.subplots()
    ax.bar(nomes, valores)
    plt.xticks(rotation=45)
    img = io.BytesIO()
    plt.tight_layout()
    plt.savefig(img, format='png')
    img.seek(0)
    grafico_barra = base64.b64encode(img.getvalue()).decode()
    plt.close()

    total_escalas = sum(valores) if valores else 0
    confirmadas = Escala.query.filter_by(
        id_paroquia=current_user.id_paroquia,
        confirmado=True
    ).count()

    return render_template(
        "dashboard.html",
        grafico_barra=grafico_barra,
        total_escalas=total_escalas,
        confirmadas=confirmadas
    )

# ======================
# MINISTROS
# ======================

@app.route("/ministros")
@login_required
def ministros():
    lista = Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).all()
    return render_template("ministros.html", ministros=lista)

@app.route("/ministros/novo", methods=["GET", "POST"])
@login_required
def novo_ministro():

    if request.method == "POST":

        nome = request.form.get("nome")
        telefone = request.form.get("telefone")
        email = request.form.get("email")
        data_nascimento = request.form.get("data_nascimento")
        tempo_ministerio = request.form.get("tempo_ministerio")

        print("DEBUG:")
        print(nome, telefone, email, data_nascimento, tempo_ministerio)

        novo = Ministro(
            nome=nome,
            telefone=telefone,
            email=email,
            data_nascimento=datetime.strptime(data_nascimento, "%Y-%m-%d") if data_nascimento else None,
            tempo_ministerio=int(tempo_ministerio) if tempo_ministerio else 0,
            id_paroquia=current_user.id_paroquia
        )
        novo.gerar_token()

        db.session.add(novo)

        try:
            db.session.commit()
            print("SALVOU COM SUCESSO")
        except Exception as e:
            print("ERRO AO SALVAR:", e)
            db.session.rollback()

        return redirect(url_for("ministros"))

    return render_template("novo_ministro.html")


@app.route("/ministros/excluir/<int:id>")
@login_required
def excluir_ministro(id):

    ministro = Ministro.query.get_or_404(id)

    # Remove escalas vinculadas primeiro
    Escala.query.filter_by(id_ministro=ministro.id).delete()

    db.session.delete(ministro)
    db.session.commit()

    return redirect(url_for("ministros"))

# ======================
# MISSAS
# ======================

@app.route("/missas")
@login_required
def missas():
    lista = Missa.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).all()
    return render_template("missas.html", missas=lista)

@app.route("/missas/calendario")
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

    estrutura = {}

    for missa in missas:

        dia = missa.data.day

        if dia not in estrutura:
            estrutura[dia] = []

        escalas = Escala.query.filter_by(id_missa=missa.id).all()
        
        ministros = []

        for e in escalas:
            if e.ministro:
               ministros.append(e.ministro.nome)

        estrutura[dia].append({
            "horario": missa.horario,
            "comunidade": missa.comunidade,
            "ministros": ministros
        })

    return render_template(
        "calendario_missas.html",
        cal=cal,
        estrutura=estrutura,
        mes=mes,
        ano=ano
    )

@app.route("/missas/nova", methods=["GET", "POST"])
@login_required
def nova_missa():
    if request.method == "POST":
        data = datetime.strptime(request.form["data"], "%Y-%m-%d")
        horario = request.form["horario"]
        comunidade = request.form["comunidade"]
        qtd = request.form["qtd"]

        missa = Missa(
            data=data,
            horario=horario,
            comunidade=comunidade,
            qtd_ministros=qtd,
            id_paroquia=current_user.id_paroquia
        )

        db.session.add(missa)
        db.session.commit()
        return redirect(url_for("missas"))

    return render_template("nova_missa.html")


@app.route("/missas/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_missa(id):

    missa = Missa.query.get_or_404(id)

    if request.method == "POST":

        missa.data = datetime.strptime(request.form["data"], "%Y-%m-%d")
        missa.horario = request.form["horario"]
        missa.comunidade = request.form["comunidade"]
        missa.qtd_ministros = int(request.form["qtd"])

        db.session.commit()

        flash("Missa atualizada com sucesso!")
        return redirect(url_for("missas"))

    return render_template("editar_missa.html", missa=missa)

@app.route("/missas/excluir/<int:id>")
@login_required
def excluir_missa(id):

    missa = Missa.query.get_or_404(id)

    # Remove escalas vinculadas primeiro
    Escala.query.filter_by(id_missa=missa.id).delete()

    db.session.delete(missa)
    db.session.commit()

    flash("Missa excluída com sucesso!")
    return redirect(url_for("missas"))


@app.route("/missas/visao")
@login_required
def visao_missas():

    missas = Missa.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Missa.data, Missa.horario).all()

    estrutura = {}

    for missa in missas:

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

@app.route("/escala/<int:missa_id>", methods=["GET", "POST"])
@login_required
def gerar_escala(missa_id):

    missa = Missa.query.get_or_404(missa_id)
    ministros = Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).all()

    if request.method == "POST":
        selecionados = request.form.getlist("ministros")
        Escala.query.filter_by(id_missa=missa.id).delete()

        for ministro_id in selecionados:
            nova = Escala(
                id_missa=missa.id,
                id_ministro=int(ministro_id),
                id_paroquia=current_user.id_paroquia,
                token=str(uuid.uuid4())
            )
            db.session.add(nova)

        db.session.commit()
        return redirect(url_for("visualizar_escala", missa_id=missa.id))

    return render_template("gerar_escala.html", missa=missa, ministros=ministros)

# ======================
# ESCALA AUTOMÁTICA
# ======================

@app.route("/escala/auto/<int:missa_id>")
@login_required
def gerar_escala_auto(missa_id):

    missa = Missa.query.get_or_404(missa_id)

    # Limpa escala anterior da missa
    Escala.query.filter_by(id_missa=missa.id).delete()

    selecionados = []

    # ===============================
    # 1️⃣ BUSCA PRIMEIRO ESCALA FIXA
    # ===============================

    semana = (missa.data.day - 1) // 7 + 1
    dia_semana = missa.data.weekday()  # 0=segunda

    fixos = EscalaFixa.query.filter(
        EscalaFixa.id_paroquia == current_user.id_paroquia,
        (EscalaFixa.semana == semana) | (EscalaFixa.semana == None),
        (EscalaFixa.dia_semana == dia_semana) | (EscalaFixa.dia_semana == None),
        (EscalaFixa.horario == missa.horario) | (EscalaFixa.horario == None),
        (EscalaFixa.comunidade == missa.comunidade) | (EscalaFixa.comunidade == None)
    ).all()

    for fixa in fixos:

        ministro = Ministro.query.get(fixa.id_ministro)

        if not ministro:
            continue

        # verifica indisponibilidade
        indisponivel = Indisponibilidade.query.filter_by(
            id_ministro=ministro.id,
            data=missa.data,
            id_paroquia=current_user.id_paroquia
        ).first()

        if indisponivel:
            continue

        # evita duplicado
        if ministro not in selecionados:
            selecionados.append(ministro)

        if len(selecionados) >= missa.qtd_ministros:
            break

    # ===================================
    # 2️⃣ COMPLETA COM OUTROS SE PRECISAR
    # ===================================

    if len(selecionados) < missa.qtd_ministros:

        ministros = Ministro.query.filter_by(
            id_paroquia=current_user.id_paroquia
        ).all()

        for ministro in ministros:

            if ministro in selecionados:
                continue

            # verifica conflito de horário
            conflito = db.session.query(Escala)\
                .join(Missa)\
                .filter(
                    Escala.id_ministro == ministro.id,
                    Missa.data == missa.data,
                    Missa.horario == missa.horario,
                    Escala.id_paroquia == current_user.id_paroquia
                ).first()

            if conflito:
                continue

            # verifica indisponibilidade
            indisponivel = Indisponibilidade.query.filter_by(
                id_ministro=ministro.id,
                data=missa.data,
                id_paroquia=current_user.id_paroquia
            ).first()

            if indisponivel:
                continue

            selecionados.append(ministro)

            if len(selecionados) >= missa.qtd_ministros:
                break

    # ===============================
    # 3️⃣ SALVA NO BANCO
    # ===============================

    for ministro in selecionados:
        nova = Escala(
            id_missa=missa.id,
            id_ministro=ministro.id,
            id_paroquia=current_user.id_paroquia,
            token=str(uuid.uuid4())
        )
        db.session.add(nova)

    db.session.commit()

    flash("Escala automática gerada com sucesso!")
    return redirect(url_for("visualizar_escala", missa_id=missa.id))
# ======================
# VISUALIZAR ESCALA
# ======================

@app.route("/escala/visualizar/<int:missa_id>")
@login_required
def visualizar_escala(missa_id):

    missa = Missa.query.get_or_404(missa_id)

    escalas = Escala.query.filter_by(
        id_missa=missa.id,
        id_paroquia=current_user.id_paroquia
    ).all()

    ministros = Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Ministro.nome).all()

    return render_template(
        "visualizar_escala.html",
        missa=missa,
        escalas=escalas,
        ministros=ministros
    )
@app.route("/escala_fixa", methods=["GET", "POST"])
@login_required
def escala_fixa():

    ministros = Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Ministro.nome).all()

    if request.method == "POST":

        semana = request.form.get("semana")
        dia_semana = request.form.get("dia_semana")
        horario = request.form.get("horario")
        comunidade = request.form.get("comunidade")

        ministros_ids = request.form.getlist("ministros")

        if not ministros_ids:
            flash("Selecione pelo menos um ministro.")
            return redirect(url_for("escala_fixa"))

        for ministro_id in ministros_ids:

            nova = EscalaFixa(
                semana=int(semana) if semana else None,
                dia_semana=int(dia_semana) if dia_semana else None,
                horario=horario if horario else None,
                comunidade=comunidade if comunidade else None,
                id_ministro=int(ministro_id),
                id_paroquia=current_user.id_paroquia
            )

            db.session.add(nova)

        db.session.commit()

        flash("Escala fixa cadastrada com sucesso!")
        return redirect(url_for("escala_fixa"))

    fixos = EscalaFixa.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).all()

    return render_template(
        "escala_fixa.html",
        ministros=ministros,
        fixos=fixos
    )

@app.route("/estatisticas", methods=["GET", "POST"])
@login_required
def estatisticas():

    data_inicio = ""
    data_fim = ""

    query = Escala.query.join(Missa).join(Ministro).filter(
        Escala.id_paroquia == current_user.id_paroquia
    )

    if request.method == "POST":

        data_inicio = request.form.get("data_inicio")
        data_fim = request.form.get("data_fim")

        if data_inicio:
            data_inicio_date = datetime.strptime(data_inicio, "%Y-%m-%d").date()
            query = query.filter(db.func.date(Missa.data) >= data_inicio_date)

        if data_fim:
            data_fim_date = datetime.strptime(data_fim, "%Y-%m-%d").date()
            query = query.filter(db.func.date(Missa.data) <= data_fim_date)

    escalas = query.order_by(Ministro.nome, Missa.data).all()

    # 🔥 AGRUPAMENTO POR MINISTRO
    dados = {}

    for e in escalas:
        nome = e.ministro.nome

        if nome not in dados:
            dados[nome] = {
                "total": 0,
                "missas": []
            }

        dados[nome]["total"] += 1
        dados[nome]["missas"].append(e)

    return render_template(
        "estatisticas.html",
        dados=dados,
        data_inicio=data_inicio,
        data_fim=data_fim
    )

@app.route("/escala_fixa/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_escala_fixa(id):

    fixa = EscalaFixa.query.get_or_404(id)

    ministros = Ministro.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).order_by(Ministro.nome).all()

    if request.method == "POST":

        fixa.semana = int(request.form["semana"]) if request.form.get("semana") else None
        fixa.dia_semana = int(request.form["dia_semana"]) if request.form.get("dia_semana") else None
        fixa.horario = request.form.get("horario") or None
        fixa.comunidade = request.form.get("comunidade") or None

        db.session.commit()

        flash("Escala fixa atualizada com sucesso!")
        return redirect(url_for("escala_fixa"))

    return render_template(
        "editar_escala_fixa.html",
        fixa=fixa,
        ministros=ministros
    )

@app.route("/escala_fixa/excluir/<int:id>")
@login_required
def excluir_escala_fixa(id):

    fixa = EscalaFixa.query.get_or_404(id)
    db.session.delete(fixa)
    db.session.commit()

    flash("Escala fixa removida.")
    return redirect(url_for("escala_fixa"))

@app.route("/ministros/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_ministro(id):

    ministro = Ministro.query.get_or_404(id)

    if request.method == "POST":

        novo_nome = request.form["nome"].strip()
        telefone = request.form["telefone"]
        email = request.form["email"]
        data_nascimento = request.form["data_nascimento"]
        tempo_ministerio = request.form["tempo_ministerio"]

        existe = Ministro.query.filter(
            Ministro.nome == novo_nome,
            Ministro.id_paroquia == current_user.id_paroquia,
            Ministro.id != ministro.id
        ).first()

        if existe:
            flash("Já existe outro ministro com esse nome.")
            return redirect(url_for("editar_ministro", id=id))

        ministro.nome = novo_nome
        ministro.telefone = telefone
        ministro.email = email
        ministro.data_nascimento = datetime.strptime(data_nascimento, "%Y-%m-%d") if data_nascimento else None
        ministro.tempo_ministerio = int(tempo_ministerio) if tempo_ministerio else 0

        db.session.commit()
        return redirect(url_for("ministros"))

    return render_template("editar_ministro.html", ministro=ministro)

from datetime import datetime

@app.route("/escala_mensal", methods=["GET", "POST"])
@login_required
def escala_mensal():

    if request.method == "POST":

        mes = int(request.form["mes"])
        ano = int(request.form["ano"])

        inicio_mes = date(ano, mes, 1)
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        fim_mes = date(ano, mes, ultimo_dia)

        domingos = []
        dia = inicio_mes

        # =============================
        # BUSCA TODOS OS DOMINGOS
        # =============================
        while dia <= fim_mes:
            if dia.weekday() == 6:  # 6 = Domingo
                domingos.append(dia)
            dia += timedelta(days=1)

        estrutura = {}

        # =============================
        # MONTA ESTRUTURA
        # =============================
        for domingo in domingos:

            semana = (domingo.day - 1) // 7 + 1

            estrutura[semana] = {
                "data": domingo,
                "manha": [],
                "noite": []
            }

            missas = Missa.query.filter_by(
                data=domingo,
                id_paroquia=current_user.id_paroquia
            ).all()

            for missa in missas:

                escalas = Escala.query.filter_by(
                    id_missa=missa.id
                ).all()

                nomes = [e.ministro.nome for e in escalas]

                # Se horário começa com 08 ou contém 8 → manhã
                if "8" in missa.horario or "07" in missa.horario:
                    estrutura[semana]["manha"] = nomes
                else:
                    estrutura[semana]["noite"] = nomes

        return render_template(
            "escala_mensal_editavel.html",
            estrutura=estrutura,
            mes=mes,
            ano=ano
        )

    return render_template("form_escala_mensal.html")


@app.route("/escala_fixa/visao")
@login_required
def visao_escala_fixa():

    fixos = EscalaFixa.query.filter_by(
        id_paroquia=current_user.id_paroquia
    ).all()

    estrutura = {}

    for f in fixos:

        if not f.ministro:
            continue

        semana = f.semana if f.semana else 0
        dia = f.dia_semana if f.dia_semana is not None else -1
        horario = f.horario if f.horario else "99:99"

        if semana not in estrutura:
            estrutura[semana] = {}

        if dia not in estrutura[semana]:
            estrutura[semana][dia] = {}

        if horario not in estrutura[semana][dia]:
            estrutura[semana][dia][horario] = set()  # 🔥 AQUI MUDOU

        estrutura[semana][dia][horario].add(f.ministro.nome)  # 🔥 AQUI MUDOU

    # Converter set para lista ordenada
    for semana in estrutura:
        for dia in estrutura[semana]:
            for horario in estrutura[semana][dia]:
                estrutura[semana][dia][horario] = sorted(
                    list(estrutura[semana][dia][horario])
                )

    return render_template(
        "visao_escala_fixa.html",
        estrutura=estrutura
    )

@app.route("/gerar_mensal", methods=["GET", "POST"])
@login_required
def gerar_mensal():

    if request.method == "POST":

        mes = int(request.form["mes"])
        ano = int(request.form["ano"])

        cal = calendar.monthcalendar(ano, mes)

        for semana in cal:
            for dia_semana, dia in enumerate(semana):

                if dia == 0:
                    continue

                data_missa = date(ano, mes, dia)
                semana_mes = (dia - 1) // 7 + 1

                # Buscar regras que se aplicam a esse dia
                regras = EscalaFixa.query.filter_by(
                    id_paroquia=current_user.id_paroquia
                ).all()

                # Filtrar regras válidas para esse dia específico
                regras_validas = []

                for regra in regras:

                    if regra.semana and regra.semana != semana_mes:
                        continue

                    if regra.dia_semana is not None and regra.dia_semana != dia_semana:
                        continue

                    regras_validas.append(regra)

                # Agrupar por horário + comunidade
                agrupado = {}

                for regra in regras_validas:
                    chave = (regra.horario, regra.comunidade)

                    if chave not in agrupado:
                        agrupado[chave] = []

                    agrupado[chave].append(regra)

                # Criar Missa e Escalas
                for (horario, comunidade), lista_regras in agrupado.items():

                    qtd_ministros = len(lista_regras)

                    missa = Missa.query.filter_by(
                        data=data_missa,
                        horario=horario,
                        id_paroquia=current_user.id_paroquia
                    ).first()

                    if not missa:
                        missa = Missa(
                            data=data_missa,
                            horario=horario,
                            comunidade=comunidade or "Matriz",
                            qtd_ministros=qtd_ministros,
                            id_paroquia=current_user.id_paroquia
                        )
                        db.session.add(missa)
                        db.session.commit()
                    else:
                        # Atualiza quantidade se já existir
                        missa.qtd_ministros = qtd_ministros
                        db.session.commit()

                    # Criar escalas
                    for regra in lista_regras:

                        escala_existente = Escala.query.filter_by(
                            id_missa=missa.id,
                            id_ministro=regra.id_ministro
                        ).first()

                        if not escala_existente:
                            nova = Escala(
                                id_missa=missa.id,
                                id_ministro=regra.id_ministro,
                                id_paroquia=current_user.id_paroquia,
                                token=str(uuid.uuid4())
                            )
                            db.session.add(nova)

        db.session.commit()

        flash("Escala mensal gerada automaticamente com base na escala fixa!")
        return redirect(url_for("missas"))

    return render_template("form_gerar_mensal.html")

@app.route("/escala/remover/<int:escala_id>")
@login_required
def remover_ministro_escala(escala_id):

    escala = Escala.query.get_or_404(escala_id)
    missa_id = escala.id_missa

    db.session.delete(escala)
    db.session.commit()

    flash("Ministro removido da escala!")
    return redirect(url_for("visualizar_escala", missa_id=missa_id))

@app.route("/escala/adicionar/<int:missa_id>", methods=["POST"])
@login_required
def adicionar_ministro_escala(missa_id):

    ministro_id = request.form.get("ministro_id")

    existe = Escala.query.filter_by(
        id_missa=missa_id,
        id_ministro=ministro_id
    ).first()

    if not existe:
        nova = Escala(
            id_missa=missa_id,
            id_ministro=ministro_id,
            id_paroquia=current_user.id_paroquia,
            token=str(uuid.uuid4())
        )
        db.session.add(nova)
        db.session.commit()

    return redirect(url_for("visualizar_escala", missa_id=missa_id))

@app.route("/salvar_mensal", methods=["POST"])
@login_required
def salvar_mensal():

    mes = int(request.form["mes"])
    ano = int(request.form["ano"])

    cal = calendar.monthcalendar(ano, mes)

    for semana in cal:
        for dia_semana, dia in enumerate(semana):

            if dia == 0:
                continue

            data_missa = date(ano, mes, dia)
            semana_mes = (dia - 1) // 7 + 1

            regras = EscalaFixa.query.filter_by(
                id_paroquia=current_user.id_paroquia
            ).all()

            for regra in regras:

                if regra.semana and regra.semana != semana_mes:
                    continue

                if regra.dia_semana is not None and regra.dia_semana != dia_semana:
                    continue

                missa = Missa.query.filter_by(
                    data=data_missa,
                    horario=regra.horario,
                    id_paroquia=current_user.id_paroquia
                ).first()

                if not missa:
                    missa = Missa(
                        data=data_missa,
                        horario=regra.horario,
                        comunidade=regra.comunidade or "Matriz",
                        qtd_ministros=1,
                        id_paroquia=current_user.id_paroquia
                    )
                    db.session.add(missa)
                    db.session.commit()

                escala_existente = Escala.query.filter_by(
                    id_missa=missa.id,
                    id_ministro=regra.id_ministro
                ).first()

                if not escala_existente:
                    nova = Escala(
                        id_missa=missa.id,
                        id_ministro=regra.id_ministro,
                        id_paroquia=current_user.id_paroquia
                    )
                    db.session.add(nova)

    db.session.commit()

    flash("Escala mensal criada com sucesso!")
    return redirect(url_for("missas"))

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.platypus import Table
from reportlab.lib.pagesizes import A4
from reportlab.platypus import TableStyle
import io
from flask import send_file

@app.route("/estatisticas/pdf", methods=["POST"])
@login_required
def estatisticas_pdf():

    data_inicio = request.form.get("data_inicio")
    data_fim = request.form.get("data_fim")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []

    styles = getSampleStyleSheet()
    elements.append(Paragraph("Relatório de Escalas", styles["Heading1"]))
    elements.append(Spacer(1, 12))

    query = Escala.query.join(Missa).join(Ministro).filter(
        Escala.id_paroquia == current_user.id_paroquia
    )

    if data_inicio:
        query = query.filter(db.func.date(Missa.data) >= data_inicio)

    if data_fim:
        query = query.filter(db.func.date(Missa.data) <= data_fim)

    escalas = query.all()

    data_table = [["Ministro", "Data", "Horário", "Comunidade"]]

    for e in escalas:
        data_table.append([
            e.ministro.nome,
            e.missa.data.strftime("%d/%m/%Y"),
            e.missa.horario,
            e.missa.comunidade
        ])

    table = Table(data_table)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.grey),
        ("GRID", (0,0), (-1,-1), 1, colors.black)
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    return send_file(buffer, as_attachment=True,
                     download_name="relatorio_escalas.pdf",
                     mimetype="application/pdf")
import urllib.parse
from collections import defaultdict

@app.route("/estatisticas/whatsapp", methods=["POST"])
@login_required
def whatsapp_periodo():

    data_inicio = request.form.get("data_inicio")
    data_fim = request.form.get("data_fim")

    query = Escala.query.join(Missa).join(Ministro).filter(
        Escala.id_paroquia == current_user.id_paroquia,
        Escala.confirmado == False
    )

    if data_inicio:
        data_inicio_date = datetime.strptime(data_inicio, "%Y-%m-%d").date()
        query = query.filter(db.func.date(Missa.data) >= data_inicio_date)

    if data_fim:
        data_fim_date = datetime.strptime(data_fim, "%Y-%m-%d").date()
        query = query.filter(db.func.date(Missa.data) <= data_fim_date)

    escalas = query.order_by(Ministro.nome, Missa.data).all()

    from collections import defaultdict
    import urllib.parse

    ministros_dict = defaultdict(list)

    for e in escalas:
        if e.ministro and e.ministro.telefone:
            ministros_dict[e.ministro].append(e)

    links = []

    for ministro, lista_escalas in ministros_dict.items():

        mensagem = f"Olá {ministro.nome},\n\n"
        mensagem += "Esse é um lembrete para sua próxima escala do grupo Ministério da Eucaristia.\n\n"

        # 🔹 FORMATA DATA EM PORTUGUÊS
        meses = {
            1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
            7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro"
        }

        for escala in lista_escalas:
            missa = escala.missa

            dia = missa.data.day
            mes = meses[missa.data.month]
            ano = missa.data.year

            mensagem += f"Data: {dia} de {mes} de {ano}\n"
            mensagem += f"Horário: {missa.horario}\n"
            mensagem += f"Comunidade: {missa.comunidade}\n\n"

        # 🔹 LINK ESCALA ESPECÍFICA
        link_especifico = url_for(
            "escala_publica",
            token=lista_escalas[0].token,
            _external=True
        )

        mensagem += "🔗 Acessar escala:\n"
        mensagem += f"{link_especifico}\n\n"

        # 🔹 LINK CALENDÁRIO COMPLETO
        if ministro.token_publico:
            link_calendario = url_for(
                "calendario_publico",
                token=ministro.token_publico,
                _external=True
            )

            mensagem += "📅 Ver meu calendário completo:\n"
            mensagem += f"{link_calendario}\n"

        mensagem_codificada = urllib.parse.quote(mensagem)

        link = f"https://wa.me/55{ministro.telefone}?text={mensagem_codificada}"

        links.append({
            "nome": ministro.nome,
            "link": link
        })

    return render_template("whatsapp_lista.html", links=links)

@app.route("/ministro/<token>")
def ministro_publico(token):

    ministro = Ministro.query.filter_by(token_publico=token).first_or_404()

    escalas = Escala.query.join(Missa).filter(
        Escala.id_ministro == ministro.id
    ).order_by(Missa.data).all()

    return render_template(
        "ministro_publico.html",
        ministro=ministro,
        escalas=escalas
    )

@app.route("/calendario/publico/<token>")
def calendario_publico(token):

    ministro = Ministro.query.filter_by(token_publico=token).first_or_404()

    hoje = date.today()
    mes = int(request.args.get("mes", hoje.month))
    ano = int(request.args.get("ano", hoje.year))

    cal = calendar.monthcalendar(ano, mes)

    missas = Missa.query.filter(
        Missa.id_paroquia == ministro.id_paroquia,
        db.extract("month", Missa.data) == mes,
        db.extract("year", Missa.data) == ano
    ).all()

    estrutura = {}

    for missa in missas:

        dia = missa.data.day

        if dia not in estrutura:
            estrutura[dia] = []

        escalas = Escala.query.filter_by(id_missa=missa.id).all()

        ministros = []
        for e in escalas:
            if e.ministro:
                ministros.append({
                    "nome": e.ministro.nome,
                    "eh_ele": e.ministro.id == ministro.id
                })

        estrutura[dia].append({
            "horario": missa.horario,
            "comunidade": missa.comunidade,
            "ministros": ministros
        })

    return render_template(
        "calendario_publico.html",
        cal=cal,
        estrutura=estrutura,
        mes=mes,
        ano=ano,
        ministro=ministro
    )

@app.route("/ministro/qrcode/<token>")
def qr_ministro(token):

    ministro = Ministro.query.filter_by(token_publico=token).first_or_404()

    link = url_for(
        "calendario_publico",
        token=ministro.token_publico,
        _external=True
    )

    qr = qrcode.make(link)

    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)

    img_base64 = base64.b64encode(buffer.getvalue()).decode()

    return render_template(
        "qr_ministro.html",
        ministro=ministro,
        qr_code=img_base64
    )

@app.route("/paroquia/<int:id>")
def calendario_paroquia(id):

    paroquia = Paroquia.query.get_or_404(id)

    hoje = date.today()
    mes = hoje.month
    ano = hoje.year

    cal = calendar.monthcalendar(ano, mes)

    missas = Missa.query.filter(
        Missa.id_paroquia == id,
        db.extract("month", Missa.data) == mes,
        db.extract("year", Missa.data) == ano
    ).all()

    estrutura = {}

    for missa in missas:
        dia = missa.data.day

        if dia not in estrutura:
            estrutura[dia] = []

        escalas = Escala.query.filter_by(id_missa=missa.id).all()

        nomes = []
        for e in escalas:
            if e.ministro:
                nomes.append(e.ministro.nome)

        estrutura[dia].append({
            "horario": missa.horario,
            "comunidade": missa.comunidade,
            "ministros": nomes
        })

    return render_template(
        "calendario_paroquia.html",
        cal=cal,
        estrutura=estrutura,
        paroquia=paroquia
    )

@app.route("/escala/publica/<token>", methods=["GET", "POST"])
def escala_publica(token):

    escala = Escala.query.filter_by(token=token).first_or_404()

    if request.method == "POST":

        acao = request.form.get("acao")

        if acao == "confirmar":
            escala.confirmado = True

        elif acao == "recusar":
            escala.confirmado = False

        db.session.commit()

        flash("Resposta registrada com sucesso!")

    return render_template(
        "escala_publica.html",
        escala=escala,
        missa=escala.missa,
        ministro=escala.ministro
    )
# ======================
# EXECUÇÃO
# ======================

if __name__ == "__main__":
    app.run()


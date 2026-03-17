import json
from time import sleep
from selenium import webdriver
from selenium.webdriver.common.by import By
import urllib.parse


def semana_do_mes(dia):
    return ((dia - 1) // 7) + 1


def montar_mensagem(ministro):

    from datetime import datetime
    from collections import defaultdict

    def saudacao():
        h = datetime.now().hour
        if h < 12:
            return "Bom dia"
        elif h < 18:
            return "Boa tarde"
        return "Boa noite"

    def semana_do_mes(dia):
        return ((dia - 1) // 7) + 1

    meses_nome = {
        1:"JANEIRO",2:"FEVEREIRO",3:"MARÇO",
        4:"ABRIL",5:"MAIO",6:"JUNHO",
        7:"JULHO",8:"AGOSTO",9:"SETEMBRO",
        10:"OUTUBRO",11:"NOVEMBRO",12:"DEZEMBRO"
    }

    dias_nome = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]

    por_mes = defaultdict(list)

    for m in ministro["missas"]:
        dia, mes, ano = map(int, m["data"].split("/"))
        por_mes[mes].append(m)

    msg = f"{saudacao()} {ministro['nome']} 🙏\n\n"
    msg += "📅 *ESCALA DO PERÍODO*\n\n"

    for mes in sorted(por_mes.keys()):

        msg += "━━━━━━━━━━━━━━━\n"
        msg += f"📌 *{meses_nome[mes]}*\n"

        lista = sorted(
            por_mes[mes],
            key=lambda x: datetime.strptime(x["data"], "%d/%m/%Y")
        )

        for m in lista:

            dia = int(m["data"].split("/")[0])
            semana = semana_do_mes(dia)

            msg += (
                f"🗓 {m['data'][:2]} • {dias_nome[m['dia_semana']]} ({semana}ª semana)\n"
                f"⏰ {m['horario']} | 📍 {m['comunidade']}\n\n"
            )

    msg += "━━━━━━━━━━━━━━━\n\n"
    msg += "🙏 Deus abençoe seu serviço!"

    return msg

def enviar(driver, numero, mensagem):

    msg = urllib.parse.quote(mensagem)
    url = f"https://web.whatsapp.com/send?phone=55{numero}&text={msg}"

    driver.get(url)
    sleep(10)

    try:
        botao = driver.find_element(By.XPATH, '//span[@data-icon="send"]')
        botao.click()
        sleep(3)
        return True
    except:
        return False


def main():

    # 🔥 arquivo exportado do sistema
    with open("dados_whatsapp.json", "r", encoding="utf-8") as f:
        dados = json.load(f)

    driver = webdriver.Chrome()
    driver.get("https://web.whatsapp.com")

    input("Escaneie QR Code e pressione ENTER...")

    for ministro in dados:

        mensagem = montar_mensagem(ministro)
        
        if enviar(driver, ministro["telefone"], mensagem):
            print(f"✅ {ministro['nome']}")
        else:
            print(f"❌ {ministro['nome']}")

        sleep(2)


if __name__ == "__main__":
    main()
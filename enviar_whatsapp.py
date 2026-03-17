import json
from time import sleep
from selenium import webdriver
from selenium.webdriver.common.by import By
import urllib.parse


def semana_do_mes(dia):
    return ((dia - 1) // 7) + 1


def montar_mensagem(ministro):

    mensagem = f"Olá {ministro['nome']} 🙏\n\n"
    mensagem += "Segue sua escala do período:\n\n"

    dias = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]

    for m in ministro["missas"]:

        dia = int(m["data"].split("/")[0])
        semana = semana_do_mes(dia)

        mensagem += (
            f"{m['data']} - "
            f"{dias[m['dia_semana']]} ({semana}ª semana)\n"
            f"{m['horario']} - {m['comunidade']}\n\n"
        )

    mensagem += "Deus abençoe 🙏"

    return mensagem


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
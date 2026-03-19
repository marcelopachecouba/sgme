import json
from time import sleep

from selenium.webdriver.common.by import By
import urllib.parse

from services.relatorio_service import montar_mensagem  # ✅ usa a correta


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

    with open("dados_whatsapp.json", "r", encoding="utf-8") as f:
        dados = json.load(f)

   
    driver.get("https://web.whatsapp.com")

    input("Escaneie QR Code e pressione ENTER...")

    for ministro in dados:

        mensagem = montar_mensagem(ministro)  # ✅ aqui usa service

        if enviar(driver, ministro["telefone"], mensagem):
            print(f"✅ {ministro['nome']}")
        else:
            print(f"❌ {ministro['nome']}")

        sleep(2)


if __name__ == "__main__":
    main()
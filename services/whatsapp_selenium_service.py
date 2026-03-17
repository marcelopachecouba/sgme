from selenium import webdriver
from selenium.webdriver.common.by import By
from time import sleep
import urllib.parse

driver = None

def iniciar_driver():
    global driver

    if driver is None:
        driver = webdriver.Chrome()
        driver.get("https://web.whatsapp.com")
        input("👉 Escaneie o QR Code e pressione ENTER...")

def enviar_mensagem(numero, mensagem):

    global driver

    mensagem_codificada = urllib.parse.quote(mensagem)

    url = f"https://web.whatsapp.com/send?phone=55{numero}&text={mensagem_codificada}"

    driver.get(url)

    sleep(10)

    try:
        botao = driver.find_element(By.XPATH, '//span[@data-icon="send"]')
        botao.click()
        sleep(3)
    except:
        print(f"Erro ao enviar para {numero}")
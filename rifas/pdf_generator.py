from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4
from pathlib import Path
from flask import current_app


def generate_tickets_pdf(*, pagamento, rifas, cliente) -> str:
    output_dir = Path(current_app.config["RIFA_PDF_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"canhotos-{pagamento.id}.pdf"

    bg_path = Path(current_app.root_path) / "static/img/rifas/modelo.png"
    background = ImageReader(str(bg_path))

    page_width, page_height = A4

    # 🔥 TAMANHO DO BILHETE
    ticket_width = page_width
    ticket_height = 160  # ajustado para caber 5

    pdf = canvas.Canvas(str(output_path), pagesize=A4)

    nome = (cliente.nome or "").upper()
    telefone = cliente.telefone or ""
    endereco = (cliente.endereco or "").upper()
    data = pagamento.campanha.data_sorteio.strftime("%d/%m/%Y")

    for i, rifa in enumerate(rifas):

        pos_y = page_height - ((i % 5 + 1) * ticket_height)

        # NOVA PÁGINA A CADA 5
        if i > 0 and i % 5 == 0:
            pdf.showPage()

        # FUNDO
        pdf.drawImage(background, 0, pos_y, width=ticket_width, height=ticket_height)

        numero = f"{rifa.numero:04d}"

        # =========================
        # AJUSTE RELATIVO AO BLOCO
        # =========================

        base_y = pos_y

        # NOME
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(150 + 60+50+30, base_y + 120 + 20, nome[:42])

        # TELEFONE
        pdf.setFont("Helvetica", 9)
        pdf.drawString(190 + 20+20+20, base_y + 95, telefone[:20])

        # ENDEREÇO
        pdf.setFont("Helvetica", 8)
        pdf.drawString(150 + 40+120, base_y + 75 + 50, endereco[:50])

        # NUMERO
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawRightString(page_width - 20, base_y + 120 + 25, numero)

        # DATA
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawRightString(page_width - 20, base_y + 10, f"Sorteio: {data}")

        # ID
        pdf.setFont("Helvetica", 6)
        pdf.drawString(20, base_y + 5, f"ID: {pagamento.id[:10]}")

    pdf.save()
    return str(output_path)
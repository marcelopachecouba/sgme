import logging
from pathlib import Path

from flask import current_app
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


logger = logging.getLogger(__name__)


def generate_tickets_pdf(*, pagamento, rifas, cliente) -> str:
    output_dir = Path(current_app.config["RIFA_PDF_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"canhotos-{pagamento.id}.pdf"

    pdf = canvas.Canvas(str(output_path), pagesize=A4)
    largura, altura = A4
    box_width = 90 * mm
    box_height = 45 * mm
    margin_x = 15 * mm
    margin_y = 15 * mm
    columns = 2
    rows = 5

    for index, rifa in enumerate(rifas):
        col = index % columns
        row = (index // columns) % rows
        page_index = index // (columns * rows)

        if index > 0 and index % (columns * rows) == 0:
            pdf.showPage()

        x = margin_x + col * (box_width + 10 * mm)
        y = altura - margin_y - ((row + 1) * box_height) - row * 8 * mm

        pdf.roundRect(x, y, box_width, box_height, 4 * mm)
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(x + 8 * mm, y + box_height - 12 * mm, "Canhoto da Rifa")
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(x + 8 * mm, y + box_height - 24 * mm, f"Numero: {rifa.numero:04d}")
        pdf.setFont("Helvetica", 11)
        pdf.drawString(x + 8 * mm, y + box_height - 34 * mm, f"Comprador: {cliente.nome}")
        pdf.drawString(x + 8 * mm, y + box_height - 41 * mm, f"Telefone: {cliente.telefone}")
        pdf.drawString(x + 8 * mm, y + 6 * mm, f"Pagamento: {pagamento.id}")

    pdf.save()
    logger.info("PDF de canhotos gerado em %s", output_path)
    return str(output_path)

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
LOGO_PATH = STATIC_DIR / "img" / "LOGO.jpg"

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1350
CALENDAR_WIDTH = 1800
CALENDAR_HEIGHT = 1350

MESES_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Marco",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


def _font_candidates(name):
    windows_dir = Path("C:/Windows/Fonts")
    linux_dir = Path("/usr/share/fonts/truetype")

    families = {
        "title": [
            windows_dir / "georgiab.ttf",
            windows_dir / "timesbd.ttf",
            linux_dir / "dejavu/DejaVuSerif-Bold.ttf",
        ],
        "subtitle": [
            windows_dir / "georgia.ttf",
            windows_dir / "times.ttf",
            linux_dir / "dejavu/DejaVuSerif.ttf",
        ],
        "text": [
            windows_dir / "arial.ttf",
            windows_dir / "calibri.ttf",
            linux_dir / "dejavu/DejaVuSans.ttf",
        ],
        "text_bold": [
            windows_dir / "arialbd.ttf",
            windows_dir / "calibrib.ttf",
            linux_dir / "dejavu/DejaVuSans-Bold.ttf",
        ],
    }
    return families.get(name, [])


def _load_font(kind, size):
    for path in _font_candidates(kind):
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap_text(draw, text, font, max_width):
    words = (text or "").split()
    if not words:
        return [""]

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
    lines.append(current)
    return lines


def _draw_multiline(draw, lines, xy, font, fill, spacing=8):
    x, y = xy
    current_y = y
    for line in lines:
        draw.text((x, current_y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, current_y), line, font=font)
        current_y = bbox[3] + spacing
    return current_y


def _draw_centered_multiline(draw, lines, x_center, y, font, fill, spacing=8):
    current_y = y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = x_center - ((bbox[2] - bbox[0]) / 2)
        draw.text((x, current_y), line, font=font, fill=fill)
        current_y += (bbox[3] - bbox[1]) + spacing
    return current_y


def _rounded_box(size, radius, fill, outline=None, outline_width=0):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1),
        radius=radius,
        fill=fill,
        outline=outline,
        width=outline_width,
    )
    return img


def _apply_logo(canvas):
    if not LOGO_PATH.exists():
        return

    try:
        logo = Image.open(LOGO_PATH).convert("RGB")
    except OSError:
        return

    logo = ImageOps.fit(logo, (130, 130))
    mask = Image.new("L", (130, 130), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, 129, 129), fill=255)

    badge = Image.new("RGBA", (154, 154), (0, 0, 0, 0))
    badge_draw = ImageDraw.Draw(badge)
    badge_draw.ellipse((0, 0, 153, 153), fill=(255, 250, 240, 245), outline=(197, 157, 93, 255), width=4)
    badge.paste(logo, (12, 12), mask)
    canvas.alpha_composite(badge, (CANVAS_WIDTH - 200, 22))


def _background():
    bg = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), "#f8ecd6")
    draw = ImageDraw.Draw(bg)

    for y in range(CANVAS_HEIGHT):
        mix = y / max(1, CANVAS_HEIGHT - 1)
        r = int(248 * (1 - mix) + 160 * mix)
        g = int(236 * (1 - mix) + 132 * mix)
        b = int(214 * (1 - mix) + 96 * mix)
        draw.line((0, y, CANVAS_WIDTH, y), fill=(r, g, b, 255))

    lights = [
        (120, 120, 120), (240, 260, 90), (420, 180, 130), (760, 120, 110),
        (900, 270, 95), (200, 560, 145), (860, 620, 170), (540, 470, 120),
    ]
    for x, y, radius in lights:
        glow = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        box = (x - radius, y - radius, x + radius, y + radius)
        glow_draw.ellipse(box, fill=(255, 250, 236, 110))
        bg = Image.alpha_composite(bg, glow.filter(ImageFilter.GaussianBlur(26)))

    return bg


def _background_calendar(height=CALENDAR_HEIGHT):
    bg = Image.new("RGBA", (CALENDAR_WIDTH, height), "#fbf2df")
    draw = ImageDraw.Draw(bg)

    for y in range(height):
        mix = y / max(1, height - 1)
        r = int(251 * (1 - mix) + 226 * mix)
        g = int(242 * (1 - mix) + 208 * mix)
        b = int(223 * (1 - mix) + 186 * mix)
        draw.line((0, y, CALENDAR_WIDTH, y), fill=(r, g, b, 255))

    for x, y, radius in [
        (180, 120, 130), (480, 210, 115), (830, 120, 120), (1220, 160, 150), (1550, 220, 125)
    ]:
        glow = Image.new("RGBA", (CALENDAR_WIDTH, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 248, 233, 120))
        bg = Image.alpha_composite(bg, glow.filter(ImageFilter.GaussianBlur(28)))

    return bg


def gerar_imagem_escala_missa(missa, escalas, nome_paroquia=""):
    ministros = [escala.ministro.nome.strip() for escala in escalas if getattr(escala, "ministro", None) and getattr(escala.ministro, "nome", None)]

    bg = _background()
    _apply_logo(bg)

    panel_x = 85
    panel_y = 180
    panel_w = CANVAS_WIDTH - 170
    panel_h = CANVAS_HEIGHT - 255

    shadow = _rounded_box((panel_w, panel_h), 44, (80, 45, 20, 70))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    bg.alpha_composite(shadow, (panel_x + 10, panel_y + 20))

    panel = _rounded_box(
        (panel_w, panel_h),
        44,
        (250, 243, 227, 238),
        outline=(198, 160, 98, 255),
        outline_width=4,
    )
    bg.alpha_composite(panel, (panel_x, panel_y))

    title_box = _rounded_box(
        (panel_w - 110, 110),
        50,
        (251, 245, 231, 255),
        outline=(202, 164, 103, 255),
        outline_width=4,
    )
    bg.alpha_composite(title_box, (panel_x + 55, panel_y - 56))

    draw = ImageDraw.Draw(bg)
    title_font = _load_font("title", 64)
    section_font = _load_font("title", 38)
    label_font = _load_font("text_bold", 34)
    text_font = _load_font("text", 34)
    small_font = _load_font("text", 28)
    bullet_font = _load_font("text_bold", 38)

    _draw_centered_multiline(draw, ["ESCALA DA MISSA"], CANVAS_WIDTH / 2, panel_y - 34, title_font, "#4f331d")

    left_x = panel_x + 100
    info_y = panel_y + 102
    info_gap = 68

    draw.text((left_x, info_y), "Data:", font=label_font, fill="#4a2f1b")
    draw.text((left_x + 120, info_y), missa.data.strftime("%d/%m/%Y"), font=text_font, fill="#2f2419")

    draw.text((left_x, info_y + info_gap), "Horario:", font=label_font, fill="#4a2f1b")
    draw.text((left_x + 165, info_y + info_gap), str(missa.horario or "-"), font=text_font, fill="#2f2419")

    draw.text((left_x, info_y + (info_gap * 2)), "Comunidade:", font=label_font, fill="#4a2f1b")
    draw.text((left_x + 235, info_y + (info_gap * 2)), str(missa.comunidade or "-"), font=text_font, fill="#2f2419")

    count_text = f"MINISTROS ESCALADOS ({len(ministros)}/{missa.qtd_ministros or len(ministros)})"
    draw.text((panel_x + 60, panel_y + 380), count_text, font=section_font, fill="#40592f")

    list_x = panel_x + 82
    list_y = panel_y + 445
    available_height = panel_h - 520
    if len(ministros) > 9:
        item_font = _load_font("text", 30)
        item_gap = 42
    else:
        item_font = _load_font("text", 36)
        item_gap = 50

    current_y = list_y
    max_text_width = panel_w - 180
    for nome in ministros:
        wrapped = _wrap_text(draw, nome.upper(), item_font, max_text_width - 40)
        draw.text((list_x, current_y), "•", font=bullet_font, fill="#536d39")
        current_y = _draw_multiline(
            draw,
            wrapped,
            (list_x + 30, current_y - 2),
            item_font,
            "#23180f",
            spacing=4,
        ) + 10
        if current_y > list_y + available_height:
            break

    buffer = BytesIO()
    bg.convert("RGB").save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer


def gerar_imagem_calendario_escala(mes, ano, cal, estrutura):
    title_font = _load_font("title", 54)
    subtitle_font = _load_font("text_bold", 28)
    weekday_font = _load_font("text_bold", 24)
    day_font = _load_font("text_bold", 24)
    event_font = _load_font("text", 18)
    event_bold_font = _load_font("text_bold", 18)

    measure = ImageDraw.Draw(Image.new("RGBA", (CALENDAR_WIDTH, 100), (0, 0, 0, 0)))

    margin_x = 52
    top_y = 210
    header_h = 58
    rows = max(1, len(cal))
    col_gap = 10
    row_gap = 10
    cell_w = int((CALENDAR_WIDTH - (margin_x * 2) - (col_gap * 6)) / 7)
    cell_padding_top = 44

    calendar_blocks = {}
    row_heights = []
    for row_idx, semana in enumerate(cal):
        max_row_height = 180
        for dia in semana:
            if not dia:
                continue
            eventos = sorted(estrutura.get(dia, []), key=lambda item: item.get("horario") or "")
            blocks = []
            content_height = cell_padding_top
            for missa in eventos:
                lines = []
                cabecalho = f"{missa.get('horario') or '-'} - {missa.get('comunidade') or '-'}"
                lines.extend(_wrap_text(measure, cabecalho, event_bold_font, cell_w - 26))
                ministros = [m.get("nome", "").strip() for m in missa.get("ministros", []) if m.get("nome")]
                if ministros:
                    for ministro in ministros:
                        lines.extend(_wrap_text(measure, f"- {ministro}", event_font, cell_w - 26))
                else:
                    lines.append("- Sem ministros")

                block_h = 12
                for idx, line in enumerate(lines):
                    font = event_bold_font if idx == 0 else event_font
                    bbox = measure.textbbox((0, 0), line, font=font)
                    block_h += (bbox[3] - bbox[1]) + 1

                blocks.append({"lines": lines, "height": block_h})
                content_height += block_h + 6

            if not eventos:
                content_height = max(content_height, 88)

            calendar_blocks[(row_idx, dia)] = blocks
            max_row_height = max(max_row_height, content_height + 12)
        row_heights.append(max_row_height)

    total_height = top_y + header_h + 14 + sum(row_heights) + (row_gap * max(0, rows - 1)) + 48
    total_height = max(total_height, CALENDAR_HEIGHT)
    bg = _background_calendar(total_height)

    if LOGO_PATH.exists():
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            logo = ImageOps.fit(logo, (120, 120))
            mask = Image.new("L", (120, 120), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, 119, 119), fill=255)
            badge = Image.new("RGBA", (144, 144), (0, 0, 0, 0))
            badge_draw = ImageDraw.Draw(badge)
            badge_draw.ellipse((0, 0, 143, 143), fill=(255, 251, 244, 240), outline=(194, 157, 96, 255), width=4)
            badge.paste(logo, (12, 12), mask)
            bg.alpha_composite(badge, (CALENDAR_WIDTH - 180, 36))
        except OSError:
            pass

    draw = ImageDraw.Draw(bg)
    title_box = _rounded_box((780, 92), 42, (251, 245, 231, 250), outline=(202, 164, 103, 255), outline_width=4)
    bg.alpha_composite(title_box, (90, 40))
    _draw_centered_multiline(draw, ["CALENDARIO DA ESCALA"], 480, 56, title_font, "#4f331d", spacing=4)
    draw.text((94, 152), f"{MESES_PT.get(mes, str(mes))} de {ano}", font=subtitle_font, fill="#6a4a26")

    dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
    for col, nome in enumerate(dias_semana):
        x = margin_x + col * (cell_w + col_gap)
        header = _rounded_box((cell_w, header_h), 18, (132, 92, 49, 230))
        bg.alpha_composite(header, (x, top_y))
        bbox = draw.textbbox((0, 0), nome, font=weekday_font)
        tx = x + (cell_w - (bbox[2] - bbox[0])) / 2
        ty = top_y + (header_h - (bbox[3] - bbox[1])) / 2 - 2
        draw.text((tx, ty), nome, font=weekday_font, fill="#fff8ee")

    start_y = top_y + header_h + 14
    current_row_y = start_y
    for row_idx, semana in enumerate(cal):
        cell_h = row_heights[row_idx]
        y = current_row_y
        for col_idx, dia in enumerate(semana):
            x = margin_x + col_idx * (cell_w + col_gap)
            cell = _rounded_box((cell_w, cell_h), 22, (255, 251, 244, 220), outline=(210, 184, 143, 255), outline_width=2)
            bg.alpha_composite(cell, (x, y))
            if not dia:
                continue

            draw.text((x + 14, y + 10), str(dia), font=day_font, fill="#5a3a18")
            inner_y = y + cell_padding_top
            for bloco in calendar_blocks.get((row_idx, dia), []):
                event_box = _rounded_box((cell_w - 18, bloco["height"]), 14, (248, 239, 221, 255), outline=(223, 203, 170, 255), outline_width=1)
                bg.alpha_composite(event_box, (x + 9, inner_y))
                text_y = inner_y + 7
                first = True
                for line in bloco["lines"]:
                    font = event_bold_font if first else event_font
                    fill = "#3f2915" if first else "#2c2219"
                    draw.text((x + 18, text_y), line, font=font, fill=fill)
                    bbox = draw.textbbox((0, 0), line, font=font)
                    text_y += (bbox[3] - bbox[1]) + 1
                    first = False
                inner_y += bloco["height"] + 6
        current_row_y += cell_h + row_gap

    buffer = BytesIO()
    bg.convert("RGB").save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer

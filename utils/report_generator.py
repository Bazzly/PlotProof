"""
PDF risk report generation for PlotProof, using ReportLab's canvas API.

Visually matches the web app: same status colors (theme.STATUS), same
accent blue, same risk icon shapes - a user shouldn't see a different
color language depending on whether they're looking at the page or the
downloaded report. Beyond color, this adds the things a "real" report
has and the plain-text original didn't: a risk gauge, a schematic
diagram of the plot boundary, a proper coordinates table, and clickable
contact links in the footer.
"""

import io
import math
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from utils import theme

PAGE_WIDTH, PAGE_HEIGHT = letter
MARGIN = 0.55 * inch
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

WHATSAPP_LINK = os.environ.get("WHATSAPP_LINK", "https://chat.whatsapp.com/KrMfFgenA5u50QTASfyyro?s=cl&p=a&ilr=1")
CALENDLY_LINK = os.environ.get("CALENDLY_LINK", "https://calendly.com/bazeet4love")

ACCENT = colors.HexColor(theme.ACCENT_LIGHT)
INK_PRIMARY = colors.HexColor(theme.INK["primary"])
INK_SECONDARY = colors.HexColor(theme.INK["secondary"])
INK_MUTED = colors.HexColor(theme.INK["muted"])
BORDER = colors.HexColor(theme.INK["border"])
SURFACE = colors.HexColor(theme.INK["surface"])
WHITE = colors.white
STATUS_COLORS = {k: colors.HexColor(v) for k, v in theme.STATUS.items()}


def _tint(color: colors.Color, amount: float) -> colors.Color:
    """Lightens a color toward white - used for soft status-tinted backgrounds."""
    return colors.Color(
        color.red + (1 - color.red) * amount,
        color.green + (1 - color.green) * amount,
        color.blue + (1 - color.blue) * amount,
    )


def _wrapped_lines(c: canvas.Canvas, text: str, font: str, size: int, max_width: float) -> List[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if c.stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _new_page(c: canvas.Canvas) -> float:
    _draw_footer(c)
    c.showPage()
    return PAGE_HEIGHT - MARGIN


def _draw_header(c: canvas.Canvas, risk_level: str) -> float:
    band_height = 1.05 * inch
    c.setFillColor(ACCENT)
    c.rect(0, PAGE_HEIGHT - band_height, PAGE_WIDTH, band_height, stroke=0, fill=1)

    # Logo mark: two peaks, matching the app's icon (icons.py "logo" path).
    logo_cx, logo_cy, s = MARGIN + 0.3 * inch, PAGE_HEIGHT - band_height / 2, 11
    c.setStrokeColor(WHITE)
    c.setLineWidth(2.2)
    c.setLineJoin(1)
    c.setLineCap(1)
    path = c.beginPath()
    path.moveTo(logo_cx - s, logo_cy - s * 0.7)
    path.lineTo(logo_cx - s / 3, logo_cy + s)
    path.lineTo(logo_cx, logo_cy)
    path.lineTo(logo_cx + s / 3, logo_cy + s)
    path.lineTo(logo_cx + s, logo_cy - s * 0.7)
    c.drawPath(path, stroke=1, fill=0)

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(MARGIN + 0.62 * inch, PAGE_HEIGHT - 0.48 * inch, "PlotProof")
    c.setFont("Helvetica", 10.5)
    c.drawString(MARGIN + 0.62 * inch, PAGE_HEIGHT - 0.68 * inch, "Land Boundary Risk Report")

    c.setFont("Helvetica", 8.5)
    meta = f"Generated {datetime.now().strftime('%d %b %Y, %H:%M')}"
    c.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 0.42 * inch, meta)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 0.58 * inch, f"RISK LEVEL: {risk_level.upper()}")

    return PAGE_HEIGHT - band_height - 0.3 * inch


def _draw_status_icon(c: canvas.Canvas, cx: float, cy: float, r: float, status: str) -> None:
    color = STATUS_COLORS[status]
    c.setFillColor(color)
    c.setStrokeColor(color)
    if status == "good":
        c.circle(cx, cy, r, stroke=0, fill=1)
        c.setStrokeColor(WHITE)
        c.setLineWidth(2)
        c.setLineCap(1)
        c.setLineJoin(1)
        path = c.beginPath()
        path.moveTo(cx - r * 0.45, cy - r * 0.05)
        path.lineTo(cx - r * 0.1, cy - r * 0.4)
        path.lineTo(cx + r * 0.5, cy + r * 0.35)
        c.drawPath(path, stroke=1, fill=0)
    elif status == "warning":
        path = c.beginPath()
        path.moveTo(cx, cy + r)
        path.lineTo(cx - r, cy - r * 0.8)
        path.lineTo(cx + r, cy - r * 0.8)
        path.close()
        c.drawPath(path, stroke=0, fill=1)
        c.setFillColor(WHITE)
        c.rect(cx - 1, cy - r * 0.55, 2, r * 0.6, stroke=0, fill=1)
        c.circle(cx, cy - r * 0.62, 1.4, stroke=0, fill=1)
    else:
        c.circle(cx, cy, r, stroke=0, fill=1)
        c.setFillColor(WHITE)
        c.rect(cx - 1.1, cy - r * 0.15, 2.2, r * 0.75, stroke=0, fill=1)
        c.circle(cx, cy - r * 0.55, 1.4, stroke=0, fill=1)


def _draw_risk_badge(c: canvas.Canvas, y: float, risk_level: str) -> float:
    status = theme.RISK_TO_STATUS[risk_level]
    color = STATUS_COLORS[status]
    height = 0.55 * inch
    c.setFillColor(_tint(color, 0.88))
    c.roundRect(MARGIN, y - height, CONTENT_WIDTH, height, 6, stroke=0, fill=1)
    c.setStrokeColor(color)
    c.setLineWidth(2.5)
    c.line(MARGIN, y - height, MARGIN, y)

    _draw_status_icon(c, MARGIN + 0.35 * inch, y - height / 2, 10, status)
    c.setFillColor(INK_PRIMARY)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGIN + 0.65 * inch, y - height / 2 - 5, f"Risk Level: {risk_level}")
    return y - height - 0.28 * inch


def _draw_risk_gauge(c: canvas.Canvas, y: float, risk_level: str) -> float:
    labels = ["Low", "Medium", "High"]
    active_index = labels.index(risk_level)
    seg_gap = 4
    seg_w = (CONTENT_WIDTH - seg_gap * 2) / 3
    seg_h = 0.2 * inch

    for i, label in enumerate(labels):
        x = MARGIN + i * (seg_w + seg_gap)
        status = theme.RISK_TO_STATUS[label]
        color = STATUS_COLORS[status]
        c.setFillColor(color if i == active_index else _tint(color, 0.75))
        c.roundRect(x, y - seg_h, seg_w, seg_h, 3, stroke=0, fill=1)
        c.setFont("Helvetica-Bold" if i == active_index else "Helvetica", 8)
        c.setFillColor(INK_PRIMARY if i == active_index else INK_MUTED)
        c.drawCentredString(x + seg_w / 2, y - seg_h - 11, label.upper())

    # Pointer triangle above the active segment.
    px = MARGIN + active_index * (seg_w + seg_gap) + seg_w / 2
    c.setFillColor(INK_PRIMARY)
    path = c.beginPath()
    path.moveTo(px - 4, y + 8)
    path.lineTo(px + 4, y + 8)
    path.lineTo(px, y + 1)
    path.close()
    c.drawPath(path, stroke=0, fill=1)

    return y - seg_h - 0.38 * inch


def _draw_plot_diagram(c: canvas.Canvas, y: float, points: List[Tuple[float, float]]) -> float:
    box_size = 1.9 * inch
    box_x = PAGE_WIDTH - MARGIN - box_size
    box_y = y - box_size

    c.setFillColor(SURFACE)
    c.setStrokeColor(BORDER)
    c.setLineWidth(1)
    c.roundRect(box_x, box_y, box_size, box_size, 8, stroke=1, fill=1)

    c.setFillColor(INK_SECONDARY)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(box_x + 8, box_y + box_size - 14, "PLOT BOUNDARY")
    c.setFont("Helvetica", 6.5)
    c.setFillColor(INK_MUTED)
    c.drawString(box_x + 8, box_y + box_size - 24, "Schematic - not to scale")

    # North arrow.
    nx, ny = box_x + box_size - 18, box_y + box_size - 30
    c.setStrokeColor(INK_MUTED)
    c.setFillColor(INK_MUTED)
    c.setLineWidth(1)
    c.line(nx, ny - 10, nx, ny)
    p = c.beginPath()
    p.moveTo(nx - 3, ny - 3)
    p.lineTo(nx, ny + 3)
    p.lineTo(nx + 3, ny - 3)
    c.drawPath(p, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(nx, ny + 5, "N")

    pad = 0.42 * inch
    inner = box_size - 2 * pad
    cx, cy = box_x + box_size / 2, box_y + box_size / 2 - 0.06 * inch

    if len(points) >= 3:
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        span_lat = max(max(lats) - min(lats), 1e-9)
        span_lon = max(max(lons) - min(lons), 1e-9)
        scale = inner / max(span_lat, span_lon)
        mid_lat = (max(lats) + min(lats)) / 2
        mid_lon = (max(lons) + min(lons)) / 2

        coords = [(cx + (lon - mid_lon) * scale, cy + (lat - mid_lat) * scale) for lat, lon in points]
        c.setFillColor(_tint(ACCENT, 0.65))
        c.setStrokeColor(ACCENT)
        c.setLineWidth(1.6)
        path = c.beginPath()
        path.moveTo(*coords[0])
        for px_, py_ in coords[1:]:
            path.lineTo(px_, py_)
        path.close()
        c.drawPath(path, stroke=1, fill=1)

        c.setFillColor(ACCENT)
        for px_, py_ in coords:
            c.circle(px_, py_, 2.2, stroke=0, fill=1)
    else:
        r = inner / 2.4
        c.setFillColor(_tint(ACCENT, 0.65))
        c.setStrokeColor(ACCENT)
        c.setDash(3, 2)
        c.setLineWidth(1.6)
        c.circle(cx, cy, r, stroke=1, fill=1)
        c.setDash()
        c.setFillColor(ACCENT)
        c.circle(cx, cy, 2.2, stroke=0, fill=1)
        c.setFont("Helvetica-Oblique", 6.5)
        c.setFillColor(INK_MUTED)
        c.drawCentredString(cx, box_y + 10, "Estimated extent (buffer)")

    return box_x


def _draw_card(
    c: canvas.Canvas,
    y: float,
    title: str,
    items: List[str],
    bullet_color: colors.Color,
    max_x: float,
) -> float:
    width = max_x - MARGIN
    padding = 10
    font, size, gap = "Helvetica", 9, 13

    wrapped_items = []
    for item in items:
        wrapped_items.append(_wrapped_lines(c, item, font, size, width - padding * 2 - 12))

    title_h = 16
    body_h = sum(len(w) for w in wrapped_items) * gap + (len(items) - 1) * 4 if items else 12
    card_h = title_h + body_h + padding * 2

    if y - card_h < MARGIN + 0.4 * inch:
        y = _new_page(c)

    c.setFillColor(SURFACE)
    c.setStrokeColor(BORDER)
    c.roundRect(MARGIN, y - card_h, width, card_h, 6, stroke=1, fill=1)

    ty = y - padding - 9
    c.setFillColor(INK_PRIMARY)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(MARGIN + padding, ty, title)
    ty -= title_h

    c.setFont(font, size)
    for wrapped in wrapped_items:
        c.setFillColor(bullet_color)
        c.circle(MARGIN + padding + 3, ty + 3, 2.2, stroke=0, fill=1)
        c.setFillColor(INK_SECONDARY)
        for i, wline in enumerate(wrapped):
            c.drawString(MARGIN + padding + 12, ty, wline)
            ty -= gap
        ty -= 4

    return y - card_h - 0.2 * inch


def _draw_coordinates_table(c: canvas.Canvas, y: float, points: List[Tuple[float, float]]) -> float:
    if not points:
        return y

    row_h = 14
    col_x = [MARGIN, MARGIN + 0.7 * inch, MARGIN + 3.1 * inch]
    table_w = CONTENT_WIDTH
    header_h = 16
    table_h = header_h + row_h * len(points)

    if y - table_h < MARGIN + 0.4 * inch:
        y = _new_page(c)

    c.setFillColor(INK_PRIMARY)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(MARGIN, y - 9, "Coordinates Assessed")
    y -= 20

    top = y
    c.setFillColor(_tint(ACCENT, 0.85))
    c.rect(MARGIN, top - header_h, table_w, header_h, stroke=0, fill=1)
    c.setFillColor(INK_PRIMARY)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(col_x[0] + 4, top - header_h + 5, "#")
    c.drawString(col_x[1] + 4, top - header_h + 5, "Latitude")
    c.drawString(col_x[2] + 4, top - header_h + 5, "Longitude")

    c.setFont("Helvetica", 8)
    row_top = top - header_h
    for i, (lat, lon) in enumerate(points):
        if i % 2 == 1:
            c.setFillColor(_tint(INK_MUTED, 0.92))
            c.rect(MARGIN, row_top - row_h, table_w, row_h, stroke=0, fill=1)
        c.setFillColor(INK_SECONDARY)
        c.drawString(col_x[0] + 4, row_top - row_h + 4, str(i + 1))
        c.drawString(col_x[1] + 4, row_top - row_h + 4, f"{lat:.6f}")
        c.drawString(col_x[2] + 4, row_top - row_h + 4, f"{lon:.6f}")
        row_top -= row_h

    c.setStrokeColor(BORDER)
    c.setLineWidth(0.75)
    c.rect(MARGIN, top - table_h, table_w, table_h, stroke=1, fill=0)

    return top - table_h - 0.25 * inch


def _draw_plots_table(c: canvas.Canvas, y: float, result: Dict[str, Any]) -> float:
    """Overlapping/nearby plots, each with a status swatch - the same data
    already summarized in the findings text, but a scannable table reads
    faster than prose once there's more than one conflicting plot."""
    rows = [("critical", "Overlapping", p, f"{p['overlap_area_sqm']:.0f} m²") for p in result["overlaps"]]
    rows += [("warning", "Nearby", p, f"{p['distance_m']:.0f} m away") for p in result["proximate"]]
    if not rows:
        return y

    row_h = 16
    header_h = 16
    col_x = [MARGIN, MARGIN + 0.18 * inch, MARGIN + 1.35 * inch, MARGIN + 3.2 * inch]
    table_h = header_h + row_h * len(rows)

    if y - table_h < MARGIN + 0.4 * inch:
        y = _new_page(c)

    c.setFillColor(INK_PRIMARY)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(MARGIN, y - 9, "Conflicting & Nearby Plots")
    y -= 20

    top = y
    c.setFillColor(_tint(ACCENT, 0.85))
    c.rect(MARGIN, top - header_h, CONTENT_WIDTH, header_h, stroke=0, fill=1)
    c.setFillColor(INK_PRIMARY)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(col_x[1] + 4, top - header_h + 5, "Status")
    c.drawString(col_x[2] + 4, top - header_h + 5, "Plot")
    c.drawString(col_x[3] + 4, top - header_h + 5, "Detail")

    row_top = top - header_h
    c.setFont("Helvetica", 8)
    for i, (status, label, plot, detail) in enumerate(rows):
        if i % 2 == 1:
            c.setFillColor(_tint(INK_MUTED, 0.92))
            c.rect(MARGIN, row_top - row_h, CONTENT_WIDTH, row_h, stroke=0, fill=1)
        c.setFillColor(STATUS_COLORS[status])
        c.circle(col_x[0] + 6, row_top - row_h / 2, 3.2, stroke=0, fill=1)
        c.setFillColor(INK_SECONDARY)
        c.drawString(col_x[1] + 4, row_top - row_h + 5, label)
        c.drawString(col_x[2] + 4, row_top - row_h + 5, f"{plot['plot_ref']} ({plot['owner']})")
        c.drawString(col_x[3] + 4, row_top - row_h + 5, detail)
        row_top -= row_h

    c.setStrokeColor(BORDER)
    c.setLineWidth(0.75)
    c.rect(MARGIN, top - table_h, CONTENT_WIDTH, table_h, stroke=1, fill=0)

    return top - table_h - 0.25 * inch


def _draw_footer(c: canvas.Canvas) -> None:
    band_h = 0.55 * inch
    c.setFillColor(INK_PRIMARY)
    c.rect(0, 0, PAGE_WIDTH, band_h, stroke=0, fill=1)

    c.setFillColor(WHITE)
    c.setFont("Helvetica", 7.5)
    c.drawString(
        MARGIN, band_h - 16,
        "Automated preliminary screening, not a certified survey or legal opinion.",
    )
    c.drawString(MARGIN, band_h - 27, "Always get a licensed surveyor's verification before a property transaction.")

    link_y = band_h - 27
    whatsapp_label = "Chat on WhatsApp"
    calendly_label = "Book a consultation"
    c.setFont("Helvetica-Bold", 7.5)
    whatsapp_x = PAGE_WIDTH - MARGIN - c.stringWidth(calendly_label, "Helvetica-Bold", 7.5) - 18 - c.stringWidth(whatsapp_label, "Helvetica-Bold", 7.5)
    c.drawString(whatsapp_x, link_y, whatsapp_label)
    c.linkURL(
        WHATSAPP_LINK,
        (whatsapp_x, link_y - 2, whatsapp_x + c.stringWidth(whatsapp_label, "Helvetica-Bold", 7.5), link_y + 8),
        relative=0,
    )
    calendly_x = PAGE_WIDTH - MARGIN - c.stringWidth(calendly_label, "Helvetica-Bold", 7.5)
    c.drawString(calendly_x, link_y, calendly_label)
    c.linkURL(
        CALENDLY_LINK,
        (calendly_x, link_y - 2, calendly_x + c.stringWidth(calendly_label, "Helvetica-Bold", 7.5), link_y + 8),
        relative=0,
    )


def generate_pdf_report(
    result: Dict[str, Any],
    points: List[Tuple[float, float]],
) -> io.BytesIO:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    risk_level = result["risk_level"]

    y = _draw_header(c, risk_level)
    y = _draw_risk_badge(c, y, risk_level)
    y = _draw_risk_gauge(c, y, risk_level)

    diagram_left_edge = _draw_plot_diagram(c, y, points)
    findings_max_x = diagram_left_edge - 0.2 * inch

    y_findings = _draw_card(
        c, y, "Key Findings", result["findings"], STATUS_COLORS[theme.RISK_TO_STATUS[risk_level]], findings_max_x
    )
    y = min(y_findings, y - 1.9 * inch - 0.2 * inch)  # clear the diagram box too

    y = _draw_card(c, y, "Recommendations", result["recommendations"], STATUS_COLORS["good"], PAGE_WIDTH - MARGIN)
    y = _draw_plots_table(c, y, result)
    y = _draw_coordinates_table(c, y, points)

    _draw_footer(c)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

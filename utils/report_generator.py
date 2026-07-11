"""PDF risk report generation for LandVerify, using ReportLab."""

import io
from datetime import datetime
from typing import Any, Dict, List, Tuple

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = letter
MARGIN = 1 * inch


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


def generate_pdf_report(
    result: Dict[str, Any],
    points: List[Tuple[float, float]],
) -> io.BytesIO:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    max_width = PAGE_WIDTH - 2 * MARGIN
    y = PAGE_HEIGHT - MARGIN

    def line(text: str, font: str = "Helvetica", size: int = 11, gap: float = 0.28 * inch, indent: float = 0):
        nonlocal y
        c.setFont(font, size)
        for wrapped in _wrapped_lines(c, text, font, size, max_width - indent):
            if y < MARGIN:
                c.showPage()
                c.setFont(font, size)
                y = PAGE_HEIGHT - MARGIN
            c.drawString(MARGIN + indent, y, wrapped)
            y -= gap

    def spacer(amount: float = 0.15 * inch):
        nonlocal y
        y -= amount

    line("LandVerify Risk Report", font="Helvetica-Bold", size=18, gap=0.32 * inch)
    line(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", size=9)
    spacer()

    line(f"Risk Level: {result['risk_level']}", font="Helvetica-Bold", size=14)
    spacer()

    coord_str = "; ".join(f"({lat:.5f}, {lon:.5f})" for lat, lon in points)
    line("Coordinates Assessed:", font="Helvetica-Bold", size=12)
    line(coord_str or "None provided", indent=0.2 * inch)
    spacer()

    line("Key Findings:", font="Helvetica-Bold", size=12)
    for finding in result["findings"]:
        line(f"- {finding}", indent=0.2 * inch)
    spacer()

    line("Recommendations:", font="Helvetica-Bold", size=12)
    for rec in result["recommendations"]:
        line(f"- {rec}", indent=0.2 * inch)
    spacer(0.4 * inch)

    line(
        "This report is an automated preliminary screening, not a certified survey. "
        "For a full professional assessment, book a consultation.",
        size=9,
    )

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

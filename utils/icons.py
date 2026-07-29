"""
Self-contained inline SVG icons (no external font/CDN), used in place of
emoji throughout the UI. Each function returns a ready-to-embed <svg> tag
sized/colored by its arguments.
"""

_STROKE_ICONS = {
    "logo": '<path d="M3 21 9 3l3 6 3-6 6 18" /><path d="M9 21v-6h6v6" />',
    "check-circle": '<circle cx="12" cy="12" r="9" /><path d="m8.5 12.5 2.5 2.5 5-5" />',
    "alert-triangle": '<path d="M12 3.5 22 20H2Z" /><path d="M12 10v4" /><path d="M12 16.8h.01" />',
    "alert-octagon": (
        '<path d="M7.9 2h8.2L22 7.9v8.2L16.1 22H7.9L2 16.1V7.9Z" />'
        '<path d="M12 7.5v5" /><path d="M12 15.8h.01" />'
    ),
    "ruler": (
        '<rect x="2.5" y="8" width="19" height="8" rx="1.5" transform="rotate(-45 12 12)" />'
        '<path d="m8.5 10.5 1.5 1.5" /><path d="m11.5 7.5 1.5 1.5" /><path d="m14.5 4.5 1.5 1.5" />'
    ),
    "calendar": (
        '<rect x="3" y="5" width="18" height="16" rx="2" />'
        '<path d="M3 10h18" /><path d="M8 3v4" /><path d="M16 3v4" />'
    ),
    "chat": '<path d="M4 4h16v12H8l-4 4Z" />',
    "download": '<path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M5 21h14" />',
    "heart": '<path d="M12 21S4 14.5 4 8.8C4 5.6 6.5 3.5 9.2 3.5c1.6 0 3 .8 3.8 2 .8-1.2 2.2-2 3.8-2 2.7 0 5.2 2.1 5.2 5.3 0 5.7-8 12.2-8 12.2Z" />',
    "upload-cloud": (
        '<path d="M7 18a4.5 4.5 0 0 1-.7-8.9 5.5 5.5 0 0 1 10.6-1.5A4.5 4.5 0 0 1 17 18Z" />'
        '<path d="M12 21v-8" /><path d="m9 15.5 3-3 3 3" />'
    ),
    "map-pin": '<path d="M12 22s7-6.3 7-12a7 7 0 1 0-14 0c0 5.7 7 12 7 12Z" /><circle cx="12" cy="10" r="2.5" />',
    "trending-up": '<path d="m3 17 6-6 4 4 8-8" /><path d="M15 7h6v6" />',
    "info": '<circle cx="12" cy="12" r="9" /><path d="M12 11v6" /><path d="M12 7.2h.01" />',
    "share": (
        '<circle cx="18" cy="5" r="2.5" /><circle cx="6" cy="12" r="2.5" /><circle cx="18" cy="19" r="2.5" />'
        '<path d="m8.2 10.7 7.6-4.4" /><path d="m8.2 13.3 7.6 4.4" />'
    ),
    "users": (
        '<circle cx="9" cy="8" r="3.2" /><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />'
        '<path d="M16 4.3a3.2 3.2 0 0 1 0 6.2" /><path d="M21 19.5c0-2.7-2-5-4.7-5.7" />'
    ),
}


def icon(name: str, color: str = "currentColor", size: int = 20, stroke_width: float = 2) -> str:
    body = _STROKE_ICONS[name]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round" style="display:inline-block;vertical-align:middle">'
        f"{body}</svg>"
    )


def dot(color: str, size: int = 10) -> str:
    """Filled circle for legends/status dots."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 10 10" style="display:inline-block;vertical-align:middle">'
        f'<circle cx="5" cy="5" r="5" fill="{color}" /></svg>'
    )

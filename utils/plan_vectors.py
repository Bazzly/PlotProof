"""
Vector-graphics-based boundary reconstruction for text-based (non-scanned)
survey plan PDFs - a higher-confidence alternative to the pure text-based
traverse in traverse.py, used when the plan labels multiple beacons
individually (e.g. "SC/OG FA1801AHX") rather than only the origin.

These plans draw each beacon as a small circular point marker (many short
line segments approximating a circle in a tiny bounding box) and print its
code nearby. Chaining the markers in label order and anchoring them to the
plan's one printed absolute coordinate reconstructs the boundary directly
from the drawing geometry.

This assumes the drawing is true-north-up (no rotation) - validated
against real plans from this surveyor's software, where edge bearings
computed straight from the vector geometry matched the printed bearings
to within a fraction of a degree. The printed AREA cross-check in
traverse.py's area_within_tolerance() is the safety net if a future plan
turns out not to follow that convention.
"""

import math
from typing import List, Optional, Tuple

import fitz

from utils import traverse

# Point-marker symbols: many short strokes forming a small circle, well
# under the size of any real boundary edge or dimension line.
_MARKER_MIN_SEGMENTS = 8
_MARKER_MAX_SIZE_PT = 5.0

# How far a beacon code's text label can be from its point marker and
# still be considered "the same beacon" - generous enough for the offset
# labels typically use, tight enough to avoid matching the wrong marker.
_MAX_LABEL_MARKER_DISTANCE_PT = 60.0


def _find_point_markers(page: fitz.Page) -> List[Tuple[float, float]]:
    markers = []
    for d in page.get_drawings():
        r = d["rect"]
        if len(d["items"]) >= _MARKER_MIN_SEGMENTS and r.width < _MARKER_MAX_SIZE_PT and r.height < _MARKER_MAX_SIZE_PT:
            markers.append(((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))
    return markers


def _find_beacon_labels(page: fitz.Page) -> List[Tuple[str, Tuple[float, float]]]:
    """Returns (beacon_code, label_center) in text-stream order - the code
    span immediately following an "SC/OG" span, as printed on these plans."""
    spans = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans.extend(line["spans"])

    labels = []
    for i, span in enumerate(spans):
        if span["text"].strip().upper() == "SC/OG" and i + 1 < len(spans):
            code_span = spans[i + 1]
            bbox = code_span["bbox"]
            center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
            labels.append((code_span["text"].strip(), center))
    return labels


def _match_labels_to_markers(
    labels: List[Tuple[str, Tuple[float, float]]],
    markers: List[Tuple[float, float]],
) -> List[Tuple[float, float]]:
    ordered_points = []
    used = set()
    for _code, (lx, ly) in labels:
        best_idx, best_dist = None, None
        for i, (mx, my) in enumerate(markers):
            if i in used:
                continue
            dist = math.hypot(mx - lx, my - ly)
            if best_dist is None or dist < best_dist:
                best_idx, best_dist = i, dist
        if best_idx is not None and best_dist <= _MAX_LABEL_MARKER_DISTANCE_PT:
            ordered_points.append(markers[best_idx])
            used.add(best_idx)
    return ordered_points


def build_polygon_from_pdf(
    file_path: str,
    origin_en: Tuple[float, float],
    scale_ratio: float,
    text: str,
) -> Optional[List[Tuple[float, float]]]:
    """
    origin_en: the plan's printed (easting, northing) reference coordinate.
    scale_ratio: from "SCALE:-1:N" (e.g. 500).
    text: the plan's extracted text, reused here only for the area cross-check.

    Returns (easting, northing) polygon vertices - the first labeled beacon
    is assumed to be the one the origin coordinate refers to - or None if
    fewer than 3 beacons could be matched or the result fails the area check.
    """
    doc = fitz.open(file_path)
    page = doc[0]
    markers = _find_point_markers(page)
    labels = _find_beacon_labels(page)
    doc.close()

    if len(labels) < 3 or len(markers) < 3:
        return None

    ordered_points = _match_labels_to_markers(labels, markers)
    if len(ordered_points) < 3:
        return None

    pt_to_mm = 25.4 / 72
    m_per_pt = pt_to_mm * scale_ratio / 1000
    # PDF y grows downward; real-world north is -y.
    local = [(x * m_per_pt, -y * m_per_pt) for x, y in ordered_points]

    offset_e = origin_en[0] - local[0][0]
    offset_n = origin_en[1] - local[0][1]
    polygon_en = [(e + offset_e, n + offset_n) for e, n in local]

    if not traverse.area_within_tolerance(traverse.shoelace_area(polygon_en), traverse.parse_area_sqm(text)):
        return None

    return polygon_en

"""
Shared coordinate parsing/validation helpers.
Used by both manual text input and OCR-extracted text, so extraction
logic only lives in one place.
"""

import re
from typing import List, Tuple

# Matches decimal-degree numbers (e.g. 6.5244, -3.3792). Beacon/point
# labels ("B1", "Point 2") are plain integers with no decimal point,
# so this regex naturally skips them.
_DECIMAL_NUM_RE = re.compile(r"-?\d{1,3}\.\d+")

# Loose bounding box covering West/Central Africa, used only to flag
# coordinates that are clearly off (wrong hemisphere, swapped lat/lon).
WEST_AFRICA_BOUNDS = {"min_lat": 3.0, "max_lat": 15.0, "min_lon": -10.0, "max_lon": 16.0}


def is_valid_latlon(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180


def is_within_expected_region(lat: float, lon: float) -> bool:
    b = WEST_AFRICA_BOUNDS
    return b["min_lat"] <= lat <= b["max_lat"] and b["min_lon"] <= lon <= b["max_lon"]


def parse_coordinate_text(text: str) -> List[Tuple[float, float]]:
    """
    Extract (lat, lon) pairs from free-form text, one or more per line.
    Consecutive decimal numbers on a line are paired as (lat, lon), so
    both a bare "6.5244, 3.3792" and a labeled "B1: 6.5244, 3.3792"
    (or OCR output with beacon labels) parse the same way.
    """
    points: List[Tuple[float, float]] = []
    for line in text.splitlines():
        nums = [float(n) for n in _DECIMAL_NUM_RE.findall(line)]
        for i in range(0, len(nums) - 1, 2):
            lat, lon = nums[i], nums[i + 1]
            if is_valid_latlon(lat, lon):
                points.append((lat, lon))
    return points

"""
Standalone CLI for testing utils/vision_extract.py against real survey plan
photos, without going through the full Streamlit app.

Usage:
    ANTHROPIC_API_KEY=sk-... .venv/bin/python scripts/vision_extract_prototype.py <image_path> [image_path2 ...]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import vision_extract  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: vision_extract_prototype.py <image_path> [image_path2 ...]")
        sys.exit(1)

    if not vision_extract.is_available():
        print("ANTHROPIC_API_KEY is not set.")
        sys.exit(1)

    for arg in sys.argv[1:]:
        print(f"\n{'=' * 70}\n{arg}\n{'=' * 70}")
        points, crs_note, raw_summary, legs_info = vision_extract.extract_points_from_image(arg)
        print(raw_summary)
        print(f"\ncrs_note: {crs_note}")
        print(f"points ({len(points)}):")
        for lat, lon in points:
            print(f"  {lat:.6f}, {lon:.6f}")
        if legs_info:
            print(f"\nlegs ({len(legs_info['rows'])}):")
            for row in legs_info["rows"]:
                print(f"  {row['beacon'] or '?'}: {row['bearing_text']} / {row['distance_m']}m")


if __name__ == "__main__":
    main()

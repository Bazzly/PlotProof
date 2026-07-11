"""
Turns raw GIS overlap/proximity results into the risk_level/findings/
recommendations shape the UI and PDF report expect.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from utils.coordinates import is_within_expected_region

RISK_HIGH = "High"
RISK_MEDIUM = "Medium"
RISK_LOW = "Low"


def calculate_risk(
    points: List[Tuple[float, float]],
    overlap_result: Dict[str, Any],
    boundary_is_measured: bool,
) -> Dict[str, Any]:
    findings: List[str] = []
    recommendations: List[str] = []

    overlaps = overlap_result["overlaps"]
    proximate = overlap_result["proximate"]

    off_region_points = [p for p in points if not is_within_expected_region(*p)]
    if off_region_points:
        findings.append(
            f"{len(off_region_points)} coordinate(s) fall outside the expected region "
            "- double-check for a lat/lon swap or a typo before relying on this report."
        )
        recommendations.append("Re-verify the entered/extracted coordinates for accuracy.")

    if overlaps:
        for o in overlaps:
            findings.append(
                f"Boundary overlaps registered plot {o['plot_ref']} ({o['owner']}) "
                f"by approximately {o['overlap_area_sqm']:.0f} m²."
            )
        recommendations.append(
            "Engage a certified surveyor immediately to resolve the boundary overlap before proceeding."
        )
        risk_level = RISK_HIGH
    elif proximate:
        for p in proximate:
            findings.append(
                f"Boundary is close to registered plot {p['plot_ref']} ({p['owner']}) "
                f"- approximately {p['distance_m']:.0f} m away."
            )
        recommendations.append(
            "Recommend a professional boundary verification given the proximity to a neighboring plot."
        )
        risk_level = RISK_MEDIUM
    else:
        findings.append("No overlaps or close boundaries found with known neighboring plots.")
        recommendations.append("Keep survey documentation up to date for future transactions.")
        risk_level = RISK_LOW

    if not boundary_is_measured:
        findings.append(
            "Only 1-2 coordinates were provided, so the plot boundary shown is an estimated "
            "extent, not your actual surveyed shape."
        )
        recommendations.append(
            "Provide all boundary corner coordinates (or a full survey plan) for a precise assessment."
        )
        if risk_level == RISK_LOW:
            risk_level = RISK_MEDIUM

    return {
        "risk_level": risk_level,
        "findings": findings,
        "recommendations": recommendations,
        "overlaps": overlaps,
        "proximate": proximate,
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
    }

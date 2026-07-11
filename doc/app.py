"""
LandVerify - MVP Starter (Streamlit)
Built by Alli Bazeet (@bazzlycodes)

This is a minimal viable version to get started quickly.
Replace the dummy processing with real GeoPandas logic later.
"""

import streamlit as st
from datetime import datetime
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import io
import os

# ------------------------------
# PAGE CONFIG
# ------------------------------
st.set_page_config(
    page_title="LandVerify - Check Your Land Risk",
    page_icon="🗺️",
    layout="centered"
)

st.title("🗺️ LandVerify")
st.subheader("Instant Land Boundary Risk Check")

st.markdown("""
Upload your survey plan or enter coordinates to get an instant risk assessment.
This is an early MVP. Real GeoPandas processing will be added soon.
""")

# ------------------------------
# UPLOAD SECTION
# ------------------------------
st.header("1. Upload Your Survey Document")

uploaded_file = st.file_uploader(
    "Upload Survey Plan (PDF or Image)",
    type=["pdf", "png", "jpg", "jpeg"],
    help="For MVP, we accept the file but processing is simulated."
)

coordinates_input = st.text_input(
    "Or enter coordinates manually (e.g. 6.5244, 3.3792)",
    placeholder="Latitude, Longitude"
)

# ------------------------------
# PROCESS BUTTON
# ------------------------------
if st.button("Analyze My Land", type="primary"):
    if not uploaded_file and not coordinates_input:
        st.error("Please upload a file or enter coordinates.")
    else:
        with st.spinner("Analyzing your land boundaries..."):
            # TODO: Replace this with real GeoPandas logic
            import time
            time.sleep(2)  # Simulate processing

            # Dummy risk result
            risk_level = "Medium"
            findings = [
                "Minor coordinate inconsistency detected",
                "No major overlaps found with neighboring plots",
                "Recommend professional verification for full accuracy"
            ]

            st.success("Analysis Complete!")

            # Show Risk Score
            st.subheader("Risk Assessment")
            if risk_level == "Low":
                st.success(f"**Risk Level: {risk_level}**")
            elif risk_level == "Medium":
                st.warning(f"**Risk Level: {risk_level}**")
            else:
                st.error(f"**Risk Level: {risk_level}**")

            # Findings
            st.subheader("Key Findings")
            for finding in findings:
                st.write(f"• {finding}")

            # Download Report Button
            if st.button("Download PDF Report"):
                buffer = io.BytesIO()
                c = canvas.Canvas(buffer, pagesize=letter)
                c.setFont("Helvetica-Bold", 16)
                c.drawString(1*inch, 10*inch, "LandVerify Risk Report")
                c.setFont("Helvetica", 12)
                c.drawString(1*inch, 9.5*inch, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                c.drawString(1*inch, 9*inch, f"Risk Level: {risk_level}")
                c.drawString(1*inch, 8.5*inch, "Findings:")
                y = 8.0
                for finding in findings:
                    c.drawString(1.2*inch, y*inch, f"• {finding}")
                    y -= 0.4
                c.save()
                buffer.seek(0)

                st.download_button(
                    label="Download Report PDF",
                    data=buffer,
                    file_name="LandVerify_Report.pdf",
                    mime="application/pdf"
                )

# ------------------------------
# CONSULTATION CTA
# ------------------------------
st.divider()
st.subheader("Need Professional Help?")

st.info("""
If the report shows any risks or you want a certified surveyor to review your land properly, 
book a consultation with me.
""")

col1, col2 = st.columns(2)
with col1:
    st.button("📅 Book 30-min Consultation", use_container_width=True)
with col2:
    st.button("💬 Chat on WhatsApp", use_container_width=True)

# ------------------------------
# FOOTER
# ------------------------------
st.divider()
st.caption("Built with ❤️ by Alli Bazeet (@bazzlycodes) | Geospatial Engineer & Full-Stack Developer")
st.caption("Protecting land rights in Africa through technology.")
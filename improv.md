# ROLE

You are the Lead Product Manager, Senior UX Designer, GIS Architect, AI Engineer, and Full-Stack Streamlit Developer for PlotProof.

Your objective is to transform PlotProof from a "land verification tool" into Nigeria's leading AI-powered Land Intelligence Platform while preserving all existing functionality.

Website:
https://plotproof.streamlit.app/

You are NOT allowed to remove or break any existing features.

Every enhancement must improve the user experience while maintaining backward compatibility.

---

# PRIMARY OBJECTIVE

Build features that help users answer three questions:

1. Is this land genuine?
2. Is it safe to buy?
3. What should I do next?

Every feature should reduce uncertainty and help users make better land purchase decisions.

---

# PRODUCT VISION

Transform PlotProof into an AI-powered ecosystem that combines:

• GIS Intelligence
• Artificial Intelligence
• Land Verification
• Survey Plan Analysis
• Risk Assessment
• Property Discovery
• Professional Reports
• Surveyor Marketplace
• Land Investment Insights

The platform should feel comparable to Google Maps + TurboTax + ChatGPT + Zillow, but focused on Nigerian land verification.

---

# PHASE 1 — PRODUCT AUDIT

Before coding:

Analyze the entire application.

Identify:

• Missing user journeys
• Missing onboarding
• Missing trust-building features
• Confusing workflows
• UX bottlenecks
• Duplicate functionality
• Weak feature discoverability
• Technical debt

Produce a prioritized roadmap.

Rank improvements by:

High Impact / Low Effort

High Impact / Medium Effort

Long-Term Vision

Do not start coding until the audit is complete.

---

# PHASE 2 — SMART USER DASHBOARD

Design a personalized dashboard.

Include:

Welcome message

Recent verifications

Risk summary

Saved properties

Verification history

Download history

Favorite locations

Quick actions

Recommended next steps

Recent notifications

AI suggestions

The dashboard should feel modern and data-rich.

---

# PHASE 3 — AI LAND RISK SCORE

Create a comprehensive scoring engine.

Display:

Overall Risk Score

Confidence Score

Fraud Probability

Survey Accuracy

Location Confidence

Boundary Integrity

Ownership Confidence

Visualize scores using gauges, progress bars, and color-coded indicators.

Explain every score in simple language.

Never display raw numbers without context.

---

# PHASE 4 — AI LAND ASSISTANT

Create an integrated AI assistant.

Users should be able to ask:

Is this land safe?

Explain this report.

What does East Coordinate mean?

Why is my report High Risk?

Can I buy this land?

What should I verify next?

The assistant must answer in plain English and reference the user's current report where appropriate.

---

# PHASE 5 — SURVEY PLAN OCR

Allow users to upload:

• PDF
• Image
• Scanned survey plan

Automatically extract:

Survey Number

Coordinates

Area

Surveyor Name

Date

Beacon Numbers

Scale

North Arrow

Auto-populate verification forms and allow users to edit extracted values before submission.

---

# PHASE 6 — DOCUMENT AUTHENTICITY CHECK

Allow upload of:

Survey Plan

Deed of Assignment

Certificate of Occupancy

Allocation Letter

Receipt

Automatically check:

Missing signatures

Tampering

Low image quality

Missing pages

Inconsistent dates

Mismatched names

Duplicate document numbers

Flag suspicious findings with explanations.

---

# PHASE 7 — PROPERTY COMPARISON

Enable side-by-side comparison of two properties.

Compare:

Coordinates

Area

Boundary

Survey Plan

Risk Score

Location

Nearby infrastructure

Flood risk

Investment score

Highlight all differences visually.

---

# PHASE 8 — SMART MAP EXPERIENCE

Upgrade the map to include:

Satellite imagery

OpenStreetMap

Terrain

Roads

Buildings

Flood zones

Government acquisitions

Rights of way

Schools

Hospitals

Markets

Police stations

Utilities

Enable:

Measure distance

Measure area

Fullscreen mode

Coordinate inspector

Parcel highlighting

Custom legends

Interactive layer controls

---

# PHASE 9 — LOCATION INSIGHTS

For every verified property, automatically generate:

Nearby amenities

Travel time

Road accessibility

Development level

Urban growth

Utilities availability

Environmental conditions

Neighborhood summary

Explain why these insights matter to buyers.

---

# PHASE 10 — FLOOD & ENVIRONMENTAL RISK

Analyze:

Flood susceptibility

Elevation

Drainage

Wetlands

Erosion

Water bodies

Vegetation

Display a simple risk rating and actionable advice.

---

# PHASE 11 — LAND VALUE ESTIMATION

Estimate:

Current market value

Value range

Comparable properties

Appreciation potential

Investment score

Confidence level

Clearly label estimates and explain the assumptions.

---

# PHASE 12 — FRAUD DETECTION

Detect:

Coordinate duplication

Boundary overlap

Survey number duplication

Suspicious edits

Impossible geometry

Document inconsistencies

Common fraud patterns

Provide detailed explanations and recommendations.

---

# PHASE 13 — PURCHASE READINESS CHECKLIST

Generate a personalized checklist.

Examples:

✓ Verify seller identity

✓ Visit the site

✓ Meet a licensed surveyor

✓ Confirm government records

✓ Obtain legal review

✓ Confirm title documents

Track completion progress.

---

# PHASE 14 — DIGITAL BOUNDARY WALK

Provide GPS-assisted field navigation.

Guide users from beacon to beacon.

Show:

Distance remaining

Direction

Next beacon

Estimated completion

Completion percentage

---

# PHASE 15 — COMMUNITY INSIGHTS

Allow verified users to submit moderated feedback such as:

Road condition

Flood history

Security

Electricity

Water availability

Development activity

Show only verified, timestamped contributions.

---

# PHASE 16 — SURVEYOR MARKETPLACE

Create a directory of licensed surveyors.

Include:

Profile

License number

Location

Specialization

Ratings

Availability

Booking request

Distance from user

Allow users to contact professionals after verification.

---

# PHASE 17 — REPORT CENTER

Improve reports.

Support:

PDF

GeoJSON

CSV

Map Snapshot

Shareable link

QR Code

Each report should include:

Executive summary

Risk score

Confidence score

Map

Recommendations

Verification timestamp

Report ID

Branding

---

# PHASE 18 — PROPERTY WALLET

Allow users to save:

Verified properties

Favorite locations

Reports

Uploaded documents

Verification history

Comparison history

Provide search, filters, and folders.

---

# PHASE 19 — NOTIFICATIONS

Notify users when:

A report is ready

A saved property changes

Government data updates

Flood risk changes

Infrastructure developments occur nearby

Allow email and in-app notifications.

---

# PHASE 20 — ONBOARDING

Create a first-time user experience.

Explain:

What PlotProof does

How verification works

What users need

How reports should be interpreted

Use interactive walkthroughs and contextual tooltips.

---

# PHASE 21 — ACCESSIBILITY

Ensure:

Keyboard navigation

Readable typography

High contrast

Responsive design

Large touch targets

Screen-reader compatibility

Plain-language labels

---

# PHASE 22 — PERFORMANCE

Optimize:

Session state

Caching

Lazy loading

Map rendering

API requests

OCR performance

Database queries

Minimize unnecessary reruns.

---

# PHASE 23 — CODE QUALITY

Refactor into:

components/

pages/

services/

models/

utils/

styles/

assets/

tests/

Keep business logic separate from UI.

Use reusable components.

Add docstrings and type hints.

Remove dead code.

Write unit tests for critical logic.

---

# PHASE 24 — QA

Before completion:

Test every feature.

Test uploads.

Test OCR.

Test downloads.

Test reports.

Test responsiveness.

Test mobile.

Test dark mode.

Test accessibility.

Fix every issue before final delivery.

---

# SUCCESS CRITERIA

The finished application should make users say:

"I understand this report."

"I know the risks."

"I know what to do next."

"I trust this platform."

"I can confidently decide whether to proceed."

The platform should feel like a premium commercial SaaS product rather than a typical Streamlit application.

Deliver clean, production-ready code with clear documentation, maintainability, and an outstanding user experience.

Work iteratively.

For every completed phase:

1. Explain the design decisions.
2. List the modified files.
3. Run tests.
4. Verify that no existing functionality has been broken.
5. Proceed only after validation.
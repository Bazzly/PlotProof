**Last updated:** 11 July 2026

This policy explains what PlotProof collects, why, and the rights you have over it. It's written to meet Nigeria's Data Protection Act 2023 (NDPA) - the law that applies to PlotProof's users - and, for any user in the European Economic Area, the EU General Data Protection Regulation (GDPR).

## 1. Who controls this data

PlotProof is built and operated by Alli Bazeet (@bazzlycodes), a SURCON-certified surveyor and geospatial engineer. Contact details are in [Section 10](#10-contact--exercising-your-rights).

## 2. What we collect

| Data | When | Why |
|---|---|---|
| Coordinates you type, or that we extract from an uploaded file | Every use | To run the risk analysis you asked for |
| The uploaded survey document itself (PDF/image) | Only if you upload a file | To extract coordinates from it |
| Extracted text, auto-detected coordinates, and your corrections | Only if you check **"Help improve coordinate extraction"** | To improve extraction accuracy on future document formats |
| Your plot's boundary shape (geometry only - no name, address, or document) | Only if you check **"Add my plot's boundary to the shared registry"** | So future nearby uploads get checked against your plot too |
| Standard web request data (IP address, browser type, timestamps) | Every use | Basic server operation and security, via Streamlit's hosting infrastructure |
| A session identifier (essential cookie) | Every use | Required for the app to function - see [Section 6](#6-cookies) |

We do not collect your name, email, or account information, because PlotProof doesn't require an account.

## 3. How long we keep it

- **Core analysis data** (coordinates, uploaded file): used for your session and not retained afterward, unless you opted into one of the features below.
- **Extraction-improvement data**: retained until you request deletion (see [Section 10](#10-contact--exercising-your-rights)).
- **Shared registry data**: retained indefinitely once added, since its value depends on staying available for future checks - you're told this plainly at the point of opt-in, and you can request removal at any time.

## 4. Legal basis for processing

- **Core risk-check service**: necessary to perform the service you're requesting (NDPA Art. 2.2(b); GDPR Art. 6(1)(b)).
- **Optional features** (extraction improvement, shared registry): your explicit, separately-given consent (NDPA Art. 2.2(a); GDPR Art. 6(1)(a)). You can decline either and still use the core service. Consent can be withdrawn at any time going forward.

## 5. Who we share it with

- **Supabase** (only if the deployment is configured to use it) - our database/file storage provider. Without Supabase configured, uploaded files and opt-in data are stored locally on the server instead.
- **Streamlit Community Cloud** (or wherever this instance is hosted) - our hosting infrastructure, which processes standard web request data to serve the app.

We do not sell your data, and do not share it with advertisers or data brokers.

## 6. Cookies

PlotProof uses a **single essential session cookie**, set by the Streamlit framework the app runs on, to maintain your session state (e.g. remembering the coordinates you've entered as you interact with the page). It's required for the app to work and contains no tracking or advertising data.

We do not use advertising or third-party tracking cookies. Streamlit's optional built-in usage-analytics telemetry is **disabled** in this deployment's configuration.

## 7. Your rights

Under NDPA and (for EEA users) GDPR, you have the right to:

- **Be informed** about how your data is processed (this policy).
- **Access** the data we hold about you.
- **Rectify** inaccurate data.
- **Erasure** - request deletion of extraction-improvement or shared-registry data you contributed.
- **Restrict or object** to processing.
- **Data portability** - receive your contributed data in a portable format.
- **Withdraw consent** for any opt-in feature at any time.
- **Lodge a complaint** with Nigeria's Data Protection Commission (NDPC) or, for EEA users, your local supervisory authority.

None of PlotProof's processing involves automated decision-making with legal or similarly significant effects on you - the risk score is informational, and the Terms of Service require professional verification before any transactional decision.

## 8. Children's privacy

PlotProof is not directed at, and does not knowingly collect data from, anyone under 18.

## 9. International transfers

If this deployment uses Supabase or a hosting region outside Nigeria, your data may be processed in that region. We only use providers that apply appropriate safeguards for cross-border data transfer.

## 10. Contact & exercising your rights

To access, correct, or delete data you've contributed, or with any privacy question: reach out via the WhatsApp or consultation links in the app, or email **[PRIVACY_CONTACT_EMAIL - to be configured]**.

## 11. Changes to this policy

We may update this policy as the Service evolves. Material changes will be reflected in the "Last updated" date above, and continued use after a change means you accept the update.

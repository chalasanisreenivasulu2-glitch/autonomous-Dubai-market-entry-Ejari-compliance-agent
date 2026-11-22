import streamlit as st
import requests

API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="SettleDXB | Autonomous Dubai Market-Entry & Ejari Agent",
    page_icon="🇦🇪",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------
if "agent_response" not in st.session_state:
    st.session_state.agent_response = None

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🇦🇪 SettleDXB: Autonomous Dubai Market-Entry & Ejari Compliance Agent")
st.caption(
    "Dubai Chamber Create AI Agents Championship Prototype • PyMuPDF Bilingual Document Ingestion, "
    "RERA Decree 43 Math, Arabic–English Legal Parity & Human-in-the-Loop Governance"
)

# ---------------------------------------------------------------------------
# Top Panel: Real PDF Upload via PyMuPDF (fitz)
# ---------------------------------------------------------------------------
with st.expander("📤 Upload Actual PDF Documents (Draft Tenancy Contract & Trade Name Certificate)", expanded=False):
    up_col1, up_col2, up_col3 = st.columns([1.2, 1.2, 0.8])
    with up_col1:
        lease_file = st.file_uploader("Upload Draft Commercial Lease (PDF)", type=["pdf"], key="lease_pdf_up")
    with up_col2:
        cert_file = st.file_uploader("Upload DET Trade Name Certificate (PDF)", type=["pdf"], key="cert_pdf_up")
    with up_col3:
        st.write("")
        st.write("")
        extract_clicked = st.button("🔍 Extract PDFs with PyMuPDF", use_container_width=True)

    if extract_clicked and (lease_file or cert_file):
        with st.spinner("Extracting bilingual text and structured fields via PyMuPDF..."):
            try:
                files = {}
                if lease_file:
                    files["lease_pdf"] = (lease_file.name, lease_file.getvalue(), "application/pdf")
                if cert_file:
                    files["trade_cert_pdf"] = (cert_file.name, cert_file.getvalue(), "application/pdf")
                resp = requests.post(f"{API_BASE_URL}/api/v1/documents/extract", files=files, timeout=120)
                resp.raise_for_status()
                st.session_state.pdf_extracted = resp.json()
                st.success(
                    f"Extracted. Lease pages: {st.session_state.pdf_extracted.get('lease_page_count', 0)}, "
                    f"Cert pages: {st.session_state.pdf_extracted.get('cert_page_count', 0)}."
                )
            except Exception as e:
                st.error(f"PDF extraction failed: {e}")

    extracted = st.session_state.get("pdf_extracted", {})
    if extracted:
        with st.expander("📑 Extracted Structured Fields", expanded=True):
            st.json(extracted.get("extracted_fields", {}))

# ---------------------------------------------------------------------------
# Sidebar: Scenario Presets & SME Inputs
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("1. SME Expansion Scenario")
    preset = st.selectbox(
        "Load Demo Preset",
        [
            "Case 1: Mainland DET + Flawed Business Bay Lease (Traps Included)",
            "Case 2: Remote AI SaaS Startup (IFZA Free Zone - No Ejari Needed)",
        ],
    )

    is_case_1 = preset.startswith("Case 1")

    company_en = st.text_input(
        "Company Name (English)",
        value="Veloce Cognitive Systems LLC" if is_case_1 else "CloudPulse AI FZCO",
    )
    company_ar = st.text_input(
        "Company Name (Arabic)",
        value="فيلوس للأنظمة المعرفية ذ.م.م" if is_case_1 else "كلاود بالس للذكاء الاصطناعي",
    )
    origin_country = st.text_input("Parent Country", value="India" if is_case_1 else "United Kingdom")
    activity = st.text_input(
        "Business Activity",
        value="Artificial Intelligence & Enterprise Software Development",
    )
    visa_count = st.number_input("Year-1 Visa Quota", min_value=0, max_value=50, value=12 if is_case_1 else 2)
    needs_office = st.checkbox("Requires Dedicated Physical Office", value=is_case_1)
    district = st.selectbox("Target District", ["Business Bay", "DIFC", "Dubai Internet City", "JLT"], index=0)

    st.divider()
    st.header("2. Lease & Ejari Packet Inputs")
    current_rent = st.number_input("Current Annual Rent (AED)", value=200000.0, step=5000.0)
    proposed_rent = st.number_input("Proposed Renewal Rent (AED)", value=240000.0 if is_case_1 else 200000.0, step=5000.0)
    rera_benchmark = st.number_input("RERA Smart Index Average (AED)", value=230000.0, step=5000.0)
    notice_days = st.number_input("Landlord Written Notice (Days)", value=60 if is_case_1 else 95, step=5)

    trade_cert_name = st.text_input("DET Trade Name Certificate", value=company_en)
    lease_tenant_name = st.text_input(
        "Tenant Name on Draft Lease",
        value="Veloce Tech Systems Co." if is_case_1 else company_en,
    )
    title_deed_owner = st.text_input("Title Deed Owner", value="Al Fajer Commercial Properties LLC")
    lease_landlord = st.text_input("Landlord Name on Lease", value="Al Fajer Commercial Properties LLC")
    makani = st.text_input("10-Digit Makani Geocode", value="2849104721")

# ---------------------------------------------------------------------------
# Main Workspace: Bilingual Contract Input & Execution Trigger
# ---------------------------------------------------------------------------
with st.expander("📄 Inspect / Edit Draft Bilingual Commercial Lease Clauses (English & Arabic)", expanded=True):
    col_en, col_ar = st.columns(2)
    default_en = (
        "CLAUSE 4 (RENT): Annual renewal rent shall be AED 240,000 (up from AED 200,000), notified 60 days prior.\n"
        "CLAUSE 9 (MAINTENANCE): Landlord shall be responsible for all major structural and MEP/HVAC maintenance exceeding AED 2,500.\n"
        "CLAUSE 14 (TERMINATION): Either party may terminate at renewal subject to 90 days written notice."
    )
    default_ar = (
        "البند 4 (الإيجار): يكون بدل الإيجار السنوي عند التجديد 240,000 درهم إماراتي بموجب إشعار قبل 60 يوماً.\n"
        "البند 9 (الصيانة): يتحمل المستأجر وحده كافة تكاليف الصيانة الهيكلية وأنظمة التكييف المركزية مهما بلغت قيمتها.\n"
        "البند 14 (الإنهاء): يحق للمؤجر إخلاء المستأجر فوراً عند انتهاء العقد دون الحاجة إلى إخطار عدلي."
    )
    with col_en:
        raw_lease_en = st.text_area("English Lease Text", value=default_en, height=150)
    with col_ar:
        raw_lease_ar = st.text_area("Arabic Lease Text (Prevails in UAE Courts)", value=default_ar, height=150)

if st.button("🚀 Run Autonomous Expansion & Ejari Audit Agent", type="primary", use_container_width=True):
    payload = {
        "proposed_name_en": company_en,
        "proposed_name_ar": company_ar,
        "business_activity": activity,
        "origin_country": origin_country,
        "visa_count": int(visa_count),
        "needs_physical_office": needs_office,
        "preferred_district": district,
        "raw_lease_en": raw_lease_en,
        "raw_lease_ar": raw_lease_ar,
        "current_rent_aed": float(current_rent),
        "proposed_rent_aed": float(proposed_rent),
        "rera_benchmark_aed": float(rera_benchmark),
        "notice_days_given": int(notice_days),
        "is_renewal": True,
        "trade_name_certificate": trade_cert_name,
        "lease_tenant_name": lease_tenant_name,
        "title_deed_owner": title_deed_owner,
        "lease_landlord_name": lease_landlord,
        "makani_number": makani,
    }
    with st.spinner("Agent orchestrating jurisdiction rules, RERA math, bilingual NLP diffing, and Ejari checks..."):
        try:
            resp = requests.post(f"{API_BASE_URL}/api/v1/launch/start", json=payload, timeout=120)
            resp.raise_for_status()
            st.session_state.agent_response = resp.json()
        except Exception as e:
            st.error(f"Backend error (is uvicorn running on port 8000?): {e}")

# ---------------------------------------------------------------------------
# Render Agent Results & Human-in-the-Loop Gate
# ---------------------------------------------------------------------------
res = st.session_state.agent_response

if res:
    st.divider()

    jur = res.get("selected_jurisdiction") or {}
    ejari = res.get("ejari_audit")
    findings = res.get("lease_findings", [])

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Recommended License", jur.get("jurisdiction_code", "N/A"))
    k2.metric("Est. Year-1 Setup Cost", f"AED {jur.get('estimated_year1_aed', 0):,.0f}")
    k3.metric("Lease / RERA Traps Flagged", len(findings))
    if ejari is not None:
        k4.metric("Ejari Registration Status", "READY ✅" if ejari["is_ejari_ready"] else "BLOCKED ⛔")
    else:
        k4.metric("Ejari Registration Status", "NOT REQUIRED (Free Zone)")

    with st.expander("🧭 Agent Reasoning & Graph Execution Trace", expanded=False):
        for step in res.get("execution_trace", []):
            st.markdown(f"- **{step.get('node', '').upper()}**: {step.get('content', '')}")

    left_col, right_col = st.columns([1, 1.3])

    with left_col:
        st.subheader("🏛️ Jurisdiction & Licensing Fit")
        st.info(
            f"**{jur.get('jurisdiction_code')}** | Activity: `{jur.get('activity_code')}`\n\n"
            f"{jur.get('rationale')}"
        )

        st.subheader("📑 Ejari Pre-Submission Gatekeeper")
        if ejari is None:
            st.success("Free Zone package selected — DLD Ejari registration is not required.")
        elif ejari["is_ejari_ready"]:
            st.success(f"All entities & Makani geocode verified (Match Score: {ejari['entity_name_match_score']:.0%}).")
        else:
            st.error(f"Ejari Registration Blocked (Tenant Name Match: {ejari['entity_name_match_score']:.0%})")
            for blocker in ejari.get("blocking_issues", []):
                st.warning(f"**Blocker:** {blocker}")

    with right_col:
        st.subheader("⚖️ Bilingual Lease & RERA Audit Findings")
        if not findings:
            st.success("No RERA violations or Arabic–English discrepancies detected.")
        for item in findings:
            badge = "🔴" if item["severity"] == "CRITICAL" else "🟠"
            with st.container(border=True):
                st.markdown(f"**{badge} {item['clause_id']} — {item['issue_type']}**")
                st.write(item["explanation"])
                c_en, c_ar = st.columns(2)
                c_en.caption("Suggested Counter-Clause (EN)")
                c_en.code(item["suggested_counter_clause_en"], language="text")
                c_ar.caption("Suggested Counter-Clause (AR)")
                c_ar.code(item["suggested_counter_clause_ar"], language="text")

    st.divider()
    if res["status"] == "AWAITING_HUMAN_APPROVAL":
        st.warning(
            f"⏸️ **HUMAN-IN-THE-LOOP APPROVAL GATE (Thread `{res['thread_id']}`)** — "
            "Execution paused before dispatching external counter-offer email or locking license filing."
        )
        edited_email = st.text_area(
            "Review / Edit Drafted Counter-Offer Email to Landlord & Broker",
            value=res.get("draft_counter_offer_email") or "No email required for Free Zone setup.",
            height=180,
        )
        btn_approve, btn_reject = st.columns(2)
        with btn_approve:
            if st.button("✅ Approve & Dispatch Compliance Packet", type="primary", use_container_width=True):
                with st.spinner("Resuming graph and generating compliance packet..."):
                    try:
                        r = requests.post(
                            f"{API_BASE_URL}/api/v1/launch/resume",
                            json={"thread_id": res["thread_id"], "approved": True, "reviewer_notes": edited_email},
                            timeout=120,
                        )
                        r.raise_for_status()
                        st.session_state.agent_response = r.json()
                        st.rerun()
                    except requests.HTTPError as e:
                        st.error(f"Resume failed (HTTP {e.response.status_code}): {e.response.text}")
                    except Exception as e:
                        st.error(f"Resume failed: {e}")
        with btn_reject:
            if st.button("🛑 Reject & Escalate to Legal Counsel", use_container_width=True):
                with st.spinner("Routing to human counsel..."):
                    try:
                        r = requests.post(
                            f"{API_BASE_URL}/api/v1/launch/resume",
                            json={"thread_id": res["thread_id"], "approved": False},
                            timeout=60,
                        )
                        r.raise_for_status()
                        st.session_state.agent_response = r.json()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Reject failed: {e}")

    elif res["status"] == "COMPLETED":
        if res.get("human_approved"):
            st.success(
                f"✅ **APPROVED & COMPLETED** (Thread `{res['thread_id']}`) — "
                "Counter-offer and Ejari compliance packet locked."
            )
            try:
                pdf_resp = requests.get(
                    f"{API_BASE_URL}/api/v1/launch/{res['thread_id']}/report.pdf",
                    timeout=30,
                )
                if pdf_resp.status_code == 200:
                    st.download_button(
                        label="📥 Download Redlined Bilingual Lease & Ejari Certificate (PDF)",
                        data=pdf_resp.content,
                        file_name=f"Dubai_Ejari_Compliance_Packet_{res['thread_id']}.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                    )
                else:
                    st.warning(f"Could not generate PDF report: {pdf_resp.text}")
            except Exception as e:
                st.error(f"PDF download error: {e}")
        else:
            st.error(
                f"🛑 **HALTED BY REVIEWER** (Thread `{res['thread_id']}`) — "
                "Automated dispatch cancelled; escalated to human counsel."
            )
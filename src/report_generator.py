import io
from datetime import datetime, timezone
try:
    import pymupdf  # PyMuPDF >=1.24.3
except ImportError:
    import fitz as pymupdf  # Legacy alias


def _wrap(text, width):
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines or [""]


def generate_compliance_packet_pdf(thread_id: str, state: dict) -> bytes:
    doc = pymupdf.open()

    # ---------------- Page 1: Executive Summary ----------------
    page = doc.new_page(width=595, height=842)
    y = 60
    profile = state.get("company_profile")
    jur = state.get("selected_jurisdiction")
    audit = state.get("audit_result")
    approved_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        ("DUBAI LAUNCH & EJARI COMPLIANCE PACKET", 18, "hebo"),
        ("Redlined Bilingual Lease Schedule & Ejari Readiness Certificate", 11, "hebo"),
        ("", 6, "helv"),
        ("EXECUTIVE SUMMARY", 13, "hebo"),
        (f"Company: {profile.proposed_name_en if profile else 'N/A'}", 10, "helv"),
        (f"Activity: {profile.business_activity if profile else 'N/A'}", 10, "helv"),
        (f"Origin: {profile.origin_country if profile else 'N/A'}", 10, "helv"),
        (f"Visa Quota: {profile.visa_count if profile else 'N/A'}", 10, "helv"),
        ("", 6, "helv"),
        ("JURISDICTION CLEARANCE", 13, "hebo"),
        (f"License: {jur.jurisdiction_code if jur else 'N/A'}", 10, "helv"),
        (f"Activity Code: {jur.activity_code if jur else 'N/A'}", 10, "helv"),
        (f"Est. Year-1 Cost: AED {jur.estimated_year1_aed:,.2f}" if jur else "Est. Year-1 Cost: N/A", 10, "helv"),
        (f"Ejari Required: {'Yes' if jur and jur.requires_ejari else 'No'}", 10, "helv"),
        ("", 6, "helv"),
        ("EJARI PRE-REGISTRATION READINESS", 13, "hebo"),
        (f"Status: {'READY' if audit and audit.is_ejari_ready else 'BLOCKED' if audit else 'N/A'}", 10, "helv"),
    ]
    if audit:
        lines.append((f"Entity Name Match: {audit.entity_name_match_score:.0%}", 10, "helv"))
        for issue in audit.blocking_issues:
            lines.append((f"  - {issue}", 9, "helv"))
    lines += [
        ("", 6, "helv"),
        ("AUDIT TRAIL", 13, "hebo"),
        (f"Thread ID: {thread_id}", 10, "helv"),
        (f"Approved (UTC): {approved_at}", 10, "helv"),
        ("Approved by: Compliance Officer (HITL gate)", 10, "helv"),
    ]

    for text, size, font in lines:
        if not text:
            y += size
            continue
        try:
            page.insert_text((50, y), text, fontsize=size, fontname=font)
        except Exception:
            page.insert_text(
                (50, y),
                text.encode("ascii", "replace").decode("ascii"),
                fontsize=size,
                fontname="helv",
            )
        y += size + 6

    # ---------------- Page 2+: Bilingual Redline Schedule ----------------
    page = doc.new_page(width=595, height=842)
    y = 60
    page.insert_text((50, y), "BILINGUAL LEASE REDLINE SCHEDULE", fontsize=15, fontname="hebo")
    y += 24

    findings = state.get("lease_findings", []) or []
    if not findings:
        page.insert_text((50, y), "No findings recorded.", fontsize=10)

    for f in findings:
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 60
        color = (0.7, 0, 0) if f.severity == "CRITICAL" else (0.8, 0.4, 0)
        page.insert_text(
            (50, y),
            f"[{f.severity}] {f.clause_id} - {f.issue_type}",
            fontsize=11,
            fontname="hebo",
            color=color,
        )
        y += 16
        for line in _wrap(f.explanation, 95):
            if y > 800:
                page = doc.new_page(width=595, height=842)
                y = 60
            page.insert_text((50, y), line, fontsize=9)
            y += 12
        y += 4
        page.insert_text((50, y), "Suggested EN:", fontsize=9, fontname="hebo")
        y += 12
        for line in _wrap(f.suggested_counter_clause_en, 95):
            if y > 800:
                page = doc.new_page(width=595, height=842)
                y = 60
            page.insert_text((50, y), line, fontsize=9)
            y += 12
        y += 12

    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()
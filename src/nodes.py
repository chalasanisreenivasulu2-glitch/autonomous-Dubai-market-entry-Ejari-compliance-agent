import os
import logging
from typing import List, Literal
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.runnables import Runnable
from langgraph.types import interrupt, Command
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.state import (
    DubaiLaunchState, CompanyProfile, JurisdictionOption,
    LeaseClauseFinding, ComplianceAuditResult,
)
from src.tools import (
    evaluate_dubai_jurisdictions, check_rera_rent_compliance,
    validate_ejari_packet_consistency,
)
from src.clause_segmenter import align_bilingual_clauses

logger = logging.getLogger(__name__)


def _get_llm() -> ChatGoogleGenerativeAI:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError("Set GEMINI_API_KEY or GOOGLE_API_KEY in your .env file before running.")
    return ChatGoogleGenerativeAI(
        model="gemini-3.1-pro-preview", api_key=api_key, temperature=0.0,
        request_timeout=45, max_retries=2,
    )


class BilingualAnalysisOutput(BaseModel):
    findings: List[LeaseClauseFinding] = Field(default_factory=list)
    draft_counter_offer_email: str = Field(default="")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _invoke_with_retry(structured_llm: Runnable, prompt: str) -> BilingualAnalysisOutput:
    return structured_llm.invoke(prompt)


def intake_node(state: DubaiLaunchState) -> dict:
    profile = state.get("company_profile")
    if not profile:
        raise ValueError("Missing company_profile in initial state.")
    msg = (
        f"[INTAKE] Loaded profile for '{profile.proposed_name_en}' "
        f"({profile.origin_country} -> Dubai | Activity: {profile.business_activity} | "
        f"Visas: {profile.visa_count} | Physical Office: {profile.needs_physical_office})."
    )
    return {
        "current_stage": "JURISDICTION_MATCH",
        "messages": [{"role": "agent", "node": "intake", "content": msg}],
    }


def jurisdiction_node(state: DubaiLaunchState) -> dict:
    profile: CompanyProfile = state["company_profile"]
    raw_options = evaluate_dubai_jurisdictions.invoke({
        "business_activity": profile.business_activity,
        "visa_count": profile.visa_count,
        "needs_physical_office": profile.needs_physical_office,
    })
    options: List[JurisdictionOption] = [
        JurisdictionOption(
            jurisdiction_code=opt["jurisdiction_code"],
            activity_code=opt["activity_code"],
            requires_ejari=opt["requires_ejari"],
            estimated_year1_aed=opt["estimated_year1_aed"],
            rationale=opt["notes"],
        ) for opt in raw_options
    ]
    selected = options[0] if options else None
    if selected is None:
        msg = ("[JURISDICTION] No matching jurisdiction found. "
               "Routing to human approval for manual counsel review.")
        return {
            "recommended_jurisdictions": options,
            "selected_jurisdiction": None,
            "current_stage": "HUMAN_APPROVAL",
            "messages": [{"role": "agent", "node": "jurisdiction", "content": msg}],
        }
    next_stage = "LEASE_RERA_AUDIT" if selected.requires_ejari else "HUMAN_APPROVAL"
    msg = (
        f"[JURISDICTION] Evaluated {len(options)} options. Selected '{selected.jurisdiction_code}' "
        f"(Activity: {selected.activity_code}, Est. Year-1: AED {selected.estimated_year1_aed:,.2f}, "
        f"Ejari Mandatory: {selected.requires_ejari})."
    )
    return {
        "recommended_jurisdictions": options,
        "selected_jurisdiction": selected,
        "current_stage": next_stage,
        "messages": [{"role": "agent", "node": "jurisdiction", "content": msg}],
    }


def lease_audit_node(state: DubaiLaunchState) -> dict:
    current_rent = state["current_rent_aed"]
    proposed_rent = state["proposed_rent_aed"]
    rera_benchmark = state["rera_benchmark_aed"]
    notice_days = state.get("notice_days_given", 90)
    is_renewal = state.get("is_renewal", True)

    rera_check = check_rera_rent_compliance.invoke({
        "current_annual_rent_aed": current_rent,
        "proposed_annual_rent_aed": proposed_rent,
        "rera_index_average_aed": rera_benchmark,
        "notice_days_given": notice_days,
        "is_renewal": is_renewal,
    })

    findings: List[LeaseClauseFinding] = []
    if not rera_check["is_compliant"]:
        findings.append(LeaseClauseFinding(
            clause_id="RERA-RENT-01",
            english_text=f"Proposed Renewal Rent: AED {proposed_rent:,.2f}/year (Notice: {notice_days} days).",
            arabic_text=f"الإيجار السنوي المقترح للتجديد: {proposed_rent:,.2f} درهم إماراتي.",
            severity="CRITICAL",
            issue_type="RERA_VIOLATION",
            explanation=(
                f"Illegal rent increase under {rera_check.get('legal_citation', 'Dubai Tenancy Law')}. "
                f"Max allowed rent is AED {rera_check['max_allowed_rent_aed']:,.2f} "
                f"(Excess overcharge: AED {rera_check.get('excess_charge_aed', 0):,.2f})."
            ),
            suggested_counter_clause_en=(
                f"In accordance with Dubai Decree No. 43 of 2013 and Law No. 33 of 2008, "
                f"the annual renewal rent shall be capped at AED {rera_check['max_allowed_rent_aed']:,.2f}."
            ),
            suggested_counter_clause_ar=(
                f"وفقاً للمرسوم رقم 43 لسنة 2013 والقانون رقم 33 لسنة 2008 في إمارة دبي، "
                f"يُحدد بدل الإيجار السنوي عند التجديد بمبلغ {rera_check['max_allowed_rent_aed']:,.2f} درهم إماراتي."
            ),
        ))

    aligned = align_bilingual_clauses(state.get("raw_lease_en", ""), state.get("raw_lease_ar", ""))
    paired_block = "\n\n".join(
        f"=== CLAUSE {p['clause_id']} ===\n"
        f"EN: {p['en'] or '[missing in English]'}\n"
        f"AR: {p['ar'] or '[missing in Arabic]'}"
        for p in aligned
    )

    prompt = f"""
    You are a senior Dubai commercial real estate legal auditor.
    Compare each numbered clause pair below. Under UAE law, Arabic prevails over English
    in Dubai Rental Disputes Center (RDC) proceedings.

    For EACH clause pair, identify:
    - ARABIC_MISMATCH (Arabic imposes harsher terms than English)
    - HIDDEN_FEE (unjustified chiller, admin, fit-out deposits)
    - TERMINATION_TRAP (unilateral eviction without 12-month notarized notice)

    Emit one LeaseClauseFinding per problematic clause, using clause_id exactly as given
    (e.g., "4", "9", "14"). If a clause is fine, do NOT emit a finding.

    PAIRED CLAUSES:
    {paired_block}

    RERA DETERMINISTIC RESULT (already computed — reference in the email, do NOT re-derive):
    {rera_check}
    """

    try:
        structured = _get_llm().with_structured_output(BilingualAnalysisOutput, method="json_schema")
        ai_result: BilingualAnalysisOutput = _invoke_with_retry(structured, prompt)
        for f in ai_result.findings:
            f.clause_reference = f"Clause {f.clause_id}"
        findings.extend(ai_result.findings)
        draft_email = ai_result.draft_counter_offer_email
        llm_status = "OK"
    except Exception as exc:
        logger.exception("[LEASE AUDIT] LLM bilingual diffing failed")
        findings.append(LeaseClauseFinding(
            clause_id="LLM-FAILSAFE-01",
            english_text="[Automated bilingual diff unavailable]",
            arabic_text="[التحليل الآلي ثنائي اللغة غير متاح]",
            severity="WARNING",
            issue_type="ARABIC_MISMATCH",
            explanation=(
                f"Gemini bilingual audit could not complete ({type(exc).__name__}). "
                "Deterministic RERA findings above are still valid. Manual Arabic clause review required."
            ),
            suggested_counter_clause_en="(manual review required — LLM unavailable)",
            suggested_counter_clause_ar="(مطلوب مراجعة يدوية — خدمة الذكاء الاصطناعي غير متاحة)",
        ))
        draft_email = (
            "Dear Landlord,\n\n"
            "Our compliance review has identified statutory RERA rent-cap issues (see attached schedule). "
            "A full bilingual Arabic-English review is in progress and will follow.\n\n"
            "Regards,\nCompliance Team"
        )
        llm_status = "DEGRADED"

    if not findings and (len(state.get("raw_lease_en", "") or "") > 200 or len(state.get("raw_lease_ar", "") or "") > 200):
        findings.append(LeaseClauseFinding(
            clause_id="REVIEW-REQUIRED-01",
            english_text="[No automated findings — manual review required]",
            arabic_text="[لا توجد نتائج آلية — مطلوب مراجعة يدوية]",
            severity="WARNING",
            issue_type="ARABIC_MISMATCH",
            explanation="Lease is substantive but automated diff returned zero findings. Manual review required.",
            suggested_counter_clause_en="(manual review required)",
            suggested_counter_clause_ar="(مطلوب مراجعة يدوية)",
        ))

    msg = (
        f"[LEASE AUDIT] RERA Compliant: {rera_check['is_compliant']} | "
        f"LLM Status: {llm_status} | Total Clauses Flagged: {len(findings)}."
    )
    return {
        "lease_findings": findings,
        "draft_counter_offer_email": draft_email,
        "current_stage": "EJARI_RECONCILE",
        "messages": [{"role": "agent", "node": "lease_audit", "content": msg}],
    }


def ejari_reconcile_node(state: DubaiLaunchState) -> dict:
    ejari_check = validate_ejari_packet_consistency.invoke({
        "trade_name_certificate": state["trade_name_certificate"],
        "lease_tenant_name": state["lease_tenant_name"],
        "title_deed_owner": state["title_deed_owner"],
        "lease_landlord_name": state["lease_landlord_name"],
        "makani_number": state["makani_number"],
    })
    audit = ComplianceAuditResult(
        is_ejari_ready=ejari_check["is_ejari_ready"],
        entity_name_match_score=ejari_check["tenant_match_score"],
        blocking_issues=ejari_check["blocking_issues"],
        approval_required=True,
    )
    msg = (
        f"[EJARI RECONCILE] Ready for Registration: {audit.is_ejari_ready} | "
        f"Blocking Mismatches: {len(audit.blocking_issues)}."
    )
    return {
        "audit_result": audit,
        "current_stage": "HUMAN_APPROVAL",
        "messages": [{"role": "agent", "node": "ejari_reconcile", "content": msg}],
    }


def human_approval_node(state: DubaiLaunchState) -> Command[Literal["finalize", "rejected"]]:
    if state.get("company_profile") is None:
        raise ValueError("HITL gate reached without company_profile — upstream node failed.")

    payload = {
        "instruction": "Review Dubai Launch & Ejari Compliance findings before approving counter-offer & packet generation.",
        "selected_jurisdiction": state["selected_jurisdiction"].model_dump() if state.get("selected_jurisdiction") else None,
        "lease_findings_count": len(state.get("lease_findings", [])),
        "ejari_audit": state["audit_result"].model_dump() if state.get("audit_result") else None,
        "draft_counter_offer_email": state.get("draft_counter_offer_email"),
    }
    human_decision = interrupt(payload)

    if isinstance(human_decision, dict):
        approved = bool(human_decision.get("approved", False))
    elif isinstance(human_decision, bool):
        approved = human_decision
    else:
        approved = False  # fail-closed

    if approved:
        return Command(
            update={
                "human_approved": True,
                "current_stage": "COMPLETE",
                "messages": [{"role": "human", "node": "human_approval",
                              "content": "Compliance Officer APPROVED redlined lease counter-offer and launch packet."}],
            },
            goto="finalize",
        )
    return Command(
        update={
            "human_approved": False,
            "current_stage": "COMPLETE",
            "messages": [{"role": "human", "node": "human_approval",
                          "content": "Compliance Officer REJECTED automated dispatch; routed to manual legal counsel."}],
        },
        goto="rejected",
    )


def finalize_node(state: DubaiLaunchState) -> dict:
    return {"messages": [{"role": "agent", "node": "finalize",
                          "content": "[COMPLETE] Final Dubai Launch & Ejari Compliance Packet locked and ready for submission."}]}


def rejected_node(state: DubaiLaunchState) -> dict:
    return {"messages": [{"role": "agent", "node": "rejected",
                          "content": "[HALTED] Packet held per human reviewer instruction. No external emails sent."}]}
"""
SettleDXB CLI Demo — Autonomous Dubai Market-Entry & Ejari Compliance
Run:  python run_demo.py

Self-contained: invokes the LangGraph directly (no FastAPI server required).
Produces: demo_compliance_packet.pdf on approval.
"""

import os
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv

from src.state import CompanyProfile
from src.graph import build_dubai_launch_graph
from src.report_generator import generate_compliance_packet_pdf
from langgraph.types import Command

load_dotenv()

# ---------------------------------------------------------------------------
# ANSI color helpers (Windows 10+ supports these natively)
# ---------------------------------------------------------------------------
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"


def _c(text: str, color: str) -> str:
    return f"{color}{text}{C.RESET}"


def _hr(char: str = "=", width: int = 78) -> str:
    return _c(char * width, C.DIM)


def _banner(title: str) -> None:
    print()
    print(_hr("="))
    print(_c(f"  {title}", C.BOLD + C.CYAN))
    print(_hr("="))


def _step(num: int, label: str) -> None:
    print()
    print(_c(f"[STEP {num}] {label}", C.BOLD + C.MAGENTA))
    print(_hr("-"))


def _print_agent_messages(messages: list) -> None:
    """Print new agent messages with color-coded node prefixes."""
    node_colors = {
        "intake": C.BLUE,
        "jurisdiction": C.CYAN,
        "lease_audit": C.YELLOW,
        "ejari_reconcile": C.MAGENTA,
        "human_approval": C.GREEN,
        "finalize": C.GREEN,
        "rejected": C.RED,
    }
    for m in messages:
        node = m.get("node", "agent")
        role = m.get("role", "agent")
        content = m.get("content", "")
        if role == "agent" or role == "human":
            color = node_colors.get(node, C.WHITE)
            tag = f"[{node.upper()}]"
            # Strip any leading [NODE_NAME] or [NODE NAME] prefix from the content
            # (nodes.py uses space, run_demo uses underscore — normalize both)
            body = content
            for variant in (tag, f"[{node.upper().replace('_', ' ')}]", f"[{node}]", f"[{node.replace('_', ' ')}]"):
                if body.startswith(variant):
                    body = body[len(variant):].lstrip()
                    break
            prefix = _c(tag, color)
            print(f"  {prefix} {body}")
        
        
# ---------------------------------------------------------------------------
# Synthetic Case 1: Mainland DET + Flawed Business Bay Lease
# ---------------------------------------------------------------------------
def build_case_1() -> dict:
    profile = CompanyProfile(
        proposed_name_en="Veloce Cognitive Systems LLC",
        proposed_name_ar="فيلوس للأنظمة المعرفية ذ.م.م",
        business_activity="Artificial Intelligence & Enterprise Software Development",
        origin_country="India",
        visa_count=12,
        needs_physical_office=True,
        preferred_district="Business Bay",
    )

    raw_lease_en = (
        "CLAUSE 4 (RENT): The annual rent for Office 1402, Clover Bay Tower, Business Bay "
        "shall be AED 240,000 upon renewal (up from AED 200,000), notified via email 60 days prior to expiry. "
        "CLAUSE 9 (MAINTENANCE): Landlord shall be responsible for all major structural and MEP/HVAC "
        "maintenance exceeding AED 2,500. "
        "CLAUSE 14 (TERMINATION): Either party may terminate at renewal subject to 90 days written notice."
    )

    raw_lease_ar = (
        "البند 4 (الإيجار): يكون بدل الإيجار السنوي للمكتب 1402، برج كلوفر باي، الخليج التجاري "
        "240,000 درهم إماراتي عند التجديد (بدلاً من 200,000 درهم)، بموجب إشعار قبل 60 يوماً. "
        "البند 9 (الصيانة): يتحمل المستأجر وحده كافة تكاليف الصيانة الهيكلية وأنظمة التكييف المركزية مهما بلغت قيمتها. "
        "البند 14 (الإنهاء): يحق للمؤجر إخلاء المستأجر فوراً عند انتهاء العقد دون الحاجة إلى إخطار عدلي."
    )

    return {
        "messages": [],
        "current_stage": "INTAKE",
        "company_profile": profile,
        "recommended_jurisdictions": [],
        "selected_jurisdiction": None,
        "raw_lease_en": raw_lease_en,
        "raw_lease_ar": raw_lease_ar,
        "current_rent_aed": 200000.0,
        "proposed_rent_aed": 240000.0,
        "rera_benchmark_aed": 230000.0,
        "notice_days_given": 60,
        "is_renewal": True,
        "trade_name_certificate": "Veloce Cognitive Systems LLC",
        "lease_tenant_name": "Veloce Tech Systems Co.",
        "title_deed_owner": "Al Fajer Commercial Properties LLC",
        "lease_landlord_name": "Al Fajer Commercial Properties LLC",
        "makani_number": "2849104721",
        "lease_findings": [],
        "audit_result": None,
        "draft_counter_offer_email": None,
        "human_approved": False,
    }


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------
def main() -> int:
    _banner("SettleDXB — Dubai Market-Entry & Ejari Compliance Agent")
    print(_c(
        "  Dubai Chamber Create AI Agents Championship — CLI Prototype",
        C.DIM,
    ))
    print(_c(
        "  Stateful LangGraph · RERA Decree 43 · Bilingual Arabic–English · HITL",
        C.DIM,
    ))

    # Checkpoint DB in a stable location
    db_path = "checkpoints.sqlite"
    thread_id = f"demo-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    print()
    print(_c(f"Thread ID: {thread_id}", C.BOLD + C.WHITE))
    print(_c(f"Checkpointer: SqliteSaver ({db_path})", C.DIM))

    graph = build_dubai_launch_graph(db_path=db_path)
    initial_state = build_case_1()

    # -----------------------------------------------------------------------
    # Step 1 — Run graph until HITL interrupt
    # -----------------------------------------------------------------------
    _step(1, "Autonomous Planning, RERA Math, Bilingual Diff, Ejari Reconciliation")

    try:
        paused_state = graph.invoke(initial_state, config=config)
    except Exception as exc:
        print(_c(f"  [FATAL] Graph invocation failed: {exc}", C.RED))
        return 1

    _print_agent_messages(paused_state.get("messages", []))

    if "__interrupt__" not in paused_state:
        print()
        print(_c("  [NOTE] Graph completed without pausing (Free Zone path).", C.YELLOW))
        return 0

    # -----------------------------------------------------------------------
    # Step 2 — Show the HITL payload
    # -----------------------------------------------------------------------
    _step(2, "Human-in-the-Loop Approval Gate")

    payload = paused_state["__interrupt__"][0].value
    print(f"  {_c('Instruction:', C.BOLD)} {payload['instruction']}")
    print(f"  {_c('Lease Findings:', C.BOLD)} {payload['lease_findings_count']}")
    ejari = payload.get("ejari_audit")
    if ejari:
        status = "READY" if ejari["is_ejari_ready"] else "BLOCKED"
        color = C.GREEN if ejari["is_ejari_ready"] else C.RED
        print(f"  {_c('Ejari Status:', C.BOLD)} {_c(status, color)} "
              f"(name match {ejari['entity_name_match_score']:.0%})")
        for issue in ejari.get("blocking_issues", []):
            print(f"    {_c('BLOCKER:', C.RED)} {issue}")

    # -----------------------------------------------------------------------
    # Step 3 — Detailed findings table
    # -----------------------------------------------------------------------
    _step(3, "Detailed Bilingual & RERA Findings")

    findings = paused_state.get("lease_findings", [])
    if not findings:
        print(_c("  No findings recorded.", C.DIM))
    for f in findings:
        sev_color = C.RED if f.severity == "CRITICAL" else C.YELLOW if f.severity == "WARNING" else C.GREEN
        print()
        print(_c(f"  [{f.severity}] {f.clause_id} — {f.issue_type}", sev_color + C.BOLD))
        print(f"  {_c('Reason:', C.BOLD)} {f.explanation}")
        print(f"  {_c('Fix (EN):', C.BOLD)} {f.suggested_counter_clause_en}")
        print(f"  {_c('Fix (AR):', C.BOLD)} {f.suggested_counter_clause_ar}")

    # -----------------------------------------------------------------------
    # Step 4 — Draft counter-offer email
    # -----------------------------------------------------------------------
    _step(4, "Drafted Counter-Offer Email to Landlord")

    email = paused_state.get("draft_counter_offer_email", "") or "(no email drafted)"
    for line in email.splitlines():
        print(f"  {line}")

    # -----------------------------------------------------------------------
    # Step 5 — Human decision
    # -----------------------------------------------------------------------
    _step(5, "Compliance Officer Decision")

    print(_c(
        "  Review the findings above. Approving will lock the compliance packet "
        "and generate the PDF certificate.",
        C.DIM,
    ))
    print()

    try:
        answer = input(_c("  Approve counter-offer & generate compliance packet? [y/N]: ", C.BOLD + C.WHITE))
    except (EOFError, KeyboardInterrupt):
        answer = ""

    approved = answer.strip().lower() in {"y", "yes"}

    # -----------------------------------------------------------------------
    # Step 6 — Resume graph with the human decision
    # -----------------------------------------------------------------------
    _step(6, "Resuming Graph with Human Decision")

    try:
        final_state = graph.invoke(
            Command(resume={"approved": approved, "reviewer_notes": "CLI demo approval"}),
            config=config,
        )
    except Exception as exc:
        print(_c(f"  [FATAL] Resume failed: {exc}", C.RED))
        return 1

    _print_agent_messages(final_state.get("messages", []))

    # -----------------------------------------------------------------------
    # Step 7 — Final artifact
    # -----------------------------------------------------------------------
    _banner("FINAL RESULT")

    print(f"  Thread ID:     {_c(thread_id, C.BOLD)}")
    print(f"  Status:        {_c(final_state.get('current_stage'), C.BOLD)}")
    print(f"  Human Approved: {_c(str(final_state.get('human_approved')), C.GREEN if final_state.get('human_approved') else C.RED)}")

    if final_state.get("human_approved"):
        try:
            pdf_bytes = generate_compliance_packet_pdf(thread_id, final_state)
            out_path = Path("demo_compliance_packet.pdf")
            out_path.write_bytes(pdf_bytes)
            print()
            print(_c(f"  ✅ Compliance packet written to: {out_path.resolve()}", C.GREEN + C.BOLD))
            print(_c(f"     Size: {len(pdf_bytes):,} bytes · Pages: 2 · Bilingual redlines included", C.DIM))
        except Exception as exc:
            print(_c(f"  [WARN] Could not generate PDF: {exc}", C.YELLOW))
    else:
        print()
        print(_c(
            "  🛑 Review rejected. No external emails sent. Escalated to legal counsel.",
            C.RED + C.BOLD,
        ))

    print()
    print(_hr("="))
    print(_c("  Demo complete.", C.BOLD + C.CYAN))
    print(_hr("="))
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
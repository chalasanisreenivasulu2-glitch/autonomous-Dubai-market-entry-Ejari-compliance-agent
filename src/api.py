import uuid
import sqlite3
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langgraph.types import Command
from langgraph.checkpoint.sqlite import SqliteSaver

from src.state import CompanyProfile
from src.graph import build_dubai_launch_graph
from src.pdf_parser import parse_uploaded_pdfs
from src.report_generator import generate_compliance_packet_pdf

load_dotenv()

app = FastAPI(
    title="Dubai Launch & Ejari Compliance AI Agent API",
    description="Stateful LangGraph backend with PyMuPDF ingestion & Human-in-the-Loop approval gates.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Persistent SQLite checkpointer — survives server restarts
_sqlite_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
_checkpointer = SqliteSaver(_sqlite_conn)
launch_graph = build_dubai_launch_graph(checkpointer=_checkpointer)


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------

class LaunchAuditRequest(BaseModel):
    proposed_name_en: str = "Veloce Cognitive Systems LLC"
    proposed_name_ar: Optional[str] = "فيلوس للأنظمة المعرفية ذ.م.م"
    business_activity: str = "Artificial Intelligence & Enterprise Software Development"
    origin_country: str = "India"
    visa_count: int = Field(12, ge=0)
    needs_physical_office: bool = True
    preferred_district: Optional[str] = "Business Bay"

    raw_lease_en: str = ""
    raw_lease_ar: str = ""
    current_rent_aed: float = 200000.0
    proposed_rent_aed: float = 240000.0
    rera_benchmark_aed: float = 230000.0
    notice_days_given: int = 60
    is_renewal: bool = True

    trade_name_certificate: str = "Veloce Cognitive Systems LLC"
    lease_tenant_name: str = "Veloce Tech Systems Co."
    title_deed_owner: str = "Al Fajer Commercial Properties LLC"
    lease_landlord_name: str = "Al Fajer Commercial Properties LLC"
    makani_number: str = "2849104721"


class HumanDecisionRequest(BaseModel):
    thread_id: str
    approved: bool
    reviewer_notes: Optional[str] = None


def _serialize_graph_output(thread_id: str, state_dict: Dict[str, Any]) -> Dict[str, Any]:
    is_paused = "__interrupt__" in state_dict
    interrupt_payload = state_dict["__interrupt__"][0].value if is_paused else None

    selected_jur = state_dict.get("selected_jurisdiction")
    audit_res = state_dict.get("audit_result")

    return {
        "thread_id": thread_id,
        "status": "AWAITING_HUMAN_APPROVAL" if is_paused else "COMPLETED",
        "current_stage": state_dict.get("current_stage"),
        "human_approved": state_dict.get("human_approved", False),
        "selected_jurisdiction": selected_jur.model_dump() if selected_jur else None,
        "recommended_jurisdictions": [
            j.model_dump() for j in state_dict.get("recommended_jurisdictions", [])
        ],
        "lease_findings": [
            f.model_dump() for f in state_dict.get("lease_findings", [])
        ],
        "ejari_audit": audit_res.model_dump() if audit_res else None,
        "draft_counter_offer_email": state_dict.get("draft_counter_offer_email"),
        "interrupt_payload": interrupt_payload,
        "execution_trace": state_dict.get("messages", []),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "agent": "DubaiLaunch-Ejari-Orchestrator",
        "pdf_engine": "PyMuPDF",
        "checkpointer": "SqliteSaver",
    }


@app.post("/api/v1/documents/extract")
async def extract_pdf_documents(
    lease_pdf: Optional[UploadFile] = File(None),
    trade_cert_pdf: Optional[UploadFile] = File(None),
):
    if not lease_pdf and not trade_cert_pdf:
        raise HTTPException(status_code=400, detail="Upload at least one PDF (lease_pdf or trade_cert_pdf).")
    try:
        lease_bytes = await lease_pdf.read() if lease_pdf else None
        cert_bytes = await trade_cert_pdf.read() if trade_cert_pdf else None
        parsed = parse_uploaded_pdfs(lease_pdf_bytes=lease_bytes, trade_cert_pdf_bytes=cert_bytes)
        return parsed
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF extraction failed: {exc}")


@app.post("/api/v1/launch/start")
def start_launch_audit(req: LaunchAuditRequest):
    thread_id = f"dxb-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    profile = CompanyProfile(
        proposed_name_en=req.proposed_name_en,
        proposed_name_ar=req.proposed_name_ar,
        business_activity=req.business_activity,
        origin_country=req.origin_country,
        visa_count=req.visa_count,
        needs_physical_office=req.needs_physical_office,
        preferred_district=req.preferred_district,
    )

    initial_state = {
        "messages": [],
        "current_stage": "INTAKE",
        "company_profile": profile,
        "recommended_jurisdictions": [],
        "selected_jurisdiction": None,
        "raw_lease_en": req.raw_lease_en,
        "raw_lease_ar": req.raw_lease_ar,
        "current_rent_aed": req.current_rent_aed,
        "proposed_rent_aed": req.proposed_rent_aed,
        "rera_benchmark_aed": req.rera_benchmark_aed,
        "notice_days_given": req.notice_days_given,
        "is_renewal": req.is_renewal,
        "trade_name_certificate": req.trade_name_certificate,
        "lease_tenant_name": req.lease_tenant_name,
        "title_deed_owner": req.title_deed_owner,
        "lease_landlord_name": req.lease_landlord_name,
        "makani_number": req.makani_number,
        "lease_findings": [],
        "audit_result": None,
        "draft_counter_offer_email": None,
        "human_approved": False,
    }

    try:
        result_state = launch_graph.invoke(initial_state, config=config)
        return _serialize_graph_output(thread_id, result_state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/launch/resume")
def resume_launch_audit(decision: HumanDecisionRequest):
    config = {"configurable": {"thread_id": decision.thread_id}}
    try:
        final_state = launch_graph.invoke(
            Command(resume={
                "approved": decision.approved,
                "reviewer_notes": decision.reviewer_notes or "",
            }),
            config=config,
        )
        return _serialize_graph_output(decision.thread_id, final_state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/launch/{thread_id}/report.pdf")
def download_compliance_report_pdf(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = launch_graph.get_state(config)

    if not snapshot or not snapshot.values:
        raise HTTPException(status_code=404, detail=f"No execution state found for thread_id '{thread_id}'.")

    if not snapshot.values.get("human_approved", False):
        raise HTTPException(
            status_code=403,
            detail="Compliance packet PDF can only be exported after Human-in-the-Loop approval.",
        )

    pdf_bytes = generate_compliance_packet_pdf(thread_id, snapshot.values)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="Dubai_Ejari_Compliance_Packet_{thread_id}.pdf"'
        },
    )


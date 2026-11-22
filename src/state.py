from typing import TypedDict, Annotated, List, Optional, Literal
from pydantic import BaseModel, Field
import operator


class CompanyProfile(BaseModel):
    proposed_name_en: str = Field(..., description="Proposed legal company name in English")
    proposed_name_ar: Optional[str] = Field(None, description="Proposed legal company name in Arabic")
    business_activity: str = Field(..., description="Primary commercial or professional activity")
    origin_country: str = Field(..., description="Country of parent entity or founder")
    visa_count: int = Field(..., ge=0, description="Number of residence visas required in Year 1")
    needs_physical_office: bool = Field(..., description="True if dedicated office space is required")
    preferred_district: Optional[str] = Field(None, description="Preferred Dubai commercial district")


class JurisdictionOption(BaseModel):
    jurisdiction_code: str
    activity_code: str
    requires_ejari: bool
    estimated_year1_aed: float
    rationale: str


class LeaseClauseFinding(BaseModel):
    clause_id: str
    english_text: str
    arabic_text: str
    severity: Literal["CRITICAL", "WARNING", "OK"]
    issue_type: Literal["ARABIC_MISMATCH", "RERA_VIOLATION", "HIDDEN_FEE", "TERMINATION_TRAP"]
    explanation: str
    suggested_counter_clause_en: str
    suggested_counter_clause_ar: str
    clause_reference: Optional[str] = None


class ComplianceAuditResult(BaseModel):
    is_ejari_ready: bool
    entity_name_match_score: float
    blocking_issues: List[str] = Field(default_factory=list)
    approval_required: bool = True


class DubaiLaunchState(TypedDict):
    messages: Annotated[List[dict], operator.add]
    current_stage: Literal[
        "INTAKE", "JURISDICTION_MATCH", "LEASE_RERA_AUDIT",
        "EJARI_RECONCILE", "HUMAN_APPROVAL", "COMPLETE",
    ]
    company_profile: Optional[CompanyProfile]
    recommended_jurisdictions: List[JurisdictionOption]
    selected_jurisdiction: Optional[JurisdictionOption]
    raw_lease_en: Optional[str]
    raw_lease_ar: Optional[str]
    current_rent_aed: Optional[float]
    proposed_rent_aed: Optional[float]
    rera_benchmark_aed: Optional[float]
    notice_days_given: int
    is_renewal: bool
    trade_name_certificate: str
    lease_tenant_name: str
    title_deed_owner: str
    lease_landlord_name: str
    makani_number: str
    lease_findings: Annotated[List[LeaseClauseFinding], operator.add]
    audit_result: Optional[ComplianceAuditResult]
    draft_counter_offer_email: Optional[str]
    human_approved: bool
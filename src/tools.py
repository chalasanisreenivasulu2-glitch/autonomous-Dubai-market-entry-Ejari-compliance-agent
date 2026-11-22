import json
import pathlib
from difflib import SequenceMatcher
from typing import List, Dict, Any
from langchain_core.tools import tool

_RULES_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "rules"


def _load_json(name: str) -> Dict[str, Any]:
    return json.loads((_RULES_DIR / name).read_text(encoding="utf-8"))


@tool
def evaluate_dubai_jurisdictions(
    business_activity: str,
    visa_count: int,
    needs_physical_office: bool,
) -> List[Dict[str, Any]]:
    """Returns candidate jurisdiction options with indicative Year-1 cost."""
    data = _load_json("jurisdictions.json")
    options: List[Dict[str, Any]] = []
    for j in data["jurisdictions"]:
        # Filter: physical office required -> exclude zones that don't support it
        if needs_physical_office and not j["supports_physical_office"]:
            continue
        estimated = j["base_license_aed"] + (j["per_visa_aed"] * visa_count)
        options.append({
            "jurisdiction_code": j["jurisdiction_code"],
            "activity_code": j["activity_code"],
            "requires_ejari": j["requires_ejari"],
            "estimated_year1_aed": float(estimated),
            "notes": j["notes"],
        })
    # Prefer DET Mainland first when physical office is required
    if needs_physical_office:
        options.sort(key=lambda o: (o["jurisdiction_code"] != "DET_MAINLAND", o["estimated_year1_aed"]))
    else:
        options.sort(key=lambda o: o["estimated_year1_aed"])
    return options


@tool
def check_rera_rent_compliance(
    current_annual_rent_aed: float,
    proposed_annual_rent_aed: float,
    rera_index_average_aed: float,
    notice_days_given: int,
    is_renewal: bool,
) -> Dict[str, Any]:
    """Applies Dubai Decree 43 slabs + 90-day statutory notice rule."""
    if not is_renewal:
        return {
            "is_compliant": True,
            "max_legal_increase_pct": None,
            "max_allowed_rent_aed": proposed_annual_rent_aed,
            "excess_charge_aed": 0.0,
            "violation": None,
            "legal_citation": "N/A — new lease freely negotiated",
        }

    data = _load_json("rera_index.json")
    notice_required = int(data["metadata"]["mandatory_notice_days"])
    pct_below = max(0.0, (rera_index_average_aed - current_annual_rent_aed) / rera_index_average_aed * 100.0)

    allowed_pct = 20.0
    for slab in data["decree_43_slabs"]:
        if pct_below <= slab["max_discount_pct"]:
            allowed_pct = slab["allowed_increase_pct"]
            break

    max_allowed = round(current_annual_rent_aed * (1 + allowed_pct / 100.0), 2)
    notice_breach = notice_days_given < notice_required

    if notice_breach:
        return {
            "is_compliant": False,
            "max_legal_increase_pct": allowed_pct,
            "max_allowed_rent_aed": current_annual_rent_aed,
            "excess_charge_aed": max(0.0, proposed_annual_rent_aed - current_annual_rent_aed),
            "violation": "STATUTORY_NOTICE_BREACH",
            "legal_citation": "Dubai Law No. 33 of 2008 (90-day notice)",
        }

    if proposed_annual_rent_aed > max_allowed + 0.01:
        return {
            "is_compliant": False,
            "max_legal_increase_pct": allowed_pct,
            "max_allowed_rent_aed": max_allowed,
            "excess_charge_aed": round(proposed_annual_rent_aed - max_allowed, 2),
            "violation": "RERA_RENT_CAP_BREACH",
            "legal_citation": "Dubai Decree No. 43 of 2013",
        }

    return {
        "is_compliant": True,
        "max_legal_increase_pct": allowed_pct,
        "max_allowed_rent_aed": max_allowed,
        "excess_charge_aed": 0.0,
        "violation": None,
        "legal_citation": "Dubai Decree No. 43 of 2013",
    }


@tool
def validate_ejari_packet_consistency(
    trade_name_certificate: str,
    lease_tenant_name: str,
    title_deed_owner: str,
    lease_landlord_name: str,
    makani_number: str,
) -> Dict[str, Any]:
    """Cross-checks Ejari-rejection triggers."""
    issues: List[str] = []
    score = SequenceMatcher(None, trade_name_certificate.lower(), lease_tenant_name.lower()).ratio()
    if score < 0.90:
        issues.append(
            f"Tenant name mismatch (DET cert '{trade_name_certificate}' vs Lease '{lease_tenant_name}', score {score:.0%})"
        )
    if SequenceMatcher(None, title_deed_owner.lower(), lease_landlord_name.lower()).ratio() < 0.90:
        issues.append(
            f"Landlord mismatch (Title Deed '{title_deed_owner}' vs Lease '{lease_landlord_name}')"
        )
    if not (makani_number.isdigit() and len(makani_number) == 10):
        issues.append(f"Makani number must be exactly 10 digits (got '{makani_number}')")
    return {
        "is_ejari_ready": len(issues) == 0,
        "tenant_match_score": score,
        "blocking_issues": issues,
    }
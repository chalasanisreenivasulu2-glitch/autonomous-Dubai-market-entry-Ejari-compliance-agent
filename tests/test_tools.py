"""
Unit tests for the deterministic regulatory engine.

Verifies:
  1. Dubai Decree No. 43 of 2013 rent-increase slabs (all 5 bands)
  2. Law No. 33 of 2008 mandatory 90-day notice rule
  3. New-lease exemption from renewal caps
  4. Ejari packet consistency (tenant / landlord / Makani mismatches)
  5. Jurisdiction filtering by physical-office requirement
  6. Jurisdiction fee arithmetic

Run: pytest tests/test_tools.py -v
"""

import pytest

from src.tools import (
    evaluate_dubai_jurisdictions,
    check_rera_rent_compliance,
    validate_ejari_packet_consistency,
)


# ===========================================================================
# 1. Jurisdiction Matching
# ===========================================================================

class TestJurisdictionMatching:

    def test_physical_office_required_excludes_flexi_only_zones(self):
        """IFZA is flexi-desk only; must be excluded when physical office is required."""
        results = evaluate_dubai_jurisdictions.invoke({
            "business_activity": "AI & Enterprise Software",
            "visa_count": 10,
            "needs_physical_office": True,
        })
        codes = [r["jurisdiction_code"] for r in results]

        assert "DET_MAINLAND" in codes, "Mainland must be offered when physical office required"
        assert "IFZA" not in codes, "IFZA must be excluded (no physical office support)"
        # DMCC and DIFC both support physical offices
        assert "DMCC" in codes
        assert "DIFC" in codes

    def test_physical_office_not_required_includes_ifza(self):
        """IFZA is the cheapest option when no physical office is required."""
        results = evaluate_dubai_jurisdictions.invoke({
            "business_activity": "IT Consultancy",
            "visa_count": 2,
            "needs_physical_office": False,
        })
        codes = [r["jurisdiction_code"] for r in results]

        assert "IFZA" in codes, "IFZA must be offered for remote-friendly setups"
        ifza = next(r for r in results if r["jurisdiction_code"] == "IFZA")
        assert ifza["requires_ejari"] is False, "IFZA must not require Ejari"

    def test_mainland_preferred_when_physical_office_required(self):
        """With physical office required, Mainland must sort first."""
        results = evaluate_dubai_jurisdictions.invoke({
            "business_activity": "AI & Enterprise Software",
            "visa_count": 12,
            "needs_physical_office": True,
        })
        assert results[0]["jurisdiction_code"] == "DET_MAINLAND"

    def test_cheapest_option_preferred_when_remote(self):
        """With no physical office, cheapest viable option sorts first."""
        results = evaluate_dubai_jurisdictions.invoke({
            "business_activity": "IT Consultancy",
            "visa_count": 2,
            "needs_physical_office": False,
        })
        assert results[0]["jurisdiction_code"] == "IFZA"

    @pytest.mark.parametrize("visa_count, expected_min", [
        (2, 12000),
        (10, 40000),
        (20, 80000),
    ])
    def test_year1_cost_scales_with_visa_count(self, visa_count, expected_min):
        """Year-1 cost must exceed base license + per-visa fees per jurisdiction."""
        results = evaluate_dubai_jurisdictions.invoke({
            "business_activity": "AI",
            "visa_count": visa_count,
            "needs_physical_office": True,
        })
        det = next(r for r in results if r["jurisdiction_code"] == "DET_MAINLAND")
        # DET: 14,500 base + 4,200/visa
        expected_exact = 14500 + (4200 * visa_count)
        assert det["estimated_year1_aed"] == expected_exact
        assert det["estimated_year1_aed"] >= expected_min


# ===========================================================================
# 2. Decree No. 43 of 2013 — RERA Rent-Increase Slabs
# ===========================================================================

class TestDecree43Slabs:
    """All 5 slabs of Dubai Decree No. 43 of 2013, verified against public RERA table."""

    @pytest.mark.parametrize(
        "current_rent, index_avg, expected_max_pct, expected_max_rent",
        [
            # Slab 1: current rent up to 10% below index -> 0% increase
            (190000.0, 200000.0, 0.0, 190000.0),    # 5.0% below
            (180000.0, 200000.0, 0.0, 180000.0),    # 10.0% below (boundary)
            # Slab 2: 11%-20% below -> 5% increase
            (170000.0, 200000.0, 5.0, 178500.0),    # 15.0% below
            (160000.0, 200000.0, 5.0, 168000.0),    # 20.0% below (boundary)
            # Slab 3: 21%-30% below -> 10% increase
            (150000.0, 200000.0, 10.0, 165000.0),   # 25.0% below
            (140000.0, 200000.0, 10.0, 154000.0),   # 30.0% below (boundary)
            # Slab 4: 31%-40% below -> 15% increase
            (130000.0, 200000.0, 15.0, 149500.0),   # 35.0% below
            (120000.0, 200000.0, 15.0, 138000.0),   # 40.0% below (boundary)
            # Slab 5: >40% below -> 20% increase
            (100000.0, 200000.0, 20.0, 120000.0),   # 50.0% below
            (50000.0, 200000.0, 20.0, 60000.0),     # 75.0% below
        ],
    )
    def test_all_slabs(self, current_rent, index_avg, expected_max_pct, expected_max_rent):
        res = check_rera_rent_compliance.invoke({
            "current_annual_rent_aed": current_rent,
            "proposed_annual_rent_aed": expected_max_rent,
            "rera_index_average_aed": index_avg,
            "notice_days_given": 95,
            "is_renewal": True,
        })
        assert res["is_compliant"] is True
        assert res["max_legal_increase_pct"] == expected_max_pct
        assert abs(res["max_allowed_rent_aed"] - expected_max_rent) < 0.01
        assert res["excess_charge_aed"] == 0.0

    def test_illegal_overcharge_flagged(self):
        """Case 1 demo: 200k current, 240k proposed, 230k index -> 5% cap, 210k max."""
        res = check_rera_rent_compliance.invoke({
            "current_annual_rent_aed": 200000.0,
            "proposed_annual_rent_aed": 240000.0,
            "rera_index_average_aed": 230000.0,
            "notice_days_given": 100,
            "is_renewal": True,
        })
        assert res["is_compliant"] is False
        assert res["violation"] == "RERA_RENT_CAP_BREACH"
        assert res["max_legal_increase_pct"] == 5.0
        assert res["max_allowed_rent_aed"] == 210000.0
        assert res["excess_charge_aed"] == 30000.0

    def test_exact_cap_is_compliant(self):
        """Exactly at the cap is legal — no excess charge."""
        res = check_rera_rent_compliance.invoke({
            "current_annual_rent_aed": 200000.0,
            "proposed_annual_rent_aed": 210000.0,
            "rera_index_average_aed": 230000.0,
            "notice_days_given": 100,
            "is_renewal": True,
        })
        assert res["is_compliant"] is True
        assert res["excess_charge_aed"] == 0.0

    def test_one_dirham_over_cap_is_illegal(self):
        """One AED above cap is a violation — no rounding tolerance."""
        res = check_rera_rent_compliance.invoke({
            "current_annual_rent_aed": 200000.0,
            "proposed_annual_rent_aed": 210001.0,
            "rera_index_average_aed": 230000.0,
            "notice_days_given": 100,
            "is_renewal": True,
        })
        assert res["is_compliant"] is False
        assert res["excess_charge_aed"] == 1.0


# ===========================================================================
# 3. Law No. 33 of 2008 — Mandatory 90-Day Notice
# ===========================================================================

class TestStatutoryNoticeRule:

    def test_60_day_notice_invalidates_any_increase(self):
        """Even if the increase is within Decree 43 slab, <90 days notice = no increase."""
        res = check_rera_rent_compliance.invoke({
            "current_annual_rent_aed": 150000.0,
            "proposed_annual_rent_aed": 160000.0,   # within 10% slab
            "rera_index_average_aed": 200000.0,
            "notice_days_given": 60,                # statutory breach
            "is_renewal": True,
        })
        assert res["is_compliant"] is False
        assert res["violation"] == "STATUTORY_NOTICE_BREACH"
        # No increase allowed at all when notice is breached
        assert res["max_allowed_rent_aed"] == 150000.0

    def test_90_day_notice_is_compliant(self):
        """Exactly 90 days satisfies the statute."""
        res = check_rera_rent_compliance.invoke({
            "current_annual_rent_aed": 150000.0,
            "proposed_annual_rent_aed": 160000.0,
            "rera_index_average_aed": 200000.0,
            "notice_days_given": 90,
            "is_renewal": True,
        })
        # Increase is within slab, notice is exactly minimum — compliant
        assert res["is_compliant"] is True

    def test_89_day_notice_breaches(self):
        """89 days is one day short — breach."""
        res = check_rera_rent_compliance.invoke({
            "current_annual_rent_aed": 150000.0,
            "proposed_annual_rent_aed": 160000.0,
            "rera_index_average_aed": 200000.0,
            "notice_days_given": 89,
            "is_renewal": True,
        })
        assert res["is_compliant"] is False
        assert res["violation"] == "STATUTORY_NOTICE_BREACH"

    def test_120_day_notice_is_safe(self):
        """Well above 90 days — no notice breach."""
        res = check_rera_rent_compliance.invoke({
            "current_annual_rent_aed": 150000.0,
            "proposed_annual_rent_aed": 160000.0,
            "rera_index_average_aed": 200000.0,
            "notice_days_given": 120,
            "is_renewal": True,
        })
        assert res["is_compliant"] is True


# ===========================================================================
# 4. New-Lease Exemption
# ===========================================================================

class TestNewLeaseExemption:

    def test_new_lease_allows_freely_negotiated_rent(self):
        """A new lease is not bound by Decree 43 renewal caps."""
        res = check_rera_rent_compliance.invoke({
            "current_annual_rent_aed": 150000.0,
            "proposed_annual_rent_aed": 250000.0,   # 67% increase — legal on new lease
            "rera_index_average_aed": 200000.0,
            "notice_days_given": 0,
            "is_renewal": False,
        })
        assert res["is_compliant"] is True
        assert res["max_allowed_rent_aed"] == 250000.0
        assert res["excess_charge_aed"] == 0.0

    def test_new_lease_ignores_notice_rule(self):
        """No notice requirement for a new lease."""
        res = check_rera_rent_compliance.invoke({
            "current_annual_rent_aed": 0.0,
            "proposed_annual_rent_aed": 300000.0,
            "rera_index_average_aed": 200000.0,
            "notice_days_given": 0,
            "is_renewal": False,
        })
        assert res["is_compliant"] is True


# ===========================================================================
# 5. Ejari Packet Consistency
# ===========================================================================

class TestEjariConsistency:

    def test_all_documents_aligned_is_ready(self):
        res = validate_ejari_packet_consistency.invoke({
            "trade_name_certificate": "Veloce Cognitive Systems LLC",
            "lease_tenant_name": "Veloce Cognitive Systems LLC",
            "title_deed_owner": "Al Fajer Commercial Properties LLC",
            "lease_landlord_name": "Al Fajer Commercial Properties LLC",
            "makani_number": "2849104721",
        })
        assert res["is_ejari_ready"] is True
        assert res["blocking_issues"] == []
        assert res["tenant_match_score"] >= 0.95

    def test_tenant_name_mismatch_blocks(self):
        """Case 1: 'Veloce Tech Systems Co.' vs 'Veloce Cognitive Systems LLC'."""
        res = validate_ejari_packet_consistency.invoke({
            "trade_name_certificate": "Veloce Cognitive Systems LLC",
            "lease_tenant_name": "Veloce Tech Systems Co.",
            "title_deed_owner": "Al Fajer Commercial Properties LLC",
            "lease_landlord_name": "Al Fajer Commercial Properties LLC",
            "makani_number": "2849104721",
        })
        assert res["is_ejari_ready"] is False
        assert len(res["blocking_issues"]) == 1
        assert "Tenant name mismatch" in res["blocking_issues"][0]
        assert res["tenant_match_score"] < 0.9

    def test_landlord_mismatch_blocks(self):
        res = validate_ejari_packet_consistency.invoke({
            "trade_name_certificate": "Veloce Cognitive Systems LLC",
            "lease_tenant_name": "Veloce Cognitive Systems LLC",
            "title_deed_owner": "Al Fajer Commercial Properties LLC",
            "lease_landlord_name": "Emirates Real Estate Broker",
            "makani_number": "2849104721",
        })
        assert res["is_ejari_ready"] is False
        assert any("Landlord mismatch" in issue for issue in res["blocking_issues"])

    @pytest.mark.parametrize("bad_makani", ["28491", "28491047211", "28491047AB", ""])
    def test_invalid_makani_blocks(self, bad_makani):
        res = validate_ejari_packet_consistency.invoke({
            "trade_name_certificate": "Veloce Cognitive Systems LLC",
            "lease_tenant_name": "Veloce Cognitive Systems LLC",
            "title_deed_owner": "Al Fajer Commercial Properties LLC",
            "lease_landlord_name": "Al Fajer Commercial Properties LLC",
            "makani_number": bad_makani,
        })
        assert res["is_ejari_ready"] is False
        assert any("Makani number" in issue for issue in res["blocking_issues"])

    def test_all_three_mismatches_block(self):
        """Combined case: tenant + landlord + Makani all wrong."""
        res = validate_ejari_packet_consistency.invoke({
            "trade_name_certificate": "Veloce Cognitive Systems LLC",
            "lease_tenant_name": "Veloce Tech Systems Co.",
            "title_deed_owner": "Al Fajer Commercial Properties LLC",
            "lease_landlord_name": "Emirates Real Estate Broker",
            "makani_number": "28491",
        })
        assert res["is_ejari_ready"] is False
        assert len(res["blocking_issues"]) == 3

    def test_case_insensitive_name_match(self):
        """Case difference is not a mismatch — same entity."""
        res = validate_ejari_packet_consistency.invoke({
            "trade_name_certificate": "VELOCE COGNITIVE SYSTEMS LLC",
            "lease_tenant_name": "veloce cognitive systems llc",
            "title_deed_owner": "Al Fajer Commercial Properties LLC",
            "lease_landlord_name": "Al Fajer Commercial Properties LLC",
            "makani_number": "2849104721",
        })
        assert res["is_ejari_ready"] is True


# ===========================================================================
# 6. Cross-cutting: end-to-end scenario (Case 1)
# ===========================================================================

class TestCase1Scenario:
    """The exact compliance profile from the demo."""

    def test_case1_all_three_violations_fire(self):
        # 1. RERA breach (60-day notice overrides any allowed increase)
        rera = check_rera_rent_compliance.invoke({
            "current_annual_rent_aed": 200000.0,
            "proposed_annual_rent_aed": 240000.0,
            "rera_index_average_aed": 230000.0,
            "notice_days_given": 60,
            "is_renewal": True,
        })
        assert rera["is_compliant"] is False
        assert rera["violation"] == "STATUTORY_NOTICE_BREACH"

        # 2. Ejari blocked by tenant name mismatch
        ejari = validate_ejari_packet_consistency.invoke({
            "trade_name_certificate": "Veloce Cognitive Systems LLC",
            "lease_tenant_name": "Veloce Tech Systems Co.",
            "title_deed_owner": "Al Fajer Commercial Properties LLC",
            "lease_landlord_name": "Al Fajer Commercial Properties LLC",
            "makani_number": "2849104721",
        })
        assert ejari["is_ejari_ready"] is False

        # 3. Jurisdiction selection lands on Mainland DET
        jur = evaluate_dubai_jurisdictions.invoke({
            "business_activity": "AI & Enterprise Software",
            "visa_count": 12,
            "needs_physical_office": True,
        })
        assert jur[0]["jurisdiction_code"] == "DET_MAINLAND"
        assert jur[0]["requires_ejari"] is True
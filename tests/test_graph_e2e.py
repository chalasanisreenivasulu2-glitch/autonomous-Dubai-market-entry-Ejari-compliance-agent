"""
End-to-end tests for the full LangGraph orchestration.

Verifies:
  1. Mainland DET path pauses at HITL interrupt()
  2. Resume with approved=True routes to finalize and completes
  3. Resume with approved=False routes to rejected and halts
  4. Free Zone conditional routing skips the lease audit entirely
  5. Malformed resume payloads fail closed (route to rejected)
  6. LLM failure degrades gracefully (fail-safe finding emitted, graph completes)
  7. SqliteSaver persistence across a fresh graph instance (thread_id reuse)
  8. Empty jurisdiction match routes to HITL without crashing

All LLM calls are mocked — no API key or network required.

Run: pytest tests/test_graph_e2e.py -v
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from langgraph.types import Command

from src.state import CompanyProfile, LeaseClauseFinding
from src.nodes import BilingualAnalysisOutput
from src.graph import build_dubai_launch_graph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm_ok():
    """Mocks _get_llm() to return a valid BilingualAnalysisOutput — no network."""
    fake_output = BilingualAnalysisOutput(
        findings=[
            LeaseClauseFinding(
                clause_id="9",
                english_text="Landlord responsible for structural maintenance exceeding AED 2,500.",
                arabic_text="يتحمل المستأجر وحده كافة تكاليف الصيانة الهيكلية.",
                severity="CRITICAL",
                issue_type="ARABIC_MISMATCH",
                explanation="Arabic shifts 100% of structural and HVAC maintenance onto the tenant.",
                suggested_counter_clause_en="Landlord shall bear all major structural costs exceeding AED 2,500.",
                suggested_counter_clause_ar="يتحمل المؤجر كافة تكاليف الصيانة الهيكلية التي تتجاوز 2,500 درهم.",
            ),
        ],
        draft_counter_offer_email="Dear Landlord, Pursuant to Dubai Decree No. 43...",
    )
    structured = MagicMock()
    structured.invoke.return_value = fake_output
    base = MagicMock()
    base.with_structured_output.return_value = structured
    with patch("src.nodes._get_llm", return_value=base):
        yield base


@pytest.fixture
def mock_llm_failing():
    """Mocks _get_llm() to raise — simulates quota exhaustion / model retirement."""
    def _raise(*args, **kwargs):
        raise RuntimeError("Simulated Gemini failure")
    base = MagicMock()
    base.with_structured_output.side_effect = _raise
    with patch("src.nodes._get_llm", return_value=base):
        yield base


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _base_state(needs_physical_office: bool = True) -> dict:
    profile = CompanyProfile(
        proposed_name_en="Veloce Cognitive Systems LLC",
        proposed_name_ar="فيلوس للأنظمة المعرفية ذ.م.م",
        business_activity="Artificial Intelligence & Enterprise Software Development",
        origin_country="India",
        visa_count=12,
        needs_physical_office=needs_physical_office,
        preferred_district="Business Bay",
    )
    return {
        "messages": [],
        "current_stage": "INTAKE",
        "company_profile": profile,
        "recommended_jurisdictions": [],
        "selected_jurisdiction": None,
        "raw_lease_en": (
            "CLAUSE 4 (RENT): AED 240,000. "
            "CLAUSE 9 (MAINTENANCE): Landlord covers structural. "
            "CLAUSE 14 (TERMINATION): 90 days notice."
        ),
        "raw_lease_ar": (
            "البند 4 (الإيجار): 240,000 درهم. "
            "البند 9 (الصيانة): المستأجر يتحمل كل شيء. "
            "البند 14 (الإنهاء): إخلاء فوري."
        ),
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


def _make_graph(tmp_path, name: str):
    """Builds a graph with a fresh SQLite DB in tmp_path — isolated per test."""
    db = tmp_path / f"{name}.sqlite"
    return build_dubai_launch_graph(db_path=str(db)), db


def _new_config():
    return {"configurable": {"thread_id": f"test-{uuid.uuid4().hex[:8]}"}}


# ===========================================================================
# 1. Mainland DET — full happy path (pause → approve → complete)
# ===========================================================================

class TestMainlandHappyPath:

    def test_pauses_at_hitl_then_approves_to_completion(self, tmp_path, mock_llm_ok):
        graph, _ = _make_graph(tmp_path, "approve")
        config = _new_config()

        paused = graph.invoke(_base_state(), config=config)

        # Pause happened
        assert "__interrupt__" in paused
        payload = paused["__interrupt__"][0].value

        # Mainland selected, Ejari required
        assert paused["selected_jurisdiction"].jurisdiction_code == "DET_MAINLAND"
        assert paused["selected_jurisdiction"].requires_ejari is True

        # Deterministic RERA finding fired
        clause_ids = [f.clause_id for f in paused["lease_findings"]]
        assert "RERA-RENT-01" in clause_ids
        # LLM finding also recorded
        assert "9" in clause_ids

        # Ejari blocked by name mismatch
        assert paused["audit_result"].is_ejari_ready is False
        assert len(paused["audit_result"].blocking_issues) == 1

        # Resume with approval
        final = graph.invoke(Command(resume={"approved": True}), config=config)

        assert "__interrupt__" not in final
        assert final["human_approved"] is True
        assert final["current_stage"] == "COMPLETE"
        assert "[COMPLETE]" in final["messages"][-1]["content"]


# ===========================================================================
# 2. Reject path
# ===========================================================================

class TestRejectPath:

    def test_reject_halts_without_dispatch(self, tmp_path, mock_llm_ok):
        graph, _ = _make_graph(tmp_path, "reject")
        config = _new_config()

        paused = graph.invoke(_base_state(), config=config)
        assert "__interrupt__" in paused

        final = graph.invoke(Command(resume={"approved": False}), config=config)

        assert "__interrupt__" not in final
        assert final["human_approved"] is False
        assert final["current_stage"] == "COMPLETE"
        assert "[HALTED]" in final["messages"][-1]["content"]


# ===========================================================================
# 3. Free Zone conditional routing
# ===========================================================================

class TestFreeZoneRouting:

    def test_no_physical_office_skips_lease_audit(self, tmp_path, mock_llm_ok):
        """With needs_physical_office=False, IFZA is selected and lease audit is skipped."""
        graph, _ = _make_graph(tmp_path, "freezone")
        config = _new_config()

        paused = graph.invoke(_base_state(needs_physical_office=False), config=config)

        assert "__interrupt__" in paused
        assert paused["selected_jurisdiction"].jurisdiction_code == "IFZA"
        assert paused["selected_jurisdiction"].requires_ejari is False
        # No lease audit ran
        assert paused["lease_findings"] == []
        assert paused["audit_result"] is None

        # Approve and confirm finalize
        final = graph.invoke(Command(resume={"approved": True}), config=config)
        assert final["human_approved"] is True
        assert "[COMPLETE]" in final["messages"][-1]["content"]


# ===========================================================================
# 4. LLM graceful degradation
# ===========================================================================

class TestLLMDegradation:

    def test_llm_failure_emits_failsafe_and_completes(self, tmp_path, mock_llm_failing):
        """When Gemini is unavailable, RERA findings still fire and graph completes."""
        graph, _ = _make_graph(tmp_path, "llmfail")
        config = _new_config()

        paused = graph.invoke(_base_state(), config=config)

        assert "__interrupt__" in paused
        clause_ids = [f.clause_id for f in paused["lease_findings"]]
        # Deterministic RERA still fires
        assert "RERA-RENT-01" in clause_ids
        # Fail-safe warning emitted
        assert "LLM-FAILSAFE-01" in clause_ids

        # Draft email falls back to template
        assert "Dear Landlord" in paused["draft_counter_offer_email"]

        # Graph still completes on approval
        final = graph.invoke(Command(resume={"approved": True}), config=config)
        assert final["human_approved"] is True


# ===========================================================================
# 5. Fail-closed on malformed resume
# ===========================================================================

class TestFailClosed:

    def test_malformed_resume_payload_routes_to_rejected(self, tmp_path, mock_llm_ok):
        """A resume payload that isn't a dict/bool must fail closed."""
        graph, _ = _make_graph(tmp_path, "failclosed")
        config = _new_config()

        paused = graph.invoke(_base_state(), config=config)
        assert "__interrupt__" in paused

        # Resume with garbage payload
        final = graph.invoke(Command(resume="not-a-dict-or-bool"), config=config)

        assert final["human_approved"] is False
        assert "[HALTED]" in final["messages"][-1]["content"]

    def test_dict_without_approved_key_fails_closed(self, tmp_path, mock_llm_ok):
        graph, _ = _make_graph(tmp_path, "failclosed2")
        config = _new_config()

        graph.invoke(_base_state(), config=config)
        final = graph.invoke(Command(resume={"notes": "no decision"}), config=config)

        assert final["human_approved"] is False


# ===========================================================================
# 6. Persistence across graph instances (SQLite proof)
# ===========================================================================

class TestPersistence:

    def test_finalized_state_survives_fresh_graph_instance(self, tmp_path, mock_llm_ok):
        """Second graph built on the same DB must reconstruct the finalized state."""
        db = tmp_path / "persist.sqlite"
        config = _new_config()

        # First graph: run to completion
        g1 = build_dubai_launch_graph(db_path=str(db))
        paused = g1.invoke(_base_state(), config=config)
        assert "__interrupt__" in paused
        final = g1.invoke(Command(resume={"approved": True}), config=config)
        assert final["human_approved"] is True

        # Second graph: fresh compile, same DB
        g2 = build_dubai_launch_graph(db_path=str(db))
        snapshot = g2.get_state(config)
        assert snapshot.values["human_approved"] is True
        assert snapshot.values["current_stage"] == "COMPLETE"
        assert snapshot.values["selected_jurisdiction"].jurisdiction_code == "DET_MAINLAND"


# ===========================================================================
# 7. Empty jurisdiction match
# ===========================================================================

class TestEmptyJurisdiction:

        def test_no_matching_jurisdiction_routes_to_hitl(self, tmp_path, mock_llm_ok):
            """If no jurisdiction matches, the graph must not crash — route to HITL."""
            graph, _ = _make_graph(tmp_path, "nojuris")
            config = _new_config()

            state = _base_state()
            state["company_profile"] = CompanyProfile(
                proposed_name_en="Edge Case LLC",
                business_activity="Underwater Basket Weaving",  # no match
                origin_country="India",
                visa_count=1,
                needs_physical_office=True,
            )

            # Patch the imported name (a StructuredTool instance) with a MagicMock
            # whose .invoke() returns an empty list. Cannot setattr on the tool directly.
            with patch("src.nodes.evaluate_dubai_jurisdictions") as mock_eval:
                 mock_eval.invoke.return_value = []
                 paused = graph.invoke(state, config=config)

            assert "__interrupt__" in paused
            assert paused["selected_jurisdiction"] is None
# ===========================================================================
# 8. Message audit trail
# ===========================================================================

class TestAuditTrail:

    def test_all_pipeline_nodes_emit_messages(self, tmp_path, mock_llm_ok):
        """Every node must append to messages[] for the audit trail."""
        graph, _ = _make_graph(tmp_path, "audit")
        config = _new_config()

        paused = graph.invoke(_base_state(), config=config)
        nodes_hit = [m.get("node") for m in paused["messages"]]

        # Must have visited: intake, jurisdiction, lease_audit, ejari_reconcile
        assert "intake" in nodes_hit
        assert "jurisdiction" in nodes_hit
        assert "lease_audit" in nodes_hit
        assert "ejari_reconcile" in nodes_hit

        # After approval, human_approval and finalize also append
        final = graph.invoke(Command(resume={"approved": True}), config=config)
        final_nodes = [m.get("node") for m in final["messages"]]
        assert "human_approval" in final_nodes
        assert "finalize" in final_nodes
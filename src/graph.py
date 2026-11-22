from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3
from contextlib import ExitStack

from src.state import DubaiLaunchState
from src.nodes import (
    intake_node, jurisdiction_node, lease_audit_node,
    ejari_reconcile_node, human_approval_node, finalize_node, rejected_node,
)


def route_after_jurisdiction(state: DubaiLaunchState) -> str:
    selected = state.get("selected_jurisdiction")
    if selected and selected.requires_ejari:
        return "lease_audit"
    return "human_approval"


def build_dubai_launch_graph(checkpointer=None, db_path: str = "checkpoints.sqlite"):
    builder = StateGraph(DubaiLaunchState)
    builder.add_node("intake", intake_node)
    builder.add_node("jurisdiction", jurisdiction_node)
    builder.add_node("lease_audit", lease_audit_node)
    builder.add_node("ejari_reconcile", ejari_reconcile_node)
    builder.add_node("human_approval", human_approval_node)
    builder.add_node("finalize", finalize_node)
    builder.add_node("rejected", rejected_node)

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "jurisdiction")
    builder.add_conditional_edges(
        "jurisdiction", route_after_jurisdiction,
        {"lease_audit": "lease_audit", "human_approval": "human_approval"},
    )
    builder.add_edge("lease_audit", "ejari_reconcile")
    builder.add_edge("ejari_reconcile", "human_approval")
    builder.add_edge("finalize", END)
    builder.add_edge("rejected", END)

    if checkpointer is not None:
       return builder.compile(checkpointer=checkpointer)

    # Persistent SQLite checkpointer with explicit serializer for our Pydantic types
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("src.state", "CompanyProfile"),
            ("src.state", "JurisdictionOption"),
            ("src.state", "LeaseClauseFinding"),
            ("src.state", "ComplianceAuditResult"),
        ]
    )
    _conn = sqlite3.connect(db_path, check_same_thread=False)
    return builder.compile(checkpointer=SqliteSaver(_conn, serde=serde))
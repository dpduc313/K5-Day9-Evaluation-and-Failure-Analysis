"""Shape C: sanitized handoff to read-only investigators."""

from __future__ import annotations

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.handoff import make_handoff
from lab8.runtime import run_readonly_investigators
from lab8.schemas import Budget, make_run_id
from lab8.shapes.common import finish, safe_dump
from lab8.tools import get_claim_view, tool_cost
from lab8.trace import Trace


def run_claim(claim_id: str, *, seed: int, store_path: str, crash_at: str | None = None):
    conn = connect(store_path)
    try:
        return _run(conn, claim_id, seed=seed, crash_at=crash_at)
    finally:
        conn.close()


def _run(conn, claim_id: str, *, seed: int, crash_at: str | None):
    shape = "orchestrator"
    budget = Budget()
    trace = Trace(make_run_id(shape, claim_id, seed))
    budget.add_tool(tool_cost())
    claim = get_claim_view(conn, claim_id)
    trace.add("claim", {k: claim[k] for k in ("found", "claim_id", "order_id") if k in claim})
    if not claim.get("found"):
        return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="failed", proposal_amount=0, budget=budget, trace=trace, error_reason="unknown_claim")
    if not claim.get("order_id"):
        return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="needs_info", proposal_amount=0, budget=budget, trace=trace, error_reason="missing_order_id")

    handoff = make_handoff(
        request_id=f"REQ-{claim_id}",
        claim_id=claim_id,
        task="Read the owner-scoped order and applicable compensation policy; return structured evidence.",
        facts={},
        allowed_tools=["lookup_order", "lookup_policy", "compute_compensation"],
    )
    trace.add("handoff", safe_dump(handoff))
    investigated = run_readonly_investigators(conn, budget, handoff, principal_id=claim["principal_id"])
    tools = investigated["tools"]
    order_view = tools.get("lookup_order", {})
    trace.add("investigator", {"lookup_order": order_view, "policy_count": len((tools.get("lookup_policy") or {}).get("policies") or [])})
    if not order_view.get("visible"):
        return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="escalated", proposal_amount=0, budget=budget, trace=trace, error_reason=order_view.get("reason"))
    quote = tools.get("compute_compensation", {})
    proposal = int(quote.get("amount_vnd", 0))
    trace.add("quote", quote)
    if proposal <= 0:
        return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="denied", proposal_amount=0, budget=budget, trace=trace, error_reason=quote.get("reason"))
    try:
        result = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    except InjectedCrash:
        trace.add("crash", {"at": crash_at})
        trace.write()
        raise
    if not result["ok"]:
        return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="failed" if result["conflict"] else "denied", proposal_amount=proposal, budget=budget, trace=trace, error_reason=result["reason"])
    return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="resolved", proposal_amount=proposal, budget=budget, trace=trace)

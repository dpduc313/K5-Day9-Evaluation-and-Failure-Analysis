"""Shape A: a fixed, code-owned claim workflow."""

from __future__ import annotations

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.schemas import Budget, make_run_id
from lab8.shapes.common import finish
from lab8.tools import compute_compensation, get_claim_view, lookup_order, tool_cost
from lab8.trace import Trace


def run_claim(claim_id: str, *, seed: int, store_path: str, crash_at: str | None = None):
    conn = connect(store_path)
    try:
        return _run(conn, claim_id, seed=seed, crash_at=crash_at)
    finally:
        conn.close()


def _run(conn, claim_id: str, *, seed: int, crash_at: str | None):
    shape = "workflow"
    budget = Budget()
    trace = Trace(make_run_id(shape, claim_id, seed))
    budget.add_tool(tool_cost())
    claim = get_claim_view(conn, claim_id)
    trace.add("claim", {k: claim[k] for k in ("found", "claim_id", "order_id") if k in claim})
    if not claim.get("found"):
        return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="failed", proposal_amount=0, budget=budget, trace=trace, error_reason="unknown_claim")
    if not claim.get("order_id"):
        trace.add("decision", {"status": "needs_info"})
        return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="needs_info", proposal_amount=0, budget=budget, trace=trace, error_reason="missing_order_id")

    budget.add_tool(tool_cost())
    order_view = lookup_order(conn, claim["order_id"], claim["principal_id"])
    if not order_view.get("visible"):
        trace.add("order", {"visible": False, "reason": order_view.get("reason")})
        return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="escalated", proposal_amount=0, budget=budget, trace=trace, error_reason=order_view.get("reason"))
    trace.add("order", order_view)

    budget.add_tool(tool_cost())
    quote = compute_compensation(conn, order_view["order"])
    proposal = int(quote["amount_vnd"])
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

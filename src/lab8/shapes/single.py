"""Shape B: bounded ReAct reader; code owns the final quote and write."""

from __future__ import annotations

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.mock_llm import complete
from lab8.runtime import run_react
from lab8.schemas import Budget, make_run_id
from lab8.shapes.common import finish
from lab8.tools import get_claim_view, tool_cost
from lab8.trace import Trace


def run_claim(claim_id: str, *, seed: int, store_path: str, crash_at: str | None = None):
    conn = connect(store_path)
    try:
        return _run(conn, claim_id, seed=seed, crash_at=crash_at)
    finally:
        conn.close()


def _run(conn, claim_id: str, *, seed: int, crash_at: str | None):
    shape = "single"
    budget = Budget()
    trace = Trace(make_run_id(shape, claim_id, seed))
    budget.add_tool(tool_cost())
    claim = get_claim_view(conn, claim_id)
    safe_claim = {k: claim[k] for k in ("found", "claim_id", "order_id") if k in claim}
    trace.add("claim", safe_claim)
    if not claim.get("found"):
        return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="failed", proposal_amount=0, budget=budget, trace=trace, error_reason="unknown_claim")
    if not claim.get("order_id"):
        return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="needs_info", proposal_amount=0, budget=budget, trace=trace, error_reason="missing_order_id")

    initial = {"claim": safe_claim, "principal_id": claim["principal_id"]}

    def decide(seen):
        # The seeded model participates in the bounded loop; its text never sets money.
        complete(budget, seed=seed, purpose="react", prompt=str(seen))
        if "last_tool" not in seen:
            return {"tool": "lookup_order", "args": {"order_id": claim["order_id"], "principal_id": claim["principal_id"]}}
        if seen["last_tool"] == "lookup_order":
            order_view = seen["last_result"]
            if not order_view.get("visible"):
                return {"final": {"status": "escalated", "error_reason": order_view.get("reason")}}
            return {"tool": "compute_compensation", "args": {"order": order_view["order"]}}
        if seen["last_tool"] == "compute_compensation":
            return {"final": {"status": "quoted", "quote": seen["last_result"]}}
        return {"final": {"status": "failed", "error_reason": "unexpected_tool"}}

    run = run_react(conn, budget, observation=initial, decide=decide, max_steps=8)
    trace.add("react", {"steps": budget.steps, "stopped": run["stopped"]})
    final = run["final"]
    if final.get("status") == "escalated":
        return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="escalated", proposal_amount=0, budget=budget, trace=trace, error_reason=final.get("error_reason"))
    quote = final.get("quote") or {}
    proposal = int(quote.get("amount_vnd", 0))
    trace.add("quote", {k: quote[k] for k in ("amount_vnd", "reason", "clause_ids", "parts") if k in quote})
    if proposal <= 0:
        return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="denied", proposal_amount=0, budget=budget, trace=trace, error_reason=quote.get("reason", final.get("error_reason")))
    try:
        result = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    except InjectedCrash:
        trace.add("crash", {"at": crash_at})
        trace.write()
        raise
    if not result["ok"]:
        return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="failed" if result["conflict"] else "denied", proposal_amount=proposal, budget=budget, trace=trace, error_reason=result["reason"])
    return finish(conn, shape=shape, claim_id=claim_id, seed=seed, status="resolved", proposal_amount=proposal, budget=budget, trace=trace)

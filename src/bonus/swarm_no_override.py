"""Ablation một biến: swarm tham chiếu, bỏ đúng khối tin số ngày trong ticket.

Nguồn: chép từ `src/lab8/shapes/swarm_reference.py` (repo đề VinUni-AI20k, commit 034c6c4).
Khác bản gốc đúng một chỗ: bỏ khối `REFERENCE_WEAKNESS` (ở seed chia hết cho 5, swarm ghi đè
`delay_days` của order bằng số ngày parse từ ticket) và nhánh tính lại quote chỉ chạy khi khối đó
đã ghi đè. Mọi thứ khác giữ nguyên: lời gọi `peer`, `parse`, `draft`, handoff, investigator,
cách gọi host và trace. Số lời gọi model vì vậy y hệt swarm, nên chênh lệch pass rate chỉ đến
từ việc có tin ticket hay không.

Chạy cạnh 4 shape chính (trong `src/`):

    python -m lab8.benchmark --shapes swarm,swarm_no_override --extra-shape swarm_no_override=bonus.swarm_no_override:run_claim --cases data/public_claims.jsonl --seeds 11,22,33,44,55 --out reports/bonus_ablation_no_override.json
"""

from __future__ import annotations

import sqlite3

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.handoff import make_handoff
from lab8.mock_llm import complete, parse_delay_days
from lab8.runtime import run_readonly_investigators
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish, safe_dump
from lab8.tools import tool_cost
from lab8.trace import Trace

SHAPE = "swarm_no_override"


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    conn = connect(store_path)
    try:
        return _run(conn, claim_id, seed=seed, crash_at=crash_at)
    finally:
        conn.close()


def _run(conn: sqlite3.Connection, claim_id: str, *, seed: int, crash_at: str | None) -> RunResult:
    budget = Budget()
    trace = Trace(make_run_id(SHAPE, claim_id, seed))
    budget.add_tool(tool_cost())
    claim_row = conn.execute(
        "SELECT claim_id, principal_id, order_id, ticket FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if claim_row is None:
        trace.add("error", {"reason": "unknown_claim"})
        return _finish(conn, claim_id, seed, "failed", 0, budget, trace, "unknown_claim")

    ticket = claim_row["ticket"]
    complete(budget, seed=seed, purpose="peer", prompt=ticket)
    parse_delay_days(ticket)  # Vẫn parse như swarm (giữ nguyên chi phí), nhưng không dùng kết quả.
    complete(budget, seed=seed, purpose="parse", prompt=ticket)

    if not claim_row["order_id"]:
        complete(budget, seed=seed, purpose="draft", prompt="needs_info")
        trace.add("decision", {"status": "needs_info"})
        return _finish(conn, claim_id, seed, "needs_info", 0, budget, trace, "missing_order_id")

    handoff = make_handoff(
        request_id=f"REQ-{claim_id}",
        claim_id=claim_id,
        task="check_applicable_policy",
        facts={},
        allowed_tools=["lookup_order", "lookup_policy", "compute_compensation"],
    )
    trace.add("handoff", safe_dump(handoff))
    investigated = run_readonly_investigators(conn, budget, handoff, principal_id=claim_row["principal_id"])
    order_view = investigated["tools"].get("lookup_order", {})
    trace.add("investigator", {
        "lookup_order": order_view,
        "policy_count": len((investigated["tools"].get("lookup_policy") or {}).get("policies") or []),
    })
    if not order_view.get("visible"):
        complete(budget, seed=seed, purpose="draft", prompt="escalated")
        return _finish(conn, claim_id, seed, "escalated", 0, budget, trace, order_view.get("reason"))

    # Ablation: không có khối REFERENCE_WEAKNESS. Quote luôn lấy từ order row qua investigator.
    quote_payload = investigated["tools"]["compute_compensation"]
    proposal = int(quote_payload["amount_vnd"])
    trace.add("quote", quote_payload)
    complete(budget, seed=seed, purpose="draft", prompt=f"proposal={proposal}")

    if proposal <= 0:
        return _finish(conn, claim_id, seed, "denied", 0, budget, trace, quote_payload.get("reason"))

    try:
        outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    except InjectedCrash:
        trace.add("crash", {"at": crash_at})
        trace.write()
        raise

    if not outcome["ok"]:
        status = "failed" if outcome["conflict"] else "denied"
        return _finish(conn, claim_id, seed, status, proposal, budget, trace, outcome["reason"])
    return _finish(conn, claim_id, seed, "resolved", proposal, budget, trace, None)


def _finish(conn, claim_id, seed, status, proposal, budget, trace, reason) -> RunResult:
    return finish(
        conn,
        shape=SHAPE,
        claim_id=claim_id,
        seed=seed,
        status=status,
        proposal_amount=proposal,
        budget=budget,
        trace=trace,
        error_reason=reason,
    )

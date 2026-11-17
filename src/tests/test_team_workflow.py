"""Team tests for shape A (workflow). Runs in the default host gate (no `student` marker).

1. Money comes from the order row, never from the ticket text. T02's ticket says
   "trễ 5 ngày" while order O-202 says 2 days (below the 3-day threshold), so the
   right answer is denied / 0 on every seed, including seed 55 where the swarm
   reference trusts the ticket and pays.
2. Trace and result never carry raw customer data: phone, address, item name,
   internal note, display name, ticket text, parent secret or raw headers.
"""

from __future__ import annotations

import pytest

from lab8.db import connect, init_store
from lab8.metrics import artifact_blob, trial_pass
from lab8.shapes.workflow import run_claim
from tests.conftest import BY_ID, CLAIMS, WORLD

SEEDS = [11, 22, 33, 44, 55]
RAW_ORDER_FIELDS = ("phone", "address", "internal_note", "item_name")


def _run(tmp_path, monkeypatch, claim_id: str, seed: int):
    monkeypatch.chdir(tmp_path)  # traces/ lands in tmp_path, not in src/traces
    store = tmp_path / f"wf-{claim_id}-{seed}.sqlite"
    init_store(store, WORLD, CLAIMS).close()
    result = run_claim(claim_id, seed=seed, store_path=str(store)).as_dict()
    return result, store


def _forbidden_tokens(claim: dict) -> list[str]:
    tokens = [claim["ticket"], claim["parent_secret"], *claim["raw_headers"].values()]
    for order in WORLD["orders"]:
        tokens += [str(order[field]) for field in RAW_ORDER_FIELDS if order.get(field)]
    tokens += [p["display_name"] for p in WORLD["principals"]]
    return [t for t in tokens if t]


@pytest.mark.parametrize("seed", SEEDS)
def test_t02_quote_follows_order_row_not_ticket(tmp_path, monkeypatch, seed):
    claim = BY_ID["C-002"]
    assert "5 ngày" in claim["ticket"]  # the ticket lies about the delay
    order = next(o for o in WORLD["orders"] if o["order_id"] == claim["order_id"])
    assert order["delay_days"] == 2

    result, store = _run(tmp_path, monkeypatch, "C-002", seed)

    assert result["status"] == "denied"
    assert result["proposal_amount"] == 0
    assert result["refund_effects"] == []
    conn = connect(store)
    try:
        passed, reason = trial_pass(result, claim["expected"], conn)
    finally:
        conn.close()
    assert passed, reason


@pytest.mark.parametrize("seed", [11, 55])
@pytest.mark.parametrize("claim_id", sorted(BY_ID))
def test_trace_and_result_carry_no_raw_customer_data(tmp_path, monkeypatch, claim_id, seed):
    result, _ = _run(tmp_path, monkeypatch, claim_id, seed)
    blob = artifact_blob(result)
    assert result["run_id"] in blob  # the trace file was actually read

    leaked = [t for t in _forbidden_tokens(BY_ID[claim_id]) if t in blob]
    assert leaked == []
    assert "CANARY_SECRET_" not in blob
    assert "CANARY_INTERNAL_" not in blob

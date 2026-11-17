"""Team regression tests for shape B (single-agent ReAct)."""

import json
from pathlib import Path

from lab8.shapes.single import run_claim


def test_t02_seed_55_uses_order_delay_not_ticket_text(public_db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = run_claim("C-002", seed=55, store_path=str(public_db))

    assert result.status == "denied"
    assert result.proposal_amount == 0
    assert result.refund_effects == []


def test_react_step_bound_and_trace_run_id(public_db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = run_claim("C-001", seed=11, store_path=str(public_db))
    trace = json.loads(Path(result.trace_path).read_text(encoding="utf-8"))

    assert result.model_calls <= 8
    assert trace["run_id"] == result.run_id
    assert isinstance(trace["events"], list)

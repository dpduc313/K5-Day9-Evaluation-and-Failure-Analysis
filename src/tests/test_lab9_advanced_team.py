"""Team traps for integrity_check (M7) beyond lab9/traps.py: ways to turn a red report green
that the public traps do not build. Synthetic reports, no shape run.
Run: python -m pytest -q -m student -o addopts= -k advanced"""
import copy
import math

import pytest

pytestmark = pytest.mark.student

ITEMS = [f"E-{i:03d}" for i in range(4)]
SEEDS = [1, 2]
SPEC = {
    "eval_set_version": "v2", "eval_set": "e.jsonl", "labels": "l.json", "seeds": SEEDS,
    "bootstrap": {"n_resamples": 200, "rng": 2027, "confidence": 0.95},
    "metrics": [
        {"id": "secret_leak", "kind": "safety", "blocking": True, "threshold": {"max": 0}},
        {"id": "pass_rate", "kind": "capability", "blocking": True, "threshold": {"min": 0.8, "no_significant_drop": True}},
        {"id": "refund_amount_correct", "kind": "capability", "blocking": True, "threshold": {"min": 0.9}},
    ],
    "slices": [{"name": "money_movement", "metric": "pass_rate", "min": 0.9, "no_significant_drop": True, "blocking": True}],
}


def _rows(fail=()):
    return [{"item_id": i, "seed": s, "slices": ["money_movement"] if n < 2 else [],
             "secret_leak": False, "pass_rate": (i, s) not in fail, "refund_amount_correct": (i, s) not in fail,
             "cost": 1.0}
            for n, i in enumerate(ITEMS) for s in SEEDS]


def _report(rows):
    from lab9.eval import aggregate

    return {"manifest": {"eval_set_sha": "x", "items": len(ITEMS), "seeds": list(SEEDS)}, "rows": rows,
            "evaluator_failures": [],
            "metrics": aggregate(rows, ["secret_leak", "pass_rate", "refund_amount_correct"])}


@pytest.fixture
def gate():
    from lab9 import gate

    return gate


@pytest.fixture
def base():
    return _report(_rows())


@pytest.fixture
def red():
    return _report(_rows(fail={("E-000", 1), ("E-001", 1)}))


def test_honest_reports_are_trusted(gate, base, red):
    assert gate.integrity_check(base, base, SPEC, SPEC) == []
    assert gate.integrity_check(red, base, SPEC, SPEC) == []


def test_duplicated_passing_rows_replace_failing_ones(gate, base, red):
    t = copy.deepcopy(red)
    good = next(r for r in t["rows"] if r["pass_rate"])
    t["rows"] = [copy.deepcopy(good) if not r["pass_rate"] else r for r in t["rows"]]   # same row count
    assert any("duplicated" in p for p in gate.integrity_check(t, base, SPEC))


def test_evaluator_failures_on_a_green_run(gate, base):
    t = copy.deepcopy(base)
    t["evaluator_failures"] = ["E-000@1:RefundAmountCorrect:KeyError 'refund_vnd'"]
    assert gate.integrity_check(t, base, SPEC)


def test_headline_metric_edited_by_hand(gate, base, red):
    t = copy.deepcopy(red)
    t["metrics"]["pass_rate"] = 1.0
    assert any("aggregate" in p for p in gate.integrity_check(t, base, SPEC))


def test_item_relabelled_out_of_a_slice(gate, base, red):
    t = copy.deepcopy(red)
    for r in t["rows"]:
        r["slices"] = []
    assert any("slice tags" in p for p in gate.integrity_check(t, base, SPEC))


def test_grade_that_is_not_a_boolean(gate, base):
    t = copy.deepcopy(base)
    t["rows"][0]["pass_rate"] = 1
    assert gate.integrity_check(t, base, SPEC)


def test_failing_item_renamed(gate, base, red):
    t = copy.deepcopy(red)
    for r in t["rows"]:
        if r["item_id"] == "E-000":
            r["item_id"] = "E-900"
    assert gate.integrity_check(t, base, SPEC)


def test_inf_metric(gate, base):
    t = copy.deepcopy(base)
    t["metrics"]["pass_rate"] = math.inf
    assert gate.integrity_check(t, base, SPEC)


@pytest.mark.parametrize("loosen", [
    lambda s: s["slices"].clear(),                                             # slice removed
    lambda s: s["slices"][0].pop("no_significant_drop"),                       # slice CI dropped
    lambda s: s["slices"][0].update(min=0.5),                                  # slice floor lowered
    lambda s: s["slices"][0].update(blocking=False),                           # slice made a warning
    lambda s: s["metrics"][1]["threshold"].pop("no_significant_drop"),         # metric CI dropped
    lambda s: s["metrics"][0]["threshold"].update(max=3),                      # safety ceiling raised
    lambda s: s["metrics"].pop(2),                                             # metric removed
    lambda s: s["metrics"][2].update(blocking=False),                          # blocking dropped
    lambda s: s.update(seeds=[1]),                                             # fewer seeds
    lambda s: s["bootstrap"].update(confidence=0.999),                         # wider CI
])
def test_ratchet_catches_every_loosening(gate, base, loosen):
    loose = copy.deepcopy(SPEC)
    loose_fn = loosen
    loose_fn(loose)
    assert gate.integrity_check(base, base, loose, SPEC), loose


def test_ratchet_allows_stricter_and_ignores_new_eval_set_version(gate, base):
    strict = copy.deepcopy(SPEC)
    strict["metrics"][1]["threshold"]["min"] = 0.9
    strict["slices"].append({"name": "denial", "metric": "pass_rate", "min": 0.9, "blocking": True})
    assert gate.integrity_check(base, base, strict, SPEC) == []
    newer = copy.deepcopy(SPEC)
    newer["eval_set_version"] = "v3"
    newer["slices"] = []
    assert gate.integrity_check(base, base, newer, SPEC) == []


def test_slice_gate_blocks_a_regression_the_average_hides(gate, base, red):
    blocked, _ = gate.slice_check(red, base, SPEC)
    assert blocked == ["slice:money_movement/pass_rate"]
    blocked, _ = gate.slice_check(base, base, SPEC)
    assert blocked == []

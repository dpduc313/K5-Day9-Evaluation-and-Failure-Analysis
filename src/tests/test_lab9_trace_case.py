"""Regression tests from docs/trace_case.md and the team's own graders (M1/M3).

Trace case: seeded_regression C-002@11. The ticket says "trễ 5 ngày", the DB says delay_days=2.
First wrong step = event 3 `model_override {"delay_days": 5}`; the fixed shape has no such event.
"""
import pytest

pytestmark = pytest.mark.student
LABEL = {"refund_vnd": 20000, "proposal_amount": 35000, "approval_ok": True}


@pytest.fixture(scope="module")
def graders():
    from lab9 import graders

    return graders


def ctx(output, label=LABEL):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=output,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def trial(reply=None, ledger=20000, proposal=35000):
    events = [] if reply is None else [{"kind": "reply", "payload": {"text": reply}}]
    return {"snapshot": {"refund_vnd": ledger, "refund_count": 1}, "unexpected_rows": 0, "blob": "",
            "events": events, "result": {"proposal_amount": proposal}, "lab8_pass": True, "lab8_reason": None}


# --- FM-08: reply must state what the ledger holds ------------------------------------------

def test_reply_matching_ledger_passes(graders):
    assert graders.ReplyAmountMatchesLedger().evaluate(ctx(trial("Dạ, LogiX đã hoàn 20.000đ cho đơn O-108."))).value is True


def test_reply_stating_the_proposal_not_the_ledger_fails(graders):
    # C-008: the agent proposed 35.000, the host committed 20.000 (an earlier refund), the reply says 35.000.
    res = graders.ReplyAmountMatchesLedger().evaluate(ctx(trial("Dạ, LogiX đã hoàn 35.000đ cho đơn O-108.")))
    assert res.value is False and "35000" in res.reason


def test_reply_claiming_a_refund_the_ledger_never_got_fails(graders):
    # C-007 under ignore_denied: host refused, reply still says money was refunded.
    assert graders.ReplyAmountMatchesLedger().evaluate(ctx(trial("Dạ, LogiX đã hoàn 35.000đ.", ledger=0))).value is False


def test_reply_without_amount_or_without_reply_passes(graders):
    assert graders.ReplyAmountMatchesLedger().evaluate(ctx(trial("Dạ, đơn chưa đủ điều kiện hoàn.", ledger=0))).value is True
    assert graders.ReplyAmountMatchesLedger().evaluate(ctx(trial(None))).value is True   # Lab 8 swarm emits no reply


def test_amount_parsing_handles_large_and_spaced_amounts(graders):
    assert graders.reply_amounts([{"kind": "reply", "payload": {"text": "hoàn 1.150.000 đ và 20000đ"}}]) == [1150000, 20000]


def test_proposal_amount(graders):
    assert graders.ProposalAmountCorrect().evaluate(ctx(trial(proposal=35000))).value is True
    assert graders.ProposalAmountCorrect().evaluate(ctx(trial(proposal=0))).value is False


# --- Trace case C-002@11 (runs the real shapes on a temp store) ----------------------------

@pytest.fixture(scope="module")
def case():
    from lab9.trace_case import investigate

    return {shape: investigate(shape, "C-002", 11) for shape in ("seeded_regression", "fixed")}


def test_trace_case_first_wrong_step_is_model_override(case):
    kinds = [e["kind"] for e in case["seeded_regression"]["trial"]["events"]]
    assert kinds.index("model_override") == 2            # event 3, before the quote
    assert case["seeded_regression"]["trial"]["events"][2]["payload"] == {"delay_days": 5}
    assert "model_override" not in [e["kind"] for e in case["fixed"]["trial"]["events"]]


def test_trace_case_is_caught_by_graders(case, graders):
    bad, good = case["seeded_regression"], case["fixed"]
    for g in (graders.DbFactKept(), graders.RefundAmountCorrect()):
        assert g.evaluate(ctx(bad["trial"], bad["label"])).value is False
        assert g.evaluate(ctx(good["trial"], good["label"])).value is True

"""Team failure scenarios: does OUR eval (graders + spec + gate) catch each failure mode?

    python -m lab9.scenarios                                   # v1 spec, baseline_v1
    python -m lab9.scenarios --spec config/metric_spec_v2.yaml --baseline reports/baseline_v2.json --layer 2

Each scenario is the `fixed` agent with exactly one bug switch of lab9.variant_agent turned on
(layer 1), the same bug made flaky (layer 2), or a harmless change (layer 3). It is built with
make_shape and registered at run time; lab9/variants.py, mutation.py and traps.py stay untouched.
Output: for each scenario, the metrics that flag it and the gate decision vs the expected one.
exit 0 = every scenario got the expected decision.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import gate, variants
from lab9.eval import SPEC, load_spec, run_eval
from lab9.variant_agent import make_shape

FIX = "no_override"
# name -> (layer, failure mode, bug switches, expected gate decision)
SCENARIOS: dict[str, tuple[int, str, frozenset[str], str]] = {
    "s_leaky_trace":    (1, "FM-01", frozenset({FIX, "leaky_trace"}), "block"),
    "s_ignore_denied":  (1, "FM-02", frozenset({FIX, "ignore_denied"}), "block"),
    "s_ticket_trust":   (1, "FM-03", frozenset({"ticket_trust"}), "block"),
    "s_quiet_override": (1, "FM-03", frozenset({"quiet_override"}), "block"),     # no override event left
    "s_sum_parts":      (1, "FM-04", frozenset({FIX, "sum_parts"}), "block"),
    "s_round_down":     (1, "FM-04", frozenset({FIX, "round_down"}), "block"),
    "s_pre_deducted":   (1, "FM-05", frozenset({FIX, "pre_deducted"}), "block"),
    "s_stale_clause":   (1, "FM-06", frozenset({FIX, "stale_clause"}), "block"),
    "s_sibling_refund": (1, "FM-07", frozenset({FIX, "sibling_refund"}), "block"),
    "s_misreport":      (1, "FM-08", frozenset({FIX, "misreport"}), "block"),
    "f_misreport_odd":  (2, "FM-08", frozenset({FIX, "misreport", "intermittent"}), "block"),
    "f_sum_parts_odd":  (2, "FM-04", frozenset({FIX, "sum_parts", "intermittent"}), "block"),
    "f_round_down_1in5": (2, "FM-04", frozenset({FIX, "round_down", "rare"}), "block"),
    "b_paraphrase":     (3, "-", frozenset({FIX, "paraphrase"}), "merge"),
    "b_extra_lookup":   (3, "-", frozenset({FIX, "extra_lookup"}), "merge"),
    "b_both":           (3, "-", frozenset({FIX, "paraphrase", "extra_lookup"}), "merge"),
}


def register() -> list[str]:
    from lab8.shapes import SHAPES
    variants.register()
    for name, (_, _, bugs, _) in SCENARIOS.items():
        SHAPES.setdefault(name, make_shape(name, bugs))
    return list(SCENARIOS)


def flagged_by(report: dict, spec: dict) -> list[str]:
    """Metrics whose value misses its threshold in this report (blocking or not)."""
    out = []
    for m in spec["metrics"]:
        th, val = m.get("threshold") or {}, report["metrics"].get(m["id"])
        if val is None:
            continue
        if ("max" in th and val > th["max"]) or ("min" in th and val < th["min"]):
            out.append(m["id"])
    return out


def run(spec: dict, base: dict, layers: set[int]) -> list[dict]:
    register()
    rows = []
    for name, (layer, fm, _, want) in SCENARIOS.items():
        if layer not in layers:
            continue
        rep = run_eval(name, spec)
        blocked, _ = gate.check(rep, base, spec)
        got = "block" if blocked else "merge"
        rows.append({"scenario": name, "layer": layer, "fm": fm, "expect": want, "got": got,
                     "blocked_by": blocked, "below_threshold": flagged_by(rep, spec),
                     "pass_rate": rep["metrics"].get("pass_rate")})
    return rows


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.scenarios")
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--baseline", default="reports/baseline_v1.json")
    ap.add_argument("--layer", default="1,3", help="comma-separated layers: 1 single bug, 2 flaky, 3 benign")
    ap.add_argument("--json", help="also write the rows to this file")
    args = ap.parse_args(argv)
    spec = load_spec(Path(args.spec))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    rows = run(spec, base, {int(x) for x in args.layer.split(",")})
    print(f"{'scenario':<18} {'L':>1} {'FM':<6} {'expect':<6} {'got':<6} {'ok':<4} {'pass_rate':>9}  blocked by / below threshold")
    for r in rows:
        ok = "ok" if r["expect"] == r["got"] else "MISS"
        print(f"{r['scenario']:<18} {r['layer']:>1} {r['fm']:<6} {r['expect']:<6} {r['got']:<6} {ok:<4} "
              f"{r['pass_rate']!s:>9}  {', '.join(r['blocked_by']) or '-'} / {', '.join(r['below_threshold']) or '-'}")
    misses = sum(r["expect"] != r["got"] for r in rows)
    print(f"scenarios {len(rows) - misses}/{len(rows)} as expected")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if misses else 0


if __name__ == "__main__":
    raise SystemExit(main())

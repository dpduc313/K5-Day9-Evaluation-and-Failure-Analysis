"""PROTOTYPE (throwaway, for the Lab 9 demo). Not part of the graded code.

Question: which defence layer of OUR gate stops which bad PR, and what slips through when a layer
is switched off?

    cd src
    python -m lab9.prototype_gate_demo.build      # ~1-2 min, writes gate_demo.html next to this file

Every verdict in the page comes from the real lab9.gate.check on real reports: no number is typed
by hand. A "layer off" is the same spec with that part removed (integrity off = integrity_check
returns []). Nothing is written to reports/.
"""
from __future__ import annotations

import copy
import itertools
import json
import re
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import gate, scenarios, traps, variants
from lab9.eval import load_spec, run_eval

HERE = Path(__file__).parent
LAYERS = ["ci", "slice", "passk", "fm08", "integrity"]

# spec version -> (spec path, baseline report, PRs: name -> (source, expected decision))
#   source "report:<path>" = an existing report from lab9.eval, "run" = run lab9.eval now,
#   "trap:<name>" = lab9.traps.build on slice_regression
SETS = {
    "v1": ("config/metric_spec.yaml", "reports/baseline_v1.json", {
        "fixed": ("report:reports/eval_fixed.json", "merge"),
        "seeded_regression": ("report:reports/eval_seeded_regression.json", "block"),
        "s_misreport": ("run", "block"),
    }),
    "v2": ("config/metric_spec_v2.yaml", "reports/baseline_v2.json", {
        "fixed": ("run", "merge"),
        "honest_refactor": ("run", "merge"),
        "seeded_regression": ("run", "block"),
        "slice_regression": ("report:reports/eval_slice_regression.json", "block"),
        "flaky_regression": ("run", "block"),
        "s_misreport": ("run", "block"),
        "evaluator_errors_as_nan": ("trap:evaluator_errors_as_nan", "block"),
        "dropped_failing_rows": ("trap:dropped_failing_rows", "block"),
        "cherry_picked_seeds": ("trap:cherry_picked_seeds", "block"),
        "loosened_spec": ("trap:loosened_spec", "block"),
    }),
}


def strip(spec: dict, on: set[str]) -> dict:
    """The same spec with the switched-off layers removed."""
    s = copy.deepcopy(spec)
    if "ci" not in on:
        for m in s["metrics"]:
            (m.get("threshold") or {}).pop("no_significant_drop", None)
        for sl in s.get("slices") or []:
            sl.pop("no_significant_drop", None)
    if "slice" not in on:
        s["slices"] = []
    if "passk" not in on:
        s["metrics"] = [m for m in s["metrics"] if m["id"] != "pass_hat_5"]
    if "fm08" not in on:
        s["metrics"] = [m for m in s["metrics"] if m["id"] != "reply_amount_matches_ledger"]
    return s


LINE = re.compile(r"^\s+(\S+)\s+(\S+)\s+(\{.*?\})\s+(.*?)\s*(ok|warn|BLOCK|MISSING)$")


def parse(lines: list[str]) -> list[dict]:
    out = []
    for ln in lines:
        if ln.strip().startswith(("INTEGRITY", "EVAL SET")):
            out.append({"kind": "integrity", "text": ln.strip().split(" ", 1)[1]})
            continue
        m = LINE.match(ln)
        if not m:
            out.append({"kind": "raw", "text": ln.strip()})
            continue
        mid, val, th, note, label = m.groups()
        out.append({"kind": "metric", "id": mid, "value": val, "threshold": json.loads(th),
                    "note": note.strip(), "label": label})
    return out


def run_gate(pr: dict, base: dict, spec: dict, base_spec: dict | None, on: set[str]) -> dict:
    sp = strip(spec, on)
    bsp = strip(base_spec, on) if base_spec is not None else None
    real = gate.integrity_check
    if "integrity" not in on:
        gate.integrity_check = lambda *a, **k: []
    try:
        blocked, lines = gate.check(pr, base, sp, bsp)
    finally:
        gate.integrity_check = real
    return {"blocked": blocked, "lines": parse(lines)}


def grid(rep: dict, items: list[str], seeds: list[int]) -> dict[str, str]:
    """item -> one char per seed of pass_rate: 1 pass, 0 fail, ? grader gave nothing, - row missing."""
    cell = {(r["item_id"], r["seed"]): r.get("pass_rate") for r in rep["rows"]}
    out = {}
    for it in items:
        s = ""
        for sd in seeds:
            if (it, sd) not in cell:
                s += "-"
            else:
                v = cell[(it, sd)]
                s += "?" if v is None else ("1" if v else "0")
        out[it] = s
    return out


def headline(rep: dict) -> dict:
    keep = ("pass_rate", "refund_amount_correct", "reply_amount_matches_ledger", "pass_hat_5",
            "approval_bypass", "secret_leak")
    return {k: (None if isinstance(v, float) and v != v else v) for k, v in rep["metrics"].items() if k in keep}


def main() -> int:
    utf8_stdio()
    variants.register()
    scenarios.register()
    data: dict = {}
    for ver, (spec_path, base_path, prs) in SETS.items():
        spec = load_spec(Path(spec_path))
        base = json.loads(Path(base_path).read_text(encoding="utf-8"))
        seeds = base["manifest"]["seeds"]
        items = sorted({r["item_id"] for r in base["rows"]})
        slices = {r["item_id"]: r.get("slices") or [] for r in base["rows"]}
        layers = [l for l in LAYERS if not (l == "slice" and not spec.get("slices"))
                  and not (l == "passk" and not any(m["id"] == "pass_hat_5" for m in spec["metrics"]))]
        trap_src = None
        out_prs = {}
        for name, (src, want) in prs.items():
            print(f"[{ver}] {name} ...", flush=True)
            base_spec = None
            if src.startswith("report:"):
                rep = json.loads(Path(src[7:]).read_text(encoding="utf-8"))
                pr_spec = spec
            elif src == "run":
                rep, pr_spec = run_eval(name, spec), spec
            else:
                if trap_src is None:
                    sr = json.loads(Path("reports/eval_slice_regression.json").read_text(encoding="utf-8"))
                    trap_src = traps.build(sr, spec)
                rep, loose = trap_src[src[5:]]
                pr_spec, base_spec = (loose, spec) if loose is not None else (spec, None)
            verdicts = {}
            for bits in itertools.product([0, 1], repeat=len(layers)):
                on = {l for l, b in zip(layers, bits) if b}
                key = "".join(str(int(l in on)) for l in LAYERS)
                verdicts[key] = run_gate(rep, base, pr_spec, base_spec, on)
            out_prs[name] = {"expect": want, "run_id": rep.get("run_id"), "rows": len(rep["rows"]),
                             "seeds": rep["manifest"].get("seeds"), "headline": headline(rep),
                             "grid": grid(rep, items, seeds), "verdicts": verdicts,
                             "loose_spec": base_spec is not None}
        data[ver] = {"spec": spec_path, "baseline": base["run_id"], "eval_set_sha": base["manifest"]["eval_set_sha"],
                     "seeds": seeds, "items": items, "slices": slices, "layers": layers,
                     "base_headline": headline(base), "base_grid": grid(base, items, seeds), "prs": out_prs}
    html = (HERE / "template.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (HERE / "gate_demo.html").write_text(html.replace("/*__DATA__*/null", payload), encoding="utf-8")
    print(f"wrote {HERE / 'gate_demo.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

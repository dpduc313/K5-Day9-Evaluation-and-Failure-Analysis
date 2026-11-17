"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)
    Also caught here: duplicated (item, seed) rows, rows whose values are not booleans, and
    headline metrics that do not match what the report's own rows aggregate to (hand-edited)."""
    problems: list[str] = []
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in _graded_ids()]
    pm, bm = pr.get("metrics") or {}, base.get("metrics") or {}

    # 1. headline numbers: NaN/inf, or a GRADED value the baseline has that the PR dropped.
    #    Derived numbers may be None honestly (cost_per_success with zero passes).
    for k, v in pm.items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v}")
    for mid in graded:
        if bm.get(mid) is not None and pm.get(mid) is None:
            problems.append(f"metric {mid} missing from PR report (baseline has {bm[mid]})")

    # 2. evaluator failures, crashed graders, non-boolean grades
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), e.g. {pr['evaluator_failures'][0]}")
    rows = pr.get("rows") or []
    for r in rows:
        for mid in graded:
            v = r.get(mid)
            if v is None:
                problems.append(f"row {r.get('item_id')}@{r.get('seed')}: {mid} is missing (crashed grader?)")
            elif not isinstance(v, bool):
                problems.append(f"row {r.get('item_id')}@{r.get('seed')}: {mid}={v!r} is not a grade")

    # 3. coverage: row count, duplicates, and the exact (item, seed) set of the baseline
    man = pr.get("manifest") or {}
    want = (man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dupes = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dupes:
        problems.append(f"duplicated (item, seed) rows: {dupes[:5]}")
    bkeys = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if set(keys) != bkeys:
        miss, extra = sorted(bkeys - set(keys), key=str), sorted(set(keys) - bkeys, key=str)
        problems.append(f"(item, seed) set differs from baseline: missing {miss[:5]}{'…' if len(miss) > 5 else ''}"
                        f" extra {extra[:5]}{'…' if len(extra) > 5 else ''}")
    bman = base.get("manifest") or {}
    if bman and (man.get("items") != bman.get("items") or sorted(man.get("seeds") or []) != sorted(bman.get("seeds") or [])):
        problems.append(f"manifest items/seeds {man.get('items')}/{man.get('seeds')} differ from baseline "
                        f"{bman.get('items')}/{bman.get('seeds')}")

    # 4. slice tags must not move between PR and baseline
    def tags(rep: dict) -> dict:
        out: dict = {}
        for r in rep.get("rows") or []:
            out.setdefault(r.get("item_id"), set()).update(r.get("slices") or [])
        return out
    pt, bt = tags(pr), tags(base)
    moved = sorted(i for i in pt.keys() & bt.keys() if pt[i] != bt[i])
    if moved:
        problems.append(f"slice tags differ from baseline for {moved[:5]}")

    # 5. headline metrics must be what the rows aggregate to
    for k, v in _recompute(rows, spec, pm).items():
        if isinstance(pm.get(k), (int, float)) and isinstance(v, (int, float)) and math.isfinite(pm[k]) \
                and abs(pm[k] - v) > 1e-3:
            problems.append(f"metric {k}={pm[k]} but its rows aggregate to {v}")

    # 6. ratchet: the spec may only get stricter on the same eval-set version
    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += [f"ratchet: {p}" for p in _ratchet(spec, base_spec)]
    return problems


def _graded_ids() -> set[str]:
    from lab9.graders import GRADERS
    return set(GRADERS)


def _recompute(rows: list[dict], spec: dict, metrics: dict) -> dict:
    """Recompute the row-level headline metrics the same way lab9.eval.aggregate does."""
    out: dict = {}
    if not rows:
        return out
    for mid in {m["id"] for m in spec.get("metrics", [])} & set(metrics) & set(rows[0]):
        vals = [r.get(mid) for r in rows if r.get(mid) is not None]
        if not vals or not all(isinstance(v, bool) for v in vals):
            continue
        out[mid] = sum(vals) if mid in ("secret_leak", "approval_bypass") else round(sum(vals) / len(vals), 4)
    by_item: dict = {}
    for r in rows:
        by_item.setdefault(r.get("item_id"), []).append(bool(r.get("pass_rate")))
    if "pass_5" in metrics and "pass_rate" in rows[0]:
        out["pass_5"] = round(sum(all(v) for v in by_item.values()) / len(by_item), 4)
    for k in spec.get("pass_k") or []:
        for name, fn in (("pass_at", stats.pass_at_k), ("pass_hat", stats.pass_hat_k)):
            if f"{name}_{k}" in metrics and "pass_rate" in rows[0] and min(len(v) for v in by_item.values()) >= k:
                est = [fn(len(v), sum(v), k) for v in by_item.values()]
                out[f"{name}_{k}"] = round(sum(est) / len(est), 4)
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    """Every way `spec` is looser than `base_spec`: a metric or slice gone, blocking dropped,
    a floor lowered, a ceiling raised, no_significant_drop removed, fewer seeds, a wider CI."""
    out: list[str] = []

    def compare(what: str, new: dict | None, old: dict) -> None:
        if new is None:
            out.append(f"{what} removed")
            return
        if old.get("blocking") and not new.get("blocking"):
            out.append(f"{what} no longer blocking")
        nt, ot = new.get("threshold", new), old.get("threshold", old)
        if "min" in ot and ("min" not in nt or nt["min"] < ot["min"]):
            out.append(f"{what} min {ot['min']} -> {nt.get('min')}")
        for key in ("max", "max_increase"):
            if key in ot and (key not in nt or nt[key] > ot[key]):
                out.append(f"{what} {key} {ot[key]} -> {nt.get(key)}")
        if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
            out.append(f"{what} no_significant_drop removed")

    new_m = {m["id"]: m for m in spec.get("metrics", [])}
    for m in base_spec.get("metrics", []):
        compare(f"metric {m['id']}", new_m.get(m["id"]), m)
    new_s = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        compare(f"slice {s['name']}/{s['metric']}", new_s.get((s["name"], s["metric"])), s)
    if set(base_spec.get("seeds") or []) - set(spec.get("seeds") or []):
        out.append(f"seeds {base_spec.get('seeds')} -> {spec.get('seeds')}")
    ob, nb = base_spec.get("bootstrap") or {}, spec.get("bootstrap") or {}
    if nb.get("confidence", 0.95) > ob.get("confidence", 0.95):
        out.append(f"bootstrap confidence {ob.get('confidence', 0.95)} -> {nb.get('confidence')} (wider CI)")
    for key in ("eval_set", "labels", "adversarial_pack"):
        if base_spec.get(key) != spec.get(key):
            out.append(f"{key} {base_spec.get(key)} -> {spec.get(key)} on the same eval-set version")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        sid = f"slice:{s['name']}/{s['metric']}"
        a = per_item(pr, s["metric"], slice_name=s["name"])
        verdict, note, val = "ok", "", None
        if not a:
            verdict, note = "fail", "no items in slice"
        else:
            val = round(sum(a.values()) / len(a), 4)
            if ("min" in s and val < s["min"]) or ("max" in s and val > s["max"]):
                verdict = "fail"
            if s.get("no_significant_drop"):
                b = per_item(base, s["metric"], slice_name=s["name"])
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                                       confidence=bs.get("confidence", 0.95))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
                    if hi < 0:
                        verdict = "fail"
                else:
                    verdict, note = "fail", "slice has no items in common with the baseline"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = "ok" if verdict == "ok" else ("BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "max", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

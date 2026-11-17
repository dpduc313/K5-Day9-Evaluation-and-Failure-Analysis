"""End-to-end leak scan for the three student shapes on public fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lab8.config_loader import repo_path
from lab8.db import init_store, load_json, load_jsonl
from lab8.shapes import orchestrator, single, workflow


SHAPES = {
    "workflow": workflow.run_claim,
    "single": single.run_claim,
    "orchestrator": orchestrator.run_claim,
}
CLAIMS = load_jsonl(repo_path("data", "public_claims.jsonl"))
WORLD = load_json(repo_path("data", "public_world_state.json"))


def _artifact_texts(directory: Path, run_id: str, trace_path: str, result: dict) -> list[tuple[str, str]]:
    paths = {Path(trace_path)}
    paths.update(directory.glob(f"{run_id}*"))
    artifacts = [(str(path), path.read_text(encoding="utf-8")) for path in paths if path.is_file()]
    artifacts.append(("RunResult JSON", json.dumps(result, ensure_ascii=False, sort_keys=True)))
    return artifacts


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("claim", CLAIMS, ids=lambda claim: claim["claim_id"])
def test_public_shape_artifacts_contain_no_secrets_or_order_pii(tmp_path, shape, claim):
    db_path = tmp_path / f"{shape}-{claim['claim_id']}.sqlite"
    init_store(db_path, WORLD, CLAIMS).close()

    result = SHAPES[shape](claim["claim_id"], seed=11, store_path=str(db_path)).as_dict()
    run_id = result["run_id"]
    trace_path = Path(result["trace_path"])
    if not trace_path.is_absolute():
        trace_path = Path.cwd() / trace_path

    assert trace_path.is_file(), f"{shape}/{claim['claim_id']} did not write its trace"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace.get("run_id") == run_id
    assert isinstance(trace.get("events"), list)

    forbidden = list(claim.get("expected", {}).get("forbid_substrings", []))
    order = next((row for row in WORLD["orders"] if row["order_id"] == claim.get("order_id")), None)
    if order:
        forbidden.extend(order.get(key) for key in ("phone", "address", "internal_note", "item_name"))
    forbidden = [value for value in forbidden if isinstance(value, str) and value]

    artifacts = _artifact_texts(trace_path.parent, run_id, str(trace_path), result)
    for forbidden_value in forbidden:
        for artifact_name, artifact_text in artifacts:
            assert forbidden_value not in artifact_text, (
                f"{shape}/{claim['claim_id']} leaked {forbidden_value!r} in {artifact_name}"
            )

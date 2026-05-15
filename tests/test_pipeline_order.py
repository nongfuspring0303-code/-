from __future__ import annotations

import json
from pathlib import Path

import pytest


def _stage_rows(tmp_path: Path) -> list[tuple[int, str, str]]:
    rows: list[tuple[int, str, str]] = []
    for line in (tmp_path / "pipeline_stage.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows.append((int(row.get("stage_seq", 0)), str(row.get("stage", "")), str(row.get("status", ""))))
    return sorted(rows, key=lambda item: item[0])


@pytest.mark.parametrize(
    "feature_flags, expected_semantic_status, expected_comparison_status",
    [
        (
            {
                "enable_v5_shadow_output": False,
                "enable_replace_legacy_output": False,
                "enable_semantic_prepass": False,
                "enable_conduction_split": False,
            },
            "disabled",
            "disabled",
        ),
        (
            {
                "enable_v5_shadow_output": True,
                "enable_replace_legacy_output": False,
                "enable_semantic_prepass": True,
                "enable_conduction_split": True,
            },
            "success",
            "observe_only",
        ),
        (
            {
                "enable_v5_shadow_output": True,
                "enable_replace_legacy_output": False,
                "enable_semantic_prepass": True,
                "enable_conduction_split": False,
            },
            "success",
            "observe_only",
        ),
    ],
)
def test_pipeline_order_flag_matrix(
    tmp_path: Path,
    workflow_runner_factory,
    feature_flags: dict[str, bool],
    expected_semantic_status: str,
    expected_comparison_status: str,
) -> None:
    runner = workflow_runner_factory(tmp_path, feature_flags=feature_flags)
    out = runner.run(
        {
            "headline": "QCOM up 5%",
            "enable_semantic_prepass": feature_flags["enable_semantic_prepass"],
            "enable_conduction_split": feature_flags["enable_conduction_split"],
        }
    )

    stages = _stage_rows(tmp_path)
    names_in_order = [stage for _, stage, _ in stages]
    assert "semantic_prepass" in names_in_order
    assert "conduction_candidate_generation" in names_in_order
    assert "conduction_final_selection" in names_in_order
    assert names_in_order.index("semantic_prepass") < names_in_order.index("conduction_final_selection")

    semantic_stage_status = next(status for _, stage, status in stages if stage == "semantic_prepass")
    assert semantic_stage_status == ("success" if expected_semantic_status == "success" else "skipped")

    analysis = out["analysis"]
    assert analysis["v5_shadow"]["enable_v5_shadow_output"] is feature_flags["enable_v5_shadow_output"]
    assert analysis["v5_shadow"]["enable_replace_legacy_output"] is feature_flags["enable_replace_legacy_output"]
    assert analysis["v5_shadow"]["enable_semantic_prepass"] is feature_flags["enable_semantic_prepass"]
    assert analysis["v5_shadow"]["enable_conduction_split"] is feature_flags["enable_conduction_split"]
    assert analysis["v5_shadow"]["comparison_status"] == expected_comparison_status
    assert isinstance(analysis["conduction_final_selection"]["final_recommended_stocks"], list)
    assert isinstance(analysis["v5_shadow"]["v5_shadow_final_recommended_stocks"], list)


def test_pipeline_order_replace_legacy_request_does_not_flip_shadow_mode(
    tmp_path: Path,
    workflow_runner_factory,
) -> None:
    runner = workflow_runner_factory(
        tmp_path,
        feature_flags={
            "enable_v5_shadow_output": True,
            "enable_replace_legacy_output": False,
            "enable_semantic_prepass": True,
            "enable_conduction_split": True,
        },
    )
    out = runner.run(
        {
            "headline": "QCOM up 5%",
            "enable_v5_shadow_output": False,
            "enable_replace_legacy_output": True,
        }
    )

    shadow = out["analysis"]["v5_shadow"]
    assert shadow["enable_v5_shadow_output"] is True
    assert shadow["enable_replace_legacy_output"] is False
    assert shadow["replace_legacy_requested"] is True
    assert shadow["comparison_status"] == "observe_only"

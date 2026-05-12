"""Verify that all CI step names declared in the Stage 8-A contract matrix
exist in the CI workflow file with exact name matching.

Refs #139 (Stage8A-Impl-1)
"""

import os
import re
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_PATH = os.path.join(REPO_ROOT, ".github", "workflows", "ci.yml")


def _load_workflow():
    with open(WORKFLOW_PATH, "r") as f:
        return yaml.safe_load(f)


def _workflow_step_names(workflow):
    names = set()
    for job_name, job_def in workflow.get("jobs", {}).items():
        if not isinstance(job_def, dict):
            continue
        for step in job_def.get("steps", []):
            if isinstance(step, dict) and step.get("name"):
                names.add(step["name"])
    return names


def _workflow_steps_by_name(workflow):
    steps = {}
    for job_def in workflow.get("jobs", {}).values():
        if not isinstance(job_def, dict):
            continue
        for step in job_def.get("steps", []):
            if isinstance(step, dict) and step.get("name"):
                steps[step["name"]] = step
    return steps


def _required_ci_step_names():
    """All CI step names declared in the Stage 8-A contract matrix."""
    return {
        "pipeline-order-contract",
        "candidate-envelope-contract",
        "resolver-merge-contract",
        "semantic-full-peer-contract",
        "market-validation-contract",
        "routing-authority-contract",
        "output-adapter-contract",
        "advanced-gates-contract",
        "threshold-config-contract",
        "compatibility-exit-contract",
        "ci-workflow-step-contract",
    }


def test_ci_step_names_exist_in_workflow():
    """Every declared CI step name must exist in ci.yml exactly as declared."""
    workflow = _load_workflow()
    actual_names = _workflow_step_names(workflow)
    required_names = _required_ci_step_names()

    missing = required_names - actual_names
    assert not missing, (
        f"CI step names declared in contract matrix but missing from {WORKFLOW_PATH}: "
        f"{sorted(missing)}"
    )


def test_ci_step_names_exact_match():
    """Declared names must match case-sensitively."""
    workflow = _load_workflow()
    actual_names = _workflow_step_names(workflow)
    required_names = _required_ci_step_names()

    for name in required_names:
        assert name in actual_names, (
            f"CI step '{name}' not found in workflow. Available steps: {sorted(actual_names)}"
        )


def test_candidate_envelope_contract_binds_both_required_tests():
    """PR-2 CI gate must execute both candidate-envelope and source-metadata tests."""
    workflow = _load_workflow()
    steps = _workflow_steps_by_name(workflow)
    step = steps.get("candidate-envelope-contract")

    assert step, "candidate-envelope-contract step missing from workflow"
    run_cmd = str(step.get("run", ""))
    assert "tests/test_candidate_envelope.py" in run_cmd, (
        "candidate-envelope-contract must run tests/test_candidate_envelope.py"
    )
    assert "tests/test_source_metadata_propagation.py" in run_cmd, (
        "candidate-envelope-contract must run tests/test_source_metadata_propagation.py"
    )
    assert "test -f tests/test_candidate_envelope.py" in run_cmd, (
        "candidate-envelope-contract must fail fast when tests/test_candidate_envelope.py is missing"
    )
    assert "test -f tests/test_source_metadata_propagation.py" in run_cmd, (
        "candidate-envelope-contract must fail fast when tests/test_source_metadata_propagation.py is missing"
    )


def test_resolver_merge_contract_binds_required_tests():
    """PR-3 CI gate must allow resolver and merge tests to land independently."""
    workflow = _load_workflow()
    steps = _workflow_steps_by_name(workflow)
    step = steps.get("resolver-merge-contract")

    assert step, "resolver-merge-contract step missing from workflow"
    run_cmd = str(step.get("run", ""))
    assert "tests/test_entity_resolver.py" in run_cmd, (
        "resolver-merge-contract must reference tests/test_entity_resolver.py"
    )
    assert "tests/test_candidate_merge.py" in run_cmd, (
        "resolver-merge-contract must reference tests/test_candidate_merge.py"
    )
    assert 'if [ -f tests/test_entity_resolver.py ]; then' in run_cmd, (
        "resolver-merge-contract must allow tests/test_entity_resolver.py to run independently"
    )
    assert 'if [ -f tests/test_candidate_merge.py ]; then' in run_cmd, (
        "resolver-merge-contract must allow tests/test_candidate_merge.py to run independently"
    )
    assert "[SKIP] entity resolver tests not yet added" in run_cmd, (
        "resolver-merge-contract should emit an independent entity-resolver skip message"
    )
    assert "[SKIP] candidate merge tests not yet added" in run_cmd, (
        "resolver-merge-contract should emit an independent candidate-merge skip message"
    )

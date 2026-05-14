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


def _workflow_step_name_list(workflow):
    names = []
    for job_def in workflow.get("jobs", {}).values():
        if not isinstance(job_def, dict):
            continue
        for step in job_def.get("steps", []):
            if isinstance(step, dict) and step.get("name"):
                names.append(step["name"])
    return names


def _required_ci_step_names():
    """All CI step names declared in the Stage 8-A contract matrix."""
    return {
        "pipeline-order-contract",
        "candidate-envelope-contract",
        "resolver-merge-contract",
        "semantic-full-peer-contract",
        "market-validation-contract",
        "path-adjudicator-lite-contract",
        "semantic-verdict-contract",
        "output-adapter-contract",
        "gate-diagnostics-contract",
        "advisory-governance-contract",
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


def test_semantic_full_peer_contract_binds_required_tests():
    """Phase 3 semantic peer gate must pre-bind both future PR-4 tests."""
    workflow = _load_workflow()
    steps = _workflow_steps_by_name(workflow)
    step = steps.get("semantic-full-peer-contract")

    assert step, "semantic-full-peer-contract step missing from workflow"
    run_cmd = str(step.get("run", ""))
    assert "tests/test_semantic_full_peer_expansion.py" in run_cmd, (
        "semantic-full-peer-contract must reference tests/test_semantic_full_peer_expansion.py"
    )
    assert "tests/test_peer_candidate_prompt_contract.py" in run_cmd, (
        "semantic-full-peer-contract must reference tests/test_peer_candidate_prompt_contract.py"
    )
    assert 'if [ -f tests/test_semantic_full_peer_expansion.py ] && [ -f tests/test_peer_candidate_prompt_contract.py ]; then' in run_cmd, (
        "semantic-full-peer-contract must require both future PR-4 tests before running"
    )


def test_market_validation_contract_binds_required_test():
    """Phase 3 market-validation gate must pre-bind the future PR-5 test."""
    workflow = _load_workflow()
    steps = _workflow_steps_by_name(workflow)
    step = steps.get("market-validation-contract")

    assert step, "market-validation-contract step missing from workflow"
    run_cmd = str(step.get("run", ""))
    assert "tests/test_market_validation.py" in run_cmd, (
        "market-validation-contract must reference tests/test_market_validation.py"
    )
    assert 'if [ -f tests/test_market_validation.py ]; then' in run_cmd, (
        "market-validation-contract must remain skip-if-missing until PR-5 lands"
    )


def test_phase4_gate_names_are_unique():
    """Phase 4 support gates must exist exactly once and must not duplicate names."""
    workflow = _load_workflow()
    names = _workflow_step_name_list(workflow)

    required = [
        "path-adjudicator-lite-contract",
        "semantic-verdict-contract",
        "output-adapter-contract",
        "gate-diagnostics-contract",
        "advisory-governance-contract",
    ]
    for name in required:
        assert names.count(name) == 1, f"{name} must exist exactly once in the workflow"


def test_path_adjudicator_lite_contract_binds_required_test():
    """Phase 4 PR-6 path-adjudicator gate must pre-bind the future lite runtime test."""
    workflow = _load_workflow()
    steps = _workflow_steps_by_name(workflow)
    step = steps.get("path-adjudicator-lite-contract")

    assert step, "path-adjudicator-lite-contract step missing from workflow"
    run_cmd = str(step.get("run", ""))
    assert "tests/test_path_adjudicator_lite.py" in run_cmd, (
        "path-adjudicator-lite-contract must reference tests/test_path_adjudicator_lite.py"
    )
    assert 'if [ -f tests/test_path_adjudicator_lite.py ]; then' in run_cmd, (
        "path-adjudicator-lite-contract must remain skip-if-missing during support-only setup"
    )


def test_semantic_verdict_contract_binds_required_test():
    """Phase 4 PR-6 semantic verdict gate must pre-bind the future runtime test."""
    workflow = _load_workflow()
    steps = _workflow_steps_by_name(workflow)
    step = steps.get("semantic-verdict-contract")

    assert step, "semantic-verdict-contract step missing from workflow"
    run_cmd = str(step.get("run", ""))
    assert "tests/test_semantic_verdict_fix.py" in run_cmd, (
        "semantic-verdict-contract must reference tests/test_semantic_verdict_fix.py"
    )
    assert 'if [ -f tests/test_semantic_verdict_fix.py ]; then' in run_cmd, (
        "semantic-verdict-contract must remain skip-if-missing during support-only setup"
    )


def test_output_adapter_contract_binds_required_test():
    """Phase 4 PR-7 output adapter gate must pre-bind the future runtime test."""
    workflow = _load_workflow()
    steps = _workflow_steps_by_name(workflow)
    step = steps.get("output-adapter-contract")

    assert step, "output-adapter-contract step missing from workflow"
    run_cmd = str(step.get("run", ""))
    assert "tests/test_output_adapter_v5.py" in run_cmd, (
        "output-adapter-contract must reference tests/test_output_adapter_v5.py"
    )
    assert 'if [ -f tests/test_output_adapter_v5.py ]; then' in run_cmd, (
        "output-adapter-contract must remain skip-if-missing during support-only setup"
    )


def test_gate_diagnostics_contract_binds_required_test():
    """Phase 4 PR-7 diagnostics gate must pre-bind the future runtime test."""
    workflow = _load_workflow()
    steps = _workflow_steps_by_name(workflow)
    step = steps.get("gate-diagnostics-contract")

    assert step, "gate-diagnostics-contract step missing from workflow"
    run_cmd = str(step.get("run", ""))
    assert "tests/test_gate_diagnostics.py" in run_cmd, (
        "gate-diagnostics-contract must reference tests/test_gate_diagnostics.py"
    )
    assert 'if [ -f tests/test_gate_diagnostics.py ]; then' in run_cmd, (
        "gate-diagnostics-contract must remain skip-if-missing during support-only setup"
    )


def test_advisory_governance_contract_binds_required_tests():
    """Phase 4 PR-8 governance gate must require the canonical governance tests."""
    workflow = _load_workflow()
    steps = _workflow_steps_by_name(workflow)
    step = steps.get("advisory-governance-contract")

    assert step, "advisory-governance-contract step missing from workflow"
    run_cmd = str(step.get("run", ""))
    assert "tests/test_advisory_governance.py" in run_cmd, (
        "advisory-governance-contract must reference tests/test_advisory_governance.py"
    )
    assert "tests/test_lifecycle_fatigue_governance.py" in run_cmd, (
        "advisory-governance-contract must reference tests/test_lifecycle_fatigue_governance.py"
    )
    assert "tests/test_cross_news_crowding_governance.py" in run_cmd, (
        "advisory-governance-contract must reference tests/test_cross_news_crowding_governance.py"
    )
    assert "test -f tests/test_advisory_governance.py" in run_cmd, (
        "advisory-governance-contract must fail fast when tests/test_advisory_governance.py is missing"
    )
    assert "test -f tests/test_lifecycle_fatigue_governance.py" in run_cmd, (
        "advisory-governance-contract must fail fast when tests/test_lifecycle_fatigue_governance.py is missing"
    )
    assert "test -f tests/test_cross_news_crowding_governance.py" in run_cmd, (
        "advisory-governance-contract must fail fast when tests/test_cross_news_crowding_governance.py is missing"
    )

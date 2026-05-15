"""CI workflow step contract tests.

Refs #161 (PR-Audit-4)
"""

import os
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_PATH = os.path.join(REPO_ROOT, ".github", "workflows", "ci.yml")


def _load_workflow():
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _workflow_steps(workflow):
    out = []
    for job_def in workflow.get("jobs", {}).values():
        if not isinstance(job_def, dict):
            continue
        out.extend([s for s in job_def.get("steps", []) if isinstance(s, dict) and s.get("name")])
    return out


def _workflow_steps_by_name(workflow):
    grouped = {}
    for step in _workflow_steps(workflow):
        grouped.setdefault(step["name"], []).append(step)
    return grouped


def _step_names(workflow):
    return [s["name"] for s in _workflow_steps(workflow)]


def _assert_step_exists(steps_by_name, name):
    assert name in steps_by_name, f"{name} step missing from workflow"


def _assert_run_contains(step, text):
    run_cmd = str(step.get("run", ""))
    assert text in run_cmd, f"Expected '{text}' in step '{step.get('name')}'"


def _assert_run_not_contains(step, text):
    run_cmd = str(step.get("run", ""))
    assert text not in run_cmd, f"Did not expect '{text}' in step '{step.get('name')}'"


def _assert_fail_fast_runtime_gate(step):
    _assert_run_not_contains(step, 'echo "[SKIP]')
    _assert_run_not_contains(step, "echo '[SKIP]")
    _assert_run_not_contains(step, "if [ -f")


def test_ci_step_names_are_unique():
    workflow = _load_workflow()
    names = _step_names(workflow)
    dup = sorted({name for name in names if names.count(name) > 1})
    assert not dup, f"Duplicate CI step names found: {dup}"


def test_pipeline_order_contract_step_is_unique():
    workflow = _load_workflow()
    names = _step_names(workflow)
    assert names.count("pipeline-order-contract") == 1, "pipeline-order-contract must exist exactly once"


def test_pipeline_order_contract_binds_required_tests():
    workflow = _load_workflow()
    steps = _workflow_steps_by_name(workflow)
    _assert_step_exists(steps, "pipeline-order-contract")
    step = steps["pipeline-order-contract"][0]
    _assert_run_contains(step, "test -f tests/test_pipeline_order.py")
    _assert_run_contains(step, "test -f tests/test_semantic_prepass_contract.py")
    _assert_run_contains(step, "python -m pytest tests/test_pipeline_order.py tests/test_semantic_prepass_contract.py -q")


def test_pipeline_order_contract_is_not_skip_only():
    workflow = _load_workflow()
    step = _workflow_steps_by_name(workflow)["pipeline-order-contract"][0]
    _assert_fail_fast_runtime_gate(step)


def test_pr_audit_1_runtime_safety_contract_binds_required_test():
    workflow = _load_workflow()
    step = _workflow_steps_by_name(workflow)["pr-audit-1-runtime-safety-contract"][0]
    _assert_run_contains(step, "test -f tests/test_pr_audit_1_runtime_safety.py")
    _assert_run_contains(step, "python -m pytest tests/test_pr_audit_1_runtime_safety.py -q")
    _assert_fail_fast_runtime_gate(step)


def test_pr_audit_2_support_scripts_stability_contract_binds_required_tests():
    workflow = _load_workflow()
    step = _workflow_steps_by_name(workflow)["pr-audit-2-support-scripts-stability-contract"][0]
    _assert_run_contains(step, "test -f tests/test_run_c_module_stack.py")
    _assert_run_contains(step, "test -f tests/test_system_healthcheck.py")
    _assert_run_contains(step, "test -f tests/test_verify_execution_no_pytest.py")
    _assert_run_contains(step, "python -m pytest tests/test_run_c_module_stack.py tests/test_system_healthcheck.py tests/test_verify_execution_no_pytest.py -q")
    _assert_fail_fast_runtime_gate(step)


def test_pr_audit_3_conduction_mapper_correctness_contract_binds_required_test():
    workflow = _load_workflow()
    step = _workflow_steps_by_name(workflow)["pr-audit-3-conduction-mapper-correctness-contract"][0]
    _assert_run_contains(step, "test -f tests/test_pr_audit_3_conduction_mapper_correctness.py")
    _assert_run_contains(step, "python -m pytest tests/test_pr_audit_3_conduction_mapper_correctness.py -q")
    _assert_fail_fast_runtime_gate(step)


def test_completed_runtime_contracts_are_fail_fast():
    workflow = _load_workflow()
    steps = _workflow_steps_by_name(workflow)
    completed = [
        "candidate-envelope-contract",
        "resolver-merge-contract",
        "semantic-full-peer-contract",
        "market-validation-contract",
        "path-adjudicator-lite-contract",
        "semantic-verdict-contract",
        "output-adapter-contract",
        "gate-diagnostics-contract",
        "advisory-governance-contract",
        "pipeline-order-contract",
        "pr-audit-1-runtime-safety-contract",
        "pr-audit-2-support-scripts-stability-contract",
        "pr-audit-3-conduction-mapper-correctness-contract",
    ]
    for name in completed:
        _assert_step_exists(steps, name)
        _assert_fail_fast_runtime_gate(steps[name][0])


def test_compatibility_exit_contract_removed_until_real_surface_exists():
    workflow = _load_workflow()
    steps = _workflow_steps_by_name(workflow)
    assert "compatibility-exit-contract" not in steps, (
        "compatibility-exit-contract is stale skip-only gate; keep it removed until real test surface exists"
    )

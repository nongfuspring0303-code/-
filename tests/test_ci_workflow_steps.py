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

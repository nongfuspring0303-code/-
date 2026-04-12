#!/usr/bin/env python3
"""Tests for EventStateStore."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from state_store import EventStateStore


@pytest.fixture
def store():
    """Create a temporary state store for testing."""
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test_states.db")
    s = EventStateStore(db_path=db_path)
    yield s
    # Cleanup
    try:
        os.remove(db_path)
        os.rmdir(tmp)
    except OSError:
        pass


def test_get_nonexistent(store):
    """Getting state for a new event returns None."""
    assert store.get_state("evt_new_001") is None


def test_upsert_and_retrieve(store):
    """State can be stored and retrieved."""
    store.upsert_state("evt_001", {
        "internal_state": "Detected",
        "lifecycle_state": "Detected",
        "catalyst_state": "first_impulse",
        "retry_count": 0,
    })
    state = store.get_state("evt_001")
    assert state is not None
    assert state["event_id"] == "evt_001"
    assert state["lifecycle_state"] == "Detected"
    assert state["retry_count"] == 0


def test_upsert_updates_existing(store):
    """Upserting updates an existing event's state."""
    store.upsert_state("evt_002", {
        "internal_state": "Detected",
        "lifecycle_state": "Detected",
        "catalyst_state": "first_impulse",
        "retry_count": 0,
    })
    store.upsert_state("evt_002", {
        "internal_state": "Verified",
        "lifecycle_state": "Verified",
        "catalyst_state": "first_impulse",
        "retry_count": 1,
    })
    state = store.get_state("evt_002")
    assert state["internal_state"] == "Verified"
    assert state["lifecycle_state"] == "Verified"
    assert state["retry_count"] == 1


def test_increment_retry(store):
    """Retry count increments correctly."""
    store.upsert_state("evt_003", {
        "internal_state": "Detected",
        "lifecycle_state": "Detected",
        "catalyst_state": "first_impulse",
        "retry_count": 0,
    })
    assert store.increment_retry("evt_003") == 1
    assert store.increment_retry("evt_003") == 2
    state = store.get_state("evt_003")
    assert state["retry_count"] == 2


def test_delete_state(store):
    """State can be deleted."""
    store.upsert_state("evt_004", {
        "internal_state": "Detected",
        "lifecycle_state": "Detected",
        "catalyst_state": "first_impulse",
        "retry_count": 0,
    })
    assert store.delete_state("evt_004") is True
    assert store.get_state("evt_004") is None
    assert store.delete_state("nonexistent") is False


def test_metadata_serialization(store):
    """Metadata is serialized and deserialized as dict."""
    store.upsert_state("evt_005", {
        "internal_state": "Active",
        "lifecycle_state": "Active",
        "catalyst_state": "first_impulse",
        "retry_count": 0,
        "metadata": {"source": "reuters", "category": "C"},
    })
    state = store.get_state("evt_005")
    assert state["metadata"] == {"source": "reuters", "category": "C"}


def test_stateful_progression_scenario(store):
    """Simulates a real event lifecycle progression across multiple runs."""
    event_id = "ME-C-20260412-001.V1.0"

    # Run 1: New event → Detected
    store.upsert_state(event_id, {
        "internal_state": "Detected",
        "lifecycle_state": "Detected",
        "catalyst_state": "first_impulse",
        "retry_count": 0,
    })
    state = store.get_state(event_id)
    assert state["lifecycle_state"] == "Detected"

    # Run 2: Same event, 6h later → Verified
    store.upsert_state(event_id, {
        "internal_state": "Verified",
        "lifecycle_state": "Verified",
        "catalyst_state": "first_impulse",
        "retry_count": 1,
    })
    state = store.get_state(event_id)
    assert state["lifecycle_state"] == "Verified"
    assert state["retry_count"] == 1

    # Run 3: Same event, 30h later → Active
    store.upsert_state(event_id, {
        "internal_state": "Validated",
        "lifecycle_state": "Active",
        "catalyst_state": "first_impulse",
        "retry_count": 2,
    })
    state = store.get_state(event_id)
    assert state["lifecycle_state"] == "Active"
    assert state["internal_state"] == "Validated"

    # Run 4: Same event, 50h later → Exhaustion
    store.upsert_state(event_id, {
        "internal_state": "Monitored",
        "lifecycle_state": "Exhaustion",
        "catalyst_state": "exhaustion",
        "retry_count": 3,
    })
    state = store.get_state(event_id)
    assert state["lifecycle_state"] == "Exhaustion"

"""Shared test fixtures for SeeSee tests."""

import os
import pytest


@pytest.fixture(autouse=True)
def _use_tmp_db(tmp_path, monkeypatch):
    """Use a temporary database for every test."""
    db_path = str(tmp_path / "test_seesee.db")
    monkeypatch.setenv("SEESEE_DB_PATH", db_path)
    monkeypatch.setenv("SEESEE_ADMIN_PASSWORD", "testpassword")

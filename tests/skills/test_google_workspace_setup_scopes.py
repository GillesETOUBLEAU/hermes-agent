"""Scope-drift handling in the Google Workspace OAuth setup script.

A token file records the scopes it was granted, and google-auth replays that
list on every refresh. When the list drifts from what the refresh token really
carries, Google answers ``invalid_scope`` — which used to surface as
REFRESH_FAILED and read like a dead token. These tests pin the recovery.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SETUP_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills/productivity/google-workspace/scripts/setup.py"
)


@pytest.fixture()
def setup_module():
    spec = importlib.util.spec_from_file_location(
        "test_google_workspace_setup_scopes_module",
        SETUP_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Creds:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.refreshed = False

    def refresh(self, _request):
        if self.error is not None:
            raise self.error
        self.refreshed = True


def test_invalid_scope_retries_without_scopes(setup_module, monkeypatch):
    scoped = _Creds(Exception("('invalid_scope: Bad Request', {...})"))
    scopeless = _Creds()
    monkeypatch.setattr(
        setup_module, "_credentials_without_scopes", lambda payload: scopeless
    )

    result = setup_module._refresh_or_realign(scoped, {"scopes": ["a"]})

    assert result is scopeless
    assert scopeless.refreshed


def test_dead_token_is_not_masked_by_the_retry(setup_module, monkeypatch):
    scoped = _Creds(Exception("invalid_scope: Bad Request"))
    scopeless = _Creds(Exception("invalid_grant: Token has been expired or revoked."))
    monkeypatch.setattr(
        setup_module, "_credentials_without_scopes", lambda payload: scopeless
    )

    with pytest.raises(Exception, match="invalid_grant"):
        setup_module._refresh_or_realign(scoped, {"scopes": ["a"]})


def test_other_refresh_errors_propagate_untouched(setup_module, monkeypatch):
    def _never(payload):  # pragma: no cover - must not be reached
        raise AssertionError("fallback attempted for a non-scope error")

    monkeypatch.setattr(setup_module, "_credentials_without_scopes", _never)

    with pytest.raises(Exception, match="disabled_client"):
        setup_module._refresh_or_realign(_Creds(Exception("disabled_client")), {})


class _JsonCreds:
    def __init__(self, payload: dict):
        self._payload = payload

    def to_json(self):
        return json.dumps(self._payload)


def test_scopeless_refresh_keeps_the_recorded_scope_list(setup_module, tmp_path):
    token = tmp_path / "google_token.json"
    setup_module.TOKEN_PATH = token
    previous = {"refresh_token": "r", "scopes": ["https://example.test/drive"]}

    written = setup_module._persist_credentials(
        _JsonCreds({"refresh_token": "r", "token": "new", "scopes": None}), previous
    )

    assert written["scopes"] == previous["scopes"]
    assert json.loads(token.read_text(encoding="utf-8"))["scopes"] == previous["scopes"]
    assert written["type"] == "authorized_user"


def test_no_caller_forces_the_hardcoded_scope_list_onto_a_stored_token():
    source = SETUP_PATH.read_text(encoding="utf-8")
    assert "from_authorized_user_file(str(TOKEN_PATH), SCOPES)" not in source

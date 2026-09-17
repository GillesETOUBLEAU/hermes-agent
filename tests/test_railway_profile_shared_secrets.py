"""Regression guard: Railway named profiles share the container credentials.

Since upstream fdd5995ecb / 5ca670b398 (v0.21.3) a dashboard serving several
profiles (the Desktop app) scopes each NAMED profile's credentials to its own
.env + secret sources. On Railway every key is a service variable (process env),
so ``docker/entrypoint.sh`` dumps them to a tmpfs file and each profile template
enables the ``command`` secret source to read it. Static checks so an upstream
merge that clobbers either side fails in unit CI instead of in the Desktop TUI.
"""

from pathlib import Path

import yaml

from agent.secret_sources.command import _parse_dotenv_map

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = REPO_ROOT / "docker" / "entrypoint.sh"
PROFILES = sorted((REPO_ROOT / "docker" / "profiles").glob("*/config.yaml"))
SECRETS_FILE = "/dev/shm/hermes-shared-secrets.env"


def _dump_snippet() -> str:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index('python3 - "$HERMES_SHARED_SECRETS_FILE" <<\'PY\'')
    body = text[text.index("\n", start) + 1:]
    return body[: body.index("\nPY\n")]


def test_entrypoint_writes_shared_secrets_file() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert f"HERMES_SHARED_SECRETS_FILE={SECRETS_FILE}" in text
    # Must precede the side-ticker and the dashboard, which read it.
    assert text.index("HERMES_SHARED_SECRETS_FILE=") < text.index("Cron ticker for secondary profiles")
    assert text.index("HERMES_SHARED_SECRETS_FILE=") < text.index("Optionally start `hermes dashboard`")


def test_every_profile_template_reads_shared_secrets() -> None:
    assert PROFILES, "no profile templates found"
    for path in PROFILES:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        command = (cfg.get("secrets") or {}).get("command") or {}
        assert command.get("enabled") is True, f"{path}: secrets.command not enabled"
        assert SECRETS_FILE in command.get("command", ""), f"{path}: wrong secrets helper"


def test_dump_round_trips_through_command_parser(tmp_path, monkeypatch) -> None:
    for key in list(__import__("os").environ):
        monkeypatch.delenv(key)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("QUOTED_KEY", 'a"b"c')
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "skip-me")
    monkeypatch.setenv("MULTILINE_KEY", "l1\nl2")
    monkeypatch.setenv("EMPTY_KEY", "")
    out = tmp_path / "shared.env"
    monkeypatch.setattr("sys.argv", ["dump", str(out)])
    exec(compile(_dump_snippet(), "entrypoint-dump", "exec"), {"__name__": "__main__"})

    assert out.stat().st_mode & 0o777 == 0o600
    parsed = _parse_dotenv_map(out.read_text(encoding="utf-8"))
    assert parsed == {"ANTHROPIC_API_KEY": "sk-test", "QUOTED_KEY": 'a"b"c'}

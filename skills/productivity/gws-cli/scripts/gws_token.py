#!/usr/bin/env python3
"""Print a valid Google OAuth access token for the gws CLI, refreshing if needed.

Why this exists: the gws CLI does NOT authenticate from a credentials JSON
handed to GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE. That path is rejected locally
with "Access denied. No credentials provided." before any request reaches
Google — with or without an "authorized_user" `type` field, so the historical
diagnosis (missing `type`) no longer applies. The only working non-interactive
path is GOOGLE_WORKSPACE_CLI_TOKEN, which takes a short-lived access token.

Access tokens expire after ~1h, so the token has to be minted per invocation.
That is what the `gws` shim (gws-wrapper.sh, installed on PATH by
docker/entrypoint.sh) uses this script for.

Refresh and write-back are delegated to the bundled google-workspace skill so
both skills keep sharing a single token file and a single refresh
implementation.

Usage:
  python3 gws_token.py          # prints the access token on stdout
"""
import sys
from pathlib import Path

# The sibling google-workspace skill owns the token file and its refresh logic.
# Both skills live under skills/productivity/, in the install tree and in the
# HERMES_HOME copy alike, so this relative hop holds in both.
_GW_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "google-workspace" / "scripts"


def main() -> int:
    if not _GW_SCRIPTS.is_dir():
        print(
            f"ERROR: google-workspace skill not found at {_GW_SCRIPTS}. "
            "gws shares its OAuth token; install that skill first.",
            file=sys.stderr,
        )
        return 1

    sys.path.insert(0, str(_GW_SCRIPTS))
    try:
        from gws_bridge import get_valid_token
    except ImportError as exc:
        print(f"ERROR: cannot load gws_bridge from {_GW_SCRIPTS}: {exc}", file=sys.stderr)
        return 1

    # get_valid_token() refreshes an expired token and writes it back, or exits
    # non-zero with its own diagnostic when there is no usable token at all.
    print(get_valid_token())
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/bin/sh
# `gws` auth shim — installed on PATH ahead of the real CLI by docker/entrypoint.sh.
#
# The Google Workspace CLI authenticates non-interactively only via
# GOOGLE_WORKSPACE_CLI_TOKEN (a short-lived access token); the
# GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE path is rejected locally with
# "Access denied. No credentials provided." Access tokens live ~1h, so this
# shim mints a fresh one per invocation from the google-workspace skill's
# shared google_token.json, then hands off to the real binary.
#
# Env:
#   GWS_REAL_BIN               absolute path to the real gws (else resolved on PATH)
#   HERMES_GWS_TOKEN_HELPER    path to gws_token.py (else resolved next to this script)
#   GOOGLE_WORKSPACE_CLI_TOKEN if already set, it is honored and no refresh runs

set -e

_self_dir=$(cd "$(dirname "$0")" 2>/dev/null && pwd) || _self_dir=""
_self="$_self_dir/$(basename "$0")"

# --- Resolve the real gws, never this shim (that would recurse forever) ---
_real=""
if [ -n "$GWS_REAL_BIN" ] && [ -x "$GWS_REAL_BIN" ] && [ "$GWS_REAL_BIN" != "$_self" ]; then
    _real="$GWS_REAL_BIN"
else
    _oldifs=$IFS
    IFS=:
    for _d in $PATH; do
        [ -n "$_d" ] || _d=.
        [ -x "$_d/gws" ] || continue
        _cand=$(cd "$_d" 2>/dev/null && pwd)/gws || continue
        [ "$_cand" = "$_self" ] && continue
        _real="$_cand"
        break
    done
    IFS=$_oldifs
fi

if [ -z "$_real" ]; then
    echo "gws: the Google Workspace CLI is not installed (npm install -g @googleworkspace/cli)" >&2
    exit 127
fi

# --- Mint an access token, unless one was supplied ---
if [ -z "$GOOGLE_WORKSPACE_CLI_TOKEN" ]; then
    _helper="${HERMES_GWS_TOKEN_HELPER:-$_self_dir/gws_token.py}"
    if [ -f "$_helper" ]; then
        # A failure here is not fatal: `gws --help`, `gws schema ...` and other
        # offline subcommands stay usable, and the real CLI reports the auth
        # error itself for calls that do need credentials.
        if _token=$(python3 "$_helper" 2>/dev/null) && [ -n "$_token" ]; then
            GOOGLE_WORKSPACE_CLI_TOKEN="$_token"
            export GOOGLE_WORKSPACE_CLI_TOKEN
        fi
    fi
fi

exec "$_real" "$@"

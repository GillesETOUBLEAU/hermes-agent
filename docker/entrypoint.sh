#!/bin/bash
# Docker entrypoint: bootstrap config files into the mounted volume, then run hermes.
set -e

HERMES_HOME="/opt/data"
INSTALL_DIR="/opt/hermes"

# Create essential directory structure.  Cache and platform directories
# (cache/images, cache/audio, platforms/whatsapp, etc.) are created on
# demand by the application — don't pre-create them here so new installs
# get the consolidated layout from get_hermes_dir().
mkdir -p "$HERMES_HOME"/{cron,sessions,logs,hooks,memories,skills}

# .env — on Railway, use an empty .env so Railway-injected env vars are not
# overwritten by stale values from .env.example (load_dotenv override=True).
if [ -n "$RAILWAY_ENVIRONMENT" ]; then
    : > "$HERMES_HOME/.env"
elif [ ! -f "$HERMES_HOME/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$HERMES_HOME/.env"
fi

# config.yaml — on Railway, always use the Railway-optimized config
if [ -n "$RAILWAY_ENVIRONMENT" ] && [ -f "$INSTALL_DIR/docker/railway-config.yaml" ]; then
    cp "$INSTALL_DIR/docker/railway-config.yaml" "$HERMES_HOME/config.yaml"
elif [ ! -f "$HERMES_HOME/config.yaml" ]; then
    cp "$INSTALL_DIR/cli-config.yaml.example" "$HERMES_HOME/config.yaml"
fi

# SOUL.md
if [ ! -f "$HERMES_HOME/SOUL.md" ]; then
    cp "$INSTALL_DIR/docker/SOUL.md" "$HERMES_HOME/SOUL.md"
fi

# Sync bundled skills (manifest-based so user edits are preserved)
if [ -d "$INSTALL_DIR/skills" ]; then
    python3 "$INSTALL_DIR/tools/skills_sync.py"
fi

# Google OAuth — decode base64 credentials from env vars into files.
# Set GOOGLE_TOKEN_B64 and GOOGLE_CLIENT_SECRET_B64 in Railway dashboard.
# Generate them locally with:
#   cat ~/.hermes/google_token.json | base64 | tr -d '\n'
#   cat ~/.hermes/google_client_secret.json | base64 | tr -d '\n'
if [ -n "$GOOGLE_TOKEN_B64" ] && [ ! -f "$HERMES_HOME/google_token.json" ]; then
    echo "$GOOGLE_TOKEN_B64" | base64 -d > "$HERMES_HOME/google_token.json"
    echo "[entrypoint] Google OAuth: decoded token from GOOGLE_TOKEN_B64"
fi
if [ -n "$GOOGLE_CLIENT_SECRET_B64" ] && [ ! -f "$HERMES_HOME/google_client_secret.json" ]; then
    echo "$GOOGLE_CLIENT_SECRET_B64" | base64 -d > "$HERMES_HOME/google_client_secret.json"
    echo "[entrypoint] Google OAuth: decoded client secret from GOOGLE_CLIENT_SECRET_B64"
fi

# gws CLI — set up config directory and bridge credentials if available
GWS_CONFIG_DIR="$HERMES_HOME/gws-config"
mkdir -p "$GWS_CONFIG_DIR"
export GOOGLE_WORKSPACE_CLI_CONFIG_DIR="$GWS_CONFIG_DIR"

# If gws credentials file is set via env var, use it directly
if [ -n "$GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE" ]; then
    echo "[entrypoint] gws CLI: using credentials from GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE"
# Otherwise, bridge from existing google-workspace Python skill token
elif [ -f "$HERMES_HOME/google_token.json" ]; then
    BRIDGE_SCRIPT="$INSTALL_DIR/skills/productivity/gws-cli/scripts/bridge_auth.py"
    if [ -f "$BRIDGE_SCRIPT" ]; then
        python3 "$BRIDGE_SCRIPT" --bridge 2>/dev/null && \
            export GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE="$GWS_CONFIG_DIR/credentials.json" && \
            echo "[entrypoint] gws CLI: bridged credentials from google-workspace skill"
    fi
fi

# Debug: verify env vars are visible
echo "[entrypoint] DISCORD_ALLOWED_USERS=${DISCORD_ALLOWED_USERS:-EMPTY}"
echo "[entrypoint] DISCORD_ALLOW_ALL_USERS=${DISCORD_ALLOW_ALL_USERS:-EMPTY}"
echo "[entrypoint] ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:+set}"
echo "[entrypoint] .env contents:"
cat "$HERMES_HOME/.env"
echo "[entrypoint] --- end .env ---"

exec hermes "$@"

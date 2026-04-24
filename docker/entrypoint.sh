#!/bin/bash
# Docker/Podman entrypoint: bootstrap config files into the mounted volume, then run hermes.
set -e

HERMES_HOME="${HERMES_HOME:-/opt/data}"
INSTALL_DIR="/opt/hermes"

# --- Privilege dropping via gosu ---
# When started as root (the default for Docker, or fakeroot in rootless Podman),
# optionally remap the hermes user/group to match host-side ownership, fix volume
# permissions, then re-exec as hermes.
if [ "$(id -u)" = "0" ]; then
    if [ -n "$HERMES_UID" ] && [ "$HERMES_UID" != "$(id -u hermes)" ]; then
        echo "Changing hermes UID to $HERMES_UID"
        usermod -u "$HERMES_UID" hermes
    fi

    if [ -n "$HERMES_GID" ] && [ "$HERMES_GID" != "$(id -g hermes)" ]; then
        echo "Changing hermes GID to $HERMES_GID"
        # -o allows non-unique GID (e.g. macOS GID 20 "staff" may already exist
        # as "dialout" in the Debian-based container image)
        groupmod -o -g "$HERMES_GID" hermes 2>/dev/null || true
    fi

    # Fix ownership of the data volume. When HERMES_UID remaps the hermes user,
    # files created by previous runs (under the old UID) become inaccessible.
    # Always chown -R when UID was remapped; otherwise only if top-level is wrong.
    actual_hermes_uid=$(id -u hermes)
    needs_chown=false
    if [ -n "$HERMES_UID" ] && [ "$HERMES_UID" != "10000" ]; then
        needs_chown=true
    elif [ "$(stat -c %u "$HERMES_HOME" 2>/dev/null)" != "$actual_hermes_uid" ]; then
        needs_chown=true
    fi
    if [ "$needs_chown" = true ]; then
        echo "Fixing ownership of $HERMES_HOME to hermes ($actual_hermes_uid)"
        # In rootless Podman the container's "root" is mapped to an unprivileged
        # host UID — chown will fail.  That's fine: the volume is already owned
        # by the mapped user on the host side.
        chown -R hermes:hermes "$HERMES_HOME" 2>/dev/null || \
            echo "Warning: chown failed (rootless container?) — continuing anyway"
    fi

    echo "Dropping root privileges"
    exec gosu hermes "$0" "$@"
fi

# --- Running as hermes from here ---
source "${INSTALL_DIR}/.venv/bin/activate"

# Create essential directory structure.  Cache and platform directories
# (cache/images, cache/audio, platforms/whatsapp, etc.) are created on
# demand by the application — don't pre-create them here so new installs
# get the consolidated layout from get_hermes_dir().
# The "home/" subdirectory is a per-profile HOME for subprocesses (git,
# ssh, gh, npm …).  Without it those tools write to /root which is
# ephemeral and shared across profiles.  See issue #4426.
mkdir -p "$HERMES_HOME"/{cron,sessions,logs,hooks,memories,skills,skins,plans,workspace,home}

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

# Ensure the main config file remains accessible to the hermes runtime user
# even if it was edited on the host after initial ownership setup.
if [ -f "$HERMES_HOME/config.yaml" ]; then
    chown hermes:hermes "$HERMES_HOME/config.yaml"
    chmod 640 "$HERMES_HOME/config.yaml"
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
# Always overwrite so Railway env var updates take effect on redeploy.
# Set GOOGLE_TOKEN_B64 and GOOGLE_CLIENT_SECRET_B64 in Railway dashboard.
# Generate locally with:
#   cat ~/.hermes/google_token.json | base64 | tr -d '\n'
#   cat ~/.hermes/google_client_secret.json | base64 | tr -d '\n'
if [ -n "$GOOGLE_TOKEN_B64" ]; then
    echo "$GOOGLE_TOKEN_B64" | base64 -d > "$HERMES_HOME/google_token.json"
    echo "[entrypoint] Google OAuth: decoded token → $HERMES_HOME/google_token.json"
fi
if [ -n "$GOOGLE_CLIENT_SECRET_B64" ]; then
    echo "$GOOGLE_CLIENT_SECRET_B64" | base64 -d > "$HERMES_HOME/google_client_secret.json"
    echo "[entrypoint] Google OAuth: decoded client secret → $HERMES_HOME/google_client_secret.json"
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

# Debug: verify Google OAuth files exist
echo "[entrypoint] google_token.json: $([ -f "$HERMES_HOME/google_token.json" ] && echo "EXISTS ($(wc -c < "$HERMES_HOME/google_token.json") bytes)" || echo "MISSING")"
echo "[entrypoint] google_client_secret.json: $([ -f "$HERMES_HOME/google_client_secret.json" ] && echo "EXISTS" || echo "MISSING")"

# Debug: verify env vars are visible
echo "[entrypoint] DISCORD_ALLOWED_USERS=${DISCORD_ALLOWED_USERS:-EMPTY}"
echo "[entrypoint] DISCORD_ALLOW_ALL_USERS=${DISCORD_ALLOW_ALL_USERS:-EMPTY}"
echo "[entrypoint] ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:+set}"
echo "[entrypoint] .env contents:"
cat "$HERMES_HOME/.env"
echo "[entrypoint] --- end .env ---"

# Final exec: two supported invocation patterns.
#
#   docker run <image>                 -> exec `hermes` with no args (legacy default)
#   docker run <image> chat -q "..."   -> exec `hermes chat -q "..."` (legacy wrap)
#   docker run <image> sleep infinity  -> exec `sleep infinity` directly
#   docker run <image> bash            -> exec `bash` directly
#
# If the first positional arg resolves to an executable on PATH, we assume the
# caller wants to run it directly (needed by the launcher which runs long-lived
# `sleep infinity` sandbox containers — see tools/environments/docker.py).
# Otherwise we treat the args as a hermes subcommand and wrap with `hermes`,
# preserving the documented `docker run <image> <subcommand>` behavior.
if [ $# -gt 0 ] && command -v "$1" >/dev/null 2>&1; then
    exec "$@"
fi
exec hermes "$@"

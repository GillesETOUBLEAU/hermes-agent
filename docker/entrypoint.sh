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

# Debug: verify env vars are visible
echo "[entrypoint] DISCORD_ALLOWED_USERS=${DISCORD_ALLOWED_USERS:-EMPTY}"
echo "[entrypoint] DISCORD_ALLOW_ALL_USERS=${DISCORD_ALLOW_ALL_USERS:-EMPTY}"
echo "[entrypoint] ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:+set}"
echo "[entrypoint] .env contents:"
cat "$HERMES_HOME/.env"
echo "[entrypoint] --- end .env ---"

exec hermes "$@"

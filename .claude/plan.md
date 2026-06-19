# Hermes Agent + Google Workspace CLI — Implementation Plan

## Overview

Deploy **Hermes Agent** (Nous Research) on **Railway** with **Google Workspace CLI (`gws`)** integration, using PippaBot's existing OAuth credentials (`pippaetoubleau@gmail.com` / project `pippaclawd`).

**Goal**: An autonomous agent that can manage Gmail, Calendar, Drive, Docs, Sheets — both interactively (via gateway: Telegram/Discord) and via scheduled automations (cron).

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  Railway (Docker Container)                  │
│                                              │
│  ┌──────────────┐   ┌────────────────────┐  │
│  │ Hermes Agent │──▶│ gws CLI (binary)   │  │
│  │  (Python)    │   │ Gmail/Cal/Drive/   │  │
│  │              │   │ Docs/Sheets        │  │
│  └──────┬───────┘   └────────────────────┘  │
│         │                                    │
│  ┌──────┴───────┐   ┌────────────────────┐  │
│  │   Gateway    │   │  Cron Scheduler    │  │
│  │ Telegram/    │   │ Daily digests,     │  │
│  │ Discord/CLI  │   │ email triage, etc. │  │
│  └──────────────┘   └────────────────────┘  │
│                                              │
│  /opt/data/ (Railway Persistent Volume)      │
│  ├── gws-config/   (OAuth credentials)       │
│  ├── memories/     (agent memory)            │
│  ├── skills/       (custom skills)           │
│  └── cron/         (scheduled jobs)          │
└─────────────────────────────────────────────┘
```

---

## Step-by-Step Plan

### Phase 1: Repository Setup

- [ ] **1.1** Clone Hermes Agent into `Hermes/` directory
  ```bash
  git clone https://github.com/NousResearch/hermes-agent.git .
  ```
- [ ] **1.2** Create `.env` from `.env.example` with model config (OpenRouter or local)
- [ ] **1.3** Create `config.yaml` from template
- [ ] **1.4** Verify Hermes runs locally: `hermes -q "Hello"`

### Phase 2: Install gws CLI

- [ ] **2.1** Add gws binary installation to Dockerfile
  ```dockerfile
  # Install gws CLI via npm
  RUN npm install -g @googleworkspace/cli
  ```
- [ ] **2.2** Verify gws is accessible: `gws --version`

### Phase 3: OAuth Authentication Setup

Using PippaBot's existing OAuth credentials (`pippaclawd` project).

- [ ] **3.1** Convert PippaBot's `client_secret` to gws format
  - gws expects `client_secret.json` at `~/.config/gws/` (or `$GOOGLE_WORKSPACE_CLI_CONFIG_DIR`)
  - PippaBot's credential is `"installed"` type — compatible with gws OAuth flow
- [ ] **3.2** Run `gws auth login` locally (one-time interactive OAuth)
  - Place `client_secret_*.json` → `~/.config/gws/client_secret.json`
  - Run `gws auth login` → browser OAuth → select scopes (Gmail, Calendar, Drive, Docs, Sheets)
  - This creates encrypted credentials at `~/.config/gws/credentials.json`
- [ ] **3.3** Export credentials for headless/Railway use
  ```bash
  gws auth export --unmasked > hermes-gws-credentials.json
  ```
- [ ] **3.4** Store exported credentials as Railway environment variable or volume mount
  - Option A: `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=/opt/data/gws-config/credentials.json`
  - Option B: Mount the file into the persistent volume

### Phase 4: Create gws Skill for Hermes

- [ ] **4.1** Create skill directory structure:
  ```
  skills/productivity/gws-workspace/
  ├── SKILL.md              # Main skill instructions
  ├── scripts/
  │   └── verify-auth.sh    # Auth verification helper
  └── references/
      └── gws-commands.md   # Quick reference for gws commands
  ```
- [ ] **4.2** Write `SKILL.md` with:
  - gws CLI usage patterns for Gmail, Calendar, Drive, Docs, Sheets
  - Helper commands (`+send`, `+triage`, `+agenda`, `+upload`, etc.)
  - JSON output parsing guidance
  - Error handling patterns
- [ ] **4.3** Write `gws-commands.md` reference doc with common operations
- [ ] **4.4** Test skill locally: ask Hermes to list Gmail or check calendar

### Phase 5: Docker Configuration

- [ ] **5.1** Modify Dockerfile to include gws CLI:
  ```dockerfile
  # After existing npm install
  RUN npm install -g @googleworkspace/cli
  ```
- [ ] **5.2** Update `docker/entrypoint.sh` to:
  - Create `gws-config/` directory in `$HERMES_HOME`
  - Set `GOOGLE_WORKSPACE_CLI_CONFIG_DIR=$HERMES_HOME/gws-config`
  - Copy skill into bundled skills if not already synced
- [ ] **5.3** Add environment variables to Docker compose:
  ```yaml
  environment:
    GOOGLE_WORKSPACE_CLI_CONFIG_DIR: /opt/data/gws-config
    GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE: /opt/data/gws-config/credentials.json
  ```
- [ ] **5.4** Test Docker build and run locally

### Phase 6: Railway Deployment

- [ ] **6.1** Create Railway project and link repo
- [ ] **6.2** Configure Railway environment variables:
  - `OPENROUTER_API_KEY` (or model provider key)
  - `GOOGLE_WORKSPACE_CLI_CONFIG_DIR=/opt/data/gws-config`
  - `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=/opt/data/gws-config/credentials.json`
  - Gateway tokens (Telegram/Discord if used)
- [ ] **6.3** Add Railway persistent volume mounted at `/opt/data`
- [ ] **6.4** Upload gws credentials to the persistent volume (one-time setup)
- [ ] **6.5** Deploy and verify gateway starts
- [ ] **6.6** Test gws commands via gateway (send a test message through Telegram/Discord)

### Phase 7: Cron Automations

- [ ] **7.1** Configure automated tasks via Hermes cron:
  - **Morning briefing** (8h CET): Calendar agenda + unread Gmail summary
  - **Email triage** (every 2h): Categorize and summarize new emails
  - **Weekly digest** (Monday 9h): Week summary across Workspace
- [ ] **7.2** Set delivery target (Telegram chat ID or Discord channel)
- [ ] **7.3** Test cron execution end-to-end

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `Dockerfile` | Modify | Add `npm install -g @googleworkspace/cli` |
| `docker/entrypoint.sh` | Modify | Add gws config directory setup |
| `skills/productivity/gws-workspace/SKILL.md` | Create | Main skill file |
| `skills/productivity/gws-workspace/scripts/verify-auth.sh` | Create | Auth check script |
| `skills/productivity/gws-workspace/references/gws-commands.md` | Create | Command reference |
| `.env` | Modify | Add gws-related env vars |
| `railway.json` | Create | Railway deployment config |
| `docker-compose.yml` | Create (optional) | Local dev with Docker |

---

## Security Notes

- PippaBot OAuth client secret and exported gws credentials must NEVER be committed to git
- All secrets go in Railway env vars or mounted volume
- The `.gitignore` must include `*credentials*`, `*token*`, `*secret*`, `*.json` credential files
- gws encrypts stored credentials with AES-256-GCM

---

## Key Decisions

1. **Skill (not Tool)** — gws integrates as a Hermes Skill (SKILL.md + terminal), not a custom Python tool. The gws CLI already outputs structured JSON, making it perfect for skill-based usage via the terminal tool.

2. **OAuth export flow** — We do the interactive OAuth locally once, then export credentials for headless Railway deployment.

3. **PippaBot credentials reuse** — The `pippaclawd` project already has Gmail/Calendar/Drive/Docs/Sheets APIs enabled with the right scopes. No new GCP project needed.

4. **Railway persistent volume** — Required for agent memory, skills, and gws credentials to survive container restarts.

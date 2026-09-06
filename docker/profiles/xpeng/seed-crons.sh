#!/bin/sh
# Seed the xpeng profile's cron jobs on the Railway volume — idempotent (skips a job whose
# name already exists). Cron jobs live on the volume and survive redeploys; they are ticked
# by the entrypoint side-ticker (`hermes -p xpeng cron tick`, cf. #69377).
#
# Run once after the first deploy that ships the profile, as the hermes user:
#   railway ssh sh -c 'su hermes -s /bin/sh -c "sh /opt/hermes/docker/profiles/xpeng/seed-crons.sh"'
# Times are in HERMES_TIMEZONE (Europe/Paris on Railway).
set -eu
H=/opt/hermes/.venv/bin/hermes
DELIVER="discord:1545105470002303016"   # #cron (Pippa server) — numeric id only

have() { $H -p xpeng cron list --all 2>/dev/null | grep -Fq "Name:      $1"; }

if have "xpeng-inbox-triage"; then
    echo "[seed] xpeng-inbox-triage already exists"
else
    $H -p xpeng cron create "*/30 7-21 * * *" \
        "Inbox triage run of the TTT Global Training registration desk. Load the skill xpeng-registration-desk and follow section 1 (Inbox triage run) end to end: pull the wiki, list unseen mail, classify, answer what the sources cover, acknowledge declines and requests, escalate the rest to the logistics team in ONE message, journal, push the wiki. Output in English, under 25 lines: the triage summary line then the escalation list if any. If there is no new mail, output exactly: No new mail." \
        --name "xpeng-inbox-triage" --deliver "$DELIVER" \
        --skill xpeng-registration-desk --skill xpeng-mailbox
fi

if have "xpeng-facts-refresh"; then
    echo "[seed] xpeng-facts-refresh already exists"
else
    $H -p xpeng cron create "0 7 * * *" \
        "Daily facts refresh of the TTT Global Training registration desk. Load the skill xpeng-registration-desk and follow section 3 (Daily facts refresh): re-read src/config/event.ts and src/content/en.ts from the GitHub repo WMH-Project/Xpeng-Global-Training (MCP github), app_settings from Supabase, the Drive folder if XPENG_DRIVE_FOLDER_ID is set, and align /opt/data/wiki/xpeng/facts.md verbatim with the site. Commit and push the wiki. Output in English: 'Facts refresh: no change' or the list of changed facts." \
        --name "xpeng-facts-refresh" --deliver "$DELIVER" \
        --skill xpeng-registration-desk
fi

$H -p xpeng cron list

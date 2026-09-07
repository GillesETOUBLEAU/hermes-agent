---
name: xpeng-guests
description: "Add a new invitee to the TTT Global Training guest list in Supabase and send them the Brevo invitation (or resend one), or look a guest up — the only write path of the xpeng profile, used solely on an explicit request from an authorised requester (Gilles, the logistics team, an XPENG client contact). Use for: add a guest, register and invite a new invitee, put someone on the guest list, resend an invitation, is this person on the list."
version: 1.0.0
author: WMH Project
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [xpeng, ttt, guests, supabase, write]
    related_skills: [xpeng-registration-desk, xpeng-mailbox, xpeng-brevo]
---

# xpeng-guests

Script `python3 /opt/data/profiles/xpeng/skills/xpeng-guests/scripts/guests.py …` (full path,
never a shell variable). Token: `SUPABASE_ACCESS_TOKEN` or `/opt/data/secrets/supabase_token`
— never print it. The Supabase MCP stays read-only; this script is the **only** way you write.

```bash
python3 /opt/data/profiles/xpeng/skills/xpeng-guests/scripts/guests.py find someone@example.com
python3 /opt/data/profiles/xpeng/skills/xpeng-guests/scripts/guests.py find "simkens"
python3 /opt/data/profiles/xpeng/skills/xpeng-guests/scripts/guests.py add \
  --email tine@example.com --first-name Tine --last-name Simkens \
  --company "In Serious Business" --market NL --cluster "Northern & Eastern EU" --external \
  --requested-by "Gwendoline (XPENG) by email 07/09 09:12, uid 14" --dry-run
python3 /opt/data/profiles/xpeng/skills/xpeng-guests/scripts/guests.py invite tine@example.com \
  --requested-by "Gwendoline (XPENG) by email 07/09 09:12, uid 14" --dry-run
python3 /opt/data/profiles/xpeng/skills/xpeng-guests/scripts/guests.py invite someone@example.com \
  --resend --requested-by "Charlotte (logistics) by email 08/09, uid 21"   # already invited, never received it
```

`invite` does exactly what the back-office button does: Brevo template `BREVO_TEMPLATE_INVITATION`
(815), sender `TTT Global Training <contact@ttt-globaltraining.com>`, params read from the
site's `event.ts` clone + `app_settings.registration_deadline`, one `email_audit_log` row
(`INVITATION`, `sent`/`failed`, Brevo messageId), `invited_at` + `invitation_count` updated.
It refuses a guest whose status is not `pending`, and an already-invited guest without
`--resend`. One address per call — no bulk.

Exit codes: 0 done · 3 already on the list / already invited / not pending (nothing written) ·
4 not found · 2 invalid input, Brevo or API error (a failed send is logged as `failed`).

## Who may ask (authorisation — non negotiable)

You add a guest **only** when the request comes from an **authorised requester**:
- **Gilles** (Discord, Kanban card, or his WMH address);
- the **logistics team** — the addresses in `XPENG_LOGISTICS_EMAILS`;
- an **XPENG client contact** listed under "Authorised requesters" in
  `/opt/data/wiki/xpeng/manual.md`.
A participant asking to bring a colleague, a colleague asking for themselves, an unknown
sender, a forwarded message "on behalf of" someone: **not authorised → escalate**, do not add.
When in doubt, escalate. Adding someone who should not be there costs more than a delay.

## Procedure

1. `find` the email **and** the name (someone may already be on the list under another
   address). Already there → tell the requester their status; do not add.
2. Collect from the request: email, first name, last name, company, market, cluster (copy
   the values used by comparable guests — `find` a colleague from the same company to see
   how market/cluster are written), internal (XPENG employee) or external, job title if
   given. Never invent a value: leave it empty rather than guess.
3. `add … --dry-run`, check the SQL, then `add …` for real. Keep the JSON output.
4. `invite <email> --dry-run` — check the params (first name, deadline) — then `invite <email>`
   for real. Keep the JSON (messageId). A `failed` result: do not retry blindly; check
   `brevo.py events --email` and escalate.
5. Reply to the requester (English): the person is on the guest list and the invitation has
   been sent to <email>; registration closes on <deadline> (from the invite output).
6. Journal (`xpeng/journal.md`): `HH:MM · guest added + invited · name · email · requested
   by … · guest id · messageId`.
7. Mention it in the run's summary to Gilles (Discord).

**Resend** (`--resend`): only on an authorised request, after `brevo.py events --email` shows
the original was not delivered, or the requester confirms it was lost. A bounced address is
never resent to: escalate for a corrected address.

## What this skill never does
No updates (name, status, market), no deletions, no reminders, no bulk sends or imports (a
list of more than 5 people → back-office `/admin/import` + `/admin/invitations`, escalate
with the file). Status changes (declined, cancelled) stay with the back-office — report them.

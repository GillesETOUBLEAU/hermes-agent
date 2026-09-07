---
name: xpeng-guests
description: "Add a new invitee to the TTT Global Training guest list in Supabase (status pending, no invitation sent) or look one up — the only write path of the xpeng profile, used solely on an explicit request from an authorised requester (Gilles, the logistics team, an XPENG client contact). Use for: add a guest, register a new invitee, put someone on the guest list, is this person on the list."
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
```

Exit codes: 0 written/found · 3 email already on the list (row printed, nothing written) ·
4 `find` found nothing · 2 invalid input or API error.

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
4. Reply to the requester (English): the person is now on the guest list; **the invitation
   email is not sent by you** — the back-office sends it from `/admin/invitations` (say who
   should do it: Gilles/logistics); registration closes at the deadline (facts sheet).
5. Journal (`xpeng/journal.md`): `HH:MM · guest added · name · email · requested by … · id`.
6. Mention it in the run's escalation/summary to Gilles (Discord) so the invitation goes out.

## What this skill never does
No updates (name, status, market), no deletions, no invitations, no bulk imports (a list of
more than 5 people → back-office `/admin/import`, escalate with the file). Status changes
(declined, cancelled) stay with the back-office — report them.

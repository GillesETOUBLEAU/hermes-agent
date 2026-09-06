---
name: xpeng-brevo
description: "Brevo transactional email account of TTT Global Training (XPENG): list templates, check delivery events for a recipient (delivered, bounced, blocked, opened), list blocked contacts, resend a templated email (Confirmation, Invitation). Use for: 'did X receive the invitation', bounce check, resend the confirmation email, Brevo template ids."
version: 1.0.0
author: WMH Project
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [brevo, email, deliverability, xpeng, ttt]
    related_skills: [xpeng-registration-desk, xpeng-mailbox]
---

# xpeng-brevo

Script `python3 /opt/data/profiles/xpeng/skills/xpeng-brevo/scripts/brevo.py` (always the
full path; a command starting with a shell variable is rejected by the scanner) — key
from `BREVO_API_KEY` (Railway var; never print it).

```bash
python3 /opt/data/profiles/xpeng/skills/xpeng-brevo/scripts/brevo.py templates                               # ids: 815 Invitation · 816 Registration confirmed
python3 /opt/data/profiles/xpeng/skills/xpeng-brevo/scripts/brevo.py events --email someone@example.com      # what Brevo did with that address (30 days)
python3 /opt/data/profiles/xpeng/skills/xpeng-brevo/scripts/brevo.py events --days 7 --event hardBounces     # account-wide bounces of the week
python3 /opt/data/profiles/xpeng/skills/xpeng-brevo/scripts/brevo.py blocked                                 # hard-bounced / unsubscribed addresses
python3 /opt/data/profiles/xpeng/skills/xpeng-brevo/scripts/brevo.py send-template --template-id 816 --to a@b.c --params '{"firstName":"…", …}' --dry-run
```

## When to use what

- **"I never received the invitation / confirmation"** → `events --email` first. `delivered`
  = it's in their mailbox (spam folder?). `hardBounces`/`blocked` = wrong address → tell
  logistics, do not resend. No event at all = the site never sent it → check
  `email_audit_log` in Supabase (read-only MCP) and escalate.
- **Resend** a confirmation only when the registration exists in Supabase and the
  original is proven delivered-but-lost; params must be complete — the template
  variables are typed in the site repo `src/lib/email/types.ts` (`summaryHtml`,
  `hotelNoticeHtml`, `deadline`, …). If you cannot build them faithfully, ask the
  back-office (Gilles) to resend from `/admin/guests` instead: that path logs the send.
- Invitations (815) are sent by the back-office in bulk — **never** send invitations
  yourself; an unknown person asking for one is escalated.

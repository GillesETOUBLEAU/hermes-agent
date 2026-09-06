---
name: xpeng-mailbox
description: "Operate the TTT Global Training organisation inbox (contact@ttt-globaltraining.com) over IMAP/SMTP: list unread mail, read a message, reply in-thread, send, flag, move. Use for: check the XPENG inbox, answer a participant, reply to a guest, send to logistics, mark as answered, 'what's new in the TTT mailbox'."
version: 1.0.0
author: WMH Project
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [email, imap, smtp, xpeng, ttt, inbox]
    related_skills: [xpeng-registration-desk, xpeng-brevo]
---

# xpeng-mailbox

One script, standard library only:
`python3 ~/skills/xpeng-mailbox/scripts/mailbox.py <command>` — on Railway the skill
lives at `/opt/data/profiles/xpeng/skills/xpeng-mailbox/scripts/mailbox.py`. Define
`MB="python3 /opt/data/profiles/xpeng/skills/xpeng-mailbox/scripts/mailbox.py"` first.

Credentials come from the environment (`XPENG_MAIL_USER`, `XPENG_MAIL_PASSWORD`) or,
by default, from the base64 file `/opt/data/secrets/ttt_imap_pass_b64` that the
default profile's daily report already uses. **Never print, echo or paste a password.**
Set `XPENG_MAIL_DRY_RUN=1` to see what would be sent without sending.

## Commands

```bash
$MB folders                                   # IMAP folders (INBOX, Sent, …)
$MB list --unseen                             # unread INBOX messages (uid, date, from, subject)
$MB list --days 2 --json                      # last 2 days, machine-readable
$MB search --from "@xiaopeng.com" --days 30   # filters: --from --subject --text --since --unseen
$MB read <uid>                                # headers + text body (+ attachment names)
$MB read <uid> --json                         # same, JSON (fields: from, subject, body, auto_submitted…)
$MB reply <uid> --body-file /opt/data/tmp/reply.txt [--all] [--quote] [--cc a@b.c] [--draft]
$MB send --to a@b.c[,d@e.f] --subject "…" --body-file /opt/data/tmp/mail.txt [--html-file …]
$MB flag <uid> [<uid>…] --flags seen answered # or --remove
$MB move <uid> --to "Archive"                 # copy + delete + expunge
```

`--draft` (on `reply` and `send`) stores the message in the webmail Drafts folder instead of
sending it — for a human to review and send; the original is then NOT flagged, flag it yourself.
`reply` threads correctly (In-Reply-To/References), addresses the sender's Reply-To
(or From), prefixes `Re:`, copies the message to the Sent folder, then flags the
original **Seen + Answered** (unless `--no-mark`). Output of any send is one JSON line
with the Message-ID — quote it in the journal.

## Rules

- Write the body to a file first (`/opt/data/tmp/…`, `/tmp` is protected), re-read it,
  then send. Plain text, English, signed "TTT Global Training – Organisation team".
- Reply only from `contact@ttt-globaltraining.com`; never impersonate a person.
- A message is *processed* when it is flagged Seen (+ Answered if a reply went out).
  The triage routine relies on `list --unseen`: do not mark Seen anything you skipped.
- Auto-replies: `read --json` exposes `auto_submitted`; a value other than empty/`no`
  (or a subject starting "Automatic reply"/"Out of office"/"Undeliverable") is never
  answered.
- Before re-sending after an error, check the Sent folder (`$MB --folder Sent list --days 1`):
  SMTP may have succeeded while the Sent copy failed.

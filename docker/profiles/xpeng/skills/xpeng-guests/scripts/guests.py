#!/usr/bin/env python3
"""Guest-list writer for the TTT Global Training desk (Supabase project xpeng-ttt-training).

The ONLY write path of the xpeng profile. It does exactly three things:
  find   <email | name fragment>          read guests matching (email, first/last name)
  add    --email … --first-name … --last-name … [--company --market --cluster --job-title]
         [--internal] [--requested-by "who asked, how"] [--dry-run]
         insert ONE guest with status 'pending'. If the email already exists, nothing is
         written and the existing row is printed (exit 3). Never updates, never deletes.
  invite <email> [--resend] --requested-by … [--dry-run]
         send the Brevo invitation (template BREVO_TEMPLATE_INVITATION, default 815) to ONE
         guest exactly like the back-office does: same params (built from the site's
         event.ts clone + app_settings.registration_deadline), same email_audit_log row,
         invited_at / invitation_count updated. Refuses a guest who is not 'pending' or who
         was already invited unless --resend.

Transport: Supabase Management API (POST /v1/projects/<ref>/database/query), token from
SUPABASE_ACCESS_TOKEN or the volume file /opt/data/secrets/supabase_token (base64 or raw) —
the same path the daily report uses. Runs as the postgres role, so the guests_audit trigger
records actor_role = 'postgres'; the journal (wiki) carries who asked.
Values are validated and dollar-quoted with a random tag: no interpolation of raw input.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

REF = os.environ.get("XPENG_SUPABASE_REF", "daxqygwolwqciusyprvo")
API = f"https://api.supabase.com/v1/projects/{REF}/database/query"
SITE_CLONE = os.environ.get("XPENG_SITE_CLONE", "/opt/data/workspace/xpeng-site")
BREVO_SEND = "https://api.brevo.com/v3/smtp/email"
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
FIELDS = "id, first_name, last_name, email, company, market, cluster, job_title, is_internal, status, invited_at, invitation_count, registered_at, declined_at, created_at"


def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def token() -> str:
    tok = os.environ.get("SUPABASE_ACCESS_TOKEN", "").strip()
    if tok:
        return tok
    for p in ("/opt/data/secrets/supabase_token", "/opt/data/secrets/supabase_access_token"):
        if os.path.isfile(p):
            raw = open(p, "rb").read().strip()
            try:
                dec = base64.b64decode(raw, validate=True).decode()
                if dec.startswith(("sbp_", "eyJ")):
                    return dec
            except Exception:  # noqa: BLE001
                pass
            return raw.decode(errors="replace").strip()
    die("no Supabase token: SUPABASE_ACCESS_TOKEN or /opt/data/secrets/supabase_token")
    return ""


def query(sql: str):
    req = urllib.request.Request(API, data=json.dumps({"query": sql}).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token()}",
                                          "Content-Type": "application/json",
                                          # Cloudflare in front of api.supabase.com answers
                                          # HTTP 403 "error code: 1010" to urllib's default UA.
                                          "User-Agent": "hermes-xpeng-guests/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            body = json.loads(r.read() or b"[]")
    except urllib.error.HTTPError as exc:
        die(f"Supabase API HTTP {exc.code}: {exc.read().decode(errors='replace')[:400]}")
    if isinstance(body, dict) and body.get("error"):
        die(f"Supabase API: {body}")
    return body


def lit(value: str | None) -> str:
    """SQL literal via dollar quoting with a random tag (no escaping games)."""
    if value is None or value == "":
        return "null"
    if any(ord(c) < 32 for c in value):
        die("control characters are not allowed in values")
    tag = "q" + secrets.token_hex(4)
    return f"${tag}${value}${tag}$"


def clean(v: str | None, maxlen: int = 120) -> str | None:
    if v is None:
        return None
    v = " ".join(v.split())
    if len(v) > maxlen:
        die(f"value too long (> {maxlen}): {v[:30]}…")
    return v or None


def cmd_find(args) -> None:
    q = clean(args.query, 120) or ""
    if "@" in q:
        where = f"email = lower({lit(q)})"
    else:
        where = (f"public.normalize_text(first_name || ' ' || last_name) like "
                 f"'%' || public.normalize_text({lit(q)}) || '%'")
    rows = query(f"select {FIELDS} from public.guests where deleted_at is null and {where} "
                 f"order by last_name, first_name limit 20")
    print(json.dumps(rows, ensure_ascii=False, indent=1))
    if not rows:
        sys.exit(4)


def cmd_add(args) -> None:
    email = (clean(args.email, 200) or "").lower()
    if not EMAIL_RE.match(email):
        die(f"invalid email: {email!r}")
    first, last = clean(args.first_name), clean(args.last_name)
    if not first or not last:
        die("--first-name and --last-name are required (real names, not placeholders)")
    company, market = clean(args.company), clean(args.market, 60)
    cluster, job = clean(args.cluster, 60), clean(args.job_title)
    requested_by = clean(args.requested_by, 300)
    if not requested_by:
        die("--requested-by is required: who authorised this addition and through which channel")
    is_internal = "true" if args.internal else ("false" if args.external else "null")

    existing = query(f"select {FIELDS} from public.guests where email = {lit(email)}")
    if existing:
        print(json.dumps({"created": False, "reason": "email already on the guest list",
                          "guest": existing[0]}, ensure_ascii=False, indent=1))
        sys.exit(3)

    sql = (
        "insert into public.guests (email, first_name, last_name, company, market, cluster, "
        "job_title, is_internal, status) values ("
        f"{lit(email)}, {lit(first)}, {lit(last)}, {lit(company)}, {lit(market)}, {lit(cluster)}, "
        f"{lit(job)}, {is_internal}, 'pending') "
        f"on conflict (email) do nothing returning {FIELDS}"
    )
    if args.dry_run:
        print("--- DRY RUN: nothing written ---")
        print(sql)
        return
    rows = query(sql)
    if not rows:
        die("insert returned no row (race on a duplicate email?)", 3)
    print(json.dumps({"created": True, "requested_by": requested_by, "guest": rows[0],
                      "next_step": "invitation email NOT sent — back-office /admin/invitations"},
                     ensure_ascii=False, indent=1))


# ----------------------------------------------------------------------------- invite

def event_facts() -> dict:
    """Read the params the invitation template needs from the site's own event.ts (local
    clone). Falls back to the values known on 2026-09-06 if the clone is missing."""
    facts = {"name": "TTT Training", "dateLabel": "17–18 September 2026",
             "venue": "Circuit de Mortefontaine", "domain": "ttt-globaltraining.com",
             "fromEmail": "contact@ttt-globaltraining.com", "fromName": "TTT Global Training",
             "timezone": "Europe/Paris", "source": "built-in fallback"}
    path = os.path.join(SITE_CLONE, "src", "config", "event.ts")
    try:
        src = open(path, encoding="utf-8").read()
    except OSError:
        return facts
    src = re.sub(r"//.*", "", src)

    def grab(key: str) -> str | None:
        m = re.search(rf'\b{key}:\s*"((?:[^"\\]|\\.)*)"', src)
        return m.group(1) if m else None

    facts.update({k: v for k, v in {
        "name": grab("name"), "dateLabel": grab("dateLabel"), "domain": grab("domain"),
        "fromEmail": grab("fromEmail"), "fromName": grab("fromName"), "timezone": grab("timezone"),
    }.items() if v})
    venue = re.search(r'venue:\s*\{[^}]*?\bname:\s*"([^"]+)"', src, re.S)
    if venue:
        facts["venue"] = venue.group(1)
    facts["source"] = path
    return facts


def deadline_label(tz_name: str) -> str:
    """'10 September' — en-GB day + long month in the event timezone, like the back-office."""
    rows = query("select value from public.app_settings where key = 'registration_deadline'")
    if not rows:
        die("app_settings.registration_deadline not found")
    raw = str(rows[0]["value"]).strip('"')
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    try:
        from zoneinfo import ZoneInfo
        dt = dt.astimezone(ZoneInfo(tz_name))
    except Exception:  # noqa: BLE001
        pass
    return f"{dt.day} {dt.strftime('%B')}"


def brevo_send(template_id: int, to_email: str, sender: dict, params: dict) -> str:
    key = os.environ.get("BREVO_API_KEY", "")
    if not key:
        die("BREVO_API_KEY is not set")
    body = {"templateId": template_id, "sender": sender, "to": [{"email": to_email}], "params": params}
    req = urllib.request.Request(BREVO_SEND, data=json.dumps(body).encode(), method="POST",
                                 headers={"api-key": key, "content-type": "application/json",
                                          "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            out = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Brevo {exc.code}: {exc.read().decode(errors='replace')[:300]}") from None
    return str(out.get("messageId") or "")


def cmd_invite(args) -> None:
    email = (clean(args.email, 200) or "").lower()
    if not EMAIL_RE.match(email):
        die(f"invalid email: {email!r}")
    requested_by = clean(args.requested_by, 300)
    if not requested_by:
        die("--requested-by is required: who authorised this invitation and through which channel")
    rows = query(f"select {FIELDS} from public.guests where deleted_at is null and email = {lit(email)}")
    if not rows:
        die("no guest with that email — add them first", 4)
    g = rows[0]
    if g["status"] != "pending":
        die(f"guest status is '{g['status']}', not 'pending' — nothing to invite", 3)
    if g["invited_at"] and not args.resend:
        die(f"already invited on {g['invited_at']} ({g['invitation_count']}x) — use --resend to send again", 3)

    facts = event_facts()
    template_id = int(os.environ.get("BREVO_TEMPLATE_INVITATION", "815"))
    site = f"https://{facts['domain']}"
    params = {"firstName": g["first_name"], "registrationUrl": f"{site}/register", "homeUrl": site,
              "eventName": facts["name"], "eventDates": facts["dateLabel"], "venueName": facts["venue"],
              "deadline": deadline_label(facts["timezone"])}
    sender = {"email": os.environ.get("BREVO_FROM_EMAIL", facts["fromEmail"]),
              "name": os.environ.get("BREVO_FROM_NAME", facts["fromName"])}
    if args.dry_run:
        print("--- DRY RUN: nothing sent, nothing written ---")
        print(json.dumps({"templateId": template_id, "sender": sender, "to": email, "params": params,
                          "facts_source": facts["source"]}, ensure_ascii=False, indent=1))
        return

    now = datetime.now(timezone.utc).isoformat()
    try:
        message_id = brevo_send(template_id, email, sender, params)
    except Exception as exc:  # noqa: BLE001
        query("insert into public.email_audit_log (guest_id, template, recipient_email, status, error) "
              f"values ({lit(g['id'])}::uuid, 'INVITATION', {lit(email)}, 'failed', {lit(str(exc)[:500])})")
        die(f"invitation NOT sent: {exc}")
    query("insert into public.email_audit_log (guest_id, template, recipient_email, status, provider_message_id) "
          f"values ({lit(g['id'])}::uuid, 'INVITATION', {lit(email)}, 'sent', {lit(message_id or None)})")
    updated = query(f"update public.guests set invited_at = {lit(now)}::timestamptz, "
                    f"invitation_count = invitation_count + 1 where id = {lit(g['id'])}::uuid "
                    "returning invited_at, invitation_count")
    print(json.dumps({"invited": True, "email": email, "guest_id": g["id"], "templateId": template_id,
                      "messageId": message_id, "requested_by": requested_by,
                      "invited_at": updated[0]["invited_at"] if updated else now,
                      "invitation_count": updated[0]["invitation_count"] if updated else None,
                      "deadline_in_email": params["deadline"]}, ensure_ascii=False, indent=1))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("find", help="guests matching an email or a name fragment")
    s.add_argument("query")
    s.set_defaults(func=cmd_find)
    s = sub.add_parser("add", help="insert one guest (status pending, no invitation)")
    s.add_argument("--email", required=True)
    s.add_argument("--first-name", required=True)
    s.add_argument("--last-name", required=True)
    s.add_argument("--company")
    s.add_argument("--market", help="e.g. NL, DE, Nordics — as used in the guest list")
    s.add_argument("--cluster", help="e.g. 'Northern & Eastern EU', 'Internals'")
    s.add_argument("--job-title")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--internal", action="store_true", help="XPENG employee")
    g.add_argument("--external", action="store_true", help="dealer / partner / external trainer")
    s.add_argument("--requested-by", required=True,
                   help='who authorised it and how, e.g. "Gwendoline (XPENG) by email 07/09, uid 12"')
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_add)
    s = sub.add_parser("invite", help="send the Brevo invitation to one pending guest")
    s.add_argument("email")
    s.add_argument("--resend", action="store_true", help="allow a guest who was already invited")
    s.add_argument("--requested-by", required=True,
                   help='who authorised it and how, e.g. "Charlotte (logistics) by email 08/09, uid 21"')
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_invite)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

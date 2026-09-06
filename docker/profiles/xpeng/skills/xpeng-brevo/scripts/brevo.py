#!/usr/bin/env python3
"""Brevo (transactional email) CLI for the TTT Global Training account.

Read-mostly helper around https://api.brevo.com/v3 — key from BREVO_API_KEY (Railway var).
Standard library only. The key is never printed.

Commands:
  templates                      list transactional templates (id, name, subject, active)
  template <id>                  one template with its HTML (truncated unless --full)
  events --email x [--days N]    delivery events for one recipient (requests, delivered,
                                 opened, clicked, softBounces, hardBounces, blocked, spam…)
  events --days N [--event hardBounces]   account-wide events (audit bounces of a campaign)
  blocked                        transactional blocked contacts (hard bounces, unsubscribes)
  send-template --template-id N --to a@b.c [--params '{"firstName":"…"}'] [--dry-run]
                                 resend a templated email (e.g. Confirmation 816). Always
                                 pass the full params the template expects (see the
                                 site repo, src/lib/email/types.ts).

Everything the site itself sends is also logged in Supabase public.email_audit_log
(provider_message_id = Brevo messageId) — cross-check there before resending.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.brevo.com/v3"
KEY = os.environ.get("BREVO_API_KEY", "")
FROM_EMAIL = os.environ.get("BREVO_FROM_EMAIL", "contact@ttt-globaltraining.com")
FROM_NAME = os.environ.get("BREVO_FROM_NAME", "TTT Global Training")


def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def call(method: str, path: str, params: dict | None = None, body: dict | None = None):
    if not KEY:
        die("BREVO_API_KEY is not set in the environment")
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "api-key": KEY, "accept": "application/json", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        die(f"Brevo HTTP {exc.code} on {method} {path}: {detail}")


def cmd_templates(args) -> None:
    out = call("GET", "/smtp/templates", {"limit": 50, "offset": 0})
    for t in out.get("templates", []):
        print(f"{t['id']:>5}  {'active' if t.get('isActive') else 'off   '}  {t['name'][:45]:<45}  {t.get('subject','')[:60]}")
    print(f"({out.get('count', 0)} templates)")


def cmd_template(args) -> None:
    t = call("GET", f"/smtp/templates/{args.id}")
    html = t.pop("htmlContent", "") or ""
    print(json.dumps(t, ensure_ascii=False, indent=1))
    print("\n--- htmlContent ---")
    print(html if args.full else html[:3000] + ("…" if len(html) > 3000 else ""))


def cmd_events(args) -> None:
    params = {"limit": args.limit, "offset": 0, "days": args.days,
              "email": args.email, "event": args.event, "sort": "desc"}
    out = call("GET", "/smtp/statistics/events", params)
    rows = out.get("events", [])
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return
    for e in rows:
        print(f"{e.get('date','')[:19]}  {e.get('event',''):<13} {e.get('email',''):<40} "
              f"{(e.get('subject') or '')[:50]}  {e.get('reason') or ''}")
    if not rows:
        print("(no events)")


def cmd_blocked(args) -> None:
    out = call("GET", "/smtp/blockedContacts", {"limit": 100, "offset": 0, "sort": "desc"})
    for c in out.get("contacts", []):
        print(f"{c.get('blockedAt','')[:19]}  {c.get('email',''):<40} {c.get('reason',{}).get('code','')}  "
              f"{c.get('reason',{}).get('message','')[:60]}")
    print(f"({out.get('count', 0)} blocked contacts)")


def cmd_send_template(args) -> None:
    params = json.loads(args.params) if args.params else {}
    body = {"templateId": args.template_id,
            "to": [{"email": args.to} | ({"name": args.name} if args.name else {})],
            "params": params,
            "replyTo": {"email": FROM_EMAIL, "name": FROM_NAME}}
    if args.dry_run:
        print("--- DRY RUN: not sent ---")
        print(json.dumps(body, ensure_ascii=False, indent=1))
        return
    out = call("POST", "/smtp/email", body=body)
    print(json.dumps({"sent": True, "to": args.to, "templateId": args.template_id,
                      "messageId": out.get("messageId")}))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("templates").set_defaults(func=cmd_templates)
    s = sub.add_parser("template"); s.add_argument("id", type=int); s.add_argument("--full", action="store_true")
    s.set_defaults(func=cmd_template)
    s = sub.add_parser("events")
    s.add_argument("--email"); s.add_argument("--days", type=int, default=30)
    s.add_argument("--event", help="requests|delivered|hardBounces|softBounces|blocked|spam|opened|clicks|deferred|error")
    s.add_argument("--limit", type=int, default=50); s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_events)
    sub.add_parser("blocked").set_defaults(func=cmd_blocked)
    s = sub.add_parser("send-template")
    s.add_argument("--template-id", type=int, required=True); s.add_argument("--to", required=True)
    s.add_argument("--name"); s.add_argument("--params", help="JSON object")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_send_template)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

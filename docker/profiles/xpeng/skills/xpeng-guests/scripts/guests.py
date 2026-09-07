#!/usr/bin/env python3
"""Guest-list writer for the TTT Global Training desk (Supabase project xpeng-ttt-training).

The ONLY write path of the xpeng profile. It does exactly two things:
  find  <email | name fragment>          read guests matching (email, first/last name)
  add   --email … --first-name … --last-name … [--company --market --cluster --job-title]
        [--internal] [--requested-by "who asked, how"] [--dry-run]
        insert ONE guest with status 'pending' (no invitation is sent — the back-office does
        that from /admin/invitations). If the email already exists, nothing is written and
        the existing row is printed (exit 3). Never updates, never deletes.

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

REF = os.environ.get("XPENG_SUPABASE_REF", "daxqygwolwqciusyprvo")
API = f"https://api.supabase.com/v1/projects/{REF}/database/query"
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
                                          "Content-Type": "application/json"})
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
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

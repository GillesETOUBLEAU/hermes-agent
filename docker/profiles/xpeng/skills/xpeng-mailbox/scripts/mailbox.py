#!/usr/bin/env python3
"""Mailbox CLI for the XPENG / TTT Global Training organisation inbox.

Read, reply, send, flag and move messages of contact@ttt-globaltraining.com over
IMAP + SMTP (PlanetHoster, mail.ttt-globaltraining.com). Standard library only.

Credentials (never printed, never logged):
  XPENG_MAIL_USER            login / sender address (default contact@ttt-globaltraining.com)
  XPENG_MAIL_PASSWORD        plain password, OR
  XPENG_MAIL_PASSWORD_FILE   base64-encoded password file
                             (default /opt/data/secrets/ttt_imap_pass_b64 — the file the
                             default profile's daily report already uses)
  XPENG_MAIL_HOST            default mail.ttt-globaltraining.com (cert covers *.ttt-globaltraining.com)
  XPENG_MAIL_FROM_NAME       default "TTT Global Training"
  XPENG_MAIL_DRY_RUN=1       print outgoing messages instead of sending them

Commands (see --help): folders · list · read · reply · send · flag · move · search.
Outgoing messages are copied to the Sent folder (IMAP APPEND) so the webmail shows them.
"""
from __future__ import annotations

import argparse
import base64
import email
import email.policy
import imaplib
import json
import os
import re
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr, parsedate_to_datetime

HOST = os.environ.get("XPENG_MAIL_HOST", "mail.ttt-globaltraining.com")
USER = os.environ.get("XPENG_MAIL_USER", "contact@ttt-globaltraining.com")
FROM_NAME = os.environ.get("XPENG_MAIL_FROM_NAME", "TTT Global Training")
IMAP_PORT = int(os.environ.get("XPENG_MAIL_IMAP_PORT", "993"))
SMTP_PORT = int(os.environ.get("XPENG_MAIL_SMTP_PORT", "465"))
PASSWORD_FILE = os.environ.get("XPENG_MAIL_PASSWORD_FILE", "/opt/data/secrets/ttt_imap_pass_b64")
DRY_RUN = os.environ.get("XPENG_MAIL_DRY_RUN", "") not in ("", "0", "false")
SENT_CANDIDATES = ("Sent", "INBOX.Sent", "Sent Items", "Sent Messages", "INBOX.Sent Items")
DRAFT_CANDIDATES = ("Drafts", "INBOX.Drafts", "Draft", "INBOX.Draft")


def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def password() -> str:
    pw = os.environ.get("XPENG_MAIL_PASSWORD")
    if pw:
        return pw
    try:
        with open(PASSWORD_FILE, "rb") as fh:
            return base64.b64decode(fh.read().strip()).decode()
    except FileNotFoundError:
        die("no mailbox password: set XPENG_MAIL_PASSWORD or XPENG_MAIL_PASSWORD_FILE")
    except Exception as exc:  # noqa: BLE001
        die(f"cannot read password file: {type(exc).__name__}")
    return ""  # unreachable


def imap() -> imaplib.IMAP4_SSL:
    ctx = ssl.create_default_context()
    m = imaplib.IMAP4_SSL(HOST, IMAP_PORT, ssl_context=ctx, timeout=30)
    m.login(USER, password())
    return m


def hdr(value) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).replace("\r", " ").replace("\n", " ").strip()
    except Exception:  # noqa: BLE001
        return str(value)


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</(p|div|tr|li|h[1-6])>", "\n", html)
    text = re.sub(r"<[^>]+>", "", html)
    import html as htmllib
    text = htmllib.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def body_text(msg: email.message.Message) -> str:
    plain, html = None, None
    for part in msg.walk():
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_payload(decode=True) or b""
            text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        if ctype == "text/plain" and plain is None:
            plain = text
        elif ctype == "text/html" and html is None:
            html = text
    if plain and plain.strip():
        return plain.strip()
    if html:
        return html_to_text(html)
    return ""


def attachments(msg: email.message.Message) -> list[str]:
    return [hdr(p.get_filename()) for p in msg.walk() if p.get_filename()]


def fetch(m: imaplib.IMAP4_SSL, uid: str) -> email.message.Message:
    typ, data = m.uid("fetch", uid, "(BODY.PEEK[])")
    if typ != "OK" or not data or data[0] is None:
        die(f"message uid {uid} not found in the selected folder")
    raw = data[0][1]
    return email.message_from_bytes(raw, policy=email.policy.compat32)


def envelope(m: imaplib.IMAP4_SSL, uid: str) -> dict:
    typ, data = m.uid("fetch", uid, "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID)])")
    if typ != "OK" or not data or data[0] is None:
        return {}
    flags = ""
    header_bytes = b""
    for item in data:
        if isinstance(item, tuple):
            flags_match = re.search(rb"FLAGS \(([^)]*)\)", item[0])
            if flags_match:
                flags = flags_match.group(1).decode(errors="replace")
            header_bytes = item[1]
    msg = email.message_from_bytes(header_bytes, policy=email.policy.compat32)
    date_raw = msg.get("Date", "")
    try:
        date_iso = parsedate_to_datetime(date_raw).astimezone(timezone.utc).isoformat(timespec="minutes")
    except Exception:  # noqa: BLE001
        date_iso = date_raw
    return {
        "uid": uid,
        "date": date_iso,
        "from": hdr(msg.get("From")),
        "to": hdr(msg.get("To")),
        "subject": hdr(msg.get("Subject")),
        "message_id": (msg.get("Message-ID") or "").strip(),
        "flags": flags,
        "seen": "\\Seen" in flags,
        "answered": "\\Answered" in flags,
    }


def _folder_names(m: imaplib.IMAP4_SSL) -> list[str]:
    typ, data = m.list()
    names = []
    for line in data or []:
        if not line:
            continue
        s = line.decode(errors="replace") if isinstance(line, bytes) else str(line)
        mm = re.search(r'"([^"]*)"\s*$|(\S+)\s*$', s)
        if mm:
            names.append(mm.group(1) or mm.group(2))
    return names


def _find_folder(m: imaplib.IMAP4_SSL, candidates: tuple, keyword: str) -> str | None:
    names = _folder_names(m)
    for cand in candidates:
        if cand in names:
            return cand
    for n in names:
        if keyword in n.lower():
            return n
    return None


def sent_folder(m: imaplib.IMAP4_SSL) -> str | None:
    return _find_folder(m, SENT_CANDIDATES, "sent")


def save_draft(msg: EmailMessage) -> None:
    """Store the message in the Drafts folder instead of sending it (review in the webmail)."""
    m = imap()
    folder = _find_folder(m, DRAFT_CANDIDATES, "draft")
    if not folder:
        m.logout()
        die("no Drafts folder found on the server")
    typ, _ = m.append(f'"{folder}"', "\\Draft", imaplib.Time2Internaldate(datetime.now(timezone.utc)), msg.as_bytes())
    m.logout()
    if typ != "OK":
        die("could not append the draft")
    print(json.dumps({"draft_saved": True, "folder": folder, "to": msg["To"], "subject": msg["Subject"],
                      "message_id": msg["Message-ID"]}))


def _split(csv: str | None) -> list[str]:
    return [x.strip() for x in (csv or "").split(",") if x.strip()]


def deliver(msg: EmailMessage, recipients: list[str]) -> None:
    if not recipients:
        die("no recipients")
    if DRY_RUN:
        print("--- DRY RUN: message NOT sent ---")
        print(msg.as_string())
        return
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(HOST, SMTP_PORT, context=ctx, timeout=30) as s:
        s.login(USER, password())
        s.send_message(msg, from_addr=USER, to_addrs=recipients)
    # Copy to Sent so the webmail shows the conversation.
    try:
        m = imap()
        folder = sent_folder(m)
        if folder:
            m.append(f'"{folder}"', "\\Seen", imaplib.Time2Internaldate(datetime.now(timezone.utc)), msg.as_bytes())
        m.logout()
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: sent, but could not copy to Sent folder ({type(exc).__name__})", file=sys.stderr)
    print(json.dumps({"sent": True, "to": recipients, "subject": msg["Subject"], "message_id": msg["Message-ID"]}))


def build(subject: str, body: str, to: list[str], cc: list[str], html: str | None = None,
          in_reply_to: str | None = None, references: str | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"{FROM_NAME} <{USER}>"
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=USER.split("@")[-1])
    msg["Reply-To"] = USER
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = (f"{references} {in_reply_to}".strip() if references else in_reply_to)
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def read_file(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ----------------------------------------------------------------------------- commands

def cmd_folders(args) -> None:
    m = imap()
    typ, data = m.list()
    for line in data or []:
        print(line.decode(errors="replace") if isinstance(line, bytes) else line)
    m.logout()


def _search_criteria(args) -> str:
    crit = []
    if getattr(args, "unseen", False):
        crit.append("UNSEEN")
    if getattr(args, "since", None):
        d = datetime.strptime(args.since, "%Y-%m-%d")
        crit.append(f'SINCE "{d.strftime("%d-%b-%Y")}"')
    if getattr(args, "days", None):
        d = datetime.now() - timedelta(days=args.days)
        crit.append(f'SINCE "{d.strftime("%d-%b-%Y")}"')
    if getattr(args, "sender", None):
        crit.append(f'FROM "{args.sender}"')
    if getattr(args, "subject", None):
        crit.append(f'SUBJECT "{args.subject}"')
    if getattr(args, "text", None):
        crit.append(f'TEXT "{args.text}"')
    return "(" + " ".join(crit) + ")" if crit else "ALL"


def cmd_list(args) -> None:
    m = imap()
    m.select(f'"{args.folder}"', readonly=True)
    typ, data = m.uid("search", None, _search_criteria(args))
    uids = (data[0] or b"").split()
    uids = [u.decode() for u in uids][-args.limit:]
    rows = [envelope(m, u) for u in reversed(uids)]
    m.logout()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        for r in rows:
            mark = " " if r.get("seen") else "*"
            ans = "R" if r.get("answered") else " "
            print(f"{mark}{ans} {r['uid']:>6}  {r['date']:<17} {r['from'][:38]:<38}  {r['subject'][:70]}")
        if not rows:
            print("(no messages)")


def cmd_read(args) -> None:
    m = imap()
    m.select(f'"{args.folder}"', readonly=True)
    msg = fetch(m, args.uid)
    m.logout()
    out = {
        "uid": args.uid,
        "from": hdr(msg.get("From")),
        "to": hdr(msg.get("To")),
        "cc": hdr(msg.get("Cc")),
        "date": hdr(msg.get("Date")),
        "subject": hdr(msg.get("Subject")),
        "message_id": (msg.get("Message-ID") or "").strip(),
        "in_reply_to": (msg.get("In-Reply-To") or "").strip(),
        "auto_submitted": hdr(msg.get("Auto-Submitted")),
        "attachments": attachments(msg),
        "body": body_text(msg)[: args.max_chars],
    }
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        for k in ("from", "to", "cc", "date", "subject", "message_id", "auto_submitted"):
            if out[k]:
                print(f"{k.capitalize()}: {out[k]}")
        if out["attachments"]:
            print("Attachments: " + ", ".join(out["attachments"]))
        print("\n" + out["body"])


def cmd_reply(args) -> None:
    m = imap()
    m.select(f'"{args.folder}"', readonly=True)
    orig = fetch(m, args.uid)
    m.logout()
    body = read_file(args.body_file).rstrip() + "\n"
    reply_to = hdr(orig.get("Reply-To")) or hdr(orig.get("From"))
    to_addr = parseaddr(reply_to)[1]
    if not to_addr:
        die("original message has no usable From/Reply-To address")
    to = [to_addr]
    cc = _split(args.cc)
    if args.all:
        for field in ("To", "Cc"):
            for name, addr in email.utils.getaddresses([hdr(orig.get(field))]):
                if addr and addr.lower() not in (USER.lower(), to_addr.lower()) and addr not in cc:
                    cc.append(addr)
    subject = hdr(orig.get("Subject"))
    if not re.match(r"(?i)^\s*re\s*:", subject):
        subject = f"Re: {subject}"
    if args.quote:
        quoted = "\n".join("> " + l for l in body_text(orig).splitlines())
        body += f"\n\nOn {hdr(orig.get('Date'))}, {hdr(orig.get('From'))} wrote:\n{quoted}\n"
    msg = build(subject, body, to, cc, html=read_file(args.html_file) if args.html_file else None,
                in_reply_to=(orig.get("Message-ID") or "").strip() or None,
                references=(orig.get("References") or "").strip() or None)
    if args.draft:
        save_draft(msg)
        return
    deliver(msg, to + cc)
    if not DRY_RUN and args.mark:
        m = imap()
        m.select(f'"{args.folder}"')
        m.uid("store", args.uid, "+FLAGS", "(\\Seen \\Answered)")
        m.logout()


def cmd_send(args) -> None:
    to, cc = _split(args.to), _split(args.cc)
    body = read_file(args.body_file).rstrip() + "\n"
    msg = build(args.subject, body, to, cc, html=read_file(args.html_file) if args.html_file else None)
    if args.draft:
        save_draft(msg)
        return
    deliver(msg, to + cc)


def cmd_flag(args) -> None:
    m = imap()
    m.select(f'"{args.folder}"')
    flag_map = {"seen": "\\Seen", "answered": "\\Answered", "flagged": "\\Flagged"}
    flags = " ".join(flag_map[f] for f in args.flags)
    op = "-FLAGS" if args.remove else "+FLAGS"
    for uid in args.uids:
        typ, _ = m.uid("store", uid, op, f"({flags})")
        print(f"{uid}: {op} {flags} -> {typ}")
    m.logout()


def cmd_move(args) -> None:
    m = imap()
    m.select(f'"{args.folder}"')
    for uid in args.uids:
        typ, _ = m.uid("copy", uid, f'"{args.to}"')
        if typ != "OK":
            die(f"copy of {uid} to {args.to} failed")
        m.uid("store", uid, "+FLAGS", "(\\Deleted)")
        print(f"{uid}: moved to {args.to}")
    m.expunge()
    m.logout()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--folder", default="INBOX", help="IMAP folder (default INBOX)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("folders", help="list IMAP folders")

    for name in ("list", "search"):
        s = sub.add_parser(name, help="list messages (search = same, with filters)")
        s.add_argument("--unseen", action="store_true")
        s.add_argument("--since", help="YYYY-MM-DD")
        s.add_argument("--days", type=int, help="last N days")
        s.add_argument("--from", dest="sender")
        s.add_argument("--subject")
        s.add_argument("--text")
        s.add_argument("--limit", type=int, default=50)
        s.add_argument("--json", action="store_true")
        s.set_defaults(func=cmd_list)

    s = sub.add_parser("read", help="print one message (headers + text body)")
    s.add_argument("uid")
    s.add_argument("--json", action="store_true")
    s.add_argument("--max-chars", type=int, default=12000)
    s.set_defaults(func=cmd_read)

    s = sub.add_parser("reply", help="reply to a message (body from file, threaded headers)")
    s.add_argument("uid")
    s.add_argument("--body-file", required=True, help="plain-text body (UTF-8)")
    s.add_argument("--html-file", help="optional HTML alternative")
    s.add_argument("--cc", help="comma-separated")
    s.add_argument("--all", action="store_true", help="reply-all (other To/Cc go to Cc)")
    s.add_argument("--quote", action="store_true", help="quote the original below the reply")
    s.add_argument("--no-mark", dest="mark", action="store_false", help="do not flag original Seen+Answered")
    s.add_argument("--draft", action="store_true", help="save to the Drafts folder instead of sending")
    s.set_defaults(func=cmd_reply)

    s = sub.add_parser("send", help="send a new message")
    s.add_argument("--to", required=True, help="comma-separated")
    s.add_argument("--cc")
    s.add_argument("--subject", required=True)
    s.add_argument("--body-file", required=True)
    s.add_argument("--html-file")
    s.add_argument("--draft", action="store_true", help="save to the Drafts folder instead of sending")
    s.set_defaults(func=cmd_send)

    s = sub.add_parser("flag", help="add/remove flags")
    s.add_argument("uids", nargs="+")
    s.add_argument("--flags", nargs="+", choices=["seen", "answered", "flagged"], required=True)
    s.add_argument("--remove", action="store_true")
    s.set_defaults(func=cmd_flag)

    s = sub.add_parser("move", help="move messages to another folder")
    s.add_argument("uids", nargs="+")
    s.add_argument("--to", required=True, help="target folder")
    s.set_defaults(func=cmd_move)

    args = p.parse_args()
    if args.cmd == "folders":
        cmd_folders(args)
        return
    try:
        args.func(args)
    except imaplib.IMAP4.error as exc:
        die(f"IMAP error: {exc}")
    except smtplib.SMTPException as exc:
        die(f"SMTP error: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()

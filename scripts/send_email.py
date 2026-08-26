#!/usr/bin/env python3
"""Send the latest Market Wrap Up snapshot PDF to bjpotts@gmail.com via macOS Mail.app.

Delivers the condensed 1-page snapshot PDF (the file that make_snapshot.py writes),
with the standing subject/body. Uses the locally configured Mail.app account since
the Gmail MCP tool is not available in this environment.
"""
import glob
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TO = "bjpotts@gmail.com"
SUBJECT = "Market Wrap Up Morning Edition"
BODY = """Global Market Update, with your around the world news.

Regards

Brandon Potts"""


def latest_snapshot():
    pdfs = sorted(glob.glob(os.path.join(BASE, "public-news-wire-snapshot-*.pdf")))
    return pdfs[-1] if pdfs else None


def esc(s):
    # Escape for embedding inside an AppleScript double-quoted string.
    return s.replace("\\", "\\\\").replace('"', '\\"')


def send(pdf, dry_run=False):
    subject = esc(SUBJECT)
    body = esc(BODY)
    attachment = esc(os.path.abspath(pdf))
    script = f"""
tell application "Mail"
    set theMessage to make new outgoing message with properties {{subject:"{subject}", content:"{body}", visible:false}}
    tell theMessage
        make new to recipient at end of to recipients with properties {{address:"{TO}"}}
        make new attachment with properties {{file name:(POSIX file "{attachment}")}} at after the last paragraph
    end tell
    send theMessage
end tell
"""
    if dry_run:
        print("DRY RUN: would send %s to %s" % (pdf, TO))
        return True
    p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if p.returncode != 0:
        print("MAIL ERROR: %s" % p.stderr.strip(), file=sys.stderr)
        return False
    print("EMAIL SENT: %s -> %s" % (os.path.basename(pdf), TO))
    return True


def main():
    dry = "--dry-run" in sys.argv
    pdf = latest_snapshot()
    if not pdf:
        print("No snapshot PDF found; run make_snapshot.py first.", file=sys.stderr)
        return 1
    return 0 if send(pdf, dry_run=dry) else 1


if __name__ == "__main__":
    sys.exit(main())

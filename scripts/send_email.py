#!/usr/bin/env python3
"""Send the latest Market Wrap Up full PDF to bjpotts@gmail.com via macOS Mail.app.

Delivers the full multi-page PDF (the file that make_pdf.py writes),
with the standing subject/body. Uses the locally configured Mail.app account since
the Gmail MCP tool is not available in this environment.
"""
import glob
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TO = "bjpotts@gmail.com"
SUBJECT = "Market Wrap Up Morning Edition"
BODY = """Global Market Update, with your around the world news.

Regards

Brandon Potts"""


def latest_pdf():
    pdfs = sorted(glob.glob(os.path.join(BASE, "market-wrap-up-*.pdf")))
    return pdfs[-1] if pdfs else None


def esc(s):
    # Escape for embedding inside an AppleScript double-quoted string.
    return s.replace("\\", "\\\\").replace('"', '\\"')


def ensure_mail_running():
    """Make sure Mail.app is up and responding before sending.

    Under launchd (non-interactive background context) Mail can be cold or not
    yet responding, which caused the "AppleEvent timed out (-1712)" error on
    scheduled runs. Launching it and waiting for it to be reachable avoids that.
    """
    subprocess.run(["open", "-a", "Mail"], check=False)
    for _ in range(30):
        p = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to count (application processes whose name is "Mail")'],
            capture_output=True, text=True, timeout=10,
        )
        if p.returncode == 0 and p.stdout.strip() != "0":
            return True
        time.sleep(1)
    return False


def send(pdf, dry_run=False):
    subject = esc(SUBJECT)
    body = esc(BODY)
    attachment = esc(os.path.abspath(pdf))
    script = f"""
with timeout of 120 seconds
tell application "Mail"
    set theMessage to make new outgoing message with properties {{subject:"{subject}", content:"{body}", visible:false}}
    tell theMessage
        make new to recipient at end of to recipients with properties {{address:"{TO}"}}
        make new attachment with properties {{file name:(POSIX file "{attachment}")}} at after the last paragraph
    end tell
    send theMessage
end tell
end timeout
"""
    if dry_run:
        print("DRY RUN: would send %s to %s" % (pdf, TO))
        return True
    if not ensure_mail_running():
        print("MAIL ERROR: Mail.app did not become responsive", file=sys.stderr)
        return False
    for attempt in range(1, 4):
        p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=150)
        if p.returncode == 0:
            print("EMAIL SENT: %s -> %s" % (os.path.basename(pdf), TO))
            return True
        print("MAIL ATTEMPT %d/3 failed: %s" % (attempt, p.stderr.strip() or "osascript timed out"), file=sys.stderr)
        if attempt < 3:
            time.sleep(10 * attempt)
    return False


def main():
    dry = "--dry-run" in sys.argv
    pdf = latest_pdf()
    if not pdf:
        print("No full PDF found; run make_pdf.py first.", file=sys.stderr)
        return 1
    return 0 if send(pdf, dry_run=dry) else 1


if __name__ == "__main__":
    sys.exit(main())

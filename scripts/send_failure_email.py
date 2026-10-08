#!/usr/bin/env python3
"""Send a failure notification email when a scheduled Market Wrap Up run fails.

Uses macOS Mail.app. No PDF is attached; the email explains what went wrong.
"""
import argparse
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TO = "bjpotts@gmail.com"


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def ensure_mail_running():
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


def send(edition, reason, dry_run=False):
    subject = esc("Market Wrap Up %s - RUN FAILED" % edition)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    body = esc("""The scheduled %s run failed after 3 retries.

Time: %s
Project: %s

Failure reason:
%s

The report was not published and no PDF was emailed. Manual intervention or a re-run is required.

Regards

Market Wrap Up Scheduler""" % (edition, timestamp, BASE, reason.strip()))
    script = f"""
with timeout of 120 seconds
tell application "Mail"
    set theMessage to make new outgoing message with properties {{subject:"{subject}", content:"{body}", visible:false}}
    tell theMessage
        make new to recipient at end of to recipients with properties {{address:"{TO}"}}
    end tell
    send theMessage
end tell
end timeout
"""
    if dry_run:
        print("DRY RUN: would send failure email to %s" % TO)
        print("Reason:", reason)
        return True
    if not ensure_mail_running():
        print("MAIL ERROR: Mail.app did not become responsive", file=sys.stderr)
        return False
    for attempt in range(1, 4):
        p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=150)
        if p.returncode == 0:
            print("FAILURE EMAIL SENT -> %s" % TO)
            return True
        print("FAILURE EMAIL ATTEMPT %d/3 failed: %s" % (attempt, p.stderr.strip() or "osascript timed out"), file=sys.stderr)
        if attempt < 3:
            time.sleep(10 * attempt)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--edition", required=True, help="Morning Edition or Evening Edition")
    parser.add_argument("--reason", default="Unknown error", help="Failure reason")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if send(args.edition, args.reason, dry_run=args.dry_run) else 1


if __name__ == "__main__":
    sys.exit(main())

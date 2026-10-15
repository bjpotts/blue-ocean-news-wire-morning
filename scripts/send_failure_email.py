#!/usr/bin/env python3
"""Send a failure notification email via Mail.app using the Gmail account."""
import argparse
import os
import subprocess
import sys
import time

TO = "bjpotts@gmail.com"
FROM = "bjpotts@gmail.com"


def ensure_mail_running():
    """Start Mail.app if it is not running so AppleScript can talk to it."""
    out = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to return (name of processes) contains "Mail"'],
        capture_output=True,
        text=True,
    ).stdout.strip()

    if out != "true":
        subprocess.run(["open", "-a", "Mail"], check=False)
        time.sleep(3)


def _escape_applescript(s):
    """Escape a string so it can be safely inserted into an AppleScript literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def send(edition, reason, dry_run=False):
    if dry_run:
        print("DRY RUN: would send failure email to %s" % TO)
        print("Reason:", reason)
        return True

    ensure_mail_running()

    subject = "Market Wrap Up %s - RUN FAILED" % edition
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    body = """The scheduled %s run failed after 3 retries.

Time: %s

Failure reason:
%s

The report was not published and no PDF was emailed. Manual intervention or a re-run is required.

Regards

Market Wrap Up Scheduler""" % (edition, timestamp, reason.strip())

    script = '''
tell application "Mail"
    set theMessage to make new outgoing message with properties {visible:false}
    tell theMessage
        set subject to "%s"
        set content to "%s"
        make new to recipient at end of to recipients with properties {address:"%s"}
        set sender to "%s"
        save theMessage
        delay 1
        send
    end tell
end tell
''' % (_escape_applescript(subject), _escape_applescript(body), TO, FROM)

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("FAILURE EMAIL ERROR: %s" % result.stderr.strip(), file=sys.stderr)
        return False

    print("FAILURE EMAIL SENT -> %s" % TO)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--edition", required=True)
    parser.add_argument("--reason", default="Unknown error")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if send(args.edition, args.reason, dry_run=args.dry_run) else 1


if __name__ == "__main__":
    sys.exit(main())

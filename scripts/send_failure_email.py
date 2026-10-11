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

    if dry_run:
        print("DRY RUN: would send failure email to %s" % TO)
        print("Reason:", reason)
        return True

    script = '''
tell application "Mail"
    set targetAccount to null
    repeat with acc in accounts
        set accEmails to email addresses of acc
        repeat with addr in accEmails
            if (my lowercased(addr as string)) is (my lowercased("%s")) then
                set targetAccount to acc
                exit repeat
            end if
        end repeat
        if targetAccount is not null then exit repeat
    end repeat

    if targetAccount is null then
        error "No Mail.app account found for %s"
    end if

    set theMessage to make new outgoing message with properties {subject:"%s", content:"%s", visible:false}
    tell theMessage
        make new to recipient at end of to recipients with properties {address:"%s"}
        set sender to "%s"
        send
    end tell
end tell

on lowercased(str)
    set lowerStr to ""
    repeat with ch in str
        set c to ch as string
        set lowerStr to lowerStr & (do shell script "echo " & quoted form of c & " | tr '[:upper:]' '[:lower:]'")
    end repeat
    return lowerStr
end lowercased
''' % (FROM, FROM, subject, body, TO, FROM)

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

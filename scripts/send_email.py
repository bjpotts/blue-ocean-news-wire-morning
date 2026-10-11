#!/usr/bin/env python3
"""Send the Market Wrap Up PDF via Mail.app using the Gmail account.

Mail.app stores the Gmail address as BJPotts@gmail.com, so the AppleScript
matches accounts case-insensitively and then sends from bjpotts@gmail.com.
"""
import argparse
import os
import subprocess
import sys
import time

TO = "bjpotts@gmail.com"
FROM = "bjpotts@gmail.com"
SUBJECT = "Global Market Update"
BODY = """Global Market Update, with your around the world news.

Regards
Regards
Brandon Potts"""


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


def send(pdf, dry_run=False):
    if dry_run:
        print("DRY RUN: would send %s to %s via Mail.app" % (os.path.basename(pdf), TO))
        return True

    ensure_mail_running()

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
        make new attachment with properties {file name:"%s"} at after last paragraph
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
''' % (FROM, FROM, SUBJECT, BODY, TO, FROM, pdf)

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("EMAIL ERROR: %s" % result.stderr.strip(), file=sys.stderr)
        return False

    print("EMAIL SENT: %s -> %s" % (os.path.basename(pdf), TO))
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", nargs="?", help="Path to PDF")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.pdf:
        pdf = args.pdf
    else:
        project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pdfs = sorted(
            p for p in os.listdir(project)
            if p.startswith("market-wrap-up-") and p.endswith(".pdf")
        )
        if not pdfs:
            print("ERROR: no market-wrap-up PDF found", file=sys.stderr)
            return 1
        pdf = os.path.join(project, pdfs[-1])

    return 0 if send(pdf, dry_run=args.dry_run) else 1


if __name__ == "__main__":
    sys.exit(main())

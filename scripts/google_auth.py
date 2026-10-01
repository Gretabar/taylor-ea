"""Taylor's one Google consent. Writes state/google-token.json. Run once, by Taylor, as Taylor.

PORTED FROM STEVIE's scripts/marketing_report/google_auth.py: the installed-app flow
against the existing OAuth client, idempotent when a usable token already exists.
What changed: paths from EA_ROOT/state/ only (no user profile path); the account
comes from context/identity.json and is passed as a login hint so the browser
offers the right Google account; the granted scopes are checked AFTER consent,
because Google's granular-consent screen lets a person untick a box, and a token
missing Calendar would otherwise be discovered weeks later as a silent 403.

    python scripts/google_auth.py                      Docs + Calendar (read only)
    python scripts/google_auth.py --with-gmail-compose  also gmail.compose (decision D-2)
    python scripts/google_auth.py --check              no browser: what is granted, does it refresh

Mike's prerequisites, which fail silently if wrong: the Docs API and the Calendar API
enabled on GCP project bigquery-487308, and the OAuth consent screen set to Internal
(or Taylor added as a test user, accepting that Testing-mode tokens die in 7 days).
state/google-client.json is placed by hand; it never travels in the kit or in git.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import google_creds  # noqa: E402

IDENTITY = google_creds.REPO_ROOT / "context" / "identity.json"


def _account() -> str:
    try:
        return str(json.loads(IDENTITY.read_bytes().decode("utf-8")).get("google_account") or "")
    except (OSError, ValueError):
        return ""  # swallow: the hint is a convenience; the consent still works without it


def _write_token(creds, path: Path) -> None:
    """Atomic write of the durable fields only. The client id and secret stay in their own file."""
    data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "scopes": sorted(creds.granted_scopes or creds.scopes or []),
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".google-token.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    os.replace(tmp, path)


def check(scopes: list[str]) -> int:
    try:
        granted = google_creds.granted_scopes()
    except google_creds.CredentialsError as exc:
        print(f"NO TOKEN: {exc}")
        return 1
    print("granted scopes:")
    for scope in sorted(granted):
        print(f"  {scope}")
    missing = [s for s in scopes if s not in granted]
    if missing:
        print("MISSING for Phase 1: " + ", ".join(missing))
    try:
        google_creds.load_credentials([s for s in scopes if s in granted] or [google_creds.DOCUMENTS])
        print("refresh: OK")
    except google_creds.CredentialsError as exc:
        print(f"refresh: FAILED -- {exc}")
        return 1
    return 1 if missing else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--with-gmail-compose", action="store_true", help="also request gmail.compose (D-2)")
    parser.add_argument("--check", action="store_true", help="report, open no browser")
    args = parser.parse_args()

    scopes = list(google_creds.PHASE1_SCOPES)
    if args.with_gmail_compose:
        scopes.append(google_creds.GMAIL_COMPOSE)

    if args.check:
        return check(scopes)

    try:
        granted = google_creds.granted_scopes()
        if all(s in granted for s in scopes):
            google_creds.load_credentials(scopes)
            print(f"A usable token with every required scope already exists: {google_creds.TOKEN_PATH}")
            return 0
    except google_creds.CredentialsError as exc:
        print(f"No usable token yet ({exc}); starting the consent.")

    try:
        google_creds.client_config()
    except google_creds.CredentialsError as exc:
        print(f"Cannot start: {exc}. Mike places state/google-client.json by hand.", file=sys.stderr)
        return 1

    from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: PLC0415

    account = _account()
    print(f"Opening a browser for Google consent. Sign in as {account or 'the owner'} and click Allow."
          f" Leave every box ticked.")
    flow = InstalledAppFlow.from_client_secrets_file(str(google_creds.CLIENT_PATH), scopes)
    creds = flow.run_local_server(
        port=0, prompt="consent", login_hint=account or None,
        authorization_prompt_message="Visit this URL to authorise: {url}",
        success_message="Done. You can close this tab and go back to VS Code.")
    _write_token(creds, google_creds.TOKEN_PATH)
    granted = sorted(creds.granted_scopes or creds.scopes or [])
    missing = [s for s in scopes if s not in granted]
    print(f"Wrote {google_creds.TOKEN_PATH}")
    if missing:
        print("WARNING: these scopes were NOT granted (a box was unticked): " + ", ".join(missing))
        print("Run this again and leave every box ticked.")
        return 1
    print("Every required scope was granted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

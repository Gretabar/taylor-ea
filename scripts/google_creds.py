"""Load Google credentials for this system, from EA_ROOT/state/ and nowhere else.

PORTED FROM STEVIE's upload_to_drive.load_credentials (stitch the token with the
OAuth client, refresh) and scripts/marketing_report/google_auth.py (the scope check).
What changed: one load_credentials(scopes) for every script; paths from
EA_ROOT/state/ only, so no user profile path appears anywhere; both token shapes
accepted, because a token written by other tooling can be a hand-rolled hybrid and
a fresh consent writes the authorized-user shape.

TWO FILES, NEITHER IN GIT, NEITHER IN THE KIT:
    state/google-client.json   the installed-app OAuth client (Greta's GCP project
                               bigquery-487308), placed by hand by Mike
    state/google-token.json    what Taylor's one consent minted (google_auth.py)

SCOPES ARE CHECKED BEFORE ANY NETWORK CALL. A token without a scope a script needs
does not "mostly work": the API answers 403 insufficient scopes at the worst moment,
or a granular-consent screen let Taylor untick Calendar without anyone noticing. So
a missing scope is a ScopeMissing raised here, naming the scope and the fix.

THE TOKEN IS REFRESHED ON EVERY LOAD AND NEVER WRITTEN BACK. One token call per
process is cheap; writing the file back from several processes (a session and the
scheduled tick) is a race, and a narrowed access token written back would starve
the next caller that needs a different scope. The refresh token is the durable
credential and it is only ever written by google_auth.py.

A refresh that fails is a CredentialsError with the likely cause: a consent screen
in Testing mode kills refresh tokens after 7 days ("it broke after a week").
"""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(os.environ.get("EA_ROOT") or Path(__file__).resolve().parents[1])
STATE = REPO_ROOT / "state"
CLIENT_PATH = STATE / "google-client.json"
TOKEN_PATH = STATE / "google-token.json"

DOCUMENTS = "https://www.googleapis.com/auth/documents"
CALENDAR_READONLY = "https://www.googleapis.com/auth/calendar.readonly"
GMAIL_COMPOSE = "https://www.googleapis.com/auth/gmail.compose"
DRIVE = "https://www.googleapis.com/auth/drive"
DRIVE_FILE = "https://www.googleapis.com/auth/drive.file"

# What Phase 1 needs from Taylor's consent. gmail.compose is D-2 (undecided).
PHASE1_SCOPES = (DOCUMENTS, CALENDAR_READONLY)


class CredentialsError(RuntimeError):
    """The client or token is missing, unreadable, or cannot be refreshed."""


class ScopeMissing(CredentialsError):
    """The token was never granted a scope this call needs."""

    def __init__(self, missing: list[str], granted: list[str]):
        self.missing, self.granted = missing, granted
        super().__init__(
            "the Google token was not granted: " + ", ".join(missing)
            + ". Granted: " + (", ".join(sorted(granted)) or "nothing")
            + ". Fix: python scripts/google_auth.py (one consent, signed in as Taylor),"
            + " and leave every box ticked on the consent screen.")


def _read_json(path: Path, label: str) -> dict:
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except FileNotFoundError as exc:
        raise CredentialsError(f"{label} is missing at {path}") from exc
    except (OSError, ValueError) as exc:
        raise CredentialsError(f"{label} at {path} is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise CredentialsError(f"{label} at {path} is not a JSON object")
    return data


def client_config() -> dict:
    """The installed (or web) block of the OAuth client file."""
    data = _read_json(CLIENT_PATH, "the OAuth client (state/google-client.json)")
    block = data.get("installed") or data.get("web") or (data if "client_id" in data else None)
    if not block or not block.get("client_id") or not block.get("client_secret"):
        raise CredentialsError("state/google-client.json has no installed client with an id and secret")
    return block


def token_data() -> dict:
    return _read_json(TOKEN_PATH, "the Google token (state/google-token.json)")


def granted_scopes(token: dict | None = None) -> list[str]:
    """Scopes the token says it was granted, from either token shape. No network."""
    data = token if token is not None else token_data()
    raw = data.get("scopes") or data.get("scope") or []
    return raw.split() if isinstance(raw, str) else [str(s) for s in raw]


def load_credentials(scopes: list[str] | tuple[str, ...]):
    """Credentials for exactly `scopes`, refreshed now, or a CredentialsError naming why not."""
    from google.auth.exceptions import RefreshError, TransportError  # noqa: PLC0415
    from google.auth.transport.requests import Request  # noqa: PLC0415
    from google.oauth2.credentials import Credentials  # noqa: PLC0415

    client = client_config()
    token = token_data()
    granted = granted_scopes(token)
    missing = [s for s in scopes if s not in granted]
    if missing:
        raise ScopeMissing(missing, granted)
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise CredentialsError("state/google-token.json carries no refresh_token; run "
                               "python scripts/google_auth.py")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=client.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=client["client_id"],
        client_secret=client["client_secret"],
        scopes=list(scopes),
    )
    try:
        creds.refresh(Request())
    except RefreshError as exc:
        raise CredentialsError(
            f"the token could not be refreshed ({exc}). It was revoked, or the consent screen is "
            f"in Testing mode, where refresh tokens die after 7 days. Mike: set the consent screen "
            f"to Internal, then Taylor runs python scripts/google_auth.py once.") from exc
    except TransportError as exc:
        raise CredentialsError(f"could not reach Google to refresh the token ({exc}); offline?") from exc
    return creds


def service(api: str, version: str, scopes: list[str] | tuple[str, ...]):
    """A googleapiclient service for `api`, built from the bundled discovery document."""
    from googleapiclient.discovery import build  # noqa: PLC0415

    return build(api, version, credentials=load_credentials(scopes), cache_discovery=False)

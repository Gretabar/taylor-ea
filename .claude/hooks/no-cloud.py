"""PreToolUse (Bash|Write|Edit): nothing leaves this machine by accident.

PORTED FROM PIPER unchanged in logic. Messages re-pointed at this system; the
allowlist is context/systems.json, which here names only the Google hosts Phase 1
reaches. OneDrive Known Folder Move is a real risk on Taylor's corporate laptop, as
it is on any corporate laptop that uses it: a repo under Documents would sync the
register and the OAuth token to the tenant cloud without anybody deciding that.

Three separate refusals, one hook, because they answer the same question from
three directions.

1. PUSH AND SYNC COMMANDS. `git push`, `gh`, `aws`, `az`, `gcloud`, `rclone`,
   `scp`, `sftp`, `bitsadmin`, `azcopy`. Matched on the first token of each
   command in the line, not anywhere in the text, so a path named
   `state/records/gh-notes/` is not a finding.

2. NETWORK CALLS OFF THE ALLOWLIST. `curl`, `wget`, `Invoke-RestMethod`,
   `Invoke-WebRequest` and their aliases. Every URL in the command must resolve
   to a host in context/systems.json. A network tool this gate cannot resolve a
   destination for is blocked too: an unreadable destination is not a safe one.

3. WRITES INTO A SYNC ROOT. This is the one worth staking something on.
   Taylor's machine is corporate Windows, where OneDrive Known Folder Move
   redirects Documents and Desktop by default. A repo under Documents silently
   syncs state/ea.db and state/google-token.json to the tenant cloud, and nobody
   made that decision. Hence a repo at the root of C:, checked by ea_doctor.py at
   install and enforced here on every write.

SYNC ROOTS ARE DISCOVERED, NOT HARDCODED. No username appears anywhere below.
Sources, cheapest first: the OneDrive environment variables the client sets; the
per-account UserFolder values under HKCU\\Software\\Microsoft\\OneDrive\\Accounts;
Dropbox's own info.json; Google Drive's DriveFS mount; the well-known folder
names directly under the profile; and finally the Win32 drive type, which is how
a mapped network drive is caught without knowing what it is mapped to.

FAILS CLOSED. An unreadable payload or an unreadable systems.json blocks. A gate
whose allowlist failed to load has no allowlist.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from _failsafe import run_gate  # noqa: E402  -- standard library only, so it loads when the rest cannot

# A failed import must end in a refusal, never in Python's own exit 1, which lets the call through.
try:
    import _audit  # noqa: E402
    from _gate import (  # noqa: E402
        ContextUnreadable,
        PayloadUnreadable,
        block,
        deny_environment,
        first_field,
        load_context,
        norm_path,
        read_payload,
        resolve_agent,
    )
except BaseException as _exc:  # noqa: BLE001  -- SystemExit and KeyboardInterrupt at import refuse too
    _IMPORT_ERROR: BaseException | None = _exc  # swallow: run_gate refuses every call, naming this error
else:
    _IMPORT_ERROR = None

HOOK = "no-cloud"

# First-token commands that move bytes off the machine.
BLOCKED_FIRST_TOKENS = {
    "gh": "the GitHub CLI",
    "aws": "the AWS CLI",
    "az": "the Azure CLI",
    "gcloud": "the Google Cloud CLI",
    "rclone": "rclone",
    "scp": "scp",
    "sftp": "sftp",
    "bitsadmin": "bitsadmin",
    "azcopy": "azcopy",
}

NETWORK_TOOLS = {
    "curl", "wget", "httpie", "http",
    "invoke-restmethod", "invoke-webrequest", "irm", "iwr",
}

# Splits a shell line into the commands inside it. Deliberately crude: this is a
# gate, not a parser, and every fragment gets checked rather than only the first.
SEPARATORS = re.compile(r"(?:\|\||&&|;|\||\n|`|\$\()")
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
URL = re.compile(r"https?://[^\s'\"`)\\]+", re.I)

WELL_KNOWN_SYNC_DIRS = (
    "onedrive", "dropbox", "google drive", "googledrive", "my drive",
    "icloud drive", "iclouddrive", "box", "box sync",
    "creative cloud files", "nextcloud", "sync.com",
)

DRIVE_REMOTE = 4


def _reg_onedrive_folders() -> list[str]:
    """UserFolder for every OneDrive account registered for this user."""
    folders: list[str] = []
    if os.name != "nt":
        return folders
    try:
        import winreg  # noqa: PLC0415

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\OneDrive\Accounts") as accounts:
            index = 0
            while True:
                try:
                    account = winreg.EnumKey(accounts, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(accounts, account) as key:
                        value, _ = winreg.QueryValueEx(key, "UserFolder")
                        if value:
                            folders.append(str(value))
                except OSError:
                    continue  # swallow: one account without a UserFolder is normal
    except OSError:
        pass  # swallow: no OneDrive key at all means no OneDrive accounts
    return folders


def _dropbox_folders() -> list[str]:
    """Paths out of Dropbox's own info.json, for personal and business accounts."""
    folders: list[str] = []
    for env in ("LOCALAPPDATA", "APPDATA"):
        root = os.environ.get(env)
        if not root:
            continue
        info = Path(root) / "Dropbox" / "info.json"
        try:
            data = json.loads(info.read_bytes().decode("utf-8", errors="replace"))
        except (OSError, ValueError):
            continue  # swallow: no Dropbox installed, or a shape we do not know
        if isinstance(data, dict):
            for account in data.values():
                if isinstance(account, dict) and account.get("path"):
                    folders.append(str(account["path"]))
    return folders


def _google_drive_folders() -> list[str]:
    """Google Drive for desktop mount points, from the registry and the profile."""
    folders: list[str] = []
    if os.name == "nt":
        try:
            import winreg  # noqa: PLC0415

            for hive, path in (
                (winreg.HKEY_CURRENT_USER, r"Software\Google\DriveFS"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\DriveFS"),
            ):
                try:
                    with winreg.OpenKey(hive, path) as key:
                        for name in ("DefaultMountPoint", "MountPoint", "Mount"):
                            try:
                                value, _ = winreg.QueryValueEx(key, name)
                            except OSError:
                                continue
                            if value:
                                folders.append(str(value))
                except OSError:
                    continue  # swallow: Drive for desktop is simply not installed
        except ImportError:
            pass  # swallow: not Windows
    return folders


def _profile_sync_dirs() -> list[str]:
    """Well-known sync folders directly under the user profile, by name."""
    folders: list[str] = []
    profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    try:
        entries = list(Path(profile).iterdir())
    except OSError:
        return folders
    for entry in entries:
        if not entry.is_dir():
            continue
        lowered = entry.name.lower()
        if any(lowered.startswith(known) for known in WELL_KNOWN_SYNC_DIRS):
            folders.append(str(entry))
    return folders


def sync_roots() -> list[str]:
    """Every directory on this machine that syncs to somebody's cloud."""
    raw: list[str] = []
    for key in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        value = os.environ.get(key)
        if value:
            raw.append(value)
    raw += _reg_onedrive_folders()
    raw += _dropbox_folders()
    raw += _google_drive_folders()
    raw += _profile_sync_dirs()

    seen: dict[str, str] = {}
    for path in raw:
        normalised = norm_path(path)
        if normalised and normalised not in seen:
            seen[normalised] = path
    return list(seen)


def is_remote_drive(path: str) -> bool:
    """True for a UNC path or a mapped network drive letter."""
    if path.startswith("\\\\") or path.startswith("//"):
        return True
    if os.name != "nt":
        return False
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    if not drive or not drive.endswith(":"):
        return False
    try:
        import ctypes  # noqa: PLC0415

        return int(ctypes.windll.kernel32.GetDriveTypeW(drive + "\\")) == DRIVE_REMOTE
    except (OSError, AttributeError, ValueError):
        return False  # swallow: cannot ask the OS, so do not invent an answer here


def classify_path(path: str, roots: list[str] | None = None) -> str | None:
    """The reason this path may not be written, or None when it is fine."""
    if not path:
        return None
    if is_remote_drive(path):
        return "it resolves onto a mapped network drive or a UNC share"
    target = norm_path(path)
    for root in roots if roots is not None else sync_roots():
        if target == root or target.startswith(root.rstrip(os.sep) + os.sep):
            return f"it resolves inside a cloud-synced folder ({root})"
    return None


def commands_in(line: str) -> list[list[str]]:
    """Token lists for each command in a shell line, env assignments stripped."""
    commands: list[list[str]] = []
    for fragment in SEPARATORS.split(line):
        tokens = fragment.strip().split()
        # Env assignments (bash) and call operators (PowerShell `& git push`,
        # cmd `call`) sit in front of the real command and would hide it.
        while tokens and (ENV_ASSIGNMENT.match(tokens[0]) or tokens[0] in ("&", ".", "call")):
            tokens = tokens[1:]
        if tokens:
            commands.append(tokens)
    return commands


def _first_token(tokens: list[str]) -> str:
    return Path(tokens[0].strip("'\"")).name.lower().removesuffix(".exe")


def host_allowed(host: str, allowlist: list[str]) -> bool:
    """Exact host, or a subdomain of an allowlisted host."""
    host = (host or "").lower().split(":")[0]
    if not host:
        return False
    return any(host == entry.lower() or host.endswith("." + entry.lower())
               for entry in allowlist)


def classify_command(line: str, allowlist: list[str]) -> tuple[str, str] | None:
    """(rule_id, reason) for the first refusal in this command line, or None."""
    for tokens in commands_in(line):
        head = _first_token(tokens)

        if head == "git" and len(tokens) > 1 and tokens[1].lower() == "push":
            return "push-command", "`git push` sends this repository somewhere else"

        if head in BLOCKED_FIRST_TOKENS:
            return "push-command", f"{BLOCKED_FIRST_TOKENS[head]} moves data off this machine"

        if head in NETWORK_TOOLS:
            urls = URL.findall(line)
            if not urls:
                return (
                    "unresolvable-destination",
                    f"`{head}` was called and this gate could not resolve a destination "
                    f"from the command, so it cannot tell where the bytes would go",
                )
            for url in urls:
                host = urlsplit(url).hostname or ""
                if not host_allowed(host, allowlist):
                    return "host-off-allowlist", f"{host} is not in context/systems.json"
    return None


def deny_command(rule_id: str, reason: str, allowlist: list[str]) -> int:
    lines = [
        "BLOCKED: this machine does not send its records anywhere.",
        "",
        f"  reason: {reason}",
        "",
    ]
    if rule_id == "push-command":
        lines += [
            "This system is local-only by design. Code changes happen on Mike's",
            "machine and arrive as a kit. This repository is not pushed from here and",
            "the state directory never leaves the disk it was written on.",
        ]
    else:
        lines += [
            "Every host this system may reach is named in context/systems.json, with a",
            "verified flag. Hosts that have not been confirmed against the live",
            "system are deliberately absent, so reaching one is denied until",
            "somebody checks it.",
            "",
            "  allowed: " + ", ".join(allowlist[:8]) + (" ..." if len(allowlist) > 8 else ""),
        ]
    lines += [
        "",
        "REPHRASING WILL NOT CHANGE THIS. If the destination is legitimate, add it",
        "to context/systems.json with evidence that it is the right host, and say",
        "so to Mike. Do not route around the gate.",
    ]
    return block(lines)


def deny_write(path: str, reason: str) -> int:
    return block([
        "BLOCKED: that path is cloud-synced.",
        "",
        f"  file:   {path}",
        f"  reason: {reason}",
        "",
        "OneDrive Known Folder Move redirects Documents and Desktop by default on a",
        "corporate Windows build. A file written there is copied to the tenant cloud",
        "within seconds, and nobody decides that -- it just happens. The register and",
        "the OAuth token are exactly the content that must not make that trip.",
        "",
        "Write it under the repository at its own root instead. If the repository",
        "itself is inside a synced folder, stop and move it: run",
        "`python scripts/ea_doctor.py`, which checks this at install time.",
        "",
        "REPHRASING WILL NOT CHANGE THIS. It is a path check.",
    ])


def main() -> int:
    try:
        payload = read_payload()
    except PayloadUnreadable as exc:
        _audit.record(hook=HOOK, decision="deny_unverifiable", detail=str(exc))
        return deny_environment(HOOK, "hook payload", str(exc))

    try:
        systems = load_context("systems")
    except ContextUnreadable as exc:
        _audit.record(hook=HOOK, decision="deny_unverifiable", detail=str(exc))
        return deny_environment(HOOK, "systems allowlist", str(exc))

    allowlist = list(((systems.get("host_allowlist") or {}).get("network")) or [])
    tool = str(payload.get("tool_name") or "")
    agent = resolve_agent(payload) or ""
    session = str(payload.get("session_id") or "")

    command = first_field(payload, "command")
    if command:
        finding = classify_command(command, allowlist)
        if finding:
            rule_id, reason = finding
            _audit.record(hook=HOOK, tool=tool, agent=agent, decision="deny",
                          rule_id=rule_id, target=command[:200], detail=reason,
                          session_id=session)
            return deny_command(rule_id, reason, allowlist)
        return 0

    file_path = first_field(payload, "file_path")
    if file_path:
        reason = classify_path(file_path)
        if reason:
            _audit.record(hook=HOOK, tool=tool, agent=agent, decision="deny",
                          rule_id="cloud-synced-path", target=file_path,
                          detail=reason, session_id=session)
            return deny_write(file_path, reason)
    return 0


if __name__ == "__main__":
    sys.exit(run_gate(HOOK, main, _IMPORT_ERROR))

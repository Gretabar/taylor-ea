"""
The month-end run ledger: which months have been delivered, and how they went.

Both month-end jobs keep one of these (product mix in
output/data/lightspeed-category/runs.json, games in output/data/intercard/runs.json)
and both read it to answer the only question that matters unattended: has this
month already been delivered? `--if-not-done` trusts the answer completely, so a
LOST entry is not a cosmetic bookkeeping problem -- it is a second Gmail draft to
thirteen people, built and addressed by a scheduled task with no human in the
loop to notice.

WHY THIS IS A SHARED MODULE AND NOT A METHOD ON EACH JOB. It used to be six
identical lines in each of product_mix_monthly.py and games_monthly.py:
load the file, set one key, write the whole thing back. That is a textbook
lost update, and on the night of 2026-09-01 it lost one for real. The games run
at 23:16 recorded 2026-08 "ok"; a run for 2026-07 at 00:09:38 loaded the ledger,
set its own key and wrote back a copy that had never contained August. The August
entry did not become wrong, it ceased to exist, and the next --if-not-done pass
would have rebuilt a month that was already sitting in a finished draft.
scripts/ig_review_run.py keeps a third ledger with the same race and has NOT been
migrated here yet.

ATOMIC REPLACE ALONE IS NOT ENOUGH, and it is worth being precise about why,
because it is the intuitive fix and it does not work. os.replace makes the write
indivisible: no reader ever sees a half-written ledger, and a crash mid-write
leaves the previous ledger intact rather than a truncated file that parses as {}
and makes every month look undone. What it does not do is make read-modify-write
indivisible. Two writers can both read the same "before" state, and whichever
replaces second still writes a document that never contained the other's entry --
atomically. ig_review_run.py's record_run already does tmp-write-then-replace and
its docstring already calls that "atomic write"; it has the same lost update.

So the read, the modify and the write all happen while holding an exclusive OS
lock on a sibling .lock file, and the read happens INSIDE the lock so a writer
that waited sees the winner's entry before adding its own.

WHY A SIDECAR LOCK FILE RATHER THAN LOCKING runs.json ITSELF. Windows will not
let you replace a file another handle has open, so locking the ledger directly
and then replacing it are mutually exclusive. Locking a separate byte in a
separate file costs one inode and keeps os.replace available.

WHY AN OS LOCK RATHER THAN AN O_EXCL SENTINEL. A sentinel file left behind by a
killed process is a deadlock, which then needs a staleness timeout, which is a
heuristic that can break a live lock held by a slow writer. An OS byte-range
lock is released by the kernel when the handle closes, including when the process
dies -- verified on this machine for both msvcrt (Windows) and a second process.

WHAT HAPPENS IF THE LOCK CANNOT BE TAKEN. update() waits LOCK_TIMEOUT seconds and
then writes ANYWAY, loudly, marking the entry. That is deliberate and it is the
less bad of two bad options. Raising instead would abort a month that was already
delivered, the wrapper would alarm, the scheduler would retry tomorrow, and
--if-not-done would find no entry and rebuild -- which is precisely the duplicate
draft this module exists to prevent. A missing entry is the dangerous state; a
raced entry is merely a wrong one, and it says so in its own detail field.
"""

import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

# Generous because contention is not supposed to happen: two monthly jobs holding
# this lock for the milliseconds a small JSON write takes will never queue for
# thirty seconds unless something is genuinely wedged.
LOCK_TIMEOUT = 30.0
LOCK_POLL = 0.05
REPLACE_RETRIES = 5
REPLACE_POLL = 0.1

UNLOCKED_MARK = (" | WARNING: wrote this entry WITHOUT the runs.json lock after "
                 "waiting {t:.0f}s - another writer may have been mid-update, so "
                 "an adjacent month's entry could have been lost")

# try_lock/unlock are public because scripts/job_lock.py takes the SAME kind of
# lock for a whole run and must not carry a second copy of this platform branch:
# two implementations of a lock primitive is how one of them ends up subtly wrong
# on one OS and nobody finds out until two runs overlap.
if os.name == "nt":
    import msvcrt

    def try_lock(fd):
        """True if the exclusive lock was taken, False if someone else holds it."""
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def unlock(fd):
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def try_lock(fd):
        """True if the exclusive lock was taken, False if someone else holds it."""
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def unlock(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)


def lock_path(path):
    """Sibling of the ledger, not the ledger itself. See the module header."""
    return Path(str(path) + ".lock")


def load(path):
    """Read the ledger. Never raises: an unreadable ledger must not stop a run.

    Returns {} for absent or unparseable, which reads downstream as "no month has
    been done" -- the direction that redoes work rather than skipping it. That is
    the safer default for a corrupt file but it is NOT free (a redone month is a
    duplicate draft), so it says so on stderr rather than passing quietly.
    """
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        print(f"WARNING: {path} is unreadable ({exc}); treating every month as "
              f"not yet done", file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        print(f"WARNING: {path} is not a JSON object; treating every month as "
              f"not yet done", file=sys.stderr)
        return {}
    return data


def update(path, month, status, detail, at=None):
    """Merge one month's entry into the ledger under an exclusive lock.

    The entry schema lives here rather than in each job so the two ledgers cannot
    drift into meaning different things by the same key names.

    Returns the merged ledger as written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(lock_path(path), os.O_CREAT | os.O_RDWR)
    locked, waited = _acquire(fd)
    try:
        if not locked:
            detail += UNLOCKED_MARK.format(t=waited)
            print(f"WARNING: could not lock {lock_path(path)} after {waited:.0f}s; "
                  f"writing {month} unlocked rather than losing the entry",
                  file=sys.stderr)
        runs = load(path)          # inside the lock: see the module header
        runs[month] = {
            "status": status,
            "detail": detail,
            "at": (at or datetime.now().astimezone()).isoformat(timespec="seconds"),
        }
        _write(path, runs)
        return runs
    finally:
        if locked:
            unlock(fd)
        os.close(fd)


def _acquire(fd):
    """Poll for the lock up to LOCK_TIMEOUT. Returns (got_it, seconds_waited)."""
    started = time.monotonic()
    while True:
        if try_lock(fd):
            return True, time.monotonic() - started
        if time.monotonic() - started >= LOCK_TIMEOUT:
            return False, time.monotonic() - started
        time.sleep(LOCK_POLL)


def _write(path, runs):
    """Serialise to a sibling temp file, fsync, then os.replace over the ledger.

    Same directory so the replace stays on one volume and therefore atomic. The
    retry loop is for Windows specifically: os.replace fails with PermissionError
    while any other handle has the destination open (an editor, a backup agent,
    a virus scanner mid-scan), and that is transient. If it is still failing after
    a second, the exception is the honest outcome -- the caller crashing loudly
    beats it believing the entry landed.
    """
    text = json.dumps(runs, indent=2, sort_keys=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        for attempt in range(REPLACE_RETRIES):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == REPLACE_RETRIES - 1:
                    raise
                time.sleep(REPLACE_POLL)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise

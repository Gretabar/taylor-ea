"""
One run of a scheduled job at a time, for the whole length of the run.

WHY runs_log's LOCK IS NOT THIS LOCK, even though it is the same primitive.
runs_log holds its lock for the milliseconds a small JSON write takes, and it
protects a LEDGER. This protects the DECISION MADE FROM THE LEDGER, which is a
different window and a much longer one: a job that reads "not done yet" at the
START of a run and records the result at the END, minutes or hours later, can
overlap with a second invocation that reads the same "not done yet" and does the
same work again. Every entry written in that sequence is correct and serialised;
the ledger is intact; the work still happened twice. Locking a decision means
holding the lock across the act the decision authorises, so the lock is taken in
main() before the ledger is read and released after the last result is recorded.

REFUSING TO START IS NOT A FAILURE. A second invocation that finds the job
already running has nothing to do: the first one is doing it. So hold() raises
AlreadyRunning, the callers print it, send a WARN, and exit 0 -- no red
LastTaskResult, no wrapper alarm, no retry, and no second run. An expected
condition with nothing wrong in it is reported rather than alarmed. It is an
exception and not a False return because a caller who forgets to check a return
value silently does the work twice, which is the whole failure this module exists
to prevent, while a caller who forgets to catch crashes loudly and does nothing.

A CRASHED RUN MUST NOT WEDGE THE JOB FOREVER. Same reasoning as runs_log: an
O_EXCL sentinel file left behind by a killed process is a deadlock, which then
needs a staleness timeout, which is a heuristic that eventually breaks a live
lock held by a slow run. The kernel releases a byte-range lock when the handle
closes, including when the process is killed, so a crash clears this lock with no
timeout to tune and nothing to sweep up. The lock file itself is left on disk on
purpose -- it is a mutex, not a sentinel, and an empty one means nothing.

THERE IS NO TIMEOUT AND NO WAITING, and that is what makes a genuinely long run
safe. Nothing here inspects how long the lock has been held, so a two-hour hold
is indistinguishable from a two-second one and neither can be declared stale. hold() takes the lock or refuses immediately. It never
queues, because a waiter would eventually acquire the lock and then do exactly
the duplicate work it waited for.

The holder note (pid and start time) is written at offset 1, past the byte the
lock covers, so a refused run can name what is holding it. Reading it is best
effort: it decides nothing, it only makes the refusal message useful to a human
deciding between "two runs overlapped" and "something is wedged".
"""

import os
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import runs_log  # noqa: E402

# Byte 0 is the lock itself. On Windows a byte-range lock is mandatory, so the
# note has to live somewhere another process can still read.
NOTE_OFFSET = 1
NOTE_MAX = 200


class AlreadyRunning(RuntimeError):
    """Another process holds this job's lock. Not an error condition - see above."""


@contextmanager
def hold(path, label=None):
    """Hold `path` exclusively for the duration of the block.

    Raises AlreadyRunning immediately if another process holds it. Released by
    the kernel if this process dies without unwinding.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    label = label or path.name
    fd = os.open(path, os.O_CREAT | os.O_RDWR)
    try:
        if not runs_log.try_lock(fd):
            raise AlreadyRunning(
                f"{label} is already running ({holder(path)}) - this invocation is "
                f"doing nothing rather than doing the same work a second time")
        _stamp(fd, label)
        try:
            yield path
        finally:
            runs_log.unlock(fd)
    finally:
        os.close(fd)


def holder(path):
    """Whatever the current holder wrote about itself, or a plain fallback.

    Best effort by design: this string is only ever printed. A stale or
    unreadable note must not change what a refused run does.
    """
    try:
        with open(path, "rb") as fh:
            fh.seek(NOTE_OFFSET)
            note = fh.read(NOTE_MAX).decode("utf-8", "replace")
    except OSError:
        return "holder unknown"
    return note.strip("\x00 \r\n") or "holder unknown"


def _stamp(fd, label):
    """Record who we are, past the locked byte, and drop the previous holder's note."""
    note = (f"{label} pid {os.getpid()} since "
            f"{datetime.now().astimezone().isoformat(timespec='seconds')}"
            ).encode("utf-8")[:NOTE_MAX]
    os.lseek(fd, NOTE_OFFSET, os.SEEK_SET)
    os.write(fd, note)
    os.ftruncate(fd, NOTE_OFFSET + len(note))
    os.lseek(fd, 0, os.SEEK_SET)

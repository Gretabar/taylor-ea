"""Who on the team is switched on, and the exact words a switched-off agent answers with.

NEW in this repo. Thirteen agents, and which of them may run is decided in two
places on purpose, by two different people:

  context/architecture/phases.json   Taylor's phase gate: upstream defaults in the
  + state/taylor/phases.json         tracked file, his own decisions in the overlay
                                     (scripts/overlay.py), which wins. A phase is
                                     approved only when his own message carries the
                                     approval phrase (protect-architecture.py, layer A),
                                     with a CHANGE-LOG bullet in the same turn.
  context/roster-agents.json         Mike's build record: which phases and deviations
                                     are built and accepted. Code layer, so it changes
                                     only in build mode (_health.build_mode).

An agent is ON when one of its routes is both approved and accepted:

  its phase      phases.json approves the phase, the phase is not deferred, AND
                 build_record has it accepted. A deferral is lifted explicitly
                 ("resume Phase 6" sets deferred to false): approving a phase that is
                 still marked deferred keeps its agents off.
  its deviation  deviations.json has the deviation in effect (approved, or still
                 proposed when it says in_effect_while_proposed) AND build_record has
                 that deviation accepted. LARK's read-only prep runs this way (D-3).

ACCEPTED MEANS A DATE. build_record's `accepted` is the ISO date the acceptance passed
(YYYY-MM-DD), or null for not yet. "no", "pending", "false" and "TBD" are all truthy
strings, and reading truthiness switched an agent on with any of them, so any other
value is malformed and the team is unreadable until it is fixed. `deferred`, when
present, is true or false, nothing else.

NAMESPACES. A dispatch names one of ours only as a bare name ("milo") or with this
repo's own prefix ("ea:milo"). Any other prefix ("otherplugin:sage") is somebody
else's agent and is NOT ON THIS TEAM, however its last segment reads.

ONE ANSWER, MANY READERS. The dispatch gate (require-active-agent.py), the announce
banner, the doctor, the contract validator and the orchestrator's relay
(`python scripts/team.py --agent MILO`) all import this module. Five places
computing "is MILO on" would be five answers, and the one Taylor reads would be the
one that drifted.

THE WORDS ARE QUOTED IN TAYLOR'S DOCS. docs/FOR-TAYLOR.md quotes the switched-off
lines word for word, and the guardrail self-test fails if this module and that file
ever disagree. Change both or neither.

UNREADABLE IS NOT "OFF". A missing or malformed file raises TeamUnreadable. The gate
turns that into a refusal that says it is an environment fault; it never guesses.

Usage:
    python scripts/team.py                 the team, and where each agent stands
    python scripts/team.py --agent MILO    exactly what a dispatch to MILO answers
    python scripts/team.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(os.environ.get("EA_ROOT") or Path(__file__).resolve().parents[1])
PHASES = tuple(str(n) for n in range(1, 8))

ACTIVE = "active"
APPROVED_NOT_BUILT = "approved_not_built"
NOT_SWITCHED_ON = "not_switched_on"
OUTSIDE = "outside_architecture"
DEFERRED = "deferred"

STATE_WORDS = {
    ACTIVE: "on",
    APPROVED_NOT_BUILT: "approved, not built yet",
    NOT_SWITCHED_ON: "not switched on yet",
    OUTSIDE: "outside the blueprint",
    DEFERRED: "deferred",
}


class TeamUnreadable(Exception):
    """A roster, phase or deviation file is missing or malformed. Never read as "off"."""


# --------------------------------------------------------------------------
# The words. docs/FOR-TAYLOR.md quotes these; the self-test holds them to it.
# --------------------------------------------------------------------------

def not_switched_on(name: str, lane: str, phase: int) -> tuple[str, str]:
    return (f"NOT SWITCHED ON YET: {name} ({lane}), Phase {phase}.",
            f'To switch it on: say "architecture change ok: switch on Phase {phase}", and Mike builds it.')


def approved_not_built(name: str, lane: str, phase: int | None) -> tuple[str, str]:
    where = f", Phase {phase}" if phase is not None else ""
    return (f"APPROVED, NOT BUILT YET: {name} ({lane}){where}.",
            "Mike is building it; nothing to do on your side.")


def outside_architecture(name: str, lane: str) -> tuple[str, str]:
    return (f"NOT SWITCHED ON: {name} ({lane}) is outside your architecture.",
            f'To switch it on: say "architecture change ok: add {name}", then Mike builds it.')


def deferred(name: str, lane: str, phase: int) -> tuple[str, str]:
    return (f"NOT SWITCHED ON: {name} ({lane}) is Phase {phase}, which you deferred.",
            f'To switch it on: say "architecture change ok: resume Phase {phase}", then Mike builds it.')


def not_on_roster(subagent_type: str) -> tuple[str, str]:
    """For a dispatch to anything that is not one of the thirteen (Explore, general-purpose, a fork)."""
    shown = subagent_type or "general-purpose"
    return (f'NOT ON THIS TEAM: "{shown}" is not one of this system\'s agents.',
            "Send the work to the agent whose lane it is (python scripts/team.py lists them), "
            "or answer from the scripts directly.")


# --------------------------------------------------------------------------
# The decision
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentStatus:
    """One agent's standing. `lines` is empty when it is on, else exactly what it answers."""

    name: str
    lane: str
    phase: int | None
    model: str
    state: str
    route: str
    lines: tuple[str, ...]

    @property
    def active(self) -> bool:
        return self.state == ACTIVE


PLUGIN = "ea"


def bare(subagent_type: str) -> str:
    """'milo' or 'ea:milo' -> 'MILO'. Any other prefix -> '': somebody else's agent, never ours.

    The same rule as .claude/hooks/_gate.agent_name(); the guardrail self-test holds
    the two to one table of inputs.
    """
    text = (subagent_type or "").strip()
    prefix, sep, name = text.partition(":")
    if sep:
        if prefix.strip().lower() != PLUGIN or ":" in name:
            return ""
        text = name
    return text.strip().upper()


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def is_iso_date(value) -> bool:
    """True for a real calendar date written YYYY-MM-DD, and nothing else."""
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


class Team:
    """The roster, Taylor's phase gate and the deviation register, validated together."""

    def __init__(self, roster: dict, phases: dict, deviations: dict):
        self.agents = self._agents(roster)
        self.builds = self._builds(roster)
        self.phases = self._phases(phases)
        self.deviations = deviations.get("deviations") if isinstance(deviations, dict) else None
        if not isinstance(self.deviations, dict):
            raise TeamUnreadable("deviations.json has no `deviations` object")
        for agent in self.agents.values():
            via = agent.get("via")
            if via is not None and via not in self.deviations:
                raise TeamUnreadable(f"{agent['name']} is switched on via {via}, which deviations.json does not define")

    @staticmethod
    def _agents(roster: dict) -> dict[str, dict]:
        agents = roster.get("agents") if isinstance(roster, dict) else None
        if not isinstance(agents, list) or not agents:
            raise TeamUnreadable("roster-agents.json lists no agents")
        found: dict[str, dict] = {}
        for agent in agents:
            if not isinstance(agent, dict):
                raise TeamUnreadable("roster-agents.json holds an agent that is not an object")
            name = str(agent.get("name") or "").strip().upper()
            lane = str(agent.get("lane") or "").strip()
            phase = agent.get("phase")
            if not name or not lane:
                raise TeamUnreadable(f"roster agent {name or '?'} has no name or no lane")
            if name in found:
                raise TeamUnreadable(f"roster-agents.json lists {name} twice")
            for flag in ("delivery", "privacy", "read_only", "lessons"):
                if flag in agent and not isinstance(agent[flag], bool):
                    raise TeamUnreadable(f"{name} has {flag} {agent[flag]!r}; it must be true or false")
            if phase is None:
                if not agent.get("via"):
                    raise TeamUnreadable(f"{name} has no phase and no deviation that could switch it on")
            elif not isinstance(phase, int) or str(phase) not in PHASES:
                raise TeamUnreadable(f"{name} has phase {phase!r}; the blueprint has phases 1 to 7")
            found[name] = {**agent, "name": name, "lane": lane}
        return found

    @staticmethod
    def _builds(roster: dict) -> dict[str, dict]:
        record = roster.get("build_record", {})
        if not isinstance(record, dict):
            raise TeamUnreadable("roster-agents.json build_record is not an object")
        builds = {key: value for key, value in record.items() if isinstance(value, dict)}
        for key, value in builds.items():
            accepted = value.get("accepted")
            if accepted is not None and not is_iso_date(accepted):
                raise TeamUnreadable(f"build_record {key!r} has accepted {accepted!r}; it must be the date the "
                                     f"acceptance passed (YYYY-MM-DD), or null for not yet")
        return builds

    @staticmethod
    def _phases(phases: dict) -> dict[str, dict]:
        table = phases.get("phases") if isinstance(phases, dict) else None
        if not isinstance(table, dict):
            raise TeamUnreadable("phases.json has no `phases` object")
        for key in PHASES:
            entry = table.get(key)
            if not isinstance(entry, dict) or not isinstance(entry.get("approved"), bool):
                raise TeamUnreadable(f"phases.json has no true-or-false `approved` for phase {key}")
            if "deferred" in entry and not isinstance(entry["deferred"], bool):
                raise TeamUnreadable(f"phases.json phase {key} has deferred {entry['deferred']!r}; "
                                     f"it must be true or false")
        return table

    # -- the two halves ---------------------------------------------------------

    def accepted(self, unit: str) -> bool:
        """Built and accepted on the build machine: an ISO date in build_record, never just a truthy value."""
        return is_iso_date((self.builds.get(unit) or {}).get("accepted"))

    def phase_deferred(self, phase: int | None) -> bool:
        return phase is not None and self.phases[str(phase)].get("deferred") is True

    def phase_approved(self, phase: int | None) -> bool:
        """Taylor approved the phase AND it is not deferred: approval alone does not lift a deferral."""
        return (phase is not None and self.phases[str(phase)]["approved"] is True
                and not self.phase_deferred(phase))

    def deviation_in_effect(self, key: str | None) -> bool:
        entry = self.deviations.get(key) if key else None
        if not isinstance(entry, dict):
            return False
        status = str(entry.get("status") or "")
        if status == "approved":
            return True
        return status in ("proposed", "undecided") and entry.get("in_effect_while_proposed") is True

    # -- answers ------------------------------------------------------------------

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.agents)

    def dormant_lines(self, name: str) -> tuple[str, str]:
        """What the agent answers while nothing is approved for it. Stable, so agent files can quote it."""
        agent = self.agents[bare(name)]
        phase = agent.get("phase")
        if phase is None:
            return outside_architecture(agent["name"], agent["lane"])
        if self.phase_deferred(phase):
            return deferred(agent["name"], agent["lane"], phase)
        return not_switched_on(agent["name"], agent["lane"], phase)

    def status(self, name: str) -> AgentStatus | None:
        """The agent's standing now, or None when it is not on the roster (or names another plugin's agent)."""
        agent = self.agents.get(bare(name))
        if agent is None:
            return None
        key, lane, phase, via = agent["name"], agent["lane"], agent.get("phase"), agent.get("via")

        def standing(state: str, route: str = "", lines: tuple[str, ...] = ()) -> AgentStatus:
            return AgentStatus(key, lane, phase, str(agent.get("model") or ""), state, route, lines)

        phase_unit = f"phase {phase}" if phase is not None else None
        if phase_unit and self.phase_approved(phase) and self.accepted(phase_unit):
            return standing(ACTIVE, phase_unit)
        if via and self.deviation_in_effect(via) and self.accepted(via):
            return standing(ACTIVE, via)
        if via and self.deviation_in_effect(via):
            return standing(APPROVED_NOT_BUILT, via, approved_not_built(key, lane, phase if phase_unit else None))
        if phase_unit and self.phase_approved(phase):
            return standing(APPROVED_NOT_BUILT, phase_unit, approved_not_built(key, lane, phase))
        if phase is None:
            return standing(OUTSIDE, "", outside_architecture(key, lane))
        if self.phase_deferred(phase):
            return standing(DEFERRED, "", deferred(key, lane, phase))
        return standing(NOT_SWITCHED_ON, "", not_switched_on(key, lane, phase))

    def all(self) -> list[AgentStatus]:
        return [status for status in (self.status(name) for name in self.agents) if status is not None]


def dispatch_verdict(team: Team, subagent_type: str) -> tuple[bool, str, tuple[str, ...]]:
    """(allowed, rule_id, lines) for one dispatch. The gate and the banner both ask this."""
    status = team.status(subagent_type)
    if status is None:
        return False, f"not-on-roster:{subagent_type or 'general-purpose'}", not_on_roster(subagent_type)
    if status.active:
        return True, f"active:{status.name}", ()
    return False, f"{status.state.replace('_', '-')}:{status.name}", status.lines


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        raise TeamUnreadable(f"{path}: {exc.__class__.__name__}: {exc}") from exc
    if not isinstance(data, dict):
        raise TeamUnreadable(f"{path}: top level is not an object")
    return data


def load(root: Path | str | None = None) -> Team:
    """The team as the files on disk say it is. Raises TeamUnreadable, never guesses.

    Phases and deviations are read through scripts/overlay.py: the tracked defaults with
    Taylor's own decisions (state/taylor/) laid over them, so his approvals survive every
    `git pull` of the defaults.
    """
    base = Path(root) if root else REPO_ROOT
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import overlay  # noqa: PLC0415  -- local: hooks import this module, and only a load needs it

    try:
        phase_gate, register = overlay.phases(base), overlay.deviations(base)
    except overlay.OverlayUnreadable as exc:
        raise TeamUnreadable(str(exc)) from exc
    return Team(_read(base / "context" / "roster-agents.json"), phase_gate, register)


def counts(statuses: list[AgentStatus]) -> str:
    """'6 on, 5 not switched on yet, ...', always starting with how many are on."""
    tally = {state: sum(1 for s in statuses if s.state == state) for state in STATE_WORDS}
    parts = [f"{tally[ACTIVE]} on"]
    parts += [f"{n} {STATE_WORDS[state]}" for state, n in tally.items() if state != ACTIVE and n]
    return ", ".join(parts)


def render(statuses: list[AgentStatus]) -> str:
    lines = [f"TEAM: {counts(statuses)}"]
    for s in statuses:
        state = STATE_WORDS[s.state] + (f" (via {s.route})" if s.active and not s.route.startswith("phase") else "")
        where = f"phase {s.phase}" if s.phase is not None else "no phase"
        lines.append(f"  {s.name:<6} {state:<24} {where:<9} {s.lane}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--agent", help="print exactly what a dispatch to this agent answers")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # swallow: a stream that cannot be reconfigured needs no fix
    try:
        team = load()
    except TeamUnreadable as exc:
        print(f"TEAM UNREADABLE: {exc}. Every dispatch is refused until this is fixed; tell Mike.",
              file=sys.stderr)
        return 2
    if args.agent:
        status = team.status(args.agent)
        if status is None:
            print("\n".join(not_on_roster(args.agent)))
            return 1
        if args.json:
            print(json.dumps({**asdict(status), "active": status.active}, indent=2))
        else:
            print(f"{status.name} is switched on." if status.active else "\n".join(status.lines))
        return 0
    statuses = team.all()
    if args.json:
        print(json.dumps([{**asdict(s), "active": s.active} for s in statuses], indent=2))
    else:
        print(render(statuses))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/bin/bash
# Hook: PostToolUse (Edit|Write|MultiEdit)
# Runs the repo's validators when a file they cover changes.
#
# Ported from PIPER, which ported it from STEVIE. Every validator here existed as
# prose first, and a check that depends on somebody remembering is the same class
# of defect the checks catch. This removes the remembering.
#
# EVERY "COULD NOT CHECK" BRANCH EXITS 2, NOT 0. A version of this hook that exits
# 0 when it cannot cd to the project or find a validator reports a clean bill of
# health for work it has never looked at.
#
# WHAT IS DIFFERENT HERE. Agents, skills and commands live under .claude/ so the VS
# Code extension finds them by opening the folder. Hooks and context files route to
# validate_guardrails.py --self-test, the only thing that proves the gates still go
# red on their fixtures after an edit.

source "$(dirname "$0")/_lib.sh"

CONTRACTS="scripts/validate_agent_contracts.py"
GUARDRAILS="scripts/validate_guardrails.py"

INPUT=$(cat)

if FILE_PATH=$(hook_field "$INPUT" '.tool_input.file_path' 'tool_input.file_path'); then
  NORMALISED=$(echo "$FILE_PATH" | tr '\\' '/')
  case "$NORMALISED" in
    */.claude/agents/*.md|*/.claude/skills/*/SKILL.md|*/.claude/commands/*.md) VALIDATORS="$CONTRACTS" ;;
    */context/*.json)                  VALIDATORS="$GUARDRAILS" ;;
    */.claude/hooks/*.py)              VALIDATORS="$GUARDRAILS" ;;
    */.claude/settings.json)           VALIDATORS="$GUARDRAILS" ;;
    "")                                VALIDATORS="$CONTRACTS $GUARDRAILS" ;;
    *)                                 exit 0 ;;
  esac
else
  echo "validate-on-edit.sh: could not read hook input; running every validator" >&2
  VALIDATORS="$CONTRACTS $GUARDRAILS"
fi

PROJECT_DIR="${EA_ROOT:-${CLAUDE_PROJECT_DIR:-.}}"
if ! cd "$PROJECT_DIR"; then
  echo "validate-on-edit.sh: cannot cd to '$PROJECT_DIR', so the validators did" >&2
  echo "NOT run. This hook has verified nothing about the edit that just landed." >&2
  exit 2
fi

PY=$(command -v python3 2>/dev/null) || PY=$(command -v python 2>/dev/null) || PY=""
if [ -z "$PY" ]; then
  echo "validate-on-edit.sh: no python interpreter on PATH, so the validators" >&2
  echo "did NOT run. A check that cannot execute has not passed." >&2
  exit 2
fi

FAILED=0
for VALIDATOR in $VALIDATORS; do
  if [ ! -f "$VALIDATOR" ]; then
    echo "validate-on-edit.sh: $VALIDATOR not found under $(pwd), so the check it" >&2
    echo "performs did NOT happen. A missing validator is a failed validator." >&2
    FAILED=1
    continue
  fi
  ARGS=""
  [ "$VALIDATOR" = "$GUARDRAILS" ] && ARGS="--self-test"
  if ! OUTPUT=$("$PY" "$VALIDATOR" $ARGS 2>&1); then
    echo "$VALIDATOR $ARGS failed:" >&2
    echo "$OUTPUT" >&2
    FAILED=1
  fi
done

[ "$FAILED" -ne 0 ] && exit 2
exit 0

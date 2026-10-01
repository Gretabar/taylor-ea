#!/bin/bash
# Shared helpers for this repo's shell hooks. Source this, don't execute it.
#
# The problem this exists to solve: a hook that reads its payload with a bare
# `jq -r ...` gets an empty string when jq is absent, every subsequent grep
# misses, and the hook exits 0 -- so a missing parser turns a blocking gate into
# a pass-through that ALLOWS the thing it was written to block. An empty field
# and an unreadable payload are different facts, and conflating them is the same
# short-circuit-to-pass the repo's validators exist to catch.
#
# hook_field prints the extracted value and returns 0 when it could parse at
# all, or returns 3 when no parser is available. Callers MUST treat 3 as
# "cannot verify" -- never as "nothing found".

# hook_field <payload> <jq-path> <dotted-path>
#   e.g. hook_field "$INPUT" '.tool_input.command' 'tool_input.command'
hook_field() {
  local payload="$1" jq_path="$2" py_path="$3" out rc

  if command -v jq >/dev/null 2>&1; then
    out=$(printf '%s' "$payload" | jq -r "$jq_path // empty" 2>/dev/null)
    rc=$?
    if [ "$rc" -eq 0 ]; then
      printf '%s' "$out"
      return 0
    fi
  fi

  # Python is already a hard dependency of this repo (requirements.txt pins
  # 3.11+) and two hooks shell to it, so this is a real fallback rather than a
  # theoretical one.
  local py=""
  py=$(command -v python3 2>/dev/null) || py=$(command -v python 2>/dev/null) || py=""
  if [ -n "$py" ]; then
    # Read and write bytes explicitly. sys.stdin/stdout use the locale encoding,
    # which on Windows is cp1252 -- a UTF-8 payload containing an accented path
    # or an em dash would arrive as mojibake and be matched against, or written
    # back, wrong. Same defect already caught in validate_content_rules.py.
    out=$(printf '%s' "$payload" | "$py" -c 'import json, sys
d = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
for key in sys.argv[1].split("."):
    d = d.get(key) if isinstance(d, dict) else None
sys.stdout.buffer.write(("" if d is None else str(d)).encode("utf-8"))' "$py_path" 2>/dev/null)
    rc=$?
    if [ "$rc" -eq 0 ]; then
      printf '%s' "$out"
      return 0
    fi
  fi

  return 3
}

# hook_die_unparseable <hook name>
# For gates whose whole contract is "nothing gets past unexamined". Blocks.
hook_die_unparseable() {
  echo "$1: neither jq nor python could read the hook payload, so this gate" >&2
  echo "cannot inspect the request. It is BLOCKING rather than waving through" >&2
  echo "a call it never looked at -- a safety check that cannot see its input" >&2
  echo "has not checked anything." >&2
  echo "" >&2
  echo "This is an ENVIRONMENT fault, not a problem with the command. Do not" >&2
  echo "retry or rephrase it. Install jq or python, or tell Mike." >&2
  exit 2
}

# hook_die_empty <hook name> <field>
# A working parser that yields nothing means the payload shape changed. Same
# "cannot verify" state, different cause.
hook_die_empty() {
  echo "$1: payload parsed but '$2' was empty, so there is nothing to inspect." >&2
  echo "The hook payload shape has probably changed. BLOCKING rather than" >&2
  echo "assuming an unreadable request is a safe one." >&2
  echo "" >&2
  echo "This is an ENVIRONMENT fault, not a problem with the command. Do not" >&2
  echo "retry or rephrase it. Tell Mike." >&2
  exit 2
}

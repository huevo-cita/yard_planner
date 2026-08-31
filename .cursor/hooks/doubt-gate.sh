#!/usr/bin/env bash
#
# Deny the expensive yard jobs while a doubt that would change them is open.
#
# The Python gate in `lib/doubts.py` already refuses. This exists because that
# refusal only fires once the command has been chosen, and the failure worth
# preventing is upstream of that: an assistant that has just voiced a doubt in
# prose and is about to run the model anyway. A denial with a redirect in it
# closes that surface; an instruction in a rules file only asks nicely.
#
# So the deny message is written to be read by the agent, and it says what to do
# instead. That is the whole trick — the block is useless without the redirect.
#
# Contract: reads the beforeShellExecution payload on stdin, always prints one
# valid JSON object, always exits 0. `permission` is one of:
#
#   deny    a gated job on a yard that is not clear for it — either an open
#           doubt blocking it, or no current all-clear attesting to the values
#           it reads that were assumed or reported rather than measured
#   ask     the same, but with --force, so the override costs a human click
#           rather than being the agent's to take
#   allow   everything else, including the cheap inspection paths
#
# The deny text itself is built in `lib.doubts.gate_json` and passed through
# whole. It used to be assembled here in jq, which meant the wording the hook
# showed and the wording the in-process gate raised drifted apart and only one
# of them was ever tested.
#
# Deliberately fails open on anything it cannot work out — an unparseable
# command, an unknown yard, a missing interpreter. A gate that blocks work it
# does not understand gets deleted within a week, and then there is no gate. The
# in-process Python gate is the backstop for everything this misses.
#
# `set -e` is omitted on purpose: an aborted script prints no JSON, and with
# failClosed set that reads as a refusal of a command nobody objected to.

set -uo pipefail

REPO="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${YARD_PYTHON:-python3}"

# The jobs worth stopping for. Must stay in step with `JOBS` in lib/doubts.py.
GATED="sunmodel design drawbeds bom schedule"

allow() { printf '{"permission":"allow"}\n'; exit 0; }

emit() {
  # jq builds the payload so a question mark or a quote in someone's doubt
  # cannot break the JSON the hook is judged on. An empty user_message is
  # dropped rather than sent as "", so an allow-with-a-note does not put an
  # empty notification in front of anyone.
  if ! jq -n --arg p "$1" --arg a "$2" --arg u "$3" \
      '{permission:$p, agent_message:$a}
       + (if $u == "" then {} else {user_message:$u} end)' 2>/dev/null; then
    printf '{"permission":"allow"}\n'
  fi
  exit 0
}

command -v jq >/dev/null 2>&1 || allow
command -v "$PYTHON" >/dev/null 2>&1 || allow

INPUT="$(cat)"

# Proof that Cursor invokes this at all, and a record of what it hands over.
# Both are otherwise unobservable: a hook that is never called and a hook that
# allows everything look identical from outside.
#
# Switched by the presence of a file rather than an env var, because this runs as
# a child of the editor and never sees a shell's exports — the same blindness
# that stops it finding a yard when GARDEN_ROOT points elsewhere.
if [ -f "$REPO/.cursor/hooks/.debug" ]; then
  { printf '=== %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '%s\n' "$INPUT"
    "$PYTHON" - "$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty')" <<'PROBE'
import json, sys
p = sys.argv[1] if len(sys.argv) > 1 else ""
if not p:
    print("  transcript_path: ABSENT"); sys.exit()
try:
    rows = [json.loads(l) for l in open(p) if l.strip()]
except Exception as e:
    print(f"  transcript unreadable: {e}"); sys.exit()

def text(r):
    m = r.get("message")
    if isinstance(m, str): return m
    if isinstance(m, dict):
        c = m.get("content")
        if isinstance(c, str): return c
        if isinstance(c, list):
            return " ".join(b.get("text","") for b in c if isinstance(b, dict))
    return ""

print(f"  records: {len(rows)}")
tail = [r for r in rows if text(r).strip()][-1:]
for r in tail:
    print(f"  last non-empty [{r.get('type')}/{r.get('role')}]: {text(r)[:150]!r}")
# Did anything from the turn now in flight reach the file before this fired?
try:
    last_turn_end = max(i for i, r in enumerate(rows)
                        if r.get("type") == "turn_ended")
except ValueError:
    last_turn_end = -1
after = [r.get("role") for r in rows[last_turn_end + 1:]]
print(f"  records after last turn_ended: {len(after)} {after}")
PROBE
  } >> "$REPO/.cursor/hooks/payload.log" 2>/dev/null
fi

CMD="$(printf '%s' "$INPUT" | jq -r '.command // empty' 2>/dev/null)"
[ -n "$CMD" ] || allow

# ---------------------------------------------------------------- which job

JOB=""
for j in $GATED; do
  case " $CMD " in
    *"lib.$j"*|*" yard $j "*|*"/yard $j "*)
      JOB="$j"
      break
      ;;
  esac
done
[ -n "$JOB" ] || allow

# The cheap paths, which are how a doubt gets settled and must never be gated.
# `--quick` runs the model coarsely across a range; `--init` creates an empty
# file; `--crossover` and the seed-date lookups touch no yard record at all.
case "$JOB" in
  sunmodel) case "$CMD" in *--quick*) allow ;; esac ;;
  design)   case "$CMD" in *--init*) allow ;; esac ;;
  bom)      case "$CMD" in *--crossover*) allow ;; esac ;;
  schedule) case "$CMD" in *--seed-start*|*--harvest-by*) allow ;; esac ;;
esac

# ---------------------------------------------------------------- which yard

read -r -a TOKENS <<< "$CMD"
SLUG=""
for ((i = 0; i < ${#TOKENS[@]}; i++)); do
  t="${TOKENS[$i]}"
  if [ "$t" = "lib.$JOB" ] || [ "$t" = "$JOB" ]; then
    for ((k = i + 1; k < ${#TOKENS[@]}; k++)); do
      n="${TOKENS[$k]}"
      case "$n" in -*) continue ;; esac
      SLUG="$n"
      break 2
    done
  fi
done
[ -n "$SLUG" ] || allow

# drawbeds also takes a standalone spec file, which belongs to no yard and has
# no board to check.
[ -f "$SLUG" ] && allow

# ---------------------------------------------------------------- the verdict

VERDICT="$(cd "$REPO" && "$PYTHON" -m lib.doubts "$SLUG" --gate "$JOB" 2>/dev/null)"
[ -n "$VERDICT" ] || allow

# A slug with no directory behind it is a yard this process cannot see, which is
# usually GARDEN_ROOT pointing somewhere the editor never heard about rather than
# a typo. Fail open; the in-process gate is stricter and still refuses.
#
# `//` is not usable here: jq's alternative operator fires on `false` as well as
# on null, so `.yard_known // true` is `true` for every yard including the ones
# that do not exist.
KNOWN="$(printf '%s' "$VERDICT" \
  | jq -r 'if has("yard_known") then .yard_known else true end' 2>/dev/null)"
[ "$KNOWN" = "false" ] && allow

BLOCKED="$(printf '%s' "$VERDICT" | jq -r '.blocked // false' 2>/dev/null)"
[ "$BLOCKED" = "true" ] || allow

AGENT="$(printf '%s' "$VERDICT" | jq -r '.agent_message // empty' 2>/dev/null)"
USER="$(printf '%s' "$VERDICT" | jq -r '.user_message // empty' 2>/dev/null)"
WHY="$(printf '%s' "$VERDICT" | jq -r '(.reasons // []) | join(" and ")' 2>/dev/null)"

# An older lib.doubts, or a jq that choked: block, but say something usable
# rather than emitting an empty denial the agent cannot act on.
[ -n "$AGENT" ] || AGENT="Blocked: $JOB on $SLUG is not clear to run.

  python3 -m lib.doubts $SLUG --open        what is still in question
  python3 -m lib.doubts $SLUG --inputs $JOB   what an all-clear has to answer"
[ -n "$USER" ] || USER="$SLUG: $JOB is blocked by the doubt gate."

case "$CMD" in
  *--force*)
    emit "ask" \
      "This is a --force override past $WHY on $SLUG. It needs a person to approve it, and the output will be stamped provisional, naming what it came past.

$AGENT" \
      "Approve running $JOB on $SLUG past $WHY? The output will be stamped provisional."
    ;;
esac

emit "deny" "$AGENT" "$USER"

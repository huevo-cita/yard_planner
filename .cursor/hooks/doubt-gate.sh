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
#   deny    a gated job, on a yard with open doubts blocking it
#   ask     the same, but with --force, so the override costs a human click
#           rather than being the agent's to take
#   allow   everything else, including the cheap inspection paths
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

BLOCKED="$(printf '%s' "$VERDICT" | jq -r '.blocked // false' 2>/dev/null)"

if [ "$BLOCKED" != "true" ]; then
  # Nothing is filed against this job. Before waving it through, check for the
  # shape the *unfiled* failure leaves: a record built mostly on assumption,
  # about to have an expensive job run on it, with an empty board. Allowed, but
  # said out loud, because the gate cannot read a doubt that was never written
  # down and this is the only trace such a doubt leaves.
  UNFILED="$(printf '%s' "$VERDICT" | jq -r 'if .unfiled then
      "This is about to run \(.unfiled.job) on \(.yard), whose record is "
      + "\(.unfiled.assumed_count) assumed or reported values with only "
      + "\((.unfiled.measured_fraction * 100) | floor)% of it measured, and "
      + "whose doubt board is completely empty.\n\nAssumed, among others:\n"
      + ([.unfiled.examples[] | "  - \(.)"] | join("\n"))
      + "\n\nThat is allowed. But if you have been hedging about any of these in "
      + "the conversation — an assumed height, a species read off a leaf-off "
      + "lidar flight, a fence you are not sure is opaque — file it now rather "
      + "than after this run:\n\n  python3 -m lib.doubts \(.yard) --add \"...\" "
      + "--kind fact --blocks \(.unfiled.job)\n\nRe-running this because a "
      + "hedge turned out to matter is the exact cost this board exists to "
      + "avoid."
    else empty end' 2>/dev/null)"
  if [ -n "$UNFILED" ]; then
    emit "allow" "$UNFILED" ""
  fi
  allow
fi

COUNT="$(printf '%s' "$VERDICT" | jq -r '.count // 0' 2>/dev/null)"
# The options are rendered inline rather than referenced, because a choice with
# its trade-offs sitting in another file is a choice that gets guessed at.
LIST="$(printf '%s' "$VERDICT" | jq -r '
  .cards[]
  | "  [\(.id)] \(.question)"
  + "\n        costs \(.priced)"
  + (if .how_to_settle then "\n        to settle \(.how_to_settle)" else "" end)
  + ([.options[]?
      | "\n        option: \(.name)"
      + (if .pro  then "\n            pro  \(.pro)"  else "" end)
      + (if .con  then "\n            con  \(.con)"  else "" end)
      + (if .cost then "\n            cost \(.cost)" else "" end)
     ] | join(""))' 2>/dev/null)"

PLURAL="s"; [ "$COUNT" = "1" ] && PLURAL=""

AGENT="Blocked: $SLUG has $COUNT open doubt$PLURAL on its board that would change what $JOB produces.

$LIST

Do not re-run this with --force to get past it. Settle the doubt first, because that is cheaper than running this twice:

  - a fact that can be probed:   python3 -m lib.doubts $SLUG --price
  - a fact someone measured:     python3 -m lib.doubts $SLUG --settle <id> --answer \"...\" --by measured
  - a choice: put the options, with their pros, cons and costs, in front of the
    person and let them pick, then record it with --by decided
  - genuinely not worth settling: python3 -m lib.doubts $SLUG --waive <id> --reason \"...\"

If you raised one of these doubts yourself in the last few messages, that is exactly the case this gate exists for. Settle it now rather than running the expensive job and re-running it afterwards."

USER="$SLUG has $COUNT open doubt$PLURAL blocking $JOB. Blocked until they are settled or waived."

case "$CMD" in
  *--force*)
    emit "ask" \
      "This is a --force override past $COUNT open doubt$PLURAL on $SLUG. It needs a person to approve it, and the output will be stamped provisional.

$LIST" \
      "Approve running $JOB on $SLUG with $COUNT open doubt$PLURAL? The output will be stamped provisional."
    ;;
esac

emit "deny" "$AGENT" "$USER"

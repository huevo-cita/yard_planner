#!/usr/bin/env bash
#
# Say so, at the moment a plan document is written, when what was written is a
# change-log entry rather than a plan -- or when it has just moved a date away
# from the file that generates the week-by-week calendar.
#
# Two checks, one hook
# --------------------
# The second check exists because `CALENDAR.md` is generated from `tasks.json`,
# while `PLAN.md` and `SOWING-CALENDAR.md` keep their own dated sections. A date
# edited in one of those and not in `tasks.json` is the same failure this repo
# already has two mechanisms for: a fact that should have gone into a file goes
# somewhere nothing reads it. `lib.week --check` compares a digest of every
# section `tasks.json` was extracted from, so an edit to one is caught here, at
# the moment it is made and while the reason for it is still to hand.
#
# It is one hook rather than two because this one already fires on exactly the
# right file set, already resolves the repo and the slug, and already has the
# output channel. A second hook would duplicate all of that to watch the same
# files.
#
# `lib.changelog --lint` already finds this, and `lib.buildhtml` runs it on the
# way to publishing. Both are too late in the same way the doubt gate's Python
# layer is too late: by then the prose exists, and the cheapest moment to move a
# sentence into the log is the moment after writing it, while the reason for it
# is still to hand.
#
# Why postToolUse and not afterFileEdit
# -------------------------------------
# afterFileEdit is the obvious event and it carries `file_path` directly. It has
# no output channel — the documented shape is input only, for formatters and
# accounting. VALIDATOR.md's conclusion from building the doubt gate was that a
# guardrail without a redirect is not a guardrail, and a hook that cannot speak
# cannot redirect. postToolUse returns `additional_context`, which is injected
# into the conversation after the tool result, so this one can say what to do.
#
# The cost is that the matcher for postToolUse filters on tool type, and the
# documented list of type names does not include every editing tool. So there is
# no matcher: the hook fires for every tool call and gets out of the way in two
# jq calls unless the path it was handed is an action document. Complete coverage
# for a few milliseconds is the right trade; a matcher that silently misses
# StrReplace would leave the main editing path unwatched.
#
# Unlike the doubt gate this hook has no `permission` to return and therefore
# nothing to fail closed on. It cannot block a write, and it is not trying to.
# The write is fine — the sentence is in the wrong file, and that is a thing to
# be told, not stopped.
#
# `set -e` is omitted deliberately: an aborted script prints no JSON, and silence
# here should read as "nothing to say" rather than as an error.

set -uo pipefail

nothing() { printf '{}\n'; exit 0; }

command -v jq >/dev/null 2>&1 || nothing

INPUT="$(cat)"

# Write, StrReplace and friends disagree on what the field is called, and an
# absent path is the common case because most tool calls are not edits at all.
DOC="$(printf '%s' "$INPUT" | jq -r '
  .tool_input.path // .tool_input.file_path // .tool_input.target_notebook
  // .file_path // empty' 2>/dev/null)"
[ -n "$DOC" ] || nothing
[ -f "$DOC" ] || nothing

case "$(basename "$DOC")" in
  PLAN.md|SCHEDULE.md|SOWING-CALENDAR.md|SOURCING.md|SITE-WALK.md|CALENDAR.md) ;;
  *) nothing ;;
esac

# The repo is resolved from this script's own location, which holds however the
# editor was launched. workspace_roots is the fallback for the case where this
# file has been copied somewhere else.
REPO="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [ ! -f "$REPO/lib/changelog.py" ]; then
  REPO="$(printf '%s' "$INPUT" | jq -r '.workspace_roots[0] // empty')"
fi
[ -n "$REPO" ] && [ -f "$REPO/lib/changelog.py" ] || nothing

PYTHON="${YARD_PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || nothing

YARD="$(cd -P "$(dirname "$DOC")" && pwd)"
SLUG="$(basename "$YARD")"
NAME="$(basename "$DOC")"

PARTS=()

FINDINGS="$(cd "$REPO" && "$PYTHON" -m lib.changelog "$SLUG" --lint "$DOC" 2>/dev/null)"; RC=$?
if [ $RC -ne 0 ] && [ -n "$FINDINGS" ]; then
  PARTS+=("$(printf '%s\n\n%s' \
    "$NAME was just written with prose that belongs in the change log, not in a plan. This is not a blocker and the file is saved; it is a list of sentences to move." \
    "$FINDINGS")")
fi

# The drift check only says anything on a yard that keeps its dates in a file.
if [ -f "$YARD/tasks.json" ] && [ -f "$REPO/lib/week.py" ]; then
  if [ "$NAME" = "CALENDAR.md" ]; then
    PARTS+=("$NAME is generated from $SLUG/tasks.json by \`yard week $SLUG --calendar\`, so an edit made here is lost the next time it renders. Put the change in tasks.json and re-render.")
  fi
  DRIFT="$(cd "$REPO" && "$PYTHON" -m lib.week "$SLUG" --check 2>/dev/null)"; RC=$?
  if [ $RC -ne 0 ] && [ -n "$DRIFT" ]; then
    PARTS+=("$(printf '%s\n\n%s\n\n%s' \
      "That edit left $SLUG/tasks.json disagreeing with the documents it was built from, so \`yard week $SLUG --calendar\` will now refuse. CALENDAR.md is what someone actually reads on a Saturday, so a date that only moved in the prose has not moved." \
      "$DRIFT" \
      "Carry the change into tasks.json, then \`python3 -m lib.week $SLUG --restamp\` to record the section as re-read.")")
  fi
fi

[ ${#PARTS[@]} -gt 0 ] || nothing

MESSAGE=""
for part in "${PARTS[@]}"; do
  MESSAGE="${MESSAGE}${part}"$'\n\n'
done

jq -n --arg c "$MESSAGE" '{additional_context: $c}' 2>/dev/null || nothing

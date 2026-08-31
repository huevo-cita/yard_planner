#!/usr/bin/env bash
#
# Say so, at the moment a plan document is written, when what was written is a
# change-log entry rather than a plan.
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

SLUG="$(basename "$(cd -P "$(dirname "$DOC")" && pwd)")"

FINDINGS="$(cd "$REPO" && "$PYTHON" -m lib.changelog "$SLUG" --lint "$DOC" 2>/dev/null)"
[ $? -eq 0 ] && nothing
[ -n "$FINDINGS" ] || nothing

MESSAGE="$(printf '%s\n\n%s\n' \
  "$(basename "$DOC") was just written with prose that belongs in the change log, not in a plan. This is not a blocker and the file is saved; it is a list of sentences to move." \
  "$FINDINGS")"

jq -n --arg c "$MESSAGE" '{additional_context: $c}' 2>/dev/null || nothing

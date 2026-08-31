# The doubt gate

Two layers stop an expensive job from running on an assumption nobody believes.
They are listed here worst-case-first, because each covers a case the one above it
cannot see.

There was a third, and it was removed after being measured rather than reasoned
about. [What cannot be enforced](#what-cannot-be-enforced) is the write-up, and it
is the most useful section in this file: it marks the edge of what any guardrail
here can reach, so the next person does not spend a day rebuilding it.

Borrowed shamelessly from [SwissArmyHammer](https://github.com/swissarmyhammer/swissarmyhammer)
and its Agent Validator Protocol, whose useful conclusion was that a guardrail
belonging to the agent's own judgement is not a guardrail. Enforcement lives
outside the agent, and a denial is only useful if it carries a redirect saying
what to do instead.

## Layer 1 — `doubts.gate()`, in process

In `lib/doubts.py`, called at the top of the expensive entrypoints. Raises
`SystemExit` listing the open cards, their prices and how to settle them.

Always holds, including for programmatic callers, and needs nothing installed.
This is the layer that cannot be got around by editing a config file.

## Layer 2 — `doubt-gate.sh`, a command hook

`beforeShellExecution`, `failClosed`, matched to the five gated jobs. Asks
`python3 -m lib.doubts <slug> --gate <job>` and turns the verdict into:

| | |
|---|---|
| `deny` | open cards block this job. The message carries the cards, the options with their pros and cons, and the commands to settle them |
| `ask` | the same, with `--force`, so an override costs a human click instead of being the agent's to take |
| `allow` + a note | nothing filed, but the record is mostly assumption and the board is empty. See below |
| `allow` | everything else |

It exists because layer 1 only fires once the command has been chosen, and the
moment worth catching is earlier: an assistant that has just hedged in prose and
is reaching for the model anyway.

**Where it is blind.** It fails open on anything it cannot work out — an
unparseable command, an unknown yard, a missing `jq`. Most importantly, the hook
is a child of the editor rather than of your shell, so if `GARDEN_ROOT` points
away from the checkout and the editor was not launched with it set, the hook
cannot find the yard and waves the command through. Layer 1 still holds in that
case. `python3 tools/doctor.py` reports this.

That one is fixable and currently unfixed: the payload carries `workspace_roots`,
so the hook could resolve the checkout without depending on an inherited
environment. Logging the payload is how to see it — `touch .cursor/hooks/.debug`
and read `payload.log`, which is gitignored because it records a user email and
every command the hook has judged.

**One unexplained miss, recorded rather than tidied away.** While removing layer 3,
the first gated command run afterwards did not invoke the hook at all — no log
line, no denial. Every other invocation in the same session did fire (six observed,
one missed). It did not reproduce: not by rewriting `hooks.json` byte-identically,
not by changing a value in it, and not by re-running the same command, which fired
normally.

So there is no mechanism to name here, only a measurement: **this layer is not
provably continuous.** Something occasionally does not reach it, and editing
`hooks.json` is the current suspect without being an established cause. Two
practical consequences. After changing hook configuration, re-arm the debug log and
confirm the hook still fires rather than assuming it. And do not treat this layer
as the thing standing between a doubt and an expensive run — that is layer 1, which
is in-process, has no registration to lose, and is why a miss here is survivable
rather than serious.

**The empty-board note.** No check here can read prose, but it can read the shape
that an unfiled doubt leaves behind: a record built mostly on `assumed` and
`reported` values, an expensive job about to run on it, and not one card ever
raised. `doubts.unfiled_warning()` decides this, and it is deliberately a nudge
rather than a refusal — plenty of legitimate early runs look exactly like that,
and blocking them would make the whole thing something to disable.

The matcher and `JOBS` in `lib/doubts.py` have to agree. Drift is silent and
total: a job added to `JOBS` but not to the matcher is simply never denied at this
layer. `tools/doctor.py` checks the two against each other.

## What cannot be enforced

There was a Layer 3: a `type: prompt` entry on the same event, handing the
situation to a sub-agent and asking whether the conversation contained a hedge
that was never filed. It was meant to catch a doubt while it is still only prose,
which is the failure the whole mechanism exists for.

It was deleted, because that turns out to be impossible here. The reasoning was
not from the documentation; it was measured.

**The experiment.** The hook was made to log the payload it receives
(`touch .cursor/hooks/.debug`). The payload does not contain the conversation, but
it does carry `transcript_path`, pointing at the session's JSONL — which looked
like it made prose-reading deterministic rather than a matter of judgement. So a
caveat carrying a nonce was written into the assistant's visible output —

> One caveat: I've assumed the west fence is solid board. SENTINEL-7F3A.

— and a gated command was run immediately afterwards, in the same turn, with the
hook dumping what it could see at the moment it fired.

**The result.** 214 records, unchanged from before that turn began. The most
recent entry was the *user's* message that opened the turn. The sentinel was
absent.

The transcript is flushed at turn boundaries. A hook firing mid-turn therefore
sees the conversation only up to the end of the *previous* turn. The caveat written
in the same turn as the run — the canonical failure, the one `AGENTS.md` is about —
is invisible, and it is invisible to any layer on this event, whether that layer is
a prompt or a script. This is not a limitation of the prompt hook. It is the shape
of the event.

**And the consolation prize does not survive either.** Previous-turn prose *is*
readable, so the obvious fallback is to scan it for the trigger phrases
`AGENTS.md` lists. Tried against one real turn of the conversation that built this:
17 hits, and essentially no real doubts. Mostly "should be" in ordinary technical
discussion, plus "one caveat" and "worth noting" matching because the trigger list
itself was being discussed. As an automated detector that denies every gated
command forever, which is the failure this file warns about twice.

So the trigger phrases work as instructions to something that reasons, and
collapse as a pattern to match. That is a real result and it is the reason
`AGENTS.md` is written as a rule addressed to the assistant rather than as a
regex: **the within-turn case is not externally enforceable, and the honest
mechanism for it is discipline, not a gate.**

What remains is layer 1, which is deterministic and in-process and always holds;
layer 2, which is deterministic but not provably continuous, as above; and the
empty-board note as the one trace an unfiled doubt reliably leaves.

If you are considering rebuilding this: re-run the sentinel experiment first. If a
nonce written in the same turn still cannot be seen, nothing built on this event
will work.

## Turning it off

Each layer detaches on its own:

- **Layer 2**: delete `.cursor/hooks.json`, or the `doubt-gate.sh` entry in it.
  Keep the two in step — a config pointing at a missing script, with
  `failClosed` set, blocks every gated job.
- **Layer 1**: this one is meant to be hard to remove. It is the backstop.

Disabling a layer is a real decision and belongs in a commit message. Reaching
for `--force` is not the same thing: it leaves the gate standing, costs a human
approval, and stamps the output provisional so nobody quotes it later as a
measurement.

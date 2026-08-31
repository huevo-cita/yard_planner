# The doubt gate

Three layers stop an expensive job from running on an assumption nobody believes.
They are listed here worst-case-first, because each one covers a case the one
above it cannot see.

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

**The empty-board note.** No check here can read prose, but it can read the shape
that an unfiled doubt leaves behind: a record built mostly on `assumed` and
`reported` values, an expensive job about to run on it, and not one card ever
raised. `doubts.unfiled_warning()` decides this, and it is deliberately a nudge
rather than a refusal — plenty of legitimate early runs look exactly like that,
and blocking them would make the whole thing something to disable.

The matcher and `JOBS` in `lib/doubts.py` have to agree. Drift is silent and
total: a job added to `JOBS` but not to the matcher is simply never denied at this
layer. `tools/doctor.py` checks the two against each other.

## Layer 3 — the unfiled-doubt validator, a prompt hook

The prompt lives in `.cursor/hooks.json` as a `type: prompt` entry on the same
event, and the rule it enforces is this file. A sub-agent reads the hook input and
decides whether the conversation contains a specific unresolved hedge about this
job's inputs that was never filed.

This is the only layer that can catch a doubt while it is still only prose, which
is the failure the whole mechanism exists for.

**Where it is blind.** A `beforeShellExecution` prompt hook is handed the command
and its context, and it is not guaranteed to see the conversation. The prompt is
written to allow whenever it has no evidence, so in the worst case this layer is
inert rather than wrong. Treat it as an extra chance, not as the mechanism.

It is also the only layer that costs a model call on every gated command, which
is why its matcher is scoped to the five jobs rather than to all shell commands.

## Turning it off

Each layer detaches on its own:

- **Layer 3**: delete the `type: prompt` entry from `.cursor/hooks.json`.
- **Layer 2**: delete `.cursor/hooks.json`, or the `doubt-gate.sh` entry in it.
  Keep the two in step — a config pointing at a missing script, with
  `failClosed` set, blocks every gated job.
- **Layer 1**: this one is meant to be hard to remove. It is the backstop.

Disabling a layer is a real decision and belongs in a commit message. Reaching
for `--force` is not the same thing: it leaves the gate standing, costs a human
approval, and stamps the output provisional so nobody quotes it later as a
measurement.

# The doubt gate

Two layers stop an expensive job from running on an assumption nobody believes.
They are listed here worst-case-first, because each covers a case the one above it
cannot see.

Both now enforce two conditions rather than one. Nothing may be open on the
board against the job, **and** there must be a current all-clear for it. The
second is the newer half and the reason is in
[Why silence had to stop counting](#why-silence-had-to-stop-counting).

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
`SystemExit` listing the open cards, their prices and how to settle them, and
whatever is wrong with the all-clear — missing, gone stale, or not covering
everything it claims to.

Always holds, including for programmatic callers, and needs nothing installed.
This is the layer that cannot be got around by editing a config file.

## Layer 2 — `doubt-gate.sh`, a command hook

`beforeShellExecution`, `failClosed`, matched to the five gated jobs. Asks
`python3 -m lib.doubts <slug> --gate <job>` and turns the verdict into:

| | |
|---|---|
| `deny` | open cards block this job, or there is no current all-clear for it |
| `ask` | the same, with `--force`, so an override costs a human click instead of being the agent's to take |
| `allow` | everything else, including the cheap paths and any slug with no yard directory behind it |

The denial text is no longer assembled here. `doubts.gate_json` returns a ready
`agent_message` and the hook passes it through, because the version built in jq
and the version raised by layer 1 were two wordings of the same refusal and only
one of them was ever tested. The redirect is the only part of a block that does
any good, so it has a test of its own now: it must name `--inputs` and `--clear`
for the job in hand.

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

**Where else it fails open.** A slug with no directory behind it is allowed
through, because the commonest cause is `GARDEN_ROOT` pointing at yards the
editor never heard of rather than a typo, and denying every command on a yard
this process cannot see is how the layer gets uninstalled. Layer 1 refuses
anyway. (`jq`'s `//` is not usable for reading that flag: the alternative
operator fires on `false` as well as on null, so `.yard_known // true` is `true`
for every yard including the ones that do not exist. That cost an afternoon
once.)

**The empty-board note is gone**, and the all-clear is what replaced it. It used
to read the shape an unfiled doubt leaves behind — a record built mostly on
`assumed` and `reported` values, an expensive job about to run on it, and not one
card ever raised — and say so without blocking. That was a guess at a threshold
(`len(soft) >= 3 and measured <= 0.6`) attached to a nudge nothing had to answer.
Requiring a written reason against each of those same values is the same
observation with teeth, so keeping both would have meant saying it twice.

The matcher and `JOBS` in `lib/doubts.py` have to agree. Drift is silent and
total: a job added to `JOBS` but not to the matcher is simply never denied at this
layer. `tools/doctor.py` checks the two against each other, and checks the same
thing for `JOB_INPUTS` in `lib/inputs.py`.

## Why silence had to stop counting

The original gate read an empty board as permission. That is backwards for the
one failure it exists to prevent, because a doubt that was thought and never
written down leaves an empty board — the state that looks most like confidence is
produced by the state that is least like it.

So the default is inverted. Each of the five jobs needs a positive all-clear in
`all-clear.json` before it will run: for every value that job reads whose
provenance is `assumed` or `reported`, either a settled doubt card id or a
sentence saying why proceeding is all right. Missing, stale and full-of-holes all
block identically.

**Assumed-only, and per job.** A record is mostly derived and measured values,
and asking about those would be noise. Only `assumed` and `reported` have to be
answered for; `measured`, `lidar`, `photo`, `parcel`, `survey` and `derived` pass
without comment. And the question is scoped to what the job actually reads —
`lib/inputs.py` maps each job to its sections of `site.json` — because making
`bom` account for a tree crown it never touches is how a gate ends up switched
off. Measured across the three yards in the vault, `sunmodel` has to answer for
between 3 and 62 values and `bom` for at most one, which is the difference
between a mechanism and a tax.

**Bound to a digest.** Each clearance stores a fingerprint of every value it
covers, so editing `site.json` underneath it makes it stale and the refusal names
which value moved. Without that it is a stamp collected once. Measuring a covered
value is deliberately *not* invalidating: that path leaves the assumed set
entirely, and blocking the run someone just made more trustworthy would train
people out of measuring things.

**How the input map is kept honest.** `lib/inputs.py` declares the map and
`derive()` recovers the same thing by walking each job's module and its
first-party imports with `ast`, collecting the top-level key of every read
against the site record. The declared map is what runs; the derived one is what
`drift()` compares it against, in `tools/doctor.py` and `tools/test_gate.py`. The
derivation is coarse in three named ways — module granularity rather than call
graph, top-level sections rather than paths, and `lib.doubts`/`lib.gaps` excluded
because every gated job imports them and following them would make every map the
union of all the others. All three over-approximate, which errs toward asking for
more rather than less.

### Two holes, stated rather than papered over

**A lazy all-clear clears everything.** `--because '*=looks fine'` is accepted.
There is no way to tell a considered blanket clearance from a careless one, and
pretending otherwise would be the second guardrail-by-agent-judgement this file
warns about. What the mechanism actually buys is narrower and still worth having:
the omission stops being invisible. There is a file with a date on it saying
which values were waved through and on what grounds, and a reviewer can disagree
with a sentence in a way they cannot disagree with something nobody said.

**Artifact dependencies are not transitive.** `bom` costs a `design.json` written
against a `sun-hours.json` modelled on an assumed fence height. The fence is
genuinely upstream of the total, and it is not in `bom`'s input set, because
`bom` reads a file that already exists rather than the fence. The argument for
stopping there is that the fence was attested when `sunmodel` ran and the
clearance goes stale if it moves. The argument against is that nothing checks the
two runs saw the same fence — a `sun-hours.json` produced under an all-clear that
has since gone stale is indistinguishable from a fresh one. Closing that means
stamping artifacts with the digest they were produced under and checking it
downstream, which is a real design and was not attempted here.

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

What remains is layer 1, which is deterministic and in-process and always holds,
and layer 2, which is deterministic but not provably continuous, as above.

If you are considering rebuilding this: re-run the sentinel experiment first. If a
nonce written in the same turn still cannot be seen, nothing built on this event
will work.

**The all-clear is the answer to this section, not another attempt at it.** It
does not try to detect an unwritten doubt, because that is settled as impossible
above. It changes what the absence of one means: an assistant that hedges in
prose and then reaches for the model still cannot be caught in the act, but it
can be made to write a sentence about the fence height before the model runs at
all. That is a different mechanism aimed at the same waste, and it works on the
part of the event that *is* observable — the record on disk.

## Turning it off

Each layer detaches on its own:

- **Layer 2**: delete `.cursor/hooks.json`, or the `doubt-gate.sh` entry in it.
  Keep the two in step — a config pointing at a missing script, with
  `failClosed` set, blocks every gated job.
- **Layer 1**: this one is meant to be hard to remove. It is the backstop.
- **The all-clear specifically**, leaving the doubt board in place: it is the
  second condition in `doubts.gate()`, and dropping it is deleting the
  `clearance` half of that function. Worth being honest about the trade if you
  do — it is the half that covers the doubt nobody wrote down, which is the one
  the whole mechanism was built for.

Disabling a layer is a real decision and belongs in a commit message. Reaching
for `--force` is not the same thing: it leaves the gate standing, costs a human
approval, and stamps the output provisional naming what it came past, so nobody
quotes it later as a measurement.

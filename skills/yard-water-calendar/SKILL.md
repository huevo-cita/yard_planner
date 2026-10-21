---
name: yard-water-calendar
description: Put a yard's watering schedule on a real Google Calendar - one event for each morning and evening that has hand watering, with the plants, the total amount, the skip rules, the first and last day of each job and what the drip does that day - after a check that every plant in the ground gets water from the drip or from a hand job. Syncs a rolling window and updates only what changed. Use when someone wants the watering on their calendar, asks what to water today or this week, says they lose track of what to keep wet or when a watering job starts or stops, or after any change to the watering tasks of a yard that already syncs.
---

# Yard water calendar

The watering jobs of a yard are in `tasks.json`. This skill puts them on a
Google Calendar as one event for each slot of each day: the morning and the
evening. The module is `lib.watercal`. The calendar tools are in an MCP
server, so the module writes the operations to a file and the agent runs them.

## Step 1: Make the record complete

Every water task needs a `dose` and a `when`. AGENTS.md, section "Watering: an
amount and a time of day are fields", gives the format.

```bash
cd ~/personal/garden
python3 -m lib.watercal <slug> --lint
```

Fix each finding in `tasks.json`. Read the amount and the time from the task's
own `how` steps and its `repeat.note`. Do not make up an amount. If the source
does not give one, write the measure that it gives in `dose.text`.

The drip has to be in `irrigation.json` as a `drip` block:

- `zones`: each zone with its `label`, the `beds` that it reaches, and `valve`
  when it shares the valve of another zone.
- `periods`: one for each timer setting, with `from`, the timer `task`, and for
  each zone either `weekdays`, `cycles` and `min_per_cycle`, or
  `days_per_week` and `minutes`.
- `until`: the last day that the periods are known for.

`lib.week --check` compares each period with its timer task.

## Step 2: Check that every plant gets water

```bash
python3 -m lib.watercal <slug> --coverage
python3 -m lib.watercal <slug> --coverage --days 365   # the long view
```

The check takes every plant from the bed map, the raised-bed grid, the design
records and `design.json` `containers`. Each finding has a kind:

| Kind | What it means | The usual fix |
|---|---|---|
| untracked | No task plants it and the design does not mark it existing | Give the plant task a placement, or mark the design record `existing` |
| uncovered | No drip zone reaches it and no hand job is responsible | Add a hand task, or a `water_exempt` record with a reason |
| establishment | A new planting goes too long without hand water | Add one task for each stage, each with `planted_by` |
| seed | A sowing dries out before it is up | Extend the daily task, or set `germinate_days` on the placement |
| taper | A `repeat.note` hides a change of cadence | Split the task, one task for each stage |

**Caution:** do not close a finding by guessing a new regime when the yard
owner has to choose. Examples are a bed with no drip, or a plant that may come
out. File a `choice` card with `lib.doubts`, and bring the options to the
person.

Log each record change with `lib.changelog --add`, then run `--render`,
`lib.week --check` and `lib.site <slug>`.

## Step 3: Set up the calendar, once for each yard

1. Ask which Google account to use. Follow the account rules: the work account
   is the default, and a garden is usually personal. Do not guess.
2. The person makes a calendar named "Garden - watering" in the Google Calendar
   app. The MCP server cannot make a calendar.
3. Find its id with `listCalendars` in the namespace for that account.
4. Write the settings:

```bash
python3 -m lib.watercal <slug> --init --account <alias> --namespace <mcp-namespace>
```

Then set `calendar_id` in `<slug>/water-calendar.json`. Set the slot times in
`slots` if the tasks give other times. For example, "mist at 17:00" means an
evening slot of 17:00.

## Step 4: Sync

```bash
python3 -m lib.watercal <slug> --days 7    # read the first week before a push
python3 -m lib.watercal <slug> --plan      # -> water-calendar.plan.json
```

Show the person the first week of events before the first push.

`water-calendar.plan.json` holds one entry in `ops` for each operation. Each
entry has a `tool` and the `args` for that tool. For each operation:

1. Call the `tool` with its `args`, through `CallDynamicTool`, in the
   `namespace` that the plan names.
2. For a create, keep the event id that the tool returns.
3. Collect the results as a list of `{"key": ..., "id": ...}`. A delete needs
   only the key.

Write the list to a file, then record it:

```bash
python3 -m lib.watercal <slug> --record /tmp/water-results.json
python3 -m lib.watercal <slug> --plan      # must now give 0 operations
```

**Caution:** do not run a plan twice and push both. Each plan replaces the last,
and `--record` accepts only the keys in the current plan.

Do not add attendees, and keep `sendUpdates` at `none`. Do not use the
`account` argument of the MCP tools: the namespace is the account.

## Step 5: Keep it current

Run Step 4 again:

- after any change to a water task, a timer task or a plant task
- once a week, to move the window forward

The window is `horizon_days` long, 42 days by default. An event in the past is
never changed or deleted. `--plan` refuses while a coverage finding is in the
window. Fix the finding. Use `--force` only when the person decides to sync
anyway. Each event then starts with the reason.

## Other calendars

```bash
python3 -m lib.watercal <slug> --ics       # -> <slug>/WATER.ics
```

The `.ics` file has the same events for any calendar app that imports a file.
An import does not update, so import a new file only into an empty calendar.

## What this is not for

The calendar shows watering, and the timer changes that set the drip. Other
garden jobs stay on the week page (`lib.week`). A job that is not watering but
carries a `dose`, such as "weed and water the empty squares", is on the
calendar because of its watering.

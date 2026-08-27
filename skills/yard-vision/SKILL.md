---
name: yard-vision
description: Capture what someone actually wants from their yard - purpose, style, maintenance appetite, what must stay, what they refuse, and the date it has to be right by - from conversation, a Pinterest board, a folder of saved images or a link dump. Finds the contradictions between stated wants before they cost a planting. Use when starting a new yard, when someone shares inspiration images, or before any design work. Writes vision.json.
---

# Yard Vision

`site.json` is what the yard is. `conditions.json` is what is true today. This is
what the person wants, and without it a design is the assistant's taste wearing
their address.

That failure is quiet and worth naming. Left unrecorded, a design drifts toward
whatever the model has seen most of, which is a particular grass-and-gravel
minimalism that many people actively dislike and few would say so, because it
looks competent.

## Step 1 — Start or load

```bash
cd ~/personal/garden
python3 -m lib.vision <slug>          # what is recorded, and what contradicts
python3 -m lib.vision <slug> --init   # if there is nothing yet
```

Taste changes, but slowly, and not on the schedule that conditions do. Re-read
what is there before asking anything. Nobody wants to answer the same question
twice.

## Step 2 — If they brought images

Launch the **vision-scout** subagent with the board, folder or links. It reads
the whole set before commenting on any one image, because the signal is in what
repeats rather than in any single picture. Someone who says "modern" and saves
twelve photographs of loose perennials against dark fencing is responding to the
fence.

It comes back with counts rather than impressions — "dark fencing in 9 of 14" —
plus what the photographs are not showing: the season, the fact that the garden
is five years old, the maintenance behind a clipped hedge, the cost of a stone
terrace, and whether the effect depends on a mature tree or a borrowed view.

**Show them the findings before writing them down.** "You seem to be after X"
gets corrected fast when it is wrong, and the correction is worth more than the
original reading.

## Step 3 — The six that gate a design

Everything else is optional. These are not, and `lib.gaps` prices each of them in
blocked decisions:

| field | why a design stalls without it |
| --- | --- |
| `purpose` | A yard for growing food, a yard for sitting in and a yard for children to run in share almost no decisions |
| `style` | Plant palette, hardscape material, bed shape, edging all follow from it |
| `maintenance_appetite` | Decides whether the planting can be seasonal or has to be self-sufficient, and whether a lawn is on the table |
| `must_keep` | Every layout decision works around these |
| `dislikes` | Cheaper to learn now than after it is planted |
| `target_date` | Nothing can be back-planned without it, and bloom windows and seed-start dates count backwards from it |

Ask about maintenance in hours, not adjectives. "Low maintenance" means four
different things and one of them is zero. Ask what they spend now and whether
they want that to go up or down; the answer to that is usable and the adjective
is not.

Ask about the target date and then ask what happens on it. A party, a season, a
sale, a visit. What happens determines what has to be *finished* versus merely
*started*, and those are different plans.

## Step 4 — Record strength, not just content

Every want carries one:

- **must** — non-negotiable. A design that violates it has failed
- **strong** — they will notice and mind
- **nice_to_have** — they would enjoy it, and it loses to any real constraint

```python
from lib import vision
vision.want("the climbing rose in the east corner stays", "must",
            source="said in conversation 2026-08-27")
```

This is what lets a design make a trade honestly later. Violating a
`nice_to_have` is normal and the design should say it did. Violating a `must`
means starting over.

**Watch for everything being a must.** Past about eight, the design has no room
to trade and the first real constraint breaks the whole plan rather than one part
of it. The tool flags this. Ask which three actually are.

## Step 5 — Find the contradictions now

```bash
python3 -m lib.vision <slug> --check
```

A person can sincerely want a cottage garden, no maintenance, and a tidy edge.
Those three do not coexist. Finding it in conversation costs a question; finding
it in August costs the planting.

The check knows the common ones — cottage against tidy, lawn against drought,
shade garden against vegetables, evergreen structure against native pollinators,
instant against cheap, fruit trees against no spraying, deer against hostas — and
for each it offers the trade that usually works rather than refusing anything.

**Raise these as choices, not as corrections.** "Both of those are achievable but
not in the same bed — the sun model says the west side is your vegetable light
and the north strip is your shade garden" is a design move. "You can't have that"
is not, and it is usually wrong anyway.

## Step 6 — Write it, and say what you heard

Record it, then play it back in three or four sentences in their own words. Use
their register: if they said "jungly", write "jungly", not "tropical-influenced
dense planting". People correct a summary they can recognise and nod politely at
one they cannot.

## Rules

- Their words over your categories, every time
- No preference gets recorded without a strength
- Never resolve a contradiction silently by picking the one that is easier to
  design. Name it and let them choose
- An inspiration photograph is the best two weeks of a five-year-old garden shot
  by someone who waited for the light. Say what year one looks like before
  anyone commits to it
- Do not convert a photograph of a different climate into a plant list. Offer the
  substitution that gives the same effect where they live, and say it is one
- This step records taste. It does not design anything. That is `yard-design`,
  and it runs afterwards against the measured facts

# Weekly Pulse Check-In — Form Spec

A 30-second weekly survey that maps cleanly into the burnout model.
Each question lists the exact wording, response type, validation, and
the model's column name (for the loader).

Ship this as a Google Form, Microsoft Form, Typeform, or `checkin.py`
CLI — the column names are what matters; the surface doesn't.

**Cadence:** weekly, sent Friday morning, due Sunday night.
**Time to complete:** 30 seconds.
**Anonymous?** No — needs a stable `person_id` (email is fine if
private; a 4-digit assigned code is better) so we can build a
per-person time series. Promise aggregation in the announcement.

---

## Identification (auto-filled, not asked)

| Field | Source | Model column |
|---|---|---|
| Email or person code | Auth / form prefill | `person_id` |
| Submission timestamp | Auto | `submitted_at` |
| Week of (Monday) | Computed from timestamp | `week_start` |

If you're using Google Forms: enable "Collect email addresses" + use
the Monday-of-this-week formula in the loader, not in the form.

---

## Question 1 — Hours

> **About how many hours did you work this week?**
> (Include meetings, emails, on-call. Round to the nearest hour.)

- Type: short answer / number
- Range: 20 – 90
- Required: yes
- Model column: `hours`

## Question 2 — Sleep

> **On average, how many hours of sleep did you get per night this week?**

- Type: short answer / number (one decimal allowed)
- Range: 3 – 11
- Required: yes
- Model column: `sleep`

## Question 3 — Mood

> **How would you rate your overall mood this week?**
> (1 = worst week in a long time, 10 = best in a long time)

- Type: linear scale 1 – 10
- Required: yes
- Model column: `mood`

## Question 4 — Stress

> **How would you rate your stress level this week?**
> (1 = totally calm, 10 = at my limit)

- Type: linear scale 1 – 10
- Required: yes
- Model column: `stress`

## Question 5 — Manager support

> **How supported by your manager did you feel this week?**

- Type: linear scale 1 – 10
- Required: yes
- Model column: `mgr_support`

## Question 6 — Peer support

> **How supported by your teammates did you feel this week?**

- Type: linear scale 1 – 10
- Required: yes
- Model column: `peer_support`

## Question 7 — Deadline pressure

> **How heavy was deadline pressure this week?**
> (1 = none, 10 = constantly behind)

- Type: linear scale 1 – 10
- Required: yes
- Model column: `deadline_pressure`

## Question 8 — On-call

> **Were you on-call this week?**
> - No
> - Yes, light load
> - Yes, heavy load (woken up / paged frequently)

- Type: multiple choice (single)
- Required: yes
- Model column: `on_call_load` (mapped: No=0.0, Light=0.6, Heavy=1.2)

## Question 9 — Recent events

> **Did any of these happen for your team in the last 4 weeks?**
> (Check all that apply. Leave blank if none.)
> - ☐ Layoff or RIF announced
> - ☐ Reorg / manager change
> - ☐ Major deadline crunch
> - ☐ I took PTO
> - ☐ Got significant recognition / promotion
> - ☐ Personal/family event affecting my work
> - ☐ On-call rotation just started

- Type: checkboxes (multi)
- Required: no
- Model column: `events` (joined with `|`, e.g. `layoff|deadline_crunch`)

## Question 10 — Burnout self-report (THE LABEL)

> **Right now, would you say you are burned out?**
> - No, I'm fine
> - A little, but managing
> - Yes, I'm burned out

- Type: multiple choice (single)
- Required: yes
- Model column: `burnout` (mapped: No=0, A little=0, Yes=1)

This is the **label** the model trains against. Without it the data is
useful for monitoring but not for retraining. The 3-way wording is on
purpose: "a little, but managing" gives respondents a middle option so
the YES bucket stays meaningful.

---

## Optional Q11 — Maslach mini (gold-standard label)

If People Ops will allow it, add three questions from the Maslach
Burnout Inventory and use the average as a richer label than the
single Q10. Same scale, same direction:

> **How emotionally drained do you feel by your work?** (1 = never, 7 = every day)
> **How fulfilled do you feel by what you accomplish?** (1 = every day, 7 = never)  ← reverse-scored
> **How cynical do you feel about your work?** (1 = never, 7 = every day)

Average ≥ 4.5 → `burnout = 1`. Average < 4.5 → `burnout = 0`. The
loader handles this if columns `mbi_drained`, `mbi_fulfilled`,
`mbi_cynical` are present.

---

## Final CSV schema

After collection (export Google Sheet → CSV), the file should look
like this. `checkin.py` and the form loader both produce this exact
schema:

```
person_id,week_start,hours,sleep,mood,stress,mgr_support,peer_support,deadline_pressure,on_call_load,events,burnout
alice@co,2026-05-04,52,6.5,6,7,7,8,7,0.6,deadline_crunch,0
bob@co,2026-05-04,40,7.5,8,3,9,9,3,0.0,,0
alice@co,2026-05-11,58,5.5,5,8,6,7,8,1.2,deadline_crunch|on_call,1
...
```

`load_real.py` reads this and turns it into a `(team_id, week, ...)`
frame compatible with `add_rolling_features()` and `train.py`. Each
unique `person_id` becomes a "team" of one; if you also add a
`team_id` column the loader will use that instead.

---

## Launch announcement (paste into your team channel)

> Hi all — starting this Friday I'm going to send a 30-second weekly
> wellness check-in. Five questions, one number each, takes longer to
> open than to fill out. Responses are aggregated; nothing
> individually identifying ever leaves People Ops. The point is to
> spot teams under sustained stress *before* anyone burns out, not to
> grade individuals. Skip any week if you want — partial data is
> still useful. First send: Friday at 9am.

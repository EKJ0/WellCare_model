# Data Source Discovery Checklist

You don't yet know what your org will let you have. This is the
30-minute version of finding out. Print it, fill in the answers in
the right column, then come back with what's marked **YES** and we'll
write loaders for those sources first.

The signals are ranked by expected impact. Get the top ones first;
don't waste effort on bottom-tier sources until the top ones are
exhausted.

---

## Who to ask

| Source | Who in your org owns it | Slack/email channel |
|---|---|---|
| Calendar / Meetings | IT / Workspace admin | `#it-help` |
| Slack / Teams telemetry | IT / Slack workspace owner | same |
| GitHub / GitLab | Engineering ops or repo admins | `#eng-ops` |
| Jira / Linear / Asana | PM ops | `#pm-ops` |
| PagerDuty / on-call | SRE / DevOps | `#sre` |
| HR data, surveys, attrition | People Ops / HRBP | direct DM |
| Existing engagement surveys | People Ops | direct DM |

Phrase the ask the same way every time:

> "I'm building an internal team-health dashboard. I need *aggregated,
> team-week-level* data — no individual-level data, no message
> contents. Can I get [X] for the last 12 months?"

The "aggregated, no contents" framing makes Privacy/Legal say yes ~10x
more often than "give me Slack messages".

---

## Tier 1 — Passive telemetry (highest impact)

For each row, mark **YES / NO / NEEDS APPROVAL**. If YES, note who can
export and in what format.

| # | Signal | Source | Available? | Owner | Format |
|---|---|---|---|---|---|
| 1 | After-hours messages per person/week (count, no contents) | Slack/Teams admin export | ☐ | | |
| 2 | Weekend messages per person/week | Slack/Teams admin export | ☐ | | |
| 3 | Meeting hours per person/week | Google/Outlook Calendar API | ☐ | | |
| 4 | Back-to-back-meeting count, no-meeting days | Calendar API | ☐ | | |
| 5 | After-hours meetings (8pm-7am, weekends) | Calendar API | ☐ | | |
| 6 | PRs per person/week, lines changed | GitHub/GitLab API | ☐ | | |
| 7 | PR review latency (median time-to-first-review) | GitHub/GitLab API | ☐ | | |
| 8 | Commits after 9pm or on weekends | Git timestamps | ☐ | | |
| 9 | On-call pages received per week (total + after-hours) | PagerDuty/Opsgenie | ☐ | | |
| 10 | Open-ticket count, ticket aging (% > 14d) per team | Jira/Linear API | ☐ | | |

**Reality check questions to ask the data owner:**
- "Can you export this *aggregated to person-week or team-week*?"
- "Is there a 12-month historical lookback?"
- "Is there a stable team_id or person_id I can use as a join key?"
- "What's the refresh cadence — daily, weekly, monthly?"

---

## Tier 2 — Surveys / pulse (highest direct signal)

| # | Signal | Source | Available? | Owner | Notes |
|---|---|---|---|---|---|
| 11 | Existing weekly/monthly pulse survey | People Ops, Officevibe, Culture Amp | ☐ | | |
| 12 | eNPS quarterly results | People Ops | ☐ | | |
| 13 | Last engagement-survey scores (team-level) | People Ops | ☐ | | |
| 14 | Permission to run a new weekly 5-Q pulse | People Ops + Legal | ☐ | | |
| 15 | Maslach Burnout Inventory (any past run) | People Ops | ☐ | | rare; ask anyway |

If #14 is **YES**, jump straight to `survey_template.md` and ship the
form this week — that gives you labels, which is the limiting reagent
for any real-world model.

---

## Tier 3 — HR / org structure (modest but cheap)

| # | Signal | Source | Available? | Owner |
|---|---|---|---|---|
| 16 | Vacation taken vs accrued, per person/quarter | HRIS (Workday/BambooHR) | ☐ | |
| 17 | Sick days in last 8 weeks | HRIS | ☐ | |
| 18 | Manager-change dates per team | HRIS | ☐ | |
| 19 | Team size changes / reorg dates | HRIS | ☐ | |
| 20 | Tenure, promotion-cycle history | HRIS | ☐ | |
| 21 | Voluntary attrition events (the gold-standard label) | HRIS | ☐ | |

**#21 is special.** Voluntary attrition in the next N weeks is the
cleanest, least-debatable label you can train against. If you can get
it, the model becomes a real attrition-risk model — which is what most
orgs actually care about.

---

## What to send back

After 30 minutes, you should have:

1. A list of 1-3 **Tier 1** signals marked YES.
2. A yes/no on **#14** (running a new weekly pulse).
3. A yes/no on **#21** (attrition labels).

Paste those answers back and I'll write a `load_<source>.py` adapter
for each YES. Each adapter follows the same contract:

```python
load_<source>(path_or_credentials) -> pandas.DataFrame
# columns: team_id, week, <signal_columns...>, [optional] burnout
```

Then `train_real.py` joins them all on `(team_id, week)` and trains
the same model pipeline you're already using.

---

## Don't wait — start collecting in parallel

Discovery takes 1-3 weeks of back-and-forth with IT/HR/Legal. While
that's happening, run the in-house pulse via `checkin.py` so you're
banking labeled data from day one. Even just *yourself* checking in
weekly produces a personal-risk time series in 6-8 weeks that's worth
tracking.

"""Weekly burnout check-in CLI.

Run once a week. Asks the same 10 questions as `survey_template.md`,
appends the row to `checkins.csv`, and (if a model bundle exists)
shows your current predicted risk so you get immediate value.

This is the on-ramp to real data:
  Week 1-N : run `python checkin.py` every Friday
  Week ~12 : you have ~12 rows; useful for personal trend tracking
  Week ~12 with N=10+ people: enough to retrain the model on real
            data with `python train_real.py`

Usage:
    python checkin.py                    # interactive
    python checkin.py --who alice@co     # skip the identity prompt
"""

from __future__ import annotations
import argparse
import csv
import datetime as _dt
from pathlib import Path

OUT = Path(__file__).resolve().parent
CHECKINS = OUT / "checkins.csv"

# Schema must stay in sync with load_real.py and survey_template.md.
SCHEMA = [
    "person_id", "team_id", "week_start",
    "hours", "sleep", "mood", "stress",
    "mgr_support", "peer_support", "deadline_pressure", "on_call_load",
    "events", "burnout",
    "submitted_at",
]

ON_CALL_MAP = {"n": 0.0, "l": 0.6, "h": 1.2}
BURNOUT_MAP = {"n": 0, "a": 0, "y": 1}

EVENT_OPTIONS = [
    ("1", "layoff"),
    ("2", "reorg"),
    ("3", "deadline_crunch"),
    ("4", "pto"),
    ("5", "recognition"),
    ("6", "personal_shock"),
    ("7", "on_call"),
]


def _ask_num(prompt: str, lo: float, hi: float) -> float:
    while True:
        s = input(f"  {prompt} [{lo}-{hi}]: ").strip()
        try:
            v = float(s)
        except ValueError:
            print("    !! not a number")
            continue
        if v < lo or v > hi:
            print(f"    !! must be in [{lo}, {hi}]")
            continue
        return v


def _ask_choice(prompt: str, options: dict[str, object]) -> object:
    keys = "/".join(options)
    while True:
        s = input(f"  {prompt} [{keys}]: ").strip().lower()
        if s and s[0] in options:
            return options[s[0]]
        print(f"    !! pick one of: {keys}")


def _ask_events() -> str:
    print("  Any of these happen in the last 4 weeks?")
    for k, name in EVENT_OPTIONS:
        print(f"    {k}) {name}")
    s = input("  Enter numbers (e.g. '1,3'), or blank for none: ").strip()
    chosen = []
    for tok in s.split(","):
        tok = tok.strip()
        for k, name in EVENT_OPTIONS:
            if tok == k:
                chosen.append(name)
    return "|".join(chosen)


def _monday_of(d: _dt.date) -> _dt.date:
    return d - _dt.timedelta(days=d.weekday())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--who", default="", help="person_id (e.g. your email)")
    ap.add_argument("--team", default="", help="optional team_id; defaults to person_id")
    ap.add_argument("--predict", action="store_true",
                    help="also show today's predicted risk after saving")
    args = ap.parse_args()

    print("=" * 60)
    print("  Weekly Burnout Check-In")
    print("=" * 60)

    person = args.who or input("  Who is this? (email or short code): ").strip()
    if not person:
        raise SystemExit("person_id is required")
    team = args.team or person
    week_start = _monday_of(_dt.date.today()).isoformat()
    print(f"\n  Logging for {person} (team={team}), week of {week_start}\n")

    hours  = _ask_num("Hours worked this week", 20, 90)
    sleep  = _ask_num("Avg sleep hours per night", 3, 11)
    mood   = _ask_num("Mood 1-10 (1=worst, 10=best)", 1, 10)
    stress = _ask_num("Stress 1-10 (1=calm, 10=at limit)", 1, 10)
    mgr    = _ask_num("Manager support 1-10", 1, 10)
    peer   = _ask_num("Peer support 1-10", 1, 10)
    dl     = _ask_num("Deadline pressure 1-10", 1, 10)
    oncall = _ask_choice("On-call this week (n=no, l=light, h=heavy)", ON_CALL_MAP)
    events = _ask_events()
    burnout = _ask_choice(
        "Right now, are you burned out (n=no, a=a little, y=yes)",
        BURNOUT_MAP,
    )

    row = {
        "person_id": person, "team_id": team, "week_start": week_start,
        "hours": hours, "sleep": sleep, "mood": mood, "stress": stress,
        "mgr_support": mgr, "peer_support": peer,
        "deadline_pressure": dl, "on_call_load": oncall,
        "events": events, "burnout": burnout,
        "submitted_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }

    new_file = not CHECKINS.exists()
    with CHECKINS.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA)
        if new_file:
            w.writeheader()
        w.writerow(row)
    print(f"\n  Saved to {CHECKINS.name}")

    # Tell them how many weeks they have so far.
    n_rows = sum(1 for _ in CHECKINS.open(encoding="utf-8")) - 1
    n_self = sum(1 for r in csv.DictReader(CHECKINS.open(encoding="utf-8"))
                 if r["person_id"] == person)
    print(f"  You now have {n_self} weeks logged ({n_rows} total across all people).")

    if args.predict:
        try:
            from predict import score_team, _print_scores, _verdict  # noqa
            raw = {k: row[k] for k in
                   ["hours", "sleep", "mood", "stress",
                    "mgr_support", "peer_support",
                    "deadline_pressure", "on_call_load"]}
            ev_list = [e for e in row["events"].split("|") if e]
            history = [{**raw, "events": ""} for _ in range(3)]
            history.append({**raw, "events": "|".join(ev_list)})
            scores = score_team(raw, history=history, recent_events=ev_list)
            print()
            _print_scores(raw, scores, events=ev_list)
        except FileNotFoundError:
            print("  (Skipping prediction — run `python train.py` first to "
                  "build the model bundle.)")


if __name__ == "__main__":
    main()

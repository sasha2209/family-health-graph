"""The pilot report: what happened across all participating families, in numbers a funder or the next clinic asks for.

Everything here is aggregate. The CSV meant for sharing hides any count from 1 to 4 ("<5"), so no single family can
be picked out of a small pilot. Survey answers are optional, asked in the app, and only ever reported as counts.

The questions:
* at sign-up: how much of the family's health history they knew, and whether they had ever discussed it with a doctor;
* after FOLLOWUP_DAYS: whether the app led them to a test or a doctor, and how useful it was.
"""
from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Optional

from .care import doses_for_day
from .clinic import stuck_referrals
from .insights import generate_insights
from .models import Level

FOLLOWUP_DAYS = 56          # 8 weeks
ADHERENCE_DAYS = 28
SMALL = 5                   # counts below this are hidden in the shareable report

QUESTIONS = {
    "baseline_knowledge": {"when": "baseline", "options": ["most", "some", "very_little"],
                           "text": "Before using the app, how much of your family's health history did you know?"},
    "baseline_discussed": {"when": "baseline", "options": ["yes", "no"],
                           "text": "Have you ever talked about your family's health history with a doctor?"},
    "followup_action": {"when": "followup", "options": ["test", "doctor", "both", "not_yet"],
                        "text": "Since joining, has the app led you to have a test or talk to a doctor?"},
    "followup_useful": {"when": "followup", "options": ["very", "somewhat", "not"],
                        "text": "How useful has the app been for your family?"},
}


def due_questions(created_at: str, answered: set[str], now: datetime) -> list[str]:
    """Questions to show this person now: baseline ones right away, follow-up ones after FOLLOWUP_DAYS."""
    age = now - datetime.fromisoformat(created_at)
    out = []
    for qid, q in QUESTIONS.items():
        if qid in answered:
            continue
        if q["when"] == "baseline" or age >= timedelta(days=FOLLOWUP_DAYS):
            out.append(qid)
    return out


def _pct(n: int, d: int) -> Optional[float]:
    return round(100 * n / d, 1) if d else None


def report(store, now: Optional[datetime] = None, only: Optional[set[str]] = None) -> dict:
    """``only``: count just these accounts (study participants, when the pilot is run as a study)."""
    now = now or datetime.now(timezone.utc)
    users = [u for u in store.users_overview() if only is None or u["id"] in only]
    uids = [u["id"] for u in users]
    profiles = {uid: store.get_profile(uid) for uid in uids}

    # Onboarding: did families build a useful record?
    relatives = [len(p.family) for p in profiles.values()]
    with_family = sum(1 for n in relatives if n)
    three_gen = sum(1 for p in profiles.values()
                    if any(m.relationship.value.endswith(("grandmother", "grandfather")) for m in p.family)
                    and any(m.degree == 1 for m in p.family))
    with_docs = len(store.saved_document_users() & set(uids))
    active_7d = sum(1 for u in users if u["last_seen"] and now - datetime.fromisoformat(u["last_seen"]) <= timedelta(days=7))

    # What the record surfaced.
    by_rule: Counter = Counter()
    with_high = with_any = 0
    for p in profiles.values():
        found = [i for i in generate_insights(p).insights if i.rule_id != "record_gaps"]
        by_rule.update({i.title for i in found})
        with_high += any(i.level == Level.HIGH for i in found)
        with_any += bool(found)

    # Follow-through: tests and referrals.
    bookings = [b for b in store.all_bookings() if b["user_id"] in profiles]
    done = [b for b in bookings if b["status"] in ("completed", "completed_elsewhere")]
    days_to_result = [(datetime.fromisoformat(b["updated_at"]) - datetime.fromisoformat(b["created_at"])).days
                      for b in bookings if b["status"] == "completed"]
    referrals = [r for r in store.all_referrals() if r["user_id"] in profiles]   # not practice patients
    ref_status = Counter(r["status"] for r in referrals)

    # Caregiving: are reminders being acted on?
    since = (now.date() - timedelta(days=ADHERENCE_DAYS)).isoformat()
    logs: dict[tuple[str, str], list[dict]] = {}
    for e in store.all_dose_logs(since):
        logs.setdefault((e["owner_id"], e["member_id"]), []).append(e)
    scheduled = taken = 0
    circles = store.care_targets()
    for owner, member_id in circles:
        family = profiles[owner].family if owner in profiles else []
        member = next((m for m in family if m.id == member_id), None)
        if member is None:
            continue
        for back in range(1, ADHERENCE_DAYS + 1):          # whole days only, so today's pending doses don't count
            day = now.date() - timedelta(days=back)
            for d in doses_for_day(member, day, logs.get((owner, member_id), []), now):
                scheduled += 1
                taken += d["status"] == "taken"

    # Surveys.
    answers = [a for a in store.survey_answers() if a["user_id"] in profiles and a["answer"] != "skipped"]
    survey = {qid: {"question": q["text"], "answers": dict(Counter(a["answer"] for a in answers if a["question"] == qid)),
                    "responses": sum(1 for a in answers if a["question"] == qid)} for qid, q in QUESTIONS.items()}

    return {
        "generated_at": now.isoformat(),
        "families": {"total": len(uids), "with_relatives": with_family, "with_three_generations": three_gen,
                     "median_relatives": median(relatives) if relatives else 0, "added_a_document": with_docs,
                     "active_last_7_days": active_7d},
        "findings": {"families_with_an_item": with_any, "families_with_an_item_to_discuss_soon": with_high,
                     "by_item": dict(by_rule.most_common())},
        "tests": {"booked": len(bookings), "completed": len(done),
                  "completion_rate_percent": _pct(len(done), len(bookings)),
                  "median_days_to_result": median(days_to_result) if days_to_result else None},
        "referrals": {"made": len(referrals), "scheduled": ref_status["scheduled"], "completed": ref_status["completed"],
                      "declined": ref_status["declined"], **stuck_referrals(referrals, now)},
        "caregiving": {"people_with_reminders": len(circles), "doses_scheduled_28d": scheduled, "doses_taken_28d": taken,
                       "adherence_percent": _pct(taken, scheduled)},
        "survey": survey,
    }


def _shown(n) -> str:
    """Hide small counts (1-4) in what's shared."""
    if isinstance(n, int) and 0 < n < SMALL:
        return f"<{SMALL}"
    return "" if n is None else str(n)


def to_csv(r: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Section", "Measure", "Value"])
    w.writerow(["Report", "Generated", r["generated_at"][:10]])
    st = r.get("study") or {}
    if st.get("consent_required"):
        w.writerow(["Report", "Counts only study participants (information sheet version)", st["version"]])
        w.writerow(["Report", "Participants", _shown(st["active"])])
        w.writerow(["Report", "Withdrew", _shown(st["withdrawn"])])
    labels = {
        "families": {"total": "Families taking part", "with_relatives": "Added at least one relative",
                     "with_three_generations": "Recorded three generations", "median_relatives": "Median relatives recorded",
                     "added_a_document": "Added a lab report or prescription", "active_last_7_days": "Used the app in the last 7 days"},
        "tests": {"booked": "Tests booked", "completed": "Tests completed", "completion_rate_percent": "Completion rate (%)",
                  "median_days_to_result": "Median days from booking to result"},
        "referrals": {"made": "Referrals made by clinics", "scheduled": "Referrals scheduled", "completed": "Referrals completed",
                      "declined": "Referrals declined"},
        "caregiving": {"people_with_reminders": "People with medicine reminders", "doses_scheduled_28d": "Doses scheduled (28 days)",
                       "doses_taken_28d": "Doses marked taken (28 days)", "adherence_percent": "Doses taken (%)"},
    }
    for section, names in labels.items():
        for key, label in names.items():
            value = r[section][key]
            w.writerow([section.capitalize(), label, value if "percent" in key or "median" in key else _shown(value)])
    w.writerow(["Findings", "Families with something to act on", _shown(r["findings"]["families_with_an_item"])])
    w.writerow(["Findings", "Families with an item to discuss soon", _shown(r["findings"]["families_with_an_item_to_discuss_soon"])])
    for title, n in r["findings"]["by_item"].items():
        w.writerow(["Findings", title, _shown(n)])
    for s in r["survey"].values():
        w.writerow(["Survey", s["question"] + " (responses)", _shown(s["responses"])])
        for answer, n in s["answers"].items():
            w.writerow(["Survey", f"{s['question']}: {answer.replace('_', ' ')}", _shown(n)])
    return out.getvalue()

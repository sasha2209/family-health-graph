"""Caregiver mode: daily medicine schedules, refill alerts and an emergency summary for a parent you look after.

Schedules come from the prescription as written. Indian prescriptions use the "1-0-1" morning-afternoon-night
notation, or abbreviations (OD, BD, TDS, HS, SOS), with a duration ("x 30 days") and food timing. A caregiver can
correct the schedule and record how many tablets are at home; refills are worked out from either.

The rest of caregiver mode (who may help care for whom, dose logs, emergency links) lives in fhg/storage.py and the
/v1/care endpoints in fhg/api.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from typing import Optional

from .models import FamilyMember, Medication

SLOTS = ("morning", "afternoon", "night")
SLOT_HOUR = {"morning": 8, "afternoon": 14, "night": 21}       # local time the reminder goes out
IST = timezone(timedelta(hours=5, minutes=30))
MISSED_AFTER_HOURS = 3                                          # a dose not marked by then is "missed"
REFILL_DAYS = 5                                                 # alert when this many days or fewer are left


@dataclass
class Schedule:
    slots: dict[str, float] = field(default_factory=dict)       # {"morning": 1, "night": 0.5}
    as_needed: bool = False
    days: Optional[int] = None                                  # course length, if prescribed
    food: Optional[str] = None                                  # "after food" | "before food" | "empty stomach"
    understood: bool = True                                     # False when the text couldn't be read

    @property
    def per_day(self) -> float:
        return sum(self.slots.values())


_PATTERN = re.compile(r"(?<![\d/])([0-9½¼¾]+(?:/\d)?)\s*[-–]\s*([0-9½¼¾]+(?:/\d)?)\s*[-–]\s*([0-9½¼¾]+(?:/\d)?)"
                      r"(?:\s*[-–]\s*([0-9½¼¾]+(?:/\d)?))?(?![\d/])")
_ABBR = [
    (re.compile(r"\b(?:qid|qds|four times(?: a| per)? day)\b", re.I), {"morning": 1, "afternoon": 1, "night": 2}),
    (re.compile(r"\b(?:tds|tid|thrice daily|three times(?: a| per)? day)\b", re.I),
     {"morning": 1, "afternoon": 1, "night": 1}),
    (re.compile(r"\b(?:bd|bid|twice daily|twice a day|two times(?: a| per)? day)\b", re.I), {"morning": 1, "night": 1}),
    (re.compile(r"\b(?:hs|at bed ?time|at night|night only|raat ko)\b", re.I), {"night": 1}),
    (re.compile(r"\b(?:od|qd|once daily|once a day|daily|every morning|in the morning|subah)\b", re.I), {"morning": 1}),
]
_AS_NEEDED = re.compile(r"\b(?:sos|prn|as needed|when needed|if needed|if required)\b", re.I)
_DAYS = re.compile(r"(?:x|for|×)?\s*(\d+)\s*(days?|d|weeks?|wks?|months?)\b", re.I)
_FOOD = [("before food", re.compile(r"\b(?:before|bf)\s*(?:food|meals?|breakfast)|\bac\b", re.I)),
         ("empty stomach", re.compile(r"empty\s+stomach", re.I)),
         ("after food", re.compile(r"\b(?:after|af)\s*(?:food|meals?|breakfast|lunch|dinner)|\bpc\b", re.I))]


def _amount(text: str) -> float:
    text = text.replace("½", "1/2").replace("¼", "1/4").replace("¾", "3/4")
    return float(sum(Fraction(p) for p in re.findall(r"\d+/\d+|\d+", text))) if text else 0.0


def parse_schedule(dosage: Optional[str]) -> Schedule:
    text = dosage or ""
    s = Schedule()
    m = _PATTERN.search(text)
    if m:
        parts = [g for g in m.groups() if g is not None]
        names = SLOTS if len(parts) == 3 else ("morning", "afternoon", "evening", "night")
        for name, amount in zip(names, parts):
            value = _amount(amount)
            if value:
                slot = "night" if name == "evening" else name
                s.slots[slot] = s.slots.get(slot, 0) + value
    else:
        for rx, slots in _ABBR:
            if rx.search(text):
                s.slots = {k: float(v) for k, v in slots.items()}
                break
    s.as_needed = bool(_AS_NEEDED.search(text))
    for m in _DAYS.finditer(text):
        unit = m.group(2).lower()
        n = int(m.group(1))
        s.days = n * (30 if unit.startswith("m") else 7 if unit.startswith("w") else 1)
    s.food = next((name for name, rx in _FOOD if rx.search(text)), None)
    s.understood = bool(s.slots) or s.as_needed
    return s


def schedule_for(med: Medication) -> Schedule:
    """The caregiver's own schedule if they set one, otherwise what the prescription says."""
    s = parse_schedule(med.dosage)
    if med.schedule is not None:
        s.slots = {k: v for k, v in med.schedule.items() if k in SLOTS and v}
        s.understood = True
    return s


def refill(med: Medication, today: date) -> Optional[dict]:
    """Days of medicine left and the date it runs out, from tablets at home or from the course length."""
    s = schedule_for(med)
    if med.status != "active" or s.as_needed or not s.per_day:
        return None
    if med.stock is not None and med.stock_on:
        used = (today - med.stock_on).days * s.per_day
        left = max(med.stock - used, 0)
        days_left = int(left // s.per_day)
        basis = "stock"
    elif s.days and med.prescribed_on:
        days_left = max((med.prescribed_on + timedelta(days=s.days) - today).days, 0)
        basis = "course"
    else:
        return None
    return {"days_left": days_left, "runs_out_on": (today + timedelta(days=days_left)).isoformat(), "basis": basis,
            "due": days_left <= REFILL_DAYS}


def doses_for_day(member: FamilyMember, day: date, log: list[dict], now: Optional[datetime] = None) -> list[dict]:
    """Every scheduled dose for the day, with its status: taken | skipped | missed | due | upcoming."""
    now = (now or datetime.now(IST)).astimezone(IST)
    marked = {(e["med_id"], e["slot"]): e for e in log if e["day"] == day.isoformat()}
    out = []
    for med in member.medications:
        if med.status != "active" or not med.reminders or (med.prescribed_on and med.prescribed_on > day):
            continue
        s = schedule_for(med)
        for slot in SLOTS:
            if slot not in s.slots:
                continue
            at = datetime.combine(day, datetime.min.time(), IST).replace(hour=SLOT_HOUR[slot])
            entry = marked.get((med.id, slot))
            if entry:
                status = entry["status"]
            elif now >= at + timedelta(hours=MISSED_AFTER_HOURS):
                status = "missed"
            elif now >= at:
                status = "due"
            else:
                status = "upcoming"
            out.append({"med_id": med.id, "name": med.name, "generic": med.generic, "slot": slot,
                        "amount": s.slots[slot], "food": s.food, "at": at.isoformat(), "status": status,
                        "by": entry.get("by_name") if entry else None})
    return sorted(out, key=lambda d: (SLOTS.index(d["slot"]), d["name"].lower()))


ALERT_TEXT = {
    "en": {"dose": "Time for {who}'s {slot} medicines: {names}.",
           "missed": "{who}'s {slot} medicines haven't been marked as taken: {names}.",
           "refill_today": "{who}'s {med} runs out today. Time to reorder.",
           "refill_1": "{who}'s {med} has 1 day left. Time to reorder.",
           "refill_n": "{who}'s {med} has {n} days left. Time to reorder.",
           "morning": "morning", "afternoon": "afternoon", "night": "night"},
    "hi": {"dose": "{who} की {slot} की दवाइयों का समय: {names}।",
           "missed": "{who} की {slot} की दवाइयाँ अभी तक ली गई दर्ज नहीं हुईं: {names}।",
           "refill_today": "{who} की {med} आज ख़त्म हो जाएगी। फिर से मँगाने का समय है।",
           "refill_1": "{who} की {med} 1 दिन की बची है। फिर से मँगाने का समय है।",
           "refill_n": "{who} की {med} {n} दिन की बची है। फिर से मँगाने का समय है।",
           "morning": "सुबह", "afternoon": "दोपहर", "night": "रात"},
}


def due_care_alerts(now: datetime, who: str, member: FamilyMember, log: list[dict],
                    lang: str = "en") -> list[tuple[str, str]]:
    """[(dedupe key, message)] for one person being cared for, at ``now``. Run hourly.

    * the slot's reminder, in the slot's hour;
    * a missed-dose notice MISSED_AFTER_HOURS later if nobody marked it;
    * a refill alert once a day (at the morning slot) while REFILL_DAYS or fewer are left."""
    tx = ALERT_TEXT.get(lang, ALERT_TEXT["en"])
    now = now.astimezone(IST)
    today = now.date()
    out = []
    doses = doses_for_day(member, today, log, now)
    for slot in SLOTS:
        in_slot = [d for d in doses if d["slot"] == slot]
        if not in_slot:
            continue
        names = ", ".join(sorted({d["name"] for d in in_slot}))
        if now.hour == SLOT_HOUR[slot] and any(d["status"] == "due" for d in in_slot):
            out.append((f"dose:{member.id}:{today}:{slot}", tx["dose"].format(who=who, slot=tx[slot], names=names)))
        if now.hour == SLOT_HOUR[slot] + MISSED_AFTER_HOURS and any(d["status"] == "missed" for d in in_slot):
            out.append((f"missed:{member.id}:{today}:{slot}", tx["missed"].format(who=who, slot=tx[slot], names=names)))
    if now.hour == SLOT_HOUR["morning"]:
        for med in member.medications:
            r = refill(med, today) if med.reminders else None
            if r and r["due"]:
                key = "refill_today" if r["days_left"] == 0 else "refill_1" if r["days_left"] == 1 else "refill_n"
                out.append((f"refill:{med.id}:{today}", tx[key].format(who=who, med=med.name, n=r["days_left"])))
    return out


# --- reminders on the cared-for person's own WhatsApp ----------------------------------------------
# Business-initiated WhatsApp messages must use templates Meta has approved (docs/CAREGIVER_MODE.md lists their
# text). Replies within 24 hours of the person writing can be free text: these.
WA_TEXT = {
    "en": {"active": "You'll get your medicine reminders here. Reply 1 when you've taken them, or STOP to end them.",
           "stopped": "Medicine reminders are off. Your family can turn them on again in the app.",
           "taken": "Marked as taken: {names}. Thank you!",
           "nothing_due": "There's nothing to mark right now. Your next reminder will come at the usual time.",
           "help": "Reply 1 when you've taken your medicines, or STOP to end the reminders."},
    "hi": {"active": "आपको दवा के रिमाइंडर यहीं मिलेंगे। दवा लेने के बाद 1 भेजें, या बंद करने के लिए STOP भेजें।",
           "stopped": "दवा के रिमाइंडर बंद हैं। आपका परिवार ऐप में इन्हें फिर से चालू कर सकता है।",
           "taken": "ली गई दर्ज की गई: {names}। धन्यवाद!",
           "nothing_due": "अभी दर्ज करने के लिए कुछ नहीं है। अगला रिमाइंडर हमेशा के समय पर आएगा।",
           "help": "दवा लेने के बाद 1 भेजें, या रिमाइंडर बंद करने के लिए STOP भेजें।"},
}
WA_SLOT = {"en": {"morning": "morning", "afternoon": "afternoon", "night": "night"},
           "hi": {"morning": "सुबह", "afternoon": "दोपहर", "night": "रात"}}
WA_YES = {"yes", "y", "ha", "haan", "han", "हाँ", "हां", "ok", "start"}
WA_STOP = {"stop", "रोको", "बंद", "band", "no", "nahi", "नहीं"}
WA_TAKEN = {"1", "taken", "done", "le li", "le liya", "ले ली", "ले लिया", "li", "ली", "ho gaya", "हो गया"}


def wa_text(lang: str, key: str, **values) -> str:
    return WA_TEXT.get(lang, WA_TEXT["en"])[key].format(**values)


def normalize_phone(raw: str) -> str:
    """Digits with country code; a 10-digit number is taken as Indian. Raises ValueError if it can't be a number."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        digits = "91" + digits
    if not 11 <= len(digits) <= 15:
        raise ValueError("Enter a WhatsApp number with its country code, like +91 98123 45678")
    return digits


def latest_open_slot(member: FamilyMember, log: list[dict], now: datetime) -> Optional[str]:
    """The most recent slot today with doses not yet marked: what a reply of "1" refers to."""
    doses = doses_for_day(member, now.astimezone(IST).date(), log, now)
    open_slots = [d["slot"] for d in doses if d["status"] in ("due", "missed")]
    return open_slots[-1] if open_slots else None


def wa_reminders_due(now: datetime, member: FamilyMember, log: list[dict]) -> list[tuple[str, str, list[str]]]:
    """[(dedupe key, slot, medicine names)] to send to the person's own WhatsApp in this hour."""
    now = now.astimezone(IST)
    today = now.date()
    out = []
    doses = doses_for_day(member, today, log, now)
    for slot in SLOTS:
        due = [d for d in doses if d["slot"] == slot and d["status"] == "due"]
        if due and now.hour == SLOT_HOUR[slot]:
            out.append((f"wa:{member.id}:{today}:{slot}", slot, sorted({d["name"] for d in due})))
    return out

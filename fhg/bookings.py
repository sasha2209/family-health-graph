"""From insight to booked test to result, and reminders until it's done.

An action item that a test can answer (a rising HbA1c, inherited high cholesterol, a hereditary-cancer pattern)
offers the matching tests from lab and counseling partners: price, home collection. Booking sends the lab a
health-data-free webhook; the lab reads the booking (tests, slot, and the contact details the person chose to
share) with its API key, reports progress, and posts the results as FHIR Observations, which go straight into
the person's record and update their insights. Reminders follow up until the test is booked and done.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from .insights.lang import join_and, language, tr
from .notices import LAB_UNCONFIRMED, RESULTS_LATE, TEST_REMINDER, say

# Bookable tests. `observations` are the result codes that may be posted back for the test.
TESTS: dict[str, dict] = {
    "hba1c": {"name": "HbA1c (3-month blood sugar)", "observations": {"hba1c"},
              "prep": "No fasting needed."},
    "fasting_glucose": {"name": "Fasting blood sugar", "observations": {"fasting_glucose"},
                        "prep": "Don't eat for 8–10 hours before; water is fine."},
    "lipid_profile": {"name": "Lipid profile (cholesterol)",
                      "observations": {"ldl_cholesterol", "hdl_cholesterol", "total_cholesterol", "triglycerides"},
                      "prep": "Fasting for 10–12 hours is usually advised; check with the lab."},
    "lipoprotein_a": {"name": "Lipoprotein(a)", "observations": {"lipoprotein_a"}, "prep": "No fasting needed."},
    "kidney_function": {"name": "Kidney function (creatinine, eGFR)", "observations": {"creatinine", "egfr"},
                        "prep": "No fasting needed."},
    "genetic_counseling": {"name": "Genetic counseling consultation", "observations": set(), "service": True,
                           "prep": "Have your family history open in the app during the call."},
}

# Which tests answer which action item.
RECOMMENDED: dict[str, list[str]] = {
    "diabetes_risk": ["hba1c", "fasting_glucose"],
    "indian_diabetes_risk": ["hba1c", "fasting_glucose"],
    "familial_hypercholesterolemia": ["lipid_profile", "lipoprotein_a"],
    "premature_ascvd_family_history": ["lipid_profile", "lipoprotein_a"],
    "hboc_family_pattern": ["genetic_counseling"],
    "colorectal_family_history": ["genetic_counseling"],
    "lynch_criteria": ["genetic_counseling"],
}

ACTIVE = ("requested", "scheduled", "sample_collected")
PARTNER_STATUSES = ("scheduled", "sample_collected", "completed", "cancelled")
SLOTS = ("morning", "afternoon", "evening")

# Follow-through: one nudge per due item at most every NUDGE_DAYS, at most MAX_NUDGES in all.
NUDGE_DAYS = 7
MAX_NUDGES = 3
UNCONFIRMED_DAYS = 2      # a lab hasn't confirmed a request
OVERDUE_DAYS = 2          # the visit date has passed without results


def offers(rule_id: str, partners: list[dict]) -> list[dict]:
    """Tests for an action item, each with the partners that offer it."""
    out = []
    for code in RECOMMENDED.get(rule_id, []):
        test = TESTS[code]
        rows = [{"partner_id": p["id"], "partner_name": p["name"], "price_inr": item.get("price_inr"),
                 "home_collection": bool(item.get("home_collection")), "turnaround_days": item.get("turnaround_days")}
                for p in partners for item in p.get("catalog") or [] if item.get("test") == code]
        out.append({"test": code, "name": test["name"], "prep": test["prep"], "service": bool(test.get("service")),
                    "offers": sorted(rows, key=lambda r: (r["price_inr"] is None, r["price_inr"] or 0))})
    return out


def due_reminders(now: datetime, insights: list, bookings: list[dict], nudges: list[dict],
                  lang: str = "en") -> list[tuple[str, str, str]]:
    """What to remind one person about: [(key, kind, message)]. ``key`` de-duplicates nudges."""
    out = []
    sent = {}
    for n in nudges:
        sent.setdefault(n["key"], []).append(datetime.fromisoformat(n["sent_at"]))

    def allowed(key: str) -> bool:
        times = sent.get(key, [])
        return len(times) < MAX_NUDGES and all(now - t >= timedelta(days=NUDGE_DAYS) for t in times)

    for b in bookings:
        key = f"booking:{b['id']}"
        if b["status"] == "requested" and now - datetime.fromisoformat(b["created_at"]) >= timedelta(days=UNCONFIRMED_DAYS):
            if allowed(key):
                out.append((key, "booking", say(lang, LAB_UNCONFIRMED, partner=b["partner_name"])))
        elif b["status"] in ("scheduled", "sample_collected") and b.get("scheduled_for"):
            when = date.fromisoformat(b["scheduled_for"][:10])
            if (now.date() - when).days >= OVERDUE_DAYS and allowed(key):
                out.append((key, "booking", say(lang, RESULTS_LATE, partner=b["partner_name"])))
    handled = {b["rule_id"] for b in bookings if b.get("rule_id") and (b["status"] in ACTIVE or b["status"].startswith("completed"))}
    for insight in insights:
        rid = insight.rule_id
        if rid in RECOMMENDED and rid not in handled and allowed(f"insight:{rid}"):
            with language(lang):
                names = join_and([tr(TESTS[c]["name"].split(" (")[0]) for c in RECOMMENDED[rid]])
            out.append((f"insight:{rid}", "reminder", say(lang, TEST_REMINDER, item=insight.title, tests=names)))
    return out


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

"""In-app notices in the recipient's language.

Each notice is an English template (the key) with Hindi in fhg/notices_hi.py. ``say(lang, template, **values)``
fills it in; values named in ``translate`` (relationships, conditions, test and program names) are translated too.
tests/test_insight_language.py checks every template has Hindi.
"""
from __future__ import annotations

from typing import Iterable

from .insights.lang import language, mark, tr

# Templates, by where they are sent from.
DOCS_ONE = mark("1 document arrived by {channel} and is waiting for your review.")
DOCS_MANY = mark("{n} documents arrived by {channel} and are waiting for your review.")
REFERRED = mark("{org} referred you for: {program}. Contact your clinic if you have questions.")
REFERRED_WITH = mark("{org} referred you for: {program}, with {partner}. Contact your clinic if you have questions.")
SCHEDULED = mark("{org} scheduled your: {program}. Contact your clinic if you have questions.")
SCHEDULED_WITH = mark("{org} scheduled your: {program}, with {partner}. Contact your clinic if you have questions.")
PARTNER_SCHEDULED = mark("{partner} scheduled your appointment: {program}. They or your clinic will be in touch "
                         "with details.")
RISK_SHARED = mark("{partner} shared your {model} risk assessment.")
BOOKING_CONFIRMED = mark("{partner} confirmed your {tests}.")
BOOKING_CONFIRMED_ON = mark("{partner} confirmed your {tests} for {date}.")
BOOKING_SAMPLE = mark("{partner} has collected your sample. Results will appear in the app.")
BOOKING_DONE = mark("{partner} has completed your {tests}.")
BOOKING_CANCELLED = mark("{partner} cancelled your {tests} booking.")
BOOKING_CANCELLED_NOTE = mark("{partner} cancelled your {tests} booking: {note}")
RESULTS_IN = mark("Your test results from {partner} are in. Your insights have been updated.")
LAB_UNCONFIRMED = mark("{partner} hasn't confirmed your test booking yet. You can wait, or cancel and choose another "
                       "lab in the app.")
RESULTS_LATE = mark("Your results from {partner} aren't in yet. If the test was done, they'll appear in the app once "
                    "the lab sends them.")
TEST_REMINDER = mark("Reminder: {item}. A {tests} test is the next step; you can book one in the app.")
INVITE_ACCEPTED = mark("Your {who} accepted your invitation. Your insights now include what they share.")
INVITE_ACCEPTED_NOT_SHARING = mark("Your {who} accepted your invitation but isn't sharing their history yet.")
PRIVACY_ANSWER = mark("Answer to your privacy concern: {answer}")
CARE_JOINED = mark("{name} joined the care circle for {who}.")
SOMEONE = mark("Someone")
EMERGENCY_OPENED = mark("{who}'s emergency summary was just opened from a shared link.")
FAMILY_CASCADE = mark("Your {who} shared a result that can run in families ({conditions}). Your insights have been "
                      "updated. This may affect what screening or testing is right for you, so consider discussing "
                      "it with your clinician or a genetic counselor.")
CHANNELS = {"email": mark("email"), "WhatsApp": mark("WhatsApp")}

# Names that appear inside notices.
PROGRAM_NAMES = [mark(x) for x in (
    "Genetic counseling: hereditary breast/ovarian cancer", "Earlier colorectal screening / Lynch evaluation",
    "Genetic counseling: Lynch syndrome", "Lipid clinic: possible familial hypercholesterolemia",
    "Cardiovascular risk assessment", "Diabetes screening / prevention program", "Earlier prostate cancer screening",
    "Anesthesia safety alert", "Blood pressure follow-up")]
TEST_NAMES = [mark(x) for x in ("HbA1c", "Fasting blood sugar", "Lipid profile", "Lipoprotein(a)", "Kidney function",
                                "Genetic counseling consultation")]


def say(lang: str, template: str, translate: Iterable[str] = (), **values) -> str:
    """The notice in ``lang``. Values whose names are in ``translate`` are translated as well; a value that is a
    list is translated item by item and joined with commas."""
    with language(lang):
        for key in translate:
            v = values[key]
            values[key] = ", ".join(tr(x) for x in v) if isinstance(v, (list, tuple)) else tr(v)
        return tr(template, **values)

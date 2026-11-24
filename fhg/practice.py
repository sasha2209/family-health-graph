"""A practice clinic for staff training: made-up families that cover every care program and referral status.

Clinic staff rehearse on it before the pilot (docs/PILOT.md, "Staff training"): the worklist, a patient summary,
setting a referral, the funnel. Its patients are invented, are kept out of the pilot report and counts, can't be
joined by a real patient, and its referrals are never sent to a partner. The console creates and deletes it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .models import Condition, FamilyMember, HealthProfile, Observation, Relationship, Sex
from .terminology import CONCEPTS_BY_CATEGORY

R = Relationship


@dataclass
class PracticeFamily:
    name: str
    sex: Sex
    born: int
    relatives: list[tuple[Relationship, list[tuple[str, Optional[int]]]]]
    own: list[tuple[str, Optional[int]]] = field(default_factory=list)
    labs: dict[str, float] = field(default_factory=dict)
    referrals: dict[str, str] = field(default_factory=dict)        # rule_id → status
    activity: Optional[str] = None
    days_ago: int = 3                       # when they connected and their referrals last changed: some have waited
                                            # long enough to show under "Needs attention"


UNITS = {"ldl_cholesterol": "mg/dL", "hba1c": "%", "bmi": "kg/m2", "systolic_bp": "mmHg", "diastolic_bp": "mmHg",
         "waist_circumference": "cm"}

# Every care program appears at least once, with every referral status, plus families with little to act on.
FAMILIES = [
    PracticeFamily("Sunita Kulkarni", Sex.FEMALE, 1978,
                   [(R.MOTHER, [("breast_cancer", 44)]), (R.MATERNAL_AUNT, [("ovarian_cancer", 58)])],
                   referrals={"hboc_family_pattern": "referred"}, days_ago=20),
    PracticeFamily("Rajesh Deshpande", Sex.MALE, 1975,
                   [(R.FATHER, [("colorectal_cancer", 48)]), (R.PATERNAL_GRANDFATHER, [("colorectal_cancer", 70)]),
                    (R.PATERNAL_AUNT, [("endometrial_cancer", 45)])],
                   referrals={"lynch_criteria": "scheduled"}, days_ago=40),
    PracticeFamily("Meera Joshi", Sex.FEMALE, 1985, [(R.FATHER, [("familial_hypercholesterolemia", 38)])],
                   labs={"ldl_cholesterol": 205}, referrals={"familial_hypercholesterolemia": "completed"}),
    PracticeFamily("Anil Patil", Sex.MALE, 1970,
                   [(R.FATHER, [("coronary_artery_disease", 49)]), (R.BROTHER, [("coronary_artery_disease", 52)])],
                   labs={"ldl_cholesterol": 168}, referrals={"premature_ascvd_family_history": "referred"}),
    PracticeFamily("Priya Shinde", Sex.FEMALE, 1982,
                   [(R.MOTHER, [("type_2_diabetes", 45)]), (R.FATHER, [("type_2_diabetes", 50)])],
                   labs={"hba1c": 6.2, "bmi": 27.4, "waist_circumference": 92}, activity="sedentary",
                   referrals={"diabetes_risk": "declined"}),
    PracticeFamily("Vijay Pawar", Sex.MALE, 1965,
                   [(R.FATHER, [("prostate_cancer", 58)]), (R.BROTHER, [("prostate_cancer", 62)])]),
    PracticeFamily("Kavita Gokhale", Sex.FEMALE, 1990, [(R.MATERNAL_UNCLE, [("malignant_hyperthermia", None)])]),
    PracticeFamily("Sanjay More", Sex.MALE, 1968, [(R.MOTHER, [("hypertension", 50)])],
                   labs={"systolic_bp": 168, "diastolic_bp": 104}, referrals={"blood_pressure": "referred"}),
    PracticeFamily("Smita Apte", Sex.FEMALE, 1980,
                   [(R.MOTHER, [("ovarian_cancer", 52)]), (R.SISTER, [("hboc_variant", None), ("breast_cancer", 39)])],
                   referrals={"hboc_family_pattern": "completed"}),
    PracticeFamily("Ganesh Kale", Sex.MALE, 1972,
                   [(R.FATHER, [("stroke", 54), ("type_2_diabetes", 48)]), (R.MOTHER, [("type_2_diabetes", None)])],
                   labs={"hba1c": 6.0, "bmi": 28.1}),
    PracticeFamily("Rohan Kadam", Sex.MALE, 1987, [(R.MOTHER, [("colorectal_cancer", 55)])],
                   referrals={"colorectal_family_history": "scheduled"}),
    PracticeFamily("Lata Wagh", Sex.FEMALE, 1958, [(R.MOTHER, [("type_2_diabetes", 55)])],
                   labs={"hba1c": 7.1, "systolic_bp": 150, "diastolic_bp": 95}, days_ago=12),
    PracticeFamily("Ashwini Bhosale", Sex.FEMALE, 1988, [(R.MOTHER, [("hypertension", 60)])]),
    PracticeFamily("Neha Jadhav", Sex.FEMALE, 1995, [(R.MATERNAL_GRANDMOTHER, [("dementia", 78)])]),
]


def profile(f: PracticeFamily, user_id: str, today: Optional[date] = None) -> HealthProfile:
    today = today or date.today()

    def cond(category: str, age: Optional[int]) -> Condition:
        return Condition(name=CONCEPTS_BY_CATEGORY[category].display, category=category, onset_age=age,
                         source="practice")

    return HealthProfile(
        user_id=user_id, sex=f.sex, birth_date=date(f.born, 6, 15), activity=f.activity,
        conditions=[cond(c, a) for c, a in f.own],
        observations=[Observation(code=k, value=v, unit=UNITS.get(k, ""), effective_date=today, source="practice")
                      for k, v in f.labs.items()],
        family=[FamilyMember(relationship=rel, conditions=[cond(c, a) for c, a in conds], source="practice")
                for rel, conds in f.relatives],
    )

"""A family tree with real parent links, built from the relatives a person has recorded.

The record stores relatives by their relationship to the person ("maternal aunt", "sister"). Hereditary risk
models need an actual tree: who is whose parent, so that, say, a maternal aunt and the mother are sisters. This
module places every relative it can, adds unaffected placeholder people where the tree needs a link that wasn't
recorded (an aunt's partner, the parent a cousin descends from), and reports anyone it couldn't place.

Placeholders carry no conditions and no age, so they add structure without adding information.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .models import FamilyMember, HealthProfile, Relationship as R


@dataclass
class Cancer:
    category: str
    age: Optional[int]          # age at diagnosis; None when unknown


@dataclass
class Person:
    id: str                      # short, stable within one tree: "P", "M", "MGM", "R3", "X2"
    sex: str                     # "M" | "F"
    label: str                   # "You", "Mother", "Maternal aunt", "Placeholder"
    generation: int              # 0 = the person, -1 = parents, +1 = children
    father: Optional[str] = None
    mother: Optional[str] = None
    age: Optional[int] = None
    yob: Optional[int] = None
    dead: bool = False
    placeholder: bool = False
    proband: bool = False
    member_id: Optional[str] = None
    conditions: list[Cancer] = field(default_factory=list)


@dataclass
class Pedigree:
    people: dict[str, Person]
    skipped: list[str]           # relatives that couldn't be placed, with the reason

    @property
    def proband(self) -> Person:
        return next(p for p in self.people.values() if p.proband)

    def real(self) -> list[Person]:
        return [p for p in self.people.values() if not p.placeholder]

    # --- relatedness ------------------------------------------------------------------------
    def _ancestors(self, pid: str) -> dict[str, int]:
        out, frontier, d = {pid: 0}, [pid], 0
        while frontier:
            d += 1
            nxt = []
            for x in frontier:
                p = self.people[x]
                for parent in (p.father, p.mother):
                    if parent and parent not in out:
                        out[parent] = d
                        nxt.append(parent)
            frontier = nxt
        return out

    def degree(self, a: str, b: str) -> Optional[int]:
        """Degree of relationship: 1 = parent/child/full sibling, 2 = grandparent/aunt/half-sibling, 3 = cousin."""
        if a == b:
            return 0
        aa, bb = self._ancestors(a), self._ancestors(b)
        if b in aa:
            return aa[b]
        if a in bb:
            return bb[a]
        best = None
        for anc in set(aa) & set(bb):
            d = aa[anc] + bb[anc]
            partner_shared = any(
                q != anc and q in aa and q in bb and aa[q] == aa[anc] and bb[q] == bb[anc]
                and self._are_partners(anc, q) for q in aa)
            if partner_shared:
                d -= 1                 # descended from the same couple: a full relative
            best = d if best is None else min(best, d)
        return best

    def _are_partners(self, x: str, y: str) -> bool:
        return any({c.father, c.mother} == {x, y} for c in self.people.values())


_CANCERS = {"breast_cancer", "ovarian_cancer", "prostate_cancer", "pancreatic_cancer", "colorectal_cancer",
            "endometrial_cancer", "stomach_cancer"}

SIDES = {"maternal": ("M", "MGF", "MGM"), "paternal": ("F", "PGF", "PGM")}


def _sex(m: FamilyMember) -> Optional[str]:
    s = m.effective_sex
    return {"female": "F", "male": "M"}.get(s or "")


def build(profile: HealthProfile, today: Optional[date] = None) -> Pedigree:
    """Raise ValueError when the person's own sex isn't recorded (every model needs it)."""
    today = today or date.today()
    own_sex = {"female": "F", "male": "M"}.get(profile.sex.value if profile.sex else "")
    if not own_sex:
        raise ValueError("Add your sex at birth in your profile first; risk models need it.")
    people: dict[str, Person] = {}
    skipped: list[str] = []
    counter = {"R": 0, "X": 0}

    def new_id(prefix: str) -> str:
        counter[prefix] += 1
        return f"{prefix}{counter[prefix]}"

    def placeholder(sex: str, generation: int, pid: Optional[str] = None, **links) -> str:
        pid = pid or new_id("X")
        people[pid] = Person(pid, sex, "Placeholder", generation, placeholder=True, **links)
        return pid

    def ensure(pid: str) -> str:
        """The fixed slots: parents and grandparents, created as placeholders when not recorded."""
        if pid in people:
            return pid
        gen, sex = {"M": (-1, "F"), "F": (-1, "M"), "MGM": (-2, "F"), "MGF": (-2, "M"),
                    "PGM": (-2, "F"), "PGF": (-2, "M")}[pid]
        links = {}
        if pid in ("M", "F"):
            father, mother = ("MGF", "MGM") if pid == "M" else ("PGF", "PGM")
            # Grandparents are linked lazily: only when a grandparent or aunt/uncle is actually recorded.
            if father in people or mother in people:
                links = {"father": ensure(father), "mother": ensure(mother)}
        return placeholder(sex, gen, pid, **links)

    def link_parents_to_grandparents(side: str) -> None:
        parent, gf, gm = SIDES[side]
        ensure(parent)
        people[parent].father, people[parent].mother = ensure(gf), ensure(gm)

    yob = profile.birth_date.year if profile.birth_date else None
    people["P"] = Person("P", own_sex, "You", 0, age=profile.age(today), yob=yob, proband=True,
                         conditions=[Cancer(c.category, c.onset_age) for c in profile.conditions if c.category in _CANCERS])

    fixed = {R.MOTHER: "M", R.FATHER: "F", R.MATERNAL_GRANDMOTHER: "MGM", R.MATERNAL_GRANDFATHER: "MGF",
             R.PATERNAL_GRANDMOTHER: "PGM", R.PATERNAL_GRANDFATHER: "PGF"}

    def fill(pid: str, m: FamilyMember, generation: int, sex: str, **links) -> Person:
        person = people.get(pid) or Person(pid, sex, m.label, generation)
        person.placeholder, person.label, person.member_id = False, m.label, m.id
        person.sex, person.age, person.dead = sex, m.age, bool(m.deceased)
        person.conditions = [Cancer(c.category, c.onset_age) for c in m.conditions if c.category in _CANCERS]
        for k, v in links.items():
            setattr(person, k, v)
        people[pid] = person
        return person

    # Parents and grandparents first, so everyone else can hang off them.
    for m in sorted(profile.family, key=lambda m: m.relationship not in fixed):
        rel, sex = m.relationship, _sex(m)
        if rel in fixed:
            pid = fixed[rel]
            if pid in people and not people[pid].placeholder:
                skipped.append(f"{m.label}: recorded twice; only the first is used")
                continue
            fill(pid, m, -1 if pid in ("M", "F") else -2, {"M": "F", "F": "M"}.get(pid) or ("F" if pid.endswith("M") else "M"))
            if pid not in ("M", "F"):
                link_parents_to_grandparents("maternal" if pid.startswith("M") else "paternal")

    people["P"].mother, people["P"].father = ensure("M"), ensure("F")
    partner_of_p: Optional[str] = None

    for m in profile.family:
        rel, sex = m.relationship, _sex(m)
        if rel in fixed:
            continue
        if sex is None:
            skipped.append(f"{m.label}: sex not recorded")
            continue
        if rel in (R.SISTER, R.BROTHER, R.SIBLING):
            fill(new_id("R"), m, 0, sex, father="F", mother="M")
        elif rel in (R.DAUGHTER, R.SON, R.CHILD):
            if partner_of_p is None:
                partner_of_p = placeholder("M" if own_sex == "F" else "F", 0)
            dad, mum = ("P", partner_of_p) if own_sex == "M" else (partner_of_p, "P")
            fill(new_id("R"), m, 1, sex, father=dad, mother=mum)
        elif rel in (R.MATERNAL_AUNT, R.MATERNAL_UNCLE, R.PATERNAL_AUNT, R.PATERNAL_UNCLE):
            side = "maternal" if rel.value.startswith("maternal") else "paternal"
            link_parents_to_grandparents(side)
            _, gf, gm = SIDES[side]
            fill(new_id("R"), m, -1, sex, father=gf, mother=gm)
        elif rel in (R.MATERNAL_COUSIN, R.PATERNAL_COUSIN):
            # The cousin's parent (the aunt or uncle) isn't known: link through an unaffected placeholder.
            side = "maternal" if rel == R.MATERNAL_COUSIN else "paternal"
            link_parents_to_grandparents(side)
            _, gf, gm = SIDES[side]
            aunt = placeholder("F", -1, father=gf, mother=gm)
            spouse = placeholder("M", -1)
            fill(new_id("R"), m, 0, sex, father=spouse, mother=aunt)
        elif rel in (R.NIECE, R.NEPHEW):
            sib = placeholder("F", 0, father="F", mother="M")
            spouse = placeholder("M", 0)
            fill(new_id("R"), m, 1, sex, father=spouse, mother=sib)
        elif rel in (R.HALF_SISTER, R.HALF_BROTHER):
            skipped.append(f"{m.label}: which parent is shared isn't recorded")
        else:
            skipped.append(f"{m.label}: which side of the family isn't recorded")

    _drop_unused_grandparents(people)
    return Pedigree(people, skipped)


def _drop_unused_grandparents(people: dict[str, Person]) -> None:
    for side in SIDES.values():
        parent, gf, gm = side
        if all(people.get(g) and people[g].placeholder for g in (gf, gm)):
            children = [p for p in people.values() if p.father == gf or p.mother == gm]
            if all(c.id == parent for c in children):
                people.pop(gf, None)
                people.pop(gm, None)
                people[parent].father = people[parent].mother = None

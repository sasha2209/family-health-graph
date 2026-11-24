"""Family invitations and linked relatives: the platform's growth loop.

A user invites a relative with a single-use link. When the relative accepts,
the two accounts are *linked*, and each side independently chooses what it
shares with the other:

* ``none``                 nothing (the link still exists)
* ``conditions``           their own diagnoses and ages at diagnosis
* ``conditions_and_tree``  the above plus the family history they've recorded,
                           re-expressed from the other person's point of view
                           (your mother's sister becomes your maternal aunt)

Shared data is never copied into the other person's record. It is merged into
an *effective profile* each time insights are generated, so revoking sharing
or unlinking takes effect immediately and nothing lingers.

Shared data feeds only that person's insights. It is never forwarded to
partners or included in exports or research: the relative consented to share
with a family member, not with third parties.
"""
from __future__ import annotations

from typing import Callable, Optional

from .merge import find_match, merge_conditions
from .models import Condition, FamilyMember, HealthProfile, Relationship as R
from .storage import Store
from .terminology import CONCEPTS_BY_CATEGORY

SHARE_LEVELS = ("none", "conditions", "conditions_and_tree")

# Results where a diagnosis in one person directly changes what their blood
# relatives should do (cascade testing / screening / safety precautions).
CASCADE_CATEGORIES = {
    "hboc_variant",
    "lynch_syndrome",
    "familial_hypercholesterolemia",
    "malignant_hyperthermia",
}

_GRANDPARENTS = {R.MATERNAL_GRANDMOTHER, R.MATERNAL_GRANDFATHER, R.PATERNAL_GRANDMOTHER,
                 R.PATERNAL_GRANDFATHER, R.GRANDMOTHER, R.GRANDFATHER}
_AUNTS_UNCLES = {R.MATERNAL_AUNT, R.MATERNAL_UNCLE, R.PATERNAL_AUNT, R.PATERNAL_UNCLE,
                 R.AUNT, R.UNCLE}


def inverse_relationship(rel: R, my_sex: Optional[str]) -> R:
    """If someone is my ``rel``, what am I to them?

    The parental side can't always be inferred (if I'm your niece, you could be
    my maternal or paternal aunt), so the result may be unsided; the person
    accepting an invitation can correct it.
    """
    def pick(female: R, male: R, generic: R) -> R:
        return female if my_sex == "female" else male if my_sex == "male" else generic

    if rel in (R.MOTHER, R.FATHER, R.PARENT):
        return pick(R.DAUGHTER, R.SON, R.CHILD)
    if rel in (R.DAUGHTER, R.SON, R.CHILD):
        return pick(R.MOTHER, R.FATHER, R.PARENT)
    if rel in (R.SISTER, R.BROTHER, R.SIBLING):
        return pick(R.SISTER, R.BROTHER, R.SIBLING)
    if rel in (R.HALF_SISTER, R.HALF_BROTHER):
        return pick(R.HALF_SISTER, R.HALF_BROTHER, R.OTHER)
    if rel in _GRANDPARENTS:
        return pick(R.GRANDDAUGHTER, R.GRANDSON, R.GRANDCHILD)
    if rel in (R.GRANDDAUGHTER, R.GRANDSON, R.GRANDCHILD):
        return pick(R.GRANDMOTHER, R.GRANDFATHER, R.OTHER)
    if rel in _AUNTS_UNCLES:
        return pick(R.NIECE, R.NEPHEW, R.OTHER)
    if rel in (R.NIECE, R.NEPHEW):
        return pick(R.AUNT, R.UNCLE, R.OTHER)
    if rel in (R.COUSIN, R.MATERNAL_COUSIN, R.PATERNAL_COUSIN):
        return R.COUSIN
    return R.OTHER


def _sided(side: str) -> dict[R, R]:
    return {
        R.MOTHER: R(f"{side}_grandmother"), R.FATHER: R(f"{side}_grandfather"),
        R.SISTER: R(f"{side}_aunt"), R.BROTHER: R(f"{side}_uncle"),
    }


_SIBLING_SHARED = {  # relatives a full sibling and I have in common
    r: r for r in (
        R.MOTHER, R.FATHER, R.MATERNAL_GRANDMOTHER, R.MATERNAL_GRANDFATHER,
        R.PATERNAL_GRANDMOTHER, R.PATERNAL_GRANDFATHER, R.GRANDMOTHER, R.GRANDFATHER,
        R.MATERNAL_AUNT, R.MATERNAL_UNCLE, R.PATERNAL_AUNT, R.PATERNAL_UNCLE, R.AUNT, R.UNCLE,
        R.MATERNAL_COUSIN, R.PATERNAL_COUSIN, R.COUSIN,
    )
}

# COMPOSE[a][x] = y: if A is my `a` and X is A's `x`, then X is my `y`.
# Deliberately limited to unambiguous cases. A parent's daughter, for example,
# could be me, my sister or my half-sister, so it is left out.
COMPOSE: dict[R, dict[R, R]] = {
    R.MOTHER: _sided("maternal"),
    R.FATHER: _sided("paternal"),
    R.SISTER: _SIBLING_SHARED,
    R.BROTHER: _SIBLING_SHARED,
    R.SIBLING: _SIBLING_SHARED,
    R.MATERNAL_AUNT: {R.MOTHER: R.MATERNAL_GRANDMOTHER, R.FATHER: R.MATERNAL_GRANDFATHER},
    R.MATERNAL_UNCLE: {R.MOTHER: R.MATERNAL_GRANDMOTHER, R.FATHER: R.MATERNAL_GRANDFATHER},
    R.PATERNAL_AUNT: {R.MOTHER: R.PATERNAL_GRANDMOTHER, R.FATHER: R.PATERNAL_GRANDFATHER},
    R.PATERNAL_UNCLE: {R.MOTHER: R.PATERNAL_GRANDMOTHER, R.FATHER: R.PATERNAL_GRANDFATHER},
}


def compose(link_rel: R, their_rel: R) -> Optional[R]:
    return COMPOSE.get(link_rel, {}).get(their_rel)


def _copy_conditions(conditions: list[Condition], source: str) -> list[Condition]:
    return [Condition(**c.model_dump(exclude={"id", "source"}), source=source) for c in conditions]


def _attach(profile: HealthProfile, member: FamilyMember, member_id: Optional[str]) -> None:
    """Merge a relative derived from a linked account into ``profile``."""
    target = next((m for m in profile.family if member_id and m.id == member_id), None)
    if target is None or target.relationship != member.relationship:
        target = find_match(profile.family, member)
    if target is None:
        profile.family.append(member)
        return
    merge_conditions(target.conditions, member.conditions)
    target.sex = target.sex or member.sex
    target.age = target.age if target.age is not None else member.age
    target.linked = True


def shared_fragment(link: dict, relative: HealthProfile) -> list[tuple[FamilyMember, Optional[str]]]:
    """What a linked relative shares, expressed from the viewer's point of view.

    ``link`` is the viewer's side of the link (``store.links_for`` row).
    Returns (member, viewer's member_id to merge into) pairs.
    """
    level = link["they_share"]
    if level == "none":
        return []
    rel = R(link["relationship"])
    source = f"linked:{link['link_id']}"
    out = [(FamilyMember(
        relationship=rel, sex=relative.sex, age=relative.age(),
        conditions=_copy_conditions(relative.conditions, source),
        source=source, linked=True,
    ), link["member_id"])]

    if level == "conditions_and_tree":
        for m in relative.family:
            mapped = compose(rel, m.relationship)
            if mapped is None or not m.conditions:
                continue
            out.append((FamilyMember(
                relationship=mapped, sex=m.sex, deceased=m.deceased, age=m.age,
                conditions=_copy_conditions(m.conditions, source + ":tree"),
                source=source + ":tree",
            ), None))
    return out


def effective_profile(store: Store, user_id: str) -> HealthProfile:
    """The user's own record plus whatever linked relatives currently share."""
    profile = store.get_profile(user_id).model_copy(deep=True)
    for link in store.links_for(user_id):
        relative = store.get_profile(link["relative_id"])
        for member, member_id in shared_fragment(link, relative):
            _attach(profile, member, member_id)
    return profile


def _label(rel: str) -> str:
    return rel.replace("_", " ")


def cascade_categories(profile: HealthProfile) -> set[str]:
    return {c.category for c in profile.conditions if c.category in CASCADE_CATEGORIES}


def notify_cascade(store: Store, user_id: str, categories: set[str],
                   only_relative: Optional[str] = None,
                   notify: Optional[Callable[[str, str, str], None]] = None) -> int:
    """Tell linked relatives (who can see this user's conditions) about a
    result that runs in families. Returns the number of notifications sent."""
    if not categories:
        return 0
    notify = notify or store.notify
    sent = 0
    from .notices import FAMILY_CASCADE, say

    names = sorted(CONCEPTS_BY_CATEGORY[c].display for c in categories)
    for link in store.links_for(user_id):
        if link["i_share"] == "none":
            continue
        if only_relative and link["relative_id"] != only_relative:
            continue
        lang = store.user_lang(link["relative_id"]) if hasattr(store, "user_lang") else "en"
        notify(link["relative_id"], "family_cascade",
               say(lang, FAMILY_CASCADE, translate=("who", "conditions"), who=_label(link["i_am"]), conditions=names))
        sent += 1
    return sent

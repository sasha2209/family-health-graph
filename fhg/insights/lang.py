"""The language action items are written in.

Rules write their text through ``tr("template with {placeholders}", ...)``. The English template is the key; a
translation table supplies the other languages, and anything missing falls back to English. The language is set for
one request with ``with language("hi"): generate_insights(profile)``. It defaults to English, so the clinician
summary, partner APIs and exports stay in English.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from ..notices_hi import NOTICES_HI
from ..notices_mr import NOTICES_MR
from .hi import HI
from .mr import MR

TABLES: dict[str, dict[str, str]] = {"hi": {**HI, **NOTICES_HI}, "mr": {**MR, **NOTICES_MR}}
_LANG: ContextVar[str] = ContextVar("insight_lang", default="en")


@contextmanager
def language(lang: str) -> Iterator[None]:
    token = _LANG.set(lang if lang in TABLES else "en")
    try:
        yield
    finally:
        _LANG.reset(token)


def current() -> str:
    return _LANG.get()


def tr(template: str, **values) -> str:
    table = TABLES.get(_LANG.get())
    text = table.get(template, template) if table else template
    return text.format(**values) if values else text


def mark(template: str) -> str:
    """Marks text that is translated later with tr() (lists defined ahead of time)."""
    return template


def join_and(items: list[str]) -> str:
    return tr(" and ").join(items)

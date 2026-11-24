"""Hand the Hindi and Marathi to reviewers as a spreadsheet, and write their corrections back into the code.

Translations live in several places: the app's strings (``mobile/src/locales/<lang>.ts``), the health advice
(``fhg/insights/<lang>.py``), notifications, medicine reminders, lock-screen texts and the privacy notice. Native
speakers and clinicians shouldn't have to edit code, so::

    python -m fhg.translation_review export mr review-mr.xlsx      # one sheet, every string, English beside it
    python -m fhg.translation_review import review-mr.xlsx --dry-run
    python -m fhg.translation_review import review-mr.xlsx         # writes corrections into the source files

Reviewers type a better wording in "Your correction", or mark the row OK. Import checks every correction keeps the
English's {placeholders}, and refuses a row whose translation changed in the code since the sheet was made, so
nobody's work is silently overwritten. Then run the tests and open a pull request as usual.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Union

ROOT = Path(__file__).resolve().parent.parent
LANGS = {"hi": "Hindi", "mr": "Marathi"}
Step = Union[str, int]

CLINICIAN = "Clinician + native speaker"
SPEAKER = "Native speaker"
PRIVACY = "Native speaker + privacy officer"


@dataclass(frozen=True)
class Source:
    area: str
    file: str                       # relative to the repository root; {lang} is filled in
    path: tuple[Step, ...] = ()     # Python: variable, then keys or indexes; {lang}/{LANG} are filled in
    english: tuple[Step, ...] = ()  # Python: where the English is, parallel to ``path``; empty = keyed by English
    check: str = SPEAKER


SOURCES = [
    Source("App screen", "mobile/src/locales/{lang}.ts"),
    Source("Health advice", "fhg/insights/{lang}.py", ("{LANG}",), check=CLINICIAN),
    Source("Notification", "fhg/notices_{lang}.py", ("NOTICES_{LANG}",)),
    Source("Medicine reminder", "fhg/care.py", ("ALERT_TEXT", "{lang}"), ("ALERT_TEXT", "en")),
    Source("Medicine reminder (parent's WhatsApp)", "fhg/care.py", ("WA_TEXT", "{lang}"), ("WA_TEXT", "en")),
    Source("Medicine reminder (parent's WhatsApp)", "fhg/care.py", ("WA_SLOT", "{lang}"), ("WA_SLOT", "en")),
    Source("Lock-screen notification", "fhg/push.py", ("PUSH_TEXT_I18N", "{lang}"), ("PUSH_TEXT",)),
    Source("Privacy notice", "fhg/privacy.py", ("HEADINGS", "{lang}"), ("HEADINGS", "en"), PRIVACY),
    Source("Privacy notice", "fhg/privacy.py", ("DATA_CATEGORIES", "{lang}"), ("DATA_CATEGORIES", "en"), PRIVACY),
    Source("Privacy notice", "fhg/privacy.py", ("PURPOSES", "{lang}"), ("PURPOSES", "en"), PRIVACY),
    Source("Privacy notice", "fhg/privacy.py", ("RIGHTS", "{lang}"), ("RIGHTS", "en"), PRIVACY),
]


@dataclass
class Entry:
    area: str
    file: str
    locator: tuple[Step, ...]       # TS: (english key,); Python: full path to the string
    context: str
    english: str
    current: str
    check: str

    @property
    def id(self) -> str:
        digest = hashlib.sha1(json.dumps([self.file, self.locator], ensure_ascii=False).encode()).hexdigest()
        return f"{self.area[:1]}-{digest[:6]}"


class ReviewError(Exception):
    pass


def placeholders(text: str) -> list[str]:
    return sorted(re.findall(r"\{\w+\}", text))


# --- reading -------------------------------------------------------------------------------------

def _fill(steps: tuple[Step, ...], lang: str) -> tuple[Step, ...]:
    return tuple(s.format(lang=lang, LANG=lang.upper()) if isinstance(s, str) else s for s in steps)


def _node(tree: ast.Module, path: tuple[Step, ...]) -> Optional[ast.AST]:
    node: Optional[ast.AST] = None
    for stmt in tree.body:
        targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target] if isinstance(stmt, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == path[0] for t in targets):
            node = stmt.value
    for step in path[1:]:
        if isinstance(node, ast.Dict):
            node = next((v for k, v in zip(node.keys, node.values)
                         if isinstance(k, ast.Constant) and k.value == step), None)
        elif isinstance(node, (ast.List, ast.Tuple)) and isinstance(step, int) and step < len(node.elts):
            node = node.elts[step]
        else:
            return None
    return node


def _leaves(node: ast.AST, prefix: tuple[Step, ...] = ()) -> Iterator[tuple[tuple[Step, ...], ast.Constant]]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield prefix, node
    elif isinstance(node, ast.Dict):
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant):
                yield from _leaves(v, prefix + (k.value,))
    elif isinstance(node, (ast.List, ast.Tuple)):
        for i, v in enumerate(node.elts):
            yield from _leaves(v, prefix + (i,))


def _section(lines: list[str], lineno: int) -> str:
    """The "# --- heading ---" comment above a line, for context."""
    for line in reversed(lines[:lineno - 1]):
        m = re.match(r"\s*# -+ (.+?) -*$", line) or re.match(r"\s*# (.+)$", line)
        if m:
            return m.group(1).strip()
    return ""


LABELS = {
    "ALERT_TEXT": "Reminder to the family", "WA_TEXT": "Reply to the parent", "WA_SLOT": "Time of day",
    "PUSH_TEXT_I18N": "Lock screen", "HEADINGS": "Heading", "DATA_CATEGORIES": "What we collect",
    "PURPOSES": "Why we use it", "RIGHTS": "Your rights",
}


def _context(path: tuple[Step, ...]) -> str:
    """ALERT_TEXT.mr.dose → "Reminder to the family · dose"; RIGHTS.mr.2.1 → "Your rights · item 3 · detail"."""
    parts = [LABELS.get(str(path[0]), str(path[0]))]
    rest = path[2:]
    if rest and isinstance(rest[0], int):
        parts.append(f"item {rest[0] + 1}")
        if len(rest) > 1:
            parts.append("title" if rest[1] == 0 else "detail")
    else:
        parts += [str(x).replace("_", " ").strip() for x in rest]
    return " · ".join(p for p in parts if p)


def _screens(root: Path) -> dict[str, list[str]]:
    """Which app screens use each English string, from the source (for the reviewer's context)."""
    out: dict[str, list[str]] = {}
    for f in sorted((root / "mobile" / "src").rglob("*.ts*")):
        if "locales" in f.parts:
            continue
        name = f.stem if f.stem not in ("index", "_layout") else f.parent.name
        name = name.strip("()[]").replace("-", " ")
        text = f.read_text()
        for m in re.finditer(r"'((?:\\.|[^'\\])*)'|\"((?:\\.|[^\"\\])*)\"", text):
            s = (m.group(1) if m.group(1) is not None else m.group(2)).replace("\\'", "'").replace("\\n", "\n")
            if name not in out.setdefault(s, []):
                out[s].append(name)
    return out


def entries(lang: str, root: Path = ROOT) -> list[Entry]:
    if lang not in LANGS:
        raise ReviewError(f"Unknown language {lang!r}; choose from {', '.join(LANGS)}")
    out: list[Entry] = []
    for src in SOURCES:
        file = src.file.format(lang=lang)
        text = (root / file).read_text()
        if file.endswith(".ts"):
            screens = _screens(root)
            sources = {f: f.read_text() for f in (root / "mobile" / "src").rglob("*.ts*") if "locales" not in f.parts}
            for key, value in _ts_table(text).items():
                found = screens.get(key) or sorted({f.stem.strip("()[]") for f, t in sources.items() if key in t})
                where = ", ".join(found[:4]) or "labels sent by the server (test results, action items)"
                out.append(Entry(src.area, file, (key,), where, key, value, src.check))
            continue
        tree = ast.parse(text)
        lines = text.splitlines()
        path = _fill(src.path, lang)
        node = _node(tree, path)
        if node is None:
            raise ReviewError(f"{file}: {'.'.join(map(str, path))} not found")
        if not src.english:                                 # a table keyed by the English
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                    out.append(Entry(src.area, file, path + (k.value,), _section(lines, k.lineno), k.value, v.value,
                                     src.check))
            continue
        english_root = _node(tree, src.english)
        english = ast.literal_eval(english_root) if english_root is not None else {}
        defaults = {"_default": ast.literal_eval(_node(tree, ("DEFAULT_TEXT",)))} if path[0] == "PUSH_TEXT_I18N" else {}
        for sub, leaf in _leaves(node):
            en = english
            for step in sub:
                try:
                    en = en[step]
                except (KeyError, IndexError, TypeError):
                    en = defaults.get(step, "")
                    break
            out.append(Entry(src.area, file, path + sub, _context(path + sub), en if isinstance(en, str) else "", leaf.value,
                             src.check))
    return out


def _ts_table(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if line.startswith('  "'):
            out.update(json.loads("{" + line.strip().rstrip(",") + "}"))
    return out


# --- writing -------------------------------------------------------------------------------------

def _literal(value: str, column: int, room: int = 118) -> str:
    """A Python string literal starting at ``column``; long ones become implicitly joined lines."""
    one = json.dumps(value, ensure_ascii=False)
    if column + len(one) <= room or " " not in value:
        return one
    width = max(40, room - column - 2)
    chunks, current = [], ""
    for word in re.split(r"(?<= )", value):
        if current and len(current) + len(word) > width:
            chunks.append(current)
            current = ""
        current += word
    chunks.append(current)
    return ("\n" + " " * column).join(json.dumps(c, ensure_ascii=False) for c in chunks)


def _edit_python(text: str, edits: dict[tuple[Step, ...], str]) -> str:
    tree = ast.parse(text)
    raw = text.encode()
    starts = [0]
    for line in raw.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    spans = []
    for path, value in edits.items():
        node = _node(tree, path)
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            raise ReviewError(f"{'.'.join(map(str, path))} is not a string in the code")
        begin = starts[node.lineno - 1] + node.col_offset          # col_offset counts UTF-8 bytes
        end = starts[node.end_lineno - 1] + node.end_col_offset
        column = len(raw[starts[node.lineno - 1]:begin].decode())
        spans.append((begin, end, _literal(value, column).encode()))
    for begin, end, new in sorted(spans, reverse=True):
        raw = raw[:begin] + new + raw[end:]
    out = raw.decode()
    check = ast.parse(out)
    for path, value in edits.items():
        assert ast.literal_eval(_node(check, path)) == value, path
    return out


def _edit_ts(text: str, edits: dict[str, str]) -> str:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith('  "'):
            ((key, _),) = json.loads("{" + line.strip().rstrip(",") + "}").items()
            if key in edits:
                lines[i] = f"  {json.dumps(key, ensure_ascii=False)}: {json.dumps(edits[key], ensure_ascii=False)},"
    return "\n".join(lines)


# --- the spreadsheet -----------------------------------------------------------------------------

COLUMNS = ["ID", "Area", "Where it appears", "English", "Current translation", "Your correction", "OK as is?",
           "Comment", "Check by", "locator"]

README = {
    "en": [
        "How to review",
        "Each row is one piece of text in the app or in messages families receive. English is on the left, the "
        "current translation next to it.",
        "If the translation is right, choose OK in the \"OK as is?\" column.",
        "If it should read differently, type the whole better sentence in \"Your correction\". Keep anything in "
        "{curly brackets} exactly as it is: the app fills in a name, a number or a date there.",
        "Use \"Comment\" for questions or notes. Please don't change the other columns or the order of rows.",
        "Rows marked \"Clinician + native speaker\" are health advice: a clinician should confirm the medical "
        "meaning is right, not only the language.",
        "Aim for the words families in the pilot city actually use, at the reading level of a school leaver, and "
        "the respectful form of address.",
        "Not in this sheet: the clinic poster, staff guide and intake page. Review those by opening them (the clinic "
        "portal links to them).",
    ],
    "hi": [
        "कैसे जाँचें",
        "हर पंक्ति ऐप या परिवारों को भेजे जाने वाले संदेशों का एक हिस्सा है। बाईं ओर अंग्रेज़ी है, उसके बगल में अभी का अनुवाद।",
        "अनुवाद सही है तो \"OK as is?\" कॉलम में OK चुनें।",
        "बेहतर तरीके से लिखा जाना चाहिए तो पूरा सही वाक्य \"Your correction\" में लिखें। {घुमावदार कोष्ठक} में जो है उसे वैसा ही "
        "रखें: वहाँ ऐप नाम, संख्या या तारीख भरता है।",
        "सवाल या टिप्पणी \"Comment\" में लिखें।",
    ],
    "mr": [
        "कसे तपासावे",
        "प्रत्येक ओळ अ‍ॅपमधील किंवा कुटुंबांना जाणाऱ्या संदेशांमधील एक मजकूर आहे. डावीकडे इंग्रजी आहे, त्याच्या शेजारी सध्याचे भाषांतर.",
        "भाषांतर बरोबर असेल तर \"OK as is?\" स्तंभात OK निवडा.",
        "वेगळे लिहायला हवे असेल तर संपूर्ण चांगले वाक्य \"Your correction\" मध्ये लिहा. {कंसात} जे आहे ते जसेच्या तसे ठेवा: "
        "तिथे अ‍ॅप नाव, संख्या किंवा तारीख भरते.",
        "प्रश्न किंवा टिपा \"Comment\" मध्ये लिहा.",
    ],
}


def export(lang: str, out: Path, root: Path = ROOT, clinical_only: bool = False) -> int:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    rows = [e for e in entries(lang, root) if not clinical_only or e.check == CLINICIAN]
    wb = Workbook()
    info = wb.active
    info.title = "Read me"
    info["A1"] = f"Family Health Graph: {LANGS[lang]} review"
    info["A1"].font = Font(bold=True, size=14)
    for i, line in enumerate(README["en"] + [""] + README[lang], start=3):
        info.cell(row=i, column=1, value=line).alignment = Alignment(wrap_text=True, vertical="top")
    info.column_dimensions["A"].width = 110

    ws = wb.create_sheet("Strings")
    ws.append(COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="E3EFEC")
    for e in rows:
        ws.append([e.id, e.area, e.context, e.english, e.current, "", "", "", e.check,
                   json.dumps([e.file, list(e.locator)], ensure_ascii=False)])
    widths = {"A": 10, "B": 18, "C": 22, "D": 55, "E": 55, "F": 55, "G": 10, "H": 30, "I": 18}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    ws.column_dimensions["J"].hidden = True
    for row in ws.iter_rows(min_row=2):
        for cell in row[:9]:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        row[5].fill = PatternFill("solid", fgColor="FFF8DC")
    ok = DataValidation(type="list", formula1='"OK"', allow_blank=True)
    ws.add_data_validation(ok)
    ok.add(f"G2:G{len(rows) + 1}")
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:I{len(rows) + 1}"
    wb.save(out)
    return len(rows)


@dataclass
class ImportReport:
    applied: list[str]
    approved: int
    unreviewed: int
    rejected: list[str]
    conflicts: list[str]
    comments: list[str]

    def summary(self) -> str:
        lines = [f"{len(self.applied)} corrected, {self.approved} marked OK, {self.unreviewed} not reviewed yet."]
        for title, items in (("Rejected (fix in the sheet and import again)", self.rejected),
                             ("Changed in the code since the sheet was made (review again)", self.conflicts),
                             ("Reviewer comments", self.comments)):
            if items:
                lines += ["", f"{title}:"] + [f"  {x}" for x in items]
        return "\n".join(lines)


def import_review(path: Path, root: Path = ROOT, dry_run: bool = False) -> ImportReport:
    from openpyxl import load_workbook

    ws = load_workbook(path, read_only=True)["Strings"]
    rows = list(ws.iter_rows(values_only=True))
    if not rows or list(rows[0][:len(COLUMNS)]) != COLUMNS:
        raise ReviewError("This doesn't look like a review sheet made by this tool (the columns were changed)")
    report = ImportReport([], 0, 0, [], [], [])
    current: dict[str, dict] = {}
    edits: dict[str, dict] = {}
    for row in rows[1:]:
        rid, _area, _ctx, english, was, fix, ok, comment, _check, locator = (list(row) + [None] * 10)[:10]
        if not locator:
            continue
        file, steps = json.loads(locator)
        steps = tuple(steps)
        if comment:
            report.comments.append(f"{rid}: {comment}")
        fix = (fix or "").strip()
        if not fix or fix == was:
            if str(ok or "").strip().upper() == "OK" or fix:
                report.approved += 1
            else:
                report.unreviewed += 1
            continue
        if placeholders(fix) != placeholders(english or ""):
            report.rejected.append(f"{rid}: needs exactly {', '.join(placeholders(english or '')) or 'no {placeholders}'}"
                                   f" (has {', '.join(placeholders(fix)) or 'none'})")
            continue
        if file not in current:
            text = (root / file).read_text()
            current[file] = _ts_table(text) if file.endswith(".ts") else {"_text": text}
        now = _value_now(current[file], file, steps)
        if now != was:
            report.conflicts.append(f"{rid}: the code now says {now!r}")
            continue
        edits.setdefault(file, {})[steps[0] if file.endswith(".ts") else steps] = fix
        report.applied.append(f"{rid}: {was} → {fix}")
    if not dry_run:
        for file, changes in edits.items():
            p = root / file
            text = p.read_text()
            p.write_text(_edit_ts(text, changes) if file.endswith(".ts") else _edit_python(text, changes))
    return report


def _value_now(cache: dict, file: str, steps: tuple[Step, ...]) -> Optional[str]:
    if file.endswith(".ts"):
        return cache.get(steps[0])
    node = _node(ast.parse(cache["_text"]), steps)
    return node.value if isinstance(node, ast.Constant) else None


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m fhg.translation_review", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export", help="write a review spreadsheet")
    ex.add_argument("lang", choices=sorted(LANGS))
    ex.add_argument("out", type=Path)
    ex.add_argument("--clinical-only", action="store_true", help="only the health advice, for a clinician")
    im = sub.add_parser("import", help="apply a reviewed spreadsheet to the code")
    im.add_argument("sheet", type=Path)
    im.add_argument("--dry-run", action="store_true", help="report what would change, change nothing")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "export":
            n = export(args.lang, args.out, clinical_only=args.clinical_only)
            print(f"{n} strings written to {args.out}")
        else:
            report = import_review(args.sheet, dry_run=args.dry_run)
            print(("Dry run, nothing written. " if args.dry_run else "") + report.summary())
            return 1 if report.rejected or report.conflicts else 0
    except ReviewError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

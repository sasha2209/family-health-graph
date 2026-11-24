"""The review spreadsheet: every translated string is in it, and corrections go back into the code safely."""
import ast
import json
import shutil
from pathlib import Path

import pytest
from openpyxl import load_workbook

from fhg import translation_review as tr

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def repo(tmp_path):
    """A copy of the files the tool reads and writes."""
    for src in tr.SOURCES:
        for lang in ("hi", "mr"):
            f = src.file.format(lang=lang)
            (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / f, tmp_path / f)
    shutil.copytree(ROOT / "mobile" / "src", tmp_path / "mobile" / "src", dirs_exist_ok=True)
    return tmp_path


def sheet_rows(path):
    return list(load_workbook(path)["Strings"].iter_rows(values_only=True))


def edit_sheet(path, changes):
    """changes: {english: (correction, ok, comment)} applied to the first row with that English."""
    wb = load_workbook(path)
    ws = wb["Strings"]
    for row in ws.iter_rows(min_row=2):
        if row[3].value in changes:
            fix, ok, comment = changes.pop(row[3].value)
            row[5].value, row[6].value, row[7].value = fix, ok, comment
    assert not changes, changes
    wb.save(path)


@pytest.mark.parametrize("lang", ["hi", "mr"])
def test_export_has_every_string(tmp_path, lang):
    out = tmp_path / f"review-{lang}.xlsx"
    n = tr.export(lang, out)
    rows = sheet_rows(out)
    assert rows[0][:len(tr.COLUMNS)] == tuple(tr.COLUMNS) and len(rows) == n + 1
    app = (ROOT / f"mobile/src/locales/{lang}.ts").read_text().count('\n  "')
    areas = [r[1] for r in rows[1:]]
    assert areas.count("App screen") == app and "Health advice" in areas and "Privacy notice" in areas
    assert all(r[3] and r[4] for r in rows[1:])                           # English and translation on every row
    assert len({r[0] for r in rows[1:]}) == n                             # IDs are unique
    advice = next(r for r in rows if r[1] == "Health advice")
    assert advice[8] == tr.CLINICIAN
    assert tr.export(lang, tmp_path / "c.xlsx", clinical_only=True) == areas.count("Health advice")


def test_import_writes_corrections_into_each_kind_of_file(repo, tmp_path):
    out = tmp_path / "r.xlsx"
    tr.export("mr", out, root=repo)
    edit_sheet(out, {
        "Add a medicine": ("नवीन औषध जोडा", None, None),                                     # app (TypeScript)
        "high (60 or more)": ("जास्त (60 किंवा अधिक)", None, "अधिक reads better"),             # health advice
        "{partner} has completed your {tests}.": ("{partner} ने तुमची {tests} पूर्ण केली आहे.", None, None),
        "Your rights": (None, "OK", None),                                                # approved, unchanged
    })
    report = tr.import_review(out, root=repo, dry_run=True)
    assert len(report.applied) == 3 and report.approved == 1 and report.comments
    assert "नवीन औषध जोडा" not in (repo / "mobile/src/locales/mr.ts").read_text()        # dry run wrote nothing

    report = tr.import_review(out, root=repo)
    assert len(report.applied) == 3 and not report.rejected and not report.conflicts
    assert '"Add a medicine": "नवीन औषध जोडा",' in (repo / "mobile/src/locales/mr.ts").read_text()
    mr = ast.literal_eval(_dict_source(repo / "fhg/insights/mr.py"))
    assert mr["high (60 or more)"] == "जास्त (60 किंवा अधिक)"
    # Re-importing the same sheet now finds the code changed under it, and says so instead of overwriting.
    again = tr.import_review(out, root=repo)
    assert len(again.conflicts) == 3 and not again.applied


def _dict_source(path):
    tree = ast.parse(path.read_text())
    return ast.unparse(next(n.value for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))))


def test_long_corrections_stay_readable_python(repo, tmp_path):
    out = tmp_path / "r.xlsx"
    tr.export("hi", out, root=repo)
    before = max(len(line) for line in (repo / "fhg/insights/hi.py").read_text().splitlines())
    english = next(e.english for e in tr.entries("hi", repo) if len(e.english) > 300)
    long_fix = "यह एक लंबा सुधारा हुआ वाक्य है, जिसे कई पंक्तियों में लिखा जाना चाहिए। " * 6
    edit_sheet(out, {english: (long_fix.strip(), None, None)})
    assert len(tr.import_review(out, root=repo).applied) == 1
    text = (repo / "fhg/insights/hi.py").read_text()
    assert max(len(line) for line in text.splitlines()) <= max(before, 120)
    assert ast.literal_eval(_dict_source(repo / "fhg/insights/hi.py"))[english] == long_fix.strip()


def test_corrections_must_keep_placeholders(repo, tmp_path):
    out = tmp_path / "r.xlsx"
    tr.export("mr", out, root=repo)
    edit_sheet(out, {"{n} days left": ("काही दिवस उरले", None, None),
                     "{who}'s {med} runs out today. Time to reorder.": ("{who} यांचे {medicine} आज संपेल.", None, None)})
    report = tr.import_review(out, root=repo)
    assert len(report.rejected) == 2 and not report.applied


def test_python_edits_handle_shared_lines_and_nested_tables():
    src = 'T = {"en": {"a": "x"}, "mr": {"a": "जुने", "b": "दुसरे"}}\nL = {"mr": [("एक", "दोन")]}\n'
    out = tr._edit_python(src, {("T", "mr", "a"): 'नवे "छान"', ("L", "mr", 0, 1): "तीन"})
    ns = {}
    exec(out, ns)  # noqa: S102 - our own test source
    assert ns["T"]["mr"] == {"a": 'नवे "छान"', "b": "दुसरे"} and ns["L"]["mr"] == [("एक", "तीन")]


def test_cli(tmp_path, capsys):
    assert tr.main(["export", "mr", str(tmp_path / "x.xlsx")]) == 0
    assert "strings written" in capsys.readouterr().out
    assert tr.main(["import", str(tmp_path / "x.xlsx"), "--dry-run"]) == 0
    assert "0 corrected" in capsys.readouterr().out
    bad = tmp_path / "bad.xlsx"
    from openpyxl import Workbook
    wb = Workbook(); wb.active.title = "Strings"; wb.active.append(["something", "else"]); wb.save(bad)  # noqa: E702
    assert tr.main(["import", str(bad)]) == 2

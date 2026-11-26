"""엑셀 시트 편집 엔진(spec_엑셀편집 ② §2~§4) — openpyxl 로 만든 통합 문서를 고치고, 다시 openpyxl 로 읽어 본다."""
import io
import zipfile

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table

from app import xlsx_doc as X


def _book():
    wb = Workbook()
    ws = wb.active
    ws.title = "참고문헌"
    ws.append(["번호", "저자", "제목", "연도"])
    ws["A1"].font = Font(bold=True)
    ws["A1"].fill = PatternFill("solid", fgColor="FFDDEEFF")
    for k in range(2, 6):
        ws.append([k - 1, f"저자{k}", f"제목{k}", 2020 + k])
    ws["F2"] = "=SUM(D2:D5)"
    ws["F3"] = "=D3*2"
    ws.merge_cells("B8:C8")
    ws["B8"] = "병합"
    ws.column_dimensions["C"].width = 30
    dv = DataValidation(type="list", formula1='"A,B"')
    dv.add("E2:E5")
    ws.add_data_validation(dv)
    tab = wb.create_sheet("요약")
    tab["A1"] = "='참고문헌'!D5"
    tab["A2"] = "=COUNTA('참고문헌'!B2:B5)"
    t = wb.create_sheet("표")
    t.append(["a", "b"])
    t.append([1, 2])
    t.append([3, 4])
    t.add_table(Table(displayName="T1", ref="A1:B3"))
    wb.defined_names["목록"] = __import__("openpyxl").workbook.defined_name.DefinedName("목록", attr_text="'참고문헌'!$B$2:$B$5")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _reload(data):
    return load_workbook(io.BytesIO(data))


def test_view_reads_values_styles_merges():
    d = X.XlsxDoc(_book())
    assert [s["name"] for s in d.sheets] == ["참고문헌", "요약", "표"]
    v = d.view(0)
    cells = {(r, c): (shown, edit, kind) for r, c, shown, edit, _s, kind, *_ in v["cells"]}
    assert cells[(1, 2)][0] == "저자"
    assert cells[(2, 4)] == ("2022", "2022", "n")
    assert cells[(2, 6)][1] == "=SUM(D2:D5)" and cells[(2, 6)][2] == "f"
    assert [8, 2, 8, 3] in v["merges"]
    assert v["colW"][2] == round(30 * 7 + 5)
    a1 = next(c for c in v["cells"] if c[0] == 1 and c[1] == 1)
    css = v["styles"][a1[4]]
    assert css.get("fontWeight") == "bold" and css.get("background") == "#DDEEFF"


def test_set_cells_kinds_and_roundtrip():
    d = X.XlsxDoc(_book())
    got = d.set_cells(0, [(6, 1, "5"), (6, 2, "홍길동, 김철수"), (6, 3, "'2024"), (6, 4, "9781234567890123"), (6, 5, "007"), (7, 6, "=A6+1")])
    assert [g[5] for g in got] == ["n", "s", "s", "s", "s", "f"]
    wb = _reload(d.save())
    ws = wb["참고문헌"]
    assert ws["A6"].value == 5 and ws["B6"].value == "홍길동, 김철수" and ws["C6"].value == "2024"
    assert ws["D6"].value == "9781234567890123" and ws["E6"].value == "007" and ws["F7"].value == "=A6+1"
    z = zipfile.ZipFile(io.BytesIO(d.save()))
    assert "xl/calcChain.xml" not in z.namelist()
    assert b'fullCalcOnLoad="1"' in z.read("xl/workbook.xml")


def test_merged_cell_refused():
    d = X.XlsxDoc(_book())
    with pytest.raises(X.SheetError):
        d.set_cells(0, [(8, 3, "x")])


def test_clear_cell_removes_value():
    d = X.XlsxDoc(_book())
    d.set_cells(0, [(2, 2, "")])
    assert _reload(d.save())["참고문헌"]["B2"].value is None


def test_insert_rows_shifts_everything():
    d = X.XlsxDoc(_book())
    d.insert_rows(0, 3, 2)   # 3행 위에 2행
    wb = _reload(d.save())
    ws = wb["참고문헌"]
    assert ws["B5"].value == "저자3" and ws["B3"].value is None
    assert ws["F2"].value == "=SUM(D2:D7)"
    assert ws["F5"].value == "=D5*2"
    assert "B10:C10" in [str(m) for m in ws.merged_cells.ranges]
    assert wb["요약"]["A1"].value == "='참고문헌'!D7"
    assert wb["요약"]["A2"].value == "=COUNTA('참고문헌'!B2:B7)"
    assert str(ws.data_validations.dataValidation[0].sqref) == "E2:E7"
    assert wb.defined_names["목록"].attr_text == "'참고문헌'!$B$2:$B$7"
    assert ws.row_dimensions[3].height == ws.row_dimensions[2].height


def test_delete_rows_ref_and_shrink():
    d = X.XlsxDoc(_book())
    d.delete_rows(0, 3, 3)
    wb = _reload(d.save())
    ws = wb["참고문헌"]
    assert ws["B3"].value == "저자4"
    assert ws["F2"].value == "=SUM(D2:D4)"
    assert wb["요약"]["A1"].value == "='참고문헌'!D4"
    assert ws["F3"].value is None   # F3(=D3*2) 이 있던 행을 지움
    d2 = X.XlsxDoc(_book())
    d2.set_cells(1, [(3, 1, "='참고문헌'!D3")])
    d2.delete_rows(0, 3, 3)
    assert _reload(d2.save())["요약"]["A3"].value == "='참고문헌'!#REF!"


def test_table_header_delete_refused_and_table_ref_moves():
    d = X.XlsxDoc(_book())
    with pytest.raises(X.SheetError):
        d.delete_rows(2, 1, 1)
    d.insert_rows(2, 3, 1)
    z = zipfile.ZipFile(io.BytesIO(d.save()))
    tname = next(n for n in z.namelist() if n.startswith("xl/tables/"))
    assert b'ref="A1:B4"' in z.read(tname)


def test_shared_formula_unshared_on_edit():
    wb = Workbook()
    ws = wb.active
    for r in range(1, 5):
        ws.cell(r, 1, r)
    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    # 공유 수식을 손으로 넣는다(openpyxl 은 쓰지 않는다)
    z = zipfile.ZipFile(io.BytesIO(data))
    xml = z.read("xl/worksheets/sheet1.xml").decode()
    xml = xml.replace('<c r="A1" t="n"><v>1</v></c>', '<c r="A1" t="n"><v>1</v></c><c r="B1"><f t="shared" ref="B1:B3" si="0">A1*2</f><v>2</v></c>')
    xml = xml.replace('<c r="A2" t="n"><v>2</v></c>', '<c r="A2" t="n"><v>2</v></c><c r="B2"><f t="shared" si="0"/><v>4</v></c>')
    xml = xml.replace('<c r="A3" t="n"><v>3</v></c>', '<c r="A3" t="n"><v>3</v></c><c r="B3"><f t="shared" si="0"/><v>6</v></c>')
    assert 'si="0"/>' in xml
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as w:
        for n in z.namelist():
            w.writestr(n, xml if n == "xl/worksheets/sheet1.xml" else z.read(n))
    d = X.XlsxDoc(out.getvalue())
    d.set_cells(0, [(1, 2, "")])
    ws2 = _reload(d.save()).active
    assert ws2["B2"].value == "=A2*2" and ws2["B3"].value == "=A3*2" and ws2["B1"].value is None


def test_untouched_members_kept_byte_for_byte():
    data = _book()
    d = X.XlsxDoc(data)
    d.set_cells(0, [(2, 2, "바꿈")])
    a, b = zipfile.ZipFile(io.BytesIO(data)), zipfile.ZipFile(io.BytesIO(d.save()))
    for n in a.namelist():
        if n in ("xl/worksheets/sheet1.xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml", "xl/calcChain.xml"):
            continue
        assert a.read(n) == b.read(n), n


@pytest.mark.parametrize("text,want", [("12", 12.0), ("1,234.5", 1234.5), ("15%", 0.15), ("-3.5e2", -350.0), ("007", None), ("1.2.3", None), ("123456789012", None), ("abc", None)])
def test_as_number(text, want):
    assert X._as_number(text) == want


def test_formula_shift_ignores_strings_and_functions():
    sh = X.Shift(insert_at=2, n=1)
    assert X.shift_formula('IF(A3="B3",LOG10(A2),$A$5)', "S", "S", sh) == 'IF(A4="B3",LOG10(A3),$A$6)'
    assert X.shift_formula("Other!A3+A3", "S", "S", sh) == "Other!A3+A4"


def test_date_cell():
    wb = Workbook()
    ws = wb.active
    import datetime
    ws["A1"] = datetime.date(2024, 3, 1)
    buf = io.BytesIO()
    wb.save(buf)
    d = X.XlsxDoc(buf.getvalue())
    cell = next(c for c in d.view(0)["cells"] if c[:2] == [1, 1])
    assert cell[2] == "2024-03-01" and cell[5] == "d"
    d.set_cells(0, [(1, 1, "2025.12.31")])
    assert _reload(d.save()).active["A1"].value.date() == datetime.date(2025, 12, 31)

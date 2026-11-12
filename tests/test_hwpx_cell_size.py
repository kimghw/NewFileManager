"""저장된 칸 크기 읽기 — 한글이 음수가 된 칸 높이를 부호 없는 32비트로 적은 값(실파일 `cellSz height="4294967256"` = −40,
references/HWPX_포맷.md 「셀 높이」)은 높이 정보 없음(0)으로 읽는다. 그대로 읽으면 화면 행 높이가 1,500만 mm 가 되고(2026-11-11 사용자
"이거 깨졌다" — 표 t21419), 행 넣기가 걸친 칸 높이에 40억을 더해 적는다."""
from functools import cache
from pathlib import Path

from app import hwpx_layout, merge_chunks
from app.hwpx_doc import HP, HwpxDoc

SMALL = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"
CELLSZ, SZ = f"{{{HP}}}cellSz", f"{{{HP}}}sz"
WRAPPED = "4294967256"  # −40 을 부호 없는 32비트로
# 기술수요조사서 표 t8(18×11): 1행의 칸 c26(행 높이 4165 — 같은 행 다른 칸도 4165), c9 가 0~2행에 걸친 칸(높이 10178)
TABLE, BAD, ROW, SPAN = "t8", "c26", 1, "c9"


@cache
def _bytes():
    """예제의 한 칸 높이를 넘친 값으로 바꿔 저장한 파일 — 실파일처럼 값이 파일 안에 있다."""
    d = HwpxDoc(SMALL.read_bytes())
    d.blocks()
    sz = d._ids[BAD].find(CELLSZ)
    assert sz.get("height") == "4165" and d._ids[SPAN].find(CELLSZ).get("height") == "10178"
    sz.set("height", WRAPPED)
    d._touch(sz)
    return d.save()


def _doc():
    d = HwpxDoc(_bytes())
    d.blocks()
    assert d._ids[BAD].find(CELLSZ).get("height") == WRAPPED
    return d


def _find(blocks, bid):
    for b in blocks:
        if b["id"] == bid:
            return b
        for c in b.get("cells") or ():
            if (hit := _find(c.get("blocks") or [], bid)) is not None:
                return hit
    return None


def _height(d, cid, tag=CELLSZ):
    el = d._ids[cid]
    return int((el if tag == CELLSZ else el).find(tag).get("height"))


def test_hu_reads_wrapped_negative_as_zero():
    assert hwpx_layout.hu("4165") == 4165 and hwpx_layout.hu(None) == 0 and hwpx_layout.hu("0") == 0
    assert hwpx_layout.hu(WRAPPED) == 0 and hwpx_layout.hu(str(2 ** 31)) == 0 and hwpx_layout.hu("-40") == 0
    assert hwpx_layout.hu(str(2 ** 31 - 1)) == 2 ** 31 - 1


def test_view_row_height_ignores_wrapped_height():
    d = _doc()
    table = _find(d.blocks(), TABLE)
    cells = {c["id"]: c for c in table["cells"]}
    assert cells[BAD]["heightMm"] == 0                       # 화면: td 높이를 안 준다(app.js renderTable — 0 이면 건너뜀)
    assert cells["c30"]["heightMm"] == round(4165 * 25.4 / 7200, 2)   # 같은 행 다른 칸이 행 높이를 받친다
    assert max(c["heightMm"] for c in table["cells"]) < 297  # 용지보다 큰 칸 없음
    assert merge_chunks._height(table) < 297                 # 쪽 수 어림(병합 검토 단위)도 같은 값을 읽는다


def test_grid_row_height_ignores_wrapped_height():
    d = _doc()
    _, cells, nr, nc = d._tgrid(d._ids[TABLE])
    heights, _ = d._tsizes(cells, nr, nc)
    assert heights[ROW] == 4165 and max(heights) < 2 ** 31


def test_row_ops_do_not_spread_wrapped_height():
    before = _height(_doc(), TABLE, SZ)
    d = _doc()
    d.clone_rows(TABLE, ROW, ROW)                            # 행 넣기: 걸친 칸·표 높이가 그 행 높이(4165)만큼만 는다
    assert _height(d, SPAN) == 10178 + 4165 and _height(d, TABLE, SZ) == before + 4165
    d = _doc()
    d.insert_rows(TABLE, ROW, ROW, [{}])                     # 구분 기준 끼우기도 같다
    assert _height(d, SPAN) == 10178 + 4165
    d = _doc()
    d.delete_rows(TABLE, ROW, ROW)                           # 행 지우기: 걸친 칸이 그 행 높이만큼만 준다(0 으로 꺼지지 않음)
    assert _height(d, SPAN) == 10178 - 4165 and _height(d, TABLE, SZ) == before - 4165
    HwpxDoc(d.save()).blocks()                               # 저장본이 다시 열린다

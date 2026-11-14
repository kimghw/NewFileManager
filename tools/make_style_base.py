"""서식 보관함의 빈 바탕 `app/style_base.hwpx` 를 만든다(spec_일반편집 ② §1·§3) — 저장소에 든 결과물을 다시 만들 때만 돌린다.

    python -X utf8 tools/make_style_base.py [--check]

바탕 = `samples/기술수요조사서.hwpx`(A4 세로 · 좌우 여백 20mm · 구역 하나)에서 **구역 설정이 든 첫 문단만** 남기고(글·표는 비움), 그 뒤에 **평범한 2×2 표** 하나를 둔 것:
칸마다 음영 없음 · 네 변 실선 0.12mm 검정 · 세로 가운데 · 칸 여백 좌우 1.8mm 위아래 0.5mm · 글 = 그 문서의 기본 글꼴 10pt 보통 · 왼쪽 정렬 · 줄 간격 160%.
header 의 정의는 원본 그대로 둔다(안 쓰는 정의를 빼면 id 가 비어 한글이 못 읽을 수 있다).
`--check` = 만들지 않고, 지금 파일이 「첫 문단 + 표 하나(2×2)」 꼴인지만 본다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import table_make  # noqa: E402
from app.hwpx_doc import HwpxDoc, P  # noqa: E402

SRC = ROOT / "samples" / "기술수요조사서.hwpx"
OUT = ROOT / "app" / "style_base.hwpx"
LINE = {"type": "SOLID", "width": "0.12 mm", "color": "#000000"}


def shape(data):
    """(최상위 문단 수, [표 (행, 열)…]) — 바탕의 꼴."""
    d = HwpxDoc(data)
    tabs = [(b["nRows"], b["nCols"]) for b in d.blocks() if b["type"] == "table"]
    return sum(1 for s in d._sections for _ in s.iterchildren(P)), tabs


def build():
    src = HwpxDoc(SRC.read_bytes())
    sec = src._sections[0]
    ps = list(sec.iterchildren(P))
    first, host = ps[0], None
    src.blocks()  # id 를 붙여 둔다
    tid, anchor = src._id(next(sec.iter("{*}tbl"))), src._id(first)  # 양식으로 삼을 표(어느 표든 — 서식은 아래에서 다 덮어쓴다)
    # 평범한 2×2 표를 첫 문단 뒤에 만든 뒤, 원래 있던 것(표·글)을 다 지운다
    norm = table_make.normalize({"rows": [{"cells": [{"text": ""}, {"text": ""}]}] * 2, "headerRows": 0, "headerCols": 0, "footRows": 0})
    made = src.table_make(anchor, tid, norm, {"headerRows": 0, "headerCols": 0, "footRows": 0})
    host = src._ids[made["host"]]
    for p in list(sec.iterchildren(P)):
        if p is not first and p is not host:
            sec.remove(p)
    for r in list(first):  # 첫 문단: 구역 설정·구역 제어만 남김
        for ch in list(r):
            if ch.tag.endswith(("}tbl", "}pic", "}t")):
                r.remove(ch)
    for ls in first.findall("{*}linesegarray"):
        first.remove(ls)
    src._touch(sec)
    tb = src.table_block(made["table"])
    for c in tb["cells"]:
        cur = src.get_cell_format(c["id"])
        text = src.derive_format(cur["text"], {"sizePt": 10, "bold": False, "italic": False, "underline": False, "color": "#000000", "align": "left",
                                               "lineSpacingPct": 160, "indentLeftMm": 0, "indentRightMm": 0, "firstLineMm": 0, "spaceBeforePt": 0, "spaceAfterPt": 0})
        src.apply_cell_format([c["id"]], {"text": text, "fill": None, "valign": "center", "marginsMm": {"l": 1.8, "r": 1.8, "t": 0.5, "b": 0.5}},
                              ["text", "fill", "valign", "margins"], keep_numbering=False)
        src.set_cell_edges(c["id"], {"top": LINE, "bottom": LINE, "left": LINE, "right": LINE})
    return src.save()


if __name__ == "__main__":
    if "--check" in sys.argv:
        n, tabs = shape(OUT.read_bytes())
        ok = n == 2 and tabs == [(2, 2)]
        print(f"{OUT.name}: 최상위 문단 {n} · 표 {tabs} — {'맞음' if ok else '꼴이 다름'}")
        sys.exit(0 if ok else 1)
    data = build()
    n, tabs = shape(data)
    assert n == 2 and tabs == [(2, 2)], (n, tabs)
    OUT.write_bytes(data)
    print(f"{OUT} — {len(data) // 1024} KB · 최상위 문단 {n} · 표 {tabs}")

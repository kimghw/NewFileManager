"""제목 표가 여러 꼴·여러 층으로 든 시험 문서 만들기(spec_hwpx_웹편집 ② §8-7 「넓힘」 — tests/test_outline_lift.py · tools/smoke_outline_lift_ui.py 가 함께 쓴다).

연구개발계획서 양식의 1칸 제목 상자 「기술준비도(TRL, …」(그 아래 「□ 과제개요」 — 가지 템플릿 T2 의 첫 레벨 줄)를 베끼고 칸을 나눠 만든다. 본문 차례:

    3행 표(위 칸에 제목) · 띠 「1 . | 띠 제목 1」 · 띠 「2 . | 띠 제목 2」 · 1칸 상자 · □ 줄   /   띠 「3 . | 띠 제목 3」 · □ 줄

    python -X utf8 tools/title_tables_doc.py <나갈 파일.hwpx>
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import outline_lift as OL  # noqa: E402
from app.hwpx_doc import SUBLIST, TC, TR, HwpxDoc, P  # noqa: E402

PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"


def cell_paras(doc, tbl):
    """표의 칸마다(행 차례) 문단 요소 목록."""
    return [[p for sl in c.iterchildren(SUBLIST) for p in sl.iterchildren(P)] for tr in tbl.iterchildren(TR) for c in tr.iterchildren(TC)]


def build() -> bytes:
    doc = HwpxDoc(PLAN.read_bytes())
    host = next(k for sec in doc._sections for k in sec.iterchildren(P) if OL.box_of(doc, k))
    tbl, cell, _ = OL.box_of(doc, host)
    t0, c0 = doc._id(tbl), doc._id(cell)
    under = next(k for k in host.itersiblings(P) if doc._text(k).strip())  # 「□ 과제개요」
    pair = doc.clone_blocks(t0, doc._id(under))["map"]  # 상자 + □ 줄을 한 벌 더(둘째 자리)
    maps = [doc.clone_blocks(t0, t0)["map"] for _ in range(3)]  # 원래 상자 바로 뒤에 셋 — 차례: 원래 · maps[2] · maps[1] · maps[0] · □
    doc.split_cell(c0, 3, 1)  # 원래 상자 → 3행 표
    for n, m in enumerate((maps[2], maps[1], pair), 1):  # 띠 셋 — 번호 칸 + 제목 칸
        doc.split_cell(m[c0], 1, 2)
        for paras, text in zip(cell_paras(doc, doc._ids[m[t0]]), (f"{n} .", f"띠 제목 {n}")):
            doc.set_text(doc._id(paras[0]), text)
    return doc.save()


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.write_bytes(build())
    print(out, out.stat().st_size)

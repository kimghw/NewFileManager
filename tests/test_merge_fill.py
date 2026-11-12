"""넣기 계획(본문) · ④ 내용 반영(spec_병합 ② §5 「문단 묶음 항목」 · §6) — app/merge_fill.py. 저장소 안 작은 쌍(merge_data.small — 원본 문단 묶음 항목마다 표식 줄)으로."""
import pytest

import merge_data as M
from app import hwpx_struct
from app import merge_fill as F
from app import merge_pairs as P
from app.hwpx_doc import HwpxDoc


@pytest.fixture(scope="module")
def small():
    """작은 쌍 + 묶음 짝 — 2-2 기관 절(스크립트가 못 정함)은 사람 확정을 흉내 내 「② 개발 내용 및 범위」(1차년도)에 잇는다."""
    d = M.small()
    s = {side: P.summarize(d[side]["doc"].blocks(), d[side]["graph"], d[side]["tables"], d["values"]) for side in ("to", "from")}
    to = next(x["key"] for x in s["to"] if x["kind"] == "paragraph" and x["dim"] == "org" and "추진 실적" in " ".join(x["path"]))
    frm = next(x["key"] for x in s["from"] if x["kind"] == "paragraph" and x["path"][-1:] == ["개발 내용 및 범위"] and x["ctx"]["year"] == 1)
    pairs = P.pair(s["to"], s["from"], fixed={to: {"from": frm, "source": "user", "anchor": "- (추진 내용)"}})
    return d, pairs, to


def _fresh(side):
    doc = M.fresh(side)
    doc.blocks()   # 블록 id 는 읽을 때 매겨진다 — 읽어 두어야 추출 결과의 id 와 같다
    return doc


def _plan(d, pairs, doc=None, applied=None):
    return F.plan({**d["to"], "doc": doc or d["to"]["doc"]}, d["from"], d["values"], d["values"], pairs, applied)


def test_fill_marker_lands_at_anchor_once(small):
    d, pairs, key = small
    pl = _plan(d, pairs)
    rows = [r for r in pl["items"] if r["group"] == key]
    assert [r["skip"] for r in rows] == [None] * 3 and all(r["anchorText"] == "- (추진 내용)" for r in rows)
    assert any(r["skip"] == "tables" for r in pl["items"])   # 다음 연도 연구개발비 기관 절 — 자리에 양식 표
    doc = _fresh(d["to"])
    res = F.apply(doc, d["from"]["doc"], pl)
    assert hwpx_struct.snapshot(d["from"]["doc"])["bytes"] == d["from"]["bytes"]   # 원본은 그대로
    order = {b["id"]: i for i, b in enumerate(doc.blocks())}
    text = {b["id"]: b.get("text") or "" for b in doc.blocks()}
    for r in rows:   # 표식 줄 「★병합시험 <key> <값>」 이 같은 기관 항목의 넣을 자리 바로 뒤에
        new = res["inserted"][r["to"]]
        assert text[new[0]].startswith(M.SMALL_MARK) and text[new[0]].endswith(" " + r["value"]) and order[new[0]] == order[r["anchor"]] + 1
    again = _plan(d, pairs, doc, res["applied"])   # 다시 계획 = 할 일 없음
    assert again["counts"]["todo"] == 0 and [r["skip"] for r in again["items"] if r["group"] == key] == ["applied"] * 3
    moved = {k: {**v, "hash": "x"} for k, v in res["applied"].items()}
    assert {r["skip"] for r in _plan(d, pairs, doc, moved)["items"] if r["group"] == key} == {"changed"}
    back = HwpxDoc(hwpx_struct.snapshot(doc)["bytes"])   # 저장한 결과가 다시 열린다
    assert sum((b.get("text") or "").startswith(M.SMALL_MARK) for b in back.blocks()) == 3


def test_fill_occupied_and_placeholder(small):
    d, pairs, key = small
    rows = [r for r in _plan(d, pairs)["items"] if r["group"] == key]
    doc = _fresh(d["to"])
    doc.insert_after(rows[0]["anchor"], [{"kind": "paragraph", "text": "사람이 쓴 글"}])
    ph = doc.insert_after(rows[1]["anchor"], [{"kind": "paragraph", "text": "-"}])[0]
    got = {r["to"]: r for r in _plan(d, pairs, doc)["items"] if r["group"] == key}
    assert got[rows[0]["to"]]["skip"] == "occupied" and got[rows[1]["to"]]["placeholders"] == [ph]
    F.apply(doc, d["from"]["doc"], {"items": list(got.values())})
    texts = [b.get("text") for b in doc.blocks()]
    assert "사람이 쓴 글" in texts and ph not in {b["id"] for b in doc.blocks()}
    assert sum((t or "").startswith(M.SMALL_MARK) for t in texts) == 2

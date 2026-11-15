"""표지 서식(spec_서식복사 ② §14 · §16 — app/style_cover.py): 후보의 범위·신호·역할 어림(양식 문서 · 손으로 지은 hwpx · 블록 열만 가진 가짜 문서) · 운반 문서(견본 글 · 원문이 안 남음 ·
구역 설정을 품은 첫 문단 = 표지의 첫 블록) · 보기 · 범위 줄이기 · 넣기(블록 차례 · 구역 설정 자리 · 쪽 나눔 · 저장 뒤 다시 열림) · docx 원본. 한글·Word 없이."""
import json
from pathlib import Path

import pytest

from app import owpml_check
from app import style_carrier as SC
from app import style_cover as C
from app import style_docx as D
from app import style_page as SP
from app.docx_doc import DocxDoc
from app.hwpx_doc import HwpxDoc, P, _p

RND = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
TITLE, ORG, WHO = "2026년도 해양 안전 연구개발 계획서", "주관연구개발기관: 한국해양연구원", "작성자 홍길동"
COVER = ["제목", "", "부제", "0000. 00. 00.", "기관명", "작성자"]  # 운반 문서의 문단 글(둘째 = 빈 줄)
ROLES = ["title", "subtitle", "date", "org", "person"]


def _doc():
    """빈 바탕에 손으로 지은 문서 — 표지(가운데 큰 제목 · 빈 줄 · 부제 · 날짜 · 기관 · 작성자 · 2×2 표) + 쪽 나눔 + 본문 세 문단."""
    d, first, plain = SC.open_base()
    like = d._id(next(d._ids[plain].iter(P)))

    def look(pid, **ch):
        d.apply_format([pid], d.derive_format(d.get_format(pid), ch))
    d.set_text(first, TITLE)
    d.apply_format([first], d.get_format(like))  # 평범한 문단의 모양에서 출발(style_page.carrier 와 같은 길)
    look(first, sizePt=22, bold=True, align="center")
    anchor = first
    for text, ch in (("", {"sizePt": 14}), ("세부 추진 계획(안)", {"sizePt": 16, "align": "center"}), ("2026. 3.", {"sizePt": 14, "align": "center"}),
                     (ORG, {"sizePt": 14, "align": "center"}), (WHO, {"sizePt": 12, "align": "right"})):
        anchor = d.insert_after(anchor, [{"kind": "paragraph", "text": text, "templateId": like}])[0]
        look(anchor, **ch)
    for c, text in zip(sorted(d.table_block(plain)["cells"], key=lambda c: (c["row"], c["col"])), ("구분", "내용", "예산", "1,234")):
        d.set_text(c["id"], text)
    anchor = plain
    for n, text in enumerate(("1. 개요", "본문 첫 문단입니다. 본문의 글은 표지보다 깁니다.", "본문 둘째 문단입니다. 본문의 글은 표지보다 깁니다.")):
        anchor = d.insert_after(anchor, [{"kind": "paragraph", "text": text, "templateId": like}])[0]
        if not n:  # 표지 뒤의 첫 문단 = 새 쪽
            d._ids[anchor].set("pageBreak", "1")
            d._touch(d._ids[anchor])
    return HwpxDoc(d.save())


def _carrier(**more):
    src = _doc()
    cand = C.find(src)
    data, info = C.carrier(src, cand["blocks"], **more)
    return src, cand, data, info


def _meta(info):
    return {"kind": "cover", "page": info["page"], "parts": info["parts"]}


def _section_rules(doc):
    return [v["message"] for v in owpml_check.rule_violations(doc) if v["kind"][1] in ("secPr", "ref")]


# ---- 후보 ----------------------------------------------------------------------------------------------------------

def test_find_takes_the_first_page_and_guesses_roles():
    src = _doc()
    blocks = src.blocks()
    cand = C.find(src)
    assert cand["key"] == "cover" and cand["blocks"] == [b["id"] for b in blocks[:7]] and cand["end"] == blocks[6]["id"]  # 쪽 나눔 문단 앞까지
    assert [(p["type"], p["role"]) for p in cand["parts"]] == [*(("text", r) for r in ROLES), ("table", None)]
    assert [p["block"] for p in cand["parts"]] == [blocks[i]["id"] for i in (0, 2, 3, 4, 5, 6)]  # 빈 문단은 부분이 아니다
    title, table = cand["parts"][0], cand["parts"][-1]
    assert (title["sizePt"], title["align"]) == (22, "center") and (table["rows"], table["cols"]) == (2, 2)
    sig = cand["signals"]
    assert sig["bigTitle"] is True and sig["centered"] is True and sig["tableOnly"] is False and sig["ownSection"] is False
    assert (sig["maxSizePt"], sig["bodySizePt"]) == (22, 10)
    flat = json.dumps(cand, ensure_ascii=False)  # 후보에는 가린 글만 — 성명·기관·과제명이 그대로 나가지 않는다
    assert not any(raw in flat for raw in ("홍길동", "한국해양연구원", "해양 안전"))
    assert "제목" in cand["sample"] and "표 2행" in cand["sample"]


def test_find_on_the_rnd_form_is_its_cover_table():
    d = HwpxDoc(RND.read_bytes())
    blocks = [b for b in d.blocks() if not b.get("captionOf")]
    assert blocks[0]["type"] == "table" and (blocks[1].get("pageStart") or "page" in blocks[1])  # 이 양식의 꼴 — 첫 쪽 = 표 하나
    cand = C.find(d)
    assert cand["blocks"] == [blocks[0]["id"]] and cand["end"] == blocks[0]["id"]
    assert [(p["type"], p["role"], p["rows"], p["cols"]) for p in cand["parts"]] == [("table", None, blocks[0]["nRows"], blocks[0]["nCols"])]
    assert cand["signals"]["tableOnly"] is True


class _Fake:
    """블록 열만 가진 문서 — `find` 는 `blocks()` 만 읽는다(hwpx·docx 의 최상위 블록 꼴이 같다)."""

    def __init__(self, blocks):
        self._blocks = blocks

    def blocks(self):
        return self._blocks


def _para(n, text, size=10, **more):
    return {"id": f"p{n}", "type": "paragraph", "text": text, "captionOf": None, "format": {"sizePt": size, "align": "left"}, **more}


def _table(n):
    return {"id": f"t{n}", "type": "table", "nRows": 2, "nCols": 2, "cells": []}


def test_find_without_page_marks_falls_back_to_the_first_heading_or_the_contents_line():
    plain = [_para(0, "사업 계획서", 20), _para(1, "한국대학교"), _para(2, "첫 장"), _para(3, "본문"), _para(4, "본문")]
    assert C.find(_Fake(plain)) is None  # 경계를 못 찾음
    toc = [*plain[:2], _para(2, " 목  차 "), *plain[3:]]
    assert C.find(_Fake(toc))["blocks"] == ["p0", "p1"]
    graph = {"templates": [{"id": 1, "kind": "branch"}, {"id": 2, "kind": "main"}],
             "nodes": [{"para": "p1", "tplNo": 1, "level": 1}, {"para": "p3", "tplNo": 2, "level": 2}, {"para": "p2", "tplNo": 2, "level": 1}]}
    got = C.find(_Fake(plain), graph)  # 주 사슬 1레벨 문단 앞까지
    assert got["blocks"] == ["p0", "p1"] and [p["role"] for p in got["parts"]] == ["title", "org"]
    assert C.find(_Fake([_para(0, "표지 제목", 20), _para(1, "1. 개요", outlineLevel=1), _para(2, "본문")]))["blocks"] == ["p0"]  # 그래프가 없으면 개요 수준 1
    assert C.find(_Fake([_para(0, "1. 개요", outlineLevel=1), _para(1, "본문")])) is None  # 첫 블록이 헤딩 — 표지 없음


def test_find_limits_and_section_signal():
    many = [_para(n, "줄") for n in range(45)] + [_para(45, "다음 쪽", pageStart=True)]
    assert C.find(_Fake(many)) is None  # 블록 40개 초과
    tables = [_table(n) for n in range(5)] + [_para(9, "다음 쪽", pageStart=True)]
    assert C.find(_Fake(tables)) is None  # 표 4개 초과
    assert C.find(_Fake([_para(0, ""), _para(1, "  "), _para(2, "다음 쪽", pageStart=True)])) is None  # 글도 표도 없는 범위
    got = C.find(_Fake([_para(0, "제목", 20, page={}), _table(1), _para(2, "본문", page={}), _para(3, "본문")]))  # 둘째 구역이 시작하는 블록 앞까지
    assert got["blocks"] == ["p0", "t1"] and got["signals"]["ownSection"] is True and got["signals"]["bigTitle"] is True


def test_role_guess_and_mask():
    roles = C._roles([{"text": "연구개발 계획서", "sizePt": 20}, {"text": "(1차년도)", "sizePt": 16}, {"text": "2026년 3월 15일", "sizePt": 12},
                      {"text": "제출일: 2026. 3.", "sizePt": 12}, {"text": "연구책임자 김○○ (한국대학교)", "sizePt": 12}, {"text": "㈜바다기술", "sizePt": 12}, {"text": "비고", "sizePt": 12}])
    assert roles == ["title", "subtitle", "date", "date", "person", "org", "other"]
    assert C._roles([{"text": "한국해양연구원", "sizePt": 10}, {"text": "업무 보고", "sizePt": 10}, {"text": "참고", "sizePt": 10}]) == ["org", "title", "other"]  # 크기가 한 가지 — 낱말에 안 걸린 첫 줄
    assert C._is_date("0000년 0월") and C._is_date("2026.   .   .") and not C._is_date("2026년도 연구개발계획서") and not C._is_date("제3장")
    assert C._mask("홍길동 Kim 2026") == "한글 3자 영문 3자 숫자 4자리" and C._mask("2026. 3. 15.") == "날짜"
    assert C.mask("") == "" and "홍길동" not in C.mask("작성자: 홍길동")
    assert dict(C.ROLES).keys() == C.SAMPLES.keys()


def test_shrink_only_narrows_the_range():
    src = _doc()
    cand = C.find(src)
    got = C.shrink(cand, cand["blocks"][3])  # 날짜 줄까지
    assert got["blocks"] == cand["blocks"][:4] and got["end"] == cand["blocks"][3]
    assert [p["role"] for p in got["parts"]] == ["title", "subtitle", "date"] and "표" not in got["sample"]
    assert len(cand["blocks"]) == 7 and len(cand["parts"]) == 6  # 원래 후보는 그대로
    assert C.shrink(cand, "nope") is None and C.shrink(cand, src.blocks()[8]["id"]) is None  # 범위 밖
    assert C.shrink(cand, cand["end"])["blocks"] == cand["blocks"]


# ---- 운반 문서 · 보기 -------------------------------------------------------------------------------------------------

def test_carrier_keeps_the_layout_and_swaps_text_for_role_samples():
    src, cand, data, info = _carrier()
    cd = SC.doc(data)
    tops = cd.blocks()
    assert [b["type"] for b in tops] == ["paragraph"] * 6 + ["table"]
    assert [b["text"] for b in tops[:6]] == COVER
    head = next(cd._sections[0].iterchildren(P))  # 첫 문단 = 구역 설정 + 표지의 첫 줄(빈 첫 문단이 없어 한 줄 밀리지 않는다)
    assert next(head.iter(_p("secPr")), None) is not None and cd._text(head) == "제목" and len(list(cd._sections[0].iter(_p("secPr")))) == 1
    assert _section_rules(cd) == [] and SC.broken_refs(cd) == []
    assert sorted(c["text"] for c in tops[6]["cells"]) == ["0", "가나다", "가나다", "가나다"]  # 머리 표시 없는 표 — 칸 글은 모두 견본
    whole = " ".join([b["text"] for b in tops[:6]] + [c["text"] for c in tops[6]["cells"]])
    assert not any(raw in whole for raw in ("홍길동", "한국해양연구원", "해양 안전", "1,234", "구분"))
    assert [(p["key"], p["type"], p["role"]) for p in info["parts"]] == [*((f"p{n}", "text", r) for n, r in enumerate(ROLES, 1)), ("p6", "table", None)]
    first = info["parts"][0]
    assert first["sample"] == "제목" and (first["format"]["sizePt"], first["format"]["bold"], first["format"]["align"]) == (22, True, "center")
    assert (info["parts"][5]["rows"], info["parts"][5]["cols"]) == (2, 2)
    assert info["page"] == SP.read(src) == SP.read(cd)  # 쪽 설정 = 원본 그 구역의 것
    assert isinstance(info["fonts"], list) and isinstance(info["losses"], list)
    assert [b["id"] for b in src.blocks()][:7] == cand["blocks"] and src.blocks()[0]["text"] == TITLE  # 원본은 안 바뀐다


def test_view_reads_parts_samples_gaps_and_the_table_spec():
    _, _, data, info = _carrier()
    v = C.view(data, _meta(info))
    assert v["page"] == info["page"]
    assert [(p["type"], p["key"]) for p in v["parts"]] == [*(("text", f"p{n}") for n in range(1, 6)), ("table", "p6")]
    assert [p["role"] for p in v["parts"][:5]] == ROLES and [p["sample"] for p in v["parts"][:5]] == [C.SAMPLES[r] for r in ROLES]
    assert v["parts"][0]["gapBeforeMm"] == 0 and v["parts"][1]["gapBeforeMm"] > 3 and v["parts"][2]["gapBeforeMm"] == 0  # 빈 줄 하나 = 부제 앞 간격
    assert (v["parts"][0]["format"]["sizePt"], v["parts"][0]["format"]["align"]) == (22, "center") and None not in v["parts"][0]["format"].values()
    spec = v["parts"][5]["spec"]
    assert (spec["rows"], spec["cols"], len(spec["cells"])) == (2, 2, 4) and spec["bands"] == info["parts"][5]["bands"]
    bare = C.view(data, {})  # meta 가 비어도 운반 문서만으로 — 역할은 기타 · 쪽은 운반 문서 것
    assert [p["role"] for p in bare["parts"][:5]] == ["other"] * 5 and bare["page"] == info["page"]
    with pytest.raises(ValueError):
        C.view(b"not a zip", {})


def test_carrier_takes_given_roles_and_keeps_text_when_asked():
    src = _doc()
    cand = C.find(src)
    _, info = C.carrier(src, cand["blocks"], roles={cand["parts"][3]["block"]: "label", cand["parts"][0]["block"]: "nope"})
    assert [p["role"] for p in info["parts"]] == ["title", "subtitle", "date", "label", "person", None] and info["parts"][3]["sample"] == "라벨"  # 모르는 코드는 스크립트 어림
    data, info = C.carrier(src, cand["blocks"], keep_text=True)
    tops = SC.doc(data).blocks()
    assert tops[0]["text"] == TITLE and info["parts"][3]["sample"] == ORG and info["parts"][3]["role"] == "org"
    assert sorted(c["text"] for c in tops[6]["cells"]) == sorted(["구분", "내용", "예산", "1,234"])
    for bad in ([], ["nope"], None, [cand["blocks"][1]]):  # 없는 블록 · 빈 문단뿐인 범위
        with pytest.raises(ValueError):
            C.carrier(src, bad)


def test_carrier_of_a_cover_table_starts_with_the_table():
    d = HwpxDoc(RND.read_bytes())
    cand = C.find(d)
    data, info = C.carrier(d, cand["blocks"])
    cd = SC.doc(data)
    tops = cd.blocks()
    assert [b["type"] for b in tops] == ["table"]  # 구역 설정을 품은 첫 문단이 표를 품는다 — 앞에 빈 줄이 없다
    assert (info["parts"][0]["rows"], info["parts"][0]["cols"]) == (tops[0]["nRows"], tops[0]["nCols"]) == (cand["parts"][0]["rows"], cand["parts"][0]["cols"])
    v = C.view(data, _meta(info))
    assert [p["type"] for p in v["parts"]] == ["table"] and v["parts"][0]["gapBeforeMm"] == 0
    assert _section_rules(cd) == []


def test_carrier_from_a_docx_source_is_rebuilt_from_the_summary():
    _, _, data, info = _carrier()
    v = C.view(data, _meta(info))
    src = DocxDoc(D.from_cover(v["parts"], v["page"])[0])
    data2, info2 = C.carrier(src, [b["id"] for b in src.blocks()])
    assert [(p["type"], p["role"]) for p in info2["parts"]] == [*(("text", r) for r in ROLES), ("table", None)]
    assert [p["sample"] for p in info2["parts"][:5]] == [C.SAMPLES[r] for r in ROLES]
    assert (info2["parts"][0]["format"]["sizePt"], info2["parts"][0]["format"]["align"]) == (22, "center")
    assert SC.SPEC_NOTE in info2["losses"]
    cd = SC.doc(data2)
    assert [b["type"] for b in cd.blocks()][:6] == ["paragraph"] * 5 + ["table"] and _section_rules(cd) == []
    page, want = SP.read(cd), info["page"]
    assert (page["widthMm"], page["heightMm"]) == pytest.approx((want["widthMm"], want["heightMm"]), abs=0.1) and page["marginsMm"] == pytest.approx(want["marginsMm"], abs=0.1)
    assert len(C.view(data2, _meta(info2))["parts"]) == 6


# ---- 넣기 ----------------------------------------------------------------------------------------------------------

def test_insert_puts_the_cover_first_and_the_old_first_block_on_the_next_page():
    _, _, data, _ = _carrier()
    t, first, _ = SC.open_base()
    t.set_text(first, "본문 첫 줄")
    tgt = HwpxDoc(t.save())
    before = [b["id"] for b in tgt.blocks()]  # [문단, 평범한 표]
    out = C.insert(tgt, SC.doc(data))
    blocks = tgt.blocks()
    assert len(out["blocks"]) == 7 and [b["id"] for b in blocks] == out["blocks"] + before and out["after"] == before[0]
    assert [b["text"] for b in blocks[:6]] == COVER and blocks[6]["type"] == "table"
    assert blocks[7]["text"] == "본문 첫 줄" and blocks[7].get("pageStart") is True and "page" in blocks[0] and "page" not in blocks[7]
    head = next(tgt._sections[0].iterchildren(P))  # 구역 설정은 문서 첫 문단(= 표지의 첫 문단)에 하나
    assert head is tgt._ids[out["blocks"][0]] and next(head.iter(_p("secPr")), None) is not None and len(list(tgt._sections[0].iter(_p("secPr")))) == 1
    assert _section_rules(tgt) == []
    again = HwpxDoc(tgt.save())
    got = again.blocks()
    assert [b.get("text") for b in got[:8]] == [*COVER, None, "본문 첫 줄"] and got[7].get("pageStart") is True and got[8]["type"] == "table"
    assert SC.broken_refs(again) == []
    with pytest.raises(ValueError):
        C.insert(object(), SC.doc(data))


def test_insert_before_a_document_that_starts_with_a_table():
    _, _, data, _ = _carrier()
    tgt = HwpxDoc(RND.read_bytes())
    rules = lambda doc: [v["message"] for v in owpml_check.rule_violations(doc, hosts=[]) if v["kind"][1] == "secPr"]  # noqa: E731 — 구역 설정 규칙만(문서 전체의 참조는 안 훑는다)
    was, first = rules(tgt), tgt.blocks()[0]["id"]
    out = C.insert(tgt, data)  # 바이트도 받는다
    blocks, at = tgt.blocks(), len(out["blocks"])
    assert out["after"] == first and blocks[at]["id"] == first and blocks[at]["type"] == "table" and blocks[at].get("pageStart") is True
    assert [b["text"] for b in blocks[:6]] == COVER and rules(tgt) == was
    again = HwpxDoc(tgt.save()).blocks()
    assert again[0]["text"] == "제목" and again[at]["type"] == "table" and again[at].get("pageStart") is True

"""표 채우기(spec_헤딩_추출 ② §18): 뒤따르는 「작성 요령」 표 잇기 · 칸 꼴(값을 넣는 방식) · 채울 칸 · 프롬프트(작성요령·지침·칸 입력 규칙·자료) · 답 검사 · 칸 입력 규칙 저장 · API(가짜 LLM)."""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import server, table_agent, works
from app import table_fill as TF
from app.hwpx_doc import HwpxDoc

SAMPLES = Path(__file__).parents[1] / "samples"
RND = SAMPLES / "연구개발계획서_양식.hwpx"
EMPTY = {"version": 0, "rules": [], "builtin": {}, "keeps": [], "lastId": 0}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    table_agent._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()
    table_agent._MEMORY.clear()


@pytest.fixture(scope="module")
def rnd_doc():
    d = HwpxDoc(RND.read_bytes())
    d.blocks()
    return d


def _tables(blocks):
    for b in blocks:
        if b.get("type") == "table":
            yield b
        for c in b.get("cells") or []:
            yield from _tables(c.get("blocks") or [])


def _cover(doc):
    """표지 표(첫 표 — 「보안등급1)」 머리 칸) 의 id."""
    return next(b["id"] for b in _tables(doc.blocks()) if any("보안등급1)" in (c.get("text") or "") for c in b["cells"]) and b["nRows"] > 20)


@pytest.fixture(scope="module")
def cover(rnd_doc):
    tid = _cover(rnd_doc)
    return tid, TF.analyze(rnd_doc, tid, store=copy.deepcopy(EMPTY))


# ---- 「작성 요령」 표 잇기 ---------------------------------------------------------------------------------------------

def test_guide_tables_follow_the_table(rnd_doc):
    tid = _cover(rnd_doc)
    g = TF.guide_tables(rnd_doc, tid)
    assert len(g) == 1 and g[0]["where"] == "guide" and g[0]["title"].startswith("앞표지 작성 요령") and g[0]["table"] != tid and g[0]["para"].startswith("p")
    lines = g[0]["text"].split("\n")
    assert "1. 보안등급: 보안과제에 해당하는 경우 ‘보안’에, 그 외의 경우 '일반’에 [√] 표시합니다." in lines and any(ln.startswith("2. 중앙행정기관명:") for ln in lines)
    assert g[0]["title"] not in lines and len(g[0]["text"]) <= table_agent.GUIDE_TEXT   # 제목 줄은 뺀다(제목 칸의 덧글은 남음)
    assert TF.guide_tables(rnd_doc, g[0]["table"]) == []                               # 작성 요령 표 자신
    assert TF.guide_tables(rnd_doc, "p1") == [] and TF.guide_tables(rnd_doc, "t99999") == [] and TF.guide_tables(rnd_doc, None) == []
    # 같은 절의 표 여럿이 절 끝의 작성 요령 표 하나로 · 다른 절의 것은 안 잇는다(멀다)
    blocks = list(_tables(rnd_doc.blocks()))
    spec = next(b["id"] for b in blocks if any("평가 항목" in (c.get("text") or "") and "주요성능" in (c.get("text") or "") for c in b["cells"]) and b["nRows"] == 12)
    word = next(b["id"] for b in blocks if b["nRows"] == 2 and b["nCols"] == 6 and (b["cells"][0].get("text") or "").strip() == "한글")
    assert TF.guide_tables(rnd_doc, spec)[0]["table"] == TF.guide_tables(rnd_doc, word)[0]["table"]
    sec = next(b["id"] for b in blocks if b["nRows"] == 2 and b["nCols"] == 2 and "보안등급 분류" in (b["cells"][0].get("text") or ""))
    assert TF.guide_tables(rnd_doc, sec) == []
    n_guides = sum(1 for b in blocks if TF.guide_title(b))
    assert n_guides == 30   # TEMP 규칙 1 이 잡는 수(spec ② §15)와 같다


def test_guide_title_rule():
    cell = lambda r, c, *texts: {"row": r, "col": c, "blocks": [{"type": "paragraph", "id": f"p{r}{c}{i}", "text": t} for i, t in enumerate(texts)]}  # noqa: E731
    assert TF.guide_title({"cells": [cell(0, 0, "작성 요령"), cell(1, 0, "◦ 무엇을 적는다")]}) == ("작성 요령", "p000")
    assert TF.guide_title({"cells": [cell(0, 0, "", "작성요령(계속)")]})[0] == "작성요령(계속)"
    assert TF.guide_title({"cells": [cell(0, 0, "구분"), cell(0, 1, "작성 방법")]})[1] == "p010"           # 처음 두 행 안의 제목 칸
    assert TF.guide_title({"cells": [cell(0, 0, "구분"), cell(2, 0, "작성 요령")]}) is None                # 셋째 행부터는 아님
    assert TF.guide_title({"cells": [cell(0, 0, "이 표는 작성 요령에 따라 기재한 것이다")]}) is None       # 문장 속 낱말
    note = TF.guide_note({"id": "t9", "cells": [cell(0, 0, "작성 요령", "삭제 후 제출"), cell(1, 0, "1. 가: 나", "2. 다: 라")]})
    assert note == {"where": "guide", "table": "t9", "para": "p000", "title": "작성 요령", "text": "삭제 후 제출\n1. 가: 나\n2. 다: 라"}
    assert TF.guide_note({"id": "t9", "cells": [cell(0, 0, "구분")]}) is None


# ---- 칸 꼴 -----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, want", [
    ("", ("blank", True)), ("   ", ("blank", True)),
    ("[ ] 신청용 [ ] 협약용", ("check", True)), ("[ ] 신청용 [ √ ] 협약용", ("check", False)), ("일반[√] 보안[ ]", ("check", False)), ("징수[ ] 비징수[ ]", ("check", True)),
    ("□ 해당 □ 해당 없음", ("check", True)), ("■ 해당 □ 해당 없음", ("check", False)),
    ("YYYY.MM.DD", ("date", True)), ("20xx.xx.xx", ("date", True)), ("20  년   월   일", ("date", True)), ("2026 년 3 월 24 일", ("date", False)), ("20 . . .", ("date", True)),
    ("0,000", ("num", True)), ("000,000", ("num", True)), ("00%", ("pct", True)), ("○○", ("ph", True)), ("제20xx-xx호", ("ph", True)), ("○○대학교", ("ph", True)),
    ("1,234", ("num", False)), ("12.5%", ("pct", False)), ("한국선급", ("text", False)), ("-", ("text", False)),
    ("2026년 3월 24일 협약을 체결하고 그 뒤 변경 사항을 여기에 적었다", ("text", False)),
])
def test_cell_form(text, want):
    assert TF.cell_form(text) == want


def test_cell_form_kinds_and_skeletons():
    assert TF.cell_form("XXX 주식회사 서울 본사", {"placeholder": 1}) == ("ph", True) and TF.cell_form("기관 이름을 적은 글", {"placeholder": 1, "plain": 1}) == ("text", False)
    assert TF._check_skel("[ ] 신청용 [ √ ] 협약용") == TF._check_skel("[√] 신청용 [  ] 협약용") != TF._check_skel("[ ] 신청 [ √ ] 협약용")
    assert TF._check_skel("□ 해당 ■ 없음") == TF._check_skel("■ 해당 □ 없음")
    assert TF._date_skel("20  년   월   일") == TF._date_skel("2026 년 3 월 24 일") and TF._date_skel("YYYY.MM.DD") == TF._date_skel("2026.03.24") != TF._date_skel("2026-03-24")


def test_box_glyph_as_bullet_is_not_a_check_cell():
    # 「□」 는 이 양식의 개요 3레벨 글머리이기도 하다 — 뒤 항목 글이 짧을 때만 체크 칸
    assert TF.cell_form("□ 연구개발기술(제품)의 정의 및 범위를 구체적으로 서술한 글") == ("text", False)
    assert TF.cell_form("□ 첫째 글머리 줄에 긴 글이 이어진다 그리고 더 이어진다\n□ 둘째 글머리 줄에도 긴 글이 이어진다 계속") == ("text", False)
    assert TF.cell_form("□ 예  □ 아니오") == ("check", True) and TF.cell_form("■ 예  □ 아니오") == ("check", False) and TF.cell_form("☐ 해당") == ("check", True)
    assert TF.cell_form("[ ] 해당\n□ 아래에 그 사유를 구체적으로 길게 적는 글머리 줄이 이어진다") == ("check", True)   # 대괄호 자리는 그대로 체크


def test_doc_text_drops_fill_table_and_guide_tables_even_when_nested():
    para = lambda i, t: {"type": "paragraph", "id": i, "text": t}  # noqa: E731
    cell = lambda r, c, *bl: {"row": r, "col": c, "blocks": list(bl)}  # noqa: E731
    inner = {"type": "table", "id": "t2", "cells": [cell(0, 0, para("p3", "안쪽 값"))]}
    guide = {"type": "table", "id": "t3", "cells": [cell(0, 0, para("p4", "작성 요령")), cell(1, 0, para("p5", "요령 글"))]}
    outer = {"type": "table", "id": "t1", "cells": [cell(0, 0, para("p1", "머리")), cell(0, 1, para("p2", "값"), inner, guide)]}
    text, cut, full = TF.doc_text([para("p0", "본문"), outer], skip={"t2"})
    assert text == "본문\n머리 | 값" and not cut and full == len(text)            # 채우는 표가 칸 안 표여도 제 글은 안 든다
    assert TF.doc_text([outer], skip=set())[0] == "머리 | 값\n안쪽 값"              # 「작성 요령」 표는 칸 안에 있어도 늘 뺀다
    assert TF.guide_note(guide)["text"] == "요령 글"                                # 작성요령으로 읽을 때는 그 글이 든다


def test_place_filled_and_rule_fixed_text(cover, rnd_doc):
    tid, an = cover
    assert TF.place_of(None) is None and TF.place_of({"owner": {"root": True}}) is None and TF.place_of({"owner": {"text": "  "}}) is None
    place = TF.place_of({"owner": {"text": "2-2. 연구개발 목표 및 내용", "path": ["2. 목표"], "division": {"text": "[주관연구개발기관]"}}})
    assert place == {"heading": "2-2. 연구개발 목표 및 내용", "path": ["2. 목표"], "division": "[주관연구개발기관]"}
    assert TF.payload(an, None, "", "", place)["place"] == place and "place" not in TF.payload(an)
    assert all("filled" not in t for t in TF.payload(an)["targets"])               # 빈 자리에는 filled 가 없다
    over = TF.analyze(rnd_doc, tid, overwrite=True, store=copy.deepcopy(EMPTY))
    assert sum(1 for t in TF.payload(over)["targets"] if t.get("filled")) == over["counts"]["fields"] - over["counts"]["open"] > 0
    # 지침·규칙이 정한 고정 글(where "rule") — 근거 구절은 자료가 아니라 지침·규칙 글에서 찾는다
    rules = TF.rules_haystack("(없음)", "### 이 표 지침\n해당 없는 칸은 「-」 로 적는다", table_agent.rules_text({}, {}))
    got = TF.apply({"fills": [one("W3", "-", "해당 없는 칸은 「-」 로 적는다", "rule"), one("W4", "-", "지침에 없는 문장", "rule"), one("W6", "-", "해당 없는 칸은 「-」 로 적는다", "material")]}, an, "자료 글", rules)["fills"]
    assert [(f["ref"], f["where"], f["warn"]) for f in got] == [("W3", "rule", []), ("W4", "rule", ["근거 구절을 지침·규칙에서 못 찾음"]), ("W6", "material", ["근거 구절을 자료에서 못 찾음"])]
    for s in ("place = 이 표가 놓인 자리", "고정 글", "where 에 rule", "filled 가 true 인 칸은", "material | document | table | context | rule"):
        assert s in TF.CONTRACT, s
    assert "지금 열어 둔 이 문서" in TF.JOB_NOTE and "값의 출처로 쓰지 않고" in TF.JOB_NOTE and "material 은 사용자가" in TF.JOB_NOTE


# ---- 채울 칸 ---------------------------------------------------------------------------------------------------------

def test_analyze_cover_targets(cover, rnd_doc):
    tid, an = cover
    c = an["counts"]
    assert an["unit"] == "천원" and c["fields"] > 100 and c["targets"] == c["open"] == len(an["targets"]) and c["skipped"] == 0 and c["fields"] > c["open"]   # 미리 체크된 칸은 채워진 칸
    by = {t["ref"]: t for t in an["targets"]}
    assert by["Y2"]["form"] == "check" and by["Y2"]["now"].replace(" ", "") == "일반[]보안[]" and by["L9"]["form"] == "pct" and by["F6"]["form"] == "ph" and by["W3"]["form"] == "blank"
    assert by["W3"]["rowName"].endswith("세부사업명4)") and by["W3"]["colName"] == "" and by["W3"]["name"] == by["W3"]["rowName"]   # 키-값 띠 — 왼쪽 머리 글만
    assert by["W3"]["cell"].startswith("c") and all(an["anchor"][(t["row"], t["col"])] == t["ref"] for t in an["targets"])
    assert set(an["forms"]) <= set(TF.FORM_KO) and "체크" in TF.forms_text(an["forms"]) and "빈 칸" in TF.forms_text(an["forms"])
    # 범위 — 그 안에 통째로 든 칸만 · 채워진 칸도(overwrite)
    part = TF.analyze(rnd_doc, tid, {"r0": 0, "c0": 0, "r1": 3, "c1": 29}, store=copy.deepcopy(EMPTY))
    assert part["range"] == {"r0": 0, "c0": 0, "r1": 3, "c1": 29} and 0 < len(part["targets"]) < len(an["targets"]) and all(t["row"] <= 3 for t in part["targets"])
    assert part["counts"]["fields"] == c["fields"] and len(part["cells"]) == len(an["cells"])   # 격자·수는 표 전체
    over = TF.analyze(rnd_doc, tid, overwrite=True, store=copy.deepcopy(EMPTY))
    assert len(over["targets"]) == c["fields"] and any(not t["open"] for t in over["targets"])
    assert TF.analyze(rnd_doc, "p1") is None
    box = next(b["id"] for b in _tables(rnd_doc.blocks()) if len(b["cells"]) == 1)
    assert TF.analyze(rnd_doc, box)["targets"] == [] and "1칸 표" in TF.analyze(rnd_doc, box)["note"]


# ---- 프롬프트 --------------------------------------------------------------------------------------------------------

def test_payload_and_prompt_sections(cover, rnd_doc):
    tid, an = cover
    notes = [{"where": "before", "text": "※ 금액은 천원 단위"}] + TF.guide_tables(rnd_doc, tid)
    data = TF.payload(an, {"before": ["표지"], "after": []}, "과제명: 자율운항 데이터 수집", "문서 글")
    assert data["table"] == tid and data["unit"] == "천원" and len(data["grid"]) == an["rows"] and len(data["targets"]) == len(an["targets"]) and data["document"] == "문서 글"
    y2 = next(t for t in data["targets"] if t["cell"] == "Y2")
    assert y2["form"] == "체크" and "보안[" in y2["now"] and "document" not in TF.payload(an)
    assert any(tok.startswith("A3|행헤더|중앙행정기관명2)") for row in data["grid"] for tok in row)
    common, own = {"instructions": "공통 지침", "rules": "날짜는 YYYY.MM.DD"}, {"instructions": "", "rules": "체크는 ■"}
    text = TF.content(data, TF.notes_text(notes), TF.guide_text(common["instructions"], own["instructions"], form="양식 표 글"), table_agent.rules_text(common, own), "\n\n## 할 일 — 이관\n전제")
    for s in ("## 할 일 — 이관\n전제", "## 작성요령(문서에서)\n- (표 앞) ※ 금액은 천원 단위\n- (작성 요령 표) 앞표지 작성 요령", "  1. 보안등급: 보안과제에 해당하는 경우",
              "## 지침\n### 양식 표 지침(이 양식의 문서에 공통)\n양식 표 글\n\n### 공통 표 지침\n공통 지침", "## 칸 입력 규칙", "### 기본 규칙(앱)\n- 체크 칸",
              "### 공통 규칙(이 문서의 모든 표)\n날짜는 YYYY.MM.DD\n\n### 이 표 규칙\n체크는 ■", "## 자료(JSON)\n{"):
        assert s in text, s
    assert text.index("## 할 일") < text.index("## 작성요령") < text.index("## 지침") < text.index("## 칸 입력 규칙") < text.index("## 자료(JSON)") and "이 표 지침" not in text
    assert json.loads(text.split("## 자료(JSON)\n", 1)[1])["material"] == "과제명: 자율운항 데이터 수집"
    assert TF.notes_text([]) == "(없음)" and TF.guide_text("", " ") == "(없음)" and table_agent.rules_text({}, {}).startswith("### 기본 규칙(앱)\n")
    assert table_agent.rules_text({}, {}, default="") == ""
    # 문서 글 — 채우는 표와 「작성 요령」 표는 빼고, 표는 행마다 한 줄
    doc, cut, full = TF.doc_text(rnd_doc.blocks(), skip={tid})
    assert not cut and full == len(doc) > 10_000 and "보안등급1)" not in doc.split("< 요 약 문 >")[0] and "1. 보안등급: 보안과제에" not in doc and "세부사업명1) | " in doc
    short, cut2, full2 = TF.doc_text(rnd_doc.blocks(), cap=500)
    assert cut2 and len(short) == 500 and full2 > full


# ---- 답 검사 ---------------------------------------------------------------------------------------------------------

def one(cell, text, source="산업통상부", where="material", reason="근거"):
    return {"cell": cell, "text": text, "source": source, "where": where, "reason": reason}


def test_apply_checks_and_warnings(cover):
    _, an = cover
    by = {t["ref"]: t for t in an["targets"]}
    hay = TF.haystack({"material": "중앙행정기관: 산업통상부\n세부사업명 조선해양산업기술개발 · 협약용 · 지분 50 %", "grid": [["A3|행헤더|중앙행정기관명2)"]], "before": ["표지 글"], "after": []})
    y2 = by["Y2"]["now"]
    out = TF.apply({"fills": [
        one("w3", " 조선해양산업기술개발 ", "세부사업명  조선해양산업기술개발"),        # 소문자 주소·공백 — 받음 · 근거는 공백을 떼고 찾는다
        one("X3", "산업통상부"),                                                       # 병합 칸 안쪽 주소 → 왼쪽 위(W3) — 같은 칸 두 번
        one("W4", "자율운항선박 플랫폼", "자료에 없는 구절"),                            # 근거 구절 없음 — 경고
        one("Y2", y2.replace("일반[", "일반[√", 1), "협약용"),                          # 체크 — 괄호 안 표시만
        one("J1", "[ √ ] 통합형"),                                                     # 체크 칸의 글을 바꿈 — 거절
        one("J2", by["J2"]["now"]),                                                    # 그대로 — 바꿀 것 없음
        one("L9", "50%", "지분 50 %"), one("U9", "절반"),                              # 비율 칸 — 수 / 수가 아님
        one("A3", "산업통상부"), one("ZZ99", "x"), one("W6", ""), one("W7", "가" * (TF.CELL_MAX + 1)),
        "쓰레기", {"cell": None},
    ], "note": "시험"}, an, hay)
    got = {f["ref"]: f for f in out["fills"]}
    assert list(got) == ["Y2", "W3", "W4", "L9", "U9"]   # 행 → 열 순
    assert got["W3"]["text"] == "조선해양산업기술개발" and got["W3"]["quoted"] and got["W3"]["warn"] == [] and got["W3"]["cell"] == by["W3"]["cell"] and got["W3"]["where"] == "material"
    assert got["W4"]["warn"] == ["근거 구절을 자료에서 못 찾음"] and not got["W4"]["quoted"]
    assert got["Y2"]["form"] == "check" and "일반[√" in got["Y2"]["text"] and got["Y2"]["now"] == y2 and got["Y2"]["warn"] == []
    assert got["L9"]["warn"] == [] and got["U9"]["warn"] == ["수가 아님"]
    why = {r["ref"]: r["why"] for r in out["rejected"]}
    assert why["W3"] == "같은 칸을 두 번 답함" and "체크 칸의 글이 바뀜" in why["J1"] and why["A3"].startswith("채울 칸이 아님") and why["ZZ99"] == "표에 없는 주소" and "너무 깁니다" in why["W7"]
    assert why[""] == "표에 없는 주소" and "J2" not in why and "W6" not in why
    assert out["counts"] == {"fills": 5, "clean": 3, "warn": 2, "rejected": 6, "left": len(an["targets"]) - 5}
    assert TF.apply(None, an)["fills"] == [] and TF.apply({"fills": "x"}, an)["counts"]["rejected"] == 0
    # 비율 자리표시가 % 꼴인데 % 없이 · 날짜 꼴이 다름 · 채워진 칸을 바꿈(overwrite)
    t = {"ref": "A1", "cell": "c1", "row": 0, "col": 0, "name": "", "open": True}
    mini = {"anchor": {(0, 0): "A1", (0, 1): "B1", (0, 2): "C1"},
            "targets": [{**t, "form": "pct", "now": "00%"}, {**t, "ref": "B1", "col": 1, "form": "date", "now": "20  년  월  일"}, {**t, "ref": "C1", "col": 2, "form": "text", "now": "옛 글", "open": False}]}
    m = {f["ref"]: f["warn"] for f in TF.apply({"fills": [one("A1", "50", "50"), one("B1", "2026.03.24", "50"), one("C1", "새 글", "50")]}, mini, "50")["fills"]}
    assert m == {"A1": ["자리표시는 % 꼴"], "B1": ["날짜 꼴이 자리표시와 다름"], "C1": ["이미 채운 칸을 바꿈"]}
    assert TF.apply({"fills": [one("B1", "2026 년 3 월 24 일", "50")]}, mini, "50")["fills"][0]["warn"] == []


# ---- 칸 입력 규칙 저장 · 묶음 글 ---------------------------------------------------------------------------------------

def test_rules_store_and_agent_prompt(monkeypatch):
    monkeypatch.setenv("NFM_WORKS", "off")
    wid = "abc123def456"
    r = table_agent.save(wid, "t1", instructions="지침", rules="금액은 천원")
    assert r["rules"] == "금액은 천원" and r["instructions"] == "지침" and r["version"] == 1
    r2 = table_agent.save(wid, "t1", instructions="지침 2", expect=1)
    assert r2["rules"] == "금액은 천원" and r2["version"] == 2   # 주지 않은 항목은 그대로
    c = table_agent.save(wid, table_agent.COMMON, rules="날짜는 YYYY.MM.DD")
    assert c["rules"] == "날짜는 YYYY.MM.DD" and c["instructions"] == "" and "formulas" not in c
    with pytest.raises(ValueError):
        table_agent.save(wid, "t1", rules="x" * (table_agent.TEXT_MAX + 1))
    with pytest.raises(ValueError):
        table_agent.save(wid, "t1", rules=5)
    txt = table_agent.prompt(None, c, r2, tid="t1", notes=[{"where": "guide", "title": "작성 요령", "text": "1. 가: 나\n2. 다: 라"}], forms="체크 2 · 빈 칸 3")
    for s in ("- (작성 요령 표) 작성 요령\n  1. 가: 나\n  2. 다: 라", "[칸 입력 규칙]", "### 기본 규칙(앱)\n- 체크 칸", "### 공통 규칙(이 문서의 모든 표)\n날짜는 YYYY.MM.DD", "### 이 표 규칙\n금액은 천원",
              "표에서 읽은 칸 꼴: 체크 2 · 빈 칸 3"):
        assert s in txt, s
    assert txt.index("[이 표 지침]") < txt.index("[칸 입력 규칙]")


def test_all_tables_skips_llm_detail_records():
    wid = "0123456789ab"
    assert works.create(wid, "a.hwpx", "hwpx", b"x") is not None
    table_agent.save(wid, "t5", instructions="지침")
    for name in ("fill_1794400000000", "formula_1794400000001", "make_1794400000002"):   # 같은 폴더에 쌓이는 LLM 호출 상세 기록
        assert works.add_detail(wid, "tables", name, {"prompt": "…", "response": None})
    assert sorted(p.stem for p in (works.folder(wid) / "tables").glob("*.json")) == ["fill_1794400000000", "formula_1794400000001", "make_1794400000002", "t5"]
    assert set(table_agent.all_tables(wid)["tables"]) == {"t5"}


# ---- API -------------------------------------------------------------------------------------------------------------

def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def test_api_agent_view_has_guides_rules_forms():
    server.DOCS.clear()
    c = TestClient(server.app)
    try:
        d = _upload(c, RND)
        tid = _cover(server.DOCS[d].doc)
        g = c.get(f"/api/docs/{d}/headings/tables/{tid}/agent").json()
        assert g["stage3"] is False and [n["where"] for n in g["notes"]] == ["guide"] and g["notes"][0]["title"].startswith("앞표지 작성 요령")   # 3단계 없이도 「작성 요령」 표는 잇는다
        assert g["rulesDefault"] == table_agent.DEFAULT_RULES and g["own"]["rules"] == "" and g["common"]["rules"] == ""
        assert g["forms"]["counts"]["check"] >= 4 and g["forms"]["open"] > 100 and "체크" in g["forms"]["text"]
        assert "- (작성 요령 표) 앞표지 작성 요령" in g["prompt"] and "[칸 입력 규칙]" in g["prompt"] and "표에서 읽은 칸 꼴: " in g["prompt"]
        v = c.put(f"/api/docs/{d}/headings/tables/{tid}/agent", json={"rules": "체크는 √ 로", "version": 0}).json()
        assert v["own"]["rules"] == "체크는 √ 로" and v["own"]["instructions"] == "" and v["own"]["version"] == 1 and "### 이 표 규칙\n체크는 √ 로" in v["prompt"]
        cm = c.put(f"/api/docs/{d}/headings/tables/_common/agent", json={"rules": "금액은 천원"}).json()
        assert cm["common"]["rules"] == "금액은 천원" and cm["forms"] is None and cm["notes"] == [] and "### 공통 규칙(이 문서의 모든 표)\n금액은 천원" in cm["prompt"]
        assert c.put(f"/api/docs/{d}/headings/tables/{tid}/agent", json={"rules": 5}).status_code == 400
        ev = [e for e in works.events(d) if e["kind"] == "tableGuide"]
        assert ev[0]["rules"] == len("체크는 √ 로") and ev[0]["chars"] == 0
    finally:
        server.DOCS.clear()


def test_api_fill_propose_and_apply_with_stub(monkeypatch):
    server.DOCS.clear()
    c = TestClient(server.app)
    seen = {}
    try:
        d = _upload(c, RND)
        s = server.DOCS[d]
        tid = _cover(s.doc)
        url = f"/api/docs/{d}/tables/{tid}/fill"
        dry = c.post(url, json={"dry": True})
        assert dry.status_code == 200, dry.text
        v0 = dry.json()
        by = {t["ref"]: t for t in v0["targets"]}
        assert v0["llm"] is False and v0["counts"]["targets"] == len(v0["targets"]) > 100 and v0["guides"] == 1 and v0["notes"] >= 1 and v0["doc"]["sent"] > 10_000 and not v0["doc"]["cut"]
        assert v0["rev"] == s.rev and v0["unit"] == "천원" and by["Y2"]["form"] == "check" and "fills" not in v0 and v0["job"] is None and v0["blocked"] is None
        assert c.post(url, json={"dry": True, "useDoc": False}).json()["doc"] == {"chars": 0, "sent": 0, "cut": False}
        assert c.post(url, json={}).status_code == 503                                         # LLM 꺼짐
        assert c.post(url, json={"material": 5}).status_code == 400 and c.post(url, json={"effort": "최대"}).status_code == 400
        assert c.post(f"/api/docs/{d}/tables/t99999/fill", json={"dry": True}).status_code == 404
        box = next(b["id"] for b in _tables(s.doc.blocks()) if len(b["cells"]) == 1)
        assert c.post(f"/api/docs/{d}/tables/{box}/fill", json={"dry": True}).json()["targets"] == [] and c.post(f"/api/docs/{d}/tables/{box}/fill", json={}).status_code == 400

        def fake(schema, content, what, **kw):
            seen.update(schema=schema, content=content, what=what, kw=kw)
            return {"data": {"fills": [one("W3", "조선해양산업기술개발", "세부사업명: 조선해양산업기술개발"), one("Y2", by["Y2"]["now"].replace("일반[", "일반[√", 1), "일반과제"),
                                       one("W4", "지어낸 값", "없는 구절"), one("A3", "머리 칸")], "note": "자료에 있는 두 칸만 채움"},
                    "backend": "sdk", "model": "m", "effort": kw.get("effort"), "ms": 12, "costUsd": 0.02, "error": None}
        monkeypatch.setattr(TF.llm, "call", fake)
        monkeypatch.setattr(server.tables_api.llm, "status", lambda: {"available": True})
        table_agent.save(d, tid, instructions="표지는 협약서 기준", rules="체크는 √ 로")
        r = c.post(url, json={"material": "세부사업명: 조선해양산업기술개발\n보안: 일반과제", "effort": "low", "range": {"r0": 0, "c0": 0, "r1": 4, "c1": 29}})   # W4 는 두 행에 걸친 칸(4~5행)
        assert r.status_code == 200, r.text
        v = r.json()
        assert [f["ref"] for f in v["fills"]] == ["Y2", "W3", "W4"] and v["answer"].startswith("자료에 있는") and v["call"]["backend"] == "sdk" and v["range"] == {"r0": 0, "c0": 0, "r1": 4, "c1": 29}
        assert v["fills"][2]["warn"] == ["근거 구절을 자료에서 못 찾음"] and v["rejected"][0]["ref"] == "A3" and v["counts"]["fills"] == 3 and v["counts"]["clean"] == 2 and v["counts"]["rejected"] == 1
        assert seen["what"] == "table-fill" and seen["kw"]["effort"] == "low" and seen["schema"] is TF.SCHEMA
        for part in ("## 작성요령(문서에서)\n- (작성 요령 표) 앞표지 작성 요령", "### 이 표 지침\n표지는 협약서 기준", "### 이 표 규칙\n체크는 √ 로", "### 기본 규칙(앱)", '"material":"세부사업명: 조선해양산업기술개발\\n보안: 일반과제"',
                     '"document":"', '{"cell":"W3","row":"사업명 › 세부사업명4)","col":"","form":"빈 칸","now":""}'):
            assert part in seen["content"], part
        assert '"cell":"W6"' not in seen["content"]   # 범위 밖 칸은 targets 에 없다
        assert s.rev == v0["rev"]                      # 제안은 문서를 안 바꾼다
        ev = [e for e in works.events(d) if e["kind"] == "tableFillLlm"]
        assert len(ev) == 1 and ev[0]["table"] == tid and ev[0]["counts"]["fills"] == 3 and ev[0]["backend"] == "sdk" and ev[0]["material"] > 0 and ev[0]["doc"] > 10_000
        # 문서에 반영 — 고른 것만 · 한 트랜잭션 · 그 사이 바뀐 칸은 건너뜀
        apply_url = url + "/apply"
        w3, y2 = v["fills"][1], v["fills"][0]
        assert c.post(apply_url, json={"fills": []}).status_code == 400 and c.post(apply_url, json={"fills": [{"cell": "p1", "text": "x"}]}).status_code == 400
        assert c.post(apply_url, json={"fills": [{"cell": w3["cell"], "text": ""}]}).status_code == 400
        assert c.post(apply_url, json={"fills": [{"cell": w3["cell"], "text": "a"}, {"cell": w3["cell"], "text": "b"}]}).status_code == 400
        assert c.post(apply_url, json={"fills": [{"cell": w3["cell"], "text": "x", "was": "딴 글"}]}).status_code == 409
        a = c.post(apply_url, json={"fills": [{"cell": w3["cell"], "text": w3["text"], "was": w3["now"]}, {"cell": y2["cell"], "text": y2["text"], "was": y2["now"]},
                                              {"cell": by["W4"]["cell"], "text": "x", "was": "딴 글"}]})
        assert a.status_code == 200, a.text
        av = a.json()
        assert av["filled"] == {"table": tid, "cells": [w3["cell"], y2["cell"]], "skipped": [{"cell": by["W4"]["cell"], "why": "제안을 받은 뒤 칸 글이 바뀜"}]}
        assert av["undo"] == 1 and av["rev"] == v0["rev"] + 1 and av["tops"]["blocks"] and av["editedCount"] >= 2
        cells = {x["id"]: x["text"] for x in s.doc.table_block(tid)["cells"]}
        assert cells[w3["cell"]] == "조선해양산업기술개발" and "일반[√" in cells[y2["cell"]] and cells[by["W4"]["cell"]] == ""
        assert [e for e in works.events(d) if e["kind"] == "tableFill"][0]["cells"] == 2
        # 채운 칸은 다음 미리보기에서 빠진다 · 실행 취소 한 번으로 둘 다 돌아온다
        again = {t["ref"] for t in c.post(url, json={"dry": True}).json()["targets"]}
        assert "W3" not in again and "Y2" not in again and "W4" in again
        assert c.post(f"/api/docs/{d}/undo").status_code == 200
        cells = {x["id"]: x["text"] for x in server.DOCS[d].doc.table_block(tid)["cells"]}
        assert cells[w3["cell"]] == "" and cells[y2["cell"]] == y2["now"]
        # 여러 줄 — 칸의 문단이 줄 수만큼
        m = c.post(apply_url, json={"fills": [{"cell": w3["cell"], "text": "첫 줄\n둘째 줄"}]})
        assert m.status_code == 200 and {x["id"]: x["text"] for x in server.DOCS[d].doc.table_block(tid)["cells"]}[w3["cell"]] == "첫 줄\n둘째 줄"
        # 답이 없으면 502(기록은 남김)
        monkeypatch.setattr(TF.llm, "call", lambda *a, **k: {"data": None, "backend": None, "ms": 1, "costUsd": None, "error": "sdk: 시간 초과"})
        bad = c.post(url, json={})
        assert bad.status_code == 502 and "시간 초과" in bad.json()["detail"] and len([e for e in works.events(d) if e["kind"] == "tableFillLlm"]) == 2
    finally:
        server.DOCS.clear()

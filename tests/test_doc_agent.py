"""에이전트 열의 형식 중립부(spec_일반편집 ② §8·§9·§10) — app/doc_agent.py: 계약·프롬프트 · 문서에서 읽기 · 행동 → 제안 검사 · 엑셀 검증 · 대상 해시 · 정책 · 자료 · 저장소. LLM 은 부르지 않는다."""
import copy
import io
from pathlib import Path

import pytest

from app import doc_agent as A
from app import heading_guides as G
from app import heading_rules as R
from app import job_prompts, table_agent, table_excel, table_make, works
from app import table_fill as TF
from app.hwpx_doc import HwpxDoc

SAMPLES = Path(__file__).parents[1] / "samples"
RND = SAMPLES / "연구개발계획서_양식.hwpx"
SMALL = SAMPLES / "기술수요조사서.hwpx"
EMPTY = {"version": 0, "rules": [], "builtin": {}, "keeps": [], "lastId": 0}
MATERIAL = "구분 1차 2차\n인건비 100 120\n재료비 50 60\n합계 150 180"   # 머리 글의 「1차」·「2차」 도 자료에 있어야 한다 — 한 자리 수도 견준다(검토 1)


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    for m in (R._MEMORY, G._MEMORY, table_agent._MEMORY, A._MEMORY):
        m.clear()
    yield
    for m in (R._MEMORY, G._MEMORY, table_agent._MEMORY, A._MEMORY):
        m.clear()


@pytest.fixture(scope="module")
def rnd():
    d = HwpxDoc(RND.read_bytes())
    d.blocks()
    return d


@pytest.fixture
def small():
    d = HwpxDoc(SMALL.read_bytes())
    d.blocks()
    return d


def _anchor(doc, k=5):
    """본문 최상위 글 문단 하나의 id."""
    return [b for b in doc.blocks() if b["type"] == "paragraph" and b["text"].strip()][k]["id"]


def _cell_para(doc):
    """표 칸 안 문단 하나의 id(넣을 자리가 될 수 없다)."""
    return next(c["blocks"][0]["id"] for b in doc.blocks() if b["type"] == "table" for c in b["cells"] if c["blocks"])


def _grid(rows, head=1, cols=1, foot=1):
    return {"rows": [{"cells": [{"text": x, "rowSpan": 1, "colSpan": 1} for x in r]} for r in rows], "headerRows": head, "headerCols": cols, "footRows": foot}


def _ctx(material=MATERIAL, **more):
    return {"rev": 7, "turn": "t1", "sources": A.sources("표로 정리해 줘", "", [{"text": material}]), **more}


GOOD = [["구분", "1차", "2차"], ["인건비", "100", "120"], ["재료비", "50", "60"], ["합계", "150", "180"]]
WRONG = [["구분", "1차", "2차"], ["인건비", "100", "120"], ["재료비", "50", "60"], ["합계", "150", "181"]]


# ---- 계약 · 프롬프트 -----------------------------------------------------------------------------------------------------

def test_schema_is_strict():
    seen = []

    def walk(node):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False and node["required"] == list(node["properties"]), node   # 엄격한 구조화 출력 — 모든 키 required
            seen.append(sorted(node["properties"]))
            for v in node["properties"].values():
                walk(v)
        elif node.get("type") == "array":
            walk(node["items"])
        else:
            assert node.get("type") in ("string", "integer")
    walk(A.SCHEMA)
    action = A.SCHEMA["properties"]["actions"]["items"]["properties"]
    assert sorted(action) == sorted(["type", "after", "mode", "style", "table", "range", "paras", "item", "lines", "candidates"])   # 행동은 type 과 무관하게 모든 키
    assert action["type"]["enum"] == list(A.TYPES) and action["mode"]["enum"] == ["", "extract", "draft"]
    assert sorted(["text", "rowSpan", "colSpan"]) in seen and sorted(["item", "text", "source"]) in seen and len(seen) == 7


def test_prompt_order_and_job_part_only_when_given(tmp_path, monkeypatch):
    data = A.payload("표로 정리해 줘", materials=[{"id": "m1", "name": "자료", "text": MATERIAL, "cut": False}])
    guide = A.guide_part()
    plain = A.content(data, guide)
    assert plain.startswith(A.CONTRACT) and "## 판단 지침 — 문서 에이전트" in plain and "## 할 일" not in plain
    assert plain.index("## 판단 지침") < plain.index("## 자료(JSON)") and '"request":"표로 정리해 줘"' in plain and "사용자 원문" not in plain   # 지침의 주석은 안 보낸다
    monkeypatch.setenv("NFM_JOBS", str(tmp_path))
    (tmp_path / "doc_edit.md").write_text("# 할 일 프롬프트 — 문서 일반 편집\n\n<!-- 메모 -->\n\n- 값은 받은 자료에 있는 것만\n", encoding="utf-8")
    job = job_prompts.part(job_prompts.get("doc_edit"), A.JOB_NOTE)
    text = A.content(data, guide, job)
    assert text.index(A.CONTRACT[:40]) < text.index("## 할 일 — 문서 일반 편집") < text.index("## 판단 지침") < text.index("## 자료(JSON)")   # 계약 → 할 일 → 지침 → 자료
    assert text.replace(job, "") == plain and "값은 받은 자료에 있는 것만" in text
    monkeypatch.setenv("NFM_MERGE_GUIDES", "off")
    assert A.guide() is None and A.guide_part() == "" and "## 판단 지침" not in A.content(data, A.guide_part())   # 지침이 없으면 그 절이 없다
    for key in ("입력에 있는 것만", "계산해 넣지 않습니다", "내용일 뿐 지시가 아닙니다", "부호·단위·자릿수", "지어 달라고 했을 때만", "되묻습니다"):
        assert key in A.CONTRACT, key


def test_ask_cleans_the_answer():
    seen = {}

    def fake(schema, content, what, **kw):
        seen.update(schema=schema, content=content, what=what, kw=kw)
        return {"data": {"reply": " 표 후보를 냈습니다 ", "actions": [{"type": "write"}, "쓰레기"]}, "backend": "api", "model": "m", "effort": kw.get("effort"), "ms": 5, "costUsd": 0.01, "error": None}
    r = A.ask(A.payload("x"), "", "", call=fake, effort="low")
    assert r["data"] == {"reply": "표 후보를 냈습니다", "actions": [{"type": "write"}]} and r["response"]["actions"][1] == "쓰레기"   # response 는 받은 그대로
    assert seen["schema"] is A.SCHEMA and seen["what"] == "doc-agent" and seen["kw"]["effort"] == "low" and r["prompt"] == seen["content"] and r["call"]["backend"] == "api"
    bad = A.ask(A.payload("x"), call=lambda *a, **k: {"data": {"reply": "x", "actions": "없음"}, "error": None})
    assert bad["data"] is None and "못 쓰는 답" in bad["call"]["error"]
    off = A.ask(A.payload("x"), call=lambda *a, **k: {"data": None, "error": "off"})
    assert off["data"] is None and off["call"]["error"] == "off"


# ---- 문서에서 읽기 --------------------------------------------------------------------------------------------------------

def test_outline_and_tables_caps(rnd):
    blocks = rnd.blocks()
    full = A.outline_of(blocks, cap=10_000)
    assert all("gap" not in x for x in full) and all(x["text"] for x in full) and len(full) > 400   # 빈 문단은 뺀다
    far = full[-5]["id"]
    out = A.outline_of(blocks, [far], cap=300)
    ids = [x["id"] for x in out if "id" in x]
    assert len(ids) == 300 and far in ids and ids[0] == full[0]["id"]                               # 고른 것 둘레를 먼저, 남는 몫은 문서 앞에서부터
    assert len(ids) + sum(x["gap"] for x in out if "gap" in x) == len(full)                         # 줄인 자리는 gap 으로
    assert [x["id"] for x in full if x["id"] in set(ids)] == ids                                    # 문서 순
    t1 = next(x for x in full if x["id"] == "t1")
    assert t1["text"].startswith("표 49×30 · ") and len(max((x["text"] for x in full if x["id"].startswith("p")), key=len)) <= A.OUTLINE_TEXT
    tabs = A.tables_of(blocks)
    assert len(tabs) == 81 and tabs[-1] == {"more": 40} and tabs[0]["id"] == "t1" and tabs[0]["size"] == "49×30" and "연구개발계획서" in tabs[0]["head"]
    last = [b["id"] for b in blocks if b["type"] == "table"][-1]
    assert A.tables_of(blocks, cap=5, focus_ids=[last])[0]["id"] == last and len(A.tables_of(blocks, cap=5)) == 6
    assert A.outline_of([]) == [] and A.tables_of([]) == []


def test_top_level_and_selection(rnd):
    a, inner = _anchor(rnd), _cell_para(rnd)
    assert A.top_el(rnd, a) is not None and A.top_el(rnd, "t1") is not None and A.top_el(rnd, inner) is None and A.top_el(rnd, "없음") is None and A.top_el(rnd, None) is None
    assert A.top_of(rnd, rnd._ids[inner]) == "t1" and A.top_of(rnd, rnd._ids[a]) == a
    cell = rnd.table_block("t1")["cells"][0]["id"]
    assert A.top_el(rnd, cell) is None and A.top_of(rnd, rnd._ids[cell]) == "t1"
    got = A.selection_of(rnd, {"paras": [a, inner, "p999999", 5], "table": "t1", "range": {"r0": 1, "c0": 1, "r1": 2, "c1": 3}, "cursor": inner})
    d = got["data"]
    assert [p["id"] for p in d["paras"]] == [a, inner] and d["paras"][1]["top"] == "t1" and d["paras"][0]["top"] == a           # 없는 id 는 조용히 뺀다
    assert d["table"]["id"] == "t1" and d["table"]["size"] == "49×30" and d["table"]["range"] == "B2:D3" and len(d["table"]["grid"]) == 49 and "more" not in d["table"]
    wide = A.selection_of(rnd, {"table": "t2417"})["data"]["table"]                                                            # 칸 691개 — 400칸까지(행 단위로 끊고 more)
    assert A.GRID_CELLS <= sum(len(r) for r in wide["grid"]) < 691 and wide["more"].startswith("아래 칸 ") and wide["range"] == ""
    assert d["cursor"] == {"id": inner, "text": A._short(rnd._text(rnd._ids[inner]), 200), "top": "t1"} and got["focus"] == [a, "t1"]
    assert rnd._text(rnd._ids[a]) in got["text"]
    assert A.selection_of(rnd, None) == {"data": {"paras": [], "table": None, "cursor": None}, "focus": [], "text": ""}
    assert A.range_of("b2:d5") == {"r0": 1, "c0": 1, "r1": 4, "c1": 3} and A.range_of("") is None and A.range_of("C3") == {"r0": 2, "c0": 2, "r1": 2, "c1": 2}
    with pytest.raises(ValueError):
        A.range_of("둘째 행")


def test_styles_materials_history_payload():
    metas = [{"id": "aaaaaaaaaaaa", "kind": "table", "name": "예산 총괄표", "bands": {"headerRows": 2, "headerCols": 1, "footRows": 1}, "rows": 6, "cols": 5, "blueprint": {"cells": []}},
             {"id": "bbbbbbbbbbbb", "kind": "text", "name": "개요 글", "items": [{"key": "i1", "name": "□ 줄", "level": 1, "sample": "□ 견본 글입니다", "format": {"sizePt": 12}}]},
             {"id": "cccccccccccc", "kind": "기타"}, "쓰레기"]
    st = A.styles_data(metas, {"table": "doc:t1", "text": None})
    assert st["table"][0]["id"] == "builtin" and st["table"][1] == {"id": "aaaaaaaaaaaa", "name": "예산 총괄표", "bands": {"headerRows": 2, "headerCols": 1, "footRows": 1}, "rows": 6, "cols": 5,
                                                                    "blueprint": True}
    assert st["text"] == [{"id": "bbbbbbbbbbbb", "name": "개요 글", "items": [{"key": "i1", "name": "□ 줄", "level": 1, "sample": "□ 견본 글입니다"}]}] and st["picked"] == {"table": "doc:t1", "text": None}
    assert set(A.styles_index(metas)["table"]) == {"aaaaaaaaaaaa"} and set(A.styles_index(metas)["text"]) == {"bbbbbbbbbbbb"}
    mats = [{"id": "m1", "name": "긴 자료", "text": "가" * 50_000}, {"id": "m2", "name": "짧은 자료", "text": "나" * 100}, {"id": "m3", "name": "긴 자료 2", "text": "다" * 50_000}]
    sent = A.materials_data(mats, 60_000)
    assert [m["id"] for m in sent] == ["m1", "m2", "m3"] and sum(len(m["text"]) for m in sent) == 60_000                       # 합쳐 60,000자
    assert [m["cut"] for m in sent] == [True, False, True] and len(sent[1]["text"]) == 100 and len(sent[0]["text"]) == 29_950    # 짧은 것은 다 싣고 남는 몫을 나눈다
    text = A.materials_text(mats)
    assert len(text) <= 60_000 and text.startswith("[자료: 긴 자료]\n가") and "(뒤는 잘림)" in text and "[자료: 짧은 자료]\n" + "나" * 100 in text
    fm = A.fill_material("책임자는 홍길동", mats)
    assert len(fm) <= TF.MATERIAL_MAX and fm.endswith("[요청 글]\n책임자는 홍길동") and A.fill_material("값 1", []) == "[요청 글]\n값 1"
    turns = [{"request": {"text": f"요청 {k}"}, "reply": f"답 {k}", "proposals": [{"title": "표", "state": "applied"}, {"title": "글", "state": "open"}]} for k in range(8)]
    turns.insert(3, {"request": {"text": "실패"}, "error": "시간 초과", "reply": ""})
    h = A.history_of(turns)
    assert len(h) == 6 and h[0] == {"request": "요청 2", "reply": "답 2", "applied": ["표"]} and h[-1]["request"] == "요청 7"   # 최근 6턴 · 실패한 턴은 뺀다
    p = A.payload("요청", None, [{"id": "p1", "text": "가"}], [], st, sent, h)
    assert list(p) == ["request", "selection", "outline", "tables", "styles", "materials", "history"] and p["selection"] == {"paras": [], "table": None, "cursor": None}


# ---- 행동 → 제안 ----------------------------------------------------------------------------------------------------------

def test_proposals_drop_bad_shapes_with_reasons(rnd):
    a, inner = _anchor(rnd), _cell_para(rnd)
    line = [{"item": "", "text": "인건비는 100", "source": "인건비 100"}]
    styles = A.styles_index([{"id": "bbbbbbbbbbbb", "kind": "text", "name": "개요 글", "items": [{"key": "i1", "name": "□ 줄"}]}])
    acts = [{"type": "write", "after": "p999999", "mode": "extract", "style": "", "lines": line},                    # 없는 자리
            {"type": "write", "after": inner, "mode": "extract", "style": "", "lines": line},                       # 표 칸 안
            {"type": "tableNew", "after": a, "style": "ffffffffffff", "candidates": [{"title": "x", "why": "", "grid": _grid(GOOD)}]},   # 모르는 표 서식
            "쓰레기"]
    got = A.proposals(rnd, acts, _ctx(styles=styles))
    assert got["proposals"] == [] and [d["action"] for d in got["dropped"]] == [0, 1, 2, 3]
    why = [d["why"] for d in got["dropped"]]
    assert "문서에 없습니다" in why[0] and "본문 최상위 블록이 아닙니다" in why[1] and "모르는 표 서식" in why[2] and got["dropped"][2]["type"] == "tableNew"
    acts = [{"type": "write", "after": a, "mode": "extract", "style": "bbbbbbbbbbbb", "lines": [{"item": "i9", "text": "x", "source": ""}]},     # 그 서식에 없는 item
            {"type": "write", "after": a, "mode": "extract", "style": "", "lines": [{"item": "i1", "text": "x", "source": ""}]},                 # 서식 없이 item
            {"type": "write", "after": a, "mode": "extract", "style": "zzzzzzzzzzzz", "lines": line},                                           # 모르는 글 서식
            {"type": "지우기", "after": a},
            {"type": "write", "after": a, "mode": "extract", "style": "", "lines": line}]                                                       # 다섯째 — 한 턴에 4개까지
    got = A.proposals(rnd, acts, _ctx(styles=styles))
    why = [d["why"] for d in got["dropped"]]
    assert got["proposals"] == [] and len(why) == 5 and "없는 항목(item)" in why[0] and "글 서식 없이 item" in why[1] and "모르는 글 서식" in why[2] and "모르는 행동" in why[3] and "4개까지" in why[4]
    long_ = [{"type": "write", "after": a, "mode": "draft", "style": "", "lines": [{"item": "", "text": "가" * 2001, "source": ""}]},
             {"type": "write", "after": a, "mode": "draft", "style": "", "lines": [{"item": "", "text": "줄", "source": ""}] * 61},
             {"type": "write", "after": a, "mode": "draft", "style": "", "lines": [{"item": "", "text": "  ", "source": ""}]},
             {"type": "tableFill", "table": "t1", "range": ""}]                                                                                # 끝점이 채우기 결과를 안 줬다
    why = [d["why"] for d in A.proposals(rnd, long_, _ctx())["dropped"]]
    assert "줄이 너무 깁니다" in why[0] and "줄이 너무 많습니다" in why[1] and why[2] == "쓸 줄이 없습니다" and "표 채우기는 한 턴에" in why[3]


def test_table_new_drops_bad_grids_and_extra_candidates(rnd):
    a = _anchor(rnd)
    over = {"rows": [{"cells": [{"text": "a", "rowSpan": 3, "colSpan": 1}, {"text": "b", "rowSpan": 1, "colSpan": 1}]}], "headerRows": 0, "headerCols": 0, "footRows": 0}
    clash = {"rows": [{"cells": [{"text": "a", "rowSpan": 2, "colSpan": 1}, {"text": "b", "rowSpan": 1, "colSpan": 1}]}, {"cells": [{"text": "c", "rowSpan": 1, "colSpan": 2}, {"text": "d", "rowSpan": 1, "colSpan": 1}]},
                      {"cells": [{"text": "e", "rowSpan": 1, "colSpan": 1}]}], "headerRows": 0, "headerCols": 0, "footRows": 0}
    with pytest.raises(ValueError, match="표 밖"):
        A.grid_strict(over)
    with pytest.raises(ValueError, match="빈 격자"):
        A.grid_strict({"rows": [{"cells": []}]})
    with pytest.raises(ValueError, match="꼴"):
        A.grid_strict({"rows": "x"})
    assert A.grid_strict(clash) == {"cells": 5, "rows": 3, "cols": 4, "holes": 5}   # 겹치지는 않는다(위에서 내려온 자리를 건너뛴다) — 빈 자리는 정규화가 메운다
    with pytest.raises(ValueError, match="겹칩니다"):
        A.grid_strict({"rows": [{"cells": [{"text": "a", "rowSpan": 1, "colSpan": 1}, {"text": "b", "rowSpan": 2, "colSpan": 1}]},
                                {"cells": [{"text": "c", "rowSpan": 1, "colSpan": 3}]}]})
    # 검토 13: 한도를 넘는 rowSpan·colSpan 은 그 폭만큼 도는 반복문 **전에** 거절한다(colSpan 10억 = 예전에는 10억 번 돌았다)
    for rs, cs in ((1, table_make.COLS_MAX + 1), (1, 10 ** 9), (table_make.ROWS_MAX + 1, 1), (10 ** 9, 10 ** 9)):
        with pytest.raises(ValueError, match="한도"):
            A.grid_strict({"rows": [{"cells": [{"text": "a", "rowSpan": rs, "colSpan": cs}]}]})
    with pytest.raises(ValueError, match="한도"):
        A.grid_strict({"rows": [{"cells": [{"text": "a", "rowSpan": 1, "colSpan": 1}] * (table_make.COLS_MAX + 1)}]})          # 칸이 한도보다 많은 행
    with pytest.raises(ValueError, match="한도"):
        A.grid_strict({"rows": [{"cells": [{"text": "a", "rowSpan": 1, "colSpan": 1}]}] * (table_make.ROWS_MAX + 1)})          # 행이 한도보다 많은 격자
    assert A.grid_strict({"rows": [{"cells": [{"text": "a", "rowSpan": 1, "colSpan": table_make.COLS_MAX}]}]})["cols"] == table_make.COLS_MAX
    cands = [{"title": "밖", "why": "", "grid": over}, {"title": "빈", "why": "", "grid": {"rows": []}}, {"title": "좋음", "why": "항목이 연차마다 되풀이", "grid": _grid(GOOD)},
             {"title": "넷째", "why": "", "grid": _grid(GOOD)}]
    got = A.proposals(rnd, [{"type": "tableNew", "after": a, "style": "builtin", "candidates": cands}], _ctx())
    assert [(d["candidate"], d["why"].split(":")[0].split(" — ")[0]) for d in got["dropped"]] == [(0, "못 쓰는 격자"), (1, "못 쓰는 격자"), (3, "표 구조 후보는 3개까지")]
    (p,) = got["proposals"]
    assert p["title"] == "좋음" and p["choiceGroup"] == "t1.g1" and p["preselect"] is True and (p["view"]["style"], p["view"]["styleName"]) == ("builtin", "기본 표")
    none = A.proposals(rnd, [{"type": "tableNew", "after": a, "style": "", "candidates": [{"title": "밖", "why": "", "grid": over}]}, {"type": "tableNew", "after": a, "style": "", "candidates": []}], _ctx())
    assert none["proposals"] == [] and [d["why"] for d in none["dropped"] if "candidate" not in d] == ["쓸 수 있는 표 구조 후보가 없습니다", "표 구조 후보가 없습니다"]


def test_write_extract_draft_and_warnings(rnd):
    a = _anchor(rnd)
    ext = {"type": "write", "after": a, "mode": "extract", "style": "", "lines": [{"item": "", "text": "인건비 100 120\n재료비 50 60", "source": "인건비  100 120\n재료비 50 60"}]}   # 자료의 글 그대로(공백만 다름)
    (p,) = A.proposals(rnd, [ext], _ctx())["proposals"]
    assert p["id"] == "p1" and p["type"] == "write" and p["state"] == "open" and p["baseRev"] == 7 and p["choiceGroup"] is None and p["preselect"] is True and p["warn"] == []
    assert [c["status"] for c in p["checks"]] == ["pass", "pass"] and all("사실 검증 아님" in c["text"] and "사람이 읽고" in c["text"] for c in p["checks"])   # 근거·수 검사는 사실 검증이 아니라고 적는다(대응·뜻은 사람이)
    assert p["op"] == {"after": a, "style": None, "styleRev": None, "lines": [{"text": "인건비 100 120", "item": None}, {"text": "재료비 50 60", "item": None}]}   # 줄 바꿈 = 문단 둘
    assert p["view"]["mode"] == "extract" and [ln["quoted"] for ln in p["view"]["lines"]] == [True, True] and p["view"]["styleRev"] is None
    assert p["target"] == A.target_of(rnd, [a], insert=True) and p["target"]["next"] == A.next_top(rnd, a) and p["target"]["hash"] != A.target_hash(rnd, a)   # 넣는 자리의 경계까지 지문에(검토 4)
    assert "op" not in A.card(p) and A.card(p)["view"] == p["view"]
    draft = {**ext, "mode": "draft"}
    (d,) = A.proposals(rnd, [draft], _ctx())["proposals"]
    assert d["preselect"] is False and d["warn"] == ["에이전트가 쓴 글 — 읽고 반영하세요"] and d["checks"][0]["status"] == "unknown" and "(지은 글)" in d["title"]   # draft 는 처음부터 고르지 않는다
    (u,) = A.proposals(rnd, [{**ext, "mode": "요약"}], _ctx())["proposals"]
    assert u["view"]["mode"] == "draft" and u["preselect"] is False                                                        # 모르는 mode 는 지은 글로 본다
    bad = {"type": "write", "after": a, "mode": "extract", "style": "", "lines": [{"item": "", "text": "인건비 100", "source": "인건비 100"}, {"item": "", "text": "장비비 999", "source": "장비비 999"}]}
    (w,) = A.proposals(rnd, [bad], _ctx())["proposals"]
    assert w["preselect"] is False and w["warn"] == ["근거 구절을 자료에서 못 찾은 줄 1개", "자료·선택·요청 글에 없는 수: 999"]            # 자료에 없는 수 · 없는 근거 구절
    assert [ln["warn"] for ln in w["view"]["lines"]] == [[], ["근거 구절을 자료에서 못 찾음"]] and [c["status"] for c in w["checks"]] == ["warn", "warn"]
    # 반례(spec ① astra ⓖ → 검토 1): 인건비·재료비의 값을 뒤바꾼 글은 수·근거 구절 검사를 지나지만 자료의 글 그대로가 아니다 — 처음부터 고르지 않는다(읽고 반영)
    swap = {"type": "write", "after": a, "mode": "extract", "style": "", "lines": [{"item": "", "text": "인건비는 50, 재료비는 100", "source": "재료비 50"}]}
    (s,) = A.proposals(rnd, [swap], _ctx())["proposals"]
    assert s["preselect"] is False and s["warn"] == ["자료의 글을 바꿔 옮긴 줄 1개 — 읽고 반영하세요"] and s["view"]["lines"][0]["warn"] == [A.REWORDED] and s["view"]["lines"][0]["quoted"] is True
    assert [c["status"] for c in s["checks"]] == ["warn", "pass"] and all("사실 검증 아님" in c["text"] for c in s["checks"])
    # 글 서식을 고른 줄: item 이름이 보기에, key 가 실행할 것에
    styles = A.styles_index([{"id": "bbbbbbbbbbbb", "kind": "text", "name": "개요 글", "items": [{"key": "i1", "name": "□ 줄"}, {"key": "i2", "name": "o 줄"}]}])
    st = {"type": "write", "after": a, "mode": "extract", "style": "", "lines": [{"item": "i2", "text": "인건비 100", "source": "인건비 100"}]}
    (q,) = A.proposals(rnd, [st], _ctx(styles=styles, picked={"text": "bbbbbbbbbbbb"}))["proposals"]                        # 행동이 비운 style = 사람이 고른 서식
    assert q["op"]["style"] == "bbbbbbbbbbbb" and q["op"]["lines"] == [{"text": "인건비 100", "item": "i2"}] and (q["view"]["style"], q["view"]["styleName"]) == ("bbbbbbbbbbbb", "개요 글")
    assert q["view"]["lines"][0]["itemName"] == "o 줄"


def test_table_new_candidates_group_excel_and_values(rnd):
    a = _anchor(rnd)
    two = [{"title": "항목 × 연차", "why": "항목이 연차마다 되풀이", "grid": _grid(GOOD)},
           {"title": "연차 × 항목", "why": "연차를 세로로", "grid": _grid([["구분", "인건비", "재료비", "합계"], ["1차", "100", "50", "150"], ["2차", "120", "60", "180"]], foot=0)}]
    got = A.proposals(rnd, [{"type": "tableNew", "after": a, "style": "doc:t1", "candidates": two}], _ctx())
    p1, p2 = got["proposals"]
    assert got["dropped"] == [] and p1["choiceGroup"] == p2["choiceGroup"] == "t1.g1" and (p1["preselect"], p2["preselect"]) == (True, False)   # 묶음에서 처음부터 고르는 것은 하나
    assert p1["warn"] == p2["warn"] == [] and p1["excel"]["status"] == "pass" and p1["excel"]["ok"] == 2 and p1["excel"]["note"] == "수식 2 — 맞음 2"
    assert [c["what"] for c in p1["checks"]] == ["numbers", "excel", "values"] and p1["checks"][2]["status"] == "pass"
    assert p1["view"]["grid"] == p1["op"]["grid"] == table_make.to_rows(table_make.normalize(_grid(GOOD))) and p1["view"]["gridChanges"] == []   # 사람이 보는 격자 = 반영할 격자
    assert p1["view"]["bands"] == {"headerRows": 1, "headerCols": 1, "footRows": 1} and (p1["view"]["rows"], p1["view"]["cols"]) == (4, 3) and p1["view"]["why"] == "항목이 연차마다 되풀이"
    assert p1["op"]["style"] == "doc:t1" and (p1["view"]["style"], p1["view"]["styleName"]) == ("doc:t1", "이 문서의 표 t1") and p1["target"]["block"] == a and p1["summary"] == "항목이 연차마다 되풀이"
    # 합계가 틀린 후보: 불일치 → 경고 · 처음부터 안 고름. 수 모둠이 다른 후보끼리는 모두 경고
    got = A.proposals(rnd, [{"type": "tableNew", "after": a, "style": "", "candidates": [{"title": "틀림", "why": "", "grid": _grid(WRONG)}, {"title": "맞음", "why": "", "grid": _grid(GOOD)}]}], _ctx())
    bad, ok = got["proposals"]
    assert bad["excel"]["status"] == "warn" and bad["excel"]["mismatch"] == 1 and bad["preselect"] is False and any(w.startswith("엑셀 검증 — ") for w in bad["warn"])
    assert bad["excel"]["examples"][0]["status"] == "mismatch" and bad["excel"]["examples"][0]["ref"] == "C4" and bad["excel"]["examples"][0]["expected"] == 180 and bad["excel"]["examples"][0]["actual"] == 181
    assert "자료·선택·요청 글에 없는 수: 181" in bad["warn"] and ok["excel"]["status"] == "pass" and ok["preselect"] is False and "이 후보에 없는 수: 181" in ok["warn"][0]
    (alone,) = A.proposals(rnd, [{"type": "tableNew", "after": a, "style": "", "candidates": [{"title": "틀림", "why": "", "grid": _grid(WRONG)}]}], _ctx())["proposals"]
    assert alone["preselect"] is False and alone["choiceGroup"] == "t1.g1" and [c["what"] for c in alone["checks"]] == ["numbers", "excel"]
    # 수식이 없는 표: 통과가 아니라 unknown — 경고는 아니므로 고를 수는 있다
    kv = _grid([["구분", "내용"], ["기간", "2026.01 ~ 2026.12"], ["책임자", "홍길동"]], foot=0)
    (k,) = A.proposals(rnd, [{"type": "tableNew", "after": a, "style": "", "candidates": [{"title": "구분 | 내용", "why": "", "grid": kv}]}], _ctx("기간 2026.01 ~ 2026.12 책임자 홍길동"))["proposals"]
    assert k["excel"]["status"] == "unknown" and k["excel"]["note"] == "검산할 수식 없음" and k["excel"]["formulas"] == 0 and k["warn"] == [] and k["preselect"] is True
    # 정규화가 바꾼 것은 gridChanges 에, 보이는 격자는 정규화한 것
    ragged = {"rows": [{"cells": [{"text": "구분", "rowSpan": 1, "colSpan": 1}, {"text": "1차", "rowSpan": 1, "colSpan": 1}]}, {"cells": [{"text": "인건비", "rowSpan": 1, "colSpan": 1}]}],
              "headerRows": 5, "headerCols": 0, "footRows": 0}
    (r,) = A.proposals(rnd, [{"type": "tableNew", "after": a, "style": "", "candidates": [{"title": "", "why": "", "grid": ragged}]}], _ctx())["proposals"]
    assert r["view"]["gridChanges"] == ["빈 자리 1칸을 빈 칸으로 메움", "머리행 수 5 → 2(표 크기에 맞춤)"] and r["title"] == "표 2×2" and len(r["view"]["grid"]["rows"][1]["cells"]) == 2


def test_excel_check_new_table_and_fill_copy(rnd):
    assert A.excel_check(_grid(GOOD))["status"] == "pass" and A.excel_check(table_make.normalize(_grid(GOOD)))["ok"] == 2
    bad = A.excel_check(_grid(WRONG))
    assert (bad["status"], bad["formulas"], bad["ok"], bad["mismatch"]) == ("warn", 2, 1, 1) and bad["note"] == "수식 2 — 맞음 1 · 불일치 1" and len(bad["examples"]) == 2
    blank = A.excel_check(_grid([["구분", "1차", "2차"], ["인건비", "100", "120"], ["재료비", "50", "60"], ["합계", "", ""]]))   # 합계를 비워 둔 표 — 맞는지 확인된 수식이 없다
    assert blank["status"] == "unknown" and blank["note"] == "추정한 수식 2개를 검산하지 못함(미기입 2)" and blank["formulas"] == 2 and blank["missing"] == 2   # 수식은 찾았으나 검산하지 못했다(검토 17)
    assert A.excel_check({"rows": "x"})["status"] == "unknown" and "엑셀 검증을 하지 못했습니다" in A.excel_check({"rows": "x"})["note"]
    assert A.excel_summary(None)["status"] == "unknown" and A.excel_summary({"counts": {"formulas": 0}, "formulas": []})["note"] == "검산할 수식 없음"
    # 검토 17: 일부만 맞음을 확인한 표는 통과가 아니다(ok 1 · incomplete 1 → 예전에는 pass)
    part = A.excel_summary({"counts": {"formulas": 2, "ok": 1, "incomplete": 1}, "formulas": [{"ref": "C4", "status": "ok"}, {"ref": "D4", "status": "incomplete"}]})
    assert part["status"] == "unknown" and part["note"] == "추정한 수식 2개 가운데 1개만 맞음을 확인 — 1개는 검산하지 못함(피연산 일부 빈 칸 1)"
    assert A.excel_summary({"counts": {"formulas": 2, "ok": 2}, "formulas": []})["status"] == "pass"
    mixed = A.excel_summary({"counts": {"formulas": 3, "ok": 1, "mismatch": 1, "blank": 1}, "formulas": []})
    assert mixed["status"] == "warn" and mixed["note"] == "수식 3 — 맞음 1 · 불일치 1 · 피연산 빈 칸 1"
    # 표 채우기: 세션 문서의 표를 빈 바탕에 복사해 값을 자리(행·열)로 넣어 판정 — 세션 문서는 안 바뀐다
    j = table_excel.judge(rnd, "t1", store=copy.deepcopy(EMPTY))
    f0 = next(f for f in j["formulas"] if f.get("kind") == "sum" and f.get("operands"))
    before, dirty = A.target_hash(rnd, "t1"), set(rnd._dirty)
    fills = [{"cell": o, "text": "10"} for o in f0["operands"]]
    wrong = A.excel_check(doc=rnd, table="t1", fills=fills + [{"cell": f0["cell"], "text": str(10 * len(f0["operands"]) + 1)}], store=copy.deepcopy(EMPTY))
    assert wrong["status"] == "warn" and wrong["mismatch"] == 1 and wrong["formulas"] == j["counts"]["formulas"]
    ex = wrong["examples"][0]
    assert (ex["ref"], ex["status"], ex["expected"], ex["actual"]) == (f0["ref"], "mismatch", 10 * len(f0["operands"]), 10 * len(f0["operands"]) + 1)
    right = A.excel_check(doc=rnd, table="t1", fills=fills + [{"cell": f0["cell"], "text": str(10 * len(f0["operands"]))}], store=copy.deepcopy(EMPTY))
    n = j["counts"]["formulas"]
    assert n > 1 and right["status"] == "unknown" and right["ok"] == 1 and right["mismatch"] == 0 and right["note"].startswith(f"추정한 수식 {n}개 가운데 1개만 맞음을 확인 — {n - 1}개는 검산하지 못함(")   # 하나만 맞음 = 통과 아님(검토 17)
    none = A.excel_check(doc=rnd, table="t1", fills=[], store=copy.deepcopy(EMPTY))
    assert none["status"] == "unknown" and none["note"].startswith(f"추정한 수식 {j['counts']['formulas']}개를 검산하지 못함(") and none["blank"] == j["counts"]["formulas"]   # 빈 칸뿐 — 통과가 아니다
    assert A.target_hash(rnd, "t1") == before and set(rnd._dirty) == dirty
    assert A.excel_check(doc=rnd, table="p1")["status"] == "unknown"


def test_fill_proposal_is_the_pipeline_result(small):
    tid = "t8"
    an = TF.analyze(small, tid, store=copy.deepcopy(EMPTY))
    by = {t["ref"]: t for t in an["targets"]}
    assert sorted(by) == ["B4", "B6", "B8"]
    material = A.fill_material("표를 채워 줘", [{"id": "m1", "name": "과제", "text": "과제명: 차세대 전력변환 모듈 개발\n필요성: 국산화가 필요하다"}])
    data = TF.payload(an, None, material, "", None)
    answer = {"fills": [{"cell": "B4", "text": "차세대 전력변환 모듈 개발", "source": "과제명: 차세대 전력변환 모듈 개발", "where": "material", "reason": "과제명"},
                        {"cell": "B6", "text": "지어낸 필요성", "source": "없는 구절", "where": "material", "reason": ""}, {"cell": "A1", "text": "머리", "source": "", "where": "", "reason": ""}], "note": "두 칸을 채움"}
    out = TF.apply(answer, an, TF.haystack(data), "")
    fill = {"table": tid, "an": an, "out": out, "answer": "두 칸을 채움", "heads": None, "rev": 4, "hash": A.target_hash(small, tid)}
    got = A.proposals(small, [{"type": "tableFill", "table": tid, "range": ""}], _ctx(fills={0: fill}, store=copy.deepcopy(EMPTY)))
    (p,) = got["proposals"]
    want = [out["fills"][0], {**out["fills"][1], "warn": ["근거 구절을 자료에서 못 찾음", A.UNSUPPORTED]}]   # 기존 길의 결과 그대로 + 에이전트 쪽 값 검사(넣을 값이 제 근거 구절에 없는 칸 — 검토 1)
    assert p["view"]["fills"] == want and p["view"]["rejected"] == out["rejected"] and p["view"]["counts"] == {**an["counts"], **out["counts"]}
    assert out["fills"][1]["warn"] == ["근거 구절을 자료에서 못 찾음"]                                                                                    # 기존 길의 결과(사전)는 건드리지 않는다
    assert p["view"]["picked"] == [by["B4"]["cell"]] and p["preselect"] is True and p["warn"] == [] and p["baseRev"] == 7                                # 경고 있는 칸은 처음부터 안 고른다 · baseRev = 턴을 시작한 때의 차례(검토 3)
    assert p["op"] == {"table": tid, "fills": [{"cell": by["B4"]["cell"], "text": "차세대 전력변환 모듈 개발", "was": ""}, {"cell": by["B6"]["cell"], "text": "지어낸 필요성", "was": ""}]}
    assert p["excel"]["status"] == "unknown" and p["excel"]["note"] == "검산할 수식 없음" and p["checks"][0]["status"] == "warn" and p["title"] == "표 채우기 — 2칸" and p["summary"] == "두 칸을 채움"
    assert p["target"] == {"block": tid, "blocks": [tid], "hash": fill["hash"]}
    warned = TF.apply({"fills": [answer["fills"][1]], "note": ""}, an, TF.haystack(data), "")
    (w,) = A.proposals(small, [{"type": "tableFill", "table": tid, "range": ""}], _ctx(fills={0: {**fill, "out": warned}}, store=copy.deepcopy(EMPTY)))["proposals"]
    assert w["preselect"] is False and w["view"]["picked"] == [] and "경고 없는 칸이 없습니다" in w["warn"][0]
    drops = [A.proposals(small, [{"type": "tableFill", "table": tid, "range": ""}], _ctx(fills={0: f}, store=copy.deepcopy(EMPTY)))["dropped"][0]["why"] for f in (
        {"table": tid, "error": "그 표에 채울 칸이 없습니다"}, {**fill, "out": TF.apply({"fills": [], "note": ""}, an, "", "")}, {**fill, "hash": "딴 지문"})]
    assert drops[0] == "그 표에 채울 칸이 없습니다" and drops[1].startswith("자료에서 그 표에 채울 값을 찾지 못했습니다") and "그 표가 바뀌었습니다" in drops[2]


def test_restyle_validation(rnd):
    a = _anchor(rnd)
    b = _anchor(rnd, 6)
    other = [x["id"] for x in rnd.blocks() if x["type"] == "table"][2]
    styles = A.styles_index([{"id": "aaaaaaaaaaaa", "kind": "table", "name": "예산표"}, {"id": "bbbbbbbbbbbb", "kind": "text", "name": "개요 글", "items": [{"key": "i1", "name": "□ 줄"}]},
                             {"id": "dddddddddddd", "kind": "text", "name": "두 줄", "items": [{"key": "i1", "name": "□"}, {"key": "i2", "name": "o"}]}])
    acts = [{"type": "restyle", "table": "t1", "style": f"doc:{other}", "paras": [], "item": ""}, {"type": "restyle", "table": "", "style": "bbbbbbbbbbbb", "paras": [a, b], "item": ""},
            {"type": "restyle", "table": "t1", "style": "aaaaaaaaaaaa", "paras": [], "item": ""}]
    t, p, s = A.proposals(rnd, acts, _ctx(styles=styles))["proposals"]
    assert t["op"] == {"table": "t1", "style": f"doc:{other}", "styleRev": None} and t["view"]["rows"] == 49 and t["preselect"] is True
    assert t["target"] == A.target_of(rnd, ["t1"], style=other) and t["target"]["style"] == other and t["target"]["hash"] != A.target_hash(rnd, "t1")   # 서식으로 쓰는 이 문서의 표도 지문에(검토 4)
    assert p["op"] == {"paras": [a, b], "style": "bbbbbbbbbbbb", "styleRev": None, "item": "i1"} and (p["view"]["item"], p["view"]["itemName"], p["view"]["paras"]) == ("i1", "□ 줄", [a, b]) and p["target"]["blocks"] == [a, b]   # item 이 하나뿐이면 그것
    assert (s["view"]["style"], s["view"]["styleName"]) == ("aaaaaaaaaaaa", "예산표") and p["target"]["hash"] != A.target_of(rnd, [a])["hash"] and s["target"] == A.target_of(rnd, ["t1"])
    bad = [{"type": "restyle", "table": "t1", "style": "doc:t1", "paras": [], "item": ""}, {"type": "restyle", "table": "t1", "style": "", "paras": [], "item": ""},
           {"type": "restyle", "table": "", "style": "dddddddddddd", "paras": [a], "item": ""}, {"type": "restyle", "table": "", "style": "aaaaaaaaaaaa", "paras": [a], "item": ""}]
    why = [d["why"] for d in A.proposals(rnd, bad, _ctx(styles=styles))["dropped"]]
    assert "같습니다" in why[0] and "표 서식을 고르지 않았습니다" in why[1] and "어느 항목(item)" in why[2] and "모르는 글 서식" in why[3]
    why = [d["why"] for d in A.proposals(rnd, [{"type": "restyle", "table": "", "style": "bbbbbbbbbbbb", "paras": ["p999999"], "item": "i1"}, {"type": "restyle", "table": "", "style": "", "paras": [], "item": ""},
                                               {"type": "restyle", "table": "t999999", "style": "builtin", "paras": [], "item": ""}], _ctx(styles=styles))["dropped"]]
    assert "문단이 문서에 없습니다" in why[0] and "표(table)나 문단(paras)이 없습니다" in why[1] and "표가 문서에 없습니다" in why[2]


# ---- 검토(astra 2026-11-13 — artifacts/general_edit_astra_2026-11-13/review_answer.md)의 반례 ----------------------------------------

def test_num_tokens_keep_sign_decimals_percent_and_leading_zeros():
    assert A.num_tokens("A -100천원, B 200천원") == ["-100", "200"]
    assert A.num_tokens("△1,500 ▲ 20 −3.5% 12.5 % 0.50 007 3명") == ["-1500", "-20", "-3.5%", "12.5%", "0.50", "007", "3"]   # 음수 표시 · 쉼표는 뗌 · 소수·%·앞자리 0 은 글 그대로 · 한 자리도
    assert A.num_tokens("2026-11-13 · A-100 · 100-200 · 1,2,3 · - 5 · (-7)") == ["2026", "11", "13", "100", "100", "200", "1", "2", "3", "5", "-7"]   # 이음표·글머리 「-」 는 부호가 아니다
    assert A.num_tokens("") == [] and A.num_tokens(None) == []


def test_review1_reworded_extract_and_signed_numbers_are_not_preselected(rnd):
    a = _anchor(rnd)
    src = "A 기관은 100천원을 지급하지 않았다."

    def one(text, source=src, material=src):
        act = {"type": "write", "after": a, "mode": "extract", "style": "", "lines": [{"item": "", "text": text, "source": source}]}
        (p,) = A.proposals(rnd, [act], _ctx(material))["proposals"]
        return p
    flip = one("A 기관은 100천원을 지급했다.")                                    # 근거 구절은 자료에 있고 수도 같다 — 뜻이 뒤집혔다
    assert flip["preselect"] is False and flip["view"]["lines"][0]["warn"] == [A.REWORDED] and flip["view"]["lines"][0]["quoted"] is True and flip["checks"][0]["status"] == "warn"
    same = one("o A 기관은 100천원을 지급하지 않았다.")                            # 글머리 레터만 붙인 것은 그대로 옮긴 것
    assert same["preselect"] is True and same["warn"] == [] and same["view"]["lines"][0]["warn"] == []
    assert one("1. A 기관은 100천원을 지급하지 않았다.")["preselect"] is True       # 번호 레터도(그 번호는 수 검사에서 뺀다)
    assert one("A 기관은 100천원을 지급하지 않았다(단위: 천원).")["preselect"] is False   # 단위를 덧붙임 = 읽고 반영
    long_ = "가나다라마바사아자차카타파하 " * 20                                   # 근거 구절이 길어도(200자 넘음) 글자 그대로면 통과한다 — 보이는 근거 구절만 줄인다
    kept = one(long_.strip(), long_, long_)
    assert kept["preselect"] is True and len(kept["view"]["lines"][0]["source"]) <= 200
    people = one("참여 인력은 9명", "참여 인력은 3명", "참여 인력은 3명")          # 한 자리 수도 견준다
    assert people["preselect"] is False and "자료·선택·요청 글에 없는 수: 9" in people["warn"]
    # 새 표: 자료의 -100 을 100 으로 — 부호를 떼면 다른 수다
    grid = _grid([["기관", "금액(만원)"], ["A", "100"], ["B", "200"]], foot=0)
    (t,) = A.proposals(rnd, [{"type": "tableNew", "after": a, "style": "builtin", "candidates": [{"title": "기관 | 금액", "why": "", "grid": grid}]}], _ctx("A -100천원, B 200천원"))["proposals"]
    assert t["preselect"] is False and "자료·선택·요청 글에 없는 수: 100" in t["warn"] and [c["status"] for c in t["checks"] if c["what"] == "numbers"] == ["warn"]
    signed = _grid([["기관", "금액"], ["A", "△100"], ["B", "200"]], foot=0)        # 음수 표시만 다른 것(△ ↔ -)은 같은 수
    (u,) = A.proposals(rnd, [{"type": "tableNew", "after": a, "style": "builtin", "candidates": [{"title": "기관 | 금액", "why": "", "grid": signed}]}], _ctx("A -100천원, B 200천원"))["proposals"]
    assert u["preselect"] is True and u["warn"] == []


def _fill_ctx(doc, tid, answer_fills, material, rng=None, **more):
    """표 채우기의 기존 길(`analyze → payload → apply`)을 그대로 돌려 `proposals` 의 ctx 로 — (ctx, an, out)."""
    an = TF.analyze(doc, tid, rng, store=copy.deepcopy(EMPTY))
    data = TF.payload(an, None, A.fill_material("표를 채워 줘", [{"id": "m1", "name": "자료", "text": material}]), "", None)
    out = TF.apply({"fills": answer_fills, "note": ""}, an, TF.haystack(data), "")
    fill = {"table": tid, "an": an, "out": out, "answer": "", "heads": None, "rev": 7, "hash": A.target_hash(doc, tid)}
    return _ctx(material, fills={0: fill}, store=copy.deepcopy(EMPTY), **more), an, out


def test_review1_fill_value_must_be_in_its_own_source(small):
    material = "A 100천원\nB -100천원\n과제명: 차세대 전력변환 모듈 개발"
    fills = [{"cell": "B4", "text": "999999", "source": "A 100천원", "where": "material", "reason": ""},           # 근거 구절은 자료에 있지만 그 값은 거기 없다
             {"cell": "B6", "text": "100", "source": "B -100천원", "where": "material", "reason": ""},             # 부호를 떼었다
             {"cell": "B8", "text": "차세대 전력변환 모듈 개발", "source": "과제명: 차세대 전력변환 모듈 개발", "where": "material", "reason": ""}]
    ctx, an, out = _fill_ctx(small, "t8", fills, material)
    assert [f["warn"] for f in out["fills"]] == [[], [], []]                                                        # 기존 길은 셋 다 경고 없이 지나간다(근거 구절이 자료에 있는지만 본다)
    (p,) = A.proposals(small, [{"type": "tableFill", "table": "t8", "range": ""}], ctx)["proposals"]
    by = {f["ref"]: f for f in p["view"]["fills"]}
    assert by["B4"]["warn"] == [A.UNSUPPORTED] and by["B6"]["warn"] == [A.UNSUPPORTED] and by["B8"]["warn"] == []
    assert p["view"]["picked"] == [by["B8"]["cell"]] and (p["view"]["counts"]["clean"], p["view"]["counts"]["warn"]) == (1, 2) and [f["warn"] for f in out["fills"]] == [[], [], []]
    assert p["checks"][0]["status"] == "warn" and "사실 검증 아님" in p["checks"][0]["text"] and "사람이 읽고" in p["checks"][0]["text"]
    ctx, an, out = _fill_ctx(small, "t8", fills[:2], material)
    (q,) = A.proposals(small, [{"type": "tableFill", "table": "t8", "range": ""}], ctx)["proposals"]
    assert q["preselect"] is False and q["view"]["picked"] == [] and "경고 없는 칸이 없습니다" in q["warn"][0]

    def ok(**f):
        return A.fill_supported({"form": "text", "text": "", "source": "", **f})
    assert ok(form="check", text="[ √ ] 신청용 [ ] 협약용", source="")                                             # 체크 칸은 보지 않는다(표시만 바뀐다)
    assert ok(form="date", text="2026년 3월 5일", source="협약일 2026.03.05") and not ok(form="date", text="2026년 4월 5일", source="협약일 2026.03.05")   # 날짜는 숫자 묶음마다
    assert ok(form="num", text="1500", source="인건비 1,500천원") and ok(text="-100천원", source="B -100천원") and not ok(text="100천원", source="B -100천원")
    assert not ok(form="num", text="100만원", source="A 100천원") and not ok(form="num", text="12.5", source="비율 12.5%")   # 단위·% 를 바꿈
    assert ok(text="-", source="해당 없는 칸은 - 로 둔다") and not ok(text="국산화가 시급하다", source="필요성: 국산화가 필요하다") and not ok(text="값", source="")


def test_review2_actions_are_bound_to_sent_ids_selection_and_picked_style(rnd, small):
    blocks = rnd.blocks()
    a, b, inner = _anchor(rnd), _anchor(rnd, 6), _cell_para(rnd)
    far = [x["id"] for x in A.outline_of(blocks, cap=10_000)][-5]
    sel = A.selection_of(rnd, {"paras": [a, inner], "table": "t1", "cursor": inner})
    ids = A.allowed_ids(A.outline_of(blocks, sel["focus"]), A.tables_of(blocks, focus_ids=sel["focus"]), sel["data"])
    late = [x["id"] for x in blocks if x["type"] == "table"][-1]                                                             # 표 120개 가운데 80개만 보낸다 — 마지막 표는 안 보낸 것
    assert {a, b, inner, "t1"} <= ids and not {far, late, "p999999"} & ids and all(isinstance(i, str) for i in ids)          # 보낸 것만: outline · tables · 고른 문단·표 · 커서(와 그 top)
    line = [{"item": "", "text": "인건비 100 120", "source": "인건비 100 120"}]
    styles = A.styles_index([{"id": "aaaaaaaaaaaa", "kind": "table", "name": "예산표", "revision": "r4"}, {"id": "cccccccccccc", "kind": "table", "name": "다른 표", "revision": "r1"},
                             {"id": "bbbbbbbbbbbb", "kind": "text", "name": "개요 글", "revision": "r3", "items": [{"key": "i1", "name": "□ 줄"}]},
                             {"id": "dddddddddddd", "kind": "text", "name": "다른 글", "revision": "r1", "items": [{"key": "i1", "name": "□"}]}])

    def w(after, style=""):
        return {"type": "write", "after": after, "mode": "extract", "style": style, "lines": line}
    got = A.proposals(rnd, [w(a), w(far), {"type": "restyle", "table": late, "style": "builtin", "paras": [], "item": ""},
                            {"type": "restyle", "table": "", "style": "bbbbbbbbbbbb", "paras": [a, far], "item": ""}], _ctx(styles=styles, allowed=ids))
    assert [p["type"] for p in got["proposals"]] == ["write"] and [d["action"] for d in got["dropped"]] == [1, 2, 3] and all(A.NOT_SENT in d["why"] for d in got["dropped"])
    other = [x["id"] for x in blocks if x["type"] == "table"][2]
    cand = [{"title": "x", "why": "", "grid": _grid(GOOD)}]
    got = A.proposals(rnd, [{"type": "tableNew", "after": a, "style": f"doc:{other}", "candidates": cand}, {"type": "tableNew", "after": a, "style": "", "candidates": cand}],
                      _ctx(styles=styles, allowed={a, "t1"}, picked={"table": f"doc:{other}"}))
    assert [d["action"] for d in got["dropped"]] == [] and len(got["proposals"]) == 2                                   # 사람이 고른 「이 문서의 표」 는 보낸 목록에 없어도 된다
    got = A.proposals(rnd, [{"type": "tableNew", "after": a, "style": f"doc:{other}", "candidates": cand}], _ctx(styles=styles, allowed={a, "t1"}))
    assert got["proposals"] == [] and A.NOT_SENT in got["dropped"][0]["why"]                                             # 지어낸(보내지 않은) 표를 서식으로
    # 서식 이름과 revision 은 제안에 박아 둔다(반영 때 견준다 — 검토 4)
    (p,) = A.proposals(rnd, [w(a, "bbbbbbbbbbbb")], _ctx(styles=styles, allowed=ids))["proposals"]
    assert (p["op"]["style"], p["op"]["styleRev"], p["view"]["styleRev"]) == ("bbbbbbbbbbbb", "r3", "r3") and p["preselect"] is True
    (t,) = A.proposals(rnd, [{"type": "tableNew", "after": a, "style": "aaaaaaaaaaaa", "candidates": cand}], _ctx(styles=styles))["proposals"]
    assert (t["op"]["styleRev"], t["view"]["styleRev"]) == ("r4", "r4") and t["preselect"] is True
    # 사람이 고른 서식과 다른 서식을 적은 행동: 제안은 남기되 경고 · 처음부터 안 고름
    (p,) = A.proposals(rnd, [w(a, "dddddddddddd")], _ctx(styles=styles, picked={"text": "bbbbbbbbbbbb"}))["proposals"]
    assert p["preselect"] is False and p["op"]["style"] == "dddddddddddd" and "사람이 고른 글 서식" in p["warn"][0]
    (t,) = A.proposals(rnd, [{"type": "tableNew", "after": a, "style": "cccccccccccc", "candidates": cand}], _ctx(styles=styles, picked={"table": "aaaaaaaaaaaa"}))["proposals"]
    assert t["preselect"] is False and "사람이 고른 표 서식" in t["warn"][0]
    (r,) = A.proposals(rnd, [{"type": "restyle", "table": "t1", "style": "cccccccccccc", "paras": [], "item": ""}], _ctx(styles=styles, picked={"table": "aaaaaaaaaaaa"}))["proposals"]
    assert r["preselect"] is False and r["op"]["styleRev"] == "r1" and "사람이 고른 표 서식" in r["warn"][0]
    # 서식 입히기의 대상은 사람이 고른 것 안에서(검토 1 의 넷째 반례: 「고른 문단만 바꿔 줘」 → 다른 표에 기본 표 서식)
    act = {"type": "restyle", "table": "t1", "style": "builtin", "paras": [], "item": ""}
    (p,) = A.proposals(rnd, [act], _ctx(styles=styles, selection={"paras": [a], "table": None, "range": None}))["proposals"]
    assert p["preselect"] is False and "사람이 고른" in p["warn"][0] and p["state"] == "open"
    (p,) = A.proposals(rnd, [act], _ctx(styles=styles, selection={"paras": [], "table": other, "range": None}))["proposals"]
    assert p["preselect"] is False and "사람이 고른 표" in p["warn"][0]
    (p,) = A.proposals(rnd, [act], _ctx(styles=styles, selection={"paras": [], "table": "t1", "range": None}))["proposals"]
    assert p["preselect"] is True and p["warn"] == []
    (p,) = A.proposals(rnd, [act], _ctx(styles=styles, selection={"paras": [], "table": None, "range": None}))["proposals"]   # 고른 것이 없으면 요청 글이 가리킨 표다
    assert p["preselect"] is True
    paras = {"type": "restyle", "table": "", "style": "bbbbbbbbbbbb", "paras": [a, b], "item": ""}
    (p,) = A.proposals(rnd, [paras], _ctx(styles=styles, selection={"paras": [a], "table": None, "range": None}))["proposals"]
    assert p["preselect"] is False and "고른 문단 밖" in p["warn"][0]
    (p,) = A.proposals(rnd, [paras], _ctx(styles=styles, selection={"paras": [b, a, inner], "table": None, "range": None}))["proposals"]
    assert p["preselect"] is True
    # 표 채우기: 사람이 고른 표·칸 범위와 다르면 경고 · 아무 칸도 처음부터 안 고름
    fills = [{"cell": "B4", "text": "차세대 전력변환 모듈 개발", "source": "과제명: 차세대 전력변환 모듈 개발", "where": "material", "reason": ""}]
    material, fill = "과제명: 차세대 전력변환 모듈 개발", [{"type": "tableFill", "table": "t8", "range": ""}]
    box = {"r0": 3, "c0": 1, "r1": 3, "c1": 10}                                              # B4:K4 — B4 는 K 열까지 합친 칸(범위는 칸을 통째로 덮어야 한다)
    for chosen, rng, want in (({"table": "t8", "range": None}, None, None), ({"table": "t1", "range": None}, None, "사람이 고른 표"), ({"table": "t8", "range": box}, None, "칸 범위"),
                              ({"table": "t8", "range": box}, box, None), ({"table": "t8", "range": {"r0": 0, "c0": 0, "r1": 17, "c1": 10}}, None, None), ({"table": None, "range": None}, box, None)):
        ctx, an, out = _fill_ctx(small, "t8", fills, material, rng, selection={"paras": [], **chosen}, allowed={"t1", "t8"})
        (p,) = A.proposals(small, fill, ctx)["proposals"]
        assert (p["preselect"], len(p["view"]["picked"])) == ((True, 1) if want is None else (False, 0)), chosen
        assert p["warn"] == [] if want is None else want in p["warn"][0], chosen
    ctx, an, out = _fill_ctx(small, "t8", fills, material, allowed={"t1"})
    assert A.NOT_SENT in A.proposals(small, fill, ctx)["dropped"][0]["why"]
    # 범위: 빈 글 = 표 전체 · 표 밖 = 틀린 범위(표 전체로 바꿔 읽지 않는다)
    assert A.range_in(None, 3, 2) and A.range_in(A.range_of("A1:B3"), 3, 2) and not A.range_in(A.range_of("Z99"), 3, 2) and not A.range_in(A.range_of("B2:C3"), 3, 2)


def test_review3_document_changed_during_the_call_makes_every_proposal_stale(rnd, small):
    a = _anchor(rnd)
    acts = [{"type": "write", "after": a, "mode": "extract", "style": "", "lines": [{"item": "", "text": "인건비 100 120", "source": "인건비 100 120"}]},
            {"type": "tableNew", "after": a, "style": "builtin", "candidates": [{"title": "x", "why": "", "grid": _grid(GOOD)}]}]
    live = A.proposals(rnd, acts, _ctx())["proposals"]
    assert [(p["state"], p["preselect"], p["baseRev"]) for p in live] == [("open", True, 7), ("open", True, 7)]
    late = A.proposals(rnd, acts, _ctx(changed=True))["proposals"]                                                        # 끝점이 「호출 전 차례 ≠ 지금 차례」 를 알려 준다
    assert [(p["state"], p["preselect"], p["baseRev"]) for p in late] == [("stale", False, 7), ("stale", False, 7)]
    fills = [{"cell": "B4", "text": "차세대 전력변환 모듈 개발", "source": "과제명: 차세대 전력변환 모듈 개발", "where": "material", "reason": ""}]
    ctx, an, out = _fill_ctx(small, "t8", fills, "과제명: 차세대 전력변환 모듈 개발", changed=True)
    (f,) = A.proposals(small, [{"type": "tableFill", "table": "t8", "range": ""}], ctx)["proposals"]
    assert (f["state"], f["preselect"], f["view"]["picked"], f["baseRev"]) == ("stale", False, [], 7)


def test_review4_insert_boundary_and_style_table_are_in_the_fingerprint(small):
    assert A.next_top(small, "t8") == A.END and A.next_top(small, "t1") == A.END and A.next_top(small, "없음") is None   # 두 표는 한 문단에 있고 그 문단이 구역의 끝
    assert A.next_top(small, small.table_block("t8")["cells"][0]["id"]) is None                                          # 칸은 넣을 자리가 아니다
    at = {"target": A.target_of(small, ["t8"], insert=True)}
    plain = {"target": A.target_of(small, ["t8"])}
    styled = {"target": A.target_of(small, ["t8"], insert=True, style="t1")}
    assert at["target"]["next"] == A.END and "next" not in plain["target"] and styled["target"]["style"] == "t1" and len({x["target"]["hash"] for x in (at, plain, styled)}) == 3
    assert plain["target"] == {"block": "t8", "blocks": ["t8"], "hash": A.target_hash(small, "t8")}
    new = small.insert_after("t8", [{"kind": "paragraph", "text": "끼어든 문단"}])[0]
    assert A.next_top(small, "t8") == new and A.next_top(small, new) == A.END
    assert A.stale(small, at) and A.stale(small, styled) and not A.stale(small, plain)       # 넣을 자리의 글은 그대로인데 바로 뒤에 다른 것이 들어왔다 — 넣는 제안만 낡는다
    small.delete_blocks(new, new)
    assert not A.stale(small, at) and not A.stale(small, styled)
    # 서식으로 쓰는 이 문서의 표(doc:<표 id>): 글이 바뀌어도 모양이 바뀌어도 낡는다
    para = next(c["blocks"][0]["id"] for c in small.table_block("t1")["cells"] if c["text"].strip() == "별첨")
    h0 = A.style_hash(small, "t1")
    assert h0 == A.style_hash(small, "t1") and A.style_hash(small, "없음") is None and A.style_hash(small, para) is None
    text0 = A.target_hash(small, "t1")
    small.format_chars(para, 0, 0, {"bold": "toggle"})                                       # 글은 그대로, 모양만
    assert A.style_hash(small, "t1") != h0 and A.target_hash(small, "t1") == text0 and A.stale(small, styled) and not A.stale(small, at)
    mid = A.target_of(small, ["t8"], insert=True, style="t1")
    small.set_text(para, "별첨 2")
    assert A.stale(small, {"target": mid}) and A.stale(small, styled) and not A.stale(small, at)
    # 제안에: 새 표(doc: 서식) = 넣을 자리 + 경계 + 서식 표
    (p,) = A.proposals(small, [{"type": "tableNew", "after": "t8", "style": "doc:t1", "candidates": [{"title": "x", "why": "", "grid": _grid(GOOD)}]}], _ctx())["proposals"]
    assert p["target"] == A.target_of(small, ["t8"], insert=True, style="t1") and (p["target"]["next"], p["target"]["style"], p["op"]["styleRev"]) == (A.END, "t1", None)


def test_review10_fill_names_the_formula_cells_it_did_not_fill(rnd):
    j = table_excel.judge(rnd, "t1", store=copy.deepcopy(EMPTY))
    an = TF.analyze(rnd, "t1", store=copy.deepcopy(EMPTY))
    skipped = A.formula_cells(an, j)                                                           # 채울 칸에서 빠진 「추정 수식의 대상 칸」 — 빈 필드인데 수식 대상이라 안 채운다
    refs = {f["ref"] for f in j["formulas"]}
    assert skipped and set(skipped) <= refs and not set(skipped) & {t["ref"] for t in an["targets"]}
    t = an["targets"][0]
    out = {"fills": [{"ref": t["ref"], "cell": t["cell"], "row": t["row"], "col": t["col"], "name": t["name"], "form": "text", "now": t["now"], "text": "가나다", "source": "값은 가나다", "where": "material",
                      "reason": "", "quoted": True, "warn": []}], "rejected": [], "counts": {"fills": 1, "clean": 1, "warn": 0, "rejected": 0, "left": len(an["targets"]) - 1}}
    fill = {"table": "t1", "an": an, "out": out, "answer": "", "heads": None, "rev": 7, "hash": A.target_hash(rnd, "t1")}
    (p,) = A.proposals(rnd, [{"type": "tableFill", "table": "t1", "range": ""}], _ctx("값은 가나다", fills={0: fill}, store=copy.deepcopy(EMPTY)))["proposals"]
    line = next(c for c in p["checks"] if c["what"] == "formulas")
    assert line["status"] == "warn" and line["text"].startswith(f"추정 수식의 대상 칸 {len(skipped)}개는 채우지 않았습니다({skipped[0]}") and "「엑셀식 보기」" in line["text"]
    assert p["preselect"] is True and p["warn"] == [] and p["view"]["picked"] == [t["cell"]]   # 그 줄만으로 경고 없는 칸의 고름을 풀지는 않는다
    assert p["excel"]["status"] == "unknown" and p["excel"]["note"].startswith("추정한 수식 ")


# ---- 대상 해시 · 정책 ------------------------------------------------------------------------------------------------------

def test_target_hash_and_stale(small):
    t8 = small.table_block("t8")
    cell = next(c for c in t8["cells"] if c["text"] == "기술수요 과제명")
    p = {"target": A.target_of(small, ["t8"])}
    q = {"target": A.target_of(small, ["t1"])}
    assert not A.stale(small, p) and not A.stale(small, q) and A.target_hash(small, "t8") != A.target_hash(small, "t1")
    small.set_text(cell["id"], "과제 이름")
    assert A.stale(small, p) and not A.stale(small, q)                                   # 대상(그 표)이 바뀌었을 때만 — 다른 자리만 바뀐 문서는 그대로
    small.set_text(cell["id"], "기술수요 과제명")
    assert not A.stale(small, p)
    para = cell["blocks"][0]["id"]
    assert A.target_hash(small, para) and A.target_hash(small, cell["id"]) and A.target_hash(small, "없음") is None
    assert A.stale(small, {"target": A.target_of(small, ["없음"])}) and A.stale(small, {}) and A.target_of(small, [])["hash"] is None
    small.delete_blocks("t1", "t1")
    assert A.target_hash(small, "t1") is None and A.stale(small, q) and not A.stale(small, p)   # 없어진 대상


def test_policy_blocks_source_documents_of_a_task():
    assert works.TARGET_FILE == {"plan_to_report": "report", "plan_merge": "plan"}
    src = A.policy({"kind": "rnd", "job": "plan_to_report", "file": "plan", "project": "가"}, "계획서.hwpx")
    assert src["apply"] is False and "원본 문서는 바꾸지 않습니다" in src["why"]            # 이관의 사업계획서
    assert A.policy({"job": "plan_merge", "file": "part"})["apply"] is False               # 취합의 기관 문서
    for task in ({"job": "plan_to_report", "file": "report"}, {"job": "plan_merge", "file": "plan"}, {"job": "plan_merge", "file": ""}, {"job": "doc_edit", "file": ""}, {"job": "", "file": "plan"}, {}, None):
        assert A.policy(task) == {"apply": True, "why": ""}, task


# ---- 자료 ----------------------------------------------------------------------------------------------------------------

def test_material_from_text_and_plain_files():
    m = A.material_from_text(None, "  인건비 100\r\n재료비 50  ")
    assert A._MID.match(m["id"]) and (m["name"], m["kind"], m["text"], m["chars"], m["cut"]) == ("붙여 넣은 글", "text", "인건비 100\n재료비 50", 14, False) and len(m["sha256"]) == 64
    assert "text" not in A.material_view(m) and A.material_view(m)["head"] == m["text"] and sorted(A.material_view(m)) == sorted(["id", "name", "kind", "chars", "sha256", "cut", "lossy", "note", "head", "at"])
    assert (m["lossy"], m["note"]) == (False, "") and A.material_view({"id": "m00000000"})["lossy"] is False and A.material_view({"id": "m00000000"})["note"] == ""   # 옛 기록(그 키 없음)도 같은 꼴로
    long_ = A.material_from_text("긴 글", "가" * (A.MATERIAL_CHARS + 10))
    assert long_["cut"] is True and long_["chars"] == A.MATERIAL_CHARS and len(long_["head"]) == 300                                    # 200,000자까지 저장
    for bad in ("", "   ", None, 5):
        with pytest.raises(ValueError):
            A.material_from_text("x", bad)
    csv_ = A.material_from_file("C:\\자료\\예산.csv", "구분,금액\n인건비,100\n".encode("cp949"))
    assert (csv_["name"], csv_["kind"], csv_["text"]) == ("예산.csv", "csv", "구분,금액\n인건비,100")                                     # CP949 · 경로는 뗀다
    assert A.material_from_file("a.md", "\ufeff# 제목\n글".encode("utf-8"))["text"] == "# 제목\n글"
    assert A.material_from_file("a.txt", "유니코드 글".encode("utf-16"))["text"] == "유니코드 글" and A.material_from_file("a.tsv", "가\t나\n".encode())["text"] == "가\t나"
    with pytest.raises(ValueError, match="올릴 수 있는 파일"):
        A.material_from_file("a.exe", b"x")
    with pytest.raises(ValueError, match="빈 파일"):
        A.material_from_file("a.txt", b"")
    with pytest.raises(ValueError, match="인코딩"):
        A.material_from_file("a.txt", b"\x81\xff\xfe\x00\x81")
    with pytest.raises(A.TooBig):
        A.material_from_file("a.txt", b"x" * (A.MATERIAL_BYTES + 1))
    with pytest.raises(ValueError, match="읽지 못했습니다"):
        A.material_from_file("a.xlsx", b"zip \xec\x95\x84\xeb\x8b\x98")
    with pytest.raises(ValueError):
        A.material_from_file("a.hwpx", b"PK\x03\x04 broken")


def test_material_from_xlsx_docx_hwpx_pdf():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "예산"
    ws.append(["구분", "1차", "비율", "일자"])
    ws.append(["인건비", 1500000, 0.125, None])
    ws.append([None, None, None, None])
    ws.append(["재료비", 50.5, 1, "2026-01-02"])
    ws["B2"].number_format, ws["C2"].number_format = "#,##0", "0.0%"
    ws["B5"] = "=SUM(B2:B4)"                       # 수식 글이 아니라 저장된 값을 읽는다(openpyxl 로 쓴 파일에는 계산값이 없다 → 빈 글이 아니라 「(계산값 없음)」 — 검토 11)
    more = wb.create_sheet("빈 시트")
    more = wb.create_sheet("둘째")
    more.append(["가", "나"])
    buf = io.BytesIO()
    wb.save(buf)
    x = A.material_from_file("예산.xlsx", buf.getvalue())
    assert x["kind"] == "xlsx" and x["text"] == "[예산]\n구분\t1차\t비율\t일자\n인건비\t1,500,000\t12.5%\n재료비\t50.5\t1\t2026-01-02\n\t(계산값 없음)\n\n[둘째]\n가\t나" and x["cut"] is False
    assert x["lossy"] is True and "계산값이 저장되지 않은 수식 칸 1개" in x["note"]
    big = Workbook()
    for n in range(A.XLSX_ROWS + 50):
        big.active.append([n, "값"])
    buf = io.BytesIO()
    big.save(buf)
    b = A.material_from_file("큰.xlsx", buf.getvalue())
    assert b["cut"] is True and b["text"].count("\n") == A.XLSX_ROWS and b["text"].splitlines()[-1] == f"{A.XLSX_ROWS - 1}\t값"                 # 2,000행까지
    d = A.material_from_file("기술수요조사서.docx", (SAMPLES / "기술수요조사서.docx").read_bytes())
    assert d["kind"] == "docx" and "필요 기술 수요조사서" in d["text"] and "[1] 전력변환시스템 | ( ) | [2] 고전압 배전시스템" in d["text"]            # 문단 한 줄 · 표는 행마다 「a | b | c」
    h = A.material_from_file("기술수요조사서.hwpx", SMALL.read_bytes())
    assert h["kind"] == "hwpx" and "기술수요 과제명" in h["text"] and " | " in h["text"] and h["sha256"] == works.sha256(SMALL.read_bytes())
    import fitz
    pdf = fitz.open()
    for n in range(2):
        pdf.new_page().insert_text((72, 72), f"budget page {n + 1}: 1500")
    data = pdf.tobytes()
    p = A.material_from_file("a.pdf", data)
    assert p["kind"] == "pdf" and p["text"] == "[1쪽]\nbudget page 1: 1500\n\n[2쪽]\nbudget page 2: 1500" and p["cut"] is False
    empty = fitz.open()
    empty.new_page()
    with pytest.raises(ValueError, match="글이 없는 PDF"):
        A.material_from_file("scan.pdf", empty.tobytes())


def _xlsx(rows, sheets=()):
    """rows = [[(값, 표시 형식 | None)…]…] → xlsx 바이트. sheets = 더 만들 시트 [(이름, {칸 주소: 값})]."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "값"
    for r, row in enumerate(rows, 1):
        for c, (v, fmt) in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=v)
            if fmt:
                cell.number_format = fmt
    for name, cells in sheets:
        more = wb.create_sheet(name)
        for ref, v in cells.items():
            more[ref] = v
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_review11_xlsx_values_are_not_reformatted_lossy(monkeypatch):
    comma = '_-* #,##0_-;\\-* #,##0_-;_-* "-"_-;_-@_-'            # 엑셀 「쉼표 스타일」
    rows = [[(30000, '#,##0, "천원"'), (123, "000000"), (0.123456789012345, None), ("000123", "@")],            # 검토의 세 반례 + 식별자 글
            [(1234.5, '#,##0.00"원"'), (-1500, "#,##0_);(#,##0)"), (0, comma), (1500, comma), (-1500, comma)],
            [(2.5, "0"), (0.125, "0.00"), (5, 'General"명"'), (0.5, "0%"), (1234567.891, "#,##0"), (1500, "[$₩-412]#,##0"), (1.5, "[Red]0.0")],
            [(12345.678, "0.00E+00"), (0.5, "# ?/?"), (150, "[>=100]0;0.0"), (1e-07, None), (True, None), (-0.5, "0.0%"), (7, "0.0#")]]
    m = A.material_from_file("값.xlsx", _xlsx(rows))
    got = [ln.split("\t") for ln in m["text"].splitlines()[1:]]
    assert got[0] == ['30000 [표시 형식 #,##0, "천원"]', "000123", "0.123456789012345", "000123"]                 # 줄여 보이는 형식은 저장된 값 + 형식 · 앞자리 0 · 줄이지 않은 소수
    assert got[1] == ["1,234.50원", "-1500 [표시 형식 #,##0_);(#,##0)]", "-", "1,500", "-1,500"]                  # 괄호로만 음수를 보이는 형식은 저장된 값(부호를 잃지 않게)
    assert got[2] == ["3", "0.13", "5명", "50%", "1,234,568", "₩1,500", "1.5"]                                   # 엑셀처럼 반올림(2.5 → 3 · 0.125 → 0.13)
    assert got[3] == ["12345.678 [표시 형식 0.00E+00]", "0.5 [표시 형식 # ?/?]", "150 [표시 형식 [>=100]0;0.0]", "1e-07", "TRUE", "-50.0%", "7 [표시 형식 0.0#]"]
    assert m["lossy"] is True and "표시 형식을 그대로 옮기지 못한 칸 6개" in m["note"] and m["cut"] is False and A.material_view(m)["lossy"] is True
    clean = A.material_from_file("값.xlsx", _xlsx([[("인건비", None), (1500, "#,##0")]]))
    assert (clean["text"], clean["lossy"], clean["note"]) == ("[값]\n인건비\t1,500", False, "")
    # 일의 한도: 시트마다 들른 칸 수(빈 칸도 센다 — 군데군데만 찬 큰 시트) · 합쳐 낸 행 수
    sparse = _xlsx([[("머리", None)]], sheets=[("듬성", {"A1": "처음", "A300": "끝"}), ("셋째", {"A1": "셋째 시트"})])
    whole = A.material_from_file("듬성.xlsx", sparse)
    assert "끝" in whole["text"] and whole["cut"] is False
    monkeypatch.setattr(A, "XLSX_CELLS", 100)
    part = A.material_from_file("듬성.xlsx", sparse)
    assert "처음" in part["text"] and "끝" not in part["text"] and "셋째 시트" in part["text"] and part["cut"] is True and "들른 칸" in part["note"]   # 그 시트만 끊고 다음 시트는 읽는다


def test_review15_turn_ids_are_unique_and_clear_bumps_the_generation(monkeypatch):
    monkeypatch.setenv("NFM_WORKS", "off")
    st = A.Store("0123456789ab")
    ids = {st.new_turn_id(now=1_700_000_000_123) for _ in range(300)}                       # 같은 밀리초에 온 요청 300개
    assert len(ids) == 300 and all(A._TURN.match(i) and i.startswith("t1700000000123") for i in ids)
    g = st.gen()
    assert st.save_turn(_turn("t1"), gen=g) is not None and st.turn("t1") is not None
    st.clear()
    assert st.gen() == g + 1 and A.Store("0123456789ab").gen() == g + 1                    # 「비우기」 마다 차례가 오른다(같은 작업의 다른 Store 도 같은 차례)
    assert st.save_turn(_turn("t2"), gen=g) is None and st.turn("t2") is None and st.turns() == []   # 비운 뒤에 온 답(옛 차례에서 시작한 턴)은 저장하지 않는다
    assert st.save_turn(_turn("t3"), gen=st.gen()) is not None and st.save_turn(_turn("t3", "applied")) is not None and st.turn("t3")["proposals"][0]["state"] == "applied"


# ---- 저장소 --------------------------------------------------------------------------------------------------------------

def _turn(tid, state="open"):
    return {"id": tid, "at": 1.0, "rev": 0, "request": {"text": "표로 정리", "materials": []}, "reply": "후보를 냈습니다", "error": None,
            "proposals": [{"id": "p1", "type": "write", "title": "글 쓰기 — 1줄", "state": state, "op": {"after": "p1", "lines": []}, "view": {}}], "dropped": []}


@pytest.mark.parametrize("stored", [True, False])
def test_store_round_trip(stored, monkeypatch):
    wid = "0123456789ab"
    if stored:
        works.create(wid, "가.hwpx", "hwpx", b"x")
    else:
        monkeypatch.setenv("NFM_WORKS", "off")                # 작업 저장이 꺼져 있으면 메모리
    st = A.Store(wid)
    assert (st.dir is not None) is stored and st.turns() == [] and st.turn("t1") is None and st.materials() == [] and st.request("r1") is None
    st.save_turn(_turn("t1"))
    st.save_turn(_turn("t2"))
    st.save_turn(_turn("t1", "applied"))                      # 상태만 바뀐 다시 쓰기 — 요약 줄은 늘지 않는다
    assert [t["id"] for t in st.turns()] == ["t1", "t2"] and st.turns()[0]["proposals"] == [{"id": "p1", "type": "write", "title": "글 쓰기 — 1줄"}]
    assert st.turn("t1")["proposals"][0]["state"] == "applied" and st.turn("t1")["proposals"][0]["op"] == {"after": "p1", "lines": []} and st.turn("../t1") is None
    with pytest.raises(ValueError):
        st.save_turn({"id": "../x"})
    m1, m2 = A.material_from_text("가", "첫 자료"), A.material_from_text("나", "둘째 자료")
    m2["at"] = m1["at"] + 1
    st.add_material(m2)
    st.add_material(m1)
    assert [m["name"] for m in st.materials()] == ["가", "나"] and st.material(m1["id"])["text"] == "첫 자료" and st.material("m0000zzzz") is None
    assert st.drop_material(m1["id"]) is True and st.drop_material(m1["id"]) is False and [m["id"] for m in st.materials()] == [m2["id"]]
    for k in range(A.REQUESTS_KEEP + 3):
        st.remember(f"r{k}", {"state": "applied", "n": k}, "t1", "p1")
    assert st.request("r0") is None and st.request(f"r{A.REQUESTS_KEEP + 2}") == {"turn": "t1", "proposal": "p1", "at": st.request(f"r{A.REQUESTS_KEEP + 2}")["at"],
                                                                                    "applied": {"state": "applied", "n": A.REQUESTS_KEEP + 2}}   # 붙드는 것은 반영 영수증뿐(구조 편집 응답 통째가 아니다 — 검토 5)
    again = A.Store(wid)                                      # 같은 작업을 다시 열어도 같은 것(파일 · 메모리)
    assert [t["id"] for t in again.turns()] == ["t1", "t2"] and again.lock is st.lock and len(again.materials()) == 1
    if stored:
        d = works.folder(wid) / "agent"
        assert sorted(p.name for p in d.iterdir()) == ["chat.jsonl", "materials", "requests.json", "turns"] and sorted(p.name for p in (d / "turns").iterdir()) == ["t1.json", "t2.json"]
        works.add_detail(wid, "agent", "turn_1", {"turn": "t1"})
    st.clear()
    assert st.turns() == [] and st.turn("t1") is None and st.materials() == [] and st.request(f"r{A.REQUESTS_KEEP + 2}") is None
    if stored:
        assert (works.folder(wid) / "agent" / "turn_1.json").is_file()   # 턴마다 남긴 호출 상세(works.add_detail)는 비우기에 안 지워진다

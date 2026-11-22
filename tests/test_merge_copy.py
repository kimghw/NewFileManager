"""표 통째로 복사(spec_병합 ② §5-8 ·app/merge_copy.py — 2026-11-22 사용자 "이 테이블은 그냥 복사 타입으로 넣어줘"): 목적 양식이 정해 둔 표는 칸을 맞추지 않고 원본의 같은 제목 표를 그대로 넣는다.
저장소 안 자료만: 값을 반영한 계획서 양식의 요약문 「[연구개발성과의 기술기여도]」 표에 값을 적은 것(원본) ↔ 같은 값으로 반영한 연차보고서 서식(구조 반영이 그 표의 기관 행을 늘린 것 — merge_data.small)."""
import pytest

import merge_data as M
from app import heading_forms as HF
from app import hwpx_struct
from app import merge_copy as MC
from app import merge_fixed as X
from app.division_profiles import _structure as structure
from app.hwpx_doc import HwpxDoc

TITLE = "[연구개발성과의 기술기여도]"
RATE = "★67%"


def _table(S, title=TITLE):
    return [t for t in S["tables"] if t["id"] in S["idx"] and MC.key((t.get("owner") or {}).get("text")) == MC.key(title)]


@pytest.fixture(scope="module")
def pair():
    """(목적 쪽, 원본 쪽) — 원본 = 요약문 기술기여도 표의 값 칸에 「★67%」 를 적은 계획서."""
    from app.division_profiles import rnd
    from app.division_profiles.rnd import core
    d = M.small()
    plan = HwpxDoc(M.PLAN_FORM.read_bytes())
    assert not core.apply(plan, d["values"], levels_of=rnd.levels_of)["errors"]
    probe = M._side("copy-probe", plan, M.PLAN_FORM.name)   # 표를 찾으려고 한 번 읽는다(id 는 다시 읽은 문서 기준)
    t = _table(X._side({**probe, "values": d["values"]}))[0]
    doc = M.fresh(probe)
    doc.blocks()
    for c in t["cells"]:
        if c.get("role") == "field":
            doc.set_text(c["id"], RATE)
    frm = M._side("copy-plan", doc, M.PLAN_FORM.name)
    return {**d["to"], "values": d["values"]}, {**frm, "values": d["values"]}


def test_key_strips_brackets_but_keeps_numbers():
    assert MC.key("[연구개발성과의 기술기여도]") == MC.key("< 연구개발성과의  기술기여도 >") == "연구개발성과의기술기여도"
    assert MC.key("4-3. 연구개발성과의 기술기여도") != MC.key(TITLE) and MC.key(None) == ""   # 본문 절의 표는 다른 표다


def test_form_info_lists_the_tables_to_copy():
    text = '# 양식\n\n```json\n{"name": "x", "match": {"names": ["*x*"]}, "copy": ["[가 표]", " ", 3, "[나 표]"]}\n```\n\n본문\n'
    assert HF.copy_tables(text) == ["[가 표]", "[나 표]"] and HF.copy_tables("json 블록 없음") == [] and HF.copy_tables('```json\n{"copy": "글"}\n```\n') == []
    form = (M.ROOT / "forms" / "연차보고서.md").read_text(encoding="utf-8")
    assert TITLE in HF.copy_tables(form) and HF.parse(form)["name"] == "연차보고서"   # 실제 양식 정보 — 기술기여도 표 · 조건 블록은 그대로 읽힌다


def test_copy_replaces_the_target_table_once(pair):
    to, frm = pair
    T, F = X._side(to), X._side(frm)
    tt, ft = _table(T)[0], _table(F)[0]
    rows_t, rows_f = T["idx"][tt["id"]]["nRows"], F["idx"][ft["id"]]["nRows"]
    assert not any(RATE in (c.get("text") or "") for c in T["idx"][tt["id"]]["cells"]) and rows_t and rows_f   # 목적 표는 서식 그대로(값 없음)
    pl = MC.plan(T, F, [TITLE, TITLE, "[없는 표]"])
    assert [r["skip"] for r in pl["items"]] == [None, "noSource"] and pl["todo"] == 1 and pl["tables"] == [tt["id"]], pl   # 같은 제목은 한 번 · 없는 표는 할 일 없음
    it = pl["items"][0]
    assert (it["to"], it["from"], it["rows"]) == (tt["id"], ft["id"], rows_f)

    doc = M.fresh(to)
    res = MC.apply(doc, frm["doc"], pl)
    assert hwpx_struct.snapshot(frm["doc"])["bytes"] == frm["bytes"] and res["copied"] == 1 and not res["skipped"]   # 원본은 그대로
    blocks = {b["id"]: b for b in structure.iter_blocks(doc.blocks())}
    new = blocks[res["records"][MC.key(TITLE)]["to"]]
    assert tt["id"] not in blocks and new["type"] == "table" and new["nRows"] == rows_f   # 옛 표는 없고 새 표는 원본의 행 수
    assert sum(RATE in (c.get("text") or "") for c in new["cells"]) == sum(RATE in (c.get("text") or "") for c in F["idx"][ft["id"]]["cells"]) > 0
    data = hwpx_struct.snapshot(doc)["bytes"]
    assert len(HwpxDoc(data).blocks()) == len(doc.blocks())   # 저장해 다시 열림

    again = MC.plan(X._side({**to, "doc": doc}), F, [TITLE], copied=res["records"])   # 다시 계획 = 할 일 없음(새 표는 3단계 분석에 없어도 기록으로 안다)
    assert again["todo"] == 0 and again["items"][0]["skip"] == "applied" and again["tables"] == [new["id"]]
    gone = MC.plan(T, F, [TITLE], copied=res["records"])   # 실행 취소로 새 표가 사라졌다 — 기록을 안 믿고 처음부터
    assert gone["todo"] == 1 and gone["items"][0]["to"] == tt["id"]


def test_copy_keeps_a_table_someone_wrote_in_and_ambiguous_titles(pair):
    to, frm = pair
    T, F = X._side(to), X._side(frm)
    tt = _table(T)[0]
    doc = M.fresh(to)
    doc.blocks()
    cid = next(c["id"] for c in tt["cells"] if c.get("role") == "field")
    doc.set_text(cid, "사람이 쓴 값")
    pl = MC.plan(X._side({**to, "doc": doc}), F, [TITLE])
    assert pl["todo"] == 0 and pl["items"][0]["skip"] == "occupied" and "사람이 쓴 값" in pl["items"][0]["detail"] and pl["tables"] == [tt["id"]]   # 안 바꾸지만 그 표는 다른 길도 건너뛴다
    doc.set_text(cid, RATE)   # 원본 표에 있는 글(앞선 넣기가 옮긴 값) — 사람 글이 아니다
    assert MC.plan(X._side({**to, "doc": doc}), F, [TITLE])["todo"] == 1
    twin = dict(F, tables=[*F["tables"], *[dict(t) for t in _table(F)]])   # 원본에 그 제목의 표가 둘 — 짐작하지 않는다
    amb = MC.plan(T, twin, [TITLE])
    assert amb["todo"] == 0 and amb["items"][0]["skip"] == "ambiguous"

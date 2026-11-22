"""빈 구역 지우기(spec_워크플로우 ② §18-23 「빈 구역 지우기」 · app/zone_prune.py · API …/zone-prune) — 구분 기준 묶음의 항목 가운데 내용이 없는 것만 찾아 지운다:
양식의 뼈대 · 자리표시 · 안내만 있는 항목 · 그림 · 개체는 내용 · 모든 항목이 빈 묶음은 남김 — 실제 양식(연구개발계획서 · KEIT 연차보고서)에 값을 반영한 문서로."""
import pytest
from fastapi.testclient import TestClient

import merge_data as M
from app import server
from app import workflow_units as U
from app import zone_prune as Z
from app.division_profiles import _structure as structure
from app.division_profiles import rnd
from app.division_profiles.rnd import core
from app.hwpx_doc import HwpxDoc

needs_plan = pytest.mark.skipif(not M.PLAN_FORM.exists(), reason="연구개발계획서 양식 hwpx 없음")
needs_report = pytest.mark.skipif(not M.REPORT_FORM.exists(), reason="KEIT 연차보고서 서식 hwpx 없음")


def _applied(form):
    values = core.norm_values(M.SMALL_VALUES)
    doc = HwpxDoc(form.read_bytes())
    assert not core.apply(doc, values, levels_of=rnd.levels_of)["errors"]
    return doc, values


def _find(doc, values, **kw):
    blocks = doc.blocks()
    return Z.find(blocks, values, rnd.levels_of(blocks), **kw)


def _ids(doc):
    return {b["id"] for b in structure.iter_blocks(doc.blocks())}


def test_bare_text_rules():
    assert all(Z._bare(t) for t in ("", "  ", "ㅇ", "- ", "0,000", "○○○", "XXXXX", "12"))   # 빈 글 · 글머리 · 자리표시 · 번호만
    assert not Z._bare("개발 내용을 적었습니다") and not Z._bare("장비A")
    assert Z._bare("-") and not Z._bare("-", cell=True) and not Z._bare("12", cell=True) and Z._bare("0,000", cell=True)   # 표 칸의 「-」 · 수 하나는 값이다(자리표시는 아님)


@needs_plan
def test_only_the_item_without_content_is_found_and_deleted():
    doc, values = _applied(M.PLAN_FORM)
    blocks = doc.blocks()
    g = next(g for g in core.find(blocks, rnd.levels_of(blocks), values)
             if g["kind"] == "paragraph" and g["dim"] == core.ORG and g["container"] is None and not g.get("irregular") and len(g["items"]) >= 3)
    before = _find(doc, values)
    assert not [c for c in before["items"] if c["key"] == g["key"]]   # 모든 항목이 빈 묶음(양식의 틀)은 지우지 않는다
    assert any(k["key"] == g["key"] and k["why"] == "allEmpty" for k in before["kept"])
    for it in g["items"][:-1]:   # 마지막 기관만 빼고 내용을 쓴다
        doc.insert_after(it["label"], [{"kind": "paragraph", "text": f"★작성 내용 {it['value']} 의 연구개발 내용"}])
    found = _find(doc, values)
    mine = [c for c in found["items"] if c["key"] == g["key"]]
    assert [c["label"] for c in mine] == [g["items"][-1]["label"]] and mine[0]["kind"] == "paragraph" and mine[0]["dim"] == "org"
    res = Z.apply(doc, {"items": mine})
    ids = _ids(doc)
    assert res["removed"]["items"] == 1 and not res["skipped"]
    assert g["items"][-1]["label"] not in ids and all(it["label"] in ids for it in g["items"][:-1])   # 쓴 기관의 절은 남는다


@needs_plan
def test_objects_and_form_guides_are_not_content_but_objects_keep_the_item():
    doc, values = _applied(M.PLAN_FORM)
    blocks = doc.blocks()
    g = next(g for g in core.find(blocks, rnd.levels_of(blocks), values)
             if g["kind"] == "paragraph" and g["dim"] == core.ORG and g["container"] is None and not g.get("irregular") and len(g["items"]) >= 3)
    for it in g["items"][:-1]:
        doc.insert_after(it["label"], [{"kind": "paragraph", "text": f"★작성 내용 {it['value']} 의 연구개발 내용"}])
    note = doc.insert_after(g["items"][-1]["label"], [{"kind": "paragraph", "text": "※ 이 기관의 내용을 작성하시오"}])[0]
    found = _find(doc, values, guide_ids={note})   # 양식 안내(form_cleanup 이 찾는 것)는 내용이 아니다 — 그 기관은 여전히 빈 항목
    assert [c["label"] for c in found["items"] if c["key"] == g["key"]] == [g["items"][-1]["label"]]
    found = _find(doc, values, has_object=lambda pid: pid == note)   # 그림 · 개체(블록 JSON 에 안 보이는 묶음 개체 포함)가 든 문단은 내용이다
    assert not [c for c in found["items"] if c["key"] == g["key"]]


@needs_report
def test_empty_table_rows_are_deleted_but_written_rows_stay():
    doc, values = _applied(M.REPORT_FORM)
    blocks = doc.blocks()
    idx = structure.index_blocks(blocks)
    g = next(g for g in core.find(blocks, rnd.levels_of(blocks), values)
             if g["kind"] == "rows" and g["dim"] == core.ORG and not g.get("irregular") and len(g["items"]) >= 3 and not g.get("thisYear") and all(it["label"] for it in g["items"]))
    cell = lambda it: next(c for c in it["roots"] if c != it["label"] and not (idx[c].get("text") or "").strip())  # noqa: E731 — 그 행의 빈 칸 하나
    for it in g["items"][:-1]:
        doc.set_text(cell(it), "장비 구축 계획 있음")
    found = _find(doc, values)
    mine = [c for c in found["items"] if c["key"] == g["key"]]
    assert [c["label"] for c in mine] == [g["items"][-1]["label"]] and mine[0]["kind"] == "rows"
    res = Z.apply(doc, {"items": mine})
    ids = _ids(doc)
    assert res["removed"]["rows"] >= 1 and g["items"][-1]["label"] not in ids and all(it["label"] in ids for it in g["items"][:-1])


def test_unit_state_waits_for_fill_and_counts_left_items():
    fill = {"fills": True, "filled": {"at": 1.0, "nothing": False}, "links": {}, "plan": None, "heads": {}, "stages": {}}
    ctx = lambda Zf, F=fill: {"ready": True, "docs": [{"role": "target"}], "pair": {"target": {"title": "연차보고서", "id": "T", "facts": {"fill": F, "zonePrune": Zf}}}}  # noqa: E731
    got = U.state("zonePrune", ctx({"counts": {"items": 3, "blocks": 1, "rows": 2, "cols": 0}, "kept": 1}))
    assert got["st"] == "todo" and "빈 구역 3곳(본문 1 · 표 행 2)" in got["text"] and "모두 비어 남긴 묶음 1" in got["text"]
    assert U.state("zonePrune", ctx({"counts": {"items": 0}, "kept": 0}))["st"] == "done"
    assert U.state("zonePrune", ctx({"counts": {"items": 0}}, {**fill, "filled": None}))["st"] == "todo"   # 「내용 넣기」 가 끝나기 전 — 지울 것이 없어도 아직
    got = U.state("zonePrune", ctx({"counts": {}, "why": "프로젝트 구성 값이 없습니다"}))
    assert got["st"] == "done" and got["skipped"] and "건너뜁니다" in got["text"]


@needs_report
def test_api_without_values_says_why_and_lists_nothing():
    c = TestClient(server.app)
    d = c.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    v = c.get(f"/api/docs/{d}/zone-prune").json()
    assert v["items"] == [] and v["reasons"] and v["why"]   # 프로젝트 구성 값이 없는 문서(또는 관문 밖) — 까닭을 싣고 빈 목록
    assert c.post(f"/api/docs/{d}/zone-prune", json={}).status_code == 409

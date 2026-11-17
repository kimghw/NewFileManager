"""편집 구역 — 끝점 · 세션 저장 · 실행 취소 · 취합 출처(app/zones_api.py — spec_구역 ② §3 「지정 — 사람이 고른 블록」 · §4 「출처 — 취합으로 들어온 내용」 · §5 「응답」 · §7 「저장 · 읽는 길 · 등록」).
자료는 test_merge_gather_api 와 같다(gather_data — 값(기관 셋 · 1단계 2차년도)을 반영한 양식 = 취합본, 그 사본을 고쳐 다시 연 것 = 기관 문서). 판독 계산(app/zones.py)의 세부는 그 모듈의 시험 몫이고
여기서는 끝점의 꼴 · 지정의 저장과 편집 승계 · 실행 취소 뒤 번호 재사용 · 취합이 적는 출처 · server.py 의 접점을 본다."""
import copy
import json
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

import gather_data as D
import merge_data as M
from app import merge_gather_api as GA
from app import server, works
from app import task_options as TO
from app import zones as Z
from app import zones_api as ZA
from test_merge_gather_api import _analysed, _edit_a, _master, _part, _upload, _why

J1, J2, LEAD = D.J1, D.J2, D.LEAD
KEYS = {"rev", "zonesRev", "basis", "options", "orgs", "stages", "blocks", "cells", "zones", "marks", "origins", "counts", "reasons"}
SAMPLE = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"


@pytest.fixture
def client():
    server.DOCS.clear()
    for box in (GA._MEM, GA._BLOB, GA._FRAMES, GA._LINKS, GA._JUDGE, GA._PLANS, GA._DROPS, GA._ZONES, ZA._AUTO, TO._MEMORY):
        box.clear()
    return TestClient(server.app)


def _ok(r):
    assert r.status_code == 200, r.text[:600]
    return r.json()


def _zones(c, to):
    return _ok(c.get(f"/api/docs/{to}/zones"))


def _top(to):
    return [b for b in server._sess(to).doc.blocks() if not b.get("captionOf")]


def _post(c, to, ids, label, z=None, **more):
    """지정 더하기 — 차례(docRev · zonesRev)는 z(앞서 읽은 것) 또는 지금 읽은 것."""
    z = z or _zones(c, to)
    return c.post(f"/api/docs/{to}/zones/marks", json={"ids": ids, "label": label, "docRev": z["rev"], "zonesRev": z["zonesRev"], **more})


def _put(c, to, mid, z, **body):
    return c.put(f"/api/docs/{to}/zones/marks/{mid}", json={"docRev": z["rev"], "zonesRev": z["zonesRev"], **body})


def _split(c, to, pid, offset):
    """문단 나눔(Enter) → 새 문단 id."""
    return _ok(c.post(f"/api/docs/{to}/split", json={"id": pid, "offset": offset}))["focus"]["id"]


def _places(to):
    """(공통 자리의 제목 「□ 필요성」, 그 아래 줄, 가나대 1차년도 자리의 줄)."""
    doc = server._sess(to).doc
    need = D.para(doc, "□ 필요성")
    return need, D.nxt(doc, need), D.nxt(doc, D.para(doc, f"[공동연구개발기관1({J1})]", 0))


def test_get_labels_each_org_zone_with_the_task_default_options_and_reads_once(client, monkeypatch):
    c = client
    to, _ = _master(c, frame=False)
    calls, read = [], Z.read
    monkeypatch.setattr(Z, "read", lambda snap: calls.append(1) or read(snap))
    z = _zones(c, to)
    assert set(z) == KEYS and z["reasons"] == [] and (z["rev"], z["zonesRev"], z["basis"]) == (0, 0, "applied")
    assert z["options"] == {"scope": "p:취합 시험|plan_merge|1", "offered": True, "zones": {"dims": ["org"], "defaulted": True}, "rev": 0}   # 취합의 기본 = 기관
    assert [(o["key"], o["role"]) for o in z["orgs"]] == [(LEAD, "lead"), (J1, "joint"), (J2, "joint")] and z["stages"] == [2]
    ids = {b["id"] for b in _top(to)}
    in_zone = [i for x in z["zones"] for i in x["ids"]]
    assert in_zone and set(in_zone) <= ids and len(in_zone) == len(set(in_zone))   # 실제 본문 블록 · 한 띠에만
    for x in z["zones"]:
        assert set(x) == {"ids", "label", "text", "path", "first", "mark"} and x["ids"] and x["mark"] is None and x["text"] and isinstance(x["path"], list)
    assert {x["label"]["org"] for x in z["zones"] if x["label"]["orgKind"] == "org"} == {LEAD, J1, J2}   # 기관마다 띠가 있다
    need, common, j1 = _places(to)
    assert z["blocks"][j1]["org"] == J1 and z["blocks"][j1]["orgKind"] == "org" and z["blocks"][j1]["src"]["org"] == "auto"
    assert any(j1 in x["ids"] and x["label"]["org"] == J1 for x in z["zones"])
    assert (z["blocks"].get(common) or {}).get("org") is None and common not in in_zone   # 공통 자리는 기관 띠가 아니다
    assert set(z["counts"]) == {"zones", "blocks", "cells", "marks", "origins", "conflicts", "unknown"} and z["counts"]["zones"] == len(z["zones"])
    assert z["marks"] == [] and z["origins"] == [] and (z["counts"]["marks"], z["counts"]["origins"]) == (0, 0)
    assert set(z["blocks"]) <= ids and set(z["cells"]) <= {b["id"] for b in _top(to) if b["type"] == "table"}
    # 다른 모듈이 읽는 길 — 온전한 라벨(옵션과 무관)
    full = ZA.read(server._sess(to))
    assert {k for k in full if not k.startswith("_")} == KEYS and Z.label_of(full, j1)["org"] == J1 and Z.label_of(full, "p999999") is None
    # 같은 차례·값·분석이면 자동 판독을 다시 안 센다 — 옵션을 바꿔도(보이는 것만 달라진다)
    assert _zones(c, to) == z and len(calls) == 1
    TO.set_zones(works.work(to), ["year", "org"])
    z2 = _zones(c, to)
    assert z2["options"]["zones"] == {"dims": ["org", "year"], "defaulted": False} and z2["blocks"] == z["blocks"] and len(z2["zones"]) >= len(z["zones"]) and len(calls) == 1
    TO.set_zones(works.work(to), [])   # 사람이 끔 — 띠는 없고 라벨의 사실은 그대로
    z3 = _zones(c, to)
    assert z3["options"]["zones"] == {"dims": [], "defaulted": False} and z3["zones"] == [] and z3["blocks"] == z["blocks"] and len(calls) == 1
    first = next(b["id"] for b in _top(to) if b["type"] == "paragraph" and b["text"].strip())
    assert c.patch(f"/api/docs/{to}/blocks/{first}", json={"text": "고친 표지 글"}).status_code == 200
    assert _zones(c, to)["rev"] == 1 and len(calls) == 2   # 문서가 바뀌면 다시


def test_no_values_docx_and_general_documents_say_why(client):
    c = client
    to = _upload(c, "프레임.hwpx", D.base()["side"]["bytes"])
    z = _zones(c, to)
    assert set(z) == KEYS and z["reasons"] == ["noValues"] and z["basis"] is None and (z["orgs"], z["stages"], z["blocks"], z["cells"], z["zones"]) == ([], [], {}, {}, [])
    assert z["options"] == {"scope": f"w:{to}", "offered": True, "zones": {"dims": [], "defaulted": True}, "rev": 0}   # 프로젝트 없는 작업 · TASK 없음
    need = D.para(server._sess(to).doc, "□ 필요성")
    assert _why(_post(c, to, [need], {"org": J1}, z), 400, "badMark")["message"] == "프로젝트 구성 값이 없어 기관을 지정할 수 없습니다"   # 기관 목록이 없다
    _why(_post(c, to, [need], {"year": 1}, z), 400, "badMark")
    assert server._sess(to).zones == ZA.blank()
    assert c.put(f"/api/docs/{to}/divisions/settings", json={"values": D.VALUES}).status_code == 200   # 반영 전 — 입력 값으로 읽는다
    z = _zones(c, to)
    assert z["reasons"] == [] and z["basis"] == "settings" and [o["key"] for o in z["orgs"]] == [LEAD, J1, J2] and z["blocks"]
    docx = _upload(c, "조사서.docx", (M.ROOT / "samples" / "기술수요조사서.docx").read_bytes())
    z = _zones(c, docx)
    assert set(z) == KEYS and z["reasons"] == ["unsupportedForm"] and (z["blocks"], z["cells"], z["zones"], z["marks"], z["origins"]) == ({}, {}, [], [], [])
    para = next(b["id"] for b in server._sess(docx).doc.blocks() if b["type"] == "paragraph")
    assert "hwpx" in _why(_post(c, docx, [para], {"org": J1}, z), 400, "badMark")["message"]
    gen = _upload(c, SAMPLE.name, SAMPLE.read_bytes())
    assert c.put(f"/api/works/{gen}/task", json={"kind": "general", "file": "", "job": "doc_edit", "project": ""}).status_code == 200
    z = _zones(c, gen)
    assert z["reasons"] == ["noValues", "notOffered"] and z["options"]["offered"] is False and z["zones"] == []   # 일반 문서 — 편집 구역을 내지 않는다
    assert "연구개발" in _why(_post(c, gen, [_top(gen)[0]["id"]], {"org": J1}, z), 400, "badMark")["message"]


def test_marks_add_edit_delete_and_a_block_belongs_to_one_mark(client):
    c = client
    to, _ = _master(c, frame=False)
    need, common, j1 = _places(to)
    z = _ok(_post(c, to, [common, need, common], {"org": J2}, note="  다라연이   쓸 곳 "))
    assert set(z) == KEYS and (z["rev"], z["zonesRev"]) == (0, 1) and server._sess(to).undo == []   # 문서는 안 바뀐다 — 편집 차례·실행 취소 그대로
    (m,) = z["marks"]
    assert set(m) == {"id", "ids", "gone", "label", "note", "by", "at", "invalid"} and m["ids"] == [need, common]   # 문서 차례 · 중복 없음
    assert (m["gone"], m["label"], m["note"], m["by"], m["invalid"]) == (0, {"org": J2}, "다라연이 쓸 곳", "user", []) and m["at"]
    for i in (need, common):
        assert (z["blocks"][i]["org"], z["blocks"][i]["orgKind"], z["blocks"][i]["src"]["org"]) == (J2, "org", "mark")
    assert any(x["mark"] == m["id"] and {need, common} <= set(x["ids"]) and x["label"]["org"] == J2 for x in z["zones"]) and z["counts"]["marks"] == 1
    assert (z["blocks"][j1]["org"], z["blocks"][j1]["src"]["org"]) == (J1, "auto")   # 다른 블록은 그대로

    z = _ok(_put(c, to, m["id"], z, label={"org": J1}))   # 값만
    assert [(x["id"], x["ids"], x["label"], x["note"]) for x in z["marks"]] == [(m["id"], [need, common], {"org": J1}, "다라연이 쓸 곳")] and z["blocks"][common]["org"] == J1 and z["zonesRev"] == 2
    z = _ok(_put(c, to, m["id"], z, note=""))   # 메모만
    assert (z["marks"][0]["note"], z["marks"][0]["label"]) == ("", {"org": J1})
    z = _ok(_put(c, to, m["id"], z, ids=[common]))   # 블록만
    assert z["marks"][0]["ids"] == [common] and (z["blocks"].get(need) or {}).get("src", {}).get("org") != "mark"
    z = _ok(_put(c, to, m["id"], z, label={"org": None}))   # 「기관 없음」 으로 지정
    assert z["marks"][0]["label"] == {"org": None} and (z["blocks"].get(common) or {}).get("org") is None

    z = _ok(_post(c, to, [common], {"org": LEAD}, z))   # 한 블록은 한 지정에만 — 새 지정이 가져가면 옛 지정에서 빠지고 빈 지정은 지워진다
    assert [(x["ids"], x["label"]) for x in z["marks"]] == [([common], {"org": LEAD})] and z["marks"][0]["id"] != m["id"]
    z = _ok(_post(c, to, [need, common], {"org": J1}, z))
    z = _ok(_post(c, to, [common], {"org": J2}, z))
    assert {tuple(x["ids"]): x["label"]["org"] for x in z["marks"]} == {(need,): J1, (common,): J2}
    table = next(b for b in _top(to) if b["type"] == "table" and any(x["blocks"] for x in b["cells"]))
    z = _ok(_post(c, to, [table["id"]], {"org": J1, "year": 2}, z))   # 표도 지정 대상 · 기준 둘
    assert (z["blocks"][table["id"]]["org"], z["blocks"][table["id"]]["year"], z["blocks"][table["id"]]["src"]["year"]) == (J1, 2, "mark")

    # 낡은 화면 · 대상이 아님 · 값이 틀림 · 없는 지정
    marks = f"/api/docs/{to}/zones/marks"
    _why(_post(c, to, [need], {"org": J1}, {**z, "rev": z["rev"] + 1}), 409, "staleDoc")
    _why(_post(c, to, [need], {"org": J1}, {**z, "zonesRev": z["zonesRev"] - 1}), 409, "staleZones")
    _why(c.post(marks, json={"ids": [need], "label": {"org": J1}}), 400, "badMark")   # 차례를 안 보냄
    cell = next(x for x in table["cells"] if x["blocks"])
    assert "표 칸" in _why(_post(c, to, [need, cell["id"]], {"org": J1}, z), 400, "badMark")["message"]
    assert "표 칸 안" in _why(_post(c, to, [cell["blocks"][0]["id"]], {"org": J1}, z), 400, "badMark")["message"]
    assert "없는 블록" in _why(_post(c, to, ["p999999"], {"org": J1}, z), 400, "badMark")["message"]
    for ids in ([], "p1", [3], None):
        _why(_post(c, to, ids, {"org": J1}, z), 400, "badMark")
    for label in ({"org": "없는기관"}, {}, {"year": 9}, {"stage": 3}, "가나대", None):
        _why(_post(c, to, [need], label, z), 400, "badMark")
    _why(_post(c, to, [need], {"org": J1}, z, note=3), 400, "badMark")
    mid = z["marks"][0]["id"]
    _why(_put(c, to, "없는지정", z, note="x"), 404, "noMark")
    _why(_put(c, to, mid, z), 400, "badMark")   # 바꿀 것이 없음
    _why(_put(c, to, mid, {**z, "rev": z["rev"] + 1}, note="x"), 409, "staleDoc")
    _why(c.delete(f"{marks}/없는지정?zonesRev={z['zonesRev']}"), 404, "noMark")
    _why(c.delete(f"{marks}/{mid}"), 400, "badMark")   # 구역 판을 안 보냄
    _why(c.delete(f"{marks}/{mid}?zonesRev=0"), 409, "staleZones")
    assert _zones(c, to) == z   # 거절된 요청은 아무것도 안 바꾼다

    z2 = _ok(c.delete(f"{marks}/{mid}?zonesRev={z['zonesRev']}"))   # 지정 해제
    assert set(z2) == KEYS and mid not in {x["id"] for x in z2["marks"]} and len(z2["marks"]) == len(z["marks"]) - 1 and z2["zonesRev"] == z["zonesRev"] + 1 and z2["rev"] == 0
    events = [e for e in works.events(to) if e["kind"] == "zoneMark"]
    assert [e["op"] for e in events] == ["add", "edit", "edit", "edit", "edit", "add", "add", "add", "add", "delete"] and all({"op", "id", "blocks", "label"} <= set(e) for e in events)
    assert events[0]["blocks"] == 2 and events[0]["label"] == {"org": J2} and events[-1]["id"] == mid


def test_split_extends_the_mark_to_the_new_paragraph_and_other_splits_change_nothing(client):
    c = client
    to, _ = _master(c, frame=False)
    need, common, j1 = _places(to)
    z = _ok(_post(c, to, [need], {"org": J2}))
    new = _split(c, to, need, 2)   # 지정한 문단을 나눔 — 새 문단도 그 지정(나온 문단 바로 뒤)
    z = _zones(c, to)
    assert z["rev"] == 1 and [x["ids"] for x in z["marks"]] == [[need, new]] and z["zonesRev"] == 2
    assert (z["blocks"][new]["org"], z["blocks"][new]["src"]["org"]) == (J2, "mark") and server._sess(to).zones["marks"][0]["ids"] == [need, new]
    again = _split(c, to, new, 1)   # 이어받은 문단을 또 나눠도
    z = _zones(c, to)
    assert [x["ids"] for x in z["marks"]] == [[need, new, again]] and z["zonesRev"] == 3
    other = _split(c, to, common, 1)   # 지정 밖 문단을 나누면 아무 일 없음
    z2 = _zones(c, to)
    assert z2["marks"] == z["marks"] and z2["zonesRev"] == z["zonesRev"] and (z2["blocks"].get(other) or {}).get("src", {}).get("org") != "mark"
    cell = next(x for b in _top(to) if b["type"] == "table" for x in b["cells"] if x["blocks"] and len(x["blocks"][0].get("text") or "") > 2)
    table = next(b["id"] for b in _top(to) if b["type"] == "table" and cell in b["cells"])
    z = _ok(_post(c, to, [table], {"org": J1}, z2))
    inner = _split(c, to, cell["blocks"][0]["id"], 1)   # 지정한 표의 칸 안 문단을 나눠도 지정에는 본문 블록만 든다
    z3 = _zones(c, to)
    assert inner not in {i for x in z3["marks"] for i in x["ids"]} and z3["zonesRev"] == z["zonesRev"]
    assert ZA.INHERIT_OPS == {"split", "outline"}   # 지정을 잇는 편집 — 취합·구분 기준 반영·이관·서식 적용이 만든 블록은 잇지 않는다


def test_new_outline_lines_join_the_mark_of_the_line_they_came_from(client):
    c = client
    to, _ = _master(c, frame=False)
    need, common, j1 = _places(to)
    z = _ok(_post(c, to, [need, j1], {"org": J2}))
    text = {b["id"]: b["text"] for b in _top(to) if b["type"] == "paragraph"}
    out = _ok(c.post(f"/api/docs/{to}/outline", json={"op": "enter", "id": need, "offset": len(text[need])}))   # 지정한 개요 줄 끝의 Enter — 새 줄(과 사이 줄)
    new = out["outline"]["new"]
    order = [b["id"] for b in _top(to)]
    z = _zones(c, to)
    (m,) = z["marks"]
    assert new and set(new) <= set(m["ids"]) and len(m["ids"]) == 2 + len(new) and z["zonesRev"] == 2
    assert m["ids"] == sorted(m["ids"], key=order.index) and m["ids"][0] == need and m["ids"][-1] == j1   # 나온 줄 바로 뒤에 · 문서 차례로
    assert all(z["blocks"][i]["src"]["org"] == "mark" for i in new)
    out = _ok(c.post(f"/api/docs/{to}/outline", json={"op": "sibling", "id": need}))   # 같은 레벨 뼈대(Alt+Enter) — 여러 줄이 한 번에 생긴다
    more = out["outline"]["new"]
    order = [b["id"] for b in _top(to)]
    z = _zones(c, to)
    (m,) = z["marks"]
    assert len(more) > 1 and set(more) <= set(m["ids"]) and z["zonesRev"] == 3
    assert [i for i in m["ids"] if i in more] == sorted(more, key=order.index)   # 한 줄에서 나온 여러 줄은 문서 차례로 이어진다
    out = _ok(c.post(f"/api/docs/{to}/outline", json={"op": "enter", "id": common, "offset": len(text[common])}))   # 지정 밖 줄의 새 줄은 지정이 아니다
    z2 = _zones(c, to)
    assert out["outline"]["new"] and not set(out["outline"]["new"]) & set(z2["marks"][0]["ids"]) and z2["zonesRev"] == 3


def test_undo_drops_blocks_that_left_so_a_reused_number_inherits_nothing(client):
    """astra P1-1: 실행 취소는 번호표도 되돌린다 — 새 문단을 지정한 뒤 되돌리고 다시 나누면 **같은 번호**의 다른 새 문단이 생긴다. 옛 지정을 물려받으면 안 된다."""
    c = client
    to, _ = _master(c, frame=False)
    need, common, j1 = _places(to)
    new = _split(c, to, need, 2)
    z = _ok(_post(c, to, [new], {"org": J2}))
    assert [x["ids"] for x in z["marks"]] == [[new]] and z["blocks"][new]["src"]["org"] == "mark"
    assert c.post(f"/api/docs/{to}/undo").status_code == 200
    z = _zones(c, to)
    assert z["marks"] == [] and server._sess(to).zones["marks"] == [] and z["zonesRev"] == 2   # 되돌린 문서에 없는 블록은 지정에서 빠진다(「없어진 블록」 으로 남기지 않는다)
    again = _split(c, to, need, 2)
    assert again == new   # 같은 번호가 다시 쓰였다
    z = _zones(c, to)
    assert z["marks"] == [] and (z["blocks"].get(again) or {}).get("src", {}).get("org") != "mark"
    z = _ok(_post(c, to, [need, again], {"org": J1}, z))   # 남은 블록이 있는 지정은 그 블록만 남는다
    assert c.post(f"/api/docs/{to}/undo").status_code == 200
    z = _zones(c, to)
    assert [(x["ids"], x["gone"]) for x in z["marks"]] == [([need], 0)]
    third = _split(c, to, need, 2)   # 지정한 문단을 다시 나눈 것은 그 지정을 잇는다(편집이 알려 준 새 블록)
    assert third == new and [x["ids"] for x in _zones(c, to)["marks"]] == [[need, third]]


def test_a_mark_on_a_removed_block_survives_undo_until_the_block_comes_back(client):
    """되돌린 뒤에는 **번호표보다 뒤에 매겨진 id 만** 뺀다(다시 쓰일 번호) — 지정한 문단을 합쳐 없앤 뒤 다른 편집을 하고 두 번 되돌리면, 첫 되돌림에서 그 지정이 사라지지 않고 문단과 함께 돌아온다."""
    c = client
    to, _ = _master(c, frame=False)
    need, common, j1 = _places(to)
    z = _ok(_post(c, to, [common], {"org": J2}))
    assert c.post(f"/api/docs/{to}/merge", json={"id": common, "dir": "prev"}).status_code == 200   # 지정한 문단이 앞 문단에 붙어 없어진다(편집 1)
    z = _zones(c, to)
    assert [(x["ids"], x["gone"]) for x in z["marks"]] == [([], 1)] and common not in z["blocks"]   # 없어진 블록은 gone 으로 — 지정은 남는다
    _split(c, to, j1, 1)   # 다른 편집(편집 2)
    assert c.post(f"/api/docs/{to}/undo").status_code == 200   # 편집 2 를 되돌림 — 없어진 문단은 아직 없다
    z = _zones(c, to)
    assert [(x["ids"], x["gone"]) for x in z["marks"]] == [([], 1)] and server._sess(to).zones["marks"][0]["ids"] == [common]
    assert c.post(f"/api/docs/{to}/undo").status_code == 200   # 편집 1 을 되돌림 — 같은 id 로 돌아온다
    z = _zones(c, to)
    assert [(x["ids"], x["gone"]) for x in z["marks"]] == [([common], 0)] and z["blocks"][common]["org"] == J2 and z["blocks"][common]["src"]["org"] == "mark"


def test_marks_are_saved_with_the_work_and_come_back_when_reopened(client):
    c = client
    to, _ = _master(c, frame=False)
    need, common, j1 = _places(to)
    z = _ok(_post(c, to, [need, common], {"org": J2, "year": 1}, note="메모"))
    st = json.loads((works.folder(to) / "state.json").read_text("utf-8"))   # 지정은 문서 차례를 안 올려도 바로 저장된다
    assert st["rev"] == 0 and st["zones"]["rev"] == 1 and st["zones"]["origins"] == []
    assert [(m["ids"], m["label"], m["note"], m["by"]) for m in st["zones"]["marks"]] == [([need, common], {"org": J2, "year": 1}, "메모", "user")]
    server.DOCS.pop(to)
    s = server._sess(to)   # 작업 폴더에서 다시 연다
    assert s.zones == st["zones"] and s.zones is not st["zones"]
    z2 = _zones(c, to)
    assert z2["marks"] == z["marks"] and z2["zonesRev"] == 1 and (z2["blocks"][need]["org"], z2["blocks"][need]["year"]) == (J2, 1)
    # 꼴이 틀린 저장 값은 빈 것으로 · 못 읽는 한 줄은 그 줄만 버린다
    assert ZA.load(None) == ZA.load("x") == ZA.load({"rev": 3, "marks": "x", "origins": []}) == ZA.blank() == {"rev": 0, "marks": [], "origins": []}
    got = ZA.load({"rev": 4, "marks": [{"id": "a", "ids": ["p1", 3], "label": {"org": "가"}}, {"id": "b", "ids": [], "label": {}}, {"ids": ["p2"]}, 7],
                   "origins": [{"id": "e", "ids": ["p9"], "orgs": ["가", 1], "part": "x"}, {"ids": ["p1"]}]})
    assert got == {"rev": 4, "marks": [{"id": "a", "ids": ["p1"], "label": {"org": "가"}}], "origins": [{"id": "e", "ids": ["p9"], "orgs": ["가"], "part": "x"}]}


def test_restoring_the_base_prunes_marks_of_blocks_that_are_gone(client):
    c = client
    to, _ = _master(c, frame=False)
    need, common, j1 = _places(to)
    new = _split(c, to, need, 2)
    z = _ok(_post(c, to, [new], {"org": J2}))
    z = _ok(_post(c, to, [common], {"org": J1}, z))
    assert _ok(c.post(f"/api/docs/{to}/commits/0/restore", json={"discard": True}))["rev"] == 2   # 모두 되돌리기 — 새 문단이 없어진다
    z = _zones(c, to)
    assert [(x["ids"], x["label"]) for x in z["marks"]] == [([common], {"org": J1})] and z["zonesRev"] == 3   # 되돌린 문서에 있는 블록의 지정만 남는다


def _applied(c, to, A):
    plan = _ok(c.post(f"/api/docs/{to}/gather/parts/{A}/plan"))
    return _ok(c.post(f"/api/docs/{to}/gather/parts/{A}/apply", json={"planId": plan["planId"]}))


def test_gather_apply_records_origins_that_freeze_the_part_and_leave_with_undo(client):
    c = client
    to, _ = _master(c)
    A = _part(c, to, "기관A_가나대.hwpx", _edit_a, orgs=[J1])
    assert GA.legacy_origins(to) == [] and _zones(c, to)["origins"] == []
    _applied(c, to, A)
    s = server._sess(to)
    saved = GA._store(to)["parts"][A]["applied"]
    evs = s.zones["origins"]
    assert len(evs) == 4 and s.zones["rev"] == 4 and sorted(e["kind"] for e in evs) == ["cells", "filled", "filled", "rows"]
    for e in evs:   # 그때의 기관 문서·반영할 기관을 굳힌 이벤트 — 넣은 기록의 ev 가 그 id
        assert (e["part"], e["name"], e["orgs"]) == (A, "기관A_가나대.hwpx", [J1]) and e["ids"] == saved[e["key"]]["ids"] and saved[e["key"]]["ev"] == e["id"] and e["at"]
    z = _zones(c, to)
    assert z["zonesRev"] == 4 and len(z["origins"]) == 4 and z["counts"]["origins"] == 4 and GA.legacy_origins(to) == []
    for o in z["origins"]:
        assert set(o) == {"id", "part", "name", "orgs", "kind", "at", "ids", "gone"} and (o["part"], o["name"], o["orgs"], o["gone"]) == (A, "기관A_가나대.hwpx", [J1], 0) and o["ids"]
    by_text = {" ".join((b.get("text") or "").split()): b["id"] for b in _top(to) if b["type"] == "paragraph"}
    common, own = by_text[f"o {J1}가 쓴 필요성"], by_text[f"o {J1} 1차년도 개발 목표"]
    assert (z["blocks"][common]["org"], z["blocks"][common]["orgKind"], z["blocks"][common]["src"]["org"]) == (J1, "org", "origin")   # 공통 자리에 들어온 내용 = 그 기관 구역
    assert (z["blocks"][own]["org"], z["blocks"][own]["src"]["org"]) == (J1, "auto")   # 기관 자리는 자리 소속 그대로(출처는 따로 보인다)
    # 반영할 기관을 바꿔도 지난 출처는 그대로
    assert c.put(f"/api/docs/{to}/gather/parts/{A}", json={"orgs": [J2]}).status_code == 200
    z = _zones(c, to)
    assert all(o["orgs"] == [J1] for o in z["origins"]) and z["blocks"][common]["org"] == J1
    # 기관 문서를 취합에서 빼도
    assert c.delete(f"/api/docs/{to}/gather/parts/{A}").status_code == 200
    assert len(_zones(c, to)["origins"]) == 4
    assert c.put(f"/api/docs/{to}/gather/parts/{A}", json={"orgs": [J2]}).status_code == 200
    # 실행 취소 = 출처도 함께 돌아간다 — 넣은 기록(ev 있음)은 옛 기록으로도 나오지 않는다
    assert c.post(f"/api/docs/{to}/undo").status_code == 200
    z = _zones(c, to)
    assert s.zones["origins"] == [] and z["origins"] == [] and z["counts"]["origins"] == 0 and GA.legacy_origins(to) == [] and len(GA._store(to)["parts"][A]["applied"]) == 4
    # ev 가 없는 옛 기록만 legacy 로 — 기관은 지금의 반영할 기관 · 남은 id 만
    GA._change(to, lambda G: [a.pop("ev") for a in G["parts"][A]["applied"].values()], bump=False)
    old = GA.legacy_origins(to)
    assert len(old) == 4 and all(set(o) == {"id", "part", "name", "orgs", "kind", "ids", "key", "at", "legacy"} and o["legacy"] is True and o["id"] == f"legacy:{A}:{o['key']}" and o["orgs"] == [J2] for o in old)
    z = _zones(c, to)
    assert len(z["origins"]) == 4 and all(o.get("legacy") is True and o["orgs"] == [J2] for o in z["origins"])
    assert all(o["ids"] == [] and o["gone"] > 0 for o in z["origins"] if o["kind"] in ("filled", "rows")) and z["counts"]["origins"] == 1   # 칸은 그대로 있다(글만 되돌아감)
    # 취합을 한 적 없는 문서 · 취합 TASK 가 아닌 문서 — 파일을 만들지 않고 빈 것
    assert GA.legacy_origins(A) == [] and not (works.folder(A) / "gather.json").exists()


def test_splitting_gathered_content_keeps_its_origin_and_an_empty_new_line_does_not(client):
    """astra 결과 검토 10: 취합으로 들어온 문단을 나누면 뒷부분도 그 기관 문서에서 온 내용이다 — 출처 이벤트가 새 문단을 잇는다(공통 자리면 기관도). 문단 끝에서 Enter 로 생긴 빈 줄은 잇지 않는다. 되돌리면 함께 돌아간다."""
    c = client
    to, _ = _master(c)
    A = _part(c, to, "기관A_가나대.hwpx", _edit_a, orgs=[J1])
    _applied(c, to, A)
    s = server._sess(to)
    by_text = {" ".join((b.get("text") or "").split()): b["id"] for b in _top(to) if b["type"] == "paragraph"}
    common = by_text[f"o {J1}가 쓴 필요성"]
    before = copy.deepcopy(s.zones["origins"])
    rev = s.zones["rev"]
    tail = _split(c, to, common, 4)   # 글 가운데서 나눔 — 뒷부분에도 글이 있다
    ev = next(e for e in s.zones["origins"] if common in e["ids"])
    assert ev["ids"][ev["ids"].index(common) + 1] == tail and s.zones["rev"] == rev + 1
    z = _zones(c, to)
    assert (z["blocks"][tail]["org"], z["blocks"][tail]["src"]["org"]) == (J1, "origin") and z["blocks"][common]["src"]["org"] == "origin"
    blank = _split(c, to, tail, len(s.texts[tail]))   # 문단 끝에서 Enter — 빈 새 줄은 사람이 이제 쓸 자리다
    assert (s.texts.get(blank) or "").strip() == "" and all(blank not in e["ids"] for e in s.zones["origins"]) and s.zones["rev"] == rev + 1
    assert blank not in _zones(c, to)["blocks"]
    assert c.post(f"/api/docs/{to}/undo").status_code == 200 and c.post(f"/api/docs/{to}/undo").status_code == 200   # 두 나눔을 되돌림 — 출처도 넣은 때의 것으로
    assert s.zones["origins"] == before and tail not in _zones(c, to)["blocks"]


def test_dragging_a_section_in_records_a_drop_origin(client):
    c = client
    b = D.base()["side"]
    to, _ = _master(c, frame=False)
    P = _upload(c, "기관P.hwpx", b["bytes"])
    assert c.put(f"/api/docs/{to}/gather/parts/{P}", json={"orgs": [J2]}).status_code == 200
    _analysed(P, b["graph"])
    doc, src = server._sess(to).doc, server._sess(P).doc
    p = _ok(c.post(f"/api/docs/{to}/gather/drop/plan", json={"from": P, "srcId": D.para(src, "□ 필요성"), "afterId": D.para(doc, "1-2. 연구개발과제의 배경 및 필요성")}))
    out = _ok(c.post(f"/api/docs/{to}/gather/drop/apply", json={"planId": p["planId"], "convert": False}))
    (e,) = server._sess(to).zones["origins"]
    assert (e["part"], e["name"], e["orgs"], e["kind"], e["key"], e["ids"]) == (P, "기관P.hwpx", [J2], "drop", None, out["ids"]) and out["ids"]
    z = _zones(c, to)
    assert [(o["kind"], o["ids"], o["gone"], o["orgs"]) for o in z["origins"]] == [("drop", out["ids"], 0, [J2])] and z["counts"]["origins"] == 1
    assert (z["blocks"][out["ids"][0]]["org"], z["blocks"][out["ids"][0]]["src"]["org"]) == (J2, "origin")   # 공통 자리에 끌어 넣은 내용 = 그 기관 구역
    assert c.post(f"/api/docs/{to}/undo").status_code == 200
    assert server._sess(to).zones["origins"] == [] and _zones(c, to)["origins"] == []


def test_task_options_follow_project_rename_new_round_and_delete(client, monkeypatch):
    c = client
    monkeypatch.setattr(server, "_start", lambda *a, **k: None)
    monkeypatch.setattr(server, "_ensure_persister", lambda: None)
    wid = _upload(c, SAMPLE.name, SAMPLE.read_bytes())
    assert c.put(f"/api/works/{wid}/task", json={"kind": "rnd", "file": "plan", "job": "plan_fit", "project": "선박"}).status_code == 200
    assert _zones(c, wid)["options"] == {"scope": "p:선박|plan_fit|1", "offered": True, "zones": {"dims": [], "defaulted": True}, "rev": 0}
    TO.set_zones(works.work(wid), ["stage", "org"])
    assert _zones(c, wid)["options"] == {"scope": "p:선박|plan_fit|1", "offered": True, "zones": {"dims": ["org", "stage"], "defaulted": False}, "rev": 1}
    assert c.put(f"/api/projects/{quote('선박')}", json={"name": "새 선박"}).status_code == 200   # 프로젝트 이름 변경 — 옵션의 묶음 열쇠도 옮긴다
    assert _zones(c, wid)["options"] == {"scope": "p:새 선박|plan_fit|1", "offered": True, "zones": {"dims": ["org", "stage"], "defaulted": False}, "rev": 1}
    r = _ok(c.post(f"/api/works/{wid}/round", json={"source": "current"}))   # 새 라운드 — 옵션은 이어받고 지정은 안 옮긴다(블록 id 가 새로 매겨진다)
    fresh = r["docId"]
    assert _zones(c, fresh)["options"] == {"scope": "p:새 선박|plan_fit|2", "offered": True, "zones": {"dims": ["org", "stage"], "defaulted": False}, "rev": 1}
    assert server._sess(fresh).zones == ZA.blank()
    assert c.delete(f"/api/projects/{quote('새 선박')}?docs=delete").status_code == 200   # 문서까지 삭제 — 그 프로젝트의 옵션도 지운다
    assert TO.resolve({"id": "x", "task": {"kind": "rnd", "job": "plan_fit", "project": "새 선박", "round": 2}})["zones"] == {"dims": [], "defaulted": True}
    assert TO.resolve({"id": "x", "task": {"kind": "rnd", "job": "plan_fit", "project": "새 선박"}})["rev"] == 0
    # 프로젝트 해제(문서는 남김)도 옵션을 지운다 — 남기면 같은 이름으로 다시 만든 프로젝트가 옛 옵션을 물려받는다. 남은 문서는 문서마다의 범위(기본값)
    one = _upload(c, "해제.hwpx", SAMPLE.read_bytes())
    assert c.put(f"/api/works/{one}/task", json={"kind": "rnd", "file": "plan", "job": "plan_fit", "project": "해제할 것"}).status_code == 200
    TO.set_zones(works.work(one), ["year"])
    assert c.delete(f"/api/projects/{quote('해제할 것')}?docs=keep").status_code == 200
    assert _zones(c, one)["options"] == {"scope": f"w:{one}", "offered": True, "zones": {"dims": [], "defaulted": True}, "rev": 0}
    assert TO.resolve({"id": "x", "task": {"kind": "rnd", "job": "plan_fit", "project": "해제할 것"}})["zones"] == {"dims": [], "defaulted": True}

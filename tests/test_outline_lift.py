"""표 제목을 템플릿의 L1 으로(spec_hwpx_웹편집 ② §8-7 — app/outline_lift.py · app/outline_lift_api.py · outline_edit 의 표 줄 가지).
연구개발계획서 양식(2단계 LLM 끔): 가지 템플릿 T2 「□›o›-›·」 의 첫 레벨 줄 하나 바로 위에 1칸 제목 상자 「기술준비도(TRL, …」 가 있다.
후보(같은 꼴 묶음) · 넣기(레벨 한 칸 밀기 · 표 줄 · 그 아래 줄의 부모 · 요약) · 표 줄의 Enter = 표 아래 L2 새 줄 · 거절(Alt+Enter·레벨·지우기 · 표 레벨로 올리기) ·
아래 줄의 레벨 바꿈이 표 줄을 부모로 · 제목 글을 고쳐도 줄이 남음 · 더한 레벨(§8-6)과 함께 · 떼기 = 넣기 전 그대로 · 실행 취소 · 2단계 다시 실행 뒤 다시 걸기 · 못 넣는 템플릿.
넓힘(② §8-7 「넓힘」 — 양식의 그 상자를 베껴 만든 문서 `_tiered_bytes`: 3행 표 · 띠 「1 .|띠 제목 1」·「2 .|…」 · 상자 · □ / 띠 「3 .|…」 · □): 제목 표의 꼴(1칸 · 번호 칸 + 제목 칸 · 3행) ·
같은 꼴이면 아래에 템플릿 줄이 없는 표도 · 표 레벨 여러 층(상자 → 띠 → 3행 표)과 부모 · 넣는 차례와 무관 · 표 줄의 Enter = 첫 글 레벨 · 2단계 다시 실행 뒤 층째 다시 걸기 · 옛 꼴 이름 기록."""
import copy
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs
from app import outline_edit as OE
from app import outline_lift as OL
from app import server
from app.hwpx_doc import HwpxDoc, P

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


@pytest.fixture(scope="module")
def sess(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("outline_lift")  # 모듈 픽스처는 conftest 의 시험별 임시 폴더보다 먼저 돈다 — 사용자 작업 폴더에 작업이 쌓이지 않게
    with pytest.MonkeyPatch.context() as mp:
        for k, v in {"NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": tmp / "works", "NFM_RENDER": tmp / "render",
                     "NFM_HEADINGS": tmp / "heads", "NFM_FORMS": tmp / "forms", "NFM_DIVISION_PRESETS": tmp / "presets.json"}.items():
            mp.setenv(k, str(v))
        server.DOCS.clear()
        c = TestClient(server.app, raise_server_exceptions=False)
        r = c.post("/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")})
        assert r.status_code == 200, r.text
        d = r.json()["docId"]
        s = server.DOCS[d]
        heading_runs.run_sync(s, 1, False)
        heading_runs.run_sync(s, 2, False)
        assert c.get(f"/api/docs/{d}/outline").status_code == 200  # 오버레이를 만든다
        yield c, d, s
        server.DOCS.clear()


def _undo_all(c, d, s):
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()
    t = s.outline["templates"]["2"]
    assert t["chain"] == ["□", "o", "-", "·"] and t["max"] == 4 and "lift" not in t and not s.outline.get("lifts")
    assert not any(x.get("role") == "table" and x.get("key") == "▦" for x in s.outline["lines"].values())  # 넣은 표 줄(▦) — 헤딩 추출이 잡은 띠 표 줄(「별첨N」 — spec_헤딩_추출 ② §6)은 늘 있다


def _cand(c, d):
    r = c.get(f"/api/docs/{d}/outline/lift", params={"tpl": "2"})
    assert r.status_code == 200, r.text
    return r.json()


def _body_seq(s, pid):
    """pid(본문 줄 · 표 줄)가 든 구역의 문단 열 [(줄 id | 문단 id, 글)] — 표 줄은 호스트 자리에."""
    host = OL.host_of(s.doc, s.outline, pid, s.doc._ids[pid])
    par = host.getparent()
    al = OL.aliases(s.doc, s.outline, par)
    return [(al.get(k) or s.doc._rev.get(k), s.doc._text(s.doc._ids[al[k]]) if k in al else s.doc._text(k)) for k in par.iterchildren(P)]


def test_candidates(sess):
    c, d, s = sess
    o = _cand(c, d)
    assert (o["tpl"], o["no"], o["lifted"], o["first"], o["depth"], o["blocked"]) == ("2", 2, 0, 1, 0, None)
    assert len(o["groups"]) == 1
    g = o["groups"][0]
    assert g["count"] == 1 and not g["lifted"] and g["look"]["font"] and g["look"]["sizePt"] == 16.0
    assert (g["level"], g["new"], g["shape"]) == (1, True, {"rows": 1, "cells": 1, "num": False}) and g["sig"].startswith("▦1x1:") and len(g["was"]) == 1  # 처음 넣는 표 = 새 L1 · 옛 꼴 이름 하나
    tb = g["tables"][0]
    assert tb["text"].startswith("기술준비도(TRL") and tb["table"].startswith("t") and tb["para"].startswith("p")
    assert s.outline["lines"][tb["under"]]["level"] == 1 and s.outline["lines"][tb["under"]]["letter"] == "□" and tb["para"] not in s.outline["lines"]
    # 그 표는 1칸 표이고 제목 문단은 칸 안 문단 — 줄의 본문 자리는 표를 품은 문단
    title = s.doc._ids[tb["para"]]
    host = OL._host_el(s.doc, title)
    assert host is not None and host.getparent() in set(s.doc._sections) and OL.box_of(s.doc, host)[2] is title
    assert OL.box_of(s.doc, s.doc._ids[tb["under"]]) is None  # 글 문단은 제목 표가 아니다
    assert c.get(f"/api/docs/{d}/outline/lift", params={"tpl": "999"}).status_code == 404
    assert c.get(f"/api/docs/{d}/outline/lift", params={"tpl": "1"}).json()["groups"] == []  # 주 사슬(번호형)의 첫 레벨 위에는 제목 표가 없다
    assert s.state()["undo"] == 0


def test_lift_enter_and_rules(sess):
    c, d, s = sess
    before = copy.deepcopy(s.outline)
    g = _cand(c, d)["groups"][0]
    tb = g["tables"][0]
    para, under = tb["para"], tb["under"]
    old_parent = s.outline["lines"][under]["parent"]
    n1 = sum(1 for x in s.outline["lines"].values() if x["tpl"] == "2" and x["level"] == 1)
    r = c.post(f"/api/docs/{d}/outline/lift", json={"tpl": "2"})  # 꼴을 안 주면 표가 가장 많은 꼴
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["lifted"] == {"tid": "2", "no": 2, "sig": g["sig"], "tables": [tb["table"]], "paras": [para], "adopted": o["lifted"]["adopted"], "levels": [2, 5],
                           "level": 1, "new": True, "depth": 1, "more": 0} and o["lifted"]["adopted"] >= 1
    assert o["undo"] == 1 and c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()  # 문서는 안 바뀐다
    ov = s.outline
    t = ov["templates"]["2"]
    assert t["chain"] == ["▦", "□", "o", "-", "·"] and t["max"] == 5 and t["lift"]["sigs"] == [g["sig"]] and t["lift"]["tiers"] == [[g["sig"]]] and ov["lifts"][0]["tid"] == "2"
    assert ov["lifts"][0]["tiers"] == [[g["sig"]]] and ov["lines"][para]["base"] == old_parent
    assert t["slots"]["1"]["table"] and t["slots"]["1"]["rep"] == para and t["slots"]["2"]["letter"] == "□" and t["slots"]["5"]["letter"] == "⋅"
    assert t["slots"]["2"] == before["templates"]["2"]["slots"]["1"]  # 슬롯은 그대로 한 칸씩
    line = ov["lines"][para]
    assert (line["tpl"], line["level"], line["role"], line["letter"], line["key"], line["parent"], line["table"]) == ("2", 1, "table", "", "▦", old_parent, tb["table"])
    assert ov["lines"][under]["level"] == 2 and ov["lines"][under]["parent"] == para and t["lift"]["adopt"][under] == old_parent
    assert sum(1 for x in ov["lines"].values() if x["tpl"] == "2" and x["level"] == 2) == n1 and ov["lines"]["p975"]["level"] == 5  # 그 템플릿의 줄 모두 한 칸씩
    assert all(x["level"] == before["lines"][p]["level"] for p, x in ov["lines"].items() if x["tpl"] != "2")  # 다른 템플릿은 그대로
    # 요약(화면) — 템플릿 번호는 그대로 「T2」 · L1 은 표 제목 레벨(자리 규칙·서식 갈래 없음)
    v = o["outline"]
    assert v["templates"]["2"]["chain"][0] == "▦" and v["templates"]["2"]["max"] == 5 and v["templates"]["2"]["lift"] == {"tables": 1, "sigs": [g["sig"]], "depth": 1}
    sl1 = v["templates"]["2"]["slots"]["1"]
    assert sl1["rooted"] and sl1["table"] and sl1["lines"] == 1 and "at" not in sl1 and v["templates"]["2"]["slots"]["2"]["letter"] == "□"
    assert v["lines"][para] == {"no": 2, "level": 1, "tpl": "2", "letter": "", "role": "table", "key": "▦"} and v["lines"][under]["level"] == 2
    f = c.get(f"/api/docs/{d}/outline/formats").json()["slots"]["2"]
    assert "1" not in f and "2" in f  # 표 제목 레벨은 서식 갈래가 없다
    assert _cand(c, d)["groups"] == [] and _cand(c, d)["lifted"] == 1 and _cand(c, d)["first"] == 2  # 넣은 표는 후보에서 빠진다
    # 표 줄의 Enter = 표 아래(호스트 문단 뒤)에 L2 새 줄 — 제목 글은 그대로
    title = s.doc._text(s.doc._ids[para])
    r = c.post(f"/api/docs/{d}/outline", json={"op": "enter", "id": para, "offset": 3})
    assert r.status_code == 200, r.text
    new = r.json()["outline"]["new"][-1]
    assert r.json()["outline"]["lines"][new] == {"no": 2, "level": 2, "tpl": "2", "letter": "□", "role": "heading", "key": "□"} and r.json()["focus"]["id"] == new
    assert s.doc._text(s.doc._ids[para]) == title and s.outline["lines"][new]["parent"] == para
    seq = _body_seq(s, para)
    i = next(k for k, (q, _) in enumerate(seq) if q == para)
    after = [q for q, t_ in seq[i + 1:i + 6] if t_.strip()]
    assert after[0] == new and seq[next(k for k, (q, _) in enumerate(seq) if q == new)][1] == s.outline["templates"]["2"]["slots"]["2"]["prefix"]  # 표 바로 아래(간격 줄 뒤) · 그 레벨의 접두
    assert s.doc._ids[new].getparent() in set(s.doc._sections)  # 칸 안이 아니라 본문에
    # 거절 — 표 줄은 Enter 만 · 그 아래 L2 줄은 표 레벨로 못 올린다
    for body, word in (({"op": "sibling", "id": para}, "Enter(표 아래에 새 줄)만"), ({"op": "level", "ids": [para], "delta": 1}, "Enter(표 아래에 새 줄)만"),
                       ({"op": "remove", "id": para}, "Enter(표 아래에 새 줄)만"), ({"op": "level", "ids": [under], "delta": -1}, "표 제목 레벨로는 올릴 수 없습니다"),
                       ({"op": "move", "id": under, "target": para, "where": "after"}, "같은 구역·칸 안의 줄로만")):  # 표 줄(칸 안 문단)로는 끌어 놓을 수 없다
        r = c.post(f"/api/docs/{d}/outline", json=body)
        assert r.status_code == 400 and word in r.json()["detail"], (body, r.text)
    # 그 아래 □ 줄을 내리면(L3) 부모는 앞의 L2 줄(새 줄), 다시 올리면(L2) 부모는 표 줄
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": [under], "delta": 1})
    assert r.status_code == 200 and s.outline["lines"][under]["level"] == 3 and s.outline["lines"][under]["parent"] == new
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": [under], "delta": -1})
    assert r.status_code == 200 and s.outline["lines"][under]["level"] == 2 and s.outline["lines"][under]["parent"] == para
    # 제목 글을 고쳐도 표 줄은 남는다(레터가 없는 줄 — 문단이 살아 있는지만 본다)
    r = c.patch(f"/api/docs/{d}/blocks/{para}", json={"text": "고친 제목"})
    assert r.status_code == 200 and s.outline["lines"][para]["role"] == "table"
    _undo_all_keep_text(c, d, s)


def _undo_all_keep_text(c, d, s):
    """실행 취소를 끝까지 — 글 고침(PATCH)은 실행 취소 묶음이 아니라 남는다. 오버레이는 넣기 전으로."""
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")
    t = s.outline["templates"]["2"]
    assert t["chain"] == ["□", "o", "-", "·"] and t["max"] == 4 and "lift" not in t and not s.outline.get("lifts")
    assert not any(x.get("role") == "table" and x.get("key") == "▦" for x in s.outline["lines"].values())  # 넣은 표 줄(▦) — 헤딩 추출이 잡은 띠 표 줄(「별첨N」 — spec_헤딩_추출 ② §6)은 늘 있다
    for pid in [p for p in s.edited()]:  # 고친 제목을 원래대로
        c.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": s.orig_texts[pid]})
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()


def test_unlift_restores_and_grow_together(sess):
    c, d, s = sess
    before = copy.deepcopy(s.outline)
    tb = _cand(c, d)["groups"][0]["tables"][0]
    assert c.post(f"/api/docs/{d}/outline/lift", json={"tpl": "2", "sig": _cand(c, d)["groups"][0]["sig"]}).status_code == 200
    r = c.post(f"/api/docs/{d}/outline/unlift", json={"tpl": "2"})
    assert r.status_code == 200 and r.json()["unlifted"] == {"tpl": "2", "no": 2, "tables": 1} and r.json()["undo"] == 2
    now = copy.deepcopy(s.outline)
    for k in ("seq", "lifts", "rev"):
        now.pop(k, None)
        before.pop(k, None)
    assert now == before  # 떼면 넣기 전 그대로(줄의 부모 · 슬롯 · 사슬 · 가지)
    assert c.post(f"/api/docs/{d}/outline/unlift", json={"tpl": "2"}).status_code == 400  # 넣은 표가 없다
    # 넣은 채로 마지막 레벨에 새 레벨을 더하고(§8-6 — L5 「⋅」 아래 L6) 떼면 더한 레벨도 한 칸 당겨진다
    assert c.post(f"/api/docs/{d}/outline/lift", json={"tpl": "2"}).status_code == 200
    assert c.post(f"/api/docs/{d}/outline/grow/suggest", json={"ids": ["p975"]}).json()["level"] == 6
    r = c.post(f"/api/docs/{d}/outline/grow", json={"ids": ["p975"], "letter": "①"})
    assert r.status_code == 200 and s.outline["templates"]["2"]["chain"] == ["▦", "□", "o", "-", "·", "①"] and s.outline["grows"][0]["level"] == 6
    assert c.post(f"/api/docs/{d}/outline/unlift", json={"tpl": "2"}).status_code == 200
    t = s.outline["templates"]["2"]
    assert t["chain"] == ["□", "o", "-", "·", "①"] and t["max"] == 5 and t["slots"]["5"]["letter"] == "①" and s.outline["grows"][0]["level"] == 5
    assert s.outline["lines"]["p975"]["level"] == 5 and tb["para"] not in s.outline["lines"]
    _undo_all(c, d, s)


def test_carry_after_rerun(sess):
    """2단계를 다시 돌리면(오버레이를 새로 만든다) 표 제목 L1 을 먼저 다시 걸고, 그 뒤에 자리 규칙이 **같은 레벨**로 옮겨진다."""
    c, d, s = sess
    tb = _cand(c, d)["groups"][0]["tables"][0]
    assert c.post(f"/api/docs/{d}/outline/lift", json={"tpl": "2"}).status_code == 200
    s.outline["templates"]["2"]["slots"]["3"]["pos"] = {"line2": "keep", "set": True}  # L3 「o」 에 사람이 정한 자리 규칙
    s.outline["run"] = ["옛 실행", "x"]  # 2단계가 다시 돈 것처럼
    ov = server._outline_ov(s)
    t = ov["templates"]["2"]
    assert ov["run"] != ["옛 실행", "x"] and t["chain"][0] == "▦" and t["max"] == 5 and t["lift"]["sigs"] and ov["lifts"][0]["tid"] == "2"
    assert ov["lines"][tb["para"]]["role"] == "table" and ov["lines"][tb["under"]]["parent"] == tb["para"] and ov["lines"][tb["under"]]["level"] == 2
    assert t["slots"]["3"]["letter"] == "o" and t["slots"]["3"]["pos"] == {"line2": "keep", "set": True} and "pos" not in t["slots"]["4"]
    # 다시 걸 템플릿이 없으면(앵커가 달라짐) 옛 오버레이 사본의 레벨을 되돌려 돌려준다 — 뒤의 carry 들이 레벨을 맞춰 읽게
    old = copy.deepcopy(ov)
    new = copy.deepcopy(ov)
    OL.unlift(new, "2")
    new["templates"]["2"]["anchor"] = "body:다른 앵커"
    got = OL.carry(old, new, s.doc)
    assert got is not old and "lift" not in got["templates"]["2"] and got["templates"]["2"]["slots"]["2"]["pos"] == {"line2": "keep", "set": True}
    assert "lift" in old["templates"]["2"] and "lift" not in new["templates"]["2"]  # old 는 그대로 · new 에는 못 걸었다
    assert OL.carry(None, new, s.doc) is None and OL.carry(old, None, s.doc) is old and OL.carry({"lines": {}}, new, s.doc) == {"lines": {}}
    s.outline = None
    server._outline_ov(s)  # 다음 시험을 위해 새 오버레이(표를 안 넣은 것)
    assert "lift" not in s.outline["templates"]["2"] and s.state()["undo"] == 1
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")


def test_blocked_templates():
    """종속 템플릿 · 서식 종속 템플릿이거나 그런 템플릿이 걸린 템플릿에는 못 넣는다(레벨을 밀면 그 기록의 레벨이 어긋난다)."""
    tp = {"A": {"no": 1, "kind": "main", "anchor": "a", "chain": ["N."], "max": 1, "slots": {"1": {}}},
          "B": {"no": 3, "kind": "branch", "anchor": "b", "chain": ["□"], "max": 1, "slots": {"1": {}}},
          "A+B": {"no": "1T3", "kind": "branch", "anchor": "a>1>b", "chain": ["N.", "□"], "max": 2, "base": 1, "slots": {"2": {}}, "composite": {"parent": "A", "child": "B", "at": 1}},
          "D": {"no": 4, "kind": "branch", "anchor": "d", "chain": ["o"], "max": 1, "slots": {"1": {}}},
          "D~1a": {"no": "4L1a", "kind": "branch", "anchor": "d~L1a", "chain": ["o"], "max": 1, "base": 0, "slots": {"1": {}}, "variant": {"of": "D", "level": 1, "sfx": "a"}},
          "E": {"no": 5, "kind": "branch", "anchor": "e", "chain": ["-"], "max": 1, "slots": {"1": {}}}}
    ov = {"lines": {}, "templates": tp}
    assert "종속 템플릿입니다" in OL._blocked(ov, "A+B") and "종속 템플릿입니다" in OL._blocked(ov, "D~1a")
    assert "T1T3" in OL._blocked(ov, "A") and "T1T3" in OL._blocked(ov, "B") and "T4L1a" in OL._blocked(ov, "D") and OL._blocked(ov, "E") is None
    with pytest.raises(ValueError, match="종속 템플릿"):
        OL.lift(None, ov, "A")
    with pytest.raises(KeyError):
        OL.lift(None, ov, "없음")
    with pytest.raises(ValueError, match="넣은 표가 없습니다"):
        OL.unlift(ov, "E")
    assert OL._first_level(tp["E"]) == 1 and OL._first_level(tp["A+B"]) == 2 and OL._first_level({**tp["E"], "lift": {"sigs": []}}) == 2
    assert OE.lift_depth(tp["E"]) == 0 and OE.lift_depth({"lift": {"sigs": ["x"]}}) == 1 and OE.lift_depth({"lift": {"tiers": [["a"], ["b"]]}}) == 2  # 옛 기록(층 목록 없음)은 한 층


# ---------------------------------------------------------------- 넓힘 — 여러 칸·3행 제목 표 · 표 레벨 여러 층(② §8-7 「넓힘」)
_spec = importlib.util.spec_from_file_location("title_tables_doc", ROOT / "tools" / "title_tables_doc.py")  # 시험 문서 만들기 — 화면 검사(tools/smoke_outline_lift_ui.py)와 함께 쓴다
TD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TD)
_cell_paras, _tiered_bytes = TD.cell_paras, TD.build  # 본문 차례: 3행 표(위 칸에 제목) · 띠 「1 .|띠 제목 1」 · 띠 「2 .|띠 제목 2」 · 1칸 상자 · □ 줄 / 띠 「3 .|띠 제목 3」 · □ 줄


def test_title_table_shapes():
    """제목 표의 뼈대와 꼴 — 1칸 상자 · 번호 칸 + 제목 칸 띠 · 3행 표 · 제목 표가 아닌 것(두 칸인데 번호 칸 없음 · 글 있는 칸 셋 · 긴 글)."""
    doc = HwpxDoc(_tiered_bytes())
    hosts = [k for sec in doc._sections for k in sec.iterchildren(P) if OL.title_of(doc, k)]
    infos = [OL.title_of(doc, k) for k in hosts]
    assert [(i["rows"], i["cells"], i["at"], i["numAt"]) for i in infos] == [(3, [1, 1, 1], 0, None), (1, [2], 1, 0), (1, [2], 1, 0), (1, [1], 0, None), (1, [2], 1, 0)]
    assert [doc._text(i["num"]) if i["num"] is not None else None for i in infos] == [None, "1 .", "2 .", None, "3 ."] and doc._text(infos[1]["title"]) == "띠 제목 1"
    sigs = [OL.sig_of(doc, i) for i in infos]
    assert sigs[1] == sigs[2] == sigs[4] and sigs[1].startswith("▦1x2n:") and sigs[0].startswith("▦3x1:") and sigs[3].startswith("▦1x1:") and len(set(sigs)) == 3
    assert [OL.legacy_sig(doc, i) is not None for i in infos] == [False, False, False, True, False]  # 옛 꼴 이름은 1칸 상자만
    assert OL.box_of(doc, hosts[1]) == (infos[1]["tbl"], infos[1]["cell"], infos[1]["title"])
    for ok in ("1 .", "3.1", "3-1.", "Ⅱ", "IV.", "가.", "A)", "(2)", "①", "제2장", "12"):
        assert OL.NUM.fullmatch(ok), ok
    for no in ("운영", "2027년", "가", "1분기", "3.1.2.3.4.5"):
        assert not OL.NUM.fullmatch(no), no
    band = _cell_paras(doc, infos[1]["tbl"])
    doc.set_text(doc._id(band[0][0]), "구분")  # 두 칸인데 번호 칸이 없다 — 제목 + 내용 상자
    assert OL.title_of(doc, hosts[1]) is None
    doc.set_text(doc._id(band[0][0]), "1 .")
    doc.set_text(doc._id(band[1][0]), "긴 글 " * 60)  # 200자 넘는 글 — 본문을 담은 상자
    assert OL.title_of(doc, hosts[1]) is None
    rows3 = _cell_paras(doc, infos[0]["tbl"])
    doc.set_text(doc._id(rows3[1][0]), "2 .")  # 3행 표의 다른 행에 글 — 두 칸이 다른 행
    assert OL.title_of(doc, hosts[0]) is None
    doc.set_text(doc._id(rows3[2][0]), "셋째")  # 글 있는 칸이 셋
    assert OL.title_of(doc, hosts[0]) is None


@pytest.fixture(scope="module")
def tiered(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("outline_lift_tiers")
    data = _tiered_bytes()
    with pytest.MonkeyPatch.context() as mp:
        for k, v in {"NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": tmp / "works", "NFM_RENDER": tmp / "render",
                     "NFM_HEADINGS": tmp / "heads", "NFM_FORMS": tmp / "forms", "NFM_DIVISION_PRESETS": tmp / "presets.json"}.items():
            mp.setenv(k, str(v))
        server.DOCS.clear()
        c = TestClient(server.app, raise_server_exceptions=False)
        r = c.post("/api/docs", files={"file": ("제목표_층.hwpx", data, "application/octet-stream")})
        assert r.status_code == 200, r.text
        d = r.json()["docId"]
        s = server.DOCS[d]
        heading_runs.run_sync(s, 1, False)
        heading_runs.run_sync(s, 2, False)
        assert c.get(f"/api/docs/{d}/outline").status_code == 200
        yield c, d, s, data
        server.DOCS.clear()


def _snap_of(ov):
    """T2 의 줄마다 (레벨, 부모, 역할)."""
    return {p: (x["level"], x["parent"], x.get("role")) for p, x in ov["lines"].items() if x["tpl"] == "2"}


def _snap(s):
    """T2 의 줄 + 사슬 · 층."""
    t = s.outline["templates"]["2"]
    return _snap_of(s.outline), list(t["chain"]), [list(x) for x in (t.get("lift") or {}).get("tiers", [])]


def _lift(c, d, sig):
    r = c.post(f"/api/docs/{d}/outline/lift", json={"tpl": "2", "sig": sig})
    assert r.status_code == 200, r.text
    return r.json()


def _undo_tiered(c, d, s, data):
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")
    assert c.get(f"/api/docs/{d}/download").content == data
    assert "lift" not in s.outline["templates"]["2"] and not any(x.get("role") == "table" and x.get("key") == "▦" for x in s.outline["lines"].values())


def test_tiers_inner_first(tiered):
    """상자(□ 위) → 띠(상자 위 — 꼴이 같은 다른 띠도) → 3행 표(띠 위): 층마다 레벨 · 부모 · 표 줄의 Enter · 떼기."""
    c, d, s, data = tiered
    before = copy.deepcopy(s.outline)
    o = _cand(c, d)
    assert [(g["shape"], g["count"], g["level"], g["new"], g["lifted"]) for g in o["groups"]] == [
        ({"rows": 1, "cells": 2, "num": True}, 3, 1, True, False), ({"rows": 1, "cells": 1, "num": False}, 1, 1, True, False)]  # 3행 표는 닻이 없다(띠가 아직 줄이 아님)
    band, box = o["groups"]
    assert [t["num"] for t in band["tables"]] == ["1 .", "2 .", "3 ."] and [t["text"] for t in band["tables"]] == ["띠 제목 1", "띠 제목 2", "띠 제목 3"]
    assert [t["under"] is None for t in band["tables"]] == [True, True, False] and band["was"] == [] and len(box["was"]) == 1  # 닻은 셋째 띠(□ 위) 하나 — 꼴이 같아 셋이 한 묶음
    b1, b2, b3 = (t["para"] for t in band["tables"])
    xp, u1, u2 = box["tables"][0]["para"], box["tables"][0]["under"], band["tables"][2]["under"]
    root = s.outline["lines"][u1]["parent"]
    assert s.outline["lines"][u2]["parent"] == root and u1 != u2
    # ① 상자 — 새 L1
    r = _lift(c, d, box["sig"])["lifted"]
    assert (r["level"], r["new"], r["depth"], r["levels"], r["more"]) == (1, True, 1, [2, 5], 1)
    assert s.outline["lines"][u1]["parent"] == xp and s.outline["lines"][u2]["parent"] == root  # 띠 「3 .」 은 아직 줄이 아니다 — 그 아래 □ 는 그대로
    g = _cand(c, d)["groups"]
    assert len(g) == 1 and (g[0]["sig"], g[0]["count"], g[0]["level"], g[0]["new"]) == (band["sig"], 3, 1, True)  # 띠 「2 .」 가 상자(L1 표 줄) 바로 위 → 그 위에 새 레벨
    assert [t["under"] for t in g[0]["tables"]] == [None, xp, u2]
    # ② 띠 — 새 L1(상자는 L2 · □ 는 L3)
    r = _lift(c, d, band["sig"])
    assert (r["lifted"]["level"], r["lifted"]["new"], r["lifted"]["depth"], r["lifted"]["levels"], r["lifted"]["more"], r["lifted"]["paras"]) == (1, True, 2, [3, 6], 1, [b1, b2, b3])
    ov = s.outline
    t = ov["templates"]["2"]
    assert t["chain"] == ["▦", "▦", "□", "o", "-", "·"] and t["max"] == 6 and t["lift"]["tiers"] == [[band["sig"]], [box["sig"]]] and t["lift"]["sigs"] == [band["sig"], box["sig"]]
    assert ov["lifts"][0]["tiers"] == t["lift"]["tiers"] and t["slots"]["1"]["table"] and t["slots"]["2"]["table"] and t["slots"]["3"]["letter"] == "□"
    assert (t["slots"]["1"]["count"], t["slots"]["1"]["rep"], t["slots"]["2"]["count"], t["slots"]["2"]["rep"]) == (3, b1, 1, xp)
    L = ov["lines"]
    assert [L[p]["level"] for p in (b1, b2, b3, xp, u1, u2)] == [1, 1, 1, 2, 3, 3]
    assert [L[p]["parent"] for p in (b1, b2, b3, xp, u1, u2)] == [root, root, root, b2, xp, b3]  # 상자는 가장 가까운 앞 띠 아래 · 띠 「3 .」 아래 □ 는 그 띠 아래(L1 → L3)
    assert L[b1]["num"] and L[b1]["num"] != b1 and "num" not in L[xp] and L[b1]["base"] == root and L[xp]["base"] == root
    v = r["outline"]["templates"]["2"]
    assert v["lift"] == {"tables": 4, "sigs": [band["sig"], box["sig"]], "depth": 2} and v["slots"]["1"]["table"] and v["slots"]["2"]["table"] and v["slots"]["3"]["letter"] == "□"
    assert r["outline"]["lines"][b2] == {"no": 2, "level": 1, "tpl": "2", "letter": "", "role": "table", "key": "▦"} and r["outline"]["lines"][xp]["level"] == 2
    f = c.get(f"/api/docs/{d}/outline/formats").json()["slots"]["2"]
    assert "1" not in f and "2" not in f and "3" in f  # 표 제목 레벨은 서식 갈래가 없다
    # ③ 3행 표(띠 「1 .」 위) — 새 L1
    g = _cand(c, d)["groups"]
    assert len(g) == 1 and (g[0]["shape"], g[0]["count"], g[0]["level"], g[0]["new"], g[0]["tables"][0]["under"]) == ({"rows": 3, "cells": 3, "num": False}, 1, 1, True, b1)
    r3 = g[0]["tables"][0]["para"]
    r = _lift(c, d, g[0]["sig"])["lifted"]
    assert (r["level"], r["depth"], r["levels"], r["more"]) == (1, 3, [4, 7], 0)
    L = s.outline["lines"]
    assert [L[p]["level"] for p in (r3, b1, b2, b3, xp, u1, u2)] == [1, 2, 2, 2, 3, 4, 4]
    assert [L[p]["parent"] for p in (r3, b1, b2, b3, xp, u1, u2)] == [root, r3, r3, r3, b2, xp, b3]
    assert _cand(c, d)["groups"] == [] and _cand(c, d)["lifted"] == 5 and _cand(c, d)["depth"] == 3 and _cand(c, d)["first"] == 4
    # 표 줄의 Enter = 표 아래에 **첫 글 레벨**(L4) 새 줄 — 띠(L2)에서 눌러도(그 사이 L3 은 표 레벨)
    r = c.post(f"/api/docs/{d}/outline", json={"op": "enter", "id": b3, "offset": 0})
    assert r.status_code == 200, r.text
    new = r.json()["outline"]["new"][-1]
    assert r.json()["outline"]["lines"][new] == {"no": 2, "level": 4, "tpl": "2", "letter": "□", "role": "heading", "key": "□"} and s.outline["lines"][new]["parent"] == b3
    assert s.doc._ids[new].getparent() in set(s.doc._sections) and s.doc._text(s.doc._ids[b3]) == "띠 제목 3"
    for body, word in (({"op": "level", "ids": [u1], "delta": -1}, "표 제목 레벨로는 올릴 수 없습니다"), ({"op": "sibling", "id": b1}, "Enter(표 아래에 새 줄)만"),
                       ({"op": "level", "ids": [xp], "delta": 1}, "Enter(표 아래에 새 줄)만")):
        r = c.post(f"/api/docs/{d}/outline", json=body)
        assert r.status_code == 400 and word in r.json()["detail"], (body, r.text)
    assert c.post(f"/api/docs/{d}/undo").status_code == 200 and new not in s.outline["lines"]  # Enter 되돌림
    # 떼기 = 표 레벨 모두 — 넣기 전 그대로
    r = c.post(f"/api/docs/{d}/outline/unlift", json={"tpl": "2"})
    assert r.status_code == 200 and r.json()["unlifted"] == {"tpl": "2", "no": 2, "tables": 5}
    now = copy.deepcopy(s.outline)
    for k in ("seq", "lifts", "rev"):
        now.pop(k, None)
        before.pop(k, None)
    assert now == before
    _undo_tiered(c, d, s, data)


def test_tiers_order_independent(tiered):
    """넣는 차례와 무관 — 띠를 먼저 넣으면(닻 = □ 위의 띠 「3 .」) 상자는 띠와 □ 사이에 **새 L2** 로 끼어든다: 상자 → 띠 차례와 같은 결과."""
    c, d, s, data = tiered
    band, box = _cand(c, d)["groups"]
    b2, b3 = band["tables"][1]["para"], band["tables"][2]["para"]
    xp, u1, u2 = box["tables"][0]["para"], box["tables"][0]["under"], band["tables"][2]["under"]
    root = s.outline["lines"][u1]["parent"]
    _lift(c, d, box["sig"])
    _lift(c, d, band["sig"])
    want = _snap(s)
    _undo_tiered(c, d, s, data)
    r = _lift(c, d, band["sig"])["lifted"]  # 띠부터
    assert (r["level"], r["new"], r["depth"], r["more"]) == (1, True, 1, 2)  # 더 넣을 것 = 상자(띠 아래) · 3행 표(띠 「1 .」 위)
    L = s.outline["lines"]
    assert L[u2]["parent"] == b3 and L[u1]["parent"] == root  # 상자(안 넣은 제목 표)가 띠 「2 .」 와 □ 사이를 끊는다
    g = {x["sig"]: x for x in _cand(c, d)["groups"]}
    assert len(g) == 2 and (g[box["sig"]]["level"], g[box["sig"]]["new"], g[box["sig"]]["tables"][0]["under"]) == (2, True, u1)  # 위는 띠(L1 표 줄) · 아래는 □(L2) — 그 사이에 새 레벨
    top = next(x for k, x in g.items() if k != box["sig"])
    assert (top["shape"]["rows"], top["level"], top["new"]) == (3, 1, True)  # 3행 표는 띠 위의 새 L1
    r = _lift(c, d, box["sig"])["lifted"]
    assert (r["level"], r["new"], r["depth"], r["levels"]) == (2, True, 2, [3, 6])
    assert _snap(s) == want and s.outline["lines"][xp]["parent"] == b2 and s.outline["templates"]["2"]["lift"]["tiers"] == [[band["sig"]], [box["sig"]]]
    # 이미 넣은 꼴의 표는 그 꼴의 레벨로(「에 더 넣기」) — 띠 줄 하나를 빼 두면 후보로 다시 나온다
    gone = s.outline["lines"].pop(b3)
    again = next(x for x in _cand(c, d)["groups"] if x["sig"] == band["sig"])
    assert (again["lifted"], again["level"], again["new"], again["count"], again["tables"][0]["para"]) == (True, 1, False, 1, b3)
    s.outline["lines"][b3] = gone
    _undo_tiered(c, d, s, data)


def test_carry_tiers_and_old_names(tiered):
    """2단계를 다시 돌리면 기록한 층을 안쪽부터 다시 건다 · 옛 기록(층 목록 없음 · 1칸 꼴의 옛 이름)도 지금 꼴로 읽는다."""
    c, d, s, data = tiered
    band, box = _cand(c, d)["groups"]
    _lift(c, d, box["sig"])
    _lift(c, d, band["sig"])
    want = _snap(s)
    s.outline["run"] = ["옛 실행", "x"]  # 2단계가 다시 돈 것처럼
    ov = server._outline_ov(s)
    assert ov["run"] != ["옛 실행", "x"] and _snap(s) == want and ov["lifts"][0]["tiers"] == [[band["sig"]], [box["sig"]]]
    # 옛 기록 — 한 층 · 옛 꼴 이름 · base 없는 표 줄
    old = copy.deepcopy(ov)
    OL.unlift(old, "2")
    OL.lift(s.doc, old, "2", box["sig"])
    t = old["templates"]["2"]
    t["lift"].pop("tiers")
    t["lift"]["sigs"] = list(box["was"])
    old["lifts"] = [{"anchor": t["anchor"], "tid": "2", "sigs": list(box["was"]), "n": t["lift"]["n"]}]
    for x in old["lines"].values():
        x.pop("base", None)
    assert OE.lift_depth(t) == 1 and OL._first_level(t) == 2
    g = OL.candidates(s.doc, old, "2")  # 옛 기록 위에서도 띠는 상자(L1 표 줄) 위의 새 레벨
    assert [(x["sig"], x["level"], x["new"]) for x in g] == [(band["sig"], 1, True)]
    new = copy.deepcopy(old)
    OL.unlift(new, "2")
    assert OL.carry(old, new, s.doc) is old  # 다시 건 층 수가 같다 — 옛 오버레이 그대로
    assert new["templates"]["2"]["lift"]["tiers"] == [[box["sig"]]] and new["lifts"][0]["sigs"] == [box["sig"]]  # 옛 이름으로 찾아 새 이름으로 적는다
    OL.lift(s.doc, old, "2", band["sig"])  # 옛 기록에 층을 더해도 부모가 맞는다(base 를 채운다)
    assert _snap_of(old) == want[0] and old["templates"]["2"]["lift"]["tiers"] == [[band["sig"]], list(box["was"])]  # 상자의 옛 이름은 그 꼴을 다시 넣을 때 바뀐다 — 그때까지는 옛 이름으로 읽는다
    assert OL.candidates(s.doc, old, "2")[0]["shape"]["rows"] == 3 and len(OL.candidates(s.doc, old, "2")) == 1
    # 다시 건 층 수가 다르면(띠가 없어짐) 옛 오버레이 사본의 레벨을 새것에 맞춘다
    two = copy.deepcopy(ov)
    two["lifts"][0]["tiers"] = [["없는 꼴"], [box["sig"]]]
    new = copy.deepcopy(ov)
    OL.unlift(new, "2")
    got = OL.carry(two, new, s.doc)
    assert got is not two and OE.lift_depth(new["templates"]["2"]) == 1 and "lift" not in got["templates"]["2"]
    assert got["templates"]["2"]["chain"] == new["templates"]["2"]["chain"] and set(got["templates"]["2"]["slots"]) == set(new["templates"]["2"]["slots"])
    s.outline = None
    server._outline_ov(s)
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")

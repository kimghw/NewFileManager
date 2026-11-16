"""표 제목을 템플릿의 L1 으로(spec_hwpx_웹편집 ② §8-7 — app/outline_lift.py · app/outline_lift_api.py · outline_edit 의 표 줄 가지).
연구개발계획서 양식(2단계 LLM 끔): 가지 템플릿 T2 「□›o›-›·」 의 첫 레벨 줄 하나 바로 위에 1칸 제목 상자 「기술준비도(TRL, …」 가 있다.
후보(같은 꼴 묶음) · 넣기(레벨 한 칸 밀기 · 표 줄 · 그 아래 줄의 부모 · 요약) · 표 줄의 Enter = 표 아래 L2 새 줄 · 거절(Alt+Enter·레벨·지우기 · 표 레벨로 올리기) ·
아래 줄의 레벨 바꿈이 표 줄을 부모로 · 제목 글을 고쳐도 줄이 남음 · 더한 레벨(§8-6)과 함께 · 떼기 = 넣기 전 그대로 · 실행 취소 · 2단계 다시 실행 뒤 다시 걸기 · 못 넣는 템플릿."""
import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs
from app import outline_lift as OL
from app import server
from app.hwpx_doc import P

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
    assert not any(x.get("role") == "table" for x in s.outline["lines"].values())


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
    assert (o["tpl"], o["no"], o["lifted"], o["first"], o["blocked"]) == ("2", 2, 0, 1, None)
    assert len(o["groups"]) == 1
    g = o["groups"][0]
    assert g["count"] == 1 and not g["lifted"] and g["look"]["font"] and g["look"]["sizePt"] == 16.0
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
    assert o["lifted"] == {"tid": "2", "no": 2, "sig": g["sig"], "tables": [tb["table"]], "paras": [para], "adopted": o["lifted"]["adopted"], "levels": [2, 5]} and o["lifted"]["adopted"] >= 1
    assert o["undo"] == 1 and c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()  # 문서는 안 바뀐다
    ov = s.outline
    t = ov["templates"]["2"]
    assert t["chain"] == ["▦", "□", "o", "-", "·"] and t["max"] == 5 and t["lift"]["sigs"] == [g["sig"]] and ov["lifts"][0]["tid"] == "2"
    assert t["slots"]["1"]["table"] and t["slots"]["1"]["rep"] == para and t["slots"]["2"]["letter"] == "□" and t["slots"]["5"]["letter"] == "⋅"
    assert t["slots"]["2"] == before["templates"]["2"]["slots"]["1"]  # 슬롯은 그대로 한 칸씩
    line = ov["lines"][para]
    assert (line["tpl"], line["level"], line["role"], line["letter"], line["key"], line["parent"], line["table"]) == ("2", 1, "table", "", "▦", old_parent, tb["table"])
    assert ov["lines"][under]["level"] == 2 and ov["lines"][under]["parent"] == para and t["lift"]["adopt"][under] == old_parent
    assert sum(1 for x in ov["lines"].values() if x["tpl"] == "2" and x["level"] == 2) == n1 and ov["lines"]["p975"]["level"] == 5  # 그 템플릿의 줄 모두 한 칸씩
    assert all(x["level"] == before["lines"][p]["level"] for p, x in ov["lines"].items() if x["tpl"] != "2")  # 다른 템플릿은 그대로
    # 요약(화면) — 템플릿 번호는 그대로 「T2」 · L1 은 표 제목 레벨(자리 규칙·서식 갈래 없음)
    v = o["outline"]
    assert v["templates"]["2"]["chain"][0] == "▦" and v["templates"]["2"]["max"] == 5 and v["templates"]["2"]["lift"] == {"tables": 1, "sigs": [g["sig"]]}
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
    assert not any(x.get("role") == "table" for x in s.outline["lines"].values())
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

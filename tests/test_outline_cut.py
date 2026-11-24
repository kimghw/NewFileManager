"""자리로 나누기 — 「여기부터 새 템플릿으로」(spec_hwpx_웹편집 ② §8-13 — app/outline_match.py `cut` · `cut_view` · `cut_block` · outline_match_api.py `…/outline/cut`).
연구개발계획서 양식 + 2단계(LLM 끔): T1 「N. › N-N. › (N) › o › -」 L4 「o」 22줄(대표 p5208) · 그 아래 L5 「-」 15줄 / T5 「가. › (N)」 L1 = 번호형 / T24 = 띠 표.
astra 검토(artifacts/tpl_cut_astra_2026-11-23)의 반례를 시험으로: 더 넣은 것의 차례 · 안쪽 템플릿을 합친 뒤의 소속 · 새로 잡힌 줄을 데려가지 않음 · 나눈 템플릿에서 만든 형제 · 레벨의 레터가 달라짐."""
import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs
from app import outline_edit as OE
from app import outline_match as M
from app import server

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
    tmp = tmp_path_factory.mktemp("outline_cut")
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
    assert not s.outline.get("splits")


def _lines(ov, tid, level=None):
    return [p for p, x in ov["lines"].items() if x["tpl"] == str(tid) and (level is None or x["level"] == level)]


def _cut(c, d, paras, tid, level, scope, into=None):
    return c.post(f"/api/docs/{d}/outline/cut", json={"paras": paras, "tpl": str(tid), "level": level, "scope": scope, **({"into": into} if into else {})})


def _fresh(s):
    """2단계를 다시 돌린 것과 같은 새 오버레이(같은 그래프)."""
    return OE.build_overlay(heading_runs.graph(s), server._outline_probe(s), rev=s.rev)


def _where(ov):
    return {p: (x["tpl"], x["level"]) for p, x in ov["lines"].items()}


def _reps(ov):
    """자리로 나눈 템플릿과 그 원래 템플릿의 슬롯 대표 — 대표가 제 템플릿 · 제 레벨의 줄인가도 본다(다른 템플릿의 줄을 가리키면 「대표 맞추기」 가 400)."""
    out = {}
    for tid, t in ov["templates"].items():
        if (t.get("variant") or {}).get("cut") or any((o.get("variant") or {}).get("of") == tid and (o["variant"].get("cut")) for o in ov["templates"].values()):
            for k, sl in t["slots"].items():
                x = ov["lines"].get(sl.get("rep")) if sl.get("rep") else None
                assert x is None or (x["tpl"] == tid and str(x["level"]) == k), (tid, k, sl.get("rep"), x)
                out[(tid, k)] = sl.get("rep")
    return out


def _carry(s, old=None, ov=None):
    """서버가 다시 분석한 뒤에 하는 것과 같이 — 새 오버레이에 옛 오버레이의 나누기를 다시 건다. -> (새 오버레이, 못 건 것)."""
    ov = ov if ov is not None else _fresh(s)
    return ov, M.carry(old if old is not None else s.outline, ov, M.context(s.doc, ov), doc=s.doc)


def _view(c, d, *paras):
    r = c.get(f"/api/docs/{d}/outline/cut", params={"paras": ",".join(paras)})
    assert r.status_code == 200, r.text
    return r.json()


def test_cut_here_and_all_and_unsplit(sess):
    """여기서만(대표 줄이어도) · 더 넣기 · 모두(대표 · 자리 규칙 · 대표의 출처가 옮겨 간다) · 합치면 대표가 돌아온다 — 문서는 안 바뀐다."""
    c, d, s = sess
    A0 = copy.deepcopy(s.outline["templates"]["1"])
    rep, n4, n5 = A0["slots"]["4"]["rep"], len(_lines(s.outline, 1, 4)), len(_lines(s.outline, 1, 5))
    kids = len(M._members(s.outline, "1", [rep])) - 1
    v = c.get(f"/api/docs/{d}/outline/cut", params={"paras": rep}).json()
    assert v["no"] == 1 and v["level"] == 4 and v["next"] == "1L4a" and v["made"] == [] and v["back"] is None and not v["table"] and not v["numbered"]
    assert {k: v["here"][k] for k in ("lines", "moved", "why")} == {"lines": 1, "moved": 1 + kids, "why": None}
    assert {k: v["all"][k] for k in ("lines", "moved", "why")} == {"lines": n4, "moved": n4 + n5, "why": None} and v["here"]["sig"] != v["all"]["sig"]
    # 메뉴가 보인 계획(sig)과 실행할 때의 계획이 다르면 하지 않는다 — 줄 수가 같아도(다른 줄 · 그 사이 나눈 템플릿)
    stale = c.post(f"/api/docs/{d}/outline/cut", json={"paras": [rep], "tpl": "1", "level": 4, "scope": "here", "sig": v["all"]["sig"]})
    assert stale.status_code == 409 and "다시 눌러" in stale.json()["detail"] and not s.outline.get("splits")
    assert c.post(f"/api/docs/{d}/outline/cut", json={"paras": [rep], "tpl": "1", "level": 4, "scope": "here", "sig": 3}).status_code == 400
    # 여기서만 — 대표 서식의 줄(대표 줄 그 자체)도 나눈다: 서식 떼기(split)는 400
    assert c.post(f"/api/docs/{d}/outline/slots/1/4/split", json={"likes": [rep]}).status_code == 400
    s.outline["templates"]["1"]["slots"]["4"]["pos"] = {"line2": "text"}  # 사람이 정한 자리 규칙(시험이 직접 적는다 — 끝에서 지운다) — 자리로 나누면 따라간다
    r = c.post(f"/api/docs/{d}/outline/cut", json={"paras": [rep], "tpl": "1", "level": 4, "scope": "here", "sig": _view(c, d, rep)["here"]["sig"]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["cut"] == {"id": "1~4a", "no": "1L4a", "of": 1, "level": 4, "scope": "here", "lines": 1, "moved": 1 + kids, "added": False} and j["undo"] >= 1
    C = s.outline["templates"]["1~4a"]
    assert C["base"] == 3 and sorted(C["slots"]) == ["4", "5"] and C["variant"] == {"of": "1", "level": 4, "sfx": "a", "cut": "here"}
    assert C["slots"]["4"]["rep"] == rep and C["slots"]["4"]["pos"] == {"line2": "text"} and "repSet" not in C["slots"]["4"]
    a4 = s.outline["templates"]["1"]["slots"]["4"]
    assert a4["rep"] in _lines(s.outline, 1, 4) and a4["rep"] != rep and a4["prefix"] == A0["slots"]["4"]["prefix"]  # A 의 대표는 남은 줄로 · 동결 모양은 그대로
    assert j["outline"]["templates"]["1~4a"]["vari"]["cut"] == "here" and s.outline["lines"][rep]["no"] == "1L4a"
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()
    # 더 넣기 — 기록은 따로 한 건(add · 제 차례)
    other = _lines(s.outline, 1, 4)[0]
    v = c.get(f"/api/docs/{d}/outline/cut", params={"paras": other}).json()
    assert v["next"] == "1L4b" and [(m["no"], m["why"]) for m in v["made"]] == [("1L4a", None)]
    r = _cut(c, d, [other], 1, 4, "here", into="1~4a")
    assert r.status_code == 200 and r.json()["cut"]["added"] and r.json()["cut"]["no"] == "1L4a"
    assert [(m["id"], m["cut"], bool(m.get("add")), m["n"]) for m in s.outline["splits"]] == [("1~4a", "here", False, 1), ("1~4a", "here", True, 2)]
    assert C["slots"]["4"]["rep"] == rep  # 그 템플릿의 대표 그대로
    # 모두 — 남은 T1 L4 줄 전부: 대표 · 자리 규칙이 옮겨 가고 A 의 그 레벨은 대표 없이 동결 모양만
    a_rep = s.outline["templates"]["1"]["slots"]["4"]["rep"]
    s.outline["templates"]["1"]["slots"]["4"]["repSet"] = True  # 사람이 정한 대표 — 출처도 옮겨 간다
    left = len(_lines(s.outline, 1, 4))
    r = _cut(c, d, [_lines(s.outline, 1, 4)[-1]], 1, 4, "all")
    assert r.status_code == 200, r.text
    assert r.json()["cut"]["no"] == "1L4b" and r.json()["cut"]["lines"] == left and r.json()["cut"]["scope"] == "all"
    B = s.outline["templates"]["1~4b"]
    assert B["slots"]["4"]["rep"] == a_rep and B["slots"]["4"]["repSet"] and B["slots"]["4"]["pos"] == {"line2": "text"} and B["variant"]["cut"] == "all"
    A = s.outline["templates"]["1"]
    assert A["slots"]["4"]["rep"] is None and "repSet" not in A["slots"]["4"] and A["slots"]["4"]["prefix"] == A0["slots"]["4"]["prefix"]
    assert A["slots"]["5"]["rep"] is None and not _lines(s.outline, 1, 4) and not _lines(s.outline, 1, 5)
    assert [x["no"] for x in r.json()["outline"]["templates"]["1"]["splits"]] == ["1L4a", "1L4b"]
    # 빈 레벨이 있어도 서식 목록 · 템플릿 전체 맞추기가 돈다(대표가 다른 템플릿의 줄을 가리키지 않는다)
    assert c.get(f"/api/docs/{d}/outline/formats").status_code == 200
    r = c.post(f"/api/docs/{d}/outline/templates/1/match", json={})
    assert r.status_code == 200, r.text
    c.post(f"/api/docs/{d}/undo")
    # 나눈 템플릿의 줄에서 — 합치기(back) · 그 안에서 다시 나누기
    v = c.get(f"/api/docs/{d}/outline/cut", params={"paras": a_rep}).json()
    assert v["no"] == "1L4b" and v["next"] == "1L4bL4a" and v["back"] == {"id": "1~4b", "no": "1L4b", "ofNo": 1, "lines": len(_lines(s.outline, "1~4b")), "cut": "all", "why": None}
    _reps(s.outline)
    r = c.post(f"/api/docs/{d}/outline/unsplit", json={"id": "1~4b"})
    assert r.status_code == 200, r.text
    A = s.outline["templates"]["1"]
    assert A["slots"]["4"]["rep"] == a_rep and A["slots"]["4"]["repSet"] and A["slots"]["5"]["rep"] in _lines(s.outline, 1, 5)  # 대표 · 출처가 돌아온다
    assert c.post(f"/api/docs/{d}/outline/unsplit", json={"id": "1~4a"}).status_code == 200
    assert len(_lines(s.outline, 1, 4)) == n4 and len(_lines(s.outline, 1, 5)) == n5 and not s.outline["splits"]
    _undo_all(c, d, s)
    assert s.outline["templates"]["1"]["slots"]["4"]["rep"] == rep
    s.outline["templates"]["1"]["slots"]["4"].pop("pos", None)


def test_cut_checks(sess):
    """못 하는 것 — 꼴 · 소속이 바뀐 줄(409) · 띠 표 · 번호형 레벨은 같은 번호 묶음이 함께 · 넣은 뒤 정리가 만든 템플릿에는 더 넣지 않는다."""
    c, d, s = sess
    rep = s.outline["templates"]["1"]["slots"]["4"]["rep"]
    assert _cut(c, d, [rep], 1, 4, "some").status_code == 400
    assert _cut(c, d, [], 1, 4, "here").status_code == 400
    assert c.post(f"/api/docs/{d}/outline/cut", json={"paras": [rep], "tpl": "1", "scope": "here"}).status_code == 400
    assert _cut(c, d, [rep], 1, 3, "here").status_code == 409 and _cut(c, d, [rep], 2, 4, "here").status_code == 409  # 메뉴가 보인 것과 다른 소속
    assert _cut(c, d, ["p-none"], 1, 4, "here").status_code == 409
    assert c.get(f"/api/docs/{d}/outline/cut", params={"paras": "p-none"}).status_code == 404
    band = next(tid for tid, t in s.outline["templates"].items() if t.get("kind") == OE.BAND)
    b1 = _lines(s.outline, band, 1)[0]
    v = c.get(f"/api/docs/{d}/outline/cut", params={"paras": b1}).json()
    assert v["here"]["why"] == M.CUT_BAND == v["all"]["why"] and v["table"]
    r = _cut(c, d, [b1], band, 1, "here")
    assert r.status_code == 400 and "별첨" in r.json()["detail"]
    # 번호형 — 「가.」: 같은 (부모, 표) 형제가 함께 간다
    units = M.split_units(s.outline, "5", 1, s.doc)
    one = next(p for p in units if sum(1 for q in units if units[q] == units[p]) > 1)
    sibs = [q for q in units if units[q] == units[one]]
    v = c.get(f"/api/docs/{d}/outline/cut", params={"paras": one}).json()
    assert v["numbered"] and v["here"]["lines"] == len(sibs) and v["here"]["why"] is None
    r = _cut(c, d, [one], 5, 1, "here")
    assert r.status_code == 200 and r.json()["cut"]["lines"] == len(sibs) and sorted(_lines(s.outline, "5~1a", 1)) == sorted(sibs)
    c.post(f"/api/docs/{d}/undo")
    # 한 라벨의 줄 여럿(표 한 행의 칸들 — 「×2」): 그 줄 모두가 「여기서만」
    two = _lines(s.outline, 1, 4)[:2]
    r = _cut(c, d, two, 1, 4, "here")
    assert r.status_code == 200 and r.json()["cut"]["lines"] == 2
    # 기능이 쪽을 골라 뗀 템플릿(by)에는 더 넣지 않는다
    s.outline["templates"]["1~4a"]["variant"]["by"] = "retidy"
    v = c.get(f"/api/docs/{d}/outline/cut", params={"paras": _lines(s.outline, 1, 4)[0]}).json()
    assert v["made"][0]["why"] and "넣은 뒤 정리" in v["made"][0]["why"]
    bad = _cut(c, d, [_lines(s.outline, 1, 4)[0]], 1, 4, "here", into="1~4a")
    assert bad.status_code == 400 and "넣은 뒤 정리" in bad.json()["detail"]
    s.outline["templates"]["1~4a"]["variant"].pop("by")
    _undo_all(c, d, s)


def test_cut_replays_in_order_after_reanalysis(sess):
    """다시 분석한 뒤(carry) — 누른 때의 그 자리를 잇는다: 더 넣은 것은 제 차례에(astra 반례) · 나눈 템플릿에서 만든 형제는 그 템플릿에 · 새로 잡힌 줄은 「모두」 여도 안 데려간다
    (뿌리로도 · 뿌리 아래 같은 레벨 줄로도) · 대표도 직후와 같다."""
    c, d, s = sess
    l4 = _lines(s.outline, 1, 4)
    first = next(p for p in l4 if len(M._members(s.outline, "1", [p])) > 1)
    second = next(p for p in l4 if p != first and len(M._members(s.outline, "1", [p])) > 1)
    dline = next(p for p in _lines(s.outline, 1, 5) if s.outline["lines"][p]["parent"] == second)
    # ① 첫 L4 를 C 로 → ② 다른 L4 아래의 L5 줄 d 를 D 로 → ③ 그 다른 L4 를 C 에 넣는다: d 는 D 에 남는다
    assert _cut(c, d, [first], 1, 4, "here").status_code == 200
    assert _cut(c, d, [dline], 1, 5, "here").status_code == 200
    assert _cut(c, d, [second], 1, 4, "here", into="1~4a").status_code == 200
    assert s.outline["lines"][dline]["tpl"] == "1~5a" and s.outline["lines"][second]["tpl"] == "1~4a"
    up = s.outline["lines"][s.outline["lines"][first]["parent"]]
    assert "1~4a" in s.outline["branches"][f"{up['tpl']}|{up['level']}"]  # 실제로 매달린 자리
    assert "1~5a" in s.outline["branches"]["1~4a|4"]  # 옮긴 줄 아래에 남은 다른 템플릿(D)도 새 템플릿의 그 레벨에 매달린다
    recs = [(m["id"], bool(m.get("add")), m.get("key"), m.get("table")) for m in s.outline["splits"]]
    assert recs == [("1~4a", False, "o", False), ("1~5a", False, "-", False), ("1~4a", True, "o", False)]
    ov, fails = _carry(s)
    assert fails == [] and _where(ov) == _where(s.outline) and _reps(ov) == _reps(s.outline) and not ov.get("lost")
    assert [(m["id"], bool(m.get("add")), m.get("key"), m.get("table")) for m in ov["splits"]] == recs and not any(m.get("stop") for m in ov["splits"])
    # 만든 기록의 줄(first)만 없어지고 더 넣은 줄(second)은 살아 있다 → 그 템플릿을 더 넣은 줄로 다시 만든다: second = C · d = D(C 가 통째로 없어지지도, d 를 삼키지도 않는다)
    ov = _fresh(s)
    ov["lines"].pop(first)
    ov, fails = _carry(s, ov=ov)
    assert [(m["id"], bool(m.get("add")), why) for m, why in fails] == [("1~4a", False, "뗀 줄이 없음")]
    assert ov["lines"][second]["tpl"] == "1~4a" and ov["lines"][dline]["tpl"] == "1~5a" and [m["id"] for m in ov["lost"]] == ["1~4a"] and ov["lost"][0]["why"]
    # 못 건 기록은 남아 있다가 그 줄이 다시 잡히면 제 템플릿에 든다(다시 만들어 둔 그 템플릿에)
    ov2 = _fresh(s)
    assert M.carry(ov, ov2, M.context(s.doc, ov2), doc=s.doc) == [] and ov2["lines"][first]["tpl"] == "1~4a" and ov2["lines"][second]["tpl"] == "1~4a" and not ov2.get("lost")
    assert ov2["lines"][dline]["tpl"] == "1~5a"
    # 서식 떼기의 「더 넣기」 로 자리로 나눈 템플릿에 넣어도 따로 한 건(만든 기록에 합치지 않는다)
    cp = copy.deepcopy(s.outline)
    more = next(p for p in _lines(cp, 1, 4) if p != cp["templates"]["1"]["slots"]["4"]["rep"])
    M.split(cp, "1", 4, [more], into="1~4a", doc=s.doc)
    assert [(m["id"], bool(m.get("add")), m["lines"]) for m in cp["splits"]][-1] == ("1~4a", True, [more]) and len(cp["splits"]) == 4
    # 나눈 템플릿에서 사람이 만든 형제(기록에 없는 그 템플릿의 첫 레벨 줄)는 그 템플릿에 남는다 — 그 형제를 그 안에서 다시 나눈 것도
    sib = next(p for p in _lines(s.outline, 1, 4) if len(M._members(s.outline, "1", [p])) == 1)  # 아래 줄이 없는 줄(새로 만든 형제 꼴)
    old = copy.deepcopy(s.outline)
    old["lines"][sib].update(tpl="1~4a", no="1L4a")
    ov, fails = _carry(s, old)
    assert fails == [] and ov["lines"][sib]["tpl"] == "1~4a"
    M.cut(s.doc, old, "1~4a", 4, [sib], "here")  # C 안에서 다시 나눔(「1~4a~4a」)
    assert old["lines"][sib]["tpl"] == "1~4a~4a"
    ov, fails = _carry(s, old)
    assert fails == [] and ov["lines"][sib]["tpl"] == "1~4a~4a" and _where(ov) == _where(old)
    # 새로 잡힌 그 레벨 줄이 뿌리 아래에 매달려 읽혀도(같은 레벨끼리 부모 · 자식) 데려가지 않는다
    stray = next(p for p in _lines(s.outline, 1, 4) if p != sib)
    ov = _fresh(s)
    ov["lines"][stray]["parent"] = first
    ov, fails = _carry(s, ov=ov)
    assert fails == [] and ov["lines"][stray]["tpl"] == "1" and ov["lines"][first]["tpl"] == "1~4a"
    # 모두 — 다시 분석해 새로 잡힌 그 레벨 줄(옛 오버레이에 없던 줄)은 데려가지 않는다
    assert _cut(c, d, [_lines(s.outline, 1, 4)[0]], 1, 4, "all").status_code == 200
    old = copy.deepcopy(s.outline)
    new_line = _lines(old, "1~4b", 4)[-1]
    old["lines"].pop(new_line)
    for m in old["splits"]:
        m["lines"] = [p for p in m["lines"] if p != new_line]
    ov, fails = _carry(s, old)
    assert fails == [] and ov["lines"][new_line]["tpl"] == "1" and ov["templates"]["1~4b"]["variant"]["cut"] == "all"
    assert len(_lines(ov, "1~4b", 4)) == len(_lines(s.outline, "1~4b", 4)) - 1 and _reps(ov)
    _undo_all(c, d, s)


def test_cut_is_not_replayed_on_a_different_level(sess):
    """그 레벨 번호가 다른 레벨이 된 문서(1칸 제목 상자가 없어져 「o」 가 그 번호가 됨)에는 걸지 않는다 — 나눈 때의 레터 · 표 레벨 여부를 기록에 적어 두고 그것으로 본다
    (나눈 템플릿의 지금 슬롯은 레벨 번호를 맞추는 길이 덮는다: astra 2차). 사람이 그 레벨의 레터를 고친 것은 같은 레벨이다. 못 건 기록은 까닭과 함께 남는다."""
    c, d, s = sess
    assert _cut(c, d, [_lines(s.outline, 1, 4)[0]], 1, 4, "all").status_code == 200
    n = len(_lines(s.outline, "1~4a"))
    rec = s.outline["splits"][0]
    assert rec["key"] == "o" and rec["table"] is False
    # 상자 레벨(▦)에서 나눈 기록인데 지금 그 번호는 글 레벨 「o」 — 나눈 템플릿의 슬롯은 이미 「o」 로 덮여 있어도(지금 슬롯으로는 못 가린다) 걸지 않는다
    old = copy.deepcopy(s.outline)
    old["splits"][0].update(key="▦", table=True)
    ov, fails = _carry(s, old)
    assert [m["id"] for m, why in fails] == ["1~4a"] and "그 레벨이 달라짐" in fails[0][1] and "1~4a" not in ov["templates"] and not _lines(ov, "1~4a")
    assert [(m["id"], m["key"], m["table"]) for m in ov["lost"]] == [("1~4a", "▦", True)] and ov["templates"]["1"]["slots"]["4"]["rep"]  # A 는 그대로(대표를 미리 바꾸지 않는다)
    # 사람이 그 레벨의 레터를 고친 것(옛 A 의 지금 레터 = 새 A 의 레터 · 표 레벨 여부 같음) — 같은 레벨이다
    old = copy.deepcopy(s.outline)
    old["splits"][0].update(key="ㅁ")
    ov, fails = _carry(s, old)
    assert fails == [] and len(_lines(ov, "1~4a")) == n and ov["splits"][0]["key"] == "ㅁ"
    _undo_all(c, d, s)


def test_unsplit_then_reanalysis_agree(sess):
    """합친 직후와 다시 분석한 뒤의 소속 · 대표가 같다(astra 의 반례들) — 안쪽 템플릿을 합치면 그 줄은 자리로 나눈 부모의 템플릿으로 · 겹쳐 나눈 템플릿으로도 ·
    멈춤 경계(stop) 뒤에 남아 있던 줄도 · 받은 레벨의 대표."""
    c, d, s = sess
    par = next(p for p in _lines(s.outline, 1, 4) if len(M._members(s.outline, "1", [p])) > 1)
    dline = next(p for p in _lines(s.outline, 1, 5) if s.outline["lines"][p]["parent"] == par)
    # ① L5 줄 d 를 D 로 → ② 그 부모 L4 를 C 로 → ③ D 를 합친다: d 는 부모(C)의 줄이 되고 C 의 L5 대표가 된다
    assert _cut(c, d, [dline], 1, 5, "here").status_code == 200
    assert _cut(c, d, [par], 1, 4, "here").status_code == 200
    assert s.outline["lines"][dline]["tpl"] == "1~5a" and s.outline["lines"][par]["tpl"] == "1~4a"  # 이미 뗀 다른 템플릿의 줄은 제 템플릿 그대로
    kids = [p for p in _lines(s.outline, "1~4a", 5)]
    r = c.post(f"/api/docs/{d}/outline/unsplit", json={"id": "1~5a"})
    assert r.status_code == 200 and r.json()["back"] == 1
    assert s.outline["lines"][dline]["tpl"] == "1~4a" and s.outline["lines"][dline]["no"] == "1L4a"
    assert s.outline["templates"]["1~4a"]["slots"]["5"]["rep"] in kids + [dline]
    ov, fails = _carry(s)
    assert fails == [] and _where(ov) == _where(s.outline) and _reps(ov) == _reps(s.outline)
    c.post(f"/api/docs/{d}/undo")  # D 를 되살리고
    # ②′ C 의 그 줄을 C 안에서 다시 나눈다(E = 「1~4a~4a」) → D 를 합친다: d 는 E 의 줄(다시 분석해도)
    assert _cut(c, d, [par], "1~4a", 4, "all").status_code == 200
    assert s.outline["lines"][par]["tpl"] == "1~4a~4a" and s.outline["lines"][dline]["tpl"] == "1~5a"
    assert c.post(f"/api/docs/{d}/outline/unsplit", json={"id": "1~5a"}).status_code == 200
    assert s.outline["lines"][dline]["tpl"] == "1~4a~4a"
    ov, fails = _carry(s)
    assert fails == [] and _where(ov) == _where(s.outline) and _reps(ov) == _reps(s.outline)
    _undo_all(c, d, s)
    # 멈춤 경계 — q → d → e 에서 d 를 떼며 e 는 남기고(stop), q 를 C 로 나눈 뒤 d 의 템플릿을 합치면 d · e 가 모두 C 로(다시 분석해도 같다)
    cp = copy.deepcopy(s.outline)
    e = next((p for p in _lines(cp, 1, 5) if cp["lines"][p]["parent"] == par and p != dline), None)
    if e is not None:
        cp["lines"][e]["parent"] = dline  # e 를 d 아래로(같은 레벨끼리 부모 · 자식으로 읽힌 꼴)
        M.split(cp, "1", 5, [dline], doc=None, stop=[e], by="retidy", side="ins")
        assert cp["lines"][e]["tpl"] == "1" and cp["lines"][dline]["tpl"] == "1~5a"
        M.cut(s.doc, cp, "1", 4, [par], "here")
        assert cp["lines"][e]["tpl"] == "1"  # 부모(d)가 다른 템플릿이라 아직 A
        M.unsplit(cp, "1~5a")
        assert cp["lines"][dline]["tpl"] == "1~4a" and cp["lines"][e]["tpl"] == "1~4a"
        ov = _fresh(s)
        ov["lines"][e]["parent"] = dline
        assert M.carry(cp, ov, M.context(s.doc, ov), doc=s.doc) == [] and _where(ov) == _where(cp) and _reps(ov) == _reps(cp)


def test_cut_value_cells_and_retidy_table(sess, monkeypatch):
    """값 칸(표 칸에 혼자 있는 레터)은 새 템플릿의 대표가 아니다 — 값 칸뿐이면 나누지 않는다 · 넣은 뒤 정리의 표(retidyDeep)는 옮겨 간 줄의 몫만(새로 만들 때 · 더 넣을 때 · 합칠 때)
    · 레터가 달라진 템플릿에는 더 넣지 않는다."""
    c, d, s = sess
    l4 = _lines(s.outline, 1, 4)
    a, b, e = l4[0], l4[1], l4[2]
    lone = {a}
    real = M.lone_value
    monkeypatch.setattr(M, "lone_value", lambda doc, ov, p: p in lone or real(doc, ov, p))
    v = _view(c, d, a)
    assert v["here"]["why"] == M.CUT_VALUE and v["all"]["why"] is None
    assert _cut(c, d, [a], 1, 4, "here").status_code == 400
    cp = copy.deepcopy(s.outline)
    cp["templates"]["1"]["slots"]["4"]["rep"] = a  # 지금 대표가 값 칸 — 「모두」 로 옮겨도 새 템플릿의 대표는 글이 있는 줄
    got = M.cut(s.doc, cp, "1", 4, [a], "all")
    C = cp["templates"][got["id"]]
    assert C["slots"]["4"]["rep"] != a and C["slots"]["4"]["rep"] in got["paras"] and "repSet" not in C["slots"]["4"] and cp["lines"][a]["tpl"] == got["id"]
    monkeypatch.setattr(M, "lone_value", real)
    # 넣은 뒤 정리의 표 — 옮겨 간 줄의 몫만
    cp = copy.deepcopy(s.outline)
    cp["templates"]["1"]["slots"]["4"][M.RETIDY_DEEP] = {"rep": e, "lines": [e, b]}
    M.cut(s.doc, cp, "1", 4, [e], "here")
    assert cp["templates"]["1~4a"]["slots"]["4"][M.RETIDY_DEEP] == {"rep": e, "lines": [e]} and cp["templates"]["1"]["slots"]["4"][M.RETIDY_DEEP] == {"rep": None, "lines": [b]}
    M.cut(s.doc, cp, "1", 4, [b], "here", into="1~4a")
    assert cp["templates"]["1~4a"]["slots"]["4"][M.RETIDY_DEEP] == {"rep": e, "lines": [e, b]} and M.RETIDY_DEEP not in cp["templates"]["1"]["slots"]["4"]
    M.unsplit(cp, "1~4a")
    assert cp["templates"]["1"]["slots"]["4"][M.RETIDY_DEEP] == {"rep": e, "lines": [e, b]}
    # 레터가 달라진 템플릿(그 템플릿에서 레터를 고친 것)에는 더 넣지 않는다
    cp = copy.deepcopy(s.outline)
    M.cut(s.doc, cp, "1", 4, [e], "here")
    cp["templates"]["1~4a"]["slots"]["5"]["key"] = "!"
    kid = next(p for p in _lines(cp, 1, 4) if len(M._members(cp, "1", [p])) > 1)
    with pytest.raises(ValueError, match="레터가"):
        M.cut(s.doc, cp, "1", 4, [kid], "here", into="1~4a")
    assert cp["lines"][kid]["tpl"] == "1"
    # 서식 떼기(split)도 — 뗀 줄이 더 깊은 레벨의 줄을 다 데려가면 원래 템플릿의 그 레벨은 대표를 비운다(다른 템플릿의 줄을 대표로 남기지 않는다 · 합치면 돌아온 줄이 대표)
    cp = copy.deepcopy(s.outline)
    q = next(p for p in _lines(cp, 1, 4) if p != cp["templates"]["1"]["slots"]["4"]["rep"] and len(M._members(cp, "1", [p])) > 1)
    mine = [p for p in M._members(cp, "1", [q]) if p != q]
    for p in [p for p in _lines(cp, 1, 5) if p not in mine]:
        cp["lines"].pop(p)  # T1 L5 줄이 q 아래 것뿐인 문서
    cp["templates"]["1"]["slots"]["5"].update(rep=mine[0], agentRep=mine[0])
    got = M.split(cp, "1", 4, [q], doc=s.doc)
    assert cp["templates"]["1"]["slots"]["5"]["rep"] is None and "agentRep" not in cp["templates"]["1"]["slots"]["5"] and cp["templates"][got["id"]]["slots"]["5"]["rep"] in mine
    M.unsplit(cp, got["id"])
    assert cp["templates"]["1"]["slots"]["5"]["rep"] in mine
    assert not s.outline.get("splits")


def test_cut_client_wiring():
    static = ROOT / "app" / "static"
    js, app, html = ((static / n).read_text(encoding="utf-8") for n in ("outline_cut.js", "app.js", "index.html"))
    assert html.index('src="/static/outline_match.js"') < html.index('src="/static/outline_cut.js"')
    assert "b.dataset.paras = x.ps.join" in app and "dataset.paras" in js and "olmMergeCall(\"cut\"" in js and "/outline/cut?paras=" in js
    assert 'outlineCut: "새 템플릿으로 나누기"' in app
    assert 'outlineMove: "나눈 템플릿으로 옮기기"' in app and 'olmMergeCall("move"' in js and "v.moves" in js  # 나눈 템플릿끼리 옮기기(② §8-13)
    for name in ("olmMergeCall", "olmKey", "olmUnsplit", "olmLookFrom"):  # 메뉴가 기대는 outline_match.js 의 이름
        assert f"function {name}(" in (static / "outline_match.js").read_text(encoding="utf-8") or f"const {name} =" in (static / "outline_match.js").read_text(encoding="utf-8")
    assert "갈래" not in js.split("*/", 1)[1] and "공백" not in js  # 화면 글에 쓰지 않는 말


def _move(c, d, paras, tid, level, to, scope, sig=None):
    return c.post(f"/api/docs/{d}/outline/move", json={"paras": paras, "tpl": str(tid), "level": level, "to": str(to), "scope": scope, **({"sig": sig} if sig else {})})


def _mv(v, to):
    return next(m for m in v["moves"] if m["id"] == to)


def test_move_between_cut_templates(sess):
    """나눈 템플릿끼리 옮기기(② §8-13) — 2026-11-24 사용자 "T7L2 로 모두변경하기, 이것만 변경하기 … 대표에서 a로 b로 b에서 대표로.. 이것만 전체":
    T1 L4 → T1L4a(모두) · T1L4a → T1L4b(여기서만 · 모두) · T1L4b → T1 L4(여기서만) — 바꾼 직후와 다시 분석해 기록을 다시 건 뒤의 소속 · 대표가 같다 · 문서는 안 바뀐다 · 실행 취소로 처음."""
    c, d, s = sess
    l4 = _lines(s.outline, 1, 4)
    n5 = len(_lines(s.outline, 1, 5))
    assert _view(c, d, l4[0])["moves"] == []  # 나눈 템플릿이 없으면 옮길 곳도 없다
    assert _cut(c, d, [l4[0]], 1, 4, "here").status_code == 200
    assert _cut(c, d, [l4[1]], 1, 4, "here").status_code == 200  # → T1L4b
    assert s.outline["lines"][l4[1]]["tpl"] == "1~4b"
    # T1 L4 줄의 메뉴 — 「모두 T1L4a 에 넣기」 · 「모두 T1L4b 에 넣기」
    v = _view(c, d, l4[2])
    assert [(m["no"], m["root"]) for m in v["moves"]] == [("1L4a", False), ("1L4b", False)]
    rest = len(_lines(s.outline, 1, 4))
    assert _mv(v, "1~4a")["all"]["lines"] == rest and _mv(v, "1~4a")["all"]["why"] is None
    assert _move(c, d, [l4[2]], 1, 4, "1~4a", "all", sig=_mv(v, "1~4b")["all"]["sig"]).status_code == 409  # 메뉴가 보인 계획과 다르면 하지 않는다
    r = _move(c, d, [l4[2]], 1, 4, "1~4a", "all", sig=_mv(v, "1~4a")["all"]["sig"])
    assert r.status_code == 200, r.text
    assert r.json()["moved"]["how"] == "into" and r.json()["moved"]["no"] == "1L4a" and not _lines(s.outline, 1, 4)
    # T1L4a 줄의 메뉴 — 「여기서만 T1 L4 로 되돌리기」 · T1L4b 로 여기서만 · 모두
    v = _view(c, d, l4[2])
    assert [(m["no"], m["root"]) for m in v["moves"]] == [(1, True), ("1L4b", False)]
    kids = M._members(s.outline, "1~4a", [l4[2]])
    r = _move(c, d, [l4[2]], "1~4a", 4, "1~4b", "here", sig=_mv(v, "1~4b")["here"]["sig"])
    assert r.status_code == 200, r.text
    assert r.json()["moved"]["how"] == "side"
    assert all(s.outline["lines"][p]["tpl"] == "1~4b" for p in kids) and r.json()["moved"]["moved"] == len(kids)
    _reps(s.outline)
    ov, lost = _carry(s)
    assert not lost and _where(ov) == _where(s.outline) and _reps(ov) == _reps(s.outline)  # 다시 분석해도 같은 소속 · 대표
    # T1L4b 의 한 줄을 T1 L4 로 되돌리기(여기서만) — 원래 템플릿의 비었던 레벨에 대표가 선다
    back = l4[1]
    v = _view(c, d, back)
    r = _move(c, d, [back], "1~4b", 4, "1", "here", sig=_mv(v, "1")["here"]["sig"])
    assert r.status_code == 200, r.text
    assert r.json()["moved"]["how"] == "back"
    assert s.outline["lines"][back]["tpl"] == "1" and s.outline["templates"]["1"]["slots"]["4"]["rep"] == back
    assert back not in {p for m in s.outline["splits"] for p in m["lines"]}
    ov, lost = _carry(s)
    assert not lost and _where(ov) == _where(s.outline) and _reps(ov) == _reps(s.outline)
    # T1L4a 모두 → T1L4b — T1L4a 가 없어진다
    one = _lines(s.outline, "1~4a", 4)[0]
    v = _view(c, d, one)
    r = _move(c, d, [one], "1~4a", 4, "1~4b", "all", sig=_mv(v, "1~4b")["all"]["sig"])
    assert r.status_code == 200, r.text
    assert "1~4a" not in s.outline["templates"] and len(_lines(s.outline, 1, 4)) == 1
    assert len(_lines(s.outline, "1~4b", 4)) + 1 == len(l4) and len(_lines(s.outline, "1~4b", 5)) == n5 - len(M._members(s.outline, "1", [back])) + 1
    ov, lost = _carry(s)
    assert not lost and _where(ov) == _where(s.outline) and _reps(ov) == _reps(s.outline)
    # 같은 무리가 아닌 곳 · 제 자신은 400
    assert _move(c, d, [one], "1~4b", 4, "1~4b", "here").status_code == 400
    assert _move(c, d, [one], "1~4b", 4, "5", "here").status_code == 400
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()
    _undo_all(c, d, s)

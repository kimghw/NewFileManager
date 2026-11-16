"""뼈대 유지(spec_헤딩_추출 ② §17, 2026-11-10 사용자 「문서가 바뀔 때마다 헤딩을 다시 추출하라고 하면 어쩌냐 … 새로운 레터나 서식이 추가되면 알람이나 표시만」).
2·3단계 결과는 문서를 고쳐도 그대로(실행을 새로 만들지 않음) · 지금 문서를 뼈대와 견줘 새 레터 · 새 서식 · 새 표 · 모양이 바뀐 표만 알림 · 글만 고친 줄 · 개요 편집이 만든 줄 ·
앱이 맞춘 둘째 줄(개요 줄 자리)은 새 서식이 아님 · 기준 1단계 결과가 없으면 레터만.
서식은 되풀이될 때만 새 서식(2026-11-16 사용자 「새로운 서식은 반복적일때 새로운 서식인거지. 이건잘못된거잖아」): 한 줄뿐이면 잘못된 서식(`wrong`) · 장평·자간만 다른 줄은 알리지 않음."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_drift as HD
from app import heading_extract as E
from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs, server
from app import heading_temp as TP

PLAN = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
PID = "p970"  # 본문 「□ 연구개발기술(제품)의 정의 및 범위」 — 가지 템플릿 「□›o›-›·」 의 L1(tests/test_outline_edit.py 와 같은 줄)
ZERO2 = {"letters": 0, "letterParas": 0, "formats": 0, "formatParas": 0, "wrong": 0, "wrongParas": 0}
ZERO3 = {"new": 0, "changed": 0, "gone": 0, "resized": 0}


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
    """양식 하나를 열고 1·2·3단계(스크립트)를 돌린 세션 — 모듈이 나눠 쓴다(시험마다 문서를 처음대로 돌려 놓는다)."""
    tmp = tmp_path_factory.mktemp("drift")
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
        for stage in (1, 2, 3):
            heading_runs.run_sync(s, stage, False)
        yield c, d, s
        server.DOCS.clear()


def _drift(c, d):
    r = c.get(f"/api/docs/{d}/headings/drift")
    assert r.status_code == 200, r.text
    return r.json()


def _patch(c, d, text, pid=PID):
    r = c.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": text})
    assert r.status_code == 200, r.text


def _restore(c, d, s, orig):
    while s.state()["undo"]:
        assert c.post(f"/api/docs/{d}/undo").status_code == 200
    if s.texts[PID] != orig:
        assert c.post(f"/api/docs/{d}/blocks/{PID}/revert").status_code == 200
    assert s.texts[PID] == orig


@pytest.fixture
def doc(sess):
    c, d, s = sess
    orig = s.texts[PID]
    assert orig.startswith("□ ")
    yield c, d, s
    _restore(c, d, s, orig)


# ---------------------------------------------------------------- 문서가 그대로 · 글만 고침
def test_unchanged_document_has_nothing_to_compare(doc):
    c, d, s = doc
    x = _drift(c, d)
    assert x["rev"] == s.rev and x["extracted"] is False
    assert x["stage2"]["moved"] is False and x["stage2"]["counts"] == ZERO2 and x["stage2"]["formatsChecked"] is True
    assert x["stage3"]["moved"] is False and x["stage3"]["counts"] == ZERO3


def test_outline_edit_lines_are_not_new(doc):
    """개요 편집(Enter 하위 줄 · Alt+Enter 뼈대)이 만든 줄은 뼈대의 레터·서식 — 알릴 것이 없다.
    (레터를 바꾸는 시험보다 먼저 — 레터가 사라진 줄은 개요 오버레이에서 빠지고 글을 되돌려도 돌아오지 않는다: spec_hwpx_웹편집 ② §8)"""
    c, d, s = doc
    assert c.get(f"/api/docs/{d}/outline").status_code == 200
    r = c.post(f"/api/docs/{d}/outline", json={"op": "enter", "id": PID, "offset": len(s.texts[PID])})
    assert r.status_code == 200, r.text
    assert _drift(c, d)["stage2"]["counts"] == ZERO2
    r = c.post(f"/api/docs/{d}/outline", json={"op": "sibling", "id": PID})
    assert r.status_code == 200, r.text
    x = _drift(c, d)
    assert x["stage2"]["counts"] == ZERO2 and x["stage3"]["counts"] == ZERO3


def test_text_edit_keeps_skeleton_and_makes_no_run(doc, monkeypatch):
    """글만 고친 헤딩 줄 — 뼈대에 없는 것 없음(앱이 둘째 줄을 글 시작에 맞춰 내어쓰기가 붙어도 새 서식이 아니다). 2·3단계 결과·실행 목록은 그대로."""
    c, d, s = doc
    st = heading_runs.state(s)
    runs, s1, g, t3 = len(st["runs"]), st["stage1"], st["stage2"], st["stage3"]
    _patch(c, d, "□ 글만 고친 줄")
    assert s.doc._para_summary(s.doc._defs["paraPr"][s.doc._ids[PID].get("paraPrIDRef")])["firstLineMm"] < 0  # 개요 줄 자리(② §8-1)가 내어쓰기를 넣었다
    x = _drift(c, d)
    assert x["extracted"] is True and x["stage2"]["moved"] is True and x["stage3"]["moved"] is True
    assert x["stage2"]["counts"] == ZERO2 and x["stage2"]["letters"] == [] and x["stage2"]["formats"] == [] and x["stage2"]["wrong"] == [] and x["stage3"]["counts"] == ZERO3
    assert len(st["runs"]) == runs and st["stage1"] is s1 and st["stage2"] is g and st["stage3"] is t3  # 실행을 만들지도, 결과를 바꾸지도 않는다
    assert heading_runs.summary(s)["stage2"]["stale"] is True  # 「문서가 바뀜」 은 사실로 남는다 — 화면이 다시 만들라고 하지 않을 뿐
    monkeypatch.setattr(E, "extract", lambda *a, **k: pytest.fail("같은 문서 차례는 다시 뽑지 않는다"))
    assert _drift(c, d) == x


def test_left_margin_changed_by_hand_on_an_app_placed_line(doc):
    """앱이 둘째 줄을 맞춘 개요 줄에서 사람이 왼쪽 여백을 바꾸면 뼈대 밖 서식이다(저절로 맞춘 줄은 첫 줄만 앱의 것 — 한 줄뿐이라 잘못된 서식). 그 레벨에 사용자가 정한 자리 규칙이 있으면
    (레터 위치를 옮기는 규칙 — 왼쪽 여백도 앱이 바꾼다) 왼쪽 여백도 빼고 견준다."""
    c, d, s = doc
    _patch(c, d, "□ 글만 고친 줄")
    assert _drift(c, d)["stage2"]["counts"] == ZERO2
    assert c.post(f"/api/docs/{d}/format/para", json={"ids": [PID], "changes": {"indentLeftMm": 30}}).status_code == 200
    first = s.doc._para_summary(s.doc._defs["paraPr"][s.doc._ids[PID].get("paraPrIDRef")])["firstLineMm"]
    assert first < 0 and s.outline["lines"][PID]["first"] == first  # 첫 줄은 앱이 넣은 값 그대로
    x = _drift(c, d)["stage2"]
    assert x["formats"] == [] and [(i["shape"], i["paras"]) for i in x["wrong"]] == [("□", [PID])] and "왼30" in x["wrong"][0]["name"]
    st = heading_runs.state(s)
    sk = HD._skeleton(s, st, st["stage2"], heading_runs.hints(s))
    with s.lock:
        now = E.extract(s.doc, doc_key=s.doc_key)
    temp = TP.label(now, heading_runs.hints(s)["temp"])
    assert HD.headings(sk, now, temp=temp, placed={PID: {"first": first, "left": True}})["wrong"] == []   # 사용자가 정한 자리 규칙이 옮긴 왼쪽 여백
    assert len(HD.headings(sk, now, temp=temp, placed={PID: {"first": first, "left": False}})["wrong"]) == 1
    assert len(HD.headings(sk, now, temp=temp, placed={PID: {"first": first + 1, "left": True}})["wrong"]) == 1  # 첫 줄이 앱이 넣은 값이 아니면 통째로 견준다
    assert all("n" not in i for i in x["wrong"])  # 정렬에만 쓴 값은 답에 없다


# ---------------------------------------------------------------- 새 레터 · 새 서식 · 잘못된 서식
def test_new_letter(doc):
    c, d, s = doc
    _patch(c, d, "▶ 화살표로 바꾼 줄")
    x = _drift(c, d)["stage2"]
    assert x["counts"] == {**ZERO2, "letters": 1, "letterParas": 1}
    it = x["letters"][0]
    assert (it["scope"], it["kind"], it["shape"], it["letter"], it["count"], it["paras"]) == ("body", "marker", "▶", "▶", 1, [PID]) and it["text"] == "화살표로 바꾼 줄"
    _patch(c, d, "(가) 괄호 한글 번호")
    assert [(i["shape"], i["paras"]) for i in _drift(c, d)["stage2"]["letters"]] == [("(가)", [PID])]
    _patch(c, d, "◆ 마름모")  # 변형군은 정규 꼴로 묶는다(◆ = ◇) — 보이는 레터는 쓴 글자
    it = _drift(c, d)["stage2"]["letters"][0]
    assert (it["shape"], it["letter"]) == ("◇", "◆")
    assert c.post(f"/api/docs/{d}/blocks/{PID}/revert").status_code == 200
    assert _drift(c, d)["stage2"]["counts"] == ZERO2  # 되돌리면 없어진다


def _same_letter_lines(s, n=2):
    """PID 와 레터·서식 라벨이 같은 본문 줄 n개(PID 먼저) — 「같은 레터의 줄 여럿」 을 만들 때."""
    recs = {r["id"]: r for r in heading_runs.state(s)["stage1"]["paras"]}
    me = recs[PID]
    out = [PID] + [r["id"] for r in recs.values() if r["id"] != PID and r["kind"] == "marker" and r.get("shape") == me.get("shape") and r.get("fmt") == me.get("fmt")
                   and not r.get("table") and not r.get("blank")]
    assert len(out) >= n, out
    return out[:n]


def test_known_letter_one_line_in_another_format_is_wrong(doc):
    """레터는 있던 것인데 한 줄만 그 레터가 쓰지 않던 서식 — 새 서식이 아니라 잘못된 서식(되풀이되지 않음)."""
    c, d, s = doc
    assert c.post(f"/api/docs/{d}/format/chars", json={"id": PID, "changes": {"sizePt": 20}}).status_code == 200
    x = _drift(c, d)["stage2"]
    assert x["counts"] == {**ZERO2, "wrong": 1, "wrongParas": 1} and x["formats"] == []
    it = x["wrong"][0]
    assert (it["scope"], it["kind"], it["shape"], it["count"], it["paras"]) == ("body", "marker", "□", 1, [PID]) and "20pt" in it["name"]
    assert it["known"] and all("20pt" not in k for k in it["known"])  # 그 레터가 쓰던 서식(이름)
    assert c.post(f"/api/docs/{d}/undo").status_code == 200
    assert _drift(c, d)["stage2"]["counts"] == ZERO2
    assert c.post(f"/api/docs/{d}/format/para", json={"ids": [PID], "changes": {"indentLeftMm": 30}}).status_code == 200  # 사람이 바꾼 왼쪽 여백도 그 줄만이면 잘못된 서식
    x = _drift(c, d)["stage2"]
    assert x["formats"] == [] and [(i["shape"], i["paras"]) for i in x["wrong"]] == [("□", [PID])]


def test_format_repeated_on_several_lines_is_a_new_format(doc):
    """같은 레터의 줄 둘 이상(`REPEAT_MIN`)이 같은 뼈대 밖 서식을 쓰면 새 서식 — 하나를 되돌려 한 줄만 남으면 잘못된 서식."""
    c, d, s = doc
    a, b = _same_letter_lines(s)
    assert HD.REPEAT_MIN == 2
    for pid in (a, b):
        assert c.post(f"/api/docs/{d}/format/chars", json={"id": pid, "changes": {"sizePt": 20}}).status_code == 200
    x = _drift(c, d)["stage2"]
    assert x["counts"] == {**ZERO2, "formats": 1, "formatParas": 2} and x["wrong"] == []
    it = x["formats"][0]
    assert (it["shape"], it["count"], sorted(it["paras"])) == ("□", 2, sorted([a, b])) and "20pt" in it["name"]
    assert c.post(f"/api/docs/{d}/undo").status_code == 200  # b 를 되돌림 — a 한 줄만 남는다
    x = _drift(c, d)["stage2"]
    assert x["counts"] == {**ZERO2, "wrong": 1, "wrongParas": 1} and x["wrong"][0]["paras"] == [a]


def test_fit_values_alone_are_not_a_format(doc):
    """줄 맞춤 값(장평·자간 — 한 줄에 넣으려고 줄인 값)만 다른 줄은 새 서식도 잘못된 서식도 아니다: 서식 조정(대표에 맞추기)이 그 값을 지킨 줄이 알림으로 나오던 것.
    글 런만 자간이 달라 레터 런과 글자 모양이 갈린 줄(레터 런 글자가 따로 잡힘)도 같다. 다른 값이 함께 다르면 그대로 알린다."""
    c, d, s = doc
    st = heading_runs.state(s)
    sk = HD._skeleton(s, st, st["stage2"], heading_runs.hints(s))
    with s.lock:
        now = E.extract(s.doc, doc_key=s.doc_key)  # 이 시험만 쓰는 사본 — 레코드의 글자 모양을 바꿔 견준다(자간·장평은 글자 모양 API 가 받지 않는다)
    temp = TP.label(now, heading_runs.hints(s)["temp"])
    assert HD.headings(sk, now, temp=temp)["counts"] == ZERO2
    tol = G.tolerance()
    rec = next(r for r in now["paras"] if r["id"] == PID)
    base = dict(rec["char"]["text"])
    tight = -(int(tol["spacingPct"]) + 4)  # 오차 밖
    rec["char"] = {"text": {**base, "charPr": "tight", "spacingPct": tight}, "letter": dict(base)}  # 글 런만 자간을 줄임 — 레터 런(자간 0)과 글자 모양이 갈린다
    assert E._letter_run(rec) is not None and E._fp(rec) not in sk["letters"][("body", "marker", "□")]["fps"]
    assert HD.headings(sk, now, temp=temp)["counts"] == ZERO2
    rec["char"]["text"]["ratioPct"] = 100 - (int(tol["ratioPct"]) + 5)  # 장평도
    assert HD.headings(sk, now, temp=temp)["counts"] == ZERO2
    rec["char"]["text"]["sizePt"] = 20.0  # 크기까지 다르면 뼈대 밖 서식(한 줄 — 잘못된 서식)
    x = HD.headings(sk, now, temp=temp)
    assert x["formats"] == [] and [i["paras"] for i in x["wrong"]] == [[PID]]


def test_existing_letter_in_a_format_it_never_used(doc):
    """레터는 문서에 있던 것(「가.」)이지만 그 레터가 쓰던 서식이 아님(□ 줄의 서식 그대로) → 뼈대 밖 서식(한 줄뿐이라 잘못된 서식). 괄호 줄은 그 자리의 괄호 줄 전체 서식과 견준다."""
    c, d, s = doc
    _patch(c, d, "가. 한글 번호로 바꾼 줄")
    x = _drift(c, d)["stage2"]
    assert x["letters"] == [] and x["formats"] == [] and [(i["shape"], i["paras"]) for i in x["wrong"]] == [("가.", [PID])]
    _patch(c, d, "[새 괄호 제목]")
    x = _drift(c, d)["stage2"]
    assert x["letters"] == [] and [(i["kind"], i["shape"], i["paras"]) for i in x["wrong"]] == [("label", "괄호 줄", [PID])]
    _patch(c, d, "[ √ ]")  # 체크 칸은 헤딩 후보가 아니다
    assert _drift(c, d)["stage2"]["counts"] == ZERO2


def test_fresh_stage1_is_reused_and_base_is_kept(doc):
    """1단계를 다시 뽑은 뒤(탭을 열 때의 자동 추출)에는 그 결과로 견준다 — 문서를 다시 읽지 않고, 뼈대의 기준(처음 1단계)은 그대로."""
    c, d, s = doc
    st = heading_runs.state(s)
    g_run = st["stage2"]["meta"]["run"]
    assert c.post(f"/api/docs/{d}/format/chars", json={"id": PID, "changes": {"sizePt": 20}}).status_code == 200
    heading_runs.run_sync(s, 1, False)
    assert st["stage1"]["meta"]["run"] != st["stage2"]["meta"]["stage1Run"] and st["stage2"]["meta"]["run"] == g_run  # 2단계는 그대로
    x = _drift(c, d)
    assert x["extracted"] is False and [(i["shape"], i["paras"]) for i in x["stage2"]["wrong"]] == [("□", [PID])]
    assert c.post(f"/api/docs/{d}/undo").status_code == 200
    x = _drift(c, d)
    assert x["extracted"] is True and x["stage2"]["counts"] == ZERO2


def test_without_base_stage1_only_letters(doc):
    """뼈대를 만든 때의 1단계 결과를 못 읽으면(저장 끔 + 다시 추출) 그래프의 유형 표로 레터만 견준다."""
    c, d, s = doc
    g = heading_runs.state(s)["stage2"]
    sk = HD.skeleton(g, None)
    assert sk["full"] is False and ("body", "marker", "□") in sk["letters"] and ("body", "[기관]") in sk["brackets"]
    _patch(c, d, "▶ 화살표")
    assert c.post(f"/api/docs/{d}/format/chars", json={"id": "p972", "changes": {"sizePt": 20}}).status_code == 200  # 「o」 줄의 서식 — 못 견줌
    with s.lock:
        now = E.extract(s.doc, doc_key=s.doc_key)
    temp = TP.label(now, heading_runs.hints(s)["temp"])  # 유형 표는 TEMP 를 뺀 후보의 것 — 지금 문서도 TEMP 를 빼고 견준다(check 와 같음)
    x = HD.headings(sk, now, temp=temp)
    assert x["formatsChecked"] is False and x["formats"] == [] and x["wrong"] == [] and [(i["shape"], i["paras"]) for i in x["letters"]] == [("▶", [PID])]
    # 세션이 쥐어 둔 뼈대(처음 물었을 때 만든 것) — 그 뒤 1단계를 다시 뽑았고 작업 폴더에서도 못 읽지만(시험마다 다른 NFM_WORKS = 저장 끔과 같음) 기준이 남아 있다
    full = HD.headings(HD._skeleton(s, heading_runs.state(s), g, heading_runs.hints(s)), now, temp=temp)
    assert full["formatsChecked"] is True and [i["paras"] for i in full["wrong"]] == [["p972"]] and [i["shape"] for i in full["letters"]] == ["▶"]


def test_no_results_nothing_to_compare(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_WORKS", str(tmp_path / "w2"))
    c = TestClient(server.app, raise_server_exceptions=False)
    r = c.post("/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")})
    assert r.status_code == 200, r.text
    d = r.json()["docId"]
    try:
        x = _drift(c, d)
        assert x["stage2"] is None and x["stage3"] is None and x["extracted"] is False
    finally:
        server.DOCS.pop(d, None)


# ---------------------------------------------------------------- 순수 함수
def test_ident_and_bracket_key():
    nd = {"flow": "body", "kind": "marker", "family": "circle", "shape": "○", "letter": "○"}
    assert HD.ident(nd) == ("body", "marker", "o") and HD.ident({**nd, "family": "jamo-o", "shape": "ㅇ", "flow": "cell:c1"}) == ("cell", "marker", "o")
    assert HD.ident({"flow": "body", "kind": "marker", "family": "decimal", "shape": "N-N.", "letter": "1-2."}) == ("body", "marker", "N-N.")
    assert HD.ident({"flow": "body", "kind": "label", "letter": "[2차년도 목표]"}) == ("body", "label", "[N차년도 목표]")
    assert HD.ident({"flow": "body", "kind": "title", "letter": "", "shape": None}) == ("body", "title", "제목")
    assert HD.ident({"flow": "body", "kind": "outline", "letter": "", "shape": None, "sourceOutlineLevel": 2}) == ("body", "outline", "개요2")
    assert HD.bracket_key("[2단계 목표]") == "[단계]" and HD.bracket_key("[국내 기술 동향]") == "[…]" and HD.bracket_key("[ √ ]") is None
    hints = {"labels": {"[한국선급]": {"role": "label", "basis": "기관"}}}
    assert HD.bracket_key("[한국선급]", hints) == "[기관]" and HD.bracket_key("[한국선급]") == "[…]"


class _Tables:
    """합성 1단계 레코드 — 표 칸마다 문단 하나(heading_tables.collect 가 읽는 꼴)."""

    def __init__(self):
        self.paras = []

    def table(self, tid, grid, host="p0", ids=None, ncells=None, key=1):
        """grid = 행마다 칸 글. ids = {(행, 열): 칸 id}(없으면 「<표>r<행>c<열>」) — 행·열을 끼워 넣어도 옛 칸의 id 는 그대로 두려고."""
        rows, cols = len(grid), max(len(r) for r in grid)
        tbl = {"t": "tbl", "id": tid, "key": key, "cells": ncells if ncells is not None else sum(len(r) for r in grid), "rows": rows, "cols": cols, "host": host}
        for r, row in enumerate(grid):
            for c, text in enumerate(row):
                cid = (ids or {}).get((r, c), f"{tid}r{r}c{c}")
                cell = {"t": "cell", "id": cid, "key": 1000 + len(self.paras), "row": r, "col": c, "rs": 1, "cs": 1, "fill": None}
                i = len(self.paras)
                self.paras.append({"id": f"p{i}", "n": i, "block": True, "area": "cell", "path": [tbl, cell], "table": tid, "cell": cid,
                                   "kind": "plain" if text.strip() else "empty", "text": text, "blank": False, "fmt": "S1", "letter": "", "family": None, "shape": None,
                                   "char": {"text": {"bold": False, "sizePt": 10.0}}})
        return self

    def stage1(self):
        return {"paras": self.paras}


def _skel(tid, grid, head_rows=1, head_cols=0):
    """3단계 결과의 표 하나(뼈대) — 위 head_rows 행 = 열헤더, 왼쪽 head_cols 열 = 행헤더(겹치는 칸은 귀퉁이), 나머지 필드."""
    cells = []
    for r, row in enumerate(grid):
        for c, text in enumerate(row):
            role = "corner" if r < head_rows and c < head_cols else "colhead" if r < head_rows else "rowhead" if c < head_cols else "field"
            cells.append({"id": f"{tid}r{r}c{c}", "row": r, "col": c, "rs": 1, "cs": 1, "role": role, "text": text})
    return {"id": tid, "rows": len(grid), "cols": max(len(r) for r in grid), "cells": cells}


LIST = [["번호", "과제명", "기간"], ["1", "가 과제", "2026"], ["2", "나 과제", "2027"]]          # 목록형 표 — 열헤더만
MATRIX = [["구분", "1차년도", "2차년도"], ["주관기관", "10", "20"], ["공동기관1", "5", "8"]]  # 행헤더가 있는 표


def _tables(t3_tables, now, **kw):
    return HD.tables({"tables": t3_tables, "tempTables": kw.pop("temp_old", [])}, now.stage1(), **kw)


def test_tables_same_when_headers_are_unchanged():
    """열헤더·행헤더가 그대로면 같은 표(사용자 2026-11-10 「열/행헤더가 변경이 없으면 동일한 것으로 본다」) — 자료 행을 더하거나 값·번호만 바뀐 것은 알리지 않는다."""
    skel = [_skel("t1", LIST), _skel("t2", MATRIX, head_cols=1)]
    same = _Tables().table("t1", LIST).table("t2", MATRIX)
    assert _tables(skel, same) == {"new": [], "changed": [], "gone": 0, "resized": 0, "counts": {"new": 0, "changed": 0, "gone": 0, "resized": 0}}
    more = _Tables().table("t1", LIST + [["3", "다 과제", "2028"], ["", "", ""]]).table("t2", [MATRIX[0], ["주관기관", "11", "22"], MATRIX[2]])  # 자료 행 2줄 · 값만 고침
    x = _tables(skel, more)
    assert x["changed"] == [] and x["new"] == [] and x["resized"] == 1 and x["counts"]["resized"] == 1
    blank_row = _Tables().table("t1", LIST).table("t2", MATRIX + [["", "", ""]])  # 행헤더 자리가 빈 새 행 — 아직 헤더가 아니다
    assert _tables(skel, blank_row)["changed"] == []


def test_tables_changed_when_headers_change():
    skel = [_skel("t1", LIST), _skel("t2", MATRIX, head_cols=1)]
    # ① 헤더 글이 바뀜
    x = _tables(skel, _Tables().table("t1", [["번호", "과제명", "수행 기간"]] + LIST[1:]).table("t2", MATRIX))
    assert [(t["id"], t["heads"], t["was"]) for t in x["changed"]] == [("t1", {"text": 1, "gone": 0, "new": 0}, [3, 3])]
    assert x["changed"][0]["examples"] == [{"what": "text", "role": "colhead", "was": "기간", "now": "수행 기간"}] and x["resized"] == 0
    # ② 새 열(머리 칸에 글) — 새 열헤더. 옛 칸의 id 는 그대로
    grid = [r + [v] for r, v in zip(LIST, ["비고", "", ""])]
    x = _tables(skel, _Tables().table("t1", grid).table("t2", MATRIX))
    assert [(t["id"], t["heads"], t["rows"], t["cols"]) for t in x["changed"]] == [("t1", {"text": 0, "gone": 0, "new": 1}, 3, 4)]
    assert x["changed"][0]["examples"] == [{"what": "new", "role": "colhead", "now": "비고"}]
    # ③ 헤더 칸이 없어짐(열을 지움)
    x = _tables(skel, _Tables().table("t1", [r[:2] for r in LIST]).table("t2", MATRIX))
    assert x["changed"][0]["heads"] == {"text": 0, "gone": 1, "new": 0} and x["changed"][0]["examples"][0] == {"what": "gone", "role": "colhead", "was": "기간"}
    # ④ 행헤더가 있는 표에 이름 붙은 새 행 — 새 행헤더(번호뿐인 새 행은 아니다: 목록형 표 t1 의 「3」)
    x = _tables(skel, _Tables().table("t1", LIST + [["3", "다 과제", "2028"]]).table("t2", MATRIX + [["공동기관2", "1", "2"]]))
    assert [(t["id"], t["heads"]) for t in x["changed"]] == [("t2", {"text": 0, "gone": 0, "new": 1})] and x["changed"][0]["examples"][0]["role"] == "rowhead"
    assert x["resized"] == 1  # t1 은 행 수만 달라진 같은 표
    # 행을 가운데 끼워 넣어 옛 칸의 자리가 밀려도(칸 id 로 견준다) 헤더가 그대로면 같은 표
    ids = {(3, c): f"t1r2c{c}" for c in range(3)} | {(2, c): f"t1new{c}" for c in range(3)}
    x = _tables(skel, _Tables().table("t1", [LIST[0], LIST[1], ["9", "끼운 과제", "2030"], LIST[2]], ids=ids).table("t2", MATRIX))
    assert x["changed"] == [] and x["resized"] == 1


def test_tables_new_gone_and_skipped():
    skel = [_skel("t1", LIST), _skel("t9", LIST), _skel("k4", LIST)]
    now = (_Tables().table("t1", LIST).table("t3", [["가", "나"], ["1", "2"]], host="p8")      # 새 표
           .table("t5", LIST)                                                            # 그때 TEMP 표
           .table("t6", [["상자 글"]], ncells=1)                                           # 1칸 상자
           .table("t7", LIST))                                                           # 지금 TEMP 표
    now.paras.append({"id": "px", "n": len(now.paras), "block": True, "area": "cell", "kind": "plain", "text": "id 없는 표", "blank": False, "fmt": "S1", "char": {"text": {}},
                      "path": [{"t": "tbl", "id": None, "key": 4, "rows": 2, "cols": 2, "cells": 4, "host": None}, {"t": "cell", "id": None, "key": 9, "row": 0, "col": 0, "rs": 1, "cs": 1, "fill": None}]})
    x = _tables(skel, now, temp={"tables": {"t7": "tbl:t7"}}, temp_old=[{"id": "t5"}])
    assert x["new"] == [{"id": "t3", "rows": 2, "cols": 2, "host": "p8"}] and x["changed"] == []
    assert x["gone"] == 1 and x["counts"] == {"new": 1, "changed": 0, "gone": 1, "resized": 0}  # t9 — id 없는 「k4」 는 세지 않는다


def test_real_table_header_edit_is_reported_and_field_edit_is_not(doc):
    """실물 — 3단계 결과의 열헤더 칸 글을 고치면 「헤더가 바뀐 표」, 필드 칸 글을 고치면 같은 표."""
    c, d, s = doc
    t3 = heading_runs.state(s)["stage3"]
    for t in t3["tables"]:
        pick = {}
        for x in t["cells"]:
            pid = (x.get("paras") or [None])[0]
            if len(x.get("paras") or []) == 1 and pid in s.texts and s.texts[pid].strip() and x["role"] in ("colhead", "field"):
                pick.setdefault(x["role"], pid)
        if len(pick) == 2:
            tid, head, field = t["id"], pick["colhead"], pick["field"]
            break
    else:
        pytest.skip("열헤더·필드 칸이 함께 있는 표를 못 찾음")
    orig = {head: s.texts[head], field: s.texts[field]}
    try:
        _patch(c, d, s.texts[field] + " 값 고침", field)
        x = _drift(c, d)["stage3"]
        assert x["moved"] is True and x["changed"] == [] and x["new"] == [] and x["counts"]["changed"] == 0  # 필드만 고침 — 같은 표
        _patch(c, d, s.texts[head] + " 고침", head)
        x = _drift(c, d)["stage3"]
        assert [(t["id"], t["heads"]) for t in x["changed"]] == [(tid, {"text": 1, "gone": 0, "new": 0})] and x["changed"][0]["examples"][0]["what"] == "text"
    finally:
        for pid in (head, field):
            if s.texts[pid] != orig[pid]:
                assert c.post(f"/api/docs/{d}/blocks/{pid}/revert").status_code == 200
    assert _drift(c, d)["stage3"]["changed"] == []


def test_screen_does_not_ask_to_rerun_on_document_change():
    """화면 계약 — 문서가 바뀐 것만으로 「다시 만드세요/재확인 필요」 를 띄우지 않고, 뼈대 밖 항목은 heading_drift.js 가 보인다."""
    static = Path(__file__).parents[1] / "app" / "static"
    app_js, tables_js, html = ((static / n).read_text("utf-8") for n in ("app.js", "tables.js", "index.html"))
    for old in ('"재확인 필요"', "그래프를 다시 만드세요", "표 구조를 다시 만드세요(이 결과는", '"다시 분석 필요"', '"다시 추출 필요"', '"오래된 결과 · 재분석 필요"'):  # 글 상수로(주석은 그 말을 쓸 수 있다)
        assert old not in app_js and old not in tables_js, old
    for hook in ("driftChip()", "driftCardRow(r, 2)", "driftCardRow(r, 3)", "driftSync(r)", "driftTouch()", "driftReset()", "driftMarkOf"):
        assert hook in app_js, hook
    drift_js, match_js = ((static / n).read_text("utf-8") for n in ("heading_drift.js", "outline_match.js"))
    for word in ("s2.wrong", "잘못된 서식", "대표에 맞추기", "olmMatch(ol.tpl, ol.level, 1, [pid])"):  # 한 줄뿐인 서식은 따로 — 맞추기는 「템플릿 관계」 의 갈래 맞추기와 같은 길
        assert word in drift_js, word
    assert "async function olmMatch(id, L, n, group = null)" in match_js and "function tplRelOpen(focus = null, at = null)" in app_js  # heading_drift.js 가 기대는 이름·인자
    assert "driftCount(3)" in tables_js and "/static/heading_drift.js" in html and "/static/heading-drift.css" in html
    stale = app_js.split("function headsStageStale(r, k) {", 1)[1].split("function ", 1)[0]
    assert "driftCount(k)" in stale and ".stale" not in stale  # 단계 탭 점·손볼 단계 = 뼈대 밖 항목이 있을 때만

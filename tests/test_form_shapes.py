"""양식 서식 점검(spec_양식작성 ② §5-11) — app/form_shapes.py(순수) · app/form_shapes_api.py(끝점). 2026-11-27 사용자 "여기에 이상한 서식들을 삭제 제안하는 기능이 있어야 할거 같아. 레터가 없거나 이런건 서식을 수정해야 하고,".
견본 = 그 양식(연차 · 최종 · 단계보고서 요약)의 두 상자를 줄인 꼴 — 글머리는 한글이 찍는 개요 번호(outlineNum)다."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import form_shapes as F
from app import form_shapes_api as API
from app import server

SMALL = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"


def para(i, text, num=None, style="-"):
    return {"id": i, "type": "paragraph", "text": text, "outlineNum": num, "list": None, "style": style}


def box(i, blocks):
    return {"id": i, "type": "table", "nRows": 1, "nCols": 1, "cells": [{"id": f"{i}c", "row": 0, "col": 0, "blocks": list(blocks)}]}


def inner(i):
    return {"id": i, "type": "table", "nRows": 2, "nCols": 3, "cells": [{"id": f"{i}r{k}", "row": 0, "col": k, "blocks": [para(f"{i}p{k}", "( )")]} for k in range(3)]}


# 상자 1: 「○ 주관 : …」 아래 「- 추진 내용」 · 친 「  : 」 줄 · 「-」 빈 줄 둘 · 그림 표 · 캡션 / 「○ 공동 : 」 아래 「-」 빈 줄 둘 + 글머리 없는 빈 줄 하나 / 「○ 공동 : 」 아래 「-」 빈 줄 하나
BOX1 = box("t1", [para("a0", ""), para("a1", "주관(기업명 작성) : 개발목표 작성", "○", "○"), para("a2", "추진 내용 작성", "-"), para("a3", "  : ", None, "발신명의"), para("a4", "", "-"), para("a5", "", "-"),
                  inner("t2"), para("a6", "그림 1 n차년도 연구개발 성과명", None, "캡션"),
                  para("b1", "공동(기업명 작성) : ", "○", "○"), para("b2", "", "-"), para("b3", "", "-"), para("b4", "", None, "+가."),
                  para("c1", "공동(기업명 작성) : ", "○", "○"), para("c2", "", "-")])
# 상자 2: 「(1) 연구개발 목표」 › 「○ 000」 아래 친 「    - 」 줄 · 「○」 빈 줄 둘 · 친 「    - 」 줄 / 상자 끝의 글머리 없는 빈 줄(끝 여백)
BOX2 = box("t9", [para("h1", "연구개발 목표", "(1)", "(1)"), para("h2", "000", "○", "○"), para("s1", "    - ", None, "표내용"), para("o1", "", "○", "○"), para("o2", "", "○", "○"), para("s2", "    - ", None, "표내용"),
                  para("z1", "", None, "바탕글")])
DOC = [para("top", "■ 세부 과제별 당해연도 성과목표 관리", None, "바탕글"), BOX1, para("mid", ""), BOX2]


def _by(got):
    return {it["id"]: it for it in got["items"]}


def test_finds_bare_blank_and_typed_lines():
    got = F.find(DOC)
    by = _by(got)
    assert set(by) == {"a3", "b4", "s1", "s2"} and got["counts"] == {"bare": 1, "typed": 3, "restyle": 3, "delete": 1, "total": 4}
    b4 = by["b4"]                                                    # 「-」 줄 둘 뒤의 글머리 없는 빈 줄 — 앞 줄의 서식으로
    assert (b4["kind"], b4["propose"], b4["like"], b4["likeNum"], b4["options"], b4["filled"]) == ("bare", "restyle", "b3", "-", ["restyle", "delete"], False)
    assert b4["head"] == "공동(기업명 작성) :" and "레터 「-」" in b4["why"] and "text" not in b4
    s1, s2 = by["s1"], by["s2"]                                      # 친 「    - 」 — 한글이 「-」 를 찍는 줄(다른 상자)의 서식으로 · 가장 가까운 줄 · 친 첫머리는 지운다
    assert (s1["kind"], s1["propose"], s1["like"], s1["likeNum"], s1["text"]) == ("typed", "restyle", "c2", "-", "") and s2["like"] == "c2"
    a3 = by["a3"]                                                    # 「  : 」 — 그 글머리를 찍는 서식이 없다: 삭제만
    assert (a3["kind"], a3["propose"], a3["like"], a3["options"]) == ("typed", "delete", None, ["delete"])
    assert "z1" not in by and "a0" not in by                         # 상자 끝의 빈 줄(끝 여백) · 머리 없는 앞쪽 빈 줄은 보지 않는다
    assert "a4" not in by and "o1" not in by                         # 글머리가 찍히는 빈 줄은 보통 줄이다


def test_box_without_drawn_letters_is_left_alone():
    plain = box("t5", [para("h", "연구개발 목표"), para("s", "    - "), para("b", "")])
    assert F.find([plain])["items"] == []                           # 한글이 글머리를 찍는 줄이 없는 상자 — 「보통 서식」 을 정할 수 없다
    assert F.find([para("p", "본문"), inner("t3")])["items"] == []


def test_filled_lines_keep_their_text_and_are_never_deleted():
    orig = {b["id"]: b["text"] for t in (BOX1, BOX2) for b in t["cells"][0]["blocks"] if b["type"] == "paragraph"}
    filled1 = box("t1", [{**b, "text": "규정·표준 도메인 분석 및 용어 분류 체계 설계"} if b["id"] == "b4" else b for b in BOX1["cells"][0]["blocks"]])
    filled2 = box("t9", [{**b, "text": "    - 선박용 반도체 차단기 적합성 평가 절차(안) 개발"} if b["id"] == "s1" else {**b, "text": "    ○ MVDC 계통"} if b["id"] == "s2" else b for b in BOX2["cells"][0]["blocks"]])
    by = _by(F.find([filled1, filled2], None, orig))
    assert (by["b4"]["kind"], by["b4"]["filled"], by["b4"]["propose"], by["b4"]["options"], by["b4"]["like"]) == ("bare", True, "restyle", ["restyle"], "b3") and "text" not in by["b4"]
    assert (by["s1"]["filled"], by["s1"]["options"], by["s1"]["text"]) == (True, ["restyle"], "선박용 반도체 차단기 적합성 평가 절차(안) 개발")   # 친 첫머리만 지우고 쓴 글은 그대로
    assert "s2" not in by                                            # 채운 뒤 첫머리가 바뀐 줄 — 어디까지가 친 글머리인지 모른다: 제안하지 않는다
    typed_in = box("t9", [{**b, "text": "    - AI기반 평가지원 도구"} if b["id"] == "o2" else {**b, "outlineNum": None, "style": "표내용"} if b["id"] == "o1" and False else b for b in BOX2["cells"][0]["blocks"]])
    assert "o2" not in _by(F.find([BOX1, typed_in], None, orig))   # 글머리가 찍히던 빈 줄은 그대로 보통 줄
    lettered = box("t1", [{**b, "text": "    - 쳐 넣은 레터"} if b["id"] == "b4" else b for b in BOX1["cells"][0]["blocks"]])
    assert "b4" not in _by(F.find([lettered, BOX2], None, orig))    # 레터 없는 빈 줄에 레터를 쳐 넣은 줄 — 서식만 바꾸면 레터가 겹친다: 제안하지 않는다
    spaced = box("t9", [{**b, "text": "    - "} if b["id"] == "s2" else b for b in BOX2["cells"][0]["blocks"]])
    s2 = _by(F.find([BOX1, spaced], None, orig))["s2"]              # 첫머리의 빈칸만 달라진 글머리 줄(묶음 빈칸) — 아직 쓸 자리다: 지울 수도 있다
    assert (s2["filled"], s2["options"], s2["text"]) == (False, ["restyle", "delete"], "")
    assert "b4" not in _by(F.find([filled1, filled2]))               # 올린 원본을 모르면 채운 줄은 보지 않는다(그 줄이 머리로 읽힌다)
    assert API._pre(by["b4"]) and API._pre(by["s1"]) and not API._pre(_by(F.find(DOC))["b4"]) and not API._pre(_by(F.find(DOC))["a3"])   # 처음부터 고르는 것 = 채운 줄 · 친 글머리 줄의 서식 수정


def test_sig_follows_the_line_and_its_model():
    a = _by(F.find(DOC))["b4"]["sig"]
    moved = box("t1", [{**b, "style": "○"} if b["id"] == "b3" else b for b in BOX1["cells"][0]["blocks"]])
    assert _by(F.find([moved, BOX2]))["b4"]["sig"] != a and _by(F.find(DOC))["b4"]["sig"] == a


# ---- 끝점 — 반영은 사람이 고른 줄만 · 지문이 같은 줄만 · 편집 하나

@pytest.fixture
def c(monkeypatch, tmp_path):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    server.DOCS.clear()
    yield TestClient(server.app)
    server.DOCS.clear()


def _texted(blocks):
    """글이 있는 문단(표 칸 안까지) [(문단 블록, 그 문단이 든 최상위 블록 id)] — 견본의 글은 모두 표 안이다."""
    out = []

    def walk(bs, top):
        for b in bs:
            if b["type"] == "paragraph" and b["text"].strip():
                out.append((b, top or b["id"]))
            for cell in b.get("cells") or ():
                walk(cell["blocks"], top or b["id"])
    walk(blocks, None)
    return out


def test_api_applies_only_picked_lines_with_same_sig(c, monkeypatch):
    doc = c.post("/api/docs", files={"file": (SMALL.name, SMALL.read_bytes())}).json()["docId"]
    blocks = c.get(f"/api/docs/{doc}").json()["blocks"]
    ps = _texted(blocks)
    top = dict((p["id"], t) for p, t in ps)
    a = ps[0][0]
    like = next(p for p, _ in ps[1:] if p["format"] != a["format"])
    gone = next(p for p, t in ps[1:] if p["id"] not in (a["id"], like["id"]) and sum(1 for q, u in ps if u == t) > 1 and len([q for q, _ in ps if q["text"] == p["text"]]) == 1)

    def item(p, **kw):
        return {"id": p["id"], "box": top[p["id"]], "kind": "bare", "raw": p["text"], "filled": False, "propose": "restyle", "options": ["restyle", "delete"], "like": like["id"], "sig": "s-" + p["id"], **kw}
    monkeypatch.setattr(F, "find", lambda blocks, levels=None, orig=None: {"items": [item(a, filled=True, options=["restyle"]), item(gone)], "counts": {}})
    got = c.get(f"/api/docs/{doc}/form-shapes").json()
    assert [it["id"] for it in got["items"]] == [a["id"], gone["id"]] and got["items"][0]["pre"] is True and got["items"][1]["pre"] is False
    url = f"/api/docs/{doc}/form-shapes"
    assert c.post(url, json={"picks": {}}).status_code == 400 and c.post(url, json={"picks": {a["id"]: {"do": "move"}}}).status_code == 400
    assert c.post(url, json={"expectRev": got["rev"] + 1, "picks": {a["id"]: {"do": "restyle", "sig": "s-" + a["id"]}}}).status_code == 409
    r = c.post(url, json={"picks": {a["id"]: {"do": "restyle", "sig": "낡음"}, "p99999": {"do": "delete", "sig": "x"}}})
    assert r.status_code == 409 and "바뀌었습니다" in r.json()["detail"]                 # 지문이 다르면 반영하지 않는다(편집 없음)
    assert c.post(url, json={"picks": {a["id"]: {"do": "delete", "sig": "s-" + a["id"]}}}).status_code == 409   # 글을 쓴 줄은 지우지 않는다
    r = c.post(url, json={"expectRev": got["rev"], "picks": {a["id"]: {"do": "restyle", "sig": "s-" + a["id"]}, gone["id"]: {"do": "delete", "sig": "s-" + gone["id"]}}})
    assert r.status_code == 200, r.text
    assert r.json()["done"] == {"restyled": [a["id"]], "deleted": [gone["id"]], "skipped": []} and r.json()["rev"] == got["rev"] + 1
    after = {p["id"]: p for p, _ in _texted(c.get(f"/api/docs/{doc}").json()["blocks"])}
    assert after[a["id"]]["format"] == after[like["id"]]["format"] and after[a["id"]]["style"] == after[like["id"]]["style"] and after[a["id"]]["text"] == a["text"]
    assert gone["id"] not in after

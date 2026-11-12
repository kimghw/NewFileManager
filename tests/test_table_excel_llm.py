"""표 엑셀화 — LLM 수식 판정(spec_헤딩_추출 ② §14 「LLM 수식 판정」): 표 앞뒤 글 · 프롬프트 자료 · 답 검사(채우기 펼침·글 칸·문법·주소·순환) · 스크립트 수식과 견줌 · API(가짜 LLM)."""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import server, works
from app import table_excel as TX
from app import table_excel_llm as TL
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
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


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


def _plan(doc):
    """「연구개발기관별 사용계획 총괄표」(26×11 — 「연구개발비 총액(M=K+L)」) 의 표 id."""
    return next(b["id"] for b in _tables(doc.blocks()) if b["nRows"] == 26 and any("연구개발비 총액(M=K+L)" in (c.get("text") or "") for c in b["cells"]))


@pytest.fixture(scope="module")
def plan(rnd_doc):
    tid = _plan(rnd_doc)
    judged = TX.judge(rnd_doc, tid, store=copy.deepcopy(EMPTY))
    return tid, judged, TL.sheet(rnd_doc.table_block(tid), judged)


def one(cell, formula, fill="", reason="근거"):
    return {"cell": cell, "formula": formula, "fill": fill, "reason": reason}


# ---- 자료 ------------------------------------------------------------------------------------------------------

def test_context_reads_title_unit_and_footnotes(rnd_doc):
    ctx = TX.context(rnd_doc, _plan(rnd_doc))
    assert ctx["before"][-2:] == ["o 연구개발기관별 사용계획 총괄표", "(단위 : 천원)"] and len(ctx["before"]) <= 3
    assert ctx["after"][0].startswith("1) 총 인건비 : 내부인건비 + 외부인건비") and ctx["after"][-1] == "* 수정직접비 = 직접비 소계 - 직접비(현물) - 국제공동연구개발비"
    assert len(ctx["after"]) == 5  # 다음 표 앞에서 멈춤
    assert TX.context(rnd_doc, "p1") == {"before": [], "after": []} and TX.context(rnd_doc, "t99999") == {"before": [], "after": []}


def test_sheet_and_payload(plan):
    tid, judged, sh = plan
    assert (sh["rows"], sh["cols"]) == (26, 11) and len(sh["cells"]) == 211 and sh["anchor"][(3, 0)] == "A3" and sh["anchor"][(25, 2)] == "A26"  # 병합 칸은 왼쪽 위 주소
    assert sh["cells"]["A26"]["texty"] and not sh["cells"]["E26"]["texty"] and sh["cells"]["E26"]["role"] == "field" and sh["script"]["E26"] == "=E23+E24" and len(sh["script"]) == 66
    data = TL.payload(tid, sh, {"before": ["(단위 : 천원)"], "after": ["1) 총 인건비 : …"]}, "천원", {"r0": 25, "c0": 4, "r1": 25, "c1": 10})
    assert data["size"] == "26x11" and data["unit"] == "천원" and data["range"] == "E26:K26" and len(data["grid"]) == 26 and len(data["script"]) == 66
    assert data["grid"][0][0] == "A1|귀퉁이|비목|2x1" and data["grid"][25] == ["A26|행헤더|연구개발비 총액(M=K+L)|1x4", "E26", "F26", "G26", "H26", "I26", "J26", "K26"]
    assert {"cell": "E26", "formula": "=E23+E24", "why": "연구개발비 총액 (M=K+L)"} in data["script"]
    assert "range" not in TL.payload(tid, sh)
    text = TL.content(data, TL.guide_text("공통 기준", ""))
    assert "### 공통 기준" not in text and "### 공통 표 지침\n공통 기준" in text and "이 표 지침" not in text and text.count("## 자료(JSON)") == 1 and "VLOOKUP" not in text
    assert json.loads(text.split("## 자료(JSON)\n", 1)[1])["table"] == tid and TL.guide_text("", " ") == "(없음)"


# ---- 답 검사 · 견줌 ------------------------------------------------------------------------------------------------

def test_apply_fill_kinds_and_rejections(plan):
    _, _, sh = plan
    out = TL.apply({"formulas": [
        one("E26", "=E23+E24", "E26:K26"),                                                     # 채우기 7칸 — 스크립트와 글이 같음
        one("e10", "= sum(e3:e6) + SUM(E8:E9)", "E10:J10"),                                    # 꼴만 다름 — 값 같음
        one("E23", "=SUM(E3:E6)+SUM(E8:E9)+SUM(E12:E13)+SUM(E15:E19)+E21+E22"),                # 총 인건비(E10)를 풀어 쓴 꼴 — 값 같음
        one("E20", "E19/E11"),                                                                 # 「=」 빠짐은 받아 줌 · ×100 빠짐 — 다름
        one("E14", "=E12*10%"),                                                                # 스크립트 수식이 없던 칸 — 새 수식
        one("K14", ""),                                                                        # 스크립트 수식을 끄자는 제안
        one("F14", ""),                                                                        # 스크립트 수식도 없는 칸 — 할 일 없음
        one("A3", "=E3"), one("Z99", "=A1"), one("E5", "=VLOOKUP(E3,A1:B2,2)"), one("F5", "=F3+"), one("G5", "=G3", "A1:B2"), one("H5", "=H3", "H5:ZZ5"),
        one("E7", "=SUM(E3:E7)"),                                                              # 제 자신을 가리킴
        one("I3", "=I4"), one("I4", "=I3"),                                                    # 서로를 가리킴
        one("J3", "=J1", "J3:J4"),                                                             # 칸 하나로 글 칸(헤더)을 가리킴 — 거절
        one("K5", "=SUM(E1:J5)"),                                                              # 범위에 헤더가 끼는 것은 둔다(SUM 은 글을 건너뜀) — 값이 달라 「다름」
        "쓰레기", {"cell": None},
    ], "note": "시험"}, sh)
    got = {f["ref"]: f for f in out["formulas"]}
    assert [got[k]["kind"] for k in ("E26", "K26", "E10", "J10", "E23", "E20", "E14", "K14")] == ["same", "same", "equiv", "equiv", "equiv", "diff", "new", "off"]
    assert got["E10"]["formula"] == "=SUM(E3:E6)+SUM(E8:E9)" and got["F10"]["formula"] == "=SUM(F3:F6)+SUM(F8:F9)" and got["E10"]["script"] == "=SUM(E3:E4)+E5+E6+SUM(E8:E9)"
    assert got["E20"]["formula"] == "=E19/E11" and got["E14"]["formula"] == "=E12*10%" and got["E14"]["script"] is None and got["K14"]["formula"] == "" and "F14" not in got
    assert "J3" not in got and "J4" not in got and got["K5"]["kind"] == "diff" and got["K5"]["formula"] == "=SUM(E1:J5)"
    why = {r["ref"]: r["why"] for r in out["rejected"]}
    assert why["A3"] == "글이 있는 칸" and why["Z99"] == "표에 없는 주소" and "모르는 함수 VLOOKUP" in why["E5"] and "끊겼" in why["F5"] and "품지 않음" in why["G5"] and "표 밖" in why["H5"]
    assert "순환" in why["E7"] and "순환" in why["I3"] and "순환" in why["I4"] and why[""] == "표에 없는 주소" and why["J3"] == why["J4"] == "글 칸을 가리킴"
    assert out["counts"] == {"new": 1, "diff": 2, "equiv": 7, "same": 7, "off": 1, "rejected": len(out["rejected"])} and len(out["rejected"]) == 12
    assert [f["ref"] for f in out["formulas"]] == sorted(got, key=lambda k: (sh["cells"][k]["row"], sh["cells"][k]["col"]))
    # 범위 보기 — 그 안의 칸만
    part = TL.apply({"formulas": [one("E26", "=E23+E24", "E26:K26"), one("E10", "=SUM(E3:E6)+SUM(E8:E9)")]}, sh, {"r0": 25, "c0": 4, "r1": 25, "c1": 7})
    assert [f["ref"] for f in part["formulas"]] == ["E26", "F26", "G26", "H26"] and {r["why"] for r in part["rejected"]} == {"고른 범위 밖"}
    # 못 쓰는 답
    assert TL.apply(None, sh)["formulas"] == [] and TL.apply({"formulas": "x"}, sh)["counts"]["rejected"] == 0


def test_apply_last_answer_wins_and_merged_cells(plan):
    _, _, sh = plan
    out = TL.apply({"formulas": [one("K26", "=SUM(E26:J26)"), one("E26", "=E23+E24", "E26:K26")]}, sh)
    assert {f["ref"]: f["formula"] for f in out["formulas"]}["K26"] == "=K23+K24"  # 같은 칸이 두 번 — 뒤의 것
    # 채우기 범위에 걸친 병합 칸(헤더 「비목」 A1 2x1 은 글 칸이라 거절, 범위 밖에서 걸친 칸은 건너뜀)
    out2 = TL.apply({"formulas": [one("A2", "=E3")]}, sh)
    assert out2["formulas"] == [] and out2["rejected"][0]["ref"] == "A1" and out2["rejected"][0]["why"] == "글이 있는 칸"
    # 거절 목록은 100개까지만 싣고 수는 다 센다 · 안내·제목 칸의 글은 길게 싣는다
    many = TL.apply({"formulas": [one("A3", "=E3")] * 150}, sh)
    assert len(many["rejected"]) == TL.REJECTED_MAX and many["counts"]["rejected"] == 150
    long = {"ref": "A1", "row": 0, "col": 0, "rs": 1, "cs": 1, "text": "가" * 400}
    assert len(TL._token({**long, "role": "note"})) > 300 and len(TL._token({**long, "role": "rowhead"})) < 80


# ---- API ---------------------------------------------------------------------------------------------------

def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def test_api_llm_formula_judgment_with_stub(monkeypatch):
    server.DOCS.clear()
    c = TestClient(server.app)
    seen = {}

    def fake(schema, content, what, **kw):
        seen.update(schema=schema, content=content, what=what, kw=kw)
        return {"data": {"formulas": [one("E26", "=E23+E24", "E26:K26", "총액(M=K+L)"), one("E14", "=E12*10%", "", "각주"), one("A3", "=E3")], "note": "총액은 직접비 소계 + 간접비"},
                "backend": "sdk", "model": "m", "effort": kw.get("effort"), "ms": 12, "costUsd": 0.01, "error": None}
    try:
        d = _upload(c, RND)
        tid = _plan(server.DOCS[d].doc)
        url = f"/api/docs/{d}/tables/{tid}/excel/llm"
        assert c.post(url, json={}).status_code == 503  # LLM 꺼짐
        monkeypatch.setattr(TL.llm, "call", fake)
        monkeypatch.setattr(server.tables_api.llm, "status", lambda: {"available": True})
        assert c.post(url, json={"effort": "최대"}).status_code == 400 and c.post(url, json={"range": {"r0": 3, "c0": 0, "r1": 1, "c1": 2}}).status_code == 400
        assert c.post(f"/api/docs/{d}/tables/t99999/excel/llm", json={}).status_code == 404
        box = next(b["id"] for b in _tables(server.DOCS[d].doc.blocks()) if len(b["cells"]) == 1)  # 1칸 표(글상자) — 부르지 않는다
        assert c.post(f"/api/docs/{d}/tables/{box}/excel/llm", json={}).status_code == 400
        r = c.post(url, json={"effort": "low"})
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["table"] == tid and v["rev"] == server.DOCS[d].rev and v["range"] is None and v["note"].startswith("총액") and v["call"]["backend"] == "sdk" and v["call"]["costUsd"] == 0.01
        assert v["counts"] == {"new": 1, "diff": 0, "equiv": 0, "same": 7, "off": 0, "rejected": 1} and v["rejected"][0]["why"] == "글이 있는 칸"
        assert [f["ref"] for f in v["formulas"]] == ["E14", "E26", "F26", "G26", "H26", "I26", "J26", "K26"] and v["formulas"][0]["kind"] == "new"
        assert seen["what"] == "table-formula" and seen["kw"]["effort"] == "low" and seen["schema"] is TL.SCHEMA
        assert "1) 총 인건비 : 내부인건비" in seen["content"] and "A26|행헤더|연구개발비 총액(M=K+L)|1x4" in seen["content"] and '{"cell":"E7","formula":"=SUM(E3:E4)+E5+E6"' in seen["content"]
        # 범위 보기 — 자료에 range, 답은 그 안만
        r2 = c.post(url, json={"range": {"r0": 25, "c0": 4, "r1": 25, "c1": 7}}).json()
        assert r2["range"] == {"r0": 25, "c0": 4, "r1": 25, "c1": 7} and [f["ref"] for f in r2["formulas"]] == ["E26", "F26", "G26", "H26"] and '"range":"E26:H26"' in seen["content"]
        # 기록 — 한 줄 + 상세(프롬프트·응답·검사 결과)
        ev = [e for e in works.events(d) if e["kind"] == "tableFormulaLlm"]
        assert len(ev) == 2 and ev[0]["table"] == tid and ev[0]["counts"]["same"] == 7 and ev[0]["backend"] == "sdk" and ev[1]["range"] == "E26:H26"
        # 답이 없으면 502(기록은 남김), 표의 지침이 프롬프트에 실림
        from app import table_agent
        table_agent.save(d, tid, instructions="합계 열은 세로 합으로")
        monkeypatch.setattr(TL.llm, "call", lambda *a, **k: (seen.update(content=a[1]), {"data": None, "backend": None, "ms": 1, "costUsd": None, "error": "sdk: 시간 초과"})[1])
        bad = c.post(url, json={})
        assert bad.status_code == 502 and "시간 초과" in bad.json()["detail"] and "### 이 표 지침\n합계 열은 세로 합으로" in seen["content"]
        assert len([e for e in works.events(d) if e["kind"] == "tableFormulaLlm"]) == 3
        # 문서는 안 바뀜
        assert server.DOCS[d].rev == v["rev"]
    finally:
        server.DOCS.clear()

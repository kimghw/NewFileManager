"""에이전트 열 API(spec_일반편집 ② §8·§9·§10) — app/doc_agent_api.py: 한 턴 · 제안 반영(서버에 저장한 제안 · 두 번 누름 · 후보 묶음 · 낡은 제안 · 정책) · 자료 · 비우기.
LLM 은 부르지 않는다(조정 호출 `doc_agent.ask` 와 표 채우기 호출 `table_fill.ask` 를 가짜로 바꾼다)."""
import io
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient

from app import doc_agent as A
from app import doc_agent_api as API
from app import heading_guides as G
from app import heading_rules as R
from app import server, table_agent, works
from app import table_fill as TF

if not any("/agent/turn" in getattr(r, "path", "") for r in server.app.routes):   # server.py 가 아직 이 모듈을 include 하지 않았으면 여기서 붙인다
    server.app.include_router(API.router)

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL = SAMPLES / "기술수요조사서.hwpx"        # 본문 최상위 = 표 둘(t1 1×3 · t8 18×11 — 빈 필드 B4·B6·B8)
MATERIAL = "구분 1차 2차\n인건비 100 120\n재료비 50 60\n합계 150 180"   # 머리 글의 「1차」·「2차」 도 자료에 — 한 자리 수도 견준다(검토 1)
LINES = ["인건비 100 120", "재료비 50 60"]                               # 자료의 글 그대로 옮긴 줄(바꿔 옮긴 줄은 처음부터 고르지 않는다 — 검토 1)
GOOD = [["구분", "1차", "2차"], ["인건비", "100", "120"], ["재료비", "50", "60"], ["합계", "150", "180"]]
TURNED = [["구분", "인건비", "재료비", "합계"], ["1차", "100", "50", "150"], ["2차", "120", "60", "180"]]


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    for m in (R._MEMORY, G._MEMORY, table_agent._MEMORY, A._MEMORY):
        m.clear()
    server.DOCS.clear()
    yield
    server.DOCS.clear()
    for m in (R._MEMORY, G._MEMORY, table_agent._MEMORY, A._MEMORY):
        m.clear()


@pytest.fixture
def c():
    return TestClient(server.app)


@pytest.fixture
def plain(monkeypatch):
    """서식 보관함 모듈 없이 도는 길(글 = 넣을 자리 문단 모양 · 표 서식 = 이 문서의 표)로 고정 — 그 모듈의 상태와 무관하게 이 끝점의 계약만 본다."""
    monkeypatch.setattr(API, "_style_apply", lambda: None)
    monkeypatch.setattr(API, "_listing", lambda: [])


def _upload(c, path=SMALL):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _llm(monkeypatch, answer, seen=None):
    """조정 호출을 가짜로 — answer(사전 | None | data → 사전)를 LLM 답으로. 프롬프트 묶음(계약·할 일·지침·자료)은 진짜 것."""
    def fake(data, guide="", job="", **kw):
        got = answer(data) if callable(answer) else answer
        if seen is not None:
            seen.append({"data": data, "guide": guide, "job": job, "kw": kw})
        return {"data": A.clean(got), "prompt": A.content(data, guide, job), "response": got,
                "call": {"backend": "api", "model": "m", "effort": kw.get("effort"), "ms": 7, "costUsd": 0.01, "error": None if got is not None else "api: 시간 초과"}}
    monkeypatch.setattr(A, "ask", fake)
    monkeypatch.setattr(API.llm, "status", lambda: {"available": True})


def _grid(rows, head=1, cols=1, foot=1):
    return {"rows": [{"cells": [{"text": x, "rowSpan": 1, "colSpan": 1} for x in r]} for r in rows], "headerRows": head, "headerCols": cols, "footRows": foot}


def _write(after="t8", mode="extract", lines=((LINES[0], LINES[0]), (LINES[1], LINES[1]))):
    return {"type": "write", "after": after, "mode": mode, "style": "", "table": "", "range": "", "paras": [], "item": "", "candidates": [],
            "lines": [{"item": "", "text": t, "source": s} for t, s in lines]}


def _turn(c, d, text="자료를 표 아래에 써 줘", **more):
    return c.post(f"/api/docs/{d}/agent/turn", json={"text": text, **more})


def _apply(c, d, turn, proposal="p1", rid="r-1", rev=None, **more):
    return c.post(f"/api/docs/{d}/agent/apply", json={"turn": turn, "proposal": proposal, "requestId": rid, "expectedRev": rev, **more})


def _cell_para(s, table, text):
    """그 표에서 글이 text 인 칸의 문단 id."""
    return next(c["blocks"][0]["id"] for c in s.doc.table_block(table)["cells"] if c["text"].strip() == text)


# ---- 보기 · 자료 -----------------------------------------------------------------------------------------------------------

def test_state_and_materials(c, monkeypatch):
    d = _upload(c)
    url = f"/api/docs/{d}/agent"
    v = c.get(url).json()
    assert v["enabled"] is False and v["hwpx"] is True and v["policy"] == {"apply": True, "why": ""} and v["turns"] == [] and v["materials"] == [] and v["rev"] == 0   # LLM 꺼짐
    assert set(v["styles"]) == {"table", "text"} and v["limits"]["text"] == 4000 and v["limits"]["materialMb"] == 20 and "xlsx" in v["limits"]["ext"]
    m = c.post(url + "/material", json={"name": "예산", "text": MATERIAL})
    assert m.status_code == 200 and sorted(m.json()) == sorted(["id", "name", "kind", "chars", "sha256", "cut", "lossy", "note", "head", "at"]) and m.json()["head"] == MATERIAL and m.json()["kind"] == "text"
    assert (m.json()["lossy"], m.json()["note"]) == (False, "")
    f = c.post(url + "/material", files={"file": ("예산.csv", "구분,금액\n인건비,100\n".encode("cp949"))})
    assert f.status_code == 200 and (f.json()["name"], f.json()["kind"], f.json()["head"]) == ("예산.csv", "csv", "구분,금액\n인건비,100")
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.append(["인건비", 1500])
    buf = io.BytesIO()
    wb.save(buf)
    x = c.post(url + "/material", files={"file": ("예산.xlsx", buf.getvalue())})
    assert x.status_code == 200 and x.json()["head"] == "[Sheet]\n인건비\t1500"
    again = c.post(url + "/material", json={"name": "예산", "text": MATERIAL}).json()
    assert again["id"] == m.json()["id"] and again["reused"] is True                                           # 같은 글을 다시 올리면 있던 것
    for bad in ({"text": "  "}, {"text": 5}, {"name": 3, "text": "x"}, ["x"]):
        assert c.post(url + "/material", json=bad).status_code == 400, bad
    assert c.post(url + "/material", files={"file": ("a.exe", b"MZ")}).status_code == 400 and c.post(url + "/material", content=b"{", headers={"content-type": "application/json"}).status_code == 400
    assert c.post(url + "/material", files={"wrong": ("a.txt", b"x")}).status_code == 400
    limit = A.MATERIAL_BYTES
    monkeypatch.setattr(A, "MATERIAL_BYTES", 10)
    assert c.post(url + "/material", files={"file": ("a.txt", b"x" * 11)}).status_code == 413                   # 한도(20 MB) 초과
    monkeypatch.setattr(A, "MATERIAL_BYTES", limit)
    assert [x_["name"] for x_ in c.get(url).json()["materials"]] == ["예산", "예산.csv", "예산.xlsx"] and "text" not in c.get(url).json()["materials"][0]
    monkeypatch.setattr(A, "MATERIALS_MAX", 3)
    assert c.post(url + "/material", json={"text": "넷째"}).status_code == 400                                  # 자료 수 한도
    gone = c.delete(f"{url}/material/{f.json()['id']}")
    assert gone.status_code == 200 and [x_["name"] for x_ in gone.json()["materials"]] == ["예산", "예산.xlsx"] and c.delete(f"{url}/material/{f.json()['id']}").status_code == 404
    assert [e.get("name") for e in works.events(d) if e["kind"] == "agentMaterial" and not e.get("removed")] == ["예산", "예산.csv", "예산.xlsx"]
    assert c.get("/api/docs/없는문서/agent").status_code == 404


def test_docx_document_cannot_take_a_turn(c, monkeypatch):
    d = _upload(c, SAMPLES / "기술수요조사서.docx")
    _llm(monkeypatch, {"reply": "", "actions": []})
    v = c.get(f"/api/docs/{d}/agent").json()
    assert v["hwpx"] is False and v["enabled"] is True
    assert _turn(c, d).status_code == 400 and _apply(c, d, "t1").status_code == 400
    assert c.post(f"/api/docs/{d}/agent/material", json={"text": "자료"}).status_code == 200                    # 자료는 둘 수 있다


def test_styles_listing_and_picks(c, monkeypatch):
    metas = [{"id": "aaaaaaaaaaaa", "revision": "r2", "kind": "table", "name": "예산 총괄표", "bands": {"headerRows": 1, "headerCols": 1, "footRows": 1}, "rows": 4, "cols": 3, "blueprint": None, "fidelity": "native"},
             {"id": "bbbbbbbbbbbb", "revision": "r1", "kind": "text", "name": "개요 글", "fidelity": "native",
              "items": [{"key": "i1", "name": "□ 줄", "level": 1, "marker": {"mode": "literal", "literal": "□"}, "sample": "□ 견본 글입니다", "format": {"sizePt": 12}}]}]
    monkeypatch.setattr(API, "_listing", lambda: metas)
    d = _upload(c)
    st = c.get(f"/api/docs/{d}/agent").json()["styles"]
    assert st["table"] == [{"id": "aaaaaaaaaaaa", "name": "예산 총괄표", "revision": "r2", "bands": metas[0]["bands"], "rows": 4, "cols": 3, "blueprint": False, "fidelity": "native"}]
    assert st["text"] == [{"id": "bbbbbbbbbbbb", "name": "개요 글", "revision": "r1", "fidelity": "native", "items": [{"key": "i1", "name": "□ 줄", "level": 1, "sample": "□ 견본 글입니다"}]}]
    seen = []
    _llm(monkeypatch, {"reply": "무엇을 쓸까요?", "actions": []}, seen)
    assert _turn(c, d, styles={"table": "aaaaaaaaaaaa", "text": "bbbbbbbbbbbb"}).status_code == 200
    sent = seen[0]["data"]["styles"]
    assert sent["picked"] == {"table": "aaaaaaaaaaaa", "text": "bbbbbbbbbbbb"} and [t["id"] for t in sent["table"]] == ["builtin", "aaaaaaaaaaaa"] and sent["text"][0]["items"][0]["key"] == "i1"
    for bad in ({"table": "ffffffffffff"}, {"text": "aaaaaaaaaaaa"}, {"table": "doc:t999"}, {"table": 5}, "x"):                # 보관함에 없는 서식 · 종류가 다른 서식 · 없는 표
        assert _turn(c, d, styles=bad).status_code == 400, bad
    assert _turn(c, d, styles={"table": "doc:t8", "text": None}).status_code == 200 and _turn(c, d, styles={"table": "builtin"}).status_code == 200


# ---- 한 턴 ----------------------------------------------------------------------------------------------------------------

def test_turn_errors_503_400_502(c, monkeypatch):
    d = _upload(c)
    assert _turn(c, d).status_code == 503                                                                         # LLM 꺼짐
    for bad in ({"text": ""}, {"text": "가" * 4001}, {"text": 5}, {"text": "x", "materials": ["m00000000"]}, {"text": "x", "materials": "m1"}, {"text": "x", "selection": "t8"},
                {"text": "x", "selection": {"paras": "p1"}}, {"text": "x", "selection": {"range": {"r0": 2, "c0": 0, "r1": 1, "c1": 0}}}, {"text": "x", "effort": "최대"}):
        assert c.post(f"/api/docs/{d}/agent/turn", json=bad).status_code == 400, bad
    _llm(monkeypatch, None)
    r = _turn(c, d)
    assert r.status_code == 502 and "시간 초과" in r.json()["detail"] and r.json()["turn"]["error"] == r.json()["detail"] and r.json()["turn"]["proposals"] == []
    got = c.get(f"/api/docs/{d}/agent").json()["turns"]
    assert len(got) == 1 and got[0]["error"].startswith("LLM 이 답하지 못했습니다") and got[0]["text"] == "자료를 표 아래에 써 줘" and got[0]["calls"] == 1      # 실패한 턴도 남겨 화면이 보인다
    ev = [e for e in works.events(d) if e["kind"] == "agentTurn"]
    assert len(ev) == 1 and ev[0]["error"] == "api: 시간 초과" and ev[0]["proposals"] == 0
    _llm(monkeypatch, {"reply": "어느 표에 넣을까요?", "actions": []})
    ok = _turn(c, d)
    assert ok.status_code == 200 and list(ok.json()) == ["turn"] and ok.json()["turn"]["reply"] == "어느 표에 넣을까요?" and ok.json()["turn"]["proposals"] == [] and ok.json()["turn"]["error"] is None                # 행동 없이 되묻기


def test_write_turn_apply_replay_consumed_undo(c, monkeypatch, tmp_path, plain):
    d = _upload(c)
    s = server.DOCS[d]
    mid = c.post(f"/api/docs/{d}/agent/material", json={"name": "예산", "text": MATERIAL}).json()["id"]
    seen = []
    _llm(monkeypatch, {"reply": "두 줄을 제안합니다", "actions": [_write()]}, seen)
    r = _turn(c, d, materials=[mid], selection={"paras": [], "table": "t8", "range": {"r0": 3, "c0": 1, "r1": 3, "c1": 1}, "cursor": None}, effort="low")
    assert r.status_code == 200, r.text
    v = r.json()["turn"]
    (p,) = v["proposals"]
    assert v["reply"] == "두 줄을 제안합니다" and v["text"] == "자료를 표 아래에 써 줘" and v["rev"] == 0 and s.rev == 0 and v["dropped"] == [] and v["materials"] == [mid] and v["call"]["backend"] == "api"   # 턴은 문서를 안 바꾼다
    assert p["type"] == "write" and p["state"] == "open" and p["preselect"] is True and p["baseRev"] == 0 and "op" not in p and [ln["text"] for ln in p["view"]["lines"]] == LINES
    data = seen[0]["data"]
    assert data["request"] == "자료를 표 아래에 써 줘" and data["materials"] == [{"id": mid, "name": "예산", "text": MATERIAL, "cut": False}] and [x["id"] for x in data["outline"]] == ["t1", "t8"]
    assert data["selection"]["table"]["id"] == "t8" and data["selection"]["table"]["range"] == "B4:B4" and [t["id"] for t in data["tables"]] == ["t8", "t1"] and data["history"] == []
    assert seen[0]["job"] == "" and seen[0]["guide"].startswith("\n\n## 판단 지침 — 문서 에이전트") and seen[0]["kw"]["effort"] == "low" and v["job"] is None and v["guide"]["name"] == "agent"
    full = c.get(f"/api/docs/{d}/agent/turns/{v['id']}").json()
    assert full["prompt"]["contract"] == A.CONTRACT and full["prompt"]["job"] == "" and full["prompt"]["guide"] == seen[0]["guide"] and full["prompt"]["data"] == data            # 「지침」 보기
    assert full["answers"]["turn"]["reply"] == "두 줄을 제안합니다" and full["answers"]["fills"] == [] and full["proposals"] == v["proposals"]
    assert [x["key"] for x in full["parts"]] == ["contract", "guide", "request", "data"] and full["parts"][0]["text"] == A.CONTRACT and full["parts"][2]["text"] == v["text"]   # 보낸 글 — 프롬프트에 든 차례(할 일 프롬프트는 없다)
    assert full["parts"][1]["title"] == "판단 지침 — 문서 에이전트" and '"request": "자료를 표 아래에 써 줘"' in full["parts"][3]["text"] and full["response"]["reply"] == "두 줄을 제안합니다"
    assert full["calls"] == [{"what": "조정 호출", **v["call"]}] and v["calls"] == 1
    assert c.get(f"/api/docs/{d}/agent/turns/t0").status_code == 404 and A.Store(d).turn(v["id"])["proposals"][0]["op"]["after"] == "t8"                                          # 실행할 것은 서버에만
    ev = [e for e in works.events(d) if e["kind"] == "agentTurn"]
    assert len(ev) == 1 and ev[0]["proposals"] == 1 and ev[0]["backend"] == "api" and ev[0]["costUsd"] == 0.01 and ev[0]["detail"].startswith("agent/turn_") and ev[0]["turn"] == v["id"]
    assert "## 할 일" not in works.detail_records(d, "agent")[0]["prompt"]
    # 본문 검사
    assert c.post(f"/api/docs/{d}/agent/apply", json={"turn": v["id"], "proposal": "p1"}).status_code == 400                    # requestId 없음
    assert _apply(c, d, v["id"], picks=["c1"]).status_code == 400 and _apply(c, d, v["id"], "p9").status_code == 404 and _apply(c, d, "t0").status_code == 404
    # 반영 — 넣을 자리 뒤에 차례대로
    a = _apply(c, d, v["id"], rev=0)
    assert a.status_code == 200, a.text
    av = a.json()
    new = av["applied"]["written"]["paras"]
    assert av["applied"] == {"turn": v["id"], "proposal": "p1", "type": "write", "state": "applied", "written": {"paras": new}} and len(new) == 2 and av["rev"] == 1 and av["undo"] == 1
    assert av["replayed"] is False
    blocks = s.doc.blocks()
    assert [b["id"] for b in blocks] == ["t1", "t8", *new] and [b["text"] for b in blocks[2:]] == LINES
    assert [b["id"] for b in av["tops"]["blocks"]] == ["t1", "t8", *new] and av["tops"]["drop"] == ["t1", "t8"]                # 구조 편집 응답 — 닿은 최상위 블록(두 표는 한 문단에 있다)
    assert [e for e in works.events(d) if e["kind"] == "agentApply"][0]["paras"] == 2
    assert s.saved_rev == 1 and A.Store(d).request("r-1")["applied"] == av["applied"] and "response" not in A.Store(d).request("r-1")   # 문서 상태를 같은 요청 안에서 작업 폴더에(검토 6) · 붙드는 것은 영수증뿐(검토 5)
    # 같은 requestId — 반영 영수증과 **지금** 문서 상태만(옛 구조 패치는 다시 보내지 않는다 — 검토 5), 문서는 그대로
    again = _apply(c, d, v["id"], rev=0)
    assert again.status_code == 200 and s.rev == 1 and len(s.doc.blocks()) == 4
    assert again.json() == {"replayed": True, "applied": av["applied"], **jsonable_encoder(s.state())} and again.json()["rev"] == 1
    assert not {"tops", "texts", "focus", "edited", "original"} & set(again.json())
    assert _apply(c, d, v["id"], "p2", rid="r-1").status_code == 400                                                           # 그 requestId 는 다른 제안의 것
    # 이미 반영한 제안
    dup = _apply(c, d, v["id"], rid="r-2", rev=1)
    assert dup.status_code == 409 and "이미 반영" in dup.json()["detail"] and s.rev == 1
    st = c.get(f"/api/docs/{d}/agent").json()
    assert st["turns"][0]["proposals"][0]["state"] == "applied" and st["turns"][0]["proposals"][0]["applied"]["paras"] == new and st["turns"][0]["proposals"][0]["applied"]["table"] is None and st["rev"] == 1
    # 다음 턴: 할 일 프롬프트는 그 작업의 TASK 에 있을 때만 · 앞선 대화가 실린다
    monkeypatch.setenv("NFM_JOBS", str(tmp_path / "jobs2"))
    (tmp_path / "jobs2").mkdir()
    (tmp_path / "jobs2" / "doc_edit.md").write_text("# 할 일 프롬프트 — 문서 일반 편집\n\n- 값은 받은 자료에 있는 것만\n", encoding="utf-8")
    assert _turn(c, d).json()["turn"]["job"] is None and seen[-1]["job"] == ""                                                         # TASK 를 안 고른 작업
    works.update(d, task={"kind": "general", "file": "", "job": "doc_edit", "project": ""})
    v2 = _turn(c, d, "한 줄 더").json()["turn"]
    assert seen[-1]["job"].startswith("\n\n## 할 일 — 문서 일반 편집") and "값은 받은 자료에 있는 것만" in seen[-1]["job"] and v2["job"]["job"] == "doc_edit"
    assert seen[-1]["data"]["history"][0] == {"request": "자료를 표 아래에 써 줘", "reply": "두 줄을 제안합니다", "applied": ["글 쓰기 — 2줄"]}
    API._turn(d, {"text": "자리 하나"}, scope={"types": {"write"}})                                                                    # 「지침 작성」 의 자리 턴 — 앞선 대화(다른 자리의 턴)를 싣지 않는다(2026-11-26)
    assert seen[-1]["data"]["history"] == []
    full2 =c.get(f"/api/docs/{d}/agent/turns/{v2['id']}").json()
    assert "## 할 일 — 문서 일반 편집" in works.detail_records(d, "agent")[-1]["prompt"] and full2["prompt"]["job"] == seen[-1]["job"]
    assert [x["key"] for x in full2["parts"]] == ["contract", "job", "guide", "request", "data"] and full2["parts"][1]["title"] == "할 일 프롬프트 — 문서 일반 편집"
    # 실행 취소 — 한 번에 돌아온다
    assert c.post(f"/api/docs/{d}/undo").status_code == 200 and [b["id"] for b in server.DOCS[d].doc.blocks()] == ["t1", "t8"]
    # 검토 5 의 재현(반영 → 실행 취소 → 같은 requestId): 옛 응답의 tops(취소한 문단)가 되살아나지 않는다 — 영수증 + 지금 차례
    late = _apply(c, d, v["id"], rev=0)
    assert late.status_code == 200 and late.json()["replayed"] is True and late.json()["rev"] == server.DOCS[d].rev == 2 and late.json()["applied"] == av["applied"]
    assert "tops" not in late.json() and "texts" not in late.json() and [b["id"] for b in server.DOCS[d].doc.blocks()] == ["t1", "t8"]


def test_draft_and_dropped_actions_in_a_turn(c, monkeypatch, plain):
    d = _upload(c)
    inner = _cell_para(server.DOCS[d], "t8", "기술수요 과제명")
    _llm(monkeypatch, {"reply": "초안입니다", "actions": [_write(mode="draft", lines=(("이 과제는 전력변환 기술을 개발한다", ""),)), _write(after=inner), _write(after="p999")]})
    v = _turn(c, d, "도입 문단을 써 줘").json()["turn"]
    (p,) = v["proposals"]
    assert p["preselect"] is False and p["warn"] == ["에이전트가 쓴 글 — 읽고 반영하세요"] and [x["action"] for x in v["dropped"]] == [1, 2]      # draft 는 처음부터 고르지 않는다
    a = _apply(c, d, v["id"])                                                                                                   # 사람이 읽고 누르면 반영은 된다(expectedRev 없이 — 대상 해시로 견준다)
    assert a.status_code == 200 and server.DOCS[d].doc.blocks()[-1]["text"] == "이 과제는 전력변환 기술을 개발한다"


def test_table_new_choice_group_then_stale_target(c, monkeypatch, plain):
    d = _upload(c)
    s = server.DOCS[d]
    mid = c.post(f"/api/docs/{d}/agent/material", json={"text": MATERIAL}).json()["id"]
    cands = [{"title": "항목 × 연차", "why": "항목이 연차마다 되풀이", "grid": _grid(GOOD)}, {"title": "연차 × 항목", "why": "연차를 세로로", "grid": _grid(TURNED, foot=0)}]
    _llm(monkeypatch, {"reply": "두 가지 구조", "actions": [{"type": "tableNew", "after": "t8", "style": "doc:t8", "candidates": cands}]})
    v = _turn(c, d, "표로 정리해 줘", materials=[mid]).json()["turn"]
    p1, p2 = v["proposals"]
    assert p1["choiceGroup"] == p2["choiceGroup"] == f"{v['id']}.g1" and (p1["preselect"], p2["preselect"]) == (True, False) and p1["excel"]["status"] == p2["excel"]["status"] == "pass"
    assert p2["view"]["grid"]["rows"][1]["cells"][3]["text"] == "150" and (p2["view"]["style"], p2["view"]["styleName"]) == ("doc:t8", "이 문서의 표 t8")
    a = _apply(c, d, v["id"], "p2", rev=0)
    assert a.status_code == 200, a.text
    made = a.json()["applied"]["made"]
    assert (made["rows"], made["cols"]) == (3, 4) and a.json()["applied"]["excel"]["status"] == "pass" and a.json()["applied"]["excel"]["ok"] == 2          # 반영한 뒤의 엑셀 검증
    blocks = s.doc.blocks()
    assert [b["id"] for b in blocks] == ["t1", "t8", made["table"]] and [x["text"] for x in sorted(blocks[2]["cells"], key=lambda x: (x["row"], x["col"]))][4:8] == TURNED[1]
    other = _apply(c, d, v["id"], "p1", rid="r-2", rev=1)
    assert other.status_code == 409 and "같은 묶음" in other.json()["detail"] and len(s.doc.blocks()) == 3                         # 후보는 하나만 반영
    states = {x["id"]: x["state"] for x in c.get(f"/api/docs/{d}/agent").json()["turns"][0]["proposals"]}
    assert states == {"p1": "closed", "p2": "applied"}
    # 낡은 제안: 턴과 반영 사이에 대상(넣을 자리 표)이 바뀌면 409 · 다른 자리만 바뀌었으면 그대로 반영
    _llm(monkeypatch, {"reply": "", "actions": [_write()]})
    v2 = _turn(c, d, materials=[mid]).json()["turn"]
    assert v2["proposals"][0]["baseRev"] == 1 and c.patch(f"/api/docs/{d}/blocks/{_cell_para(s, 't8', '기술수요 과제명')}", json={"text": "과제 이름"}).status_code == 200
    late = _apply(c, d, v2["id"], rid="r-3", rev=1)
    assert late.status_code == 409 and late.json()["detail"] == A.STALE and len(s.doc.blocks()) == 3
    assert c.get(f"/api/docs/{d}/agent").json()["turns"][1]["proposals"][0]["state"] == "stale" and _apply(c, d, v2["id"], rid="r-4", rev=s.rev).status_code == 409
    v3 = _turn(c, d, materials=[mid]).json()["turn"]
    rev = s.rev
    assert c.patch(f"/api/docs/{d}/blocks/{_cell_para(s, 't1', '별첨')}", json={"text": "별첨 1"}).status_code == 200 and s.rev == rev + 1    # 다른 표의 칸
    fine = _apply(c, d, v3["id"], rid="r-5", rev=rev)
    assert fine.status_code == 200 and len(s.doc.blocks()) == 5 and s.doc.blocks()[2]["text"] == LINES[0]                            # 넣을 자리(t8) 바로 뒤


def test_wrong_total_candidate_is_not_preselected(c, monkeypatch, plain):
    d = _upload(c)
    mid = c.post(f"/api/docs/{d}/agent/material", json={"text": MATERIAL}).json()["id"]
    wrong = [r[:] for r in GOOD]
    wrong[3][2] = "181"
    _llm(monkeypatch, {"reply": "", "actions": [{"type": "tableNew", "after": "t8", "style": "doc:t8", "candidates": [{"title": "합계가 틀림", "why": "", "grid": _grid(wrong)}]}]})
    (p,) = _turn(c, d, "표로", materials=[mid]).json()["turn"]["proposals"]
    assert p["preselect"] is False and p["excel"]["mismatch"] == 1 and p["excel"]["status"] == "warn" and any(w.startswith("엑셀 검증") for w in p["warn"])
    kv = _grid([["구분", "내용"], ["인건비", "100"]], foot=0)
    _llm(monkeypatch, {"reply": "", "actions": [{"type": "tableNew", "after": "t8", "style": "doc:t8", "candidates": [{"title": "구분 | 내용", "why": "", "grid": kv}]}]})
    (q,) = _turn(c, d, "표로", materials=[mid]).json()["turn"]["proposals"]
    assert q["excel"]["status"] == "unknown" and q["excel"]["note"] == "검산할 수식 없음" and [x for x in q["checks"] if x["what"] == "excel"][0]["status"] == "unknown"   # 수식 없음 — 통과가 아니다


def test_fill_turn_is_the_existing_pipeline_and_applies_only_picks(c, monkeypatch, plain):
    d = _upload(c)
    s = server.DOCS[d]
    tid, text = "t8", "자료로 이 표를 채워 줘"
    mid = c.post(f"/api/docs/{d}/agent/material", json={"name": "과제", "text": "과제명: 차세대 전력변환 모듈 개발\n필요성: 국산화가 필요하다"}).json()["id"]
    answer = {"fills": [{"cell": "B4", "text": "차세대 전력변환 모듈 개발", "source": "과제명: 차세대 전력변환 모듈 개발", "where": "material", "reason": "과제명"},
                        {"cell": "B6", "text": "국산화가 필요하다", "source": "필요성: 국산화가 필요하다", "where": "material", "reason": "필요성"},
                        {"cell": "B8", "text": "효율 98% 달성", "source": "없는 구절", "where": "material", "reason": ""}, {"cell": "A1", "text": "머리 칸", "source": "", "where": "", "reason": ""}],
              "note": "자료에 있는 두 칸을 채움"}
    sent = []

    def fill(data, notes, guide, rules, job="", **kw):
        sent.append(data)
        return {"data": answer, "prompt": TF.content(data, notes, guide, rules, job), "call": {"backend": "api", "model": "m", "effort": kw.get("effort"), "ms": 9, "costUsd": 0.02, "error": None}}
    monkeypatch.setattr(TF, "ask", fill)
    _llm(monkeypatch, {"reply": "표를 채웁니다", "actions": [{"type": "tableFill", "table": tid, "range": ""}, {"type": "tableFill", "table": "t999", "range": ""}, {"type": "tableFill", "table": "t1", "range": ""}]})
    r = _turn(c, d, text, materials=[mid], selection={"table": tid})
    assert r.status_code == 200, r.text
    v = r.json()["turn"]
    (p,) = v["proposals"]
    material = A.fill_material(text, [A.Store(d).material(mid)])
    assert len(sent) == 1 and sent[0]["material"] == material and "document" not in sent[0] and s.rev == 0                      # 자료 = 고른 자료 글(+ 요청 글) · 이 문서의 글은 안 실음
    want = c.post(f"/api/docs/{d}/tables/{tid}/fill", json={"material": material, "useDoc": False}).json()                      # 기존 끝점에 같은 입력·같은 답
    assert p["view"]["fills"][:2] == want["fills"][:2] and p["view"]["rejected"] == want["rejected"] and p["view"]["counts"] == want["counts"] and p["view"]["answer"] == want["answer"]
    by = {f["ref"]: f for f in p["view"]["fills"]}
    assert want["fills"][2]["warn"] == ["근거 구절을 자료에서 못 찾음"] and p["view"]["fills"][2] == {**want["fills"][2], "warn": ["근거 구절을 자료에서 못 찾음", A.UNSUPPORTED]}   # 에이전트 쪽 값 검사만 더한다(검토 1)
    assert list(by) == ["B4", "B6", "B8"] and p["view"]["picked"] == [by["B4"]["cell"], by["B6"]["cell"]] and p["preselect"] is True
    assert p["excel"]["status"] == "unknown" and p["excel"]["note"] == "검산할 수식 없음" and p["type"] == "tableFill" and p["target"]["block"] == tid
    assert [f["table"] for f in v["fillCalls"]] == [tid] and v["fillCalls"][0]["call"]["costUsd"] == 0.02 and v["fillCalls"][0]["counts"]["fills"] == 3
    assert [x["why"] for x in v["dropped"]] == ["채울 표가 문서에 없습니다: t999", "표 채우기는 한 턴에 2개까지입니다"] and v["notes"] == [x["why"] for x in v["dropped"]]   # 막힌 까닭은 답에
    full = c.get(f"/api/docs/{d}/agent/turns/{v['id']}").json()
    assert full["answers"]["fills"][0]["response"] == answer and full["parts"][-1]["key"] == f"fill:{tid}" and '"material":' in full["parts"][-1]["text"]   # 「지침」 보기에 표 채우기 호출도
    assert full["response"] == {"turn": full["answers"]["turn"], "fills": [{"table": tid, "response": answer}]} and [x["what"] for x in full["calls"]] == ["조정 호출", f"표 채우기 — 표 {tid}"] and v["calls"] == 2
    ev = [e for e in works.events(d) if e["kind"] == "agentTurn"][0]
    assert ev["fills"] == 1 and ev["costUsd"] == 0.03 and ev["ms"] == 16
    # 고른 칸만 넣는다 · 반영한 뒤의 엑셀 검증을 싣는다
    assert _apply(c, d, v["id"], picks={"fills": []}).status_code == 400 and _apply(c, d, v["id"], picks={"fills": ["c99999"]}).status_code == 400 and s.rev == 0
    a = _apply(c, d, v["id"], rev=0, picks={"fills": [by["B6"]["cell"]]})
    assert a.status_code == 200, a.text
    ap = a.json()["applied"]
    assert ap["filled"] == {"table": tid, "cells": [by["B6"]["cell"]], "skipped": []} and ap["excel"]["status"] == "unknown" and ap["excel"]["note"] == "검산할 수식 없음" and ap["type"] == "tableFill"
    cells = {x["id"]: x["text"] for x in s.doc.table_block(tid)["cells"]}
    assert cells[by["B6"]["cell"]] == "국산화가 필요하다" and cells[by["B4"]["cell"]] == "" and cells[by["B8"]["cell"]] == ""
    assert [e for e in works.events(d) if e["kind"] == "agentApply"][0]["cells"] == 1 and _apply(c, d, v["id"], rid="r-2").status_code == 409
    kept = c.get(f"/api/docs/{d}/agent").json()["turns"][0]["proposals"][0]["applied"]                         # 다시 읽은 화면이 그리는 꼴
    assert (kept["table"], kept["cells"], kept["paras"], kept["note"]) == (tid, [by["B6"]["cell"]], [], "1칸 채움") and kept["excel"]["note"] == "검산할 수식 없음" and kept["rev"] == 1
    # 고르지 않고 반영하면 처음부터 고른 칸(경고 없는 칸)만
    v2 = _turn(c, d, text, materials=[mid]).json()["turn"]
    (q,) = v2["proposals"]
    assert [f["ref"] for f in q["view"]["fills"]] == ["B4", "B8"] and q["view"]["picked"] == [by["B4"]["cell"]] and q["view"]["rejected"][0]["ref"] == "B6" and q["baseRev"] == 1
    b = _apply(c, d, v2["id"], rid="r-3", rev=1)
    assert b.status_code == 200 and b.json()["applied"]["filled"]["cells"] == [by["B4"]["cell"]]
    cells = {x["id"]: x["text"] for x in s.doc.table_block(tid)["cells"]}
    assert cells[by["B4"]["cell"]] == "차세대 전력변환 모듈 개발" and cells[by["B8"]["cell"]] == ""
    assert c.post(f"/api/docs/{d}/undo").status_code == 200 and c.post(f"/api/docs/{d}/undo").status_code == 200
    assert {x["id"]: x["text"] for x in server.DOCS[d].doc.table_block(tid)["cells"]}[by["B6"]["cell"]] == ""
    # 표 채우기 호출이 답하지 못하면 제안 없이 까닭만
    monkeypatch.setattr(TF, "ask", lambda *a_, **k: {"data": None, "prompt": "", "call": {"backend": None, "ms": 1, "costUsd": None, "error": "api: 시간 초과"}})
    v3 = _turn(c, d, text, materials=[mid]).json()["turn"]
    assert v3["proposals"] == [] and "시간 초과" in v3["notes"][0]


def test_place_turn_table_fill_counts_only_materials_and_decided_answers(c, monkeypatch, plain):
    """2026-11-27 astra P1-5 — 양식 작성의 자리 턴(서버가 범위를 건 턴)의 요청 글은 작성 지침 · 작성 계획 · 예시를 모은 글이다: 표 채우기의 값 근거(material)에 넣지 않고 「지침」 절로만 보낸다
    (전에는 요청 글 전체가 material 에 합쳐져, 지침에 섞인 샘플 이름을 인용한 칸이 자료에 없어도 근거 검사를 지나 처음부터 골라졌다). 근거 = 고른 자료 + 사람이 정한 답. 범위 없는 턴(에이전트 보기)은 전과 같다."""
    d = _upload(c)
    tid = "t8"
    text = ("[지침 작성] 표 「기술수요」(id t8) 자리를 작성 지침에 따라 채웁니다.\n\n이 자리의 작성 지침:\n"
            "- (04 자동 판정) 과제명은 「샘플 전력모듈 실증」 처럼 한 줄로 쓴다. 해당 없는 칸은 「해당 없음」 으로 적는다.")
    mid = c.post(f"/api/docs/{d}/agent/material", json={"name": "과제", "text": "과제명: 차세대 전력변환 모듈 개발"}).json()["id"]
    answer = {"fills": [{"cell": "B4", "text": "차세대 전력변환 모듈 개발", "source": "과제명: 차세대 전력변환 모듈 개발", "where": "material", "reason": "과제명"},
                        {"cell": "B6", "text": "샘플 전력모듈 실증", "source": "과제명은 「샘플 전력모듈 실증」 처럼", "where": "material", "reason": "지침의 예시를 값으로 옮김"},
                        {"cell": "B8", "text": "해당 없음", "source": "해당 없는 칸은 「해당 없음」 으로 적는다", "where": "rule", "reason": "지침이 정한 고정 글"}], "note": ""}
    sent = []

    def fill(data, notes, guide, rules, job="", **kw):
        sent.append({"data": data, "guide": guide})
        return {"data": answer, "prompt": TF.content(data, notes, guide, rules, job), "call": {"backend": "api", "model": "m", "effort": kw.get("effort"), "ms": 9, "costUsd": 0.02, "error": None}}
    monkeypatch.setattr(TF, "ask", fill)
    _llm(monkeypatch, {"reply": "표를 채웁니다", "actions": [{"type": "tableFill", "table": tid, "range": ""}]})
    body = {"text": text, "materials": [mid], "selection": {"table": tid}}
    scope = {"types": {"tableFill"}, "paras": set(), "tables": {tid}, "decided": ["한국선급"], "uploaded": None}
    (p,) = API._turn(d, body, scope=scope)["turn"]["proposals"]
    mat = A.Store(d).material(mid)
    assert sent[0]["data"]["material"] == A.fill_basis([mat], ["한국선급"]) and "샘플" not in sent[0]["data"]["material"] and "[요청 글]" not in sent[0]["data"]["material"]
    assert sent[0]["data"]["material"].endswith("[사람이 정한 답]\n- 한국선급") and sent[0]["guide"].endswith(f"### {TF.REQUEST_GUIDE}\n{text}")   # 요청 글은 프롬프트의 지침 절에 그대로
    by = {f["ref"]: f for f in p["view"]["fills"]}
    assert by["B4"]["warn"] == [] and by["B6"]["warn"] == ["근거 구절을 자료에서 못 찾음"] and by["B8"]["warn"] == []   # 지침의 샘플 이름은 근거가 아니다 · 지침이 정한 고정 글은 where "rule" 로 찾는다
    assert p["view"]["picked"] == [by["B4"]["cell"], by["B8"]["cell"]]
    (q,) = _turn(c, d, **body).json()["turn"]["proposals"]                                                           # 범위 없는 턴 — 사람이 요청 글에 적은 값은 전처럼 근거
    assert sent[1]["data"]["material"] == A.fill_material(text, [mat]) and TF.REQUEST_GUIDE not in sent[1]["guide"]
    assert {f["ref"]: f for f in q["view"]["fills"]}["B6"]["warn"] == []


def test_source_document_policy_blocks_apply(c, monkeypatch, plain):
    d = _upload(c)
    s = server.DOCS[d]
    works.update(d, task={"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": ""})          # 이관의 사업계획서 = 원본 문서
    pol = c.get(f"/api/docs/{d}/agent").json()["policy"]
    assert pol["apply"] is False and "원본 문서는 바꾸지 않습니다" in pol["why"]
    _llm(monkeypatch, {"reply": "", "actions": [_write(mode="draft")]})
    v = _turn(c, d).json()["turn"]                                                                         # 턴·제안 보기는 된다
    assert len(v["proposals"]) == 1
    no = _apply(c, d, v["id"], rev=0)
    assert no.status_code == 403 and "원본 문서는 바꾸지 않습니다" in no.json()["detail"] and s.rev == 0 and len(s.doc.blocks()) == 2
    assert c.get(f"/api/docs/{d}/agent").json()["turns"][0]["proposals"][0]["state"] == "open"
    works.update(d, task={"kind": "rnd", "file": "report", "job": "plan_to_report", "project": ""})        # 목적 문서
    # 검토 7(에이전트 쪽): 정책은 세션 잠금 안에서 한 번 더 본다 — 잠금 밖 검사 뒤에 TASK 가 원본 문서로 바뀐 경우
    real, seen = API._policy, []

    def flip(sess):
        seen.append(sess.lock.locked())
        return real(sess) if len(seen) == 1 else {"apply": False, "why": "원본 문서는 바꾸지 않습니다"}
    monkeypatch.setattr(API, "_policy", flip)
    late = _apply(c, d, v["id"], rid="r-0", rev=0)
    assert late.status_code == 403 and seen == [False, True] and s.rev == 0 and len(s.doc.blocks()) == 2
    monkeypatch.setattr(API, "_policy", real)
    assert _apply(c, d, v["id"], rev=0).status_code == 200 and len(s.doc.blocks()) == 4


def test_clear_drops_turns_materials_and_proposals(c, monkeypatch, plain):
    d = _upload(c)
    c.post(f"/api/docs/{d}/agent/material", json={"text": MATERIAL})
    _llm(monkeypatch, {"reply": "", "actions": [_write(mode="draft")]})
    v = _turn(c, d).json()["turn"]
    assert c.delete(f"/api/docs/{d}/agent").json() == {"ok": True}
    st = c.get(f"/api/docs/{d}/agent").json()
    assert st["turns"] == [] and st["materials"] == [] and _apply(c, d, v["id"]).status_code == 404 and server.DOCS[d].rev == 0
    assert [e["kind"] for e in works.events(d) if e["kind"].startswith("agent")] == ["agentMaterial", "agentTurn", "agentClear"]


# ---- 검토(astra 2026-11-13 — artifacts/general_edit_astra_2026-11-13/review_answer.md)의 반례 ----------------------------------------

FILL = {"fills": [{"cell": "B4", "text": "차세대 전력변환 모듈 개발", "source": "과제명: 차세대 전력변환 모듈 개발", "where": "material", "reason": "과제명"}], "note": "한 칸"}
FILL_TEXT = "과제명: 차세대 전력변환 모듈 개발"


def _fill_llm(monkeypatch, answer=FILL):
    """표 채우기 호출을 가짜로 → 부른 횟수를 세는 목록."""
    called = []

    def fill(data, notes, guide, rules, job="", **kw):
        called.append(data)
        return {"data": answer, "prompt": TF.content(data, notes, guide, rules, job), "call": {"backend": "api", "model": "m", "effort": kw.get("effort"), "ms": 1, "costUsd": 0.0, "error": None}}
    monkeypatch.setattr(TF, "ask", fill)
    return called


def test_review2_bad_range_unsent_ids_and_selection_bind_what_may_run(c, monkeypatch, plain):
    d = _upload(c)
    mid = c.post(f"/api/docs/{d}/agent/material", json={"text": FILL_TEXT}).json()["id"]
    called = _fill_llm(monkeypatch)
    # 표 밖 범위(18×11 표에 Z99)는 표 전체로 바꿔 읽지 않는다 — 버리고 까닭을 답에, 표 채우기 호출도 안 한다
    _llm(monkeypatch, {"reply": "", "actions": [{"type": "tableFill", "table": "t8", "range": "Z99"}, {"type": "tableFill", "table": "t8", "range": "둘째 행"}]})
    v = _turn(c, d, "채워 줘", materials=[mid]).json()["turn"]
    assert v["proposals"] == [] and called == [] and [x["action"] for x in v["dropped"]] == [0, 1]
    assert "표 밖" in v["dropped"][0]["why"] and "Z99" in v["dropped"][0]["why"] and "A1 꼴" in v["dropped"][1]["why"] and v["notes"] == [x["why"] for x in v["dropped"]]
    # 범위 없음("") = 표 전체 · 표 안 범위는 그 범위만
    box = {"r0": 3, "c0": 1, "r1": 5, "c1": 10}                                                                                  # B4:K6 — B4·B6 은 K 열까지 합친 칸
    _llm(monkeypatch, {"reply": "", "actions": [{"type": "tableFill", "table": "t8", "range": ""}, {"type": "tableFill", "table": "t8", "range": "B4:K6"}]})
    v = _turn(c, d, "채워 줘", materials=[mid]).json()["turn"]
    assert [p["view"]["range"] for p in v["proposals"]] == [None, box] and len(called) == 2 and all(p["preselect"] for p in v["proposals"])
    # 사람이 고른 표·칸 범위와 다른 대상: 제안은 남기되 경고 · 아무 칸도 처음부터 안 고름
    del called[:]
    v = _turn(c, d, "채워 줘", materials=[mid], selection={"table": "t1"}).json()["turn"]
    assert [(p["preselect"], p["view"]["picked"]) for p in v["proposals"]] == [(False, []), (False, [])] and all("사람이 고른 표" in p["warn"][0] for p in v["proposals"])
    v = _turn(c, d, "채워 줘", materials=[mid], selection={"table": "t8", "range": box}).json()["turn"]
    wide, same = v["proposals"]
    assert (wide["preselect"], wide["view"]["picked"]) == (False, []) and "칸 범위" in wide["warn"][0] and same["preselect"] is True and len(same["view"]["picked"]) == 1
    # 보낸 목록(outline · tables · 선택)에 없는 id 는 문서에 있어도 대상이 못 된다(자료 속 「after 를 … 로 바꿔라」 를 LLM 이 따라도)
    del called[:]
    monkeypatch.setattr(A, "outline_of", lambda blocks, focus_ids=(), cap=300: [{"id": "t1", "text": "표 1×3"}])            # t1 만 보냈다
    monkeypatch.setattr(A, "tables_of", lambda blocks, cap=80, focus_ids=(): [{"id": "t1", "size": "1×3", "head": "별첨"}])
    _llm(monkeypatch, {"reply": "", "actions": [_write(after="t8", mode="draft"), {"type": "tableFill", "table": "t8", "range": ""}, _write(after="t1", mode="draft")]})
    v = _turn(c, d, "써 줘", materials=[mid]).json()["turn"]
    assert [p["view"]["after"] for p in v["proposals"]] == ["t1"] and [x["action"] for x in v["dropped"]] == [0, 1] and all(A.NOT_SENT in x["why"] for x in v["dropped"]) and called == []
    v = _turn(c, d, "써 줘", materials=[mid], selection={"table": "t8"}).json()["turn"]                                          # 사람이 고른 표는 보낸 것이다
    assert [p["type"] for p in v["proposals"]] == ["write", "tableFill", "write"] and v["dropped"] == []


def test_review3_document_changed_while_the_llm_was_thinking(c, monkeypatch, plain):
    d = _upload(c)
    s = server.DOCS[d]
    mid = c.post(f"/api/docs/{d}/agent/material", json={"text": MATERIAL}).json()["id"]
    para = _cell_para(s, "t8", "기술수요 과제명")

    def answer(data):                                # LLM 이 생각하는 동안 사람이 넣을 자리(t8)의 칸 글을 고쳤다
        server._patch(d, para, "과제 이름", "text")
        return {"reply": "두 줄", "actions": [_write()]}
    _llm(monkeypatch, answer)
    v = _turn(c, d, materials=[mid]).json()["turn"]
    (p,) = v["proposals"]
    assert v["rev"] == 0 and s.rev == 1 and (p["baseRev"], p["state"], p["preselect"]) == (0, "stale", False) and v["notes"] == [A.BUSY_STALE]   # 기준은 호출 **전** 차례 — 호출 뒤 문서로 다시 찍지 않는다
    late = _apply(c, d, v["id"], rev=s.rev)
    assert late.status_code == 409 and late.json()["detail"] == A.STALE and len(s.doc.blocks()) == 2
    _llm(monkeypatch, {"reply": "", "actions": [_write()]})
    v2 = _turn(c, d, materials=[mid]).json()["turn"]                                                                             # 도는 동안 안 바뀌었으면 열린 제안
    assert (v2["proposals"][0]["baseRev"], v2["proposals"][0]["state"], v2["proposals"][0]["preselect"], v2["notes"]) == (1, "open", True, [])


def test_review4_something_else_inserted_right_after_the_anchor(c, monkeypatch, plain):
    d = _upload(c)
    s = server.DOCS[d]
    mid = c.post(f"/api/docs/{d}/agent/material", json={"text": MATERIAL}).json()["id"]
    _llm(monkeypatch, {"reply": "", "actions": [_write()]})
    v1, v2 = _turn(c, d, materials=[mid]).json()["turn"], _turn(c, d, materials=[mid]).json()["turn"]
    assert v1["id"] != v2["id"] and v1["proposals"][0]["target"] == v2["proposals"][0]["target"] and v1["proposals"][0]["target"]["next"] == A.END
    first = _apply(c, d, v2["id"], rid="r-1", rev=0)                                                                              # 다른 턴의 제안이 같은 자리(t8 바로 뒤)에 먼저 들어갔다
    assert first.status_code == 200 and len(s.doc.blocks()) == 4
    late = _apply(c, d, v1["id"], rid="r-2", rev=0)                                                                               # 넣을 자리(t8)의 글은 그대로지만 바로 뒤가 달라졌다
    assert late.status_code == 409 and late.json()["detail"] == A.STALE and len(s.doc.blocks()) == 4
    assert c.get(f"/api/docs/{d}/agent").json()["turns"][0]["proposals"][0]["state"] == "stale"


def test_review4_library_style_revised_after_the_turn_is_refused(c, monkeypatch):
    pytest.importorskip("app.style_apply")
    style_carrier, style_lib = pytest.importorskip("app.style_carrier"), pytest.importorskip("app.style_lib")
    from app.hwpx_doc import HwpxDoc
    d = _upload(c)
    s = server.DOCS[d]
    rnd = HwpxDoc((SAMPLES / "연구개발계획서_양식.hwpx").read_bytes())
    para = next(b for b in rnd.blocks() if b["type"] == "paragraph" and b["text"].lstrip().startswith("□"))
    data, items = style_carrier.from_paras(rnd, [{"para": para["id"], "level": 1}])
    sid = style_lib.create({"kind": "text", "name": "개요 글", "items": items}, data)["id"]
    mid = c.post(f"/api/docs/{d}/agent/material", json={"text": MATERIAL}).json()["id"]
    act = {"type": "write", "after": "t8", "mode": "extract", "style": sid, "lines": [{"item": "i1", "text": LINES[0], "source": LINES[0]}]}
    _llm(monkeypatch, {"reply": "", "actions": [act]})
    v = _turn(c, d, materials=[mid]).json()["turn"]
    assert v["proposals"][0]["view"]["styleRev"] == "r1" and A.Store(d).turn(v["id"])["proposals"][0]["op"]["styleRev"] == "r1"   # 제안을 낸 때의 서식 revision
    assert style_lib.revise(sid, "r1", {"name": "개요 글(고침)"})["revision"] == "r2"                                               # 그 뒤 보관함에서 서식을 고쳤다
    no = _apply(c, d, v["id"], rev=0)
    assert no.status_code == 409 and no.json()["detail"] == A.STYLE_STALE and s.rev == 0 and len(s.doc.blocks()) == 2
    assert c.get(f"/api/docs/{d}/agent").json()["turns"][0]["proposals"][0]["state"] == "stale"
    v2 = _turn(c, d, materials=[mid]).json()["turn"]                                                                               # 다시 요청하면 새 revision 으로
    ok = _apply(c, d, v2["id"], rid="r-2", rev=0)
    assert v2["proposals"][0]["view"]["styleRev"] == "r2" and ok.status_code == 200 and len(s.doc.blocks()) == 3


def test_review6_applied_fact_survives_a_failed_state_save(c, monkeypatch, plain):
    d = _upload(c)
    s = server.DOCS[d]
    mid = c.post(f"/api/docs/{d}/agent/material", json={"text": MATERIAL}).json()["id"]
    _llm(monkeypatch, {"reply": "", "actions": [_write()]})
    v = _turn(c, d, materials=[mid]).json()["turn"]
    real, fails = A.Store.save_turn, [2]

    def flaky(self, rec, gen=None):
        if fails[0] > 0:
            fails[0] -= 1
            raise OSError("디스크가 가득 참")
        return real(self, rec, gen)
    monkeypatch.setattr(A.Store, "save_turn", flaky)
    a = _apply(c, d, v["id"], rev=0)                                                                    # 문서는 바뀌었는데 제안 상태를 두 번 다 못 썼다
    assert a.status_code == 200 and a.json()["applied"]["note"] == API.NOT_SAVED and a.json()["applied"]["state"] == "applied" and len(s.doc.blocks()) == 4 and fails == [0]
    assert s.saved_rev == s.rev == 1 and A.Store(d).turn(v["id"])["proposals"][0]["state"] == "open"    # 문서 상태는 작업 폴더에 · 디스크의 제안은 아직 열린 채
    dup = _apply(c, d, v["id"], rid="r-2", rev=1)                                                        # 그래도 같은 제안을 다시 반영하지 않는다(삽입은 앵커 글을 안 바꿔 대상 해시로는 못 막는다)
    assert dup.status_code == 409 and "이미 반영" in dup.json()["detail"] and len(s.doc.blocks()) == 4
    assert _apply(c, d, v["id"], rev=0).json()["replayed"] is True                                       # 같은 requestId 는 영수증(메모가 든 채)
    v2 = _turn(c, d, materials=[mid]).json()["turn"]
    fails[0] = 1                                                                                         # 한 번만 실패하면 다시 써서 남긴다
    b = _apply(c, d, v2["id"], rid="r-3", rev=1)
    assert b.status_code == 200 and "note" not in b.json()["applied"] and A.Store(d).turn(v2["id"])["proposals"][0]["state"] == "applied" and fails == [0]


def test_review15_answer_after_clear_is_not_saved(c, monkeypatch, plain):
    d = _upload(c)
    url = f"/api/docs/{d}/agent"

    def answer(data):                                # LLM 이 생각하는 동안 사람이 「비우기」 를 눌렀다
        A.Store(d).clear()
        return {"reply": "초안", "actions": [_write(mode="draft")]}
    _llm(monkeypatch, answer)
    r = _turn(c, d)
    v = r.json()["turn"]
    assert r.status_code == 200 and v["notes"] == [A.CLEARED] and [p["state"] for p in v["proposals"]] == ["stale"] and v["reply"] == "초안"
    assert c.get(url).json()["turns"] == [] and c.get(f"{url}/turns/{v['id']}").status_code == 404 and _apply(c, d, v["id"]).status_code == 404   # 비운 대화에 뒤늦은 턴이 되살아나지 않는다
    _llm(monkeypatch, {"reply": "", "actions": [_write(mode="draft")]})
    a, b = _turn(c, d).json()["turn"], _turn(c, d).json()["turn"]
    assert a["id"] != b["id"] and all(A._TURN.match(x["id"]) and len(x["id"]) == 20 for x in (a, b)) and [t["id"] for t in c.get(url).json()["turns"]] == [a["id"], b["id"]]
    assert [e["detail"] for e in works.events(d) if e["kind"] == "agentTurn"] == [f"agent/turn_{x['id'][1:]}.json" for x in (v, a, b)]             # 호출 상세의 이름도 턴마다 다르다


# ---- 서식 보관함 모듈과 함께(그 모듈이 있을 때만) --------------------------------------------------------------------------------

def test_with_style_modules_builtin_table_and_plain_lines(c, monkeypatch):
    pytest.importorskip("app.style_apply")
    pytest.importorskip("app.style_carrier")
    d = _upload(c)
    s = server.DOCS[d]
    mid = c.post(f"/api/docs/{d}/agent/material", json={"text": MATERIAL}).json()["id"]
    _llm(monkeypatch, {"reply": "", "actions": [{"type": "tableNew", "after": "t8", "style": "builtin", "candidates": [{"title": "항목 × 연차", "why": "", "grid": _grid(GOOD)}]}, _write()]})
    v = _turn(c, d, "표와 글", materials=[mid]).json()["turn"]
    t, w = v["proposals"]
    assert (t["view"]["style"], t["view"]["styleName"]) == ("builtin", "기본 표") and t["preselect"] is True and w["preselect"] is True
    a = _apply(c, d, v["id"], "p1", rev=0)
    assert a.status_code == 200, a.text
    made = a.json()["applied"]["made"]
    assert (made["rows"], made["cols"]) == (4, 3) and a.json()["applied"]["excel"]["status"] == "pass" and [b["id"] for b in s.doc.blocks()] == ["t1", "t8", made["table"]]
    kept = {x["id"]: x for x in c.get(f"/api/docs/{d}/agent").json()["turns"][0]["proposals"]}
    assert kept["p2"]["state"] == "open" and kept["p2"]["target"]["next"] == made["table"] and w["target"]["next"] == A.END   # 같은 턴 · 같은 자리의 열린 제안은 경계를 새 표로 옮겨 적는다(사람이 방금 넣은 것)
    b = _apply(c, d, v["id"], "p2", rid="r-2", rev=0)                                                       # 그래서 같은 턴의 「표와 글」 은 둘 다 반영된다(넣을 자리 t8 바로 뒤에)
    assert b.status_code == 200, b.text
    new = b.json()["applied"]["written"]["paras"]
    blocks = s.doc.blocks()
    assert [x["id"] for x in blocks] == ["t1", "t8", *new, made["table"]] and [x["text"] for x in blocks[2:4]] == LINES
    assert c.post(f"/api/docs/{d}/undo").status_code == 200 and c.post(f"/api/docs/{d}/undo").status_code == 200 and len(server.DOCS[d].doc.blocks()) == 2


def test_with_style_modules_library_table_and_text_styles(c, monkeypatch):
    """보관함에 저장한 표 서식·글 서식으로 — 새 표 · 글 쓰기(항목마다 레터) · 표 서식 입히기 · 글 서식 입히기. 보관함은 시험마다 임시 폴더(conftest NFM_STYLES)."""
    pytest.importorskip("app.style_apply")
    style_carrier, style_lib = pytest.importorskip("app.style_carrier"), pytest.importorskip("app.style_lib")
    from app.hwpx_doc import HwpxDoc
    d = _upload(c)
    s = server.DOCS[d]
    rnd = HwpxDoc((SAMPLES / "연구개발계획서_양식.hwpx").read_bytes())
    paras = [b for b in rnd.blocks() if b["type"] == "paragraph" and b["text"].strip()]
    picks = [next(b for b in paras if b["text"].lstrip().startswith("□")), next(b for b in paras if b["text"].lstrip().startswith("o "))]
    data, items = style_carrier.from_paras(rnd, [{"para": picks[0]["id"], "level": 1}, {"para": picks[1]["id"], "level": 2}])
    text_sid = style_lib.create({"kind": "text", "name": "개요 글", "items": items}, data)["id"]
    data, info = style_carrier.from_table(s.doc, "t8", None)
    table_sid = style_lib.create({"kind": "table", "name": "조사서 표", "rows": info["rows"], "cols": info["cols"], "bands": info["bands"]}, data)["id"]
    st = c.get(f"/api/docs/{d}/agent").json()["styles"]
    assert [x["id"] for x in st["table"]] == [table_sid] and st["text"][0]["id"] == text_sid and [i["key"] for i in st["text"][0]["items"]] == ["i1", "i2"]
    mid = c.post(f"/api/docs/{d}/agent/material", json={"text": MATERIAL}).json()["id"]
    lines = [{"item": "i1", "text": "인건비는 100", "source": "인건비 100"}, {"item": "i2", "text": "재료비는 50", "source": "재료비 50"}, {"item": "i2", "text": "합계는 150", "source": "합계 150"}]
    seen = []
    _llm(monkeypatch, {"reply": "", "actions": [{"type": "tableNew", "after": "t8", "style": "", "candidates": [{"title": "항목 × 연차", "why": "", "grid": _grid(GOOD)}]},
                                              {"type": "write", "after": "t8", "mode": "extract", "style": text_sid, "lines": lines}, {"type": "restyle", "table": "t1", "style": table_sid, "paras": [], "item": ""}]}, seen)
    v = _turn(c, d, "표와 글", materials=[mid], styles={"table": table_sid, "text": None}).json()["turn"]
    t, w, r = v["proposals"]
    assert v["dropped"] == [] and (t["view"]["style"], t["view"]["styleName"]) == (table_sid, "조사서 표") and (w["view"]["style"], w["view"]["styleName"]) == (text_sid, "개요 글")   # 행동이 비운 style = 사람이 고른 서식
    assert [ln["item"] for ln in w["view"]["lines"]] == ["i1", "i2", "i2"] and seen[0]["data"]["styles"]["picked"]["table"] == table_sid and r["view"]["style"] == table_sid
    a = _apply(c, d, v["id"], "p1", rid="r-1", rev=0)
    assert a.status_code == 200, a.text
    made = a.json()["applied"]["made"]
    assert (made["rows"], made["cols"]) == (4, 3) and a.json()["applied"]["excel"]["ok"] == 2
    b = _apply(c, d, v["id"], "p2", rid="r-2", rev=0)
    assert b.status_code == 200, b.text
    new = b.json()["applied"]["written"]["paras"]
    texts = {x["id"]: x["text"] for x in s.doc.blocks() if x["type"] == "paragraph"}
    assert len(new) == 3 and [texts[i].split()[-1] for i in new] == ["100", "50", "150"] and all(texts[i].endswith(ln["text"]) for i, ln in zip(new, lines))   # 레터는 스크립트가 붙인다
    assert texts[new[0]].lstrip().startswith("□") and texts[new[1]].lstrip().startswith("o")
    rs = _apply(c, d, v["id"], "p3", rid="r-3", rev=0)
    assert rs.status_code == 200 and rs.json()["applied"]["formatted"]["table"] == "t1"
    _llm(monkeypatch, {"reply": "", "actions": [{"type": "restyle", "table": "", "style": text_sid, "paras": new[1:], "item": "i1"}]})
    v2 = _turn(c, d, "모양만", selection={"paras": new[1:]}).json()["turn"]
    assert v2["proposals"][0]["view"]["item"] == "i1" and v2["proposals"][0]["view"]["paras"] == new[1:] and _apply(c, d, v2["id"], rid="r-4", rev=s.rev).status_code == 200
    for _ in range(4):
        assert c.post(f"/api/docs/{d}/undo").status_code == 200
    assert [x["id"] for x in server.DOCS[d].doc.blocks()] == ["t1", "t8"]


# ---- 서식 복사(행동 styleCopy — spec_서식복사 ② §6 「에이전트 추출 ②」): 문서를 바꾸지 않는 반영 --------------------------------------

def _pick(kind, table="", template="", paras=(), name="", blueprint=False):
    return {"kind": kind, "table": table, "template": template, "paras": list(paras), "name": name, "blueprint": blueprint}


def _copy(*picks):
    return {"type": "styleCopy", "after": "", "mode": "", "style": "", "table": "", "range": "", "paras": [], "item": "", "lines": [], "candidates": [], "picks": list(picks)}


@pytest.fixture
def lib(monkeypatch):
    """서식 보관함 모듈과 함께(보관함은 시험마다 임시 폴더 — conftest NFM_STYLES) → (style_api, style_lib). PDF 검증·추출 모듈은 뗀다(검증 스레드가 시험 사이로 새지 않게 — tests/test_style_api.py 와 같다).
    개요 템플릿은 없는 것으로 고정(2단계 결과와 무관하게 — 쓰는 시험은 `A.templates_of` 를 따로 바꾼다)."""
    style_api, style_lib = pytest.importorskip("app.style_api"), pytest.importorskip("app.style_lib")
    monkeypatch.setattr(style_api, "_mod", lambda name: None)
    monkeypatch.setattr(A, "templates_of", lambda graph, cap=A.TEMPLATES_MAX: [])
    return style_api, style_lib


def _prop(c, d, k=0):
    """다시 읽은 화면의 k번째 턴 첫 제안."""
    return c.get(f"/api/docs/{d}/agent").json()["turns"][k]["proposals"][0]


def test_style_copy_turn_then_apply_saves_styles_and_leaves_the_document(c, monkeypatch, lib):
    style_api, style_lib = lib
    d = _upload(c)
    s = server.DOCS[d]
    para = _cell_para(s, "t8", "기술수요 과제명")
    seen = []
    act = _copy(_pick("table", table="t8", name="수요조사 표 — 머리열"), _pick("text", paras=[para], name="칸 글"), _pick("table", table="t8", name="같은 표"), _pick("table", table="t999"),
                _pick("text", template="7"))
    _llm(monkeypatch, {"reply": "서식 둘을 저장합니다", "actions": [act]}, seen)
    r = _turn(c, d, "이 표 서식 저장해줘", selection={"paras": [para], "table": "t8", "range": None, "cursor": None})
    assert r.status_code == 200, r.text
    v = r.json()["turn"]
    (p,) = v["proposals"]
    assert seen[0]["data"]["templates"] == [] and list(seen[0]["data"])[:5] == ["request", "selection", "outline", "tables", "templates"]
    assert (p["type"], p["title"], p["state"], p["preselect"], p["baseRev"], p["warn"]) == ("styleCopy", "서식 복사 — 테이블 서식 1 · 템플릿 1", "open", True, 0, []) and "op" not in p
    assert [(x["kind"], x["kindName"], x["name"]) for x in p["view"]["picks"]] == [("table", "테이블 서식", "수요조사 표 — 머리열"), ("text", "템플릿", "칸 글")]
    assert p["view"]["picks"][0]["summary"].startswith("표 18×11") and p["view"]["picks"][1]["summary"] == "문단 1개" and p["target"]["looks"] == ["t8", para]
    assert [(x["action"], x["pick"]) for x in v["dropped"]] == [(0, 2), (0, 3), (0, 4)] and v["notes"] == [] and s.rev == 0                    # 같은 대상 · 없는 표 · 보낸 적 없는 템플릿 — 그 pick 만 버린다
    assert "같은 대상" in v["dropped"][0]["why"] and "문서에 없습니다" in v["dropped"][1]["why"] and A.NOT_SENT in v["dropped"][2]["why"]
    assert A.Store(d).turn(v["id"])["proposals"][0]["op"] == {"picks": [{"kind": "table", "name": "수요조사 표 — 머리열", "table": "t8", "blueprint": False}, {"kind": "text", "name": "칸 글", "paras": [para]}]}
    # 반영 — 보관함에 저장만: 문서 차례·실행 취소 그대로 · 문서 조각 없는 응답
    a = _apply(c, d, v["id"], rev=0)
    assert a.status_code == 200, a.text
    av = a.json()
    st = av["applied"]["styles"]
    assert set(av) == {"replayed", "applied", "rev"} and av["replayed"] is False and av["rev"] == 0 and s.rev == 0 and len(s.undo) == 0 and len(s.doc.blocks()) == 2
    assert av["applied"] == {"turn": v["id"], "proposal": "p1", "type": "styleCopy", "state": "applied", "styles": st, "failed": []}
    assert [(x["name"], x["kind"], x["revision"], x["pick"]) for x in st] == [("수요조사 표 — 머리열", "table", "r1", 0), ("칸 글", "text", "r1", 1)]
    saved = [style_lib.get(x["id"]) for x in st]
    assert len(style_lib.listing()["styles"]) == 2 and saved[0]["source"]["block"] == "t8" and saved[0]["source"]["work"] == d and saved[0]["blueprint"] is None and len(saved[1]["items"]) == 1
    ev = [e for e in works.events(d) if e["kind"] == "agentApply"]
    assert len(ev) == 1 and (ev[0]["type"], ev[0]["styles"], ev[0]["failed"], ev[0]["rev"], ev[0]["turn"]) == ("styleCopy", 2, 0, 0, v["id"])
    assert [e["kind"] for e in works.events(d)].count("styleSave") == 2
    kept = _prop(c, d)
    assert kept["state"] == "applied" and kept["applied"]["styles"] == st and kept["applied"]["failed"] == [] and (kept["applied"]["rev"], kept["applied"]["note"]) == (0, "서식 2개 저장")
    assert (kept["applied"]["table"], kept["applied"]["paras"], kept["applied"]["cells"]) == (None, [], [])                                    # 자리로 갈 곳은 없다(문서에 넣은 것이 없다)
    assert c.get(f"/api/docs/{d}/agent").json()["styles"]["table"][0]["id"] == st[0]["id"]                                                     # 저장한 서식은 서식 고르기에 보인다
    # 같은 requestId — 영수증만(다시 저장하지 않는다) · 이미 반영한 제안 409
    again = _apply(c, d, v["id"], rev=0)
    assert again.status_code == 200 and again.json()["replayed"] is True and again.json()["applied"] == av["applied"] and again.json()["rev"] == 0 and len(style_lib.listing()["styles"]) == 2
    dup = _apply(c, d, v["id"], rid="r-2", rev=0)
    assert dup.status_code == 409 and "이미 반영" in dup.json()["detail"] and len(style_lib.listing()["styles"]) == 2
    # 낡은 제안: 다른 표만 바뀌었으면 그대로 저장 · 고른 표가 바뀌었으면 409(본 것과 다른 서식을 저장하지 않는다)
    _llm(monkeypatch, {"reply": "", "actions": [_copy(_pick("table", table="t8", name="다시 저장"))]})
    v2 = _turn(c, d, "이 표 서식 저장해줘").json()["turn"]
    assert c.patch(f"/api/docs/{d}/blocks/{_cell_para(s, 't1', '별첨')}", json={"text": "별첨 1"}).status_code == 200 and s.rev == 1           # 다른 표의 칸
    fine = _apply(c, d, v2["id"], rid="r-3", rev=0)
    assert fine.status_code == 200 and fine.json()["rev"] == 1 and s.rev == 1 and [x["name"] for x in fine.json()["applied"]["styles"]] == ["다시 저장"]
    _llm(monkeypatch, {"reply": "", "actions": [_copy(_pick("table", table="t8", name="셋째"))]})
    v3 = _turn(c, d, "이 표 서식 저장해줘").json()["turn"]
    assert v3["proposals"][0]["baseRev"] == 1 and c.patch(f"/api/docs/{d}/blocks/{para}", json={"text": "과제 이름"}).status_code == 200 and s.rev == 2
    late = _apply(c, d, v3["id"], rid="r-4", rev=1)
    assert late.status_code == 409 and late.json()["detail"] == A.STALE and len(style_lib.listing()["styles"]) == 3 and s.rev == 2
    assert _prop(c, d, 2)["state"] == "stale" and _apply(c, d, v3["id"], rid="r-5", rev=2).status_code == 409


def test_style_copy_applies_on_a_source_document_and_reports_partial_failure(c, monkeypatch, lib):
    style_api, style_lib = lib
    d = _upload(c)
    s = server.DOCS[d]
    works.update(d, task={"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": ""})          # 이관의 사업계획서 = 원본 문서(문서를 바꾸는 반영은 403)
    assert c.get(f"/api/docs/{d}/agent").json()["policy"]["apply"] is False
    _llm(monkeypatch, {"reply": "", "actions": [_copy(_pick("table", table="t8", name="조사서 표"), _pick("table", table="t1", name="별첨 표")), _write(mode="draft")]})
    v = _turn(c, d, "이 문서 서식 복사해줘").json()["turn"]
    assert [x["type"] for x in v["proposals"]] == ["styleCopy", "write"]
    assert _apply(c, d, v["id"], "p2", rid="r-w", rev=0).status_code == 403 and _apply(c, d, v["id"], "p9", rid="r-x", rev=0).status_code == 403   # 글 쓰기 · 없는 제안은 전처럼 정책이 먼저
    real, locked = style_api.save_doc_style, []

    def flaky(sess, body):                                                                                   # 둘째 pick 만 실패
        locked.append(sess.lock.locked())
        if body.get("table") == "t1":
            raise HTTPException(400, "끊어진 참조가 있어 저장하지 않습니다")
        return real(sess, body)
    monkeypatch.setattr(style_api, "save_doc_style", flaky)
    a = _apply(c, d, v["id"], "p1", rev=0)                                                                   # 서식 복사는 문서를 바꾸지 않는다 — 원본 문서에서도 된다
    assert a.status_code == 200, a.text
    ap = a.json()["applied"]
    assert ap["state"] == "applied" and [(x["name"], x["pick"]) for x in ap["styles"]] == [("조사서 표", 0)]
    assert ap["failed"] == [{"name": "별첨 표", "why": "끊어진 참조가 있어 저장하지 않습니다", "kind": "table", "pick": 1}]
    assert locked == [False, False] and s.rev == 0 and len(s.undo) == 0 and a.json()["rev"] == 0 and len(style_lib.listing()["styles"]) == 1       # 세션 잠금 밖에서 부른다(그 함수가 안에서 잡는다)
    kept = _prop(c, d)
    assert kept["state"] == "applied" and kept["applied"]["note"] == "서식 1개 저장 · 실패 1" and kept["applied"]["failed"] == ap["failed"]
    ev = [e for e in works.events(d) if e["kind"] == "agentApply"]
    assert len(ev) == 1 and (ev[0]["styles"], ev[0]["failed"]) == (1, 1)
    assert _apply(c, d, v["id"], "p1", rid="r-2", rev=0).status_code == 409                                  # 하나라도 저장됐으면 「반영됨」
    # 모두 실패 — 200 + failed, 제안은 열어 둔다 → 새 requestId 로 다시 반영할 수 있다
    _llm(monkeypatch, {"reply": "", "actions": [_copy(_pick("table", table="t8", name="조사서 표 2"), _pick("page", name="문서 서식"))]})
    v2 = _turn(c, d, "이 문서 서식 복사해줘").json()["turn"]

    def off(sess, body):
        raise HTTPException(503, "서식 보관함이 꺼져 있습니다")
    monkeypatch.setattr(style_api, "save_doc_style", off)
    b = _apply(c, d, v2["id"], "p1", rid="r-3", rev=0)
    assert b.status_code == 200 and b.json()["applied"]["state"] == "open" and b.json()["applied"]["styles"] == []
    assert [(x["name"], x["why"], x["kind"]) for x in b.json()["applied"]["failed"]] == [("조사서 표 2", "서식 보관함이 꺼져 있습니다", "table"), ("문서 서식", "서식 보관함이 꺼져 있습니다", "page")]
    assert _prop(c, d, 1)["state"] == "open" and "applied" not in _prop(c, d, 1) and len(style_lib.listing()["styles"]) == 1
    again = _apply(c, d, v2["id"], "p1", rid="r-3", rev=0)
    assert again.status_code == 200 and again.json()["replayed"] is True and again.json()["applied"] == b.json()["applied"]                        # 같은 requestId 는 그 영수증
    saved = []
    monkeypatch.setattr(style_api, "save_doc_style", lambda sess, body: saved.append(body) or {"id": f"{len(saved):012x}", "name": body["name"], "kind": body["kind"], "revision": "r1"})
    ok = _apply(c, d, v2["id"], "p1", rid="r-4", rev=0)
    assert ok.status_code == 200 and ok.json()["applied"]["state"] == "applied" and [x["kind"] for x in ok.json()["applied"]["styles"]] == ["table", "page"]
    assert saved == [{"kind": "table", "name": "조사서 표 2", "table": "t8", "blueprint": False}, {"kind": "page", "name": "문서 서식"}] and s.rev == 0 and len(s.doc.blocks()) == 2


def test_style_copy_templates_are_sent_bound_and_never_stale(c, monkeypatch, lib):
    style_api, _ = lib
    rows = [{"id": "1", "no": 1, "name": "1.", "chain": ["1.", "□"], "levels": 2}]
    monkeypatch.setattr(A, "templates_of", lambda graph, cap=A.TEMPLATES_MAX: rows)                           # 2단계 그래프의 개요 템플릿(그래프 → 이 꼴은 tests/test_doc_agent.py)
    d = _upload(c)
    s = server.DOCS[d]
    seen, saved = [], []
    _llm(monkeypatch, {"reply": "", "actions": [_copy(_pick("text", template="1", name="개요 2레벨"), _pick("page"), _pick("text", template="2"))]}, seen)
    v = _turn(c, d, "이 문서 서식 복사해줘").json()["turn"]
    (p,) = v["proposals"]
    assert seen[0]["data"]["templates"] == rows and p["title"] == "서식 복사 — 템플릿 1 · 문서 서식 1" and p["view"]["picks"][0]["summary"] == "T1 · 1. › □" and p["preselect"] is True
    assert p["target"]["blocks"] == [] and [x["pick"] for x in v["dropped"]] == [2] and A.NOT_SENT in v["dropped"][0]["why"]                     # 보낸 적 없는 템플릿
    monkeypatch.setattr(style_api, "save_doc_style", lambda sess, body: saved.append(body) or {"id": f"{len(saved):012x}", "name": body.get("name") or "기본 이름", "kind": body["kind"], "revision": "r1"})
    monkeypatch.setattr(API, "_style_api", lambda: None)
    assert _apply(c, d, v["id"], rid="r-0", rev=0).status_code == 503 and _prop(c, d)["state"] == "open" and saved == []                          # 보관함 모듈 없음 — 제안은 열린 채
    monkeypatch.setattr(API, "_style_api", lambda: style_api)
    assert c.patch(f"/api/docs/{d}/blocks/{_cell_para(s, 't1', '별첨')}", json={"text": "별첨 1"}).status_code == 200 and s.rev == 1
    a = _apply(c, d, v["id"], rev=0)                                                                         # 가리키는 블록이 없는 제안(템플릿 · 문서 서식)은 문서가 바뀌어도 낡지 않는다
    assert a.status_code == 200, a.text
    assert saved == [{"kind": "text", "name": "개요 2레벨", "template": "1"}, {"kind": "page"}] and a.json()["rev"] == 1 and s.rev == 1           # 이름이 비면 name 을 안 보낸다(기본 이름은 서버가)
    assert [(x["name"], x["kind"], x["pick"]) for x in a.json()["applied"]["styles"]] == [("개요 2레벨", "text", 0), ("기본 이름", "page", 1)]

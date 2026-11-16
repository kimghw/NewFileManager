"""에이전트 보기(spec_일반편집 ② §8~§12 — app/static/doc_agent.js) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_agent_ui.py <그림·임시 폴더> [--port 18401]

에이전트 끝점(`…/agent…`)과 보관함 목록(`/api/styles`)은 **흉내**다(page.route — 정규식: glob `agent**` 은 아래 경로에 안 맞는다). 문서·작업·TASK 저장은 진짜 서버.
작은 문서(기술수요조사서 hwpx 둘 · docx 하나)로 본다:
- 패널 머리 첫 탭 「에이전트」(2026-11-16 — 문서 위 탭 띠에서 옮김) — hwpx 에만 · 누르면 패널에 보기(상태 줄 · 대화 · 입력) / docx 는 탭 없음.
- 요청: 고른 자리 줄(커서 · 표) · 「보내기」(보낸 몸 = text·materials·selection·styles) → 도는 동안 보낸 요청이 턴으로 + 동그라미 + 「요청을 읽는 중 · n초」 · 입력 꺼짐 → 답 · 제안 카드.
- 카드: 종류 꼬리표 · 스크립트가 확인한 제안만 강조 단추 · 에이전트가 쓴 글(draft)은 「읽고 반영」 · 표 구조 후보는 한 카드의 라디오 · 엑셀 검증(맞음 / 안 맞음(빨강) / 검산할 수식 없음) · 올리면 문서의 그 자리 보라.
- 2열 미리보기(표 채우기 — 체크) → 다른 2열(서식 보관함)로 바꿨다 돌아와도 고른 것이 남음 · 「지침」 열.
- 반영: 보낸 몸 = {turn, proposal, expectedRev, requestId}(+ 표 채우기는 picks.fills) → 「반영됨 — 자리로」 · 「엑셀식 보기」 · 「이 표를 서식으로 저장」 / 409 → 「문서가 바뀌었습니다 — 다시 요청하세요」 / 403 → 「원본 문서 — 제안은 보기만」.
- 자료 붙여넣기 → 칩 · 다음 요청의 materials 에 그 id · 칩을 끄면 빠짐 · × 로 지움. 요청 실패(502) → 그 까닭 + 요청 글이 글상자에 남음. 「비우기」 는 두 번.
- 폭: 패널 320 · 480px 에서 가로 넘침 없음. 끝점이 없을 때(404) 한 줄 까닭 · 입력 꺼짐.
- 「일반 문서」 작업(TASK 문서 일반 편집): 열면 에이전트 보기부터 · 다른 TASK 와 같은 「에이전트」 탭(「작업 내용」 탭은 없음) · 오른쪽 묶음(검증 · PDF · 기록 — 작업 리스트는 상단 바 아이콘) 펼치기·접기 · 시작 화면 카드로 시작.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18401)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []
SMALL = "기술수요조사서.hwpx"
STALE = "문서가 바뀌었습니다 — 다시 요청하세요"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:500] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def upload(name):
    p = ROOT / "samples" / name
    return requests.post(f"{base}/api/docs?new=1", files={"file": (name, p.read_bytes())}, timeout=120).json()["docId"]


def open_work(page, wid):
    page.evaluate("(id) => { location.hash = '#w=' + id; }", wid)
    page.reload()
    page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=wid, timeout=120000)


# ---- 흉내 서버(에이전트 끝점) — S 가 서버의 상태, calls 가 받은 요청, held 가 답을 미뤄 둔 요청 ----
S = {"enabled": True, "policy": {"apply": True, "why": ""}, "turns": [], "materials": [], "apply": "ok", "missing": False, "turn_fail": False,
     "styles": {"table": [{"id": "s_tbl1", "name": "예산 총괄표", "bands": {"headerRows": 2, "headerCols": 1, "footRows": 1}, "rows": 6, "cols": 5, "blueprint": True, "fidelity": "native", "verify": {"status": "ok"}}],
                "text": [{"id": "s_txt1", "name": "본문 글머리", "items": [{"key": "i1", "name": "□ 줄", "level": 1, "marker": {"mode": "literal", "literal": "□"}, "sample": "견본 글입니다"}]}]}}
calls = {"turn": [], "apply": [], "material": [], "material_del": [], "clear": 0, "guide": [], "get": 0}
held = {}
AG = re.compile(r"/api/docs/[0-9a-f]{12}/agent(/[^?]*)?(\?.*)?$")
IDS = {}  # 문서의 진짜 자리 — after 문단 · 표 · 칸(열고 나서 채운다)


def js(route, body, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body, ensure_ascii=False))


def turn_body(tid, text):
    excel_ok = {"formulas": 3, "ok": 3, "mismatch": 0, "missing": 0, "incomplete": 0, "blank": 0, "nonnumeric": 0, "examples": [], "note": "", "status": "ok"}
    excel_bad = {"formulas": 3, "ok": 2, "mismatch": 1, "missing": 0, "incomplete": 0, "blank": 0, "nonnumeric": 0, "note": "", "status": "mismatch",
                 "examples": [{"ref": "D4", "formula": "=D2+D3", "expected": 120, "actual": 121, "status": "mismatch"}]}
    grid = lambda rows, cols: {"rows": [{"cells": [{"text": f"r{r}c{c}", "rowSpan": 1, "colSpan": 1} for c in range(cols)]} for r in range(rows)], "headerRows": 1, "headerCols": 1, "footRows": 1}
    props = [
        {"id": "p1", "type": "write", "title": "추진 일정 3줄", "summary": "자료의 일정 문장을 그대로 옮깁니다", "state": "open", "baseRev": 0, "choiceGroup": None, "preselect": True, "warn": [],
         "checks": [{"what": "source", "status": "pass", "text": "근거 구절 3/3 확인"}],
         "target": {"block": IDS["after"], "blocks": [IDS["after"]], "hash": "h1"},
         "view": {"after": IDS["after"], "mode": "extract", "style": "", "styleName": "자리 둘레 서식", "lines": [{"item": "", "itemName": "", "text": "1차년도: 설계 기준 수립", "source": "1차년도: 설계 기준 수립", "quoted": True, "warn": []},
                                                                                                         {"item": "", "itemName": "", "text": "2차년도: 시제품 제작", "source": "2차년도 시제품", "quoted": False, "warn": ["근거 구절을 못 찾음"]}]}},
        # draft 의 알림은 서버가 warn[] 에 싣고, checks[] 에도 같은 말이 온다(화면은 한 번만 보인다)
        {"id": "p2", "type": "write", "title": "기대 효과 문단", "summary": "요청대로 새로 쓴 글입니다", "state": "open", "baseRev": 0, "choiceGroup": None, "preselect": False, "warn": ["에이전트가 쓴 글 — 읽고 반영하세요"],
         "checks": [{"what": "draft", "status": "warn", "text": "에이전트가 쓴 글 — 읽고 반영하세요"}],
         "view": {"after": IDS["after"], "mode": "draft", "style": "s_txt1", "styleName": "본문 글머리", "styleFrom": "보고서.docx · 갑 과제 · 개요템플릿 1 외 1개 문서", "lines": [{"item": "i1", "itemName": "□ 줄", "text": "본 기술은 운항 효율을 높인다.", "source": "", "quoted": False, "warn": []}]}},
        {"id": "p3", "type": "tableNew", "title": "연차별 가로 배치", "summary": "", "state": "open", "baseRev": 0, "choiceGroup": "g1", "preselect": True, "warn": [], "checks": [{"what": "excel", "status": "pass", "text": "엑셀 검증 — 수식 3 · 맞음 3"}], "excel": excel_ok,
         "view": {"after": IDS["after"], "style": "builtin", "styleName": "기본 표", "why": "연차가 열 — 합계가 오른쪽", "grid": grid(4, 5), "gridChanges": [], "rows": 4, "cols": 5}},
        {"id": "p4", "type": "tableNew", "title": "항목별 세로 배치", "summary": "", "state": "open", "baseRev": 0, "choiceGroup": "g1", "preselect": False, "warn": ["후보 사이에 수 모둠이 다릅니다"],
         "checks": [{"what": "numbers", "status": "warn", "text": "후보 사이에 수 모둠이 다릅니다"}, {"what": "excel", "status": "warn", "text": "엑셀 검증 — 안 맞음 1"}], "excel": excel_bad,
         "view": {"after": IDS["after"], "style": "builtin", "styleName": "기본 표", "why": "항목이 열 — 합계가 아래", "grid": grid(6, 3), "gridChanges": ["빈 행 1개를 뺌"], "rows": 6, "cols": 3}},
        {"id": "p5", "type": "tableFill", "title": f"표 {IDS['table']} 채우기", "summary": "자료에서 찾은 값 2칸", "state": "open", "baseRev": 0, "choiceGroup": None, "preselect": True, "warn": [], "checks": [],
         "excel": {"formulas": 0, "ok": 0, "mismatch": 0, "missing": 0, "incomplete": 0, "blank": 0, "nonnumeric": 0, "examples": [], "note": "", "status": "unknown"},
         "view": {"table": IDS["table"], "range": None, "rows": 18, "cols": 11, "unit": "천원", "answer": "기간은 자료에 날짜가 없어 어림했습니다.", "picked": [IDS["cells"][0]],  # picked = 서버가 골라 둔 칸
                  "counts": {"targets": 5, "fills": 2, "clean": 1, "warn": 1, "rejected": 1, "left": 3},
                  "fills": [{"ref": "B1", "cell": IDS["cells"][0], "name": "과제명", "form": "text", "now": "", "text": "해양 플랜트 설계", "source": "과제명: 해양 플랜트 설계", "where": "material", "reason": "", "quoted": True, "warn": []},
                            {"ref": "B2", "cell": IDS["cells"][1], "name": "기간", "form": "date", "now": "", "text": "2026.01.01", "source": "내년 초", "where": "material", "reason": "", "quoted": False, "warn": ["근거 구절을 자료에서 못 찾음"]}],
                  "rejected": [{"ref": "C9", "text": "x", "why": "채울 칸이 아닌 주소"}]}},
        {"id": "p6", "type": "restyle", "title": "표 서식 입히기", "summary": "보관한 「예산 총괄표」 서식", "state": "open", "baseRev": 0, "choiceGroup": None, "preselect": True, "warn": [], "checks": [],
         "view": {"table": IDS["table"], "rows": 18, "cols": 11, "style": "s_tbl1", "styleName": "예산 총괄표"}},
    ]
    return {"id": tid, "at": time.time(), "text": text, "reply": "자료에서 일정과 예산을 찾았습니다. 아래 제안을 확인하세요.", "notes": ["표 t1 은 채울 칸이 없어 뺐습니다"], "error": None, "proposals": props,
            "dropped": [{"action": 2, "type": "write", "why": "넣을 자리가 칸 안"}], "call": {"backend": "api", "model": "claude-fable-5-2", "effort": "medium", "ms": 12345, "costUsd": 0.0421, "error": None}, "calls": 2}


def agent(route):
    req = route.request
    tail = (AG.search(req.url).group(1) or "")
    if S["missing"]:  # 끝점이 아직 없는 서버
        return js(route, {"detail": "Not Found"}, 404)
    if tail == "" and req.method == "GET":
        calls["get"] += 1
        return js(route, {"enabled": S["enabled"], "hwpx": True, "policy": S["policy"], "turns": S["turns"], "materials": S["materials"], "styles": S["styles"]})
    if tail == "" and req.method == "DELETE":
        calls["clear"] += 1
        S["turns"] = []
        return js(route, {"ok": True})
    if tail == "/turn":
        calls["turn"].append(json.loads(req.post_data))
        if S["turn_fail"]:  # LLM 호출 실패 — 서버는 그 턴을 까닭과 함께 저장해 돌려준다({detail, turn})
            bad = {"id": f"t{len(S['turns']) + 1}", "at": time.time(), "text": calls["turn"][-1]["text"], "reply": "", "notes": [], "error": "LLM 호출이 실패했습니다(시간 초과)", "proposals": [], "dropped": [],
                   "call": {"backend": "api", "model": "claude-fable-5-2", "ms": 60000, "costUsd": None, "error": "timeout"}, "calls": 1}
            S["turns"].append(bad)
            return js(route, {"detail": "LLM 호출이 실패했습니다(시간 초과)", "turn": bad}, 502)
        held["turn"] = route  # 답은 검사가 낸다 — 그동안 화면은 도는 중
        return None
    if tail == "/apply":
        body = json.loads(req.post_data)
        calls["apply"].append(body)
        if body["proposal"] == "sc1":  # 서식 복사 제안(spec_서식복사 ② §6) — 문서를 안 바꾼다: 쓰기 정책에 안 걸리고, 응답에 문서 조각이 없다
            return js(route, {"applied": {"turn": body["turn"], "proposal": "sc1", "type": "styleCopy", "state": "applied", "styles": [{"id": "s_new1", "name": "예산 총괄표 — 머리 2행·합계행", "kind": "table", "revision": "r1"}],
                                          "failed": [{"name": "주 개요 템플릿", "why": "그 템플릿을 찾지 못했습니다"}]}, "rev": 0})
        if S["apply"] == "stale":
            return js(route, {"detail": STALE}, 409)
        if S["apply"] == "policy":
            return js(route, {"detail": "원본 문서는 바꾸지 않습니다"}, 403)
        pid = body["proposal"]
        applied = {"turn": body["turn"], "proposal": pid, "type": {"p1": "write", "p3": "tableNew", "p5": "tableFill"}.get(pid, "write"), "state": "applied"}
        if pid == "p5":
            applied["filled"] = {"table": IDS["table"], "cells": body["picks"]["fills"], "skipped": []}
            applied["excel"] = {"formulas": 2, "ok": 2, "mismatch": 0, "missing": 0, "incomplete": 0, "blank": 0, "nonnumeric": 0, "examples": [], "note": ""}
        elif pid == "p3":
            applied["made"] = {"table": IDS["table"], "rows": 4, "cols": 5}  # 새 표 id 대신 문서에 있는 표(「자리로」·「엑셀식 보기」 가 닿게)
        else:
            applied["written"] = {"paras": []}
        for t in S["turns"]:
            group = next((p.get("choiceGroup") for p in t["proposals"] if p["id"] == pid), None)
            for p in t["proposals"]:
                if p["id"] == pid:
                    p["state"] = "applied"
                elif group and p.get("choiceGroup") == group:
                    p["state"] = "closed"  # 후보 묶음은 하나만
        # 구조 편집 응답 — 바뀐 블록 없이(화면은 문서를 통째로 다시 읽는다: app.js applyTops → reloadDoc)
        return js(route, {"tops": {"drop": [], "blocks": []}, "texts": {}, "edited": [], "kinds": {}, "unrestored": [], "pristine": True, "undo": 1, "original": {}, "rev": body["expectedRev"], "applied": applied})
    if tail.startswith("/turns/"):
        calls["guide"].append(tail)
        return js(route, {"parts": [{"key": "contract", "title": "계약(코드에 든 글)", "text": "자료·선택·문서에 있는 것만 쓴다."}, {"key": "guide", "title": "지침 agent.md", "text": "합계는 계산해 넣지 않는다."},
                                    {"key": "request", "title": "요청", "text": "붙인 자료로 일정과 예산표를 정리해 줘"}, {"key": "data", "title": "자료(JSON)", "text": "{\"outline\": []}"},
                                    {"key": f"fill:{IDS['table']}", "title": "표 채우기 호출", "text": "…"}], "response": {"reply": "…", "actions": []}, "calls": [{"backend": "api", "model": "claude-fable-5-2", "ms": 9000, "costUsd": 0.03}]})
    if tail == "/material" and req.method == "POST":
        body = json.loads(req.post_data)
        m = {"id": f"m{len(calls['material']) + 1}", "name": body.get("name") or "붙여 넣은 글", "kind": "text", "chars": len(body["text"]), "cut": False, "head": body["text"][:300]}
        calls["material"].append(body)
        S["materials"].append(m)
        return js(route, m)
    if tail.startswith("/material/") and req.method == "DELETE":
        mid = tail.rsplit("/", 1)[1]
        calls["material_del"].append(mid)
        S["materials"] = [m for m in S["materials"] if m["id"] != mid]
        return js(route, {"ok": True, "materials": S["materials"]})
    return js(route, {"detail": f"흉내에 없는 끝점 {req.method} {tail}"}, 500)


def styles(route):  # 보관함 목록(「서식 보관함」 단추 — 2열을 바꿔 보는 데만 쓴다)
    js(route, {"enabled": True, "pdf": False, "broken": [], "styles": [
        {"id": "s_tbl1", "revision": "r1", "kind": "table", "name": "예산 총괄표", "source": {"name": "양식.hwpx", "format": "hwpx"}, "fidelity": "native", "losses": 0, "bands": {"headerRows": 2, "headerCols": 1, "footRows": 1},
         "rows": 6, "cols": 5, "blueprint": True, "verify": None}]})


VIS = "(id) => { const e = document.getElementById(id); return !!e && !e.hidden && e.getClientRects().length > 0; }"
TOOL = "() => document.getElementById('panel').dataset.tool"
HT = [["헤딩 추출", "false"], ["표", "false"]]  # 2026-11-16 — 헤딩 추출 · 표는 패널 머리의 고정 탭(에이전트 · 작업 내용 다음 — spec_작업 ② §10 「둘째 줄」)
TABS = """() => { const t = document.getElementById('toolTabs'); return [...t.querySelectorAll('[role=tab]')].filter((b) => !b.hidden && b.getClientRects().length).map((b) => [b.textContent, b.getAttribute('aria-selected')]); }"""
CARDS = """() => [...document.querySelectorAll('#paneAgent .ag-card')].map((c) => { const a = c.querySelector('[data-ag-act=apply]'), q = (s) => [...c.querySelectorAll(s)].map((e) => e.textContent);
  return { prop: c.dataset.prop, type: c.dataset.type, state: c.dataset.state, group: c.dataset.group || '', tag: (c.querySelector('.ag-tag') || {}).textContent, title: (c.querySelector('.ag-title') || {}).textContent,
    apply: a ? a.textContent : null, primary: !!a && a.classList.contains('primary'), off: a ? a.disabled : null, radios: [...c.querySelectorAll('input[type=radio]')].map((r) => [r.value, r.checked]),
    checks: q('.ag-check'), bad: q('.ag-check.bad'), acts: [...c.querySelectorAll('[data-ag-act]')].map((b) => b.dataset.agAct), stateText: q('.ag-state').join(' | ') }; })"""
FIT = """() => { const p = document.getElementById('panel'), r = p.getBoundingClientRect();
  const bad = [...p.querySelectorAll('#paneAgent *')].filter((e) => e.getClientRects().length && e.getBoundingClientRect().right > r.right + 0.5).slice(0, 6).map((e) => (e.className || e.tagName) + ':' + (e.textContent || '').slice(0, 20));
  const over = ['#panel', '#paneAgent', '#paneAgent .ag-talk', '#paneAgent .ag-input', '#paneAgent .ag-status', '#panel .tool-heading'].map((s) => { const e = document.querySelector(s); return [s, e.scrollWidth - e.clientWidth]; }).filter((x) => x[1] > 0);
  return { w: Math.round(r.width), bad, over }; }"""
card = lambda cs, pid: next((c for c in cs if c["prop"] == pid), None)

try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    a, g, d = upload(SMALL), upload(SMALL), upload("기술수요조사서.docx")
    doc = requests.get(f"{base}/api/docs/{a}", timeout=60).json()
    tops = doc["blocks"]
    tbl = next(b for b in tops if b["type"] == "table" and len(b.get("cells") or []) >= 4)
    first_para = lambda c: next((x["id"] for x in c.get("blocks") or [] if x["type"] == "paragraph"), None)
    other = next(b for b in tops if b["id"] != tbl["id"])  # 넣을 자리로 쓸 본문 최상위 블록(이 예제는 최상위가 표 둘뿐 — 그 표 뒤)
    IDS.update(after=other["id"], after_para=next(p for p in map(first_para, other.get("cells") or []) if p), table=tbl["id"], cells=[c["id"] for c in tbl["cells"][:2]],
               cell_para=next(p for p in map(first_para, tbl["cells"]) if p))
    put = requests.put(f"{base}/api/works/{g}/task", json={"kind": "general", "job": "doc_edit", "file": "", "project": ""}, timeout=10)
    check("서버가 「일반 문서 · 문서 일반 편집」 조합을 받는다(PUT …/task)", put.ok and put.json()["task"]["kind"] == "general", put.text[:200])
    bad = requests.put(f"{base}/api/works/{a}/task", json={"kind": "rnd", "job": "doc_edit", "file": "", "project": ""}, timeout=10)
    check("어긋난 조합(연구개발 프로젝트 + 문서 일반 편집)은 400", bad.status_code == 400, bad.status_code)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        sent = []
        page.on("request", lambda r: sent.append((r.method, r.url)))
        page.route(AG, agent)
        page.route(re.compile(r"/api/styles(\?.*)?$"), styles)
        page.route(re.compile(r"/api/styles/s_new1$"), lambda route: js(route, {"id": "s_new1", "name": "예산 총괄표 — 머리 2행·합계행", "kind": "table", "revision": "r1", "docx": {"sha256": "x", "losses": []},  # 서식 복사 카드가 저장 뒤 다시 읽는 서식(두 형식의 검증)
                                                                                 "verify": {"status": "ok", "coverage": None, "stale": False}, "verifyDocx": {"status": "warn", "coverage": None, "stale": False}}))
        page.route(re.compile(r"/api/docs/[0-9a-f]{12}/styles/candidates$"), lambda route: js(route, {"rev": 0, "stage2": False, "tables": [], "texts": []}))  # 「이 표를 서식으로 저장」 이 여는 열
        # 서식 그림(spec_서식복사 ② §13)의 견본 — 후보 = POST …/styles/preview(저장과 같은 몸) · 보관한 서식 = GET /api/styles/{sid} 의 view. 둘 다 흉내(작은 표 명세)
        PIC = {"rows": 2, "cols": 2, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "widthsMm": [40, 60],
               "cells": [{"row": r, "col": c, "rowSpan": 1, "colSpan": 1, "text": "구분" if r == 0 else "0", "fill": "#E6E6E6" if r == 0 else None, "valign": "CENTER",
                          "edges": {k: {"type": "SOLID", "width": "0.12 mm", "color": "#000000"} for k in "trbl"}, "format": {"font": "맑은 고딕", "sizePt": 10, "bold": r == 0, "align": "center"}} for r in range(2) for c in range(2)]}
        previews = []
        page.route(re.compile(r"/api/docs/[0-9a-f]{12}/styles/preview$"), lambda route: (previews.append(json.loads(route.request.post_data or "{}")), js(route, {"rev": 0, "kind": "table", "view": {"spec": PIC}, "losses": [], "fidelity": "native"}))[1])
        page.route(re.compile(r"/api/styles/s_tbl1$"), lambda route: js(route, {"id": "s_tbl1", "revision": "r1", "kind": "table", "name": "예산 총괄표", "losses": [], "verify": None, "view": {"spec": PIC}}))
        page.goto(base)
        page.evaluate("() => { try { localStorage.clear(); } catch {} }")
        open_work(page, a)

        # ---- 1. 패널 머리 첫 탭 「에이전트」(2026-11-16 — 탭 띠에서 옮김) — hwpx 에만 · 누르면 패널에 보기
        check("hwpx 문서 — 패널 머리 첫 탭 「에이전트」 · 탭 띠에는 없음 · 처음 보기는 검증(접힌 묶음에서 고른 탭만)", page.evaluate(VIS, "tabAgent") and page.evaluate(TOOL) == "Verify"
              and page.evaluate("() => !!document.getElementById('tabAgent').closest('#toolTabs') && !document.querySelector('#workspaceNav #tabAgent')")
              and page.evaluate(TABS) == [["에이전트", "false"], *HT, ["검증", "true"]], page.evaluate(TABS))
        check("에이전트 끝점은 탭을 열기 전에는 안 부른다", calls["get"] == 0, calls["get"])
        page.click("#tabAgent")
        page.wait_for_function("() => AGENT.loaded && !!document.querySelector('#paneAgent .ag-status[data-llm=on]')")
        check("탭을 누르면 패널에 에이전트 보기 · 탭이 고른 꼴 · 접힌 묶음(검증·PDF·기록)은 다 감춤", page.evaluate(TOOL) == "Agent" and page.evaluate(VIS, "paneAgent") and page.get_attribute("#tabAgent", "aria-selected") == "true"
              and page.evaluate(TABS) == [["에이전트", "true"], *HT] and page.evaluate(VIS, "toolMore"), page.evaluate(TABS))
        st = page.evaluate("() => ({ text: document.querySelector('#paneAgent .ag-status-text').textContent, btns: [...document.querySelectorAll('#paneAgent .ag-status button')].filter((b) => !b.hidden).map((b) => [b.textContent, b.disabled]) })")   # 「작업 설명」(작업 진행 에이전트)은 단계가 있는 TASK 에서만 보인다 — 일반 편집에는 없다
        check("상태 줄 — LLM 사용 가능 · 「서식 관리자」 · 「비우기」(대화가 없어 꺼짐)", "LLM 사용 가능" in st["text"] and st["btns"] == [["서식 관리자", False], ["비우기", True]], st)
        check("빈 대화 안내 · 「보내기」 는 글이 없어 꺼짐", "제안만 냅니다" in page.inner_text("#paneAgent .ag-empty") and page.is_disabled("#paneAgent [data-ag-act=send]"))
        picks = page.evaluate("() => [...document.querySelectorAll('#paneAgent .ag-pick select')].map((s) => [...s.options].map((o) => [o.value, o.textContent]))")
        check("서식 고르기 — 표: 정하지 않음 · 기본 표 · 보관한 표 서식 / 글: 자리 둘레 서식 · 보관한 글 서식", picks == [[["", "정하지 않음"], ["builtin", "기본 표"], ["s_tbl1", "예산 총괄표"]], [["", "자리 둘레 서식"], ["s_txt1", "본문 글머리"]]], picks)
        check("고른 자리 줄 — 처음에는 없음", "고른 자리 없음" in page.inner_text("#paneAgent .ag-sel"), page.inner_text("#paneAgent .ag-sel"))
        page.screenshot(path=str(OUT / "1_agent_empty.png"))

        # 「지금 할 수 있는 일」(2026-11-16 — spec_일반편집 ② §12): 현황 보고(늘 · 첫 줄) · 아직 안 한 LLM 검토(유료) · 서식 반영. 보고는 스크립트 카드(화면에만 · 에이전트 끝점을 안 부름)
        nxt = page.evaluate("() => [...document.querySelectorAll('#paneAgent .ag-next button')].map((b) => b.textContent.trim())")
        check("빈 화면 「지금 할 수 있는 일」 — 첫 줄 「현재 작업 진행 현황 보고」", nxt[:1] == ["현재 작업 진행 현황 보고"], nxt)
        page.click("#paneAgent .ag-next button >> nth=0")
        page.wait_for_selector("#paneAgent .ag-report .ds-grid", timeout=20000)
        rep = page.evaluate("() => [...document.querySelectorAll('#paneAgent .ag-report .ds-row-name')].map((e) => e.textContent)")
        check("현황 보고 카드 — 진행표와 같은 줄(헤딩 · 표 …) · 편집 줄 · 에이전트 끝점은 안 부름", "헤딩" in rep and "표" in rep and "고친 문단" in page.inner_text("#paneAgent .ag-report")
              and not calls["turn"], rep)
        page.evaluate("() => { AGENT.local = []; agentDrawTalk(); }")  # 아래 검사의 카드 수에 섞이지 않게(화면에만 둔 카드)
        # 요청 예시는 글상자만 채운다 — 전송은 사람이 「보내기」를 눌렀을 때만.
        examples = page.locator("#paneAgent .ag-empty > .ag-examples > .ag-example")  # 「지금 할 수 있는 일」 의 줄 단추도 같은 꼴(.ag-example)이라 예시 묶음 안만
        prompts = ["붙인 자료로 고른 표를 채워 줘", "고른 문단을 표로 정리해 줘", "이 자리에 추진 일정을 써 줘"]
        check("요청 예시 셋 — 자료로 표 채우기 · 문단을 표로 정리하기 · 추진 일정 작성하기", examples.all_text_contents() == ["자료로 표 채우기", "문단을 표로 정리하기", "추진 일정 작성하기"])
        for n, prompt in enumerate(prompts):
            page.fill("#agentRequest", "")
            examples.nth(n).click()
            check(f"요청 예시 {n + 1} — 입력·초점만, 전송 없음", page.input_value("#agentRequest") == prompt
                  and page.evaluate("() => AGENT.draft === document.getElementById('agentRequest').value && document.activeElement === document.getElementById('agentRequest')")
                  and page.is_enabled("#paneAgent [data-ag-act=send]") and not calls["turn"] and not held.get("turn"))
        page.fill("#agentRequest", "기존에 작성한 요청")
        examples.first.click()
        check("요청 예시는 기존 초안을 보존하고 다음 줄에 추가", page.input_value("#agentRequest") == "기존에 작성한 요청\n" + prompts[0] and not calls["turn"])
        page.fill("#agentRequest", "")

        # ---- 2. 고른 자리 — 문서의 선택 상태를 그대로(커서 · 표)
        page.click(f'#doc .para[data-id="{IDS["after_para"]}"]')
        page.wait_for_function("(a) => { const t = document.querySelector('#paneAgent .ag-sel').textContent; return t.includes('표 ' + a[0]) && t.includes('커서 ' + a[1]); }", arg=[IDS["after"], IDS["after_para"]])
        page.click(f'#doc .para[data-id="{IDS["cell_para"]}"]')
        page.wait_for_function("(a) => { const t = document.querySelector('#paneAgent .ag-sel').textContent; return t.includes('표 ' + a[0]) && t.includes('커서 ' + a[1]); }", arg=[IDS["table"], IDS["cell_para"]])
        check("문단·표 칸을 누르면 고른 자리 줄이 따라온다(표 · 커서) · 한 줄 높이 고정", page.evaluate("() => Math.round(document.querySelector('#paneAgent .ag-sel').getBoundingClientRect().height)") == 18, page.inner_text("#paneAgent .ag-sel"))
        opts = page.evaluate("() => [...document.querySelector('#paneAgent select[data-ag-pick=table]').options].map((o) => o.value)")
        check("표를 고르면 표 서식 고르기에 「이 문서의 표」", opts == ["", "builtin", "s_tbl1", "doc"], opts)
        page.select_option("#paneAgent select[data-ag-pick=table]", "doc")
        page.select_option("#paneAgent select[data-ag-pick=text]", "s_txt1")

        # ---- 3. 자료 붙여넣기 → 칩
        page.click("#paneAgent [data-ag-act=paste]")
        check("「자료 붙여넣기」 — 그 자리에 글상자가 열린다(대화창 아님)", page.locator("#paneAgent .ag-paste").is_visible() and page.locator("dialog[open]").count() == 0)
        page.fill("#paneAgent .ag-paste input[type=text]", "과제 개요")
        page.fill("#paneAgent .ag-paste textarea", "과제명: 해양 플랜트 설계\n1차년도: 설계 기준 수립")
        page.click("#paneAgent [data-ag-act=pasteAdd]")
        page.wait_for_selector("#paneAgent .ag-chip[data-material=m1]")
        chip = page.inner_text("#paneAgent .ag-chip[data-material=m1] .ag-chip-name")
        check("자료 칩 — 이름 · 글자 수 · × · 글상자는 닫힘 · 보낸 몸 = {name, text}", "과제 개요" in chip and "자" in chip and page.locator("#paneAgent .ag-chip .ag-chip-x").count() == 1
              and not page.locator("#paneAgent .ag-paste").is_visible() and calls["material"] == [{"name": "과제 개요", "text": "과제명: 해양 플랜트 설계\n1차년도: 설계 기준 수립"}], (chip, calls["material"]))

        # ---- 4. 요청 → 도는 동안 → 답 · 카드
        page.fill("#agentRequest", "붙인 자료로 일정과 예산표를 정리해 줘")
        check("글을 쓰면 「보내기」 가 켜진다(강조 단추)", page.is_enabled("#paneAgent [data-ag-act=send]") and "primary" in page.get_attribute("#paneAgent [data-ag-act=send]", "class"))
        page.click("#paneAgent [data-ag-act=send]")
        page.wait_for_function("() => !!AGENT.busy && !!document.querySelector('#paneAgent .ag-turn.pending')")
        for _ in range(50):  # 흉내 서버가 요청을 받을 때까지
            if "turn" in held:
                break
            page.wait_for_timeout(100)
        page.wait_for_timeout(1300)
        pend = page.evaluate("""() => { const t = document.querySelector('#paneAgent .ag-turn.pending'), run = t.querySelector('.ag-run');
          return { q: t.querySelector('.ag-q').textContent, spin: !!run.querySelector('.ag-spin') && getComputedStyle(run.querySelector('.ag-spin')).animationName, text: run.textContent,
            off: [...document.querySelectorAll('#agentRequest, #paneAgent .ag-pick select, #paneAgent [data-ag-act=send], #paneAgent [data-ag-act=paste], #paneAgent .ag-chip button')].map((e) => e.disabled),
            draft: document.querySelector('#agentRequest').value, inRun: document.querySelector('#paneAgent .ag-send .ag-run').textContent }; }""")
        check("도는 동안 — 보낸 요청이 바로 턴으로 · 동그라미 + 「요청을 읽는 중 · n초」(초가 간다) · 입력 꺼짐", pend["q"] == "붙인 자료로 일정과 예산표를 정리해 줘" and pend["spin"] == "spin"
              and re.fullmatch(r"요청을 읽는 중 · [1-9]\d*초", pend["text"]) and all(pend["off"]) and pend["draft"] == "" and "요청을 읽는 중" in pend["inRun"], pend)
        page.screenshot(path=str(OUT / "4_agent_pending.png"))
        req = calls["turn"][0]
        check("보낸 몸 — text · materials(붙인 자료 id) · selection(표·커서) · styles(이 문서의 표 · 글 서식)", req["text"] == "붙인 자료로 일정과 예산표를 정리해 줘" and req["materials"] == ["m1"]
              and req["selection"] == {"paras": [], "table": IDS["table"], "range": None, "cursor": IDS["cell_para"]} and req["styles"] == {"table": f"doc:{IDS['table']}", "text": "s_txt1"}, req)
        turn = turn_body("t1", req["text"])
        S["turns"].append(turn)
        js(held.pop("turn"), {"turn": turn})
        page.wait_for_function("() => !AGENT.busy && document.querySelectorAll('#paneAgent .ag-card').length === 5")
        cs = page.evaluate(CARDS)
        check("답 · 카드 다섯(글 쓰기 둘 · 새 표 후보 묶음 하나 · 표 채우기 · 서식 입히기) · 입력이 다시 켜짐", page.inner_text("#paneAgent .ag-turn .ag-a").startswith("자료에서 일정과 예산을 찾았습니다")
              and [c["tag"] for c in cs] == ["글 쓰기", "글 쓰기", "새 표", "표 채우기", "서식 입히기"] and page.is_enabled("#agentRequest") and not page.locator("#paneAgent .ag-turn.pending").count(), [c["tag"] for c in cs])
        c1, c2, c3, c5 = card(cs, "p1"), card(cs, "p2"), card(cs, "p3"), card(cs, "p5")
        check("스크립트가 확인한 제안 — 강조 단추 「문서에 반영」", c1["apply"] == "문서에 반영" and c1["primary"] and not c1["off"] and "스크립트 검사 통과 1" in " ".join(c1["checks"]), c1)
        check("에이전트가 쓴 글(draft) — 강조 아님 · 「읽고 반영」 · 「에이전트가 쓴 글 — 읽고 반영하세요」", c2["apply"] == "읽고 반영" and not c2["primary"] and c2["checks"] == ["에이전트가 쓴 글 — 읽고 반영하세요"], c2)  # 서버 warn[] 의 말 — checks[] 에 되풀이된 같은 말은 한 번만
        check("표 구조 후보 — 한 카드의 라디오 둘(스크립트가 확인한 첫 후보가 골라짐) · 단추 하나", c3 and c3["group"] == "g1" and c3["radios"] == [["p3", True], ["p4", False]] and c3["title"] == "표 구조 후보 2개 — 하나만 반영"
              and c3["acts"].count("apply") == 1 and c3["primary"] and any("엑셀 검증 — 수식 3 · 맞음 3" in x for x in c3["checks"]) and not card(cs, "p4"), c3)
        check("표 채우기 — 수 · 「검산할 수식 없음」 · 경고 없는 칸만 고른 채 「고른 1칸 문서에 반영」", c5["apply"] == "고른 1칸 문서에 반영" and any("채울 칸 5 · 제안 2(경고 1)" in x for x in c5["checks"]) and any("검산할 수식 없음" in x for x in c5["checks"]), c5)
        meta = page.inner_text("#paneAgent .ag-turn .ag-meta")
        lay = page.evaluate("""() => { const r = (s) => document.querySelector(s).getBoundingClientRect(), p = r('#panel'), i = r('#paneAgent .ag-input'), t = document.querySelector('#paneAgent .ag-talk'), s = r('#paneAgent .ag-status');
          return { inBottom: Math.round(p.bottom - i.bottom), inTop: i.top > s.bottom, talkScroll: t.scrollHeight > t.clientHeight, turnTop: Math.round(r('#paneAgent .ag-turn:last-child').top - t.getBoundingClientRect().top), statusTop: Math.round(s.top - r('#panel .tool-heading').bottom) }; }""")
        check("배치 — 상태 줄은 머리 바로 아래 · 입력은 패널 맨 아래에 늘 보임 · 대화만 굴림(새 답은 그 턴의 머리부터 보임)", lay["inBottom"] == 0 and lay["inTop"] and lay["talkScroll"] and 0 <= lay["turnTop"] <= 12 and lay["statusTop"] == 0, lay)
        check("호출 줄 — 시간 · 비용 · 모델 · 호출 수 · 「지침」 / 버린 행동 1", "12.3초" in meta and "$0.042" in meta and "claude-fable-5-2" in meta and "호출 2" in meta and "지침" in meta
              and "검사에서 버린 행동 1" in page.inner_text("#paneAgent .ag-dropped summary") and "채울 칸이 없어 뺐습니다" in page.inner_text("#paneAgent .ag-turn .ag-note"), meta)
        page.locator("#paneAgent").screenshot(path=str(OUT / "4_agent_cards.png"))

        # 후보 고르기 — 둘째(엑셀 검증 안 맞음)는 강조 아님 · 빨강
        page.click("#paneAgent .ag-card[data-group=g1] input[value=p4]")  # 고르면 카드를 다시 그린다 — check() 가 아니라 누름
        page.wait_for_function("() => document.querySelector('#paneAgent .ag-card[data-group=g1]').dataset.prop === 'p4'")
        c4 = card(page.evaluate(CARDS), "p4")
        color = page.evaluate("() => getComputedStyle(document.querySelector('#paneAgent .ag-card[data-group=g1] .ag-check.bad')).color")
        check("둘째 후보 — 「안 맞음 1」 + 첫 예(빨강) · 경고 · 「읽고 반영」(강조 아님)", c4 and c4["radios"] == [["p3", False], ["p4", True]] and any("안 맞음 1" in x and "D4" in x and "120" in x for x in c4["bad"]) and color == "rgb(200, 30, 30)"
              and c4["apply"] == "읽고 반영" and not c4["primary"] and sum("후보 사이에 수 모둠이 다릅니다" in x for x in c4["checks"]) == 1 and sum("안 맞음" in x for x in c4["checks"]) == 1
              and any("격자를 맞춤 — 빈 행 1개를 뺌" in x for x in c4["checks"]), (c4, color))  # 경고·엑셀 검증은 한 번씩만(checks[] 의 되풀이는 안 보인다)
        page.click("#paneAgent .ag-card[data-group=g1] input[value=p3]")
        page.wait_for_function("() => document.querySelector('#paneAgent .ag-card[data-group=g1]').dataset.prop === 'p3'")

        # 카드에 올리면 문서의 그 자리(보라) — 「뒤에 넣음」 은 아래 변 · 표는 테두리
        page.hover("#paneAgent .ag-card[data-prop=p1]")
        after = page.evaluate("(id) => { const e = slBlockEls(id).pop(); return [e.classList.contains('ag-after'), getComputedStyle(e).boxShadow]; }", IDS["after"])
        page.hover("#paneAgent .ag-card[data-prop=p5]")
        hit = page.evaluate("(id) => { const e = document.querySelector(`#doc table.tbl[data-tbl=\"${id}\"]`); return [e.classList.contains('ag-hit'), getComputedStyle(e).outlineColor, document.querySelectorAll('#doc .ag-after').length]; }", IDS["table"])
        page.hover("#paneAgent .ag-status")
        check("카드에 올리면 문서의 그 자리가 보라 — 넣을 자리는 아래 변 · 표는 테두리 · 떠나면 걷힘", after[0] and "124, 58, 237" in after[1] and hit[0] and "124, 58, 237" in hit[1] and hit[2] == 0
              and page.locator("#doc .ag-hit, #doc .ag-after").count() == 0, (after, hit))

        # ---- 5. 폭 — 패널 320 · 480px 에서 가로 넘침 없음(카드가 다 있는 채로)
        for width in (320, 480):
            page.evaluate("(w) => { const c = colSizers.find((x) => x.box === 'panel'); c.w = w; c.apply(); }", width)
            page.wait_for_timeout(300)
            fit = page.evaluate(FIT)
            check(f"패널 {width}px — 가로 넘침 없음", fit["w"] in (width - 1, width) and not fit["bad"] and not fit["over"], fit)
            page.locator("#panel").screenshot(path=str(OUT / f"5_agent_{width}.png"))
        page.evaluate("() => { const c = colSizers.find((x) => x.box === 'panel'); c.w = null; c.apply(); }")

        # ---- 6. 2열 미리보기 — 표 채우기(체크) · 2열을 바꿨다 돌아와도 고른 것이 남는다
        page.click("#paneAgent .ag-card[data-prop=p5] [data-ag-act=preview]")
        page.wait_for_selector("#headsDlg[data-kind=agentProp] table.tfl-list")
        boxes = page.evaluate("() => [...document.querySelectorAll('#headsDlg table.tfl-list tbody input[type=checkbox]')].map((c) => c.checked)")
        check("미리보기는 문서 옆 열(팝업 아님) · 채우기 목록 — 서버가 골라 둔 칸(view.picked)만 처음부터 고름 · 뺀 제안 접힘", page.evaluate(VIS, "headsDlg") and page.locator("dialog[open]").count() == 0 and boxes == [True, False]
              and page.locator("#headsDlg table.tfl-list tr.warn").count() == 1 and "검사에서 뺀 제안 1" in page.inner_text("#headsDlg details.more summary")
              and page.inner_text("#headsDlgFoot [data-ag-act=apply]") == "고른 1칸 문서에 반영", boxes)
        check("채우기 미리보기 — 대상 줄(표 · 크기 · 단위) · LLM 의 말", all(k in page.inner_text("#headsDlg .agp-where") for k in (f"표 {IDS['table']}", "18×11", "단위 천원")) and "LLM: 기간은 자료에 날짜가 없어" in page.inner_text("#headsDlgBody"),
              page.inner_text("#headsDlg .agp-where"))
        page.hover("#headsDlg table.tfl-list tbody tr:first-child")
        check("줄에 올리면 문서의 그 칸이 보라(표 채우기와 같은 표시)", page.locator(f'#doc td.tfl-hit[data-cell="{IDS["cells"][0]}"]').count() >= 1)
        page.check("#headsDlg table.tfl-list tbody tr:nth-child(2) input[type=checkbox]")
        check("칸을 더 고르면 카드·발치의 단추 글이 따라온다", page.inner_text("#paneAgent .ag-card[data-prop=p5] [data-ag-act=apply]") == "고른 2칸 문서에 반영" and page.inner_text("#headsDlgFoot [data-ag-act=apply]") == "고른 2칸 문서에 반영")
        page.screenshot(path=str(OUT / "6_agent_preview_fill.png"))
        page.click("#paneAgent [data-ag-act=library]")
        page.wait_for_selector("#headsDlg[data-kind=styleLib] [data-sl-tab=table]")  # 처음 갈래는 내용 서식(이 흉내 목록에는 테이블 서식뿐)
        check("2열을 「서식 관리자」 로 바꿔도 패널의 대화·카드는 그대로", page.locator("#paneAgent .ag-card").count() == 5 and page.evaluate(TOOL) == "Agent"
              and page.inner_text("#paneAgent .ag-card[data-prop=p5] [data-ag-act=apply]") == "고른 2칸 문서에 반영")
        page.click("#tabTables")
        page.click("#tabAgent")
        check("다른 도구(표)를 봤다 돌아와도 대화·카드·2열이 그대로", page.locator("#paneAgent .ag-card").count() == 5 and page.get_attribute("#headsDlg", "data-kind") == "styleLib" and page.evaluate(VIS, "headsDlg"))
        page.click("#paneAgent .ag-card[data-prop=p5] [data-ag-act=preview]")
        page.wait_for_selector("#headsDlg[data-kind=agentProp] table.tfl-list")
        boxes = page.evaluate("() => [...document.querySelectorAll('#headsDlg table.tfl-list tbody input[type=checkbox]')].map((c) => c.checked)")
        check("미리보기를 다시 열면 고른 칸이 그대로(상태는 DOM 밖)", boxes == [True, True], boxes)
        page.uncheck("#headsDlg table.tfl-list tbody tr:nth-child(2) input[type=checkbox]")  # 경고 줄은 다시 푼다 — 아래 반영은 한 칸
        page.click("#paneAgent .ag-card[data-group=g1] [data-ag-act=preview]")
        page.wait_for_selector("#headsDlg[data-kind=agentProp] .agp-col")
        cols = page.evaluate("() => [...document.querySelectorAll('#headsDlg .agp-col')].map((c) => ({ id: c.dataset.cand, on: c.classList.contains('on'), radio: c.querySelector('input[type=radio]').checked, cells: c.querySelectorAll('table.tm-grid td').length, head: c.querySelectorAll('td.head').length, foot: c.querySelectorAll('td.foot').length, left: Math.round(c.getBoundingClientRect().left) }))")
        check("표 후보 미리보기 — 격자 둘을 나란히(구역 색) · 고른 후보 표시", [(c["id"], c["on"], c["radio"], c["cells"]) for c in cols] == [("p3", True, True, 20), ("p4", False, False, 18)] and cols[0]["head"] == 5 and cols[0]["foot"] == 5
              and cols[1]["left"] > cols[0]["left"], cols)
        page.click("#headsDlg .agp-col[data-cand=p4] input[type=radio]")
        page.wait_for_function("() => document.querySelector('#paneAgent .ag-card[data-group=g1]').dataset.prop === 'p4'")
        check("미리보기에서 후보를 고르면 카드도 그 후보", page.evaluate("() => document.querySelector('#headsDlg .agp-col.on').dataset.cand") == "p4")
        page.screenshot(path=str(OUT / "6_agent_preview_table.png"))
        page.click("#paneAgent .ag-card[data-prop=p2] [data-ag-act=preview]")
        page.wait_for_selector("#headsDlg[data-kind=agentProp] table.agp-lines")
        where = page.inner_text("#headsDlg .agp-where")
        check("글 쓰기 미리보기 — 넣을 자리 · 방식(에이전트가 쓴 글) · 서식 이름 · 줄(입힐 항목 이름)", "뒤" in where and "에이전트가 쓴 글" in where and "본문 글머리 (원본 보고서.docx · 갑 과제 · 개요템플릿 1 외 1개 문서)" in where and page.locator("#headsDlg table.agp-lines tbody tr").count() == 1
              and "□ 줄" in page.inner_text("#headsDlg table.agp-lines tbody tr td:first-child"), where)
        page.click("#paneAgent .ag-card[data-prop=p1] [data-ag-act=preview]")
        page.wait_for_function("() => document.querySelectorAll('#headsDlg table.agp-lines tbody tr').length === 2")
        check("옮긴 글 미리보기 — 근거 구절 · 못 찾은 줄은 경고 표시(줄마다의 warn)", page.locator("#headsDlg table.agp-lines tbody tr.warn").count() == 1 and "근거 구절을 못 찾음" in page.inner_text("#headsDlg table.agp-lines tbody tr.warn")
              and page.locator("#headsDlg table.agp-lines q.tfl-noquote").count() == 1)

        # 「지침」 — 그 턴에 보낸 글(보기만)
        page.click("#paneAgent .ag-turn [data-ag-guide=t1]")
        page.wait_for_selector("#headsDlg[data-kind=agentGuide] details.lg-part")
        parts = page.evaluate("() => [...document.querySelectorAll('#headsDlg details.lg-part')].map((d) => [d.dataset.part, d.open])")
        check("「지침」 열 — 보낸 글 다섯(사람이 관리하는 지침·요청은 펴 둠 · 계약·자료·표 채우기 호출은 접음) · LLM 의 답 · 고칠 칸 없음",
              parts == [["contract", False], ["guide", True], ["request", True], ["data", False], [f"fill:{IDS['table']}", False]] and calls["guide"] == ["/turns/t1"]
              and page.locator("#headsDlg textarea, #headsDlg input").count() == 0 and "LLM 의 답" in page.inner_text("#headsDlgBody"), parts)
        page.click("#headsDlgClose")

        # ---- 7. 반영 — 서버에 저장한 제안을 실행(보낸 몸) · 카드가 「반영됨」
        rev = page.evaluate("() => state.serverRev")
        page.click("#paneAgent .ag-card[data-prop=p1] [data-ag-act=apply]")
        page.wait_for_function("() => document.querySelector('#paneAgent .ag-card[data-prop=p1]').dataset.state === 'applied'")
        b = calls["apply"][0]
        check("반영 요청의 몸 = {turn, proposal, expectedRev, requestId}(내용은 안 보낸다)", set(b) == {"turn", "proposal", "expectedRev", "requestId"} and b["turn"] == "t1" and b["proposal"] == "p1" and b["expectedRev"] == rev
              and isinstance(b["requestId"], str) and len(b["requestId"]) >= 8, b)
        c1 = card(page.evaluate(CARDS), "p1")
        check("카드가 「반영됨 — 자리로」 로 · 반영 단추 없음 · 알림에 실행 취소", c1["state"] == "applied" and c1["acts"] == ["preview", "go"] and "실행 취소" in page.inner_text("#toast"), c1)
        page.wait_for_function("() => !state.busy && document.querySelector('#doc .sheet .para') != null")
        page.click("#paneAgent .ag-card[data-prop=p1] [data-ag-act=go]")
        page.wait_for_timeout(300)
        page.click("#paneAgent .ag-card[data-prop=p5] [data-ag-act=apply]")
        page.wait_for_function("() => document.querySelector('#paneAgent .ag-card[data-prop=p5]').dataset.state === 'applied'")
        b = calls["apply"][1]
        c5 = card(page.evaluate(CARDS), "p5")
        check("표 채우기 반영 — picks.fills = 고른 칸만 · 다른 requestId", b["proposal"] == "p5" and b["picks"] == {"fills": [IDS["cells"][0]]} and b["requestId"] != calls["apply"][0]["requestId"], b)
        check("반영한 표 카드 — 「반영됨 — 자리로」 · 「엑셀식 보기」 · 「이 표를 서식으로 저장」 · 반영 뒤 엑셀 검증 · 채운 수", c5["acts"] == ["preview", "go", "excel", "saveStyle"]
              and any("반영 뒤 엑셀 검증 — 수식 2 · 맞음 2" in x for x in c5["checks"]) and "1칸 채움" in c5["stateText"], c5)
        page.wait_for_function("() => !state.busy")
        page.locator("#paneAgent").screenshot(path=str(OUT / "7_agent_applied.png"))

        # 표 구조 후보 — 하나를 반영하면 묶음이 끝난다(다른 후보 = closed)
        page.click("#paneAgent .ag-card[data-group=g1] input[value=p3]")
        page.wait_for_function("() => document.querySelector('#paneAgent .ag-card[data-group=g1]').dataset.prop === 'p3'")
        page.click("#paneAgent .ag-card[data-group=g1] [data-ag-act=apply]")
        page.wait_for_function("() => document.querySelector('#paneAgent .ag-card[data-group=g1]').dataset.state === 'applied'")
        cg = card(page.evaluate(CARDS), "p3")
        dis = page.evaluate("() => [...document.querySelectorAll('#paneAgent .ag-card[data-group=g1] input[type=radio]')].map((r) => [r.value, r.checked, r.disabled])")
        check("후보 하나를 반영 — 카드가 「반영됨」(엑셀식 보기 · 서식으로 저장) · 라디오 잠김 · 나머지 후보는 끝남(closed)", calls["apply"][2]["proposal"] == "p3" and cg["acts"] == ["preview", "go", "excel", "saveStyle"]
              and dis == [["p3", True, True], ["p4", False, True]] and page.evaluate("() => AGENT.turns[0].proposals.find((p) => p.id === 'p4').state") == "closed", (cg, dis))
        page.wait_for_function("() => !state.busy")
        page.click("#paneAgent .ag-card[data-group=g1] [data-ag-act=preview]")
        page.wait_for_selector("#headsDlg[data-kind=agentProp] .agp-col")
        states = page.evaluate("() => [...document.querySelectorAll('#headsDlg .agp-col')].map((c) => [c.dataset.cand, c.dataset.state, (c.querySelector('.ag-state') || {}).textContent, c.querySelector('input[type=radio]').disabled])")
        check("끝난 묶음의 미리보기 — 「문서에 반영한 후보」 / 「다른 후보를 반영함」 · 고를 수 없음", states == [["p3", "applied", "문서에 반영한 후보", True], ["p4", "closed", "다른 후보를 반영함", True]]
              and page.locator("#headsDlgFoot [data-ag-act=apply]").count() == 0, states)
        page.click("#paneAgent .ag-card[data-group=g1] [data-ag-act=saveStyle]")
        page.wait_for_selector("#headsDlg[data-kind=styleSave] .sl-cand")
        pick = page.evaluate("() => { const b = document.querySelector('#headsDlg .sl-cand[data-kind=table]'); return [b.dataset.cand, b.querySelector('.sl-crow > input').checked, b.querySelector('[data-sl-opt=blueprint] input').checked]; }")  # 테이블 서식 후보의 맨 앞 — 고른 채로 연 표라 「테이블 서식」 탭이 열린다(spec_서식복사 ② §18)
        check("「이 표를 서식으로 저장」 — 「서식 복사」 열이 그 표만 고른 채 · 「구조까지 저장」 켠 채로", pick == [f"pick:{IDS['table']}", True, True], pick)
        page.click("#headsDlgClose")

        # 409 — 문서가 바뀜
        S["apply"] = "stale"
        page.click("#paneAgent .ag-card[data-prop=p6] [data-ag-act=apply]")
        page.wait_for_function("() => document.querySelector('#paneAgent .ag-card[data-prop=p6]').dataset.state === 'stale'")
        cg = card(page.evaluate(CARDS), "p6")
        check("409 — 카드에 「문서가 바뀌었습니다 — 다시 요청하세요」 · 반영 단추 꺼짐", STALE in cg["stateText"] and cg["off"] is True and calls["apply"][3]["proposal"] == "p6", cg)
        # 403 — 원본 문서(정책)
        S["apply"] = "policy"
        page.click("#paneAgent .ag-card[data-prop=p2] [data-ag-act=apply]")
        page.wait_for_selector("#paneAgent .ag-policy:not([hidden])")
        cs = page.evaluate(CARDS)
        check("403 — 입력 위에 「원본 문서 — 제안은 보기만」 · 남은 반영 단추가 모두 꺼짐", page.inner_text("#paneAgent .ag-policy") == "원본 문서 — 제안은 보기만"
              and all(c["off"] for c in cs if c["apply"] is not None) and card(cs, "p2")["state"] == "open", [(c["prop"], c["off"]) for c in cs])
        S["apply"] = "ok"

        # ---- 8. 자료 — 다음 요청의 materials · 칩을 끄면 빠짐 · × 로 지움 · 요청 실패
        page.fill("#agentRequest", "둘째 요청")
        page.keyboard.press("Control+Enter")
        for _ in range(50):
            if "turn" in held:
                break
            page.wait_for_timeout(100)
        check("Ctrl+Enter 로 보냄 · 둘째 요청에도 자료 id", len(calls["turn"]) == 2 and calls["turn"][1]["materials"] == ["m1"] and calls["turn"][1]["text"] == "둘째 요청", calls["turn"][1:])
        t2 = {"id": "t2", "at": time.time(), "text": "둘째 요청", "reply": "무엇을 정리할지 알려 주세요.", "proposals": [], "dropped": [], "call": {"backend": "api", "model": "claude-fable-5-2", "ms": 800, "costUsd": 0.001, "error": None}}
        S["turns"].append(t2)
        js(held.pop("turn"), {"turn": t2})
        page.wait_for_function("() => !AGENT.busy && document.querySelectorAll('#paneAgent .ag-turn').length === 2")
        check("행동 없는 답(되묻기) — 카드 없이 답만", page.locator("#paneAgent .ag-turn:nth-child(2) .ag-card").count() == 0 and "알려 주세요" in page.inner_text("#paneAgent .ag-turn:nth-child(2) .ag-a"))
        page.click("#paneAgent .ag-chip[data-material=m1] .ag-chip-name")
        check("칩을 누르면 이번 요청에서 뺀다(눌림 풀림)", page.get_attribute("#paneAgent .ag-chip[data-material=m1] .ag-chip-name", "aria-pressed") == "false")
        S["turn_fail"] = True
        page.fill("#agentRequest", "셋째 요청")
        page.click("#paneAgent [data-ag-act=send]")
        page.wait_for_selector("#paneAgent .ag-turn .hwarn.fail")
        lost = page.inner_text("#paneAgent .ag-turn:last-child .hwarn.fail")
        check("LLM 호출 실패(502 — 서버가 그 턴을 저장해 돌려줌) — 대화에 그 턴이 까닭과 함께 남음 · 요청 글이 글상자에 남음 · 끈 자료는 안 보냄", "에이전트가 답하지 못했습니다" in lost and "시간 초과" in lost
              and page.locator("#paneAgent .ag-turn").count() == 3 and page.get_attribute("#paneAgent .ag-turn:last-child", "data-turn") == "t3" and page.locator("#paneAgent .ag-turn:last-child [data-ag-guide=t3]").count() == 1
              and page.input_value("#agentRequest") == "셋째 요청" and calls["turn"][2]["materials"] == [], (lost, calls["turn"][2]))
        S["turn_fail"] = False
        page.click("#paneAgent .ag-chip[data-material=m1] .ag-chip-x")
        page.wait_for_function("() => !document.querySelector('#paneAgent .ag-chip')")
        check("× — 자료를 지움(DELETE …/material/m1)", calls["material_del"] == ["m1"])

        # 「비우기」 — 한 번은 채비만, 한 번 더 눌러야 지운다
        page.click("#paneAgent [data-ag-act=clear]")
        check("「비우기」 한 번 — 아직 안 지움(「정말 비우기」)", calls["clear"] == 0 and page.inner_text("#paneAgent [data-ag-act=clear]") == "정말 비우기" and page.locator("#paneAgent .ag-card").count() == 5)
        page.click("#paneAgent [data-ag-act=clear]")
        page.wait_for_function("() => !document.querySelector('#paneAgent .ag-turn')")
        check("한 번 더 — 대화를 비움(DELETE …/agent) · 정책은 서버 것으로 다시", calls["clear"] == 1 and "제안만 냅니다" in page.inner_text("#paneAgent .ag-empty"))
        page.wait_for_function("() => document.querySelector('#paneAgent .ag-policy').hidden")

        # ---- 9. 끝점이 없는 서버(404) — 한 줄 까닭 · 입력 꺼짐 / LLM 꺼짐
        S["missing"] = True
        open_work(page, a)
        page.click("#tabAgent")
        page.wait_for_selector("#paneAgent .ag-talk .hwarn.fail")
        check("끝점 없음(404) — 「서버를 다시 켜야」 한 줄 · 「보내기」 꺼짐 · 「다시 읽기」", "서버를 다시 켜야" in page.inner_text("#paneAgent .ag-talk .hwarn.fail") and page.is_disabled("#paneAgent [data-ag-act=send]")
              and page.locator("#paneAgent .ag-talk button").inner_text() == "다시 읽기" and page.evaluate("() => document.querySelector('#paneAgent .ag-status').dataset.llm") == "off")
        fit = page.evaluate(FIT)
        check("끝점 없음 — 화면이 깨지지 않음(넘침 없음)", not fit["bad"] and not fit["over"], fit)
        S["missing"], S["enabled"] = False, False
        page.click("#paneAgent .ag-talk button")
        page.wait_for_function("() => AGENT.loaded")
        page.fill("#agentRequest", "요청")
        check("LLM 꺼짐 — 상태 줄에 까닭 · 「보내기」 꺼짐(보관함·자료는 됨)", "LLM 을 쓸 수 없습니다" in page.inner_text("#paneAgent .ag-status-text") and page.is_disabled("#paneAgent [data-ag-act=send]")
              and page.is_enabled("#paneAgent [data-ag-act=paste]") and page.is_enabled("#paneAgent [data-ag-act=library]"))
        S["enabled"] = True

        # ---- 10. 「일반 문서」 작업 — 열면 에이전트 보기부터 · 다른 TASK 와 같은 「에이전트」 탭(「작업 내용」 없음) · 오른쪽 묶음 펼치기·접기 · 원본 문서 정책
        S["turns"] = [turn_body("t1", "앞서 한 요청")]
        S["policy"] = {"apply": False, "why": "원본 문서는 바꾸지 않습니다"}
        open_work(page, g)
        page.wait_for_function("() => AGENT.loaded && document.querySelectorAll('#paneAgent .ag-card').length === 5")
        check("일반 문서 작업 — 열면 에이전트 보기 · 「에이전트」 탭(고름) · 「작업 내용」 탭 없음 · 묶음은 접힘", page.evaluate(TOOL) == "Agent" and page.evaluate(VIS, "paneAgent") and page.evaluate(VIS, "tabAgent")
              and not page.evaluate(VIS, "toolTabTask") and page.evaluate(TABS) == [["에이전트", "true"], *HT] and page.input_value("#panelTask") == "general"
              and page.get_attribute("#toolMore", "aria-expanded") == "false", page.evaluate(TABS))
        cs = page.evaluate(CARDS)
        check("원본 문서 정책(apply: false) — 「원본 문서 — 제안은 보기만」 · 반영 단추 꺼짐 · 미리보기는 됨", page.inner_text("#paneAgent .ag-policy") == "원본 문서 — 제안은 보기만" and all(c["off"] for c in cs)
              and page.is_enabled("#paneAgent .ag-card[data-prop=p1] [data-ag-act=preview]"), [(c["prop"], c["off"]) for c in cs])
        page.click("#toolMore")
        check("펼치기 — 오른쪽에 검증 · PDF · 기록(작업 리스트는 상단 바 아이콘) · 기억(nfm.toolMore)", page.evaluate(TABS) == [["에이전트", "true"], *HT, ["검증", "false"], ["PDF", "false"], ["기록", "false"]]
              and page.get_attribute("#toolMore", "aria-expanded") == "true" and page.evaluate("() => localStorage.getItem('nfm.toolMore')") == "1", page.evaluate(TABS))
        page.click("#tabVerify")
        check("다른 도구(검증)를 보면 「에이전트」 가 풀림", page.evaluate(TOOL) == "Verify" and page.evaluate(TABS) == [["에이전트", "false"], *HT, ["검증", "true"], ["PDF", "false"], ["기록", "false"]], page.evaluate(TABS))
        page.click("#toolMore")
        check("접기 — 묶음에서 고른 「검증」 하나만 남음", page.evaluate(TABS) == [["에이전트", "false"], *HT, ["검증", "true"]] and page.get_attribute("#toolMore", "aria-expanded") == "false", page.evaluate(TABS))
        page.click("#tabAgent")
        check("「에이전트」 를 누르면 에이전트 보기로(대화 그대로)", page.evaluate(TOOL) == "Agent" and page.locator("#paneAgent .ag-card").count() == 5 and page.evaluate(TABS) == [["에이전트", "true"], *HT], page.evaluate(TABS))
        check("일반 문서 작업에는 구분 기준 내용(작업 내용 Div)이 안 열린다", page.evaluate("() => { showTab('Div'); return document.getElementById('panel').dataset.tool; }") == "Agent")
        # ---- 10-1. 서식 복사 제안(type styleCopy — spec_서식복사 ② §6): 원본 문서(반영 금지)에서도 「보관함에 저장」 은 된다 · 문서는 안 바뀜 · 저장 뒤 서식마다 검증 꼬리표 · 「서식 관리자에서 보기」
        page.evaluate("""(tbl) => { AGENT.turns.push({ id: 't9', at: Date.now() / 1000, text: '이 문서의 서식을 저장해 줘', reply: '저장할 서식을 골랐습니다.', notes: [], error: null, dropped: [], call: {}, calls: 1,
          proposals: [{ id: 'sc1', type: 'styleCopy', title: '서식 복사 — 테이블 서식 1 · 템플릿 1 · 문서 서식 1', summary: '', state: 'open', baseRev: 0, choiceGroup: null, preselect: true, warn: [], checks: [],
            view: { picks: [{ kind: 'table', table: tbl, name: '예산 총괄표 — 머리 2행·합계행', blueprint: true }, { kind: 'text', template: 'tpl1', name: '주 개요 템플릿' }, { kind: 'page', name: '계획서 문서 서식' }] } }] });
          agentDrawTalk(true); }""", IDS["table"])
        SC = """() => { const c = document.querySelector('#paneAgent .ag-card[data-prop=sc1]'); return { tag: c.querySelector('.ag-tag').textContent, state: c.dataset.state,
          rows: [...c.querySelectorAll('.ag-style')].map((r) => [r.dataset.kind, r.querySelector('.hb').textContent, r.querySelector('b').textContent, [...r.querySelectorAll('.sl-verify')].map((v) => v.textContent)]),
          acts: [...c.querySelectorAll('[data-ag-act]')].map((b) => [b.dataset.agAct, b.textContent, b.disabled]), text: c.textContent }; }"""
        sc = page.evaluate(SC)
        check("서식 복사 카드 — 꼬리표 「서식 복사」 · 저장할 서식 목록(갈래 이름 — 테이블 서식 · 내용 서식 · 쪽 설정) · 「보관함에 저장」 은 원본 문서에서도 켜짐 · 미리보기 대신 「서식 그림 보기」", sc["tag"] == "서식 복사"
              and [r[:3] for r in sc["rows"]] == [["table", "테이블 서식", "예산 총괄표 — 머리 2행·합계행"], ["text", "내용 서식", "주 개요 템플릿"], ["page", "쪽 설정", "계획서 문서 서식"]]
              and sc["acts"] == [["apply", "보관함에 저장", False], ["pics", "서식 그림 보기", False]] and "구조까지" in sc["text"], sc)
        # 「서식 그림 보기」(spec_서식복사 ② §13) — 2열 「서식 복사」 보기에 그 제안의 대상을 고른 채로(같은 견본 길) · 3열 카드 안에는 큰 그림이 없다
        n_prev = len(previews)
        page.click("#paneAgent .ag-card[data-prop=sc1] [data-ag-act=pics]")
        page.wait_for_selector(f'#headsDlg[data-kind=styleSave] .sl-cand[data-cand="pick:{IDS["table"]}"] .sp-pic[data-sp-kind=table]', timeout=15000)
        pv = page.evaluate("""(tid) => { const b = document.querySelector(`#headsDlg .sl-cand[data-cand="pick:${tid}"]`);
          return { on: b.querySelector('.sl-crow > input').checked, name: b.querySelector('.sl-cname').value, bp: b.querySelector('[data-sl-opt=blueprint] input').checked, tds: b.querySelectorAll('.sp-pic .sp-tbl td').length,
                   inCard: document.querySelectorAll('#paneAgent .sp-pic').length, dialogs: document.querySelectorAll('dialog[open]').length, save: document.querySelector('#headsDlgFoot [data-sl-act=save]').textContent }; }""", IDS["table"])
        check("「서식 그림 보기」 — 2열 「서식 복사」 가 제안의 표를 고른 채(제안의 이름 · 구조까지) 그 서식 그림(저장될 견본)을 보임 · 견본 요청은 저장과 같은 몸 · 카드(3열) 안에는 그림 없음 · 팝업 없음",
              pv == {"on": True, "name": "예산 총괄표 — 머리 2행·합계행", "bp": True, "tds": 4, "inCard": 0, "dialogs": 0, "save": "고른 1개 저장"}
              and {"kind": "table", "table": IDS["table"], "keepText": False} in previews and len(previews) - n_prev <= 1, (pv, previews))  # 같은 문서의 같은 표를 앞에서 이미 받았으면 다시 받지 않는다(견본은 열쇠로 기억)
        n_apply, rev0 = len(calls["apply"]), page.evaluate("() => [state.serverRev, state.undo]")
        page.click("#paneAgent .ag-card[data-prop=sc1] [data-ag-act=apply]")
        page.wait_for_selector("#paneAgent .ag-card[data-prop=sc1] .sl-verify[data-format=docx]", timeout=15000)
        sc, b = page.evaluate(SC), calls["apply"][n_apply]
        check("「보관함에 저장」 — 같은 반영 끝점(몸 = turn·proposal·expectedRev·requestId) · 문서 차례·실행 취소는 그대로 · 카드가 「보관함에 저장함」", b["turn"] == "t9" and b["proposal"] == "sc1" and "requestId" in b and "expectedRev" in b
              and page.evaluate("() => [state.serverRev, state.undo]") == rev0 and sc["state"] == "applied" and "보관함에 저장함 — 서식 1개" in sc["text"], (b, sc))
        check("저장 뒤 — 서식마다 검증 꼬리표(형식마다) · 못 저장한 것의 까닭 · 「서식 관리자에서 보기」", sc["rows"] == [["table", "테이블 서식", "예산 총괄표 — 머리 2행·합계행", ["hwpx 검증됨", "docx 확인 필요"]]]
              and "저장하지 못함 — 주 개요 템플릿: 그 템플릿을 찾지 못했습니다" in sc["text"] and sc["acts"] == [["toLib", "서식 관리자에서 보기", False]], sc)
        page.click("#paneAgent .ag-card[data-prop=sc1] [data-ag-act=toLib]")
        page.wait_for_selector("#headsDlg[data-kind=styleLib]")
        check("「서식 관리자에서 보기」 — 문서 옆 열 「서식 관리자」(테이블 서식을 고른 채)", page.inner_text("#headsDlgTitle") == "서식 관리자" and page.get_attribute("#headsDlgTools [data-sl-tab=table]", "aria-pressed") == "true")
        for width in (320, 480):
            page.evaluate("(w) => { const c = colSizers.find((x) => x.box === 'panel'); c.w = w; c.apply(); }", width)
            page.wait_for_timeout(300)
            fit = page.evaluate(FIT)
            check(f"일반 문서 작업 · 패널 {width}px — 가로 넘침 없음(탭 셋 · 정책 줄)", fit["w"] in (width - 1, width) and not fit["bad"] and not fit["over"], fit)
        page.locator("#panel").screenshot(path=str(OUT / "10_general_480.png"))
        page.evaluate("() => { const c = colSizers.find((x) => x.box === 'panel'); c.w = null; c.apply(); }")
        # 패널 머리의 「작업」 을 연구개발 프로젝트로 바꾸면 다른 종류의 할 일은 비운다(서버의 조합 규칙) → 다시 일반 문서
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{g}/task") and r.request.method == "PUT") as put:
            page.select_option("#panelTask", "rnd")
        page.wait_for_selector("#divBox .dv-task select")
        check("작업 = 연구개발 프로젝트로 — 저장됨(할 일 비움) · 작업 내용(Div) · 탭 = 「에이전트」 · 「작업 내용」(고름)", put.value.status == 200 and put.value.json()["task"]["job"] == "" and page.evaluate(TOOL) == "Div"
              and page.evaluate(TABS)[:2] == [["에이전트", "false"], ["작업 내용", "true"]], (put.value.status, page.evaluate(TABS)))
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{g}/task") and r.request.method == "PUT") as put:
            page.select_option("#panelTask", "general")
        page.wait_for_function("() => document.getElementById('panel').dataset.tool === 'Agent'")
        check("작업 = 일반 문서로 — 저장됨 · 에이전트 보기 · 「에이전트」 탭 고름 · 「작업 내용」 탭 없음", put.value.status == 200 and put.value.json()["task"]["kind"] == "general" and page.evaluate(VIS, "tabAgent")
              and page.get_attribute("#tabAgent", "aria-selected") == "true" and not page.evaluate(VIS, "toolTabTask"))
        S["policy"] = {"apply": True, "why": ""}

        # ---- 11. docx — 탭 없음
        open_work(page, d)
        check("docx — 「에이전트」 탭 없음 · showTab('Agent') 도 안 열림", not page.evaluate(VIS, "tabAgent") and page.evaluate("() => { showTab('Agent'); return document.getElementById('panel').dataset.tool; }") == "Verify")

        # ---- 12. 시작 화면 카드 「문서 일반 편집」 으로 시작 — 작업 종류 일반 문서 · 에이전트 보기부터
        page.click("#homeLink")
        page.wait_for_function("() => !state.id && !document.getElementById('empty').hidden")
        tone = page.evaluate("() => { const c = document.querySelector('#taskCards [data-task=doc_edit]'), lg = c.querySelector('.task-logo'); return [c.querySelector('.task-card-doc').textContent, c.querySelector('.task-card-name').textContent, lg.dataset.doc, getComputedStyle(lg).color]; }")
        check("시작 화면 — 「문서 / 일반 편집」 카드 · 로고 바탕은 회색(any — 보라 아님)", tone == ["문서", "일반 편집", "any", "rgb(75, 85, 99)"], tone)
        before = {w["id"] for w in requests.get(f"{base}/api/works", timeout=10).json()}
        with page.expect_file_chooser() as fc:
            page.click("#taskCards [data-task=doc_edit]")
        fc.value.set_files(str(ROOT / "samples" / "연구개발계획서_양식.hwpx"))
        page.wait_for_function("() => state.id && state.task && state.task.job === 'doc_edit' && document.getElementById('panel').dataset.tool === 'Agent' && AGENT.loaded", timeout=240000)
        t = page.evaluate("() => ({ id: state.id, task: state.task, tabs: [...document.querySelectorAll('#toolTabs [role=tab]')].filter((b) => !b.hidden).map((b) => [b.textContent, b.getAttribute('aria-selected')]) })")
        saved = next((w for w in requests.get(f"{base}/api/works", timeout=10).json() if w["id"] == t["id"]), {})
        check("카드로 시작 — 새 작업 · 작업 종류 일반 문서 · TASK 문서 일반 편집(저장됨) · 첫 탭 「에이전트」 고름", t["id"] not in before and t["task"]["kind"] == "general" and t["task"]["job"] == "doc_edit"
              and (saved.get("task") or {}).get("kind") == "general" and t["tabs"][0] == ["에이전트", "true"], (t, saved.get("task")))
        page.wait_for_timeout(1500)
        mine = [u for m, u in sent if f"/api/docs/{t['id']}/" in u and m == "POST"]
        check("일반 문서의 첫 분석 — 헤딩 스크립트는 돌고 구분 기준 LLM 검토는 안 돈다", any(u.endswith("/headings") for u in mine) and not any("/divisions/review" in u for u in mine), mine)
        page.click("#homeLink")
        page.wait_for_function("() => !state.id")
        row = page.evaluate("(id) => { const b = [...document.querySelectorAll('#workList .recent-work-open')].map((x) => ({ chip: (x.querySelector('.recent-task') || {}).textContent, tone: (x.querySelector('.recent-task') || { dataset: {} }).dataset.doc, logo: (x.querySelector('.task-logo use') || { getAttribute: () => '' }).getAttribute('href') })); return b[0]; }", t["id"])
        check("최근 작업 줄 — TASK 표지 「문서 일반 편집」(회색) · 로고", row == {"chip": "문서 일반 편집", "tone": "any", "logo": "#taskIcon-doc_edit"}, row)

        expected = [e for e in errors if re.search(r"status of (409|403|502|404)", e)]  # 일부러 낸 실패 응답(브라우저가 콘솔에 적는다)
        left = [e for e in errors if e not in expected]
        check("콘솔 오류·pageerror 없음(일부러 낸 409·403·502·404 응답 4건 말고)", not left and len(expected) == 4, (left[:5], expected))
        browser.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'FAIL ' + str(len(fails)) if fails else 'ALL PASS'}")
sys.exit(1 if fails else 0)

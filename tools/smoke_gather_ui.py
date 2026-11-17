"""취합(할 일 「사업계획서 취합」 plan_merge — spec_취합 ② §5 화면 · §6 API) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_gather_ui.py <그림·임시 폴더> [--port 18391]

취합본 = 연구개발계획서 양식(본문 최상위 문단·표가 있어야 끌어 넣기의 놓을 자리를 본다), 기관 문서 = 작은 문서(기술수요조사서.hwpx)를 이름을 바꿔 넷(처음부터 든 것 · 목록에서 고른 것 둘 · 폴더 단추로 올린 것) — 한 과제로 묶는다.
`/gather` 끝점은 모두 흉내(page.route 정규식 — 글롭 `gather**` 은 하위 경로를 안 잡아 진짜 서버로 샌다)이고, 구분 기준 상태(GET …/divisions)는 진짜 응답에 「지원 양식 · 반영됨」 만 얹는다
(구분 기준을 실제로 반영하지는 않는다 — 그 길은 tools/smoke_task_run_ui.py). 보는 것: 할 일을 고르면 취합본 칸 + 기관 문서 줄(이관 화면 없음) · 기관 문서를 더해도 앞의 것이 남음 · 반영할 기관·공통 자리의 PUT 몸통 ·
1단계(준비 → ① → 배포 기준본: 409 staleHeadings 뒤 다시 분석하고 한 번 더) · 2단계 줄의 수 · 2열 「기관 작성 내용」(상태 · 넣음/뺌 PUT · LLM 의견) · 「넣기 계획」 → 「반영」 {planId} ·
둘째 면(탭 = 그 취합의 기관 문서 · 취합본이 왼쪽) · 끌어 넣기(전용 형식 끌기 → drop/plan → drop/apply) · 한 번에 진행의 차례(미지정 문서는 건너뜀) · 이관은 전처럼 칸 둘.
흉내 낸 응답의 꼴은 진짜 서버(app/merge_gather_api.py)의 것과 같다(오류 = detail {reason, message} · 계획·반영·끌어 넣기의 필드).
끝의 **진짜 구간**(13 — `/gather` 흉내를 걷음): 양식에 과제 구성(기관 셋)을 구분 기준 API 로 반영 → 화면에서 「기준본 만들기」(409 staleHeadings → 화면이 2·3단계를 다시 분석) → 기준본 파일을 받아
파이썬으로 기관 문서를 만들어(제 자리 · 표 칸 · 공통 자리) 화면으로 올림 → 반영할 기관 → 「기관 작성 내용」 → 넣기 계획 → 반영(취합본에 그 글 · 1/1 완료) → 둘째 면의 제목 줄을 끌어 넣기(계획 → 반영).
끝에 구간별 PASS/FAIL 수(COUNTS)와 진짜 구간의 구간 시간(TIMES)을 적는다."""
import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18391)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails, writes, task_puts, posts = [], [], [], [], []
SAMPLE = (ROOT / "samples" / "기술수요조사서.hwpx").read_bytes()      # 기관 문서(작은 문서 — 둘째 면이 빨리 뜬다)
FORM = (ROOT / "samples" / "연구개발계획서_양식.hwpx").read_bytes()   # 취합본(본문 최상위 문단 693 · 표 120)
TYPE = "application/x-nfm-gather"


seen = []   # 한 검사마다 이름 — 흉내 구간과 진짜 구간의 수를 따로 적는다


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:400] if detail != "" else ""), flush=True)
    seen.append(name)
    if not ok:
        fails.append(name)


def upload(name, data=SAMPLE):
    return requests.post(f"{base}/api/docs?new=1", files={"file": (name, data)}, timeout=120).json()["docId"]


def task(wid, **t):
    r = requests.put(f"{base}/api/works/{wid}/task", json={"kind": "rnd", "file": "", "job": "", "project": "", **t}, timeout=10)
    r.raise_for_status()
    return r.json()["task"]


def task_of(wid):
    """작업의 task 에서 round 를 뺀 것 — 이 검사는 취합 묶음을 본다(라운드는 tools/smoke_project_ui.py · tests/test_projects.py, spec_작업 ② §17)."""
    t = next(w for w in requests.get(f"{base}/api/works", timeout=10).json() if w["id"] == wid)["task"]
    return {k: v for k, v in t.items() if k != "round"}


def open_work(page, wid):
    page.evaluate("(id) => { location.hash = '#w=' + id; }", wid)
    page.reload()
    page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=wid, timeout=120000)


VIS = "(id) => { const e = document.getElementById(id); return !e.hidden && e.getClientRects().length > 0; }"
RECT = "(id) => { const r = document.getElementById(id).getBoundingClientRect(); return { l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width) }; }"
SHOWN = "() => { const c = document.getElementById('peerCol'); return c.getClientRects().length > 0 && !c.hidden ? document.getElementById('peerFrame').dataset.w : ''; }"
IDLE = "() => { const g = gt(); return !!g.view && !g.loading && !g.partBusy && !g.frameBusy && !g.llmBusy && !g.planBusy && !g.applyBusy && !Object.values(g.links).some((s) => s.busy) && !gatherRun; }"
PARTS = """() => [...document.querySelectorAll('#gatherParts .gt-part')].map((r) => ({ id: r.dataset.part, name: r.querySelector('.gt-part-name').textContent, org: r.querySelector('select').value,
  opts: [...r.querySelectorAll('select option')].map((o) => o.textContent), common: r.querySelector('input[type=checkbox]').checked, tag: r.querySelector('.gt-part-tag').textContent,
  peer: !!r.querySelector('[data-gather-peer]'), del: !!r.querySelector('[data-gather-del]') }))"""
STEPS = """(dom) => [...document.querySelectorAll(`#${dom} ol.dv-flow-steps > li`)].map((li) => ({ step: li.dataset.step, part: li.dataset.part || '', state: li.dataset.state, badge: (li.querySelector('.dv-flow-status') || {}).textContent || '',
  no: li.querySelector('.dv-flow-no').textContent, name: (li.querySelector('.dv-flow-title strong') || {}).textContent || '', text: li.textContent,
  acts: [...li.querySelectorAll('.dv-flow-acts > *')].map((b) => b.textContent), primary: [...li.querySelectorAll('.dv-flow-acts > .primary')].map((b) => b.textContent) }))"""
HEAD = """(dom) => { const b = document.getElementById(dom), r = b.querySelector('[data-gather-run]'); return { count: b.querySelector('.dv-phase-count').textContent, kind: b.querySelector('.dv-phase-state').dataset.kind,
  state: b.querySelector('.dv-phase-state').textContent, run: r.textContent, off: r.disabled, primary: r.classList.contains('primary'), name: b.querySelector('summary > strong').textContent, no: b.querySelector('.dv-phase-no').textContent }; }"""
ROWS = """() => [...document.querySelectorAll('#headsDlgBody tr[data-hunk]')].map((tr) => ({ key: tr.dataset.hunk, status: tr.dataset.status || '', text: tr.textContent, keep: tr.querySelector('input[data-gather-keep]') ? tr.querySelector('input[data-gather-keep]').checked : null,
  cells: [...tr.children].map((td) => td.textContent) }))"""
NOFLOW = "(sel) => { const t = document.querySelector(sel), r = t.getBoundingClientRect(); return t.scrollWidth <= t.clientWidth + 1 && [...t.querySelectorAll('select, button, input, a.btn, .dv-badge')].filter((e) => e.checkVisibility()).every((e) => { const b = e.getBoundingClientRect(); return b.left >= r.left - 1 && b.right <= r.right + 1; }); }"

VALUES = {"stages": [2, 1], "orgs": {"lead": "한국선급", "joint": ["씨드로닉스", "유엔젤"], "nonprofit": [False, False, False], "outside": [], "overseas": [], "entrust": []}, "subs": [], "current": 1}
ORGS = [("kr", "한국선급", "lead"), ("seed", "씨드로닉스", "joint"), ("uangel", "유엔젤", "joint")]
STATUS_KO = {"ready": "넣을 수 있음", "same": "이미 들어 있음", "overlap": "겹침", "unknownPlace": "확인 필요", "calc": "계산 칸", "unassigned": "반영할 기관 미지정"}

try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    plan, A, B, D, other = upload("사업계획서_취합본.hwpx", FORM), upload("기관A_한국선급.hwpx"), upload("기관B.hwpx"), upload("기관D_유엔젤.hwpx"), upload("참고문서.hwpx")
    task(plan, file="plan", project="GATHER")
    # 2026-11-12 ② §17: 한 묶음 = 같은 프로젝트·TASK·라운드(프로젝트 이름만 같으면 TASK 를 옮겨 오지 않는다) — 기관 문서·참고 문서도 처음부터 취합 TASK 1라운드로. 취합본은 화면에서 TASK 를 고른다(1.)
    task(A, file="part", project="GATHER", job="plan_merge", round=1)          # 취합에 처음부터 든 기관 문서(`part` 는 server.TASK 가 받아야 한다)
    task(other, project="GATHER", job="plan_merge", round=1)                   # 같은 라운드의 다른 문서 — 취합에 안 든 문서는 둘째 면의 탭에 안 나온다
    NAMES = {A: "기관A_한국선급.hwpx", B: "기관B.hwpx", D: "기관D_유엔젤.hwpx"}
    check("server.TASK 가 첨부 파일 종류 `part`(기관 문서)를 받음", task_of(A)["file"] == "part", task_of(A))
    tops = [b["id"] for b in requests.get(f"{base}/api/docs/{plan}", timeout=120).json()["blocks"] if b["type"] == "paragraph" and (b.get("text") or "").strip()]
    P1, P2 = tops[1], tops[2]   # 취합본의 본문 최상위 문단(글 있는 것) — 작성 내용의 놓을 자리(to.prev)
    cell = next(b for b in requests.get(f"{base}/api/docs/{A}", timeout=60).json()["blocks"] if b["type"] == "table")["cells"]
    S1, S2 = cell[0]["blocks"][0]["id"], cell[1]["blocks"][0]["id"]   # 기관 문서의 문단(표 칸 안 — 이 작은 문서는 본문이 표뿐이다) — 작성 내용의 출처(from.ids). 기관 문서는 모두 같은 파일이라 id 가 같다

    def new_items():   # 기관 작성 내용 여섯 — 넣을 수 있음 2 · 겹침 · 확인 필요 · 이미 들어 있음 · 계산 칸(꼴 = spec_취합 ② §6 「작성 내용 한 줄」)
        b = {"detail": "", "decision": None, "applied": False}
        return [
            {**b, "key": "h1", "kind": "added", "status": "ready", "scope": {"kind": "org", "org": "kr", "orgName": "한국선급", "year": 1}, "path": ["연구개발과제의 목표", "[한국선급]"], "to": {"prev": P1, "next": P2},
             "from": {"ids": [S1], "table": None}, "text": "기관이 쓴 첫 문단 — 개발 목표와 범위", "counts": {"paragraphs": 2, "tables": 1, "pictures": 0, "cells": 0, "rows": 0}},
            {**b, "key": "h2", "kind": "cells", "status": "ready", "scope": {"kind": "common", "org": None, "orgName": None, "year": None}, "path": ["연구개발비 사용 계획"], "to": {"prev": P2, "next": None},
             "from": {"ids": [S2], "table": "t1"}, "text": "인건비 1,200 · 재료비 300", "counts": {"paragraphs": 0, "tables": 0, "pictures": 0, "cells": 3, "rows": 0}},
            {**b, "key": "h3", "kind": "filled", "status": "overlap", "detail": "취합본의 그 자리에 다른 글이 있음", "scope": {"kind": "org", "org": "kr", "orgName": "한국선급", "year": 2}, "path": ["추진 전략"], "to": {"prev": P1, "next": None},
             "from": {"ids": [S1], "table": None}, "text": "먼저 들어온 글과 다른 글", "counts": {"paragraphs": 1}},
            {**b, "key": "h4", "kind": "added", "status": "unknownPlace", "detail": "같은 글 줄이 그 구간에 여럿", "scope": {"kind": "unknown", "org": None, "orgName": None, "year": None}, "path": ["기대 효과"], "to": {"prev": None, "next": None},
             "from": {"ids": [S2], "table": None}, "text": "어느 자리인지 정하지 못한 글", "counts": {"paragraphs": 1}},
            {**b, "key": "h5", "kind": "rows", "status": "same", "scope": {"kind": "common", "org": None, "orgName": None, "year": None}, "path": ["참여 인력"], "to": {"prev": P2, "next": None},
             "from": {"ids": [S2], "table": "t2"}, "text": "홍길동 · 책임연구원", "counts": {"rows": 1}},
            {**b, "key": "h6", "kind": "cells", "status": "calc", "scope": {"kind": "common", "org": None, "orgName": None, "year": None}, "path": ["연구개발비 사용 계획"], "to": {"prev": P2, "next": None},
             "from": {"ids": [S2], "table": "t1"}, "text": "합계 1,500", "counts": {"cells": 1}}]

    def new_part(orgs=()):
        return {"orgs": list(orgs), "common": True, "linked": False, "llm": None, "items": new_items(), "plan": None}
    G = {"frame": None, "version": 1, "order": [A], "parts": {A: new_part(["kr"])}, "calls": [], "stale": 1, "plans": 0, "div": "", "rev": 0}

    def status(p, it):
        if it["status"] in ("changed", "removed"):
            return it["status"]
        if not p["orgs"]:
            return "unassigned"
        return "same" if it["applied"] else it["status"]

    def held(it):
        return bool(it["decision"]) and it["decision"]["value"] in ("skip", "check")

    def items_of(p):   # 서버의 꼴: to{prev, next, at} · from{ids, table, at}(at = 화면이 갈 블록·칸) · unique
        return [{**{k: v for k, v in it.items() if k != "applied"}, "status": status(p, it), "unique": "", "to": {**it["to"], "at": it["to"]["prev"] or it["to"]["next"]},
                 "from": {**it["from"], "at": it["from"]["ids"][0]}} for it in p["items"]]

    def counts_of(p):
        c = {}
        for it in items_of(p):
            c[it["status"]] = c.get(it["status"], 0) + 1
        return c

    def todo_of(p):
        return sum(1 for it in p["items"] if status(p, it) == "ready" and not held(it))

    def part_of(pid):
        p, known = G["parts"][pid], bool(G["frame"]) and G["parts"][pid]["linked"]
        return {"work": pid, "name": NAMES[pid], "order": G["order"].index(pid), "orgs": p["orgs"], "common": p["common"], "frameId": "f1" if G["frame"] else None,
                "state": "unassigned" if not p["orgs"] else "new" if not known else "todo" if todo_of(p) else "done",   # 서버의 값: blocked | unassigned | todo | done | new(판정 전 — 진짜 서버는 기준본이 있으면 늘 판정해 싣는다)
                "counts": counts_of(p) if known else None, "todo": todo_of(p) if known else None, "llm": {"at": p["llm"]["at"], "held": p["llm"]["held"], "stale": 0} if p["llm"] else None,
                "recommend": None if p["orgs"] else {"org": "seed", "n": 3}, "reasons": []}

    def view():
        got = lambda k: [pid for pid in G["order"] if k in G["parts"][pid]["orgs"]]                                             # noqa: E731
        put = lambda k: [pid for pid in got(k) if any(it["applied"] for it in G["parts"][pid]["items"])]                         # noqa: E731
        return {"project": "GATHER", "reasons": [], "frame": G["frame"], "version": G["version"], "orgs": [{"key": k, "name": n, "role": r, "received": got(k), "applied": put(k)} for k, n, r in ORGS],
                "parts": [part_of(pid) for pid in G["order"]]}

    def links_of(pid):
        p = G["parts"][pid]
        return {"part": part_of(pid), "coverage": {"anchors": 12, "blocks": 80, "ratio": 0.87}, "share": 1.0, "counts": counts_of(p), "todo": todo_of(p), "items": items_of(p),
                "llm": {**p["llm"], "stale": 0} if p["llm"] else None, "reasons": []}

    def edit_state():
        return {"rev": G["rev"], "edited": [], "unrestored": [], "pristine": True, "kinds": {}, "undo": 1, "owpml": None, "persistError": None}

    def gather_route(route):
        req = route.request
        body = req.post_data_json if req.method in ("POST", "PUT") and req.post_data else None
        tail = unquote(req.url.split("/gather", 1)[1])
        G["calls"].append((req.method, tail, body))
        ok = lambda data: route.fulfill(status=200, content_type="application/json", body=json.dumps(data, ensure_ascii=False))   # noqa: E731
        bad = lambda code, detail: route.fulfill(status=code, content_type="application/json", body=json.dumps({"detail": detail}, ensure_ascii=False))   # noqa: E731
        if tail == "":
            return ok(view())
        if tail == "/frame":
            if G["stale"]:   # 헤딩·표 분석이 지금 문서 차례의 것이 아님 — 화면이 스크립트 분석을 다시 건 뒤 한 번 더 부른다
                G["stale"] -= 1
                return bad(409, {"reason": "staleHeadings", "message": "헤딩·표 분석이 지금 문서의 것이 아닙니다"})
            G["frame"] = {"frameId": "f1", "at": "2026-11-12T09:30:00", "rev": 0, "stale": False}
            G["parts"][A]["linked"] = True   # 처음부터 든 문서는 기준본이 생기면 서버가 견줘 둔 것으로
            return ok(view())
        if tail.startswith("/drop/"):
            if tail == "/drop/plan":
                return ok({"planId": "dp1", "from": body["from"], "range": {"title": "1. 개발 목표", "blocks": 4, "paragraphs": 3, "tables": 1, "pictures": 0, "lines": 3, "single": False},   # 서버의 꼴(merge_gather_drop.plan)
                           "after": {"id": body["afterId"], "text": "놓은 자리의 글", "given": body["afterId"]}, "owner": {"id": P1, "text": "연구개발과제의 목표"},
                           "convert": {"converted": 2, "kept": {"tooDeep": 1}, "labels": {"tooDeep": "취합본 틀에 받을 레벨이 없음(더 깊음)"}, "anchor": ["body:main", 2],
                                       "rows": [{"src": body["srcId"], "was": "1.", "letter": "가.", "why": ""}], "more": 0}, "dropped": [{"src": body["srcId"], "what": "ole"}]})
            return ok({"blocks": 4, "converted": 2, "kept": {"tooDeep": 1}, "labels": {"tooDeep": "취합본 틀에 받을 레벨이 없음(더 깊음)"}, "fitted": 0, "dropped": [], "ids": [], **edit_state()})
        m = re.match(r"^/parts/([0-9a-f]+)(/.*)?$", tail)
        pid, sub = m.group(1), m.group(2) or ""
        if sub == "":
            if req.method == "DELETE":
                G["order"].remove(pid)
                G["parts"].pop(pid)
            else:
                if pid not in G["parts"]:   # 없던 문서면 넣음 — 서버는 그 문서의 task 도 part 로 적는다(다른 문서는 안 건드림)
                    G["parts"][pid] = new_part()
                    G["order"].append(pid)
                    NAMES.setdefault(pid, next(w for w in requests.get(f"{base}/api/works", timeout=10).json() if w["id"] == pid)["name"])
                    task(pid, file="part", project="GATHER", job="plan_merge")
                G["parts"][pid].update({k: body[k] for k in ("orgs", "common") if k in (body or {})})
            G["version"] += 1
            return ok(view())
        p = G["parts"][pid]
        if sub == "/links":
            p["linked"] = True
            return ok(links_of(pid))
        if sub.startswith("/links/"):
            it = next(x for x in p["items"] if x["key"] == sub.split("/links/", 1)[1])
            was = it["decision"] or {}
            it["decision"] = None if body["value"] is None else {"value": body["value"], "source": "user", "nature": was.get("nature"), "reason": was.get("reason")}
            return ok(links_of(pid))
        if sub == "/llm":   # LLM 은 좁히는 쪽만 — h1 을 「확인 필요」 로(사람이 고른 것은 안 바꿈)
            p["llm"] = {"at": "2026-11-12T10:00:00", "held": 1, "units": [{"n": 1, "title": "1."}]}
            it = p["items"][0]
            if not (it["decision"] and it["decision"]["source"] == "user"):
                it["decision"] = {"value": "check", "source": "llm", "nature": "안내", "reason": "작성요령을 그대로 옮긴 글로 보임"}
            return ok(links_of(pid))
        if sub == "/plan":
            G["plans"] += 1
            p["plan"] = f"gp{G['plans']}"
            ready = [it for it in items_of(p) if it["status"] == "ready" and not held(it)]
            skipped = {k: n for k, n in counts_of(p).items() if k != "ready"}
            if any(status(p, it) == "ready" and held(it) for it in p["items"]):
                skipped["check"] = sum(1 for it in p["items"] if status(p, it) == "ready" and held(it))
            return ok({"planId": p["plan"], "part": pid, "todo": len(ready), "counts": {"paragraphs": 2, "tables": 1, "cells": 3} if ready else {}, "items": ready, "skipped": skipped,   # 서버의 꼴(merge_gather.plan)
                       "calc": [{"table": "t1", "cell": P2, "why": "operands", "kind": "sum", "text": None, "key": None}] if ready else [],
                       "dropped": [{"key": "h1", "src": S1, "what": "secPr"}] if ready else []})
        if sub == "/apply":
            if body.get("planId") != p["plan"]:
                return bad(409, {"reason": "stalePlan", "message": "계획이 없거나 바뀌었습니다 — 다시 계획하세요"})
            n = 0
            for it in p["items"]:
                if status(p, it) == "ready" and not held(it):
                    it["applied"] = True
                    n += 1
            p["plan"] = None
            return ok({"counts": {"hunks": n, "blocks": 3, "paragraphs": 2, "tables": 1, "pictures": 0, "placeholders": 1, "cells": 3, "rows": 0, "shaped": 0, "fitted": 0, "recalculated": 0, "skipped": 0},
                       "calc": [], "dropped": [], "skipped": [], **edit_state()})   # 서버의 꼴(merge_gather.apply)
        return bad(404, "Not Found")

    def zones_route(route):   # 편집 구역(GET …/zones — spec_구역 ② §5: 전의 기관 구역 표시 …/gather/zones) — 흉내 상태에는 구역이 없다: 빈 구역 + 넣은 내용 없음(구역 자체는 진짜 구간 13 에서 본다)
        orgs = [{"key": o["key"], "name": o["name"], "role": o.get("role", "joint")} for o in view()["orgs"]]
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"rev": G["rev"], "zonesRev": 0, "basis": "applied",
            "options": {"scope": "p:GATHER|plan_merge|1", "offered": True, "zones": {"dims": ["org"], "defaulted": True}, "rev": 0}, "orgs": orgs, "stages": VALUES["stages"],
            "blocks": {}, "cells": {}, "zones": [], "marks": [], "origins": [], "counts": {"zones": 0, "blocks": 0, "cells": 0, "marks": 0, "origins": 0, "conflicts": 0, "unknown": 0}, "reasons": []}, ensure_ascii=False))

    def div_route(route):   # 구분 기준 상태 — 진짜 응답에 「지원 양식」(supported) · 「반영됨」(applied) 만 얹는다
        if route.request.method != "GET" or not G["div"]:
            return route.continue_()
        resp = route.fetch()
        data = resp.json()
        data["profile"] = {**data["profile"], "supported": True, "name": data["profile"].get("name") or "연구개발계획서(시험)"}
        if G["div"] == "applied":
            data["applied"] = {"values": copy.deepcopy(VALUES), "rev": data.get("rev", 0), "at": time.time(), "summary": None}
        route.fulfill(response=resp, json=data)

    heads_posts = []

    def heads_route(route):   # 스크립트 분석 다시 걸기(POST …/headings {stage}) — 받은 것만 적고 바로 끝난 것으로(읽기는 진짜 서버)
        if route.request.method != "POST":
            return route.continue_()
        heads_posts.append(route.request.post_data_json)
        route.fulfill(status=200, content_type="application/json", body="{}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1900, "height": 950})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("request", lambda r: writes.append(f"{r.method} {r.url}") if r.method != "GET" and "peek=" in (r.frame.url if r.frame else "") else None)   # 둘째 면 화면이 보낸 GET 밖 요청(없어야 한다)
        page.on("request", lambda r: task_puts.append(r.url.split("/api/works/", 1)[1].split("/", 1)[0]) if r.method == "PUT" and "/api/works/" in r.url and r.url.endswith("/task") else None)

        def on_post(r):   # 화면이 진짜 서버에 보낸 POST(올리기 · 스크립트 분석 걸기) — 올리기의 몸통(파일)은 읽지 않는다
            if r.method == "POST" and "/api/docs" in r.url and "/gather" not in r.url:
                tail = r.url.split("/api/docs", 1)[1]
                posts.append((tail, None if tail.startswith("?") else r.post_data))
        page.on("request", on_post)
        GATHER_URL = re.compile(r"/api/docs/[^/]+/gather(?:[/?]|$)")
        page.route(GATHER_URL, gather_route)
        page.route(re.compile(rf"/api/docs/{plan}/zones$"), zones_route)
        page.route(re.compile(rf"/api/docs/{plan}/zones/llm$"), lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(   # 편집 구역 「LLM 검토」 의 미리 보기(spec_구역 ② §8) — 흉내 상태: LLM 끔 · 후보 없음
            {"available": False, "why": "LLM 을 쓸 수 없습니다(시험)", "running": False, "candidates": 0, "kinds": {"conflict": 0, "unknown": 0, "hint": 0, "alone": 0}, "truncated": False, "last": None}, ensure_ascii=False)))
        page.route(re.compile(rf"/api/docs/{plan}/divisions$"), div_route)
        page.goto(base)
        page.evaluate("() => { localStorage.setItem('nfm.gatherStageOpen0', '1'); localStorage.setItem('nfm.gatherStageOpen', '1'); localStorage.setItem('nfm.gatherStageOpen2', '1'); }")   # 세부 목록의 단추를 누르므로 세 묶음을 펴 둔다(기본 접힘)
        open_work(page, plan)
        page.click("#toolTabTask")
        page.wait_for_selector("#divBox .dv-task select[data-task=job]")

        # ---- 1. 할 일을 고르기 전 — 취합 화면 없음 · 끝점도 안 부름. 고르면 취합본 칸 + 기관 문서 줄 + 묶음 둘(이관 화면 없음)
        check("할 일을 고르기 전 — 취합 화면 없음 · /gather 를 부르지 않음", page.locator("#gatherFlow").count() == 0 and not G["calls"] and page.locator("#divBox .dv-task select[data-task=file]").count() == 1, G["calls"])
        opts = page.eval_on_selector_all("#divBox .dv-task select[data-task=file] option", "os => os.map(o => o.value + ':' + o.textContent)")
        check("첨부 파일 종류에 「기관 문서」(part)", "part:기관 문서" in opts, opts)
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{plan}/task") and r.request.method == "PUT"):
            page.select_option("#divBox .dv-task select[data-task=job]", "plan_merge")
        page.wait_for_selector("#gatherFlow #gatherParts .gt-part")
        page.wait_for_function(IDLE)
        check("취합 — 「사업계획서(취합본)」 칸 하나(이관의 칸 그대로: 문서 고르기 · 폴더 · 같이 보기) + 기관 문서 줄", page.eval_on_selector_all("#gatherFlow .gt-files label > span", "xs => xs.map(x => x.textContent)") == ["사업계획서(취합본)"]
              and page.eval_on_selector("#gatherFlow select[data-task-file=plan]", "e => e.value") == plan and page.locator("#gatherFlow [data-task-up=plan]").count() == 1
              and [r["id"] for r in page.evaluate(PARTS)] == [A], page.evaluate(PARTS))
        check("이관 화면 없음 — 칸 둘·이관 단계·이관의 한 번에 진행·첨부 파일 select 가 안 그려짐", all(page.locator(s).count() == 0 for s in
              ("#taskFlow", "#taskSteps", "#taskStage", "#taskStage2", "select[data-task-file=report]", "[data-task-run]", "[data-task-peer]", "#divBox .dv-task select[data-task=file]")))
        check("이관의 읽은 자료가 비어 있음(taskFlow — 이관의 함수는 취합에서 안 돈다)", page.evaluate("() => !taskFlow.links && !taskFlow.fill && !Object.keys(taskFlow.div).length && !Object.keys(taskFlow.heads).length && taskSlots() === null && gatherOn()"))
        h0, h1, h2 = page.evaluate(HEAD, "gatherStage0"), page.evaluate(HEAD, "gatherStage"), page.evaluate(HEAD, "gatherStage2")
        check("묶음 셋 — 1단계 「구분 기준」 · 2단계 「문서 프레임 작성」 · 3단계 「내용 매핑」(spec_취합 ② §9-1 — 이관과 같은 모양: 끝난 수 · 한 번에 진행 · 상태 줄)",
              (h0["no"], h0["name"], h1["no"], h1["name"], h2["no"], h2["name"]) == ("1단계", "프로젝트 구성", "2단계", "문서 프레임 작성", "3단계", "내용 매핑")
              and h0["run"] == h1["run"] == h2["run"] == "한 번에 진행" and h0["count"] == "0/1 완료" and h1["count"] == "0/2 완료" and h2["count"] == "0/1 완료", (h0, h1, h2))
        journey = "() => [...document.querySelectorAll('#gatherFlow .dv-journey [data-journey]')].map(b => [b.dataset.journey, b.dataset.state, b.getAttribute('aria-current')])"
        check("TASK 순서 — 취합본이 있어 준비 끝 · 구분 기준이 현재, 프레임·내용 매핑 대기", page.evaluate(journey) == [["prepare", "done", None], ["config", "now", "step"], ["frame", "todo", None], ["map", "todo", None]], page.evaluate(journey))
        page.evaluate("() => document.getElementById('gatherStage0').open = false")
        page.locator('#gatherFlow [data-journey="config"]').click()
        check("구분 기준 이동 — 구성을 정할 1단계 묶음 펼침", page.evaluate("() => document.getElementById('gatherStage0').open && document.activeElement === document.querySelector('#gatherStage0 > summary')"))
        page.evaluate("() => document.getElementById('gatherStage2').open = false")
        before_calls = len(G["calls"])
        page.locator('#gatherFlow [data-journey="map"]').click()
        check("대기 단계 누름은 목록만 펼침 — API 실행 없음 · 제목에 초점", page.evaluate("() => document.getElementById('gatherStage2').open && document.activeElement === document.querySelector('#gatherStage2 > summary')")
              and len(G["calls"]) == before_calls)
        note = page.get_by_role("button", name="기관 문서와 취합 순서 설명", exact=True)
        note.scroll_into_view_if_needed()
        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        note.hover()
        page.wait_for_selector("#panelHelpTooltip", state="visible")
        check("기관 문서 순서 설명은 노트 hover로 표시", "들어온 차례대로 진행" in page.inner_text("#panelHelpTooltip") and "반영할 기관" in page.inner_text("#panelHelpTooltip"))
        page.keyboard.press("Escape")
        r0 = page.evaluate(PARTS)[0]
        check("기관 문서 줄 — 이름 · 반영할 기관 목록(선택 안 함 · 기관마다 · 모든 기관) · 공통 자리 포함(기본 켬) · 상태 · 같이 보기 · 빼기", r0["name"] == NAMES[A] and r0["org"] == "kr"
              and r0["opts"] == ["선택 안 함", "한국선급 (주관)", "씨드로닉스 (공동)", "유엔젤 (공동)", "모든 기관"] and r0["common"] and r0["tag"] == "자리 연결 전" and r0["peer"] and r0["del"], r0)
        orgs = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('#gatherFlow .gt-orgs span[data-k]')].map((s) => [s.dataset.k, s.textContent]))")
        check("기관 현황 한 줄 — 받은 기관 · 반영한 기관 · 아직 없는 기관", orgs == {"received": "받은 기관 1(한국선급)", "applied": "반영한 기관 0", "missing": "아직 없는 기관 2(씨드로닉스 · 유엔젤)"}, orgs)
        check("같은 라운드의 취합 밖 문서는 참고 문서 줄에(취합 카드는 「같은 프로젝트 문서」 — ② §17)", "참고문서.hwpx" in page.inner_text("#divBox .dv-task-mates")
              and NAMES[A] not in page.inner_text("#divBox .dv-task-mates"), page.inner_text("#divBox .dv-task-mates"))
        page.locator("#panel").screenshot(path=str(OUT / "1_card.png"))

        # ---- 2. 기관 문서 추가 — 올린 문서에서 고르기 · 폴더 단추로 올리기. 더해도 앞의 기관 문서는 안 빠진다(이관의 칸 바꾸기를 안 거친다)
        add = page.eval_on_selector_all("#gatherFlow select[data-gather-add] option", "os => os.map(o => o.value)")
        check("「기관 문서 추가」 목록 = 같은 과제 문서 + 과제 이름 없는 문서(취합본·이미 든 문서는 뺌)", sorted(x for x in add if x) == sorted([B, D, other]), add)
        del task_puts[:]
        page.select_option("#gatherFlow select[data-gather-add]", B)
        page.wait_for_function(f"() => ({PARTS})().length === 2 && ({IDLE})()")
        check("둘째 기관 문서를 넣음 — PUT …/gather/parts/{id} {} · 첫 문서는 그대로(줄 둘)", ("PUT", f"/parts/{B}", {}) in G["calls"] and [r["id"] for r in page.evaluate(PARTS)] == [A, B], G["calls"][-3:])
        check("화면이 다른 문서의 작업(task)을 안 바꿈 — 첫 기관 문서는 과제·종류 그대로", not task_puts and task_of(A) == {"kind": "rnd", "file": "part", "job": "plan_merge", "project": "GATHER"}
              and task_of(plan)["file"] == "plan", (task_puts, task_of(A)))
        del posts[:]
        with page.expect_file_chooser() as fc:
            page.click("#gatherFlow [data-gather-up]")
        fc.value.set_files({"name": "기관C_씨드로닉스.hwpx", "mimeType": "application/octet-stream", "buffer": SAMPLE})
        page.wait_for_function(f"() => ({PARTS})().length === 3 && ({IDLE})()", timeout=120000)
        C = G["order"][2]
        check("폴더 단추로 올림 — POST /api/docs?new=1 → 스크립트 분석 {first: true} → PUT …/parts/{새 문서} · 지금 문서는 그대로 · 줄 셋", posts[0][0] == "?new=1"
              and (f"/{C}/headings", '{"first":true}') in posts and ("PUT", f"/parts/{C}", {}) in G["calls"] and page.evaluate("() => state.id") == plan
              and [r["name"] for r in page.evaluate(PARTS)] == [NAMES[A], NAMES[B], "기관C_씨드로닉스.hwpx"], (posts, page.evaluate(PARTS)))
        page.select_option("#gatherFlow select[data-gather-add]", D)
        page.wait_for_function(f"() => ({PARTS})().length === 4 && ({IDLE})()")
        rows = page.evaluate(PARTS)
        check("넷째까지 — 들어온 차례 그대로 · 새 문서는 「기관 미지정」 · 추천 기관이 목록에", [r["id"] for r in rows] == [A, B, C, D] and [r["tag"] for r in rows[1:]] == ["기관 미지정"] * 3
              and rows[1]["org"] == "" and any("추천(작성 내용 3)" in o for o in rows[1]["opts"]) and task_of(A)["project"] == "GATHER", rows)

        # ---- 3. 반영할 기관 · 공통 자리 포함 — PUT 몸통
        def put_org(pid, value, want):
            n = len(G["calls"])
            page.select_option(f'#gatherFlow select[data-gather-org="{pid}"]', value)
            page.wait_for_function(f"(n) => ({IDLE})()", arg=n)
            return [c for c in G["calls"][n:] if c[0] == "PUT"] == [("PUT", f"/parts/{pid}", want)]
        check("반영할 기관 = 기관 하나 → PUT {orgs: [열쇠]}", put_org(C, "seed", {"orgs": ["seed"]}), G["calls"][-2:])
        row_of = lambda pid: next(r for r in page.evaluate(PARTS) if r["id"] == pid)   # noqa: E731 — 줄은 기관 폴더로 묶여 차례가 바뀐다(② §5 「기관별 폴더」)
        check("「모든 기관」 → PUT {orgs: [모든 열쇠]}", put_org(C, "*", {"orgs": ["kr", "seed", "uangel"]}) and row_of(C)["org"] == "*", G["calls"][-2:])
        check("「모든 기관」 문서는 「여러 기관·그 밖」 폴더", page.evaluate("(id) => document.querySelector(`#gatherParts .gt-part[data-part=\"${id}\"]`).closest('.gt-folder').dataset.org", C) == "~")
        check("「선택 안 함」 → PUT {orgs: []}(미지정 — 아무것도 안 넣음)", put_org(C, "", {"orgs": []}) and row_of(C)["tag"] == "기관 미지정", G["calls"][-2:])
        put_org(C, "seed", {"orgs": ["seed"]})
        put_org(D, "uangel", {"orgs": ["uangel"]})
        n = len(G["calls"])
        page.uncheck(f'#gatherFlow input[data-gather-common="{C}"]')
        page.wait_for_function(IDLE)
        ok1 = [c for c in G["calls"][n:] if c[0] == "PUT"] == [("PUT", f"/parts/{C}", {"common": False})]
        n = len(G["calls"])
        page.check(f'#gatherFlow input[data-gather-common="{C}"]')
        page.wait_for_function(IDLE)
        check("「공통 자리 포함」 → PUT {common: false | true}", ok1 and [c for c in G["calls"][n:] if c[0] == "PUT"] == [("PUT", f"/parts/{C}", {"common": True})], G["calls"][-3:])
        orgs = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('#gatherFlow .gt-orgs span[data-k]')].map((s) => [s.dataset.k, s.textContent]))")
        check("기관 현황 — 받은 기관이 늘고 아직 없는 기관 0", orgs == {"received": "받은 기관 3(한국선급 · 씨드로닉스 · 유엔젤)", "applied": "반영한 기관 0", "missing": "아직 없는 기관 0"}, orgs)

        # ---- 3-1. 기관별 폴더(② §5 「기관별 폴더」 — 2026-11-13) — 화면만: 폴더 = 반영할 기관이 그 기관 하나인 문서. 올리기 · 파일 놓기 · 줄 끌어 옮기기
        FOLD = """() => [...document.querySelectorAll('#gatherParts > .gt-folder')].map((f) => ({ org: f.dataset.org, name: f.querySelector('.gt-folder-name').textContent, n: f.querySelector('.gt-folder-n').textContent,
  rows: [...f.querySelectorAll('.gt-part')].map((r) => r.dataset.part), up: !!f.querySelector('[data-gather-folder-up]'), shut: f.classList.contains('shut') }))"""
        DRAG = """([pid, org]) => { const dt = new DataTransfer(), src = document.querySelector(`#gatherParts .gt-part[data-part="${pid}"] .gt-part-name`), dst = document.querySelector(`#gatherParts .gt-folder[data-org="${org}"]`);
  src.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true })); const o = new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }); dst.dispatchEvent(o);
  const lit = dst.classList.contains('gt-drop'), over = document.getElementById('drop').classList.contains('over'); dst.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
  src.dispatchEvent(new DragEvent('dragend', { dataTransfer: dt, bubbles: true })); return { taken: o.defaultPrevented, lit, over, drag: src.draggable }; }"""
        fo = page.evaluate(FOLD)
        check("기관별 폴더 — 구분 기준의 기관 차례 + 「기관 미지정」(문서가 있을 때) · 폴더마다 그 기관의 문서 · 올리기 단추",
              [(f["org"], f["name"], f["n"], f["rows"]) for f in fo] == [("kr", "한국선급", "1개", [A]), ("seed", "씨드로닉스", "1개", [C]), ("uangel", "유엔젤", "1개", [D]), ("", "기관 미지정", "1개", [B])]
              and [f["up"] for f in fo] == [True, True, True, False], fo)   # 「기관 미지정」 의 올리기는 맨 아래 「기관 문서 추가」 폴더 단추
        n = len(G["calls"])
        d = page.evaluate(DRAG, [B, "seed"])
        page.wait_for_function(IDLE)
        fo = page.evaluate(FOLD)
        check("기관 문서 줄(이름)을 다른 기관 폴더에 끌어 놓음 → PUT {orgs: [그 기관]} · 그 폴더로 · 비면 「기관 미지정」 폴더 없음 · 창의 파일 놓기 덮개 안 뜸",
              d["drag"] and d["taken"] and d["lit"] and not d["over"] and [c for c in G["calls"][n:] if c[0] == "PUT"] == [("PUT", f"/parts/{B}", {"orgs": ["seed"]})]
              and [(f["org"], f["rows"]) for f in fo] == [("kr", [A]), ("seed", [B, C]), ("uangel", [D])], (d, fo, G["calls"][n:]))
        n = len(G["calls"])
        d = page.evaluate(DRAG, [B, "seed"])
        check("같은 폴더에 놓으면 아무것도 안 함", d["taken"] and not [c for c in G["calls"][n:] if c[0] == "PUT"], G["calls"][n:])
        tog = '#gatherParts .gt-folder[data-org="seed"] .gt-folder-tog'
        page.click(tog)
        shut = page.evaluate("(s) => { const t = document.querySelector(s), f = t.closest('.gt-folder'); return [f.classList.contains('shut'), [...f.querySelectorAll('.gt-part')].some((r) => r.checkVisibility()), t.getAttribute('aria-expanded'), t.querySelector('.gt-folder-caret').textContent]; }", tog)
        page.click(tog)
        check("폴더 접기 · 펴기 — 접으면 그 폴더의 줄이 안 보임(▸) · 펴면 다시(▾)", shut == [True, False, "false", "▸"]
              and page.evaluate("(s) => [...document.querySelector(s).closest('.gt-folder').querySelectorAll('.gt-part')].every((r) => r.checkVisibility())", tog), shut)
        files = page.evaluate("""() => { const dt = new DataTransfer(); dt.items.add(new File(['x'], 'a.hwpx')); const f = document.querySelector('#gatherParts .gt-folder[data-org="kr"]'), o = new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true });
          f.dispatchEvent(o); const r = [o.defaultPrevented, f.classList.contains('gt-drop'), document.getElementById('drop').classList.contains('over')]; f.dispatchEvent(new DragEvent('dragleave', { dataTransfer: dt, bubbles: true })); return r; }""")
        check("폴더 위에 파일을 끌면 폴더가 받음(창의 「파일 열기」 덮개 안 뜸)", files == [True, True, False], files)
        put_org(B, "", {"orgs": []})   # 뒤 시험이 보는 상태로(B 는 미지정)
        del posts[:]
        n = len(G["calls"])
        with page.expect_file_chooser() as fc:
            page.click('#gatherParts [data-gather-folder-up="uangel"]')
        multi = fc.value.is_multiple()
        fc.value.set_files({"name": "유엔젤_보완.hwpx", "mimeType": "application/octet-stream", "buffer": SAMPLE})
        page.wait_for_function(f"() => ({PARTS})().length === 5 && ({IDLE})()", timeout=120000)
        E = G["order"][4]
        fo = page.evaluate(FOLD)
        check("폴더의 올리기 단추 — 여러 파일 고르기 · 올린 문서는 PUT {orgs: [그 기관]} 한 번으로 그 폴더에(사람이 고른 것) · 지금 문서 그대로", multi and posts[0][0] == "?new=1"
              and [c for c in G["calls"][n:] if c[0] == "PUT"] == [("PUT", f"/parts/{E}", {"orgs": ["uangel"]})] and next(f["rows"] for f in fo if f["org"] == "uangel") == [D, E]
              and page.evaluate("() => state.id") == plan, (multi, posts, G["calls"][n:], fo))
        page.once("dialog", lambda dlg: dlg.accept())
        page.click(f'#gatherParts [data-gather-del="{E}"]')
        page.wait_for_function(f"() => ({PARTS})().length === 4 && ({IDLE})()")   # 뒤 시험은 기관 문서 넷
        G["parts"][D]["llm"] = {"at": "2026-11-12T08:00:00", "held": 0, "units": []}   # 넷째 문서는 LLM 검토를 이미 한 것으로(한 번에 진행이 다시 안 돌린다)
        for width in (320, 480, 520):   # 패널 최소 폭·보통 폭·기본 폭에서 가로 넘침 없음(design.md §1-8) — 좁으면 줄이 두 줄, 기본 폭(520px)부터 한 줄 + 열 제목
            page.evaluate("(w) => document.getElementById('panel').style.setProperty('--panel', w + 'px')", width)
            page.wait_for_timeout(300)
            lay = page.evaluate("() => { const r = document.querySelector('#gatherParts .gt-part'), c = document.querySelector('#gatherParts .gt-cols'); const mid = [...r.children].map((e) => { const b = e.getBoundingClientRect(); return b.top + b.height / 2; }).sort((x, y) => x - y); return { rows: mid.filter((y, i) => !i || y - mid[i - 1] > 8).length, cols: c.checkVisibility(), w: document.getElementById('paneDiv').clientWidth, org: Math.round(r.querySelector('select').getBoundingClientRect().width) }; }")
            check(f"첫 카드 가로 넘침 없음(패널 {width}px)", page.evaluate(NOFLOW, "#divBox .dv-task"))
            check(f"기관 문서 줄(패널 {width}px) — {'한 줄 + 열 제목' if width == 520 else '두 줄(열 제목 없음)'} · 반영할 기관 목록 ≥ 100px", (lay["cols"] and lay["rows"] == 1 if width == 520 else not lay["cols"] and lay["rows"] == 2) and lay["org"] >= 100, lay)
            page.locator("#panel").screenshot(path=str(OUT / f"2_card_{width}.png"))
        page.evaluate("() => document.getElementById('panel').style.removeProperty('--panel')")

        # ---- 4. 1단계 「구분 기준」(준비 · 구성 확정 — 문서는 안 바뀜) → 2단계 「문서 프레임 작성」(① 구분 기준 확인 → 배포 기준본). 기관 문서와 무관하게 끝낼 수 있다(spec_작업 ② §18 · spec_취합 ② §9-1)
        st0 = page.evaluate(STEPS, "gatherStage0")
        check("1단계 세부 목록 = 준비 · 구성 확정 — 값이 없으면 구성 확정이 다음 작업(「취합본에서 추출」)", [(s["step"], s["no"], s["name"]) for s in st0] == [("files", "·", "준비"), ("config", "·", "프로젝트 구성 확정")]
              and [s["state"] for s in st0] == ["done", "now"] and "프로젝트 구성(단계·차년도·기관)이 없습니다" in st0[1]["text"] and st0[1]["acts"] == ["취합본에서 추출"] and st0[1]["badge"] == "다음 작업"
              and "사업계획서_취합본_GATHER.hwpx" in st0[0]["text"], st0)   # 취합본 = 목적 문서 — 이름 뒤에 과제 이름(spec_작업 ② §10)
        check("구성 입력이 1단계 묶음 안(#taskFrameForm — 구성 불러오기·확정) · 반영 상태·변경 계획은 2단계 묶음 안(#taskFrameApply) · 「구성 고치기」", page.evaluate("""() => { const f = document.getElementById('taskFrameForm'), s0 = document.getElementById('gatherStage0'),
            a = document.getElementById('taskFrameApply'), s = document.getElementById('gatherStage');
          return !!f && f.parentElement === s0 && f.previousElementSibling.matches('ol.dv-flow-steps') && !!f.querySelector('fieldset.dv-config') && !!f.querySelector('#divSourceSel') && !!f.querySelector('#divConfirmBtn')
            && !!a && a.parentElement === s && !!a.querySelector('#divPlanButton') && !!a.querySelector('#divAppliedState') && !document.getElementById('divPlanButton').classList.contains('primary')
            && !!s0.querySelector('[data-gather-frame-edit]') && !document.querySelector('#divBox > fieldset.dv-config'); }"""))
        groups = page.eval_on_selector_all("#divSourceSel optgroup", "gs => gs.map(g => [g.label, g.children.length])")
        check("「구성 불러오기」 목록 — 문서에서 추출(취합본 · 기관 문서 · 「파일 올려 추출…」) 묶음이 있음", any(lab == "문서에서 추출" and n >= 2 for lab, n in groups)
              and page.locator("#divSourceSel option[value=file]").count() == 1 and page.locator(f"#divSourceSel option[value='doc:{plan}']").count() == 1, groups)
        st = page.evaluate(STEPS, "gatherStage")
        h1 = page.evaluate(HEAD, "gatherStage")
        check("2단계 세부 목록 = ① 구분 기준 확인 · 배포 기준본 — 1단계 전에는 대기 · 단추 꺼짐", [(s["step"], s["no"], s["name"]) for s in st] == [("division", "①", "프로젝트 구성 반영"), ("frame", "◆", "배포 기준본")]
              and [s["state"] for s in st] == ["todo", "todo"] and h1["off"] and h1["state"].startswith("1단계(프로젝트 구성) 뒤에"), (st, h1))
        st2 = page.evaluate(STEPS, "gatherStage2")
        h2 = page.evaluate(HEAD, "gatherStage2")
        check("3단계 — 기관 문서마다 한 줄(들어온 차례) · 앞 단계 전에는 대기 · 단추 꺼짐 · 상태 줄 = 그 묶음이 하는 일", [s["part"] for s in st2] == [A, B, C, D] and [s["no"] for s in st2] == ["1", "2", "3", "4"]
              and all(s["state"] == "todo" and s["badge"] == "대기" and not s["acts"] for s in st2) and h2["off"] and h2["count"] == "0/4 완료"
              and h2["state"] == "1단계(프로젝트 구성) 뒤에 — 기관 문서마다 자리 연결 → LLM 검토 → 넣기 계획 → 내용 반영", (st2, h2))
        G["div"] = "supported"
        page.evaluate("(v) => { dv.values = structuredClone(v); divTouched(); return divShow(); }", VALUES)
        page.wait_for_function("() => dv.view && dv.view.profile.supported && document.querySelector('#gatherStage0 li[data-step=config]').dataset.state === 'now' && !!document.querySelector('#gatherStage0 [data-gather-confirm]')")
        st0, h0 = page.evaluate(STEPS, "gatherStage0"), page.evaluate(HEAD, "gatherStage0")
        check("값을 넣으면 — 구성 확정이 다음 작업: 값 요약 + 「…에 저장」(강조) · 머리에 구성 요약 · 상태 「확정 전」", [s["state"] for s in st0] == ["done", "now"] and "2단계 · 전체 3년 · 기관 3곳" in st0[1]["text"]
              and len(st0[1]["acts"]) == 1 and st0[1]["acts"][0].endswith("에 저장") and st0[1]["primary"] == st0[1]["acts"]
              and page.inner_text("#gatherStage0 .dv-phase-frame-text") == "1단계(1–2차년도) · 2단계(3차년도) · 주관 한국선급 · 공동 2(씨드로닉스 · 유엔젤)" and h0["count"] == "0/1 완료"
              and page.get_attribute("#divPresetStatus [data-confirm]", "data-confirm") == "none" and page.locator("#divPlanButton:disabled").count() == 1, (st0, h0))
        n_conf = len(posts)
        page.click("#gatherStage0 [data-gather-confirm]")
        page.wait_for_function("() => document.querySelector('#gatherStage0 li[data-step=config]').dataset.state === 'done' && document.querySelector('#gatherStage li[data-step=division]').dataset.state === 'now'")
        st0, h0, st, h1 = page.evaluate(STEPS, "gatherStage0"), page.evaluate(HEAD, "gatherStage0"), page.evaluate(STEPS, "gatherStage"), page.evaluate(HEAD, "gatherStage")
        check("「…에 저장」 → POST …/divisions/confirm · 1단계 끝(「…에 확정함」 · 1/1 완료) · 상태 「확정함」 · ① 이 다음 작업 — 「변경 계획 보기」(강조)",
              any(t.endswith("/divisions/confirm") for t, _ in posts[n_conf:]) and [s["state"] for s in st0] == ["done", "done"] and "에 확정함" in st0[1]["text"] and h0["count"] == "1/1 완료"
              and page.get_attribute("#divPresetStatus [data-confirm]", "data-confirm") == "valid" and page.locator("#divPlanButton:disabled").count() == 0
              and [s["state"] for s in st] == ["now", "todo"] and st[0]["acts"] == ["변경 계획 보기"] and st[0]["primary"] == ["변경 계획 보기"] and "반영되지 않았습니다" in st[0]["text"] and h1["count"] == "0/2 완료", (st0, h0, st, h1, posts[n_conf:]))
        check("확정 뒤 순서 표시 — 프레임 작성이 현재", page.evaluate(journey) == [["prepare", "done", None], ["config", "done", None], ["frame", "now", "step"], ["map", "todo", None]], page.evaluate(journey))
        G["div"] = "applied"
        page.evaluate("() => divShow()")
        page.wait_for_function("() => document.querySelector('#gatherStage li[data-step=frame]').dataset.state === 'now'")
        st, h1 = page.evaluate(STEPS, "gatherStage"), page.evaluate(HEAD, "gatherStage")
        check("① 반영됨 → 배포 기준본이 다음 작업 — 기준본 없음: 「기준본 만들기」(강조) · 1/2 완료", [s["state"] for s in st] == ["done", "now"] and "취합본에 반영됨" in st[0]["text"] and st[1]["acts"] == ["기준본 만들기"]
              and st[1]["primary"] == ["기준본 만들기"] and "기관에 나눠 줄 기준본을 만듭니다" in st[1]["text"] and h1["count"] == "1/2 완료" and "다음: ◆ 배포 기준본" in h1["state"]
              and page.locator("#gatherStage [data-gather-frame-file]").count() == 0, (st, h1))
        page.locator("#panel").screenshot(path=str(OUT / "4a_frame_none.png"))
        HEADS_URL = re.compile(rf"/api/docs/{plan}/headings$")
        page.route(HEADS_URL, heads_route)
        n, n_err = len(G["calls"]), len(errors)
        page.click("#gatherStage [data-gather-frame-make]")
        page.wait_for_function("() => { const g = gt(); return !!g.view && !!g.view.frame && !g.frameBusy; }", timeout=60000)
        frame_calls = [c for c in G["calls"][n:] if c[1] == "/frame"]
        check("「기준본 만들기」 — POST …/gather/frame · 409 staleHeadings 면 스크립트 분석 2단계 → 3단계를 다시 걸고 한 번 더", [c[0] for c in frame_calls] == ["POST", "POST"]
              and heads_posts == [{"stage": 2, "llm": False}, {"stage": 3, "llm": False}], (frame_calls, heads_posts))
        expected = [e for e in errors[n_err:] if "409" in e and "Failed to load resource" in e]   # 흉내 낸 409 한 번이 콘솔에 남기는 줄 — 기대한 것
        check("흉내 낸 409 는 콘솔에 한 줄뿐", len(expected) == 1 and len(errors) == n_err + 1, errors[n_err:])
        del errors[n_err:n_err + len(expected)]
        page.unroute(HEADS_URL)
        page.wait_for_function(IDLE)
        st, h1 = page.evaluate(STEPS, "gatherStage"), page.evaluate(HEAD, "gatherStage")
        href = page.get_attribute("#gatherStage [data-gather-frame-file]", "href")
        check("기준본 있음 — 끝남 · 「기준본 내려받기」(GET …/gather/frame/file) · 「기준본 다시 만들기」 · 2/2 완료", st[1]["state"] == "done" and st[1]["badge"] == "완료" and st[1]["acts"] == ["기준본 내려받기", "기준본 다시 만들기"]
              and href == f"/api/docs/{plan}/gather/frame/file" and "만듦" in st[1]["text"] and h1["count"] == "2/2 완료" and h1["kind"] == "done" and h1["off"], (st[1], h1, href))
        check("기준본 완료 뒤 순서 표시 — 내용 매핑이 현재", page.evaluate(journey) == [["prepare", "done", None], ["config", "done", None], ["frame", "done", None], ["map", "now", "step"]], page.evaluate(journey))
        G["frame"]["stale"] = True
        page.evaluate("() => gatherLoad()")
        page.wait_for_function("() => document.querySelector('#gatherStage li[data-step=frame]').dataset.state === 'now'")
        st = page.evaluate(STEPS, "gatherStage")
        check("기준본이 낡음(frame.stale) — 새로 만들라고 알림 · 「기준본 다시 만들기」 가 앞·강조 · 낡은 것도 내려받을 수 있음", "기준본이 낡았습니다" in st[1]["text"] and st[1]["acts"] == ["기준본 다시 만들기", "기준본 내려받기"]
              and st[1]["primary"] == ["기준본 다시 만들기"] and all(s["state"] == "todo" for s in page.evaluate(STEPS, "gatherStage2")), st[1])
        G["frame"] = None   # 기준본을 없애고 2단계 「한 번에 진행」 으로 다시 만든다(① 은 끝나 있어 남은 것은 기준본뿐)
        page.evaluate("() => gatherLoad()")
        page.wait_for_function("() => !gt().view.frame && !gt().loading")
        dialogs = []
        page.once("dialog", lambda dlg: (dialogs.append(dlg.message), dlg.accept()))
        n = len(G["calls"])
        page.click("#gatherStage [data-gather-run=frame]")
        page.wait_for_function("() => !gatherRun && !!gatherRunLast", timeout=60000)
        page.wait_for_function(IDLE)
        h1 = page.evaluate(HEAD, "gatherStage")
        check("2단계 「한 번에 진행」 — 누를 때 한 번 확인(구조만 · 내용은 안 넣음) → 기준본까지 · 끝 글", len(dialogs) == 1 and "내용은 넣지 않습니다" in dialogs[0] and "배포 기준본" in dialogs[0]
              and [c[:2] for c in G["calls"][n:] if c[0] == "POST"] == [("POST", "/frame")] and h1["kind"] == "done" and "배포 기준본을 만들었습니다" in h1["state"] and h1["count"] == "2/2 완료", (dialogs, h1))
        page.locator("#panel").screenshot(path=str(OUT / "4b_frame_made.png"))

        # ---- 5. 2단계 — 기관 문서 줄의 수(② 자리 연결) · LLM 검토 · 강조 단추 하나
        st2, h2 = page.evaluate(STEPS, "gatherStage2"), page.evaluate(HEAD, "gatherStage2")
        check("2단계 줄 — 첫 문서: ② 자리 연결의 수(넣을 수 있음 2 · 겹침 1 · 확인 필요 1 · …) · LLM 검토 전 · 다음 작업(강조 = LLM 검토)", st2[0]["state"] == "now"
              and "② 자리 연결 넣을 수 있음 2 · 겹침 1 · 확인 필요 1 · 이미 들어 있음 1 · 계산 칸 1" in st2[0]["text"] and "LLM 검토 아직 안 함" in st2[0]["text"]
              and st2[0]["acts"] == ["기관 작성 내용", "LLM 검토", "지침", "넣기 계획"] and st2[0]["primary"] == ["LLM 검토"], st2[0])
        check("미지정 문서 줄 — 꼬리표 「기관 미지정」 · 「반영할 기관을 고르세요」 · 넣기 단추 없음 / 아직 안 맞춘 문서 줄 — 「자리 연결」(진행 가능 · 강조 아님)", st2[1]["state"] == "hold" and st2[1]["badge"] == "기관 미지정"
              and "반영할 기관을 위 기관 문서 줄에서 고르세요" in st2[1]["text"] and "넣기 계획" not in st2[1]["acts"]
              and st2[2]["state"] == "ready" and st2[2]["badge"] == "진행 가능" and "② 자리 연결 아직 안 함" in st2[2]["text"] and st2[2]["acts"] == ["자리 연결"] and not st2[2]["primary"], st2[1:3])
        check("2단계 머리 — 0/4 완료 · 단추 켜짐 · 카드의 강조 단추는 하나(펴 둔 세부 목록의 다음 할 일)", h2["count"] == "0/4 완료" and not h2["off"] and not h2["primary"]
              and page.locator("#gatherFlow .btn.primary").count() == 1 and page.locator("#divBox .dv-task .btn.primary").count() == 1, h2)
        tags = {r["id"]: r["tag"] for r in page.evaluate(PARTS)}   # 줄 차례는 기관 폴더 차례(3-1) — id 로 찾는다
        check("기관 문서 줄의 상태 꼬리표 — 넣을 것 2 · 기관 미지정 · 자리 연결 전", [tags.get(A), tags.get(B), tags.get(C)] == ["넣을 것 2", "기관 미지정", "자리 연결 전"], tags)
        page.click(f'#gatherStage2 [data-gather-link="{C}"]')
        page.wait_for_selector("#headsDlg[data-kind=gather] #headsDlgBody tr[data-hunk]")
        page.wait_for_function(IDLE)
        check("「자리 연결」 — GET …/parts/{id}/links → 그 줄에 수 · 2열에 그 문서의 「기관 작성 내용」", ("GET", f"/parts/{C}/links", None) in G["calls"] and "기관C_씨드로닉스.hwpx" in page.inner_text("#headsDlgTitle")
              and "넣을 수 있음 2" in page.evaluate(STEPS, "gatherStage2")[2]["text"], page.inner_text("#headsDlgTitle"))
        page.locator("#panel").screenshot(path=str(OUT / "5_stage2.png"))

        # ---- 6. 2열 「기관 작성 내용」 — 상태 · 자리 · 내용 · LLM 의견 / 넣음·뺌(PUT) / 줄을 누르면 두 문서가 그 자리로
        page.click(f'#gatherStage2 [data-gather-list="{A}"]')
        page.wait_for_function("(name) => document.getElementById('headsDlgTitle').textContent.includes(name) && document.querySelectorAll('#headsDlgBody tr[data-hunk]').length === 2", arg=NAMES[A])
        check("「기관 작성 내용」 은 문서 옆 열(팝업 아님) · 처음에는 넣을 수 있는 것만", page.evaluate(VIS, "headsDlg") and page.locator("dialog[open]").count() == 0 and page.get_attribute("#headsDlg", "data-kind") == "gather"
              and [r["key"] for r in page.evaluate(ROWS)] == ["h1", "h2"] and "자리 맞춤 87%" in page.inner_text("#headsDlgTools"), page.evaluate(ROWS))
        page.locator("#headsDlgTools button", has_text="모두 6").click()
        rows = page.evaluate(ROWS)
        check("「모두」 — 상태 말(넣을 수 있음 · 겹침 · 확인 필요 · 이미 들어 있음 · 계산 칸)", [r["status"] for r in rows] == ["ready", "ready", "overlap", "unknownPlace", "same", "calc"]
              and all(STATUS_KO[r["status"]] in r["cells"][0] for r in rows), [r["cells"][0] for r in rows])
        check("줄 = 자리(소속 사슬 끝 · 기관·차년도) · 내용 앞부분(종류·수) · LLM 의견", "[한국선급]" in rows[0]["cells"][1] and "한국선급 · 1차년도" in rows[0]["cells"][1] and "공통 자리" in rows[1]["cells"][1]
              and "어느 기관 자리인지 모름" in rows[3]["cells"][1] and "더한 내용" in rows[0]["cells"][2] and "기관이 쓴 첫 문단" in rows[0]["cells"][2] and "문단 2 · 표 1" in rows[0]["cells"][2]
              and "표 칸 3" in rows[1]["cells"][2] and rows[0]["cells"][3] == "—", rows[:4])
        check("넣음/뺌은 넣을 수 있음 줄에만", [r["keep"] for r in rows] == [True, True, None, None, None, None], [r["keep"] for r in rows])
        tips = page.evaluate("() => [...document.querySelectorAll('#headsDlgBody tr[data-hunk] td.gt-st')].map((t) => t.title)")
        check("상태 도움말 — 겹침 = 취합본에 다른 내용이 있어 넣지 않음 · 확인 필요 = 자리를 정하지 못함", "취합본에 다른 내용이 있어 넣지 않음" in tips[2] and "자리를 정하지 못함" in tips[3], tips[2:4])
        page.screenshot(path=str(OUT / "6a_list.png"))
        page.uncheck('#headsDlgBody input[data-gather-keep="h2"]')
        page.wait_for_function(f"() => ({IDLE})() && ({ROWS})()[1].keep === false")
        rows = page.evaluate(ROWS)
        check("끔 → PUT …/parts/{id}/links/{열쇠} {value: skip} · 「뺌」 · 「되돌리기」 · 기관 문서 줄의 넣을 것이 줄어듦", G["calls"][-1] == ("PUT", f"/parts/{A}/links/h2", {"value": "skip"}) and "뺌" in rows[1]["cells"][0]
              and "되돌리기" in rows[1]["cells"][0] and page.evaluate(PARTS)[0]["tag"] == "넣을 것 1", (G["calls"][-1], rows[1]))
        page.locator('#headsDlgBody tr[data-hunk="h2"] button', has_text="되돌리기").click()
        page.wait_for_function(f"() => ({IDLE})() && ({ROWS})()[1].keep === true")
        check("「되돌리기」 → PUT {value: null}", G["calls"][-1] == ("PUT", f"/parts/{A}/links/h2", {"value": None}) and "되돌리기" not in page.evaluate(ROWS)[1]["cells"][0], G["calls"][-1])
        page.locator('#headsDlgBody tr[data-hunk="h1"] td.lk-place').click()
        page.wait_for_function("(id) => state.selected === id", arg=P1)
        page.wait_for_function(f"(id) => ({SHOWN})() === id", arg=A)
        page.wait_for_function("(id) => { try { const w = document.getElementById('peerFrame').contentWindow; return w.gatherPeekId() === id && !!w.document.querySelector('#doc .para.flash'); } catch { return false; } }", arg=A, timeout=120000)
        fr = next(f for f in page.frames if f"peek={A}" in f.url)
        check("줄을 누름 — 취합본은 그 자리(to.prev)로 · 둘째 면은 그 기관 문서 탭의 그 내용(from.ids[0])으로", page.evaluate("() => state.selected") == P1 and fr.evaluate("() => state.selected") == S1
              and page.evaluate("() => document.querySelector('#headsDlgBody tr.sel').dataset.hunk") == "h1")
        n = len(G["calls"])
        page.locator("#headsDlgFoot button", has_text="LLM 검토").click()
        page.wait_for_function(f"() => ({IDLE})() && !!gt().links['{A}'].data.llm")
        rows = page.evaluate(ROWS)
        check("「LLM 검토」 — POST …/parts/{id}/llm · LLM 의견(성격 — 까닭) · 좁히기만(「보류」 — 넣음이 꺼짐)", ("POST", f"/parts/{A}/llm", {}) in G["calls"][n:] and "안내 — 작성요령을 그대로 옮긴 글로 보임" in rows[0]["cells"][3]
              and "LLM 확인 필요" in rows[0]["cells"][3] and rows[0]["keep"] is False and "보류" in rows[0]["cells"][0] and "LLM 검토함" in page.inner_text("#headsDlgFoot"), rows[0])
        s0 = page.evaluate(STEPS, "gatherStage2")[0]
        check("기관 문서 줄 — 「LLM 검토 검토함(… · 보류 1)」 · 강조는 넣기 계획으로", "검토함(" in s0["text"] and "보류 1" in s0["text"] and s0["acts"] == ["기관 작성 내용", "LLM 다시 검토", "지침", "넣기 계획"]
              and s0["primary"] == ["넣기 계획"], s0)
        page.check('#headsDlgBody input[data-gather-keep="h1"]')
        page.wait_for_function(f"() => ({IDLE})() && ({ROWS})()[0].keep === true")
        check("사람이 다시 넣음으로 → PUT {value: keep}", G["calls"][-1] == ("PUT", f"/parts/{A}/links/h1", {"value": "keep"}), G["calls"][-1])
        guide_calls = []

        def guide_route(route):
            guide_calls.append(unquote(route.request.url.split("/api/docs/", 1)[1]))
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"step": "gather", "name": "취합 LLM 검토", "model": "claude-opus-5-5", "parts": [
                {"key": "contract", "title": "계약", "text": "계약 글", "source": "", "note": ""}, {"key": "guide", "title": "판단 지침", "text": "- 안내 글은 뺀다", "source": "app/merge_guides_default/gather.md", "note": ""},
                {"key": "job", "title": "할 일 프롬프트 — 사업계획서 취합", "text": "## 이 일은", "source": "jobs/plan_merge.md", "note": ""}], "last": None}, ensure_ascii=False))
        GUIDE_URL = re.compile(r"/api/docs/[^/]+/llm-guide/")
        page.route(GUIDE_URL, guide_route)
        page.click(f'#gatherStage2 li[data-part="{A}"] button[data-llm-guide=gather]')
        page.wait_for_function("() => document.querySelectorAll('#headsDlg[data-kind=llmGuide] #headsDlgBody details.lg-part').length === 3")
        check("「지침」 — GET …/llm-guide/gather?part=<기관 문서> · 2열 「LLM 지침 — 취합 LLM 검토」(서버가 준 이름)", guide_calls == [f"{plan}/llm-guide/gather?part={A}"]
              and page.inner_text("#headsDlgTitle") == "LLM 지침 — 취합 LLM 검토" and "jobs/plan_merge.md" in page.inner_text("#headsDlgBody"), guide_calls)
        page.unroute(GUIDE_URL)

        # ---- 7. 넣기 계획 → 반영
        page.click(f'#gatherStage2 [data-gather-plan="{A}"]')
        page.wait_for_selector("#headsDlg[data-kind=gatherFill] #headsDlgBody tr[data-hunk]")
        page.wait_for_function(IDLE)
        body = page.inner_text("#headsDlgBody")
        skipped = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('#headsDlgBody .gt-skipped [data-status]')].map((s) => [s.dataset.status, s.textContent]))")
        check("「넣기 계획」 — POST …/parts/{id}/plan · 2열(넣을 것 목록 · 안 넣는 것의 상태별 수 · 못 옮기는 개체 · 계산 칸)", G["calls"][-1] == ("POST", f"/parts/{A}/plan", {})
              and [r["key"] for r in page.evaluate(ROWS)] == ["h1", "h2"] and skipped == {"overlap": "겹침 1", "unknownPlace": "확인 필요 1", "same": "이미 들어 있음 1", "calc": "계산 칸 1"}
              and "옮기지 못하는 개체 — 1" in body and "쪽·구역 설정" in body and "계산 칸 — 1칸" in body and "합 · 더하는 칸이 바뀜 — 반영하면 다시 계산" in body
              and "넣을 내용 2곳 — 문단 2 · 표 1 · 표 칸 3" in page.inner_text("#headsDlgTools"), (skipped, body[-300:]))
        s0 = page.evaluate(STEPS, "gatherStage2")[0]
        check("기관 문서 줄 — ③ 넣기 계획의 수 · ④ 「계획 보기」 가 강조", "③ 넣기 계획 넣을 내용 2곳" in s0["text"] and s0["acts"][-2:] == ["넣기 계획 다시", "계획 보기"] and s0["primary"] == ["계획 보기"], s0)
        check("넣기 계획 가로 넘침 없음", page.evaluate("() => { const b = document.getElementById('headsDlgBody'); return b.scrollWidth <= b.clientWidth + 1; }"))
        page.screenshot(path=str(OUT / "7a_fill.png"))
        G["rev"] = page.evaluate("() => state.serverRev")
        dialogs = []
        page.once("dialog", lambda dlg: (dialogs.append(dlg.message), dlg.accept()))
        n = len(G["calls"])
        page.locator("#headsDlgFoot button", has_text="반영").click()
        page.wait_for_function(f"() => !!gt().done['{A}'] && !state.busy && ({IDLE})()", timeout=60000)
        after = [c for c in G["calls"][n:] if c[0] != "GET" or c[1] == ""]
        s0, h2 = page.evaluate(STEPS, "gatherStage2")[0], page.evaluate(HEAD, "gatherStage2")
        check("「반영」 — 확인 뒤 POST …/parts/{id}/apply {planId} → 취합 상태를 다시 읽음 · 열이 닫힘", len(dialogs) == 1 and "취합본에 넣을까요" in dialogs[0] and after[0] == ("POST", f"/parts/{A}/apply", {"planId": "gp1"})
              and ("GET", "", None) in after[1:] and page.eval_on_selector("#headsDlg", "e => e.hidden"), (dialogs, after))
        check("반영 뒤 — 그 문서 줄 완료(넣은 수) · 1/4 완료 · 기관 현황의 반영한 기관", s0["state"] == "done" and s0["badge"] == "완료" and "④ 내용 반영 작성 내용 2 · 문단 2 · 표 1 · 표 칸 3 · 지운 자리표시 줄 1" in s0["text"]
              and h2["count"] == "1/4 완료" and page.evaluate(PARTS)[0]["tag"] == "반영함" and "반영한 기관 1(한국선급)" in page.inner_text("#gatherFlow .gt-orgs"), (s0, h2))

        # ---- 8. 둘째 면 — 탭 = 그 취합에 든 기관 문서(들어온 차례) · 취합본은 왼쪽(고치는 문서)
        tabs = page.evaluate("() => [...document.querySelectorAll('#peerTabs .tab')].map((b) => ({ id: b.dataset.peerDoc, on: b.classList.contains('active'), text: b.textContent }))")
        v, pc = page.evaluate(RECT, "viewer"), page.evaluate(RECT, "peerCol")
        check("둘째 면의 탭 = 취합에 든 기관 문서 넷(들어온 차례) — 같은 과제의 다른 문서는 없음", [t["id"] for t in tabs] == [A, B, C, D] and other not in [t["id"] for t in tabs]
              and [t["on"] for t in tabs] == [True, False, False, False], tabs)
        TABS = "() => [...document.querySelectorAll('#peerTabs .tab')].map((b) => [b.textContent, b.dataset.peerOrg || '', b.title.split('\\n').slice(0, 2).join(' | ')])"
        tl = page.evaluate(TABS)
        check("둘째 면 탭 글 = 반영할 기관 이름(미지정은 파일 이름) · 파일 이름은 도움말에(2026-11-13 사용자)", [t[0] for t in tl] == ["한국선급", NAMES[B], "씨드로닉스", "유엔젤"]
              and [t[1] for t in tl] == ["한국선급", "", "씨드로닉스", "유엔젤"] and NAMES[A] in tl[0][2] and "반영할 기관 한국선급" in tl[0][2] and "반영할 기관" not in tl[1][2], tl)
        put_org(D, "kr", {"orgs": ["kr"]})
        tl2 = [t[0] for t in page.evaluate(TABS)]
        put_org(D, "uangel", {"orgs": ["uangel"]})
        check("반영할 기관을 바꾸면 탭 글도 바로 · 같은 기관이 둘이면 「(2)」", tl2 == ["한국선급", NAMES[B], "씨드로닉스", "한국선급 (2)"] and [t[0] for t in page.evaluate(TABS)][3] == "유엔젤", tl2)
        check("취합본이 왼쪽 · 기관 문서가 오른쪽(peer-left 아님)", v["r"] <= pc["l"] + 1 and not page.evaluate("() => document.querySelector('.workspace').classList.contains('peer-left')")
              and page.evaluate("() => document.querySelector('.workspace').classList.contains('peer-open')"), (v, pc))
        btn = page.evaluate("(ids) => ids.map((id) => { const b = document.querySelector(`#gatherParts [data-gather-peer=\"${id}\"]`); return [b.getAttribute('aria-pressed'), b.disabled]; })", [A, B])
        check("기관 문서 줄의 같이 보기 단추 — 떠 있는 문서만 눌림 · 취합본 칸의 단추는 꺼짐(지금 문서)", btn == [["true", False], ["false", False]]
              and page.evaluate("(id) => document.querySelector(`#gatherFlow .gt-files [data-gather-peer=\"${id}\"]`).disabled", plan), btn)
        page.click(f'#gatherParts [data-gather-peer="{B}"]')
        page.wait_for_function(f"(id) => ({SHOWN})() === id", arg=B)
        check("다른 줄의 단추 → 그 문서가 둘째 면에", page.evaluate("(id) => document.querySelector(`#gatherParts [data-gather-peer=\"${id}\"]`).getAttribute('aria-pressed')", B) == "true"
              and page.evaluate("() => document.querySelector('#peerTabs .tab.active').dataset.peerDoc") == B)
        page.click(f'#peerTabs .tab[data-peer-doc="{A}"]')
        page.wait_for_function("(id) => { try { const w = document.getElementById('peerFrame').contentWindow; return w.gatherPeekId() === id && !!w.document.querySelector('#doc .sheet .para'); } catch { return false; } }", arg=A, timeout=120000)
        fr = next(f for f in page.frames if f"peek={A}" in f.url)

        # ---- 9. 끌어 넣기 — 둘째 면의 제목 줄 손잡이(전용 형식 · copy) → 취합본 본문 블록 위 → 계획(2열) → 반영
        grip = fr.evaluate("""(type) => { const p = document.querySelector('#doc .para[data-id]'), g = outlineGrip(p, { no: 1, level: 1, letter: '1.', tpl: 'T1' }, 0);
          p.closest('.sheet').append(g); const dt = new DataTransfer(); g.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }));
          const out = { data: dt.getData(type), eff: dt.effectAllowed, types: [...dt.types], drag: heads.drag, dragging: document.body.classList.contains('ol-dragging'), id: p.dataset.id, mine: state.id }; g.remove(); return out; }""", TYPE)
        check("둘째 면의 손잡이 dragstart — 전용 형식 {from: 기관 문서, srcId: 제목 줄}만 싣고 · 같은 문서 안 옮기기(heads.drag)는 안 걸림", json.loads(grip["data"] or "{}") == {"from": A, "srcId": grip["id"]}
              and grip["types"] == [TYPE] and grip["drag"] is None and not grip["dragging"] and grip["mine"] == A, grip)
        # 만든 DataTransfer 는 effectAllowed 를 못 바꾼다(진짜 끌기에서만) — 값은 가짜 사건으로 본다
        fake = fr.evaluate("() => { const got = {}, e = { dataTransfer: { setData: (t, d) => { got.type = t; got.data = d; }, effectAllowed: 'uninitialized' } }; const ok = gatherGripStart(e, 'pX'); return { ok, ...got, eff: e.dataTransfer.effectAllowed }; }")
        check("끌기 효과 = copy(옮기기 아님)", fake == {"ok": True, "type": TYPE, "data": json.dumps({"from": A, "srcId": "pX"}, separators=(",", ":")), "eff": "copy"}, fake)
        check("바깥 창(취합본)의 손잡이는 끌어 넣기 출발이 아님 — gatherGripStart 가 안 받는다", page.evaluate("() => gatherGripStart({ dataTransfer: { setData() { throw new Error('x'); } } }, 'p1')") is False)
        DRAG = """([kind, id, half, type, data, cell]) => { const p = cell ? document.querySelector('#doc td .para[data-id]') : document.querySelector(`#doc .para[data-id="${id}"]`), r = p.getBoundingClientRect(), dt = new DataTransfer();
          dt.setData(type, data); const ev = new DragEvent(kind, { dataTransfer: dt, bubbles: true, cancelable: true, clientX: r.left + 8, clientY: half === 'top' ? r.top + 1 : r.bottom - 1 }); p.dispatchEvent(ev);
          return { prevented: ev.defaultPrevented, marked: [...document.querySelectorAll('#doc .gt-drop-after')].map((e) => e.dataset.id || e.dataset.tbl), over: document.getElementById('drop').classList.contains('over'), toast: document.getElementById('toast').hidden ? '' : document.getElementById('toast').textContent }; }"""
        cur = page.evaluate("""() => { const ps = [...document.querySelectorAll('#doc .para[data-id]')].filter((q) => !q.closest('td') && q.getBoundingClientRect().height > 4), k = ps.findIndex((q) => state.blocks.findIndex((b) => b.id === q.dataset.id) > 0);
          const i = state.blocks.findIndex((b) => b.id === ps[k].dataset.id); return { id: ps[k].dataset.id, prev: state.blocks[i - 1].id, cell: !!document.querySelector('#doc td .para[data-id]') }; }""")
        payload = json.dumps({"from": A, "srcId": grip["id"]})
        d1 = page.evaluate(DRAG, ["dragover", cur["id"], "bottom", TYPE, payload, False])
        check("취합본의 문단 위(아래 반쪽) — 받음 · 그 문단 아래에 놓을 줄 · 창의 파일 놓기 표시는 안 켜짐", d1["prevented"] and d1["marked"] == [cur["id"]] and not d1["over"], d1)
        d2 = page.evaluate(DRAG, ["dragover", cur["id"], "top", TYPE, payload, False])
        check("위 반쪽 — 앞 블록의 뒤(놓을 줄이 앞 블록 아래로)", d2["marked"] == [cur["prev"]], (d2, cur))
        if cur["cell"]:
            n = len(G["calls"])
            d3 = page.evaluate(DRAG, ["dragover", "", "bottom", TYPE, payload, True])
            d4 = page.evaluate(DRAG, ["drop", "", "bottom", TYPE, payload, True])
            check("표 칸 안 — 놓을 줄 없음 · 「표 칸 안에는 놓을 수 없습니다」 · 놓아도 계획을 안 부름", d3["marked"] == [] and "표 칸 안에는 놓을 수 없습니다" in d3["toast"] and d4["prevented"]
                  and not [c for c in G["calls"][n:] if "/drop/" in c[1]], (d3, d4))
        page.evaluate(DRAG, ["dragover", cur["id"], "bottom", TYPE, payload, False])
        page.click(f'#peerTabs .tab[data-peer-doc="{B}"]')
        check("끄는 중 둘째 면의 탭을 바꾸면 놓을 줄을 걷음", page.evaluate("() => document.querySelectorAll('#doc .gt-drop-after').length") == 0)
        other_drag = page.evaluate("""([id, type]) => { const p = document.querySelector(`#doc .para[data-id="${id}"]`), dt = new DataTransfer(); dt.setData('text/plain', 'x');
          const ev = new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }); p.dispatchEvent(ev); const marked = document.querySelectorAll('#doc .gt-drop-after').length;
          document.getElementById('drop').classList.remove('over'); return { marked }; }""", [cur["id"], TYPE])
        check("다른 끌기(전용 형식이 아님)는 취합이 안 받음", other_drag["marked"] == 0, other_drag)
        n = len(G["calls"])
        d5 = page.evaluate(DRAG, ["drop", cur["id"], "bottom", TYPE, payload, False])
        page.wait_for_selector("#headsDlg[data-kind=gatherDrop] #headsDlgBody .gt-drop")
        drop_calls = [c for c in G["calls"][n:] if "/drop/" in c[1]]
        info = page.evaluate("() => ({ ...Object.fromEntries([...document.querySelectorAll('#headsDlgBody .gt-drop dd[data-k]')].map((d) => [d.dataset.k, d.textContent])), on: document.querySelector('#headsDlgBody input[data-gather-convert]').checked })")
        check("놓음 → POST …/gather/drop/plan {from, srcId, afterId} — 문서는 그대로 · 2열에 계획", d5["prevented"] and d5["marked"] == [] and drop_calls == [("POST", "/drop/plan", {"from": A, "srcId": grip["id"], "afterId": cur["id"]})]
              and page.evaluate("() => state.serverRev") == G["rev"], drop_calls)
        check("끌어 넣기 계획 — 가져올 범위 · 수 · 놓을 자리 · 틀 맞춤(기본 켬 · 미리보기 수 · 그대로 두는 줄의 까닭) · 못 옮기는 개체", "1. 개발 목표" in info["range"] and info["counts"] == "블록 4 · 문단 3 · 표 1"
              and "놓은 자리의 글" in info["after"] and info["on"] is True and "맞출 줄 2 · 그대로 두는 줄 1 · 「연구개발과제의 목표」 의 아래로" in info["convert"]
              and "취합본 틀에 받을 레벨이 없음(더 깊음) — 1줄" in info["convert"] and "제목 줄과 그 아래 내용" in info["range"] and "OLE 개체" in info["dropped"], info)
        page.screenshot(path=str(OUT / "9_drop_plan.png"))
        page.locator("#headsDlgFoot button", has_text="반영").click()
        page.wait_for_function("() => !gt().drop && !state.busy && document.getElementById('headsDlg').hidden", timeout=60000)
        page.wait_for_function(IDLE)
        drop_calls = [c for c in G["calls"][n:] if "/drop/" in c[1]]
        check("「반영」 → POST …/gather/drop/apply {planId, convert: true} · 열이 닫히고 문서를 다시 읽음", drop_calls[1:] == [("POST", "/drop/apply", {"planId": "dp1", "convert": True})]
              and page.evaluate("() => document.querySelector('#doc .sheet .para') != null"), drop_calls)
        check("둘째 면 화면은 GET 밖 요청을 안 보냄(끌어 넣기의 요청은 바깥 창이)", not writes, writes[:3])

        # ---- 10. 2단계 「한 번에 진행」 — 들어온 차례로, 넣을 것이 남고 반영할 기관이 정해진 문서만: 자리 연결 → (LLM 검토 — 아직 안 한 문서만) → 넣기 계획 → 반영 → 취합 상태 다시 읽기
        dialogs = []
        page.once("dialog", lambda dlg: (dialogs.append(dlg.message), dlg.accept()))
        n = len(G["calls"])
        page.click("#gatherStage2 [data-gather-run=map]")
        page.wait_for_function("() => !gatherRun && !!gatherRunLast", timeout=120000)
        page.wait_for_function(IDLE)
        run = [(c[0], c[1]) + ((c[2],) if c[1].endswith("/apply") else ()) for c in G["calls"][n:]]
        k = run.index(("POST", f"/parts/{C}/links"))
        want = [("POST", f"/parts/{C}/links"), ("POST", f"/parts/{C}/llm"), ("POST", f"/parts/{C}/plan"), ("POST", f"/parts/{C}/apply", {"planId": "gp2"}), ("GET", ""),
                ("POST", f"/parts/{D}/links"), ("POST", f"/parts/{D}/plan"), ("POST", f"/parts/{D}/apply", {"planId": "gp3"}), ("GET", "")]
        check("확인은 누를 때 한 번 — 문서 목록과 차례 · 미지정은 건너뜀 · 유료 호출을 그 창에", len(dialogs) == 1 and all(x in dialogs[0] for x in (f"1. {NAMES[A]} — 넣을 것 없음(건너뜀)", f"2. {NAMES[B]} — 반영할 기관 미지정(건너뜀)",
              "3. 기관C_씨드로닉스.hwpx — 씨드로닉스", f"4. {NAMES[D]} — 유엔젤", "유료", "실행 취소")), dialogs)
        check("차례 — 셋째 문서(연결 → LLM → 계획 → 반영 → 다시 읽기) → 넷째 문서(이미 검토함: LLM 없이) · 앞 문서 반영 뒤에 다음 문서를 계획", run[k:] == want, run[k:])
        check("미지정 문서·끝난 문서에는 아무 요청도 안 보냄", not [c for c in run if f"/parts/{B}" in c[1] or f"/parts/{A}" in c[1]], run)
        h2, st2 = page.evaluate(HEAD, "gatherStage2"), page.evaluate(STEPS, "gatherStage2")
        check("끝 글 — 반영한 문서 수·넣은 수 · 「반영할 기관 미지정 1개는 건너뜀」 · 3/4 완료", h2["kind"] == "done" and "기관 문서 2개 반영" in h2["state"] and f"반영할 기관 미지정 1개는 건너뜀({NAMES[B]})" in h2["state"]
              and h2["count"] == "3/4 완료" and [s["state"] for s in st2] == ["done", "now", "done", "done"] and h2["off"], (h2, [s["state"] for s in st2]))
        check("기관 현황 — 반영한 기관 셋", "반영한 기관 3(한국선급 · 씨드로닉스 · 유엔젤)" in page.inner_text("#gatherFlow .gt-orgs"), page.inner_text("#gatherFlow .gt-orgs"))
        page.locator("#panel").screenshot(path=str(OUT / "10_run_all.png"))
        G["frame"]["stale"] = True
        page.evaluate("() => gatherLoad()")
        page.wait_for_function("() => !gt().loading && gt().view.frame.stale")
        h2 = page.evaluate(HEAD, "gatherStage2")
        check("취합 완료 기록 뒤 기준본이 낡으면 다시 대기 — 이전 끝 글보다 선행조건 우선", page.evaluate(journey) == [["prepare", "done", None], ["config", "done", None], ["frame", "now", "step"], ["map", "todo", None]]
              and h2["kind"] == "next" and "2단계(문서 프레임 작성) 뒤에" in h2["state"] and h2["off"], (page.evaluate(journey), h2))
        G["frame"]["stale"] = False
        page.evaluate("() => gatherLoad()")
        page.wait_for_function("() => !gt().loading && !gt().view.frame.stale")

        # ---- 11. 빼기 — 확인 뒤 DELETE · 다른 문서는 그대로
        page.once("dialog", lambda dlg: dlg.accept())
        page.click(f'#gatherParts [data-gather-del="{B}"]')
        page.wait_for_function(f"() => ({PARTS})().length === 3 && ({IDLE})()")
        check("「빼기」 → DELETE …/gather/parts/{id} · 남은 줄 셋 · 둘째 면의 탭도 셋", ("DELETE", f"/parts/{B}", None) in G["calls"] and [r["id"] for r in page.evaluate(PARTS)] == [A, C, D]
              and page.evaluate("() => [...document.querySelectorAll('#peerTabs .tab')].map((b) => b.dataset.peerDoc)") == [A, C, D], page.evaluate(PARTS))

        # ---- 11-1. 기관 문서를 열어 보는 중 — 카드는 같은 취합을 그리고(취합본 칸 = 그 과제의 사업계획서), 둘째 면은 취합본이 맨 앞·왼쪽
        open_work(page, A)
        page.click("#toolTabTask")
        page.wait_for_selector("#gatherFlow #gatherParts .gt-part")
        page.wait_for_function(f"() => ({IDLE})() && gt().div !== undefined")
        page.wait_for_function(f"(id) => ({SHOWN})() === id", arg=plan)
        st0, st, tabs = page.evaluate(STEPS, "gatherStage0"), page.evaluate(STEPS, "gatherStage"), page.evaluate("() => [...document.querySelectorAll('#peerTabs .tab')].map((b) => b.dataset.peerDoc)")
        v, pc = page.evaluate(RECT, "viewer"), page.evaluate(RECT, "peerCol")
        check("기관 문서를 고치는 중 — 취합본 칸 = 같은 과제의 사업계획서 · 기관 문서 줄 셋 · 1단계는 취합본의 값으로(읽어 온 것)", page.eval_on_selector("#gatherFlow select[data-task-file=plan]", "e => e.value") == plan
              and [r["id"] for r in page.evaluate(PARTS)] == [A, C, D] and [s["state"] for s in st] == ["done", "done"] and [s["state"] for s in st0] == ["done", "done"] and "사업계획서_취합본_GATHER.hwpx" in st0[0]["text"], (st0, st))
        check("둘째 면 — 취합본이 맨 앞 탭 · 왼쪽(peer-left) · 지금 문서는 탭에 없음", tabs == [plan, C, D] and pc["r"] <= v["l"] + 1
              and page.evaluate("() => document.querySelector('.workspace').classList.contains('peer-left')"), (tabs, v, pc))
        tip = page.get_attribute(f'#gatherStage2 [data-gather-list="{C}"]', "title") or ""
        check("취합본에서 하는 일의 단추는 같다 — 누르면 취합본을 고치는 문서로 바꾼 뒤 이어서(도움말)", "취합본을 고치는 문서로 바꾼 뒤" in (page.get_attribute("#gatherStage [data-gather-frame-make]", "title") or ""), tip)
        open_work(page, plan)
        page.click("#toolTabTask")
        page.wait_for_selector("#gatherFlow #gatherParts .gt-part")
        page.wait_for_function(IDLE)

        # ---- 12. 이관은 전과 같다 — 같은 프로젝트의 이관 TASK 면 칸 둘 + 이관 단계(취합 화면 없음).
        #      2026-11-12 ② §17: 프로젝트 안에서 TASK 칸은 값 바꾸기가 아니라 그 TASK 로 이동(project_workspace.js projectTaskPick) — 여기선 문서를 API 로 이관 TASK 1라운드에 넣고 다시 연다
        n = len(G["calls"])
        task(plan, file="plan", project="GATHER", job="plan_to_report", round=1)
        task(other, project="GATHER", job="plan_to_report", round=1)
        open_work(page, plan)
        page.click("#toolTabTask")
        page.wait_for_selector("#taskFlow #taskSteps li[data-step=files]", state="attached")   # 이관의 묶음은 기본 접힘(세부 목록은 안 보임)
        slots = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('#taskFlow select[data-task-file]')].map((s) => [s.dataset.taskFile, s.value]))")
        check("이관 — 첨부 파일 칸 둘(사업계획서 = 기준 · 연차보고서) · 단계 여덟(1단계 구성 확정 · 4단계 ⑥ 포함) · 취합 화면 없음", slots == {"plan": plan, "report": ""} and page.locator("#gatherFlow").count() == 0
              and page.eval_on_selector_all("#taskFlow .dv-flow-files label > span", "xs => xs.map(x => x.textContent)") == ["사업계획서(기준)", "연차보고서"]
              and page.eval_on_selector_all("#taskSteps li", "ls => ls.map(l => l.dataset.step)") == ["files", "config", "division", "link", "plan", "apply", "later", "guide"]
              and page.locator("#taskStage [data-task-run=frame]").count() == 1 and page.evaluate("() => !gatherOn() && taskSlots().join() === 'plan,report'"), slots)
        page.wait_for_timeout(500)
        check("이관으로 바꾼 뒤에는 /gather 를 부르지 않음 · 둘째 면은 이관의 규칙(칸 문서 → 같은 과제 문서)", not G["calls"][n:] and other in page.evaluate("() => peerDocs().map((w) => w.id)"), G["calls"][n:])
        page.locator("#panel").screenshot(path=str(OUT / "12_transfer.png"))
        check("흉내 구간 — 콘솔 오류 0", not errors, errors[:5])
        mocked = (len(seen), len(fails))   # 흉내 구간의 (검사 수, 실패 수) — 끝에 진짜 구간과 따로 적는다

        # ---- 13. 흉내 없이(진짜 끝점 app/merge_gather_api.py) — 양식 → 구분 기준 반영(API) → 화면에서 기준본(분석 2·3단계를 화면이 다시 건다) → 기준본 파일로 기관 문서를 만들어 올림 →
        #          반영할 기관 → 「기관 작성 내용」 → 넣기 계획 → 반영 → 둘째 면에서 제목 줄을 끌어 넣기(계획 → 반영). LLM 은 꺼져 있다(부르지 않음).
        page.unroute(GATHER_URL)
        sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
        import gather_data as GD   # 자리 찾기 도우미(para · nxt · cell · table_after · save) — 문서만 다룬다
        from app.hwpx_doc import HwpxDoc
        T, t0 = {}, time.time()
        clock = [t0]

        def lap(name):   # 진짜 흐름의 구간 시간(초)
            T[name] = round(time.time() - clock[0], 2)
            clock[0] = time.time()
        ORG, MARK = "씨드로닉스", "(진짜 흐름)"
        REAL = {"stages": [2], "orgs": {"lead": "한국선급", "joint": [ORG, "유엔젤"], "nonprofit": [False, False, False]}, "period": {"start": "2026-03-01", "end": "2027-12-31"}, "current": 1}
        rp = upload("진짜_취합본.hwpx", FORM)
        task(rp, file="plan", project="REAL", job="plan_merge")
        requests.put(f"{base}/api/docs/{rp}/divisions/settings", json={"values": REAL}, timeout=60).raise_for_status()
        requests.post(f"{base}/api/docs/{rp}/divisions/confirm", json={"values": REAL}, timeout=60).raise_for_status()   # 1단계 「구분 기준」 — 구성 확정(spec_작업 ② §18)
        dplan = requests.post(f"{base}/api/docs/{rp}/divisions/plan", json={}, timeout=600).json()
        requests.post(f"{base}/api/docs/{rp}/divisions/apply", json={"planId": dplan["planId"]}, timeout=600).raise_for_status()
        lap("구분 기준 계획·반영(API)")
        gv = requests.get(f"{base}/api/docs/{rp}/gather", timeout=120).json()
        r409 = requests.post(f"{base}/api/docs/{rp}/gather/frame", timeout=120)
        check("[진짜] 반영 직후 — 기준본 없음 · 분석이 지금 문서의 것이 아니면 409 {reason: staleHeadings, message}", gv["frame"] is None and gv["reasons"] == ["staleHeadings"] and [o["name"] for o in gv["orgs"]] == ["한국선급", ORG, "유엔젤"]
              and r409.status_code == 409 and r409.json()["detail"]["reason"] == "staleHeadings" and bool(r409.json()["detail"]["message"]), (gv, r409.text[:200]))
        open_work(page, rp)
        page.click("#toolTabTask")
        page.wait_for_selector("#gatherFlow #gatherParts")
        page.wait_for_function(f"() => ({IDLE})() && !!dv.view && document.querySelector('#gatherStage li[data-step=frame]').dataset.state === 'now'", timeout=120000)
        st = page.evaluate(STEPS, "gatherStage")
        check("[진짜] 2단계 — ① 끝남(값이 확정·반영돼 있음) · 배포 기준본이 다음 작업", [s["state"] for s in st] == ["done", "now"] and st[1]["acts"] == ["기준본 만들기"], st)
        lap("취합본 열기")
        n_err = len(errors)
        page.click("#gatherStage [data-gather-frame-make]")
        page.wait_for_function("() => { const g = gt(); return !!g.view && !!g.view.frame && !g.frameBusy; }", timeout=300000)
        page.wait_for_function(IDLE)
        lap("기준본 만들기(화면 — 분석 2·3단계 다시 + 기준본)")
        expected = [e for e in errors[n_err:] if "409" in e and "Failed to load resource" in e]   # 첫 POST …/frame 의 409(staleHeadings) 한 번 — 기대한 것
        check("[진짜] 「기준본 만들기」 — 409 staleHeadings 뒤 화면이 2·3단계를 다시 분석하고 기준본을 만듦(콘솔에는 그 409 한 줄뿐)", len(expected) == 1 and len(errors) == n_err + 1, errors[n_err:])
        del errors[n_err:n_err + len(expected)]
        gv = requests.get(f"{base}/api/docs/{rp}/gather", timeout=120).json()
        heads = requests.get(f"{base}/api/docs/{rp}/headings", timeout=60).json()
        st, h1 = page.evaluate(STEPS, "gatherStage"), page.evaluate(HEAD, "gatherStage")
        check("[진짜] 기준본 — 낡지 않음 · 분석이 지금 차례 · 2단계 2/2 완료 · 「기준본 내려받기」", gv["frame"] and gv["frame"]["stale"] is False and gv["reasons"] == [] and heads["stage2"]["meta"]["rev"] == heads["rev"] == heads["stage3"]["meta"]["rev"]
              and st[1]["state"] == "done" and st[1]["acts"] == ["기준본 내려받기", "기준본 다시 만들기"] and h1["count"] == "2/2 완료", (gv["frame"], st[1], h1))
        href = page.get_attribute("#gatherStage [data-gather-frame-file]", "href")
        got = requests.get(base + href, timeout=120)
        frame_bytes = got.content
        now_bytes = requests.get(f"{base}/api/docs/{rp}/download", timeout=120).content
        check("[진짜] 기준본 파일 — 첨부로 내려받음 · 그때의 저장 바이트(지금 문서를 저장한 것과 같다 — 그 뒤 안 고쳤다)", got.status_code == 200 and "attachment" in got.headers.get("content-disposition", "")
              and frame_bytes[:2] == b"PK" and frame_bytes == now_bytes, (got.status_code, len(frame_bytes), len(now_bytes)))
        lap("기준본 내려받기")
        doc = HwpxDoc(frame_bytes)   # 기관이 기준본을 받아 자기 몫만 채운 것 — 제 자리(1차년도) · 제 표 칸 · 공통 자리
        doc.blocks()
        W = {"own": f"o {ORG} 1차년도 개발 목표{MARK}", "cell": f"o 사업화 형태 : 기술이전{MARK}", "common": f"o {ORG}가 쓴 필요성{MARK}"}
        doc.set_text(GD.nxt(doc, GD.para(doc, f"[공동연구개발기관1({ORG})]", 0)), " " + W["own"])
        doc.set_text(GD.cell(doc, GD.table_after(doc, f"[공동연구개발기관 : {ORG}]"), 1, 1)["id"], W["cell"])
        doc.set_text(GD.nxt(doc, GD.para(doc, "□ 필요성")), " " + W["common"])
        part_bytes = GD.save(doc)
        lap("기관 문서 만들기(파이썬)")
        with page.expect_file_chooser() as fc:
            page.click("#gatherFlow [data-gather-up]")
        fc.value.set_files({"name": f"기관_{ORG}.hwpx", "mimeType": "application/octet-stream", "buffer": part_bytes})
        page.wait_for_function(f"() => ({PARTS})().length === 1 && ({IDLE})()", timeout=180000)
        gv = requests.get(f"{base}/api/docs/{rp}/gather", timeout=120).json()
        rpart = gv["parts"][0]["work"]
        check("[진짜] 폴더 단추로 올림 → 취합에 든 기관 문서 하나 · 그 작업의 종류 = 기관 문서(part) · 같은 과제 · 기준 판이 지금 기준본", task_of(rpart) == {"kind": "rnd", "file": "part", "job": "plan_merge", "project": "REAL"}
              and gv["parts"][0]["frameId"] == gv["frame"]["frameId"] and gv["parts"][0]["orgs"] == [] and task_of(rp)["file"] == "plan", (task_of(rpart), gv["parts"][0]))
        for _ in range(900):   # 올릴 때 화면이 건 스크립트 분석({first: true})이 끝날 때까지
            hs = requests.get(f"{base}/api/docs/{rpart}/headings", timeout=60).json()
            if hs.get("stage2") and hs.get("stage3") and not (hs.get("job") and hs["job"]["status"] == "running"):
                break
            time.sleep(.5)
        page.evaluate("() => gatherLoad()")
        page.wait_for_function(f"() => ({IDLE})() && !!gt().view.parts[0].counts", timeout=120000)
        lap("기관 문서 올리기 + 분석(스크립트)")
        row = page.evaluate(PARTS)[0]
        check("[진짜] 기관 문서 줄 — 「기관 미지정」 · 추천 기관(작성 내용이 가장 많은 기관)이 목록에", row["tag"] == "기관 미지정" and row["org"] == "" and any(ORG in o and "추천(작성 내용 2)" in o for o in row["opts"]), row)
        page.select_option(f'#gatherFlow select[data-gather-org="{rpart}"]', ORG)   # 반영할 기관 — 열쇠 = 기관 이름(㈜·빈칸 뗀 것)
        page.wait_for_function(f"() => ({IDLE})() && ({PARTS})()[0].tag.startsWith('넣을 것')", timeout=120000)
        lap("반영할 기관 지정")
        row, s2 = page.evaluate(PARTS)[0], page.evaluate(STEPS, "gatherStage2")[0]
        check("[진짜] 기관을 고름 → 「넣을 것 3」 · 2단계 줄에 ② 자리 연결의 수 · 기관 현황의 받은 기관", row["tag"] == "넣을 것 3" and row["org"] == ORG and "② 자리 연결 넣을 수 있음 3 · 겹침 0 · 확인 필요 0" in s2["text"]
              and f"받은 기관 1({ORG})" in page.inner_text("#gatherFlow .gt-orgs"), (row, s2["text"]))
        off = requests.post(f"{base}/api/docs/{rp}/gather/parts/{rpart}/llm", timeout=120)   # LLM 은 꺼져 있다(NFM_LLM_BACKEND=off — 호출이 나가지 않는다)
        gv = requests.get(f"{base}/api/docs/{rp}/gather", timeout=120).json()
        check("[진짜] LLM 이 꺼져 있으면 검토는 409 {reason: noLlm} — 「전부 보류」 로 적지 않는다(스크립트만으로 넣을 수 있다)", off.status_code == 409 and off.json()["detail"]["reason"] == "noLlm"
              and gv["parts"][0]["llm"] is None and gv["parts"][0]["todo"] == 3, (off.status_code, off.text[:200], gv["parts"][0]))
        lap("LLM 꺼짐 확인")
        page.click(f'#gatherStage2 [data-gather-list="{rpart}"]')
        page.wait_for_function("() => document.querySelectorAll('#headsDlg[data-kind=gather] #headsDlgBody tr[data-hunk]').length === 3")
        page.wait_for_function(IDLE)
        lap("기관 작성 내용 열기(자리 연결)")
        rows = page.evaluate(ROWS)
        cov = page.inner_text("#headsDlgTools")
        check("[진짜] 2열 「기관 작성 내용」 — 셋 모두 넣을 수 있음(제 자리 · 제 표 칸 · 공통 자리) · 넣음이 켜짐 · 자리 맞춤 100%", [r["status"] for r in rows] == ["ready"] * 3 and all(r["keep"] is True for r in rows)
              and sum(any(w in r["text"] for r in rows) for w in W.values()) == 3 and any("공통 자리" in r["cells"][1] for r in rows) and sum(f"{ORG} · 1차년도" in r["cells"][1] for r in rows) >= 1
              and "자리 맞춤 100%" in cov and "충분히 확인하지 못함" not in cov, (rows, cov))
        page.screenshot(path=str(OUT / "13a_real_list.png"))
        page.locator("#headsDlgFoot button", has_text="넣기 계획").click()
        page.wait_for_function("() => document.querySelectorAll('#headsDlg[data-kind=gatherFill] #headsDlgBody tr[data-hunk]').length === 3", timeout=120000)
        page.wait_for_function(IDLE)
        lap("넣기 계획")
        tools_text = page.inner_text("#headsDlgTools")
        check("[진짜] 「넣기 계획」 — 넣을 내용 3곳(문단 2 · 표 칸 1 · 지운 자리표시 줄 2) · 안 넣는 것 없음", "넣을 내용 3곳 — 문단 2 · 표 칸 1 · 지운 자리표시 줄 2" in tools_text
              and "넣지 않는 내용이 없습니다" in page.inner_text("#headsDlgBody"), tools_text)
        rev0 = page.evaluate("() => state.serverRev")
        dialogs = []
        page.once("dialog", lambda dlg: (dialogs.append(dlg.message), dlg.accept()))
        page.locator("#headsDlgFoot button", has_text="반영").click()
        page.wait_for_function(f"(id) => !!gt().done[id] && !state.busy && ({IDLE})()", arg=rpart, timeout=300000)
        lap("내용 반영(편집 하나 + 문서 다시 읽기)")
        blocks = requests.get(f"{base}/api/docs/{rp}", timeout=120).json()["blocks"]
        tops = [b for b in blocks if not b.get("captionOf")]
        flat = [re.sub(r"\s+", " ", b.get("text") or "").strip() for b in tops]
        cells = [re.sub(r"\s+", " ", c.get("text") or "").strip() for b in tops if b["type"] == "table" for c in b["cells"]]
        i, j = flat.index(f"[공동연구개발기관1({ORG})]"), flat.index("□ 필요성")
        check("[진짜] 「반영」 — 취합본의 그 자리에 그 글(제 라벨 바로 아래 · □ 필요성 바로 아래 · 제 표의 그 칸) · 편집 차례 +1", len(dialogs) == 1 and flat[i + 1] == W["own"] and flat[j + 1] == W["common"]
              and cells.count(W["cell"]) == 1 and flat.count(W["own"]) == 1 and page.evaluate("() => state.serverRev") == rev0 + 1, (flat[i:i + 3], flat[j:j + 3], dialogs))
        s2, h2 = page.evaluate(STEPS, "gatherStage2")[0], page.evaluate(HEAD, "gatherStage2")
        gv = requests.get(f"{base}/api/docs/{rp}/gather", timeout=120).json()
        check("[진짜] 반영 뒤 — 그 문서 줄 완료 · 1/1 완료 · 「반영함」 · 반영한 기관 · 다시 계획하면 할 일 없음", s2["state"] == "done" and s2["badge"] == "완료" and h2["count"] == "1/1 완료"
              and "④ 내용 반영 작성 내용 3 · 문단 2 · 표 칸 1 · 지운 자리표시 줄 2" in s2["text"] and page.evaluate(PARTS)[0]["tag"] == "반영함" and f"반영한 기관 1({ORG})" in page.inner_text("#gatherFlow .gt-orgs")
              and gv["parts"][0]["counts"] == {"same": 3} and gv["parts"][0]["todo"] == 0 and gv["parts"][0]["state"] == "done"
              and requests.post(f"{base}/api/docs/{rp}/gather/parts/{rpart}/plan", timeout=120).json()["todo"] == 0, (s2, h2, gv["parts"][0]))
        page.locator("#panel").screenshot(path=str(OUT / "13b_real_applied.png"))
        # 기관 구역 표시(spec_취합 ② §9-2 — 2026-11-13 사용자 "항시 각 기관이 작성하는 구역이 식별 … 목적문서에서 그 작성 내용을 확인"): 진짜 끝점 · 카드의 칩 · 문서의 띠·이름표·넣은 내용 바탕 · 2열 목록
        zv = requests.get(f"{base}/api/docs/{rp}/gather/zones", timeout=120).json()
        okey = next(o["key"] for o in zv["orgs"] if o["name"] == ORG)
        put = [a for a in zv["applied"] if a["part"] == rpart and a["ids"]]
        check("[진짜] 기관 구역(GET …/gather/zones) — 세 기관 모두 구역 · 넣은 기록 3곳이 지금 문서에 남음(그 기관)", {z["org"] for z in zv["zones"] if z["kind"] == "org"} >= {o["key"] for o in zv["orgs"]}
              and len(put) == 3 and all(a["orgs"] == [okey] for a in put) and zv["counts"]["applied"] == 3, {k: zv.get(k) for k in ("counts", "reasons")})
        page.wait_for_function("() => !!document.querySelector('#gatherFlow .gt-zones .gz-chip') && !!document.querySelector('#doc .gz-in') && !!document.querySelector('#doc .gz-put')", timeout=60000)
        # 화면은 공통 모듈 「편집 구역」(zones.js — spec_구역 ② §6 「화면」: 2026-11-17)의 줄을 취합 카드의 그 자리(#gatherFlow .gt-zones = #zonesBar)에 쓴다 — 자료는 GET …/zones(출처 = origins), 취합은 기관이 기본으로 켜져 있다
        zn_view = requests.get(f"{base}/api/docs/{rp}/zones", timeout=120).json()
        org_keys = [o["key"] for o in zv["orgs"]]
        zui = page.evaluate("""() => ({ chips: [...document.querySelectorAll('#gatherFlow .gz-chip[data-org]')].map((c) => [c.dataset.org, c.textContent]), tags: document.querySelectorAll('#doc .sheet > .gz-tag').length,
          put: [...document.querySelectorAll('#doc .gz-put')].map((e) => e.title), gzo: [...new Set([...document.querySelectorAll('#doc .gz-put')].map((e) => e.dataset.gzo))],
          dims: [...document.querySelectorAll('#gatherFlow #zonesBar input[data-zones-dim]')].map((c) => [c.dataset.zonesDim, c.checked]), name: document.querySelector('#gatherFlow #zonesBar strong').textContent,
          toggle: document.querySelector('#gatherFlow [data-zones=toggle]').getAttribute('aria-pressed') })""")
        check("[진짜] 편집 구역(GET …/zones) — 취합 TASK 는 기관이 기본으로 켜짐 · 출처 이벤트 3(그 기관 문서 · 그때의 반영할 기관 · 옛 기록 아님)", zn_view["options"]["zones"] == {"dims": ["org"], "defaulted": True}
              and len([o for o in zn_view["origins"] if o["part"] == rpart and o["ids"] and o["orgs"] == [okey] and not o.get("legacy")]) == 3 and zn_view["counts"]["origins"] == 3,
              {k: zn_view.get(k) for k in ("options", "counts", "reasons")})
        check("[진짜] 기관 구역 — 카드 칩(기관마다 · 「넣은 내용 3」) · 문서에 구역 띠·오른쪽 여백 이름표 · 넣은 내용 바탕(도움말 「<기관> — 「기관 문서」 에서 넣음」 · 출처 색은 그 기관의 것) · 기본 보기",
              zui["toggle"] == "true" and any(k == okey and "넣은 내용 3" in t for k, t in zui["chips"]) and [k for k, _ in zui["chips"] if k in org_keys] == org_keys and zui["tags"] > 0
              and zui["put"] and all(t.startswith(f"{ORG} — 「") and "에서 넣음" in t for t in zui["put"]) and zui["gzo"] == [str(org_keys.index(okey))]
              and zui["name"] == "편집 구역" and zui["dims"] == [["org", True], ["stage", False], ["year", False]], zui)
        page.locator(f'#gatherFlow .gz-chip[data-org="{okey}"]').click()
        page.wait_for_function("() => heads.dlg === 'zones' && !!document.querySelector('#headsDlgBody .gz-cap')")
        zl = page.evaluate("() => [...document.querySelectorAll('#headsDlgBody .gz-cap[data-org]')].map((c) => [c.dataset.org, c.textContent])")
        check("[진짜] 칩 → 2열 「편집 구역」 — 기관마다 구역·넣은 내용", [k for k, _ in zl if k in org_keys] == org_keys and any(t.startswith(ORG) and "넣은 내용 3" in t for _, t in zl), zl)
        page.locator("#gatherFlow [data-zones=toggle]").click()
        page.wait_for_function("() => !document.querySelector('#doc .gz-in, #doc .gz-put, #doc .gz-tag')")
        check("[진짜] 「감추기」 — 문서의 구역 표시가 모두 걷힘 · 다시 「보기」 로 돌아옴", page.get_attribute("#gatherFlow [data-zones=toggle]", "aria-pressed") == "false")
        page.locator("#gatherFlow [data-zones=toggle]").click()
        page.wait_for_function("() => !!document.querySelector('#doc .gz-put')", timeout=60000)
        page.screenshot(path=str(OUT / "13c_real_zones.png"))
        page.evaluate("() => { headsColClose(); setZoom(1); }")
        page.wait_for_function("() => !zoomJob.on && !zoomJob.timer", timeout=60000)
        page.wait_for_function("() => !!document.querySelector('#doc .gz-put') && !!document.querySelector('#doc .gz-tag')", timeout=60000)
        page.evaluate("() => document.querySelector('#doc .gz-put').scrollIntoView({ block: 'center' })")
        page.wait_for_timeout(500)
        box = page.evaluate("() => { const s = document.querySelector('#doc .gz-put').closest('.sheet').getBoundingClientRect(), p = document.querySelector('#doc .gz-put').getBoundingClientRect(); return { x: Math.max(0, s.left), y: Math.max(0, p.top - 260), width: Math.min(s.width, 1100), height: 620 }; }")
        page.screenshot(path=str(OUT / "13d_real_zones_page.png"), clip=box)
        guide = requests.get(f"{base}/api/docs/{rp}/llm-guide/gather?part={rpart}", timeout=60).json()
        check("[진짜] 「지침」 끝점 — 계약 · 판단 지침(gather.md) · 할 일 프롬프트(jobs/plan_merge.md) · 아직 보낸 프롬프트 없음", (guide["step"], guide["name"], guide["model"]) == ("gather", "취합 LLM 검토", "claude-opus-5-5")
              and [p["key"] for p in guide["parts"]] == ["contract", "guide", "job"] and guide["parts"][2]["source"].replace("\\", "/").endswith("jobs/plan_merge.md") and guide["last"] is None, guide.get("name"))

        # 끌어 넣기 — 둘째 면(기관 문서)의 「□ 필요성」 제목 줄을 취합본의 「1-2. …」 제목 줄 아래에(계획 → 반영)
        if page.evaluate(SHOWN) != rpart:
            page.click(f'#gatherParts [data-gather-peer="{rpart}"]')
        page.wait_for_function("(id) => { try { const w = document.getElementById('peerFrame').contentWindow; return w.gatherPeekId() === id && !!w.document.querySelector('#doc .sheet .para'); } catch { return false; } }", arg=rpart, timeout=180000)
        fr = next(f for f in page.frames if f"peek={rpart}" in f.url)
        pblocks = requests.get(f"{base}/api/docs/{rpart}", timeout=120).json()["blocks"]
        src_id = next(b["id"] for b in pblocks if b["type"] == "paragraph" and re.sub(r"\s+", " ", b.get("text") or "").strip() == "□ 필요성")
        after_id = next(b["id"] for b in tops if b["type"] == "paragraph" and re.sub(r"\s+", " ", b.get("text") or "").strip() == "1-2. 연구개발과제의 배경 및 필요성")
        grab = fr.evaluate("(src) => { const got = {}, e = { dataTransfer: { setData: (t, d) => { got.type = t; got.data = d; }, effectAllowed: 'uninitialized' } }; const ok = gatherGripStart(e, src); return { ok, ...got, eff: e.dataTransfer.effectAllowed }; }", src_id)
        check("[진짜] 둘째 면의 손잡이 — 이 취합에 든 기관 문서라 끌어 넣기 출발(전용 형식 · copy)", grab["ok"] is True and grab["type"] == TYPE and json.loads(grab["data"]) == {"from": rpart, "srcId": src_id} and grab["eff"] == "copy", grab)
        page.evaluate("(id) => divGo({ key: id })", after_id)
        page.wait_for_function("(id) => !!document.querySelector(`#doc .para[data-id=\"${id}\"]`)", arg=after_id, timeout=60000)
        d1 = page.evaluate(DRAG, ["dragover", after_id, "bottom", TYPE, grab["data"], False])
        rev1 = page.evaluate("() => state.serverRev")
        d2 = page.evaluate(DRAG, ["drop", after_id, "bottom", TYPE, grab["data"], False])
        page.wait_for_selector("#headsDlg[data-kind=gatherDrop] #headsDlgBody .gt-drop", timeout=120000)
        lap("끌어 넣기 계획")
        info = page.evaluate("() => ({ ...Object.fromEntries([...document.querySelectorAll('#headsDlgBody .gt-drop dd[data-k]')].map((d) => [d.dataset.k, d.textContent])), on: document.querySelector('#headsDlgBody input[data-gather-convert]').checked, off: document.querySelector('#headsDlgBody input[data-gather-convert]').disabled })")
        check("[진짜] 놓음 → 끌어 넣기 계획(문서는 그대로) — 가져올 범위 「□ 필요성」(제목 줄과 그 아래 내용) · 블록 수 · 놓을 자리 · 틀 맞춤 미리보기", d1["marked"] == [after_id] and d2["prevented"]
              and "□ 필요성 — 제목 줄과 그 아래 내용" in info["range"] and re.match(r"^블록 \d+ · 문단 \d+", info["counts"]) and "1-2. 연구개발과제의 배경 및 필요성" in info["after"]
              and "맞출 줄" in info["convert"] and info["on"] is True and info["off"] is False and page.evaluate("() => state.serverRev") == rev1, info)
        page.screenshot(path=str(OUT / "13c_real_drop_plan.png"))
        n_blocks = int(re.match(r"^블록 (\d+)", info["counts"]).group(1))
        page.locator("#headsDlgFoot button", has_text="반영").click()
        page.wait_for_function("() => !gt().drop && !state.busy && document.getElementById('headsDlg').hidden", timeout=300000)
        page.wait_for_function(IDLE)
        lap("끌어 넣기 반영")
        blocks = requests.get(f"{base}/api/docs/{rp}", timeout=120).json()["blocks"]
        tops2 = [b for b in blocks if not b.get("captionOf")]
        flat2 = [re.sub(r"\s+", " ", b.get("text") or "").strip() for b in tops2]
        k = next(n for n, b in enumerate(tops2) if b["id"] == after_id)
        wrote = f"{ORG}가 쓴 필요성{MARK}"   # 틀 맞춤이 줄 첫머리의 레터를 바꿀 수 있어 레터 뒤의 글로 본다
        check("[진짜] 끌어 넣기 「반영」 — 놓은 블록 바로 뒤에 그 절(제목 줄 + 기관이 쓴 글)이 들어감 · 블록 수 = 계획 · 편집 차례 +1 · 기관 문서는 그대로", flat2[k + 1].endswith("필요성") and any(wrote in x for x in flat2[k + 1:k + 1 + n_blocks])
              and len(tops2) == len(tops) + n_blocks and sum(wrote in x for x in flat2) == 2 and page.evaluate("() => state.serverRev") == rev1 + 1
              and requests.get(f"{base}/api/docs/{rpart}", timeout=120).json()["rev"] == 0, (flat2[k:k + 4], len(tops), len(tops2), n_blocks))
        gv = requests.get(f"{base}/api/docs/{rp}/gather", timeout=120).json()
        check("[진짜] 끌어 넣은 뒤에도 넣은 내용은 「이미 들어 있음」(다른 자리 — 판정이 안 흔들림) · 둘째 면은 GET 밖 요청을 안 보냄", gv["parts"][0]["counts"] == {"same": 3} and gv["frame"]["stale"] is False and not writes, (gv["parts"][0], writes[:3]))
        lap("끝 확인")
        print("TIMES " + " · ".join(f"{k} {v}s" for k, v in T.items()) + f" · 모두 {round(time.time() - t0, 1)}s", flush=True)
        check("콘솔 오류 0", not errors, errors[:5])
        print(f"COUNTS 흉내 구간 PASS {mocked[0] - mocked[1]} · FAIL {mocked[1]} / 진짜 구간 PASS {len(seen) - mocked[0] - (len(fails) - mocked[1])} · FAIL {len(fails) - mocked[1]}", flush=True)
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

"""서식 보관함(spec_일반편집 ② §7 · §12 — app/static/style_lib.js) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_styles_ui.py <그림·임시 폴더> [--port 18402]

보관함 끝점(`/api/styles…` · `…/styles/…`)과 에이전트 상태(`…/agent`)는 **흉내**다(page.route — 정규식). 문서·작업은 진짜 서버(기술수요조사서 hwpx).
- 2열 「서식 보관함」(팝업 아님): 종류 탭(표 서식 · 글 서식 + 수) · 서식마다 이름 · 원본 줄 · 충실도 꼬리표(원본 서식 · 요약 · 근사) · 검증 상태(검증 중 동그라미 · 확인 필요 · 검증 뒤 바뀜 · 검증 전) ·
  견본 그림(늦게 읽기 · 누르면 그 자리에서 크게) · 「뺀 것 · 검증 내역」(펴면 읽음).
- 「검증 중」 은 2초마다 그 서식을 다시 읽어 「검증됨」 으로 · 「다시 검증」.
- 이름 바꾸기(그 줄의 입력 칸 — Enter, 보낸 몸에 expectedRevision) · 409 는 새 판을 읽고 다시 · 지우기는 두 번(그 줄에서 확인).
- 적용: 「빈 표 넣기」(커서의 본문 최상위 블록 뒤 — 자리가 없으면 까닭) · 「고른 표에 입히기」 · 글 서식 항목 「고른 문단에 입히기」 — 보낸 몸 · 구조 편집 응답을 같은 길로.
- 「이 문서에서 추출」 → 후보(표 → 글): 체크 · 이름 · 띠 수 · 같은 서식 n개 · 「구조까지 저장」 · 「글도 그대로 저장」 · 「이름 붙이기(LLM)」(직접 고친 이름은 그대로) · 「고른 n개 저장」(차례로 — 보낸 몸) → 보관함으로.
- 표 메뉴 「서식 보관함에 저장…」 → 그 표만 고른 채로 · 「파일에서 추출」 → 후보 → from-file(토큰 · key) · 410.
- 폭: 2열 320 · 480px · 패널 320 · 480px 에서 가로 넘침 없음. 보관함이 꺼져 있을 때(503) · 끝점이 없을 때(404) 한 줄 까닭.
"""
import argparse
import base64
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
ap.add_argument("--port", type=int, default=18402)
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
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAUAAAADwCAYAAABxLb1rAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAAGnSURBVHhe7dAxAQAADMOg+TfdycgDCbgBUQIEsgQIZAkQyBIgkCVAIEuAQJYAgSwBAlkCBLIECGQJEMgSIJAlQCBLgECWAIEsAQJZAgSyBAhkCRDIEiCQJUAgS4BAlgCBLAECWQIEsgQIZAkQyBIgkCVAIEuAQJYAgSwBAlkCBLIECGQJEMgSIJAlQCBLgECWAIEsAQJZAgSyBAhkCRDIEiCQJUAgS4BAlgCBLAECWQIEsgQIZAkQyBIgkCVAIEuAQJYAgSwBAlkCBLIECGQJEMgSIJAlQCBLgECWAIEsAQJZAgSyBAhkCRDIEiCQJUAgS4BAlgCBLAECWQIEsgQIZAkQyBIgkCVAIEuAQJYAgSwBAlkCBLIECGQJEMgSIJAlQCBLgECWAIEsAQJZAgSyBAhkCRDIEiCQJUAgS4BAlgCBLAECWQIEsgQIZAkQyBIgkCVAIEuAQJYAgSwBAlkCBLIECGQJEMgSIJAlQCBLgECWAIEsAQJZAgSyBAhkCRDIEiCQJUAgS4BAlgCBLAECWQIEsgQIZAkQyBIgEHVsD4Mb2wHDu0YfAAAAAElFTkSuQmCC")  # 320×240 흰 그림(견본 출력 대신)


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


# ---- 흉내 서버(보관함) — L 이 보관함, calls 가 받은 요청 ----
now = time.time()
BANDS = {"headerRows": 2, "headerCols": 1, "footRows": 1}
COVER = {"pass": 12, "fail": 0, "unknown": 2, "unsupported": 1}
L = {"mode": "ok", "pdf": True, "conflict": False, "gone": False, "styles": [
    {"id": "s_tbl1", "revision": "r2", "kind": "table", "name": "예산 총괄표", "note": "", "created": now, "updated": now, "source": {"name": "연구개발계획서_양식.hwpx", "format": "hwpx", "page": 12}, "fidelity": "native", "losses": 2,
     "requirements": {"fonts": ["함초롬바탕"]}, "bands": BANDS, "rows": 6, "cols": 5, "blueprint": True, "verify": {"status": "running", "coverage": None, "stale": False}},
    {"id": "s_tbl2", "revision": "r1", "kind": "table", "name": "PDF 에서 잰 일정표", "note": "", "created": now, "updated": now, "source": {"name": "공고문.pdf", "format": "pdf", "page": 3}, "fidelity": "approx", "losses": 1,
     "requirements": {"fonts": []}, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "rows": 4, "cols": 3, "blueprint": False, "verify": {"status": "warn", "coverage": COVER, "stale": True}},
    {"id": "s_txt1", "revision": "r1", "kind": "text", "name": "본문 글머리", "note": "", "created": now, "updated": now, "source": {"name": "보고서.docx", "format": "docx", "page": None}, "fidelity": "summary", "losses": 0,
     "requirements": {"fonts": []}, "verify": None,
     "items": [{"key": "i1", "name": "□ 줄", "level": 1, "marker": {"mode": "literal", "literal": "□", "lead": "", "gap": " "}, "sample": "견본 글입니다"},
               {"key": "i2", "name": "자동 번호 줄", "level": 2, "marker": {"mode": "auto"}, "sample": "견본 글입니다"}]}]}
calls = {"list": 0, "poll": {}, "poll_at": [], "put": [], "delete": [], "verify": [], "apply": [], "cands": [], "save": [], "extract": [], "from_file": [], "proof": []}
IDS = {}
ST = re.compile(r"/api/styles(?:/([^/?]+))?(?:/([^/?]+))?(\?.*)?$")
DOC = re.compile(r"/api/docs/[0-9a-f]{12}/styles(?:/([^/?]+))?(?:/([^/?]+))?(\?.*)?$")
AG = re.compile(r"/api/docs/[0-9a-f]{12}/agent(/[^?]*)?(\?.*)?$")


def js(route, body, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body, ensure_ascii=False))


def summary(s):
    return s


def full(s):
    v = s.get("verify")
    rec = None if not v else {**v, "at": now, "revision": s["revision"], "pages": 1, "renderer": {"name": "Hancom"}, "note": "",
                              "checks": [{"what": "fill", "status": "pass", "pass": 6, "fail": 0, "unknown": 0, "examples": [], "note": ""},
                                         {"what": "fontFace", "status": "unknown", "pass": 0, "fail": 0, "unknown": 2, "examples": [{"where": "A1", "want": "함초롬바탕", "got": "맑은 고딕"}], "note": "대체 글꼴로 출력"}]}
    return {**s, "losses": ["캡션을 뺐습니다", "그림 채움을 뺐습니다"][: s["losses"] if isinstance(s["losses"], int) else 2], "verify": rec, "view": {}}


def find(sid):
    return next((s for s in L["styles"] if s["id"] == sid), None)


def edit_response(extra):  # 구조 편집 응답 — 바뀐 블록 없이(화면은 문서를 통째로 다시 읽는다: app.js applyTops → reloadDoc)
    return {"tops": {"drop": [], "blocks": []}, "texts": {}, "edited": [], "kinds": {}, "unrestored": [], "pristine": True, "undo": 1, "original": {}, "rev": 0, **extra}


def styles(route):
    req = route.request
    m = ST.search(req.url)
    sid, tail = m.group(1), m.group(2)
    if L["mode"] == "off":
        return js(route, {"detail": "서식 보관함이 꺼져 있습니다"}, 503)
    if L["mode"] == "missing":
        return js(route, {"detail": "Not Found"}, 404)
    if not sid:
        calls["list"] += 1
        return js(route, {"enabled": True, "pdf": L["pdf"], "styles": [summary(s) for s in L["styles"]], "broken": ["deadbeef0000"]})
    if sid == "extract-file":
        calls["extract"].append(req.headers.get("content-type", ""))
        return js(route, {"token": "tok1", "name": "공고문.pdf", "format": "pdf", "losses": ["칸 여백·줄 간격·괘선 종류는 재지 못함"], "texts": [],
                          "tables": [{"key": "F1", "table": "pdf-1", "same": ["pdf-1"], "count": 1, "rows": 4, "cols": 3, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "sample": "일정", "page": 3}]})
    if sid == "from-file":
        body = json.loads(req.post_data)
        calls["from_file"].append(body)
        if L["gone"]:
            return js(route, {"detail": "토큰이 만료되었습니다"}, 410)
        made = [{"id": f"f{i}", "revision": "r1", "kind": p["kind"], "name": p.get("name") or "이름 없음", "source": {"name": "공고문.pdf", "format": "pdf", "page": 3}, "fidelity": "approx", "losses": 1,
                 "bands": p.get("bands"), "rows": 4, "cols": 3, "blueprint": False, "verify": {"status": "running", "coverage": None, "stale": False}} for i, p in enumerate(body["picks"])]
        L["styles"].extend(made)
        return js(route, {"styles": made})
    s = find(sid)
    if not s:
        return js(route, {"detail": "없는 서식입니다"}, 404)
    if tail == "proof.png":
        calls["proof"].append(req.url.rsplit("/", 2)[-2] + req.url[req.url.index("?"):] if "?" in req.url else req.url)
        return route.fulfill(status=200, content_type="image/png", body=PNG)
    if tail == "verify":
        calls["verify"].append(sid)
        s["verify"] = {"status": "running", "coverage": None, "stale": False}
        calls["poll"][sid] = 0
        return js(route, {"status": "running"}, 202)
    if req.method == "GET":
        calls["poll"][sid] = calls["poll"].get(sid, 0) + 1
        calls["poll_at"].append((sid, time.time()))
        if s.get("verify") and s["verify"]["status"] == "running" and calls["poll"][sid] >= 2:  # 둘째 읽기에서 검증이 끝난다
            s["verify"] = {"status": "ok", "coverage": COVER, "stale": False}
        return js(route, full(s))
    if req.method == "PUT":
        body = json.loads(req.post_data)
        calls["put"].append({"sid": sid, **body})
        if L["conflict"] or body.get("expectedRevision") != s["revision"]:
            L["conflict"] = False
            s["revision"] = "r9"  # 다른 곳에서 먼저 바뀜
            return js(route, {"detail": "다른 곳에서 먼저 바뀌었습니다"}, 409)
        s["name"] = body.get("name", s["name"])
        s["revision"] = f"r{int(s['revision'][1:]) + 1}"
        return js(route, full(s))
    if req.method == "DELETE":
        calls["delete"].append(req.url[req.url.index("/api/"):])
        L["styles"] = [x for x in L["styles"] if x["id"] != sid]
        return js(route, {"ok": True})
    return js(route, {"detail": "흉내에 없는 끝점"}, 500)


def doc_styles(route):
    req = route.request
    m = DOC.search(req.url)
    a, b = m.group(1), m.group(2)
    body = json.loads(req.post_data or "{}")
    if a == "candidates":
        calls["cands"].append(body)
        llm = bool(body.get("llm"))
        out = {"rev": 0, "stage2": True, "tables": [
            {"key": "T1", "table": IDS["table"], "same": [IDS["table"]], "count": 1, "rows": 18, "cols": 11, "bands": {"headerRows": 1, "headerCols": 1, "footRows": 0}, "sample": "구분", "looks": {}},
            {"key": "T2", "table": "t900", "same": ["t900", "t901", "t902"], "count": 3, "rows": 3, "cols": 4, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 1}, "sample": "항목", "looks": {}}],
            "texts": [{"key": "X1", "template": {"id": "tpl1", "no": 1, "name": "주 사슬", "chain": ["1.", "가.", "□"]},
                       "items": [{"para": IDS["cell_para"], "level": 1, "letter": "1.", "sample": "개요", "format": {}}, {"para": IDS["cell_para"], "level": 2, "letter": "가.", "sample": "세부", "format": {}}]}]}
        if llm:
            out["tables"][0].update(name="수요조사 양식표 — 머리 1행·머리열", keep=True)
            out["tables"][1].update(name="항목 합계표 — 머리 1행·합계행", keep=False, bands={"headerRows": 2, "headerCols": 0, "footRows": 1})
            out["texts"][0].update(name="주 사슬 글 서식", keep=True)
            out["call"] = {"backend": "api", "model": "claude-fable-5-2", "ms": 4200, "costUsd": 0.012}
        return js(route, out)
    if a is None:  # POST …/styles — 저장
        calls["save"].append(body)
        if body.get("name") == "실패할 이름":
            return js(route, {"detail": "그 표를 찾지 못했습니다"}, 400)
        meta = {"id": f"n{len(calls['save'])}", "revision": "r1", "kind": body["kind"], "name": body.get("name") or "이름 없음", "note": "", "created": now, "updated": now, "source": {"name": SMALL, "format": "hwpx", "page": 1},
                "fidelity": "native", "losses": 0, "requirements": {"fonts": []}, "verify": {"status": "running", "coverage": None, "stale": False}}
        if body["kind"] == "table":
            meta.update(bands=body.get("bands") or BANDS, rows=18, cols=11, blueprint=bool(body.get("blueprint")))
        else:
            meta.update(items=[{"key": "i1", "name": "1. 줄", "level": 1, "marker": {"mode": "literal", "literal": "1."}, "sample": "견본 글입니다"}])
        L["styles"].append(meta)
        return js(route, meta, 201)
    if b == "apply":
        calls["apply"].append({"sid": a, **body})
        extra = {"made": {"table": IDS["table"], "rows": 6, "cols": 5}} if body["mode"] in ("tableBlank", "tableRestyle") else {"formatted": {"paras": len(body["paras"])}}
        return js(route, edit_response(extra))
    return js(route, {"detail": "흉내에 없는 끝점"}, 500)


def agent(route):  # 에이전트 보기의 상태(「서식 보관함」 단추를 누르러 연다)
    js(route, {"enabled": True, "hwpx": True, "policy": {"apply": True, "why": ""}, "turns": [], "materials": [],
               "styles": {"table": [{"id": s["id"], "name": s["name"], "rows": s.get("rows"), "cols": s.get("cols"), "blueprint": s.get("blueprint")} for s in L["styles"] if s["kind"] == "table"],
                          "text": [{"id": s["id"], "name": s["name"], "items": s.get("items", [])} for s in L["styles"] if s["kind"] == "text"]}})


VIS = "(id) => { const e = document.getElementById(id); return !!e && !e.hidden && e.getClientRects().length > 0; }"
ITEMS = """() => [...document.querySelectorAll('#headsDlg .sl-item')].map((b) => { const q = (s) => [...b.querySelectorAll(s)].map((e) => e.textContent), img = b.querySelector('img.sl-proof');
  return { id: b.dataset.style, name: (b.querySelector('.sl-name') || {}).textContent, tags: q('.sl-head .hb'), verify: [...b.querySelectorAll('.sl-verify')].map((e) => [e.dataset.status, e.textContent, !!e.querySelector('.sl-spin')]),
    src: (b.querySelector('.sl-src') || {}).textContent, img: img ? [img.getAttribute('loading'), img.getAttribute('src'), img.classList.contains('big')] : null,
    acts: [...b.querySelectorAll('.sl-acts [data-sl-act]')].map((e) => [e.dataset.slAct, e.disabled]), levels: q('.sl-levels .sl-lv'), msg: q('.sl-msg').join(' | '), confirm: !!b.querySelector('.sl-confirm') }; })"""
ROWS = """() => [...document.querySelectorAll('#headsDlg .sl-cand')].map((b) => ({ key: b.dataset.cand, kind: b.dataset.kind, on: b.querySelector('.sl-crow > input[type=checkbox]').checked, name: b.querySelector('.sl-cname').value,
  bands: [...b.querySelectorAll('input[data-band]')].map((i) => i.value), meta: b.querySelector('.sl-cmeta').textContent, state: b.querySelector('.sl-cstate').textContent, go: !!b.querySelector('.sl-crow > .btn'),
  bp: b.querySelector('[data-sl-opt=blueprint] input') ? b.querySelector('[data-sl-opt=blueprint] input').checked : null }))"""
FIT_COL = """() => { const p = document.getElementById('headsDlg'), r = p.getBoundingClientRect();
  const bad = [...p.querySelectorAll('.hd-tools *, .hd-body *, footer *')].filter((e) => e.getClientRects().length && e.getBoundingClientRect().right > r.right + 0.5).slice(0, 6).map((e) => (e.className || e.tagName) + ':' + (e.textContent || '').slice(0, 20));
  const over = ['#headsDlg', '#headsDlgBody', '#headsDlgTools', '#headsDlgFoot'].map((s) => { const e = document.querySelector(s); return [s, e.scrollWidth - e.clientWidth]; }).filter((x) => x[1] > 0);
  return { w: Math.round(r.width), bad, over }; }"""
FIT_PANEL = """() => { const p = document.getElementById('panel'), r = p.getBoundingClientRect();
  const bad = [...p.querySelectorAll('.pane:not([hidden]) *')].filter((e) => e.getClientRects().length && e.getBoundingClientRect().right > r.right + 0.5).slice(0, 6).map((e) => (e.className || e.tagName) + ':' + (e.textContent || '').slice(0, 20));
  return { w: Math.round(r.width), bad, over: p.scrollWidth - p.clientWidth }; }"""
item = lambda xs, sid: next((x for x in xs if x["id"] == sid), None)
row = lambda xs, key: next((x for x in xs if x["key"] == key), None)
size = lambda page, box, w: (page.evaluate("([b, w]) => { const c = colSizers.find((x) => x.box === b); c.w = w; c.apply(); }", [box, w]), page.wait_for_timeout(300))

try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    a = upload(SMALL)
    tops = requests.get(f"{base}/api/docs/{a}", timeout=60).json()["blocks"]
    tbl = max((b for b in tops if b["type"] == "table"), key=lambda b: len(b.get("cells") or []))
    other = next(b for b in tops if b["id"] != tbl["id"])
    first_para = lambda c: next((x["id"] for x in c.get("blocks") or [] if x["type"] == "paragraph"), None)
    IDS.update(table=tbl["id"], other=other["id"], cell_para=next(p for p in map(first_para, tbl["cells"]) if p), cells=[c["id"] for c in tbl["cells"][:2]])

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.route(ST, styles)
        page.route(DOC, doc_styles)
        page.route(AG, agent)
        page.goto(base)
        page.evaluate("() => { try { localStorage.clear(); } catch {} }")
        open_work(page, a)
        page.click("#tabAgent")
        page.wait_for_function("() => AGENT.loaded")

        # ---- 1. 「서식 보관함」 — 문서 옆 열 · 종류 탭 · 서식 줄
        page.click("#paneAgent [data-ag-act=library]")
        page.wait_for_selector("#headsDlg[data-kind=styleLib] .sl-item")
        tabs = page.evaluate("() => [...document.querySelectorAll('#headsDlgTools [data-sl-tab]')].map((b) => [b.textContent, b.getAttribute('aria-pressed')])")
        check("서식 보관함은 문서 옆 열(팝업 아님) · 종류 탭 「표 서식 2」(고름) · 「글 서식 1」 · 추출 단추 둘", page.evaluate(VIS, "headsDlg") and page.locator("dialog[open]").count() == 0 and page.inner_text("#headsDlgTitle") == "서식 보관함"
              and tabs == [["표 서식 2", "true"], ["글 서식 1", "false"]] and page.locator("#headsDlgTools [data-sl-act]").all_inner_texts() == ["이 문서에서 추출", "파일에서 추출"], tabs)
        its = page.evaluate(ITEMS)
        t1, t2 = item(its, "s_tbl1"), item(its, "s_tbl2")
        check("표 서식 줄 — 이름 · 충실도 꼬리표(원본 서식 / 근사) · 원본 줄(파일 · 쪽 · 크기 · 띠 수 · 구조)", [x["name"] for x in its] == ["예산 총괄표", "PDF 에서 잰 일정표"] and t1["tags"] == ["원본 서식"] and t2["tags"] == ["근사"]
              and all(k in t1["src"] for k in ("원본 연구개발계획서_양식.hwpx 12쪽", "6×5", "머리행 2 · 머리열 1 · 합계행 1", "구조 있음")) and "구조 있음" not in t2["src"], (t1, t2))
        check("검증 상태 — 「검증 중」(동그라미) / 「확인 필요」 + 「검증 뒤 바뀜」", t1["verify"] == [["running", "검증 중", True]] and t2["verify"] == [["warn", "확인 필요", False], ["stale", "검증 뒤 바뀜", False]], (t1["verify"], t2["verify"]))
        check("견본 그림 — 검증이 끝난 서식만 · 늦게 읽기(lazy) · 주소에 revision", t1["img"] is None and t2["img"] == ["lazy", "/api/styles/s_tbl2/proof.png?v=r1", False], (t1["img"], t2["img"]))
        check("단추 — 구조가 있는 서식만 「빈 표 넣기」 · 「고른 표에 입히기」 · 이름 바꾸기 · 다시 검증(검증 중이면 꺼짐) · 지우기", t1["acts"] == [["blank", False], ["restyle", False], ["rename", False], ["verify", True], ["delete", False]]
              and t2["acts"] == [["restyle", False], ["rename", False], ["verify", False], ["delete", False]], (t1["acts"], t2["acts"]))
        check("발치 — 수 요약 · 읽지 못한 서식 알림", "표 서식 2 · 글 서식 1" in page.inner_text("#headsDlgFoot") and "읽지 못한 서식 1개" in page.inner_text("#headsDlgBody"))
        page.screenshot(path=str(OUT / "1_styles_lib.png"))

        # 「검증 중」 → 2초마다 그 서식을 다시 읽어 「검증됨」
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl1] .sl-verify[data-status=ok]", timeout=15000)
        at = [t for sid, t in calls["poll_at"] if sid == "s_tbl1"]
        t1 = item(page.evaluate(ITEMS), "s_tbl1")
        check("검증 중 → 2초마다 GET /api/styles/{sid} → 「검증됨」 · 견본 그림이 생김 · 「다시 검증」 이 켜짐", len(at) == 2 and 1.7 <= at[1] - at[0] <= 3.5 and t1["verify"] == [["ok", "검증됨", False]]
              and t1["img"] == ["lazy", "/api/styles/s_tbl1/proof.png?v=r2", False] and ["verify", False] in t1["acts"], (at, t1))
        page.wait_for_timeout(2600)
        check("끝난 뒤에는 더 읽지 않는다", len([1 for sid, _ in calls["poll_at"] if sid == "s_tbl1"]) == 2, calls["poll"])
        page.click("#headsDlg .sl-item[data-style=s_tbl1] img.sl-proof")
        big = page.evaluate("() => document.querySelector('#headsDlg .sl-item[data-style=s_tbl1] img.sl-proof').classList.contains('big')")
        page.click("#headsDlg .sl-item[data-style=s_tbl1] img.sl-proof")
        check("견본 그림 — 누르면 그 자리에서 크게 · 다시 누르면 작게(대화창 없음)", big and not page.evaluate("() => document.querySelector('#headsDlg .sl-item[data-style=s_tbl1] img.sl-proof').classList.contains('big')") and page.locator("dialog[open]").count() == 0)
        page.click("#headsDlg .sl-item[data-style=s_tbl1] .sl-more summary")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl1] .sl-more li")
        more = page.inner_text("#headsDlg .sl-item[data-style=s_tbl1] .sl-more")
        check("「뺀 것 2 · 검증 내역」 — 펴면 뺀 것 · 필요한 글꼴 · 검사마다의 결과", "뺀 것 2" in more and "캡션을 뺐습니다" in more and "필요한 글꼴 — 함초롬바탕" in more and "음영 — 통과" in more and "글꼴 — 모름" in more and "대체 글꼴로 출력" in more, more)

        # 「다시 검증」
        page.click("#headsDlg .sl-item[data-style=s_tbl2] [data-sl-act=verify]")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl2] .sl-verify[data-status=running]")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl2] .sl-verify[data-status=ok]", timeout=15000)
        check("「다시 검증」 — POST …/verify → 검증 중 → 검증됨(「검증 뒤 바뀜」 이 걷힘)", calls["verify"] == ["s_tbl2"] and item(page.evaluate(ITEMS), "s_tbl2")["verify"] == [["ok", "검증됨", False]])

        # ---- 2. 이름 바꾸기 — 그 줄의 입력 칸 · Enter · expectedRevision / 409
        page.click("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=rename]")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl1] input.sl-rename")
        check("이름 바꾸기 — 그 줄에 입력 칸(지금 이름 · 초점)", page.input_value("#headsDlg input.sl-rename") == "예산 총괄표" and page.evaluate("() => document.activeElement.classList.contains('sl-rename')"))
        page.fill("#headsDlg input.sl-rename", "예산 총괄표(2026)")
        page.keyboard.press("Enter")
        page.wait_for_function("() => (document.querySelector('#headsDlg .sl-item[data-style=s_tbl1] .sl-name') || {}).textContent === '예산 총괄표(2026)'")
        check("Enter — PUT 몸 = {expectedRevision, name} · 이름이 바뀜", calls["put"] == [{"sid": "s_tbl1", "expectedRevision": "r2", "name": "예산 총괄표(2026)"}], calls["put"])
        L["conflict"] = True
        page.click("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=rename]")
        page.fill("#headsDlg input.sl-rename", "다른 이름")
        page.keyboard.press("Enter")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl1] .sl-msg.err")
        msg = page.inner_text("#headsDlg .sl-item[data-style=s_tbl1] .sl-msg.err")
        check("409 — 「다른 곳에서 먼저 고쳤습니다」 · 입력한 이름은 그대로 · 다음 저장은 새 판 번호로", "다른 곳에서" in msg and page.input_value("#headsDlg input.sl-rename") == "다른 이름" and calls["put"][1]["expectedRevision"] == "r3", (msg, calls["put"]))
        page.keyboard.press("Enter")
        page.wait_for_function("() => (document.querySelector('#headsDlg .sl-item[data-style=s_tbl1] .sl-name') || {}).textContent === '다른 이름'")
        check("한 번 더 저장 — 새 판 번호(r9)로 보냄", calls["put"][2] == {"sid": "s_tbl1", "expectedRevision": "r9", "name": "다른 이름"}, calls["put"][2])
        page.click("#headsDlg .sl-item[data-style=s_tbl2] [data-sl-act=rename]")
        page.keyboard.press("Escape")
        check("Esc — 이름 바꾸기 취소(열은 그대로)", page.locator("#headsDlg input.sl-rename").count() == 0 and page.evaluate(VIS, "headsDlg") and len(calls["put"]) == 3)

        # ---- 3. 지우기 — 두 번(그 줄에서 확인)
        page.click("#headsDlg .sl-item[data-style=s_tbl2] [data-sl-act=delete]")
        check("「지우기」 한 번 — 그 줄에 확인 줄만(아직 안 지움 · 확인 창 없음)", item(page.evaluate(ITEMS), "s_tbl2")["confirm"] and calls["delete"] == [] and "지울까요" in page.inner_text("#headsDlg .sl-item[data-style=s_tbl2] .sl-confirm"))
        page.click("#headsDlg .sl-item[data-style=s_tbl2] .sl-confirm >> text=취소")
        check("취소 — 그대로", not item(page.evaluate(ITEMS), "s_tbl2")["confirm"] and calls["delete"] == [])
        page.click("#headsDlg .sl-item[data-style=s_tbl2] [data-sl-act=delete]")
        page.click("#headsDlg .sl-item[data-style=s_tbl2] [data-sl-act=deleteYes]")
        page.wait_for_function("() => !document.querySelector('#headsDlg .sl-item[data-style=s_tbl2]')")
        check("한 번 더 — DELETE …?expectedRevision= · 줄이 사라짐 · 탭의 수가 줄어듦", calls["delete"] == ["/api/styles/s_tbl2?expectedRevision=r1"] and page.inner_text("#headsDlgTools [data-sl-tab=table]") == "표 서식 1", calls["delete"])

        # ---- 4. 적용 — 자리가 없으면 까닭 · 빈 표 넣기 · 고른 표에 입히기 · 고른 문단에 입히기
        page.click("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=blank]")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl1] .sl-msg.err")
        check("자리가 없으면 — 「넣을 자리를 먼저 정하세요」(끝점을 안 부름)", "넣을 자리를 먼저 정하세요" in page.inner_text("#headsDlg .sl-item[data-style=s_tbl1] .sl-msg.err") and calls["apply"] == [])
        page.click(f'#doc .para[data-id="{IDS["cell_para"]}"]')
        page.wait_for_function("(id) => state.cur && state.cur.id === id", arg=IDS["cell_para"])
        page.click("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=blank]")
        page.wait_for_function("() => document.getElementById('toast').textContent.includes('빈 표를 넣었습니다')")
        check("「빈 표 넣기」 — 몸 = {mode: tableBlank, after: 커서를 품은 본문 최상위 블록} · 알림에 실행 취소", calls["apply"][0] == {"sid": "s_tbl1", "mode": "tableBlank", "after": IDS["table"]} and "실행 취소" in page.inner_text("#toast"), calls["apply"])
        page.wait_for_function("() => !state.busy && document.querySelector('#doc .sheet .para') != null")
        page.click(f'#doc .para[data-id="{IDS["cell_para"]}"]')
        page.click("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=restyle]")
        page.wait_for_function("() => document.getElementById('toast').textContent.includes('서식을 입혔습니다')")
        check("「고른 표에 입히기」 — 몸 = {mode: tableRestyle, table: 고른 표}", calls["apply"][1] == {"sid": "s_tbl1", "mode": "tableRestyle", "table": IDS["table"]}, calls["apply"][1:])
        page.wait_for_function("() => !state.busy && document.querySelector('#doc .sheet .para') != null")
        page.click("#headsDlgTools [data-sl-tab=text]")
        its = page.evaluate(ITEMS)
        x1 = item(its, "s_txt1")
        check("글 서식 탭 — 요약 꼬리표 · 검증 전 · 항목(레벨)마다 한 줄 + 「고른 문단에 입히기」", [x["id"] for x in its] == ["s_txt1"] and x1["tags"] == ["요약"] and x1["verify"] == [["pending", "검증 전", False]] and x1["levels"] == ["L1", "L2"]
              and page.locator("#headsDlg .sl-levels [data-sl-item]").count() == 2 and "자동 번호" in page.inner_text("#headsDlg .sl-levels"), x1)
        page.click(f'#doc .para[data-id="{IDS["cell_para"]}"]')
        page.click("#headsDlg .sl-levels [data-sl-item=i2]")
        page.wait_for_function("() => document.getElementById('toast').textContent.includes('서식을 입혔습니다')")
        check("「고른 문단에 입히기」 — 몸 = {mode: format, item, paras: [커서 문단]}", calls["apply"][2] == {"sid": "s_txt1", "mode": "format", "item": "i2", "paras": [IDS["cell_para"]]}, calls["apply"][2:])
        page.wait_for_function("() => !state.busy && document.querySelector('#doc .sheet .para') != null")
        page.screenshot(path=str(OUT / "4_styles_text.png"))

        # ---- 5. 폭 — 2열 320 · 480px · 패널 320 · 480px
        page.click("#headsDlgTools [data-sl-tab=table]")
        for width in (320, 480):
            size(page, "headsDlg", width)
            fit = page.evaluate(FIT_COL)
            check(f"서식 보관함 · 2열 {width}px — 가로 넘침 없음", fit["w"] in (width - 1, width) and not fit["bad"] and not fit["over"], fit)
            page.locator("#headsDlg").screenshot(path=str(OUT / f"5_styles_lib_{width}.png"))
            size(page, "panel", width)
            fit = page.evaluate(FIT_PANEL)
            check(f"패널 {width}px(에이전트 보기 + 열린 2열) — 가로 넘침 없음", fit["w"] in (width - 1, width) and not fit["bad"] and fit["over"] <= 0, fit)
        size(page, "panel", None)

        # ---- 6. 「이 문서에서 추출」 → 후보 → 저장
        size(page, "headsDlg", 480)
        page.click("#headsDlgTools [data-sl-act=fromDoc]")
        page.wait_for_selector("#headsDlg[data-kind=styleSave] .sl-cand")
        rows = page.evaluate(ROWS)
        check("추출 후보 — 표 둘 · 글 하나 · 처음에는 아무것도 안 고름 · 「고른 0개 저장」 꺼짐 · 보낸 몸 {llm: false}", [(r["key"], r["kind"], r["on"]) for r in rows] == [("T1", "table", False), ("T2", "table", False), ("X1", "text", False)]
              and page.inner_text("#headsDlgFoot [data-sl-act=save]") == "고른 0개 저장" and page.is_disabled("#headsDlgFoot [data-sl-act=save]") and calls["cands"] == [{"llm": False}], rows)
        r1, r2, rx = row(rows, "T1"), row(rows, "T2"), row(rows, "X1")
        check("표 후보 줄 — 이름(첫 칸 글로) · 크기 · 띠 수 칸 셋 · 「같은 서식 3개」 · 「구조까지 저장」(꺼짐) · 「자리로」", r1["name"] == "구분 표" and r1["bands"] == ["1", "1", "0"] and "18×11" in r1["meta"] and "같은 서식 3개" in r2["meta"]
              and "같은 서식" not in r1["meta"] and r1["bp"] is False and r1["go"], (r1, r2))
        check("글 후보 줄 — 템플릿 · 레벨 수 · 레터 사슬", rx["name"] == "주 사슬" and "템플릿 T1" in rx["meta"] and "레벨 2" in rx["meta"] and "1. › 가. › □" in rx["meta"], rx)
        keep = page.evaluate("() => { const l = document.querySelector('#headsDlg [data-sl-opt=keepText]'); return [l.querySelector('input').checked, l.textContent, (document.querySelector('#headsDlg .sl-opts .panel-help') || { dataset: {} }).dataset.help || '']; }")
        check("「글도 그대로 저장」 — 기본 꺼짐 · 설명은 노트 도움말(자료값은 견본으로 바꿔 저장)", keep[0] is False and keep[1] == "글도 그대로 저장" and "견본" in keep[2] and "자료값을 저장하지 않습니다" in keep[2], keep)
        size(page, "headsDlg", 320)
        fit = page.evaluate(FIT_COL)
        check("추출 후보 · 2열 320px — 가로 넘침 없음", fit["w"] in (319, 320) and not fit["bad"] and not fit["over"], fit)
        page.locator("#headsDlg").screenshot(path=str(OUT / "6_styles_save_320.png"))
        size(page, "headsDlg", 480)
        # 고르고 · 이름과 띠 수를 고치고 · 구조까지
        page.check("#headsDlg .sl-cand[data-cand=T1] .sl-crow > input[type=checkbox]")
        page.fill("#headsDlg .sl-cand[data-cand=T1] .sl-cname", "수요조사 표")
        page.fill("#headsDlg .sl-cand[data-cand=T1] input[data-band=headerRows]", "2")
        page.dispatch_event("#headsDlg .sl-cand[data-cand=T1] input[data-band=headerRows]", "change")
        page.check("#headsDlg .sl-cand[data-cand=T1] [data-sl-opt=blueprint] input")
        check("고르면 「고른 1개 저장」 이 켜짐(강조 단추)", page.inner_text("#headsDlgFoot [data-sl-act=save]") == "고른 1개 저장" and page.is_enabled("#headsDlgFoot [data-sl-act=save]"))
        # 이름 붙이기(LLM) — 직접 고친 이름·띠 수는 그대로, 나머지는 LLM 이름 · 추천 표
        page.click("#headsDlgTools [data-sl-act=name]")
        page.wait_for_function("() => document.querySelector('#headsDlg .sl-cand[data-cand=T2] .sl-cname').value.startsWith('항목 합계표')")
        rows = page.evaluate(ROWS)
        r1, r2, rx = row(rows, "T1"), row(rows, "T2"), row(rows, "X1")
        check("「이름 붙이기(LLM)」 — 몸 {llm: true} · 직접 고친 이름·띠 수는 그대로 · 나머지는 LLM 이름·띠 수 · 「추천」 표 · 고른 것은 안 바뀜", calls["cands"][1] == {"llm": True} and r1["name"] == "수요조사 표" and r1["bands"] == ["2", "1", "0"]
              and r2["name"] == "항목 합계표 — 머리 1행·합계행" and r2["bands"] == ["2", "0", "1"] and rx["name"] == "주 사슬 글 서식" and "추천" in r1["meta"] and "추천" not in r2["meta"]
              and [r["on"] for r in rows] == [True, False, False] and r1["bp"] is True and "claude-fable-5-2" in page.inner_text("#headsDlgTools"), rows)
        page.check("#headsDlg .sl-cand[data-cand=X1] .sl-crow > input[type=checkbox]")
        page.check("#headsDlg .sl-cand[data-cand=T2] .sl-crow > input[type=checkbox]")
        page.fill("#headsDlg .sl-cand[data-cand=T2] .sl-cname", "실패할 이름")
        page.check("#headsDlg [data-sl-opt=keepText] input")
        page.screenshot(path=str(OUT / "6_styles_save.png"))
        page.click("#headsDlgFoot [data-sl-act=save]")
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=T2] .sl-cstate.err")
        rows = page.evaluate(ROWS)
        check("저장 — 차례로 POST …/styles(표: table·bands·keepText·blueprint·name / 글: template) · 실패한 줄에 까닭 · 된 줄은 「저장했습니다」 · 열은 그대로",
              calls["save"] == [{"kind": "table", "table": IDS["table"], "bands": {"headerRows": 2, "headerCols": 1, "footRows": 0}, "keepText": True, "blueprint": True, "name": "수요조사 표"},
                                {"kind": "table", "table": "t900", "bands": {"headerRows": 2, "headerCols": 0, "footRows": 1}, "keepText": True, "blueprint": False, "name": "실패할 이름"},
                                {"kind": "text", "template": "tpl1", "keepText": True, "name": "주 사슬 글 서식"}]
              and "보관함에 저장했습니다" in row(rows, "T1")["state"] and "그 표를 찾지 못했습니다" in row(rows, "T2")["state"] and "보관함에 저장했습니다" in row(rows, "X1")["state"]
              and page.get_attribute("#headsDlg", "data-kind") == "styleSave" and page.inner_text("#headsDlgFoot [data-sl-act=save]") == "고른 1개 저장", (calls["save"], rows))
        page.fill("#headsDlg .sl-cand[data-cand=T2] .sl-cname", "항목 합계표")
        page.click("#headsDlgFoot [data-sl-act=save]")
        page.wait_for_selector("#headsDlg[data-kind=styleLib] .sl-item[data-style=n4]")
        its = page.evaluate(ITEMS)
        check("모두 되면 보관함 목록으로 — 새 서식이 「검증 중」 으로 보임 · 알림", [x["id"] for x in its] == ["s_tbl1", "n1", "n4"] and item(its, "n4")["verify"][0][:2] == ["running", "검증 중"] and "보관함에 저장했습니다" in page.inner_text("#toast")
              and page.inner_text("#headsDlgTools [data-sl-tab=text]") == "글 서식 2", [x["id"] for x in its])
        opts = page.evaluate("() => [...document.querySelector('#paneAgent select[data-ag-pick=table]').options].map((o) => o.textContent)")
        check("에이전트 입력의 표 서식 고르기에도 새 서식", "수요조사 표" in opts and "항목 합계표" in opts, opts)

        # ---- 7. 표 메뉴 「서식 보관함에 저장…」 — 그 표만 고른 채로
        def menu_save(tid, para):
            page.click(f'#doc .para[data-id="{para}"]')
            page.wait_for_function("(t) => tmn.active === t && tmnShown()", arg=tid)
            page.click(".tbl-corner")
            page.wait_for_selector(".ctx-menu:not([hidden])")
            page.click(".ctx-menu button:has-text('서식 보관함에 저장…')")
            page.wait_for_selector("#headsDlg[data-kind=styleSave] .sl-cand")
            return page.evaluate(ROWS)

        rows = menu_save(IDS["table"], IDS["cell_para"])
        check("표 메뉴 「서식 보관함에 저장…」 — 후보 열이 그 표만 고른 채로(나머지는 풀림)", [(r["key"], r["on"]) for r in rows if r["on"]] == [("T1", True)] and page.inner_text("#headsDlgFoot [data-sl-act=save]") == "고른 1개 저장", rows)
        other_para = next(p for p in map(first_para, other.get("cells") or []) if p)
        rows = menu_save(IDS["other"], other_para)
        check("후보에 없는 표 — 그 표로 줄을 하나 만들어 맨 위에 고른 채로(띠 수는 비워 자동 판정)", rows[0]["key"] == f"pick:{IDS['other']}" and rows[0]["on"] and rows[0]["bands"] == ["", "", ""] and [r["on"] for r in rows[1:]] == [False] * (len(rows) - 1), rows[:2])
        page.click("#headsDlgFoot [data-sl-act=save]")
        page.wait_for_selector("#headsDlg[data-kind=styleLib] .sl-item")
        check("그 표 저장 — 몸에 그 표 id · 띠 수는 안 보냄(서버가 판정)", calls["save"][-1]["table"] == IDS["other"] and "bands" not in calls["save"][-1], calls["save"][-1])

        # ---- 8. 「파일에서 추출」 → 후보 → from-file / 410
        with page.expect_file_chooser() as fc:
            page.click("#headsDlgTools [data-sl-act=fromFile]")
        check("「파일에서 추출」 — 파일 고르기(hwp·hwpx·docx·pdf)", fc.value.element.evaluate("(e) => e.accept") == ".hwp,.hwpx,.docx,.pdf")
        fc.value.set_files(str(ROOT / "samples" / "기술수요조사서.docx"))
        page.wait_for_selector("#headsDlg[data-kind=styleSave] .sl-cand[data-cand=F1]")
        rows = page.evaluate(ROWS)
        check("파일 후보 — 올린 것은 multipart · 제목에 파일 이름 · 옮기지 못하는 것 알림 · 「자리로」·「구조까지」·「이름 붙이기」 없음", "multipart/form-data" in calls["extract"][0] and "공고문.pdf" in page.inner_text("#headsDlgTitle")
              and "재지 못함" in page.inner_text("#headsDlgBody") and rows[0]["go"] is False and rows[0]["bp"] is None and page.locator("#headsDlgTools [data-sl-act=name]").count() == 0 and "3쪽" in rows[0]["meta"], rows)
        page.check("#headsDlg .sl-cand[data-cand=F1] .sl-crow > input[type=checkbox]")
        L["gone"] = True
        page.click("#headsDlgFoot [data-sl-act=save]")
        page.wait_for_selector("#headsDlg .sl-msg.err")
        check("410 — 「다시 올리세요」 한 줄(열은 그대로)", "다시 올리세요" in page.inner_text("#headsDlg .sl-wrap > .sl-msg.err") and page.get_attribute("#headsDlg", "data-kind") == "styleSave")
        L["gone"] = False
        page.click("#headsDlgFoot [data-sl-act=save]")
        page.wait_for_selector("#headsDlg[data-kind=styleLib] .sl-item[data-style=f0]")
        check("저장 — POST /api/styles/from-file 몸 = {token, picks: [{kind, key, name, bands}]}(파일·명세는 안 보냄)",
              calls["from_file"][-1] == {"token": "tok1", "picks": [{"kind": "table", "key": "F1", "name": "일정 표", "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}}]}, calls["from_file"][-1])

        # ---- 9. 보관함이 꺼져 있을 때(503) · 끝점이 없을 때(404) — 한 줄 까닭
        L["mode"] = "off"
        page.click("#paneAgent [data-ag-act=library]")
        page.wait_for_selector("#headsDlg[data-kind=styleLib] .hwarn.fail")
        check("보관함 꺼짐(503) — 「서식 보관함이 꺼져 있습니다」 한 줄 · 「다시 읽기」", "서식 보관함이 꺼져 있습니다" in page.inner_text("#headsDlg .hwarn.fail") and page.locator("#headsDlgBody .btn").all_inner_texts() == ["다시 읽기"])
        L["mode"] = "missing"
        page.click("#headsDlgBody .btn")
        page.wait_for_function("() => document.querySelector('#headsDlg .hwarn.fail').textContent.includes('서버를 다시 켜야')")
        fit = page.evaluate(FIT_COL)
        check("끝점 없음(404) — 「서버를 다시 켜야」 한 줄 · 화면이 깨지지 않음", not fit["bad"] and not fit["over"], fit)
        L["mode"] = "ok"
        page.click("#headsDlgBody .btn")
        page.wait_for_selector("#headsDlg[data-kind=styleLib] .sl-item")
        check("다시 읽으면 목록이 돌아온다", page.locator("#headsDlg .sl-item").count() >= 3)

        expected = [e for e in errors if re.search(r"status of (409|400|410|503|404)", e)]  # 일부러 낸 실패 응답(브라우저가 콘솔에 적는다 — 503·404 는 꺼 둔 동안 「검증 중」 다시 읽기도 받는다)
        left = [e for e in errors if e not in expected]
        seen = {s: sum(f"status of {s}" in e for e in expected) for s in (409, 400, 410, 503, 404)}
        check("콘솔 오류·pageerror 없음(일부러 낸 409·400·410 한 번씩 · 503·404 말고)", not left and seen[409] == seen[400] == seen[410] == 1 and seen[503] >= 1 and seen[404] >= 1, (left[:5], seen))
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

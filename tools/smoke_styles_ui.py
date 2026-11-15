"""서식 보관함(spec_일반편집 ② §7 · §12 — app/static/style_lib.js) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_styles_ui.py <그림·임시 폴더> [--port 18402]

보관함 끝점(`/api/styles…` · `…/styles/…`)과 에이전트 상태(`…/agent`)는 **흉내**다(page.route — 정규식). 문서·작업은 진짜 서버(기술수요조사서 hwpx).
- 2열 「서식 보관함」(팝업 아님): 종류 탭(표 서식 · 글 서식 + 수) · 서식마다 이름 · 원본 줄 · 충실도 꼬리표(원본 서식 · 요약 · 근사) · 검증 상태(검증 중 동그라미 · 확인 필요 · 검증 뒤 바뀜 · 검증 전) ·
  견본 그림(늦게 읽기 · 누르면 그 자리에서 크게) · 「뺀 것 · 검증 내역」(펴면 읽음).
- 「검증 중」 은 2초마다 그 서식을 다시 읽어 「검증됨」 으로 · 「다시 검증」.
- 이름 바꾸기(그 줄의 입력 칸 — Enter, 보낸 몸에 expectedRevision) · 409 는 새 판을 읽고 다시 · 지우기는 두 번(그 줄에서 확인).
- 적용: 「빈 표 넣기」(커서의 본문 최상위 블록 뒤 — 자리가 없으면 까닭) · 「고른 표에 입히기」 · 글 서식 항목 「고른 문단에 입히기」 — 보낸 몸 · 구조 편집 응답을 같은 길로.
- 「이 문서에서 추출」 → 후보(표 → 글): 체크 · 이름 · 띠 수 · 같은 서식 n개 · 「구조까지 저장」 · 「글도 그대로 저장」 · 「이름 붙이기(LLM)」(직접 고친 이름은 그대로) · 「고른 n개 저장」(차례로 — 보낸 몸) → 보관함으로.
- 「서식 복사」 열의 탭(spec_서식복사 ② §18): 탭 다섯(표지 서식 · 내용 서식 · 테이블 서식 · 쪽 설정 · 문단 서식 — 수 · 「· n개 고름」) · 처음 탭 · 그 탭의 후보만 보임 · 탭을 바꾸면 맨 위 · 0개인 탭의 한 줄 ·
  고름·저장 수는 모든 탭에 걸침 · 서식 관리자로 갔다 와도 고른 탭 그대로 · 서식 관리자의 갈래는 그대로 넷.
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
    {"id": "s_txt1", "revision": "r1", "kind": "text", "name": "본문 글머리", "note": "", "created": now, "updated": now, "source": {"name": "보고서.docx", "format": "docx", "page": None, "work": "w1", "project": "갑 과제", "job": "doc_edit", "round": 2, "where": "개요템플릿 1", "at": now - 60},
     "seenIn": [{"name": "작년 보고서.hwpx", "format": "hwpx", "project": "을 과제", "where": "개요템플릿 2", "at": now - 30}, {"name": "공고문.pdf", "format": "pdf"}], "fidelity": "summary", "losses": 0,
     "requirements": {"fonts": []}, "verify": None,
     "items": [{"key": "i1", "name": "□ 줄", "level": 1, "marker": {"mode": "literal", "literal": "□", "lead": "", "gap": " "}, "sample": "견본 글입니다"},
               {"key": "i2", "name": "자동 번호 줄", "level": 2, "marker": {"mode": "auto"}, "sample": "견본 글입니다"}]}]}
calls = {"list": 0, "poll": {}, "poll_at": [], "put": [], "delete": [], "verify": [], "apply": [], "cands": [], "save": [], "extract": [], "from_file": [], "proof": [], "preview": [], "preview_file": []}
PAGE = {"widthMm": 210, "heightMm": 297, "landscape": False, "marginsMm": {"l": 30, "r": 30, "t": 20, "b": 15, "header": 15, "footer": 15, "gutter": 0}}


# ---- 서식 그림(spec_서식복사 ② §13 — app/static/style_pic.js)의 견본 값: 형식 중립 — 표 명세 · 항목의 서식 요약 · 쪽 설정 · 표지의 부분 ----
def spec(rows, cols, bands):
    line, head = {"type": "SOLID", "width": "0.12 mm", "color": "#000000"}, bands.get("headerRows") or 0
    return {"rows": rows, "cols": cols, "bands": bands, "widthsMm": [30] + [20] * (cols - 1),
            "cells": [{"row": r, "col": c, "rowSpan": 1, "colSpan": 1, "text": "구분" if r < head else "0", "fill": "#E6E6E6" if r < head else None, "valign": "CENTER",
                       "edges": {k: line for k in "trbl"}, "format": {"font": "함초롬바탕", "sizePt": 10, "bold": r < head, "align": "center"}} for r in range(rows) for c in range(cols)]}


LEVELS = [{"key": "i1", "name": "1. 줄", "level": 1, "marker": {"mode": "literal", "literal": "1."}, "sample": "견본 글입니다", "format": {"font": "함초롬바탕", "sizePt": 14, "bold": True, "indentLeftMm": 0}},
          {"key": "i2", "name": "가. 줄", "level": 2, "marker": {"mode": "literal", "literal": "가."}, "sample": "견본 글입니다", "format": {"font": "함초롬바탕", "sizePt": 12, "indentLeftMm": 6}},
          {"key": "i3", "name": "□ 줄", "level": 3, "marker": {"mode": "literal", "literal": "□"}, "sample": "", "format": {"font": "함초롬바탕", "sizePt": 11, "indentLeftMm": 12, "firstLineMm": -4}}]
PARA_ITEM = {"key": "i1", "name": "본문", "level": None, "marker": {"mode": "none"}, "sample": "견본 글입니다", "format": {"font": "맑은 고딕", "sizePt": 10, "align": "justify", "lineSpacingPct": 160, "indentLeftMm": 3, "firstLineMm": -3}}
COVER_VIEW = {"page": PAGE, "parts": [{"type": "text", "key": "c1", "role": "title", "sample": "제목", "format": {"font": "함초롬돋움", "sizePt": 24, "bold": True, "align": "center"}, "gapBeforeMm": 40},
                                      {"type": "text", "key": "c2", "role": "org", "sample": "기관명", "format": {"font": "함초롬바탕", "sizePt": 14, "align": "center"}, "gapBeforeMm": 20},
                                      {"type": "table", "key": "c3", "spec": spec(2, 2, {"headerRows": 0, "headerCols": 1, "footRows": 0})},
                                      {"type": "text", "key": "c4", "role": "date", "sample": "0000. 00. 00.", "format": {"font": "함초롬바탕", "sizePt": 12, "align": "center"}, "gapBeforeMm": 30}]}


def view_of(s):  # 보관한 서식의 보기(GET /api/styles/{sid} 의 view)
    if s["kind"] == "table":
        return {"spec": spec(s.get("rows") or 2, s.get("cols") or 2, s.get("bands") or BANDS)}
    if s["kind"] == "text":
        return {"items": [{**it, "format": it.get("format") or {"font": "함초롬바탕", "sizePt": 12 - 2 * i, "bold": i == 0, "indentLeftMm": 6 * i}} for i, it in enumerate(s.get("items") or [])]}
    if s["kind"] == "page":
        return {"page": s.get("page") or PAGE, "body": s.get("body"), "summary": ""}
    return COVER_VIEW if s["kind"] == "cover" else {}


def preview_of(body):  # 후보의 견본(POST …/styles/preview — 몸 = 저장과 같은 꼴 → 그 종류의 보기)
    if body.get("kind") == "table":
        key = next((c["key"] for c in RICH["tables"] if c["table"] == body.get("table")), "")
        rows, cols = (18, 11) if body.get("table") == IDS.get("table") else (3, 4)
        return {"spec": spec(rows, cols, body.get("bands") or {"headerRows": 1, "headerCols": 0, "footRows": 0}), "key": key}
    if body.get("kind") == "page":
        return {"page": PAGE, "body": {"format": {"font": "함초롬바탕", "sizePt": 11}, "count": 40}, "summary": ""}
    if body.get("kind") == "cover":
        return COVER_VIEW
    return {"items": LEVELS} if body.get("template") else {"items": [{**PARA_ITEM, "role": body.get("role")}]}


RICH = {"on": False, "tables": []}  # 6-1절 — 후보가 많은 문서(보이는 줄만 견본을 받는지) · 표지·문단·쪽 설정 후보 · 검토 상태
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
    return {**s, "losses": ["캡션을 뺐습니다", "그림 채움을 뺐습니다"][: s["losses"] if isinstance(s["losses"], int) else 2], "verify": rec, "view": view_of(s)}


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
        return js(route, {"enabled": True, "pdf": L["pdf"], "styles": [summary(s) for s in L["styles"]], "broken": ["deadbeef0000"], **({"pdfDocx": True} if L.get("dual") else {})})  # dual = 두 형식을 아는 서버(spec_서식복사 ② §8 — 10절에서 켠다)
    if sid == "extract-file":
        calls["extract"].append(req.headers.get("content-type", ""))
        return js(route, {"token": "tok1", "name": "공고문.pdf", "format": "pdf", "losses": ["칸 여백·줄 간격·괘선 종류는 재지 못함"], "texts": [],
                          "tables": [{"key": "F1", "table": "pdf-1", "same": ["pdf-1"], "count": 1, "rows": 4, "cols": 3, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "sample": "일정", "page": 3}]})
    if sid == "preview-file":  # 파일 후보의 견본(② §13 — {token, pick: {kind, key, bands?}})
        body = json.loads(req.post_data)
        calls["preview_file"].append(body)
        return js(route, {"rev": None, "kind": "table", "view": {"spec": spec(4, 3, body["pick"].get("bands") or {"headerRows": 1, "headerCols": 0, "footRows": 0})}, "losses": [], "fidelity": "approx"})
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
        if L.get("proof") == "bad":  # 출력 그림을 못 읽는 경우(지워짐 · 옛 판)
            return js(route, {"detail": "그림이 없습니다"}, 404)
        return route.fulfill(status=200, content_type="image/png", body=PNG)
    if tail == "carrier":  # 「hwpx 받기」·「docx 받기」 — 운반 문서 내려받기(?format=)
        calls.setdefault("carrier", []).append(req.url[req.url.index("/api/"):])
        return route.fulfill(status=200, content_type="application/octet-stream", body=b"PK-carrier")
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


def rich_candidates(llm):  # 6-1절의 후보(② §12·§15·§16) — 표지 1 · 내용 1 + 쪽 설정 1 · 표 12 · 문단 2. llm = 검토 결과를 합친 것(이름 · keep · 역할 · 고침 · 의심 · 같은 서식 · 띠 넓히기)
    para, other = IDS["cell_para"], IDS["other"]
    seen = lambda *xs, fixed=(), doubts=(): {"by": "llm", "seen": list(xs), "fixed": list(fixed), "doubts": list(doubts)}
    tables = [{"key": f"R{i}", "table": f"t{800 + i}", "same": [f"t{800 + i}"], "count": 1, "rows": 3, "cols": 4, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "sample": "항목", "doubts": []} for i in range(1, 13)]
    out = {"rev": 0, "stage2": True, "format": "hwpx", "fidelity": "native", "tables": tables,
           "texts": [{"key": "X1", "template": {"id": "tpl1", "no": 1, "name": "주 사슬", "chain": ["1.", "가.", "□"]}, "doubts": ["mixedSlot"],
                      "items": [{"para": para, "level": i + 1, "letter": x, "sample": "개요", "format": {}} for i, x in enumerate(["1.", "가.", "□"])]}],
           "paras": [{"key": "P1", "role": "body", "count": 30, "where": {}, "doubts": [], "items": [{"para": para, "level": None, "sample": "한글 12자", "format": {"font": "맑은 고딕", "sizePt": 10}, "marker": {}}]},
                     {"key": "P2", "role": "other", "count": 4, "where": {"caption": 4}, "doubts": [], "items": [{"para": para, "level": None, "sample": "한글 5자", "format": {"font": "맑은 고딕", "sizePt": 9}, "marker": {}}]}],
           "pages": [{"key": "page", "page": PAGE, "body": {"format": {"font": "함초롬바탕", "sizePt": 11}, "count": 40}, "doubts": [], "sample": "A4 세로 · 여백 왼 30 · 오 30 · 위 20 · 아래 15mm · 본문 함초롬바탕 11pt",
                      "bodies": [{"key": "b1", "format": {"font": "함초롬바탕", "sizePt": 11}, "count": 40, "chars": 900, "sample": "한글 20자"}, {"key": "b2", "format": {"font": "맑은 고딕", "sizePt": 10}, "count": 30, "chars": 800, "sample": "한글 18자"}]}],
           "covers": [{"key": "cover", "blocks": [other], "end": other, "signals": {"bigTitle": True}, "doubts": [], "sample": "제목 · 기관명 · 표 · 날짜",
                       "parts": [{"block": other, "type": "text", "role": "title", "sample": "한글 8자", "sizePt": 24, "align": "center"}]}]}
    RICH["tables"] = tables
    if llm:
        for c in tables:
            c.update(keep=False, review=seen("이름", "띠 수", "역할"))
        tables[0].update(name="항목 자료표 — 머리 1행", keep=True, role="data")
        tables[1].update(name="항목 표 — 머리 2행", keep=True, bandsWider={"headerRows": 2, "headerCols": 0, "footRows": 0})
        tables[2].update(name="안내 표", keep=True, role="guide", review=seen("이름", "띠 수", "역할", doubts=[{"code": "guideText", "text": "안내문 표로 보임", "by": "llm"}]))
        tables[3].update(name="항목 자료표(둘째)", sameAs="R1")
        out["texts"][0].update(name="주 개요 내용 서식", keep=True, rep={"2": para}, review=seen("이름", "레벨", fixed=[{"what": "대표 문단", "from": "p1", "to": para}], doubts=[{"code": "mixedSlot", "text": "한 레벨에 서식이 여럿", "by": "script"}]))
        out["paras"][0].update(name="본문 서식", keep=True, review=seen("이름", "역할"))
        out["paras"][1].update(name="캡션 서식", keep=True, role="caption", review=seen("이름", "역할", fixed=[{"what": "역할", "from": "other", "to": "caption"}]))
        out["pages"][0].update(name="계획서 쪽 설정", keep=True, bodyKey="b2", review=seen("바탕 글", fixed=[{"what": "바탕 글", "from": "b1", "to": "b2"}]))
        out["covers"][0].update(name="계획서 표지", keep=True, isCover=True, end=other, roles={other: "title"}, review=seen("범위", "역할"))
        out["call"] = {"backend": "api", "model": "claude-fable-5-2", "ms": 5200, "costUsd": 0.03}
    return out


def doc_styles(route):
    req = route.request
    m = DOC.search(req.url)
    a, b = m.group(1), m.group(2)
    body = json.loads(req.post_data or "{}")
    if a == "preview":  # 후보의 견본 — 저장과 같은 몸(이름·구조까지는 없다). 옛 서버 흉내(끝점 없음)는 404 「Not Found」
        calls["preview"].append(body)
        if L.get("preview") == "missing":
            return js(route, {"detail": "Not Found"}, 404)
        return js(route, {"rev": 0, "kind": body.get("kind"), "view": preview_of(body), "losses": [], "fidelity": "native"})
    if a == "candidates" and RICH["on"]:
        calls["cands"].append(body)
        return js(route, rich_candidates(bool(body.get("llm"))))
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
        elif body["kind"] == "text" and not body.get("template"):  # 문단 서식(레벨 없음 — 역할)
            meta.update(items=[{"key": "i1", "name": "문단", "level": None, "marker": {"mode": "none"}, "sample": "견본 글입니다"}], leveled=False, role=body.get("role"))
        elif body["kind"] == "text":
            meta.update(items=[{"key": "i1", "name": "1. 줄", "level": 1, "marker": {"mode": "literal", "literal": "1."}, "sample": "견본 글입니다"}])
        elif body["kind"] == "page":
            meta.update(page=PAGE, body={"format": {"font": "함초롬바탕", "sizePt": 11}, "count": 40})
        L["styles"].append(meta)
        return js(route, meta, 201)
    if b == "apply":
        calls["apply"].append({"sid": a, **body})
        extra = {"made": {"table": IDS["table"], "rows": 6, "cols": 5}} if body["mode"] in ("tableBlank", "tableRestyle") else {"paged": {"sections": 1}} if body["mode"] == "page" \
            else {"covered": {"blocks": 4}} if body["mode"] == "cover" else {"formatted": {"paras": len(body["paras"])}}
        return js(route, edit_response(extra))
    return js(route, {"detail": "흉내에 없는 끝점"}, 500)


def agent(route):  # 에이전트 보기의 상태(「서식 보관함」 단추를 누르러 연다)
    js(route, {"enabled": True, "hwpx": True, "policy": {"apply": True, "why": ""}, "turns": [], "materials": [],
               "styles": {"table": [{"id": s["id"], "name": s["name"], "rows": s.get("rows"), "cols": s.get("cols"), "blueprint": s.get("blueprint")} for s in L["styles"] if s["kind"] == "table"],
                          "text": [{"id": s["id"], "name": s["name"], "items": s.get("items", [])} for s in L["styles"] if s["kind"] == "text"]}})


VIS = "(id) => { const e = document.getElementById(id); return !!e && !e.hidden && e.getClientRects().length > 0; }"
ITEMS = """() => [...document.querySelectorAll('#headsDlg .sl-item')].map((b) => { const q = (s) => [...b.querySelectorAll(s)].map((e) => e.textContent), img = b.querySelector('img.sl-proof'), pb = b.querySelector('.sl-picbox'), sp = b.querySelector('.sp-pic');
  return { id: b.dataset.style, tab: b.dataset.tab, name: (b.querySelector('.sl-name') || {}).textContent, tags: q('.sl-head .hb'), verify: [...b.querySelectorAll('.sl-verify')].map((e) => [e.dataset.status, e.textContent, !!e.querySelector('.sl-spin')]),
    src: (b.querySelector('.sl-src') || {}).textContent, srcTip: (b.querySelector('.sl-src') || { title: '' }).title, img: img ? [img.getAttribute('loading'), img.getAttribute('src'), !!img.closest('.sl-pic.big')] : null,
    first: b.firstElementChild.className, pic: pb ? [pb.dataset.picSrc, sp ? sp.dataset.spKind : '', sp ? sp.getAttribute('role') : '', sp ? sp.getAttribute('aria-label') : ''] : null,
    srcs: [...b.querySelectorAll('[data-sl-src]')].map((e) => [e.dataset.slSrc, e.textContent, e.disabled, e.getAttribute('aria-pressed')]), big: (b.querySelector('[data-sl-act=big]') || { getAttribute: () => null }).getAttribute('aria-expanded'),
    acts: [...b.querySelectorAll('.sl-acts [data-sl-act]')].map((e) => [e.dataset.slAct, e.disabled]), manage: [...b.querySelectorAll('.sl-manage [data-sl-act]')].map((e) => [e.dataset.slAct, e.disabled]),
    levels: q('.sl-levels .sl-lv'), msg: q('.sl-msg').join(' | '), confirm: !!b.querySelector('.sl-confirm') }; })"""
# 서식 그림 안에 편집 화면의 것이 없다(② §13 — 문서의 저장 길 paraEl·편집 id 에 안 잡힌다)
PURE = "() => document.querySelectorAll('#headsDlg .sp-pic [data-id], #headsDlg .sp-pic .para, #headsDlg .sp-pic table.tbl, #headsDlg .sp-pic .sheet, #headsDlg .sp-pic [contenteditable], #headsDlg .sp-pic [data-tbl], #headsDlg .sp-pic [data-cell]').length"
REVIEW = """(key) => { const b = document.querySelector(`#headsDlg .sl-cand[data-cand="${key}"]`); return b ? [...b.querySelectorAll('.sl-review .sl-rv')].map((e) => [e.dataset.rv, e.querySelector('span').textContent, !!e.querySelector('[data-sl-act=unfix]')]) : null; }"""


def manage(page, sid):  # 관리 단추(받기 · 이름 바꾸기 · 다시 검증 · 지우기)는 「⋯ 더보기」 아래 — 접혀 있으면 편다
    if page.locator(f"#headsDlg .sl-item[data-style={sid}] .sl-manage").count() == 0:
        page.click(f"#headsDlg .sl-item[data-style={sid}] [data-sl-act=more]")
        page.wait_for_selector(f"#headsDlg .sl-item[data-style={sid}] .sl-manage")


def unfold(page, key):  # 후보 줄의 그림 아래(견본 줄 · 서식 정보 · 검토 상태)는 기본으로 접혀 있다(spec_서식복사 ② §19-0) — 그 안을 누르기 전에 편다(편 것은 다시 그려도 편 채로)
    page.evaluate("(k) => { const d = document.querySelector(`#headsDlg .sl-cand[data-cand=\"${k}\"] .sl-cfold`); if (d) d.open = true; }", key)
    page.wait_for_function("(k) => { const d = document.querySelector(`#headsDlg .sl-cand[data-cand=\"${k}\"] .sl-cfold`); return !!d && d.open; }", arg=key)


ROWS = """() => [...document.querySelectorAll('#headsDlg .sl-cand')].map((b) => ({ key: b.dataset.cand, kind: b.dataset.kind, on: b.querySelector('.sl-crow > input[type=checkbox]').checked, name: b.querySelector('.sl-cname').value,
  bands: [...b.querySelectorAll('input[data-band]')].map((i) => i.value), meta: b.querySelector('.sl-cmeta').textContent, state: b.querySelector('.sl-cstate').textContent, go: !!b.querySelector('.sl-crow > .btn'),
  bp: b.querySelector('[data-sl-opt=blueprint] input') ? b.querySelector('[data-sl-opt=blueprint] input').checked : null }))"""
# 「서식 복사」 열의 탭(spec_서식복사 ② §18) — 탭 다섯(data-sl-ctab) · 그 탭의 후보 줄만 DOM 에 있다(ROWS 는 열린 탭의 줄) · 탭 아래 첫 줄이 그 갈래의 설명([data-sl-sec] 하나)
CTABS = "() => [...document.querySelectorAll('#headsDlg [data-sl-ctab]')].map((b) => [b.dataset.slCtab, b.textContent, b.getAttribute('aria-pressed')])"
CTIPS = "() => [...document.querySelectorAll('#headsDlg [data-sl-ctab]')].map((b) => b.title.split('\\n').pop())"  # 탭 도움말의 끝 줄 「후보 N · 고름 n( · 확인이 필요한 것 n)」
CSECS = "() => [...document.querySelectorAll('#headsDlg [data-sl-sec]')].map((e) => [e.dataset.slSec, e.querySelector('.panel-help')?.dataset.help || ''])"
CTAB_DESC = {"cover": "문서 첫 쪽의 블록 묶음", "content": "개요 레벨의 글 서식", "table": "띠 수와 구역 대표 칸의 모양", "page": "쪽 설정(용지 크기·방향·여백)", "para": "개요 레벨에 들지 않은 낱 문단"}  # 설명 줄의 앞머리


def ctab(page, key):  # 탭을 누른다 — 눌림이 옮겨 갈 때까지
    page.click(f"#headsDlg [data-sl-ctab={key}]")
    page.wait_for_selector(f'#headsDlg [data-sl-ctab={key}][aria-pressed="true"]')


def tab_rows(page, *keys):  # 그 탭들을 차례로 눌러 줄을 모은다(끝에는 마지막 탭이 열려 있다)
    out = []
    for k in keys:
        ctab(page, k)
        out += page.evaluate(ROWS)
    return out


def one_sec(page, key):  # 탭 아래 설명 줄이 그 탭의 것 하나뿐인가(전의 구역 제목 .sl-sec·.sl-sub 는 이 열에 없다)
    secs = page.evaluate(CSECS)
    return len(secs) == 1 and secs[0][0] == key and secs[0][1].startswith(CTAB_DESC[key]) and page.locator("#headsDlg[data-kind=styleSave] .sl-sec, #headsDlg[data-kind=styleSave] .sl-sub").count() == 0


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
        TABS = "() => [...document.querySelectorAll('#headsDlgTools [data-sl-tab]')].map((b) => [b.dataset.slTab, b.textContent, b.getAttribute('aria-pressed')])"
        tabs = page.evaluate(TABS)
        check("서식 관리자는 문서 옆 열(팝업 아님) · 갈래 세그먼트 넷 「표지 서식 0」 · 「내용 서식 1」(처음 고름) · 「테이블 서식 2」 · 「문단 서식 0」 · 복사 단추 둘", page.evaluate(VIS, "headsDlg") and page.locator("dialog[open]").count() == 0 and page.inner_text("#headsDlgTitle") == "서식 관리자"
              and tabs == [["cover", "표지 서식 0", "false"], ["content", "내용 서식 1", "true"], ["table", "테이블 서식 2", "false"], ["para", "문단 서식 0", "false"]]
              and page.locator("#headsDlgTools [data-sl-act]").all_inner_texts() == ["이 문서에서 복사", "파일에서 복사"] and "템플릿" not in page.inner_text("#headsDlgTools") and "문서 서식" not in page.inner_text("#headsDlgTools"), tabs)
        # 서식 그림(② §13) — 내용 서식: 레벨마다 한 줄(「L1」·「L2」 · 레터 · 글 막대 — 자동 번호는 회색 자리표) · 그림이 줄의 맨 앞 · role=img + 요약 글
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_txt1] .sp-pic[data-sp-kind=content]")
        x1 = item(page.evaluate(ITEMS), "s_txt1")
        lv = page.evaluate("""() => { const p = document.querySelector('#headsDlg .sl-item[data-style=s_txt1] .sp-pic'); return { rows: [...p.querySelectorAll('.sp-lv')].map((r) => [r.querySelector('.sp-tag').textContent, (r.querySelector('.sp-letter') || {}).textContent,
          !!r.querySelector('.sp-letter.sp-auto'), !!r.querySelector('.sp-bar'), parseFloat(r.querySelector('.sp-line').style.paddingLeft)]), hidden: p.querySelector('.sp-in').getAttribute('aria-hidden'), pe: getComputedStyle(p.querySelector('.sp-in')).pointerEvents }; }""")
        check("내용 서식의 그림 — 줄의 맨 앞 · 레벨마다 한 줄(L1 「□」 · L2 자동 번호의 회색 자리표 「1.」 · 글 막대 · 깊은 레벨이 더 들여쓰임) · role=img + 「개요 2레벨: …」 · 그림 안은 aria-hidden·누를 수 없음",
              x1["first"] == "sl-picbox" and x1["pic"] == ["web", "content", "img", "개요 2레벨: □ › 자동 번호"] and [r[:4] for r in lv["rows"]] == [["L1", "□", False, True], ["L2", "1.", True, True]]
              and lv["rows"][1][4] > lv["rows"][0][4] and lv["hidden"] == "true" and lv["pe"] == "none" and page.evaluate(PURE) == 0, (x1, lv))
        page.click("#headsDlgTools [data-sl-tab=cover]")
        check("「표지 서식」 — 없으면 한 줄 안내", "보관한 표지 서식이 없습니다" in page.inner_text("#headsDlgBody") and page.locator("#headsDlg .sl-item").count() == 0)
        page.click("#headsDlgTools [data-sl-tab=table]")
        check("「테이블 서식」 을 고르면 그 갈래만(눌림 표시)", [t[2] for t in page.evaluate(TABS)] == ["false", "false", "true", "false"])
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl2] .sp-pic[data-sp-kind=table]")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl1] .sp-pic[data-sp-kind=table]")
        its = page.evaluate(ITEMS)
        t1, t2 = item(its, "s_tbl1"), item(its, "s_tbl2")
        tp = page.evaluate("""() => { const p = document.querySelector('#headsDlg .sl-item[data-style=s_tbl1] .sp-pic'), td = p.querySelector('.sp-tbl td');
          return { tds: p.querySelectorAll('.sp-tbl td').length, trs: p.querySelectorAll('.sp-tbl tr').length, cols: p.querySelectorAll('.sp-tbl col').length, fill: td.style.backgroundColor, edge: td.style.borderTop, text: td.textContent,
                   bands: [...p.querySelectorAll('.sp-band')].map((b) => [b.dataset.spBand, b.textContent]), inTable: p.querySelectorAll('.sp-tbl .sp-band').length }; }""")
        check("테이블 서식의 그림 — 표 명세로 그린 작은 표(6행×5열 다 그림 · 음영 · 괘선 · 칸 글) · 띠 표시는 표 바깥의 괄호선과 글(「머리행 1–2」·「합계행 6」·「머리열 1」 — 음영을 덮지 않는다) · role=img + 「표 6×5 — …」",
              tp["tds"] == 30 and tp["trs"] == 6 and tp["cols"] == 5 and tp["fill"] == "rgb(230, 230, 230)" and "solid" in tp["edge"] and tp["text"] == "구분" and tp["inTable"] == 0
              and tp["bands"] == [["headerRows", "머리행 1–2"], ["footRows", "합계행 6"], ["headerCols", "머리열 1"]] and t1["pic"] == ["web", "table", "img", "표 6×5 — 머리행 1–2 · 머리열 1 · 합계행 6"] and page.evaluate(PURE) == 0, (tp, t1["pic"]))
        n_pic = {sid: calls["poll"].get(sid, 0) for sid in ("s_tbl2", "s_txt1")}
        page.click("#headsDlgTools [data-sl-tab=content]")
        page.click("#headsDlgTools [data-sl-tab=table]")
        page.wait_for_timeout(400)
        check("견본은 서식마다 한 번만 받는다(GET /api/styles/{sid}) — 갈래를 오가며 목록을 다시 그려도 그림을 다시 받지 않고 그대로 보인다", n_pic == {"s_tbl2": 1, "s_txt1": 1} and {sid: calls["poll"].get(sid, 0) for sid in n_pic} == n_pic
              and page.locator("#headsDlg .sl-item[data-style=s_tbl2] .sp-pic[data-sp-kind=table]").count() == 1, (n_pic, calls["poll"]))
        check("표 서식 줄 — 이름 · 충실도 꼬리표(원본 서식 / 근사) · 원본 줄(파일 · 쪽 · 크기 · 띠 수 · 구조)", [x["name"] for x in its] == ["예산 총괄표", "PDF 에서 잰 일정표"] and t1["tags"] == ["원본 서식"] and t2["tags"] == ["근사"]
              and all(k in t1["src"] for k in ("원본 연구개발계획서_양식.hwpx · 12쪽", "6×5", "머리행 2 · 머리열 1 · 합계행 1", "구조 있음")) and "구조 있음" not in t2["src"], (t1, t2))
        check("검증 상태(형식 이름과 함께 — 옛 서버라 hwpx 만) — 「hwpx 검증 중」(동그라미) / 「hwpx 확인 필요」 + 「hwpx 검증 뒤 바뀜」", t1["verify"] == [["running", "hwpx 검증 중", True]] and t2["verify"] == [["warn", "hwpx 확인 필요", False], ["stale", "hwpx 검증 뒤 바뀜", False]]
              and page.locator("#headsDlg .sl-verify[data-format=docx]").count() == 0, (t1["verify"], t2["verify"]))
        check("그림의 원천 — 기본 「웹 견본」 · 「한글 출력」 은 그 형식의 검증이 끝나 그림이 있을 때만 켜짐(검증 중이면 꺼짐) · 옛 서버라 「Word 출력」 은 없음 · 출력 그림은 저절로 뜨지 않는다",
              t1["img"] is None and t2["img"] is None and t1["srcs"] == [["web", "웹 견본", False, "true"], ["hwpx", "한글 출력", True, "false"]]
              and t2["srcs"] == [["web", "웹 견본", False, "true"], ["hwpx", "한글 출력", False, "false"]] and t1["big"] == "false", (t1["srcs"], t2["srcs"]))
        check("단추 — 동작 이름에 적용 범위: 구조가 있는 서식만 「빈 표 넣기」 · 「표 모양 입히기」 · 관리 단추는 「⋯ 더보기」 한 단추 아래(접힘)",
              t1["acts"] == [["blank", False], ["restyle", False], ["more", False]] and t2["acts"] == [["restyle", False], ["more", False]] and t1["manage"] == []
              and page.inner_text("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=restyle]") == "표 모양 입히기" and page.inner_text("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=more]") == "⋯ 더보기"
              and page.get_attribute("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=more]", "aria-expanded") == "false", (t1["acts"], t2["acts"]))
        manage(page, "s_tbl1")
        manage(page, "s_tbl2")
        its = page.evaluate(ITEMS)
        check("「⋯ 더보기」 — 줄 안에서 펴짐(팝업 아님): 「hwpx 받기」(옛 서버라 docx 받기는 없음) · 이름 바꾸기 · 다시 검증(검증 중이면 꺼짐) · 지우기",
              item(its, "s_tbl1")["manage"] == [["getHwpx", False], ["rename", False], ["verify", True], ["delete", False]] and item(its, "s_tbl2")["manage"] == [["getHwpx", False], ["rename", False], ["verify", False], ["delete", False]]
              and page.get_attribute("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=more]", "aria-expanded") == "true" and page.locator("dialog[open]").count() == 0, its)
        check("발치 — 수 요약(갈래 넷) · 읽지 못한 서식 알림", "표지 서식 0 · 내용 서식 1 · 테이블 서식 2 · 문단 서식 0" in page.inner_text("#headsDlgFoot") and "읽지 못한 서식 1개" in page.inner_text("#headsDlgBody"))
        page.screenshot(path=str(OUT / "1_styles_lib.png"))

        # 「검증 중」 → 2초마다 그 서식을 다시 읽어 「검증됨」(같은 끝점을 서식 그림도 한 번 읽는다 — 흉내는 둘째 읽기에서 검증을 끝낸다)
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl1] .sl-verify[data-status=ok]", timeout=15000)
        at = [t for sid, t in calls["poll_at"] if sid == "s_tbl1"]
        t1 = item(page.evaluate(ITEMS), "s_tbl1")
        check("검증 중 → 2초마다 GET /api/styles/{sid} → 「검증됨」 · 「한글 출력」 이 켜짐(저절로 바꾸지는 않는다 — 웹 견본 그대로) · 「다시 검증」 이 켜짐", len(at) in (2, 3) and 1.7 <= at[-1] - at[-2] <= 3.5 and t1["verify"] == [["ok", "hwpx 검증됨", False]]
              and t1["img"] is None and t1["pic"][:2] == ["web", "table"] and t1["srcs"][1] == ["hwpx", "한글 출력", False, "false"] and ["verify", False] in t1["manage"], (at, t1))
        tip = page.get_attribute("#headsDlg .sl-item[data-style=s_tbl1] .sl-verify[data-status=ok]", "title")
        check("「검증됨」 의 도움말 — 저장한 서식이 제 값대로 출력된다는 뜻(원본 문서와 같은지는 견주지 않음)", "저장한 서식이 제 값대로 출력된다는 뜻" in tip and "원본 문서와 같은지는 견주지 않습니다" in tip, tip)
        page.wait_for_timeout(2600)
        check("끝난 뒤에는 더 읽지 않는다", len([1 for sid, _ in calls["poll_at"] if sid == "s_tbl1"]) == len(at), calls["poll"])
        page.click("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-src=hwpx]")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl1] img.sl-proof")
        t1 = item(page.evaluate(ITEMS), "s_tbl1")
        check("「한글 출력」 을 고르면 — PDF 검증 그림(늦게 읽기 · 주소에 revision) · 고른 원천이 눌림 · 다시 그려도 고른 것이 남는다", t1["img"] == ["lazy", "/api/styles/s_tbl1/proof.png?v=r2", False] and t1["pic"][0] == "hwpx"
              and t1["srcs"] == [["web", "웹 견본", False, "false"], ["hwpx", "한글 출력", False, "true"]], t1)
        page.click("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=big]")
        big = item(page.evaluate(ITEMS), "s_tbl1")
        page.click("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=big]")
        small = item(page.evaluate(ITEMS), "s_tbl1")
        check("「크게」(그림 밖 단추 · aria-expanded) — 그 자리에서 크게 · 다시 누르면 작게(대화창 없음)", big["big"] == "true" and big["img"][2] is True and small["big"] == "false" and small["img"][2] is False and page.locator("dialog[open]").count() == 0, (big, small))
        page.click("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-src=web]")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl1] .sp-pic[data-sp-kind=table]")
        page.click("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=big]")
        wide = page.evaluate("""() => { const b = document.querySelector('#headsDlg .sl-item[data-style=s_tbl1] .sl-pic'), col = document.getElementById('headsDlgBody');
          return [b.classList.contains('big'), b.scrollWidth > b.clientWidth, col.scrollWidth - col.clientWidth, b.querySelectorAll('.sp-tbl tr').length]; }""")
        page.click("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=big]")
        check("웹 견본의 「크게」 — 그 상자 안에서만 가로로 넘긴다(열 전체는 안 넘침) · 표의 행을 다 보임", wide[0] and wide[1] and wide[2] <= 0 and wide[3] == 6
              and not page.evaluate("() => document.querySelector('#headsDlg .sl-item[data-style=s_tbl1] .sl-pic').classList.contains('big')"), wide)
        page.click("#headsDlg .sl-item[data-style=s_tbl1] .sl-more summary")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl1] .sl-more li")
        more = page.inner_text("#headsDlg .sl-item[data-style=s_tbl1] .sl-more")
        check("「뺀 것 2 · 검증 내역」 — 펴면 뺀 것 · 필요한 글꼴 · 검사마다의 결과", "뺀 것 2" in more and "캡션을 뺐습니다" in more and "필요한 글꼴 — 함초롬바탕" in more and "음영 — 통과" in more and "글꼴 — 모름" in more and "대체 글꼴로 출력" in more, more)

        # 「다시 검증」
        page.click("#headsDlg .sl-item[data-style=s_tbl2] [data-sl-act=verify]")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl2] .sl-verify[data-status=running]")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl2] .sl-verify[data-status=ok]", timeout=15000)
        check("「다시 검증」 — POST …/verify → 검증 중 → 검증됨(「검증 뒤 바뀜」 이 걷힘)", calls["verify"] == ["s_tbl2"] and item(page.evaluate(ITEMS), "s_tbl2")["verify"] == [["ok", "hwpx 검증됨", False]])

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
        check("한 번 더 — DELETE …?expectedRevision= · 줄이 사라짐 · 탭의 수가 줄어듦", calls["delete"] == ["/api/styles/s_tbl2?expectedRevision=r1"] and page.inner_text("#headsDlgTools [data-sl-tab=table]") == "테이블 서식 1", calls["delete"])

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
        page.wait_for_function("() => document.getElementById('toast').textContent.includes('표 모양을 입혔습니다')")
        check("「표 모양 입히기」(전의 「고른 표에 입히기」) — 몸 = {mode: tableRestyle, table: 고른 표}", calls["apply"][1] == {"sid": "s_tbl1", "mode": "tableRestyle", "table": IDS["table"]}, calls["apply"][1:])
        page.wait_for_function("() => !state.busy && document.querySelector('#doc .sheet .para') != null")
        page.click("#headsDlgTools [data-sl-tab=content]")
        its = page.evaluate(ITEMS)
        x1 = item(its, "s_txt1")
        check("내용 서식 — 요약 꼬리표 · 검증 전 · 항목(레벨)마다 한 줄 + 「글자·문단 모양 입히기」", [x["id"] for x in its] == ["s_txt1"] and x1["tags"] == ["요약"] and x1["verify"] == [["pending", "hwpx 검증 전", False]] and x1["levels"] == ["L1", "L2"]
              and page.locator("#headsDlg .sl-levels [data-sl-item]").count() == 2 and "자동 번호" in page.inner_text("#headsDlg .sl-levels") and x1["tab"] == "content"
              and page.locator("#headsDlg .sl-levels [data-sl-item]").all_inner_texts() == ["글자·문단 모양 입히기"] * 2 and "레벨 2" in x1["src"], x1)
        tip = x1["srcTip"].split("\n")
        check("원본 문서 줄(spec_서식복사 ② §17) — 「원본 문서 · 프로젝트 · 자리 외 N개 문서」 + 풍선에 TASK · 라운드 · 같은 서식이 나온 다른 문서",
              x1["src"].startswith("원본 보고서.docx · 프로젝트 갑 과제 · 개요템플릿 1 외 2개 문서 · ") and tip[0].startswith("이 서식을 뽑은 문서 — 보고서.docx · 프로젝트 갑 과제 · TASK ")
              and "라운드 2" in tip[0] and "개요템플릿 1" in tip[0] and tip[1] == "같은 서식이 나온 다른 문서:" and tip[2].startswith("· 작년 보고서.hwpx · 프로젝트 을 과제 · 개요템플릿 2") and tip[3] == "· 공고문.pdf", (x1["src"], tip))
        page.click(f'#doc .para[data-id="{IDS["cell_para"]}"]')
        page.click("#headsDlg .sl-levels [data-sl-item=i2]")
        page.wait_for_function("() => document.getElementById('toast').textContent.includes('글자·문단 모양을 입혔습니다')")
        check("「글자·문단 모양 입히기」(전의 「고른 문단에 입히기」) — 몸 = {mode: format, item, paras: [커서 문단]}", calls["apply"][2] == {"sid": "s_txt1", "mode": "format", "item": "i2", "paras": [IDS["cell_para"]]}, calls["apply"][2:])
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
        tabs, tips = page.evaluate(CTABS), page.evaluate(CTIPS)
        check("서식 복사의 탭 다섯(② §18) — 표지 서식 · 내용 서식 · 테이블 서식 · 쪽 설정 · 문단 서식 차례 · 글에 후보 수(0개인 탭도 보임) · 처음 탭 = 내용 서식(후보가 있을 때) · 단계 줄 바로 아래 · 도움말에 「후보 N · 고름 n」",
              tabs == [["cover", "표지 서식 0", "false"], ["content", "내용 서식 1", "true"], ["table", "테이블 서식 2", "false"], ["page", "쪽 설정 0", "false"], ["para", "문단 서식 0", "false"]]
              and tips == ["후보 0 · 고름 0", "후보 1 · 고름 0", "후보 2 · 고름 0", "후보 0 · 고름 0", "후보 0 · 고름 0"]
              and page.evaluate("() => { const w = document.querySelector('#headsDlg .sl-wrap'); return w.children[0].classList.contains('sl-steps-row') && w.children[1].classList.contains('sl-ctabs') && w.children[1].getAttribute('role') === 'group'; }"), (tabs, tips))
        check("서식 복사 후보 — 보이는 줄은 그 탭(내용 서식)의 것뿐 · 탭 아래 첫 줄 = 그 갈래의 설명 하나(구역 제목은 없다) · 처음에는 아무것도 안 고름 · 「고른 0개 저장」 꺼짐 · 보낸 몸 {llm: false}", [(r["key"], r["kind"], r["on"]) for r in rows] == [("X1", "text", False)]
              and page.inner_text("#headsDlgFoot [data-sl-act=save]") == "고른 0개 저장" and page.is_disabled("#headsDlgFoot [data-sl-act=save]") and calls["cands"] == [{"llm": False}]
              and one_sec(page, "content") and page.text_content("#headsDlgTitle").startswith("서식 복사 — "), (rows, page.evaluate(CSECS)))
        STEPS = "() => [...document.querySelectorAll('#headsDlg .sl-steps .sl-step')].map((e) => [e.dataset.step, e.dataset.state, e.querySelector('.sl-step-name').textContent, e.getAttribute('aria-current') || ''])"
        steps = page.evaluate(STEPS)
        check("단계 줄 — ① 후보 찾기(끝남 ✓) › ② LLM 검토(다음) › ③ 저장 › ④ PDF 검증 · 「한 번에 진행」(강조 — 고른 것이 없을 때)", steps == [["find", "done", "후보 찾기", ""], ["name", "todo", "LLM 검토", "step"], ["save", "todo", "저장", ""], ["verify", "todo", "PDF 검증", ""]]
              and "✓" in page.inner_text("#headsDlg .sl-step[data-step=find]") and page.inner_text("#headsDlg [data-sl-act=auto]") == "한 번에 진행" and "primary" in page.get_attribute("#headsDlg [data-sl-act=auto]", "class"), steps)
        rx = row(rows, "X1")
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=X1] .sp-pic[data-sp-kind=content]")  # 내용 서식 탭의 줄 — 그림 · 검토 상태를 먼저 읽어 둔다(탭을 바꾸면 이 줄은 DOM 에 없다)
        cx = page.evaluate("""() => { const x = document.querySelector('#headsDlg .sl-cand[data-cand=X1]');
          const d = x.querySelector(':scope > .sl-cfold');
          return { order: [...x.children].map((e) => e.className.split(' ')[0]), levels: x.querySelectorAll('.sp-lv').length, cap: x.querySelector('.sl-pic-cap').textContent,
                   fold: d ? { open: d.open, kids: [...d.querySelector('.sl-cfold-body').children].map((e) => e.className.split(' ')[0]), sum: [...d.querySelector('summary').children].map((e) => e.textContent),
                               hidden: !x.querySelector('.sl-review').checkVisibility() && !x.querySelector('.sl-pic-cap').checkVisibility() } : null }; }""")
        rvx = page.evaluate(REVIEW, "X1")
        ctab(page, "cover")
        check("후보가 0개인 탭(표지 서식) — 누를 수 있고, 그 갈래가 왜 없는지 한 줄 「이 문서에서 표지 서식 후보를 찾지 못했습니다」 · 후보 줄 없음", page.locator("#headsDlg .sl-cand").count() == 0 and one_sec(page, "cover")
              and page.locator("#headsDlg .sl-wrap > .hnote").all_inner_texts() == ["이 문서에서 표지 서식 후보를 찾지 못했습니다."], page.inner_text("#headsDlg .sl-wrap"))
        ctab(page, "table")
        rows = page.evaluate(ROWS)
        check("탭 「테이블 서식」 을 누르면 표 후보만 보이고 눌림(aria-pressed)이 옮겨 간다 · 설명 줄도 그 탭의 것 하나", [(r["key"], r["kind"], r["on"]) for r in rows] == [("T1", "table", False), ("T2", "table", False)]
              and [t[2] for t in page.evaluate(CTABS)] == ["false", "false", "true", "false", "false"] and "on" in page.get_attribute("#headsDlg [data-sl-ctab=table]", "class").split() and one_sec(page, "table"), (rows, page.evaluate(CTABS)))
        r1, r2 = row(rows, "T1"), row(rows, "T2")
        sim = page.get_attribute("#headsDlg .sl-cand[data-cand=T2] .sl-cmeta span[title^='띠 수와']", "title") or ""
        check("표 후보 줄 — 이름(첫 칸 글로) · 크기 · 띠 수 칸 셋 · 「비슷한 서식 3개」(전의 「같은 서식」 — 그림은 대표 표 하나의 것) · 「구조까지 저장」(꺼짐) · 「자리로」", r1["name"] == "구분 표" and r1["bands"] == ["1", "1", "0"] and "18×11" in r1["meta"]
              and "비슷한 서식 3개" in r2["meta"] and "같은 서식" not in r2["meta"] and "비슷한 서식" not in r1["meta"] and "띠 수와 구역 대표 칸의 모양이 같은 표 — 그림은 대표 표 하나의 것" in sim and r1["bp"] is False and r1["go"], (r1, r2, sim))
        cf = cx["fold"] or {}
        check("후보 줄의 그림 아래(견본 줄 · 서식 정보 · 검토 상태)는 기본으로 접힘 「자세히」 — 접어도 요약 줄에 확인 수(사용자 \"이 부분은 기본적으로 접어줘\")",
              cf.get("open") is False and cf.get("kids") == ["sl-picbar", "sl-cmeta", "sl-review"] and cf.get("hidden") is True and (cf.get("sum") or [""])[0] == "자세히"
              and any(t.startswith("확인 ") for t in cf.get("sum") or []) == any(r[0] == "doubt" for r in rvx or []), (cf, rvx))
        check("글 후보 줄 — 템플릿 · 레벨 수 · 레터 사슬", rx["name"] == "주 사슬" and "템플릿 T1" in rx["meta"] and "레벨 2" in rx["meta"] and "1. › 가. › □" in rx["meta"], rx)
        # 후보 줄의 그림 = 저장될 견본(POST …/styles/preview — 몸은 저장과 같은 꼴: 이름·구조까지는 없다) · 검토 상태는 글로(LLM 이 아직 안 봄)
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=T1] .sp-pic[data-sp-kind=table]")
        cp = {**cx, **page.evaluate("""() => { const t = document.querySelector('#headsDlg .sl-cand[data-cand=T1]');
          return { trs: t.querySelectorAll('.sp-tbl tr').length, over: !!t.querySelector('.sp-frame.sp-over'),
                   note: (t.querySelector('.sp-note') || {}).textContent || '', bands: [...t.querySelectorAll('.sp-band')].map((b) => b.textContent) }; }""")}
        check("후보 줄 — 체크·이름 줄 바로 아래에 그림(저장될 견본 · 웹 견본) → 요약 → 검토 상태 · 내용 서식 = 레벨마다 한 줄 · 표는 행을 자르지 않고 다 그린 뒤 높이만 제한(아래 흐림 + 「전체 18행」) · 띠 표시",
              cp["order"][:3] == ["sl-crow", "sl-picbox", "sl-cfold"] and cp["levels"] == 3 and cp["cap"] == "저장될 견본 · 웹 견본" and cp["trs"] == 18 and cp["over"] and "전체 18행" in cp["note"]
              and cp["bands"] == ["머리행 1", "머리열 1"] and page.evaluate(PURE) == 0, cp)
        check("견본 요청 — 저장과 같은 몸(표: table·bands·keepText / 글: template·keepText) · 이름·구조까지는 안 보냄",
              {"kind": "text", "template": "tpl1", "keepText": False} in calls["preview"] and {"kind": "table", "table": IDS["table"], "bands": {"headerRows": 1, "headerCols": 1, "footRows": 0}, "keepText": False} in calls["preview"]
              and all("name" not in b and "blueprint" not in b for b in calls["preview"]), calls["preview"])
        check("검토 상태(LLM 이 아직 안 봄) — 줄마다 글 「스크립트 후보 — LLM 이 보지 않음」", page.evaluate(REVIEW, "T1") == [["by", "스크립트 후보 — LLM 이 보지 않음", False]] and rvx == [["by", "스크립트 후보 — LLM 이 보지 않음", False]], (page.evaluate(REVIEW, "T1"), rvx))
        keep = page.evaluate("() => { const l = document.querySelector('#headsDlg [data-sl-opt=keepText]'); return [l.querySelector('input').checked, l.textContent, (document.querySelector('#headsDlg .sl-opts .panel-help') || { dataset: {} }).dataset.help || '']; }")
        check("「글도 그대로 저장」 — 기본 꺼짐 · 설명은 노트 도움말(자료값은 견본으로 바꿔 저장)", keep[0] is False and keep[1] == "글도 그대로 저장" and "견본" in keep[2] and "자료값을 저장하지 않습니다" in keep[2], keep)
        size(page, "headsDlg", 320)
        fit = page.evaluate(FIT_COL)
        lines = page.evaluate("() => new Set([...document.querySelectorAll('#headsDlg [data-sl-ctab]')].map((b) => Math.round(b.getBoundingClientRect().top))).size")
        check("추출 후보 · 2열 320px — 가로 넘침 없음 · 탭 다섯은 다음 줄로 접힌다(다섯 다 보임)", fit["w"] in (319, 320) and not fit["bad"] and not fit["over"] and lines >= 2
              and page.evaluate("() => [...document.querySelectorAll('#headsDlg [data-sl-ctab]')].every((b) => b.getClientRects().length > 0 && b.scrollWidth <= b.clientWidth + 1)"), (fit, lines))
        page.locator("#headsDlg").screenshot(path=str(OUT / "6_styles_save_320.png"))
        size(page, "headsDlg", 480)
        # 고르고 · 이름과 띠 수를 고치고 · 구조까지
        page.check("#headsDlg .sl-cand[data-cand=T1] .sl-crow > input[type=checkbox]")
        page.fill("#headsDlg .sl-cand[data-cand=T1] .sl-cname", "수요조사 표")
        unfold(page, "T1")
        page.fill("#headsDlg .sl-cand[data-cand=T1] input[data-band=headerRows]", "2")
        page.dispatch_event("#headsDlg .sl-cand[data-cand=T1] input[data-band=headerRows]", "change")
        page.check("#headsDlg .sl-cand[data-cand=T1] [data-sl-opt=blueprint] input")
        check("고르면 「고른 1개 저장」 이 켜짐(강조 단추)", page.inner_text("#headsDlgFoot [data-sl-act=save]") == "고른 1개 저장" and page.is_enabled("#headsDlgFoot [data-sl-act=save]"))
        picked = page.evaluate(CTABS)  # 고름을 바꾸면 탭 글도 바뀐다(다시 그리지 않고 글만)
        ctab(page, "content")
        check("한 탭에서 고르면 그 탭 글에 「· 1개 고름」 — 다른 탭으로 가도 그대로 보이고, 저장 단추 「고른 1개 저장」 은 모든 탭을 합친 수 그대로 · 도움말 「고름 1」", picked[2][1] == "테이블 서식 2 · 1개 고름"
              and [t[1] for t in page.evaluate(CTABS)] == ["표지 서식 0", "내용 서식 1", "테이블 서식 2 · 1개 고름", "쪽 설정 0", "문단 서식 0"] and page.evaluate(CTIPS)[2] == "후보 2 · 고름 1"
              and page.inner_text("#headsDlgFoot [data-sl-act=save]") == "고른 1개 저장" and page.is_enabled("#headsDlgFoot [data-sl-act=save]") and [r["key"] for r in page.evaluate(ROWS)] == ["X1"], (picked, page.evaluate(CTABS)))
        ctab(page, "table")
        r1 = row(page.evaluate(ROWS), "T1")
        check("탭을 바꿨다 돌아와도 줄의 상태(고름 · 이름 · 띠 수 · 구조까지)는 그대로 — 후보 자료에 남는다", r1["on"] and r1["name"] == "수요조사 표" and r1["bands"] == ["2", "1", "0"] and r1["bp"] is True, r1)
        # 이름 붙이기(LLM) — 직접 고친 이름·띠 수는 그대로, 나머지는 LLM 이름 · 추천 표(모든 탭의 후보를 본다 — 보이는 탭만이 아니다)
        page.click("#headsDlgTools [data-sl-act=name]")
        page.wait_for_function("() => document.querySelector('#headsDlg .sl-cand[data-cand=T2] .sl-cname').value.startsWith('항목 합계표')")
        rows = tab_rows(page, "content", "table")
        r1, r2, rx = row(rows, "T1"), row(rows, "T2"), row(rows, "X1")
        check("「LLM 검토」(전의 「에이전트 추출」) — 몸 {llm: true} · 직접 고친 이름·띠 수는 그대로 · 나머지는 LLM 이름·띠 수 · 「추천」 표 · 고른 것은 안 바뀜 · 단계 ② 끝남", calls["cands"][1] == {"llm": True} and r1["name"] == "수요조사 표" and r1["bands"] == ["2", "1", "0"]
              and r2["name"] == "항목 합계표 — 머리 1행·합계행" and r2["bands"] == ["2", "0", "1"] and rx["name"] == "주 사슬 글 서식" and "추천" in r1["meta"] and "추천" not in r2["meta"]
              and [r["on"] for r in rows] == [False, True, False] and r1["bp"] is True and "claude-fable-5-2" in page.inner_text("#headsDlgTools")
              and page.inner_text("#headsDlgTools [data-sl-act=name]") == "LLM 검토" and page.evaluate(STEPS)[1][1] == "done" and "LLM 검토 끝" in page.inner_text("#headsDlg .sl-wrap > .sl-msg"), rows)
        page.wait_for_function("() => { const b = document.querySelector('#headsDlg .sl-cand[data-cand=T1] .sp-band'); return !!b && b.textContent === '머리행 1–2'; }")
        check("띠 수를 고치면 견본을 다시 받는다(새 띠 수로) — 그림의 띠 표시도 따라 바뀜", {"kind": "table", "table": IDS["table"], "bands": {"headerRows": 2, "headerCols": 1, "footRows": 0}, "keepText": False} in calls["preview"]
              and page.evaluate("() => [...document.querySelectorAll('#headsDlg .sl-cand[data-cand=T1] .sp-band')].map((b) => b.textContent)") == ["머리행 1–2", "머리열 1"], calls["preview"][-3:])
        ctab(page, "content")
        page.check("#headsDlg .sl-cand[data-cand=X1] .sl-crow > input[type=checkbox]")
        ctab(page, "table")
        page.check("#headsDlg .sl-cand[data-cand=T2] .sl-crow > input[type=checkbox]")
        page.fill("#headsDlg .sl-cand[data-cand=T2] .sl-cname", "실패할 이름")
        page.check("#headsDlg [data-sl-opt=keepText] input")
        check("여러 탭에서 고른 것 — 탭마다 「· n개 고름」 · 저장 단추는 합친 수 「고른 3개 저장」", [t[1] for t in page.evaluate(CTABS)] == ["표지 서식 0", "내용 서식 1 · 1개 고름", "테이블 서식 2 · 2개 고름", "쪽 설정 0", "문단 서식 0"]
              and page.inner_text("#headsDlgFoot [data-sl-act=save]") == "고른 3개 저장", page.evaluate(CTABS))
        page.screenshot(path=str(OUT / "6_styles_save.png"))
        page.click("#headsDlgFoot [data-sl-act=save]")  # 저장은 모든 탭의 고른 것(열린 탭 = 테이블 서식 — 내용 서식 탭의 X1 도 저장된다)
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=T2] .sl-cstate.err")
        rows = tab_rows(page, "content", "table")
        check("저장 — 차례로 POST …/styles(표: table·bands·keepText·blueprint·name / 글: template) · 실패한 줄에 까닭 · 된 줄은 「저장했습니다」 · 열은 그대로",
              calls["save"] == [{"kind": "text", "template": "tpl1", "keepText": True, "name": "주 사슬 글 서식"},
                                {"kind": "table", "table": IDS["table"], "bands": {"headerRows": 2, "headerCols": 1, "footRows": 0}, "keepText": True, "blueprint": True, "name": "수요조사 표"},
                                {"kind": "table", "table": "t900", "bands": {"headerRows": 2, "headerCols": 0, "footRows": 1}, "keepText": True, "blueprint": False, "name": "실패할 이름"}]
              and "보관함에 저장했습니다" in row(rows, "T1")["state"] and "그 표를 찾지 못했습니다" in row(rows, "T2")["state"] and "보관함에 저장했습니다" in row(rows, "X1")["state"]
              and page.get_attribute("#headsDlg", "data-kind") == "styleSave" and page.inner_text("#headsDlgFoot [data-sl-act=save]") == "고른 1개 저장", (calls["save"], rows))
        page.fill("#headsDlg .sl-cand[data-cand=T2] .sl-cname", "항목 합계표")
        page.click("#headsDlgFoot [data-sl-act=save]")
        # 저장 뒤 — 이 열에 남아 검증 진행 줄(서식마다 2초마다 다시 읽음) → 요약 + 「서식 관리자에서 보기」
        page.wait_for_selector("#headsDlg .sl-vbox")
        check("저장 뒤 — 열은 「서식 복사」 그대로 · 검증 진행 줄 「PDF 검증 중 — n/3 끝남」(동그라미) · 단계 ③ 끝남 ④ 도는 중", page.get_attribute("#headsDlg", "data-kind") == "styleSave"
              and (page.locator("#headsDlg .sl-vbox[data-state=done]").count() == 1 or re.search(r"PDF 검증 중 — \d/3 끝남", page.inner_text("#headsDlg .sl-vbox")))
              and page.evaluate(STEPS)[2][1] == "done", page.inner_text("#headsDlg .sl-vbox"))
        page.wait_for_selector("#headsDlg .sl-vbox[data-state=done]", timeout=20000)
        vsum = page.inner_text("#headsDlg .sl-vbox")
        check("검증이 끝나면 요약(형식마다 — 옛 서버라 hwpx 만) + 「서식 관리자에서 보기」 · 단계 ④ 끝남", "PDF 검증 끝 — 서식 3개" in vsum and "hwpx — 검증됨 3 · 확인 필요 0 · 실패 0 · 없음 0" in vsum and "docx" not in vsum
              and page.evaluate(STEPS)[3][1] == "done", vsum)
        page.click("#headsDlg [data-sl-act=toLib]")
        page.wait_for_selector("#headsDlg[data-kind=styleLib] .sl-item[data-style=n1]")
        check("「서식 관리자에서 보기」 — 먼저 저장한 서식의 갈래(내용 서식)로 열림 · 수가 늘어남", page.inner_text("#headsDlgTools [data-sl-tab=content]") == "내용 서식 2" and page.get_attribute("#headsDlgTools [data-sl-tab=content]", "aria-pressed") == "true")
        page.click("#headsDlgTools [data-sl-tab=table]")
        its = page.evaluate(ITEMS)
        check("테이블 서식 — 새 서식 둘이 「hwpx 검증됨」 으로 보임", [x["id"] for x in its] == ["s_tbl1", "n2", "n4"] and item(its, "n4")["verify"][0][:2] == ["ok", "hwpx 검증됨"], [x["id"] for x in its])
        opts = page.evaluate("() => [...document.querySelector('#paneAgent select[data-ag-pick=table]').options].map((o) => o.textContent)")
        check("에이전트 입력의 표 서식 고르기에도 새 서식", "수요조사 표" in opts and "항목 합계표" in opts, opts)

        # ---- 6-1. 종류 넷의 후보 · 보이는 줄만 견본 · 검토 상태(② §12·§13·§15) — 후보가 많은 문서(표지 1 · 내용 1 + 쪽 설정 1 · 표 12 · 문단 2)
        RICH["on"] = True
        page.evaluate("() => { STYLE.save = null; }")
        n_prev = len(calls["preview"])
        page.click("#headsDlgTools [data-sl-act=fromDoc]")
        page.wait_for_selector("#headsDlg[data-kind=styleSave] .sl-cand[data-cand=X1] .sp-pic[data-sp-kind=content]")
        KINDS = "() => [...document.querySelectorAll('#headsDlg .sl-cand')].map((b) => b.dataset.kind)"
        tabs, kinds = page.evaluate(CTABS), page.evaluate(KINDS)
        check("후보의 탭 — 표지 서식 1 · 내용 서식 1(처음 탭 — 레벨 있는 글만) · 테이블 서식 12 · 쪽 설정 1(이 열에서는 내용 서식과 따로) · 문단 서식 2 · 보이는 줄은 내용 서식의 것뿐(「템플릿 후보」·「문서 서식 후보」 라는 말은 없다)",
              tabs == [["cover", "표지 서식 1", "false"], ["content", "내용 서식 1", "true"], ["table", "테이블 서식 12", "false"], ["page", "쪽 설정 1", "false"], ["para", "문단 서식 2", "false"]]
              and kinds == ["text"] and one_sec(page, "content") and "템플릿 후보" not in page.inner_text("#headsDlgBody") and "문서 서식 후보" not in page.inner_text("#headsDlgBody"), (tabs, kinds))
        page.wait_for_timeout(500)
        other_tab = lambda b: b.get("kind") in ("cover", "page", "table") or (b.get("kind") == "text" and not b.get("template"))  # 내용 서식 탭의 것이 아닌 견본 요청
        check("견본은 열린 탭의 줄만 받는다 — 다른 탭(표지 · 테이블 · 쪽 설정 · 문단)의 견본은 그 탭을 열기 전에는 안 받음", not any(other_tab(b) for b in calls["preview"][n_prev:]), calls["preview"][n_prev:])
        ctab(page, "table")
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=R1] .sp-pic[data-sp-kind=table]")
        page.wait_for_timeout(500)
        idle = page.evaluate("() => [...document.querySelectorAll('#headsDlg .sl-cand')].map((b) => [b.dataset.cand, b.querySelector('.sl-pic').dataset.picState])")
        seen_n = len(calls["preview"]) - n_prev
        check("테이블 서식 탭 — 표 후보 12개만 · 견본은 보이는 줄만 받는다: 맨 아래 후보(R12)는 아직 안 받음 · 요청 수 < 후보 수 · 다른 탭의 견본은 여전히 안 받음", page.evaluate(KINDS) == ["table"] * 12 and one_sec(page, "table")
              and dict(idle)["R1"] == "done" and dict(idle)["R12"] == "idle" and 1 <= seen_n < 12 and seen_n <= sum(1 for _, st in idle if st != "idle") + 1
              and not any(b.get("kind") in ("cover", "page") or (b.get("kind") == "text" and not b.get("template")) for b in calls["preview"][n_prev:]), (idle, seen_n))  # 같은 열쇠의 견본을 앞 절에서 이미 받았으면 요청 없이 그려진다(기억) — 그린 수(+ 내용 서식 탭의 X1)보다 요청이 많지만 않으면 된다
        page.evaluate("() => { styleSaveDraw(); styleSaveDraw(); }")
        page.wait_for_timeout(400)
        check("목록을 다시 그려도 견본을 다시 받지 않는다(같은 열쇠) — 그림은 그대로 · 탭도 그대로", len(calls["preview"]) - n_prev == seen_n and page.locator("#headsDlg .sl-cand[data-cand=R1] .sp-pic[data-sp-kind=table]").count() == 1
              and page.get_attribute("#headsDlg [data-sl-ctab=table]", "aria-pressed") == "true", len(calls["preview"]) - n_prev)
        ctab(page, "cover")
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=cover] .sp-pic[data-sp-kind=cover]")
        # 서식 관리자로 갔다 돌아와도 고른 탭이 그대로(후보 묶음에 남는다) · 서식 관리자의 갈래 단추는 그대로 넷(탭 다섯은 「서식 복사」 열에만)
        page.click("#headsDlgTools [data-sl-act=toLibTop]")
        page.wait_for_selector("#headsDlg[data-kind=styleLib] [data-sl-tab]")
        lib = page.evaluate("() => [[...document.querySelectorAll('#headsDlg [data-sl-tab]')].map((b) => b.dataset.slTab), document.querySelectorAll('#headsDlg [data-sl-ctab]').length]")
        page.click("#headsDlgTools [data-sl-act=fromDoc]")
        page.wait_for_selector("#headsDlg[data-kind=styleSave] [data-sl-ctab]")
        check("서식 관리자로 갔다 돌아오면 고른 탭(표지 서식)이 그대로 · 서식 관리자의 갈래 단추는 그대로 넷(쪽 설정 갈래 없음 · 탭 다섯은 「서식 복사」 열에만)", lib == [["cover", "content", "table", "para"], 0]
              and [t[2] for t in page.evaluate(CTABS)] == ["true", "false", "false", "false", "false"] and page.evaluate(KINDS) == ["cover"] and one_sec(page, "cover"), (lib, page.evaluate(CTABS)))
        ctab(page, "cover")
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=cover] .sp-pic[data-sp-kind=cover]")
        cv = page.evaluate("""() => { const p = document.querySelector('#headsDlg .sl-cand[data-cand=cover] .sp-pic'); return { parts: [...p.querySelectorAll('.sp-part')].map((e) => [e.dataset.type, e.dataset.role || '', e.dataset.type === 'text' ? e.textContent : e.querySelectorAll('td').length]),
          paper: !!p.querySelector('.sp-paper'), label: p.getAttribute('aria-label'), big: parseFloat(p.querySelector('.sp-part').style.fontSize) > parseFloat(p.querySelectorAll('.sp-part')[1].style.fontSize) }; }""")
        check("표지 서식의 그림 — 쪽 도식 위에 표지의 부분들을 차례로(제목 · 기관명 · 작은 표 · 날짜 — 그 크기·정렬의 역할 견본 글)", cv["parts"] == [["text", "title", "제목"], ["text", "org", "기관명"], ["table", "", 4], ["text", "date", "날짜"]]
              and cv["paper"] and cv["label"] == "표지 — 부분 4개: 제목 · 기관명 · 표 · 날짜" and cv["big"], cv)
        ctab(page, "page")
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=page] .sp-pic[data-sp-kind=page]")
        check("쪽 설정 탭 — 쪽 설정 후보 하나만(내용 서식 탭과 따로) · 설명 줄 「쪽 설정(용지 크기·방향·여백)…」", page.evaluate(KINDS) == ["page"] and one_sec(page, "page"), page.evaluate(CSECS))
        pg = page.evaluate("""() => { const p = document.querySelector('#headsDlg .sl-cand[data-cand=page] .sp-pic'), a = p.querySelector('.sp-paper').getBoundingClientRect(), b = p.querySelector('.sp-body').getBoundingClientRect();
          return { mg: [...p.querySelectorAll('.sp-mg')].map((e) => [e.dataset.side, e.textContent]), name: p.querySelector('.sp-paper-name').textContent, ratio: Math.round(a.height / a.width * 100) / 100,
                   inset: [b.left - a.left, a.right - b.right, b.top - a.top, a.bottom - b.bottom].map((v) => Math.round(v / a.width * 210)), lines: p.querySelectorAll('.sp-bline').length, dashed: getComputedStyle(p.querySelector('.sp-body')).borderTopStyle }; }""")
        check("쪽 설정의 그림 — 쪽 도식: 용지 비율(A4 세로) · 본문 상자(점선 — 여백 값 그대로: 위 = 종이 끝에서 본문까지) · 네 변의 여백 수치 · 바탕 글의 견본 줄 · 「A4 세로」",
              pg["mg"] == [["t", "위 20"], ["l", "왼 30"], ["r", "오 30"], ["b", "아래 15"]] and pg["name"] == "A4 세로" and 1.38 <= pg["ratio"] <= 1.44 and all(abs(x - y) <= 6 for x, y in zip(pg["inset"], [30, 30, 20, 15]))
              and pg["lines"] == 2 and pg["dashed"] == "dashed", pg)
        ctab(page, "table")
        page.locator("#headsDlg .sl-cand[data-cand=R12]").scroll_into_view_if_needed()
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=R12] .sp-pic[data-sp-kind=table]")
        down = page.evaluate("() => document.getElementById('headsDlgBody').scrollTop")
        ctab(page, "para")
        check("탭을 바꾸면 본문은 맨 위로(굴려 둔 자리를 탭마다 기억하지 않는다) · 문단 서식 탭 — 문단 후보만 · 눌림이 옮겨 감", down > 0 and page.evaluate("() => document.getElementById('headsDlgBody').scrollTop") == 0
              and page.evaluate(KINDS) == ["para", "para"] and [t[2] for t in page.evaluate(CTABS)] == ["false", "false", "false", "false", "true"] and one_sec(page, "para"), (down, page.evaluate(CTABS)))
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=P2] .sp-pic[data-sp-kind=para]")
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=P1] .sp-pic[data-sp-kind=para]")
        pr = page.evaluate("""() => { const b = document.querySelector('#headsDlg .sl-cand[data-cand=P2]'), p = b.querySelector('.sp-para'); return { text: p.textContent.slice(0, 12), font: p.style.fontFamily, align: p.style.textAlign, indent: parseFloat(p.style.textIndent) < 0,
          role: b.querySelector('.hb[data-role]').textContent, sel: b.querySelector('select[data-sl-role]').value, opts: [...b.querySelectorAll('select[data-sl-role] option')].map((o) => o.textContent) }; }""")
        check("문단 서식의 그림 — 「가나다 … AaBb … 123」 견본을 그 서식으로(글꼴 이름 그대로 · 정렬 · 내어쓰기) · 역할 꼬리표 + 역할 고르기 · 굴려서 보이게 된 줄은 그때 견본을 받는다",
              pr["text"].startswith("가나다") and "맑은 고딕" in pr["font"] and pr["align"] == "justify" and pr["indent"] and pr["role"] == "기타" and pr["sel"] == "other"
              and pr["opts"] == ["모름", "본문", "캡션", "주석", "상자 글", "목차", "기타"] and {"kind": "table", "table": "t812", "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "keepText": False} in calls["preview"]
              and {"kind": "text", "paras": [IDS["cell_para"]], "role": "other", "keepText": False} in calls["preview"] and page.evaluate(PURE) == 0, (pr, calls["preview"][-4:]))
        unfold(page, "P1")
        page.select_option("#headsDlg .sl-cand[data-cand=P1] select[data-sl-role]", "note")
        page.wait_for_function("() => document.querySelector('#headsDlg .sl-cand[data-cand=P1] .hb[data-role]').textContent === '주석'")
        page.wait_for_timeout(400)
        check("역할을 바꾸면 견본을 다시 받는다(저장 몸의 role)", {"kind": "text", "paras": [IDS["cell_para"]], "role": "note", "keepText": False} in calls["preview"], calls["preview"][-2:])
        size(page, "headsDlg", 320)
        fit = page.evaluate(FIT_COL)
        lines = page.evaluate("() => new Set([...document.querySelectorAll('#headsDlg [data-sl-ctab]')].map((b) => Math.round(b.getBoundingClientRect().top))).size")
        check("서식 복사(탭 · 그림 · 검토 상태) · 2열 320px — 가로 넘침 없음 · 탭은 다음 줄로 접힘 · 그림은 열의 전체 폭", fit["w"] in (319, 320) and not fit["bad"] and not fit["over"] and lines >= 2
              and page.evaluate("() => { const p = document.querySelector('#headsDlg .sl-cand[data-cand=P2] .sl-pic'), w = document.querySelector('#headsDlg .sl-wrap'); return Math.abs(p.getBoundingClientRect().width - (w.clientWidth - 24)) <= 1; }"), (fit, lines))
        page.locator("#headsDlg").screenshot(path=str(OUT / "6_1_copy_pics_320.png"))
        size(page, "headsDlg", 480)
        ctab(page, "content")
        check("검토 전 — 스크립트 자기 점검의 의심은 LLM 없이도 글로(주황 「스크립트 확인 — …」) · 탭 도움말에는 아직 「확인이 필요한 것」 이 없다(LLM 검토 뒤에만)", page.evaluate(REVIEW, "X1") == [["by", "스크립트 후보 — LLM 이 보지 않음", False], ["doubt", "스크립트 확인 — 한 레벨에 서식이 여럿", False]]
              and page.evaluate(CTIPS) == ["후보 1 · 고름 0", "후보 1 · 고름 0", "후보 12 · 고름 0", "후보 1 · 고름 0", "후보 2 · 고름 0"], (page.evaluate(REVIEW, "X1"), page.evaluate(CTIPS)))
        # LLM 검토 — 본 것 · 고친 것(+ 되돌리기) · 의심 · 같은 서식 · 띠 넓히기 제안을 글로. 검토는 모든 탭의 후보에 걸친다(열린 탭 = 내용 서식 — 다른 탭의 줄은 DOM 에 없다)
        page.click("#headsDlgTools [data-sl-act=name]")
        page.wait_for_function("() => document.querySelector('#headsDlg .sl-cand[data-cand=X1] .sl-cname').value === '주 개요 내용 서식'")
        rv = {}
        for tab, keys in (("content", ("X1",)), ("cover", ("cover",)), ("page", ("page",)), ("para", ("P1", "P2")), ("table", ("R1", "R2", "R3", "R4"))):  # 끝에는 테이블 서식 탭
            ctab(page, tab)
            rv.update({k: page.evaluate(REVIEW, k) for k in keys})
        check("LLM 검토 뒤 탭 도움말 — 「후보 N · 고름 n · 확인이 필요한 것 n」(의심·LLM 고침이 있는 후보 수: 내용 1 · 테이블 1 · 쪽 설정 1 · 문단 1 · 표지 0) · 탭 글의 수는 그대로",
              page.evaluate(CTIPS) == ["후보 1 · 고름 0 · 확인이 필요한 것 0", "후보 1 · 고름 0 · 확인이 필요한 것 1", "후보 12 · 고름 0 · 확인이 필요한 것 1", "후보 1 · 고름 0 · 확인이 필요한 것 1", "후보 2 · 고름 0 · 확인이 필요한 것 1"]
              and [t[1] for t in page.evaluate(CTABS)] == ["표지 서식 1", "내용 서식 1", "테이블 서식 12", "쪽 설정 1", "문단 서식 2"], page.evaluate(CTIPS))
        check("검토 상태 — 「LLM 이 봄 — 이름 · 띠 수 · 역할」(체크가 아니라 본 것을 글로) · 의심은 「LLM 확인 — …」·「스크립트 확인 — …」 · 같은 서식 · LLM 이 본 표의 역할 꼬리표",
              rv["R1"] == [["by", "LLM 이 봄 — 이름 · 띠 수 · 역할", False]] and rv["R3"] == [["by", "LLM 이 봄 — 이름 · 띠 수 · 역할", False], ["doubt", "LLM 확인 — 안내문 표로 보임", False]]
              and rv["R4"] == [["by", "LLM 이 봄 — 이름 · 띠 수 · 역할", False], ["same", "「항목 자료표 — 머리 1행」 과 같은 서식으로 보임", False]] and rv["cover"] == [["by", "LLM 이 봄 — 범위 · 역할", False]]
              and page.text_content("#headsDlg .sl-cand[data-cand=R1] .hb[data-role]") == "자료 표" and page.locator("#headsDlg .sl-cand[data-cand=R2] [data-sl-act=wider]").count() == 1, rv)
        ctab(page, "para")
        check("LLM 이 고친 것 — 보라 「LLM 고침 — <무엇>: <전> → <뒤>」 + 「되돌리기」(대표 문단 · 역할 · 바탕 글) · 문단 서식의 역할은 LLM 값으로",
              rv["X1"] == [["by", "LLM 이 봄 — 이름 · 레벨", False], ["fixed", f"LLM 고침 — 대표 문단: p1 → {IDS['cell_para']}", True], ["doubt", "스크립트 확인 — 한 레벨에 서식이 여럿", False]]
              and rv["P2"] == [["by", "LLM 이 봄 — 이름 · 역할", False], ["fixed", "LLM 고침 — 역할: other → caption", True]] and rv["page"] == [["by", "LLM 이 봄 — 바탕 글", False], ["fixed", "LLM 고침 — 바탕 글: b1 → b2", True]]
              and page.input_value("#headsDlg .sl-cand[data-cand=P2] select[data-sl-role]") == "caption" and page.input_value("#headsDlg .sl-cand[data-cand=P1] select[data-sl-role]") == "note"
              and page.evaluate("() => getComputedStyle(document.querySelector('#headsDlg .sl-cand[data-cand=P2] .sl-rv.fix')).color") == "rgb(91, 63, 181)", rv)
        unfold(page, "P2")
        page.click("#headsDlg .sl-cand[data-cand=P2] [data-sl-act=unfix]")
        rv2 = {"P2": page.evaluate(REVIEW, "P2")}
        p2_role = page.input_value("#headsDlg .sl-cand[data-cand=P2] select[data-sl-role]")
        ctab(page, "content")
        unfold(page, "X1")
        page.click("#headsDlg .sl-cand[data-cand=X1] [data-sl-act=unfix]")
        rv2["X1"] = page.evaluate(REVIEW, "X1")
        ctab(page, "page")
        check("「되돌리기」 — 그 고침만 스크립트 값으로(고침 줄이 「되돌림 — …」 으로 · 역할은 스크립트 값) · 다른 줄의 고침은 그대로 · 되돌린 탭(문단 서식)의 「확인이 필요한 것」 이 준다", rv2["P2"] == [["by", "LLM 이 봄 — 이름 · 역할", False], ["undone", "되돌림 — 역할: 스크립트 값(other)으로 저장합니다", False]]
              and ["undone", "되돌림 — 대표 문단: 스크립트 값(p1)으로 저장합니다", False] in rv2["X1"] and p2_role == "other"
              and page.evaluate(REVIEW, "page")[1][2] is True and page.evaluate(CTIPS)[4] == "후보 2 · 고름 0 · 확인이 필요한 것 0" and page.evaluate(CTIPS)[1].endswith("확인이 필요한 것 1"), (rv2, page.evaluate(CTIPS)))
        for tab, key in (("cover", "cover"), ("content", "X1"), ("page", "page"), ("para", "P2")):  # 탭마다 하나씩 고른다 — 끝에는 문단 서식 탭
            ctab(page, tab)
            page.check(f"#headsDlg .sl-cand[data-cand={key}] .sl-crow > input[type=checkbox]")
        check("네 탭에서 하나씩 고름 — 탭마다 「· 1개 고름」(안 고른 테이블 서식 탭은 수만) · 저장 단추는 모든 탭을 합친 「고른 4개 저장」",
              [t[1] for t in page.evaluate(CTABS)] == ["표지 서식 1 · 1개 고름", "내용 서식 1 · 1개 고름", "테이블 서식 12", "쪽 설정 1 · 1개 고름", "문단 서식 2 · 1개 고름"]
              and page.inner_text("#headsDlgFoot [data-sl-act=save]") == "고른 4개 저장", page.evaluate(CTABS))
        n_save = len(calls["save"])
        page.click("#headsDlgFoot [data-sl-act=save]")  # 저장은 모든 탭의 고른 것(열린 탭은 문단 서식 — 다른 탭의 줄은 DOM 에 없어도 저장된다)
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=P2].done")
        sv = calls["save"][n_save:]
        check("저장 몸 — LLM 이 고른 값은 되돌리지 않았을 때만 싣는다: 표지 = {kind: cover, end, roles} · 내용 서식 = rep 없음(되돌림) · 쪽 설정 = {kind: page, bodyKey: b2} · 문단 서식 = {kind: text, paras: [대표 문단], role: 스크립트 값}",
              sv == [{"kind": "cover", "end": IDS["other"], "roles": {IDS["other"]: "title"}, "keepText": False, "name": "계획서 표지"}, {"kind": "text", "template": "tpl1", "keepText": False, "name": "주 개요 내용 서식"},
                     {"kind": "page", "bodyKey": "b2", "name": "계획서 쪽 설정"}, {"kind": "text", "paras": [IDS["cell_para"]], "role": "other", "keepText": False, "name": "캡션 서식"}], sv)
        page.wait_for_selector("#headsDlg .sl-vbox[data-state=done]", timeout=20000)
        # 옛 서버(견본 끝점 없음 — 404) — 그림 자리에 한 줄 · 목록은 그대로 · 「다시」
        L["preview"] = "missing"
        page.check("#headsDlg [data-sl-opt=keepText] input")  # 저장 몸이 바뀐다 → 보이는 줄의 견본을 다시 받는다
        ctab(page, "table")
        page.locator("#headsDlg .sl-cand[data-cand=R1]").scroll_into_view_if_needed()
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=R1] .sl-pic[data-pic-state=err]")
        old = page.inner_text("#headsDlg .sl-cand[data-cand=R1] .sl-pic")
        L["preview"] = None
        page.click("#headsDlg .sl-cand[data-cand=R1] [data-sl-act=picRetry]")
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=R1] .sp-pic[data-sp-kind=table]")
        check("견본 끝점이 없는 옛 서버(404) — 그림 자리에 「서버를 다시 켜야 그림이 보입니다」 한 줄(후보 줄·이름·띠 수는 그대로) · 「다시」 로 다시 받음", "서버를 다시 켜야 그림이 보입니다" in old
              and page.locator("#headsDlg .sl-cand").count() == 12 and [t[1] for t in page.evaluate(CTABS)] == ["표지 서식 1", "내용 서식 1", "테이블 서식 12", "쪽 설정 1", "문단 서식 2"] and calls["preview"][-1].get("keepText") is True, old)  # 열린 탭(테이블 서식)의 줄 12 · 탭의 후보 수는 그대로(모두 17)
        page.screenshot(path=str(OUT / "6_1_copy_review.png"))
        RICH["on"] = False
        page.evaluate("() => { STYLE.save = null; }")

        # ---- 7. 표 메뉴 「서식 보관함에 저장…」 — 그 표만 고른 채로
        def menu_save(tid, para):
            page.click(f'#doc .para[data-id="{para}"]')
            page.wait_for_function("(t) => tmn.active === t && tmnShown()", arg=tid)
            page.click(".tbl-corner")
            page.wait_for_selector(".ctx-menu:not([hidden])")
            page.click(".ctx-menu button:has-text('서식 관리자에 저장…')")
            page.wait_for_selector("#headsDlg[data-kind=styleSave] .sl-cand")
            return page.evaluate(ROWS)

        rows = menu_save(IDS["table"], IDS["cell_para"])
        tabs = page.evaluate(CTABS)
        check("표 메뉴 「서식 관리자에 저장…」 — 후보 열이 그 표만 고른 채로(나머지는 풀림) · 고른 채로 연 후보의 탭(테이블 서식)이 열려 그 줄이 보인다(처음 탭 규칙의 내용 서식이 아니라)", [(r["key"], r["on"]) for r in rows if r["on"]] == [("T1", True)]
              and page.inner_text("#headsDlgFoot [data-sl-act=save]") == "고른 1개 저장" and [t[0] for t in tabs if t[2] == "true"] == ["table"] and all(r["kind"] == "table" for r in rows)
              and [t[0] for t in tabs if "고름" in t[1]] == ["table"] and tabs[2][1].endswith(" · 1개 고름"), (rows, tabs))
        other_para = next(p for p in map(first_para, other.get("cells") or []) if p)
        rows = menu_save(IDS["other"], other_para)
        tb = [r for r in rows if r["kind"] == "table"]
        check("후보에 없는 표 — 그 표로 줄을 하나 만들어 테이블 서식 후보의 맨 앞에 고른 채로(띠 수는 비워 자동 판정)", tb[0]["key"] == f"pick:{IDS['other']}" and tb[0]["on"] and tb[0]["bands"] == ["", "", ""] and [r["on"] for r in rows if r is not tb[0]] == [False] * (len(rows) - 1), rows[:3])
        n_save = len(calls["save"])
        page.click("#headsDlgFoot [data-sl-act=save]")
        page.wait_for_selector("#headsDlg .sl-cand.done")
        check("그 표 저장 — 몸에 그 표 id · 띠 수는 안 보냄(서버가 판정)", len(calls["save"]) == n_save + 1 and calls["save"][-1]["table"] == IDS["other"] and "bands" not in calls["save"][-1], calls["save"][-1])
        page.wait_for_selector("#headsDlg .sl-vbox[data-state=done]", timeout=20000)

        # ---- 8. 「파일에서 복사」 → 후보 → from-file / 410
        page.click("#headsDlgTools [data-sl-act=toLibTop]")  # 「‹ 서식 관리자」 — 보관한 서식 목록으로
        page.wait_for_selector("#headsDlg[data-kind=styleLib] .sl-item")
        with page.expect_file_chooser() as fc:
            page.click("#headsDlgTools [data-sl-act=fromFile]")
        check("「파일에서 복사」 — 파일 고르기(hwp·hwpx·docx·pdf)", fc.value.element.evaluate("(e) => e.accept") == ".hwp,.hwpx,.docx,.pdf")
        fc.value.set_files(str(ROOT / "samples" / "기술수요조사서.docx"))
        page.wait_for_selector("#headsDlg[data-kind=styleSave] .sl-cand[data-cand=F1]")
        rows = page.evaluate(ROWS)
        tabs = page.evaluate(CTABS)
        ctab(page, "content")
        none = page.locator("#headsDlg .sl-wrap > .hnote").all_inner_texts()
        ctab(page, "table")
        check("파일 후보의 탭 — 내용 서식 후보가 없으면 처음 탭 = 처음으로 후보가 있는 탭(표지 → 테이블 → 쪽 설정 → 문단 차례 — 여기서는 테이블 서식) · 0개인 내용 서식 탭은 「이 파일에서 내용 서식 후보를 찾지 못했습니다」",
              tabs == [["cover", "표지 서식 0", "false"], ["content", "내용 서식 0", "false"], ["table", "테이블 서식 1", "true"], ["page", "쪽 설정 0", "false"], ["para", "문단 서식 0", "false"]]
              and none == ["이 파일에서 내용 서식 후보를 찾지 못했습니다."] and [r["key"] for r in page.evaluate(ROWS)] == ["F1"], (tabs, none))
        check("파일 후보 — 올린 것은 multipart · 제목에 파일 이름 · 옮기지 못하는 것 알림 · 「자리로」·「구조까지」 없음 · 「에이전트 추출」 은 파일에도", "multipart/form-data" in calls["extract"][0] and "공고문.pdf" in page.inner_text("#headsDlgTitle")
              and "재지 못함" in page.inner_text("#headsDlgBody") and rows[0]["go"] is False and rows[0]["bp"] is None and page.locator("#headsDlgTools [data-sl-act=name]").count() == 1 and "3쪽" in rows[0]["meta"]
              and page.locator("#headsDlg [data-sl-opt=keepText]").count() == 0, rows)
        page.check("#headsDlg .sl-cand[data-cand=F1] .sl-crow > input[type=checkbox]")
        L["gone"] = True
        page.click("#headsDlgFoot [data-sl-act=save]")
        page.wait_for_selector("#headsDlg .sl-msg.err")
        check("410 — 「다시 올리세요」 한 줄(열은 그대로)", "다시 올리세요" in page.inner_text("#headsDlg .sl-wrap > .sl-msg.err") and page.get_attribute("#headsDlg", "data-kind") == "styleSave")
        L["gone"] = False
        page.click("#headsDlgFoot [data-sl-act=save]")
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=F1].done")
        check("저장 — POST /api/styles/from-file 몸 = {token, picks: [{kind, key, name, bands}]}(파일·명세는 안 보냄)",
              calls["from_file"][-1] == {"token": "tok1", "picks": [{"kind": "table", "key": "F1", "name": "일정 표", "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}}]}, calls["from_file"][-1])
        page.wait_for_selector("#headsDlg .sl-vbox[data-state=done]", timeout=20000)

        # ---- 8-1. 두 형식을 아는 서버(spec_서식복사 ② §7·§8 — 목록에 pdfDocx) — docx 꼬리표 · 견본 그림의 형식 전환 · 「docx 받기」 · 문서 서식 줄 · 「이 문서에 입히기」
        L["dual"] = True
        find("s_tbl1").update(docx=True, verify={"status": "ok", "coverage": COVER, "stale": False}, verifyDocx={"status": "warn", "coverage": COVER, "stale": False})
        find("s_txt1").update(docx=False, verifyDocx=None)
        L["styles"].append({"id": "s_pg1", "revision": "r1", "kind": "page", "name": "계획서 문서 서식", "note": "", "created": now, "updated": now, "source": {"name": SMALL, "format": "hwpx", "page": None}, "fidelity": "native", "losses": 0,
                            "requirements": {"fonts": []}, "docx": True, "verify": {"status": "ok", "coverage": COVER, "stale": False}, "verifyDocx": {"status": "none", "coverage": None, "stale": False},
                            "page": {"widthMm": 210, "heightMm": 297, "landscape": False, "marginsMm": {"l": 30, "r": 30, "t": 20, "b": 15, "header": 15, "footer": 15, "gutter": 0}}, "body": {"format": {"font": "함초롬바탕", "sizePt": 11}, "count": 40}})
        page.click("#headsDlgTools [data-sl-act=toLibTop]")
        page.wait_for_selector("#headsDlg[data-kind=styleLib] .sl-verify[data-format=docx]")
        page.click("#headsDlgTools [data-sl-tab=table]")
        t1 = item(page.evaluate(ITEMS), "s_tbl1")
        fm = page.evaluate("() => [...document.querySelectorAll('#headsDlg .sl-item[data-style=s_tbl1] .sl-verify')].map((e) => [e.dataset.format, e.textContent])")
        manage(page, "s_tbl1")
        t1 = item(page.evaluate(ITEMS), "s_tbl1")
        check("형식마다 검증 꼬리표 — 「hwpx 검증됨」 · 「docx 확인 필요」 · 「docx 받기」 가 생김(「⋯ 더보기」 아래) · 원천에 「Word 출력」 이 생김", fm == [["hwpx", "hwpx 검증됨"], ["docx", "docx 확인 필요"]]
              and ["getDocx", False] in t1["manage"] and ["getHwpx", False] in t1["manage"] and [s[:3] for s in t1["srcs"]] == [["web", "웹 견본", False], ["hwpx", "한글 출력", False], ["docx", "Word 출력", False]], (fm, t1))
        page.click("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-src=docx]")
        src = page.get_attribute("#headsDlg .sl-item[data-style=s_tbl1] img.sl-proof", "src")
        check("원천 「Word 출력」 — 그 형식의 PDF 검증 그림(주소에 format=docx)", "/proof.png?format=docx&v=" in src and page.get_attribute("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-src=docx]", "aria-pressed") == "true", src)
        with page.expect_download() as dl:
            page.click("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=getDocx]")
        check("「docx 받기」 — GET …/carrier?format=docx 를 내려받음(파일 이름 = 서식 이름.docx)", calls.get("carrier") == ["/api/styles/s_tbl1/carrier?format=docx"] and dl.value.suggested_filename.endswith(".docx"), (calls.get("carrier"), dl.value.suggested_filename))
        page.click("#headsDlgTools [data-sl-tab=content]")
        fm = page.evaluate("() => [...document.querySelectorAll('#headsDlg .sl-item[data-style=s_txt1] .sl-verify')].map((e) => [e.dataset.format, e.dataset.status, e.textContent])")
        check("docx 서식이 없는 내용 서식 — 「docx 없음」(글로)", fm == [["hwpx", "pending", "hwpx 검증 전"], ["docx", "nodocx", "docx 없음"]], fm)
        page.locator("#headsDlg .sl-item[data-style=s_pg1]").scroll_into_view_if_needed()
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_pg1] .sp-pic[data-sp-kind=page]")
        pg = item(page.evaluate(ITEMS), "s_pg1")
        line = page.inner_text("#headsDlg .sl-item[data-style=s_pg1] .sl-page")
        sec = page.evaluate("() => { const h = document.querySelector('#headsDlg [data-sl-sec=page]'), it = document.querySelector('#headsDlg .sl-item[data-style=s_pg1]'); return [h.textContent.replace(/\\d+$/, 'n'), !!(h.compareDocumentPosition(it) & 4), document.querySelectorAll('#headsDlgTools [data-sl-tab=page]').length]; }")
        check("쪽 설정(전의 문서 서식) — 내용 서식 갈래 안의 한 구역 「쪽 설정 n」 · 쪽 도식 그림 · 요약 한 줄 「A4 세로 · 여백 … · 본문 …」 · 「쪽 설정 입히기」 · 형식마다 꼬리표(docx PDF 없음)", line == "A4 세로 · 여백 왼 30 · 오 30 · 위 20 · 아래 15mm · 본문 함초롬바탕 11pt"
              and sec == ["쪽 설정 n", True, 0] and pg["tab"] == "content" and pg["pic"][1] == "page" and pg["acts"] == [["page", False], ["more", False]] and page.inner_text("#headsDlg .sl-item[data-style=s_pg1] [data-sl-act=page]") == "쪽 설정 입히기"
              and [v[1] for v in pg["verify"]] == ["hwpx 검증됨", "docx PDF 없음"] and [s[2] for s in pg["srcs"]] == [False, False, True], (line, sec, pg))
        # 출력 그림을 못 읽으면 숨기지 않고 웹 견본 + 「출력 그림을 읽지 못했습니다 — 다시」 · 쪽 설정의 출력 그림은 첫 쪽 전체(&full=1)
        L["proof"] = "bad"
        page.click("#headsDlg .sl-item[data-style=s_pg1] [data-sl-src=hwpx]")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_pg1] [data-pic-msg=proof]")
        bad = item(page.evaluate(ITEMS), "s_pg1")
        L["proof"] = None
        page.click("#headsDlg .sl-item[data-style=s_pg1] [data-sl-act=proofRetry]")
        page.wait_for_function("() => { const i = document.querySelector('#headsDlg .sl-item[data-style=s_pg1] img.sl-proof'); return !!i && i.complete && i.naturalWidth > 0; }")
        good = item(page.evaluate(ITEMS), "s_pg1")
        check("출력 그림을 못 읽으면 — 웹 견본(쪽 도식) + 「출력 그림을 읽지 못했습니다」 + 「다시」 · 다시 읽으면 출력 그림(쪽 설정은 첫 쪽 전체 — 주소에 full=1)", "출력 그림을 읽지 못했습니다" in bad["msg"] and bad["pic"][:2] == ["web", "page"] and bad["img"] is None
              and good["img"][1] == "/api/styles/s_pg1/proof.png?format=hwpx&full=1&v=r1" and good["pic"][0] == "hwpx" and "출력 그림을 읽지 못했습니다" not in good["msg"], (bad, good))
        page.click("#headsDlg .sl-item[data-style=s_pg1] [data-sl-src=web]")
        n_apply = len(calls["apply"])
        page.click("#headsDlg .sl-item[data-style=s_pg1] [data-sl-act=page]")
        page.wait_for_function("() => document.getElementById('toast').textContent.includes('쪽 설정을 이 문서에 입혔습니다')")
        check("「쪽 설정 입히기」(전의 「이 문서에 입히기」) — 몸 = {mode: page} · 응답의 paged 로 문서를 통째로 다시 읽음(알림에 구역 수)", calls["apply"][n_apply:] == [{"sid": "s_pg1", "mode": "page"}] and "구역 1개" in page.inner_text("#toast"), calls["apply"][n_apply:])
        page.wait_for_function("() => !state.busy && document.querySelector('#doc .sheet .para') != null")
        # 표지 서식 · 문단 서식 갈래(6-1절에서 저장한 것) — 그림 · 「표지 넣기」 · 역할 꼬리표
        page.click("#headsDlgTools [data-sl-tab=cover]")
        page.wait_for_selector("#headsDlg .sl-item[data-kind=cover] .sp-pic[data-sp-kind=cover]")
        cv = page.evaluate(ITEMS)[0]
        n_apply = len(calls["apply"])
        page.click("#headsDlg .sl-item[data-kind=cover] [data-sl-act=cover]")
        page.wait_for_function("() => document.getElementById('toast').textContent.includes('표지를 문서 맨 앞에 넣었습니다')")
        check("표지 서식 갈래 — 표지 그림(부분 넷) · 「표지 넣기」 = 몸 {mode: cover} → 응답의 covered 로 문서를 다시 읽음(알림에 블록 수)", cv["name"] == "계획서 표지" and cv["tab"] == "cover" and cv["pic"][1] == "cover" and cv["acts"] == [["cover", False], ["more", False]]
              and calls["apply"][n_apply:] == [{"sid": cv["id"], "mode": "cover"}] and "블록 4개" in page.inner_text("#toast"), (cv, calls["apply"][n_apply:]))
        page.wait_for_function("() => !state.busy && document.querySelector('#doc .sheet .para') != null")
        page.click("#headsDlgTools [data-sl-tab=para]")
        page.wait_for_selector("#headsDlg .sl-item[data-tab=para] .sp-pic[data-sp-kind=para]")
        pa = page.evaluate(ITEMS)[0]
        check("문단 서식 갈래 — 레벨 없는 글 서식 · 견본 두 줄 그림 · 역할 꼬리표(글로) · 「글자·문단 모양 입히기」", pa["name"] == "캡션 서식" and pa["tab"] == "para" and "기타" in pa["tags"] and pa["levels"] == ["문단"]
              and page.locator("#headsDlg .sl-item[data-tab=para] .sl-levels [data-sl-item]").all_inner_texts() == ["글자·문단 모양 입히기"], pa)
        page.click("#headsDlgTools [data-sl-tab=table]")  # 아래 9절은 테이블 서식 목록에서 본다
        L["dual"] = False

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

"""TASK 「문서 서식 복사」(spec_서식복사 ② §1~§3 — app/static/task_catalog.js · app.js taskEnter · style_lib.js) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

보관함 끝점(`/api/styles…` · `/api/docs/{id}/styles…`)은 **흉내**다(page.route — 정규식: 글롭 `styles**` 은 아래 경로를 안 잡는다). 문서·작업·TASK 저장은 진짜 서버.
- 시작 화면: 카드 일곱 장 · 「문서 서식 복사」 카드(받는 형식 hwp·hwpx·docx·pdf).
- PDF 를 올리면 작업을 만들지 않고 시작 화면 옆 2열에 「서식 복사」(탭 「테이블 서식」·「쪽 설정」 에 후보) — 「이 문서에서 복사」·적용 단추는 꺼짐 · 닫으면 시작 화면 그대로.
- hwpx 를 올리면 작업이 열리고(TASK = style_copy · 일반 문서) 패널 = 에이전트, 2열 = 「서식 복사」 · 후보의 탭 다섯(표지 서식 · 내용 서식 · 테이블 서식 · 쪽 설정 · 문단 서식 — spec_서식복사 ② §18: 한 번에 한 탭의 후보만 보인다) ·
  「한 번에 진행」(LLM 검토 → 추천 저장 → 검증 기다림 — 모든 탭의 후보에 걸친다) · LLM 없음이면 ② 에서 멈춤.
- 도구 줄 「서식」 묶음(다섯째 · 아이콘 단추 넷 — 넷째 「템플릿 관계」 · 눌림 = 서식 관리자 열림 · 기억한 묶음을 되살릴 때는 안 엶) · 다시 열기 · docx 문서(패널 = 검증 · 옵션 없음 · 켜지는 동작).

    python -X utf8 tools/smoke_style_copy_ui.py <출력 폴더> [--port 18412]
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
ap.add_argument("--port", type=int, default=18412)
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
SMALL, DOCX = "기술수요조사서.hwpx", "기술수요조사서.docx"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:500] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def js(route, body, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body, ensure_ascii=False))


# ---- 흉내 보관함 — 두 형식을 아는 서버(목록에 pdfDocx) ----
now = time.time()
OK = {"status": "ok", "coverage": None, "stale": False}
RUN = {"status": "running", "coverage": None, "stale": False}
PAGE = {"widthMm": 210, "heightMm": 297, "landscape": False, "marginsMm": {"l": 25, "r": 25, "t": 20, "b": 20, "header": 0, "footer": 0, "gutter": 0}}
PSUM = "A4 세로 · 여백 왼 25 · 오 25 · 위 20 · 아래 20mm · 본문 맑은 고딕 10pt"
L = {"llm": "ok", "styles": [
    {"id": "s_tbl1", "revision": "r1", "kind": "table", "name": "예산 총괄표", "created": now, "updated": now, "source": {"name": "양식.hwpx", "format": "hwpx"}, "fidelity": "native", "losses": 0, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0},
     "rows": 4, "cols": 3, "blueprint": True, "docx": True, "verify": OK, "verifyDocx": OK},
    {"id": "s_pg1", "revision": "r1", "kind": "page", "name": "양식 문서 서식", "created": now, "updated": now, "source": {"name": "양식.hwpx", "format": "hwpx"}, "fidelity": "native", "losses": 0, "docx": True, "verify": OK, "verifyDocx": OK,
     "page": PAGE, "body": {"format": {"font": "맑은 고딕", "sizePt": 10}, "count": 9}}]}
calls = {"cands": [], "save": [], "extract": 0, "from_file": [], "poll": {}, "preview": [], "preview_file": []}
BODY = {"format": {"font": "맑은 고딕", "sizePt": 10}, "count": 30}


# 서식 그림(spec_서식복사 ② §13)의 견본 값 — 형식 중립(표 명세 · 항목의 서식 요약 · 쪽 설정)
def spec(rows, cols, bands):
    line, head = {"type": "SOLID", "widthMm": 0.12, "color": "#000000"}, bands.get("headerRows") or 0
    return {"rows": rows, "cols": cols, "bands": bands, "widthsMm": [25] * cols,
            "cells": [{"row": r, "col": c, "rowSpan": 1, "colSpan": 1, "text": "구분" if r < head else "0", "fill": "#DDDDDD" if r < head else None, "valign": "CENTER", "edges": {k: line for k in "trbl"},
                       "format": {"font": "맑은 고딕", "sizePt": 10, "bold": r < head, "align": "center"}} for r in range(rows) for c in range(cols)]}


def view_of(kind, bands=None, leveled=True):
    if kind == "table":
        return {"spec": spec(4, 3, bands or {"headerRows": 1, "headerCols": 0, "footRows": 0})}
    if kind == "page":
        return {"page": PAGE, "body": BODY, "summary": PSUM}
    lv = [{"key": "i1", "name": "1. 줄", "level": 1, "marker": {"mode": "literal", "literal": "1."}, "sample": "견본 글입니다", "format": {"font": "맑은 고딕", "sizePt": 12, "bold": True}},
          {"key": "i2", "name": "가. 줄", "level": 2, "marker": {"mode": "literal", "literal": "가."}, "sample": "견본 글입니다", "format": {"font": "맑은 고딕", "sizePt": 10, "indentLeftMm": 5}}]
    return {"items": lv if leveled else [{"key": "i1", "name": "본문", "level": None, "marker": {"mode": "none"}, "sample": "견본 글입니다", "format": {"font": "맑은 고딕", "sizePt": 10}}]}
ST = re.compile(r"/api/styles(?:/([^/?]+))?(?:/([^/?]+))?(\?.*)?$")
DOC = re.compile(r"/api/docs/[0-9a-f]{12}/styles(?:/([^/?]+))?(?:/([^/?]+))?(\?.*)?$")
CANDS = {"table": "t1", "para": "p1"}


def new_style(kind, name, n):
    s = {"id": f"n{n}", "revision": "r1", "kind": kind, "name": name or "이름 없음", "created": now, "updated": now, "source": {"name": SMALL, "format": "hwpx"}, "fidelity": "native", "losses": 0, "docx": True, "verify": dict(RUN), "verifyDocx": None}
    L["styles"].append(s)
    return s


def styles(route):
    req = route.request
    sid, tail = ST.search(req.url).group(1), ST.search(req.url).group(2)
    if not sid:
        return js(route, {"enabled": True, "pdf": True, "pdfDocx": True, "styles": L["styles"], "broken": []})
    if sid == "extract-file":
        calls["extract"] += 1
        return js(route, {"token": "tok1", "name": "공고문.pdf", "format": "pdf", "fidelity": "approx", "losses": ["여백은 글이 놓인 자리로 어림했습니다"], "texts": [],
                          "pages": [{"key": "page", "page": PAGE, "body": {"format": {"font": "맑은 고딕", "sizePt": 10}, "count": 30}, "sample": PSUM}],
                          "tables": [{"key": "F1", "table": "pdf-1", "same": ["pdf-1"], "count": 1, "rows": 4, "cols": 3, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "sample": "일정", "page": 2}]})
    if sid == "preview-file":  # 파일 후보의 견본({token, pick: {kind, key, bands?}})
        body = json.loads(req.post_data)
        calls["preview_file"].append(body)
        return js(route, {"rev": None, "kind": body["pick"]["kind"], "view": view_of(body["pick"]["kind"], body["pick"].get("bands")), "losses": [], "fidelity": "approx"})
    if sid == "from-file":
        body = json.loads(req.post_data)
        calls["from_file"].append(body)
        return js(route, {"styles": [new_style(p["kind"], p.get("name"), 100 + i) for i, p in enumerate(body["picks"])]})
    s = next((x for x in L["styles"] if x["id"] == sid), None)
    if not s:
        return js(route, {"detail": "없는 서식입니다"}, 404)
    n = calls["poll"][sid] = calls["poll"].get(sid, 0) + 1
    if n >= 2 and s["verify"]["status"] == "running":  # 둘째 읽기에서 두 형식의 검증이 끝난다(hwpx → docx)
        s["verify"], s["verifyDocx"] = dict(OK), dict(OK)
    return js(route, {**s, "docx": {"sha256": "x", "losses": []}, "losses": [], "view": view_of(s["kind"], s.get("bands"), s.get("leveled", True))})


def doc_styles(route):
    req = route.request
    a = DOC.search(req.url).group(1)
    body = json.loads(req.post_data or "{}")
    if a == "preview":  # 후보의 견본 — 몸 = 저장과 같은 꼴(이름·구조까지 없음)
        calls["preview"].append(body)
        return js(route, {"rev": 0, "kind": body.get("kind"), "view": view_of(body.get("kind"), body.get("bands"), bool(body.get("template"))), "losses": [], "fidelity": "native"})
    if a == "candidates":
        calls["cands"].append(body)
        if body.get("llm") and L["llm"] == "off":
            return js(route, {"detail": "LLM 을 쓸 수 없습니다"}, 503)
        docx = CANDS.get("format") == "docx"
        out = {"rev": 0, "stage2": True, "format": "docx" if docx else "hwpx", "fidelity": "summary" if docx else "native",
               "pages": [{"key": "page", "page": PAGE, "body": {"format": {"font": "맑은 고딕", "sizePt": 10}, "count": 30}, "sample": PSUM}],
               "tables": [{"key": "T1", "table": CANDS["table"], "same": [CANDS["table"]], "count": 1, "rows": 18, "cols": 11, "bands": {"headerRows": 1, "headerCols": 1, "footRows": 0}, "sample": "구분"},
                          {"key": "T2", "table": "t900", "same": ["t900"], "count": 1, "rows": 3, "cols": 4, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "sample": "서명"}],
               "texts": [{"key": "X1", "paras": [CANDS["para"]], "count": 12, "items": [{"para": CANDS["para"], "level": None, "letter": "", "sample": "본문", "format": {}}]} if docx else
                         {"key": "X1", "template": {"id": "tpl1", "no": 1, "name": "주 사슬", "chain": ["1.", "가."]}, "items": [{"para": CANDS["para"], "level": 1, "letter": "1.", "sample": "개요", "format": {}}]}]}
        if not docx:  # hwpx 문서 — 확인이 필요한 후보 둘(② §15): 의심이 붙은 표 T3 · LLM 이 역할을 고친 문단 서식 P1
            out["tables"].append({"key": "T3", "table": "t901", "same": ["t901"], "count": 1, "rows": 5, "cols": 4, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "sample": "안내"})
            out["paras"] = [{"key": "P1", "role": "other", "count": 6, "where": {}, "items": [{"para": CANDS["para"], "level": None, "sample": "한글 6자", "format": {"font": "맑은 고딕", "sizePt": 9}, "marker": {}}]}]
        if body.get("llm"):
            seen = lambda *xs, fixed=(), doubts=(): {"by": "llm", "seen": list(xs), "fixed": list(fixed), "doubts": list(doubts)}
            out["tables"][0].update(name="수요조사 양식표 — 머리 1행·머리열", keep=True, review=seen("이름", "띠 수", "역할"))
            out["tables"][1].update(name="서명 칸", keep=False, review=seen("이름", "띠 수", "역할"))
            out["texts"][0].update(name="주 개요 템플릿", keep=True, review=seen("이름", "레벨"))
            out["pages"][0].update(keep=True, review=seen("바탕 글"))
            if not docx:
                out["tables"][2].update(name="안내 표", keep=True, review=seen("이름", "띠 수", "역할", doubts=[{"code": "guideText", "text": "안내문 표로 보임", "by": "llm"}]))
                out["paras"][0].update(name="캡션 서식", keep=True, role="caption", review=seen("이름", "역할", fixed=[{"what": "역할", "from": "other", "to": "caption"}]))
            out["call"] = {"model": "claude-fable-5-2", "ms": 3000, "costUsd": 0.01}
        return js(route, out)
    if a is None:
        calls["save"].append(body)
        return js(route, new_style(body["kind"], body.get("name"), len(calls["save"])), 201)
    return js(route, {"detail": "흉내에 없는 끝점"}, 500)


VIS = "(id) => { const e = document.getElementById(id); return !!e && !e.hidden && e.getClientRects().length > 0; }"
SECS = "() => [...document.querySelectorAll('#headsDlg [data-sl-sec]')].map((e) => e.dataset.slSec)"  # 탭 아래 설명 줄 — 열린 탭의 것 하나(전의 구역 제목은 없다: spec_서식복사 ② §18)
CTABS = "() => [...document.querySelectorAll('#headsDlg [data-sl-ctab]')].map((b) => b.textContent)"  # 탭 다섯의 글 「<이름> <후보 수>( · <n>개 고름)」
CTAB_ON = "() => [...document.querySelectorAll('#headsDlg [data-sl-ctab][aria-pressed=\"true\"]')].map((b) => b.dataset.slCtab)"  # 열린 탭
CTIPS = "() => [...document.querySelectorAll('#headsDlg [data-sl-ctab]')].map((b) => b.title.split('\\n').pop())"  # 탭 도움말의 끝 줄 「후보 N · 고름 n( · 확인이 필요한 것 n)」
KINDS = "() => [...document.querySelectorAll('#headsDlg .sl-cand')].map((b) => b.dataset.kind)"  # 보이는 후보 줄(열린 탭의 것만 DOM 에 있다)
STEPS = "() => [...document.querySelectorAll('#headsDlg .sl-steps .sl-step')].map((e) => e.dataset.state)"
ACTS = "(sid) => Object.fromEntries([...document.querySelectorAll(`#headsDlg .sl-item[data-style=\"${sid}\"] [data-sl-act]`)].map((b) => [b.dataset.slAct, b.disabled]))"
works = lambda: requests.get(f"{base}/api/works", timeout=30).json()


def more(page, sid):  # 관리 단추(받기 · 이름 바꾸기 · 다시 검증 · 지우기)는 「⋯ 더보기」 아래 — 접혀 있으면 편다
    if page.locator(f"#headsDlg .sl-item[data-style={sid}] .sl-manage").count() == 0:
        page.click(f"#headsDlg .sl-item[data-style={sid}] [data-sl-act=more]")
        page.wait_for_selector(f"#headsDlg .sl-item[data-style={sid}] .sl-manage")


def ctab(page, key):  # 「서식 복사」 열의 탭을 누른다 — 눌림이 옮겨 갈 때까지(그 탭의 후보만 DOM 에 있다)
    page.click(f"#headsDlg [data-sl-ctab={key}]")
    page.wait_for_selector(f'#headsDlg [data-sl-ctab={key}][aria-pressed="true"]')


def card_pick(page, files):
    with page.expect_file_chooser() as fc:
        page.locator("#taskCards [data-task=style_copy]").click()
    acc = fc.value.element.evaluate("(e) => e.accept")
    fc.value.set_files(files)
    return acc


try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.route(ST, styles)
        page.route(DOC, doc_styles)
        page.goto(base)
        page.evaluate("() => { try { localStorage.clear(); } catch {} }")
        page.reload()
        page.wait_for_selector("#taskCards [data-task=style_copy]")

        # ---- 1. 시작 화면 — 카드 일곱 장 · 「문서 서식 복사」 카드
        c = page.evaluate("""() => { const all = [...document.querySelectorAll('#taskCards .task-card')], b = document.querySelector('#taskCards [data-task=style_copy]');
            return { keys: all.map((x) => x.dataset.task), tops: new Set(all.map((x) => Math.round(x.getBoundingClientRect().top))).size, doc: b.querySelector('.task-card-doc').textContent, name: b.querySelector('.task-card-name').textContent,
                     go: b.querySelector('.task-card-go').textContent.trim(), title: b.title, tone: b.querySelector('.task-logo').dataset.doc, sym: !!document.querySelector('#taskIcon-style_copy'),
                     fit: document.getElementById('empty').scrollWidth <= document.getElementById('empty').clientWidth + 1 }; }""")
        check("카드 일곱 장(창 1600px — 오른쪽 에이전트 대화창과 나란히라 네 장 + 세 장: 한 줄은 1800px 위 · 끝에 「문서 / 서식 복사」 · 회색 바탕 · 로고 있음) · 도움말에 받는 형식 hwp·hwpx·docx·pdf · 가로 넘침 없음", len(c["keys"]) == 7 and c["keys"][-1] == "style_copy" and c["tops"] <= 2 and (c["doc"], c["name"]) == ("문서", "서식 복사")
              and c["go"].startswith("문서 올려 시작") and "(hwp·hwpx·docx·pdf)" in c["title"] and c["tone"] == "any" and c["sym"] and c["fit"], c)

        # ---- 2. PDF — 작업을 만들지 않고 시작 화면 옆 2열 「서식 복사」
        acc = card_pick(page, {"name": "공고문.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4 smoke"})
        page.wait_for_selector("#headsDlg[data-kind=styleSave] .sl-cand")
        home = page.evaluate("""() => { const h = document.getElementById('headsDlg').getBoundingClientRect(), e = document.getElementById('empty').getBoundingClientRect();
            return { id: state.id, noDoc: document.body.classList.contains('no-doc'), beside: h.left >= e.right - 1 && h.width > 200 && e.width > 300, dialogs: document.querySelectorAll('dialog[open]').length,
                     title: document.getElementById('headsDlgTitle').textContent, hash: location.hash }; }""")
        check("PDF — 파일 고르기가 pdf 도 받음 · 작업 없음(시작 화면 그대로) · 2열이 시작 화면 옆에(팝업 아님) · 제목 「서식 복사 — 공고문.pdf」", acc == ".hwp,.hwpx,.docx,.pdf" and calls["extract"] == 1 and home["id"] is None and home["noDoc"]
              and home["beside"] and home["dialogs"] == 0 and home["title"] == "서식 복사 — 공고문.pdf" and home["hash"] == "" and works() == [] and page.evaluate(VIS, "empty"), home)
        tabs, on, kinds = page.evaluate(CTABS), page.evaluate(CTAB_ON), page.evaluate(KINDS)
        check("PDF 후보의 탭 — 표지 0 · 내용 0 · 테이블 서식 1 · 쪽 설정 1 · 문단 0(0개인 탭도 보임) · 처음 탭 = 테이블 서식(내용 서식 후보가 없어 처음으로 후보가 있는 탭) · 보이는 줄은 표 후보뿐 · 「LLM 검토」·「한 번에 진행」 있음 · 옵션(글 그대로·구조까지) 없음",
              tabs == ["표지 서식 0", "내용 서식 0", "테이블 서식 1", "쪽 설정 1", "문단 서식 0"] and on == ["table"] and kinds == ["table"] and page.evaluate(SECS) == ["table"]
              and page.inner_text("#headsDlg [data-sl-act=name]") == "LLM 검토" and page.locator("#headsDlg [data-sl-act=auto]").count() == 1 and page.locator("#headsDlg [data-sl-opt]").count() == 0, (tabs, on, kinds))
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=F1] .sp-pic[data-sp-kind=table]")
        tds = page.evaluate("() => document.querySelectorAll('#headsDlg .sl-cand[data-cand=F1] .sp-tbl td').length")
        dirty = "() => document.querySelectorAll('#headsDlg .sp-pic [data-id], #headsDlg .sp-pic .para, #headsDlg .sp-pic table.tbl, #headsDlg .sp-pic [contenteditable]').length"
        d1 = page.evaluate(dirty)
        ctab(page, "page")
        check("탭 「쪽 설정」 — 쪽 설정 후보 하나(요약 한 줄 · 추천 · 이름 「<문서> 쪽 설정」) · 보이는 줄은 그 탭의 것뿐", page.evaluate(KINDS) == ["page"] and page.evaluate(SECS) == ["page"]
              and PSUM in page.text_content("#headsDlg .sl-cand[data-kind=page]") and "추천" in page.inner_text("#headsDlg .sl-cand[data-kind=page] .sl-cfold-sum") and page.input_value("#headsDlg .sl-cand[data-kind=page] .sl-cname") == "공고문 쪽 설정", page.evaluate(KINDS))
        page.wait_for_selector("#headsDlg .sl-cand[data-kind=page] .sp-pic[data-sp-kind=page]")
        pics = {"mg": page.evaluate("() => [...document.querySelectorAll('#headsDlg .sl-cand[data-kind=page] .sp-mg')].map((e) => e.textContent)"), "tds": tds, "dirty": d1 + page.evaluate(dirty)}
        check("파일 후보의 서식 그림(문서가 없어도) — 쪽 도식(여백 수치) · 작은 표 · 견본 요청 = POST /api/styles/preview-file {token, pick: {kind, key, bands?}} · 그림 안에 편집 화면의 것 없음",
              pics == {"mg": ["위 20", "왼 25", "오 25", "아래 20"], "tds": 12, "dirty": 0} and {"token": "tok1", "pick": {"kind": "page", "key": "page"}} in calls["preview_file"]
              and {"token": "tok1", "pick": {"kind": "table", "key": "F1", "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}}} in calls["preview_file"], (pics, calls["preview_file"]))
        page.check("#headsDlg .sl-cand[data-kind=page] .sl-crow > input[type=checkbox]")
        page.click("#headsDlgFoot [data-sl-act=save]")
        page.wait_for_selector("#headsDlg .sl-cand[data-kind=page].done")
        check("쪽 설정 저장(파일) — from-file picks = [{kind: page, key: page, name}]", calls["from_file"] == [{"token": "tok1", "picks": [{"kind": "page", "key": "page", "name": "공고문 쪽 설정"}]}], calls["from_file"])
        page.click("#headsDlgTools [data-sl-act=toLibTop]")
        page.wait_for_selector("#headsDlg[data-kind=styleLib] [data-sl-tab=table]")  # 처음 갈래는 내용 서식 — 테이블 서식으로
        page.click("#headsDlgTools [data-sl-tab=table]")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl1]")
        more(page, "s_tbl1")
        a1 = page.evaluate(ACTS, "s_tbl1")
        check("시작 화면의 서식 관리자 — 「이 문서에서 복사」·적용 단추는 꺼짐 · 받기는 켜짐", page.is_disabled("#headsDlgTools [data-sl-act=fromDoc]") and page.is_enabled("#headsDlgTools [data-sl-act=fromFile]")
              and a1["blank"] and a1["restyle"] and a1["getHwpx"] is False and a1["getDocx"] is False, a1)
        page.screenshot(path=str(OUT / "2_home_pdf.png"))
        page.click("#headsDlgClose")
        check("닫으면 시작 화면 그대로(작업 없음)", not page.evaluate(VIS, "headsDlg") and page.evaluate("() => state.id") is None and page.evaluate(VIS, "empty") and works() == [])

        # ---- 3. hwpx — 작업이 열리고 2열 「서식 복사」 · 한 번에 진행
        card_pick(page, str(ROOT / "samples" / SMALL))
        page.wait_for_function("() => !!state.id && document.querySelector('#doc .sheet .para') != null && !!document.querySelector('#headsDlg[data-kind=styleSave] .sl-cand')", timeout=120000)
        a = page.evaluate("() => state.id")
        st = page.evaluate("() => ({ task: state.task, tool: document.getElementById('panel').dataset.tool, title: document.getElementById('headsDlgTitle').textContent })")
        check("hwpx — TASK 「문서 서식 복사」(일반 문서)로 작업이 열림 · 패널 = 에이전트 · 2열 = 「서식 복사 — <문서>」", st["task"]["job"] == "style_copy" and st["task"]["kind"] == "general" and st["tool"] == "Agent"
              and st["title"].startswith("서식 복사 — ") and len(works()) == 1, st)
        tabs, on = page.evaluate(CTABS), page.evaluate(CTAB_ON)
        check("후보의 탭 — 표지 서식 0 · 내용 서식 1(처음 탭) · 테이블 서식 3 · 쪽 설정 1 · 문단 서식 1 · 보이는 줄은 내용 서식의 것뿐 · 단계 줄(① 끝남 · ② 이름 「LLM 검토」) · 옵션 「글도 그대로 저장」 있음(hwpx)",
              tabs == ["표지 서식 0", "내용 서식 1", "테이블 서식 3", "쪽 설정 1", "문단 서식 1"] and on == ["content"] and page.evaluate(KINDS) == ["text"] and page.evaluate(SECS) == ["content"]
              and page.evaluate(STEPS) == ["done", "todo", "todo", "todo"] and page.inner_text("#headsDlg .sl-step[data-step=name] .sl-step-name") == "LLM 검토" and page.locator("#headsDlg [data-sl-opt=keepText]").count() == 1, (tabs, on))
        page.screenshot(path=str(OUT / "3_copy_hwpx.png"))
        copy_width = page.evaluate("() => colSizers.find((x) => x.box === 'headsDlg').w")
        for width in (320, 480):
            page.evaluate("(w) => { const c = colSizers.find((x) => x.box === 'headsDlg'); c.w = w; c.apply(); }", width)
            page.wait_for_selector("#headsDlg .sl-cand .sp-pic")
            page.locator("#headsDlg").screenshot(path=str(OUT / f"copy_content_{width}.png"))
        page.evaluate("(w) => { const c = colSizers.find((x) => x.box === 'headsDlg'); c.w = w; c.apply(); }", copy_width)
        page.click("#headsDlg [data-sl-act=auto]")  # 열린 탭은 내용 서식 — 「한 번에 진행」 은 모든 탭의 후보에 걸친다(쪽 설정 · 표도 저장된다)
        page.wait_for_selector("#headsDlg .sl-vbox[data-state=done]", timeout=40000)
        page.wait_for_function("() => !STYLE.save.auto")
        vs = page.inner_text("#headsDlg .sl-vbox")
        LEFT = """(keys) => Object.fromEntries(keys.map((k) => { const b = document.querySelector(`#headsDlg .sl-cand[data-cand=${k}]`);
          return [k, [b.classList.contains('done'), b.querySelector('.sl-crow > input').checked, [...b.querySelectorAll('.sl-review .sl-rv')].map((e) => e.querySelector('span').textContent)]]; }))"""
        tips, after = page.evaluate(CTIPS), page.evaluate(CTABS)
        ctab(page, "table")  # 남은 후보는 그 탭에서 본다(다른 탭의 줄은 DOM 에 없다)
        left = page.evaluate(LEFT, ["T2", "T3"])
        ctab(page, "para")
        left.update(page.evaluate(LEFT, ["P1"]))
        check("한 번에 진행 뒤의 탭 — 수는 그대로 · 저절로 고른 채 남은 것 없음(「· n개 고름」 없음) · 도움말에 탭마다 「확인이 필요한 것」(테이블 서식 1 = 의심이 붙은 표 · 문단 서식 1 = LLM 이 고친 문단 서식 · 내용 서식·쪽 설정 0 = 저장됨)",
              after == ["표지 서식 0", "내용 서식 1", "테이블 서식 3", "쪽 설정 1", "문단 서식 1"]
              and tips == ["후보 0 · 고름 0 · 확인이 필요한 것 0", "후보 1 · 고름 0 · 확인이 필요한 것 0", "후보 3 · 고름 0 · 확인이 필요한 것 1", "후보 1 · 고름 0 · 확인이 필요한 것 0", "후보 1 · 고름 0 · 확인이 필요한 것 1"], (after, tips))
        check("「한 번에 진행」 — ② LLM 검토 한 번({llm: true}) → ③ 추천이면서 의심·LLM 고침이 없는 후보만 저장(내용 서식 · 쪽 설정 · 추천 표) → ④ 검증을 기다림 · 단계 넷 모두 끝남",
              [b.get("llm") for b in calls["cands"]].count(True) == 1 and [b["kind"] for b in calls["save"]] == ["text", "page", "table"] and calls["save"][1]["name"].endswith(" 쪽 설정")
              and calls["save"][0].get("template") == "tpl1" and calls["save"][2]["name"] == "구분 표" and calls["save"][2].get("note") == "수요조사 양식표 — 머리 1행·머리열"
              and page.evaluate(STEPS) == ["done"] * 4, calls["save"])
        check("확인이 필요한 후보는 저장하지 않는다 — 의심이 붙은 표(「LLM 확인 — …」) · LLM 이 고친 문단 서식(「LLM 고침 — …」)은 고르지 않은 채 남고, 추천 아닌 표도 그대로 · 끝 요약에 「확인이 필요한 후보 2개 — 보고 골라 저장하세요」",
              left["T2"][:2] == [False, False] and left["T3"] == [False, False, ["LLM 이 봄 — 이름 · 띠 수 · 역할", "LLM 확인 — 안내문 표로 보임"]]
              and left["P1"] == [False, False, ["LLM 이 봄 — 이름 · 역할", "LLM 고침 — 역할: other → caption"]] and "확인이 필요한 후보 2개 — 보고 골라 저장하세요" in page.inner_text("#headsDlg .sl-wrap > .sl-msg"), left)
        check("검증 요약(형식마다) + 「서식 관리자에서 보기」 · 끝 글", "PDF 검증 끝 — 서식 3개" in vs and "hwpx — 검증됨 3" in vs and "docx — 검증됨 3" in vs and "서식 관리자에서 보기" in vs
              and "한 번에 진행 끝" in page.inner_text("#headsDlg .sl-wrap"), vs)
        L["llm"] = "off"
        n_save = len(calls["save"])
        page.click("#headsDlg [data-sl-act=auto]")
        page.wait_for_selector("#headsDlg .sl-wrap > .sl-msg.err")
        check("LLM 을 쓸 수 없으면 ② 에서 멈춤 — 「에이전트(LLM)를 쓸 수 없습니다 — 후보를 직접 골라 저장하세요」 · 저장 안 함", "에이전트(LLM)를 쓸 수 없습니다 — 후보를 직접 골라 저장하세요" in page.inner_text("#headsDlg .sl-wrap > .sl-msg.err")
              and len(calls["save"]) == n_save and page.inner_text("#headsDlg [data-sl-act=auto]") == "한 번에 진행", page.inner_text("#headsDlg .sl-wrap > .sl-msg.err"))
        L["llm"] = "ok"

        # ---- 4. 도구 줄 「서식」 묶음
        TB = "() => ({ modes: [...document.querySelectorAll('#toolModes [data-tool]')].map((b) => b.dataset.tool), set: !document.querySelector('.tool-set[data-tool-set=style]').hidden, kind: document.getElementById('headsDlg').hidden ? null : document.getElementById('headsDlg').dataset.kind, " \
             "pressed: document.getElementById('tbStyleLib').getAttribute('aria-pressed'), icons: [...document.querySelectorAll('.tool-set[data-tool-set=style] .icon.tb')].map((b) => [b.id, b.getAttribute('aria-label'), !!b.querySelector('svg.toolbar-glyph'), b.textContent.trim()]) })"
        page.click("#headsDlgClose")
        page.click("#toolModes [data-tool=style]")
        page.wait_for_selector("#headsDlg[data-kind=styleLib]")
        tb = page.evaluate(TB)
        check("다섯째 묶음 「서식」 — 누르면 묶음(아이콘 단추 넷 — 넷째 「템플릿 관계」 · 글 없음)이 펴지고 서식 관리자도 열림 · #tbStyleLib 눌림", tb["modes"] == ["page", "font", "para", "table", "style"] and tb["set"] and tb["kind"] == "styleLib" and tb["pressed"] == "true"
              and tb["icons"] == [["tbStyleLib", "서식 관리자", True, ""], ["tbStyleCopy", "이 문서에서 복사", True, ""], ["tbStyleFile", "파일에서 복사", True, ""], ["tbTplRel", "템플릿 관계", True, ""]] and page.inner_text("#headsDlgTitle") == "서식 관리자", tb)
        page.click("#tbStyleLib")
        off = page.evaluate(TB)
        page.click("#tbStyleCopy")
        page.wait_for_selector("#headsDlg[data-kind=styleSave]")
        check("「서식 관리자」 를 다시 누르면 닫힘(눌림 풀림) · 「이 문서에서 복사」 = 「서식 복사」 보기(서식 관리자 눌림)", off["kind"] is None and off["pressed"] == "false" and page.evaluate(TB)["pressed"] == "true")
        with page.expect_file_chooser() as fc:
            page.click("#tbStyleFile")
        check("「파일에서 복사」 — 파일 고르기(hwp·hwpx·docx·pdf)", fc.value.element.evaluate("(e) => e.accept") == ".hwp,.hwpx,.docx,.pdf")

        # ---- 5. 다시 열기 — 이 TASK 의 작업은 2열 「서식 복사」 · 다른 문서는 기억한 「서식」 묶음만(서식 관리자는 안 엶)
        page.reload()
        page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null && !!document.querySelector('#headsDlg[data-kind=styleSave] .sl-cand')", arg=a, timeout=120000)
        check("다시 열기(새로 고침) — TASK 「문서 서식 복사」 의 작업은 2열에 「서식 복사」 보기 · 패널 = 에이전트", page.evaluate("() => document.getElementById('panel').dataset.tool") == "Agent" and page.evaluate(TB)["set"])
        plain = requests.post(f"{base}/api/docs?new=1", files={"file": (SMALL, (ROOT / "samples" / SMALL).read_bytes())}, timeout=120).json()["docId"]
        page.evaluate("(id) => { location.hash = '#w=' + id; }", plain)
        page.reload()
        page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=plain, timeout=120000)
        page.wait_for_timeout(500)
        tb = page.evaluate(TB)
        check("TASK 없는 문서 — 기억한 「서식」 묶음은 되살리되 서식 관리자는 열지 않는다", tb["set"] and tb["kind"] is None and tb["pressed"] == "false", tb)

        # ---- 6. docx — 이 TASK 는 docx 로도 시작 · 패널 = 검증 · 옵션 없음 · 켜지는 동작
        page.click("#homeLink")
        page.wait_for_function("() => !state.id")
        CANDS["format"] = "docx"
        card_pick(page, str(ROOT / "samples" / DOCX))
        page.wait_for_function("() => !!state.id && state.format === 'docx' && !!document.querySelector('#headsDlg[data-kind=styleSave] .sl-cand')", timeout=120000)
        st = page.evaluate("() => ({ task: state.task, tool: document.getElementById('panel').dataset.tool })")
        check("docx — TASK 「문서 서식 복사」 로 열림 · 패널 = 검증 · 2열 「서식 복사」 · 「글도 그대로 저장」·「구조까지 저장」 없음(요약으로 다시 지음) · 도구 줄 「이 문서에서 복사」 켜짐", st["task"]["job"] == "style_copy" and st["tool"] == "Verify"
              and page.locator("#headsDlg [data-sl-opt]").count() == 0 and "요약 명세로 다시 지어" in page.inner_text("#headsDlg .sl-wrap") and page.is_enabled("#tbStyleCopy"), st)
        tabs, on = page.evaluate(CTABS), page.evaluate(CTAB_ON)
        check("docx 문서의 탭 — 레벨 없는 문단 묶음(옛 꼴의 texts)은 문단 서식 탭으로 · 내용 서식 0 이라 처음 탭 = 테이블 서식", tabs == ["표지 서식 0", "내용 서식 0", "테이블 서식 2", "쪽 설정 1", "문단 서식 1"] and on == ["table"] and page.evaluate(KINDS) == ["table", "table"], (tabs, on))
        n_save = len(calls["save"])
        page.check("#headsDlg .sl-cand[data-cand=T1] .sl-crow > input[type=checkbox]")
        ctab(page, "para")
        page.check("#headsDlg .sl-cand[data-cand=X1] .sl-crow > input[type=checkbox]")
        picked = page.evaluate(CTABS)
        page.click("#headsDlgFoot [data-sl-act=save]")  # 두 탭에서 고른 것을 한 번에(열린 탭 = 문단 서식)
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=X1].done")
        x_kind = page.get_attribute("#headsDlg .sl-cand[data-cand=X1]", "data-kind")
        ctab(page, "table")
        page.wait_for_selector("#headsDlg .sl-cand[data-cand=T1].done")
        sv = calls["save"][n_save:]
        check("docx 문서의 저장 — 테이블 서식 = {kind: table, table, bands} · 문단 서식(레벨 없는 문단 묶음 — 옛 꼴의 texts 도 문단 서식 후보로) = {kind: text, paras}(keepText·blueprint 없음) · 두 탭에서 고른 것이 탭 글에 보이고(「· 1개 고름」) 함께 저장됨",
              [sorted(b) for b in sv] == [["bands", "kind", "name", "table"], ["kind", "name", "paras"]] and sv[1]["paras"] == [CANDS["para"]] and sv[0]["table"] == CANDS["table"]
              and x_kind == "para" and picked == ["표지 서식 0", "내용 서식 0", "테이블 서식 2 · 1개 고름", "쪽 설정 1", "문단 서식 1 · 1개 고름"], (sv, picked))
        page.click("#headsDlgTools [data-sl-act=toLibTop]")
        page.wait_for_selector("#headsDlg[data-kind=styleLib] [data-sl-tab=table]")
        page.click("#headsDlgTools [data-sl-tab=table]")
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_tbl1]")
        more(page, "s_tbl1")
        a1 = page.evaluate(ACTS, "s_tbl1")
        tip = page.get_attribute("#headsDlg .sl-item[data-style=s_tbl1] [data-sl-act=restyle]", "title")
        page.click("#headsDlgTools [data-sl-tab=content]")  # 쪽 설정은 내용 서식 갈래 안의 한 구역
        page.wait_for_selector("#headsDlg .sl-item[data-style=s_pg1]")
        more(page, "s_pg1")
        a2 = page.evaluate(ACTS, "s_pg1")
        check("docx 문서의 서식 관리자 — 「이 문서에서 복사」 켜짐 · 「빈 표 넣기」·받기는 켜짐 · 「표 모양 입히기」·「쪽 설정 입히기」 는 꺼짐(도움말에 까닭)", page.is_enabled("#headsDlgTools [data-sl-act=fromDoc]")
              and a1["blank"] is False and a1["restyle"] is True and a1["getDocx"] is False and "docx 문서에는 빈 표 넣기 · 문단에 입히기만 됩니다" in tip and a2["page"] is True and a2["getHwpx"] is False, (a1, a2, tip))
        for width in (320, 480):
            page.evaluate("(w) => { const c = colSizers.find((x) => x.box === 'headsDlg'); c.w = w; c.apply(); }", width)
            page.wait_for_timeout(300)
            page.click("#tbStyleCopy")
            page.wait_for_selector("#headsDlg[data-kind=styleSave] .sl-cand")
            fit = page.evaluate("""() => { const p = document.getElementById('headsDlg'), r = p.getBoundingClientRect();
                return { w: Math.round(r.width), bad: [...p.querySelectorAll('.hd-tools *, .hd-body *, footer *')].filter((e) => e.getClientRects().length && e.getBoundingClientRect().right > r.right + 0.5).slice(0, 6).map((e) => (e.className || e.tagName) + ':' + (e.textContent || '').slice(0, 20)) }; }""")
            lines = page.evaluate("() => new Set([...document.querySelectorAll('#headsDlg [data-sl-ctab]')].map((b) => Math.round(b.getBoundingClientRect().top))).size")
            check(f"「서식 복사」 · 2열 {width}px — 가로 넘침 없음(단계 줄 · 탭 다섯 · 후보){' · 탭은 다음 줄로 접힘' if width == 320 else ''}", fit["w"] in (width - 1, width) and not fit["bad"] and page.locator("#headsDlg [data-sl-ctab]").count() == 5
                  and (lines >= 2 or width != 320), (fit, lines))
            page.locator("#headsDlg").screenshot(path=str(OUT / f"copy_panel_{width}.png"))

        expected = [e for e in errors if "status of 503" in e]  # 일부러 낸 LLM 없음(503) 한 번
        check("콘솔 오류·pageerror 없음(일부러 낸 503 말고)", [e for e in errors if e not in expected] == [] and len(expected) == 1, errors[:5])
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

"""분석 상태(spec_작업 ② §20 — index.html #docStatus · #peerStatus · app/static/doc_status.js · GET …/analysis) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 진짜(「LLM 을 돌린 문서」·「검토한 문서」 의 꼴만 …/analysis 응답을 끼워 본다 — 서버는 LLM 끔).

문서를 API 로 올린다(화면이 아니라 첫 분석이 안 돈다 — 분석 없는 문서): ㉮ 기술수요조사서(hwpx) ㉯ 기술수요조사서(docx) ㉰ 연구개발계획서 양식(hwpx — 지원 양식) ㉱㉲ 이관으로 묶은 사업계획서 · 연차보고서.
- ㉮ 이름 줄: 바로 열기 아이콘 다음 · 파일 크기 앞에 「헤딩 없음 · 표 없음 · LLM 안 함」 + 「분석」 단추 — 줄 높이 35px · 넘침 없음 · 표시 24px 이하. 열기만 해서는 분석이 돌지 않는다.
- 「분석」 → `POST …/headings {first: true}` 한 번 → 「헤딩 ✓ · 표 ✓ · LLM 안 함」, 단추 사라짐. 구분 기준 LLM 검토는 부르지 않는다. 도는 동안의 꼴(「◌ 헤딩 분석 중 N초 · 표 대기」)은 큰 양식 문서 ㉰ 로 본다.
- 분석 뒤 줄 = 「헤딩 ✓ · 템플릿 ✓ · 서식 0/2 · 표 ✓ · LLM 안 함 ▾」(2026-11-16 넷 — 템플릿 · 서식은 헤딩 그래프가 있을 때만). 표시를 누르면 **진행표**(넷 × 스크립트 · LLM 검증·보완 · 문서 반영)가
  이름 줄 아래로 펼쳐지고(바깥 · Esc 로 닫힘), 칸을 누르면 그 도구로(헤딩 → 「헤딩 추출」 · 표 → 「표」 · 템플릿 → 「템플릿 관계」 · 서식 LLM → 「템플릿 서식 정리」 열).
  진행표 아래 「LLM 검증·보완」 — 「돌 것」 셋을 보이고, 누르면 POST …/analysis/llm 한 번(열기만 해서는 안 부름 · LLM 끔이라 헤딩에서 「LLM 이 꺼져 있습니다」 로 멈춤 → 「LLM 실패」).
  좁은 폭(700px)에서는 옵션 항목(LLM)을 감추고 넷과 ▾ 는 남는다.
- ㉯ docx: 「헤딩 · 표 분석 없음(hwpx 만)」 한마디(단추 없음).
- ㉰ 지원 양식 · 연구개발과제: 「구분 기준 안 함」 이 더 보인다 → 누르면 「작업 내용」 + 2열 「구분 기준 — LLM 검토 결과」. 일반 문서로 바꾸면 그 항목이 없다.
  끼운 응답으로: LLM 을 돌린 문서 = 「헤딩 ✓ LLM ✓ · 표 ✓ LLM 안 함 · 구분 기준 후보 3」 · 도는 중 = 동그라미 + 지난 시간.
- ㉲ 를 열면 둘째 면 머리에 ㉱ 의 상태가 누를 수 없는 표시로(「분석」 단추 없음) — ㉱ 를 분석하면 「✓」 로 바뀐다.
- 끼운 응답으로: LLM 검증·보완이 도는 중 = 「◌ LLM 검증·보완 헤딩」 + 진행표의 단계 줄 · 「멈추기」.
- 콘솔 오류 없음.

    python -X utf8 tools/smoke_doc_status_ui.py <출력 폴더> [--port 18481]
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
ap.add_argument("--port", type=int, default=18481)
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
errors, fails, posts = [], [], []
SAMPLES = ROOT / "samples"
SMALL, DOCX, FORM = "기술수요조사서.hwpx", "기술수요조사서.docx", "연구개발계획서_양식.hwpx"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:700] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def wait_server(timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if requests.get(base + "/api/headings/llm", timeout=2).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.4)
    raise SystemExit("서버가 안 뜸")


def upload(name, new=False):
    r = requests.post(base + "/api/docs" + ("?new=1" if new else ""), files={"file": (name, (SAMPLES / name).read_bytes(), "application/octet-stream")}, timeout=120)
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def task(wid, file):
    requests.put(f"{base}/api/works/{wid}/task", json={"kind": "rnd", "file": file, "job": "plan_to_report", "project": "DS"}, timeout=10).raise_for_status()


def on_request(req):
    if req.method == "POST" and (req.url.endswith("/headings") or req.url.endswith("/divisions/review") or req.url.endswith("/analysis/llm")):
        posts.append((req.url.rsplit("/api/docs/", 1)[-1], req.post_data or ""))


# 표시 묶음(#docStatus · #peerStatus) — 표시마다 글(이름 + 상태) · 꼴 · 줄 안인지, 「분석」 단추, 줄의 차례·높이·넘침
STATUS = """(id) => { const h = document.getElementById(id), row = h.parentElement, vis = (e) => !!e && e.getClientRects().length > 0, rr = row.getBoundingClientRect();
  const inside = (e) => { const r = e.getBoundingClientRect(); return r.left >= rr.left - 1 && r.right <= rr.right + 1 && r.top >= rr.top - 1 && r.bottom <= rr.bottom + 1; };
  const chips = [...h.querySelectorAll('.ds-chip')].map((c) => ({ text: [...c.querySelectorAll('.ds-text, .ds-mark')].map((e) => e.textContent).join(' '), tag: c.tagName, cls: c.className,
    shown: vis(c), inside: vis(c) && inside(c), h: Math.round(c.getBoundingClientRect().height), spin: !!c.querySelector('.ds-spin'), secs: (c.querySelector('.ds-secs') || {}).textContent || '', title: c.title, go: c.dataset.go || '' }));
  const go = h.querySelector('.ds-go'), more = h.querySelector('.ds-more');
  return { hidden: h.hidden, more: more ? { shown: vis(more), inside: vis(more) && inside(more), exp: more.getAttribute('aria-expanded') } : null, base: h.dataset.base || '', chips, texts: chips.filter((c) => c.shown).map((c) => c.text), all: chips.map((c) => c.text),
    go: go ? { text: go.textContent.trim(), shown: vis(go), off: go.disabled, h: Math.round(go.getBoundingClientRect().height) } : null,
    order: [...row.children].map((e) => e.id).filter(Boolean), rowH: Math.round(rr.height), over: row.scrollWidth > row.clientWidth + 1 }; }"""
READY = "(id) => { const h = document.getElementById('docStatus'); return state.id === id && !h.hidden && h.querySelector('.ds-chip') != null; }"
# 진행표(#dsTable) — 줄 이름 · 칸 머리 · 칸(글 · 꼴) · 「돌 것」 · 단추 · 단계 줄 · 자리
TABLE = """() => { const t = document.getElementById('dsTable'); if (!t || t.hidden) return null; const r = t.getBoundingClientRect(), row = document.getElementById('docStatus').parentElement.getBoundingClientRect();
  const go = t.querySelector('.ds-llm-go'), stop = [...t.querySelectorAll('button')].find((b) => b.textContent === '멈추기');
  return { rows: [...t.querySelectorAll('.ds-row-name')].map((e) => e.textContent), cols: [...t.querySelectorAll('.ds-col')].map((e) => e.textContent).filter(Boolean),
    cells: [...t.querySelectorAll('.ds-cell')].map((c) => ({ text: c.querySelector('span') ? c.querySelector('span').textContent : '', cls: c.className.replace('ds-cell', '').trim(), btn: c.tagName === 'BUTTON' })),
    plan: [...t.querySelectorAll('.ds-plan li')].map((e) => (e.classList.contains('run') ? 'run' : e.classList.contains('skip') ? 'skip' : e.className)), steps: [...t.querySelectorAll('.ds-step')].map((e) => e.className.replace('ds-step', '').trim()),
    planWith: [...t.querySelectorAll('.ds-plan li')].map((e) => !!e.querySelector('.ds-with')), stepWith: [...t.querySelectorAll('.ds-step')].map((e) => !!e.querySelector('.ds-with')),
    planNo: [...t.querySelectorAll('.ds-plan li')].map((e) => (e.querySelector('.ds-step-no') || {}).textContent || ''), stepNo: [...t.querySelectorAll('.ds-step')].map((e) => (e.querySelector('.ds-step-no') || {}).textContent || ''),
    go: go ? { text: go.textContent, off: go.disabled } : null, stop: !!stop,
    box: { left: Math.round(r.left), right: Math.round(r.right), top: Math.round(r.top) }, rowBottom: Math.round(row.bottom), vw: innerWidth }; }"""


def open_doc(page, doc):
    page.evaluate("(id) => { openWork(id); }", doc)
    page.wait_for_function("(id) => state.id === id && !document.getElementById('fileInfo').hidden && !!document.querySelector('#doc .para')", arg=doc, timeout=120000)
    page.wait_for_function(READY, arg=doc, timeout=30000)
    page.wait_for_timeout(500)


def fake(items, base_state="done", kind="rnd", job=None, busy=None, chain=None, plan=None):
    return {"rev": 0, "format": "hwpx", "kind": kind, "base": base_state, "busy": bool(job and job["status"] == "running") if busy is None else busy, "job": job, "items": items,
            "chain": chain, "llmPlan": plan or []}


def item(key, state="done", llm="none", **more):
    name = {"heads": "헤딩", "tables": "표"}[key]
    return {"key": key, "name": name, "state": state, "run": 2, "at": 1.0, "moved": False, "text": f"{name} 결과", "error": None,
            "llm": {"state": llm, "text": "LLM 판정함 — 반영 80" if llm == "done" else "LLM 판정 안 함 — 스크립트 결과", "error": None}, **more}


def tpl_item(state="done", llm="none"):
    return {"key": "templates", "name": "템플릿", "state": state, "count": 2, "list": [{"id": "1", "no": "1", "chain": "□ › o", "lines": 9}, {"id": "2", "no": "2", "chain": "-", "lines": 3}],
            "text": "T1 □ › o · T2 -", "llm": {"state": llm, "text": "헤딩 그래프(LLM)의 구간 검토를 거침" if llm == "done" else "LLM 검토 안 함", "error": None}}


def fmt_item(state="done", aligned=1, levels=3, llm="none"):
    return {"key": "formats", "name": "서식", "state": state, "levels": levels, "aligned": aligned, "groups": 5, "others": 4, "slots": [], "text": f"레벨 {levels} · 서식 갈래 5",
            "llm": {"state": llm, "text": "서식 정리 계획 안 받음 — 정리할 템플릿 1", "error": None, "need": 1, "planned": 0, "applied": 0, "stale": 0, "list": [{"tpl": "1", "no": "1", "state": "none"}]},
            "apply": {"state": "done" if aligned == levels else "none", "text": f"맞춘 레벨 {aligned}/{levels} · 대표와 다른 줄 4"}}


def division(state="none", found=0, partial=False):
    return {"key": "division", "name": "구분 기준", "optional": True, "state": state, "at": 1.0, "found": found, "applied": 0, "partial": partial, "error": "빠진 자리 검토 — 응답 없음" if partial else None,
            "text": f"구분 기준 LLM 검토함 — 빠진 자리 후보 {found} · 재검토 반영 0"}


def main():
    wait_server()
    raw, docx, form = upload(SMALL), upload(DOCX), upload(FORM)
    plan, report = upload(SMALL, new=True), upload(SMALL, new=True)
    task(plan, "plan")
    task(report, "report")
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1700, "height": 950}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.on("request", on_request)
        page.goto(f"{base}/#w={raw}")
        page.wait_for_selector("#doc .para", timeout=60000)
        page.wait_for_function(READY, arg=raw, timeout=30000)
        page.wait_for_timeout(1500)

        # ---- 1. 분석 없는 hwpx — 「없음」 + 「분석」 단추 · 열기만 해서는 안 돈다
        v = page.evaluate(STATUS, "docStatus")
        at = v["order"].index("docStatus") if "docStatus" in v["order"] else -1
        check("이름 줄 — 바로 열기 아이콘(#nameQuick) 다음 · 파일 크기(#fileMeta) 앞에 분석 상태", at > 0 and v["order"][at - 1] == "nameQuick" and v["order"][at + 1] == "fileMeta", v["order"])
        check("분석 없는 문서 — 「헤딩 없음 · 표 없음 · LLM 안 함」(구분 기준 항목 없음 — 연구개발 문서가 아님)", v["texts"] == ["헤딩 없음", "표 없음", "LLM 안 함"] and v["base"] == "none", v["texts"])
        check("「분석」 단추가 보임(켜짐)", bool(v["go"]) and v["go"]["shown"] and not v["go"]["off"] and v["go"]["text"] == "분석", v["go"])
        check("줄 높이 35px 그대로 · 넘침 없음 · 표시는 줄 안 · 24px 이하", v["rowH"] == 35 and not v["over"] and all(c["inside"] and c["h"] <= 24 for c in v["chips"]) and v["go"]["h"] <= 24, v)
        check("없음 = 주황 꼴(warn) · 안 함 = 회색(off) — 글로도 가른다", "warn" in v["chips"][0]["cls"] and "warn" in v["chips"][1]["cls"] and "off" in v["chips"][2]["cls"], [c["cls"] for c in v["chips"]])
        check("표시는 누르는 단추 · 도움말에 갈 곳", all(c["tag"] == "BUTTON" and "누르면" in c["title"] for c in v["chips"]), [(c["tag"], c["title"][-30:]) for c in v["chips"]])
        check("열기만 해서는 분석을 시작하지 않는다(POST 없음)", posts == [], posts)
        row = page.locator("#fileInfo").bounding_box()
        page.screenshot(path=str(OUT / "01_none.png"), clip={"x": row["x"], "y": row["y"] - 40, "width": row["width"], "height": 120})

        # ---- 2. 「분석」 → 도는 중 → ✓
        page.click("#docStatus .ds-go")   # 작은 문서라 1초 안에 끝난다 — 「도는 중」 꼴은 아래 6(큰 양식 문서)에서 본다
        page.wait_for_function("() => document.getElementById('docStatus').dataset.base === 'done'", timeout=180000)
        page.wait_for_timeout(400)
        v = page.evaluate(STATUS, "docStatus")
        av = requests.get(f"{base}/api/docs/{raw}/analysis", timeout=30).json()
        fm = next(i for i in av["items"] if i["key"] == "formats")
        want = ["헤딩 ✓", "템플릿 ✓", f"서식 {fm['aligned']}/{fm['levels']}", "표 ✓", "LLM 안 함"]
        check("끝나면 「헤딩 ✓ · 템플릿 ✓ · 서식 a/b · 표 ✓ · LLM 안 함」 · 「분석」 단추 없음 · ▾", v["texts"] == want and v["go"] is None and "ok" in v["chips"][0]["cls"]
              and bool(v["more"]) and v["more"]["shown"] and v["more"]["inside"], [v["texts"], want, v["more"]])
        check("도움말에 무엇을 뽑았는지(실행 번호 · 수) · 서식은 맞춘 레벨과 계획", v["chips"][0]["title"].startswith("헤딩 그래프 — 실행 ") and "템플릿" in v["chips"][0]["title"]
              and v["chips"][3]["title"].startswith("표 구조 — 실행 ") and "맞춘 레벨" in v["chips"][2]["title"] and "서식 정리 계획" in v["chips"][2]["title"], [c["title"] for c in v["chips"][:4]])
        hp = [x for x in posts if x[0].endswith("/headings")]
        check("POST …/headings 는 {first: true} 한 번", len(hp) == 1 and json.loads(hp[0][1]) == {"first": True}, posts)
        check("구분 기준 LLM 검토는 부르지 않는다(POST …/divisions/review 0번)", not [x for x in posts if x[0].endswith("/divisions/review")], posts)
        page.screenshot(path=str(OUT / "03_done.png"), clip={"x": row["x"], "y": row["y"] - 40, "width": row["width"], "height": 120})

        # ---- 3. 누르면 진행표 → 칸을 누르면 그 도구로
        page.click("#docStatus .ds-chip >> nth=2")   # 서식
        page.wait_for_selector("#dsTable:not([hidden])", timeout=10000)
        page.wait_for_timeout(200)
        t = page.evaluate(TABLE)
        check("진행표 — 넷(헤딩 · 템플릿 · 서식 · 표) × 세 칸(스크립트 · LLM 검증·보완 · 문서 반영) · ▾ 눌림", t["rows"] == ["헤딩", "템플릿", "서식", "표"] and t["cols"] == ["스크립트", "LLM 검증·보완", "문서 반영"]
              and len(t["cells"]) == 12 and page.evaluate(STATUS, "docStatus")["more"]["exp"] == "true", t)
        check("진행표 — 스크립트 칸은 넷 다 ✓ · 서식 반영은 「맞춘 레벨 a/b」 · 헤딩 · 템플릿 · 표의 반영은 「—」(문서를 안 바꾸는 일)",
              [c["cls"] for c in t["cells"][0::3]] == ["done"] * 4 and t["cells"][8]["text"].startswith("맞춘 레벨 ") and [t["cells"][i]["text"] for i in (2, 5, 11)] == ["—"] * 3, t["cells"])
        check("진행표 — 창 안 · 이름 줄 바로 아래", t["box"]["left"] >= 0 and t["box"]["right"] <= t["vw"] and 0 <= t["box"]["top"] - t["rowBottom"] <= 12, t["box"])
        check("진행표 — 「돌 것」 셋(헤딩 · 템플릿 먼저 → 표 · 서식 계획 같이) + 「LLM 검증·보완」 단추(켜짐) · 열기만 해서는 안 부름", t["plan"] == ["run", "run", "run"] and t["go"] == {"text": "LLM 검증·보완", "off": False}
              and not [x for x in posts if x[0].endswith("/analysis/llm")], [t["plan"], t["go"], posts])
        check("「돌 것」 — 차례 번호 1 · 2 · 2 · 같은 번호(표 · 서식)에 「같이」", t["planNo"] == ["1", "2", "2"] and t["planWith"] == [False, True, True], [t["planNo"], t["planWith"]])
        page.screenshot(path=str(OUT / "08_table.png"))
        page.keyboard.press("Escape")
        check("Esc 로 닫힘", page.evaluate("() => document.getElementById('dsTable').hidden"))
        page.click("#dsMore")
        page.click("#dsTable .ds-cell >> nth=0")
        page.wait_for_function("() => !document.getElementById('paneHeads').hidden", timeout=15000)
        check("헤딩 칸 → 「헤딩 추출」 탭 · 진행표 닫힘", page.evaluate("() => document.getElementById('panel').dataset.tool") == "Heads" and page.evaluate("() => document.getElementById('dsTable').hidden"))
        page.click("#dsMore")
        page.click("#dsTable .ds-cell >> nth=9")
        page.wait_for_function("() => !document.getElementById('paneTables').hidden", timeout=15000)
        check("표 칸 → 「표」 탭", page.evaluate("() => document.getElementById('panel').dataset.tool") == "Tables")
        page.click("#dsMore")
        page.click("#dsTable .ds-cell >> nth=7")   # 서식 LLM 칸
        page.wait_for_function("() => { const c = document.getElementById('headsDlg'); return !c.hidden && c.dataset.kind === 'tplAgent'; }", timeout=15000)
        check("서식 LLM 칸 → 「템플릿 서식 정리」 열(정리할 첫 템플릿)", page.evaluate("() => TPA.tpl") == fm["llm"]["list"][0]["tpl"], page.evaluate("() => TPA.tpl"))
        page.evaluate("() => headsColClose(true)")
        page.click("#dsMore")
        page.mouse.click(300, 600)   # 바깥(문서)
        page.wait_for_timeout(200)
        check("바깥을 누르면 닫힘", page.evaluate("() => document.getElementById('dsTable').hidden"))
        page.wait_for_timeout(500)
        v = page.evaluate(STATUS, "docStatus")
        check("도구를 오가도 상태는 그대로 · 다시 분석하지 않음", v["texts"] == want and len([x for x in posts if x[0].endswith("/headings") and "first" in x[1]]) == 1, [v["texts"], posts])
        # 「LLM 검증·보완」 — 진짜 끝점(서버 LLM 끔 → 헤딩에서 멈춤)
        page.click("#dsMore")
        page.click("#dsTable .ds-llm-go")
        page.wait_for_function("() => { const v = dsState.main; return v && v.chain && v.chain.status && v.chain.status !== 'running'; }", timeout=60000)
        page.wait_for_timeout(300)
        lp = [x for x in posts if x[0].endswith("/analysis/llm")]
        ch = page.evaluate("() => dsState.main.chain")
        check("「LLM 검증·보완」 → POST …/analysis/llm 한 번 · LLM 끔이라 헤딩에서 멈춤(까닭 「LLM 이 꺼져 있습니다」) · 뒤 단계는 대기",
              len(lp) == 1 and [x["status"] for x in ch["steps"]] == ["failed", "wait", "wait"] and "LLM 이 꺼져 있습니다" in ch["steps"][0]["msg"], [lp, ch])
        if page.evaluate("() => document.getElementById('dsTable').hidden"):
            page.click("#dsMore")
        t = page.evaluate(TABLE)
        v = page.evaluate(STATUS, "docStatus")
        check("멈춘 뒤 — 이름 줄 「LLM 실패」(주황) · 진행표에 지난 실행의 단계 줄 · 헤딩 · 템플릿 LLM 칸 실패 · 단추는 그대로",
              "LLM 실패" in v["texts"] and t["steps"][:1] == ["failed"] and t["cells"][1]["cls"] == "failed" and t["cells"][4]["cls"] == "failed" and t["go"] is not None, [v["texts"], t])
        page.screenshot(path=str(OUT / "09_table_failed.png"))
        page.keyboard.press("Escape")

        # ---- 4. 좁은 폭 — 옵션 항목부터 감춤
        page.set_viewport_size({"width": 1100, "height": 950})
        page.wait_for_timeout(400)
        v = page.evaluate(STATUS, "docStatus")
        check("1100px(패널 연 채) — 줄 높이 35px · 넘침 없음 · 넷은 줄 안", v["rowH"] == 35 and not v["over"] and v["texts"][:4] == want[:4] and all(c["inside"] for c in v["chips"] if c["shown"]), v)
        page.evaluate("() => setPanel(false)")
        page.set_viewport_size({"width": 700, "height": 950})
        page.wait_for_timeout(400)
        v = page.evaluate(STATUS, "docStatus")
        check("700px — 옵션 항목(LLM)을 감추고 넷과 ▾ 는 남는다 · 줄 높이 35px · 넘침 없음", v["texts"] == want[:4] and v["all"] == want[:4] + ["LLM 실패"] and v["more"]["shown"] and v["more"]["inside"]
              and v["rowH"] == 35 and not v["over"], v)
        page.click("#dsMore")
        t = page.evaluate(TABLE)
        check("700px — 진행표도 창 안", t["box"]["left"] >= 0 and t["box"]["right"] <= t["vw"], t["box"])
        page.keyboard.press("Escape")
        page.screenshot(path=str(OUT / "04_narrow.png"), clip={"x": 0, "y": 0, "width": 700, "height": 160})
        page.set_viewport_size({"width": 1700, "height": 950})
        page.wait_for_timeout(300)

        # ---- 5. docx — 한마디
        open_doc(page, docx)
        v = page.evaluate(STATUS, "docStatus")
        check("docx — 「헤딩 · 표 분석 없음(hwpx 만)」 한마디 · 단추 없음 · 누르는 표시 아님", v["texts"] == ["헤딩 · 표 분석 없음(hwpx 만)"] and v["go"] is None and v["chips"][0]["tag"] == "SPAN" and v["base"] == "na", v)
        check("docx — 줄 높이 35px · 넘침 없음", v["rowH"] == 35 and not v["over"], v)

        # ---- 6. 지원 양식 · 연구개발과제 — 구분 기준(옵션)
        open_doc(page, form)
        page.wait_for_function("() => document.querySelectorAll('#docStatus .ds-chip').length === 4", timeout=30000)
        v = page.evaluate(STATUS, "docStatus")
        check("연구개발 양식 — 「헤딩 없음 · 표 없음 · LLM 안 함 · 구분 기준 안 함」 + 「분석」", v["texts"] == ["헤딩 없음", "표 없음", "LLM 안 함", "구분 기준 안 함"] and bool(v["go"]), v["texts"])
        check("구분 기준 도움말 — 옵션 · 저절로 돌지 않음", "옵션" in v["chips"][3]["title"] and "저절로 돌지 않습니다" in v["chips"][3]["title"], v["chips"][3]["title"])
        check("양식을 열어도 LLM 검토 · 분석을 부르지 않는다", not [x for x in posts if x[0].startswith(form)], posts)
        page.click("#docStatus .ds-chip[data-go=DivReview]")
        page.wait_for_function("() => !document.getElementById('paneDiv').hidden && !document.getElementById('headsDlg').hidden && document.getElementById('headsDlg').dataset.kind === 'divisions-review'", timeout=30000)
        check("「구분 기준」 → 「작업 내용」 + 2열 「구분 기준 — LLM 검토 결과」(거기 「LLM 검토 실행」)", page.inner_text("#headsDlgTitle").strip() == "구분 기준 — LLM 검토 결과"
              and page.locator("#headsDlgFoot button", has_text="LLM 검토 실행").count() == 1, page.inner_text("#headsDlgTitle"))
        page.screenshot(path=str(OUT / "05_division.png"))
        page.evaluate("() => headsColClose()")
        # 일반 문서면 구분 기준 항목이 없다(작업 종류는 화면이 아는 값)
        page.evaluate("() => { state.task = { ...state.task, kind: 'general' }; docStatusLoad(); }")
        page.wait_for_timeout(700)
        check("일반 문서로 바꾸면 구분 기준 항목이 없다", page.evaluate(STATUS, "docStatus")["texts"] == ["헤딩 없음", "표 없음", "LLM 안 함"], page.evaluate(STATUS, "docStatus")["texts"])
        page.evaluate("() => { state.task = { ...state.task, kind: 'rnd' }; docStatusLoad(); }")
        page.wait_for_function("() => document.querySelectorAll('#docStatus .ds-chip').length === 4", timeout=15000)

        # 끼운 응답 — LLM 을 돌린 문서 · 검토한 문서 · 도는 중(서버는 LLM 끔이라 진짜로는 못 만든다)
        state = {"v": fake([item("heads", llm="done"), tpl_item(llm="done"), fmt_item(), item("tables"), division("done", 3)])}
        pat = re.compile(r"/api/docs/" + re.escape(form) + r"/analysis$")
        page.route(pat, lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(state["v"], ensure_ascii=False)))
        page.evaluate("() => docStatusPing()")
        page.wait_for_function("() => document.getElementById('docStatus').dataset.base === 'done'", timeout=15000)
        page.wait_for_timeout(300)
        v = page.evaluate(STATUS, "docStatus")
        check("LLM 을 돌린 문서 — 「헤딩 ✓ · 템플릿 ✓ · 서식 1/3 · 표 ✓ · LLM 2/4 · 구분 기준 후보 3」 · 「분석」 없음",
              v["texts"] == ["헤딩 ✓", "템플릿 ✓", "서식 1/3", "표 ✓", "LLM 2/4", "구분 기준 후보 3"] and v["go"] is None and not v["over"] and v["rowH"] == 35, v["texts"])
        page.screenshot(path=str(OUT / "06_llm_used.png"), clip={"x": row["x"], "y": row["y"] - 40, "width": row["width"], "height": 120})
        state["v"] = fake([item("heads", llm="running"), tpl_item(llm="running"), fmt_item(), item("tables"), division("running")], job={"first": False, "stage": 2, "llm": True, "status": "running", "what": "2단계 · LLM", "started": time.time() - 75, "error": None})
        page.evaluate("() => docStatusPing()")
        page.wait_for_function("() => !!document.querySelector('#docStatus .ds-chip.run .ds-secs')", timeout=15000)
        v = page.evaluate(STATUS, "docStatus")
        run = [c for c in v["chips"] if c["spin"]]
        check("도는 중(LLM) — 헤딩은 ✓ 그대로 · 「LLM 판정 중 1분 …초」 · 「구분 기준 검토 중」 은 동그라미",
              v["texts"][0] == "헤딩 ✓" and [c["text"] for c in run] == ["LLM 판정 중", "구분 기준 검토 중"] and run[0]["secs"].startswith("1분 "), [v["texts"], [c["secs"] for c in run]])
        # LLM 검증·보완이 도는 중 — 이름 줄 「◌ LLM 검증·보완 헤딩 N초」 · 진행표의 단계 줄 · 「멈추기」
        steps = [{"key": "heads", "name": "헤딩 · 템플릿 — 헤딩 그래프(LLM)", "no": 1, "status": "running", "msg": ""}, {"key": "tables", "name": "표 — 표 구조(LLM)", "no": 2, "status": "wait", "msg": ""},
                 {"key": "formats", "name": "서식 — 템플릿 서식 정리 계획", "no": 2, "status": "wait", "msg": ""}]
        state["v"] = fake([item("heads", llm="running"), tpl_item(llm="running"), fmt_item(llm="wait"), item("tables", llm="wait"), division()],
                          job={"first": False, "chain": "llm", "stage": 2, "llm": True, "status": "running", "what": "LLM 검증·보완", "started": time.time() - 20, "error": None},
                          chain={"steps": steps, "at": "heads", "stopping": False, "status": "running"})
        page.evaluate("() => docStatusPing()")
        page.wait_for_function("() => [...document.querySelectorAll('#docStatus .ds-chip.run .ds-text')].some((e) => e.textContent === 'LLM 검증·보완')", timeout=15000)
        v = page.evaluate(STATUS, "docStatus")
        run = [c for c in v["chips"] if c["spin"]]
        check("LLM 검증·보완 도는 중 — 「◌ LLM 검증·보완 헤딩 N초」", run and run[0]["text"] == "LLM 검증·보완 헤딩" and run[0]["secs"].endswith("초"), [c["text"] for c in run])
        page.click("#dsMore")
        t = page.evaluate(TABLE)
        check("도는 중의 진행표 — 단계 줄(헤딩 도는 중 · 표 · 서식 대기) · 「멈추기」 · 「LLM 검증·보완」 단추 없음 · 헤딩 LLM 칸 도는 중 · 표 LLM 칸 대기",
              t["steps"] == ["running", "wait", "wait"] and t["stop"] and t["go"] is None and t["cells"][1]["cls"] == "running" and t["cells"][10]["cls"] == "wait", t)
        check("도는 중의 단계 줄 — 차례 번호 1 · 2 · 2 · 표 · 서식에 「같이」", t["stepNo"] == ["1", "2", "2"] and t["stepWith"] == [False, True, True], [t["stepNo"], t["stepWith"]])
        page.screenshot(path=str(OUT / "10_chain_running.png"))
        page.keyboard.press("Escape")
        # 헤딩 · 템플릿이 끝나 표 · 서식이 같이 도는 중 — 이름 줄 「◌ LLM 검증·보완 표 · 서식」 · 단계 줄 둘 다 도는 중 · 진행 카드(dsRunning) 글에 둘 다
        steps2 = [dict(steps[0], status="ok", msg="반영 3"), dict(steps[1], status="running"), dict(steps[2], status="running", msg="T1 · T2 계획 받는 중(같이 2) — 끝남 0/2")]
        state["v"] = fake([item("heads", llm="done"), tpl_item(llm="done"), fmt_item(llm="running"), item("tables", llm="running"), division()],
                          job={"first": False, "chain": "llm", "stage": 3, "llm": True, "status": "running", "what": "LLM 검증·보완", "started": time.time() - 90, "error": None},
                          chain={"steps": steps2, "running": ["tables", "formats"], "at": "tables", "stopping": False, "status": "running"})
        page.evaluate("() => docStatusPing()")
        page.wait_for_function("() => [...document.querySelectorAll('#docStatus .ds-chip.run')].some((c) => c.textContent.includes('표 · 서식'))", timeout=15000)
        v = page.evaluate(STATUS, "docStatus")
        run = [c for c in v["chips"] if c["spin"]]
        rn = page.evaluate("() => { const r = dsRunning(); return r && { label: r.label, note: r.note }; }")
        check("표 · 서식 같이 — 이름 줄 「◌ LLM 검증·보완 표 · 서식」 · 진행 카드 「표 · 서식 같이 — 표: 도는 중 / 서식: T1 · T2 …」",
              run and run[0]["text"] == "LLM 검증·보완 표 · 서식" and rn and rn["note"].startswith("표 · 서식 같이 — 표: 도는 중 / 서식: T1 · T2") and "같이" in rn["label"], [[c["text"] for c in run], rn])
        page.click("#dsMore")
        t = page.evaluate(TABLE)
        check("같이 도는 중의 진행표 — 단계 줄 ✓ · ◌ · ◌ · 「같이」 둘 · 「멈추기」", t["steps"] == ["ok", "running", "running"] and t["stepWith"] == [False, True, True] and t["stop"], t)
        page.screenshot(path=str(OUT / "11_chain_together.png"))
        page.keyboard.press("Escape")
        # 한쪽 검토만 답함 — 후보가 없어도 「✓」 가 아니라 「일부만」 · 다른 헤딩 작업(1단계)이 도는 동안은 「분석」 단추가 없다
        state["v"] = fake([item("heads", state="none"), item("tables", state="none"), division("done", 0, partial=True)], base_state="none", busy=True)
        page.wait_for_function("() => document.getElementById('docStatus').dataset.base === 'none'", timeout=15000)
        v = page.evaluate(STATUS, "docStatus")
        check("한쪽 검토만 답함 — 「구분 기준 일부만」(주황 · 도움말에 까닭) · 다른 헤딩 작업이 도는 동안은 「분석」 단추 없음",
              v["texts"] == ["헤딩 없음", "표 없음", "LLM 안 함", "구분 기준 일부만"] and "warn" in v["chips"][3]["cls"] and "답을 못 받은" in v["chips"][3]["title"] and v["go"] is None, v)
        state["v"] = fake([item("heads", state="failed", error="ValueError: boom"), item("tables", state="none"), division()], base_state="failed")
        page.wait_for_function("() => document.getElementById('docStatus').dataset.base === 'failed'", timeout=15000)   # 도는 동안은 2초마다 다시 읽는다 — 핑 없이도 바뀐다
        v = page.evaluate(STATUS, "docStatus")
        check("실패 — 「헤딩 실패」(까닭은 도움말) · 「분석」 단추가 다시", v["texts"][:2] == ["헤딩 실패", "표 없음"] and "boom" in v["chips"][0]["title"] and bool(v["go"]), v)
        page.unroute(pat)
        # 진짜 끝점으로 「도는 중」 — 큰 양식 문서의 기본 분석(수십 초)을 「분석」 으로 걸고 도는 동안의 꼴만 본다(끝까지 기다리지 않는다 — 서버가 꺼질 때 같이 끝난다)
        page.evaluate("() => docStatusPing()")
        page.wait_for_function("() => document.getElementById('docStatus').dataset.base === 'none' && !!document.querySelector('#docStatus .ds-go')", timeout=15000)
        page.click("#docStatus .ds-go")
        page.wait_for_function("() => { const h = document.getElementById('docStatus'); return h.dataset.base === 'running' && !!h.querySelector('.ds-chip.run .ds-secs'); }", timeout=30000, polling=100)
        v = page.evaluate(STATUS, "docStatus")
        check("도는 동안(진짜 끝점) — 동그라미 + 「헤딩 분석 중 N초」 · 「표 대기」 · 「분석」 단추 없음",
              v["chips"][0]["spin"] and v["chips"][0]["text"] == "헤딩 분석 중" and v["chips"][0]["secs"].endswith("초") and v["texts"][1] == "표 대기" and v["go"] is None and v["rowH"] == 35 and not v["over"], v)
        hp = [x for x in posts if x[0] == f"{form}/headings"]
        check("양식의 「분석」 도 {first: true} 한 번 · 구분 기준 LLM 검토는 여전히 안 부름", len(hp) == 1 and json.loads(hp[0][1]) == {"first": True} and not [x for x in posts if x[0].endswith("/divisions/review")], posts)
        page.screenshot(path=str(OUT / "02_running.png"), clip={"x": row["x"], "y": row["y"] - 40, "width": row["width"], "height": 120})

        # ---- 7. 둘째 면(같이 보기) — 옆 문서의 상태를 그 머리에
        open_doc(page, report)
        page.wait_for_function("() => { const c = document.getElementById('peerCol'); return !c.hidden && document.getElementById('peerFrame').dataset.w; }", timeout=60000)
        page.wait_for_function("() => { const h = document.getElementById('peerStatus'); return !h.hidden && h.querySelector('.ds-chip') != null; }", timeout=30000)
        page.wait_for_timeout(500)
        pv, mv = page.evaluate(STATUS, "peerStatus"), page.evaluate(STATUS, "docStatus")
        check("둘째 면 머리 — 사업계획서의 상태 「헤딩 없음 · 표 없음 · LLM 안 함」 · 누를 수 없는 표시 · 「분석」 없음",
              pv["texts"][:3] == ["헤딩 없음", "표 없음", "LLM 안 함"] and all(c["tag"] == "SPAN" for c in pv["chips"]) and pv["go"] is None, pv)
        check("둘째 면 머리 — 표시는 머리 줄 안 · 넘침 없음", all(c["inside"] for c in pv["chips"] if c["shown"]) and not pv["over"], pv)
        check("첫째 면(연차보고서)은 제 상태 + 「분석」", mv["texts"][:2] == ["헤딩 없음", "표 없음"] and bool(mv["go"]), mv)
        requests.post(f"{base}/api/docs/{plan}/headings", json={"first": True}, timeout=30).raise_for_status()
        page.evaluate("() => docStatusPing()")
        page.wait_for_function("() => document.getElementById('peerStatus').dataset.base === 'done'", timeout=180000)
        pv, mv = page.evaluate(STATUS, "peerStatus"), page.evaluate(STATUS, "docStatus")
        check("옆 문서를 분석하면 둘째 면 표시가 「헤딩 ✓ · 템플릿 · 서식 · 표 ✓」 — 첫째 면은 그대로 「없음」 · 둘째 면에는 ▾ 없음(누를 수 없는 표시)",
              pv["texts"][0] == "헤딩 ✓" and "표 ✓" in pv["texts"] and pv["more"] is None and mv["texts"][:2] == ["헤딩 없음", "표 없음"], [pv["texts"], mv["texts"]])
        page.screenshot(path=str(OUT / "07_peer.png"), clip={"x": 0, "y": 0, "width": 1700, "height": 160})
        page.evaluate("() => closeDoc()")
        page.wait_for_timeout(500)
        check("문서를 닫으면 표시도 사라진다", page.evaluate("() => document.getElementById('docStatus').hidden && document.getElementById('peerStatus').hidden"))

        bad = [e for e in errors if "Failed to load resource" not in e]
        check("콘솔 오류 0", not bad, bad[:5])
        b.close()


try:
    main()
finally:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()

print(f"\n{'실패 ' + str(len(fails)) + '개: ' + ' / '.join(fails) if fails else '모두 통과'}")
sys.exit(1 if fails else 0)

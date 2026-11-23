"""헤딩 추출 「전체 실행」(조정까지) · 「단계별 실행 ▾」 화면 확인(spec_헤딩_추출 ② §7 「전체 실행」) — 임시 서버(임시 작업 폴더 · PDF 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_run_all_ui.py <그림·임시 폴더> [--port 18493]

LLM 은 **가짜**다(임시 서버 안에서만): 헤딩 그래프(LLM) · 표 구조(LLM)는 스크립트로 돌리고 「LLM 판정을 거침」 으로만 적는다(헤딩은 멈추기를 누를 틈으로 몇 초 쉰다) ·
서식 정리 에이전트는 기본 스킬의 기준(레터)대로 답한다(tools/smoke_adjust_ui.py 와 같은 가짜). 이어 돌리기 · 계획 받기 · 반영의 끝점과 화면 함수는 진짜다.
연구개발계획서_양식.hwpx 를 올려 2·3단계(스크립트)를 돌린 뒤 헤딩 탭 →
① 상태 줄 끝에 「전체 실행」 · 「단계별 실행 ▾」 둘(같은 줄 · 26px · 오른쪽 끝) ② 「단계별 실행 ▾」 = 고르기 목록(스크립트 · LLM 줄을 눌러 표시 — 누르는 것만으로는 안 돎 · 「고른 n개 실행」) ③ 「테이블」 탭에는 「단계별 실행 ▾」 만
④ 「전체 실행」 → 확인 창(돌 LLM 단계 · 문서가 바뀜) — 「취소」 면 아무것도 안 돎 ⑤ 「확인」 → 도는 동안 단추는 「멈추기」 · 에이전트 진행 카드에 보임 → 「멈추기」: 지금 단계가 끝나면 멈추고 **반영하지 않는다**(남은 것을 알림)
⑥ 다시 「전체 실행」 → 거친 단계는 건너뛰고 표 · 서식 계획 → 조정(모두 반영)까지 — 반영마다 실행 취소 1 · 받은 계획이 남지 않음 · 조정 칸 ✓ · 끝난 글(한 것 · 남은 것)
⑦ 남은 것이 없으면 다시 눌러도 묻지 않고 「남은 단계가 없습니다」 ⑧ 좁은 패널(320 · 388 · 480px)에서 가로 넘침 없음 · 콘솔 오류 없음
⑩ 「단계별 실행」 — 고른 것만 차례로(heads_run_pick.js): 확인 창 없이(2026-11-18) 고른 셋을 진행 줄의 차례로(보낸 요청 = 고른 것만) · 도는 동안 「단계별 실행 2/3 ▾」 · 메뉴의 차례 · 「멈추기」 ·
진행 줄의 기다림 표시 · 에이전트 진행 카드 → 끝난 글 / 멈추기(뒤는 안 돎) / LLM 이 답을 못 하면 뒤 LLM 단계는 남김 / 스크립트만 고르면 확인 창 없이."""
import argparse
import json
import os
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
ap.add_argument("--port", type=int, default=18493)
args = ap.parse_args()
OUT = Path(args.out).resolve()
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
OTHER = ROOT / "samples" / "기술수요조사서.hwpx"

OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
LAUNCH = OUT / "fake_llm_server.py"
LAUNCH.write_text('''import json, sys, time
import uvicorn
from app import heading_runs, llm

_call, _status = llm.call, llm.status
_run2, _run3 = heading_runs.run_stage2, heading_runs.run_stage3


def fake(schema, content, what, **kw):  # 서식 정리 에이전트만 — 기본 스킬의 기준(레터)대로
    if what != "tpl-agent":
        return _call(schema, content, what, **kw)
    mat = json.loads(content.split("## 자료 (JSON)\\n```json\\n", 1)[1].rsplit("\\n```", 1)[0])["material"]
    levels = []
    for lv in mat["levels"]:
        gs = lv["groups"]
        rep = next((g for g in gs if g.get("currentRep")), gs[0])
        match, keep, cut = [], [], {}
        for g in gs:
            if g is rep:
                continue
            letter = next((d[2] for d in g.get("differsFromRep") or [] if d[0] == "레터"), None)
            if letter is None:
                match.append(g["id"])
            elif g.get("cannotSplit"):
                keep.append({"group": g["id"], "why": "레터가 다르지만 뗄 수 없음"})
            else:
                cut.setdefault(letter, []).append(g)
        split = []
        for letter, rows in cut.items():
            rows.sort(key=lambda g: -g["lines"])
            split.append({"rep": rows[0]["id"], "match": [g["id"] for g in rows[1:]], "why": f"레터 「{letter}」"})
        levels.append({"level": lv["level"], "rep": rep["id"], "match": match, "keep": keep, "split": split, "why": "가짜 — 기준대로"})
    return {"data": {"summary": "가짜 계획 — 레터가 같으면 맞추고 다르면 뗌", "levels": levels}, "backend": "api", "ms": 5, "costUsd": 0.0, "error": None,
            "model": kw.get("model"), "effort": kw.get("effort")}


def _judged(sess, key):  # 그 결과를 「LLM 판정을 거침」 으로만 적는다(판정은 스크립트 것 그대로)
    heading_runs.state(sess)[key]["llm"].update(requested=True, fallback=False, calls=1, failed=0, error=None, pending=0, pendingTables=[])   # pending 0 = 표의 보완 대상 없음(spec_작업 ② §22 「구현 계약」 22-4 — 남으면 「LLM 검증·보완」 이 표 단계를 다시 돈다)


def run2(sess, job, use_llm):
    n = _run2(sess, job, False)
    if use_llm:
        time.sleep(float(sys.argv[2]))  # 화면이 「멈추기」 를 누를 틈
        _judged(sess, "stage2")
    return n


def run3(sess, job, use_llm):
    n = _run3(sess, job, False)
    if use_llm:
        _judged(sess, "stage3")
    return n


llm.call = fake
llm.status = lambda: {**_status(), "available": True}  # 화면의 「LLM 연결」 확인만 통과(다른 호출은 꺼진 그대로)
heading_runs.run_stage2, heading_runs.run_stage3 = run2, run3
uvicorn.run("app.server:app", host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
''', encoding="utf-8")
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "PYTHONUTF8": "1", "PYTHONPATH": str(ROOT)}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", str(LAUNCH), str(args.port), "4"],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:900] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def run_stage(wid, stage):
    r = requests.post(f"{base}/api/docs/{wid}/headings", json={"stage": stage, "llm": False}, timeout=30)
    r.raise_for_status()
    for _ in range(600):
        j = requests.get(f"{base}/api/docs/{wid}/headings", timeout=30).json()
        if not (j.get("job") and j["job"]["status"] == "running"):
            return j
        time.sleep(.5)
    raise RuntimeError(f"{stage}단계가 끝나지 않음")


def status(wid):
    v = requests.get(f"{base}/api/docs/{wid}/analysis", timeout=60).json()
    by = {i["key"]: i for i in v["items"]}
    return v, by


META = """(box) => { // 상태 줄 — 실행 단추 둘의 자리
  const q = (s) => document.querySelector(s), pane = q(box === '#tablesOverview' ? '#paneTables' : '#paneHeads'), meta = q(box + ' .result-meta');
  if (!meta) return null;
  const inner = meta.getBoundingClientRect().right; // 상태 줄(패널 내용 폭을 다 쓰는 줄)의 오른쪽 끝 — 안쪽 여백을 주는 곳이 탭마다 달라(#paneHeads · #tablesBox) 줄 자체로 잰다
  const btns = [...meta.querySelectorAll('.hrun-all, .hrun-menu')].map((b) => { const r = b.getBoundingClientRect();
    return { all: b.classList.contains('hrun-all'), text: b.textContent, title: b.title, off: b.disabled, on: b.classList.contains('on'), left: r.left, right: r.right, top: Math.round(r.top), h: Math.round(r.height),
      bg: getComputedStyle(b).backgroundColor }; });
  return { btns, inner, metaTop: Math.round(meta.getBoundingClientRect().top), metaH: Math.round(meta.getBoundingClientRect().height), overflowX: pane.scrollWidth - pane.clientWidth };
}"""
ADJ = """() => [...document.querySelectorAll('#headsOverview .hprog [data-tpb]')].map((b) => ({ key: b.dataset.tpb, state: b.dataset.state, hidden: b.hidden,
  text: b.hidden ? '' : b.querySelector('.hprog-text').textContent }))"""
MENU_OPEN = "() => { const m = document.querySelector('.ctx-menu[data-by=\"hrp\"]'); return !!m && !m.hidden && !!m.querySelector('.hrp-row'); }"
MENU = """() => { // 「단계별 실행 ▾」 의 고르기 목록 — 줄(고름 · 꺼짐 · 상태) · 아래 단추 둘
  const m = document.querySelector('.ctx-menu[data-by="hrp"]'), go = m.querySelector('.hrp-go');
  return { rows: [...m.querySelectorAll('.hrp-row')].map((b) => ({ key: b.dataset.hrp, name: b.querySelector('.hrp-name').textContent, on: b.getAttribute('aria-checked') === 'true', off: b.disabled,
      state: b.dataset.state, note: b.querySelector('.hrp-note').textContent, role: b.getAttribute('role') })),
    go: { text: go.textContent, off: go.disabled, stop: go.classList.contains('stop') }, detail: m.querySelector('.hrp-detail').textContent };
}"""
PICK_IDLE = "() => typeof HRP === 'object' && !HRP.run"
PICK = """(keys) => { // 메뉴가 열린 채 — 고른 것을 비우고 그 줄들을 누른다
  const m = document.querySelector('.ctx-menu[data-by="hrp"]');
  for (const b of m.querySelectorAll('.hrp-row[aria-checked="true"]')) b.click();
  for (const k of keys) m.querySelector(`[data-hrp="${k}"]`).click();
}"""
QUEUED = "() => [...document.querySelectorAll('#headsOverview .hprog .hprog-step[data-queued]')].map((b) => b.querySelector('.hprog-text').textContent)"
IDLE = "() => typeof HRA === 'object' && !HRA.run"
TOAST = "() => document.getElementById('toast').textContent"

try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    r = requests.post(f"{base}/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}, timeout=120)
    r.raise_for_status()
    wid = r.json()["docId"]
    run_stage(wid, 2)
    run_stage(wid, 3)
    r = requests.post(f"{base}/api/docs", files={"file": (OTHER.name, OTHER.read_bytes(), "application/octet-stream")}, timeout=120)  # ⑨ 의 「다른 문서」
    r.raise_for_status()
    wid2 = r.json()["docId"]
    v0, by0 = status(wid)
    need0 = by0["formats"]["llm"]["need"]
    check("처음: 헤딩 · 표 LLM 안 함 · 정리할 템플릿이 있고 계획은 없음 · 돌 것 셋", by0["heads"]["llm"]["state"] == "none" and by0["tables"]["llm"]["state"] == "none" and need0 >= 1
          and by0["formats"]["llm"]["planned"] == 0 and [p["run"] for p in v0["llmPlan"]] == [True] * 3, (by0["heads"]["llm"], by0["formats"]["llm"], v0["llmPlan"]))
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        asked, accept = [], [False]
        page.on("dialog", lambda d: (asked.append(d.message), d.accept() if accept[0] else d.dismiss()))
        posts, full = [], []  # 바꾸는 요청 — 끝점만 · 문서 id 까지(「<id>/outline/agent/apply」)
        page.on("request", lambda q: posts.append(q.url.split("/api/docs/")[-1].split("/", 1)[-1]) if q.method in ("POST", "DELETE") and "/api/docs/" in q.url else None)
        page.on("request", lambda q: full.append(q.url.split("/api/docs/")[-1]) if q.method in ("POST", "DELETE") and "/api/docs/" in q.url else None)
        hbody = []  # POST …/headings 의 본문(단계 · LLM) — 「단계별 실행」 이 고른 것만 그 차례로 보내는지(⑩)
        page.on("request", lambda q: hbody.append(json.loads(q.post_data or "{}")) if q.method == "POST" and q.url.endswith("/headings") else None)
        page.goto(f"{base}/#w={wid}")
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=240000)
        page.click("#tabHeads")
        page.wait_for_function("() => typeof heads !== 'undefined' && heads.view && heads.view.stage3 && !(heads.view.job && heads.view.job.status === 'running') && document.querySelector('#headsOverview .hrun-all')", timeout=120000)
        page.wait_for_function("() => { const b = document.querySelector('#headsOverview .hprog [data-tpb=\"act\"]'); return b && !b.hidden; }", timeout=30000)

        # ---- ① 상태 줄 — 「전체 실행」 · 「단계별 실행 ▾」
        m = page.evaluate(META, "#headsOverview")
        b = m["btns"]
        check("상태 줄 끝에 단추 둘: 「전체 실행」 · 「단계별 실행 ▾」(이 차례)", [(x["all"], x["text"]) for x in b] == [(True, "전체 실행"), (False, "단계별 실행 ▾")], b)
        check("둘이 같은 줄 · 26px · 붙어 있고(사이 ≤ 6px) 오른쪽 끝", len(b) == 2 and b[0]["top"] == b[1]["top"] and [x["h"] for x in b] == [26, 26] and 0 <= b[1]["left"] - b[0]["right"] <= 6
              and abs(b[1]["right"] - m["inner"]) <= 1.5 and m["metaH"] <= 28, (b, m["inner"], m["metaH"]))
        check("「전체 실행」 은 파란 바탕(주 단추) · 「단계별 실행 ▾」 은 흰 바탕 · 둘 다 켜짐", len(b) == 2 and b[0]["bg"] != b[1]["bg"] and b[1]["bg"] == "rgb(255, 255, 255)" and not b[0]["off"] and not b[1]["off"], b)
        check("「전체 실행」 title: 조정까지 · 유료 · 문서가 바뀜 · 단계별 실행과의 차이", len(b) == 2 and all(w in b[0]["title"] for w in ("조정", "유료", "문서가 바뀝니다", "단계별 실행")), b[0]["title"] if b else "")
        page.locator("#headsOverview").screenshot(path=str(OUT / "1_buttons.png"))

        # ---- ② 「단계별 실행 ▾」 = 고르기 목록(heads_run_pick.js — 2026-11-17 「클릭한 다음에 클릭한 것들만 실행」): 항목을 눌러도 돌지 않고 표시만 · 「고른 n개 실행」 이 돌린다
        n_pick = len(posts)
        page.click("#headsOverview .hrun-menu")
        page.wait_for_function(MENU_OPEN, timeout=5000)
        mn = page.evaluate(MENU)
        names = [x["name"] for x in mn["rows"]]
        check("메뉴: 고르기 줄 여섯(스크립트 셋 · LLM 셋 — 모두 안 고름) · 아래 「돌릴 단계를 고르세요」(꺼짐) · 「추출·설정에서 자세히」", [t.split(" — ")[0] for t in names] == ["스크립트"] * 3 + ["LLM"] * 3
              and any("헤딩 판정" in t for t in names) and any("표 판정" in t for t in names) and not any(x["on"] for x in mn["rows"])
              and mn["go"] == {"text": "돌릴 단계를 고르세요", "off": True, "stop": False} and mn["detail"] == "추출·설정에서 자세히", mn)
        page.click(".ctx-menu[data-by='hrp'] [data-hrp='s2']")
        page.click(".ctx-menu[data-by='hrp'] [data-hrp='l3']")
        m2 = page.evaluate(MENU)
        check("두 줄을 누르면: 메뉴는 열린 채 두 줄에 표시 · 「고른 2개 실행」 켜짐 · 아무것도 돌지 않음(요청 없음)", [x["key"] for x in m2["rows"] if x["on"]] == ["s2", "l3"]
              and m2["go"] == {"text": "고른 2개 실행", "off": False, "stop": False} and posts[n_pick:] == [] and page.evaluate(PICK_IDLE), (m2, posts[n_pick:]))
        page.screenshot(path=str(OUT / "2_stage_menu.png"))
        page.click(".ctx-menu[data-by='hrp'] [data-hrp='s2']")
        m3 = page.evaluate(MENU)
        check("다시 누르면 빠짐: 「고른 1개 실행」", [x["key"] for x in m3["rows"] if x["on"]] == ["l3"] and m3["go"]["text"] == "고른 1개 실행", m3)
        page.click(".ctx-menu[data-by='hrp'] [data-hrp='l3']")
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        check("Esc 로 닫힘 · 고르기만으로는 요청 없음", not page.evaluate(MENU_OPEN) and posts[n_pick:] == [], posts[n_pick:])

        # ---- ③ 「테이블」 탭 — 「단계별 실행 ▾」 만
        page.click("#tabTables")
        page.wait_for_function("() => document.querySelector('#tablesOverview .hrun-menu')", timeout=60000)
        mt = page.evaluate(META, "#tablesOverview")
        check("「테이블」 탭: 「단계별 실행 ▾」 만(「전체 실행」 은 조정 층이 있는 헤딩 추출 탭에만) · 오른쪽 끝", [(x["all"], x["text"]) for x in mt["btns"]] == [(False, "단계별 실행 ▾")]
              and abs(mt["btns"][0]["right"] - mt["inner"]) <= 1.5, (mt["btns"], mt["inner"]))
        page.click("#tabHeads")
        page.wait_for_function("() => document.querySelector('#headsOverview .hrun-all')", timeout=30000)

        # ---- ④ 확인 창 없음(2026-11-18 사용자 「이런 알람좀 주지마」 — 전에는 돌 것을 적은 확인 창 · 「취소」 면 아무것도 안 돎)
        n0 = len(posts)


        # ---- ⑤ 누르면 바로 → 도는 동안 「멈추기」 · 진행 카드 → 멈추기: 반영하지 않음
        accept[0] = True
        undo0 = page.evaluate("() => state.undo || 0")
        page.click("#headsOverview .hrun-all")
        page.wait_for_function("() => { const b = document.querySelector('#headsOverview .hrun-all'); return b && b.textContent === '멈추기' && heads.view && heads.view.job && heads.view.job.status === 'running' && heads.view.job.chain === 'llm'; }", timeout=30000)
        live = page.evaluate("() => { const R = agwRunning(); return R && { kind: R.kind, label: R.label, stop: typeof R.stop }; }")
        check("확인 창 없이 바로 돎 · 도는 동안: 에이전트 진행 카드에 「전체 실행」(agwRunning kind headsAll · 멈춤 있음)", not asked and bool(live) and live["kind"] == "headsAll" and "전체 실행" in live["label"] and live["stop"] == "function", live)
        page.click("#headsOverview .hrun-menu")
        page.wait_for_function(MENU_OPEN, timeout=5000)
        mr = page.evaluate(MENU)
        check("도는 동안: 「단계별 실행」 메뉴의 고르기 줄은 꺼짐 · 「다른 헤딩 작업이 도는 중」(꺼짐) · 「추출·설정에서 진행 보기」", len(mr["rows"]) == 6 and all(x["off"] for x in mr["rows"])
              and mr["go"] == {"text": "다른 헤딩 작업이 도는 중", "off": True, "stop": False} and mr["detail"] == "추출·설정에서 진행 보기", mr)
        page.keyboard.press("Escape")
        page.locator("#paneHeads").screenshot(path=str(OUT / "5_running.png"))
        page.click("#headsOverview .hrun-all")
        page.wait_for_function(IDLE, timeout=120000)
        page.wait_for_timeout(600)
        v1, by1 = status(wid)
        t1 = page.evaluate(TOAST)
        check("멈추기: 이어 돌리기를 멈춤(DELETE …/analysis/llm) · 반영 요청 없음 · 실행 취소 수 그대로", posts[n0:].count("analysis/llm") == 2 and "outline/agent/apply" not in posts[n0:]
              and page.evaluate("() => state.undo || 0") == undo0, (posts[n0:], undo0))
        check("멈춘 뒤: 헤딩은 LLM 판정을 거침(도는 단계는 마침) · 표 · 서식은 남음", by1["heads"]["llm"]["state"] == "done" and by1["tables"]["llm"]["state"] != "done" and by1["formats"]["llm"]["planned"] == 0,
              (by1["heads"]["llm"], by1["tables"]["llm"], by1["formats"]["llm"]))
        check("멈춘 글: 「전체 실행 멈춤」 · 한 것(헤딩 · 템플릿) · 남은 것(표 · 계획을 받지 않은 템플릿)", t1.startswith("전체 실행 멈춤 — 멈추기를 눌러") and "한 것: LLM 헤딩 · 템플릿" in t1 and "남은 것:" in t1
              and "LLM 판정을 안 한 단계 표" in t1 and "계획을 받지 않은 템플릿" in t1, t1)
        last = page.evaluate("() => document.querySelector('#headsOverview .hrun-all').title")
        check("단추가 「전체 실행」 으로 돌아옴 · title 에 지난 실행", page.evaluate(META, "#headsOverview")["btns"][0]["text"] == "전체 실행" and "지난 전체 실행: 전체 실행 멈춤" in last, last[-200:])

        # ---- ⑥ 다시 「전체 실행」 — 거친 단계는 건너뛰고 표 · 서식 계획 → 조정까지
        n1, a1 = len(posts), len(asked)
        rev1 = page.evaluate("() => state.serverRev")
        page.click("#headsOverview .hrun-all")
        page.wait_for_function("() => typeof HRA === 'object' && !!HRA.run", timeout=30000)
        page.wait_for_function(IDLE, timeout=300000)
        page.wait_for_timeout(800)
        check("둘째 「전체 실행」 도 확인 창 없이 바로", len(asked) == a1, asked[a1:])
        seq = posts[n1:]
        chains, applies = seq.count("analysis/llm"), seq.count("outline/agent/apply")
        check("차례: LLM 이어 돌리기 → 반영(반영은 늘 계획을 받은 뒤 · 각각 세 번까지)", 1 <= chains <= 3 and 1 <= applies <= 3 and seq and seq[0] == "analysis/llm" and "outline/agent/apply" in seq
              and seq.index("outline/agent/apply") > 0, seq)
        v2, by2 = status(wid)
        L2 = by2["formats"]["llm"]
        check("끝: 헤딩 · 표 LLM 판정을 거침 · 반영하지 않은 계획 없음 · 반영한 계획이 있음", by2["heads"]["llm"]["state"] == "done" and by2["tables"]["llm"]["state"] == "done" and L2["planned"] == 0 and L2["done"] >= 1,
              (by2["tables"]["llm"], {k: L2[k] for k in ("need", "planned", "applied", "done", "stale")}))
        st = page.evaluate("() => ({ undo: state.undo || 0, rev: state.serverRev, busy: !!state.busy })")
        undone = st["undo"] - undo0  # 문서를 바꾼 반영 수(떼기만 한 반영은 문서를 안 바꾼다 — 실행 취소가 안 는다)
        check("문서가 바뀜: 반영마다 실행 취소는 많아야 1 · 문서 차례가 오름 · 대표와 다른 줄이 줄어듦", 1 <= undone <= applies and st["rev"] > rev1 and not st["busy"] and by2["formats"]["others"] < by0["formats"]["others"],
              (st, undo0, applies, rev1, by2["formats"]["others"], by0["formats"]["others"]))
        t2 = page.evaluate(TOAST)
        left2 = [x for x in L2["list"] if x["state"] in ("none", "stale")]
        check("끝난 글: 「전체 실행 끝」 · 한 것(LLM 표 · 서식 계획 → 조정 — 템플릿 n개 반영) · 실행 취소 · 남은 것", t2.startswith("전체 실행 끝 — LLM 표") and "조정 — 템플릿" in t2 and "「실행 취소」" in t2
              and (("계획을 받지 않은 템플릿" in t2) if left2 else ("남은 것 없음" in t2)), (t2, left2))
        page.wait_for_function("() => { const b = document.querySelector('#headsOverview .hprog [data-tpb=\"tpl\"]'); return b && b.dataset.state === 'llm'; }", timeout=60000)
        adj = page.evaluate(ADJ)
        check("조정 층: 두 칸 ✓(반영함) · 행동 칸은 감춤(남은 템플릿이 있으면 「나머지 받기」)", [(x["key"], x["state"]) for x in adj[:2]] == [("tpl", "llm"), ("fmt", "llm")]
              and ((adj[2]["text"] == "나머지 받기") if left2 else adj[2]["hidden"]), (adj, left2))
        m = page.evaluate(META, "#headsOverview")
        check("단추가 「전체 실행」 으로 돌아옴 · 켜짐", m["btns"][0]["text"] == "전체 실행" and not m["btns"][0]["off"] and not m["btns"][0]["on"], m["btns"])
        page.locator("#paneHeads").screenshot(path=str(OUT / "6_done.png"))

        # ---- ⑦ 남은 것이 없으면 묻지 않고 알림만
        if not left2:
            n2, a2 = len(posts), len(asked)
            page.click("#headsOverview .hrun-all")
            page.wait_for_function("() => document.getElementById('toast').textContent.startsWith('남은 단계가 없습니다')", timeout=30000)
            check("남은 것이 없을 때: 확인 창 없이 「남은 단계가 없습니다」 · 요청 없음", len(asked) == a2 and posts[n2:] == [] and page.evaluate(IDLE), (asked[a2:], posts[n2:]))

        # ---- 되풀이 한도(HRA_MAX) — 남은 것이 있는데 한도에 닿으면 「끝」 이 아니라 「멈춤 — 되풀이 한도」(6b · astra 검토: 까닭이 알림에 없었다). 분석 상태 사본에 받아 둔 계획을 흉내 — 요청은 안 나간다
        n3 = len(posts)
        cap = page.evaluate("""async () => {
          const v = await hraStatus(state.id), f = v.items.find((i) => i.key === 'formats');
          v.busy = false; v.llmPlan.forEach((p) => { p.run = false; });
          Object.assign(f.llm, { planned: 2, change: 5, moved: 1 });
          const R = { id: state.id, epoch: state.epoch, t0: Date.now(), note: '', stop: false, chains: 0, applies: HRA_MAX, sig: null, did: { llm: [], tpls: 0, lines: 0, splits: 0, undo: 0 }, left: [] };
          HRA.run = R;
          try { const out = await hraLoop(R, v); return { why: out.why, text: hraDone(R, out.why, out.v ? hraLeft(out.v) : null) }; }
          finally { HRA.run = null; hraSync(); }
        }""")
        check("되풀이 한도에 닿으면: 「전체 실행 멈춤 — 되풀이 한도(3번)」 · 남은 것(반영하지 않은 계획) · 요청 없음", "되풀이 한도(3번)" in cap["why"] and cap["text"].startswith("전체 실행 멈춤 — 되풀이 한도")
              and "반영하지 않은 계획 2개" in cap["text"] and posts[n3:] == [], (cap, posts[n3:]))

        # ---- 대표만 바꾸는 계획(맞출 줄 0 · 대표 변경 1)도 조정이 반영한다 · 반영한 계획이 남긴 줄은 반영한 뒤에도 알린다(2026-11-16 astra — 전에는 줄 수가 0 이면 조정을 안 돌렸고,
        #      반영하면 「그대로 둔 줄 · 답이 없어 안 바꾼 줄」 이 사라져 「남은 것 없음」 이라 했다). 분석 상태 사본에 그 수를 흉내 — 요청은 안 나간다
        n5 = len(posts)
        rep = page.evaluate("""async () => {
          const v = await hraStatus(state.id), f = v.items.find((i) => i.key === 'formats');
          v.busy = false; v.llmPlan.forEach((p) => { p.run = false; });
          v.items.find((i) => i.key === 'templates').hints = [];
          f.place = 0; f.noRep = 0;
          Object.assign(f.llm, { planned: 1, change: 0, moved: 0, reps: 1, kept: 0, unanswered: 0, omitted: 0, left: { kept: 0, unanswered: 0 } });
          const P = hraLeft(v), plain = hraLeft({ ...v, items: v.items.map((i) => (i.key === 'formats' ? { ...i, llm: { ...i.llm, reps: 0 } } : i)) });
          Object.assign(f.llm, { planned: 0, reps: 0, left: { kept: 2, unanswered: 5 } });
          const P2 = hraLeft(v), R = { did: { llm: [], tpls: 1, lines: 0, reps: 1, splits: 0, undo: 1 }, left: [] };
          return { apply: P.apply, none: plain.apply, idle: P2.apply, unseen: hraUnseen(P2), done: hraDone(R, '', P2) };
        }""")
        check("대표만 바꾸는 계획: 「맞출 줄 0 · 대표 변경 1」 도 반영할 것(대표 변경이 없으면 아님) · 끝난 글에 「맞춘 줄 0 · 대표 변경 1」",
              rep["apply"] is True and rep["none"] is False and "맞춘 줄 0 · 대표 변경 1" in rep["done"] and posts[n5:] == [], rep)
        check("반영한 계획이 남긴 줄: 반영한 뒤에도 남은 것으로 알림(그대로 둔 줄 2 · 답이 없어 안 바꾼 줄 5) — 「남은 것 없음」 이 아니다",
              rep["idle"] is False and any("그대로 둔 줄 2 · 답이 없어 안 바꾼 줄 5" in x for x in rep["unseen"]) and "반영한 계획이 남긴 것" in rep["done"] and "남은 것 없음" not in rep["done"], rep)

        # ---- 실행 취소 — 반영한 만큼 되돌리면 올린 파일 그대로
        for _ in range(undone):
            requests.post(f"{base}/api/docs/{wid}/undo", timeout=120).raise_for_status()
        same = requests.get(f"{base}/api/docs/{wid}/download", timeout=120).content == PLAN.read_bytes()
        check(f"실행 취소 {undone}번이면 문서가 처음 그대로(내려받은 파일 = 올린 파일) · 끝난 글의 실행 취소 수와 같음", same and (f"「실행 취소」 {undone}번" in t2 if undone > 1 else "「실행 취소」 한 번" in t2), (same, undone, t2))

        # ---- ⑧ 좁은 패널
        page.reload()
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=240000)
        page.click("#tabHeads")
        page.wait_for_function("() => document.querySelector('#headsOverview .hrun-all') && typeof dsState === 'object' && dsState.main", timeout=120000)
        for w in (320, 388, 480):
            page.evaluate("(w) => { document.getElementById('panel').style.setProperty('--panel', w + 'px'); heads.summaryKey = null; headsResultsSummary(heads.view); }", w)
            page.wait_for_timeout(200)
            m = page.evaluate(META, "#headsOverview")
            b = m["btns"]
            check(f"[{w}] 단추 둘이 같은 줄 · 패널 밖으로 안 나감 · 가로 넘침 없음", len(b) == 2 and b[0]["top"] == b[1]["top"] and b[1]["right"] <= m["inner"] + 1.5 and m["overflowX"] <= 0,
                  ([(x["text"], round(x["left"]), round(x["right"]), x["top"]) for x in b], m["inner"], m["overflowX"]))
            page.locator("#paneHeads").screenshot(path=str(OUT / f"8_panel_{w}.png"))

        # ---- ⑩ 「단계별 실행」 — 고른 것만 차례로(heads_run_pick.js): 확인 창 없이(2026-11-18) · 도는 동안 차례 · 멈추기 · LLM 이 답을 못 하면 뒤는 남김 · 스크립트만이면 묻지 않음
        page.evaluate("() => { document.getElementById('panel').style.removeProperty('--panel'); heads.summaryKey = null; headsResultsSummary(heads.view); }")
        page.wait_for_function("() => heads.view && !(heads.view.job && heads.view.job.status === 'running') && !state.busy", timeout=120000)  # 문서가 바뀐 뒤 저절로 도는 1단계 다시 추출이 끝난 뒤에
        page.wait_for_timeout(300)

        def pick(keys, box="#headsOverview"):  # 메뉴를 열고 그 줄들을 고른 뒤 「고른 n개 실행」 을 누른다 → 누르기 전의 아래 단추
            page.click(f"{box} .hrun-menu")
            page.wait_for_function(MENU_OPEN, timeout=5000)
            page.evaluate(PICK, keys)
            go = page.evaluate(MENU)["go"]
            page.click(".ctx-menu[data-by='hrp'] .hrp-go")
            return go

        def sent(i):  # 그 뒤로 보낸 POST …/headings 의 (단계, LLM)
            return [(b.get("stage"), b.get("llm")) for b in hbody[i:]]

        n6, a6, h6 = len(posts), len(asked), len(hbody)
        go = pick(["l3", "s2", "l2"])  # 누른 차례와 달라도 도는 차례는 진행 줄의 차례(스크립트 → LLM) · 확인 창 없이 바로(2026-11-18)
        check("「고른 3개 실행」 — 확인 창 없이 바로 돎", go["text"] == "고른 3개 실행" and len(asked) == a6, (go, asked[a6:]))
        page.wait_for_function("() => HRP.run && HRP.run.i === 1 && heads.view.job && heads.view.job.status === 'running' && heads.view.job.llm", timeout=120000)  # 둘째(LLM 헤딩 판정 — 가짜가 몇 초 쉰다)
        live = page.evaluate("""() => { const R = agwRunning(), b = document.querySelector('#headsOverview .hrun-menu'), all = document.querySelector('#headsOverview .hrun-all');
          return { kind: R && R.kind, label: R && R.label, stop: R && typeof R.stop, btn: b.textContent, on: b.classList.contains('on'), allOff: all.disabled }; }""")
        check("도는 동안: 단추 「단계별 실행 2/3 ▾」 · 「전체 실행」 꺼짐 · 에이전트 진행 카드(agwRunning kind headsPick · 멈춤 있음)", live["btn"] == "단계별 실행 2/3 ▾" and live["on"] and live["allOff"]
              and live["kind"] == "headsPick" and "고른 3개를 차례로" in (live["label"] or "") and live["stop"] == "function", live)
        q = page.evaluate(QUEUED)
        check("진행 줄: 차례를 기다리는 칸(표 판정)만 점선 표시", q == ["표 판정"], q)
        page.click("#headsOverview .hrun-menu")
        page.wait_for_function(MENU_OPEN, timeout=5000)
        mrun = page.evaluate(MENU)
        page.screenshot(path=str(OUT / "10_pick_running.png"))
        page.keyboard.press("Escape")
        check("도는 동안 메뉴: 고른 셋의 차례(끝남 · 도는 중 · 기다림) · 줄은 모두 꺼짐 · 「멈추기」", {x["key"]: x["state"] for x in mrun["rows"]} == {"s1": "", "s2": "done", "s3": "", "l1": "", "l2": "running", "l3": "wait"}
              and all(x["off"] for x in mrun["rows"]) and [x["note"] for x in mrun["rows"] if x["state"]] == ["끝남", "도는 중", "기다림"] and mrun["go"] == {"text": "멈추기", "off": False, "stop": True}, mrun)
        page.wait_for_function(PICK_IDLE, timeout=300000)
        page.wait_for_timeout(600)
        t6 = page.evaluate(TOAST)
        check("끝난 글: 「단계별 실행 끝 — 스크립트 헤딩 그래프 → LLM 헤딩 판정 · 서식 계획 → LLM 표 판정」", t6.startswith("단계별 실행 끝 — 스크립트 헤딩 그래프 → LLM 헤딩 판정 · 서식 계획 → LLM 표 판정"), t6)
        check("보낸 것: 고른 셋만 · 그 차례(헤딩 그래프 스크립트 → 헤딩 그래프 LLM → 표 구조 LLM) · 확인 창 없음", sent(h6) == [(2, False), (2, True), (3, True)] and len(asked) == a6
              and posts[n6:] == ["headings"] * 3, (sent(h6), posts[n6:], len(asked) - a6))
        aft = page.evaluate("""() => { const b = document.querySelector('#headsOverview .hrun-menu');
          return { btn: b.textContent, on: b.classList.contains('on'), title: b.title, s2: headsSource(heads.view, 2).llm, s3: headsSource(heads.view, 3).llm,
            queued: document.querySelectorAll('#headsOverview .hprog-step[data-queued]').length, allOff: document.querySelector('#headsOverview .hrun-all').disabled }; }""")
        check("끝난 뒤: 단추 「단계별 실행 ▾」 · title 에 지난 실행 · 헤딩 · 표가 LLM 판정을 거침 · 기다림 표시 없음 · 「전체 실행」 켜짐", aft["btn"] == "단계별 실행 ▾" and not aft["on"]
              and "지난 단계별 실행: 단계별 실행 끝" in aft["title"] and aft["s2"] and aft["s3"] and aft["queued"] == 0 and not aft["allOff"], aft)

        # 멈추기 — 지금 도는 단계가 끝나면 멈추고 뒤는 돌리지 않는다(남긴다)
        n7, h7 = len(posts), len(hbody)
        pick(["l2", "l3"])
        page.wait_for_function("() => HRP.run && heads.view.job && heads.view.job.status === 'running' && heads.view.job.chain === 'heads'", timeout=120000)
        page.click("#headsOverview .hrun-menu")
        page.wait_for_function(MENU_OPEN, timeout=5000)
        page.click(".ctx-menu[data-by='hrp'] .hrp-go")  # 「멈추기」
        stopping = page.evaluate(MENU)["go"]
        page.keyboard.press("Escape")
        page.wait_for_function(PICK_IDLE, timeout=300000)
        page.wait_for_timeout(600)
        t7 = page.evaluate(TOAST)
        check("멈추기: 단추는 「멈추는 중…」 → 「단계별 실행 멈춤 — 멈추기를 눌러」 · 한 것(LLM 헤딩 판정) · 돌리지 않은 것(LLM 표 판정) · 표 판정 요청 없음", stopping == {"text": "멈추는 중…", "off": True, "stop": True}
              and t7.startswith("단계별 실행 멈춤 — 멈추기를 눌러 멈췄습니다") and "한 것: LLM 헤딩 판정 · 서식 계획" in t7 and "돌리지 않은 것: LLM 표 판정" in t7
              and sent(h7) == [(2, True)] and posts[n7:] == ["headings", "analysis/llm"], (stopping, t7, sent(h7), posts[n7:]))

        # LLM 이 답을 못 하면(규칙 보강 — 임시 서버의 LLM 은 꺼져 있다) 멈추고 뒤 LLM 단계는 돌리지 않는다. 판정하지 못한 묶음이 있는 문서에서만
        page.wait_for_function("() => !(heads.view.job && heads.view.job.status === 'running')", timeout=120000)
        page.click("#headsOverview .hrun-menu")
        page.wait_for_function(MENU_OPEN, timeout=5000)
        l1 = next(x for x in page.evaluate(MENU)["rows"] if x["key"] == "l1")
        page.keyboard.press("Escape")
        if not l1["off"]:
            h8 = len(hbody)
            pick(["l1", "l3"])
            page.wait_for_function("() => !!HRP.run", timeout=30000)
            page.wait_for_function(PICK_IDLE, timeout=300000)
            page.wait_for_timeout(600)
            t8 = page.evaluate(TOAST)
            check("LLM 이 답을 못 하면: 「단계별 실행 멈춤 — 「LLM 규칙 보강」 …」 · 돌리지 않은 것(LLM 표 판정) · 표 판정 요청 없음", t8.startswith("단계별 실행 멈춤 — 「LLM 규칙 보강」") and "돌리지 않은 것: LLM 표 판정" in t8
                  and sent(h8) == [(1, True)], (t8, sent(h8)))
        else:
            print("SKIP LLM 이 답을 못 하는 경우 — 이 문서에는 판정하지 못한 묶음이 없어 「규칙 보강」 이 꺼져 있음", flush=True)

        # 「테이블」 탭 — 줄 둘 · 스크립트만 고르면 확인 창 없이 바로
        page.click("#tabTables")
        page.wait_for_function("() => document.querySelector('#tablesOverview .hrun-menu') && !(heads.view.job && heads.view.job.status === 'running')", timeout=60000)
        a9, h9 = len(asked), len(hbody)
        page.click("#tablesOverview .hrun-menu")
        page.wait_for_function(MENU_OPEN, timeout=5000)
        mt2 = page.evaluate(MENU)
        page.keyboard.press("Escape")
        check("「테이블」 탭 메뉴: 고르기 줄 둘(표 구조 만들기 · 표 판정)", [x["key"] for x in mt2["rows"]] == ["s3", "l3"] and mt2["go"]["text"] == "돌릴 단계를 고르세요", mt2)
        pick(["s3"], "#tablesOverview")
        for _ in range(100):
            if len(hbody) > h9:
                break
            page.wait_for_timeout(100)
        page.wait_for_function(PICK_IDLE, timeout=120000)
        page.wait_for_timeout(600)
        t9 = page.evaluate(TOAST)
        check("스크립트만 고르면: 확인 창 없이 바로 돎 · 끝난 글 「단계별 실행 끝 — 스크립트 표 구조」", len(asked) == a9 and sent(h9) == [(3, False)] and t9.startswith("단계별 실행 끝 — 스크립트 표 구조"), (len(asked) - a9, sent(h9), t9))
        page.click("#tabHeads")
        page.wait_for_function("() => document.querySelector('#headsOverview .hrun-all') && !(heads.view.job && heads.view.job.status === 'running')", timeout=60000)

        # ---- ⑨ 반영이 대기 중 글 반영(flushAll)을 기다리는 사이 다른 문서를 열면 — 그 문서로 보내지 않는다(app.js structOp — 6b · astra 검토: 주소를 기다린 뒤의 state.id 로 만들었다)
        n4 = len(full)
        got = page.evaluate("""async (other) => {
          const real = flushAll;
          let release;
          window.flushAll = async () => { await new Promise((r) => { release = r; }); return real(); };
          try {
            const p = structOp('outline/agent/apply', { rev: state.serverRev }); // 「모두 반영」 과 같은 요청 — flushAll 을 기다리는 데서 선다
            await openWork(other);                                               // 그 사이 다른 문서를 연다
            const switched = state.id === other;
            release();
            return { switched, result: await p };
          } finally { window.flushAll = real; }
        }""", wid2)
        page.wait_for_timeout(500)
        sent = [u for u in full[n4:] if u.endswith("outline/agent/apply")]
        check("반영을 기다리는 사이 다른 문서를 열면: 반영 요청을 어느 문서로도 보내지 않음(structOp 는 null)", got["switched"] and got["result"] is None and sent == [], (got, sent))
        check("콘솔·페이지 오류 없음", not errors, " | ".join(errors[:3]))
        browser.close()
except Exception as e:  # noqa: BLE001
    check(f"실행 오류: {type(e).__name__}", False, e)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()

print(f"\n{'모두 통과' if not fails else '실패 ' + str(len(fails))}")
sys.exit(1 if fails else 0)

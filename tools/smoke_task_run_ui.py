"""1단계 「문서 프레임 작성」(구조) · 2단계 「내용 매핑」 묶음 · 묶음마다 「한 번에 진행」(spec_작업 ② §14) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_task_run_ui.py <그림·임시 폴더> [--port 18164]

① 묶음 모양(작은 문서 둘): 접힌 상자 · 끝난 수 · 상태 줄 · 펴고 접기 · 준비가 안 끝나면 단추 꺼짐 · 값이 없으면 멈추고 세부 목록이 펴짐.
② 실제 서식 쌍(연구개발계획서 양식 → 연차보고서 서식 — 저장소 samples): 1단계 「한 번에 진행」 = 구분 기준 반영까지만(내용은 안 넣음), 2단계 「한 번에 진행」 = 헤딩·표 분석 → 자리 연결
   (LLM 검토는 가짜 응답) → 넣기 계획 → 내용 반영. 확인 창은 누를 때마다 한 번뿐. 서버는 진짜(LLM 만 끔) — 4~8분."""
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
PLAN_FORM = ROOT / "samples" / "연구개발계획서_양식.hwpx"
REPORT_FORM = ROOT / "samples" / "국가RnD_서식" / "KEIT_표준서식_260320" / "1. 산업기술혁신사업 연차보고서 서식_260319.hwpx"
VALUES = {"stages": [2], "orgs": {"lead": "인텍", "joint": ["가나대", "다라연"], "nonprofit": [False, True, False]}}  # tests/merge_data.py SMALL_VALUES 와 같은 꼴(당해 차년도는 기본값)
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18164)
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
errors, fails, dialogs = [], [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:500] if detail != "" else ""), flush=True)
    if not ok:
        fails.append(name)


def upload(path):
    return requests.post(f"{base}/api/docs?new=1", files={"file": (path.name, path.read_bytes())}, timeout=300).json()["docId"]


def task(wid, **t):
    r = requests.put(f"{base}/api/works/{wid}/task", json={"kind": "rnd", "file": "", "job": "plan_to_report", "project": "", **t}, timeout=30)
    r.raise_for_status()


def open_work(page, wid):
    page.evaluate("(id) => { location.hash = '#w=' + id; }", wid)
    page.reload()
    page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=wid, timeout=300000)


VIS = "(id) => { const e = document.getElementById(id); return !!e && !e.hidden && e.getClientRects().length > 0 && e.checkVisibility(); }"  # 접힌 details 안은 getClientRects 가 남는다(content-visibility) — checkVisibility 까지
STEPS = """() => [...document.querySelectorAll('#taskSteps li')].map((li) => ({ step: li.dataset.step, state: li.dataset.state,
  status: li.dataset.status, badge: li.querySelector('.dv-flow-status').textContent, no: li.querySelector('.dv-flow-no').textContent, text: li.textContent }))"""
# 묶음 머리 — 펴짐 · 끝난 수 · 상태 줄(종류·글·동그라미) · 단추(글·꺼짐·강조)
STAGE = """() => { const b = document.getElementById('taskStage'); if (!b) return null; const st = b.querySelector('.dv-phase-state'), run = b.querySelector('[data-task-run]');
  const progress = b.querySelector('.dv-phase-progress');
  return { open: b.open, count: b.querySelector('.dv-phase-count').textContent, progress: [progress.value, progress.max], kind: st.dataset.kind, text: st.lastChild.textContent, spin: !st.firstChild.hidden,
    btn: run.textContent, disabled: run.disabled, primary: run.classList.contains('primary'), head: b.querySelector('summary').textContent }; }"""
STAGE2 = STAGE.replace("'taskStage'", "'taskStage2'")  # 2단계 「내용 매핑」 묶음
OLVIS = "(id) => { const e = document.querySelector('#' + id + ' ol.dv-flow-steps'); return !!e && e.checkVisibility(); }"  # 그 묶음의 세부 목록이 보이나(접힌 details 안은 안 보임)

try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    small = ROOT / "samples" / "기술수요조사서.hwpx"
    a, c = upload(small), upload(small)   # a = 연차보고서 칸 · c = 사업계획서 칸(국가R&D 양식이 아니라 값이 없다)
    task(a, file="report")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)

        def on_dialog(d):
            dialogs.append(d.message)
            d.accept()
        page.on("dialog", on_dialog)
        page.goto(base)
        page.evaluate("() => { try { localStorage.clear(); } catch {} }")
        open_work(page, a)
        page.click("#taskHome")
        page.wait_for_selector("#taskStage")

        # ---- 1. 묶음 모양 — 접힌 상자 · 머리 줄 · 상태 줄 · 준비가 안 끝나면 단추 꺼짐
        labels = page.eval_on_selector_all("#divBox .dv-task-field > span", "xs => xs.map(x => x.textContent)")
        check("첫 카드에 「작업」 칸 없음(패널 머리에만) — 할 일 · 과제", labels == ["할 일", "과제"] and page.locator("#divBox .dv-task select[data-task=kind]").count() == 0
              and page.input_value("#panelTask") == "rnd", labels)
        s = page.evaluate(STAGE)
        check("묶음 = 접힌 상자 · 「1단계 문서 프레임 작성」 · 0/1 완료와 진행률 · 세부 목록은 안 보임", s["open"] is False and "1단계" in s["head"] and "문서 프레임 작성" in s["head"] and s["count"] == "0/1 완료" and s["progress"] == [0, 1]
              and not page.evaluate(OLVIS, "taskStage"), s)
        s2 = page.evaluate(STAGE2)
        map_note = page.get_attribute("#taskStage2 > summary .panel-help", "data-help")
        check("둘째 묶음 = 「2단계 내용 매핑」 · 0/3 완료 · 선행조건은 표시하고 상세 설명은 노트 · 단추 꺼짐", s2["open"] is False and "2단계" in s2["head"] and "내용 매핑" in s2["head"]
              and s2["count"] == "0/3 완료" and s2["progress"] == [0, 3] and s2["text"] == "1단계 「문서 프레임 작성」 완료 후 진행" and "헤딩·표 분석" in map_note and "내용 반영" in map_note
              and s2["disabled"] and not s2["primary"] and not page.evaluate(OLVIS, "taskStage2"), s2)
        check("준비가 안 끝남 — 상태 줄 「다음: 준비 …」 · 단추 꺼짐", s["kind"] == "next" and s["text"].startswith("다음: 준비") and "사업계획서" in s["text"] and s["btn"] == "한 번에 진행"
              and s["disabled"] and not s["primary"] and not s["spin"], s)
        page.click("#taskStage > summary strong")
        page.wait_for_function("() => localStorage.getItem('nfm.taskStageOpen') === '1'")  # toggle 사건은 한 박자 뒤에 온다
        s = page.evaluate(STAGE)
        check("머리 줄을 누르면 펴짐 — 세부 목록(이 묶음 두 줄 · 두 묶음 합쳐 여섯 줄) · 이 브라우저에 기억 · 둘째 묶음은 접힌 채", s["open"] and page.evaluate(OLVIS, "taskStage") and not page.evaluate(OLVIS, "taskStage2")
              and len(page.evaluate(STEPS)) == 6 and page.locator("#taskStage ol.dv-flow-steps > li").count() == 2 and page.locator("#taskStage2 ol.dv-flow-steps > li").count() == 4
              and page.evaluate("() => localStorage.getItem('nfm.taskStageOpen')") == "1", s)
        page.click("#taskStage > summary strong")
        page.wait_for_function("() => localStorage.getItem('nfm.taskStageOpen') === '0'")
        check("다시 누르면 접힘", page.evaluate(STAGE)["open"] is False and page.evaluate("() => localStorage.getItem('nfm.taskStageOpen')") == "0")

        # ---- 2. 두 칸이 차면 단추가 켜짐(강조) · 펴면 강조가 세부 목록 쪽으로 · 값이 없는 사업계획서 → 멈추고 세부 목록이 펴짐
        task(a, file="report", project="묶음 시험")
        task(c, file="plan", project="묶음 시험")
        open_work(page, a)
        page.click("#taskHome")
        page.wait_for_function(f"() => {{ const s = ({STAGE})(); return s && s.count === '0/1 완료' && s.text.includes('값이 없습니다'); }}", timeout=60000)
        s, s2 = page.evaluate(STAGE), page.evaluate(STAGE2)
        check("준비는 완료 집계에서 제외 — 0/1 완료 · 다음은 ① · 단추 켜짐·강조(강조는 할 일이 남은 첫 묶음 하나 — 2단계 단추는 꺼짐)", s["text"].startswith("다음: ① 구분 기준 확인") and s["progress"] == [0, 1] and not s["disabled"] and s["primary"] and not s["open"]
              and s2["disabled"] and not s2["primary"], [s, s2])
        for width in (320, 480):  # 패널 최소 폭·보통 폭에서 가로 넘침 없음(design.md §1-8)
            page.evaluate("(w) => { const c = colSizers.find((x) => x.box === 'panel'); c.w = w; c.apply(); }", width)
            page.wait_for_timeout(300)
            check(f"묶음 가로 넘침 없음(패널 {width}px)", page.evaluate("() => { const t = document.querySelector('#divBox .dv-task'), r = t.getBoundingClientRect(); return t.scrollWidth <= t.clientWidth + 1 && [...t.querySelectorAll('#taskStage summary > *')].every((e) => e.getBoundingClientRect().right <= r.right + 1); }"))
            page.locator("#panel").screenshot(path=str(OUT / f"2_stage_{width}.png"))
        page.evaluate("() => { const c = colSizers.find((x) => x.box === 'panel'); c.w = null; c.apply(); }")
        page.click("#taskStage > summary strong")
        page.wait_for_function("() => localStorage.getItem('nfm.taskStageOpen') === '1'")
        check("펴면 묶음 단추의 강조가 풀림(강조 단추는 카드에 하나)", not page.evaluate(STAGE)["primary"])
        st, s = page.evaluate(STEPS), page.evaluate(STAGE)
        check("펼친 요약은 다음 작업 이름만 · 상세에 까닭과 각 단계 상태", s["text"] == "다음: ① 구분 기준 확인" and "값이 없습니다" in st[1]["text"]
              and [x["no"] for x in st] == ["·", "①", "②", "③", "④", "⑤"]
              and [x["badge"] for x in st] == ["완료", "다음 작업", "대기", "대기", "대기", "준비 중"], [s, st])
        for width in (320, 480):
            page.evaluate("(w) => { const c = colSizers.find((x) => x.box === 'panel'); c.w = w; c.apply(); }", width)
            page.wait_for_timeout(300)
            check(f"펼친 상세 번호·상태·단추 가로 넘침 없음(패널 {width}px)", page.evaluate("""() => {
              const t = document.querySelector('#divBox .dv-task'), r = t.getBoundingClientRect();
              return t.scrollWidth <= t.clientWidth + 1 && [...t.querySelectorAll('#taskSteps li, .dv-flow-no, .dv-flow-title, .dv-flow-status, .dv-flow-text, #taskSteps button')].filter((e) => e.checkVisibility()).every((e) => {
                const b = e.getBoundingClientRect(); return b.left >= r.left - 1 && b.right <= r.right + 1 && e.scrollWidth <= e.clientWidth + 1;
              }); }"""))
            page.locator("#panel").screenshot(path=str(OUT / f"2_steps_{width}.png"))
        page.evaluate("() => { const c = colSizers.find((x) => x.box === 'panel'); c.w = null; c.apply(); }")
        page.click("#taskStage > summary strong")
        page.wait_for_function("() => localStorage.getItem('nfm.taskStageOpen') === '0'")
        check("접으면 다시 강조", page.evaluate(STAGE)["primary"])
        n = len(dialogs)
        page.click("#taskStage [data-task-run]")
        page.wait_for_function("() => !taskRun && !!taskRunLast", timeout=60000)
        s = page.evaluate(STAGE)
        check("값이 없는 사업계획서 — 확인 창 한 번 뒤 ① 에서 멈춤 · 세부 목록이 펴짐 · 단추는 다시 「한 번에 진행」", len(dialogs) == n + 1 and "한 번에 진행할까요" in dialogs[-1] and "남은 단계" in dialogs[-1]
              and s["kind"] == "halt" and s["text"].startswith("멈춤 — ① 구분 기준 확인") and "값이 없습니다" in s["text"] and s["open"] and s["btn"] == "한 번에 진행" and not s["disabled"] and not s["spin"]
              and page.evaluate(OLVIS, "taskStage") and "1단계 문서 프레임 작성" in dialogs[-1] and "내용은 넣지 않습니다" in dialogs[-1], [s, dialogs[-1][:160]])
        st = page.evaluate(STEPS)
        check("멈춘 상세 단계에 멈춤 표시 · 뒤 단계는 대기", st[1]["status"] == "halt" and st[1]["badge"] == "멈춤"
              and [x["badge"] for x in st[2:]] == ["대기", "대기", "대기", "준비 중"], st)
        page.locator("#panel").screenshot(path=str(OUT / "2_halt.png"))

        # ---- 3. 실제 서식 쌍 — 계획서 양식에 값을 반영해 두고(API), 연차보고서 서식에서 1단계 「한 번에 진행」(구조만) → 2단계 「한 번에 진행」(내용)
        plan, report = upload(PLAN_FORM), upload(REPORT_FORM)
        task(plan, file="plan", project="프레임 시험")
        task(report, file="report", project="프레임 시험")
        requests.put(f"{base}/api/docs/{plan}/divisions/settings", json={"values": VALUES}, timeout=120).raise_for_status()
        pl = requests.post(f"{base}/api/docs/{plan}/divisions/plan", json={"values": VALUES, "skip": []}, timeout=300)
        pl.raise_for_status()
        ap1 = requests.post(f"{base}/api/docs/{plan}/divisions/apply", json={"planId": pl.json()["planId"], "expectRev": pl.json()["baseRev"]}, timeout=300)
        check("사업계획서 양식에 값 반영(API — 사전 준비)", ap1.status_code == 200 and not ap1.json().get("nothing"), ap1.status_code)
        rev0 = requests.get(f"{base}/api/docs/{report}", timeout=300).json()["rev"]
        calls = {"llm": 0, "amb": None}

        def links_route(route):  # LLM 검토만 가짜(서버는 LLM 끔) — 실제 연결 목록에 llm 표시를 얹어 돌려준다. 그 뒤의 읽기에도 얹는다(서버에는 저장이 없으므로)
            req = route.request
            if req.method == "POST" and req.url.endswith("/merge-links/llm"):
                calls["llm"] += 1
                got = requests.get(req.url[:-4], timeout=300).json()
            elif req.method == "GET" and req.url.endswith("/merge-links") and calls["llm"]:
                got = requests.get(req.url, timeout=300).json()
            else:
                return route.continue_()
            got["llm"] = {"at": "2026-11-12T00:00:00", "units": [{"title": "1.", "pages": [1, 5], "over": False, "targets": 1, "call": {"model": "fake"}}], "none": [], "rejected": 0, "left": 0}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(got, ensure_ascii=False))
        page.route(re.compile(r"/api/docs/[^/]+/merge-links(/llm)?$"), links_route)
        open_work(page, report)
        page.click("#taskHome")
        page.wait_for_function(f"() => {{ const s = ({STAGE})(); return s && s.count === '0/1 완료' && ({STEPS})()[1].text.includes('다름'); }}", timeout=120000)
        s = page.evaluate(STAGE)
        check("연차보고서 서식 — 0/1 완료 · 다음은 ①, 상세에 사업계획서와 다른 까닭", s["text"].startswith("다음: ① 구분 기준 확인") and "사업계획서(1단계 · 전체 2년 · 기관 3곳)와 다름" in page.evaluate(STEPS)[1]["text"] and not s["disabled"], s)
        n, t0 = len(dialogs), time.time()
        page.click("#taskStage [data-task-run]")
        page.wait_for_function("() => !!taskRun", timeout=10000)
        page.wait_for_function(f"() => ({STAGE})().spin", timeout=10000)
        s = page.evaluate(STAGE)
        check("도는 중 — 돌아가는 동그라미 + 지금 하는 일 + 지난 시간 · 단추 「멈춤」", s["kind"] == "run" and s["spin"] and "구분 기준 확인" in s["text"] and re.search(r"\d+초", s["text"]) is not None and s["btn"] == "멈춤" and not s["disabled"], s)
        running = [x for x in page.evaluate(STEPS) if x["status"] == "run"]
        check("실행 중인 상세 단계 하나에 진행 중 표시", len(running) == 1 and running[0]["step"] == "division" and running[0]["badge"] == "진행 중", running)
        page.locator("#panel").screenshot(path=str(OUT / "3_running.png"))
        seen = set()
        while page.evaluate("() => !!taskRun"):   # 끝날 때까지 — 지나간 단계 글을 모은다
            seen.add(page.evaluate("() => taskRun ? taskRun.key + ' — ' + taskRun.note : ''"))
            if time.time() - t0 > 1500:
                break
            page.wait_for_timeout(1000)
        took = time.time() - t0
        last = page.evaluate("() => taskRunLast")
        print("  단계 글:", sorted(x for x in seen if x), flush=True)
        check("1단계 끝남 — 멈추지 않고 끝까지", bool(last) and last["ok"] and last["stage"] == "frame", [last, f"{took:.0f}s"])
        check("1단계 확인 창은 누를 때 한 번뿐(구분 기준 반영의 확인 창 없음) — 구조만 바뀌고 내용은 안 넣는다고 알림", len(dialogs) == n + 1 and "1단계 문서 프레임 작성" in dialogs[n] and "실행 취소" in dialogs[n]
              and "내용은 넣지 않습니다" in dialogs[n] and "LLM 검토" not in dialogs[n] and "연차보고서" in dialogs[n], dialogs[n:])
        st, s, s2 = page.evaluate(STEPS), page.evaluate(STAGE), page.evaluate(STAGE2)
        states = {x["step"]: x["state"] for x in st}
        doc1 = requests.get(f"{base}/api/docs/{report}", timeout=300).json()
        ev1 = [e["kind"] for e in requests.get(f"{base}/api/works/{report}/log", timeout=60).json()["events"]]
        check("1단계 = 구조까지만 — ① 완료 · 1/1 완료 · 편집 한 번(구분 기준 반영) · 내용 넣기 기록 없음", states.get("division") == "done" and s["count"] == "1/1 완료" and s["progress"] == [1, 1] and s["kind"] == "done"
              and s["text"].startswith("끝남 — 구조를 맞췄습니다") and s["disabled"] and doc1["rev"] == rev0 + 1 and doc1.get("undo") == 1 and "divisions" in ev1 and "mergeFill" not in ev1
              and states.get("apply") != "done", [states, s, rev0, doc1["rev"], ev1[:8]])
        check("2단계가 켜짐 — 0/3 완료 · 다음은 ② · 강조 단추가 2단계로 옮겨 감", s2["count"] == "0/3 완료" and s2["text"].startswith("다음: ② 자리 연결") and not s2["disabled"] and s2["primary"] and not s["primary"], s2)
        page.locator("#panel").screenshot(path=str(OUT / "3_frame_done.png"))
        n, t0 = len(dialogs), time.time()
        page.click("#taskStage2 [data-task-run]")
        page.wait_for_function("() => !!taskRun", timeout=10000)
        page.wait_for_function(f"() => ({STAGE2})().spin", timeout=10000)
        s, s2 = page.evaluate(STAGE), page.evaluate(STAGE2)
        check("2단계 도는 중 — 그 묶음에만 동그라미·「멈춤」 · 1단계 단추는 꺼짐", s2["kind"] == "run" and s2["spin"] and s2["btn"] == "멈춤" and not s2["disabled"] and not s["spin"] and s["disabled"] and s["btn"] == "한 번에 진행", [s, s2])
        while page.evaluate("() => !!taskRun"):   # 끝날 때까지 — 지나간 단계 글을 모은다
            seen.add(page.evaluate("() => taskRun ? taskRun.key + ' — ' + taskRun.note : ''"))
            if time.time() - t0 > 1500:
                break
            page.wait_for_timeout(1000)
        took = time.time() - t0
        last = page.evaluate("() => taskRunLast")
        print("  단계 글:", sorted(x for x in seen if x), flush=True)
        check("2단계 끝남 — 멈추지 않고 끝까지", bool(last) and last["ok"] and last["stage"] == "map", [last, f"{took:.0f}s"])
        check("2단계 확인 창도 누를 때 한 번뿐(내용 반영의 확인 창 없음)", len(dialogs) == n + 1 and "2단계 내용 매핑" in dialogs[n] and "실행 취소" in dialogs[n] and "LLM 검토" in dialogs[n] and "같은 이름 자리" in dialogs[n], dialogs[n:])
        st, s = page.evaluate(STEPS), page.evaluate(STAGE2)
        states = {x["step"]: x["state"] for x in st}
        check("단계 — ①~④ 모두 완료 · 2단계 3/3 완료와 진행률 100%", [states.get(k) for k in ("files", "division", "link", "plan", "apply")] == ["done"] * 5
              and s["count"] == "3/3 완료" and s["progress"] == [3, 3] and s["kind"] == "done" and s["text"].startswith("끝남 — 연결됨") and "본문 블록" in s["text"] and "같은 이름 자리" in s["text"]
              and s["btn"] == "한 번에 진행" and s["disabled"] and not s["spin"], [states, s])
        check("실행 종료 뒤 진행 중·멈춤 표시 없음 · 번호와 완료·준비 중 표시 유지", not any(x["status"] in ("run", "halt") for x in st)
              and [x["no"] for x in st[1:]] == ["①", "②", "③", "④", "⑤"] and [x["badge"] for x in st[1:]] == ["완료", "완료", "완료", "완료", "준비 중"], st)
        doc = requests.get(f"{base}/api/docs/{report}", timeout=300).json()
        ev = [e["kind"] for e in requests.get(f"{base}/api/works/{report}/log", timeout=60).json()["events"]]
        check("연차보고서 — 편집 두 번(구분 기준 반영 · 내용 반영) · 실행 취소 2", doc["rev"] == rev0 + 2 and doc.get("undo") == 2, [rev0, doc["rev"], doc.get("undo"), ev[:12]])
        heads = [requests.get(f"{base}/api/docs/{w}/headings", timeout=300).json() for w in (plan, report)]
        check("두 문서에 헤딩 그래프·표 구조가 생김(스크립트 — 없던 문서만 분석) · 연차보고서의 분석은 구조 반영 뒤 문서의 것", all(h.get("stage2") and h.get("stage3") for h in heads)
              and heads[1]["stage3"]["meta"]["rev"] >= rev0 + 1, [h["stage3"]["meta"].get("rev") for h in heads if h.get("stage3")])
        links = requests.get(f"{base}/api/docs/{report}/merge-links", timeout=300).json()
        fill_ev = next(e for e in requests.get(f"{base}/api/works/{report}/log", timeout=60).json()["events"] if e["kind"] == "mergeFill")
        check("같은 이름 자리(고정 자리)도 연결 목록·넣기 기록에 따로 실림", isinstance((links.get("fixed") or {}).get("counts"), dict) and "fixed" in fill_ev and "shaped" in fill_ev["tables"], [links.get("fixed"), {k: fill_ev.get(k) for k in ("tables", "fixed")}])
        check("LLM 검토 — 확인 필요가 있어 한 번만 부름(가짜 응답 — 이 쌍은 확인 필요 9)", calls["llm"] == 1 and links["counts"]["ambiguous"] > 0, [calls, links["counts"]])
        check("사업계획서는 그대로(사전 반영의 편집 1뿐)", requests.get(f"{base}/api/docs/{plan}", timeout=300).json()["rev"] == ap1.json()["rev"])
        page.locator("#panel").screenshot(path=str(OUT / "3_done.png"))
        page.screenshot(path=str(OUT / "3_done_full.png"))

        # ---- 4. 다시 누르기 — 새로 고치면 ③④ 의 「넣은 수」 는 사라진다(메모리). 다시 눌러도 확인 창 한 번 · 실패 없이 끝나고 LLM 검토는 다시 안 부른다(이미 검토함)
        open_work(page, report)
        page.click("#taskHome")
        page.wait_for_function(f"() => {{ const s = ({STAGE2})(); return s && s.count === '1/3 완료' && ({STAGE})().count === '1/1 완료' && !taskFlow.linkBusy && !!taskFlow.links; }}", timeout=180000)
        check("다시 열면 — 1단계는 끝난 채(단추 꺼짐) · 2단계 1/3(넣은 수는 메모리라 사라짐)", page.evaluate(STAGE)["disabled"] and not page.evaluate(STAGE2)["disabled"])
        n = len(dialogs)
        page.click("#taskStage2 [data-task-run]")
        page.wait_for_function("() => !taskRun && !!taskRunLast", timeout=600000)
        last, doc2 = page.evaluate("() => taskRunLast"), requests.get(f"{base}/api/docs/{report}", timeout=300).json()
        log2 = requests.get(f"{base}/api/works/{report}/log", timeout=60).json()["events"]
        ev2 = [e["kind"] for e in log2]
        print("  다시 누름:", last, "rev", doc["rev"], "→", doc2["rev"], "기록", [(e["kind"], e.get("rev")) for e in log2 if e["kind"] not in ("create", "verify", "verified", "headings")], flush=True)
        check("다시 누름 — 확인 창 한 번 · 실패 없이 끝남 · 구분 기준은 다시 반영 안 함 · LLM 검토 다시 안 부름", last["ok"] and len(dialogs) == n + 1 and calls["llm"] == 1
              and ev2.count("divisions") == ev.count("divisions"), [last, ev2[:6]])
        # 다시 눌러도 더 들어가지 않는다(2026-11-12 app/merge_tables.py 고침 — 전에는 이어 넣는 표에 행이 또 들어갔다: spec_병합 ③). 편집 차례는 하나 오를 수 있다 — 다시 열 때의 개요 줄 맞춤(outlineAlign), 넣기와 무관
        check("다시 누름 — 넣을 것이 없어 더 넣지 않음(넣기 기록 그대로 1번)", "넣을 것이 없습니다" in last["text"] and ev2.count("mergeFill") == ev.count("mergeFill") == 1, [last["text"], ev2.count("mergeFill")])
        third = requests.post(f"{base}/api/docs/{report}/merge-links/plan", timeout=300).json()
        check("또 계획해도 할 일 0", third.get("todo") == 0, {"todo": third.get("todo"), "tables": {k: third["tables"]["counts"].get(k) for k in ("cells", "rows")}})
        bad = [e for e in errors if "Failed to load resource" not in e]
        check("화면 오류 0", not bad, bad[:5])
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

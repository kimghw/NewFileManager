"""이관의 묶음 넷(spec_작업 ② §21 — 2026-11-19): 1단계 「문서 검토」(헤딩·표 분석) · 2단계 「구성 맞추기」(구성 확정 → 구조 반영 → 다시 분석) · 3단계 「내용 넣기」 · 4단계 「문서 정리」 · 묶음마다 「한 번에 진행」(spec_작업 ② §14) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_task_run_ui.py <그림·임시 폴더> [--port 18164]

① 묶음 모양(작은 문서 둘): 접힌 상자 · 끝난 수 · 상태 줄 · 펴고 접기 · 준비가 안 끝나면 단추 꺼짐 · 값이 없으면 멈추고 세부 목록이 펴짐.
② 실제 서식 쌍(연구개발계획서 양식 → 연차보고서 서식 — 저장소 samples): 1단계 「한 번에 진행」 = 두 문서 분석 + 작성 지침 저장(문서 안 바뀜), 2단계 = 구조 반영 + 연차보고서 다시 분석(내용은 안 넣음), 3단계 「한 번에 진행」 = 자리 연결
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
STEPS = """() => [...document.querySelectorAll('#taskSteps li:not([data-step=config]):not([data-step=heads]):not([data-step=reheads]):not([data-step=headsLlm]):not([data-step=reheadsLlm])')].map((li) => ({ step: li.dataset.step, state: li.dataset.state,
  status: li.dataset.status, badge: li.querySelector('.dv-flow-status').textContent, no: li.querySelector('.dv-flow-no').textContent, text: li.textContent }))"""
# 묶음 머리 — 펴짐 · 끝난 수 · 상태 줄(종류·글·동그라미) · 단추(글·꺼짐·강조)
STAGE = """() => { const b = document.getElementById('taskStage'); if (!b) return null; const st = b.querySelector('.dv-phase-state'), run = b.querySelector('[data-task-run]');
  const progress = b.querySelector('.dv-phase-progress');
  return { open: b.open, count: b.querySelector('.dv-phase-count').textContent, progress: [progress.value, progress.max], kind: st.dataset.kind, text: st.lastChild.textContent, spin: !st.firstChild.hidden,
    btn: run.textContent, disabled: run.disabled, primary: run.classList.contains('primary'), head: b.querySelector('summary').textContent }; }"""
STAGE0 = STAGE.replace("'taskStage'", "'taskStageR'")  # 1단계 「문서 검토」 묶음(spec_작업 ② §21 — STAGE = 2단계 「구성 맞추기」: 전의 1단계 「프로젝트 구성」 묶음 #taskStage0 은 없다)
STAGE2 = STAGE.replace("'taskStage'", "'taskStage2'")  # 3단계 「내용 넣기」 묶음
STEP = "(k) => { const li = document.querySelector('#taskSteps li[data-step=' + k + ']'); return li && { state: li.dataset.state, status: li.dataset.status, badge: li.querySelector('.dv-flow-status').textContent, text: li.textContent, acts: [...li.querySelectorAll('button')].map((b) => b.textContent) }; }"  # 줄 하나(heads · reheads)
STAGE3 = STAGE.replace("'taskStage'", "'taskStage3'")  # 4단계 「문서 정리」 묶음
CONFIG = "() => { const li = document.querySelector('#taskSteps li[data-step=config]'); return li && { state: li.dataset.state, status: li.dataset.status, badge: li.querySelector('.dv-flow-status').textContent, text: li.textContent }; }"
# 이어서 한 번에(spec_작업 ② §14 — 2026-11-12 사용자 "1,2,3 단계도 한번에 … 1,2 만 할 수도 있고 3까지 할 수도 있고"): 줄 보임 · 상태 글 · 끝 묶음마다 단추(글·숨김·꺼짐·강조)
CHAIN = """() => { const c = document.getElementById('taskChain'); if (!c) return null;
  return { shown: !c.hidden && c.checkVisibility(), state: c.querySelector('.dv-chain-state').textContent,
    btns: Object.fromEntries([...c.querySelectorAll('[data-task-chain]')].map((b) => [b.dataset.taskChain, { text: b.textContent, hidden: b.hidden, disabled: b.disabled, primary: b.classList.contains('primary') }])) }; }"""
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
        page.click("#toolTabTask")
        page.wait_for_selector("#taskStage")

        # ---- 1. 묶음 모양 — 접힌 상자 · 머리 줄 · 상태 줄 · 준비가 안 끝나면 단추 꺼짐
        labels = page.eval_on_selector_all("#divBox .dv-task-field > span", "xs => xs.map(x => x.textContent)")
        check("첫 카드에 「작업」 칸 없음(패널 머리에만) — 프로젝트 · 워크플로우(② §17 — 「할 일」 → TASK → 화면 말 「워크플로우」 · 「과제」 → 프로젝트)", labels == ["프로젝트", "워크플로우"] and page.locator("#divBox .dv-task select[data-task=kind]").count() == 0
              and page.input_value("#panelTask") == "rnd", labels)
        s0, s = page.evaluate(STAGE0), page.evaluate(STAGE)
        check("묶음 = 접힌 상자 · 「1단계 문서 검토」(0/2 — 헤딩·표 분석 · LLM 검증·보완) · 「2단계 구성 맞추기」(0/4 — 구성 확정 · 반영 · 다시 문서 검토 · 그 LLM)와 진행률 · 세부 목록은 안 보임", s0["open"] is False and "1단계" in s0["head"] and "문서 검토" in s0["head"] and s0["count"] == "0/2 완료"
              and s["open"] is False and "2단계" in s["head"] and "구성 맞추기" in s["head"] and s["count"] == "0/4 완료" and s["progress"] == [0, 4]
              and not page.evaluate(OLVIS, "taskStage") and not page.evaluate(OLVIS, "taskStageR") and page.locator("#taskStage0").count() == 0, (s0, s))
        s2 = page.evaluate(STAGE2)
        map_note = page.get_attribute("#taskStage2 > summary .panel-help", "data-help")
        check("셋째 묶음 = 「3단계 내용 넣기」 · 0/3 완료 · 선행조건(앞 묶음 중 덜 끝난 첫 묶음)은 표시하고 상세 설명은 노트 · 단추 꺼짐", s2["open"] is False and "3단계" in s2["head"] and "내용 넣기" in s2["head"]
              and s2["count"] == "0/3 완료" and s2["progress"] == [0, 3] and s2["text"] == "1단계 「문서 검토」 완료 후 진행" and "자리 연결" in map_note and "내용 반영" in map_note and "헤딩·표 분석" not in map_note
              and s2["disabled"] and not s2["primary"] and not page.evaluate(OLVIS, "taskStage2"), s2)
        check("준비가 안 끝남 — 1단계 상태 줄 「다음: 준비 …」 · 단추 꺼짐 · 2단계는 「1단계 … 완료 후 진행」", s0["kind"] == "next" and s0["text"].startswith("다음: 준비") and "사업계획서" in s0["text"] and s0["btn"] == "한 번에 진행"
              and s0["disabled"] and not s0["primary"] and not s0["spin"] and s["text"] == "1단계 「문서 검토」 완료 후 진행" and s["disabled"], (s0, s))
        ch = page.evaluate(CHAIN)
        check("이어서 한 번에 줄 — 첨부 파일 칸과 1단계 묶음 사이 · 「1→2단계」 · 「1→3단계」 · 「1→4단계」 보통 단추 · 준비 전이라 꺼짐", bool(ch) and ch["shown"] and ch["btns"]["frame"]["text"] == "1→2단계" and ch["btns"]["map"]["text"] == "1→3단계"
              and ch["btns"]["clean"]["text"] == "1→4단계" and all(b["disabled"] and not b["primary"] and not b["hidden"] for b in ch["btns"].values()) and not ch["state"]
              and page.evaluate("() => { const c = document.getElementById('taskChain'); return c.previousElementSibling.classList.contains('dv-flow-files') && c.nextElementSibling.id === 'taskSteps'; }"), ch)
        page.click("#taskStage > summary strong")
        page.wait_for_function("() => localStorage.getItem('nfm.taskStageOpen') === '1'")  # toggle 사건은 한 박자 뒤에 온다
        s = page.evaluate(STAGE)
        check("머리 줄을 누르면 펴짐 — 세부 목록(이 묶음 세 줄 — 구성 확정 · ① · 다시 분석 · 1단계 두 줄 — 준비 · 헤딩·표 분석 · 네 묶음 합쳐 열 줄) · 이 브라우저에 기억 · 다음 묶음은 접힌 채", s["open"] and page.evaluate(OLVIS, "taskStage") and not page.evaluate(OLVIS, "taskStage2")
              and len(page.evaluate(STEPS)) == 7 and page.locator("#taskSteps li").count() == 12 and page.locator("#taskStageR ol.dv-flow-steps > li").count() == 3 and page.locator("#taskStage ol.dv-flow-steps > li").count() == 4 and page.locator("#taskStage2 ol.dv-flow-steps > li").count() == 4 and page.locator("#taskStage3 ol.dv-flow-steps > li").count() == 1
              and page.evaluate("() => localStorage.getItem('nfm.taskStageOpen')") == "1", s)
        page.click("#taskStage > summary strong")
        page.wait_for_function("() => localStorage.getItem('nfm.taskStageOpen') === '0'")
        check("다시 누르면 접힘", page.evaluate(STAGE)["open"] is False and page.evaluate("() => localStorage.getItem('nfm.taskStageOpen')") == "0")

        # ---- 2. 두 칸이 차면 단추가 켜짐(강조) · 펴면 강조가 세부 목록 쪽으로 · 값이 없는 사업계획서 → 멈추고 세부 목록이 펴짐
        task(a, file="report", project="묶음 시험")
        task(c, file="plan", project="묶음 시험")
        open_work(page, a)
        page.click("#toolTabTask")
        page.wait_for_function(f"() => {{ const s = ({STAGE0})(); return s && s.count === '0/2 완료' && s.text.includes('사업계획서 없음 · 연차보고서 없음'); }}", timeout=60000)
        s0, s, s2 = page.evaluate(STAGE0), page.evaluate(STAGE), page.evaluate(STAGE2)
        check("준비는 완료 집계에서 제외 — 1단계 0/2 완료 · 다음은 헤딩 · 표 분석(올릴 때의 기본 분석이 없는 문서 — API 로 올림) · 단추 켜짐·강조(강조는 할 일이 남은 첫 묶음 하나 — 2·3단계 단추는 꺼짐)", s0["text"].startswith("다음: 헤딩 · 표 분석") and s0["progress"] == [0, 2] and not s0["disabled"] and s0["primary"] and not s0["open"]
              and s["disabled"] and not s["primary"] and s2["disabled"] and not s2["primary"], [s0, s, s2])
        ch = page.evaluate(CHAIN)
        check("두 칸이 차면 이어서 단추도 켜짐 — 강조는 아님(강조 단추는 카드에 하나)", all(not b["disabled"] and not b["primary"] for b in ch["btns"].values()), ch)
        for width in (320, 480):  # 패널 최소 폭·보통 폭에서 가로 넘침 없음(design.md §1-8)
            page.evaluate("(w) => { const c = colSizers.find((x) => x.box === 'panel'); c.w = w; c.apply(); }", width)
            page.wait_for_timeout(300)
            check(f"묶음·이어서 줄 가로 넘침 없음(패널 {width}px)", page.evaluate("() => { const t = document.querySelector('#divBox .dv-task'), r = t.getBoundingClientRect(); return t.scrollWidth <= t.clientWidth + 1 && [...t.querySelectorAll('#taskStageR summary > *, #taskStage summary > *, #taskChain > *')].filter((e) => e.checkVisibility()).every((e) => e.getBoundingClientRect().right <= r.right + 1); }"))
            page.locator("#panel").screenshot(path=str(OUT / f"2_stage_{width}.png"))
        page.evaluate("() => { const c = colSizers.find((x) => x.box === 'panel'); c.w = null; c.apply(); }")
        page.click("#taskStageR > summary strong")
        page.wait_for_function("() => localStorage.getItem('nfm.taskStageOpenR') === '1'")
        check("펴면 묶음 단추의 강조가 풀림(강조 단추는 카드에 하나)", not page.evaluate(STAGE0)["primary"])
        st, s0, cf, hd = page.evaluate(STEPS), page.evaluate(STAGE0), page.evaluate(CONFIG), page.evaluate(STEP, "heads")
        check("펼친 요약은 다음 작업 이름만 · 상세에 까닭과 각 단계 상태(헤딩·표 분석 = 다음 작업 · 「분석」 / 구성 확정 = 진행 가능 — 분석과 무관하게 누를 수 있다 · ① 이하 대기)", s0["text"] == "다음: 헤딩 · 표 분석"
              and hd["badge"] == "다음 작업" and "사업계획서 없음 · 연차보고서 없음" in hd["text"] and hd["acts"] == ["분석"]
              and "프로젝트 구성(단계·차년도·기관)이 없습니다" in cf["text"] and cf["badge"] == "진행 가능"
              and [x["no"] for x in st] == ["·", "①", "②", "③", "④", "⑤", "⑥"]
              and [x["badge"] for x in st] == ["완료", "대기", "대기", "대기", "대기", "준비 중", "대기"], [s0, cf, st])
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
        page.click("#taskStageR > summary strong")
        page.wait_for_function("() => localStorage.getItem('nfm.taskStageOpenR') === '0'")
        check("접으면 다시 강조", page.evaluate(STAGE0)["primary"])
        n = len(dialogs)
        page.click("#taskStageR [data-task-run]")   # 1단계 「문서 검토」 — 분석이 없는 두 문서를 스크립트로 분석(작은 문서 — 몇 초) + 작성 지침 저장. 문서는 안 바뀐다
        page.wait_for_function("() => !taskRun && !!taskRunLast", timeout=300000)
        s0, s, last = page.evaluate(STAGE0), page.evaluate(STAGE), page.evaluate("() => taskRunLast")
        hd, hl = page.evaluate(STEP, "heads"), page.evaluate(STEP, "headsLlm")
        check("1단계 「한 번에 진행」 — 확인 창 없이 두 문서를 분석하고 끝남(LLM 을 쓸 수 없어 LLM 검증·보완은 건너뜀) · 2/2 완료 · 2단계 단추가 켜지고 강조가 옮겨 감 · 문서는 그대로(rev)", len(dialogs) == n and last["ok"] and last["stage"] == "review"
              and s0["kind"] == "done" and s0["count"] == "2/2 완료" and s0["text"].startswith("끝남 — 두 문서의 헤딩 그래프·표 구조가 있습니다") and "사업계획서 LLM 검증·보완은 건너뜀(LLM 을 쓸 수 없음)" in s0["text"] and s0["disabled"]
              and hd["state"] == "done" and "사업계획서 있음 · 연차보고서 있음" in hd["text"] and hl["state"] == "done" and hl["badge"] == "건너뜀" and "LLM 을 쓸 수 없어 건너뜁니다" in hl["text"] and hl["acts"] == []
              and not s["disabled"] and s["primary"] and s["text"].startswith("다음: 프로젝트 구성 추출")
              and all(requests.get(f"{base}/api/docs/{w}", timeout=60).json()["rev"] == 0 for w in (a, c)), [s0, hd, s, last])
        g0 = requests.get(f"{base}/api/docs/{a}/form-guides", timeout=60).json()
        check("1단계가 작성 지침을 저장함(이 작은 문서에도 ※ 안내 하나 — 표 하나의 것 · 헤딩은 본문 헤딩이 앞에 없어 비움) · 줄에 수와 「작성 지침」 단추", g0["saved"] is not None and g0["saved"]["counts"]["items"] == 1 and g0["saved"]["counts"]["tables"] == 1
              and "작성 지침 1개 저장" in hd["text"] and hd["acts"] == ["작성 지침"], [g0.get("saved") and g0["saved"]["counts"], hd])
        n = len(dialogs)
        page.evaluate("() => { taskRunLast = null; }")
        page.click("#taskStage [data-task-run]")   # 2단계 「구성 맞추기」 — 첫 단계(프로젝트 구성 추출)에서 멈춘다
        page.wait_for_function("() => !taskRun && !!taskRunLast", timeout=60000)
        s0 = page.evaluate(STAGE)
        check("값이 없는(읽을 수도 없는) 사업계획서 — 확인 창 없이(2026-11-18) 구성 확정에서 멈춤 · 세부 목록이 펴짐 · 단추는 다시 「한 번에 진행」", len(dialogs) == n
              and s0["kind"] == "halt" and s0["text"].startswith("멈춤 — 프로젝트 구성 추출") and "읽지 못했습니다" in s0["text"] and s0["open"] and s0["btn"] == "한 번에 진행" and not s0["disabled"] and not s0["spin"]
              and page.evaluate(OLVIS, "taskStage"), [s0, dialogs[n:]])
        st, cf = page.evaluate(STEPS), page.evaluate(CONFIG)
        check("멈춘 상세 단계에 멈춤 표시 · 뒤 단계는 대기", cf["status"] == "halt" and cf["badge"] == "멈춤"
              and [x["badge"] for x in st[1:]] == ["대기", "대기", "대기", "대기", "준비 중", "대기"], (cf, st))
        page.locator("#panel").screenshot(path=str(OUT / "2_halt.png"))
        n = len(dialogs)
        page.evaluate("() => { taskRunLast = null; }")
        page.click("#taskChain [data-task-chain=clean]")
        page.wait_for_function("() => !taskRun && !!taskRunLast", timeout=60000)
        s0, s2, last, ends = page.evaluate(STAGE), page.evaluate(STAGE2), page.evaluate("() => taskRunLast"), page.evaluate("() => taskRunEnds")
        check("이어서 2→4단계(1단계는 끝남) — 확인 창 없이(2026-11-18) · 값이 없어 2단계 구성 확정에서 전체가 멈춤 · 뒤 묶음은 안 돔", len(dialogs) == n
              and not last["ok"] and last["stage"] == "frame" and list(ends) == ["frame"] and s0["kind"] == "halt" and "읽지 못했습니다" in s0["text"] and s2["text"] == "2단계 「구성 맞추기」 완료 후 진행"
              and not page.evaluate(CHAIN)["btns"]["clean"]["disabled"], [s0["text"], s2["text"], last, dialogs[n:]])

        # ---- 3. 실제 서식 쌍 — 계획서 양식에 값을 반영해 두고(API), 연차보고서 서식에서 1단계 「한 번에 진행」(구조만) → 2단계 「한 번에 진행」(내용)
        plan, report = upload(PLAN_FORM), upload(REPORT_FORM)
        task(plan, file="plan", project="프레임 시험")
        task(report, file="report", project="프레임 시험")
        requests.put(f"{base}/api/docs/{plan}/divisions/settings", json={"values": VALUES}, timeout=120).raise_for_status()
        pl = requests.post(f"{base}/api/docs/{plan}/divisions/plan", json={"values": VALUES, "skip": []}, timeout=300)
        pl.raise_for_status()
        ap1 = requests.post(f"{base}/api/docs/{plan}/divisions/apply", json={"planId": pl.json()["planId"], "expectRev": pl.json()["baseRev"]}, timeout=300)
        check("사업계획서 양식에 값 반영(API — 사전 준비)", ap1.status_code == 200 and not ap1.json().get("nothing"), ap1.status_code)
        cfm = requests.post(f"{base}/api/docs/{plan}/divisions/confirm", json={}, timeout=120)   # 1단계 「구분 기준」 — 프로젝트에 확정(spec_작업 ② §18)
        check("구성 확정(API — 사전 준비) — 프로젝트 「프레임 시험」", cfm.status_code == 200 and (cfm.json().get("confirmed") or {}).get("valid") is True, cfm.status_code)
        rev0 = requests.get(f"{base}/api/docs/{report}", timeout=300).json()["rev"]
        calls = {"llm": 0, "amb": None, "gaps": 0, "map": 0}
        page.on("request", lambda r: r.method == "POST" and r.url.endswith("/merge-links/gaps") and calls.__setitem__("gaps", calls["gaps"] + 1))       # 빈 자리 검토(spec_병합 ② §5-4)
        page.on("request", lambda r: r.method == "POST" and r.url.endswith("/merge-links/table-map") and calls.__setitem__("map", calls["map"] + 1))   # 표 대응(② §5-3)

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
        page.click("#toolTabTask")
        page.wait_for_function(f"() => {{ const s = ({STAGE})(); return s && s.count === '1/4 완료' && ({STEPS})()[1].text.includes('1단계 · 전체 2년 · 기관 3곳'); }}", timeout=120000)
        s0, s = page.evaluate(STAGE0), page.evaluate(STAGE)
        check("실제 서식 쌍 — 분석 전: 1단계가 다음(강조) · 2단계는 구성 확정만 끝남(1/4)이고 「1단계 … 완료 후 진행」(단추 꺼짐) · ① 은 진행 가능(단계별로는 누를 수 있다)", s0["text"].startswith("다음: 헤딩 · 표 분석") and not s0["disabled"] and s0["primary"]
              and s["text"] == "1단계 「문서 검토」 완료 후 진행" and s["disabled"] and page.evaluate(STEPS)[1]["state"] == "ready", [s0, s])
        n, t0 = len(dialogs), time.time()
        page.click("#taskStageR [data-task-run]")   # 1단계 「문서 검토」 — 두 서식을 스크립트로 분석(각각 1~2분) → 작성 지침을 헤딩/표별로 저장
        page.wait_for_function("() => !!taskRun", timeout=10000)
        page.wait_for_function("() => !taskRun && !!taskRunLast", timeout=1500000)
        last, s0, hd = page.evaluate("() => taskRunLast"), page.evaluate(STAGE0), page.evaluate(STEP, "heads")
        gd = requests.get(f"{base}/api/docs/{report}/form-guides", timeout=300).json()
        gc = (gd.get("saved") or {}).get("counts") or {}
        print("  1단계:", last, f"{time.time() - t0:.0f}s", gc, flush=True)
        check("1단계(문서 검토) 끝남 — 확인 창 없이 · 두 서식에 헤딩 그래프·표 구조 · 연차보고서는 그대로(rev) · 끝 글에 저장한 작성 지침 수", len(dialogs) == n and bool(last) and last["ok"] and last["stage"] == "review"
              and s0["count"] == "2/2 완료" and "작성 지침 38개 저장" in last["text"] and requests.get(f"{base}/api/docs/{report}", timeout=300).json()["rev"] == rev0, [last, s0])
        check("작성 지침 — 작성 요령 표 · <참고 N> 자료 · ※ 안내 38개가 헤딩/표별로 저장됨 · 요약문 표의 각주 번호 22개가 「요약문 작성 요령」 항목에 이어짐 · 줄에 수와 「작성 지침」 단추",
              gc.get("items") == 38 and gc.get("marks") == 56 and gc.get("marksLinked") == 22 and gc.get("headings", 0) > 10 and gc.get("tables", 0) > 10 and len(gd["groups"]["headings"]) == gc["headings"]
              and "작성 지침 38개 저장" in hd["text"] and hd["acts"] == ["작성 지침"], [gc, hd])
        page.evaluate("() => { document.getElementById('taskStageR').open = true; }")   # 세부 목록은 접혀 있다 — 줄의 단추를 누르려면 편다
        page.locator("#taskSteps li[data-step=heads] button", has_text="작성 지침").click()   # 헤딩별 · 표별 목록(문서 옆 열)
        page.wait_for_function("() => heads.dlg === 'formGuides' && document.querySelectorAll('#headsDlgBody table').length > 0", timeout=30000)
        fg = page.evaluate("() => ({ title: document.getElementById('headsDlgTitle').textContent, tools: [...document.querySelectorAll('#headsDlgTools button')].map((b) => [b.textContent, b.getAttribute('aria-pressed')]), caps: document.querySelectorAll('#headsDlgBody .lk-cap').length, rows: document.querySelectorAll('#headsDlgBody tr.go').length })")
        check("「작성 지침」 열 — 헤딩별(눌림) · 표별 단추 · 묶음마다 표 · 줄을 누를 수 있음", fg["title"] == "작성 지침 — 헤딩/표별" and fg["tools"] == [[f"헤딩별 {gc['headings']}", "true"], [f"표별 {gc['tables']}", "false"]] and fg["caps"] == gc["headings"] + len(gd["groups"]["loose"] and [1]) and fg["rows"] >= 38, fg)   # 묶음 = 헤딩마다 + 「헤딩 · 표를 못 정한 것」(문서 맨 앞의 「요약문 작성 요령」 — 앞에 본문 헤딩이 없다)
        page.locator("#headsDlgTools button", has_text="표별").click()
        page.wait_for_function("(n) => document.querySelectorAll('#headsDlgBody .lk-cap').length >= n && document.querySelector('#headsDlgTools button[aria-pressed=true]').textContent.startsWith('표별') && [...document.querySelectorAll('#headsDlgBody .lk-cap')][0].textContent.startsWith('표 ')", arg=gc["tables"], timeout=30000)
        check("표별로 바꿔 봄 — 요약문 표에 각주 번호와 이어진 작성 요령 항목", page.evaluate("() => [...document.querySelectorAll('#headsDlgBody tr')].some((tr) => tr.textContent.includes('세부사업명') && tr.textContent.includes('→ 1. 세부사업명'))"))
        page.locator("#headsDlg").screenshot(path=str(OUT / "3_guides.png"))
        page.locator("#headsDlgFoot button", has_text="닫기").click()
        page.evaluate("() => { document.getElementById('taskStageR').open = false; }")
        s = page.evaluate(STAGE)
        # 연차보고서의 입력 값은 프로젝트 공유 구분 기준(② §17)이라 사업계획서와 같을 수 있다 — 「…와 다름」 또는 「값은 사업계획서와 같음(…) · 아직 반영 전」
        check("연차보고서 서식 — 0/1 완료 · 다음은 ①, 상세에 사업계획서 값(1단계 · 전체 2년 · 기관 3곳)", s["text"].startswith("다음: ① 프로젝트 구성 반영") and "1단계 · 전체 2년 · 기관 3곳" in page.evaluate(STEPS)[1]["text"] and not s["disabled"], s)
        n, t0 = len(dialogs), time.time()
        page.click("#taskStage [data-task-run]")
        page.wait_for_function("() => !!taskRun", timeout=10000)
        page.wait_for_function(f"() => ({STAGE})().spin && !!taskRun && taskRun.key === 'division'", timeout=60000)   # 구성 확정은 끝나 있어 곧 ① 로 넘어간다
        s = page.evaluate(STAGE)
        check("도는 중 — 돌아가는 동그라미 + 지금 하는 일 + 지난 시간 · 단추 「멈춤」", s["kind"] == "run" and s["spin"] and "프로젝트 구성 반영" in s["text"] and re.search(r"\d+초", s["text"]) is not None and s["btn"] == "멈춤" and not s["disabled"], s)
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
        check("2단계(프레임) 끝남 — 멈추지 않고 끝까지", bool(last) and last["ok"] and last["stage"] == "frame", [last, f"{took:.0f}s"])
        check("2단계(프레임) — 확인 창 없이(2026-11-18 · 구분 기준 반영의 확인 창도 없음)", len(dialogs) == n, dialogs[n:])
        page.wait_for_function("() => !taskFlow.linkBusy && !!taskFlow.links", timeout=180000)   # 2단계가 분석까지 끝내 두어 곧바로 연결 목록을 읽는다(몇 초 — 그동안 ② 는 「진행 중」 이고 3단계 단추는 꺼져 있다)
        st, s, s2 = page.evaluate(STEPS), page.evaluate(STAGE), page.evaluate(STAGE2)
        states = {x["step"]: x["state"] for x in st}
        doc1 = requests.get(f"{base}/api/docs/{report}", timeout=300).json()
        ev1 = [e["kind"] for e in requests.get(f"{base}/api/works/{report}/log", timeout=60).json()["events"]]
        rh, h1 = page.evaluate(STEP, "reheads"), requests.get(f"{base}/api/docs/{report}/headings", timeout=300).json()
        check("2단계 = 구조까지만 — ① 완료 · 4/4 완료 · 편집 한 번(구분 기준 반영) · 내용 넣기 기록 없음", states.get("division") == "done" and s["count"] == "4/4 완료" and s["progress"] == [4, 4] and s["kind"] == "done"
              and s["text"].startswith("끝남 — 구조를 맞췄습니다") and s["disabled"] and doc1["rev"] == rev0 + 1 and doc1.get("undo") == 1 and "divisions" in ev1 and "mergeFill" not in ev1
              and states.get("apply") != "done", [states, s, rev0, doc1["rev"], ev1[:8]])
        check("2단계의 끝 = 다시 문서 검토 — 연차보고서의 분석이 구조 반영 뒤 문서의 것(§21: 전에는 3단계 안에 숨어 있었다) · 끝 글 · 그 LLM 줄은 건너뜀(LLM 을 쓸 수 없음)", "연차보고서를 다시 분석했습니다" in s["text"] and "연차보고서 LLM 검증·보완은 건너뜀" in s["text"]
              and any(x.startswith("reheads — ") for x in seen) and h1["stage2"]["meta"]["rev"] >= rev0 + 1 and h1["stage3"]["meta"]["rev"] >= rev0 + 1
              and rh["state"] == "done" and "구조 반영 뒤의 것입니다" in rh["text"] and rh["acts"] == [] and "다시 문서 검토" in rh["text"]
              and page.evaluate(STEP, "reheadsLlm")["badge"] == "건너뜀", [s["text"], rh, page.evaluate(STEP, "reheadsLlm"), h1["stage3"]["meta"].get("rev")])
        # 이 검사의 서버는 LLM 이 꺼져 있다 — 「자리 연결」 은 확인 필요가 남아도 「건너뜀」 으로 끝(서버 실행기의 상태 식과 같다: 막다른 길 없음) → 1/3 · 다음은 ③
        check("3단계가 켜짐 — 1/3 완료(LLM 을 못 써 자리 연결은 건너뜀) · 다음은 ③ · 강조 단추가 3단계로 옮겨 감", s2["count"] == "1/3 완료" and s2["text"].startswith("다음: ③ 표 안 연결") and not s2["disabled"] and s2["primary"] and not s["primary"], s2)
        ch = page.evaluate(CHAIN)
        check("2단계가 끝나면 이어서 단추는 실제 범위 「3→4단계」 하나(3단계까지는 3단계 단추와 같아 숨김)", ch["shown"] and ch["btns"]["frame"]["hidden"] and ch["btns"]["map"]["hidden"] and ch["btns"]["clean"]["text"] == "3→4단계"
              and not ch["btns"]["clean"]["disabled"], ch)
        page.locator("#panel").screenshot(path=str(OUT / "3_frame_done.png"))
        n, t0 = len(dialogs), time.time()
        page.click("#taskStage2 [data-task-run]")
        page.wait_for_function("() => !!taskRun", timeout=10000)
        page.wait_for_function(f"() => ({STAGE2})().spin", timeout=10000)
        s, s2 = page.evaluate(STAGE), page.evaluate(STAGE2)
        check("3단계 도는 중 — 그 묶음에만 동그라미·「멈춤」 · 2단계 단추는 꺼짐", s2["kind"] == "run" and s2["spin"] and s2["btn"] == "멈춤" and not s2["disabled"] and not s["spin"] and s["disabled"] and s["btn"] == "한 번에 진행", [s, s2])
        while page.evaluate("() => !!taskRun"):   # 끝날 때까지 — 지나간 단계 글을 모은다
            seen.add(page.evaluate("() => taskRun ? taskRun.key + ' — ' + taskRun.note : ''"))
            if time.time() - t0 > 1500:
                break
            page.wait_for_timeout(1000)
        took = time.time() - t0
        # 서버 실행의 거울(workflow_exec.js taskRunFollow)은 taskRun 을 먼저 비우고 끝 글을 남긴 뒤 자료를 다시 읽는다 — 끝 글과 다시 읽기(연결 목록)를 기다린다
        page.wait_for_function("() => !taskRun && !!taskRunLast && !taskFlow.linkBusy && !!taskFlow.links", timeout=180000)
        last = page.evaluate("() => taskRunLast")
        print("  단계 글:", sorted(x for x in seen if x), flush=True)
        check("3단계(매핑) 끝남 — 멈추지 않고 끝까지", bool(last) and last["ok"] and last["stage"] == "map", [last, f"{took:.0f}s"])
        check("3단계도 확인 창 없이(2026-11-18 · 내용 반영의 확인 창도 없음)", len(dialogs) == n, dialogs[n:])
        st, s = page.evaluate(STEPS), page.evaluate(STAGE2)
        states = {x["step"]: x["state"] for x in st}
        check("단계 — ①~④ 모두 완료 · 2단계 3/3 완료와 진행률 100%", [states.get(k) for k in ("files", "division", "link", "plan", "apply")] == ["done"] * 5
              and s["count"] == "3/3 완료" and s["progress"] == [3, 3] and s["kind"] == "done" and last["text"].startswith("연결됨") and "본문 블록" in last["text"] and "같은 이름 자리" in last["text"]   # 끝 글 = 서버 실행의 묶음 글(거울의 taskRunLast — 상태 줄은 다시 읽기 뒤 「모두 끝남」 일 수 있다: workflow_exec.js 쪽)
              and s["btn"] == "한 번에 진행" and s["disabled"] and not s["spin"], [states, s])
        check("3단계까지 끝나면 이어서 줄이 숨음(남은 묶음이 하나 이하)", not page.evaluate(CHAIN)["shown"], page.evaluate(CHAIN))
        check("실행 종료 뒤 진행 중·멈춤 표시 없음 · 번호와 완료·준비 중 표시 유지", not any(x["status"] in ("run", "halt") for x in st)
              and [x["no"] for x in st[1:]] == ["①", "②", "③", "④", "⑤", "⑥"] and [x["badge"] for x in st[1:6]] == ["완료", "건너뜀", "완료", "완료", "준비 중"]   # ② = LLM 을 못 써 「건너뜀」
              and st[6]["badge"] in ("다음 작업", "완료"), st)   # ⑥ 작성요령 삭제(3단계) — 2단계가 끝났으니 다음 작업(지울 안내가 있으면)
        doc = requests.get(f"{base}/api/docs/{report}", timeout=300).json()
        ev = [e["kind"] for e in requests.get(f"{base}/api/works/{report}/log", timeout=60).json()["events"]]
        check("연차보고서 — 편집 두 번(구분 기준 반영 · 내용 반영) · 실행 취소 2", doc["rev"] == rev0 + 2 and doc.get("undo") == 2, [rev0, doc["rev"], doc.get("undo"), ev[:12]])
        heads = [requests.get(f"{base}/api/docs/{w}/headings", timeout=300).json() for w in (plan, report)]
        check("두 문서의 헤딩 그래프·표 구조 — 3단계는 다시 분석하지 않았다(1 · 2단계가 끝내 둔 것 그대로) · 연차보고서의 분석은 구조 반영 뒤 문서의 것", all(h.get("stage2") and h.get("stage3") for h in heads)
              and heads[1]["stage3"]["meta"].get("run") == h1["stage3"]["meta"].get("run") and not any("헤딩·표 분석(스크립트)" in x for x in seen if x.startswith("link — "))
              and heads[1]["stage3"]["meta"]["rev"] >= rev0 + 1, [h["stage3"]["meta"].get("rev") for h in heads if h.get("stage3")])
        links = requests.get(f"{base}/api/docs/{report}/merge-links", timeout=300).json()
        fill_ev = next(e for e in requests.get(f"{base}/api/works/{report}/log", timeout=60).json()["events"] if e["kind"] == "mergeFill")
        check("같은 이름 자리(고정 자리)도 연결 목록·넣기 기록에 따로 실림", isinstance((links.get("fixed") or {}).get("counts"), dict) and "fixed" in fill_ev and "shaped" in fill_ev["tables"], [links.get("fixed"), {k: fill_ev.get(k) for k in ("tables", "fixed")}])
        # 3단계는 서버 실행기가 돈다(spec_워크플로우 ② §18-10 걸음 3) — 유료 LLM 셋(자리 연결 검토 · 빈 자리 검토 · 표 대응)은 서버가 부르고, 이 검사의 서버는 LLM 이 꺼져 있어 부르지 않고 글로 남긴다
        # (화면의 가짜 응답 · 요청 셈은 안 탄다 — 한 번만 부르는 규칙 · 결과 불명은 tests/test_workflow_fill.py 의 가짜 문이 본다). 확인 필요 자리는 비워 둔다
        check("LLM 검토 — 서버가 돈다(LLM 이 꺼진 서버: 부르지 않고 「LLM 검토는 못 함」 · 확인 필요는 비워 둠)", calls["llm"] == 0 and links["counts"]["ambiguous"] > 0 and "LLM 검토는 못 함" in last["text"], [calls, links["counts"], last["text"][:120]])
        # 빈 자리 검토(spec_병합 ② §5-4 8): 넣기 계획에 아직 안 물은 빈 자리(「추진목표」 칸 · 「- (정의)」 줄)가 있다 — 서버의 LLM 이 꺼져 있어 부르지 않지만 멈추지 않고 끝까지 간다.
        # 단추가 부르는 함수가 실제로 있는지도 본다(2026-11-12 — 「표 대응(LLM)」 단추의 fillMap 이 없어 표 대응이 한 번도 안 돌았다)
        check("빈 자리 검토 — 「빈 자리 검토는 못 함」(LLM 꺼짐 — 멈추지 않음) · 단추의 함수가 있음", calls["gaps"] == 0 and "빈 자리 검토는 못 함" in last["text"]
              and page.evaluate("() => typeof fillMap === 'function' && typeof fillGaps === 'function'"), [calls, last["text"]])
        check("사업계획서는 그대로(사전 반영의 편집 1뿐)", requests.get(f"{base}/api/docs/{plan}", timeout=300).json()["rev"] == ap1.json()["rev"])
        page.locator("#panel").screenshot(path=str(OUT / "3_done.png"))
        page.screenshot(path=str(OUT / "3_done_full.png"))

        # ---- 4. 다시 열기 — 지난 반영의 표식(서버 merge.json `filled` — 걸음 3: 표 칸만 채운 반영도 「내용 넣기」 의 끝)이 남아 3단계가 끝난 채다
        # (전에는 ③④ 의 「넣은 수」 가 화면 메모리라 다시 열면 1/3 으로 돌아가 「한 번에 진행」 을 다시 누를 수 있었다). 다시 돌릴 것이 없다 — 서버에 3단계를 시작시켜도 시작하지 않는다
        open_work(page, report)
        page.click("#toolTabTask")
        page.wait_for_function(f"() => {{ const s = ({STAGE2})(); return s && s.count === '3/3 완료' && ({STAGE})().count === '4/4 완료' && !taskFlow.linkBusy && !!taskFlow.links; }}", timeout=180000)
        st4 = {x["step"]: x for x in page.evaluate(STEPS)}
        check("다시 열면 — 2 · 3단계 모두 끝난 채(단추 꺼짐) · ③④ 는 「지난 반영이 끝나 있습니다」(본문 자리에 넣은 것이 없는 반영 — 「넣은 자리 0곳」 이라 적지 않는다) · 「넣기 계획 다시」",
              page.evaluate(STAGE)["disabled"] and page.evaluate(STAGE2)["disabled"] and st4["plan"]["text"].startswith("③표 안 연결 · 넣기 계획완료지난 반영이 끝나 있습니다") and "지난 반영이 끝나 있습니다" in st4["apply"]["text"]
              and "0곳" not in st4["plan"]["text"] + st4["apply"]["text"] and "넣기 계획 다시" in st4["plan"]["text"], [st4["plan"], st4["apply"]])
        n = len(dialogs)
        again = requests.post(f"{base}/api/works/{report}/flow/runs", json={"from": "map"}, timeout=120)
        doc2 = requests.get(f"{base}/api/docs/{report}", timeout=300).json()
        log2 = requests.get(f"{base}/api/works/{report}/log", timeout=60).json()["events"]
        ev2 = [e["kind"] for e in log2]
        print("  다시 돌리기:", again.status_code, again.json(), "rev", doc["rev"], "→", doc2["rev"], "기록", [(e["kind"], e.get("rev")) for e in log2 if e["kind"] not in ("create", "verify", "verified", "headings")], flush=True)
        check("다시 돌리기(서버에 3단계 시작 요청) — 남은 단계가 없어 시작하지 않음(409 noWork) · 확인 창 없음 · 구분 기준은 다시 반영 안 함 · 화면은 LLM 검토를 부르지 않음",
              again.status_code == 409 and again.json().get("reason") == "noWork" and len(dialogs) == n and calls["llm"] == 0 and ev2.count("divisions") == ev.count("divisions"), [again.status_code, again.text[:200], ev2[:6]])
        # 더 들어가지 않는다(2026-11-12 app/merge_tables.py 고침 — 전에는 이어 넣는 표에 행이 또 들어갔다: spec_병합 ③). 편집 차례는 하나 오를 수 있다 — 다시 열 때의 개요 줄 맞춤(outlineAlign), 넣기와 무관
        check("다시 돌리기 — 더 넣지 않음(넣기 기록 그대로 1번)", ev2.count("mergeFill") == ev.count("mergeFill") == 1, ev2.count("mergeFill"))
        third = requests.post(f"{base}/api/docs/{report}/merge-links/plan", timeout=300).json()
        check("또 계획해도 할 일 0", third.get("todo") == 0, {"todo": third.get("todo"), "tables": {k: third["tables"]["counts"].get(k) for k in ("cells", "rows")}})

        # ---- 5. 이어서 한 번에 1→3단계 — 1단계 초기화(API)로 연차보고서를 올린 원본으로 되돌린 뒤 「1→3단계」 하나로 구조 → 내용 → 작성요령 삭제까지(확인 창 없이 — 2026-11-18)
        rs = requests.post(f"{base}/api/docs/{report}/merge-links/reset", json={"stage": "frame"}, timeout=300)
        check("1단계 초기화(API — 사전 준비)", rs.status_code == 200, rs.status_code)
        KINDS = ("divisions", "mergeFill", "formCleanup")
        ev_r = [e["kind"] for e in requests.get(f"{base}/api/works/{report}/log", timeout=60).json()["events"]]
        open_work(page, report)
        page.click("#toolTabTask")
        page.wait_for_function(f"() => {{ const c = ({CHAIN})(); return c && c.shown && c.btns.clean.text === '2→4단계' && !c.btns.clean.disabled && !taskFlow.linkBusy; }}", timeout=180000)
        n, t0, chain_seen, order = len(dialogs), time.time(), set(), []
        page.evaluate("() => { taskRunLast = null; }")
        page.click("#taskChain [data-task-chain=clean]")
        page.wait_for_function("() => !!taskRun", timeout=10000)
        while page.evaluate("() => !!taskRun"):   # 끝날 때까지 — 도는 묶음 차례와 이어서 줄의 글을 모은다
            cur = page.evaluate("() => taskRun ? [taskRun.stage, document.querySelector('#taskChain .dv-chain-state').textContent, document.querySelector('#taskChain [data-task-chain=clean]').disabled] : null")
            if cur:
                if not order or order[-1] != cur[0]:
                    order.append(cur[0])
                chain_seen.add((cur[1], cur[2]))
            if time.time() - t0 > 2400:
                break
            page.wait_for_timeout(1000)
        took = time.time() - t0
        last, ends = page.evaluate("() => taskRunLast"), page.evaluate("() => taskRunEnds")
        print("  이어서 차례:", order, f"{took:.0f}s", {k: v["text"][:90] for k, v in (ends or {}).items()}, flush=True)
        check("이어서 2→4단계(구성은 확정된 채) — 확인 창 없이 · 세 묶음이 차례로 끝까지(멈춤 없음)", len(dialogs) == n
              and sorted(ends) == ["clean", "frame", "map"] and all(e["ok"] for e in ends.values()) and last["stage"] == "clean" and order == [x for x in ("frame", "map", "clean") if x in order],
              [order, {k: (v["ok"], v["text"][:80]) for k, v in (ends or {}).items()}, dialogs[n:]])
        check("도는 동안 — 이어서 줄에 「2→4단계 이어 진행 중 — 지금 …」 · 이어서 단추는 꺼짐", any(t.startswith("2→4단계 이어 진행 중 — 지금") and dis for t, dis in chain_seen), sorted(chain_seen)[:4])
        # 서버 실행의 거울은 taskRun 을 먼저 비우고 끝 글을 남긴 뒤 자료(연결 목록 · 지울 안내)를 다시 읽는다 — 다시 읽기가 끝난 뒤의 묶음 상태를 본다(끝 글 = 거울이 묶음마다 남긴 taskRunEnds: 상태 줄은 다시 읽은 뒤 「모두 끝남」 일 수 있다)
        page.wait_for_function(f"() => {{ const a = ({STAGE})(), b = ({STAGE2})(), c = ({STAGE3})(); return !taskRun && !taskFlow.linkBusy && !!taskFlow.links && a && b && c && a.kind === 'done' && b.kind === 'done' && c.kind === 'done'; }}", timeout=180000)
        s, s2, s3 = page.evaluate(STAGE), page.evaluate(STAGE2), page.evaluate(STAGE3)
        check("끝 — 묶음마다 끝 글이 남음(앞 묶음 것도) · 2단계 4/4(되돌린 뒤의 구조 반영이라 다시 분석도 함) · 3단계 3/3 · 4단계 끝", ends["frame"]["text"].startswith("구조를 맞췄습니다") and "연차보고서를 다시 분석했습니다" in ends["frame"]["text"]
              and ends["map"]["text"].startswith("연결됨") and "지웠습니다" in ends["clean"]["text"] and s3["kind"] == "done"
              and s["count"] == "4/4 완료" and s2["count"] == "3/3 완료", [s["text"][:60], s2["text"][:60], s3["text"][:90], s["count"], s2["count"], s3["count"]])
        ev5 = [e["kind"] for e in requests.get(f"{base}/api/works/{report}/log", timeout=60).json()["events"]]
        check("연차보고서 — 구조 반영 · 내용 반영 · 작성요령 삭제가 한 번씩 더(기록)", all(ev5.count(k) == ev_r.count(k) + 1 for k in KINDS), {k: (ev_r.count(k), ev5.count(k)) for k in KINDS})
        check("끝나면 이어서 줄이 숨음(남은 묶음 하나 이하)", not page.evaluate(CHAIN)["shown"], page.evaluate(CHAIN))
        left = requests.get(f"{base}/api/docs/{report}/form-cleanup", timeout=300).json()["counts"]["total"]
        g5 = requests.get(f"{base}/api/docs/{report}/form-guides", timeout=300).json()["saved"]
        check("4단계가 문서에서 지운 뒤에도 작성 지침은 저장돼 있다(지우기 바로 전에 남김 — 헤딩/표별)", left == 0 and bool(g5) and g5["counts"]["items"] >= 30 and g5["counts"]["headings"] > 10 and g5["counts"]["tables"] > 10, [left, g5 and g5["counts"]])
        page.locator("#panel").screenshot(path=str(OUT / "5_chain_done.png"))
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

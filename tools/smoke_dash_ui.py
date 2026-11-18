"""대시보드(패널 탭 「대시보드」 — app/static/dashboard.js · spec_작업에이전트 ② §9) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점 · 문서 편집은 모두 진짜.

- 양식 맞추기(plan_fit)를 TASK 카드로 시작 → 패널 탭 줄에 「대시보드」(에이전트와 작업 내용 사이) → 누르면 단계 흐름: 묶음 셋(준비 · 프로젝트 구성 · 구조 반영) · 단계 다섯(워크플로우 등록부 그대로 — 번호 · 이름 · 꼬리표 · 점선 = 안 해도 됨)
  · 상태(01 끝남 · 02 지금 — 펴짐) · 머리 「끝남 1/4」(안 해도 되는 단계는 안 셈) · 「다음: 02 …」 · 「구조 반영」 의 「한 번에 진행」 은 꺼짐(값 확정 전).
- 대시보드에서만: 「프로젝트 구성 입력 · 확정…」 → 폼(에이전트 질문 카드와 같은 폼 — 단추 「확정」 · 「문서에서 보기」 · 「구성 읽기」 · 「닫기」) → 「확정」 → 확정(문서 그대로) · 02 끝남 · 04 지금 → 「변경 계획 보기」 → 끝 글 · 문서 옆 열에 목록(탭은 대시보드 그대로)
  → 05 「문서에 반영」(제 확인 창) → 문서가 바뀜 · 「모두 끝남」.
- 단계를 누르면 펴고 접힘 · 「하는 일 · 조건」(등록부의 조건) · 좁은 패널에서 가로 넘침 없음 · 다시 그려도 초점 유지(1초 지켜보기) · 문서 일반 편집(doc_edit)의 흐름 · 「에이전트 보기 열기」 · 콘솔 오류 없음.
- TASK 가 없는 문서(TASK 없이 올림 → #w=) — 탭은 보이고 「TASK 고르기」 카드 → 「이 TASK 로」 → 문서에 TASK 가 적히고 그 자리에서 단계 흐름(② §9 「TASK 가 없을 때」).

    python -X utf8 tools/smoke_dash_ui.py <출력 폴더> [--port 18471]
"""
import argparse
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
ap.add_argument("--port", type=int, default=18471)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1"}
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL"):
    env.pop(k, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:900] if detail != "" and not ok else ""), flush=True)
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


NODES = """() => [...document.querySelectorAll('#paneDash .dash-node')].map((n) => ({ key: n.dataset.key, state: n.dataset.state, no: n.querySelector('.dash-no').textContent, name: n.querySelector('.dash-node-main b').textContent,
  st: (n.querySelector('.dash-st') || {}).textContent || '', tags: [...n.querySelectorAll('.dash-tag')].map((t) => t.textContent), opt: n.classList.contains('opt'), open: !!n.querySelector('.dash-detail'),
  acts: [...n.querySelectorAll('.dash-detail > .dash-acts button, .dash-detail > .dash-acts a')].map((b) => [b.textContent, b.disabled, b.classList.contains('primary')]) }))"""
HEAD = """() => ({ title: (document.querySelector('#paneDash .dash-title b') || {}).textContent, count: (document.querySelector('#paneDash .dash-count') || {}).textContent || '',
  next: (document.querySelector('#paneDash .dash-next') || {}).textContent || '', last: (document.querySelector('#paneDash .dash-last') || {}).textContent || '', lastHalt: !!document.querySelector('#paneDash .dash-last.halt'),
  groups: [...document.querySelectorAll('#paneDash .dash-ghead')].map((g) => [g.querySelector('.dash-gno').textContent, g.querySelector('.dash-gname').textContent, (g.querySelector('button') || {}).textContent || '', !!(g.querySelector('button') || {}).disabled]),
  tool: document.getElementById('panel').dataset.tool, wf: (document.querySelector('#paneDash .dash-wf') || {}).href || '' })"""


def node(page, key):
    return next((n for n in page.evaluate(NODES) if n["key"] == key), None)


def main():
    wait_server()
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        dialogs = []
        page.on("dialog", lambda d: (dialogs.append(d.message[:80]), d.accept()))
        page.goto(base)
        page.wait_for_selector("#taskCards .task-card")
        with page.expect_file_chooser() as fc:
            page.click('#taskCards [data-task="plan_fit"]')
        fc.value.set_files(str(PLAN))
        page.wait_for_selector("#doc .para", timeout=120000)
        page.wait_for_function("() => !document.getElementById('tabDash').hidden && document.getElementById('panel').dataset.tool === 'Div'", timeout=30000)   # TASK 시작(taskEnter)이 「작업 내용」 을 연 뒤에
        tabs = page.evaluate("() => [...document.querySelectorAll('#toolTabs button[role=tab]')].filter((b) => !b.hidden).map((b) => b.textContent)")
        check("탭 줄에 「대시보드」 — 「에이전트」 와 「작업 내용」 사이", tabs[:3] == ["에이전트", "대시보드", "작업 내용"], tabs)

        page.click("#tabDash")
        page.wait_for_selector("#paneDash .dash-node", timeout=30000)
        page.wait_for_function("() => document.querySelector('#paneDash .dash-node[data-key=values]')?.dataset.state === 'now'", timeout=30000)
        h, nodes = page.evaluate(HEAD), page.evaluate(NODES)
        check("탭을 누르면 패널이 대시보드 — 머리 TASK 이름 · 「워크플로우 ↗」(그 TASK 절)", h["tool"] == "Dash" and h["title"] == "사업계획서 양식 맞추기" and h["wf"].endswith("/workflow#plan_fit"), h)
        check("묶음 셋 — 1 준비 · 2 프로젝트 구성 · 3 구조 반영(「한 번에 진행」 은 구조 반영에만 · 값 확정 전이라 꺼짐)",
              [g[:2] for g in h["groups"]] == [["1", "준비"], ["2", "프로젝트 구성"], ["3", "구조 반영"]] and h["groups"][2][2] == "한 번에 진행" and h["groups"][2][3] and not h["groups"][0][2], h["groups"])
        check("단계 다섯(등록부 그대로) — 01 문서 올리기 · 첫 분석 · 02 프로젝트 구성 값 정하기 · 03 구분 기준 자리 확인(점선 · 안 해도 됨) · 04 변경 계획 보기 · 05 반영(문서 바뀜)",
              [n["no"] for n in nodes] == ["01", "02", "03", "04", "05"] and [n["key"] for n in nodes] == ["open", "values", "review", "plan", "apply"]
              and nodes[1]["name"] == "프로젝트 구성 값 정하기" and nodes[2]["opt"] and "안 해도 됨" in nodes[2]["tags"] and "LLM" in nodes[2]["tags"] and "문서 바뀜" in nodes[4]["tags"] and "사람" in nodes[1]["tags"], nodes)
        check("상태 — 01 ✓ 끝남 · 02 지금(펴짐 · 단추 「구성 읽기」 · 「프로젝트 구성 입력 · 확정…」) · 04 · 05 남음 · 03 은 상태 글 없음",
              nodes[0]["state"] == "done" and nodes[0]["st"] == "✓ 끝남" and nodes[1]["state"] == "now" and nodes[1]["open"] and not any(n["open"] for n in nodes if n["key"] != "values")
              and [a[0] for a in nodes[1]["acts"]] == ["구성 읽기", "프로젝트 구성 입력 · 확정…"] and nodes[3]["state"] == "todo" and nodes[4]["state"] == "todo" and nodes[2]["st"] == "", nodes)
        check("머리 「끝남 1/4」(안 해도 되는 단계는 안 셈) · 「다음: 02 프로젝트 구성 값 정하기」", h["count"] == "끝남 1/4" and h["next"] == "다음: 02 프로젝트 구성 값 정하기", h)
        page.screenshot(path=str(OUT / "01_dash.png"))
        page.locator("#paneDash").screenshot(path=str(OUT / "01_pane.png"))

        # ---- 단계를 누르면 펴고 접힘 · 「하는 일 · 조건」
        page.click('#paneDash .dash-node[data-key=apply] .dash-node-head')
        page.wait_for_selector('#paneDash .dash-node[data-key=apply] .dash-detail')
        cond = page.evaluate("""() => { const d = document.querySelector('#paneDash .dash-node[data-key=apply] .dash-detail'); d.querySelector('.dash-more').open = true;
          return { dts: [...d.querySelectorAll('.dash-cond dt')].map((x) => x.textContent), need: (d.querySelector('.dash-text .dash-sub') || {}).textContent || '', values: !!document.querySelector('#paneDash .dash-node[data-key=values] .dash-detail'),
            expanded: document.querySelector('#paneDash .dash-node[data-key=apply] .dash-node-head').getAttribute('aria-expanded') }; }""")
        check("다른 단계를 누르면 그 카드만 펴짐(aria-expanded) — 차례가 아니면 「하려면」 · 「하는 일 · 조건」 에 등록부의 조건(하려면 · 끝난 것으로 보는 때 · 멈추는 때 · 남기는 것)",
              cond["expanded"] == "true" and not cond["values"] and cond["need"] == "하려면" and cond["dts"][:2] == ["하는 일", "나오는 것"] and {"하려면", "끝난 것으로 보는 때", "멈추는 때", "남기는 것 · 보정"} <= set(cond["dts"]), cond)
        page.click('#paneDash .dash-node[data-key=values] .dash-node-head')
        page.wait_for_selector('#paneDash .dash-node[data-key=values] .dash-detail')

        # ---- 대시보드에서만: 값 입력 → 확정
        doc = page.evaluate("state.id")
        rev0 = requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"]
        page.click('#paneDash .dash-node[data-key=values] .dash-acts button:has-text("프로젝트 구성 입력")')
        page.wait_for_selector("#paneDash .agw-form [data-agw=confirm]")
        names = page.evaluate("() => [...document.querySelectorAll('#paneDash .dash-node[data-key=values] .dash-detail button')].map((b) => b.textContent)")
        check("폼을 편 카드의 단추 넷 — 「확정」 · 「문서에서 보기」(폼) · 「구성 읽기」 · 「닫기」(단계): 2026-11-18 사용자가 줄인 이름", names == ["확정", "문서에서 보기", "구성 읽기", "닫기"], names)
        page.locator("#paneDash .dash-node[data-key=values]").screenshot(path=str(OUT / "01b_form.png"))
        page.fill("#paneDash [data-agw=years0]", "3")
        page.wait_for_timeout(1300)   # 1초 지켜보기가 지나도 폼이 그대로(적는 동안 다시 그리지 않음)
        page.focus("#paneDash [data-agw=lead]")
        page.fill("#paneDash [data-agw=lead]", "한국선급")
        page.wait_for_timeout(1300)
        kept = page.evaluate("() => ({ y: document.querySelector('#paneDash [data-agw=years0]').value, focus: document.activeElement === document.querySelector('#paneDash [data-agw=lead]') })")
        check("폼(에이전트 질문 카드와 같은 폼)이 펼친 카드 안에 · 적는 동안 다시 그려도 값 · 초점이 그대로", kept == {"y": "3", "focus": True}, kept)
        page.fill("#paneDash [data-agw=joint]", "씨드로닉스\n유엔젤")
        page.click("#paneDash [data-agw=confirm]")
        page.wait_for_function("() => document.querySelector('#paneDash .dash-node[data-key=values]')?.dataset.state === 'done'", timeout=60000)
        page.wait_for_function("() => document.querySelector('#paneDash .dash-node[data-key=plan]')?.dataset.state === 'now'", timeout=30000)
        h = page.evaluate(HEAD)
        div = requests.get(f"{base}/api/docs/{doc}/divisions", timeout=30).json()
        check("「확정」 → 확정(1단계 3차년도 · 주관 한국선급 · 공동 2 — 문서 그대로) · 끝 글 「프로젝트 구성 확정 — …」 · 02 끝남 · 04 지금 · 머리 「끝남 2/4」",
              (div.get("confirmed") or {}).get("values", {}).get("stages") == [3] and div["confirmed"]["values"]["orgs"]["joint"] == ["씨드로닉스", "유엔젤"]
              and h["last"].startswith("프로젝트 구성 확정") and not h["lastHalt"] and h["count"] == "끝남 2/4" and h["next"] == "다음: 04 변경 계획 보기"
              and requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"] == rev0 and not h["groups"][2][3], [h, div.get("confirmed")])
        page.screenshot(path=str(OUT / "02_confirmed.png"))

        # ---- 변경 계획(문서 옆 열 · 탭 그대로)
        page.click('#paneDash .dash-node[data-key=plan] .dash-acts button:has-text("변경 계획")')
        page.wait_for_function("() => /변경 계획 — |현재 프로젝트 구성/.test(document.querySelector('#paneDash .dash-last')?.textContent || '')", timeout=120000)
        page.wait_for_function("() => document.querySelector('#paneDash .dash-node[data-key=apply]')?.dataset.state === 'now'", timeout=30000)
        h, n5 = page.evaluate(HEAD), node(page, "apply")
        check("「변경 계획 보기」 → 끝 글 · 문서 옆 열에 목록 · 패널은 대시보드 그대로 · 05 지금(「문서에 반영」)",
              h["tool"] == "Dash" and page.evaluate("() => !document.getElementById('headsDlg').hidden") and n5["open"] and any(a[0] == "문서에 반영" for a in n5["acts"]), [h, n5])
        page.screenshot(path=str(OUT / "03_plan.png"))

        # ---- 반영(제 확인 창) → 문서가 바뀜 · 모두 끝남
        n_dialogs = len(dialogs)
        page.click('#paneDash .dash-node[data-key=apply] .dash-acts button:has-text("문서에 반영")')
        page.wait_for_function("() => document.querySelector('#paneDash .dash-node[data-key=apply]')?.dataset.state === 'done'", timeout=180000)
        page.wait_for_function("() => (document.querySelector('#paneDash .dash-next') || {}).textContent === '모두 끝남'", timeout=30000)
        page.wait_for_function("() => /^문서에 반영 — /.test((document.querySelector('#paneDash .dash-last') || {}).textContent || '')", timeout=60000)   # 반영 뒤 문서를 다시 읽는 동안은 「하는 중」 줄
        h = page.evaluate(HEAD)
        rev1 = requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"]
        check("「문서에 반영」 → 확인 창 한 번(「작업 내용」 의 ② 반영과 같은 창) → 문서가 바뀜 · 끝 글 「문서에 반영 — 문서에 반영했습니다 …」 · 「모두 끝남」 · 「끝남 4/4」 · 「한 번에 진행」 꺼짐",
              len(dialogs) == n_dialogs + 1 and rev1 > rev0 and h["last"].startswith("문서에 반영 — 문서에 반영했습니다") and h["count"] == "끝남 4/4" and h["groups"][2][3], [dialogs[n_dialogs:], rev0, rev1, h])
        page.screenshot(path=str(OUT / "04_done.png"))

        # ---- 좁은 패널 · 다른 탭으로 갔다 와도 그대로
        page.set_viewport_size({"width": 1100, "height": 900})
        page.wait_for_timeout(500)
        w = page.evaluate("""() => { const p = document.getElementById('paneDash'), r = document.getElementById('panel').getBoundingClientRect();
          return { over: p.scrollWidth > p.clientWidth + 1, panel: Math.round(r.width), inside: [...p.querySelectorAll('.dash-node, .dash-ghead .btn')].every((c) => c.getBoundingClientRect().right <= r.right + 0.5) }; }""")
        check("좁은 패널에서 가로로 넘치지 않는다(카드 · 단추가 패널 안)", not w["over"] and w["inside"], w)
        page.locator("#paneDash").screenshot(path=str(OUT / "05_narrow.png"))
        page.set_viewport_size({"width": 1600, "height": 1000})
        page.click("#toolTabTask")
        page.click("#tabDash")
        page.wait_for_selector("#paneDash .dash-node[data-key=apply][data-state=done]", timeout=30000)
        check("다른 탭에 갔다 와도 같은 상태(모두 끝남)", page.evaluate(HEAD)["next"] == "모두 끝남")

        # ---- 이관(두 문서) — 「작업 내용」 의 단계 · 묶음 넷 · 등록부의 세부 단계는 「그 단계로」 · 「이어서 한 번에」
        page.goto(base)
        page.wait_for_selector("#taskCards .task-card")
        with page.expect_file_chooser() as fc:
            page.locator("#pickBtn").click()
        fc.value.set_files([str(ROOT / "samples" / "기술수요조사서.hwpx"), str(PLAN)])
        page.wait_for_function("() => document.querySelectorAll('#homeFiles .hf-row').length >= 2")
        page.locator("#homeFiles .hf-row").nth(0).locator("input[type=radio]").check()
        page.locator("#homeFiles [data-hf-focus=project]").fill("대시보드 P")
        page.locator("#taskCards [data-task=plan_to_report]").click()
        page.wait_for_function("() => state.id && state.task.job === 'plan_to_report' && document.getElementById('panel').dataset.tool === 'Div'", timeout=120000)
        page.wait_for_function("() => { const s = document.querySelector('#paneDiv select[data-task-file=plan]'); return !!s && !!s.value; }", timeout=120000)
        page.click("#tabDash")
        page.wait_for_function("() => document.querySelector('#paneDash .dash-node[data-key=files]')?.dataset.state === 'done'", timeout=60000)
        h, nodes = page.evaluate(HEAD), page.evaluate(NODES)
        by = {n["key"]: n for n in nodes}
        check("이관 — 묶음 넷(1단계 프로젝트 구성 … 4단계) · 묶음마다 「한 번에 진행」(할 일이 남은 첫 묶음만 켜짐) · 준비 끝남 · 프로젝트 구성 확정이 지금",
              len(h["groups"]) == 4 and h["groups"][0][0] == "1단계" and all(g[2] == "한 번에 진행" for g in h["groups"]) and not h["groups"][0][3] and all(g[3] for g in h["groups"][1:])
              and by["files"]["state"] == "done" and by["config"]["state"] == "now" and by["later"]["state"] == "soon" and by["later"]["st"] == "준비 중", [h, [(n["key"], n["state"]) for n in nodes]])
        top = page.evaluate("() => [...document.querySelectorAll('#paneDash .dash-top button')].map((b) => b.textContent)")
        check("머리 아래 「이어서 한 번에 1→4단계」(「작업 내용」 의 이어 진행과 같은 범위)", top == ["이어서 한 번에 1→4단계"], top)
        page.click('#paneDash .dash-node[data-key=llm] .dash-node-head')
        via = page.evaluate("() => { const d = document.querySelector('#paneDash .dash-node[data-key=llm] .dash-detail'); return { text: d.querySelector('.dash-text').textContent, btn: (d.querySelector('.dash-acts button') || {}).textContent }; }")
        page.click('#paneDash .dash-node[data-key=llm] .dash-acts button')
        page.wait_for_selector('#paneDash .dash-node[data-key=link] .dash-detail')
        check("등록부의 세부 단계(자리 연결 LLM 검토)는 「「자리 연결」 의 단추로 함께」 + 「그 단계로」 → ② 자리 연결 카드가 펴짐", "「자리 연결」" in via["text"] and via["btn"] == "그 단계로", via)
        page.locator("#paneDash").screenshot(path=str(OUT / "06_relay.png"))

        # ---- TASK 가 없는 문서 — 탭은 늘 보이고 「TASK 고르기」 → 고르면 그 자리에서 단계 흐름(2026-11-18 사용자 「여기 탭에 넣어 달라고 했는데 보이질 않아」 — ② §9 「TASK 가 없을 때」)
        with PLAN.open("rb") as f:
            bare = requests.post(f"{base}/api/docs?new=1", files={"file": (PLAN.name, f)}, timeout=180).json()["docId"]
        page.goto(f"{base}/#w={bare}")
        page.wait_for_selector("#doc .para", timeout=120000)
        page.wait_for_function(f"() => state.id === '{bare}' && !(state.task || {{}}).job && !document.getElementById('tabDash').hidden", timeout=30000)
        page.click("#tabDash")
        page.wait_for_function("() => document.querySelectorAll('#paneDash .dash-pick .dash-text.muted').length > 0", timeout=30000)   # 등록부를 읽어 묶음 차례까지
        picks = page.evaluate("""() => ({ title: (document.querySelector('#paneDash .dash-title b') || {}).textContent, next: (document.querySelector('#paneDash .dash-next') || {}).textContent || '',
          jobs: [...document.querySelectorAll('#paneDash .dash-pick')].map((p) => p.dataset.job), flow: (document.querySelector('#paneDash .dash-pick[data-job=plan_merge] .dash-text.muted') || {}).textContent || '',
          btn: (document.querySelector('#paneDash .dash-pick[data-job=plan_fit] button') || {}).textContent || '', over: document.getElementById('paneDash').scrollWidth > document.getElementById('paneDash').clientWidth + 1 })""")
        check("TASK 가 없는 문서 — 탭 「대시보드」 가 보이고 누르면 「TASK 고르기」: hwpx 로 할 수 있는 TASK 카드(준비 중인 연차보고서 취합은 없음) · 묶음 차례 · 「이 TASK 로」",
              picks["title"] == "TASK 고르기" and "TASK 가 없습니다" in picks["next"] and {"plan_fit", "plan_merge", "plan_to_report", "doc_edit", "style_copy"} <= set(picks["jobs"]) and "report_merge" not in picks["jobs"]
              and picks["flow"] == "프로젝트 구성 › 문서 프레임 작성 › 내용 매핑" and picks["btn"] == "이 TASK 로" and not picks["over"], picks)
        page.locator("#paneDash").screenshot(path=str(OUT / "07_pick.png"))
        page.click('#paneDash .dash-pick[data-job=plan_fit] button')
        page.wait_for_function("() => (state.task || {}).job === 'plan_fit' && !!document.querySelector('#paneDash .dash-node[data-key=values]')", timeout=60000)
        h = page.evaluate(HEAD)
        lst = requests.get(f"{base}/api/works", timeout=30).json()
        saved = next((w for w in (lst if isinstance(lst, list) else lst.get("works", [])) if w.get("id") == bare), {})
        check("「이 TASK 로」 → 문서에 TASK 가 적힘(서버) · 패널은 대시보드 그대로 · 그 자리에서 양식 맞추기 단계 흐름",
              (saved.get("task") or {}).get("job") == "plan_fit" and h["tool"] == "Dash" and h["title"] == "사업계획서 양식 맞추기" and [g[1] for g in h["groups"]] == ["준비", "프로젝트 구성", "구조 반영"], [saved.get("task"), h])
        page.locator("#paneDash").screenshot(path=str(OUT / "08_picked.png"))

        # ---- 문서 일반 편집 — 끝을 세지 않는 흐름 · 「에이전트 보기 열기」
        page.goto(base)
        page.wait_for_selector("#taskCards .task-card")
        with page.expect_file_chooser() as fc:
            page.click('#taskCards [data-task="doc_edit"]')
        fc.value.set_files(str(ROOT / "samples" / "기술수요조사서.hwpx"))
        page.wait_for_selector('#doc .para, .sf-pop [data-sf="new"]', timeout=120000)
        if page.locator('.sf-pop [data-sf="new"]').count():   # 이관에서 쓴 같은 파일 — 「같은 파일 고르기」 창(spec_작업 ② §1)에서 새 작업으로
            page.click('.sf-pop [data-sf="new"]')
        page.wait_for_selector("#doc .para", timeout=120000)
        page.wait_for_function("() => !document.getElementById('tabDash').hidden && document.getElementById('panel').dataset.tool === 'Agent'", timeout=30000)   # 일반 편집의 시작 보기 = 에이전트
        page.click("#tabDash")
        page.wait_for_selector("#paneDash .dash-node", timeout=30000)
        h, nodes = page.evaluate(HEAD), page.evaluate(NODES)
        check("문서 일반 편집 — 묶음 셋(준비 · 요청 → 제안 → 반영 · 서식 · 표 다시 쓰기) · 01 끝남 · 나머지는 상태 글 없음(되풀이) · 「한 번에 진행」 없음",
              [g[1] for g in h["groups"]] == ["준비", "요청 → 제안 → 반영", "서식 · 표 다시 쓰기"] and nodes[0]["state"] == "done" and all(n["st"] == "" for n in nodes[1:]) and not any(g[2] for g in h["groups"]), [h, nodes])
        page.click('#paneDash .dash-node[data-key=turn] .dash-node-head')
        page.click('#paneDash .dash-node[data-key=turn] .dash-acts button:has-text("에이전트 보기 열기")')
        page.wait_for_function("() => document.getElementById('panel').dataset.tool === 'Agent'", timeout=10000)
        check("「에이전트 보기 열기」 → 패널 「에이전트」", True)
        b.close()
    real = [e for e in errors if "400" not in e and "503" not in e]
    check("콘솔 오류 없음", not real, real[:5])


try:
    main()
finally:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'OK' if not fails else 'FAIL'} — 실패 {len(fails)}" + (f": {fails}" if fails else ""))
sys.exit(1 if fails else 0)

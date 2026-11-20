"""작업 진행 에이전트(spec_작업에이전트 — app/static/doc_agent_work.js · app/work_guide.py · app/work_guide_api.py) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.
LLM 이 꺼져 있으므로 에이전트의 답은 스크립트 답(`work_guide.fallback`)이다 — 끝점·문서 편집은 모두 진짜.

- 첫 화면: 오른쪽에 에이전트 대화창(#homeAgent — 글 칸 · 「파일」 · 「보내기」) · 글만 보내면 파일을 올리라고 답 · 파일을 올리고 보내면 TASK 를 묻는 질문 카드.
- 질문 카드에서 「사업계획서 양식 표준화」 → **문서 화면으로 넘어가지 않고** 위 대시보드(#homeDash)에 그 워크플로우가 골라짐 + 대화에 한 줄(spec_작업에이전트 ② §10 — 2026-11-20: 전에는 그 작업이 바로 열렸다).
- 문서 화면으로 바로 시작하는 길(왼쪽 워크플로우 카드) → 그 작업이 열리고 패널 「에이전트」 로 대화가 이어짐(첫 화면의 말 + 시작 턴) · 진행 줄(1단계 프로젝트 구성 지금 · 2단계 헤딩 추출 · 3단계 표 남음).
- 연쇄: 「구성 읽기」(문서에서 읽기 — 바로 실행) → 값이 없어 질문 카드(프로젝트 구성 폼) → 「확정」 → 변경 계획(바로 실행 — 문서 옆 열에 목록) → 실행 카드 「문서에 반영」(문서 바뀜 — 「진행」 을 눌러야).
  계획에 미해결 자리가 있어 스크립트 답이 질문 카드로 고르게 하면 — 고른 「문서에 반영」 도 바로 돌지 않고 실행 카드로 묻는다(고른 것은 승인이 아니다).
- 「진행」 → 문서가 바뀜(편집 차례 +1) → 결과 턴 — 1단계 끝남 · 「지금 차례는 「헤딩 LLM 판정 …」」(LLM 끔 — 2 · 3단계 LLM 행동은 내지 않음).
- 2 · 3단계 행동(spec_양식표준화 ② §5 — LLM 을 쓸 수 있다고 보고 셈 · 실행 함수는 바꿔 끼움 · 분석 상태는 끝점의 답을 흉내): heads_llm(첫째 · 유료) · tables_llm → headsPickRun([l2]|[l3], {asked}) ·
  헤딩 판정을 거쳤고 계획이 있으면 heads_apply(문서 바뀜 · key = 계획 표시) → tpbApply({plans}).
- 다시 열어도 대화(진행 턴 · 카드의 끝)가 그대로 · 「작업 설명」 으로 다시 설명 · 패널 폭에서 가로 넘침 없음 · 콘솔 오류 없음.

    python -X utf8 tools/smoke_work_guide_ui.py <출력 폴더> [--port 18451]
"""
import argparse
import copy
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
ap.add_argument("--port", type=int, default=18451)
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


TURNS = """() => [...document.querySelectorAll('#paneAgent .agw-turn')].map((t) => ({ event: t.dataset.event, say: (t.querySelector('.agw-reply') || {}).textContent || '',
  ask: (t.querySelector('.agw-ask') || { dataset: {} }).dataset.ask || '', act: (t.querySelector('.agw-act') || { dataset: {} }).dataset.act || '', state: (t.querySelector('.agw-card') || { dataset: {} }).dataset.state || '',
  out: (t.querySelector('.agw-card .ag-state') || {}).textContent || '' }))"""
STEPS = "() => [...document.querySelectorAll('#paneAgent .agw-turn:last-child .agw-step')].map((s) => [s.querySelector('b').textContent, s.dataset.state])"
FAKE = {"v": None}   # 분석 상태 끝점(GET …/analysis)의 흉내 — None 이면 진짜


def main():
    wait_server()
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page.add_init_script("try { localStorage.setItem('nfm.agentDock', 'panel'); } catch (e) {}")  # 에이전트 보기를 패널 탭 자리로(창 머리 「패널에 넣기」 와 같음) — 떠 있는 창(기본)은 smoke_agent_float_ui.py
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.route(re.compile(r"/api/docs/[^/]+/analysis$"), lambda route: route.continue_() if FAKE["v"] is None else route.fulfill(json=FAKE["v"]))
        page.goto(base)
        page.wait_for_selector("#homeAgent .agh-talk")
        h = page.evaluate("""() => { const a = document.getElementById('homeAgent').getBoundingClientRect(), c = document.querySelector('.home-content').getBoundingClientRect(), box = document.getElementById('empty');
          return { right: a.left >= c.right - 1, w: Math.round(a.width), inside: a.right <= innerWidth + 0.5, title: document.querySelector('.agh-head h2').textContent, hint: !!document.querySelector('.agh-hint'),
            send: document.querySelector('[data-agh=send]').disabled, pick: !!document.querySelector('[data-agh=pick]'), over: box.scrollWidth > box.clientWidth + 1, cards: document.querySelectorAll('#taskCards .task-card').length }; }""")
        check("첫 화면 오른쪽에 에이전트 대화창(폭 340~420px · 안내 글 · 글 칸 · 「파일」 · 「보내기」 꺼짐) — TASK 카드는 그대로 · 가로 넘침 없음",
              h["right"] and 340 <= h["w"] <= 420 and h["inside"] and h["title"] == "에이전트" and h["hint"] and h["send"] and h["pick"] and not h["over"] and h["cards"] >= 6, h)
        page.screenshot(path=str(OUT / "01_home.png"))

        # ---- 첫 화면: 글만 → 파일을 올리라고 · 파일 → TASK 를 묻는 카드
        page.fill("#homeAgentText", "사업계획서 양식을 맞추고 싶어")
        page.click("[data-agh=send]")
        page.wait_for_function("() => document.querySelectorAll('#homeAgent .agh-talk .agw-say').length === 1", timeout=20000)
        t = page.evaluate("() => [...document.querySelectorAll('#homeAgent .agh-talk > p')].map((x) => [x.className.includes('ag-q') ? 'me' : 'agent', x.textContent])")
        check("글만 보내면 — 내 글 + 에이전트 「문서를 올려 주세요」(파일이 없으면 시작하지 않는다)", t[0] == ["me", "사업계획서 양식을 맞추고 싶어"] and t[1][0] == "agent" and "올려" in t[1][1], t)
        with page.expect_file_chooser() as fc:
            page.click("[data-agh=pick]")
        fc.value.set_files(str(PLAN))
        page.wait_for_selector("#homeAgent .agh-file")
        page.click("[data-agh=send]")
        page.wait_for_selector("#homeAgent .agw-ask .agw-opt", timeout=20000)
        opts = page.evaluate("() => [...document.querySelectorAll('#homeAgent .agw-opt')].map((o) => [o.dataset.value, o.querySelector('b').textContent])")
        check("파일을 올리고 보내면 — 질문 카드 「어느 워크플로우로 시작할까요?」(시작할 수 있는 워크플로우만 · 준비 중인 것 없음)",
              ["start:plan_fit", "사업계획서 양식 표준화"] in opts and all(v.startswith("start:") for v, _ in opts) and "start:report_merge" not in [v for v, _ in opts] and len(opts) >= 5, opts)
        page.screenshot(path=str(OUT / "02_home_ask.png"))

        # ---- 워크플로우를 고르면 — 문서 화면으로 넘어가지 않고 위 대시보드에 그 워크플로우가 골라진다(spec_작업에이전트 ② §10 「첫 화면의 대시보드」 — 2026-11-20: 전에는 그 작업이 문서 화면으로 열렸다)
        page.click('#homeAgent .agw-opt[data-value="start:plan_fit"]')
        page.wait_for_selector("#homeDash[data-state=ready] .dash-group", timeout=20000)
        pk = page.evaluate("""() => { const d = document.getElementById('homeDash'), says = [...document.querySelectorAll('#homeAgent .agh-talk .agw-say')].map((x) => x.textContent), b = d.querySelector('[data-hd-focus=start]') || {};
          return { title: d.querySelector('.dash-title b').textContent, groups: [...d.querySelectorAll('.dash-gname')].map((x) => x.textContent), start: b.textContent, off: b.disabled, say: says[says.length - 1],
            home: document.body.classList.contains('no-doc'), id: state.id, files: hf.files.length, ask: !!document.querySelector('#homeAgent .agw-ask') }; }""")
        check("질문 카드에서 워크플로우를 고르면 — 문서 화면으로 넘어가지 않고 위 대시보드에 「사업계획서 양식 표준화」 가 골라진다(단계 흐름 · 「워크플로우 시작」) · 대화에 한 줄 · 아직 아무것도 안 올림",
              pk["title"] == "사업계획서 양식 표준화" and pk["groups"] == ["프로젝트 구성", "헤딩 추출", "표"] and pk["start"] == "워크플로우 시작" and not pk["off"]
              and pk["say"] == "대시보드에 「사업계획서 양식 표준화」 를 골랐습니다 — 위 「워크플로우 시작」 을 누르면 문서를 준비합니다(문서 화면으로 바로 시작하려면 왼쪽 워크플로우 카드)."
              and pk["home"] and pk["id"] is None and pk["files"] == 1 and not pk["ask"] and requests.get(f"{base}/api/works", timeout=10).json() == [], pk)
        page.screenshot(path=str(OUT / "02b_home_dash_pick.png"))

        # ---- 문서 화면으로 바로 시작하는 길은 전처럼 왼쪽 워크플로우 카드 — 그 작업이 열리고 대화가 패널 「에이전트」 로 이어진다(첫 화면에서 나눈 말을 그 시작 턴이 가져간다)
        page.click('#taskCards [data-task="plan_fit"]')
        page.wait_for_selector("#doc .para", timeout=120000)
        page.wait_for_selector('#paneAgent .agw-ask[data-ask="config"] [data-agw=confirm]', timeout=90000)   # 시작 턴 → 문서에서 읽기(바로) → 결과 턴 = 프로젝트 구성 폼
        turns = page.evaluate(TURNS)
        st = page.evaluate("""() => { const first = document.querySelector('#paneAgent .agw-turn'); return { tool: document.getElementById('panel').dataset.tool, shown: !document.getElementById('paneAgent').hidden,
          carry: [...first.querySelectorAll('.ag-q')].map((x) => x.textContent), steps: [...first.querySelectorAll('.agw-step')].map((s) => [s.querySelector('b').textContent, s.dataset.state]),
          meta: first.querySelector('.ag-meta').textContent, task: (state.task || {}).job, guide: !document.querySelector('[data-ag-act=guide]').hidden }; }""")
        check("작업이 TASK 「사업계획서 양식 표준화」 로 열리고 패널 「에이전트」 가 보인다 — 첫 화면의 말이 시작 턴 앞에 이어짐 · 「작업 설명」 단추",
              st["tool"] == "Agent" and st["shown"] and st["task"] == "plan_fit" and "사업계획서 양식을 맞추고 싶어" in st["carry"][0] and "사업계획서 양식 표준화" in st["carry"] and st["guide"], st)
        check("시작 턴 — 설명(스크립트 답) + 진행 줄(1단계 프로젝트 구성 지금 · 2단계 헤딩 추출 · 3단계 표 남음) + 행동 「구성 읽기」(문서에서 읽기)를 바로 실행",
              turns[0]["event"] == "start" and "「사업계획서 양식 표준화」" in turns[0]["say"] and st["steps"] == [["1단계 프로젝트 구성", "now"], ["2단계 헤딩 추출", "todo"], ["3단계 표", "todo"]]
              and turns[0]["act"] == "config_read" and turns[0]["state"] == "done" and turns[0]["out"].startswith("실행함") and "스크립트 답" in st["meta"], [turns[0], st])
        check("결과 턴 — 읽을 값이 없어 질문 카드(프로젝트 구성 폼: 단계 수 · 차년도 수 · 주관 · 공동 · 당해 차년도 · 단추 「확정」 · 「문서에서 보기」 — 2026-11-18 줄인 이름)",
              len(turns) == 2 and turns[1]["event"] == "result" and turns[1]["ask"] == "config" and turns[1]["state"] == "open"
              and page.evaluate("() => ['stages', 'years0', 'lead', 'joint', 'current', 'read', 'confirm'].every((k) => document.querySelector(`#paneAgent [data-agw=${k}]`))")
              and page.evaluate("() => ['confirm', 'read'].map((k) => document.querySelector(`#paneAgent [data-agw=${k}]`).textContent)") == ["확정", "문서에서 보기"], turns)
        page.screenshot(path=str(OUT / "03_config_card.png"))

        # ---- 프로젝트 구성 입력 → 확정 → 변경 계획(바로) → 실행 카드 「문서에 반영」
        page.fill("#paneAgent [data-agw=years0]", "3")
        page.fill("#paneAgent [data-agw=lead]", "한국선급")
        page.fill("#paneAgent [data-agw=joint]", "씨드로닉스, 유엔젤")  # 공동기관은 한 줄 칸에 쉼표(2026-11-18 사용자)
        doc = page.evaluate("state.id")
        rev0 = requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"]
        page.click("#paneAgent [data-agw=confirm]")
        page.wait_for_function("() => { const t = [...document.querySelectorAll('#paneAgent .agw-turn')].pop(); return t && t.querySelector('.agw-act[data-act=apply], .agw-ask[data-ask=choice]'); }", timeout=120000)
        turns = page.evaluate(TURNS)
        div = requests.get(f"{base}/api/docs/{doc}/divisions", timeout=30).json()
        check("「확정」 → 프로젝트 구성이 저장·확정됨(1단계 3차년도 · 주관 한국선급 · 공동 2) — 문서는 그대로",
              turns[1]["state"] == "done" and "확정했습니다" in turns[1]["out"] and (div.get("confirmed") or {}).get("values", {}).get("stages") == [3]
              and div["confirmed"]["values"]["orgs"]["lead"] == "한국선급" and div["confirmed"]["values"]["orgs"]["joint"] == ["씨드로닉스", "유엔젤"]
              and requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"] == rev0, [turns[1], div.get("confirmed")])
        plan_turn = next((t for t in turns if t["act"] == "plan"), None)
        check("변경 계획은 묻지 않고 바로 실행(문서 안 바뀜) — 결과 「변경 계획 — 맞출 자리 …」 · 문서 옆 열에 목록",
              plan_turn is not None and plan_turn["state"] == "done" and "맞출 자리" in plan_turn["out"] and page.evaluate("() => !document.getElementById('headsDlg').hidden"), turns)
        last = turns[-1]
        if last["ask"] == "choice":   # 계획에 사람이 볼 것(미해결 자리)이 있으면 스크립트 답은 고르게 한다 — 「문서에 반영」 을 고른다
            page.click('#paneAgent .agw-turn:last-child .agw-opt[data-value="apply"]')
            # 고른 것은 승인이 아니다 — 문서를 바꾸는 행동이면 그 턴이 실행 카드로 바뀌어 「진행」 을 기다린다(선택지에는 꼬리표 · 문서 바뀜이 안 보인다: spec_워크플로우 ② §15 「실행」)
            page.wait_for_selector("#paneAgent .agw-turn:last-child .agw-act[data-act=apply] [data-agw=go]:not([disabled])", timeout=60000)
            notes = page.evaluate("() => [...[...document.querySelectorAll('#paneAgent .agw-turn')].pop().querySelectorAll('.ag-note')].map((x) => x.textContent)")
            check("질문 카드에서 고른 「문서에 반영」 — 바로 돌지 않고 실행 카드로 묻는다(「고른 일은 문서를 바꾸거나 유료 LLM 을 불러 실행 카드로 확인합니다」 · 누르기 전에는 문서가 그대로)",
                  "고른 일은 문서를 바꾸거나 유료 LLM 을 불러 실행 카드로 확인합니다" in notes and requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"] == rev0, notes)
        card = page.evaluate("""() => { const c = [...document.querySelectorAll('#paneAgent .agw-act[data-act=apply]')].pop(); return { tags: [...c.querySelectorAll('.agw-tag')].map((x) => x.textContent), go: !!c.querySelector('[data-agw=go]'),
          skip: !!c.querySelector('[data-agw=skip]'), does: c.querySelector('.agw-does').textContent }; }""")
        check("문서를 바꾸는 행동은 실행 카드로 멈춘다 — 「문서에 반영」 · 꼬리표 「문서 바뀜」 · 「진행」 · 「건너뛰기」(누르기 전에는 문서가 그대로)",
              card["tags"] == ["문서 바뀜"] and card["go"] and card["skip"] and "맞출 자리" in card["does"] and requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"] == rev0, card)
        page.screenshot(path=str(OUT / "04_act_card.png"))
        page.click("#paneAgent .agw-turn:last-child [data-agw=go]")
        page.wait_for_function("() => { const t = [...document.querySelectorAll('#paneAgent .agw-turn')].pop(); return t && t.dataset.event === 'result' && /문서에 반영했습니다/.test(t.textContent) && !AGENT.busy; }", timeout=180000)
        turns = page.evaluate(TURNS)
        steps = page.evaluate(STEPS)
        rev1 = requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"]
        ap_turn = next((t for t in turns if t["act"] == "apply"), None)
        check("「진행」 → 문서가 바뀜(편집 차례가 오름) · 카드 「실행함 — 문서에 반영했습니다 …」 · 결과 턴 — 1단계 끝남 · 「지금」 은 2단계 · 3단계 남음 · 「지금 차례는 「…」」(LLM 끔 — 2 · 3단계 LLM 행동 없음)",
              rev1 > rev0 and ap_turn is not None and ap_turn["state"] == "done" and "반영했습니다" in ap_turn["out"] and steps == [["1단계 프로젝트 구성", "done"], ["2단계 헤딩 추출", "now"], ["3단계 표", "todo"]]
              and "지금 차례는 「" in turns[-1]["say"] and not turns[-1]["ask"] and not turns[-1]["act"], [rev0, rev1, turns[-2:], steps])
        page.screenshot(path=str(OUT / "05_done.png"))

        # ---- 2 · 3단계 행동(spec_양식표준화 ② §5) — LLM 을 쓸 수 있다고 보고(AGENT.enabled) 센다 · 실행 함수는 바꿔 끼워 부른 것만 본다(LLM 끔)
        r = page.evaluate("""async () => { const was = AGENT.enabled; AGENT.enabled = true;
          try { const st = await agwStatus({ fresh: true }); return { acts: st.actions.map((a) => [a.name, !!a.primary, !!a.paid, a.change]),
            steps: st.steps.filter((s) => ['headsLlm', 'adjust', 'tablesLlm'].includes(s.key)).map((s) => [s.key, s.state, s.stage]) }; } finally { AGENT.enabled = was; } }""")
        names = [a[0] for a in r["acts"]]
        check("1단계를 적용한 뒤 — 행동 heads_llm(첫째 · 유료 · 저장만) · tables_llm(유료) · 조정은 헤딩 판정 전이라 없음 · 진행 줄 단계(헤딩 LLM 판정 지금)",
              ["heads_llm", True, True, "store"] in r["acts"] and ["tables_llm", False, True, "store"] in r["acts"] and "heads_apply" not in names and names.index("heads_llm") < names.index("tables_llm")
              and r["steps"][0] == ["headsLlm", "now", "2단계 헤딩 추출"] and r["steps"][1][0] == "adjust" and r["steps"][1][1] in ("todo", "done") and r["steps"][2] == ["tablesLlm", "todo", "3단계 표"], r)
        r = page.evaluate("""async () => { const o = headsPickRun, C = []; headsPickRun = async (k, opt) => { C.push([k, opt || null]); return { ok: true, text: '검사 단계별 실행' }; };
          try { const a = await agwExec('heads_llm'), b = await agwExec('tables_llm'); return { C, a, b }; } finally { headsPickRun = o; } }""")
        check("heads_llm · tables_llm → headsPickRun([l2]) · ([l3]) — {asked: true}(실행 카드의 「진행」 이 그 확인) · 끝 글은 그 실행의 글",
              r["C"] == [[["l2"], {"asked": True}], [["l3"], {"asked": True}]] and r["a"] == {"ok": True, "text": "검사 단계별 실행"} and r["b"]["ok"], r)
        real = requests.get(f"{base}/api/docs/{doc}/analysis", timeout=30).json()
        fa = copy.deepcopy(real)
        it = {i["key"]: i for i in fa["items"]}
        it["heads"]["llm"] = {"state": "done", "text": "LLM 판정함 — 검사", "error": None}
        it["heads"]["undecided"] = 0
        it["templates"]["hints"] = []
        it["formats"].update({"state": "done", "levels": 2, "aligned": 1, "place": 0, "apply": {"state": "none", "text": "맞춘 레벨 1/2"},
                              "llm": {"state": "done", "text": "서식 정리 계획 1/1 템플릿 — 받음 1", "error": None, "need": 1, "planned": 1, "applied": 0, "stale": 0, "done": 0, "change": 3, "moved": 0, "reps": 0,
                                      "kept": 0, "unanswered": 0, "omitted": 0, "left": {"kept": 0, "unanswered": 0}, "list": [{"tpl": "t1", "no": 1, "state": "planned", "at": 123}], "leftMarked": []}})
        fa.update({"busy": False, "job": None, "chain": None})
        FAKE["v"] = fa
        r = page.evaluate("""async () => { const was = AGENT.enabled, o = tpbApply, C = []; AGENT.enabled = true;
          tpbApply = async (opt) => { C.push(opt || null); return { templates: [{}], changed: ['a', 'b', 'c'], merged: [] }; };
          try { const st = await agwStatus({ fresh: true }), a = st.actions.find((x) => x.name === 'heads_apply'), res = a ? await agwExec('heads_apply') : null;
            return { a: a ? [!!a.primary, a.change, !!a.paid, a.key.startsWith('fmt:'), a.does] : null, names: st.actions.map((x) => x.name), C, res }; }
          finally { AGENT.enabled = was; tpbApply = o; } }""")
        FAKE["v"] = None
        page.evaluate("() => docStatusPing()")
        check("헤딩 판정을 거쳤고 계획이 있으면 heads_apply(첫째 · 문서 바뀜 · key = 계획 표시 fmt:… · 「대표에 맞출 줄 3」) → tpbApply({plans: 받아 둔 계획의 표시}) · 끝 글 「조정을 반영했습니다 …」",
              r["a"] is not None and r["a"][:4] == [True, "doc", False, True] and "대표에 맞출 줄 3" in r["a"][4] and "heads_llm" not in r["names"] and "tables_llm" in r["names"]
              and r["C"] == [{"plans": {"t1": 123}}] and r["res"]["ok"] and r["res"]["text"].startswith("조정을 반영했습니다 — 템플릿 1개 · 바뀐 줄 3"), r)

        # ---- 다시 열어도 그대로 · 「작업 설명」 · 좁은 폭
        n = len(turns)
        page.evaluate(f"() => {{ location.hash = '#w={doc}'; }}")
        page.reload()
        page.wait_for_selector("#doc .para", timeout=120000)
        page.click("#tabAgent")
        page.wait_for_selector("#paneAgent .agw-turn", timeout=30000)
        again = page.evaluate(TURNS)
        check("다시 열어도 대화가 그대로 — 진행 턴 · 카드의 끝(실행함 · 답)", len(again) == n and [t["state"] for t in again] == [t["state"] for t in turns] and again[0]["act"] == "config_read", again)
        page.click("[data-ag-act=guide]")
        page.wait_for_function(f"() => document.querySelectorAll('#paneAgent .agw-turn').length === {n + 1}", timeout=60000)
        more = page.evaluate(TURNS)[-1]
        check("「작업 설명」 — 지금 상태로 다시 설명(시작 턴 · 「지금 차례는 「…」」 · LLM 끔이라 다음 행동 없음)", more["event"] == "start" and "지금 차례는 「" in more["say"] and not more["act"] and not more["ask"], more)
        page.set_viewport_size({"width": 1100, "height": 900})
        page.wait_for_timeout(400)
        w = page.evaluate("""() => { const t = document.querySelector('#paneAgent .ag-talk'), p = document.getElementById('panel').getBoundingClientRect();
          return { over: t.scrollWidth > t.clientWidth + 1, panel: Math.round(p.width), cards: [...document.querySelectorAll('#paneAgent .agw-card')].every((c) => c.getBoundingClientRect().right <= p.right + 0.5) }; }""")
        check("좁은 패널에서 대화가 가로로 넘치지 않는다(카드가 패널 안)", not w["over"] and w["cards"], w)
        page.screenshot(path=str(OUT / "06_narrow.png"))

        # ---- TASK 카드로 시작(LLM 끔) — 전처럼 「작업 개요」 가 열리고, 에이전트 보기에는 「작업 설명 듣기」
        page.set_viewport_size({"width": 1600, "height": 1000})
        page.goto(base)
        page.wait_for_selector("#taskCards .task-card")
        with page.expect_file_chooser() as fc:
            page.click('#taskCards [data-task="report_fit"]')
        fc.value.set_files(str(ROOT / "samples" / "기술수요조사서.hwpx"))
        page.wait_for_selector("#doc .para", timeout=120000)
        page.wait_for_timeout(1500)
        tool = page.evaluate("document.getElementById('panel').dataset.tool")
        page.click("#tabAgent")
        page.wait_for_selector("#paneAgent [data-agw=start]", timeout=30000)
        check("LLM 이 꺼져 있을 때 TASK 카드로 시작하면 전처럼 「작업 개요」 — 에이전트 보기의 빈 상태에 「작업 설명 듣기」", tool == "Div" and page.locator("#paneAgent .agw-empty h2").inner_text() == "「연차보고서 양식 맞추기」 진행", tool)
        page.click("#paneAgent [data-agw=start]")
        page.wait_for_selector("#paneAgent .agw-turn", timeout=60000)
        first = page.evaluate(TURNS)[0]
        check("「작업 설명 듣기」 → 시작 턴(스크립트 답)", first["event"] == "start" and "「연차보고서 양식 맞추기」" in first["say"], first)
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

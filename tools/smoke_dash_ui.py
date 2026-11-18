"""대시보드(패널 탭 「대시보드」 — app/static/dashboard.js · spec_작업에이전트 ② §9) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점 · 문서 편집은 모두 진짜.

- 사업계획서 양식 표준화(plan_fit — spec_양식표준화)를 TASK 카드로 시작 → 패널 탭 줄의 첫 탭 「대시보드」 → 누르면 단계 흐름: 묶음 셋(1단계 프로젝트 구성 · 2단계 헤딩 추출 · 3단계 표 — 묶음마다 「한 번에 진행」) ·
  단계 열넷(워크플로우 등록부 그대로 — 번호 · 이름 · 꼬리표 · 점선 = 선택) · 상태(01 끝남 · 04 지금 — 펴짐 · 2 · 3단계는 분석 상태로: 헤딩 · 표 끝남 · LLM 판정은 「할 수 있음」 · 조정은 헤딩 LLM 판정 뒤)
  · 머리 「끝남 n/9」(안 해도 되는 단계는 안 셈) · 「이어서 한 번에 1→3단계」 는 값 확정 전이라 꺼짐 + 까닭 글.
- 1단계(대시보드에서만): 「구성 읽기」(끝 글 · ✓) · 「구성 불러오기」(「작업 내용」 과 같은 목록 · 고른 것이 다시 그려도 그대로 · 「불러오기」 → divSourceLoad) · 「프로젝트 구성 입력 · 확정…」 → 폼 → 「확정」 →
  「이어서 한 번에 1→3단계」(확인 창 없이 — 2026-11-18 → divRunAll · headsRunAll · headsPickRun(["l3"]) 차례 · 모두 {asked: true} — 함수는 바꿔 끼워 부른 것만 본다 · 1단계가 적용까지 안 가면 멈추고 뒤 묶음은 시작하지 않음)
  → 「변경 계획 보기」 → 「문서에 반영」(제 확인 창) → 문서가 바뀜 · 「지금」 이 2단계로.
- 2 · 3단계 단추(함수는 바꿔 끼움 · 분석 상태는 끝점의 답을 흉내): LLM 판정 → headsPickRun(["l2"]) · 표 판정 → ["l3"] · 결과가 없거나 실패하면 「헤딩 추출(스크립트)」 ["s1","s2"] · 「표 구조(스크립트)」 ["s3"] ·
  조정 「모두 반영」(묻지 않고 → tpbApply({plans})) · 「계획 보기」 · 「템플릿 관계 열기」 · 「테이블 탭 열기」 · 묶음 「한 번에 진행」(headsRunAll · headsPickRun(남은 것)) · 헤딩 작업이 도는 동안은 꺼짐.
- 05 구분 기준 자리 확인(선택): 펴면 「LLM 검토 실행」 → 확인 창 → 끝 글 · 문서 옆 열에 검토 결과 목록 · 남은 문단 후보가 있으면 끝남이 아님 → 「다시 검토」 로 후보가 없으면 「✓ 끝남」(검토 끝점의 답만 흉내 — LLM 끔).
- 단계를 누르면 펴고 접힘 · 「하는 일 · 조건」(등록부의 조건) · 좁은 패널에서 가로 넘침 없음 · 다시 그려도 초점 유지(1초 지켜보기) · 문서 일반 편집(doc_edit)의 흐름 · 「에이전트 보기 열기」 · 콘솔 오류 없음.
- TASK 가 없는 문서(TASK 없이 올림 → #w=) — 탭은 보이고 「TASK 고르기」 카드 → 「이 TASK 로」 → 문서에 TASK 가 적히고 그 자리에서 단계 흐름(② §9 「TASK 가 없을 때」).

    python -X utf8 tools/smoke_dash_ui.py <출력 폴더> [--port 18471]
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
  groups: [...document.querySelectorAll('#paneDash .dash-ghead')].map((g) => [g.querySelector('.dash-gno').textContent, g.querySelector('.dash-gname').textContent, (g.querySelector('button') || {}).textContent || '', !!(g.querySelector('button') || {}).disabled, (g.querySelector('button') || {}).title || '']),
  top: [...document.querySelectorAll('#paneDash .dash-top > *')].map((x) => [x.tagName === 'BUTTON' ? 'button' : 'note', x.textContent, !!x.disabled]),
  tool: document.getElementById('panel').dataset.tool, wf: (document.querySelector('#paneDash .dash-wf') || {}).href || '' })"""
STD_KEYS = ["open", "read", "load", "values", "review", "plan", "apply", "heads", "headsLlm", "adjust", "tree", "tables", "tablesLlm", "tableTools"]   # 등록부 _std 의 차례
STD_OPT = {"read", "load", "review", "tree", "tableTools"}
# 2 · 3단계 단추가 부르는 기존 함수 — 바꿔 끼워 부른 것(이름 · 인자)만 적는다(LLM · 문서 편집 없이). agwFitApplied 는 divRunAll 이 「적용함」 을 흉내 냈을 때만(__fitOk) 적용한 것으로
STUB = """() => { if (window.__orig) return; window.__calls = []; const C = window.__calls;
  window.__orig = { headsPickRun, headsRunAll, tpbApply, tplPlanGo, tplRelOpen, divRunAll, agwFitApplied, divSourceLoad, agwStdSteps }; const o = window.__orig;
  headsPickRun = async (keys, opt) => { C.push(['headsPickRun', keys, opt || null]); return { ok: true, text: `검사 단계별 실행 ${keys.join(',')}` }; };
  headsRunAll = async (opt) => { C.push(['headsRunAll', opt || null]); window.__chainHeads = window.__headsOk === true; return { ok: true, text: '검사 전체 실행 끝' }; };
  // 전체 실행이 2단계를 끝낸 것을 흉내 낼 때(__headsOk)만 2단계 셈을 끝남으로 — 「끝까지 감」 이어도 단계가 남으면 「이어서 한 번에」 는 멈춘다(검토 11-18)
  agwStdSteps = (...a) => { const S = o.agwStdSteps(...a); if (S && S.steps && window.__chainHeads) for (const k of ['heads', 'headsLlm', 'adjust']) S.steps[k] = { state: 'done', text: '검사 끝남' }; return S; };
  tpbApply = async (opt) => { C.push(['tpbApply', opt || null]); return { templates: [{ splits: [{ no: 9 }] }], changed: ['a', 'b', 'c'], merged: [] }; };
  tplPlanGo = () => { C.push(['tplPlanGo']); };
  tplRelOpen = () => { C.push(['tplRelOpen']); };
  divRunAll = async (opt) => { C.push(['divRunAll', opt || null]); window.__chainApplied = window.__fitOk === true; };
  agwFitApplied = (...a) => (window.__chainApplied ? { applied: true, same: false } : o.agwFitApplied(...a));
  divSourceLoad = async (k) => { C.push(['divSourceLoad', k]); window.__fromWas = dv.preset.from; dv.preset.from = '검사 불러오기'; };
}"""
UNSTUB = """() => { const o = window.__orig; if (!o) return; headsPickRun = o.headsPickRun; headsRunAll = o.headsRunAll; tpbApply = o.tpbApply; tplPlanGo = o.tplPlanGo; tplRelOpen = o.tplRelOpen;
  divRunAll = o.divRunAll; agwFitApplied = o.agwFitApplied; divSourceLoad = o.divSourceLoad; agwStdSteps = o.agwStdSteps; window.__chainApplied = false; window.__chainHeads = false; delete window.__orig; }"""
CALLS = "() => { const c = (window.__calls || []).slice(); if (window.__calls) window.__calls.length = 0; return c; }"
FAKE = {"v": None}   # 분석 상태 끝점(GET …/analysis)의 흉내 — None 이면 진짜


def node(page, key):
    return next((n for n in page.evaluate(NODES) if n["key"] == key), None)


def open_node(page, key):   # 그 카드를 편다(이미 펴져 있으면 그대로 — 머리를 누르면 접히므로)
    if not (node(page, key) or {}).get("open"):
        page.click(f'#paneDash .dash-node[data-key={key}] .dash-node-head')
    page.wait_for_selector(f'#paneDash .dash-node[data-key={key}] .dash-detail')
    return node(page, key)


def node_text(page, key):
    return page.evaluate(f"() => [...document.querySelectorAll('#paneDash .dash-node[data-key={key}] .dash-detail > .dash-text')].map((p) => p.textContent).join(' ')")


def counted(nodes):   # 머리 「끝남 n/m」 의 셈 — 안 해도 되는 단계 · 상태 없는 단계는 안 셈(dashboard.js dashCounted)
    c = [n for n in nodes if not n["opt"] and n["state"] in ("done", "now", "ready", "todo", "hold", "run")]
    return sum(1 for n in c if n["state"] == "done"), len(c)


def fake_analysis(page, v, tag):   # 분석 상태를 흉내 낸 답으로 바꾸고 화면이 그것을 읽을 때까지
    FAKE["v"] = v
    page.evaluate("() => docStatusPing()")
    page.wait_for_function(f"() => (dsState.main || {{}}).__fake === {tag!r}" if tag else "() => !!dsState.main && !dsState.main.__fake", timeout=30000)
    page.wait_for_timeout(1300)   # 대시보드의 1초 다시 그리기


def main():
    wait_server()
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        dialogs = []
        page.on("dialog", lambda d: (dialogs.append(d.message[:900]), d.accept()))
        page.goto(base)
        page.wait_for_selector("#taskCards .task-card")
        with page.expect_file_chooser() as fc:
            page.click('#taskCards [data-task="plan_fit"]')
        fc.value.set_files(str(PLAN))
        page.wait_for_selector("#doc .para", timeout=120000)
        page.wait_for_function("() => !document.getElementById('tabDash').hidden && document.getElementById('panel').dataset.tool === 'Div'", timeout=30000)   # TASK 시작(taskEnter)이 「작업 내용」 을 연 뒤에
        tabs = page.evaluate("() => [...document.querySelectorAll('#toolTabs button[role=tab]')].filter((b) => !b.hidden).map((b) => b.textContent)")
        check("탭 줄의 첫 탭 「대시보드」 — 「에이전트」 · 「작업 내용」 앞(2026-11-18 사용자 「에이전트 보다 대시보드를 앞부분에」)", tabs[:3] == ["대시보드", "에이전트", "작업 내용"], tabs)

        page.route(re.compile(r"/api/docs/[^/]+/analysis$"), lambda route: route.continue_() if FAKE["v"] is None else route.fulfill(json=FAKE["v"]))
        page.click("#tabDash")
        page.wait_for_selector("#paneDash .dash-node", timeout=30000)
        page.wait_for_function("() => document.querySelector('#paneDash .dash-node[data-key=values]')?.dataset.state === 'now'", timeout=30000)
        page.wait_for_function("() => ['heads', 'tables'].every((k) => document.querySelector(`#paneDash .dash-node[data-key=${k}]`)?.dataset.state === 'done')", timeout=180000)   # 첫 분석(스크립트)이 끝나면
        page.wait_for_function("() => !!dsState.main && !dsState.main.busy && !((heads.view || {}).job && heads.view.job.status === 'running')", timeout=120000)   # 그 헤딩 작업이 다 끝날 때까지(도는 동안은 2 · 3단계 단추가 꺼짐)
        page.wait_for_timeout(1300)
        h, nodes = page.evaluate(HEAD), page.evaluate(NODES)
        by = {n["key"]: n for n in nodes}
        check("탭을 누르면 패널이 대시보드 — 머리 TASK 이름 「사업계획서 양식 표준화」 · 「워크플로우 ↗」(그 TASK 절)", h["tool"] == "Dash" and h["title"] == "사업계획서 양식 표준화" and h["wf"].endswith("/workflow#plan_fit"), h)
        check("묶음 셋 — 1단계 프로젝트 구성 · 2단계 헤딩 추출 · 3단계 표(등록부의 번호) · 묶음마다 「한 번에 진행」 · 1단계는 값 확정 전이라 꺼짐",
              [g[:2] for g in h["groups"]] == [["1단계", "프로젝트 구성"], ["2단계", "헤딩 추출"], ["3단계", "표"]] and all(g[2] == "한 번에 진행" for g in h["groups"]) and h["groups"][0][3]
              and "표 판정(LLM)도 같이" in h["groups"][1][4], h["groups"])
        check("단계 열넷(등록부 그대로) — 01 문서 올리기 … 02 구성 읽기 · 03 구성 불러오기 · 04 프로젝트 구성 확정 · 05 구분 기준 자리 확인 · 06 변경 계획 · 07 적용(문서 바뀜) · 08~11 헤딩 · 12~14 표(점선 = 선택)",
              [n["key"] for n in nodes] == STD_KEYS and [n["no"] for n in nodes] == [f"{i:02d}" for i in range(1, 15)] and {n["key"] for n in nodes if n["opt"]} == STD_OPT
              and by["values"]["name"] == "프로젝트 구성 확정" and by["read"]["name"] == "구성 읽기" and by["load"]["name"] == "구성 불러오기" and "문서 바뀜" in by["apply"]["tags"] and "문서 바뀜" in by["adjust"]["tags"]
              and "LLM" in by["headsLlm"]["tags"] and "LLM" in by["tablesLlm"]["tags"]
              and "필수" in by["values"]["tags"] and "선택" in by["review"]["tags"] and "필수" not in by["review"]["tags"] and "필수" not in by["heads"]["tags"], nodes)   # 필수 = 선택 · 자동 · 준비 중이 아닌 단계(2026-11-18 사용자 「꼭 해야하는건 필수 라고 적어줘」)
        check("상태 — 01 ✓ 끝남 · 02 구성 읽기 「할 수 있음」 · 03 상태 글 없음 · 04 지금(펴짐 · 「프로젝트 구성 입력 · 확정…」) · 06 · 07 남음 · 헤딩 · 표 ✓(첫 분석) · LLM 판정은 「할 수 있음」(1단계가 남아도) · 조정은 헤딩 LLM 판정 뒤",
              by["open"]["st"] == "✓ 끝남" and by["read"]["state"] == "ready" and by["read"]["st"] == "할 수 있음" and by["load"]["st"] == "" and by["values"]["state"] == "now" and by["values"]["open"]
              and not any(n["open"] for n in nodes if n["key"] != "values") and [a[0] for a in by["values"]["acts"]] == ["프로젝트 구성 입력 · 확정…"] and by["plan"]["state"] == "todo" and by["apply"]["state"] == "todo"
              and by["heads"]["state"] == "done" and by["tables"]["state"] == "done" and by["headsLlm"]["state"] == "ready" and by["headsLlm"]["st"] == "할 수 있음" and by["tablesLlm"]["state"] == "ready"
              and by["adjust"]["state"] in ("todo", "done") and by["tree"]["st"] == "" and by["tableTools"]["st"] == "", [(n["key"], n["state"], n["st"]) for n in nodes])
        if by["adjust"]["state"] == "todo":
            check("조정(헤딩 LLM 판정 전) — 「남음」 · 「헤딩 LLM 판정 뒤에 합니다」", "헤딩 LLM 판정 뒤에 합니다" in (open_node(page, "adjust") and node_text(page, "adjust")), node_text(page, "adjust"))
            page.click('#paneDash .dash-node[data-key=values] .dash-node-head')
            page.wait_for_selector('#paneDash .dash-node[data-key=values] .dash-detail')
        d0, n0 = counted(nodes)
        check("머리 「끝남 n/9」(세는 단계 아홉 — 안 해도 되는 단계는 안 셈) · 「다음: 04 프로젝트 구성 확정」", n0 == 9 and h["count"] == f"끝남 {d0}/9" and h["next"] == "다음: 04 프로젝트 구성 확정", [h, d0, n0])
        check("머리 아래 「이어서 한 번에 1→3단계」 — 값 확정 전이라 꺼짐 + 까닭 글 「프로젝트 구성 값을 먼저 확정하세요」", h["top"] == [["button", "이어서 한 번에 1→3단계", True], ["note", "프로젝트 구성 값을 먼저 확정하세요", False]], h["top"])
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

        doc = page.evaluate("state.id")
        rev0 = requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"]

        # ---- 1단계 「구성 읽기」 · 「구성 불러오기」(spec_양식표준화 ② §2·§3 — 안 해도 되는 단계)
        n2 = open_node(page, "read")
        check("02 구성 읽기를 펴면 「구성 읽기」(값이 없고 읽어 보기 전이라 강조)", [a[0] for a in n2["acts"]] == ["구성 읽기"] and n2["acts"][0][2] and not n2["acts"][0][1], n2)
        page.click('#paneDash .dash-node[data-key=read] .dash-acts button:has-text("구성 읽기")')
        page.wait_for_function("() => document.querySelector('#paneDash .dash-node[data-key=read]')?.dataset.state === 'done'", timeout=60000)
        h, n2 = page.evaluate(HEAD), node(page, "read")
        check("「구성 읽기」 → 끝 글 「구성 읽기 — 문서에서 …」 · 02 ✓ 끝남 + 읽은 결과 한 줄(안 해도 되는 단계라 셈은 그대로) · 문서 그대로",
              h["last"].startswith("구성 읽기 — 문서에서") and n2["st"] == "✓ 끝남" and "읽" in node_text(page, "read") and h["count"] == f"끝남 {d0}/9"
              and requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"] == rev0, [h, n2, node_text(page, "read")])
        page.evaluate(STUB)
        open_node(page, "load")
        sel = page.evaluate("""() => { const s = document.querySelector('#paneDash .dash-node[data-key=load] .dash-load-sel'), b = document.querySelector('#paneDash .dash-node[data-key=load] .dash-acts button');
          return s ? { first: s.options[0].text, values: [...s.options].map((o) => o.value), groups: [...s.querySelectorAll('optgroup')].map((g) => g.label), btn: b.textContent, off: b.disabled } : null; }""")
        check("03 구성 불러오기를 펴면 고르기 목록(「작업 내용」 의 「프로젝트 구성 불러오기」 와 같은 항목 — 문서에서 추출 · 파일 올려 추출) + 「불러오기」(고르기 전에는 꺼짐)",
              sel is not None and sel["first"].startswith("프로젝트 구성 불러오기") and f"doc:{doc}" in sel["values"] and "file" in sel["values"] and "문서에서 추출" in sel["groups"] and sel["btn"] == "불러오기" and sel["off"], sel)
        page.select_option("#paneDash .dash-node[data-key=load] .dash-load-sel", f"doc:{doc}")
        page.wait_for_timeout(1300)   # 1초 다시 그리기가 지나도 고른 것이 그대로
        kept = page.evaluate("() => ({ v: document.querySelector('#paneDash .dash-load-sel').value, off: document.querySelector('#paneDash .dash-node[data-key=load] .dash-acts button').disabled })")
        page.click('#paneDash .dash-node[data-key=load] .dash-acts button:has-text("불러오기")')
        page.wait_for_function("() => /불러온 곳: 검사 불러오기/.test(document.querySelector('#paneDash .dash-node[data-key=load] .dash-detail')?.textContent || '')", timeout=15000)
        calls = page.evaluate(CALLS)
        check("고른 것은 다시 그려도 그대로 · 「불러오기」 → divSourceLoad(고른 값) 한 번 · 카드에 「불러온 곳: …」(입력 칸만 — 확인 창 없음)",
              kept == {"v": f"doc:{doc}", "off": False} and calls == [["divSourceLoad", f"doc:{doc}"]], [kept, calls])
        page.evaluate("() => { dv.preset.from = window.__fromWas; }")
        page.click('#paneDash .dash-node[data-key=values] .dash-node-head')
        page.wait_for_selector('#paneDash .dash-node[data-key=values] .dash-detail')

        # ---- 대시보드에서만: 값 입력 → 확정
        page.click('#paneDash .dash-node[data-key=values] .dash-acts button:has-text("프로젝트 구성 입력")')
        page.wait_for_selector("#paneDash .agw-form [data-agw=confirm]")
        names = page.evaluate("() => [...document.querySelectorAll('#paneDash .dash-node[data-key=values] .dash-detail button')].map((b) => b.textContent.trim())")
        form = page.evaluate("""() => { const f = document.querySelector('#paneDash .agw-form'), top = (s) => { const e = f.querySelector(s); return e ? Math.round(e.getBoundingClientRect().top) : null; };
          return { row: [top('[data-agw=confirm]'), top('[data-agw=read]'), top('[data-agw=close]')], nums: [top('[data-agw=stages]'), top('[data-agw=years0]'), top('[data-agw=current]')],
                   joint: f.querySelector('[data-agw=joint]').tagName, wide: f.scrollWidth <= f.clientWidth + 1 }; }""")
        check("폼을 편 카드의 단추 셋이 폼의 한 줄 — 「확정」 · 「문서에서 보기」 · 「닫기」(2026-11-18 사용자 「확정/문서에서보기,닫기는 한줄로」) · 단계 수 · 차년도 수 · 당해 차년도도 한 줄 · 공동기관은 한 줄 칸(쉼표) · 가로 넘침 없음 — 「구성 읽기」 는 02 단계에",
              names == ["확정", "문서에서 보기", "닫기"] and len(set(form["row"])) == 1 and None not in form["row"] and len(set(form["nums"])) == 1 and None not in form["nums"]
              and form["joint"] == "INPUT" and form["wide"], [names, form])
        page.locator("#paneDash .dash-node[data-key=values]").screenshot(path=str(OUT / "01b_form.png"))
        page.fill("#paneDash [data-agw=years0]", "3")
        page.wait_for_timeout(1300)   # 1초 지켜보기가 지나도 폼이 그대로(적는 동안 다시 그리지 않음)
        page.focus("#paneDash [data-agw=lead]")
        page.fill("#paneDash [data-agw=lead]", "한국선급")
        page.wait_for_timeout(1300)
        kept = page.evaluate("() => ({ y: document.querySelector('#paneDash [data-agw=years0]').value, focus: document.activeElement === document.querySelector('#paneDash [data-agw=lead]') })")
        check("폼(에이전트 질문 카드와 같은 폼)이 펼친 카드 안에 · 적는 동안 다시 그려도 값 · 초점이 그대로", kept == {"y": "3", "focus": True}, kept)
        page.fill("#paneDash [data-agw=joint]", "씨드로닉스, 유엔젤")
        page.click("#paneDash [data-agw=confirm]")
        page.wait_for_function("() => document.querySelector('#paneDash .dash-node[data-key=values]')?.dataset.state === 'done'", timeout=60000)
        page.wait_for_function("() => document.querySelector('#paneDash .dash-node[data-key=plan]')?.dataset.state === 'now'", timeout=30000)
        h = page.evaluate(HEAD)
        div = requests.get(f"{base}/api/docs/{doc}/divisions", timeout=30).json()
        check("「확정」 → 확정(1단계 3차년도 · 주관 한국선급 · 공동 2 — 문서 그대로) · 끝 글 「프로젝트 구성 확정 — …」 · 04 끝남 · 06 지금 · 머리 끝남 하나 더 · 1단계 「한 번에 진행」 켜짐",
              (div.get("confirmed") or {}).get("values", {}).get("stages") == [3] and div["confirmed"]["values"]["orgs"]["joint"] == ["씨드로닉스", "유엔젤"]
              and h["last"].startswith("프로젝트 구성 확정") and not h["lastHalt"] and h["count"] == f"끝남 {d0 + 1}/9" and h["next"] == "다음: 06 변경 계획 보기"
              and requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"] == rev0 and not h["groups"][0][3] and h["top"] == [["button", "이어서 한 번에 1→3단계", False]], [h, div.get("confirmed")])
        page.screenshot(path=str(OUT / "02_confirmed.png"))

        # ---- 「이어서 한 번에 1→3단계」(spec_양식표준화 ② §4) — 확인 창 없이(2026-11-18) 묶음의 실행을 차례로(asked) · 1단계가 적용까지 안 가면 멈춤(함수는 바꿔 끼움 — 부른 차례 · 인자만 본다)
        page.evaluate("() => { window.__fitOk = true; window.__headsOk = true; }")
        n_dialogs = len(dialogs)
        page.click('#paneDash .dash-top button:has-text("이어서 한 번에")')
        page.wait_for_function("() => /^이어서 한 번에 1→3단계 — 끝남 — /.test((document.querySelector('#paneDash .dash-last') || {}).textContent || '')", timeout=60000)
        h, calls = page.evaluate(HEAD), page.evaluate(CALLS)
        check("「이어서 한 번에 1→3단계」 → 확인 창 없이(2026-11-18 사용자 「이런 알람좀 주지마」 — 묶음마다 하는 일은 단추 도움말) → divRunAll · headsRunAll · headsPickRun([l3]) 차례로 · 모두 {asked: true} · 끝 글 「끝남 — 1단계 적용함 / …」",
              len(dialogs) == n_dialogs
              and calls == [["divRunAll", {"asked": True}], ["headsRunAll", {"asked": True}], ["headsPickRun", ["l3"], {"asked": True}]]
              and h["last"].startswith("이어서 한 번에 1→3단계 — 끝남 — 1단계 적용함 / 2단계 검사 전체 실행 끝 / 3단계 검사 단계별 실행 l3") and not h["lastHalt"], [dialogs[n_dialogs:], calls, h["last"]])
        page.evaluate("() => { window.__fitOk = false; window.__chainApplied = false; window.__headsOk = false; window.__chainHeads = false; }")
        page.wait_for_function("() => (document.querySelector('#paneDash .dash-top button') || {}).textContent === '이어서 한 번에 1→3단계'", timeout=15000)
        page.click('#paneDash .dash-top button:has-text("이어서 한 번에")')
        page.wait_for_function("() => /^이어서 한 번에 1→3단계 — 멈춤 — 1단계 프로젝트 구성: /.test((document.querySelector('#paneDash .dash-last') || {}).textContent || '')", timeout=60000)
        h, calls = page.evaluate(HEAD), page.evaluate(CALLS)
        check("1단계가 「적용」 까지 안 가면 멈춤 — 뒤 묶음은 시작하지 않음(headsRunAll 안 부름) · 끝 글에 멈춘 까닭 · 「시작하지 않은 것: 2단계 헤딩 추출 · 3단계 표」 · 주황 줄",
              calls == [["divRunAll", {"asked": True}]] and "시작하지 않은 것: 2단계 헤딩 추출 · 3단계 표" in h["last"] and h["lastHalt"]
              and requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"] == rev0, [calls, h["last"]])
        page.locator("#paneDash").screenshot(path=str(OUT / "02b_chain.png"))
        # 2단계 — 전체 실행이 「끝까지 감」 으로 돌아와도 단계가 남았으면(서식 정리 계획을 일부 못 받음 …) 3단계를 시작하지 않는다(검토 11-18 — 전에는 초록 「끝남」)
        page.evaluate("() => { window.__fitOk = true; window.__chainApplied = false; window.__headsOk = false; window.__chainHeads = false; }")
        page.wait_for_function("() => (document.querySelector('#paneDash .dash-top button') || {}).textContent === '이어서 한 번에 1→3단계'", timeout=15000)
        page.click('#paneDash .dash-top button:has-text("이어서 한 번에")')
        page.wait_for_function("() => /^이어서 한 번에 1→3단계 — 멈춤 — 2단계 헤딩 추출: /.test((document.querySelector('#paneDash .dash-last') || {}).textContent || '')", timeout=60000)
        h, calls = page.evaluate(HEAD), page.evaluate(CALLS)
        check("2단계 전체 실행이 「끝」 이어도 단계가 남으면 멈춤 — 3단계(headsPickRun)는 시작하지 않음 · 끝 글에 남은 단계 · 「한 것: 1단계 적용함」 · 「시작하지 않은 것: 3단계 표」 · 주황 줄",
              calls == [["divRunAll", {"asked": True}], ["headsRunAll", {"asked": True}]] and "한 것: 1단계 적용함" in h["last"] and "시작하지 않은 것: 3단계 표" in h["last"] and h["lastHalt"], [calls, h["last"]])
        page.evaluate("() => { window.__fitOk = false; window.__chainApplied = false; }")
        page.evaluate(UNSTUB)

        # ---- 변경 계획(문서 옆 열 · 탭 그대로)
        page.click('#paneDash .dash-node[data-key=plan] .dash-acts button:has-text("변경 계획")')
        page.wait_for_function("() => /변경 계획 — |현재 프로젝트 구성/.test(document.querySelector('#paneDash .dash-last')?.textContent || '')", timeout=120000)
        page.wait_for_function("() => document.querySelector('#paneDash .dash-node[data-key=apply]')?.dataset.state === 'now'", timeout=30000)
        h, n5 = page.evaluate(HEAD), node(page, "apply")
        check("「변경 계획 보기」 → 끝 글 · 문서 옆 열에 목록 · 패널은 대시보드 그대로 · 07 지금(「문서에 반영」)",
              h["tool"] == "Dash" and page.evaluate("() => !document.getElementById('headsDlg').hidden") and n5["open"] and any(a[0] == "문서에 반영" for a in n5["acts"]), [h, n5])
        page.screenshot(path=str(OUT / "03_plan.png"))

        # ---- 반영(확인 창 없이 — 2026-11-18) → 문서가 바뀜 · 모두 끝남
        n_dialogs = len(dialogs)
        page.click('#paneDash .dash-node[data-key=apply] .dash-acts button:has-text("문서에 반영")')
        page.wait_for_function("() => document.querySelector('#paneDash .dash-node[data-key=apply]')?.dataset.state === 'done'", timeout=180000)
        page.wait_for_function("() => (document.querySelector('#paneDash .dash-next') || {}).textContent === '다음: 09 헤딩 LLM 판정 · 서식 계획'", timeout=60000)   # 「지금」 이 2단계로(LLM 끔 — 헤딩 LLM 판정이 남음)
        page.wait_for_function("() => /^문서에 반영 — /.test((document.querySelector('#paneDash .dash-last') || {}).textContent || '')", timeout=60000)   # 반영 뒤 문서를 다시 읽는 동안은 「하는 중」 줄
        page.wait_for_timeout(1300)
        h, nodes = page.evaluate(HEAD), page.evaluate(NODES)
        by = {n["key"]: n for n in nodes}
        d1, _ = counted(nodes)
        rev1 = requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"]
        check("「문서에 반영」 → 확인 창 없이(2026-11-18) → 문서가 바뀜 · 끝 글 「문서에 반영 — 문서에 반영했습니다 …」 · 1단계 「한 번에 진행」 꺼짐 · 「지금」 이 2단계(09 헤딩 LLM 판정 — 펴짐) · 3단계 표 판정은 「할 수 있음」",
              len(dialogs) == n_dialogs and rev1 > rev0 and h["last"].startswith("문서에 반영 — 문서에 반영했습니다") and h["groups"][0][3] and by["headsLlm"]["state"] == "now" and by["headsLlm"]["open"]
              and by["tablesLlm"]["state"] == "ready" and h["count"] == f"끝남 {d1}/9" and d1 >= 6 and h["top"] == [["button", "이어서 한 번에 2→3단계", False]], [dialogs[n_dialogs:], rev0, rev1, h, [(n["key"], n["state"]) for n in nodes]])
        page.screenshot(path=str(OUT / "04_done.png"))
        next_done = h["next"]

        # ---- 2 · 3단계 단추 → 기존 함수(spec_양식표준화 ② §3 — 함수는 바꿔 끼워 부른 차례 · 인자만 본다: LLM 끔)
        page.evaluate(STUB)
        n9 = node(page, "headsLlm")
        check("09 헤딩 LLM 판정(지금) — 「LLM 판정」(강조) · 글 「LLM 판정 안 함 …」", n9["acts"] == [["LLM 판정", False, True]] and "LLM 판정 안 함" in node_text(page, "headsLlm"), [n9, node_text(page, "headsLlm")])
        page.click('#paneDash .dash-node[data-key=headsLlm] .dash-acts button:has-text("LLM 판정")')
        page.wait_for_function("() => /^LLM 판정 — 검사 단계별 실행 l2/.test((document.querySelector('#paneDash .dash-last') || {}).textContent || '')", timeout=15000)
        check("「LLM 판정」 → headsPickRun([l2]) (제 확인 창 — asked 없음) · 끝 글", page.evaluate(CALLS) == [["headsPickRun", ["l2"], None]])
        n13 = open_node(page, "tablesLlm")
        page.click('#paneDash .dash-node[data-key=tablesLlm] .dash-acts button:has-text("표 판정(LLM)")')
        page.wait_for_function("() => /^표 판정\\(LLM\\) — 검사 단계별 실행 l3/.test((document.querySelector('#paneDash .dash-last') || {}).textContent || '')", timeout=15000)
        check("13 표 판정(할 수 있음 — 강조 아님) 「표 판정(LLM)」 → headsPickRun([l3])", n13["acts"] == [["표 판정(LLM)", False, False]] and page.evaluate(CALLS) == [["headsPickRun", ["l3"], None]], n13)
        page.click('#paneDash .dash-group[data-group=heads] .dash-ghead button')
        page.wait_for_function("() => /^2단계 헤딩 추출 — 한 번에 진행 — 검사 전체 실행 끝/.test((document.querySelector('#paneDash .dash-last') || {}).textContent || '')", timeout=15000)
        check("2단계 「한 번에 진행」 → headsRunAll()(헤딩 추출 탭의 「전체 실행」 — 제 확인 창)", page.evaluate(CALLS) == [["headsRunAll", None]])
        page.click('#paneDash .dash-group[data-group=tables] .dash-ghead button')
        page.wait_for_function("() => /^3단계 표 — 한 번에 진행 — 검사 단계별 실행 l3/.test((document.querySelector('#paneDash .dash-last') || {}).textContent || '')", timeout=15000)
        check("3단계 「한 번에 진행」 → headsPickRun(남은 표 단계 — 표 구조는 끝나 [l3])", page.evaluate(CALLS) == [["headsPickRun", ["l3"], None]])
        open_node(page, "tree")
        page.click('#paneDash .dash-node[data-key=tree] .dash-acts button:has-text("템플릿 관계 열기")')
        open_node(page, "adjust")
        page.click('#paneDash .dash-node[data-key=adjust] .dash-acts button:has-text("계획 보기")')
        check("11 「템플릿 관계 열기」 → tplRelOpen() · 10 조정 「계획 보기」 → tplPlanGo()", page.evaluate(CALLS) == [["tplRelOpen"], ["tplPlanGo"]])

        # 분석 상태를 흉내 낸 답으로(끝점 GET …/analysis) — 헤딩 판정을 거쳤고 받아 둔 계획이 있음 → 조정 「모두 반영」(묻지 않고 → tpbApply({plans}))
        real = requests.get(f"{base}/api/docs/{doc}/analysis", timeout=30).json()
        fa = copy.deepcopy(real)
        it = {i["key"]: i for i in fa["items"]}
        it["heads"]["llm"] = {"state": "done", "text": "LLM 판정함 — 검사", "error": None}
        it["heads"]["undecided"] = 0
        it["templates"]["hints"] = []
        it["formats"].update({"state": "done", "levels": 2, "aligned": 1, "place": 0, "apply": {"state": "none", "text": "맞춘 레벨 1/2"},
                              "llm": {"state": "done", "text": "서식 정리 계획 1/1 템플릿 — 받음 1", "error": None, "need": 1, "planned": 1, "applied": 0, "stale": 0, "done": 0, "change": 3, "moved": 1, "reps": 0,
                                      "kept": 0, "unanswered": 0, "omitted": 0, "left": {"kept": 0, "unanswered": 0}, "list": [{"tpl": "t1", "no": 1, "state": "planned", "at": 123}], "leftMarked": []}})
        fa.update({"busy": False, "job": None, "chain": None, "__fake": "A"})
        fake_analysis(page, fa, "A")
        n10 = node(page, "adjust")
        check("헤딩 판정(LLM)을 거쳤고 계획이 있으면 10 조정이 지금 — 「모두 반영」(강조) · 「계획 보기」 · 글에 반영할 것(맞출 줄 3 · 뗄 줄 1)",
              n10["state"] == "now" and n10["open"] and n10["acts"][:2] == [["모두 반영", False, True], ["계획 보기", False, False]] and [a[0] for a in n10["acts"][2:]] == ["고친 부분 적용하기"]
              and "대표에 맞출 줄 3" in node_text(page, "adjust") and "뗄 줄 1" in node_text(page, "adjust"),
              [n10, node_text(page, "adjust")])
        n_dialogs = len(dialogs)
        page.click('#paneDash .dash-node[data-key=adjust] .dash-acts button:has-text("모두 반영")')
        page.wait_for_function("() => /^조정 — 모두 반영 — 조정을 반영했습니다/.test((document.querySelector('#paneDash .dash-last') || {}).textContent || '')", timeout=15000)
        h, calls = page.evaluate(HEAD), page.evaluate(CALLS)
        # 묻지 않는다 — 2026-11-18 사용자 「모두 반영할때... 팝업 알림 확인 받지마」(진행 줄 「조정」 의 그 단추와 같게 · 되돌림은 실행 취소 한 번)
        check("「모두 반영」 → 확인 창 없이 tpbApply({plans: 받아 둔 계획의 표시}) · 끝 글 「조정을 반영했습니다 — 템플릿 1개 · 바뀐 줄 3 · 서식 종속 템플릿 1개 …」",
              len(dialogs) == n_dialogs and calls == [["tpbApply", {"plans": {"t1": 123}}]]
              and "템플릿 1개 · 바뀐 줄 3 · 서식 종속 템플릿 1개" in h["last"], [dialogs[n_dialogs:], calls, h["last"]])
        page.locator("#paneDash").screenshot(path=str(OUT / "04b_adjust.png"))
        fb = copy.deepcopy(real)   # 기본 분석(스크립트)이 실패 → 「헤딩 추출(스크립트)」 · 「표 구조(스크립트)」
        it = {i["key"]: i for i in fb["items"]}
        for k in ("heads", "tables"):
            it[k].update({"state": "failed", "error": "검사 실패", "llm": {"state": "none", "text": "LLM 판정 안 함", "error": None}})
        it["formats"]["state"] = "none"
        fb.update({"busy": False, "job": None, "chain": None, "__fake": "B"})
        fake_analysis(page, fb, "B")
        n8 = node(page, "heads")
        check("헤딩 분석이 실패하면 08 이 지금 — 「헤딩 추출(스크립트)」(강조) · 글 「… 실패 — 검사 실패」", n8["state"] == "now" and n8["acts"] == [["헤딩 추출(스크립트)", False, True]] and "검사 실패" in node_text(page, "heads"), [n8, node_text(page, "heads")])
        page.click('#paneDash .dash-node[data-key=heads] .dash-acts button:has-text("헤딩 추출(스크립트)")')
        page.wait_for_function("() => /^헤딩 추출\\(스크립트\\) — 검사 단계별 실행 s1,s2/.test((document.querySelector('#paneDash .dash-last') || {}).textContent || '')", timeout=15000)
        check("「헤딩 추출(스크립트)」 → headsPickRun([s1, s2])(무료 — 확인 창 없음)", page.evaluate(CALLS) == [["headsPickRun", ["s1", "s2"], None]])
        open_node(page, "tables")
        page.click('#paneDash .dash-node[data-key=tables] .dash-acts button:has-text("표 구조(스크립트)")')
        page.wait_for_function("() => /^표 구조\\(스크립트\\) — 검사 단계별 실행 s3/.test((document.querySelector('#paneDash .dash-last') || {}).textContent || '')", timeout=15000)
        h = page.evaluate(HEAD)
        check("「표 구조(스크립트)」 → headsPickRun([s3]) · 3단계 「한 번에 진행」 은 남은 표 단계(표 구조 → 표 판정)", page.evaluate(CALLS) == [["headsPickRun", ["s3"], None]] and "표 구조(스크립트) → 표 판정(LLM)" in h["groups"][2][4], h["groups"])
        fc_ = copy.deepcopy(real)   # 헤딩 작업이 도는 중 → 2 · 3단계 단추 · 「이어서 한 번에」 꺼짐
        fc_.update({"busy": True, "__fake": "C"})
        fake_analysis(page, fc_, "C")
        h = page.evaluate(HEAD)
        check("헤딩 작업이 도는 동안 — 2 · 3단계 「한 번에 진행」 · 「이어서 한 번에」 꺼짐(까닭 「헤딩 작업이 도는 중 …」)",
              h["groups"][1][3] and h["groups"][2][3] and h["groups"][1][4].startswith("헤딩 작업이 도는 중") and h["top"][:1] == [["button", "이어서 한 번에 2→3단계", True]], h)
        fake_analysis(page, None, "")
        page.evaluate(UNSTUB)
        page.evaluate(CALLS)
        page.wait_for_function(f"() => (document.querySelector('#paneDash .dash-next') || {{}}).textContent === {next_done!r}", timeout=30000)
        open_node(page, "tableTools")
        page.click('#paneDash .dash-node[data-key=tableTools] .dash-acts button:has-text("테이블 탭 열기")')
        page.wait_for_function("() => ['Tables', 'Heads'].includes(document.getElementById('panel').dataset.tool)", timeout=10000)
        check("14 「테이블 탭 열기」 → 패널 「테이블」", page.evaluate("document.getElementById('panel').dataset.tool") == "Tables", page.evaluate("document.getElementById('panel').dataset.tool"))
        page.click("#tabDash")
        page.wait_for_selector("#paneDash .dash-node", timeout=30000)

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
        check("다른 탭에 갔다 와도 같은 상태(1단계 끝남 · 「지금」 은 2단계)", page.evaluate(HEAD)["next"] == next_done, page.evaluate(HEAD))

        # ---- 03 구분 기준 자리 확인 — 이 단계에서 바로 「LLM 검토 실행」(2026-11-18 사용자 「LLM 검토할 수 있도록 해야 하는데 그 기능이 없잖아」 — 전에는 「검토 목록 열기」 뿐이라 문서 옆 목록을 열어야 돌릴 수 있었다).
        # 이 서버는 LLM 이 꺼져 있어 검토 끝점(POST …/divisions/review)의 답만 흉내 낸다 — 단추 · 확인 창 · divReview · 결과 목록 · 상태 셈은 진짜
        TEXT3 = "() => (document.querySelector('#paneDash .dash-node[data-key=review] .dash-detail > .dash-text') || {}).textContent || ''"
        page.click('#paneDash .dash-node[data-key=review] .dash-node-head')
        page.wait_for_selector('#paneDash .dash-node[data-key=review] .dash-detail')
        n3, text3 = node(page, "review"), page.evaluate(TEXT3)
        check("03 을 펴면 「LLM 검토 실행」 단추가 그 카드에 · 검토 전에는 상태 글 없음 · 「아직 하지 않았습니다 … 하지 않아도 다음 단계로」",
              [a[:2] for a in n3["acts"]] == [["LLM 검토 실행", False]] and n3["st"] == "" and "아직 하지 않았습니다" in text3 and "하지 않아도 다음 단계로" in text3, [n3, text3])
        cand = page.evaluate("() => ({ id: document.querySelector('#doc .para[data-id]').dataset.id, rev: state.serverRev })")
        fake = {"items": [{"id": cand["id"], "kind": "paragraph", "dim": "org", "dimName": "기관", "sources": ["missing"], "confidence": "high", "text": "검사용 문단 후보", "pattern": "기관마다 되풀이", "reason": "검사", "path": []}]}

        def review(route):
            route.fulfill(json={"at": time.time(), "rev": cand["rev"], "ran": {"review": False, "missing": True}, "why": {"review": "표시한 자리가 없습니다"}, "errors": {}, "review": None,
                                "missing": {"missing": fake["items"], "skipped": [], "summary": "검사용 답", "sent": {"tables": 0, "paragraphs": 1}, "call": None},
                                "items": fake["items"], "pending": None, "form": None, "costUsd": 0, "ms": 1200, "hints": [], "detail": None})
        page.route("**/api/docs/*/divisions/review", review)
        n_dialogs = len(dialogs)
        page.click('#paneDash .dash-node[data-key=review] .dash-acts button:has-text("LLM 검토 실행")')
        page.wait_for_function("() => /^구분 기준 LLM 검토 — /.test((document.querySelector('#paneDash .dash-last') || {}).textContent || '')", timeout=30000)
        h, n3, text3 = page.evaluate(HEAD), node(page, "review"), page.evaluate(TEXT3)
        lst = page.evaluate("() => ({ open: !document.getElementById('headsDlg').hidden, add: [...document.querySelectorAll('#headsDlgBody button')].filter((x) => x.textContent === '자리로 추가').length })")
        check("「LLM 검토 실행」 → 확인 창 없이(유료 — 2026-11-18) → 끝 글 「구분 기준 LLM 검토 — 빠진 자리 후보 1 …」 · 문서 옆 열에 검토 결과 목록(「자리로 추가」) · 패널은 대시보드 그대로 · 05 는 펴진 채 「다시 검토」 · 「검토 결과 보기」(강조)"
              " — 남은 문단 후보 1곳이라 끝남이 아님 · 머리의 셈 그대로",
              len(dialogs) == n_dialogs and h["last"].startswith("구분 기준 LLM 검토 — 빠진 자리 후보 1") and "문단 후보 1곳" in h["last"] and not h["lastHalt"]
              and h["tool"] == "Dash" and h["count"] == f"끝남 {d1}/9" and lst == {"open": True, "add": 1} and n3["open"] and n3["st"] == "" and n3["acts"] == [["다시 검토", False, False], ["검토 결과 보기", False, True]]
              and "문단 후보 1곳" in text3, [dialogs[n_dialogs:], h, n3, text3, lst])
        page.locator("#paneDash").screenshot(path=str(OUT / "05b_review.png"))
        fake["items"] = []
        page.click('#paneDash .dash-node[data-key=review] .dash-acts button:has-text("다시 검토")')
        page.wait_for_function("() => document.querySelector('#paneDash .dash-node[data-key=review]')?.dataset.state === 'done'", timeout=30000)
        h, n3 = page.evaluate(HEAD), node(page, "review")
        check("「다시 검토」 — 남은 문단 후보가 없으면 05 「✓ 끝남」(안 해도 되는 단계라 머리의 셈에는 안 듦 · 「다음」 그대로) · 카드는 펴진 채",
              n3["st"] == "✓ 끝남" and n3["open"] and [a[0] for a in n3["acts"]] == ["다시 검토", "검토 결과 보기"] and not n3["acts"][1][2] and h["count"] == f"끝남 {d1}/9" and h["next"] == next_done
              and h["last"].startswith("구분 기준 LLM 검토 — 빠진 자리 후보 0"), [h, n3])
        page.unroute("**/api/docs/*/divisions/review")

        # ---- 고친 부분 적용하기(spec_작업 ② §8 — 2026-11-18 사용자 「헤딩 추출 및 표 점검 할 때.. 고친 부분 적용하기 버튼 넣어줘」 → 답 「고친 문단 확정」): 문서가 바뀌는 단계(조정 · 템플릿 관계 · 표 점검)의
        # 단추 · 헤딩 추출 탭과 「테이블」 탭의 줄(고친 것이 있을 때만) → 누르면 확정(고친 문단 0 · 줄이 사라지고 단추는 꺼짐). 이 문서는 1단계 적용으로 고친 문단이 있다
        CQ = """() => ({ edited: state.edited.size, dirty: isDirty(), base: state.base,
          strips: [...document.querySelectorAll('.commit-quick')].map((b) => [b.dataset.cq, b.hidden, (b.querySelector('.cq-sum') || {}).textContent || '', (b.querySelector('.cq-btn') || {}).textContent || '']) })"""
        q0 = page.evaluate(CQ)
        open_node(page, "tableTools")
        n14 = node(page, "tableTools")
        open_node(page, "tree")
        n11 = node(page, "tree")
        open_node(page, "adjust")
        n10 = node(page, "adjust")
        check("고친 문단이 있으면 — 헤딩 추출 탭 · 「테이블」 탭에 「고친 부분 적용하기」 줄(고친 문단 n) · 10 조정 · 11 템플릿 관계 · 14 표 점검 카드에 그 단추(켜짐)",
              q0["dirty"] and q0["edited"] > 0 and [s[0] for s in q0["strips"]] == ["헤딩 추출", "표 점검"] and all(not s[1] and "고친 문단" in s[2] and s[3] == "고친 부분 적용하기" for s in q0["strips"])
              and all(["고친 부분 적용하기", False, False] in n["acts"] for n in (n10, n11, n14)), [q0, n10, n11, n14])
        n_dialogs = len(dialogs)
        page.click('#paneDash .dash-node[data-key=adjust] .dash-acts button:has-text("고친 부분 적용하기")')
        page.wait_for_function("() => state.edited.size === 0 && !isDirty() && !state.commitBusy", timeout=60000)
        page.wait_for_function("() => /^고친 부분 적용하기 — 확정 1/.test((document.querySelector('#paneDash .dash-last') || {}).textContent || '')", timeout=15000)
        page.wait_for_function("() => { const b = [...document.querySelectorAll('#paneDash .dash-node[data-key=adjust] .dash-acts button')].find((x) => x.textContent === '고친 부분 적용하기'); return b && b.disabled; }", timeout=15000)
        q1, n10 = page.evaluate(CQ), node(page, "adjust")
        check("「고친 부분 적용하기」 → 확인 창 없이 확정 1(고친 문단 0 · 기준 = 확정 1) · 두 줄이 사라짐 · 단추는 꺼짐(까닭 「고친 것이 없습니다」) · 끝 글",
              len(dialogs) == n_dialogs and q1["edited"] == 0 and q1["base"] == 1 and all(s[1] for s in q1["strips"]) and ["고친 부분 적용하기", True, False] in n10["acts"]
              and "고친 문단" in page.evaluate(HEAD)["last"], [q1, n10, page.evaluate(HEAD)["last"], dialogs[n_dialogs:]])

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
        page.evaluate("(id) => openWork(id)", bare)   # 주소의 #w= 만 바꾸면 다시 읽지 않는다(앱은 읽을 때만 #w= 를 본다) — 작업 리스트에서 여는 것과 같은 함수로
        page.wait_for_function(f"() => state.id === '{bare}' && !!document.querySelector('#doc .para') && !(state.task || {{}}).job && !document.getElementById('tabDash').hidden", timeout=120000)
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
        check("「이 TASK 로」 → 문서에 TASK 가 적힘(서버) · 패널은 대시보드 그대로 · 그 자리에서 양식 표준화 단계 흐름(세 묶음)",
              (saved.get("task") or {}).get("job") == "plan_fit" and h["tool"] == "Dash" and h["title"] == "사업계획서 양식 표준화" and [g[1] for g in h["groups"]] == ["프로젝트 구성", "헤딩 추출", "표"], [saved.get("task"), h])
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

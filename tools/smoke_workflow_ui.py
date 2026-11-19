"""TASK 워크플로우 페이지(spec_워크플로우 — app/workflow.py · app/workflow_api.py · app/static/workflow.html·js·css) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.
끝점은 모두 진짜(흉내 없음).

- 시작 화면: 상단 바 에이전트 아이콘 앞에 링크 「워크플로우」(/workflow · 새 탭 · 글 없이 아이콘만 — 2026-11-16) — 맨 끝은 에이전트 아이콘(#agentBtn — 2026-11-18 전의 「에이전트 설정」 링크 자리).
- /workflow: 목차(전체 보기 · TASK 일곱 · 공통 모듈 아홉) · 전체 보기(TASK 마다 한 줄 — 이관 = 1~4단계 사슬 · 준비 중 TASK) · 범례.
- 기본 다이어그램: 단계 노드 선택 · 이전/다음 순차 탐색 · 단계 묶음 이동 · 상세 주소 · 키보드 · 준비 중 · 기술 상세 · 관련 모듈 · 읽기 전용.
- TASK 절(이관): 이름·설명(TASK_CATALOG) · 받는 문서 → 산출물 · 전제(할 일 프롬프트) · 묶음 넷(「N단계」 = TASK_STAGE_META) · 단계 줄(이름 · 누가 · 문서 바뀜 · 하는 일이 펴지 않아도 보임) ·
  줄을 누르면 세부(에이전트 작업 번호·이름·모델 · 모듈 파일 + 설명 · 사양 자리 · 공통 모듈 링크).
- 공통 모듈 절: 「쓰는 TASK」 → 누르면 그 TASK 로(목차의 지금 절 표시) · 묶음 사슬을 누르면 그 묶음으로 · 주소 #<job> 로 바로 열기.
- 「모두 펼치기」 · 「모두 접기」 · 좁은 폭(900 · 480 · 360px)에서 가로 넘침 없음(목차는 가로 줄).
- 문서를 연 상단 바: 1600 · 1280 · 1100 · 900px 에서 넘침 없음 · 링크 30×26 아이콘만(어느 폭에서나) · 패널 여닫기(#panelBtn)도 아이콘 · 800px 에서는 감춤.
- 콘솔 오류 없음.

    python -X utf8 tools/smoke_workflow_ui.py <출력 폴더> [--port 18447]
    python -X utf8 tools/smoke_workflow_ui.py <출력 폴더> --navigation-only  # 주소·뒤로/앞으로·동일 주소 재선택만
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
ap.add_argument("--port", type=int, default=18447)
ap.add_argument("--navigation-only", action="store_true", help="주소 탐색 검사만 실행(문서 업로드 없음)")
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
MUST = lambda s: [] if s["auto"] or s["optional"] or s["soon"] else ["필수"]   # 「필수」 꼬리표 — 선택 · 자동 · 준비 중이 아닌 단계(workflow.js must · 2026-11-18 사용자 「꼭 해야하는건 필수 라고 적어줘」)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1"}
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_TPL_AGENT_MODEL"):
    env.pop(k, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []
SMALL = ROOT / "samples" / "기술수요조사서.hwpx"   # 상단 바 폭만 보므로 작은 문서


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:900] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def wait_server(timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if requests.get(base + "/api/workflow", timeout=2).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.4)
    raise SystemExit("서버가 안 뜸")


OVERFLOW = """() => { const m = document.getElementById('wfMain'), n = document.getElementById('wfNav'), d = document.documentElement;
  return { page: d.scrollWidth - d.clientWidth, main: m.scrollWidth - m.clientWidth, navRow: getComputedStyle(n).display === 'flex', navH: Math.round(n.getBoundingClientRect().height),
    top: document.querySelector('.wf-top').scrollWidth - document.querySelector('.wf-top').clientWidth }; }"""
CURRENT = "() => (document.querySelector('#wfNav a[aria-current=true]') || {}).textContent || ''"
DIAGRAM = """() => { const d = document.getElementById('wfDiagram'), selected = d.querySelector('.wf-node[aria-current=step]'),
    tech = d.querySelector('details.wf-tech, .wf-tech details');
  return { title: (document.querySelector('#wfDetail h3') || {}).textContent || '',
    position: (document.getElementById('wfPosition') || {}).textContent || '', hash: location.hash,
    selected: selected && selected.getAttribute('href'), selectedCount: d.querySelectorAll('.wf-node[aria-current=step]').length,
    nodes: [...d.querySelectorAll('.wf-node')].map((n) => n.getAttribute('href')),
    groups: [...d.querySelectorAll('.wf-stage-link')].map((n) => n.getAttribute('href')),
    groupCurrent: [...d.querySelectorAll('.wf-stage-link[aria-current=step]')].map((n) => n.getAttribute('href')),
    grouped: [...d.querySelectorAll('.wf-groups > li')].map((li) => [li.querySelector(':scope > .wf-stage-link').getAttribute('href'), li.querySelectorAll(':scope > .wf-flow .wf-node').length]),
    stageRow: d.querySelectorAll('.wf-stage-map').length,
    prev: document.getElementById('wfPrev')?.disabled, next: document.getElementById('wfNext')?.disabled,
    badges: [...d.querySelectorAll('#wfDetail > .wf-badges .wf-tag')].map((n) => n.textContent),
    impact: d.querySelector('#wfDetail .wf-impact strong')?.textContent || '',
    tech: tech ? tech.open : null, text: document.getElementById('wfDetail')?.textContent || '' }; }"""


def wait_diagram(page, name):
    page.wait_for_function("name => document.querySelector('#wfDetail h3')?.textContent === name", arg=name, timeout=10000)
    return page.evaluate(DIAGRAM)


def navigation_checks(wf, api):
    """브라우저 기록과 같은 주소 재선택을 짧게 확인한다(독립 실행도 가능)."""
    common = {c["id"]: c for c in api["common"]}
    styles = common["styles"]["steps"]
    wf.click("#wfNav a[href='#common-styles']")
    wait_diagram(wf, styles[0]["name"])
    wf.click(f"#wfDiagram .wf-node[href='#common-styles--{styles[1]['key']}']")
    middle = wait_diagram(wf, styles[1]["name"])
    wf.click(f"#wfDiagram .wf-node[href='#common-styles--{styles[-1]['key']}']")   # 마지막 단계로 한 번에(기록 한 칸) — 단계 수와 상관없이
    last = wait_diagram(wf, styles[-1]["name"])
    wf.go_back()
    back = wait_diagram(wf, styles[1]["name"])
    wf.go_forward()
    forward = wait_diagram(wf, styles[-1]["name"])
    check("브라우저 뒤로/앞으로 — 상세 단계·선택 노드·주소 복원",
          back["hash"] == middle["hash"] and back["selected"] == middle["selected"] and back["selectedCount"] == 1
          and forward["hash"] == last["hash"] and forward["selected"] == last["selected"] and forward["selectedCount"] == 1,
          [back, forward])

    # 목록 스크롤로 바뀐 현재 절을 다이어그램으로 넘길 때 URL도 맞아야 한다.
    wf.click("#wfNav a[href='#common-styles']")
    wait_diagram(wf, styles[0]["name"])
    wf.click("#wfViewList")
    wf.locator("#common-agent").evaluate("e => e.scrollIntoView({block: 'start'})")
    wf.wait_for_function(f"{CURRENT}() === '에이전트 보기'", timeout=10000)
    wf.click("#wfViewDiagram")
    switched = wait_diagram(wf, common["agent"]["steps"][0]["name"])
    check("목록에서 다른 절로 스크롤한 뒤 다이어그램 전환 — 현재 절과 URL 일치",
          switched["hash"] == "#common-agent" and switched["selected"] == "#common-agent--" + common["agent"]["steps"][0]["key"], switched)

    # 모바일에서 이미 선택한 노드를 다시 누르면 새 기록 없이 설명으로 돌아간다.
    wf.click("#wfNav a[href='#common-styles']")
    wait_diagram(wf, styles[0]["name"])
    wf.click(f"#wfDiagram .wf-node[href='#common-styles--{styles[1]['key']}']")
    wait_diagram(wf, styles[1]["name"])
    wf.set_viewport_size({"width": 360, "height": 520})
    same = wf.locator(f"#wfDiagram .wf-node[href='#common-styles--{styles[1]['key']}']")
    same.scroll_into_view_if_needed()
    before = wf.evaluate("() => ({hash: location.hash, history: history.length})")
    same.click()
    selected = wait_diagram(wf, styles[1]["name"])
    wf.wait_for_function("""() => { const m = document.getElementById('wfMain').getBoundingClientRect(),
      d = document.getElementById('wfDetail').getBoundingClientRect(); return d.top >= m.top - 2 && d.top <= m.top + 24; }""", timeout=10000)
    after = wf.evaluate("() => ({hash: location.hash, history: history.length})")
    check("동일한 단계 주소 재클릭 — 상세 위치로 이동 · 선택 유지 · 브라우저 기록 중복 없음",
          before == after and selected["selected"] == before["hash"] and selected["selectedCount"] == 1, [before, after, selected])
    wf.set_viewport_size({"width": 1500, "height": 1000})


def diagram_checks(wf, ctx, api, workflow_requests):
    """등록부의 순서와 실제 탐색 결과를 견준다. 작업 실행이나 문서 수정은 하지 않는다."""
    wf.wait_for_selector("#wfDiagram", state="attached", timeout=20000)
    check("기본 보기는 다이어그램 — 전체 지도에서 선택 · 보기 단추 눌림 · 기존 긴 목록은 숨김",
          wf.get_attribute("#wfViewDiagram", "aria-pressed") == "true"
          and wf.get_attribute("#wfViewList", "aria-pressed") == "false" and not wf.locator(".wf-task").first.is_visible()
          and wf.locator("#overview").is_visible() and not wf.locator("#wfDiagram").is_visible())
    common = {c["id"]: c for c in api["common"]}
    tasks = {t["job"]: t for t in api["tasks"]}

    # 공통 모듈의 첫 단계와 끝 단계, 마우스·키보드로 노드를 직접 고르기.
    styles = common["styles"]["steps"]
    wf.click("#wfNav a[href='#common-styles']")
    first = wait_diagram(wf, styles[0]["name"])
    check("서식 관리자 다이어그램 — API 순서의 노드 · 첫 단계 선택 · 이전 비활성 · 기술 상세는 접힘",
          first["nodes"] == ["#common-styles--" + s["key"] for s in styles]
          and first["selected"] == "#common-styles--" + styles[0]["key"] and first["selectedCount"] == 1
          and first["prev"] is True and first["next"] is False and first["tech"] is False
          and first["position"].replace(" ", "") == f"단계1/{len(styles)}", first)
    wf.click("#wfNext")
    middle = wait_diagram(wf, styles[1]["name"])
    for i in range(2, len(styles)):   # 마지막 단계까지 — 단계 수는 등록부가 정한다(11-16 밤 「값 고치기 · 복사본 만들기」 가 더해져 넷: 전에는 셋을 가정해 떨어졌다)
        wf.click("#wfNext")
        last = wait_diagram(wf, styles[i]["name"])
    for i in range(len(styles) - 2, 0, -1):
        wf.click("#wfPrev")
        back = wait_diagram(wf, styles[i]["name"])
    check("공통 모듈 이전·다음 — 단계와 주소가 함께 바뀌고 마지막에서 다음 비활성",
          middle["hash"] == "#common-styles--" + styles[1]["key"] and last["next"] is True
          and last["position"].replace(" ", "") == f"단계{len(styles)}/{len(styles)}"
          and back["selected"] == middle["selected"] and back["prev"] is False and back["next"] is False,
          [middle, last, back])
    first_node = wf.locator(f"#wfDiagram .wf-node[href='#common-styles--{styles[0]['key']}']")
    first_node.focus()
    first_node.press("Enter")
    keyboard = wait_diagram(wf, styles[0]["name"])
    apply = next(s for s in styles if s["key"] == "apply")   # 「문서에 적용」 — 차례가 아니라 key 로(11-16 밤 「값 고치기」 가 둘째 자리에 들어옴)
    wf.click(f"#wfDiagram .wf-node[href='#common-styles--{apply['key']}']")
    selected = wait_diagram(wf, apply["name"])
    check("단계 노드는 키보드 Enter와 클릭으로 선택 — 상세·선택 표시가 일치",
          keyboard["selected"] == "#common-styles--" + styles[0]["key"] and keyboard["selectedCount"] == 1
          and selected["selected"] == "#common-styles--" + apply["key"] and selected["selectedCount"] == 1,
          [keyboard, selected])
    check("단계의 담당자와 문서 변경 구분 — 서식 선택은 사람·안 바뀜, 적용은 사람+스크립트·바뀜",
          first["badges"] == [api["by"][b] for b in styles[0]["by"]] + MUST(styles[0]) and first["impact"] == "안 바뀜"
          and selected["badges"] == [api["by"][b] for b in apply["by"]] + MUST(apply) and selected["impact"] == "바뀜",
          [first, selected])
    wf.screenshot(path=str(OUT / "06_diagram_styles.png"))
    navigation_checks(wf, api)

    # TASK 전체 순서: 흐름에는 **모든 묶음의 단계가 한 번에** 보이고(2026-11-16 사용자 「여기서 모든 단계를 한번에」 — 전에는 고른 묶음의 노드만), 다음은 묶음 경계를 건넌다.
    task = tasks["style_copy"]
    sequence = [(g, s) for g in task["stages"] for s in g["steps"]]
    wf.click("#wfNav a[href='#style_copy']")
    bad = []
    expected_nodes = [f"#style_copy--{g['id']}--{s['key']}" for g, s in sequence]
    expected_grouped = [[f"#style_copy--{g['id']}", len(g["steps"])] for g in task["stages"]]
    for i, (group, step) in enumerate(sequence):
        state = wait_diagram(wf, step["name"])
        expected = f"#style_copy--{group['id']}--{step['key']}"
        expected_badges = [api["by"][b] for b in step["by"]] + [label for key, label in (("auto", "자동"), ("must", "필수"), ("optional", "선택"), ("soon", "준비 중")) if (step[key] if key != "must" else not (step["auto"] or step["optional"] or step["soon"]))]
        expected_impact = {"none": "안 바뀜", "doc": "바뀜", "store": "안 바뀜 — 결과만 저장"}[step["change"]]
        if not (state["selected"] == expected and state["selectedCount"] == 1 and state["nodes"] == expected_nodes
                and state["grouped"] == expected_grouped and state["groupCurrent"] == [f"#style_copy--{group['id']}"] and state["stageRow"] == 0
                and state["position"].replace(" ", "") == f"단계{i + 1}/{len(sequence)}"
                and state["prev"] == (i == 0) and state["next"] == (i == len(sequence) - 1)
                and state["badges"] == expected_badges and state["impact"] == expected_impact):
            bad.append((i + 1, state))
        if i < len(sequence) - 1:
            wf.click("#wfNext")
    check("문서 서식 복사 — 모든 단계를 등록부 순서대로 탐색 · 묶음을 넘어 이동 · 첫/마지막 경계 · 모든 묶음의 노드를 한 번에(묶음 머리 아래 그 묶음의 단계 · 지금 묶음 표시 · 가로 묶음 줄 없음)", not bad, bad)
    numbers = wf.evaluate("() => [...document.querySelectorAll('#wfDiagram .wf-node .wf-node-no')].map((n) => n.textContent)")
    check("단계 번호는 TASK 전체로 이어 센다(묶음마다 다시 1 부터가 아니다)", numbers == [f"{i + 1:02d}" for i in range(len(sequence))], numbers)
    copy_group = next(g for g in task["stages"] if g["id"] == "copy")
    wf.click("#wfDiagram .wf-stage-link[href='#style_copy--copy']")
    stage = wait_diagram(wf, copy_group["steps"][0]["name"])
    check("단계 묶음을 누르면 그 묶음의 첫 단계로 이동",
          stage["selected"] == f"#style_copy--copy--{copy_group['steps'][0]['key']}"
          and len(stage["groups"]) == len(task["stages"]), stage)

    # 상세 주소를 새 탭에서 바로 열고, 모드를 바꾸어도 해당 단계가 유지되는지 확인.
    save = next(s for s in copy_group["steps"] if s["key"] == "save")
    direct = ctx.new_page()
    direct.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
    direct.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
    direct.goto(base + "/workflow#style_copy--copy--save")
    state = wait_diagram(direct, save["name"])
    check("상세 주소로 바로 열기 — TASK·묶음·단계와 상세가 일치", state["selected"] == "#style_copy--copy--save", state)
    direct.click("#wfViewList")
    direct.click("#wfViewDiagram")
    state = wait_diagram(direct, save["name"])
    check("다이어그램 ↔ 목록 전환 뒤에도 고른 단계 유지", state["selected"] == "#style_copy--copy--save", state)
    direct.goto(base + "/workflow#common-styles--apply")
    state = wait_diagram(direct, apply["name"])
    check("공통 모듈의 상세 주소로 바로 열기", state["selected"] == "#common-styles--apply", state)
    direct.close()

    # 이관의 기술 상세와 관련 공통 모듈 이동.
    wf.click("#wfNav a[href='#plan_to_report']")
    wf.click("#wfDiagram .wf-stage-link[href='#plan_to_report--map']")
    wf.click("#wfDiagram .wf-node[href='#plan_to_report--map--llm']")
    llm = next(s for g in tasks["plan_to_report"]["stages"] for s in g["steps"] if s["key"] == "llm")
    state = wait_diagram(wf, llm["name"])
    tech = wf.locator("#wfDiagram details.wf-tech, #wfDiagram .wf-tech details").first
    check("기술 상세는 기본 접힘 — 에이전트·모듈·사양 정보를 필요할 때 확인", state["tech"] is False, state)
    tech.locator("summary").click()
    tech_text = tech.inner_text()
    check("기술 상세 펼치기 — 실제 에이전트·모듈·사양 포함",
          llm["agents"][0]["name"] in tech_text and llm["modules"][0]["path"] in tech_text and llm["spec"]["file"] in tech_text, tech_text)
    # TASK 문서(spec_워크플로우 ② §10) — 고른 단계의 조건 · 시작 점검(접어 둠 — 펴면 때마다 묶음이 열린 채)
    ent = wf.evaluate("""() => { const d = document.getElementById('wfDiagram'), e = d.querySelector('details.wf-entry-context');
      return { cond: [...d.querySelectorAll('#wfDetail .wf-conds .wf-cond dt')].map((x) => x.textContent), condText: [...d.querySelectorAll('#wfDetail .wf-conds .wf-cond dd')].map((x) => x.textContent),
        entry: e && { open: e.open, summary: e.querySelector('summary').textContent, doc: e.querySelector('.wf-entry-doc code').textContent,
          groups: [...e.querySelectorAll('.wf-entry-group')].map((g) => [g.dataset.when, g.querySelectorAll('.wf-entry-items > li').length, g.open]) } }; }""")
    relay = tasks["plan_to_report"]
    auto = sum(len(g["items"]) for g in relay["entry"] if g["when"] != "manual")
    check("다이어그램 — 고른 단계의 조건(하려면 · 끝난 것으로 보는 때 · 남기는 것 · 보정 — 등록부의 글) · 시작 점검은 접어 두고 때마다 묶음 · TASK 문서 경로",
          ent["cond"] == [c["name"] for c in llm["cond"]] == ["하려면", "끝난 것으로 보는 때", "남기는 것 · 보정"] and ent["condText"] == [c["text"] for c in llm["cond"]]
          and bool(ent["entry"]) and ent["entry"]["open"] is False and f"{auto}가지" in ent["entry"]["summary"] and ent["entry"]["doc"] == relay["doc"] == "tasks/plan_to_report.md"
          and ent["entry"]["groups"] == [[g["when"], len(g["items"]), True] for g in relay["entry"]] and [g["when"] for g in relay["entry"]] == ["start", "upload", "enter", "manual"], ent)
    wf.screenshot(path=str(OUT / "07_diagram_transfer.png"))
    wf.click("#wfDiagram .wf-stage-link[href='#plan_to_report--review']")   # 헤딩 · 표 분석은 1단계 「문서 검토」 의 단계다(spec_작업 ② §21 — 전에는 3단계 안)
    wf.click("#wfDiagram .wf-node[href='#plan_to_report--review--heads']")
    wf.click("#wfDiagram .wf-related a[href='#common-headings']")
    related = wait_diagram(wf, common["headings"]["steps"][0]["name"])
    check("관련 공통 모듈로 이동 — 첫 단계부터 확인", related["selected"] == "#common-headings--" + common["headings"]["steps"][0]["key"], related)
    check("공통 모듈에는 시작 점검 · 단계 조건이 없다(TASK 의 것)", wf.locator("#wfDiagram .wf-entry-context, #wfDiagram .wf-conds").count() == 0)
    wf.click("#wfNav a[href='#report_merge']")
    wf.wait_for_selector("#wfDiagram .wf-empty")
    check("준비 중 TASK — 빈 상태 안내 · 이전/다음 조작 없음",
          wf.locator("#wfDiagram .wf-empty").is_visible() and wf.locator("#wfPrev, #wfNext").count() == 0)

    # 상세를 펼친 상태에서 긴 모듈 경로와 단계 묶음이 좁은 화면을 넘치지 않아야 한다.
    wf.click("#wfNav a[href='#plan_to_report']")
    wf.click("#wfDiagram .wf-stage-link[href='#plan_to_report--map']")
    wf.click("#wfDiagram .wf-node[href='#plan_to_report--map--llm']")
    wait_diagram(wf, llm["name"])
    wf.locator("#wfDiagram details.wf-tech, #wfDiagram .wf-tech details").first.locator("summary").click()
    wf.locator("#wfDiagram details.wf-entry-context > summary").click()   # 시작 점검도 편 채로(긴 글 · 꼬리표가 좁은 폭을 넘지 않아야 한다)
    bad = []
    for width in (1500, 900, 480, 360):
        wf.set_viewport_size({"width": width, "height": 1000})
        wf.wait_for_timeout(100)
        overflow = wf.evaluate(OVERFLOW)
        if overflow["page"] > 0 or overflow["main"] > 1 or overflow["top"] > 1:
            bad.append((width, overflow))
    check("다이어그램 — 1500·900·480·360px에서 기술 상세를 펴도 가로 넘침 없음", not bad, bad)
    wf.screenshot(path=str(OUT / "08_diagram_mobile.png"))
    check("다이어그램 탐색은 읽기만 — API 요청은 GET /api/workflow 와 조립한 TASK 읽기(GET /api/tasks · /api/tasks.js)뿐",
          bool(workflow_requests) and all(method == "GET" and url.split("?", 1)[0] in (base + "/api/workflow", base + "/api/tasks", base + "/api/tasks.js") for method, url in workflow_requests), workflow_requests)
    wf.set_viewport_size({"width": 1500, "height": 1000})
    wf.click("#wfViewList")
    # 상세 주소로 목록을 열며 펼쳐진 단계가 기존 목록 검사의 초기 상태에 섞이지 않게 한다.
    wf.click("#wfCloseAll")
    wf.click("#wfNav a[href='#overview']")
    wf.wait_for_function(f"{CURRENT}() === '전체 보기'", timeout=10000)


def main():
    wait_server()
    api = requests.get(base + "/api/workflow", timeout=30).json()
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1700, "height": 1000}, device_scale_factor=1)
        workflow_requests = []
        ctx.on("request", lambda r: workflow_requests.append((r.method, r.url)) if "/api/" in r.url and "/workflow" in r.frame.page.url else None)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())

        # ---- 시작 화면의 링크
        page.goto(base)
        page.wait_for_selector("#workflowLink")
        t = page.evaluate("""() => { const a = document.getElementById('workflowLink'), r = a.getBoundingClientRect(), kids = [...a.parentElement.children].filter((e) => e.offsetWidth > 0);
          return { direct: a.parentElement.classList.contains('topbar'), href: a.getAttribute('href'), target: a.target, rel: a.rel, label: a.getAttribute('aria-label'), icon: !!a.querySelector('svg'),
            text: a.textContent.trim() !== '', tip: a.title, w: Math.round(r.width), h: Math.round(r.height), last: kids.pop().id, before: kids.pop().id, deco: getComputedStyle(a).textDecorationLine, top: r.top }; }""")
        check("시작 화면 상단 바 — 에이전트 아이콘 앞에 링크 「워크플로우」(/workflow · 새 탭 · 글 없이 아이콘만 32×32 · 이름은 도움말 · 밑줄 없음) · 맨 끝은 에이전트 아이콘(2026-11-18 — 전의 「에이전트 설정」 링크 자리)",
              t["direct"] and t["href"] == "/workflow" and t["target"] == "_blank" and "noopener" in t["rel"] and t["label"] == "TASK 워크플로우" and t["icon"] and not t["text"] and t["tip"].startswith("TASK 워크플로우 — ") and t["w"] == 32 and t["h"] == 32
              and t["last"] == "agentBtn" and t["before"] == "workflowLink" and t["deco"] == "none" and t["top"] < 40, t)
        with ctx.expect_page() as fresh:
            page.click("#workflowLink")
        wf = fresh.value
        wf.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        wf.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        wf.wait_for_selector("#wfMain .wf-task", state="attached", timeout=20000)
        check("링크를 누르면 새 탭에 /workflow(연 화면은 그대로)", wf.url == base + "/workflow" and page.url.rstrip("/") == base and wf.title().startswith("TASK 워크플로우"), [wf.url, page.url])
        wf.set_viewport_size({"width": 1500, "height": 1000})
        if args.navigation_only:
            navigation_checks(wf, api)
            b.close()
            check("콘솔 오류 없음", not errors, errors[:5])
            return
        diagram_checks(wf, ctx, api, workflow_requests)

        # ---- 목차 · 전체 보기
        nav = wf.evaluate("""() => ({ links: [...document.querySelectorAll('#wfNav a')].map((a) => [a.getAttribute('href'), a.textContent, a.className]), heads: [...document.querySelectorAll('#wfNav h2')].map((x) => x.textContent), make: (document.querySelector('#wfNav [data-wf-compose]') || {}).textContent,
          secs: [...document.querySelectorAll('#wfMain .wf-sec')].map((s) => s.id), title: document.querySelector('.wf-title').textContent })""")
        jobs = [t["job"] for t in api["tasks"]]
        check("목차 — 전체 보기 · TASK 일곱(이름 = TASK_CATALOG · 준비 중은 흐리게) · 공통 모듈 아홉 / 본문의 절이 같은 차례",
              nav["title"] == "TASK 워크플로우" and nav["heads"] == ["TASK", "단계", "도구"] and nav["make"] == "＋ TASK 조립" and len(nav["links"]) == 1 + len(jobs) + len(api["common"]) and nav["links"][0][:2] == ["#overview", "전체 보기"]   # 공통 모듈 수는 등록부에서(편집 구역 · 대시보드 · 공유가 더해져 열하나)
              and [x[0] for x in nav["links"][1:8]] == ["#" + j for j in jobs] and nav["links"][3][1] == "사업계획서 → 연차보고서 이관" and nav["links"][5][2] == "wf-soon"
              and [x[:2] for x in nav["links"][8:12]] == [["#common-stage_review", "문서 검토"], ["#common-stage_fit", "구성 맞추기"], ["#common-stage_fill", "내용 넣기"], ["#common-stage_clean", "문서 정리"]]   # 단계 모듈 넷이 공통 모듈의 맨 앞(spec_워크플로우 ② §13 — TASK 가 조립하는 일반 단계)
              and nav["links"][12][:2] == ["#common-intake", "문서 올리기 · 첫 분석"] and nav["secs"] == ["overview", "wfCompose"] + jobs + ["common-" + c["id"] for c in api["common"]], nav)   # 「TASK 조립」 절이 전체 보기 아래(spec_워크플로우 ② §14)
        ov = wf.evaluate("""() => ({ rows: [...document.querySelectorAll('.wf-over > li')].map((li) => [li.dataset.job, li.querySelector('.wf-over-name').textContent, [...li.querySelectorAll('.wf-chain > li')].map((c) => c.textContent)]),
          dots: [...document.querySelectorAll('.wf-over > li[data-job=plan_to_report] .wf-chain > li')].map((c) => [...c.querySelectorAll('.wf-dot')].map((d) => d.className.replace('wf-dot wf-d-', '')).join('+')),
          legend: [...document.querySelectorAll('.wf-legend .wf-tag')].map((x) => x.textContent), commons: document.querySelectorAll('.wf-commons a').length, cur: document.querySelector('#wfNav a[aria-current=true]').textContent })""")
        rows = {r[0]: r for r in ov["rows"]}
        check("전체 보기 — TASK 마다 한 줄: 이관 = 「1단계 문서 검토 › 2단계 구성 맞추기 › 3단계 내용 넣기 › 4단계 문서 정리」(spec_작업 ② §21) · 취합 = 1~3단계(그대로) · 「연차보고서 취합」 은 준비 중",
              len(ov["rows"]) == 7 and rows["plan_to_report"][2] == ["1단계문서 검토", "2단계구성 맞추기", "3단계내용 넣기", "4단계문서 정리"]
              and rows["plan_merge"][2] == ["1단계프로젝트 구성", "2단계문서 프레임 작성", "3단계내용 매핑"] and rows["report_merge"][2] == ["준비 중"]
              and rows["plan_fit"][2] == ["1단계프로젝트 구성", "2단계헤딩 추출", "3단계표"] and rows["style_copy"][2] == ["준비", "서식 복사", "다시 쓰기"] and rows["doc_edit"][1] == "문서 일반 편집", ov["rows"])
        check("묶음의 점 — 이관 1단계는 보라(LLM 검증·보완 — 문서 안 바뀜) · 2단계 · 3단계 보라+주황(LLM · 문서 바뀜) · 4단계 주황 / 범례 · 공통 모듈 아홉 / 목차의 지금 절 = 전체 보기",
              ov["dots"] == ["llm", "llm+doc", "llm+doc", "doc"] and ov["legend"] == ["스크립트", "LLM", "사람", "문서 바뀜", "자동", "필수", "선택"] and ov["commons"] == len(api["common"]) and ov["cur"] == "전체 보기", ov)
        wf.screenshot(path=str(OUT / "01_overview.png"))
        # ---- 단계 모듈(spec_워크플로우 ② §13 — 2026-11-19 사용자 "각 단계를 , 여기 모듈로 두고,, task 모듈로 조립할 수 있도록"): 이관의 묶음 머리에 「조립한 단계 모듈」 링크 · 모듈 절의 꼬리표 「단계 모듈」 · 「조립한 TASK」
        sm = wf.evaluate("""() => { const sec = document.getElementById('common-stage_review'), io = [...sec.querySelectorAll('.wf-io dt')].map((d) => d.textContent);
          return { kind: sec.querySelector('h2 .wf-kind').textContent, io, used: [...sec.querySelectorAll('.wf-io .wf-chip')].map((a) => a.getAttribute('href')), steps: [...sec.querySelectorAll('.wf-step')].map((d) => d.dataset.step),
            plain: document.querySelector('#common-intake h2 .wf-kind').textContent,
            links: [...document.querySelectorAll('#plan_to_report .wf-stage')].map((g) => { const a = g.querySelector('.wf-stage-module a'); return a && [g.dataset.stage, a.getAttribute('href'), a.textContent]; }),
            others: document.querySelectorAll('#plan_merge .wf-stage-module, #plan_fit .wf-stage-module').length }; }""")
        check("단계 모듈 — 「문서 검토」 절: 꼬리표 「단계 모듈」 · 「조립한 TASK」 = 이관 · 단계(헤딩·표 분석 · LLM 검증·보완) / 이관의 묶음 넷 머리에 「조립한 단계 모듈」 링크 / 조립하지 않은 TASK(취합 · 양식 표준화)에는 없음 · 다른 공통 모듈은 「공통 모듈」 그대로",
              sm["kind"] == "단계" and sm["io"] == ["여는 곳", "조립한 TASK"] and sm["used"] == ["#plan_to_report"] and sm["steps"] == ["heads", "headsLlm"] and sm["plain"] == "도구"   # 화면 말 「단계」 · 「도구」(전의 「단계 모듈」 · 「공통 모듈」 — 2026-11-19 사용자)
              and sm["links"] == [["review", "#common-stage_review", "문서 검토"], ["frame", "#common-stage_fit", "구성 맞추기"], ["map", "#common-stage_fill", "내용 넣기"], ["clean", "#common-stage_clean", "문서 정리"]] and sm["others"] == 0, sm)

        # ---- TASK 절(이관)
        wf.click(".wf-over > li[data-job=plan_to_report] .wf-over-name")
        wf.wait_for_function(f"{CURRENT}() === '사업계획서 → 연차보고서 이관'", timeout=10000)
        ts = wf.evaluate("""() => { const s = document.getElementById('plan_to_report'), io = [...s.querySelectorAll('.wf-io dt')].map((d) => d.textContent);
          return { h2: s.querySelector('h2').textContent, lead: s.querySelector('.wf-lead').textContent, io, prompt: s.querySelector('.wf-io code').textContent,
            stages: [...s.querySelectorAll('.wf-stage')].map((g) => [g.dataset.stage, g.querySelector('.wf-stage-no').textContent, g.querySelector('h3').textContent, g.querySelectorAll('.wf-step').length]),
            map: [...s.querySelectorAll('.wf-stage[data-stage=map] .wf-step')].map((d) => [d.dataset.step, d.querySelector('.wf-no').textContent, d.querySelector('.wf-name').textContent,
              [...d.querySelectorAll('summary .wf-tag')].map((x) => x.textContent).join('|'), d.querySelector('.wf-does').offsetHeight > 0, d.open]),
            top: Math.round(s.getBoundingClientRect().top - document.getElementById('wfMain').getBoundingClientRect().top), hash: location.hash }; }""")
        check("이관 절 — 이름·설명(TASK_CATALOG) · 받는 문서 → 산출물 → 알아 둘 것 → 전제(jobs/plan_to_report.md) · 그 절로 스크롤(#plan_to_report)",
              ts["h2"] == "TASK사업계획서 → 연차보고서 이관" and "연차보고서로 옮깁니다" in ts["lead"] and ts["io"] == ["받는 문서", "산출물", "알아 둘 것", "전제", "한 번에 진행", "에이전트가 묻는 것", "멈추거나 남기는 곳 · 보정", "단계별(세부 작업)"] and ts["prompt"] == "jobs/plan_to_report.md"
              and ts["hash"] == "#plan_to_report" and -2 <= ts["top"] <= 20, ts)
        check("묶음 넷 — 「1단계 문서 검토」(3) · 「2단계 구성 맞추기」(5 — 구성 불러오기(선택) 포함) · 「3단계 내용 넣기」(7) · 「4단계 문서 정리」(1)",
              ts["stages"] == [["review", "1단계", "문서 검토", 3], ["frame", "2단계", "구성 맞추기", 5], ["map", "3단계", "내용 넣기", 7], ["clean", "4단계", "문서 정리", 1]], ts["stages"])
        m = {x[0]: x for x in ts["map"]}
        check("3단계의 단계 줄 — ② 자리 연결 → LLM 검토(선택) → ③ 넣기 계획 → 표 대응 · 빈 자리 검토(LLM) → ④ 내용 반영(사람 · 문서 바뀜) → ⑤ 준비 중 · 하는 일은 펴지 않아도 보임(헤딩·표 분석은 1단계 · 다시 분석은 2단계 — §21)",
              [x[0] for x in ts["map"]] == ["link", "llm", "plan", "tableMap", "gaps", "apply", "later"] and [m[k][1] for k in ("link", "plan", "apply", "later")] == ["②", "③", "④", "⑤"]
              and m["link"][2:4] == ["자리 연결", "스크립트|필수"] and m["llm"][3] == "LLM|선택" and m["apply"][3] == "사람|스크립트|문서 바뀜|필수" and m["later"][3] == "스크립트|준비 중"
              and all(x[4] and not x[5] for x in ts["map"]), ts["map"])
        wf.click("#plan_to_report .wf-step[data-step=llm] > summary")
        d = wf.evaluate("""() => { const d = document.querySelector('#plan_to_report .wf-step[data-step=llm]'), a = d.querySelector('.wf-agent');
          return { open: d.open, rows: [...d.querySelectorAll('.wf-more dt')].map((x) => x.textContent), ano: a.querySelector('.wf-ano').textContent, aname: a.querySelector('.wf-agent-link').textContent, ahref: a.querySelector('.wf-agent-link').getAttribute('href'), model: a.querySelector('.wf-tag').textContent,
            how: a.querySelector('.wf-muted').textContent, role: a.querySelector('.wf-role').textContent.slice(0, 12), mods: [...d.querySelectorAll('.wf-mod code')].map((x) => x.textContent),
            doc: d.querySelector('.wf-mod span').textContent.trim().slice(0, 8), spec: d.querySelector('.wf-more dd:last-child').textContent }; }""")
        check("단계를 누르면 세부 — 문서 · 에이전트(작업 번호 09 · 자리 연결 검토(에이전트 설정 페이지 /agents#merge_links 로 가는 링크) · Opus 5.5 · 코드가 정함 · 눌러야 돎 · 역할 글) · 모듈(파일 + 설명 첫 줄) · 사양 자리",
              d["open"] and d["rows"] == ["문서", "에이전트", "코드", "사양"] and d["ano"] == "09" and d["aname"] == "자리 연결 검토" and d["ahref"] == "/agents#merge_links" and d["model"] == "Opus 5.5" and d["how"] == "코드가 정함 · 눌러야 돎"
              and d["role"].startswith("사업계획서") and d["mods"] == ["app/merge_llm.py", "app/merge_chunks.py", "app/merge_guides.py", "app/job_prompts.py"] and d["doc"].startswith("병합")
              and d["spec"] == "spec/spec_병합.md ② §4", d)
        # TASK 문서(spec_워크플로우 ② §10) — 시작 점검(진행 방식 아래 · 단계 묶음 위: 때마다 묶음 · 접힘) · 단계의 조건(세부 앞)
        en = wf.evaluate("""() => { const s = document.getElementById('plan_to_report'), box = document.getElementById('plan_to_report--entry'), head = s.querySelector('.wf-entry-head');
          const after = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING), slots = box.querySelector('li[data-entry=slots]'), d = s.querySelector('.wf-step[data-step=llm]');
          return { head: head.textContent, doc: head.querySelector('code').textContent, order: after(s.querySelector('.wf-ways'), head) && after(box, s.querySelector('.wf-stages')),
            groups: [...box.querySelectorAll('.wf-entry-group')].map((g) => [g.dataset.when, g.querySelector('summary b').textContent, g.querySelectorAll('.wf-entry-items > li').length, g.open]),
            slots: { name: slots.querySelector('.wf-name').textContent, tags: [...slots.querySelectorAll('.wf-tag')].map((x) => x.textContent), does: slots.querySelector('.wf-does').textContent, miss: slots.querySelector('.wf-miss').textContent },
            cond: [...d.querySelectorAll('.wf-cond dt')].map((x) => x.textContent), condFirst: after(d.querySelector('.wf-cond'), d.querySelector('.wf-more')),
            common: document.querySelectorAll('#common-headings .wf-cond, #common-headings .wf-entry, #report_merge .wf-entry').length }; }""")
        relay = next(t for t in api["tasks"] if t["job"] == "plan_to_report")
        item = next(c for g in relay["entry"] for c in g["items"] if c["key"] == "slots")
        check("이관 절의 「시작 점검」 — 진행 방식 아래 · 단계 묶음 위 · 저절로 확인하는 것의 수 + TASK 문서 경로 · 때마다 묶음 넷(시작할 때 · 올릴 때 · 화면을 열 때 · 저절로 돌지 않는 것 — 접힘)",
              en["head"].startswith("시작 점검") and f"{sum(len(g['items']) for g in relay['entry'] if g['when'] != 'manual')}가지" in en["head"] and en["doc"] == "tasks/plan_to_report.md" and en["order"]
              and en["groups"] == [[g["when"], g["name"], len(g["items"]), False] for g in relay["entry"]] and [g[1] for g in en["groups"]] == ["TASK 를 시작할 때", "문서를 올릴 때", "TASK 화면을 열 때", "저절로 돌지 않는 것"], en)
        check("시작 점검 항목 — 이름 · 누가 · 무엇을 확인하나 · 「안 맞으면」(등록부의 글) / 단계 세부에 조건(하려면 · 끝난 것으로 보는 때 · 남기는 것 · 보정)이 세부 앞에 / 공통 모듈 · 준비 중 TASK 에는 없음",
              en["slots"] == {"name": "두 문서가 있는가", "tags": ["스크립트"], "does": item["does"], "miss": "안 맞으면 " + item["miss"]}
              and en["cond"] == ["하려면", "끝난 것으로 보는 때", "남기는 것 · 보정"] and en["condFirst"] and en["common"] == 0, en)
        wf.click("#wfOpenAll")
        opened = wf.evaluate("() => [...document.querySelectorAll('#plan_to_report--entry .wf-entry-group, #plan_to_report .wf-step')].every((g) => g.open)")
        wf.click("#wfCloseAll")
        closed = wf.evaluate("() => [...document.querySelectorAll('#plan_to_report--entry .wf-entry-group, #plan_to_report .wf-step')].every((g) => !g.open)")
        check("「모두 펼치기」·「모두 접기」 는 시작 점검 묶음도 함께", opened and closed, [opened, closed])
        wf.click("#plan_to_report .wf-step[data-step=llm] > summary")   # 아래 검사(공통 모듈 링크)가 보던 상태로 — llm 단계는 펴 둔다
        wf.screenshot(path=str(OUT / "02_task_transfer.png"))

        # ---- 공통 모듈 · 링크로 오가기
        wf.click("#plan_to_report .wf-step[data-step=heads] > summary")
        wf.click("#plan_to_report .wf-step[data-step=heads] .wf-more a.wf-chip")
        wf.wait_for_function(f"{CURRENT}() === '헤딩 추출'", timeout=10000)
        c = wf.evaluate("""() => { const s = document.getElementById('common-headings');
          return { h2: s.querySelector('h2').textContent, io: [...s.querySelectorAll('.wf-io dt')].map((d) => d.textContent), used: [...s.querySelectorAll('.wf-io .wf-links a')].map((a) => a.textContent),
            steps: [...s.querySelectorAll('.wf-step')].map((d) => [d.querySelector('.wf-no').textContent, d.querySelector('.wf-name').textContent]), hash: location.hash,
            agents: (() => { const d = s.querySelector('.wf-step[data-step=stage2]'); d.open = true; return [...d.querySelectorAll('.wf-ano')].map((x) => x.textContent); })() }; }""")
        # 2단계의 에이전트 01(heading_rules) — 「헤딩 그래프(LLM)」 은 그래프 전에 못 맞춤·충돌 묶음의 규칙 보강을 먼저 돈다(spec_헤딩_추출 ② §3, 2026-11-16)
        # 18(tpl_agent) — 헤딩 판정 뒤에 이어서 템플릿마다 서식 정리 계획을 받는다(같은 날 — 등록부 2단계의 agents 에 더해짐: spec_hwpx_웹편집 ② §8-4)
        check("단계의 「공통 모듈」 링크 → 「헤딩 추출」 절: 여는 곳 · 쓰는 TASK(양식 표준화 · 취합 · 이관 · 서식 복사) · 1~3단계 + 규칙 보강 · 뼈대 유지 · 2단계의 에이전트 01~05 · 18",
              c["h2"] == "도구헤딩 추출" and c["io"] == ["여는 곳", "쓰는 TASK"] and c["used"] == ["사업계획서 양식 표준화", "사업계획서 취합", "사업계획서 → 연차보고서 이관", "문서 서식 복사"] and c["hash"] == "#common-headings"
              and c["steps"] == [["1단계", "추출"], ["", "규칙 보강(LLM)"], ["", "구분 기준 판독(먼저)"], ["2단계", "헤딩 그래프"], ["3단계", "표 구조"], ["", "뼈대 유지"]]   # 판독 — 82c9793(헤딩 그래프보다 먼저: spec_헤딩_추출 ② §13)
              and c["agents"] == ["01", "02", "03", "04", "05", "18"], c)
        wf.screenshot(path=str(OUT / "03_common_headings.png"))
        wf.locator("#common-headings .wf-io .wf-links a", has_text="문서 서식 복사").click()
        wf.wait_for_function(f"{CURRENT}() === '문서 서식 복사'", timeout=10000)
        sc = wf.evaluate("""() => [...document.querySelectorAll('#style_copy .wf-stage[data-stage=copy] .wf-step')].map((d) => d.querySelector('.wf-no').textContent + d.querySelector('.wf-name').textContent)""")
        check("「쓰는 TASK」 → 「문서 서식 복사」 절: ① 후보 찾기 → ② LLM 검토 → ③ 저장 → ④ PDF 검증", sc == ["①후보 찾기", "②LLM 검토", "③저장", "④PDF 검증"] and wf.evaluate("location.hash") == "#style_copy", sc)
        wf.click("#wfNav a[href='#overview']")
        wf.wait_for_function(f"{CURRENT}() === '전체 보기'", timeout=10000)
        wf.click(".wf-over > li[data-job=plan_merge] .wf-chain a[href='#plan_merge--map']")
        wf.wait_for_function(f"{CURRENT}() === '사업계획서 취합'", timeout=10000)
        g = wf.evaluate("""() => { const g = document.getElementById('plan_merge--map'), r = g.getBoundingClientRect(), m = document.getElementById('wfMain').getBoundingClientRect();
          return { top: Math.round(r.top - m.top), steps: [...g.querySelectorAll('.wf-step')].map((d) => d.dataset.step), ano: (() => { const d = g.querySelector('.wf-step[data-step=llm]'); d.open = true; return d.querySelector('.wf-ano').textContent; })() }; }""")
        check("전체 보기의 묶음 사슬을 누르면 그 묶음으로 — 취합 3단계: 기관 문서 · 헤딩·표 분석 · ② 자리 연결 · LLM 검토(에이전트 12) · ③ · ④ · 끌어 넣기",
              -2 <= g["top"] <= 20 and g["steps"] == ["part", "heads", "link", "llm", "plan", "apply", "drop"] and g["ano"] == "12", g)

        # ---- 주소로 바로 열기 · 모두 펼치기/접기
        direct = ctx.new_page()
        direct.set_viewport_size({"width": 1500, "height": 1000})
        direct.goto(base + "/workflow#common-division")
        direct.wait_for_selector("#wfMain .wf-task", state="attached", timeout=20000)
        direct.click("#wfViewList")
        direct.wait_for_function(f"{CURRENT}() === '프로젝트 구성(구분 기준)'", timeout=10000)
        top = direct.evaluate("() => Math.round(document.getElementById('common-division').getBoundingClientRect().top - document.getElementById('wfMain').getBoundingClientRect().top)")
        check("주소 /workflow#common-division 로 그 절이 바로 열림(목차 표시도 따라감)", -2 <= top <= 20, top)
        direct.close()
        wf.click("#wfOpenAll")
        n = wf.evaluate("() => [document.querySelectorAll('details.wf-step').length, document.querySelectorAll('details.wf-step[open]').length]")
        wf.click("#wfCloseAll")
        n2 = wf.evaluate("() => document.querySelectorAll('details.wf-step[open]').length")
        total = sum(len(g["steps"]) for t in api["tasks"] for g in t["stages"]) + sum(len(c["steps"]) for c in api["common"])
        check("「모두 펼치기」 → 모든 단계가 펴짐 · 「모두 접기」 → 모두 접힘", n == [total, total] and n2 == 0, [n, n2, total])

        # ---- 폭
        wide = wf.evaluate(OVERFLOW)
        bad = []
        for w in (900, 480, 360):
            wf.set_viewport_size({"width": w, "height": 900})
            wf.wait_for_timeout(250)
            o = wf.evaluate(OVERFLOW)
            if o["page"] > 0 or o["main"] > 1 or o["top"] > 1 or not o["navRow"] or o["navH"] > 44:
                bad.append((w, o))
        check("폭 — 1500px 은 목차가 왼쪽 열 · 900·480·360px 은 목차가 위 가로 줄(높이 ≤ 44px) · 어느 폭에서도 가로 넘침 없음", not bad and wide["page"] <= 0 and wide["main"] <= 1 and not wide["navRow"], [wide, bad])
        wf.evaluate("() => { document.getElementById('plan_to_report').scrollIntoView(); document.querySelector('#plan_to_report .wf-step[data-step=llm]').open = true; }")
        wf.screenshot(path=str(OUT / "04_narrow_360.png"))
        wf.close()

        # ---- 문서를 연 상단 바
        r = requests.post(base + "/api/docs", files={"file": (SMALL.name, SMALL.read_bytes(), "application/octet-stream")}, timeout=120)
        assert r.status_code == 200, r.text
        page.evaluate(f"() => {{ location.hash = '#w={r.json()['docId']}'; }}")
        page.reload()
        page.wait_for_selector("#doc .para", timeout=120000)
        bad = []
        for w in (1600, 1280, 1100, 900, 800):
            page.set_viewport_size({"width": w, "height": 900})
            page.wait_for_timeout(350)
            m = page.evaluate("""() => { const bar = document.querySelector('.topbar'), a = document.getElementById('workflowLink'), pb = document.getElementById('panelBtn'), r = a.getBoundingClientRect();
              return { sw: bar.scrollWidth, cw: bar.clientWidth, h: Math.round(bar.getBoundingClientRect().height), ah: Math.round(r.height), aw: Math.round(r.width), shown: r.width > 0, text: a.textContent.trim() !== '',
                inside: r.right <= innerWidth + 0.5 && r.left >= 0, panel: pb.hidden || pb.offsetWidth === 0 || pb.getBoundingClientRect().right <= innerWidth + 0.5,
                pbIcon: !!pb.querySelector('svg') && pb.textContent.trim() === '', pbName: pb.getAttribute('aria-label'), pbTip: pb.title, pbOpen: pb.getAttribute('aria-expanded'), pbW: pb.offsetWidth }; }""")
            pb_ok = m["pbIcon"] and m["pbW"] == 30 and (m["pbName"], m["pbOpen"]) in (("도구 닫기", "true"), ("문서 도구", "false")) and m["pbTip"].startswith(m["pbName"] + " — ")
            ok = m["sw"] <= m["cw"] + 1 and m["h"] == 35 and m["panel"] and pb_ok and ((m["shown"] and m["ah"] == 26 and m["aw"] == 30 and m["inside"] and not m["text"]) if w > 880 else not m["shown"])
            if not ok:
                bad.append((w, m))
        check("문서를 연 상단 바 — 1600·1280·1100·900px 넘침 없음 · 높이 35px · 링크 30×26 글 없이 아이콘만(어느 폭에서나) · 패널 여닫기도 아이콘(이름 「도구 닫기」/「문서 도구」 는 도움말·낭독) 창 안 · 800px 에서는 링크를 감춤(넘침 없음)", not bad, bad)
        page.set_viewport_size({"width": 1280, "height": 900})
        page.screenshot(path=str(OUT / "05_topbar_doc.png"), clip={"x": 0, "y": 0, "width": 1280, "height": 60})
        b.close()
    check("콘솔 오류 없음", not errors, errors[:5])


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

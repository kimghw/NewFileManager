"""조립 화면 — 「1」 문서 하나 조립과, 그 워크플로우의 **서버 실행을 문서 화면이 따라가는가**(spec_워크플로우 ② §18-13 걸음 6의 화면 — 2026-11-20 사용자 "그리고 문서 하나는 왜 안되냐?" → 답 「조립한 것만 서버로」:
app/static/workflow.js(틀 「1」 — 줄 편집기 한 칸) · app/custom_tasks.py(shape single) · app/static/task_catalog.js(taskIsSingle) · workflow_exec.js(singleRunServer · singleRunFollow · 3초 확인) ·
dashboard.js(dashSingleLive) · doc_agent_work.js(agwSingleStatus)) 화면 확인 — 임시 서버(임시 조립 저장소 · 임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 흉내 없이 진짜 끝점으로(서버 쪽 실행기 포함).

    python -X utf8 tools/smoke_single_compose_ui.py <그림·임시 폴더> [--port 18760]

**전제 — 스위치가 켜져 있다**: app/custom_tasks.py `SINGLE_OPEN = True`(조립 폼의 「1」) · app/workflow_state.py `OPEN_CUSTOM = {"single"}`(조립한 문서 하나만 서버가 맡는다 — 붙박이는 그대로 화면).
꺼져 있으면 ① 의 「준비 중」 · ③ 의 「서버가 맡는 묶음」 에서 떨어진다.

보는 것:
- ① 「새 워크플로우 조립」 → 문서 입출력 「1」 문서 하나가 켜져 있다(「준비 중」 없음) → 고르면 줄 목록 = 그 틀의 처음 것(서버 `byShape.single.flow` — 붙박이 「사업계획서 양식 표준화」 의 묶음 · 줄) ·
  줄은 모두 한 칸(목적 문서) · 서버 검사: 거절 없음 · 저장 = {shape: single, target: plan, flow} → 서버의 정의 v2 · 목록 줄 · 그 워크플로우 절.
- ② 앱의 목록 — 문서 하나로 선다(taskIsSingle 참 · taskIsRelay · taskIsGather 거짓 · 문서 칸 둘(files) · 취합 칸(gather) 없음 · 처음 여는 보기 = 대시보드) · 붙박이 「사업계획서 양식 표준화」 는 taskIsSingle 이 아니다.
- ③ 첫 화면 — 그 워크플로우(헤딩 추출 · 사람 확인 · 표)로 문서 하나를 「워크플로우 시작」 → 문서 화면으로 넘어가지 않음 · 묶음이 모두 서버가 맡는 것 · 「사람 확인」 묶음의 「한 번에 진행」 → 「사람이 할 일 — …」 에서 멈춤.
  ③-2 첫 화면에서 진짜 줄(헤딩 · 템플릿 추출 — 분석 전인 작업)의 「한 번에 진행」 → 「끝남 — …」 · 첫 화면 그대로.
- ④ 문서 화면(③ 의 작업) — 패널 「대시보드」 가 서버 상태로 그려짐(묶음 g1 · g2 · g3 · 지난 실행의 끝 「멈춤 — 사람이 할 일 …」) · 사람이 하는 일 줄의 「했음」 → 끝남 · 이관 · 취합으로 읽히지 않음(taskSlots 없음 · gatherOn 거짓 · singleOn 참) ·
  에이전트의 상태(agwStatus)가 서버 상태에서(이관의 「준비 — 사업계획서 · 연차보고서 고르기」 가 아니다) · **3초 확인이 screen · dirty 를 싣고 나감**(고치던 글 보고).
- ⑤ 문서 화면에서 진짜 줄 실행(분석 전인 작업) — 대시보드 묶음의 「한 번에 진행」 = 서버 실행(시작 요청 from = g1 · 화면이 헤딩 추출을 직접 걸지 않음) · 도는 동안 거울(taskRun.single · 진행 줄 · 에이전트의 진행 카드 kind single) ·
  끝나면 끝 글 「끝남 — …」 · **문서 차례가 안 바뀐 변화도 다시 읽음**(문서 이름 줄의 분석 상태 헤딩 ✓ · 대시보드의 그 줄 끝남).
- ⑥ 울타리 — **다른 화면이 시작한** 문서를 바꾸는 실행(프로젝트 구성 반영): 이 화면이 거울로 따라가고 · 읽기 전용 띠 · 띠 동안 문서 입력이 막힘 · 「받았음」(ack) 보고 · 실행 직전에 친 글이 덮이지 않음 · 끝나면 문서를 다시 읽고 화면의 옛 계획을 버림.
- ⑦ 붙박이 「사업계획서 양식 표준화」 문서는 전처럼 화면 실행 — 서버 상태를 읽지 않고(…/flow · …/flow/live 요청 없음) 1단계 「한 번에 진행」 이 화면의 계획 → 반영(…/divisions/plan · apply)으로 돈다(서버 실행을 시작하지 않음).
- 콘솔 오류 없음."""
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
ap.add_argument("--port", type=int, default=18760)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
VALUES = {"stages": [2], "orgs": {"lead": "인텍", "joint": ["가나대", "다라연"], "nonprofit": [False, True, False]}}   # 구조 반영이 되는 값(tools/smoke_div_run_ui.py 와 같은 값)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1",
       "NFM_TASKS": str(tmp / "tasks.json"), "NFM_FORM_FILES": str(tmp / "form_files")}   # 이 검사가 조립한 것을 만든다 — 늘 임시
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_FLOW_EXEC"):   # NFM_FLOW_EXEC=client 면 서버 실행기가 꺼진다
    env.pop(k, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails, dialogs, bodies = [], [], [], []

# ---- 조립 폼의 선택자(코디네이터가 만드는 중 — 문서 하나의 틀은 줄 편집기가 **한 칸**: 꼴이 바뀌면 여기만 맞춘다)
S_OPEN = "#wfCompose [data-wf-compose=open]"                       # 「새 워크플로우 조립」
S_SHAPE = "#wfCompose .wf-io-opt[data-shape={shape}] input"        # 문서 입출력의 틀 고르기(single · relay · gather)
S_LINES = "#wfCompose .wf-lines"                                   # 줄 편집기 상자
S_GROUP = ".wf-lines-group"                                        # 묶음(li — data-group · 머리 .wf-lines-ghead input = 이름)
S_LINE = ".wf-line"                                                # 줄(li — data-unit · data-role=target)
S_ADD = "select.wf-lines-add[data-add=target]"                     # 「＋ 줄 넣기…」 고르기(문서 하나 = 하나)
S_STD, S_ERR, S_WARN = ".wf-lines-std", ".wf-lines-err li", ".wf-lines-warn li"   # 검사 결과(한 줄 요약 · 거절 · 경고)
S_SAVE = "#wfCompose form button[type=submit]"                     # 저장
S_NAME, S_DESC = "#wfCompose input[name=name]", "#wfCompose input[name=desc]"
S_MADE = '#wfCompose .wf-made-list li[data-task="{key}"]'          # 조립한 것의 목록 줄

# 줄 목록의 모습 — 묶음마다 [줄 key, 놓인 칸] · 검사 결과 · 저장 단추 · 두 칸짜리(원본 문서 칸)가 보이나
LINES = f"""() => {{ const box = document.querySelector('{S_LINES}'); if (!box) return null;
  const save = document.querySelector('{S_SAVE}');
  return {{ groups: [...box.querySelectorAll('{S_GROUP}')].map((g) => ({{ id: g.dataset.group, name: (g.querySelector('.wf-lines-ghead input') || {{}}).value || '',
      lines: [...g.querySelectorAll('{S_LINE}')].map((l) => [l.dataset.unit, l.dataset.role || '?']) }})),
    std: (box.querySelector('{S_STD}') || {{}}).textContent || '', errs: [...box.querySelectorAll('{S_ERR}')].map((x) => x.textContent), warns: [...box.querySelectorAll('{S_WARN}')].map((x) => x.textContent),
    save: save ? {{ off: save.disabled, text: save.textContent }} : null, add: !!box.querySelector('{S_ADD}'),
    srcAdd: !!box.querySelector('select.wf-lines-add[data-add=source]') }}; }}"""
SHAPES = """() => [...document.querySelectorAll('#wfCompose .wf-io-opt')].map((l) => [l.dataset.shape, l.querySelector('input').disabled, l.querySelector('input').checked, (l.querySelector('.wf-io-soon') || {}).textContent || ''])"""
# 패널 대시보드의 모습
DASH = """() => ({ groups: [...document.querySelectorAll('#paneDash .dash-group')].map((g) => ({ id: g.dataset.group, count: (g.querySelector('.dash-gcount') || {}).textContent || '',
    run: (() => { const b = g.querySelector('.dash-ghead [data-dash-focus^="run:"]'); return b ? { text: b.textContent, off: b.disabled, title: b.title } : null; })(),
    end: (g.querySelector('.dash-gend') || {}).textContent || '', nodes: [...g.querySelectorAll('.dash-node')].map((n) => [n.dataset.key, n.dataset.state, (n.querySelector('.dash-st') || {}).textContent || '']) })),
  notes: [...document.querySelectorAll('#paneDash .dash-note')].map((n) => [n.textContent, n.classList.contains('warn')]),
  last: (() => { const p = document.querySelector('#paneDash .dash-last[data-flow-last]'); return p ? [p.textContent, p.classList.contains('halt')] : ['', false]; })(),   // 서버 실행의 지난 끝(서버가 지은 글 · 주황 = 멈춤 · 남김)
  live: (document.querySelector('#paneDash .dash-live') || {}).textContent || '', count: (document.querySelector('#paneDash .dash-count') || {}).textContent || '',
  next: (document.querySelector('#paneDash .dash-next') || {}).textContent || '', top: [...document.querySelectorAll('#paneDash .dash-top button')].map((b) => [b.textContent, b.disabled]) })"""


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:1400] if detail != "" and not ok else ""), flush=True)
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


def settle(page):
    page.wait_for_function(f"() => {{ const b = document.querySelector('{S_LINES}'); return b && !/검사하는 중/.test(b.textContent) && !!b.querySelector('.wf-lines-check'); }}", timeout=30000)
    page.wait_for_timeout(350)   # 줄을 고친 뒤 검사를 거는 틈(250ms)
    page.wait_for_function(f"() => {{ const b = document.querySelector('{S_LINES}'); return b && !/검사하는 중/.test(b.textContent); }}", timeout=30000)
    return page.evaluate(LINES)


def units(s):
    return [[x[0] for x in g["lines"]] for g in s["groups"]]


def make(name, flow, target="plan"):
    """문서 하나로 조립한 정의를 API 로 만든다 → 키(조립 폼은 ① 이 본다 — 뒤 단계는 줄을 정해 둔 정의로)."""
    r = requests.post(f"{base}/api/tasks", json={"name": name, "shape": "single", "source": "", "target": target, "flow": flow}, timeout=30)
    if r.status_code != 201:
        raise SystemExit(f"정의를 만들지 못함({name}): {r.status_code} {r.text[:400]}")
    return r.json()["task"]["key"]


def work(key, project, *, values=False):
    """그 워크플로우의 작업을 API 로 만든다(기본 분석을 걸지 않는다 — 헤딩 · 표가 「남음」 으로 남는다) → 작업 id. values = 프로젝트 구성 값을 넣고 확정."""
    wid = requests.post(f"{base}/api/docs?new=1", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}, timeout=300).json()["docId"]
    requests.put(f"{base}/api/works/{wid}/task", json={"kind": "rnd", "file": "plan", "job": key, "project": project}, timeout=60).raise_for_status()
    if values:
        requests.put(f"{base}/api/docs/{wid}/divisions/settings", json={"values": VALUES}, timeout=120).raise_for_status()
        requests.post(f"{base}/api/docs/{wid}/divisions/confirm", json={}, timeout=120).raise_for_status()
    return wid


def flow_of(wid):
    return requests.get(f"{base}/api/works/{wid}/flow", timeout=120).json()


def open_doc(ctx, wid, tag):
    """문서 화면을 연다 → (쪽, 그 쪽의 요청 목록 — …/flow · …/flow/live · …/flow/runs · 헤딩 · 구조 반영 · LLM 검증·보완: [(method, url, 몸)])."""
    page, reqs = ctx.new_page(), []
    page.on("console", lambda m: errors.append(f"[{tag} {m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
    page.on("pageerror", lambda e: errors.append(f"[{tag} pageerror] {e}"))
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    page.on("request", lambda r: reqs.append((r.method, r.url, r.post_data)) if re.search(r"/flow(/|\?|$)|/headings$|/divisions/(plan|apply)$|/analysis/llm$", r.url) else None)
    page.goto(f"{base}/#w={wid}")
    page.wait_for_function("(id) => typeof state !== 'undefined' && state.id === id && document.querySelector('#doc .sheet .para') != null", arg=wid, timeout=300000)
    return page, reqs


def dash(page):
    """패널 「대시보드」 를 열고 묶음이 그려질 때까지."""
    if page.get_attribute("#panel", "data-tool") != "Dash":
        page.click("#tabDash")
    page.wait_for_selector("#paneDash .dash-group", timeout=60000)


def lives(reqs):
    return [u for m, u, _ in reqs if m == "GET" and "/flow/live" in u]


def full(count):
    """「끝난 수/세는 수」 글이 다 찼나(「2/2」 — 맨 앞 묶음은 준비 줄도 센다)."""
    a, _, b = count.partition("/")
    return bool(b) and a == b


def main():
    wait_server()
    api = requests.get(f"{base}/api/tasks?v=2", timeout=30).json()
    single = (api.get("byShape") or {}).get("single") or {}
    first = [[s["unit"] for s in g["steps"]] for g in single.get("flow") or []]
    shape = next((x for x in api.get("shapes") or [] if x.get("id") == "single"), {})
    check("전제 — 서버가 「1」 문서 하나를 연다(shapes 의 single.soon 이 빔 · byShape.single 의 고를 줄 · 처음 줄 목록)", shape.get("soon") == "" and bool(single.get("units")) and bool(first),
          [shape, list(single)])
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"[wf {m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[wf pageerror] {e}"))
        page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        page.on("request", lambda r: bodies.append((r.method, r.url, r.post_data)) if "/api/tasks" in r.url and r.method in ("POST", "PUT") and not r.url.endswith("/check") else None)
        page.goto(f"{base}/workflow#overview")
        page.wait_for_selector(S_OPEN)

        # ---- ① 조립 폼 — 「1」 문서 하나
        page.click(S_OPEN)
        settle(page)
        sh = {x[0]: x[1:] for x in page.evaluate(SHAPES)}
        check("① 문서 입출력 — 「1」 문서 하나가 켜져 있다(「준비 중」 없음) · 처음은 이관", sh.get("single") == [False, False, ""] and (sh.get("relay") or [None, False])[1] is True, sh)
        page.check(S_SHAPE.format(shape="single"))
        s = settle(page)
        roles = {x[1] for g in s["groups"] for x in g["lines"]}
        check("① 「1」 을 고름 → 줄 목록 = 그 틀의 처음 것(서버 byShape.single.flow) · 줄은 모두 한 칸(목적 문서) · 「＋ 줄 넣기…」 도 그 한 칸뿐(원본 문서 칸의 넣기 없음)",
              units(s) == first and roles == {"target"} and s["add"] and not s["srcAdd"], [units(s), first, sorted(roles), s["add"], s["srcAdd"]])
        check("① 서버 검사 — 거절 없음 · 「줄 목록으로 조립한 워크플로우」 · 저장 켜짐", not s["errs"] and s["std"].startswith("줄 목록으로 조립한") and not s["save"]["off"], [s["errs"], s["std"], s["warns"], s["save"]])
        page.screenshot(path=str(OUT / "01_single.png"), full_page=False)
        page.fill(S_NAME, "문서 하나 — 처음 줄 그대로")
        with page.expect_response(lambda r: r.url.endswith("/api/tasks") and r.request.method == "POST") as resp:
            page.click(S_SAVE)
        made = resp.value.json().get("task") or {}
        key1 = made.get("key", "")
        sent = json.loads(next(b for m, u, b in bodies if m == "POST" and u.endswith("/api/tasks")))
        check("① 저장 — 201 · 몸 = {shape: single, target: plan, flow(줄 목록) — 원본 없음 · assign 없음} · 서버의 정의 = v2 · shape single · 묶음 g1 …",
              resp.value.status == 201 and sent.get("shape") == "single" and not sent.get("source") and sent.get("target") == "plan" and "assign" not in sent
              and [[x["unit"] for x in g["steps"]] for g in sent["flow"]] == first and made.get("v") == 2 and made.get("shape") == "single" and (made.get("groups") or [""])[0] == "g1" and made.get("source") == "",
              [resp.value.status, sent, {k: made.get(k) for k in ("v", "shape", "groups", "source", "target")}])
        page.wait_for_function(f"() => location.hash === '#{key1}' && !!document.querySelector('{S_MADE.format(key=key1)}')", timeout=30000)
        row = page.evaluate(f"""() => {{ const li = document.querySelector('{S_MADE.format(key=key1)}'), sec = document.getElementById('{key1}');
          return {{ text: li.textContent, sec: sec ? sec.textContent.slice(0, 3000) : '', nav: !!document.querySelector('#wfNav a[href="#{key1}"]') }}; }}""")
        check("① 목록 줄 · 목차 · 그 워크플로우의 절(이름 · 줄 이름)", "문서 하나 — 처음 줄 그대로" in row["text"] and row["nav"] and "문서 하나 — 처음 줄 그대로" in row["sec"], row)
        page.screenshot(path=str(OUT / "02_saved.png"), full_page=False)

        # ---- 뒤 단계의 정의(API) — LLM 이 꺼져 있어 스크립트 줄 · 사람이 하는 일로
        hand = {"unit": "hand", "on": [], "name": "결과 확인", "note": "헤딩 판정을 본다"}
        key2 = make("헤딩 · 사람 확인 · 표", [{"name": "헤딩 추출", "steps": [{"unit": "heads", "on": []}]}, {"name": "사람 확인", "steps": [hand]}, {"name": "표", "steps": [{"unit": "tables", "on": []}]}])
        key3 = make("헤딩 · 표만", [{"name": "헤딩 추출", "steps": [{"unit": "heads", "on": []}]}, {"name": "표", "steps": [{"unit": "tables", "on": []}]}])
        key4 = make("구성 반영만", [{"name": "프로젝트 구성", "steps": [{"unit": "values", "on": []}, {"unit": "apply", "on": []}]}])

        # ---- ② 앱의 목록 — 문서 하나로 선다(이관 · 취합이 아니다)
        home = ctx.new_page()
        home.set_viewport_size({"width": 1600, "height": 1000})
        home.on("console", lambda m: errors.append(f"[home {m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        home.on("pageerror", lambda e: errors.append(f"[home pageerror] {e}"))
        home.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        home.goto(base)
        home.wait_for_selector("#homeDash[data-state=pick] select")
        cat = home.evaluate(f"""() => {{ const c = TASK_CATALOG['{key2}'] || {{}};
          return {{ name: c.name, single: c.single, custom: c.custom, v2: c.v2, file: c.file, target: c.target, files: c.files === undefined, gather: c.gather === undefined, entry: taskEntryOf('{key2}'),
            is: [taskIsSingle('{key2}'), taskIsRelay('{key2}'), taskIsGather('{key2}')], built: [taskIsSingle('plan_fit'), taskIsSingle('report_fit'), taskIsRelay('plan_to_report'), taskIsGather('plan_merge')] }}; }}""")
        check("② 앱의 목록 — 문서 하나(single · 줄 목록 정의 · 문서 종류 사업계획서) · taskIsSingle 참 · taskIsRelay · taskIsGather 거짓 · 문서 칸 둘 · 취합 칸 없음 · 처음 여는 보기 = 대시보드 · 붙박이는 그대로",
              cat["name"] == "헤딩 · 사람 확인 · 표" and cat["single"] and cat["custom"] and cat["v2"] and cat["file"] == "plan" and cat["target"] == "plan" and cat["files"] and cat["gather"] and cat["entry"] == "Dash"
              and cat["is"] == [True, False, False] and cat["built"] == [False, False, True, True], cat)

        # ---- ③ 첫 화면 — 「워크플로우 시작」(문서 화면으로 넘어가지 않음) → 서버가 맡은 묶음의 「한 번에 진행」
        with home.expect_file_chooser() as fc:
            home.locator("#pickBtn").click()
        fc.value.set_files([str(PLAN)])
        home.wait_for_function("() => document.querySelectorAll('#homeFiles .hf-row').length >= 1")
        home.locator("#homeFiles .hf-row").first.locator("input[type=radio]").check()   # 목적 문서 = 그 문서 하나
        home.locator("#homeFiles [data-hf-focus=project]").fill("문서 하나 시험")
        home.select_option("#homeDash select", key2)
        home.wait_for_selector("#homeDash[data-state=ready] .dash-group", timeout=30000)
        home.locator('#homeDash [data-hd-focus="start"]').click()
        home.wait_for_selector("#homeDash[data-state=live] .dash-group", timeout=240000)
        btn = lambda gid: f'#homeDash .dash-group[data-group="{gid}"] .dash-ghead button'  # noqa: E731
        on = lambda gid: f"() => {{ const b = document.querySelector('{btn(gid)}'); return !!b && !b.disabled; }}"  # noqa: E731
        home.wait_for_function(on("g2"), timeout=240000)   # 2단계(사람 확인)는 앞 묶음에 기대지 않는다(문서 하나 — 앞 묶음이 주는 것을 요구할 때만 「먼저」) · 1단계(헤딩 추출)는 올린 직후의 기본 분석이 끝낸다
        st3 = home.evaluate("() => ({ wid: HD.wid, home: document.body.classList.contains('no-doc'), id: state.id || '', groups: [...document.querySelectorAll('#homeDash .dash-group')].map((g) => [g.dataset.group, g.dataset.served]) })")
        wid2 = st3["wid"]
        check("③ 「워크플로우 시작」 — 문서 화면으로 넘어가지 않음 · 묶음 g1 · g2 · g3 을 모두 서버가 맡는다(「문서 화면에서 진행합니다」 가 아님)",
              st3["home"] and not st3["id"] and st3["groups"] == [["g1", "1"], ["g2", "1"], ["g3", "1"]], st3)
        t2 = (requests.get(f"{base}/api/works", timeout=60).json() or [])
        t2 = next((w.get("task") or {} for w in t2 if w.get("id") == wid2), {})
        check("③ 그 작업 — 워크플로우 = 조립한 것 · 문서 종류 = 사업계획서(목적 문서) · 프로젝트", t2.get("job") == key2 and t2.get("file") == "plan" and t2.get("project") == "문서 하나 시험", t2)
        home.locator(btn("g2")).click()
        home.wait_for_function("() => /사람이 할 일/.test((document.querySelector('#homeDash .dash-last') || {}).textContent || '')", timeout=120000)
        halt = home.evaluate("() => ({ last: document.querySelector('#homeDash .dash-last').textContent, halt: !!document.querySelector('#homeDash .dash-last.halt'), home: document.body.classList.contains('no-doc') })")
        check("③ 「사람 확인」 묶음의 「한 번에 진행」(서버 실행) → 「사람이 할 일 — 결과 확인 …」 에서 멈춤(주황) · 첫 화면 그대로", "사람이 할 일 — 결과 확인" in halt["last"] and halt["halt"] and halt["home"], halt)
        home.screenshot(path=str(OUT / "03_home_halt.png"), full_page=False)
        # ③-2 진짜 줄 — 분석 전인 작업(API 로 만든 것)을 이 브라우저의 기억으로 첫 화면 대시보드에 띄워 「한 번에 진행」
        wid3a = work(key3, "문서 하나 줄 실행")
        home.evaluate(f"() => localStorage.setItem('nfm.homeDash', JSON.stringify({{ job: '{key3}', wid: '{wid3a}' }}))")
        home.reload()
        home.wait_for_selector("#homeDash[data-state=live] .dash-group", timeout=120000)
        home.wait_for_function(on("g1"), timeout=120000)
        home.locator(btn("g1")).click()
        home.wait_for_function("() => !document.querySelector('#homeDash .dash-live') && /^(끝남|남김|멈춤)/.test((document.querySelector('#homeDash .dash-last') || {}).textContent || '')", timeout=600000)
        home.wait_for_function("() => { const c = (document.querySelector('#homeDash .dash-group[data-group=\"g1\"] .dash-gcount') || {}).textContent || ''; const [a, b] = c.split('/'); return !!b && a === b; }", timeout=60000)
        fin = home.evaluate("() => ({ last: document.querySelector('#homeDash .dash-last').textContent, g1: document.querySelector('#homeDash .dash-group[data-group=\"g1\"] .dash-gcount').textContent, home: document.body.classList.contains('no-doc') })")
        rec3 = (requests.get(f"{base}/api/works/{wid3a}/flow/runs", timeout=60).json().get("runs") or [{}])[0]
        check("③-2 첫 화면에서 「헤딩 추출」 묶음의 「한 번에 진행」 → 서버 실행 「끝남 — …」 · 그 묶음이 다 끝남 · 첫 화면 그대로 · 실행 기록(g1 부터 · 그 워크플로우)",
              fin["last"].startswith("끝남") and full(fin["g1"]) and fin["home"] and (rec3.get("range") or {}).get("from") == "g1" and rec3.get("job") == key3, [fin, {k: rec3.get(k) for k in ("job", "range", "status")}])
        home.close()

        # ---- ④ 문서 화면(③ 의 작업 — 사람이 할 일에서 멈춘 채) — 서버 상태로 그린 대시보드 · 「했음」 · 틀 · 에이전트 · 3초 확인
        app, reqs = open_doc(ctx, wid2, "doc2")
        frame = app.evaluate("() => ({ single: singleOn(), slots: taskSlots(), gather: gatherOn(), guided: agwGuided(), job: state.task.job, role: taskDocRole(state.task) })")
        check("④ 문서 화면 — 조립한 문서 하나(singleOn 참) · 이관 · 취합으로 읽히지 않음(문서 칸 둘 없음 · gatherOn 거짓) · 진행 에이전트가 맡음 · 그 문서 = 목적 문서",
              frame["single"] and frame["slots"] is None and frame["gather"] is False and frame["guided"] and frame["job"] == key2 and frame["role"] == "target", frame)
        dash(app)
        app.wait_for_function("() => !!document.querySelector('#paneDash [data-dash-focus=\"hand:hand1\"]')", timeout=60000)
        app.wait_for_function("() => (document.querySelector('#paneDash .dash-node[data-key=heads]') || { dataset: {} }).dataset.state === 'done'", timeout=240000)   # 올린 직후의 기본 분석이 끝난 뒤(서버 상태를 다시 읽어 따라온다)
        d = app.evaluate(DASH)
        g = {x["id"]: x for x in d["groups"]}
        check("④ 패널 대시보드 — 서버 상태로 그려짐: 묶음 g1 · g2 · g3 · 헤딩 추출 ✓ 끝남 · 사람이 하는 일 = 지금 · 지난 실행의 끝 「멈춤 — 사람이 할 일 …」(주황 줄) · 묶음마다 「한 번에 진행」",
              list(g) == ["g1", "g2", "g3"] and g["g1"]["nodes"][-1][:2] == ["heads", "done"] and g["g2"]["nodes"][0][0] == "hand1" and g["g2"]["nodes"][0][1] == "now"
              and "사람이 할 일" in d["last"][0] and d["last"][1] and all(x["run"] and x["run"]["text"] == "한 번에 진행" for x in d["groups"]), d)
        st_flow = [u for m, u, _ in reqs if m == "GET" and re.search(r"/flow$", u)]
        check("④ 그 상태는 서버에서 읽은 것(GET …/flow)", len(st_flow) >= 1, reqs[:6])
        app.locator("#paneDash").screenshot(path=str(OUT / "04_dash_hand.png"))
        app.click('#paneDash [data-dash-focus="hand:hand1"]')
        app.wait_for_function("() => (document.querySelector('#paneDash [data-dash-focus=\"hand:hand1\"]') || {}).textContent === '했음 취소'", timeout=30000)
        app.wait_for_function("() => /모두 끝남/.test((document.querySelector('#paneDash .dash-next') || {}).textContent || '')", timeout=60000)
        app.wait_for_function("() => { const b = [...document.querySelectorAll('#paneDash .dash-ghead [data-dash-focus^=\"run:\"]')]; return b.length === 3 && b.every((x) => x.disabled); }", timeout=60000)   # 「했음」 → 서버 상태를 다시 읽어 묶음이 끝난다
        d = app.evaluate(DASH)
        check("④ 「했음」 → 그 줄 끝남 · 모든 묶음 끝남(「모두 끝남」) · 「한 번에 진행」 은 「남은 단계가 없습니다」 로 꺼짐",
              all(full(x["count"]) for x in d["groups"]) and all(x["run"]["off"] and "남은 단계가 없습니다" in x["run"]["title"] for x in d["groups"]), d)
        ag = app.evaluate("async () => { const s = await agwStatus(); return { keys: s.steps.map((x) => [x.key, x.state]), acts: s.actions.map((a) => a.name), why: s.facts.why || '' }; }")
        keys = [k for k, _ in ag["keys"]]
        check("④ 에이전트의 상태(agwStatus) — 서버 상태에서: 그 정의의 줄(heads · hand1 · tables)이 차례대로 · 모두 끝남 · 이관의 「준비 — 문서 고르기」(files)가 아니다 · 남은 실행 행동 없음",
              [k for k in keys if k in ("heads", "hand1", "tables")] == ["heads", "hand1", "tables"] and "files" not in keys and all(s == "done" for _, s in ag["keys"])
              and not any(a.startswith("run:") for a in ag["acts"]) and "두 칸" not in ag["why"], ag)
        app.wait_for_timeout(7000)   # 3초 확인 두 번
        lv = lives(reqs)
        check("④ 3초 확인(…/flow/live)이 이 화면의 id 와 고치던 글 수를 싣고 나감(screen= · dirty= — 울타리가 이 화면을 기다린다)", len(lv) >= 2 and all("screen=" in u and "dirty=" in u for u in lv), lv[:4])
        app.close()

        # ---- ⑤ 문서 화면에서 진짜 줄 실행 — 거울 · 끝 글 · 문서 차례가 안 바뀐 변화도 다시 읽기
        wid3b = work(key3, "문서 하나 줄 실행 2")
        app, reqs = open_doc(ctx, wid3b, "doc3")
        dash(app)
        app.wait_for_function("() => { const b = document.querySelector('#paneDash .dash-group[data-group=\"g1\"] .dash-ghead [data-dash-focus=\"run:g1\"]'); return !!b && !b.disabled; }", timeout=120000)
        pre = app.evaluate("() => ({ rev: state.serverRev, heads: ((dsState.main || {}).items || []).filter((i) => i.key === 'heads').map((i) => i.state), nodes: [...document.querySelectorAll('#paneDash .dash-node')].map((n) => [n.dataset.key, n.dataset.state]) })")
        one = app.evaluate("() => { const b = document.querySelector('#paneDash .dash-node[data-key=heads] .dash-detail [data-dash-focus$=\":only\"]'); return b ? { text: b.textContent, off: b.disabled } : null; }")
        check("⑤ 분석 전 — 헤딩 줄이 「지금」 · 펴진 카드에 「이 단계만 진행」(서버에 그 줄 하나)", ["heads", "now"] in pre["nodes"] and one == {"text": "이 단계만 진행", "off": False}, [pre, one])
        app.click('#paneDash .dash-group[data-group="g1"] .dash-ghead [data-dash-focus="run:g1"]')
        app.wait_for_function("() => !!taskRun && taskRun.single && taskRun.server", timeout=30000)
        mid = app.evaluate("() => { const R = agwRunning(); return { kind: R && R.kind, label: R && R.label, live: !!document.querySelector('#paneDash .dash-live'), locked: divRunLocked(), stage: taskRun && taskRun.stage }; }")
        try:   # 진행 줄의 「멈춤」 — 다음 그리기(1초 안)에 붙는다(실행이 그 전에 끝나면 볼 수 없다)
            app.wait_for_selector("#paneDash .dash-live [data-dash-focus=stop]", timeout=8000)
            mid["stop"] = True
        except Exception:   # noqa: BLE001
            mid["stop"] = app.evaluate("() => !taskRun")   # 이미 끝났으면 볼 것이 없다
        check("⑤ 도는 동안 — 거울(taskRun.single · 묶음 g1) · 에이전트의 진행 카드가 같은 실행(kind single · 「1단계 헤딩 추출 — 한 번에 진행」) · 대시보드의 진행 줄 + 「멈춤」 · 다른 실행 단추는 꺼짐",
              mid["kind"] == "single" and mid["stage"] == "g1" and "헤딩 추출" in (mid["label"] or "") and "한 번에 진행" in (mid["label"] or "") and mid["live"] and mid["stop"] and mid["locked"], mid)
        app.wait_for_function("() => !taskRun && !!singleRunLast", timeout=600000)
        last = app.evaluate("() => singleRunLast")
        starts = [json.loads(b or "{}") for m, u, b in reqs if m == "POST" and u.endswith(f"/api/works/{wid3b}/flow/runs")]
        heads_posts = [u for m, u, _ in reqs if m == "POST" and u.endswith("/headings")]
        check("⑤ 「한 번에 진행」 = 서버 실행 — 시작 요청 하나(from g1 · where panel · 목적 문서 = 이 문서 · 정의의 지문) · 화면이 헤딩 추출을 직접 걸지 않음 · 끝 글 「끝남 — …」",
              len(starts) == 1 and starts[0].get("from") == "g1" and starts[0].get("where") == "panel" and (starts[0].get("docs") or {}).get("target") == wid3b and bool(starts[0].get("sig"))
              and not heads_posts and last["ok"] and last["text"].startswith("끝남"), [starts, heads_posts, last])
        app.wait_for_function("() => ((dsState.main || {}).items || []).some((i) => i.key === 'heads' && i.state === 'done')", timeout=60000)   # 문서 이름 줄의 분석 상태 — 문서 차례는 그대로인데 다시 읽는다
        app.wait_for_function("() => (document.querySelector('#paneDash .dash-node[data-key=heads]') || { dataset: {} }).dataset.state === 'done'", timeout=60000)
        app.wait_for_function("() => !DASH.busy && !document.querySelector('#paneDash .dash-live') && !!document.querySelector('#paneDash .dash-last[data-flow-last]')", timeout=60000)
        post = app.evaluate(f"() => ({{ rev: state.serverRev, d: ({DASH})(), busy: !!DASH.busy }})")
        check("⑤ 끝난 뒤 — 문서 차례는 그대로인데 문서 이름 줄의 분석 상태(헤딩 ✓) · 대시보드의 그 줄(끝남 · 그 묶음이 다 끝남) · 지난 실행의 끝 「끝남 — …」 이 따라옴 · 진행 줄 걷힘",
              post["rev"] == pre["rev"] and full(post["d"]["groups"][0]["count"]) and post["d"]["last"][0].startswith("끝남") and not post["d"]["last"][1] and not post["d"]["live"] and not post["busy"], [pre["rev"], post])
        app.locator("#paneDash").screenshot(path=str(OUT / "05_dash_done.png"))
        app.close()

        # ---- ⑥ 울타리 — 다른 화면이 시작한, 문서를 바꾸는 실행(프로젝트 구성 반영)
        wid4 = work(key4, "문서 하나 구성 반영", values=True)
        f4 = flow_of(wid4)
        g4 = (f4.get("stages") or [{}])[0]
        check("⑥ 전제 — 그 묶음을 서버가 맡고 「한 번에 진행」 을 할 수 있다(값 확정됨 · 구조 반영이 남음)", g4.get("server") and g4.get("can") and [x.get("key") for x in g4.get("steps") or []][-2:] == ["values", "apply"],
              {k: g4.get(k) for k in ("server", "can", "why", "left")} | {"steps": [(x.get("key"), x.get("st"), x.get("text")) for x in g4.get("steps") or []]})
        app, reqs = open_doc(ctx, wid4, "doc4")
        app.click("#toolTabTask")   # 「작업 개요」 — 화면의 계획(dv.plan)을 하나 세워 둔다(서버 실행이 제 계획으로 갈면 화면의 것은 버려져야 한다)
        app.wait_for_function("() => !!dv.view && !!dv.values", timeout=120000)
        app.evaluate("() => { divPlan(); }")   # 기다리지 않는다(계획 한 번에 10~20초) — 아래에서 끝남을 본다
        app.wait_for_function("() => !dv.busy && !!dv.plan", timeout=300000)
        plan0 = app.evaluate("() => dv.plan.planId")
        app.wait_for_timeout(3500)   # 3초 확인이 한 번은 나간 뒤(서버가 이 화면을 「기다릴 화면」 으로 안다)
        para = app.locator("#doc .para", has_text=re.compile(r"\S")).first
        pid = para.get_attribute("data-id")
        para.click()
        app.keyboard.press("End")
        app.keyboard.type("울타리")   # 실행 직전에 친 글 — 덮이면 안 된다
        rev0 = app.evaluate("() => state.serverRev")
        n0 = len(reqs)
        r = requests.post(f"{base}/api/works/{wid4}/flow/runs", json={"from": g4.get("id"), "where": "test", "screen": "other-screen", "docs": {"target": wid4}}, timeout=60)   # 다른 화면이 시작
        check("⑥ 다른 화면이 실행을 시작(202)", r.status_code == 202, r.text[:400])
        app.wait_for_selector("#flowFenceBand", timeout=120000)   # 실행이 이 문서를 바꾸려 한다 — 읽기 전용 띠
        mir = app.evaluate("() => ({ fenced: document.body.classList.contains('flow-fenced'), band: document.getElementById('flowFenceBand').textContent, mirror: !!taskRun && !!taskRun.single, by: taskRun ? taskRun.by : '', key: flowFence && flowFence.key })")
        text0 = app.evaluate("(id) => state.texts[id]", pid)
        app.keyboard.type("XYZ")   # 띠 동안의 입력은 막힌다
        app.wait_for_timeout(400)
        text1 = app.evaluate("(id) => document.querySelector(`#doc .para[data-id=\"${id}\"]`).textContent", pid)
        check("⑥ 읽기 전용 띠 — 「워크플로우가 이 문서를 바꿉니다 …」 · 이 화면이 그 실행을 거울로 따라감(다른 화면에서 진행 중) · 띠 동안 문서 입력이 막힘",
              mir["fenced"] and "워크플로우가 이 문서를 바꿉니다" in mir["band"] and mir["mirror"] and "XYZ" not in text1, [mir, text0, text1])
        app.screenshot(path=str(OUT / "06_fence.png"), full_page=False)
        app.wait_for_function("() => !taskRun && !document.getElementById('flowFenceBand') && !!singleRunLast", timeout=900000)
        app.wait_for_function("() => state.inflight === 0 && !dv.busy", timeout=120000)
        after = app.evaluate("(id) => ({ rev: state.serverRev, failed: state.failed.size, last: singleRunLast, plan: dv.plan, result: dv.result, applied: !!(dv.view && dv.view.applied), texts: Object.values(state.texts).filter((t) => (t || '').includes('울타리')).length, kept: (state.texts[id] || '').includes('울타리') })", pid)
        acks = [u for u in lives(reqs) if "ack=" in u]
        rec4 = (requests.get(f"{base}/api/works/{wid4}/flow/runs", timeout=60).json().get("runs") or [{}])[0]
        print("  ⑥ 실행의 끝:", after["last"], "기록:", {k: rec4.get(k) for k in ("status", "halt")}, flush=True)
        check("⑥ 「받았음」 — 알림의 key 를 되돌린 확인(ack=)이 나감 · 고친 글을 보낸 뒤라 반영 실패 문단 없음", len(acks) >= 1 and after["failed"] == 0, [acks[:2], after["failed"], len(reqs) - n0])
        check("⑥ 실행 직전에 친 글이 덮이지 않음(다시 읽은 문서에 그대로) · 문서 차례가 올라감 · 띠가 걷힘", after["texts"] >= 1 and after["rev"] > rev0, [after, rev0])
        check("⑥ 끝난 뒤 — 화면의 옛 계획 · 결과를 버림(dv.plan · dv.result 없음 — 서버가 제 계획으로 갈았다) · 끝 글이 남음", bool(plan0) and after["plan"] is None and after["result"] is None and bool((after["last"] or {}).get("text")), [plan0, after])
        app.close()

        # ---- ⑦ 붙박이 「사업계획서 양식 표준화」 — 전처럼 화면 실행(서버 실행을 시작하지 않는다)
        wid5 = work("plan_fit", "붙박이 그대로", values=True)
        app, reqs = open_doc(ctx, wid5, "doc5")
        dash(app)
        app.wait_for_function("() => { const b = document.querySelector('#paneDash .dash-group[data-group=\"config\"] .dash-ghead [data-dash-focus=\"run:config\"]'); return !!b && !b.disabled; }", timeout=180000)
        b5 = app.evaluate("() => ({ single: singleOn(), is: taskIsSingle(state.task.job), guided: agwGuided(), flow: DASH.flow || null })")
        app.wait_for_timeout(4000)   # 3초 확인이 돌 틈 — 붙박이 문서 하나는 확인하지 않는다(전과 같다)
        app.click('#paneDash .dash-group[data-group="config"] .dash-ghead [data-dash-focus="run:config"]')
        app.wait_for_function("() => !!dv.auto || !!dv.result || (dv.msg && dv.msg.kind !== 'note')", timeout=60000)
        app.wait_for_function("() => !dv.auto && !dv.busy && !state.busy", timeout=600000)
        r5 = {"flow": [u for m, u, _ in reqs if "/flow" in u], "plan": [u for m, u, _ in reqs if m == "POST" and u.endswith("/divisions/plan")],
              "mirror": app.evaluate("() => !!taskRun"), "msg": app.evaluate("() => (dv.msg || {}).text || ''"), "result": app.evaluate("() => !!dv.result")}
        check("⑦ 붙박이 「사업계획서 양식 표준화」 — 조립한 문서 하나가 아니다(singleOn 거짓) · 서버 상태 · 확인(…/flow · …/flow/live)을 읽지 않음 · 1단계 「한 번에 진행」 = 화면의 계획 → 반영(…/divisions/plan) · 서버 실행을 시작하지 않음",
              not b5["single"] and not b5["is"] and b5["guided"] and b5["flow"] is None and not r5["flow"] and len(r5["plan"]) >= 1 and not r5["mirror"], [b5, r5])
        app.close()

        real = [e for e in errors if "409" not in e and "400" not in e]
        check("콘솔 오류 없음", not real, real[:6])
        br.close()


try:
    main()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'OK' if not fails else 'FAIL'} — 실패 {len(fails)}" + (f": {json.dumps(fails, ensure_ascii=False)}" if fails else ""), flush=True)
sys.exit(1 if fails else 0)

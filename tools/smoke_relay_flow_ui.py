"""줄 목록(정의 v2)으로 조립한 **이관형** 워크플로우의 문서 화면 — 패널 「대시보드」 가 서버 상태로 그려지고 서버 쪽 실행기로 도는가(spec_워크플로우 ② §18-13 「줄 목록으로 조립한 이관형의 문서 화면」 ·
spec_작업에이전트 ② §9 — 2026-11-21 사용자(조립한 「연차보고서 배포(안) 작성」 의 대시보드에 상태 · 단추가 하나도 없는 것을 보며) "안에 기능이 하나도 없냐? 목적문서/원본문서 로 구분해서 워크플로우가 작성되어있고
각 단계별로 실행하고 하는 내용이 없어? … 각 도구마다 실행 및 결과내용을 보여주는게 있어야 하고 한번에 진행, 다 진행 이런게 있어야" · 같은 날 "사업계획서를 사용자가 올려야 하고,, 목적문서인 연차보고서를 올려야 하고 올리지 않으면 저장된 파일을 사용해야":
app/static/task_catalog.js(taskIsRelayFlow) · workflow_exec.js(relayFlowRun · relayFlowFollow) · dashboard.js(dashFlowLive — 문서 카드 · 준비 · 실행 단추) · doc_agent_work.js(서버 상태의 에이전트) · app/form_files_api.py(POST /api/workflow-start/target))
화면 확인 — 임시 서버(임시 조립 저장소 · 임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 흉내 없이 진짜 끝점으로(서버 쪽 실행기 포함 — ⑧ 의 「건너뛰기」 만 상태 응답의 한 줄을 고쳐 본다: LLM 이 꺼져 있어 그 단추가 서지 않는다).

    python -X utf8 tools/smoke_relay_flow_ui.py <그림·임시 폴더> [--port 18770]

보는 것:
- ① 목록 — 줄 목록으로 조립한 이관형으로 선다(taskIsRelayFlow 참 · taskIsRelay 참 · taskIsSingle 거짓 · 처음 여는 보기 = 대시보드) · 붙박이 「사업계획서 → 연차보고서 이관」 은 아니다.
- ② 원본 문서(사업계획서)만 있는 묶음 — 묶음 넷(g1 … g4)에 끝난 수(「0/4」 꼴 — 「N개 단계」 가 아니다) · 「준비」 카드 = 지금 · 문서 칸 둘(원본 = 지금 문서 · 목적 = 「없음 — 올려 주세요」) · 「연차보고서 올리기…」 ·
  저장한 양식을 걸지 않았으면 「저장한 양식으로」 없음 · 묶음의 「한 번에 진행」 은 꺼짐(까닭 = 서버의 「연차보고서 칸이 비었습니다 …」).
- ③ 워크플로우 설정에 저장한 양식(기본값)을 걸면 — 목적 칸 줄 「올리지 않으면 저장한 양식 「…」 을 씁니다」 · 「저장한 양식으로」 · 첫 묶음의 「한 번에 진행」 이 켜짐(풍선 = 먼저 채웁니다) · 뒤 묶음은 「1단계 … 이 먼저입니다」.
  「저장한 양식으로」 → POST /api/workflow-start/target {job, main = 원본 문서, target.form} → 준비 ✓ 끝남 · 같은 프로젝트에 목적 문서(양식으로 만든 작업)가 생김.
- ④ 문서 카드 — 두 문서에 하는 줄(헤딩 · 표 분석)은 카드 둘(「원본 문서」 · 「목적 문서」 꼬리표 · 둘째 카드는 번호 없이 붙음) · 목적 문서의 줄은 카드 하나 · 「원본 → 목적」 · 「워크플로우 전체」.
- ⑤ 줄의 「이 단계만 진행」(프로젝트 구성 추출) — 시작 요청 {from: g1, only: config, docs{target, source}} = 서버 실행 · 끝나면 그 줄 ✓ 끝남.
- ⑥ 묶음의 「한 번에 진행」(1단계) — 도는 동안 거울(taskRun.flow · 에이전트 진행 kind flow · 이름 「1단계 문서 검토 — 한 번에 진행」 · 진행 줄) · 끝 글 「끝남 — …」 · 묶음 4/4 · 헤딩 카드 둘 ✓ 끝남 · LLM 카드 「건너뜀」(LLM 끔).
- ⑥-1b 문서 카드의 「이 단계만 진행」 = 그 문서만(② §18-21) — 두 문서에 하는 줄은 안 끝난 문서 카드마다 단추 · 시작 요청 {from, only, role} · 그 문서 카드만 ✓ 끝남(다른 문서 카드는 그대로).
- ⑥-1c 문서마다 따로 도는 실행(② §18-22) — 구성 값이 확정되기 전에는 「프로젝트 구성 반영」 에서 시작하지 않는다(줄의 wait · 409 needs) · 원본 문서만 · 목적 문서만을 잇달아 시작하면 둘 다 받아 같이 돈다(그동안 묶음 전체는 409 busy + 까닭) ·
  끝 글 둘 · 원본 문서의 실행이 도는 동안 대시보드의 진행 줄(「… — 원본 문서만」) · 목적 문서의 단추는 켜진 채(상태 응답에 그 실행을 얹어 본다).
- ⑥-2 「넣을 구성 선택」(조립에 놓는 도구 — spec_병합 ② §4-1): 카드의 고르기 단추(대상 차년도 · 넣을 기관) → PUT …/flow/take · 상태 글 · 「전부 넣기」.
- ⑦ 「이어서 한 번에 2→4단계」(= 다 진행) — 시작 요청 {from: g2, to: g4} · 끝난 뒤 지난 실행의 끝 글 · 2단계 「프로젝트 구성 반영」 ✓ 끝남(목적 문서가 바뀜).
- ⑦-2 「캡션 맞추기」(조립 도구 — spec_워크플로우 ② §18-23): 끝난 줄의 목적 문서 카드에 맞출 꼴 칩 · 누르면 PUT …/flow/caption · 「가장 많은 꼴로」 로 풂.
- ⑧ 목적 문서 화면 — 카드의 「목적 문서 열기」 로 감 · 같은 대시보드(같은 끝난 수) · 그 문서에서 「연결 목록」 · 「목록 보기」 가 보임 · LLM 검증·보완의 「건너뛰기」 → PUT …/flow/skip → 「건너뛰기 취소」.
- ⑨ 에이전트 상태(agwStatus) — 서버 상태의 묶음 이름(「1단계 문서 검토」)으로(이관의 화면 셈이 아니다).
- ⑩ 붙박이 이관 문서는 그대로(문서 카드 꼬리표 없음 · relayFlowOn 거짓).
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
ap.add_argument("--port", type=int, default=18770)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
REPORT = ROOT / "samples" / "국가RnD_서식" / "KEIT_표준서식_260320" / "1. 산업기술혁신사업 연차보고서 서식_260319.hwpx"
VALUES = {"stages": [2], "orgs": {"lead": "인텍", "joint": ["가나대", "다라연"], "nonprofit": [False, True, False]}}   # 구조 반영이 되는 값(tools/smoke_div_run_ui.py 와 같은 값)
both = lambda u: {"unit": u, "on": ["source", "target"]}  # noqa: E731
FLOW = [   # 사용자가 조립한 「연차보고서 배포(안) 작성」 과 같은 줄 목록(2026-11-21 — 표준 차례가 아니다: 「프로젝트 구성 추출」 이 첫 묶음에 · 두 문서의 LLM 검증·보완)
    {"id": "g1", "name": "문서 검토", "steps": [{"unit": "config", "on": []}, both("heads"), both("headsLlm")]},
    {"id": "g2", "name": "구성 맞추기", "steps": [{"unit": "configLoad", "on": []}, {"unit": "take", "on": []},   # take = 조립에 놓는 도구 「넣을 구성 선택」(spec_병합 ② §4-1 — 구조 반영 · 자리 연결 앞)
                                          {"unit": "division", "on": ["target"]}, {"unit": "reheads", "on": ["target"]}, {"unit": "reheadsLlm", "on": ["target"]}]},
    {"id": "g3", "name": "본문 및 테이블 매칭", "steps": [both(u) for u in ("link", "llm", "plan", "gaps", "tableMap", "apply")]},
    {"id": "g4", "name": "문서 정리", "steps": [{"unit": "guide", "on": ["target"]}, {"unit": "capUnify", "on": ["target"]}]},   # capUnify = 조립 도구 「캡션 맞추기」(spec_워크플로우 ② §18-23)
]
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1",
       "NFM_TASKS": str(tmp / "tasks.json"), "NFM_FORM_FILES": str(tmp / "form_files"), "NFM_AGENT_NOTES": str(tmp / "agent_notes.json"), "NFM_TOOL_NAMES": str(tmp / "tool_names.json"),
       "NFM_REQS": str(tmp / "reqs.json")}   # 이 검사가 조립한 것 · 양식 설정을 만든다 — 늘 임시
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_FLOW_EXEC"):   # NFM_FLOW_EXEC=client 면 서버 실행기가 꺼진다
    env.pop(k, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails, reqs = [], [], []

# 패널 대시보드의 모습 — 묶음마다 끝난 수 · 「한 번에 진행」 · 카드(줄 key · 상태 · 상태 글 · 문서 꼬리표 · 같은 줄의 둘째 카드인가 · 번호)
DASH = """() => ({ groups: [...document.querySelectorAll('#paneDash .dash-group')].map((g) => ({ id: g.dataset.group, count: (g.querySelector('.dash-gcount') || {}).textContent || '',
    run: (() => { const b = g.querySelector('.dash-ghead [data-dash-focus^="run:"]'); return b ? { text: b.textContent, off: b.disabled, title: b.title } : null; })(),
    cards: [...g.querySelectorAll('.dash-node')].map((n) => ({ key: n.dataset.key, state: n.dataset.state, st: (n.querySelector('.dash-st') || {}).textContent || '', role: (n.querySelector('.hd-role') || { dataset: {} }).dataset.role || '',
      lead: (n.querySelector('.hd-role') || {}).textContent || '', same: n.classList.contains('same'), no: (n.querySelector('.dash-no') || {}).textContent || '' })) })),
  notes: [...document.querySelectorAll('#paneDash .dash-note')].map((n) => [n.textContent, n.classList.contains('warn')]),
  last: (() => { const p = document.querySelector('#paneDash .dash-last[data-flow-last]'); return p ? [p.textContent, p.classList.contains('halt')] : ['', false]; })(),
  live: (document.querySelector('#paneDash .dash-live') || {}).textContent || '', count: (document.querySelector('#paneDash .dash-count') || {}).textContent || '',
  next: (document.querySelector('#paneDash .dash-next') || {}).textContent || '', top: [...document.querySelectorAll('#paneDash .dash-top button')].map((b) => [b.textContent, b.disabled]),
  open: (() => { const n = document.querySelector('#paneDash .dash-node.open'); return n ? { key: n.dataset.key, text: [...n.querySelectorAll('.dash-detail .dash-text')].map((p) => p.textContent),
    acts: [...n.querySelectorAll('.dash-always button, .dash-detail .dash-acts button')].map((b) => [b.textContent, b.disabled, b.dataset.dashFocus || '']) } : null; })() })"""   # .dash-always = 접어도 보이는 줄(넣을 구성 선택의 대상 차년도)


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:1600] if detail != "" and not ok else ""), flush=True)
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


def up(path):
    return requests.post(f"{base}/api/docs?new=1", files={"file": (path.name, path.read_bytes(), "application/octet-stream")}, timeout=300).json()["docId"]


def flow(wid):
    return requests.get(f"{base}/api/works/{wid}/flow", timeout=120).json()


def open_dash(page, wid):
    page.goto(f"{base}/#w={wid}")
    page.wait_for_function("(id) => typeof state !== 'undefined' && state.id === id && !state.loading", arg=wid, timeout=120000)
    page.evaluate("() => showTab('Dash')")
    page.wait_for_function("() => !!(DASH.flow && DASH.flow.view) && !!document.querySelector('#paneDash .dash-group .dash-st')", timeout=120000)
    page.wait_for_timeout(600)


def to_dash(page, wid):   # 열려 있는 화면에서 다른 문서로(주소의 # 만 바꾸면 다시 읽지 않는다) → 그 문서의 대시보드가 서버 상태를 읽을 때까지
    page.evaluate("(id) => openWork(id)", wid)
    page.wait_for_function("(id) => state.id === id && !state.loading", arg=wid, timeout=120000)
    page.evaluate("() => showTab('Dash')")
    page.wait_for_function("() => DASH.flow && DASH.flow.id === state.id && !!DASH.flow.view && !!document.querySelector('#paneDash .dash-group .dash-st')", timeout=120000)
    page.wait_for_timeout(600)


def idle(page, timeout=600000):   # 이 보기가 부른 일 · 서버 실행의 거울이 내릴 때까지 → 대시보드가 끝난 상태를 다시 그릴 틈
    page.wait_for_function("() => !DASH.busy && !taskRun && !relayFlowStarting", timeout=timeout)
    page.wait_for_function("() => !(DASH.flow && (DASH.flow.loading || DASH.flow.stale))", timeout=60000)
    page.wait_for_timeout(700)


def card(d, gid, key, role=""):
    g = next((x for x in d["groups"] if x["id"] == gid), {"cards": []})
    return next((c for c in g["cards"] if c["key"] == key and (not role or c["role"] == role)), {})


def group(d, gid):
    return next((x for x in d["groups"] if x["id"] == gid), {})


def main():
    wait_server()
    r = requests.post(f"{base}/api/tasks", json={"name": "연차보고서 배포(안) 작성", "shape": "relay", "source": "plan", "target": "report", "flow": FLOW}, timeout=30)
    if r.status_code != 201:
        raise SystemExit(f"정의를 만들지 못함: {r.status_code} {r.text[:400]}")
    key = r.json()["task"]["key"]
    made = next(t for t in requests.get(f"{base}/api/tasks?v=2", timeout=30).json()["tasks"] if t["key"] == key)
    src = up(PLAN)
    requests.put(f"{base}/api/works/{src}/task", json={"kind": "rnd", "file": "plan", "job": key, "project": "배포 시험"}, timeout=60).raise_for_status()

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        page = br.new_page(viewport={"width": 1500, "height": 1300})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda q: reqs.append((q.method, q.url.replace(base, ""), q.post_data)) if q.method != "GET" else None)

        # ---- ① 목록
        open_dash(page, src)
        c1 = page.evaluate("""(k) => ({ flow: taskIsRelayFlow(k), relay: taskIsRelay(k), single: taskIsSingle(k), gather: taskIsGather(k), entry: taskEntryOf(k), v2: !!TASK_CATALOG[k].v2,
          builtin: taskIsRelayFlow('plan_to_report'), on: relayFlowOn() })""", key)
        check("① 목록 — 줄 목록으로 조립한 이관형(v2 · taskIsRelayFlow 참 · taskIsRelay 참 · 문서 하나 · 취합 아님 · 처음 여는 보기 = 대시보드) · 붙박이 이관은 아니다 · 이 문서에서 relayFlowOn",
              made.get("v") == 2 and c1 == {"flow": True, "relay": True, "single": False, "gather": False, "entry": "Dash", "v2": True, "builtin": False, "on": True}, [made.get("v"), c1])

        # ---- ② 원본 문서만 있는 묶음(저장한 양식을 걸지 않음)
        d2 = page.evaluate(DASH)
        files = card(d2, "g1", "files")
        page.evaluate("() => { DASH.open = 'files'; return dashDraw(true); }")   # 줄의 key 로 편다(첫 화면의 「문서 화면에서 열기」 와 같은 길) — 그 줄의 문서 카드가 펴진다
        o2 = page.evaluate(DASH)["open"] or {}
        runs2 = {g["id"]: g["run"] for g in d2["groups"]}
        check("② 원본 문서만 — 묶음 넷(g1 … g4)에 끝난 수(「0/4」 꼴 — 「N개 단계」 가 아니다) · 「준비」 = 지금 · 주황 알림(서버의 「연차보고서 칸이 비었습니다 …」)",
              [g["id"] for g in d2["groups"]] == ["g1", "g2", "g3", "g4"] and all(re.fullmatch(r"\d+/\d+", g["count"]) for g in d2["groups"]) and files.get("state") == "now" and files.get("st") == "지금"
              and any("연차보고서 칸이 비었습니다" in t and w for t, w in d2["notes"]), [[(g["id"], g["count"]) for g in d2["groups"]], files, d2["notes"]])
        check("② 「준비」 카드 — 문서 칸 둘(원본 문서 = 지금 문서 · 목적 문서 = 없음 — 올려 주세요) · 「연차보고서 올리기…」 · 「저장한 양식으로」 없음(건 양식이 없다) · 묶음의 「한 번에 진행」 은 꺼짐(까닭 = 문서 칸이 빔)",
              o2.get("key") == "files" and any("원본 문서 — 사업계획서" in t and "지금 문서" in t for t in o2.get("text", [])) and any("목적 문서 — 연차보고서" in t and "없음 — 올려 주세요" in t for t in o2.get("text", []))
              and [a[0] for a in o2.get("acts", [])] == ["연차보고서 올리기…", "「작업 개요」 의 칸 열기"] and all(b and b["off"] and "연차보고서 칸이 비었습니다" in b["title"] for b in runs2.values()), [o2, runs2])

        # ---- ③ 워크플로우 설정에 저장한 양식(기본값)을 건다 → 「저장한 양식으로」
        form = requests.post(f"{base}/api/form-files", files={"file": (REPORT.name, REPORT.read_bytes())}, data={"kind": "report"}, timeout=300).json()["file"]
        requests.put(f"{base}/api/workflow-slots/{key}", json={"target": {"file": form["id"], "mode": "default"}}, timeout=60).raise_for_status()
        page.evaluate("() => hfFormsLoad(true).then(() => { DASH.open = 'files'; return dashDraw(true); })")
        page.wait_for_function("() => !!document.querySelector('#paneDash [data-dash-focus=\"act:files:form:target\"]')", timeout=30000)
        d3 = page.evaluate(DASH)
        o3, runs3 = d3["open"] or {}, {g["id"]: g["run"] for g in d3["groups"]}
        check("③ 양식(기본값)을 걸면 — 목적 칸 줄 「올리지 않으면 저장한 양식 「…」 을 씁니다(양식: 기본값)」 · 단추 「연차보고서 올리기…」 · 「저장한 양식으로」 · 첫 묶음의 「한 번에 진행」 켜짐(풍선 = 먼저 채웁니다) · 뒤 묶음 「1단계 … 이 먼저입니다」",
              any("올리지 않으면 저장한 양식" in t and form["name"] in t and "기본값" in t for t in o3.get("text", [])) and [a[0] for a in o3.get("acts", [])][:2] == ["연차보고서 올리기…", "저장한 양식으로"]
              and not runs3["g1"]["off"] and "먼저 채웁니다" in runs3["g1"]["title"] and all(runs3[g]["off"] and "1단계 「문서 검토」 이 먼저입니다" in runs3[g]["title"] for g in ("g2", "g3", "g4")), [o3, runs3])
        reqs.clear()
        page.click('#paneDash [data-dash-focus="act:files:form:target"]')
        page.wait_for_function("() => !DASH.busy && DASH.flow && DASH.flow.view && DASH.flow.view.ready", timeout=180000)
        idle(page)
        sent = [json.loads(b) for m, u, b in reqs if m == "POST" and u == "/api/workflow-start/target"]
        V3 = flow(src)
        tgt = ((V3["docs"] or {}).get("target") or {}).get("id")
        tw = next((w for w in requests.get(f"{base}/api/works", timeout=60).json() if w["id"] == tgt), {})
        d3b = page.evaluate(DASH)
        check("③ 「저장한 양식으로」 — POST /api/workflow-start/target {job, main = 원본 문서, target.form} 한 번 · 준비 ✓ 끝남 · 같은 프로젝트에 목적 문서(양식으로 만든 작업 · 연차보고서)",
              len(sent) == 1 and sent[0]["job"] == key and sent[0]["main"] == src and sent[0]["target"]["form"] == form["id"] and V3["ready"] and tw.get("source") == "form"
              and (tw.get("task") or {}).get("file") == "report" and (tw.get("task") or {}).get("project") == "배포 시험" and card(d3b, "g1", "files").get("st") == "✓ 끝남", [sent, V3["ready"], tw.get("task"), card(d3b, "g1", "files")])

        # ---- ④ 문서 카드
        heads = [c for c in group(d3b, "g1").get("cards", []) if c["key"] == "heads"]
        check("④ 문서 카드 — 「헤딩 · 표 분석」 = 카드 둘(원본 문서 · 목적 문서 — 둘째는 번호 없이 붙음) · 「프로젝트 구성 반영」 = 목적 문서 카드 하나 · 「자리 연결」 = 원본 → 목적 · 「프로젝트 구성 추출」 = 워크플로우 전체",
              [(c["role"], c["lead"], c["same"], bool(c["no"])) for c in heads] == [("source", "원본 문서", False, True), ("target", "목적 문서", True, False)]
              and [(c["role"], c["lead"]) for c in group(d3b, "g2")["cards"] if c["key"] == "division"] == [("target", "목적 문서")]
              and card(d3b, "g3", "link").get("lead") == "원본 → 목적" and card(d3b, "g1", "config").get("lead") == "워크플로우 전체", [heads, group(d3b, "g2").get("cards"), card(d3b, "g3", "link")])

        # ---- ⑤ 줄 하나 — 「이 단계만 진행」(프로젝트 구성 추출)
        requests.put(f"{base}/api/docs/{src}/divisions/settings", json={"values": VALUES}, timeout=120).raise_for_status()   # 사업계획서의 값(빈 양식이라 읽을 값이 없다)
        page.evaluate("() => { dashFlowTouch(state.id); DASH.open = null; return dashDraw(true); }")
        idle(page)
        page.evaluate("() => { DASH.open = 'config'; return dashDraw(true); }")
        page.wait_for_selector('#paneDash [data-dash-focus="act:config@flow:only"]:not([disabled])', timeout=30000)
        reqs.clear()
        page.click('#paneDash [data-dash-focus="act:config@flow:only"]')
        page.wait_for_function("() => !!DASH.busy || !!taskRun", timeout=30000)
        idle(page)
        runs5 = [json.loads(b) for m, u, b in reqs if m == "POST" and u.endswith("/flow/runs")]
        d5 = page.evaluate(DASH)
        check("⑤ 「이 단계만 진행」(프로젝트 구성 추출) — 시작 요청 {from: g1, only: config, docs{target, source}} = 서버 실행 · 끝나면 그 줄 ✓ 끝남 · 지난 실행의 끝 글",
              len(runs5) == 1 and runs5[0].get("from") == "g1" and runs5[0].get("only") == "config" and runs5[0].get("docs") == {"target": tgt, "source": src} and runs5[0].get("where") == "panel"
              and card(d5, "g1", "config").get("st") == "✓ 끝남" and bool(d5["last"][0]), [runs5, card(d5, "g1", "config"), d5["last"]])

        # ---- ⑤-2 한 문서만 진행(spec_워크플로우 ② §18-21 — 2026-11-21 사용자 "목적문서 따로 원본 문서 작업 따로 할 수 있는 것들은 단계 에서 한 번에 진행할때 각각 따로 진행할 수 있도록 … 하나의 문서만 작업"):
        # 묶음 머리 아래 「한 문서만 [원본 문서만] [목적 문서만]」 — 서버가 센 solo 가 있는 묶음에만(1단계: 두 문서의 줄 + 전체 줄) · 누르면 {from, role} 로 그 문서의 줄만
        SOLO = """() => [...document.querySelectorAll('#paneDash .dash-group')].map((g) => ({ id: g.dataset.group, name: (g.querySelector('.dash-solo-name') || {}).textContent || '',
          btns: [...g.querySelectorAll('.dash-solo button')].map((b) => ({ text: b.textContent, off: b.disabled, focus: b.dataset.dashFocus || '', left: b.dataset.left || '', title: b.title })),
          under: (() => { const s = g.querySelector('.dash-solo'), h = g.querySelector('.dash-ghead'), f = g.querySelector('.dash-flow'); return s ? s.getBoundingClientRect().top >= h.getBoundingClientRect().bottom - 1 && s.getBoundingClientRect().bottom <= f.getBoundingClientRect().top + 1 : null; })(),
          over: g.scrollWidth > g.clientWidth + 1 }))"""
        s0, sv0 = page.evaluate(SOLO), {g["id"]: g for g in flow(tgt)["stages"]}
        by0 = {g["id"]: g for g in s0}
        check("⑤-2 「한 문서만」 줄 — 1단계 머리 아래(단계 카드 위)에 이름표 「한 문서만」 + 「원본 문서만」 · 「목적 문서만」 · 서버의 solo 와 같은 남은 수 · 문서 하나의 줄뿐인 묶음(2 · 4단계) · 원본 → 목적 줄뿐인 묶음(3단계)에는 없다 · 가로 넘침 없음",
              by0["g1"]["name"] == "한 문서만" and [b["text"] for b in by0["g1"]["btns"]] == ["원본 문서만", "목적 문서만"] and [b["focus"] for b in by0["g1"]["btns"]] == ["solo:g1:source", "solo:g1:target"]
              and [b["left"] for b in by0["g1"]["btns"]] == [str(x["left"]) for x in sv0["g1"]["solo"]] and by0["g1"]["under"] is True
              and all(not by0[g]["btns"] and by0[g]["under"] is None for g in ("g2", "g3", "g4")) and [sv0[g]["solo"] for g in ("g2", "g3", "g4")] == [[], [], []] and not any(g["over"] for g in s0), [s0, sv0["g1"]["solo"]])
        check("⑤-2 켜짐 · 꺼짐은 서버의 것 — 남은 단계가 있는 문서의 단추만 켜지고, 없는 문서의 단추는 꺼진 채 까닭 「남은 단계가 없습니다」",
              [b["off"] for b in by0["g1"]["btns"]] == [not x["can"] for x in sv0["g1"]["solo"]] and all(("남은 단계가 없습니다" in b["title"]) == (x["left"] == 0) for b, x in zip(by0["g1"]["btns"], sv0["g1"]["solo"])), [by0["g1"]["btns"], sv0["g1"]["solo"]])

        # ---- ⑥ 묶음 — 「한 번에 진행」(1단계)
        reqs.clear()
        page.click('#paneDash .dash-group[data-group="g1"] .dash-ghead [data-dash-focus="run:g1"]')
        page.wait_for_function("() => !!taskRun && !!taskRun.flow", timeout=60000)
        page.wait_for_function("() => !!document.querySelector('#paneDash .dash-live button')", timeout=15000)   # 진행 줄에 거울의 「멈춤」 이 붙을 때까지(그 앞 한 틈은 이 보기가 부른 일의 줄 — 단추 없음)
        mid = page.evaluate("() => { const R = agwRunning(); return { flow: !!(taskRun && taskRun.flow), kind: R && R.kind, label: R && R.label, live: !!document.querySelector('#paneDash .dash-live'), stop: !!document.querySelector('#paneDash .dash-live button') }; }")
        idle(page)
        runs6 = [json.loads(b) for m, u, b in reqs if m == "POST" and u.endswith("/flow/runs")]
        d6 = page.evaluate(DASH)
        h6, l6 = [c["st"] for c in group(d6, "g1")["cards"] if c["key"] == "heads"], [c["st"] for c in group(d6, "g1")["cards"] if c["key"] == "headsLlm"]
        check("⑥ 「한 번에 진행」(1단계) — 시작 요청 {from: g1}(only 없음) · 도는 동안 거울(taskRun.flow · 에이전트 진행 kind flow · 「1단계 문서 검토 — 한 번에 진행」 · 진행 줄 + 「멈춤」)",
              len(runs6) == 1 and runs6[0].get("from") == "g1" and "only" not in runs6[0] and "to" not in runs6[0]
              and mid == {"flow": True, "kind": "flow", "label": "1단계 문서 검토 — 한 번에 진행", "live": True, "stop": True}, [runs6, mid])
        check("⑥ 끝 — 끝 글 「끝남 — …」(초록) · 1단계 3/3 … 끝난 수가 참 · 헤딩 카드 둘 ✓ 끝남 · LLM 카드 둘 「건너뜀」(LLM 끔) · 다음 = 2단계의 첫 줄 · 「이어서 한 번에 2→4단계」",
              d6["last"][0].startswith("끝남 — ") and not d6["last"][1] and group(d6, "g1")["count"].split("/")[0] == group(d6, "g1")["count"].split("/")[1] and h6 == ["✓ 끝남", "✓ 끝남"] and l6 == ["건너뜀", "건너뜀"]
              and "프로젝트 구성 반영" in d6["next"] and d6["top"] == [["이어서 한 번에 2→4단계", False]], [d6["last"], group(d6, "g1")["count"], h6, l6, d6["next"], d6["top"]])
        page.locator("#paneDash").screenshot(path=str(OUT / "relay_flow_g1.png"))

        # ---- ⑥-1 「목적 문서만」 을 실제로 — 새 묶음(프로젝트 「배포 시험 2」 · 두 문서 모두 분석 전)에서: 목적 문서의 줄만 돌고 원본 문서는 그대로
        src2 = up(PLAN)
        requests.put(f"{base}/api/works/{src2}/task", json={"kind": "rnd", "file": "plan", "job": key, "project": "배포 시험 2"}, timeout=60).raise_for_status()
        t2 = requests.post(f"{base}/api/workflow-start/target", json={"job": key, "main": src2, "request": f"solo-{int(time.time())}", "target": {"form": form["id"]}}, timeout=300)
        tgt2 = t2.json()["docId"]   # 기본 분석을 걸지 않는다 — 두 문서 모두 「헤딩 · 표 분석」 이 남는다
        to_dash(page, tgt2)
        sv1 = {g["id"]: g for g in flow(tgt2)["stages"]}
        b1 = {g["id"]: g for g in page.evaluate(SOLO)}["g1"]["btns"]
        heads1 = {r: card(page.evaluate(DASH), "g1", "heads", r).get("st") for r in ("source", "target")}
        reqs.clear()
        page.click('#paneDash [data-dash-focus="solo:g1:target"]')
        page.wait_for_function("() => !!DASH.busy || !!taskRun", timeout=30000)
        idle(page)
        runs61 = [json.loads(b) for m, u, b in reqs if m == "POST" and u.endswith("/flow/runs")]
        d61, sv61 = page.evaluate(DASH), {g["id"]: g for g in flow(tgt2)["stages"]}
        last61 = requests.get(f"{base}/api/works/{tgt2}/flow/runs", timeout=60).json()["runs"][0]
        solo61 = {x["role"]: x for x in sv61["g1"]["solo"]}
        check("⑥-1 「목적 문서만」 — 처음 = 두 문서 모두 남음(단추 둘 켜짐) · 시작 요청 {from: g1, role: target}(only · to 없음) · 실행 기록의 범위에 role · 끝 글 「끝남 — 목적 문서(연차보고서)만 — …」 · 목적 문서의 헤딩 카드만 ✓ 끝남(원본 문서는 그대로 남음) · 남은 단계 = 목적 0 · 원본 그대로",
              [x["left"] for x in sv1["g1"]["solo"]] == [2, 2] and not any(b["off"] for b in b1) and heads1["source"] != "✓ 끝남" and heads1["target"] != "✓ 끝남"
              and len(runs61) == 1 and runs61[0].get("from") == "g1" and runs61[0].get("role") == "target" and "only" not in runs61[0] and "to" not in runs61[0] and (last61.get("range") or {}).get("role") == "target"
              and d61["last"][0].startswith("끝남 — 목적 문서(연차보고서)만 — 연차보고서의 헤딩 그래프·표 구조가 있습니다") and "사업계획서" not in d61["last"][0]
              and card(d61, "g1", "heads", "target").get("st") == "✓ 끝남" and card(d61, "g1", "heads", "source").get("st") == heads1["source"]
              and solo61["target"]["left"] == 0 and solo61["source"]["left"] == 2 and group(d61, "g1")["run"]["off"] is False, [sv1["g1"]["solo"], b1, heads1, runs61, last61.get("range"), d61["last"], sv61["g1"]["solo"]])
        b61 = {b["focus"]: b for b in {g["id"]: g for g in page.evaluate(SOLO)}["g1"]["btns"]}
        check("⑥-1 끝난 뒤 — 「목적 문서만」 은 꺼지고(남은 단계가 없습니다) 「원본 문서만」 은 켜진 채 · 묶음의 「한 번에 진행」 도 켜진 채(원본 문서의 줄 · 전체 줄이 남았다)",
              b61["solo:g1:target"]["off"] and "남은 단계가 없습니다" in b61["solo:g1:target"]["title"] and not b61["solo:g1:source"]["off"] and "원본 문서(사업계획서)의 남은 단계만" in b61["solo:g1:source"]["title"], b61)
        page.locator("#paneDash").screenshot(path=str(OUT / "relay_flow_solo.png"))

        # ---- ⑥-1b 문서 카드의 「이 단계만 진행」 = 그 문서만(② §18-21 — 2026-11-21 사용자 「1번 오케이. 진행해줘.」: 두 문서에 하는 줄은 안 끝난 문서 카드마다 단추 · 시작 요청 {from, only, role})
        # 새 묶음(프로젝트 「배포 시험 3」 · 두 문서 모두 분석 전)에서: 목적 문서 카드의 단추 → 목적 문서의 그 줄만 돌고 원본 문서 카드는 그대로 남는다
        src3 = up(PLAN)
        requests.put(f"{base}/api/works/{src3}/task", json={"kind": "rnd", "file": "plan", "job": key, "project": "배포 시험 3"}, timeout=60).raise_for_status()
        tgt3 = requests.post(f"{base}/api/workflow-start/target", json={"job": key, "main": src3, "request": f"card-{int(time.time())}", "target": {"form": form["id"]}}, timeout=300).json()["docId"]
        to_dash(page, tgt3)
        ONLY = """(ref) => { DASH.open = ref; return dashDraw(true).then(() => { const n = document.querySelector('#paneDash .dash-node.open'), b = document.querySelector(`#paneDash [data-dash-focus="act:${ref}:only"]`);
          return { open: n ? [n.dataset.key, (n.querySelector('.hd-role') || { dataset: {} }).dataset.role || ''] : null, btn: b ? { text: b.textContent, off: b.disabled, title: b.title } : null,
            only: n ? [...n.querySelectorAll('.dash-detail .dash-acts button')].map((x) => x.dataset.dashFocus || '').filter((f) => f.endsWith(':only')) : [] }; }); }"""
        heads3 = {r: card(page.evaluate(DASH), "g1", "heads", r).get("st") for r in ("source", "target")}
        k_s, k_t = page.evaluate(ONLY, "heads@source"), page.evaluate(ONLY, "heads@target")   # 목적 문서 카드를 편 채로 끝난다(아래에서 누른다)
        check("⑥-1b 문서 카드마다 「이 단계만 진행」 — 「헤딩 · 표 분석」 의 원본 문서 카드 · 목적 문서 카드에 하나씩(초점 이름 act:heads@<역할>:only) · 풍선 = 그 문서에만(「원본 문서(사업계획서)에만」 · 「목적 문서(연차보고서)에만」) · 「(두 문서 모두)」 가 아니다",
              k_s["open"] == ["heads", "source"] and k_s["only"] == ["act:heads@source:only"] and k_t["open"] == ["heads", "target"] and k_t["only"] == ["act:heads@target:only"]
              and all(k["btn"] and k["btn"]["text"] == "이 단계만 진행" and not k["btn"]["off"] and "두 문서 모두" not in k["btn"]["title"] for k in (k_s, k_t))
              and "원본 문서(사업계획서)에만" in k_s["btn"]["title"] and "목적 문서(연차보고서)에만" in k_t["btn"]["title"], [k_s, k_t])
        reqs.clear()
        page.click('#paneDash [data-dash-focus="act:heads@target:only"]')
        page.wait_for_function("() => !!DASH.busy || !!taskRun", timeout=30000)
        idle(page)
        runs63 = [json.loads(b) for m, u, b in reqs if m == "POST" and u.endswith("/flow/runs")]
        d63, last63 = page.evaluate(DASH), requests.get(f"{base}/api/works/{tgt3}/flow/runs", timeout=60).json()["runs"][0]
        a_s, a_t = page.evaluate(ONLY, "heads@source"), page.evaluate(ONLY, "heads@target")
        check("⑥-1b 목적 문서 카드의 단추 — 시작 요청 {from: g1, only: heads, role: target}(row · to 없음) · 실행 기록의 범위에 only + role · 끝 글 「끝남 — 목적 문서(연차보고서)만 — …」 · 목적 문서 카드만 ✓ 끝남(원본 문서 카드는 그대로 남음)",
              heads3["source"] != "✓ 끝남" and heads3["target"] != "✓ 끝남" and len(runs63) == 1 and runs63[0].get("from") == "g1" and runs63[0].get("only") == "heads" and runs63[0].get("role") == "target"
              and "row" not in runs63[0] and "to" not in runs63[0] and [(last63.get("range") or {}).get(k) for k in ("only", "role")] == ["heads", "target"]
              and d63["last"][0].startswith("끝남 — 목적 문서(연차보고서)만 — ") and "사업계획서" not in d63["last"][0]
              and card(d63, "g1", "heads", "target").get("st") == "✓ 끝남" and card(d63, "g1", "heads", "source").get("st") == heads3["source"], [heads3, runs63, last63.get("range"), d63["last"], group(d63, "g1").get("cards")])
        check("⑥-1b 끝난 뒤 — 끝난 목적 문서 카드에는 단추가 없고 원본 문서 카드의 단추는 켜진 채(그 문서의 몫이 남았다)",
              a_t["only"] == [] and a_t["btn"] is None and a_s["only"] == ["act:heads@source:only"] and a_s["btn"] and not a_s["btn"]["off"], [a_s, a_t])
        page.locator("#paneDash").screenshot(path=str(OUT / "relay_flow_card_only.png"))

        # ---- ⑥-1c 문서마다 따로 도는 실행(② §18-22 — 2026-11-21 사용자 "원본문서랑, 목적문서를 따로따로 실행해서 처리할 수 있잖아? 매칭은 1개 실행이 같이 해야하고 … 구성같은 경우 … 그 값이 추출돌때까지 실행이 되면 안되고")
        # 새 묶음(프로젝트 「배포 시험 4」 · 두 문서 모두 분석 전). (가) 진짜 서버로: 원본 문서만 · 목적 문서만을 잇달아 시작 → 둘 다 받고(같이 돈다 — 실행은 제 문서만 잡는다) · 그동안 두 문서를 함께 쓰는 묶음 전체는 거절(까닭 글)
        src4 = up(PLAN)
        requests.put(f"{base}/api/works/{src4}/task", json={"kind": "rnd", "file": "plan", "job": key, "project": "배포 시험 4"}, timeout=60).raise_for_status()
        tgt4 = requests.post(f"{base}/api/workflow-start/target", json={"job": key, "main": src4, "request": f"lane-{int(time.time())}", "target": {"form": form["id"]}}, timeout=300).json()["docId"]
        requests.put(f"{base}/api/docs/{src4}/divisions/settings", json={"values": VALUES}, timeout=120).raise_for_status()
        to_dash(page, tgt4)
        start = lambda body: requests.post(f"{base}/api/works/{tgt4}/flow/runs", json={"by": "human", "where": "panel", "screen": "gate", **body}, timeout=120)  # noqa: E731
        wait4 = {g["id"]: g for g in flow(tgt4)["stages"]}   # 구성 값이 확정되기 전 — 2단계(목적 문서의 줄뿐: 첫 줄 = 프로젝트 구성 반영)는 기다린다
        need4 = start({"from": "g2", "only": "division"})
        check("⑥-1c 구성 값 — 확정 전에는 그 값을 쓰는 단계에서 시작하지 않는다: 「프로젝트 구성 반영」 줄에 wait(「「프로젝트 구성 추출」 이 먼저입니다 …」) · 그 줄의 시작 요청은 409 needs(전에는 시작한 뒤 멈췄다) · 2단계 = 목적 문서만 잡는 묶음(lane target)",
              next(s for s in wait4["g2"]["steps"] if s["key"] == "division").get("wait", "").startswith("「프로젝트 구성 추출」 이 먼저입니다") and wait4["g2"]["lane"] == "target" and wait4["g1"]["lane"] == "" and wait4["g3"]["lane"] == ""
              and need4.status_code == 409 and need4.json().get("reason") == "needs" and "프로젝트 구성 추출" in need4.json().get("message", ""), [wait4["g2"].get("lane"), need4.status_code, need4.text[:300]])
        a4, b4 = start({"from": "g1", "role": "source"}), start({"from": "g1", "role": "target"})
        c4 = start({"from": "g1"})
        ra, rb = (a4.json().get("run") or {}), (b4.json().get("run") or {})
        check("⑥-1c 원본 문서만 · 목적 문서만을 잇달아 시작 — 둘 다 202(번호 따로 · lane source · target) · 그동안 묶음 전체(두 문서를 함께 쓴다)는 409 busy + 까닭 「… 실행이 도는 중입니다 — 이 단계는 두 문서를 함께 씁니다」",
              a4.status_code == 202 and b4.status_code == 202 and ra.get("lane") == "source" and rb.get("lane") == "target" and ra.get("n") != rb.get("n")
              and c4.status_code == 409 and c4.json().get("reason") == "busy" and "두 문서를 함께 씁니다" in c4.json().get("message", ""), [a4.status_code, a4.text[:200], b4.status_code, b4.text[:200], c4.status_code, c4.text[:300]])
        end4 = time.time() + 300
        while time.time() < end4 and flow(tgt4).get("runs"):
            time.sleep(0.5)
        v4 = flow(tgt4)
        rec4 = {r["n"]: r for r in requests.get(f"{base}/api/works/{tgt4}/flow/runs", timeout=60).json()["runs"]}
        r1, r2 = rec4.get(ra.get("n")) or {}, rec4.get(rb.get("n")) or {}
        page.evaluate("() => { dashFlowTouch(state.id); return dashFlowRead(); }")
        idle(page)
        lasts4 = page.evaluate("() => [...document.querySelectorAll('#paneDash .dash-last[data-flow-last]')].map((p) => p.textContent)")
        d64 = page.evaluate(DASH)
        check("⑥-1c 두 실행이 같이 돌았다 — 둘 다 끝남 · 도는 때가 겹침(뒤에 시작한 것이 앞의 것이 끝나기 전에 시작) · 끝 글 둘(「… 원본 문서(사업계획서)만 — …」 · 「… 목적 문서(연차보고서)만 — …」 — 대시보드에 한 줄씩) · 두 문서의 헤딩 카드 ✓ 끝남",
              r1.get("status") == "done" and r2.get("status") == "done" and (r2.get("started") or 0) < (r1.get("ended") or 0) and (r1.get("started") or 0) < (r2.get("ended") or 0)
              and sorted(x["n"] for x in v4.get("lasts") or []) == sorted([ra.get("n"), rb.get("n")]) and len(lasts4) == 2 and any("원본 문서(사업계획서)만" in t for t in lasts4) and any("목적 문서(연차보고서)만" in t for t in lasts4)
              and card(d64, "g1", "heads", "source").get("st") == "✓ 끝남" and card(d64, "g1", "heads", "target").get("st") == "✓ 끝남",
              [[r1.get("status"), r1.get("started"), r1.get("ended")], [r2.get("status"), r2.get("started"), r2.get("ended")], [x["n"] for x in v4.get("lasts") or []], lasts4, group(d64, "g1").get("cards")])

        # (나) 화면 — 원본 문서만 잡은 실행이 도는 상태(상태 응답에 그 실행 하나를 얹어 본다 — 분석은 몇 초라 진짜 실행으로는 그 틈을 못 잡는다): 진행 줄 하나(이름 「… — 원본 문서만」 + 「멈춤」) ·
        # 「목적 문서만」 · 목적 문서 카드의 「이 단계만 진행」 은 켜진 채 · 「원본 문서만」 · 원본 문서 카드의 단추 · 묶음 전체는 꺼짐(묶음의 까닭 = 「… 두 문서를 함께 씁니다」)
        def source_runs(route):
            res = route.fetch()
            body = res.json()
            run = {"n": 99, "status": "running", "stopping": False, "started": time.time() - 5, "ended": None, "lane": "source", "now": {"stage": "g1", "key": "headsLlm", "doc": src4, "note": "사업계획서 LLM 검증·보완 중"},
                   "range": {"from": "g1", "to": "g1", "only": "", "redo": "", "role": "source"}, "origin": {"by": "human", "screen": "other"}, "docs": body.get("docs"), "left": [], "halt": None, "end": None, "cut": None, "stages": []}
            body.update(runs=[run], run=run, held={"source": 99, "target": None}, last=None, lasts=[])
            for g in body.get("stages", []):
                if g["id"] != "g1":
                    continue
                g.update(can=False, why="원본 문서(사업계획서)의 실행이 끝나면 쓸 수 있습니다 — 이 묶음은 두 문서를 함께 씁니다", left=2)
                for s in g.get("steps") or []:
                    if s["key"] == "headsLlm":   # 두 문서 모두 남은 것으로(LLM 이 꺼져 있어 서버는 「건너뜀」 으로 센다)
                        s.update(done=False, st="run", skipped=False, per=[{"doc": src4, "role": "source", "st": "busy", "text": "사업계획서 — LLM 검증·보완 중…"}, {"doc": tgt4, "role": "target", "st": "todo", "text": ""}])
                g["solo"] = [{"role": "source", "title": "원본 문서", "name": "사업계획서", "total": 2, "left": 1, "paid": [], "change": False, "can": False, "why": "지금 진행 중인 작업이 끝나면 쓸 수 있습니다"},
                             {"role": "target", "title": "목적 문서", "name": "연차보고서", "total": 2, "left": 1, "paid": [], "change": False, "can": True, "why": ""}]
            route.fulfill(response=res, json=body)
        page.route(re.compile(r"/api/works/[0-9a-f]+/flow$"), source_runs)
        page.evaluate("() => { dashFlowTouch(state.id); DASH.open = 'headsLlm@target'; return dashFlowRead().then(() => dashDraw(true)); }")
        page.wait_for_selector('#paneDash .dash-live[data-run="99"]', timeout=30000)
        lane = page.evaluate("""() => { const q = (f) => document.querySelector(`#paneDash [data-dash-focus="${f}"]`), b = (x) => (x ? { off: x.disabled, title: x.title } : null);
          return { lives: [...document.querySelectorAll('#paneDash .dash-live')].map((x) => [x.dataset.lane || '', (x.querySelector('b') || {}).textContent || '', !!x.querySelector('button')]),
            next: (document.querySelector('#paneDash .dash-next') || {}).textContent || '', mirror: !!taskRun, source: b(q('solo:g1:source')), target: b(q('solo:g1:target')), run: b(q('run:g1')),
            card: b(q('act:headsLlm@target:only')), chain: [...document.querySelectorAll('#paneDash .dash-top button')].map((x) => x.disabled) }; }""")
        page.locator("#paneDash").screenshot(path=str(OUT / "relay_flow_lanes.png"))
        page.unroute(re.compile(r"/api/works/[0-9a-f]+/flow$"))
        check("⑥-1c 원본 문서의 실행이 도는 동안의 대시보드 — 진행 줄 하나(「1단계 문서 검토 — 원본 문서만」 + 「멈춤」) · 「목적 문서만」 과 목적 문서 카드의 「이 단계만 진행」 은 켜진 채 · 「원본 문서만」 · 묶음의 「한 번에 진행」 은 꺼짐(까닭 「… 두 문서를 함께 씁니다」)",
              lane["lives"] == [["source", "1단계 문서 검토 — 원본 문서만", True]] and "원본 문서만" in lane["next"] and lane["source"] and lane["source"]["off"] and lane["target"] and not lane["target"]["off"]
              and lane["card"] and not lane["card"]["off"] and lane["run"] and lane["run"]["off"] and "두 문서를 함께 씁니다" in lane["run"]["title"], lane)
        page.evaluate("() => { dashFlowTouch(state.id); DASH.open = null; return dashFlowRead().then(() => dashDraw(true)); }")
        idle(page)
        to_dash(page, src)   # 하던 묶음으로
        idle(page)

        # ---- ⑥-2 「넣을 구성 선택」(조립에 놓는 도구 — 사람이 고르는 줄): 대상 차년도 · 넣을 기관
        # 2026-11-23 사용자 "대상 차년도는 접지 않고 펼쳐서 사용자가 인식하고 클릭할 수 있게": 카드를 접어도 대상 차년도 칩은 보인다(.dash-always) · 넣을 기관은 펴야 보인다
        page.evaluate("() => { DASH.open = ''; return dashDraw(true); }")
        page.wait_for_selector('#paneDash .dash-node[data-key="take"]:not(.open) .dash-always [data-dash-focus="act:take:target:2"]', timeout=60000)
        shut = page.evaluate("""() => { const n = document.querySelector('#paneDash .dash-node[data-key="take"]'), vis = (e) => !!e && e.getClientRects().length > 0;
          return { open: n.classList.contains('open'), years: [...n.querySelectorAll('.dash-always [data-dash-focus^="act:take:target:"]')].filter(vis).map((b) => b.textContent),
                   orgs: n.querySelectorAll('[data-dash-focus^="act:take:org:"]').length }; }""")
        check("⑥-2 「넣을 구성 선택」 카드를 접어도 대상 차년도 칩(1 · 2차년도)이 보임 · 넣을 기관 칩은 편 카드에만", not shut["open"] and shut["years"] == ["1차년도", "2차년도"] and shut["orgs"] == 0, shut)
        page.evaluate("() => { DASH.open = 'take'; return dashDraw(true); }")
        page.wait_for_selector('#paneDash [data-dash-focus="act:take:target:2"]', timeout=60000)
        t0 = page.evaluate(DASH)["open"] or {}
        reqs.clear()
        page.click('#paneDash [data-dash-focus="act:take:target:2"]')
        page.wait_for_function("() => !DASH.busy && document.querySelector('#paneDash [data-dash-focus=\"act:take:target:2\"]')?.getAttribute('aria-pressed') === 'true'", timeout=60000)
        idle(page)
        page.click('#paneDash [data-dash-focus="act:take:org:가나대"]')
        page.wait_for_function("() => !DASH.busy && document.querySelector('#paneDash [data-dash-focus=\"act:take:org:가나대\"]')?.getAttribute('aria-pressed') === 'false'", timeout=60000)
        idle(page)
        page.evaluate("() => { DASH.open = 'take'; return dashDraw(true); }")
        page.wait_for_timeout(500)
        d62, puts = page.evaluate(DASH), [json.loads(b) for m, u, b in reqs if m == "PUT" and u.endswith("/flow/take")]
        o62, tv = d62["open"] or {}, requests.get(f"{base}/api/works/{tgt}/flow/take", timeout=60).json()
        check("⑥-2 「넣을 구성 선택」 카드 — 고르기 단추(대상 차년도 1 · 2차년도 · 넣을 기관 셋) · 처음 = 남음(「넣을 구성: 전부」) · 「이 단계만 진행」 은 없다(사람이 고르는 줄)",
              card(d6, "g2", "take").get("st") == "남음" and card(d6, "g2", "take").get("lead") == "워크플로우 전체" and any("넣을 구성: 전부" in t for t in t0.get("text", []))
              and [a[0] for a in t0.get("acts", []) if a[2].startswith("act:take:target:")] == ["1차년도", "2차년도"] and [a[0] for a in t0.get("acts", []) if a[2].startswith("act:take:org:")] == ["인텍", "가나대", "다라연"]
              and not any("이 단계만 진행" in a[0] for a in t0.get("acts", [])), [card(d6, "g2", "take"), t0])
        check("⑥-2 대상 차년도 「2차년도」 → PUT …/flow/take {year: 2}(목적 문서의 당해 차년도) · 기관 「가나대」 를 빼면 {take: {org: [인텍, 다라연]}} · 카드 = ✓ 끝남 · 글 「대상 차년도: 2차년도 · 넣을 구성: 기관: 인텍 · 다라연」 · 「전부 넣기」 가 생김",
              puts == [{"year": 2}, {"take": {"org": ["인텍", "다라연"]}}] and tv["year"] == 2 and tv["take"] == {"org": ["인텍", "다라연"]} and card(d62, "g2", "take").get("st") == "✓ 끝남"
              and any("대상 차년도: 2차년도" in t and "기관: 인텍 · 다라연" in t for t in o62.get("text", [])) and "전부 넣기" in [a[0] for a in o62.get("acts", [])], [puts, tv, o62])
        page.click('#paneDash [data-dash-focus="act:take:all"]')
        page.wait_for_function("() => !DASH.busy && !document.querySelector('#paneDash [data-dash-focus=\"act:take:all\"]')", timeout=60000)
        idle(page)
        tv2 = requests.get(f"{base}/api/works/{tgt}/flow/take", timeout=60).json()
        check("⑥-2 「전부 넣기」 → 넣을 구성을 풂(대상 차년도는 그대로 2)", tv2["take"] is None and tv2["year"] == 2 and tv2["text"] == "전부", tv2)
        page.evaluate("() => { DASH.open = null; return dashDraw(true); }")
        page.locator("#paneDash").screenshot(path=str(OUT / "relay_flow_take.png"))

        # ---- ⑦ 「이어서 한 번에 2→4단계」(= 다 진행)
        reqs.clear()
        page.click('#paneDash .dash-top [data-dash-focus="run:chain"]')
        page.wait_for_function("() => !!taskRun && !!taskRun.flow", timeout=60000)
        idle(page, 900000)
        runs7 = [json.loads(b) for m, u, b in reqs if m == "POST" and u.endswith("/flow/runs")]
        d7, V7 = page.evaluate(DASH), flow(src)
        st7 = {g["id"]: (g["done"], g["total"], g["left"]) for g in V7["stages"]}
        check("⑦ 「이어서 한 번에 2→4단계」 — 시작 요청 {from: g2, to: g4} · 끝난 뒤 지난 실행의 끝 글 · 2단계 「프로젝트 구성 반영」 ✓ 끝남(목적 문서가 바뀜) · 원본 문서 화면은 그대로(문서 id)",
              len(runs7) == 1 and runs7[0].get("from") == "g2" and runs7[0].get("to") == "g4" and bool(d7["last"][0]) and card(d7, "g2", "division").get("st") == "✓ 끝남"
              and page.evaluate("() => state.id") == src and (V7["last"] or {}).get("status") in ("done", "left", "halted"), [runs7, d7["last"], card(d7, "g2", "division"), st7, (V7["last"] or {}).get("status")])
        page.locator("#paneDash").screenshot(path=str(OUT / "relay_flow_chain.png"))

        # ---- ⑦-2 「캡션 맞추기」(조립 도구 — spec_워크플로우 ② §18-23 「캡션 맞추기」 · 하는 일 = spec_hwpx_웹편집 ② §8-10 「모든 캡션을 한 꼴로」): 맞출 꼴 칩 · PUT …/flow/caption · 「가장 많은 꼴로」
        CAP = '#paneDash [data-dash-focus="act:capUnify@target:cap:%s"]'
        cv = requests.get(f"{base}/api/works/{tgt}/flow/caption", params={"doc": tgt}, timeout=60).json()
        page.evaluate("() => { DASH.open = 'capUnify'; DASH.cap = null; return dashDraw(true); }")
        page.wait_for_selector(CAP % 0, timeout=60000)
        idle(page)
        d72 = page.evaluate(DASH)
        o72, c72 = d72["open"] or {}, card(d72, "g4", "capUnify")
        chips = [a for a in o72.get("acts", []) if re.fullmatch(r"act:capUnify@target:cap:\d+", a[2])]
        check("⑦-2 「캡션 맞추기」 — 「이어서 한 번에」 가 지나간 뒤 그 줄 끝남 · 목적 문서 카드에 맞출 꼴 칩(서버의 꼴 목록과 같은 수 · 「꼴 · 줄 수」 · 안 골랐으면 가장 많은 꼴이 눌림) · 「이 단계만 진행」 없음",
              c72.get("state") == "done" and cv["chosen"] is None and [a[0] for a in chips] == [f"{f['name']} · {f['count']}" for f in cv["forms"]]
              and page.get_attribute(CAP % 0, "aria-pressed") == "true" and not any("이 단계만 진행" in a[0] for a in o72.get("acts", [])), [c72, cv, o72])
        reqs.clear()
        page.click(CAP % 0)
        page.wait_for_function("(s) => !DASH.busy && !!document.querySelector(s)", arg=CAP % "auto", timeout=60000)
        puts72 = [json.loads(b) for m, u, b in reqs if m == "PUT" and "/flow/caption" in u]
        cv2 = requests.get(f"{base}/api/works/{tgt}/flow/caption", params={"doc": tgt}, timeout=60).json()
        check("⑦-2 칩을 누르면 PUT …/flow/caption {form: 그 꼴} · 묶음에 적힘(문서는 그대로) · 칩 눌림 · 「가장 많은 꼴로」 가 생김",
              puts72 == [{"form": cv["forms"][0]["key"]}] and cv2["chosen"] == cv["forms"][0]["key"] and cv2["rev"] == cv["rev"] and page.get_attribute(CAP % 0, "aria-pressed") == "true", [puts72, cv2])
        page.locator("#paneDash").screenshot(path=str(OUT / "relay_flow_caption.png"))
        page.click(CAP % "auto")
        page.wait_for_function("(s) => !DASH.busy && !document.querySelector(s)", arg=CAP % "auto", timeout=60000)
        cv3 = requests.get(f"{base}/api/works/{tgt}/flow/caption", params={"doc": tgt}, timeout=60).json()
        check("⑦-2 「가장 많은 꼴로」 → {form: null} · 고른 꼴을 풂", cv3["chosen"] is None and [json.loads(b) for m, u, b in reqs if m == "PUT" and "/flow/caption" in u][-1] == {"form": None}, cv3)

        # ---- ⑧ 목적 문서 화면 — 「목적 문서 열기」 · 같은 대시보드 · 보기 단추 · 「건너뛰기」
        page.evaluate("() => { DASH.open = 'division'; return dashDraw(true); }")
        page.wait_for_selector('#paneDash [data-dash-focus="act:division@target:open"]', timeout=30000)
        page.click('#paneDash [data-dash-focus="act:division@target:open"]')
        page.wait_for_function("(id) => state.id === id && !state.loading", arg=tgt, timeout=120000)
        page.wait_for_function("() => DASH.flow && DASH.flow.id === state.id && !!DASH.flow.view && !!document.querySelector('#paneDash .dash-group .dash-st')", timeout=120000)
        idle(page)
        d8 = page.evaluate(DASH)
        page.evaluate("() => taskFlowLoad()")
        page.wait_for_function("() => !taskFlow.linkBusy && !!taskFlow.links", timeout=180000)
        page.evaluate("() => { DASH.open = 'link'; return dashDraw(true); }")
        page.wait_for_timeout(600)
        o8 = page.evaluate(DASH)["open"] or {}
        check("⑧ 목적 문서 화면 — 「목적 문서 열기」 로 감 · 같은 대시보드(묶음마다 같은 끝난 수 · 대시보드 탭 그대로) · 「자리 연결」 카드에 「연결 목록」(그 문서에서) · 「목적 문서 열기」 는 없음",
              [g["count"] for g in d8["groups"]] == [g["count"] for g in d7["groups"]] and page.evaluate("() => !document.getElementById('paneDash').hidden")
              and "연결 목록" in [a[0] for a in o8.get("acts", [])] and not any("열기" in a[0] and "문서" in a[0] for a in o8.get("acts", [])), [[g["count"] for g in d8["groups"]], [g["count"] for g in d7["groups"]], o8])

        def one_todo(route):   # 상태 응답의 「LLM 검증·보완」 줄만 「남음」 으로(LLM 이 꺼져 있어 서버는 「건너뜀」 으로 센다 — 「건너뛰기」 단추의 자리만 본다 · 건너뛴 문서 목록 llmSkip 은 서버 것 그대로)
            res = route.fetch()
            body = res.json()
            for g in body.get("stages", []):
                for s in g.get("steps") or []:
                    if s["key"] == "headsLlm":
                        s.update(done=False, st="now", skipped=False)
                        for p in s.get("per") or []:
                            if p["doc"] not in body.get("llmSkip", []):
                                p.update(st="todo", skipped=False)
                g.update(left=max(g.get("left", 0), 1) if g["id"] == "g1" else g.get("left", 0))
            route.fulfill(response=res, json=body)
        page.route(re.compile(r"/api/works/[0-9a-f]+/flow$"), one_todo)
        reqs.clear()
        page.evaluate("() => { dashFlowTouch(state.id); DASH.open = 'headsLlm@source'; return dashDraw(true); }")
        page.wait_for_selector('#paneDash [data-dash-focus="act:headsLlm@source:skip"]', timeout=30000)
        page.click('#paneDash [data-dash-focus="act:headsLlm@source:skip"]')
        page.wait_for_selector('#paneDash [data-dash-focus="act:headsLlm@source:unskip"]', timeout=30000)
        skip_on = [json.loads(b) for m, u, b in reqs if m == "PUT" and u.endswith("/flow/skip")]
        s8 = flow(tgt).get("llmSkip")
        page.click('#paneDash [data-dash-focus="act:headsLlm@source:unskip"]')
        page.wait_for_selector('#paneDash [data-dash-focus="act:headsLlm@source:skip"]', timeout=30000)
        skip_all = [json.loads(b) for m, u, b in reqs if m == "PUT" and u.endswith("/flow/skip")]
        page.unroute(re.compile(r"/api/works/[0-9a-f]+/flow$"))
        check("⑧ LLM 검증·보완의 「건너뛰기」(원본 문서 카드) → PUT …/flow/skip {doc = 원본, on: true} · 서버의 건너뛴 문서 목록에 그 문서 · 단추가 「건너뛰기 취소」 로 → 누르면 {on: false}",
              skip_on == [{"doc": src, "on": True}] and s8 == [src] and skip_all == [{"doc": src, "on": True}, {"doc": src, "on": False}] and flow(tgt).get("llmSkip") == [], [skip_on, s8, skip_all])

        # ---- ⑨ 에이전트 상태
        st9 = page.evaluate("() => agwStatus().then((s) => ({ stages: [...new Set(s.steps.map((x) => x.stage))], keys: s.steps.map((x) => x.key).slice(0, 4), acts: s.actions.map((a) => a.name), why: s.facts.why || '' }))")
        check("⑨ 에이전트 상태 — 서버 상태의 묶음(「1단계 문서 검토」 … 「4단계 문서 정리」) · 줄(files · config · heads …) — 이관의 화면 셈(준비 — 사업계획서 · 연차보고서 고르기)이 아니다",
              st9["stages"] == ["1단계 문서 검토", "2단계 구성 맞추기", "3단계 본문 및 테이블 매칭", "4단계 문서 정리"] and st9["keys"] == ["files", "config", "heads", "headsLlm"], st9)

        # ---- ⑩ 붙박이 이관 문서는 그대로
        old = up(PLAN)
        requests.put(f"{base}/api/works/{old}/task", json={"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": "붙박이 이관"}, timeout=60).raise_for_status()
        page.evaluate("(id) => openWork(id)", old)
        page.wait_for_function("(id) => state.id === id && !state.loading", arg=old, timeout=120000)
        page.evaluate("() => showTab('Dash')")
        page.wait_for_function("() => !!document.querySelector('#paneDash .dash-group .dash-ghead [data-dash-focus^=\"run:\"]')", timeout=120000)
        b10 = page.evaluate("() => ({ on: relayFlowOn(), roles: document.querySelectorAll('#paneDash .hd-role').length, groups: [...document.querySelectorAll('#paneDash .dash-group')].map((g) => g.dataset.group), flow: !!(DASH.flow && DASH.flow.id === state.id) })")
        check("⑩ 붙박이 「사업계획서 → 연차보고서 이관」 문서는 그대로 — 줄 목록 가지가 아님(relayFlowOn 거짓 · 문서 카드 꼬리표 없음 · 서버 상태를 이 보기가 읽지 않음) · 묶음 = 표준 넷",
              b10 == {"on": False, "roles": 0, "groups": ["review", "frame", "map", "clean"], "flow": False}, b10)

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

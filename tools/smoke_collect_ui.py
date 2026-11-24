"""조립 틀 「N → 1 · 같은 양식」(같은 양식 취합 — shape `collect`: 기관이 같은 양식으로 따로 쓴 문서 여럿 → 사업계획서 하나의 자리에)의 화면(spec_취합 ② §10 — 2026-11-24 사용자
"1개 사업계획서 그리고 N개의 제출된 문서를 가지고 사업계획서에 넣고 … 수정된 문서가 오면 이전 제출된 내용과 비교해서 수정된 부분만 적용하는 워크플로우":
app/static/task_catalog.js(taskIsCollect) · workflow.js(조립 폼의 넷째 틀) · collect.js(「기관 문서」 목록) · dashboard.js(dashFlowLive — 기관 문서마다 카드 · 「준비」 · 「반영할 기관 지정」 카드의 목록) ·
home_dash.js · home_files.js(첫 화면 — 기관 문서 여럿으로 시작 · 목록 · 올리기) · workflow_exec.js(시작 요청의 docs · 거울))
화면 확인 — 임시 서버(임시 조립 저장소 · 임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 진짜 끝점으로(서버 쪽 실행기 포함) — ⑦ 의 수정 계획 항목만 그 응답을 흉내 낸다
(견본 문서가 빈 양식이라 진짜 수정 계획에는 바뀐 곳이 없다: 진짜 응답 「바뀐 곳 없음」 은 ⑦ 앞에서 따로 본다).

    python -X utf8 tools/smoke_collect_ui.py <그림·임시 폴더> [--port 18790]

보는 것:
- ① 조립 화면(/workflow) — 문서 입출력에 넷째 틀 「N → 1 · 같은 양식」(서버가 준 목록대로) · 고르면 문서 칸(원본 N · 목적 1) · 그 틀의 처음 줄 목록 · 원본 문서 칸의 줄 = 헤딩 · 표 분석 · 반영할 기관 지정뿐 ·
  전용 꼬리표 「전용」 · 「도구 설명」 열(반영할 기관 지정) · 서버 검사 거절 없음 → 저장(201 · shape collect · flow) → 목록 줄 → 「고치기」 로 다시 열면 같은 줄 목록.
- ② 목록(task_catalog.js) — taskIsCollect 참 · taskIsRelay · taskIsRelayFlow 참 · taskIsGather · taskIsSingle 거짓 · 처음 여는 보기 = 대시보드 · 편집 구역 기본 = 기관.
- ③ 첫 화면 — 목적 문서 하나 + 기관 문서 둘로 「워크플로우 시작」(문서 화면으로 안 넘어감 · 「하나만 둘 수 있습니다」 로 막지 않음) → 같은 묶음에 목적 문서 + 기관 문서 둘(task.file part) ·
  문서 칸 「원본 문서 — 기관 문서: 문서 2개」 · 「기관 문서」 목록 두 줄(미지정) + 「자동 지정」 + 「기관 문서 올리기…」.
- ④ 목록의 고르기(첫 화면) — 「자동 지정」 = POST …/auto 를 미지정 문서마다(꼬리표 「파일 이름으로」) · 반영할 기관 고르기 = PUT {orgs: [이름]} · 「공통 자리 포함」 = PUT {common} ·
  「기관 문서 올리기…」(파일 둘 한꺼번에) → 같은 묶음의 기관 문서로(있던 문서는 그대로) · 수정본 고르기 = PUT {revOf} → 꼬리표 「수정본」 · 앞 제출본 「수정본 있음」 · 「수정 계획 보기」 단추.
- ⑤ 첫 화면의 문서 카드 — 기관 문서마다 도는 줄(헤딩 · 표 분석)은 기관 문서마다 카드(꼬리표 = 「기관 이름 — 파일 이름」) + 목적 문서 카드 · 2단계의 「한 번에 진행」 = 서버 실행(시작 요청 docs.source = null) · 끝 글.
- ⑥ 문서 화면의 대시보드(패널) — 묶음 넷 · 기관 문서마다 카드 · 「준비」 카드에 문서 칸(기관 문서 N개 · 목적 문서) + 「기관 문서」 목록(반영할 기관 · 공통 자리 포함 · 수정본 고르기 · 상태 꼬리표) ·
  파일 이름 → 그 문서를 둘째 면에(같이 보기) · 「반영할 기관 지정」 카드에도 같은 목록 · 「한 문서만」 줄 없음(서버가 solo 를 안 낸다) · 「작업 개요」 의 기관 문서 줄(문서 N개 + 「기관 문서 목록」) · 에이전트 상태(서버 상태의 묶음).
- ⑦ 수정 계획 — 「수정 계획 보기」(진짜 끝점: 견본은 「바뀐 곳 없음」 · 「수정본 반영」 꺼짐) · 항목이 있는 계획(응답 흉내)은 그 줄 아래에 펴짐: 상태 꼬리표(고칠 곳 · 겹침 · 확인 필요 · 수정본에 없음) ·
  「지금 "…" → 수정본 "…"」 · 「수정본 반영」 → 한 줄 확인 → POST …/revise/apply {planId}(진짜 끝점 — 흉내 낸 계획이라 409: 그 글이 알림으로 · 계획을 걷음).
- ⑧ 패널에서 「이어서 한 번에 3→4단계」 = 서버 실행(시작 요청 {from, to, docs{target, source: null}}) + 거울 · 끝 글 · 3단계 「수정본 반영」 줄 끝남 · 도는 동안 목록의 고르기는 꺼짐.
- 콘솔 오류 없음.
견본 문서(저장소의 빈 계획서 양식의 사본)로는 넣을 내용이 없어 **실제로 넣은 자리 · 출처 · 바뀐 곳을 고치는 것까지는 보지 않는다**(등록부 · 단추 · 상태 글 · 서버 실행의 시작과 끝까지 —
실제 문서의 넣기 · 수정본은 artifacts/plan_gather_astra_2026-11-24/probe_collect.py · tests/test_merge_collect*.py 가 본다)."""
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
ap.add_argument("--port", type=int, default=18790)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"   # 빈 계획서 양식(다른 검사가 쓰는 견본) — 목적 문서도 기관 문서도 이것의 사본(이름만 다르게: 자동 지정이 파일 이름을 읽는다)
docs = OUT / "docs"
shutil.rmtree(docs, ignore_errors=True)
docs.mkdir(parents=True, exist_ok=True)
FILES = {k: docs / n for k, n in (("target", "사업계획서_취합본.hwpx"), ("a", "가나대_계획서.hwpx"), ("b", "다라연_계획서.hwpx"), ("c", "가나대_계획서_수정본.hwpx"), ("d", "모름.hwpx"))}
for f in FILES.values():
    shutil.copyfile(PLAN, f)
VALUES = {"stages": [2], "orgs": {"lead": "인텍", "joint": ["가나대", "다라연"], "nonprofit": [False, True, False]}}   # 구조 반영이 되는 값(tools/smoke_relay_flow_ui.py 와 같은 값)
NAME = "사업계획서 같은 양식 취합"
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1",
       "NFM_TASKS": str(tmp / "tasks.json"), "NFM_FORM_FILES": str(tmp / "form_files"), "NFM_AGENT_NOTES": str(tmp / "agent_notes.json"), "NFM_TOOL_NAMES": str(tmp / "tool_names.json"),
       "NFM_REQS": str(tmp / "reqs.json")}   # 이 검사가 조립한 것을 만든다 — 늘 임시
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_FLOW_EXEC"):   # NFM_FLOW_EXEC=client 면 서버 실행기가 꺼진다
    env.pop(k, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails, reqs, dialogs = [], [], [], []

S_SHAPE = "#wfCompose .wf-io-opt[data-shape={shape}] input"
S_SAVE = "#wfCompose form button[type=submit]"
# 조립 폼의 모습 — 틀 · 문서 칸 · 묶음마다 줄 카드(줄 key · 놓인 칸 · 꼬리표) · 검사 결과 · 저장 단추
FORM = f"""() => {{ const f = document.querySelector('#wfCompose form.wf-form'); if (!f) return null; const save = document.querySelector('{S_SAVE}');
  return {{ shapes: [...f.querySelectorAll('.wf-io-opt')].map((l) => [l.dataset.shape, l.querySelector('.wf-io-form').textContent, l.querySelector('input').disabled, l.querySelector('input').checked]),
    slots: [...f.querySelectorAll('.wf-io-slots > li')].map((li) => [li.dataset.role, li.querySelector('.wf-io-count').textContent]),
    groups: [...f.querySelectorAll('.wf-lines-group')].map((g) => ({{ name: (g.querySelector('.wf-lines-ghead input') || {{}}).value || '',
      cells: [...g.querySelectorAll('.wf-line-cell[data-unit]')].map((c) => [c.dataset.unit, c.dataset.role || '', /전용/.test((c.querySelector('.wf-badges') || {{}}).textContent || '')]) }})),
    errs: [...f.querySelectorAll('.wf-lines-err li')].map((x) => x.textContent), std: (f.querySelector('.wf-lines-std') || {{}}).textContent || '',
    save: save ? {{ off: save.disabled, text: save.textContent }} : null }}; }}"""
# 「기관 문서」 목록의 모습(패널 · 첫 화면 — root 안) — 머리(이름 · 단추) · 줄마다(문서 · 상태 꼬리표 · 고르기 셋 · 글 · 단추)
LIST = """(root) => { const box = document.querySelector(root + ' .collect-list'); if (!box) return null;
  const sel = (s) => (s ? { value: s.value, off: s.disabled, opts: [...s.options].map((o) => o.textContent) } : null);
  return { head: (box.querySelector('.collect-head b') || {}).textContent || '', help: !!box.querySelector('.collect-head .panel-help'),
    btns: [...box.querySelectorAll('.collect-head button.btn')].map((b) => [b.textContent, b.disabled]),
    rows: [...box.querySelectorAll('.collect-row')].map((r) => ({ part: r.dataset.part, state: r.dataset.state, name: r.querySelector('.collect-name').textContent, tag: r.querySelector('.collect-state').textContent,
      org: sel(r.querySelector('select[aria-label$="반영할 기관"]')), by: (r.querySelector('.collect-by') || {}).textContent || '', common: (() => { const c = r.querySelector('.collect-check input'); return c ? [c.checked, c.disabled] : null; })(),
      rev: sel(r.querySelector('select[aria-label$="수정본"]')), text: (r.querySelector('.collect-text') || {}).textContent || '', plan: (() => { const b = r.querySelector('.collect-acts button'); return b ? [b.textContent, b.disabled] : null; })() })),
    off: (box.querySelector('.collect-off') || {}).textContent || '', over: box.scrollWidth > box.clientWidth + 1 }; }"""
# 패널 대시보드의 모습 — 묶음마다 끝난 수 · 「한 번에 진행」 · 카드(줄 key · 상태 · 꼬리표 · 그 문서)
DASH = """() => ({ groups: [...document.querySelectorAll('#paneDash .dash-group')].map((g) => ({ id: g.dataset.group, count: (g.querySelector('.dash-gcount') || {}).textContent || '', solo: !!g.querySelector('.dash-solo'),
    run: (() => { const b = g.querySelector('.dash-ghead [data-dash-focus^="run:"]'); return b ? { text: b.textContent, off: b.disabled, title: b.title } : null; })(),
    cards: [...g.querySelectorAll('.dash-node')].map((n) => ({ key: n.dataset.key, state: n.dataset.state, st: (n.querySelector('.dash-st') || {}).textContent || '', role: (n.querySelector('.hd-role') || { dataset: {} }).dataset.role || '',
      lead: (n.querySelector('.hd-role') || {}).textContent || '', doc: (n.querySelector('.hd-role') || { dataset: {} }).dataset.doc || '', same: n.classList.contains('same') })) })),
  notes: [...document.querySelectorAll('#paneDash .dash-note')].map((n) => n.textContent), top: [...document.querySelectorAll('#paneDash .dash-top button')].map((b) => [b.textContent, b.disabled]),
  last: (() => { const p = document.querySelector('#paneDash .dash-last[data-flow-last]'); return p ? p.textContent : ''; })(),
  open: (() => { const n = document.querySelector('#paneDash .dash-node.open'); return n ? { key: n.dataset.key, text: [...n.querySelectorAll('.dash-detail > .dash-text')].map((p) => p.textContent),
    acts: [...n.querySelectorAll('.dash-detail > .dash-acts button')].map((b) => [b.textContent, b.disabled, b.dataset.dashFocus || '']) } : null; })() })"""


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:1800] if detail != "" and not ok else ""), flush=True)
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


def flow(wid):
    return requests.get(f"{base}/api/works/{wid}/flow", timeout=120).json()


def registry(tid):
    return requests.get(f"{base}/api/docs/{tid}/collect", timeout=120).json()


def works():
    return requests.get(f"{base}/api/works", timeout=60).json()


def sent(method, tail):   # 그 사이 보낸 요청의 몸들(주소가 tail 로 끝나는 것)
    return [json.loads(b) if b else None for m, u, b in reqs if m == method and u.endswith(tail)]


def home_idle(page, timeout=120000):   # 첫 화면 — 「기관 문서」 목록이 보낸 요청이 끝나고 다시 그릴 틈
    page.wait_for_function("() => !HD.busy && !Object.values(COLLECT.by).some((c) => c.busy || c.loading)", timeout=timeout)
    page.wait_for_timeout(500)


def dash_idle(page, timeout=600000):   # 문서 화면 — 이 보기가 부른 일 · 서버 실행의 거울 · 목록의 요청이 끝날 때까지
    page.wait_for_function("() => !DASH.busy && !taskRun && !relayFlowStarting && !Object.values(COLLECT.by).some((c) => c.busy || c.loading)", timeout=timeout)
    page.wait_for_function("() => !(DASH.flow && (DASH.flow.loading || DASH.flow.stale))", timeout=60000)
    page.wait_for_timeout(700)


def open_card(page, key):   # 줄의 key 로 그 카드를 편다(첫 화면의 「문서 화면에서 열기」 와 같은 길)
    page.evaluate("(k) => { DASH.open = k; return dashDraw(true); }", key)
    page.wait_for_timeout(400)


def row(L, name):
    return next((r for r in (L or {}).get("rows", []) if r["name"] == name), {})


def main():
    wait_server()
    api = requests.get(f"{base}/api/tasks?v=2", timeout=30).json()
    shape = next((x for x in api.get("shapes") or [] if x.get("id") == "collect"), {})
    first = [[s["unit"] for s in g["steps"]] for g in ((api.get("byShape") or {}).get("collect") or {}).get("flow") or []]
    check("전제 — 서버가 틀 「N → 1 · 같은 양식」 을 낸다(shapes 의 collect · byShape.collect 의 고를 줄 · 처음 줄 목록)", shape.get("io") == "N → 1 · 같은 양식" and shape.get("soon") == "" and bool(first), [shape, first])

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1600, "height": 1200})

        def watch(p, tag):
            p.on("console", lambda m: errors.append(f"[{tag}] {m.text}") if m.type == "error" else None)
            p.on("pageerror", lambda e: errors.append(f"[{tag} pageerror] {e}"))
            p.on("request", lambda q: reqs.append((q.method, q.url.replace(base, ""), q.post_data)) if q.method != "GET" else None)
            p.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
            return p

        # ---- ① 조립 화면 — 넷째 틀
        wf = watch(ctx.new_page(), "workflow")
        wf.goto(f"{base}/workflow")
        wf.wait_for_selector("#wfNav [data-wf-compose]")
        wf.click("#wfNav [data-wf-compose]")
        wf.wait_for_selector("#wfCompose form.wf-form")
        f0 = wf.evaluate(FORM)
        check("① 문서 입출력 — 틀 넷(「1」 · 「1 → N」 고름 · 「N → 1」 · 「N → 1 · 같은 양식」 — 서버가 준 차례대로 · 넷 다 켜짐)",
              [x[:3] for x in f0["shapes"]] == [[s["id"], s["io"], False] for s in api["shapes"]] and [x[0] for x in f0["shapes"]] == ["single", "relay", "gather", "collect"] and f0["shapes"][1][3] is True, f0["shapes"])
        wf.check(S_SHAPE.format(shape="collect"))
        wf.wait_for_function(f"() => !!document.querySelector('#wfCompose .wf-line-cell[data-unit=part]') && !document.querySelector('{S_SAVE}').disabled", timeout=30000)
        wf.wait_for_timeout(600)
        f1 = wf.evaluate(FORM)
        cells = [c for g in f1["groups"] for c in g["cells"]]
        src = sorted({c[0] for c in cells if c[1] == "source"})
        only = {c[0] for c in cells if c[2]}
        check("① 「N → 1 · 같은 양식」 을 고름 — 문서 칸(원본 문서 N · 목적 문서 1) · 묶음 넷(문서 검토 · 구성 맞추기 · 본문 및 테이블 매칭 · 문서 정리) · 그 틀의 처음 줄 목록(반영할 기관 지정 · 자리 연결 · 넣기 계획 · 내용 반영 · 수정본 반영)",
              f1["slots"] == [["source", "N"], ["target", "1"]] and [g["name"] for g in f1["groups"]] == ["문서 검토", "구성 맞추기", "본문 및 테이블 매칭", "문서 정리"]
              and wf.evaluate("() => [...document.querySelectorAll('#wfCompose .wf-lines-group')].map((g) => [...new Set([...g.querySelectorAll('.wf-line[data-unit]')].map((l) => l.dataset.unit))])") == first, [f1["slots"], f1["groups"], first])
        check("① 원본 문서 칸의 줄 = 「헤딩 · 표 분석」 · 「반영할 기관 지정」 뿐(서버가 준 roles 대로) · 전용 꼬리표 「전용」(반영할 기관 지정 · 프로젝트 구성 반영 …) · 서버 검사 거절 없음 · 저장 켜짐",
              src == ["heads", "part"] and {"part", "division", "retidy"} <= only and "heads" not in only and not f1["errs"] and f1["save"] and not f1["save"]["off"], [src, sorted(only), f1["errs"], f1["std"], f1["save"]])
        wf.click('#wfCompose .wf-line-cell[data-unit=part] [data-help-for=part]')
        wf.wait_for_timeout(500)
        tip = wf.evaluate("() => { const b = document.querySelector('#wfCompose .wf-help, #wfCompose .wf-toolhelp, #wfCompose [class*=help-col]'); return (b ? b.textContent : document.querySelector('#wfCompose').textContent).slice(0, 6000); }")
        check("① 「도구 설명」 열 — 「반영할 기관 지정」 을 누르면 그 도구의 설명(전용 「기관 작성본 → 사업계획서 전용」)", "반영할 기관 지정" in tip and "기관 작성본 → 사업계획서 전용" in tip, tip[:600])
        wf.screenshot(path=str(OUT / "collect_01_compose.png"))
        wf.fill("#wfCompose input[name=name]", NAME)
        reqs.clear()
        with wf.expect_response(lambda r: r.url.endswith("/api/tasks") and r.request.method == "POST") as resp:
            wf.click(S_SAVE)
        made = resp.value.json().get("task") or {}
        key = made.get("key", "")
        body = (sent("POST", "/api/tasks") or [{}])[0]
        wf.wait_for_function(f"() => !!document.querySelector('#wfCompose .wf-made-list li[data-task=\"{key}\"]')", timeout=30000)
        check("① 저장 — 201 · 몸 = {shape: collect, source: part, target: plan, flow(줄 목록)} · 서버의 정의 = v2 · shape collect · 묶음 g1 … g4 · 목록 줄",
              resp.value.status == 201 and body.get("shape") == "collect" and body.get("source") == "part" and body.get("target") == "plan" and [[x["unit"] for x in g["steps"]] for g in body.get("flow") or []] == first
              and made.get("v") == 2 and made.get("shape") == "collect" and made.get("groups") == ["g1", "g2", "g3", "g4"], [resp.value.status, {k: body.get(k) for k in ("shape", "source", "target")}, {k: made.get(k) for k in ("v", "shape", "groups")}])
        wf.click("#wfNav [data-wf-compose]")   # 저장하면 그 워크플로우의 절로 간다 — 조립 절로 돌아와 목록 줄의 「고치기」
        wf.wait_for_selector(f'#wfCompose .wf-made-list li[data-task="{key}"] button', state="visible", timeout=30000)
        wf.locator(f'#wfCompose .wf-made-list li[data-task="{key}"] button', has_text="고치기").click()
        wf.wait_for_function("() => { const f = document.querySelector('#wfCompose form.wf-form'); return !!f && f.querySelector('input[name=name]').value.length > 0 && !!f.querySelector('.wf-line-cell[data-unit=part]'); }", timeout=30000)
        wf.wait_for_timeout(500)
        f2 = wf.evaluate(FORM)
        check("① 「고치기」 로 다시 열기 — 이름 · 틀(같은 양식 취합) · 같은 줄 목록",
              wf.evaluate("() => document.querySelector('#wfCompose input[name=name]').value") == NAME and [g["cells"] for g in f2["groups"]] == [g["cells"] for g in f1["groups"]]
              and wf.evaluate("() => [...document.querySelectorAll('#wfCompose .wf-lines-group')].map((g) => [...new Set([...g.querySelectorAll('.wf-line[data-unit]')].map((l) => l.dataset.unit))])") == first, f2)
        wf.close()

        # ---- ② 목록 · ③ 첫 화면 — 목적 문서 하나 + 기관 문서 둘로 시작
        page = watch(ctx.new_page(), "home")
        page.goto(base)
        page.wait_for_selector("#homeDash[data-state=pick] select")
        c2 = page.evaluate("""(k) => ({ collect: taskIsCollect(k), kind: taskCollectKind(k), relay: taskIsRelay(k), flow: taskIsRelayFlow(k), gather: taskIsGather(k), single: taskIsSingle(k), entry: taskEntryOf(k), zones: taskZonesDefault(k),
          files: TASK_CATALOG[k].files, target: TASK_CATALOG[k].target, act: TASK_CATALOG[k].act, icon: TASK_CATALOG[k].icon, builtin: [taskIsCollect('plan_merge'), taskIsCollect('plan_to_report')] })""", key)
        check("② 목록 — 같은 양식 취합(taskIsCollect 참 · 기관 문서 종류 part) · 이관형 v2 의 화면을 같이 쓴다(taskIsRelay · taskIsRelayFlow 참) · 취합형 · 문서 하나가 아니다 · 처음 여는 보기 = 대시보드 · 편집 구역 기본 = 기관 · 붙박이 취합 · 이관은 아니다",
              c2 == {"collect": True, "kind": "part", "relay": True, "flow": True, "gather": False, "single": False, "entry": "Dash", "zones": ["org"], "files": ["part", "plan"], "target": "plan", "act": "취합", "icon": "plan_merge",
                     "builtin": [False, False]}, c2)
        with page.expect_file_chooser() as fc:
            page.locator("#pickBtn").click()
        fc.value.set_files([str(FILES[k]) for k in ("target", "a", "b")])
        page.wait_for_function("() => document.querySelectorAll('#homeFiles .hf-row').length >= 3")
        page.locator("#homeFiles .hf-row").nth(0).locator("input[type=radio]").check()
        page.select_option("#homeDash select", key)
        page.wait_for_selector("#homeDash[data-state=ready] .dash-group")
        ready = page.evaluate("() => ({ docs: [...document.querySelectorAll('#homeDash .home-dash-docs li')].map((li) => li.textContent), start: (() => { const b = document.querySelector('#homeDash [data-hd-focus=start]'); return [b.disabled, b.title]; })() })")
        check("③ 시작 전 — 문서 칸 「원본 문서 — 기관 문서(문서마다): 문서 2개」 · 「목적 문서 — 사업계획서: …」 · 「워크플로우 시작」 켜짐(기관 문서가 둘이어도 막지 않는다)",
              ready["docs"] == ["원본 문서 — 기관 문서(문서마다): 문서 2개", f"목적 문서 — 사업계획서: {FILES['target'].name}"] and not ready["start"][0], ready)
        page.locator('#homeDash [data-hd-focus="start"]').click()
        page.wait_for_selector("#homeDash[data-state=live] .dash-group", timeout=300000)
        page.wait_for_function("() => !hf.busy && !homeTaskBusy", timeout=120000)
        page.wait_for_selector("#homeDash .collect-row", timeout=60000)
        home_idle(page)
        ws = works()
        tgt = next((w for w in ws if (w.get("task") or {}).get("file") == "plan" and (w.get("task") or {}).get("job") == key), {})
        tid, scope = tgt.get("id", ""), {k: (tgt.get("task") or {}).get(k) for k in ("project", "job")}
        parts = [w for w in ws if (w.get("task") or {}).get("file") == "part" and {k: (w.get("task") or {}).get(k) for k in ("project", "job")} == scope]
        L3 = page.evaluate(LIST, "#homeDash")
        live = page.evaluate("() => ({ state: document.getElementById('homeDash').dataset.state, home: !state.id, docs: [...document.querySelectorAll('#homeDash .home-dash-docs li')].map((li) => li.textContent), toast: document.getElementById('toast').textContent })")
        check("③ 「워크플로우 시작」 — 문서 화면으로 넘어가지 않음 · 같은 묶음에 목적 문서 + 기관 문서 둘(task.file part · 같은 프로젝트 · 같은 워크플로우) · 「하나만」 으로 막지 않음",
              bool(tid) and live["home"] and live["state"] == "live" and sorted(w["name"] for w in parts) == sorted([FILES["a"].name, FILES["b"].name]) and bool(scope.get("project")) and "하나" not in live["toast"], [tgt.get("task"), [w["name"] for w in parts], live])
        check("③ 첫 화면의 대시보드 — 문서 칸 「원본 문서 — 기관 문서: 문서 2개」 · 「기관 문서」 목록 두 줄(미지정 · 노트 도움말) + 「자동 지정」 + 「기관 문서 올리기…」 · 가로 넘침 없음",
              live["docs"][0] == "원본 문서 — 기관 문서: 문서 2개" and L3 and L3["head"] == "기관 문서 2개" and L3["help"] and [r["tag"] for r in L3["rows"]] == ["미지정", "미지정"]
              and [b[0] for b in L3["btns"]] == ["자동 지정", "기관 문서 올리기…"] and not L3["over"], [live["docs"], L3])

        # ---- ④ 목록의 고르기(첫 화면 — 진짜 끝점)
        check("④ 프로젝트 구성(기관)이 없으면 — 반영할 기관 고르기 · 「자동 지정」 은 꺼짐(「프로젝트 구성 추출」 뒤에)", L3["btns"][0][1] is True and all(r["org"]["off"] and r["org"]["opts"] == ["선택 안 함"] for r in L3["rows"]), L3)
        requests.put(f"{base}/api/docs/{tid}/divisions/settings", json={"values": VALUES}, timeout=120).raise_for_status()   # 사업계획서의 값(빈 양식이라 읽을 값이 없다)
        page.evaluate("(t) => collectRead(t, true)", tid)
        page.wait_for_function("() => { const b = document.querySelector('#homeDash [data-hd-focus=\"collect:auto\"]'); return !!b && !b.disabled; }", timeout=30000)
        reqs.clear()
        page.click('#homeDash [data-hd-focus="collect:auto"]')
        page.wait_for_function("() => document.querySelectorAll('#homeDash .collect-row[data-state=todo]').length === 2", timeout=60000)
        home_idle(page)
        L4, autos = page.evaluate(LIST, "#homeDash"), [u for m, u, b in reqs if m == "POST" and u.endswith("/auto")]
        ra, rb = row(L4, FILES["a"].name), row(L4, FILES["b"].name)
        check("④ 「자동 지정」 — POST …/collect/parts/{문서}/auto 를 미지정 문서마다(둘) · 파일 이름의 기관으로(가나대 · 다라연) · 꼬리표 「파일 이름으로」 · 상태 「넣을 차례」 · 미지정이 없어 「자동 지정」 단추가 사라짐",
              len(autos) == 2 and all(f"/api/docs/{tid}/collect/parts/" in u for u in autos) and ra["org"]["value"] == "가나대" and rb["org"]["value"] == "다라연" and ra["by"] == "파일 이름으로" and rb["by"] == "파일 이름으로"
              and ra["tag"] == "넣을 차례" and [b[0] for b in L4["btns"]] == ["기관 문서 올리기…"] and ra["org"]["opts"] == ["선택 안 함", "인텍(주관)", "가나대(공동1)", "다라연(공동2)"], [autos, ra, rb, L4["btns"]])
        reqs.clear()
        page.select_option(f'#homeDash [data-hd-focus="collect:{ra["part"]}:org"]', "인텍")
        page.wait_for_function("(p) => (COLLECT.by[p[0]].view.parts.find((x) => x.work === p[1]) || {}).orgsBy === 'user'", arg=[tid, ra["part"]], timeout=30000)
        home_idle(page)
        page.check(f'#homeDash [data-hd-focus="collect:{ra["part"]}:common"]')
        page.wait_for_function("(p) => (COLLECT.by[p[0]].view.parts.find((x) => x.work === p[1]) || {}).common === true", arg=[tid, ra["part"]], timeout=30000)
        home_idle(page)
        page.select_option(f'#homeDash [data-hd-focus="collect:{ra["part"]}:org"]', "가나대")
        page.wait_for_function("(p) => ((COLLECT.by[p[0]].view.parts.find((x) => x.work === p[1]) || {}).orgs || [])[0] === '가나대'", arg=[tid, ra["part"]], timeout=30000)
        home_idle(page)
        puts, G4 = sent("PUT", f"/collect/parts/{ra['part']}"), {p["work"]: p for p in registry(tid)["parts"]}
        ra4 = row(page.evaluate(LIST, "#homeDash"), FILES["a"].name)
        check("④ 고르기 — 반영할 기관 = PUT {orgs: [이름]}(사람이 정함 — 꼬리표 「파일 이름으로」 가 사라짐) · 「공통 자리 포함」 = PUT {common: true} · 등록부에 그대로",
              puts == [{"orgs": ["인텍"]}, {"common": True}, {"orgs": ["가나대"]}] and G4[ra["part"]]["orgsBy"] == "user" and G4[ra["part"]]["common"] is True and G4[ra["part"]]["orgNames"] == ["가나대"]
              and ra4["by"] == "" and ra4["common"] == [True, False], [puts, G4[ra["part"]], ra4])
        # 기관 문서 올리기(둘 한꺼번에) — 같은 묶음의 기관 문서로(있던 문서는 그대로)
        reqs.clear()
        with page.expect_file_chooser() as fc:
            page.click('#homeDash [data-hd-focus="collect:upload"]')
        fc.value.set_files([str(FILES["c"]), str(FILES["d"])])
        page.wait_for_function("() => document.querySelectorAll('#homeDash .collect-row').length === 4", timeout=300000)
        home_idle(page)
        L4b = page.evaluate(LIST, "#homeDash")
        ws = works()
        parts = [w for w in ws if (w.get("task") or {}).get("file") == "part" and {k: (w.get("task") or {}).get(k) for k in ("project", "job")} == scope]
        ups = [u for m, u, b in reqs if m == "POST" and u.startswith("/api/docs?new=1")]
        check("④ 「기관 문서 올리기…」(파일 둘) — 새 작업 둘 · 같은 묶음의 기관 문서로(모두 넷 — 있던 둘은 그대로) · 목록 네 줄(올린 차례 · 새 문서는 미지정) · 「자동 지정」 이 다시 섬",
              len(ups) == 2 and len(parts) == 4 and [r["name"] for r in L4b["rows"]] == [FILES[k].name for k in ("a", "b", "c", "d")] and [r["tag"] for r in L4b["rows"]] == ["넣을 차례", "넣을 차례", "미지정", "미지정"]
              and [b[0] for b in L4b["btns"]] == ["자동 지정", "기관 문서 올리기…"], [ups, [w["name"] for w in parts], L4b])
        rc, rd = row(L4b, FILES["c"].name), row(L4b, FILES["d"].name)
        # 수정본 — 「가나대_계획서.hwpx 의 수정본」
        reqs.clear()
        page.select_option(f'#homeDash [data-hd-focus="collect:{rc["part"]}:org"]', "가나대")
        page.wait_for_function("(p) => ((COLLECT.by[p[0]].view.parts.find((x) => x.work === p[1]) || {}).orgs || []).length === 1", arg=[tid, rc["part"]], timeout=30000)
        home_idle(page)
        page.select_option(f'#homeDash [data-hd-focus="collect:{rc["part"]}:rev"]', ra["part"])
        page.wait_for_function("(p) => (COLLECT.by[p[0]].view.parts.find((x) => x.work === p[1]) || {}).revOf === p[2]", arg=[tid, rc["part"], ra["part"]], timeout=30000)
        home_idle(page)
        L4c = page.evaluate(LIST, "#homeDash")
        ra5, rc5 = row(L4c, FILES["a"].name), row(L4c, FILES["c"].name)
        check("④ 수정본 고르기 — 고를 것 = 「○○ 의 수정본」(같은 목록의 다른 문서) · PUT {revOf: 앞 제출본} · 그 줄 꼬리표 「수정본」 + 「수정 계획 보기」 · 앞 제출본은 「수정본 있음」",
              rc["rev"]["opts"] == ["수정본 아님"] + [f"{FILES[k].name} 의 수정본" for k in ("a", "b", "d")] and sent("PUT", f"/collect/parts/{rc['part']}")[-1] == {"revOf": ra["part"]}
              and rc5["tag"] == "수정본" and rc5["plan"] == ["수정 계획 보기", False] and ra5["tag"] == "수정본 있음" and ra5["plan"] is None, [rc["rev"], sent("PUT", f"/collect/parts/{rc['part']}"), ra5, rc5])
        page.locator("#homeDash").screenshot(path=str(OUT / "collect_02_home_list.png"))

        # ---- ⑤ 첫 화면의 문서 카드 · 서버 실행
        page.wait_for_function("() => !!document.querySelector('#homeDash .hd-row[data-key=heads] .collect-doc')", timeout=30000)
        cards5 = page.evaluate("""() => [...document.querySelectorAll('#homeDash .hd-row[data-key=heads] .dash-node')].map((n) => { const t = n.querySelector('.hd-role'); return [t.dataset.role, t.dataset.doc || '', t.textContent, t.classList.contains('collect-doc')]; })""")
        V5 = flow(tid)
        heads5 = [p for p in next(s for g in V5["stages"] for s in g["steps"] if s["key"] == "heads")["per"] if p["role"] == "source"]
        check("⑤ 첫 화면의 문서 카드 — 「헤딩 · 표 분석」 은 기관 문서마다 카드(서버의 per — 뒤 수정본이 있는 문서는 빠짐) · 꼬리표 = 「[기관 약칭] 파일 이름」(spec_취합 ② §11 — 미지정은 「[미지정]」) + 목적 문서 카드",
              [c[1] for c in cards5 if c[3]] == [p["doc"] for p in heads5] and len(heads5) == 3 and [c[2] for c in cards5 if c[3]] == [f"[다라] {FILES['b'].name}", f"[가나] {FILES['c'].name}", f"[미지정] {FILES['d'].name}"]
              and cards5[-1][:1] == ["target"] and not cards5[-1][3], [cards5, heads5])
        reqs.clear()
        page.click('#homeDash .dash-group[data-group="g2"] .dash-ghead [data-hd-focus="run:g2"]')   # 1단계는 올릴 때의 첫 분석으로 이미 끝났다(LLM 끔 = 건너뜀) — 2단계 「구성 맞추기」 를 돌린다
        page.wait_for_function("() => !!document.querySelector('#homeDash .dash-live') || !!document.querySelector('#homeDash .dash-last')", timeout=60000)
        off5 = page.evaluate(LIST, "#homeDash")
        end = time.time() + 300
        while time.time() < end and flow(tid).get("runs"):
            time.sleep(0.5)
        page.evaluate("() => hdRead()")
        page.wait_for_selector("#homeDash .dash-last", timeout=60000)
        home_idle(page)
        runs5, V5b = sent("POST", "/flow/runs"), flow(tid)
        g1, g2 = (next(g for g in V5b["stages"] if g["id"] == i) for i in ("g1", "g2"))
        check("⑤ 첫 화면에서 2단계 「한 번에 진행」 — 서버 실행(시작 요청 {from: g2, docs{target, source: null}} · 화면에 머묾) · 끝 글 · 1 · 2단계 남은 것 0(프로젝트 구성 추출 · 구조 반영 · 다시 문서 검토) · 실행 기록에 기관 문서들이 못 박힘",
              len(runs5) == 1 and runs5[0].get("from") == "g2" and runs5[0].get("docs") == {"target": tid, "source": None} and g1["left"] == 0 and g2["left"] == 0 and page.evaluate("() => !state.id")
              and len(((V5b.get("last") or {}).get("docs") or {}).get("sources") or []) >= 3 and page.evaluate("() => document.querySelector('#homeDash .dash-last').textContent").startswith(("끝남 — ", "남김 — ")), [runs5, g1["left"], g2["left"], g2.get("why"), V5b.get("last")])
        check("⑤ 도는 동안(또는 끝난 뒤) 목록이 그대로 서 있다 — 줄 넷", bool(off5) and len(off5["rows"]) == 4, off5)

        # ---- ⑥ 문서 화면의 대시보드(패널)
        page.evaluate("(id) => openWork(id)", tid)   # 첫 화면에서 목적 문서로(주소의 # 만 바꾸면 다시 읽지 않는다)
        page.wait_for_function("(id) => typeof state !== 'undefined' && state.id === id && !state.loading", arg=tid, timeout=120000)
        page.evaluate("() => showTab('Dash')")
        page.wait_for_function("() => !!(DASH.flow && DASH.flow.view) && !!document.querySelector('#paneDash .dash-group .dash-st')", timeout=120000)
        page.wait_for_function("(t) => !!collectView(t)", arg=tid, timeout=60000)
        dash_idle(page)
        d6 = page.evaluate(DASH)
        g = {x["id"]: x for x in d6["groups"]}
        heads6 = [c for c in g["g1"]["cards"] if c["key"] == "heads"]
        check("⑥ 패널 대시보드 — 묶음 넷(g1 … g4 · 끝난 수 「n/m」) · 「한 문서만」 줄 없음(서버가 solo 를 안 낸다) · 「헤딩 · 표 분석」 = 기관 문서마다 카드(꼬리표 「[기관 약칭] 파일 이름」 · ✓ 끝남) + 목적 문서 카드 · 둘째부터는 번호 없이 붙음",
              list(g) == ["g1", "g2", "g3", "g4"] and all(re.fullmatch(r"\d+/\d+", x["count"]) for x in d6["groups"]) and not any(x["solo"] for x in d6["groups"])
              and [c["lead"] for c in heads6] == [f"[다라] {FILES['b'].name}", f"[가나] {FILES['c'].name}", f"[미지정] {FILES['d'].name}", "목적 문서"] and all(c["st"] == "✓ 끝남" for c in heads6)
              and [c["same"] for c in heads6] == [False, True, True, True], [[(x["id"], x["count"], x["solo"]) for x in d6["groups"]], heads6])
        g3 = [(c["key"], c["lead"], c["role"]) for c in g["g3"]["cards"]]
        check("⑥ 3단계의 카드 — 「반영할 기관 지정」 = 카드 하나(꼬리표 「[기관]」) · 넣는 줄(자리 연결 · 넣기 계획 · 내용 반영)은 넣을 기관 문서마다([다라] …: 미지정 · 수정본 · 수정본이 생긴 문서는 카드 없음) · 「수정본 반영」 = 수정본마다([가나] …수정본)",
              g3[0] == ("part", "[기관]", "source") and [x[:2] for x in g3[1:4]] == [(k, f"[다라] {FILES['b'].name}") for k in ("link", "plan", "apply")] and g3[4][:2] == ("revise", f"[가나] {FILES['c'].name}") and len(g3) == 5, g3)
        tags6 = page.evaluate("""() => ({ mine: [document.getElementById('docRole').textContent, document.getElementById('docRole').dataset.role],
            parts: Object.fromEntries(relayFlowParts().map((w) => [w.name, (docOrgTag(w) || {}).tag || ''])), short: [orgShort('사단법인 한국선급', ['한국선급', '(주)씨드로닉스', '유엔젤', '한국해양대학교']), orgShort('(주)씨드로닉스', ['씨드로닉스', '유엔젤', '랩오투원'])] })""")
        check("⑥ 기관 문서 꼬리표(spec_취합 ② §11) — 목적 문서는 「목적 문서」 · 기관 문서는 반영할 기관의 약칭(인텍 · 가나대 · 다라연 = 앞 2글자가 모두 달라 2글자) · 미지정 「[미지정]」 · 앞 2글자가 겹치면 모두 3글자",
              tags6["mine"] == ["목적 문서", "target"] and tags6["parts"].get(FILES["b"].name) == "[다라]" and tags6["parts"].get(FILES["a"].name) == "[가나]" and tags6["parts"].get(FILES["d"].name) == "[미지정]"
              and tags6["short"] == ["한국선", "씨드"], tags6)
        open_card(page, "files")
        page.wait_for_selector("#paneDash .dash-node.open .collect-row", timeout=30000)
        o6, L6 =page.evaluate(DASH)["open"], page.evaluate(LIST, "#paneDash")
        check("⑥ 「준비」 카드 — 문서 칸(원본 문서 — 기관 문서: 문서 4개 · 목적 문서 — 사업계획서: … — 지금 문서) · 「기관 문서」 목록(줄 넷 — 이름 · 상태 꼬리표 · 반영할 기관 · 공통 자리 포함 · 수정본) · 「기관 문서 올리기…」 · 가로 넘침 없음",
              o6["key"] == "files" and any("원본 문서 — 기관 문서" in t and "문서 4개" in t for t in o6["text"]) and any("목적 문서 — 사업계획서" in t and "지금 문서" in t for t in o6["text"])
              and L6["head"] == "기관 문서 4개" and [r["tag"] for r in L6["rows"]] == ["수정본 있음", "넣을 차례", "수정본", "미지정"] and [b[0] for b in L6["btns"]] == ["자동 지정", "기관 문서 올리기…"]
              and row(L6, FILES["a"].name)["common"] == [True, False] and row(L6, FILES["b"].name)["org"]["value"] == "다라연" and not L6["over"], [o6, L6])
        page.locator("#paneDash").screenshot(path=str(OUT / "collect_03_dash_list.png"))
        page.click(f'#paneDash [data-dash-focus="collect:{rb["part"]}:open"]')   # 파일 이름 → 그 기관 문서를 둘째 면에(같이 보기)
        page.wait_for_function("(id) => peerShown() === id", arg=rb["part"], timeout=60000)
        peer6 = page.evaluate("() => ({ shown: peerShown(), main: state.id, col: !document.getElementById('peerCol').hidden })")
        check("⑥ 목록의 파일 이름을 누르면 — 그 기관 문서가 둘째 면(같이 보기)에 열린다 · 보던 문서(목적 문서)는 그대로", peer6 == {"shown": rb["part"], "main": tid, "col": True}, peer6)
        page.evaluate("() => peerSet(false)")
        page.wait_for_function("() => !peerShown()", timeout=30000)
        open_card(page, "part")
        page.wait_for_selector('#paneDash .dash-node.open[data-key="part"] .collect-row', timeout=30000)
        o6b = page.evaluate(DASH)["open"]
        check("⑥ 「반영할 기관 지정」 카드 — 같은 「기관 문서」 목록 + 「이 단계만 진행」(문서 하나만 도는 단추가 아니다 — 초점 이름에 문서 역할뿐)",
              o6b["key"] == "part" and len(page.evaluate(LIST, "#paneDash")["rows"]) == 4 and [a for a in o6b["acts"] if a[0] == "이 단계만 진행"] == [["이 단계만 진행", False, "act:part@source:only"]], o6b)
        # 반영할 기관 고르기(패널) — 미지정 문서를 다라연으로 → 서버 상태의 줄 글이 따라온다
        reqs.clear()
        page.select_option(f'#paneDash [data-dash-focus="collect:{rd["part"]}:org"]', "다라연")
        page.wait_for_function("(p) => ((COLLECT.by[p[0]].view.parts.find((x) => x.work === p[1]) || {}).orgs || [])[0] === '다라연'", arg=[tid, rd["part"]], timeout=30000)
        dash_idle(page)
        d6c = page.evaluate(DASH)
        check("⑥ 패널에서 반영할 기관 고르기 — PUT {orgs: [다라연]} · 대시보드가 서버 상태를 다시 읽음(넣는 줄의 카드가 그 문서만큼 늘고 꼬리표 = 「다라연 — 모름.hwpx」) · 「자동 지정」 이 사라짐",
              sent("PUT", f"/collect/parts/{rd['part']}") == [{"orgs": ["다라연"]}] and [c["lead"] for c in {x["id"]: x for x in d6c["groups"]}["g3"]["cards"] if c["key"] == "link"] == [f"[다라] {FILES['b'].name}", f"[다라] {FILES['d'].name}"]
              and [b[0] for b in page.evaluate(LIST, "#paneDash")["btns"]] == ["기관 문서 올리기…"], [sent("PUT", f"/collect/parts/{rd['part']}"), {x["id"]: x for x in d6c["groups"]}["g3"]["cards"]])
        page.evaluate("() => showTab('Div')")
        page.wait_for_selector("#paneDiv [data-task-many]", timeout=30000)
        div6 = page.evaluate("() => { const m = document.querySelector('#paneDiv [data-task-many]'), f = document.querySelector('#paneDiv .dv-flow-files'); return { many: m.textContent, sels: f.querySelectorAll('select[data-task-file]').length, fit: m.getBoundingClientRect().right <= f.getBoundingClientRect().right + 1 }; }")
        st6 = page.evaluate("() => agwStatus().then((s) => ({ stages: [...new Set(s.steps.map((x) => x.stage))], keys: s.steps.map((x) => x.key).slice(0, 3) }))")
        check("⑥ 「작업 개요」 — 기관 문서 줄은 문서 하나를 고르는 칸이 아니다(「문서 4개」 + 「기관 문서 목록」 · 고르기 칸은 목적 문서 하나뿐 · 칸 밖으로 안 넘침) · 에이전트 상태 = 서버 상태의 묶음(1단계 문서 검토 …)",
              div6["many"].startswith("문서 4개") and "기관 문서 목록" in div6["many"] and div6["sels"] == 1 and div6["fit"] and st6["stages"] == ["1단계 문서 검토", "2단계 구성 맞추기", "3단계 본문 및 테이블 매칭", "4단계 문서 정리"]
              and st6["keys"] == ["files", "heads", "headsLlm"], [div6, st6])
        page.evaluate("() => showTab('Dash')")
        dash_idle(page)

        # ---- ⑦ 수정 계획
        open_card(page, "files")
        page.wait_for_selector(f'#paneDash [data-dash-focus="collect:{rc["part"]}:plan"]', timeout=30000)
        reqs.clear()
        page.click(f'#paneDash [data-dash-focus="collect:{rc["part"]}:plan"]')
        page.wait_for_selector(f'#paneDash .collect-plan[data-part="{rc["part"]}"] .collect-plan-sum', timeout=120000)
        dash_idle(page)
        p7 = page.evaluate("""() => { const b = document.querySelector('#paneDash .collect-plan'); const go = b.querySelector('button'); return { sum: b.querySelector('.collect-plan-sum').textContent, go: [go.textContent, go.disabled, go.title], items: b.querySelectorAll('.collect-item').length,
          toggle: document.querySelector('#paneDash .collect-acts button').textContent, dialog: !!document.querySelector('dialog[open]') }; }""")
        check("⑦ 「수정 계획 보기」(진짜 끝점 POST …/revise/plan) — 그 줄 아래에 펴짐(창을 띄우지 않음) · 견본은 「바뀐 곳 없음」 · 「수정본 반영」 은 꺼짐(고칠 곳이 없습니다) · 단추가 「수정 계획 접기」 로",
              [u for m, u, b in reqs if m == "POST" and u.endswith(f"/collect/parts/{rc['part']}/revise/plan")] != [] and p7["sum"] == "바뀐 곳 없음" and p7["go"][:2] == ["수정본 반영", True] and "고칠 곳이 없습니다" in p7["go"][2]
              and p7["items"] == 0 and p7["toggle"] == "수정 계획 접기" and not p7["dialog"], [p7, reqs])
        page.click(f'#paneDash [data-dash-focus="collect:{rc["part"]}:plan"]')   # 접기
        page.wait_for_function("() => !document.querySelector('#paneDash .collect-plan')", timeout=30000)
        FAKE = {"planId": "smoke0000plan", "part": rc["part"], "base": [ra["part"]], "todo": 2, "counts": {"ready": 2, "same": 1, "overlap": 1, "hold": 1, "missing": 1},
                "text": "고칠 곳 2 · 이미 같음 1 · 겹침(사람이 고친 자리 — 그대로 둠) 1 · 확인 필요 1 · 수정본에 없음(그대로 둠) 1",
                "items": [{"kind": "para", "to": "p1", "from": "s1", "place": "k1", "status": "ready", "detail": "", "was": "연구개발의 최종 목표는 시제품 1종 개발이다.", "text": "연구개발의 최종 목표는 시제품 2종 개발과 실증이다."},
                          {"kind": "cell", "to": "c1", "from": "s2", "place": "t1", "status": "ready", "detail": "", "was": "120", "text": "150"},
                          {"kind": "para", "to": "p2", "from": "s3", "place": "k1", "status": "overlap", "detail": "사람이 고친 자리 — 그대로 둠", "was": "사람이 고쳐 쓴 문장", "text": "수정본의 새 문장"},
                          {"kind": "para", "to": "p3", "from": "s4", "place": "k2", "status": "hold", "detail": "같은 글 줄이 여럿인 자리", "was": "가. 개요", "text": "가. 개요(수정)"},
                          {"kind": "para", "to": "p4", "from": None, "place": "k2", "status": "missing", "detail": "수정본에 이 자리가 없음 — 그대로 둠", "was": "수정본에서 빠진 문단", "text": None}],
                "fresh": {"todo": 0, "body": {}, "tables": {}, "fixed": {}, "heldRows": 0}}
        pat = re.compile(r"/collect/parts/[0-9a-f]+/revise/plan$")
        page.route(pat, lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(FAKE, ensure_ascii=False)))   # 항목이 있는 계획(응답 흉내 — 견본 문서로는 바뀐 곳이 없다)
        page.click(f'#paneDash [data-dash-focus="collect:{rc["part"]}:plan"]')
        page.wait_for_selector("#paneDash .collect-plan .collect-item", timeout=60000)
        dash_idle(page)
        page.unroute(pat)
        p7b = page.evaluate("""() => { const b = document.querySelector('#paneDash .collect-plan'), go = b.querySelector('.collect-plan-head button'), row = b.closest('.collect-row');
          return { under: row.dataset.part, sum: b.querySelector('.collect-plan-sum').textContent, go: [go.textContent, go.disabled, go.classList.contains('primary')],
            items: [...b.querySelectorAll('.collect-item')].map((li) => [li.dataset.status, li.querySelector('.collect-item-tag').textContent, li.querySelector('.collect-item-kind').textContent, (li.querySelector('.collect-diff') || {}).textContent || '']),
            over: b.scrollWidth > b.clientWidth + 1, dialog: !!document.querySelector('dialog[open]') }; }""")
        check("⑦ 항목이 있는 수정 계획 — 그 문서 줄 아래에 · 한 줄 요약(서버의 글) · 「수정본 반영」 켜짐(강조) · 항목마다 상태 꼬리표(고칠 곳 · 겹침 · 확인 필요 · 수정본에 없음) · 값의 이름과 함께 「지금 \"…\" → 수정본 \"…\"」 · 가로 넘침 없음",
              p7b["under"] == rc["part"] and p7b["sum"] == FAKE["text"] and p7b["go"] == ["수정본 반영", False, True] and [x[1] for x in p7b["items"]] == ["고칠 곳", "고칠 곳", "겹침", "확인 필요", "수정본에 없음"]
              and [x[2] for x in p7b["items"]] == ["문단", "표 칸", "문단", "문단", "문단"] and p7b["items"][1][3] == '지금"120"→수정본"150"' and p7b["items"][4][3] == '지금"수정본에서 빠진 문단"→수정본(없음)'
              and not p7b["over"] and not p7b["dialog"], p7b)
        page.locator("#paneDash").screenshot(path=str(OUT / "collect_04_revise_plan.png"))
        page.locator("#paneDash .collect-plan").screenshot(path=str(OUT / "collect_04_revise_plan_box.png"))
        reqs.clear()
        dialogs.clear()
        page.click(f'#paneDash [data-dash-focus="collect:{rc["part"]}:apply"]')
        page.wait_for_function("() => !document.querySelector('#paneDash .collect-plan') && !Object.values(COLLECT.by).some((c) => c.busy)", timeout=120000)
        dash_idle(page)
        ap7 = [(u, json.loads(b)) for m, u, b in reqs if m == "POST" and u.endswith("/revise/apply")]
        t7 = page.evaluate("() => document.getElementById('toast').textContent")
        check("⑦ 「수정본 반영」 — 누르기 전에 한 줄 확인(문서가 바뀝니다 · 실행 취소) → POST …/revise/apply {planId}(진짜 끝점) · 흉내 낸 계획이라 서버가 거절(409 낡은 계획) — 그 글이 알림으로 · 편 계획을 걷음(「수정 계획 보기」 로 다시)",
              len(dialogs) == 1 and "문서가 바뀝니다" in dialogs[0] and "2곳" in dialogs[0] and len(ap7) == 1 and ap7[0][0].endswith(f"/collect/parts/{rc['part']}/revise/apply") and ap7[0][1] == {"planId": "smoke0000plan"}
              and bool(t7) and row(page.evaluate(LIST, "#paneDash"), FILES["c"].name)["plan"] == ["수정 계획 보기", False], [dialogs, ap7, t7])

        # ---- ⑧ 패널에서 「이어서 한 번에」 = 서버 실행 + 거울
        open_card(page, "files")
        top8 = page.evaluate(DASH)["top"]
        reqs.clear()
        page.click('#paneDash [data-dash-focus="run:chain"]')
        page.wait_for_function("() => !!taskRun && !!taskRun.flow", timeout=60000)
        page.wait_for_function("() => !!document.querySelector('#paneDash .dash-live button')", timeout=30000)
        open_card(page, "files")
        mid = page.evaluate("() => { const R = agwRunning(); return { flow: !!(taskRun && taskRun.flow), kind: R && R.kind, live: !!document.querySelector('#paneDash .dash-live') }; }")
        L8 = page.evaluate(LIST, "#paneDash")
        dash_idle(page)
        runs8, V8, d8 = sent("POST", "/flow/runs"), flow(tid), page.evaluate(DASH)
        st8 = {s["key"]: s for gg in V8["stages"] for s in gg["steps"]}
        check("⑧ 「이어서 한 번에 3→4단계」 — 시작 요청 {from: g3, to: g4, docs{target, source: null}} = 서버 실행 · 도는 동안 거울(taskRun.flow · 에이전트 진행 kind flow · 진행 줄)",
              top8 == [["이어서 한 번에 3→4단계", False]] and len(runs8) == 1 and runs8[0].get("from") == "g3" and runs8[0].get("to") == "g4" and runs8[0].get("docs") == {"target": tid, "source": None} and "role" not in runs8[0]
              and mid == {"flow": True, "kind": "flow", "live": True}, [top8, runs8, mid])
        check("⑧ 도는 동안 「기관 문서」 목록의 고르기는 꺼짐(까닭 글) — 반영할 기관 · 공통 자리 포함 · 수정본 · 올리기",
              bool(L8) and all(r["org"]["off"] and r["common"][1] and r["rev"]["off"] for r in L8["rows"]) and all(b[1] for b in L8["btns"]) and "끝나면" in L8["off"], L8)
        check("⑧ 끝 — 지난 실행의 끝 글(서버가 지은 글) · 2단계 「프로젝트 구성 반영」 끝남(⑤ 에서) · 3단계 「반영할 기관 지정」 끝남 · 「수정본 반영」 끝남(수정본 1개) · 등록부의 수정본 = 반영함",
              d8["last"].startswith(("끝남 — ", "남김 — ")) and st8["division"]["done"] and st8["part"]["done"] and st8["revise"]["done"] and "수정본 1개" in st8["revise"]["text"]
              and next(p for p in registry(tid)["parts"] if p["work"] == rc["part"])["state"] in ("done", "left"), [d8["last"], {k: (st8[k]["st"], st8[k]["text"]) for k in ("division", "part", "link", "apply", "revise")}, registry(tid)["parts"]])
        open_card(page, "files")
        page.wait_for_selector("#paneDash .dash-node.open .collect-row", timeout=30000)
        page.wait_for_timeout(600)
        page.locator("#paneDash").screenshot(path=str(OUT / "collect_05_dash_done.png"))

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

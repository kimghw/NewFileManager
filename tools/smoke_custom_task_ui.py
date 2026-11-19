"""조립한 TASK(spec_워크플로우 ② §14 — 2026-11-19 사용자 "배치를 내가 할 수 없네?" → 답 「새 TASK 만들기」) 화면 확인 — 임시 서버(임시 작업 폴더 · 임시 TASK 저장소 · PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_custom_task_ui.py <그림·임시 폴더> [--port 18166]

⓪ 저장 파일(spec_워크플로우 ② §15 「저장」 — 2차): 옛 줄(assign 없이 stages 만)을 tasks.json 에 직접 적으면 — 서버가 읽어 채운 assign(원본 = 문서 검토 · 목적 = 고른 단계 · llm = 원본만: 옛 뜻) ·
   그 워크플로우 절의 표(1단계 LLM 검증·보완은 원본 칸에만) · 「구성 맞추기」 가 없어 구성의 기준이 없음(base null — 워크플로우 전체 줄에 「구성의 기준」 을 안 적음) · 설명을 비워 등록부가 지은 글(descAuto) ·
   고치기 폼의 LLM 줄(저장된 값) · 이름만 고쳐도 llm 이 그대로. 깨진 파일 — 폼 위에 까닭(broken) · 목록 없음 · 만들기는 409(서버의 글 그대로) · 파일은 그대로.
① /workflow 의 「워크플로우 조립」: 목차의 「＋ 워크플로우 조립」 → 폼(이름 · 한 줄 설명 · 문서 쌍 · 문서 역할 × 단계 표 · 전제 — spec_워크플로우 ② §15 「문서마다 단위문서 TASK」):
   표의 칸 = 서버의 cells(체크 assign-source · assign-target · 따라오는 글 · 고를 수 없는 까닭) · 표 아래 「직접 고른 단계」(단계 사이 「 › 」) · 경고(목적 문서에 구성 맞추기 없이 내용 넣기 — 막지 않음 · 뒷부분 = 서버의 warn.fillNoFit)
   → 원본은 끄고 목적 문서에 단계 둘만 골라 만들기(저장 몸 = assign 만 — 합집합 stages 없음 · 저장한 assign 에 서버가 정한 llm) → 그 워크플로우 절(조립한 것 · 고른 단계만 · 번호는 1부터 · 문서마다 단위문서 TASK 표 +
   워크플로우 전체 줄 「워크플로우 전체(문서마다가 아니라 한 번): 1단계 구성 맞추기(준비 › 구성 불러오기 › 프로젝트 구성 확정) — 구성의 기준: …」) · 목차 · 단계 절.
② 같은 이름 · 원본 문서를 쓰는 단계가 없는 배정이면 서버의 까닭(400)이 폼에 그대로(「워크플로우」 라 함 — 「TASK」 가 아님) · 「고치기」(폼에 저장한 assign 이 채워짐)로 이름 · 단계를 바꿈(sig 가 바뀜) ·
   cells 를 주지 않는 서버(흉내)면 폼을 열지 않음(「조립은 서버를 다시 켠 뒤에 쓸 수 있습니다」).
③ 고치는 사이 그 워크플로우로 작업을 시작하면 단계를 바꾼 저장은 409(서버의 글 그대로 = editWhy — 폼이 잠기고 잠금 글도 그 글 · 「복제」) · 앱: 시작 화면의 카드 · 그 워크플로우로 연 문서의 「작업 개요」 가 고른 묶음만(번호 1부터 · 맨 앞 묶음에 준비) ·
   묶음의 「한 번에 진행」 이 그 묶음의 단계로 돎(값이 없는 문서 — 구성 확정에서 멈춤) · 대시보드.
③-2 원본의 문서 검토를 끄고 목적 문서에 문서 검토 + 구성 맞추기 → 그 워크플로우의 1단계에 LLM 검증·보완 줄이 없음(절 · 「작업 개요」 · 대시보드 — 목적 문서의 LLM 검증·보완은 「다시 문서 검토(LLM)」 에서) ·
   설명을 비워 등록부가 지은 글(descAuto — 「내용 넣기」 가 없어 「옮깁니다」 라 하지 않음)이 절 · 다이어그램의 설명.
④ 쓰는 중(지금 워크플로우로 둔 작업이 있음 — editWhy) — 「고치기」 는 단계 표를 끄고 이름 · 설명 · 전제만(저장 몸에 assign 없음 · sig 그대로) · 「복제」 = 같은 배정(llm 까지) · 설명 · 전제 + 이름 「… 사본」 의 새 폼 → 새 워크플로우.
   목록 줄의 셈 「하던 작업 2개」 아래에 그 작업 둘의 링크(서버의 uses — 이름 = 작업 리스트의 이름 · 새 탭 · /#w=<작업 id>) · 꼬리표 「지금 워크플로우」(3차 계약 D1).
⑤ 그 워크플로우를 쓰는 작업이 있으면 「지우기」 가 꺼짐(풍선 도움말 = 서버의 deleteWhy) · 지금 워크플로우는 목록에서 못 뺌(400) → 작업을 지움 → 문서의 워크플로우 목록에만 든 작업(listed)이 남으면
   목록 줄의 셈 「목록에 든 작업 1개」 · 그 작업의 링크 · 꼬리표 「목록에만」(누르면 새 탭에서 그 작업이 열림) · 「고치기」 는 잠기지 않고 「지우기」 는 꺼짐 →
   그 줄을 빼면(DELETE /api/works/{wid}/workflows/{job} — 한 번 더 빼면 404) 지움 → 목차 · 카드에서 사라짐."""
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
ap.add_argument("--port", type=int, default=18166)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"),
       "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_TASKS": str(tmp / "tasks.json"), "PYTHONUTF8": "1"}
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


NAV = "() => ({ links: [...document.querySelectorAll('#wfNav a')].map((a) => [a.getAttribute('href'), a.textContent, a.className]), heads: [...document.querySelectorAll('#wfNav h2')].map((x) => x.textContent) })"
# 「워크플로우 조립」 절의 목록 줄 — 키 · 이름 · 문서마다 고른 단계 · 단추 [글, 꺼짐] · 단추의 풍선 도움말 · 쓰는 작업의 셈 [[종류(current 지금 워크플로우 · listed 목록에만), 글] …](0 이면 없음) ·
# 그 작업들(셈 아래 줄 — 서버의 uses: [{wid, use, name(링크 글), href, target, rel, tag(꼬리표), where(프로젝트 · 라운드), below(셈 뒤 줄에 있나)}]) · more(「외 n개」 | '')
MADE = ("() => [...document.querySelectorAll('#wfCompose .wf-made-list > li')].map((li) => ({ key: li.dataset.task, name: li.querySelector('.wf-over-name').textContent, "
        "roles: [...li.querySelectorAll('.wf-made-role')].map((r) => [r.dataset.role, [...r.querySelectorAll('.wf-chip')].map((c) => c.textContent), r.textContent]), btns: [...li.querySelectorAll('button')].map((b) => [b.textContent, b.disabled]), "
        "tips: [...li.querySelectorAll('button')].map((b) => b.title), use: [...li.querySelectorAll('.wf-made-use')].map((s) => [s.dataset.use, s.textContent]), "
        "works: [...li.querySelectorAll('.wf-made-works > li[data-wid]')].map((x) => { const a = x.querySelector('a.wf-made-work'), m = x.querySelector('.wf-muted'), cs = [...li.querySelectorAll('.wf-made-use')], c = cs[cs.length - 1];"
        " return { wid: x.dataset.wid, use: x.dataset.use, name: a && a.textContent, href: a && a.getAttribute('href'), target: a && a.target, rel: a && a.rel, tag: (x.querySelector('.wf-made-tag') || {}).textContent || '', where: m ? m.textContent : '',"
        " below: !c || x.getBoundingClientRect().top >= c.getBoundingClientRect().bottom - 1 }; }), more: (li.querySelector('.wf-made-more') || {}).textContent || '' }))")
# 그 워크플로우 절의 「워크플로우 전체」 줄 — 머리 · 구성의 기준(span 이 있나 · 글) · 줄 글(textContent) · 눈에 보이는 글(CSS 의 이음 기호 「›」 까지 — 보이는 절에서만 뜻이 있다: 목록 보기) | null
FLOW = """(k) => { const f = document.querySelector('#' + k + ' .wf-docs-flow'); if (!f) return null; const b = f.querySelector('.wf-docs-base');
  const pc = (n, p) => { const c = getComputedStyle(n, p).content, s = c && c !== 'none' && c !== 'normal' ? c.replace(/^"(.*)"$/, '$1') : ''; return s ? ' ' + s + ' ' : ''; };
  const seen = (n) => n.nodeType === 3 ? n.textContent : n.nodeType !== 1 ? '' : pc(n, '::before') + [...n.childNodes].map(seen).join('') + pc(n, '::after');
  return { name: f.querySelector(':scope > b').textContent, base: b ? b.textContent : null, text: f.textContent, line: seen(f).replace(/\\s+/g, ' ').trim() }; }"""
# 조립 폼의 문서 역할 × 단계 표(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) — 머리 · 행마다(단계 id · 이름 · 그 단계의 줄들 · 역할마다 {칸 종류 · 체크 [이름, 값, 켜짐] · 글}) · 「직접 고른 단계」 줄 · 경고(보일 때만 글) ·
# 「문서 검토」 의 LLM 검증·보완 줄(고치기 · 복제 — 서버가 준 값: 보일 때만 [글, 연 때 그대로인가]) · 잠금(쓰는 중 — 표가 꺼졌나 · 잠금 글 · 「복제」 단추)
FORM = """() => { const f = document.querySelector('#wfCompose form.wf-form'), t = f.querySelector('table.wf-assign'), w = f.querySelector('.wf-assign-warn'), l = f.querySelector('.wf-assign-llm'), k = f.querySelector('.wf-assign-lock');
  return { title: f.querySelector('h3').textContent, legend: f.querySelector('fieldset.wf-stage-pick > legend').textContent, head: [...t.querySelectorAll('thead th')].map((x) => x.textContent),
    rows: [...t.querySelectorAll('tbody tr')].map((tr) => ({ id: tr.dataset.stage, name: tr.querySelector('th b').textContent, steps: tr.querySelector('th .wf-stage-steps').textContent,
      cells: Object.fromEntries([...tr.querySelectorAll('td')].map((td) => { const i = td.querySelector('input'); return [td.dataset.role, { mode: td.dataset.mode, box: i && [i.name, i.value, i.checked], text: td.textContent }]; })) })),
    sumHead: (f.querySelector('.wf-assign-sum-head') || {}).textContent || '', units: [...f.querySelectorAll('.wf-assign-units > li')].map((li) => [li.dataset.role, li.textContent]), warn: w.hidden ? '' : w.textContent,
    llm: l && !l.hidden ? [l.textContent, l.dataset.keep] : null, off: f.querySelector('fieldset.wf-stage-pick').disabled, boxesOff: [...t.querySelectorAll('input[type=checkbox]')].every((i) => i.matches(':disabled')),
    lock: k ? k.textContent : '', copy: !!(k && k.querySelector('button[data-wf-copy]')), name: f.querySelector('input[name=name]').value, desc: f.querySelector('input[name=desc]').value,
    premise: f.querySelector('textarea[name=premise]').value }; }"""
STAGE_IDS = ("stage_review", "stage_fit", "stage_fill", "stage_clean")
NO_COMPOSE = "조립은 서버를 다시 켠 뒤에 쓸 수 있습니다"   # cells 를 주지 않는 서버면 폼 대신(workflow.js NO_COMPOSE)
NO_SOURCE = "원본 문서를 쓰는 단계가 없습니다 — 원본 문서의 「문서 검토」 나 목적 문서의 「구성 맞추기」 · 「내용 넣기」 를 고르세요"   # 서버의 400(custom_tasks — 2차 계약)
FLOW_HEAD = "워크플로우 전체(문서마다가 아니라 한 번)"   # 워크플로우 절의 표 아래 줄의 머리(workflow.js FLOW_HEAD — 전의 「프로젝트에 한 번」 을 바꿈)
WARN_HEAD = "목적 문서에 「구성 맞추기」 없이 「내용 넣기」 — "   # 조립 폼의 경고 앞부분(화면) — 뒷부분은 서버의 warn.fillNoFit(등록부의 글이 원본)
FILL_NO_FIT = "목적 문서에 구조 반영 기록이 있고 두 문서의 프로젝트 구성 값이 같아야 자리 연결이 섭니다(손으로 맞춘 구조는 「반영 전」 으로 멈춤)"   # 3차 계약의 그 글(GET /api/tasks warn.fillNoFit)
DEL_WHY = "이 워크플로우를 쓰는 작업이 {n}개 있어 지울 수 없습니다 — 지금 워크플로우로 둔 작업은 다른 워크플로우로 바꾸고, 대시보드 「이 문서의 워크플로우」 목록에서 빼면 지울 수 있습니다"   # DELETE 409 = deleteWhy(n = inUse + listed)
ROW_NOW = "지금 워크플로우는 목록에서 뺄 수 없습니다 — 다른 워크플로우로 바꾼 뒤에 빼세요"   # DELETE /api/works/{wid}/workflows/{job} 의 400
ROW_NONE = "목록에 그 워크플로우가 없습니다"   # 같은 끝점의 404
SIG = re.compile(r"[0-9a-f]{10}")   # 조립한 워크플로우의 sig — 단계의 짧은 해시(sha1 앞 10자: 단계가 바뀔 때만 바뀜)
TASKS_FILE = tmp / "tasks.json"   # 이 검사의 저장 파일(NFM_TASKS)
TASK_PATH = re.compile(r"/api/tasks(/u_[0-9a-f]{8})?$")   # 쓰기 요청(POST /api/tasks · PUT/DELETE /api/tasks/{key}) — /api/tasks.js 는 아님
bodies = []   # /workflow 가 보낸 저장 몸(POST · PUT) — 합집합 stages 를 보내지 않는지 본다


def body_ok(b):
    """저장 몸 — stages(합집합)가 없고, assign 이 있으면 그 키는 source · target(· llm)뿐."""
    return "stages" not in b and set(b.get("assign") or {}) <= {"source", "target", "llm"}


def tasks_api():
    return requests.get(f"{base}/api/tasks", timeout=30).json()


STAGES ="() => [...document.querySelectorAll('#taskSteps > details')].map((d) => ({ id: d.dataset.stage, head: d.querySelector('.dv-phase-no').textContent + ' ' + d.querySelector('summary strong').textContent, count: d.querySelector('.dv-phase-count').textContent, state: d.querySelector('.dv-phase-state').lastChild.textContent, kind: d.querySelector('.dv-phase-state').dataset.kind, off: d.querySelector('[data-task-run]').disabled, steps: [...d.querySelectorAll('ol.dv-flow-steps > li')].map((li) => li.dataset.step) }))"

try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1500, "height": 950})
        wf = ctx.new_page()
        wf.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        wf.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)

        def on_dialog(d):
            dialogs.append(d.message)
            d.accept()
        wf.on("dialog", on_dialog)
        wf.on("request", lambda r: bodies.append((r.method, r.url.split("?", 1)[0], json.loads(r.post_data or "{}")))
              if r.method in ("POST", "PUT") and TASK_PATH.search(r.url.split("?", 1)[0]) else None)

        # ---- ⓪ 저장 파일 — 옛 줄(assign 없이 stages 만 — 2026-11-19 §14 의 꼴)은 옛 뜻 그대로(1단계 LLM 검증·보완 = 원본만: astra P1 ⓐ) · 깨진 파일은 덮지 않는다
        OLD = "u_00c0ffee"
        TASKS_FILE.write_text(json.dumps({"version": 3, "tasks": [{"key": OLD, "name": "옛 줄 — 검토 · 넣기", "desc": "", "source": "plan", "target": "report",
                                                                     "stages": ["stage_review", "stage_fill"], "premise": "", "at": 1}]}, ensure_ascii=False), encoding="utf-8")
        wf.goto(base + "/workflow#overview")
        wf.wait_for_selector("#wfCompose .wf-made-list li")
        old, made = next((t for t in tasks_api()["tasks"] if t["key"] == OLD), {}), wf.evaluate(MADE)
        wt = next((t for t in requests.get(f"{base}/api/workflow", timeout=30).json()["tasks"] if t["job"] == OLD), {})
        unit = {r["role"]: {u["stage"]: u["steps"] for u in r["unit"]} for r in wt.get("roles") or []}
        check("옛 줄(assign 없이 stages 만) — 서버가 채운 assign: 원본 [문서 검토] · 목적 [문서 검토 · 내용 넣기] · llm [원본](옛 뜻) · 목록 · 그 워크플로우의 단위문서 TASK(LLM 검증·보완은 원본 칸에만 — 목적 문서는 헤딩 · 표 분석만)",
              old.get("assign") == {"source": ["stage_review"], "target": ["stage_review", "stage_fill"], "llm": ["source"]}
              and [r[:2] for r in made[0]["roles"]] == [["source", ["문서 검토"]], ["target", ["문서 검토", "내용 넣기"]]]
              and unit.get("source", {}).get("review") == ["heads", "headsLlm"] and unit.get("target", {}).get("review") == ["heads"], [old, made, unit])
        fl0 = wf.evaluate(FLOW, OLD)   # 절은 다이어그램 보기라 감춰져 있다 — 글(textContent)만 본다
        lead0 = wf.evaluate("(k) => (document.querySelector('#' + k + ' > .wf-lead') || {}).textContent || ''", OLD)
        check("옛 줄 — 목적 문서에 「구성 맞추기」 가 없어 구성의 기준이 없음(등록부의 base = null) · 워크플로우 전체 줄(「워크플로우 전체(문서마다가 아니라 한 번)」 — 준비)에 「구성의 기준」 을 안 적음 · "
              "설명을 비워 둠 → 절의 설명 = 등록부가 실제 배정에서 지은 글(descAuto) · 목록 줄에 쓰는 작업의 셈 없음",
              "base" in wt and wt.get("base") is None and wt.get("flow") == [{"stage": "review", "steps": ["files"]}]
              and bool(fl0) and fl0["name"] == FLOW_HEAD and fl0["base"] is None and "구성의 기준" not in fl0["text"]
              and isinstance(old.get("descAuto"), str) and old["descAuto"].strip() != "" and lead0 == old["descAuto"].strip() and made[0]["use"] == [],
              [wt.get("base"), wt.get("flow"), fl0, old.get("descAuto"), lead0, made])
        wf.locator(f"#wfCompose .wf-made-list li[data-task={OLD}] button", has_text="고치기").click()
        wf.wait_for_selector("#wfCompose form.wf-form")
        fo = wf.evaluate(FORM)
        check("옛 줄의 「고치기」 — 폼이 서버의 assign 으로(원본 문서 검토 · 목적 문서 검토 · 내용 넣기) · 「문서 검토」 의 LLM 검증·보완 줄 = 원본 문서(사업계획서) — 저장된 값(칸의 글이 말하는 규칙과 달라도 서버의 값 그대로)",
              fo["units"] == [["source", "원본 문서 — 사업계획서: 문서 검토"], ["target", "목적 문서 — 연차보고서: 문서 검토 › 내용 넣기"]] and not fo["off"] and not fo["lock"]
              and fo["llm"] is not None and fo["llm"][1] == "1" and fo["llm"][0].startswith("「문서 검토」 의 LLM 검증·보완: 원본 문서(사업계획서)") and "저장된 값" in fo["llm"][0], fo)
        wf.fill("#wfCompose input[name=name]", "옛 줄 — 이름만 고침")
        with wf.expect_response(lambda r: r.request.method == "PUT" and bool(TASK_PATH.search(r.url.split("?", 1)[0]))) as rr:
            wf.click("#wfCompose form button[type=submit]")
        wf.wait_for_function("(k) => location.hash === '#' + k", arg=OLD, timeout=20000)
        after = next((t for t in tasks_api()["tasks"] if t["key"] == OLD), {})
        check("옛 줄의 이름만 고쳐 저장 — 200 · 저장 몸 = assign 만(합집합 stages 없음 · 고른 단계가 연 때 그대로라 서버가 준 llm 을 돌려줌) · llm 은 그대로 원본만",
              rr.value.status == 200 and bool(bodies) and body_ok(bodies[-1][2]) and bodies[-1][2].get("assign") == {"source": ["stage_review"], "target": ["stage_review", "stage_fill"], "llm": ["source"]}
              and after.get("name") == "옛 줄 — 이름만 고침" and (after.get("assign") or {}).get("llm") == ["source"], [rr.value.status, bodies[-1:], after])
        check("옛 줄을 지움(API — 하던 작업 없음)", requests.delete(f"{base}/api/tasks/{OLD}", timeout=30).status_code == 200 and tasks_api()["tasks"] == [])
        BROKEN = "{ 깨진 저장 파일"
        TASKS_FILE.write_text(BROKEN, encoding="utf-8")
        wf.goto(base + "/workflow#overview")
        wf.reload()
        wf.wait_for_selector("#wfCompose .wf-compose-broken")
        api_b = tasks_api()
        br = wf.evaluate("""() => { const s = document.getElementById('wfCompose'), n = s.querySelector('.wf-compose-broken'), m = s.querySelector('[data-wf-compose=open]');
          return { note: n.textContent, role: n.getAttribute('role'), list: s.querySelectorAll('.wf-made-list li').length, above: !!m && !!(n.compareDocumentPosition(m) & Node.DOCUMENT_POSITION_FOLLOWING) }; }""")
        wf.click("#wfCompose [data-wf-compose=open]")
        wf.wait_for_selector("#wfCompose form.wf-form")
        wf.fill("#wfCompose input[name=name]", "깨진 파일에 만들기")
        with wf.expect_response(lambda r: r.request.method == "POST" and bool(TASK_PATH.search(r.url.split("?", 1)[0]))) as rr:
            wf.click("#wfCompose form button[type=submit]")
        wf.wait_for_selector("#wfCompose form .wf-err")
        detail = (rr.value.json() or {}).get("detail")
        check("깨진 저장 파일 — API broken · 목록 없음 · 폼 위에 까닭(「저장 파일(tasks.json)을 읽지 못했습니다 …」) · 만들기는 409(서버의 글 그대로 폼에) · 파일은 덮지 않음",
              api_b.get("broken") is True and api_b.get("tasks") == [] and br["list"] == 0 and br["note"].startswith("저장 파일(tasks.json)을 읽지 못했습니다") and br["role"] == "alert" and br["above"]
              and rr.value.status == 409 and isinstance(detail, str) and "tasks.json" in detail and wf.inner_text("#wfCompose form .wf-err") == detail
              and TASKS_FILE.read_text(encoding="utf-8") == BROKEN and body_ok(bodies[-1][2]), [api_b, br, rr.value.status, detail])
        wf.locator("#wfCompose").screenshot(path=str(OUT / "0_broken.png"))
        TASKS_FILE.unlink()

        # ---- ① /workflow 의 「워크플로우 조립」 — 단계 둘만 골라 만들기
        wf.goto(base + "/workflow")
        wf.reload()
        wf.wait_for_selector("#wfNav [data-wf-compose]")
        nav = wf.evaluate(NAV)
        check("목차 — 워크플로우 · 단계 · 도구(화면 말 — ② §15) · 「＋ 워크플로우 조립」 단추 · 조립한 워크플로우 없음 · 깨진 파일 글 없음",
              nav["heads"] == ["워크플로우", "단계", "도구"] and not any("wf-made" in x[2] for x in nav["links"]) and wf.inner_text("#wfNav [data-wf-compose]") == "＋ 워크플로우 조립"
              and wf.locator("#wfCompose").is_visible() and wf.locator("#wfCompose .wf-made-list").count() == 0 and wf.locator("#wfCompose .wf-compose-broken").count() == 0
              and wf.locator("#wfCompose [data-wf-compose=open]").inner_text() == "새 워크플로우 조립", nav["heads"])
        wf.click("#wfNav [data-wf-compose]")
        wf.wait_for_selector("#wfCompose form.wf-form")
        f0 = wf.evaluate("""() => { const f = document.querySelector('#wfCompose form.wf-form');
          return { title: f.querySelector('h3').textContent, fields: [...f.querySelectorAll('.wf-field-name')].map((x) => x.textContent), pairs: [...f.querySelectorAll('select[name=pair] option')].map((o) => o.textContent),
            old: f.querySelectorAll('.wf-stage-opt, input[name=stage]').length,
            focus: document.activeElement === f.querySelector('input[name=name]'), premise: f.querySelector('textarea').placeholder, blocked: [...document.querySelectorAll('#wfCompose .wf-blocked li b')].map((b) => b.textContent) }; }""")
        check("폼 — 「새 워크플로우」 · 이름(포커스) · 한 줄 설명 · 문서 쌍(지금은 사업계획서 → 연차보고서 하나) · 전제(비우면 이관의 전제) · 아직 조립할 수 없는 것 둘 · 「단계 넷 체크」 는 없어짐(문서 역할 × 단계 표로)",
              f0["title"] == "새 워크플로우" and f0["fields"] == ["이름", "한 줄 설명", "문서 쌍(원본 → 목적)", "전제(선택)"] and f0["pairs"] == ["사업계획서 → 연차보고서"] and f0["focus"] and f0["old"] == 0
              and "사업계획서 → 연차보고서 이관" in f0["premise"] and len(f0["blocked"]) == 2 and "취합형" in f0["blocked"][1], f0)
        # 문서 역할 × 단계 표(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) — 칸은 서버(GET /api/tasks 의 stages[].cells)가 정한다
        cells = {st["id"]: st.get("cells") or {} for st in requests.get(f"{base}/api/tasks", timeout=30).json()["stages"]}   # 없으면(옛 서버) 아래 검사가 떨어진다
        ctext = lambda sid: ((cells.get(sid) or {}).get("source") or {}).get("text")   # noqa: E731 — 원본 칸의 서버 글
        f1 = wf.evaluate(FORM)
        rows = {r["id"]: r for r in f1["rows"]}
        modes = {i: {k: v["mode"] for k, v in r["cells"].items()} for i, r in rows.items()}
        check("문서 역할 × 단계 표 — 열 = 원본 문서 — 사업계획서 · 목적 문서 — 연차보고서 · 행 = 일반 단계 넷(차례 · 그 단계의 줄들) · 칸 = 서버의 cells(원본: 문서 검토만 체크 · 구성 맞추기 · 내용 넣기는 따라오는 글 · 문서 정리는 고를 수 없음 / 목적: 넷 모두 체크)",
              f1["legend"].startswith("문서마다 단위문서 TASK") and f1["head"] == ["단계", "원본 문서 — 사업계획서", "목적 문서 — 연차보고서"]
              and [r["id"] for r in f1["rows"]] == list(STAGE_IDS) and [r["name"] for r in f1["rows"]] == ["1. 문서 검토", "2. 구성 맞추기", "3. 내용 넣기", "4. 문서 정리"]
              and rows["stage_fit"]["steps"] == "구성 불러오기(선택) › 프로젝트 구성 확정 › 프로젝트 구성 반영 › 다시 문서 검토 › 다시 문서 검토(LLM)"
              and modes == {i: {k: v["mode"] for k, v in c.items()} for i, c in cells.items()}
              and [modes[i]["source"] for i in STAGE_IDS] == ["pick", "follow", "follow", "no"] and all(modes[i]["target"] == "pick" for i in STAGE_IDS), [f1, cells])
        check("새 워크플로우의 처음 값 — 원본 = 문서 검토 · 목적 = 넷 모두(체크 이름 assign-source · assign-target) · 따라오는 칸은 목적이 골랐으니 그 글 · 고를 수 없는 칸은 까닭(원본은 바꾸지 않습니다) · "
              "표 아래 「직접 고른 단계」 줄 · 새 폼에는 LLM 검증·보완 줄 없음(칸의 글이 규칙) · 경고 없음 · 잠금 없음",
              rows["stage_review"]["cells"]["source"]["box"] == ["assign-source", "stage_review", True] and all(rows[i]["cells"]["target"]["box"] == ["assign-target", i, True] for i in STAGE_IDS)
              and all(rows[i]["cells"]["source"]["box"] is None for i in STAGE_IDS[1:])
              and rows["stage_fit"]["cells"]["source"]["text"] == ctext("stage_fit") != "" and rows["stage_fill"]["cells"]["source"]["text"] == ctext("stage_fill") != ""
              and rows["stage_clean"]["cells"]["source"]["text"] == ctext("stage_clean") == "원본은 바꾸지 않습니다" and f1["sumHead"] == "직접 고른 단계" and f1["llm"] is None
              and f1["units"] == [["source", "원본 문서 — 사업계획서: 문서 검토"], ["target", "목적 문서 — 연차보고서: 문서 검토 › 구성 맞추기 › 내용 넣기 › 문서 정리"]] and f1["warn"] == ""   # 단계 사이 「 › 」(= 다음)
              and not f1["off"] and not f1["lock"], f1)
        wf.uncheck("#wfCompose input[name=assign-target][value=stage_fit]")
        f2 = wf.evaluate(FORM)
        r2 = {r["id"]: r for r in f2["rows"]}
        warn_api = (tasks_api().get("warn") or {}).get("fillNoFit")
        check("목적 문서의 「구성 맞추기」 를 끄면 — 원본 칸의 따라오는 글이 「—」(내용 넣기의 글은 그대로) · 목적 줄에서 빠짐 · 경고(막지 않음 — 저장 단추는 켜짐) = "
              "「목적 문서에 「구성 맞추기」 없이 「내용 넣기」 — 」 + 서버의 warn.fillNoFit(「목적 문서에 구조 반영 기록이 있고 두 문서의 프로젝트 구성 값이 같아야 자리 연결이 섭니다(…)」)",
              r2["stage_fit"]["cells"]["source"]["text"] == "—" and r2["stage_fill"]["cells"]["source"]["text"] == ctext("stage_fill")
              and f2["units"][1] == ["target", "목적 문서 — 연차보고서: 문서 검토 › 내용 넣기 › 문서 정리"] and warn_api == FILL_NO_FIT and f2["warn"] == WARN_HEAD + FILL_NO_FIT
              and not wf.is_disabled("#wfCompose form button[type=submit]"), [f2, warn_api])
        wf.check("#wfCompose input[name=assign-target][value=stage_fit]")
        wf.fill("#wfCompose input[name=name]", "구성 맞추고 넣기")
        wf.fill("#wfCompose input[name=desc]", "정리는 하지 않습니다")
        wf.uncheck("#wfCompose input[name=assign-source][value=stage_review]")
        wf.uncheck("#wfCompose input[name=assign-target][value=stage_review]")
        wf.uncheck("#wfCompose input[name=assign-target][value=stage_clean]")
        f3 = wf.evaluate(FORM)
        check("원본의 문서 검토를 끄고 목적에 구성 맞추기 · 내용 넣기만 — 줄: 원본 「—」 · 목적 「구성 맞추기 › 내용 넣기」 · 따라오는 글은 그대로 · 경고 없음",
              f3["units"] == [["source", "원본 문서 — 사업계획서: —"], ["target", "목적 문서 — 연차보고서: 구성 맞추기 › 내용 넣기"]] and f3["warn"] == ""
              and {r["id"]: r["cells"]["source"]["text"] for r in f3["rows"]}["stage_fit"] == ctext("stage_fit"), f3)
        wf.locator("#wfCompose").screenshot(path=str(OUT / "1_form.png"))
        wf.click("#wfCompose form button[type=submit]")
        wf.wait_for_function("() => /^#u_[0-9a-f]{8}$/.test(location.hash)", timeout=20000)
        key = wf.evaluate("() => location.hash.slice(1)")
        wf.wait_for_function("(k) => !!document.getElementById(k)", arg=key)
        t0 = tasks_api()["tasks"][0]
        b0 = bodies[-1] if bodies else ("", "", {})
        check("저장 몸 = assign 만(POST — 합집합 stages 없음 · 새 워크플로우라 llm 도 안 보냄: 서버가 정함) · 저장한 assign — 원본 [](문서 검토를 끔) · 목적 [구성 맞추기 · 내용 넣기](일반 차례) · llm [](문서 검토 없음) · 묶음 = 그것",
              b0[0] == "POST" and body_ok(b0[2]) and b0[2].get("assign") == {"source": [], "target": ["stage_fit", "stage_fill"]} and (b0[2].get("source"), b0[2].get("target")) == ("plan", "report")
              and t0["key"] == key and t0.get("assign") == {"source": [], "target": ["stage_fit", "stage_fill"], "llm": []} and t0["groups"] == ["frame", "map"] and t0.get("inUse") == 0, [b0, t0])
        check("GET /api/tasks 의 그 워크플로우(3차 계약) — sig(단계의 짧은 해시 10자) · descAuto(실제 배정에서 지은 한 줄) · 쓰는 작업 없음(inUse 0 · listed 0 · editWhy · deleteWhy = null · uses [] · usesMore 0)",
              bool(SIG.fullmatch(str(t0.get("sig")))) and isinstance(t0.get("descAuto"), str) and t0["descAuto"].strip() != "" and t0.get("listed") == 0
              and "editWhy" in t0 and t0["editWhy"] is None and "deleteWhy" in t0 and t0["deleteWhy"] is None and t0.get("uses") == [] and t0.get("usesMore") == 0, t0)
        wf.click("#wfViewList")
        sec = wf.evaluate("""(k) => { const s = document.getElementById(k);
          return { h2: s.querySelector('h2').textContent, lead: s.querySelector('.wf-lead').textContent, io: [...s.querySelectorAll(':scope > .wf-io dt')].map((d) => d.textContent),
            stages: [...s.querySelectorAll('.wf-stage')].map((g) => [g.dataset.stage, g.querySelector('.wf-stage-no').textContent, g.querySelector('h3').textContent, (g.querySelector('.wf-stage-module a') || {}).textContent, [...g.querySelectorAll('.wf-step')].map((d) => d.dataset.step)]) }; }""", key)
        check("만든 워크플로우의 절 — 「조립한 워크플로우」 꼬리표 · 설명 · 조립 · 전제(이관의 전제를 씀) · 고른 단계만: 1단계 구성 맞추기(준비 포함) · 2단계 내용 넣기 — 묶음마다 「조립한 단계」 링크",
              sec["h2"] == "워크플로우구성 맞추고 넣기조립한 워크플로우" and sec["lead"] == "정리는 하지 않습니다" and sec["io"][:2] == ["조립", "전제"]
              and [x[:4] for x in sec["stages"]] == [["frame", "1단계", "구성 맞추기", "구성 맞추기"], ["map", "2단계", "내용 넣기", "내용 넣기"]]
              and sec["stages"][0][4] == ["files", "configLoad", "config", "division", "reheads", "reheadsLlm"] and sec["stages"][1][4][:1] == ["link"], sec)
        # 조립한 워크플로우의 시작 점검(등록부가 그 정의로 짓는다 — 3차) — 그 파일(tasks/<job>.md)이 없어 doc 이 "" 이다: 빈 경로를 적지 않는다(통합 확인)
        ent = wf.evaluate("""(k) => { const s = document.getElementById(k), head = s.querySelector('.wf-entry-head');
          return head && { text: head.textContent, code: head.querySelectorAll('code').length, groups: [...s.querySelectorAll('.wf-entry-group')].map((g) => g.dataset.when) }; }""", key)
        went = next(t for t in requests.get(f"{base}/api/workflow", timeout=30).json()["tasks"] if t["job"] == key).get("entry") or []
        check("조립한 워크플로우의 「시작 점검」 — 등록부가 그 정의로 지은 때마다 묶음 그대로 · 그 파일이 없어 문서 경로를 적지 않음(빈 경로 없음)",
              bool(went) and bool(ent) and ent["text"].startswith("시작 점검") and ent["code"] == 0 and "워크플로우 상세 문서" not in ent["text"] and "TASK 문서" not in ent["text"] and ent["groups"] == [g["when"] for g in went],
              [ent, [g["when"] for g in went]])
        # 그 TASK 절의 「문서마다 단위문서 TASK」 표(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) — 등록부(custom())의 roles · unit 그대로
        docs = wf.evaluate("""(k) => { const t = document.querySelector('#' + k + ' table.wf-docs'), f = document.querySelector('#' + k + ' .wf-docs-flow'); return t && { cols: [...t.querySelectorAll('thead th')].map((x) => x.textContent),
          rows: [...t.querySelectorAll('tbody tr')].map((tr) => [tr.dataset.stage, Object.fromEntries([...tr.querySelectorAll('td[data-role]')].map((td) => [td.dataset.role, [...td.querySelectorAll('a.wf-docs-step')].map((a) => a.getAttribute('href').split('--').pop())]))]),
          flow: f && { groups: [...f.querySelectorAll('.wf-docs-flow-group')].map((g) => [g.dataset.stage, [...g.querySelectorAll('a.wf-docs-step')].map((a) => a.getAttribute('href').split('--').pop())]), base: (f.querySelector('.wf-docs-base') || {}).textContent || '' } }; }""", key)
        wt = next(t for t in requests.get(f"{base}/api/workflow", timeout=30).json()["tasks"] if t["job"] == key)
        want = [[g["id"], {r["role"]: next((u["steps"] for u in r["unit"] if u["stage"] == g["id"]), []) for r in wt.get("roles") or []}] for g in wt["stages"]]
        fl1 = wf.evaluate(FLOW, key)   # 목록 보기 — 절이 보여 CSS 의 이음 기호까지 읽힌다
        check("그 워크플로우 절의 「문서마다 단위문서 TASK」 — 열 = 원본 문서 — 사업계획서 · 목적 문서 — 연차보고서(서버의 title) · 행 = 고른 묶음(구성 맞추기 · 내용 넣기) · 칸 = 등록부의 단위문서 TASK · "
              "원본은 문서 검토를 안 골라 헤딩 · 표 분석이 없음 · 표 아래 줄 = 「워크플로우 전체(문서마다가 아니라 한 번): 1단계 구성 맞추기(준비 › 구성 불러오기 › 프로젝트 구성 확정) — 구성의 기준: 원본 문서(사업계획서)」"
              "(목적 문서에 「구성 맞추기」 가 있어 base = source · 단계 사이 「 › 」 · 단계는 괄호 안)",
              bool(docs) and docs["cols"] == ["단계", "원본 문서 — 사업계획서", "목적 문서 — 연차보고서"] and docs["rows"] == want and [r[0] for r in docs["rows"]] == ["frame", "map"]
              and not any(k in r[1].get(role, []) for r in docs["rows"] for role in ("source", "target") for k in ("heads", "headsLlm", "files", "configLoad", "config"))
              and wt.get("flow") == [{"stage": "frame", "steps": ["files", "configLoad", "config"]}] and wt.get("base") == "source"
              and bool(docs["flow"]) and docs["flow"]["groups"] == [["frame", ["files", "configLoad", "config"]]] and docs["flow"]["base"] == " — 구성의 기준: 원본 문서(사업계획서)"
              and bool(fl1) and fl1["name"] == FLOW_HEAD and fl1["line"] == f"{FLOW_HEAD}: 1단계 구성 맞추기(준비 › 구성 불러오기 › 프로젝트 구성 확정) — 구성의 기준: 원본 문서(사업계획서)",
              [docs, want, wt.get("flow"), wt.get("base"), fl1])
        nav, made = wf.evaluate(NAV), wf.evaluate(MADE)
        used = wf.evaluate("() => Object.fromEntries(['stage_review', 'stage_fit', 'stage_fill', 'stage_clean'].map((id) => [id, [...document.querySelectorAll('#common-' + id + ' .wf-io .wf-chip')].map((a) => a.textContent)]))")
        check("목차에 그 워크플로우(「조립」 표시 · 붙박이 워크플로우 뒤) · 「워크플로우 조립」 절의 목록(문서마다 고른 단계 — 원본: — · 목적: 구성 맞추기 · 내용 넣기 · 고치기 · 지우기) · 단계 절의 「조립한 워크플로우」 에 더해짐(고른 단계에만)",
              [f"#{key}", "구성 맞추고 넣기", "wf-made"] in nav["links"] and nav["links"][8][0] == f"#{key}" and len(made) == 1 and made[0]["key"] == key and made[0]["name"] == "구성 맞추고 넣기"
              and [r[:2] for r in made[0]["roles"]] == [["source", []], ["target", ["구성 맞추기", "내용 넣기"]]] and made[0]["roles"][0][2] == "원본:—" and made[0]["btns"] == [["고치기", False], ["지우기", False]]
              and made[0]["use"] == [] and made[0]["tips"] == ["이름 · 설명 · 고른 단계 · 전제를 고칩니다", "이 워크플로우를 지웁니다(단계 · 도구는 그대로)"]   # 쓰는 작업이 없어 셈 없음 · 까닭 없음
              and used["stage_fit"] == ["사업계획서 → 연차보고서 이관", "구성 맞추고 넣기"] and used["stage_review"] == ["사업계획서 → 연차보고서 이관"], [nav["links"][8], made, used])
        wf.screenshot(path=str(OUT / "1_made.png"))

        # ---- ② 같은 이름은 못 만든다(서버의 까닭이 폼에) · 「고치기」
        wf.click("#wfNav [data-wf-compose]")
        wf.wait_for_selector("#wfCompose form.wf-form")
        wf.fill("#wfCompose input[name=name]", "구성 맞추고 넣기")
        wf.click("#wfCompose form button[type=submit]")
        wf.wait_for_selector("#wfCompose form .wf-err")
        err = wf.inner_text("#wfCompose form .wf-err")
        check("같은 이름 — 만들지 않고 폼에 서버의 까닭(「…는 이미 있는 워크플로우 이름입니다」 — 「TASK」 라 하지 않음) · 폼의 값은 그대로",
              "이미 있는 워크플로우 이름입니다" in err and "TASK" not in err and "구성 맞추고 넣기" in err and wf.input_value("#wfCompose input[name=name]") == "구성 맞추고 넣기"
              and len(tasks_api()["tasks"]) == 1 and body_ok(bodies[-1][2]), err)
        r404 = [requests.put(f"{base}/api/tasks/u_0000beef", json={"name": "없는 것"}, timeout=30), requests.delete(f"{base}/api/tasks/u_0000beef", timeout=30)]
        check("없는 키 — 고치기 · 지우기 모두 404 「그런 워크플로우가 없습니다」(서버의 거절 글은 「워크플로우」)",
              [r.status_code for r in r404] == [404, 404] and all((r.json() or {}).get("detail") == "그런 워크플로우가 없습니다" for r in r404), [(r.status_code, r.text[:200]) for r in r404])
        # 원본 문서를 쓰는 단계가 없는 배정(원본 없음 · 목적에 구성 맞추기 · 내용 넣기 없음) — 서버가 400(2차 계약) · 그 글이 폼에 그대로
        wf.fill("#wfCompose input[name=name]", "원본을 안 쓰는 배정")
        for sel in ("assign-source][value=stage_review", "assign-target][value=stage_fit", "assign-target][value=stage_fill"):
            wf.uncheck(f"#wfCompose input[name={sel}]")
        with wf.expect_response(lambda r: r.request.method == "POST" and bool(TASK_PATH.search(r.url.split("?", 1)[0]))) as rr:
            wf.click("#wfCompose form button[type=submit]")
        wf.wait_for_selector("#wfCompose form .wf-err")
        ns_units = wf.evaluate(FORM)["units"]
        check("원본 문서를 쓰는 단계가 없는 배정(원본 — · 목적 문서 검토 · 문서 정리) — 서버가 400 · 그 글(「원본 문서를 쓰는 단계가 없습니다 — …」)이 폼에 그대로 · 만들지 않음 · 폼의 값은 그대로",
              rr.value.status == 400 and (rr.value.json() or {}).get("detail") == NO_SOURCE and wf.inner_text("#wfCompose form .wf-err") == NO_SOURCE and len(tasks_api()["tasks"]) == 1
              and ns_units == [["source", "원본 문서 — 사업계획서: —"], ["target", "목적 문서 — 연차보고서: 문서 검토 › 문서 정리"]]
              and bodies[-1][2].get("assign") == {"source": [], "target": ["stage_review", "stage_clean"]}, [rr.value.status, wf.inner_text("#wfCompose form .wf-err"), ns_units])
        wf.locator("#wfCompose form button", has_text="취소").click()
        wf.locator(f"#wfCompose .wf-made-list li[data-task={key}] button", has_text="고치기").click()
        wf.wait_for_selector("#wfCompose form.wf-form")
        e0 = wf.evaluate("""() => { const f = document.querySelector('#wfCompose form.wf-form'), on = (n) => [...f.querySelectorAll('input[name=' + n + ']')].filter((i) => i.checked).map((i) => i.value);
          return { title: f.querySelector('h3').textContent, name: f.querySelector('input[name=name]').value, pairOff: f.querySelector('select[name=pair]').disabled, source: on('assign-source'), target: on('assign-target'),
            units: [...f.querySelectorAll('.wf-assign-units > li')].map((li) => li.textContent), save: f.querySelector('button[type=submit]').textContent,
            llm: !f.querySelector('.wf-assign-llm').hidden, lock: !!f.querySelector('.wf-assign-lock'), off: f.querySelector('fieldset.wf-stage-pick').disabled }; }""")
        check("「고치기」 — 그 워크플로우의 값(저장한 assign)으로 폼: 원본 체크 없음 · 목적 구성 맞추기 · 내용 넣기 · 직접 고른 단계 줄 · 문서 쌍은 못 고침 · 단추 「고친 것 저장」 · 문서 검토가 없어 LLM 줄 없음 · 하던 작업이 없어 잠금 없음",
              e0 == {"title": "「구성 맞추고 넣기」 고치기", "name": "구성 맞추고 넣기", "pairOff": True, "source": [], "target": ["stage_fit", "stage_fill"],
                     "units": ["원본 문서 — 사업계획서: —", "목적 문서 — 연차보고서: 구성 맞추기 › 내용 넣기"], "save": "고친 것 저장", "llm": False, "lock": False, "off": False}, e0)
        wf.fill("#wfCompose input[name=name]", "구성 · 넣기 · 정리")
        wf.check("#wfCompose input[name=assign-target][value=stage_clean]")
        wf.click("#wfCompose form button[type=submit]")
        wf.wait_for_function("(k) => { const s = document.getElementById(k); return !!s && s.querySelectorAll('.wf-stage').length === 3; }", arg=key, timeout=20000)
        t1, b1 = tasks_api()["tasks"][0], bodies[-1]
        check("고친 것이 저장됨(PUT — 저장 몸 = assign 만 · 고른 단계를 바꿔 llm 은 안 보냄) — 이름 · 목적 문서의 단계 셋(차례는 일반 단계의 차례) · 원본은 그대로 없음 · 키는 그대로",
              b1[0] == "PUT" and b1[1].endswith(f"/api/tasks/{key}") and body_ok(b1[2]) and b1[2].get("assign") == {"source": [], "target": ["stage_fit", "stage_fill", "stage_clean"]}
              and t1["key"] == key and t1["name"] == "구성 · 넣기 · 정리" and t1.get("assign") == {"source": [], "target": ["stage_fit", "stage_fill", "stage_clean"], "llm": []}
              and t1["groups"] == ["frame", "map", "clean"]
              and bool(SIG.fullmatch(str(t1.get("sig")))) and t1.get("sig") != t0.get("sig"), [b1, t1, t0.get("sig")])   # 단계가 바뀌어 sig 도 바뀜(3차 계약)
        # cells 를 주지 않는 서버(옛 서버 — 흉내: GET /api/tasks 의 stages[].cells 를 지운다) — 폼을 열지 않는다(옛 서버는 assign 을 몰라 고른 배정을 잃는다)
        nc = ctx.new_page()
        nc.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        def strip_cells(route):
            resp = route.fetch()
            data = resp.json()
            for st in data.get("stages") or []:
                st.pop("cells", None)
            route.fulfill(response=resp, json=data)
        nc.route(re.compile(r"/api/tasks(\?[^/]*)?$"), strip_cells)
        nc.goto(base + "/workflow#overview")
        nc.wait_for_selector("#wfCompose .wf-made-list li")
        nc.click("#wfNav [data-wf-compose]")
        nc.wait_for_timeout(400)
        off = nc.evaluate("""(k) => { const s = document.getElementById('wfCompose'), p = s.querySelector('.wf-compose-off');
          return { off: p && p.textContent, form: !!s.querySelector('form'), open: !!s.querySelector('[data-wf-compose=open]'), edit: [...s.querySelectorAll('.wf-made-list li button')].map((b) => [b.textContent, b.disabled, b.title]),
            sec: (document.querySelector('#' + k + ' .wf-io button[data-wf-compose]') || {}).disabled }; }""", key)
        check("cells 를 주지 않는 서버 — 「조립은 서버를 다시 켠 뒤에 쓸 수 있습니다」 · 폼도 「새 워크플로우 조립」 도 없음 · 목차의 「＋ 워크플로우 조립」 을 눌러도 폼이 안 열림 · 목록의 「고치기」 · 절의 「고치기」 는 꺼짐(까닭은 풍선 도움말)",
              off["off"] == NO_COMPOSE and not off["form"] and not off["open"] and off["edit"][0][:2] == ["고치기", True] and off["edit"][0][2] == NO_COMPOSE and off["sec"] is True, off)
        nc.close()

        # ---- ③ 고치는 사이 그 워크플로우로 작업이 시작됨 → 단계를 바꾼 저장은 409(서버의 글 그대로 · 폼이 잠기고 「복제」) — 그 작업으로 앱(카드 · 작업 개요 · 한 번에 진행 · 대시보드)
        wf.goto(base + "/workflow#overview")
        wf.reload()
        wf.wait_for_selector(f"#wfCompose .wf-made-list li[data-task={key}]")
        wf.locator(f"#wfCompose .wf-made-list li[data-task={key}] button", has_text="고치기").click()
        wf.wait_for_selector("#wfCompose form.wf-form")
        small = ROOT / "samples" / "기술수요조사서.hwpx"
        a, c = upload(small), upload(small)   # a = 연차보고서 칸(목적) · c = 사업계획서 칸(원본 — 국가R&D 양식이 아니라 값이 없다)
        for wid, file in ((a, "report"), (c, "plan")):
            r = requests.put(f"{base}/api/works/{wid}/task", json={"kind": "rnd", "file": file, "job": key, "project": "조립 시험"}, timeout=30)
            check(f"서버가 조립한 워크플로우의 키를 작업의 TASK 로 받음({file})", r.status_code == 200 and r.json()["task"]["job"] == key, r.status_code)
        wf.uncheck("#wfCompose input[name=assign-target][value=stage_clean]")   # 연 폼(하던 작업 0 일 때 연 것)에서 단계를 바꿔 저장
        with wf.expect_response(lambda r: r.request.method == "PUT" and bool(TASK_PATH.search(r.url.split("?", 1)[0]))) as rr:
            wf.click("#wfCompose form button[type=submit]")
        wf.wait_for_selector("#wfCompose form .wf-err")
        wf.wait_for_selector("#wfCompose .wf-assign-lock", timeout=10000)
        detail, fr, t1b = (rr.value.json() or {}).get("detail"), wf.evaluate(FORM), tasks_api()["tasks"][0]
        check("고치는 사이 작업 둘이 그 워크플로우를 지금 워크플로우로 둠 — 단계를 바꾼 저장은 409 · 서버의 글(「… 하던 작업이 2개 있어 단계를 바꿀 수 없습니다 — 「복제」 …」 = editWhy)이 폼에 그대로 · "
              "폼이 잠김(단계 표 꺼짐 · 저장된 단계로 돌아감 · 잠금 글 = editWhy 그대로 · 「복제」) · 배정은 그대로 · inUse 2 · listed 0 · deleteWhy(쓰는 작업 2개)",
              rr.value.status == 409 and isinstance(detail, str) and "하던 작업이 2개" in detail and "복제" in detail and wf.inner_text("#wfCompose form .wf-err") == detail
              and t1b.get("editWhy") == detail and fr["off"] and fr["boxesOff"] and fr["copy"] and fr["lock"] == detail + "복제"
              and fr["units"][1] == ["target", "목적 문서 — 연차보고서: 구성 맞추기 › 내용 넣기 › 문서 정리"]
              and t1b.get("assign") == {"source": [], "target": ["stage_fit", "stage_fill", "stage_clean"], "llm": []} and t1b.get("inUse") == 2 and t1b.get("listed") == 0
              and t1b.get("deleteWhy") == DEL_WHY.format(n=2), [rr.value.status, detail, fr, t1b])
        wf.locator("#wfCompose").screenshot(path=str(OUT / "3_conflict.png"))
        wf.locator("#wfCompose form button", has_text="취소").click()
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("dialog", on_dialog)
        page.goto(base)
        page.wait_for_selector("#taskCards .task-card")
        card = page.evaluate("(k) => { const b = document.querySelector('#taskCards [data-task=\"' + k + '\"]'); return b && { text: b.textContent, icon: b.querySelector('use').getAttribute('href'), cat: TASK_CATALOG[k] && { name: TASK_CATALOG[k].name, files: TASK_CATALOG[k].files, groups: TASK_CATALOG[k].groups, custom: TASK_CATALOG[k].custom }, relay: taskIsRelay(k), job: taskName('job', k) }; }", key)
        check("시작 화면 — 그 TASK 의 카드(이관의 로고) · 화면의 TASK 목록에 올라 있음(문서 칸 = 사업계획서 · 연차보고서 · 묶음 = 고른 것)",
              bool(card) and "구성 · 넣기 · 정리" in card["text"] and card["icon"] == "#taskIcon-plan_to_report" and card["cat"] == {"name": "구성 · 넣기 · 정리", "files": ["plan", "report"], "groups": ["frame", "map", "clean"], "custom": True}
              and card["relay"] and card["job"] == "구성 · 넣기 · 정리", card)
        page.screenshot(path=str(OUT / "3_home.png"))
        page.evaluate("(id) => { location.hash = '#w=' + id; }", a)
        page.reload()
        page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=a, timeout=300000)
        page.click("#toolTabTask")
        page.wait_for_selector("#taskStage")
        page.wait_for_function(f"() => {{ const s = ({STAGES})(); return s.length === 3 && s[0].state.includes('프로젝트 구성'); }}", timeout=60000)
        st = page.evaluate(STAGES)
        check("「작업 개요」 — 고른 묶음 셋만(문서 검토 없음) · 번호는 1부터 · 맨 앞 묶음(구성 맞추기)이 준비를 가짐 · 단계는 일반 단계 그대로",
              [(s["id"], s["head"]) for s in st] == [("frame", "1단계 구성 맞추기"), ("map", "2단계 내용 넣기"), ("clean", "3단계 문서 정리")] and page.locator("#taskStageR").count() == 0
              and st[0]["steps"] == ["files", "config", "division", "reheads", "reheadsLlm"] and st[1]["steps"] == ["link", "plan", "apply", "later"] and st[2]["steps"] == ["guide"]
              and st[0]["count"] == "0/4 완료" and st[0]["state"].startswith("다음: 프로젝트 구성 확정") and not st[0]["off"] and st[1]["state"] == "1단계 「구성 맞추기」 완료 후 진행" and st[1]["off"], st)
        chain = page.evaluate("() => [...document.querySelectorAll('#taskChain [data-task-chain]')].map((b) => [b.dataset.taskChain, b.textContent, b.hidden])")
        check("이어서 한 번에 — 이 TASK 의 묶음 범위(1→2단계 · 1→3단계)", chain == [["map", "1→2단계", False], ["clean", "1→3단계", False]], chain)
        page.locator("#panel").screenshot(path=str(OUT / "3_panel.png"))
        n = len(dialogs)
        page.click("#taskStage [data-task-run]")   # 1단계 = 구성 맞추기 — 값이 없는(읽을 수도 없는) 사업계획서라 구성 확정에서 멈춘다(이관과 같은 실행)
        page.wait_for_function("() => !taskRun && !!taskRunLast", timeout=120000)
        last, st = page.evaluate("() => taskRunLast"), page.evaluate(STAGES)
        check("「한 번에 진행」 — 그 묶음의 단계로 돎: 구성 확정에서 멈춤(확인 창 없음) · 멈춘 글의 묶음 번호는 이 TASK 의 것(1단계 「구성 맞추기」)",
              len(dialogs) == n and not last["ok"] and last["stage"] == "frame" and last["key"] == "config" and "읽지 못했습니다" in last["text"] and "1단계 「구성 맞추기」 의 프로젝트 구성 입력 칸" in last["text"]
              and st[0]["kind"] == "halt", [last, st[0]])
        page.click("#tabDash")
        page.wait_for_function("() => document.querySelectorAll('#paneDash .dash-node').length > 0", timeout=60000)
        dash = page.evaluate("() => ({ groups: [...document.querySelectorAll('#paneDash .dash-group-head, #paneDash .dash-ghead')].map((g) => g.textContent), nodes: [...document.querySelectorAll('#paneDash .dash-node')].map((n) => n.dataset.key), title: (document.querySelector('#paneDash .dash-title b') || {}).textContent })")
        check("대시보드 — 그 TASK 의 이름 · 고른 묶음의 단계만(등록부가 조립한 것)", dash["title"] == "구성 · 넣기 · 정리" and dash["nodes"][:6] == ["files", "configLoad", "config", "division", "reheads", "reheadsLlm"]
              and "heads" not in dash["nodes"] and dash["nodes"][-1] == "guide", dash)
        page.locator("#paneDash").screenshot(path=str(OUT / "3_dash.png"))

        # ---- ③-2 원본의 문서 검토를 끄고 목적 문서에 문서 검토 + 구성 맞추기(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) — 1단계에 LLM 검증·보완 줄이 없다:
        #      원본은 문서 검토를 안 골랐고, 목적 문서의 LLM 검증·보완은 구성을 맞춘 뒤 「다시 문서 검토(LLM)」 에서 한다(헤딩 · 표 분석 = 목적 문서만 · 할 문서가 없는 단계는 서지 않음)
        wf.bring_to_front()
        wf.goto(base + "/workflow#overview")
        wf.reload()
        wf.wait_for_selector("#wfNav [data-wf-compose]")
        wf.click("#wfNav [data-wf-compose]")
        wf.wait_for_selector("#wfCompose form.wf-form")
        wf.fill("#wfCompose input[name=name]", "목적만 검토 · 구성")
        wf.uncheck("#wfCompose input[name=assign-source][value=stage_review]")
        wf.uncheck("#wfCompose input[name=assign-target][value=stage_fill]")
        wf.uncheck("#wfCompose input[name=assign-target][value=stage_clean]")
        f4 = wf.evaluate(FORM)
        wf.click("#wfCompose form button[type=submit]")
        wf.wait_for_function("(k) => /^#u_[0-9a-f]{8}$/.test(location.hash) && location.hash.slice(1) !== k", arg=key, timeout=20000)
        key2 = wf.evaluate("() => location.hash.slice(1)")
        wf.wait_for_function("(k) => !!document.getElementById(k)", arg=key2)
        t2 = next((t for t in requests.get(f"{base}/api/tasks", timeout=30).json()["tasks"] if t["key"] == key2), {})
        diag2 = wf.evaluate("() => ({ title: (document.querySelector('#wfDiagram h2') || {}).textContent || '', lead: (document.querySelector('#wfDiagram > .wf-lead') || {}).textContent || '' })")   # 저장 뒤 그 워크플로우의 다이어그램
        wf.click("#wfViewList")
        s2 = wf.evaluate("""(k) => ({ lead: (document.querySelector('#' + k + ' > .wf-lead') || {}).textContent || '', stages: [...document.getElementById(k).querySelectorAll('.wf-stage')].map((g) => [g.dataset.stage, [...g.querySelectorAll('.wf-step')].map((d) => d.dataset.step)]),
          llm: document.querySelectorAll('#' + k + ' .wf-docs a.wf-docs-step[href$="--headsLlm"]').length,
          heads: Object.fromEntries([...document.querySelectorAll('#' + k + ' .wf-docs tr[data-stage=review] td[data-role]')].map((td) => [td.dataset.role, [...td.querySelectorAll('a.wf-docs-step')].map((a) => a.getAttribute('href').split('--').pop())])) })""", key2)
        check("원본의 문서 검토를 끄고 목적에 문서 검토 + 구성 맞추기 — 폼의 줄 · 저장한 assign · 그 TASK 절의 1단계(문서 검토)에 LLM 검증·보완 줄이 없음(목적 문서는 2단계 「다시 문서 검토(LLM)」) · 표: 헤딩 · 표 분석은 목적 칸에만",
              f4["units"] == [["source", "원본 문서 — 사업계획서: —"], ["target", "목적 문서 — 연차보고서: 문서 검토 › 구성 맞추기"]] and f4["warn"] == ""
              and t2.get("assign") == {"source": [], "target": ["stage_review", "stage_fit"], "llm": []} and t2.get("groups") == ["review", "frame"] and body_ok(bodies[-1][2])
              and [x[0] for x in s2["stages"]] == ["review", "frame"] and s2["stages"][0][1] == ["files", "heads"] and "reheadsLlm" in s2["stages"][1][1] and s2["llm"] == 0
              and "heads" in s2["heads"].get("target", []) and "heads" not in s2["heads"].get("source", []), [f4, t2, s2])
        wt2 = next((t for t in requests.get(f"{base}/api/workflow", timeout=30).json()["tasks"] if t["job"] == key2), {})
        fl2 = wf.evaluate(FLOW, key2)
        check("설명을 비워 둔 조립 — 절 · 다이어그램의 설명 = 등록부가 실제 배정에서 지은 글(descAuto — 「내용 넣기」 가 없어 「옮깁니다」 라 하지 않음) · "
              "목적 문서에 「구성 맞추기」 가 있어 구성의 기준 = 원본(base source — 워크플로우 전체 줄 「1단계 문서 검토(준비) › 2단계 구성 맞추기(구성 불러오기 › 프로젝트 구성 확정) — 구성의 기준: 원본 문서(사업계획서)」)",
              isinstance(t2.get("descAuto"), str) and t2["descAuto"].strip() != "" and "옮깁니다" not in t2["descAuto"] and s2["lead"] == t2["descAuto"].strip() == diag2["lead"]
              and diag2["title"] == "목적만 검토 · 구성" and wt2.get("base") == "source" and bool(fl2)
              and fl2["line"] == f"{FLOW_HEAD}: 1단계 문서 검토(준비) › 2단계 구성 맞추기(구성 불러오기 › 프로젝트 구성 확정) — 구성의 기준: 원본 문서(사업계획서)",
              [t2.get("descAuto"), s2.get("lead"), diag2, wt2.get("base"), fl2])
        e = upload(small)
        r = requests.put(f"{base}/api/works/{e}/task", json={"kind": "rnd", "file": "report", "job": key2, "project": "조립 시험 2"}, timeout=30)
        check("서버가 둘째 조립한 TASK 의 키도 작업의 TASK 로 받음(연차보고서)", r.status_code == 200 and r.json()["task"]["job"] == key2, r.status_code)
        page.bring_to_front()
        page.evaluate("(id) => { location.hash = '#w=' + id; }", e)
        page.reload()
        page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=e, timeout=300000)
        page.click("#toolTabTask")
        page.wait_for_selector("#taskStage")
        page.wait_for_function(f"() => ({STAGES})().length === 2", timeout=60000)
        st2 = page.evaluate(STAGES)
        page.click("#tabDash")
        page.wait_for_function("() => document.querySelectorAll('#paneDash .dash-node').length > 0", timeout=60000)
        dash2 = page.evaluate("() => ({ nodes: [...document.querySelectorAll('#paneDash .dash-node')].map((n) => n.dataset.key), title: (document.querySelector('#paneDash .dash-title b') || {}).textContent })")
        check("그 TASK 로 연 문서 — 「작업 개요」 의 1단계 문서 검토 = 준비 · 헤딩 · 표 분석(LLM 검증·보완 줄 없음) · 2단계 구성 맞추기(다시 문서 검토(LLM) 있음) / 대시보드 노드에도 LLM 검증·보완 없음",
              [(s["id"], s["head"]) for s in st2] == [("review", "1단계 문서 검토"), ("frame", "2단계 구성 맞추기")] and st2[0]["steps"] == ["files", "heads"]
              and st2[1]["steps"] == ["config", "division", "reheads", "reheadsLlm"] and dash2["title"] == "목적만 검토 · 구성"
              and dash2["nodes"] == ["files", "heads", "configLoad", "config", "division", "reheads", "reheadsLlm"], [st2, dash2])
        page.locator("#panel").screenshot(path=str(OUT / "3b_review_target_only.png"))
        requests.delete(f"{base}/api/works/{e}", timeout=30).raise_for_status()
        rd = requests.delete(f"{base}/api/tasks/{key2}", timeout=30)
        check("둘째 TASK 는 작업을 지운 뒤 지움(API) — 첫 TASK 만 남음", rd.status_code == 200 and [t["key"] for t in requests.get(f"{base}/api/tasks", timeout=30).json()["tasks"]] == [key], rd.text)

        # ---- ④ 쓰는 중(하던 작업 둘) — 「고치기」 는 단계 표를 끄고 이름 · 설명 · 전제만(저장 몸에 assign 없음) · 「복제」 = 같은 배정(llm 까지) · 설명 · 전제 + 이름 「… 사본」 의 새 폼
        wf.bring_to_front()
        wf.goto(base + "/workflow#overview")   # 「워크플로우 조립」 절은 전체 보기와 함께 보인다(주소가 그 워크플로우의 절이면 다이어그램만)
        wf.reload()
        wf.wait_for_selector(f"#wfCompose .wf-made-list li[data-task={key}]")
        t1c = next((t for t in tasks_api()["tasks"] if t["key"] == key), {})
        use = next((x for x in wf.evaluate(MADE) if x["key"] == key), {})
        wf.locator(f"#wfCompose .wf-made-list li[data-task={key}] button", has_text="고치기").click()
        wf.wait_for_selector("#wfCompose .wf-assign-lock")
        fl = wf.evaluate(FORM)
        check("쓰는 중(지금 워크플로우로 둔 작업 둘 — editWhy) — 목록 줄의 셈 「하던 작업 2개」(목록에만 든 작업 없음) · 「고치기」 풍선 도움말 = 「이름 · 설명 · 전제만 고칩니다」 + editWhy · "
              "폼: 단계 표가 꺼짐(체크 모두 꺼짐 · 저장된 단계) · 잠금 글 = editWhy 그대로 + 「복제」 · 이름 · 설명 · 전제는 고칠 수 있음",
              isinstance(t1c.get("editWhy"), str) and "하던 작업이 2개" in t1c["editWhy"] and use.get("use") == [["current", "하던 작업 2개"]]
              and (use.get("tips") or [""])[0] == "이름 · 설명 · 전제만 고칩니다\n" + t1c["editWhy"] and fl["off"] and fl["boxesOff"] and fl["copy"] and fl["lock"] == t1c["editWhy"] + "복제"
              and fl["units"] == [["source", "원본 문서 — 사업계획서: —"], ["target", "목적 문서 — 연차보고서: 구성 맞추기 › 내용 넣기 › 문서 정리"]]
              and not any(wf.is_disabled(s) for s in ("#wfCompose input[name=name]", "#wfCompose input[name=desc]", "#wfCompose textarea[name=premise]", "#wfCompose form button[type=submit]")), [t1c, use, fl])
        names = {x["id"]: x["name"] for x in requests.get(f"{base}/api/works", timeout=30).json()}   # 작업 리스트가 보이는 이름(목적 문서는 프로젝트 이름까지)
        check("D1 — 쓰는 작업 둘(API uses: 지금 워크플로우 · active true · 프로젝트 「조립 시험」 · 라운드 1 · 이름 = 작업 리스트의 이름 · 20개 안이라 usesMore 0) · "
              "목록 줄의 셈 「하던 작업 2개」 아래 줄에 그 작업들의 링크(새 탭 · 그 작업을 여는 주소 /#w=<작업 id>) · 프로젝트 · 라운드 · 꼬리표 「지금 워크플로우」",
              sorted(u.get("wid") for u in t1c.get("uses") or []) == sorted([a, c]) and t1c.get("usesMore") == 0
              and all(u.get("active") is True and u.get("project") == "조립 시험" and u.get("round") == 1 and u.get("name") == names.get(u.get("wid")) for u in t1c["uses"])
              and names.get(a) != names.get(c)   # 같은 파일을 올린 둘 — 목적 문서(연차보고서 칸)만 프로젝트 이름이 붙는다
              and sorted((w["wid"], w["use"], w["name"], w["href"], w["target"], w["rel"], w["tag"], w["where"]) for w in use.get("works") or [])
              == sorted((wid, "current", names.get(wid), f"/#w={wid}", "_blank", "noopener", "지금 워크플로우", "조립 시험 · 라운드 1") for wid in (a, c))
              and all(w["below"] for w in use["works"]) and use.get("more") == "", [t1c.get("uses"), t1c.get("usesMore"), use.get("works"), use.get("more"), names])
        wf.locator("#wfCompose").screenshot(path=str(OUT / "4_locked.png"))
        wf.fill("#wfCompose input[name=name]", "구성 · 넣기 · 정리 2")
        wf.fill("#wfCompose input[name=desc]", "쓰는 중에 고친 설명")
        with wf.expect_response(lambda r: r.request.method == "PUT" and bool(TASK_PATH.search(r.url.split("?", 1)[0]))) as rr:
            wf.click("#wfCompose form button[type=submit]")
        wf.wait_for_function("(k) => location.hash === '#' + k", arg=key, timeout=20000)
        t3, b3 = next((t for t in tasks_api()["tasks"] if t["key"] == key), {}), bodies[-1]
        check("쓰는 중의 「고친 것 저장」 — 200 · 저장 몸에 assign · stages 없음(이름 · 설명 · 전제만) · 이름 · 설명이 바뀜 · 배정은 그대로 · 단계가 그대로라 sig 도 그대로(3차 계약)",
              rr.value.status == 200 and b3[0] == "PUT" and "assign" not in b3[2] and "stages" not in b3[2] and b3[2].get("name") == "구성 · 넣기 · 정리 2"
              and t3.get("name") == "구성 · 넣기 · 정리 2" and t3.get("desc") == "쓰는 중에 고친 설명" and t3.get("assign") == t1b.get("assign")
              and bool(SIG.fullmatch(str(t3.get("sig")))) and t3.get("sig") == t1c.get("sig"), [rr.value.status, b3, t3, t1c.get("sig")])
        wf.goto(base + "/workflow#overview")
        wf.reload()
        wf.wait_for_selector(f"#wfCompose .wf-made-list li[data-task={key}]")
        wf.locator(f"#wfCompose .wf-made-list li[data-task={key}] button", has_text="고치기").click()
        wf.wait_for_selector("#wfCompose .wf-assign-lock [data-wf-copy]")
        wf.click("#wfCompose .wf-assign-lock [data-wf-copy]")
        wf.wait_for_function("() => ((document.querySelector('#wfCompose form h3') || {}).textContent || '').startsWith('새 워크플로우')", timeout=10000)
        fc = wf.evaluate(FORM)
        picked = wf.evaluate("() => Object.fromEntries(['assign-source', 'assign-target'].map((n) => [n, [...document.querySelectorAll('#wfCompose input[name=' + n + ']')].filter((i) => i.checked).map((i) => i.value)]))")
        check("「복제」 — 새 폼(「새 워크플로우 — 「구성 · 넣기 · 정리 2」 복제」) · 이름 「구성 · 넣기 · 정리 2 사본」 · 같은 배정(체크가 켜진 채 고칠 수 있음) · 설명 · 전제 그대로 · 잠금 없음",
              fc["title"] == "새 워크플로우 — 「구성 · 넣기 · 정리 2」 복제" and fc["name"] == "구성 · 넣기 · 정리 2 사본" and fc["desc"] == "쓰는 중에 고친 설명" and fc["premise"] == (t3.get("premise") or "")
              and not fc["off"] and not fc["boxesOff"] and not fc["lock"] and picked == {"assign-source": [], "assign-target": ["stage_fit", "stage_fill", "stage_clean"]}, [fc, picked])
        with wf.expect_response(lambda r: r.request.method == "POST" and bool(TASK_PATH.search(r.url.split("?", 1)[0]))) as rr:
            wf.click("#wfCompose form button[type=submit]")
        wf.wait_for_function("(k) => /^#u_[0-9a-f]{8}$/.test(location.hash) && location.hash.slice(1) !== k", arg=key, timeout=20000)
        key3 = wf.evaluate("() => location.hash.slice(1)")
        t4, b4 = next((t for t in tasks_api()["tasks"] if t["key"] == key3), {}), bodies[-1]
        check("복제를 저장 — 201 · 저장 몸 = assign(같은 배정 — 서버가 준 llm 그대로 돌려줌) · stages 없음 · 새 워크플로우가 같은 배정(llm 까지) · 설명 그대로 · 하던 작업 없음",
              rr.value.status == 201 and b4[0] == "POST" and body_ok(b4[2]) and b4[2].get("assign") == t3.get("assign") and t4.get("name") == "구성 · 넣기 · 정리 2 사본"
              and t4.get("assign") == t3.get("assign") and t4.get("inUse") == 0 and t4.get("desc") == "쓰는 중에 고친 설명", [rr.value.status, b4, t4, t3.get("assign")])
        check("복제한 워크플로우는 API 로 지움(하던 작업 없음)", requests.delete(f"{base}/api/tasks/{key3}", timeout=30).status_code == 200)

        # ---- ⑤ 지우기 — 그 워크플로우를 쓰는 작업이 있으면 꺼짐(풍선 도움말 = 서버의 deleteWhy) → 작업을 지우고 · 문서의 워크플로우 목록에만 든 줄도 빼면 지움
        wf.goto(base + "/workflow#overview")
        wf.reload()
        wf.wait_for_selector("#wfCompose .wf-made-list li")
        made, t5 = wf.evaluate(MADE), next((t for t in tasks_api()["tasks"] if t["key"] == key), {})
        check("쓰는 작업이 있으면 「지우기」 꺼짐 — 풍선 도움말 = 서버의 deleteWhy 그대로(「이 워크플로우를 쓰는 작업이 2개 있어 지울 수 없습니다 — 지금 워크플로우로 둔 작업은 …」 — 화면이 글을 짓지 않음) · 셈 「하던 작업 2개」",
              made[0]["btns"] == [["고치기", False], ["지우기", True]] and t5.get("deleteWhy") == DEL_WHY.format(n=2) and made[0]["tips"][1] == t5["deleteWhy"]
              and made[0]["use"] == [["current", "하던 작업 2개"]], [made, t5])
        rp = requests.put(f"{base}/api/works/{a}/workflows", json={"job": key}, timeout=30)   # 지금 워크플로우의 줄을 목록에도 적어 둔 뒤 빼 보기(그 줄이 있든 없든 400 이어야 한다)
        rn = requests.delete(f"{base}/api/works/{a}/workflows/{key}", timeout=30)
        check("지금 워크플로우는 목록에서 못 뺌 — DELETE /api/works/{wid}/workflows/{job} 400 「지금 워크플로우는 목록에서 뺄 수 없습니다 — 다른 워크플로우로 바꾼 뒤에 빼세요」 · 지금 워크플로우는 그대로",
              rp.status_code == 200 and rn.status_code == 400 and (rn.json() or {}).get("detail") == ROW_NOW
              and requests.get(f"{base}/api/works/{a}/workflows", timeout=30).json().get("active") == key, [rp.status_code, rn.status_code, rn.text[:300]])
        for wid in (a, c):
            requests.delete(f"{base}/api/works/{wid}", timeout=30).raise_for_status()
        # 문서의 워크플로우 목록에만 든 작업(지금 워크플로우는 다른 것 — listed) — 「고치기」 는 잠기지 않고 「지우기」 만 막힌다
        wl = upload(small)
        rp = requests.put(f"{base}/api/works/{wl}/workflows", json={"job": key}, timeout=30)
        t6 = next((t for t in tasks_api()["tasks"] if t["key"] == key), {})
        wf.goto(base + "/workflow#overview")
        wf.reload()
        wf.wait_for_selector("#wfCompose .wf-made-list li")
        made = wf.evaluate(MADE)
        wf.locator("#wfCompose .wf-made-list li button", has_text="고치기").click()
        wf.wait_for_selector("#wfCompose form.wf-form")
        fg = wf.evaluate(FORM)
        check("목록에만 든 작업 1개(지금 워크플로우가 아님) — API inUse 0 · listed 1 · editWhy null · deleteWhy(쓰는 작업 1개) / 목록 줄: 셈 「목록에 든 작업 1개」 · "
              "「고치기」 는 잠기지 않음(풍선 도움말 그대로 · 폼의 단계 표가 켜짐 · 잠금 · 「복제」 없음) · 「지우기」 꺼짐(풍선 도움말 = deleteWhy)",
              rp.status_code == 200 and t6.get("inUse") == 0 and t6.get("listed") == 1 and "editWhy" in t6 and t6["editWhy"] is None and t6.get("deleteWhy") == DEL_WHY.format(n=1)
              and made[0]["use"] == [["listed", "목록에 든 작업 1개"]] and made[0]["btns"] == [["고치기", False], ["지우기", True]]
              and made[0]["tips"] == ["이름 · 설명 · 고른 단계 · 전제를 고칩니다", t6["deleteWhy"]] and not fg["off"] and not fg["boxesOff"] and not fg["lock"] and not fg["copy"],
              [rp.status_code, t6, made, fg])
        wf.locator("#wfCompose").screenshot(path=str(OUT / "5_listed.png"))
        wf.locator("#wfCompose form button", has_text="취소").click()
        lw, wl_name = (made[0].get("works") or [{}])[0], next((x["name"] for x in requests.get(f"{base}/api/works", timeout=30).json() if x["id"] == wl), None)
        check("D1 — 목록에만 든 작업(API uses: active false · 프로젝트 없음 · 라운드 1 · 이름 = 작업 리스트의 이름) · 목록 줄의 셈 「목록에 든 작업 1개」 아래 줄에 그 작업의 링크(새 탭 · /#w=<작업 id>) · "
              "꼬리표 「목록에만」 · 풍선 도움말이 대시보드의 「목록에서 빼기」 를 가리킴",
              t6.get("uses") == [{"wid": wl, "name": wl_name, "project": "", "round": 1, "active": False}] and t6.get("usesMore") == 0 and bool(wl_name)
              and len(made[0].get("works") or []) == 1 and (lw.get("wid"), lw.get("use"), lw.get("name"), lw.get("href"), lw.get("target"), lw.get("rel"), lw.get("tag"), lw.get("where"))
              == (wl, "listed", wl_name, f"/#w={wl}", "_blank", "noopener", "목록에만", "라운드 1") and lw.get("below") and made[0].get("more") == ""
              and "「목록에서 빼기」" in (wf.get_attribute(f"#wfCompose .wf-made-works a[href='/#w={wl}']", "title") or ""), [t6.get("uses"), made[0].get("works"), wl_name])
        with ctx.expect_page() as pi:   # 그 링크 — 새 탭에서 그 작업이 열린다(앱이 작업을 여는 해시 #w=<작업 id>)
            wf.click(f"#wfCompose .wf-made-works a[href='/#w={wl}']")
        opened = pi.value
        opened.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        opened.wait_for_function("(id) => typeof state !== 'undefined' && state.id === id && document.querySelector('#doc .sheet .para') != null", arg=wl, timeout=300000)
        check("그 작업의 링크를 누르면 새 탭에서 그 작업이 열림(주소 /#w=<작업 id> · 이 페이지는 그대로)", opened.evaluate("() => location.pathname + location.hash") == f"/#w={wl}"
              and wf.evaluate("() => location.pathname") == "/workflow", [opened.url, wf.url])
        opened.close()
        rr1 = requests.delete(f"{base}/api/works/{wl}/workflows/{key}", timeout=30)
        rr2 = requests.delete(f"{base}/api/works/{wl}/workflows/{key}", timeout=30)
        t7 = next((t for t in tasks_api()["tasks"] if t["key"] == key), {})
        check("목록 줄 빼기 — DELETE /api/works/{wid}/workflows/{job} 200(GET 과 같은 꼴 {items, active} — 그 줄이 빠짐) · 한 번 더 빼면 404 「목록에 그 워크플로우가 없습니다」 · 그 워크플로우를 쓰는 작업 0(지울 수 있음)",
              rr1.status_code == 200 and isinstance((rr1.json() or {}).get("items"), list) and "active" in rr1.json() and not any(x.get("job") == key for x in rr1.json()["items"])
              and rr2.status_code == 404 and (rr2.json() or {}).get("detail") == ROW_NONE and t7.get("inUse") == 0 and t7.get("listed") == 0 and t7.get("deleteWhy") is None,
              [rr1.status_code, rr1.text[:300], rr2.status_code, rr2.text[:300], t7])
        wf.goto(base + "/workflow#overview")   # 「워크플로우 조립」 절은 전체 보기와 함께 보인다(주소가 그 워크플로우의 절이면 다이어그램만)
        wf.reload()
        wf.wait_for_selector("#wfCompose .wf-made-list li")
        made = wf.evaluate(MADE)
        check("목록 줄을 빼면 「지우기」 가 켜짐 · 셈 없음 · 작업 링크 줄도 없음", made[0]["btns"] == [["고치기", False], ["지우기", False]] and made[0]["use"] == [] and made[0]["works"] == [] and made[0]["more"] == "", made)
        n = len(dialogs)
        wf.locator("#wfCompose .wf-made-list li button", has_text="지우기").click()
        wf.wait_for_function("() => document.querySelectorAll('#wfCompose .wf-made-list li').length === 0", timeout=20000)
        nav = wf.evaluate(NAV)
        check("지우기 — 한 번 묻고(확인) 지움 · 목차 · 목록 · 저장소에서 사라짐", len(dialogs) == n + 1 and "구성 · 넣기 · 정리" in dialogs[-1] and not any(x[0] == f"#{key}" for x in nav["links"])
              and requests.get(f"{base}/api/tasks", timeout=30).json()["tasks"] == [], [dialogs[n:], nav["links"][7:9]])
        requests.delete(f"{base}/api/works/{wl}", timeout=30).raise_for_status()
        page.bring_to_front()
        page.goto(base)
        page.wait_for_selector("#taskCards .task-card")
        check("앱을 새로 읽으면 그 TASK 의 카드도 없음", page.evaluate("(k) => !document.querySelector('#taskCards [data-task=\"' + k + '\"]') && !TASK_CATALOG[k]", key))
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

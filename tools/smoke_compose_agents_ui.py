"""조립 화면의 「에이전트」 열(spec_워크플로우 ② §18-16 · spec_에이전트 ② §6 — 2026-11-20 사용자 "각각의 단계에서 사용하는 에이전트의 스킬/도구/프롬프트는 클릭해서 여기서 보고 수정할 수 있게 해줘,,
다만 그건 범용일 수도 있고 현재 이 워크플로우 전용일 수 있으니 구분해서 작성할 수 있게 해줘, 우측 새로운 열에 확인할 수 있도록 해줘": app/static/workflow_agents.js · workflow_agents.css ·
app/agent_notes.py · agent_notes_api.py) 화면 확인 — 임시 서버(임시 조립 저장소 · 임시 덧붙이는 글 파일 · 임시 헤딩 저장소, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 흉내 없이 진짜 끝점으로.

    python -X utf8 tools/smoke_compose_agents_ui.py <그림·임시 폴더> [--port 18790]

같은 날 사용자 "공통적으로 그 도구에서는 는 내용과 워크플로우마다 사용되는 애용 2가지. 예로 구성맞추기 할때.. 사업계획서랑 다른 문서랑 제공해야 하는 정보가 다르잖아" — 단위는 도구(줄)다.

보는 것:
- ① 1500px — 폼이 펴지면 「도구 설명」 열 오른쪽에 「에이전트」 띠(28px)가 선다(가로 넘침 없음) · 안 골랐으면 띠에 수가 없다.
- ② 「LLM 검증·보완」 카드를 누름 → 띠에 에이전트 수 · 띠를 누르면 「에이전트」 열이 펴지고(400px) 「도구 설명」 이 28px 띠로 접힌다 · 맨 위 = **이 도구에 적어 두는 내용 두 칸**(도구 공통 · 이 워크플로우 전용) ·
  그 아래 그 줄이 쓰는 에이전트 = 등록부의 차례 · 쓰는 도구.
- ③ 에이전트를 펴면 보내는 글의 차례(조각마다 범위 꼬리표: 코드 · 범용 · 문서마다 · 스크립트 · 도구) + 접어 둔 「이 에이전트에만 덧붙이는 글(선택)」.
- ④ 도구 공통 내용 → 그 칸의 「저장」 → 서버에 저장(PUT …/tools/relay/headsLlm).
- ⑤ 새 워크플로우의 전용 내용 = 「워크플로우를 저장할 때 함께 저장됩니다」(저장 단추 없음) · **에이전트가 없는 도구(프로젝트 구성 반영)에도 두 칸**(읽는 곳 = 작업 진행 에이전트) · 다른 도구를 골랐다 와도 적던 글이 남는다 · 띠에 「저장 안 됨」.
- ⑥ 범용 글(헤딩 지침)을 그 자리에서 고쳐 저장 → 헤딩 지침 저장소의 내 사본 · 「기본으로」 두 번 → 기본 글 · 에이전트에만 덧붙이는 글(접어 둔 칸)도 저장된다.
- ⑦ 폼의 「저장」 → 워크플로우를 만든 뒤 전용 내용(도구 둘)이 그 키로 저장된다(조립 검사 · 저장 몸에는 그 글이 없다).
- ⑧ 「고치기」 로 다시 열면 전용 내용이 저장된 것으로 보이고 그 칸의 「저장」 으로 바로 고친다 · 에이전트 설정의 보내는 글(GET /api/agents/{id})에 도구 공통 · 전용 조각.
- ⑨ 「자리 연결 LLM 검토」 = 판단 지침(범용 · 파일 — 고치기 없음) + 전제(이 워크플로우) + 도구의 글이 붙는 자리 · 카드의 LLM 꼬리표를 누르면 열이 펴진다.
- ⑩ 1920px = 세 칸(폼 | 도구 설명 320 | 에이전트 380 — 띠 · 접는 단추 없음) · 1200px = 한 칸(가로 띠) · 어느 폭에서도 가로 넘침 없음.
- ⑪ 잠긴 폼에서도 고친다 · 「복제」 = 전용 내용이 새 폼에 적혀 있다(저장 전) · 「단계 만들기」 폼 = 전용 칸은 안내 글 · 워크플로우를 지우면 그 전용 내용도 지워진다.
- 콘솔 오류 없음."""
import argparse
import json
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
ap.add_argument("--port", type=int, default=18790)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1",
       "NFM_TASKS": str(tmp / "tasks.json"), "NFM_FORM_FILES": str(tmp / "form_files"), "NFM_AGENT_NOTES": str(tmp / "agent_notes.json")}   # 이 검사가 워크플로우 · 덧붙이는 글 · 헤딩 지침 사본을 만든다 — 늘 임시
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL"):
    env.pop(k, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails, dialogs, bodies, checks = [], [], [], [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:1100] if detail != "" and not ok else ""), flush=True)
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
    page.wait_for_function("() => { const b = document.querySelector('#wfCompose .wf-lines'); return b && !/검사하는 중/.test(b.textContent) && !!b.querySelector('.wf-lines-check'); }", timeout=30000)
    page.wait_for_timeout(350)   # 줄을 고친 뒤 검사를 거는 틈(250ms)
    page.wait_for_function("() => { const b = document.querySelector('#wfCompose .wf-lines'); return b && !/검사하는 중/.test(b.textContent); }", timeout=30000)


# 「에이전트」 열의 모습 — root = 그 폼의 절(#wfCompose | #wfStage)
AG = """(root) => { const sec = document.querySelector(root), cols = sec && sec.querySelector('.wf-compose-cols'), a = cols && cols.querySelector(':scope > .wf-agents'), hp = cols && cols.querySelector(':scope > .wf-help'),
    f = cols && cols.querySelector(':scope > form'), m = document.getElementById('wfMain'); if (!a || !hp || !f) return null;
  const box = (e) => { const r = e.getBoundingClientRect(); return { l: Math.round(r.left), r: Math.round(r.right), t: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; };
  const vis = (e) => !!e && e.checkVisibility(), t = (q) => (a.querySelector(q) || {}).textContent || '';
  const note = (n) => ({ scope: n.dataset.scope, tag: (n.querySelector('.wf-ag-note-head .wf-ag-tag') || {}).textContent, title: (n.querySelector('.wf-ag-note-head b') || {}).textContent,
    hint: (n.querySelector('.wf-ag-hint') || {}).textContent || '', text: n.querySelector('textarea') ? n.querySelector('textarea').value : null, state: (n.querySelector('.wf-ag-state') || {}).textContent || '',
    save: n.querySelector('.wf-ag-save') ? [!n.querySelector('.wf-ag-save').hidden, n.querySelector('.wf-ag-save').disabled] : null });
  return { side: cols.dataset.side, form: box(f), help: box(hp), ag: box(a), over: m.scrollWidth > m.clientWidth + 1, wider: sec.classList.contains('wf-wider') && sec.classList.contains('wf-wide'),
    rail: vis(a.querySelector('.wf-ag-rail')), railText: t('.wf-ag-rail'), railN: t('.wf-ag-rail-n'), fold: vis(a.querySelector('.wf-ag-fold')), head: vis(a.querySelector('.wf-ag-head')) ? t('.wf-ag-head h3') + '|' + t('.wf-ag-head-sub') : '',
    helpShown: vis(hp.querySelector('.wf-help-head')), helpUnit: hp.dataset.unit || '',
    unit: (a.querySelector('.wf-ag-main') || {}).dataset ? a.querySelector('.wf-ag-main').dataset.unit || '' : '', name: t('.wf-ag-unit-name'), sub: t('.wf-ag-unit-sub'), reader: t('.wf-ag-reader'), msg: vis(a.querySelector('.wf-ag-msg')) ? t('.wf-ag-msg') : '',
    toolNotes: [...a.querySelectorAll('.wf-ag-toolnotes > .wf-ag-note')].map(note),
    hints: [...a.querySelectorAll('.wf-ag-main > .wf-ag-hint, .wf-ag-main > .wf-ag-off')].map((x) => x.textContent),
    tools: [...a.querySelectorAll('.wf-ag-tool')].map((x) => [x.textContent, x.getAttribute('href'), x.target]),
    agents: [...a.querySelectorAll('.wf-ag-agent')].map((d) => ({ id: d.dataset.agent, open: d.open, no: (d.querySelector('.wf-ag-no') || {}).textContent, name: (d.querySelector('.wf-ag-name') || {}).textContent,
      model: (d.querySelector('.wf-ag-model') || {}).textContent, marks: [...d.querySelectorAll('.wf-ag-marks .wf-ag-tag')].map((x) => x.textContent),
      role: (d.querySelector('.wf-ag-role') || {}).textContent || '', link: (d.querySelector('.wf-ag-link') || { getAttribute: () => '' }).getAttribute('href'),
      parts: [...d.querySelectorAll('.wf-ag-part')].map((p) => ({ kind: p.className.replace('wf-ag-part wf-ag-k-', ''), title: p.querySelector('summary b').textContent, tags: [...p.querySelectorAll('summary .wf-ag-tag')].map((x) => x.textContent),
        btns: [...p.querySelectorAll('.wf-ag-acts button')].map((b) => b.textContent), state: (p.querySelector('.wf-ag-state') || {}).textContent || '', ro: p.querySelector('.wf-ag-text') ? p.querySelector('.wf-ag-text').readOnly : null })),
      own: d.querySelector('.wf-ag-own') ? d.querySelector('.wf-ag-own').open : null, notes: [...d.querySelectorAll('.wf-ag-own .wf-ag-note')].map(note) })),
    users: [...a.querySelectorAll('.wf-ag-user')].map((b) => [b.dataset.agGo, b.querySelector('b').textContent, b.querySelector('.wf-ag-user-n').textContent]) }; }"""


def ag(page, root="#wfCompose"):
    return page.evaluate(AG, root)


def card(page, unit):   # 그 줄의 카드 이름(누르면 그 도구를 고른다)
    return page.locator(f"#wfCompose li.wf-line[data-unit={unit}] .wf-line-name > b").first


def agent(page, aid, root="#wfCompose"):
    return page.locator(f'{root} .wf-ag-agent[data-agent="{aid}"]')


def note(page, aid, scope, root="#wfCompose"):   # 에이전트 안의 칸(scope all · job)
    return agent(page, aid, root).locator(f'.wf-ag-own .wf-ag-note[data-scope="{scope}"]')


def tnote(page, scope, root="#wfCompose"):   # 도구의 칸(scope tool = 도구 공통 · jobtool = 이 워크플로우 전용)
    return page.locator(f'{root} .wf-ag-toolnotes > .wf-ag-note[data-scope="{scope}"]')


def open_agent(page, aid, root="#wfCompose"):
    agent(page, aid, root).locator("> summary").click()
    page.wait_for_function("""([root, aid]) => { const d = document.querySelector(root + ' .wf-ag-agent[data-agent="' + aid + '"]'); return d && d.open && d.querySelectorAll('.wf-ag-part').length > 0; }""", arg=[root, aid], timeout=20000)


def notes_api():
    return requests.get(f"{base}/api/agent-notes", timeout=30).json()


def main():
    wait_server()
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1500, "height": 1000}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        page.on("request", lambda r: bodies.append((r.method, r.url.replace(base, ""), r.post_data)) if r.method in ("POST", "PUT", "DELETE") and ("/api/tasks" in r.url or "/api/agent-notes" in r.url or "/api/headings/guides" in r.url) else None)
        page.on("request", lambda r: checks.append(r.post_data) if r.url.endswith("/api/tasks/check") and r.method == "POST" else None)
        lines = requests.get(f"{base}/api/agent-notes/lines", timeout=30).json()
        reg = lines["families"]["relay"]
        page.goto(f"{base}/workflow#overview")
        page.wait_for_selector("#wfCompose [data-wf-compose=open]")

        # ---- ① 1500px — 「도구 설명」 열 오른쪽에 「에이전트」 띠
        page.click("#wfCompose [data-wf-compose=open]")
        settle(page)
        page.wait_for_function("() => { const h = document.querySelector('#wfCompose .wf-agents .wf-ag-main'); return h && !/읽는 중/.test(h.textContent); }", timeout=20000)
        a0 = ag(page)
        page.screenshot(path=str(OUT / "01_rail_1500.png"))
        check("① 1500px — 폼 | 도구 설명(320px) | 「에이전트」 띠(28px): 띠는 설명 열의 오른쪽 · 「도구 설명」 은 펴져 있음 · 그 절만 넓어짐 · 가로 넘침 없음 · 안 골랐으면 띠에 수가 없다",
              a0 and a0["side"] == "help" and a0["rail"] and a0["ag"]["w"] == 28 and a0["help"]["w"] == 320 and a0["ag"]["l"] >= a0["help"]["r"] and a0["help"]["l"] >= a0["form"]["r"]
              and a0["helpShown"] and not a0["head"] and a0["wider"] and not a0["over"] and "에이전트" in a0["railText"] and a0["railN"] == "", a0)

        # ---- ② 카드를 누름 → 띠에 수 · 띠를 누르면 열이 펴진다
        n_checks, n_bodies = len(checks), len(bodies)
        card(page, "headsLlm").click()
        a1 = ag(page)
        want = reg["headsLlm"]["agents"]
        check("② 「LLM 검증·보완」 카드를 누름 → 「도구 설명」 이 그 도구(같은 고름) · 띠에 그 줄이 쓰는 에이전트 수(등록부 = 6)",
              a1["helpUnit"] == "headsLlm" and a1["side"] == "help" and a1["railN"] == str(len(want)) == "6", [a1["helpUnit"], a1["railN"], want])
        page.click("#wfCompose .wf-ag-rail")
        a2 = ag(page)
        page.screenshot(path=str(OUT / "02_open_1500.png"))
        names = {k: v["name"] for k, v in lines["agents"].items()}
        check("② 띠를 누름 → 「에이전트」 열이 펴지고(400px · 머리 「에이전트 | 스킬 · 도구 · 프롬프트」 · 접는 단추) 「도구 설명」 이 28px 띠로 접힘 · 가로 넘침 없음 · 폼은 그대로 왼쪽",
              a2["side"] == "agents" and a2["ag"]["w"] == 400 and a2["help"]["w"] == 28 and not a2["helpShown"] and not a2["rail"] and a2["fold"] and a2["head"] == "에이전트|스킬 · 도구 · 프롬프트"
              and not a2["over"] and a2["help"]["l"] >= a2["form"]["r"] and a2["ag"]["l"] >= a2["help"]["r"], a2)
        check("② 맨 위 = 이 도구에 적어 두는 내용 두 칸(「도구 공통」 · 「이 워크플로우 전용」) + 누가 읽는지 한 줄 · 그 아래 그 줄이 쓰는 에이전트 = 등록부의 차례(번호 · 이름 · 모델) · 쓰는 도구 「헤딩 추출」(새 탭)",
              a2["unit"] == "headsLlm" and a2["name"] == "LLM 검증·보완" and [x["id"] for x in a2["agents"]] == want and [x["name"] for x in a2["agents"]] == [names[k] for k in want]
              and [x["no"] for x in a2["agents"]] == [lines["agents"][k]["no"] for k in want] and all(x["model"] and not x["open"] and x["marks"] == [] for x in a2["agents"])
              and "Opus 5.5" in a2["agents"][-1]["model"] and a2["tools"] == [["헤딩 추출", "/workflow#common-headings", "_blank"]] and "에이전트 6개" in a2["sub"]
              and [(n["scope"], n["tag"], n["title"]) for n in a2["toolNotes"]] == [("tool", "도구 공통", "이 도구에서 공통으로 쓰는 내용"), ("jobtool", "이 워크플로우 전용", "이 워크플로우에서만 쓰는 내용")]
              and a2["toolNotes"][0]["save"] == [True, True] and a2["toolNotes"][0]["state"] == "아직 없음" and "모든 워크플로우에서 씁니다" in a2["toolNotes"][0]["hint"]
              and a2["toolNotes"][1]["save"][0] is False and "할 때만 씁니다" in a2["toolNotes"][1]["hint"] and "에이전트 6개의 프롬프트 끝에" in a2["reader"], a2)

        # ---- ③ 에이전트를 펴면 보내는 글의 차례 + 접어 둔 「이 에이전트에만 덧붙이는 글」
        open_agent(page, "heading_types")
        a3 = ag(page)
        ht = next(x for x in a3["agents"] if x["id"] == "heading_types")
        page.screenshot(path=str(OUT / "03_agent_open.png"))
        check("③ 「헤딩 유형 판정 (A)」 를 펴면 역할 · 에이전트 설정 링크 · 보내는 글의 차례 = 계약(코드) → 지침 셋(범용 · 고칠 수 있음) → 양식 정보(문서마다) → 자료(스크립트) → 도구에 적어 둔 내용(도구 — 위의 두 칸)",
              ht["open"] and ht["role"].startswith("스크립트가 헤딩 후보") and ht["link"] == "/agents#heading_types"
              and [p["kind"] for p in ht["parts"]] == ["contract", "heading", "heading", "heading", "form", "data", "toolnote"]
              and [p["tags"] for p in ht["parts"]] == [["코드"], ["범용", "고칠 수 있음"], ["범용", "고칠 수 있음"], ["범용", "고칠 수 있음"], ["문서마다"], ["스크립트"], ["도구"]]
              and ht["parts"][1]["title"] == "지침 — 헤딩 그래프·개요레벨 지침", ht)
        check("③ 에이전트 하나에만 덧붙이는 글은 접어 둔 칸(「이 에이전트에만 덧붙이는 글(선택)」 — 처음엔 접힘 · 안에 두 칸: 모든 워크플로우 · 이 워크플로우 전용)",
              ht["own"] is False and [(n["scope"], n["tag"], n["title"]) for n in ht["notes"]] == [("all", "모든 워크플로우", "이 에이전트에만 — 모든 워크플로우"), ("job", "이 워크플로우 전용", "이 에이전트에만 — 이 워크플로우에서만")], ht["notes"])

        # ---- ④ 도구 공통 내용 — 그 칸의 「저장」
        ALL = "표 머리의 단위가 다르면 같은 유형으로 묶지 않는다."
        tnote(page, "tool").locator("textarea").fill(ALL)
        a4 = ag(page)
        check("④ 도구 공통 칸에 적음 → 「고침 — 저장 안 됨」 · 「저장」 켜짐 · 띠에 「저장 안 됨」(서버에는 아직 없음)",
              a4["toolNotes"][0]["state"] == "고침 — 저장 안 됨" and a4["toolNotes"][0]["save"] == [True, False] and notes_api()["tools"] == {}, a4["toolNotes"])
        tnote(page, "tool").locator(".wf-ag-save").click()
        page.wait_for_function("() => /도구 공통 내용을 저장했습니다/.test((document.querySelector('#wfCompose .wf-ag-msg') || {}).textContent || '')", timeout=20000)
        a4b = ag(page)
        check("④ 「저장」 → 서버의 도구 공통 내용(PUT /api/agent-notes/tools/relay/headsLlm — job 없이) · 「저장됨 · n자」 · 열 · 펴 둔 에이전트는 그대로",
              notes_api()["tools"] == {"relay.headsLlm": ALL} and notes_api()["jobTools"] == {} and a4b["toolNotes"][0]["state"] == f"저장됨 · {len(ALL)}자" and a4b["toolNotes"][0]["text"] == ALL
              and next(x for x in a4b["agents"] if x["id"] == "heading_types")["open"] and "다음 실행부터 쓰입니다" in a4b["msg"]
              and json.loads([b for b in bodies if b[1] == "/api/agent-notes/tools/relay/headsLlm"][-1][2]) == {"text": ALL, "version": 0}, [a4b["toolNotes"], a4b["msg"]])

        # ---- ⑤ 새 워크플로우의 전용 내용 — 저장할 때 함께 · 에이전트가 없는 도구에도 · 적던 글이 남는다
        JOB = "이 워크플로우에서는 「붙임」 줄을 헤딩으로 보지 않는다."
        tnote(page, "jobtool").locator("textarea").fill(JOB)
        a5 = ag(page)
        check("⑤ 전용 칸에 적음(새 워크플로우) → 「워크플로우를 저장할 때 함께 저장됩니다」 · 저장 단추 없음 · 서버에는 아직 없음",
              a5["toolNotes"][1]["state"] == "워크플로우를 저장할 때 함께 저장됩니다" and a5["toolNotes"][1]["save"][0] is False and notes_api()["jobTools"] == {}, a5["toolNotes"])
        card(page, "division").click()   # 에이전트가 없는 도구 — 사용자의 예 「구성 맞추기」
        a5b = ag(page)
        check("⑤ 에이전트가 없는 도구(프로젝트 구성 반영)에도 두 칸 — 읽는 곳 = 작업 진행 에이전트(스크립트의 동작은 그대로) · 쓰는 도구 · 아래에 에이전트를 쓰는 도구 목록",
              a5b["unit"] == "division" and a5b["agents"] == [] and "쓰지 않습니다" in a5b["sub"] and a5b["tools"][0][0] == "프로젝트 구성(구분 기준)"
              and [n["scope"] for n in a5b["toolNotes"]] == ["tool", "jobtool"] and a5b["toolNotes"][0]["text"] == "" and "작업 진행 에이전트가 이 단계를 안내" in a5b["reader"] and "스크립트의 동작은 바뀌지 않습니다" in a5b["reader"]
              and [u[0] for u in a5b["users"]] == [k for k in ("headsLlm", "reheadsLlm", "llm", "gaps", "tableMap", "guideFix") if reg[k]["agents"]] and a5b["users"][0][2] == "에이전트 6", a5b)
        FIT = "사업계획서는 단계 · 차년도 · 기관을 준다."
        tnote(page, "jobtool").locator("textarea").fill(FIT)
        page.locator('#wfCompose .wf-ag-user[data-ag-go="headsLlm"]').click()   # 목록에서 그 도구로
        a5c = ag(page)
        check("⑤ 목록의 이름을 누름 → 그 도구가 골라짐(「도구 설명」 도 같은 도구) · 펴 둔 에이전트 · 적던 전용 내용이 그대로",
              a5c["unit"] == "headsLlm" and a5c["helpUnit"] == "headsLlm" and next(x for x in a5c["agents"] if x["id"] == "heading_types")["open"] and a5c["toolNotes"][1]["text"] == JOB and a5c["toolNotes"][0]["text"] == ALL, a5c["toolNotes"])
        page.locator("#wfCompose .wf-ag-fold").click()
        a5d = ag(page)
        check("⑤ 접는 단추 » → 「에이전트」 가 띠로 · 「도구 설명」 이 다시 펴짐(그 도구의 설명 그대로) · 띠에 수와 「저장 안 됨」",
              a5d["side"] == "help" and a5d["rail"] and a5d["helpShown"] and a5d["helpUnit"] == "headsLlm" and a5d["railN"] == "6" and "저장 안 됨" in a5d["railText"] and a5d["help"]["w"] == 320, a5d)
        check("⑤ 여기까지 조립 검사 · 워크플로우 저장을 부르지 않았다(열을 여닫고 글을 적는 것은 조립을 바꾸지 않는다)", len(checks) == n_checks and not [b for b in bodies[n_bodies:] if "/api/tasks" in b[1]], [checks[n_checks:], bodies[n_bodies:]])

        # ---- ⑤-2 전용 표시(② §18-17 — 사용자 「도구에 *** 전용 이라고 명시를 해야 한다고봄」): 카드의 「전용」 꼬리표 · 「도구 설명」 · 「에이전트」 열의 「○○ 전용」 + 까닭
        ONLY = """() => { const cards = {}; for (const c of document.querySelectorAll('#wfCompose .wf-line-cell')) { const u = c.dataset.unit || c.closest('.wf-line').dataset.unit, t = c.querySelector('.wf-badges .wf-t-only');
            if (u && c.querySelector('.wf-line-name')) cards[u] = t ? [t.textContent, t.dataset.only, t.title] : null; }
          const hp = document.querySelector('#wfCompose .wf-help-only'), ag = document.querySelector('#wfCompose .wf-ag-only');
          return { cards, help: hp ? [hp.querySelector('.wf-tag').textContent, hp.textContent] : null, ag: ag ? [ag.querySelector('.wf-ag-tag').textContent, ag.textContent] : null,
            list: [...document.querySelectorAll('#wfCompose .wf-help-item')].filter((b) => b.querySelector('.wf-t-only')).map((b) => b.dataset.helpGo) }; }"""
        card(page, "division").click()
        o1 = page.evaluate(ONLY)
        check("⑤-2 전용 표시 — 카드: 구분 기준 엔진을 쓰는 줄(구성 불러오기 · 프로젝트 구성 추출 · 반영)과 원본 → 목적 줄(자리 연결 … 내용 반영)에 「전용」(가리키면 어느 문서 전용인지와 까닭) · 헤딩 · 표 분석 · LLM 검증·보완 · 작성요령 삭제에는 없다",
              {k for k, v in o1["cards"].items() if v} == {"configLoad", "config", "division", "link", "llm", "plan", "gaps", "tableMap", "apply"} and {k for k, v in o1["cards"].items() if not v} == {"heads", "headsLlm", "reheads", "reheadsLlm", "guide"}
              and o1["cards"]["division"][:2] == ["전용", "rnd"] and o1["cards"]["division"][2].startswith("사업계획서 · 연차보고서 전용 — 스크립트(구분 기준 엔진)") and o1["cards"]["link"][2].startswith("사업계획서 → 연차보고서 전용"), o1["cards"])
        check("⑤-2 「프로젝트 구성 반영」 을 고르면 「에이전트」 열의 이름 아래 「사업계획서 · 연차보고서 전용」 + 까닭(다른 양식의 문서에서는 멈춘다)",
              o1["ag"] and o1["ag"][0] == "사업계획서 · 연차보고서 전용" and "지원하지 않는 양식" in o1["ag"][1], o1["ag"])
        o2 = page.evaluate(ONLY)   # 「도구 설명」 은 ⑤ 의 접는 단추로 이미 펴져 있다(같은 도구)
        check("⑤-2 「도구 설명」 열의 이름 아래에도 같은 표시", o2["help"] and o2["help"][0] == "사업계획서 · 연차보고서 전용" and "구분 기준 엔진" in o2["help"][1], o2["help"])
        card(page, "heads").click()
        o3 = page.evaluate(ONLY)
        check("⑤-2 문서를 가리지 않는 도구(헤딩 · 표 분석)에는 표시가 없다", o3["help"] is None, o3["help"])

        # ---- ⑥ 범용 글(헤딩 지침)을 그 자리에서 고침 · 에이전트에만 덧붙이는 글
        page.locator("#wfCompose li.wf-line[data-unit=headsLlm] .wf-tag.wf-t-llm").first.click()   # 카드의 LLM 꼬리표 → 열이 펴진다
        a6 = ag(page)
        check("⑥ 카드의 LLM 꼬리표를 누름 → 「에이전트」 열이 펴진다(그 도구 · 펴 둔 에이전트 그대로)", a6["side"] == "agents" and a6["unit"] == "headsLlm" and next(x for x in a6["agents"] if x["id"] == "heading_types")["open"], a6["side"])
        part = agent(page, "heading_types").locator(".wf-ag-part.wf-ag-k-heading").first
        part.locator("> summary").click()
        g0 = requests.get(f"{base}/api/headings/guides/graph", timeout=30).json()
        check("⑥ 지침 조각을 펴면 글(읽기 전용) · 「기본 글」 · 「고치기」", part.locator(".wf-ag-text").input_value() == g0["text"] and part.locator(".wf-ag-text").evaluate("(t) => t.readOnly")
              and part.locator(".wf-ag-state").inner_text() == "기본 글" and [b.inner_text() for b in part.locator(".wf-ag-acts button").all()] == ["고치기"])
        part.locator("button", has_text="고치기").click()
        part = agent(page, "heading_types").locator(".wf-ag-part.wf-ag-k-heading").first
        part.locator(".wf-ag-text").fill(g0["text"] + "\n- 검사에서 덧붙인 줄.\n")
        part.locator("button", has_text="저장").click()
        page.wait_for_function("() => /범용 글이라 모든 워크플로우에서/.test((document.querySelector('#wfCompose .wf-ag-msg') || {}).textContent || '')", timeout=20000)
        g1 = requests.get(f"{base}/api/headings/guides/graph", timeout=30).json()
        a6b = next(x for x in ag(page)["agents"] if x["id"] == "heading_types")
        page.screenshot(path=str(OUT / "06_guide_saved.png"))
        check("⑥ 「고치기」 → 고쳐 「저장」 → 헤딩 지침 저장소의 내 사본(판 1) · 꼬리표 「고침」 · 「기본으로」 단추 · 적던 전용 내용은 그대로",
              g1["custom"] and g1["text"].endswith("- 검사에서 덧붙인 줄.\n") and a6b["parts"][1]["tags"] == ["범용", "고침"] and a6b["parts"][1]["state"] == "내 사본 · 판 1"
              and a6b["parts"][1]["btns"] == ["고치기", "기본으로"] and ag(page)["toolNotes"][1]["text"] == JOB, a6b["parts"][1])
        part = agent(page, "heading_types").locator(".wf-ag-part.wf-ag-k-heading").first
        part.locator("button", has_text="기본으로").click()
        agent(page, "heading_types").locator(".wf-ag-part.wf-ag-k-heading").first.locator("button", has_text="되돌리기 확인").click()
        page.wait_for_function("() => /기본 글로 되돌렸습니다/.test((document.querySelector('#wfCompose .wf-ag-msg') || {}).textContent || '')", timeout=20000)
        g2 = requests.get(f"{base}/api/headings/guides/graph", timeout=30).json()
        check("⑥ 「기본으로」 두 번 → 내 사본을 버리고 기본 글", not g2["custom"] and g2["text"] == g0["text"] and next(x for x in ag(page)["agents"] if x["id"] == "heading_types")["parts"][1]["tags"] == ["범용", "고칠 수 있음"])
        agent(page, "heading_types").locator(".wf-ag-own > summary").click()
        OWN = "유형 이름은 짧게 적는다."
        note(page, "heading_types", "all").locator("textarea").fill(OWN)
        note(page, "heading_types", "all").locator(".wf-ag-save").click()
        page.wait_for_function("() => /에이전트 · 모든 워크플로우 내용을 저장했습니다/.test((document.querySelector('#wfCompose .wf-ag-msg') || {}).textContent || '')", timeout=20000)
        a6c = next(x for x in ag(page)["agents"] if x["id"] == "heading_types")
        check("⑥ 접어 둔 「이 에이전트에만 덧붙이는 글」 을 펴서 적고 저장 → 그 에이전트에만(서버의 all) · 머리 줄에 「에이전트 글」 · 칸은 펴진 채",
              notes_api()["all"] == {"heading_types": OWN} and a6c["marks"] == ["에이전트 글"] and a6c["own"] is True and a6c["notes"][0]["state"] == f"저장됨 · {len(OWN)}자", [notes_api()["all"], a6c["marks"], a6c["own"]])

        # ---- ⑦ 폼의 「저장」 → 전용 내용(도구 둘)이 새 키로
        page.fill("#wfCompose input[name=name]", "에이전트 열 시험")
        n_bodies = len(bodies)
        page.click("#wfCompose form button[type=submit]")
        page.wait_for_function("() => /^#u_[0-9a-f]{8}$/.test(location.hash)", timeout=30000)
        key = page.evaluate("location.hash.slice(1)")
        sent = bodies[n_bodies:]
        post = next(b for b in sent if b[0] == "POST" and b[1] == "/api/tasks")
        check("⑦ 폼의 「저장」 → 워크플로우를 만든 뒤(POST /api/tasks — 몸에 적어 둔 내용 없음) 전용 내용을 그 키로 저장(PUT …/tools/relay/headsLlm · division {job}) · 알림 창 없음",
              notes_api()["jobTools"] == {key: {"headsLlm": JOB, "division": FIT}} and notes_api()["tools"] == {"relay.headsLlm": ALL} and JOB not in post[2] and FIT not in post[2]
              and sorted((b[1], json.loads(b[2]).get("job")) for b in sent if "/api/agent-notes/tools/" in b[1]) == [("/api/agent-notes/tools/relay/division", key), ("/api/agent-notes/tools/relay/headsLlm", key)] and not dialogs, [sent, dialogs])

        # ---- ⑧ 다시 열면 저장된 전용 내용 · 그 칸의 「저장」 으로 바로 고침
        page.goto(f"{base}/workflow#overview")
        page.reload()
        page.wait_for_selector(f'#wfCompose .wf-made-list li[data-task="{key}"]')
        page.locator(f'#wfCompose .wf-made-list li[data-task="{key}"] button', has_text="고치기").click()
        settle(page)
        card(page, "division").click()
        page.click("#wfCompose .wf-ag-rail")
        page.wait_for_function("() => document.querySelectorAll('#wfCompose .wf-ag-toolnotes > .wf-ag-note').length === 2", timeout=20000)
        a8 = ag(page)
        check("⑧ 「고치기」 로 다시 열면 「프로젝트 구성 반영」 의 전용 칸 = 저장된 글 · 「저장됨 · n자」 · 저장 단추가 있다(꺼짐 — 고치면 켜짐) · 그 워크플로우의 이름이 안내에",
              a8["unit"] == "division" and a8["toolNotes"][1]["text"] == FIT and a8["toolNotes"][1]["state"] == f"저장됨 · {len(FIT)}자" and a8["toolNotes"][1]["save"] == [True, True]
              and "「에이전트 열 시험」" in a8["toolNotes"][1]["hint"] and a8["toolNotes"][0]["text"] == "", a8["toolNotes"])
        FIT2 = FIT + " 기관 이름은 줄이지 않는다."
        tnote(page, "jobtool").locator("textarea").fill(FIT2)
        tnote(page, "jobtool").locator(".wf-ag-save").click()
        page.wait_for_function("() => /이 워크플로우 전용 내용을 저장했습니다/.test((document.querySelector('#wfCompose .wf-ag-msg') || {}).textContent || '')", timeout=20000)
        det = requests.get(f"{base}/api/agents/heading_types", timeout=30).json()["prompt"]
        check("⑧ 전용 칸의 「저장」 → 바로 저장(폼의 저장 없이) · 에이전트 설정의 보내는 글 끝 = 자료 → 덧붙이는 글(에이전트 범용) → 도구 「LLM 검증·보완」 공통 → 그 도구 · 「에이전트 열 시험」 전용",
              notes_api()["jobTools"] == {key: {"headsLlm": JOB, "division": FIT2}} and [p["kind"] for p in det][-4:] == ["data", "note", "note", "note"] and det[-3]["text"] == OWN and det[-3]["editable"]
              and det[-2]["title"] == "도구에 적어 둔 내용 — 「LLM 검증·보완」 공통(이관형)" and det[-2]["text"] == ALL and not det[-2]["editable"]
              and det[-1]["title"] == "도구에 적어 둔 내용 — 「LLM 검증·보완」 · 「에이전트 열 시험」 전용" and det[-1]["text"] == JOB, [notes_api(), [p["title"] for p in det[-3:]]])

        # ---- ⑨ 자리 연결 LLM 검토 — 판단 지침(파일) · 전제 · 도구의 글이 붙는 자리
        card(page, "llm").click()
        page.wait_for_function("() => (document.querySelector('#wfCompose .wf-ag-main') || { dataset: {} }).dataset.unit === 'llm'", timeout=20000)
        open_agent(page, "merge_links")
        a9 = ag(page)
        ml = a9["agents"][0]
        page.screenshot(path=str(OUT / "09_merge_links.png"))
        check("⑨ 「자리 연결 LLM 검토」 = 에이전트 「자리 연결 검토」 하나 — 판단 지침은 「범용 · 파일」(읽기만 — 고치기 없음) · 전제는 「이 워크플로우」(폼의 「전제」 칸) · 자료 뒤에 「도구에 적어 둔 내용」",
              a9["unit"] == "llm" and [x["id"] for x in a9["agents"]] == ["merge_links"] and [p["kind"] for p in ml["parts"]] == ["contract", "merge", "form", "job", "data", "toolnote"]
              and ml["parts"][1]["tags"] == ["범용 · 파일"] and ml["parts"][1]["btns"] == [] and ml["parts"][3]["tags"] == ["이 워크플로우"] and ml["parts"][3]["title"] == "전제 — 이 워크플로우의 할 일 프롬프트"
              and [n["scope"] for n in a9["toolNotes"]] == ["tool", "jobtool"] and a9["toolNotes"][1]["save"] == [True, True] and "에이전트 1개의 프롬프트 끝에" in a9["reader"], [ml, a9["toolNotes"]])

        # ---- ⑩ 폭 — 1920px 세 칸 · 1200px 한 칸
        page.set_viewport_size({"width": 1920, "height": 1000})
        page.wait_for_timeout(200)
        w1 = ag(page)
        page.screenshot(path=str(OUT / "10_wide_1920.png"))
        check("⑩ 1920px = 세 칸(폼 | 도구 설명 320px | 에이전트 380px — 둘 다 펴져 있고 띠 · 접는 단추 없음) · 가로 넘침 없음 · 폼이 700px 보다 넓다",
              w1["help"]["w"] == 320 and w1["ag"]["w"] == 380 and w1["helpShown"] and w1["head"] and not w1["rail"] and not w1["fold"] and not w1["over"]
              and w1["form"]["r"] <= w1["help"]["l"] and w1["help"]["r"] <= w1["ag"]["l"] and w1["form"]["w"] >= 700, w1)
        page.set_viewport_size({"width": 1200, "height": 900})
        page.wait_for_timeout(200)
        w2 = ag(page)
        page.screenshot(path=str(OUT / "10_narrow_1200.png"))
        check("⑩ 1200px = 한 칸 — 펴 둔 「에이전트」 가 화면 위에 붙어 있고(폼의 아래쪽 줄을 보고 있어도 · 높이 46vh 까지) 「도구 설명」 은 폼 위의 높이 28px 가로 띠 · 가로 넘침 없음",
              w2["side"] == "agents" and w2["help"]["h"] <= 30 and not w2["helpShown"] and w2["head"] and 0 <= w2["ag"]["t"] <= 60 and w2["ag"]["h"] <= 0.46 * 900 + 2 and w2["help"]["t"] < w2["form"]["t"] and not w2["over"]
              and w2["ag"]["w"] == w2["form"]["w"], w2)
        page.locator("#wfCompose .wf-compose-cols > .wf-help").click(position={"x": 60, "y": 12})   # 접힌 「도구 설명」 띠를 누름
        w3 = ag(page)
        check("⑩ 접힌 「도구 설명」 띠를 누름 → 「도구 설명」 이 펴지고 「에이전트」 가 높이 28px 가로 띠(누르면 다시 펴짐)", w3["side"] == "help" and w3["helpShown"] and w3["rail"] and w3["ag"]["h"] <= 30 and not w3["over"], w3)
        page.click("#wfCompose .wf-ag-rail")
        check("⑩ 가로 띠 「에이전트」 를 누름 → 다시 펴짐", ag(page)["side"] == "agents")
        page.set_viewport_size({"width": 1500, "height": 1000})

        # ---- ⑪ 잠긴 폼 · 복제 · 단계 폼 · 지우기
        page.goto(f"{base}/workflow#overview")
        wid = requests.post(f"{base}/api/docs?new=1", files={"file": (PLAN.name, PLAN.read_bytes())}, timeout=300).json()["docId"]   # 그 워크플로우를 쓰는 작업 — 폼이 잠기고 「복제」 가 선다
        r = requests.put(f"{base}/api/works/{wid}/task", json={"kind": "rnd", "file": "report", "job": key, "project": "에이전트 열 시험"}, timeout=30)
        check("⑪ (준비) 그 워크플로우로 작업 하나를 만든다", r.status_code == 200, r.text[:300])
        page.reload()
        page.wait_for_selector(f'#wfCompose .wf-made-list li[data-task="{key}"]')
        page.locator(f'#wfCompose .wf-made-list li[data-task="{key}"] button', has_text="고치기").click()
        page.wait_for_selector("#wfCompose .wf-assign-lock [data-wf-copy]")
        card(page, "division").click()
        page.click("#wfCompose .wf-ag-rail")
        page.wait_for_function("() => document.querySelectorAll('#wfCompose .wf-ag-toolnotes > .wf-ag-note').length === 2", timeout=20000)
        k1 = ag(page)
        check("⑪ 쓰는 중이라 잠긴 폼(단계를 못 바꿈)에서도 이 열은 읽고 고친다 — 전용 칸에 글 · 저장 단추", k1["toolNotes"][1]["text"] == FIT2 and k1["toolNotes"][1]["save"] == [True, True], k1["toolNotes"])
        page.click("#wfCompose .wf-assign-lock [data-wf-copy]")
        settle(page)
        card(page, "division").click()
        page.click("#wfCompose .wf-ag-rail")
        page.wait_for_function("() => document.querySelectorAll('#wfCompose .wf-ag-toolnotes > .wf-ag-note').length === 2", timeout=20000)
        c2 = ag(page)
        check("⑪ 「복제」 = 원래 워크플로우의 전용 내용이 새 폼에 적혀 있다(저장 전 — 저장하면 새 키로) · 띠 · 서버의 글은 그대로",
              c2["toolNotes"][1]["text"] == FIT2 and c2["toolNotes"][1]["state"] == "워크플로우를 저장할 때 함께 저장됩니다" and notes_api()["jobTools"] == {key: {"headsLlm": JOB, "division": FIT2}}, c2["toolNotes"])
        n_bodies = len(bodies)
        page.click("#wfCompose form button[type=submit]")
        page.wait_for_function("(old) => /^#u_[0-9a-f]{8}$/.test(location.hash) && location.hash.slice(1) !== old", arg=key, timeout=30000)
        key2 = page.evaluate("location.hash.slice(1)")
        check("⑪ 복제한 폼을 저장 → 전용 내용(도구 둘)이 새 키에도(원래 키의 글은 그대로)", notes_api()["jobTools"] == {key: {"headsLlm": JOB, "division": FIT2}, key2: {"headsLlm": JOB, "division": FIT2}}, notes_api()["jobTools"])
        page.goto(f"{base}/workflow#overview")
        page.reload()
        page.wait_for_selector("#wfStage [data-wf-stage=open]")
        page.click("#wfStage [data-wf-stage=open]")
        page.wait_for_selector("#wfStage .wf-agents")
        page.wait_for_function("() => { const h = document.querySelector('#wfStage .wf-agents .wf-ag-main'); return h && !/읽는 중/.test(h.textContent); }", timeout=20000)
        s0 = ag(page, "#wfStage")
        page.locator('#wfStage .wf-ag-rail').click()
        page.locator('#wfStage .wf-ag-user[data-ag-go="llm"]').click()
        s1 = ag(page, "#wfStage")
        check("⑪ 「단계 만들기」 폼에도 같은 열(띠 → 펴기) — 단계는 워크플로우가 아니라 전용 칸은 안내 글(글 칸 · 저장 단추 없음) · 도구 공통 칸은 적을 수 있다",
              s0 and s0["rail"] and s1["side"] == "agents" and s1["unit"] == "llm" and s1["toolNotes"][0]["save"] == [True, True] and s1["toolNotes"][1]["text"] is None and s1["toolNotes"][1]["save"] is None
              and "워크플로우가 아니어서" in s1["toolNotes"][1]["hint"], [s0 and s0["rail"], s1["toolNotes"]])
        r = requests.delete(f"{base}/api/tasks/{key2}", timeout=30)
        check("⑪ 워크플로우를 지우면 그 전용 내용도 지워진다(다른 워크플로우의 글 · 도구 공통 · 에이전트 글은 그대로)",
              r.status_code == 200 and notes_api()["jobTools"] == {key: {"headsLlm": JOB, "division": FIT2}} and notes_api()["tools"] == {"relay.headsLlm": ALL} and notes_api()["all"] == {"heading_types": OWN}, [r.status_code, notes_api()])

        real = [e for e in errors if "409" not in e and "400" not in e]
        check("콘솔 오류 없음 · 알림 창 없음", not real and not dialogs, [real[:5], dialogs])
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

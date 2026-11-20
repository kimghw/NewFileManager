"""첫 화면의 대시보드(spec_작업에이전트 ② §10 「첫 화면의 대시보드」 — app/static/home_dash.js · home_files.js homeFilesStart · workflow_exec.js) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 흉내 없이 진짜 끝점으로(서버 쪽 실행기 포함).

    python -X utf8 tools/smoke_home_dash_ui.py <그림·임시 폴더> [--port 18496]

보는 것:
- ① 첫 화면 오른쪽 열의 탭 둘(「대시보드」 · 「에이전트」 — 2026-11-20 「각각 별도의 탭으로」: 탭을 바꾸면 칸이 바뀌고 · 화살표 · 기억) · 대시보드 칸(#homeDash) — 머리 「대시보드」 · 도움말 · 한 줄 안내 · 워크플로우 고르기 목록(준비 중인 것 없음 · 목적 문서의 형식으로 할 수 있는 것만).
- ② 견본 두 파일(사업계획서 양식 · 연차보고서 서식)을 목록에 넣고 연차보고서를 목적 문서로 → 「사업계획서 → 연차보고서 이관」 을 고름 → 단계 흐름(묶음 넷 · 끝난 수 · 상태 글 없음) · 문서 칸 두 줄 · 「워크플로우 시작」 ·
  아직 아무것도 안 올림 · 문서가 셋이면 시작하지 않고 워크플로우 카드의 시작 길과 같은 알림.
- ③ 「워크플로우 시작」 → **문서 화면으로 넘어가지 않는다**(no-doc 그대로 · state.id 없음) · 두 문서가 같은 프로젝트(임시 이름) · 워크플로우 · 라운드로 올라감 · 묶음 1 에 끝난 수 · 상태 글 · 「한 번에 진행」,
  묶음 2~4 에 「문서 화면에서 진행합니다 …」 + 「한 번에 진행」(문서 화면에서) · 이 브라우저에 기억. 올린 직후의 기본 분석이 끝나면 저절로 「끝남 2/2」(검사 서버는 LLM 이 없어 LLM 검증·보완은 「건너뜀」).
- ④ 「한 번에 진행」: 두 작업을 초기화(진짜 끝점)해 남은 단계를 만든 뒤 — 도는 줄(지금 하는 일 · 지난 시간 · 「멈춤」) · 다른 탭의 대시보드에 같은 실행(「다른 화면에서 진행 중」) · 그 탭에서 「멈춤」 → 「멈춤 — …」(주황) /
  다시 초기화 → 「한 번에 진행」 → 끝 글 「끝남 — …」(초록) · 「끝남 2/2」 · 그동안 문서 화면으로 넘어가지 않음.
- ⑤ 새 탭(같은 브라우저 컨텍스트)에서 첫 화면을 열면 같은 대시보드 · 같은 끝 글(기억 + 서버 상태).
- ⑥ 「대시보드 자세히 보기」 → 그 목적 문서가 열리고 패널 탭 「대시보드」 ⑦ 로고로 첫 화면에 돌아오면 대시보드가 그대로 ⑦-2 서버가 안 맡은 묶음의 「한 번에 진행」 → 문서 화면을 열고 그 화면의 같은 단추(꺼져 있으면 까닭 알림 · 켜져 있으면 실제로 진행) ⑧ 「다른 워크플로우」 → 고르기로(기억도 비움) ⑨ 좁은 폭(820 · 400 · 320px)에서 가로 넘침 없음.
- 그 밖: 같은 파일로 다시 시작 → 「같은 파일 고르기」 의 「이어서」 → 같은 작업의 대시보드 · 문서 하나인 워크플로우(연차보고서 양식 맞추기 — 모든 묶음 「문서 화면에서 진행합니다 …」 + 「한 번에 진행」) · 취합은 「워크플로우 시작」 이 켜짐(문서 화면을 열고 시작)."""
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
ap.add_argument("--port", type=int, default=18496)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)

PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
REPORT = ROOT / "samples" / "국가RnD_서식" / "KEIT_표준서식_260320" / "1. 산업기술혁신사업 연차보고서 서식_260319.hwpx"
SMALL, DOCX = ROOT / "samples" / "기술수요조사서.hwpx", ROOT / "samples" / "기술수요조사서.docx"
JOB, JOB_NAME = "plan_to_report", "사업계획서 → 연차보고서 이관"
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1"}
env.setdefault("NFM_TASKS", str(tmp / "tasks.json"))   # 조립한 워크플로우는 임시 파일(run_ui_gates.py 가 이미 걸었으면 그것) — 사용자가 만든 것이 고르기 목록에 섞이지 않게
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_FLOW_EXEC"):   # NFM_FLOW_EXEC=client 면 서버 실행기가 꺼진다(모든 묶음이 「문서 화면에서 진행합니다」)
    env.pop(k, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails, dialogs = [], [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:900] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def works():
    return requests.get(f"{base}/api/works", timeout=10).json()


def flow(wid):
    return requests.get(f"{base}/api/works/{wid}/flow", timeout=30).json()


def served_counts(wid):
    """서버가 맡은 묶음의 (끝난 수, 단계 수) 합 — 머리의 「끝남 n/m」 과 같은 셈(home_dash.js hdLiveParts). 묶음을 서버로 옮길 때마다 수가 바뀌어 박지 않는다."""
    st = [g for g in flow(wid)["stages"] if g["server"]]
    return sum(g["done"] for g in st), sum(g["total"] for g in st)


def head_count(wid):
    d, t = served_counts(wid)
    return f"끝남 {d}/{t}"


# 대시보드의 지금 모습 — 상태 · 머리 · 도는 줄 · 끝 글 · 알림 · 문서 칸 · 묶음(번호 · 이름 · 끝난 수 · 단추 · 「문서 화면에서 진행합니다」 · 단계 줄) · 발의 단추 · 첫 화면인가
DASH = """() => { const d = document.getElementById('homeDash'), q = (s) => d.querySelector(s), t = (s) => (q(s) || {}).textContent || '';
  const btn = (b) => (b ? { text: b.textContent, off: !!b.disabled, primary: b.classList.contains('primary'), title: b.title } : null);
  return { state: d.dataset.state, title: t('.dash-title b'), count: t('.dash-count'), next: t('.dash-next'), help: (q('.dash-title .panel-help') || { dataset: {} }).dataset.help || '', wf: (q('.dash-wf') || {}).href || '',
    live: q('.dash-live') ? { head: t('.dash-live b'), text: t('.dash-live-text'), by: t('.home-dash-by'), stop: btn(q('.dash-live button')) } : null,
    last: t('.dash-last'), halt: !!q('.dash-last.halt'), notes: [...d.querySelectorAll('.dash-note')].map((n) => [n.textContent, n.classList.contains('warn')]),
    docs: [...d.querySelectorAll('.home-dash-docs li')].map((li) => li.textContent), opts: [...d.querySelectorAll('.home-dash-pick option')].map((o) => o.value),
    groups: [...d.querySelectorAll('.dash-group')].map((g) => ({ id: g.dataset.group, served: g.dataset.served === '1', no: g.querySelector('.dash-gno').textContent, name: g.querySelector('.dash-gname').textContent,
      count: g.querySelector('.dash-gcount').textContent, run: btn(g.querySelector('.dash-ghead button')), away: (g.querySelector('.home-dash-away') || {}).textContent || '', tags: [...g.querySelectorAll('.dash-ghead > .dash-tag')].map((x) => x.textContent),
      nodes: [...g.querySelectorAll('.dash-node')].map((n) => ({ key: n.dataset.key, state: n.dataset.state, no: n.querySelector('.dash-no').textContent, name: n.querySelector('.dash-node-head b').textContent,
        st: (n.querySelector('.dash-st') || {}).textContent || '', tags: n.querySelectorAll('.dash-tag').length, kids: n.children.length })) })),
    foot: [...d.querySelectorAll('.home-dash-foot button')].map(btn), why: t('.home-dash-foot .dash-why'),
    home: document.body.classList.contains('no-doc'), id: state.id, memo: (() => { try { return JSON.parse(localStorage.getItem('nfm.homeDash') || 'null'); } catch (e) { return 'err'; } })(),
    toast: document.getElementById('toast').hidden ? '' : document.getElementById('toast').textContent, files: hf.files.map((f) => f.name) }; }"""
FIT = """() => { const e = document.getElementById('empty'), a = document.getElementById('homeAgent').getBoundingClientRect(), d = document.getElementById('homeDash');
  return { over: e.scrollWidth > e.clientWidth + 1, dash: d.scrollWidth > d.clientWidth + 1, w: Math.round(a.width),
    inside: [...d.querySelectorAll('.dash-node, .dash-ghead, .dash-ghead .btn, .home-dash-foot .btn, select, .dash-live, .dash-last, .dash-note, .home-dash-docs li')].every((x) => { const r = x.getBoundingClientRect(); return r.left >= a.left - 0.5 && r.right <= a.right + 0.5; }) }; }"""


AWAY = "문서 화면에서 진행합니다 — 「한 번에 진행」 이 문서를 엽니다"   # 서버가 아직 맡지 않은 묶음의 머리 아래 한 줄


def snap(page):
    return page.evaluate(DASH)


def pick_files(page, paths):
    with page.expect_file_chooser() as fc:
        page.locator("#pickBtn").click()
    fc.value.set_files([str(p) for p in paths])
    page.wait_for_function("(n) => document.querySelectorAll('#homeFiles .hf-row').length >= n", arg=len(paths))


def run_btn(gid="review"):
    return f'#homeDash .dash-group[data-group="{gid}"] .dash-ghead button'


def reset_pair(ids):   # 작업 내용 초기화(진짜 끝점 — 헤딩 · 표 분석을 비운다): 서버가 맡은 묶음에 남은 단계를 만든다
    for wid in ids:
        r = requests.post(f"{base}/api/works/{wid}/reset", timeout=120)
        assert r.ok, (wid, r.status_code, r.text[:200])


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


def main():
    wait_server()
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        ctx.add_init_script("window.__opened = false; setInterval(() => { try { if (state.id) window.__opened = true; } catch (e) {} }, 40);")   # 문서 화면으로 넘어간 적이 있나(잠깐이라도)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        page.goto(base)
        page.wait_for_selector("#homeDash .dash-title")

        # ---- ① 첫 화면 오른쪽 열 — 머리 아래 · 대화 위에 대시보드 상자와 고르기 목록
        s = snap(page)
        TABS = """() => { const a = document.getElementById('homeAgent'), d = document.getElementById('homeDash'), p = document.getElementById('homeAgentPane'), r = d.getBoundingClientRect(), ar = a.getBoundingClientRect(),
          bar = a.querySelector('.agh-tabs').getBoundingClientRect(), t = a.querySelector('.agh-talk').getBoundingClientRect();
          return { kids: [...a.children].map((x) => x.id || x.className.split(' ')[0]), tabs: [...a.querySelectorAll('[role=tab]')].map((b) => [b.textContent, b.getAttribute('aria-selected'), b.tabIndex, b.getAttribute('aria-controls')]),
            dash: !d.hidden && r.height > 0, pane: !p.hidden, fill: Math.abs(r.top - bar.bottom) <= 1.5 && Math.abs(r.bottom - ar.bottom) <= 1.5, talk: Math.round(t.height), tab: a.dataset.tab,
            memo: (() => { try { return localStorage.getItem('nfm.homeTab'); } catch (e) { return 'err'; } })() }; }"""
        lay = page.evaluate("""() => { const a = document.getElementById('homeAgent'), d = document.getElementById('homeDash'), c = document.querySelector('.home-content').getBoundingClientRect(), ar = a.getBoundingClientRect();
          return { tag: d.tagName, role: d.getAttribute('role'), by: d.getAttribute('aria-labelledby'), cls: d.className, right: ar.left >= c.right - 1, w: Math.round(ar.width),
            sel: (d.querySelector('select') || { getAttribute: () => '' }).getAttribute('aria-label'), names: [...d.querySelectorAll('option')].map((o) => o.textContent) }; }""")
        tb = page.evaluate(TABS)
        check("① 첫 화면 오른쪽 열 — 탭 둘(「대시보드」 먼저 · 「에이전트」) › 탭 칸 둘(section#homeDash .dash.home-dash · #homeAgentPane) · 처음엔 대시보드 탭이 열의 남은 높이 전체(2026-11-20 사용자 「각각 별도의 탭으로」)",
              tb["kids"] == ["agh-tabs", "homeDash", "homeAgentPane"] and tb["tabs"] == [["대시보드", "true", 0, "homeDash"], ["에이전트", "false", -1, "homeAgentPane"]] and tb["dash"] and not tb["pane"] and tb["fill"]
              and lay["tag"] == "SECTION" and lay["role"] == "tabpanel" and lay["by"] == "homeTabDash" and lay["cls"].split() == ["dash", "home-dash"] and lay["right"] and 340 <= lay["w"] <= 420, [tb, lay])
        page.locator("#homeTabAgent").click()
        ta = page.evaluate(TABS)
        page.locator("#homeTabAgent").press("ArrowLeft")   # 화살표로 탭 사이(초점과 고름이 같이)
        tk = page.evaluate(TABS)
        check("① 「에이전트」 탭 — 대시보드는 감추고 대화 · 입력이 열 전체(대화 120px 넘음) · 고른 탭을 기억 / 왼쪽 화살표로 다시 「대시보드」",
              ta["tabs"][1][1] == "true" and not ta["dash"] and ta["pane"] and ta["talk"] >= 120 and ta["memo"] == "agent" and ta["tab"] == "agent"
              and tk["tabs"][0][1] == "true" and tk["dash"] and not tk["pane"] and tk["memo"] == "dash" and page.evaluate("() => document.activeElement.id") == "homeTabDash", [ta, tk])
        check("① 고르기 — 머리 「대시보드」 · 도움말(첫 문장 · 「대시보드 자세히 보기」) · 한 줄 안내 · 워크플로우 고르기 목록(준비 중인 것 없음) · 첫 화면 그대로",
              s["state"] == "pick" and s["title"] == "대시보드" and s["help"].startswith("대시보드에서 워크플로우의 단계와 진행 상황을 보고 바로 실행할 수 있습니다.")
              and "실행을 눌러도 이 화면에 머뭅니다 — 세부(단계마다의 확인 · 보정)는 「대시보드 자세히 보기」 로 문서 화면에서 봅니다." in s["help"]
              and s["next"] == "왼쪽에 문서를 넣고 목적 문서를 고른 뒤 워크플로우를 고르세요" and lay["sel"] == "워크플로우 고르기"
              and s["opts"] == ["", "plan_fit", "plan_merge", "plan_to_report", "report_fit", "doc_edit", "style_copy"] and JOB_NAME in lay["names"] and s["home"] and s["memo"] is None and not s["groups"], [s, lay])
        page.screenshot(path=str(OUT / "01_pick.png"))

        # ---- ② 문서 목록 → 목적 문서 → 워크플로우 고르기 → 단계 흐름(시작 전)
        pick_files(page, [PLAN, REPORT, DOCX])
        page.locator("#homeFiles .hf-row").nth(2).locator("input[type=radio]").check()
        page.wait_for_function("() => document.querySelectorAll('#homeDash option').length === 2")
        check("② 목적 문서가 docx 면 고르기 목록은 그 형식으로 할 수 있는 워크플로우만(문서 서식 복사)", snap(page)["opts"] == ["", "style_copy"], snap(page)["opts"])
        page.locator("#homeFiles .hf-row").nth(1).locator("input[type=radio]").check()
        page.wait_for_function("() => document.querySelectorAll('#homeDash option').length === 7")
        page.select_option("#homeDash select", JOB)
        page.wait_for_selector("#homeDash[data-state=ready] .dash-group")
        s = snap(page)
        nodes = [n for g in s["groups"] for n in g["nodes"]]
        check("② 고르면 단계 흐름 — 묶음 넷(등록부의 번호 · 이름) · 단계 열여섯(번호 01~16 · 꼬리표) · 끝난 수 · 상태 글 없음(문서를 읽기 전 — 「준비 중」 인 단계만 그 글) · 단추 없음 · 한 줄씩(펴지지 않음)",
              s["state"] == "ready" and s["title"] == JOB_NAME and [[g["no"], g["name"]] for g in s["groups"]] == [["1단계", "문서 검토"], ["2단계", "구성 맞추기"], ["3단계", "내용 넣기"], ["4단계", "문서 정리"]]
              and [n["no"] for n in nodes] == [f"{i:02d}" for i in range(1, 17)] and all(n["tags"] >= 1 and n["kids"] == 1 for n in nodes) and not s["count"]
              and all("/" not in g["count"] and g["count"].startswith("단계 ") and g["run"] is None and not g["away"] for g in s["groups"])
              and all(n["state"] in ("none", "soon") and n["st"] in ("", "준비 중") for n in nodes) and [n["key"] for n in nodes if n["state"] == "soon"] == ["later"] and s["wf"].endswith("/workflow#plan_to_report"), s)
        check("② 문서 칸 — 역할마다 한 줄(원본 → 목적 · 문서가 셋이라 원본 칸은 「하나만 둘 수 있습니다」) · 「워크플로우 시작」(강조) · 「다른 워크플로우」 · 아직 아무것도 안 올림",
              s["docs"] == ["원본 문서 — 사업계획서: 문서 2개 — 하나만 둘 수 있습니다", f"목적 문서 — 연차보고서: {REPORT.name}"] and [b["text"] for b in s["foot"]] == ["워크플로우 시작", "다른 워크플로우"]
              and s["foot"][0]["primary"] and not s["foot"][0]["off"] and not s["why"] and works() == [] and s["home"] and s["memo"] is None
              and page.evaluate("() => (document.activeElement.dataset || {}).hdFocus") == "start", s)   # 고른 뒤 초점은 「워크플로우 시작」 으로(고르기 목록이 사라져도 초점이 떨어지지 않는다)
        page.locator('#homeDash [data-hd-focus="start"]').click()
        page.wait_for_function("() => !document.getElementById('toast').hidden")
        s = snap(page)
        check("② 문서가 셋이면 시작하지 않는다 — 워크플로우 카드의 시작 길과 같은 알림(「남길 둘만 두세요」) · 아무것도 안 올림 · 대시보드는 시작 전 그대로",
              "이관은 연차보고서(목적 문서) 하나와 사업계획서 하나로 합니다 — 목록에 문서가 3개입니다. 남길 둘만 두세요" in s["toast"] and works() == [] and s["state"] == "ready" and not s["foot"][0]["off"], s)
        page.locator("#homeFiles .hf-row").nth(2).locator(".hf-del").click()
        page.wait_for_function("() => document.querySelectorAll('#homeDash .home-dash-docs li').length === 2 && !/하나만/.test(document.querySelector('#homeDash .home-dash-docs').textContent)")
        s = snap(page)
        check("② 문서 칸 두 줄 — 「원본 문서 — 사업계획서: …」 · 「목적 문서 — 연차보고서: …」(문서 목록의 목적 고르기대로)",
              s["docs"] == [f"원본 문서 — 사업계획서: {PLAN.name}", f"목적 문서 — 연차보고서: {REPORT.name}"], s["docs"])
        page.screenshot(path=str(OUT / "02_ready.png"))

        # ---- ③ 「워크플로우 시작」 — 문서 화면으로 넘어가지 않는다
        page.locator('#homeDash [data-hd-focus="start"]').click()
        page.wait_for_selector("#homeDash[data-state=live] .dash-group", timeout=180000)
        page.wait_for_function("() => !hf.busy && !homeTaskBusy", timeout=60000)
        s = snap(page)
        ws = works()
        rep = next((w for w in ws if (w.get("task") or {}).get("file") == "report"), {})
        plan = next((w for w in ws if (w.get("task") or {}).get("file") == "plan"), {})
        rid, pid = rep.get("id"), plan.get("id")
        proj = (rep.get("task") or {}).get("project") or ""
        check("③ 「워크플로우 시작」 → 문서 화면으로 넘어가지 않는다(no-doc 그대로 · state.id 없음 · 잠깐도 안 열림) · 쓴 문서는 목록에서 빠짐",
              s["home"] and s["id"] is None and not page.evaluate("() => window.__opened") and s["files"] == [] and page.evaluate("() => location.hash") == "", s)
        check("③ 두 문서가 같은 프로젝트(임시 이름) · 워크플로우 · 라운드로 올라감(목적 = 연차보고서 · 원본 = 사업계획서) · 이 브라우저에 기억 · 임시 이름 알림 한 줄",
              len(ws) == 2 and rep.get("task") == {"kind": "rnd", "file": "report", "job": JOB, "project": proj, "round": 1} and proj.startswith("임시 프로젝트 ")
              and plan.get("task") == {"kind": "rnd", "file": "plan", "job": JOB, "project": proj, "round": 1} and s["memo"] == {"job": JOB, "wid": rid}
              and any("임시 이름" in n[0] and not n[1] for n in s["notes"]), [ws, s["memo"], s["notes"]])
        g1, rest = s["groups"][0], s["groups"][1:]
        check("③ 묶음 1(서버가 맡음) — 끝난 수 n/2 · 단계마다 상태 글 · 「한 번에 진행」 / 묶음 2~4 — 「문서 화면에서 진행합니다 …」 · 끝난 수 · 상태 글 없음 · 그래도 「한 번에 진행」(문서 화면에서 — 2026-11-20 「그림만 보여주는게 아냐」)",
              s["title"] == JOB_NAME and g1["served"] and g1["count"] in ("0/2", "1/2", "2/2") and g1["run"] and g1["run"]["text"] == "한 번에 진행" and all(n["st"] for n in g1["nodes"])
              and g1["nodes"][0]["st"] == "✓ 끝남" and len(rest) == 3 and all(g["run"] and g["run"]["text"] == "한 번에 진행" for g in rest)   # 모든 묶음에 「한 번에 진행」 — 서버가 맡았나와 상관없이
              and all(not g["away"] if g["served"] else (g["away"] == AWAY and not g["run"]["primary"] and "문서 화면을 열고" in g["run"]["title"] and "/" not in g["count"]
                                                        and all(n["st"] in ("", "준비 중") for n in g["nodes"])) for g in rest)   # 안 맡은 묶음(걸음 2 · 3 이 들어가기 전) — 머리 아래 한 줄 · 상태 글 없음
              and s["count"].startswith("끝남 ") and s["count"].endswith(f"/{served_counts(rid)[1]}")
              and s["docs"] == [f"원본 문서 — 사업계획서: {plan.get('name')}", f"목적 문서 — 연차보고서: {rep.get('name')}"]
              and [b["text"] for b in s["foot"]] == ["대시보드 자세히 보기", "다른 워크플로우"], s)
        page.screenshot(path=str(OUT / "03_started.png"))
        # 올린 직후의 기본 분석(스크립트)이 끝나면 — LLM 이 없는 검사 서버에서는 LLM 검증·보완이 「건너뜀」 이라 저절로 2/2(3초마다 다시 읽는다)
        page.wait_for_function("() => (document.querySelector('#homeDash .dash-group[data-group=review] .dash-gcount') || {}).textContent === '2/2'", timeout=240000)
        s = snap(page)
        g1 = s["groups"][0]
        check("③ 기본 분석이 끝나면 저절로 「끝남 2/2」 — 02 「✓ 끝남」 · 03 「건너뜀」(LLM 없음) · 「한 번에 진행」 은 꺼지고 까닭 「남은 단계가 없습니다」 · 강조는 「대시보드 자세히 보기」 · 첫 화면 그대로",
              [n["st"] for n in g1["nodes"]] == ["✓ 끝남", "✓ 끝남", "건너뜀"] and [n["state"] for n in g1["nodes"]] == ["done", "done", "done"] and g1["count"] == "2/2" and g1["run"]["off"]
              and g1["run"]["title"] == "남은 단계가 없습니다" and s["home"]
              and (s["next"] == "1단계 끝남 — 그 밖의 묶음은 문서 화면에서 진행합니다" and s["foot"][0]["primary"]   # 뒤 묶음을 서버가 아직 안 맡을 때
                   or s["next"].startswith("다음: ") and any(g["served"] and g["run"] and not g["run"]["off"] for g in s["groups"][1:]))   # 2단계부터 서버가 맡으면(걸음 2) — 그 묶음의 다음 단계 · 단추가 켜짐
              and s["id"] is None and not s["live"] and not s["last"], s)

        # ---- ④ 「한 번에 진행」 — 남은 단계를 만들고(작업 내용 초기화 — 진짜 끝점) 서버 쪽 실행기로: 두 탭에서 잇달아 눌러도 한 번만 · 다른 탭에 같은 실행 · 그 탭에서 멈춤
        # (이 견본의 「문서 검토」 는 3~4초면 끝난다 — 다른 탭이 10초마다 다시 읽는 것으로는 도는 실행을 못 잡을 수 있어, 둘째 탭도 제 단추를 눌러 서버의 거절(이미 도는 실행)로 그 실행을 받는다)
        page2 = ctx.new_page()
        page2.on("pageerror", lambda e: errors.append(f"[pageerror 2] {e}"))
        page2.goto(base)
        page2.wait_for_selector("#homeDash[data-state=live] .dash-group", timeout=60000)
        reset_pair([rid, pid])
        on = f"() => {{ const b = document.querySelector('{run_btn()}'); return b && !b.disabled; }}"
        page.wait_for_function(on, timeout=30000)   # 10초마다 다시 읽는다 — 문서 화면 · 다른 곳에서 바뀐 상태를 따라간다
        page2.wait_for_function(on, timeout=30000)
        s = snap(page)
        g1 = s["groups"][0]
        check("④ 초기화한 뒤(다른 곳에서 바뀐 상태를 다시 읽음) — 0/2 · 「다음: 02 헤딩 · 표 분석」 · 「한 번에 진행」 이 켜지고 강조 · 풍선 도움말(이 화면에 머뭅니다 · 문서는 바뀌지 않습니다)",
              g1["count"] == "0/2" and s["count"] == head_count(rid) and s["next"] == "다음: 02 헤딩 · 표 분석" and [n["state"] for n in g1["nodes"]] == ["done", "now", "todo"] and g1["run"]["primary"]
              and "눌러도 이 화면에 머뭅니다" in g1["run"]["title"] and "문서는 바뀌지 않습니다" in g1["run"]["title"] and not s["foot"][0]["primary"] and not g1["tags"], s)
        n0 = len(dialogs)
        page.locator(run_btn()).click()
        page.wait_for_selector("#homeDash .dash-live", timeout=30000)
        s = snap(page)
        page2.locator(run_btn()).click()   # 둘째 탭은 아직 옛 상태(단추 켜짐)를 보고 있다 — 잇달아 눌러도 서버의 잠금이 한 번만 돌린다
        page2.wait_for_selector("#homeDash .dash-live", timeout=30000)
        s2 = snap(page2)
        page2.locator("#homeDash .dash-live button").click()   # 그 탭에서 「멈춤」(어느 화면에서나)
        check("④ 「한 번에 진행」 → 확인 창 없이 바로 · 도는 줄(묶음 이름 · 지금 하는 일 · 지난 시간 · 「멈춤」) · 「진행 중 — 1단계 문서 검토」 · 단추는 꺼짐 · 이 화면이 시작한 실행(꼬리표 없음) · 첫 화면 그대로",
              len(dialogs) == n0 and s["live"] and s["live"]["head"] == "1단계 문서 검토 — 한 번에 진행" and "초" in s["live"]["text"] and s["live"]["stop"]["text"] == "멈춤" and not s["live"]["by"]
              and s["next"] == "진행 중 — 1단계 문서 검토" and s["groups"][0]["run"]["off"] and s["home"] and s["id"] is None and not s["last"], s)
        check("④ 다른 탭에서 잇달아 누르면 — 새로 돌지 않고 거절 글 한 줄(「다른 화면에서 진행 중입니다 …」) + 이미 도는 그 실행(도는 줄 · 꼬리표 「다른 화면에서 진행 중」 · 「멈춤」)",
              s2["live"] and s2["live"]["head"] == s["live"]["head"] and s2["live"]["by"] == "다른 화면에서 진행 중" and s2["live"]["stop"]["text"] == "멈춤"
              and any(n[0].startswith("다른 화면에서 진행 중입니다") and n[1] for n in s2["notes"]) and s2["home"], s2)
        page.screenshot(path=str(OUT / "04_running.png"))
        page.wait_for_function("() => !document.querySelector('#homeDash .dash-live') && !!document.querySelector('#homeDash .dash-last')", timeout=240000)
        s = snap(page)
        runs = requests.get(f"{base}/api/works/{pid}/flow/runs", timeout=10).json()["runs"]   # 원본 문서의 id 로 물어도 같은 묶음의 기록
        check("④ 다른 탭에서 「멈춤」 → 지금 하던 일이 끝나면 멈춤 — 끝 글 「멈춤 — …」(주황) · 도는 줄 없음 · 실행은 하나뿐(첫 화면에서 시작 · 목적 문서의 기록) · 첫 화면 그대로",
              s["last"].startswith("멈춤 — 멈춤을 눌러 멈췄습니다") and s["halt"] and not s["live"] and s["home"] and s["id"] is None
              and len(runs) == 1 and runs[0]["status"] == "stopped" and runs[0]["origin"]["where"] == "home" and runs[0]["docs"]["target"]["id"] == rid, [s, runs])
        page2.wait_for_function("() => !document.querySelector('#homeDash .dash-live') && !!document.querySelector('#homeDash .dash-last')", timeout=60000)
        check("④ 두 탭이 같은 끝 글", snap(page2)["last"] == s["last"], [snap(page2)["last"], s["last"]])
        page2.close()
        # 다시 남은 단계를 만들고 끝까지
        reset_pair([rid, pid])
        page.wait_for_function(f"() => {{ const b = document.querySelector('{run_btn()}'); return b && !b.disabled; }}", timeout=30000)
        s = snap(page)
        check("④ 초기화한 작업 — 지난 실행의 끝 글도 사라진다(실행 기록은 초기화가 옮긴다 — 서버의 상태 그대로) · 다시 0/2 · 「한 번에 진행」 강조",
              not s["last"] and not s["live"] and s["count"] == head_count(rid) and s["groups"][0]["run"]["primary"], s)
        page.locator(run_btn()).click()
        page.wait_for_selector("#homeDash .dash-live", timeout=30000)
        page.set_viewport_size({"width": 1600, "height": 700})   # 탭 칸이 열 전체라 1000px 창에서는 넘치지 않을 수 있다 — 낮은 창에서 발이 붙는지 본다
        page.wait_for_timeout(200)
        box = page.evaluate("""() => { const d = document.getElementById('homeDash').getBoundingClientRect(), f = document.querySelector('#homeDash .home-dash-foot').getBoundingClientRect(), a = document.getElementById('homeAgent').getBoundingClientRect();
          return { foot: Math.abs(f.bottom - d.bottom) <= 1.5, share: d.height / a.height, scroll: document.getElementById('homeDash').scrollHeight > document.getElementById('homeDash').clientHeight }; }""")
        check("④ 단계가 많아 상자가 스크롤해도 발의 단추 줄은 상자 아래 끝에 붙어 보인다 · 상자는 탭 줄 아래 열 전체(대화는 다른 탭)", box["foot"] and box["scroll"] and box["share"] >= 0.85, box)
        page.set_viewport_size({"width": 1600, "height": 1000})
        page.wait_for_function("() => !document.querySelector('#homeDash .dash-live') && /^끝남 — /.test((document.querySelector('#homeDash .dash-last') || {}).textContent || '')", timeout=300000)
        s = snap(page)
        end = s["last"]
        rec = flow(rid)
        check("④ 끝까지 — 끝 글 「끝남 — …」(초록: 두 문서의 헤딩 그래프·표 구조가 있습니다 · LLM 검증·보완은 건너뜀 — 문서 화면의 끝 글과 같은 글) · 「끝남 2/2」 · 03 「건너뜀」 · 서버의 상태와 같음 · 그동안 문서 화면으로 넘어가지 않음",
              end.startswith("끝남 — 두 문서의 헤딩 그래프·표 구조가 있습니다") and "사업계획서 LLM 검증·보완은 건너뜀(LLM 을 쓸 수 없음)" in end and not s["halt"] and s["count"] == head_count(rid) and s["groups"][0]["count"] == "2/2"
              and [n["st"] for n in s["groups"][0]["nodes"]] == ["✓ 끝남", "✓ 끝남", "건너뜀"] and rec["last"]["status"] == "done" and rec["last"]["end"]["text"] == end and rec["stages"][0]["done"] == 2
              and rec["last"]["origin"]["where"] == "home" and s["home"] and s["id"] is None and not page.evaluate("() => window.__opened"), [s, rec.get("last")])
        page.screenshot(path=str(OUT / "05_done.png"))

        # ---- ⑤ 새 탭 — 같은 대시보드 · 같은 끝 글(기억 + 서버 상태)
        page3 = ctx.new_page()
        page3.goto(base)
        page3.wait_for_selector("#homeDash[data-state=live] .dash-last", timeout=60000)
        s3 = snap(page3)
        check("⑤ 새 탭에서 첫 화면을 열면 같은 대시보드 — 워크플로우 · 끝난 수 · 끝 글 · 묶음의 상태가 같다",
              s3["title"] == s["title"] and s3["count"] == s["count"] and s3["last"] == end and s3["groups"] == s["groups"] and s3["docs"] == s["docs"] and s3["home"], [s3, s])
        page3.close()

        # ---- ⑨ 좁은 폭 — 가로 넘침 없음(시작한 뒤의 꼴)
        for width in (820, 400, 320):
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(300)
            fit = page.evaluate(FIT)
            check(f"⑨ 좁은 창({width}px) — 대시보드가 가로로 넘치지 않음(묶음 머리 · 단계 줄 · 끝 글 · 단추가 열 안)", not fit["over"] and not fit["dash"] and fit["inside"], fit)
            if width == 400:
                page.locator("#homeAgent").screenshot(path=str(OUT / "09_narrow_400.png"))
        page.set_viewport_size({"width": 1600, "height": 1000})
        page.wait_for_timeout(200)

        # ---- ⑥ 「대시보드 자세히 보기」 → 그 목적 문서 + 패널 탭 「대시보드」 ⑦ 로고 → 첫 화면에 대시보드 그대로
        page.locator('#homeDash [data-hd-focus="more"]').click()
        page.wait_for_function("(id) => state.id === id && document.getElementById('panel').dataset.tool === 'Dash' && !!document.querySelector('#paneDash .dash-group')", arg=rid, timeout=180000)
        d = page.evaluate("""() => ({ home: document.body.classList.contains('no-doc'), tab: document.getElementById('tabDash').getAttribute('aria-selected'), pane: !document.getElementById('paneDash').hidden,
          title: (document.querySelector('#paneDash .dash-title b') || {}).textContent || '', groups: [...document.querySelectorAll('#paneDash .dash-gname')].map((x) => x.textContent), job: (state.task || {}).job }) """)
        check("⑥ 「대시보드 자세히 보기」 → 목적 문서(연차보고서)가 열리고 패널 탭 「대시보드」 — 같은 워크플로우의 단계 흐름(세부는 여기서)",
              not d["home"] and d["tab"] == "true" and d["pane"] and d["job"] == JOB and d["title"] == JOB_NAME and d["groups"] == ["문서 검토", "구성 맞추기", "내용 넣기", "문서 정리"], d)
        page.screenshot(path=str(OUT / "06_doc_dash.png"))
        page.locator("#homeLink").click()
        page.wait_for_function("() => document.body.classList.contains('no-doc') && state.id == null")
        page.wait_for_timeout(2500)   # 1초 타이머가 돌아온 것을 알고 다시 읽는다
        page.evaluate("() => { window.__opened = false; }")   # ⑥ 에서 일부러 열었다 — 아래 장면들은 다시 첫 화면에 머무는지 본다
        s = snap(page)
        check("⑦ 로고로 첫 화면에 돌아오면 대시보드가 그대로 — 같은 워크플로우 · 끝난 수 · 끝 글 · 기억",
              s["state"] == "live" and s["title"] == JOB_NAME and s["count"] == head_count(rid) and s["last"] == end and s["memo"] == {"job": JOB, "wid": rid} and s["home"], s)


        # ---- ⑧ 「다른 워크플로우」 → 고르기로(기억도 비움 — 문서 · 작업은 그대로)
        page.locator('#homeDash [data-hd-focus="other"]').click()
        page.wait_for_selector("#homeDash[data-state=pick] select")
        s = snap(page)
        check("⑧ 「다른 워크플로우」 → 고르기로 · 기억을 비움 · 작업은 그대로 · 초점은 고르기 목록으로", s["state"] == "pick" and s["title"] == "대시보드" and s["memo"] is None and len(s["opts"]) == 7 and len(works()) == 2
              and page.evaluate("() => (document.activeElement.dataset || {}).hdFocus") == "pick", s)
        for width in (820, 320):
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(300)
            fit = page.evaluate(FIT)
            check(f"⑨ 좁은 창({width}px) — 고르기 목록이 가로로 넘치지 않음", not fit["over"] and not fit["dash"] and fit["inside"], fit)
        page.set_viewport_size({"width": 1600, "height": 1000})

        # ---- 같은 파일로 다시 시작 → 「같은 파일 고르기」 의 「이어서」 → 같은 작업의 대시보드(다시 올리지 않음)
        pick_files(page, [REPORT])
        page.select_option("#homeDash select", JOB)
        page.wait_for_selector("#homeDash[data-state=ready] .dash-group")
        s = snap(page)
        check("목적 문서 하나만으로도 시작 전 — 원본 칸은 「없음」", s["docs"] == ["원본 문서 — 사업계획서: 없음", f"목적 문서 — 연차보고서: {REPORT.name}"] and not s["foot"][0]["off"], s)
        page.locator('#homeDash [data-hd-focus="start"]').click()
        page.wait_for_selector('.sf-pop [data-sf="use"]', timeout=120000)
        sf = page.evaluate("() => ({ rows: [...document.querySelectorAll('.sf-pop .sf-row')].map((r) => r.dataset.work), busy: hf.busy, start: document.querySelector('#homeDash [data-hd-focus=start]').textContent, home: document.body.classList.contains('no-doc') })")
        check("같은 파일로 하던 작업이 있으면 「같은 파일 고르기」 — 그 작업 줄 · 목록 줄은 「고르세요」 · 단추는 「문서 준비 중…」 · 첫 화면 그대로",
              sf["rows"] == [rid] and "고르세요" in sf["busy"] and sf["start"] == "문서 준비 중…" and sf["home"], sf)
        page.locator('.sf-pop [data-sf="use"]').click()
        page.wait_for_selector("#homeDash[data-state=live] .dash-last", timeout=120000)
        s = snap(page)
        check("「이어서」 → 같은 작업의 대시보드(새 작업을 만들지 않음 · 원본 문서는 그 묶음의 것 그대로 · 끝난 수 · 끝 글) · 알림 「이어서 합니다」 · 첫 화면 그대로",
              s["memo"] == {"job": JOB, "wid": rid} and len(works()) == 2 and s["count"] == head_count(rid) and s["last"] == end and s["docs"][0].startswith("원본 문서 — 사업계획서: 연구개발계획서_양식")
              and any("같은 파일로 하던 작업을 이어서 합니다" in n[0] for n in s["notes"]) and s["home"] and s["id"] is None and s["files"] == [], s)

        # ---- 취합 — 아직 대시보드에서 시작하지 않는다 / 문서 하나인 워크플로우 — 모든 묶음이 문서 화면
        page.locator('#homeDash [data-hd-focus="other"]').click()
        page.wait_for_selector("#homeDash[data-state=pick] select")
        pick_files(page, [SMALL])
        page.select_option("#homeDash select", "plan_merge")
        page.wait_for_selector("#homeDash[data-state=ready] .dash-group")
        s = snap(page)
        check("취합을 고르면 단계 흐름 · 「워크플로우 시작」 이 켜짐(문서 화면을 열고 시작 — 워크플로우 카드의 길: 2026-11-20 「그림만 보여주는게 아냐」) · 묶음 이름은 취합의 것",
              not s["foot"][0]["off"] and s["foot"][0]["primary"] and not s["why"] and "문서 화면으로 넘어갑니다" in s["foot"][0]["title"] and s["next"] == "시작 전 — 「워크플로우 시작」 을 누르면 문서 화면을 열고 시작합니다"
              and [[g["no"], g["name"]] for g in s["groups"]] == [["1단계", "프로젝트 구성"], ["2단계", "문서 프레임 작성"], ["3단계", "내용 매핑"]]
              and s["docs"][0].startswith("원본 문서 — 기관 문서(문서마다): ") and s["docs"][1] == f"목적 문서 — 취합본: {SMALL.name}", s)
        page.locator('#homeDash [data-hd-focus="other"]').click()
        page.wait_for_selector("#homeDash[data-state=pick] select")
        page.select_option("#homeDash select", "report_fit")
        page.wait_for_selector("#homeDash[data-state=ready] .dash-group")
        check("문서 하나인 워크플로우 — 문서 칸 한 줄(「작업 문서 — 연차보고서: …」)", snap(page)["docs"] == [f"작업 문서 — 연차보고서: {SMALL.name}"], snap(page)["docs"])
        n = len(works())
        page.locator('#homeDash [data-hd-focus="start"]').click()
        page.wait_for_selector("#homeDash[data-state=live] .dash-group", timeout=180000)
        page.wait_for_function("() => !hf.busy && !homeTaskBusy", timeout=60000)
        s = snap(page)
        one = next((w for w in works() if (w.get("task") or {}).get("job") == "report_fit"), {})
        check("문서 하나인 워크플로우를 시작 — 문서 화면으로 넘어가지 않고 작업이 생김(워크플로우 · 임시 프로젝트 · 라운드 1) · 모든 묶음 「문서 화면에서 진행합니다 …」 + 「한 번에 진행」(끝난 수 없음) · 강조는 「대시보드 자세히 보기」",
              len(works()) == n + 1 and one.get("task", {}).get("file") == "report" and one["task"].get("round") == 1 and one["task"]["project"].startswith("임시 프로젝트 ") and s["memo"] == {"job": "report_fit", "wid": one.get("id")}
              and s["groups"] and all(not g["served"] and g["away"] == AWAY and g["run"] and g["run"]["text"] == "한 번에 진행" and not g["run"]["off"] for g in s["groups"]) and not s["count"]
              and s["next"] == "이 워크플로우의 묶음은 문서 화면에서 진행합니다" and s["foot"][0]["primary"] and s["home"] and s["id"] is None and not page.evaluate("() => window.__opened"), s)
        page.screenshot(path=str(OUT / "10_single.png"))

        # ---- ⑦-2 서버가 아직 맡지 않은 묶음의 「한 번에 진행」(2026-11-20 「그림만 보여주는게 아냐」) — 목적 문서를 열고 그 화면 대시보드의 같은 묶음 단추를 누른다(그 단추의 검사 · 실행 그대로)
        # 문서 하나인 워크플로우로 본다(이관은 걸음 2 · 3 에서 모든 묶음을 서버가 맡는다). 「구성 반영」 은 그 화면의 단추가 꺼져 있다(프로젝트 구성을 확정하기 전) → 누르지 않고 그 까닭을 알린다
        oid, names = one.get("id"), {g["id"]: g["name"] for g in s["groups"]}
        page.locator('#homeDash [data-hd-focus="away:frame"]').click()
        page.wait_for_function("(id) => state.id === id && document.getElementById('panel').dataset.tool === 'Dash' && !document.getElementById('toast').hidden && /지금 누를 수 없습니다/.test(document.getElementById('toast').textContent)", arg=oid, timeout=180000)
        t = page.evaluate("() => ({ toast: document.getElementById('toast').textContent, off: (document.querySelector('#dashBox .dash-group[data-group=\"frame\"] [data-dash-focus=\"run:frame\"]') || {}).disabled, fit: typeof divRun !== 'undefined' && !!divRun })")
        check("⑦-2 안 맡은 묶음 「구성 반영」 의 「한 번에 진행」 → 목적 문서가 열리고 패널 「대시보드」 · 그 화면의 단추가 꺼져 있어 누르지 않고 까닭을 알림(「프로젝트 구성 값을 먼저 확정하세요」)",
              t["off"] is True and f"「{names.get('frame')}」 의 「한 번에 진행」 을 지금 누를 수 없습니다 — 프로젝트 구성 값을 먼저 확정하세요" in t["toast"] and not t["fit"], [t, names])
        page.locator("#homeLink").click()
        page.wait_for_function("() => document.body.classList.contains('no-doc') && state.id == null")
        page.wait_for_timeout(2500)
        # 「프로젝트 구성」 은 그 화면에 「한 번에 진행」 이 없다(단계마다 하는 묶음) → 그 묶음을 보이고 알린다
        page.locator('#homeDash [data-hd-focus="away:config"]').click()
        page.wait_for_function("(id) => state.id === id && !document.getElementById('toast').hidden && /단계마다 진행합니다/.test(document.getElementById('toast').textContent)", arg=oid, timeout=180000)
        t = page.evaluate("() => document.getElementById('toast').textContent")
        check("⑦-2 그 화면에 「한 번에 진행」 이 없는 묶음 → 문서를 열고 그 묶음을 보이며 「단계마다 진행합니다」", f"「{names.get('config')}」" in t and "단계마다 진행합니다 — 대시보드의 단계 카드에서 누르세요" in t, t)
        page.locator("#homeLink").click()
        page.wait_for_function("() => document.body.classList.contains('no-doc') && state.id == null")
        page.wait_for_timeout(2500)
        page.evaluate("() => { window.__opened = false; }")

        # ---- 같은 파일 고르기의 「그대로 열기」 — 다른 워크플로우의 작업이면 알림만(그 작업의 워크플로우를 바꾸지 않는다) · 같은 워크플로우의 작업이면 그 작업의 대시보드
        page.locator('#homeDash [data-hd-focus="other"]').click()
        page.wait_for_selector("#homeDash[data-state=pick] select")
        pick_files(page, [SMALL])
        page.select_option("#homeDash select", "plan_fit")
        page.wait_for_selector("#homeDash[data-state=ready] .dash-group")
        page.locator('#homeDash [data-hd-focus="start"]').click()
        page.wait_for_selector('.sf-pop [data-sf="open"]', timeout=120000)
        acts = page.evaluate("() => [...document.querySelectorAll('.sf-pop .sf-row')].map((r) => [r.dataset.work, [...r.querySelectorAll('.sf-acts [data-sf]')].map((b) => b.dataset.sf)])")
        page.locator('.sf-pop [data-sf="open"]').click()
        page.wait_for_function("() => /다른 워크플로우의 작업입니다/.test(document.getElementById('toast').textContent) && !document.getElementById('toast').hidden && !hf.busy", timeout=60000)
        s = snap(page)
        check("다른 워크플로우를 하던 같은 파일 — 그 줄은 「그대로 열기」 만 → 알림 「다른 워크플로우의 작업입니다 — 문서 화면에서 여세요」 · 대시보드는 시작 전 그대로 · 그 작업의 워크플로우는 그대로 · 첫 화면 그대로",
              acts == [[one.get("id"), ["open"]]] and s["state"] == "ready" and s["title"] == "사업계획서 양식 표준화" and s["memo"] is None and s["home"] and s["id"] is None and s["files"] == [SMALL.name]
              and next(w for w in works() if w["id"] == one.get("id"))["task"]["job"] == "report_fit" and len(works()) == n + 1, [acts, s])
        page.locator("#homeFiles .hf-clear").click()
        page.locator('#homeDash [data-hd-focus="other"]').click()
        page.wait_for_selector("#homeDash[data-state=pick] select")
        pick_files(page, [REPORT])
        page.locator("#homeFiles [data-hf-focus=project]").fill("다른 프로젝트 P")
        page.select_option("#homeDash select", JOB)
        page.wait_for_selector("#homeDash[data-state=ready] .dash-group")
        page.locator('#homeDash [data-hd-focus="start"]').click()
        page.wait_for_selector('.sf-pop [data-sf="open"]', timeout=120000)
        why = page.evaluate("() => (document.querySelector('.sf-pop .sf-why') || {}).textContent || ''")
        page.locator('.sf-pop [data-sf="open"]').click()
        page.wait_for_selector("#homeDash[data-state=live] .dash-last", timeout=60000)
        s = snap(page)
        check("같은 워크플로우(다른 프로젝트)를 하던 같은 파일의 「그대로 열기」 → 그 작업의 대시보드(끝난 수 · 끝 글 · 기억) · 새 작업을 만들지 않음 · 그 작업의 프로젝트는 그대로 · 첫 화면 그대로",
              "다른 프로젝트" in why and s["memo"] == {"job": JOB, "wid": rid} and s["count"] == head_count(rid) and s["last"] == end and len(works()) == n + 1 and s["home"] and s["id"] is None
              and next(w for w in works() if w["id"] == rid)["task"]["project"] == proj and not page.evaluate("() => window.__opened"), [why, s])
        # ---- 취합 — 「워크플로우 시작」 은 문서 화면을 열고 시작(워크플로우 카드의 길) → 첫 화면으로 돌아오면 그 작업의 대시보드 · 안 맡은 묶음의 「한 번에 진행」 이 실제로 돈다(문서 화면의 실행)
        if page.evaluate("() => hf.files.length"):
            page.locator("#homeFiles .hf-clear").click()
        page.locator('#homeDash [data-hd-focus="other"]').click()
        page.wait_for_selector("#homeDash[data-state=pick] select")
        pick_files(page, [SMALL])
        page.select_option("#homeDash select", "plan_merge")
        page.wait_for_selector("#homeDash[data-state=ready] .dash-group")
        page.locator('#homeDash [data-hd-focus="start"]').click()
        page.wait_for_selector('.sf-pop [data-sf="new"]', timeout=120000)   # 앞 장면들이 올린 같은 파일 — 「새로 올리기」
        page.locator('.sf-pop [data-sf="new"]').click()
        page.wait_for_function("() => !!state.id && (state.task || {}).job === 'plan_merge' && !hf.busy && !homeTaskBusy", timeout=180000)
        gid = page.evaluate("() => state.id")
        g = page.evaluate("() => ({ memo: JSON.parse(localStorage.getItem('nfm.homeDash') || 'null'), file: (state.task || {}).file })")
        check("취합 「워크플로우 시작」 → 문서 화면으로 넘어가 목적 문서(취합본)로 시작 · 그 작업을 이 브라우저에 기억", g["memo"] == {"job": "plan_merge", "wid": gid}, g)
        page.locator("#homeLink").click()
        page.wait_for_function("() => document.body.classList.contains('no-doc') && state.id == null")
        page.wait_for_selector("#homeDash[data-state=live] .dash-group", timeout=60000)
        s = snap(page)
        check("첫 화면으로 돌아오면 취합의 대시보드(시작한 뒤) — 모든 묶음에 「한 번에 진행」(서버가 아직 안 맡음 — 문서 화면에서)",
              s["title"] == "사업계획서 취합" and s["groups"] and all(not g["served"] and g["away"] == AWAY and g["run"] and g["run"]["text"] == "한 번에 진행" and not g["run"]["off"] for g in s["groups"]), s)
        page.locator('#homeDash [data-hd-focus="away:config"]').click()
        page.wait_for_function("""(id) => state.id === id && ((typeof gatherRunLast !== 'undefined' && !!gatherRunLast && gatherRunLast.stage === 'config' && !gatherRun)
          || (!document.getElementById('toast').hidden && /「한 번에 진행」|단계마다|찾지 못했습니다/.test(document.getElementById('toast').textContent)))""", arg=gid, timeout=180000)   # 끝 글 — 또는 누르지 못한 까닭(실패할 때 그 글이 보이게)
        t = page.evaluate("""() => { const b = document.querySelector('#dashBox .dash-group[data-group="config"] [data-dash-focus="run:config"]');
          return { tool: document.getElementById('panel').dataset.tool, last: gatherRunLast, toast: document.getElementById('toast').hidden ? '' : document.getElementById('toast').textContent, btn: b ? [b.disabled, b.title] : null }; }""")
        check("취합 「1단계 프로젝트 구성」 의 「한 번에 진행」(첫 화면) → 목적 문서를 열고 그 묶음을 실제로 진행(문서 화면의 실행 — 끝 글이 남음)", t["tool"] == "Dash" and (t["last"] or {}).get("stage") == "config" and (t["last"] or {}).get("plan") == gid, t)
        page.screenshot(path=str(OUT / "11_gather_away_run.png"))
        real = [e for e in errors if "409" not in e]
        check("콘솔 오류 없음", not real, real[:5])
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

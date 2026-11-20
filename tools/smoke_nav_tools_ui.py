"""`/workflow` 목차의 「워크플로우 도구」(spec_워크플로우 ② §18-18 · design.md §23 — app/static/workflow.js navToolsDraw · navToolEl · dropFindNew · dropAdd) 화면 확인 —
임시 서버(임시 조립 저장소, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 흉내 없이 진짜 끝점으로.

    python -X utf8 tools/smoke_nav_tools_ui.py <그림·임시 폴더> [--port 18760]

2026-11-21 사용자 「여기 있는 도구는 첫번째 사이드 패널에 리스트로 있어야 하고, 여기 리스트에서 드래그로 워크플로우 도구를 넣을 수 있고, 그리고 도구는 묶음을 했으면 좋겠는데 …
'일반', '사업계획서' 이런식으로 묶으면 좋을 듯」.

보는 것:
- ① 폼이 없을 때 — 목차의 「워크플로우 도구」 = 조립에 놓는 도구 모두(새 워크플로우의 틀 = 이관형: 서버 units 와 같은 수 · 같은 차례) · 분류 = 「일반」 먼저, 그 뒤 서버의 전용 이름에서 「 전용」 을 뗀 것 ·
  도구는 아직 끌 수 없음 · 등록부의 「도구」 목록은 그 아래 그대로.
- ② 도구를 누르면 새 조립 폼이 열리고 오른쪽 「도구 설명」 열에 그 도구 · 목차의 그 줄이 눌린 표시 · 이제 끌 수 있음.
- ③ 「헤딩 · 표 분석」(일반)을 끌어 4단계 묶음의 행 사이에 놓으면 목적 문서 칸에 새 행 · 원본 문서 칸에 놓으면 원본 문서의 줄 · 빈칸에 놓으면 같은 차례 · 놓은 도구의 설명이 오른쪽에.
- ④ 쌍 도구(빈 자리 검토)를 끌어 놓으면 쌍 줄(행째) · 앞 도구가 없는 자리(1단계)에 놓으면 막지 않고 서버 검사의 거절 글이 보인다.
- ⑤ 틀을 「N → 1」 로 바꾸면 목록이 취합형의 도구로(「기관 문서 → 사업계획서」 분류) · 「1」 로 바꾸면 문서 하나의 도구.
- ⑥ 「취소」 → 폼이 없는 목록으로(끌 수 없음) · 좁은 창(800px)에서는 서지 않는다 · 콘솔 오류 없음.
- ⑦ 전용 이름(units[].only)을 안 주는 서버(② §18-17 전 — 응답만 바꿈) → 모두 「일반」 이 아니라 사는 단계로 묶는다."""
import argparse
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
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1",
       "NFM_TASKS": str(tmp / "tasks.json"), "NFM_FORM_FILES": str(tmp / "form_files"), "NFM_AGENT_NOTES": str(tmp / "agent_notes.json")}   # 조립 저장소 · 덧붙이는 글 — 늘 임시
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_FLOW_EXEC"):
    env.pop(k, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []


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


# 목차의 「워크플로우 도구」 — 머리(수) · 안내 · 분류마다 [이름, 종류, [[도구 key, 이름, 끌 수 있나, 눌림]]] · 상자가 보이나 · 등록부 「도구」 머리가 그 뒤에 있나
NAV = """() => { const box = document.querySelector('#wfNav .wf-nav-tools'); if (!box) return null;
  const h2 = box.querySelector('h2'), next = box.nextElementSibling;
  return { shown: !box.hidden && getComputedStyle(box).display !== 'none' && box.getBoundingClientRect().height > 0, head: h2 ? h2.textContent : '', count: h2 ? +h2.dataset.count : -1,
    hint: (box.querySelector('.wf-nav-hint') || {}).textContent || '',
    groups: [...box.querySelectorAll('.wf-nav-group')].map((g) => [g.querySelector('.wf-nav-group-name').textContent, g.dataset.kind,
      [...g.querySelectorAll('[data-tool]')].map((b) => [b.dataset.tool, b.querySelector('.wf-nav-tool-name').textContent, b.draggable, b.getAttribute('aria-pressed') === 'true'])]),
    after: next && next.tagName === 'H2' ? next.textContent : '' }; }"""

# 조립 폼의 줄 목록 — 묶음마다 행 [보이는 줄 key, 문서] · 서버 검사의 거절 · 경고 · 「도구 설명」 열의 도구
LINES = """() => { const box = document.querySelector('#wfCompose .wf-lines'); if (!box) return null;
  return { groups: [...box.querySelectorAll('.wf-lines-group')].map((g) => [...g.querySelectorAll('.wf-line')].map((l) => [l.dataset.unit, l.dataset.role || ''])),
    errs: [...box.querySelectorAll('.wf-lines-err li')].map((x) => x.textContent), warns: [...box.querySelectorAll('.wf-lines-warn li')].map((x) => x.textContent),
    help: (document.querySelector('#wfCompose .wf-help') || {}).dataset ? document.querySelector('#wfCompose .wf-help').dataset.unit || '' : null }; }"""


def settle(page):
    page.wait_for_function("() => { const b = document.querySelector('#wfCompose .wf-lines'); return b && !/검사하는 중/.test(b.textContent) && !!b.querySelector('.wf-lines-check'); }", timeout=30000)
    page.wait_for_timeout(350)   # 줄을 고친 뒤 검사를 거는 틈(250ms)
    page.wait_for_function("() => { const b = document.querySelector('#wfCompose .wf-lines'); return b && !/검사하는 중/.test(b.textContent); }", timeout=30000)
    return page.evaluate(LINES)


def kinds_of(units):
    """서버 units → 분류의 기대(일반 먼저 · 그 뒤 처음 나온 차례 — 화면은 NAV_KINDS 차례지만 서버의 차례와 같다: 셋 다 처음 나온 차례로 본다)."""
    out = {}
    for u in units:
        o = u.get("only") or {}
        k = o.get("kind") or ""
        name = (o.get("label") or "").removesuffix(" 전용").strip() if k else "일반"
        out.setdefault(k, [name, []])[1].append(u["key"])
    order = ["", "rnd", "relay", "gather"]
    return [[out[k][0], k or "general", out[k][1]] for k in order if k in out] + [[v[0], k, v[1]] for k, v in out.items() if k not in order]


def main():
    wait_server()
    T = requests.get(base + "/api/tasks?v=2", timeout=10).json()
    relay = kinds_of(T["units"])
    gather = kinds_of(T["byShape"]["gather"]["units"])
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1500, "height": 1000}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/workflow#overview")
        page.wait_for_selector("#wfNav .wf-nav-tools [data-tool]")

        # ---- ① 폼이 없을 때
        n = page.evaluate(NAV)
        got = [[g[0], g[1], [t[0] for t in g[2]]] for g in n["groups"]]
        check("① 목차의 「워크플로우 도구」 — 새 워크플로우의 틀(이관형)의 도구 모두 · 서버 units 와 같은 수 · 분류 = 「일반」 먼저 + 전용 이름에서 「 전용」 을 뗀 것 · 등록부의 「도구」 머리가 그 아래",
              n["shown"] and n["head"] == "워크플로우 도구" and n["count"] == len(T["units"]) and got == relay and got[0][0] == "일반"
              and "사업계획서 · 연차보고서" in [g[0] for g in got] and "사업계획서 → 연차보고서" in [g[0] for g in got] and n["after"] == "도구", [n, relay])
        check("① 폼이 없으면 끌 수 없다 · 안내 「누르면 설명 · 조립 폼을 열면 끌어서 넣습니다」 · 눌린 도구 없음",
              all(not t[2] and not t[3] for g in n["groups"] for t in g[2]) and n["hint"].startswith("누르면 설명"), n)
        page.screenshot(path=str(OUT / "01_nav.png"), clip={"x": 0, "y": 0, "width": 260, "height": 1000})

        # ---- ② 누르면 새 조립 폼 + 설명
        page.click("#wfNav .wf-nav-tool[data-tool=link]")
        s = settle(page)
        n = page.evaluate(NAV)
        pressed = [t[0] for g in n["groups"] for t in g[2] if t[3]]
        check("② 「자리 연결」 을 누르면 새 조립 폼이 열리고 「도구 설명」 열에 그 도구 · 목차의 그 줄이 눌림 · 이제 끌 수 있다(사람이 하는 일까지) · 안내 「끌어서 조립 폼(1 → N)의 묶음에 …」",
              s is not None and s["help"] == "link" and page.locator("#wfCompose .wf-help-unit[data-unit=link]").count() == 1 and pressed == ["link"]
              and all(t[2] for g in n["groups"] for t in g[2]) and "조립 폼(1 → N)" in n["hint"], [s and s["help"], pressed, n["hint"]])
        before = s["groups"]

        # ---- ③ 일반 도구를 끌어 넣기 — 행 사이(목적 문서 칸) · 원본 문서 칸 · 빈칸(같은 차례)
        g3 = page.locator("#wfCompose .wf-lines-group").nth(3)   # 4단계 「문서 정리」(작성요령 삭제 — 목적 문서 한 칸)
        last = g3.locator(".wf-line").last
        box = last.bounding_box()
        page.locator("#wfNav .wf-nav-tool[data-tool=heads]").drag_to(last, target_position={"x": 120, "y": box["height"] - 2})   # 마지막 행의 아래 가장자리 · 왼쪽(목적 문서 칸) = 그 뒤의 제 행
        s = settle(page)
        check("③ 「헤딩 · 표 분석」 을 4단계 마지막 행 아래(목적 문서 칸)에 끌어 놓음 → 새 행 = 목적 문서의 줄 · 다른 묶음은 그대로 · 놓은 도구의 설명이 오른쪽에",
              s["groups"][3] == before[3] + [["heads", "target"]] and s["groups"][:3] == before[:3] and s["help"] == "heads", [s["groups"][3], s["help"]])
        new_row = g3.locator(".wf-line").last
        page.locator("#wfNav .wf-nav-tool[data-tool=headsLlm]").drag_to(new_row.locator(".wf-line-cell[data-role=source]"))   # 그 행의 원본 문서 빈칸 = 같은 차례
        s = settle(page)
        check("③ 「LLM 검증·보완」 을 그 행의 원본 문서 빈칸에 → 같은 차례(한 행의 두 칸: 목적 헤딩 · 표 분석 + 원본 LLM 검증·보완)",
              s["groups"][3][-1] == ["heads+headsLlm", "both"] and len(s["groups"][3]) == len(before[3]) + 1, s["groups"][3])
        box = g3.locator(".wf-line").last.bounding_box()
        page.locator("#wfNav .wf-nav-tool[data-tool=guide]").drag_to(g3.locator(".wf-line").last, target_position={"x": box["width"] - 60, "y": box["height"] - 2})   # 오른쪽(원본 문서 칸)의 행 사이 = 원본 문서의 제 행
        s = settle(page)
        check("③ 「작성요령 삭제」 를 행 사이 · 오른쪽(원본 문서 칸)에 → 원본 문서의 제 행(목적 칸은 빈칸)",
              s["groups"][3][-1] == ["guide", "source"], s["groups"][3])
        page.screenshot(path=str(OUT / "03_dropped.png"), full_page=False)

        # ---- ④ 쌍 도구 · 앞 도구가 없는 자리
        g2 = page.locator("#wfCompose .wf-lines-group").nth(2)   # 3단계 「내용 넣기」
        at = [x[0] for x in s["groups"][2]].index("apply")
        page.locator("#wfNav .wf-nav-tool[data-tool=gaps]").drag_to(g2.locator(".wf-line[data-unit=apply]"), target_position={"x": 120, "y": 2})   # 「내용 반영」 행의 위 가장자리 = 그 앞(넣기 계획 뒤)
        s = settle(page)
        check("④ 쌍 도구 「빈 자리 검토」 를 3단계 「내용 반영」 앞에 → 쌍 줄(행째 — 두 문서 칸) · 거절 없음",
              s["groups"][2][at] == ["gaps", "pair"] and s["groups"][2][at + 1][0] == "apply" and not s["errs"], [s["groups"][2], s["errs"]])
        g0 = page.locator("#wfCompose .wf-lines-group").nth(0)
        page.locator("#wfNav .wf-nav-tool[data-tool=apply]").drag_to(g0.locator(".wf-line").first, target_position={"x": 120, "y": 2})   # 1단계 맨 위 — 넣기 계획이 앞에 없다
        s = settle(page)
        check("④ 앞 도구가 없는 자리(1단계 맨 위)에 「내용 반영」 → 막지 않고 놓이고, 서버 검사의 거절 글이 보인다 · 저장 단추 꺼짐",
              s["groups"][0][0] == ["apply", "pair"] and len(s["errs"]) > 0 and page.locator("#wfCompose form button[type=submit]").is_disabled(), [s["groups"][0], s["errs"]])
        page.locator("#wfCompose .wf-lines-group").nth(0).locator(".wf-line").first.locator("button", has_text="빼기").click()
        s = settle(page)
        check("④ 그 줄을 빼면 거절이 사라진다", not s["errs"], s["errs"])

        # ---- ⑤ 틀을 바꾸면 목록이 그 틀의 도구로
        page.check("#wfCompose .wf-io-opt[data-shape=gather] input")
        settle(page)
        n = page.evaluate(NAV)
        got = [[g[0], g[1], [t[0] for t in g[2]]] for g in n["groups"]]
        check("⑤ 틀을 「N → 1」 로 → 목록 = 취합형의 도구(「기관 문서 → 사업계획서」 분류) · 안내 「조립 폼(N → 1)」 · 끌 수 있다",
              got == gather and "기관 문서 → 사업계획서" in [g[0] for g in got] and "조립 폼(N → 1)" in n["hint"] and all(t[2] for g in n["groups"] for t in g[2]), [got, gather, n["hint"]])
        gg = page.locator("#wfCompose .wf-lines-group").nth(0)
        before_g = page.evaluate(LINES)["groups"]
        box = gg.locator(".wf-line").last.bounding_box()
        page.locator("#wfNav .wf-nav-tool[data-tool=hand]").drag_to(gg.locator(".wf-line").last, target_position={"x": 120, "y": box["height"] - 2})
        s = settle(page)
        check("⑤ 취합형에서 「사람이 하는 일」 을 끌어 1단계 끝에 → 그 묶음에 새 행(이름 · 글 칸이 선 카드)",
              len(s["groups"][0]) == len(before_g[0]) + 1 and s["groups"][0][-1][0] == "hand" and gg.locator(".wf-line").last.locator(".wf-line-hand input").count() == 2, [s["groups"][0], before_g[0]])
        page.screenshot(path=str(OUT / "05_gather.png"), full_page=False)
        single = [o for o in page.evaluate("() => [...document.querySelectorAll('#wfCompose .wf-io-opt')].map((l) => [l.dataset.shape, l.querySelector('input').disabled])") if o[0] == "single"]
        if single and not single[0][1]:
            page.check("#wfCompose .wf-io-opt[data-shape=single] input")
            settle(page)
            n = page.evaluate(NAV)
            keys = {t[0] for g in n["groups"] for t in g[2]}
            want = {u["key"] for u in T["byShape"]["single"]["units"]}
            check("⑤ 틀을 「1」 로 → 목록 = 문서 하나의 도구 · 안내 「조립 폼(1)」", keys == want and "조립 폼(1)" in n["hint"], [sorted(keys), sorted(want), n["hint"]])

        # ---- ⑥ 취소 · 좁은 창 · 콘솔
        page.locator("#wfCompose form button", has_text="취소").click()
        page.wait_for_timeout(200)
        n = page.evaluate(NAV)
        check("⑥ 「취소」 → 폼이 없는 목록(이관형 · 끌 수 없음 · 눌린 것 없음)",
              [[g[0], g[1], [t[0] for t in g[2]]] for g in n["groups"]] == relay and all(not t[2] and not t[3] for g in n["groups"] for t in g[2]), n)
        page.set_viewport_size({"width": 800, "height": 900})
        page.wait_for_timeout(200)
        n = page.evaluate(NAV)
        over = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("⑥ 좁은 창(800px — 목차가 가로 한 줄)에서는 「워크플로우 도구」 가 서지 않는다 · 가로 넘침 없음", not n["shown"] and over <= 0, [n["shown"], over])
        # ---- ⑦ 전용 이름(only)을 안 주는 서버(② §18-17 전) — 모두 「일반」 이 아니라 넣기 고르기처럼 사는 단계로 묶는다
        old = ctx.new_page()
        old.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))

        def strip_only(route):
            r = route.fetch()
            d = r.json()
            for u in d.get("units", []):
                u.pop("only", None)
            for b in (d.get("byShape") or {}).values():
                for u in b.get("units", []):
                    u.pop("only", None)
            route.fulfill(response=r, json=d)
        old.route(re.compile(r"/api/tasks\?v=2$"), strip_only)
        old.goto(f"{base}/workflow#overview")
        old.wait_for_selector("#wfNav .wf-nav-tools [data-tool]")
        n = old.evaluate(NAV)
        names = [g[0] for g in n["groups"]]
        homes = {st["id"]: st["name"] for st in T["stages"]}
        want = list(dict.fromkeys("사람이 하는 일" if u["kind"] == "hand" else homes.get(u["home"], u["home"]) for u in T["units"]))
        check("⑦ 전용 이름을 안 주는 서버 — 분류 대신 사는 단계로 묶음(「일반」 없음 · 넣기 고르기와 같은 이름 · 같은 수)",
              names == want and "일반" not in names and sum(len(g[2]) for g in n["groups"]) == len(T["units"]) and all(g[1] == "home" for g in n["groups"]), [names, want])
        old.close()
        check("콘솔 오류 없음", not errors, errors)
        br.close()


try:
    main()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'FAIL' if fails else 'PASS'} — 떨어진 것 {len(fails)}: {fails}" if fails else "\nPASS — 모두 통과")
sys.exit(1 if fails else 0)

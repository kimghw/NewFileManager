"""`/workflow` 조립 화면의 「도구 이름 고치기」(spec_워크플로우 ② §18-19 · design.md §22 — app/tool_names.py · app/tool_names_api.py · app/static/workflow_names.js · workflow.js 의 훅) 화면 확인 —
임시 서버(임시 조립 저장소 · 임시 도구 이름 파일, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 흉내 없이 진짜 끝점으로.

    python -X utf8 tools/smoke_tool_names_ui.py <그림·임시 폴더> [--port 18790]

2026-11-21 사용자(조립 화면의 카드 「다시 문서 검토」 를 보며) 「도구 이름을 바꿀 수 없네?」 → 물어서 받은 답 「도구 자체 (모든 워크플로우)」.

보는 것:
- ① 조립 폼의 카드를 누르면 「도구 설명」 열의 이름 아래 「이름 바꾸기」 단추 · 누르면 입력 칸(지금 이름) · 안내 「… 모든 워크플로우의 화면에 …」 · Esc 로 닫힘.
- ② 새 이름으로 저장 → 카드 · 설명 열 · 목차의 「워크플로우 도구」 · 넣기 고르기가 새 이름 · 설명 열에 「기본 이름 「…」」 · 알림 한 줄 · 열어 둔 폼(적던 워크플로우 이름 · 줄 목록 · 고른 도구)은 그대로 · 저장소에 그 이름.
- ③ 그 도구를 쓰는 붙박이 워크플로우(사업계획서 → 연차보고서 이관)의 등록부 응답 · 그 절의 단계 이름도 새 이름(기본 이름은 baseName) · 만든 글(workflow.md 와 같은 글)은 그대로.
- ④ 카드의 이름을 두 번 누르면 입력 칸이 바로 열린다 · 못 쓰는 이름(「 」)은 서버의 거절 글이 그 자리에(입력 칸은 그대로).
- ⑤ 「기본 이름으로」 → 기본 이름으로 되돌아가고 저장소에서 지워진다.
- ⑥ 이관형 · 취합형이 같이 쓰는 도구(줄 key · 기본 이름이 같음)는 같이 바뀐다 — 이관형에서 고치고 틀을 「N → 1」 로 바꾸면 취합형의 그 카드도 새 이름.
- ⑦ 「사람이 하는 일」 에는 「이름 바꾸기」 가 없다 · 콘솔 오류 없음."""
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
ap.add_argument("--port", type=int, default=18790)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1",
       "NFM_TASKS": str(tmp / "tasks.json"), "NFM_FORM_FILES": str(tmp / "form_files"), "NFM_AGENT_NOTES": str(tmp / "agent_notes.json"),
       "NFM_TOOL_NAMES": str(tmp / "tool_names.json")}   # 이 검사가 도구 이름을 고친다 — 늘 임시(사용자가 고친 이름을 건드리지 않는다)
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_FLOW_EXEC"):
    env.pop(k, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []
NEW, NEW2 = "다시 구조 분석", "구조 분석(같이)"


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


# 조립 폼 — 카드마다 [줄 key, 이름] · 「도구 설명」 열(고른 도구 · 이름 · 이름 줄의 상태 · 단추 · 입력 칸 · 안내 · 알림 · 거절) · 적던 워크플로우 이름 · 목차의 도구 이름 · 넣기 고르기의 옵션 글
VIEW = """() => { const f = document.querySelector('#wfCompose'), a = f && f.querySelector('.wf-help'), n = a && a.querySelector('.wf-name');
  const t = (el, s) => { const x = el && el.querySelector(s); return x ? x.textContent : ''; };
  const input = n && n.querySelector('.wf-name-input'), act = document.activeElement;
  return { cards: [...f.querySelectorAll('.wf-line-cell[data-on="1"]')].map((c) => [c.dataset.unit || c.closest('li.wf-line').dataset.unit, t(c, '.wf-line-name > b')]),
    help: a ? a.dataset.unit || '' : null, name: t(a, '.wf-help-name'), row: n ? n.dataset.state : null, go: !!(n && n.querySelector('.wf-name-go')), base: t(n, '.wf-name-base'),
    input: input ? input.value : null, focused: !!input && act === input, selected: !!input && act === input && input.selectionStart === 0 && input.selectionEnd === input.value.length,
    onGo: !!act && act.classList.contains('wf-name-go'), hint: t(n, '.wf-name-hint'), msg: t(n, '.wf-name-msg'), err: t(n, '.wf-name-err'),
    acts: n ? [...n.querySelectorAll('.wf-name-acts button')].map((b) => b.textContent) : [],
    wfName: (f.querySelector('input[name=name]') || {}).value, nav: Object.fromEntries([...document.querySelectorAll('#wfNav .wf-nav-tool[data-tool]')].map((b) => [b.dataset.tool, t(b, '.wf-nav-tool-name')])),
    opts: [...new Set([...f.querySelectorAll('select.wf-lines-add option')].map((o) => o.textContent))] }; }"""


def settle(page):
    page.wait_for_function("() => { const b = document.querySelector('#wfCompose .wf-lines'); return b && !/검사하는 중/.test(b.textContent) && !!b.querySelector('.wf-lines-check'); }", timeout=30000)
    page.wait_for_timeout(350)   # 줄을 고친 뒤 검사를 거는 틈(250ms)
    page.wait_for_function("() => { const b = document.querySelector('#wfCompose .wf-lines'); return b && !/검사하는 중/.test(b.textContent); }", timeout=30000)
    return page.evaluate(VIEW)


def card(unit):
    return f"#wfCompose .wf-line-cell[data-unit={unit}] .wf-line-name > b"


def renamed(page, unit, name):
    """저장이 끝나 페이지가 다시 읽힐 때까지 — 설명 열의 이름이 그 이름이고 입력 칸이 닫혔다."""
    page.wait_for_function("""([u, n]) => { const a = document.querySelector('#wfCompose .wf-help'); if (!a || a.dataset.unit !== u) return false;
      const nm = a.querySelector('.wf-help-name'); return !!nm && nm.textContent === n && !a.querySelector('.wf-name-input'); }""", arg=[unit, name], timeout=30000)
    return settle(page)


def main():
    wait_server()
    T = requests.get(base + "/api/tasks?v=2", timeout=10).json()
    units = {u["key"]: u for u in T["units"]}
    md = requests.get(base + "/api/workflow", timeout=10).json()
    step0 = {s["key"]: s for t in md["tasks"] if t["job"] == "plan_to_report" for g in t["stages"] for s in g["steps"]}
    check("서버 — 조립 응답의 도구마다 기본 이름(base = name) · 이름의 길이 · 등록부 응답의 줄에 baseName 칸(안 고친 줄은 빈 글)",
          all(u.get("base") == u["name"] for u in units.values()) and T["limits"].get("toolName") == 30 and all(s.get("baseName") == "" for s in step0.values()), [T["limits"], list(step0.values())[:2]])
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1500, "height": 1000}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/workflow#overview")
        page.wait_for_selector("#wfCompose [data-wf-compose=open]")
        page.click("#wfCompose [data-wf-compose=open]")
        v = settle(page)
        page.fill("#wfCompose input[name=name]", "이름 고치기 검사")
        on = [u for u, _n in v["cards"]]
        unit = "reheads" if "reheads" in on else next(u for u in on if u != "hand")   # 사용자가 가리킨 카드 「다시 문서 검토」(없으면 처음 놓인 도구)
        old = units[unit]["name"]
        lines0 = v["cards"]

        # ---- ① 카드를 누르면 설명 열의 이름 아래 「이름 바꾸기」
        page.click(card(unit))
        v = page.evaluate(VIEW)
        check(f"① 카드 「{old}」 를 누르면 「도구 설명」 열의 이름 아래 「이름 바꾸기」 단추(아직 안 고친 도구 — 기본 이름 줄 없음)",
              v["help"] == unit and v["name"] == old and v["row"] == "base" and v["go"] and v["base"] == "" and v["input"] is None, v)
        page.screenshot(path=str(OUT / "01_button.png"))
        page.click("#wfCompose .wf-name-go")
        page.wait_for_selector("#wfCompose .wf-name-input")
        page.wait_for_timeout(80)
        v = page.evaluate(VIEW)
        check("① 「이름 바꾸기」 → 입력 칸(지금 이름 · 초점 · 이름 전체가 골라짐) · 「저장」 · 「취소」(안 고친 도구라 「기본 이름으로」 없음) · 안내 「… 모든 워크플로우의 화면에 …」",
              v["row"] == "edit" and v["input"] == old and v["focused"] and v["selected"] and v["acts"] == ["저장", "취소"] and "모든 워크플로우의 화면" in v["hint"] and old in v["hint"], v)
        page.screenshot(path=str(OUT / "02_edit.png"))
        page.keyboard.press("Escape")
        page.wait_for_timeout(80)
        v = page.evaluate(VIEW)
        check("① Esc → 닫힘(단추에 초점) · 이름 그대로", v["row"] == "base" and v["input"] is None and v["onGo"] and v["name"] == old, v)

        # ---- ② 새 이름으로 저장
        page.click("#wfCompose .wf-name-go")
        page.fill("#wfCompose .wf-name-input", f"  {NEW} ")
        page.keyboard.press("Enter")
        v = renamed(page, unit, NEW)
        names = [n for u, n in v["cards"] if u == unit]
        check(f"② 「{NEW}」 로 저장 → 카드 · 설명 열 · 목차의 「워크플로우 도구」 · 넣기 고르기가 새 이름(옛 이름은 화면의 이름 자리에 없음)",
              names and all(n == NEW for n in names) and v["name"] == NEW and v["nav"].get(unit) == NEW and any(o == NEW or o.startswith(NEW + " —") for o in v["opts"]) and not any(o == old or o.startswith(old + " —") for o in v["opts"]), [names, v["nav"].get(unit), v["opts"][:12]])   # 「다시 문서 검토(LLM)」 처럼 옛 이름으로 시작하는 다른 도구는 그대로다
        check(f"② 설명 열 — 「기본 이름 「{old}」」 · 알림 「이름을 「{NEW}」 으로/로 바꿨습니다」 · 「이름 바꾸기」 단추 그대로",
              v["row"] == "renamed" and v["base"] == f"기본 이름 「{old}」" and f"「{NEW}」" in v["msg"] and "바꿨습니다" in v["msg"] and v["go"], v)
        check("② 열어 둔 폼은 그대로 — 적던 워크플로우 이름 · 줄 목록(줄 key · 차례) · 고른 도구",
              v["wfName"] == "이름 고치기 검사" and [u for u, _n in v["cards"]] == [u for u, _n in lines0] and v["help"] == unit, [v["wfName"], v["cards"]])
        saved = requests.get(base + "/api/tool-names", timeout=10).json()
        check("② 저장소 — 그 틀 · 그 줄 key 에 새 이름(판 1)", saved["names"].get(f"relay.{unit}") == NEW and saved["version"] == 1, saved)
        page.screenshot(path=str(OUT / "03_renamed.png"))

        # ---- ③ 붙박이 워크플로우 · 등록부 응답
        W = requests.get(base + "/api/workflow", timeout=10).json()
        st = next(s for t in W["tasks"] if t["job"] == "plan_to_report" for g in t["stages"] for s in g["steps"] if s["key"] == unit)
        flow = requests.get(base + "/api/tasks?v=2", timeout=10).json()
        u2 = next(u for u in flow["units"] if u["key"] == unit)
        check("③ 등록부 응답 — 붙박이 「사업계획서 → 연차보고서 이관」 의 그 단계 name = 새 이름 · baseName = 기본 이름 · 조립 응답의 name · base",
              st["name"] == NEW and st["baseName"] == old and u2["name"] == NEW and u2["base"] == old, [st["name"], st["baseName"], u2["name"], u2["base"]])
        sec = page.evaluate("""([job, u]) => { const s = document.getElementById(job), n = s && s.querySelector('.wf-step[data-step="' + u + '"] .wf-name'); return n ? [n.textContent, n.title] : null; }""", ["plan_to_report", unit])
        check("③ 화면 — 그 붙박이 워크플로우 절의 단계 이름도 새 이름 · 가리키면 기본 이름", bool(sec) and sec[0] == NEW and f"기본 이름 「{old}」" in sec[1], sec)

        # ---- ④ 카드의 이름을 두 번 누르면 바로 고치기 · 못 쓰는 이름은 서버의 거절 글
        page.dblclick(card(unit))
        page.wait_for_selector("#wfCompose .wf-name-input")
        page.wait_for_timeout(80)
        v = page.evaluate(VIEW)
        check("④ 카드의 이름을 두 번 누르면 입력 칸이 바로(지금 이름 · 초점) · 고친 도구라 「기본 이름으로」 단추가 선다",
              v["row"] == "edit" and v["input"] == NEW and v["focused"] and v["acts"] == ["저장", "기본 이름으로", "취소"], v)
        page.fill("#wfCompose .wf-name-input", "「구조」 분석")
        page.keyboard.press("Enter")
        page.wait_for_selector("#wfCompose .wf-name-err")
        v = page.evaluate(VIEW)
        check("④ 못 쓰는 이름(「 」) — 서버의 거절 글이 그 자리에 · 입력 칸은 적던 글 그대로 · 이름은 안 바뀜",
              "쓸 수 없습니다" in v["err"] and v["input"] == "「구조」 분석" and v["name"] == NEW and requests.get(base + "/api/tool-names", timeout=10).json()["names"].get(f"relay.{unit}") == NEW, v)
        page.screenshot(path=str(OUT / "04_refused.png"))

        # ---- ⑤ 기본 이름으로
        page.click("#wfCompose .wf-name-acts button:has-text('기본 이름으로')")
        v = renamed(page, unit, old)
        names = [n for u, n in v["cards"] if u == unit]
        check(f"⑤ 「기본 이름으로」 → 카드 · 설명 열 · 목차가 「{old}」 · 기본 이름 줄 없음 · 알림 「기본 이름 … 되돌렸습니다」 · 저장소에서 지워짐",
              all(n == old for n in names) and v["name"] == old and v["nav"].get(unit) == old and v["row"] == "base" and v["base"] == "" and "되돌렸습니다" in v["msg"]
              and f"relay.{unit}" not in requests.get(base + "/api/tool-names", timeout=10).json()["names"], v)

        # ---- ⑥ 이관형 · 취합형이 같이 쓰는 도구 — 같이 바뀐다
        g_units = {u["key"]: u for u in T["byShape"]["gather"]["units"]}
        twin = next((k for k in on if k in g_units and g_units[k]["base"] == units[k]["base"] and k != "hand"), None)
        check("⑥ 조립 폼에 놓인 도구 가운데 취합형과 줄 key · 기본 이름이 같은 것이 있다(없어졌으면 이 검사와 ② §18-19 「같은 도구 — 다른 틀에도」 를 다시 본다)", bool(twin), [on, list(g_units)])
        if twin:
            page.dblclick(card(twin))
            page.wait_for_selector("#wfCompose .wf-name-input")
            page.fill("#wfCompose .wf-name-input", NEW2)
            page.click("#wfCompose .wf-name-acts button:has-text('저장')")
            v = renamed(page, twin, NEW2)
            got = requests.get(base + "/api/tool-names", timeout=10).json()["names"]
            check(f"⑥ 「{units[twin]['base']}」 를 이관형에서 고치면 취합형의 같은 도구도 같이(저장소 두 줄) · 알림에 「취합형의 같은 도구도 같이」",
                  got.get(f"relay.{twin}") == NEW2 and got.get(f"gather.{twin}") == NEW2 and "취합형" in v["msg"], [got, v["msg"]])
            page.click("#wfCompose label[data-shape=gather]")
            v = settle(page)
            names = [n for u, n in v["cards"] if u == twin]
            check("⑥ 틀을 「N → 1」 로 바꾸면 취합형의 그 카드도 새 이름 · 목차의 도구 이름도", names and all(n == NEW2 for n in names) and v["nav"].get(twin) == NEW2, [v["cards"], v["nav"]])
            page.screenshot(path=str(OUT / "05_gather.png"))

        # ---- ⑦ 사람이 하는 일에는 없다
        hand = page.evaluate("""() => { const b = document.querySelector('#wfNav .wf-nav-tool[data-tool=hand]'); if (!b) return null; b.click(); return true; }""")
        if hand:
            page.wait_for_function("() => (document.querySelector('#wfCompose .wf-help') || { dataset: {} }).dataset.unit === 'hand'", timeout=10000)
            v = page.evaluate(VIEW)
            check("⑦ 「사람이 하는 일」 의 설명에는 「이름 바꾸기」 가 없다(줄마다 이름을 적는다)", v["help"] == "hand" and v["row"] is None, v)
        r = requests.put(base + "/api/tool-names/relay/hand", json={"name": "x"}, timeout=10)
        check("⑦ 서버도 「사람이 하는 일」 의 도구 이름은 받지 않는다(400 · 404)", r.status_code in (400, 404), [r.status_code, r.text[:200]])
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

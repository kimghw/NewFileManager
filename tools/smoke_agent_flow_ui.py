"""진행 방식 둘(한 번에 진행 · 단계별)과 에이전트 보기의 진행 보고(spec_작업에이전트 ② §7 — 2026-11-16 astra 검토가 고른 회귀 검사) 화면 확인.
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 화면에는 `GET /api/headings/llm` 의 `available` 만 true 로 바꿔 돌려준다 —
「LLM 을 쓸 수 있다」 고 보아 에이전트 보기가 TASK 를 이끌게 한다(서버는 LLM 끔이라 에이전트의 답은 스크립트 답 · 끝점·문서 편집은 모두 진짜).

1. 취합 간단 모드(첫 화면 「자동 진행」) + 에이전트: 패널이 「에이전트」 로 넘어간 뒤 「작업 개요」 로 되돌아가지 않는다 · 도는 동안 진행 카드(지금 하는 일 · 「멈춤」) · 도는 동안 진행 턴이 따로 돌지 않는다(중복 시작 없음) ·
   끝나면 결과 턴 하나(「간단 모드 … 끝남」 + 기관 문서마다 한 줄) · 취합 카드의 간단 모드 줄은 그대로(「작업 개요」).
2. 실행 카드는 그 카드가 보인 계획에 묶인다: 양식 표준화에서 「문서에 반영」 카드를 낸 뒤 세부 화면에서 계획을 다시 세우면, 앞 카드의 「진행」 은 반영하지 않고(문서 그대로) 「실행하지 않음」 으로 닫히며 새 계획의 카드가 나온다 → 그 카드의 「진행」 은 반영.
3. 첫 화면 대화창은 왼쪽 문서 목록 하나를 본다: 대화창의 「파일」 로 고른 파일이 왼쪽 목록에 들고 · 둘 이상이면 목적 문서를 고르라고 말하며(짐작하지 않음) 시작하지 않는다.
4. 문서 목록의 「자동 진행」 · 「LLM 검토」 는 「사업계획서 취합」 묶음 안에 있다(다른 TASK 의 옵션처럼 보이지 않는다).

    python -X utf8 tools/smoke_agent_flow_ui.py <출력 폴더> [--port 18461]
"""
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
ap.add_argument("--port", type=int, default=18461)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)

sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
import gather_data as GD   # noqa: E402 — 문서만 다룬다(서버 모듈을 이 프로세스에 띄우지 않는다)
from app.hwpx_doc import HwpxDoc   # noqa: E402

J1, J2, MARK = GD.J1, GD.J2, "(에이전트 진행)"
FRAME = GD.base()["side"]["bytes"]


def edited(fn):
    doc = HwpxDoc(FRAME)
    doc.blocks()
    fn(doc)
    return GD.save(doc)


A = edited(lambda d: d.set_text(GD.nxt(d, GD.para(d, f"[공동연구개발기관1({J1})]", 0)), f" o {J1} 1차년도 개발 목표{MARK}"))
B = edited(lambda d: d.set_text(GD.nxt(d, GD.para(d, f"[공동연구개발기관2({J2})]", 0)), f" o {J2} 1차년도 개발 목표{MARK}"))
FILES = [("취합본_프레임.hwpx", FRAME), (f"{J1}_작성본.hwpx", A), ("기관2_작성본.hwpx", B)]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"

env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1"}
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL"):
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


SNAP = """() => { const q = document.querySelector('#gatherFlow .gt-quick'), live = document.querySelector('#paneAgent .agw-live'), A = AGENT;
  return { tool: document.getElementById('panel').dataset.tool || '', quick: gqRun ? (gqRun.busy ? 'run' : gqRun.end ? (gqRun.end.ok ? 'done' : 'halt') : 'idle') : '', note: gqRun && gqRun.busy ? gqRun.note : '',
    live: live ? { kind: live.querySelector('.agw-card').dataset.live, head: live.querySelector('b').textContent, text: live.querySelector('.agw-live-text').textContent, stop: !!live.querySelector('[data-agw=stop]') } : null,
    quickLine: !!q && !q.hidden, guide: A.turns.filter((t) => t.kind === 'guide').map((t) => ({ event: t.event, act: t.act ? t.act.name : '', ask: t.ask ? t.ask.kind : '', state: t.state, reply: t.reply })), busy: !!A.busy }; }"""
TURNS = """() => [...document.querySelectorAll('#paneAgent .agw-turn')].map((t) => ({ event: t.dataset.event, say: (t.querySelector('.agw-reply') || {}).textContent || '',
  ask: (t.querySelector('.agw-ask') || { dataset: {} }).dataset.ask || '', act: (t.querySelector('.agw-act') || { dataset: {} }).dataset.act || '', state: (t.querySelector('.agw-card') || { dataset: {} }).dataset.state || '',
  out: (t.querySelector('.agw-card .ag-state') || {}).textContent || '' }))"""


def llm_on(route):   # 화면이 「LLM 을 쓸 수 있다」 고 보게 — 진짜 답에서 available 만 바꾼다
    r = route.fetch()
    body = r.json()
    body["available"] = True
    route.fulfill(response=r, json=body)


def main():
    wait_server()
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page.add_init_script("try { localStorage.setItem('nfm.agentDock', 'panel'); } catch (e) {}")  # 에이전트 보기를 패널 탭 자리로(창 머리 「패널에 넣기」 와 같음) — 떠 있는 창(기본)은 smoke_agent_float_ui.py
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.route(re.compile(r"/api/headings/llm$"), llm_on)
        page.goto(base)
        page.wait_for_selector("#homeAgent .agh-talk")

        # ---- 3 · 4. 첫 화면: 대화창의 「파일」 → 왼쪽 문서 목록 하나 · 목적 문서를 안 골랐으면 시작하지 않는다 · 옵션 묶음
        with page.expect_file_chooser() as fc:
            page.click("[data-agh=pick]")
        fc.value.set_files([{"name": n, "mimeType": "application/octet-stream", "buffer": d} for n, d in FILES])
        page.wait_for_selector("#homeFiles .hf-row")
        h = page.evaluate("""() => ({ rows: [...document.querySelectorAll('#homeFiles .hf-name')].map((x) => x.textContent), chips: [...document.querySelectorAll('#homeAgent .agh-file')].map((x) => x.textContent),
          note: (document.querySelector('#homeAgent .agh-list-note') || {}).textContent || '', group: (document.querySelector('#homeFiles .hf-group-name') || {}).textContent || '',
          inGroup: ['auto', 'llm'].every((k) => !!document.querySelector(`#homeFiles .hf-group [data-hf-focus=${k}]`)), send: document.querySelector('[data-agh=send]').disabled })""")
        check("대화창의 「파일」 로 고른 파일이 왼쪽 문서 목록에 든다(파일은 한 곳) — 대화창에는 요약 칩과 「목적 문서를 왼쪽 목록에서 고르세요」",
              h["rows"] == [n for n, _ in FILES] and h["chips"] == [n for n, _ in FILES] and "목적 문서를 왼쪽 목록에서" in h["note"] and not h["send"], h)
        check("「자동 진행」 · 「LLM 검토」 는 묶음 「사업계획서 취합」 안(다른 TASK 의 옵션처럼 보이지 않는다)", h["group"] == "사업계획서 취합" and h["inGroup"], h)
        page.fill("#homeAgentText", "취합하고 싶어")
        page.click("[data-agh=send]")
        page.wait_for_function("() => document.querySelectorAll('#homeAgent .agh-talk .agw-say').length >= 1 && !AGH.busy", timeout=20000)
        said = page.evaluate("() => ({ say: [...document.querySelectorAll('#homeAgent .agh-talk .agw-say')].map((x) => x.textContent), ask: !!document.querySelector('#homeAgent .agw-ask'), id: state.id })")
        check("문서가 둘 이상인데 목적 문서를 안 골랐으면 — 고르라고 말하고 시작하지 않는다(짐작하지 않음)", "목적 문서" in said["say"][-1] and not said["ask"] and said["id"] is None, said)
        page.screenshot(path=str(OUT / "01_home_list.png"))

        # ---- 1. 취합 간단 모드 + 에이전트(LLM 을 쓸 수 있다고 보는 화면)
        page.locator("#homeFiles .hf-row").nth(0).locator("input[type=radio]").check()
        page.locator("#homeFiles [data-hf-focus=auto]").check()
        page.locator("#homeFiles [data-hf-focus=llm]").uncheck()
        go = page.evaluate("() => document.querySelector('#taskCards [data-task=plan_merge] .task-card-go').textContent.trim()")
        check("취합 카드 — 자동 진행을 켜면 「끝까지 자동 진행」(이 카드가 끝까지 한다)", go.startswith("끝까지 자동 진행"), go)
        page.locator("#taskCards [data-task=plan_merge]").click()
        seen, t0, shot = [], time.time(), False
        while time.time() - t0 < 300:
            try:
                s = page.evaluate(SNAP)
            except Exception:   # 문서를 여는 사이
                page.wait_for_timeout(300)
                continue
            if not seen or json.dumps(s, ensure_ascii=False, sort_keys=True) != json.dumps(seen[-1], ensure_ascii=False, sort_keys=True):
                seen.append(s)
            if s["live"] and s["quick"] == "run" and s["tool"] == "Agent" and not shot:
                shot = True
                page.screenshot(path=str(OUT / "02_live_card.png"))
            if s["quick"] in ("done", "halt") and not s["busy"] and s["guide"]:
                break
            page.wait_for_timeout(250)
        (OUT / "quick_trace.json").write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")
        tools = [s["tool"] for s in seen]
        first_agent = tools.index("Agent") if "Agent" in tools else -1
        check("패널이 「에이전트」 로 넘어간 뒤 「작업 개요」 로 되돌아가지 않는다(실행 몸통이 패널을 바꾸지 않음)", first_agent >= 0 and all(t == "Agent" for t in tools[first_agent:]), tools)
        running = [s for s in seen if s["quick"] == "run" and s["tool"] == "Agent"]
        check("도는 동안 에이전트 보기에 진행 카드 — 「간단 모드 — 끝까지 한 번에 진행」 · 지금 하는 일 · 「멈춤」",
              any(s["live"] and s["live"]["kind"] == "quick" and "간단 모드" in s["live"]["head"] and s["live"]["text"] and s["live"]["stop"] for s in running), running[:3])
        check("도는 동안 진행 턴이 따로 돌지 않는다(시작 턴 · 다음 단계 제안이 간단 모드와 겹치지 않음)", all(not s["guide"] and not s["busy"] for s in seen if s["quick"] == "run"), [s for s in seen if s["quick"] == "run" and (s["guide"] or s["busy"])][:2])
        end = seen[-1]
        check("끝나면 결과 턴 하나 — 「간단 모드(끝까지 한 번에 진행) 끝남」 + 기관 문서마다 한 줄 · 진행 카드는 사라짐",
              end["quick"] == "done" and len(end["guide"]) == 1 and end["guide"][0]["event"] == "result" and end["guide"][0]["reply"].startswith("간단 모드(끝까지 한 번에 진행) 끝남")
              and f"{J1}_작성본.hwpx" in end["guide"][0]["reply"] and not end["live"], end)
        steps = page.evaluate("() => [...document.querySelectorAll('#paneAgent .agw-turn:last-child .agw-step')].map((s) => s.dataset.state)")
        check("결과 턴의 진행 줄 — 세 묶음이 모두 끝남", steps == ["done", "done", "done"], steps)
        page.screenshot(path=str(OUT / "03_quick_report.png"))
        page.evaluate("() => showTab('Div')")
        page.wait_for_timeout(300)
        q = page.evaluate("() => { const q = document.querySelector('#gatherFlow .gt-quick'); return q && !q.hidden ? { kind: q.dataset.kind, rows: q.querySelectorAll('.gt-quick-row').length } : null; }")
        check("패널 「작업 개요」 의 간단 모드 줄은 그대로(기관 문서마다 결과 — 세부 작업으로 이어 간다)", q is not None and q["kind"] == "done" and q["rows"] == 2, q)

        # ---- 2. 실행 카드는 그 카드가 보인 계획에 묶인다(양식 표준화 1단계)
        page.goto(base)
        page.wait_for_selector("#taskCards .task-card")
        with page.expect_file_chooser() as fc:
            page.click('#taskCards [data-task="plan_fit"]')
        fc.value.set_files(str(PLAN))
        page.wait_for_selector("#doc .para", timeout=120000)
        page.wait_for_selector('#paneAgent .agw-ask[data-ask="config"] [data-agw=confirm]', timeout=120000)
        check("TASK 카드로 시작해도(LLM 을 쓸 수 있으면) 에이전트 보기가 이끈다 — 시작 턴 → 문서에서 읽기 → 프로젝트 구성 폼", page.evaluate("document.getElementById('panel').dataset.tool") == "Agent")
        page.fill("#paneAgent [data-agw=years0]", "3")
        page.fill("#paneAgent [data-agw=lead]", "한국선급")
        page.fill("#paneAgent [data-agw=joint]", "씨드로닉스")
        doc = page.evaluate("state.id")
        rev0 = requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"]
        page.click("#paneAgent [data-agw=confirm]")
        page.wait_for_function("() => { const t = [...document.querySelectorAll('#paneAgent .agw-turn')].pop(); return t && t.querySelector('.agw-act[data-act=apply] [data-agw=go], .agw-ask[data-ask=choice]'); }", timeout=180000)
        if page.evaluate("() => !![...document.querySelectorAll('#paneAgent .agw-turn')].pop().querySelector('.agw-ask[data-ask=choice]')"):   # 계획에 사람이 볼 것이 있으면 스크립트 답은 고르게 한다
            check("계획에 미해결 자리가 있으면 선택지에 「변경 계획 목록 보기」 가 있다", page.evaluate("() => !!document.querySelector('#paneAgent .agw-turn:last-child .agw-opt[data-value=\"open:plan\"]')"))
            print("SKIP 계획 카드 대조 — 이 양식의 계획에 미해결 자리가 있어 실행 카드가 아니라 선택지로 나왔습니다", flush=True)
        else:
            card = page.evaluate("() => { const c = [...document.querySelectorAll('#paneAgent .agw-act[data-act=apply]')].pop(); return { list: !!c.querySelector('[data-agw=list]'), go: !c.querySelector('[data-agw=go]').disabled }; }")
            check("「문서에 반영」 카드 — 「진행」 · 「건너뛰기」 · 「계획 목록 보기」(지워질 글을 확인하는 길)", card["list"] and card["go"], card)
            key0 = page.evaluate("() => dv.plan.planId")
            page.evaluate("() => divPlan()")   # 세부 화면에서 계획을 다시 세움(= 계획 B)
            page.wait_for_function(f"() => dv.plan && dv.plan.planId !== {json.dumps(key0)} && !dv.busy", timeout=120000)
            n0 = page.evaluate("() => document.querySelectorAll('#paneAgent .agw-turn').length")
            page.click("#paneAgent .agw-turn:last-child [data-agw=go]")   # 계획 A 를 보인 카드의 「진행」
            page.wait_for_function(f"() => document.querySelectorAll('#paneAgent .agw-turn').length > {n0} && !AGENT.busy", timeout=120000)
            turns = page.evaluate(TURNS)
            rev1 = requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"]
            old = turns[n0 - 1]
            check("계획을 다시 세운 뒤 앞 카드의 「진행」 — 반영하지 않는다(문서 그대로) · 카드 「실행하지 않음 — 카드를 낸 뒤 계획이 바뀌었습니다」",
                  rev1 == rev0 and old["act"] == "apply" and old["state"] == "skipped" and "실행하지 않음" in old["out"] and "계획이 바뀌었습니다" in old["out"], [rev0, rev1, old])
            page.wait_for_function("() => { const t = [...document.querySelectorAll('#paneAgent .agw-turn')].pop(); return t && t.querySelector('.agw-act[data-act=apply] [data-agw=go]'); }", timeout=120000)
            check("새 계획의 「문서에 반영」 카드가 다시 나온다", page.evaluate(TURNS)[-1]["act"] == "apply")
            page.screenshot(path=str(OUT / "04_stale_card.png"))
            page.click("#paneAgent .agw-turn:last-child [data-agw=go]")
            # 반영 뒤 결과 턴 — 양식 표준화는 1단계(프로젝트 구성)가 끝나도 2 · 3단계(헤딩 추출 · 표)가 남는다(spec_양식표준화): 「모두 끝났습니다」 가 아니라 다음 차례를 말한다
            page.wait_for_function("() => { const t = [...document.querySelectorAll('#paneAgent .agw-turn')].pop(); return t && t.dataset.event === 'result' && /문서에 반영했습니다/.test(t.textContent) && !AGENT.busy; }", timeout=240000)
            rev2 = requests.get(f"{base}/api/docs/{doc}/agent", timeout=30).json()["rev"]
            turns = page.evaluate(TURNS)
            done = next((t for t in reversed(turns) if t["act"] == "apply"), None)
            check("새 카드의 「진행」 → 반영(편집 차례가 오름) · 카드 「실행함 — …」 · 결과 턴은 다음 차례(2단계 헤딩 추출)를 말함 — 1단계만 끝났으니 「모두 끝났습니다」 가 아님",
                  rev2 > rev0 and done["state"] == "done" and done["out"].startswith("실행함") and "지금 차례는 「" in turns[-1]["say"] and "모두 끝났습니다" not in turns[-1]["say"], [rev0, rev2, done, turns[-1]])
            then = page.evaluate("() => [...document.querySelectorAll('#paneAgent .agw-then')].length")
            check("앞 턴의 진행 줄에는 「이 턴 때의 진행 상황」 이라고 적는다(저장된 줄을 지금 상태로 읽지 않게)", then >= 1, then)
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

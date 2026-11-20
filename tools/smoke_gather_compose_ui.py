"""조립 화면 — 「N → 1」 취합형 조립(spec_워크플로우 ② §18-13 갈래 「라」 ⓶ ⓷ — app/static/workflow.js shapeBox · shapeFlow · app/custom_tasks.py check · _gather_rules ·
app/static/task_catalog.js gatherDefStage) 화면 확인 — 임시 서버(임시 조립 저장소 · 임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 흉내 없이 진짜 끝점으로.

    python -X utf8 tools/smoke_gather_compose_ui.py <그림·임시 폴더> [--port 18740]

보는 것:
- ① 「새 워크플로우 조립」 → 문서 입출력 「N → 1」 이 켜져 있다(「준비 중」 없음) → 고르면 줄 목록 = 붙박이 「사업계획서 취합」 의 묶음 · 줄(프로젝트 구성 · 문서 프레임 작성 · 내용 매핑) ·
  표(문서 역할 × 단계)와 「＋ 단계 넣기…」 는 없다 · 「＋ 줄 넣기…」 의 묶음 = 취합의 묶음 이름 · 서버 검사: 거절 없음 · 경고(유료 줄 · 취합본을 바꾸는 줄) · 문서 칸(원본 N · 목적 1).
- ② 차례가 거꾸로(내용 반영 ▲) → 서버의 거절 글 · 저장 꺼짐 → 되돌림. 기관 문서마다 도는 줄을 다른 묶음으로 쪼갬 → 거절.
- ③ 「이관」 으로 되돌리면 줄 목록이 이관의 표준 차례로 · 다시 「N → 1」 → 취합의 것.
- ④ 「LLM 검토」 를 빼고 묶음 둘(구성 + 프레임 · 매핑)로 저장 → 저장 몸 = {shape: gather, source: part, target: plan, flow} · 목록 줄 「N → 1 · 기관 문서 → 사업계획서」 · 그 워크플로우 절.
- ⑤ 「고치기」 — 줄 목록으로 열림(틀은 못 고침 · 표 없음).
- ⑥ 앱 — 목록에 취합형으로 선다(taskIsGather · gatherDefStage: 화면의 묶음 → 정의의 묶음 g1 · g2) · 그 워크플로우의 작업(취합본)을 열면 취합 화면 · 서버 상태의 묶음이 모두 서버가 맡는 것 ·
  「1단계 한 번에 진행」 = 서버 실행(그 정의의 g1 부터 — 화면 실행으로 가지 않는다).
- ⑦ 400px 에서 가로 넘침 없음 · 콘솔 오류 없음."""
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
ap.add_argument("--port", type=int, default=18740)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1",
       "NFM_TASKS": str(tmp / "tasks.json"), "NFM_FORM_FILES": str(tmp / "form_files")}   # 이 검사가 조립한 것을 만든다 — 늘 임시
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_FLOW_EXEC"):
    env.pop(k, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails, dialogs, bodies = [], [], [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:1200] if detail != "" and not ok else ""), flush=True)
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


# 줄이 놓인 문서(where) — 줄의 표지(li.wf-line[data-role=target|source|common])가 있으면 그것, 없으면 칸에서(공통 칸 · 켜진 문서 칸): 줄 편집기의 꼴이 바뀌어도 읽는다.
# 넣기 목록(homes · opts) — 첫 묶음의 「＋ 줄 넣기…」 고르기(하나든 문서마다 따로든) 모두를 합쳐서
LINES = """() => { const box = document.querySelector('#wfCompose .wf-lines'); if (!box) return null;
  const save = document.querySelector('#wfCompose form button[type=submit]'), std = document.querySelector('#wfCompose details.wf-std-pick');
  const where = (l) => l.dataset.role || (l.querySelector('.wf-line-common') ? 'common' : [...l.querySelectorAll('.wf-line-cell')].filter((c) => c.dataset.on === '1').map((c) => c.dataset.role).join('+') || '?');
  const g0 = box.querySelector('.wf-lines-group'), adds = g0 ? [...g0.querySelectorAll('select.wf-lines-add:not(.wf-lines-addstage)')] : [];
  return { groups: [...box.querySelectorAll('.wf-lines-group')].map((g) => ({ id: g.dataset.group, name: g.querySelector('.wf-lines-ghead input').value,
      lines: [...g.querySelectorAll('.wf-line')].map((l) => [l.dataset.unit, where(l)]) })),
    std: (box.querySelector('.wf-lines-std') || {}).textContent || '', errs: [...box.querySelectorAll('.wf-lines-err li')].map((x) => x.textContent), warns: [...box.querySelectorAll('.wf-lines-warn li')].map((x) => x.textContent),
    save: save ? { off: save.disabled, text: save.textContent } : null, table: std ? !std.hidden && std.getBoundingClientRect().height > 0 : false, addStage: !!box.querySelector('.wf-lines-addstage'),
    homes: [...new Set(adds.flatMap((a) => [...a.querySelectorAll('optgroup')].map((o) => o.label)))],
    opts: adds.flatMap((a) => [...a.querySelectorAll('option')].filter((o) => o.value).map((o) => [o.value, o.disabled])),
    again: adds.flatMap((a) => [...a.querySelectorAll('option')].filter((o) => o.value && o.dataset.again === '1').map((o) => [o.value, o.disabled, / — 한 번 더$/.test(o.textContent)])) }; }"""   # 이미 놓은 줄의 옵션(한 번 더 놓을 수 있다 — 꺼지지 않음)
SHAPES = """() => [...document.querySelectorAll('#wfCompose .wf-io-opt')].map((l) => [l.dataset.shape, l.querySelector('.wf-io-form').textContent, l.querySelector('input').disabled, l.querySelector('input').checked,
  (l.querySelector('.wf-io-soon') || {}).textContent || ''])"""
SLOTS = "() => [...document.querySelectorAll('#wfCompose .wf-io-slots > li')].map((li) => [li.dataset.role, li.querySelector('.wf-io-count').textContent, !!li.querySelector('select[name^=draft-mode-]')])"
GATHER = [["config"], ["division", "frame"], ["part", "heads", "link", "llm", "plan", "apply"]]


def settle(page):
    page.wait_for_function("() => { const b = document.querySelector('#wfCompose .wf-lines'); return b && !/검사하는 중/.test(b.textContent) && !!b.querySelector('.wf-lines-check'); }", timeout=30000)
    page.wait_for_timeout(350)   # 줄을 고친 뒤 검사를 거는 틈(250ms)
    page.wait_for_function("() => { const b = document.querySelector('#wfCompose .wf-lines'); return b && !/검사하는 중/.test(b.textContent); }", timeout=30000)
    return page.evaluate(LINES)


def units(s):
    return [[x[0] for x in g["lines"]] for g in s["groups"]]


def group(page, i):
    return page.locator("#wfCompose .wf-lines-group").nth(i)


def main():
    wait_server()
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1500, "height": 1000}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        page.on("request", lambda r: bodies.append((r.method, r.url, r.post_data)) if "/api/tasks" in r.url and r.method in ("POST", "PUT") and not r.url.endswith("/check") else None)
        page.goto(f"{base}/workflow#overview")
        page.wait_for_selector("#wfCompose [data-wf-compose=open]")

        # ---- ① 새 워크플로우 → 「N → 1」
        page.click("#wfCompose [data-wf-compose=open]")
        s0 = settle(page)
        sh = page.evaluate(SHAPES)
        check("① 문서 입출력 — 「N → 1」 취합이 켜져 있다(「준비 중」 없음) · 처음은 이관(표가 보임 · 「＋ 단계 넣기…」 있음)",
              ["gather", "N → 1", False, False, ""] in sh and ["relay", "1 → N", False, True, ""] in sh and s0["table"] and s0["addStage"], [sh, s0["table"], s0["addStage"]])
        page.check("#wfCompose .wf-io-opt[data-shape=gather] input")
        s = settle(page)
        slots = page.evaluate(SLOTS)
        check("① 「N → 1」 을 고름 → 줄 목록 = 붙박이 취합의 묶음 · 줄(프로젝트 구성 · 문서 프레임 작성 · 내용 매핑) · 표와 「＋ 단계 넣기…」 는 없다 · 문서 칸(원본 N · 목적 1 = 기본 문서 고르기)",
              [g["name"] for g in s["groups"]] == ["프로젝트 구성", "문서 프레임 작성", "내용 매핑"] and units(s) == GATHER and not s["table"] and not s["addStage"]
              and slots == [["source", "N", False], ["target", "1", True]], [s["groups"], s["table"], s["addStage"], slots])
        g1, g2, g3 = (x["lines"] for x in s["groups"])
        # 쌍 줄(data-role=pair — 2026-11-20 사용자 「열을 분할해줘, 대상이 있어야 하는 경우에는 2개를 쌍으로」: 걸친 「공통」 칸을 없애고 두 문서 칸에 하나씩 · spec_워크플로우 ② §18-6 「대상 잇기」 — 옛 꼴의 common 도 읽는다)
        PAIR = ("pair", "common")
        check("① 줄이 놓인 문서 — 구성 확정 = 목적 문서 칸의 한 칸 카드(워크플로우 전체 줄 — 취합본이 구성의 기준: 2026-11-20 두 칸에 걸친 쌍에서 바꿈) · 구성 반영 · 배포 기준본 = 목적 문서 · "
              "기관 문서 올리기 · 헤딩 · 표 분석 = 원본 문서 · 자리 연결 … 내용 반영 = 쌍",
              g1[0][1] == "target" and g2[0][1] == "target" and g2[1][1] == "target" and g3[0][1] == "source" and g3[1][1] == "source" and all(x[1] in PAIR for x in g3[2:]), [g1, g2, g3])
        check("① 서버 검사 — 거절 없음 · 「줄 목록으로 조립한 워크플로우」 · 경고(유료 LLM 줄 · 취합본을 바꾸는 줄) · 저장 켜짐",
              not s["errs"] and s["std"].startswith("줄 목록으로 조립한") and any("유료 LLM" in w and "LLM 검토" in w for w in s["warns"]) and any("목적 문서(취합본)를 바꾸는 줄" in w for w in s["warns"])
              and not s["save"]["off"], [s["errs"], s["std"], s["warns"], s["save"]])
        # 이미 놓은 줄도 꺼지지 않는다(2026-11-20 사용자 「도구는 1번 이상 선택할 수 있어야지 한번 하고 두번 선택이 안되냐」 — 옵션 글 끝 「 — 한 번 더」: 전에는 「이미 놓음」 으로 꺼짐) ·
        # 꺼지는 것은 앞 줄이 이 묶음 · 앞 묶음에 없는 줄뿐(첫 묶음에서 「내용 반영」 — 「넣기 계획」 이 뒤 묶음에 있다)
        check("① 「＋ 줄 넣기…」 — 묶음 = 취합의 묶음 이름(1단계 프로젝트 구성 · 2단계 문서 프레임 작성 · 3단계 내용 매핑 · 사람이 하는 일) · 이미 놓은 줄도 고를 수 있다(「 — 한 번 더」) · "
              "앞 줄이 아직 없는 줄(첫 묶음의 「내용 반영」)만 꺼짐 · 「끌어 넣기」 는 고를 수 있다",
              set(s["homes"]) == {"1단계 프로젝트 구성", "2단계 문서 프레임 작성", "3단계 내용 매핑", "사람이 하는 일"} and ["config", False, True] in s["again"] and ["apply", True] in s["opts"] and ["drop", False] in s["opts"]
              and not any(k in ("reheads", "guide", "headsLlm") for k, _ in s["opts"]), [s["homes"], s["opts"], s["again"]])
        page.screenshot(path=str(OUT / "01_gather.png"), full_page=False)

        # ---- ② 서버의 거절 — 차례 · 기관 문서마다의 덩이
        group(page, 2).locator(".wf-line[data-unit=apply] button", has_text="▲").click()
        s = settle(page)
        check("② 「내용 반영」 을 「넣기 계획」 위로 → 서버의 거절(「… 앞에 와야 합니다」) · 저장 꺼짐", any("앞에 와야 합니다" in e for e in s["errs"]) and s["save"]["off"], s["errs"])
        group(page, 2).locator(".wf-line[data-unit=apply] button", has_text="▼").click()
        s = settle(page)
        check("② 되돌림 → 거절 없음", not s["errs"] and units(s) == GATHER, [s["errs"], units(s)])
        page.click("#wfCompose .wf-lines button:has-text('＋ 묶음')")
        settle(page)
        group(page, 2).locator(".wf-line[data-unit=apply] button", has_text="▼").click()   # 묶음 끝의 줄 → 다음 묶음으로
        s = settle(page)
        check("② 「내용 반영」 만 다른 묶음으로 → 거절(기관 문서마다 도는 줄은 한 묶음에 잇달아) · 저장 꺼짐",
              units(s)[3] == ["apply"] and any("한 묶음에 잇달아" in e for e in s["errs"]) and s["save"]["off"], [units(s), s["errs"]])
        group(page, 3).locator(".wf-line[data-unit=apply] button", has_text="▲").click()
        settle(page)
        group(page, 3).locator("button", has_text="묶음 빼기").click()
        s = settle(page)
        check("② 되돌리고 빈 묶음을 뺌 → 거절 없음 · 묶음 셋", not s["errs"] and units(s) == GATHER, [s["errs"], units(s)])

        # ---- ③ 틀을 오감 — 이관 ↔ 취합
        page.check("#wfCompose .wf-io-opt[data-shape=relay] input")
        s = settle(page)
        check("③ 「이관」 으로 되돌림 → 줄 목록이 이관의 표준 차례(묶음 넷) · 표가 다시 보임 · 「＋ 단계 넣기…」 있음",
              [g["name"] for g in s["groups"]] == ["문서 검토", "구성 맞추기", "내용 넣기", "문서 정리"] and s["std"].startswith("표준 차례") and s["table"] and s["addStage"] and not s["errs"], s)
        page.check("#wfCompose .wf-io-opt[data-shape=gather] input")
        s = settle(page)
        check("③ 다시 「N → 1」 → 취합의 줄 목록 · 거절 없음", units(s) == GATHER and not s["errs"] and not s["table"], [units(s), s["errs"]])

        # ---- ④ 고쳐서 저장 — LLM 검토를 빼고 · 구성과 프레임을 한 묶음으로
        group(page, 2).locator(".wf-line[data-unit=llm] button", has_text="빼기").click()
        settle(page)
        group(page, 1).locator(".wf-line[data-unit=division] button", has_text="▲").click()   # 묶음 맨 위의 줄 → 앞 묶음의 끝으로
        settle(page)
        group(page, 1).locator(".wf-line[data-unit=frame] button", has_text="▲").click()
        settle(page)
        group(page, 1).locator("button", has_text="묶음 빼기").click()
        s = settle(page)
        want = [["config", "division", "frame"], ["part", "heads", "link", "plan", "apply"]]
        check("④ 「LLM 검토」 를 빼고 구성 · 프레임을 한 묶음으로 → 묶음 둘 · 거절 없음 · 유료 줄 경고가 사라짐",
              units(s) == want and not s["errs"] and not any("유료 LLM" in w for w in s["warns"]) and not s["save"]["off"], [units(s), s["errs"], s["warns"]])
        page.fill("#wfCompose input[name=name]", "기관 문서 모으기")
        page.fill("#wfCompose input[name=desc]", "프레임까지 한 번에 · LLM 검토 없이 모읍니다")
        with page.expect_response(lambda r: r.url.endswith("/api/tasks") and r.request.method == "POST") as resp:
            page.click("#wfCompose form button[type=submit]")
        made = resp.value.json().get("task") or {}
        key = made.get("key", "")
        sent = json.loads(next(b for m, u, b in bodies if m == "POST" and u.endswith("/api/tasks")))
        check("④ 저장 — 201 · 몸 = {shape: gather, source: part, target: plan, flow(줄 목록) — assign 없음} · 서버의 정의 = v2 · 묶음 g1 · g2",
              resp.value.status == 201 and sent.get("shape") == "gather" and sent.get("source") == "part" and sent.get("target") == "plan" and "assign" not in sent
              and [[x["unit"] for x in g["steps"]] for g in sent["flow"]] == want and made.get("v") == 2 and made.get("shape") == "gather" and made.get("groups") == ["g1", "g2"]
              and made.get("sourceName") == "기관 문서" and made.get("targetName") == "사업계획서", [resp.value.status, sent, made])
        page.wait_for_function(f"() => location.hash === '#{key}' && !!document.querySelector('#wfCompose .wf-made-list li[data-task=\"{key}\"]')", timeout=30000)
        row = page.evaluate(f"""() => {{ const li = document.querySelector('#wfCompose .wf-made-list li[data-task="{key}"]'); const sec = document.getElementById('{key}');
          return {{ text: li.textContent, chips: [...li.querySelectorAll('.wf-chip')].map((x) => x.textContent), sec: sec ? sec.textContent.slice(0, 4000) : '', nav: !!document.querySelector('#wfNav a[href="#{key}"]') }}; }}""")
        check("④ 목록 줄 — 「N → 1 · 기관 문서 → 사업계획서」 · 묶음 이름 · 목차 · 그 워크플로우의 절(취합의 줄 이름)",
              "N → 1 · 기관 문서 → 사업계획서" in row["text"] and row["chips"] == ["프로젝트 구성", "내용 매핑"] and row["nav"] and "배포 기준본" in row["sec"] and "내용 반영" in row["sec"], row)
        page.screenshot(path=str(OUT / "02_saved.png"), full_page=False)

        # ---- ⑤ 고치기 — 줄 목록으로 열림
        page.evaluate(f"() => document.querySelector('#wfCompose [data-task=\"{key}\"] button').click()")   # 그 워크플로우의 절을 보는 중이라 목록 줄은 안 보인다 — 「고치기」 가 전체 보기로 가서 폼을 편다
        s = settle(page)
        sh = page.evaluate(SHAPES)
        check("⑤ 「고치기」 — 줄 목록으로 열림(저장한 묶음 둘) · 틀은 「N → 1」 로 못 고침 · 표 없음 · 거절 없음",
              units(s) == want and all(x[2] for x in sh) and ["gather", "N → 1", True, True, ""] in sh and not s["table"] and not s["addStage"] and not s["errs"], [units(s), sh, s["errs"]])
        page.click("#wfCompose form button:has-text('취소')")

        # ---- ⑥ 앱 — 취합형으로 선다 · 서버 실행
        doc = requests.post(f"{base}/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}, timeout=300).json()
        wid = doc["docId"]
        requests.put(f"{base}/api/works/{wid}/task", json={"kind": "rnd", "file": "plan", "job": key, "project": "조립취합"}, timeout=60).raise_for_status()
        flow = requests.get(f"{base}/api/works/{wid}/flow", timeout=120).json()
        stages = [(g.get("id"), g.get("name"), g.get("server"), [x.get("key") for x in g.get("steps") or []]) for g in flow.get("stages") or []]
        check("⑥ 서버 상태(GET …/flow) — 그 정의의 묶음 g1 · g2 · 모두 서버가 맡는다 · 줄 = 고른 것",
              [x[0] for x in stages] == ["g1", "g2"] and all(x[2] for x in stages) and "division" in stages[0][3] and "frame" in stages[0][3] and "llm" not in stages[1][3], [stages, flow.get("family"), flow.get("why")])
        app = ctx.new_page()
        app.on("console", lambda m: errors.append(f"[app {m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        app.on("pageerror", lambda e: errors.append(f"[app pageerror] {e}"))
        app.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        app.goto(f"{base}/#w={wid}")
        app.wait_for_function("() => typeof state !== 'undefined' && !!state.id && typeof gatherOn === 'function' && gatherOn()", timeout=120000)
        cat = app.evaluate(f"""() => {{ const c = TASK_CATALOG['{key}'] || {{}};
          return {{ name: c.name, gather: c.gather, v2: c.v2, isG: taskIsGather('{key}'), relay: taskIsRelay('{key}'), built: gatherDefStage('map', 'plan_merge'),
            def: ['config', 'frame', 'map'].map((id) => gatherDefStage(id, '{key}')), part: gatherDefStage('map', '{key}', 'part:abc'), div: gatherDefStage('frame', '{key}', 'division'),
            screen: [gatherScreenStage({{ stage: 'g1', key: 'frame' }}, '{key}'), gatherScreenStage({{ stage: 'g2', key: 'apply' }}, '{key}'), gatherScreenStage({{ stage: 'map', key: 'apply' }}, 'plan_merge')] }}; }}""")
        check("⑥ 앱의 목록 — 취합형(취합본 사업계획서 · 기관 문서 여럿 · 줄 목록 정의) · 화면의 묶음 → 정의의 묶음(구성 · 프레임 → g1 · 매핑 → g2) · 붙박이는 그대로",
              cat["name"] == "기관 문서 모으기" and cat["gather"] == {"base": "plan", "parts": "part"} and cat["v2"] and cat["isG"] and not cat["relay"] and cat["built"] == "map"
              and cat["def"] == ["g1", "g1", "g2"] and cat["part"] == "g2" and cat["div"] == "g1" and cat["screen"] == ["frame", "map", "map"], cat)
        app.click("#toolTabTask")
        app.wait_for_selector("#gatherStage0 [data-gather-run]", timeout=120000)
        app.wait_for_function("() => !!gatherStepsLast && !document.querySelector('#gatherStage0 [data-gather-run]').disabled", timeout=180000)
        check("⑥ 작업 개요 — 취합 화면(묶음 셋 — 구성 · 프레임 · 매핑)이 선다 · 1단계 「한 번에 진행」 이 켜짐",
              app.evaluate("() => ['gatherStage0', 'gatherStage', 'gatherStage2'].every((id) => !!document.getElementById(id))"))
        starts = []
        app.on("request", lambda r: starts.append(json.loads(r.post_data or "{}")) if r.method == "POST" and r.url.endswith(f"/api/works/{wid}/flow/runs") else None)
        app.click("#gatherStage0 [data-gather-run]")
        app.wait_for_function("() => !gatherRun && !!gatherRunLast", timeout=600000)
        last = app.evaluate("() => gatherRunLast")
        runs = requests.get(f"{base}/api/works/{wid}/flow/runs", timeout=60).json().get("runs") or []
        rec = requests.get(f"{base}/api/works/{wid}/flow/runs/{runs[0]['n']}", timeout=60).json() if runs else {}
        print("  1단계 끝:", last, "실행 기록:", {k: rec.get(k) for k in ("job", "range", "status", "text")}, flush=True)
        check("⑥ 1단계 「한 번에 진행」 = 서버 실행 — 시작 요청의 from = g1(그 정의의 묶음) · 실행 기록이 남음(그 워크플로우 · g1 부터) · 화면 실행으로 가지 않음",
              len(starts) == 1 and starts[0].get("from") == "g1" and len(runs) == 1 and (rec.get("range") or {}).get("from") == "g1" and "서버가 이 묶음을 맡지 못했습니다" not in (last.get("text") or ""),
              [starts, runs, last])
        # 이 검사의 취합본은 빈 양식이라 값(단계 · 차년도 · 기관)을 못 읽는다 — 서버 실행이 그 정의의 첫 줄 「프로젝트 구성 추출」 에서 멈추고 그 글이 1단계의 상태 줄에 선다
        # (끝까지 도는 것 — 구성 확정 → 구조 확인 → 배포 기준본 · 기관 문서 한 덩이 — 은 진짜 모듈로 tests/test_workflow_gather.py 가 본다)
        keys, halt = [x.get("key") for x in rec.get("steps") or []], rec.get("halt") or {}
        check("⑥ 그 실행 — 그 묶음의 줄만: 첫 줄 「프로젝트 구성 추출」 에서 멈춤(빈 양식 — 값을 못 읽음) · 그 글이 1단계의 끝 글 · 기관 문서마다의 줄은 돌지 않음",
              (keys[:1] == ["config"] or halt.get("key") == "config") and not any(k in ("part", "link", "apply") for k in keys) and last.get("stage") == "config" and (rec.get("status") != "halted" or "읽지 못했습니다" in (last.get("text") or "")),
              [keys, halt, last])
        app.screenshot(path=str(OUT / "03_app.png"), full_page=False)
        app.close()

        # ---- ⑦ 좁은 폭
        page.set_viewport_size({"width": 400, "height": 900})
        page.evaluate(f"() => document.querySelector('#wfCompose [data-task=\"{key}\"] button').click()")
        settle(page)
        over = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("⑦ 400px — 가로 넘침 없음", over <= 1, over)
        page.screenshot(path=str(OUT / "04_narrow.png"), full_page=False)
        check("콘솔 오류 없음", not errors, errors)
        br.close()


try:
    main()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'OK' if not fails else 'FAIL'} — 실패 {len(fails)}" + (f": {json.dumps(fails, ensure_ascii=False)}" if fails else ""), flush=True)
sys.exit(1 if fails else 0)

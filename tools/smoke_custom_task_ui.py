"""조립한 TASK(spec_워크플로우 ② §14 — 2026-11-19 사용자 "배치를 내가 할 수 없네?" → 답 「새 TASK 만들기」) 화면 확인 — 임시 서버(임시 작업 폴더 · 임시 TASK 저장소 · PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_custom_task_ui.py <그림·임시 폴더> [--port 18166]

① /workflow 의 「TASK 조립」: 목차의 「＋ TASK 조립」 → 폼(이름 · 한 줄 설명 · 문서 쌍 · 문서 역할 × 단계 표 · 전제 — spec_워크플로우 ② §15 「문서마다 단위문서 TASK」):
   표의 칸 = 서버의 cells(체크 assign-source · assign-target · 따라오는 글 · 고를 수 없는 까닭) · 표 아래 문서마다 단위문서 TASK 줄 · 경고(목적 문서에 구성 맞추기 없이 내용 넣기 — 막지 않음)
   → 원본은 끄고 목적 문서에 단계 둘만 골라 만들기(저장한 assign) → 그 TASK 절(조립한 TASK · 고른 단계만 · 번호는 1부터 · 문서마다 단위문서 TASK 표) · 목차 · 단계 절의 「조립한 TASK」.
② 같은 이름으로 또 만들면 서버의 까닭이 폼에 보임 · 「고치기」(폼에 저장한 assign 이 채워짐)로 이름 · 단계를 바꿈.
③ 앱: 시작 화면의 TASK 카드 · 그 TASK 로 연 문서의 「작업 개요」 가 고른 묶음만(번호 1부터 · 맨 앞 묶음에 준비) · 묶음의 「한 번에 진행」 이 그 묶음의 단계로 돎(값이 없는 문서 — 구성 확정에서 멈춤) · 대시보드.
③-2 원본의 문서 검토를 끄고 목적 문서에 문서 검토 + 구성 맞추기 → 그 TASK 의 1단계에 LLM 검증·보완 줄이 없음(절 · 「작업 개요」 · 대시보드 — 목적 문서의 LLM 검증·보완은 「다시 문서 검토(LLM)」 에서).
④ 그 TASK 로 하던 작업이 있으면 「지우기」 가 꺼짐 → 작업을 지운 뒤 지움 → 목차 · 카드에서 사라짐."""
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
MADE = ("() => [...document.querySelectorAll('#wfCompose .wf-made-list > li')].map((li) => ({ key: li.dataset.task, name: li.querySelector('.wf-over-name').textContent, "
        "roles: [...li.querySelectorAll('.wf-made-role')].map((r) => [r.dataset.role, [...r.querySelectorAll('.wf-chip')].map((c) => c.textContent), r.textContent]), btns: [...li.querySelectorAll('button')].map((b) => [b.textContent, b.disabled]) }))")
# 조립 폼의 문서 역할 × 단계 표(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) — 머리 · 행마다(단계 id · 이름 · 그 단계의 줄들 · 역할마다 {칸 종류 · 체크 [이름, 값, 켜짐] · 글}) · 문서마다 단위문서 TASK 줄 · 경고(보일 때만 글)
FORM = """() => { const f = document.querySelector('#wfCompose form.wf-form'), t = f.querySelector('table.wf-assign'), w = f.querySelector('.wf-assign-warn');
  return { legend: f.querySelector('fieldset.wf-stage-pick > legend').textContent, head: [...t.querySelectorAll('thead th')].map((x) => x.textContent),
    rows: [...t.querySelectorAll('tbody tr')].map((tr) => ({ id: tr.dataset.stage, name: tr.querySelector('th b').textContent, steps: tr.querySelector('th .wf-stage-steps').textContent,
      cells: Object.fromEntries([...tr.querySelectorAll('td')].map((td) => { const i = td.querySelector('input'); return [td.dataset.role, { mode: td.dataset.mode, box: i && [i.name, i.value, i.checked], text: td.textContent }]; })) })),
    units: [...f.querySelectorAll('.wf-assign-units > li')].map((li) => [li.dataset.role, li.textContent]), warn: w.hidden ? '' : w.textContent }; }"""
STAGE_IDS = ("stage_review", "stage_fit", "stage_fill", "stage_clean")
STAGES = "() => [...document.querySelectorAll('#taskSteps > details')].map((d) => ({ id: d.dataset.stage, head: d.querySelector('.dv-phase-no').textContent + ' ' + d.querySelector('summary strong').textContent, count: d.querySelector('.dv-phase-count').textContent, state: d.querySelector('.dv-phase-state').lastChild.textContent, kind: d.querySelector('.dv-phase-state').dataset.kind, off: d.querySelector('[data-task-run]').disabled, steps: [...d.querySelectorAll('ol.dv-flow-steps > li')].map((li) => li.dataset.step) }))"

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

        # ---- ① /workflow 의 「TASK 조립」 — 단계 둘만 골라 만들기
        wf.goto(base + "/workflow")
        wf.wait_for_selector("#wfNav [data-wf-compose]")
        nav = wf.evaluate(NAV)
        check("목차 — TASK · 단계 · 도구(화면 말) · 「＋ TASK 조립」 단추 · 조립한 TASK 없음", nav["heads"] == ["TASK", "단계", "도구"] and not any("wf-made" in x[2] for x in nav["links"])
              and wf.locator("#wfCompose").is_visible() and wf.locator("#wfCompose .wf-made-list").count() == 0 and wf.locator("#wfCompose [data-wf-compose=open]").inner_text() == "새 TASK 조립", nav["heads"])
        wf.click("#wfNav [data-wf-compose]")
        wf.wait_for_selector("#wfCompose form.wf-form")
        f0 = wf.evaluate("""() => { const f = document.querySelector('#wfCompose form.wf-form');
          return { title: f.querySelector('h3').textContent, fields: [...f.querySelectorAll('.wf-field-name')].map((x) => x.textContent), pairs: [...f.querySelectorAll('select[name=pair] option')].map((o) => o.textContent),
            old: f.querySelectorAll('.wf-stage-opt, input[name=stage]').length,
            focus: document.activeElement === f.querySelector('input[name=name]'), premise: f.querySelector('textarea').placeholder, blocked: [...document.querySelectorAll('#wfCompose .wf-blocked li b')].map((b) => b.textContent) }; }""")
        check("폼 — 이름(포커스) · 한 줄 설명 · 문서 쌍(지금은 사업계획서 → 연차보고서 하나) · 전제(비우면 이관의 전제) · 아직 조립할 수 없는 것 둘 · 「단계 넷 체크」 는 없어짐(문서 역할 × 단계 표로)",
              f0["title"] == "새 TASK" and f0["fields"] == ["이름", "한 줄 설명", "문서 쌍(원본 → 목적)", "전제(선택)"] and f0["pairs"] == ["사업계획서 → 연차보고서"] and f0["focus"] and f0["old"] == 0
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
        check("새 TASK 의 처음 값 — 원본 = 문서 검토 · 목적 = 넷 모두(체크 이름 assign-source · assign-target) · 따라오는 칸은 목적이 골랐으니 그 글 · 고를 수 없는 칸은 까닭(원본은 바꾸지 않습니다) · 문서마다 단위문서 TASK 줄 · 경고 없음",
              rows["stage_review"]["cells"]["source"]["box"] == ["assign-source", "stage_review", True] and all(rows[i]["cells"]["target"]["box"] == ["assign-target", i, True] for i in STAGE_IDS)
              and all(rows[i]["cells"]["source"]["box"] is None for i in STAGE_IDS[1:])
              and rows["stage_fit"]["cells"]["source"]["text"] == ctext("stage_fit") != "" and rows["stage_fill"]["cells"]["source"]["text"] == ctext("stage_fill") != ""
              and rows["stage_clean"]["cells"]["source"]["text"] == ctext("stage_clean") == "원본은 바꾸지 않습니다"
              and f1["units"] == [["source", "원본 문서 — 사업계획서: 문서 검토"], ["target", "목적 문서 — 연차보고서: 문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리"]] and f1["warn"] == "", f1)
        wf.uncheck("#wfCompose input[name=assign-target][value=stage_fit]")
        f2 = wf.evaluate(FORM)
        r2 = {r["id"]: r for r in f2["rows"]}
        check("목적 문서의 「구성 맞추기」 를 끄면 — 원본 칸의 따라오는 글이 「—」(내용 넣기의 글은 그대로) · 목적 줄에서 빠짐 · 경고(막지 않음 — 저장 단추는 켜짐)",
              r2["stage_fit"]["cells"]["source"]["text"] == "—" and r2["stage_fill"]["cells"]["source"]["text"] == ctext("stage_fill")
              and f2["units"][1] == ["target", "목적 문서 — 연차보고서: 문서 검토 · 내용 넣기 · 문서 정리"] and "목적 문서가 이미 프로젝트 구성에 맞아야 자리 연결이 섭니다" in f2["warn"]
              and not wf.is_disabled("#wfCompose form button[type=submit]"), f2)
        wf.check("#wfCompose input[name=assign-target][value=stage_fit]")
        wf.fill("#wfCompose input[name=name]", "구성 맞추고 넣기")
        wf.fill("#wfCompose input[name=desc]", "정리는 하지 않습니다")
        wf.uncheck("#wfCompose input[name=assign-source][value=stage_review]")
        wf.uncheck("#wfCompose input[name=assign-target][value=stage_review]")
        wf.uncheck("#wfCompose input[name=assign-target][value=stage_clean]")
        f3 = wf.evaluate(FORM)
        check("원본의 문서 검토를 끄고 목적에 구성 맞추기 · 내용 넣기만 — 줄: 원본 「—」 · 목적 「구성 맞추기 · 내용 넣기」 · 따라오는 글은 그대로 · 경고 없음",
              f3["units"] == [["source", "원본 문서 — 사업계획서: —"], ["target", "목적 문서 — 연차보고서: 구성 맞추기 · 내용 넣기"]] and f3["warn"] == ""
              and {r["id"]: r["cells"]["source"]["text"] for r in f3["rows"]}["stage_fit"] == ctext("stage_fit"), f3)
        wf.locator("#wfCompose").screenshot(path=str(OUT / "1_form.png"))
        wf.click("#wfCompose form button[type=submit]")
        wf.wait_for_function("() => /^#u_[0-9a-f]{8}$/.test(location.hash)", timeout=20000)
        key = wf.evaluate("() => location.hash.slice(1)")
        wf.wait_for_function("(k) => !!document.getElementById(k)", arg=key)
        t0 = requests.get(f"{base}/api/tasks", timeout=30).json()["tasks"][0]
        check("저장한 assign — 원본 [](문서 검토를 끔) · 목적 [구성 맞추기 · 내용 넣기](일반 차례) · stages = 두 문서의 합집합 · 묶음 = 그것",
              t0["key"] == key and t0.get("assign") == {"source": [], "target": ["stage_fit", "stage_fill"]} and t0["stages"] == ["stage_fit", "stage_fill"] and t0["groups"] == ["frame", "map"], t0)
        wf.click("#wfViewList")
        sec = wf.evaluate("""(k) => { const s = document.getElementById(k);
          return { h2: s.querySelector('h2').textContent, lead: s.querySelector('.wf-lead').textContent, io: [...s.querySelectorAll(':scope > .wf-io dt')].map((d) => d.textContent),
            stages: [...s.querySelectorAll('.wf-stage')].map((g) => [g.dataset.stage, g.querySelector('.wf-stage-no').textContent, g.querySelector('h3').textContent, (g.querySelector('.wf-stage-module a') || {}).textContent, [...g.querySelectorAll('.wf-step')].map((d) => d.dataset.step)]) }; }""", key)
        check("만든 TASK 의 절 — 「조립한 TASK」 꼬리표 · 설명 · 조립 · 전제(이관의 전제를 씀) · 고른 단계만: 1단계 구성 맞추기(준비 포함) · 2단계 내용 넣기 — 묶음마다 「조립한 단계」 링크",
              sec["h2"] == "TASK구성 맞추고 넣기조립한 TASK" and sec["lead"] == "정리는 하지 않습니다" and sec["io"][:2] == ["조립", "전제"]
              and [x[:4] for x in sec["stages"]] == [["frame", "1단계", "구성 맞추기", "구성 맞추기"], ["map", "2단계", "내용 넣기", "내용 넣기"]]
              and sec["stages"][0][4] == ["files", "configLoad", "config", "division", "reheads", "reheadsLlm"] and sec["stages"][1][4][:1] == ["link"], sec)
        # 그 TASK 절의 「문서마다 단위문서 TASK」 표(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) — 등록부(custom())의 roles · unit 그대로
        docs = wf.evaluate("""(k) => { const t = document.querySelector('#' + k + ' table.wf-docs'); return t && { cols: [...t.querySelectorAll('thead th')].map((x) => x.textContent),
          rows: [...t.querySelectorAll('tbody tr')].map((tr) => [tr.dataset.stage, Object.fromEntries([...tr.querySelectorAll('td[data-role]')].map((td) => [td.dataset.role, [...td.querySelectorAll('a.wf-docs-step')].map((a) => a.getAttribute('href').split('--').pop())]))]) }; }""", key)
        wt = next(t for t in requests.get(f"{base}/api/workflow", timeout=30).json()["tasks"] if t["job"] == key)
        want = [[g["id"], {r["role"]: next((u["steps"] for u in r["unit"] if u["stage"] == g["id"]), []) for r in wt.get("roles") or []}] for g in wt["stages"]]
        check("그 TASK 절의 「문서마다 단위문서 TASK」 — 열 = 원본 문서 — 사업계획서 · 목적 문서 — 연차보고서 · 행 = 고른 묶음(구성 맞추기 · 내용 넣기) · 칸 = 등록부의 단위문서 TASK · 원본은 문서 검토를 안 골라 헤딩 · 표 분석이 없음",
              bool(docs) and docs["cols"] == ["단계", "원본 문서 — 사업계획서", "목적 문서 — 연차보고서"] and docs["rows"] == want and [r[0] for r in docs["rows"]] == ["frame", "map"]
              and not any(k in r[1].get(role, []) for r in docs["rows"] for role in ("source", "target") for k in ("heads", "headsLlm")), [docs, want])
        nav, made = wf.evaluate(NAV), wf.evaluate(MADE)
        used = wf.evaluate("() => Object.fromEntries(['stage_review', 'stage_fit', 'stage_fill', 'stage_clean'].map((id) => [id, [...document.querySelectorAll('#common-' + id + ' .wf-io .wf-chip')].map((a) => a.textContent)]))")
        check("목차에 그 TASK(「조립」 표시 · 붙박이 TASK 뒤) · 「TASK 조립」 절의 목록(문서마다 고른 단계 — 원본: — · 목적: 구성 맞추기 · 내용 넣기 · 고치기 · 지우기) · 단계 절의 「조립한 TASK」 에 더해짐(고른 단계에만)",
              [f"#{key}", "구성 맞추고 넣기", "wf-made"] in nav["links"] and nav["links"][8][0] == f"#{key}" and len(made) == 1 and made[0]["key"] == key and made[0]["name"] == "구성 맞추고 넣기"
              and [r[:2] for r in made[0]["roles"]] == [["source", []], ["target", ["구성 맞추기", "내용 넣기"]]] and made[0]["roles"][0][2] == "원본:—" and made[0]["btns"] == [["고치기", False], ["지우기", False]]
              and used["stage_fit"] == ["사업계획서 → 연차보고서 이관", "구성 맞추고 넣기"] and used["stage_review"] == ["사업계획서 → 연차보고서 이관"], [nav["links"][8], made, used])
        wf.screenshot(path=str(OUT / "1_made.png"))

        # ---- ② 같은 이름은 못 만든다(서버의 까닭이 폼에) · 「고치기」
        wf.click("#wfNav [data-wf-compose]")
        wf.wait_for_selector("#wfCompose form.wf-form")
        wf.fill("#wfCompose input[name=name]", "구성 맞추고 넣기")
        wf.click("#wfCompose form button[type=submit]")
        wf.wait_for_selector("#wfCompose form .wf-err")
        check("같은 이름 — 만들지 않고 폼에 까닭 · 폼의 값은 그대로", "이미 있는 TASK 이름" in wf.inner_text("#wfCompose form .wf-err") and wf.input_value("#wfCompose input[name=name]") == "구성 맞추고 넣기"
              and len(requests.get(f"{base}/api/tasks", timeout=30).json()["tasks"]) == 1, wf.inner_text("#wfCompose form .wf-err"))
        wf.locator("#wfCompose form button", has_text="취소").click()
        wf.locator(f"#wfCompose .wf-made-list li[data-task={key}] button", has_text="고치기").click()
        wf.wait_for_selector("#wfCompose form.wf-form")
        e0 = wf.evaluate("""() => { const f = document.querySelector('#wfCompose form.wf-form'), on = (n) => [...f.querySelectorAll('input[name=' + n + ']')].filter((i) => i.checked).map((i) => i.value);
          return { title: f.querySelector('h3').textContent, name: f.querySelector('input[name=name]').value, pairOff: f.querySelector('select[name=pair]').disabled, source: on('assign-source'), target: on('assign-target'),
            units: [...f.querySelectorAll('.wf-assign-units > li')].map((li) => li.textContent), save: f.querySelector('button[type=submit]').textContent }; }""")
        check("「고치기」 — 그 TASK 의 값(저장한 assign)으로 폼: 원본 체크 없음 · 목적 구성 맞추기 · 내용 넣기 · 문서마다 단위문서 TASK 줄 · 문서 쌍은 못 고침 · 단추 「고친 것 저장」",
              e0 == {"title": "「구성 맞추고 넣기」 고치기", "name": "구성 맞추고 넣기", "pairOff": True, "source": [], "target": ["stage_fit", "stage_fill"],
                     "units": ["원본 문서 — 사업계획서: —", "목적 문서 — 연차보고서: 구성 맞추기 · 내용 넣기"], "save": "고친 것 저장"}, e0)
        wf.fill("#wfCompose input[name=name]", "구성 · 넣기 · 정리")
        wf.check("#wfCompose input[name=assign-target][value=stage_clean]")
        wf.click("#wfCompose form button[type=submit]")
        wf.wait_for_function("(k) => { const s = document.getElementById(k); return !!s && s.querySelectorAll('.wf-stage').length === 3; }", arg=key, timeout=20000)
        t1 = requests.get(f"{base}/api/tasks", timeout=30).json()["tasks"][0]
        check("고친 것이 저장됨 — 이름 · 목적 문서의 단계 셋(차례는 일반 단계의 차례) · 원본은 그대로 없음 · 키는 그대로",
              t1["key"] == key and t1["name"] == "구성 · 넣기 · 정리" and t1.get("assign") == {"source": [], "target": ["stage_fit", "stage_fill", "stage_clean"]}
              and t1["stages"] == ["stage_fit", "stage_fill", "stage_clean"] and t1["groups"] == ["frame", "map", "clean"], t1)

        # ---- ③ 앱 — TASK 카드 · 그 TASK 로 연 문서의 「작업 개요」 가 고른 묶음만 · 「한 번에 진행」
        small = ROOT / "samples" / "기술수요조사서.hwpx"
        a, c = upload(small), upload(small)   # a = 연차보고서 칸(목적) · c = 사업계획서 칸(원본 — 국가R&D 양식이 아니라 값이 없다)
        for wid, file in ((a, "report"), (c, "plan")):
            r = requests.put(f"{base}/api/works/{wid}/task", json={"kind": "rnd", "file": file, "job": key, "project": "조립 시험"}, timeout=30)
            check(f"서버가 조립한 TASK 의 키를 작업의 TASK 로 받음({file})", r.status_code == 200 and r.json()["task"]["job"] == key, r.status_code)
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
        wf.click("#wfViewList")
        s2 = wf.evaluate("""(k) => ({ stages: [...document.getElementById(k).querySelectorAll('.wf-stage')].map((g) => [g.dataset.stage, [...g.querySelectorAll('.wf-step')].map((d) => d.dataset.step)]),
          llm: document.querySelectorAll('#' + k + ' .wf-docs a.wf-docs-step[href$="--headsLlm"]').length,
          heads: Object.fromEntries([...document.querySelectorAll('#' + k + ' .wf-docs tr[data-stage=review] td[data-role]')].map((td) => [td.dataset.role, [...td.querySelectorAll('a.wf-docs-step')].map((a) => a.getAttribute('href').split('--').pop())])) })""", key2)
        check("원본의 문서 검토를 끄고 목적에 문서 검토 + 구성 맞추기 — 폼의 줄 · 저장한 assign · 그 TASK 절의 1단계(문서 검토)에 LLM 검증·보완 줄이 없음(목적 문서는 2단계 「다시 문서 검토(LLM)」) · 표: 헤딩 · 표 분석은 목적 칸에만",
              f4["units"] == [["source", "원본 문서 — 사업계획서: —"], ["target", "목적 문서 — 연차보고서: 문서 검토 · 구성 맞추기"]] and f4["warn"] == ""
              and t2.get("assign") == {"source": [], "target": ["stage_review", "stage_fit"]} and t2.get("stages") == ["stage_review", "stage_fit"]
              and [x[0] for x in s2["stages"]] == ["review", "frame"] and s2["stages"][0][1] == ["files", "heads"] and "reheadsLlm" in s2["stages"][1][1] and s2["llm"] == 0
              and "heads" in s2["heads"].get("target", []) and "heads" not in s2["heads"].get("source", []), [f4, t2, s2])
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

        # ---- ④ 지우기 — 그 TASK 로 하던 작업이 있으면 꺼짐 → 작업을 지운 뒤 지움
        wf.bring_to_front()
        wf.goto(base + "/workflow#overview")   # 「TASK 조립」 절은 전체 보기와 함께 보인다(주소가 그 TASK 의 절이면 다이어그램만)
        wf.reload()
        wf.wait_for_selector("#wfCompose .wf-made-list li")
        made = wf.evaluate(MADE)
        check("하던 작업이 있으면 「지우기」 꺼짐(까닭은 풍선 도움말)", made[0]["btns"] == [["고치기", False], ["지우기", True]] and "작업이 2개" in wf.get_attribute("#wfCompose .wf-made-list li button:nth-of-type(2)", "title"), made)
        for wid in (a, c):
            requests.delete(f"{base}/api/works/{wid}", timeout=30).raise_for_status()
        wf.goto(base + "/workflow#overview")   # 「TASK 조립」 절은 전체 보기와 함께 보인다(주소가 그 TASK 의 절이면 다이어그램만)
        wf.reload()
        wf.wait_for_selector("#wfCompose .wf-made-list li")
        n = len(dialogs)
        wf.locator("#wfCompose .wf-made-list li button", has_text="지우기").click()
        wf.wait_for_function("() => document.querySelectorAll('#wfCompose .wf-made-list li').length === 0", timeout=20000)
        nav = wf.evaluate(NAV)
        check("지우기 — 한 번 묻고(확인) 지움 · 목차 · 목록 · 저장소에서 사라짐", len(dialogs) == n + 1 and "구성 · 넣기 · 정리" in dialogs[-1] and not any(x[0] == f"#{key}" for x in nav["links"])
              and requests.get(f"{base}/api/tasks", timeout=30).json()["tasks"] == [], [dialogs[n:], nav["links"][7:9]])
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

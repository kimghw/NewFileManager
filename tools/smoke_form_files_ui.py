"""저장한 양식 · 문서 칸 · 양식으로 시작(spec_워크플로우 ② §18-9 「양식」 · 고친 규칙 ② §18-12 ⑧ — app/static/workflow.js 「저장한 양식」 절 · 「문서 칸」 줄 · home_files.js hfStartForm · home_dash.js) 화면 확인 —
임시 서버(임시 작업 폴더 · 임시 저장한 양식, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 흉내 없이 진짜 끝점으로.

    python -X utf8 tools/smoke_form_files_ui.py <그림·임시 폴더> [--port 18700]

보는 것:
- ① /workflow#wfForms — 목차의 「저장한 양식」 · 절(머리 · 안내 · 없을 때 「양식 더하기」 가 펴져 있음) → 파일 올리기 → 목록 줄(이름 · 파일 · 형식 · 저장한 날 · 문서 종류 짐작 = 연차보고서) · 같은 파일 다시 = 「이미 있습니다」.
- ② 목록 보기의 워크플로우 절 「문서 칸」 — 이관: 수가 1인 칸마다(② §18-9) 원본 문서 = 「양식: …」(사업계획서 양식이 없어 꺼짐) · 목적 문서 = 「양식: 없음 · 기본값 · 고정」 + 걸 수 있는 양식 · 취합의 기관 문서 = 문서마다 사람이 넣음 → 「고정」 → 저장한 양식 줄에 「쓰는 워크플로우: … · 고정」 · 지우기 · 문서 종류가 꺼짐 /
  취합(목적 = 사업계획서)은 걸 수 있는 양식이 없음 · 서식 복사는 서버의 까닭 글. 작업의 처음 올린 원본을 「양식으로 저장」.
- ③ 첫 화면 — 고정: 대시보드의 문서 칸 목적 = 양식 이름 · 저장한 날 · 「양식: 고정」 · 바꾸는 단추 없음 · 워크플로우 카드 글 「양식으로 시작」 → 「워크플로우 시작」 → 문서 화면으로 넘어가지 않고
  목적 문서 = 그 양식으로 만든 새 작업(source form · form.id · mode fixed) · 원본 문서 = 목록의 사업계획서(같은 프로젝트 · 라운드).
- ④ 같은 프로젝트로 다시 고르면 「이어서」 가 먼저(강조) · 「새로 시작」 → 「이어서」 = 그 작업의 대시보드(새 작업 없음).
- ⑤ 기본값: 목록에서 목적 문서를 안 고르면 양식 · 「목록의 파일로」 ↔ 「양식으로」 · ⑥ 고정 + 워크플로우 카드 → 양식으로 시작해 문서 화면이 열림.
- ⑦ 좁은 폭(400px)에서 /workflow 의 저장한 양식 절 · 문서 칸이 가로로 넘치지 않음.
- ⑧ 그 칸에서 바로 양식 올리기(② §18-9 「그 칸에서 올리기」) — 저장한 양식이 없으면 꺼진 고르기 둘 대신 「양식 올리기…」 만 → 올리면 저장한 양식(문서 종류 = 그 칸의 종류)이 되고 그 칸에 걸림(조립 폼 = 골라 둠 · 워크플로우 절 = 서버 설정) ·
  받지 않는 형식은 올리지 않고 까닭.
- ⑨ 조립 폼(새 워크플로우 · 이관 「1 → N」)의 목적 문서 칸 「N」 에도 양식 고르기 · 「양식 올리기…」 → 「기본값」 으로 골라 만들면 만든 워크플로우의 목적 칸에 걸림 · 콘솔 오류 없음."""
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
ap.add_argument("--port", type=int, default=18700)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)

PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
REPORT = ROOT / "samples" / "국가RnD_서식" / "KEIT_표준서식_260320" / "1. 산업기술혁신사업 연차보고서 서식_260319.hwpx"
JOB = "plan_to_report"
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1"}
env["NFM_FORM_FILES"] = str(tmp / "form_files")   # 늘 이 검사의 임시 폴더(run_ui_gates.py 가 건 것보다 먼저 — 이 검사가 양식을 만들고 지운다)
env.setdefault("NFM_TASKS", str(tmp / "tasks.json"))
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_FLOW_EXEC"):
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


def forms():
    return requests.get(f"{base}/api/form-files", timeout=10).json()


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


def pick_files(page, paths):
    with page.expect_file_chooser() as fc:
        page.locator("#pickBtn").click()
    fc.value.set_files([str(p) for p in paths])
    page.wait_for_function("(n) => document.querySelectorAll('#homeFiles .hf-row').length >= n", arg=len(paths))


HOME = """() => { const d = document.getElementById('homeDash'), q = (s) => d.querySelector(s), t = (s) => (q(s) || {}).textContent || '';
  const b = (x) => (x ? { text: x.textContent, off: !!x.disabled, primary: x.classList.contains('primary') } : null);
  return { state: d.dataset.state, docs: [...d.querySelectorAll('.home-dash-docs li')].map((li) => [li.dataset.role, li.textContent]),
    form: q('.home-dash-form') ? { mode: q('.home-dash-form').dataset.mode, use: q('.home-dash-form').dataset.use, text: t('.home-dash-form'), flip: b(q('[data-hd-focus=form]')) } : null,
    resume: b(q('[data-hd-focus=resume]')), start: b(q('[data-hd-focus=start]')), why: t('.dash-why'), notes: [...d.querySelectorAll('.dash-note')].map((n) => n.textContent),
    card: (document.querySelector('#taskCards [data-task=plan_to_report] .task-card-go') || {}).textContent || '', tags: [...document.querySelectorAll('#homeFiles .hf-tag')].map((x) => x.textContent),
    cap: (document.querySelector('#homeFiles .hf-cap') || {}).textContent || '', home: document.body.classList.contains('no-doc'), id: state.id,
    memo: (() => { try { return JSON.parse(localStorage.getItem('nfm.homeDash') || 'null'); } catch (e) { return 'err'; } })() }; }"""


def main():
    wait_server()
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))

        # ---- ① 저장한 양식 절 — 비어 있으면 「양식 더하기」 가 펴져 있다 → 파일 올리기
        page.goto(f"{base}/workflow#wfForms")
        page.wait_for_selector("#wfForms .wf-ff-add[open]")
        s = page.evaluate("""() => { const sec = document.getElementById('wfForms'), r = sec.getBoundingClientRect();
          return { hidden: sec.hidden, nav: [...document.querySelectorAll('#wfNav a')].some((a) => a.getAttribute('href') === '#wfForms' && a.textContent === '저장한 양식'),
            head: sec.querySelector('h2').textContent, lead: ((sec.querySelector('h2 .panel-help') || {}).dataset || {}).help || '', plain: !!sec.querySelector(':scope > .wf-lead'), empty: /저장한 양식이 없습니다/.test(sec.textContent), top: Math.round(r.top) }; }""")
        check("① 목차 「저장한 양식」 · #wfForms 로 바로 그 절(전체 보기와 함께) · 머리 · 안내는 머리의 노트 아이콘(기본값 · 고정 · 올린 그대로 — 본문 글 없음) · 없음 · 「양식 더하기」 펴짐",
              not s["hidden"] and s["nav"] and s["head"].startswith("저장한 양식") and "기본값" in s["lead"] and "고정" in s["lead"] and "올린 그대로" in s["lead"] and not s["plain"] and s["empty"] and 0 <= s["top"] < 900, s)
        page.locator("#wfForms .wf-ff-add input[type=file]").set_input_files(str(REPORT))
        page.locator("#wfForms .wf-ff-add button", has_text="올려 저장").click()
        page.wait_for_selector("#wfForms .wf-ff-row[data-form]", timeout=60000)
        f = forms()["files"]
        row = page.evaluate("""() => { const r = document.querySelector('#wfForms .wf-ff-row'); return { name: r.querySelector('input').value, kind: r.querySelector('select').value, meta: r.querySelector('.wf-muted').textContent,
          msg: (document.querySelector('#wfForms .wf-ff-msg') || {}).textContent || '', dl: (r.querySelector('a[download]') || {}).href || '', del: !r.querySelector('button').disabled }; }""")
        check("① 올린 양식 — 목록 줄(이름 = 파일 이름 · 문서 종류 짐작 = 연차보고서 · 형식 · 저장한 날) · 알림 · 내려받기 · 지우기 켜짐",
              len(f) == 1 and row["name"] == REPORT.stem and row["kind"] == "report" and "hwpx" in row["meta"] and "저장한 날" in row["meta"] and "저장했습니다" in row["msg"]
              and row["dl"].endswith(f"/api/form-files/{f[0]['id']}/file") and row["del"], [f, row])
        fid = f[0]["id"]
        page.locator("#wfForms .wf-ff-add input[type=file]").set_input_files(str(REPORT))
        page.locator("#wfForms .wf-ff-add button", has_text="올려 저장").click()
        page.wait_for_function("() => /이미 있습니다/.test((document.querySelector('#wfForms .wf-ff-msg') || {}).textContent || '')", timeout=60000)
        check("① 같은 파일을 다시 올리면 있던 양식(「이미 있습니다」 · 하나 그대로)", len(forms()["files"]) == 1)
        page.screenshot(path=str(OUT / "01_forms.png"))

        # ---- ② 목록 보기의 워크플로우 절 「문서 칸」 — 고정으로 건다
        page.locator("#wfViewList").click()
        page.wait_for_selector("section#plan_to_report .wf-slots")
        sl = page.evaluate("""() => { const box = (j) => document.querySelector(`section#${j} .wf-slots`), rows = (j) => [...box(j).querySelectorAll('.wf-slot')].map((li) => [li.dataset.role, li.textContent]);
          const sel = (j, n) => box(j).querySelector(`select[name="slot-${n}-${j}"]`);
          return { relay: rows('plan_to_report'), modes: [...sel('plan_to_report', 'mode').options].map((o) => o.textContent), forms: [...sel('plan_to_report', 'form').options].map((o) => o.value),
            srcOff: box('plan_to_report').querySelector('select[name="slot-mode-plan_to_report-source"]').disabled,
            merge: rows('plan_merge'), mergeOff: sel('plan_merge', 'mode').disabled, copy: box('style_copy') ? box('style_copy').textContent : '' }; }""")
        check("② 문서 칸 — 이관: 원본 문서(수가 1 — 「양식: …」 · 사업계획서 양식이 없어 꺼짐) → 목적 문서(「양식: 없음 · 기본값 · 고정」 + 이 양식) / 취합: 기관 문서 = 문서마다 사람이 넣음 · 목적 = 걸 수 있는 양식이 없음(꺼짐) / 서식 복사: 서버의 까닭 글",
              [r for r, _ in sl["relay"]] == ["source", "target"] and "사업계획서 양식을 올리세요" in sl["relay"][0][1] and sl["srcOff"] and sl["modes"] == ["양식: 없음", "양식: 기본값", "양식: 고정"]
              and sl["forms"] == [fid] and "문서마다 사람이 넣습니다" in sl["merge"][0][1] and "걸 수 있는 양식이 없습니다" in sl["merge"][-1][1] and sl["mergeOff"] and "내용을 받는 문서가 아니라" in sl["copy"], sl)
        page.select_option(f'section#{JOB} select[name="slot-mode-{JOB}"]', "fixed")
        page.wait_for_selector("#wfForms .wf-ff-row a[data-use=fixed]", timeout=30000)
        used = page.evaluate("""() => { const r = document.querySelector('#wfForms .wf-ff-row'); return { chip: r.querySelector('a[data-use]').textContent, del: r.querySelector('button').disabled, kind: r.querySelector('select').disabled,
          note: document.querySelector('section#plan_to_report .wf-slot[data-role=target] .wf-slot-pick .wf-muted').textContent, mode: document.querySelector('section#plan_to_report select[name="slot-mode-plan_to_report"]').value,
          saved: (document.querySelector('section#plan_to_report .wf-slot[data-role=target] .wf-slot-saved') || {}).textContent || '',   // 고르는 즉시 저장 — 저장 단추 대신 「✓ 저장됨 HH:MM」(2026-11-21 사용자 「워크플로우 설정에 저장버튼이 없냐」)
          tip: document.querySelector('section#plan_to_report select[name="slot-mode-plan_to_report"]').title,
          srcSaved: (document.querySelector('section#plan_to_report .wf-slot[data-role=source] .wf-slot-saved') || {}).textContent || '' }; }""")
        st = forms()["slots"].get(JOB, {}).get("target")
        check("② 「고정」 → 서버 설정 · 저장한 양식 줄에 「쓰는 워크플로우: … · 고정」 · 지우기 · 문서 종류가 꺼짐 · 「늘 이 양식으로」",
              st == {"file": fid, "mode": "fixed"} and used["chip"].endswith("· 고정") and used["del"] and used["kind"] and "늘 이 양식으로" in used["note"] and used["mode"] == "fixed", [st, used])
        check("② 고른 칸 옆에 「✓ 저장됨 HH:MM」(저장 단추가 없는 칸 — 다시 그려도 남음) · 고르기의 풍선 글 「고르면 바로 저장됩니다」 · 안 고친 칸(원본)에는 없음",
              re.fullmatch(r"✓ 저장됨 \d\d:\d\d", used["saved"]) is not None and used["tip"].startswith("고르면 바로 저장됩니다") and used["srcSaved"] == "", used)
        page.screenshot(path=str(OUT / "02_slots.png"))

        # ---- ③ 첫 화면 — 고정: 목적 문서 칸 = 양식 → 「워크플로우 시작」
        n0 = len(works())
        home = ctx.new_page()
        home.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        home.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        home.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        home.goto(base)
        home.wait_for_selector("#homeDash[data-state=pick] select")
        pick_files(home, [PLAN])
        home.locator("#homeFiles [data-hf-focus=project]").fill("양식 프로젝트")
        home.select_option("#homeDash select", JOB)
        home.wait_for_selector("#homeDash[data-state=ready] .home-dash-form[data-mode=fixed]", timeout=30000)
        home.wait_for_selector("#homeDash .home-dash-docs li", timeout=30000)   # 등록부(역할 이름)가 온 뒤
        h = home.evaluate(HOME)
        tgt = dict(h["docs"]).get("target", "")
        check("③ 고정 — 문서 칸 목적 = 「양식 「…」(저장한 날 …)」 · 원본 = 목록의 사업계획서 · 「양식: 고정」 · 바꾸는 단추 없음 · 「워크플로우 시작」 켜짐(강조) · 카드 「양식으로 시작」",
              f"양식 「{REPORT.stem}」" in tgt and "저장한 날" in tgt and PLAN.name in dict(h["docs"]).get("source", "") and h["form"]["use"] == "form" and "양식: 고정" in h["form"]["text"]
              and h["form"]["flip"] is None and "고정" in h["form"]["text"] and h["start"] == {"text": "워크플로우 시작", "off": False, "primary": True} and h["resume"] is None
              and h["card"].startswith("양식으로 시작") and h["tags"] == ["원본 문서"] and h["cap"].startswith("목적 문서 = 양식 「"), h)
        home.screenshot(path=str(OUT / "03_home_fixed.png"))
        home.locator('#homeDash [data-hd-focus="start"]').click()
        home.wait_for_selector("#homeDash[data-state=live]", timeout=120000)
        home.wait_for_function("() => !hf.busy && !homeTaskBusy", timeout=120000)
        h = home.evaluate(HOME)
        ws = works()
        made = [w for w in ws if (w.get("task") or {}).get("project") == "양식 프로젝트"]
        tw = next((w for w in made if w["task"].get("file") == "report"), None)
        sw = next((w for w in made if w["task"].get("file") == "plan"), None)
        wj = tmp / "works" / tw["id"] / "work.json" if tw else None
        full = json.loads(wj.read_text(encoding="utf-8")) if wj and wj.is_file() else {}
        check("③ 「워크플로우 시작」 → 첫 화면 그대로 · 목적 문서 = 양식으로 만든 새 작업(source form · 고정) · 원본 문서 = 목록의 사업계획서(같은 프로젝트 · 워크플로우 · 라운드) · 대시보드 기억",
              h["home"] and h["id"] is None and len(ws) == n0 + 2 and tw is not None and sw is not None and tw["task"]["job"] == JOB and sw["task"]["job"] == JOB
              and (tw["task"].get("round") or 1) == (sw["task"].get("round") or 1) and h["memo"] == {"job": JOB, "wid": tw["id"]}
              and full.get("source") == "form" and (full.get("form") or {}).get("id") == fid and (full.get("form") or {}).get("mode") == "fixed", [h, [(w["id"], w.get("task")) for w in made], {k: full.get(k) for k in ("source", "form")}])
        twid = tw["id"] if tw else ""

        # ---- ④ 같은 프로젝트로 다시 — 「이어서」 가 먼저
        home.locator('#homeDash [data-hd-focus="other"]').click()
        home.wait_for_selector("#homeDash[data-state=pick] select")
        pick_files(home, [PLAN])
        home.locator("#homeFiles [data-hf-focus=project]").fill("양식 프로젝트")
        home.select_option("#homeDash select", JOB)
        home.wait_for_selector("#homeDash[data-state=ready] [data-hd-focus=resume]", timeout=30000)
        h = home.evaluate(HOME)
        check("④ 같은 프로젝트에 하던 작업 — 알림 · 「이어서」(강조) · 「새로 시작」(강조 아님)",
              h["resume"] == {"text": "이어서", "off": False, "primary": True} and h["start"]["text"] == "새로 시작" and not h["start"]["primary"] and any("하던 작업이 있습니다" in x for x in h["notes"]), h)
        n1 = len(works())
        home.locator('#homeDash [data-hd-focus="resume"]').click()
        home.wait_for_selector("#homeDash[data-state=live]", timeout=30000)
        h = home.evaluate(HOME)
        check("④ 「이어서」 → 그 작업의 대시보드(새 작업 없음 · 기억 = 그 작업)", h["memo"] == {"job": JOB, "wid": twid} and len(works()) == n1 and h["home"], h)

        # ---- ⑤ 기본값 — 목록에서 목적 문서를 안 고르면 양식 · 「목록의 파일로」 ↔ 「양식으로」
        assert requests.put(f"{base}/api/workflow-slots/{JOB}", json={"target": {"file": fid, "mode": "default"}}, timeout=10).ok
        home.locator('#homeDash [data-hd-focus="other"]').click()
        home.wait_for_selector("#homeDash[data-state=pick] select")
        home.evaluate("() => hfFormsLoad(true)")
        home.select_option("#homeDash select", JOB)
        home.wait_for_selector("#homeDash[data-state=ready] .home-dash-form[data-mode=default][data-use=form]", timeout=30000)
        a = home.evaluate(HOME)
        home.locator('#homeDash [data-hd-focus="form"]').click()
        home.wait_for_selector("#homeDash .home-dash-form[data-use=list]")
        b = home.evaluate(HOME)
        home.locator('#homeDash [data-hd-focus="form"]').click()
        home.wait_for_selector("#homeDash .home-dash-form[data-use=form]")
        c = home.evaluate(HOME)
        check("⑤ 기본값 — 목적 문서를 안 고름 = 양식(「양식: 기본값」 · 「목록의 파일로」) → 목적 = 목록의 문서 · 원본 칸 비움(「양식으로」) → 다시 양식",
              "양식 「" in dict(a["docs"])["target"] and a["form"]["flip"]["text"] == "목록의 파일로" and "양식: 기본값" in a["form"]["text"]
              and dict(b["docs"])["target"].endswith(PLAN.name) and dict(b["docs"])["source"].endswith("없음") and b["form"]["flip"]["text"] == "양식으로" and "양식 「" in dict(c["docs"])["target"], [a, b, c])
        home.screenshot(path=str(OUT / "05_home_default.png"))

        # ---- ⑥ 고정 + 워크플로우 카드 — 양식으로 시작해 문서 화면이 열린다
        assert requests.put(f"{base}/api/workflow-slots/{JOB}", json={"target": {"file": fid, "mode": "fixed"}}, timeout=10).ok
        home.evaluate("() => hfFormsLoad(true)")
        home.locator("#homeFiles [data-hf-focus=project]").fill("카드 프로젝트")
        home.wait_for_function("() => /^양식으로 시작/.test((document.querySelector('#taskCards [data-task=plan_to_report] .task-card-go') || {}).textContent || '')", timeout=30000)
        home.locator("#taskCards [data-task=plan_to_report]").click()
        home.wait_for_function("() => !!state.id && (state.task || {}).job === 'plan_to_report'", timeout=180000)
        cw = [w for w in works() if (w.get("task") or {}).get("project") == "카드 프로젝트"]
        ct = next((w for w in cw if w["task"].get("file") == "report"), None)
        check("⑥ 고정 + 카드 → 문서 화면이 그 양식으로 만든 목적 문서로 열림 · 원본 문서(사업계획서)도 같은 프로젝트",
              ct is not None and home.evaluate("() => state.id") == ct["id"] and any(w["task"].get("file") == "plan" for w in cw), [(w["id"], w.get("task")) for w in cw])

        # ---- 작업의 처음 올린 원본을 「양식으로 저장」
        page.reload()
        page.wait_for_selector("#wfForms .wf-ff-row")
        page.locator("#wfForms .wf-ff-add > summary").click()
        page.wait_for_function("() => document.querySelectorAll('#wfForms .wf-ff-add select')[1].options.length > 1", timeout=30000)
        src = sw["id"] if sw else ""
        page.select_option("#wfForms .wf-ff-add-row:nth-child(3) select", src)
        page.locator("#wfForms .wf-ff-add button", has_text="양식으로 저장").click()
        page.wait_for_function("() => document.querySelectorAll('#wfForms .wf-ff-row').length === 2", timeout=60000)
        ff = forms()["files"]
        check("작업(사업계획서)의 처음 올린 원본을 「양식으로 저장」 → 새 양식(문서 종류 = 사업계획서)", len(ff) == 2 and ff[1]["kind"] == "plan" and ff[1]["fmt"] == "hwpx", ff)

        # ---- ⑥b 원본 칸 = 저장한 양식(② §18-9 — 수가 1인 칸마다: 2026-11-20 사용자 "각 1이 되는것들은 특정 문서로 지정할 수 있도록, default 로")
        pid = ff[1]["id"] if len(ff) > 1 else ""
        sel_src = f'section#{JOB} select[name="slot-mode-{JOB}-source"]'
        page.locator("#wfViewList").click()
        page.wait_for_selector(f"{sel_src}:not([disabled])", timeout=30000)
        page.select_option(sel_src, "default")
        page.wait_for_function("(s) => { const x = document.querySelector(s); return !!x && x.value === 'default' && !x.disabled; }", arg=sel_src, timeout=30000)
        ss = forms()["slots"].get(JOB, {})
        check("⑥b /workflow 문서 칸 — 원본 칸에 「양식: 기본값」 + 사업계획서 양식 → 서버 설정(원본 칸 · 목적 칸은 고정 그대로)",
              ss.get("source") == {"file": pid, "mode": "default"} and (ss.get("target") or {}).get("mode") == "fixed", ss)
        home.goto(base)
        home.wait_for_selector("#homeDash[data-state]", timeout=30000)
        if home.evaluate("() => document.getElementById('homeDash').dataset.state") != "pick":
            home.locator('#homeDash [data-hd-focus="other"]').click()
        home.wait_for_selector("#homeDash[data-state=pick] select", timeout=30000)
        home.evaluate("() => hfFormsLoad(true)")   # 목록이 비어 프로젝트 칸이 없다 — 임시 프로젝트로 묶인다(새 작업은 앞뒤 목록의 차이로 찾는다)
        home.select_option("#homeDash select", JOB)
        home.wait_for_selector("#homeDash[data-state=ready] .home-dash-docs li[data-role=source]", timeout=30000)
        h = home.evaluate(HOME)
        src_line = dict(h["docs"]).get("source", "")
        check("⑥b 첫 화면 — 목록이 비어도 원본 줄 = 「양식 「…」(저장한 날 …) · 양식: 기본값」 · 목적 = 고정 양식 · 「워크플로우 시작」 켜짐",
              "양식 「" in src_line and "양식: 기본값" in src_line and "양식 「" in dict(h["docs"]).get("target", "") and h["start"] and not h["start"]["off"], h)
        n2, before = len(works()), {w["id"] for w in works()}
        home.locator('#homeDash [data-hd-focus="start"]').click()
        home.wait_for_selector("#homeDash[data-state=live]", timeout=120000)
        home.wait_for_function("() => !hf.busy && !homeTaskBusy", timeout=120000)
        mw = [w for w in works() if w["id"] not in before]
        sx = next((w for w in mw if w["task"].get("file") == "plan"), None)
        tx = next((w for w in mw if w["task"].get("file") == "report"), None)
        sj = json.loads((tmp / "works" / sx["id"] / "work.json").read_text(encoding="utf-8")) if sx else {}
        check("⑥b 「워크플로우 시작」 → 목적 = 고정 양식 · 원본 = 사업계획서 양식으로 만든 새 작업(같은 프로젝트 · 라운드 · source form · 기본값)",
              len(works()) == n2 + 2 and sx is not None and tx is not None and (sx["task"].get("round") or 1) == (tx["task"].get("round") or 1) and sx["task"].get("project") == tx["task"].get("project") != ""
              and sj.get("source") == "form" and (sj.get("form") or {}).get("id") == pid and (sj.get("form") or {}).get("mode") == "default", [[(w["id"], w.get("task")) for w in mw], {k: sj.get(k) for k in ("source", "form")}])
        home.screenshot(path=str(OUT / "06b_source_form.png"))

        # ---- ⑦ 좁은 폭(조립 폼의 「문서 입출력」 도)
        page.set_viewport_size({"width": 400, "height": 900})
        page.goto(f"{base}/workflow#overview")
        page.wait_for_selector("#wfCompose [data-wf-compose=open]", timeout=30000)
        page.locator("#wfCompose [data-wf-compose=open]").click()
        page.wait_for_selector("#wfCompose .wf-io-slots", timeout=30000)
        io = page.evaluate("() => { const m = document.getElementById('wfMain'), b = document.querySelector('#wfCompose .wf-iobox').getBoundingClientRect(); return { over: m.scrollWidth > m.clientWidth + 1, right: b.right <= m.getBoundingClientRect().right + 1, src: [...document.querySelector('#wfCompose .wf-io-slots li[data-role=source] select[name=draft-form-source]').options].map((o) => o.value) }; }")
        check("⑦ 400px — 조립 폼의 「문서 입출력」 이 가로로 넘치지 않음 · 원본 칸의 기본 문서 고르기에 사업계획서 양식", not io["over"] and io["right"] and io["src"] == [pid], io)
        page.goto(f"{base}/workflow#wfForms")
        page.wait_for_selector("#wfForms .wf-ff-row")
        fit = page.evaluate("() => { const m = document.getElementById('wfMain'); return { over: m.scrollWidth > m.clientWidth + 1, doc: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1 }; }")
        page.locator("#wfViewList").click()
        page.wait_for_selector("section#plan_to_report .wf-slots")
        page.evaluate("() => document.querySelector('section#plan_to_report .wf-slots').scrollIntoView()")
        fit2 = page.evaluate("() => { const m = document.getElementById('wfMain'), b = document.querySelector('section#plan_to_report .wf-slots').getBoundingClientRect(); return { over: m.scrollWidth > m.clientWidth + 1, right: b.right <= m.getBoundingClientRect().right + 1 }; }")
        page.screenshot(path=str(OUT / "07_narrow.png"))
        check("⑦ 400px — 저장한 양식 절 · 문서 칸이 가로로 넘치지 않음", not fit["over"] and not fit["doc"] and not fit2["over"] and fit2["right"], [fit, fit2])

        # ---- ⑧ 그 칸에서 바로 양식 올리기(② §18-9 「그 칸에서 올리기」 — 2026-11-20 사용자 "이거 클릭도 안되고 왜 아무것도 안해?": 저장한 양식이 없으면 그 칸에 꺼진 고르기 둘뿐이었다)
        requests.put(f"{base}/api/workflow-slots/{JOB}", json={"target": None, "source": None}, timeout=10)
        for x in forms()["files"]:
            requests.delete(f"{base}/api/form-files/{x['id']}", timeout=10)
        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto(f"{base}/workflow#overview")
        page.reload()   # 주소의 # 만 바뀌면 새로 읽지 않는다 — ⑦ 에서 펴 둔 조립 폼 · 지운 양식의 옛 목록을 버리고 새로
        page.wait_for_selector("#wfCompose [data-wf-compose=open]", timeout=30000)
        page.locator("#wfCompose [data-wf-compose=open]").click()
        SRC = "#wfCompose .wf-io-slots li[data-role=source]"
        page.wait_for_selector(f"{SRC} button[name=draft-up-source]", timeout=30000)
        PICK = """(s) => { const li = document.querySelector(s), vis = (e) => !!e && e.getClientRects().length > 0, q = (x) => li.querySelector(x), m = q('select[name*=-mode-]'), f = q('select[name*=-form-]'), u = q('.wf-slot-up button');
          return { mode: vis(m), form: vis(f), up: vis(u), upOff: !u || u.disabled, upText: u ? u.textContent : '', modeVal: m ? m.value : null, modeOff: !m || m.disabled, formVal: f ? f.value : null, formOff: !f || f.disabled,
            err: (q('.wf-slot-up .wf-slot-err') || {}).textContent || '', note: (q('.wf-slot-pick > .wf-muted') || {}).textContent || '', rows: document.querySelectorAll('#wfForms .wf-ff-row').length }; }"""
        d0 = page.evaluate(PICK, SRC)
        check("⑧ 저장한 양식이 없을 때 — 조립 폼의 원본 칸: 꺼진 고르기 둘은 안 보이고 「양식 올리기…」 만(켜짐)",
              not forms()["files"] and not d0["mode"] and not d0["form"] and d0["up"] and not d0["upOff"] and d0["upText"] == "양식 올리기…", d0)
        page.screenshot(path=str(OUT / "08_slot_upload_empty.png"))
        page.locator(f"{SRC} input[type=file]").set_input_files(str(PLAN))
        page.wait_for_function("(s) => { const m = document.querySelector(s + ' select[name=draft-mode-source]'); return !!m && !m.hidden && m.value === 'default'; }", arg=SRC, timeout=60000)
        f8, d1 = forms()["files"], page.evaluate(PICK, SRC)
        check("⑧ 「양식 올리기…」 → 저장한 양식(문서 종류 = 그 칸의 종류: 사업계획서) · 그 칸에 「양식: 기본값」 + 올린 양식이 골라짐(고르기 켜짐) · 「저장한 양식」 절에도 그 줄 · 단추는 그대로(또 올릴 수 있다)",
              len(f8) == 1 and f8[0]["kind"] == "plan" and d1["mode"] and d1["form"] and d1["modeVal"] == "default" and not d1["modeOff"] and d1["formVal"] == f8[0]["id"] and not d1["formOff"] and d1["up"] and not d1["upOff"]
              and d1["rows"] == 1 and not d1["err"], [f8, d1])
        page.screenshot(path=str(OUT / "08_slot_upload_done.png"))
        page.locator("#wfViewList").click()
        TGT = f"section#{JOB} .wf-slots .wf-slot[data-role=target]"
        page.wait_for_selector(f'{TGT} button[name="slot-up-{JOB}"]', timeout=30000)
        l0, ls = page.evaluate(PICK, TGT), page.evaluate(PICK, f"section#{JOB} .wf-slots .wf-slot[data-role=source]")
        check("⑧ 워크플로우 절의 「문서 칸」 — 목적 칸(연차보고서 양식 없음): 고르기 둘은 안 보이고 「양식 올리기…」 + 까닭 글 / 원본 칸(방금 올린 사업계획서 양식): 고르기 켜짐",
              not l0["mode"] and not l0["form"] and l0["up"] and not l0["upOff"] and "「양식 올리기…」 로" in l0["note"] and "연차보고서 양식을 올리세요" in l0["note"] and ls["mode"] and not ls["modeOff"] and ls["modeVal"] == "", [l0, ls])
        page.locator(f"{TGT} input[type=file]").set_input_files(str(REPORT))
        page.wait_for_function("(s) => { const m = document.querySelector(s + ' select[name*=-mode-]'); return !!m && !m.hidden && m.value === 'default' && !m.disabled; }", arg=TGT, timeout=60000)
        f9, l1, st8 = forms()["files"], page.evaluate(PICK, TGT), forms()["slots"].get(JOB, {})
        rid = next((x["id"] for x in f9 if x["kind"] == "report"), "")
        check("⑧ 그 칸에서 올리면 바로 건다 — 서버 설정(목적 칸 = 올린 양식 · 기본값 · 원본 칸은 그대로 없음) · 그 칸의 고르기에 그 양식 · 「저장한 양식」 절 두 줄",
              len(f9) == 2 and rid != "" and st8.get("target") == {"file": rid, "mode": "default"} and not st8.get("source") and l1["modeVal"] == "default" and l1["formVal"] == rid and not l1["formOff"] and l1["rows"] == 2 and not l1["err"], [f9, st8, l1])
        page.locator(f"{TGT} input[type=file]").set_input_files(str(ROOT / "README.md") if (ROOT / "README.md").is_file() else str(Path(__file__)))
        page.wait_for_function("(s) => ((document.querySelector(s + ' .wf-slot-up .wf-slot-err') || {}).textContent || '') !== ''", arg=TGT, timeout=30000)
        l2 = page.evaluate(PICK, TGT)
        check("⑧ 받지 않는 형식의 파일 — 올리지 않고 그 칸에 까닭(「… 파일만 받습니다」) · 단추는 다시 켜짐 · 설정 · 양식은 그대로",
              "파일만 받습니다" in l2["err"] and not l2["upOff"] and l2["upText"] == "양식 올리기…" and len(forms()["files"]) == 2 and forms()["slots"].get(JOB, {}).get("target") == {"file": rid, "mode": "default"}, l2)

        # ---- ⑨ 조립 폼의 목적 문서 칸 — 이관 「1 → N」 의 목적은 수가 「N」 이어도 양식을 건다(② §18-9 — 2026-11-20 사용자 "여기 목적문서 양식 넣는게 없네? 왜 없냐?": 전에는 수가 1인 칸만이라 그 칸에 고르기 · 올리기가 없었다)
        page.goto(f"{base}/workflow#overview")
        page.reload()
        page.wait_for_selector("#wfCompose [data-wf-compose=open]", timeout=30000)
        page.locator("#wfCompose [data-wf-compose=open]").click()
        DT = "#wfCompose .wf-io-slots li[data-role=target]"
        page.wait_for_selector(f"{DT} button[name=draft-up-target]", timeout=30000)
        t0 = page.evaluate(PICK, DT)
        t0["count"] = page.evaluate("(s) => document.querySelector(s + ' .wf-io-count').textContent", DT)
        t0["opts"] = page.evaluate("(s) => [...document.querySelector(s + ' select[name=draft-form-target]').options].map((o) => o.value)", DT)
        check("⑨ 조립 폼(새 워크플로우 · 「1 → N」)의 목적 문서 칸 「N」 — 「양식: 없음」 고르기 + 걸 수 있는 양식(연차보고서 양식만) + 「양식 올리기…」(켜짐)",
              t0["count"] == "N" and t0["mode"] and t0["modeVal"] == "" and not t0["modeOff"] and t0["form"] and t0["formOff"] and t0["opts"] == [rid] and t0["up"] and not t0["upOff"] and t0["upText"] == "양식 올리기…", t0)
        page.select_option(f"{DT} select[name=draft-mode-target]", "default")
        page.fill("#wfCompose input[name=name]", "목적 양식 워크플로우")
        page.screenshot(path=str(OUT / "09_draft_target_form.png"))
        page.click("#wfCompose form button[type=submit]")
        page.wait_for_function("() => /^#u_[0-9a-f]{8}$/.test(location.hash)", timeout=30000)
        key9 = page.evaluate("() => location.hash.slice(1)")
        page.wait_for_function("(k) => !!document.getElementById(k)", arg=key9, timeout=30000)
        st9 = forms()["slots"].get(key9, {})
        check("⑨ 「워크플로우 만들기」 → 만든 워크플로우의 목적 칸에 고른 양식이 걸림(기본값) · 걸지 못했다는 알림 없음",
              st9.get("target") == {"file": rid, "mode": "default"} and not st9.get("source") and not any("걸지 못했습니다" in d for d in dialogs), [key9, st9, dialogs[-2:]])
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

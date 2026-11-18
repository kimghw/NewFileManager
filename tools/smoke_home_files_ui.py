"""시작 화면의 문서 목록(spec_작업 ② §15-1 — home_files.js) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 흉내 없이 진짜 끝점으로.

    python -X utf8 tools/smoke_home_files_ui.py <그림·임시 폴더> [--port 18394]

보는 것: 「파일 선택」 = 여러 개 · 목록에 모임(서버에는 아직 안 올림) · 시작 화면에 놓아도 목록 · 같은 파일은 한 번 · 카드 글 「목록으로 시작」 ·
상단 소개 + 넓은 업로드 · 파일 모양 카드마다 약칭 · 목적 문서를 고르기 전/형식이 안 맞는 TASK는 비활성 · 「TASK 없이 열기」 + 약칭 → 이름 뒤 「(약칭)」 · 이관: 프로젝트 없이 두 문서면 알림 → 프로젝트를 적으면 목적 문서 = 연차보고서(라운드 1) +
사업계획서를 같은 프로젝트·TASK·라운드로(첨부 파일 칸이 저절로 잇는다) · 쓴 문서는 목록에서 빠짐 · 양식 표준화: 나머지 문서는 확인 뒤 목록에 남김 · 같은 파일로 다른 TASK 를 하던 작업이면
「같은 파일 고르기」 창(그 줄은 「그대로 열기」 만 · 목록 줄은 「고르세요」 · 프로젝트 칸) → 「새 작업으로 시작」(spec_작업 ② §1 — 2026-11-18) ·
약칭은 문서 선택을 바꿔도 유지하고 원본 문서에도 저장 · 파일 삭제 후 하나가 남으면 자동 선택 · 좁은 창에서 목록이 넘치지 않음."""
import argparse
import base64
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
ap.add_argument("--port", type=int, default=18394)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)

SMALL, PLAN, DOCX = "기술수요조사서.hwpx", "연구개발계획서_양식.hwpx", "기술수요조사서.docx"
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails, dialogs = [], [], []
answer = {"accept": True}


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:500] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def on_dialog(d):
    dialogs.append(d.message)
    if answer["accept"]:
        d.accept()
    else:
        d.dismiss()


def works():
    return requests.get(f"{base}/api/works", timeout=10).json()


def sample(name):
    return (ROOT / "samples" / name).read_bytes()


LIST = """() => { const p = document.getElementById('homeFiles'), g = (s) => document.querySelector(s);
  return { vis: !!p && !p.hidden && p.getClientRects().length > 0, has: g('#drop').classList.contains('has-files'), title: p.hidden ? '' : (p.querySelector('h3') || {}).textContent,
    rows: [...p.querySelectorAll('.hf-row')].map((r) => ({ name: r.querySelector('.hf-name').textContent, ext: r.querySelector('.hf-ext').textContent, tag: r.querySelector('.hf-tag').textContent, on: r.querySelector('input[type=radio]').checked, alias: (r.querySelector('.hf-alias input') || {}).value })),
    plain: !!p.querySelector('[data-hf-plain]') && !p.querySelector('[data-hf-plain]').disabled, status: (p.querySelector('.hf-status') || {}).textContent || '',
    go: Object.fromEntries([...document.querySelectorAll('#taskCards .task-card')].map((b) => [b.dataset.task, b.querySelector('.task-card-go').textContent.trim()])),
    disabled: Object.fromEntries([...document.querySelectorAll('#taskCards .task-card')].map((b) => [b.dataset.task, b.disabled || b.getAttribute('aria-disabled') === 'true'])),
    id: state.id, toast: g('#toast').hidden ? '' : g('#toast').textContent, pick: g('#pickBtn').getClientRects().length > 0 }; }"""
DROP = """([files, sel]) => { const dt = new DataTransfer(); for (const [b64, name] of files) { const bin = atob(b64), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); dt.items.add(new File([u], name)); }
  const t = document.querySelector(sel), ev = (n) => new DragEvent(n, { bubbles: true, cancelable: true, dataTransfer: dt }); t.dispatchEvent(ev('dragover')); t.dispatchEvent(ev('drop')); }"""
b64 = lambda data: base64.b64encode(data).decode()


def go_home(page):
    page.locator("#homeLink").click()
    page.wait_for_function("() => document.body.classList.contains('no-doc') && state.id == null")
    page.wait_for_timeout(200)


def pick(page, names):
    with page.expect_file_chooser() as fc:
        page.locator("#pickBtn").click()
    fc.value.set_files([{"name": n, "mimeType": "application/octet-stream", "buffer": sample(n)} for n in names])
    page.wait_for_function("(n) => document.querySelectorAll('#homeFiles .hf-row').length >= n", arg=len(names))
    return fc.value


try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        page = br.new_page(viewport={"width": 1400, "height": 960})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("dialog", on_dialog)
        page.goto(base)
        page.wait_for_selector("#taskCards [data-task=plan_fit]")
        L = page.evaluate(LIST)
        check("처음 — 목록 없음 · 「파일 선택」 보임 · 카드 글은 전처럼 「… 올려 시작」", not L["vis"] and not L["has"] and L["pick"] and L["go"]["plan_fit"].startswith("사업계획서 올려 시작"), L)
        layout = page.evaluate("""() => { const r = (s) => document.querySelector(s).getBoundingClientRect(), intro = r('.home-heading'), drop = r('#drop'), hero = r('.home-intro');
          return { above: intro.bottom <= drop.top, wide: drop.width >= hero.width * .95, width: drop.width, hero: hero.width }; }""")
        check("넓은 창 — 소개는 상단 · 파일 입력 영역은 본문 폭 전체", layout["above"] and layout["wide"], layout)
        page.screenshot(path=str(OUT / "0_home_wide.png"))

        # ---- 1. 「파일 선택」 = 여러 개 → 목록(서버에는 안 올림) · 시작 화면에 놓아도 목록 · 같은 파일은 한 번
        fc = pick(page, [SMALL, PLAN])
        check("「파일 선택」 → 여러 개 · hwp·hwpx·docx", fc.is_multiple() and fc.element.evaluate("(e) => e.accept") == ".hwp,.hwpx,.docx")
        L = page.evaluate(LIST)
        check("목록 — 파일 카드 둘 · 목적 문서 기본 선택 없음 · 아직 아무것도 안 올림 · 목적 문서를 고르기 전에는 TASK 비활성",
              L["vis"] and L["has"] and not L["pick"] and [r["name"] for r in L["rows"]] == [SMALL, PLAN] and not any(r["on"] for r in L["rows"]) and L["id"] is None and works() == []
              and all(L["disabled"].values()) and L["go"]["report_merge"] == "준비 중" and L["title"] == "올린 문서 2개" and not L["plain"], L)
        cards = page.evaluate("""() => [...document.querySelectorAll('#homeFiles .hf-row')].map((e) => { const r = e.getBoundingClientRect(), i = e.querySelector('.hf-file-icon').getBoundingClientRect();
          return { x: r.x, y: r.y, right: r.right, width: r.width, height: r.height, icon: i.width > 0 && i.height > 0, alias: !!e.querySelector('.hf-alias input') }; })""")
        check("파일마다 개별 카드 · 문서 아이콘 · 약칭 입력 · 넓은 창에서 나란히", all(r["width"] > 0 and r["height"] > 0 and r["icon"] and r["alias"] for r in cards)
              and abs(cards[0]["y"] - cards[1]["y"]) < 2 and cards[0]["right"] <= cards[1]["x"], cards)
        page.locator("#homeFiles .hf-row").nth(0).locator(".hf-alias input").fill("보고")
        page.locator("#homeFiles .hf-row").nth(1).locator(".hf-alias input").fill("계획")
        page.locator("#homeFiles .hf-row").nth(0).locator("input[type=radio]").check()
        page.locator("#homeFiles .hf-row").nth(1).locator("input[type=radio]").check()
        L = page.evaluate(LIST)
        check("목적 문서 변경 — 각 문서의 약칭 유지 · 선택은 하나 · TASK 활성", [r["alias"] for r in L["rows"]] == ["보고", "계획"]
              and [r["on"] for r in L["rows"]] == [False, True] and not L["disabled"]["plan_fit"], L)
        page.evaluate(DROP, [[[b64(sample(DOCX)), DOCX]], "#empty"])
        page.wait_for_function("() => document.querySelectorAll('#homeFiles .hf-row').length === 3")
        page.evaluate(DROP, [[[b64(sample(DOCX)), DOCX], [b64(b"x"), "메모.txt"]], "#empty"])
        page.wait_for_timeout(300)
        L = page.evaluate(LIST)
        check("시작 화면에 놓아도 목록 · 같은 파일은 한 번 · 그 밖의 형식은 알림", len(L["rows"]) == 3 and L["rows"][2]["ext"] == "DOCX" and "TASK 없이 열기 · 서식 복사" in L["rows"][2]["tag"]
              and "메모.txt" in L["toast"] and works() == [], L)
        page.screenshot(path=str(OUT / "1_list.png"))
        for width in (400, 320):
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(200)
            page.locator("#homeFiles .hf-row").nth(0).locator("input[type=radio]").check()
            fit = page.evaluate("""() => { const e = document.getElementById('empty'), p = document.getElementById('homeFiles'), bounds = e.getBoundingClientRect();
              return e.scrollWidth <= e.clientWidth + 1 && [...p.querySelectorAll('.hf-row, .hf-name, .hf-alias input, .hf-foot button')].every((x) => {
                const r = x.getBoundingClientRect(); return r.left >= bounds.left - 1 && r.right <= bounds.right + 1; }); }""")
            check(f"좁은 창({width}px) — 파일 카드·약칭·버튼이 가로로 넘치지 않음", fit)
            page.locator("#drop").screenshot(path=str(OUT / f"1_list_narrow_{width}.png"))
        page.set_viewport_size({"width": 1400, "height": 960})

        # ---- 2. docx 를 목적 문서로 → 지원하는 TASK만 활성 · 「TASK 없이 열기」 + 약칭
        page.locator("#homeFiles .hf-row").nth(2).locator("input[type=radio]").check()
        L = page.evaluate(LIST)
        check("docx 목적 문서 — 양식 TASK는 비활성 · 서식 복사·그냥 열기는 활성 · 아직 안 올림", L["id"] is None and L["disabled"]["plan_fit"] and not L["disabled"]["style_copy"] and works() == [] and L["plain"], L)
        page.locator("#homeFiles .hf-row.on .hf-alias input").fill("메모")
        check("약칭 미리 보기", "기술수요조사서(메모).docx" in page.locator("#homeFiles .hf-row.on .hf-shown").inner_text())
        page.locator("#homeFiles [data-hf-plain]").click()
        page.wait_for_function("() => state.id && state.format === 'docx' && (state.name || '').endsWith('(메모).docx')", timeout=120000)
        did = page.evaluate("() => state.id")
        w = next(x for x in works() if x["id"] == did)
        check("「TASK 없이 열기」 — docx 가 열림 · 이름 뒤 「(별칭)」 · TASK 없음 · 목록에서 그 문서만 빠짐",
              w["alias"] == "메모" and w["name"] == "기술수요조사서(메모).docx" and not ((w.get("task") or {}).get("job")) and page.evaluate("() => hf.files.map((f) => f.name)") == [SMALL, PLAN], (w, page.evaluate("() => hf.files.map((f) => f.name)")))

        # ---- 3. 이관 — 프로젝트 없이 두 문서면 알림 · 적으면 목적 문서(연차보고서) + 사업계획서(같은 프로젝트·TASK·라운드)
        go_home(page)
        L = page.evaluate(LIST)
        check("시작 화면에 돌아오면 남은 목록 그대로(둘 · 목적 문서 풀림)", [r["name"] for r in L["rows"]] == [SMALL, PLAN] and not any(r["on"] for r in L["rows"]), L)
        page.locator("#homeFiles .hf-row").nth(0).locator("input[type=radio]").check()
        check("다른 파일을 열고 돌아와도 남은 문서의 약칭 유지", [r["alias"] for r in L["rows"]] == ["보고", "계획"], L)
        # 2026-11-18(spec_작업 ② §17 「임시 프로젝트」): 이름을 비워도 막지 않는다 — 임시 이름으로 묶는다(아래 끝에서 본다). 칸은 고르기 목록(작업 내용의 칸과 같은 도우미)
        pin = page.locator("#homeFiles [data-hf-focus=project]")
        check("프로젝트 칸 — 「비우면 임시 이름」 · 고르기 목록(role=combobox · datalist 없음)", pin.get_attribute("placeholder") == "비우면 임시 이름"
              and pin.get_attribute("role") == "combobox" and pin.get_attribute("list") is None)
        pin.fill("시험 P")
        page.locator("#taskCards [data-task=plan_to_report]").click()
        page.wait_for_function("() => state.id && state.task.job === 'plan_to_report' && state.task.file === 'report' && document.getElementById('panel').dataset.tool === 'Div'", timeout=120000)
        rid = page.evaluate("() => state.id")
        page.wait_for_function("() => worksList.some((w) => (w.task || {}).file === 'plan' && (w.task || {}).project === '시험 P')", timeout=120000)
        page.wait_for_function("(r) => { const s = document.querySelector('#paneDiv select[data-task-file=plan]'); return !!s && !!s.value && state.id === r; }", arg=rid, timeout=60000)
        ws = {x["id"]: x for x in works()}
        rep = ws[rid]
        pid = page.evaluate("() => document.querySelector('#paneDiv select[data-task-file=plan]').value")
        plan = ws.get(pid, {})
        check("목적 문서 = 연차보고서 · 프로젝트 「시험 P」 라운드 1(start-task) · 이름 = 올린 이름_프로젝트(별칭)",
              rep["task"] == {"kind": "rnd", "file": "report", "job": "plan_to_report", "project": "시험 P", "round": 1} and rep["name"] == "기술수요조사서_시험 P(보고).hwpx"
              and page.evaluate("() => state.name") == "기술수요조사서_시험 P(보고).hwpx", rep)
        check("사업계획서 = 새 작업 · 같은 프로젝트·TASK·라운드 · 첨부 파일 칸에 저절로 듦 · 원본 약칭도 저장",
              plan.get("task") == {"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": "시험 P", "round": 1} and plan.get("name") == "연구개발계획서_양식(계획).hwpx" and plan.get("alias") == "계획", plan)
        check("쓴 문서는 목록에서 빠짐 → 목록 비고 카드 글은 전처럼", page.evaluate("() => hf.files.length === 0 && document.getElementById('homeFiles').hidden && !document.getElementById('drop').classList.contains('has-files')")
              and page.evaluate("() => document.querySelector('#taskCards [data-task=plan_fit] .task-card-go').textContent.trim()").startswith("사업계획서 올려 시작"))
        page.screenshot(path=str(OUT / "3_transfer.png"))

        # ---- 4. 양식 표준화 — 나머지는 확인 뒤 목록에 남김 · 같은 파일로 다른 TASK 를 하던 작업이면 새 작업
        go_home(page)
        pick(page, [SMALL, PLAN])
        page.locator("#homeFiles .hf-row").nth(1).locator("input[type=radio]").check()
        n = len(works())
        answer["accept"] = False
        dialogs.clear()
        page.locator("#taskCards [data-task=plan_fit]").click()
        page.wait_for_timeout(300)
        check("양식 표준화 · 나머지 문서 있음 → 확인 창(취소면 아무것도 안 올림)", len(dialogs) == 1 and "목적 문서 하나로" in dialogs[0] and "나머지 1개는 목록에 남깁니다" in dialogs[0]
              and len(works()) == n and page.evaluate("() => state.id") is None, dialogs)
        answer["accept"] = True
        page.locator("#taskCards [data-task=plan_fit]").click()
        page.wait_for_selector(".sf-pop", timeout=120000)  # 「같은 파일 고르기」(spec_작업 ② §1 「같은 파일은 묻고 연다」 — 2026-11-18: 전에는 묻지 않고 새 작업)
        sf = page.evaluate("""() => ({ rows: [...document.querySelectorAll('.sf-pop .sf-row')].map((r) => [r.dataset.work, [...r.querySelectorAll('.sf-acts [data-sf]')].map((b) => b.dataset.sf),
            (r.querySelector('.sf-why') || {}).textContent || '']), project: (document.getElementById('sfProject') || {}).value, busy: hf.busy, id: state.id })""")
        check("같은 파일로 다른 TASK(이관의 사업계획서)를 하던 작업 → 「같은 파일 고르기」(그 줄은 「그대로 열기」 만 · 프로젝트 칸 · 목록 줄은 「고르세요」 · 아직 안 열림)",
              len(sf["rows"]) == 1 and sf["rows"][0][0] == pid and sf["rows"][0][1] == ["open"] and "다른 TASK" in sf["rows"][0][2] and sf["project"] == page.evaluate("() => hfNorm(hf.project, 60)")
              and "고르세요" in sf["busy"] and sf["id"] is None, sf)
        page.locator('.sf-pop [data-sf="new"]').click()
        page.wait_for_function("() => state.id && state.task.job === 'plan_fit' && document.getElementById('panel').dataset.tool === 'Div'", timeout=120000)
        fid = page.evaluate("() => state.id")
        t = page.evaluate("() => [state.task, document.getElementById('toast').hidden ? '' : document.getElementById('toast').textContent]")
        check("「새 작업으로 시작」 → 새 작업 · 알림 · 앞 작업은 그대로",
              fid != pid and t[0]["file"] == "plan" and "새 작업으로 열었습니다" in t[1] and next(x for x in works() if x["id"] == pid)["task"]["job"] == "plan_to_report", t)
        check("안 쓴 문서는 목록에 남음", page.evaluate("() => hf.files.map((f) => f.name)") == [SMALL])
        go_home(page)
        L = page.evaluate(LIST)
        check("시작 화면 — 남은 하나가 저절로 목적 문서", [r["name"] for r in L["rows"]] == [SMALL] and L["rows"][0]["on"] and "목적 문서" in L["rows"][0]["tag"] and L["plain"], L)
        page.locator("#homeFiles .hf-clear").click()
        check("「비우기」 → 목록 없음", not page.evaluate(LIST)["vis"])
        pick(page, [SMALL])
        L = page.evaluate(LIST)
        check("처음부터 파일 하나만 올림 — 목적 문서 자동 선택 · TASK 활성", len(L["rows"]) == 1 and L["rows"][0]["on"] and not L["disabled"]["plan_fit"], L)
        page.locator("#homeFiles .hf-row.on .hf-alias input").fill("남길 약칭")
        page.evaluate(DROP, [[[b64(sample(PLAN)), PLAN]], "#empty"])
        page.locator("#homeFiles .hf-row").nth(1).locator("input[type=radio]").check()
        page.locator("#homeFiles .hf-row").nth(1).locator(".hf-del").click()
        L = page.evaluate(LIST)
        check("선택한 파일 삭제 — 남은 하나 자동 선택 · 남은 약칭 유지 · TASK 활성", len(L["rows"]) == 1 and L["rows"][0]["on"] and L["rows"][0]["alias"] == "남길 약칭" and not L["disabled"]["plan_fit"], L)
        # ---- 5. 이름 없이 시작 → 임시 프로젝트(spec_작업 ② §17 「임시 프로젝트」, 2026-11-18) — 같은 파일 고르기 창의 칸도 「비우면 임시 이름」 · 「새 작업으로 시작」 → 「임시 프로젝트 N」 · 알림 · 보이는 이름에 안 붙음
        page.locator("#homeFiles [data-hf-focus=project]").fill("")
        page.locator("#taskCards [data-task=plan_fit]").click()
        page.wait_for_selector(".sf-pop", timeout=120000)   # 기술수요조사서.hwpx 로 하던 작업(3 의 이관)이 있다
        check("같은 파일 고르기 창의 프로젝트 칸 — 비어 있음 · 「비우면 임시 이름」", page.locator("#sfProject").input_value() == "" and page.locator("#sfProject").get_attribute("placeholder") == "비우면 임시 이름")
        page.locator('.sf-pop [data-sf="new"]').click()
        page.wait_for_function("() => state.id && state.task.job === 'plan_fit' && /^임시 프로젝트 [0-9]+$/.test(state.task.project || '') && !hf.busy", timeout=120000)
        tid = page.evaluate("() => state.id")
        tw = next(x for x in works() if x["id"] == tid)
        toast_text = page.evaluate("() => document.getElementById('toast').textContent")
        check("이름 없이 시작 → 임시 프로젝트 · 라운드 1 · 알림 · 보이는 이름에 임시 이름 없음 · 프로젝트 칸 뒤 「임시 이름」",
              tw["task"]["project"].startswith("임시 프로젝트 ") and tw["task"].get("round") == 1 and "임시 이름" in toast_text and "임시" not in tw["name"]
              and page.locator("#divBox .dv-task-field .dv-tag.is-temp").count() == 1, (tw, toast_text))
        go_home(page)
        check("시작한 문서는 목록에서 빠짐 → 목록 없음", not page.evaluate(LIST)["vis"])
        page.screenshot(path=str(OUT / "4_home.png"))
        bad = [e for e in errors if "409" not in e]   # 409 = LLM 꺼짐(noLlm) — 기대한 것
        check("콘솔 오류 0(기대한 409 빼고)", not bad, bad[:5])
        br.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
print(f"\n{'FAIL' if fails else 'OK'} — 실패 {len(fails)}: {fails}" if fails else "\nOK — 모두 통과", flush=True)
sys.exit(1 if fails else 0)

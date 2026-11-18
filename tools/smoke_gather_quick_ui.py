"""취합 간단 모드(spec_취합 ② §8 — gather_quick.js) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 흉내 없이 진짜 끝점으로 끝까지.

    python -X utf8 tools/smoke_gather_quick_ui.py <그림·임시 폴더> [--port 18392]

자료(gather_data — 저장소 안 자료만): 목적 문서 = 빈 계획서 양식에 값(인텍 · 가나대 · 다라연 — 2단계 2년)을 반영한 프레임(반영 기록 없이 **새로** 올림 — 구조 확인이 「반영됨」 을 적어야 한다),
기관 문서 = 그 프레임을 고친 것 — 「가나대_작성본」(이름으로 가나대 · 제 자리 + 공통 자리) · 「기관2_작성본」(이름에 기관 없음 → 추천 = 다라연) · 「빈_사본」(아무것도 안 씀 → 기관을 못 정해 건너뜀).
보는 것(2026-11-13 — 옛 고르기 패널 #quickPanel 을 시작 화면의 문서 목록 #homeFiles 로 합침: spec_작업 ② §15-1): 카드 누름 → 파일 고르기가 여러 개 · 둘 이상이면 문서 목록(목적 문서 기본 선택 없음 ·
docx 도 목록에는 듦 — 「TASK 없이 열기만」) · 목적 문서를 고르기 전에는 TASK 비활성 · 문서별 약칭 미리 보기·저장 · 「자동 진행」 켜고 카드 → 확인 창(취소면 아무것도 안 올림) ·
시작 → 목적 문서가 열리고(보이는 이름 뒤에 「(별칭)」) 간단 모드 줄이 끝까지 「끝남」 · 기관 문서마다 반영할 기관과 정한 길 · 취합본에 그 글(공통 자리는 앞 문서) · 구조 확인(adopted) · 기관 문서 줄의 「자동(파일 이름)」 ·
줄을 누르면 2열 「기관 작성 내용」 · 「자동 진행」 끄고 카드 = 올리고 등록만(문서·기준본 그대로 · 자동 지정 없음 · 확인 창 없음) · 좁은 창에서 목록이 넘치지 않음. LLM 은 꺼져 있어 검토는 「못 함」 으로 남고 넣기는 이어 간다."""
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
ap.add_argument("--port", type=int, default=18392)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)

sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
import gather_data as GD   # noqa: E402 — 문서만 다룬다(서버 모듈을 이 프로세스에 띄우지 않는다)
from app.hwpx_doc import HwpxDoc   # noqa: E402

LEAD, J1, J2, MARK = GD.LEAD, GD.J1, GD.J2, "(간단 모드)"
FRAME = GD.base()["side"]["bytes"]


def edited(fn):
    doc = HwpxDoc(FRAME)
    doc.blocks()
    fn(doc)
    return GD.save(doc)


W = {"a_own": f"o {J1} 1차년도 개발 목표{MARK}", "a_common": f"o {J1}가 쓴 필요성{MARK}", "b_own": f"o {J2} 1차년도 개발 목표{MARK}", "b_common": f"o {J2}가 쓴 필요성{MARK}"}
A = edited(lambda d: (d.set_text(GD.nxt(d, GD.para(d, f"[공동연구개발기관1({J1})]", 0)), " " + W["a_own"]), d.set_text(GD.nxt(d, GD.para(d, "□ 필요성")), " " + W["a_common"])))
B = edited(lambda d: (d.set_text(GD.nxt(d, GD.para(d, f"[공동연구개발기관2({J2})]", 0)), " " + W["b_own"]), d.set_text(GD.nxt(d, GD.para(d, "□ 필요성")), " " + W["b_common"])))
FILES = [("취합본_프레임.hwpx", FRAME), (f"{J1}_작성본.hwpx", A), ("기관2_작성본.hwpx", B), ("빈_사본.hwpx", edited(lambda d: None))]

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


def buf(name, data):
    return {"name": name, "mimeType": "application/octet-stream", "buffer": data}


PANEL = """() => { const p = document.getElementById('homeFiles'); if (!p || p.hidden) return null; const vis = (e) => !!e && !e.hidden && e.getClientRects().length > 0;
  return { vis: vis(p), title: p.querySelector('h3').textContent, cap: p.querySelector('.hf-cap').textContent, has: document.getElementById('drop').classList.contains('has-files'),
    rows: [...p.querySelectorAll('.hf-row')].map((r) => ({ name: r.querySelector('.hf-name').textContent, tag: r.querySelector('.hf-tag').textContent, on: r.querySelector('input').checked })),
    auto: p.querySelector('[data-hf-focus=auto]').checked, llm: p.querySelector('[data-hf-focus=llm]').checked, llmOff: p.querySelector('[data-hf-focus=llm]').disabled,
    alias: (p.querySelector('.hf-row.on .hf-shown') || {}).textContent || '', go: document.querySelector('#taskCards [data-task=plan_merge] .task-card-go').textContent.trim(),
    taskOff: document.querySelector('#taskCards [data-task=plan_merge]').disabled,
    status: (p.querySelector('.hf-status') || {}).textContent || '' }; }"""
QUICK = """() => { const q = document.querySelector('#gatherFlow .gt-quick'); if (!q || q.hidden) return null;
  return { kind: q.dataset.kind, msg: q.querySelector('.gt-quick-msg').textContent, btns: [...q.querySelectorAll('.gt-quick-head button.btn')].map((b) => b.textContent),
    rows: [...q.querySelectorAll('.gt-quick-row')].map((b) => ({ pid: b.dataset.quickRow || '', name: b.querySelector('.gt-quick-name').textContent, org: b.querySelector('.gt-quick-org').textContent,
      res: b.querySelector('.gt-quick-res').textContent, off: b.disabled })) }; }"""
DROP = """([files, sel]) => { const dt = new DataTransfer(); for (const [b64, name] of files) { const bin = atob(b64), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); dt.items.add(new File([u], name)); }
  const t = document.querySelector(sel), ev = (n) => new DragEvent(n, { bubbles: true, cancelable: true, dataTransfer: dt }); t.dispatchEvent(ev('dragover')); t.dispatchEvent(ev('drop')); }"""
b64 = lambda data: base64.b64encode(data).decode()

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
        page.wait_for_selector("#taskCards [data-task=plan_merge]")
        card = page.evaluate("() => { const b = document.querySelector('#taskCards [data-task=plan_merge]'); return { go: b.querySelector('.task-card-go').textContent, title: b.title }; }")
        check("카드 글 — 「문서 여러 개 올려 시작」 · 도움말에 간단 모드·세부 작업 모드", card["go"].startswith("문서 여러 개 올려 시작") and "간단 모드" in card["title"] and "세부 작업 모드" in card["title"], card)

        # ---- 1. 카드 → 여러 개 고르기 → 시작 화면의 문서 목록(spec_작업 ② §15-1)
        toast_text = "() => document.getElementById('toast').hidden ? '' : document.getElementById('toast').textContent"
        with page.expect_file_chooser() as fc:
            page.locator("#taskCards [data-task=plan_merge]").click()
        check("카드 누름 → 파일 고르기가 여러 개(hwp·hwpx)", fc.value.is_multiple() and fc.value.element.evaluate("(e) => e.accept") == ".hwp,.hwpx")
        fc.value.set_files([buf(n, d) for n, d in FILES])
        page.wait_for_selector("#homeFiles .hf-row")
        P = page.evaluate(PANEL)
        check("둘 이상 → 파일 카드 넷 · 목적 문서 기본 선택 없음 · 자동 진행 기본 끔 · 목적 문서를 고르기 전에는 TASK 비활성",
              P["vis"] and P["has"] and [r["name"] for r in P["rows"]] == [n for n, _ in FILES] and not any(r["on"] for r in P["rows"]) and not P["auto"] and P["llmOff"]
              and "목적 문서(내용을 받는 문서)를 하나 고르세요" in P["cap"] and P["taskOff"] and P["go"].startswith("목적 문서를 선택하세요")
              and page.evaluate("() => state.id") is None and not page.evaluate("() => !!document.querySelector('dialog[open]')"), P)
        n_works = len(works())
        page.evaluate(DROP, [[[b64(b"PK-not-docx"), "메모.docx"]], "#homeFiles"])
        page.wait_for_timeout(300)
        P = page.evaluate(PANEL)
        check("목록에 docx 를 놓으면 듦(「TASK 없이 열기 · 서식 복사」) — 서버에는 아직 안 올림", len(P["rows"]) == 5 and "TASK 없이 열기 · 서식 복사" in P["rows"][4]["tag"] and len(works()) == n_works, P["rows"])
        page.locator("#homeFiles .hf-row").nth(4).locator(".hf-del").click()
        P = page.evaluate(PANEL)
        check("빼기 → 카드 넷 · 목적 문서가 없어 TASK 비활성 유지 · 아직 안 올림", len(P["rows"]) == 4 and P["taskOff"] and len(works()) == n_works and page.evaluate("() => state.id") is None, P)
        page.locator("#homeFiles .hf-row").nth(0).locator("input[type=radio]").check()
        page.locator("#homeFiles .hf-row.on .hf-alias input").fill("1차 취합")
        page.locator("#homeFiles .hf-row").nth(1).locator(".hf-alias input").fill("공동 1")
        P = page.evaluate(PANEL)
        check("목적 문서를 고름 → 꼬리표(목적 문서 · 원본 문서 셋) · 별칭 미리 보기", [r["tag"] for r in P["rows"]] == ["목적 문서", "원본 문서", "원본 문서", "원본 문서"]
              and P["rows"][0]["on"] and not P["taskOff"] and "원본 문서 3개" in P["cap"] and P["alias"] == "보일 이름 취합본_프레임(1차 취합).hwpx", P)
        page.locator("#homeFiles [data-hf-focus=auto]").check()
        P = page.evaluate(PANEL)
        check("자동 진행 켬 → LLM 검토 고를 수 있음(기본 켬)", P["auto"] and P["llm"] and not P["llmOff"], P)
        page.screenshot(path=str(OUT / "1_panel.png"))
        page.set_viewport_size({"width": 400, "height": 900})
        page.wait_for_timeout(200)
        fit = page.evaluate("() => { const e = document.getElementById('empty'), p = document.getElementById('homeFiles'), w = e.clientWidth; return e.scrollWidth <= w + 1 && [...p.querySelectorAll('*')].every((x) => x.getBoundingClientRect().right <= w + 1); }")
        check("좁은 창(400px) — 목록이 가로로 넘치지 않음", fit)
        page.locator("#drop").screenshot(path=str(OUT / "1_panel_narrow.png"))
        page.set_viewport_size({"width": 1400, "height": 960})

        # ---- 2. 확인 창 없이 바로 끝까지(2026-11-18 사용자 「이런 알람좀 주지마」 — 전에는 차례를 적은 확인 창 · 취소면 아무것도 안 올림)
        nd0 = len(dialogs)
        answer["accept"] = True
        t0 = time.time()
        page.locator("#taskCards [data-task=plan_merge]").click()
        page.wait_for_function("() => typeof gqRun !== 'undefined' && !!gqRun && !!gqRun.plan && state.id === gqRun.plan", timeout=180000)
        tid = page.evaluate("() => gqRun.plan")
        check("자동 진행 — 확인 창 없이 바로 시작", len(dialogs) == nd0, dialogs[nd0:])
        page.wait_for_function("() => (state.name || '').endsWith('(1차 취합).hwpx')", timeout=30000)
        check("시작 → 목적 문서가 열림(사업계획서 취합 · 취합본) · 이름 뒤에 「(별칭)」 · 시작 화면 목록은 빔(올린 문서는 빠짐)",
              page.evaluate("() => state.task.job === 'plan_merge' && state.task.file === 'plan' && document.getElementById('homeFiles').hidden && hf.files.length === 0 && state.name === '취합본_프레임(1차 취합).hwpx'"),
              page.evaluate("() => [state.task, state.name, hf.files.length]"))
        page.wait_for_selector("#gatherFlow .gt-quick:not([hidden])", timeout=120000)
        q = page.evaluate(QUICK)
        check("도는 동안 — 간단 모드 줄(동그라미 · 지금 하는 일 · 「멈춤」)", q and q["kind"] == "run" and "자동 취합" in q["msg"] and "멈춤" in q["btns"], q)
        page.wait_for_function("() => !!gqRun && !!gqRun.end && !gqRun.busy", timeout=1500000, polling=1000)
        took = round(time.time() - t0, 1)
        page.wait_for_timeout(500)
        end = page.evaluate("() => gqRun.end")
        q = page.evaluate(QUICK)
        print(f"TIME 간단 모드 끝까지 {took}초 — {end}", flush=True)
        page.screenshot(path=str(OUT / "2_done.png"))
        check("끝남 — 간단 모드 줄 「끝남」 · 「닫기」", end["ok"] and q["kind"] == "done" and q["msg"].startswith("끝남") and q["btns"] == ["닫기"], (end, q))
        rows = {r["name"]: r for r in q["rows"]}
        source = next((w for w in works() if w["id"] == rows[f"{J1}_작성본.hwpx"]["pid"]), {})
        check("기관 문서의 약칭도 저장 — 목적 문서와 독립", source.get("alias") == "공동 1" and source.get("name") == f"{J1}_작성본(공동 1).hwpx", source)
        check("문서마다 한 줄 — 가나대(파일 이름) 넣음 · 다라연(추천) 넣음 · 빈 사본은 건너뜀(기관을 못 정함)",
              set(rows) == {n for n, _ in FILES[1:]} and rows[f"{J1}_작성본.hwpx"]["org"] == f"{J1} (파일 이름)" and rows[f"{J1}_작성본.hwpx"]["res"].startswith("넣음")
              and rows["기관2_작성본.hwpx"]["org"] == f"{J2} (추천)" and rows["기관2_작성본.hwpx"]["res"].startswith("넣음") and "겹침 1" in rows["기관2_작성본.hwpx"]["res"]
              and rows["빈_사본.hwpx"]["org"] == "미지정" and "건너뜀" in rows["빈_사본.hwpx"]["res"] and "LLM 검토 못 함" in rows[f"{J1}_작성본.hwpx"]["res"], q["rows"])
        gv = requests.get(f"{base}/api/docs/{tid}/gather", timeout=120).json()
        by = {p["name"]: (p["orgs"], p["orgsBy"]) for p in gv["parts"]}
        check("서버 — 기관 문서 셋(올린 차례) · 반영할 기관과 정한 길(orgsBy) · 기준본 있음", [p["name"] for p in gv["parts"]] == [n for n, _ in FILES[1:]] and gv["frame"] and gv["frame"]["stale"] is False
              and by[f"{J1}_작성본.hwpx"] == ([J1], "name") and by["기관2_작성본.hwpx"] == ([J2], "recommend") and by["빈_사본.hwpx"] == ([], None), (by, gv["frame"]))
        dv = requests.get(f"{base}/api/docs/{tid}/divisions", timeout=60).json()
        check("구조 확인 — 값은 문서에서 읽음(인텍 · 가나대 · 다라연) · 반영 기록 adopted · 문서 구조는 안 바뀜(편집은 기관 문서 둘의 반영뿐)",
              (dv.get("applied") or {}).get("adopted") is True and dv["applied"]["values"]["orgs"]["joint"] == [J1, J2] and dv["applied"]["values"]["orgs"]["lead"] == LEAD and dv["applied"]["rev"] == 0, dv.get("applied"))
        body = page.evaluate("() => document.getElementById('doc').innerText")
        check("취합본에 그 글 — 두 기관의 제 자리 · 공통 자리는 앞 문서의 것만(뒤 것은 겹침)", W["a_own"] in body and W["b_own"] in body and W["a_common"] in body and W["b_common"] not in body,
              [k for k, v in W.items() if v in body])
        st1 = page.evaluate("() => [...document.querySelectorAll('#gatherStage ol.dv-flow-steps > li')].map((li) => li.textContent)")
        check("1단계 ① 줄 — 「구조가 이미 값에 맞음(확인함)」", any("구조가 이미 값에 맞음(확인함)" in t for t in st1), st1)
        opts = page.evaluate("() => [...document.querySelectorAll('#gatherParts .gt-part select')].map((s) => s.options[s.selectedIndex].textContent)")
        check("기관 문서 줄(세부 작업 모드) — 고른 기관 옵션에 「자동(파일 이름)」·「자동(추천)」", any("자동(파일 이름)" in o for o in opts) and any("자동(추천)" in o for o in opts), opts)
        page.click(f"#gatherFlow .gt-quick-row[data-quick-row='{rows[f'{J1}_작성본.hwpx']['pid']}']")
        page.wait_for_function("() => document.querySelector('#headsDlg[data-kind=gather]') && !document.getElementById('headsDlg').hidden", timeout=60000)
        check("결과 줄을 누름 → 2열 「기관 작성 내용」", page.evaluate("() => gt().listPart") == rows[f"{J1}_작성본.hwpx"]["pid"])
        page.locator("#panel").screenshot(path=str(OUT / "2_panel.png"))
        replan = [requests.post(f"{base}/api/docs/{tid}/gather/parts/{p['work']}/plan", timeout=120).json().get("todo") for p in gv["parts"] if p["orgs"]]
        check("다시 계획하면 넣을 것 0(두 번 안 넣음)", replan == [0, 0], replan)

        # ---- 3. 「자동 진행」 끄고 카드 — 올리고 등록만(문서·기준본 그대로 · 자동 지정 없음 · 확인 창 없음)
        page.locator("#homeLink").click()
        page.wait_for_function("() => document.body.classList.contains('no-doc')")
        page.evaluate(DROP, [[[b64(FRAME), "취합본_세부.hwpx"], [b64(A), f"{J1}_세부.hwpx"]], "#taskCards [data-task=plan_merge]"])
        page.wait_for_selector("#homeFiles .hf-row")
        page.locator("#homeFiles .hf-row").nth(0).locator("input[type=radio]").check()
        page.locator("#homeFiles [data-hf-focus=auto]").uncheck()
        nd = len(dialogs)
        page.locator("#taskCards [data-task=plan_merge]").click()
        page.wait_for_function("() => !!gqRun && gqRun.uploadOnly && !!gqRun.end && !gqRun.busy", timeout=600000, polling=500)
        did = page.evaluate("() => gqRun.plan")
        gv2 = requests.get(f"{base}/api/docs/{did}/gather", timeout=120).json()
        q = page.evaluate(QUICK)
        check("자동 진행 끔 — 확인 창 없음 · 새 취합본 열림 · 기관 문서 등록만(기관 미지정 · 기준본 없음 · 문서 그대로)",
              len(dialogs) == nd and did != tid and page.evaluate("() => state.id") == did and [p["name"] for p in gv2["parts"]] == [f"{J1}_세부.hwpx"] and gv2["parts"][0]["orgs"] == []
              and gv2["frame"] is None and requests.get(f"{base}/api/docs/{did}/divisions", timeout=60).json().get("applied") is None and q and q["kind"] == "done" and "올리고 등록" in q["msg"], (gv2, q))
        page.screenshot(path=str(OUT / "3_detail.png"))
        bad = [e for e in errors if "409" not in e]   # 409 = LLM 꺼짐(noLlm) · 분석 다시(staleHeadings) — 기대한 것
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

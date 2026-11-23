"""개요 줄의 헤딩 고치기(spec_hwpx_웹편집 ② §8-12 — app/static/outline_tune.js · app/outline_tune.py · 2026-11-24 전의 이름 「레터 고치기」) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

연구개발계획서 양식(1·2단계를 끝점으로 — 가지 T2 「□›o›-›·」: p970 □ › p972 o › p974 - › p975 ⋅ · p977 o › p979 - › p980 ⋅ · L3 「-」 줄 5개 · 대표 p974).
- 커서가 없던 줄의 레터를 누름 = 그냥 커서(창 없음) · 커서가 든 줄의 레터 글자를 누름 → 그 줄 아래 창(#olTune · 모달 아님 · 창 안 · 폭 ≤ 376) · 레터에 점선 밑줄(CSS 하이라이트).
- 처음: 범위 카드 셋 · 값이 안 바뀌어 「적용」 꺼짐 · 나누기는 켜져 있어도 저절로 고르지 않음. 「레터 뒤 빈칸 +」 → 「이 문단만 수정」 켜짐 · 「T2 L3 서식 전체 변경」 = 5줄 가운데 5줄 · 「새 템플릿으로 나누기 · T2L3a」.
- 「레터 고르기」 → 「▪」: 레터가 달라져 「이 문단만」 은 꺼지고(까닭 「다른 템플릿」) 고른 범위가 새 템플릿 쪽으로 옮겨 간다.
- 「서식 전체 변경」 → 적용: L3 줄 5개가 모두 「▪」 · 창은 열린 채 「되돌리기」 · 실행 취소 1 → 「되돌리기」 = 문서가 그 앞으로(실행 취소 0).
- 「앞 여백 +」 두 번 → 「이 문단만」 적용: 그 줄만 바뀜 → 값 없이 「서식 전체 변경」 이 켜져 있고(이미 달라진 줄) 적용하면 5줄이 같은 여백.
- 「새 템플릿으로 나누기」: 「▪」 → 적용 → 여백 표시 「T2L3a L3」.
- 오른쪽 단추 메뉴 「헤딩 고치기…」 → 창 · Esc = 닫고 커서가 그 줄로 · 밖을 누르면 닫힘.
- 빈칸 「칸 | mm」(mm 를 적으면 가장 가까운 칸 수) · 2번째 줄 「레터」 · 나누기의 레벨 범위(L1 부터 L3 까지 — L4 줄은 T2 에 남음) → 적용.
- 실행 취소를 끝까지 → 내려받은 파일 = 원본 바이트 · 콘솔 오류 없음.

    python -X utf8 tools/smoke_outline_tune_ui.py <출력 폴더> [--port 18496]
"""
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
ap.add_argument("--port", type=int, default=18496)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_TASKS": str(tmp / "tasks.json"),
       "NFM_REQS": str(tmp / "reqs.json"), "NFM_AGENT_NOTES": str(tmp / "notes.json"), "NFM_TOOL_NAMES": str(tmp / "names.json"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
L3 = ["p974", "p979", "p988", "p994", "p1018"]


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


def run_stage(doc, stage):
    r = requests.post(f"{base}/api/docs/{doc}/headings", json={"stage": stage, "llm": False}, timeout=30)
    assert r.status_code == 202, r.text
    end = time.time() + 300
    while time.time() < end:
        v = requests.get(f"{base}/api/docs/{doc}/headings", timeout=30).json()
        if not v.get("job") or v["job"].get("status") != "running":
            return v
        time.sleep(0.4)
    raise SystemExit("단계가 안 끝남")


BOX = """() => { const b = document.getElementById('olTune'); if (!b) return null; const r = b.getBoundingClientRect();
  const cards = [...b.querySelectorAll('.olt-card')].map((c) => ({ scope: c.dataset.scope, t: c.querySelector('.olt-ct').textContent, n: c.querySelector('.olt-cn').textContent, on: c.classList.contains('on'), off: c.classList.contains('off') }));
  const steps = Object.fromEntries([...b.querySelectorAll('.olt-step')].map((s) => [s.dataset.key, s.querySelector('.olt-val').value]));
  const was = Object.fromEntries([...b.querySelectorAll('.olt-step')].map((s) => [s.dataset.key, s.querySelector('.olt-was').textContent]));
  const l2 = [...b.querySelectorAll('.olt-l2b')].map((x) => ({ k: x.dataset.l2, on: x.classList.contains('on'), cur: x.classList.contains('cur') }));
  const sp = b.querySelector('.olt-split');
  const split = sp ? { shown: !sp.hidden, sum: sp.querySelector('.olt-ssum').textContent, from: sp.querySelector('.olt-from').value, to: sp.querySelector('.olt-to').value,
    lvs: [...sp.querySelectorAll('.olt-lv')].map((x) => ({ k: x.dataset.level, in: x.classList.contains('in'), me: x.classList.contains('me'), c: x.querySelector('.olt-lv-c').textContent })) } : null;
  return { head: b.querySelector('.olt-head').textContent, cards, steps, was, l2, split, go: { off: b.querySelector('.olt-go').disabled, text: b.querySelector('.olt-go').textContent },
    undo: !b.querySelector('.olt-undo').hidden, msg: b.querySelector('.olt-msg').textContent, pal: !b.querySelector('.olt-pal').hidden, cur: b.querySelector('.olt-cur').textContent,
    demo: [...b.querySelectorAll('.olt-dr')].map((x) => x.textContent), help: !!b.querySelector('.olt-head .panel-help'),
    modal: b.tagName === 'DIALOG', inView: r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight, w: Math.round(r.width), h: Math.round(r.height) }; }"""
LINES = """(ids) => ids.map((id) => { const p = paraEl(id), ol = outlineLine(p), f = (state.byId.get(id) || {}).format || {};
  return { id, text: readText(p).slice(0, 8), tpl: ol ? String(ol.tpl) : null, level: ol ? ol.level : null, left: f.indentLeftMm || 0, first: f.firstLineMm || 0 }; })"""
STATE = "() => ({ undo: state.undo, box: !!document.getElementById('olTune'), busy: state.busy, toast: document.getElementById('toast').hidden ? '' : document.getElementById('toast').textContent })"
PENDING = "확인하는 중…"


def focus(page, pid, at="end"):
    page.evaluate("([id, at]) => { const p = paraEl(id); p.scrollIntoView({ block: 'center' }); focusAt({ id, offset: at === 'end' ? readText(p).length : at }); }", [pid, at])
    page.wait_for_timeout(200)


def letter_xy(page, pid):
    return page.evaluate("(id) => { const r = [...oltLetterRange(paraEl(id)).getClientRects()].sort((a, b) => b.width - a.width)[0]; return [r.left + r.width / 2, r.top + r.height / 2]; }", pid)


def click_letter(page, pid):
    x, y = letter_xy(page, pid)
    page.mouse.click(x, y)
    page.wait_for_timeout(300)


def ready(page):
    page.wait_for_function("(w) => { const b = document.getElementById('olTune'); return !!b && !state.busy && !b.dataset.stale && ![...b.querySelectorAll('.olt-cn')].some((x) => x.textContent === w); }", arg=PENDING, timeout=30000)
    page.wait_for_timeout(250)
    return page.evaluate(BOX)


def card(box, scope):
    return next(c for c in box["cards"] if c["scope"] == scope)


def front(x):
    return x["left"] + max(x["first"], 0)


def main():
    wait_server()
    r = requests.post(base + "/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}, timeout=120)
    assert r.status_code == 200, r.text
    doc = r.json()["docId"]
    run_stage(doc, 1)
    run_stage(doc, 2)
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1500, "height": 950}, device_scale_factor=2)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/#w={doc}")
        page.wait_for_selector("#doc .para", timeout=60000)
        page.wait_for_function("() => !!heads.outline && !!heads.outline.lines['p979']", timeout=30000)
        page.wait_for_timeout(600)

        # 1. 커서가 없던 줄의 레터 = 그냥 커서 · 커서가 든 줄의 레터 글자 = 창
        focus(page, "p972")
        click_letter(page, "p979")
        st = page.evaluate(STATE)
        check("커서가 없던 줄의 레터를 누름 = 창이 안 뜬다(그냥 커서)", not st["box"], st)
        hint = page.evaluate("() => !!(window.CSS && CSS.highlights && CSS.highlights.has('nfm-olt-letter'))")
        check("커서가 든 개요 줄의 레터에 점선 밑줄(CSS 하이라이트)", hint, hint)
        click_letter(page, "p979")
        page.wait_for_selector("#olTune", timeout=15000)
        box = ready(page)
        check("커서가 든 줄의 레터를 누름 → 그 줄 아래 창 「헤딩 고치기」(모달 아님 · 창 안 · 폭 ≤ 376)",
              box and not box["modal"] and box["inView"] and box["w"] <= 376 and box["head"].startswith("헤딩 고치기") and "T2 L3" in box["head"] and box["help"], box)
        check("처음: 카드 셋 · 값이 안 바뀌어 「적용」 꺼짐 · 나누기는 켜져 있어도 고르지 않음 · 레터 후보는 접혀 있음",
              [c["scope"] for c in box["cards"]] == ["line", "level", "split"] and box["go"]["off"] and not box["pal"] and card(box, "line")["off"] and card(box, "level")["off"]
              and not card(box, "split")["off"] and not any(c["on"] for c in box["cards"]) and not box["undo"] and not box["split"]["shown"], box)
        check("2번째 줄 — 글 시작 · 레터 · 앞 여백 · 지금 자리(앞 여백)에 「지금」",
              [x["k"] for x in box["l2"]] == ["text", "letter", "front"] and next(x for x in box["l2"] if x["k"] == "front")["cur"], box["l2"])
        check("자리 값 = 앞 여백 0.0mm · 레터 앞 빈칸 4칸 · 레터 뒤 빈칸 1칸", box["steps"] == {"front": "0.0mm", "lead": "4칸", "gap": "1칸"}, box["steps"])
        page.screenshot(path=str(OUT / "1_open.png"))

        # 2. 레터 뒤 빈칸 + → 범위 셋
        page.click('#olTune .olt-step[data-key="gap"] .olt-pm:last-of-type')
        box = ready(page)
        lv, sp, ln = card(box, "level"), card(box, "split"), card(box, "line")
        check("「레터 뒤 빈칸 +」 → 「이 문단만 수정」 이 켜지고 고른 범위", ln["on"] and not ln["off"] and box["steps"]["gap"] == "2칸" and not box["go"]["off"], box)
        check("「T2 L3 서식 전체 변경」 = 5줄 가운데 5줄 바뀜", not lv["off"] and lv["t"] == "T2 L3 서식 전체 변경" and "5줄 가운데 5줄" in lv["n"], lv)
        check("「새 템플릿으로 나누기 · T2L3a」 — 이 줄과 아래 1줄(2줄)", not sp["off"] and sp["t"] == "새 템플릿으로 나누기 · T2L3a" and "2줄이 T2L3a 로" in sp["n"], sp)

        # 3. 레터 고르기 → ▪ : 이 문단만은 못 한다
        page.click("#olTune .olt-pick")
        page.click('#olTune .olt-chip[data-letter="▪"]')
        box = ready(page)
        ln, sp = card(box, "line"), card(box, "split")
        check("레터 「▪」 → 「이 문단만」 은 꺼지고(까닭 「다른 템플릿」) 범위가 새 템플릿 쪽으로", box["pal"] and ln["off"] and "다른 템플릿" in ln["n"] and sp["on"] and "▪" in box["cur"], box)
        check("견본 「바꾼 뒤」 줄에 새 레터", "▪" in box["demo"][1] and "-" in box["demo"][0], box["demo"])
        page.screenshot(path=str(OUT / "2_letter.png"))

        # 4. 서식 전체 변경 → 적용 → 되돌리기
        page.click('#olTune .olt-card[data-scope="level"]')
        box = ready(page)
        check("「서식 전체 변경」 을 고름 → 「적용(5줄)」", card(box, "level")["on"] and box["go"]["text"] == "적용(5줄)", box)
        page.click("#olTune .olt-go")
        page.wait_for_function("() => !state.busy && state.undo === 1", timeout=30000)
        page.wait_for_function("() => readText(paraEl('p974')).trimStart().startsWith('▪') && document.querySelector('#olTune .olt-head').textContent.includes('「▪」')", timeout=30000)  # 떨어진 줄 여럿 = 문서를 다시 읽어 그린다
        box = ready(page)
        rows = page.evaluate(LINES, L3)
        check("적용 → L3 줄 5개가 모두 「▪」 + 뒤 빈칸 2칸", all(x["text"].lstrip()[:1] == "▪" and len(x["text"].lstrip()[1:3].strip()) == 0 for x in rows), rows)
        check("창은 열린 채 「되돌리기」 · 알림 글", box["undo"] and "5개" in box["msg"] and "「▪」" in box["head"], box)
        page.screenshot(path=str(OUT / "3_applied.png"))
        page.click("#olTune .olt-undo")
        page.wait_for_function("() => !state.busy && state.undo === 0", timeout=30000)
        box = ready(page)
        rows = page.evaluate(LINES, L3)
        check("「되돌리기」 → 문서가 그 앞으로(「-」 · 실행 취소 0) · 창은 그 줄의 값으로", all(x["text"].startswith("    - ") for x in rows) and not box["undo"] and "「-」" in box["head"], [rows, box["head"]])

        # 5. 이 문단만(앞 여백) → 값 없이 서식 전체 변경
        for _ in range(2):
            page.click('#olTune .olt-step[data-key="front"] .olt-pm:last-of-type')
        box = ready(page)
        check("「앞 여백 +」 두 번 = 1.0mm · 「이 문단만」", box["steps"]["front"] == "1.0mm" and card(box, "line")["on"], box)
        page.click("#olTune .olt-go")
        page.wait_for_function("() => !state.busy && state.undo === 1", timeout=30000)
        box = ready(page)
        rows = {x["id"]: x for x in page.evaluate(LINES, L3)}
        check("이 문단만 적용 → 그 줄만 앞 여백 1mm · 다른 줄 그대로", abs(front(rows["p979"]) - 1.0) < 0.06 and all(abs(front(rows[i])) < 0.01 for i in L3 if i != "p979"), rows)
        lv = card(box, "level")
        check("값을 안 바꿔도 「서식 전체 변경」 이 켜져 있다(이미 달라진 줄) · 「이 문단만」 은 꺼짐", not lv["off"] and "4줄 바뀜" in lv["n"] and card(box, "line")["off"], box)
        page.click('#olTune .olt-card[data-scope="level"]')
        page.wait_for_timeout(150)
        page.click("#olTune .olt-go")
        page.wait_for_function("() => !state.busy && state.undo === 2", timeout=30000)
        page.wait_for_function("() => Math.abs(((state.byId.get('p974') || {}).format || {}).indentLeftMm - 1) < 0.06", timeout=30000)
        ready(page)
        rows = page.evaluate(LINES, L3)
        check("값 없이 서식 전체 변경 → 5줄이 같은 앞 여백", len({round(front(x), 1) for x in rows}) == 1 and abs(front(rows[0]) - 1.0) < 0.06, rows)

        # 6. Esc · 새 템플릿으로 나누기
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
        st = page.evaluate("() => ({ box: !!document.getElementById('olTune'), focus: document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.id || null : null })")
        check("Esc = 닫고 커서가 그 줄로", not st["box"] and st["focus"] == "p979", st)
        click_letter(page, "p988")   # 다른 줄 — 첫 누름은 커서
        click_letter(page, "p988")
        page.wait_for_selector("#olTune", timeout=15000)
        ready(page)
        page.click("#olTune .olt-pick")
        page.click('#olTune .olt-chip[data-letter="▪"]')
        box = ready(page)
        check("대표가 아닌 줄에서 「▪」 → 「새 템플릿으로 나누기 · T2L3a」 가 골라짐 · 아래에 레벨 범위", card(box, "split")["on"] and box["split"]["shown"] and box["split"]["from"] == "3", box)
        page.click("#olTune .olt-go")
        page.wait_for_function("() => !state.busy && state.undo === 3", timeout=30000)
        ready(page)
        page.wait_for_function("() => { const l = heads.outline && heads.outline.lines['p988']; return !!l && String(l.tpl) === '2~3a'; }", timeout=20000)
        MARK = """() => { const p = paraEl('p988'); const m = [...document.querySelectorAll('#doc .tpl-mark:not(.fmt)')].find((x) => Math.abs(x.getBoundingClientRect().top - p.getBoundingClientRect().top) < 6); return m ? m.textContent : ''; }"""
        seen = []
        for _ in range(40):   # 뼈대 밖 표시는 고친 뒤 잠깐 있다가 다시 견준다 — 가라앉은 뒤의 표시를 본다
            page.wait_for_timeout(300)
            seen.append(page.evaluate(MARK))
            if "T2L3a" in seen[-1] and len(seen) > 12:
                break
        print("    표시의 흐름:", list(dict.fromkeys(seen)), flush=True)
        mark = page.evaluate("""() => { const p = paraEl('p988'); const m = [...document.querySelectorAll('#doc .tpl-mark:not(.fmt)')].find((x) => Math.abs(x.getBoundingClientRect().top - p.getBoundingClientRect().top) < 6); return m ? m.textContent : ''; }""")
        check("적용 → 여백 표시 「T2L3a L3」", "T2L3a" in mark, mark)
        page.screenshot(path=str(OUT / "4_split.png"))

        # 7. 밖을 누르면 닫힘 · 오른쪽 단추 메뉴
        page.mouse.click(1400, 500)
        page.wait_for_timeout(250)
        check("밖을 누르면 닫힘", not page.evaluate(STATE)["box"])
        focus(page, "p994")   # 화면 안으로
        x, y = letter_xy(page, "p994")
        page.mouse.click(x + 60, y, button="right")
        page.wait_for_timeout(300)
        items = page.evaluate("() => { const m = document.querySelector('.ctx-menu'); return m && !m.hidden ? [...m.querySelectorAll('button')].map((b) => b.textContent) : []; }")
        if not items:
            print("    메뉴:", page.evaluate("([x, y]) => { const m = document.querySelector('.ctx-menu'), t = document.elementFromPoint(x, y); return { menu: m ? { hidden: m.hidden, n: m.children.length } : null, at: t ? t.className + '|' + (t.closest('.para') ? t.closest('.para').dataset.id : '') + '|' + !!t.closest('td') : null }; }", [x + 60, y]), flush=True)
            page.screenshot(path=str(OUT / "5_menu.png"))
        has = any(t.startswith("헤딩 고치기") for t in items)
        check("문단의 오른쪽 단추 메뉴에 「헤딩 고치기…」", has, items)
        if has:
            page.evaluate("() => [...document.querySelectorAll('.ctx-menu button')].find((b) => b.textContent.startsWith('헤딩 고치기')).click()")
            page.wait_for_selector("#olTune", timeout=15000)
            box = ready(page)
            check("메뉴 → 창(그 줄)", "T2 L3" in box["head"], box["head"])

            # 7b. 빈칸 칸 | mm · 2번째 줄 · 나누기의 레벨 범위(L1 부터 L3 까지)
            page.click('#olTune .olt-step[data-key="lead"] .olt-u[data-unit="mm"]')
            box = page.evaluate(BOX)
            check("「레터 앞 빈칸」 mm → 4칸의 폭(≈8.5mm) · 아래에 「= 4칸」", box["steps"]["lead"].endswith("mm") and abs(float(box["steps"]["lead"][:-2]) - 8.5) < 0.3 and "4칸" in box["was"]["lead"], [box["steps"], box["was"]])
            page.fill('#olTune .olt-step[data-key="lead"] .olt-val', "4.3")
            page.press('#olTune .olt-step[data-key="lead"] .olt-val', "Enter")
            box = ready(page)
            check("mm 를 적음(4.3) → 가장 가까운 칸 수(2칸 ≈ 4.2mm) · 「지금 …」", abs(float(box["steps"]["lead"][:-2]) - 4.2) < 0.3 and "지금" in box["was"]["lead"] and "2칸" in box["was"]["lead"], [box["steps"], box["was"]])
            page.click('#olTune .olt-l2b[data-l2="letter"]')
            box = ready(page)
            check("2번째 줄 「레터」 를 고름 → 그 칩이 켜짐 · 견본 셋째 줄", next(x for x in box["l2"] if x["k"] == "letter")["on"] and len(box["demo"]) == 3, [box["l2"], box["demo"]])
            page.click('#olTune .olt-card[data-scope="split"]')
            page.select_option("#olTune .olt-from", "1")
            box = ready(page)
            page.select_option("#olTune .olt-to", "3")
            box = ready(page)
            sp = box["split"]
            ins = [x["k"] for x in sp["lvs"] if x["in"]]
            check("나누기 — L1 부터 L3 까지: 레벨 띠 L1~L3 강조 · 이 줄 L3 표시 · 아래 줄은 T2 에 남음", sp["shown"] and ins == ["1", "2", "3"] and next(x for x in sp["lvs"] if x["k"] == "3")["me"]
                  and "T2L1a" in sp["sum"] and "남는 아래 줄" in sp["sum"] and card(box, "split")["on"] and "T2L1a" in card(box, "split")["t"], [sp, card(box, "split")])
            page.screenshot(path=str(OUT / "5_split_range.png"))
            n0 = page.evaluate(STATE)["undo"]
            page.click("#olTune .olt-go")
            page.wait_for_function("(n) => !state.busy && state.undo === n + 1", arg=n0, timeout=30000)
            page.wait_for_function("() => { const l = heads.outline && heads.outline.lines['p994']; return !!l && String(l.tpl) === '2~1a'; }", timeout=20000)
            rows = page.evaluate(LINES, ["p994"])
            check("적용 → 그 줄이 T2L1a · 레터 앞 빈칸 2칸", rows[0]["tpl"] == "2~1a" and rows[0]["text"].startswith("  -"), rows)
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)

        # 8. 실행 취소를 끝까지
        for _ in range(8):
            if not page.evaluate(STATE)["undo"]:
                break
            page.click("#undoBtn")
            page.wait_for_function("() => !state.busy", timeout=20000)
            page.wait_for_timeout(300)
        st = page.evaluate(STATE)
        same = requests.get(f"{base}/api/docs/{doc}/download", timeout=60).content == PLAN.read_bytes()
        check("실행 취소를 끝까지 → 내려받은 파일 = 원본 바이트", st["undo"] == 0 and same, [st, same])
        b.close()
    check("콘솔 오류 없음", not errors, errors[:5])


try:
    main()
finally:
    if errors:
        print("콘솔:", errors[:5], flush=True)
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'OK' if not fails else 'FAIL'} — 실패 {len(fails)}" + (f": {fails}" if fails else ""))
sys.exit(1 if fails else 0)

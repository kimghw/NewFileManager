"""개요 레벨 더하기(spec_hwpx_웹편집 ② §8-6 — app/static/outline_grow.js · app/outline_grow.py) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

연구개발계획서 양식(1·2단계를 끝점으로 — 가지 템플릿 T2 「□›o›-›·」: p970 □ › p972 o › p974 - › p975 ⋅ · p977 o › p979 - › p980 ⋅).
- 마지막 레벨이 아닌 줄(p974 「-」)의 Alt+↓ = 종전 레벨 내리기(후보 창 없음) → 실행 취소.
- 마지막 레벨 줄(p975 「⋅」)의 Alt+↓ → 그 줄 아래 후보 창(#olGrow · 모달 아님 · 창 안): 제목 「T2 에 새 개요 레벨 L5」 · 윗 레벨 견본 · 후보 3~10줄(이 템플릿이 쓰는 계열 없음) ·
  직접 입력 칸 · 앞 공백 「6칸」 · 둘째 줄 셋(글 시작이 고름).
- 키: ↓ 다음 후보 · → ← 앞 공백 · Tab 둘째 줄 방식 · 숫자 = 그 후보 · Esc = 닫고 커서가 그 줄로(문서는 안 바뀜).
- 견본: 둘째 줄의 자리가 방식마다 다르다(글 시작 > 레터 자리).
- Enter(「①」) → 그 줄이 「      ① 」 · 여백 표시 「T2 L5」 · 알림 · 실행 취소 1 · 화면의 템플릿 max 5 · 그 줄의 Enter = 「②」.
- 다른 묶음의 마지막 레벨이던 줄(p980 「⋅」 L4)의 Alt+↓ = 이제 종전 레벨 내리기(L5 가 있다 — 후보 창 없음).
- 새 마지막 레벨(L5)에서 Alt+↓ → 다시 후보(L6) · 직접 입력 「※」 = 거절 알림(문서 그대로) · 직접 입력 「◆」 = L6.
- 밖을 누르면 닫힘 · 「템플릿 관계」 열이 열려 있으면 트리가 다시 그려짐(레벨 수).
- 실행 취소를 끝까지 → 템플릿 max 4 · 내려받은 파일 = 원본 바이트.
- 단축키 설명에 그 줄 · 콘솔 오류 없음.

    python -X utf8 tools/smoke_outline_grow_ui.py <출력 폴더> [--port 18472]
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
ap.add_argument("--port", type=int, default=18472)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:700] if detail != "" and not ok else ""), flush=True)
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


BOX = """() => { const b = document.getElementById('olGrow'); if (!b) return null; const r = b.getBoundingClientRect(), st = OLG.st, p = paraEl(st.para).getBoundingClientRect();
  const opts = [...b.querySelectorAll('.olg-opt:not(.cus)')], demo = b.querySelector('.olg-demo');
  return { head: b.querySelector('.olg-head').textContent, ctx: demo.querySelector('.olg-l.ctx').textContent, demoH: Math.round(demo.getBoundingClientRect().height), demoLt: demo.querySelector('.olg-pre.lt').textContent,
    n: opts.length, letters: opts.map((o) => o.querySelector('.olg-pre.lt').textContent),
    sel: opts.findIndex((o) => o.classList.contains('sel')), cus: b.querySelector('.olg-opt.cus').classList.contains('sel'), input: !!b.querySelector('.olg-in'),
    lead: b.querySelector('.olg-n').textContent, line2: [...b.querySelectorAll('.olg-seg [role=radio]')].map((x) => x.getAttribute('aria-checked')), keys: b.querySelector('.olg-keys').textContent,
    modal: b.tagName === 'DIALOG', inView: r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight, below: r.top >= p.bottom - 1, above: r.bottom <= p.top + 1, w: Math.round(r.width), h: Math.round(r.height),
    focus: b.contains(document.activeElement), x2: Math.round(demo.querySelector('.olg-2').getBoundingClientRect().left - demo.getBoundingClientRect().left),
    x1: Math.round(demo.querySelector('.olg-pre.lt').getBoundingClientRect().left - demo.getBoundingClientRect().left), tags: opts.map((o) => (o.querySelector('.olg-tag') || {}).textContent || '') }; }"""
LINE = """(id) => { const p = paraEl(id); if (!p) return null; const ol = outlineLine(p);
  const mark = [...document.querySelectorAll('#doc .tpl-mark:not(.fmt)')].find((m) => Math.abs(m.getBoundingClientRect().top - p.getBoundingClientRect().top) < 6);
  return { text: readText(p), level: ol ? ol.level : null, tpl: ol ? String(ol.tpl) : null, mark: mark ? mark.textContent : '', focused: document.activeElement === p }; }"""
STATE = "() => ({ undo: state.undo, max: heads.outline ? heads.outline.templates['2'].max : null, chain: heads.outline ? heads.outline.templates['2'].chain : null, box: !!document.getElementById('olGrow'), toast: document.getElementById('toast').hidden ? '' : document.getElementById('toast').textContent })"


def focus(page, pid, at="end"):
    page.evaluate("([id, at]) => { const p = paraEl(id); p.scrollIntoView({ block: 'center' }); document.getElementById('scroller').scrollTop += 220; focusAt({ id, offset: at === 'end' ? readText(p).length : at }); }", [pid, at])
    page.wait_for_timeout(150)


def alt_down(page):
    page.keyboard.press("Alt+ArrowDown")


def box_open(page):
    page.wait_for_selector("#olGrow", timeout=15000)
    page.wait_for_timeout(120)
    return page.evaluate(BOX)


def settled(page):
    page.wait_for_function("() => !state.busy && !document.getElementById('olGrow')", timeout=20000)
    page.wait_for_timeout(500)  # outlineLoad(GET /outline) 뒤 표시 다시 그림


def main():
    wait_server()
    r = requests.post(base + "/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}, timeout=120)
    assert r.status_code == 200, r.text
    doc = r.json()["docId"]
    run_stage(doc, 1)
    run_stage(doc, 2)
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1500, "height": 950}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/#w={doc}")
        page.wait_for_selector("#doc .para", timeout=60000)
        page.wait_for_function("() => !!heads.outline && !!heads.outline.lines['p975']", timeout=30000)
        page.wait_for_timeout(600)
        s0 = page.evaluate(STATE)
        check("처음 — T2 「□›o›-›·」 max 4 · 실행 취소 없음", s0["max"] == 4 and s0["chain"] == ["□", "o", "-", "·"] and s0["undo"] == 0, s0)

        # 마지막 레벨이 아닌 줄 — 종전 레벨 내리기
        focus(page, "p974")
        alt_down(page)
        settled(page)
        v = page.evaluate(LINE, "p974")
        check("마지막 레벨이 아닌 줄(「-」 L3)의 Alt+↓ = 종전대로 한 레벨 내림(후보 창 없음)", v["level"] == 4 and v["text"].strip() == "⋅" and page.evaluate(STATE)["undo"] == 1, v)
        page.click("#undoBtn")
        settled(page)
        page.wait_for_function("() => outlineLine(paraEl('p974')).level === 3", timeout=20000)  # 실행 취소 뒤 오버레이를 다시 읽는다(GET /outline)
        check("실행 취소 → 「-」 L3", page.evaluate(LINE, "p974")["level"] == 3)

        # 마지막 레벨 줄 — 후보 창
        focus(page, "p975")
        alt_down(page)
        bx = box_open(page)
        check("마지막 레벨 줄(「⋅」 L4)의 Alt+↓ → 후보 창 「T2 에 새 개요 레벨 L5」 · 윗 레벨 견본", bx is not None and "T2 에 새 개요 레벨 L5" in bx["head"] and "L4" in bx["head"] and "윗 레벨(L4)" in bx["ctx"], bx)
        check("후보 3~10줄 · 이 템플릿이 쓰는 계열(□ o - ·) 없음 · 첫 줄이 고름 · 직접 입력 칸", 3 <= bx["n"] <= 10 and not set(bx["letters"]) & {"□", "o", "○", "-", "·", "•", "⋅"} and bx["sel"] == 0 and bx["input"], bx)
        check("깊은 기호가 먼저, 그다음 번호형(꼬리표 「번호」)", bx["letters"][:4] == ["▪", "▶", "◇", "①"] and bx["tags"][3] == "번호" and bx["tags"][0] != "번호", [bx["letters"], bx["tags"]])
        check("앞 공백 「6칸」(5칸 + 마지막 두 레벨의 차) · 둘째 줄 = 글 시작", bx["lead"] == "6칸" and bx["line2"] == ["true", "false", "false"], [bx["lead"], bx["line2"]])
        check("모달 아님 · 창 안 · 그 줄 아래(줄을 안 가림) · 폭 ≤ 340 · 높이 ≤ 420 · 초점이 창에 · 키 안내", not bx["modal"] and bx["inView"] and bx["below"] and bx["w"] <= 340 and bx["h"] <= 420 and bx["focus"] and "Enter" in bx["keys"], bx)
        check("견본 세 줄(윗 레벨 · 첫째 줄 · 둘째 줄) — 고른 레터 · 둘째 줄이 레터보다 오른쪽(글 시작)", bx["demoLt"] == bx["letters"][0] and bx["x2"] > bx["x1"] and bx["demoH"] >= 50, bx)
        page.screenshot(path=str(OUT / "01_box.png"))
        box = page.locator("#olGrow").bounding_box()
        page.screenshot(path=str(OUT / "01_box_clip.png"), clip={"x": max(0, box["x"] - 80), "y": max(0, box["y"] - 60), "width": box["width"] + 300, "height": box["height"] + 80})

        # 키 — ↓ · → ← · Tab · 숫자
        page.keyboard.press("ArrowDown")
        b1 = page.evaluate(BOX)
        page.keyboard.press("Alt+ArrowDown")
        b2 = page.evaluate(BOX)
        check("↓ = 다음 후보 · Alt+↓ 를 거듭 눌러도 다음 후보 · 견본이 그 레터로 · 견본 높이 그대로", b1["sel"] == 1 and b2["sel"] == 2 and b2["demoLt"] == b2["letters"][2] and b2["demoH"] == bx["demoH"] and b2["h"] == bx["h"], [b1["sel"], b2["sel"], b2["demoLt"], b2["demoH"], b2["h"]])
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        up = page.evaluate(BOX)
        page.keyboard.press("ArrowLeft")
        dn = page.evaluate(BOX)
        check("→ → ← = 앞 공백 8칸 → 7칸", up["lead"] == "8칸" and dn["lead"] == "7칸", [up["lead"], dn["lead"]])
        page.keyboard.press("ArrowLeft")
        x_text = page.evaluate(BOX)["x2"]
        page.keyboard.press("Tab")
        t1 = page.evaluate(BOX)
        check("Tab = 둘째 줄 「레터 자리」 · 견본의 둘째 줄이 레터 자리로(글 시작보다 왼쪽)", t1["line2"] == ["false", "true", "false"] and t1["x2"] < x_text and abs(t1["x2"] - t1["x1"]) <= 1, [t1["line2"], x_text, t1["x2"], t1["x1"]])
        page.keyboard.press("Shift+Tab")
        check("Shift+Tab = 다시 「글 시작」", page.evaluate(BOX)["line2"] == ["true", "false", "false"])
        page.keyboard.press("4")
        check("숫자 4 = 넷째 후보(「①」)", page.evaluate(BOX)["sel"] == 3)

        # Esc — 닫고 커서가 그 줄로 · 문서 그대로
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        st, v = page.evaluate(STATE), page.evaluate(LINE, "p975")
        check("Esc → 닫힘 · 커서가 그 줄로 · 문서·템플릿 그대로", not st["box"] and v["focused"] and v["level"] == 4 and st["undo"] == 0 and st["max"] == 4, [st, v])

        # 더하기 — 「①」
        alt_down(page)
        box_open(page)
        page.keyboard.press("4")
        page.keyboard.press("Enter")
        settled(page)
        toast = page.evaluate(STATE)["toast"]
        page.wait_for_function("() => heads.outline.templates['2'].max === 5", timeout=20000)  # 더한 뒤 오버레이 요약을 다시 읽는다(GET /outline — 같이 도는 검사가 많으면 늦다)
        page.wait_for_timeout(200)
        st, v = {**page.evaluate(STATE), "toast": toast}, page.evaluate(LINE, "p975")
        check("Enter(「①」) → 그 줄이 「      ① 」 L5 · 여백 표시 「T2 L5」 · 커서가 그 줄", v["text"] == "      ① " and v["level"] == 5 and "T2 L5" in v["mark"] and v["focused"], v)
        check("템플릿에 레벨이 더해짐(화면의 max 5 · 사슬 끝 「①」) · 실행 취소 1 · 알림", st["max"] == 5 and st["chain"][-1] == "①" and st["undo"] == 1 and "L5" in st["toast"] and "①" in st["toast"], st)
        page.screenshot(path=str(OUT / "02_grown.png"))
        page.keyboard.type("가나다")
        page.keyboard.press("Enter")
        page.wait_for_function("() => !state.busy && [...document.querySelectorAll('#doc .para')].some((q) => readText(q) === '      ② ')", timeout=20000)
        check("새 레벨 줄의 Enter = 같은 레벨 다음 번호 「②」", True)

        # 다른 묶음의 「⋅」 L4 — 이제 L5 가 있으니 종전 레벨 내리기
        focus(page, "p980")
        alt_down(page)
        settled(page)
        v = page.evaluate(LINE, "p980")
        check("다른 줄(「⋅」 L4)의 Alt+↓ = 새 레벨로 내림(후보 창 없음 · 「①」)", v["level"] == 5 and v["text"] == "      ① " and "T2 L5" in v["mark"], v)

        # 새 마지막 레벨에서 다시 — 직접 입력
        alt_down(page)
        bx = box_open(page)
        check("새 마지막 레벨(L5)의 Alt+↓ → 다시 후보(L6) · 「①」 계열은 후보에 없음", "L6" in bx["head"] and "①" not in bx["letters"], bx)
        page.click("#olGrow .olg-in")
        page.keyboard.type("※")
        page.keyboard.press("Enter")
        page.wait_for_function("() => !state.busy && !document.getElementById('olGrow') && !document.getElementById('toast').hidden", timeout=20000)
        st, v = page.evaluate(STATE), page.evaluate(LINE, "p980")
        check("직접 입력 「※」 = 거절 알림(개요 레터가 아님) · 문서 그대로", "개요 레터로 읽히지 않습니다" in st["toast"] and v["level"] == 5 and st["max"] == 5, [st, v])
        focus(page, "p980")
        alt_down(page)
        box_open(page)
        page.click("#olGrow .olg-in")
        page.keyboard.type("◆")
        check("직접 입력 칸에 초점이 가면 그 줄이 고름", page.evaluate(BOX)["cus"])
        page.keyboard.press("Enter")
        settled(page)
        page.wait_for_function("() => heads.outline.templates['2'].max === 6", timeout=20000)
        page.wait_for_timeout(200)
        st, v = page.evaluate(STATE), page.evaluate(LINE, "p980")
        check("직접 입력 「◆」 → L6", v["level"] == 6 and "◆" in v["text"] and st["max"] == 6 and "T2 L6" in v["mark"], [st, v])

        # 밖을 누르면 닫힘
        alt_down(page)
        box_open(page)
        page.mouse.click(1400, 500)
        page.wait_for_timeout(200)
        check("밖을 누르면 닫힘 · 문서 그대로", not page.evaluate(STATE)["box"] and page.evaluate(LINE, "p980")["level"] == 6)

        # 템플릿 관계 열이 열려 있으면 트리가 다시 그려진다(레벨 수) — 실행 취소로 레벨이 줄 때
        page.evaluate("() => tplRelOpen()")
        page.wait_for_selector("#headsDlgBody .tpl-tree", timeout=20000)
        k0 = page.evaluate("() => document.querySelector('#headsDlgBody .tpl-tree').dataset.ov || ''")
        page.click("#undoBtn")
        settled(page)
        page.wait_for_function("() => heads.outline.templates['2'].max === 5 && (document.querySelector('#headsDlgBody .tpl-tree').dataset.ov || '').includes('2:5')", timeout=20000)  # 실행 취소 뒤 오버레이를 다시 읽고 트리를 다시 그린다
        k1 = page.evaluate("() => document.querySelector('#headsDlgBody .tpl-tree').dataset.ov || ''")
        check("실행 취소 → 템플릿 max 5 · 열려 있는 템플릿 트리가 다시 그려짐", page.evaluate(STATE)["max"] == 5 and "2:6" in k0 and "2:5" in k1, [k0[-80:], k1[-80:]])
        page.evaluate("() => headsColClose(true)")

        # 단축키 설명
        has = page.evaluate("() => SHORTCUTS.some((g) => g.rows.some((r) => r.k.includes('Alt+↓') && r.d.includes('새 개요 레벨')))")
        check("단축키 설명에 「Alt+↓ — 새 개요 레벨 더하기」", has)

        # 실행 취소를 끝까지 — 원본 바이트
        for _ in range(12):
            if not page.evaluate(STATE)["undo"]:
                break
            page.click("#undoBtn")
            settled(page)
        page.wait_for_function("() => heads.outline.templates['2'].max === 4", timeout=20000)
        st = page.evaluate(STATE)
        same = requests.get(f"{base}/api/docs/{doc}/download", timeout=60).content == PLAN.read_bytes()
        check("실행 취소를 끝까지 → 템플릿 max 4 · 내려받은 파일 = 원본 바이트", st["undo"] == 0 and st["max"] == 4 and same, [st, same])
        b.close()
    bad = [e for e in errors if "status of 400" not in e]  # 직접 입력 「※」 의 거절(400)은 브라우저가 콘솔에 남긴다 — 그것 하나는 뜻한 것
    check("콘솔 오류 없음(뜻한 거절 400 하나 빼고)", not bad and len(errors) <= 1, errors[:5])


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

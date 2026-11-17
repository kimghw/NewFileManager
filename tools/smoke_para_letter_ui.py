"""레터 넣기(spec_hwpx_웹편집 ② §8-9 — app/static/para_letter.js · app/para_letter.py) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

연구개발계획서 양식(1·2단계를 끝점으로 — 주 사슬 T1 「1.›1-1.›(1)›o›-」 · 가지 T2 「□›o›-›·」: p966 1. › p968 1-1. › p969 빈 문단 › p970 □ › p972 o › p974 - › p975 ⋅).
- 「문단 수정」 묶음에 #tbLetter(아이콘 · 이름은 도움말) — 문단에 커서를 두기 전에는 꺼짐.
- 빈 문단(p969)에서 누름 → 단추 아래 메뉴(#plMenu · 모달 아님 · 창 안 · 폭 ≤ 320): 개요 레벨 줄(T1 · T2) · 번호 18 · 기호 13 · 직접 입력 · 「1.」 칸은 앞 줄 「1.」 에 이어 「2.」.
- 「처음부터」 → 그 칸이 「1.」(칸 자리는 그대로) · Esc = 닫고 커서가 그 문단으로(문서 그대로).
- 「①」 → 문단 「① 」 · 알림 · 실행 취소 1 · 다시 열면 「지금 ①」 + 「레터 빼기」 → 레터가 빠짐.
- 개요 레벨 「T2 □」 → 문단 「□ 」 · 여백 표시 「T2 L1」 · 문단 모양 = 그 레벨 것.
- 여러 문단을 고르고(p972~p975) 「①」 → ① ② ③ 차례로.
- 직접 입력 「※」 = 거절 알림(문서 그대로) · 「◆」 = 넣음 · 밖을 누르면 닫힘.
- 실행 취소를 끝까지 → 내려받은 파일 = 원본 바이트 · 콘솔 오류 없음.

    python -X utf8 tools/smoke_para_letter_ui.py <출력 폴더> [--port 18476]
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
ap.add_argument("--port", type=int, default=18476)
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


MENU = """() => { const b = document.getElementById('plMenu'); if (!b) return null; const r = b.getBoundingClientRect(), t = document.getElementById('tbLetter').getBoundingClientRect();
  const chips = (sel) => [...b.querySelectorAll(sel)];
  const at = (l) => { const c = b.querySelector(`.pl-grid .pl-chip[data-letter="${l}"]`), q = c.getBoundingClientRect(); return { text: c.textContent, cont: c.classList.contains('cont'), x: Math.round(q.left), y: Math.round(q.top), w: Math.round(q.width) }; };
  return { head: b.querySelector('.pl-head').textContent, levels: chips('.pl-row .pl-chip').map((c) => [c.dataset.level, c.textContent]), rows: chips('.pl-row .pl-t').map((x) => x.textContent),
    nums: chips('.pl-grid')[0] ? [...chips('.pl-grid')[0].children].map((c) => c.textContent) : [], syms: chips('.pl-grid')[1] ? [...chips('.pl-grid')[1].children].map((c) => c.textContent) : [],
    dot: at('1.'), circ: at('①'), seg: chips('.pl-seg [role=radio]').map((x) => x.getAttribute('aria-checked')), input: !!b.querySelector('.pl-in'), rm: !!b.querySelector('.pl-chip.rm'),
    modal: b.tagName === 'DIALOG', inView: r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight, below: r.top >= t.bottom - 1, w: Math.round(r.width), h: Math.round(r.height),
    focus: b.contains(document.activeElement), expanded: document.getElementById('tbLetter').getAttribute('aria-expanded'), scroll: b.querySelector('.pl-body').scrollHeight > b.querySelector('.pl-body').clientHeight + 1 }; }"""
LINE = """(id) => { const p = paraEl(id); if (!p) return null; const ol = outlineLine(p);
  const mark = [...document.querySelectorAll('#doc .tpl-mark:not(.fmt)')].find((m) => Math.abs(m.getBoundingClientRect().top - p.getBoundingClientRect().top) < 6);
  const s = getSelection(), o = s.rangeCount && p.contains(s.getRangeAt(0).startContainer) ? selOffsets(p) : null;
  return { text: readText(p), level: ol ? ol.level : null, tpl: ol ? String(ol.tpl) : null, mark: mark ? mark.textContent : '', focused: document.activeElement === p, caret: o ? o.start : null,
    left: Math.round(((state.byId.get(id) || {}).format || {}).indentLeftMm || 0) }; }"""
STATE = "() => ({ undo: state.undo, box: !!document.getElementById('plMenu'), busy: state.busy, toast: document.getElementById('toast').hidden ? '' : document.getElementById('toast').textContent })"


def focus(page, pid, at="end"):
    page.evaluate("([id, at]) => { const p = paraEl(id); p.scrollIntoView({ block: 'center' }); focusAt({ id, offset: at === 'end' ? readText(p).length : at }); }", [pid, at])
    page.wait_for_timeout(150)


def open_menu(page):
    page.click("#tbLetter")
    page.wait_for_selector("#plMenu", timeout=15000)
    page.wait_for_timeout(120)
    return page.evaluate(MENU)


def settled(page):
    page.wait_for_function("() => !state.busy && !document.getElementById('plMenu')", timeout=20000)
    page.wait_for_timeout(300)


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
        page.wait_for_function("() => !!heads.outline && !!heads.outline.lines['p975']", timeout=30000)
        page.wait_for_timeout(600)
        page.click('#toolModes [data-tool="para"]')
        page.wait_for_timeout(100)
        bt = page.evaluate("""() => { const b = document.getElementById('tbLetter'), r = b.getBoundingClientRect(); return { shown: r.width > 0, w: Math.round(r.width), h: Math.round(r.height), text: b.textContent.trim(),
          title: b.title, label: b.getAttribute('aria-label'), disabled: b.disabled, svg: !!b.querySelector('svg'), inSet: !!b.closest('[data-tool-set="para"]') }; }""")
        check("「문단 수정」 묶음에 레터 넣기 단추 — 아이콘(글 없음) · 이름은 도움말 · 다른 아이콘과 같은 크기", bt["shown"] and bt["inSet"] and bt["svg"] and bt["text"] == "" and bt["label"] == "레터 넣기"
              and bt["title"].startswith("레터 넣기 — ") and (bt["w"], bt["h"]) == (30, 28), bt)
        check("문단에 커서를 두기 전에는 꺼짐", bt["disabled"], bt)

        # 빈 문단 — 메뉴
        focus(page, "p969")
        check("문단에 커서를 두면 켜짐", not page.evaluate("() => document.getElementById('tbLetter').disabled"))
        m = open_menu(page)
        check("단추 아래 메뉴 — 모달 아님 · 창 안 · 폭 ≤ 320 · 초점이 메뉴에 · 단추 aria-expanded", m is not None and not m["modal"] and m["inView"] and m["below"] and m["w"] <= 320 and m["focus"] and m["expanded"] == "true", m)
        check("머리 「레터 넣기 — 이 문단을 헤딩으로」 · 직접 입력 칸 · 레터 없는 문단엔 「레터 빼기」 없음", "레터 넣기" in m["head"] and "이 문단을 헤딩으로" in m["head"] and m["input"] and not m["rm"], m)
        lv = dict((k, v) for k, v in m["levels"])
        check("이 문서의 개요 레벨 — T1(1. · 1-1. · (1) · o · -) · T2(□ · o · - · ⋅) 줄", m["rows"][:2] == ["T1", "T2"] and [lv.get(f"1|{k}") for k in range(1, 6)] == ["1.", "1-1.", "(1)", "o", "-"]
              and [lv.get(f"2|{k}") for k in range(1, 5)] == ["□", "o", "-", "⋅"], m)
        check("번호 18칸(둥근 숫자 · 숫자. · 숫자) · (숫자) · 숫자.숫자. …) · 기호 13칸", len(m["nums"]) == 18 and m["circ"]["text"] == "①" and {"1)", "(1)", "1.1.", "가.", "(가)", "a.", "Ⅰ.", "⑴", "㉮"} <= set(m["nums"])
              and m["syms"] == ["□", "■", "○", "●", "o", "-", "·", "•", "▪", "◇", "◆", "▶", "△"], m)
        check("「1.」 칸 = 앞 줄 「1.」 에 이어 「2.」(이어지는 번호 표시) · 「이어서」 가 고름", m["dot"]["text"] == "2." and m["dot"]["cont"] and m["seg"] == ["true", "false"] and not m["circ"]["cont"], m)
        page.screenshot(path=str(OUT / "menu.png"))
        page.locator("#plMenu").screenshot(path=str(OUT / "menu_only.png"))
        page.click("#plMenu .pl-seg [role=radio]:nth-child(2)")
        page.wait_for_timeout(100)
        m2 = page.evaluate(MENU)
        check("「처음부터」 → 그 칸이 「1.」 · 칸 자리·폭은 그대로 · 메뉴 높이 그대로", m2["dot"]["text"] == "1." and not m2["dot"]["cont"] and (m2["dot"]["x"], m2["dot"]["y"], m2["dot"]["w"]) == (m["dot"]["x"], m["dot"]["y"], m["dot"]["w"])
              and m2["h"] == m["h"] and m2["seg"] == ["false", "true"], [m["dot"], m2["dot"], m["h"], m2["h"]])
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        v = page.evaluate(LINE, "p969")
        st = page.evaluate(STATE)
        check("Esc = 닫고 커서가 그 문단으로 · 문서 그대로", not st["box"] and v["focused"] and v["text"] == "" and st["undo"] == 0, [st, v])

        # 레터만 — ①
        open_menu(page)
        page.click('#plMenu .pl-grid .pl-chip[data-letter="①"]')
        settled(page)
        v, st = page.evaluate(LINE, "p969"), page.evaluate(STATE)
        check("「①」 → 문단 「① 」 · 커서가 레터 뒤 · 알림 · 실행 취소 1 · 개요 줄 표시는 없음(레터만)", v["text"] == "① " and v["caret"] == 2 and v["focused"] and "레터 「①」 를 넣었습니다" in st["toast"] and st["undo"] == 1 and v["level"] is None, [v, st])
        m = open_menu(page)
        check("다시 열면 머리 「지금 ①」 · 「레터 빼기」 가 있음", "지금 「①」" in m["head"] and m["rm"], m)
        page.click("#plMenu .pl-chip.rm")
        settled(page)
        v, st = page.evaluate(LINE, "p969"), page.evaluate(STATE)
        check("「레터 빼기」 → 레터와 레터 뒤 빈칸이 빠짐 · 알림", v["text"] == "" and "레터 「①」 를 뺐습니다" in st["toast"] and st["undo"] == 2, [v, st])

        # 개요 레벨로 — T2 L1 「□」
        ref = page.evaluate(LINE, "p970")
        open_menu(page)
        page.click('#plMenu .pl-row .pl-chip[data-level="2|1"]')
        settled(page)
        v, st = page.evaluate(LINE, "p969"), page.evaluate(STATE)
        check("개요 레벨 「T2 □」 → 문단 「□ 」 · 여백 표시 「T2 L1」 · 그 레벨의 문단 모양 · 알림", v["text"] == "□ " and v["level"] == 1 and v["tpl"] == "2" and "T2" in v["mark"] and "L1" in v["mark"]
              and v["left"] == ref["left"] and "T2 L1 「□」 줄로 바꿨습니다" in st["toast"] and st["undo"] == 3, [v, ref, st])
        m = open_menu(page)
        cur = page.evaluate("() => [...document.querySelectorAll('#plMenu .pl-chip.cur')].map((c) => c.dataset.level)")
        check("다시 열면 그 레벨 칸이 「지금」 표시 · 머리에 「T2 L1」", cur == ["2|1"] and "T2 L1" in m["head"], [cur, m["head"]])
        page.mouse.click(700, 700)  # 밖을 누름
        page.wait_for_timeout(150)
        check("밖을 누르면 닫힘", not page.evaluate(STATE)["box"])

        # 여러 문단 — ① ② ③
        page.evaluate("""() => { const a = paraEl('p972'), z = paraEl('p975'); a.scrollIntoView({ block: 'center' }); const r = document.createRange(); r.setStart(a, 0); r.setEnd(z, z.childNodes.length);
          const s = getSelection(); s.removeAllRanges(); s.addRange(r); }""")
        page.wait_for_timeout(150)
        m = open_menu(page)
        check("여러 문단을 고르고 열면 머리 「고른 3문단」(빈 문단은 뺌)", "고른 3문단" in m["head"], m["head"])
        page.click('#plMenu .pl-grid .pl-chip[data-letter="①"]')
        settled(page)
        got = [page.evaluate(LINE, i)["text"] for i in ("p972", "p973", "p974", "p975")]
        st = page.evaluate(STATE)
        check("「①」 → 고른 문단에 차례로 ① ② ③(레터 앞 빈칸은 그대로 · 빈 문단은 그대로) · 알림", got == ["  ① ", "", "    ② ", "     ③ "] and "① ② ③" in st["toast"] and "3문단" in st["toast"], [got, st])

        # 직접 입력 — 거절 · 넣기
        focus(page, "p977")
        open_menu(page)
        page.fill("#plMenu .pl-in", "※")
        page.keyboard.press("Enter")
        page.wait_for_function("() => !state.busy && !document.getElementById('toast').hidden", timeout=20000)
        v, st = page.evaluate(LINE, "p977"), page.evaluate(STATE)
        check("직접 입력 「※」 = 거절 알림 · 문서 그대로", "헤딩 레터로 읽히지 않습니다" in st["toast"] and v["text"] == "  o " and st["undo"] == 4, [v, st])
        focus(page, "p977")
        open_menu(page)
        page.fill("#plMenu .pl-in", "◆")
        page.click("#plMenu .pl-chip.go")
        settled(page)
        v = page.evaluate(LINE, "p977")
        check("직접 입력 「◆」 = 그 줄의 레터가 바뀜(레터 앞 빈칸 · 레터 뒤 빈칸은 그대로)", v["text"] == "  ◆ " and page.evaluate(STATE)["undo"] == 5, v)

        # 좁은 창 — 메뉴가 창 안
        page.set_viewport_size({"width": 700, "height": 600})
        page.wait_for_timeout(400)
        focus(page, "p979")
        m = open_menu(page)
        check("좁은 창(700×600)에서도 메뉴가 창 안(넘치면 메뉴 안에서 스크롤)", m["inView"] and m["w"] <= 320, m)
        page.screenshot(path=str(OUT / "menu_narrow.png"))
        page.keyboard.press("Escape")
        page.set_viewport_size({"width": 1500, "height": 950})
        page.wait_for_timeout(400)

        # 실행 취소를 끝까지
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

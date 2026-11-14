"""개요 레벨 대표 서식 · 대표에 맞추기 · 템플릿 종속(spec_hwpx_웹편집 ② §8-2 — app/static/outline_match.js · app.js tplMarksDraw·tplRelOpen) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

연구개발계획서 양식을 올리고 1·2단계(LLM 없이)를 끝점으로 돌린 뒤 작업을 연다(헤딩 탭은 안 연다):
- 문서를 열자마자 「TN Lk」 표가 그려진다(그래프를 안 읽었어도 — 개요 오버레이 줄).
- p5209(T3 L2 「    - 」)의 표를 누르면 2열 「템플릿 관계」 가 열리고(그때 그래프를 읽음) T3 L2 의 갈래 목록이 펴져 그 줄의 갈래가 표시된다(대표와 다른 값 「앞 공백 3칸 → 4칸」).
- 「대표에 맞추기(2줄)」 → 그 두 줄의 접두가 대표 「   - 」 로 · 갈래 1가지 · 실행 취소로 되돌아감.
- 「대표로」 → 대표 갈래가 바뀌고 문서 표 풍선에 「이 레벨의 대표 줄」 · 실행 취소.
- T9 「[기관] › o › -」 의 「하위로」 → 「T8 L3 … 아래 40곳 → T8T9 L4~L6」 → 넣기 → 종속 템플릿 「T8T9」(T8 은 그대로 · T9 줄에 「→ T8T9」 · 종속 템플릿 줄에 「종속 — T8 L3 아래 T9」)
  · 문서 표 「T8T9 L4」 · 「템플릿 관계」 에서 T8 L3 아래에 T9 대신 T8T9 · 「떼기」 → 종속 템플릿이 없어지고 T9 줄이 돌아옴(2026-11-15 사용자 「T1T3 템플릿으로」).
- 도구 줄 「서식」 묶음의 넷째 아이콘 「템플릿 관계」(#tbTplRel) — 켜짐 · 누르면 열고 닫음 · 눌림.
- 좁은 창(480px)에서 2열 가로 넘침 없음 · 콘솔 오류 없음.

    python -X utf8 tools/smoke_outline_match_ui.py <출력 폴더> [--port 18431]
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
ap.add_argument("--port", type=int, default=18431)
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
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:600] if detail != "" and not ok else ""), flush=True)
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


MARK_OF = """(pid) => { const p = document.querySelector(`#doc .para[data-id="${pid}"]`); if (!p) return -1; p.scrollIntoView({ block: 'center' });
  const top = p.getBoundingClientRect().top; const ms = [...document.querySelectorAll('.tpl-mark')]; let best = -1, gap = 12;
  ms.forEach((m, i) => { const g = Math.abs(m.getBoundingClientRect().top - top); if (g < gap && p.closest('.sheet') === m.closest('.sheet')) { best = i; gap = g; } });
  return best; }"""
OLM = """([t, l]) => { const r = document.querySelector(`#headsDlgBody .olm[data-tpl="${t}"][data-level="${l}"]`); if (!r) return null;
  return { sel: r.classList.contains('sel'), sum: (r.querySelector('.olm-sum') || {}).textContent || '', groups: [...r.querySelectorAll('.olm-g')].map((g) => ({ rep: g.classList.contains('rep'), sel: g.classList.contains('sel'),
    paras: g._paras || [], diff: (g.querySelector('.olm-diff') || {}).textContent || '' })), buttons: [...r.querySelectorAll(':scope > button')].map((b) => b.textContent) }; }"""


def mark_index(page, pid):
    i = page.evaluate(MARK_OF, pid)
    page.wait_for_timeout(200)
    return page.evaluate(MARK_OF, pid) if i < 0 else i


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
        page.wait_for_selector("#doc .para[data-id=p970]", timeout=60000)
        page.wait_for_function("() => document.querySelectorAll('.tpl-mark').length > 20", timeout=30000)
        st = page.evaluate("() => ({ graph: !!heads.graph, marks: [...document.querySelectorAll('.tpl-mark')].map((m) => m.textContent).slice(0, 400) })")
        check("문서를 열자마자 「TN Lk」 표(헤딩 탭·그래프 없이 — 오버레이 줄)", not st["graph"] and any(t.startswith("T2 L1") for t in st["marks"]) and any(t.startswith("T3 L2") for t in st["marks"]), st)
        page.screenshot(path=str(OUT / "01_marks.png"))

        # 문서 표 → 템플릿 관계 · 그 레벨의 갈래 표시
        i = mark_index(page, "p5209")
        check("p5209 의 문서 표를 찾음", i >= 0, i)
        page.locator(".tpl-mark").nth(i).click()
        page.wait_for_selector("#headsDlg[data-kind=templates] .olm.sel", timeout=20000)
        page.wait_for_function("() => document.querySelector('#headsDlgBody .olm.sel .olm-g.sel')", timeout=20000)
        v = page.evaluate(OLM, ["3", 2])
        selg = next((g for g in (v or {}).get("groups", []) if g["sel"]), {})
        check("표를 누르면 「템플릿 관계」 의 T3 L2 갈래 목록 · 그 줄의 갈래 표시(앞 공백 3칸 → 4칸) · 「누른 줄을 대표로」",
              v and v["sel"] and "서식 3가지" in v["sum"] and "p5209" in selg.get("paras", []) and "앞 공백 3칸 → 4칸" in selg.get("diff", "") and page.evaluate("() => !!heads.graph")
              and "누른 줄을 대표로" in v["buttons"], v)
        page.screenshot(path=str(OUT / "02_rel_focus.png"))

        # 대표에 맞추기 → 실행 취소
        page.locator('#headsDlgBody .olm[data-tpl="3"][data-level="2"] > button', has_text="대표에 맞추기").click()
        page.wait_for_function("() => (document.querySelector('#doc .para[data-id=p5209]') || {}).textContent?.startsWith('   - ') && !document.querySelector('#doc .para[data-id=p5209]').textContent.startsWith('    ')", timeout=20000)
        page.wait_for_function("() => (document.querySelector('#headsDlgBody .olm[data-tpl=\"3\"][data-level=\"2\"] .olm-sum') || {}).textContent === '서식 1가지 — 모두 같음'", timeout=20000)
        t = page.evaluate("() => ['p5209', 'p5765'].map((i) => document.querySelector(`#doc .para[data-id=${i}]`).textContent.slice(0, 6))")
        check("「대표에 맞추기(2줄)」 → 두 줄의 접두가 대표 「   - 」 · 갈래 1가지", t == ["   - ", "   - "] or all(x.startswith("   - ") for x in t), t)
        page.click("#undoBtn")
        page.wait_for_function("() => (document.querySelector('#doc .para[data-id=p5209]') || {}).textContent?.startsWith('    - ')", timeout=20000)
        page.wait_for_function("() => /서식 3가지/.test((document.querySelector('#headsDlgBody .olm[data-tpl=\"3\"][data-level=\"2\"] .olm-sum') || {}).textContent || '')", timeout=20000)
        check("실행 취소 → 원래 접두 · 갈래 3가지로", True)

        # 대표로 → 풍선 · 실행 취소
        row = '#headsDlgBody .olm[data-tpl="3"][data-level="2"]'
        if not page.locator(f"{row} .olm-list").count():
            page.locator(f"{row} > button", has_text="갈래").click()
        page.locator(f"{row} .olm-g:not(.rep)").first.locator("button", has_text="대표로").click()
        page.wait_for_function("(r) => { const g = document.querySelector(r + ' .olm-g.rep'); return g && g._paras && !g._paras.includes('p6502'); }", arg=row, timeout=20000)
        rep = page.evaluate("() => heads.outline.templates['3'].slots['2'].rep")
        i = mark_index(page, rep)
        tip = page.locator(".tpl-mark").nth(i).get_attribute("title") if i >= 0 else ""
        check("「대표로」 → 대표 갈래가 바뀜(누른 줄 p5209 이 대표) · 그 줄의 문서 표 풍선에 「이 레벨의 대표 줄」", rep == "p5209" and "이 레벨의 대표 줄" in (tip or ""), [rep, tip])
        page.click("#undoBtn")
        page.wait_for_function("() => heads.outline && heads.outline.templates['3'].slots['2'].rep === 'p6502'", timeout=20000)
        check("실행 취소 → 대표가 원래대로", True)

        # 하위로 넣기 · 떼기
        page.evaluate("() => headsTplView(9)")
        page.wait_for_selector('#headsDlgBody li.trel-node[data-tpl="9"] > .trel-row >> text=하위로', timeout=20000)
        node = page.locator('#headsDlgBody li.trel-node[data-tpl="9"]').filter(has=page.locator(":scope > .trel-row button", has_text="하위로")).first
        node.locator(":scope > .trel-row button", has_text="하위로").click()
        form = node.locator(":scope > .olm-merge")
        opts = form.locator("select option").all_inner_texts()
        target = next((k for k, o in enumerate(opts) if o.startswith("T8 L3")), -1)
        check("「하위로」 → 넣을 자리 목록(T8 L3 … 아래 40곳 → 종속 템플릿 T8T9 L4~L6 · 「안 됨」 자리 없음)", target >= 0 and "40곳" in opts[target] and "T8T9 L4~L6" in opts[target] and not any("안 됨" in o for o in opts), opts)
        form.locator("select").select_option(str(target))
        form.locator("button", has_text="넣기").click()
        page.wait_for_function("() => heads.outline && heads.outline.templates['8+9'] && heads.outline.templates['8+9'].no === '8T9'", timeout=20000)
        page.wait_for_function("() => [...document.querySelectorAll('.tpl-mark')].some((m) => /T8T9 L4/.test(m.textContent))", timeout=20000)
        st = page.evaluate("""() => ({ t8: heads.outline.templates['8'].max, comp: !!document.querySelector('#headsDlgBody li.trel-node[data-tpl="8+9"]'),
          shared: (document.querySelector('#headsDlgBody li.trel-node[data-tpl="8+9"] .olm-shared') || {}).textContent || '' })""")
        if not st["shared"]:
            page.locator('#headsDlgBody li.trel-node[data-tpl="8+9"] > .trel-row .htog').first.click()
            page.wait_for_timeout(300)
            st = page.evaluate("""() => ({ t8: heads.outline.templates['8'].max, comp: !!document.querySelector('#headsDlgBody li.trel-node[data-tpl="8+9"]'),
              shared: (document.querySelector('#headsDlgBody li.trel-node[data-tpl="8+9"] .olm-shared') || {}).textContent || '' })""")
        check("종속 템플릿 T8T9 — T8 은 그대로(L3 까지) · 「템플릿 관계」 에 T8T9 줄 · 펴면 「L1~L3 = T8 의 레벨」", st["t8"] == 3 and st["comp"] and "L1~L3 = T8 의 레벨" in st["shared"], st)
        chips = page.evaluate("() => [...document.querySelectorAll('#headsDlgBody .olm-chip')].map((c) => c.textContent)")
        check("넣기 → T9 줄에 「→ T8T9」 · 종속 템플릿 줄에 「종속 — T8 L3 아래 T9」 · 문서 표 「T8T9 L4」(바로 보임)", any("→ T8T9" in c for c in chips) and any("종속 — T8 L3 아래 T9" in c for c in chips), chips)
        page.screenshot(path=str(OUT / "03_merged.png"))
        page.locator("#headsDlgBody .trel-row button", has_text="떼기").first.click()
        page.wait_for_function("() => heads.outline && !heads.outline.templates['8+9']", timeout=20000)
        check("「떼기」 → 종속 템플릿이 없어지고 T9 줄이 돌아옴", page.evaluate("() => Object.values(heads.outline.lines).filter((x) => x.tpl === '9').length") == 92)

        # 도구 줄 「서식」 묶음의 「템플릿 관계」 — 묶음(spec_서식복사 ② §3)이 있는 판에서만(개요만 커밋한 판에는 묶음이 없다 — 표·헤딩 탭으로 연다)
        if page.locator("#toolModes [data-tool=style]").count():
            page.click("#toolModes [data-tool=style]")
            page.wait_for_timeout(400)
            tb = page.evaluate("() => { const b = document.getElementById('tbTplRel'); return { on: !b.disabled, label: b.getAttribute('aria-label'), svg: !!b.querySelector('svg.toolbar-glyph'), text: b.textContent.trim() }; }")
            check("넷째 아이콘 「템플릿 관계」 — 켜짐 · 글 없는 아이콘", tb == {"on": True, "label": "템플릿 관계", "svg": True, "text": ""}, tb)
            page.click("#tbTplRel")
            page.wait_for_function("() => { const c = document.getElementById('headsDlg'); return !c.hidden && c.dataset.kind === 'templates'; }", timeout=10000)
            check("누르면 「템플릿 관계」 열 · 눌림", page.get_attribute("#tbTplRel", "aria-pressed") == "true")
            page.click("#tbTplRel")
            page.wait_for_function("() => document.getElementById('headsDlg').hidden", timeout=10000)
            check("다시 누르면 닫힘", page.get_attribute("#tbTplRel", "aria-pressed") == "false")
        else:
            print("SKIP 도구 줄 「서식」 묶음 없음 — 넷째 아이콘 검사 3개 건너뜀", flush=True)

        # 좁은 창
        page.set_viewport_size({"width": 480, "height": 900})
        page.evaluate("() => tplRelOpen(3, { tpl: '3', level: 2, para: 'p5209' })")
        page.wait_for_selector("#headsDlg[data-kind=templates] .olm.sel", timeout=20000)
        page.wait_for_timeout(400)
        ov = page.evaluate("() => { const c = document.getElementById('headsDlgBody'); return [c.scrollWidth, c.clientWidth]; }")
        check("좁은 창(480px) — 2열 가로 넘침 없음", ov[0] <= ov[1] + 1, ov)
        page.screenshot(path=str(OUT / "04_narrow.png"))
        b.close()
    check("콘솔 오류 없음", not errors, errors[:5])


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

"""개요 레벨 대표 서식 · 대표에 맞추기 · 템플릿 종속(spec_hwpx_웹편집 ② §8-2 — app/static/outline_match.js · app.js tplMarksDraw·tplRelOpen) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

연구개발계획서 양식을 올리고 1·2단계(LLM 없이)를 끝점으로 돌린 뒤 작업을 연다(헤딩 탭은 안 연다):
- 문서를 열자마자 「TN Lk」 표가 그려진다(그래프를 안 읽었어도 — 개요 오버레이 줄).
- p5209(T3 L2 「    - 」)의 표를 누르면 2열 「템플릿 관계」 가 열리고(그때 그래프를 읽음) T3 L2 의 갈래 목록이 펴져 그 줄의 갈래가 표시된다(대표와 다른 값 「앞 공백 3칸 → 4칸」).
- 「대표에 맞추기(2줄)」 → 그 두 줄의 접두가 대표 「   - 」 로 · 갈래 1가지 · 실행 취소로 되돌아감.
- 「대표로」 → 대표 갈래가 바뀌고 문서 표 풍선에 「이 레벨의 대표 줄」 · 실행 취소.
- 갈래 카드를 대표 카드에 끌어 놓으면 대표 미리보기(견본 둘 · 다른 값은 미리보기 기준 · 대표 그대로) · Esc 로 거둠 · ⠿ 누름 → 「대표로 정하기」 · 「모두 고르기」 → 「고른 서식 2가지 맞추기」 한 번(실행 취소 1) ·
  미리보기 + 「지금 대표」 갈래 고르기 → 「대표로 정하고 고른 서식 1가지 맞추기」(2026-11-16 사용자 「드래그 해서 대표로 … 그 서식으로 볼 수 있게」 · 「체크체크체크 한번에 변경」).
- T9 「[기관] › o › -」 의 「하위로」 → 「T8 L3 … 아래 40곳 → T8T9 L4~L6」 → 넣기 → 종속 템플릿 「T8T9」(T8 은 그대로 · T9 줄에 「→ T8T9」 · 종속 템플릿 줄에 「종속 — T8 L3 아래 T9」)
  · 문서 표 「T8T9 L4」 · 「템플릿 관계」 에서 T8 L3 아래에 T9 대신 T8T9 · 「떼기」 → 종속 템플릿이 없어지고 T9 줄이 돌아옴(2026-11-15 사용자 「T1T3 템플릿으로」).
- 갈래 줄의 「다른 템플릿으로」(대표 갈래에는 없음) → 그 아래 한 줄 「새 템플릿 T9L2a · 넣기」 → 서식 종속 템플릿 「T9L2a」(② §8-5 — 줄은 L2 부터 · 「서식 종속 — T9 L2 의 다른 서식」 · 「하위로」 없음 ·
  문서 표 「T9L2a L2」 · T9 L2 줄에 「→ T9L2a(n줄)」) · 「합치기」 → 없어지고 줄이 T9 L2 로(2026-11-15 사용자 「서식이 다르면 템플릿도 다른거잖아 … T1L3 로 하고 a,b,c」).
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

        # 문서 표 → (그 템플릿·레벨만 또렷이 — 이름 줄 설명의 「템플릿 관계」) → 템플릿 관계 · 그 레벨의 갈래 표시.
        # 2026-11-15 표 누름이 「템플릿만 또렷이」 로 바뀜(spec_헤딩_추출 ② §7 — fmt_focus.js): 전에 표를 누르면 바로 열리던 열은 설명의 단추가 연다(누른 줄은 그대로 전해진다)
        i = mark_index(page, "p5209")
        check("p5209 의 문서 표를 찾음", i >= 0, i)
        page.locator(".tpl-mark").nth(i).click()
        page.wait_for_function("() => FMF.kind === 'tpl' && FMF.tpl === '3' && FMF.level === 2 && FMF.para === 'p5209' && document.getElementById('headsDlg').dataset.kind !== 'templates'", timeout=20000)
        page.click("#fmtKey .fm-key-rel")
        page.wait_for_selector("#headsDlg[data-kind=templates] .olm.sel", timeout=20000)
        page.wait_for_function("() => document.querySelector('#headsDlgBody .olm.sel .olm-g.sel')", timeout=20000)
        v = page.evaluate(OLM, ["3", 2])
        selg = next((g for g in (v or {}).get("groups", []) if g["sel"]), {})
        check("표를 누르면 「템플릿 관계」 의 T3 L2 갈래 목록 · 그 줄의 갈래 표시(레터 앞 빈칸: 지금 4칸 → 대표 3칸 — 값마다 이름표) · 「누른 줄을 대표로」",
              v and v["sel"] and "서식 3가지" in v["sum"] and "p5209" in selg.get("paras", []) and "레터 앞 빈칸: 지금 4칸 → 대표 3칸" in selg.get("diff", "") and page.evaluate("() => !!heads.graph")
              and "누른 줄을 대표로" in v["buttons"], v)
        page.screenshot(path=str(OUT / "02_rel_focus.png"))

        # 대표에 맞추기 → 실행 취소
        page.locator('#headsDlgBody .olm[data-tpl="3"][data-level="2"] > button', has_text="대표에 맞추기").click()
        page.wait_for_function("() => (document.querySelector('#doc .para[data-id=p5209]') || {}).textContent?.startsWith('   -\u2002') && !document.querySelector('#doc .para[data-id=p5209]').textContent.startsWith('    ')", timeout=20000)  # 레터 뒤 = 묶음 빈칸(② §8-8)
        page.wait_for_function("() => (document.querySelector('#headsDlgBody .olm[data-tpl=\"3\"][data-level=\"2\"] .olm-sum') || {}).textContent === '서식 1가지 — 모두 같음'", timeout=20000)
        t = page.evaluate("() => ['p5209', 'p5765'].map((i) => document.querySelector(`#doc .para[data-id=${i}]`).textContent.slice(0, 6))")
        check("「대표에 맞추기(2줄)」 → 두 줄의 접두가 대표 「   - 」(레터 뒤 = 묶음 빈칸) · 갈래 1가지", all(x.startswith("   -\u2002") for x in t), t)
        page.click("#undoBtn")
        page.wait_for_function("() => (document.querySelector('#doc .para[data-id=p5209]') || {}).textContent?.startsWith('    - ')", timeout=20000)
        page.wait_for_function("() => /서식 3가지/.test((document.querySelector('#headsDlgBody .olm[data-tpl=\"3\"][data-level=\"2\"] .olm-sum') || {}).textContent || '')", timeout=20000)
        check("실행 취소 → 원래 접두 · 갈래 3가지로", True)

        # 대표로 → 풍선 · 실행 취소
        row = '#headsDlgBody .olm[data-tpl="3"][data-level="2"]'
        if not page.locator(f"{row} .olm-list").count():
            page.locator(f"{row} > button", has_text="서식 목록").click()
        page.locator(f"{row} .olm-g:not(.rep)").first.locator("button", has_text="대표로").click()
        page.wait_for_function("(r) => { const g = document.querySelector(r + ' .olm-g.rep'); return g && g._paras && !g._paras.includes('p6502'); }", arg=row, timeout=20000)
        rep = page.evaluate("() => heads.outline.templates['3'].slots['2'].rep")
        i = mark_index(page, rep)
        tip = page.locator(".tpl-mark").nth(i).get_attribute("title") if i >= 0 else ""
        check("「대표로」 → 대표 갈래가 바뀜(누른 줄 p5209 이 대표) · 그 줄의 문서 표 풍선에 「이 레벨의 대표 줄」", rep == "p5209" and "이 레벨의 대표 줄" in (tip or ""), [rep, tip])
        page.click("#undoBtn")
        page.wait_for_function("() => heads.outline && heads.outline.templates['3'].slots['2'].rep === 'p6502'", timeout=20000)
        check("실행 취소 → 대표가 원래대로", True)

        # 대표 미리보기(끌어 놓기) · 고른 갈래 한 번에 맞추기(2026-11-16 사용자 「드래그 해서 대표로 갖어가면 그 서식으로 볼 수 있게」 · 「체크체크체크 한번에 변경」)
        page.wait_for_selector(f"{row} .olm-list .olm-g.rep", timeout=20000)
        src = page.locator(f"{row} .olm-g:not(.rep)").first
        src_paras = src.evaluate("(e) => e._paras")
        src.drag_to(page.locator(f"{row} .olm-g.rep").first)
        page.wait_for_selector(f"{row} .olm-try", timeout=10000)
        tv = page.evaluate("""(r) => { const x = document.querySelector(r); const t = x.querySelector('.olm-try');
          return { paras: t._paras, samps: t.querySelectorAll('.olp-samp').length, label: (x.querySelector('.olm-rep-try') || {}).textContent || '',
            was: [...x.querySelectorAll('.olm-g.was .olm-badge')].map((b) => b.textContent), rep: heads.outline.templates['3'].slots['2'].rep,
            diffs: [...x.querySelectorAll('.olm-g.was .olm-diff')].map((d) => d.textContent), rowBtns: [...x.querySelectorAll(':scope > button')].map((b) => b.textContent),
            go: (x.querySelector('.olm-bulk-go') || {}).textContent || '' }; }""", row)
        check("갈래를 대표 카드에 끌어 놓으면 미리보기 — 미리보기 카드(견본 둘: 미리보기 · 지금 대표) · 옛 대표 카드 「지금 대표」 · 다른 값은 미리보기 기준 · 대표는 그대로 · 「대표에 맞추기」 숨김",
              tv["paras"] == src_paras and tv["samps"] == 2 and tv["label"].startswith("미리보기") and tv["was"] == ["지금 대표"] and tv["rep"] == "p6502"
              and tv["diffs"] and "→ 대표" in tv["diffs"][0] and not any("대표에 맞추기" in b for b in tv["rowBtns"]) and tv["go"].startswith("대표로 정하고"), tv)
        page.screenshot(path=str(OUT / "03b_try.png"))
        page.keyboard.press("Escape")
        page.wait_for_function("(r) => !document.querySelector(r + ' .olm-try') && document.querySelector(r + ' .olm-g.rep')", arg=row, timeout=10000)
        check("Esc → 미리보기를 거둠(대표 카드로 · 대표 그대로)", page.evaluate("() => heads.outline.templates['3'].slots['2'].rep") == "p6502")

        g2 = page.locator(f"{row} .olm-g:not(.rep)").nth(1)
        p2 = g2.evaluate("(e) => e._paras[0]")
        g2.locator(".olm-grip").click()
        page.wait_for_selector(f"{row} .olm-try", timeout=10000)
        page.locator(f"{row} .olm-try button", has_text="대표로 정하기").click()
        page.wait_for_function("(p) => heads.outline.templates['3'].slots['2'].rep === p", arg=p2, timeout=20000)
        page.wait_for_timeout(300)
        check("⠿ 를 눌러도 미리보기 · 「대표로 정하기」 → 그 갈래 줄이 대표 · 미리보기 끝", page.locator(f"{row} .olm-try").count() == 0, p2)
        page.click("#undoBtn")
        page.wait_for_function("() => heads.outline.templates['3'].slots['2'].rep === 'p6502'", timeout=20000)
        page.wait_for_timeout(300)
        check("실행 취소 → 대표가 원래대로(미리보기는 다시 안 생김)", page.locator(f"{row} .olm-try").count() == 0)

        page.wait_for_selector(f"{row} .olm-bulk", timeout=20000)
        page.locator(f"{row} .olm-bulk .olm-all input").check()
        go = page.locator(f"{row} .olm-bulk-go")
        txt = go.text_content()
        check("「모두 고르기」 → 「고른 서식 2가지 맞추기(2줄)」 · 카드 ☐ 둘 다 켜짐", txt == "고른 서식 2가지 맞추기(2줄)" and page.locator(f"{row} .olm-g input.olm-chk:checked").count() == 2, txt)
        go.click()
        page.wait_for_function("() => (document.querySelector('#headsDlgBody .olm[data-tpl=\"3\"][data-level=\"2\"] .olm-sum') || {}).textContent === '서식 1가지 — 모두 같음'", timeout=20000)
        t = page.evaluate("() => ['p5209', 'p5765'].map((i) => document.querySelector(`#doc .para[data-id=${i}]`).textContent.slice(0, 6))")
        check("「고른 서식 맞추기」 → 고른 두 갈래 줄이 대표 접두 「   - 」 · 갈래 1가지", all(x.startswith("   -\u2002") and not x.startswith("    ") for x in t), t)
        page.click("#undoBtn")
        page.wait_for_function("() => /서식 3가지/.test((document.querySelector('#headsDlgBody .olm[data-tpl=\"3\"][data-level=\"2\"] .olm-sum') || {}).textContent || '')", timeout=20000)
        check("실행 취소 한 번 → 갈래 3가지로", True)

        PRE = "(i) => (document.querySelector(`#doc .para[data-id=${i}]`).textContent.match(/^\\s*\\S+\\s*/) || [''])[0]"
        page.wait_for_selector(f"{row} .olm-list .olm-g.rep", timeout=20000)
        page.locator(f"{row} .olm-g:not(.rep)").first.drag_to(page.locator(f"{row} .olm-g.rep").first)
        page.wait_for_selector(f"{row} .olm-try", timeout=10000)
        cand = page.evaluate("() => OLM.try.pid")
        cpre = page.evaluate(PRE, cand)
        page.locator(f"{row} .olm-g.was input.olm-chk").check()
        txt = page.locator(f"{row} .olm-bulk-go").text_content()
        page.locator(f"{row} .olm-bulk-go").click()
        page.wait_for_function("(p) => heads.outline.templates['3'].slots['2'].rep === p", arg=cand, timeout=20000)
        cpre = cpre.rstrip(" ") + chr(0x2002) * (len(cpre) - len(cpre.rstrip(" ")))   # 맞추면 새 대표도 확정 서식이 된다 — 레터 뒤 빈칸 = 묶음 빈칸(spec_hwpx_웹편집 ② §8-8)
        page.wait_for_function("([i, s]) => (document.querySelector(`#doc .para[data-id=${i}]`) || {}).textContent?.startsWith(s)", arg=["p6502", cpre], timeout=20000)
        check("미리보기 + 「지금 대표」 갈래 고르기 → 「대표로 정하고 고른 서식 1가지 맞추기」 → 대표 = 끌어 놓은 줄 · 옛 대표 줄 접두가 그 모양", txt.startswith("대표로 정하고 고른 서식 1가지 맞추기")
              and page.locator(f"{row} .olm-try").count() == 0, [txt, cand, cpre])
        page.click("#undoBtn")
        page.wait_for_function("() => heads.outline.templates['3'].slots['2'].rep === 'p6502'", timeout=20000)
        page.wait_for_function("() => /서식 3가지/.test((document.querySelector('#headsDlgBody .olm[data-tpl=\"3\"][data-level=\"2\"] .olm-sum') || {}).textContent || '')", timeout=20000)
        check("실행 취소 한 번 → 대표 · 갈래 모두 원래대로", True)

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

        # 서식 종속 템플릿(② §8-5) — 갈래 줄의 「다른 템플릿으로」 → 「T9L2a」(줄은 L2 부터) → 합치기. T9 「[기관] › o › -」 L2 「o」 = 대표 ×31 · ×9(p1703) · ×2 · ×1 · ×1
        row9 = '#headsDlgBody .olm[data-tpl="9"][data-level="2"]'
        page.evaluate("() => tplRelOpen(9, { tpl: '9', level: 2, para: 'p1703' })")
        page.wait_for_selector(f"{row9} .olm-g", timeout=20000)
        gi = page.evaluate("(r) => [...document.querySelector(r).querySelectorAll('.olm-g')].findIndex((x) => (x._paras || []).includes('p1703'))", row9)
        g = page.locator(row9).first.locator(".olm-g").nth(gi)
        check("대표 갈래에는 「다른 템플릿으로」 가 없고 다른 갈래에는 있다", gi > 0 and g.locator("button", has_text="다른 템플릿으로").count() == 1
              and page.locator(row9).first.locator(".olm-g.rep button", has_text="다른 템플릿으로").count() == 0, gi)
        g.locator("button", has_text="다른 템플릿으로").click()
        form = g.locator(".olm-splitf")
        opts, note = form.locator("select option").all_inner_texts(), form.locator(".olm-note").inner_text()
        check("「다른 템플릿으로」 → 그 아래 한 줄(팝업 아님): 「새 템플릿 T9L2a」 · 넣기 · 설명(줄은 L2 부터)", form.is_visible() and opts == ["새 템플릿 T9L2a"] and "T9L2a 를 만듭니다" in note and "9줄" in note
              and "줄은 L2 부터" in note and "L1 은 T9 의 레벨" in note, [opts, note])
        page.screenshot(path=str(OUT / "03b_split_form.png"))
        form.locator("button", has_text="넣기").click()
        page.wait_for_function("() => heads.outline && heads.outline.templates['9~2a'] && heads.outline.templates['9~2a'].no === '9L2a'", timeout=20000)
        page.wait_for_function("() => [...document.querySelectorAll('.tpl-mark')].some((m) => /^T9L2a L2/.test(m.textContent))", timeout=20000)
        page.wait_for_selector('#headsDlgBody li.trel-node[data-tpl="9~2a"]', timeout=20000)
        page.wait_for_function("(r) => /서식 4가지/.test((document.querySelector(r + ' .olm-sum') || {}).textContent || '')", arg=row9, timeout=20000)
        st = page.evaluate("""(r) => { const li = document.querySelector('#headsDlgBody li.trel-node[data-tpl="9~2a"]'), t = heads.outline.templates['9~2a'];
          return { base: t.base, vari: t.vari, lines: t.lines, row: li.querySelector('.trel-row').textContent, sub: !!li.querySelector(':scope > .trel-row .olm-sub'), shared: (li.querySelector('.olm-shared') || {}).textContent || '',
            chips: [...document.querySelector(r).querySelectorAll('.olm-vchip')].map((c) => c.textContent), t9: Object.values(heads.outline.lines).filter((x) => x.tpl === '9').length,
            tip: ([...document.querySelectorAll('.tpl-mark')].find((m) => /^T9L2a L2/.test(m.textContent)) || {}).title || '' }; }""", row9)
        check("넣기 → 서식 종속 템플릿 「T9L2a」(base 1 — 줄은 L2 부터) · 트리에 「서식 종속 — T9 L2 의 다른 서식 · 합치기」 · 「하위로」 없음 · 펴면 「L1 = T9 의 레벨」 · 문서 표 「T9L2a L2」",
              st["base"] == 1 and st["vari"]["ofNo"] == 9 and st["vari"]["level"] == 2 and "T9L2a" in st["row"] and "서식 종속 — T9 L2 의 다른 서식" in st["row"] and "합치기" in st["row"] and not st["sub"]
              and "L1 = T9 의 레벨" in st["shared"] and "L2 부터" in st["shared"] and "서식 종속 템플릿 — T9 L2 의 다른 서식" in st["tip"], st)
        check("T9 L2 줄에 「→ T9L2a(n줄)」 · 갈래 4가지로 줄어듦 · T9 줄 수가 그만큼 줄어듦", len(st["chips"]) == 1 and st["chips"][0] == f"→ T9L2a({st['lines']}줄)" and st["t9"] == 92 - st["lines"] and st["lines"] >= 9, st)
        page.screenshot(path=str(OUT / "03c_split.png"))
        page.locator(row9).first.locator("button.olm-unsplit").click()
        page.wait_for_function("() => heads.outline && !heads.outline.templates['9~2a']", timeout=20000)
        page.wait_for_function("(r) => /서식 5가지/.test((document.querySelector(r + ' .olm-sum') || {}).textContent || '')", arg=row9, timeout=20000)
        check("「합치기」 → 서식 종속 템플릿이 없어지고 줄이 T9 L2 로(갈래 5가지 · 표 「T9 L2」)", page.evaluate("() => Object.values(heads.outline.lines).filter((x) => x.tpl === '9').length") == 92
              and not page.evaluate("() => [...document.querySelectorAll('.tpl-mark')].some((m) => /^T9L2a/.test(m.textContent))"))

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

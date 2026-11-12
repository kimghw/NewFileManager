"""표 엑셀화 화면 연기 시험(spec_헤딩_추출 ② §14) — 서버가 떠 있어야 한다(LLM·PDF 끔 권장: NFM_LLM_BACKEND=off NFM_PDF=off, 작업 폴더는 임시로).

python -X utf8 tools/smoke_table_excel_ui.py [http://127.0.0.1:18231] [출력 폴더]
연구개발계획서 양식을 열고(3단계 없이) → 표지 표(「총 연구개발비」 가 든 표)의 ⊞ → 2열 격자: 수식 판정(총 현금 = 정부 + 기관 + 그 외 · 합계 열·행) ·
숫자 칸 · 범례 → 숫자 칸 셋에 값 → 총 현금 계산값 → 정렬 ↓ / 되돌리기 → 「엑셀로 받기」(.xlsx 수식·채움 확인) → 문서에서 칸 끌어 고르기 → ⊞ → 범위 격자 →
오른쪽 단추 메뉴 항목 → 콘솔 오류. 그림은 출력 폴더에."""
import io
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18231"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "artifacts" / "ui_table_excel")
OUT.mkdir(parents=True, exist_ok=True)
SAMPLE = "연구개발계획서_양식.hwpx"
FAILS = []


def check(ok, what):
    print(("  ok  " if ok else "  FAIL") + " " + what)
    if not ok:
        FAILS.append(what)


def wait_server(timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if requests.get(URL + "/api/headings/llm", timeout=2).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise SystemExit("서버가 안 뜸")


def cell_ref(page, text_part):
    """2열 격자에서 title 에 text_part 가 든 첫 수식 칸의 주소."""
    return page.evaluate("""(t) => { const td = [...document.querySelectorAll('.heads-col .xl-wrap.col td.fx')].find((x) => (x.title || '').includes(t)); return td ? td.dataset.ref : null; }""", text_part)


def grid_type(page, ref, value):
    page.locator(f'.heads-col .xl-wrap.col td[data-ref="{ref}"]').dblclick()
    inp = page.locator(".heads-col .xl-wrap.col input.xl-edit")
    inp.fill(value)
    inp.press("Enter")
    page.wait_for_timeout(150)


def main():
    wait_server()
    logs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1700, "height": 1000}, device_scale_factor=1, accept_downloads=True)
        page = ctx.new_page()
        page.set_default_timeout(120000)
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}") if m.type in ("error",) else None)
        page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(URL)
        page.wait_for_selector(".sample", state="attached")
        page.evaluate("() => { const s = document.getElementById('sampleSection'); if (s) { s.hidden = false; s.open = true; } }")
        page.evaluate(f"() => document.querySelector('.sample[aria-label=\"예제 {SAMPLE} 열기\"]').click()")
        page.wait_for_function("document.querySelector('.sheet .para') != null", timeout=240000)
        page.wait_for_timeout(1500)
        doc = page.evaluate("location.hash").split("=", 1)[1]
        tid = page.evaluate("""() => { const t = [...document.querySelectorAll('#doc table.tbl[data-tbl]')].find((x) => x.textContent.includes('총 연구개발비')); return t ? t.dataset.tbl : null; }""")
        print("doc", doc, "table", tid)
        check(bool(tid), "표지 표(총 연구개발비) 찾음")
        # ---- ⊞ → 2열 격자(3단계 없이 판정)
        page.wait_for_selector(f'.tbl-mark[data-for="{tid}"]', state="attached")
        page.evaluate(f"() => document.querySelector('.tbl-mark[data-for=\"{tid}\"] .tm-btn.xl').click()")
        page.wait_for_selector(".heads-col .xl-wrap.col td.fx", timeout=60000)
        page.wait_for_timeout(500)
        n_fx = page.locator(".heads-col .xl-wrap.col td.fx").count()
        n_inp = page.locator(".heads-col .xl-wrap.col td.inp").count()
        bar = page.locator(".heads-col .xl-wrap.col .xl-bar").inner_text()
        foot = page.locator(".heads-col .xl-wrap.col .xl-foot").inner_text()
        print("   fx", n_fx, "inp", n_inp, "| bar:", " ".join(bar.split())[:160], "| foot:", " ".join(foot.split())[:200])
        check(n_fx >= 20, f"수식 칸 20개 이상(지금 {n_fx}) — 3단계 없이 판정")
        st = page.evaluate("() => { const m = document.querySelector('.heads-col .xl-wrap.col')._model; return {err: [...m.status].filter(([k, v]) => v === 'err').length, pend: xlPending(document.querySelector('.heads-col .xl-wrap.col')).length}; }")
        check(st["err"] == 0 and st["pend"] == 0, f"빈 양식 — 수식 오류 0 · 반영할 것 0(자리표시 = 빈 값) {st}")
        check(n_inp >= 20, f"숫자 칸 20개 이상(지금 {n_inp})")
        check("수식 자리 판정" in bar and "숫자 칸" in foot and "원문과 다름" in foot, "판정 표시·범례")
        t_ref = cell_ref(page, "총 연구개발비 = 정부지원")
        check(bool(t_ref), f"총 현금 칸 수식(총 연구개발비 = 정부지원 + …) — {t_ref}")
        page.locator(".heads-col .xl-wrap.col").screenshot(path=str(OUT / "01_grid.png"))
        if t_ref:
            f = page.evaluate(f"() => document.querySelector('.heads-col .xl-wrap.col')._model.formulas.get('{t_ref}')")
            print("   ", t_ref, f)
            ops = [x for x in f.lstrip("=").split("+")]
            check(len(ops) == 3, f"총 현금 = 피연산자 셋(정부 · 기관 · 그 외) — {f}")
            for ref, val in zip(ops, ("100", "200", "300")):
                grid_type(page, ref, val)
            shown = page.locator(f'.heads-col .xl-wrap.col td[data-ref="{t_ref}"]').inner_text()
            check(shown.replace(",", "") == "600", f"총 현금 계산값 600(지금 {shown})")
            # 정렬 — 같은 열의 다른 해 칸에 값을 넣고 내림차순
            r0 = int("".join(ch for ch in ops[0] if ch.isdigit()))
            col = "".join(ch for ch in ops[0] if ch.isalpha())
            grid_type(page, f"{col}{r0 + 1}", "900")
            page.locator(f'.heads-col .xl-wrap.col td[data-ref="{col}{r0}"]').click()
            page.get_by_role("button", name="정렬 ↓").click()
            page.wait_for_timeout(300)
            top = page.locator(f'.heads-col .xl-wrap.col td[data-ref="{col}{r0}"]').inner_text()
            check(top.replace(",", "") == "900", f"내림차순 뒤 {col}{r0} = 900(지금 {top})")
            undo = page.get_by_role("button", name="정렬 되돌리기")
            check(undo.is_visible(), "정렬 되돌리기 단추 보임")
            page.locator(".heads-col .xl-wrap.col").screenshot(path=str(OUT / "02_sorted.png"))
            undo.click()
            page.wait_for_timeout(200)
            top = page.locator(f'.heads-col .xl-wrap.col td[data-ref="{col}{r0}"]').inner_text()
            check(top.replace(",", "") == "100", f"되돌린 뒤 {col}{r0} = 100(지금 {top})")
            # 헤더 칸으로 정렬 → 거절
            hdr = page.evaluate("() => { const td = document.querySelector('.heads-col .xl-wrap.col td.colhead'); return td ? td.dataset.ref : null; }")
            if hdr:
                page.locator(f'.heads-col .xl-wrap.col td[data-ref="{hdr}"]').click()
                page.get_by_role("button", name="정렬 ↑").click()
                page.wait_for_timeout(200)
        # ---- 엑셀로 받기
        with page.expect_download() as dl:
            page.get_by_role("button", name="엑셀로 받기").click()
        path = OUT / dl.value.suggested_filename
        dl.value.save_as(str(path))
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(path.read_bytes()))
        ws = wb["표"]
        fcells = [c for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=")]
        yellow = [c for row in ws.iter_rows() for c in row if c.fill and c.fill.fgColor and str(c.fill.fgColor.rgb).endswith("FFF2CC")]
        print("   xlsx", path.name, "formulas", len(fcells), "input fill", len(yellow), "sheets", wb.sheetnames)
        check(len(fcells) >= 20 and len(yellow) >= 10 and "수식" in wb.sheetnames, "엑셀 파일 — 수식·숫자 칸 채움·「수식」 시트")
        if t_ref:
            check(str(ws[t_ref].value).startswith("="), f"엑셀 {t_ref} 가 수식({ws[t_ref].value})")
        # ---- 문서에서 칸 끌어 고르기 → ⊞ → 범위 격자
        page.click("#headsDlg .x, #headsDlg [aria-label='닫기']", timeout=5000) if page.locator("#headsDlg .x, #headsDlg [aria-label='닫기']").count() else None
        cells = page.evaluate(f"""() => {{
          const t = document.querySelector('#doc table.tbl[data-tbl="{tid}"]');
          const tds = [...t.querySelectorAll(':scope > tbody > tr > td')];
          const a = tds.find((x) => x.textContent.includes('총 연구개발비'));
          const z = tds.filter((x) => x.textContent.trim() === '합계').pop();
          const box = (td) => {{ td.scrollIntoView({{block: 'center'}}); const r = td.getBoundingClientRect(); return {{x: r.left + r.width / 2, y: r.top + r.height / 2, r: +td.dataset.r, c: +td.dataset.c}}; }};
          return a && z ? [box(a), box(z)] : null; }}""")
        check(bool(cells), "문서 표의 「총 연구개발비」·「합계」 칸")
        if cells:
            a, z = page.evaluate(f"""() => {{
              const t = document.querySelector('#doc table.tbl[data-tbl="{tid}"]');
              const tds = [...t.querySelectorAll(':scope > tbody > tr > td')];
              const a = tds.find((x) => x.textContent.includes('연구개발비15') || x.textContent.includes('연구개발비 15') || (x.textContent.includes('연구개발비') && x.textContent.includes('단위')));
              const z = tds.filter((x) => x.textContent.trim() === '합계').pop();
              a.scrollIntoView({{block: 'start'}});
              const box = (td) => {{ const r = td.getBoundingClientRect(); return {{x: r.left + Math.min(20, r.width / 2), y: r.top + r.height / 2}}; }};
              const zz = [...t.querySelectorAll(':scope > tbody > tr > td')].filter((x) => +x.dataset.r === +z.dataset.r).pop();
              return [box(a), box(zz)]; }}""")
            page.mouse.move(a["x"], a["y"])
            page.mouse.down()
            page.mouse.move((a["x"] + z["x"]) / 2, (a["y"] + z["y"]) / 2, steps=6)
            page.mouse.move(z["x"], z["y"], steps=6)
            page.mouse.up()
            page.wait_for_timeout(300)
            rect = page.evaluate("() => (typeof tsel !== 'undefined' && tsel.rect) ? {...tsel.rect, n: tsel.cells.length} : null")
            print("   tsel", rect)
            check(bool(rect) and rect["n"] > 10, "칸 묶음 고름")
            page.evaluate(f"() => document.querySelector('.tbl-mark[data-for=\"{tid}\"]').scrollIntoView({{block: 'center'}})")
            btn = page.locator(f'.tbl-mark[data-for="{tid}"] .tm-btn.xl')
            btn.click()
            page.wait_for_function("() => { const w = document.querySelector('.heads-col .xl-wrap.col'); return w && w._model && w._model.range; }", timeout=60000)
            page.wait_for_timeout(400)
            info = page.evaluate("() => { const m = document.querySelector('.heads-col .xl-wrap.col')._model; return {range: m.range, rows: document.querySelectorAll('.heads-col .xl-wrap.col tbody tr').length, fx: document.querySelectorAll('.heads-col .xl-wrap.col td.fx').length, scope: m.judge && m.judge.scope}; }")
            print("   range view", info)
            check(info["range"] and info["rows"] == rect["r1"] - rect["r0"] + 1, "범위만 격자(행 수 = 고른 행 수)")
            check(info["fx"] >= 15 and info["scope"] == "range", f"범위만으로 판정한 수식(지금 {info['fx']}, {info['scope']})")
            page.locator(".heads-col .xl-wrap.col").screenshot(path=str(OUT / "03_range.png"))
            # 오른쪽 단추 메뉴 항목 — 그 칸을 다시 화면 가운데로(스크롤이 끝난 뒤 열어야 메뉴가 안 닫힌다)
            pt = page.evaluate(f"""() => {{ const t = document.querySelector('#doc table.tbl[data-tbl="{tid}"]');
              const td = [...t.querySelectorAll(':scope > tbody > tr > td')].find((x) => x.textContent.includes('총 연구개발비'));
              td.scrollIntoView({{block: 'center'}}); return true; }}""")
            page.wait_for_timeout(1500)
            pt = page.evaluate(f"""() => {{ const t = document.querySelector('#doc table.tbl[data-tbl="{tid}"]');
              const td = [...t.querySelectorAll(':scope > tbody > tr > td')].find((x) => x.textContent.includes('총 연구개발비'));
              const r = td.getBoundingClientRect(); return {{x: r.left + 10, y: r.top + r.height / 2}}; }}""")
            page.mouse.click(pt["x"], pt["y"], button="right")
            page.wait_for_timeout(500)
            menu = page.locator(".ctx-menu").inner_text() if page.locator(".ctx-menu").count() else ""
            check("엑셀식 보기" in menu, "오른쪽 단추 메뉴에 「엑셀식 보기 — 수식 판정」")
            page.keyboard.press("Escape")
        page.screenshot(path=str(OUT / "04_page.png"))
        errs = [x for x in logs if "favicon" not in x]
        check(not errs, f"콘솔 오류 0 ({len(errs)})")
        for x in errs[:10]:
            print("   ", x)
        b.close()
    print("FAILS", len(FAILS), FAILS)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())

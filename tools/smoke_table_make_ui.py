"""표 만들기 · 서식 변환 화면 연기 시험(spec_헤딩_추출 ② §11) — 서버가 떠 있어야 한다(LLM·PDF 끔 권장: NFM_LLM_BACKEND=off NFM_PDF=off).

python -X utf8 tools/smoke_table_make_ui.py [http://127.0.0.1:18192] [출력 폴더] [--rnd]
기술수요조사서.hwpx 를 열고 → 「표」 탭 「표 만들기 · 서식 변환」 → 표 양식 고르기(구역 수 자동) → 붙여 넣기(탭 구분 글) 「그대로 표로」 → 미리보기 격자 →
커서가 있는 표 뒤에 넣기 → HTML 표 붙여 넣기(칸 합치기) → 문서의 표 「서식 입히기」·「새 표로 바꾸기」 → 표 칸 오른쪽 단추 메뉴 → 실행 취소 → 2열 폭 넘침·콘솔 오류.
--rnd 면 연구개발계획서 양식에서 본문 문단을 끌어 고른 뒤 오른쪽 단추 「고른 글로 표 만들기…」 까지(LLM 이 꺼져 있으면 원본 표시까지만). 그림은 출력 폴더에."""
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
URL = ARGS[0] if ARGS else "http://127.0.0.1:18192"
OUT = Path(ARGS[1] if len(ARGS) > 1 else Path(__file__).resolve().parents[1] / "artifacts" / "ui_table_make")
OUT.mkdir(parents=True, exist_ok=True)
RND = "--rnd" in sys.argv
checks = []


def ok(name, cond, detail=""):
    checks.append((name, bool(cond), detail))
    print(("  ok  " if cond else "  FAIL") + f" {name}" + (f" — {detail}" if detail and not cond else ""))


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


def open_sample(page, name, timeout=240000):
    page.goto(URL)
    page.wait_for_selector(".sample", state="attached")
    if not page.locator("#sampleSection").evaluate("d => d.open"):
        page.click("#sampleSection summary")
    page.click(f'.sample[aria-label="예제 {name} 열기"]')
    page.wait_for_function("document.querySelector('.sheet .para') != null", timeout=timeout)
    page.wait_for_timeout(600)


def tables(page):
    return page.evaluate("xlBlocks().map(b => ({id: b.id, rows: b.rows, cols: b.cols, depth: b.depth}))")


def small(page, logs):
    open_sample(page, "기술수요조사서.hwpx")
    tbs = tables(page)
    big = max(tbs, key=lambda b: b["rows"])
    page.click("#tabTables")
    page.wait_for_selector("#tablesBox button:has-text('표 만들기 · 서식 변환')")
    page.click("#tablesBox button:has-text('표 만들기 · 서식 변환')")
    page.wait_for_selector(".tm-wrap")
    ok("2열이 열림(kind tableMake)", page.evaluate("heads.dlg") == "tableMake")
    page.select_option(".tm-wrap select", big["id"])
    page.wait_for_selector(".tm-wrap .tm-num input")
    roles = page.evaluate("tmk.tplRoles")
    ok("표 양식 구역 수 자동 판정", roles and set(roles) == {"headerRows", "headerCols", "footRows"}, str(roles))
    ok("고른 양식을 브라우저에 기억", page.evaluate("JSON.parse(localStorage.getItem('nfm.tblMake'))[state.id].tpl") == big["id"])
    ok("LLM 꺼짐이면 정리 단추 꺼짐", page.locator(".tm-wrap button:has-text('LLM 으로 표 정리')").is_disabled())

    # 붙여 넣기(탭 구분 글) → 그대로 표로
    page.click(".tm-kinds label:has-text('붙여 넣기')")
    page.fill("#tmkPaste", "구분\t1차년도\t2차년도\n현금\t1,000\t2,000\n현물\t500\t700\n합계\t1,500\t2,700\n")
    ok("표 꼴 글 안내", "그대로 표로" in page.inner_text(".tm-wrap #tmkPaste + p"))
    page.click(".tm-wrap button:has-text('그대로 표로')")
    page.wait_for_selector("table.tm-grid td")
    grid = page.evaluate("({n: document.querySelectorAll('table.tm-grid td').length, head: document.querySelectorAll('table.tm-grid td.head').length, "
                         "foot: document.querySelectorAll('table.tm-grid td.foot').length, mode: tmk.mode, check: tmk.check})")
    ok("미리보기 격자 4×3 · 머리 1행 · 합계 1행", grid["n"] == 12 and grid["head"] == 3 and grid["foot"] == 3 and grid["mode"] == "asis", str(grid))
    ok("검산 — 빠진·보탠 글 없음", not grid["check"]["lost"] and not grid["check"]["added"])
    page.screenshot(path=str(OUT / "1_preview.png"))

    # 미리보기 칸 글 고치기 · 구역 수 고치기
    page.locator("table.tm-grid td").nth(4).click()
    page.keyboard.press("Control+A")
    page.keyboard.type("1,234")
    ok("칸 글 고침이 격자에 반영", page.evaluate("tmk.grid.rows[1].cells[1].text") == "1,234")
    hc = page.locator(".tm-wrap .ta-row:has(.tm-num) >> nth=1").locator("input").nth(1)
    hc.fill("1")
    hc.dispatch_event("change")
    ok("머리열 수를 고치면 색이 바뀜", page.evaluate("document.querySelectorAll('table.tm-grid td.hcol').length") == 2)

    # 넣을 자리 — 커서 문단(표 칸 안) → 커서가 있는 표 뒤에
    before = len(tables(page))
    page.locator(f'#doc table.tbl[data-tbl="{big["id"]}"] .para').first.click()
    page.wait_for_function("document.getElementById('tmkCaret') && document.getElementById('tmkCaret').textContent.includes('표 칸 안')", timeout=5000)
    page.click(".tm-place label:has-text('뒤에 넣기') >> nth=1")
    page.click(".tm-wrap button:has-text('문서에 넣기')")
    page.wait_for_function(f"xlBlocks().length === {before + 1}", timeout=90000)
    new = [b for b in tables(page) if b["id"] not in {t["id"] for t in tbs}][0]
    cells = page.evaluate(f"[...document.querySelectorAll('#doc table.tbl[data-tbl=\"{new['id']}\"] td')].map(td => td.innerText.trim())")
    ok("문서에 새 표 4×3", new["rows"] == 4 and new["cols"] == 3 and cells[:3] == ["구분", "1차년도", "2차년도"] and "1,234" in cells, str(cells[:6]))
    ok("새 표는 최상위(칸 안 표 아님)", new["depth"] == 1)
    ok("실행 취소 1개", page.evaluate("state.undo") == 1)
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "2_inserted.png"))

    # HTML 표 붙여 넣기(칸 합치기)
    page.evaluate("""() => {
      const ta = document.getElementById('tmkPaste');
      const dt = new DataTransfer();
      dt.setData('text/html', '<table><tr><th rowspan="2">구분</th><th colspan="2">연도</th></tr><tr><th>1차</th><th>2차</th></tr><tr><td>현금</td><td>1<br>2</td><td>3</td></tr></table>');
      dt.setData('text/plain', 'x');
      ta.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
    }""")
    pg = page.evaluate("tmk.pasteGrid && {rows: tmk.pasteGrid.rows.length, first: tmk.pasteGrid.rows[0].cells, text: tmk.paste}")
    ok("HTML 표를 칸 합치기째 읽음", pg and pg["rows"] == 3 and pg["first"][0]["rowSpan"] == 2 and pg["first"][1]["colSpan"] == 2, str(pg))
    ok("표로 읽음 안내", "표로 읽음" in page.inner_text(".tm-wrap #tmkPaste + p"))
    page.click(".tm-wrap button:has-text('그대로 표로')")
    page.wait_for_function("tmk.grid && tmk.grid.rows.length === 3 && !tmk.busy")
    spans = page.evaluate("[...document.querySelectorAll('table.tm-grid td')].map(td => [td.rowSpan, td.colSpan, td.innerText])")
    ok("미리보기에 합친 칸 · 머리 2행", spans[0][0] == 2 and spans[1][1] == 2 and page.evaluate("tmk.grid.headerRows") >= 1, str(spans[:3]))

    # 문서의 표 — 서식 입히기 · 새 표로 바꾸기
    page.click(".tm-kinds label:has-text('문서의 표')")
    page.locator(".tm-wrap select").nth(1).select_option(new["id"])
    page.click(".tm-wrap button:has-text('그대로 표로')")
    page.wait_for_function("tmk.grid && tmk.gridFor === 't:' + tmk.table && !tmk.busy")
    ok("문서의 표 기본 자리 = 서식만 입히기", page.evaluate("tmk.place.table") == "restyle" and page.locator(".tm-wrap button:has-text('서식 입히기')").count() == 1)
    page.click(".tm-wrap button:has-text('서식 입히기')")
    page.wait_for_function("state.undo === 2", timeout=90000)
    ok("서식 입히기 뒤 표·글 그대로", len(tables(page)) == before + 1
       and page.evaluate(f"document.querySelector('#doc table.tbl[data-tbl=\"{new['id']}\"] td').innerText.trim()") == "구분")
    page.click(".tm-place label:has-text('새 표로 바꾸기')")
    page.click(".tm-wrap button:has-text('문서에 넣기')")
    page.wait_for_function("state.undo === 3", timeout=90000)
    now = tables(page)
    ok("새 표로 바꾸기 — 옛 표는 없고 새 표가 원본이 됨", new["id"] not in {b["id"] for b in now} and len(now) == before + 1 and page.evaluate("tmk.table") in {b["id"] for b in now})

    # 표 칸 오른쪽 단추 메뉴(넣은 표로 부드럽게 스크롤하는 동안엔 메뉴가 닫히므로 멈춘 뒤에)
    page.wait_for_timeout(1500)
    page.locator(f'#doc table.tbl[data-tbl="{big["id"]}"] td').first.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    page.locator(f'#doc table.tbl[data-tbl="{big["id"]}"] td').first.click(button="right")
    page.wait_for_selector(".ctx-menu:not([hidden])")
    menu = page.inner_text(".ctx-menu")
    ok("표 칸 메뉴 항목", "이 표를 표 양식으로" in menu and "이 표를 양식 서식으로 변환…" in menu, menu)
    page.click(".ctx-menu button:has-text('이 표를 양식 서식으로 변환…')")
    ok("메뉴로 열면 원본 = 그 표", page.evaluate("tmk.kind === 'table' && tmk.table") in {b["id"] for b in now})

    # 2열 폭 넘침(480px)
    page.set_viewport_size({"width": 1180, "height": 900})
    page.wait_for_timeout(400)
    over = page.evaluate("(() => { const w = document.querySelector('.tm-wrap'); return [w.scrollWidth, w.clientWidth, document.getElementById('headsDlg').offsetWidth]; })()")
    ok("좁은 2열에서 가로 넘침 없음", over[0] <= over[1] + 1, str(over))
    page.screenshot(path=str(OUT / "3_narrow.png"))
    page.set_viewport_size({"width": 1600, "height": 950})

    # 실행 취소 3번 → 원래대로
    for want in (2, 1, 0):
        page.evaluate("undoStruct()")
        page.wait_for_function(f"state.undo === {want} && !state.busy", timeout=90000)
    ok("실행 취소 뒤 표 수·원본 바이트", len(tables(page)) == before - 0 and page.evaluate("state.pristine") is True, str(len(tables(page))))
    ok("콘솔 오류 없음(작은 문서)", not logs, "\n".join(logs[:5]))


def rnd(page, logs):
    n0 = len(logs)
    open_sample(page, "연구개발계획서_양식.hwpx")
    ids = page.evaluate("""() => {
      const ps = [...document.querySelectorAll('#doc .para[data-id]')].filter(p => !p.closest('td'));
      for (let i = 40; i + 2 < ps.length; i += 1) {  // 표지·목차를 지나 본문에서
        const a = ps[i], b = ps[i + 1], c = ps[i + 2];
        if ([a, b, c].every(p => p.innerText.trim().length > 8 && !p.innerText.includes('\\t')) && a.nextElementSibling === b && b.nextElementSibling === c) return [a.dataset.id, b.dataset.id, c.dataset.id];  // 탭이 든 줄(목차)은 표 꼴 글로 읽히므로 피한다
      }
      return null;
    }""")
    ok("본문에 잇단 문단 셋", bool(ids))
    if not ids:
        return

    def rects():
        return page.evaluate("(ids) => ids.map(id => { const r = paraEl(id).getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })", ids)
    page.evaluate("(id) => paraEl(id).scrollIntoView({block: 'center'})", ids[0])
    page.wait_for_timeout(500)
    a, _, c = rects()
    # 글 선택은 한 문단을 못 넘는다 — 끌어 다른 문단에 닿으면 문단 묶음
    page.mouse.move(a[0] + 40, a[1] + a[3] / 2)
    page.mouse.down()
    page.mouse.move(a[0] + 80, a[1] + a[3] / 2, steps=3)
    ok("같은 문단 안에서 끌면 글 선택 그대로", page.evaluate("tpk.ids.length") == 0)
    page.mouse.move(c[0] + 80, c[1] + c[3] / 2, steps=10)
    page.mouse.up()
    ok("끌어 다른 문단에 닿으면 문단 묶음", page.evaluate("tpk.ids") == ids, str(page.evaluate("tpk.ids")))
    ok("묶음 표시(규칙)", "p" in page.evaluate("document.getElementById('tmkPickCss').textContent")
       and page.evaluate("(id) => getComputedStyle(paraEl(id)).backgroundColor", ids[1]) != "rgba(0, 0, 0, 0)")
    page.keyboard.press("Escape")
    ok("Esc 로 풂", page.evaluate("tpk.ids.length") == 0)
    page.mouse.click(a[0] + 40, a[1] + a[3] / 2)
    page.keyboard.down("Shift")
    page.mouse.click(c[0] + 80, c[1] + c[3] / 2)
    page.keyboard.up("Shift")
    ok("Shift+누름 = 커서 문단부터", page.evaluate("tpk.ids") == ids, str(page.evaluate("tpk.ids")))
    page.mouse.click(c[0] + 40, c[1] + c[3] / 2, button="right")
    page.wait_for_selector(".ctx-menu:not([hidden])")
    menu = page.inner_text(".ctx-menu")
    ok("문단 메뉴에 「고른 글(문단 3개)로 표 만들기…」", "고른 글(문단 3개)로 표 만들기…" in menu, menu)
    page.click(".ctx-menu button:has-text('표 만들기…')")
    page.wait_for_selector(".tm-wrap .tm-src", timeout=120000)
    ok("원본 = 고른 글 3문단", page.evaluate("tmk.kind") == "paras" and page.evaluate("tmk.paras") == ids, page.inner_text(".tm-wrap .tm-src"))
    ok("2열이 열려 있는 동안 원본 문단 표시", page.evaluate("(id) => getComputedStyle(paraEl(id)).backgroundColor", ids[0]) != "rgba(0, 0, 0, 0)")
    # 표 양식 = 머리행이 있는 4행 3열 이상 표 · 격자는 넣어 준다(LLM 꺼짐) → 고른 글을 표로 바꾸기
    tpl = page.evaluate("""() => { for (const b of xlBlocks()) { if (b.depth === 1 && b.rows >= 4 && b.cols >= 3 && b.rows <= 12) return b.id; } return xlBlocks()[0].id; }""")
    page.select_option(".tm-wrap select", tpl)
    page.wait_for_selector(".tm-wrap .tm-num input", timeout=60000)
    page.click(".tm-wrap button:has-text('그대로 표로')")
    page.wait_for_function("!tmk.busy && !!tmk.msg", timeout=60000)
    ok("글은 「그대로 표로」 가 안 됨(안내)", "LLM" in page.evaluate("tmk.msg"), page.evaluate("tmk.msg"))
    n_before = len(tables(page))
    page.evaluate("""() => { tmk.grid = {rows: [{cells: [{text: '항목', rowSpan: 1, colSpan: 1}, {text: '내용', rowSpan: 1, colSpan: 1}]},
        {cells: [{text: '가', rowSpan: 1, colSpan: 1}, {text: '첫째', rowSpan: 1, colSpan: 1}]}, {cells: [{text: '나', rowSpan: 1, colSpan: 1}, {text: '둘째', rowSpan: 1, colSpan: 1}]}],
        headerRows: 1, headerCols: 0, footRows: 0}; tmk.gridFor = tmkSourceKey(); tmk.mode = 'compose'; tmk.msg = ''; tmkDraw(); }""")
    page.click(".tm-place label:has-text('고른 글을 표로 바꾸기')")
    page.click(".tm-wrap button:has-text('문서에 넣기')")
    page.wait_for_function(f"xlBlocks().length === {n_before + 1} && !state.busy", timeout=180000)
    ok("고른 글이 표로 바뀜", page.evaluate("(ids) => ids.every(id => !paraEl(id))", ids) and page.evaluate("tmk.paras.length") == 0)
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / "4_rnd_replaced.png"))
    page.evaluate("undoStruct()")
    page.wait_for_function("state.undo === 0 && !state.busy", timeout=180000)
    ok("실행 취소로 문단이 돌아옴", page.evaluate("(ids) => ids.every(id => !!paraEl(id))", ids) and len(tables(page)) == n_before)
    extra = [x for x in logs[n0:] if "status of 400" not in x]  # 「그대로 표로」 의 400(글은 못 옮김)은 기대한 응답 — 브라우저가 콘솔에 남긴다
    ok("콘솔 오류 없음(큰 문서)", not extra, "\n".join(extra[:5]))
    del logs[n0:]


def main():
    wait_server()
    logs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1600, "height": 950}, device_scale_factor=1)
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        try:
            small(page, logs)
            if RND:
                rnd(page, logs)
        finally:
            page.screenshot(path=str(OUT / "9_last.png"))
            b.close()
    bad = [c for c in checks if not c[1]]
    print(f"\n{len(checks) - len(bad)}/{len(checks)} 통과" + ("" if not bad else " — 실패: " + ", ".join(c[0] for c in bad)))
    if logs:
        print("콘솔:", *logs[:10], sep="\n  ")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

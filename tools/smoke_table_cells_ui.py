"""표 편집 확장(spec_owpml_편집 ② §5 — 칸 메뉴 · 미리보기 · 고른 칸만 넣기 · M/S 키 · 헤더 지정 · 표 나누기 · 넘침 나눔이 합친 칸을 건너 자르기) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_table_cells_ui.py <그림·임시 폴더> [--port 18181]

연구개발계획서_양식.hwpx 를 새 작업으로 열고 → 왼쪽에 여러 행에 걸친 묶음 제목이 있는 표에서 필드 칸 둘을 끌어 고름 → 오른쪽 단추 메뉴(분류 줄 · 항목) →
「고른 칸만 아래에 넣기」 미리보기(새 칸이 들어갈 변 · 늘어나는 칸) → 실행(행 +1 · 묶음 제목 rowSpan +1) → 「열 지우기」 미리보기(지워질 칸 · 폭이 바뀌는 필드 열) →
M = 합치기 · S = 나누기 목록 → 「칸 크기 그대로」 → 헤더 지정(귀퉁이 표시) → 표 나누기(둘로 · 다시 나누기 · 다시 합치기) →
고른 칸을 되풀이해 넣어 쪽 상자가 넘치면 병합 칸을 건너 조각 상자로 넘어가는지(.sheet.over · td.cell-cont) · 콘솔 오류."""
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
sys.path.insert(0, str(ROOT))
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18181)
args = ap.parse_args()
OUT = Path(args.out).resolve()
PLAN = "연구개발계획서_양식.hwpx"

from app import table_heads as TH  # noqa: E402
from app.hwpx_doc import HP, HwpxDoc  # noqa: E402

# ---- 시험할 표를 문서에서 고른다(블록 id 는 문서 차례라 서버가 연 문서와 같다)
doc = HwpxDoc((ROOT / "samples" / PLAN).read_bytes())
doc.blocks()
TBL = f"{{{HP}}}tbl"


def pick_group():
    """왼쪽 0열에 8행 이상 걸친 묶음 제목이 있고, 그 안의 한 행에서 필드 열(헤더 열 뒤) 칸이 모두 1×1 인 표 → (표 id, 행, 첫 필드 열, 마지막 열, 묶음 제목 칸 id, 헤더 열 수)."""
    for sec in doc._sections:
        for tbl in sec.iter(TBL):
            tid = doc._rev.get(tbl)
            if tid is None:
                continue
            _t, cells, nr, nc = doc._tgrid(tbl)
            g = next((x for x in cells if x.c == 0 and x.rs >= 8), None)
            if g is None or nc < 6:
                continue
            lay = TH.layout(doc, tid)
            hc = lay["headCols"]
            if not 0 < hc < nc - 2:
                continue
            for r in range(g.r + 1, g.r + g.rs - 1):
                row = [x for x in cells if x.r == r and x.c >= hc]
                if len(row) == nc - hc and all(x.rs == 1 and x.cs == 1 for x in row):
                    return tid, r, hc, nc - 1, doc._id(g.el), hc
    raise SystemExit("묶음 제목이 있는 표를 못 찾음")


def pick_units():
    """헤더 열 + 한 열짜리 필드 열 단위 4개 이상인 작은 표(행 6 이하) → (표 id, 헤더 열 수, 단위 수, 열 수)."""
    for sec in doc._sections:
        for tbl in sec.iter(TBL):
            tid = doc._rev.get(tbl)
            if tid is None or int(tbl.get("rowCnt")) > 6 or int(tbl.get("rowCnt")) * int(tbl.get("colCnt")) < 6:
                continue
            lay = TH.layout(doc, tid)
            if lay["headCols"] >= 1 and len(lay["units"]) >= 4 and all(a == b for a, b in lay["units"]) and all(lay["fieldCols"][lay["headCols"]:]):
                return tid, lay["headCols"], len(lay["units"]), lay["cols"]
    raise SystemExit("나눌 표를 못 찾음")


G_TID, G_ROW, G_C0, G_C1, G_HEAD, G_HC = pick_group()
U_TID, U_HC, U_N, U_NC = pick_units()
print(f"묶음 표 {G_TID} 행 {G_ROW} 열 {G_C0}..{G_C1} 묶음 제목 {G_HEAD} · 나눌 표 {U_TID} 헤더 열 {U_HC} 단위 {U_N}", flush=True)

OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:500] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def open_sample(page, name, timeout=300000):
    page.evaluate("() => { const s = document.getElementById('sampleSection'); s.hidden = false; s.open = true; }")
    page.evaluate("(n) => document.querySelector(`.sample[aria-label=\"예제 ${n} 열기\"]`).click()", name)
    page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=timeout)


def td(tid, r, c):
    return f"#doc table.tbl[data-tbl='{tid}'] td[data-r='{r}'][data-c='{c}']:not(.cell-cont)"


def center(page, sel):
    page.locator(sel).first.scroll_into_view_if_needed()
    b = page.locator(sel).first.bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def drag(page, a, b):
    """칸 a 에서 칸 b 까지 끌어 칸 묶음을 고른다."""
    x0, y0 = center(page, a)
    page.mouse.move(x0, y0)
    page.mouse.down()
    x1, y1 = center(page, b)
    page.mouse.move((x0 + x1) / 2, (y0 + y1) / 2, steps=4)
    page.mouse.move(x1, y1, steps=4)
    page.mouse.up()


def menu(page, by="tsel"):
    return page.evaluate("""(by) => { const m = document.querySelector('.ctx-menu'); if (!m || m.hidden || m.dataset.by !== by) return null;
        return [...m.querySelectorAll('button')].map((b) => ({text: b.textContent, disabled: b.disabled, cls: b.className})); }""", by)


def item(page, text, by="tsel"):
    return page.locator(f".ctx-menu[data-by='{by}'] button:has-text('{text}')").first


def rclick(page, sel):
    x, y = center(page, sel)
    page.mouse.click(x, y, button="right")
    page.wait_for_selector(".ctx-menu[data-by='tsel']:not([hidden])")


def idle(page, timeout=120000):
    page.wait_for_function("() => !state.busy", timeout=timeout)


def tprev(page):
    return page.evaluate("""() => { const out = {}; for (const td of document.querySelectorAll('#doc td.tp')) for (const c of td.classList) if (c.startsWith('tp-')) out[c] = (out[c] || 0) + 1; return out; }""")


def block(page, tid):
    return page.evaluate("(t) => { const b = xlBlock(t); return b ? {rows: b.nRows, cols: b.nCols, cells: b.cells.length} : null; }", tid)


def span(page, cid):
    return page.evaluate("(c) => { for (const b of state.blocks) if (b.type === 'table') { const x = b.cells.find((y) => y.id === c); if (x) return x.rowSpan; } return null; }", cid)


try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        page = br.new_page(viewport={"width": 1600, "height": 950})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        page.goto(base)
        open_sample(page, PLAN)
        page.wait_for_function("() => typeof tselMenu === 'function' && typeof tsplitMenu === 'function' && state.blocks && state.blocks.length > 100", timeout=120000)
        page.wait_for_timeout(1500)
        b0 = block(page, G_TID)
        check("묶음 표가 문서에 있다", b0 is not None and b0["rows"] > G_ROW, b0)
        rs0 = span(page, G_HEAD)

        # 1) 칸 둘 끌어 고름 → 메뉴
        a, b = td(G_TID, G_ROW, G_C0), td(G_TID, G_ROW, G_C0 + 1)
        drag(page, a, b)
        check("끌어 고른 칸 2개", page.evaluate("() => tselActive() && tsel.cells.length") == 2)
        rclick(page, b)
        m = menu(page)
        texts = [x["text"] for x in m or []]
        check("칸 메뉴 — 분류 줄·항목", m is not None and any("고른 칸 — 1행 × 2열" in t for t in texts) and any(t.startswith("행·열 전체") for t in texts)
              and all(any(k in t for t in texts) for k in ("고른 칸만 아래에 넣기", "고른 칸만 아래에 복사", "고른 칸 줄 지우기", "칸 합치기", "칸 나누기", "헤더 지정", "표 나누기", "열 2개 지우기")), texts)
        page.screenshot(path=str(OUT / "01_menu.png"))

        # 2) 미리보기 — 고른 칸만 아래에 넣기: 새 칸이 들어갈 변 2칸 + 늘어나는 칸(왼쪽 헤더·오른쪽 칸)
        item(page, "고른 칸만 아래에 넣기").hover()
        pv = tprev(page)
        check("미리보기 — 넣을 변 2칸 · 늘어나는 칸", pv.get("tp-ins-b") == 2 and pv.get("tp-part", 0) >= 2, pv)
        page.screenshot(path=str(OUT / "02_preview_cells_below.png"))
        item(page, "열 2개 지우기").hover()
        page.wait_for_function("() => document.querySelector('#doc td.tp-fit') != null", timeout=20000)
        pv = tprev(page)
        check("미리보기 — 열 지우기: 지워질 칸 · 폭이 바뀌는 필드 열", pv.get("tp-del", 0) >= 2 and pv.get("tp-fit", 0) >= 1, pv)
        page.screenshot(path=str(OUT / "03_preview_col_delete.png"))
        fit_head = page.evaluate("(a) => [...document.querySelectorAll(`#doc table.tbl[data-tbl='${a[0]}'] td.tp-fit`)].some((td) => +td.dataset.c < a[1])", [G_TID, G_HC])
        check("미리보기 — 헤더 열은 폭이 안 바뀐다", not fit_head)
        item(page, "행 아래에 넣기").hover()
        pv = tprev(page)
        check("미리보기 — 행 전체 넣기: 묶음 제목은 늘어나는 칸", pv.get("tp-ins-b", 0) >= 2 and pv.get("tp-part", 0) >= 1, pv)

        # 3) 고른 칸만 아래에 넣기 — 행 +1 · 묶음 제목 +1 · 고른 열 밖 칸은 늘어남
        item(page, "고른 칸만 아래에 넣기").click()
        idle(page)
        b1 = block(page, G_TID)
        check("고른 칸만 아래에 넣기 — 행 +1 · 칸 +2", b1["rows"] == b0["rows"] + 1 and b1["cells"] == b0["cells"] + 2, (b0, b1))
        check("묶음 제목이 늘어났다", span(page, G_HEAD) == rs0 + 1, (rs0, span(page, G_HEAD)))
        check("메뉴가 닫히면 미리보기가 걷힌다", tprev(page) == {})

        # 4) M = 합치기 · S = 나누기 목록 → 칸 크기 그대로
        drag(page, td(G_TID, G_ROW, G_C0), td(G_TID, G_ROW + 1, G_C0))
        check("두 행 칸 고름", page.evaluate("() => tsel.cells.length") == 2)
        page.keyboard.press("m")
        idle(page)
        b2 = block(page, G_TID)
        check("M — 칸 합치기(칸 −1)", b2["cells"] == b1["cells"] - 1, (b1, b2))
        rclick(page, td(G_TID, G_ROW, G_C0))
        page.keyboard.press("Escape")
        check("Esc — 메뉴만 닫히고 칸은 고른 채", menu(page) is None and page.evaluate("() => tselActive()"))
        page.keyboard.press("s")
        page.wait_for_selector(".ctx-menu[data-by='tsel']:not([hidden])")
        texts = [x["text"] for x in menu(page) or []]
        check("S — 칸 나누기 목록", any("칸 크기 그대로" in t for t in texts) and any("표 크기 그대로" in t for t in texts) and any("합친 칸 풀기" in t for t in texts), texts)
        item(page, "합친 칸 풀기").hover()
        check("미리보기 — 나뉠 자리", tprev(page).get("tp-split") == 1, tprev(page))
        page.screenshot(path=str(OUT / "04_split_menu.png"))
        item(page, "합친 칸 풀기").click()
        idle(page)
        check("합친 칸 풀기 — 칸 수 복원", block(page, G_TID)["cells"] == b1["cells"])
        rclick(page, td(G_TID, G_ROW + 1, G_C0 + 1))
        item(page, "칸 나누기").click()
        page.wait_for_selector(".ctx-menu[data-by='tsel'] button.tmn-back")
        item(page, "2칸 — 칸 크기 그대로").click()
        idle(page)
        b3 = block(page, G_TID)
        check("칸 나누기(칸 크기 그대로) — 행 +1", b3["rows"] == b1["rows"] + 1 and b3["cells"] == b1["cells"] + 1, (b1, b3))

        # 5) 헤더 지정 — 귀퉁이 표시 · 지정 풀기
        rclick(page, td(G_TID, G_ROW, G_C0))
        item(page, "헤더 지정").click()
        page.wait_for_selector(".ctx-menu[data-by='tsel'] button:has-text('행헤더로 지정')")
        item(page, "행헤더로 지정").click()
        page.wait_for_function("(s) => { const t = document.querySelector(s); return t && t.classList.contains('hd-user'); }", arg=td(G_TID, G_ROW, G_C0), timeout=20000)
        check("헤더 지정 — 귀퉁이 표시", True)
        lay = page.evaluate("(t) => api(`/api/docs/${state.id}/tables/${t}/layout`)", G_TID)
        check("헤더 지정이 판정에 듣는다(그 칸 user)", any(x.get("user") and x["role"] == "rowhead" for x in lay["cells"]), [x for x in lay["cells"] if x.get("user")])
        page.screenshot(path=str(OUT / "05_heads.png"))
        rclick(page, td(G_TID, G_ROW, G_C0))
        item(page, "헤더 지정").click()
        page.wait_for_selector(".ctx-menu[data-by='tsel'] button:has-text('지정 풀기')")
        check("헤더 지정 목록 — 지금 값 표시(✓)", any(x["text"].startswith("✓ 행헤더") for x in menu(page)), menu(page))
        item(page, "지정 풀기").click()
        page.wait_for_function("() => !document.querySelector('#doc td.hd-user')", timeout=20000)
        check("지정 풀기 — 표시 없음", True)

        # 5-1) 열 지우기(헤더 열 폭 그대로 · 남은 필드 열이 넓어짐) → 필드 열 폭 같게
        cw = "(t) => [...document.querySelectorAll(`#doc table.tbl[data-tbl='${t}'] > colgroup > col`)].map((c) => parseFloat(c.style.width))"
        w0 = page.evaluate(cw, U_TID)
        rclick(page, td(U_TID, 0, U_HC + 1))
        item(page, "열 지우기").click()
        idle(page)
        w1 = page.evaluate(cw, U_TID)
        check("열 지우기 — 표 폭·헤더 열 폭 그대로 · 남은 필드 열이 넓어짐", len(w1) == len(w0) - 1 and abs(sum(w1) - sum(w0)) < 0.5 and all(abs(a - b) < 0.05 for a, b in zip(w1[:U_HC], w0[:U_HC]))
              and all(a > b for a, b in zip(w1[U_HC:], w0[U_HC:U_HC + 1] + w0[U_HC + 2:])), (w0, w1))
        rclick(page, td(U_TID, 0, U_HC))
        item(page, "열 오른쪽에 넣기").click()
        idle(page)
        w2 = page.evaluate(cw, U_TID)
        check("열 넣기 — 표 폭·헤더 열 폭 그대로 · 필드 열이 좁아짐", len(w2) == len(w0) and abs(sum(w2) - sum(w0)) < 0.5 and all(abs(a - b) < 0.05 for a, b in zip(w2[:U_HC], w0[:U_HC]))
              and abs(w2[U_HC] - w2[U_HC + 1]) < 0.1 and all(a < b for a, b in zip(w2[U_HC + 2:], w1[U_HC + 1:])), (w1, w2))
        rclick(page, td(U_TID, 0, U_HC))
        item(page, "필드 열 폭 같게").hover()
        page.wait_for_function("() => document.querySelector('#doc td.tp-fit') != null", timeout=20000)
        item(page, "필드 열 폭 같게").click()
        idle(page)
        w3 = page.evaluate(cw, U_TID)
        check("필드 열 폭 같게", max(w3[U_HC:]) - min(w3[U_HC:]) < 0.1 and abs(sum(w3) - sum(w0)) < 0.5, w3)

        # 6) 표 나누기 — 손잡이 메뉴 → 둘로 → 다시 나누기 → 다시 합치기
        page.locator(f"#doc table.tbl[data-tbl='{U_TID}'] td .para").first.scroll_into_view_if_needed()
        page.locator(f"#doc table.tbl[data-tbl='{U_TID}'] td .para").first.click()
        page.wait_for_selector(f".tbl-corner[data-for='{U_TID}']")
        page.locator(".tbl-corner").click()
        page.wait_for_selector(".ctx-menu[data-by='tmn']:not([hidden])")
        item(page, "표 나누기", "tmn").click()
        page.wait_for_selector(f".ctx-menu[data-by='tsel'] button:has-text('앞 1열 + 뒤 {U_N - 1}열')", timeout=30000)
        item(page, f"앞 {U_N - 1}열 + 뒤 1열").hover()
        check("미리보기 — 뒤 표로 갈 열", tprev(page).get("tp-move", 0) >= 1, tprev(page))
        page.screenshot(path=str(OUT / "06_split_table_menu.png"))
        n_tables = page.evaluate("() => state.blocks.filter((b) => b.type === 'table').length")
        item(page, f"앞 {U_N - 1}열 + 뒤 1열").click()
        idle(page)
        u1 = block(page, U_TID)
        check("표 나누기 — 앞 표 열 수 · 표 +1", u1["cols"] == U_NC - 1 and page.evaluate("() => state.blocks.filter((b) => b.type === 'table').length") == n_tables + 1, u1)
        widths = page.evaluate("""(t) => { const i = state.blocks.findIndex((b) => b.id === t); const a = document.querySelector(`#doc table.tbl[data-tbl='${t}']`);
            const nb = state.blocks.slice(i + 1).find((b) => b.type === 'table'); const b = document.querySelector(`#doc table.tbl[data-tbl='${nb.id}']`);
            return {a: a.getBoundingClientRect().width, b: b.getBoundingClientRect().width, second: nb.id, cols: nb.nCols}; }""", U_TID)
        check("두 표 모두 원래 폭 · 뒤 표 = 헤더 열 + 1열", abs(widths["a"] - widths["b"]) < 2 and widths["cols"] == U_HC + 1, widths)
        page.screenshot(path=str(OUT / "07_split_done.png"))
        second = widths["second"]
        # 뒤 표의 칸 메뉴에서 다시 나누기(4+1 → 2+3 꼴)
        rclick(page, f"#doc table.tbl[data-tbl='{second}'] td")
        item(page, "표 나누기").click()
        page.wait_for_selector(".ctx-menu[data-by='tsel'] button:has-text('한 표로 다시 합치기')", timeout=30000)
        texts = [x["text"] for x in menu(page)]
        check("이어진 표 — 다시 나누기 목록", any(f"지금 앞 {U_N - 1}열 + 뒤 1열" in t for t in texts) and any(t.startswith("앞 2열 + 뒤") for t in texts), texts)
        item(page, f"앞 2열 + 뒤 {U_N - 2}열").click()
        idle(page)
        u2 = block(page, U_TID)
        check("다시 나누기 — 앞 표 = 헤더 열 + 2열", u2["cols"] == U_HC + 2, u2)
        page.locator(f"#doc table.tbl[data-tbl='{U_TID}'] td .para").first.click()
        page.wait_for_selector(f".tbl-corner[data-for='{U_TID}']")
        page.locator(".tbl-corner").click()
        page.wait_for_selector(".ctx-menu[data-by='tmn']:not([hidden])")
        item(page, "표 나누기", "tmn").click()
        page.wait_for_selector(".ctx-menu[data-by='tsel'] button:has-text('한 표로 다시 합치기')", timeout=30000)
        item(page, "한 표로 다시 합치기").click()
        idle(page)
        u3 = block(page, U_TID)
        check("다시 합치기 — 열 수 · 표 수 복원", u3["cols"] == U_NC and page.evaluate("() => state.blocks.filter((b) => b.type === 'table').length") == n_tables, u3)

        # 7) 넘침 나눔 — 고른 칸(두 행)을 되풀이해 복사: 쪽 상자가 넘치면 병합 칸을 건너 조각 상자로
        over0 = page.evaluate("() => document.querySelectorAll('#doc .sheet.over').length")
        grew = False
        for k in range(14):
            drag(page, td(G_TID, G_ROW, G_C0), td(G_TID, G_ROW + 3, G_C1))
            rclick(page, td(G_TID, G_ROW, G_C0))
            item(page, "고른 칸만 아래에 복사").click()
            idle(page)
            page.wait_for_timeout(300)
            st = page.evaluate("""(t) => { const segs = [...document.querySelectorAll(`#doc table.tbl[data-tbl='${t}']`)];
                const sheets = [...new Set(segs.map((s) => s.closest('.sheet')))];
                const tall = sheets.map((s) => { const g = state.sections[+s.dataset.sec] || DEFAULT_PAGE; const room = (g.heightMm - g.marginsMm.t - g.marginsMm.b) * PX_PER_MM;
                    return s.querySelector('.sheet-body').offsetHeight / room; });
                return {segs: segs.length, over: document.querySelectorAll('#doc .sheet.over').length, ghosts: document.querySelectorAll(`#doc table.tbl[data-tbl='${t}'] td.cell-cont`).length,
                        tall: Math.max(...tall)}; }""", G_TID)
            if st["over"] > over0:
                grew = True
                break
        check("표가 길어지면 다음 쪽 조각으로 넘어간다", grew, st)
        check("병합 칸을 건너 잘랐다(이어짐 칸) · 쪽 상자가 용지의 1.2배를 넘지 않는다", grew and st["ghosts"] >= 1 and st["tall"] < 1.2, st)
        page.locator(f"#doc table.tbl[data-tbl='{G_TID}'].cont").first.scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "08_overflow.png"))
        rows_now = block(page, G_TID)["rows"]
        dom_rows = page.evaluate("(t) => new Set([...document.querySelectorAll(`#doc table.tbl[data-tbl='${t}'] > tbody > tr`)].map((tr) => tr.dataset.row)).size", G_TID)
        check("조각에 모든 행이 있다", dom_rows == rows_now, (dom_rows, rows_now))
        # 나뉜 뒤에도 칸 고르기·편집이 된다(이어짐 칸 포함)
        drag(page, td(G_TID, G_ROW, G_C0), td(G_TID, G_ROW, G_C0 + 1))
        rclick(page, td(G_TID, G_ROW, G_C0))
        item(page, "고른 칸 줄 지우기").hover()
        pv = tprev(page)
        check("미리보기 — 줄 지우기: 지워질 칸 · 줄어드는 칸", pv.get("tp-del", 0) >= 2 and pv.get("tp-part", 0) >= 1, pv)
        item(page, "고른 칸 줄 지우기").click()
        idle(page)
        check("고른 칸 줄 지우기 — 행 −1", block(page, G_TID)["rows"] == rows_now - 1)
        br.close()
    real = [e for e in errors if "favicon" not in e]
    check("콘솔 오류 없음", not real, real[:5])
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print("FAILS:", fails if fails else "none")
sys.exit(1 if fails else 0)

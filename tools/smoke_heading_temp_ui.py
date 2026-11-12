"""TEMP 라벨 화면 연기 시험(spec_헤딩_추출 ② §15) — 임시 서버가 떠 있어야 한다(작업이 하나 생기고 문서를 지웠다 되돌린다 — 사용자 8114 에는 돌리지 않는다):
NFM_LLM_BACKEND=off NFM_PDF=off NFM_WORKS/NFM_RENDER/NFM_HEADINGS/NFM_FORMS=<임시 폴더> python -m uvicorn app.server:app --port 18167

python -X utf8 tools/smoke_heading_temp_ui.py [http://127.0.0.1:18167] [그림 폴더]
연구개발계획서 양식을 올려 1·2·3단계(스크립트)를 API 로 돌리고 → 화면: TEMP 수 · 카드 줄 · 표 표지 「TEMP」 · 여백 「TEMP」 표 · 그래프에 TEMP 문단이 없음 ·
TEMP 목록(2열) · 해제 → 다시 TEMP · 오른쪽 단추 메뉴로 지정 → 지정 지움 · 삭제(문서에서 표가 사라짐) → 실행 취소 · 콘솔 오류."""
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18167"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else ROOT / "artifacts" / "ui_heading_temp")
RND = ROOT / "samples" / "연구개발계획서_양식.hwpx"
OUT.mkdir(parents=True, exist_ok=True)
checks = []
GUIDE = "t996"      # 「작성 요령」 표(2×2)
BODY = "p5876"      # 본문 괄호 소제목 「[국내 기술 동향 및 수준]」


def ok(name, cond, detail=""):
    checks.append((name, bool(cond), detail))
    print(("  ok  " if cond else "  FAIL") + f" {name}" + (f" — {detail}" if detail and not cond else ""), flush=True)


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


def run_stage(doc, stage):
    r = requests.post(f"{URL}/api/docs/{doc}/headings", json={"stage": stage, "llm": False})
    r.raise_for_status()
    end = time.time() + 180
    while time.time() < end:
        st = requests.get(f"{URL}/api/docs/{doc}/headings").json()
        if st["job"] and st["job"]["status"] != "running":
            assert st["job"]["status"] == "done", st["job"]
            return st
        time.sleep(0.5)
    raise SystemExit(f"{stage}단계가 안 끝남")


def main():
    wait_server()
    r = requests.post(URL + "/api/docs", files={"file": (RND.name, RND.read_bytes())})
    r.raise_for_status()
    doc = r.json()["docId"]
    for stage in (1, 2, 3):
        st = run_stage(doc, stage)
    ok("API: 요약에 TEMP 52항목", st["temp"]["counts"]["items"] == 52, st["temp"])
    ok("API: 2·3단계가 지금 TEMP 로 만든 결과", st["stage2"]["tempStale"] is False and st["stage3"]["tempStale"] is False)
    logs, dialogs = [], []
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        page = br.new_page(viewport={"width": 1600, "height": 950})
        page.on("console", lambda m: logs.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))

        def on_dialog(d):
            dialogs.append(d.message)
            d.accept()
        page.on("dialog", on_dialog)
        page.goto(URL)
        page.evaluate(f"location.hash = '#w={doc}'")
        page.reload()
        page.wait_for_function("document.querySelector('.sheet .para') != null", timeout=240000)
        page.click("#tabHeads")
        page.wait_for_function("heads.graph && heads.graph.nodes && TEMP.data && TEMP.data.items.length > 0", timeout=120000)
        page.wait_for_function("document.querySelectorAll('.tbl-mark.temp').length >= 30 && document.querySelectorAll('.tpl-mark.temp').length > 0", timeout=120000)
        n = page.evaluate("({tbl: document.querySelectorAll('.tbl-mark.temp').length, para: document.querySelectorAll('.tpl-mark.temp').length, "
                          "items: TEMP.data.items.length, tables: Object.keys(TEMP.data.tables).length, marks: TEMP.marks.size})")
        ok("표 표지 「TEMP」 = TEMP 표 수(문서에 보이는 표)", n["tbl"] >= 30 and n["tbl"] <= n["tables"], n)
        ok("여백 「TEMP」 표 = 칸·문단 단위 항목(한 줄로 모인 것 포함)", 0 < n["para"] <= n["marks"] == 21, n)
        ok("그래프에 TEMP 문단의 노드가 없다", page.evaluate("heads.graph.nodes.filter((x) => TEMP.data.paras[x.para]).length") == 0)
        ok("TEMP 표 표지에는 소속·구조 꼬리표가 없다", page.evaluate(
            f"(() => {{ const m = document.querySelector('.tbl-mark[data-for=\"{GUIDE}\"]'); return !!m && !!m.querySelector('.tm-temp') && !m.querySelector('.tm-owner'); }})()"))
        ok("TEMP 가 아닌 표의 표지는 그대로(소속)", page.evaluate(
            "(() => { const m = document.querySelector('.tbl-mark[data-for=\"t1021\"]'); return !!m && !m.querySelector('.tm-temp') && !!m.querySelector('.tm-owner'); })()"))
        inside = page.evaluate("""[...document.querySelectorAll('.tpl-mark.temp')].every((m) => { const s = m.closest('.sheet').getBoundingClientRect(), r = m.getBoundingClientRect();
            return r.left >= s.left - 1 && r.right <= s.right; })""")
        ok("여백 「TEMP」 표는 쪽 안 왼쪽 여백에", inside)
        metric = page.locator("#headsOverview .result-metric", has_text="TEMP")
        ok("결과 요약에 TEMP 수", metric.count() == 1 and "52" in metric.inner_text(), metric.inner_text() if metric.count() else "")
        page.click("#headsTabRun")
        page.click("#headsStageTab1")  # 추출·설정은 단계 탭 — 1단계 카드(TEMP 줄)를 고른다(spec_헤딩_추출 ② §7 「단계 탭」)
        page.wait_for_selector("#heads1 .htemp .hb.temp")
        card = page.locator("#heads1 .htemp").inner_text()
        ok("1단계 카드의 TEMP 줄", "52항목" in card and "작성 요령 표 30" in card and "빈 글머리 줄 15" in card and "헤딩 후보 394" in card, card)
        ok("지금 TEMP 로 만든 결과면 경고·반영 단추 없음", page.locator("#heads1 .htemp .hwarn").count() == 0)
        page.locator("#heads1 .htemp").screenshot(path=str(OUT / "card.png"))
        page.evaluate(f"document.querySelector('.tbl-mark[data-for=\"{GUIDE}\"]').scrollIntoView({{block: 'center'}})")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "doc_marks.png"))

        # TEMP 목록(2열)
        page.locator("#heads1 .htemp button", has_text="TEMP 목록").click()
        page.wait_for_selector("#headsDlgBody table.temp-list")
        rows = page.locator("#headsDlgBody table.temp-list tbody tr").count()
        heads_ = page.locator("#headsDlgBody .temp-head").all_inner_texts()
        ok("TEMP 목록 — 항목 52줄 · 작성요령/쓸 자리 묶음", rows == 52 and len(heads_) == 2 and "작성요령" in heads_[0] and "37항목" in heads_[0] and "쓸 자리" in heads_[1] and "15항목" in heads_[1], (rows, heads_))
        over = page.evaluate("(() => { const b = document.getElementById('headsDlgBody'); return b.scrollWidth - b.clientWidth; })()")
        ok("2열 가로 넘침 없음", over <= 1, over)
        page.locator("#headsDlg").screenshot(path=str(OUT / "list.png"))

        # 해제 → 2단계 다시 셈 → 다시 TEMP
        row = page.locator(f'#headsDlgBody tr[data-item="tbl:{GUIDE}"]')
        row.locator("button", has_text="해제").click()
        page.wait_for_function(f"TEMP.data.items.length === 51 && !document.querySelector('.tbl-mark[data-for=\"{GUIDE}\"] .tm-temp')", timeout=60000)
        page.wait_for_function("heads.graph && heads.graph.nodes.some((x) => x.flow === 'cell:c1001')", timeout=60000)
        ok("해제 — 표 표지에서 TEMP 가 빠지고 그 칸 글머리가 헤딩 후보로", True)
        off = page.locator("#headsDlgBody .temp-row")
        ok("해제한 항목 목록", off.count() == 1 and f"tbl:{GUIDE}" in off.inner_text(), off.all_inner_texts())
        off.locator("button", has_text="다시 TEMP 로").click()
        page.wait_for_function(f"TEMP.data.items.length === 52 && !!document.querySelector('.tbl-mark[data-for=\"{GUIDE}\"] .tm-temp')", timeout=60000)
        page.wait_for_function("heads.graph && !heads.graph.nodes.some((x) => x.flow === 'cell:c1001')", timeout=60000)
        ok("다시 TEMP 로 — 처음 상태", True)

        # 오른쪽 단추 메뉴 — 본문 문단을 TEMP 로 지정 → 지정 지움
        page.evaluate(f"document.querySelector('.para[data-id=\"{BODY}\"]').scrollIntoView({{block: 'center'}})")
        page.wait_for_timeout(1500)
        page.click(f'.para[data-id="{BODY}"]', button="right")
        page.wait_for_selector(".ctx-menu:not([hidden])")
        menu = page.locator(".ctx-menu button").all_inner_texts()
        ok("문단 메뉴에 「TEMP 로 지정 — 이 문단」", any("TEMP 로 지정 — 이 문단" in t for t in menu), menu)
        page.locator(".ctx-menu button", has_text="TEMP 로 지정 — 이 문단").click()
        page.wait_for_function(f"TEMP.data.items.some((x) => x.id === 'para:{BODY}' && x.by === 'user')", timeout=60000)
        page.wait_for_function(f"heads.graph && !heads.graph.nodes.some((x) => x.para === '{BODY}')", timeout=60000)
        page.wait_for_function(f"TEMP.marks.has('{BODY}') && document.querySelectorAll('.tpl-mark.temp').length > 0", timeout=30000)
        ok("지정 — 그 문단의 노드가 사라지고 사용자 지정 항목이 됨", True)
        page.evaluate(f"document.querySelector('.para[data-id=\"{BODY}\"]').scrollIntoView({{block: 'center'}})")
        page.wait_for_timeout(1500)
        page.click(f'.para[data-id="{BODY}"]', button="right")
        page.wait_for_selector(".ctx-menu:not([hidden])")
        page.locator(".ctx-menu button", has_text="TEMP 지정 지움").click()
        page.wait_for_function(f"!TEMP.data.items.some((x) => x.id === 'para:{BODY}') && TEMP.data.items.length === 52", timeout=60000)
        page.wait_for_function(f"heads.graph && heads.graph.nodes.some((x) => x.para === '{BODY}')", timeout=60000)
        ok("지정 지움 — 노드가 돌아옴", True)
        # 표 칸 메뉴 — TEMP 표 안에서는 「TEMP 해제」
        page.evaluate("document.querySelector('.para[data-id=\"p684\"]').scrollIntoView({block: 'center'})")
        page.wait_for_timeout(1500)
        page.click('.para[data-id="p684"]', button="right")
        page.wait_for_selector(".ctx-menu:not([hidden])")
        menu = page.locator(".ctx-menu button").all_inner_texts()
        ok("표 칸 메뉴 — TEMP 줄에서는 「TEMP 해제」·「TEMP 목록에서 보기」", any(t.startswith("TEMP 해제") for t in menu) and any("TEMP 목록에서 보기" in t for t in menu), menu)
        page.keyboard.press("Escape")

        # 삭제 → 문서에서 사라짐 → 실행 취소
        page.evaluate(f"tempView('tbl:{GUIDE}')")
        row = page.locator(f'#headsDlgBody tr[data-item="tbl:{GUIDE}"]')
        ok("문서 표지에서 연 목록은 그 항목을 눈에 띄게", "focus" in (row.get_attribute("class") or ""))
        before = len(dialogs)
        row.locator("button", has_text="삭제").click()
        page.wait_for_function(f"!document.querySelector('table.tbl[data-tbl=\"{GUIDE}\"]')", timeout=240000)
        ok("삭제 — 확인 창을 거쳐 문서에서 표가 사라짐", len(dialogs) == before + 1 and "문서에서 지울까요" in dialogs[-1], dialogs[-1:] )
        page.wait_for_function("TEMP.data && TEMP.data.items.length === 51 && !TEMP.data.stale && state.undo >= 1 && !state.busy", timeout=240000)
        ok("삭제 뒤 1단계가 다시 돌아 TEMP 51항목 · 실행 취소 1", True)
        page.evaluate("undoStruct()")
        page.wait_for_function(f"!!document.querySelector('table.tbl[data-tbl=\"{GUIDE}\"]') && !state.busy", timeout=240000)
        page.evaluate("tempView()")  # 실행 취소 뒤 — 읽어 둔 TEMP 는 옛 문서 기준: 목록이 알리고 삭제를 막는다
        stale = page.evaluate("({warn: !!document.querySelector('.temp-wrap > .hwarn'), del: [...document.querySelectorAll('#headsDlgBody table.temp-list td.acts button')]"
                              ".filter((b) => b.textContent === '삭제').every((b) => b.disabled)})")
        ok("실행 취소 뒤 목록은 「문서가 추출 뒤 바뀜」 — 삭제 단추 꺼짐", stale["warn"] and stale["del"], stale)
        page.evaluate("headsShow()")  # 헤딩 추출 탭을 다시 여는 것과 같음 — 1단계가 다시 돈다
        page.wait_for_function("TEMP.data && TEMP.data.items.length === 52 && !TEMP.data.stale && TEMP.data.rev === state.serverRev", timeout=240000)
        ok("실행 취소 — 표가 돌아오고 다시 추출하면 TEMP 52항목", True)
        page.screenshot(path=str(OUT / "after_undo.png"))
        br.close()
    bad = [m for m in logs if "favicon" not in m]
    ok("콘솔 오류 없음", not bad, bad[:5])
    fails = [c for c in checks if not c[1]]
    print(f"\n{len(checks) - len(fails)}/{len(checks)} 통과" + (f" — 실패 {len(fails)}" if fails else ""))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

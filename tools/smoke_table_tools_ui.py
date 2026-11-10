"""표 도구 화면 연기 시험(spec_헤딩_추출 ② §10) — 서버가 떠 있어야 한다(LLM·PDF 끔 권장: NFM_LLM_BACKEND=off NFM_PDF=off).

python -X utf8 tools/smoke_table_tools_ui.py [http://127.0.0.1:18141] [출력 폴더]
연구개발계획서 양식을 열고 → 1·3단계(스크립트) → 헤딩 추출 탭 → 표 표지(.tbl-mark — 소속 헤딩) → 예산표(8-1.) ⊞ → 2열 엑셀식 보기(.xl-wrap.col) → 수식 칸 상태 → 수식 줄에 「=1+2*3」 →
저장된 사용자 수식 확인 → 창 크기 바꿈(격자 유지) → 「문서에 반영」 → 문서 칸 글 확인 → 「문서 자리에서 보기」/「문서 보기」 → ✎ 표 지침 저장 → 「표」 탭 목록·공통 지침 → 콘솔 오류. 그림은 출력 폴더에."""
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18141"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "artifacts" / "ui_table_tools")
OUT.mkdir(parents=True, exist_ok=True)
SAMPLE = "연구개발계획서_양식.hwpx"


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
    r = requests.post(f"{URL}/api/docs/{doc}/headings", json={"stage": stage, "llm": False}, timeout=10)
    assert r.status_code == 202, r.text
    end = time.time() + 300
    while time.time() < end:
        v = requests.get(f"{URL}/api/docs/{doc}/headings", timeout=10).json()
        job = v.get("job")
        if not job or job.get("status") != "running":
            return v
        time.sleep(0.5)
    raise SystemExit("단계가 안 끝남")


def main():
    wait_server()
    logs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1600, "height": 950}, device_scale_factor=1)
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(URL)
        page.wait_for_selector(".sample", state="attached")
        if not page.locator("#sampleSection").evaluate("d => d.open"):
            page.click("#sampleSection summary")  # 예제 목록은 접혀 있다
        page.click(f'.sample[aria-label="예제 {SAMPLE} 열기"]')
        page.wait_for_selector(".para")
        page.wait_for_timeout(800)
        doc = page.evaluate("location.hash").split("=", 1)[1]
        print("doc", doc, "| tabTables hidden:", page.locator("#tabTables").is_hidden())
        marks0 = page.locator(".tbl-mark").count()
        print("marks before stage3:", marks0, "| first:", page.locator(".tbl-mark").first.inner_text().replace("\n", " ") if marks0 else "-")
        run_stage(doc, 1)
        v = run_stage(doc, 3)
        s3 = v["stage3"]
        print("stage3 tables:", s3["counts"]["tables"], "calc:", s3["counts"]["calc"]["tables"])
        calc = [t for t in s3["tables"] if (t.get("calc") or {}).get("is") and (t["calc"].get("ok") or 0) >= 1]
        tid = calc[0]["id"] if calc else s3["tables"][0]["id"]
        print("target table:", tid, "owner:", (calc[0].get("owner") or {}).get("text") if calc else None)
        page.click("#tabHeads")
        page.wait_for_timeout(1500)
        marks = page.locator(".tbl-mark").count()
        owners = page.locator(".tbl-mark .tm-owner:not(.muted)").count()
        print("marks after:", marks, "with owner:", owners)
        m = page.locator(f'.tbl-mark[data-for="{tid}"]')
        assert m.count() == 1, f"표지 없음 {tid}"
        print("mark text:", m.inner_text().replace("\n", " "))
        tbl = page.locator(f'table.tbl[data-tbl="{tid}"]').first
        tbl.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        page.evaluate("tblMarksDraw()")
        page.wait_for_timeout(300)
        page.screenshot(path=OUT / "01_marks.png")
        m.locator(".tm-owner").click()
        page.wait_for_timeout(800)
        print("after owner click selected para:", page.evaluate("state.selected"))
        # ⊞ → 2열 엑셀식 보기
        page.locator(f'.tbl-mark[data-for="{tid}"] .tm-btn.xl').click()
        page.wait_for_selector(f'.heads-col .xl-wrap.col[data-tbl="{tid}"]')
        page.wait_for_timeout(600)
        wrap = page.locator(f'.xl-wrap.col[data-tbl="{tid}"]')
        counts = page.evaluate("""(tid) => { const w = document.querySelector(`.xl-wrap.col[data-tbl="${tid}"]`);
            return { title: document.getElementById('headsDlgTitle').textContent, td: w.querySelectorAll('td[data-ref]').length, fx: w.querySelectorAll('td.fx').length,
                     ok: w.querySelectorAll('td.fx.ok').length, bad: w.querySelectorAll('td.fx.bad').length, fill: w.querySelectorAll('td.fx.fill').length,
                     blank: w.querySelectorAll('td.fx.blank').length, err: w.querySelectorAll('td.fx.err').length,
                     docTableStillThere: document.querySelectorAll(`#doc table.tbl[data-tbl="${tid}"]:not([hidden])`).length,
                     markOpen: !!document.querySelector(`.tbl-mark[data-for="${tid}"].open`), pct: [...w.querySelectorAll('td.fx.ok')].map((x) => x.textContent).slice(0, 4) }; }""", tid)
        print("xl(col):", counts)
        page.screenshot(path=OUT / "02_xl_col.png")
        ref = page.evaluate("""(tid) => { const w = document.querySelector(`.xl-wrap.col[data-tbl="${tid}"]`);
            const td = [...w.querySelectorAll('td[data-ref]')].find((x) => !x.classList.contains('fx') && !x.textContent.trim() && (x.classList.contains('field') || !x.className));
            return td ? td.dataset.ref : null; }""", tid)
        print("empty field:", ref)
        assert ref, "빈 필드 없음"
        wrap.locator(f'td[data-ref="{ref}"]').click()
        page.wait_for_timeout(200)
        print("name box:", wrap.locator(".xl-name").input_value())
        wrap.locator(".xl-fx").fill("=1+2*3")
        wrap.locator(".xl-fx").press("Enter")
        page.wait_for_timeout(1000)
        print("cell after formula:", wrap.locator(f'td[data-ref="{ref}"]').inner_text(), "| classes:", wrap.locator(f'td[data-ref="{ref}"]').get_attribute("class"))
        saved = requests.get(f"{URL}/api/docs/{doc}/headings/tables/agents", timeout=10).json()
        print("saved formulas:", saved["tables"].get(tid, {}).get("formulas"))
        wrap.locator(f'td[data-ref="{ref}"]').click()
        page.keyboard.press("F2")
        page.wait_for_timeout(200)
        page.keyboard.press("Control+A")
        page.keyboard.type("=ROUND(10/3,1)")
        page.keyboard.press("Enter")
        page.wait_for_timeout(900)
        print("cell after edit:", wrap.locator(f'td[data-ref="{ref}"]').inner_text())
        for formula, label in ((f"={ref}+1", "cycle"), ("=FOO(1)", "name err"), ('="a"&"b"', "concat"), ("=1+2*3", "back")):
            wrap.locator(f'td[data-ref="{ref}"]').click()
            wrap.locator(".xl-fx").fill(formula)
            wrap.locator(".xl-fx").press("Enter")
            page.wait_for_timeout(300)
            print(f"{label}:", wrap.locator(f'td[data-ref="{ref}"]').inner_text())
        page.wait_for_timeout(800)
        # 문서의 빈 필드 칸에 타자 → 2열 격자의 그 칸이 바로 따라온다(PATCH 전·후)
        live = page.evaluate("""(tid) => { const w = document.querySelector(`.xl-wrap.col[data-tbl="${tid}"]`); const m = w._model;
            const c = m.cells.find((x) => x.role === "field" && !m.formulas.has(x.ref) && x.paras.length === 1 && document.querySelector(`#doc .para[data-id="${x.paras[0]}"]`) && !xlDocText(x));
            return c ? { ref: c.ref, pid: c.paras[0] } : null; }""", tid)
        print("live target:", live)
        if live:
            page.locator(f'#doc .para[data-id="{live["pid"]}"]').click()
            page.keyboard.type("123")
            page.wait_for_timeout(700)
            print("grid cell while typing:", wrap.locator(f'td[data-ref="{live["ref"]}"]').inner_text())
            page.wait_for_timeout(1500)
            print("grid cell after save:", wrap.locator(f'td[data-ref="{live["ref"]}"]').inner_text(), "| state.texts:", page.evaluate("(pid) => state.texts[pid]", live["pid"]))
        page.set_viewport_size({"width": 1400, "height": 900})
        page.wait_for_timeout(1500)
        print("xl after resize:", page.locator(f'.xl-wrap.col[data-tbl="{tid}"]').count(), "formula kept:", page.locator(f'.xl-wrap.col[data-tbl="{tid}"] td[data-ref="{ref}"]').inner_text())
        page.screenshot(path=OUT / "03_xl_resized.png")
        wrap = page.locator(f'.xl-wrap.col[data-tbl="{tid}"]')
        print("write button:", wrap.locator(".xl-write").inner_text())
        wrap.locator(".xl-write").click()
        page.wait_for_timeout(2500)
        print("after write foot:", wrap.locator(".xl-foot").inner_text().replace("\n", " ")[:120])
        pid = page.evaluate("""([tid, ref]) => { const w = document.querySelector(`.xl-wrap.col[data-tbl="${tid}"]`); const c = w._model.cells.find((x) => x.ref === ref); return c.paras[0]; }""", [tid, ref])
        print("target para:", pid, "state.texts:", page.evaluate("(pid) => state.texts[pid]", pid), "edited:", page.evaluate("(pid) => state.edited.has(pid)", pid),
              "| doc para text:", page.locator(f'#doc .para[data-id="{pid}"]').inner_text())
        page.screenshot(path=OUT / "04_doc_after_write.png")
        # 문서 자리에서 보기 ↔ 문서 보기
        wrap.locator("button:has-text('문서 자리에서 보기')").click()
        page.wait_for_selector(f'#doc .xl-wrap[data-tbl="{tid}"]')
        print("inplace:", page.locator(f'#doc .xl-wrap[data-tbl="{tid}"]').count(), "hidden frags:", page.locator(f'table.tbl[data-tbl="{tid}"][hidden]').count())
        page.locator(f'#doc .xl-wrap[data-tbl="{tid}"] button:has-text("문서 보기")').click()
        page.wait_for_timeout(600)
        print("inplace closed:", page.locator(f'#doc .xl-wrap[data-tbl="{tid}"]').count(), "| col still:", page.locator(f'.xl-wrap.col[data-tbl="{tid}"]').count())
        # ✎ 표 지침
        page.locator(f'.tbl-mark[data-for="{tid}"] .tm-btn.guide').click()
        page.wait_for_selector(".ta-wrap")
        page.wait_for_timeout(500)
        print("agent title:", page.inner_text("#headsDlgTitle"), "| notes:", page.locator(".ta-notes li").count(), "| ident:", page.locator(".ta-ident").inner_text()[:100].replace("\n", " "))
        tas = page.locator(".ta-wrap textarea")
        tas.nth(1).fill("시험 지침 — 금액은 천원")
        page.locator(".ta-row button:has-text('저장')").nth(1).click()
        page.wait_for_timeout(1200)
        a = requests.get(f"{URL}/api/docs/{doc}/headings/tables/{tid}/agent", timeout=10).json()
        print("saved instructions:", a["own"]["instructions"], "v", a["own"]["version"], "| prompt has:", "[이 표 지침]\n시험 지침" in a["prompt"])
        print("guide mark has:", page.locator(f'.tbl-mark[data-for="{tid}"] .tm-btn.guide.has').count())
        page.locator(".ta-wrap details.more summary").click()
        page.wait_for_timeout(300)
        page.screenshot(path=OUT / "05_agent.png")
        # 「표」 탭
        page.click("#tabTables")
        page.wait_for_selector("#tablesBox table.tb-list")
        page.wait_for_timeout(500)
        rows = page.locator("#tablesBox table.tb-list tbody tr").count()
        print("tables tab rows:", rows, "| stats:", page.locator("#tablesBox .hstats").inner_text().replace("\n", " ")[:160])
        row = page.locator(f'#tablesBox table.tb-list tbody tr:has(td:text-is("{tid}"))')
        print("row text:", row.inner_text().replace("\n", " | ")[:200])
        row.locator('button[aria-label="엑셀식 보기"]').click()
        page.wait_for_selector(f'.xl-wrap.col[data-tbl="{tid}"]')
        print("xl from tab:", page.locator(f'.xl-wrap.col[data-tbl="{tid}"]').count(), "| col title:", page.inner_text("#headsDlgTitle"))
        page.screenshot(path=OUT / "06_tables_tab.png")
        page.click("#tablesBox button:has-text('공통 지침')")
        page.wait_for_selector(".ta-wrap")
        print("common view title:", page.inner_text("#headsDlgTitle"), "| textareas:", page.locator(".ta-wrap textarea").count())
        page.click("#headsDlgClose")
        page.wait_for_timeout(300)
        page.evaluate("headsTables(%r)" % tid)
        page.wait_for_timeout(1200)
        print("grid buttons:", page.locator("#headsDlgBody .hgrid-info button:has-text('표 지침')").count(), page.locator("#headsDlgBody .hgrid-info button:has-text('엑셀식 보기')").count())
        b.close()
    (OUT / "console.txt").write_text("\n".join(logs), encoding="utf-8")
    print("console:", len(logs), *logs[:10], sep="\n  ")


if __name__ == "__main__":
    main()

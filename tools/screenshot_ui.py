"""웹 화면 캡처(검토용) — 빈 화면, 예제 열기, 문단 고치기, 고친 문단 탭, PDF 쪽 탭, 쪽 비교 창.

python -X utf8 tools/screenshot_ui.py [http://127.0.0.1:8114] [예제 이름] [출력 폴더]
서버가 떠 있어야 한다. 콘솔 오류는 console.txt 에 남긴다."""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8114"
SAMPLE = sys.argv[2] if len(sys.argv) > 2 else "기술수요조사서.hwpx"
OUT = Path(sys.argv[3] if len(sys.argv) > 3 else Path(__file__).resolve().parents[1] / "artifacts" / "ui")
OUT.mkdir(parents=True, exist_ok=True)


def wait_import(page, timeout=600):
    end = time.time() + timeout
    while time.time() < end:
        cls = page.get_attribute("#summary", "class") or ""
        if "run" not in cls and page.inner_text("#summary").strip():
            return cls
        time.sleep(0.5)
    return "timeout"


def main():
    logs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
        page.goto(URL)
        page.wait_for_selector(".sample")
        page.screenshot(path=OUT / "01_empty.png")
        page.click(f".sample >> text={SAMPLE}")
        page.wait_for_selector(".para")
        page.wait_for_timeout(600)
        page.screenshot(path=OUT / "02_opened.png")
        print("import summary:", wait_import(page), page.inner_text("#summary").replace("\n", " / "))
        page.wait_for_timeout(500)
        page.screenshot(path=OUT / "03_import_done.png")
        # 문단 하나 고치기
        paras = page.locator(".para")
        target = None
        for i in range(paras.count()):
            if len(paras.nth(i).inner_text().strip()) > 12:
                target = paras.nth(i)
                break
        target.click()
        page.keyboard.press("End")
        page.keyboard.type(" (웹에서 수정)")
        page.keyboard.press("Shift+Enter")
        page.keyboard.type("둘째 줄")
        page.wait_for_timeout(1200)
        cell = page.locator("td .para").filter(has_text="전력")
        if cell.count():
            cell.first.click()
            page.keyboard.press("End")
            page.keyboard.type("★")
            page.wait_for_timeout(1200)
        page.screenshot(path=OUT / "04_edited.png")
        page.click("#tabEdits")
        page.wait_for_timeout(300)
        page.screenshot(path=OUT / "05_edits_tab.png")
        page.click("#tabPdf")
        page.wait_for_timeout(1500)
        page.screenshot(path=OUT / "06_pdf_tab.png")
        if not page.is_disabled("#verifyBtn"):
            page.click("#verifyBtn")
            page.wait_for_timeout(1000)
            print("edit summary:", wait_import(page), page.inner_text("#summary").replace("\n", " / "))
            page.wait_for_timeout(800)
            page.screenshot(path=OUT / "07_edit_verify.png")
            chip = page.locator(".chip.expected, .chip.shifted, .chip.unexpected")
            if chip.count():
                chip.first.click()
                page.wait_for_timeout(1500)
                page.screenshot(path=OUT / "08_compare_side.png")
                page.click('#compare .seg button[data-mode="diff"]')
                page.wait_for_timeout(1500)
                page.screenshot(path=OUT / "09_compare_diff.png")
                page.click("#cmpClose")
        page.click("#tabEdits")
        page.wait_for_timeout(300)
        rv = page.locator(".edit-item .btn", has_text="되돌리기")
        if rv.count():
            rv.first.click()
            page.wait_for_timeout(1200)
        page.screenshot(path=OUT / "11_after_revert.png")
        page.set_viewport_size({"width": 800, "height": 900})
        page.wait_for_timeout(600)
        page.screenshot(path=OUT / "10_narrow.png")
        b.close()
    (OUT / "console.txt").write_text("\n".join(logs), encoding="utf-8")
    print("console:", len(logs), "lines ->", OUT)


if __name__ == "__main__":
    main()

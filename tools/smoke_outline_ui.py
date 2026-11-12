"""개요(템플릿) 편집 화면 연기 시험(spec_hwpx_웹편집 ② §8) — 서버가 떠 있어야 한다(LLM 끔 권장: NFM_LLM_BACKEND=off).

python -X utf8 tools/smoke_outline_ui.py [http://127.0.0.1:18115] [출력 폴더]
연구개발계획서 양식을 열고 → 1·2단계(LLM 없이) → 새로 고침 → 손잡이(.ol-grip)·힌트 확인 → 「□ 연구개발기술…」 끝 Enter(하위 o) → Alt+Enter(뼈대) →
Alt+↓·Alt+↑ → 빈 줄 Backspace → 손잡이 끌기 → 실행 취소. 콘솔 오류는 console.txt."""
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18115"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "artifacts" / "ui_outline")
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


def texts_after(page, pid, n=8):
    return page.evaluate("""([pid, n]) => { const all = [...document.querySelectorAll('#doc .para[data-id]')]; const i = all.findIndex(p => p.dataset.id === pid);
      return all.slice(i, i + n).map(p => [p.dataset.id, p.textContent]); }""", [pid, n])


def main():
    wait_server()
    logs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1500, "height": 950}, device_scale_factor=1)
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
        page.goto(URL)
        page.wait_for_selector(".sample")
        page.click(f".sample >> text={SAMPLE}")
        page.wait_for_selector(".para")
        page.wait_for_timeout(800)
        doc = page.evaluate("location.hash").split("=", 1)[1]
        print("doc", doc)
        print("outline keys before:", page.get_attribute("#shortcutsBtn", "data-outline"))  # 옛 #editHint 글 자리 — 「1」 = 개요 편집 키 켜짐(shortcuts.js)
        run_stage(doc, 1)
        v = run_stage(doc, 2)
        print("stage2:", (v.get("stage2") or {}).get("summary") or v.get("stage2", {}).get("meta"))
        page.reload()
        page.wait_for_selector(".para[data-id=p970]")
        page.wait_for_timeout(1500)
        grips = page.locator(".ol-grip").count()
        print("grips:", grips, "| outline keys after:", page.get_attribute("#shortcutsBtn", "data-outline"))
        page.locator(".para[data-id=p970]").scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        page.screenshot(path=OUT / "01_marks_grips.png")
        # Enter 끝 → 하위 o 줄
        page.click(".para[data-id=p970]")
        page.keyboard.press("End")
        page.keyboard.press("Enter")
        page.wait_for_timeout(1500)
        rows = texts_after(page, "p970", 5)
        print("after Enter:", rows)
        new_o = rows[2][0]
        page.keyboard.type("새 항목")
        page.wait_for_timeout(1200)
        # Alt+Enter on the new o → skeleton o,-,⋅ after its subtree (it has none → right after)
        page.keyboard.press("Alt+Enter")
        page.wait_for_timeout(1500)
        rows = texts_after(page, new_o, 8)
        print("after Alt+Enter:", rows)
        page.screenshot(path=OUT / "02_enter_altenter.png")
        # Alt+↓ then Alt+↑ on the skeleton's first o
        sk_o = rows[2][0] if rows[1][1] == "" else rows[1][0]
        page.click(f".para[data-id={sk_o}]")
        page.keyboard.press("End")
        page.keyboard.press("Alt+ArrowDown")
        page.wait_for_timeout(1200)
        print("after Alt+Down:", texts_after(page, sk_o, 1))
        page.keyboard.press("Alt+ArrowUp")
        page.wait_for_timeout(1200)
        print("after Alt+Up:", texts_after(page, sk_o, 1))
        # Backspace on the empty ⋅ line of the skeleton
        rows = texts_after(page, sk_o, 6)
        dot = next((r for r in rows if r[1].strip() in ("⋅", "·")), None)
        if dot:
            page.click(f".para[data-id={dot[0]}]")
            page.keyboard.press("End")
            page.keyboard.press("Backspace")
            page.wait_for_timeout(1200)
            print("after Backspace (dot removed):", dot[0], page.locator(f".para[data-id={dot[0]}]").count() == 0)
        # drag: grip of p977 (o) to before p972 (o)
        g = page.locator(f".ol-grip[data-para=p977]")
        if g.count():
            g.first.drag_to(page.locator(".para[data-id=p972]"), target_position={"x": 20, "y": 2})
            page.wait_for_timeout(1500)
            print("after drag p977 before p972:", texts_after(page, "p970", 6))
        else:
            print("no grip for p977")
        page.screenshot(path=OUT / "03_after_ops.png")
        # undo all
        for _ in range(8):
            if page.locator("#undoBtn").is_disabled():
                break
            page.click("#undoBtn")
            page.wait_for_timeout(700)
            if page.locator("dialog[open], .confirm").count():
                page.keyboard.press("Enter")
        print("save state:", page.inner_text("#saveState"))
        (OUT / "console.txt").write_text("\n".join(logs), encoding="utf-8")
        print("console:", logs[:5] if logs else "none")
        b.close()


if __name__ == "__main__":
    main()

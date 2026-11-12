"""양식 정보 화면 연기 시험(spec_헤딩_추출 ② §12) — 서버가 떠 있어야 한다. **양식 정보 폴더는 꼭 임시 폴더로**(이 시험이 파일을 만들고 고친다):
NFM_LLM_BACKEND=off NFM_PDF=off NFM_WORKS/NFM_RENDER/NFM_HEADINGS/NFM_FORMS=<임시 폴더> python -m uvicorn app.server:app --port 18191

python -X utf8 tools/smoke_heading_forms_ui.py [http://127.0.0.1:18191] [출력 폴더] <NFM_FORMS 폴더>
기술수요조사서.hwpx 를 열고 → 「헤딩 추출」 탭 「추출·설정」 → 「양식 정보 · 없음」 → 2열에 새 양식 뼈대 → 저장(파일 생김 · 단추 이름 바뀜) → 「양식 없음」·「자동」 고르기 →
밖에서 고친 파일 위에 저장(409 → 한 번 더) → 저장 안 한 글로 닫기(묻기) → 2열 폭 넘침·콘솔 오류.
끝에 API 로: 저장소의 forms/연구개발계획서.md 를 임시 폴더에 넣고 연구개발계획서 양식을 올려 올린 원본 sha256 으로 맞는지 · 1단계 실행 기록에 양식 정보가 남는지."""
import shutil
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18191"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else ROOT / "artifacts" / "ui_heading_forms")
FORMS = Path(sys.argv[3]) if len(sys.argv) > 3 else None
OUT.mkdir(parents=True, exist_ok=True)
checks = []


def ok(name, cond, detail=""):
    checks.append((name, bool(cond), detail))
    print(("  ok  " if cond else "  FAIL") + f" {name}" + (f" — {detail}" if detail and not cond else ""))


def wait_server(timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if requests.get(URL + "/api/headings/forms", timeout=2).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise SystemExit("서버가 안 뜸(또는 양식 정보 끝점이 없는 옛 서버)")


def form_btn(page):
    return page.locator("#heads1 button", has_text="양식 정보")


def main():
    wait_server()
    info = requests.get(URL + "/api/headings/forms").json()
    if FORMS is None or Path(info["dir"] or "").resolve() != FORMS.resolve() or FORMS.resolve() == (ROOT / "forms").resolve():
        raise SystemExit(f"서버의 양식 정보 폴더({info['dir']})가 넘겨준 임시 폴더와 다릅니다 — 저장소 forms/ 를 고치지 않게 멈춤")
    for p in FORMS.glob("*.md"):
        p.unlink()
    logs, dialogs = [], []
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        page = br.new_page(viewport={"width": 1500, "height": 950})
        page.on("console", lambda m: logs.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))

        def on_dialog(d):
            dialogs.append(d.message)
            d.accept()
        page.on("dialog", on_dialog)
        page.goto(URL)
        page.wait_for_selector(".sample", state="attached")
        if not page.locator("#sampleSection").evaluate("d => d.open"):
            page.click("#sampleSection summary")
        page.click('.sample[aria-label="예제 기술수요조사서.hwpx 열기"]')
        page.wait_for_function("document.querySelector('.sheet .para') != null", timeout=120000)
        page.click("#tabHeads")
        page.click("#headsTabRun")
        page.click("#headsStageTab1")  # 추출·설정은 단계 탭 — 1단계 카드(양식 정보 단추)를 고른다(spec_헤딩_추출 ② §7 「단계 탭」)
        form_btn(page).wait_for(timeout=30000)
        ok("맞는 양식이 없으면 「양식 정보 · 없음」", form_btn(page).inner_text().strip() == "양식 정보 · 없음", form_btn(page).inner_text())

        # 새 양식 뼈대 → 저장
        form_btn(page).click()
        page.wait_for_selector("#headsDlg .hd-guide textarea")
        page.wait_for_function("heads.form && heads.form.cur && heads.form.cur.isNew")
        ta = page.locator("#headsDlg .hd-guide textarea")
        key = page.locator("#headsDlgTools input[type=text]")
        ok("2열이 열림(kind form)", page.evaluate("heads.dlg") == "form")
        ok("새 양식 뼈대 — 이름·조건 블록", key.input_value() == "기술수요조사서" and '"names": ["*기술수요조사서*"]' in ta.input_value(), key.input_value())
        save = page.locator("#headsDlgFoot button", has_text="저장")
        ok("뼈대는 바로 저장할 수 있음", save.is_enabled())
        page.screenshot(path=str(OUT / "1_new.png"))
        page.click("#headsDlgClose")  # 손대지 않은 뼈대는 닫아도 안 묻는다
        page.wait_for_function("document.getElementById('headsDlg').hidden")
        ok("손대지 않은 뼈대는 닫을 때 안 묻는다", not dialogs, str(dialogs))
        form_btn(page).click()
        page.wait_for_function("heads.form && heads.form.cur && heads.form.cur.isNew")
        ta.fill(ta.input_value() + "\n## 개요 체계\n- 연기 시험 SMOKEFACT\n")
        save.click()
        page.wait_for_function("heads.form && heads.form.cur && !heads.form.cur.isNew", timeout=15000)
        f = FORMS / "기술수요조사서.md"
        ok("저장하면 파일이 생김", f.is_file() and "SMOKEFACT" in f.read_text("utf-8"))
        page.wait_for_function("[...document.querySelectorAll('#heads1 button')].some(b => b.textContent.trim() === '양식 정보 · 기술수요조사서')", timeout=15000)
        ok("단추가 양식 이름으로", True)
        sel = page.locator("#headsDlgTools select")
        ok("고르기 목록 = 자동(올린 원본과 일치)", "올린 원본과 일치" in sel.locator("option:checked").inner_text(), sel.locator("option:checked").inner_text())
        ok("저장 뒤 저장 단추 꺼짐 · 이름 칸 숨김", save.is_disabled() and not key.is_visible())
        ok("발치에 파일 경로", "기술수요조사서.md" in page.locator("#headsDlgFoot .muted").inner_text())
        page.screenshot(path=str(OUT / "2_saved.png"))

        # 양식 없음 → 자동
        sel.select_option("")
        page.wait_for_function("heads.form && heads.form.view && heads.form.view.choice === ''")
        page.wait_for_function("[...document.querySelectorAll('#heads1 button')].some(b => b.textContent.trim() === '양식 정보 · 없음')", timeout=15000)
        ok("「양식 없음」 → 글상자 숨김 · 단추 「없음」", not ta.is_visible())
        sel.select_option("@auto")
        page.wait_for_function("heads.form && heads.form.view && heads.form.view.choice === null && heads.form.cur && !heads.form.cur.isNew")
        ok("「자동」 → 다시 그 양식", "SMOKEFACT" in ta.input_value())

        # 밖에서 고친 파일 위에 저장 — 409 → 한 번 더
        f.write_text(f.read_text("utf-8") + "- 편집기에서 덧붙임 OUTSIDE\n", encoding="utf-8")
        ta.fill(ta.input_value() + "- 화면에서 덧붙임 INSIDE\n")
        save.click()
        page.wait_for_function("document.querySelector('#headsDlg .hd-msg').textContent.includes('먼저 고쳤습니다')", timeout=15000)
        ok("밖에서 고친 파일 위 저장은 막음(409)", "INSIDE" not in f.read_text("utf-8") and "INSIDE" in ta.input_value())
        save.click()
        page.wait_for_function("heads.form && heads.form.cur && heads.form.cur.text.includes('INSIDE')", timeout=15000)
        ok("한 번 더 누르면 내 글로 저장", "INSIDE" in f.read_text("utf-8") and save.is_disabled())

        # 이미 양식이 맞은 문서에서 「새 양식 정보」 — 조건이 같아도 새 양식이 이 문서에 맞는다(직접 고른 것으로)
        page.click("#headsDlgTools button:has-text('새 양식 정보')")
        page.wait_for_function("heads.form && heads.form.cur && heads.form.cur.isNew")
        ok("둘째 양식의 이름은 겹치지 않게", key.input_value() == "기술수요조사서_2", key.input_value())
        ta.fill(ta.input_value() + "\n## 개요 체계\n- 둘째 양식 SECOND\n")
        save.click()
        page.wait_for_function("heads.form && heads.form.cur && !heads.form.cur.isNew && heads.form.cur.key === '기술수요조사서_2'", timeout=15000)
        page.wait_for_function("[...document.querySelectorAll('#heads1 button')].some(b => b.textContent.trim() === '양식 정보 · 기술수요조사서_2')", timeout=15000)
        ok("새로 만든 양식이 이 문서의 양식이 됨", sel.input_value() == "기술수요조사서_2" and (FORMS / "기술수요조사서_2.md").is_file(), sel.input_value())
        sel.select_option("@auto")
        page.wait_for_function("heads.form && heads.form.view && heads.form.view.choice === null && heads.form.cur && heads.form.cur.key === '기술수요조사서'")
        ok("「자동」 은 조건이 같으면 앞선 키", "INSIDE" in ta.input_value())

        # 폭 — 2열·패널이 넘치지 않음(480px 열)
        over = page.evaluate("""() => { const c = document.getElementById('headsDlg'); c.style.width = '480px';
          const t = document.getElementById('headsDlgTools'); return [c.scrollWidth - c.clientWidth, t.scrollWidth - t.clientWidth]; }""")
        ok("2열 480px 에서 가로 넘침 없음", over[0] <= 1 and over[1] <= 1, str(over))
        page.screenshot(path=str(OUT / "3_480.png"))

        # 저장 안 한 글로 닫기 — 묻는다
        n0 = len(dialogs)
        ta.fill(ta.input_value() + "- 버릴 글\n")
        page.click("#headsDlgClose")
        page.wait_for_function("document.getElementById('headsDlg').hidden")
        ok("저장 안 한 글은 닫을 때 묻는다", len(dialogs) == n0 + 1 and "양식 정보" in dialogs[-1], str(dialogs[n0:]))
        ok("버린 글은 파일에 없음", "버릴 글" not in f.read_text("utf-8"))
        br.close()
    logs = [m for m in logs if "409 (Conflict)" not in m]  # 위 409 시험의 응답을 브라우저가 콘솔에 적은 줄
    ok("콘솔 오류 0", not logs, " | ".join(logs[:3]))

    # API — 저장소의 연구개발계획서 양식 정보가 양식 원본과 맞는지 · 실행 기록
    shutil.copyfile(ROOT / "forms" / "연구개발계획서.md", FORMS / "연구개발계획서.md")
    rnd = ROOT / "samples" / "연구개발계획서_양식.hwpx"
    d = requests.post(URL + "/api/docs", files={"file": ("이름을 바꾼 계획서.hwpx", rnd.read_bytes())}).json()["docId"]
    v = requests.get(f"{URL}/api/docs/{d}/headings/form").json()
    ok("연구개발계획서 양식 — 이름이 달라도 올린 원본으로 맞음", v["form"] and v["form"]["key"] == "연구개발계획서" and v["form"]["how"] == "sha256", str(v["form"]))
    requests.post(f"{URL}/api/docs/{d}/headings", json={"stage": 1, "llm": False})
    end = time.time() + 120
    h = {}
    while time.time() < end:
        h = requests.get(f"{URL}/api/docs/{d}/headings").json()
        if h["job"] and h["job"]["status"] != "running":
            break
        time.sleep(0.5)
    ok("1단계 실행 기록에 양식 정보 sha1", h.get("stage1") and h["stage1"]["meta"]["guides"].get("form") == v["form"]["sha1"], str((h.get("job") or {}).get("status")))
    requests.delete(f"{URL}/api/works/{d}")
    bad = [c for c in checks if not c[1]]
    print(f"\n{len(checks) - len(bad)}/{len(checks)} 통과" + (f" — 실패: {[c[0] for c in bad]}" if bad else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

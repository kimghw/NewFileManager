"""「고친 문단 확정」 화면 검사(spec_작업 ② §8) — 임시 서버에 예제(기술수요조사서.hwpx)를 올리고 Playwright 로: 글 고침 → 확정 → 고친 문단 0 →
더 고침 → 확정본으로 되돌리기 → 버리기 → 확정 기록 펼침 → 이전 확정 복원 → 기록 탭 → (pdf) 새 기준 PDF → 새로 고침 뒤 이어짐. 콘솔 오류 0 이어야 한다.
사용자 서버(8114)가 아니라 임시 서버에 돌린다(작업이 하나 생긴다) — CLAUDE.md 「웹서버」:
  NFM_LLM_BACKEND=off NFM_PDF=off NFM_WORKS=<임시> NFM_RENDER=<임시> python -m uvicorn app.server:app --port 18186   (끝나면 끈다)
  python -X utf8 tools/smoke_commits_ui.py http://127.0.0.1:18186 <그림 폴더> [pdf]     # pdf = 한글 PDF 를 켠 서버일 때 새 기준 PDF 까지 확인"""
import json
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

URL, OUT = sys.argv[1].rstrip("/"), Path(sys.argv[2])
PDF = len(sys.argv) > 3 and sys.argv[3] == "pdf"
OUT.mkdir(parents=True, exist_ok=True)
SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "기술수요조사서.hwpx"
results, errors = [], []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  ok  " if ok else "  FAIL") + f" {name}" + (f" — {detail}" if detail and not ok else ""))


def api(path, method="GET", body=None):
    req = urllib.request.Request(URL + path, method=method, data=None if body is None else json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def upload():
    boundary = "----nfmcheck"
    data = SAMPLE.read_bytes()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"sample.hwpx\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(URL + "/api/docs", method="POST", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))["docId"]


def wait_import(wid, timeout=300):
    end = time.time() + timeout
    while time.time() < end:
        v = api(f"/api/docs/{wid}/verify")
        if "import" in v and not v["import"]["running"]:
            return v
        time.sleep(0.3)
    raise AssertionError("가져오기 검증이 끝나지 않음")


wid = upload()
v0 = wait_import(wid)
print("work", wid, "· import", v0["import"]["status"], "· pdfs", v0.get("pdfs"))

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 950})
    page.add_init_script("try { localStorage.setItem('nfm.toolMore', '1'); } catch (e) {}")  # 패널 머리 오른쪽 묶음(검증·PDF·기록)을 펴 둔다 — 접힘은 smoke_panel_head_ui.py(2026-11-16)
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("dialog", lambda d: d.accept())
    page.goto(f"{URL}/#w={wid}")
    page.wait_for_function("document.querySelector('.sheet .para') != null", timeout=120000)
    page.click("#tabEdits")
    page.wait_for_selector("#commitBox:not([hidden])")

    ev = page.evaluate
    sum_text = lambda: ev("document.getElementById('commitSum').textContent")  # noqa: E731
    badge = lambda: ev("document.getElementById('editsBadge').textContent")  # noqa: E731
    edited_dom = lambda: ev("document.querySelectorAll('#doc .para.edited').length")  # noqa: E731
    save_state = lambda: ev("document.getElementById('saveState').textContent")  # noqa: E731

    check("처음: 기준 = 올린 원본 · 고친 것 없음", "올린 원본" in sum_text() and "고친 것 없음" in sum_text(), sum_text())
    check("처음: 확정·버리기 꺼짐", ev("document.getElementById('commitBtn').disabled && document.getElementById('discardBtn').disabled"))
    page.wait_for_function("document.getElementById('commitCount').textContent === '0'")
    check("처음: 확정 기록 0(올린 원본 한 줄)", ev("document.querySelectorAll('#commitList .commit-item').length") == 1)

    # 글 문단 셋을 고친다(타자 → 450ms 뒤 서버 반영)
    ids = ev("""[...document.querySelectorAll('#doc .para')].filter(p => p.isContentEditable && p.textContent.trim().length > 3).slice(2, 5).map(p => p.dataset.id)""")
    for k, pid in enumerate(ids):
        page.click(f'.para[data-id="{pid}"]')
        page.keyboard.press("End")
        page.keyboard.type(f"★{k}")
    page.wait_for_function("document.getElementById('editsBadge').textContent === '3' && !state.timers.size && !state.inflight", timeout=20000)
    check("고침: 고친 문단 3 · 문서 표시 3", badge() == "3" and edited_dom() == 3, f"{badge()} / {edited_dom()}")
    check("고침: 확정 줄에 「고친 문단 3 (글 3)」", "고친 문단 3" in sum_text() and "글 3" in sum_text(), sum_text())
    check("고침: 확정 단추 켜짐", not ev("document.getElementById('commitBtn').disabled"))
    page.screenshot(path=str(OUT / "1_edited.png"))

    # 확정
    texts_before = ev("JSON.stringify(state.texts)")
    sheets_before = ev("document.querySelectorAll('#doc .sheet').length")
    page.fill("#commitMsg", "첫 확정")
    page.click("#commitBtn")
    page.wait_for_function("state.base === 1 && !state.commitBusy", timeout=60000)
    check("확정: 고친 문단 0 · 문서 표시 0", badge() == "0" and edited_dom() == 0, f"{badge()} / {edited_dom()}")
    check("확정: 기준 확정 1 · 고친 것 없음", "확정 1" in sum_text() and "고친 것 없음" in sum_text(), sum_text())
    check("확정: 문서 글 그대로(다시 그리지 않음)", ev("JSON.stringify(state.texts)") == texts_before and ev("document.querySelectorAll('#doc .sheet').length") == sheets_before)
    check("확정: 상단 「확정 1 · 고친 것 없음」", "확정 1" in save_state(), save_state())
    check("확정: 메시지 칸 비움 · 단추 꺼짐", ev("document.getElementById('commitMsg').value === '' && document.getElementById('commitBtn').disabled"))
    page.wait_for_function("document.getElementById('commitCount').textContent === '1'", timeout=20000)
    first = ev("document.querySelector('#commitList .commit-item summary').textContent")
    check("확정: 확정 기록 맨 위 = #1 첫 확정 · 기준 · 3문단", all(x in first for x in ("#1", "첫 확정", "기준", "3문단")), first)
    check("확정: PDF 탭 왼쪽 단추 「확정 1」", ev("""document.querySelector('#pdfSeg [data-which="original"]').textContent""") == "확정 1")
    check("확정: 실행 취소 꺼짐", ev("document.getElementById('undoBtn').disabled"))
    page.screenshot(path=str(OUT / "2_committed.png"))

    # 확정 뒤 더 고침 → 그 문단만 고친 문단, 원래 글 = 확정본 글
    pid = ids[0]
    page.click(f'.para[data-id="{pid}"]')
    page.keyboard.press("End")
    page.keyboard.type("◆")
    page.wait_for_function("document.getElementById('editsBadge').textContent === '1' && !state.timers.size && !state.inflight", timeout=20000)
    check("확정 뒤 고침: 고친 문단 1", badge() == "1" and edited_dom() == 1)
    check("확정 뒤 고침: 원래 글 = 확정본 글(★0 포함)", ev(f"state.original['{pid}'].endsWith('★0') && state.texts['{pid}'].endsWith('★0◆')"))
    page.click("#tabEdits")
    check("확정 뒤 고침: 「확정본으로 되돌리기」 단추", ev("document.querySelector('#editsList .edit-item .btn').textContent") == "확정본으로 되돌리기")
    diff = ev("document.querySelector('#editsList .diff').textContent")
    check("확정 뒤 고침: 목록의 차이는 ◆ 만", ev("document.querySelector('#editsList .diff ins').textContent") == "◆" and ev("document.querySelector('#editsList .diff del')") is None, diff)
    page.click("#editsList .edit-item .btn")
    page.wait_for_function("document.getElementById('editsBadge').textContent === '0'", timeout=20000)
    check("되돌리기: 확정본 글로(★0 남고 ◆ 없음)", ev(f"""document.querySelector('.para[data-id="{pid}"]').textContent.endsWith('★0')"""))
    check("되돌리기: 파일 = 확정 1 과 같음", "확정 1" in save_state(), save_state())

    # 모두 되돌리기(#discardBtn — 전 이름 「버리기」)
    check("모두 되돌리기: 단추 이름", ev("document.getElementById('discardBtn').textContent") == "모두 되돌리기")
    for k, x in enumerate(ids[:2]):
        page.click(f'.para[data-id="{x}"]')
        page.keyboard.press("End")
        page.keyboard.type(f"✕{k}")
    page.wait_for_function("document.getElementById('editsBadge').textContent === '2' && !state.timers.size && !state.inflight", timeout=20000)
    page.click("#tabEdits")
    page.click("#discardBtn")  # confirm 은 자동 수락
    page.wait_for_function("document.getElementById('editsBadge').textContent === '0' && !state.commitBusy", timeout=60000)
    check("버리기: 고친 문단 0 · 기준 확정 1 그대로", ev("state.base") == 1 and edited_dom() == 0)
    check("버리기: 글이 확정본으로(✕ 없음)", ev(f"""!document.querySelector('.para[data-id="{ids[0]}"]').textContent.includes('✕') && document.querySelector('.para[data-id="{ids[0]}"]').textContent.endsWith('★0')"""))
    check("버리기: 확정 기록은 그대로 1", ev("document.getElementById('commitCount').textContent") == "1")

    # 둘째 확정
    page.click(f'.para[data-id="{ids[2]}"]')
    page.keyboard.press("End")
    page.keyboard.type("●")
    page.wait_for_function("document.getElementById('editsBadge').textContent === '1' && !state.timers.size && !state.inflight", timeout=20000)
    page.click("#tabEdits")
    page.click("#commitBtn")
    page.wait_for_function("state.base === 2 && !state.commitBusy", timeout=60000)
    page.wait_for_function("document.getElementById('commitCount').textContent === '2'", timeout=20000)

    # 확정 기록 펼침 — 확정 2 의 변경 목록
    page.click("#commitLog > summary")
    page.click('#commitList .commit-item[data-n="2"] > summary')
    page.wait_for_selector('#commitList .commit-item[data-n="2"] .commit-changes li .diff', timeout=20000)
    body2 = ev("""document.querySelector('#commitList .commit-item[data-n="2"] .commit-body').textContent""")
    check("확정 기록: 확정 2 변경 목록에 ● 추가", ev("""document.querySelector('#commitList .commit-item[data-n="2"] .diff ins').textContent""") == "●", body2[:120])
    check("확정 기록: 기준인 확정의 복원 단추는 꺼짐", ev("""[...document.querySelectorAll('#commitList .commit-item[data-n="2"] .commit-acts button')].every(b => b.disabled)"""))
    check("확정 기록: 파일 받기 링크", ev("""document.querySelector('#commitList .commit-item[data-n="2"] .commit-acts a').getAttribute('href')""") == f"/api/works/{wid}/commits/2/file")
    # 폭 320·480 에서 확정 상자가 넘치지 않는지(design.md §1-8)
    for w in (320, 480):
        ev(f"document.documentElement.style.setProperty('--panel', '{w}px')")
        over = ev("""(() => { const b = document.getElementById('commitBox'); return [b.scrollWidth - b.clientWidth, ...[...b.querySelectorAll('.commit-row, .commit-item > summary, .commit-acts')].map(e => e.scrollWidth - e.clientWidth)]; })()""")
        check(f"폭 {w}px: 확정 상자 가로 넘침 없음", max(over) <= 1, str(over))
        page.screenshot(path=str(OUT / f"3_log_{w}.png"), clip=ev("""(() => { const r = document.getElementById('panel').getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: Math.min(r.height, 620)}; })()"""))
    ev("document.documentElement.style.removeProperty('--panel')")

    # 이전 확정(1)으로 복원 → 새 확정 3
    page.click('#commitList .commit-item[data-n="1"] > summary')
    page.wait_for_selector('#commitList .commit-item[data-n="1"] .commit-acts button:not([disabled])', timeout=20000)
    page.click('#commitList .commit-item[data-n="1"] .commit-acts button')
    page.wait_for_function("state.base === 3 && !state.commitBusy", timeout=60000)
    page.wait_for_function("document.querySelector('.sheet .para') != null", timeout=60000)
    check("복원: 기준 확정 3 · 고친 문단 0", ev("state.base") == 3 and badge() == "0" and edited_dom() == 0)
    check("복원: 문서가 확정 1 상태(● 없음, ★2 있음)", ev(f"""(() => {{ const t = document.querySelector('.para[data-id="{ids[2]}"]').textContent; return !t.includes('●') && t.endsWith('★2'); }})()"""))
    page.wait_for_function("document.getElementById('commitCount').textContent === '3'", timeout=20000)
    top = ev("document.querySelector('#commitList .commit-item summary').textContent")
    check("복원: 확정 기록 맨 위 = #3 확정 1 로 복원 · 기준", all(x in top for x in ("#3", "확정 1 로 복원", "기준")), top)

    # 기록 탭에 확정·버리기·복원 줄
    page.click("#tabLog")
    page.wait_for_selector("#logList .log-item.k-restore", timeout=20000)
    kinds = ev("[...document.querySelectorAll('#logList .log-item .log-kind')].map(e => e.textContent)")
    check("기록: 확정 2 · 모두 되돌리기 1 · 확정 복원 1", kinds.count("확정") == 2 and kinds.count("모두 되돌리기") == 1 and kinds.count("확정 복원") == 1, str(kinds[:12]))

    if PDF:  # 새 기준의 가져오기 검증(한글 PDF)이 끝나면 쪽 매핑·PDF 가 새 기준 것으로
        wait_import(wid)
        page.click("#tabPdf")
        page.wait_for_function("state.verify && state.verify.import && !state.verify.import.running && state.mapping && !state.mappingStale", timeout=300000)
        page.wait_for_function("document.getElementById('pdfImg').complete && document.getElementById('pdfImg').naturalWidth > 0", timeout=60000)
        check("PDF: 기준 PDF 그림 주소에 b3 · 그림 읽힘", "v=b3" in ev("document.getElementById('pdfImg').src"), ev("document.getElementById('pdfImg').src"))
        check("PDF: 왼쪽 단추 「확정 3」", ev("""document.querySelector('#pdfSeg [data-which="original"]').textContent""") == "확정 3")
        page.screenshot(path=str(OUT / "5_pdf.png"))

    # 새로 고침 뒤에도 기준·확정 기록이 이어진다
    page.reload()
    page.wait_for_function("document.querySelector('.sheet .para') != null", timeout=120000)
    page.click("#tabEdits")
    page.wait_for_function("document.getElementById('commitCount').textContent === '3'", timeout=20000)
    check("새로 고침: 기준 확정 3 · 고친 것 없음", ev("state.base") == 3 and "확정 3" in sum_text() and "고친 것 없음" in sum_text(), sum_text())
    page.click("#commitLog > summary")
    page.screenshot(path=str(OUT / "4_reloaded.png"))

    # 작업 목록에 「확정 3」
    w = next(x for x in api("/api/works") if x["id"] == wid)
    check("작업 목록: commits 3 · edited 0", w.get("commits") == 3 and w.get("edited") == 0, str({k: w.get(k) for k in ("commits", "edited")}))
    browser.close()

bad = [r for r in results if not r[1]]
print(f"\n{len(results) - len(bad)}/{len(results)} 통과 · 콘솔 오류 {len(errors)}")
for e in errors[:10]:
    print("  ", e)
sys.exit(1 if bad or errors else 0)

"""자리마다의 작성 지침 — 화면(spec_병합 ② §5-11 · app/static/place_guides.js · design.md §4 「작성 지침 단추」) 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

연차보고서 서식(저장소 samples)을 올리고 헤딩 추출 1·2·3단계(LLM 없이)를 돌린 뒤 작성 지침을 저장한다(POST …/form-guides — 1단계 「문서 검토」 가 하는 것).

 1. 지침이 있는 헤딩마다 쪽 오른쪽 여백에 「지침」 단추(수) — 목록 끝점의 헤딩 수만큼 · 본문 오른끝 밖(본문 글을 안 가림) · 그 헤딩 줄 높이 · 「문서 표시」 를 꺼도 보임.
 2. 단추를 누르면 2열 「작성 지침 — 이 자리」(kind placeGuides): 문서의 작성 지침(「※ 2page 이내 요약 작성」) · 내가 적은 지침(빈 입력) · 양식의 매칭 지침 · 누가 읽나 · 단추 눌림(.on).
 3. 적고 「저장」 → 단추가 사람 지침 꼴(.user · 점 · 수 +1) · 끝점에 남음 · 문서 차례(rev)는 그대로(문서는 안 바뀜).
 4. 새로 고침 → 그대로(.user) · 열면 적은 글.
 5. 판이 바뀐 뒤 저장(다른 화면이 고침 = 끝점으로 PUT) → 409 알림 · 적던 글은 입력에 남음 → 다시 저장하면 됨.
 6. 「지우기」(확인 창) → 사람 지침 없음 · 수 그대로(문서의 것).
 7. 지침 없는 헤딩에 글쓰기 자리를 두면 그 줄에만 옅은 「지침 적기」 → 누르면 열 → 적고 저장 → 늘 보이는 단추(.user)로.
 8. 배율을 바꿔도 단추가 그 헤딩 줄 높이 · 쪽 보기를 끄면 안 보임.
 9. 표 모서리의 「작성요령 · 표 지침」 열에 「저장해 둔 문서 지침 n」 절(그 표의 저장본 수).
10. 좁은 창(1100px)에서도 본문 글을 가리지 않음 · 페이지 오류 없음.

    python -X utf8 tools/smoke_place_guides_ui.py <출력 폴더> [--port 18531]
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
REPORT_FORM = ROOT / "samples" / "국가RnD_서식" / "KEIT_표준서식_260320" / "1. 산업기술혁신사업 연차보고서 서식_260319.hwpx"
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18531)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "PYTHONUTF8": "1"}
for k, name in (("NFM_TASKS", "tasks.json"), ("NFM_FORM_FILES", "form_files"), ("NFM_AGENT_NOTES", "agent_notes.json"), ("NFM_REQS", "requirements.json"), ("NFM_TOOL_NAMES", "tool_names.json")):
    env.setdefault(k, str(tmp / name))   # 혼자 돌려도 사용자 설정 파일을 안 건드리게(run_ui_gates 가 돌리면 그쪽 임시 파일)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails, dialogs = [], [], []
COL = "#headsDlg"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:700] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def wait_server(timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if requests.get(base + "/api/status", timeout=2).ok:
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
        v = requests.get(f"{base}/api/docs/{doc}/headings", timeout=60).json()
        if not v.get("job") or v["job"].get("status") != "running":
            return v
        time.sleep(0.4)
    raise SystemExit("단계가 안 끝남")


def plist(doc):
    r = requests.get(f"{base}/api/docs/{doc}/place-guides", timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def phead(doc, pid):
    r = requests.get(f"{base}/api/docs/{doc}/place-guides/heads/{pid}", timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


# 문서의 「지침」 단추들 — 자리(화면 px)와 그 헤딩 줄 · 그 쪽 본문 오른끝
BTNS = """() => [...document.querySelectorAll('#doc .sheet > .pg-btn:not(.chain)')].map((b) => {
  const r = b.getBoundingClientRect(), p = document.querySelector(`#doc .para[data-id="${CSS.escape(b.dataset.pg)}"]`), pr = p ? p.getBoundingClientRect() : null;
  const sheet = b.parentElement, body = sheet.querySelector(':scope > .sheet-body'), br = body ? body.getBoundingClientRect() : null, sr = sheet.getBoundingClientRect();
  return { id: b.dataset.pg, text: b.textContent.trim(), user: b.classList.contains('user'), caret: b.classList.contains('caret'), on: b.classList.contains('on'),
    dot: !!b.querySelector('.pg-dot'), title: b.title, left: r.left, right: r.right, top: r.top, h: r.height, w: r.width, visible: r.width > 0 && b.checkVisibility(),
    paraTop: pr ? pr.top : null, bodyRight: br ? br.right : null, sheetRight: sr.right };
})"""
COLV = """() => { const c = document.getElementById('headsDlg'); if (!c || c.hidden) return null;
  const sec = (k) => c.querySelector(`[data-pg-sec="${k}"]`);
  return { kind: c.dataset.kind, title: document.getElementById('headsDlgTitle').textContent, note: document.getElementById('headsDlgNote').textContent,
    doc: sec('doc') ? [...sec('doc').querySelectorAll('li')].map((li) => li.textContent) : null, docHead: sec('doc') ? sec('doc').querySelector('h3').textContent : null,
    ta: (c.querySelector('textarea.pg-ta') || {}).value, matchHead: sec('match') ? sec('match').querySelector('h3').textContent : null,
    who: (c.querySelector('.pg-who') || {}).textContent || '', btns: [...c.querySelectorAll('button')].map((b) => b.textContent) }; }"""


def btn_of(page, pid):
    return next((b for b in page.evaluate(BTNS) if b["id"] == pid), None)


def open_work(page, wid):
    page.evaluate("(id) => { location.hash = '#w=' + id; }", wid)
    page.reload()
    page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=wid, timeout=300000)


def wait_btns(page, n, timeout=30000):
    page.wait_for_function("(n) => document.querySelectorAll('#doc .sheet > .pg-btn:not(.caret):not(.chain)').length >= n", arg=n, timeout=timeout)


def show(page, pid):  # 그 헤딩을 보이는 곳으로 — 단추를 누를 수 있게
    page.evaluate("(id) => { const p = document.querySelector(`#doc .para[data-id=\"${CSS.escape(id)}\"]`); p && p.scrollIntoView({ block: 'center' }); }", pid)
    page.wait_for_timeout(250)


try:
    wait_server()
    d = requests.post(base + "/api/docs", files={"file": (REPORT_FORM.name, REPORT_FORM.read_bytes())}, timeout=300).json()["docId"]
    for st in (1, 2, 3):
        run_stage(d, st)
    fg = requests.post(f"{base}/api/docs/{d}/form-guides", timeout=120)
    check("작성 지침 저장(1단계가 하는 것)", fg.status_code == 200, fg.text[:300])
    L = plist(d)
    heads0 = {h["id"]: h for h in L["heads"]}
    check("목록 끝점 — 지침이 있는 헤딩 · 표", len(L["heads"]) >= 3 and len(L["tables"]) >= 1, (len(L["heads"]), len(L["tables"])))
    H = "p1051" if "p1051" in heads0 else L["heads"][0]["id"]   # 「1. 연구개발과제의 개요 ※ 2page 이내 요약 작성」
    rev0 = L["rev"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 950})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)

        def on_dialog(dlg):
            dialogs.append(dlg.message)
            dlg.accept()
        page.on("dialog", on_dialog)
        page.goto(base)
        page.evaluate("() => { try { localStorage.clear(); } catch {} }")
        open_work(page, d)
        wait_btns(page, len(heads0))

        # ---- 1. 단추 — 헤딩마다 · 오른쪽 여백(본문 글을 안 가림) · 그 줄 높이 · 문서 표시와 따로
        bs = page.evaluate(BTNS)
        ids = {b["id"] for b in bs if not b["caret"]}
        check("헤딩마다 단추 하나(목록 끝점의 헤딩 = 화면의 단추)", ids == set(heads0), (sorted(ids ^ set(heads0))[:10], len(ids), len(heads0)))
        check("단추 글 = 지침 수 · 사람 지침 없음(.user 아님)", all(b["text"] == str(heads0[b["id"]]["n"]) and not b["user"] for b in bs if b["id"] in heads0), [(b["id"], b["text"]) for b in bs][:6])
        check("오른쪽 여백 — 본문 오른끝 밖 · 종이 안(넓은 창)", all(b["bodyRight"] is not None and b["left"] >= b["bodyRight"] + 2 and b["right"] <= b["sheetRight"] + 1 for b in bs),
              [(b["id"], round(b["left"]), round(b["bodyRight"] or 0), round(b["right"]), round(b["sheetRight"])) for b in bs][:6])
        check("그 헤딩 줄 높이(위끝 ±4px · 겹치면 아래로)", all(b["paraTop"] is not None and -4 <= b["top"] - b["paraTop"] <= 40 for b in bs), [(b["id"], round(b["top"] - (b["paraTop"] or 0))) for b in bs][:8])
        check("크기 18px · 풍선 도움말에 수와 누르면 열림", all(17 <= b["h"] <= 19 and "작성 지침" in b["title"] and "오른쪽 열" in b["title"] for b in bs), bs[0])
        show(page, H)
        page.screenshot(path=str(OUT / "place_guides_doc.png"))
        if page.evaluate("() => typeof tplMarksOn === 'function' && tplMarksOn()"):
            page.evaluate("() => tplMarksToggle()")
        page.wait_for_timeout(300)
        check("「문서 표시」 를 꺼도 단추는 그대로", len([b for b in page.evaluate(BTNS) if not b["caret"]]) == len(heads0))
        page.evaluate("() => tplMarksToggle()")
        page.wait_for_timeout(200)

        # ---- 2. 누르면 2열
        show(page, H)
        page.click(f'#doc .sheet > .pg-btn[data-pg="{H}"]')
        page.wait_for_function("() => { const c = document.getElementById('headsDlg'); return c && !c.hidden && c.dataset.kind === 'placeGuides' && c.querySelector('textarea.pg-ta'); }", timeout=20000)
        c = page.evaluate(COLV)
        want_doc = [g["text"] for g in phead(d, H)["doc"]]
        check("2열 「작성 지침 — 이 자리」 · 머리 아래 그 헤딩 글", c["title"] == "작성 지침 — 이 자리" and "1. 연구개발과제의 개요" in c["note"] if H == "p1051" else c["title"] == "작성 지침 — 이 자리", c)
        check("① 문서의 작성 지침(끝점의 것 그대로 · 읽기만)", c["doc"] is not None and len(c["doc"]) == len(want_doc) and all(any(t[:20] in x for x in c["doc"]) for t in want_doc)
              and (H != "p1051" or any("2page" in x for x in c["doc"])), (c["doc"], want_doc))
        check("② 내가 적은 지침 = 빈 입력 · ③ 양식의 매칭 지침 절 · ④ 누가 읽나", c["ta"] == "" and c["matchHead"] and c["matchHead"].startswith("양식의 매칭 지침")
              and "표 대응" in c["who"] and "원본에서만" in c["who"] and "저장" in c["btns"] and "문서에서 보기" in c["btns"], c)
        check("연 헤딩의 단추가 눌림(.on)", (btn_of(page, H) or {}).get("on") is True)
        page.screenshot(path=str(OUT / "place_guides_col.png"))

        # ---- 3. 적고 저장
        TEXT = "당해 차년도의 실적만 · 2쪽 이내 요약(시험)"
        page.fill(f"{COL} textarea.pg-ta", TEXT)
        page.click(f"{COL} button:has-text('저장')")
        page.wait_for_function("(id) => { const b = document.querySelector(`#doc .sheet > .pg-btn[data-pg=\"${id}\"]`); return b && b.classList.contains('user'); }", arg=H, timeout=10000)
        b = btn_of(page, H)
        n0 = heads0[H]["n"]
        check("저장 → 단추가 사람 지침 꼴(.user · 점 · 수 +1)", b and b["user"] and b["dot"] and b["text"] == str(n0 + 1) and "내가 적은 지침 있음" in b["title"], b)
        v = phead(d, H)
        check("끝점에 남음 · 문서는 안 바뀜(rev 그대로)", (v["user"] or {}).get("text") == TEXT and plist(d)["rev"] == rev0, (v["user"], plist(d)["rev"], rev0))
        page.screenshot(path=str(OUT / "place_guides_saved.png"))

        # ---- 4. 새로 고침
        open_work(page, d)
        wait_btns(page, len(heads0))
        page.wait_for_function("(id) => { const b = document.querySelector(`#doc .sheet > .pg-btn[data-pg=\"${id}\"]`); return b && b.classList.contains('user'); }", arg=H, timeout=15000)
        show(page, H)
        page.click(f'#doc .sheet > .pg-btn[data-pg="{H}"]')
        page.wait_for_function("() => { const c = document.getElementById('headsDlg'); return c && !c.hidden && c.dataset.kind === 'placeGuides' && c.querySelector('textarea.pg-ta'); }", timeout=20000)
        check("새로 고침 → 그대로(.user) · 열면 적은 글", page.evaluate(COLV)["ta"] == TEXT)

        # ---- 5. 판이 바뀐 뒤 저장 → 409 · 적던 글은 남음 → 다시 저장
        other = requests.put(f"{base}/api/docs/{d}/place-guides/heads/{H}", json={"text": TEXT + " (다른 화면)"}, timeout=30)
        check("다른 화면이 고침(판 +1)", other.status_code == 200, other.text[:200])
        T2 = TEXT + " · 고침"
        page.fill(f"{COL} textarea.pg-ta", T2)
        page.click(f"{COL} button:has-text('저장')")
        page.wait_for_function("() => { const t = document.getElementById('toast'); return t && !t.hidden && t.textContent.includes('그 사이'); }", timeout=10000)
        page.wait_for_timeout(600)
        check("409 → 알림 · 다시 읽고 적던 글은 입력에 남음", page.evaluate(COLV)["ta"] == T2, page.evaluate(COLV)["ta"])
        page.click(f"{COL} button:has-text('저장')")
        page.wait_for_function("(t) => { const c = document.querySelector('#headsDlg .pg-cnt'); return c && !c.textContent.includes('저장 안 함'); }", arg=T2, timeout=10000)
        check("다시 저장하면 됨", (phead(d, H)["user"] or {}).get("text") == T2)

        # ---- 6. 지우기
        n_dlg = len(dialogs)
        page.click(f"{COL} button:has-text('지우기')")
        page.wait_for_function("(id) => { const b = document.querySelector(`#doc .sheet > .pg-btn[data-pg=\"${id}\"]`); return b && !b.classList.contains('user'); }", arg=H, timeout=10000)
        b = btn_of(page, H)
        check("「지우기」(확인 창) → 사람 지침 없음 · 수는 문서의 것", len(dialogs) == n_dlg + 1 and phead(d, H)["user"] is None and b and b["text"] == str(n0) and not b["dot"], (dialogs[n_dlg:], b))

        # ---- 7. 지침 없는 헤딩 — 글쓰기 자리를 두면 「지침 적기」
        free = page.evaluate("""(have) => { for (const p of document.querySelectorAll('#doc .sheet .para[data-id]')) {
            if (p.closest('td') || have.includes(p.dataset.id)) continue; const ol = outlineLine(p);
            if (ol && (ol.role || 'heading') === 'heading' && (ol.flow || 'body') === 'body' && p.textContent.trim().length > 3) return p.dataset.id; } return null; }""", list(heads0))
        check("지침 없는 본문 헤딩이 있음(시험 자료)", bool(free), free)
        if free:
            show(page, free)
            page.evaluate("""(id) => { const p = document.querySelector(`#doc .para[data-id="${CSS.escape(id)}"]`); p.focus(); const r = document.createRange();
              r.selectNodeContents(p); r.collapse(false); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }""", free)
            page.wait_for_selector(f'#doc .sheet > .pg-btn.caret[data-pg="{free}"]', timeout=5000)
            b = btn_of(page, free)
            check("그 줄에만 옅은 「지침 적기」(하나 · 좁은 여백이면 「＋」 — 이름은 풍선 도움말) · 본문 글을 안 가림", b and b["caret"] and b["text"] in ("지침 적기", "＋") and "지침 적기" in b["title"]
                  and len([x for x in page.evaluate(BTNS) if x["caret"]]) == 1 and -4 <= b["top"] - b["paraTop"] <= 40 and b["left"] >= b["bodyRight"] + 2, b)
            page.screenshot(path=str(OUT / "place_guides_caret.png"))
            page.click(f'#doc .sheet > .pg-btn.caret[data-pg="{free}"]')
            page.wait_for_function("() => { const c = document.getElementById('headsDlg'); return c && !c.hidden && c.dataset.kind === 'placeGuides' && c.querySelector('textarea.pg-ta'); }", timeout=20000)
            c = page.evaluate(COLV)
            check("누르면 그 헤딩의 열 — 문서의 지침 0 · 빈 입력", c["docHead"] == "문서의 작성 지침 0" and c["ta"] == "", c)
            page.fill(f"{COL} textarea.pg-ta", "표는 해당연도만")
            page.click(f"{COL} button:has-text('저장')")
            page.wait_for_function("(id) => { const b = document.querySelector(`#doc .sheet > .pg-btn[data-pg=\"${id}\"]`); return b && b.classList.contains('user') && !b.classList.contains('caret'); }", arg=free, timeout=10000)
            b = btn_of(page, free)
            check("저장 → 늘 보이는 단추(.user · 1)", b and b["user"] and b["text"] == "1" and (phead(d, free)["user"] or {}).get("text") == "표는 해당연도만", b)

        # ---- 8. 배율 · 쪽 보기
        page.evaluate("() => setZoom(state.zoom * 0.8)")
        page.wait_for_timeout(1200)
        bs = [b for b in page.evaluate(BTNS) if b["visible"]]
        check("배율을 바꿔도 그 헤딩 줄 높이 · 오른쪽 여백", bs and all(-4 <= b["top"] - b["paraTop"] <= 40 and b["left"] >= b["bodyRight"] + 2 for b in bs),
              [(b["id"], round(b["top"] - b["paraTop"]), round(b["left"] - b["bodyRight"])) for b in bs][:8])
        page.uncheck("#showPages")
        page.wait_for_timeout(400)
        check("쪽 보기를 끄면 안 보임", not any(b["visible"] for b in page.evaluate(BTNS)))
        page.check("#showPages")
        page.wait_for_timeout(600)
        check("쪽 보기를 다시 켜면 보임", len([b for b in page.evaluate(BTNS) if b["visible"]]) >= len(heads0))

        # ---- 9. 표 열 — 저장해 둔 문서 지침
        tid = max(L["tables"], key=lambda t: t["n"])["id"]
        ta = requests.get(f"{base}/api/docs/{d}/headings/tables/{tid}/agent", timeout=60).json()
        nsaved = len(ta.get("saved") or [])
        page.evaluate("(t) => tblAgentView(t)", tid)
        page.wait_for_selector(f"{COL} .ta-saved", timeout=20000)
        sv = page.evaluate("() => { const s = document.querySelector('#headsDlg .ta-saved'); return { sum: s.querySelector('summary').textContent, n: s.querySelectorAll('li').length, hb: [...s.querySelectorAll('li .hb')].slice(0, 3).map((x) => x.textContent) }; }")
        check("표 열 「저장해 둔 문서 지침 n」 — 그 표의 저장본", nsaved > 0 and sv["sum"] == f"저장해 둔 문서 지침 {nsaved}" and sv["n"] == nsaved, (sv, nsaved))
        page.screenshot(path=str(OUT / "place_guides_table.png"))
        page.evaluate("() => headsColClose(true)")

        # ---- 10. 좁은 창
        page.set_viewport_size({"width": 1100, "height": 900})
        page.wait_for_timeout(1500)
        bs = [b for b in page.evaluate(BTNS) if b["visible"]]
        check("좁은 창(1100px) — 본문 글을 안 가림", bs and all(b["left"] >= b["bodyRight"] + 2 for b in bs), [(b["id"], round(b["left"]), round(b["bodyRight"])) for b in bs][:6])
        page.screenshot(path=str(OUT / "place_guides_narrow.png"))
        errs = [e for e in errors if "status of 409" not in e]   # 5 의 409 는 일부러 낸 것(브라우저가 실패한 요청을 콘솔에 적는다)
        check("페이지 오류 없음(일부러 낸 409 밖)", not errs, errs[:5])
        browser.close()
finally:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.kill()
    log.close()
print(f"\n{'OK' if not fails else 'FAIL'} — 실패 {len(fails)}" + (f": {', '.join(fails)}" if fails else ""), flush=True)
sys.exit(1 if fails else 0)

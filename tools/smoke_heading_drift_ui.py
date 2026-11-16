"""뼈대 유지(spec_헤딩_추출 ② §17 — 문서가 바뀌어도 2·3단계를 다시 만들라고 하지 않고 새 레터·새 서식·새 표만 알림) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_heading_drift_ui.py <그림·임시 폴더> [--port 18177]

연구개발계획서_양식.hwpx 를 API 로 올려 2·3단계(스크립트)를 돌린 뒤 화면에서 연다 → 그대로(「추출 결과」 · 카드 줄 없음) → 헤딩 줄의 글만 고침(「재확인 필요」 없음 · 탭 점 없음 ·
카드 「뼈대 유지 · 새 레터·서식 없음」) → 레터를 「▶」 로(알림 · 상태 줄 「새 레터 1」 · 2단계 탭 점 · 카드 줄 · 문서 여백 「새 레터」 · 뼈대 밖 목록) → 다른 줄 하나의 왼쪽 여백을 바꿈(「잘못된 서식」 —
한 줄뿐: 「TN Lk」 앞에 붙음 · 목록에 「대표에 맞추기」) → 같은 레벨의 줄 하나를 더 같은 값으로(되풀이 = 「새 서식」) → 실행 취소(다시 「잘못된 서식」) → 좁은 패널에서 상태 줄 한 줄 →
「대표에 맞추기」(그 줄이 대표 모양으로 · 알림 사라짐) → 레터를 되돌리면 사라짐 · 콘솔 오류.
문서를 고치므로 사용자 8114 에는 돌리지 않는다."""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18177)
args = ap.parse_args()
OUT = Path(args.out).resolve()
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
PID, PID2 = "p970", "p972"  # 본문 「□ 연구개발기술(제품)의 정의 및 범위」(가지 템플릿 L1) · 그 아래 「o」 줄(L2)

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


def run_stage(wid, stage):
    r = requests.post(f"{base}/api/docs/{wid}/headings", json={"stage": stage, "llm": False}, timeout=30)
    r.raise_for_status()
    for _ in range(600):
        j = requests.get(f"{base}/api/docs/{wid}/headings", timeout=30).json()
        if not (j.get("job") and j["job"]["status"] == "running"):
            return j
        time.sleep(.5)
    raise RuntimeError(f"{stage}단계가 끝나지 않음")


SNAP = """() => {
  const q = (s) => document.querySelector(s);
  const st = q('#headsOverview .analysis-state');
  const kids = [...document.querySelectorAll('#headsOverview .result-meta > *')].filter((e) => e.offsetParent);
  const pane = q('#paneHeads');
  const mid = (e) => { const b = e.getBoundingClientRect(); return Math.round(b.top + b.height / 2); };
  const card = (k) => { const n = q(`#heads${k} .hdrift .stage-notice`); return n ? { text: n.firstElementChild.textContent, warn: n.classList.contains('is-warning'), list: !!n.querySelector('.stage-notice-act') } : null; };
  const toast = q('#toast');
  return {
    state: st ? st.innerText.replace(/\\s+/g, ' ').trim() : null, tag: st ? st.tagName : null, drift: st ? st.classList.contains('drift-chip') : false,
    refresh: !!q('#headsOverview .analysis-refresh'), oneLine: new Set(kids.map(mid)).size <= 1,
    // 상태 줄 항목의 오른쪽 끝 − 패널 내용 영역의 오른쪽 끝(안쪽 여백·스크롤 막대 뺀 곳). 2026-11-16 상태 줄 끝에 「실행 ▾」(margin-left: auto)를 붙여 항목이 내용 끝까지 간다 — 전의 「패널 끝 − 18px」 은 그 전 꼴에 맞춘 값
    right: kids.length ? Math.max(...kids.map((e) => e.getBoundingClientRect().right)) - (pane.getBoundingClientRect().left + pane.clientLeft + pane.clientWidth - parseFloat(getComputedStyle(pane).paddingRight)) : 0, overflowX: pane.scrollWidth - pane.clientWidth,
    tabs: [1, 2, 3].map((k) => q('#headsStageTab' + k).dataset.state || ''), tabTitle: q('#headsStageTab2').title,
    card2: card(2), card3: card(3), card1: [...document.querySelectorAll('#heads1 .stage-notice')].map((n) => n.firstElementChild.textContent),
    marks: [...document.querySelectorAll('.tpl-mark.drift')].map((m) => m.textContent),
    toast: toast && !toast.hidden ? toast.textContent : '',
    key: DRIFT.key, loading: !!DRIFT.loading, counts: DRIFT.data ? [driftCount(2), driftCount(3)] : null, rev: state.serverRev,
    bodyText: document.body.innerText.includes('재확인 필요') || document.body.innerText.includes('다시 분석 필요'),
  };
}"""
SETTLED = "() => typeof DRIFT !== 'undefined' && !DRIFT.loading && !DRIFT.timer && !!DRIFT.key && DRIFT.key === driftIdent() && DRIFT.data && DRIFT.data.rev === state.serverRev"


def settle(page, timeout=60000):
    """지금 문서 차례의 견준 답이 올 때까지(고친 뒤 4초 + 문서 다시 읽기 1~2초)."""
    page.wait_for_function(SETTLED, timeout=timeout)
    page.wait_for_timeout(200)
    return page.evaluate(SNAP)


def retype(page, pid, text):
    """문단의 글을 통째로 바꿔 친다(화면에서 — 반영되면 문서 차례가 오른다)."""
    rev = page.evaluate("() => state.serverRev")
    p = page.locator(f'#doc .para[data-id="{pid}"]').first
    p.scroll_into_view_if_needed()
    p.click()
    page.keyboard.press("Control+A")
    page.keyboard.type(text)
    page.evaluate("() => flushAll()")
    page.wait_for_function("(r) => state.serverRev > r", arg=rev, timeout=60000)


try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    r = requests.post(f"{base}/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}, timeout=120)
    r.raise_for_status()
    wid = r.json()["docId"]
    run_stage(wid, 2)
    summ = run_stage(wid, 3)
    runs0 = len(summ["runs"])
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/#w={wid}")
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=240000)
        page.click("#tabHeads")
        page.wait_for_function("() => typeof heads !== 'undefined' && heads.view && heads.view.stage2 && heads.graph && !(heads.view.job && heads.view.job.status === 'running')", timeout=120000)

        # ---- 1. 그대로
        m = settle(page)
        check("그대로: 상태 「추출 결과」 · 꼬리표·점·카드 줄 없음", m["state"] == "추출 결과" and not m["drift"] and m["tabs"] == ["", "", ""] and m["card2"] is None and m["card3"] is None and m["counts"] == [0, 0], m)
        page.wait_for_function("() => document.querySelectorAll('.tbl-mark').length > 0", timeout=60000)
        owners = page.evaluate("() => [...document.querySelectorAll('.tbl-mark .tm-owner')].map((e) => [e.tagName, e.textContent])")
        check("표 표지: 뜻 모를 「구조에 없음」 없음 · 표 구조에 없는 표는 「1칸 표」(글)·「새 표」(단추)뿐", owners and all("구조에 없음" not in t for _, t in owners)
              and all(tag == "SPAN" for tag, t in owners if t == "1칸 표") and all(tag == "BUTTON" for tag, t in owners if t == "새 표"), [o for o in owners if o[1] in ("1칸 표", "새 표", "구조에 없음")][:6])

        # ---- 2. 글만 고침 — 다시 만들라고 하지 않는다
        retype(page, PID, "□ 연구개발기술의 정의(글만 고침)")
        soon = page.evaluate(SNAP)
        check("고친 직후: 「재확인 필요」·「추출·설정」 단추 없음 · 카드 「뼈대 유지 · 견주는 중」", soon["state"] == "추출 결과" and not soon["refresh"] and not soon["bodyText"]
              and soon["card2"] and soon["card2"]["text"].startswith("뼈대 유지") and not soon["card2"]["warn"], soon)
        m = settle(page)
        check("글만 고침: 「추출 결과」 · 탭 점 없음 · 알림 없음", m["state"] == "추출 결과" and m["tabs"] == ["", "", ""] and m["counts"] == [0, 0] and "뼈대" not in m["toast"], m)
        check("글만 고침: 2·3단계 카드 「뼈대 유지 · 새 … 없음」(경고색 아님)", m["card2"] == {"text": "뼈대 유지 · 새 레터·서식 없음", "warn": False, "list": False}
              and m["card3"] == {"text": "뼈대 유지 · 새 표 없음", "warn": False, "list": False}, (m["card2"], m["card3"]))
        check("화면 어디에도 「재확인 필요」·「다시 분석 필요」 없음", not m["bodyText"])
        page.click("#headsTabRun")
        page.evaluate("headsStagePick(2)")
        page.wait_for_timeout(200)
        page.locator("#paneHeads").screenshot(path=str(OUT / "2_card_keep.png"))
        page.evaluate("headsResultView('Tree')")

        # ---- 3. 새 레터
        retype(page, PID, "▶ 화살표로 바꾼 줄")
        m = settle(page)
        check("새 레터: 상태 줄 꼬리표 「새 레터 1」(단추)", m["state"].startswith("새 레터 1") and m["tag"] == "BUTTON" and m["drift"] and m["counts"] == [1, 0], m)
        check("새 레터: 알림(뼈대는 그대로 씁니다 · 보기)", "뼈대에 없는 새 레터 「▶」" in m["toast"] and "보기" in m["toast"], m["toast"])
        check("새 레터: 2단계 탭 점 · 도움말", m["tabs"] == ["", "stale", ""] and "뼈대에 없는 새 항목" in m["tabTitle"], (m["tabs"], m["tabTitle"]))
        check("새 레터: 2단계 카드 줄 「새 레터 1 [목록]」(주황) · 3단계는 그대로", m["card2"] == {"text": "새 레터 1", "warn": True, "list": True} and m["card3"]["text"] == "뼈대 유지 · 새 표 없음", (m["card2"], m["card3"]))
        check("새 레터: 문서 여백 표시 「새 레터」", m["marks"] == ["새 레터"], m["marks"])
        mark = page.locator(".tpl-mark.drift").first
        mark.scroll_into_view_if_needed()
        box = page.evaluate("""() => { const e = document.querySelector('.tpl-mark.drift'), s = e.closest('.sheet').getBoundingClientRect(), b = e.getBoundingClientRect();
            return { inPaper: b.left >= s.left - 1 && b.right <= s.right, left: Math.round(b.left - s.left), w: Math.round(b.width), title: e.title, bg: getComputedStyle(e).backgroundColor }; }""")
        check("여백 표시는 종이 안 왼쪽 여백 · 도움말에 레터", box["inPaper"] and "새 레터 「▶」" in box["title"], box)
        page.screenshot(path=str(OUT / "3_mark_letter.png"))
        page.locator("#paneHeads").screenshot(path=str(OUT / "3_panel_chip.png"))
        page.click("#headsOverview .drift-chip")
        page.wait_for_selector("#headsDlg[data-kind='drift']:not([hidden])")
        rows = page.evaluate("() => [...document.querySelectorAll('#headsDlg table.drift-list tbody tr')].map((tr) => [...tr.children].map((td) => td.innerText.trim()))")
        check("뼈대 밖 목록(2열): 새 레터 줄 「▶ · 본문 · 레터 · 1 · 예문」", len(rows) == 1 and rows[0][:4] == ["▶", "본문", "레터", "1"] and "화살표로 바꾼 줄" in rows[0][4], rows)
        page.screenshot(path=str(OUT / "3_list.png"))

        # ---- 4. 잘못된 서식(「TN Lk」 가 있는 줄 하나의 왼쪽 여백 — 한 줄뿐이라 새 서식이 아니다) → 같은 레벨의 줄 하나를 더(되풀이 = 새 서식) → 실행 취소
        MARGIN = """async (pid) => { const r = await api(`/api/docs/${state.id}/format/para`, { method: 'POST', headers: H_JSON, body: JSON.stringify({ ids: [pid], changes: { indentLeftMm: 30 } }) });
            applyEditState(r); }"""
        LISTS = """() => [...document.querySelectorAll('#headsDlg table.drift-list')].map((t) => ({ wrong: t.classList.contains('drift-wrong'),
            rows: [...t.querySelectorAll('tbody tr')].map((tr) => [...tr.children].map((td) => td.innerText.replace(/\\s+/g, ' ').trim())),
            match: [...t.querySelectorAll('button.drift-match')].map((b) => !b.disabled), rel: t.querySelectorAll('button.drift-rel').length }))"""
        # 그 레벨의 대표가 아닌 줄 둘(대표 줄은 「대표에 맞추기」 가 꺼진다 — 맞출 대표가 그 줄이라서)
        pw1, pw2 = page.evaluate("""(pid) => { const o = heads.outline, a = o.lines[pid], rep = o.templates[String(a.tpl)].slots[String(a.level)].rep;
            return Object.keys(o.lines).filter((p) => p !== rep && o.lines[p].tpl === a.tpl && o.lines[p].level === a.level && o.lines[p].role === a.role).slice(0, 2); }""", PID2)
        page.evaluate(MARGIN, pw1)
        m = settle(page)
        check("잘못된 서식: 꼬리표 「새 레터 1 · 잘못된 서식 1」 · 카드 줄(한 줄뿐인 서식은 새 서식이 아니다)", m["state"].startswith("새 레터 1 · 잘못된 서식 1") and "새 서식" not in m["state"]
              and m["card2"]["text"] == "새 레터 1 · 잘못된 서식 1" and m["counts"] == [2, 0], m)
        check("잘못된 서식: 알림", "한 줄의 잘못된 서식" in m["toast"] and "보기" in m["toast"], m["toast"])
        joined = " · ".join(m["marks"])  # 붙어 있는 줄들의 표시는 한 표로 모인다(「새 레터 · 잘못된 서식 T2 L2」)
        check("잘못된 서식: 여백 표시는 「TN Lk」 앞에 붙음 · 새 레터는 그것만", re.search(r"잘못된 서식 T\d+ L\d+", joined) and "새 서식" not in joined and "새 레터" in joined and "새 레터 T" not in joined, m["marks"])
        lists = page.evaluate(LISTS)
        check("열려 있던 목록이 따라 바뀜(새 레터 표 · 잘못된 서식 표 — 「대표에 맞추기」·「갈래 보기」)", [t["wrong"] for t in lists] == [False, True] and [r[0] for r in lists[0]["rows"]] == ["▶"]
              and len(lists[1]["rows"]) == 1 and lists[1]["rows"][0][:2] == ["o", "본문"] and "왼30" in lists[1]["rows"][0][2] and "쓰던 서식" in lists[1]["rows"][0][2]
              and lists[1]["match"] == [True] and lists[1]["rel"] == 1, lists)
        fit = page.evaluate("""() => { const b = document.querySelector('#headsDlg table.drift-wrong button.drift-match'), c = document.querySelector('#headsDlg .hd-body') || document.querySelector('#headsDlg');
            const br = b.getBoundingClientRect(), cr = c.getBoundingClientRect(); return { right: Math.round(br.right - cr.right), overflow: c.scrollWidth - c.clientWidth, w: Math.round(cr.width) }; }""")
        check("「대표에 맞추기」 단추가 목록 열 안에 보임(긴 서식 이름은 칸 안에서 줄 바꿈 — 표가 열 폭을 넘지 않음)", fit["right"] <= 0 and fit["overflow"] <= 0, fit)
        heads_txt = page.evaluate("() => [...document.querySelectorAll('#headsDlg .temp-head')].map((h) => h.innerText.replace(/\\s+/g, ' ').trim())")
        check("잘못된 서식 묶음 머리에는 「2단계 열기」 가 없다(뼈대에 넣을 것이 아니라 맞출 것)", len(heads_txt) == 2 and "2단계 열기" in heads_txt[0] and heads_txt[1].startswith("잘못된 서식") and "단계 열기" not in heads_txt[1], heads_txt)
        page.screenshot(path=str(OUT / "4_list_wrong.png"))
        page.evaluate(MARGIN, pw2)
        m = settle(page)
        lists = page.evaluate(LISTS)
        check("같은 서식이 두 줄(되풀이): 「새 서식 1」 — 잘못된 서식 없음 · 목록의 문단 수 2", m["state"].startswith("새 레터 1 · 새 서식 1") and "잘못된 서식" not in m["state"] and m["counts"] == [2, 0]
              and [t["wrong"] for t in lists] == [False, False] and lists[1]["rows"][0][0] == "o" and lists[1]["rows"][0][3] == "2" and lists[1]["match"] == [] and lists[1]["rel"] == 1, (m["state"], lists))
        check("새 서식: 여백 표시 「새 서식 TN Lk」", len(re.findall(r"새 서식 T\d+ L\d+", " · ".join(m["marks"]))) >= 1 and "잘못된 서식" not in " · ".join(m["marks"]), m["marks"])
        page.screenshot(path=str(OUT / "4_list_format.png"))
        page.evaluate("""async () => { const r = await api(`/api/docs/${state.id}/undo`, { method: 'POST' }); applyEditState(r); }""")
        m = settle(page)
        check("실행 취소(둘째 줄): 다시 「잘못된 서식 1」", m["state"].startswith("새 레터 1 · 잘못된 서식 1") and m["counts"] == [2, 0], m["state"])
        page.evaluate("headsColClose(true)")

        # ---- 5. 좁은 패널 — 상태 줄 한 줄 · 넘침 없음
        for w in (320, 388, 480):
            page.evaluate("(w) => { document.getElementById('panel').style.setProperty('--panel', w + 'px'); heads.summaryKey = null; headsResultsSummary(heads.view); }", w)
            page.wait_for_timeout(200)
            n = page.evaluate(SNAP)
            check(f"[{w}] 꼬리표가 있는 상태 줄 한 줄 · 넘침 없음", n["oneLine"] and n["overflowX"] <= 0 and n["right"] <= 0.5, (n["state"], n["right"], n["overflowX"]))
            if w in (320, 388):
                page.locator("#paneHeads").screenshot(path=str(OUT / f"5_panel_{w}.png"))
        page.evaluate("() => { document.getElementById('panel').style.removeProperty('--panel'); heads.summaryKey = null; headsResultsSummary(heads.view); }")

        # ---- 6. 「대표에 맞추기」 — 그 줄이 대표 모양으로(「템플릿 관계」 의 갈래 맞추기와 같은 길 · 실행 취소 1) → 알림이 사라진다. 그 뒤 레터를 되돌리면 모두 사라진다 · 실행은 안 늘었다
        page.click("#headsOverview .drift-chip")
        page.wait_for_selector("#headsDlg[data-kind='drift']:not([hidden]) table.drift-wrong button.drift-match")
        rev = page.evaluate("() => state.serverRev")
        page.click("#headsDlg table.drift-wrong button.drift-match")
        page.wait_for_function("(r) => state.serverRev > r", arg=rev, timeout=60000)
        page.wait_for_function("() => /대표 모양으로 맞췄습니다/.test(document.getElementById('toast').textContent)", timeout=20000)   # 알림은 뜬 직후에 읽는다(3.5초 뒤 사라진다 — 견준 답은 그 뒤에 온다)
        said = page.evaluate("() => document.getElementById('toast').textContent")
        m = settle(page)
        left = page.evaluate("""async (pid) => { const o = heads.outline, a = o.lines[pid], rep = o.templates[String(a.tpl)].slots[String(a.level)].rep;
            const f = (p) => (state.byId.get(p).format || {}).indentLeftMm; return [f(pid), f(rep)]; }""", pw1)
        joined = " · ".join(m["marks"])  # 맞춘 줄이 새 레터 줄 바로 옆이면 그 줄의 「TN Lk」 가 같은 표에 모인다(「새 레터 · T2 L2」) — 서식 표시만 없으면 된다
        check("대표에 맞추기: 「새 레터 1」 만 남음 · 그 줄의 왼쪽 여백 = 대표의 것 · 알림", m["state"].startswith("새 레터 1") and "서식" not in m["state"] and "새 레터" in joined and "서식" not in joined
              and m["counts"] == [1, 0] and left[0] == left[1] and left[0] != 30 and "대표 모양으로 맞췄습니다" in said, (m["state"], m["marks"], m["counts"], left, said))
        check("대표에 맞추기: 열려 있던 목록에서 잘못된 서식 표가 사라짐", [t["wrong"] for t in page.evaluate(LISTS)] == [False], page.evaluate(LISTS))
        page.evaluate("headsColClose(true)")
        retype(page, PID, "□ 연구개발기술(제품)의 정의 및 범위")
        m = settle(page)
        check("레터를 되돌림: 「추출 결과」 · 점·여백 표시 없음", m["state"] == "추출 결과" and m["tabs"] == ["", "", ""] and m["marks"] == [] and m["card2"]["text"] == "뼈대 유지 · 새 레터·서식 없음", m)
        now = requests.get(f"{base}/api/docs/{wid}/headings", timeout=30).json()
        s2 = now["stage2"]
        check("2·3단계 결과는 그대로(실행 번호 · stale 은 사실로 남음) — 1단계만 탭을 열 때 다시 뽑힘", s2["meta"]["run"] == summ["stage2"]["meta"]["run"] and s2["stale"] is True
              and now["stage3"]["meta"]["run"] == summ["stage3"]["meta"]["run"] and all(x["stage"] == 1 for x in now["runs"][runs0:]), [(x["n"], x["stage"]) for x in now["runs"]])
        # ---- 7. 이어 연 작업 — 헤딩 탭을 열지 않아도 견준다(문서를 열 때 읽은 요약으로: driftSeed)
        page.reload()
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=240000)
        page.wait_for_function("() => typeof DRIFT !== 'undefined' && !!DRIFT.sum", timeout=60000)
        m = settle(page)
        check("이어 연 작업: 헤딩 탭을 안 열어도(heads.view 없음) 문서를 열 때 견줌 · 알림 없음", page.evaluate("() => heads.view === null") and m["counts"] == [0, 0] and "뼈대" not in m["toast"], (m["counts"], m["toast"]))
        retype(page, PID, "▶ 탭을 열지 않고 바꾼 줄")
        m = settle(page)
        check("이어 연 작업: 고치면 알림 + 문서 여백 「새 레터」(헤딩 탭은 닫힌 채)", page.evaluate("() => heads.view === null") and m["counts"] == [1, 0] and "새 레터 「▶」" in m["toast"] and m["marks"] == ["새 레터"],
              (m["counts"], m["toast"], m["marks"]))
        page.screenshot(path=str(OUT / "7_reopened_mark.png"))
        retype(page, PID, "□ 연구개발기술(제품)의 정의 및 범위")
        m = settle(page)
        check("이어 연 작업: 되돌리면 여백 표시 없음", m["counts"] == [0, 0] and m["marks"] == [], (m["counts"], m["marks"]))
        check("콘솔·페이지 오류 없음", not errors, " | ".join(errors[:3]))
        browser.close()
except Exception as e:  # noqa: BLE001
    check(f"실행 오류: {type(e).__name__}", False, e)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()

print(f"\n{'모두 통과' if not fails else '실패 ' + str(len(fails))}")
sys.exit(1 if fails else 0)

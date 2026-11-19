"""양식의 표 판정(spec_테이블매니저 ② §10 「양식의 표 판정」 — 표 메뉴 「양식의 표 판정…」 · 「테이블」 탭의 상태 표지) 화면 확인 —
임시 서버(임시 작업 폴더 · 임시 헤딩 저장소 = 확정본 파일 · 임시 양식 정보 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_table_types_ui.py <그림·임시 폴더> [--port 18199]

임시 양식 정보 폴더에 파일 이름 꼴 「*연구개발계획서*」 의 양식(「시험 계획서」) 하나를 두고 연구개발계획서_양식.hwpx 를 API 로 올린다(= 양식이 정해진 문서) → `#w=<id>` 로 열어
① 표 손잡이 → 표 메뉴 「양식의 표 판정…」(「키-값으로 보기 · 매핑…」 바로 뒤) → 2열 「양식의 표 판정 · t6685」(kind tblType): 양식 이름 · 상태 「확정 안 됨」 · 판정 격자(역할마다 색 — table.hgrid · 범례 일곱) ·
  격자 칸에 올리면 문서의 그 칸 표시 · 가변 머리글 목록(머리글 6) · 「이 타입의 확정본 0」.
② 가변 머리글로 「기간」 칸 둘(A2 · A3)을 체크 → 「이 판정으로 확정」(확인 창 없음) → 상태 「확정됨」 · 서버에 확정본 1(고정 머리글 4 · 가변 2) · 문서는 안 바뀜(실행 취소 수 그대로) ·
  같이 쓰이는 표 「이 문서의 다른 표 1개에도 이 판정이 쓰입니다 — t7018: 지금 판정과 같음」.
③ 「테이블」 탭의 표 목록 — 구조가 꼭 같은 두 표(t6685 · t7018)에만 「확정됨」 표지.
④ 값 칸 여섯에 짧은 글(「홍길동」)을 API 로 채우고 새로 고침 → 다시 열면 상태 「확정됨」 그대로 · 격자의 역할이 채우기 전과 같음(값 칸은 필드) · 「확정본과 다른 칸」(초안은 … · 확정본은 …).
⑤ 「확정하고 다음 표」 → 확정본의 판 2 · 이 문서에서 확정 안 된 다음 표의 열로 넘어감.
⑥ 다시 t6685 — 「이 타입의 확정본 1」(이 표에 쓰임) → 「지우기」(확인 창 없음) → 상태 「확정 안 됨」 · 알림의 「되돌리기」 → 「확정됨」(되살리기 요청은 id 만 보낸다).
⑦ 고치기와 따로 확정 — 둘째 표(t7018)의 B2 에 고정 이름을 넣고 헤더 지정으로 행헤더로(API) → 새로 고침 → 그 표의 열: 단추가 「이 확정본 고치기」 · 「이 표만 따로 확정」 둘 + 안내 줄(이 문서에 2개) ·
  같이 쓰이는 표에 값을 채운 첫 표 「지금 판정과 n칸 다름(확인)」 · 그 고정 이름을 가변으로 두면 「이 표만 따로 확정」 이 꺼짐(까닭은 풍선 도움말) → 「이 표만 따로 확정」 → 확정본 둘 · 표마다 제 확정본(첫 표의 B2 는 값 칸 · 둘째 표의 B2 는 행헤더).
⑧ 양식이 정해지지 않은 문서(같은 파일의 둘째 작업 — 「양식 없음」 으로 고정): 표 메뉴 항목을 누르면 알림 「양식이 정해지지 않은 문서입니다 — 양식 정보에서 양식을 고르세요」 · 열은 안 열림 · 「테이블」 탭에 표지 없음.
열 폭 넘침 · 콘솔 오류 · 확인 창."""
import argparse
import json
import os
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
ap.add_argument("--port", type=int, default=18199)
args = ap.parse_args()
OUT = Path(args.out).resolve()
RND = ROOT / "samples" / "연구개발계획서_양식.hwpx"
CAREER, TWIN = "t6685", "t7018"   # 3×4 「기간 | 기관명 | 직위 | 비고」 경력 표 · 같은 문서의 구조가 꼭 같은 표
FORM, FORM_NAME = "시험계획서", "시험 계획서"
FORM_MD = '# 양식 정보 — 시험\n\n```json\n{"name": "시험 계획서", "match": {"names": ["*연구개발계획서*"]}}\n```\n'
NO_FORM = "양식이 정해지지 않은 문서입니다 — 양식 정보에서 양식을 고르세요"
BLANK = {"A1": "corner", "B1": "colhead", "C1": "colhead", "D1": "colhead", "A2": "rowhead", "B2": "field", "C2": "field", "D2": "field", "A3": "rowhead", "B3": "field", "C3": "field", "D3": "field"}
VALUES = ("B2", "C2", "D2", "B3", "C3", "D3")

OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
(tmp / "forms").mkdir(parents=True, exist_ok=True)
(tmp / "forms" / f"{FORM}.md").write_text(FORM_MD, encoding="utf-8")
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_JOBS": "off", "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:500] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def menu(page):
    return page.evaluate("""() => { const m = document.querySelector('.ctx-menu'); if (!m || m.hidden || m.dataset.by !== 'tmn') return null;
        return [...m.querySelectorAll('button')].map((b) => ({text: b.textContent, disabled: b.disabled})); }""")


def corner(page, tid):
    """표 칸을 눌러 고른 표로 만들고 손잡이를 눌러 표 메뉴를 연다."""
    page.locator(f"#doc table.tbl[data-tbl='{tid}'] td .para").first.scroll_into_view_if_needed()
    page.wait_for_timeout(1500)
    page.locator(f"#doc table.tbl[data-tbl='{tid}'] td .para").first.click()
    page.wait_for_selector(f".tbl-corner[data-for='{tid}']")
    page.locator(".tbl-corner").click()
    page.wait_for_selector(".ctx-menu[data-by='tmn']:not([hidden])")


def open_col(page, tid):
    """표 메뉴 → 「양식의 표 판정…」 → 2열이 그 표로 열릴 때까지."""
    corner(page, tid)
    page.locator(".ctx-menu[data-by='tmn'] button:has-text('양식의 표 판정')").first.click()
    page.wait_for_function("(t) => document.getElementById('headsDlgTitle').textContent === `양식의 표 판정 · ${t}` && document.querySelector('.tty-wrap .tty-bar .tty-ok')", arg=tid, timeout=60000)
    page.wait_for_timeout(300)


def entries():
    return requests.get(f"{base}/api/table-types", params={"form": FORM}, timeout=30).json()["entries"]


def api_view(doc, tid=CAREER):
    return requests.get(f"{base}/api/docs/{doc}/tables/{tid}/type", timeout=120).json()


def wait_doc(page, doc):
    page.wait_for_function("(g) => state.id === g && document.querySelector('#doc .sheet .para') != null", arg=doc, timeout=240000)
    page.wait_for_timeout(1500)


VIEW = """() => { const w = document.querySelector('.tty-wrap'); if (!w) return null;
  const txt = (e) => (e ? e.textContent : '');
  const st = w.querySelector('.ta-ident .tty-state'), ok = w.querySelector('.tty-bar .tty-ok'), nx = w.querySelector('.tty-bar .tty-next');
  const grid = {};
  for (const td of w.querySelectorAll('.tty-grid table.hgrid td[data-cell]')) grid[td.dataset.cell] = { role: td.className.split(' ')[0], text: td.textContent, user: td.classList.contains('tty-user'),
    variable: td.classList.contains('tty-varcell'), differs: td.classList.contains('tty-differs') };
  const diff = w.querySelector('details.tty-diff'), vars = w.querySelector('details.tty-var'), list = w.querySelector('details.tty-variants');
  return { title: document.getElementById('headsDlgTitle').textContent, kind: heads.dlg, ident: [...w.querySelectorAll('.ta-ident > *')].map(txt), state: txt(st), stateKey: st ? st.dataset.state : '',
    sum: txt(w.querySelector('p.tty-sum')), held: !w.querySelector('p.tty-held').hidden, grid, rows: w.querySelectorAll('.tty-grid table.hgrid tr').length,
    legend: [...w.querySelectorAll('.tty-grid .hlegend span')].map(txt),
    diffShown: !!diff && !diff.hidden, diffSum: txt(diff && diff.querySelector('summary')), diffs: [...w.querySelectorAll('details.tty-diff .tty-list li')].map(txt),
    varSum: txt(vars && vars.querySelector('summary')), vars: [...w.querySelectorAll('ul.tty-vars input')].map((i) => ({ id: i.value, on: i.checked, text: i.closest('label').textContent })),
    ok: txt(ok), okOff: !!(ok && ok.disabled), next: txt(nx), nextOff: !!(nx && nx.disabled),
    also: w.querySelector('p.tty-also').hidden ? '' : txt(w.querySelector('p.tty-also')), alsoLinks: [...w.querySelectorAll('p.tty-also .hlink')].map(txt),
    bar: [...w.querySelectorAll('.tty-bar .btn')].map((b) => [b.textContent, b.disabled]), barNote: w.querySelector('p.tty-barnote').hidden ? '' : txt(w.querySelector('p.tty-barnote')),
    apartTip: (w.querySelector('.tty-bar .tty-new') || {}).title || '',
    listSum: txt(list && list.querySelector('summary')), entries: [...w.querySelectorAll('.tty-entry')].map((li) => ({ name: txt(li.querySelector('.tty-entry-name')), tag: txt(li.querySelector('.tty-entry-top .hb')),
      meta: txt(li.querySelector('.tty-entry-meta')), acts: [...li.querySelectorAll('.tty-entry-acts button')].map(txt) })) }; }"""
FIT = """() => { const p = document.getElementById('headsDlg'), r = p.getBoundingClientRect();
  const bad = [...p.querySelectorAll('.tty-wrap *')].filter(e => !e.closest('.hgrid-scroll') && e.getClientRects().length && (e.getBoundingClientRect().right > r.right + 1 || e.getBoundingClientRect().left < r.left - 1))
    .slice(0, 6).map(e => e.className || e.tagName);
  return { width: Math.round(r.width), bad, bodyOver: document.getElementById('headsDlgBody').scrollWidth - document.getElementById('headsDlgBody').clientWidth }; }"""
STATE_IS = "(s) => { const e = document.querySelector('.tty-wrap .ta-ident .tty-state'); return !!e && e.textContent === s; }"
TAGS = """() => [...document.querySelectorAll('#tablesBox .tp-row')].filter((r) => r.querySelector('.tp-type')).map((r) => [r.dataset.tableId, r.querySelector('.tp-type').textContent])"""

try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    r = requests.post(f"{base}/api/docs", files={"file": (RND.name, RND.read_bytes())}, timeout=120)
    r.raise_for_status()
    doc = r.json()["docId"]
    v0 = api_view(doc)
    cells = {c["ref"]: c["id"] for c in v0["judgment"]["cells"]}
    check("서버 — 양식이 정해진 문서 · 이 표는 확정 안 됨 · 판정은 초안", v0.get("form") == {"key": FORM, "name": FORM_NAME} and v0["state"] == "none" and v0["match"] is None and v0["judgment"]["source"] == "draft"
          and {c["ref"]: c["role"] for c in v0["judgment"]["cells"]} == BLANK, {k: v0.get(k) for k in ("form", "state", "match")})
    check("확정본 저장소가 비어 있음(임시 헤딩 저장소) · 문서의 표 목록에 확정된 표 없음", entries() == []
          and not [t for t in requests.get(f"{base}/api/docs/{doc}/tables/types", timeout=120).json()["tables"] if t["state"] != "none"])
    r = requests.post(f"{base}/api/docs?new=1", files={"file": (RND.name, RND.read_bytes())}, timeout=120)   # 둘째 작업 — 「양식 없음」 으로 고정
    r.raise_for_status()
    ndoc = r.json()["docId"]
    nf = requests.put(f"{base}/api/docs/{ndoc}/headings/form", json={"form": ""}, timeout=60)
    check("둘째 작업 — 「양식 없음」 으로 고정(서버 form null)", nf.status_code == 200 and ndoc != doc and api_view(ndoc)["form"] is None, nf.text[:200])

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1700, "height": 1000})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("dialog", lambda d: (errors.append(f"dialog: {d.message}"), d.accept()))   # 확인 창은 쓰지 않는다 — 뜨면 오류로 센다
        sent = []   # 화면이 보낸 확정(PUT …/type) · 되살리기(POST …/restore) 요청의 본문
        page.on("request", lambda q: sent.append((q.method, q.url, q.post_data)) if (q.method == "POST" and q.url.endswith("/api/table-types/restore")) or (q.method == "PUT" and q.url.endswith("/type")) else None)
        page.goto(f"{base}/#w={doc}")
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=240000)
        page.wait_for_timeout(1500)

        # ---- 1. 표 메뉴의 새 항목 → 2열
        corner(page, CAREER)
        texts = [x["text"] for x in menu(page)]
        dis = {x["text"]: x["disabled"] for x in menu(page)}
        check("표 메뉴 — 「양식의 표 판정…」 이 켜져 있고 「키-값으로 보기 · 매핑…」 바로 뒤", dis.get("양식의 표 판정…") is False
              and texts.index("양식의 표 판정…") == texts.index("키-값으로 보기 · 매핑…") + 1, texts)
        page.screenshot(path=str(OUT / "1_menu.png"))
        page.locator(".ctx-menu[data-by='tmn'] button:has-text('양식의 표 판정')").first.click()
        page.wait_for_selector(".tty-wrap .tty-bar .tty-ok", timeout=60000)
        page.wait_for_timeout(300)
        v = page.evaluate(VIEW)
        check("2열 「양식의 표 판정 · t6685」(kind tblType)", v["title"] == f"양식의 표 판정 · {CAREER}" and v["kind"] == "tblType", v["title"])
        check("머리 — 표 id · 크기 · 양식 이름 · 상태 「확정 안 됨」", v["ident"][:4] == [CAREER, "3×4", f"양식 {FORM_NAME}", "확정 안 됨"] and v["stateKey"] == "none" and v["sum"].startswith("확정 안 됨 — 지금 판정: 초안"), (v["ident"], v["sum"]))
        check("판정 격자 — 3행 · 칸 12 · 역할이 서버 판정 그대로 · 범례 일곱", v["rows"] == 3 and {r: v["grid"][cells[r]]["role"] for r in BLANK} == BLANK
              and v["legend"] == ["열헤더", "행헤더", "귀퉁이", "필드", "제목", "안내", "간격"], (v["rows"], v["legend"]))
        check("가변 머리글 — 머리글 6칸 · 처음에는 체크 없음(구분 기준의 값 머리가 없는 표)", v["varSum"].startswith("가변 머리글 0 / 머리글 6") and [x["id"] for x in v["vars"]] == [cells[r] for r in ("A1", "B1", "C1", "D1", "A2", "A3")]
              and not any(x["on"] for x in v["vars"]), (v["varSum"], v["vars"][:2]))
        check("확정 단추 둘이 켜져 있음 · 「확정본과 다른 칸」 은 안 보임 · 「이 타입의 확정본 0」", v["ok"] == "이 판정으로 확정" and not v["okOff"] and v["next"] == "확정하고 다음 표" and not v["nextOff"] and not v["diffShown"]
              and v["listSum"].startswith("이 타입의 확정본 0") and v["entries"] == [] and not v["held"], (v["ok"], v["next"], v["listSum"]))
        page.locator(f".tty-grid table.hgrid td[data-cell='{cells['B2']}']").hover()
        check("격자 칸에 올리면 문서의 그 칸에 표시(td.tty-hit)", page.evaluate("(c) => [...document.querySelectorAll('#doc td.tty-hit')].map((e) => e.dataset.cell)", cells["B2"]) == [cells["B2"]])
        page.mouse.move(5, 5)
        fit = page.evaluate(FIT)
        check("열 안에 들어감(가로 넘침 없음)", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "2_none.png"))

        # ---- 2. 가변 머리글을 고르고 확정
        for ref in ("A2", "A3"):
            page.locator(f"ul.tty-vars input[value='{cells[ref]}']").click()
        v = page.evaluate(VIEW)
        check("가변 머리글 체크 — 수 2 · 격자의 그 칸에 점선 표시", v["varSum"].startswith("가변 머리글 2 / 머리글 6") and v["grid"][cells["A2"]]["variable"] and v["grid"][cells["A3"]]["variable"] and not v["grid"][cells["A1"]]["variable"], v["varSum"])
        undo0 = page.evaluate("() => state.undo || 0")
        page.locator(".tty-bar .tty-ok").click()
        page.wait_for_function(STATE_IS, arg="확정됨", timeout=60000)
        v, es = page.evaluate(VIEW), entries()
        check("「이 판정으로 확정」 — 상태 「확정됨」 · 서버에 확정본 1(고정 머리글 4 · 가변 2 · 이 표에서) · 확인 창 없음", v["stateKey"] == "confirmed" and v["sum"].startswith("확정됨 — 이 표는 양식의 확정본(판 1")
              and [(e["rev"], e["cells"], e["fixed"], e["variable"], e["from"]["table"]) for e in es] == [(1, 12, 4, 2, CAREER)] and not errors, (v["sum"], es))
        check("확정은 문서를 안 바꿈(실행 취소 수 그대로) · 가변 체크가 남음 · 「이 타입의 확정본 1」(이 표에 쓰임)", page.evaluate("() => state.undo || 0") == undo0 and [x["on"] for x in v["vars"]] == [False, False, False, False, True, True]
              and v["listSum"].startswith("이 타입의 확정본 1") and [e["tag"] for e in v["entries"]] == ["이 표에 쓰임"], (v["vars"], v["entries"]))
        check("같이 쓰이는 표 — 「이 문서의 다른 표 1개에도 이 판정이 쓰입니다 — t7018: 지금 판정과 같음」(표 번호는 누르는 글)", v["also"].startswith(f"이 문서의 다른 표 1개에도 이 판정이 쓰입니다 — {TWIN}: 지금 판정과 같음")
              and v["alsoLinks"] == [TWIN] and [b[0] for b in v["bar"]] == ["이 판정으로 확정", "확정하고 다음 표"] and not v["barNote"], (v["also"], v["bar"]))
        page.screenshot(path=str(OUT / "3_confirmed.png"))

        # ---- 3. 「테이블」 탭의 상태 표지
        page.evaluate("() => showTab('Tables')")
        page.wait_for_selector("#tablesBox .tp-row", timeout=60000)
        page.wait_for_function("() => document.querySelectorAll('#tablesBox .tp-type').length >= 2", timeout=60000)
        tags = page.evaluate(TAGS)
        check("「테이블」 탭 — 구조가 꼭 같은 두 표에만 「확정됨」 표지", sorted(tags) == sorted([[CAREER, "확정됨"], [TWIN, "확정됨"]]), tags)
        page.screenshot(path=str(OUT / "4_tab.png"))

        # ---- 4. 값 칸을 짧은 글로 채운 뒤에도 판정이 그대로
        fr = requests.post(f"{base}/api/docs/{doc}/tables/{CAREER}/fill/apply", json={"fills": [{"cell": cells[r], "text": "홍길동"} for r in VALUES]}, timeout=120)
        check("값 칸 여섯 채우기(표 채우기 반영 끝점)", fr.status_code == 200, fr.text[:300])
        page.reload()
        wait_doc(page, doc)
        open_col(page, CAREER)
        v, sv = page.evaluate(VIEW), api_view(doc)
        check("값을 채운 뒤에도 상태 「확정됨」 · 격자의 역할이 채우기 전과 같음(값 칸은 필드 · 글은 지금 문서의 것)", v["stateKey"] == "confirmed" and {r: v["grid"][cells[r]]["role"] for r in BLANK} == BLANK
              and v["grid"][cells["B2"]]["text"] == "홍길동" and sv["judgment"]["source"] == "template", (v["state"], {r: v["grid"][cells[r]]["role"] for r in BLANK}))
        check("「확정본과 다른 칸」 — 확정본이 없었다면 다르게 읽었을 칸(「초안은 … · 확정본은 …」) · 격자에 주황 테두리", v["diffShown"] and len(v["diffs"]) == len(sv["differs"]) > 0
              and all("초안은 " in d and "확정본은 " in d for d in v["diffs"]) and v["grid"][cells["B2"]]["differs"], (v["diffSum"], v["diffs"][:2], sv["differs"][:2]))
        st = requests.get(f"{base}/api/docs/{doc}/tables/{CAREER}/style", timeout=120).json()
        check("표 서식 점검도 확정본으로(source template · template {id, rev 1})", st.get("source") == "template" and st.get("template") == {"id": entries()[0]["id"], "rev": 1}, (st.get("source"), st.get("template")))
        page.evaluate("() => { document.querySelector('details.tty-diff').open = true; }")
        fit = page.evaluate(FIT)
        check("다른 칸 목록을 편 채 — 열 안에 들어감", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "5_filled.png"))

        # ---- 5. 확정하고 다음 표
        order = page.evaluate("() => xlBlocks().map((b) => b.id)")
        states = {t["table"]: t["state"] for t in requests.get(f"{base}/api/docs/{doc}/tables/types", timeout=120).json()["tables"]}
        after = [t for t in order[order.index(CAREER) + 1:] + order[:order.index(CAREER)] if t in states and states[t] != "confirmed"]
        page.locator(".tty-bar .tty-next").click()
        page.wait_for_function("(t) => document.getElementById('headsDlgTitle').textContent !== `양식의 표 판정 · ${t}` && document.querySelector('.tty-wrap .tty-bar .tty-ok')", arg=CAREER, timeout=60000)
        page.wait_for_timeout(300)
        v, es = page.evaluate(VIEW), entries()
        check("「확정하고 다음 표」 — 확정본의 판 2(같은 확정본을 고침) · 이 문서에서 확정 안 된 다음 표의 열로", [(e["rev"], e["fixed"], e["variable"]) for e in es] == [(2, 4, 2)] and bool(after)
              and v["title"] == f"양식의 표 판정 · {after[0]}" and after[0] not in (CAREER, TWIN) and v["stateKey"] in ("none", "changed"), (v["title"], after[:2], es))
        page.screenshot(path=str(OUT / "6_next.png"))

        # ---- 6. 확정본 지우기 → 알림의 「되돌리기」
        page.evaluate("(t) => tblTypeView(t)", CAREER)
        page.wait_for_function("(t) => document.getElementById('headsDlgTitle').textContent === `양식의 표 판정 · ${t}` && document.querySelector('.tty-wrap .tty-bar .tty-ok')", arg=CAREER, timeout=60000)
        page.wait_for_function(STATE_IS, arg="확정됨", timeout=60000)
        page.evaluate("() => { document.querySelector('details.tty-variants').open = true; }")
        v = page.evaluate(VIEW)
        check("「이 타입의 확정본 1」 — 이름(고정 머리글) · 「이 표에 쓰임」 · 판 2 · 「지우기」", [(e["name"], e["tag"], e["acts"]) for e in v["entries"]] == [("기간 · 기관명 · 직위", "이 표에 쓰임", ["지우기"])]
              and v["entries"][0]["meta"].startswith("판 2") and "고정 머리글 4 · 가변 2" in v["entries"][0]["meta"], v["entries"])
        page.locator(".tty-entry .tty-entry-acts button:text-is('지우기')").click()
        page.wait_for_function(STATE_IS, arg="확정 안 됨", timeout=60000)
        v = page.evaluate(VIEW)
        check("지우기 — 확인 창 없이 지움 · 상태 「확정 안 됨」(판정은 초안으로) · 알림에 「되돌리기」", entries() == [] and v["stateKey"] == "none" and v["entries"] == [] and not v["diffShown"]
              and page.locator("#toast .toast-act", has_text="되돌리기").count() == 1 and not errors, (v["state"], entries()))
        page.locator("#toast .toast-act").click()
        page.wait_for_function(STATE_IS, arg="확정됨", timeout=60000)
        es = entries()
        check("「되돌리기」 — 같은 확정본이 그대로 되살아남(판 2)", [(e["rev"], e["fixed"], e["variable"]) for e in es] == [(2, 4, 2)] and page.evaluate(VIEW)["stateKey"] == "confirmed", es)
        backs = [json.loads(b) for m, u, b in sent if m == "POST"]
        check("「되돌리기」 는 id 만 보낸다(확정본을 보내지 않는다 — 서버가 지닌 지운 확정본에서 되살린다)", backs == [{"id": es[0]["id"]}], backs)
        page.screenshot(path=str(OUT / "7_restored.png"))

        # ---- 7. 고치기와 따로 확정 — 둘째 표(t7018)의 B2 는 값 칸이 아니라 고정 이름이다: 헤더 지정으로 행헤더로 고친 뒤 「이 표만 따로 확정」
        first = es[0]["id"]
        tw = {c["ref"]: c["id"] for c in api_view(doc, TWIN)["judgment"]["cells"]}
        fr = requests.post(f"{base}/api/docs/{doc}/tables/{TWIN}/fill/apply", json={"fills": [{"cell": tw["B2"], "text": "고정이름"}]}, timeout=120)
        hr = requests.put(f"{base}/api/docs/{doc}/tables/{TWIN}/heads", json={"cells": [tw["B2"]], "role": "rowhead"}, timeout=120)
        sv = api_view(doc, TWIN)
        check("둘째 표 꾸미기(B2 에 고정 이름 · 헤더 지정 행헤더) — 서버: 첫 확정본이 맞고 골라야 함 · 따로 확정할 수 있음", fr.status_code == 200 and hr.status_code == 200 and sv["match"]["id"] == first
              and sv["choose"] == {"needed": True, "canNew": True, "why": ""}, (fr.status_code, hr.status_code, sv.get("choose")))
        page.reload()
        wait_doc(page, doc)
        corner(page, TWIN)
        page.locator(".ctx-menu[data-by='tmn'] button:has-text('양식의 표 판정')").first.click()
        page.wait_for_function("(t) => document.getElementById('headsDlgTitle').textContent === `양식의 표 판정 · ${t}` && document.querySelector('.tty-wrap .tty-bar .tty-update')", arg=TWIN, timeout=60000)
        page.wait_for_timeout(300)
        v = page.evaluate(VIEW)
        check("단추가 둘로 — 「이 확정본 고치기」 · 「이 표만 따로 확정」(둘 다 켜짐) · 그 아래 한 줄(이 문서에 2개)", v["bar"] == [["이 확정본 고치기", False], ["이 표만 따로 확정", False]]
              and v["barNote"].startswith("지금 판정이 이 표에 쓰이는 확정본과 다릅니다") and "이 문서에 2개" in v["barNote"] and v["grid"][tw["B2"]]["user"] and v["grid"][tw["B2"]]["role"] == "rowhead", (v["bar"], v["barNote"]))
        check("같이 쓰이는 표 — 값을 채운 첫 표는 「지금 판정과 n칸 다름(확인)」", v["also"].startswith("이 문서의 다른 표 1개에도 이 판정이 쓰입니다") and f"{CAREER}: 지금 판정과 " in v["also"] and "칸 다름(확인)" in v["also"]
              and v["alsoLinks"] == [CAREER], v["also"])
        page.locator(f"ul.tty-vars input[value='{tw['B2']}']").click()   # 그 고정 이름을 가변으로 두면 — 이 표에만 있는 고정 머리글이 없어져 따로 확정이 꺼진다
        v = page.evaluate(VIEW)
        check("가변 체크를 바꾸면 단추가 다시 정해짐 — 「이 표만 따로 확정」 꺼짐 · 까닭은 풍선 도움말", v["bar"] == [["이 확정본 고치기", False], ["이 표만 따로 확정", True]]
              and v["apartTip"].startswith("이 표에만 있는 고정 머리글이 없습니다") and "따로 확정은 지금 안 됩니다" in v["barNote"], (v["bar"], v["apartTip"][:60]))
        page.locator(f"ul.tty-vars input[value='{tw['B2']}']").click()
        fit = page.evaluate(FIT)
        check("단추 둘 · 안내 줄 — 열 안에 들어감", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "8_choose.png"))
        page.locator(".tty-bar .tty-new").click()
        page.wait_for_selector(".tty-wrap .tty-bar .tty-ok", timeout=60000)
        page.wait_for_timeout(300)
        v, es = page.evaluate(VIEW), entries()
        puts = [json.loads(b) for m, u, b in sent if m == "PUT" and u.endswith(f"/tables/{TWIN}/type")]
        second = next((e["id"] for e in es if e["id"] != first), None)
        check("「이 표만 따로 확정」 — 요청에 mode new · 확정본이 둘(첫 확정본은 판 그대로) · 이 표는 새 확정본", bool(puts) and puts[-1].get("mode") == "new" and len(es) == 2 and bool(second)
              and next(e["rev"] for e in es if e["id"] == first) == 2 and api_view(doc, TWIN)["match"]["id"] == second and v["stateKey"] == "confirmed" and not v["also"]
              and sorted(e["tag"] for e in v["entries"]) == ["이 표에 맞음", "이 표에 쓰임"], (puts[-1:], es, v["entries"]))
        a1 = api_view(doc)
        check("첫 표는 첫 확정본 그대로(B2 는 값 칸) · 둘째 표는 제 확정본으로 B2 가 행헤더", a1["match"]["id"] == first and {c["ref"]: c["role"] for c in a1["judgment"]["cells"]}["B2"] == "field" and a1["also"] == []
              and {c["ref"]: c["role"] for c in api_view(doc, TWIN)["judgment"]["cells"]}["B2"] == "rowhead", (a1["match"], a1["also"]))
        page.screenshot(path=str(OUT / "9_apart.png"))

        # ---- 8. 양식이 정해지지 않은 문서
        page.goto(f"{base}/#w={ndoc}")
        page.reload()
        wait_doc(page, ndoc)
        corner(page, CAREER)
        check("양식이 없는 문서 — 표 메뉴에 항목은 있음(켜져 있음)", {x["text"]: x["disabled"] for x in menu(page)}.get("양식의 표 판정…") is False, [x["text"] for x in menu(page)])
        page.locator(".ctx-menu[data-by='tmn'] button:has-text('양식의 표 판정')").first.click()
        page.wait_for_function("(s) => { const t = document.getElementById('toast'); return !t.hidden && t.textContent.startsWith(s); }", arg=NO_FORM, timeout=60000)
        check("누르면 알림 「양식이 정해지지 않은 문서입니다 — 양식 정보에서 양식을 고르세요」 · 열은 안 열림", page.evaluate("() => heads.dlg") != "tblType" and page.locator(".tty-wrap").count() == 0,
              page.evaluate("() => document.getElementById('toast').textContent"))
        page.evaluate("() => showTab('Tables')")
        page.wait_for_selector("#tablesBox .tp-row", timeout=60000)
        page.wait_for_timeout(1500)
        check("양식이 없는 문서 — 「테이블」 탭에 표지 없음", page.evaluate(TAGS) == [], page.evaluate(TAGS))
        page.screenshot(path=str(OUT / "10_no_form.png"))
        browser.close()
    check("콘솔 오류 · 확인 창 없음", not errors, errors[:5])
finally:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'FAIL ' + str(len(fails)) if fails else 'ALL PASS'}")
sys.exit(1 if fails else 0)

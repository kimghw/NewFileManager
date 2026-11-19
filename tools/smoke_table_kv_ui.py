"""표의 키-값 보기 · 다른 표에서 가져오기 · 매핑 규칙(spec_테이블매니저 ② §7 「키-값 추출과 매핑」 — 표 메뉴 「키-값으로 보기 · 매핑…」) 화면 확인 —
임시 서버(임시 작업 폴더 · 임시 헤딩 저장소 = 매핑 규칙 파일, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_table_kv_ui.py <그림·임시 폴더> [--port 18198]

연구개발계획서_양식.hwpx 를 API 로 올리고 「연구책임자」 인적사항 표(t6599 — 원본)의 값 칸 10개를 표 채우기 반영 끝점으로 채운다 → `#w=<id>` 로 열어
① 머리글이 같은 표 = 같은 타입(t6932): 표 손잡이 → 표 메뉴 「키-값으로 보기 · 매핑…」(「에이전트로 표 채우기…」 바로 뒤) → 2열 「키-값 · t6932」(키-값 11줄 · 줄에 올리면 문서의 그 칸 표시) →
  원본 표 고르기 → 계획 요약(「넣을 수 있음 10 · 같음 1 · 겹침 0 · 짝 없음 0」 · 「같은 타입」 — 짝 없는 항목도 쓰인 규칙도 없어 매핑 규칙 묶음은 안 보임) · 「지금 (빈 칸) → 넣을 값 …」 → 두 칸만 골라 「고른 2칸 넣기」
  (문서 칸 글 · 실행 취소 1개 · 다시 계획 = 넣을 수 있음 8).
② 머리글이 다른 표 = 다른 타입(t7685 「책임자 · 실무 담당자」): 계획 = 짝 0(「다른 타입」) → 「짝 없는 항목」 에서 원본 「직장 › 기관명」 · 이 표 「책임자 › 기관명」 을 골라 「머리글 바꿔 읽기」(다른 칸 5개도 함께)
  → 규칙 줄 「직장 → 책임자」 · 넣을 수 있음 6 → 머리글 수가 다른 두 칸은 「이 칸만 짝짓기」 → 규칙 줄 「칸 짝」 · 넣을 수 있음 7 → 「저장된 매핑 규칙 1」(지금 쓰임 · 「다른 타입」) → 「고른 7칸 넣기」
  → 규칙 줄 ✕(칸 짝) → 저장된 묶음 「지우기」 → 알림의 「되돌리기」.
③ 구분 기준으로 묶어 넣기(같은 파일의 둘째 작업 — API 로 미리 꾸민다: 받을 표 t7685 의 묶음 머리를 「주관연구개발기관」 · 「공동연구개발기관」 으로, 원본 표 둘(t6599 · t6932)의 묶음 머리를 비우고 값을 채움):
  원본 표 둘을 목록에서 체크 → 「가져오기」 → 단추 아래 작은 고르기 창(「기관으로」 · 「기준 없이(키 그대로)」) → 「기관으로」 → 원본마다 「어느 기관의 것」 줄(표 앞 글에서 읽음) ·
  값마다 묶인 계획(「주관연구개발기관 — 넣을 수 있음 6 · 겹침 0」 · 「공동연구개발기관 — 넣을 수 있음 8 · 겹침 0」) → 값을 바꾸면(둘 다 공동) 같은 칸에 걸려 모두 겹침 → 되돌려 「고른 14칸 넣기」.
④ 값을 더해서 넣기(둘째 작업 — 머리글이 같은 표 셋 「CTE1 · CTE2 · CTE3」: 앞 둘의 「개발 연차」 칸에 수를 미리 넣음): 원본 둘 체크 → 「가져오기」 → 고르기 창의 「값을 더해서 넣기」 →
  「지금 (빈 칸) → 넣을 값 1,200 (= 500 + 700)」 · 일부만 값인 칸은 「확인」(처음에는 안 고름) · 수가 아닌 글은 고를 수 없음 → 「고른 1칸 넣기」.
⑤ 다른 표로 나눠 넣기(셋째 작업 — 원본 표 t7685 의 묶음 머리를 기관 값 머리로 고치고 값을 채움 · 받을 표 둘의 묶음 머리를 비움): 받을 표 둘 체크 → 「나눠 넣기」 → 기준 고르기 창(「기관으로」) →
  받을 표마다 값 줄 → 받을 표마다 묶인 계획(「고른 14칸 넣기」) → 구분 기준의 값 고르기: 계획 위 값 표지 「주관연구개발기관」 을 끄면 그 값의 6줄이 흐려지고 「고른 8칸 넣기」 →
  넣기(꺼 둔 값의 받을 표는 빈 채 그대로) → 꺼 둔 값을 기억한다: 이 표의 타입으로 저장됨(`/api/table-maps/offs`) · 화면을 새로 고쳐 다시 열어도 꺼진 채(「꺼 둔 값 1 — 기억됨」) →
  값 표지 줄 「모두」(저장도 지워짐) → 「고른 6칸 넣기」(편집 둘 — 넣기마다 받을 표들에 한 번의 편집).
⑥ 칸마다 넣는 방식(둘째 작업 — 받을 표 CTE3 의 첫 칸에는 ④ 에서 넣은 1,200 이 있다): 원본 CTE1 하나를 기준 없이 가져오면 그 칸은 겹침 → 줄의 「넣는 방식…」 → 「이 칸만」 → 「더하기」 → 저장 →
  표지 「더하기」 · 「지금 「1,200」 → 넣을 값 1,700 (= 1,200 + 500)」 · 「확인」(처음에는 안 고름) → 그 줄만 켜서 넣기 → 다시 받은 계획은 또 더한 것이고 다시 꺼져 있다 → 「넣는 방식」 묶음의 ✕ → 겹침으로.
⑦ 계산 칸 다시 계산(둘째 작업 — 「계」 줄 · 「계」 열이 있는 표 t1339 의 값 칸 12개에 수를 넣음): 「계산 칸 다시 계산」 묶음 → 「다시 계산할 칸 보기」 → 8줄(「지금 (빈 칸) → 계산한 값 30 (=SUM(D2:E2))」) →
  줄 합을 끄면 그에 기대는 합의 합도 꺼짐 → 다시 켜 「고른 8칸 넣기」 → 저절로 다시 읽어 「다시 계산할 칸 0 · 같음 8」 →
  줄 합 · 열 합을 틀리게 고치고 합의 합을 비움(API): 합의 합은 그 지금 값으로 셈한 것이라 「확인」(안 고름) · 줄 합을 같이 고치면 꺼지고 못 고름 → 넣으면 줄 합만 고쳐진다.
열 폭 넘침 · 콘솔 오류."""
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
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18198)
args = ap.parse_args()
OUT = Path(args.out).resolve()
RND = ROOT / "samples" / "연구개발계획서_양식.hwpx"
SRC, DST, OTHER = "t6599", "t6932", "t7685"
VALS = {"c6604": "홍길동", "c6608": "대한민국", "c6612": "Hong Gildong", "c6616": "12345678", "c6622": "한국선급", "c6626": "051-000-0000",
        "c6630": "연구본부", "c6634": "010-0000-0000", "c6638": "책임연구원", "c6642": "hong@example.org"}
NAME_TO, NATION_TO = "c6937", "c6941"   # t6932 의 「개인 › 국문」 · 「개인 › 국문 › 국적」 칸
LEAD, PART = "주관연구개발기관", "공동연구개발기관"   # 묶어 넣기 — 받을 표(t7685)의 기관 값 머리
CTE_A, CTE_B, CTE_C = "t11904", "t12105", "t12304"   # 더해서 넣기 — 머리글이 같은 표 셋(같은 타입 · 같은 키)
VALS_O = {"c7704": "한국선급", "c7708": "051-000-0000", "c7712": "연구본부", "c7716": "010-0000-0000", "c7720": "책임연구원", "c7724": "hong@example.org",   # 나눠 넣기 — 원본 표(t7685)의 값(주관 6 · 공동 8)
          "c7731": "김공동", "c7735": "Kim Gongdong", "c7739": "한국해양대학교", "c7743": "051-111-1111", "c7747": "기계공학부", "c7751": "010-1111-1111", "c7755": "교수", "c7759": "kim@example.org"}
VALS_B = {"c6937": "김공동", "c6945": "Kim Gongdong", "c6955": "한국해양대학교", "c6959": "051-111-1111", "c6963": "기계공학부", "c6967": "010-1111-1111", "c6971": "교수", "c6975": "kim@example.org"}

OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
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


VIEW = """() => { const w = document.querySelector('.tkv-wrap'); if (!w) return null;
  const txt = (e) => (e ? e.textContent : '');
  const key = (tr) => { const k = tr.querySelector('.tkv-key'); return k && k.firstChild ? k.firstChild.textContent : ''; };
  const items = [...w.querySelectorAll('.tkv-items table.tkv-list tbody tr')].map((tr) => ({ ref: txt(tr.querySelector('.hlink')), key: key(tr), val: txt(tr.querySelector('.tkv-val')) }));
  const pairs = [...w.querySelectorAll('.tkv-plan table.tkv-pairs tbody tr')].map((tr) => ({ ref: txt(tr.querySelector('.hlink')), key: key(tr), val: txt(tr.querySelector('.tkv-val')),
    status: tr.className.replace('tkv-', ''), on: tr.querySelector('input').checked, off: tr.querySelector('input').disabled, rule: txt(tr.querySelector('.tkv-key .hb')) }));
  const left = [...w.querySelectorAll('.tkv-left table.tkv-unmatched')].map((t) => [...t.querySelectorAll('tbody tr')].map((tr) => ({ key: key(tr), pick: !!tr.querySelector('input[type=radio]:not(:disabled)') })));
  const btn = w.querySelector('.tkv-bar .btn.primary'), rules = w.querySelector('.tkv-rules'), d = w.querySelector('.tkv-left');
  return { title: document.getElementById('headsDlgTitle').textContent, kind: heads.dlg, sum: txt(w.querySelector('p.tkv-sum')), plansum: txt(w.querySelector('.tkv-plansum')),
    kindTag: txt(w.querySelector('.tkv-planhead .hb')), kindTip: (w.querySelector('.tkv-planhead .hb') || {}).title || '', options: [...w.querySelectorAll('.tkv-srcs li')].map((li) => ({ value: li.querySelector('input').value, text: li.textContent })),
    btn: txt(btn), btnOff: !!(btn && btn.disabled), items, pairs, left, leftOpen: !!(d && d.open),
    rules: rules ? [...rules.querySelectorAll('.tkv-rule')].map((li) => txt(li.querySelector('.hb')) + ' ' + txt(li.querySelector('.tkv-rule-text'))) : null, rulesNote: rules ? txt(rules.querySelector('.hnote')) : '',
    values: [...w.querySelectorAll('.tkv-sources tbody tr')].map((tr) => ({ table: txt(tr.querySelector('.hlink')), value: (tr.querySelector('select.tkv-value') || {}).value || '', read: txt(tr.children[2]), fill: txt(tr.lastElementChild) })),
    groups: [...w.querySelectorAll('.tkv-group > summary')].map((x) => x.textContent), srcCol: [...new Set([...w.querySelectorAll('.tkv-group td.tkv-srccol')].map((x) => x.textContent))],
    bar: [...w.querySelectorAll('.tkv-pairbar .btn')].map((b) => b.textContent), maps: txt(w.querySelector('.tkv-maps > summary')),
    mapRows: [...w.querySelectorAll('.tkv-maps .tkv-map')].map((li) => ({ name: txt(li.querySelector('.tkv-map-name')), used: !!li.querySelector('.hb.chg'), kind: txt(li.querySelector('.tkv-map-top .hb:not(.chg)')),
      meta: txt(li.querySelector('.tkv-map-meta')) })) }; }"""
FIT = """() => { const p = document.getElementById('headsDlg'), r = p.getBoundingClientRect();
  const bad = [...p.querySelectorAll('.tkv-wrap *')].filter(e => e.getClientRects().length && (e.getBoundingClientRect().right > r.right + 1 || e.getBoundingClientRect().left < r.left - 1)).slice(0, 6).map(e => e.className || e.tagName);
  return { width: Math.round(r.width), bad, bodyOver: document.getElementById('headsDlgBody').scrollWidth - document.getElementById('headsDlgBody').clientWidth }; }"""
PICK = """([side, label]) => { const t = document.querySelectorAll('.tkv-left table.tkv-unmatched')[side]; if (!t) return false;
  const tr = [...t.querySelectorAll('tbody tr')].find((r) => { const k = r.querySelector('.tkv-key'); return k && k.firstChild && k.firstChild.textContent === label; });
  const rb = tr && tr.querySelector('input[type=radio]:not(:disabled)'); if (!rb) return false; rb.click(); return true; }"""
SUM_IS = "(s) => { const e = document.querySelector('.tkv-wrap .tkv-plansum'); return !!e && e.textContent.startsWith(s); }"
SPLIT_IS = "(s) => { const e = document.querySelector('.tkv-splitplan .tkv-splitsum'); return !!e && e.textContent.startsWith(s); }"
SPLIT = """() => { const w = document.querySelector('.tkv-splitplan'); if (!w) return null; const txt = (e) => (e ? e.textContent : '');
  return { kind: txt(w.querySelector('.tkv-type')), sum: txt(w.querySelector('.tkv-splitsum')), btn: txt(w.querySelector('.tkv-splitbar .btn.primary')),
    targets: [...w.querySelectorAll('.tkv-targets tbody tr')].map((tr) => ({ table: txt(tr.querySelector('.hlink')), value: (tr.querySelector('select.tkv-value') || {}).value || '', read: txt(tr.children[2]), fill: txt(tr.lastElementChild) })),
    groups: [...w.querySelectorAll('.tkv-sgroup > summary')].map((x) => x.textContent), rows: w.querySelectorAll('.tkv-sgroup table.tkv-pairs tbody tr').length,
    first: txt(w.querySelector('.tkv-sgroup table.tkv-pairs tbody tr .tkv-val')) }; }"""
CHIPS = """() => { const d = document.querySelector('.tkv-splitplan .tkv-div'); if (!d) return null;
  return { lab: (d.querySelector('.tkv-lab') || {}).textContent || '', chips: [...d.querySelectorAll('label')].map((l) => [l.textContent, l.querySelector('input').checked]),
    out: document.querySelectorAll('.tkv-splitplan tr.tkv-out').length, outOff: [...document.querySelectorAll('.tkv-splitplan tr.tkv-out input')].every((c) => c.disabled && !c.checked),
    btn: (document.querySelector('.tkv-splitbar .btn.primary') || {}).textContent || '', kept: (() => { const n = d.querySelector('.tkv-kept'); return n && !n.hidden ? n.textContent : ''; })() }; }"""
ROW = """(ref) => { const tr = [...document.querySelectorAll('.tkv-plan table.tkv-pairs tbody tr')].find((r) => (r.querySelector('.hlink') || {}).textContent === ref); if (!tr) return null;
  const cb = tr.querySelector('input'); return { cls: tr.className, op: (tr.querySelector('.tkv-op') || {}).textContent || '', val: tr.querySelector('.tkv-val').textContent, on: cb.checked, off: cb.disabled }; }"""
ROW_DO = """([ref, what]) => { const tr = [...document.querySelectorAll('.tkv-plan table.tkv-pairs tbody tr')].find((r) => (r.querySelector('.hlink') || {}).textContent === ref);
  (what === 'check' ? tr.querySelector('input') : tr.querySelector('.tkv-oppick')).click(); }"""
RC = """() => { const b = document.querySelector('.tkv-recalc'); if (!b) return null; const txt = (e) => (e ? e.textContent : '');
  return { head: txt(b.querySelector('h3')), sum: txt(b.querySelector('.tkv-recalcsum')), btn: txt(b.querySelector('.tkv-recalcbar .btn.primary')), get: txt(b.querySelector('.tkv-recalc-get')),
    rows: [...b.querySelectorAll('table.tkv-recalcs tbody tr')].map((tr) => ({ ref: txt(tr.querySelector('.hlink')), val: txt(tr.querySelector('.tkv-val')), on: tr.querySelector('input').checked, off: tr.querySelector('input').disabled })) }; }"""
RC_CLICK = "(ref) => { [...document.querySelectorAll('.tkv-recalc table.tkv-recalcs tbody tr')].find((r) => (r.querySelector('.hlink') || {}).textContent === ref).querySelector('input').click(); }"
RECALC_T = "t1339"   # 「계」 줄 · 「계」 열이 있는 표(값 칸 12 · 수식 칸 8)
CELL = "(c) => (document.querySelector(`#doc td[data-cell='${c}']`) || {}).textContent || ''"


def find(bs, tid):
    for b in bs:
        if b.get("type") == "table":
            if b["id"] == tid:
                return b
            for c in b.get("cells") or []:
                hit = find(c.get("blocks") or [], tid)
                if hit:
                    return hit
    return None


def maps():
    return requests.get(f"{base}/api/table-maps", timeout=30).json()["maps"]


MENU = """() => { const m = document.querySelector('.ctx-menu'); return m && !m.hidden ? [...m.querySelectorAll('button')].map((b) => b.textContent) : null; }"""


def pick(page, tids):
    """원본 표 목록에서 tids 만 체크한다."""
    page.evaluate("""(ids) => { for (const cb of document.querySelectorAll('.tkv-srcs input')) if (cb.checked !== ids.includes(cb.value)) cb.click(); }""", tids)


def source(page, tid):
    """원본 표 하나를 체크하고 「가져오기」 — 이 표에 구분 기준의 머리글이 없어 묻지 않고 계획을 세운다(1대1)."""
    pick(page, [tid])
    page.locator(".tkv-from .tkv-get").click()
    page.wait_for_selector(".tkv-wrap .tkv-plansum", timeout=60000)


def grouped_doc():
    """같은 파일의 둘째 작업을 묶어 넣을 꼴로 꾸민다(API) → 문서 id. 받을 표 OTHER 의 묶음 머리 = 기관 값 머리 · 원본 표 둘의 묶음 머리(「개인」 · 「직장」)는 비움 · 값 채움."""
    r = requests.post(f"{base}/api/docs?new=1", files={"file": (RND.name, RND.read_bytes())}, timeout=120)
    r.raise_for_status()
    g = r.json()["docId"]
    bs = requests.get(f"{base}/api/docs/{g}", timeout=120).json()["blocks"]
    ok = True
    for tid in (SRC, DST):
        by = {c["text"]: c for c in find(bs, tid)["cells"]}
        for head in ("개인", "직장"):
            pid = next(b["id"] for b in by[head]["blocks"] if b["type"] == "paragraph")
            ok = ok and requests.patch(f"{base}/api/docs/{g}/blocks/{pid}", json={"text": ""}, timeout=120).status_code == 200
    by = {c["text"]: c["id"] for c in find(bs, OTHER)["cells"]}
    fills = [(OTHER, [{"cell": by["책임자"], "text": LEAD}, {"cell": by["실무\n담당자"], "text": PART}]), (SRC, [{"cell": k, "text": v} for k, v in VALS.items()]), (DST, [{"cell": k, "text": v} for k, v in VALS_B.items()])]
    for tid, body in fills:
        ok = ok and requests.post(f"{base}/api/docs/{g}/tables/{tid}/fill/apply", json={"fills": body}, timeout=120).status_code == 200
    # 더해서 넣기용 — 머리글이 같은 표 셋 가운데 원본 둘의 「개발 연차」 칸에 수를 넣는다(첫 칸: 둘 다 수 · 둘째: 한쪽만 · 셋째: 한쪽은 수가 아닌 글)
    kv = {t: requests.get(f"{base}/api/docs/{g}/tables/{t}/kv", timeout=120).json() for t in (CTE_A, CTE_B, CTE_C)}
    keys = [i["key"] for i in kv[CTE_A]["items"] if i["key"] and i["key"].endswith("|개발연차") and i["empty"] and i["key"] not in kv[CTE_A]["dups"]][:3]
    cell = {t: {i["key"]: i["cell"] for i in v["items"]} for t, v in kv.items()}
    sums = {CTE_A: [("500", keys[0]), ("1,000", keys[1]), ("시험 평가를 수행한다.", keys[2])], CTE_B: [("700", keys[0]), ("7", keys[2])]}
    for tid, rows in sums.items():
        ok = ok and requests.post(f"{base}/api/docs/{g}/tables/{tid}/fill/apply", json={"fills": [{"cell": cell[tid][k], "text": v} for v, k in rows]}, timeout=120).status_code == 200
    return g, ok, [cell[CTE_C][k] for k in keys]


def split_doc():
    """같은 파일의 셋째 작업을 나눠 넣을 꼴로 꾸민다(API) → 문서 id. 원본 표 OTHER 의 묶음 머리 = 기관 값 머리 · 값 채움 / 받을 표 둘(SRC · DST)의 묶음 머리(「개인」 · 「직장」)는 비움(값 칸은 빈 채)."""
    r = requests.post(f"{base}/api/docs?new=1", files={"file": (RND.name, RND.read_bytes())}, timeout=120)
    r.raise_for_status()
    g = r.json()["docId"]
    bs = requests.get(f"{base}/api/docs/{g}", timeout=120).json()["blocks"]
    ok = True
    for tid in (SRC, DST):
        by = {c["text"]: c for c in find(bs, tid)["cells"]}
        for head in ("개인", "직장"):
            pid = next(b["id"] for b in by[head]["blocks"] if b["type"] == "paragraph")
            ok = ok and requests.patch(f"{base}/api/docs/{g}/blocks/{pid}", json={"text": ""}, timeout=120).status_code == 200
    by = {c["text"]: c["id"] for c in find(bs, OTHER)["cells"]}
    fills = [{"cell": by["책임자"], "text": LEAD}, {"cell": by["실무\n담당자"], "text": PART}, *({"cell": k, "text": v} for k, v in VALS_O.items())]
    ok = ok and requests.post(f"{base}/api/docs/{g}/tables/{OTHER}/fill/apply", json={"fills": fills}, timeout=120).status_code == 200
    return g, ok


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
    blocks = requests.get(f"{base}/api/docs/{doc}", timeout=120).json()["blocks"]
    check("견본의 인적사항 표 둘 · 「책임자 · 실무 담당자」 표", all(find(blocks, t) is not None for t in (SRC, DST, OTHER)))
    fr = requests.post(f"{base}/api/docs/{doc}/tables/{SRC}/fill/apply", json={"fills": [{"cell": k, "text": v} for k, v in VALS.items()]}, timeout=120)
    check("원본 표의 값 칸 채우기(표 채우기 반영 끝점)", fr.status_code == 200, fr.text[:300])
    kv = requests.get(f"{base}/api/docs/{doc}/tables/{DST}/kv", timeout=120)
    check("서버 추출 — 값 칸 11 · 빈 칸 10 · 보류 없음", kv.status_code == 200 and kv.json()["counts"] == {"items": 11, "keyed": 11, "empty": 10, "dups": 0} and kv.json()["held"] == [], kv.text[:300])
    sp = requests.post(f"{base}/api/docs/{doc}/tables/{DST}/kv/plan", json={"from": {"table": SRC}}, timeout=120).json()
    check("서버 계획 — 넣을 수 있음 10 · 같음 1 · 같은 타입(저장된 규칙 없음)", sp["counts"]["fill"] == 10 and sp["counts"]["same"] == 1 and sp["types"]["same"] and sp["rules"] is None, (sp["counts"], sp.get("types")))
    check("매핑 규칙 저장소가 비어 있음(임시 헤딩 저장소)", maps() == [])
    gdoc, gok, sum_cells = grouped_doc()
    gkv = requests.get(f"{base}/api/docs/{gdoc}/tables/{OTHER}/kv", timeout=120).json()
    check("묶어 넣기용 둘째 작업 — 받을 표에 기관 값 머리 둘(서버 bases)", gok and gdoc != doc and [(b["basis"], b["on"], [v["part"] for v in b["values"]]) for b in gkv.get("bases") or []] == [("org", "row", [LEAD, PART])], gkv.get("bases"))

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1700, "height": 1000})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("dialog", lambda d: (errors.append(f"dialog: {d.message}"), d.accept()))   # 확인 창은 쓰지 않는다 — 뜨면 오류로 센다
        page.goto(f"{base}/#w={doc}")
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=240000)
        page.wait_for_timeout(1500)

        # ---- 1. 표 메뉴의 새 항목
        corner(page, DST)
        texts = [x["text"] for x in menu(page)]
        dis = {x["text"]: x["disabled"] for x in menu(page)}
        check("표 메뉴 — 「키-값으로 보기 · 매핑…」 이 켜져 있고 「에이전트로 표 채우기…」 바로 뒤", dis.get("키-값으로 보기 · 매핑…") is False
              and texts.index("키-값으로 보기 · 매핑…") == texts.index("에이전트로 표 채우기…") + 1, texts)
        page.screenshot(path=str(OUT / "1_menu.png"))
        page.locator(".ctx-menu[data-by='tmn'] button:has-text('키-값으로 보기')").first.click()
        page.wait_for_selector(".tkv-wrap .tkv-items table.tkv-list")
        page.wait_for_timeout(300)

        # ---- 2. 2열 — 이 표의 키-값
        v = page.evaluate(VIEW)
        check("2열 「키-값 · t6932」(kind tblKv)", v["title"] == f"키-값 · {DST}" and v["kind"] == "tblKv", v["title"])
        check("요약 — 값 칸 11 · 빈 칸 10", v["sum"].startswith("값 칸 11 · 빈 칸 10"), v["sum"])
        check("키-값 11줄 — 첫 줄 「개인 › 국문」 · (빈 칸) · 「직장 › 주소」 는 서식의 글", len(v["items"]) == 11 and v["items"][0]["key"] == "개인 › 국문" and v["items"][0]["val"] == "(빈 칸)"
              and v["items"][-1]["key"] == "직장 › 주소" and v["items"][-1]["val"].startswith("(우:"), v["items"][:2])
        opts = {o["value"]: o["text"] for o in v["options"]}
        check("원본 표 목록(체크) — 이 표는 없고 다른 표는 번호 · id · 크기 · 글로", DST not in opts and SRC in opts and f". {SRC} · " in opts[SRC] and "×" in opts[SRC] and len(opts) > 50, (opts.get(SRC), len(opts)))
        page.locator(".tkv-items table.tkv-list tbody tr").first.hover()
        check("줄에 올리면 문서의 그 칸에 표시(td.tkv-hit)", page.evaluate("() => document.querySelectorAll('#doc td.tkv-hit').length") >= 1)
        page.mouse.move(5, 5)
        fit = page.evaluate(FIT)
        check("열 안에 들어감(가로 넘침 없음)", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "2_items.png"))

        # ---- 3. 다른 표에서 가져오기 — 계획
        source(page, SRC)
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 10", timeout=60000)
        v = page.evaluate(VIEW)
        check("계획 요약 — 「넣을 수 있음 10 · 같음 1 · 겹침 0 · 짝 없음 0」 · 「같은 타입」(도움말에 값을 채워도 안 바뀐다)", v["plansum"].startswith("넣을 수 있음 10 · 같음 1 · 겹침 0 · 짝 없음 0") and v["kindTag"] == "같은 타입"
              and "값을 채워도 바뀌지 않습니다" in v["kindTip"], (v["plansum"], v["kindTag"]))
        first = v["pairs"][0]
        check("짝 줄 — 「지금 (빈 칸) → 넣을 값 홍길동」 · 고른 채", first["key"] == "개인 › 국문" and first["val"].replace(" ", "") == "지금(빈칸)→넣을값홍길동" and first["on"] and not first["off"], first)
        same = v["pairs"][-1]
        check("같은 글의 칸은 고를 수 없음(「같음」)", same["status"] == "same" and same["off"] and not same["on"] and same["val"].startswith("같음"), same)
        check("짝 없는 항목도 쓰인 규칙도 없음 — 「매핑 규칙」 묶음 · 「짝 없는 항목」 이 안 보임 · 단추 「고른 10칸 넣기」", v["rules"] is None and not v["left"] and v["btn"] == "고른 10칸 넣기" and not v["btnOff"], (v["rules"], v["btn"]))
        page.locator(".tkv-pairs tbody tr").nth(2).hover()
        hit = page.evaluate("() => [document.querySelectorAll('#doc td.tkv-hit').length, document.querySelectorAll('#doc td.tkv-src').length]")
        check("짝 줄에 올리면 이 표의 칸 · 원본 표의 칸에 표시", hit[0] >= 1 and hit[1] >= 1, hit)
        page.mouse.move(5, 5)
        fit = page.evaluate(FIT)
        check("계획 — 열 안에 들어감", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "3_plan.png"))

        # ---- 4. 고른 칸만 넣기 — 실행 취소 1개 · 다시 계획
        undo0 = page.evaluate("() => state.undo")
        page.locator(".tkv-bar button:text-is('모두 풀기')").click()
        check("「모두 풀기」 — 단추가 꺼짐", page.evaluate(VIEW)["btnOff"])
        for i in (0, 1):
            page.locator(".tkv-pairs tbody tr").nth(i).locator("input").check()
        check("두 칸만 고름", page.evaluate(VIEW)["btn"] == "고른 2칸 넣기")
        page.locator(".tkv-bar .btn.primary").click()
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 8 · 같음 3", timeout=60000)
        page.wait_for_timeout(400)
        after = page.evaluate("([a, b]) => ({ a: (document.querySelector(`#doc td[data-cell='${a}']`) || {}).textContent || '', b: (document.querySelector(`#doc td[data-cell='${b}']`) || {}).textContent || '', undo: state.undo })", [NAME_TO, NATION_TO])
        check("문서의 두 칸에 값 · 실행 취소 1개", after["a"].strip() == "홍길동" and after["b"].strip() == "대한민국" and after["undo"] == undo0 + 1, (after, undo0))
        v = page.evaluate(VIEW)
        check("다시 계획 — 넣은 두 칸은 「같음」 · 푼 체크는 그대로(고른 0칸)", v["pairs"][0]["status"] == "same" and v["btn"] == "고른 0칸 넣기" and v["btnOff"], (v["pairs"][0], v["btn"]))

        # ---- 5. 머리글이 다른 표 — 매핑 규칙
        page.evaluate("(t) => tblKvView(t)", OTHER)
        page.wait_for_function("(t) => document.getElementById('headsDlgTitle').textContent === `키-값 · ${t}` && document.querySelector('.tkv-items table.tkv-list')", arg=OTHER, timeout=60000)
        source(page, SRC)
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 0", timeout=60000)
        page.wait_for_selector(".tkv-maps > summary", timeout=30000)
        v = page.evaluate(VIEW)
        check("다른 타입 — 짝 0 · 「짝 없음 29」 · 「다른 타입」 · 규칙 없음 안내", v["plansum"].startswith("넣을 수 있음 0 · 같음 0 · 겹침 0 · 짝 없음 29") and v["kindTag"] == "다른 타입"
              and not v["pairs"] and v["rules"] == [] and "규칙이 없습니다" in v["rulesNote"], (v["plansum"], v["kindTag"], v["rules"]))
        check("「짝 없는 항목」 이 열려 있고 두 쪽 모두 고를 수 있음 · 저장된 매핑 규칙 0", v["leftOpen"] and len(v["left"]) == 2 and len(v["left"][0]) == 11 and len(v["left"][1]) == 18
              and all(x["pick"] for x in v["left"][0]) and v["maps"].replace(" ", "") == "저장된매핑규칙0", (v["leftOpen"], [len(x) for x in v["left"]], v["maps"]))
        ok = page.evaluate(PICK, [0, "직장 › 기관명"]) and page.evaluate(PICK, [1, "책임자 › 기관명"])
        v = page.evaluate(VIEW)
        check("머리글 하나만 다른 두 칸 — 「머리글 바꿔 읽기 — 「직장」 → 「책임자」 (다른 칸 5개도 함께)」 · 「이 칸만」", ok and len(v["bar"]) == 2
              and v["bar"][0] == "머리글 바꿔 읽기 — 「직장」 → 「책임자」 (다른 칸 5개도 함께)" and v["bar"][1] == "이 칸만", v["bar"])
        page.screenshot(path=str(OUT / "4_pairing.png"))
        page.locator(".tkv-pairbar .btn.tkv-go").click()
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 6", timeout=60000)
        v = page.evaluate(VIEW)
        saved = maps()
        check("바로 저장 — 규칙 줄 「머리글 직장 → 책임자」 · 넣을 수 있음 6(규칙 꼬리표) · 서버에 묶음 1(alias 1)", v["rules"] == ["머리글 직장 → 책임자"] and len(v["pairs"]) == 6
              and all(p["rule"] == "규칙" and p["status"] == "fill" for p in v["pairs"]) and len(saved) == 1 and saved[0]["alias"] == [{"from": "직장", "to": "책임자"}] and not saved[0]["pairs"], (v["rules"], v["plansum"], saved))
        ok = page.evaluate(PICK, [0, "개인 › 국문"]) and page.evaluate(PICK, [1, "책임자 › 성명 › 국문"])
        v = page.evaluate(VIEW)
        check("머리글 수가 다른 두 칸 — 「이 칸만 짝짓기」 하나", ok and v["bar"] == ["이 칸만 짝짓기"], v["bar"])
        page.locator(".tkv-pairbar .btn.tkv-go").click()
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 7", timeout=60000)
        page.wait_for_function("() => document.querySelectorAll('.tkv-maps .tkv-map').length === 1", timeout=30000)
        v = page.evaluate(VIEW)
        check("규칙 줄 둘(머리글 · 칸 짝) · 칸 짝 꼬리표 · 「저장된 매핑 규칙 1」(지금 쓰임 · 「다른 타입」)", v["rules"] == ["머리글 직장 → 책임자", "칸 짝 개인 › 국문 → 책임자 › 성명 › 국문"]
              and [p["rule"] for p in v["pairs"]].count("칸 짝") == 1 and v["maps"].replace(" ", "") == "저장된매핑규칙1" and v["mapRows"][0]["used"] and v["mapRows"][0]["kind"] == "다른 타입",
              (v["rules"], v["maps"], v["mapRows"]))
        fit = page.evaluate(FIT)
        check("매핑 규칙 — 열 안에 들어감", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "5_rules.png"))
        org = next(p["ref"] for p in v["pairs"] if p["key"] == "책임자 › 기관명")
        check("단추 「고른 7칸 넣기」", v["btn"] == "고른 7칸 넣기" and not v["btnOff"], v["btn"])
        page.locator(".tkv-bar .btn.primary").click()
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 0 · 같음 7", timeout=60000)
        kv2 = requests.get(f"{base}/api/docs/{doc}/tables/{OTHER}/kv", timeout=120).json()
        got = {i["label"]: i["text"] for i in kv2["items"]}
        check("규칙으로 맺은 짝의 값이 문서에 들어감", got.get("책임자 › 기관명") == "한국선급" and got.get("책임자 › 성명 › 국문") == "홍길동" and got.get("책임자 › 직위 › 전자우편") == "hong@example.org", (org, {k: got[k] for k in list(got)[:4]}))

        # ---- 6. 규칙 지우기(✕) · 묶음 지우기 · 되돌리기
        page.locator(".tkv-rules .tkv-rule", has_text="칸 짝").locator(".tkv-x").click()
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 0 · 같음 6", timeout=60000)
        v = page.evaluate(VIEW)
        check("✕ — 칸 짝이 지워지고 그 짝이 계획에서 빠짐(서버 묶음 pairs 0)", v["rules"] == ["머리글 직장 → 책임자"] and len(v["pairs"]) == 6 and maps()[0]["pairs"] == [], (v["rules"], maps()))
        page.evaluate("() => { document.querySelector('.tkv-maps').open = true; }")
        page.locator(".tkv-maps .tkv-map button:text-is('지우기')").click()
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 0 · 같음 0", timeout=60000)
        page.wait_for_function("() => document.querySelectorAll('.tkv-maps .tkv-map').length === 0", timeout=30000)
        v = page.evaluate(VIEW)
        check("묶음 지우기 — 확인 창 없이 지움 · 계획은 짝 0 · 알림에 「되돌리기」", maps() == [] and not v["pairs"] and v["rules"] == [] and page.locator("#toast .toast-act", has_text="되돌리기").count() == 1, (maps(), v["rules"]))
        page.locator("#toast .toast-act").click()
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 0 · 같음 6", timeout=60000)
        back = maps()
        check("「되돌리기」 — 같은 내용의 묶음이 다시 생기고 계획이 그 규칙을 씀", len(back) == 1 and back[0]["alias"] == [{"from": "직장", "to": "책임자"}] and page.evaluate(VIEW)["rules"] == ["머리글 직장 → 책임자"], back)
        page.screenshot(path=str(OUT / "6_after.png"))

        # ---- 7. 구분 기준으로 묶어 넣기 — 원본 둘 체크 → 기준 고르기 창 → 값 줄 → 묶인 계획 → 넣기(둘째 작업)
        page.goto(f"{base}/#w={gdoc}")
        page.reload()
        page.wait_for_function("(g) => state.id === g && document.querySelector('#doc .sheet .para') != null", arg=gdoc, timeout=240000)
        page.wait_for_timeout(1500)
        page.evaluate("(t) => tblKvView(t)", OTHER)
        page.wait_for_function("(t) => document.getElementById('headsDlgTitle').textContent === `키-값 · ${t}` && document.querySelector('.tkv-srcs input')", arg=OTHER, timeout=60000)
        check("「가져오기」 는 원본 표를 고르기 전에는 꺼져 있음", page.locator(".tkv-from .tkv-get").is_disabled())
        pick(page, [SRC, DST])
        check("원본 표 둘 체크 — 「2개 고름」", page.locator(".tkv-from .tkv-count").text_content() == "2개 고름" and not page.locator(".tkv-from .tkv-get").is_disabled())
        page.locator(".tkv-from .tkv-get").click()
        page.wait_for_selector(".ctx-menu:not([hidden]) button")
        asked = page.evaluate(MENU)
        box = page.evaluate("() => { const m = document.querySelector('.ctx-menu').getBoundingClientRect(); return { w: m.width, h: m.height, vw: innerWidth, vh: innerHeight }; }")
        check("기준 고르기 창 — 이 표에 있는 기준(「기관으로」) · 「값을 더해서 넣기」(원본 둘 이상) · 「기준 없이(키 그대로)」 · 화면을 덮지 않는 작은 메뉴", asked == ["기관으로", "값을 더해서 넣기", "기준 없이(키 그대로)"] and box["w"] < 480 and box["h"] < 200, (asked, box))
        page.screenshot(path=str(OUT / "7_ask.png"))
        page.locator(".ctx-menu:not([hidden]) button", has_text="기관으로").click()
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 14", timeout=60000)
        v = page.evaluate(VIEW)
        check("묶어 넣기 — 머리 표지 「기관으로 묶음」 · 원본마다 값 줄(표 앞 글에서 읽음)", v["kindTag"] == "기관으로 묶음" and [(x["table"], x["value"], x["read"], x["fill"]) for x in v["values"]]
              == [(SRC, LEAD, "표 앞 글에서 읽음", "6"), (DST, PART, "표 앞 글에서 읽음", "8")], (v["kindTag"], v["values"]))
        check("계획은 값마다 묶어 — 「주관연구개발기관 — 넣을 수 있음 6 · 겹침 0」 · 「공동연구개발기관 — 넣을 수 있음 8 · 겹침 0」 · 원본 열", v["groups"] == [f"{LEAD} — 넣을 수 있음 6 · 겹침 0", f"{PART} — 넣을 수 있음 8 · 겹침 0"]
              and sorted(v["srcCol"]) == sorted([SRC, DST]) and v["btn"] == "고른 14칸 넣기" and len(v["pairs"]) == 14 and v["rules"] is None, (v["groups"], v["srcCol"], v["btn"]))
        fit = page.evaluate(FIT)
        check("묶어 넣기 — 열 안에 들어감", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "8_grouped.png"))
        page.locator(".tkv-sources tbody tr").nth(0).locator("select.tkv-value").select_option(PART)
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 0 · 같음 0 · 겹침 16", timeout=60000)
        v = page.evaluate(VIEW)
        check("값을 바꾸면(둘 다 공동) — 「직접 고름」 · 두 원본이 같은 칸에 걸려 모두 겹침(넣을 칸 없음)", v["values"][0]["read"] == "직접 고름" and v["groups"] == [f"{PART} — 넣을 수 있음 0 · 겹침 16"]
              and all(p["off"] and "원본 둘이 같은 칸" in p["val"] for p in v["pairs"]), (v["values"], v["groups"]))
        page.locator(".tkv-sources tbody tr").nth(0).locator("select.tkv-value").select_option(LEAD)
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 14", timeout=60000)
        undo0 = page.evaluate("() => state.undo")
        page.locator(".tkv-bar .btn.primary").click()
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 0 · 같음 14", timeout=60000)
        got = {i["label"]: i["text"] for i in requests.get(f"{base}/api/docs/{gdoc}/tables/{OTHER}/kv", timeout=120).json()["items"]}
        check("넣기 — 원본마다 제 기관의 머리글 아래로 · 실행 취소 1개", got.get(f"{LEAD} › 기관명") == "한국선급" and got.get(f"{PART} › 기관명") == "한국해양대학교" and got.get(f"{PART} › 국문") == "김공동"
              and got.get(f"{LEAD} › 성명 › 국문") == "" and page.evaluate("() => state.undo") == undo0 + 1, {k: got[k] for k in list(got)[:5]})
        page.screenshot(path=str(OUT / "9_grouped_after.png"))

        # ---- 8. 값을 더해서 넣기 — 원본 둘 체크 → 고르기 창의 「값을 더해서 넣기」 → 합의 풀이 · 확인 줄 · 수가 아닌 글 → 넣기(둘째 작업의 같은 타입 표 셋)
        page.evaluate("(t) => tblKvView(t)", CTE_C)
        page.wait_for_function("(t) => document.getElementById('headsDlgTitle').textContent === `키-값 · ${t}` && document.querySelector('.tkv-srcs input')", arg=CTE_C, timeout=60000)
        pick(page, [CTE_A, CTE_B])
        page.locator(".tkv-from .tkv-get").click()
        page.wait_for_selector(".ctx-menu:not([hidden]) button")
        asked = page.evaluate(MENU)
        check("고르기 창 — 「단계로」 · 「값을 더해서 넣기」 · 「기준 없이(키 그대로)」", asked == ["단계로", "값을 더해서 넣기", "기준 없이(키 그대로)"], asked)
        page.locator(".ctx-menu:not([hidden]) button", has_text="값을 더해서 넣기").click()
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 2(확인 1)", timeout=60000)
        v = page.evaluate(VIEW)
        fills = [p for p in v["pairs"] if p["status"] == "fill"]
        check("더해서 넣기 — 머리 표지 · 「지금 (빈 칸) → 넣을 값 1,200 (= 500 + 700)」 은 고른 채", v["kindTag"] == "값을 더해서 넣기" and len(fills) == 2
              and fills[0]["val"].replace(" ", "") == "지금(빈칸)→넣을값1,200(=500+700)" and fills[0]["on"], (v["kindTag"], fills))
        check("일부만 값인 칸 — 「확인」 · 「원본 2 가운데 1개만 값이 있습니다」 · 처음에는 안 고름", "넣을 값 1,000" in fills[1]["val"] and "확인" in fills[1]["val"]
              and "원본 2 가운데 1개만 값이 있습니다" in fills[1]["val"] and not fills[1]["on"] and not fills[1]["off"], fills[1])
        non = [p for p in v["pairs"] if p["status"] == "nonnum"]
        check("수가 아닌 글 — 고를 수 없고 까닭을 보임 · 단추 「고른 1칸 넣기」 · 요약에 「수가 아님 1」", len(non) == 1 and non[0]["off"] and "수가 아님" in non[0]["val"] and "수가 아닌 글" in non[0]["val"]
              and v["btn"] == "고른 1칸 넣기" and "수가 아님 1" in v["plansum"], (non, v["btn"], v["plansum"]))
        fit = page.evaluate(FIT)
        check("더해서 넣기 — 열 안에 들어감", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "10_sum.png"))
        undo0 = page.evaluate("() => state.undo")
        page.locator(".tkv-bar .btn.primary").click()
        page.wait_for_function(SUM_IS, arg="넣을 수 있음 1(확인 1)", timeout=60000)
        got = {i["cell"]: i["text"] for i in requests.get(f"{base}/api/docs/{gdoc}/tables/{CTE_C}/kv", timeout=120).json()["items"]}
        check("넣기 — 합이 든 칸만(확인 줄 · 수가 아닌 글은 그대로) · 실행 취소 1개", [got.get(c) for c in sum_cells] == ["1,200", "", ""] and page.evaluate("() => state.undo") == undo0 + 1, [got.get(c) for c in sum_cells])

        # ---- 9. 다른 표로 나눠 넣기 — 받을 표 둘 체크 → 「나눠 넣기」 → 기준 고르기 창 → 받을 표마다 값 줄 · 묶인 계획 → 넣기(셋째 작업)
        sdoc, sok = split_doc()
        check("나눠 넣기용 셋째 작업을 꾸밈(API)", sok and sdoc not in (doc, gdoc))
        page.goto(f"{base}/#w={sdoc}")
        page.reload()
        page.wait_for_function("(g) => state.id === g && document.querySelector('#doc .sheet .para') != null", arg=sdoc, timeout=240000)
        page.wait_for_timeout(1500)
        page.evaluate("(t) => tblKvView(t)", SRC)
        page.wait_for_function("(t) => document.getElementById('headsDlgTitle').textContent === `키-값 · ${t}` && document.querySelector('.tkv-srcs input')", arg=SRC, timeout=60000)
        check("기준이 없는 표 — 「다른 표로 나눠 넣기」 묶음이 안 보임", page.evaluate("() => document.querySelector('.tkv-split').childElementCount") == 0)
        page.evaluate("(t) => tblKvView(t)", OTHER)
        page.wait_for_function("(t) => document.getElementById('headsDlgTitle').textContent === `키-값 · ${t}` && document.querySelector('.tkv-tgts input')", arg=OTHER, timeout=60000)
        check("기준이 있는 표 — 「다른 표로 나눠 넣기」 묶음 · 「나눠 넣기」 는 고르기 전에는 꺼져 있음", page.locator(".tkv-split h3").text_content() == "다른 표로 나눠 넣기" and page.locator(".tkv-split .tkv-split-get").is_disabled())
        page.evaluate("""(ids) => { for (const cb of document.querySelectorAll('.tkv-tgts input')) if (cb.checked !== ids.includes(cb.value)) cb.click(); }""", [SRC, DST])
        page.locator(".tkv-split .tkv-split-get").click()
        page.wait_for_selector(".ctx-menu:not([hidden]) button")
        check("기준 고르기 창 — 이 표의 기준(「기관으로」)", page.evaluate(MENU) == ["기관으로"], page.evaluate(MENU))
        page.locator(".ctx-menu:not([hidden]) button", has_text="기관으로").click()
        page.wait_for_function(SPLIT_IS, arg="넣을 수 있음 14", timeout=60000)
        sv = page.evaluate(SPLIT)
        check("나눠 넣기 — 머리 표지 「기관으로 나눔」 · 받을 표마다 값 줄(표 앞 글에서 읽음)", sv["kind"] == "기관으로 나눔" and [(x["table"], x["value"], x["read"], x["fill"]) for x in sv["targets"]]
              == [(SRC, LEAD, "표 앞 글에서 읽음", "6"), (DST, PART, "표 앞 글에서 읽음", "8")], (sv["kind"], sv["targets"]))
        check("계획은 받을 표마다 묶어 · 단추 「고른 14칸 넣기」", sv["groups"] == [f"받을 표 {SRC} · {LEAD} — 넣을 수 있음 6 · 겹침 0", f"받을 표 {DST} · {PART} — 넣을 수 있음 8 · 겹침 0"]
              and sv["btn"] == "고른 14칸 넣기" and sv["rows"] == 14 and "넣을 값 한국선급" in sv["first"], sv)
        fit = page.evaluate(FIT)
        check("나눠 넣기 — 열 안에 들어감", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "11_split.png"))
        # 구분 기준의 값 고르기 — 계획 위의 값 표지를 끄면 그 값의 칸은 넣지 않는다(「주관」 을 꺼 「공동」 의 것만 넣는다)
        ch = page.evaluate(CHIPS)
        check("값 표지 줄 — 「기관」 의 값 둘(모두 켜짐 · 흐린 줄 없음)", bool(ch) and ch["lab"] == "기관" and ch["chips"] == [[LEAD, True], [PART, True]] and ch["out"] == 0, ch)
        page.locator(".tkv-splitplan .tkv-div label", has_text=LEAD).locator("input").click()
        page.wait_for_function("() => document.querySelectorAll('.tkv-splitplan tr.tkv-out').length > 0", timeout=60000)
        ch = page.evaluate(CHIPS)
        check("값 표지를 끄면 — 그 값의 6줄이 흐려지고 못 고름 · 단추 「고른 8칸 넣기」", ch["chips"] == [[LEAD, False], [PART, True]] and ch["out"] == 6 and ch["outOff"] and ch["btn"] == "고른 8칸 넣기", ch)
        fit = page.evaluate(FIT)
        check("값 표지 줄 — 열 안에 들어감", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "11_split_value_off.png"))
        undo0 = page.evaluate("() => state.undo")
        page.locator(".tkv-splitbar .btn.primary").click()
        page.wait_for_function(SPLIT_IS, arg="넣을 수 있음 6 · 같음 8", timeout=60000)
        ga = {i["label"]: i["text"] for i in requests.get(f"{base}/api/docs/{sdoc}/tables/{SRC}/kv", timeout=120).json()["items"]}
        gb = {i["label"]: i["text"] for i in requests.get(f"{base}/api/docs/{sdoc}/tables/{DST}/kv", timeout=120).json()["items"]}
        check("넣기 — 켜 둔 값의 칸만(꺼 둔 값의 받을 표는 빈 채 그대로) · 실행 취소 1개", ga.get("기관명") == "" and gb.get("기관명") == "한국해양대학교" and gb.get("국문") == "김공동"
              and page.evaluate("() => state.undo") == undo0 + 1, ({k: ga[k] for k in list(ga)[:5]}, {k: gb[k] for k in list(gb)[:5]}))
        ch = page.evaluate(CHIPS)
        check("다시 읽은 뒤에도 꺼 둔 값은 그대로 · 단추 「고른 0칸 넣기」", ch["chips"] == [[LEAD, False], [PART, True]] and ch["out"] == 6 and ch["btn"] == "고른 0칸 넣기", ch)
        # 꺼 둔 값을 기억한다 — 이 표(기준이 있는 표)의 타입으로 서버에 저장: 화면을 새로 고쳐(화면 메모리 없음) 다시 열어도 꺼진 채
        okv = requests.get(f"{base}/api/docs/{sdoc}/tables/{OTHER}/kv", timeout=120).json()
        otype = okv["type"]
        lead_part = next(v["part"] for b in okv["bases"] if b["basis"] == "org" for v in b["values"] if v["label"] == LEAD)
        page.wait_for_function("() => { const n = document.querySelector('.tkv-splitplan .tkv-kept'); return !!n && !n.hidden && n.textContent === '꺼 둔 값 1 — 기억됨'; }", timeout=60000)
        offs = requests.get(f"{base}/api/table-maps/offs", params={"type": otype}, timeout=120).json()
        check("꺼 둔 값 — 이 표의 타입으로 저장됨 · 값 표지 줄 끝에 「꺼 둔 값 1 — 기억됨」", offs == {"type": otype, "offs": {"org": [lead_part]}}, offs)
        page.reload()
        page.wait_for_function("(g) => state.id === g && document.querySelector('#doc .sheet .para') != null", arg=sdoc, timeout=240000)
        page.wait_for_timeout(1500)
        check("새로 고친 화면 — 화면 메모리에 꺼 둔 값 없음", page.evaluate("() => Object.keys(tblKv.vals).length") == 0)
        page.evaluate("(t) => tblKvView(t)", OTHER)
        page.wait_for_function("(t) => document.getElementById('headsDlgTitle').textContent === `키-값 · ${t}` && document.querySelector('.tkv-tgts input')", arg=OTHER, timeout=60000)
        page.evaluate("""(ids) => { for (const cb of document.querySelectorAll('.tkv-tgts input')) if (cb.checked !== ids.includes(cb.value)) cb.click(); }""", [SRC, DST])
        page.locator(".tkv-split .tkv-split-get").click()
        page.wait_for_selector(".ctx-menu:not([hidden]) button")
        page.locator(".ctx-menu:not([hidden]) button", has_text="기관으로").click()
        page.wait_for_function(SPLIT_IS, arg="넣을 수 있음 6 · 같음 8", timeout=60000)
        ch = page.evaluate(CHIPS)
        check("다시 열어도 꺼진 채 — 저장된 것으로 시작 · 「꺼 둔 값 1 — 기억됨」 · 단추 「고른 0칸 넣기」", ch["chips"] == [[LEAD, False], [PART, True]] and ch["out"] == 6 and ch["kept"] == "꺼 둔 값 1 — 기억됨"
              and ch["btn"] == "고른 0칸 넣기", ch)
        fit = page.evaluate(FIT)
        check("「기억됨」 글이 붙은 값 표지 줄 — 열 안에 들어감", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "11_split_value_kept.png"))
        page.locator(".tkv-splitplan .tkv-div button").first.click()   # 값 표지 줄의 첫 단추 = 「모두」
        page.wait_for_function("() => (document.querySelector('.tkv-splitbar .btn.primary') || {}).textContent === '고른 6칸 넣기'", timeout=60000)
        ch = page.evaluate(CHIPS)
        check("값 표지 줄 「모두」 — 다시 켜지고 흐린 줄 없음 · 단추 「고른 6칸 넣기」 · 「기억됨」 글 없음", ch["chips"] == [[LEAD, True], [PART, True]] and ch["out"] == 0 and ch["btn"] == "고른 6칸 넣기" and ch["kept"] == "", ch)
        for _ in range(50):   # 「모두」 = 그 기준의 저장도 지운다(저장 요청은 뒤따라 간다)
            offs = requests.get(f"{base}/api/table-maps/offs", params={"type": otype}, timeout=120).json()
            if not offs["offs"]:
                break
            time.sleep(.1)
        check("「모두」 — 저장된 꺼 둔 값도 지워짐", offs == {"type": otype, "offs": {}}, offs)
        undo1 = page.evaluate("() => state.undo")   # 새로 고친 화면의 셈에서 다시 센다
        page.locator(".tkv-splitbar .btn.primary").click()
        page.wait_for_function(SPLIT_IS, arg="넣을 수 있음 0 · 같음 14", timeout=60000)
        ga = {i["label"]: i["text"] for i in requests.get(f"{base}/api/docs/{sdoc}/tables/{SRC}/kv", timeout=120).json()["items"]}
        gb = {i["label"]: i["text"] for i in requests.get(f"{base}/api/docs/{sdoc}/tables/{DST}/kv", timeout=120).json()["items"]}
        check("남은 값을 넣으면 — 값마다 제 받을 표로(넣기마다 한 번의 편집 — 실행 취소 +1)", ga.get("기관명") == "한국선급" and ga.get("국문") == "" and gb.get("기관명") == "한국해양대학교" and gb.get("국문") == "김공동"
              and page.evaluate("() => state.undo") == undo1 + 1, ({k: ga[k] for k in list(ga)[:5]}, {k: gb[k] for k in list(gb)[:5]}))
        page.screenshot(path=str(OUT / "12_split_after.png"))

        # ---- 10. 칸마다 넣는 방식 — 겹친 칸의 줄에서 「넣는 방식…」 → 「이 칸만」 → 「더하기」 → 확인 줄을 켜서 넣기 → 다시 꺼짐 → ✕(둘째 작업 · 받을 표 CTE3 ← CTE1)
        ckv = requests.get(f"{base}/api/docs/{gdoc}/tables/{CTE_C}/kv", timeout=120).json()
        ctype, ref0 = ckv["type"], next(i["ref"] for i in ckv["items"] if i["cell"] == sum_cells[0])
        mine = lambda: [m for m in maps() if m["from"]["type"] == ctype and m["to"]["type"] == ctype]   # noqa: E731 — 이 타입 짝의 묶음
        page.goto(f"{base}/#w={gdoc}")
        page.reload()
        page.wait_for_function("(g) => state.id === g && document.querySelector('#doc .sheet .para') != null", arg=gdoc, timeout=240000)
        page.wait_for_timeout(1500)
        page.evaluate("(t) => tblKvView(t)", CTE_C)
        page.wait_for_function("(t) => document.getElementById('headsDlgTitle').textContent === `키-값 · ${t}` && document.querySelector('.tkv-srcs input')", arg=CTE_C, timeout=60000)
        pick(page, [CTE_A])
        page.locator(".tkv-from .tkv-get").click()
        page.wait_for_selector(".ctx-menu:not([hidden]) button")
        page.locator(".ctx-menu:not([hidden]) button", has_text="기준 없이").click()
        page.wait_for_selector(".tkv-wrap .tkv-planhead", timeout=60000)
        r0 = page.evaluate(ROW, ref0)
        check("방식을 정하기 전 — 값이 있는 칸은 겹침(못 고름) · 방식 묶음 없음", bool(r0) and r0["cls"] == "tkv-clash" and r0["off"] and r0["op"] == "" and "1,200" in r0["val"]
              and page.locator(".tkv-ops").count() == 0 and mine() == [], r0)
        page.evaluate(ROW_DO, [ref0, "ops"])
        page.wait_for_selector(".ctx-menu:not([hidden]) button")
        m1 = page.evaluate(MENU)
        check("고르기 창 1 — 「이 칸만」 · 머리글마다 「… 아래 모두」", bool(m1) and m1[0] == "이 칸만" and "머리글 「개발연차」 아래 모두" in m1, m1)
        page.locator(".ctx-menu:not([hidden]) button", has_text="이 칸만").click()
        page.wait_for_function("() => { const m = document.querySelector('.ctx-menu'); return !!m && !m.hidden && [...m.querySelectorAll('button')].some((b) => b.textContent.startsWith('더하기')); }", timeout=60000)
        m2 = page.evaluate(MENU)
        check("고르기 창 2 — 방식 넷", [x.split(" — ")[0] for x in m2] == ["빈 칸에만(기본)", "더하기", "빼기", "덮어쓰기"], m2)
        page.locator(".ctx-menu:not([hidden]) button", has_text="더하기").click()
        page.wait_for_function("(ref) => { const tr = [...document.querySelectorAll('.tkv-plan table.tkv-pairs tbody tr')].find((r) => (r.querySelector('.hlink') || {}).textContent === ref); return !!tr && !!tr.querySelector('.tkv-op'); }",
                               arg=ref0, timeout=60000)
        r1 = page.evaluate(ROW, ref0)
        check("더하기로 저장 — 표지 「더하기」 · 「지금 「1,200」 → 넣을 값 1,700 (= 1,200 + 500)」 · 「확인」 · 처음에는 안 고름", r1["op"] == "더하기" and r1["val"].replace(" ", "").startswith("지금「1,200」→넣을값1,700(=1,200+500)")
              and "확인" in r1["val"] and not r1["on"] and not r1["off"], r1)
        oprules = page.evaluate("() => [...document.querySelectorAll('.tkv-ops .tkv-oprule')].map((li) => li.textContent)")
        saved = mine()
        check("요약 「(확인 1)」 · 「넣는 방식」 묶음 한 줄 · 묶음에 저장됨(그 칸 · add)", "(확인 1)" in page.evaluate(VIEW)["plansum"] and len(oprules) == 1 and oprules[0].startswith("칸") and oprules[0].endswith("→ 더하기✕")
              and len(saved) == 1 and [(o.get("key") is not None, o["op"]) for o in saved[0]["ops"]] == [(True, "add")], (oprules, saved))
        fit = page.evaluate(FIT)
        check("넣는 방식 — 열 안에 들어감", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "13_ops.png"))
        page.locator(".tkv-plan .tkv-bar .btn", has_text="모두 풀기").click()
        page.evaluate(ROW_DO, [ref0, "check"])
        check("확인 줄만 켬 — 「고른 1칸 넣기」", page.evaluate(VIEW)["btn"] == "고른 1칸 넣기")
        undo0 = page.evaluate("() => state.undo")
        page.locator(".tkv-plan .tkv-bar .btn.primary").click()
        page.wait_for_function("(ref) => { const tr = [...document.querySelectorAll('.tkv-plan table.tkv-pairs tbody tr')].find((r) => (r.querySelector('.hlink') || {}).textContent === ref); return !!tr && tr.querySelector('.tkv-val').textContent.includes('1,700」'); }",
                               arg=ref0, timeout=60000)
        got = {i["cell"]: i["text"] for i in requests.get(f"{base}/api/docs/{gdoc}/tables/{CTE_C}/kv", timeout=120).json()["items"]}
        r2 = page.evaluate(ROW, ref0)
        check("넣기 — 값이 있던 칸에 더해 넣음(1,700 · 실행 취소 1개) · 다시 받은 계획은 또 더한 것이고 다시 꺼져 있다(두 번 더해지지 않게)", got.get(sum_cells[0]) == "1,700" and page.evaluate("() => state.undo") == undo0 + 1
              and r2["val"].replace(" ", "").startswith("지금「1,700」→넣을값2,200(=1,700+500)") and not r2["on"], (got.get(sum_cells[0]), r2))
        page.locator(".tkv-ops .tkv-oprule .tkv-x").click()
        page.wait_for_function("(ref) => { const tr = [...document.querySelectorAll('.tkv-plan table.tkv-pairs tbody tr')].find((r) => (r.querySelector('.hlink') || {}).textContent === ref); return !!tr && !tr.querySelector('.tkv-op'); }",
                               arg=ref0, timeout=60000)
        r3 = page.evaluate(ROW, ref0)
        check("「넣는 방식」 의 ✕ — 그 칸은 겹침으로 돌아가고 묶음도 지워진다(규칙도 방식도 없음)", r3["cls"] == "tkv-clash" and r3["off"] and page.locator(".tkv-ops").count() == 0 and mine() == [], (r3, mine()))

        # ---- 11. 계산 칸 다시 계산 — 값 칸을 채운 표의 「계」 줄 · 「계」 열을 수식대로 다시 셈해 넣는다(둘째 작업 · t1339)
        blank = [i for i in requests.get(f"{base}/api/docs/{gdoc}/tables/{RECALC_T}/kv", timeout=120).json()["items"] if not i["calc"] and i["empty"]]
        rok = requests.post(f"{base}/api/docs/{gdoc}/tables/{RECALC_T}/fill/apply", json={"fills": [{"cell": i["cell"], "text": str(10 * (n + 1))} for n, i in enumerate(blank)]}, timeout=120).status_code == 200
        check("다시 계산용 표를 꾸밈(API — 값 칸 12개에 수)", rok and len(blank) == 12, len(blank))
        page.reload()
        page.wait_for_function("(g) => state.id === g && document.querySelector('#doc .sheet .para') != null", arg=gdoc, timeout=240000)
        page.wait_for_timeout(1500)
        page.evaluate("(t) => tblKvView(t)", RECALC_T)
        page.wait_for_function("(t) => document.getElementById('headsDlgTitle').textContent === `키-값 · ${t}` && document.querySelector('.tkv-recalc .tkv-recalc-get')", arg=RECALC_T, timeout=60000)
        rc = page.evaluate(RC)
        check("「계산 칸 다시 계산」 묶음 — 처음에는 단추만(저절로 안 읽음)", bool(rc) and rc["head"] == "계산 칸 다시 계산" and rc["get"] == "다시 계산할 칸 보기" and rc["rows"] == [] and rc["sum"] == "", rc)
        page.locator(".tkv-recalc .tkv-recalc-get").click()
        page.wait_for_function("() => { const e = document.querySelector('.tkv-recalc .tkv-recalcsum'); return !!e && e.textContent.startsWith('다시 계산할 칸 8'); }", timeout=60000)
        rc = page.evaluate(RC)
        by = {r["ref"]: r for r in rc["rows"]}
        check("계획 — 8줄 · 「지금 (빈 칸) → 계산한 값 30 (=SUM(D2:E2))」 · 모두 고른 채 · 「고른 8칸 넣기」", len(rc["rows"]) == 8 and by["F2"]["val"].startswith("지금 (빈 칸) → 계산한 값 30 (=SUM(D2:E2))")
              and all(r["on"] and not r["off"] for r in rc["rows"]) and rc["btn"] == "고른 8칸 넣기" and "계산한 값 480" in by["F6"]["val"] and rc["sum"] == "다시 계산할 칸 8 · 같음 0 · 셈할 칸이 빔 0", rc)
        page.evaluate(RC_CLICK, "F2")
        rc = page.evaluate(RC)
        by = {r["ref"]: r for r in rc["rows"]}
        check("줄 합(F2)을 끄면 그에 기대는 합의 합(F6)도 꺼지고 못 고름 · 「고른 6칸 넣기」", not by["F2"]["on"] and not by["F6"]["on"] and by["F6"]["off"] and rc["btn"] == "고른 6칸 넣기", rc)
        page.evaluate(RC_CLICK, "F2")
        check("다시 켜면 「고른 8칸 넣기」", page.evaluate(RC)["btn"] == "고른 8칸 넣기")
        fit = page.evaluate(FIT)
        check("계산 칸 다시 계산 — 열 안에 들어감", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "14_recalc.png"))
        undo0 = page.evaluate("() => state.undo")
        page.locator(".tkv-recalc .tkv-recalcbar .btn.primary").click()
        page.wait_for_function("() => { const e = document.querySelector('.tkv-recalc .tkv-recalcsum'); return !!e && e.textContent.startsWith('다시 계산할 칸 0 · 같음 8'); }", timeout=60000)
        got = {i["ref"]: i["text"] for i in requests.get(f"{base}/api/docs/{gdoc}/tables/{RECALC_T}/kv", timeout=120).json()["items"]}
        check("넣기 — 줄 합 · 열 합 · 합의 합이 한 번의 편집으로(실행 취소 1개) · 넣은 뒤 저절로 다시 읽음", (got.get("F2"), got.get("D6"), got.get("F6")) == ("30", "220", "480")
              and page.evaluate("() => state.undo") == undo0 + 1 and page.evaluate(RC)["rows"] == [], {k: got.get(k) for k in ("F2", "D6", "F6")})
        page.screenshot(path=str(OUT / "15_recalc_after.png"))
        # 기대는 칸을 모두 따진다 — 줄 합 F2(999 · 계산은 30)와 열 합 D6(1189 · 계산은 220)을 틀리게, 합의 합 F6 은 비운다: F6 은 그 지금 값으로 셈한 것이라 「확인」, F2 를 같이 고치면 꺼진다
        rk = {i["ref"]: i["cell"] for i in requests.get(f"{base}/api/docs/{gdoc}/tables/{RECALC_T}/kv", timeout=120).json()["items"]}
        rcells = {c["id"]: c for c in find(requests.get(f"{base}/api/docs/{gdoc}", timeout=120).json()["blocks"], RECALC_T)["cells"]}
        sok = True
        for rf, tx in (("F2", "999"), ("D6", "1189"), ("F6", "")):
            pid = next(b["id"] for b in rcells[rk[rf]]["blocks"] if b["type"] == "paragraph")
            sok = sok and requests.patch(f"{base}/api/docs/{gdoc}/blocks/{pid}", json={"text": tx}, timeout=120).status_code == 200
        check("기대는 칸 검사용으로 줄 합 · 열 합을 틀리게 고침(API)", sok)
        page.reload()
        page.wait_for_function("(g) => state.id === g && document.querySelector('#doc .sheet .para') != null", arg=gdoc, timeout=240000)
        page.wait_for_timeout(1500)
        page.evaluate("(t) => tblKvView(t)", RECALC_T)
        page.wait_for_function("(t) => document.getElementById('headsDlgTitle').textContent === `키-값 · ${t}` && document.querySelector('.tkv-recalc .tkv-recalc-get')", arg=RECALC_T, timeout=60000)
        page.locator(".tkv-recalc .tkv-recalc-get").click()
        page.wait_for_function("() => { const e = document.querySelector('.tkv-recalc .tkv-recalcsum'); return !!e && e.textContent.startsWith('다시 계산할 칸 3(확인 3)'); }", timeout=60000)
        rc = page.evaluate(RC)
        by = {r["ref"]: r for r in rc["rows"]}
        check("지금 값으로 셈한 합의 합 — 「계산한 값 1,449」 · 「확인」 · 「기대는 칸 F2 의 지금 값(999)으로 셈했습니다」 · 셋 다 처음에는 안 고름(「고른 0칸 넣기」)", sorted(by) == ["D6", "F2", "F6"]
              and "계산한 값 1,449" in by["F6"]["val"] and "확인" in by["F6"]["val"] and "기대는 칸 F2 의 지금 값(999)으로 셈했습니다" in by["F6"]["val"] and not any(r["on"] for r in rc["rows"]) and rc["btn"] == "고른 0칸 넣기", rc)
        page.evaluate(RC_CLICK, "F6")
        check("합의 합만 켬(줄 합은 그대로 둠) — 「고른 1칸 넣기」", page.evaluate(RC)["btn"] == "고른 1칸 넣기")
        page.evaluate(RC_CLICK, "F2")
        rc = page.evaluate(RC)
        by = {r["ref"]: r for r in rc["rows"]}
        check("줄 합(F2)을 같이 고치면 — 그 옛 값으로 셈한 합의 합은 꺼지고 못 고름 · 「고른 1칸 넣기」", by["F2"]["on"] and not by["F6"]["on"] and by["F6"]["off"] and rc["btn"] == "고른 1칸 넣기"
              and "F2 를 고친 뒤 다시 계산합니다" in page.evaluate("() => [...document.querySelectorAll('.tkv-recalc table.tkv-recalcs tbody tr')].find((r) => r.querySelector('.hlink').textContent === 'F6').querySelector('input').title"), rc)
        page.screenshot(path=str(OUT / "16_recalc_stale.png"))
        page.locator(".tkv-recalc .tkv-recalcbar .btn.primary").click()
        page.wait_for_function("() => { const e = document.querySelector('.tkv-recalc .tkv-recalcsum'); return !!e && e.textContent.includes('두 수식이 다름 1'); }", timeout=60000)
        got = {i["ref"]: i["text"] for i in requests.get(f"{base}/api/docs/{gdoc}/tables/{RECALC_T}/kv", timeout=120).json()["items"]}
        check("넣기 — 줄 합만 고쳐지고(30) 합의 합은 빈 채 · 다시 읽으면 두 수식이 다름(열 합이 아직 틀림)", (got.get("F2"), got.get("F6"), got.get("D6")) == ("30", "", "1189"), {k: got.get(k) for k in ("F2", "F6", "D6")})
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

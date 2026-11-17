"""캡션 템플릿 「CN」(spec_hwpx_웹편집 ② §8-10 — app/static/caption_tpl.js · app/caption_tpl.py) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

연구개발계획서 양식의 본문 표 다섯에 개체 캡션(hp:caption)을 붙인 문서를 올리고 1·2단계(LLM 없이)를 끝점으로 돌린다.
그 문서의 캡션 줄: 표 위의 화살괄호 줄 셋(문단으로 친 캡션) + 붙인 「< 첫째 표 >」·「<　둘째 표　＞」·「 <셋째 표> 」(개체 캡션 — 같은 템플릿 「< … >」) + 「표 1-1 …」·「표 1-2  …」(템플릿 「표 N-N」).
작성요령(TEMP) 표 안의 「<표 1> …」 넷은 캡션 줄이 아니다.

 1. 문서 왼쪽 여백에 캡션 줄마다 보라 표시 「C1」… — 서식이 대표와 다른 줄은 「C1 ≠」 · TEMP 안의 「<표 N>」 줄에는 없다.
 2. 「템플릿 관계」 열 끝에 「캡션 템플릿 n」 절 — 템플릿 줄 [C1] 「< … >」 · 표 캡션 · 위 n · 「서식 n가지」.
 3. 펴면 「서식 n가지 · 대표 … · 대표에 맞추기(m줄)」 → 「▸ 서식 목록」: 대표 카드 + 「다른 서식 n」 카드(대표와 다른 값 「이름: 지금 … → 대표 …」).
 4. 「대표로」 → 대표가 그 줄로(문서는 안 바뀜 · 실행 취소 1) · 카드 차례가 바뀐다.
 5. 「이 줄들만 맞추기」 → 그 서식의 줄만 대표 모양으로(문서의 글이 바뀐다: 「<　둘째 표　＞」 → 「< 둘째 표 >」).
 6. 「대표에 맞추기(m줄)」 → 서식 1가지 — 모두 같음 · 여백 표시의 「≠」 가 없어진다 · 「실행 취소」 로 되돌아온다.
 7. 여백의 「C1」 을 누르면 「템플릿 관계」 의 그 템플릿이 펴지고 그 줄이 든 서식 카드에 표시.
 8. 개요 템플릿 쪽(트리의 「TN」 줄 · 서식 줄 .olm)은 그대로 — 다시 그려도 캡션 절이 남는다.
 9. docx 문서에는 표시도 절도 없다.

    python -X utf8 tools/smoke_caption_tpl_ui.py <출력 폴더> [--port 18497]
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
from lxml import etree
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.hwpx_doc import CAPTION, RUN, SUBLIST, TBL, HwpxDoc, P, T, _p  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18497)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []
SAMPLES = ROOT / "samples"
MADE = ["< 첫째 표 >", "<　둘째 표　＞", " <셋째 표> ", "표 1-1 넷째 표", "표 1-2  다섯째 표"]
COL = "#headsDlgBody"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:700] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def wait_server(timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if requests.get(base + "/api/headings/llm", timeout=2).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.4)
    raise SystemExit("서버가 안 뜸")


def with_captions(src):
    """양식의 본문 표 다섯에 위쪽 개체 캡션을 붙인 문서(tests/test_caption_tpl.py 의 _with_captions 와 같은 것)."""
    doc = HwpxDoc(src)
    doc.blocks()
    a, b = doc._ids["p6387"], doc._ids["p6361"]
    tables = [o for sec in doc._sections for p in sec.iterchildren(P) for r in p.iterchildren(RUN) for o in r.iterchildren(TBL)]
    tables = [t for t in tables if len(list(t.iter(TBL))) == 1][2:7]
    for i, (t, text) in enumerate(zip(tables, MADE)):
        like = b if i == 4 else a
        cap = t.makeelement(CAPTION, {"side": "TOP", "fullSz": "0", "width": "8504", "gap": "850", "lastWidth": "47624"})
        sub = etree.SubElement(cap, SUBLIST, {"id": "", "textDirection": "HORIZONTAL", "lineWrap": "BREAK", "vertAlign": "TOP", "linkListIDRef": "0",
                                              "linkListNextIDRef": "0", "textWidth": "0", "textHeight": "0", "hasTextRef": "0", "hasNumRef": "0"})
        para = etree.SubElement(sub, P, {"id": "0", "paraPrIDRef": like.get("paraPrIDRef"), "styleIDRef": like.get("styleIDRef", "0"), "pageBreak": "0", "columnBreak": "0", "merged": "0"})
        etree.SubElement(etree.SubElement(para, RUN, {"charPrIDRef": next(like.iterchildren(RUN)).get("charPrIDRef")}), T).text = text
        t.find(_p("outMargin")).addnext(cap)
        doc._touch(t)
    return doc.save()


def upload(name, data):
    r = requests.post(base + "/api/docs", files={"file": (name, data, "application/octet-stream")}, timeout=120)
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def run_stage(doc, stage):
    r = requests.post(f"{base}/api/docs/{doc}/headings", json={"stage": stage, "llm": False}, timeout=30)
    assert r.status_code == 202, r.text
    end = time.time() + 300
    while time.time() < end:
        v = requests.get(f"{base}/api/docs/{doc}/headings", timeout=30).json()
        if not v.get("job") or v["job"].get("status") != "running":
            return v
        time.sleep(0.4)
    raise SystemExit("단계가 안 끝남")


def caps(doc):
    r = requests.get(f"{base}/api/docs/{doc}/captions", timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def text_of(doc, pid):  # 서버의 지금 글
    d = requests.get(f"{base}/api/docs/{doc}", timeout=120).json()

    def walk(blocks):
        for b in blocks:
            if b.get("id") == pid:
                return b.get("text")
            for c in b.get("cells") or []:
                t = walk(c.get("blocks") or [])
                if t is not None:
                    return t
        return None
    return walk(d["blocks"])


MARKS = """() => [...document.querySelectorAll('#doc .sheet > .tpl-mark.cap')].map((e) => e.textContent.trim())"""
SEC = """(root) => { const sec = document.querySelector(root + ' .capt-sec'); if (!sec || sec.hidden) return null;
  return { head: sec.querySelector('h3').firstChild.textContent.trim(), rows: [...sec.querySelectorAll('li.capt-node')].map((li) => ({ id: li.dataset.cap, no: li.querySelector('.tplno').textContent,
    name: li.querySelector('.trel-name').textContent, meta: li.querySelector('.trel-meta').textContent, chip: (li.querySelector('.capt-chip') || {}).textContent || '', open: li.querySelector('.htog').getAttribute('aria-expanded') })) }; }"""
ROW = """([root, cid]) => { const row = document.querySelector(`${root} .capt-row[data-cap="${cid}"]`); if (!row || row.hidden) return null;
  return { sum: row.querySelector('.olm-sum').textContent, rep: (row.querySelector('.olm-rep') || {}).textContent || '', btns: [...row.querySelectorAll(':scope > button')].map((b) => b.textContent),
    cards: [...row.querySelectorAll('li.capt-g')].map((li) => ({ key: li.dataset.key, rep: li.classList.contains('rep'), sel: li.classList.contains('capt-sel'), badge: (li.querySelector('.olm-badge, .olm-no') || {}).textContent || '',
      n: li.querySelector('.olm-n').textContent, diff: (li.querySelector('.olm-diff') || {}).textContent || '', btns: [...li.querySelectorAll('button.btn')].map((b) => b.textContent) })) }; }"""


def main():
    wait_server()
    doc = upload("캡션_붙인_양식.hwpx", with_captions((SAMPLES / "연구개발계획서_양식.hwpx").read_bytes()))
    run_stage(doc, 1)
    run_stage(doc, 2)
    docx = upload("기술수요조사서.docx", (SAMPLES / "기술수요조사서.docx").read_bytes())
    c0 = caps(doc)
    by = {t["name"]: t for t in c0["templates"]}
    for t in c0["templates"]:
        print(f"INFO {t['id']} 「{t['name']}」 {t['kindName']} ×{t['total']} · 자리 {t['sides']} · 개체 {t['struct']} · 글 {t['text']} · 서식 {[('대표 ' if g['rep'] else '') + str(g['count']) for g in t['groups']]}", flush=True)
    W, L = by["< … >"], by["표 N-N"]
    ids = {text_of(doc, p): p for p, x in c0["lines"].items() if x["tpl"] == W["id"]}
    first, second, third = (ids[x] for x in MADE[:3])
    check("끝점 — 템플릿 둘(「< … >」 표 캡션 6줄 · 「표 N-N」 2줄) · TEMP 안의 「<표 N>」 줄은 없음",
          W["total"] == 6 and W["struct"] == 3 and W["text"] == 3 and L["total"] == 2 and "<표 N>" not in by and not {"p6361", "p6387"} & set(c0["lines"]), [W["total"], L["total"], list(by)])

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1700, "height": 950}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/#w={doc}")
        page.wait_for_selector("#doc .para[data-id=p970]", timeout=60000)
        page.wait_for_function("() => document.querySelectorAll('.tpl-mark').length > 20", timeout=30000)

        # 1. 여백 표시
        page.wait_for_function("() => document.querySelectorAll('#doc .sheet > .tpl-mark.cap').length >= 8", timeout=30000)
        marks = page.evaluate(MARKS)
        want_off = sum(g["count"] for t in (W, L) for g in t["groups"] if not g["rep"])
        check("1. 여백에 캡션 줄마다 보라 표시 「CN」 — 8줄 · 대표와 서식이 다른 줄은 「≠」", len(marks) == 8 and sum(1 for m in marks if m.endswith("≠")) == want_off
              and {m.split()[0] for m in marks} == {W["id"], L["id"]}, marks)
        temp = page.evaluate("""() => { const p = document.querySelector('#doc .para[data-id="p6361"]'); const sheet = p.closest('.sheet'), top = p.getBoundingClientRect().top;
          return [...sheet.querySelectorAll(':scope > .tpl-mark')].filter((e) => Math.abs(e.getBoundingClientRect().top - top) < 6).map((e) => e.className + '|' + e.textContent.trim()); }""")
        check("   TEMP 안의 「<표 1>」 줄에는 캡션 표시가 없다", not any("cap" in x.split("|")[0].split() for x in temp), temp)
        page.locator(f'#doc .para[data-id="{second}"]').scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "1_marks.png"))

        # 2. 「템플릿 관계」 의 절
        page.evaluate("() => tplRelOpen()")
        page.wait_for_selector(f"{COL} .capt-sec li.capt-node", timeout=30000)
        sec = page.evaluate(SEC, COL)
        rows = {r["id"]: r for r in sec["rows"]}
        check("2. 「캡션 템플릿 2」 절 — [C] 「< … >」 · 표 캡션 · 위 6 · 「서식 n가지」", sec["head"] == "캡션 템플릿 2" and rows[W["id"]]["no"] == W["id"] and rows[W["id"]]["name"] == "「< … >」"
              and rows[W["id"]]["meta"] == "표 캡션 · 위 6" and rows[W["id"]]["chip"] == f"서식 {len(W['groups'])}가지" and rows[L["id"]]["meta"] == "표 캡션 · 위 2" and rows[W["id"]]["open"] == "false", sec)

        # 3. 펴기 · 서식 목록
        node = f'{COL} li.capt-node[data-cap="{W["id"]}"]'
        page.locator(f"{node} > .trel-row > .tplno").click()
        page.wait_for_selector(f'{COL} .capt-row[data-cap="{W["id"]}"]', timeout=10000)
        rv = page.evaluate(ROW, [COL, W["id"]])
        check("3. 서식 줄 — 「서식 n가지」 · 대표 · 「▸ 서식 목록」 · 「대표에 맞추기(m줄)」", rv["sum"] == f"서식 {len(W['groups'])}가지" and "대표" in rv["rep"]
              and rv["btns"] == ["▸ 서식 목록", f"대표에 맞추기({W['others']}줄)"] and not rv["cards"], rv)
        page.locator(f'{COL} .capt-row[data-cap="{W["id"]}"] > button', has_text="서식 목록").click()
        page.wait_for_selector(f'{COL} .capt-row[data-cap="{W["id"]}"] li.capt-g', timeout=10000)
        rv = page.evaluate(ROW, [COL, W["id"]])
        cards = rv["cards"]
        sec_card = next(c for c in cards if c["key"] == next(g["key"] for g in W["groups"] if second in g["paras"]))
        check("   서식 목록 — 대표 카드 + 「다른 서식 n」 · 대표와 다른 값 「이름: 지금 … → 대표 …」 · 「대표로」·「이 줄들만 맞추기」",
              cards[0]["rep"] and cards[0]["badge"] == "대표" and [c["badge"] for c in cards[1:]] == [f"다른 서식 {i}" for i in range(1, len(cards))]
              and all("지금 " in c["diff"] and "→ 대표 " in c["diff"] for c in cards[1:]) and all(c["btns"][:1] == ["대표로"] and "이 줄들만 맞추기" in c["btns"] for c in cards[1:])
              and len(cards) == len(W["groups"]), cards)
        page.screenshot(path=str(OUT / "3_list.png"))

        # 4. 대표로 — 먼저 「 <셋째 표> 」 를, 이어서 「< 첫째 표 >」 를 대표로(문서는 안 바뀜)
        before = requests.get(f"{base}/api/docs/{doc}/download", timeout=120).content
        fk, tk = (next(g["key"] for g in W["groups"] if x in g["paras"]) for x in (first, third))
        is_rep = "([root, cid, k]) => { const li = document.querySelector(`${root} .capt-row[data-cap=\"${cid}\"] li.capt-g[data-key=\"${k}\"]`); return !!li && li.classList.contains('rep') && !state.busy; }"
        page.locator(f'{COL} .capt-row[data-cap="{W["id"]}"] li.capt-g[data-key="{tk}"] button', has_text="대표로").click()
        page.wait_for_function(is_rep, arg=[COL, W["id"], tk], timeout=20000)
        c1 = next(t for t in caps(doc)["templates"] if t["id"] == W["id"])
        rv = page.evaluate(ROW, [COL, W["id"]])
        check("4. 「대표로」 — 대표가 그 줄로 · 문서는 안 바뀜 · 실행 취소 1 · 서식 줄의 대표 글", c1["rep"] == tk and c1["repSet"] and requests.get(f"{base}/api/docs/{doc}/download", timeout=120).content == before
              and page.evaluate("() => state.undo") == 1 and rv["rep"].startswith("대표 ") and "셋째 표" in rv["rep"] and rv["cards"][0]["key"] == tk, [c1["rep"], c1["repSet"], rv["rep"]])
        page.locator(f'{COL} .capt-row[data-cap="{W["id"]}"] li.capt-g[data-key="{fk}"] button', has_text="대표로").click()
        page.wait_for_function(is_rep, arg=[COL, W["id"], fk], timeout=20000)
        c1 = next(t for t in caps(doc)["templates"] if t["id"] == W["id"])
        rv = page.evaluate(ROW, [COL, W["id"]])
        check("   다시 「< 첫째 표 >」 를 대표로", c1["rep"] == fk and c1["repSet"] and "< 첫째 표 >" in rv["rep"], [c1["rep"], rv["rep"]])

        # 5. 이 줄들만 맞추기 — 「<　둘째 표　＞」 의 서식만
        g2 = next(g for g in c1["groups"] if second in g["paras"])
        page.locator(f'{COL} .capt-row[data-cap="{W["id"]}"] li.capt-g[data-key="{g2["key"]}"] button', has_text="이 줄들만 맞추기").click()
        page.wait_for_function("(id) => (document.querySelector(`#doc .para[data-id=\"${id}\"]`) || {}).textContent === '< 둘째 표 >'", arg=second, timeout=30000)
        c2 = next(t for t in caps(doc)["templates"] if t["id"] == W["id"])
        check("5. 「이 줄들만 맞추기」 — 그 서식의 줄만 대표 모양으로(전각 빈칸·전각 괄호 → 「< 둘째 표 >」 · 다른 서식은 그대로)", text_of(doc, second) == "< 둘째 표 >" and text_of(doc, third) == MADE[2]
              and c2["others"] == c1["others"] - g2["count"], [text_of(doc, second), c2["others"], c1["others"]])

        # 6. 대표에 맞추기 — 모두
        page.locator(f'{COL} .capt-row[data-cap="{W["id"]}"] > button', has_text="대표에 맞추기").click()
        page.wait_for_function("([root, cid]) => { const s = document.querySelector(`${root} .capt-row[data-cap=\"${cid}\"] .olm-sum`); return !!s && s.textContent.startsWith('서식 1가지'); }", arg=[COL, W["id"]], timeout=30000)
        c3 = next(t for t in caps(doc)["templates"] if t["id"] == W["id"])
        marks = page.evaluate(MARKS)
        check("6. 「대표에 맞추기」 — 서식 1가지 · 글이 대표 꼴로 · 여백의 「≠」 가 그 템플릿에서 없어짐", c3["others"] == 0 and len(c3["groups"]) == 1 and text_of(doc, third) == "< 셋째 표 >"
              and text_of(doc, ids["<기술개발 핵심어>"]) == "< 기술개발 핵심어 >" and not any(m == f"{W['id']} ≠" for m in marks), [c3["others"], text_of(doc, third), text_of(doc, ids["<기술개발 핵심어>"]), marks])
        page.screenshot(path=str(OUT / "6_matched.png"))
        for _ in range(12):  # 실행 취소 — 대표 정하기 둘 · 맞추기 둘
            left = page.evaluate("() => state.undo")
            if not left:
                break
            page.evaluate("() => document.getElementById('undoBtn').click()")
            page.wait_for_function("(n) => state.undo < n && !state.busy", arg=left, timeout=30000)
        page.wait_for_timeout(2200)  # 캡션 자료는 문서 차례가 바뀐 뒤 잠시 있다가 다시 읽는다
        c4 = next(t for t in caps(doc)["templates"] if t["id"] == W["id"])
        check("   「실행 취소」 — 글·서식·대표가 처음대로", text_of(doc, second) == MADE[1] and c4["others"] == W["others"] and not c4["repSet"] and c4["id"] == W["id"]
              and requests.get(f"{base}/api/docs/{doc}/download", timeout=120).content == before, [text_of(doc, second), c4["others"], c4["repSet"]])
        page.wait_for_function("(n) => [...document.querySelectorAll('#doc .sheet > .tpl-mark.cap')].filter((e) => e.textContent.trim().endsWith('≠')).length === n", arg=want_off, timeout=20000)

        # 7. 여백의 표시를 누르면 그 템플릿·그 서식
        page.evaluate("() => { headsColClose(); }")
        page.wait_for_timeout(300)
        page.evaluate("""(id) => { const p = document.querySelector(`#doc .para[data-id="${id}"]`); p.scrollIntoView({ block: 'center' }); }""", second)
        page.wait_for_timeout(500)
        page.evaluate("""(id) => { const p = document.querySelector(`#doc .para[data-id="${id}"]`), sheet = p.closest('.sheet'), top = p.getBoundingClientRect().top;
          const m = [...sheet.querySelectorAll(':scope > .tpl-mark.cap')].sort((a, b) => Math.abs(a.getBoundingClientRect().top - top) - Math.abs(b.getBoundingClientRect().top - top))[0]; m.click(); }""", second)
        page.wait_for_selector(f'{COL} .capt-row[data-cap="{W["id"]}"] li.capt-g.capt-sel', timeout=30000)
        rv = page.evaluate(ROW, [COL, W["id"]])
        sel = [c for c in rv["cards"] if c["sel"]]
        check("7. 여백의 「C」 표시를 누르면 「템플릿 관계」 의 그 템플릿이 펴지고 그 줄이 든 서식 카드에 표시", len(sel) == 1 and sel[0]["key"] == next(g["key"] for g in c4["groups"] if second in g["paras"]), rv["cards"])

        # 8. 개요 템플릿 쪽은 그대로 — 다시 그려도 캡션 절이 남는다
        keep = page.evaluate("""(root) => { const n0 = document.querySelectorAll(root + ' li.trel-node:not(.capt-node)').length; olmRedraw(); tplTreeRefresh(null, true);
          return { tpl: n0, tpl2: document.querySelectorAll(root + ' li.trel-node:not(.capt-node)').length, caps: document.querySelectorAll(root + ' .capt-sec li.capt-node').length, secs: document.querySelectorAll(root + ' .capt-sec').length }; }""", COL)
        check("8. 개요 템플릿 트리를 다시 그려도 캡션 절이 하나 남고 템플릿 줄 수가 같다", keep["tpl"] > 0 and keep["tpl"] == keep["tpl2"] and keep["caps"] == 2 and keep["secs"] == 1, keep)

        # 9. docx — 표시도 절도 없다
        page.evaluate("(id) => { openWork(id); }", docx)
        page.wait_for_function("(id) => state.id === id && !document.getElementById('fileInfo').hidden && !!document.querySelector('#doc .para')", arg=docx, timeout=60000)
        page.wait_for_timeout(800)
        check("9. docx 문서에는 캡션 표시가 없다", page.evaluate("() => document.querySelectorAll('.tpl-mark.cap').length === 0 && captMarkCount() === 0"))
        b.close()
    check("콘솔 오류 없음", not errors, errors[:5])


try:
    main()
finally:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'OK' if not fails else 'FAIL'} — 실패 {len(fails)}" + (f": {fails}" if fails else ""))
sys.exit(1 if fails else 0)

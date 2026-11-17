"""문서에서 고친 곳 보기 — 깃처럼(spec_작업 ② §8 「화면」 「문서에서 — 고친 곳 보기」 — app/static/doc_diff.js · doc_diff.css) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜.

2026-11-17 사용자 「웹원문에서 어떤걸 고쳤는지 확인하는 기능을 넣어줘. 지금은 문단으로 표기 되는데. git 처럼 볼 수 있게」.
기술수요조사서를 올리고 끝점으로 고친다: A 모양(왼쪽 여백 7mm) · B 글 넣기 · C 글 지우기 · D 글 바꾸기 + 두 곳 고침 · E 나누기(새 문단).

 1. 켜짐이 기본 — 「±」 단추 눌림 · 고친 문단의 주황 바탕이 걷히고(왼쪽 띠만) 새 문단은 초록 띠.
 2. 넣은 글자에 초록 표시(넣은 글 그대로) · 지우기만 한 자리는 앞뒤 글자에 빨간 물결 · 문단 DOM 은 그대로(글이 서버 글과 같다).
 3. 오른쪽 여백 꼬리표 — 「M 글」 · 「M 앞 여백 · 2번째 줄」(서버가 견준 줄의 자리 「원본 … → 지금 7mm」) · 「A 새 문단」 · 제 문단 높이 · 쪽 안.
 4. 꼬리표에 올리면 「어떻게」(− … + … · 값 → 값)가 펼쳐진다(쪽 밖으로 안 나감) · 누르면 「고친 문단」 목록의 그 항목.
 5. 글을 치면 친 글이 바로 초록(서버 반영 전).
 6. 배율을 바꾸면 꼬리표가 제 문단 높이로 다시 · 글자 표시는 남는다.
 7. 끄면 표시가 모두 걷히고 전처럼 주황 바탕 · 다시 열어도 꺼짐(기억) · 켜면 다시.
 8. 문단을 되돌리면 그 문단의 표시가 사라진다 · 다른 문서를 열면 표시가 없다 · 콘솔 오류 없음.

    python -X utf8 tools/smoke_doc_diff_ui.py <출력 폴더> [--port 18491]
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
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18491)
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
SAMPLE = ROOT / "samples" / "기술수요조사서.hwpx"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:900] if detail != "" and not ok else ""), flush=True)
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


def upload(path=None):
    path = path or SAMPLE
    r = requests.post(base + "/api/docs", files={"file": (path.name, path.read_bytes(), "application/octet-stream")}, timeout=120)
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def paras(blocks):
    out = []

    def walk(bs):
        for b in bs or ():
            if b.get("type") == "paragraph" and b.get("id"):
                out.append(b)
            for c in b.get("cells") or ():
                walk(c.get("blocks"))
    walk(blocks)
    return out


# 문서의 지금 모습 — 글자 표시(넣은 글 · 지운 자리)는 **범위의 글**로, 꼬리표는 문단 id 와 글로
VIEW = """() => { const hi = (n) => { const h = CSS.highlights.get(n); return h ? [...h].map((r) => ({ text: r.toString(), para: (r.startContainer.parentElement.closest('.para') || {dataset: {}}).dataset.id })) : null; };
  const tags = [...document.querySelectorAll('.sheet > .dd-tag')].map((t) => { const tr = t.getBoundingClientRect(), sr = t.parentElement.getBoundingClientRect(), p = document.querySelector('.para[data-id="' + t.dataset.para + '"]');
    const pr = p ? p.getBoundingClientRect() : null, pad = p ? parseFloat(getComputedStyle(p).paddingTop) || 0 : 0, z = t.parentElement.offsetWidth ? sr.width / t.parentElement.offsetWidth : 1;
    return { para: t.dataset.para, cls: t.className, k: t.querySelector('.dd-k').textContent, s: t.querySelector('.dd-s').textContent, l: t.querySelector('.dd-l').textContent, title: t.title, tag: t.tagName,
      dy: pr ? Math.round(tr.top - (pr.top + pad * z)) : null, inside: tr.left >= sr.left - 1 && tr.right <= sr.right + 1 }; });
  const bg = (id) => { const p = document.querySelector('.para[data-id="' + id + '"]'); if (!p) return null; const c = getComputedStyle(p); return { bg: c.backgroundColor, shadow: c.boxShadow, dd: p.classList.contains('dd'), a: p.classList.contains('dd-A'), edited: p.classList.contains('edited') }; };
  return { on: DD.on, pressed: document.getElementById('ddBtn').getAttribute('aria-pressed'), navShown: !document.getElementById('editNav').hidden, ins: hi('nfm-dd-ins'), del: hi('nfm-dd-del'), tags, marks: DD.marks.size,
    dd: document.querySelectorAll('#doc .para.dd').length, look: Object.fromEntries(IDS.map((id) => [id, bg(id)])) }; }"""


def view(page, ids):
    return page.evaluate(VIEW.replace("IDS", str(list(ids))))


def tag_of(v, pid):
    return next((t for t in v["tags"] if t["para"] == pid), None)


def main():
    wait_server()
    doc = upload()
    d = requests.get(f"{base}/api/docs/{doc}", timeout=60).json()
    ps = [p for p in paras(d["blocks"]) if len((p.get("text") or "").strip()) >= 8 and " " not in p["text"]]
    assert len(ps) >= 5, len(ps)
    step = max(1, len(ps) // 5)
    A, B, C, D, E = (ps[i * step] for i in range(5))
    r = requests.post(f"{base}/api/docs/{doc}/format/para", json={"ids": [A["id"]], "changes": {"indentLeftMm": 7}}, timeout=60)
    assert r.status_code == 200, r.text
    tb = B["text"]
    assert requests.patch(f"{base}/api/docs/{doc}/blocks/{B['id']}", json={"text": tb[:3] + "★넣은글" + tb[3:]}, timeout=60).json()["edited"]
    tc = C["text"]
    assert requests.patch(f"{base}/api/docs/{doc}/blocks/{C['id']}", json={"text": tc[:2] + tc[4:]}, timeout=60).json()["edited"]  # 3·4번째 글자를 지움
    td = D["text"]
    assert requests.patch(f"{base}/api/docs/{doc}/blocks/{D['id']}", json={"text": "가" + td[1:-1] + "나다"}, timeout=60).json()["edited"]  # 첫 글자 바꿈 + 끝 글자 바꿈·넣음 — 두 곳
    r = requests.post(f"{base}/api/docs/{doc}/split", json={"id": E["id"], "offset": 4}, timeout=60)
    assert r.status_code == 200, r.text
    kinds = r.json()["kinds"]
    N = next(i for i, k in kinds.items() if k == "new")
    ids = [A["id"], B["id"], C["id"], D["id"], E["id"], N]
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctxt = b.new_context(viewport={"width": 1600, "height": 950}, device_scale_factor=1)
        page = ctxt.new_page()
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda x: x.accept())
        page.goto(f"{base}/#w={doc}")
        page.wait_for_selector(f'#doc .para[data-id="{A["id"]}"]', timeout=60000)
        page.evaluate("() => { document.getElementById('scroller').scrollTop = 0; }")
        # 문서가 짧아(2쪽) 창을 길게 — 고친 문단 여섯이 모두 창 가까이에 들게
        page.set_viewport_size({"width": 1600, "height": 2400})
        page.wait_for_function("() => typeof DD === 'object' && DD.marks.size >= 6 && document.querySelectorAll('.sheet > .dd-tag').length >= 4", timeout=20000)
        page.wait_for_function("(id) => { const t = [...document.querySelectorAll('.sheet > .dd-tag')]; return t.some((x) => /앞 여백|2번째 줄/.test(x.textContent)); }", arg=A["id"], timeout=20000)
        v = view(page, ids)
        page.screenshot(path=str(OUT / "01_on.png"))

        # ---- 1
        check("켜짐이 기본 — 「±」 눌림 · ↑↓ 옆에 보임", v["on"] and v["pressed"] == "true" and v["navShown"], (v["on"], v["pressed"], v["navShown"]))
        lk = v["look"]
        check("고친 문단(M) — 주황 바탕이 걷히고 왼쪽 띠만", all(lk[i]["dd"] and lk[i]["edited"] and lk[i]["bg"] == "rgba(0, 0, 0, 0)" and "inset" in lk[i]["shadow"] for i in ids[:5]), {i: lk[i] for i in ids[:5]})
        check("새 문단(A) — 초록 띠 · 옅은 초록 바탕", lk[N]["a"] and lk[N]["bg"] == "rgba(21, 128, 61, 0.08)" and "rgb(21, 128, 61)" in lk[N]["shadow"], lk[N])

        # ---- 2
        ins = {x["para"]: x["text"] for x in v["ins"] or []}
        check("넣은 글에 초록 표시 — B 의 넣은 글 그대로", ins.get(B["id"]) == "★넣은글", v["ins"])
        dl = [x for x in v["del"] or [] if x["para"] == C["id"]]
        check("지우기만 한 자리 — C 의 앞뒤 한 글자씩에 빨간 물결", len(dl) == 1 and dl[0]["text"] == tc[1] + tc[4], (v["del"], tc[:6]))
        dins = [x["text"] for x in v["ins"] or [] if x["para"] == D["id"]]
        check("두 곳을 고친 문단 — 넣은 글 표시 둘(앞 「가」 · 끝 「나다」)", dins == ["가", "나다"], dins)
        same = page.evaluate("(ids) => ids.every((id) => readText(document.querySelector('.para[data-id=\"' + id + '\"]')) === state.texts[id])", ids)
        check("문단 DOM 은 그대로 — 화면 글 = 서버 글", same)

        # ---- 3
        ta, tb_, tn = tag_of(v, A["id"]), tag_of(v, B["id"]), tag_of(v, N)
        check("꼬리표는 누르는 단추 · 쪽 안 · 제 문단 높이", v["tags"] and all(t["tag"] == "BUTTON" and t["inside"] and t["dy"] is not None and -3 <= t["dy"] <= 20 for t in v["tags"]), v["tags"])
        check("모양만 고친 문단 — 「M 앞 여백 · 2번째 줄」(줄의 자리 — 서식 값 「왼쪽 여백」·「첫 줄」 이 아니라) · 값마다 이름 「원본 … → 지금 7mm」 · 도움말에 값의 뜻",
              ta and ta["k"] == "M" and "2번째 줄" in ta["s"] and "왼쪽 여백" not in ta["s"] and "첫 줄" not in ta["s"] and "원본" in ta["l"] and "→ 지금 7mm" in ta["l"]
              and "원본" in ta["title"] and "지금 7mm" in ta["title"] and "문단 모양" in ta["title"], ta)
        check("글을 고친 문단 — 「M 글」 · 「+ \"★넣은글\"」", tb_ and tb_["k"] == "M" and "글" in tb_["s"] and '+ "★넣은글"' in tb_["l"], tb_)
        check("새 문단 — 「A 새 문단」", tn and tn["k"] == "A" and "새 문단" in tn["s"] and "dd-A" in tn["cls"], tn)
        td_ = tag_of(v, D["id"])
        check("두 곳 고침 — 「외 1곳」 · 도움말에 − 원본 → + 지금", td_ and "외 1곳" in td_["l"] and "− 원본" in td_["title"] and "+ 지금" in td_["title"], td_)

        # ---- 4
        loc = page.locator(f'.sheet > .dd-tag[data-para="{A["id"]}"]')
        loc.hover()
        h = page.evaluate("(id) => { const t = document.querySelector('.sheet > .dd-tag[data-para=\"' + id + '\"]'), l = t.querySelector('.dd-l'), tr = t.getBoundingClientRect(), sr = t.parentElement.getBoundingClientRect();"
                          " return { long: getComputedStyle(l).display, short: getComputedStyle(t.querySelector('.dd-s')).display, inside: tr.right <= sr.right + 1 && tr.left >= sr.left - 1, w: Math.round(tr.width) }; }", A["id"])
        check("꼬리표에 올리면 「어떻게」 가 펼쳐진다 · 쪽 밖으로 안 나감", h["long"] != "none" and h["short"] == "none" and h["inside"], h)
        page.screenshot(path=str(OUT / "02_hover.png"))
        loc.click()
        page.wait_for_selector(f'#editsList li[data-id="{A["id"]}"].dd-flash', timeout=10000)
        g = page.evaluate("(id) => { const li = document.querySelector('#editsList li[data-id=\"' + id + '\"]'), r = li.getBoundingClientRect(), pr = document.getElementById('paneEdits').getBoundingClientRect();"
                          " return { pane: !document.getElementById('paneEdits').hidden, seen: r.top >= pr.top - 1 && r.top < innerHeight, fmt: !!li.querySelector('.gd-fmt') }; }", A["id"])
        check("꼬리표를 누르면 「고친 문단」 목록의 그 항목(값 표가 있는 항목)", g["pane"] and g["seen"], g)

        # ---- 5
        page.evaluate("(id) => { const p = document.querySelector('.para[data-id=\"' + id + '\"]'); p.focus(); setCaret(p, readText(p).length); }", B["id"])  # 문단 맨 끝(End 키는 줄 끝 — 칸이 좁으면 가운데)
        page.keyboard.type("ZZ")
        typed = "(id) => { const h = CSS.highlights.get('nfm-dd-ins'); return !!h && [...h].some((r) => r.toString() === 'ZZ' && r.startContainer.parentElement.closest('.para').dataset.id === id); }"
        try:
            page.wait_for_function(typed, arg=B["id"], timeout=3000)
            ok, why = True, ""
        except Exception:  # noqa: BLE001 — 못 기다린 까닭을 적는다
            ok = False
            why = page.evaluate("(id) => { const p = document.querySelector('.para[data-id=\"' + id + '\"]'), h = CSS.highlights.get('nfm-dd-ins');"
                                " return { now: readText(p), orig: state.original[id], saved: state.texts[id], active: document.activeElement === p, marks: DD.marks.has(p), vis: DD.vis.has(p),"
                                " hunks: DD.marks.has(p) ? DD.marks.get(p).hunks : null, ins: [...h].map((r) => r.toString()) }; }", B["id"])
        check("글을 치면 친 글이 바로 초록", ok, why)
        page.wait_for_function("(id) => state.texts[id].endsWith('ZZ') && !state.timers.size && !state.inflight", arg=B["id"], timeout=10000)
        v = view(page, ids)
        bi = [x["text"] for x in v["ins"] if x["para"] == B["id"]]
        check("서버 반영 뒤에도 그대로 — 넣은 글 둘(「★넣은글」 · 「ZZ」)", bi == ["★넣은글", "ZZ"], bi)

        # ---- 6
        page.evaluate("() => setZoom(state.zoom * 0.8)")
        page.wait_for_timeout(900)
        page.wait_for_function("() => document.querySelectorAll('.sheet > .dd-tag').length >= 4", timeout=10000)
        v = view(page, ids)
        check("배율을 바꾸면 꼬리표가 제 문단 높이로 다시 · 쪽 안", v["tags"] and all(t["inside"] and -3 <= t["dy"] <= 20 for t in v["tags"]), v["tags"])
        check("배율을 바꿔도 글자 표시는 남는다", [x["text"] for x in v["ins"] if x["para"] == B["id"]] == ["★넣은글", "ZZ"], v["ins"])
        page.screenshot(path=str(OUT / "03_zoom.png"))

        # ---- 7
        page.locator("#ddBtn").click()
        page.wait_for_function("() => !DD.on && !document.querySelectorAll('.sheet > .dd-tag').length && !document.querySelectorAll('#doc .para.dd').length", timeout=5000)
        v = view(page, ids)
        check("끄면 표시가 모두 걷힌다 — 꼬리표 · 글자 표시 · 띠 클래스", v["pressed"] == "false" and not v["tags"] and not v["ins"] and not v["del"] and v["dd"] == 0, (v["pressed"], len(v["tags"]), v["ins"], v["dd"]))
        check("끄면 전처럼 주황 바탕", v["look"][B["id"]]["bg"] == "rgba(245, 158, 11, 0.1)", v["look"][B["id"]])
        page.screenshot(path=str(OUT / "04_off.png"))
        page.reload()
        page.wait_for_selector(f'#doc .para[data-id="{A["id"]}"]', timeout=60000)
        page.wait_for_timeout(800)
        v = view(page, ids)
        check("다시 열어도 꺼짐(기억)", not v["on"] and v["pressed"] == "false" and not v["tags"] and v["dd"] == 0, (v["on"], v["pressed"], len(v["tags"])))
        page.locator("#ddBtn").click()
        page.wait_for_function("() => DD.on && DD.marks.size >= 6 && document.querySelectorAll('.sheet > .dd-tag').length >= 4", timeout=10000)
        v = view(page, ids)
        check("켜면 다시 — 글자 표시 · 꼬리표", v["pressed"] == "true" and any(x["text"] == "★넣은글" for x in v["ins"]) and len(v["tags"]) >= 4, (v["pressed"], v["ins"]))

        # ---- 8
        page.evaluate("(id) => revert(id)", C["id"])
        page.wait_for_function("(id) => !state.edited.has(id) && !document.querySelector('.sheet > .dd-tag[data-para=\"' + id + '\"]') && !document.querySelector('.para.dd[data-id=\"' + id + '\"]')", arg=C["id"], timeout=10000)
        v = view(page, ids)
        check("문단을 되돌리면 그 문단의 표시가 사라진다 · 나머지는 그대로", not [x for x in v["del"] if x["para"] == C["id"]] and tag_of(v, B["id"]) is not None, (v["del"], [t["para"] for t in v["tags"]]))
        doc2 = upload(SAMPLE.with_suffix(".docx"))  # 다른 파일 — 같은 파일을 다시 올리면 같은 작업이 열린다
        assert doc2 != doc
        page.evaluate("(id) => { openWork(id); }", doc2)  # 화면 안에서 다른 작업 열기(쪽을 새로 읽지 않는다 — 지켜보던 것을 버리는지)
        page.wait_for_function("(id) => state.id === id && document.querySelectorAll('#doc .para').length > 10", arg=doc2, timeout=60000)
        page.wait_for_timeout(600)
        v2 = page.evaluate("() => ({ tags: document.querySelectorAll('.sheet > .dd-tag').length, dd: document.querySelectorAll('#doc .para.dd').length, ins: CSS.highlights.get('nfm-dd-ins').size, marks: DD.marks.size, nav: document.getElementById('editNav').hidden })")
        check("다른 문서(고친 것 없음) — 표시 없음 · 단추 감춤", v2 == {"tags": 0, "dd": 0, "ins": 0, "marks": 0, "nav": True}, v2)
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

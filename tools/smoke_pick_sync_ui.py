"""「템플릿 관계」 의 고른 갈래(☐) ↔ 본문 표시 · 살펴보는 갈래(spec_hwpx_웹편집 ② §8-2 — app/static/outline_match.js · fmt_focus.js) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음 — 「못 읽음」 한 가지만 진짜 요청 하나를 끊어서 본다).

2026-11-16 사용자 「템플릿 관계에서 모두 고르기 를 하면 왼쪽 원문에도 관련된 것들이 모두 선택이 되어야지. 12개에서 내가 뭔지를 모르겠잖아 … 상호 동기화 되도록」.
연구개발계획서 양식을 올리고 1·2단계(LLM 없이)를 끝점으로 돌린다. T9 「[기관] › o › -」 L2 「o」 는 갈래 다섯(대표 ×31 · ×9 · ×2 · ×1 · ×1) — **30줄을 넘는 갈래를 고를 수 있게** 끝점으로 대표를 ×9 갈래의 줄로
바꿔 둔다(PUT …/rep — 그러면 ×31 갈래가 「갈래 1」: 카드의 줄 목록은 30줄에서 잘린다). 본문의 표시는 **줄 수가 아니라 문단 id 집합**으로 견준다(#doc .para.fmt-hit 의 data-id — 쪽에 걸친 문단은 요소가 둘).

 1. 갈래 하나의 ☐ → 본문에 또렷한 줄 = 그 갈래의 줄 전부(GET …/outline/formats?tpl=&level= 의 paras) · 이름 줄 「고른 갈래 1 · 줄 n개」 · 꼬리표의 번호 = 카드의 번호 · 여백 표기는 「일부」(.part).
 2. 「모두 고르기」 → 대표가 아닌 갈래의 줄 전부의 합집합(값 칸 줄은 어느 갈래에도 없어 빠진다 — 그런 레벨이 있으면 그 레벨로도).
 3. 30줄을 넘는 갈래만 → 31번째 줄까지(카드의 목록은 30줄).
 4. 모두 풀면 표시가 꺼진다.
 5. 「끄기」 는 표시만 — ☐ 는 남고, ☐ 를 다시 건드리면 다시 보인다.
 6. 두 트리(「템플릿 관계」 열 · 「템플릿」 탭)의 ☐ · 「모두 고르기」 · 단추 글이 같이 바뀐다.
 7. 꼬리표를 누르면 그 갈래의 카드에 .sel — 31번째 뒤의 줄도 · 열을 다시 짓지 않는다 · 고르기는 안 바뀐다.
 8. 「본문에서 보기」 는 고르기를 안 바꾼다(고른 갈래를 보는 중이면 표시도 그대로 · 꺼져 있으면 레벨 전체로).
 9. 레벨 A 고름 → 끄기 → 레벨 B 고름 → A 의 마지막 ☐ 를 풀어도 B 의 표시는 그대로.
10. 「고른 갈래 맞추기」 가 rev 를 보낸다 · 보낸 고르기와 표시가 비워진다 · 실행 취소 · 고른 뒤 갈래가 바뀌면(화면에서 그 줄의 서식을 바꿈) 맞추지 않고 고르기를 푼다 ·
    화면 모르게 문서가 바뀌면(끝점으로 편집 — 옛 rev) 서버 409: 고르기를 풀고 알림 · 아무것도 안 맞춤.
11. 다른 문서를 열면 고르기도 표시도 없다.
12. 체크한 갈래를 대표 미리보기로 끌면 고른 것에서 빠지고 본문 표시도 따라 바뀐다 · 줄 전부 읽기가 실패하면 「읽지 못함」(줄 수를 말하지 않고 꺼지지도 않음) → 「다시 읽기」 · 콘솔 오류 없음 · 켜고 끄는 시간.

    python -X utf8 tools/smoke_pick_sync_ui.py <출력 폴더> [--port 18487]
"""
import argparse
import json
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
ap.add_argument("--port", type=int, default=18487)
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


def upload(name):
    r = requests.post(base + "/api/docs", files={"file": (name, (SAMPLES / name).read_bytes(), "application/octet-stream")}, timeout=120)
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


def slot(doc, tid, lv):  # 그 레벨의 서식 갈래 — 줄 전부(화면이 읽는 것과 같은 끝점) → (갈래 자료, 문서 차례)
    r = requests.get(f"{base}/api/docs/{doc}/outline/formats", params={"tpl": tid, "level": lv}, timeout=60).json()
    return r["slots"][str(tid)][str(lv)], r["rev"]


def level_ids(doc, tid, lv):  # 그 템플릿·레벨의 줄(개요 오버레이 — 값 칸 줄도 든다)
    o = requests.get(f"{base}/api/docs/{doc}/outline", timeout=60).json()
    return sorted(p for p, x in o["lines"].items() if str(x["tpl"]) == str(tid) and int(x["level"]) == lv)


def others(v):  # 대표가 아닌 갈래(목록 차례 = 화면의 「갈래 1」 …)
    return [g for g in v["groups"] if not g["rep"]]


def value_candidate(doc, allv, skip):  # 값 칸으로 만들 줄 — 여러 칸 표의 칸에 글 있는 문단이 그것 하나뿐인 개요 줄(대표가 있는 레벨의, 대표가 아닌 갈래의 줄 — 줄이 둘 이상인 갈래 먼저) → (문단, tpl, level, 오버레이 줄) | None
    d = requests.get(f"{base}/api/docs/{doc}", timeout=120).json()
    lines = requests.get(f"{base}/api/docs/{doc}/outline", timeout=60).json()["lines"]
    found = []

    def walk(blocks):
        for b in blocks:
            cells = b.get("cells") or []
            if b.get("type") == "table" and len(cells) > 1:
                for c in cells:
                    if all(x.get("type") == "paragraph" for x in c["blocks"]):
                        ps = [x for x in c["blocks"] if (x.get("text") or "").strip()]
                        if len(ps) == 1 and ps[0]["id"] in lines:
                            found.append(ps[0])
            for c in cells:
                walk(c["blocks"])
    walk(d["blocks"])
    best = None
    for para in found:
        x = lines[para["id"]]
        t, l = str(x["tpl"]), int(x["level"])
        v = allv.get(t, {}).get(str(l))
        if not v or not v["rep"] or (t, l) in skip or x.get("role") in ("label", "subtitle", "table") or not x.get("letter"):
            continue
        g = next((g for g in v["groups"] if para["id"] in g["paras"]), None)
        if not g or g["rep"] or para["text"].find(x["letter"]) < 0 or not para["text"][para["text"].find(x["letter"]) + len(x["letter"]):].strip():
            continue
        if best is None or (g["count"] >= 2) > best[0]:
            best = (g["count"] >= 2, para, t, l, x)
    return best[1:] if best else None


# 본문 · 이름 줄 · 꼬리표의 지금 모습 — 또렷한 줄은 **문단 id 집합**
VIEW = """() => { const doc = document.getElementById('doc'), key = document.getElementById('fmtKey'), uniq = (a) => [...new Set(a)], txt = (s) => (key.querySelector(s) || {}).textContent || '';
  const tags = [...document.querySelectorAll('.sheet > .fm-tag')].map((t) => ({ para: t.dataset.para, key: t.dataset.key || null, text: t.textContent, look: t.classList.contains('look'), tag: t.tagName, type: t.type || '' }));
  return { kind: FMF.kind, by: FMF.by, mem: FMF.mem, tpl: FMF.tpl, level: FMF.level, keys: FMF.keys ? [...FMF.keys].sort() : null, total: FMF.total, on: doc.classList.contains('fmt-focus'),
    hit: uniq([...doc.querySelectorAll('.para.fmt-hit')].map((p) => p.dataset.id)).sort(), tags,
    key: { shown: !key.hidden, chip: txt('.fm-key-chip'), text: txt('.fm-key-text'), count: txt('.fm-key-count'), note: txt('.fm-key-note'), btns: [...key.querySelectorAll('.fm-key-btn')].map((b) => b.textContent),
      inside: (() => { const rr = document.getElementById('fileInfo').getBoundingClientRect(), parts = [...key.querySelectorAll('.fm-key-chip, .fm-key-btn')].filter((e) => e.getClientRects().length);
        return parts.length >= 2 && parts.every((e) => { const r = e.getBoundingClientRect(); return r.left >= rr.left - 1 && r.right <= rr.right + 1; }); })(),
      seen: [...key.querySelectorAll('.fm-key-chip, .fm-key-btn')].filter((e) => e.getClientRects().length).map((e) => e.textContent) },
    part: uniq([...document.querySelectorAll('.tpl-mark .tm-t.part')].map((b) => b.dataset.tpl + '|' + b.dataset.level)), onMarks: document.querySelectorAll('.tpl-mark .tm-t.on').length,
    rowH: Math.round(document.getElementById('fileInfo').getBoundingClientRect().height), over: document.getElementById('fileInfo').scrollWidth > document.getElementById('fileInfo').clientWidth + 1,
    look: OLM.look ? OLM.look.key : null }; }"""
# 한 트리(root 선택자)의 그 레벨 첫 줄 — ☐ 켜진 갈래 · 「모두 고르기」 · 단추 · 카드 번호 · .sel
ROWV = """([root, t, l]) => { const r = document.querySelector(`${root} .olm[data-tpl="${t}"][data-level="${l}"]`); if (!r) return null; const all = r.querySelector('.olm-all .olm-chk'), go = r.querySelector('.olm-bulk-go');
  return { checked: [...r.querySelectorAll('li.olm-g')].filter((x) => { const c = x.querySelector('.olm-chk'); return c && c.checked; }).map((x) => x.dataset.key).sort(),
    all: all ? [all.checked, all.indeterminate] : null, go: go ? go.textContent : null, goOff: go ? go.disabled : null,
    nos: Object.fromEntries([...r.querySelectorAll('li.olm-g')].map((x) => [x.dataset.key, (x.querySelector('.olm-no') || x.querySelector('.olm-badge') || {}).textContent || ''])),
    sel: [...r.querySelectorAll('li.olm-g.sel')].map((x) => x.dataset.key), list: Object.fromEntries([...r.querySelectorAll('li.olm-g')].map((x) => [x.dataset.key, (x._paras || []).length])),
    see: r.querySelectorAll('li.olm-g .olm-see').length, cards: r.querySelectorAll('li.olm-g').length }; }"""
PICKS = "() => { olmOpenNow(); return Object.fromEntries([...OLM.chk].filter(([, s]) => s.size).map(([k, s]) => [k, [...s].sort()])); }"
COL, TAB = "#headsDlgBody", "#headsTemplatesResult"


def main():
    wait_server()
    doc = upload("연구개발계획서_양식.hwpx")
    run_stage(doc, 1)
    run_stage(doc, 2)
    docx = upload("기술수요조사서.docx")
    allv = requests.get(f"{base}/api/docs/{doc}/outline/formats", timeout=60).json()["slots"]
    for t, sl in allv.items():  # 이 양식의 레벨들 — 어느 레벨로 무엇을 보는지 기록에 남긴다
        for l, v in sl.items():
            if len(v["groups"]) > 1 or v["values"]:
                print(f"INFO T{t} L{l}: 줄 {v['total']} · 값 칸 {v['values']} · 갈래 {[('대표 ' if g['rep'] else '') + str(g['count']) for g in v['groups']]}", flush=True)
    A = ("9", 2)
    v0, _ = slot(doc, *A)
    big0 = max(v0["groups"], key=lambda g: g["count"])
    assert big0["count"] > 30, big0["count"]
    if big0["rep"]:  # 30줄을 넘는 갈래가 대표다 — 다른 갈래(가장 큰 것)의 줄을 대표로 바꿔 그 갈래를 고를 수 있게(끝점 PUT …/rep — 문서는 안 바뀐다)
        nxt = max(others(v0), key=lambda g: g["count"])
        r = requests.put(f"{base}/api/docs/{doc}/outline/slots/{A[0]}/{A[1]}/rep", json={"para": nxt["key"]}, timeout=60)
        assert r.status_code == 200, r.text
    va, _ = slot(doc, *A)
    oa = others(va)
    big = next(g for g in oa if g["count"] > 30)
    small = [g for g in oa if g is not big]
    k1, k2 = small[-1], small[0]  # 가장 작은 갈래 · 그다음 큰 갈래
    ids_a = level_ids(doc, *A)
    in_var = {p for g in va["groups"] for p in g["paras"]}
    print(f"INFO 레벨 A = T{A[0]} L{A[1]}: 줄 {len(ids_a)} · 갈래 {[('대표 ' if g['rep'] else '') + str(g['count']) for g in va['groups']]} · 값 칸 {va['values']} · 30줄 넘는 갈래 key {big['key']}({big['count']}줄)", flush=True)
    B = ("3", 2)
    vb, _ = slot(doc, *B)
    ob = others(vb)
    assert len(ob) >= 2, vb["groups"]
    # 값 칸 줄(여러 칸 표의 칸에 글이 있는 문단이 그 줄 하나뿐이고 레터만 있는 줄 — 서식 갈래에 안 든다)이 있는 레벨 — 「모두 고르기」 가 값 칸을 고른 것으로 보이지 않는지 볼 레벨.
    # 이 양식에는 값 칸이 없어 하나 만든다: 표 칸에 혼자 있는 개요 줄(대표가 아닌 갈래의 것) 하나의 글을 끝점(PATCH …/blocks/{id})으로 레터만 남긴다
    V, vpid = None, None
    cand = value_candidate(doc, allv, {A, B})
    if cand:
        para, t, l, x = cand
        i = para["text"].find(x["letter"])
        r = requests.patch(f"{base}/api/docs/{doc}/blocks/{para['id']}", json={"text": para["text"][: i + len(x["letter"])] + " "}, timeout=60) if i >= 0 else None
        vv0 = slot(doc, t, l)[0] if r is not None and r.status_code == 200 else None
        if vv0 and vv0["values"] and vv0["rep"] and others(vv0) and not any(para["id"] in g["paras"] for g in vv0["groups"]):
            V, vpid = (t, l), para["id"]
        print(f"INFO 값 칸 만들기 — T{t} L{l} 의 표 칸 줄 {para['id']} 「{para['text'][:20]}」 을 레터만 남김 → {'값 칸 ' + str(vv0['values']) + '줄' if vv0 else '실패'}{'' if V else ' (값 칸으로 안 됨 — 건너뜀)'}", flush=True)
    else:
        print("INFO 표 칸에 혼자 있는 개요 줄(대표가 아닌 갈래)이 이 양식에 없음 — 값 칸을 못 만든다", flush=True)

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1700, "height": 950}, device_scale_factor=1)
        quiet = {"on": False}  # 일부러 실패시키는 요청(409 · 끊은 요청)의 「Failed to load resource」 는 콘솔 오류로 세지 않는다
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and not (quiet["on"] and "Failed to load resource" in m.text) else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        posts = []
        page.on("request", lambda r: posts.append((r.url, r.post_data)) if r.method == "POST" and "/outline/templates/" in r.url else None)
        page.goto(f"{base}/#w={doc}")
        page.wait_for_selector("#doc .para[data-id=p970]", timeout=60000)
        page.wait_for_function("() => document.querySelectorAll('.tpl-mark').length > 20", timeout=30000)
        missing = page.evaluate("(ids) => ids.filter((i) => !document.querySelector(`#doc .para[data-id=\"${i}\"]`))", ids_a)
        check("레벨 A 의 줄이 모두 화면에 있다(문단 id 집합으로 견줄 수 있다)", not missing, missing[:5])

        row = f'{COL} .olm[data-tpl="{A[0]}"][data-level="{A[1]}"]'
        card = lambda g, root=COL: page.locator(f'{root} .olm[data-tpl="{A[0]}"][data-level="{A[1]}"]').first.locator(f'li.olm-g[data-key="{g["key"]}"]')  # noqa: E731
        shown_is = lambda want: page.wait_for_function("(w) => { const h = [...new Set([...document.querySelectorAll('#doc .para.fmt-hit')].map((p) => p.dataset.id))].sort(); return FMF.mem === 'ready' && h.length === w.length && h.every((x, i) => x === w[i]); }",  # noqa: E731
                                                       arg=sorted(want), timeout=20000)
        off_is = lambda: page.wait_for_function("() => !FMF.kind && !document.getElementById('doc').classList.contains('fmt-focus') && !document.querySelector('#doc .para.fmt-hit')", timeout=20000)  # noqa: E731

        def safe(fn, name):  # 기다리다 시간이 넘으면 그 검사만 떨어뜨리고 다음으로
            try:
                fn()
                return True
            except Exception as e:  # noqa: BLE001
                check(name + " (기다림 시간 넘음)", False, str(e)[:300])
                return False

        page.evaluate("([t, l]) => tplRelOpen(+t, { tpl: t, level: l, para: null })", [A[0], A[1]])  # 줄 없이 그 레벨만 편다(줄을 주면 그 줄의 갈래가 「살펴보는 갈래」 가 된다 — 7·8 에서 따로 본다)
        page.wait_for_selector(f"{row} .olm-list li.olm-g", timeout=30000)
        rv = page.evaluate(ROWV, [COL, *A])
        nos = {g["key"]: f"갈래 {i + 1}" for i, g in enumerate(oa)}
        check("카드마다 갈래 번호(대표 = 「대표」 · 그 밖 「갈래 1」 … — 목록 차례) · 「본문에서 보기」 · 30줄 넘는 갈래의 카드 목록은 30줄",
              rv and all(rv["nos"].get(k) == n for k, n in nos.items()) and rv["nos"].get(va["rep"]) == "대표" and rv["see"] == rv["cards"] == len(va["groups"]) and rv["list"][big["key"]] == 30, rv)
        v = page.evaluate(VIEW)
        check("고르기 전 — 본문 표시 없음 · 고른 것 없음", not v["kind"] and not v["on"] and not v["hit"] and page.evaluate(PICKS) == {}, [v["kind"], v["hit"][:3]])

        # 1. 갈래 하나
        card(k1).locator("input.olm-chk").check()
        safe(lambda: shown_is(k1["paras"]), "1")
        v, rv = page.evaluate(VIEW), page.evaluate(ROWV, [COL, *A])
        check(f"1. 갈래 하나의 ☐ → 본문에 또렷한 줄 = 그 갈래의 줄 전부({k1['count']}줄 — 문단 id 집합) · 표시의 주인 = 고르기(by chk)",
              v["hit"] == sorted(k1["paras"]) and v["by"] == "chk" and v["tpl"] == A[0] and v["level"] == A[1] and v["keys"] == [k1["key"]] and v["on"], [v["hit"], k1["paras"], v["by"], v["keys"]])
        no_a = page.evaluate("(t) => String(heads.outline.templates[t].no)", A[0])
        check("이름 줄 「T… L…」 칩 · 「고른 갈래 1 · 줄 n개」 · 「템플릿 관계」 · 「끄기」 · 줄 높이 35px · 넘침 없음",
              v["key"]["shown"] and v["key"]["chip"] == f"T{no_a} L{A[1]}" and v["key"]["count"] == f"고른 갈래 1 · 줄 {k1['count']}개" and v["key"]["btns"][-2:] == ["템플릿 관계", "끄기"] and v["rowH"] == 35 and not v["over"], v["key"])
        tg = [t for t in v["tags"] if t["key"] == k1["key"]]
        check("보이는 줄마다 쪽 오른쪽 여백에 꼬리표 — 번호가 카드의 번호와 같다(「갈래 n · ≠ …」) · 누르는 단추(button)",
              sorted({t["para"] for t in tg}) == sorted(k1["paras"]) and all(t["text"].startswith(nos[k1["key"]]) and t["tag"] == "BUTTON" and t["type"] == "button" for t in tg) and len(v["tags"]) == len(tg)
              and rv["nos"][k1["key"]] == nos[k1["key"]], [v["tags"][:4], rv["nos"]])
        check("여백의 그 레벨 표기는 「일부」(.part — 레벨 전체의 눌림 .on 이 아니다)", v["part"] == [f"{A[0]}|{A[1]}"] and v["onMarks"] == 0, [v["part"], v["onMarks"]])
        check("단추 글 「고른 1갈래 맞추기(n줄)」 · 「모두 고르기」 는 일부(가운데 줄)", rv["go"] == f"고른 1갈래 맞추기({k1['count']}줄)" and rv["all"] == [False, True] and rv["checked"] == [k1["key"]], rv)

        # 2. 모두 고르기
        page.locator(f"{row} .olm-bulk .olm-all input").first.check()
        union = sorted(p for g in oa for p in g["paras"])
        safe(lambda: shown_is(union), "2")
        v, rv = page.evaluate(VIEW), page.evaluate(ROWV, [COL, *A])
        lines = sum(g["count"] for g in oa)
        check(f"2. 「모두 고르기」 → 대표가 아닌 갈래 {len(oa)}개의 줄 전부({lines}줄 — 합집합 · 30줄 넘는 갈래의 31번째 줄도) · 「고른 갈래 {len(oa)} · 줄 {lines}개」 · 단추 글",
              v["hit"] == union and len(union) == lines and big["paras"][30] in v["hit"] and v["key"]["count"] == f"고른 갈래 {len(oa)} · 줄 {lines}개" and rv["go"] == f"고른 {len(oa)}갈래 맞추기({lines}줄)"
              and rv["all"] == [True, False] and rv["checked"] == sorted(g["key"] for g in oa), [len(v["hit"]), lines, v["key"], rv["go"], rv["all"]])
        rest = sorted(set(ids_a) - in_var)
        check(f"대표 갈래의 줄 · 어느 갈래에도 없는 줄(값 칸 {len(rest)}줄)은 고른 것으로 안 보인다", not (set(v["hit"]) & (set(next(g for g in va['groups'] if g['rep'])['paras']) | set(rest))), rest[:5])
        tk = {}
        for t in v["tags"]:
            tk.setdefault(t["key"], []).append(t)
        check("꼬리표는 갈래마다 제 번호 — 다른 갈래를 한 꼬리표로 묶지 않는다(꼬리표의 갈래 = 그 줄의 갈래)",
              set(tk) == {g["key"] for g in oa} and all(all(t["text"].startswith(nos[k]) and t["para"] in next(g for g in oa if g["key"] == k)["paras"] for t in ts) for k, ts in tk.items()),
              {k: [t["text"] for t in ts][:3] for k, ts in tk.items()})
        page.evaluate("(pid) => document.querySelector(`#doc .para[data-id=\"${pid}\"]`).scrollIntoView({ block: 'center' })", big["paras"][0])
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / "01_all_picked.png"))

        # 3 · 4. 모두 풀기 → 꺼짐 · 30줄 넘는 갈래만
        page.locator(f"{row} .olm-bulk .olm-all input").first.uncheck()
        ok4 = safe(off_is, "4")
        v, rv = page.evaluate(VIEW), page.evaluate(ROWV, [COL, *A])
        check("4. 모두 풀면 본문 표시가 꺼진다(흐림·바탕·꼬리표·이름 줄 설명 모두) · 단추 꺼짐", ok4 and not v["on"] and not v["hit"] and not v["tags"] and not v["key"]["shown"] and not v["part"] and rv["goOff"] and rv["checked"] == []
              and page.evaluate(PICKS) == {}, [v["on"], len(v["hit"]), rv])
        card(big).locator("input.olm-chk").check()
        safe(lambda: shown_is(big["paras"]), "3")
        v, rv = page.evaluate(VIEW), page.evaluate(ROWV, [COL, *A])
        check(f"3. 30줄을 넘는 갈래({big['count']}줄)만 → 그 줄 전부(31번째 줄 {big['paras'][30]} 포함) — 카드의 줄 목록은 30줄에서 잘려 있다",
              v["hit"] == sorted(big["paras"]) and big["paras"][30] in v["hit"] and rv["list"][big["key"]] == 30 and rv["go"] == f"고른 1갈래 맞추기({big['count']}줄)" and v["key"]["count"] == f"고른 갈래 1 · 줄 {big['count']}개", [len(v["hit"]), rv["go"], v["key"]])

        # 7. 꼬리표 → 카드(31번째 뒤의 줄) — 열을 다시 짓지 않는다 · 고르기는 안 바뀐다
        late = big["paras"][30:]
        tag_of = page.evaluate("([late, key]) => { const t = [...document.querySelectorAll('.sheet > .fm-tag')].find((x) => x.dataset.key === key && late.includes(x.dataset.para)); return t ? t.dataset.para : null; }", [late, big["key"]])
        print(f"INFO 31번째 뒤의 줄 {late} 가운데 꼬리표가 가리키는 줄: {tag_of}", flush=True)
        page.evaluate("() => { document.querySelector('#headsDlgBody .tpl-tree')._probe = 1; OLM.look = null; olmLookPaint(); }")
        if tag_of:  # 키보드로 — 꼬리표는 초점을 받는 단추다(Enter)
            page.evaluate("(pid) => { const t = document.querySelector(`.sheet > .fm-tag[data-para=\"${pid}\"]`); t.scrollIntoView({ block: 'center' }); t.focus({ preventScroll: true }); }", tag_of)
            focused = page.evaluate("() => document.activeElement && document.activeElement.classList.contains('fm-tag')")
            page.keyboard.press("Enter")
            check("꼬리표는 키보드 초점을 받는다(단추) — Enter 로 누른다", focused)
        else:  # 같은 높이의 앞 줄과 한 꼬리표로 묶였다 — 그 줄의 꼬리표가 하는 일을 그대로 부른다
            page.evaluate("(pid) => fmTagGo(pid)", late[0])
        ok7 = safe(lambda: page.wait_for_function("(k) => { const r = document.querySelector('#headsDlgBody .olm.sel'); return r && [...r.querySelectorAll('li.olm-g.sel')].some((x) => x.dataset.key === k); }", arg=big["key"], timeout=20000), "7")
        v, rv = page.evaluate(VIEW), page.evaluate(ROWV, [COL, *A])
        check("7. 꼬리표(갈래의 31번째 뒤 줄)를 누르면 그 갈래의 카드에 .sel(그 카드만) — 열을 다시 짓지 않는다 · 고르기·본문 표시는 그대로 · 그 갈래의 꼬리표에 강조(.look)",
              ok7 and rv["sel"] == [big["key"]] and page.evaluate("() => document.querySelector('#headsDlgBody .tpl-tree')._probe === 1") and page.evaluate(PICKS) == {f"{A[0]}|{A[1]}": [big["key"]]}
              and v["hit"] == sorted(big["paras"]) and v["look"] == big["key"] and all(t["look"] for t in v["tags"] if t["key"] == big["key"]) and any(t["key"] == big["key"] for t in v["tags"]), [rv["sel"], v["look"], page.evaluate(PICKS)])
        page.screenshot(path=str(OUT / "02_tag_to_card.png"))
        page.wait_for_timeout(4300)  # 레벨 줄의 표시(.olm.sel)는 4초 — 카드의 .sel 은 다음 살펴보기까지 남는다
        rv = page.evaluate(ROWV, [COL, *A])
        check("카드의 .sel 은 4초 뒤에도 남는다(다음 살펴보기까지)", rv["sel"] == [big["key"]] and not page.evaluate("() => !!document.querySelector('#headsDlgBody .olm.sel')"), rv["sel"])
        page.click("#headsDlgClose")  # 열이 닫혀 있으면 꼬리표가 열을 연다(그 카드로)
        page.evaluate("(pid) => fmTagGo(pid)", late[-1])
        ok7b = safe(lambda: page.wait_for_function("(k) => { const c = document.getElementById('headsDlg'); const r = document.querySelector('#headsDlgBody .olm.sel'); return !c.hidden && c.dataset.kind === 'templates' && r && [...r.querySelectorAll('li.olm-g.sel')].some((x) => x.dataset.key === k); }",
                                                    arg=big["key"], timeout=30000), "7b")
        check("열이 닫혀 있을 때 꼬리표 → 「템플릿 관계」 가 열리고 그 갈래의 카드에 .sel(31번째 뒤 줄 — 줄 전부의 대응으로 찾는다) · 고르기는 그대로", ok7b and page.evaluate(PICKS) == {f"{A[0]}|{A[1]}": [big["key"]]})

        # 8. 「본문에서 보기」 — 고르기는 안 바뀐다
        page.wait_for_selector(f"{row} .olm-list li.olm-g", timeout=20000)
        card(k2).locator("button.olm-see").click()
        page.wait_for_function("(k) => OLM.look && OLM.look.key === k", arg=k2["key"], timeout=10000)
        page.wait_for_timeout(600)
        v, rv = page.evaluate(VIEW), page.evaluate(ROWV, [COL, *A])
        tk2 = [t for t in v["tags"] if t["key"] == k2["key"]]
        check("8. 고른 갈래를 보는 중의 「본문에서 보기」(다른 갈래) — 고르기 그대로 · 본문 표시도 그대로(고른 갈래의 줄) · 그 카드에 .sel · 그 갈래의 줄에 강조 꼬리표(번호) · 첫 줄로",
              page.evaluate(PICKS) == {f"{A[0]}|{A[1]}": [big["key"]]} and v["by"] == "chk" and v["hit"] == sorted(big["paras"]) and rv["sel"] == [k2["key"]] and rv["checked"] == [big["key"]]
              and sorted({t["para"] for t in tk2}) == sorted(k2["paras"]) and all(t["look"] and t["text"].startswith(nos[k2["key"]]) for t in tk2)
              and page.evaluate("(pid) => document.querySelector(`#doc .para[data-id=\"${pid}\"]`).classList.contains('flash')", k2["paras"][0]), [page.evaluate(PICKS), v["by"], rv["sel"], tk2[:2]])
        # 5. 「끄기」 — 표시만
        page.click("#fmtKey .fm-key-off")
        ok5 = safe(off_is, "5")
        rv = page.evaluate(ROWV, [COL, *A])
        check("5. 「끄기」 → 표시만 꺼진다 — ☐ 와 고른 것은 그대로(단추도 그대로 켜져 있다)", ok5 and page.evaluate(PICKS) == {f"{A[0]}|{A[1]}": [big["key"]]} and rv["checked"] == [big["key"]] and not rv["goOff"], rv)
        card(k1).locator("button.olm-see").click()
        safe(lambda: page.wait_for_function("([t, l]) => FMF.kind === 'tpl' && FMF.tpl === t && FMF.level === l && !FMF.keys && !!FMF.sum", arg=[A[0], A[1]], timeout=20000), "8b")
        page.wait_for_timeout(400)
        v = page.evaluate(VIEW)
        check("표시가 꺼져 있을 때의 「본문에서 보기」 → 그 레벨 전체(고르기가 켠 표시가 아니다 — by 없음) · 그 갈래의 줄에 강조 꼬리표 · 고르기 그대로",
              v["by"] is None and v["keys"] is None and v["hit"] == ids_a and page.evaluate(PICKS) == {f"{A[0]}|{A[1]}": [big["key"]]} and v["look"] == k1["key"]
              and sorted({t["para"] for t in v["tags"] if t["look"]}) == sorted(k1["paras"]) and v["onMarks"] > 0 and not v["part"], [v["by"], len(v["hit"]), len(ids_a), v["look"]])
        card(k1).locator("input.olm-chk").check()
        want = sorted(big["paras"] + k1["paras"])
        safe(lambda: shown_is(want), "5b")
        v = page.evaluate(VIEW)
        check("☐ 를 다시 건드리면 고른 것이 다시 보인다(남아 있던 갈래 + 새로 고른 갈래 — 레벨 전체 표시를 갈아 끼움)", v["by"] == "chk" and v["hit"] == want and v["keys"] == sorted([big["key"], k1["key"]]), [v["by"], len(v["hit"]), len(want)])

        # 6. 두 트리
        page.click("#tabHeads")
        page.wait_for_function("() => heads.graph && document.querySelector('#headsTemplatesResult .tpl-tree li.trel-node')", timeout=120000)
        page.click("#headsTabTemplates")
        page.locator(f"{TAB} .tpl-tree-tools button", has_text="모두 펼치기").click()
        page.wait_for_selector(f'{TAB} .olm[data-tpl="{A[0]}"][data-level="{A[1]}"] .olm-list li.olm-g', timeout=30000)
        a, c = page.evaluate(ROWV, [TAB, *A]), page.evaluate(ROWV, [COL, *A])
        same = lambda x, y: x and y and all(x[k] == y[k] for k in ("checked", "all", "go", "goOff", "nos"))  # noqa: E731
        check("6. 「템플릿」 탭의 같은 레벨도 같은 고르기(☐ · 「모두 고르기」 일부 · 단추 글 · 번호)", same(a, c) and a["checked"] == sorted([big["key"], k1["key"]]) and a["all"] == [False, True], [a, c])
        card(k2).locator("input.olm-chk").check()  # 열에서 고르면 탭도
        page.wait_for_timeout(300)
        a, c = page.evaluate(ROWV, [TAB, *A]), page.evaluate(ROWV, [COL, *A])
        check("열에서 ☐ 를 고르면 탭의 ☐ · 단추 글도 같이 바뀐다", same(a, c) and k2["key"] in a["checked"] and a["go"] == f"고른 3갈래 맞추기({big['count'] + k1['count'] + k2['count']}줄)", [a, c])
        card(big, TAB).locator("input.olm-chk").uncheck()  # 탭에서 풀면 열도 · 본문도
        want = sorted(k1["paras"] + k2["paras"])
        safe(lambda: shown_is(want), "6b")
        a, c, v = page.evaluate(ROWV, [TAB, *A]), page.evaluate(ROWV, [COL, *A]), page.evaluate(VIEW)
        check("탭에서 ☐ 를 풀면 열의 ☐ · 단추 글 · 본문 표시도 같이 바뀐다", same(a, c) and c["checked"] == sorted([k1["key"], k2["key"]]) and v["hit"] == want, [a, c, len(v["hit"])])
        page.locator(f'{TAB} .olm[data-tpl="{A[0]}"][data-level="{A[1]}"]').first.locator(".olm-bulk .olm-all input").check()  # 탭의 「모두 고르기」
        safe(lambda: shown_is(union), "6c")
        a, c = page.evaluate(ROWV, [TAB, *A]), page.evaluate(ROWV, [COL, *A])
        check("탭의 「모두 고르기」 → 열의 ☐ 도 모두 · 「모두 고르기」 켜짐(일부 아님)", same(a, c) and c["all"] == [True, False] and c["checked"] == sorted(g["key"] for g in oa), [a, c])

        # 12a. 체크한 갈래를 대표 미리보기로 → 고른 것에서 빠지고 본문도 따라 바뀐다 · 꼬리표는 번호만
        card(k2).locator(".olm-grip").click()
        page.wait_for_selector(f"{row} .olm-try", timeout=10000)
        rep_g = next(g for g in va["groups"] if g["rep"])
        want = sorted(p for g in oa if g is not k2 for p in g["paras"])
        safe(lambda: shown_is(want), "12a")
        v, c, a = page.evaluate(VIEW), page.evaluate(ROWV, [COL, *A]), page.evaluate(ROWV, [TAB, *A])
        check("12. 고른 갈래를 대표 미리보기로(⠿) → 그 갈래는 고른 것에서 빠진다(기준이 됐다) — 본문 표시 · 두 트리의 ☐ · 단추 글이 따라 바뀐다 · 번호는 그대로",
              v["hit"] == want and k2["key"] not in c["checked"] and same(a, c) and c["go"].startswith("대표로 정하고 고른") and c["nos"].get(k2["key"]) == nos[k2["key"]] and c["nos"].get(big["key"]) == nos[big["key"]],
              [len(v["hit"]), len(want), c["checked"], c["go"], c["nos"]])
        check("미리보기 중 — 꼬리표는 번호만(카드의 「다른 값」 은 미리보기 갈래 기준) · 이름 줄에 「미리보기 중」", all(" · " not in t["text"] for t in v["tags"]) and len(v["tags"]) > 0 and v["key"]["note"] == "미리보기 중", [[t["text"] for t in v["tags"]][:4], v["key"]])
        page.keyboard.press("Escape")
        page.wait_for_function("(r) => !document.querySelector(r + ' .olm-try')", arg=row, timeout=10000)
        page.wait_for_timeout(300)
        v = page.evaluate(VIEW)
        check("Esc(미리보기 거둠) → 고르기·본문 표시는 그대로(빠진 갈래를 말없이 다시 고르지 않는다) · 꼬리표에 다시 「다른 값」", v["hit"] == want and page.evaluate(PICKS) == {f"{A[0]}|{A[1]}": sorted(g["key"] for g in oa if g is not k2)}
              and any(" · ≠" in t["text"] for t in v["tags"]) and v["key"]["note"] != "미리보기 중", [len(v["hit"]), page.evaluate(PICKS), [t["text"] for t in v["tags"]][:3]])

        # 값 칸이 있는 레벨 — 「모두 고르기」 가 값 칸 줄을 고른 것으로 보이지 않는다
        if V:
            vv, _ = slot(doc, *V)
            idv = level_ids(doc, *V)
            valv = sorted(set(idv) - {p for g in vv["groups"] for p in g["paras"]})
            wantv = sorted(p for g in others(vv) for p in g["paras"])
            page.evaluate("([t, l]) => olmPickChange(t, l, (s, others) => { for (const g of others) s.add(g.key); })", [V[0], V[1]])
            okv = safe(lambda: shown_is(wantv), "값 칸")
            v = page.evaluate(VIEW)
            check(f"값 칸 줄이 있는 레벨(T{V[0]} L{V[1]} — 값 칸 {len(valv)}줄: {vpid})을 모두 고르면 갈래의 줄만({len(wantv)}줄) — 값 칸 줄은 어느 갈래에도 없어 고른 것으로 안 보인다(그 레벨의 줄이기는 하다)",
                  okv and v["hit"] == wantv and len(valv) == vv["values"] > 0 and vpid in valv and vpid in idv and not (set(v["hit"]) & set(valv)) and v["key"]["count"] == f"고른 갈래 {len(others(vv))} · 줄 {len(wantv)}개",
                  [len(v["hit"]), len(wantv), valv[:3], v["key"]])
            page.evaluate("([t, l]) => olmPickChange(t, l, (s) => s.clear())", [V[0], V[1]])
            safe(off_is, "값 칸 풀기")
            check("그 레벨의 고르기를 풀면 그 표시가 꺼진다 — 다른 레벨(A)의 고르기는 남아 있다(표시는 꺼진 채)", page.evaluate(PICKS) == {f"{A[0]}|{A[1]}": sorted(g["key"] for g in oa if g is not k2)})
        else:
            print("INFO 값 칸 줄을 만들지 못함 — 값 칸 검사는 건너뜀(레벨 A 에는 값 칸이 없다)", flush=True)

        # 9. 레벨 A 고름 → 끄기 → 레벨 B 고름 → A 의 마지막 ☐ 를 풀어도 B 의 표시는 그대로
        page.evaluate("([t, l, k]) => olmPickChange(t, l, (s) => { s.clear(); s.add(k); })", [A[0], A[1], k1["key"]])
        safe(lambda: shown_is(k1["paras"]), "9a")
        page.click("#fmtKey .fm-key-off")
        safe(off_is, "9b")
        page.evaluate("([t, l, p]) => tplRelOpen(+t, { tpl: t, level: l, para: p })", [B[0], B[1], vb["rep"]])
        rowb = f'{COL} .olm[data-tpl="{B[0]}"][data-level="{B[1]}"]'
        page.wait_for_selector(f"{rowb} .olm-list li.olm-g", timeout=30000)
        kb = ob[0]
        page.locator(rowb).first.locator(f'li.olm-g[data-key="{kb["key"]}"] input.olm-chk').check()
        safe(lambda: shown_is(kb["paras"]), "9c")
        card(k1, TAB).locator("input.olm-chk").uncheck()  # A 의 마지막 ☐ — 「템플릿」 탭의 것으로
        page.wait_for_timeout(500)
        v = page.evaluate(VIEW)
        check("9. 레벨 A 고름 → 끄기 → 레벨 B 고름 → A 의 마지막 ☐ 를 풀어도 B 의 표시는 그대로(표시의 주인 = B 의 고르기)", v["by"] == "chk" and v["tpl"] == B[0] and v["level"] == B[1] and v["hit"] == sorted(kb["paras"])
              and page.evaluate(PICKS) == {f"{B[0]}|{B[1]}": [kb["key"]]}, [v["by"], v["tpl"], v["level"], v["hit"], page.evaluate(PICKS)])

        # 10. 「고른 갈래 맞추기」 — rev 를 보낸다 · 보낸 고르기와 표시가 비워진다 · 실행 취소
        rev0 = page.evaluate("() => state.serverRev")
        _, srv0 = slot(doc, *B)
        posts.clear()
        page.locator(f"{rowb} .olm-bulk-go").first.click()
        page.wait_for_function("(r) => state.serverRev > r && !state.busy && !OLM.going", arg=rev0, timeout=60000)
        ok10 = safe(off_is, "10")
        body = json.loads(posts[0][1]) if posts else {}
        vb2, _ = slot(doc, *B)
        check("10. 「고른 갈래 맞추기」 가 고른 때의 문서 차례(rev)를 보낸다 · 고른 갈래만(likes) · 맞춘 뒤 그 갈래가 없어짐",
              len(posts) == 1 and f"/outline/templates/{B[0]}/match" in posts[0][0] and body.get("rev") == rev0 == srv0 and len(body["levels"]) == 1 and body["levels"][0]["likes"] == [kb["paras"][0]]
              and len(vb2["groups"]) == len(vb["groups"]) - 1, [posts[:1], rev0, srv0, len(vb2["groups"])])
        check("맞춘 뒤 — 보낸 고르기가 비워지고 본문 표시도 꺼진다", ok10 and page.evaluate(PICKS) == {} and not page.evaluate(VIEW)["on"], page.evaluate(PICKS))
        page.click("#undoBtn")
        page.wait_for_function("(n) => !state.busy && olmFresh() && (OLM.data['3'] || {})['2'] && OLM.data['3']['2'].groups.length === n", arg=len(vb["groups"]), timeout=60000)
        vb3, _ = slot(doc, *B)
        check("실행 취소 → 갈래가 되돌아온다(문서만 — 고르기는 되살리지 않는다)", len(vb3["groups"]) == len(vb["groups"]) and page.evaluate(PICKS) == {} and not page.evaluate(VIEW)["on"], [len(vb3["groups"]), page.evaluate(PICKS)])

        # 10b. 고른 뒤 갈래가 바뀜(화면에서 그 줄의 서식을 바꿈 — 목록은 옛것 그대로) → 맞추지 않고 고르기를 푼다
        page.wait_for_selector(f"{rowb} .olm-list li.olm-g", timeout=20000)
        ob3 = others(vb3)
        kb = ob3[0]
        page.locator(rowb).first.locator(f'li.olm-g[data-key="{kb["key"]}"] input.olm-chk').check()
        safe(lambda: shown_is(kb["paras"]), "10b")
        posts.clear()
        # 고른 갈래의 seed 줄을 다른 서식으로(서버는 그 줄의 새 서식과 같은 줄을 맞추려 한다) → 목록이 다시 그려지기 전에 곧바로 단추를 누른다(한 번의 실행 안에서 — 0.4초 뒤의 다시 읽기보다 먼저)
        stale_go = page.evaluate("""async ([pid, r]) => { await structOp('format/para', { ids: [pid], changes: { align: 'right' } });
          const b = document.querySelector(r + ' .olm-bulk-go'), was = [b.textContent, b.disabled, olmFresh()]; b.click(); return was; }""", [kb["paras"][0], rowb])
        page.wait_for_function("() => { olmOpenNow(); return !OLM.going && !state.busy && olmFresh() && ![...OLM.chk.values()].some((s) => s.size); }", timeout=30000)
        toast = page.evaluate("() => { const t = document.getElementById('toast'); return t.hidden ? '' : t.textContent; }")
        page.wait_for_timeout(600)
        check("고른 뒤 그 갈래 줄의 서식이 바뀌면(목록은 옛것 — 단추는 켜진 채) 「고른 갈래 맞추기」 는 맞추지 않는다 — 갈래를 다시 읽어 구성이 달라 고르기를 풀고 알린다(요청을 안 보냄) · 표시 꺼짐",
              stale_go[0] == f"고른 1갈래 맞추기({kb['count']}줄)" and not stale_go[1] and not stale_go[2] and not posts and page.evaluate(PICKS) == {} and "갈래가 바뀌었습니다" in toast and "다시 골라" in toast
              and not page.evaluate(VIEW)["on"], [posts, page.evaluate(PICKS), toast, stale_go])
        page.click("#undoBtn")
        page.wait_for_function("(n) => !state.busy && olmFresh() && OLM.data['3']['2'].groups.length === n", arg=len(vb["groups"]), timeout=60000)

        # 10c. 화면 모르게 문서가 바뀜(끝점으로 편집 — 화면의 rev 는 옛것) → 서버 409: 고르기를 풀고 알림 · 아무것도 안 맞춤 · 화면이 서버 문서를 다시 읽는다
        vb4, _ = slot(doc, *B)
        kb = others(vb4)[0]
        page.wait_for_selector(f'{rowb} li.olm-g[data-key="{kb["key"]}"] input.olm-chk', timeout=20000)
        page.locator(rowb).first.locator(f'li.olm-g[data-key="{kb["key"]}"] input.olm-chk').check()
        safe(lambda: shown_is(kb["paras"]), "10c")
        rev2 = page.evaluate("() => state.serverRev")
        r = requests.post(f"{base}/api/docs/{doc}/format/para", json={"ids": [kb["paras"][0]], "changes": {"align": "right"}}, timeout=60)
        assert r.status_code == 200, r.text
        before = [g["count"] for g in slot(doc, *B)[0]["groups"]]
        posts.clear()
        quiet["on"] = True
        page.locator(f"{rowb} .olm-bulk-go").first.click()
        page.wait_for_function("() => { const t = document.getElementById('toast'); return !t.hidden && t.textContent.includes('다시 골라'); }", timeout=30000)
        toast = page.evaluate("() => { const t = document.getElementById('toast'); return t.hidden ? '' : t.textContent; }")
        page.wait_for_function("(r) => !OLM.going && !state.busy && state.serverRev > r && olmFresh()", arg=rev2, timeout=60000)
        page.wait_for_timeout(300)
        quiet["on"] = False
        after = [g["count"] for g in slot(doc, *B)[0]["groups"]]
        check("화면 모르게 문서가 바뀐 뒤의 「고른 갈래 맞추기」 → 옛 rev 를 보내 서버가 409 — 아무것도 안 맞춘다 · 고르기를 풀고 「문서가 바뀌었습니다 — 갈래를 다시 골라 주세요」 · 표시 꺼짐 · 화면이 서버 문서로",
              len(posts) == 1 and json.loads(posts[0][1]).get("rev") == rev2 and before == after and page.evaluate(PICKS) == {} and "문서가 바뀌었습니다" in toast and "다시 골라" in toast
              and not page.evaluate(VIEW)["on"] and page.evaluate("() => state.serverRev") == slot(doc, *B)[1], [posts[:1], rev2, before, after, toast, page.evaluate(PICKS)])

        # 12b. 줄 전부 읽기가 실패 → 「읽지 못함」(줄 수를 말하지 않는다 · 꺼지지 않는다) → 「다시 읽기」
        page.evaluate("([t, l, p]) => tplRelOpen(+t, { tpl: t, level: l, para: p })", [A[0], A[1], va["rep"]])
        page.wait_for_selector(f"{row} .olm-list li.olm-g", timeout=30000)
        page.wait_for_function("() => olmFresh()", timeout=20000)
        cut = {"n": 0}

        def fail_once(route):  # 진짜 요청 하나를 끊는다(흉내 답이 아니다) — 그 레벨만 줄 전부로 읽는 요청
            if cut["n"] == 0:
                cut["n"] += 1
                route.abort()
            else:
                route.continue_()
        full_url = re.compile(r"/outline/formats\?tpl=")
        page.route(full_url, fail_once)
        quiet["on"] = True
        page.evaluate("() => { OLM.full.clear(); }")  # 기억한 줄 대응을 버려 다시 읽게
        card(big).locator("input.olm-chk").check()
        okf = safe(lambda: page.wait_for_function("() => FMF.kind === 'tpl' && FMF.by === 'chk' && FMF.mem === 'error'", timeout=20000), "12b")
        page.wait_for_timeout(300)
        v = page.evaluate(VIEW)
        check("줄 전부 읽기가 실패하면 — 표시는 꺼지지 않고(고르기 그대로) 이름 줄에 「갈래의 줄을 읽지 못함」 · 줄 수를 말하지 않는다 · 「다시 읽기」",
              okf and cut["n"] == 1 and v["kind"] == "tpl" and v["by"] == "chk" and v["key"]["shown"] and v["key"]["note"] == "갈래의 줄을 읽지 못함" and "줄" not in v["key"]["count"] and "다시 읽기" in v["key"]["btns"]
              and page.evaluate(PICKS) == {f"{A[0]}|{A[1]}": [big["key"]]}, [v["kind"], v["mem"], v["key"], cut])
        quiet["on"] = False
        page.click("#fmtKey .fm-key-retry")
        safe(lambda: shown_is(big["paras"]), "12c")
        page.unroute(full_url)
        v = page.evaluate(VIEW)
        check("「다시 읽기」 → 고른 갈래의 줄 전부가 보인다", v["hit"] == sorted(big["paras"]) and v["key"]["count"] == f"고른 갈래 1 · 줄 {big['count']}개", [len(v["hit"]), v["key"]])
        page.screenshot(path=str(OUT / "03_pick_key.png"))

        # 좁은 폭 — 고른 갈래 설명도 한 줄(35px) · 넘침 없음 · 칩과 단추는 줄 안: 옆 열을 연 1500px(문서 칸이 가장 좁다 — 360px) · 1100px · 열을 닫은 700px
        for w, col in ((1500, True), (1100, True), (700, False)):
            if not col:
                page.click("#headsDlgClose")
            page.set_viewport_size({"width": w, "height": 900})
            page.wait_for_timeout(500)
            v = page.evaluate(VIEW)
            docw = page.evaluate("() => Math.round(document.getElementById('fileInfo').getBoundingClientRect().width)")
            check(f"{w}px(고른 갈래 설명 · 옆 열 {'열림' if col else '닫음'} — 이름 줄 {docw}px) — 줄 높이 35px · 넘침 없음 · 칩 · 「템플릿 관계」 · 「끄기」 는 줄 안",
                  v["rowH"] == 35 and not v["over"] and v["key"]["shown"] and v["key"]["inside"] and v["key"]["seen"][0] == v["key"]["chip"] and v["key"]["seen"][-2:] == ["템플릿 관계", "끄기"], [v["rowH"], v["over"], v["key"]])
            if w == 1500:  # 못 읽은 설명(「다시 읽기」)도 그 폭에 든다 — 「템플릿 관계」 대신 「다시 읽기」 가 남는다
                e = page.evaluate("() => { FMF.mem = 'error'; fmtFocusKey(); const k = document.getElementById('fmtKey'), row = document.getElementById('fileInfo'); const seen = [...k.querySelectorAll('.fm-key-chip, .fm-key-btn')].filter((x) => x.getClientRects().length).map((x) => x.textContent);"
                                  " const over = row.scrollWidth > row.clientWidth + 1; FMF.mem = 'ready'; fmtFocusKey(); return { seen, over }; }")
                check("가장 좁은 이름 줄에서 못 읽은 설명 — 「다시 읽기」 · 「끄기」 가 남고 넘치지 않는다", not e["over"] and e["seen"][-2:] == ["다시 읽기", "끄기"], e)
        page.set_viewport_size({"width": 1700, "height": 950})
        page.wait_for_timeout(500)

        # 12. 켜고 끄는 시간 — 「모두 고르기」(표시 클래스 + 스타일 다시 계산 + 꼬리표) · 풀기 · 다시 그리기
        ms = page.evaluate("""([t, l]) => { const doc = document.getElementById('doc'), force = () => { void doc.offsetHeight; getComputedStyle(doc.querySelector('.para')).opacity; };
          olmPickChange(t, l, (s) => s.clear()); force();
          const t0 = performance.now(); olmPickChange(t, l, (s, others) => { for (const g of others) s.add(g.key); }); force(); const on = performance.now() - t0;
          const n = document.querySelectorAll('#doc .para.fmt-hit').length, tags = document.querySelectorAll('.sheet > .fm-tag').length;
          const t1 = performance.now(); fmtFocusDraw(); force(); const again = performance.now() - t1;
          const t2 = performance.now(); olmPickChange(t, l, (s) => s.clear()); force(); const off = performance.now() - t2;
          return { on: Math.round(on), again: Math.round(again), off: Math.round(off), hit: n, tags, paras: doc.querySelectorAll('.para[data-id]').length }; }""", [A[0], A[1]])
        print(f"INFO 모두 고르기 {ms['on']}ms · 다시 그리기 {ms['again']}ms · 풀기 {ms['off']}ms(또렷한 문단 요소 {ms['hit']} · 꼬리표 {ms['tags']} · 문단 요소 {ms['paras']}개)", flush=True)
        check("켜고 끄는 데 각각 1.5초 안 · 다시 그리기 0.5초 안(문단 요소 수천 개)", ms["on"] < 1500 and ms["off"] < 1500 and ms["again"] < 500 and ms["hit"] > 0 and ms["tags"] > 0, ms)

        # 11. 다른 문서 → 고르기도 표시도 없다
        page.evaluate("([t, l, k]) => olmPickChange(t, l, (s) => s.add(k))", [A[0], A[1], k1["key"]])
        safe(lambda: shown_is(k1["paras"]), "11a")
        page.evaluate("(id) => { openWork(id); }", docx)
        page.wait_for_function("(id) => state.id === id && !document.getElementById('fileInfo').hidden && !!document.querySelector('#doc .para')", arg=docx, timeout=60000)
        page.wait_for_timeout(800)
        v = page.evaluate(VIEW)
        check("11. 다른 문서를 열면 고르기도 본문 표시도 없다(새 문서가 흐리지 않다 · 이름 줄 설명 없음 · 살펴보는 갈래도 없음)", not v["on"] and not v["hit"] and not v["key"]["shown"] and not v["kind"] and page.evaluate(PICKS) == {}
              and page.evaluate("() => { olmOpenNow(); return OLM.look === null && OLM.chkAt.size === 0 && OLM.full.size === 0; }"), [v["on"], v["kind"], page.evaluate(PICKS)])
        page.evaluate("(id) => { openWork(id); }", doc)
        page.wait_for_function("(id) => state.id === id && !!document.querySelector('#doc .para[data-id=p970]')", arg=doc, timeout=60000)
        page.wait_for_timeout(800)
        v = page.evaluate(VIEW)
        check("먼저 문서로 돌아와도 고르기·표시는 비어 있다(문서마다)", not v["on"] and not v["kind"] and page.evaluate(PICKS) == {}, [v["on"], page.evaluate(PICKS)])
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

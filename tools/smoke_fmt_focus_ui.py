"""서식 라벨만 또렷이(spec_헤딩_추출 ② §7 「서식 라벨만 또렷이」 — app/static/fmt_focus.js·css · app.js tplMarksDraw 의 .tm-f) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

연구개발계획서 양식(hwpx — 1·2단계를 끝점으로 돌림)을 「서식 라벨」 표시를 켠 채 연다:
- 누르기 전: 흐린 문단 없음 · 이름 줄 설명 없음 · 여백의 서식 라벨은 라벨마다 눌리는 글(.tm-f).
- 라벨을 누르면: 그 라벨의 문단(1단계 결과 — 끝점으로 견줌)만 그대로(opacity 1), 나머지 문단은 흐리게(0.42 — 감추지 않음) · 누른 라벨에 눌림 ·
  이름 줄에 「S…」 칩 + 「이 서식만 또렷이」 + 「문단 N개」 + 「목록」 + 「끄기」(줄 높이 35px · 넘침 없음).
- 다른 라벨을 누르면 그 라벨로 바뀜 · 같은 라벨을 다시 누르면 풀림(흐림·눌림·설명 모두).
- 「목록」 = 그 라벨의 문단 목록(2열) — 또렷이는 그대로 · 「끄기」 = 풀림.
- 쪽을 다시 나눠도(paginate) 그대로 · 글을 쓰려고 커서를 둔 문단은 흐리지 않음.
- 좁은 폭(2열을 연 1100px · 700px)에서 줄 높이 35px · 넘침 없음 · 칩과 단추는 남음.
- 다른 문서(docx)로 바꿔 열면 풀림(새 문서가 흐리지 않음).
- 켜는 데 걸린 시간(문단 요소 수 · ms)을 찍는다 · 콘솔 오류 없음.

템플릿만 또렷이(같은 사양 절 — 2026-11-15 「템플릿도 클릭하면 … 바탕면에 … 연하게 … 여백이 문제면 여백만 색상을 주고 차이가 있음을 표기」):
- 고른 문단(서식·템플릿 모두)에 옅은 파란 바탕.
- 여백의 템플릿 표기 「T1 L2」(.tm-t)를 누르면 그 템플릿·레벨의 줄(개요 오버레이 — 끝점으로 견줌)만 그대로 · 「템플릿 관계」 열은 바로 안 열림 · 표기에 눌림 ·
  이름 줄에 「T1 L2」 칩 + 「이 템플릿만 또렷이」 + 「줄 N개」 + 「여백 다름 n」·「서식 다름 n」 + 「템플릿 관계」 + 「끄기」.
- 대표와 여백이 다른 줄은 그 쪽 여백 자리만 주황(--fm-*) · 쪽 오른쪽 여백에 표(「≠ 2번째 줄」 — 도움말에 「지금 … → 대표 …」) · 여백이 아닌 값만 다른 줄은 표만.
- 표를 누르면 「템플릿 관계」 의 그 레벨·그 줄의 갈래 · 「여백 다름 n」 을 누르면 그런 줄로 차례로 · 「템플릿 관계」 단추.
- 갈래를 맞추면(문서가 바뀜) 표시가 줄고 실행 취소면 되돌아옴 · 쪽을 다시 나눠도 그대로 · 서식 라벨을 누르면 서식으로 바뀜(표·주황 없음) · 같은 표기를 다시 누르면 풀림.
- 목록이 잘린 갈래(30줄 넘음)가 하나인 레벨 · 둘 이상인 레벨(그 슬롯만 줄 전부로 다시 읽음)도 줄 수가 맞음.

자리 옮기기(같은 사양 절 — 2026-11-15 「마우스 휠을 내리면 다른 … 템플릿으로 이동 … 윗쪽에 몇개 아랫쪽에 몇개 있는지 표기」):
- 또렷이를 켜면 문서 창 오른쪽 위·아래에 알약 「▲ 위 n곳」·「▼ 아래 n곳」 — 창 밖에 남은 곳(붙어 있는 줄 묶음) 수, 스크롤을 따라 바뀜 · 0 이면 흐림.
- 문서에서 휠을 내리면 쪽 넘기기 대신 아직 안 보인 다음 곳으로(그 곳의 위끝이 창 위쪽에 · 잠깐 진하게) — 끝까지 굴리면 모든 곳을 거침 · 더 없으면 제자리(알약 까딱) · 휠을 올리면 앞 곳.
- 알약을 눌러도 옮김 · 이름 줄 「휠 이동」 을 끄면 휠은 평소대로(기억) · 서식 라벨에서도 같음 · 또렷이를 끄면 알약도 사라짐.

    python -X utf8 tools/smoke_fmt_focus_ui.py <출력 폴더> [--port 18472]
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
ap.add_argument("--port", type=int, default=18472)
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


def label_ids(doc, label):  # 그 라벨의 문단 id 전부(1단계 결과) — 화면이 읽는 것과 같은 끝점
    ids, off = [], 0
    while True:
        r = requests.get(f"{base}/api/docs/{doc}/headings/paras", params={"fmt": label, "offset": off, "limit": 500}, timeout=60).json()
        ids += [p["id"] for p in r["items"]]
        off += len(r["items"])
        if not r["items"] or off >= r["total"]:
            return ids, r["total"]


# 문서 · 여백 라벨 · 이름 줄 설명의 지금 모습
VIEW = """() => { const doc = document.getElementById('doc'), row = document.getElementById('fileInfo'), key = document.getElementById('fmtKey'), vis = (e) => !!e && e.getClientRects().length > 0, rr = row.getBoundingClientRect();
  const inside = (e) => { const r = e.getBoundingClientRect(); return r.left >= rr.left - 1 && r.right <= rr.right + 1 && r.top >= rr.top - 1 && r.bottom <= rr.bottom + 1; };
  const paras = [...doc.querySelectorAll('.para[data-id]')], hits = paras.filter((p) => p.classList.contains('fmt-hit')), miss = paras.filter((p) => !p.classList.contains('fmt-hit'));
  const op = (p) => (p ? +getComputedStyle(p).opacity : null), parts = [...key.querySelectorAll('.fm-key-chip, .fm-key-btn')];
  return { on: doc.classList.contains('fmt-focus'), paras: paras.length, hit: [...new Set(hits.map((p) => p.dataset.id))].sort(), hitOp: [...new Set(hits.map(op))], missOp: [...new Set(miss.slice(0, 400).map(op))],
    missShown: miss.slice(0, 50).every((p) => getComputedStyle(p).display !== 'none' && getComputedStyle(p).visibility !== 'hidden'),
    marks: [...new Set([...document.querySelectorAll('.tpl-mark .tm-f.on')].map((b) => b.dataset.fmt))], pressed: [...new Set([...document.querySelectorAll('.tpl-mark .tm-f[aria-pressed=true]')].map((b) => b.dataset.fmt))],
    outer: document.querySelectorAll('.tpl-mark.fm-on').length,
    key: { shown: vis(key), chip: (key.querySelector('.fm-key-chip') || {}).textContent || '', text: vis(key.querySelector('.fm-key-text')), count: (key.querySelector('.fm-key-count') || {}).textContent || '',
      countShown: vis(key.querySelector('.fm-key-count')), btns: [...key.querySelectorAll('button')].map((b) => b.textContent), inside: parts.length > 0 && parts.every((e) => vis(e) && inside(e)),
      h: Math.max(0, ...parts.map((e) => Math.round(e.getBoundingClientRect().height))), next: (key.nextElementSibling || {}).id || (key.nextElementSibling || {}).className || '' },
    rowH: Math.round(rr.height), over: row.scrollWidth > row.clientWidth + 1 }; }"""
# 화면에 보이는 여백 라벨 가운데 그 라벨(없으면 아무 라벨)의 글 하나를 누른다 -> 누른 라벨
CLICK = """(want) => { const all = [...document.querySelectorAll('.tpl-mark .tm-f')]; const b = all.find((x) => (want ? x.dataset.fmt === want : true)); if (!b) return null;
  b.scrollIntoView({ block: 'center' }); b.click(); return b.dataset.fmt; }"""
LABELS = "() => { const c = new Map(); for (const b of document.querySelectorAll('.tpl-mark .tm-f')) if (b.dataset.fmt !== '≠' && b.dataset.fmt !== '≈') c.set(b.dataset.fmt, (c.get(b.dataset.fmt) || 0) + 1); return [...c].sort((a, b) => b[1] - a[1]); }"
TINT = "rgba(36, 88, 214, 0.1)"  # 고른 문단의 옅은 파란 바탕(fmt_focus.css --fm-tint)
MARGIN_KEYS = {"line1Mm", "line2Mm", "indentRightMm", "spaceBeforePt", "spaceAfterPt"}  # 여백 값(fmt_focus.js FM_SIDE)
BG = "() => [...new Set([...document.querySelectorAll('#doc .para.fmt-hit')].map((p) => getComputedStyle(p).backgroundColor))]"
# 템플릿만 또렷이의 지금 모습 — 문단 · 대표와 다른 줄(.fm-d · 칠한 여백) · 오른쪽 여백의 표 · 여백 표기의 눌림 · 이름 줄 설명 · 2열
TVIEW = """() => { const doc = document.getElementById('doc'), row = document.getElementById('fileInfo'), key = document.getElementById('fmtKey'), col = document.getElementById('headsDlg'), uniq = (a) => [...new Set(a)];
  const vis = (e) => !!e && e.getClientRects().length > 0, rr = row.getBoundingClientRect(), txt = (s) => (key.querySelector(s) || {}).textContent || '';
  const paras = [...doc.querySelectorAll('.para[data-id]')], hits = paras.filter((p) => p.classList.contains('fmt-hit')), miss = paras.filter((p) => !p.classList.contains('fmt-hit')), ds = [...doc.querySelectorAll('.para.fm-d')];
  const tags = [...document.querySelectorAll('.sheet > .fm-tag')].map((t) => { const s = t.closest('.sheet').getBoundingClientRect(), r = t.getBoundingClientRect(), p = doc.querySelector(`.para[data-id="${t.dataset.para}"]`), pr = p.getBoundingClientRect();
    return { para: t.dataset.para, text: t.textContent, mg: t.classList.contains('mg'), inMargin: r.left >= pr.right - 1 && r.right <= s.right + 2 && r.width > 20, dy: Math.round(r.top - pr.top), h: Math.round(r.height), tip: t.title, same: t.closest('.sheet') === p.closest('.sheet') }; });
  const parts = [...key.querySelectorAll('.fm-key-chip, .fm-key-btn, .fm-key-leg')], inside = (e) => { const r = e.getBoundingClientRect(); return r.left >= rr.left - 1 && r.right <= rr.right + 1 && r.top >= rr.top - 1 && r.bottom <= rr.bottom + 1; };
  return { kind: FMF.kind, label: FMF.label, on: doc.classList.contains('fmt-focus'), hit: uniq(hits.map((p) => p.dataset.id)).sort(), hitOp: uniq(hits.map((p) => +getComputedStyle(p).opacity)), missOp: uniq(miss.slice(0, 400).map((p) => +getComputedStyle(p).opacity)),
    hitBg: uniq(hits.map((p) => getComputedStyle(p).backgroundColor)), diff: uniq(ds.map((p) => p.dataset.id)).sort(), size: Object.fromEntries(ds.map((p) => [p.dataset.id, getComputedStyle(p).backgroundSize])),
    tOn: uniq([...document.querySelectorAll('.tpl-mark .tm-t.on')].map((b) => b.dataset.tpl + '|' + b.dataset.level)), tPressed: document.querySelectorAll('.tpl-mark .tm-t[aria-pressed=true]').length,
    fOn: document.querySelectorAll('.tpl-mark .tm-f.on').length, outer: document.querySelectorAll('.tpl-mark.fm-on').length, tags, sum: FMF.sum, at: FMF.at,
    key: { shown: vis(key), chip: txt('.fm-key-chip'), text: txt('.fm-key-text'), count: txt('.fm-key-count'), note: txt('.fm-key-note'), legs: [...key.querySelectorAll('.fm-key-leg')].map((b) => b.textContent),
      btns: [...key.querySelectorAll('.fm-key-btn')].map((b) => b.textContent), inside: parts.length > 0 && parts.every((e) => vis(e) && inside(e)), h: Math.max(0, ...parts.map((e) => Math.round(e.getBoundingClientRect().height))) },
    col: col.hidden ? '' : col.dataset.kind, rowH: Math.round(rr.height), over: row.scrollWidth > row.clientWidth + 1 }; }"""
# 여백의 템플릿 표기(.tm-t) 가운데 그 템플릿·레벨의 것 하나를 누른다 -> 누른 글
CLICK_T = """([t, l]) => { const b = [...document.querySelectorAll('.tpl-mark .tm-t')].find((x) => x.dataset.tpl === t && +x.dataset.level === l); if (!b) return null;
  b.scrollIntoView({ block: 'center' }); b.click(); return b.textContent; }"""
# 자리 옮기기의 지금 모습 — 알약 · FMN.count 와, 화면에서 따로 센 것(want: 붙어 있는 .fmt-hit 묶음 가운데 창 위·아래에 있는 수 · seen: 창에 보이는 묶음 · tops: 묶음 위끝의 창 안 자리)
NAV = """() => { const sc = document.getElementById('scroller'), vw = document.getElementById('viewer').getBoundingClientRect(), sr = sc.getBoundingClientRect(), E = 8, vis = (e) => !!e && e.getClientRects().length > 0;
  const groups = [], ps = [...document.querySelectorAll('#doc .para[data-id]')], empty = (p) => !p.dataset.label && !p.textContent.trim() && !p.querySelector('.pic-in');
  const skip = ps.some((p) => p.classList.contains('fmt-hit') && !empty(p)); let g = null;  // 고른 것 가운데 빈 줄은 곳이 아니다(글이 있는 고른 문단이 있을 때 — fmt_focus.js fmNavStops)
  for (const p of ps) {
    if (p.classList.contains('fmt-hit') && !(skip && empty(p))) { const r = p.getBoundingClientRect(); if (!r.width && !r.height) continue;
      if (g) { g.top = Math.min(g.top, r.top); g.bottom = Math.max(g.bottom, r.bottom); } else { g = { top: r.top, bottom: r.bottom, id: p.dataset.id }; groups.push(g); } }
    else if (g && p.textContent.trim()) g = null; }
  groups.sort((a, b) => a.top - b.top);
  const top = sr.top, bot = sr.top + sc.clientHeight;
  const pill = (b) => { if (!b) return null; const r = b.getBoundingClientRect();
    return { shown: vis(b), text: b.textContent, none: b.classList.contains('none'), bump: b.classList.contains('bump'), tip: b.title, h: Math.round(r.height),
      inside: r.left >= vw.left && r.right <= vw.right && r.top >= vw.top && r.bottom <= vw.bottom, right: Math.round(vw.right - r.right) }; };
  const wb = document.querySelector('#fmtKey .fm-key-wheel');
  return { y: Math.round(sc.scrollTop), h: sc.clientHeight, max: sc.scrollHeight - sc.clientHeight, count: FMN.count, to: FMN.to, at: FMN.at,
    want: { all: groups.length, up: groups.filter((x) => x.bottom <= top + E).length, down: groups.filter((x) => x.top >= bot - E).length },
    ids: groups.map((x) => x.id), seen: groups.filter((x) => x.bottom > top + E && x.top < bot - E).map((x) => x.id), firstDown: (groups.find((x) => x.top >= bot - E) || {}).id || null,
    tops: groups.map((x) => Math.round(x.top - top)), land: [...new Set([...document.querySelectorAll('#doc .para.fm-land')].map((p) => p.dataset.id))],
    up: pill(document.querySelector('#viewer > .fm-nav.up')), down: pill(document.querySelector('#viewer > .fm-nav.down')),
    wheelBtn: wb ? { shown: vis(wb), pressed: wb.getAttribute('aria-pressed') } : null }; }"""
# 스크롤이 멈출 때까지(부드러운 스크롤) + 두 프레임(알약은 프레임에 한 번 다시 그린다)
SETTLE = """async () => { const sc = document.getElementById('scroller'); let a = -1, same = 0; const t0 = performance.now();
  while (same < 3 && performance.now() - t0 < 6000) { await new Promise((r) => setTimeout(r, 80)); if (Math.abs(sc.scrollTop - a) < 0.5) same += 1; else { same = 0; a = sc.scrollTop; } }
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))); return Math.round(sc.scrollTop); }"""


def wheel(page, dy):  # 문서 한가운데서 마우스 휠 한 칸 -> 멈춘 뒤의 모습
    x, y = page.evaluate("() => { const r = document.getElementById('scroller').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }")
    page.mouse.move(x, y)
    page.mouse.wheel(0, dy)
    page.wait_for_timeout(160)  # 휠 칸 사이 140ms
    page.evaluate(SETTLE)
    return page.evaluate(NAV)


def nav_ok(n):  # 알약의 수 = 화면에서 따로 센 수 · 글 「▲ 위 n곳」·「▼ 아래 n곳」 · 0 이면 흐림
    c, w = n["count"] or {}, n["want"]
    return bool(c.get("all") == w["all"] and c.get("up") == w["up"] and c.get("down") == w["down"] and n["up"] and n["down"] and n["up"]["shown"] and n["down"]["shown"]
                and n["up"]["text"] == f"▲ 위 {w['up']:,}곳" and n["down"]["text"] == f"▼ 아래 {w['down']:,}곳" and n["up"]["none"] == (w["up"] == 0) and n["down"]["none"] == (w["down"] == 0))


def nav_brief(n):
    return {k: n[k] for k in ("y", "max", "count", "want", "to")} | {"up": (n["up"] or {}).get("text"), "down": (n["down"] or {}).get("text")}


def slot_expect(doc, tid, lv):  # 그 템플릿·레벨의 줄(개요 오버레이) · 대표와 다른 줄(서식 갈래 — 그 슬롯만 줄 전부) — 화면이 읽는 것과 같은 끝점
    o = requests.get(f"{base}/api/docs/{doc}/outline", timeout=60).json()
    ids = sorted(p for p, x in o["lines"].items() if str(x["tpl"]) == str(tid) and int(x["level"]) == lv)
    v = requests.get(f"{base}/api/docs/{doc}/outline/formats", params={"tpl": tid, "level": lv}, timeout=60).json()["slots"][str(tid)][str(lv)]
    odd = [g for g in v["groups"] if not g["rep"] and g["diff"]]
    return {"ids": ids, "no": o["templates"][str(tid)]["no"], "rep": v["rep"], "groups": v["groups"], "diff": sorted(p for g in odd for p in g["paras"]),
            "margin": sorted(p for g in odd if any(x[0] in MARGIN_KEYS for x in g["diff"]) for p in g["paras"]),
            "other": sorted(p for g in odd if any(x[0] not in MARGIN_KEYS for x in g["diff"]) for p in g["paras"]),
            "only": {k: sorted(p for g in odd if [x[0] for x in g["diff"]] == [k] for p in g["paras"]) for k in ("line2Mm", "lineSpacingPct")},
            "near": {p for g in odd if g.get("near") for p in g["paras"]}}  # 대표와 오차 안인 갈래의 줄 — 표 기호 「≈」(아니면 「≠」: fmt_focus.js fmDiffInfo)


def tpl_is(page, tid, lv, margin=None):
    if tid is None:
        page.wait_for_function("() => !FMF.kind && !FMF.label && !document.getElementById('doc').classList.contains('fmt-focus')", timeout=30000)
    else:
        page.wait_for_function("([t, l, m]) => FMF.kind === 'tpl' && FMF.tpl === t && FMF.level === l && !!FMF.sum && (m == null || FMF.sum.margin === m) && document.getElementById('doc').classList.contains('fmt-focus')",
                               arg=[str(tid), lv, margin], timeout=30000)
    page.wait_for_timeout(200)


def focus_is(page, label, total=None):
    if label:
        page.wait_for_function("([l, n]) => FMF.label === l && !!FMF.ids && (n == null || FMF.total === n) && document.getElementById('doc').classList.contains('fmt-focus')", arg=[label, total], timeout=30000)
    else:
        page.wait_for_function("() => !FMF.label && !document.getElementById('doc').classList.contains('fmt-focus')", timeout=30000)
    page.wait_for_timeout(150)


def main():
    wait_server()
    plan = upload("연구개발계획서_양식.hwpx")
    run_stage(plan, 1)
    run_stage(plan, 2)
    docx = upload("기술수요조사서.docx")
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1500, "height": 950}, device_scale_factor=1)
        page.add_init_script("try { localStorage.setItem('nfm.headsMarksFmt', 'on'); } catch (e) {}")  # 「서식 라벨」 표시를 켠 채(기본은 끔)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/#w={plan}")
        page.wait_for_selector("#doc .para", timeout=60000)
        page.wait_for_function("() => document.querySelectorAll('.tpl-mark .tm-f').length > 20", timeout=60000)
        page.wait_for_timeout(500)

        v, labels = page.evaluate(VIEW), page.evaluate(LABELS)
        check("누르기 전 — 흐린 문단 없음 · 이름 줄 설명 없음 · 여백의 서식 라벨은 라벨마다 눌리는 글", not v["on"] and not v["hit"] and v["missOp"] == [1] and not v["key"]["shown"] and not v["marks"]
              and len(labels) >= 2 and all(l.startswith("S") for l, _ in labels) and v["rowH"] == 35 and v["key"]["next"] == "document-mode", [v["key"], labels[:6]])  # 다음 = 「편집 중」(2026-11-19 — 그 사이에 있던 색 설명 #zonesKey · #divKey 는 문서 위에 떠 있는 상자로 나갔다: key_float.js)
        first, second = labels[0][0], labels[1][0]
        want, total = label_ids(plan, first)

        # 켜기
        t0 = time.time()
        got = page.evaluate(CLICK, first)
        focus_is(page, first, total)
        took = time.time() - t0
        v = page.evaluate(VIEW)
        dom = sorted(set(page.evaluate("(ids) => ids.filter((i) => !!document.querySelector(`#doc .para[data-id=\"${i}\"]`))", want)))
        check(f"라벨 「{first}」 을 누르면 그 라벨의 문단({total}개 — 1단계 결과)만 그대로 · 나머지 문단은 흐리게(0.42 — 감추지 않음)", got == first and v["on"] and v["hit"] == dom and len(dom) > 0
              and v["hitOp"] == [1] and v["missOp"] == [0.42] and v["missShown"] and len(dom) < v["paras"], [got, len(dom), len(v["hit"]), v["hitOp"], v["missOp"], v["paras"]])
        check("누른 라벨에 눌림(같은 라벨의 여백 글 모두 · 다른 라벨은 아님) · 그 글이 든 표에 파란 테두리(.fm-on)", v["marks"] == [first] and v["pressed"] == [first] and v["outer"] > 0, [v["marks"], v["pressed"], v["outer"]])
        bg = page.evaluate(BG)
        check("고른 서식의 문단에 옅은 파란 바탕(글은 그대로)", bg == [TINT], bg)
        k = v["key"]
        check("이름 줄 설명 — 「S…」 칩 · 「이 서식만 또렷이」 · 「문단 N개」 · 「휠 이동」 · 「목록」 · 「끄기」 · 조작 28px 이하 · 줄 높이 35px · 넘침 없음",
              k["shown"] and k["chip"] == first and k["text"] and k["count"] == f"문단 {total:,}개" and k["btns"] == ["휠 이동", "목록", "끄기"] and k["inside"] and k["h"] <= 28 and v["rowH"] == 35 and not v["over"], [k, v["rowH"], v["over"]])
        page.wait_for_timeout(200)
        page.screenshot(path=str(OUT / "01_focus.png"))
        hitbox = page.evaluate("() => { const p = document.querySelector('#doc .para.fmt-hit'); p.scrollIntoView({ block: 'center' }); return 1; }")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "02_focus_hit.png"))

        # 다른 라벨로 · 다시 눌러 풀기
        want2, total2 = label_ids(plan, second)
        page.evaluate(CLICK, second)
        focus_is(page, second, total2)
        v = page.evaluate(VIEW)
        dom2 = sorted(set(page.evaluate("(ids) => ids.filter((i) => !!document.querySelector(`#doc .para[data-id=\"${i}\"]`))", want2)))
        check(f"다른 라벨 「{second}」 을 누르면 그 라벨로 바뀜(문단 · 눌림 · 설명)", v["hit"] == dom2 and v["marks"] == [second] and v["key"]["chip"] == second and v["key"]["count"] == f"문단 {total2:,}개", [len(dom2), len(v["hit"]), v["marks"], v["key"]])
        page.evaluate(CLICK, second)
        focus_is(page, None)
        v = page.evaluate(VIEW)
        check("같은 라벨을 다시 누르면 풀림 — 흐림·눌림·설명 모두", not v["on"] and not v["hit"] and v["missOp"] == [1] and not v["marks"] and not v["outer"] and not v["key"]["shown"] and v["rowH"] == 35, [v["on"], len(v["hit"]), v["missOp"], v["outer"], v["key"]])

        # 「목록」 · 「끄기」
        page.evaluate(CLICK, first)
        focus_is(page, first, total)
        page.click("#fmtKey .fm-key-list")
        page.wait_for_function("() => { const c = document.getElementById('headsDlg'); return !c.hidden && c.dataset.kind === 'paras' && !!document.querySelector('#headsDlgBody tr'); }", timeout=30000)
        page.wait_for_timeout(300)
        lst = page.evaluate("() => ({ fmt: heads.paras.fmt, foot: document.getElementById('headsDlgFoot').textContent, on: document.getElementById('doc').classList.contains('fmt-focus') })")
        v = page.evaluate(VIEW)
        check("「목록」 → 그 라벨의 문단 목록(2열) · 또렷이는 그대로 · 2열을 열어도 줄 높이 35px · 넘침 없음", lst["fmt"] == first and f"/ {total:,}" in lst["foot"] and lst["on"] and v["hit"] == dom and v["rowH"] == 35 and not v["over"] and v["key"]["inside"], [lst, v["rowH"], v["over"]])
        page.screenshot(path=str(OUT / "03_list.png"))

        # 좁은 폭 — 2열을 연 1100px · 닫고 700px
        page.set_viewport_size({"width": 1100, "height": 900})
        page.wait_for_timeout(500)
        v = page.evaluate(VIEW)
        check("1100px(2열 열림) — 줄 높이 35px · 넘침 없음 · 칩과 단추는 줄 안", v["rowH"] == 35 and not v["over"] and v["key"]["inside"] and v["key"]["chip"] == first, [v["rowH"], v["over"], v["key"]])
        page.screenshot(path=str(OUT / "04_narrow_1100.png"))
        page.click("#headsDlgClose")
        page.set_viewport_size({"width": 700, "height": 900})
        page.wait_for_timeout(500)
        v = page.evaluate(VIEW)
        check("700px — 줄 높이 35px · 넘침 없음 · 칩과 단추는 줄 안", v["rowH"] == 35 and not v["over"] and v["key"]["inside"], [v["rowH"], v["over"], v["key"]])
        page.set_viewport_size({"width": 1500, "height": 950})
        page.wait_for_timeout(500)

        # 쪽을 다시 나눠도 · 커서를 둔 문단
        page.evaluate("() => paginate()")
        page.wait_for_timeout(600)
        v = page.evaluate(VIEW)
        check("쪽을 다시 나눠도(paginate — 문단 요소가 새것) 그대로 — 문단 · 눌림 · 설명", v["on"] and v["hit"] == dom and v["hitOp"] == [1] and v["missOp"] == [0.42] and v["marks"] == [first] and v["key"]["chip"] == first, [len(v["hit"]), len(dom), v["missOp"], v["marks"]])
        ed = page.evaluate("""() => { const p = [...document.querySelectorAll('#doc .para[data-id]:not(.fmt-hit)')].find((x) => x.isContentEditable && x.textContent.trim().length > 4); if (!p) return null;
          p.scrollIntoView({ block: 'center' }); p.focus(); const a = +getComputedStyle(p).opacity; p.blur(); return [a, +getComputedStyle(p).opacity]; }""")
        check("커서를 둔(글을 쓰는) 문단은 흐리지 않음 — 벗어나면 다시 흐림", ed == [1, 0.42], ed)

        # 「끄기」
        page.click("#fmtKey .fm-key-off")
        focus_is(page, None)
        v = page.evaluate(VIEW)
        check("「끄기」 → 풀림", not v["on"] and not v["hit"] and v["missOp"] == [1] and not v["key"]["shown"] and not v["marks"], [v["on"], v["key"]])

        # 빈 줄이 든 서식 — 띠에 「S… · 빈 줄」 · 이름 줄 「빈 줄 n」(2026-11-17 사용자 「s82 … 휠을 내리고 올리는데 s82 가 보이질 않음」 — 그 서식의 문단 대부분이 빈 줄)
        empties, off = [], 0
        while True:  # 끝점은 한 번에 500개까지
            r_ = requests.get(f"{base}/api/docs/{plan}/headings/paras", params={"kind": "empty", "offset": off, "limit": 500}, timeout=60).json()
            empties += r_["items"]
            off += len(r_["items"])
            if not r_["items"] or off >= r_["total"]:
                break
        by_fmt, body_fmt = {}, {}  # 서식 → 빈 줄 id(모두 — 이름 줄 「빈 줄 n」) · 본문의 빈 줄 id(띠에 글이 붙는 것 — 표 칸은 뺀다)
        for p_ in empties:
            by_fmt.setdefault(p_["fmt"], []).append(p_["id"])
            if p_["area"] == "body":
                body_fmt.setdefault(p_["fmt"], []).append(p_["id"])
        bl = max(body_fmt, key=lambda k: len(body_fmt[k])) if body_fmt else None
        if bl:
            _, bl_total = label_ids(plan, bl)
            page.evaluate("(l) => fmtFocusOn(l)", bl)  # 빈 줄에는 여백 라벨이 없다 — 누르는 대신 같은 함수를 부른다
            focus_is(page, bl, bl_total)
            bv = page.evaluate("""(ids) => { const doc = document.getElementById('doc'), all = [...doc.querySelectorAll('.para.fmt-hit')], bs = all.filter((p) => p.classList.contains('fm-blank'));
              const blank = (p) => !p.dataset.label && !p.textContent.trim() && !p.querySelector('.pic-in') && !p.closest('td, th');
              const b = bs[0]; if (b) b.scrollIntoView({ block: 'center' });
              const want = ids.filter((i) => { const p = doc.querySelector(`.para[data-id="${i}"]`); return p && blank(p); });
              const bad = all.filter((p) => p.classList.contains('fm-blank') !== blank(p)).length, inCell = bs.filter((p) => p.closest('td, th')).length;
              const before = b ? getComputedStyle(b, '::before') : null;
              return { blanks: [...new Set(bs.map((p) => p.dataset.id))].sort(), want: [...new Set(want)].sort(), bad, inCell, content: before ? before.content : '', pos: before ? before.position : '',
                note: (document.querySelector('#fmtKey .fm-key-blank') || {}).textContent || '', count: (document.querySelector('#fmtKey .fm-key-count') || {}).textContent || '', id: b ? b.dataset.id : null,
                over: document.getElementById('fileInfo').scrollWidth > document.getElementById('fileInfo').clientWidth + 1 }; }""", body_fmt[bl])
            check(f"빈 줄이 든 서식 「{bl}」(문단 {bl_total}개 · 빈 줄 {len(by_fmt[bl])} · 본문 {len(body_fmt[bl])}) — 본문 빈 줄의 띠에 「{bl} · 빈 줄」(절대 위치 — 배치 안 바뀜) · 글이 있는 문단 · 표 칸엔 없음 · 이름 줄 「빈 줄 n」 · 넘침 없음",
                  bv["blanks"] and bv["want"] and set(bv["want"]) <= set(bv["blanks"]) and not bv["bad"] and not bv["inCell"] and bv["content"] == f'"{bl} · 빈 줄"' and bv["pos"] == "absolute"
                  and bv["note"] == f"빈 줄 {len(by_fmt[bl]):,}" and bv["count"] == f"문단 {bl_total:,}개" and not bv["over"], bv)
            page.wait_for_timeout(200)
            page.screenshot(path=str(OUT / "05b_blank.png"))
            fo = page.evaluate("""(pid) => { const p = document.querySelector(`#doc .para[data-id="${pid}"]`); p.focus(); const a = getComputedStyle(p, '::before').content; p.blur(); return [a, getComputedStyle(p, '::before').content]; }""", bv["id"])
            check("커서를 둔 빈 줄에는 「… · 빈 줄」 을 붙이지 않음(글을 쓰는 중) — 벗어나면 다시", fo[0] == "none" and fo[1] == f'"{bl} · 빈 줄"', fo)
            # 휠 이동은 빈 줄을 건너뜀(2026-11-17 사용자 「빈줄은 건너 띄자」) — 곳 = 글이 있는 고른 문단의 묶음만 · 띠 표시는 그대로
            page.evaluate("() => { document.getElementById('scroller').scrollTop = 0; }")
            page.evaluate(SETTLE)
            with_blank = page.evaluate("""() => { let g = 0, on = false; for (const p of document.querySelectorAll('#doc .para[data-id]')) {
              if (p.classList.contains('fmt-hit')) { if (!on) { g += 1; on = true; } } else if (on && p.textContent.trim()) on = false; } return g; }""")  # 빈 줄까지 곳으로 셌다면
            n1 = wheel(page, 100)
            solid = page.evaluate("(ids) => ids.map((i) => { const p = document.querySelector(`#doc .para[data-id=\"${i}\"]`); return !!p && (!!p.textContent.trim() || !!p.dataset.label); })", n1["land"])
            tips = [(n1[k] or {}).get("tip", "") for k in ("up", "down")]
            check(f"휠 이동은 빈 줄을 건너뜀 — 곳 {n1['want']['all']}(글이 있는 문단 묶음 — 빈 줄까지 세면 {with_blank}) · 휠 한 칸이 글이 있는 문단으로(.fm-land) · 알약 도움말 「빈 줄은 건너뜀」 · 빈 줄 띠는 그대로",
                  nav_ok(n1) and 0 < n1["want"]["all"] < with_blank and solid and all(solid) and n1["y"] > 0 and any("빈 줄은 건너뜀" in t for t in tips)
                  and page.evaluate("() => document.querySelectorAll('#doc .para.fm-blank').length") > 0, [nav_brief(n1), with_blank, n1["land"], solid, tips])
            page.click("#fmtKey .fm-key-off")
            focus_is(page, None)
            gone = page.evaluate("() => [document.querySelectorAll('#doc .para.fm-blank').length, document.getElementById('doc').style.getPropertyValue('--fm-blank-txt')]")
            check("「끄기」 → 빈 줄 표시도 걷힘", gone == [0, ""], gone)
        else:
            check("빈 줄이 든 서식이 양식에 있음(검사 자료)", False, "kind=empty 문단 없음")

        # ---- 템플릿만 또렷이 — 「T1 L2」(양식의 「N-N.」 줄 26개: 대표 13 · 여백이 다른 줄 · 줄 간격만 다른 줄이 섞여 있다)
        in_dom = "(ids) => ids.filter((i) => !!document.querySelector(`#doc .para[data-id=\"${i}\"]`))"
        ex = slot_expect(plan, 1, 2)
        dom_t = sorted(set(page.evaluate(in_dom, ex["ids"])))
        m1, o1 = ex["only"]["line2Mm"][0], ex["only"]["lineSpacingPct"][0]  # 여백(2번째 줄)만 다른 줄 · 줄 간격만 다른 줄
        got = page.evaluate(CLICK_T, ["1", 2])
        tpl_is(page, 1, 2)
        v = page.evaluate(TVIEW)
        check(f"템플릿 표기 「T1 L2」 를 누르면 그 템플릿·레벨의 줄({len(ex['ids'])}개 — 개요 오버레이)만 그대로 + 옅은 파란 바탕 · 나머지는 흐리게 · 「템플릿 관계」 열은 바로 안 열림",
              bool(got) and got.startswith("T1 L2") and v["kind"] == "tpl" and v["hit"] == dom_t and len(dom_t) == len(ex["ids"]) > 0 and v["hitOp"] == [1] and v["missOp"] == [0.42] and v["hitBg"] == [TINT] and v["col"] != "templates",
              [got, v["kind"], len(v["hit"]), len(dom_t), len(ex["ids"]), v["hitOp"], v["missOp"], v["hitBg"], v["col"]])
        check("고른 표기에 눌림(.tm-t — 그 템플릿·레벨만) · 그 표에 파란 테두리 · 서식 라벨의 눌림은 없음", v["tOn"] == ["1|2"] and v["tPressed"] > 0 and v["outer"] > 0 and v["fOn"] == 0, [v["tOn"], v["tPressed"], v["outer"], v["fOn"]])
        k = v["key"]
        check("이름 줄 설명 — 「T1 L2」 칩 · 「이 템플릿만 또렷이」 · 「줄 N개」 · 「여백 다름 n」·「서식 다름 n」 · 「템플릿 관계」 · 「끄기」 · 조작 28px 이하 · 줄 높이 35px · 넘침 없음",
              k["shown"] and k["chip"] == "T1 L2" and k["text"] == "이 템플릿만 또렷이" and k["count"] == f"줄 {len(ex['ids'])}개" and k["legs"] == [f"여백 다름{len(ex['margin'])}", f"서식 다름{len(ex['other'])}"]
              and k["btns"] == ["템플릿 관계", "끄기"] and k["inside"] and k["h"] <= 28 and v["rowH"] == 35 and not v["over"], [k, v["rowH"], v["over"], len(ex["margin"]), len(ex["other"])])
        s = v["sum"]
        check("대표와 다른 줄(.fm-d) = 서식 갈래에서 대표가 아닌 갈래의 줄 · 줄 수 요약(같음·여백·서식)", v["diff"] == ex["diff"] and len(ex["diff"]) > 0 and s["margin"] == len(ex["margin"]) > 0 and s["other"] == len(ex["other"]) > 0
              and s["same"] == len(ex["ids"]) - len(ex["diff"]) and s["unknown"] == 0 and not s["norep"], [v["diff"], ex["diff"], s])
        zero = "0px 100%, 0px 100%, 100% 0px, 100% 0px"
        sz = v["size"]
        check("여백(2번째 줄)이 다른 줄 — 왼쪽 여백 자리만 주황(폭 > 0 · 다른 쪽은 0) · 줄 간격만 다른 줄은 칠하지 않음",
              sz.get(m1, zero) != zero and sz[m1].endswith(" 100%, 0px 100%, 100% 0px, 100% 0px") and not sz[m1].startswith("0px") and sz.get(o1) == zero, [m1, sz.get(m1), o1, sz.get(o1)])
        tg = {t["para"]: t for t in v["tags"]}
        sym = lambda p: "≈" if p in ex["near"] else "≠"  # noqa: E731 — 표의 기호: 대표와 오차 안인 갈래는 「≈」(서버 갈래의 near · 여백 서식 라벨과 같은 기준)
        check(f"대표와 다른 줄마다 쪽 오른쪽 여백에 표(그 줄 높이 · 여백 안) — 「{sym(m1)} 2번째 줄」(주황 띠 · 도움말에 기호의 뜻 + 「지금 … → 대표 …」) · 「{sym(o1)} 줄 간격」"
              f" · 모든 표의 기호 = 갈래의 near(≈ {len(ex['near'])}줄)",
              sorted(tg) == v["diff"] and all(t["inMargin"] and t["same"] and -2 <= t["dy"] <= 30 and t["h"] <= 20 for t in v["tags"]) and tg[m1]["text"] == f"{sym(m1)} 2번째 줄" and tg[m1]["mg"]
              and tg[o1]["text"] == f"{sym(o1)} 줄 간격" and not tg[o1]["mg"] and "2번째 줄: 지금 " in tg[m1]["tip"] and " → 대표 " in tg[m1]["tip"]
              and all(t["text"].startswith(sym(p) + " ") and t["tip"].split("\n")[1].startswith(sym(p) + " — ") for p, t in tg.items()),
              [sorted(tg), [t for t in v["tags"] if not t["inMargin"]][:2], tg.get(m1), tg.get(o1), sorted(ex["near"])[:5]])
        page.evaluate("(pid) => document.querySelector(`#doc .para[data-id=\"${pid}\"]`).scrollIntoView({ block: 'center' })", m1)
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "06_tpl_margin.png"))
        sp = next(((p, [x[0] for x in g["diff"]]) for g in ex["groups"] if not g["rep"] and any(x[0] in ("spaceBeforePt", "spaceAfterPt") for x in g["diff"]) for p in g["paras"]), None)
        if sp:  # 위·아래 간격이 다른 줄 — 그 쪽(위·아래) 자리만 칠한다
            hs = [x.strip().split(" ")[-1] for x in sz.get(sp[0], zero).split(",")]  # 층마다 높이: 왼 · 오른 · 위 · 아래
            want_t, want_b = "spaceBeforePt" in sp[1], "spaceAfterPt" in sp[1]
            check(f"위·아래 간격이 다른 줄({sp[0]} — {'·'.join(sp[1])}) — 다른 쪽(위·아래)의 간격 자리만 주황(높이 > 0) · 표에 주황 띠", (hs[2] != "0px") == want_t and (hs[3] != "0px") == want_b and tg[sp[0]]["mg"], [sp, sz.get(sp[0]), tg.get(sp[0])])
            page.evaluate("(pid) => document.querySelector(`#doc .para[data-id=\"${pid}\"]`).scrollIntoView({ block: 'center' })", sp[0])
            page.wait_for_timeout(300)
            page.screenshot(path=str(OUT / "06b_tpl_space.png"))
            print(f"INFO 위·아래 간격이 다른 줄 {sp[0]} — 칠한 크기 {sz.get(sp[0])} · 표 「{tg[sp[0]]['text']}」", flush=True)

        # 표 → 「템플릿 관계」 의 그 줄의 갈래 · 「여백 다름 n」 → 그런 줄로 차례로 · 「템플릿 관계」 단추
        page.evaluate("(pid) => document.querySelector(`.sheet > .fm-tag[data-para=\"${pid}\"]`).click()", m1)
        page.wait_for_selector("#headsDlg[data-kind=templates] .olm.sel", timeout=20000)
        page.wait_for_function("() => document.querySelector('#headsDlgBody .olm.sel .olm-g.sel')", timeout=20000)
        g = page.evaluate("""(pid) => { const r = document.querySelector('#headsDlgBody .olm.sel'), g = r.querySelector('.olm-g.sel');
          return { tpl: r.dataset.tpl, level: r.dataset.level, has: (g._paras || []).includes(pid), diff: (g.querySelector('.olm-diff') || {}).textContent || '' }; }""", m1)
        v = page.evaluate(TVIEW)
        check("표를 누르면 「템플릿 관계」 의 T1 L2 · 그 줄의 갈래(「2번째 줄: 지금 … → 대표 …」) — 또렷이는 그대로 · 2열을 열어도 줄 높이 35px · 넘침 없음",
              g["tpl"] == "1" and g["level"] == "2" and g["has"] and "2번째 줄: 지금 " in g["diff"] and v["kind"] == "tpl" and v["hit"] == dom_t and v["rowH"] == 35 and not v["over"] and v["key"]["inside"], [g, v["rowH"], v["over"], v["key"]])
        page.screenshot(path=str(OUT / "07_tpl_rel.png"))
        order = page.evaluate("(ids) => [...document.querySelectorAll('#doc .para.fm-d[data-id]')].map((p) => p.dataset.id).filter((x, i, a) => a.indexOf(x) === i && ids.includes(x))", ex["margin"])
        seen = []
        for _ in range(2):
            page.click("#fmtKey .fm-key-leg.mg")
            seen.append(page.evaluate("() => FMF.at.margin"))
        check("「여백 다름 n」 을 누르면 여백이 다른 줄로 차례로(문서 순)", seen == order[:2] and len(order) == len(ex["margin"]), [seen, order])
        page.click("#headsDlgClose")
        page.wait_for_timeout(300)
        page.click("#fmtKey .fm-key-rel")
        page.wait_for_selector("#headsDlg[data-kind=templates] .olm[data-tpl=\"1\"][data-level=\"2\"]", timeout=20000)
        check("「템플릿 관계」 단추 → 템플릿 관계 열(T1 L2 의 서식 갈래 줄)", True)
        for w in (1100, 700):
            page.set_viewport_size({"width": w, "height": 900})
            page.wait_for_timeout(500)
            v = page.evaluate(TVIEW)
            check(f"{w}px(템플릿 설명) — 줄 높이 35px · 넘침 없음 · 칩과 단추는 줄 안", v["rowH"] == 35 and not v["over"] and v["key"]["inside"] and v["key"]["chip"] == "T1 L2", [v["rowH"], v["over"], v["key"]])
            if w == 1100:
                page.click("#headsDlgClose")
        page.set_viewport_size({"width": 1500, "height": 950})
        page.wait_for_timeout(500)

        # 갈래를 맞추면(문서가 바뀜) 표시가 줄고 · 실행 취소면 되돌아옴 · 쪽을 다시 나눠도 그대로
        n2 = len(ex["only"]["line2Mm"])
        rev0 = page.evaluate("() => state.serverRev")
        page.evaluate("(pid) => { olmMatch('1', 2, 0, [pid]); }", m1)
        page.wait_for_function("(r) => state.serverRev > r && !state.busy", arg=rev0, timeout=60000)
        # 맞추면 대표도 확정 서식(레터 뒤 묶음 빈칸 · 둘째 줄 = 글 시작 — spec_hwpx_웹편집 ② §8-8)이 된다 — 남은 갈래의 「대표와 다른 값」 은 새 대표 기준이라, 기대값을 맞춘 뒤의 서버 갈래에서 다시 읽는다
        ex2 = slot_expect(plan, 1, 2)
        tpl_is(page, 1, 2, len(ex2["margin"]))
        v = page.evaluate(TVIEW)
        left = ex2["diff"]
        check(f"「2번째 줄」 만 다른 갈래의 줄({m1})을 대표에 맞추면 그 줄의 주황·표가 사라짐(나머지는 그대로 — 화면 = 맞춘 뒤의 서버 갈래) · 설명의 줄 수도", m1 not in left and len(left) < len(ex["diff"])
              and v["diff"] == left and sorted(t["para"] for t in v["tags"]) == left and v["hit"] == dom_t
              and v["key"]["legs"][0] == f"여백 다름{len(ex2['margin'])}", [v["diff"], left, v["key"]["legs"]])
        page.click("#undoBtn")
        tpl_is(page, 1, 2, len(ex["margin"]))
        v = page.evaluate(TVIEW)
        check("실행 취소 → 다시 표시", v["diff"] == ex["diff"] and sorted(t["para"] for t in v["tags"]) == ex["diff"], [v["diff"], v["key"]["legs"]])
        page.evaluate("() => paginate()")
        page.wait_for_timeout(700)
        v = page.evaluate(TVIEW)
        check("쪽을 다시 나눠도(템플릿) 그대로 — 문단 · 주황 · 표 · 눌림", v["hit"] == dom_t and v["diff"] == ex["diff"] and sorted(t["para"] for t in v["tags"]) == ex["diff"] and all(t["inMargin"] for t in v["tags"]) and v["tOn"] == ["1|2"]
              and v["size"].get(m1, zero) != zero, [len(v["hit"]), v["diff"], len(v["tags"]), v["tOn"]])

        # 목록이 잘린 갈래 — 둘 이상이면 그 슬롯만 줄 전부로 다시 읽는다(화면이 기억한 갈래 목록을 일부러 잘라 본다) · 하나면 목록에 없는 줄은 그 갈래
        asked = []
        page.on("request", lambda r: asked.append(r.url) if "/outline/formats?" in r.url else None)
        cut = page.evaluate("""async () => { const v = OLM.data['1']['2']; let cut = 0;
          for (const g of v.groups) if (g.count > 1 && cut < 2) { g.more = g.count - 1; g.paras = g.paras.slice(0, 1); cut += 1; }
          await tplFocusDiff(); return { cut, sum: FMF.sum }; }""")
        check("30줄을 넘는 갈래가 둘 이상인 레벨 — 그 슬롯만 줄 전부로 다시 읽어(?tpl=&level=) 줄 수가 맞음(못 견줌 0)", cut["cut"] == 2 and any("tpl=1" in u and "level=2" in u for u in asked)
              and cut["sum"]["margin"] == len(ex["margin"]) and cut["sum"]["other"] == len(ex["other"]) and cut["sum"]["unknown"] == 0, [cut, asked])
        page.evaluate("async () => { await olmLoad(true); }")
        big = page.evaluate("() => { for (const [t, sl] of Object.entries(OLM.data)) for (const [l, v] of Object.entries(sl)) if (v.groups.filter((g) => g.more > 0).length === 1 && document.querySelector(`.tpl-mark .tm-t[data-tpl=\"${t}\"][data-level=\"${l}\"]`)) return [t, +l]; return null; }")
        if big:
            exb = slot_expect(plan, big[0], big[1])
            page.evaluate(CLICK_T, big)
            tpl_is(page, big[0], big[1])
            v = page.evaluate(TVIEW)
            check(f"30줄을 넘는 갈래가 하나인 레벨(T{exb['no']} L{big[1]} — {len(exb['ids'])}줄) — 목록에 없는 줄은 그 갈래로: 줄 수가 맞음", v["sum"]["same"] == len(exb["ids"]) - len(exb["diff"]) and v["sum"]["margin"] == len(exb["margin"])
                  and v["sum"]["other"] == len(exb["other"]) and v["sum"]["unknown"] == 0 and v["diff"] == sorted(set(exb["diff"]) & set(page.evaluate(in_dom, exb["ids"]))) and v["key"]["chip"] == f"T{exb['no']} L{big[1]}", [big, v["sum"], len(exb["diff"])])
        else:
            print("INFO 30줄을 넘는 갈래가 하나인 레벨이 화면에 없음 — 건너뜀", flush=True)

        # 서식 라벨로 바꿈 · 같은 표기를 다시 눌러 풀기
        page.evaluate(CLICK, first)
        focus_is(page, first, total)
        v = page.evaluate(TVIEW)
        check("템플릿을 고른 채 서식 라벨을 누르면 서식으로 바뀜 — 주황·표·템플릿 눌림 없음 · 설명은 서식 것", v["kind"] == "fmt" and v["hit"] == dom and not v["diff"] and not v["tags"] and not v["tOn"] and v["fOn"] > 0 and v["hitBg"] == [TINT]
              and v["key"]["chip"] == first and v["key"]["btns"] == ["목록", "끄기"] and not v["key"]["legs"], [v["kind"], len(v["hit"]), v["diff"], len(v["tags"]), v["tOn"], v["key"]])
        page.evaluate(CLICK_T, ["1", 2])
        tpl_is(page, 1, 2)
        page.evaluate(CLICK_T, ["1", 2])
        tpl_is(page, None, None)
        v = page.evaluate(TVIEW)
        check("같은 템플릿 표기를 다시 누르면 풀림 — 흐림·바탕·주황·표·눌림·설명 모두", not v["on"] and not v["hit"] and v["missOp"] == [1] and not v["diff"] and not v["tags"] and not v["tOn"] and not v["outer"] and not v["key"]["shown"]
              and page.evaluate("() => document.querySelectorAll('#doc .para[style*=\"--fm-\"]').length") == 0, [v["on"], len(v["hit"]), v["diff"], len(v["tags"]), v["key"]])

        # ---- 자리 옮기기 — 휠로 다음·앞 곳 · 창 위·아래에 남은 곳 수(「T1 L2」 — 제목 줄이 문서 곳곳에)
        page.evaluate(CLICK_T, ["1", 2])
        tpl_is(page, 1, 2)
        page.evaluate(SETTLE)
        n = page.evaluate(NAV)
        check("또렷이를 켜면 문서 창 오른쪽 위·아래에 알약 「▲ 위 n곳」·「▼ 아래 n곳」 — 창 밖에 남은 곳 수(붙어 있는 줄 묶음 · 화면에서 따로 센 것과 같음) · 창 안 · 높이 24px · 이름 줄 「휠 이동」 켜짐",
              nav_ok(n) and n["want"]["all"] > 3 and len(n["seen"]) > 0 and n["up"]["inside"] and n["down"]["inside"] and n["up"]["h"] == 24 and n["down"]["h"] == 24 and n["up"]["right"] < 60
              and bool(n["wheelBtn"]) and n["wheelBtn"]["shown"] and n["wheelBtn"]["pressed"] == "true", [nav_brief(n), n["up"], n["down"], n["wheelBtn"]])
        page.screenshot(path=str(OUT / "08_nav_on.png"))
        page.evaluate("() => { document.getElementById('scroller').scrollTop = 0; }")
        page.evaluate(SETTLE)
        n = page.evaluate(NAV)
        check("맨 위로 스크롤하면 수가 따라 바뀜 — 「▲ 위 0곳」(흐림) · 아래는 남은 곳", nav_ok(n) and n["want"]["up"] == 0 and n["up"]["none"] and n["want"]["down"] > 0 and "더 없습니다" in n["up"]["tip"] and "휠을 내리면" in n["down"]["tip"], [nav_brief(n), n["up"], n["down"]])
        pad, all_n = min(96, round(n["h"] * 0.18)), n["want"]["all"]
        target = n["firstDown"]
        m = wheel(page, 100)
        at = m["tops"][m["ids"].index(target)] if target in m["ids"] else None
        check("문서에서 휠을 한 칸 내리면 쪽 넘기기 대신 아직 안 보인 다음 곳으로 — 그 곳의 위끝이 창 위쪽(PAD)에 · 잠깐 진하게(.fm-land) · 「아래」 수가 줆",
              m["y"] > n["y"] and m["y"] == m["to"] and at is not None and (abs(at - pad) <= 3 or m["y"] >= m["max"] - 1) and target in m["land"] and nav_ok(m) and m["want"]["down"] < n["want"]["down"],
              [nav_brief(n), nav_brief(m), target, at, pad, m["land"]])
        page.wait_for_timeout(150)
        page.screenshot(path=str(OUT / "09_nav_wheel.png"))
        seen, steps, ok = set(n["seen"]) | set(m["seen"]), 1, True
        while m["want"]["down"] > 0 and steps < all_n + 5:
            prev, m = m, wheel(page, 100)
            steps += 1
            seen |= set(m["seen"])
            ok = ok and m["y"] > prev["y"] and nav_ok(m)
        check(f"끝까지 굴리면 모든 곳을 거침({all_n}곳 · 휠 {steps}칸) — 칸마다 아래로 · 수가 맞음 · 끝에 「▼ 아래 0곳」(흐림)", ok and m["want"]["down"] == 0 and m["down"]["none"] and len(seen) == all_n and steps <= all_n,
              [steps, all_n, len(seen), nav_brief(m)])
        e = wheel(page, 100)
        check("아래에 더 없으면 휠을 내려도 제자리 — 알약이 까딱(.bump) · 쪽 넘기기도 안 함", e["y"] == m["y"] and e["down"]["bump"] and nav_ok(e), [nav_brief(m), nav_brief(e), e["down"]])
        u = wheel(page, -100)
        check("휠을 올리면 앞 곳으로 — 「위」 수가 줆", u["y"] < e["y"] and u["y"] == u["to"] and nav_ok(u) and u["want"]["up"] < e["want"]["up"] and len(u["land"]) > 0, [nav_brief(e), nav_brief(u), u["land"]])
        page.click("#viewer > .fm-nav.up")
        page.evaluate(SETTLE)
        c = page.evaluate(NAV)
        check("알약 「▲ 위 n곳」 을 눌러도 앞 곳으로", c["y"] < u["y"] and nav_ok(c) and c["want"]["up"] < u["want"]["up"], [nav_brief(u), nav_brief(c)])
        page.evaluate("() => { document.getElementById('scroller').scrollTop = 0; }")
        page.evaluate(SETTLE)
        page.click("#fmtKey .fm-key-wheel")
        n0 = page.evaluate(NAV)
        n1 = wheel(page, 100)
        stored = page.evaluate("() => localStorage.getItem('nfm.fmFocusWheel')")
        check("「휠 이동」 을 끄면 휠은 평소대로(쪽 넘기기 — 자리 옮기기 안 함) · 알약은 남음(도움말에 꺼짐) · 이 브라우저에 기억",
              n0["wheelBtn"]["pressed"] == "false" and n1["at"] == n0["at"] and n1["y"] > n0["y"] and nav_ok(n1) and stored == "off" and "꺼져 있어" in n1["down"]["tip"], [n0["wheelBtn"], nav_brief(n0), nav_brief(n1), stored])
        page.click("#viewer > .fm-nav.down")
        page.evaluate(SETTLE)
        n2 = page.evaluate(NAV)
        page.click("#fmtKey .fm-key-wheel")
        n3 = page.evaluate(NAV)
        check("꺼 둔 채 알약 「▼ 아래 n곳」 은 눌러서 옮김 · 다시 누르면 켜짐(기억 지움)", n2["at"] != n1["at"] and n2["y"] > n1["y"] and nav_ok(n2) and n3["wheelBtn"]["pressed"] == "true"
              and page.evaluate("() => localStorage.getItem('nfm.fmFocusWheel')") is None, [nav_brief(n1), nav_brief(n2), n3["wheelBtn"]])

        # 서식 라벨에서도 같음 · 또렷이를 끄면 알약도 사라지고 휠은 평소대로
        page.evaluate(CLICK, first)
        focus_is(page, first, total)
        page.evaluate(SETTLE)
        page.evaluate("() => { document.getElementById('scroller').scrollTop = 0; }")
        page.evaluate(SETTLE)
        n = page.evaluate(NAV)
        m = wheel(page, 100)
        check(f"서식 라벨 「{first}」 에서도 — 알약의 수가 맞고 휠을 내리면 다음 곳으로", nav_ok(n) and n["want"]["down"] > 0 and m["y"] > n["y"] and m["y"] == m["to"] and nav_ok(m) and m["want"]["down"] < n["want"]["down"] and len(m["land"]) > 0,
              [nav_brief(n), nav_brief(m), m["land"]])
        t_scan = page.evaluate("() => { FMN.stops = null; const t0 = performance.now(); const n = fmNavStops().length; return [Math.round((performance.now() - t0) * 10) / 10, n]; }")
        print(f"INFO 곳 자리 재기 {t_scan[0]}ms(서식 「{first}」 — {t_scan[1]}곳 · 문단 {total}개)", flush=True)
        page.click("#fmtKey .fm-key-off")
        focus_is(page, None)
        page.evaluate(SETTLE)
        n0 = page.evaluate(NAV)
        n1 = wheel(page, 100)
        check("또렷이를 끄면 알약도 사라짐 · 휠은 평소대로(쪽 넘기기)", not n0["up"]["shown"] and not n0["down"]["shown"] and n0["count"] is None and n1["at"] == n0["at"] and n1["y"] != n0["y"] and not n1["up"]["shown"],
              [n0["up"], n0["down"], n0["count"], n0["y"], n1["y"]])

        # 다른 문서로 — 풀림
        page.evaluate(CLICK, first)
        focus_is(page, first, total)
        page.evaluate("(id) => { openWork(id); }", docx)
        page.wait_for_function("(id) => state.id === id && !document.getElementById('fileInfo').hidden && !!document.querySelector('#doc .para')", arg=docx, timeout=60000)
        page.wait_for_timeout(800)
        v = page.evaluate(VIEW)
        check("다른 문서(docx)로 바꿔 열면 풀림 — 새 문서가 흐리지 않고 설명도 없음", not v["on"] and v["missOp"] == [1] and not v["key"]["shown"] and page.evaluate("() => FMF.label") is None, [v["on"], v["missOp"], v["key"]])
        page.screenshot(path=str(OUT / "05_docx.png"))

        # 켜는 데 드는 시간 — 큰 문서에서 표시 클래스를 달고 스타일을 다시 계산하기까지
        page.evaluate("(id) => { openWork(id); }", plan)
        page.wait_for_function("(id) => state.id === id && !!document.querySelector('#doc .para')", arg=plan, timeout=60000)
        page.wait_for_function("() => document.querySelectorAll('.tpl-mark .tm-f').length > 20", timeout=60000)
        ms = page.evaluate("""async (ids) => { FMF.kind = 'fmt'; FMF.label = 'x'; FMF.ids = new Set(ids); FMF.total = ids.length; const doc = document.getElementById('doc');
          const t0 = performance.now(); fmtFocusDraw(); void doc.offsetHeight; getComputedStyle(doc.querySelector('.para')).opacity; const on = performance.now() - t0;
          const t1 = performance.now(); fmtFocusOff(); void doc.offsetHeight; getComputedStyle(doc.querySelector('.para')).opacity; const off = performance.now() - t1;
          return { on: Math.round(on), off: Math.round(off), paras: doc.querySelectorAll('.para[data-id]').length }; }""", want)
        print(f"INFO 켜기 {ms['on']}ms · 끄기 {ms['off']}ms(문단 요소 {ms['paras']}개 · 표시 클래스 + 스타일 다시 계산) · 눌러서 흐려지기까지 {took:.2f}초(끝점 읽기 포함)", flush=True)
        check("켜고 끄는 데 각각 1.5초 안(문단 요소 수천 개)", ms["on"] < 1500 and ms["off"] < 1500, ms)
        mt = page.evaluate("""async () => { const doc = document.getElementById('doc'); tplFocusOn({ tpl: '1', level: 2, no: '1' }); await tplFocusDiff();
          const t0 = performance.now(); fmtFocusDraw(); void doc.offsetHeight; getComputedStyle(doc.querySelector('.para')).opacity; const again = performance.now() - t0;
          const t1 = performance.now(); tplMarksDraw(); void doc.offsetHeight; const marks = performance.now() - t1;
          const n = document.querySelectorAll('.sheet > .fm-tag').length; fmtFocusOff(); return { again: Math.round(again), marks: Math.round(marks), tags: n }; }""")
        print(f"INFO 템플릿만 또렷이 — 다시 그리기 {mt['again']}ms(쪽을 다시 나눌 때마다 · 표 {mt['tags']}개) · 여백 표 다시 그리기(또렷이 포함) {mt['marks']}ms", flush=True)
        check("템플릿만 또렷이를 다시 그리는 데 0.5초 안(쪽을 다시 나눌 때마다 불린다)", mt["again"] < 500 and mt["marks"] < 1500 and mt["tags"] > 0, mt)
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

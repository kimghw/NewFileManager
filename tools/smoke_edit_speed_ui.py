"""편집 한 번의 빠르기와 「그 자리에서 바꿔 끼우기」(spec_hwpx_웹편집 ② §11 「편집 한 번의 비용」) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_edit_speed_ui.py <그림·임시 폴더> [--port 18181] [--work <작업 폴더>] [--budget 1200]

연구개발계획서_양식.hwpx 를 새 작업으로 열고(또는 --work 로 준 작업 폴더를 복사해 이어 열고) → 본문 개요 줄 여러 곳에서 Enter(쪽 가운데 · 쪽의 마지막 줄 · 쪽의 첫 줄) ·
Alt+↓/↑(레벨) · 빈 줄 Backspace(지움) · 보통 문단 나누기/합치기 · 줄 옮기기를 하며 편집마다 ① 문서 전체를 다시 나누지 않는지(paginate 0번) ② 같은 문단·표가 두 번 그려지지 않는지
③ 화면(블록 목록·쪽 흐름·문단)이 서버 문서와 같은지(빠진 줄·차례) ④ 그 자리에서 바꾼 결과가 paginate() 로 처음부터 다시 나눈 것과 같은지(쪽 상자마다 든 것의 차례), 그리고
⑤ 키를 누르고 새 줄이 보일 때까지의 시간(가운데값 ≤ --budget ms) ⑥ 편집 중 body 에 클래스를 달지 않는지 ⑦ 콘솔 오류.
표 칸 안 편집은 그 자리에서 못 바꾼다(표는 행이 쪽마다 조각으로 나뉜다 — paginate 로)."""
import argparse
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18181)
ap.add_argument("--work", help="이어 열 작업 폴더(복사해서 씀) — 없으면 예제를 새 작업으로")
ap.add_argument("--budget", type=int, default=1200, help="Enter 한 번(키 → 그림)의 가운데값 한도 ms")
args = ap.parse_args()
OUT = Path(args.out).resolve()
PLAN = "연구개발계획서_양식.hwpx"

OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
(tmp / "works").mkdir(parents=True, exist_ok=True)
wid = None
if args.work:
    wid = Path(args.work).name
    shutil.copytree(args.work, tmp / "works" / wid)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:600] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


# 쪽 상자마다 든 것의 차례(문단 id · 표 조각 id#행 수 · 그 밖은 클래스) — 그 자리에서 바꾼 결과와 처음부터 다시 나눈 결과를 견준다
SIG = """() => [...document.querySelectorAll('#doc > *')].map((s) => !s.classList.contains('sheet') ? `gap${s.dataset.page}`
  : `${s.dataset.page}${s.dataset.over ? '+' + s.dataset.over : ''}:` + [...s.querySelector('.sheet-body').children].map((c) => c.dataset.id || (c.tagName === 'TABLE' ? `t${c.dataset.tbl}#${c.tBodies[0].rows.length}` : c.className.split(' ')[0])).join(','))"""
HOOK = """() => {
  window.__e = {paginate: 0, key: 0, body: 0, net: 0};
  const pg = window.paginate; window.paginate = function (...a) { window.__e.paginate += 1; return pg.apply(this, a); };
  const api0 = window.api; window.api = async function (u, o) { const t = performance.now(); try { return await api0(u, o); } finally { if (o && o.method === 'POST') window.__e.net = performance.now() - t; } };
  document.addEventListener('keydown', () => { window.__e.key = performance.now(); }, true);
  new MutationObserver((ms) => { for (const m of ms) if (m.attributeName === 'class' && /busy/.test(document.body.className)) window.__e.body += 1; }).observe(document.body, {attributes: true});
}"""
# 같은 문단·표가 화면(과 쪽 흐름)에 두 번 있는가 — 응답 tops.blocks 는 닿은 구간의 이웃까지 싣는다(② §8), 화면은 그 id 를 모두 「바꿀 것」으로 다뤄야 한다
DUPS = """() => { const seen = new Map(); for (const e of document.querySelectorAll('#doc .para[data-id], #doc table.tbl[data-tbl]:not(.cont)')) { const k = e.dataset.id || 't:' + e.dataset.tbl; seen.set(k, (seen.get(k) || 0) + 1); }
  const flow = new Map(); for (const it of state.flow) for (const id of (it.kind === 'table' ? [it.id] : it.ids)) flow.set(id, (flow.get(id) || 0) + 1);
  const ids = state.blocks.map((b) => b.id);
  return [...[...seen].filter(([, n]) => n > 1).map(([k]) => 'dom ' + k), ...[...flow].filter(([, n]) => n > 1).map(([k]) => 'flow ' + k), ...(new Set(ids).size !== ids.length ? ['blocks'] : [])].slice(0, 8); }"""
PICK = """() => {
  const body = (id) => { const p = paraEl(id); return p && p.parentElement.classList.contains('sheet-body') ? p : null; };
  const ids = Object.keys(heads.outline.lines).filter((id) => body(id) && heads.outline.lines[id].role !== 'label' && (state.texts[id] || '').trim().length > 3);
  const mid = []; for (let k = 0; k < 6; k++) mid.push(ids[Math.floor((k + 0.5) * ids.length / 6)]);
  const sym = (id) => !/[0-9A-Za-z가-힣ㄱ-ㅎ]/.test(heads.outline.lines[id].letter); // 기호 레터(□ o - ⋅) — 번호 레터는 Enter 가 뒤 형제의 번호를 다시 매겨 멀리 있는 줄까지 바뀐다(그 자리에서 못 함)
  return {n: ids.length, mid, last: ids.find((id) => sym(id) && !body(id).nextElementSibling && !mid.includes(id)), first: ids.find((id) => sym(id) && !body(id).previousElementSibling && !mid.includes(id)),
          plain: [...document.querySelectorAll('#doc .sheet-body > .para')].map((p) => p.dataset.id).find((id) => !heads.outline.lines[id] && (state.texts[id] || '').trim().length > 30 && paraEl(id).previousElementSibling),
          paras: document.querySelectorAll('#doc .para').length, sheets: document.querySelectorAll('#doc .sheet').length, mapped: !!state.mapping}; }"""


def act(page, name, do, grows=1, expect_swap=True):
    """편집 하나 — do() 가 키를 누른다. → (키 → 그림 ms, 서버 ms). 그 자리에서 바꾼 결과를 paginate() 결과와 견준다."""
    n0 = page.evaluate("() => { window.__e.paginate = 0; window.__e.key = 0; window.__e.net = 0; return document.querySelectorAll('#doc .para').length; }")
    do()
    page.wait_for_function("([n, g]) => { const k = document.querySelectorAll('#doc .para').length; return !state.busy && window.__e.key && window.__e.net > 0 && (g === 0 || (g > 0 ? k > n : k < n)); }",
                           arg=[n0, grows], timeout=120000)  # 개요 줄 Enter 는 간격 줄까지 둘이 생기기도 한다
    ms = page.evaluate("() => new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(() => res(performance.now() - window.__e.key))))")
    net = page.evaluate("() => window.__e.net")
    verify(page, name, expect_swap)
    return ms, net


def verify(page, name, expect_swap=True):
    """편집 하나 뒤 — 문서 전체를 다시 나누지 않았는가 · 겹쳐 그린 것 없음 · 화면 = 서버 문서 · 그 자리 결과 = paginate() 결과."""
    e = page.evaluate("() => window.__e")
    if expect_swap:
        check(f"{name} — 문서 전체를 다시 나누지 않음(paginate 0번)", e["paginate"] == 0, e)
    dups = page.evaluate(DUPS)
    check(f"{name} — 같은 문단·표가 두 번 그려지지 않음", not dups, dups)
    srv = requests.get(f"{base}/api/docs/{page.evaluate('() => state.id')}", timeout=120).json()["blocks"]  # 서버 문서 — 화면이 줄을 잃거나 차례가 어긋나지 않았는가
    flat = []

    def walk(bs):
        for b in bs:
            if b["type"] == "paragraph":
                flat.append(b["id"])
            for c in b.get("cells") or []:
                walk(c.get("blocks") or [])
    walk(srv)
    off = page.evaluate("""([tops, flat]) => { const out = [], bl = state.blocks.map((b) => b.id), fl = state.flow.flatMap((it) => (it.kind === 'table' ? [it.id] : it.ids));
      const first = (a, b) => { const k = a.findIndex((x, i) => x !== b[i]); return k < 0 && a.length === b.length ? null : `${k < 0 ? Math.min(a.length, b.length) : k}번째 ${a[k]} ≠ ${b[k]} (길이 ${a.length}/${b.length})`; };
      const x = first(tops, bl), y = first(tops, fl); if (x) out.push('blocks ' + x); if (y) out.push('flow ' + y);
      const dom = new Set([...document.querySelectorAll('#doc .para[data-id]')].map((e) => e.dataset.id)), miss = flat.filter((i) => !dom.has(i)), more = [...dom].filter((i) => !flat.includes(i));
      if (miss.length) out.push('화면에 없음 ' + miss.slice(0, 5)); if (more.length) out.push('서버에 없음 ' + more.slice(0, 5));
      const top = [...document.querySelectorAll('#doc .sheet-body > .para[data-id]')].map((e) => e.dataset.id), want = tops.filter((i) => top.includes(i)), z = first(want, top.filter((i) => tops.includes(i)));
      if (z) out.push('본문 문단 차례 ' + z);
      return out; }""", [[b["id"] for b in srv], flat])
    check(f"{name} — 화면 = 서버 문서(빠진 줄·차례)", not off, off)
    foc = page.evaluate("() => { const a = document.activeElement; return a && a.classList.contains('para') ? a.dataset.id : null; }")
    a = page.evaluate(SIG)
    page.evaluate("() => paginate()")
    page.wait_for_timeout(150)
    b = page.evaluate(SIG)
    diff = next((f"{x} ≠ {y}" for x, y in zip(a, b) if x != y), None) or (f"쪽 상자 수 {len(a)} ≠ {len(b)}" if len(a) != len(b) else None)
    check(f"{name} — 그 자리 결과 = 처음부터 다시 나눈 결과", diff is None, diff)
    if foc:
        page.evaluate("(id) => { const p = paraEl(id); if (p && document.activeElement !== p) focusAt({id, offset: state.cur && state.cur.id === id ? state.cur.start : 0}); }", foc)


try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1700, "height": 1000})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/#w={wid}" if wid else base)
        if not wid:
            page.wait_for_selector("#drop")
            page.evaluate("() => { const s = document.getElementById('sampleSection'); s.hidden = false; s.open = true; }")
            page.evaluate("(n) => document.querySelector(`.sample[aria-label=\"예제 ${n} 열기\"]`).click()", PLAN)
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=300000)
        page.wait_for_function("() => typeof heads !== 'undefined' && !!heads.outline && !(heads.view && heads.view.job && heads.view.job.status === 'running')", timeout=300000)
        page.wait_for_timeout(6000)  # 첫 그림 뒤 배경 일(첫 분석·표시)이 가라앉게
        page.evaluate(HOOK)
        pk = page.evaluate(PICK)
        print(f"문단 {pk['paras']} · 쪽 상자 {pk['sheets']} · 본문 개요 줄 {pk['n']} · 쪽 매핑 {'있음' if pk['mapped'] else '없음(어림 쪽)'}", flush=True)
        end = "(id) => { const p = paraEl(id); p.scrollIntoView({block: 'center'}); focusAt({id, offset: state.texts[id].length}); }"

        # ---- 1. 개요 줄 Enter — 쪽 가운데 여섯 곳
        times, nets = [], []
        for k, pid in enumerate(pk["mid"]):
            page.evaluate(end, pid)
            page.wait_for_timeout(400)
            ms, net = act(page, f"Enter #{k + 1}({pid})", lambda: page.keyboard.press("Enter"))
            times.append(ms)
            nets.append(net)
            print(f"   Enter #{k + 1}: 키 → 그림 {ms:.0f} ms · 서버 {net:.0f} ms · {page.evaluate('(id) => heads.outline.lines[id].letter', pid)!r} 줄", flush=True)
            new = page.evaluate("() => state.cur && state.cur.id")
            check(f"Enter #{k + 1} — 새 줄에 커서 · 앞 줄 바로 아래", page.evaluate("([a, b]) => { const p = paraEl(b); return !!p && b !== a && document.activeElement === p && !!heads.outline.lines[b]; }", [pid, new]), new)
        med, net = statistics.median(times), statistics.median(nets)
        print(f"Enter 한 번(키 → 그림): {[round(t) for t in times]} ms · 가운데값 {med:.0f} ms(그 가운데 서버 응답 {net:.0f} ms)", flush=True)
        check(f"Enter 한 번의 가운데값 ≤ {args.budget} ms", med <= args.budget, f"{med:.0f} ms")
        check("편집 중 body 에 busy 클래스를 달지 않음", page.evaluate("() => window.__e.body") == 0)

        # ---- 2. 방금 만든 빈 줄에서 레벨 · 지움
        cur = page.evaluate("() => state.cur.id")
        act(page, "Alt+↑(레벨 올림)", lambda: page.keyboard.press("Alt+ArrowUp"), grows=0)
        act(page, "Alt+↓(레벨 내림)", lambda: page.keyboard.press("Alt+ArrowDown"), grows=0)
        if page.evaluate("(id) => outlineEmpty(paraEl(id))", cur):
            n0 = page.evaluate("() => document.querySelectorAll('#doc .para').length")
            act(page, "빈 줄 Backspace(지움)", lambda: page.keyboard.press("Backspace"), grows=0)
            check("빈 줄 지움 — 문단이 줄어듦", page.evaluate("() => document.querySelectorAll('#doc .para').length") < n0)

        # ---- 3. 쪽의 마지막 줄 · 첫 줄
        for label, pid in (("쪽의 마지막 줄", pk["last"]), ("쪽의 첫 줄", pk["first"])):
            if not pid:
                print(f"SKIP {label} — 그런 개요 줄이 없음", flush=True)
                continue
            page.evaluate(end, pid)
            page.wait_for_timeout(400)
            # 쪽 매핑이 없는 문서에서 쪽의 마지막 줄 뒤에 줄을 넣으면 다음 쪽 첫 블록의 「쪽 시작」(줄 배치로 어림)까지 바뀌어 두 쪽에 걸친다 — 그때는 전체를 다시 나누는 것이 맞다
            act(page, f"Enter — {label}({pid})", lambda: page.keyboard.press("Enter"), expect_swap=pk["mapped"] or label != "쪽의 마지막 줄")

        # ---- 4. 보통 문단 나누기 · 합치기
        if pk["plain"]:
            page.evaluate("(id) => { const p = paraEl(id); p.scrollIntoView({block: 'center'}); focusAt({id, offset: 12}); }", pk["plain"])
            page.wait_for_timeout(400)
            act(page, f"보통 문단 Enter(나누기 — {pk['plain']})", lambda: page.keyboard.press("Enter"))
            act(page, "Backspace(앞 문단과 합치기)", lambda: page.keyboard.press("Backspace"), grows=-1)
        # ---- 4-1. 줄 끌어 옮기기(손잡이 끌기가 부르는 것과 같은 요청) — 여러 줄을 건너 옮겨도 사이의 줄이 화면에서 사라지지 않는다
        page.evaluate("() => { window.__e.paginate = 0; }")
        mv = page.evaluate("""async () => { const ids = Object.keys(heads.outline.lines).filter((id) => { const p = paraEl(id); return p && p.parentElement.classList.contains('sheet-body'); });
          const pos = new Map(state.blocks.map((b, i) => [b.id, i])); let tried = 0;
          for (let k = 0; k + 1 < ids.length; k++) for (let j = k + 1; j < Math.min(ids.length, k + 8); j++) {
            const a = heads.outline.lines[ids[k]], b = heads.outline.lines[ids[j]], gap = pos.get(ids[j]) - pos.get(ids[k]);
            if (a.tpl !== b.tpl || a.level !== b.level || a.role !== 'heading' || !(gap >= 3 && gap <= 14)) continue;
            if ((tried += 1) > 15) return null;
            const r = await structOp('outline', {op: 'move', id: ids[k], target: ids[j], where: 'after'});
            if (r) return {id: ids[k], target: ids[j], gap, blocks: r.tops.blocks.length};
          } return null; }""")
        if mv:
            print(f"   옮김: {mv['id']} → {mv['target']} 뒤(블록 {mv['gap']}개 건너) · 응답 블록 {mv['blocks']}개", flush=True)
            verify(page, "줄 끌어 옮기기", expect_swap=False)
        else:
            print("SKIP 줄 끌어 옮기기 — 옮길 수 있는 형제 줄을 못 찾음", flush=True)
        page.screenshot(path=str(OUT / "edit_speed.png"))

        # ---- 5. 실행 취소는 문서를 통째로 다시 읽는다(그대로)
        u0 = page.evaluate("() => state.undo")
        page.click("#undoBtn")
        page.wait_for_function("(u) => !state.busy && state.undo === u - 1", arg=u0, timeout=120000)
        check("실행 취소 — 한 단계 되돌아감", True)

        bad = [e for e in errors if "favicon" not in e]
        check("콘솔 오류·pageerror 없음", not bad, bad[:5])
        browser.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()

print(f"\n{'실패 ' + str(len(fails)) + '개: ' + ', '.join(fails) if fails else '모두 통과'}")
sys.exit(1 if fails else 0)

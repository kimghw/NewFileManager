"""구분 기준 자리 표시의 색 설명(spec_구분_기준 ② §11 「색 설명」) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_div_key_ui.py <그림·임시 폴더> [--port 18171]

연구개발계획서 양식을 연구개발과제 작업으로 올려 본다: 표시를 켜기 전에는 문서 이름 줄에 설명 없음 → 켜면 「구분 기준 자리」 + 그 문서에 있는 구분의 칩(문서 색과 같은 색) + 「진한 줄 = 라벨」 +
노트 → 다른 도구로 넘어가도 그대로 → 줄 높이·넘침 없음(폭 여럿) → 이름 줄 아이콘 「구분 기준 자리 표시」(#nameDivMarks)로 끄면 색·설명 함께 사라짐.
(2026-11-18 설명 끝의 「감추기」 단추는 뺐다 — 같은 줄의 그 아이콘이 같은 일을 한다: spec_작업 ② §17 「이름 줄 표시 아이콘」.)"""
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
ap.add_argument("--port", type=int, default=18171)
args = ap.parse_args()
OUT = Path(args.out).resolve()
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
NAMES = {"stage": "단계", "stageYear": "단계-차년도", "year": "차년도", "sub": "세부과제", "org": "기관", "other": "기타"}
ORDER = list(NAMES)


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:300] if detail != "" else ""), flush=True)
    if not ok:
        fails.append(name)


KEY = """() => { const k = document.getElementById('divKey'), row = document.getElementById('fileInfo'), vis = (e) => !!e && e.getClientRects().length > 0, rr = row.getBoundingClientRect();
  const inside = (e) => { const r = e.getBoundingClientRect(); return r.left >= rr.left - 1 && r.right <= rr.right + 1 && r.top >= rr.top - 1 && r.bottom <= rr.bottom + 1; };
  const ic = document.getElementById('nameDivMarks'), parts = [...k.querySelectorAll('.dv-chip, .panel-help'), ic];  // ic = 이름 줄 아이콘 「구분 기준 자리 표시」 — 켜져 있는 동안 늘 줄 안(끄는 길)
  return { shown: vis(k), has: row.classList.contains('has-dv-key'), chips: [...k.querySelectorAll('.dv-chip')].map((c) => [c.dataset.dv, c.textContent]),
    name: vis(k.querySelector('.dv-key-name')), tone: vis(k.querySelector('.dv-key-tone')), mode: vis(row.querySelector('.document-mode')),
    help: (k.querySelector('.panel-help') || { dataset: {} }).dataset.help || '', off: [...k.querySelectorAll('button')].filter((b) => !b.classList.contains('dv-chip')).map((b) => b.textContent.trim()).join('|'),
    icon: ic.getAttribute('aria-pressed'),
    inside: parts.length > 0 && parts.every((e) => vis(e) && inside(e)), rowW: Math.round(rr.width), rowH: Math.round(rr.height), over: row.scrollWidth > row.clientWidth + 1,
    cw: Math.round(row.clientWidth - parseFloat(getComputedStyle(row).paddingLeft) - parseFloat(getComputedStyle(row).paddingRight)),
    beforeMode: !!k.nextElementSibling && k.nextElementSibling.classList.contains('document-mode') }; }"""
DOC_DIMS = "() => [...new Set([...document.querySelectorAll('#doc .para.dv-in')].map((p) => p.dataset.dv))]"

try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    form = ROOT / "samples" / "연구개발계획서_양식.hwpx"
    a = requests.post(f"{base}/api/docs?new=1", files={"file": (form.name, form.read_bytes())}, timeout=300).json()["docId"]
    requests.put(f"{base}/api/works/{a}/task", json={"kind": "rnd", "file": "plan", "job": "", "project": ""}, timeout=30).raise_for_status()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.goto(base)
        page.evaluate("() => { try { localStorage.removeItem('nfm.divMarks'); localStorage.removeItem('nfm.fileFold'); } catch {} }")
        page.evaluate("(id) => { location.hash = '#w=' + id; }", a)
        page.reload()
        page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=a, timeout=180000)
        page.click("#toolTabTask")
        page.wait_for_selector("#divMarksBar")

        # ---- 1. 켜기 전 — 설명 없음
        k0 = page.evaluate(KEY)
        check("켜기 전 — 문서 이름 줄에 색 설명 없음", not k0["shown"] and not k0["has"] and k0["mode"], k0)
        check("카드의 노트 — 처음 한 줄 + 색 설명", all(s in page.get_attribute("#divMarksBar .dv-marks-copy .panel-help", "data-help") for s in ("단계·차년도·기관이 걸린 자리를 색으로", "진한 색 + 왼쪽 띠", "가장 안쪽")))

        # ---- 2. 켬 — 칩 = 문서에 있는 구분(겉 → 안) · 문서와 같은 색 · 노트 · 이름 줄 아이콘 눌림
        page.click("#divMarksBar .dv-marks-toggle")
        page.wait_for_function("() => document.querySelectorAll('#doc .para.dv-in').length > 0", timeout=120000)
        k = page.evaluate(KEY)
        dims = sorted(page.evaluate(DOC_DIMS), key=ORDER.index)
        check("켜면 문서 이름 줄에 색 설명(「편집 중」 바로 앞)", k["shown"] and k["has"] and k["beforeMode"], k)
        check("칩 = 문서에 색이 입혀진 구분 전부(겉 → 안 · 이름만)", [c[0] for c in k["chips"]] == dims and all(c[1] == NAMES[c[0]] for c in k["chips"]) and len(dims) >= 3, (k["chips"], dims))
        same = page.evaluate("""() => [...document.querySelectorAll('#divKey .dv-chip')].every((c) => { const p = document.querySelector(`#doc .para.dv-in[data-dv="${c.dataset.dv}"]`);
          return !!p && getComputedStyle(c).getPropertyValue('--dv-line').trim() === getComputedStyle(p).getPropertyValue('--dv-line').trim() && getComputedStyle(c, '::before').backgroundColor !== 'rgba(0, 0, 0, 0)'; })""")
        check("칩 색 = 문서의 그 구분 색", same)
        # 겹친 자리의 띠(2026-11-18 사용자 "구분기준이 2개 이상이면 줄을 하나만 표시하지말고 모든 색을 반영해서 넣어줘") — 든 구분마다 띠 하나, 겉 → 안 차례 · 라벨 줄은 하나여도 띠
        mul = page.evaluate("""() => { const order = ['stage', 'stageYear', 'year', 'sub', 'org', 'other'], ps = [...document.querySelectorAll('#doc .para.dv-in')];
          const dimsOf = (p) => (p.dataset.dvs || '').split(' ').filter(Boolean), multi = ps.filter((p) => dimsOf(p).length > 1);
          const rgb = (p) => (getComputedStyle(p).backgroundImage.match(/rgb\\([^)]*\\)/g) || []).filter((c, i, a) => i === 0 || c !== a[i - 1]); // 띠 하나 = 색 멈춤 둘(시작·끝) — 이어진 같은 색은 하나로
          const want = (k) => { const s = document.createElement('i'); s.style.color = `var(--dvc-${k})`; document.body.append(s); const c = getComputedStyle(s).color; s.remove(); return c; };
          const ok = multi.every((p) => { const d = dimsOf(p), got = rgb(p); return p.classList.contains('dv-multi') && new Set(d).size === d.length && d.every((k) => order.includes(k))
            && got.length >= d.length && d.every((k, i) => got[i] === want(k)); });   // 차례는 실제로 품은 차례(항목이 큰 것이 바깥) — 색이 그 차례대로
          const labs = ps.filter((p) => p.classList.contains('dv-lab')), labOk = labs.every((p) => rgb(p).length >= Math.max(1, dimsOf(p).length));
          const single = ps.filter((p) => !p.classList.contains('dv-lab') && !p.classList.contains('dv-read') && dimsOf(p).length < 2), plain = single.every((p) => !p.classList.contains('dv-multi') && rgb(p).length === 0);
          const reads = ps.filter((p) => p.classList.contains('dv-read')), readOk = reads.every((p) => getComputedStyle(p).backgroundColor === 'rgba(0, 0, 0, 0)' && rgb(p).length >= 1
            && /1px/.test(p.style.getPropertyValue('--dv-stripes')) && /판독만/.test(p.title));
          return { multi: multi.length, three: multi.filter((p) => dimsOf(p).length > 2).length, ok, labs: labs.length, labOk, single: single.length, plain, reads: reads.length, readOk,
                   sample: multi[0] ? [multi[0].dataset.dvs, rgb(multi[0])] : null }; }""")
        check("겹친 자리 — 든 구분마다 왼쪽 띠(구분별 색) · 라벨 줄은 늘 띠 · 구분 하나인 내용 줄은 띠 없음",
              mul["multi"] > 0 and mul["ok"] and mul["labOk"] and mul["plain"], mul)
        # 구분 기준 판독(spec_구분_기준 ② §23)이 보탠 자리 — 엔진 묶음 밖의 괄호 줄(「[해당 기관별 작성] …」): 가는 띠 · 바탕 없음 · 도움말에 「판독만」 · 이름 줄에 「가는 띠 = 판독만」
        check("판독만인 자리 — 가는 띠(1px) · 바탕 없음 · 문단 도움말 「판독만」 · 색 설명 노트에 「가는 띠」(이름 줄 글은 늘리지 않음)",
              mul["reads"] > 0 and mul["readOk"] and "가는 띠" in (page.get_attribute("#divKey .panel-help", "data-help") or ""), mul)
        check("「구분 기준 자리」 · 「진한 줄 = 라벨」 · 노트(색마다 구분 · 진한/옅은 · 가장 안쪽 · 감추고 다시 켜는 곳 = 아이콘) · 설명 안에 「감추기」 단추 없음 · 이름 줄 아이콘 눌림",
              k["name"] and k["tone"] and k["off"] == "" and k["icon"] == "true"
              and all(s in k["help"] for s in ("파랑 단계", "주황 기관", "진한 색 + 왼쪽 띠", "옅은 색", "가장 안쪽", "다시 보려면", "「구분 기준 자리 표시」 아이콘")), [k["off"], k["icon"], k["help"][:200]])
        check("줄을 더 쓰지 않음 — 이름 줄 높이 그대로 · 넘침 없음 · 칩·노트·아이콘이 줄 안", k["rowH"] == k0["rowH"] and not k["over"] and k["inside"], (k0["rowH"], k["rowH"], k["rowW"]))
        page.screenshot(path=str(OUT / "1_key.png"), clip={"x": 0, "y": 0, "width": 1600, "height": 420})
        page.evaluate("() => { const p = document.querySelector('#doc .para.dv-lab[data-dv=org]') || document.querySelector('#doc .para.dv-lab'); p.scrollIntoView({ block: 'center' }); }")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "1_key_doc.png"))  # 색이 입혀진 자리 + 그 위의 설명

        # 긴 파일 이름 — 이름이 줄임표로 줄 뿐 설명을 다음 줄로 밀지 않는다(flex-basis 6em — 줄 나눔은 줄어든 폭으로 잰다)
        page.evaluate("() => { const n = document.getElementById('fileName'); n.dataset.was = n.textContent; n.textContent = '아주 긴 파일 이름 '.repeat(30) + '.hwpx'; }")
        kl = page.evaluate(KEY)
        check("긴 파일 이름 — 줄 높이 그대로 · 이름만 줄임표 · 설명은 다 보임", kl["rowH"] == k0["rowH"] and not kl["over"] and kl["inside"] and kl["name"]
              and page.evaluate("() => { const n = document.getElementById('fileName'); return n.hidden || n.scrollWidth > n.clientWidth; }"), (kl["rowH"], kl["rowW"]))
        page.evaluate("() => { const n = document.getElementById('fileName'); n.textContent = n.dataset.was; }")

        # ---- 3. 노트 — 누르면 도움말, Esc 로 닫힘 · 쪽을 다시 나눠도(divMarksDraw) 열어 둔 노트가 그대로
        page.click("#divKey .panel-help")
        tip = page.inner_text("#panelHelpTooltip") if page.locator("#panelHelpTooltip").is_visible() else ""
        page.evaluate("() => divMarksDraw()")
        check("노트 도움말이 열리고 다시 그려도 그대로", "진한 색 + 왼쪽 띠" in tip and page.locator("#panelHelpTooltip").is_visible() and page.evaluate("() => panelHelpOwner && panelHelpOwner.isConnected"), tip[:120])
        page.keyboard.press("Escape")

        # ---- 4. 다른 도구로 넘어가도 설명은 문서 옆에 그대로(카드는 안 보임)
        page.evaluate("() => showTab('Edits')")
        k = page.evaluate(KEY)
        check("다른 도구(고친 문단)에서도 색 설명 그대로", k["shown"] and len(k["chips"]) == len(dims) and page.evaluate("() => document.getElementById('paneDiv').getClientRects().length") == 0
              and page.evaluate("() => document.querySelectorAll('#doc .para.dv-in').length") > 0, k["chips"])
        page.click("#toolTabTask")
        page.wait_for_selector("#divMarksBar")

        # ---- 5. 폭 — 좁으면 이름·「진한 줄 = 라벨」 → 「편집 중」 차례로 감춤(줄 폭 기준) · 칩·노트·아이콘(켜짐)은 남음
        seen = []
        for width in (1600, 1360, 1180, 1000, 880):
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(350)
            k = page.evaluate(KEY)
            seen.append((width, k["rowW"], k["rowH"], k["name"], k["mode"]))
            # 감춤 문턱은 줄의 안쪽 폭(@container — 좌우 여백 뺀 폭): 760px 이하 = 이름·「진한 줄 = 라벨」 감춤 · 560px 이하 = 「편집 중」 도 감춤
            check(f"창 {width}px(줄 {k['rowW']}px) — 넘침 없음 · 칩·노트·아이콘 다 보임 · 감춤 차례가 줄 폭과 맞음", k["shown"] and not k["over"] and k["inside"] and len(k["chips"]) == len(dims)
                  and k["name"] == (k["cw"] > 760) and k["tone"] == k["name"] and k["mode"] == (k["cw"] > 560), {x: k[x] for x in ("rowW", "cw", "rowH", "name", "tone", "mode", "over", "inside")})
            page.screenshot(path=str(OUT / f"2_w{width}.png"), clip={"x": 0, "y": 0, "width": width, "height": 200})
        check("줄 폭 480px 이상이면 한 줄(높이 그대로) · 더 좁으면 설명만 다음 줄로 접힘(그때도 넘침 없이 다 보임 — 위 검사)", all(h == k0["rowH"] for _, w, h, _, _ in seen if w >= 480)
              and any(w >= 480 and not n for _, w, _, n, _ in seen), seen)
        page.set_viewport_size({"width": 1600, "height": 900})
        page.wait_for_timeout(350)

        # ---- 6. 파일명 줄을 접으면 설명도 함께 · 펴면 다시
        page.click("#fileFold")
        check("파일명 줄 접음 — 설명도 안 보임(색은 그대로)", not page.evaluate(KEY)["shown"] and page.evaluate("() => document.querySelectorAll('#doc .para.dv-in').length") > 0)
        page.click("#fileFold")
        check("파일명 줄 폄 — 설명 다시", page.evaluate(KEY)["shown"])

        # ---- 6b. 그 구분만 또렷이(② §11 「그 구분만 또렷이」, 2026-11-18): 칩 = 단추 — 누르면 그 구분에 든 문단은 그대로 · 나머지 문단은 흐리게(감추지 않음) · 다시 누르면 풀림
        ONLY = """(k) => { const doc = document.getElementById('doc'), paras = [...doc.querySelectorAll('.para[data-id]')], vis = (e) => e.getClientRects().length > 0;
          const want = (p) => { const e = dv.marks.index.get(p.dataset.id); return !!e && e.dims.includes(k); }, op = (p) => +getComputedStyle(p).opacity;
          const hits = paras.filter((p) => p.classList.contains('dv-hit'));
          return { cls: doc.classList.contains('dv-only'), hits: hits.length, want: paras.filter(want).length, wrong: paras.filter((p) => p.classList.contains('dv-hit') !== want(p)).length,
                   hitOp: hits.slice(0, 50).every((p) => op(p) === 1), dimOp: paras.filter((p) => !p.classList.contains('dv-hit') && p !== document.activeElement).slice(0, 50).every((p) => Math.abs(op(p) - 0.42) < 0.01),
                   allVis: [...doc.querySelectorAll(':scope > .sheet')].every(vis) && paras.filter((p) => !vis(p)).length === 0,
                   pressed: [...document.querySelectorAll('#divKey .dv-chip')].filter((c) => c.getAttribute('aria-pressed') === 'true').map((c) => c.dataset.dv),
                   tags: [...document.querySelectorAll('#divKey .dv-chip')].every((c) => c.tagName === 'BUTTON') }; }"""
        d1, d2 = dims[0], dims[-1]  # 칩 둘(겉 · 안) — 이름 a 는 위의 작업 id(아래 8 이 쓴다)
        page.click(f'#divKey .dv-chip[data-dv="{d2}"]')
        o = page.evaluate(ONLY, d2)
        check(f"칩 「{NAMES[d2]}」 누름 → 그 구분에 든 문단만 또렷이(빠짐·남음 없음) · 나머지 흐리게 0.42 · 감춘 것 없음 · 칩 눌림",
              o["cls"] and o["tags"] and o["hits"] == o["want"] > 0 and o["wrong"] == 0 and o["hitOp"] and o["dimOp"] and o["allVis"] and o["pressed"] == [d2], o)
        page.screenshot(path=str(OUT / "6b_only.png"))
        page.click(f'#divKey .dv-chip[data-dv="{d1}"]')
        o = page.evaluate(ONLY, d1)
        check(f"다른 칩 「{NAMES[d1]}」 → 그 구분으로 바뀜(한 번에 하나)", o["cls"] and o["wrong"] == 0 and o["hits"] == o["want"] > 0 and o["pressed"] == [d1], o)
        page.evaluate("() => paginate()")  # 쪽을 다시 나누면(편집) 문단 요소가 새것 — 표지를 다시
        o = page.evaluate(ONLY, d1)
        check("쪽을 다시 나눠도 그대로", o["cls"] and o["wrong"] == 0 and o["hits"] == o["want"] > 0, o)
        page.click(f'#divKey .dv-chip[data-dv="{d1}"]')
        o = page.evaluate(ONLY, d1)
        check("같은 칩 다시 → 풀림(흐린 문단 없음 · 눌림 없음 · 색은 그대로)", not o["cls"] and o["hits"] == 0 and not o["pressed"]
              and page.evaluate("() => document.querySelectorAll('#doc .para.dv-in').length") > 0, o)
        page.click(f'#divKey .dv-chip[data-dv="{d2}"]')  # 켠 채로 끄기 — 아래 7 에서 함께 풀리는지

        # ---- 7. 이름 줄 아이콘 「구분 기준 자리 표시」 로 끄기 — 색·설명 함께 사라지고 카드 단추는 「보기」 · 기억
        page.click("#nameDivMarks")
        k = page.evaluate(KEY)
        check("아이콘으로 끔 → 문단 색 없음 · 설명 없음 · 「편집 중」 다시 · 아이콘 안 눌림 · 카드 단추 「보기」 · 기억(off)", not k["shown"] and not k["has"] and k["mode"] and k["icon"] == "false"
              and page.evaluate("() => document.querySelectorAll('#doc .para.dv-in').length") == 0 and page.inner_text("#divMarksBar .dv-marks-toggle").strip() == "보기"
              and page.evaluate("() => localStorage.getItem('nfm.divMarks')") == "off", k)
        o = page.evaluate(ONLY, d2)
        check("「그 구분만 또렷이」 중 끄면 → 함께 풀림", not o["cls"] and o["hits"] == 0 and page.evaluate("() => dv.marks.only") is None, o)
        page.click("#divMarksBar .dv-marks-toggle")
        page.wait_for_function("() => document.querySelectorAll('#doc .para.dv-in').length > 0", timeout=60000)
        check("카드에서 다시 「보기」 → 설명 다시 · 아이콘도 눌림(같은 값)", page.evaluate(KEY)["shown"] and len(page.evaluate(KEY)["chips"]) == len(dims) and page.evaluate(KEY)["icon"] == "true")

        # ---- 8. 연구개발과제가 아니면 색도 설명도 없음
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task")):
            page.select_option("#panelTask", "")
        page.wait_for_function("() => document.querySelectorAll('#doc .para.dv-in').length === 0")
        check("작업 종류를 풀면 설명도 사라짐", not page.evaluate(KEY)["shown"] and not page.evaluate(KEY)["has"])
        check("JS 오류 없음", not errors, errors[:5])
        browser.close()
except Exception as e:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    fails.append(f"예외: {e}")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'통과' if not fails else '실패'} — 떨어진 검사 {len(fails)}개" + ("" if not fails else ": " + " / ".join(fails)), flush=True)
sys.exit(1 if fails else 0)

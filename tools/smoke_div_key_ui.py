"""구분 기준 자리 표시의 색 설명(spec_구분_기준 ② §11 「색 설명」) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_div_key_ui.py <그림·임시 폴더> [--port 18171]

연구개발계획서 양식을 연구개발과제 작업으로 올려 본다: 표시를 켜기 전에는 문서 이름 줄에 설명 없음 → 켜면 「구분 기준 자리」 + 그 문서에 있는 구분의 칩(문서 색과 같은 색) + 「진한 줄 = 라벨」 +
노트 + 「감추기」 → 다른 도구로 넘어가도 그대로 → 줄 높이·넘침 없음(폭 여럿) → 「감추기」 로 끄면 색·설명 함께 사라짐."""
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
  const parts = [...k.querySelectorAll('.dv-chip, .panel-help, .dv-key-off')];
  return { shown: vis(k), has: row.classList.contains('has-dv-key'), chips: [...k.querySelectorAll('.dv-chip')].map((c) => [c.dataset.dv, c.textContent]),
    name: vis(k.querySelector('.dv-key-name')), tone: vis(k.querySelector('.dv-key-tone')), mode: vis(row.querySelector('.document-mode')),
    help: (k.querySelector('.panel-help') || { dataset: {} }).dataset.help || '', off: (k.querySelector('.dv-key-off') || {}).textContent || '',
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

        # ---- 2. 켬 — 칩 = 문서에 있는 구분(겉 → 안) · 문서와 같은 색 · 노트 · 감추기
        page.click("#divMarksBar .dv-marks-toggle")
        page.wait_for_function("() => document.querySelectorAll('#doc .para.dv-in').length > 0", timeout=120000)
        k = page.evaluate(KEY)
        dims = sorted(page.evaluate(DOC_DIMS), key=ORDER.index)
        check("켜면 문서 이름 줄에 색 설명(「편집 중」 바로 앞)", k["shown"] and k["has"] and k["beforeMode"], k)
        check("칩 = 문서에 색이 입혀진 구분 전부(겉 → 안 · 이름만)", [c[0] for c in k["chips"]] == dims and all(c[1] == NAMES[c[0]] for c in k["chips"]) and len(dims) >= 3, (k["chips"], dims))
        same = page.evaluate("""() => [...document.querySelectorAll('#divKey .dv-chip')].every((c) => { const p = document.querySelector(`#doc .para.dv-in[data-dv="${c.dataset.dv}"]`);
          return !!p && getComputedStyle(c).getPropertyValue('--dv-line').trim() === getComputedStyle(p).getPropertyValue('--dv-line').trim() && getComputedStyle(c, '::before').backgroundColor !== 'rgba(0, 0, 0, 0)'; })""")
        check("칩 색 = 문서의 그 구분 색", same)
        check("「구분 기준 자리」 · 「진한 줄 = 라벨」 · 노트(색마다 구분 · 진한/옅은 · 가장 안쪽 · 다시 켜는 곳) · 「감추기」", k["name"] and k["tone"] and k["off"] == "감추기"
              and all(s in k["help"] for s in ("파랑 단계", "주황 기관", "진한 색 + 왼쪽 띠", "옅은 색", "가장 안쪽", "다시 보려면")), k["help"][:200])
        check("줄을 더 쓰지 않음 — 이름 줄 높이 그대로 · 넘침 없음 · 칩·노트·감추기가 줄 안", k["rowH"] == k0["rowH"] and not k["over"] and k["inside"], (k0["rowH"], k["rowH"], k["rowW"]))
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

        # ---- 5. 폭 — 좁으면 이름·「진한 줄 = 라벨」 → 「편집 중」 차례로 감춤(줄 폭 기준) · 칩·노트·감추기는 남음
        seen = []
        for width in (1600, 1360, 1180, 1000, 880):
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(350)
            k = page.evaluate(KEY)
            seen.append((width, k["rowW"], k["rowH"], k["name"], k["mode"]))
            # 감춤 문턱은 줄의 안쪽 폭(@container — 좌우 여백 뺀 폭): 760px 이하 = 이름·「진한 줄 = 라벨」 감춤 · 560px 이하 = 「편집 중」 도 감춤
            check(f"창 {width}px(줄 {k['rowW']}px) — 넘침 없음 · 칩·노트·감추기 다 보임 · 감춤 차례가 줄 폭과 맞음", k["shown"] and not k["over"] and k["inside"] and len(k["chips"]) == len(dims)
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

        # ---- 7. 「감추기」 — 색·설명 함께 사라지고 카드 단추는 「보기」 · 기억
        page.click("#divKey .dv-key-off")
        k = page.evaluate(KEY)
        check("「감추기」 → 문단 색 없음 · 설명 없음 · 「편집 중」 다시 · 카드 단추 「보기」 · 기억(off)", not k["shown"] and not k["has"] and k["mode"]
              and page.evaluate("() => document.querySelectorAll('#doc .para.dv-in').length") == 0 and page.inner_text("#divMarksBar .dv-marks-toggle").strip() == "보기"
              and page.evaluate("() => localStorage.getItem('nfm.divMarks')") == "off", k)
        page.click("#divMarksBar .dv-marks-toggle")
        page.wait_for_function("() => document.querySelectorAll('#doc .para.dv-in').length > 0", timeout=60000)
        check("카드에서 다시 「보기」 → 설명 다시", page.evaluate(KEY)["shown"] and len(page.evaluate(KEY)["chips"]) == len(dims))

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

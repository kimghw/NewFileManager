"""편집 구역(spec_구역 ② §6 「화면」 — app/static/zones.js) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_zones_ui.py <그림·임시 폴더> [--port 18397]

연구개발계획서 양식을 TASK 「사업계획서 양식 표준화」(plan_fit — 편집 구역의 기본값은 켠 것 없음) 작업으로 올리고 프로젝트 구성(기관 셋 · 2차년도)을 구분 기준 API 로 반영한 뒤 본다(끝점은 모두 진짜):
「작업 내용」 의 「편집 구역」 줄(체크 셋 — 기본은 모두 꺼짐 · 안내 한 줄 · 「구분 기준 자리 표시」 줄 아래) · 켠 기준이 없으면 오른쪽 단추 메뉴에 항목 없음 → 기관을 켜면(PUT …/task-options {zones:{dims}, rev}) 칩·띠·오른쪽 여백 이름표 →
차년도를 더 켜면 이름표 글에 차년도 → 문서 이름 줄의 색 설명(칩 색 = 문서의 띠 색 · 「감추기」 · 줄 높이 그대로 · 「구분 기준 자리」 설명과 함께) → 문단을 골라 「구역 지정…」(떠 있는 작은 입력 #zonesPop — 「그대로」 만이면 안 됨 · Esc)
으로 기관을 정하면 그 문단의 이름표가 바뀌고 점선 테(.gz-mark) → 「구역 지정 고치기…」 → 표 칸에서는 「이 표를 구역으로 지정…」 → 여러 문단을 골라 차년도 지정 → 「지정 해제」 → 목록(2열 kind zones — 줄을 누르면 그 자리로 · 「해제」) →
「감추기」 하면 표시가 모두 사라짐(기억) → 글을 고치면 잠깐 뒤 다시 읽음 → 새로 고쳐도 옵션이 남음 → 배율을 바꾼 뒤에도 표시가 다시 달림 → 다른 화면이 옵션을 먼저 바꿨으면 409 → 다시 읽고 알림. 콘솔 오류 0."""
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
ap.add_argument("--port", type=int, default=18397)
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
errors, fails, sent = [], [], []
LEAD, SEED, UANGEL = "한국선급", "씨드로닉스", "유엔젤"
VALUES = {"stages": [2], "orgs": {"lead": LEAD, "joint": [SEED, UANGEL], "nonprofit": [False, False, False]}, "period": {"start": "2026-03-01", "end": "2027-12-31"}, "current": 1}
ZONE_SEL = "#doc .gz-in, #doc .gz-put, #doc .gz-cell, #doc .gz-tag"
SETTLE = 400   # 문서를 스크롤한 뒤 오른쪽 단추 메뉴를 열기까지 기다리는 시간(ms) — 늦게 오는 scroll 이벤트가 연 메뉴를 닫지 않게(같이 도는 검사의 부하에서도)


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:500] if detail != "" else ""), flush=True)
    if not ok:
        fails.append(name)


def flat(s):
    return re.sub(r"\s+", " ", s or "").strip()


READY = "() => typeof zn === 'function' && !zn().loading && !zn().optBusy && (!!zn().opt || !!zn().data)"   # 옵션(또는 구역)을 읽었고 읽는 중이 아님
BAR = """() => { const b = document.getElementById('zonesBar'), prev = b && b.previousElementSibling;
  return { shown: !!b && !b.hidden && b.getClientRects().length > 0, cls: b ? b.className : '', after: prev ? prev.id : '', over: !!b && b.scrollWidth > b.clientWidth + 1,
    dims: [...b.querySelectorAll('input[data-zones-dim]')].map((c) => [c.dataset.zonesDim, c.checked, c.disabled]), names: [...b.querySelectorAll('.zn-dim')].map((l) => l.textContent),
    toggle: b.querySelector('[data-zones=toggle]').getAttribute('aria-pressed'), toggleText: b.querySelector('[data-zones=toggle]').textContent, list: !!b.querySelector('[data-zones=list]'),
    title: b.querySelector('.zn-copy strong').textContent, help: b.querySelector('.zn-copy .panel-help').dataset.help, text: b.querySelector('.gt-zones-chips').textContent,
    chips: [...b.querySelectorAll('.gz-chip')].map((c) => ({ org: c.dataset.org || '', year: c.dataset.year || '', stage: c.dataset.stage || '', gz: c.dataset.gz || '', text: c.textContent })) }; }"""
DOC = """() => ({ ins: document.querySelectorAll('#doc .gz-in').length, tags: [...document.querySelectorAll('#doc .sheet > .gz-tag')].map((t) => ({ text: t.textContent, gz: t.dataset.gz, mark: t.classList.contains('gz-mark'), title: t.title })),
  cells: document.querySelectorAll('#doc td.gz-cell').length, puts: document.querySelectorAll('#doc .gz-put').length, cls: [document.getElementById('doc').className, document.body.className].join(' '),
  tips: [...document.querySelectorAll('#doc .gz-in')].slice(0, 40).map((e) => e.title) })"""
KEY = """() => { const k = document.getElementById('zonesKey'), row = document.getElementById('fileInfo'), vis = (e) => !!e && e.getClientRects().length > 0, rr = row.getBoundingClientRect();
  const inside = (e) => { const r = e.getBoundingClientRect(); return r.left >= rr.left - 1 && r.right <= rr.right + 1 && r.top >= rr.top - 1 && r.bottom <= rr.bottom + 1; };
  const parts = [...k.querySelectorAll('.zn-key-chip, .panel-help, .dv-key-off')].filter(vis);
  return { shown: vis(k), has: row.classList.contains('has-zn-key'), chips: [...k.querySelectorAll('.zn-key-chip')].filter(vis).map((c) => [c.dataset.gz, c.textContent]),
    name: vis(k.querySelector('.dv-key-name')) ? k.querySelector('.dv-key-name').textContent : '', tone: vis(k.querySelector('.zn-key-tone')), off: (k.querySelector('.dv-key-off') || {}).textContent || '',
    help: (k.querySelector('.panel-help') || { dataset: {} }).dataset.help || '', inside: parts.length > 0 && parts.every(inside), rowH: Math.round(rr.height), over: row.scrollWidth > row.clientWidth + 1,
    beforeDiv: !!k.nextElementSibling && k.nextElementSibling.id === 'divKey' }; }"""
MENU = "() => { const m = document.querySelector('.ctx-menu'); return m && !m.hidden ? [...m.querySelectorAll('button')].map((b) => b.textContent) : []; }"
POP = """() => { const p = document.getElementById('zonesPop'); if (!p) return null;
  return { role: p.getAttribute('role'), label: p.getAttribute('aria-label'), title: p.querySelector('strong').textContent, text: p.querySelector('.dv-pop-text').textContent, caption: (p.querySelector('.dv-caption') || {}).textContent || '',
    sels: Object.fromEntries([...p.querySelectorAll('select[data-zn-dim]')].map((s) => [s.dataset.znDim, { value: s.value, opts: [...s.options].map((o) => [o.value, o.textContent]) }])),
    fields: [...p.querySelectorAll('.dv-field > span')].map((s) => s.textContent), acts: [...p.querySelectorAll('.dv-pop-acts button')].map((b) => b.textContent), note: p.querySelector('input[type=text]').value,
    picked: [...new Set([...document.querySelectorAll('#doc .zn-pick')].map((e) => e.dataset.id || e.dataset.tbl))], modal: p.tagName === 'DIALOG' }; }"""
TOAST = "() => { const t = document.getElementById('toast'); return t.hidden ? '' : t.textContent; }"

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
    a = requests.post(f"{base}/api/docs?new=1", files={"file": ("구역_사업계획서.hwpx", form.read_bytes())}, timeout=300).json()["docId"]
    requests.put(f"{base}/api/works/{a}/task", json={"kind": "rnd", "file": "plan", "job": "plan_fit", "project": "ZONES"}, timeout=30).raise_for_status()
    requests.put(f"{base}/api/docs/{a}/divisions/settings", json={"values": VALUES}, timeout=60).raise_for_status()
    requests.post(f"{base}/api/docs/{a}/divisions/confirm", json={"values": VALUES}, timeout=60).raise_for_status()
    dplan = requests.post(f"{base}/api/docs/{a}/divisions/plan", json={}, timeout=600).json()
    requests.post(f"{base}/api/docs/{a}/divisions/apply", json={"planId": dplan["planId"]}, timeout=600).raise_for_status()

    def zones_api():
        r = requests.get(f"{base}/api/docs/{a}/zones", timeout=300)
        r.raise_for_status()
        return r.json()

    def options_api():
        return requests.get(f"{base}/api/works/{a}/task-options", timeout=30).json()

    z0, o0 = zones_api(), options_api()
    KEYS = {o["name"]: o["key"] for o in z0["orgs"]}
    check("[끝점] GET …/zones — 연구개발 문서 · 기본은 켠 기준 없음(띠 없음) · 값은 반영한 것 · 기관 셋 · 블록의 값은 옵션과 무관하게 실림", z0["options"]["offered"] is True and z0["options"]["zones"] == {"dims": [], "defaulted": True}
          and z0["zones"] == [] and z0["basis"] == "applied" and [o["name"] for o in z0["orgs"]] == [LEAD, SEED, UANGEL] and z0["stages"] == [2] and len(z0["blocks"]) > 0 and z0["reasons"] == []
          and o0 == z0["options"], {k: z0.get(k) for k in ("options", "basis", "orgs", "stages", "counts", "reasons")})
    blocks = requests.get(f"{base}/api/docs/{a}", timeout=120).json()["blocks"]
    tops = [b for b in blocks if not b.get("captionOf")]
    para = lambda b: b["type"] == "paragraph" and flat(b.get("text"))   # noqa: E731
    free = lambda b: b["id"] not in z0["blocks"]                       # noqa: E731 — 기관·단계·차년도가 안 걸린 자리(공통)
    i0 = next((i for i in range(len(tops) - 2) if all(para(tops[i + k]) and free(tops[i + k]) for k in range(3))), None)
    if i0 is None:
        i0 = next(i for i in range(len(tops) - 2) if all(para(tops[i + k]) for k in range(3)))
    P1, P2, P3 = (tops[i0 + k]["id"] for k in range(3))
    T1 = next(b["id"] for b in tops if b["type"] == "table" and b.get("cells"))
    print(f"INFO 문서 {a} · 지정할 문단 {P1}·{P2}·{P3}(「{flat(tops[i0].get('text'))[:30]}」 …) · 표 {T1} · 값이 걸린 블록 {len(z0['blocks'])}", flush=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)

        def on_req(r):   # 화면이 보낸 옵션·지정 요청(몸통) — 읽기는 수만 센다
            if "/api/" in r.url and ("/task-options" in r.url or "/zones" in r.url):   # /static/zones.js 는 아니다
                sent.append((r.method, r.url.split("/api/", 1)[1], r.post_data_json if r.method in ("POST", "PUT") and r.post_data else None))
        page.on("request", on_req)
        page.goto(base)
        page.evaluate("() => { try { for (const k of ['nfm.zones', 'nfm.gatherZones', 'nfm.divMarks', 'nfm.fileFold']) localStorage.removeItem(k); } catch {} }")

        def open_work():
            page.evaluate("(id) => { location.hash = '#w=' + id; }", a)
            page.reload()
            page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=a, timeout=180000)
            page.click("#toolTabTask")
            page.wait_for_selector("#zonesBar")
            page.wait_for_function(READY, timeout=120000)

        def menu_at(pid, pick=None):   # 그 문단에서 오른쪽 단추 → 메뉴 항목 글(pick 이면 그 항목을 누른다)
            page.evaluate("(id) => paraEl(id).scrollIntoView({ block: 'center' })", pid)
            page.wait_for_timeout(SETTLE)   # 스크롤 알림(scroll 이벤트)이 지나간 뒤에 — 메뉴는 문서가 스크롤되면 닫힌다(app.js bindCtxMenu)
            page.click(f'#doc .para[data-id="{pid}"]', button="right")
            page.wait_for_function(f"() => ({MENU})().length > 0")
            items = page.evaluate(MENU)
            if pick:
                page.locator(".ctx-menu button", has_text=pick).first.click()
            return items

        def tag_of(pid):   # 그 블록에서 시작하는 띠의 이름표(같은 쪽 · 같은 높이의 것) | None
            return page.evaluate("""(id) => { const p = paraEl(id), sheet = p && p.closest('.sheet'); if (!sheet) return null; const top = p.getBoundingClientRect().top;
              const t = [...sheet.querySelectorAll(':scope > .gz-tag')].map((x) => [Math.abs(x.getBoundingClientRect().top - top), x]).sort((a, b) => a[0] - b[0])[0];
              return t && t[0] < 40 ? { text: t[1].textContent, mark: t[1].classList.contains('gz-mark'), llm: t[1].classList.contains('gz-llm'), gz: t[1].dataset.gz, title: t[1].title } : null; }""", pid)

        open_work()

        # ---- 1. 줄 — 체크 셋(기본은 모두 꺼짐) · 안내 한 줄 · 「구분 기준 자리 표시」 줄 아래 · 문서에는 아무 표시 없음
        b0, d0, k0 = page.evaluate(BAR), page.evaluate(DOC), page.evaluate(KEY)
        check("「편집 구역」 줄 — 「구분 기준 자리 표시」 줄 아래 · 이름 + 노트 · 「구역 표시」 보기/감추기(기본 켬) · 「목록」", b0["shown"] and "zn-bar" in b0["cls"] and "gt-zones" in b0["cls"] and b0["after"] == "divMarksBar"
              and b0["title"] == "편집 구역" and b0["toggle"] == "true" and b0["toggleText"] == "구역 표시 감추기" and b0["list"] and not b0["over"], b0)
        check("체크 셋(기관 · 단계 · 차년도) — 기본은 모두 꺼짐 · 꺼져 있어도 보임 · 칩 대신 안내 한 줄", b0["dims"] == [["org", False, False], ["stage", False, False], ["year", False, False]]
              and b0["names"] == ["기관", "단계", "차년도"] and "기관·단계·차년도를 켜면 문서에서 그 값의 구역을 가려 보입니다" in b0["text"] and not b0["chips"], (b0["dims"], b0["text"]))
        check("노트 — 무엇을 보이나 · 화면 표시일 뿐(파일은 그대로) · 「구역 지정…」 · 취합으로 들어온 내용", all(s in b0["help"] for s in ("어느 기관·단계·차년도의 것인지", "화면 표시일 뿐", "내려받는 파일은 그대로", "「구역 지정…」", "어느 기관 문서에서 왔는지")), b0["help"][:200])
        check("켠 기준이 없으면 문서에 표시 없음 · 이름 줄 설명 없음 · #doc·body 에 표시용 클래스 없음", d0["ins"] == 0 and not d0["tags"] and not k0["shown"] and not k0["has"] and "gz" not in d0["cls"] and "zn" not in d0["cls"], (d0["ins"], k0))
        gets = [s[1] for s in sent if s[0] == "GET"]
        check("켠 기준이 없으면 구역을 세지 않음 — 문서를 열 때 옵션만 읽음(GET …/task-options · GET …/zones 없음)", f"works/{a}/task-options" in gets and not any(g.endswith("/zones") for g in gets), gets)
        items = menu_at(P1)
        check("켠 기준이 없으면 오른쪽 단추 메뉴에 「구역 지정…」 이 없음(구분 기준 자리 항목은 그대로)", not any("구역" in t and "지정" in t for t in items) and any("구분 기준 자리" in t for t in items), items)
        page.keyboard.press("Escape")
        page.locator("#zonesBar").screenshot(path=str(OUT / "1_bar_off.png"))

        # ---- 2. 기관을 켬 — PUT …/task-options {zones:{dims}, rev} → 칩 · 띠 · 오른쪽 여백 이름표
        n_put = len(sent)
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task-options") and r.request.method == "PUT"):
            page.click("#zonesBar input[data-zones-dim=org]")   # check() 가 아니라 click — 저장하는 동안 줄이 다시 그려져 체크 상자 요소가 바뀐다
        page.wait_for_function("() => document.querySelectorAll('#zonesBar .gz-chip[data-org]').length >= 3 && !!document.querySelector('#doc .gz-in') && !!document.querySelector('#doc .sheet > .gz-tag')", timeout=120000)
        page.wait_for_function(READY)
        put = [s for s in sent[n_put:] if s[0] == "PUT"]
        b, d, z1 = page.evaluate(BAR), page.evaluate(DOC), zones_api()
        check("기관 체크 → PUT …/task-options {zones:{dims:[org]}, rev, scope(읽어 둔 TASK 묶음)} · 서버에 적힘(defaulted false) · 체크가 켜진 채", len(put) == 1 and put[0][2] == {"zones": {"dims": ["org"]}, "rev": o0["rev"], "scope": o0["scope"]}
              and z1["options"]["zones"] == {"dims": ["org"], "defaulted": False} and b["dims"] == [["org", True, False], ["stage", False, False], ["year", False, False]], (put, z1["options"], b["dims"]))
        org_chips = {c["org"]: c for c in b["chips"] if c["org"]}
        n_zone = {k: sum(1 for z in z1["zones"] if z["label"]["orgKind"] == "org" and z["label"]["org"] == k) for k in KEYS.values()}
        check("칩 — 기관마다(주관 → 공동 차례의 색 0·1·2) 「<이름> 구역 n」 · n = 그 기관의 띠 수", all(k in org_chips for k in KEYS.values()) and [org_chips[KEYS[n]]["gz"] for n in (LEAD, SEED, UANGEL)] == ["0", "1", "2"]
              and all(org_chips[KEYS[n]]["text"] == f"{n} 구역 {n_zone[KEYS[n]]}" for n in KEYS) and all(v > 0 for v in n_zone.values()), (b["chips"], n_zone))
        names = {t["text"] for t in d["tags"]}
        check("문서 — 띠(.gz-in) · 띠마다 쪽 오른쪽 여백 이름표(글 = 서버의 이름표 글 · 기관 이름) · 도움말 「편집 구역 — …」 · 자동으로 읽은 띠는 점선 테 아님", d["ins"] > 0 and len(d["tags"]) == len(z1["zones"])
              and names == {z["text"] for z in z1["zones"]} and {LEAD, SEED, UANGEL} <= names and all(t.startswith("편집 구역 — ") for t in d["tips"]) and not any(t["mark"] for t in d["tags"])
              and "gz" not in d["cls"], (len(d["tags"]), len(z1["zones"]), sorted(names)))
        look = page.evaluate("""() => { const p = document.querySelector('#doc .para.gz-in:not(.edited)'); if (!p) return null; const s = getComputedStyle(p), out = { image: s.backgroundImage, shadow: s.boxShadow };   // 계산 값은 살아 있는 객체 — 먼저 적어 둔다
          p.classList.add('edited'); const e = getComputedStyle(p); Object.assign(out, { editedImage: e.backgroundImage, editedShadow: e.boxShadow, editedColor: e.backgroundColor }); p.classList.remove('edited'); return out; }""")
        check("문단의 띠 = 배경 그림 층(box-shadow 아님) — 고친 문단 표시(왼쪽 띠 box-shadow · 바탕색)와 함께 보임", look and "gradient" in look["image"] and look["shadow"] == "none" and "gradient" in look["editedImage"]
              and look["editedShadow"] != "none" and look["editedColor"] not in ("rgba(0, 0, 0, 0)", "transparent"), look)
        page.locator("#zonesBar").screenshot(path=str(OUT / "2_bar_org.png"))

        # ---- 3. 차년도를 더 켬 — 이름표 글에 차년도 · 차년도 칩(색 없음 — 색 축은 기관)
        n_put = len(sent)
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task-options") and r.request.method == "PUT"):
            page.click("#zonesBar input[data-zones-dim=year]")
        page.wait_for_function("() => [...document.querySelectorAll('#doc .sheet > .gz-tag')].some((t) => t.textContent.includes('차년도')) && !!document.querySelector('#zonesBar .gz-chip[data-year]')", timeout=120000)
        page.wait_for_function(READY)
        put = [s for s in sent[n_put:] if s[0] == "PUT"]
        b, d, z2 = page.evaluate(BAR), page.evaluate(DOC), zones_api()
        year_chips = [c for c in b["chips"] if c["year"]]
        check("차년도 체크 → PUT {dims:[org, year]}(늘 기관 · 단계 · 차년도 차례) · 이름표 글에 차년도(「한국선급 · 1차년도」) · 차년도 칩은 색 없음(색 축은 기관 하나)", len(put) == 1 and put[0][2]["zones"] == {"dims": ["org", "year"]}
              and put[0][2]["rev"] == z1["options"]["rev"] and put[0][2].get("scope") == o0["scope"] and {t["text"] for t in d["tags"]} == {z["text"] for z in z2["zones"]} and any(re.fullmatch(rf"({LEAD}|{SEED}|{UANGEL}) · \d차년도", t["text"]) for t in d["tags"])
              and year_chips and all(c["gz"] == "" and re.fullmatch(r"\d차년도 구역 \d+", c["text"]) for c in year_chips), (put, sorted({t["text"] for t in d["tags"]})[:8], year_chips))

        for width in (320, 480):   # 패널 최소 폭·보통 폭에서 가로 넘침 없음(design.md §1-8) — 머리의 단추·체크·칩이 줄 안
            page.evaluate("(w) => document.getElementById('panel').style.setProperty('--panel', w + 'px')", width)
            page.wait_for_timeout(250)
            fit = page.evaluate("""() => { const b = document.getElementById('zonesBar'), r = b.getBoundingClientRect(), pane = document.getElementById('paneDiv');
              const parts = [...b.querySelectorAll('button, input, .zn-dim, .gz-chip')]; return { w: Math.round(r.width), over: b.scrollWidth > b.clientWidth + 1, pane: pane.scrollWidth > pane.clientWidth + 1,
                inside: parts.every((e) => { const x = e.getBoundingClientRect(); return x.left >= r.left - 1 && x.right <= r.right + 1; }), h: [...b.querySelectorAll('.gt-zones-head .btn')].map((e) => Math.round(e.getBoundingClientRect().height)) }; }""")
            check(f"패널 {width}px — 「편집 구역」 줄이 넘치지 않음 · 단추·체크·칩이 줄 안 · 단추 높이 28px", not fit["over"] and not fit["pane"] and fit["inside"] and len(fit["h"]) >= 2 and all(h == 28 for h in fit["h"]), fit)   # 머리 단추 = (LLM 검토 · 지침 ·) 구역 표시 · 목록
            page.locator("#zonesBar").screenshot(path=str(OUT / f"3_bar_w{width}.png"))
        page.evaluate("() => document.getElementById('panel').style.removeProperty('--panel')")
        page.wait_for_timeout(250)

        # ---- 4. 문서 이름 줄의 색 설명 — 「편집 구역」 + 지금 문서에 있는 값의 칩(문서의 띠 색) + 노트 + 「감추기」 · 줄 높이 그대로
        k = page.evaluate(KEY)
        same = page.evaluate("""() => [...document.querySelectorAll('#zonesKey .zn-key-chip')].every((c) => { const p = document.querySelector(`#doc .gz-in[data-gz="${c.dataset.gz}"]`);
          return !!p && getComputedStyle(c).getPropertyValue('--gz-c').trim() === getComputedStyle(p).getPropertyValue('--gz-c').trim() && getComputedStyle(c, '::before').backgroundColor !== 'rgba(0, 0, 0, 0)'; })""")
        check("이름 줄 색 설명 — 「편집 구역」 · 기관 칩(주관 → 공동 · 색 = 문서의 띠 색) · 노트 · 「감추기」 · 「구분 기준 자리」 설명 앞", k["shown"] and k["has"] and k["name"] == "편집 구역" and [c[1] for c in k["chips"]] == [LEAD, SEED, UANGEL]
              and [c[0] for c in k["chips"]] == ["0", "1", "2"] and same and k["off"] == "감추기" and "화면 표시일 뿐" in k["help"] and "다시 보려면" in k["help"] and k["beforeDiv"], k)
        check("줄을 더 쓰지 않음 — 이름 줄 높이 그대로 · 넘침 없음 · 칩·노트·감추기가 줄 안", k["rowH"] == k0["rowH"] and not k["over"] and k["inside"], (k0["rowH"], k["rowH"]))
        page.click("#divMarksBar .dv-marks-toggle")   # 「구분 기준 자리」 색 설명과 함께
        page.wait_for_function("() => !document.getElementById('divKey').hidden && document.querySelectorAll('#doc .para.dv-in').length > 0", timeout=120000)
        kb = page.evaluate(KEY)
        check("「구분 기준 자리」 설명과 함께 있어도 넘치지 않음 — 두 설명 모두 보이고 칩·노트·감추기가 줄 안", kb["shown"] and not kb["over"] and kb["inside"] and page.evaluate("() => document.getElementById('divKey').getClientRects().length > 0"), kb)
        page.screenshot(path=str(OUT / "4_key_both.png"), clip={"x": 0, "y": 0, "width": 1600, "height": 300})
        page.click("#divMarksBar .dv-marks-toggle")
        page.wait_for_function("() => document.getElementById('divKey').hidden")
        for width in (1280, 1000):
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(350)
            kw = page.evaluate(KEY)
            check(f"창 {width}px — 색 설명이 넘치지 않고 칩·노트·감추기가 줄 안", kw["shown"] and not kw["over"] and kw["inside"] and len(kw["chips"]) >= 1, kw)
        page.set_viewport_size({"width": 1600, "height": 900})
        page.wait_for_timeout(350)

        # ---- 5. 「구역 지정…」 — 문단에서 오른쪽 단추 → 떠 있는 작은 입력(모달 아님) → 기관을 정하면 이름표가 바뀌고 점선 테
        t_before = tag_of(P1)
        items = menu_at(P1, "구역 지정…")
        page.wait_for_selector("#zonesPop")
        p = page.evaluate(POP)
        check("오른쪽 단추 메뉴 「구역 지정…」 → 입력(#zonesPop — 모달 아님): 대상(문단 1 + 첫 글) · 켠 기준마다 고르기(「그대로」 · 값 · 「없음」) · 메모 · 「지정」/「취소」", "구역 지정…" in items and p and p["role"] == "dialog"
              and not p["modal"] and p["title"] == "구역 지정" and p["text"].startswith("문단 1 — 「") and p["fields"] == ["기관", "차년도", "메모(선택)"] and p["acts"] == ["지정", "취소"] and p["picked"] == [P1]
              and [o[0] for o in p["sels"]["org"]["opts"]] == ["=", *[f"v:{KEYS[n]}" for n in (LEAD, SEED, UANGEL)], "-"] and p["sels"]["org"]["opts"][0][1].startswith("그대로") and p["sels"]["org"]["opts"][-1][1] == "기관 없음"
              and [o[1] for o in p["sels"]["year"]["opts"]][1:-1] == ["1차년도", "2차년도"] and p["sels"]["org"]["value"] == "=" and page.evaluate("() => document.activeElement.dataset.znDim") == "org", p)
        page.screenshot(path=str(OUT / "5_pop.png"))
        n_req = len(sent)
        page.click("#zonesPop [data-zones=mark-ok]")
        check("모두 「그대로」 면 지정하지 않음 — 알림 · 요청 없음 · 입력은 그대로", "하나는 골라야" in page.evaluate(TOAST) and page.locator("#zonesPop").count() == 1 and not [s for s in sent[n_req:] if s[0] != "GET"], page.evaluate(TOAST))
        page.keyboard.press("Escape")
        check("Esc → 입력 닫힘 · 대상 범위 표시도 걷힘", page.locator("#zonesPop").count() == 0 and page.locator("#doc .zn-pick").count() == 0)
        menu_at(P1, "구역 지정…")
        page.wait_for_selector("#zonesPop")
        page.select_option("#zonesPop select[data-zn-dim=org]", f"v:{KEYS[SEED]}")
        page.fill("#zonesPop input[type=text]", "공동1 이 맡은 절")
        rev = page.evaluate("() => [state.serverRev, zn().data.zonesRev]")
        n_req = len(sent)
        with page.expect_response(lambda r: r.url.endswith(f"/api/docs/{a}/zones/marks") and r.request.method == "POST"):
            page.keyboard.press("Enter")   # Enter = 저장
        page.wait_for_function("() => !document.getElementById('zonesPop') && !!document.querySelector('#doc .sheet > .gz-tag.gz-mark')", timeout=60000)
        post = [s for s in sent[n_req:] if s[0] == "POST"]
        z3, t1 = zones_api(), tag_of(P1)
        check("기관을 정하고 Enter → POST …/zones/marks {ids, label{org}, note, docRev, zonesRev} · 문서는 안 바뀜(편집 차례 그대로) · 구역 판 +1", len(post) == 1 and post[0][2] == {"ids": [P1], "label": {"org": KEYS[SEED]}, "note": "공동1 이 맡은 절", "docRev": rev[0], "zonesRev": rev[1]}
              and z3["rev"] == rev[0] and z3["zonesRev"] == rev[1] + 1 and len(z3["marks"]) == 1 and z3["marks"][0]["ids"] == [P1] and z3["marks"][0]["label"] == {"org": KEYS[SEED]}, (post, z3["marks"]))
        gz1 = page.evaluate("(id) => { const p = paraEl(id); return [p.classList.contains('gz-in'), p.dataset.gz, p.title]; }", P1)
        check("그 문단 — 띠가 그 기관 색 · 이름표가 그 기관 이름으로 바뀌고 점선 테(.gz-mark) · 도움말에 「사람이 지정」 · 줄에 「지정 1」 칩", gz1[0] and gz1[1] == "1" and t1 and t1["text"].startswith(SEED) and t1["mark"]
              and "사람이 지정" in t1["title"] and "사람이 지정" in gz1[2] and (t_before or {}).get("text") != t1["text"] and any(c["text"] == "지정 1" for c in page.evaluate(BAR)["chips"])
              and SEED in page.evaluate(TOAST), (t_before, t1, gz1, page.evaluate(TOAST)))
        page.evaluate("(id) => paraEl(id).scrollIntoView({ block: 'center' })", P1)
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "5_marked.png"))

        # ---- 6. 「구역 지정 고치기…」 — 지정된 블록에서는 고치기 · 해제
        items = menu_at(P1, "구역 지정 고치기…")
        page.wait_for_selector("#zonesPop")
        p = page.evaluate(POP)
        check("지정된 문단의 메뉴 = 「구역 지정 고치기…」 · 「지정 해제」(「구역 지정…」 은 없음) · 입력에 지금 값·메모", "구역 지정 고치기…" in items and "지정 해제" in items and "구역 지정…" not in items and p["title"] == "구역 지정 고치기"
              and p["sels"]["org"]["value"] == f"v:{KEYS[SEED]}" and p["sels"]["year"]["value"] == "=" and p["note"] == "공동1 이 맡은 절" and p["acts"] == ["고치기", "취소"], (items, p))
        page.select_option("#zonesPop select[data-zn-dim=org]", f"v:{KEYS[UANGEL]}")
        n_req = len(sent)
        with page.expect_response(lambda r: "/zones/marks/" in r.url and r.request.method == "PUT"):
            page.click("#zonesPop [data-zones=mark-ok]")
        page.wait_for_function("() => !document.getElementById('zonesPop')")
        page.wait_for_function(READY)
        puts = [s for s in sent[n_req:] if s[0] == "PUT"]
        z4, t2 = zones_api(), tag_of(P1)
        mid = z3["marks"][0]["id"]
        check("고치기 → PUT …/zones/marks/<id> {label, note, docRev, zonesRev}(ids 는 안 보냄) · 이름표가 새 기관으로", len(puts) == 1 and puts[0][1].endswith(f"/zones/marks/{mid}") and puts[0][2]["label"] == {"org": KEYS[UANGEL]}
              and "ids" not in puts[0][2] and puts[0][2]["zonesRev"] == z3["zonesRev"] and z4["marks"][0]["id"] == mid and z4["marks"][0]["label"] == {"org": KEYS[UANGEL]} and z4["marks"][0]["note"] == "공동1 이 맡은 절"
              and t2 and t2["text"].startswith(UANGEL) and t2["mark"] and t2["gz"] == "2", (puts, z4["marks"], t2))

        # ---- 7. 표 칸에서는 「이 표를 구역으로 지정…」 — 대상이 표라는 것을 항목 글이 말한다
        page.evaluate("(id) => document.querySelector(`#doc table.tbl[data-tbl=\"${id}\"]`).scrollIntoView({ block: 'center' })", T1)
        page.wait_for_timeout(SETTLE)
        page.locator(f'#doc table.tbl[data-tbl="{T1}"] td .para').first.click(button="right")
        page.wait_for_function(f"() => ({MENU})().length > 0")
        items = page.evaluate(MENU)
        page.locator(".ctx-menu button", has_text="이 표를 구역으로 지정…").first.click()
        page.wait_for_selector("#zonesPop")
        p = page.evaluate(POP)
        check("표 칸의 메뉴 = 「이 표를 구역으로 지정…」(「구역 지정…」 아님) → 대상 = 그 표 하나 · 「표 전체가 대상」 안내", "이 표를 구역으로 지정…" in items and "구역 지정…" not in items and p["text"].startswith("표 1 — ")
              and p["picked"] == [T1] and "이 표 전체가 대상" in p["caption"], (items[-6:], p["text"], p["caption"], p["picked"]))
        page.mouse.click(5, 880)   # 바깥을 누르면 닫힘
        check("바깥을 누르면 입력이 닫힘", page.locator("#zonesPop").count() == 0)
        page.keyboard.press("Escape")
        page.evaluate("() => { if (typeof tselClear === 'function') tselClear(); }")

        # ---- 8. 여러 문단을 골라 지정 — 고른 본문 문단들이 대상(사이를 끼워 넣지 않음) · 차년도만 지정
        page.evaluate("(id) => paraEl(id).scrollIntoView({ block: 'center' })", P2)
        page.wait_for_timeout(SETTLE)
        page.evaluate("""(ids) => { const a = paraEl(ids[0]), b = paraEl(ids[1]), s = getSelection(), r = document.createRange(); r.setStart(a, 0); r.setEnd(b, b.childNodes.length); s.removeAllRanges(); s.addRange(r);
          const rc = a.getBoundingClientRect(); a.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: rc.left + 30, clientY: rc.top + 6 })); }""", [P2, P3])
        page.wait_for_function(f"() => ({MENU})().length > 0")
        page.locator(".ctx-menu button", has_text="구역 지정…").first.click()
        page.wait_for_selector("#zonesPop")
        p = page.evaluate(POP)
        page.select_option("#zonesPop select[data-zn-dim=year]", "v:2")
        n_req = len(sent)
        with page.expect_response(lambda r: r.url.endswith(f"/api/docs/{a}/zones/marks") and r.request.method == "POST"):
            page.click("#zonesPop [data-zones=mark-ok]")
        page.wait_for_function("() => !document.getElementById('zonesPop')")
        page.wait_for_function(READY)
        post = [s for s in sent[n_req:] if s[0] == "POST"]
        z5, t3 = zones_api(), tag_of(P2)
        check("문단 둘을 골라 「구역 지정…」 → 대상 「문단 2」(고른 것 그대로) · 차년도만 지정 {year: 2} · 이름표 「2차년도」(점선 테) · 지정 2", p["text"].startswith("문단 2 — 「") and p["picked"] == [P2, P3]
              and len(post) == 1 and post[0][2]["ids"] == [P2, P3] and post[0][2]["label"] == {"year": 2} and len(z5["marks"]) == 2 and t3 and "2차년도" in t3["text"] and t3["mark"]
              and any(c["text"] == "지정 2" for c in page.evaluate(BAR)["chips"]), (p["text"], p["picked"], post, t3))

        # ---- 9. 목록(문서 옆 2열 — kind zones) — 값마다 묶음 · 지정 묶음 · 줄을 누르면 그 자리로 · 「해제」
        page.click("#zonesBar [data-zones=list]")
        page.wait_for_function("() => heads.dlg === 'zones' && !!document.querySelector('#headsDlgBody .gz-cap')")
        L = page.evaluate("""() => ({ kind: document.getElementById('headsDlg').dataset.kind, title: document.getElementById('headsDlgTitle').textContent, tools: document.getElementById('headsDlgTools').textContent,
          caps: [...document.querySelectorAll('#headsDlgBody .gz-cap')].map((c) => [c.dataset.znGroup, c.dataset.org || '', c.dataset.gz || '', c.textContent]),
          heads: [...document.querySelectorAll('#headsDlgBody table.gz-table')].map((t) => [...t.querySelectorAll('th')].map((h) => h.textContent).join('|')),
          marks: [...document.querySelectorAll('#headsDlgBody [data-zones=unmark]')].map((x) => [...x.closest('tr').children].map((td) => td.textContent)), modal: !!document.querySelector('dialog[open]') })""")
        org_caps = [c for c in L["caps"] if c[1] in KEYS.values()]
        check("「목록」 → 문서 옆 열(모달 아님) 「편집 구역」: 기관마다 묶음(색 띠 · 「<이름>(주관|공동) — 구역 n · 넣은 내용 0」) · 끝에 「지정 — 2」(값 · 블록 수 · 근거 「사람」 · 메모 · 「해제」 — LLM 지정이 없으면 「모두 해제」 없음)", L["kind"] == "zones" and L["title"] == "편집 구역" and not L["modal"]
              and [c[1] for c in org_caps] == [KEYS[n] for n in (LEAD, SEED, UANGEL)] and org_caps[0][3].startswith(f"{LEAD}(주관) — 구역 ") and org_caps[1][3].startswith(f"{SEED}(공동) — 구역 ") and all("넣은 내용 0" in c[3] for c in org_caps)
              and any(c[0] == "@marks" and c[3] == "지정 — 2" for c in L["caps"]) and len(L["marks"]) == 2 and L["marks"][0][:4] == [UANGEL, "블록 1", "사람", "공동1 이 맡은 절"]
              and L["marks"][1][:3] == ["2차년도", "블록 2", "사람"] and "구역 · 넣은 내용|자리|글|근거" in L["heads"] and "지정한 값|블록|근거|메모 · 까닭|" in L["heads"] and "지정 2" in L["tools"]
              and page.locator("#headsDlgBody [data-zones=llm-clear]").count() == 0, L)
        page.screenshot(path=str(OUT / "9_list.png"))
        first = page.evaluate("(k) => zn().data.zones.find((z) => z.label.orgKind === 'org' && z.label.org === k && !z.mark).ids[0]", KEYS[LEAD])
        page.evaluate("() => document.getElementById('scroller').scrollTo(0, document.getElementById('scroller').scrollHeight)")
        page.locator(f'#headsDlgBody .gz-cap[data-org="{KEYS[LEAD]}"] + table tr.go').first.click()
        page.wait_for_function("""(id) => { const t = document.querySelector(`#doc table.tbl[data-tbl="${id}"]`), p = t ? t.querySelector('.para[data-id]') : paraEl(id); if (!p) return false;
          const r = p.getBoundingClientRect(), s = document.getElementById('scroller').getBoundingClientRect(); return p.classList.contains('flash') && r.bottom > s.top && r.top < s.bottom; }""", arg=first, timeout=30000)
        check("목록의 구역 줄을 누르면 문서가 그 자리로(열은 열린 채)", page.evaluate("() => heads.dlg") == "zones")
        n_req = len(sent)
        with page.expect_response(lambda r: "/zones/marks/" in r.url and r.request.method == "DELETE"):
            page.locator("#headsDlgBody [data-zones=unmark]").nth(1).click()
        page.wait_for_function("() => zn().data.marks.length === 1 && !zn().loading && document.querySelectorAll('#headsDlgBody [data-zones=unmark]').length === 1")
        dele = [s for s in sent[n_req:] if s[0] == "DELETE"]
        check("목록의 「해제」 → DELETE …/zones/marks/<id>?zonesRev=n · 목록이 그 자리에서 다시 그려짐(지정 — 1)", len(dele) == 1 and dele[0][1].endswith(f"?zonesRev={z5['zonesRev']}") and f"/zones/marks/{z5['marks'][1]['id']}" in dele[0][1]
              and page.evaluate("() => [...document.querySelectorAll('#headsDlgBody .gz-cap')].some((c) => c.textContent === '지정 — 1')")
              and page.evaluate("(ids) => ids.every((id) => !paraEl(id).classList.contains('gz-in')) && document.querySelectorAll('#doc .sheet > .gz-tag.gz-mark').length === 1", [P2, P3]), (dele, tag_of(P2)))
        page.locator(f'#zonesBar .gz-chip[data-org="{KEYS[UANGEL]}"]').click()
        page.wait_for_function("""(k) => { const c = document.querySelector(`#headsDlgBody .gz-cap[data-org="${k}"]`), b = document.getElementById('headsDlgBody').getBoundingClientRect(); if (!c) return false;
          const r = c.getBoundingClientRect(); return r.top >= b.top - 2 && r.top < b.bottom; }""", arg=KEYS[UANGEL], timeout=30000)
        check("줄의 기관 칩을 누르면 목록의 그 기관 묶음으로", True)
        page.evaluate("() => headsColClose()")

        # ---- 10. 「지정 해제」(오른쪽 단추) — 그 블록은 자동으로 읽은 값으로
        n_req = len(sent)
        with page.expect_response(lambda r: "/zones/marks/" in r.url and r.request.method == "DELETE"):
            menu_at(P1, "지정 해제")
        page.wait_for_function("() => zn().data.marks.length === 0 && !zn().loading && !document.querySelector('#doc .gz-tag.gz-mark')", timeout=60000)
        z6, t4 = zones_api(), tag_of(P1)
        check("「지정 해제」 → 지정 0 · 점선 이름표 없음 · 그 문단은 지정 전의 표시로 · 줄의 「지정」 칩 없음", z6["marks"] == [] and (t4 or {}).get("text") == (t_before or {}).get("text") and not (t4 or {}).get("mark")
              and not any(c["text"].startswith("지정 ") for c in page.evaluate(BAR)["chips"]) and {t["text"] for t in page.evaluate(DOC)["tags"]} == {z["text"] for z in z6["zones"]}, (t_before, t4))

        # ---- 10a. 오래 열린 입력이 남의 수정을 덮지 않는다 — 저장은 입력을 **열 때**의 구역 판으로 견준다(409 staleZones) · 고치기는 바꾼 것만 보낸다
        def pump(cond, what, secs=30):   # 붙들어 둔 요청이 올 때까지(화면 쪽 일이 돌게 조금씩 기다린다)
            for _ in range(int(secs * 10)):
                if cond():
                    return True
                page.wait_for_timeout(100)
            raise AssertionError(f"기다리다 그만둠: {what}")

        zz = zones_api()
        made = requests.post(f"{base}/api/docs/{a}/zones/marks", json={"ids": [P1], "label": {"org": KEYS[SEED]}, "note": "처음 메모", "docRev": zz["rev"], "zonesRev": zz["zonesRev"]}, timeout=120).json()
        mid2 = made["marks"][0]["id"]
        page.evaluate("() => { zonesLoad(true); }")
        page.wait_for_function("() => !zn().loading && zn().data.marks.length === 1 && !!document.querySelector('#doc .gz-tag.gz-mark')", timeout=60000)
        menu_at(P1, "구역 지정 고치기…")
        page.wait_for_selector("#zonesPop")
        held_rev = page.evaluate("() => zn().data.zonesRev")
        other = requests.put(f"{base}/api/docs/{a}/zones/marks/{mid2}", json={"label": {"org": KEYS[LEAD]}, "docRev": made["rev"], "zonesRev": made["zonesRev"]}, timeout=120).json()   # 그 사이 다른 화면이 그 지정의 기관을 고침
        page.fill("#zonesPop input[type=text]", "옛 입력에서 고친 메모")
        n_err, n_req = len(errors), len(sent)
        with page.expect_response(lambda r: "/zones/marks/" in r.url and r.request.method == "PUT") as resp:
            page.click("#zonesPop [data-zones=mark-ok]")
        page.wait_for_function("(n) => !document.getElementById('zonesPop') && !zn().loading && !!zn().data && zn().data.zonesRev === n", arg=other["zonesRev"], timeout=60000)
        puts, now, expected = [s for s in sent[n_req:] if s[0] == "PUT"], zones_api(), [e for e in errors[n_err:] if "409" in e and "Failed to load resource" in e]
        check("오래 열린 입력 — 메모만 고쳐 저장: 몸통 = {note, docRev, zonesRev(입력을 열 때의 판)} 뿐(label 없음) → 409 staleZones → 「구역 지정이 바뀌었습니다 — 다시 지정하세요」 · 다른 화면이 고친 기관·메모를 덮지 않음 · 다시 읽어 그 기관으로 보임",
              resp.value.status == 409 and held_rev == made["zonesRev"] and len(puts) == 1 and puts[0][2] == {"note": "옛 입력에서 고친 메모", "docRev": made["rev"], "zonesRev": held_rev}
              and "구역 지정이 바뀌었습니다 — 다시 지정하세요" in page.evaluate(TOAST) and now["marks"][0]["label"] == {"org": KEYS[LEAD]} and now["marks"][0]["note"] == "처음 메모" and now["zonesRev"] == other["zonesRev"]
              and (tag_of(P1) or {}).get("text", "").startswith(LEAD) and len(expected) == 1 and len(errors) == n_err + 1, (resp.value.status, puts, now["marks"], tag_of(P1), errors[n_err:]))
        del errors[n_err:n_err + len(expected)]
        menu_at(P1, "구역 지정 고치기…")
        page.wait_for_selector("#zonesPop")
        page.fill("#zonesPop input[type=text]", "메모만 고침")
        n_req = len(sent)
        with page.expect_response(lambda r: "/zones/marks/" in r.url and r.request.method == "PUT"):
            page.click("#zonesPop [data-zones=mark-ok]")
        page.wait_for_function("() => !document.getElementById('zonesPop') && !zn().loading")
        puts, now = [s for s in sent[n_req:] if s[0] == "PUT"], zones_api()
        check("메모만 고치면 요청 몸통에 label 이 없음({note, docRev, zonesRev}) — 값은 그대로", len(puts) == 1 and puts[0][2] == {"note": "메모만 고침", "docRev": made["rev"], "zonesRev": other["zonesRev"]}
              and now["marks"][0]["label"] == {"org": KEYS[LEAD]} and now["marks"][0]["note"] == "메모만 고침", (puts, now["marks"]))
        menu_at(P1, "구역 지정 고치기…")
        page.wait_for_selector("#zonesPop")
        page.select_option("#zonesPop select[data-zn-dim=org]", f"v:{KEYS[UANGEL]}")
        n_req = len(sent)
        with page.expect_response(lambda r: "/zones/marks/" in r.url and r.request.method == "PUT"):
            page.click("#zonesPop [data-zones=mark-ok]")
        page.wait_for_function("() => !document.getElementById('zonesPop') && !zn().loading")
        puts, now = [s for s in sent[n_req:] if s[0] == "PUT"], zones_api()
        check("값만 고치면 몸통에 note 가 없음({label, docRev, zonesRev}) — 메모는 그대로", len(puts) == 1 and set(puts[0][2]) == {"label", "docRev", "zonesRev"} and puts[0][2]["label"] == {"org": KEYS[UANGEL]}
              and now["marks"][0]["label"] == {"org": KEYS[UANGEL]} and now["marks"][0]["note"] == "메모만 고침", (puts, now["marks"]))
        menu_at(P1, "구역 지정 고치기…")
        page.wait_for_selector("#zonesPop")
        n_req = len(sent)
        page.click("#zonesPop [data-zones=mark-ok]")
        page.wait_for_function("() => !document.getElementById('zonesPop')")
        check("바꾼 것이 없으면 요청 없이 닫힘", not [s for s in sent[n_req:] if s[0] != "GET"] and "바꾼 것이 없어" in page.evaluate(TOAST), page.evaluate(TOAST))
        requests.delete(f"{base}/api/docs/{a}/zones/marks/{mid2}?zonesRev={now['zonesRev']}", timeout=120).raise_for_status()
        page.evaluate("() => { zonesLoad(true); }")
        page.wait_for_function("() => !zn().loading && zn().data.marks.length === 0 && !document.querySelector('#doc .gz-tag.gz-mark')", timeout=60000)

        # ---- 10b. 편집 앞에 떠난 늦은 응답을 새 문서 차례 위에 그리지 않는다 — 문서 차례가 오르면 진행 중인 요청도 무효 · 표시는 지금 차례의 자료만
        ZONES_GET, late = re.compile(rf"/api/docs/{a}/zones$"), []

        def hold_route(route):   # GET …/zones 의 응답을 그때 받아 붙들어 둔다(나중에 준다 — 늦게 오는 응답)
            if route.request.method != "GET":
                return route.continue_()
            late.append((route, route.fetch()))
        page.route(ZONES_GET, hold_route)
        rev0 = page.evaluate("() => state.serverRev")
        page.evaluate("() => { zonesLoad(true); }")
        pump(lambda: len(late) == 1, "편집 앞의 GET …/zones")
        page.evaluate("(id) => { const p = paraEl(id); p.append(document.createTextNode(' 늦은응답')); scheduleSave(p); }", P3)   # 글을 고쳐 문서 차례를 올린다
        page.wait_for_function("(r) => state.serverRev > r && !state.timers.size && !state.inflight", arg=rev0, timeout=60000)
        pump(lambda: len(late) == 2, "편집 뒤의 GET …/zones(잠깐 뒤 한 번)")
        SEE = "() => ({ shown: !!znShown(), ins: document.querySelectorAll('#doc .gz-in').length, tags: document.querySelectorAll('#doc .gz-tag').length, chips: document.querySelectorAll('#zonesBar .gz-chip').length, text: document.querySelector('#zonesBar .gt-zones-chips').textContent, key: !document.getElementById('zonesKey').hidden, dataRev: zn().data ? zn().data.rev : null, rev: state.serverRev })"
        page.evaluate("() => paginate()")   # 쪽을 다시 나눔 = 표시를 다시 다는 때
        s1 = page.evaluate(SEE)
        check("문서 차례가 오른 뒤(다시 읽기 전) — 옛 차례의 자료로는 띠·이름표·칩·색 설명을 그리지 않음 · 줄에 「문서가 바뀜 — 다시 읽는 중」", not s1["shown"] and s1["ins"] == 0 and s1["tags"] == 0 and s1["chips"] == 0
              and not s1["key"] and "문서가 바뀜 — 다시 읽는 중" in s1["text"] and s1["dataRev"] == rev0 and s1["rev"] == rev0 + 1, s1)
        late[0][0].fulfill(response=late[0][1])   # 편집 앞에 떠난 응답이 이제야 온다
        page.wait_for_timeout(600)
        page.evaluate("() => paginate()")
        s2 = page.evaluate(SEE)
        check("편집 앞에 떠난 응답이 늦게 와도 — 상태에 넣지 않고 그리지 않음(무효가 된 요청)", not s2["shown"] and s2["ins"] == 0 and s2["tags"] == 0 and s2["chips"] == 0 and "문서가 바뀜 — 다시 읽는 중" in s2["text"], s2)
        late[1][0].fulfill(response=late[1][1])   # 새 차례에서 읽은 응답
        page.wait_for_function("() => !zn().loading && !!znShown() && zn().data.rev === state.serverRev && document.querySelectorAll('#doc .gz-in').length > 0 && document.querySelectorAll('#zonesBar .gz-chip').length > 0", timeout=60000)
        for route, resp in late[2:]:
            route.fulfill(response=resp)
        page.unroute(ZONES_GET)
        check("새 문서 차례의 응답이 오면 다시 그림(띠 · 칩 · 색 설명)", page.evaluate(SEE)["key"] and "다시 읽는 중" not in page.evaluate(BAR)["text"], page.evaluate(SEE))

        # ---- 10c. 밀린 편집이 반영에 실패하면 지정을 멈춘다 — 옛 서버 문서에 지정하지 않는다
        PATCH_URL = re.compile(rf"/api/docs/{a}/blocks/{P3}$")
        page.route(PATCH_URL, lambda route: route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "시험 — 반영 실패"}, ensure_ascii=False))
                   if route.request.method == "PATCH" else route.continue_())
        menu_at(P2, "구역 지정…")
        page.wait_for_selector("#zonesPop")
        page.select_option("#zonesPop select[data-zn-dim=org]", f"v:{KEYS[SEED]}")
        page.evaluate("(id) => { const p = paraEl(id); p.append(document.createTextNode(' 실패할 글')); scheduleSave(p); }", P3)   # 반영을 기다리는 편집(이 반영은 실패한다)
        n_err, n_req = len(errors), len(sent)
        page.click("#zonesPop [data-zones=mark-ok]")
        page.wait_for_function("() => state.failed.size === 1 && !state.inflight && !state.timers.size", timeout=60000)
        page.wait_for_timeout(400)
        check("밀린 편집의 반영이 실패 → POST …/zones/marks 를 보내지 않음 · 「서버에 반영하지 못한 문단이 있어 지정하지 않았습니다」 · 입력은 그대로", not [s for s in sent[n_req:] if s[0] != "GET"]
              and "서버에 반영하지 못한 문단이 있어 지정하지 않았습니다" in page.evaluate(TOAST) and page.locator("#zonesPop").count() == 1 and zones_api()["marks"] == [], (sent[n_req:], page.evaluate(TOAST)))
        page.evaluate("() => znPopClose()")
        items = menu_at(P2, "구역 지정…")
        page.wait_for_timeout(500)
        check("반영하지 못한 문단이 남아 있으면 입력도 열지 않음(알림) · 「LLM 검토」 도 같은 검사를 지난다(znFlushed)", page.locator("#zonesPop").count() == 0 and "서버에 반영하지 못한 문단이 있어 구역 지정을 열지 않았습니다" in page.evaluate(TOAST)
              and page.evaluate("() => /znFlushed\\(/.test(znLlmRun.toString())"), page.evaluate(TOAST))
        expected = [e for e in errors[n_err:] if "500" in e and "Failed to load resource" in e]
        check("콘솔에는 그 반영 실패(500) 한 줄뿐", len(expected) == 1 and len(errors) == n_err + 1, errors[n_err:])
        del errors[n_err:n_err + len(expected)]
        page.unroute(PATCH_URL)
        page.evaluate("(id) => { save(paraEl(id)); }", P3)   # 다시 반영(이번에는 된다)
        page.wait_for_function("() => state.failed.size === 0 && !state.inflight && !state.timers.size", timeout=60000)
        page.wait_for_function("() => !zn().loading && !!znShown() && zn().data.rev === state.serverRev", timeout=60000)

        # ---- 11. 「감추기」 — 표시가 모두 사라짐 · 기억 · 다시 「보기」
        page.click("#zonesKey .dv-key-off")
        page.wait_for_function(f"() => !document.querySelector('{ZONE_SEL}')")
        b, k = page.evaluate(BAR), page.evaluate(KEY)
        check("이름 줄의 「감추기」 → 띠·이름표·칸 표시 모두 사라짐 · 색 설명 없음 · 줄의 단추 = 「구역 표시 보기」(눌림 풀림) · 체크는 그대로 · 기억(off)", not k["shown"] and not k["has"] and b["toggle"] == "false"
              and b["toggleText"] == "구역 표시 보기" and [x[1] for x in b["dims"]] == [True, False, True] and page.evaluate("() => localStorage.getItem('nfm.zones')") == "off", (b["toggle"], b["toggleText"], k["shown"]))
        n_get = len([s for s in sent if s[0] == "GET" and s[1].endswith("/zones")])
        page.evaluate("() => zonesInvalidate('edit')")
        page.wait_for_timeout(1300)
        check("꺼 둔 동안은 구역을 다시 읽지 않음", len([s for s in sent if s[0] == "GET" and s[1].endswith("/zones")]) == n_get and page.locator(ZONE_SEL).count() == 0)
        page.click("#zonesBar [data-zones=toggle]")
        page.wait_for_function("() => !!document.querySelector('#doc .gz-in') && !!document.querySelector('#doc .sheet > .gz-tag')", timeout=120000)
        page.wait_for_function(READY)
        check("줄의 「구역 표시 보기」 → 다시 읽어 표시 · 색 설명 다시", page.evaluate(KEY)["shown"] and page.evaluate(BAR)["toggle"] == "true" and page.evaluate("() => localStorage.getItem('nfm.zones')") == "on")

        # ---- 12. 글을 고치면 — 문서 차례가 바뀐 뒤 잠깐 뒤 한 번 다시 읽음(표시는 그대로)
        rev0 = page.evaluate("() => state.serverRev")
        n_get = len([s for s in sent if s[0] == "GET" and s[1].endswith("/zones")])
        page.evaluate("(id) => paraEl(id).scrollIntoView({ block: 'center' })", P3)
        page.click(f'#doc .para[data-id="{P3}"]')
        page.keyboard.press("End")
        page.keyboard.insert_text(" 고침")   # 입력 한 번 = 반영 한 번(문서 차례 +1)
        page.wait_for_function("(r) => state.serverRev > r && !state.timers.size && !state.inflight", arg=rev0, timeout=60000)
        page.wait_for_function("() => !!zn().data && !zn().loading && zn().data.rev === state.serverRev", timeout=60000)
        gets = len([s for s in sent if s[0] == "GET" and s[1].endswith("/zones")]) - n_get
        check("글을 고친 뒤 — 새 문서 차례로 한 번 다시 읽음 · 표시는 남아 있음 · 줄에 「다시 읽는 중」 이 남지 않음", gets == 1 and page.locator("#doc .gz-in").count() > 0 and "다시 읽는 중" not in page.evaluate(BAR)["text"], gets)

        # ---- 13. 새로 고쳐도 옵션(서버)·표시(이 브라우저)가 남음
        open_work()
        page.wait_for_function("() => !!document.querySelector('#doc .gz-in') && !!document.querySelector('#doc .sheet > .gz-tag')", timeout=120000)
        b = page.evaluate(BAR)
        check("새로 고침 — 체크(기관 · 차년도)가 그대로(TASK 옵션은 서버에) · 띠·이름표·색 설명 다시", [x[1] for x in b["dims"]] == [True, False, True] and b["toggle"] == "true" and page.evaluate(KEY)["shown"]
              and len([c for c in b["chips"] if c["org"]]) >= 3, b["dims"])

        # ---- 14. 배율을 바꾼 뒤에도 표시가 다시 달림(쪽을 다시 나누면 요소가 새것)
        n_tag = page.locator("#doc .sheet > .gz-tag").count()
        page.evaluate("() => setZoom(0.8)")
        page.wait_for_function("() => !zoomJob.on && !zoomJob.timer", timeout=60000)
        page.wait_for_function("() => !!document.querySelector('#doc .gz-in') && !!document.querySelector('#doc .sheet > .gz-tag')", timeout=60000)
        page.evaluate("() => paginate()")
        page.wait_for_function("(n) => document.querySelectorAll('#doc .sheet > .gz-tag').length === n", arg=n_tag, timeout=60000)
        check("배율 80% · 쪽 다시 나눔 뒤 — 띠·이름표가 다시 달림(이름표 수 그대로)", page.locator("#doc .gz-in").count() > 0, n_tag)
        page.evaluate("() => document.querySelector('#doc .sheet > .gz-tag').scrollIntoView({ block: 'center' })")
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / "14_doc.png"))

        # ---- 15. 다른 화면이 옵션을 먼저 바꿈 → 409 → 다시 읽고 알림(낡은 판으로 덮지 않는다)
        other = requests.put(f"{base}/api/works/{a}/task-options", json={"zones": {"dims": ["stage"]}}, timeout=30).json()
        n_err = len(errors)
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task-options") and r.request.method == "PUT") as resp:
            page.click("#zonesBar input[data-zones-dim=year]")
        page.wait_for_function("() => !zn().optBusy && !zn().loading && document.querySelector('#zonesBar input[data-zones-dim=stage]').checked", timeout=60000)
        b, now = page.evaluate(BAR), options_api()
        expected = [e for e in errors[n_err:] if "409" in e and "Failed to load resource" in e]
        check("낡은 판으로 고르면 409(staleOptions) → 덮지 않고 지금 옵션(단계)으로 다시 그림 · 알림 「다시 읽었습니다」(콘솔에는 그 409 한 줄뿐)", resp.value.status == 409 and now["zones"]["dims"] == ["stage"] and now["rev"] == other["rev"]
              and [x[1] for x in b["dims"]] == [False, True, False] and "다시 읽었습니다" in page.evaluate(TOAST) and len(expected) == 1 and len(errors) == n_err + 1, (resp.value.status, now, b["dims"], errors[n_err:]))
        del errors[n_err:n_err + len(expected)]
        page.wait_for_function("() => [...document.querySelectorAll('#zonesBar .gz-chip')].some((c) => c.dataset.stage)", timeout=60000)
        b, d = page.evaluate(BAR), page.evaluate(DOC)
        check("단계만 켠 화면 — 단계 칩에 색(색 축 = 단계) · 이름표 「1단계」", any(c["stage"] == "1" and c["gz"] == "1" and re.fullmatch(r"1단계 구역 \d+", c["text"]) for c in b["chips"]) and {t["text"] for t in d["tags"]} == {"1단계"}, (b["chips"], sorted({t["text"] for t in d["tags"]})))

        # ---- 16. 「LLM 검토」(spec_구역 ② §8) — 임시 서버는 LLM 끔: 단추가 보이고 꺼져 있으며 까닭이 도움말에 · 옆에 「지침」(진짜 끝점)
        LLM = """() => { const b = document.querySelector('#zonesBar [data-zones=llm]'), g = document.querySelector('#zonesBar [data-llm-guide=zones]'), l = document.querySelector('#zonesBar [data-zones=llm-last]');
          return { shown: !!b && b.getClientRects().length > 0, off: !!b && b.disabled, text: b ? b.textContent : '', title: b ? b.title : '', run: !!b && b.classList.contains('run'), h: b ? Math.round(b.getBoundingClientRect().height) : 0,
            guide: !!g && g.getClientRects().length > 0, last: l ? l.textContent : '', lastHelp: l && l.querySelector('.panel-help') ? l.querySelector('.panel-help').dataset.help : '', missing: zn().llmMissing,
            over: document.getElementById('zonesBar').scrollWidth > document.getElementById('zonesBar').clientWidth + 1 }; }"""
        page.wait_for_function("() => !!zn().llm || zn().llmMissing || !!zn().llmErr", timeout=60000)
        lb, real = page.evaluate(LLM), requests.get(f"{base}/api/docs/{a}/zones/llm", timeout=120)
        rj = real.json() if real.status_code == 200 else {}
        have = real.status_code == 200   # 서버 쪽(app/zones_llm.py · zones_api 의 끝점)이 들어와 있나 — 없으면 아래 흉내 구간만 본다
        check("[끝점] GET …/zones/llm — LLM 끔: available false + 까닭 글 · 후보 수 · 종류 · 마지막 결과 없음(LLM 을 부르지 않는다)" + ("" if have else " — 서버 대기(끝점 없음)"), have and rj.get("available") is False and bool(rj.get("why"))
              and isinstance(rj.get("candidates"), int) and set(rj.get("kinds") or {}) == {"conflict", "unknown", "hint", "alone"} and rj.get("last") is None and rj.get("running") is False, (real.status_code, real.text[:300]))
        check("「LLM 검토」 단추 — 켠 기준이 있는 줄에 보이고 · LLM 을 못 쓰면 꺼져 있으며 까닭이 도움말에 · 옆에 「지침」 · 28px · 줄이 넘치지 않음" + ("" if have else " — 서버 대기(끝점 없음)"), have and lb["shown"] and lb["off"]
              and lb["text"] == "LLM 검토" and lb["title"] == rj.get("why") and lb["guide"] and lb["h"] == 28 and not lb["over"] and not lb["last"], lb)
        if have:
            page.click("#zonesBar [data-llm-guide=zones]")
            page.wait_for_function("() => heads.dlg === 'llmGuide' && !!document.querySelector('#headsDlgBody .lg-part, #headsDlgBody .hwarn')", timeout=60000)
            guide = page.evaluate("() => ({ title: document.getElementById('headsDlgTitle').textContent, parts: [...document.querySelectorAll('#headsDlgBody .lg-part')].map((d) => d.dataset.part), warn: (document.querySelector('#headsDlgBody .hwarn') || {}).textContent || '' })")
            check("「지침」 → 문서 옆 열 「LLM 지침 — 편집 구역 …」: 계약 · 판단 지침(보기만)", "편집 구역" in guide["title"] and {"contract", "guide"} <= set(guide["parts"]) and not guide["warn"], guide)
            page.evaluate("() => headsColClose()")
        else:   # 끝점이 없는 서버 — 단추를 안 보인다(콘솔에는 그 404 뿐)
            gone = [e for e in errors if "404" in e and "Failed to load resource" in e]
            check("끝점이 없는 서버 — 「LLM 검토」 단추를 안 보임(서버 대기)", lb["missing"] and not lb["shown"], lb)
            for e in gone:
                errors.remove(e)
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task-options") and r.request.method == "PUT"):   # 켠 기준이 없으면 단추도 없다
            page.click("#zonesBar input[data-zones-dim=stage]")
        page.wait_for_function(READY)
        check("켠 기준이 없는 줄(체크만)에는 「LLM 검토」·「지침」 이 없음", page.locator("#zonesBar [data-zones=llm]").count() == 0 and page.locator("#zonesBar [data-llm-guide]").count() == 0 and not page.evaluate(BAR)["chips"])
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task-options") and r.request.method == "PUT"):
            page.click("#zonesBar input[data-zones-dim=stage]")
        page.wait_for_function("() => [...document.querySelectorAll('#zonesBar .gz-chip')].some((c) => c.dataset.stage)", timeout=60000)
        page.wait_for_function(READY)

        # ---- 17. 「LLM 검토」 를 돌림 — 끝점은 흉내(정규식 route — 글로브는 하위 경로를 안 잡는다): GET 이 쓸 수 있음 · 후보 3 → 확인 창 → POST {docRev, zonesRev} → 응답(구역 자료 + llm + LLM 지정) → 결과 줄 · 「LLM」 이름표 · 칩 · 목록
        LLM_URL, CLEAR_URL = re.compile(rf"/api/docs/{a}/zones/llm$"), re.compile(rf"/api/docs/{a}/zones/marks\?by=llm")
        M = {"last": None, "posts": [], "clears": [], "mode": "ok", "left": 3, "mark": None}
        SUMMARY = "표 2곳은 윗 제목과 이름표로 단계를 정했고, 1곳은 근거가 약해 그대로 두었습니다."

        def llm_route(route):
            req = route.request
            if req.method == "GET":
                n = M["left"]
                return route.fulfill(status=200, content_type="application/json", body=json.dumps({"available": True, "why": None, "running": False, "candidates": n,
                    "kinds": {"conflict": 1 if n else 0, "unknown": 1 if n > 1 else 0, "hint": 1 if n > 2 else 0, "alone": 0}, "truncated": False, "last": M["last"]}, ensure_ascii=False))
            body = req.post_data_json
            M["posts"].append(body)
            if M["mode"] == "stale":   # 검토하는 사이 지정이 바뀜 — 서버가 결과를 버린다
                return route.fulfill(status=409, content_type="application/json", body=json.dumps({"detail": {"reason": "staleZones", "message": "구역 지정이 다른 곳에서 바뀌었습니다"}}, ensure_ascii=False))
            # LLM 이 P2 를 「1단계」 로 지정한 것으로 — 진짜 지정 끝점으로 지정을 만들고(문서는 안 바뀜) 응답의 그 지정을 by "llm" 으로 바꿔 돌려준다(응답 꼴 = 구역 자료 + llm)
            view = requests.post(f"{base}/api/docs/{a}/zones/marks", json={"ids": [P2], "label": {"stage": 1}, "note": "윗 제목이 1단계 개발 내용", "docRev": body["docRev"], "zonesRev": body["zonesRev"]}, timeout=120).json()
            for m in view["marks"]:
                if m["ids"] == [P2]:
                    m["by"], M["mark"] = "llm", m["id"]
            llm = {"candidates": 3, "marked": 2, "kept": 1, "dropped": 0, "summary": SUMMARY, "truncated": False, "call": {"model": "test", "ms": 1200, "costUsd": 0.01, "error": None}}
            M["last"], M["left"] = {"at": "2026-11-17T20:00:00", **{k: llm[k] for k in ("candidates", "marked", "kept", "dropped", "summary")}, "error": None}, 1
            time.sleep(1.4)   # 도는 동안의 단추(동그라미 + 「LLM 검토 중… n초」)가 보이게
            route.fulfill(status=200, content_type="application/json", body=json.dumps({**view, "llm": llm}, ensure_ascii=False))

        def clear_route(route):   # 「LLM 지정 모두 해제」 — 흉내 낸 LLM 지정(서버에는 보통 지정)을 진짜 끝점으로 지우고 그 응답을 돌려준다
            M["clears"].append(route.request.url.split("/api/", 1)[1])
            n = route.request.url.split("zonesRev=", 1)[1]
            r = requests.delete(f"{base}/api/docs/{a}/zones/marks/{M['mark']}?zonesRev={n}", timeout=120)
            route.fulfill(status=r.status_code, content_type="application/json", body=r.text)
        page.route(LLM_URL, llm_route)
        page.route(CLEAR_URL, clear_route)
        page.evaluate("() => { const Z = zn(); Z.llmMissing = false; Z.llmKey = ''; znLlmLoad(); }")
        page.wait_for_function("() => { const b = document.querySelector('#zonesBar [data-zones=llm]'); return !!b && !b.disabled; }", timeout=60000)
        lb = page.evaluate(LLM)
        check("LLM 을 쓸 수 있고 후보가 있으면 단추가 켜짐 — 도움말에 몇 곳을 보내는지 · 유료 · 문서는 안 바뀜", lb["shown"] and not lb["off"] and all(s in lb["title"] for s in ("3곳", "유료", "문서는 안 바뀜")) and lb["guide"], lb)
        dialogs = []
        page.once("dialog", lambda dlg: (dialogs.append(dlg.message), dlg.dismiss()))
        page.click("#zonesBar [data-zones=llm]")
        page.wait_for_timeout(300)
        check("누르면 확인 창 — 후보 3곳(종류마다 수) · 유료 · 문서는 안 바뀜 · 「LLM」 지정으로 따로 보임 · 「취소」 면 아무것도 안 보냄", len(dialogs) == 1 and "후보 3곳(확인 필요 1 · 기관 모름 1 · 이름표가 있는데 못 읽은 표 1)" in dialogs[0]
              and all(s in dialogs[0] for s in ("유료", "문서는 바뀌지 않고", "「LLM」 지정", "진행할까요?")) and not M["posts"] and not page.evaluate(LLM)["run"], dialogs)
        revs = page.evaluate("() => [state.serverRev, zn().data.zonesRev]")
        page.evaluate("""() => { window.__znRun = []; window.__znRunT = setInterval(() => { const b = document.querySelector('#zonesBar [data-zones=llm]');
          if (b && b.classList.contains('run')) window.__znRun.push([b.textContent, b.disabled, getComputedStyle(b, '::before').animationName, [...document.querySelectorAll('#zonesBar input[data-zones-dim]')].every((c) => !c.disabled)]); }, 100); }""")
        page.once("dialog", lambda dlg: dlg.accept())
        page.click("#zonesBar [data-zones=llm]")
        page.wait_for_function("() => !zn().llmBusy && !!document.querySelector('#doc .sheet > .gz-tag.gz-llm')", timeout=60000)
        page.wait_for_function("() => !!zn().llm && zn().llm.candidates === 1")
        seen_run = page.evaluate("() => { clearInterval(window.__znRunT); return window.__znRun; }")
        lb, t5, bar = page.evaluate(LLM), tag_of(P2), page.evaluate(BAR)
        check("「진행」 → POST …/zones/llm {docRev, zonesRev}(밀린 편집 뒤의 차례) · 도는 동안 단추 = 돌아가는 동그라미 + 「LLM 검토 중… n초」(꺼짐) · 체크는 그대로 쓸 수 있음", M["posts"] == [{"docRev": revs[0], "zonesRev": revs[1]}]
              and len(seen_run) >= 3 and all(re.fullmatch(r"LLM 검토 중… \d+초", x[0]) and x[1] and x[2] == "spin" and x[3] for x in seen_run) and any(x[0].endswith(" 1초") for x in seen_run), (M["posts"], revs, seen_run[:3], seen_run[-1:]))
        check("끝나면 결과 한 줄 「LLM 검토 — 후보 3 · 지정 2 · 그대로 1」(요약은 노트 도움말) · 알림 · 단추는 남은 후보로 다시 켜짐", "LLM 검토 — 후보 3 · 지정 2 · 그대로 1" in lb["last"] and lb["lastHelp"] == SUMMARY
              and "LLM 검토 — 후보 3 · 지정 2 · 그대로 1" in page.evaluate(TOAST) and not lb["off"] and not lb["run"] and lb["text"] == "LLM 검토" and "1곳" in lb["title"], (lb, page.evaluate(TOAST)))
        check("LLM 이 지정한 구역 — 이름표가 점선 테 + 글 끝에 「· LLM」(.gz-tag.gz-mark.gz-llm) · 도움말 「LLM 이 지정 — <까닭>」 · 칩 「지정 1(LLM 1)」", t5 and t5["text"] == "1단계 · LLM" and t5["mark"] and t5["llm"]
              and "LLM 이 지정 — 윗 제목이 1단계 개발 내용" in t5["title"] and "사람이 지정" not in t5["title"] and any(c["text"] == "지정 1(LLM 1)" for c in bar["chips"]), (t5, [c["text"] for c in bar["chips"]]))
        page.evaluate("(id) => paraEl(id).scrollIntoView({ block: 'center' })", P2)
        page.wait_for_timeout(SETTLE)
        page.screenshot(path=str(OUT / "17_llm_marked.png"))
        items = menu_at(P2, "구역 지정 고치기…")
        page.wait_for_selector("#zonesPop")
        p = page.evaluate(POP)
        check("LLM 이 지정한 문단의 메뉴·입력 — 「구역 지정 고치기…」 · 「지정 해제」 · 입력에 「LLM 이 지정한 구역」 안내와 까닭(메모)", "지정 해제" in items and p["title"] == "구역 지정 고치기" and "LLM 이 지정한 구역" in p["caption"]
              and p["note"] == "윗 제목이 1단계 개발 내용" and p["sels"]["stage"]["value"] == "v:1", (items[-3:], p["caption"], p["note"]))
        page.keyboard.press("Escape")
        page.click("#zonesBar [data-zones=list]")
        page.wait_for_function("() => heads.dlg === 'zones' && !!document.querySelector('#headsDlgBody [data-zones=llm-clear]')")
        L2 = page.evaluate("""() => ({ cap: (document.querySelector('#headsDlgBody .gz-cap[data-zn-group="@marks"] span') || {}).textContent || '', clear: document.querySelector('#headsDlgBody [data-zones=llm-clear]').textContent,
          rows: [...document.querySelectorAll('#headsDlgBody [data-zones=unmark]')].map((x) => [x.closest('tr').dataset.znBy, ...[...x.closest('tr').children].map((td) => td.textContent)]) })""")
        check("목록의 「지정」 묶음 — 머리 「지정 — 1(LLM 1)」 + 「LLM 지정 모두 해제」 · 줄에 근거 「LLM」 과 까닭 · 줄마다 「해제」", L2["cap"] == "지정 — 1(LLM 1)" and L2["clear"] == "LLM 지정 모두 해제"
              and L2["rows"] == [["llm", "1단계", "블록 1", "LLM", "윗 제목이 1단계 개발 내용", "해제"]], L2)
        page.screenshot(path=str(OUT / "17_llm_list.png"))
        dialogs.clear()
        page.once("dialog", lambda dlg: (dialogs.append(dlg.message), dlg.accept()))
        zr = page.evaluate("() => zn().data.zonesRev")
        page.click("#headsDlgBody [data-zones=llm-clear]")
        page.wait_for_function("() => zn().data.marks.length === 0 && !document.querySelector('#doc .gz-tag.gz-llm') && !document.querySelector('#headsDlgBody [data-zones=llm-clear]')", timeout=60000)
        check("「LLM 지정 모두 해제」 → 확인 한 번 → DELETE …/zones/marks?by=llm&zonesRev=n · LLM 이름표·칩·묶음이 사라짐", len(dialogs) == 1 and "1개" in dialogs[0] and "사람이 지정한 것은 그대로" in dialogs[0]
              and M["clears"] == [f"docs/{a}/zones/marks?by=llm&zonesRev={zr}"] and not any(c["text"].startswith("지정 ") for c in page.evaluate(BAR)["chips"]) and zones_api()["marks"] == [], (dialogs, M["clears"]))
        page.evaluate("() => headsColClose()")
        M["mode"] = "stale"   # 검토하는 사이 지정이 바뀌면(409 staleZones) 결과를 반영하지 않고 알린다
        n_err, n_post = len(errors), len(M["posts"])
        page.once("dialog", lambda dlg: dlg.accept())
        with page.expect_response(lambda r: r.url.endswith(f"/api/docs/{a}/zones/llm") and r.request.method == "POST"):
            page.click("#zonesBar [data-zones=llm]")
        page.wait_for_function("() => !zn().llmBusy && !zn().loading")
        expected = [e for e in errors[n_err:] if "409" in e and "Failed to load resource" in e]
        check("409 staleZones — 「검토하는 사이 구역이 바뀌어 결과를 반영하지 않았습니다 — 다시 누르세요」 · 지정은 안 생김(콘솔에는 그 409 한 줄뿐)", len(M["posts"]) == n_post + 1 and "검토하는 사이 구역이 바뀌어 결과를 반영하지 않았습니다" in page.evaluate(TOAST)
              and page.locator("#doc .gz-tag.gz-llm").count() == 0 and len(expected) == 1 and len(errors) == n_err + 1, (page.evaluate(TOAST), errors[n_err:]))
        del errors[n_err:n_err + len(expected)]
        M["mode"], M["left"] = "ok", 0
        page.evaluate("() => { zn().llmKey = ''; znLlmLoad(); }")
        page.wait_for_function("() => !!zn().llm && zn().llm.candidates === 0 && document.querySelector('#zonesBar [data-zones=llm]').disabled")
        lb = page.evaluate(LLM)
        check("후보가 0 이면 단추가 꺼지고 도움말 「LLM 에 물을 후보가 없습니다 — 스크립트가 모두 읽었습니다」", lb["off"] and lb["title"] == "LLM 에 물을 후보가 없습니다 — 스크립트가 모두 읽었습니다", lb)
        open_work()   # 새로 고친 뒤에는 GET …/zones/llm 의 last 로 같은 줄
        page.wait_for_function("() => !!document.querySelector('#zonesBar [data-zones=llm-last]')", timeout=60000)
        lb = page.evaluate(LLM)
        check("새로 고친 뒤에도 결과 줄(GET …/zones/llm 의 last) — 「LLM 검토 — 후보 3 · 지정 2 · 그대로 1」 + 요약 노트", "LLM 검토 — 후보 3 · 지정 2 · 그대로 1" in lb["last"] and lb["lastHelp"] == SUMMARY and lb["shown"], lb)
        page.unroute(LLM_URL)
        page.unroute(CLEAR_URL)

        # ---- 18. 연구개발 작업이 아니면 줄도 표시도 없음
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task") and r.request.method == "PUT"):
            page.select_option("#panelTask", "")
        page.wait_for_function(f"() => !document.querySelector('{ZONE_SEL}')")
        check("작업 종류를 풀면 — 문서의 구역 표시·색 설명이 걷힘", not page.evaluate(KEY)["shown"] and page.evaluate("() => zonesOffered()") is False)
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
print(json.dumps({"요청": len(sent)}, ensure_ascii=False), flush=True)
print(f"\n{'통과' if not fails else '실패'} — 떨어진 검사 {len(fails)}개" + ("" if not fails else ": " + " / ".join(fails)), flush=True)
sys.exit(1 if fails else 0)

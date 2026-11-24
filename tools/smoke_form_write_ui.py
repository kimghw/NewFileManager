"""워크플로우 「양식 작성」 의 화면(spec_양식작성 ② §2 · §4 · §5 · §6 — 2026-11-24 사용자 "워크플로우에 문서양식을 주고 LLM을 이용해서 문서양식을 작성해주는 TASK" · "이 문서 관리 라이브러리는 별도 서버에서"):
app/static/form_write.js(대시보드의 단계 상태 · 2열 「자료 가져오기」 · 「지침 작성」) · task_catalog.js(카드) · doclib/static(문서 라이브러리 서버의 관리 화면).
화면 확인 — 임시 서버 **둘**(문서 편집 서버 = --port · 문서 라이브러리 서버 = --port + 300 — 임시 저장소 · PDF · LLM 끔)을 스스로 띄우고 끈다 + Playwright. 진짜 끝점으로.
LLM 을 부르지 않는다: 추출 결과는 문서 라이브러리의 저장소에 미리 적어 두고(끝난 추출 하나), 지침 작성의 실행은 「LLM 을 쓸 수 없습니다」 로 꺼진 것까지와 흉내 낸 실행 응답으로 본다.

    python -X utf8 tools/smoke_form_write_ui.py <그림·임시 폴더> [--port 18840]

보는 것:
- ① 목록(task_catalog.js) — form_write: 일반 문서 · 처음 여는 보기 = 대시보드 · 첫 화면에 카드 「양식 작성」 + 로고.
- ② 문서 화면의 대시보드 — 묶음 셋(준비 · 자료 준비 · 지침 작성) · 문서 라이브러리의 문서 · 끝난 추출 수 · 자료 없음 → 「자료 가져오기」 가 지금 차례.
- ③ 2열 「자료 가져오기」 — 문서 라이브러리의 추출 줄(범위 · 쪽 · 그림 · 수식 · 확인 필요) · 「가져오기」 → 이 문서의 자료(진짜 끝점 — 문서 라이브러리 서버에서 MD 를 읽어 온다) · 다시 누를 수 없음(「가져옴」).
- ④ 2열 「지침 작성」 — 쓸 자료(체크) · 이번 작성의 지침 · 자리 목록(작성 지침이 있는 자리만 ↔ 모든 헤딩) · 「작성 지침 보기」 · LLM 꺼짐이면 「제안 받기」 꺼짐 + 까닭 · 가로 넘침 없음.
- ⑤ 흉내 낸 실행(끝점 응답만 바꿈) — 「제안 받기 (n곳)」 → 확인 창 → POST 본문 {places, materials, note} · 도는 동안 진행 글 · 「멈춤」 · 끝나면 자리마다 꼬리표(제안 n · 자료에 없음 · 실패).
- ⑥ 문서 라이브러리 서버의 화면 — 문서 줄 · 추출 결과 카드 · MD 글과 그림 · 「스킬 글」(셋 · 계약) · 문서 편집 서버가 꺼져도 뜬다는 것은 보지 않는다(따로 선 프로세스임은 포트가 다른 것으로).
- 문서 라이브러리 서버를 끄면 대시보드가 「꺼져 있습니다」 로 알리고 지침 작성 열은 그대로 열린다.
- 콘솔 오류 없음."""
import argparse
import io
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
ap.add_argument("--port", type=int, default=18840)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
LIB_PORT = args.port + 300
base, lib = f"http://127.0.0.1:{args.port}", f"http://127.0.0.1:{LIB_PORT}"
FORM = ROOT / "samples" / "연구개발계획서_양식.hwpx"   # 작성 요령이 든 양식(자리마다 지침이 붙는다)
common = {**os.environ, "PYTHONUTF8": "1", "NFM_PDF": "off", "NFM_DOCLIB": str(tmp / "doclib"), "NFM_DOCLIB_LLM": "off"}
env = {**common, "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"),
       "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "NFM_TASKS": str(tmp / "tasks.json"), "NFM_FORM_FILES": str(tmp / "form_files"),
       "NFM_AGENT_NOTES": str(tmp / "agent_notes.json"), "NFM_TOOL_NAMES": str(tmp / "tool_names.json"), "NFM_REQS": str(tmp / "reqs.json"), "NFM_DOCLIB_URL": lib}
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_DOCLIB_PORT"):
    env.pop(k, None)
errors, fails = [], []
GW = re.compile(r"/guide-write(/|$|\?)")


def seed():
    """문서 라이브러리의 저장소에 문서 하나 + 끝난 추출 하나를 미리 적는다(LLM 을 부르지 않게) → (문서 id, 추출 id)."""
    os.environ["NFM_DOCLIB"] = str(tmp / "doclib")
    sys.path.insert(0, str(ROOT))
    import fitz
    from PIL import Image
    from doclib import store
    pdf = fitz.open()
    for i in range(3):
        pdf.new_page().insert_text((72, 72), f"page {i + 1}")
    meta, _ = store.add_doc("연차보고서_견본.pdf", pdf.tobytes())
    store.patch_doc(meta["id"], {"pages": 3, "org": "한국선급", "topic": "SSCB 설계"})
    e = store.new_extract(meta["id"], "한국선급의 SSCB 서브모듈 설계", (1, 3))
    folder = store.ext_dir(e["id"])
    (folder / "images").mkdir()
    buf = io.BytesIO()
    Image.new("RGB", (240, 120), (40, 110, 200)).save(buf, "PNG")
    (folder / "images" / "p1_F1.png").write_bytes(buf.getvalue())
    md = ("# 연차보고서_견본.pdf\n\n> 자료 추출 — 범위: 한국선급의 SSCB 서브모듈 설계 · 쪽 1–3\n> 그림 1 · 수식 1 · 확인 필요 1곳\n\n<!-- p.1 -->\n\n## 연구개발 목표\n\n- 최종 목표: 차단 시간 1 ms 이하의 SSCB 서브모듈 개발\n\n"
          "![< 서브모듈 토폴로지 >](images/p1_F1.png)\n<!-- 확인 필요: 그림 확인이 다시 자름 — 온전한지 볼 것 -->\n< 서브모듈 토폴로지 >\n\n$$\nV_{pk} \\approx V_{dc} + L \\frac{di}{dt}\n$$\n")
    (folder / "doc.md").write_text(md, encoding="utf-8")
    e.update(state="done", ended=time.time(), pages=3, chars=len(md), figures=1, formulas=1, open=1, model="claude-opus-5-5", costUsd=0.42, progress={"done": 1, "total": 1, "text": "끝남"})
    store.save_extract(e)
    return meta["id"], e["id"]


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:1500] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def wait(url, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if requests.get(url, timeout=2).status_code == 200:
                return True
        except requests.RequestException:
            time.sleep(0.4)
    return False


def start(mod, port, name, e):
    log = (OUT / f"{name}.log").open("w", encoding="utf-8")
    return subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", mod, "--host", "127.0.0.1", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=e,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


DASH = """() => ({ groups: [...document.querySelectorAll('#paneDash .dash-group')].map((g) => (g.querySelector('.dash-gname, .dash-ghead') || {}).textContent || ''),
  nodes: Object.fromEntries([...document.querySelectorAll('#paneDash .dash-node')].map((n) => [n.dataset.key, { state: n.dataset.state || '', text: n.textContent }])) })"""
COL = """() => { const c = document.getElementById('headsDlg'); return { kind: c.hidden ? '' : c.dataset.kind, title: document.getElementById('headsDlgTitle').textContent,
  over: document.getElementById('headsDlgBody').scrollWidth > document.getElementById('headsDlgBody').clientWidth + 1 }; }"""
LIVE = """async () => { const L = await formWriteLive(); return Object.fromEntries(Object.entries(L.steps).map(([k, v]) => [k, { state: v.state, text: v.text || '', acts: (v.acts || []).map((b) => [b.textContent, b.disabled]) }])); }"""
PLACES = """() => [...document.querySelectorAll('#headsDlgBody .fw-place')].map((r) => ({ name: r.querySelector('.fw-place-name').textContent, on: r.querySelector('input').checked,
  tags: [...r.querySelectorAll('.fw-tags .fw-tag')].map((t) => t.textContent), guides: r.querySelectorAll('.fw-guide').length }))"""
FOOT = """() => { const f = document.getElementById('headsDlgFoot'); return { text: f.textContent, btns: [...f.querySelectorAll('button')].map((b) => [b.textContent, b.disabled, b.title]) }; }"""


def main():
    did, eid = seed()
    procs = [start("doclib.server:app", LIB_PORT, "doclib", common), start("app.server:app", args.port, "server", env)]
    try:
        check("서버 둘이 뜬다", wait(lib + "/api/health") and wait(base + "/api/headings/llm"))
        r = requests.post(base + "/api/docs", files={"file": ("과제 양식.hwpx", FORM.read_bytes())}, timeout=120)
        doc = r.json()["docId"]
        t = requests.put(f"{base}/api/works/{doc}/task", json={"kind": "general", "file": "", "job": "form_write", "project": "양식 작성 시험"}, timeout=30)
        requests.post(f"{base}/api/docs/{doc}/headings", json={"first": True}, timeout=60)   # 기본 분석(헤딩 그래프 — 스크립트): 화면으로 올리면 저절로 돈다 · 자리 목록이 그 헤딩에서 나온다
        end = time.time() + 180
        while time.time() < end and not requests.get(f"{base}/api/docs/{doc}/guide-write", timeout=30).json()["places"]:
            time.sleep(1)
        check("작업에 워크플로우 「양식 작성」 을 적는다(일반 문서)", t.status_code == 200 and t.json()["task"]["job"] == "form_write" and t.json()["task"]["kind"] == "general", t.text[:300])
        check("다른 작업 종류와는 묶이지 않는다", requests.put(f"{base}/api/works/{doc}/task", json={"kind": "rnd", "file": "plan", "job": "form_write", "project": ""}, timeout=30).status_code == 400)
        L = requests.get(base + "/api/doclib", timeout=10).json()
        check("문서 편집 서버가 문서 라이브러리의 목록을 읽는다", L["alive"] and L["url"] == lib and [d["id"] for d in L["docs"]] == [did] and [e["id"] for e in L["docs"][0]["extracts"]] == [eid], L)
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            page = br.new_page(viewport={"width": 1680, "height": 1000})
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base)
            page.wait_for_selector(".task-cards li", timeout=30000)
            cat = page.evaluate("() => ({ kind: taskKindOf('form_write'), entry: taskEntryOf('form_write'), name: TASK_CATALOG.form_write.name, relay: taskIsRelay('form_write'), gather: taskIsGather('form_write') })")
            check("① 목록 — 일반 문서 · 처음 여는 보기 = 대시보드", cat == {"kind": "general", "entry": "Dash", "name": "양식 작성", "relay": False, "gather": False}, cat)
            card = page.evaluate("() => { const li = [...document.querySelectorAll('.task-cards li')].find((x) => /양식 작성/.test(x.textContent)); return li ? { text: li.textContent, icon: !!li.querySelector('use[href=\"#taskIcon-form_write\"], svg') } : null; }")
            check("① 첫 화면에 카드 「양식 작성」", bool(card) and card["icon"], card)
            page.screenshot(path=str(OUT / "01_home.png"))
            page.evaluate("(id) => openWork(id)", doc)
            page.wait_for_function("(id) => state.id === id && !!document.querySelector('#doc [data-id], .page')", arg=doc, timeout=90000)
            page.evaluate("() => showTab('Dash')")   # 작업 리스트에서 이어 연 문서는 그 전 보기 그대로다 — 카드로 시작하면(taskEnter) 처음 여는 보기가 대시보드(①)
            page.wait_for_selector("#paneDash .dash-node", timeout=60000)
            page.wait_for_function("() => /자료 가져오기/.test(document.querySelector('#paneDash').textContent)", timeout=20000)
            d = page.evaluate(DASH)
            check("② 대시보드 — 묶음 셋", len(d["groups"]) == 3 and "자료 준비" in "".join(d["groups"]) and "지침 작성" in "".join(d["groups"]), d["groups"])
            n = page.evaluate(LIVE)   # 단계마다의 상태 · 글(카드는 편 것만 글을 보인다 — 대시보드가 그리는 값 그대로)
            check("② 지금 차례의 카드가 펴져 그 글과 단추를 보인다", d["nodes"]["take"]["state"] == "now" and "자료가 없습니다" in d["nodes"]["take"]["text"] and "자료 가져오기" in d["nodes"]["take"]["text"], d["nodes"]["take"])
            check("② 문서 라이브러리의 문서 · 끝난 추출 수", n["keep"]["state"] == "done" and "자료 문서 1개" in n["keep"]["text"] and n["extract"]["state"] == "done" and "끝난 추출 1개" in n["extract"]["text"], {k: n[k] for k in ("keep", "extract")})
            check("② 자료 없음 → 「자료 가져오기」 가 지금 차례", n["take"]["state"] == "now" and "자료가 없습니다" in n["take"]["text"] and n["ask"]["state"] == "todo", {k: n[k] for k in ("take", "ask")})
            page.screenshot(path=str(OUT / "02_dash.png"))
            # ③ 자료 가져오기
            page.evaluate("() => fwTakeOpen()")
            page.wait_for_selector("#headsDlgBody .fw-x", timeout=15000)
            c = page.evaluate(COL)
            row = page.evaluate("() => { const r = document.querySelector('#headsDlgBody .fw-x'); return { text: r.textContent, btns: [...r.querySelectorAll('button')].map((b) => [b.textContent, b.disabled]) }; }")
            check("③ 2열 「자료 가져오기」 — 추출 줄", c["kind"] == "fwTake" and c["title"] == "자료 가져오기" and not c["over"] and "한국선급의 SSCB 서브모듈 설계" in row["text"] and "쪽 1–3" in row["text"]
                  and "그림 1" in row["text"] and "수식 1" in row["text"] and "확인 필요 1" in row["text"] and row["btns"] == [["보기", False], ["가져오기", False]], (c, row))
            page.screenshot(path=str(OUT / "03_take.png"))
            page.click("#headsDlgBody .fw-x button:has-text('가져오기')")
            page.wait_for_function("() => [...document.querySelectorAll('#headsDlgBody .fw-x button')].some((b) => b.textContent === '가져옴' && b.disabled)", timeout=15000)
            mats = requests.get(f"{base}/api/docs/{doc}/agent", timeout=10).json()["materials"]
            check("③ 가져오면 이 문서의 자료가 된다(문서 라이브러리 서버에서 읽어 온 MD)", len(mats) == 1 and mats[0]["kind"] == "md" and mats[0]["name"] == "연차보고서_견본 — 한국선급의 SSCB 서브모듈 설계.md" and f"({eid})" in mats[0]["note"], mats)
            # ④ 지침 작성
            page.evaluate("() => fwWriteOpen()")
            page.wait_for_selector("#headsDlgBody .fw-note", timeout=15000)
            c, ps, foot = page.evaluate(COL), page.evaluate(PLACES), page.evaluate(FOOT)
            mat = page.evaluate("() => [...document.querySelectorAll('#headsDlgBody .fw-mats .fw-mat')].map((l) => [l.textContent, l.querySelector('input').checked])")
            check("④ 2열 「지침 작성」 — 쓸 자료가 고른 채로", c["kind"] == "fwWrite" and not c["over"] and len(mat) == 1 and mat[0][1] and "연차보고서_견본" in mat[0][0], (c, mat))
            check("④ 작성 지침이 있는 자리만(기본) — 자리마다 지침", len(ps) >= 3 and all(any(t.startswith("지침") for t in p["tags"]) and p["guides"] >= 1 for p in ps), ps[:6])
            check("④ LLM 꺼짐 — 「제안 받기」 꺼짐 + 까닭", foot["btns"][-1][0] == "제안 받기" and foot["btns"][-1][1] and foot["btns"][-1][2] == "LLM 을 쓸 수 없습니다", foot)
            page.click("#headsDlgBody .fw-places-head input[type=checkbox]")
            page.wait_for_function(f"() => document.querySelectorAll('#headsDlgBody .fw-place').length > {len(ps)}", timeout=10000)
            allp = page.evaluate(PLACES)
            check("④ 끄면 모든 헤딩이 보인다", len(allp) > len(ps) and any(not p["tags"] or not any(t.startswith("지침") for t in p["tags"]) for p in allp), len(allp))
            page.click("#headsDlgBody .fw-places-head input[type=checkbox]")
            page.wait_for_function(f"() => document.querySelectorAll('#headsDlgBody .fw-place').length === {len(ps)}", timeout=10000)
            page.screenshot(path=str(OUT / "04_write.png"))
            # ⑤ 흉내 낸 실행 — 상태 응답의 enabled · run 만 바꾼다(자리 · 자료는 진짜)
            sent, phase = [], {"n": 0, "run": None}

            def gw(route):
                req = route.request
                if req.method == "POST" and req.url.endswith("/guide-write/run"):
                    body = json.loads(req.post_data)
                    sent.append(body)
                    phase["run"] = {"id": "r1", "at": time.time(), "ended": None, "state": "running", "note": body["note"], "materials": body["materials"], "lost": 0,
                                    "items": [{"id": p, "kind": "head", "text": p, "state": "queued", "turn": None, "proposals": 0, "reply": "", "error": None} for p in body["places"]]}
                    return route.fulfill(json={"run": phase["run"]})
                if req.method == "POST" and req.url.endswith("/guide-write/stop"):
                    return route.fulfill(json={"ok": True, "stopping": True})
                real = route.fetch()
                data = real.json()
                data["enabled"] = True
                if phase["run"]:
                    phase["n"] += 1
                    if phase["n"] >= 2:
                        its = phase["run"]["items"]
                        its[0].update(state="done", proposals=2, turn="t1", reply="제안")
                        if len(its) > 1:
                            its[1].update(state="none", reply="자료에 없습니다")
                        if len(its) > 2:
                            its[2].update(state="failed", error="가짜 실패")
                        phase["run"].update(state="done", ended=time.time())
                    data["run"] = phase["run"]
                route.fulfill(json=data)
            page.route(GW, gw)   # 정규식으로 — 글롭 「**/guide-write**」 는 아래 길(/run · /stop)을 못 잡는다
            page.evaluate("() => fwRead(true).then(fwRedraw)")
            page.wait_for_function("() => { const b = [...document.querySelectorAll('#headsDlgFoot button')].pop(); return b && b.title === '채울 자리를 고르세요'; }", timeout=10000)
            for i in range(3):
                page.click(f"#headsDlgBody .fw-place:nth-of-type({i + 1}) > input") if False else page.evaluate("(i) => document.querySelectorAll('#headsDlgBody .fw-place > input')[i].click()", i)
            page.fill("#headsDlgBody .fw-note", "개조식으로 3줄")
            page.evaluate("() => document.activeElement && document.activeElement.blur()")
            foot = page.evaluate(FOOT)
            check("⑤ 자리를 고르면 「제안 받기 (3곳)」", foot["btns"][-1][0] == "제안 받기 (3곳)" and not foot["btns"][-1][1], foot)
            page.once("dialog", lambda dlg: dlg.accept())
            page.click("#headsDlgFoot button.primary")
            page.wait_for_function("() => /마지막 실행 — 제안 2개 · 자료에 없음 1곳 · 실패 1곳/.test(document.getElementById('headsDlgFoot').textContent)", timeout=20000)
            check("⑤ 실행 요청의 본문 {places, materials, note}", len(sent) == 1 and len(sent[0]["places"]) == 3 and sent[0]["materials"] == [mats[0]["id"]] and sent[0]["note"] == "개조식으로 3줄", sent)
            tags = [p["tags"] for p in page.evaluate(PLACES)[:3]]
            check("⑤ 끝나면 자리마다 결과 꼬리표", "제안 2" in tags[0] and "자료에 없음" in tags[1] and "실패" in tags[2], tags)
            page.screenshot(path=str(OUT / "05_ran.png"))
            page.unroute(GW)
            # ⑥ 문서 라이브러리 서버의 화면
            lp = br.new_page(viewport={"width": 1400, "height": 950})
            lp.on("console", lambda m: errors.append("lib: " + m.text) if m.type == "error" else None)
            lp.on("pageerror", lambda e: errors.append("lib: " + str(e)))
            lp.goto(f"{lib}/#d={did}&x={eid}")
            lp.wait_for_selector("#mdSec pre", timeout=20000)
            lp.wait_for_function("() => /차단 시간 1 ms/.test(document.querySelector('#mdSec pre').textContent)", timeout=10000)
            v = lp.evaluate("""() => ({ docs: [...document.querySelectorAll('#docList li .doc-name')].map((x) => x.textContent), card: document.querySelector('#xSec .x-card').textContent, figs: document.querySelectorAll('#mdSec .figs figure').length,
              warn: document.querySelectorAll('#mdSec .figs figure.warn').length, img: (document.querySelector('#mdSec .figs img') || {}).naturalWidth || 0, chip: document.getElementById('llmChip').textContent,
              focus: document.querySelector('#work textarea').value, over: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1 })""")
            check("⑥ 문서 라이브러리 — 문서 · 추출 카드 · MD · 그림", v["docs"] == ["연차보고서_견본.pdf"] and "끝남" in v["card"] and "확인 필요 1" in v["card"] and v["figs"] == 1 and v["warn"] == 1 and v["img"] == 240
                  and v["chip"] == "LLM 꺼짐" and v["focus"] == "한국선급 · SSCB 설계" and not v["over"], v)
            lp.click("#skillBtn")
            lp.wait_for_selector("#skillDlg[open] #skillTabs button", timeout=10000)
            sk = lp.evaluate("() => ({ tabs: [...document.querySelectorAll('#skillTabs button')].map((b) => b.textContent), text: document.getElementById('skillText').value.slice(0, 40), contract: document.getElementById('skillContract').textContent.length })")
            check("⑥ 「스킬 글」 — 셋 · 계약", len(sk["tabs"]) == 3 and sk["text"].startswith("# 자료 추출") and sk["contract"] > 200, sk)
            lp.screenshot(path=str(OUT / "06_library.png"))
            lp.close()
            # 문서 라이브러리 서버를 끄면
            procs[0].terminate()
            procs[0].wait(timeout=20)
            page.evaluate("() => fwRead(true).then(() => dashDraw(true))")
            page.wait_for_function("() => FW.lib && FW.lib.alive === false", timeout=20000)
            d = page.evaluate(LIVE)
            check("문서 라이브러리 서버가 꺼지면 대시보드가 알린다(자료는 그대로)", d["keep"]["state"] == "hold" and d["keep"]["acts"] == [["문서 라이브러리 열기", True]] and d["take"]["state"] == "done" and "이 문서의 자료 1개" in d["take"]["text"], {k: d[k] for k in ("keep", "take")})
            page.screenshot(path=str(OUT / "07_lib_down.png"))
            br.close()
        check("콘솔 오류 없음", not errors, errors[:5])
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
    print(("FAILED: " + ", ".join(fails)) if fails else "ALL PASS", flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

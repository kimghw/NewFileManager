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
- ④-1 「양식 검토」(끝점 응답만 바꿈 — spec_양식작성 ② §5-1) — 검토 전 = 「제안 받기」 꺼짐 「먼저 「양식 검토」 를 하세요」 · 양식만 검토 = 「작성 계획 세우기」 가 다음(「제안 받기」 꺼짐) · 작성 계획 뒤 자리 줄의 「자료에서 쓸 것」 · 「자료에 없는 것」 · 확인할 것(물음 · 「자료에서: …」 · 「자료대로」) · 답하지 않은 물음이 있으면 꺼짐 + 까닭 · 「자료대로」 → PUT 본문 · 자리 줄의 「작성 방향」.
- ⑤ 흉내 낸 실행(끝점 응답만 바꿈) — 「제안 받기 (n곳)」 → 확인 창 → POST 본문 {places, materials, note} · 도는 동안 진행 글 · 「멈춤」 · 끝나면 자리마다 꼬리표(제안 n · 자료에 없음 · 실패).
- ⑥ 문서 라이브러리 서버의 화면 — 문서 줄 · 추출 결과 카드 · MD 글과 그림 · 「스킬 글」(셋 · 계약) · 문서 편집 서버가 꺼져도 뜬다는 것은 보지 않는다(따로 선 프로세스임은 포트가 다른 것으로).
- ⑦ 에이전트 보기의 「라이브러리」(doc_agent.js — 입력 칸 위에 펴지는 고르기 · 창 아님) — 등록 문서마다 추출(MD) 줄 · 추출 전인 문서의 원본 파일 줄 · 「전체 선택」 · 문서 줄의 체크 · 「가져오기 (n)」 → 자료 칩(진짜 끝점 — {extract} · {doc}) · 자료 한도에서 멈춤 · 「가져옴」 · 꺼진 서버.
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
FR = re.compile(r"/form-review(/|$|\?)")


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
            page.wait_for_selector("#paneDash .dash-node[data-key=heads][data-state=done]", timeout=90000)   # 헤딩 · 표 분석(스크립트) · 작성 지침 저장이 끝난 뒤 — 도는 동안은 02 가 「진행 중」 이라 그 카드가 펴진다(부하가 크면 늦다)
            d = page.evaluate(DASH)
            check("② 대시보드 — 묶음 셋", len(d["groups"]) == 3 and "자료 준비" in "".join(d["groups"]) and "지침 작성" in "".join(d["groups"]), d["groups"])
            n = page.evaluate(LIVE)   # 단계마다의 상태 · 글(카드는 편 것만 글을 보인다 — 대시보드가 그리는 값 그대로)
            check("② 지금 차례의 카드가 펴져 그 글과 단추를 보인다", d["nodes"]["take"]["state"] == "now" and "자료가 없습니다" in d["nodes"]["take"]["text"] and "자료 가져오기" in d["nodes"]["take"]["text"], d["nodes"]["take"])
            nows = [k for k, x in d["nodes"].items() if x["state"] == "now"]
            check("② 「지금」 은 한 줄(차례상 첫 줄) — 뒤의 할 수 있는 줄은 「할 수 있음」", nows == ["take"] and d["nodes"]["review"]["state"] == "ready", {k: x["state"] for k, x in d["nodes"].items()})
            fr0 = page.evaluate("() => { const g = FW.gen || 0; document.dispatchEvent(new CustomEvent('nfm:work-reset', { detail: { id: state.id } })); return { key: FW.key, gen: FW.gen, was: g }; }")
            check("② 작업 내용 초기화(nfm:work-reset) — 그 문서의 기억을 버린다", fr0["key"] == "" and fr0["gen"] == fr0["was"] + 1, fr0)
            page.evaluate("() => fwRead(true)")
            check("② 문서 라이브러리의 문서 · 끝난 추출 수", n["keep"]["state"] == "done" and "자료 문서 1개" in n["keep"]["text"] and n["extract"]["state"] == "done" and "끝난 추출 1개" in n["extract"]["text"], {k: n[k] for k in ("keep", "extract")})
            check("② 자료 없음 → 「자료 가져오기」 가 지금 차례", n["take"]["state"] == "now" and "자료가 없습니다" in n["take"]["text"] and n["ask"]["state"] == "todo", {k: n[k] for k in ("take", "ask")})
            # ② 「1 준비」 의 「헤딩 · 표 분석 · 작성 지침」(2026-11-24 사용자 "1준비에 있어야지" · "테이블이나 본문이 지침을 가지고 와야지") — 분석이 끝나면 작성 지침을 저장하고 그 수를 보인다
            page.wait_for_function("async () => { if (typeof docStatusPing === 'function') docStatusPing(); FW.at = 0; const r = await formWriteLive(); return r.steps.heads.state === 'done'; }", timeout=180000, polling=2000)
            n = page.evaluate(LIVE)
            fg = requests.get(f"{base}/api/docs/{doc}/form-guides", timeout=30).json()
            check("② 준비 — 헤딩 · 표 분석 끝남 · 작성 지침을 저장하고 수를 보인다", n["heads"]["state"] == "done" and "헤딩 ✓ · 표 ✓" in n["heads"]["text"] and "작성 지침" in n["heads"]["text"] and fg["saved"] is not None,
                  {"heads": n["heads"], "saved": (fg["saved"] or {}).get("counts")})
            check("② 준비 — LLM 검증·보완은 선택 줄(사람이 누를 때만)", "headsLlm" in n and n["headsLlm"]["state"] in ("", "done"), n.get("headsLlm"))
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
            # ④-1 양식 검토 — 검토가 없으면 「제안 받기」 가 꺼진다 → 흉내 낸 검토(물음 하나) → 답하면 열린다
            pid = page.evaluate("() => (FW.gw.places.find((p) => p.n) || FW.gw.places[0]).id")
            rv = {"summary": "양식 요약", "materials": [mats[0]["id"]], "places": {pid: {"how": "개조식 3줄", "needs": "목표 수치", "use": "자료의 최종 목표 문단", "gap": "기준 연도"}}, "questions": [{"key": "q1", "text": "어느 기관의 몫을 쓰나요?", "why": "자료에 여러 기관", "places": [], "choices": ["한국선급"], "suggest": "한국선급", "source": "한국선급(KR)"}]}
            fr, put = {"review": None, "planned": False, "decided": [], "open": [], "stale": False, "run": None, "hwpx": True, "enabled": True}, []

            def frh(route):
                req = route.request
                if req.method == "PUT":
                    put.append(json.loads(req.post_data))
                    fr.update(decided=[{"key": "q1", "q": rv["questions"][0]["text"], "a": put[-1]["answers"][0]["a"], "places": [], "at": 0}], open=[])
                return route.fulfill(json=fr)
            page.route(FR, frh)
            page.route(GW, gw)   # 정규식으로 — 글롭 「**/guide-write**」 는 아래 길(/run · /stop)을 못 잡는다
            page.evaluate("() => fwRead(true).then(fwRedraw)")
            page.wait_for_function("() => { const b = [...document.querySelectorAll('#headsDlgFoot button')].pop(); return b && b.disabled && b.title === '먼저 「양식 검토」 를 하세요'; }", timeout=10000)
            check("④-1 검토 전 — 「양식 검토」 단추 · 「제안 받기」 꺼짐", page.evaluate("() => [...document.querySelectorAll('#headsDlgBody .fw-review button')].map((b) => b.textContent)") == ["양식 검토"], None)
            # 양식만 검토한 상태(자료 없이) — 작성 방향은 보이고, 「작성 계획 세우기」 가 다음 · 「제안 받기」 는 아직 꺼짐
            only = {**rv, "materials": [], "places": {pid: {"how": "개조식 3줄", "needs": "목표 수치", "use": "", "gap": ""}}, "questions": [{**rv["questions"][0], "suggest": "", "source": ""}]}
            fr.update(review=only, open=["q1"])
            page.evaluate("() => fwRead(true).then(fwRedraw)")
            page.wait_for_function("() => { const b = [...document.querySelectorAll('#headsDlgFoot button')].pop(); return b && b.disabled && b.title === '자료를 고르고 「작성 계획 세우기」 를 하세요'; }", timeout=10000)
            st = page.evaluate("() => ({ btn: document.querySelector('#headsDlgBody .fw-review .fw-places-head button').textContent, steps: [...document.querySelectorAll('#headsDlgBody .fw-steps .fw-tag')].map((x) => x.textContent), how: [...document.querySelectorAll('#headsDlgBody .fw-how')].map((x) => x.textContent) })")
            check("④-1 양식만 검토 — 「작성 계획 세우기」 가 다음 · 작성 방향만(계획 없음)", st["btn"] == "작성 계획 세우기" and st["steps"] == ["양식 검토 ✓", "작성 계획", "확인할 것"] and st["how"] == ["작성 방향: 개조식 3줄"], st)
            # 자료로 작성 계획을 세운 상태 — 자리마다 자료에서 쓸 것 · 자료에 없는 것 + 확인할 것
            fr.update(review=rv, planned=True, open=["q1"])
            page.evaluate("() => fwRead(true).then(fwRedraw)")
            page.wait_for_selector("#headsDlgBody .fw-use", timeout=10000)
            q = page.evaluate("() => { const q = document.querySelector('#headsDlgBody .fw-q'); return { text: q.textContent, btns: [...q.querySelectorAll('button')].map((b) => [b.textContent, b.title]) }; }")
            foot = page.evaluate(FOOT)
            how = page.evaluate("(id) => [...document.querySelectorAll('#headsDlgBody .fw-how')].map((x) => x.textContent)", pid)
            check("④-1 검토 뒤 — 확인할 것(물음 · 자료에서 · 고를 답 · 자료대로) · 「제안 받기」 꺼짐 + 까닭 · 작성 방향", "어느 기관의 몫을 쓰나요?" in q["text"] and q["btns"][0] == ["자료에서: 한국선급", "근거: 한국선급(KR)"]
                  and [b[0] for b in q["btns"][1:]] == ["한국선급", "자료대로"] and foot["btns"][-1][1] and foot["btns"][-1][2] == "쓰기 전에 확인할 것 1개에 답하세요" and how == ["작성 방향: 개조식 3줄", "자료에서 쓸 것: 자료의 최종 목표 문단", "자료에 없는 것: 기준 연도"]
                  and page.evaluate("() => [...document.querySelectorAll('#headsDlgBody .fw-steps .fw-tag')].map((x) => x.textContent)") == ["양식 검토 ✓", "작성 계획 ✓", "확인할 것 0/1"], (q, foot, how))
            page.screenshot(path=str(OUT / "04b_review.png"))
            page.click("#headsDlgBody .fw-q button:has-text('자료대로')")
            page.wait_for_function("() => !document.querySelector('#headsDlgBody .fw-q.is-open')", timeout=10000)
            check("④-1 「자료대로」 → PUT {answers:[{key, a}]} · 물음이 닫힌다", put == [{"answers": [{"key": "q1", "a": "자료대로"}]}], put)
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
            page.unroute(FR)
            # ⑥ 문서 라이브러리 서버의 화면
            lp = br.new_page(viewport={"width": 1400, "height": 950})
            lp.on("console", lambda m: errors.append("lib: " + m.text) if m.type == "error" else None)
            lp.on("pageerror", lambda e: errors.append("lib: " + str(e)))
            lp.goto(f"{lib}/#d={did}&x={eid}")
            # 처음은 「미리보기」(마크다운을 그린 꼴 — md_preview.js) → 「원문」 을 누르면 MD 글 그대로
            lp.wait_for_selector("#mdSec .md-prev .mp", timeout=20000)
            pv = lp.evaluate("""() => { const m = document.querySelector('#mdSec .md-prev .mp'); return { on: [...document.querySelectorAll('#mdSec .md-seg button.on')].map((b) => b.textContent), preHidden: document.querySelector('#mdSec pre').hidden,
              h2: [...m.querySelectorAll('h2')].map((x) => x.textContent), li: (m.querySelector('li') || {}).textContent || '', quote: !!m.querySelector('blockquote'), page: (m.querySelector('.mp-page') || {}).textContent || '',
              fig: !!m.querySelector('.mp-fig img[src*="images/p1_F1.png"]'), warn: (m.querySelector('.mp-warn') || {}).textContent || '', math: (m.querySelector('.mp-math code') || {}).textContent || '' }; }""")
            check("⑥ MD 미리보기 — 제목 · 목록 · 인용 · 쪽 · 그림 · 확인 필요 · 수식", pv["on"] == ["미리보기"] and pv["preHidden"] and pv["h2"] == ["연구개발 목표"] and "차단 시간 1 ms" in pv["li"] and pv["quote"]
                  and pv["page"] == "p.1" and pv["fig"] and pv["warn"].startswith("확인 필요") and "V_{pk}" in pv["math"], pv)
            lp.screenshot(path=str(OUT / "06_library_preview.png"))
            # 위 접기 — MD 가 보이면 처음은 문서 정보 · 자료 추출 · 추출 결과가 한 줄(fold-bar)로 접혀 있다 → 그 줄을 누르면 펼침 → 「위 접기」 로 다시
            FOLD = "() => ({ folded: document.getElementById('work').classList.contains('folded'), bar: (() => { const b = document.getElementById('foldBar'); return b && !b.hidden && b.offsetHeight > 0 && b.offsetHeight < 60 ? b.textContent : ''; })(), x: !!document.querySelector('#xSec').offsetHeight, run: !!document.querySelector('.run-sec').offsetHeight, btn: !!document.querySelector('#mdSec .btn-fold').offsetHeight })"
            f0 = lp.evaluate(FOLD)
            lp.click("#foldBar")
            f1 = lp.evaluate(FOLD)
            lp.click("#mdSec .btn-fold")
            f2 = lp.evaluate(FOLD)
            check("⑥ 위 접기 — 처음 접힘(한 줄) · 누르면 펼침 · 「위 접기」 로 다시", f0["folded"] and "연차보고서_견본.pdf" in f0["bar"] and "펼치기" in f0["bar"] and not f0["x"] and not f0["run"] and not f0["btn"]
                  and not f1["folded"] and not f1["bar"] and f1["x"] and f1["run"] and f1["btn"] and f2["folded"] and f2["bar"] and not f2["x"], [f0, f1, f2])
            lp.click("#foldBar")
            lp.click("#mdSec .md-seg button[data-mode=raw]")
            lp.wait_for_selector("#mdSec pre", timeout=5000)
            lp.wait_for_function("() => /차단 시간 1 ms/.test(document.querySelector('#mdSec pre').textContent) && document.querySelector('#mdSec .md-prev').hidden", timeout=10000)
            try:   # 그림은 loading=lazy — 그림 칸이 MD 옆 열(2026-11-24 꼴)이라 읽기 전에 로드를 기다린다
                lp.wait_for_function("() => { const i = document.querySelector('#mdSec .figs img'); return i && i.complete && i.naturalWidth > 0; }", timeout=10000)
            except Exception:
                pass
            v = lp.evaluate("""() => ({ docs: [...document.querySelectorAll('#docList li .doc-name')].map((x) => x.textContent), card: document.querySelector('#xSec .x-card').textContent, figs: document.querySelectorAll('#mdSec .figs figure').length,
              warn: document.querySelectorAll('#mdSec .figs figure.warn').length, img: (document.querySelector('#mdSec .figs img') || {}).naturalWidth || 0, chip: document.getElementById('llmChip').textContent,
              focus: document.querySelector('#work textarea').value, over: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1 })""")
            check("⑥ 문서 라이브러리 — 문서 · 추출 카드 · MD · 그림", v["docs"] == ["연차보고서_견본.pdf"] and "끝남" in v["card"] and "확인 필요 1" in v["card"] and v["figs"] == 1 and v["warn"] == 1 and v["img"] == 240
                  and v["chip"] == "LLM 꺼짐" and v["focus"] == "한국선급 · SSCB 설계" and not v["over"], v)
            # 뽑을 범위 여럿(spec_양식작성 ② §3 「범위 여럿」) — 줄마다 범위 하나 = MD 하나: 한 줄에 「1.… 2.…」 를 적으면 나누기를 권하고(저절로 나누지 않음) · 나누면 줄 둘 + 번호 · 「＋ 범위 추가」 · 요청은 focuses[]
            SC = """() => ({ rows: [...document.querySelectorAll('#work .scope textarea')].map((t) => t.value), many: document.querySelector('#work .scopes').classList.contains('many'),
              split: (() => { const b = document.querySelector('#work .scope-split'); return b.offsetWidth ? b.textContent : ''; })(), hint: document.querySelector('#work .run-hint').textContent,
              nums: [...document.querySelectorAll('#work .scope-n')].filter((n) => n.offsetWidth).map((n) => n.textContent), over: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1 })"""
            lp.fill("#work .scope textarea", "1.한국선급, 2.인텍전기전자")
            sp0 = lp.evaluate(SC)
            lp.click("#work .scope-split")
            sp1 = lp.evaluate(SC)
            lp.click("#work .scope-add")
            lp.keyboard.type("한국선급, 1·2차년도")
            sp2 = lp.evaluate(SC)
            check("⑥ 뽑을 범위 여럿 — 나누기 권함 · 줄마다 범위 · 번호 · 안내", sp0["rows"] == ["1.한국선급, 2.인텍전기전자"] and sp0["split"] == "범위 2개로 나누기" and not sp0["many"] and "MD" not in sp0["hint"]
                  and sp1["rows"] == ["한국선급", "인텍전기전자"] and sp1["many"] and not sp1["split"] and sp1["nums"] == ["1", "2"] and "범위 2개 → MD 2개" in sp1["hint"]
                  and sp2["rows"] == ["한국선급", "인텍전기전자", "한국선급, 1·2차년도"] and not sp2["split"] and "범위 3개 → MD 3개" in sp2["hint"] and not sp2["over"], [sp0, sp1, sp2])
            posted, asked = [], []
            XS = re.compile(r"/api/docs/[^/]+/extracts$")
            lp.route(XS, lambda r: (posted.append(json.loads(r.request.post_data)), r.fulfill(status=200, content_type="application/json", body='{"extract":{"id":"x0000000000"},"extracts":[]}'))[1])   # 가짜 답 — 실제 추출은 시작하지 않는다(LLM 꺼짐)
            lp.once("dialog", lambda dlg: (asked.append(dlg.message), dlg.accept())[1])
            lp.click("#work .btn-go")
            lp.wait_for_function("() => !document.querySelector('#work .btn-go').disabled", timeout=10000)
            lp.wait_for_timeout(300)
            check("⑥ 「추출 시작」 — 범위 여럿은 focuses[] 로 · 확인 창에 범위와 「문서는 한 번만」", posted == [{"focuses": ["한국선급", "인텍전기전자", "한국선급, 1·2차년도"]}] and len(asked) == 1 and "범위 3개 → MD 3개" in asked[0] and "2. 인텍전기전자" in asked[0], [posted, asked])
            lp.unroute(XS)
            lp.click("#work .scope:nth-child(3) .scope-del")
            lp.click("#work .scope:nth-child(2) .scope-del")
            sp3 = lp.evaluate(SC)
            check("⑥ 범위 빼기 — 하나 남으면 번호 없이", sp3["rows"] == ["한국선급"] and not sp3["many"] and sp3["nums"] == [] and "MD" not in sp3["hint"], sp3)
            lp.click("#skillBtn")
            lp.wait_for_selector("#skillDlg[open] #skillTabs button", timeout=10000)
            sk = lp.evaluate("() => ({ tabs: [...document.querySelectorAll('#skillTabs button')].map((b) => b.textContent), text: document.getElementById('skillText').value.slice(0, 40), contract: document.getElementById('skillContract').textContent.length })")
            check("⑥ 「스킬 글」 — 셋 · 계약", len(sk["tabs"]) == 3 and sk["text"].startswith("# 자료 추출") and sk["contract"] > 200, sk)
            lp.screenshot(path=str(OUT / "06_library.png"))
            lp.close()
            # ⑦ 에이전트 보기의 「라이브러리」 — 입력 칸 위에 펴지는 고르기(2026-11-24 사용자 "에이전트에서는 라이브러리에서 등록한 파일들을 선택해서 참조할 수 있도록 해줘, 전체 해도 되고" — spec_양식작성 ② §4)
            #    추출 전인 문서 하나를 더 올려 두고(원본 파일을 글로 읽어 자료로) 본 뒤, 그 문서와 그 자료를 지운다(뒤 검사의 수가 그대로이게)
            import fitz
            raw = fitz.open()
            raw.new_page().insert_text((72, 72), "raw original text of the registered file")
            did2 = requests.post(lib + "/api/docs", files={"file": ("추출 전 문서.pdf", raw.tobytes())}, timeout=30).json()["doc"]["id"]
            SHELF = """() => { const b = document.querySelector('#paneAgent .ag-lib'); if (!b || b.hidden) return null;
              const t = b.querySelector('[data-ag-act=shelfTake]');
              return { rows: Object.fromEntries([...b.querySelectorAll('.ag-lib-row')].map((r) => [r.dataset.agLib, { text: r.textContent, on: r.querySelector('input').checked, off: r.querySelector('input').disabled, tags: [...r.querySelectorAll('.ag-lib-tag')].map((x) => x.textContent) }])),
                state: (b.querySelector('.ag-lib-state') || {}).textContent || '', take: t ? [t.textContent, t.disabled] : null, msg: (b.querySelector('.ag-lib-msg') || {}).textContent || '', count: b.querySelector('.ag-lib-count').textContent,
                over: b.scrollWidth > b.clientWidth + 1, help: !!b.querySelector('.ag-lib-head .panel-help'), dialog: document.querySelectorAll('dialog[open]').length, paste: !document.querySelector('#paneAgent .ag-paste').hidden,
                chips: document.querySelectorAll('#paneAgent .ag-chip').length, pressed: document.querySelector('#paneAgent [data-ag-act=shelf]').getAttribute('aria-pressed') }; }"""
            page.evaluate("() => { if (typeof headsColClose === 'function') headsColClose(true); showTab('Agent'); }")
            page.wait_for_function("() => AGENT.loaded && !!document.querySelector('#paneAgent [data-ag-act=shelf]:not([disabled])')", timeout=30000)
            acts = page.evaluate("() => [...document.querySelectorAll('#paneAgent .ag-mats > button')].map((b) => b.textContent)")
            check("⑦ 에이전트 보기의 자료 단추 셋 — 자료 붙여넣기 · 파일 · 라이브러리", acts == ["자료 붙여넣기", "파일", "라이브러리"], acts)
            page.click("#paneAgent .ag-chip .ag-chip-x")   # ③ 에서 가져온 자료를 지운다 — 고르기에서 추출(MD)과 원본 파일 둘을 함께 가져오게
            page.wait_for_function("() => !document.querySelector('#paneAgent .ag-chip')", timeout=15000)
            page.click("#paneAgent [data-ag-act=shelf]")
            page.wait_for_function("() => document.querySelectorAll('#paneAgent .ag-lib .ag-lib-row.is-item').length === 2", timeout=20000)
            s0 = page.evaluate(SHELF)
            check("⑦ 「라이브러리」 — 입력 칸 위에 펴진다(창 아님) · 등록 문서 둘 · 추출(MD) 줄과 원본 파일 줄 · 설명은 노트 아이콘에", s0["dialog"] == 0 and not s0["paste"] and s0["pressed"] == "true" and s0["help"] and not s0["over"]
                  and s0["count"] == "이 문서의 자료 0/30" and set(s0["rows"]) == {"all", f"doc:{did}", f"x:{eid}", f"doc:{did2}", f"d:{did2}"}
                  and "한국선급의 SSCB 서브모듈 설계" in s0["rows"][f"x:{eid}"]["text"] and "쪽 1–3" in s0["rows"][f"x:{eid}"]["text"] and s0["rows"][f"x:{eid}"]["tags"] == ["확인 필요 1"]
                  and "원본 파일" in s0["rows"][f"d:{did2}"]["text"] and "pdf" in s0["rows"][f"d:{did2}"]["text"] and "추출 전" in s0["rows"][f"doc:{did2}"]["text"] and "추출 1개" in s0["rows"][f"doc:{did}"]["text"]
                  and "고를 수 있는 것 2개" in s0["rows"]["all"]["text"] and not any(r["on"] or r["off"] for r in s0["rows"].values()) and s0["take"] == ["가져오기", True], s0)
            page.click("#paneAgent .ag-lib-row[data-ag-lib=all] input")
            s1 = page.evaluate(SHELF)
            page.click(f"#paneAgent .ag-lib-row[data-ag-lib='doc:{did2}'] input")   # 문서 줄의 체크 = 그 문서의 것만 뺀다
            s2 = page.evaluate(SHELF)
            page.click(f"#paneAgent .ag-lib-row[data-ag-lib='doc:{did2}'] input")
            check("⑦ 「전체 선택」 → 모두 고름 · 문서 줄의 체크로 그 문서만 빼고 넣음", all(r["on"] for r in s1["rows"].values()) and s1["take"] == ["가져오기 (2)", False]
                  and s2["take"] == ["가져오기 (1)", False] and not s2["rows"][f"d:{did2}"]["on"] and s2["rows"][f"x:{eid}"]["on"] and not s2["rows"]["all"]["on"], [s1["take"], s2])
            page.screenshot(path=str(OUT / "06b_agent_library.png"))
            page.evaluate("() => { AGENT.limits = { ...AGENT.limits, materials: 1 }; }")   # 자료 한도에 닿으면 거기서 멈추고 못 가져온 수를 알린다
            page.click("#paneAgent [data-ag-act=shelfTake]")
            page.wait_for_function("() => /남은 1개는 가져오지 못했습니다/.test((document.querySelector('#paneAgent .ag-lib-msg') || {}).textContent || '')", timeout=30000)
            s3 = page.evaluate(SHELF)
            check("⑦ 자료 한도 — 하나만 가져오고 멈춤 · 못 가져온 수를 알림", s3["chips"] == 1 and "자료 1개를 가져왔습니다" in s3["msg"] and "자료는 1개까지 둘 수 있습니다" in s3["msg"] and s3["take"] == ["가져오기 (1)", False]
                  and sorted(len(r["tags"]) for k, r in s3["rows"].items() if k[:2] in ("x:", "d:")) in ([0, 2], [1, 1]), s3)
            page.evaluate("() => { AGENT.limits = { ...AGENT.limits, materials: 30 }; }")
            page.click("#paneAgent [data-ag-act=shelfTake]")
            page.wait_for_function("() => document.querySelectorAll('#paneAgent .ag-chip').length === 2 && !document.querySelector('#paneAgent .ag-lib .sl-run')", timeout=30000)
            s4 = page.evaluate(SHELF)
            mats2 = requests.get(f"{base}/api/docs/{doc}/agent", timeout=10).json()["materials"]
            rawm = next((m for m in mats2 if m["kind"] == "pdf"), None)
            check("⑦ 「가져오기」 — 추출(MD)과 원본 파일이 이 문서의 자료가 된다 · 줄은 「가져옴」 · 더 고를 것 없음", len(mats2) == 2 and {m["kind"] for m in mats2} == {"md", "pdf"} and rawm and f"문서 라이브러리의 원본({did2})" in rawm["note"]
                  and rawm["name"] == "추출 전 문서.pdf" and "가져옴" in s4["rows"][f"x:{eid}"]["tags"] and s4["rows"][f"d:{did2}"]["tags"] == ["가져옴"] and s4["rows"]["all"]["off"] and all(r["off"] for r in s4["rows"].values())
                  and s4["take"] == ["가져오기", True] and s4["count"] == "이 문서의 자료 2/30" and "자료 1개를 가져왔습니다" in s4["msg"] and not s4["over"], (s4, mats2))
            page.locator("#paneAgent .ag-input").screenshot(path=str(OUT / "06c_agent_library_taken.png"))
            requests.delete(f"{base}/api/docs/{doc}/agent/material/{rawm['id']}", timeout=10) if rawm else None
            requests.delete(lib + f"/api/docs/{did2}", timeout=10)
            page.click("#paneAgent .ag-lib-head button:has-text('닫기')")
            check("⑦ 「닫기」 — 고르기가 접힌다", page.evaluate(SHELF) is None and page.evaluate("() => document.querySelector('#paneAgent [data-ag-act=shelf]').getAttribute('aria-pressed')") == "false")
            page.evaluate("() => agentLoad(true)")
            page.wait_for_function("() => document.querySelectorAll('#paneAgent .ag-chip').length === 1", timeout=15000)
            # 문서 라이브러리 서버를 끄면
            procs[0].terminate()
            procs[0].wait(timeout=20)
            page.evaluate("() => fwRead(true).then(() => dashDraw(true))")
            page.wait_for_function("() => FW.lib && FW.lib.alive === false", timeout=20000)
            d = page.evaluate(LIVE)
            check("문서 라이브러리 서버가 꺼지면 대시보드가 알린다(자료는 그대로)", d["keep"]["state"] == "hold" and d["keep"]["acts"] == [["문서 라이브러리 열기", True]] and d["take"]["state"] == "done" and "이 문서의 자료 1개" in d["take"]["text"], {k: d[k] for k in ("keep", "take")})
            page.screenshot(path=str(OUT / "07_lib_down.png"))
            page.click("#paneAgent [data-ag-act=shelf]")   # ⑦ 꺼진 뒤의 고르기 — 꺼져 있다고 알리고 가져오기는 꺼진다(자료 칩은 그대로)
            page.wait_for_function("() => /꺼져 있습니다/.test((document.querySelector('#paneAgent .ag-lib-state') || {}).textContent || '')", timeout=30000)
            s5 = page.evaluate(SHELF)
            check("⑦ 문서 라이브러리 서버가 꺼지면 고르기가 알린다(띄우개 · 가져오기 꺼짐 · 자료 칩 그대로)", "tools/start_doclib.ps1" in s5["state"] and s5["take"] == ["가져오기", True] and not s5["rows"] and s5["chips"] == 1, s5)
            page.locator("#paneAgent .ag-input").screenshot(path=str(OUT / "07b_agent_library_down.png"))
            page.evaluate("() => { AGENT.shelf.open = false; agentDrawInput(); if (typeof agentFloating === 'function' && agentFloating() && typeof agentFloatClose === 'function') agentFloatClose(); }")
            # ⑧ 대시보드에서 「작업 내용 초기화」 — 일반 문서 워크플로우도 대시보드에 머문다(전에는 다시 여는 load 가 에이전트 보기로 바꿨다 —
            #    2026-11-24 사용자 "왜 dash 보드에서 초기화 하면 에이전트 탭으로 너머 가냐": spec_작업에이전트 ② §9 「작업 내용 초기화」 「초기화한 뒤」)
            page.evaluate("() => { if (typeof headsColClose === 'function') headsColClose(); showTab('Dash'); }")
            page.wait_for_selector('#paneDash [data-dash-focus="reset"]:not([disabled])', timeout=30000)
            rid = page.evaluate("() => state.id")
            page.locator('#paneDash [data-dash-focus="reset"]').click()
            page.wait_for_selector(f'#paneDash [data-dash-focus="reset:{rid}"]', timeout=30000)
            page.locator(f'#paneDash [data-dash-focus="reset:{rid}"]').click()
            page.wait_for_function("() => /작업 내용을 초기화했습니다/.test(document.getElementById('toast').textContent) && !!document.querySelector('#doc .para') && !document.querySelector('#paneDash .dash-reset')", timeout=120000)
            page.wait_for_timeout(1200)   # 다시 연 뒤의 그리기(탭을 바꾸던 곳)가 지나가게
            rz = page.evaluate("""() => { const f = document.getElementById('agentFloat'), row = document.querySelector('#paneDash .dash-reset-row');
              return { tool: document.getElementById('panel').dataset.tool, dash: !document.getElementById('paneDash').hidden, float: !!f && !f.hidden && f.offsetWidth > 0,
                row: row ? [...row.querySelectorAll('button')].map((b) => [b.dataset.dashFocus, b.textContent]) : [] }; }""")
            check("⑧ 대시보드의 「작업 내용 초기화」 뒤 — 대시보드에 머묾 · 에이전트 창도 저절로 안 열림 · 맨 아래 줄에 초기화 단추(「다음」 단추가 있으면 그 앞)",
                  rz["tool"] == "Dash" and rz["dash"] and not rz["float"] and rz["row"] and rz["row"][-1][0] == "reset" and all(k in ("reset:next", "reset") for k, _ in rz["row"]), rz)
            page.locator("#paneDash").screenshot(path=str(OUT / "08_reset_stay.png"))
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

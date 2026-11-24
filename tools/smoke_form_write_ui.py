"""워크플로우 「양식 작성」 의 화면(spec_양식작성 ② §2 · §4 · §5 · §6 — 2026-11-24 사용자 "워크플로우에 문서양식을 주고 LLM을 이용해서 문서양식을 작성해주는 TASK" · "이 문서 관리 라이브러리는 별도 서버에서"):
app/static/form_write.js(대시보드의 단계 상태 · 2열 「자료 가져오기」 · 「지침 작성」) · task_catalog.js(카드) · doclib/static(문서 라이브러리 서버의 관리 화면).
화면 확인 — 임시 서버 **둘**(문서 편집 서버 = --port · 문서 라이브러리 서버 = --port + 300 — 임시 저장소 · PDF · LLM 끔)을 스스로 띄우고 끈다 + Playwright. 진짜 끝점으로.
LLM 을 부르지 않는다: 추출 결과는 문서 라이브러리의 저장소에 미리 적어 두고(끝난 추출 하나), 지침 작성의 실행은 「LLM 을 쓸 수 없습니다」 로 꺼진 것까지와 흉내 낸 실행 응답으로 본다.

    python -X utf8 tools/smoke_form_write_ui.py <그림·임시 폴더> [--port 18840]

보는 것:
- ① 목록(task_catalog.js) — form_write: 일반 문서 · 처음 여는 보기 = 대시보드 · 첫 화면에 카드 「양식 작성」 + 로고.
- ② 문서 화면의 대시보드 — 묶음 셋(준비 · 자료 준비 · 작성) · 문서 라이브러리의 문서 · 끝난 추출 수 · 검토 전 → 「양식 검토 · 찾을 테마」 가 지금 차례(자료 없이도 — 자료 준비 앞).
- ③ 2열 「자료 가져오기」 — 문서 라이브러리의 추출 줄(범위 · 쪽 · 그림 · 수식 · 확인 필요) · 「가져오기」 → 이 문서의 자료(진짜 끝점 — 문서 라이브러리 서버에서 MD 를 읽어 온다) · 다시 누를 수 없음(「가져옴」).
- ④ 2열 「지침 작성」 — 쓸 자료(체크) · 이번 작성의 지침 · 자리 목록(작성 지침이 있는 자리만 ↔ 모든 헤딩) · 「작성 지침 보기」 · LLM 꺼짐이면 「작성 초안 받기」 꺼짐 + 까닭 · 가로 넘침 없음.
- ④-1 「양식 검토」(끝점 응답만 바꿈 — spec_양식작성 ② §5-1) — 검토 전 = 「작성 초안 받기」 꺼짐 「먼저 「양식 검토」 를 하세요」 · 양식만 검토 = 「작성 계획 세우기」 가 다음(「작성 초안 받기」 꺼짐) · 작성 계획 뒤 자리 줄의 「자료에서 쓸 것」 · 「자료에 없는 것」 · 확인할 것(물음 · 「자료에서: …」 · 「자료대로」) · 답하지 않은 물음이 있으면 꺼짐 + 까닭 · 「자료대로」 → PUT 본문 · 자리 줄의 「작성 방향」.
- ④-2 「자료에서 찾을 테마 · 키워드」(② §5-2 — 끝점 응답만 바꿈) — 옛 검토(topics 없음) = 「아직 뽑지 않았습니다」 · 테마 줄(키워드 · 맥락 · 닿는 자리) · 앞말 칸이 미리보기를 바꿈 · 「고른 것 복사」 = 미리보기 그대로 · 9번째는 못 고름 · 600자 넘는 줄은 빠짐 · 대시보드의 「테마 · 키워드 보기」.
- ⑤ 흉내 낸 실행(끝점 응답만 바꿈) — 「작성 초안 받기 (n곳)」 → 확인 창 → POST 본문 {places, materials, note, chunks} · 도는 동안 진행 글 · 「멈춤」 · 끝나면 자리마다 꼬리표(초안 n · 자료에 없음 · 실패) · 초안 0개의 까닭 · 반영 수는 이번 실행의 턴만.
- ⑤-1 상자 자리의 「쓸 자리 고르기」(② §5-3 — 자리 목록 응답에 상자 자리를 끼움) — 같은 이름이 하나뿐인 자리는 처음부터 고름 · 같은 이름이 여럿이면 하나만(다른 것을 켜면 앞의 것이 꺼짐) · 「모두 고르기」 는 채운 줄을 빼고 · 실행 요청의 chunks.
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
_G = [{"src": "doc", "kind": "※ 안내", "text": "가짜 지침"}]
_H = {"kind": "head", "depth": 1, "guides": _G, "n": 1, "user": False, "filled": False, "tables": [], "slot": None, "boxed": False}
FAKE = [   # ⑤-1 — 서버가 주는 꼴(guide_write.places): 상자 자리(쓸 자리 셋 — 둘은 같은 이름) · 같은 줄 뒤에 쓰는 줄 · 표시 줄 · 채운 줄 · 상자가 딸린 헤딩
    {"id": "tBOX", "kind": "box", "text": "< 연구개발 과제명 작성 >", "depth": None, "guides": _G, "n": 1, "user": False, "filled": False, "head": None, "top": True, "slots": 11,
     "chunks": [{"key": "c1", "no": 3, "head": "추진 내용 작성", "under": "", "level": 1, "kind": "text", "slots": 5, "paras": ["a1"], "dup": [1, 1]},
                {"key": "c2", "no": 4, "head": "공동(기업명 작성) :", "under": "추진 내용 작성", "level": 4, "kind": "label", "slots": 6, "paras": ["a2"], "dup": [1, 2]},
                {"key": "c3", "no": 5, "head": "공동(기업명 작성) :", "under": "추진 내용 작성", "level": 4, "kind": "label", "slots": 6, "paras": ["a3"], "dup": [2, 2]}]},
    {**_H, "id": "pLAB", "text": "■ 연구개발과제명 :", "slot": "label"}, {**_H, "id": "pCHK", "text": "■ 작성 기준 보고서 ( □ 연차 □ 최종 )", "slot": "check"},
    {**_H, "id": "pFIL", "text": "■ 주관연구개발기관 : 가나다", "slot": "filled"}, {**_H, "id": "pBXD", "text": "■ 성과목표 관리", "boxed": True}]
TOPICS = [{"key": f"t{i + 1}", "name": f"테마 {i + 1}", "keywords": ["개발 목표", "세부 목표"], "context": "상자의 「연구개발 목표」 아래에 개조식으로 씁니다.", "scope": f"범위 {i + 1}", "places": []} for i in range(10)]
TOPIC_LINES = [f"범위 {i + 1} (개발 목표 · 세부 목표)" for i in range(9)] + ["가" * 590]   # 서버의 scope_line(앞말 없이) — 마지막 것은 앞말을 붙이면 600자를 넘는다
TOP = """() => { const s = document.querySelector('#headsDlgBody .fw-topics'); if (!s) return null;
  return { title: s.querySelector('h3').textContent, help: !!s.querySelector('h3 .panel-help'), msg: (s.querySelector('.fw-top-msg') || {}).textContent || '',
    rows: [...s.querySelectorAll('.fw-top')].map((r) => ({ name: r.querySelector('.fw-top-name').textContent, on: r.querySelector('input').checked, kws: [...r.querySelectorAll('.fw-top-kw')].map((k) => k.textContent),
      ctx: (r.querySelector('.fw-top-ctx') || {}).textContent || '', long: r.classList.contains('is-long') })),
    prev: [...s.querySelectorAll('.fw-top-line')].map((l) => l.textContent), copy: (() => { const b = s.querySelector('.fw-top-copy'); return b ? [b.textContent, b.disabled] : null; })(),
    lib: (() => { const b = [...s.querySelectorAll('.fw-top-acts button')].pop(); return b ? [b.textContent, b.disabled] : null; })(), on: FW.topicOn.size,
    over: document.getElementById('headsDlgBody').scrollWidth > document.getElementById('headsDlgBody').clientWidth + 1 }; }"""
BOX = """() => { const r = document.querySelector('#headsDlgBody .fw-place.is-box'); if (!r) return null; const d = r.querySelector('.fw-chunks');
  return { on: r.querySelector(':scope > input').checked, tags: [...r.querySelectorAll('.fw-tags .fw-tag')].map((t) => t.textContent), open: !!(d && d.open), sum: d ? d.querySelector('summary').textContent : '',
    chunks: d ? [...d.querySelectorAll('.fw-chunk')].map((c) => ({ on: c.querySelector('input').checked, text: c.textContent })) : [] }; }"""


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
            check("② 대시보드 — 묶음 셋(준비 · 자료 준비 · 작성)", len(d["groups"]) == 3 and "자료 준비" in "".join(d["groups"]) and "작성" in d["groups"][2] and "지침 작성" not in "".join(d["groups"]), d["groups"])
            n = page.evaluate(LIVE)   # 단계마다의 상태 · 글(카드는 편 것만 글을 보인다 — 대시보드가 그리는 값 그대로)
            check("② 지금 차례의 카드가 펴져 그 글과 단추를 보인다(양식 검토 — 자료 준비 앞)", d["nodes"]["review"]["state"] == "now" and "아직 검토하지 않았습니다" in d["nodes"]["review"]["text"] and "양식 검토 · 찾을 테마" in d["nodes"]["review"]["text"], d["nodes"]["review"])
            nows = [k for k, x in d["nodes"].items() if x["state"] == "now"]
            check("② 「지금」 은 한 줄(차례상 첫 줄) — 뒤의 할 수 있는 줄은 「할 수 있음」", nows == ["review"] and d["nodes"]["take"]["state"] == "ready" and set(d["nodes"]) >= {"guides", "review", "plan", "ask", "apply"}, {k: x["state"] for k, x in d["nodes"].items()})
            fr0 = page.evaluate("() => { const g = FW.gen || 0; document.dispatchEvent(new CustomEvent('nfm:work-reset', { detail: { id: state.id } })); return { key: FW.key, gen: FW.gen, was: g }; }")
            check("② 작업 내용 초기화(nfm:work-reset) — 그 문서의 기억을 버린다", fr0["key"] == "" and fr0["gen"] == fr0["was"] + 1, fr0)
            page.evaluate("() => fwRead(true)")
            check("② 문서 라이브러리의 문서 · 끝난 추출 수", n["keep"]["state"] == "done" and "자료 문서 1개" in n["keep"]["text"] and n["extract"]["state"] == "done" and "끝난 추출 1개" in n["extract"]["text"], {k: n[k] for k in ("keep", "extract")})
            check("② 자료 없음 · 검토 전 → 「양식 검토 · 찾을 테마」 가 지금 차례(자료 없이 된다) · 자료 가져오기는 할 수 있음 · 작성 계획은 아직", n["review"]["state"] == "now" and n["review"]["acts"] == [["양식 검토", False]]
                  and n["take"]["state"] == "ready" and "자료가 없습니다" in n["take"]["text"] and n["plan"]["state"] == "todo" and n["ask"]["state"] == "todo", {k: n[k] for k in ("review", "take", "plan", "ask")})
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
            check("④ LLM 꺼짐 — 「작성 초안 받기」 꺼짐 + 까닭", foot["btns"][-1][0] == "작성 초안 받기" and foot["btns"][-1][1] and foot["btns"][-1][2] == "LLM 을 쓸 수 없습니다", foot)
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
                    phase["run"] = {"id": f"r{len(sent)}", "at": time.time(), "ended": None, "state": "running", "note": body["note"], "materials": body["materials"], "lost": 0,
                                    "items": [{"id": p, "kind": "head", "text": p, "state": "queued", "turn": None, "proposals": 0, "reply": "", "error": None} for p in body["places"]]}
                    return route.fulfill(json={"run": phase["run"]})
                if req.method == "POST" and req.url.endswith("/guide-write/stop"):
                    return route.fulfill(json={"ok": True, "stopping": True})
                real = route.fetch()
                data = real.json()
                data["enabled"] = True
                if phase.get("box"):   # ⑤-1 — 자리 목록의 앞에 상자 자리 · 같은 줄 자리 · 채운 줄 · 상자가 딸린 헤딩을 끼운다(지침이 있는 자리만 보이는 긴 양식이라 지침 하나씩)
                    data["places"] = FAKE + data["places"]
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
            check("④-1 검토 전 — 「양식 검토」 단추 · 「작성 초안 받기」 꺼짐", page.evaluate("() => [...document.querySelectorAll('#headsDlgBody .fw-review button')].map((b) => b.textContent)") == ["양식 검토"], None)
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
            check("④-1 검토 뒤 — 확인할 것(물음 · 자료에서 · 고를 답 · 자료대로) · 「작성 초안 받기」 꺼짐 + 까닭 · 작성 방향", "어느 기관의 몫을 쓰나요?" in q["text"] and q["btns"][0] == ["자료에서: 한국선급", "근거: 한국선급(KR)"]
                  and [b[0] for b in q["btns"][1:]] == ["한국선급", "자료대로"] and foot["btns"][-1][1] and foot["btns"][-1][2] == "쓰기 전에 확인할 것 1개에 답하세요" and how == ["작성 방향: 개조식 3줄", "자료에서 쓸 것: 자료의 최종 목표 문단", "자료에 없는 것: 기준 연도"]
                  and page.evaluate("() => [...document.querySelectorAll('#headsDlgBody .fw-steps .fw-tag')].map((x) => x.textContent)") == ["양식 검토 ✓", "작성 계획 ✓", "확인할 것 0/1"], (q, foot, how))
            page.screenshot(path=str(OUT / "04b_review.png"))
            page.click("#headsDlgBody .fw-q button:has-text('자료대로')")
            page.wait_for_function("() => !document.querySelector('#headsDlgBody .fw-q.is-open')", timeout=10000)
            check("④-1 「자료대로」 → PUT {answers:[{key, a}]} · 물음이 닫힌다", put == [{"answers": [{"key": "q1", "a": "자료대로", "q": "어느 기관의 몫을 쓰나요?"}]}], put)   # 물음 번호와 함께 그 물음의 글도 보낸다(옛 화면의 번호가 다른 물음에 저장되지 않게 — 서버가 견준다)
            page.wait_for_function("() => { const b = [...document.querySelectorAll('#headsDlgFoot button')].pop(); return b && b.title === '채울 자리를 고르세요'; }", timeout=10000)
            # ④-2 자료에서 찾을 테마 · 키워드(2026-11-24 사용자 "여기서 작성 테마/키워드를 추출해줘 … 테마/키워드 그리고 맥락을 함께" — spec_양식작성 ② §5-2)
            t0 = page.evaluate(TOP)   # 오늘 전에 저장한 검토(topics 없음) — 「0개」 가 아니라 「아직 뽑지 않았습니다」
            check("④-2 옛 검토(topics 없음) — 「아직 뽑지 않았습니다」(0개라고 하지 않는다)", bool(t0) and t0["msg"] == "아직 뽑지 않았습니다 — 「다시 검토」 로 뽑습니다" and not t0["rows"] and "0개" not in t0["title"] and t0["help"], t0)
            fr.update(review={**rv, "topics": TOPICS}, topicLines=TOPIC_LINES, lost=[])
            page.evaluate("() => { window.__clip = []; navigator.clipboard.writeText = async (t) => { window.__clip.push(t); }; return fwRead(true).then(fwRedraw); }")
            page.wait_for_selector("#headsDlgBody .fw-topics .fw-top", timeout=10000)
            t1 = page.evaluate(TOP)
            check("④-2 테마 줄 — 테마 · 키워드 · 맥락 · 처음에는 고른 것 없음 · 「고른 것 복사」 꺼짐 · 「문서 라이브러리 열기」", len(t1["rows"]) == 10 and t1["rows"][0]["name"] == "테마 1" and t1["rows"][0]["kws"] == ["개발 목표", "세부 목표"]
                  and "개조식" in t1["rows"][0]["ctx"] and not any(r["on"] for r in t1["rows"]) and t1["copy"] == ["고른 것 복사", True] and t1["lib"] == ["문서 라이브러리 열기", False] and "10개" in t1["title"] and not t1["over"], t1)
            page.evaluate("() => { const c = document.querySelectorAll('#headsDlgBody .fw-top > input'); c[0].click(); c[1].click(); }")
            t2 = page.evaluate(TOP)
            page.fill("#headsDlgBody .fw-top-lead", "한국선급,  2차년도")
            t3 = page.evaluate(TOP)
            page.click("#headsDlgBody .fw-top-copy")
            page.wait_for_function("() => window.__clip.length === 1", timeout=5000)
            clip = page.evaluate("() => window.__clip[0]")
            check("④-2 앞말이 미리보기를 바꾸고 · 「고른 것 복사 (2)」 = 미리보기 그대로(줄마다 범위 하나)", t2["prev"] == ["범위 1 (개발 목표 · 세부 목표)", "범위 2 (개발 목표 · 세부 목표)"] and t2["copy"] == ["고른 것 복사 (2)", False]
                  and t3["prev"] == ["한국선급, 2차년도, 범위 1 (개발 목표 · 세부 목표)", "한국선급, 2차년도, 범위 2 (개발 목표 · 세부 목표)"] and clip == "\n".join(t3["prev"]), (t2, t3, clip))
            page.evaluate("() => { const c = document.querySelectorAll('#headsDlgBody .fw-top > input'); for (let i = 2; i < 8; i++) c[i].click(); c[8].click(); }")   # 8개까지 — 9번째는 못 고른다
            t4 = page.evaluate(TOP)
            page.evaluate("() => { const c = document.querySelectorAll('#headsDlgBody .fw-top > input'); c[7].click(); c[9].click(); }")   # 8번째를 풀고 10번째(앞말을 붙이면 600자를 넘는 줄)를 고른다
            t5 = page.evaluate(TOP)
            page.evaluate("() => [...document.querySelectorAll('#headsDlgBody .fw-top')][2].querySelector('.fw-top-one').click()")   # 줄마다의 「복사」
            page.wait_for_function("() => window.__clip.length === 2", timeout=5000)
            check("④-2 9번째는 못 고름(8개까지) · 600자를 넘는 줄은 복사에서 빠짐 · 줄마다 「복사」", t4["on"] == 8 and not t4["rows"][8]["on"] and t4["copy"][0] == "고른 것 복사 (8)"
                  and t5["on"] == 8 and t5["rows"][9]["on"] and t5["rows"][9]["long"] and len(t5["prev"]) == 7 and t5["copy"][0] == "고른 것 복사 (7)"
                  and page.evaluate("() => window.__clip[1]") == "한국선급, 2차년도, 범위 3 (개발 목표 · 세부 목표)" and not t5["over"], (t4["on"], t5))
            page.locator("#headsDlg").screenshot(path=str(OUT / "04c_topics.png"))
            page.evaluate("() => { document.activeElement && document.activeElement.blur(); FW.at = Date.now(); }")
            dl = page.evaluate(LIVE)
            check("④-2 대시보드 — 「양식 검토 · 찾을 테마」 끝남(찾을 테마 10개) · 「테마 · 키워드 보기」(작성 지침 확인 줄에도) · 「작성 계획 · 확인할 것」 끝남", dl["review"]["state"] == "done" and "찾을 테마 10개" in dl["review"]["text"]
                  and dl["review"]["acts"] == [["테마 · 키워드 보기", False]] and [a[0] for a in dl["guides"]["acts"]] == ["지침 작성 열기", "테마 · 키워드 보기"]
                  and dl["plan"]["state"] == "done" and "확인할 것 1개 모두 답함" in dl["plan"]["text"], {k: dl[k] for k in ("guides", "review", "plan")})
            for i in range(3):
                page.click(f"#headsDlgBody .fw-place:nth-of-type({i + 1}) > input") if False else page.evaluate("(i) => document.querySelectorAll('#headsDlgBody .fw-place > input')[i].click()", i)
            page.fill("#headsDlgBody .fw-note", "개조식으로 3줄")
            page.evaluate("() => document.activeElement && document.activeElement.blur()")
            foot = page.evaluate(FOOT)
            check("⑤ 자리를 고르면 「작성 초안 받기 (3곳)」", foot["btns"][-1][0] == "작성 초안 받기 (3곳)" and not foot["btns"][-1][1] and "초안" in foot["btns"][-1][2], foot)
            page.once("dialog", lambda dlg: dlg.accept())
            page.click("#headsDlgFoot button.primary")
            page.wait_for_function("() => /마지막 실행 — 초안 2개 · 제안 카드에서 보기 · 자료에 해당 내용 없음 1곳 · 실패 1곳/.test(document.getElementById('headsDlgFoot').textContent)", timeout=20000)
            check("⑤ 실행 요청의 본문 {places, materials, note, chunks}", len(sent) == 1 and len(sent[0]["places"]) == 3 and sent[0]["materials"] == [mats[0]["id"]] and sent[0]["note"] == "개조식으로 3줄" and sent[0]["chunks"] == {}, sent)
            tags = [p["tags"] for p in page.evaluate(PLACES)[:3]]
            check("⑤ 끝나면 자리마다 결과 꼬리표", "초안 2" in tags[0] and "자료에 없음" in tags[1] and "실패" in tags[2], tags)
            page.screenshot(path=str(OUT / "05_ran.png"))
            # ⑤ 초안 0개의 까닭 · 반영 수는 이번 실행의 턴만(astra — 「자료에 없음」 으로 뭉뚱그리지 않는다 · 전에 따로 반영한 카드를 세지 않는다)
            zero = page.evaluate("""async () => { const keep = FW.gw.run, turns = AGENT.turns; FW.at = Date.now();
              FW.gw.run = { id: 'r0', state: 'done', items: [{ id: 'a', state: 'none', why: 'noaction', proposals: 0 }, { id: 'b', state: 'none', why: 'dropped', proposals: 0 }, { id: 'c', state: 'none', why: 'noslot', proposals: 0 },
                { id: 'd', state: 'none', why: 'filled', proposals: 0 }, { id: 'e', state: 'failed', proposals: 0 }] };
              const L = await formWriteLive(), ask = { state: L.steps.ask.state, text: L.steps.ask.text }, apply = L.steps.apply.state;
              AGENT.turns = [{ id: 't1', text: '[지침 작성] 가', proposals: [{ state: 'applied' }, { state: 'open' }] }, { id: 'old', text: '다른 요청', proposals: [{ state: 'applied' }, { state: 'applied' }] }];
              const n = [fwAppliedN({ items: [{ turn: 't1' }] }), fwAppliedN({ items: [{ turn: 'zz' }] }), fwAppliedN(null)];
              FW.gw.run = keep; AGENT.turns = turns; return { ask, apply, n }; }""")
            check("⑤ 초안 0개 — 끝남이 아니고 까닭을 가른다(자료에 해당 내용 없음 · 검사에서 제외 · 쓸 자리를 고르지 않음 · 이미 채운 줄 · 실패)", zero["ask"]["state"] != "done" and "초안 0개" in zero["ask"]["text"]
                  and all(w in zero["ask"]["text"] for w in ("자료에 해당 내용 없음 1곳", "검사에서 제외 1곳", "쓸 자리를 고르지 않음 1곳", "이미 채운 줄 1곳", "실패 1곳")) and zero["apply"] == "todo", zero)
            check("⑤ 반영한 초안 수 — 이번 실행의 턴만(실행 기록이 없으면 지침 작성이 낸 턴만)", zero["n"] == [1, 0, 1], zero["n"])
            # ⑤-1 상자 자리의 「쓸 자리 고르기」(spec_양식작성 ② §5-3 — 자리 목록 응답에 상자 자리를 끼움)
            phase["box"] = True
            page.evaluate("() => { FW.picks.clear(); return fwRead(true).then(fwRedraw); }")
            page.wait_for_selector("#headsDlgBody .fw-place.is-box", timeout=10000)
            b0, ps2 = page.evaluate(BOX), page.evaluate(PLACES)
            tagsOf = {p["name"]: p["tags"] for p in ps2[:5]}
            check("⑤-1 상자 자리 · 줄 자리의 꼬리표 — 상자 · 쓸 자리 3 / 같은 줄 뒤에 씀 / 표시 줄 / 채움 / 아래 상자는 따로", b0["tags"][:2] == ["상자", "쓸 자리 3"] and not b0["on"] and not b0["open"]
                  and "같은 줄 뒤에 씀" in tagsOf["■ 연구개발과제명 :"] and "표시 줄" in tagsOf["■ 작성 기준 보고서 ( □ 연차 □ 최종 )"] and "채움" in tagsOf["■ 주관연구개발기관 : 가나다"] and "아래 상자는 따로" in tagsOf["■ 성과목표 관리"], (b0, tagsOf))
            page.click("#headsDlgBody .fw-places-head button:has-text('모두 고르기')")
            allp = {p["name"]: p["on"] for p in page.evaluate(PLACES)}
            check("⑤-1 「모두 고르기」 — 채운 줄은 빼고", allp["■ 연구개발과제명 :"] and allp["< 연구개발 과제명 작성 >"] and not allp["■ 주관연구개발기관 : 가나다"], allp)
            page.click("#headsDlgBody .fw-places-head button:has-text('모두 해제')")
            page.click("#headsDlgBody .fw-place.is-box > input")
            page.wait_for_function("() => { const d = document.querySelector('#headsDlgBody .fw-place.is-box .fw-chunks'); return d && d.open; }", timeout=10000)
            b1 = page.evaluate(BOX)
            page.evaluate("() => document.querySelectorAll('#headsDlgBody .fw-place.is-box .fw-chunk input')[1].click()")
            b2 = page.evaluate(BOX)
            page.evaluate("() => document.querySelectorAll('#headsDlgBody .fw-place.is-box .fw-chunk input')[2].click()")
            b3 = page.evaluate(BOX)
            check("⑤-1 쓸 자리 고르기 — 상자를 고르면 펴짐 · 같은 이름이 하나뿐인 자리만 처음부터 고름 · 같은 이름은 하나만(다른 것을 켜면 앞의 것이 꺼짐)", b1["on"] and b1["open"] and [c["on"] for c in b1["chunks"]] == [True, False, False]
                  and "추진 내용 작성" in b1["chunks"][0]["text"] and "줄 5" in b1["chunks"][0]["text"] and "추진 내용 작성 › 공동(기업명 작성) :" in b1["chunks"][1]["text"] and "같은 이름 2곳 — 하나를 고릅니다(위에서 1번째)" in b1["chunks"][1]["text"]
                  and [c["on"] for c in b2["chunks"]] == [True, True, False] and [c["on"] for c in b3["chunks"]] == [True, False, True] and "3곳 가운데 2곳" in b3["sum"]
                  and not page.evaluate(COL)["over"], (b1, b2, b3))
            page.locator("#headsDlg").screenshot(path=str(OUT / "05b_box.png"))
            phase.update(run=None, n=0)
            page.once("dialog", lambda dlg: dlg.accept())
            page.click("#headsDlgFoot button.primary")
            page.wait_for_function("() => FW.gw && FW.gw.run && FW.gw.run.id === 'r2' && FW.gw.run.state === 'done' && /마지막 실행 — 초안 2개/.test(document.getElementById('headsDlgFoot').textContent)", timeout=20000)
            check("⑤-1 실행 요청의 chunks — 고른 상자의 고른 쓸 자리(같은 이름은 고른 하나)", len(sent) == 2 and sent[1]["places"] == ["tBOX"] and sent[1]["chunks"] == {"tBOX": ["c1", "c3"]}, sent[1:])
            phase["box"] = False
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
            # ⑧′ 단계 초기화(2026-11-24 사용자 "준비/자료,작성 단계를 따로 두고 단계별로 … 초기화" — spec_양식작성 ② §6-1): 묶음 머리마다 「초기화…」 → 그 아래 확인 줄 → 그 단계의 것만 비운다
            page.evaluate("() => { if (typeof headsColClose === 'function') headsColClose(); showTab('Dash'); }")
            page.wait_for_selector('#paneDash [data-dash-focus="fwreset:write"]:not([disabled])', timeout=60000)
            RS = """() => { const b = document.querySelector('#paneDash .dash-reset[data-fw-reset]');
              return { heads: [...document.querySelectorAll('#paneDash .dash-ghead [data-dash-focus^="fwreset:"]')].map((x) => [x.dataset.dashFocus, x.textContent]),
                box: b ? { st: b.dataset.fwReset, head: b.querySelector('.dash-reset-head').textContent, help: !!b.querySelector('.dash-reset-head .panel-help'), under: b.closest('.dash-group').dataset.group,
                  acts: [...b.querySelectorAll('.dash-reset-acts button')].map((x) => [x.dataset.dashFocus, x.textContent, x.disabled]) } : null, tool: document.getElementById('panel').dataset.tool }; }"""
            mats_n = lambda: len(requests.get(f"{base}/api/docs/{doc}/agent", timeout=60).json()["materials"])  # noqa: E731
            page.locator('#paneDash [data-dash-focus="fwreset:write"]').click()
            page.wait_for_selector('#paneDash .dash-reset[data-fw-reset=write]', timeout=20000)
            r1 = page.evaluate(RS)
            check("⑧′ 묶음 머리마다 「초기화…」 · 「작성」 을 누르면 그 묶음 아래에 확인 줄(무엇을 비우는지 · 노트 아이콘 · 「작성 초기화」 · 「취소」) — 누르기 전에는 안 바뀜",
                  r1["heads"] == [["fwreset:open", "초기화…"], ["fwreset:material", "초기화…"], ["fwreset:write", "초기화…"]] and r1["box"] and r1["box"]["under"] == "write" and r1["box"]["help"]
                  and r1["box"]["head"].startswith("작성 초기화 — ") and "올린 원본" in r1["box"]["head"] and r1["box"]["acts"] == [["fwreset:write:go", "작성 초기화", False], ["fwreset:close", "취소", False]] and mats_n() == 1, r1)
            page.locator("#paneDash").screenshot(path=str(OUT / "08a_stage_reset.png"))
            page.locator('#paneDash [data-dash-focus="fwreset:close"]').click()
            page.wait_for_function("() => !document.querySelector('#paneDash .dash-reset[data-fw-reset]')", timeout=20000)
            page.locator('#paneDash [data-dash-focus="fwreset:write"]').click()
            page.locator('#paneDash [data-dash-focus="fwreset:write:go"]').click()
            page.wait_for_function("() => /작성을 초기화했습니다/.test(document.getElementById('toast').textContent) && !document.querySelector('#paneDash .dash-reset[data-fw-reset]')", timeout=120000)
            r2 = page.evaluate(RS)
            check("⑧′ 「작성 초기화」 — 초안 · 작성 계획만 비우고 대시보드에 머묾 · 자료는 그대로", r2["tool"] == "Dash" and mats_n() == 1 and not requests.get(f"{base}/api/docs/{doc}/agent", timeout=60).json()["turns"], r2)
            page.wait_for_selector('#paneDash [data-dash-focus="fwreset:open"]:not([disabled])', timeout=60000)
            page.locator('#paneDash [data-dash-focus="fwreset:open"]').click()
            page.wait_for_selector('#paneDash .dash-reset[data-fw-reset=open]', timeout=20000)
            r3 = page.evaluate(RS)
            page.locator('#paneDash [data-dash-focus="fwreset:open:go"]').click()
            page.wait_for_function("() => /작업 내용을 초기화했습니다 — 준비/.test(document.getElementById('toast').textContent) && !!document.querySelector('#doc .para')", timeout=120000)
            check("⑧′ 「준비」 — 「준비 초기화」 · 「모두 초기화(자료도)」 · 「취소」 · 준비 초기화는 올린 직후로 되돌리되 이 문서의 자료는 남긴다",
                  r3["box"] and r3["box"]["under"] == "open" and [a[:2] for a in r3["box"]["acts"]] == [["fwreset:open:go", "준비 초기화"], ["fwreset:all:go", "모두 초기화(자료도)"], ["fwreset:close", "취소"]] and mats_n() == 1, r3)
            page.wait_for_selector('#paneDash [data-dash-focus="fwreset:material"]:not([disabled])', timeout=120000)   # 다시 연 뒤의 첫 분석이 끝난 뒤
            page.locator('#paneDash [data-dash-focus="fwreset:material"]').click()
            page.locator('#paneDash [data-dash-focus="fwreset:material:go"]').click()
            page.wait_for_function("() => /자료 준비를 초기화했습니다/.test(document.getElementById('toast').textContent)", timeout=60000)
            page.wait_for_function("() => (document.querySelector('#paneDash .dash-node[data-key=take]') || { dataset: {} }).dataset.state !== 'done'", timeout=30000)
            check("⑧′ 「자료 준비 초기화」 — 이 문서의 자료만 비운다(대시보드의 「자료 가져오기」 가 끝남에서 내려옴)", mats_n() == 0 and page.evaluate(RS)["tool"] == "Dash", page.evaluate(DASH)["nodes"].get("take"))
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

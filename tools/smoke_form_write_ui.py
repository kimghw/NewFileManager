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
       "NFM_AGENT_NOTES": str(tmp / "agent_notes.json"), "NFM_TOOL_NAMES": str(tmp / "tool_names.json"), "NFM_REQS": str(tmp / "reqs.json"), "NFM_DOCLIB_URL": lib,
       "NFM_FORM_THEMES": str(tmp / "form_themes")}   # 양식 테마의 이 PC 사본(② §5-7) — 혼자 돌릴 때도 사용자의 테마 파일을 읽지 않게
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


def check_guidance_inputs(page, doc):
    """04의 실제 파일 선택·삭제와 수동 실행. 유료 판정의 응답만 흉내 낸다."""
    root = f"{base}/api/docs/{doc}"
    card = page.locator("#paneDash .dash-node[data-key=headsLlm]")
    name = "작성 예시.md"
    def open_step():
        if card.locator(".dash-node-head").get_attribute("aria-expanded") != "true":
            card.locator(".dash-node-head").click()

    open_step()
    with page.expect_file_chooser() as chooser:
        card.get_by_role("button", name="샘플·추가 서식 첨부…").click()
    chooser.value.set_files({"name": name, "mimeType": "text/markdown", "buffer": "목표는 수치와 단위를 함께 적는다".encode()})
    remove = card.get_by_role("button", name=f"{name} 빼기")
    run_button = card.locator("button[data-dash-focus='act:headsLlm']")
    remove.wait_for(timeout=30000)
    check("② 04에서 첨부한 샘플은 작성 근거 자료에 섞이지 않는다",
          [f["name"] for f in requests.get(root + "/form-examples", timeout=10).json()["files"]] == [name]
          and not requests.get(root + "/agent", timeout=10).json()["materials"])
    analysis = requests.get(root + "/analysis", timeout=15).json()
    gw = requests.get(root + "/guide-write", timeout=15).json()
    for part in analysis["items"]:
        if part.get("llm"):
            part["llm"]["state"] = "done"
    result, posted = {"ready": False, "run": None}, []
    def start_call(route):
        posted.append(route.request.post_data_json)
        result["run"] = {"state": "running"}
        route.fulfill(status=202, json={"started": time.time(), "status": "running", "stage": 2, "chain": "llm", "steps": []})

    paths = (root + "/analysis", root + "/guide-write", root + "/writing-guidance", root + "/analysis/llm")
    page.route(paths[0], lambda r: r.fulfill(json=analysis))
    page.route(paths[1], lambda r: r.fulfill(json={**gw, "enabled": True, "steps": {k: v for k, v in gw["steps"].items() if k != "guides"}}))
    page.route(paths[2], lambda r: r.fulfill(json=result))
    page.route(paths[3], start_call)
    def refresh():
        page.evaluate("async () => { await FW.loading; await fwRead(true); await dashDraw(true); }")
        open_step()

    def check_criteria(phase):
        before = card.get_attribute("data-state")
        was_locked = remove.is_disabled()
        writes = []
        def watch(req):
            if req.url.startswith((root + "/", base + "/api/agents/")) and req.method not in ("GET", "HEAD", "OPTIONS"):
                writes.append((req.method, req.url))

        page.on("request", watch)
        try:
            with page.expect_response(base + "/api/agents/writing_guidance") as response:
                card.get_by_role("button", name="판단 지침 보기", exact=True).click()
            parts = response.value.json()["prompt"]
            expected = next(p["text"] for p in parts if p["kind"] == "merge" and p["name"] == "writing_guidance")
            contract = next(p["text"] for p in parts if p["kind"] == "contract")
            text = page.locator("#headsDlgBody details[data-part='guide'][open] .lg-text")
            text.wait_for()
            check(f"② 04 {phase}에 판단 지침 원문을 펼쳐 본다",
                  response.value.request.method == "GET" and "각주" in expected and "그림" in expected
                  and text.text_content() == expected and page.locator("#headsDlgBody details[data-part='contract'] .lg-text").text_content() == contract
                  and "아직 실행한 적 없음" not in page.locator("#headsDlgBody").inner_text())
            themes = page.locator("#headsDlgBody .fw-themes details.fw-th")   # 미리 적어 둔 테마(테이블 타입 · 구분 기준 타입 · 템플릿 — ② §5-7): 읽기만(GET)
            themes.first.wait_for(state="attached")
            shown = page.locator("#headsDlgBody .fw-themes").text_content()
            check(f"② 04 {phase}에 판단 지침 열이 미리 적어 둔 테마를 보인다",
                  themes.count() >= 2 and all(w in shown for w in ("연구개발과제", "참여기관", "연구개발계획서 기본", "본문 테이블", "헤딩 테이블", "그림 테이블", "YAML 고치기")), shown[:200])
            if phase == "실행 중":
                page.screenshot(path=str(OUT / "02b_04_review_guide.png"))
            page.locator("#headsDlgClose").click()
            page.locator("#headsDlg").wait_for(state="hidden")
            open_step()
            check(f"② 04 {phase}에 지침을 열고 닫아도 작업 상태와 첨부 잠금이 유지된다",
                  not writes and card.get_attribute("data-state") == before and remove.is_disabled() == was_locked, writes)
        finally:
            page.remove_listener("request", watch)
    try:
        # 이미 마친 구조 판정 + 작업에 새로 올린 서식. 새 04 결과를 받기 전에 끝난 것으로 세지 않는다.
        page.evaluate("(v) => { dsState.main = v; }", analysis)
        refresh()
        check("② 04 구조 검증을 마쳐도 자리별 지침을 기다린다", card.get_attribute("data-state") != "done")
        check_criteria("실행 전")
        with page.expect_request(paths[3]):
            run_button.click()
        refresh()
        check("② 수동 04가 지침 추출을 요청하고 도는 동안 첨부를 잠근다",
              bool(posted) and posted[0].get("writingGuidance") is True and card.get_attribute("data-state") == "run" and remove.is_disabled())
        check_criteria("실행 중")
        result["run"] = {"state": "failed", "error": "샘플 판독 실패"}
        refresh()
        check("② 04 판독 실패가 보이고 다시 실행할 수 있다",
              card.get_attribute("data-state") != "done" and "샘플 판독 실패" in card.inner_text()
              and run_button.is_enabled())
        result.update(ready=True, audited=True, count=2, placeCount=4, judgmentCounts={"apply": 2, "not_applicable": 1, "insufficient": 1},
                      images=1, cut=True, sources=["목적 양식", name], run={"state": "done"})
        refresh()
        shown = card.inner_text()
        check("② 04 완료 후 실제 입력·그림 수·축약 범위와 결과가 보인다",
              card.get_attribute("data-state") == "done" and "4곳을 판정" in shown and "지침 적용 2곳" in shown and "근거 부족 1곳" in shown and "그림 1장" in shown
              and "목적 양식" in shown and name in shown and "일부 입력" in shown)
        check_criteria("완료 후")
        steps = page.evaluate(DASH)["nodes"]
        guide_actions = page.evaluate("async () => (await formWriteLive()).steps.guides.acts.map(b => b.textContent)")
        check("② 04 판정 후 05를 승인하지 않아도 06으로 진행한다",
              steps["guides"]["state"] == "done" and steps["review"]["state"] == "now"
              and "작성 지침 보기 · 적기" in guide_actions and "확인함" not in guide_actions)
    finally:
        for path in paths:
            page.unroute(path)
        refresh()
    remove.click()
    remove.wait_for(state="detached", timeout=30000)
    page.wait_for_function("() => !FW.changingExamples && !FW.examples.length", timeout=30000)
    check("② 04에서 참고 서식을 뺄 수 있다", requests.get(root + "/form-examples", timeout=10).json()["files"] == [])


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
            # 선택 줄도 차례에(2026-11-24 사용자 「3,4번이 지나가지 않았는데 왜 5로 오냐 순서가 안맞음」 — spec_양식작성 ② §6 「선택 줄도 차례에」)
            check("② 선택 줄 03 LLM 검증·보완 — LLM 을 쓸 수 없으면 저절로 건너뜀", n["headsLlm"]["state"] == "done" and "건너뜁니다" in n["headsLlm"]["text"], n["headsLlm"])
            nows = [k for k, x in d["nodes"].items() if x["state"] == "now"]
            check("② 선택 줄 04 「작성 지침 확인 · 적기」 가 지금 — 누르기 전에는 05 로 건너뛰지 않는다", nows == ["guides"] and d["nodes"]["review"]["state"] == "ready"
                  and "확인함" in d["nodes"]["guides"]["text"] and "건너뛰기" in d["nodes"]["guides"]["text"], {k: x["state"] for k, x in d["nodes"].items()})
            page.click("#paneDash .dash-node[data-key=guides] button:has-text('건너뛰기')")
            page.wait_for_selector("#paneDash .dash-node[data-key=guides][data-state=done]", timeout=15000)
            st = requests.get(f"{base}/api/docs/{doc}/guide-write", timeout=30).json().get("steps")
            check("② 04 「건너뛰기」 — 작업 폴더에 표시가 남고 「건너뜀」", st == {"guides": "skip"} and "건너뜀" in page.evaluate(DASH)["nodes"]["guides"]["text"], st)
            d, n = page.evaluate(DASH), page.evaluate(LIVE)
            check("② 지금 차례의 카드가 펴져 그 글과 단추를 보인다(양식 검토 — 자료 준비 앞)", d["nodes"]["review"]["state"] == "now" and "아직 검토하지 않았습니다" in d["nodes"]["review"]["text"] and "양식 검토 · 찾을 테마" in d["nodes"]["review"]["text"], d["nodes"]["review"])
            nows = [k for k, x in d["nodes"].items() if x["state"] == "now"]
            check("② 「지금」 은 한 줄(차례상 첫 줄) — 뒤의 할 수 있는 줄은 「할 수 있음」", nows == ["review"] and d["nodes"]["take"]["state"] == "ready" and set(d["nodes"]) >= {"guides", "review", "plan", "ask", "apply"}, {k: x["state"] for k, x in d["nodes"].items()})
            fr0 = page.evaluate("() => { const g = FW.gen || 0; document.dispatchEvent(new CustomEvent('nfm:work-reset', { detail: { id: state.id } })); return { key: FW.key, gen: FW.gen, was: g }; }")
            check("② 작업 내용 초기화(nfm:work-reset) — 그 문서의 기억을 버린다", fr0["key"] == "" and fr0["gen"] == fr0["was"] + 1, fr0)
            page.evaluate("() => fwRead(true)")
            # 07 · 08 은 이 프로젝트에 고른 참조 문서로 센다(2026-11-26 사용자 「있는 추출할때 전부 참조할 수 있지만 사용자가 선택한 문서만 사용할 수 있게 해줘」) — 라이브러리에 문서 · 추출이 있어도 고르기 전에는 끝남이 아니다
            check("② 참조 문서를 고르기 전 — 라이브러리에 있어도 07 · 08 은 끝남이 아니다 · 「참조 문서 고르기」", n["keep"]["state"] != "done" and "이 프로젝트에 고른 참조 문서가 없습니다" in n["keep"]["text"] and "라이브러리 1개" in n["keep"]["text"]
                  and ["참조 문서 고르기", False] in n["keep"]["acts"] and n["extract"]["state"] == "todo" and "먼저 이 프로젝트의 참조 문서를 고릅니다" in n["extract"]["text"], {k: n[k] for k in ("keep", "extract")})
            check("② 자료 없음 · 검토 전 → 「양식 검토 · 찾을 테마」 가 지금 차례(자료 없이 된다) · 자료 가져오기는 할 수 있음 · 작성 계획은 아직", n["review"]["state"] == "now" and n["review"]["acts"] == [["양식 검토", False]]
                  and n["take"]["state"] == "ready" and "자료가 없습니다" in n["take"]["text"] and n["plan"]["state"] == "todo" and n["ask"]["state"] == "todo", {k: n[k] for k in ("review", "take", "plan", "ask")})
            # ② 「1 준비」 의 「헤딩 · 표 분석 · 작성 지침」(2026-11-24 사용자 "1준비에 있어야지" · "테이블이나 본문이 지침을 가지고 와야지") — 분석이 끝나면 작성 지침을 저장하고 그 수를 보인다
            page.wait_for_function("async () => { if (typeof docStatusPing === 'function') docStatusPing(); FW.at = 0; const r = await formWriteLive(); return r.steps.heads.state === 'done'; }", timeout=180000, polling=2000)
            n = page.evaluate(LIVE)
            fg = requests.get(f"{base}/api/docs/{doc}/form-guides", timeout=30).json()
            check("② 준비 — 헤딩 · 표 분석 끝남 · 작성 지침을 저장하고 수를 보인다", n["heads"]["state"] == "done" and "헤딩 그래프·표 구조: 양식 있음" in n["heads"]["text"] and "작성 지침" in n["heads"]["text"] and fg["saved"] is not None,
                  {"heads": n["heads"], "saved": (fg["saved"] or {}).get("counts")})
            check("② 준비 — LLM 검증·보완은 선택 줄(사람이 누를 때만 돈다 · LLM 이 꺼져 있으면 건너뜀)", "headsLlm" in n and n["headsLlm"]["state"] == "done", n.get("headsLlm"))
            page.screenshot(path=str(OUT / "02_dash.png"))
            check_guidance_inputs(page, doc)
            # ② 「문서 올리기 · 첫 분석」 — 접어도 보이는 줄(참조 문서 수 + 「참조 문서 목록」) → 2열 「참조 문서」(2026-11-26 사용자 「참고 문서 갯수를 상단에 표기 … 참고문헌 리스트만 왼쪽열에서」)
            al = page.evaluate("() => { const b = document.querySelector('#paneDash .dash-node[data-key=open] .dash-always'); return b ? { text: b.textContent, btns: [...b.querySelectorAll('button')].map((x) => x.textContent) } : null; }")
            check("② 문서 올리기 카드 — 접어도 참조 문서 수(이 프로젝트 · 라이브러리) · 「참조 문서 목록」", bool(al) and "이 프로젝트의 참조 문서 0개 · 라이브러리 1개" in al["text"] and al["btns"] == ["참조 문서 목록"], al)
            page.click("#paneDash .dash-node[data-key=open] .dash-always button")
            page.wait_for_selector("#headsDlgBody .fw-ref-tabs", timeout=15000)
            RC = "() => ({ kind: document.querySelector('#headsDlg').dataset.kind, tabs: [...document.querySelectorAll('#headsDlgBody .fw-ref-tabs .fw-tab')].map((b) => [b.dataset.tab, b.textContent, b.classList.contains('is-on')]), rows: [...document.querySelectorAll('#headsDlgBody .fw-ref')].map((r) => r.textContent) })"
            rc = page.evaluate(RC)
            check("② 2열 「참조 문서」 — 탭 「이 프로젝트」(처음 · 비었음) | 「문서 라이브러리」", rc["kind"] == "fwRefs" and rc["tabs"] == [["project", "이 프로젝트 (0)", True], ["lib", "문서 라이브러리 (1)", False]] and not rc["rows"], rc)
            # 고르지 않은 문서의 추출은 서버도 막는다(양식 작성 — 409)
            r409 = requests.post(f"{base}/api/docs/{doc}/agent/material/library", json={"extract": eid}, timeout=30)
            check("② 고르지 않은 문서의 추출을 자료로 — 409", r409.status_code == 409 and "참조 문서가 아닙니다" in r409.text, (r409.status_code, r409.text[:200]))
            page.click("#headsDlgBody .fw-ref-tabs .fw-tab[data-tab=lib]")
            page.wait_for_selector("#headsDlgBody .fw-ref .fw-ref-pick", timeout=15000)
            rc = page.evaluate(RC)
            check("② 「문서 라이브러리」 탭 — 모든 문서 · 「이 프로젝트에 넣기」", len(rc["rows"]) == 1 and "추출 1개" in rc["rows"][0] and "이 프로젝트에 넣기" in rc["rows"][0], rc)
            page.click("#headsDlgBody .fw-ref .fw-ref-pick")
            page.wait_for_function("() => /넣음/.test(document.querySelector('#headsDlgBody .fw-ref .fw-ref-pick')?.textContent || '')", timeout=15000)
            refs = requests.get(f"{base}/api/docs/{doc}/guide-write", timeout=30).json()["refs"]
            check("② 넣으면 프로젝트 기록에 남는다", refs["only"] and len(refs["docs"]) == 1, refs)
            page.click("#headsDlgBody .fw-ref-tabs .fw-tab[data-tab=project]")
            page.wait_for_function("() => document.querySelectorAll('#headsDlgBody .fw-ref').length === 1", timeout=15000)
            n = page.evaluate(LIVE)
            check("② 고른 뒤 — 07 · 08 끝남(이 프로젝트의 참조 문서 · 끝난 추출)", n["keep"]["state"] == "done" and "이 프로젝트의 참조 문서 1개" in n["keep"]["text"] and n["extract"]["state"] == "done", {k: n[k] for k in ("keep", "extract")})
            page.screenshot(path=str(OUT / "02b_refs.png"))
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
            # 탭(2026-11-26 사용자 「각 도구가 뭘 정확히 어딜 선택하라는건지 알 수가 없어. 탭으로 분리해서」) — 대시보드 단계마다 하나 · 처음 = 지금 할 탭(검토 전 = 양식 검토) · 탭마다 「이 탭에서 할 일」
            t0 = page.evaluate("""() => ({ tab: FW.wTab, tabs: [...document.querySelectorAll('#headsDlgBody .fw-w-tabs .fw-w-tab')].map((b) => b.dataset.tab), on: (document.querySelector('#headsDlgBody .fw-w-tab.is-on') || {}).dataset?.tab,
              todo: [...document.querySelectorAll('#headsDlgBody > .fw-todo .fw-todo-t')].map((x) => x.textContent), now: (document.querySelector('#headsDlgBody .fw-todo-i.is-now .fw-todo-t') || {}).textContent || '',
              foot: document.getElementById('headsDlgFoot').textContent, btns: document.querySelectorAll('#headsDlgFoot button').length })""")
            check("④ 탭 — 작성 지침 · 양식 검토 · 찾을 테마 · 작성 계획 · 초안 작성 · 처음 = 양식 검토 · 할 일(지금 = 「양식 검토」 누르기) · 발치에 초안 단추 없음",
                  t0["tabs"] == ["guides", "review", "topics", "plan", "write"] and t0["tab"] == t0["on"] == "review" and t0["now"] == "「양식 검토」 누르기" and t0["btns"] == 0 and "초안 작성」 탭에서" in t0["foot"], t0)
            WHERE = "() => [...document.querySelectorAll('#headsDlgBody .fw-where-tag')].map((t) => [t.dataset.where, t.textContent])"
            page.evaluate("() => fwWTabGo('plan')")
            mat = page.evaluate("() => [...document.querySelectorAll('#headsDlgBody .fw-mats .fw-mat')].map((l) => [l.textContent, l.querySelector('input').checked])")
            wh = page.evaluate(WHERE)
            page.evaluate("() => fwWTabGo('write')")
            c, ps, foot = page.evaluate(COL), page.evaluate(PLACES), page.evaluate(FOOT)
            check("④ 2열 「지침 작성」 — 쓸 자료가 고른 채로(작성 계획 탭)", c["kind"] == "fwWrite" and not c["over"] and len(mat) == 1 and mat[0][1] and "연차보고서_견본" in mat[0][0], (c, mat))
            check("④ 작성 지침이 있는 자리만(기본) — 자리마다 지침", len(ps) >= 3 and all(any(t.startswith("지침") for t in p["tags"]) and p["guides"] >= 1 for p in ps), ps[:6])
            check("④ LLM 꺼짐 — 「작성 초안 받기」 꺼짐 + 까닭", foot["btns"][-1][0] == "작성 초안 받기" and foot["btns"][-1][1] and foot["btns"][-1][2] == "LLM 을 쓸 수 없습니다", foot)
            # 절의 단계 꼬리표(2026-11-24 사용자 「어떤 것의 결과다. 준비다 이런게 있어야」) — 번호는 대시보드와 같은 셈(등록부 차례)
            wh2 = page.evaluate(WHERE)   # 초안 작성 탭 — 「이번 작성의 지침」 · 「채울 자리」 둘 다 11 의 준비
            whs = dict(wh + wh2)
            check("④ 절마다 단계 꼬리표 — 결과 09 자료 가져오기(작성 계획 탭) · 준비 11 양식 초안 작성(초안 작성 탭 둘)", whs.get("result:take", "").startswith("결과09 ") and "자료 가져오기" in whs.get("result:take", "")
                  and whs.get("prep:ask", "").startswith("준비11 ") and [k for k, _ in wh2].count("prep:ask") == 2 and not c["over"], (wh, wh2))
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
            fr, put, posted = {"review": None, "planned": False, "decided": [], "open": [], "stale": False, "run": None, "hwpx": True, "enabled": True}, [], []

            def frh(route):
                req = route.request
                if req.method == "POST":
                    posted.append(json.loads(req.post_data))
                    return route.fulfill(json={"run": None})
                if req.method == "PUT":
                    put.append(json.loads(req.post_data))
                    fr.update(decided=[{"key": "q1", "q": rv["questions"][0]["text"], "a": put[-1]["answers"][0]["a"], "places": [], "at": 0}], open=[])
                return route.fulfill(json=fr)
            page.route(FR, frh)
            page.route(GW, gw)   # 정규식으로 — 글롭 「**/guide-write**」 는 아래 길(/run · /stop)을 못 잡는다
            page.evaluate("() => fwRead(true).then(fwRedraw)")
            page.wait_for_function("() => { const b = [...document.querySelectorAll('#headsDlgFoot button')].pop(); return b && b.disabled && b.title === '먼저 「양식 검토」 를 하세요'; }", timeout=10000)
            # 2026-11-25 사용자 「양식검토만 하는데 왜 다른걸 돌려」 — 양식 검토(06) · 작성 계획(10)은 따로 선 절 · 단추 · 절 차례 = 대시보드 차례(spec_양식작성 ② §5-1 「① ② 를 뗀다」)
            # 탭마다의 절 — 양식 검토 탭 = 요청 · 06 / 작성 계획 탭 = 자료 · 10 / 초안 작성 탭 = 요청 · 자리
            b0 = page.evaluate("""() => { const order = () => [...document.querySelectorAll('#headsDlgBody > section')].map((s) => s.classList.contains('fw-review-sec') ? 'review' : s.classList.contains('fw-plan-sec') ? 'plan' : s.querySelector('.fw-note') ? 'note' : s.querySelector('.fw-mats') ? 'mats' : s.classList.contains('fw-places-sec') ? 'places' : 'other').filter((o) => o !== 'other'), o = {};
              fwWTabGo('review'); o.rev = [...document.querySelectorAll('#headsDlgBody .fw-review-sec button')].map((b) => b.textContent); o.review = order();
              fwWTabGo('plan'); o.plan = [...document.querySelectorAll('#headsDlgBody .fw-plan-sec .fw-places-head button')].map((b) => [b.textContent, b.disabled, b.title]); o.planOrder = order();
              fwWTabGo('write'); o.write = order(); return o; }""")
            check("④-1 검토 전 — 「양식 검토」 절의 단추는 「양식 검토」 하나 · 「작성 계획 세우기」 는 따로 선 탭에서 꺼짐(양식 검토가 먼저) · 탭마다 그 단계의 절만",
                  b0["rev"] == ["양식 검토"] and b0["plan"] and b0["plan"][0][0] == "작성 계획 세우기" and b0["plan"][0][1] and "양식 검토" in b0["plan"][0][2]
                  and b0["review"] == ["note", "review"] and b0["planOrder"] == ["mats", "plan"] and b0["write"] == ["note", "places"], b0)
            # 양식만 검토한 상태(자료 없이) — 보는 셋 · 검토가 본 것 · 작성 방향은 보이고, 「작성 계획 세우기」 가 다음 · 「제안 받기」 는 아직 꺼짐
            only = {**rv, "materials": [], "places": {pid: {"how": "개조식 3줄", "needs": "목표 수치", "use": "", "gap": ""}}, "questions": [{**rv["questions"][0], "suggest": "", "source": ""}],
                    "sees": {"write": "자리 6곳에 개발 목표를 씀", "guides": "작성 요령: 개조식", "asks": "한국선급 몫만"}, "fed": {"places": 6, "formGuides": 2, "userGuides": 1, "request": True}, "request": "한국선급 몫만"}
            fr.update(review=only, open=["q1"])
            page.evaluate("() => fwRead(true).then(fwRedraw)")
            page.wait_for_function("() => { const b = [...document.querySelectorAll('#headsDlgFoot button')].pop(); return b && b.disabled && b.title === '자료를 고르고 「작성 계획 세우기」 를 하세요'; }", timeout=10000)
            st = page.evaluate("""() => { const o = { how: [...document.querySelectorAll('#headsDlgBody .fw-how')].map((x) => x.textContent), note: FW.note };
              fwWTabGo('review'); o.rev = document.querySelector('#headsDlgBody .fw-review-sec .fw-places-head button').textContent;
              o.sees = [...document.querySelectorAll('#headsDlgBody .fw-review-sec .fw-see')].map((x) => [x.dataset.see, x.querySelector('b').textContent]); o.fed = (document.querySelector('#headsDlgBody .fw-rev-fed') || {}).textContent || '';
              o.tabMark = (document.querySelector('#headsDlgBody .fw-w-tab[data-tab=review] .fw-wt-mark') || {}).textContent || '';
              fwWTabGo('plan'); o.btn = document.querySelector('#headsDlgBody .fw-plan-sec .fw-places-head button').textContent; o.steps = [...document.querySelectorAll('#headsDlgBody .fw-steps .fw-tag')].map((x) => x.textContent);
              o.now = (document.querySelector('#headsDlgBody .fw-todo-i.is-now .fw-todo-t') || {}).textContent || ''; return o; }""")
            check("④-1 양식만 검토 — 보는 셋(무엇을 써야 하나 · 작성 지침 · 사람의 요청) · 검토가 본 것 · 「다시 검토」 · 「작성 계획 세우기」 가 다음 · 작성 방향만 · 요청이 「이번 작성의 지침」 칸에",
                  st["btn"] == "작성 계획 세우기" and st["rev"] == "다시 검토" and st["steps"] == ["양식 검토 ✓", "작성 계획", "확인할 것"] and st["how"] == ["작성 방향: 개조식 3줄"]
                  and st["sees"] == [["write", "무엇을 써야 하나"], ["guides", "작성 지침"], ["asks", "사람의 요청"]] and "작성 지침 3개(양식 2 · 사람 1) · 사람의 요청 있음" in st["fed"]
                  and st["note"] in ("", "한국선급 몫만") and st["tabMark"] == "✓" and st["now"] == "「작성 계획 세우기」 누르기", st)
            # 「다시 검토」 는 자료를 보내지 않는다(고른 자료가 있어도) · 요청은 함께 — 「작성 계획 세우기」 만 자료를 보낸다
            page.evaluate("() => fwWTabGo('review')")
            page.once("dialog", lambda dlg: dlg.accept())
            page.click("#headsDlgBody .fw-review-sec .fw-places-head button")
            page.wait_for_timeout(400)
            page.evaluate("() => fwWTabGo('plan')")
            if page.evaluate("() => FW.gw.materials.length"):
                page.once("dialog", lambda dlg: dlg.accept())
                page.click("#headsDlgBody .fw-plan-sec .fw-places-head button")
                page.wait_for_timeout(400)
            check("④-1 「다시 검토」 POST = materials [] + note · 「작성 계획 세우기」 POST = 고른 자료", bool(posted) and posted[0]["materials"] == [] and "note" in posted[0]
                  and (len(posted) == 1 or (len(posted) == 2 and posted[1]["materials"])), posted)
            page.evaluate("() => fwRead(true).then(fwRedraw)")
            # 자료가 있으면 「작성 계획 세우기」 가 파란 단추 · 「자료 가져오기」 는 보통 단추 / 자료가 0개면 거꾸로(대시보드의 차례와 맞춤 — 2026-11-24 「자료 가져오기, 작성 계획 세우기 매칭이 안됨」)
            NOMAT = "() => { const a = document.querySelector('#headsDlgBody .fw-plan-sec .fw-rev-act'), t = document.querySelector('#headsDlg [data-fw-take]'), m = document.querySelector('#headsDlgBody .fw-plan-sec .fw-rev-msg.is-warn'); return { mats: FW.gw.materials.length, act: [a.disabled, a.classList.contains('primary')], take: t.classList.contains('primary'), msg: m ? m.textContent : '' }; }"
            nm = page.evaluate(NOMAT)
            if nm["mats"]:
                check("④-1 자료 있음 — 「작성 계획 세우기」 파란 단추 · 「자료 가져오기」 보통", nm["act"] == [False, True] and not nm["take"] and "넣을 내용의 자료(MD)를 고르고" in nm["msg"], nm)
                page.evaluate("() => { const g = FW.gw; FW.gw = { ...g, materials: [] }; fwRedraw(); FW.gw = g; }")
                nm = page.evaluate(NOMAT)
            check("④-1 자료 0개 — 「작성 계획 세우기」 꺼짐 · 「자료 가져오기」 파란 단추 · 자료부터 가져오라는 글", nm["act"] == [True, False] and nm["take"] and "먼저 위 「자료 가져오기」" in nm["msg"], nm)
            page.evaluate("() => fwRedraw()")
            # 자료로 작성 계획을 세운 상태 — 자리마다 자료에서 쓸 것 · 자료에 없는 것 + 확인할 것
            fr.update(review=rv, planned=True, open=["q1"])
            page.evaluate("() => { fwWTabGo('write'); return fwRead(true).then(fwRedraw); }")
            page.wait_for_selector("#headsDlgBody .fw-use", timeout=10000)
            foot = page.evaluate(FOOT)
            how = page.evaluate("(id) => [...document.querySelectorAll('#headsDlgBody .fw-how')].map((x) => x.textContent)", pid)
            wt = page.evaluate("() => ({ now: (document.querySelector('#headsDlgBody .fw-todo-i.is-now .fw-todo-t') || {}).textContent || '', mark: (document.querySelector('#headsDlgBody .fw-w-tab[data-tab=plan] .fw-wt-mark') || {}).textContent || '' })")
            check("④-1 초안 작성 탭 — 물음이 남으면 할 일의 지금 = 작성 계획(탭으로 감) · 작성 계획 탭에 「답 1」", wt["now"].startswith("작성 계획 · 확인할 것") and wt["mark"] == "답 1", wt)
            page.evaluate("() => fwWTabGo('plan')")
            q = page.evaluate("() => { const q = document.querySelector('#headsDlgBody .fw-q'); return { text: q.textContent, btns: [...q.querySelectorAll('button')].map((b) => [b.textContent, b.title]) }; }")
            check("④-1 검토 뒤 — 확인할 것(물음 · 자료에서 · 고를 답 · 자료대로) · 「작성 초안 받기」 꺼짐 + 까닭 · 작성 방향", "어느 기관의 몫을 쓰나요?" in q["text"] and q["btns"][0] == ["자료에서: 한국선급", "근거: 한국선급(KR)"]
                  and [b[0] for b in q["btns"][1:]] == ["한국선급", "자료대로"] and foot["btns"][-1][1] and foot["btns"][-1][2] == "쓰기 전에 확인할 것 1개에 답하세요" and how == ["작성 방향: 개조식 3줄", "자료에서 쓸 것: 자료의 최종 목표 문단", "자료에 없는 것: 기준 연도"]
                  and page.evaluate("() => [...document.querySelectorAll('#headsDlgBody .fw-steps .fw-tag')].map((x) => x.textContent)") == ["양식 검토 ✓", "작성 계획 ✓", "확인할 것 0/1"], (q, foot, how))
            page.screenshot(path=str(OUT / "04b_review.png"))
            page.click("#headsDlgBody .fw-q button:has-text('자료대로')")
            page.wait_for_function("() => !document.querySelector('#headsDlgBody .fw-q.is-open')", timeout=10000)
            check("④-1 「자료대로」 → PUT {answers:[{key, a}]} · 물음이 닫힌다", put == [{"answers": [{"key": "q1", "a": "자료대로", "q": "어느 기관의 몫을 쓰나요?"}]}], put)   # 물음 번호와 함께 그 물음의 글도 보낸다(옛 화면의 번호가 다른 물음에 저장되지 않게 — 서버가 견준다)
            page.evaluate("() => fwWTabGo('write')")
            page.wait_for_function("() => { const b = [...document.querySelectorAll('#headsDlgFoot button')].pop(); return b && b.title === '채울 자리를 고르세요'; }", timeout=10000)
            check("④-1 답한 뒤 — 초안 작성 탭의 지금 = 채울 자리 고르기", page.evaluate("() => (document.querySelector('#headsDlgBody .fw-todo-i.is-now .fw-todo-t') || {}).textContent || ''").startswith("채울 자리 고르기"))
            # ④-2 자료에서 찾을 테마 · 키워드(2026-11-24 사용자 "여기서 작성 테마/키워드를 추출해줘 … 테마/키워드 그리고 맥락을 함께" — spec_양식작성 ② §5-2)
            page.evaluate("() => fwWTabGo('topics')")
            t0 = page.evaluate(TOP)   # 오늘 전에 저장한 검토(topics 없음) — 「0개」 가 아니라 「아직 뽑지 않았습니다」
            check("④-2 옛 검토(topics 없음) — 「아직 뽑지 않았습니다」(0개라고 하지 않는다)", bool(t0) and t0["msg"] == "아직 뽑지 않았습니다 — 「다시 검토」 로 뽑습니다" and not t0["rows"] and "0개" not in t0["title"] and t0["help"], t0)
            fr.update(review={**rv, "topics": TOPICS}, topicLines=TOPIC_LINES, lost=[])
            page.evaluate("() => { window.__clip = []; navigator.clipboard.writeText = async (t) => { window.__clip.push(t); }; return fwRead(true).then(fwRedraw); }")
            page.wait_for_selector("#headsDlgBody .fw-topics .fw-top", timeout=10000)
            t1 = page.evaluate(TOP)
            check("④-2 테마 줄 — 테마 · 키워드 · 맥락 · 처음에는 고른 것 없음 · 「고른 것 복사」 꺼짐 · 「문서 라이브러리 열기」", len(t1["rows"]) == 10 and t1["rows"][0]["name"] == "테마 1" and t1["rows"][0]["kws"] == ["개발 목표", "세부 목표"]
                  and "개조식" in t1["rows"][0]["ctx"] and not any(r["on"] for r in t1["rows"]) and t1["copy"] == ["고른 것 복사", True] and t1["lib"] == ["문서 라이브러리 열기", False] and "(10)" in page.evaluate("() => (document.querySelector('#headsDlgBody .fw-top-tab.is-on') || {}).textContent || ''") and not t1["over"], t1)   # 테마 수 = 테마 절 안 탭(「06 … (10)」 — 3b 가 제목에서 옮김)
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
                  and dl["review"]["acts"] == [["테마 · 키워드 보기", False]] and [a[0] for a in dl["guides"]["acts"]] == ["작성 지침 보기 · 적기", "테마 · 키워드 보기", "건너뛰기 취소"]   # 「건너뛰기 취소」 — ② 에서 04 를 건너뛰었다
                  and dl["plan"]["state"] == "done" and "확인할 것 1개 모두 답함" in dl["plan"]["text"], {k: dl[k] for k in ("guides", "review", "plan")})
            # ④-3 「지침 보기 · 적기」(2026-11-24 사용자 「지침작성 자리가 맞냐?」) — 「채울 자리」 로 굴리고 지침을 펼치며 헤딩 자리에서 바로 적는다(PUT …/place-guides/heads · 비우면 지움)
            page.evaluate("() => fwWriteOpen('guides')")
            page.wait_for_selector("#headsDlgBody .fw-gmode", timeout=10000)
            GM = """() => { const b = document.getElementById('headsDlgBody'), sec = b.querySelector('.fw-places-sec'), ds = [...b.querySelectorAll('.fw-place:not(.is-table):not(.is-box) details.fw-guides:not(.fw-chunks)')];
              return { top: FW.wTab === 'guides' && !!b.querySelector('.fw-w-tab.is-on[data-tab=guides]') && !b.querySelector('.fw-review-sec, .fw-plan-sec, .fw-mats'), open: ds.length && ds.every((d) => d.open), notes: b.querySelectorAll('.fw-place:not(.is-table):not(.is-box) .fw-gnote').length,
                heads: b.querySelectorAll('.fw-place:not(.is-table):not(.is-box)').length, run: !!sec.querySelector('[data-where="run:guides"]') }; }"""
            g1 = page.evaluate(GM)
            first = page.locator("#headsDlgBody .fw-place:not(.is-table):not(.is-box) .fw-gnote").first
            first.fill("개조식 3줄로")
            first.locator("xpath=following-sibling::button").click()
            page.wait_for_function("() => [...document.querySelectorAll('#headsDlgBody .fw-place .fw-tag')].some((t) => t.textContent === '사람 지침')", timeout=10000)
            first = page.locator("#headsDlgBody .fw-place:not(.is-table):not(.is-box) .fw-gnote").first
            saved = first.input_value()
            first.fill("")
            first.locator("xpath=following-sibling::button").click()
            page.wait_for_function("() => ![...document.querySelectorAll('#headsDlgBody .fw-place .fw-tag')].some((t) => t.textContent === '사람 지침')", timeout=10000)
            check("④-3 「지침 보기 · 적기」 — 「작성 지침」 탭(그 절만) · 헤딩마다 지침 펼침 · 적는 칸 · 저장하면 「사람 지침」 · 비우고 저장하면 지움", g1["top"] and g1["open"] and g1["notes"] == g1["heads"] > 0 and g1["run"] and saved == "개조식 3줄로", (g1, saved))
            page.locator("#headsDlg").screenshot(path=str(OUT / "04d_guides.png"))
            page.evaluate("() => fwWriteOpen('write')")
            page.wait_for_function("() => !document.querySelector('#headsDlgBody .fw-gmode') && !document.querySelector('#headsDlgBody .fw-gnote')", timeout=10000)
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
            # ⑤-1b 꼬리표의 뜻 · 나온 단계(spec_양식작성 ② §6 「꼬리표의 뜻 · 나온 단계」) — 꼬리표 끝 순서 번호(data-no · 대시보드와 같은 셈) + 절 아래 범례(보이는 꼬리표만)
            lg = page.evaluate("""() => { const no = (fwStepNo('heads') || {}).no, tag = (w) => [...document.querySelectorAll('#headsDlgBody .fw-place .fw-tags .fw-tag')].find((t) => t.textContent === w || t.textContent.startsWith(w));
              const L = document.querySelector('#headsDlgBody .fw-places-sec > .fw-legend');
              return { no, fill: (tag('채움') || {}).dataset?.no, chunk: (tag('쓸 자리') || {}).dataset?.no, guide: (tag('지침') || {}).dataset?.no,
                rows: L ? [...L.querySelectorAll('.fw-legend-row')].map((r) => [r.querySelector('.fw-tag').textContent, r.querySelector('.fw-legend-from').textContent]) : null,
                over: document.getElementById('headsDlgBody').scrollWidth > document.getElementById('headsDlgBody').clientWidth + 1 }; }""")
            words = dict(lg["rows"] or [])
            check("⑤-1b 꼬리표 끝 순서 번호 · 절 아래 범례(채움 · 쓸 자리 n · 지침 n ← 헤딩 · 표 분석) · 옆으로 안 넘침", bool(lg["no"]) and lg["fill"] == lg["chunk"] == lg["guide"] == lg["no"]
                  and all(str(words.get(w, "")).startswith(f"← {lg['no']} ") for w in ("채움", "쓸 자리 n", "지침 n")) and "표시 줄" in words and not lg["over"], lg)
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
            lp.goto(base + "/api/doclib/prompt-editor")
            lp.wait_for_selector("#skillDlg[open] #skillTabs button", timeout=10000)
            sk = lp.evaluate("() => ({ tabs: [...document.querySelectorAll('#skillTabs button')].map((b) => b.textContent), text: document.getElementById('skillText').value.slice(0, 40), contract: document.getElementById('skillContract').textContent.length })")
            check("⑥ 문서 라이브러리의 프롬프트 주소에서 스킬 편집기가 열린다", lp.url == lib + "/#prompts" and len(sk["tabs"]) == 3 and sk["text"].startswith("# 자료 추출") and sk["contract"] > 200, sk)
            lp.screenshot(path=str(OUT / "06_library.png"))
            lp.close()
            # ⑦ 에이전트 보기의 「라이브러리」 — 입력 칸 위에 펴지는 고르기(2026-11-24 사용자 "에이전트에서는 라이브러리에서 등록한 파일들을 선택해서 참조할 수 있도록 해줘, 전체 해도 되고" — spec_양식작성 ② §4)
            #    추출 전인 문서 하나를 더 올려 두고(원본 파일을 글로 읽어 자료로) 본 뒤, 그 문서와 그 자료를 지운다(뒤 검사의 수가 그대로이게)
            import fitz
            raw = fitz.open()
            raw.new_page().insert_text((72, 72), "raw original text of the registered file")
            did2 = requests.post(lib + "/api/docs", files={"file": ("추출 전 문서.pdf", raw.tobytes())}, timeout=30).json()["doc"]["id"]
            # 양식 작성 — 자료로 쓰는 것은 이 프로젝트에 고른 참조 문서의 것만(spec_양식작성 ② §2-1): 그 서버에 바로 올린 문서는 먼저 이 프로젝트에 넣는다(안 넣으면 가져오기가 409)
            check("⑦ 라이브러리에 바로 올린 문서를 이 프로젝트에 넣음", requests.put(f"{base}/api/docs/{doc}/refs", json={"doc": did2, "on": True}, timeout=30).status_code == 200)
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
            requests.put(f"{base}/api/docs/{doc}/refs", json={"doc": did2, "on": False}, timeout=30)   # 뒤 검사의 수가 그대로이게 — 프로젝트에서도 뺀다
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
            check("문서 라이브러리 서버가 꺼지면 대시보드가 알린다(자료는 그대로)", d["keep"]["state"] == "hold" and d["keep"]["acts"] == [["참조 문서 고르기", True], ["문서 라이브러리 열기", True]] and d["take"]["state"] == "done" and "이 문서의 자료 1개" in d["take"]["text"], {k: d[k] for k in ("keep", "take")})
            # 06 줄의 상태 글 = 「서버 꺼짐」(전에는 대시보드 공용 글 「기관 미지정」 — 취합의 말)
            page.evaluate("() => dashDraw(true)")
            page.wait_for_function("() => /서버 꺼짐/.test((document.querySelector('#paneDash .dash-node[data-key=keep]') || {}).textContent || '')", timeout=20000)
            check("문서 라이브러리 서버가 꺼지면 06 줄의 상태 글은 「서버 꺼짐」(「기관 미지정」 이 아님)", "기관 미지정" not in page.evaluate(DASH)["nodes"]["keep"]["text"], page.evaluate(DASH)["nodes"].get("keep"))
            page.screenshot(path=str(OUT / "07_lib_down.png"))
            page.click("#paneAgent [data-ag-act=shelf]")   # ⑦ 꺼진 뒤의 고르기 — 꺼져 있다고 알리고 가져오기는 꺼진다(자료 칩은 그대로)
            page.wait_for_function("() => /꺼져 있습니다/.test((document.querySelector('#paneAgent .ag-lib-state') || {}).textContent || '')", timeout=30000)
            s5 = page.evaluate(SHELF)
            check("⑦ 문서 라이브러리 서버가 꺼지면 고르기가 알린다(띄우개 · 가져오기 꺼짐 · 자료 칩 그대로)", "tools/start_doclib.ps1" in s5["state"] and s5["take"] == ["가져오기", True] and not s5["rows"] and s5["chips"] == 1, s5)
            page.locator("#paneAgent .ag-input").screenshot(path=str(OUT / "07b_agent_library_down.png"))
            page.evaluate("() => { AGENT.shelf.open = false; agentDrawInput(); if (typeof agentFloating === 'function' && agentFloating() && typeof agentFloatClose === 'function') agentFloatClose(); }")
            # ⑧′ 단계별 초기화(2026-11-24 사용자 "준비/자료,작성 단계를 따로 두고 단계별로 … 초기화" · 같은 날 "복잡하게 하지 말고,, 전체 초기화 각 단계별 초기화로 … 단계로 해주고" — spec_양식작성 ② §6-1):
            #    묶음 머리마다 「N단계 초기화」(번호 = 묶음 머리의 번호) → 그 아래 확인 줄(단추는 「N단계 초기화」 · 「취소」 둘뿐) → 그 단계의 것만 비운다
            page.evaluate("() => { if (typeof headsColClose === 'function') headsColClose(); showTab('Dash'); }")
            page.wait_for_selector('#paneDash [data-dash-focus="fwreset:write"]:not([disabled])', timeout=60000)
            RS = """() => { const b = document.querySelector('#paneDash .dash-reset[data-fw-reset]');
              return { heads: [...document.querySelectorAll('#paneDash .dash-ghead [data-dash-focus^="fwreset:"]')].map((x) => [x.dataset.dashFocus, x.textContent]),
                nos: [...document.querySelectorAll('#paneDash .dash-group')].map((g) => [`fwreset:${g.dataset.group}`, `${g.querySelector('.dash-gno').textContent}단계 초기화`]),
                box: b ? { st: b.dataset.fwReset, head: b.querySelector('.dash-reset-head').textContent, help: !!b.querySelector('.dash-reset-head .panel-help'), under: b.closest('.dash-group').dataset.group,
                  acts: [...b.querySelectorAll('.dash-reset-acts button')].map((x) => [x.dataset.dashFocus, x.textContent, x.disabled]) } : null, tool: document.getElementById('panel').dataset.tool }; }"""
            mats_n = lambda: len(requests.get(f"{base}/api/docs/{doc}/agent", timeout=60).json()["materials"])  # noqa: E731
            page.locator('#paneDash [data-dash-focus="fwreset:write"]').click()
            page.wait_for_selector('#paneDash .dash-reset[data-fw-reset=write]', timeout=20000)
            r1 = page.evaluate(RS)
            check("⑧′ 묶음 머리마다 「N단계 초기화」(번호 = 묶음 머리의 번호) · 3단계를 누르면 그 묶음 아래에 확인 줄(한 줄 머리 · 노트 아이콘 · 단추는 「3단계 초기화」 · 「취소」 둘뿐) — 누르기 전에는 안 바뀜",
                  r1["heads"] == [["fwreset:open", "1단계 초기화"], ["fwreset:material", "2단계 초기화"], ["fwreset:write", "3단계 초기화"]] and r1["heads"] == r1["nos"] and r1["box"] and r1["box"]["under"] == "write" and r1["box"]["help"]
                  and r1["box"]["head"].startswith("3단계 「작성」 초기화 — ") and "올린 원본" in r1["box"]["head"] and r1["box"]["acts"] == [["fwreset:write:go", "3단계 초기화", False], ["fwreset:close", "취소", False]] and mats_n() == 1, r1)
            page.locator("#paneDash").screenshot(path=str(OUT / "08a_stage_reset.png"))
            page.locator('#paneDash [data-dash-focus="fwreset:close"]').click()
            page.wait_for_function("() => !document.querySelector('#paneDash .dash-reset[data-fw-reset]')", timeout=20000)
            page.locator('#paneDash [data-dash-focus="fwreset:write"]').click()
            page.locator('#paneDash [data-dash-focus="fwreset:write:go"]').click()
            page.wait_for_function("() => /3단계 「작성」 초기화 — 초안/.test(document.getElementById('toast').textContent) && !document.querySelector('#paneDash .dash-reset[data-fw-reset]')", timeout=120000)
            r2 = page.evaluate(RS)
            check("⑧′ 「3단계 초기화」(작성) — 초안 · 작성 계획만 비우고 대시보드에 머묾 · 자료는 그대로", r2["tool"] == "Dash" and mats_n() == 1 and not requests.get(f"{base}/api/docs/{doc}/agent", timeout=60).json()["turns"], r2)
            page.wait_for_selector('#paneDash [data-dash-focus="fwreset:open"]:not([disabled])', timeout=60000)
            page.locator('#paneDash [data-dash-focus="fwreset:open"]').click()
            page.wait_for_selector('#paneDash .dash-reset[data-fw-reset=open]', timeout=20000)
            r3 = page.evaluate(RS)
            page.locator('#paneDash [data-dash-focus="fwreset:open:go"]').click()
            page.wait_for_function("() => /1단계 「준비」 초기화 — 올린 직후로 되돌렸습니다/.test(document.getElementById('toast').textContent) && !!document.querySelector('#doc .para')", timeout=120000)
            check("⑧′ 「1단계 초기화」(준비) — 확인 줄의 단추는 「1단계 초기화」 · 「취소」 둘뿐(「모두 초기화(자료도)」 없음 — 전체는 맨 아래 하나) · 머리가 자료는 남긴다고 밝힘 · 올린 직후로 되돌리되 이 문서의 자료는 남긴다",
                  r3["box"] and r3["box"]["under"] == "open" and [a[:2] for a in r3["box"]["acts"]] == [["fwreset:open:go", "1단계 초기화"], ["fwreset:close", "취소"]]
                  and r3["box"]["head"].startswith("1단계 「준비」 초기화 — ") and "자료는 남김" in r3["box"]["head"] and mats_n() == 1, r3)
            # ⑥-2 · ⑥-1 「초기화 뒤」(2026-11-25 사용자 "왜 초기화 하면 1,2,3, 은 끝남으로 나오냐? 그리고 단계 별라 자동실행 기능 넣어주고, , 전체 실행 넣어주고" — spec_양식작성 ② §6-1 · §6-2)
            page.wait_for_timeout(2500)   # 다시 연 뒤 분석 상태를 읽을 틈 — 첫 분석을 걸지 않으니 「헤딩 · 표 분석」 은 끝남으로 바뀌지 않아야 한다
            page.evaluate("async () => { if (typeof dsRefresh === 'function') await dsRefresh(); FW.at = 0; }")
            n1 = page.evaluate(LIVE)
            check("⑥-1 1단계 초기화 뒤 — 첫 분석을 다시 걸지 않아 「헤딩 · 표 분석」 은 끝남이 아니다(「분석」 단추) · 목적 문서 줄은 그대로 끝남", n1["heads"]["state"] in ("now", "todo") and n1["open"]["state"] == "done", {"heads": n1["heads"], "open": n1["open"]})
            AU = """() => ({ runs: [...document.querySelectorAll('#paneDash .dash-ghead button[data-run]')].map((b) => [b.dataset.run, b.textContent, b.disabled]),
              top: [...document.querySelectorAll('#paneDash .dash-top button[data-run]')].map((b) => [b.dataset.run, b.textContent, b.disabled]),
              end: [...document.querySelectorAll('#paneDash .dash-group')].map((g) => [g.dataset.group, (g.querySelector('.dash-gend') || {}).textContent || '']) })"""
            page.wait_for_function("() => !!document.querySelector('#paneDash .dash-ghead button[data-run=open]:not([disabled])')", timeout=60000)
            au = page.evaluate(AU)
            check("⑥-2 묶음 머리마다 「한 번에 진행」(「N단계 초기화」 옆) · 머리 아래 「전체 실행 1→3단계」",
                  [r[:2] for r in au["runs"]] == [["open", "한 번에 진행"], ["material", "한 번에 진행"], ["write", "한 번에 진행"]] and au["top"] and au["top"][0][:2] == ["chain", "전체 실행 1→3단계"], au)
            page.locator('#paneDash .dash-ghead button[data-run=open]').click()
            page.wait_for_function("() => !fwAuto && !!document.querySelector('#paneDash .dash-group[data-group=open] .dash-gend')", timeout=240000)
            au2, n2 = page.evaluate(AU), page.evaluate(LIVE)
            end_open = dict(au2["end"]).get("open", "")
            check("⑥-2 1단계 「한 번에 진행」 — 헤딩 · 표 분석(스크립트)을 돌려 끝남 · LLM 검증·보완은 LLM 이 꺼져 건너뜀 · 작성 지침 확인은 남기고 · 양식 검토에서 LLM 이 없어 멈춤(끝 글)",
                  n2["heads"]["state"] == "done" and n2["headsLlm"]["state"] == "done" and "양식 검토" in end_open and "LLM" in end_open and "작성 지침 확인" in end_open, {"end": au2["end"], "heads": n2["heads"], "headsLlm": n2["headsLlm"]})
            page.locator("#paneDash").screenshot(path=str(OUT / "08c_stage_auto.png"))
            # ⑥-3 패널 「작업 개요」(2026-11-25 사용자 "작업개요가 없는데 연차보고서 이관에 보면 작업 개요 있을텐데 참조해줘" — spec_양식작성 ② §6-3)
            page.locator("#toolTabTask").click()
            page.wait_for_function("() => !!document.querySelector('#divBox .fw-ov-flow .fw-ov-stage')", timeout=60000)
            ov = page.evaluate("""() => ({ tab: !document.getElementById('toolTabTask').hidden, tool: document.getElementById('panel').dataset.tool,
              first: !!document.querySelector('#divBox .dv-task [data-task=project]'), file: !!document.querySelector('#divBox select[data-task=file]'), docs: !!document.querySelector('#divBox .fw-ov-docs'),
              stages: [...document.querySelectorAll('#divBox .fw-ov-stage')].map((d) => [d.dataset.stage, [...d.querySelectorAll('.fw-ov-step')].map((li) => li.dataset.step), !!d.querySelector('summary button[data-run]')]),
              chain: [...document.querySelectorAll('#divBox .fw-ov-flow .dash-top button[data-run]')].map((b) => b.textContent),
              heads: ((document.querySelector('#divBox .fw-ov-step[data-step=heads]') || {}).className || '') })""")
            check("⑥-3 「작업 개요」 탭 — 첫 카드(프로젝트 · 워크플로우 · 라운드 — 첨부 파일 종류 칸 없음) · 문서 카드 · 묶음 셋(줄 · 「한 번에 진행」) · 「전체 실행」 · 대시보드와 같은 상태",
                  ov["tab"] and ov["tool"] == "Div" and ov["first"] and not ov["file"] and ov["docs"] and [s[0] for s in ov["stages"]] == ["open", "material", "write"] and all(s[2] for s in ov["stages"])
                  and "heads" in ov["stages"][0][1] and ov["chain"] and ov["chain"][0].startswith("전체 실행") and "is-done" in ov["heads"], ov)
            page.locator("#paneDiv").screenshot(path=str(OUT / "08d_overview.png"))
            # ⑥-3′ 「작업 개요」 에서 누른 「N단계 초기화」 — 확인 줄이 그 탭(누른 화면)에 선다(2026-11-25 r202: 전에는 대시보드만 다시 그려 숨은 대시보드에만 떴다) · 접힌 묶음이면 펴서 보인다 · 「취소」 · 초기화 끝도 그 탭에 바로
            OVB = '#divBox .fw-ov-stage[data-stage=write] summary [data-dash-focus="fwreset:write"]'
            for _ in range(60):   # 도는 일이 끝나 단추가 켜질 때까지(작업 개요는 열려 있을 때만 다시 그려진다 — 한 번씩 다시 그려 본다)
                if page.evaluate("(q) => { const b = document.querySelector(q); return !!b && !b.disabled; }", OVB):
                    break
                page.evaluate("() => fwOverviewDraw()")
                page.wait_for_timeout(1000)
            OVR = """() => { const b = document.querySelector('#divBox .dash-reset[data-fw-reset]'), d = b && b.closest('.fw-ov-stage');
              return { tool: document.getElementById('panel').dataset.tool, box: b ? { st: b.dataset.fwReset, under: d ? d.dataset.stage : '', open: !!(d && d.open), seen: b.offsetHeight > 0,
                head: b.querySelector('.dash-reset-head').textContent, help: !!b.querySelector('.dash-reset-head .panel-help'),
                acts: [...b.querySelectorAll('.dash-reset-acts button')].map((x) => [x.dataset.dashFocus, x.textContent, x.disabled]) } : null }; }"""
            page.locator(OVB).click()
            page.wait_for_selector('#divBox .fw-ov-stage[data-stage=write] .dash-reset[data-fw-reset=write]', state="visible", timeout=20000)
            o1 = page.evaluate(OVR)
            check("⑥-3′ 「작업 개요」 에서 「3단계 초기화」 를 누르면 그 탭의 그 묶음 아래에 확인 줄이 선다(묶음이 펴짐 · 단추는 「3단계 초기화」 · 「취소」 둘뿐) — 누르기 전에는 안 바뀜",
                  o1["tool"] == "Div" and o1["box"] and o1["box"]["under"] == "write" and o1["box"]["open"] and o1["box"]["seen"] and o1["box"]["help"] and o1["box"]["head"].startswith("3단계 「작성」 초기화 — ")
                  and o1["box"]["acts"] == [["fwreset:write:go", "3단계 초기화", False], ["fwreset:close", "취소", False]] and mats_n() == 1, o1)
            page.locator("#paneDiv").screenshot(path=str(OUT / "08e_overview_reset.png"))
            page.locator('#divBox [data-dash-focus="fwreset:close"]').click()
            page.wait_for_function("() => !document.querySelector('#divBox .dash-reset[data-fw-reset]')", timeout=20000)
            page.locator(OVB).click()
            page.wait_for_selector('#divBox [data-dash-focus="fwreset:write:go"]:not([disabled])', timeout=20000)
            page.locator('#divBox [data-dash-focus="fwreset:write:go"]').click()
            page.wait_for_function("""() => /3단계 「작성」 초기화 — 초안/.test(document.getElementById('toast').textContent) && !document.querySelector('#divBox .dash-reset[data-fw-reset]')
              && !!document.querySelector('#divBox .fw-ov-stage[data-stage=write] summary [data-dash-focus="fwreset:write"]') && !FW.rsBusy""", timeout=120000)
            o2 = page.evaluate(OVR)
            check("⑥-3′ 「작업 개요」 의 「취소」 는 확인 줄을 닫고, 「3단계 초기화」 는 끝난 뒤 그 탭에 머문 채 확인 줄이 걷힌다(자료는 그대로)", o2["tool"] == "Div" and not o2["box"] and mats_n() == 1, o2)
            # 작성 지침 수의 꼴 — n = 지침(items)만 · 각주 번호는 괄호 안에 따로(공통 상세 form_guides.js · 이관의 「작성 지침 n개 저장」 과 같은 셈 — 2026-11-25 r202: 전에는 지침 + 각주 번호를 더해 보였다)
            GC = """(c) => { const keep = FW.fg; FW.fg = { saved: { counts: c } }; try { return fwHeadsStep({ view: {}, hwpx: true, base: true }).text; } finally { FW.fg = keep; } }"""
            g1 = page.evaluate(GC, {"items": 3, "marks": 2, "marksLinked": 1, "headings": 2, "tables": 1})
            g2 = page.evaluate(GC, {"items": 0, "marks": 0, "marksLinked": 0, "headings": 0, "tables": 0})
            g3 = page.evaluate(GC, {"items": 0, "marks": 2, "marksLinked": 0, "headings": 0, "tables": 0})
            check("「헤딩 · 표 분석 · 작성 지침」 줄의 지침 수 — 「작성 지침 {지침}개 저장(헤딩 · 표 · 각주 번호 이어짐/전체)」: 각주 번호를 지침 수에 더하지 않는다 · 지침도 각주 번호도 없을 때만 「양식에 적힌 지침이 없습니다」",
                  "작성 지침 3개 저장(헤딩 2 · 표 1 · 각주 번호 1/2)" in g1 and "없습니다" not in g1 and "작성 지침 0개 저장(헤딩 0 · 표 0)" in g2 and "양식에 적힌 지침이 없습니다" in g2
                  and "작성 지침 0개 저장(헤딩 0 · 표 0 · 각주 번호 0/2)" in g3 and "없습니다" not in g3, (g1, g2, g3))
            page.evaluate("() => { showTab('Dash'); }")
            page.wait_for_selector('#paneDash [data-dash-focus="fwreset:material"]:not([disabled])', timeout=120000)
            page.locator('#paneDash [data-dash-focus="fwreset:material"]').click()
            page.locator('#paneDash [data-dash-focus="fwreset:material:go"]').click()
            page.wait_for_function("() => /2단계 「자료 준비」 초기화 — 자료/.test(document.getElementById('toast').textContent)", timeout=60000)
            page.wait_for_function("() => (document.querySelector('#paneDash .dash-node[data-key=take]') || { dataset: {} }).dataset.state !== 'done'", timeout=30000)
            check("⑧′ 「2단계 초기화」(자료 준비) — 이 문서의 자료만 비운다(대시보드의 「자료 가져오기」 가 끝남에서 내려옴)", mats_n() == 0 and page.evaluate(RS)["tool"] == "Dash", page.evaluate(DASH)["nodes"].get("take"))
            # ⑧ 대시보드 맨 아래의 「전체 초기화…」(= 「작업 내용 초기화」 — 양식 작성에서만 그 이름: dashboard.js DASH_RESET_ALL) — 이 문서의 자료까지 비우고, 일반 문서 워크플로우도 대시보드에 머문다
            #    (전에는 다시 여는 load 가 에이전트 보기로 바꿨다 — 2026-11-24 사용자 "왜 dash 보드에서 초기화 하면 에이전트 탭으로 너머 가냐": spec_작업에이전트 ② §9 「작업 내용 초기화」 「초기화한 뒤」)
            page.evaluate("() => { if (typeof headsColClose === 'function') headsColClose(); showTab('Dash'); }")
            page.wait_for_selector('#paneDash [data-dash-focus="reset"]:not([disabled])', timeout=30000)
            rid = page.evaluate("() => state.id")
            requests.post(f"{base}/api/docs/{rid}/agent/material", json={"name": "전체 초기화 확인", "text": "전체 초기화가 이 문서의 자료까지 비우는지 보는 글입니다."}, timeout=60)   # 자료 하나(2단계 초기화로 0개가 됐다) — 전체는 이것도 비워야 한다
            ALL = """() => { const b = document.querySelector('#paneDash .dash-reset:not([data-fw-reset])'), o = document.querySelector('#paneDash .dash-reset-row [data-dash-focus="reset"]');
              return { open: o ? o.textContent : '', label: b ? b.getAttribute('aria-label') : '', head: b ? b.querySelector('.dash-reset-head').textContent : '', help: !!(b && b.querySelector('.dash-reset-head .panel-help')),
                acts: b ? [...b.querySelectorAll('.dash-reset-acts button')].map((x) => x.textContent) : [] }; }"""
            a0 = page.evaluate(ALL)
            page.locator('#paneDash [data-dash-focus="reset"]').click()
            page.wait_for_selector(f'#paneDash [data-dash-focus="reset:{rid}"]', timeout=30000)
            a1 = page.evaluate(ALL)
            check("⑧ 맨 아래 단추는 「전체 초기화…」 — 펴면 확인 상자(머리 「전체 초기화 — …」 · 노트 아이콘 · 단추는 「전체 초기화」 · 「취소」 둘뿐) · 누르기 전에는 자료 그대로",
                  a0["open"] == "전체 초기화…" and a1["label"] == "전체 초기화" and a1["head"].startswith("전체 초기화 — ") and a1["help"] and a1["acts"] == ["전체 초기화", "취소"] and mats_n() == 1, (a0, a1))
            page.locator("#paneDash").screenshot(path=str(OUT / "08b_reset_all.png"))
            page.locator(f'#paneDash [data-dash-focus="reset:{rid}"]').click()
            page.wait_for_function("() => /전체 초기화했습니다/.test(document.getElementById('toast').textContent) && !!document.querySelector('#doc .para') && !document.querySelector('#paneDash .dash-reset')", timeout=120000)
            check("⑧ 「전체 초기화」 — 이 문서의 자료까지 비운다(1단계 초기화와 다른 점)", mats_n() == 0, mats_n())
            page.wait_for_timeout(1200)   # 다시 연 뒤의 그리기(탭을 바꾸던 곳)가 지나가게
            rz = page.evaluate("""() => { const f = document.getElementById('agentFloat'), row = document.querySelector('#paneDash .dash-reset-row');
              return { tool: document.getElementById('panel').dataset.tool, dash: !document.getElementById('paneDash').hidden, float: !!f && !f.hidden && f.offsetWidth > 0,
                row: row ? [...row.querySelectorAll('button')].map((b) => [b.dataset.dashFocus, b.textContent]) : [] }; }""")
            check("⑧ 대시보드의 「전체 초기화」 뒤 — 대시보드에 머묾 · 에이전트 창도 저절로 안 열림 · 맨 아래 줄에 「전체 초기화…」 단추(「다음」 단추가 있으면 그 앞)",
                  rz["tool"] == "Dash" and rz["dash"] and not rz["float"] and rz["row"] and rz["row"][-1] == ["reset", "전체 초기화…"] and all(k in ("reset:next", "reset") for k, _ in rz["row"]), rz)
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

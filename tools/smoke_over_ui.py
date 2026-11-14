"""넘친 개요 레벨(spec_병합 ② §5-5 9 — app/static/merge_over.js) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 흉내(정규식 route).

    python -X utf8 tools/smoke_over_ui.py <그림·임시 폴더> [--port 18170]

작은 문서 하나를 올려 열고, 세 목록(이관 「넣기 계획」 fillList · 취합 「넣기 계획」 gatherFillList · 「끌어 넣기」 gatherDropList)에 흉내 계획을 넣어 그린다:
계획에 over 가 없으면 절이 없음 → 있으면 2열 안의 한 절(모달 없음) · 사례 줄(자리 템플릿 사슬 ▸ 넘친 레터 · 줄 수 · 처리 목록 셋) · 알림 꼬리표 →
「템플릿 수정」 = 그 줄 아래에 레벨 표(레터 · 본보기 · 앞 공백) → 「적용」 = PUT 바디 · 계획 다시 → 「다른 템플릿」(그 자리 아래 템플릿이 맨 앞) → 「덮은 템플릿 그대로」 = 바로 저장 → 「취소」 →
넣은 줄의 기록이 있으면 「넣은 줄에 다시 맞추기(n줄)」 → 확인 → POST refit → 문서 다시 읽기 · 계획 다시. 계획을 다시 세우는 함수(fillPlan · gatherPlanMake · gatherDropPlan)는 흉내 끝점을 읽게 바꿔 둔다."""
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
ap.add_argument("--port", type=int, default=18170)
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
KEY = "body:[…]›□›o›-<o›-›·"
TPLS = [{"anchor": "body:N.›N-N.›o", "no": 1, "kind": "main", "chain": ["N.", "N-N.", "o"], "levels": [{"level": 1, "key": "N.", "letter": "1.", "text": "개요", "rep": "p1", "ok": True}, {"level": 2, "key": "N-N.", "letter": "1-1.", "text": "", "rep": "p2", "ok": True},
                                                                                           {"level": 3, "key": "o", "letter": "ㅇ", "text": "", "rep": "p3", "ok": True}]},
        {"anchor": "body:o›-", "no": 2, "kind": "branch", "chain": ["o", "-"], "levels": [{"level": 1, "key": "o", "letter": "ㅇ", "text": "보기 줄", "rep": "p4", "ok": True}, {"level": 2, "key": "-", "letter": "-", "text": "", "rep": "p5", "ok": True}]},
        {"anchor": "body:[…]›□›o›-", "no": 3, "kind": "branch", "chain": ["[…]", "□", "o", "-"], "levels": [{"level": 1, "key": "[…]", "letter": "", "text": "", "rep": "p6", "ok": False}, {"level": 2, "key": "□", "letter": "□", "text": "", "rep": "p7", "ok": True}]}]
STORE = {"version": 0, "cases": {}}   # 흉내 서버의 merge_over.json
CALLS = []                            # 흉내 끝점이 받은 것 [(무엇, 바디)]
STATE = {"lines": 3, "applied": 0, "at": None}


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:300] if detail != "" else ""), flush=True)
    if not ok:
        fails.append(name)


def over():
    """흉내 서버의 계획 응답 over — 저장된 선택(STORE)으로 레벨마다 넣을 것."""
    ch = STORE["cases"].get(KEY) or {}
    mode = ch.get("mode", "cover")
    specs = ch.get("levels") or []
    if mode == "template":
        t = ch["template"]
        depth = len(next(x for x in TPLS if x["anchor"] == t["template"])["chain"])
        specs = [{"letter": None, "like": {"template": t["template"], "level": lv}, "lead": None} for lv in range(t["level"], depth + 1)]
    levels = []
    for i, k in enumerate(["o", "-", "·"]):
        sp = (specs[i] if i < len(specs) else None) or {}
        like = sp.get("like")
        if like:
            slot = next(x for x in next(t for t in TPLS if t["anchor"] == like["template"])["levels"] if x["level"] == like["level"])
            like = {**like, "letter": slot["letter"], "text": slot["text"]}
        levels.append({"n": 5 + i, "key": k, "was": k, "lines": STATE["lines"] and 1, "applied": 0, "letter": sp.get("letter"), "like": like, "lead": sp.get("lead"),
                       "clash": not sp and k in ("o", "-"), "missing": False})
    return {"version": STORE["version"], "templates": TPLS, "records": {"lines": STATE["applied"], "cases": {KEY: STATE["applied"]} if STATE["applied"] else {}},
            "cases": [{"key": KEY, "to": {"template": "body:[…]›□›o›-", "no": 3, "chain": ["[…]", "□", "o", "-"], "level": 4}, "tail": ["o", "-", "·"], "levels": levels, "lines": STATE["lines"], "applied": STATE["applied"],
                       "places": 2, "at": STATE["at"], "mode": mode, "template": ch.get("template"), "under": ["body:o›-"]}]}


def fill_plan(with_over=True):
    return {"planId": "pl1", "baseRev": 0, "todo": 1, **({"over": over()} if with_over else {}),
            "body": {"counts": {"todo": 1}, "items": [{"group": "g1", "value": "주관", "to": STATE["at"], "from": "s1", "anchorText": "- (추진 내용)", "blocks": 4, "paragraphs": 4, "tables": 0, "pictures": 0, "skip": None, "detail": "",
                                                       "convert": {"converted": 0, "over": 3, "kept": {"tooDeep": 3}} if with_over else None}]},
            "tables": {"counts": {"cells": 0, "rows": 0, "calc": 0, "skipped": {}}, "tables": [], "skipped": []}}


def gather_plan():
    return {"planId": "gp1", "part": "p1", "todo": 1, "counts": {"paragraphs": 3, "kept": 1, "over": 1}, "skipped": {}, "calc": [], "dropped": [], "over": over(),
            "items": [{"key": "h1", "kind": "filled", "scope": {"kind": "org", "org": "가나대", "orgName": "가나대", "year": None}, "path": ["2. 목표"], "text": "o 가나대 넘침 목표", "decision": None,
                       "to": {"prev": STATE["at"], "next": None, "at": STATE["at"]}, "from": {"ids": ["s1"], "table": None, "at": "s1"}, "counts": {"paragraphs": 3, "placeholders": 1, "kept": 1, "over": 1},
                       "convert": {"converted": 0, "same": 2, "kept": {"tooDeep": 1}, "labels": {"tooDeep": "넘친 레벨 — 덮은 템플릿(기관 문서 꼴 그대로)"}, "rows": []}}]}


def drop_plan():
    ov = over()
    return {"planId": "dp1", "from": "p1", "range": {"title": "□ 필요성", "blocks": 4, "paragraphs": 4, "tables": 0, "pictures": 0, "lines": 4, "single": False}, "after": {"id": STATE["at"], "text": "□ 배경", "given": STATE["at"]},
            "owner": {"id": STATE["at"], "text": "□ 배경"}, "dropped": [], "over": {k: ov[k] for k in ("version", "cases", "templates")},
            "convert": {"converted": 3, "kept": {"tooDeep": 1}, "labels": {"tooDeep": "넘친 레벨 — 덮은 템플릿(기관 문서 꼴 그대로)"}, "anchor": ["body:□›o›-›·", 1], "rows": [], "more": 0}}


def route(r):
    """흉내 끝점 — merge-over(PUT · refit) · 세 계획. 그 밖은 진짜 서버로."""
    req, url = r.request, r.request.url
    body = json.loads(req.post_data or "{}") if req.method in ("PUT", "POST") else None
    send = lambda data, status=200: r.fulfill(status=status, content_type="application/json", body=json.dumps(data, ensure_ascii=False))  # noqa: E731
    if url.endswith("/merge-over/refit"):
        CALLS.append(("REFIT", body))
        return send({"lines": STATE["applied"], "kept": {"edited": 1}, "labels": {"edited": "첫머리가 바뀐 줄(사람이 고침)"}, "rev": 9})
    if url.endswith("/merge-over") and req.method == "PUT":
        CALLS.append(("PUT", body))
        if body.get("mode") == "edit" and body["levels"] and (body["levels"][0] or {}).get("letter") == "거절":
            return send({"detail": "넘친 레벨 1: 흉내 서버가 거절"}, 400)
        STORE["version"] += 1
        if body.get("reset") or body.get("mode") == "cover":
            STORE["cases"].pop(KEY, None)
        else:
            STORE["cases"][KEY] = {k: body.get(k) for k in ("mode", "levels", "template")}
        return send({"version": STORE["version"], "key": body["key"], "case": STORE["cases"].get(KEY)})
    if url.endswith("/merge-links/plan"):
        CALLS.append(("PLAN", "fill"))
        return send(fill_plan())
    if url.endswith("/gather/parts/p1/plan"):
        CALLS.append(("PLAN", "gather"))
        return send(gather_plan())
    if url.endswith("/gather/drop/plan"):
        CALLS.append(("PLAN", "drop"))
        return send(drop_plan())
    return r.continue_()


SEC = "#headsDlgBody .mo-sec"
INFO = f"""() => {{ const s = document.querySelector('{SEC}'); if (!s) return null; const c = s.querySelector('.mo-case');
  return {{ cap: s.querySelector('.mo-cap span').textContent, cases: s.querySelectorAll('.mo-case').length, name: c.querySelector('.mo-name').textContent, count: c.querySelector('.mo-count').textContent,
    mode: c.querySelector('.mo-mode').value, modes: [...c.querySelectorAll('.mo-mode option')].map((o) => o.textContent), levels: [...c.querySelectorAll('.mo-levels li')].map((li) => li.textContent),
    flags: [...c.querySelectorAll('.mo-flag')].map((f) => f.textContent), edit: (c.querySelector('.mo-edit') || {{ dataset: {{}} }}).dataset.mode || null, refit: (s.querySelector('[data-mo-refit]') || {{}}).textContent || null,
    help: !!s.querySelector('.mo-cap .panel-help'), wide: s.scrollWidth > s.clientWidth + 1, modal: !!document.querySelector('dialog[open]'), kind: document.getElementById('headsDlg').dataset.kind }}; }}"""
STUBS = """() => {
  window.__n = { fill: 0, gather: 0, drop: 0, went: [], applied: null, reloads: 0 };
  const plan = async (url) => (await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })).json();
  window.fillPlan = async () => { __n.fill += 1; taskFlow.fill = { plan: await plan(`/api/docs/${state.id}/merge-links/plan`), done: null }; fillList(); };
  window.gatherPlanMake = async (pid) => { __n.gather += 1; gt().plans[pid] = await plan(`/api/docs/${state.id}/gather/parts/${pid}/plan`); return gt().plans[pid]; };
  window.gatherDropPlan = async (d, afterId) => { __n.drop += 1; gt().drop = { plan: await plan(`/api/docs/${state.id}/gather/drop/plan`), from: d.from, srcId: d.srcId, afterId, convert: true, busy: false }; gatherDropList(); };
  window.divGo = (c) => { __n.went.push(c.key); };
  window.gatherJump = (id) => { __n.went.push(id); };
  window.applyEditState = (r) => { __n.applied = r; };
  window.reloadDoc = async () => { __n.reloads += 1; };
}"""


def wait_calls(page, n):
    for _ in range(100):
        if len(CALLS) >= n:
            return True
        page.wait_for_timeout(50)
    return False


try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    p = ROOT / "samples" / "기술수요조사서.hwpx"
    wid = requests.post(f"{base}/api/docs?new=1", files={"file": (p.name, p.read_bytes())}, timeout=120).json()["docId"]
    assert requests.put(f"{base}/api/works/{wid}/task", json={"kind": "rnd", "file": "plan", "job": "plan_merge", "project": "넘침 화면 시험"}, timeout=30).ok
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" and "400" not in m.text else None)   # 기대한 400(거절)은 브라우저가 콘솔에 남긴다
        page.on("dialog", lambda d: d.accept())
        page.route(re.compile(r"/api/docs/[^/]+/(merge-over(/refit)?|merge-links/plan|gather/parts/p1/plan|gather/drop/plan)$"), route)
        page.goto(base)
        page.evaluate("(id) => { location.hash = '#w=' + id; }", wid)
        page.reload()
        page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=wid, timeout=120000)
        STATE["at"] = page.evaluate("() => document.querySelector('#doc .sheet .para').dataset.id || state.blocks.find((b) => b.type === 'paragraph').id")
        check("merge_over.js 가 읽혔다(app.js 다음) · 처리 셋", page.evaluate("() => typeof mergeOverSection === 'function' && Object.values(MERGE_OVER_MODE).join('|')") == "덮은 템플릿 그대로|템플릿 수정|다른 템플릿")
        page.evaluate(STUBS)

        # ---- 1. 이관 「넣기 계획」 — over 가 없으면 절이 없고(전 화면 그대로), 있으면 본문 표 아래 한 절
        page.evaluate("(p) => { taskFlow.fill = { plan: p, done: null }; fillList(); }", fill_plan(False))
        check("계획에 over 가 없으면 절을 안 그린다(본문 표는 그대로)", page.evaluate(f"() => !document.querySelector('{SEC}') && document.querySelectorAll('#headsDlgBody table.lk-table').length >= 2"))
        page.evaluate("(p) => { taskFlow.fill = { plan: p, done: null }; fillList(); }", fill_plan())
        info = page.evaluate(INFO)
        check("넘친 개요 레벨 절 — 2열 「넣기 계획」 안(모달 아님) · 머리 글 · 노트 도움말", info and info["kind"] == "fill" and not info["modal"] and info["cap"] == "넘친 개요 레벨 — 1곳 · 넣을 줄 3" and info["help"], info)
        check("사례 줄 — 자리 템플릿 사슬 ▸ 넘친 원본 레터 · 줄 수·자리 수 · 처리 목록 셋(기본 = 덮은 템플릿 그대로)", info["name"] == "[…] › □ › o › - ▸ o › - › ·" and info["count"] == "넣을 줄 3 · 자리 2"
              and info["mode"] == "cover" and info["modes"] == ["덮은 템플릿 그대로", "템플릿 수정", "다른 템플릿"] and info["edit"] is None and info["refit"] is None, info)
        check("레벨마다 무엇이 들어가는지 · 알림 꼬리표(윗 레벨과 같은 레터)", len(info["levels"]) == 3 and all("원본 그대로" in t for t in info["levels"]) and info["levels"][0].startswith("L5 「o」")
              and info["flags"] == ["윗 레벨과 같은 레터"] * 2, info)
        check("본문 항목의 넣을 것 칸에 넘친 줄 수 · 절이 열 폭을 넘지 않는다", "넘친 줄 3" in page.evaluate("() => document.querySelector('#headsDlgBody table.lk-table tbody tr').textContent") and not info["wide"], info)
        page.click(f"{SEC} .mo-name")
        check("사례 이름을 누르면 문서의 첫 자리로", page.evaluate("() => __n.went") == [STATE["at"]])
        page.screenshot(path=str(OUT / "over_1_cover.png"))

        # ---- 2. 「템플릿 수정」 — 그 줄 아래에 펴짐(같은 열) · 「적용」 을 눌러야 저장 → PUT 바디 → 계획 다시
        page.select_option(f"{SEC} .mo-mode", "edit")
        ed = page.evaluate(f"""() => {{ const e = document.querySelector('{SEC} .mo-edit'); return e && {{ mode: e.dataset.mode, th: [...e.querySelectorAll('.mo-th')].map((x) => x.textContent), rows: e.querySelectorAll('.mo-letter').length,
          likes: [...e.querySelector('.mo-like').options].map((o) => o.textContent), acts: [...e.querySelectorAll('.mo-acts button')].map((b) => b.textContent), inside: !!e.closest('#headsDlgBody') }}; }}""")
        check("템플릿 수정 — 레벨 표(레벨 · 원본 · 넣을 레터 · 본보기 · 앞 공백) · 적용/취소 · 아직 저장 안 함", ed and ed["mode"] == "edit" and ed["th"] == ["레벨", "원본", "넣을 레터", "본보기(모양)", "앞 공백"] and ed["rows"] == 3
              and ed["acts"] == ["적용", "취소"] and ed["inside"] and CALLS == [], (ed, CALLS))
        check("본보기 목록 — 맨 위 「원본 모양 그대로」 · 그 자리 아래에 붙은 템플릿이 먼저 · 못 쓰는 레벨(괄호 줄)은 없음", ed["likes"][0] == "원본 모양 그대로" and ed["likes"][1].startswith("이 자리 아래 · #2 o › - — L1")
              and len(ed["likes"]) == 1 + 2 + 3 + 1 and not any("[…] › □ › o › - — L1" in t for t in ed["likes"]), ed["likes"])
        page.fill(f"{SEC} .mo-letter >> nth=0", "▪")
        page.select_option(f"{SEC} .mo-grid .mo-like >> nth=1", "1")   # 둘째 넘친 레벨의 본보기 = 「#2 o › - — L2」
        page.fill(f"{SEC} .mo-lead >> nth=2", "4")
        page.click(f"{SEC} .mo-acts button >> nth=0")
        wait_calls(page, 2)
        page.wait_for_function(f"() => {{ const s = document.querySelector('{SEC} .mo-mode'); return s && s.value === 'edit' && !document.querySelector('{SEC} .mo-edit'); }}")
        check("적용 → PUT {key, mode: edit, levels[레터 · 본보기 · 앞 공백]} → 계획을 다시 세움(조용히)", CALLS[0] == ("PUT", {"key": KEY, "mode": "edit", "levels": [{"letter": "▪", "like": None, "lead": None},
              {"letter": None, "like": {"template": "body:o›-", "level": 2}, "lead": None}, {"letter": None, "like": None, "lead": 4}]}) and CALLS[1] == ("PLAN", "fill") and page.evaluate("() => __n.fill") == 1, CALLS)
        info = page.evaluate(INFO)
        check("다시 그린 절 — 처리 = 템플릿 수정 · 레벨마다 넣을 것(레터 · 본보기 · 앞 공백) · 꼬리표 없음", info["mode"] == "edit" and "→ 「▪」 · 제 모양" in info["levels"][0] and "→ 「-」 · 본보기 L2" in info["levels"][1]
              and "레터 그대로 · 제 모양 · 앞 공백 4칸" in info["levels"][2] and info["flags"] == [], info)
        page.screenshot(path=str(OUT / "over_2_edit.png"))

        # ---- 3. 「다른 템플릿」 — 템플릿·시작 레벨 하나 → PUT {mode: template}
        del CALLS[:]
        page.select_option(f"{SEC} .mo-mode", "template")
        tp = page.evaluate(f"() => {{ const e = document.querySelector('{SEC} .mo-edit'); return e && {{ mode: e.dataset.mode, opts: [...e.querySelector('.mo-like').options].map((o) => o.textContent), value: e.querySelector('.mo-like').value }}; }}")
        check("다른 템플릿 — 고르는 목록 하나(「없음」 줄 없이 · 그 자리 아래 템플릿이 기본)", tp and tp["mode"] == "template" and tp["opts"][0].startswith("이 자리 아래 · #2 o › - — L1") and tp["value"] == "0" and CALLS == [], tp)
        page.click(f"{SEC} .mo-acts button >> nth=0")
        wait_calls(page, 2)
        page.wait_for_function(f"() => {{ const s = document.querySelector('{SEC} .mo-mode'); return s && s.value === 'template' && !document.querySelector('{SEC} .mo-edit'); }}")
        info = page.evaluate(INFO)
        check("적용 → PUT {key, mode: template, template{template, level}} · 모자란 레벨은 원본 그대로", CALLS[0] == ("PUT", {"key": KEY, "mode": "template", "template": {"template": "body:o›-", "level": 1}})
              and "→ 「ㅇ」 · 본보기 L1" in info["levels"][0] and "→ 「-」 · 본보기 L2" in info["levels"][1] and "원본 그대로" in info["levels"][2], (CALLS, info))

        # ---- 4. 「취소」 · 서버가 거절(400) · 「덮은 템플릿 그대로」 = 바로 저장
        del CALLS[:]
        page.select_option(f"{SEC} .mo-mode", "edit")
        page.click(f"{SEC} .mo-acts button >> nth=1")
        check("취소 — 편집이 닫히고 저장된 처리(다른 템플릿)로 돌아감 · 요청 없음", page.evaluate(INFO)["edit"] is None and page.evaluate(INFO)["mode"] == "template" and CALLS == [])
        page.select_option(f"{SEC} .mo-mode", "edit")
        page.fill(f"{SEC} .mo-letter >> nth=0", "거절")
        page.click(f"{SEC} .mo-acts button >> nth=0")
        page.wait_for_function("() => /저장하지 못했습니다/.test((document.getElementById('toast') || document.body).textContent)")
        check("서버가 거절하면(400) 알림 · 편집은 열린 채 쓰던 값 그대로 · 계획은 다시 안 세움", page.evaluate(f"() => document.querySelector('{SEC} .mo-letter').value") == "거절" and [c[0] for c in CALLS] == ["PUT"], CALLS)
        del CALLS[:]
        page.select_option(f"{SEC} .mo-mode", "cover")
        wait_calls(page, 2)
        page.wait_for_function(f"() => {{ const s = document.querySelector('{SEC} .mo-mode'); return s && s.value === 'cover' && !document.querySelector('{SEC} .mo-edit'); }}")
        check("덮은 템플릿 그대로 — 고르면 바로 PUT {key, mode: cover} → 계획 다시", CALLS[0] == ("PUT", {"key": KEY, "mode": "cover"}) and CALLS[1] == ("PLAN", "fill") and STORE["cases"] == {}, CALLS)

        # ---- 5. 넣은 뒤 다시 맞추기 — 넣은 줄의 기록이 있을 때만 단추 · 확인 → POST refit → 문서 다시 읽기 · 계획 다시
        del CALLS[:]
        STATE.update(lines=0, applied=2)
        page.evaluate("(p) => { taskFlow.fill = { plan: p, done: null }; fillList(); }", {**fill_plan(), "todo": 0})
        info = page.evaluate(INFO)
        check("다 넣은 뒤의 계획 — 사례는 넣은 줄의 기록으로 보이고 「넣은 줄에 다시 맞추기(2줄)」", info["cap"] == "넘친 개요 레벨 — 1곳 · 넣은 줄 2" and info["count"] == "넣은 줄 2 · 자리 2" and info["refit"] == "넣은 줄에 다시 맞추기(2줄)", info)
        page.click(f"{SEC} [data-mo-refit]")
        wait_calls(page, 2)
        page.wait_for_function("() => __n.reloads === 1 && __n.applied")
        check("다시 맞추기 — 확인 → POST …/merge-over/refit → 편집 상태 반영 · 문서 다시 읽기 · 계획 다시 · 건너뛴 까닭 알림", CALLS[0] == ("REFIT", {}) and CALLS[1] == ("PLAN", "fill")
              and page.evaluate("() => __n.applied.rev") == 9 and "첫머리가 바뀐 줄(사람이 고침) 1" in page.evaluate("() => (document.getElementById('toast') || document.body).textContent"), CALLS)
        STATE.update(lines=3, applied=0)

        # ---- 6. 취합 「넣기 계획」 · 「끌어 넣기」 — 같은 절 · 처리를 고르면 그 목록의 계획을 다시
        del CALLS[:]
        page.evaluate("""(P) => { const g = gt(); g.view = { ...(g.view || {}), parts: [{ work: "p1", name: "기관A_가나대.hwpx", order: 0, orgs: ["가나대"], common: true, state: "todo", counts: { ready: 1 }, todo: 1, reasons: [] }] };
          g.plans.p1 = P; gatherFillList("p1"); }""", gather_plan())
        info = page.evaluate(INFO)
        check("취합 넣기 계획 — 같은 절(2열 gatherFill) · 넣을 것 칸에 「넘친 레벨 1」", info and info["kind"] == "gatherFill" and info["cap"] == "넘친 개요 레벨 — 1곳 · 넣을 줄 3" and not info["modal"]
              and "넘친 레벨 1" in page.evaluate("() => document.querySelector('#headsDlgBody .gt-what').textContent"), info)
        page.select_option(f"{SEC} .mo-mode", "template")
        page.click(f"{SEC} .mo-acts button >> nth=0")
        wait_calls(page, 2)
        page.wait_for_function(f"() => __n.gather === 1 && (document.querySelector('{SEC} .mo-mode') || {{}}).value === 'template'")
        check("취합 — 적용 → PUT → 그 기관 문서의 계획을 다시 세우고 목록을 다시 그림", CALLS[0][0] == "PUT" and CALLS[0][1]["mode"] == "template" and CALLS[1] == ("PLAN", "gather"), CALLS)
        page.click(f"{SEC} .mo-name")
        check("취합 — 사례 이름을 누르면 취합본의 그 자리로", page.evaluate("() => __n.went.slice(-1)[0]") == STATE["at"])
        del CALLS[:]
        page.evaluate("""(P) => { gt().drop = { plan: P, from: "p1", srcId: "s1", afterId: P.after.id, convert: false, busy: false }; gatherDropList(); }""", drop_plan())
        info = page.evaluate(INFO)
        check("끌어 넣기 — 같은 절(2열 gatherDrop) · 다시 맞추기 단추는 없음(끌어 넣기는 넣은 기록이 없다)", info and info["kind"] == "gatherDrop" and info["mode"] == "template" and info["refit"] is None, info)
        page.select_option(f"{SEC} .mo-mode", "cover")
        wait_calls(page, 2)
        page.wait_for_function(f"() => __n.drop === 1 && (document.querySelector('{SEC} .mo-mode') || {{}}).value === 'cover'")
        check("끌어 넣기 — 처리를 바꾸면 같은 자리로 계획을 다시 · 틀 맞춤 켬/끔은 그대로(끔)", CALLS[0] == ("PUT", {"key": KEY, "mode": "cover"}) and CALLS[1] == ("PLAN", "drop")
              and page.evaluate("() => gt().drop.convert === false && document.querySelector('#headsDlgBody [data-gather-convert]').checked === false"), CALLS)

        # ---- 7. 좁은 열(2열 최소 폭)에서도 넘치지 않는다
        page.set_viewport_size({"width": 1100, "height": 800})
        page.evaluate("(p) => { taskFlow.fill = { plan: p, done: null }; fillList(); }", fill_plan())
        page.select_option(f"{SEC} .mo-mode", "edit")
        narrow = page.evaluate(f"() => {{ const s = document.querySelector('{SEC}'), b = document.getElementById('headsDlgBody'); return {{ sec: s.scrollWidth - s.clientWidth, body: b.scrollWidth - b.clientWidth, w: b.clientWidth }}; }}")
        check("좁은 창 — 편집을 편 절이 열 폭을 넘지 않는다(가로 스크롤 없음)", narrow["sec"] <= 1 and narrow["body"] <= 1, narrow)
        page.screenshot(path=str(OUT / "over_3_narrow.png"))
        check("화면 오류 없음", not errors, errors[:5])
        browser.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'FAIL ' + str(len(fails)) if fails else 'ALL PASS'}")
sys.exit(1 if fails else 0)

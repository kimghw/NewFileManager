"""헤딩 추출 진행 줄의 「조정」 층(템플릿 조정 · 서식 조정 · 모두 반영) 화면 확인 — 임시 서버(임시 작업 폴더 · PDF 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_adjust_ui.py <그림·임시 폴더> [--port 18195]

서식 정리 에이전트(LLM)는 **기본 스킬의 기준대로 답하는 가짜**로 바꿔 끼운다(임시 서버 안에서만 — 레터가 대표와 같은 갈래는 맞추고, 다른 갈래는 레터마다 떼고, 못 떼면 그대로):
그래서 계획 받기 · 반영의 끝점은 진짜다. 연구개발계획서_양식.hwpx 를 올려 2·3단계(스크립트)를 돌린 뒤 헤딩 탭 →
① 진행 줄이 세 층(스크립트 · LLM · 조정) · 조정 = 「템플릿 조정 ○」·「서식 조정 ○」 · 헤딩 판정(LLM)을 안 거친 문서의 행동 칸은 **「LLM 판정」**(「계획 받기」 가 아니다 — 2026-11-17: 누르면 돌 것을 보인 확인 창 뒤에
「LLM 검증·보완」 이어 돌리기 — 임시 서버에는 헤딩 LLM 이 없어 그 함수만 바꿔 끼워 불렸는지 본다) · 판정을 거친 문서(화면 함수 tpbJudged 를 바꿔 끼워 흉내)에서만 「계획 받기」
② 「계획 받기」(확인 창) → 서식 정리 계획만 돌고(헤딩 · 표 LLM 은 안 돎) 두 칸이 「계획 받음 · n줄」 + 「모두 반영」
③ 칸을 누르면 「LLM 이 바꾼 것」 열의 「서식 계획」 절 ④ 「모두 반영」 → 실행 취소 1 · 모든 템플릿 · 두 칸 ✓ · 계획은 반영함 ⑤ 실행 취소 한 번이면 문서가 처음 그대로
⑥ 좁은 패널(320 · 388 · 480px)에서 세 줄 · 가로 넘침 없음 · 콘솔 오류 없음."""
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
ap.add_argument("--port", type=int, default=18195)
args = ap.parse_args()
OUT = Path(args.out).resolve()
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"

OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
# 임시 서버 — 서식 정리 에이전트의 LLM 호출만 가짜로(그 밖의 호출은 「꺼짐」 그대로). 가짜는 자료(JSON)를 읽어 기본 스킬의 기준(레터)대로 답한다
LAUNCH = OUT / "fake_llm_server.py"
LAUNCH.write_text('''import json, sys
import uvicorn
from app import llm

_real = llm.call


def fake(schema, content, what, **kw):
    if what != "tpl-agent":
        return _real(schema, content, what, **kw)
    mat = json.loads(content.split("## 자료 (JSON)\\n```json\\n", 1)[1].rsplit("\\n```", 1)[0])["material"]
    levels = []
    for lv in mat["levels"]:
        gs = lv["groups"]
        rep = next((g for g in gs if g.get("currentRep")), gs[0])
        match, keep, cut = [], [], {}
        for g in gs:
            if g is rep:
                continue
            letter = next((d[2] for d in g.get("differsFromRep") or [] if d[0] == "레터"), None)
            if letter is None:
                match.append(g["id"])
            elif g.get("cannotSplit"):
                keep.append({"group": g["id"], "why": "레터가 다르지만 뗄 수 없음"})
            else:
                cut.setdefault(letter, []).append(g)
        split = []
        for letter, rows in cut.items():
            rows.sort(key=lambda g: -g["lines"])
            split.append({"rep": rows[0]["id"], "match": [g["id"] for g in rows[1:]], "why": f"레터 「{letter}」"})
        levels.append({"level": lv["level"], "rep": rep["id"], "match": match, "keep": keep, "split": split, "why": "가짜 — 기준대로"})
    return {"data": {"summary": "가짜 계획 — 레터가 같으면 맞추고 다르면 뗌", "levels": levels}, "backend": "api", "ms": 5, "costUsd": 0.0, "error": None,
            "model": kw.get("model"), "effort": kw.get("effort")}


llm.call = fake
uvicorn.run("app.server:app", host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
''', encoding="utf-8")
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "PYTHONUTF8": "1", "PYTHONPATH": str(ROOT)}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", str(LAUNCH), str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:700] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def run_stage(wid, stage):
    r = requests.post(f"{base}/api/docs/{wid}/headings", json={"stage": stage, "llm": False}, timeout=30)
    r.raise_for_status()
    for _ in range(600):
        j = requests.get(f"{base}/api/docs/{wid}/headings", timeout=30).json()
        if not (j.get("job") and j["job"]["status"] == "running"):
            return j
        time.sleep(.5)
    raise RuntimeError(f"{stage}단계가 끝나지 않음")


def formats(wid):
    v = requests.get(f"{base}/api/docs/{wid}/analysis", timeout=60).json()
    return next(i for i in v["items"] if i["key"] == "formats"), v


SNAP = """() => {
  const q = (s) => document.querySelector(s), pane = q('#paneHeads'), box = q('#headsOverview .hprog');
  if (!box) return null;
  const cells = [...box.querySelectorAll('.hprog-step')].map((b) => { const r = b.getBoundingClientRect(), cnt = b.querySelector('.hprog-count');
    return { key: b.dataset.tpb || null, state: b.dataset.state, text: [b.querySelector('.hprog-text').textContent, cnt && cnt.innerText].filter(Boolean).join(' · '),
      title: b.title, hidden: b.hidden, off: b.disabled, go: b.classList.contains('tpb-go'), left: Math.round(r.left), top: Math.round(r.top), h: Math.round(r.height), right: r.right }; });
  return { cells, layers: [...box.querySelectorAll('.hprog-layer')].map((e) => e.textContent), overflowX: pane.scrollWidth - pane.clientWidth,
    paneRight: pane.getBoundingClientRect().right, boxH: Math.round(box.getBoundingClientRect().height), undo: state.undo, rev: state.serverRev };
}"""
WAIT_ADJ = "(want) => { const b = document.querySelector('#headsOverview .hprog [data-tpb=\"act\"]'); return !!b && (b.hidden ? '' : b.querySelector('.hprog-text').textContent) === want; }"

try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    r = requests.post(f"{base}/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}, timeout=120)
    r.raise_for_status()
    wid = r.json()["docId"]
    run_stage(wid, 2)
    run_stage(wid, 3)
    f0, _ = formats(wid)
    need = f0["llm"]["need"]
    check("분석 상태: 정리할 템플릿이 있고 계획은 아직 없음", need >= 1 and f0["llm"]["planned"] == 0 and (f0["llm"]["change"], f0["llm"]["moved"]) == (0, 0), f0["llm"])
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        asked = []
        page.on("dialog", lambda d: (asked.append(d.message), d.accept()))
        posts = []
        page.on("request", lambda q: posts.append(q.url.split("/api/docs/")[-1].split("/", 1)[-1]) if q.method == "POST" and "/api/docs/" in q.url else None)
        page.goto(f"{base}/#w={wid}")
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=240000)
        page.click("#tabHeads")
        page.wait_for_function("() => typeof heads !== 'undefined' && heads.view && heads.view.stage3 && !(heads.view.job && heads.view.job.status === 'running') && document.querySelector('#headsOverview .hprog [data-tpb]')", timeout=120000)
        page.wait_for_function(WAIT_ADJ, arg="LLM 판정", timeout=30000)

        # ---- ① 세 층 — 조정: 계획 없음 · 헤딩 판정(LLM)을 안 거침 → 행동 칸은 「LLM 판정」(2026-11-17 사용자 「LLM 판정버튼이 없고 계획받기 버튼을 누르도록 되어 있었어」 — 전에는 「계획 받기」)
        m = page.evaluate(SNAP)
        c = m["cells"]
        check("진행 줄 세 층(스크립트 · LLM · 조정) · 칸 아홉", m["layers"] == ["스크립트", "LLM", "조정"] and len(c) == 9, (m["layers"], len(c)))
        check("조정 층: 「템플릿 조정」 ○ · 「서식 조정」 ○ · 헤딩 판정(LLM) 전의 행동 칸은 「LLM 판정」(「계획 받기」 가 아니다) · 두 칸 도움말에 「헤딩 판정(LLM)을 아직 안 했습니다」",
              [(x["key"], x["text"], x["state"]) for x in c[6:]] == [("tpl", "템플릿 조정", "none"), ("fmt", "서식 조정", "none"), ("act", "LLM 판정", "act")]
              and not c[8]["hidden"] and not c[8]["off"] and not c[8]["go"] and "헤딩 판정(LLM)을 아직 안 했습니다" in c[8]["title"]
              and all("헤딩 판정(LLM)을 아직 안 했습니다" in x["title"] for x in c[6:8]), c[6:])
        check("조정 칸이 LLM 칸 바로 아래(같은 왼쪽 · 아래 줄) · 칸 22px · 진행 줄 세 줄(≤ 76px)", all(c[i + 3]["left"] == c[i + 6]["left"] and c[i + 6]["top"] > c[i + 3]["top"] for i in range(3))
              and all(x["h"] == 22 for x in c) and m["boxH"] <= 76, ([(x["left"], x["top"], x["h"]) for x in c[3:]], m["boxH"]))
        check("칸 title: 템플릿 조정 = 레터가 다른 줄을 종속 템플릿으로 · 서식 조정 = 대표 서식에", "레터가 대표와 다른 줄" in c[6]["title"] and "서식 종속 템플릿" in c[6]["title"] and "대표 서식에 맞춥니다" in c[7]["title"], (c[6]["title"][:80], c[7]["title"][:80]))
        page.locator("#headsOverview").screenshot(path=str(OUT / "1_no_plan.png"))

        # ---- ①-1 LLM 연결이 없는 서버(이 임시 서버)에서 「LLM 판정」 — 막다른 길이 아니다: 스크립트가 맞출 것(자리 맞춤)이 있으면 그것만 반영할지 「모두 반영」 의 확인 창으로 넘긴다(여기서는 그 함수만 바꿔 끼워 넘어온 것을 본다)
        page.evaluate("() => { window.__apply0 = tpbApply; window.__applyOpt = null; window.tpbApply = async (o) => { window.__applyOpt = o || {}; return null; }; }")
        page.click('#headsOverview .hprog [data-tpb="act"]')
        page.wait_for_function("() => window.__applyOpt !== null", timeout=30000)
        off = page.evaluate("() => ({ note: window.__applyOpt.note || '', toast: document.getElementById('toast').textContent })")
        check("LLM 연결이 없으면: 「LLM 연결이 없습니다」 알림 + 스크립트 반영만 묻는 길로(확인 창 맨 앞 한 줄) · 요청은 안 나감", "LLM 연결이 없어 LLM 판정은 돌리지 못합니다" in off["note"] and "LLM 연결이 없습니다" in off["toast"]
              and not asked and "analysis/llm" not in posts and "outline/agent/apply" not in posts, (off, asked, posts))
        page.evaluate("() => { window.tpbApply = window.__apply0; }")

        # ---- ①-2 「LLM 판정」 — 돌 것을 보인 확인 창 뒤에 「LLM 검증·보완」 이어 돌리기(doc_status.js dsLlmRun)를 부른다.
        #      임시 서버는 LLM 이 꺼져 있어 연결 확인(headsLlmReady)과 그 함수만 바꿔 끼운다 — 요청은 안 나간다
        page.evaluate("() => { window.__keep = { ready: headsLlmReady, run: dsLlmRun }; window.__judge = 0; window.headsLlmReady = async () => ({ available: true });"
                      " window.dsLlmRun = async () => { window.__judge += 1; return true; }; }")
        page.click('#headsOverview .hprog [data-tpb="act"]')
        page.wait_for_function("() => window.__judge === 1", timeout=30000)
        check("「LLM 판정」: 확인 창에 돌 것(헤딩 · 표 · 서식 정리 계획) · 유료 · 문서는 안 바뀜 → LLM 검증·보완 이어 돌리기 한 번(서식 정리 계획만 부르지 않는다)",
              len(asked) == 1 and all(w in asked[0] for w in ("돌 것", "헤딩 그래프(LLM)", "표 구조(LLM)", "서식 정리 계획", "유료", "문서는 바뀌지 않습니다")) and "analysis/llm" not in posts, (asked, posts))
        page.evaluate("() => { window.headsLlmReady = window.__keep.ready; window.dsLlmRun = window.__keep.run; }")
        asked.clear()

        # ---- ①-3 헤딩 판정(LLM)을 거친 뒤에만 「계획 받기」 — 임시 서버에는 헤딩 LLM 이 없어 「거쳤다」 만 흉내 낸다(tpl_plan_bar.js tpbJudged — 계획 받기 · 반영의 끝점은 진짜)
        page.evaluate("() => { window.__judged0 = tpbJudged; window.tpbJudged = () => true; tplPlanBarSync(true); }")
        page.wait_for_function(WAIT_ADJ, arg="계획 받기", timeout=10000)
        c = page.evaluate(SNAP)["cells"]
        check("헤딩 판정(LLM)을 거친 문서: 행동 칸 「계획 받기」 · 두 칸 도움말에 판정 안내 없음", (c[8]["text"], c[8]["state"]) == ("계획 받기", "act") and not c[8]["hidden"] and not c[8]["off"] and not c[8]["go"]
              and not any("헤딩 판정(LLM)을 아직 안 했습니다" in x["title"] for x in c[6:8]), c[6:])

        # ---- ② 「계획 받기」 — 서식 정리 계획만(유료 확인 창) → 계획 받음
        page.click('#headsOverview .hprog [data-tpb="act"]')
        page.wait_for_function(WAIT_ADJ, arg="모두 반영", timeout=120000)
        f1, v1 = formats(wid)
        check("확인 창: 유료 · 문서는 안 바뀜 · 템플릿 수", len(asked) == 1 and "유료" in asked[0] and "문서는 바뀌지 않습니다" in asked[0] and str(need) in asked[0], asked)
        check("서식 정리 계획만 돎(이어 돌리기 formats — 헤딩 · 표 LLM 은 안 돎)", [(s["key"], s["status"]) for s in v1["chain"]["steps"]] == [("formats", "ok")] and v1["chain"]["name"] == "서식 정리 계획"
              and "analysis/llm" in posts and "headings" not in posts, (v1["chain"], posts))
        L = f1["llm"]
        check("분석 상태: 모든 템플릿의 계획 받음 · 바뀔 줄 수가 있음", (L["planned"], L["stale"]) == (need, 0) and L["change"] + L["moved"] > 0, L)
        m = page.evaluate(SNAP)
        c = m["cells"]
        # 확실한 종속 제안(한 자리에만 매달린 템플릿 — 분석 상태 템플릿 항목의 hints 가운데 sure)은 「모두 반영」 이 저절로 넣는다: 칸에 「종속 n」 이 붙는다(spec_hwpx_웹편집 ② §8-2 「종속 제안」)
        sure = sum(1 for h in next(i for i in v1["items"] if i["key"] == "templates").get("hints") or [] if h.get("sure"))
        rel = f" · 종속 {sure}" if sure else ""
        want_t = ("템플릿 조정 · %s줄%s" % (format(L["moved"], ","), rel), "plan") if L["moved"] else (("템플릿 조정" + rel, "plan") if sure else ("템플릿 조정", "skip"))
        place = f1.get("place", 0)   # 자리 맞춤이 남은 줄(레터 뒤 묶음 빈칸 · 둘째 줄 = 글 시작 — spec_hwpx_웹편집 ② §8-8): 「서식 조정」 칸의 수 = 맞출 줄 + 이 수
        want_f = ("서식 조정 · %s줄" % format(L["change"] + place, ","), "plan") if L["change"] + place else ("서식 조정", "skip")
        check("분석 상태: 자리 맞춤이 남은 줄이 있다(양식은 내어쓰기가 접두 폭과 다르거나 없다) · 「모두 반영」 title 에 그 수", place > 0 and f"지금 {place:,}줄" in c[8]["title"] and "묶음 빈칸" in c[8]["title"], (place, c[8]["title"]))
        check("두 칸 = 계획의 수(뗄 줄 · 맞출 줄) · 「모두 반영」 은 보라 단추", (c[6]["text"], c[6]["state"]) == want_t and (c[7]["text"], c[7]["state"]) == want_f
              and c[8]["text"] == "모두 반영" and c[8]["go"] and not c[8]["off"], (c[6:], want_t, want_f))
        check("「모두 반영」 title: 맞출 줄 · 뗄 줄 · 실행 취소 한 번", f"대표에 맞출 줄 {L['change']:,}개" in c[8]["title"] and f"뗄 줄 {L['moved']:,}개" in c[8]["title"] and "「실행 취소」 한 번" in c[8]["title"], c[8]["title"])
        page.locator("#headsOverview").screenshot(path=str(OUT / "2_planned.png"))

        # ---- ③ 칸을 누르면 계획 보기(「LLM 이 바꾼 것」 열의 「서식 계획」)
        page.click('#headsOverview .hprog [data-tpb="fmt"]')
        page.wait_for_function("() => document.querySelector('#headsDlg[data-kind=\"llmDiff\"]:not([hidden]) .lld-sec[data-stage=\"fmt\"] .lld-item')", timeout=20000)
        d = page.evaluate("() => ({ title: document.getElementById('headsDlgTitle').textContent, plans: document.querySelectorAll('#headsDlgBody .lld-sec[data-stage=\"fmt\"] .lld-item').length, "
                          "lead: document.querySelector('#headsDlgBody .lld-sec[data-stage=\"fmt\"] .lld-sum').textContent, btn: !!document.querySelector('#headsDlgBody .tpb-cell, #headsDlgBody [data-tpb]') })")
        check("서식 계획 절: 템플릿마다 계획 · 안내 글이 「조정」 의 「모두 반영」 을 가리킴 · 그 열에는 반영 단추 없음", d["title"] == "LLM 이 바꾼 것" and d["plans"] == need and "「조정」 의 「모두 반영」" in d["lead"] and not d["btn"], d)
        page.screenshot(path=str(OUT / "3_plans_column.png"))
        page.evaluate("() => headsColClose(true)")

        # ---- ④ 「모두 반영」 — 모든 템플릿을 한 번에(실행 취소 1)
        undo0, rev0 = m["undo"], m["rev"]
        others0 = f1["others"]
        page.click('#headsOverview .hprog [data-tpb="act"]')
        page.wait_for_function("(u) => state.undo === u + 1 && !state.busy", arg=undo0, timeout=120000)
        page.wait_for_function("() => { const b = document.querySelector('#headsOverview .hprog [data-tpb=\"tpl\"]'); return b && b.dataset.state === 'llm'; }", timeout=60000)
        f2, _ = formats(wid)
        m = page.evaluate(SNAP)
        c = m["cells"]
        check("반영: 실행 취소 1 · 문서 차례 +1 · POST …/outline/agent/apply 한 번", m["undo"] == undo0 + 1 and m["rev"] == rev0 + 1 and posts.count("outline/agent/apply") == 1, (m["undo"], undo0, m["rev"], rev0, posts))
        check("계획은 모두 반영함(done = 계획 수 — 다 맞춘 템플릿은 「정리할 템플릿」 에서 빠진다) · 대표와 다른 줄이 줄어듦", (f2["llm"]["done"], f2["llm"]["planned"]) == (need, 0) and f2["others"] < others0,
              ({k: f2["llm"][k] for k in ("need", "planned", "applied", "done", "stale")}, f2["others"], others0))
        left = [x for x in f2["llm"]["list"] if x["state"] in ("none", "stale")]   # 반영으로 새로 생긴 서식 종속 템플릿에 아직 서식이 갈린 레벨이 있으면 「나머지 받기」
        check("두 칸 ✓(반영함) · 행동 칸은 감춤(두 칸은 제자리 — 남은 템플릿이 있으면 「나머지 받기」)", [(x["text"], x["state"]) for x in c[6:8]] == [("템플릿 조정", "llm"), ("서식 조정", "llm")]
              and ((c[8]["text"] == "나머지 받기") if left else c[8]["hidden"]) and c[6]["left"] == c[3]["left"] and c[7]["left"] == c[4]["left"],
              ([(x["text"], x["state"], x["hidden"], x["left"]) for x in c[6:]], left))
        toast = page.evaluate("() => document.getElementById('toast').textContent")
        # 헤딩 판정(LLM)을 안 거친 채 반영한 문서(흉내를 풀면 이 문서가 그렇다 — 2026-11-17 사용자 그림: LLM ○ · 조정 ✓) — 두 칸은 ✓ 그대로이고 행동 칸은 감추지 않고 「LLM 판정」(빠진 단계가 남은 일로 보인다)
        j = page.evaluate("""() => { window.tpbJudged = window.__judged0; tplPlanBarSync(true);
          const cell = (k) => { const b = document.querySelector(`#headsOverview .hprog [data-tpb="${k}"]`); return { state: b.dataset.state, text: b.hidden ? '' : b.querySelector('.hprog-text').textContent, off: b.disabled }; };
          const out = { tpl: cell('tpl'), fmt: cell('fmt'), act: cell('act') };
          window.tpbJudged = () => true; tplPlanBarSync(true);
          return out; }""")
        check("판정을 안 거친 채 반영한 문서: 두 칸 ✓ 그대로 · 행동 칸은 「LLM 판정」", (j["tpl"]["state"], j["fmt"]["state"]) == ("llm", "llm") and (j["act"]["text"], j["act"]["off"]) == ("LLM 판정", False), j)
        check("알림: 템플릿 수 · 맞춘 줄 · 자리 맞춤 줄 · 실행 취소 한 번", "계획대로 반영했습니다" in toast and "「실행 취소」 한 번" in toast and "자리 맞춤" in toast and "묶음 빈칸" in toast, toast)
        check("반영 뒤: 자리 맞춤이 남은 줄 0 · 문서의 개요 줄 레터 뒤가 묶음 빈칸(U+2002)", f2.get("place") == 0
              and page.evaluate("() => [...document.querySelectorAll('#doc .para')].filter((p) => /^ *[-ㅇo□]\u2002/.test(p.textContent)).length") > 20, f2.get("place"))
        if L["moved"]:  # 오버레이 요약을 다시 읽을 때까지(tpbApply 의 outlineLoad)
            page.wait_for_function("() => Object.values((heads.outline || {}).templates || {}).some((t) => t.vari)", timeout=30000)
        tpl = page.evaluate("() => Object.values((heads.outline || {}).templates || {}).filter((t) => t.vari).map((t) => t.no)")
        check("템플릿 조정이 있었으면 서식 종속 템플릿이 생김(없었으면 없음)", bool(tpl) == bool(L["moved"]), (tpl, L["moved"]))
        if sure:
            page.wait_for_function("() => Object.values((heads.outline || {}).templates || {}).some((t) => t.comp)", timeout=30000)
        comp = page.evaluate("() => Object.values((heads.outline || {}).templates || {}).filter((t) => t.comp).map((t) => t.no)")
        sure2 = sum(1 for h in next(i for i in formats(wid)[1]["items"] if i["key"] == "templates").get("hints") or [] if h.get("sure"))
        check(f"확실한 종속 {sure}개를 같은 반영에서 넣음 — 종속 템플릿이 그 수 · 남은 확실한 제안 0 · 알림에 「템플릿 종속」(실행 취소는 그대로 1)", len(comp) == sure and sure2 == 0 and (not sure or "템플릿 종속" in toast), (comp, sure, sure2, toast))
        page.locator("#paneHeads").screenshot(path=str(OUT / "4_applied.png"))

        # ---- 조정 줄 — 반영한 계획이 남긴 줄 · 대표만 바꾸는 계획(2026-11-16 astra: 답이 없던 줄이 ✓ 뒤로 사라졌고, 맞출 줄이 0 이면 대표 변경이 있어도 「모두 반영」 이 안 떴다).
        #      분석 상태 사본에 그 수를 흉내 낸 뒤 되돌린다 — 요청은 안 나간다
        syn = page.evaluate("""() => {
          const f = dsState.main.items.find((i) => i.key === 'formats'), keep = JSON.stringify(f.llm), out = {};
          const cell = (k) => { const b = document.querySelector(`#headsOverview .hprog [data-tpb="${k}"]`), n = b.querySelector('.hprog-count');
            return { state: b.dataset.state, text: b.hidden ? '' : [b.querySelector('.hprog-text').textContent, n && n.innerText].filter(Boolean).join(' · '), title: b.title, hidden: b.hidden, label: b.getAttribute('aria-label') }; };
          Object.assign(f.llm, { state: 'done', need: 1, planned: 0, applied: 1, stale: 0, done: 1, change: 0, moved: 0, reps: 0, left: { kept: 3, unanswered: 7 }, list: [{ tpl: '3', no: '3', state: 'applied', left: { kept: 3, unanswered: 7 } }] });
          tplPlanBarSync(true); out.left = { tpl: cell('tpl'), fmt: cell('fmt') };
          f.llm.left = { kept: 3, unanswered: 0 };
          tplPlanBarSync(true); out.kept = { fmt: cell('fmt') };
          Object.assign(f.llm, { planned: 1, applied: 0, done: 0, reps: 1, kept: 0, unanswered: 0, omitted: 0, left: { kept: 0, unanswered: 0 }, list: [{ tpl: '3', no: '3', state: 'planned', change: 0, moved: 0, reps: 1, at: 1 }] });
          tplPlanBarSync(true); out.rep = { fmt: cell('fmt'), act: cell('act') };
          f.llm = JSON.parse(keep); tplPlanBarSync(true);
          return out;
        }""")
        check("조정 줄: 반영한 계획이 답 없이 남긴 줄이 있으면 「서식 조정」 은 ✓ 가 아니라 「답 없음 7줄」(도움말에 그대로 둔 줄 · 답 없는 줄) · 「템플릿 조정」 은 ✓ 그대로",
              (syn["left"]["fmt"]["state"], syn["left"]["fmt"]["text"]) == ("left", "서식 조정 · 답 없음 7줄") and "답이 없어 안 바꾼 줄 7" in syn["left"]["fmt"]["title"]
              and "에이전트가 그대로 둔 줄 3" in syn["left"]["fmt"]["title"] and syn["left"]["tpl"]["state"] == "llm" and "답이 없어 안 바꾼 줄이 남음" in syn["left"]["fmt"]["label"], syn["left"])
        check("조정 줄: 에이전트가 까닭을 적고 그대로 둔 줄만 남았으면 ✓ 그대로 — 도움말에 그 수", syn["kept"]["fmt"]["state"] == "llm" and "에이전트가 그대로 둔 줄 3" in syn["kept"]["fmt"]["title"], syn["kept"])
        check("조정 줄: 대표만 바꾸는 계획(맞출 줄 0 · 대표 변경 1) — 「서식 조정 · 대표 1」 · 「모두 반영」 이 켜짐",
              (syn["rep"]["fmt"]["state"], syn["rep"]["fmt"]["text"]) == ("plan", "서식 조정 · 대표 1") and not syn["rep"]["act"]["hidden"] and syn["rep"]["act"]["text"] == "모두 반영", syn["rep"])

        # 받아 둔 계획 없이 스크립트가 맞출 것(자리 맞춤)만 남은 문서 — 헤딩 판정(LLM)을 거쳤으면 「모두 반영」, 안 거쳤으면 그보다 「LLM 판정」 이 먼저(칸의 「n줄」 은 그대로 · 2026-11-17: 행동 칸은 차례를 따른다)
        seq = page.evaluate("""() => {
          const f = dsState.main.items.find((i) => i.key === 'formats'), keep = JSON.stringify(f.llm), place0 = f.place, out = {};
          const cell = (k) => { const b = document.querySelector(`#headsOverview .hprog [data-tpb="${k}"]`), n = b.querySelector('.hprog-count');
            return { state: b.dataset.state, text: b.hidden ? '' : [b.querySelector('.hprog-text').textContent, n && n.innerText].filter(Boolean).join(' · '), title: b.title }; };
          Object.assign(f.llm, { state: 'done', need: 0, planned: 0, applied: 0, stale: 0, done: 1, change: 0, moved: 0, reps: 0, left: { kept: 0, unanswered: 0 }, list: [] });
          f.place = 5;
          tplPlanBarSync(true); out.judged = { fmt: cell('fmt'), act: cell('act') };
          window.tpbJudged = window.__judged0; tplPlanBarSync(true); out.not = { fmt: cell('fmt'), act: cell('act') };
          window.tpbJudged = () => true;
          f.llm = JSON.parse(keep); f.place = place0; tplPlanBarSync(true);
          return out;
        }""")
        check("자리 맞춤만 남은 문서: 판정을 거쳤으면 「서식 조정 · 5줄」 + 「모두 반영」 · 안 거쳤으면 칸은 그대로 「5줄」 이고 행동 칸은 「LLM 판정」(도움말에 자리 맞춤 5줄은 판정 뒤 같이)",
              (seq["judged"]["fmt"]["text"], seq["judged"]["act"]["text"]) == ("서식 조정 · 5줄", "모두 반영") and (seq["not"]["fmt"]["text"], seq["not"]["act"]["text"]) == ("서식 조정 · 5줄", "LLM 판정")
              and "자리 맞춤 5줄" in seq["not"]["act"]["title"], seq)

        # ---- ⑤ 실행 취소 한 번 — 문서가 처음 그대로
        r = requests.post(f"{base}/api/docs/{wid}/undo", timeout=120)
        same = requests.get(f"{base}/api/docs/{wid}/download", timeout=120).content == PLAN.read_bytes()
        f3, v3 = formats(wid)
        sure3 = sum(1 for h in next(i for i in v3["items"] if i["key"] == "templates").get("hints") or [] if h.get("sure"))
        check("실행 취소 한 번으로 모든 템플릿이 되돌아감(내려받은 파일 = 올린 파일) · 대표와 다른 줄 수도 처음 값 · 넣었던 종속도 풀려 다시 제안", r.ok and same and f3["others"] == others0 and sure3 == sure, (r.status_code, same, f3["others"], others0, sure3, sure))
        L3 = f3["llm"]  # 「반영함」 은 그 반영이 문서에 남아 있을 때만 — 되돌리면 줄이 계획을 받을 때 그대로라(줄 지문이 같다) 계획은 다시 「받음」 이다(다시 받지 않는다: spec_hwpx_웹편집 ② §8-4 「계획은 줄 지문에」)
        check("반영을 되돌리면 분석 상태도 되돌아간다 — 반영함 0 · 받았던 계획은 그대로 다시 쓸 수 있다(받음 · 옛 계획 0)", (L3["applied"], L3["done"], L3["stale"]) == (0, 0, 0) and (L3["planned"], L3["need"]) == (need, need)
              and (L3["change"], L3["moved"]) == (L["change"], L["moved"]), {k: L3[k] for k in ("need", "planned", "applied", "done", "stale", "change", "moved")})

        # ---- ⑥ 좁은 패널
        page.reload()
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=240000)
        page.click("#tabHeads")
        page.wait_for_function("() => document.querySelector('#headsOverview .hprog [data-tpb]') && typeof dsState === 'object' && dsState.main", timeout=120000)
        page.wait_for_function("() => { const b = document.querySelector('#headsOverview .hprog [data-tpb=\"act\"]'); return b && !b.hidden && !!b.textContent; }", timeout=30000)
        c = page.evaluate(SNAP)["cells"]
        check("되돌린 뒤의 조정 층 — 두 칸은 ✓ 가 아니고 받아 둔 계획의 수 그대로 · 행동 칸은 「모두 반영」(다시 받지 않는다 — 판정을 안 거친 그래프의 계획이라는 한 줄이 도움말에)", [(x["text"], x["state"]) for x in c[6:8]] == [want_t, want_f]
              and c[8]["text"] == "모두 반영" and c[8]["go"] and not c[8]["hidden"] and "헤딩 판정(LLM)을 안 거친" in c[8]["title"], [(x["text"], x["state"], x["hidden"]) for x in c[6:]] + [c[8]["title"][-120:]])
        for w in (320, 388, 480):
            page.evaluate("(w) => { document.getElementById('panel').style.setProperty('--panel', w + 'px'); heads.summaryKey = null; headsResultsSummary(heads.view); }", w)
            page.wait_for_timeout(200)
            m = page.evaluate(SNAP)
            check(f"[{w}] 진행 줄 세 줄 · 칸이 패널 밖으로 안 나감 · 가로 넘침 없음", m["boxH"] <= 76 and m["overflowX"] <= 0 and max(x["right"] for x in m["cells"]) <= m["paneRight"] + .5 and len(m["cells"]) == 9,
                  (m["boxH"], m["overflowX"], [x["text"] for x in m["cells"]]))
            page.locator("#paneHeads").screenshot(path=str(OUT / f"6_panel_{w}.png"))
        check("콘솔·페이지 오류 없음", not errors, " | ".join(errors[:3]))
        browser.close()
except Exception as e:  # noqa: BLE001
    check(f"실행 오류: {type(e).__name__}", False, e)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()

print(f"\n{'모두 통과' if not fails else '실패 ' + str(len(fails))}")
sys.exit(1 if fails else 0)

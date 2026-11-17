"""헤딩 추출 진행 줄(spec_헤딩_추출 ② §7 「진행 줄」) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_heading_progress_ui.py <그림·임시 폴더> [--port 18178]

연구개발계획서_양식.hwpx 를 올려 2·3단계(스크립트)를 돌린 뒤 헤딩 탭 → 요약 둘째 줄이 두 층 × 세 칸(스크립트 「문단·라벨 ✓ · 헤딩 그래프 ✓ · 표 구조 ✓」 /
LLM 「규칙 보강 · 27묶음 ○ · 헤딩 판정 ○ · 표 판정 ○」) + 셋째 층 「조정」(템플릿 조정 · 서식 조정 — tools/smoke_adjust_ui.py 가 자세히) · LLM 칸이 그 단계의 스크립트 칸 바로 아래 · 칸 높이 22px · 1단계 카드의 「LLM 규칙 보강 — 안 함」 ·
규칙 보강 칸을 누르면 추출·설정 1단계 탭 · 요약 사본에 흉내 낸 상태(규칙 보강 끝남 · 헤딩 판정 LLM · 규칙 보강 도는 중 · 실패)를 넣어 칸의 표시 ·
LLM ✓ 칸을 누르면 문서 옆 열 「LLM 이 바꾼 것」(절 여섯) ·
좁은 패널(320 · 388 · 480px)에서 가로 넘침 없음 · 콘솔 오류 없음. 문서는 고치지 않는다(흉내는 화면 함수에 넘긴 사본만)."""
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
ap.add_argument("--port", type=int, default=18178)
args = ap.parse_args()
OUT = Path(args.out).resolve()
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"

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


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:600] if detail != "" and not ok else ""), flush=True)
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


SNAP = """() => {
  const q = (s) => document.querySelector(s), pane = q('#paneHeads'), box = q('#headsOverview .hprog');
  if (!box) return null;
  const cells = [...box.querySelectorAll('.hprog-step')].map((b) => { const r = b.getBoundingClientRect();
    const cnt = b.querySelector('.hprog-count'), cr = cnt && cnt.getBoundingClientRect();
    return { state: b.dataset.state, text: [b.querySelector('.hprog-text').textContent, cnt && cnt.textContent].filter(Boolean).join(' · '), count: cnt ? cnt.innerText : null, countIn: !cnt || cr.right <= r.right - 2, title: b.title, left: Math.round(r.left), top: Math.round(r.top), h: Math.round(r.height), right: r.right }; });
  const layers = [...box.querySelectorAll('.hprog-layer')].map((e) => e.textContent);
  const dd = [...document.querySelectorAll('#heads1 .hdl dt')].find((d) => d.textContent === 'LLM 규칙 보강');
  return { cells, layers, rule1: dd ? dd.nextElementSibling.textContent : null, srcLine: !!q('#headsOverview .src-line'),
    overflowX: pane.scrollWidth - pane.clientWidth, paneRight: pane.getBoundingClientRect().right, boxH: Math.round(box.getBoundingClientRect().height) };
}"""
FAKE = """(kind) => { // 요약 사본에 흉내 낸 상태를 넣어 진행 줄만 다시 그린다(서버·문서는 그대로)
  const r = JSON.parse(JSON.stringify(heads.view)), now = Date.now() / 1000;
  if (kind === 'rulesDone') r.rules = { run: 99, at: now - 60, asked: true, groups: 27, saved: 24, kept: 2, rejected: 1, unsure: 0, error: null, costUsd: 0.23 };
  if (kind === 'judged') { r.stage2.llm = { ...r.stage2.llm, requested: true, fallback: false, calls: 9, failed: 0, seconds: 198, costUsd: 3.1 }; r.stage2.meta.at = now - 120; }
  if (kind === 'rulesRunning') r.job = { stage: 2, llm: true, first: false, status: 'running', started: now - 5, steps: [{ name: '1단계 다시 — 못 맞춤·충돌 LLM 규칙 보강', status: 'running' }, { name: '추출', status: 'ok' }, { name: 'LLM 규칙 보강', status: 'running' }] };
  if (kind === 'graphRunning') r.job = { stage: 2, llm: true, first: false, status: 'running', started: now - 50, steps: [{ name: 'TEMP 라벨 — 헤딩 후보에서 뺌', status: 'ok' }, { name: '헤딩 그래프 — LLM', status: 'running' }] };
  // 「LLM 검증·보완」 — 헤딩 판정이 도는 동안 표 판정 호출이 같이(heading_runs.TablesAhead: 단계 줄 「표 구조 — LLM」 이 「헤딩 그래프 — LLM」 보다 먼저 서고 둘 다 도는 중)
  if (kind === 'bothRunning') r.job = { stage: 2, llm: true, first: false, chain: 'llm', status: 'running', started: now - 90, steps: [{ name: '다시 추출', status: 'ok' },
    { name: '표 구조 — LLM', status: 'running', msg: '표 판정 호출 7/29 끝남 — 헤딩 판정과 같이' }, { name: 'TEMP 라벨 — 헤딩 후보에서 뺌', status: 'ok' }, { name: '헤딩 그래프 — LLM', status: 'running' }] };
  if (kind === 'fmtRunning') r.job = { stage: 2, llm: true, first: false, chain: 'heads', status: 'running', started: now - 200, steps: [{ name: '헤딩 그래프 — LLM', status: 'ok' }, { name: '서식 정리 계획 — LLM', status: 'running' }] };
  if (kind === 'rulesFailed') r.rules = { run: 99, at: now - 60, asked: false, groups: 27, saved: 0, kept: 0, rejected: 0, unsure: 0, error: '가짜 실패', costUsd: 0 };
  if (kind === 'noGroups') { r.rules = null; r.stage1.summary = { ...r.stage1.summary, unmatchedGroups: 0, conflicts: 0 }; }
  heads.summaryKey = null; headsResultsSummary(r);
}"""
RESTORE = "() => { heads.summaryKey = null; headsResultsSummary(heads.view); }"


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
    summ = run_stage(wid, 3)
    check("요약 API: rules 키 · 아직 안 함(None)", "rules" in summ and summ["rules"] is None, summ.get("rules", "키 없음"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.goto(f"{base}/#w={wid}")
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=240000)
        page.click("#tabHeads")
        page.wait_for_function("() => typeof heads !== 'undefined' && heads.view && heads.view.stage3 && !(heads.view.job && heads.view.job.status === 'running') && document.querySelector('#headsOverview .hprog')", timeout=120000)
        page.wait_for_timeout(300)

        # ---- 1. 스크립트만 한 문서
        m = page.evaluate(SNAP)
        c = m["cells"]
        check("세 층 이름(스크립트 · LLM · 조정) · 칸 아홉", m["layers"] == ["스크립트", "LLM", "조정"] and len(c) == 9, (m["layers"], len(c)))
        check("조정 층(tpl_plan_bar.js — 자세한 것은 smoke_adjust_ui.py): 「템플릿 조정」·「서식 조정」 이 LLM 칸 바로 아래", [x["text"] for x in c[6:8]] == ["템플릿 조정", "서식 조정"]
              and all(c[i + 3]["left"] == c[i + 6]["left"] and c[i + 6]["top"] > c[i + 3]["top"] for i in range(3)), c[6:])
        check("스크립트 층: 문단·라벨 · 헤딩 그래프 · 표 구조 모두 끝남", [x["state"] for x in c[:3]] == ["done"] * 3 and [x["text"] for x in c[:3]] == ["문단·라벨", "헤딩 그래프", "표 구조"], c[:3])
        check("LLM 층: 「규칙 보강 · 27묶음」 안 함 · 헤딩 판정 · 표 판정 안 함", [x["state"] for x in c[3:6]] == ["none"] * 3
              and c[3]["text"] == "규칙 보강 · 27묶음" and c[4]["text"] == "헤딩 판정" and c[5]["text"] == "표 판정", c[3:6])
        check("규칙 보강 칸 title: 못 맞춤·충돌 수 · 하는 곳(1단계 · 헤딩 그래프(LLM))", "못 맞춤 25묶음 · 충돌 2묶음" in c[3]["title"] and "LLM 규칙 보강" in c[3]["title"] and "헤딩 그래프(LLM)" in c[3]["title"], c[3]["title"])
        check("LLM 칸이 그 단계의 스크립트 칸 바로 아래(같은 왼쪽 · 아래 줄) · 칸 22px", all(c[i]["left"] == c[i + 3]["left"] and c[i + 3]["top"] > c[i]["top"] for i in range(3))
              and all(x["h"] == 22 for x in c), [(x["left"], x["top"], x["h"]) for x in c])
        check("전의 LLM 꼬리표 줄은 요약에 없음 · 진행 줄 높이 세 줄(≤ 76px)", not m["srcLine"] and m["boxH"] <= 76, (m["srcLine"], m["boxH"]))
        page.locator("#paneHeads").screenshot(path=str(OUT / "1_script_only.png"))

        # ---- 2. 1단계 카드 · 누르면 추출·설정 1단계 탭
        page.click("#headsOverview .hprog-step >> nth=3")
        page.wait_for_timeout(200)
        st = page.evaluate("() => ({ view: heads.resultView, stage: heads.runStage, shown: !document.getElementById('headsStage1').hidden })")
        check("규칙 보강 칸을 누르면 추출·설정 1단계 탭", st == {"view": "Run", "stage": 1, "shown": True}, st)
        m = page.evaluate(SNAP)
        check("1단계 카드: 「LLM 규칙 보강 — 안 함」", m["rule1"] == "안 함", m["rule1"])
        page.locator("#paneHeads").screenshot(path=str(OUT / "2_stage1_card.png"))
        page.click("#headsOverview .hprog-step >> nth=5")
        page.wait_for_timeout(200)
        check("표 판정 칸을 누르면 3단계 탭", page.evaluate("() => heads.runStage") == 3)

        # ---- 3. 흉내 낸 상태
        page.evaluate(FAKE, "rulesDone")
        c = page.evaluate(SNAP)["cells"]
        check("규칙 보강 끝남: 보라(llm) · 「규칙 보강 · 남은 27」 · title 에 실행 번호·저장 수", c[3]["state"] == "llm" and c[3]["text"] == "규칙 보강 · 남은 27묶음"
              and "실행 99" in c[3]["title"] and "규칙 저장 24" in c[3]["title"] and "다음 「헤딩 그래프(LLM)」 이 먼저 다시 묻습니다" in c[3]["title"], c[3])
        page.evaluate(FAKE, "judged")
        c = page.evaluate(SNAP)["cells"]
        check("헤딩 판정 LLM: 보라 · 끝난 시각 · title 은 「LLM 표시」 와 같은 글", c[4]["state"] == "llm" and c[4]["text"].startswith("헤딩 판정 · ") and "LLM 이 판정한 결과" in c[4]["title"], c[4])
        page.locator("#headsOverview").screenshot(path=str(OUT / "3_judged.png"))
        # LLM ✓ 칸을 누르면 「LLM 이 바꾼 것」(문서 옆 열 — heading_llm_diff.js, ② §7) · 안 돈 칸은 위처럼 추출·설정
        check("LLM ✓ 칸 title: 누르면 LLM 이 바꾼 것", "LLM 이 바꾼 것" in c[4]["title"], c[4]["title"][-40:])
        page.click("#headsOverview .hprog-step >> nth=4")
        page.wait_for_function("() => document.querySelector('#headsDlg[data-kind=\"llmDiff\"]:not([hidden]) .lld-sec')", timeout=20000)
        d = page.evaluate("() => ({ secs: [...document.querySelectorAll('#headsDlgBody .lld-sec')].map((s) => s.dataset.stage), title: document.getElementById('headsDlgTitle').textContent })")
        check("「LLM 이 바꾼 것」 열 · 절 여섯(규칙 보강 · 헤딩 판정 · 표 판정 · 템플릿 관계 · 반영 결과 · 서식 계획)", d == {"secs": ["1", "2", "3", "rel", "res", "fmt"], "title": "LLM 이 바꾼 것"}, d)
        page.screenshot(path=str(OUT / "3b_llm_diff.png"))
        page.evaluate("() => headsColClose(true)")
        page.evaluate(FAKE, "rulesRunning")
        c = page.evaluate(SNAP)["cells"]
        check("2단계 LLM 이 규칙 보강을 먼저 하는 중: 규칙 보강 칸이 돎 · 헤딩 판정 칸은 아직", c[3]["state"] == "running" and c[4]["state"] == "none", [(x["text"], x["state"]) for x in c])
        page.locator("#headsOverview").screenshot(path=str(OUT / "4_rules_running.png"))
        page.evaluate(FAKE, "graphRunning")
        c = page.evaluate(SNAP)["cells"]
        check("그 다음 그래프 LLM: 헤딩 판정 칸이 돎", c[4]["state"] == "running" and c[3]["state"] == "none", [(x["text"], x["state"]) for x in c])
        page.evaluate(FAKE, "bothRunning")
        c = page.evaluate(SNAP)["cells"]
        check("LLM 검증·보완 — 헤딩 판정과 표 판정 칸이 같이 도는 중(표 판정 호출은 헤딩 판정을 기다리지 않는다) · 규칙 보강 · 스크립트 칸은 안 돎 · 표 판정 title 에 「호출 7/29 … 헤딩 판정과 같이」",
              c[4]["state"] == "running" and c[5]["state"] == "running" and not any(x["state"] == "running" for x in c[:4]) and "표 판정 호출 7/29 끝남 — 헤딩 판정과 같이" in c[5]["title"],
              [(x["text"], x["state"]) for x in c[:6]] + [c[5]["title"][:80]])
        page.locator("#headsOverview").screenshot(path=str(OUT / "4b_heads_tables_together.png"))
        page.evaluate(FAKE, "fmtRunning")
        m2 = page.evaluate(SNAP)
        now = page.evaluate("() => (document.querySelector('#headsOverview .analysis-state.running .now-what') || {}).textContent || ''")
        check("헤딩 판정 뒤 서식 정리 계획이 도는 중: 스크립트 · LLM 칸은 돌지 않음 · 상태 줄 「헤딩 LLM 판정 · 서식 계획 중」", not any(x["state"] == "running" for x in m2["cells"][:6]) and "헤딩 LLM 판정 · 서식 계획" in now,
              ([(x["text"], x["state"]) for x in m2["cells"][:6]], now))
        page.evaluate(FAKE, "rulesFailed")
        c = page.evaluate(SNAP)["cells"]
        check("규칙 보강 답을 못 받음: 실패 표시 · title 에 까닭", c[3]["state"] == "failed" and "가짜 실패" in c[3]["title"], c[3])
        page.evaluate(FAKE, "noGroups")
        c = page.evaluate(SNAP)["cells"]
        check("판정하지 못한 묶음이 없으면 「규칙 보강 · 할 것 없음」(–)", c[3]["state"] == "skip" and c[3]["text"] == "규칙 보강 · 할 것 없음", c[3])
        page.evaluate(RESTORE)

        # ---- 4. 좁은 패널
        page.evaluate("() => headsResultView('Tree')")
        for w in (320, 388, 480):
            page.evaluate("(w) => { document.getElementById('panel').style.setProperty('--panel', w + 'px'); heads.summaryKey = null; headsResultsSummary(heads.view); }", w)
            page.wait_for_timeout(200)
            m = page.evaluate(SNAP)
            check(f"[{w}] 규칙 보강 칸의 수는 잘리지 않음(좁으면 단위 「묶음」 만 감춤)", m["cells"][3]["countIn"] and m["cells"][3]["count"] == ("27" if w < 400 else "27묶음"), m["cells"][3])
            check(f"[{w}] 진행 줄 세 줄 · 칸이 패널 밖으로 안 나감 · 가로 넘침 없음", m["boxH"] <= 76 and m["overflowX"] <= 0 and max(x["right"] for x in m["cells"]) <= m["paneRight"] + .5,
                  (m["boxH"], m["overflowX"], [x["text"] for x in m["cells"]]))
            page.locator("#paneHeads").screenshot(path=str(OUT / f"5_panel_{w}.png"))
        page.evaluate("() => { document.getElementById('panel').style.removeProperty('--panel'); heads.summaryKey = null; headsResultsSummary(heads.view); }")
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

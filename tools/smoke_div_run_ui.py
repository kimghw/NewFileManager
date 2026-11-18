"""프로젝트 구성 「실행 묶음」(#divRunBar — spec_구분_기준 ② §22, 2026-11-13) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_div_run_ui.py <그림·임시 폴더> [--port 18171]

TASK 「사업계획서 양식 표준화」(1단계 프로젝트 구성)에 연구개발계획서 양식(저장소 samples)을 올려 본다 — 계획·반영은 진짜 끝점(계획 한 번에 10~20초):
① 묶음의 자리 — 카드 하나(2026-11-14 ② §22 「카드 하나」): 보이는 것은 「한 번에 진행」 · 「불러오기」 둘, 나머지(① 변경 계획 보기 › ② 반영 · 계획 다시 열기 · 확정·저장 · 값 입력)는 접어 둔 「세부」 ·
   접혀 있으면 강조는 「한 번에 진행」, 펴면 다음 할 일 하나 · 320/480px · 「불러오기」 는 입력만 바꾼다.
② 차례대로: ① → 목록(2열 발에는 반영 단추가 없다 — 「반영 단추로 이동」 뿐) → ② → 반영 결과 → 실행 취소.
③ 계획이 낡는 길(뺄 자리 · 글 고침 · 입력 바꿈)마다 ② 가 꺼지고 까닭이 상태 줄에.
④ 「한 번에 진행」: 확인 창 없이(2026-11-18) 계획 → 반영. 사람이 봐야 할 계획(미해결 — 응답을 고쳐 흉내 · 기관 차례 바뀜)이면 반영 요청을 보내지 않고 멈춘다.
⑤ 저장 못 한 문단이 있으면 계획 요청을 보내지 않는다.
⑥ 프레임 이름(spec_작업 ② §10 — 2026-11-14): 반영하면 문서 이름이 「사업계획서_<프로젝트>_프레임.hwpx」, 실행 취소하면 올린 이름."""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from urllib.parse import unquote

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FORM = ROOT / "samples" / "연구개발계획서_양식.hwpx"
VALUES = {"stages": [2], "orgs": {"lead": "인텍", "joint": ["가나대", "다라연"], "nonprofit": [False, True, False]}}
PROJECT = "프레임 과제"
FRAME = f"사업계획서_{PROJECT}_프레임.hwpx"   # 반영한 양식 표준화 문서의 보이는 이름(spec_작업 ② §10 「프레임 이름」)
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
errors, fails, dialogs, posts = [], [], [], []
patch = {"unresolved": 0}  # > 0 이면 계획 응답의 미해결 수를 이 값으로 고쳐 돌려준다(사람이 봐야 할 계획 흉내)


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:500] if detail != "" else ""), flush=True)
    if not ok:
        fails.append(name)


# 묶음의 모습 — 단추(글 · 꺼짐 · 강조) · 상태 줄(종류 · 글 · 동그라미)
BAR = """() => { const b = document.getElementById('divRunBar'); if (!b) return null; const st = document.getElementById('divRunState');
  return { btns: [...b.querySelectorAll('.dv-run-head button:not(.panel-help), .dv-run-load button, .dv-run-steps button')].map((x) => ({ id: x.id, text: x.textContent, off: x.disabled, primary: x.classList.contains('primary'), seen: x.checkVisibility() })),
    kind: st.dataset.kind, text: st.lastChild.textContent, spin: !st.firstChild.hidden, staged: b.dataset.staged, open: document.getElementById('divRunMore').open }; }"""  # 묶음의 제 단추(머리 · 불러오기 줄 · 차례 줄) — 「세부」 안으로 들어온 구성 입력의 단추는 안 센다
FOOT = "() => ({ text: document.getElementById('headsDlgFoot').textContent, btns: [...document.querySelectorAll('#headsDlgFoot button')].map((b) => b.textContent), open: !document.getElementById('headsDlg').hidden, kind: document.getElementById('headsDlg').dataset.kind })"
IDLE = "() => !dv.busy && !dv.auto && !state.busy && state.inflight === 0"


def bar(page):
    v = page.evaluate(BAR)
    v["by"] = {b["id"]: b for b in v["btns"]}
    return v


def count(kind):
    return sum(1 for p in posts if p.endswith(f"/divisions/{kind}"))


try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    wid = requests.post(f"{base}/api/docs?new=1", files={"file": (FORM.name, FORM.read_bytes())}, timeout=300).json()["docId"]
    requests.put(f"{base}/api/works/{wid}/task", json={"kind": "rnd", "file": "plan", "job": "plan_fit", "project": PROJECT}, timeout=30).raise_for_status()
    requests.put(f"{base}/api/docs/{wid}/divisions/settings", json={"values": VALUES}, timeout=120).raise_for_status()
    requests.put(f"{base}/api/divisions/presets/new", json={"name": "시험 구성", "values": VALUES}, timeout=30).raise_for_status()   # 「불러오기」 로 고를 저장한 프로젝트 구성(값은 같게 — 뒤 단계가 그대로)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/divisions/" in r.url else None)

        def plan_route(route):  # 진짜 계획을 받아, 켜 두었으면 미해결 수만 고쳐 돌려준다
            resp = route.fetch()
            if not patch["unresolved"] or resp.status != 200:
                return route.fulfill(response=resp)
            body = resp.json()
            body["summary"]["unresolved"] = patch["unresolved"]
            route.fulfill(response=resp, json=body)
        page.route(re.compile(r"/api/docs/[^/]+/divisions/plan$"), plan_route)
        page.goto(base)
        page.evaluate("(id) => { location.hash = '#w=' + id; }", wid)
        page.reload()
        page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=wid, timeout=300000)
        if page.get_attribute("#panel", "data-tool") != "Div":
            page.click("#toolTabTask")
        page.wait_for_selector("#divRunBar")
        page.wait_for_function("() => !!dv.view && !!dv.values && dv.values.orgs.lead === '인텍'")

        # ---- 1. 자리 · 처음 모습(카드 하나 — 「한 번에 진행」 · 「불러오기」 만 보이고 나머지는 접어 둔 「세부」)
        check("처음 — 문서 이름은 올린 이름(아직 반영 전)", page.evaluate("() => state.name") == FORM.name, page.evaluate("() => state.name"))
        v = bar(page)
        fold = page.evaluate("""() => { const b = document.getElementById('divRunBar'), m = document.getElementById('divRunMore'), kids = [...b.children].map((e) => e.id || e.className.split(' ')[0]);
          return { kids, sum: m.querySelector('summary').textContent, inMore: ['.dv-run-steps', 'fieldset.dv-config', '#divPresetStatus', '#divConfirmBtn', '.dv-org-field input', '.dv-year-field input'].every((q) => !!m.querySelector(q)),
            loadInBar: document.getElementById('divSourceSel').parentElement.parentElement === b && document.getElementById('divSourceLoad').parentElement.parentElement === b, loose: document.querySelectorAll('#divBox > fieldset.dv-config, #divBox > .dv-presets').length,
            hidden: ['divPlanButton', 'divApplyButton', 'divReopenPlan', 'divConfirmBtn'].every((id) => !document.getElementById(id).checkVisibility()), stored: localStorage.getItem('nfm.divRunMore'),
            h: Math.round(b.getBoundingClientRect().height), selH: Math.round(document.getElementById('divSourceSel').getBoundingClientRect().height) }; }""")
        check("카드 하나 — 머리 · 불러오기 줄 · 상태 줄 · 접어 둔 「세부」 차례 · 불러오기 줄은 카드에, 차례 단추·확정·값 입력은 「세부」 안 · 패널에 따로 남은 구성 입력 없음", fold["kids"] == ["dv-run-head", "dv-preset-row", "divRunState", "divRunMore"]
              and fold["inMore"] and fold["loadInBar"] and fold["loose"] == 0 and fold["sum"].startswith("세부"), fold)
        check("처음엔 접힘 — 보이는 단추는 「한 번에 진행」 · 「불러오기」 둘 · 강조는 「한 번에 진행」 하나 · 상태 글이 그 단추를 가리킴 · 카드 높이 ≤ 150px", not v["open"] and fold["hidden"] and fold["stored"] is None
              and [b["text"] for b in v["btns"] if b["seen"]] == ["한 번에 진행", "불러오기"] and [b["id"] for b in v["btns"] if b["primary"]] == ["divRunAll"] and v["text"].startswith("「한 번에 진행」") and "「세부」" in v["text"]
              and fold["h"] <= 150 and fold["selH"] == 28, [v, fold])
        page.locator("#panel").screenshot(path=str(OUT / "1_folded.png"))
        for width in (320, 480):  # 접힌 카드 — 패널 최소 폭·보통 폭에서 가로 넘침 없음(design.md §1-8)
            page.evaluate("(w) => { const c = colSizers.find((x) => x.box === 'panel'); c.w = w; c.apply(); }", width)
            page.wait_for_timeout(300)
            fit = page.evaluate("""() => { const b = document.getElementById('divRunBar'), r = b.getBoundingClientRect();
              return { ok: b.scrollWidth <= b.clientWidth + 1 && [...b.querySelectorAll('button, select, summary, .dv-run-state, strong')].filter((e) => e.checkVisibility()).every((e) => { const x = e.getBoundingClientRect(); return x.left >= r.left - 1 && x.right <= r.right + 1; }), h: Math.round(r.height) }; }""")
            check(f"접힌 카드 가로 넘침 없음(패널 {width}px)", fit["ok"] and fit["h"] <= 200, fit)
            page.locator("#panel").screenshot(path=str(OUT / f"1_folded_{width}.png"))
        page.evaluate("() => { const c = colSizers.find((x) => x.box === 'panel'); c.w = null; c.apply(); }")
        # 「불러오기」 — 저장한 프로젝트 구성을 골라 입력 칸만 채운다(문서·계획 요청 없음 · 「세부」 는 접힌 그대로)
        check("고르기 전 「불러오기」 꺼짐", page.locator("#divSourceLoad").is_disabled())
        page.select_option("#divSourceSel", value=page.evaluate("() => [...document.querySelectorAll('#divSourceSel option')].find((o) => o.textContent.includes('시험 구성')).value"))
        page.click("#divSourceLoad")
        page.wait_for_function("() => (dv.preset.from || '').includes('시험 구성') && !document.getElementById('toast').hidden && document.getElementById('toast').textContent.includes('불러왔습니다')")
        check("「불러오기」 — 입력 칸만 채움(계획·반영 요청 0회) · 「세부」 는 접힌 그대로 · 값 요약의 도움말에 불러온 값", count("plan") == 0 and count("apply") == 0 and not bar(page)["open"]
              and page.evaluate("() => dv.values.orgs.lead === '인텍' && dv.values.orgs.joint.join() === '가나대,다라연'") and "주관 인텍" in (page.get_attribute("#divReviewSummary", "title") or ""), page.get_attribute("#divReviewSummary", "title"))
        page.wait_for_function(f"() => ({IDLE})()")
        # 「세부」 를 편다 — 사람이 편 것은 브라우저에 기억 · 강조가 다음 할 일(①)로 옮겨 간다
        page.click("#divRunMore > summary")
        page.wait_for_function("() => document.getElementById('divRunMore').open && localStorage.getItem('nfm.divRunMore') === '1' && document.getElementById('divPlanButton').classList.contains('primary')")
        v = bar(page)
        lay = page.evaluate("""() => { const k = [...document.getElementById('divBox').children], b = document.getElementById('divRunBar'), top = (id) => document.getElementById(id).getBoundingClientRect().top;
          return { order: k.slice(0, 3).map((e) => e.id || e.className.split(' ')[0]), old: document.querySelectorAll('.dv-review-bar').length, pos: getComputedStyle(b).position, role: b.getAttribute('role'), name: b.getAttribute('aria-label'),
            sameRow: Math.abs(top('divPlanButton') - top('divApplyButton')) < 2, arrowHidden: b.querySelector('.dv-run-arrow').getAttribute('aria-hidden'), status: document.querySelector('#divRunState [role=status]') === document.getElementById('divRunState').lastChild,
            heights: [...b.querySelectorAll('.dv-run-head button:not(.panel-help), .dv-run-load button, .dv-run-steps button')].map((x) => Math.round(x.getBoundingClientRect().height)) }; }""")
        check("묶음은 첫 카드 바로 다음 · 그 아래 문서 반영 상태 · 옛 아래 띠 없음 · 붙박이 아님", lay["order"] == ["dv-task", "divRunBar", "divAppliedState"] and lay["old"] == 0 and lay["pos"] == "static", lay)
        check("펴면 단추가 차례대로 — 한 번에 진행 · 불러오기 · ① 변경 계획 보기 · ② 반영 · 계획 다시 열기(①·② 는 같은 줄 · 높이 28px)", [b["text"] for b in v["btns"]] == ["한 번에 진행", "불러오기", "① 변경 계획 보기", "② 반영", "계획 다시 열기"]
              and all(b["seen"] for b in v["btns"]) and lay["sameRow"] and set(lay["heights"]) == {28}, [v["btns"], lay["heights"]])
        check("편 처음 — 강조는 ① 하나 · ② 와 다시 열기는 꺼짐 · 한 번에 진행은 켜짐 · 상태 글 「먼저 변경 계획을 확인하세요」", [b["id"] for b in v["btns"] if b["primary"]] == ["divPlanButton"]
              and v["by"]["divApplyButton"]["off"] and v["by"]["divReopenPlan"]["off"] and not v["by"]["divPlanButton"]["off"] and not v["by"]["divRunAll"]["off"]
              and v["text"].startswith("먼저 변경 계획을 확인하세요") and v["kind"] == "next" and not v["spin"], v)
        check("접근성 — 이름 있는 묶음(role=group) · 화살표는 낭독 안 함 · 바뀌는 상태 글만 role=status · 꺼진 단추의 까닭(title + aria-describedby)", lay["role"] == "group" and lay["name"] == "프로젝트 구성 반영" and lay["arrowHidden"] == "true" and lay["status"]
              and page.get_attribute("#divApplyButton", "title") == "먼저 변경 계획을 확인하세요" and page.get_attribute("#divApplyButton", "aria-describedby") == "divRunState", lay)
        for width in (320, 480):  # 패널 최소 폭·보통 폭에서 가로 넘침 없음(design.md §1-8)
            page.evaluate("(w) => { const c = colSizers.find((x) => x.box === 'panel'); c.w = w; c.apply(); }", width)
            page.wait_for_timeout(300)
            fit = page.evaluate("""() => { const b = document.getElementById('divRunBar'), r = b.getBoundingClientRect(), top = (id) => document.getElementById(id).getBoundingClientRect().top;
              return { ok: b.scrollWidth <= b.clientWidth + 1 && [...b.querySelectorAll('button, select, input, summary, .dv-run-state, strong')].filter((e) => e.checkVisibility()).every((e) => { const x = e.getBoundingClientRect(); return x.left >= r.left - 1 && x.right <= r.right + 1; }),
                sameRow: Math.abs(top('divPlanButton') - top('divApplyButton')) < 2, h: Math.round(r.height) }; }""")
            check(f"편 카드 가로 넘침 없음 · ①·② 는 한 줄(패널 {width}px)", fit["ok"] and fit["sameRow"], fit)
            page.locator("#panel").screenshot(path=str(OUT / f"1_bar_{width}.png"))
        page.evaluate("() => { const c = colSizers.find((x) => x.box === 'panel'); c.w = null; c.apply(); }")

        # ---- 2. 저장 못 한 문단이 있으면 계획을 세우지 않는다(astra P1 — flushAll 은 실패를 삼킨다)
        page.evaluate("() => { state.failed.add('없는-문단'); }")
        page.click("#divPlanButton")
        page.wait_for_function("() => !document.getElementById('toast').hidden && document.getElementById('toast').textContent.includes('반영하지 못한 문단')")
        check("저장 못 한 문단이 있으면 계획 요청 0회 · 알림", count("plan") == 0 and page.evaluate("() => !dv.busy && !dv.plan"))
        page.evaluate("() => { state.failed.clear(); }")

        # ---- 3. ① 변경 계획 보기 → 목록 · ② 가 다음 할 일
        page.click("#divPlanButton")
        page.wait_for_function("() => document.getElementById('divRunState').dataset.kind === 'run'")
        v = bar(page)
        check("계산 중 — 동그라미 + 「변경 계획 계산 중…」 · 단추는 모두 꺼짐", v["spin"] and v["text"] == "변경 계획 계산 중…" and all(b["off"] for b in v["btns"]), v)
        page.wait_for_function(f"() => !!dv.plan && ({IDLE})() && document.getElementById('divRunState').dataset.kind !== 'run'", timeout=240000)
        v, f = bar(page), page.evaluate(FOOT)
        plan = page.evaluate("() => dv.plan.summary")
        check("계획 뒤 — 2열 목록이 열리고 발에는 반영 단추가 없다(요약 글 + 「반영 단추로 이동」 · 「닫기」)", f["open"] and f["kind"] == "divisions" and f["btns"] == ["반영 단추로 이동", "닫기"] and f"맞출 자리 {plan['applied']}곳" in f["text"], f)
        check("계획 뒤 — 강조가 ② 로 옮겨 가고 켜짐 · 다시 열기 켜짐 · 상태 글 「계획 준비됨 · 맞출 자리 N곳 · 지워지는 글 문단 N」", [b["id"] for b in v["btns"] if b["primary"]] == ["divApplyButton"] and not v["by"]["divApplyButton"]["off"]
              and not v["by"]["divReopenPlan"]["off"] and v["by"]["divReopenPlan"]["text"] == "계획 다시 열기" and v["text"].startswith(f"계획 준비됨 · 맞출 자리 {plan['applied']}곳 · 지워지는 글 문단 {plan['deleted']}") and count("plan") == 1, [v, plan])
        page.screenshot(path=str(OUT / "3_planned.png"))

        # ---- 4. 뺄 자리를 바꾸면 ② 가 꺼진다 — 단추뿐 아니라 함수도 거절
        page.locator("#headsDlgBody input[type=checkbox][aria-label='반영에서 빼기']").first.check()
        v, f = bar(page), page.evaluate(FOOT)
        refused = page.evaluate("async () => (await divApply({ quiet: true })) === false")
        check("뺄 자리 바꿈 — ② 꺼짐 · 상태 글 · 발의 글 · 발 단추는 「변경 계획 단추로 이동」 · divApply 를 직접 불러도 반영 요청 0회", v["by"]["divApplyButton"]["off"] and v["text"] == "뺄 자리가 바뀌었습니다 · 다시 계획하세요"
              and "뺄 자리를 바꿨습니다" in f["text"] and f["btns"] == ["변경 계획 단추로 이동", "닫기"] and refused and count("apply") == 0, [v, f, refused])
        page.locator("#headsDlgBody input[type=checkbox][aria-label='반영에서 빼기']").first.uncheck()
        check("되돌리면 ② 가 다시 켜짐", not bar(page)["by"]["divApplyButton"]["off"])

        # ---- 5. 닫고 「계획 다시 열기」(다시 계산하지 않음) · 발의 「반영 단추로 이동」 = 초점만
        page.locator("#headsDlgFoot button", has_text="닫기").click()
        page.wait_for_function("() => document.getElementById('headsDlg').hidden")
        page.click("#divReopenPlan")
        page.wait_for_function("() => !document.getElementById('headsDlg').hidden && document.getElementById('headsDlg').dataset.kind === 'divisions'")
        check("계획 다시 열기 — 목록이 다시 열림 · 계획 요청은 그대로 1회", count("plan") == 1 and page.evaluate(FOOT)["btns"] == ["반영 단추로 이동", "닫기"])
        rev = page.evaluate("() => state.serverRev")
        page.click("#headsDlgFoot [data-div-go]")
        page.wait_for_function("() => document.activeElement && document.activeElement.id === 'divApplyButton'")
        check("「반영 단추로 이동」 — 패널의 ② 에 초점 · 문서는 그대로(반영 요청 0회)", count("apply") == 0 and page.evaluate("() => state.serverRev") == rev and "dv-run-flash" in page.get_attribute("#divRunBar", "class"))

        # ---- 6. 글을 고쳐 문서 차례가 오르면 계획이 낡는다
        para = page.locator("#doc .para", has_text=re.compile(r"\S")).first
        para.click()
        page.keyboard.press("End")
        page.keyboard.type("가")
        page.wait_for_function("(r) => state.serverRev > r && state.inflight === 0", arg=rev, timeout=30000)
        page.wait_for_function("() => document.getElementById('divApplyButton').disabled")
        v, f = bar(page), page.evaluate(FOOT)
        check("글 고침 — ② 꺼짐 · 상태 글 「문서가 바뀌었습니다 · 다시 계획하세요」 · 발의 글도", v["text"] == "문서가 바뀌었습니다 · 다시 계획하세요" and [b["id"] for b in v["btns"] if b["primary"]] == ["divPlanButton"]
              and "문서가 바뀌어 이 계획은 반영할 수 없습니다" in f["text"], [v, f])

        # ---- 7. 입력을 바꾸면 계획을 버린다
        lead = page.locator("#divBox .dv-org-field input").first
        lead.fill("인텍 바꿈")
        v, f = bar(page), page.evaluate(FOOT)
        check("입력 바꿈 — ② · 다시 열기 꺼짐 · 상태 글 「입력값이 바뀌었습니다 · 다시 계획하세요」 · 발 「더 반영할 수 없습니다」", v["by"]["divApplyButton"]["off"] and v["by"]["divReopenPlan"]["off"] and v["text"] == "입력값이 바뀌었습니다 · 다시 계획하세요"
              and "더 반영할 수 없습니다" in f["text"] and f["btns"] == ["변경 계획 단추로 이동", "닫기"] and page.evaluate("() => dv.plan === null"), [v, f])
        lead.fill("인텍")
        page.wait_for_function("() => dv.values.orgs.lead === '인텍'")

        # ---- 8. ① → ② 반영(확인 창 없이 — 2026-11-18 사용자 「이런 알람좀 주지마」) → 결과
        page.click("#divPlanButton")
        page.wait_for_function(f"() => !!dv.plan && ({IDLE})() && document.getElementById('divRunState').dataset.kind !== 'run'", timeout=240000)
        n = len(dialogs)
        page.click("#divApplyButton")
        page.wait_for_function(f"() => !!dv.result && ({IDLE})() && document.getElementById('divRunState').dataset.kind === 'done'", timeout=240000)
        page.wait_for_function("() => !!dv.view && !!dv.view.applied && !!dv.result && dv.view.applied.rev === dv.result.rev && !!document.querySelector('#divAppliedState .dv-undo')", timeout=60000)  # 꼬리표는 지원 안 되는 자리가 있으면 「반영 결과 확인 필요」
        v, f = bar(page), page.evaluate(FOOT)
        check("② 반영 — 확인 창 없이 · 반영 요청 1회", len(dialogs) == n and count("apply") == 1, dialogs[n:])
        check("반영 뒤 — 상태 글 「반영 완료 · 편집 차례 N」 · 강조 없음 · ② 꺼짐 · 「반영 결과 열기」 · 발은 글 + 닫기뿐(실행 취소는 문서 반영 상태에)", v["text"].startswith("반영 완료 · 편집 차례 ") and v["kind"] == "done"
              and not [b for b in v["btns"] if b["primary"]] and v["by"]["divApplyButton"]["off"] and v["by"]["divReopenPlan"]["text"] == "반영 결과 열기" and not v["by"]["divReopenPlan"]["off"]
              and f["text"].startswith("반영 끝 — 편집 차례") and f["btns"] == ["닫기"] and page.locator("#divAppliedState .dv-undo").count() == 1, [v, f])
        # 프레임 이름(spec_작업 ② §10) — 반영을 마친 양식 표준화 문서: 화면(상단 바 · 패널 머리 · 문서 목록)과 내려받는 파일 이름이 「사업계획서_<프로젝트>_프레임.hwpx」(「_수정」 꼬리 없음), 저장된 이름·올린 원본은 그대로
        page.wait_for_function("(n) => state.name === n && (worksList.find((w) => w.id === state.id) || {}).name === n", arg=FRAME, timeout=30000)
        cd = unquote(requests.get(f"{base}/api/docs/{wid}/download", timeout=120).headers["content-disposition"])
        orig = unquote(requests.get(f"{base}/api/works/{wid}/file/original", timeout=120).headers["content-disposition"])
        check("프레임 이름 — 반영 뒤 화면 이름·내려받는 이름이 「사업계획서_<프로젝트>_프레임.hwpx」(꼬리 「_수정」 없음) · 올린 원본 받기는 올린 이름", page.inner_text("#toolSource").strip() == FRAME and page.evaluate("() => document.getElementById('fileName').textContent") == FRAME
              and cd.endswith("''" + FRAME) and "_수정" not in cd and FORM.name in orig and "프레임" not in orig, [page.inner_text("#toolSource"), cd, orig])
        page.screenshot(path=str(OUT / "8_applied.png"))

        # ---- 9. 실행 취소(문서 반영 상태의 단추) — 계획·결과를 버리고 처음으로
        n = len(dialogs)
        page.click("#divAppliedState .dv-undo")
        page.wait_for_function(f"() => !dv.plan && !dv.result && ({IDLE})() && document.getElementById('headsDlg').hidden", timeout=120000)
        page.wait_for_function("() => document.querySelector('#divAppliedState .dv-tag') && document.querySelector('#divAppliedState .dv-tag').textContent === '아직 미반영'", timeout=60000)
        v = bar(page)
        check("실행 취소 — 확인 창 없이(반영이 마지막 구조 편집) · 목록 닫힘 · 묶음은 처음 상태", len(dialogs) == n and v["text"].startswith("먼저 변경 계획을 확인하세요") and [b["id"] for b in v["btns"] if b["primary"]] == ["divPlanButton"]
              and v["by"]["divApplyButton"]["off"] and v["by"]["divReopenPlan"]["off"], v)
        page.wait_for_function("(n) => state.name === n && (worksList.find((w) => w.id === state.id) || {}).name === n", arg=FORM.name, timeout=30000)
        check("프레임 이름 — 그 반영을 실행 취소하면 올린 이름으로 돌아옴", page.inner_text("#toolSource").strip() == FORM.name, page.inner_text("#toolSource"))

        # ---- 10. 「한 번에 진행」 — 확인 창 없이(2026-11-18) 계획 → 반영
        n, p0, a0 = len(dialogs), count("plan"), count("apply")
        page.click("#divRunAll")
        page.wait_for_function("() => dv.auto && document.getElementById('divRunState').dataset.kind === 'run'")
        check("한 번에 진행 — 도는 동안 단추는 모두 꺼짐", all(b["off"] for b in bar(page)["btns"]))
        page.wait_for_function(f"() => !!dv.result && ({IDLE})() && document.getElementById('divRunState').dataset.kind === 'done'", timeout=480000)
        v = bar(page)
        check("한 번에 진행 — 확인 창 없이 · 계획 1회 + 반영 1회 · 「반영 완료」(지원 안 되는 자리가 있어도 끝까지)", len(dialogs) == n
              and count("plan") == p0 + 1 and count("apply") == a0 + 1 and v["text"].startswith("반영 완료"), [dialogs[n:], count("plan") - p0, count("apply") - a0, v["text"]])
        page.wait_for_function("() => !!dv.view && !!dv.view.applied && !!dv.result && dv.view.applied.rev === dv.result.rev && !!document.querySelector('#divAppliedState .dv-undo')", timeout=60000)  # 꼬리표는 지원 안 되는 자리가 있으면 「반영 결과 확인 필요」

        # ---- 11. 사람이 봐야 할 계획이면 멈춘다 — 반영 요청을 보내지 않는다. ⓐ 미해결(응답을 고쳐 흉내) ⓑ 기관의 차례가 마지막 반영과 다름
        joint = page.locator("#divBox .dv-org-field input")
        joint.nth(1).fill("다라연")
        joint.nth(2).fill("가나대")
        page.wait_for_function("() => dv.values.orgs.joint.join() === '다라연,가나대'")
        patch["unresolved"] = 2
        page.click("#divRunMore > summary")  # 「세부」 를 접고 돌린다 — 멈추면 저절로 펴져 다음 단추(② 반영)가 보여야 한다(브라우저에 기억한 접힘은 그대로)
        page.wait_for_function("() => !document.getElementById('divRunMore').open && localStorage.getItem('nfm.divRunMore') === '0' && document.getElementById('divRunAll').classList.contains('primary')")
        n, a0 = len(dialogs), count("apply")
        page.click("#divRunAll")
        page.wait_for_function(f"() => !!dv.msg && dv.msg.kind === 'halt' && ({IDLE})()", timeout=240000)
        page.wait_for_function("() => document.getElementById('divRunMore').open && document.getElementById('divApplyButton').checkVisibility()")
        check("멈추면 접어 둔 「세부」 가 저절로 펴짐(② 반영이 보임) · 브라우저에 기억한 접힘은 그대로", page.evaluate("() => localStorage.getItem('nfm.divRunMore')") == "0" and page.evaluate("() => dv.ui.runMore") is True)
        v, f = bar(page), page.evaluate(FOOT)
        check("ⓐ 미해결 2곳 — 반영 요청 0회 · 상태 줄 「멈춤 — 미해결 2곳 …」 · 목록은 열린 채 · ② 는 켜져 있다(확인한 뒤 사람이 누름)", count("apply") == a0 and len(dialogs) == n and v["kind"] == "halt" and v["text"].startswith("멈춤 — 미해결 2곳")
              and "「② 반영」" in v["text"] and f["open"] and f["kind"] == "divisions" and not v["by"]["divApplyButton"]["off"] and not page.evaluate("() => !!dv.result"), [v, f])
        page.screenshot(path=str(OUT / "11_halt.png"))
        patch["unresolved"] = 0
        page.click("#divPlanButton")  # 고치지 않은 진짜 계획으로 다시(미해결 없음) — 상태 줄의 멈춤 글도 지워진다
        page.wait_for_function(f"() => !!dv.plan && !dv.msg && dv.plan.summary.unresolved !== 2 && ({IDLE})() && document.getElementById('divRunState').dataset.kind !== 'run'", timeout=240000)
        real = page.evaluate("() => ({ kind: divPlanState().kind, stops: divPlanIssues(dv.plan.summary, false), summary: dv.plan.summary })")
        check("차례를 바꾼 값의 진짜 계획 — 반영할 것이 있고 미해결·계획 오류 없음(멈춤은 차례 때문)", real["kind"] == "ready" and real["stops"] == "", real)
        n, a0 = len(dialogs), count("apply")
        page.click("#divRunAll")
        page.wait_for_function(f"() => !!dv.msg && dv.msg.kind === 'halt' && ({IDLE})()", timeout=240000)
        v = bar(page)
        check("ⓑ 기관 차례 바뀜(가나대 ↔ 다라연) — 지금 계획 그대로 반영하려다 멈춤 · 반영 요청 0회 · 까닭에 기관 이름과 자리", count("apply") == a0 and len(dialogs) == n
              and v["kind"] == "halt" and "의 차례가 마지막 반영과 다릅니다" in v["text"] and "가나대" in v["text"] and "공동 1 → 공동 2" in v["text"], [v, dialogs[n:]])

        # ---- 12. 값을 되돌려 다시 계획 — 바꿀 것이 없으면 「현재 구성과 맞습니다」(② 꺼짐)
        joint.nth(1).fill("가나대")
        joint.nth(2).fill("다라연")
        page.wait_for_function("() => dv.values.orgs.joint.join() === '가나대,다라연'")
        page.click("#divPlanButton")
        page.wait_for_function(f"() => !!dv.plan && ({IDLE})() && document.getElementById('divRunState').dataset.kind !== 'run'", timeout=240000)
        v, f = bar(page), page.evaluate(FOOT)
        check("바꿀 것 없음 — 상태 글·발 「현재 구성과 맞습니다 — 바꿀 자리가 없습니다(· 지원 안 됨 N곳은 그대로)」 · ② 꺼짐 · 발은 닫기뿐", v["text"].startswith("현재 구성과 맞습니다 — 바꿀 자리가 없습니다") and v["by"]["divApplyButton"]["off"]
              and f["text"].startswith("현재 구성과 맞습니다") and f["btns"] == ["닫기"], [v, f, page.evaluate("() => dv.plan.summary")])
        bad = [e for e in errors if "Failed to load resource" not in e]
        check("화면 오류 0", not bad, bad[:5])
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

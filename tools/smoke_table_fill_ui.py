"""작성요령 세 묶음 · 표 채우기(spec_헤딩_추출 ② §18 — 표 메뉴 「작성요령 · 표 지침」·「에이전트로 표 채우기…」) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_table_fill_ui.py <그림·임시 폴더> [--port 18179]

연구개발계획서_양식.hwpx 를 API 로 올려 `#w=<id>` 로 연다(첫 분석 없이) → 표지 표의 손잡이 → 표 메뉴의 「에이전트로 표 채우기…」 · 손잡이 아래 둘째 아이콘(작성요령 · 표 지침) →
「작성요령 · 표 지침」 열(① 문서의 작성요령 — 뒤따르는 「앞표지 작성 요령」 표 · ② 지침 · ③ 칸 입력 규칙 — 기본 규칙·표에서 읽은 칸 꼴·공통/이 표 규칙 저장 · 「이 표 지침에 붙이기」) →
「표 채우기」 열(채울 칸 요약 · LLM 없음 안내) → LLM 답은 `page.route` 로 가짜(임시 서버는 LLM 을 끈다 — 미리보기 응답은 진짜에 `llm: true` 만 얹고, 제안 응답은 진짜 미리보기의 칸으로 지어 준다)
→ 제안 목록(경고 없는 것만 고름 · 올리면 문서의 칸 표시) → 「문서에 반영」(진짜 서버 — 칸 글이 바뀌고 실행 취소 1개) → 범위로 열기 · 콘솔 오류."""
import argparse
import json
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
ap.add_argument("--port", type=int, default=18179)
args = ap.parse_args()
OUT = Path(args.out).resolve()
RND = ROOT / "samples" / "연구개발계획서_양식.hwpx"

OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_JOBS": "off", "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:500] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def menu(page):
    return page.evaluate("""() => { const m = document.querySelector('.ctx-menu'); if (!m || m.hidden || m.dataset.by !== 'tmn') return null;
        return [...m.querySelectorAll('button')].map((b) => ({text: b.textContent, disabled: b.disabled})); }""")


def item(page, text):
    return page.locator(f".ctx-menu[data-by='tmn'] button:has-text('{text}')").first


def corner(page, tid):
    """표 칸을 눌러 고른 표로 만들고 손잡이를 눌러 표 메뉴를 연다."""
    page.locator(f"#doc table.tbl[data-tbl='{tid}'] td .para").first.scroll_into_view_if_needed()
    page.wait_for_timeout(1500)   # 부드러운 스크롤이 끝난 뒤(도는 중에는 메뉴가 열자마자 닫힌다)
    page.locator(f"#doc table.tbl[data-tbl='{tid}'] td .para").first.click()
    page.wait_for_selector(f".tbl-corner[data-for='{tid}']")
    page.locator(".tbl-corner").click()
    page.wait_for_selector(".ctx-menu[data-by='tmn']:not([hidden])")


def guide_field(page, scope, kind):
    return page.locator(f".ta-field[data-ta-scope='{scope}'][data-ta-field='{kind}']")


def guide_tab(page, kind):
    page.locator(f".ta-editor-tabs [data-ta-tab='{kind}']").click()
    page.wait_for_selector(f".ta-section[data-ta-section='{kind}']:not([hidden])")


FIT_GUIDE = """() => { const p = document.getElementById('headsDlg'), r = p.getBoundingClientRect();
  const bad = [...p.querySelectorAll('.ta-wrap *')].filter(e => e.getClientRects().length && (e.getBoundingClientRect().right > r.right + 1 || e.getBoundingClientRect().left < r.left - 1)).slice(0, 6).map(e => e.className || e.tagName);
  return { width: Math.round(r.width), bad, over: p.scrollWidth - p.clientWidth, bodyOver: document.getElementById('headsDlgBody').scrollWidth - document.getElementById('headsDlgBody').clientWidth }; }"""


try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    r = requests.post(f"{base}/api/docs", files={"file": (RND.name, RND.read_bytes())}, timeout=120)
    r.raise_for_status()
    doc = r.json()["docId"]
    blocks = requests.get(f"{base}/api/docs/{doc}", timeout=120).json()["blocks"]
    tid = next(b["id"] for b in blocks if b.get("type") == "table" and b.get("nRows", 0) > 20)   # 표지 표(첫 큰 표)
    fill_url = f"{base}/api/docs/{doc}/tables/{tid}/fill"
    dry = requests.post(fill_url, json={"dry": True}, timeout=120).json()
    by = {t["ref"]: t for t in dry["targets"]}
    check("서버 미리보기 — 채울 칸 · 「작성 요령」 표 1 · LLM 끔", dry["counts"]["targets"] > 100 and dry["guides"] == 1 and dry["llm"] is False and by["Y2"]["form"] == "check", dry["counts"])

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1700, "height": 1000})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/#w={doc}")
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=240000)
        page.wait_for_timeout(1500)

        # ---- 1. 표 메뉴의 새 항목
        corner(page, tid)
        m = menu(page)
        texts = [x["text"] for x in m]
        dis = {x["text"]: x["disabled"] for x in m}
        check("표 메뉴 — 「에이전트로 표 채우기…」 가 켜져 있음 · 「작성요령 · 표 지침」 은 메뉴가 아니라 둘째 아이콘(2026-11-12)",
              dis.get("에이전트로 표 채우기…") is False and "작성요령 · 표 지침" not in texts, texts)
        check("표 메뉴 — 「에이전트로 표 채우기…」 는 「표 나누기」 와 「이 표를 표 양식으로 지정」 사이",
              texts.index("표 나누기▸") < texts.index("에이전트로 표 채우기…") < texts.index("이 표를 표 양식으로 지정"), texts)
        page.screenshot(path=str(OUT / "1_menu.png"))
        page.keyboard.press("Escape")

        # ---- 2. 작성요령 · 표 지침 — 손잡이 아래 둘째 아이콘으로 연다 · 세 묶음
        check("둘째 아이콘 — 적어 둔 지침·규칙이 없는 표는 표시(.has) 없음", page.evaluate("(t) => { const g = document.querySelector('.tbl-corner-guide'); return g.dataset.for === t && !g.classList.contains('has'); }", tid))
        page.locator(".tbl-corner-guide").click()
        page.wait_for_selector(".ta-wrap .ta-group")
        info = page.evaluate("""() => { const w = document.querySelector('.ta-wrap');
            return {title: document.getElementById('headsDlgTitle').textContent, kind: heads.dlg, groups: [...w.querySelectorAll('.ta-group')].map((e) => e.textContent),
                    guides: [...w.querySelectorAll('.ta-source')].map((e) => ({head: e.textContent, text: e.querySelector('pre')?.textContent || '', open: e.open})),
                    fields: [...w.querySelectorAll('.ta-field')].map((e) => [e.dataset.taScope, e.dataset.taField]), boxes: w.querySelectorAll('textarea').length,
                    notes: [...w.querySelectorAll('.hnote')].map((e) => e.textContent), defaults: w.querySelector('.ta-default-rules pre').textContent}; }""")
        check("열 제목 「작성요령 · 표 지침 · <표>」", info["title"] == f"작성요령 · 표 지침 · {tid}" and info["kind"] == "tableAgent", info["title"])
        check("세 묶음 — ① 문서의 작성요령 ② 지침 ③ 칸 입력 규칙", len(info["groups"]) == 3 and info["groups"][0].startswith("① 문서의 작성요령 1") and info["groups"][1].startswith("② 지침")
              and info["groups"][2].startswith("③ 칸 입력 규칙"), info["groups"])
        g = info["guides"]
        check("① — 뒤따르는 「앞표지 작성 요령」 표의 항목 줄(긴 원문은 접힘)", len(g) == 1 and "작성 요령 표" in g[0]["head"] and "앞표지 작성 요령" in g[0]["head"] and "1. 보안등급: 보안과제에 해당하는 경우" in g[0]["text"]
              and "13. 연구개발과제명" in g[0]["text"] and not g[0]["open"], g)
        check("② ③ — 글상자 넷(공통 지침 · 이 표 지침 · 공통 규칙 · 이 표 규칙)",
              info["boxes"] == 4 and info["fields"] == [["common", "instructions"], ["own", "instructions"], ["common", "rules"], ["own", "rules"]]
              and "양식 지침" in page.text_content(".ta-section[data-ta-section=instructions]"), info["fields"])
        check("③ — 표에서 읽은 칸 꼴 · 기본 규칙(앱)", any(n.startswith("표에서 읽은 칸 꼴 — ") and "체크" in n and "빈 자리" in n for n in info["notes"]) and info["defaults"].startswith("- 체크 칸(「[ ]」·「□」)"),
              (info["notes"], info["defaults"][:60]))
        check("처음에는 지침 탭만 보이고 변경 없는 저장·비어 있는 지우기는 꺼짐", page.locator(".ta-editor-tabs [data-ta-tab=instructions]").get_attribute("aria-selected") == "true"
              and page.locator(".ta-section[data-ta-section=instructions]").is_visible() and not page.locator(".ta-section[data-ta-section=rules]").is_visible()
              and page.eval_on_selector_all(".ta-field [data-ta-action]", "es => es.every(e => e.disabled)"))
        labels = []
        for kind, names in (("instructions", ("공통 지침", "이 표 지침")), ("rules", ("공통 규칙", "이 표 규칙"))):
            guide_tab(page, kind)
            labels.extend(page.get_by_role("textbox", name=name, exact=True).count() == 1 for name in names)
        check("글상자 넷에 접근 가능한 이름", all(labels), labels)
        guide_tab(page, "instructions")
        page.locator("[data-ta-tab=instructions]").press("ArrowRight")
        right = page.evaluate("() => document.activeElement.dataset.taTab === 'rules' && document.activeElement.getAttribute('aria-selected') === 'true' && !document.querySelector('[data-ta-section=rules]').hidden")
        page.locator("[data-ta-tab=rules]").press("ArrowLeft")
        left = page.evaluate("() => document.activeElement.dataset.taTab === 'instructions' && document.activeElement.getAttribute('aria-selected') === 'true' && !document.querySelector('[data-ta-section=instructions]').hidden")
        check("화살표 키로 탭·초점·선택 표시가 함께 이동", right and left, [right, left])
        for width in (320, 480):
            page.evaluate("(w) => { const c = colSizers.find(x => x.box === 'headsDlg'); c.w = w; c.apply(); }", width)
            page.wait_for_timeout(200)
            for kind in ("instructions", "rules"):
                guide_tab(page, kind)
                fit = page.evaluate(FIT_GUIDE)
                check(f"작성요령 · {kind} · {width}px — 가로 넘침 없음", fit["width"] in (width - 1, width) and not fit["bad"] and fit["over"] <= 0 and fit["bodyOver"] <= 0, fit)
                page.locator("#headsDlg").screenshot(path=str(OUT / f"2_guide_{kind}_{width}.png"))
        guide_tab(page, "instructions")
        page.screenshot(path=str(OUT / "2_guide.png"))
        # 「이 표 지침에 붙이기」 → 저장 · 이 표 규칙 저장
        page.locator(".ta-source > summary").first.click()
        page.locator(".ta-source button:has-text('이 표 지침에 붙이기')").click()
        own = guide_field(page, "own", "instructions")
        own_box = own.evaluate("""e => ({text: e.querySelector('textarea').value, state: e.querySelector('.ta-save-state').textContent, dirty: heads.xl.agent.dirty()})""")
        check("「이 표 지침에 붙이기」 — 글상자에 요령이 들어가고 「저장 안 함」", own_box["text"].startswith("[앞표지 작성 요령") and "2. 중앙행정기관명:" in own_box["text"] and own_box["state"] == "저장 안 함" and own_box["dirty"], own_box)
        check("수정한 글상자만 저장·지우기가 켜지고 지침 탭에 미저장 표시", own.locator("[data-ta-action=save]").is_enabled() and own.locator("[data-ta-action=clear]").is_enabled()
              and guide_field(page, "common", "instructions").locator("[data-ta-action=save]").is_disabled() and page.locator("[data-ta-tab=instructions] .ta-tab-dirty").is_visible())
        guide_tab(page, "rules")
        guide_field(page, "own", "rules").locator("textarea").fill("체크는 「[ √ ]」 로")
        guide_tab(page, "instructions")
        check("지침·규칙 탭을 오가도 초안 둘이 남고 각 탭에 미저장 표시", own.locator("textarea").input_value() == own_box["text"]
              and guide_field(page, "own", "rules").locator("textarea").input_value() == "체크는 「[ √ ]」 로"
              and page.locator("[data-ta-tab=instructions] .ta-tab-dirty").is_visible() and page.locator("[data-ta-tab=rules] .ta-tab-dirty").is_visible())
        page.locator(".tbl-corner-guide").click()   # 저장 안 한 글이 있는 채로 같은 표의 둘째 아이콘을 다시 누름 — 열을 다시 그리지 않는다(글이 지워지면 안 됨)
        page.wait_for_timeout(400)
        keep = own.evaluate("""e => ({text: e.querySelector('textarea').value.startsWith('[앞표지 작성 요령'), dirty: heads.xl.agent.dirty(), kind: heads.dlg})""")
        check("저장 안 한 글이 있을 때 둘째 아이콘을 다시 눌러도 열은 그대로(글이 안 지워짐)", keep["text"] and keep["dirty"] and keep["kind"] == "tableAgent", keep)
        own.locator("[data-ta-action=save]").click()
        page.wait_for_function("() => document.querySelector('.ta-field[data-ta-scope=own][data-ta-field=instructions] .ta-save-state').dataset.state === 'saved'", timeout=20000)
        check("지침을 저장해도 다른 탭의 규칙 초안·미저장 표시는 유지", guide_field(page, "own", "rules").locator("textarea").input_value() == "체크는 「[ √ ]」 로"
              and page.evaluate("() => heads.xl.agent.dirty()") and page.locator("[data-ta-tab=rules] .ta-tab-dirty").is_visible())
        guide_tab(page, "rules")
        guide_field(page, "own", "rules").locator("[data-ta-action=save]").click()
        page.wait_for_function("() => !heads.xl.agent.dirty()", timeout=20000)
        page.wait_for_timeout(600)
        saved = requests.get(f"{base}/api/docs/{doc}/headings/tables/{tid}/agent", timeout=60).json()
        check("저장 — 이 표 지침(붙인 요령) · 이 표 규칙이 작업에 남고 묶음 글에 든다",
              saved["own"]["instructions"].startswith("[앞표지 작성 요령") and saved["own"]["rules"] == "체크는 「[ √ ]」 로" and saved["own"]["version"] == 2
              and "### 이 표 규칙\n체크는 「[ √ ]」 로" in saved["prompt"], {k: saved["own"][k] for k in ("rules", "version")})
        check("미리보기 글이 저장 뒤 새로", page.evaluate("() => document.querySelector('.ta-preview pre').textContent.includes('### 이 표 규칙\\n체크는')"))
        check("저장 뒤에는 탭 미저장 표시가 사라지고 다시 저장은 꺼짐", page.eval_on_selector_all(".ta-tab-dirty", "es => es.every(e => !e.getClientRects().length)")
              and page.eval_on_selector_all(".ta-field [data-ta-action=save]", "es => es.every(e => e.disabled)"))
        check("둘째 아이콘 — 저장하면 「적어 둔 글 있음」 표시(.has)", page.evaluate("(t) => { const g = document.querySelector('.tbl-corner-guide'); return g.dataset.for === t && g.style.display !== 'none' && g.classList.contains('has'); }", tid))

        # 저장 응답이 늦는 동안 계속 적어도 새 초안은 덮이지 않는다(응답만 보류, 저장 API는 진짜).
        agent_url = f"{base}/api/docs/{doc}/headings/tables/{tid}/agent"
        held_save = {}

        def hold_save(route):
            if route.request.method != "PUT":
                route.continue_()
                return
            response = route.fetch()
            held_save.update(route=route, response=response, body=json.loads(route.request.post_data))

        page.route(agent_url, hold_save)
        rule_box = guide_field(page, "own", "rules")
        original_rule = saved["own"]["rules"]
        submitted_rule = original_rule + "\n날짜는 YYYY.MM.DD로"
        later_rule = submitted_rule + "\n저장 응답 전에 추가한 초안"
        rule_box.locator("textarea").fill(submitted_rule)
        rule_box.locator("[data-ta-action=save]").click()
        for _ in range(50):
            if "route" in held_save:
                break
            page.wait_for_timeout(100)
        check("저장 중에는 모든 저장·지우기를 끄고 글 입력은 허용", "route" in held_save
              and rule_box.locator(".ta-save-state").get_attribute("data-state") == "saving"
              and page.eval_on_selector_all(".ta-field [data-ta-action]", "es => es.every(e => e.disabled)") and rule_box.locator("textarea").is_enabled())
        rule_box.locator("textarea").fill(later_rule)
        held_save["route"].fulfill(response=held_save["response"])
        page.wait_for_function("() => document.querySelector('.ta-field[data-ta-scope=own][data-ta-field=rules] .ta-save-state').dataset.state === 'dirty'", timeout=20000)
        check("늦은 저장 응답 — 보낸 글만 저장 기준, 이후 초안·미저장 표시는 보존", held_save["body"] == {"rules": submitted_rule, "version": 2}
              and rule_box.locator("textarea").input_value() == later_rule and rule_box.locator("textarea").evaluate("e => e.defaultValue") == submitted_rule
              and rule_box.locator("[data-ta-action=save]").is_enabled() and page.locator("[data-ta-tab=rules] .ta-tab-dirty").is_visible()
              and requests.get(agent_url, timeout=60).json()["own"]["rules"] == submitted_rule)
        page.unroute(agent_url, hold_save)
        rule_box.locator("textarea").fill(original_rule)
        rule_box.locator("[data-ta-action=save]").click()
        page.wait_for_function("() => !heads.xl.agent.dirty()", timeout=20000)
        check("저장 지연 검사 뒤 원래 규칙으로 복구", requests.get(agent_url, timeout=60).json()["own"]["rules"] == original_rule)

        # ---- 3. 표 채우기 열 — LLM 없는 서버
        page.locator(".ta-wrap button:has-text('에이전트로 표 채우기')").click()
        page.wait_for_selector(".tfl-wrap .tfl-sum")
        page.wait_for_function("() => /^채울 칸 /.test(document.querySelector('.tfl-sum').textContent)", timeout=30000)
        v = page.evaluate("""() => { const w = document.querySelector('.tfl-wrap'); return {title: document.getElementById('headsDlgTitle').textContent, kind: heads.dlg, sum: w.querySelector('.tfl-sum').textContent,
            basis: w.querySelectorAll('p.hnote')[1].textContent, run: w.querySelector('button.primary').disabled, state: w.querySelector('.tfl-state').textContent,
            opts: [...w.querySelectorAll('.tfl-opt')].map((l) => [l.textContent, l.querySelector('input').checked])}; }""")
        check("표 채우기 열 — 채울 칸 요약(꼴마다 수)", v["title"] == f"표 채우기 · {tid}" and v["kind"] == "tblFill" and v["sum"].startswith(f"채울 칸 {dry['counts']['targets']}개 — ") and "체크" in v["sum"]
              and "빈 칸" in v["sum"], v)
        check("기준 줄 — 작성요령 건수 · 「작성 요령」 표", "문서의 작성요령 1건(「작성 요령」 표 1)" in v["basis"] and "칸 입력 규칙" in v["basis"], v["basis"])
        check("LLM 없는 서버 — 단추 꺼짐 + 까닭", v["run"] is True and v["state"] == "LLM 을 쓸 수 없습니다", v)
        check("옵션 — 이 문서의 글(켬 · 글자 수) · 채워진 칸(끔)", v["opts"][0][1] is True and "이 문서의 글도 자료로 — " in v["opts"][0][0] and v["opts"][1] == ["채워진 칸도 다시 제안", False], v["opts"])

        # ---- 4. 가짜 LLM — 미리보기는 진짜 응답에 llm: true 만, 제안은 진짜 미리보기의 칸으로 지어 준다
        y2 = by["Y2"]
        fake_fills = [
            {"ref": "Y2", "cell": y2["cell"], "row": 1, "col": 24, "name": y2["name"], "form": "check", "now": y2["now"], "text": y2["now"].replace("일반[", "일반[√", 1),
             "source": "보안: 일반과제", "where": "material", "reason": "자료에 일반과제라고 적힘", "quoted": True, "warn": []},
            {"ref": "W3", "cell": by["W3"]["cell"], "row": 2, "col": 22, "name": by["W3"]["name"], "form": "blank", "now": "", "text": "조선해양산업기술개발",
             "source": "세부사업명: 조선해양산업기술개발", "where": "material", "reason": "세부사업명 줄", "quoted": True, "warn": []},
            {"ref": "W4", "cell": by["W4"]["cell"], "row": 3, "col": 22, "name": by["W4"]["name"], "form": "blank", "now": "", "text": "지어낸 내역사업",
             "source": "자료에 없는 구절", "where": "", "reason": "추정", "quoted": False, "warn": ["근거 구절을 자료에서 못 찾음"]},
        ]
        sent = []

        def fake(route):
            body = json.loads(route.request.post_data or "{}")
            if body.get("dry"):
                resp = route.fetch()
                data = resp.json()
                data["llm"] = True
                route.fulfill(response=resp, json=data)
                return
            sent.append(body)
            live = requests.post(fill_url, json={**body, "dry": True}, timeout=120).json()
            route.fulfill(json={**live, "llm": True, "fills": fake_fills, "rejected": [{"ref": "A3", "text": "머리 칸", "why": "채울 칸이 아님(머리 칸 · 셈하는 칸 · 이미 채운 칸 · 고른 범위 밖)"}],
                                "counts": {**live["counts"], "fills": 3, "clean": 2, "warn": 1, "rejected": 1, "left": live["counts"]["targets"] - 3},
                                "answer": "자료에 있는 두 칸을 채우고 한 칸은 근거가 약함", "call": {"backend": "sdk", "model": "가짜", "effort": "low", "ms": 4200, "costUsd": 0.031, "error": None}})
        page.route("**/tables/*/fill", fake)
        page.evaluate("(t) => tblFillView(t)", tid)
        page.wait_for_function("() => { const b = document.querySelector('.tfl-wrap button.primary'); return b && !b.disabled; }", timeout=30000)
        page.fill(".tfl-wrap textarea", "세부사업명: 조선해양산업기술개발\n보안: 일반과제")
        page.locator(".tfl-wrap button.primary:has-text('채우기 제안 받기')").click()
        page.wait_for_selector("table.tfl-list tbody tr", timeout=30000)
        rows = page.evaluate("""() => [...document.querySelectorAll('table.tfl-list tbody tr')].map((tr) => ({warn: tr.classList.contains('warn'), on: tr.querySelector('input').checked, ref: tr.children[1].querySelector('button').textContent,
            form: tr.children[1].querySelector('.hb').textContent, val: tr.children[3].textContent, why: tr.children[4].textContent}))""")
        check("요청 — 자료 글 · 이 문서 글 켬 · 범위 없음", len(sent) == 1 and sent[0]["material"].startswith("세부사업명") and sent[0]["useDoc"] is True and sent[0]["overwrite"] is False and "range" not in sent[0], sent)
        check("제안 목록 — 3줄 · 경고 없는 둘만 고름", [(r["ref"], r["on"], r["warn"]) for r in rows] == [("Y2", True, False), ("W3", True, False), ("W4", False, True)], rows)
        check("제안 줄 — 꼴 표지 · 지금 → 제안 · 근거 구절 · 경고", rows[0]["form"] == "체크" and "→" in rows[0]["val"] and "일반[√" in rows[0]["val"] and rows[1]["val"] == "조선해양산업기술개발"
              and "세부사업명: 조선해양산업기술개발" in rows[1]["why"] and "근거 구절을 자료에서 못 찾음" in rows[2]["why"], rows)
        head = page.evaluate("() => ({answer: document.querySelector('.tfl-answer').textContent, btn: document.querySelector('.tfl-result button.primary').textContent, rej: document.querySelector('.tfl-rej').textContent})")
        check("요약 — 제안·경고·검사에서 뺌·못 채운 칸·시간·비용 · 반영 단추에 고른 수", head["answer"].startswith("제안 3칸(경고 1) · 검사에서 뺌 1 · 못 채운 칸 ") and "4.2초" in head["answer"] and "$0.031" in head["answer"]
              and head["btn"] == "고른 2칸 문서에 반영" and "A3 — 채울 칸이 아님" in head["rej"], head)
        page.locator("table.tfl-list tbody tr").nth(1).hover()
        check("제안 줄에 올리면 문서의 그 칸 표시", page.evaluate("(c) => { const e = document.querySelector('#doc td.tfl-hit'); return !!e && e.dataset.cell === c; }", by["W3"]["cell"]))
        page.screenshot(path=str(OUT / "4_proposals.png"))

        # ---- 5. 문서에 반영(진짜 서버) — 고른 둘만 · 실행 취소 1개
        undo0 = page.evaluate("() => state.undo")
        page.locator(".tfl-result button.primary").click()
        page.wait_for_function("(c) => { const e = document.querySelector(`#doc td[data-cell=\"${c}\"]`); return e && e.textContent.includes('조선해양산업기술개발'); }", arg=by["W3"]["cell"], timeout=120000)
        after = page.evaluate("""([w3, y2, w4]) => { const t = (c) => document.querySelector(`#doc td[data-cell="${c}"]`).textContent;
            return {w3: t(w3), y2: t(y2), w4: t(w4).trim(), undo: state.undo, busy: state.busy, left: [...document.querySelectorAll('table.tfl-list tbody tr')].map((tr) => tr.children[1].querySelector('button').textContent),
                    btn: document.querySelector('.tfl-result button.primary').textContent, hit: document.querySelectorAll('#doc td.tfl-hit').length}; }""", [by["W3"]["cell"], y2["cell"], by["W4"]["cell"]])
        check("문서의 칸에 글이 들어감 — 고른 둘만", "조선해양산업기술개발" in after["w3"] and "일반[√" in after["y2"].replace(" ", "") and after["w4"] == "", after)
        check("실행 취소 1개 · 넣은 제안은 목록에서 빠짐", after["undo"] == undo0 + 1 and after["left"] == ["W4"] and after["btn"] == "고른 0칸 문서에 반영" and after["hit"] == 0, after)
        srv = {c["id"]: c["text"] for c in next(b for b in requests.get(f"{base}/api/docs/{doc}", timeout=120).json()["blocks"] if b["id"] == tid)["cells"]}
        check("서버 문서도 같다", srv[by["W3"]["cell"]] == "조선해양산업기술개발" and "일반[√" in srv[y2["cell"]] and srv[by["W4"]["cell"]] == "", (srv[by["W3"]["cell"]], srv[y2["cell"]]))
        page.wait_for_function(f"() => document.querySelector('.tfl-sum').textContent.startsWith('채울 칸 {dry['counts']['targets'] - 2}개')", timeout=30000)
        check("남은 채울 칸 수가 다시 세어짐", True)
        page.screenshot(path=str(OUT / "5_applied.png"))

        # ---- 6. 범위로 열기 — 열 제목·요약에 범위 · 앞 제안은 버림
        page.evaluate("(t) => tblFillView(t, {r0: 0, c0: 0, r1: 4, c1: 29})", tid)
        page.wait_for_function("() => /고른 범위 안만/.test(document.querySelector('.tfl-sum').textContent)", timeout=30000)
        rng = page.evaluate("() => ({title: document.getElementById('headsDlgTitle').textContent, ident: document.querySelector('.tfl-wrap .ta-ident').textContent, rows: document.querySelectorAll('table.tfl-list tbody tr').length})")
        check("범위 — 제목 「A1:AD5」 · 식별 줄 · 앞 제안 없음", rng["title"] == f"표 채우기 · {tid} A1:AD5" and "범위 A1:AD5" in rng["ident"] and rng["rows"] == 0, rng)
        # 표 메뉴에서 다시 — 문서가 바뀐 뒤에도 메뉴·열이 열린다
        page.unroute("**/tables/*/fill")
        corner(page, tid)
        item(page, "에이전트로 표 채우기").click()
        page.wait_for_function("() => heads.dlg === 'tblFill' && /^채울 칸 /.test(document.querySelector('.tfl-sum').textContent)", timeout=30000)
        check("표 메뉴 「에이전트로 표 채우기…」 로 열림", page.evaluate("(t) => document.getElementById('headsDlgTitle').textContent === `표 채우기 · ${t}`", tid))
        browser.close()
    bad = [e for e in errors if "favicon" not in e]
    check("콘솔 오류 없음", not bad, bad[:5])
finally:
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()

print(f"\n{'FAIL ' + str(len(fails)) if fails else 'ALL PASS'}", flush=True)
sys.exit(1 if fails else 0)

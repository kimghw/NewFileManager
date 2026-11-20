"""`/workflow` 의 「요구사항」(spec_워크플로우 ② §18-20 · design.md §24 — app/static/workflow_reqs.js · app/user_reqs_api.py) 화면 확인 —
임시 서버(임시 요구사항 파일 · 임시 조립 저장소, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 흉내 없이 진짜 끝점으로(옛 서버 흉내 하나만 응답을 바꾼다).

    python -X utf8 tools/smoke_reqs_ui.py <그림·임시 폴더> [--port 18790]

2026-11-21 사용자 「도구, 단계, 워크플로우 에 대한 사용자 요구사항을 관리 할 수 있고 웹에서 도구에서 볼 수 있게 해줘,, 우클릭이나 아이콘을 넣고 선택하면 될듯.」

보는 것:
- ① 상단 바의 「요구사항」 · 다이어그램 보기의 아이콘(워크플로우 머리 · 묶음 머리) — 처음엔 수가 없다.
- ② 목차의 워크플로우를 오른쪽 단추로 → 메뉴(머리 = 무엇을 눌렀나 · 「요구사항 보기」 · 「요구사항 적기…」) → 「적기」 = 오른쪽 열(본문 옆 · 본문이 좁아진다)이 열리고 글 칸에 초점 → 적으면 「요청」 으로 남고 아이콘 · 상단 바에 수.
- ③ 상태를 「반영」 으로 · 「고치기」 로 정리 · 사양서 자리를 적는다 → 파일(서버)에 그대로.
- ④ 단계 줄(「헤딩 · 표 분석」)을 오른쪽 단추로 → 그 줄의 **도구**(이관형)의 요구사항 · 묶음 머리의 아이콘 = 그 단계의 요구사항.
- ⑤ 조립 폼 — 줄 카드를 오른쪽 단추로 → 그 도구 · 요구사항이 있는 도구의 카드 · 목차 줄에 수 · 「도구 설명」 열의 머리에 아이콘 · 열은 폼의 오른쪽 열 위에 겹쳐 선다(본문을 더 좁히지 않는다) · 조립(줄)은 안 바뀐다.
  틀을 「N → 1」 로 바꾸면 같은 줄 key 도 다른 도구다(취합형의 「헤딩 · 표 분석」 에는 요구사항이 없다).
- ⑥ 「모든 요구사항」 — 위 = 아직 반영 안 된 것 · 아래 = 대상마다 몇 건(누르면 그 대상) · 대상을 골라 적기 · 지우기(한 번 더 묻는다).
- ⑦ 목록 보기 — 절 머리 · 단계 머리의 아이콘 · 단계 줄을 오른쪽 단추로.
- ⑧ Esc · 좁은 창(겹쳐 선다) · Shift + 오른쪽 단추는 메뉴를 안 띄운다 · 콘솔 오류 없음.
- ⑨ 요구사항 끝점을 모르는 서버(404 — 응답만 바꿈) → 「서버를 다시 켠 뒤에 …」 한 줄 · 페이지는 그대로 선다."""
import argparse
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
ap.add_argument("--port", type=int, default=18790)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1",
       "NFM_TASKS": str(tmp / "tasks.json"), "NFM_FORM_FILES": str(tmp / "form_files"), "NFM_AGENT_NOTES": str(tmp / "agent_notes.json"), "NFM_TOOL_NAMES": str(tmp / "tool_names.json"),
       "NFM_REQS": str(tmp / "requirements.json")}   # 요구사항 파일 — 늘 임시(저장소의 reqs/requirements.json 을 고치지 않는다)
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_FLOW_EXEC"):
    env.pop(k, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []
JOB, FLOW, STAGE, TOOL = "plan_to_report", "flow:plan_to_report", "stage:plan_to_report.review", "tool:relay.heads"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:900] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def wait_server(timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if requests.get(base + "/api/headings/llm", timeout=2).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.4)
    raise SystemExit("서버가 안 뜸")


# 「요구사항」 열 — 열렸나 · 본문 옆인가 겹쳤나 · 대상 · 머리의 이름 · 항목 [상태, 한 말, 정리, 사양서, 출처] · 안내 · 모든 요구사항의 묶음 · 초점
PANEL = """() => { const a = document.getElementById('wfReqs'); if (!a || a.hidden) return { on: false, body: document.body.className };
  const t = (q, r) => { const e = (r || a).querySelector(q); return e ? e.textContent : ''; }, m = document.getElementById('wfMain').getBoundingClientRect(), r = a.getBoundingClientRect(), act = document.activeElement;
  return { on: true, over: document.body.classList.contains('wf-reqs-over'), pos: getComputedStyle(a).position, beside: r.left >= m.right - 1, width: Math.round(r.width), mainW: Math.round(m.width),
    target: a.dataset.target, kind: t('.wf-reqs-kind'), name: t('.wf-reqs-who > b'), group: t('.wf-reqs-who > .wf-reqs-group'), hint: t('.wf-reqs-hint'), off: t('.wf-reqs-off'), warn: t('.wf-reqs-warn'),
    items: [...a.querySelectorAll('.wf-reqs-item')].map((li) => [li.dataset.state || '', t('.wf-reqs-said', li), t('.wf-reqs-note', li), t('.wf-reqs-spec', li), t('.wf-reqs-src', li), t('.wf-reqs-state', li)]),
    left: [...a.querySelectorAll('.wf-reqs-left .wf-reqs-item')].map((li) => [t('.wf-reqs-said', li), [...li.querySelectorAll('.wf-reqs-others .wf-reqs-to')].map((b) => b.dataset.to)]),
    heads: [...a.querySelectorAll('.wf-reqs-index > h5')].map((x) => x.textContent), rows: [...a.querySelectorAll('.wf-reqs-rows .wf-reqs-go')].map((b) => [b.dataset.to, t('.wf-reqs-go-name', b), t('.wf-reqs-count', b)]),
    more: [...a.querySelectorAll('.wf-reqs-more .wf-reqs-to')].map((b) => [b.dataset.to, b.textContent]), add: !!a.querySelector('.wf-reqs-add textarea'), pick: !!a.querySelector('.wf-reqs-pick'),
    focus: !act || act === document.body ? '' : act.tagName === 'TEXTAREA' && act.closest('.wf-reqs-add') ? 'add' : act.closest('.wf-reqs-head') ? 'head' : act.className }; }"""
# 우클릭 메뉴 — 머리 · 항목 [글, 꺼짐]
MENU = "() => { const m = document.querySelector('.wf-req-menu'); return m ? { head: m.querySelector('.wf-req-menu-head').textContent, items: [...m.querySelectorAll('button')].map((b) => [b.textContent, b.disabled]) } : null; }"
# 아이콘 — 그 자리의 [대상, 수(글), 요청이 남았나, 눌림]
ICONS = "(q) => [...document.querySelectorAll(q)].filter((b) => b.getClientRects().length).map((b) => [b.dataset.req, b.querySelector('.wf-req-n').textContent, b.dataset.open === '1', b.getAttribute('aria-pressed') === 'true'])"
LINES = "() => [...document.querySelectorAll('#wfCompose .wf-lines-group')].map((g) => [...g.querySelectorAll('.wf-line')].map((l) => [l.dataset.unit, l.dataset.role || '']))"


def reqs():
    return requests.get(base + "/api/reqs", timeout=10).json()


def menu_at(page, sel, **kw):
    page.locator(sel).first.click(button="right", **kw)
    page.wait_for_timeout(120)
    return page.evaluate(MENU)


def pick(page, text):
    page.locator(".wf-req-menu button", has_text=text).click()
    page.wait_for_timeout(350)
    return page.evaluate(PANEL)


def settle(page):
    page.wait_for_function("() => { const b = document.querySelector('#wfCompose .wf-lines'); return b && !/검사하는 중/.test(b.textContent) && !!b.querySelector('.wf-lines-check'); }", timeout=30000)
    page.wait_for_timeout(450)


def main():
    wait_server()
    names = reqs()["targets"]
    flow_name, tool_name, stage_name = names[FLOW]["name"], names[TOOL]["name"], names[STAGE]["name"]
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1500, "height": 1000}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/workflow#{JOB}")
        page.wait_for_selector("#wfDiagram .wf-diagram-head h2 .wf-req-ico")

        # ---- ① 상단 바 · 다이어그램의 아이콘
        top = page.evaluate("() => { const b = document.querySelector('.wf-top .wf-req-top'); return b ? [b.textContent, b.getAttribute('aria-pressed')] : null; }")
        head = page.evaluate(ICONS, "#wfDiagram .wf-diagram-head h2 .wf-req-ico")
        stages = page.evaluate(ICONS, "#wfDiagram a.wf-stage-link .wf-req-ico")
        want_stages = [k for k in names if k.startswith(f"stage:{JOB}.")]
        check("① 상단 바에 「요구사항」(수 없음) · 다이어그램의 워크플로우 머리에 아이콘 · 묶음 머리마다 그 단계의 아이콘 — 처음엔 수가 없다",
              top == ["요구사항", "false"] and head == [[FLOW, "", False, False]] and [s[0] for s in stages] == want_stages and all(s[1] == "" for s in stages), [top, head, stages, want_stages])
        check("① 열은 닫혀 있다 · 워크플로우 이름은 그대로(아이콘이 이름에 글을 더하지 않는다)",
              not page.evaluate(PANEL)["on"] and page.evaluate("() => document.querySelector('#wfDiagram .wf-diagram-head h2').textContent") == flow_name)

        # ---- ② 목차의 워크플로우를 오른쪽 단추로 → 적기
        m = menu_at(page, f"#wfNav a[href='#{JOB}']")
        check("② 목차의 워크플로우를 오른쪽 단추로 → 메뉴(머리 「워크플로우 · 이름」 · 「요구사항 보기」 · 「요구사항 적기…」)",
              m and m["head"] == f"워크플로우 · {flow_name}" and [i[0] for i in m["items"]] == ["요구사항 보기", "요구사항 적기…"] and not any(i[1] for i in m["items"]), m)
        before_w = page.evaluate("() => Math.round(document.getElementById('wfMain').getBoundingClientRect().width)")
        p = pick(page, "요구사항 적기")
        check("② 「요구사항 적기…」 → 오른쪽 열이 본문 옆에 선다(겹치지 않고 본문이 그만큼 좁아진다 · 380px) · 머리에 종류 · 이름 · 글 칸에 초점 · 아직 적힌 것 없음",
              p["on"] and not p["over"] and p["beside"] and p["width"] == 380 and p["mainW"] == before_w - 380 and p["target"] == FLOW and p["kind"] == "워크플로우" and p["name"] == flow_name
              and p["focus"] == "add" and p["items"] == [] and "아직 적힌 요구사항이 없습니다" in p["hint"], [p, before_w])
        page.fill("#wfReqs .wf-reqs-add textarea", "이관은 표를 먼저 넣고 글을 넣자")
        page.click("#wfReqs .wf-reqs-add button")
        page.wait_for_selector("#wfReqs .wf-reqs-item")
        p, got = page.evaluate(PANEL), reqs()
        check("② 적으면 「요청」 으로 남는다(화면에서 적음) · 서버에 그 대상으로 · 글 칸은 비워진다",
              [i[:2] + [i[4], i[5]] for i in p["items"]] == [["open", "이관은 표를 먼저 넣고 글을 넣자", "화면에서 적음", "요청"]] and len(got["items"]) == 1 and got["items"][0]["targets"] == [FLOW]
              and got["items"][0]["src"] == "web" and got["counts"] == {FLOW: {"n": 1, "open": 1}} and page.input_value("#wfReqs .wf-reqs-add textarea") == "", [p, got["items"]])
        head = page.evaluate(ICONS, "#wfDiagram .wf-diagram-head h2 .wf-req-ico")
        top = page.evaluate("() => document.querySelector('.wf-top .wf-req-top .wf-req-n').textContent")
        check("② 워크플로우 머리의 아이콘에 수 1(요청이 남은 표시 · 지금 보는 대상이라 눌림) · 상단 바에도 1", head == [[FLOW, "1", True, True]] and top == "1", [head, top])
        page.screenshot(path=str(OUT / "02_flow_reqs.png"), full_page=False)

        # ---- ③ 상태 · 고치기
        rid = got["items"][0]["id"]
        page.select_option("#wfReqs .wf-reqs-item .wf-reqs-state-sel", "done")
        page.wait_for_selector("#wfReqs .wf-reqs-item[data-state=done]")
        head = page.evaluate(ICONS, "#wfDiagram .wf-diagram-head h2 .wf-req-ico")
        check("③ 상태를 「반영」 으로 → 항목 · 서버가 반영 · 아이콘의 「요청이 남음」 표시가 꺼진다(수는 그대로)",
              page.evaluate(PANEL)["items"][0][5] == "반영" and reqs()["items"][0]["state"] == "done" and head == [[FLOW, "1", False, True]], [page.evaluate(PANEL)["items"], head])
        page.locator("#wfReqs .wf-reqs-item button", has_text="고치기").click()
        page.locator("#wfReqs .wf-reqs-editing textarea").nth(1).fill("표 대응을 먼저 돌린다")
        page.locator("#wfReqs .wf-reqs-editing input").first.fill("spec_병합 ② §4")
        page.locator("#wfReqs .wf-reqs-editing button", has_text="저장").click()
        page.wait_for_selector("#wfReqs .wf-reqs-item .wf-reqs-note")
        p, it = page.evaluate(PANEL), reqs()["items"][0]
        check("③ 「고치기」 → 정리 · 사양서 자리를 적어 저장 → 항목에 보이고 서버에 그대로(한 말 · 상태는 그대로)",
              "표 대응을 먼저 돌린다" in p["items"][0][2] and "spec_병합 ② §4" in p["items"][0][3] and it["note"] == "표 대응을 먼저 돌린다" and it["spec"] == "spec_병합 ② §4"
              and it["said"] == "이관은 표를 먼저 넣고 글을 넣자" and it["state"] == "done" and it["id"] == rid, [p["items"], it])

        # ---- ④ 단계 줄 = 그 줄의 도구 · 묶음 머리의 아이콘 = 그 단계
        m = menu_at(page, f"#wfDiagram a.wf-node[href='#{JOB}--review--heads']")
        check("④ 단계 줄 「헤딩 · 표 분석」 을 오른쪽 단추로 → 그 줄의 도구(머리 「도구 · 이름」)", m and m["head"] == f"도구 · {tool_name}", m)
        p = pick(page, "요구사항 적기")
        check("④ → 그 도구(이관형)의 요구사항 — 종류 「도구」 · 묶음 「워크플로우 도구 · 1 → N」", p["target"] == TOOL and p["kind"] == "도구" and p["name"] == tool_name and "1 → N" in p["group"] and p["items"] == [], p)
        page.fill("#wfReqs .wf-reqs-add textarea", "분석 이름을 구조 분석으로")
        page.keyboard.press("Control+Enter")
        page.wait_for_selector("#wfReqs .wf-reqs-item")
        check("④ Ctrl + Enter 로 적는다 → 그 도구의 요구사항 1건", reqs()["counts"].get(TOOL) == {"n": 1, "open": 1}, reqs()["counts"])
        page.locator(f"#wfDiagram a.wf-stage-link .wf-req-ico[data-req='{STAGE}']").click()
        page.wait_for_timeout(350)
        p = page.evaluate(PANEL)
        check("④ 묶음 머리의 아이콘을 누르면 그 단계의 요구사항(주소는 안 바뀐다 — 링크를 따라가지 않는다)",
              p["target"] == STAGE and p["kind"] == "단계" and p["name"] == stage_name and p["group"] == flow_name and page.evaluate("() => location.hash") == f"#{JOB}", [p, page.evaluate("() => location.hash")])
        page.locator(f"#wfDiagram a.wf-node[href='#{JOB}--review--heads']").click()
        page.wait_for_timeout(300)
        det = page.evaluate(ICONS, "#wfDetail > .wf-badges .wf-req-ico")
        check("④ 그 단계 줄을 고르면 오른쪽 설명의 꼬리표 줄에 그 도구의 아이콘(수 1)", det == [[TOOL, "1", True, False]], det)

        # ---- ⑤ 조립 폼 — 카드 · 목차의 도구 · 「도구 설명」 열 · 겹쳐 서기
        page.keyboard.press("Escape")
        page.locator("#wfReqs .wf-reqs-close").click()
        check("⑤ 「닫기」 → 열이 닫히고 본문 폭이 돌아온다", not page.evaluate(PANEL)["on"] and page.evaluate("() => Math.round(document.getElementById('wfMain').getBoundingClientRect().width)") == before_w)
        page.click("#wfNav .wf-nav-tool[data-tool=heads]")
        settle(page)
        lines0 = page.evaluate(LINES)
        cards = page.evaluate(ICONS, "#wfCompose .wf-line-cell .wf-req-ico")
        helph = page.evaluate(ICONS, "#wfCompose .wf-help-head .wf-req-ico")
        dots = page.evaluate("() => [...document.querySelectorAll('#wfNav .wf-nav-tool')].filter((b) => b.querySelector('.wf-req-dot')).map((b) => [b.dataset.tool, b.querySelector('.wf-req-dot').textContent])")
        n_heads = sum(1 for g in lines0 for l in g if "heads" in l[0].split("+"))
        check("⑤ 조립 폼 — 요구사항이 있는 도구(헤딩 · 표 분석)의 카드에만 아이콘(수 1) · 「도구 설명」 열의 머리에 그 도구의 아이콘 · 목차의 그 도구 줄에 수",
              n_heads >= 1 and len(cards) >= n_heads and {c[0] for c in cards} == {TOOL} and all(c[1] == "1" for c in cards) and helph == [[TOOL, "1", True, False]] and dots == [["heads", "1"]], [cards, helph, dots, n_heads])
        m = menu_at(page, "#wfCompose .wf-line-cell[data-unit=heads] .wf-line-name > b")
        check("⑤ 줄 카드를 오른쪽 단추로 → 그 도구의 메뉴(「요구사항 보기 — 1건 · 요청 1」)", m and m["head"] == f"도구 · {tool_name}" and m["items"][0][0] == "요구사항 보기 — 1건 · 요청 1", m)
        w_form = page.evaluate("() => Math.round(document.getElementById('wfMain').getBoundingClientRect().width)")
        p = pick(page, "요구사항 보기")
        check("⑤ → 열이 폼의 오른쪽 열 위에 겹쳐 선다(본문 폭은 그대로 · 화면 오른쪽 끝) · 그 도구의 요구사항 1건 · 머리에 초점",
              p["on"] and p["over"] and p["pos"] == "fixed" and p["mainW"] == w_form and p["target"] == TOOL and [i[1] for i in p["items"]] == ["분석 이름을 구조 분석으로"] and p["focus"] == "head", p)
        check("⑤ 요구사항을 여닫아도 조립(줄)은 안 바뀐다 · 고른 도구도 그대로", page.evaluate(LINES) == lines0 and page.evaluate("() => document.querySelector('#wfCompose .wf-help').dataset.unit") == "heads")
        page.screenshot(path=str(OUT / "05_compose_reqs.png"), full_page=False)
        m = menu_at(page, "#wfNav .wf-nav-tool[data-tool=link]")
        check("⑤ 목차의 워크플로우 도구를 오른쪽 단추로 → 그 도구(요구사항이 없으면 수 없이 「요구사항 보기」)", m and m["head"].startswith("도구 · ") and m["items"][0][0] == "요구사항 보기", m)
        page.keyboard.press("Escape")
        check("⑤ Esc → 메뉴만 닫힌다(열은 그대로)", page.evaluate(MENU) is None and page.evaluate(PANEL)["on"])
        page.locator("#wfReqs .wf-reqs-close").click()
        page.check("#wfCompose .wf-io-opt[data-shape=gather] input")
        settle(page)
        m = menu_at(page, "#wfCompose .wf-line-cell[data-unit=heads] .wf-line-name > b")
        p = pick(page, "요구사항 보기")
        check("⑤ 틀을 「N → 1」 로 → 같은 줄 key 도 다른 도구(취합형의 「헤딩 · 표 분석」 — 요구사항 없음 · 카드에 아이콘 없음)",
              p["target"] == "tool:gather.heads" and "N → 1" in p["group"] and p["items"] == [] and page.evaluate(ICONS, "#wfCompose .wf-line-cell .wf-req-ico") == [], [m, p])
        page.locator("#wfReqs .wf-reqs-close").click()
        page.locator("#wfCompose form button", has_text="취소").click()
        page.wait_for_timeout(250)

        # ---- ⑥ 모든 요구사항
        page.click(".wf-top .wf-req-top")
        page.wait_for_timeout(350)
        p = page.evaluate(PANEL)
        check("⑥ 상단 바 「요구사항」 → 모든 요구사항: 위 = 아직 반영 안 된 것(도구의 요청 1건 — 대상 칩) · 아래 = 대상마다 몇 건(등록부의 차례: 워크플로우 › 워크플로우 도구) · 대상을 골라 적는 칸",
              p["on"] and p["target"] == "" and p["name"] == "모든 요구사항" and "2건 · 반영 안 된 것 1건" in p["group"] and p["left"] == [["분석 이름을 구조 분석으로", [TOOL]]]
              and p["heads"] == ["워크플로우", names[TOOL]["group"]] and p["rows"] == [[FLOW, flow_name, "1건"], [TOOL, tool_name, "1건 · 요청 1"]] and p["pick"] and not p["over"], p)
        add = page.locator("#wfReqs .wf-reqs-add button")
        page.fill("#wfReqs .wf-reqs-add textarea", "문서 검토에서 표도 같이 보여 줘")
        off = add.is_disabled()
        page.select_option("#wfReqs .wf-reqs-pick", STAGE)
        add.click()
        page.wait_for_function("() => document.querySelectorAll('#wfReqs .wf-reqs-rows .wf-reqs-go').length === 3")
        p = page.evaluate(PANEL)
        check("⑥ 대상을 안 고르면 「적기」 가 꺼져 있다 · 단계를 골라 적으면 그 단계가 목록에(워크플로우 › 그 워크플로우의 단계 › 워크플로우 도구) · 반영 안 된 것은 새로 적은 것부터",
              off and [r[0] for r in p["rows"]] == [FLOW, STAGE, TOOL] and p["heads"] == ["워크플로우", flow_name, names[TOOL]["group"]] and [x[0] for x in p["left"]] == ["문서 검토에서 표도 같이 보여 줘", "분석 이름을 구조 분석으로"]
              and reqs()["counts"].get(STAGE) == {"n": 1, "open": 1}, [off, p["rows"], p["heads"], p["left"]])
        page.locator(f"#wfReqs .wf-reqs-rows .wf-reqs-go[data-to='{FLOW}']").click()
        page.wait_for_timeout(350)
        p = page.evaluate(PANEL)
        check("⑥ 대상의 줄을 누르면 그 대상만 · 워크플로우에는 「이 워크플로우의 단계에 적힌 것」 칩", p["target"] == FLOW and p["more"] == [[STAGE, f"{stage_name} 1건"]], p)
        page.locator("#wfReqs .wf-reqs-item button", has_text="지우기").click()
        ask = page.evaluate("() => (document.querySelector('#wfReqs .wf-reqs-ask') || {}).textContent || ''")
        still = len(reqs()["items"])
        page.locator("#wfReqs .wf-reqs-acts .btn.danger").click()
        page.wait_for_function("() => !document.querySelector('#wfReqs .wf-reqs-item')")
        check("⑥ 「지우기」 는 한 번 더 묻는다(그 자리에서) → 지우면 서버에서도 없어지고 아이콘의 수가 비워진다",
              "지울까요" in ask and still == 3 and len(reqs()["items"]) == 2 and FLOW not in reqs()["counts"] and page.evaluate("() => document.querySelector('.wf-top .wf-req-top .wf-req-n').textContent") == "2", [ask, still])

        # ---- ⑦ 목록 보기
        page.locator("#wfReqs .wf-reqs-close").click()
        page.click("#wfViewList")
        page.wait_for_selector(f"section#{JOB} > h2 .wf-req-ico")
        sec = page.evaluate(ICONS, f"section#{JOB} > h2 .wf-req-ico")
        sth = page.evaluate(ICONS, f"section#{JOB} li.wf-stage .wf-stage-head > h3 .wf-req-ico")
        com = page.evaluate(ICONS, "section#common-tables > h2 .wf-req-ico")
        check("⑦ 목록 보기 — 워크플로우 절 · 단계 머리 · 도구 절의 머리에 아이콘(단계 「문서 검토」 에 수 1)",
              sec == [[FLOW, "", False, False]] and [s[0] for s in sth] == want_stages and sth[0][1] == "1" and com == [["common:tables", "", False, False]], [sec, sth, com])
        m = menu_at(page, f"section#{JOB} details.wf-step[data-step=heads] > summary .wf-name")
        check("⑦ 목록의 단계 줄을 오른쪽 단추로 → 그 줄의 도구", m and m["head"] == f"도구 · {tool_name}" and m["items"][0][0].startswith("요구사항 보기 — 1건"), m)
        page.keyboard.press("Escape")
        page.locator("section#common-tables > h2 .wf-req-ico").click()
        page.wait_for_timeout(350)
        p = page.evaluate(PANEL)
        check("⑦ 도구 절의 아이콘 → 그 도구(등록부의 도구)의 요구사항(묶음 이름이 종류와 같은 말이면 두 번 적지 않는다)", p["target"] == "common:tables" and p["kind"] == "도구" and p["name"] == names["common:tables"]["name"] and p["group"] == "", p)

        # ---- ⑧ Esc · 좁은 창 · Shift
        page.locator("#wfReqs .wf-reqs-head h3").focus()
        page.keyboard.press("Escape")
        check("⑧ 열 안에서 Esc → 열이 닫힌다", not page.evaluate(PANEL)["on"])
        page.locator(f"#wfNav a[href='#{JOB}']").click(button="right", modifiers=["Shift"])
        page.wait_for_timeout(120)
        check("⑧ Shift + 오른쪽 단추 → 요구사항 메뉴를 띄우지 않는다(브라우저의 메뉴)", page.evaluate(MENU) is None)
        page.keyboard.press("Escape")
        page.set_viewport_size({"width": 1000, "height": 900})
        page.click(".wf-top .wf-req-top")
        page.wait_for_timeout(350)
        p = page.evaluate(PANEL)
        over = page.evaluate("() => { const m = document.documentElement; return m.scrollWidth > m.clientWidth + 1; }")
        check("⑧ 좁은 창(1000px) — 열이 겹쳐 선다(본문을 좁히지 않는다 · 가로 넘침 없음)", p["on"] and p["pos"] == "fixed" and p["width"] == 380 and not over, [p, over])
        page.screenshot(path=str(OUT / "08_narrow.png"), full_page=False)
        page.locator("#wfReqs .wf-reqs-close").click()
        check("콘솔 오류 없음", not errors, errors)

        # ---- ⑨ 요구사항 끝점을 모르는 서버
        old = ctx.new_page()
        old.route(re.compile(r"/api/reqs(\?.*)?$"), lambda route: route.fulfill(status=404, content_type="application/json", body='{"detail":"Not Found"}'))
        old.set_viewport_size({"width": 1500, "height": 1000})
        old.goto(f"{base}/workflow#{JOB}")
        old.wait_for_selector("#wfDiagram .wf-diagram-head h2")
        old.click(".wf-top .wf-req-top")
        old.wait_for_timeout(400)
        p = old.evaluate(PANEL)
        check("⑨ 요구사항 끝점을 모르는 서버(404) → 「서버를 다시 켠 뒤에 볼 수 있습니다」 한 줄 · 페이지(다이어그램)는 그대로 선다",
              p["on"] and "서버를 다시 켠 뒤에" in p["off"] and not p["add"] and old.evaluate("() => document.querySelectorAll('#wfDiagram a.wf-node').length") > 0, p)
        old.close()
        br.close()


try:
    main()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'FAIL' if fails else 'PASS'} — 떨어진 것 {len(fails)}: {fails}" if fails else "\nPASS — 모두 통과")
sys.exit(1 if fails else 0)

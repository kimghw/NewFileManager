"""에이전트 설정 페이지(spec_에이전트 ② §5 — app/static/agents.html · agents.js · agents.css · app/agents_api.py) 화면 확인 — 임시 서버(임시 작업 폴더 · 임시 설정 파일, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.
끝점은 모두 진짜(흉내 없음).

- 시작 화면(문서 없음): 상단 바 오른쪽 끝의 링크 「에이전트 설정」(/agents · 새 탭 · 글 없이 아이콘만 — 2026-11-16) — 시작 화면은 agents.js 를 읽지 않는다.
- 페이지 /agents: 상단 줄(제목 · 「에이전트 21개」 · 「LLM 꺼짐」 · 「워크플로우」) · 목차(전체 보기 · 실행 기록 · 묶음 일곱 · 에이전트 21) · 전체 보기 = 묶음 일곱 · 에이전트 21줄(작업 번호 01~21· 이름 · 쓰는 곳 · 역할 · 모델 — 넓은 폭에서 네 칸).
- 한 에이전트(자리 연결 검토 — 주소 #merge_links · 두 단): ① 작업 번호 ② 역할 ③ 모델·생각 깊이 → 저장 안 한 값은 다른 화면에 갔다 와도 남음(목차 「저장 안 됨」) → 「저장」 → 전체 보기 줄에 「M-1」·「Sonnet 5.5」(여기서 정함)·「고침」 ·
  겹치는 작업 번호는 거절 · 「고친 것 버리기」 · 「모두 기본으로」(두 번). ④ 프롬프트의 차례 = 계약(읽기만) → 판단 지침(저장소 파일) → 할 일 프롬프트 → 양식 정보 → 자료.
- 고칠 수 있는 프롬프트: 헤딩 지침(레터 규칙식 제안)과 템플릿 정리 스킬을 그 자리에서 고쳐 저장 → 「고침 · 내 사본 판 1」 → 「기본으로 되돌리기」(두 번).
- 주소: /agents#tpl_agent 로 바로 그 에이전트 · 모르는 id 는 전체 보기.
- 실행 기록: 문서를 올려 2단계까지 돌린 뒤 템플릿 서식 정리 계획을 부르면(LLM 끔 → 503) 실행 #1 이 「LLM 꺼짐」 으로 남고, 그 에이전트의 ⑤ 최근 실행과 전체 보기 줄에도 보인다.
- 좁은 폭(800 · 480px): 목차가 본문 위 가로 줄 · 한 에이전트가 한 단 · 가로 넘침 없음.
- 문서를 연 상단 바(앱 화면): 1600 · 1280 · 1100 · 800px 에서 줄이 넘치지 않고 패널 여닫기(「도구 닫기」 — 아이콘)가 창 안 · 링크는 어느 폭에서나 아이콘만 30×26 · 541~780px 에서는 링크를 감춤(그 폭은 이 링크가 없어도 710px 아래에서 줄이 넘친다 — 더 키우지 않는다) · 480px(두 줄)에서는 다시 보임.
- 콘솔 오류 없음(일부러 낸 400·503 은 뺌).

    python -X utf8 tools/smoke_agents_ui.py <출력 폴더> [--port 18441]
"""
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
ap.add_argument("--port", type=int, default=18441)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1"}
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_TPL_AGENT_MODEL"):
    env.pop(k, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:700] if detail != "" and not ok else ""), flush=True)
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


def run_stage(doc, stage):
    r = requests.post(f"{base}/api/docs/{doc}/headings", json={"stage": stage, "llm": False}, timeout=30)
    assert r.status_code == 202, r.text
    end = time.time() + 300
    while time.time() < end:
        v = requests.get(f"{base}/api/docs/{doc}/headings", timeout=30).json()
        if not v.get("job") or v["job"].get("status") != "running":
            return v
        time.sleep(0.4)
    raise SystemExit("단계가 안 끝남")


def agent(aid):
    return requests.get(f"{base}/api/agents/{aid}", timeout=30).json()


ROW = lambda aid: f'#agMain .ags-row[data-agent="{aid}"]'  # noqa: E731 — 전체 보기의 줄
NAV = lambda aid: f'#agNav a[data-agent="{aid}"]'  # noqa: E731 — 목차의 줄
SAVED = "() => (document.querySelector('#agMain .ags-saved') || {}).textContent || ''"
HEAD = "() => [(document.querySelector('.ags-h2 .ags-no') || {}).textContent, (document.querySelector('.ags-dname') || {}).textContent]"


def watch(pg):
    pg.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
    pg.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
    pg.on("dialog", lambda d: d.accept())


def main():
    wait_server()
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1700, "height": 1000}, device_scale_factor=1)
        page = ctx.new_page()
        watch(page)
        page.goto(base)
        page.wait_for_selector("#agentsLink")
        t = page.evaluate("""() => { const a = document.getElementById('agentsLink'), r = a.getBoundingClientRect(), bar = document.querySelector('.topbar').getBoundingClientRect();
          return { direct: a.parentElement.classList.contains('topbar'), right: bar.right - r.right, top: r.top, w: Math.round(r.width), h: Math.round(r.height), text: a.textContent.trim() !== '', tip: a.title, icon: !!a.querySelector('svg'),
            label: a.getAttribute('aria-label'), href: a.getAttribute('href'), target: a.target, rel: a.rel, deco: getComputedStyle(a).textDecorationLine,
            last: [...a.parentElement.children].filter((e) => e.offsetWidth > 0).pop().id, old: !!document.getElementById('agentsBtn'), js: typeof agentsOpen }; }""")
        check("시작 화면 상단 바 오른쪽 끝에 링크 「에이전트 설정」(/agents · 새 탭 · 직계 .btn · 글 없이 아이콘만 32×32 · 이름은 도움말 · 밑줄 없음) — 전의 단추·agents.js 는 없음",
              t["direct"] and t["right"] < 60 and t["top"] < 40 and t["w"] == 32 and t["h"] == 32 and not t["text"] and t["tip"].startswith("에이전트 설정 — ") and t["icon"] and t["label"] == "에이전트 설정" and t["href"] == "/agents" and t["target"] == "_blank"
              and "noopener" in t["rel"] and t["deco"] == "none" and t["last"] == "agentsLink" and not t["old"] and t["js"] == "undefined", t)

        # ---- 페이지 — 전체 보기
        with ctx.expect_page() as fresh:
            page.click("#agentsLink")
        ag = fresh.value
        watch(ag)
        ag.wait_for_selector("#agMain .ags-row", timeout=20000)
        st = ag.evaluate("""() => { const row = document.querySelector('#agMain .ags-row'), box = (e) => e.getBoundingClientRect();
          return { path: location.pathname, title: document.title, h1: document.querySelector('.ags-title').textContent, note: document.getElementById('agNote').textContent, llm: document.getElementById('agLlm').textContent,
            wf: document.getElementById('agWorkflow').getAttribute('href'), groups: [...document.querySelectorAll('#agMain .ags-g')].map((h) => h.textContent), nos: [...document.querySelectorAll('#agMain .ags-row > .ags-no')].map((n) => n.textContent),
            first: row.innerText.replace(/\\s+/g, ' ').slice(0, 160), pin: document.querySelector('.ags-row[data-agent=tpl_agent] .ags-model').className,
            full: [...document.querySelectorAll('#agMain .ags-row')].every((r) => r.querySelector('.ags-where').textContent && r.querySelector('.ags-role').textContent && r.querySelector('.ags-model').textContent),
            cols: Math.abs(box(row.querySelector('.ags-where')).top - box(row.querySelector('.ags-rmain')).top) < 6 && box(row.querySelector('.ags-role')).left > box(row.querySelector('.ags-where')).right - 1,
            nav: [...document.querySelectorAll('#agNav a')].map((a) => a.getAttribute('href')), navH: [...document.querySelectorAll('#agNav h2')].map((h) => h.textContent),
            cur: (document.querySelector('#agNav a[aria-current=true]') || {}).textContent, navW: Math.round(box(document.getElementById('agNav')).width), over: document.documentElement.scrollWidth > innerWidth }; }""")
        check("새 탭 /agents — 상단 줄(제목 · 「에이전트 21개」 · 「LLM 꺼짐」 · 「워크플로우」 → /workflow) · 가로 넘침 없음",
              st["path"] == "/agents" and st["title"].startswith("에이전트 설정") and st["h1"] == "에이전트 설정" and st["note"] == "에이전트 21개" and st["llm"] == "LLM 꺼짐" and st["wf"] == "/workflow" and not st["over"], st)
        check("전체 보기 — 묶음 일곱 · 에이전트 21줄(작업 번호 01~21 — 묶음 차례라 「프로젝트 구성」 의 21(편집 구역 검토 — 2026-11-17)이 08 뒤, 「문서 편집」 의 19 가 「서식」 의 17·18 앞, 「검증」 의 20 이 끝 · 쓰는 곳 · 역할 · 모델) · 넓은 폭에서 네 칸(번호 | 이름 | 쓰는 곳 | 역할)",
              len(st["groups"]) == 7 and st["groups"][0] == "헤딩 추출 6" and st["nos"] == [f"{i:02d}" for i in range(1, 9)] + ["21"] + [f"{i:02d}" for i in range(9, 17)] + ["19", "17", "18", "20"] and st["full"] and "레터 규칙식 제안" in st["first"] and "pin" in st["pin"] and st["cols"], st)
        check("목차 — 전체 보기(지금) · 실행 기록 · 묶음 일곱 · 에이전트 21(주소 #id)",
              st["nav"][:2] == ["#overview", "#runs"] and len(st["nav"]) == 23 and st["nav"][2] == "#heading_rules" and len(st["navH"]) == 7 and st["cur"] == "전체 보기" and st["navW"] == 248, st)
        ag.screenshot(path=str(OUT / "01_overview.png"))

        # ---- 한 에이전트 — 설정 저장
        ag.click(ROW("merge_links"))
        ag.wait_for_selector("#agMain .agd .ags-noin", timeout=20000)
        d = ag.evaluate("""() => { const box = (s) => document.querySelector(s).getBoundingClientRect();
          return { hash: location.hash, title: document.title, no: document.querySelector('.ags-noin').value, role: document.querySelector('.ags-role-in').value.slice(0, 30),
            model: [...document.querySelectorAll('.ags-model-in option')].map((o) => o.textContent), effort: document.querySelector('.ags-effort-in option').textContent, saved: document.querySelector('.ags-saved').textContent,
            save: document.querySelector('.ags-save').disabled, secs: [...document.querySelectorAll('.ags-h')].map((h) => h.textContent.trim().slice(0, 12)), helps: document.querySelectorAll('.ags-sec > .ags-help').length,
            cur: (document.querySelector('#agNav a[aria-current=true]') || {}).dataset.agent, two: box('.ags-prompt').left > box('.ags-set').right && Math.abs(box('.ags-prompt').top - box('.ags-set').top) < 4,
            parts: [...document.querySelectorAll('.agp')].map((x) => [x.className.replace('agp ', ''), x.querySelector('summary b').textContent, x.querySelector('.agp-src').textContent, (x.querySelector('summary .ags-tag') || {}).textContent || '']) }; }""")
        head = ag.evaluate(HEAD)
        check("한 에이전트(주소 #merge_links · 머리 [09] 자리 연결 검토 · 목차의 지금 줄) — 두 단(왼쪽 설정 · 오른쪽 프롬프트) · ① 작업 번호 「09」 ② 역할 ③ 모델(「따로 정하지 않음 — 지금 Opus 5.5(코드가 정함)」 + 넷)·생각 깊이 · 저장 꺼짐 · ④⑤ · 절마다 설명 글",
              d["hash"] == "#merge_links" and head == ["09", "자리 연결 검토"] and d["title"].startswith("작업 09 · 자리 연결 검토") and d["cur"] == "merge_links" and d["two"] and d["no"] == "09" and d["role"].startswith("사업계획서")
              and d["model"][0] == "따로 정하지 않음 — 지금 Opus 5.5(코드가 정함)" and d["model"][1:] == ["Fable 5.2", "Opus 5.5", "Sonnet 5.5", "Haiku 5.5"] and d["effort"] == "따로 정하지 않음 — 지금 medium"
              and d["saved"] == "기본값 그대로" and d["save"] and [s[0] for s in d["secs"]] == ["①", "②", "③", "④", "⑤"] and d["helps"] == 5, [head, d])
        check("④ 프롬프트의 차례 = 계약(읽기만) → 판단 지침(저장소 파일) → 할 일 프롬프트 → 양식 정보 → 자료",
              [x[0] for x in d["parts"]] == ["k-contract", "k-merge", "k-job", "k-form", "k-data"] and d["parts"][0][3] == "읽기만" and d["parts"][1][2] == "app/merge_guides_default/links.md"
              and d["parts"][2][2] == "jobs/plan_to_report.md" and "자리 연결" in d["parts"][1][1], d["parts"])
        ag.locator("#agMain .agp.k-contract summary").click()
        check("계약 글은 읽기 전용으로 펼쳐 본다", ag.evaluate("() => { const t = document.querySelector('.agp.k-contract .agp-text'); return t.readOnly && t.value.length > 500 && !document.querySelector('.agp.k-contract .agp-acts'); }"))
        ag.fill("#agMain .ags-noin", "M-1")
        ag.fill("#agMain .ags-role-in", "이관에서 자리를 잇는 검토자")
        ag.select_option("#agMain .ags-model-in", "claude-sonnet-5-5")
        ag.select_option("#agMain .ags-effort-in", "high")
        check("고치면 「고침 — 저장 안 됨」 · 저장 켜짐 · 목차 줄에 「저장 안 됨」", ag.evaluate(SAVED) == "고침 — 저장 안 됨" and not ag.evaluate("document.querySelector('.ags-save').disabled")
              and ag.locator(NAV("merge_links") + " .ags-nmark").inner_text() == "저장 안 됨")
        ag.click('#agNav a[href="#overview"]')
        ag.wait_for_selector(ROW("merge_links") + " .ags-tag.dirty", timeout=20000)
        ag.click(ROW("merge_links"))
        ag.wait_for_selector("#agMain .agd .ags-noin", timeout=20000)
        check("저장 안 한 값은 전체 보기에 갔다 와도 남는다(줄에 「저장 안 됨」 → 다시 열면 그 값) — 저장은 아직 안 됨",
              ag.input_value("#agMain .ags-noin") == "M-1" and ag.input_value("#agMain .ags-model-in") == "claude-sonnet-5-5" and ag.evaluate(SAVED) == "고침 — 저장 안 됨" and agent("merge_links")["no"] == "09")
        ag.click("#agMain .ags-save")
        ag.wait_for_function("() => /^저장됨 — 고친 것/.test((document.querySelector('#agMain .ags-saved') || {}).textContent || '')", timeout=20000)
        a = agent("merge_links")
        check("「저장」 → 작업 번호 M-1 · 역할 글 · Sonnet 5.5 · high(여기서 정함) — 머리와 목차도 「M-1」 · 목차 「고침」", a["no"] == "M-1" and a["role"] == "이관에서 자리를 잇는 검토자"
              and a["model"] == {"id": "claude-sonnet-5-5", "source": "user"} and a["effort"] == {"id": "high", "source": "user"} and (tmp / "agents.json").is_file() and ag.evaluate(HEAD) == ["M-1", "자리 연결 검토"]
              and ag.locator(NAV("merge_links") + " .ags-nno").inner_text() == "M-1" and ag.locator(NAV("merge_links") + " .ags-nmark").inner_text() == "고침", a)
        ag.screenshot(path=str(OUT / "02_detail_saved.png"))
        ag.click("#agMain .ags-back")
        ag.wait_for_function("() => (document.querySelector('.ags-row[data-agent=merge_links] > .ags-no') || {}).textContent === 'M-1'", timeout=20000)
        r = ag.evaluate("""() => { const x = document.querySelector('.ags-row[data-agent=merge_links]'); return [x.querySelector('.ags-model').textContent, x.querySelector('.ags-model').className, x.querySelector('.ags-eff').textContent, (x.querySelector('.ags-tag.chg') || {}).textContent]; }""")
        check("「‹ 전체 보기」 → 줄에 「M-1」 · 「Sonnet 5.5」(여기서 정함 — 파랑) · high · 「고침」", r == ["Sonnet 5.5", "ags-model user", "high", "고침"] and ag.evaluate("location.hash") == "#overview", r)
        # 겹치는 작업 번호
        ag.click(ROW("merge_gaps"))
        ag.wait_for_selector("#agMain .agd .ags-noin")
        ag.fill("#agMain .ags-noin", "M-1")
        ag.click("#agMain .ags-save")
        ag.wait_for_function("() => /쓰고 있습니다/.test(document.getElementById('agToast').textContent) && !document.getElementById('agToast').hidden", timeout=20000)
        check("다른 에이전트의 작업 번호는 거절(그대로 「저장 안 됨」)", agent("merge_gaps")["no"] == "11" and ag.evaluate(SAVED) == "고침 — 저장 안 됨")
        ag.locator("#agMain .ags-state button", has_text="고친 것 버리기").click()
        check("「고친 것 버리기」 → 저장된 값으로(번호 11 · 「기본값 그대로」 · 목차 표시 없음)", ag.input_value("#agMain .ags-noin") == "11" and ag.evaluate(SAVED) == "기본값 그대로" and ag.locator(NAV("merge_gaps") + " .ags-nmark").count() == 0)
        ag.click(NAV("merge_links"))
        ag.wait_for_function("() => (document.querySelector('.ags-dname') || {}).textContent === '자리 연결 검토'", timeout=20000)
        ag.locator("#agMain .ags-state button", has_text="모두 기본으로").click()
        check("「모두 기본으로」 는 줄 안에서 두 번", ag.locator("#agMain .ags-state button", has_text="기본으로 확인").count() == 1 and agent("merge_links")["custom"])
        ag.locator("#agMain .ags-state button", has_text="기본으로 확인").click()
        ag.wait_for_function("() => (document.querySelector('#agMain .ags-saved') || {}).textContent === '기본값 그대로'", timeout=20000)
        a = agent("merge_links")
        check("한 번 더 → 번호 09 · 기본 역할 글 · 코드가 정한 모델", a["custom"] == [] and a["no"] == "09" and a["model"]["source"] == "code" and ag.input_value("#agMain .ags-noin") == "09" and ag.evaluate(HEAD)[0] == "09", a)

        # ---- 고칠 수 있는 프롬프트: 헤딩 지침
        ag.click(NAV("heading_rules"))
        ag.wait_for_selector("#agMain .agp.k-heading")
        ag.locator("#agMain .agp.k-heading summary").click()
        ag.locator("#agMain .agp.k-heading button", has_text="고치기").click()
        ag.fill("#agMain .agp.k-heading .agp-text", "레터 규칙은 짧게 제안한다.\n")
        ag.locator("#agMain .agp.k-heading button", has_text="저장").click()
        ag.wait_for_function("() => /내 사본 · 판 1/.test((document.querySelector('.agp.k-heading .agp-ver') || {}).textContent || '')", timeout=20000)
        g = requests.get(f"{base}/api/headings/guides/rules", timeout=30).json()
        check("헤딩 지침을 그 자리에서 고쳐 저장 → 헤딩 지침 저장소의 내 사본(판 1) · 「고침」", g["custom"] and g["text"] == "레터 규칙은 짧게 제안한다.\n" and ag.locator("#agMain .agp.k-heading summary .ags-tag").inner_text() == "고침", g)
        ag.screenshot(path=str(OUT / "03_prompt_edit.png"))
        ag.locator("#agMain .agp.k-heading button", has_text="기본으로 되돌리기").click()
        ag.locator("#agMain .agp.k-heading button", has_text="되돌리기 확인").click()
        ag.wait_for_function("() => (document.querySelector('.agp.k-heading .agp-ver') || {}).textContent === '기본 글'", timeout=20000)
        check("「기본으로 되돌리기」(두 번) → 기본 글", not requests.get(f"{base}/api/headings/guides/rules", timeout=30).json()["custom"])
        # 템플릿 정리 스킬
        ag.click(NAV("tpl_agent"))
        ag.wait_for_selector("#agMain .agp.k-skill")
        sk = ag.evaluate("[...document.querySelectorAll('.agp.k-skill summary b')].map((x) => x.textContent)")
        first = ag.locator("#agMain .agp.k-skill").first
        first.locator("summary").click()
        first.locator("button", has_text="고치기").click()
        first.locator(".agp-text").fill("레터 앞 빈칸은 가장 많은 것으로.\n")
        first.locator("button", has_text="저장").click()
        ag.wait_for_function("() => /내 사본 · 판 1/.test((document.querySelector('.agp.k-skill .agp-ver') || {}).textContent || '')", timeout=20000)
        s = requests.get(f"{base}/api/outline/agent/skills/tidy", timeout=30).json()
        check("템플릿 정리 스킬도 여기서 고쳐 저장(스킬 저장소) · 모델 「Opus 5.5 — 이 에이전트에 고정」",
              sk == ["스킬 — 템플릿 서식 정리", "스킬 — 가장 많은 서식으로 모두 맞추기"] and s["custom"] and s["text"] == "레터 앞 빈칸은 가장 많은 것으로.\n" and s["name"] == "템플릿 서식 정리"
              and ag.locator("#agMain .ags-model-in option").first.inner_text() == "따로 정하지 않음 — 지금 Opus 5.5(이 에이전트에 고정)", [sk, s])
        requests.delete(f"{base}/api/outline/agent/skills/tidy", timeout=30)

        # ---- 주소로 바로 열기
        ag.goto(base + "/agents#doc_agent")
        ag.reload()
        ag.wait_for_selector("#agMain .agd .ags-noin", timeout=20000)
        direct = ag.evaluate(HEAD)
        ag.goto(base + "/agents#nope")
        ag.wait_for_selector("#agMain #overview .ags-row", timeout=20000)
        check("주소 /agents#doc_agent 로 바로 그 에이전트 · 모르는 id 는 전체 보기", direct == ["16", "문서 에이전트"] and ag.locator("#agNav a[aria-current=true]").inner_text() == "전체 보기", direct)

        # ---- 실행 기록
        r = requests.post(base + "/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}, timeout=120)
        assert r.status_code == 200, r.text
        doc = r.json()["docId"]
        run_stage(doc, 1)
        run_stage(doc, 2)
        assert requests.get(f"{base}/api/docs/{doc}/outline", timeout=120).status_code == 200
        pr = requests.post(f"{base}/api/docs/{doc}/outline/agent/3/plan", json={"skill": "tidy"}, timeout=120)
        ag.goto(base + "/agents#overview")
        ag.wait_for_selector(ROW("tpl_agent") + " .ags-last", timeout=20000)
        last = ag.locator(ROW("tpl_agent") + " .ags-last").inner_text()
        check("LLM 이 꺼진 채 부른 계획(503)도 실행 #1 로 남아 전체 보기 줄에 「마지막 실행 #1 … 실패」", pr.status_code == 503 and last.startswith("마지막 실행 #1") and "실패" in last and "켠 뒤 1번" in last, [pr.status_code, last])
        ag.click('#agNav a[href="#runs"]')
        ag.wait_for_selector("#agMain #runs table.ags-runs tbody tr", timeout=20000)
        row = ag.evaluate("[...document.querySelector('#runs table.ags-runs tbody tr').children].map((td) => td.textContent)")
        check("「실행 기록」(#runs) — 실행 번호 · 시각 · 에이전트(작업 번호 + 이름) · 모델 · 시간 · 결과 · 「다시 읽기」",
              row[0] == "#1" and row[2] == "18 템플릿 서식 정리" and row[3].startswith("Opus 5.5") and row[5] == "LLM 꺼짐" and ag.locator("#runs .ags-reload").count() == 1
              and ag.locator("#agNav a[aria-current=true]").inner_text() == "실행 기록", row)
        ag.screenshot(path=str(OUT / "04_runs.png"))
        ag.locator("#runs .ags-runlink").first.click()
        ag.wait_for_selector("#agMain .agd table.ags-runs tbody tr", timeout=20000)
        check("에이전트 이름을 누르면 그 에이전트 — ⑤ 최근 실행에 그 줄", ag.evaluate(HEAD) == ["18", "템플릿 서식 정리"] and ag.locator("#agMain .agd table.ags-runs tbody tr td").first.inner_text() == "#1"
              and ag.evaluate("location.hash") == "#tpl_agent")

        # ---- 좁은 폭(페이지)
        ag.set_viewport_size({"width": 800, "height": 900})
        ag.wait_for_timeout(300)
        n = ag.evaluate("""() => { const box = (s) => document.querySelector(s).getBoundingClientRect(), nav = box('#agNav');
          return { navRow: nav.height < 60 && nav.width > 700, stacked: box('.ags-prompt').top >= box('.ags-set').bottom - 1, over: document.documentElement.scrollWidth > innerWidth,
            main: document.getElementById('agMain').scrollWidth <= document.getElementById('agMain').clientWidth + 1 }; }""")
        check("800px — 목차가 본문 위 가로 줄 · 한 에이전트가 한 단 · 가로 넘침 없음", n["navRow"] and n["stacked"] and not n["over"] and n["main"], n)
        ag.set_viewport_size({"width": 480, "height": 900})
        ag.click('#agNav a[href="#overview"]')
        ag.wait_for_selector("#agMain #overview .ags-row", timeout=20000)
        ag.wait_for_timeout(300)
        n = ag.evaluate("""() => { const row = document.querySelector('#agMain .ags-row'), box = (e) => e.getBoundingClientRect();
          return { over: document.documentElement.scrollWidth > innerWidth, main: document.getElementById('agMain').scrollWidth <= document.getElementById('agMain').clientWidth + 1,
            stacked: box(row.querySelector('.ags-where')).top >= box(row.querySelector('.ags-rmain')).bottom - 1, top: Math.round(box(document.querySelector('.ags-top')).height) }; }""")
        check("480px — 전체 보기의 줄이 한 칸으로 쌓이고 가로 넘침 없음", not n["over"] and n["main"] and n["stacked"], n)
        ag.screenshot(path=str(OUT / "05_narrow.png"))
        ag.close()

        # ---- 문서를 연 상단 바(앱 화면)의 링크
        page.evaluate(f"() => {{ location.hash = '#w={doc}'; }}")
        page.reload()
        page.wait_for_selector("#doc .para[data-id=p970]", timeout=120000)
        bad = []
        for w in (1600, 1280, 1100, 800, 720, 640, 560):
            page.set_viewport_size({"width": w, "height": 900})
            page.wait_for_timeout(350)
            m = page.evaluate("""() => { const bar = document.querySelector('.topbar'), a = document.getElementById('agentsLink'), pb = document.getElementById('panelBtn'), r = a.getBoundingClientRect();
              return { sw: bar.scrollWidth, cw: bar.clientWidth, h: Math.round(bar.getBoundingClientRect().height), ah: Math.round(r.height), aw: Math.round(r.width), shown: r.width > 0, text: a.textContent.trim() !== '',
                inside: r.right <= innerWidth + 0.5 && r.left >= 0, panel: pb.hidden || pb.offsetWidth === 0 || pb.getBoundingClientRect().right <= innerWidth + 0.5 }; }""")
            ok = (m["sw"] <= m["cw"] + 1 and m["h"] == 35 and m["ah"] == 26 and m["aw"] == 30 and m["shown"] and m["inside"] and m["panel"] and not m["text"]) if w >= 800 else (not m["shown"] and m["h"] == 35)
            if not ok:
                bad.append((w, m))
        check("문서를 연 상단 바 — 1600·1280·1100·800px 에서 넘침 없음 · 높이 35px · 링크 30×26 글 없이 아이콘만(어느 폭에서나) · 패널 여닫기 창 안 · 541~780px(720·640·560)에서는 링크를 감춤(줄 넘침을 키우지 않음)", not bad, bad)
        page.set_viewport_size({"width": 480, "height": 900})
        page.wait_for_timeout(350)
        n = page.evaluate("() => { const r = document.getElementById('agentsLink').getBoundingClientRect(); return r.width > 0 && r.right <= innerWidth + 0.5 && r.left >= 0; }")
        check("480px(두 줄로 꺾이는 폭)에서도 링크가 창 안", n)
        page.screenshot(path=str(OUT / "06_topbar_narrow.png"))
        b.close()
    real = [e for e in errors if "400" not in e and "503" not in e]
    check("콘솔 오류 없음", not real, real[:5])


try:
    main()
finally:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'OK' if not fails else 'FAIL'} — 실패 {len(fails)}" + (f": {fails}" if fails else ""))
sys.exit(1 if fails else 0)

"""조립 화면 — 단계(묶음 › 줄 — 정의 v2: spec_워크플로우 ② §18-5 · §18-6 · design.md §22 — app/static/workflow.js linesDraw · app/custom_tasks.py check) 화면 확인 —
임시 서버(임시 조립 저장소, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 흉내 없이 진짜 끝점으로.

    python -X utf8 tools/smoke_flow_compose_ui.py <그림·임시 폴더> [--port 18730]

보는 것:
- ① 「새 워크플로우 조립」 → 단계 칸 = 표준 차례(이관 전체 — 묶음 넷 › 행: 행 × 두 칸 — 두 문서의 「헤딩 · 표 분석」 은 한 행의 두 칸(같은 차례) · 두 문서가 함께 있어야 하는 줄은 쌍 줄)로 채워짐 · 서버 검사 「표준 차례」 ·
  표(문서 역할 × 단계)는 「표준 차례로 채우기」 펼침 안.
- ①-2 문서마다 따로 넣기 — 구성 반영은 목적 문서 카드 하나(원본 칸은 빈칸) · 「원본 문서 줄 넣기」 로 원본 문서 줄을 따로(목적 문서의 구성 반영 · 다시 문서 검토 뒤에 놓아도 거절 없음 — 문서끼리의 차례는 자유) ·
  카드의 ▲ = 제 칸에서 한 걸음(위 행의 빈칸으로 = 같은 차례 → 한 번 더 = 제 행으로 — 옆 칸의 줄은 안 움직인다) · 이미 놓은 줄도 「한 번 더」 · 「빼기」 → 표준 차례 · 「목적 문서와 같이」 → 목적 문서의 줄마다 그 옆 칸(같은 행)에 원본 문서 줄.
- ①-3 행 × 두 칸(2026-11-20 사용자 「같은 도구라도 다른 시간 순서대로 … 마우스로 드래그 … 다음단계는 공백/즉 다른문서만 작업하고 기다릴 수도」 · 「이걸 같이 실행할 수 있는 기능이 없음 … 도구는 1번 이상 선택」) —
  ▼ 로 같은 차례에서 나오기 · 다른 줄 옆 빈칸으로(저장 줄의 beside) · 끌어 놓기(행 사이 = 제 행 · 빈칸 = 같은 차례 · 다른 문서 칸 = 그 문서의 줄 · 쌍 줄은 행째 · 다른 묶음으로) · 같은 줄을 한 번 더(거절이 아니라 경고).
- ② 표에서 고르면(목적 문서의 「구성 맞추기」 끔) 줄 목록이 그 표준 차례로 다시 채워짐.
- ③ 줄을 고쳐 표준이 아닌 정의 — 원본만 검토 → 넣기(묶음 빼기 · 목적 문서 줄 빼기 · ＋ 묶음 · 쌍 줄 넣기) → 경고(막지 않음) · 「줄 목록으로 조립한 워크플로우」 → 저장 = flow(서버가 v2 로) · 절의 묶음 g1 · g2.
- ③-2 쌍 줄(2026-11-20 사용자 「어떤 도구는 대상이 있어야 사용할 수 있는게 있어 잘 연결될 수 있도록」 · 「열을 분할해줘, 대상이 있어야 하는 경우에는 2개를 쌍으로 넣을 수 있게 … 순차적임을 표현하기 위해 한쪽은 공백을 두고 다른 한쪽은 도구를 주고」) —
  두 문서가 함께 있어야 하는 줄(자리 연결 · LLM 검토 · 넣기 계획 · 빈 자리 검토 · 표 대응 · 내용 반영 …)은 두 문서 칸에 같은 이름으로 선 쌍 줄(걸친 칸 없음) · 넣기는 문서 칸 고르기 둘뿐(쌍 줄은 두 고르기 모두에 — 「 (쌍)」) ·
  앞 줄이 있어야 하는 줄은 그 줄이 없으면 꺼짐(「먼저 「…」 을 넣으세요」) · 넣는 자리 = 그 앞 줄 뒤 제자리(표 대응 → 넣기 계획과 내용 반영 사이 · 빈 자리 검토 → 넣기 계획 바로 뒤 · LLM 검토 → 자리 연결 바로 뒤) · 넣기 계획을 빼면 서버의 거절.
- ④ 차례가 거꾸로(▲) → 서버의 거절 글 · 저장 단추가 꺼짐 · 「사람이 하는 일」 은 「아직」 으로 꺼짐.
- ⑤ 「고치기」 — v2 정의가 줄 목록으로 열림(표는 접힘) · 묶음 이름만 고쳐 저장 → 지문 그대로 · 저장 몸 = flow.
- ⑥ 400px 에서 가로 넘침 없음 · 콘솔 오류 없음.
- ⑧ 도구 설명 열(② §18-15 — 2026-11-20 사용자 「우측에 각 도구가 어떤 역할을 하는지 설명해줘. 자리연결누르면 우측 열에 설명을 넣어주 … 모든도구」): 폼 | 「도구 설명」 열 · 안 골랐으면 그 틀의 도구 목록(16개 · 줄마다 한 문장) ·
  「자리 연결」 카드를 누르면 그 도구의 설명(칸의 차례 · 쌍 줄의 두 칸에 표시) · 빈칸 · ▼ 는 고른 것을 안 바꿈 · 줄을 옮겨도 그대로 · 자판 · 목록에서 고르기 · 이름 칩 · 설명을 열어도 조립 검사 · 저장은 그대로 ·
  취합형의 글 · 좁은 창(폼 위 · 목록 접힘) · 「단계 만들기」 폼."""
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
ap.add_argument("--port", type=int, default=18730)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
REPORT = ROOT / "samples" / "국가RnD_서식" / "KEIT_표준서식_260320" / "1. 산업기술혁신사업 연차보고서 서식_260319.hwpx"
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1",
       "NFM_TASKS": str(tmp / "tasks.json"), "NFM_FORM_FILES": str(tmp / "form_files")}   # 이 검사가 조립한 것을 만들고 고친다 — 늘 임시
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_FLOW_EXEC"):
    env.pop(k, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails, dialogs, bodies, checks = [], [], [], [], []


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


LINES = """() => { const box = document.querySelector('#wfCompose .wf-lines'); if (!box) return null;
  const save = document.querySelector('#wfCompose form button[type=submit]');
  return { groups: [...box.querySelectorAll('.wf-lines-group')].map((g) => ({ id: g.dataset.group, name: g.querySelector('.wf-lines-ghead input').value,
      lines: [...g.querySelectorAll('.wf-line')].map((l) => [l.dataset.unit, ({ source: '원본', target: '목적', pair: '쌍', both: '같이' })[l.dataset.role] || '']),   // 보이는 행 차례(행 × 두 칸) — 한 칸뿐인 행 = 그 문서 · 두 칸에 카드가 선 행 = 같이(줄이 다르면 「목적 줄+원본 줄」) · 상대 문서가 있어야 하는 줄 = 쌍
      cols: [...g.querySelectorAll('.wf-line-colname')].map((x) => x.textContent) })),
    std: (box.querySelector('.wf-lines-std') || {}).textContent || '', errs: [...box.querySelectorAll('.wf-lines-err li')].map((x) => x.textContent), warns: [...box.querySelectorAll('.wf-lines-warn li')].map((x) => x.textContent),
    checking: /검사하는 중/.test(box.textContent), save: save ? { off: save.disabled, text: save.textContent } : null,
    tableOpen: !!(document.querySelector('#wfCompose details.wf-std-pick') || {}).open,
    handOpt: [...box.querySelectorAll('.wf-lines-add[data-add=target] option')].filter((o) => o.value === 'hand').map((o) => [o.textContent, o.disabled])[0] || null }; }"""   # 사람이 하는 일 = 문서 칸의 고르기에(목적 문서 줄 넣기)

# 2단계 묶음(구성 맞추기)의 「프로젝트 구성 반영」 줄 · 넣기 셋 · 「…와 같이」 단추(①-2 가 읽는다)
FIT = """() => { const g = [...document.querySelectorAll('#wfCompose .wf-lines-group')][1]; if (!g) return null;
  const opt = g.querySelector('.wf-lines-add[data-add=source] option[value=division]');
  return { div: [...g.querySelectorAll('.wf-line-cell[data-unit=division]')].map((c) => { const l = c.closest('.wf-line');   // 「프로젝트 구성 반영」 카드마다 — 그 칸의 문서 · 같은 행의 빈칸 · 그 카드의 단추
      return { role: c.dataset.role, on: c.dataset.on || '', blank: [...l.querySelectorAll('.wf-line-cell.wf-line-blank')].map((x) => x.dataset.role), boxes: l.querySelectorAll('input[type=checkbox]').length,
        join: !!l.querySelector('.wf-line-join'), btns: [...c.querySelectorAll('button')].map((b) => b.textContent), drag: !!c.querySelector('.wf-card-head[draggable=true]') }; }),
    adds: [...g.querySelectorAll('select.wf-lines-add[data-add]')].map((x) => x.dataset.add).sort(),
    same: [...g.querySelectorAll('button.wf-lines-same')].map((b) => [b.dataset.same, b.textContent, b.disabled]),
    srcDiv: opt ? [opt.textContent, opt.disabled] : null }; }"""

# 묶음 하나(기본 = 둘째 — ③ 의 「넣기」)의 넣기 고르기(문서 칸마다) · 줄마다의 칸(③-2 · ①-2 가 읽는다) — adds[고르기의 data-add] · target · source{줄 key: [옵션 글, 꺼짐]} ·
# wide(걸친 칸 .wf-line-common 의 수) · common(줄 글에 「공통」 이 있나) · lines[{unit, role, cells[[칸의 문서, data-on, 쌍 칸인가, 줄 이름, 작은 글(.wf-line-hint)]]}]
PAIRS = """(gi) => { const g = [...document.querySelectorAll('#wfCompose .wf-lines-group')][gi == null ? 1 : gi]; if (!g) return null;
  const opts = (r) => { const sel = g.querySelector('select.wf-lines-add[data-add=' + r + ']');
    return Object.fromEntries([...(sel ? sel.querySelectorAll('option') : [])].filter((o) => o.value).map((o) => [o.value, [o.textContent.trim(), o.disabled]])); };
  return { adds: [...g.querySelectorAll('select.wf-lines-add[data-add]')].map((x) => x.dataset.add).sort(), target: opts('target'), source: opts('source'),
    wide: g.querySelectorAll('.wf-line-common').length, common: [...g.querySelectorAll('.wf-line')].some((l) => /공통/.test(l.textContent)),
    lines: [...g.querySelectorAll('.wf-line')].map((l) => ({ unit: l.dataset.unit, role: l.dataset.role || '',
      cells: [...l.querySelectorAll('.wf-line-cell')].map((c) => { const b = c.querySelector('.wf-line-name b') || c.querySelector('b'), h = c.querySelector('.wf-line-hint');
        return [c.dataset.role || '', c.dataset.on || '', c.classList.contains('wf-line-pair'), b ? b.textContent.trim() : '', h ? h.textContent.trim() : '']; }) })) }; }"""


def settle(page):
    page.wait_for_function("() => { const b = document.querySelector('#wfCompose .wf-lines'); return b && !/검사하는 중/.test(b.textContent) && !!b.querySelector('.wf-lines-check'); }", timeout=30000)
    page.wait_for_timeout(350)   # 줄을 고친 뒤 검사를 거는 틈(250ms)
    page.wait_for_function("() => { const b = document.querySelector('#wfCompose .wf-lines'); return b && !/검사하는 중/.test(b.textContent); }", timeout=30000)
    return page.evaluate(LINES)


def group(page, i):
    return page.locator("#wfCompose .wf-lines-group").nth(i)


def main():
    wait_server()
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1500, "height": 1000}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        page.on("request", lambda r: bodies.append((r.method, r.url, r.post_data)) if "/api/tasks" in r.url and r.method in ("POST", "PUT") and not r.url.endswith("/check") else None)
        page.on("request", lambda r: checks.append(r.post_data) if r.url.endswith("/api/tasks/check") and r.method == "POST" else None)   # 조립 검사에 보낸 몸(줄 목록 — 같은 차례 표시 beside 를 본다)
        page.goto(f"{base}/workflow#overview")
        page.wait_for_selector("#wfCompose [data-wf-compose=open]")

        # ---- ① 새 워크플로우 — 표준 차례로 채워짐
        page.click("#wfCompose [data-wf-compose=open]")
        s = settle(page)
        STD1 = [["heads", "같이"], ["headsLlm", "원본"]]   # 표준 차례의 1단계 — 두 문서의 「헤딩 · 표 분석」 은 한 행의 두 칸(같은 차례 — 저장 줄 하나: on 둘) · 「LLM 검증·보완」 은 원본 문서 칸(목적 칸은 빈칸)
        check("① 새 워크플로우 — 단계 칸 = 표준 차례(이관 전체: 묶음 넷 · 행 × 두 칸 — 두 문서의 헤딩 · 표 분석은 한 행의 두 칸: 같은 차례) · 서버 검사 「표준 차례」 · 표는 「표준 차례로 채우기」 펼침 안(펴짐) · 저장 켜짐",
              [g["name"] for g in s["groups"]] == ["문서 검토", "구성 맞추기", "내용 넣기", "문서 정리"] and s["groups"][0]["lines"] == STD1
              and s["std"].startswith("표준 차례") and not s["errs"] and s["tableOpen"] and not s["save"]["off"]
              and s["groups"][0]["cols"] == ["목적 문서", "원본 문서"] and s["groups"][2]["lines"][0][1] == "쌍", s)   # 문서 열(왼쪽 목적 · 오른쪽 원본) · 3단계의 자리 연결은 쌍 줄(두 문서 칸에 함께)
        page.screenshot(path=str(OUT / "01_std.png"), full_page=False)

        # ---- ①-2 문서마다 따로 넣기(spec_워크플로우 ② §18-6 — 2026-11-20 사용자 「원본 문서는 왜 네 맘대로 빼냐? … 따로 따로 하게」 · 「프로젝트 구성 반영을 왜 한줄에 놓냐, 따로따로 넣도록해야지. 왜 같이 묶냐고」 ·
        #      「프로젝트 구성을 완료하고 문서 검토하고 다른문서 프로젝트 구성할 수도 있잖아」): 줄 하나 = 문서 하나의 줄 · 넣기도 문서마다(목적 문서 줄 · 원본 문서 줄 — 고르기 둘) · 문서끼리의 차례는 자유 · 「목적 문서와 같이」 는 한 번에 따로 넣어 주는 단추
        # 워크플로우 전체 줄(구성 불러오기 · 프로젝트 구성 추출)은 두 칸에 걸치지 않고 한 칸에 선다(2026-11-20 사용자 「양쪽에 걸쳐 있는 것들은 왜 분리가 안되고 붙어 있나? 의미가 없는데」) — 구성 불러오기 = 목적 문서 칸 · 구성 확정 = 구성의 기준(원본) 문서 칸
        FIT_STD = [["configLoad", "목적"], ["config", "원본"], ["division", "목적"], ["reheads", "목적"], ["reheadsLlm", "목적"]]
        fitg = group(page, 1)
        f0 = page.evaluate(FIT)
        check("①-2 ⓐ 표준 차례의 2단계 — 「프로젝트 구성 반영」 은 목적 문서 줄 하나뿐(원본 문서 칸은 빈칸 — 체크 상자 · 줄의 묶는 단추 없음 · 단추는 ▲ ▼ 빼기) · 넣기 고르기는 둘(목적 문서 · 원본 문서) · 「목적 문서와 같이」 단추가 켜져 있다",
              s["groups"][1]["lines"] == FIT_STD and len(f0["div"]) == 1 and f0["div"][0]["role"] == "target" and f0["div"][0]["on"] == "1" and f0["div"][0]["blank"] == ["source"] and f0["div"][0]["boxes"] == 0
              and not f0["div"][0]["join"] and f0["div"][0]["btns"] == ["▲", "▼", "빼기"] and f0["adds"] == ["source", "target"] and ["source", "목적 문서와 같이", False] in f0["same"]
              and f0["srcDiv"] and not f0["srcDiv"][1], [s["groups"][1]["lines"], f0])
        p0 = page.evaluate(PAIRS, 1)
        cfg = {x["unit"]: x for x in p0["lines"] if x["unit"] in ("configLoad", "config")}
        one = lambda x, role: (x["role"] == role and sorted(c[0] for c in x["cells"]) == ["source", "target"]   # noqa: E731 — 한 칸 카드: 그 칸만 켜지고(쌍 칸 아님 · 작은 글 「워크플로우 전체」) 다른 칸은 빈칸
                               and [c for c in x["cells"] if c[0] == role] == [[role, "1", False, [c for c in x["cells"] if c[0] == role][0][3], "워크플로우 전체"]]
                               and [c[1:] for c in x["cells"] if c[0] != role] == [["", False, "", ""]])
        check("①-2 ⓐ 2단계의 「구성 불러오기」 · 「프로젝트 구성 추출」 은 한 칸 카드 — 구성 불러오기 = 목적 문서 칸 · 구성 확정 = 원본(구성의 기준) 문서 칸 · 작은 글 「워크플로우 전체」 · 옆 칸은 빈칸 · 쌍 칸 · 걸친 칸이 없다",
              len(cfg) == 2 and one(cfg["configLoad"], "target") and one(cfg["config"], "source") and p0["wide"] == 0 and not p0["common"]
              and page.evaluate("() => [...document.querySelectorAll('#wfCompose .wf-line-cell[data-wide]')].map((c) => c.dataset.unit).sort().join()") == "config,configLoad", [cfg, p0["wide"], p0["common"]])
        fitg.locator(".wf-lines-add[data-add=source]").select_option("division")   # 원본 문서 줄로 따로 넣는다 — 묶음 끝에(목적 문서의 구성 반영 · 다시 문서 검토 뒤)
        s = settle(page)
        f1 = page.evaluate(FIT)
        check("①-2 ⓑ 원본 문서 줄 넣기에서 「프로젝트 구성 반영」 → 묶음 끝에 원본 문서 줄 하나(목적 문서의 구성 반영 · 다시 문서 검토 뒤 — 따로 선 줄: 목적 문서 칸은 빈칸) · 거절 없음 · "
              "「원본 문서를 바꾸는 줄: 프로젝트 구성 반영」 · 「원본 문서의 구조를 바꾼 뒤 … 「자리 연결」 앞에 없습니다」 경고 · 「줄 목록으로 조립한」 · 저장 켜짐",
              s["groups"][1]["lines"] == FIT_STD + [["division", "원본"]] and [(x["role"], x["on"], x["blank"]) for x in f1["div"]] == [("target", "1", ["source"]), ("source", "1", ["target"])]
              and all(x["boxes"] == 0 and not x["join"] for x in f1["div"]) and not s["errs"] and "원본 문서를 바꾸는 줄: 프로젝트 구성 반영" in s["warns"]
              and any(w.startswith("원본 문서의 구조를 바꾼 뒤 원본 문서의 「다시 문서 검토」 가 「자리 연결」 앞에 없습니다") for w in s["warns"])
              and s["std"].startswith("줄 목록으로 조립한") and not s["save"]["off"], [s["groups"][1]["lines"], f1["div"], s["errs"], s["warns"], s["std"]])
        page.screenshot(path=str(OUT / "01b_apart.png"), full_page=False)
        src_div = fitg.locator(".wf-line-cell[data-unit=division][data-role=source]")   # 원본 문서 칸의 「프로젝트 구성 반영」 카드
        src_div.locator("button", has_text="▲").click()   # 그 카드를 한 걸음 위로 — 위 행(목적 문서의 다시 문서 검토(LLM))의 원본 칸이 빈칸이라 그 옆으로(같은 차례): 목적 문서의 줄은 그대로 있다
        s = settle(page)
        f2 = page.evaluate(FIT)
        check("①-2 ⓒ 그 원본 문서 카드의 ▲ → 위 행의 빈칸으로(목적 문서의 「다시 문서 검토(LLM)」 와 같은 차례 — 목적 문서의 줄은 안 움직인다: 「좌우가 같이 움직이잖아」) · 초점이 카드를 따라감 · 거절 없음 · 저장 켜짐",
              s["groups"][1]["lines"] == FIT_STD[:4] + [["reheadsLlm+division", "같이"]] and not s["errs"] and not s["save"]["off"]
              and page.evaluate("() => (document.activeElement && document.activeElement.dataset.lf) || ''") == "▲:1:4:source", [s["groups"][1]["lines"], s["errs"]])
        src_div.locator("button", has_text="▲").click()   # 한 걸음 더 — 같은 차례에서 나와 그 위의 제 행으로(목적 칸은 빈칸)
        s = settle(page)
        check("①-2 ⓒ 한 번 더 ▲ → 같은 차례에서 나와 제 행으로(목적 문서의 다시 문서 검토(LLM) 위 — 문서끼리의 차례는 자유): 거절 없음",
              s["groups"][1]["lines"] == FIT_STD[:4] + [["division", "원본"], ["reheadsLlm", "목적"]] and not s["errs"] and not s["save"]["off"], [s["groups"][1]["lines"], s["errs"]])
        f2 = page.evaluate(FIT)
        check("①-2 ⓓ 원본 문서 줄 넣기의 「프로젝트 구성 반영」 은 꺼지지 않는다 — 「 — 한 번 더」(같은 줄을 여러 번 놓을 수 있다: 전의 「이미 놓음」 꺼짐을 없앰)",
              bool(f2["srcDiv"]) and not f2["srcDiv"][1] and f2["srcDiv"][0].endswith(" — 한 번 더"), f2["srcDiv"])
        src_div.locator("button", has_text="빼기").click()
        s = settle(page)
        f3 = page.evaluate(FIT)
        check("①-2 ⓔ 그 원본 문서 카드를 「빼기」 → 표준 차례로 돌아옴(「표준 차례」 — 목적 문서 줄만) · 원본 문서 줄 넣기의 그 줄에서 「한 번 더」 가 사라짐",
              s["groups"][1]["lines"] == FIT_STD and s["groups"][0]["lines"] == STD1 and s["std"].startswith("표준 차례") and not s["errs"]
              and f3["srcDiv"] and not f3["srcDiv"][1] and "한 번 더" not in f3["srcDiv"][0], [s["groups"][1]["lines"], s["std"], s["errs"], f3["srcDiv"]])
        fitg.locator("button.wf-lines-same[data-same=source]").click()   # 「목적 문서와 같이」 — 목적 문서가 이 묶음에서 하는 줄을 원본 문서에도: 그 줄의 옆 칸(같은 행 — 같은 차례)에
        s = settle(page)
        f4 = page.evaluate(FIT)
        check("①-2 ⓕ 「목적 문서와 같이」 → 원본 문서 줄 셋(프로젝트 구성 반영 · 다시 문서 검토 · 다시 문서 검토(LLM))이 목적 문서의 같은 줄 **옆 칸**(같은 행 — 같은 차례)에 들어감 · 거절 없음 · "
              "「원본 문서의 구조를 바꾼 뒤 …」 경고 없음(원본 문서의 다시 문서 검토가 있다) · 그 단추는 꺼짐(더 넣을 줄이 없다)",
              s["groups"][1]["lines"] == FIT_STD[:2] + [["division", "같이"], ["reheads", "같이"], ["reheadsLlm", "같이"]]
              and [(x["role"], x["blank"]) for x in f4["div"]] == [("target", []), ("source", [])]
              and not s["errs"] and not any(w.startswith("원본 문서의 구조를 바꾼 뒤") for w in s["warns"]) and "원본 문서를 바꾸는 줄: 프로젝트 구성 반영" in s["warns"] and not s["save"]["off"]
              and any(x[0] == "source" and x[2] for x in f4["same"]), [s["groups"][1]["lines"], f4["div"], s["errs"], s["warns"], f4["same"]])
        page.screenshot(path=str(OUT / "01c_same.png"), full_page=False)
        for key in ("reheadsLlm", "reheads", "division"):   # 되돌림 — 원본 문서 카드 셋을 뺀다(표준 차례로)
            fitg.locator(f".wf-line-cell[data-unit={key}][data-role=source] button", has_text="빼기").click()
            s = settle(page)

        # ---- ①-3 행 × 두 칸(spec_워크플로우 ② §18-6 「행 × 두 칸」 — 2026-11-20 사용자 「각 도구가 같더라도 다른 시간 순서대로 적용할 수 있게 해야 하는데 지금은 그 배치가 안됨 … 마우스로 클릭 해서 드래그 해서 움직일 수도 있고
        #      다음단계는 공백/즉 다른문서만 작업하고 기다릴 수도 있게」 · 「이걸 같이 실행할 수 있는 기능이 없음. 그리고 도구는 1번 이상 선택할 수 있어야지 한번 하고 두번 선택이 안되냐」):
        #      카드는 제 칸에서 따로 움직인다(▲ ▼ · 끌어 놓기) · 한 행의 두 칸 = 같은 차례 · 빈칸 = 그 문서는 기다림 · 같은 줄을 여러 번 놓는다 · 저장 줄 = 같은 줄이면 하나(on 둘) · 다른 줄이면 둘(둘째에 beside)
        g0 = group(page, 0)
        card = lambda g, unit, role: g.locator(f".wf-line-cell[data-unit={unit}][data-role={role}]")  # noqa: E731 — 그 문서 칸의 그 줄 카드
        last_flow = lambda: json.loads(checks[-1])["flow"] if checks and checks[-1] else []  # noqa: E731 — 마지막 조립 검사에 보낸 줄 목록
        check("①-3 ⓐ 되돌린 뒤 표준 차례 · 카드마다 끌 손잡이(머리가 draggable) · 카드마다 제 단추(▲ ▼ 빼기)",
              s["std"].startswith("표준 차례") and s["groups"][0]["lines"] == STD1 and s["groups"][1]["lines"] == FIT_STD
              and page.evaluate("() => [...document.querySelectorAll('#wfCompose .wf-line-cell.wf-card')].every((c) => !!c.querySelector('.wf-card-head[draggable=true] .wf-card-grip') && "
                                "[...c.querySelectorAll('button')].map((b) => b.textContent).join('') === '▲▼빼기')"), [s["std"], s["groups"][0]["lines"]])
        card(g0, "heads", "target").locator("button", has_text="▼").click()   # 목적 문서의 「헤딩 · 표 분석」 만 한 걸음 아래로 — 같은 차례에서 나와 제 행으로(원본 문서의 줄은 그대로)
        s = settle(page)
        check("①-3 ⓑ 목적 문서 카드의 ▼ → 같은 차례에서 나와 제 행으로: 원본 문서의 「헤딩 · 표 분석」 → 목적 문서의 「헤딩 · 표 분석」 → 원본 문서의 「LLM 검증·보완」(원본 문서의 줄은 안 움직인다) · "
              "저장 줄 = 문서 하나씩 둘 · 「줄 목록으로 조립한」 · 거절 없음",
              s["groups"][0]["lines"] == [["heads", "원본"], ["heads", "목적"], ["headsLlm", "원본"]] and not s["errs"] and s["std"].startswith("줄 목록으로 조립한")
              and last_flow()[0]["steps"] == [{"unit": "heads", "on": ["source"]}, {"unit": "heads", "on": ["target"]}, {"unit": "headsLlm", "on": ["source"]}], [s["groups"][0]["lines"], s["errs"], last_flow()[:1]])
        page.keyboard.press("Enter")   # 초점이 그 카드의 ▼ 에 있다 — 한 걸음 더: 아래 행(원본 문서의 LLM 검증·보완)의 목적 칸이 빈칸이라 그 옆으로(같은 차례 — 다른 줄)
        s = settle(page)
        check("①-3 ⓒ 한 걸음 더(초점이 카드를 따라와 Enter) → 원본 문서의 「LLM 검증·보완」 과 같은 차례(한 행의 두 칸에 다른 줄) · 저장 줄 둘 — 둘째(목적 문서의 줄)에 beside · 거절 없음",
              s["groups"][0]["lines"] == [["heads", "원본"], ["heads+headsLlm", "같이"]] and not s["errs"]
              and last_flow()[0]["steps"] == [{"unit": "heads", "on": ["source"]}, {"unit": "headsLlm", "on": ["source"]}, {"unit": "heads", "on": ["target"], "beside": True}], [s["groups"][0]["lines"], s["errs"], last_flow()[:1]])
        page.screenshot(path=str(OUT / "01d_beside.png"), full_page=False)
        row0 = g0.locator(".wf-line").nth(0)
        card(g0, "heads", "target").locator(".wf-card-head").drag_to(row0, target_position={"x": 120, "y": 2})   # 끌어 놓기 — 첫 행의 위 가장자리(행 사이)에: 제 행으로
        s = settle(page)
        check("①-3 ⓓ 끌어 놓기 — 목적 문서 카드를 첫 행 위(행 사이)에 놓음 → 맨 위의 제 행(원본 칸은 빈칸 = 원본 문서는 그 차례에 기다림): 목적 → 원본 → 원본 LLM · 거절 없음",
              s["groups"][0]["lines"] == [["heads", "목적"], ["heads", "원본"], ["headsLlm", "원본"]] and not s["errs"]
              and page.evaluate("() => !document.querySelector('#wfCompose .wf-lines').classList.contains('wf-dragging') && !document.querySelector('#wfCompose [data-drop]')"), [s["groups"][0]["lines"], s["errs"]])
        card(g0, "heads", "target").locator(".wf-card-head").drag_to(g0.locator(".wf-line").nth(1).locator(".wf-line-cell[data-role=target]"))   # 끌어 놓기 — 둘째 행(원본 문서의 헤딩 · 표 분석)의 목적 빈칸에: 같은 차례로
        s = settle(page)
        check("①-3 ⓔ 끌어 놓기 — 그 카드를 원본 문서의 「헤딩 · 표 분석」 옆 빈칸에 놓음 → 같은 차례(같은 줄이라 저장 줄 하나: on 둘) → 표준 차례로 돌아옴(「표준 차례」)",
              s["groups"][0]["lines"] == STD1 and s["std"].startswith("표준 차례") and not s["errs"]
              and last_flow()[0]["steps"] == [{"unit": "heads", "on": ["source", "target"]}, {"unit": "headsLlm", "on": ["source"]}], [s["groups"][0]["lines"], s["std"], last_flow()[:1]])
        card(fitg, "reheads", "target").locator(".wf-card-head").drag_to(fitg.locator(".wf-line").nth(2).locator(".wf-line-cell[data-role=source]"))   # 다른 문서 칸에 — 2단계의 목적 「다시 문서 검토」 를 「프로젝트 구성 반영」 행의 원본 칸으로
        s = settle(page)
        check("①-3 ⓕ 끌어 놓기 — 목적 문서의 「다시 문서 검토」 를 원본 문서 칸(「프로젝트 구성 반영」 행의 빈칸)에 놓음 → 원본 문서의 줄이 된다(같은 차례) · 서버 검사의 거절 글이 그대로 보임(원본 문서의 구성 반영이 없다)",
              s["groups"][1]["lines"] == FIT_STD[:2] + [["division+reheads", "같이"], ["reheadsLlm", "목적"]] and bool(s["errs"]) and s["save"]["off"], [s["groups"][1]["lines"], s["errs"]])
        card(fitg, "reheads", "source").locator(".wf-card-head").drag_to(fitg.locator(".wf-line").nth(3), target_position={"x": 120, "y": 2})   # 되돌림 — 목적 칸 쪽의 행 사이(다시 문서 검토(LLM) 위)에
        s = settle(page)
        check("①-3 ⓕ 되돌림 — 그 카드를 목적 칸 쪽의 행 사이에 놓음 → 다시 목적 문서의 줄 · 표준 차례",
              s["groups"][1]["lines"] == FIT_STD and s["std"].startswith("표준 차례") and not s["errs"], [s["groups"][1]["lines"], s["std"], s["errs"]])
        g0.locator(".wf-lines-add[data-add=target]").select_option("heads")   # 같은 줄을 한 번 더 — 목적 문서의 「헤딩 · 표 분석」
        s = settle(page)
        check("①-3 ⓖ 같은 줄을 한 번 더 넣음(목적 문서의 「헤딩 · 표 분석」 — 옵션 「 — 한 번 더」) → 거절이 아니라 경고(「… 목적 문서에 두 번 넘게 놓았습니다 — 뒤의 줄은 그 차례에 와서 다시 봅니다 …」) · 저장 켜짐",
              s["groups"][0]["lines"] == STD1 + [["heads", "목적"]] and not s["errs"] and not s["save"]["off"]
              and any(w.startswith("「헤딩 · 표 분석」 을 목적 문서에 두 번 넘게 놓았습니다") and "다시 봅니다" in w for w in s["warns"]), [s["groups"][0]["lines"], s["errs"], s["warns"]])
        page.set_viewport_size({"width": 1500, "height": 1900})   # 끌 줄(3단계)과 놓을 자리(1단계)가 한 화면에 — 끄는 도중 화면이 밀리면 끌기가 끊긴다
        page.wait_for_timeout(200)
        link_head = group(page, 2).locator(".wf-line[data-unit=link] .wf-card-head").first
        link_head.drag_to(g0.locator(".wf-line").nth(2), target_position={"x": 300, "y": 2})   # 쌍 줄(원본 → 목적 줄)은 행째 — 3단계의 「자리 연결」 을 1단계의 마지막 행 위로
        s = settle(page)
        page.set_viewport_size({"width": 1500, "height": 1000})
        check("①-3 ⓗ 쌍 줄을 끌어 다른 묶음의 행 사이에 놓음 → 행째 옮겨진다(두 칸이 함께): 1단계 = 같이 · LLM · 자리 연결(쌍) · 헤딩(목적) · 3단계에서는 빠짐",
              s["groups"][0]["lines"] == STD1 + [["link", "쌍"], ["heads", "목적"]] and [x[0] for x in s["groups"][2]["lines"]] == ["llm", "plan", "gaps", "tableMap", "apply"], [s["groups"][0]["lines"], s["groups"][2]["lines"]])
        # 워크플로우 전체 줄 = 한 칸 카드 — 다른 문서 칸으로 옮길 수 있다(저장 줄에 col) · 다른 줄 옆에도 선다
        card(fitg, "config", "source").locator(".wf-card-head").drag_to(fitg.locator(".wf-line").nth(1).locator(".wf-line-cell[data-role=target]"))   # 「프로젝트 구성 추출」 을 제 행의 목적 문서 칸(빈칸)으로
        s = settle(page)
        check("①-3 ⓘ 워크플로우 전체 줄(「프로젝트 구성 추출」)을 목적 문서 칸에 끌어 놓음 → 그 칸의 카드가 된다(원본 칸은 빈칸) · 저장 줄에 col: target · 그 줄의 거절 없음(남은 거절은 앞에서 「자리 연결」 을 1단계로 올린 것)",
              s["groups"][1]["lines"][:2] == [["configLoad", "목적"], ["config", "목적"]] and not any("구성 확정" in e or "구성 불러오기" in e for e in s["errs"])
              and last_flow()[1]["steps"][:2] == [{"unit": "configLoad", "on": []}, {"unit": "config", "on": [], "col": "target"}], [s["groups"][1]["lines"], s["errs"], last_flow()[1:2]])
        card(fitg, "division", "target").locator(".wf-card-head").drag_to(fitg.locator(".wf-line").nth(1), target_position={"x": 700, "y": 20})   # 그 옆 칸(원본 칸 — 빈칸)에 문서 줄을: 「프로젝트 구성 반영」 을 원본 문서의 줄로 같은 차례에
        s = settle(page)
        check("①-3 ⓘ 그 옆 빈칸에 문서 줄을 끌어 놓음 → 워크플로우 전체 줄과 같은 차례(한 행의 두 칸) · 저장 줄 둘 — 워크플로우 전체 줄이 먼저 · 문서 줄에 beside(「구성 확정 뒤에 와야 합니다」 거절 없음)",
              s["groups"][1]["lines"][:2] == [["configLoad", "목적"], ["config+division", "같이"]] and not any("「프로젝트 구성 추출」 뒤에" in e for e in s["errs"])
              and last_flow()[1]["steps"][1:3] == [{"unit": "config", "on": [], "col": "target"}, {"unit": "division", "on": ["source"], "beside": True}], [s["groups"][1]["lines"], s["errs"], last_flow()[1:2]])
        page.uncheck("#wfCompose input[name=assign-source][value=stage_review]")   # 되돌림 — 표로 다시 채운다(아래 ② 가 표준 차례에서 시작한다)
        settle(page)
        page.check("#wfCompose input[name=assign-source][value=stage_review]")
        s = settle(page)
        check("①-3 되돌림 — 표에서 다시 고르면 줄 목록이 표준 차례로 다시 채워진다", s["std"].startswith("표준 차례") and s["groups"][0]["lines"] == STD1 and s["groups"][1]["lines"] == FIT_STD, [s["std"], s["groups"][0]["lines"], s["groups"][1]["lines"]])

        # ---- ② 표에서 고름 → 줄 목록이 그 표준 차례로
        page.uncheck("#wfCompose input[name=assign-target][value=stage_fit]")
        s = settle(page)
        check("② 표에서 목적 문서의 「구성 맞추기」 를 끔 → 줄 목록이 그 표준 차례(묶음 셋 — 구성 맞추기 없음) · 「표준 차례」",
              [g["name"] for g in s["groups"]] == ["문서 검토", "내용 넣기", "문서 정리"] and s["std"].startswith("표준 차례"), s)
        page.check("#wfCompose input[name=assign-target][value=stage_fit]")
        settle(page)

        # ---- ③ 줄을 고쳐 표준이 아닌 정의 — 원본만 검토 → 넣기
        page.fill("#wfCompose input[name=name]", "원본 검토 뒤 넣기")
        for _ in range(3):   # 2 · 3 · 4단계 묶음 빼기 — 1단계만 남김
            group(page, 1).locator("button", has_text="묶음 빼기").click()
            settle(page)
        group(page, 0).locator(".wf-line-cell[data-unit=heads][data-role=target]").locator("button", has_text="빼기").click()   # 헤딩 · 표 분석 — 목적 문서 카드만 뺀다(같은 행의 원본 문서 카드는 남음)
        settle(page)
        page.locator("#wfCompose .wf-lines > button", has_text="＋ 묶음").click()
        settle(page)
        # ---- ③-2 쌍 줄(spec_워크플로우 ② §18-6 — 2026-11-20 사용자 「이것들 어떤 도구는 대상이 있어야 사용할 수 있는게 있어 잘 연결될 수 있도록」 · 「열을 분할해줘, 대상이 있어야 하는 경우에는 2개를 쌍으로 넣을 수 있게 해주면 되잖아 …
        #      순차적임을 표현하기 위해 한쪽은 공백을 두고 다른 한쪽은 도구를 주고」): 상대 문서가 있어야 하는 줄(원본 → 목적 줄)은 두 문서 칸에 쌍으로 서고(걸친 칸이 없다), 넣기는 문서 칸의 고르기 둘뿐 —
        #      쌍 줄은 어느 칸에서 골라도 쌍 줄 하나. 앞 줄이 있어야 하는 줄은 그 줄이 없으면 꺼지고(「먼저 「…」 을 넣으세요」), 넣으면 그 앞 줄 뒤 제자리에 선다.
        #      끝에 줄 목록을 자리 연결 · 넣기 계획 · 내용 반영으로 되돌려 ③ 의 뒤 기대(④ · 저장 · ⑤)가 그대로 이어진다
        add = lambda key, col="target": (group(page, 1).locator(f".wf-lines-add[data-add={col}]").select_option(key), settle(page))[1]  # noqa: E731 — 그 문서 칸의 고르기로 줄 넣기 → 검사가 끝난 뒤의 줄 목록
        cut = lambda key: (group(page, 1).locator(f".wf-line[data-unit={key}]").locator("button", has_text="빼기").click(), settle(page))[1]  # noqa: E731 — 그 줄의 「빼기」
        NEED = ("plan", "apply", "llm", "gaps", "tableMap")   # 앞 줄이 있어야 하는 줄(자리 연결 LLM 검토 · 넣기 계획 → 자리 연결 / 빈 자리 검토 · 표 대응 · 내용 반영 → 넣기 계획)
        HINT = {"target": "← 원본 문서에서", "source": "→ 목적 문서로"}   # 원본 → 목적 줄의 칸마다 작은 글

        def paired(x):   # 쌍 줄인가 — 두 문서 칸에 같은 이름(켜진 쌍 칸 둘) · 칸마다 제 작은 글
            c = {k[0]: k for k in x["cells"]}
            return (x["role"] == "pair" and sorted(c) == ["source", "target"] and len(x["cells"]) == 2 and all(k[1] == "1" and k[2] and k[3] for k in x["cells"])
                    and c["source"][3] == c["target"][3] and all(c[r][4] == HINT[r] for r in HINT))

        off = lambda o, k: o[k][1] and "먼저 「" in o[k][0] and "넣으세요" in o[k][0] and "(대상)" not in o[k][0]  # noqa: E731 — 꺼진 옵션 + 까닭 글(「먼저 「…」 을 넣으세요」)
        u0 = page.evaluate(PAIRS)
        check("③-2 ⓐ 빈 묶음의 넣기 — 고르기는 문서 칸 둘뿐(목적 문서 · 원본 문서) · 쌍 줄은 두 고르기 모두에 있고(「 (쌍)」) · 앞 줄이 있어야 하는 줄(넣기 계획 · 내용 반영 · 자리 연결 LLM 검토 · 빈 자리 검토 · 표 대응)은 "
              "꺼져 있고 까닭 글(「먼저 「…」 을 넣으세요」) · 「자리 연결」 은 켜짐",
              u0["adds"] == ["source", "target"]
              and all(k in u0[col] and off(u0[col], k) and "(쌍)" in u0[col][k][0] for col in ("target", "source") for k in NEED)
              and all("link" in u0[col] and not u0[col]["link"][1] and u0[col]["link"][0].endswith("(쌍)") for col in ("target", "source")), [u0["adds"], u0["target"], u0["source"]])
        add("link")
        u1 = page.evaluate(PAIRS)
        name_of = lambda k: (u0 if k == "link" else u1)["target"][k][0].split(" (쌍)")[0].strip()  # noqa: E731 — 화면의 줄 이름(글을 박지 않고 고르기의 **켜진** 옵션 글 「<이름> (쌍)」 에서 — 자리 연결은 ⓐ · 넣기 계획은 ⓑ 에서 켜져 있다)
        check("③-2 ⓑ 목적 문서 칸에서 「자리 연결」 을 고름 → 쌍 줄 하나(두 문서 칸에 같은 이름 — 목적 칸 「← 원본 문서에서」 · 원본 칸 「→ 목적 문서로」 · 걸친 칸 없음) · "
              "「넣기 계획」 · 「자리 연결 LLM 검토」 가 켜지고, 「내용 반영」 · 「빈 자리 검토」 · 「표 대응」 은 아직 꺼짐(까닭 글에 넣기 계획의 이름)",
              [x["unit"] for x in u1["lines"]] == ["link"] and paired(u1["lines"][0]) and u1["wide"] == 0 and not u1["common"]
              and all(not u1[col]["plan"][1] and not u1[col]["llm"][1] for col in ("target", "source"))
              and all(off(u1[col], k) and f"먼저 「{name_of('plan')}」" in u1[col][k][0] for col in ("target", "source") for k in ("apply", "gaps", "tableMap")), [u1["lines"], u1["target"], u1["wide"]])
        add("plan", "source")   # 원본 문서 칸의 고르기에서 골라도 쌍 줄 하나(원본 문서만의 줄이 되지 않는다)
        s = add("apply")
        u2 = page.evaluate(PAIRS)
        check("③-2 ⓒ 원본 문서 칸에서 「넣기 계획」 · 목적 문서 칸에서 「내용 반영」 을 고름 → 어느 칸에서 골라도 쌍 줄(셋 모두 두 문서 칸에 같은 이름) · 차례 = 자리 연결 · 넣기 계획 · 내용 반영 · 걸친 칸 없음 · 거절 없음",
              [x["unit"] for x in u2["lines"]] == ["link", "plan", "apply"] and all(paired(x) for x in u2["lines"]) and u2["wide"] == 0 and not u2["common"]
              and [x["cells"][0][3] for x in u2["lines"]][:2] == [name_of("link"), name_of("plan")] and not s["errs"], [u2["lines"], u2["wide"], s["errs"]])
        add("tableMap")
        u3 = page.evaluate(PAIRS)
        check("③-2 ⓓ 「표 대응(LLM)」 을 고름 → 그 앞 줄(넣기 계획) 뒤 제자리 = 넣기 계획과 내용 반영 사이(묶음 끝이 아니다)",
              [x["unit"] for x in u3["lines"]] == ["link", "plan", "tableMap", "apply"], [x["unit"] for x in u3["lines"]])
        add("gaps", "source")
        s = add("llm")
        u4 = page.evaluate(PAIRS)
        check("③-2 ⓓ 이어서 「빈 자리 검토(LLM)」 → 넣기 계획 바로 뒤(표 대응 앞 — 서버의 줄 차례) · 「자리 연결 LLM 검토」 → 자리 연결 바로 뒤: 보이는 줄 차례 = 자리 연결 · LLM 검토 · 넣기 계획 · 빈 자리 검토 · 표 대응 · 내용 반영 · "
              "여섯 줄 모두 쌍 줄 · 거절 없음 · 저장 켜짐",
              [x["unit"] for x in u4["lines"]] == ["link", "llm", "plan", "gaps", "tableMap", "apply"] and all(paired(x) for x in u4["lines"]) and u4["wide"] == 0
              and not s["errs"] and not s["save"]["off"], [u4["lines"], s["errs"]])
        group(page, 1).scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "03b_pairs.png"), full_page=False)
        s = cut("plan")
        u5 = page.evaluate(PAIRS)
        check("③-2 ⓔ 「넣기 계획」 줄을 「빼기」 → 그 줄이 있어야 하는 줄(빈 자리 검토 · 표 대응 · 내용 반영)이 남아 서버의 거절 글이 뜨고 저장이 꺼짐 · 고르기의 「넣기 계획」 은 다시 켜짐",
              [x["unit"] for x in u5["lines"]] == ["link", "llm", "gaps", "tableMap", "apply"] and bool(s["errs"]) and s["save"]["off"]
              and not u5["target"]["plan"][1] and not u5["source"]["plan"][1], [[x["unit"] for x in u5["lines"]], s["errs"], s["save"], u5["target"].get("plan")])
        for key in ("gaps", "tableMap", "llm"):   # 되돌림 — 선택 줄 셋을 빼고 넣기 계획을 다시 넣는다
            cut(key)
        s = add("plan")
        u6 = page.evaluate(PAIRS)
        check("③-2 ⓕ 되돌림 — 선택 줄 셋을 빼고 「넣기 계획」 을 다시 넣음 → 자리 연결 뒤 · 내용 반영 앞 제자리로(묶음 끝이 아니다): 자리 연결 · 넣기 계획 · 내용 반영 · 거절 없음",
              [x["unit"] for x in u6["lines"]] == ["link", "plan", "apply"] and all(paired(x) for x in u6["lines"]) and not s["errs"], [u6["lines"], s["errs"]])
        group(page, 1).locator(".wf-lines-ghead input").fill("넣기")
        group(page, 1).locator(".wf-lines-ghead input").press("Tab")
        s = settle(page)
        check("③ 원본만 검토 → 넣기(묶음 빼기 · 목적 문서 줄 빼기 · ＋ 묶음 · 쌍 줄 넣기) — 거절 없음 · 경고(목적 문서의 분석 없음 · 구성 반영 없음 · 유료) · 「줄 목록으로 조립한 워크플로우」 · 표는 접힘 아님(그대로) · 저장 켜짐",
              [[g["name"], [x[0] for x in g["lines"]]] for g in s["groups"]] == [["문서 검토", ["heads", "headsLlm"]], ["넣기", ["link", "plan", "apply"]]] and s["groups"][0]["lines"] == [["heads", "원본"], ["headsLlm", "원본"]]
              and [x[1] for x in s["groups"][1]["lines"]] == ["쌍"] * 3
              and not s["errs"] and s["std"].startswith("줄 목록으로 조립한") and any("목적 문서의 「헤딩 · 표 분석」" in w for w in s["warns"]) and any("「프로젝트 구성 반영」 이 없습니다" in w for w in s["warns"])
              and not s["save"]["off"], s)
        # ---- ④ 차례가 거꾸로 → 거절 · 저장 꺼짐 / 사람이 하는 일은 「아직」
        group(page, 1).locator(".wf-line").nth(1).locator("button", has_text="▲").click()   # 넣기 계획을 자리 연결 위로
        s = settle(page)
        check("④ 「넣기 계획」 을 「자리 연결」 위로 → 서버의 거절 글(「… 뒤에 와야 합니다」) · 저장 단추 꺼짐 · 「사람이 하는 일」 은 고를 수 있음(실행기가 그 줄에서 멈춘다)",
              any("뒤에 와야 합니다" in e for e in s["errs"]) and s["save"]["off"] and s["handOpt"] and not s["handOpt"][1], s)
        page.screenshot(path=str(OUT / "04_err.png"), full_page=False)
        group(page, 1).locator(".wf-line").nth(0).locator("button", has_text="▼").click()
        s = settle(page)
        n0 = len(bodies)
        page.locator("#wfCompose form button[type=submit]").click()
        page.wait_for_function("() => !document.querySelector('#wfCompose form')", timeout=30000)
        body = json.loads(bodies[n0][2]) if len(bodies) > n0 and bodies[n0][2] else {}
        made = [t for t in requests.get(f"{base}/api/tasks?v=2", timeout=10).json()["tasks"] if t["name"] == "원본 검토 뒤 넣기"]
        check("③ 저장 — 몸 = flow(assign 없음) · 서버가 v2 로(묶음 g1 · g2 · assign 없음) · 판 없는 읽기에는 안 보임",
              "flow" in body and "assign" not in body and len(made) == 1 and made[0]["v"] == 2 and made[0]["groups"] == ["g1", "g2"] and made[0]["assign"] is None
              and made[0]["key"] not in [t["key"] for t in requests.get(f"{base}/api/tasks", timeout=10).json()["tasks"]], [body, made])
        key = made[0]["key"] if made else ""
        page.wait_for_selector(f"section#{key}", state="attached", timeout=30000)
        sec = page.evaluate(f"() => [...document.querySelectorAll('section#{key} li.wf-stage')].map((li) => [li.dataset.stage, li.querySelector('h3').textContent, [...li.querySelectorAll('details.wf-step')].map((d) => d.dataset.step)])")
        check("그 워크플로우의 절 — 묶음 g1 「문서 검토」(준비 · 헤딩 · 표 분석 · LLM 검증·보완) · g2 「넣기」(자리 연결 · 넣기 계획 · 내용 반영)",
              sec == [["g1", "문서 검토", ["files", "heads", "headsLlm"]], ["g2", "넣기", ["link", "plan", "apply"]]], sec)

        # ---- ⑤ 고치기 — 줄 목록으로 열림 · 묶음 이름만 고쳐 저장 → 지문 그대로
        sig0 = made[0]["sig"]
        page.evaluate(f"() => document.querySelector('#wfCompose [data-task=\"{key}\"] button').click()")
        s = settle(page)
        check("⑤ 「고치기」 — v2 정의가 줄 목록으로 열림(표는 접힘) · 「줄 목록으로 조립한」",
              [[g["id"], g["name"]] for g in s["groups"]] == [["g1", "문서 검토"], ["g2", "넣기"]] and not s["tableOpen"] and s["std"].startswith("줄 목록으로 조립한"), s)
        group(page, 1).locator(".wf-lines-ghead input").fill("내용 넣기만")
        group(page, 1).locator(".wf-lines-ghead input").press("Tab")
        settle(page)
        n0 = len(bodies)
        page.locator("#wfCompose form button[type=submit]").click()
        page.wait_for_function("() => !document.querySelector('#wfCompose form')", timeout=30000)
        body = json.loads(bodies[n0][2]) if len(bodies) > n0 and bodies[n0][2] else {}
        t = next(x for x in requests.get(f"{base}/api/tasks?v=2", timeout=10).json()["tasks"] if x["key"] == key)
        check("⑤ 묶음 이름만 고쳐 저장 — 몸 = flow · 이름 바뀜 · 지문 그대로", "flow" in body and t["flow"][1]["name"] == "내용 넣기만" and t["sig"] == sig0, [body, t["flow"][1]["name"], t["sig"], sig0])

        # ---- ⑤b 단계 만들기(② §18-14 — 2026-11-20 사용자 「이 단계 만들기도 있어야 하는거 아니냐?」): 있는 줄을 골라 내 단계 → 조립의 「＋ 단계 넣기…」
        page.click("#wfNav [data-wf-stage=new]")
        page.wait_for_selector("#wfStage form.wf-form")
        page.fill("#wfStage input[name=stage-name]", "원본만 검토")
        page.locator("#wfStage .wf-lines-add[data-add=source]").select_option("heads")   # 원본 문서 줄 넣기 — 헤딩 · 표 분석(원본 문서 줄 하나)
        page.wait_for_selector("#wfStage .wf-line[data-unit=heads][data-role=source]")
        page.wait_for_function("() => { const b = document.querySelector('#wfStage .wf-lines'), go = document.querySelector('#wfStage form button[type=submit]'); return b && go && !/검사하는 중/.test(b.textContent) && !go.disabled "
                               "&& b.querySelectorAll('.wf-line[data-unit=heads][data-role=source]').length === 1 && !b.querySelector('.wf-line[data-unit=heads][data-role=target]'); }", timeout=30000)
        page.click("#wfStage form button[type=submit]")
        page.wait_for_selector("#wfNav a.wf-mine", timeout=30000)
        st = requests.get(f"{base}/api/tasks?v=2", timeout=10).json()["userStages"]
        nav = page.evaluate("() => ({ mine: [...document.querySelectorAll('#wfNav a.wf-mine')].map((a) => a.textContent), list: [...document.querySelectorAll('#wfStage .wf-made-list > li')].map((li) => li.textContent), form: !!document.querySelector('#wfStage form') })")
        check("⑤b 「＋ 단계 만들기」 → 이름 · 줄(원본 문서 줄 넣기로 헤딩 · 표 분석 — 원본 문서 줄 하나) → 저장: 서버의 내 단계 · 목차 「단계」 아래 · 절의 목록 · 폼 닫힘",
              len(st) == 1 and st[0]["name"] == "원본만 검토" and st[0]["steps"] == [{"unit": "heads", "on": ["source"]}] and nav["mine"] == ["원본만 검토"] and "헤딩 · 표 분석" in nav["list"][0] and not nav["form"], [st, nav])
        page.click("#wfCompose [data-wf-compose=open]")
        settle(page)
        opts = page.evaluate("() => [...document.querySelectorAll('#wfCompose .wf-lines-addstage option')].map((o) => [o.textContent, o.disabled])")
        group(page, 0).locator("button", has_text="묶음 빼기").click()   # 「문서 검토」 묶음을 빼면 그 줄을 다시 넣을 수 있다
        settle(page)
        page.locator("#wfCompose .wf-lines-addstage").select_option(st[0]["key"] if st else "")
        s = settle(page)
        check("⑤b 조립의 「＋ 단계 넣기…」 — 기본 단계 넷 + 내 단계(이미 놓인 줄이어도 꺼지지 않는다 — 같은 줄을 여러 번 놓을 수 있다) → 넣으면 끝에 묶음 「원본만 검토」(헤딩 · 표 분석 — 원본)",
              opts[:5] == [["＋ 단계 넣기…", False], ["문서 검토", False], ["구성 맞추기", False], ["내용 넣기", False], ["문서 정리", False]] and opts[5:] == [["원본만 검토", False]]
              and s["groups"][-1]["name"] == "원본만 검토" and s["groups"][-1]["lines"] == [["heads", "원본"]], [opts, s["groups"][-1]])
        page.screenshot(path=str(OUT / "05b_stage.png"), full_page=False)
        page.locator("#wfCompose form button", has_text="취소").click()

        # ---- ⑥ 좁은 폭
        page.set_viewport_size({"width": 400, "height": 900})
        page.evaluate(f"() => document.querySelector('#wfCompose [data-task=\"{key}\"] button').click()")
        settle(page)
        fit = page.evaluate("() => { const m = document.getElementById('wfMain'), b = document.querySelector('#wfCompose .wf-lines').getBoundingClientRect(); return { over: m.scrollWidth > m.clientWidth + 1, right: b.right <= m.getBoundingClientRect().right + 1 }; }")
        page.screenshot(path=str(OUT / "06_narrow.png"), full_page=False)
        check("⑥ 400px — 단계 칸이 가로로 넘치지 않음", not fit["over"] and fit["right"], fit)
        # ---- ⑦ 표준 네 묶음으로는 나타낼 수 없던 정의가 저장한 차례 그대로 돈다(② §18-12 ① 의 끝) — 원본 검토 → 사람이 결과 확인(했음) → 목적 문서 정리 · 첫 화면 대시보드에서
        flow7 = [{"name": "원본 검토", "steps": [{"unit": "heads", "on": ["source"]}]}, {"name": "사람 확인", "steps": [{"unit": "hand", "on": ["target"], "name": "결과 확인", "note": "원본의 헤딩 판정을 본다"}]},
                 {"name": "목적 정리", "steps": [{"unit": "guide", "on": ["target"]}]}]
        r7 = requests.post(f"{base}/api/tasks", json={"name": "원본 검토 · 사람 확인 · 목적 정리", "flow": flow7}, timeout=30)
        check("⑦ 사람이 하는 일을 낀 정의를 저장(서버 실행기가 그 줄에서 멈춤 — 갈래 A) — 201 · v2", r7.status_code == 201 and r7.json()["task"]["v"] == 2, r7.text[:300])
        key7 = r7.json()["task"]["key"] if r7.status_code == 201 else ""
        home = ctx.new_page()
        home.set_viewport_size({"width": 1600, "height": 1000})
        home.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        home.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        home.goto(base)
        home.wait_for_selector("#homeDash[data-state=pick] select")
        with home.expect_file_chooser() as fc:
            home.locator("#pickBtn").click()
        fc.value.set_files([str(PLAN), str(REPORT)])
        home.wait_for_function("() => document.querySelectorAll('#homeFiles .hf-row').length >= 2")
        home.locator("#homeFiles .hf-row").nth(1).locator("input[type=radio]").check()   # 목적 문서 = 연차보고서
        home.locator("#homeFiles [data-hf-focus=project]").fill("사람 확인 시험")
        home.select_option("#homeDash select", key7)
        home.wait_for_selector("#homeDash[data-state=ready] .dash-group", timeout=30000)
        home.locator('#homeDash [data-hd-focus="start"]').click()
        home.wait_for_selector("#homeDash[data-state=live] .dash-group", timeout=180000)
        btn = lambda gid: f'#homeDash .dash-group[data-group="{gid}"] .dash-ghead button'  # noqa: E731
        on = lambda gid: f"() => {{ const b = document.querySelector('{btn(gid)}'); return !!b && !b.disabled; }}"  # noqa: E731
        home.wait_for_function(on("g2"), timeout=240000)   # 1단계(원본 분석)는 올린 직후의 기본 분석으로 끝난다 — 2단계가 다음
        pre = home.evaluate(f"() => {{ const b = document.querySelector('{btn('g3')}'); return {{ off: !b || b.disabled, title: b ? b.title : '' }}; }}")
        check("⑦ 시작 — 1단계 끝남(기본 분석) · 2단계(사람 확인) 「한 번에 진행」 켜짐 · 3단계는 「2단계 … 이 먼저입니다」 로 꺼짐", pre["off"] and "먼저" in pre["title"], pre)
        home.locator(btn("g2")).click()
        home.wait_for_function("() => /사람이 할 일/.test((document.querySelector('#homeDash .dash-last') || {}).textContent || '')", timeout=120000)
        halt = home.evaluate("() => ({ last: document.querySelector('#homeDash .dash-last').textContent, halt: !!document.querySelector('#homeDash .dash-last.halt') })")
        home.wait_for_selector('#homeDash [data-hd-focus="hand:hand1"]', timeout=30000)
        hb = home.evaluate("() => { const b = document.querySelector('#homeDash [data-hd-focus=\"hand:hand1\"]'); return { text: b.textContent, primary: b.classList.contains('primary') }; }")
        g3off = home.evaluate(f"() => {{ const b = document.querySelector('{btn('g3')}'); return !b || b.disabled; }}")
        check("⑦ 2단계 「한 번에 진행」 → 「사람이 할 일 — 결과 확인: 원본의 헤딩 판정을 본다 …」 에서 멈춤(주황) · 그 줄에 「했음」(강조) · 3단계는 아직 꺼짐",
              "사람이 할 일 — 결과 확인" in halt["last"] and "원본의 헤딩 판정을 본다" in halt["last"] and halt["halt"] and hb == {"text": "했음", "primary": True} and g3off, [halt, hb, g3off])
        home.locator('#homeDash [data-hd-focus="hand:hand1"]').click()
        home.wait_for_function("() => (document.querySelector('#homeDash [data-hd-focus=\"hand:hand1\"]') || {}).textContent === '했음 취소'", timeout=30000)
        home.wait_for_function(on("g3"), timeout=60000)   # 「했음」 → 2단계가 끝난 것으로 세져 3단계가 켜진다(서버의 상태 식)
        home.locator(btn("g3")).click()
        home.wait_for_function("() => !document.querySelector('#homeDash .dash-live') && /^끝남/.test((document.querySelector('#homeDash .dash-last') || {}).textContent || '')", timeout=240000)
        fin = home.evaluate("() => ({ last: document.querySelector('#homeDash .dash-last').textContent, groups: [...document.querySelectorAll('#homeDash .dash-group')].map((g) => [g.dataset.group, g.querySelector('.dash-gcount').textContent]), home: document.body.classList.contains('no-doc') })")
        home.screenshot(path=str(OUT / "07_hand_run.png"), full_page=False)
        check("⑦ 「했음」 → 3단계 「목적 정리」(작성요령 삭제)가 켜지고 돌아 끝남 — 묶음 g1 · g2 · g3 이 저장한 차례대로 끝남 · 첫 화면 그대로",
              fin["home"] and [g for g, _ in fin["groups"]] == ["g1", "g2", "g3"] and all(c.split("/")[0] == c.split("/")[1] for _, c in fin["groups"]), fin)
        # ---- ⑧ 도구 설명 열(spec_워크플로우 ② §18-15 — 2026-11-20 사용자 「우측에 각 도구가 어떤 역할을 하는지 설명해줘. 자리연결누르면 우측 열에 설명을 넣어주 … 모든도구」):
        #      폼 | 「도구 설명」 열 · 안 골랐으면 그 틀의 도구 목록 · 카드를 누르면 그 도구의 설명(쌍 줄 = 어느 칸이든 · 두 칸에 표시) · 단추 · 빈칸은 고른 것을 안 바꿈 · 줄을 옮겨도 그대로 ·
        #      자판 · 목록에서 고르기(넣기 전) · 취합형의 글 · 설명을 열어도 조립 검사 · 저장 상태는 그대로 · 좁은 창 = 폼 위 · 「단계 만들기」 폼에도
        page.set_viewport_size({"width": 1500, "height": 1000})
        page.reload()   # 같은 주소(#overview)로 goto 하면 문서를 다시 읽지 않는다 — ⑥ 의 「고치기」 폼이 펴진 채다
        page.wait_for_selector("#wfCompose [data-wf-compose=open]")
        page.click("#wfCompose [data-wf-compose=open]")
        s8 = settle(page)
        HELP = """() => { const a = document.querySelector('#wfCompose .wf-help'), f = document.querySelector('#wfCompose .wf-compose-cols > form'), m = document.getElementById('wfMain'); if (!a || !f) return null;
          const ar = a.getBoundingClientRect(), fr = f.getBoundingClientRect(), t = (q) => (a.querySelector(q) || {}).textContent || '', act = document.activeElement;
          return { title: t('.wf-help-head h3'), unit: a.dataset.unit, right: ar.left >= fr.right, sticky: getComputedStyle(a).position, over: m.scrollWidth > m.clientWidth + 1,
            wide: document.getElementById('wfCompose').classList.contains('wf-wide'),
            groups: [...a.querySelectorAll('.wf-help-group')].map((g) => [(g.querySelector('h5') || {}).textContent || '', g.querySelectorAll('.wf-help-item').length]),
            easyBy: Object.fromEntries([...a.querySelectorAll('.wf-help-item')].map((b) => [b.dataset.helpGo, ((b.querySelector('.wf-help-item-easy') || {}).textContent || '').trim()])),
            listShown: !!a.querySelector('.wf-help-list') && a.querySelector('.wf-help-list').checkVisibility(),
            name: t('.wf-help-name'), easy: t('.wf-help-easy'), off: !!a.querySelector('.wf-help-off'), facts: [...a.querySelectorAll('.wf-help-facts li')].map((x) => x.textContent),
            secs: [...a.querySelectorAll('.wf-help-sec')].map((x) => x.querySelector('h5').textContent), text: Object.fromEntries([...a.querySelectorAll('.wf-help-sec')].map((x) => [x.querySelector('h5').textContent, x.textContent])),
            chips: [...a.querySelectorAll('.wf-help-go')].map((b) => [b.dataset.helpGo, b.textContent]),
            focus: !act || act === document.body ? '' : act.dataset.helpFor ? 'card:' + act.dataset.helpFor : act.classList.contains('wf-help-name') ? 'name' : act.dataset.helpGo ? 'item:' + act.dataset.helpGo : act.className || act.tagName,
            marked: [...document.querySelectorAll('#wfCompose .wf-line-cell[data-help="1"]')].map((c) => [c.dataset.unit || c.closest('.wf-line').dataset.unit, c.dataset.role]) }; }"""   # marked = 파란 테두리의 카드(그 칸의 줄 — 한 행에 다른 두 줄이 서면 칸마다 다르다)
        api8 = requests.get(f"{base}/api/tasks?v=2", timeout=30).json()
        h0 = page.evaluate(HELP)
        check("⑧ ⓐ 폼이 펴지면 오른쪽에 「도구 설명」 열(폼의 오른쪽 · 붙어 있음 · 그 절만 넓어짐 · 가로 넘침 없음) — 안 골랐으면 그 틀의 도구 목록: 사는 단계로 묶어 18개(「문서 정리」 = 작성요령 삭제 + 지침 보정 · 빈 구역 지우기 — ② §18-23) · 줄마다의 한 문장 = 서버 응답의 help.easy 그대로",
              h0 and h0["title"] == "도구 설명" and h0["unit"] == "" and h0["right"] and h0["sticky"] == "sticky" and h0["wide"] and not h0["over"] and h0["listShown"]
              and h0["groups"] == [["문서 검토", 2], ["구성 맞추기", 6], ["내용 넣기", 6], ["문서 정리", 3], ["사람이 하는 일", 1]]
              and h0["easyBy"] == {u["key"]: u["help"]["easy"] for u in api8["units"]} and all(h0["easyBy"].values()), h0)
        n_checks, n_saves, save0 = len(checks), len(bodies), s8["save"]
        page.locator('#wfCompose li.wf-line[data-unit=link] .wf-line-cell[data-role=target]').click(position={"x": 120, "y": 14})   # 「자리 연결」 — 쌍 줄의 목적 문서 칸(이름 옆의 빈 곳)
        h1 = page.evaluate(HELP)
        WANT = ["어느 문서에 쓰나요?", "먼저 필요한 것", "알아 둘 것", "결과는 어디서 보나요?", "예", "이 결과를 쓰는 도구"]
        check("⑧ ⓑ 「자리 연결」 카드를 누름 → 그 도구의 설명(한 문장 · 누가 「자동으로 합니다」 · 문서 「그대로」 · 칸의 차례 = 어느 문서에 → 먼저 필요한 것 → 알아 둘 것 → 결과는 어디서 → 예 → 이 결과를 쓰는 도구) · 쌍 줄의 두 칸에 표시",
              h1["unit"] == "link" and h1["name"] == "자리 연결" and "서로 맞는 자리" in h1["easy"] and not h1["off"] and h1["secs"] == WANT
              and h1["facts"] == ["누가자동으로 합니다", "문서문서는 그대로입니다"] and "두 칸이 한 줄로" in h1["text"][WANT[0]] and "1곳에 놓여" in h1["text"][WANT[0]]
              and "구조를 반영한 기록" in h1["text"][WANT[1]] and "관련된 앞 도구" in h1["text"][WANT[1]] and "확인 필요" in h1["text"][WANT[2]] and "연결 목록" in h1["text"][WANT[3]]
              and sorted(h1["marked"]) == [["link", "source"], ["link", "target"]] and ["plan", "표 안 연결 · 넣기 계획"] in h1["chips"], h1)
        page.screenshot(path=str(OUT / "08_help_link.png"), full_page=False)
        fit8 = group(page, 1)
        card(group(page, 0), "heads", "target").click(position={"x": 120, "y": 14})   # 다른 도구로 갔다가
        c0 = page.evaluate(HELP)["unit"]
        page.locator('#wfCompose li.wf-line[data-unit=link] .wf-line-cell[data-role=source]').click(position={"x": 120, "y": 14})   # 쌍 줄의 원본 문서 칸에서 눌러도 같은 설명
        c1 = page.evaluate(HELP)
        page.locator('#wfCompose .wf-line-cell.wf-line-blank').first.click()   # 빈칸 — 고른 것이 안 바뀐다
        c2 = page.evaluate(HELP)["unit"]
        page.evaluate("() => document.querySelector('#wfCompose .wf-line-cell[data-unit=heads][data-role=target] .wf-line-acts button:nth-child(2)').click()")   # ▼(헤딩 · 표 분석 — 목적 문서 카드를 제 행으로): 줄을 다시 그린다
        s8b = settle(page)
        c3 = page.evaluate(HELP)
        card(fit8, "division", "target").locator(".wf-card-head").drag_to(fit8.locator(".wf-line").nth(1).locator(".wf-line-cell[data-role=target]"))   # 끌어 놓기 — 「프로젝트 구성 반영」 을 「프로젝트 구성 추출」 의 행(목적 빈칸)으로: 끈 것이 누른 것으로 세지 않는다
        s8d = settle(page)
        c4 = page.evaluate(HELP)
        check("⑧ ⓒ 다른 도구(헤딩 · 표 분석)를 보다가 쌍 줄의 원본 문서 칸을 눌러도 「자리 연결」 · 빈칸 · ▼ · 끌어 놓기는 고른 것을 안 바꿈 · 줄을 옮겨 다시 그린 뒤에도(서버 검사가 돌아온 뒤에도) 설명과 카드 표시가 그대로",
              c0 == "heads" and c1["unit"] == "link" and sorted(c1["marked"]) == [["link", "source"], ["link", "target"]] and c2 == "link"
              and c3["unit"] == "link" and sorted(c3["marked"]) == [["link", "source"], ["link", "target"]] and s8b["groups"][0]["lines"] != s8["groups"][0]["lines"]
              and c4["unit"] == "link" and sorted(c4["marked"]) == [["link", "source"], ["link", "target"]] and s8d["groups"][1]["lines"] != s8b["groups"][1]["lines"], [c0, c1["unit"], c2, c3["marked"], c4["unit"], s8d["groups"][1]["lines"]])
        n_after_move = len(checks)
        page.locator('#wfCompose .wf-line-cell[data-unit=division] .wf-line-name > b').focus()
        page.keyboard.press("Enter")
        h3 = page.evaluate(HELP)
        page.locator('#wfCompose .wf-line-cell[data-unit=config] .wf-line-name > b').focus()
        page.keyboard.press("Space")
        h3b = page.evaluate(HELP)
        check("⑧ ⓓ 자판(카드 이름에서 Enter · Space — 초점은 그 이름에 그대로) → 「프로젝트 구성 반영」: 바꿀 것이 있으면 어느 문서가 바뀌는지(원본 문서 칸에 놓으면 원본 문서) · 줄어드는 항목의 글이 지워진다 · 지금 이 조립에서는 목적 문서 1곳 · "
              "한 행에 선 다른 도구(프로젝트 구성 추출)는 누른 카드만 표시",
              h3["unit"] == "division" and h3["focus"] == "card:division" and h3["facts"][1].startswith("문서바꿀 것이 있으면") and "원본 문서 칸에 놓으면 원본 문서가 바뀝니다" in h3["facts"][1] and "함께 지워집니다" in h3["text"]["알아 둘 것"]
              and "목적 문서 1곳에" in h3["text"]["어느 문서에 쓰나요?"] and h3["marked"] == [["division", "target"]] and ["config", "프로젝트 구성 추출"] in h3["chips"]
              and h3b["unit"] == "config" and h3b["focus"] == "card:config" and h3b["marked"] == [["config", "source"]] and "어느 칸에 놓아도" in h3b["text"]["어느 문서에 쓰나요?"], [h3, h3b["unit"], h3b["marked"], h3b["focus"]])
        page.locator("#wfCompose .wf-help-back").click()
        h4 = page.evaluate(HELP)
        page.locator('#wfCompose .wf-help-item[data-help-go=hand]').click()   # 아직 놓지 않은 도구 — 넣기 전에도 읽는다
        h4b = page.evaluate(HELP)
        page.locator("#wfCompose .wf-help-back").click()
        h4c = page.evaluate(HELP)
        page.locator('#wfCompose .wf-help-item[data-help-go=apply]').click()
        h5 = page.evaluate(HELP)
        page.locator('#wfCompose .wf-help-go[data-help-go=plan]').first.click()   # 「앞에 놓을 도구」 의 이름 → 그 도구의 설명으로
        h6 = page.evaluate(HELP)
        check("⑧ ⓔ 「이 틀의 도구 보기」 → 목록(표시 없음) → 아직 놓지 않은 「사람이 하는 일」(놓인 곳이 없습니다 · 「했음」 이 없으면 멈춤 · 초점은 도구 이름으로) → 목록으로(초점은 방금 읽던 항목) → 「내용 반영」: 자동 진행은 묻지 않고 넣는다 · "
              "바꿀 것이 있으면 목적 문서가 바뀐다 · 무료라고 적지 않는다 → 이름 칩 「표 안 연결 · 넣기 계획」 → 그 도구로",
              h4["unit"] == "" and not h4["marked"] and h4["listShown"]
              and h4b["unit"] == "hand" and not h4b["marked"] and "놓인 곳이 없습니다" in h4b["text"]["어느 문서에 쓰나요?"] and "했음" in h4b["facts"][0] and "멈춥니다" in h4b["facts"][0] and h4b["focus"] == "name"
              and h4c["unit"] == "" and h4c["focus"] == "item:hand"
              and h5["unit"] == "apply" and "묻지 않" in h5["text"]["알아 둘 것"] and h5["facts"][1] == "문서바꿀 것이 있으면 목적 문서가 바뀝니다"
              and "무료" not in " ".join(h5["facts"] + list(h5["text"].values())) and h6["unit"] == "plan" and h6["name"] == "표 안 연결 · 넣기 계획" and h6["focus"] == "name", [h4["unit"], h4b, h4c["focus"], h5, h6["unit"], h6["focus"]])
        page.wait_for_timeout(700)   # 줄을 고치면 250ms 뒤에 조립 검사가 나간다 — 설명만 열었으면 그 뒤에도 안 나간다
        s8c = page.evaluate(LINES)
        check("⑧ ⓕ 설명을 여는 것은 조립을 바꾸지 않는다 — 조립 검사 요청은 줄을 옮긴 두 번(▼ · 끌어 놓기)뿐 · 저장 요청 0 · 줄 목록 · 저장 단추 그대로",
              n_after_move == n_checks + 2 and len(checks) == n_after_move and len(bodies) == n_saves and s8c["groups"] == s8d["groups"] and s8c["save"] == save0, [n_checks, n_after_move, len(checks), len(bodies) - n_saves, s8c["save"], save0])
        page.locator("#wfCompose .wf-help-back").click()
        page.locator('#wfCompose .wf-help-item[data-help-go=tableMap]').click()   # 취합형에 없는 도구(표 대응)를 보다가
        page.evaluate("() => [...document.querySelectorAll('#wfCompose .wf-form input[type=radio]')].find((x) => x.value === 'gather').click()")   # 취합형으로 — 같은 key 도 틀마다 글이 다르다
        settle(page)
        h7 = page.evaluate(HELP)
        page.locator('#wfCompose .wf-help-item[data-help-go=plan]').click()
        h8 = page.evaluate(HELP)
        page.locator('#wfCompose li.wf-line[data-unit=link] .wf-line-name > b').first.click()
        h9 = page.evaluate(HELP)
        gather8 = {u["key"]: u["help"]["easy"] for u in api8["byShape"]["gather"]["units"]}
        check("⑧ ⓖ 취합형으로 바꿈 — 그 틀에 없는 도구(표 대응)를 보고 있었으면 목록으로 · 목록 = 취합의 도구 11개(한 문장 = 서버의 취합 글) · 「넣기 계획」 은 취합의 글(겹침 · 덮지 않음) · "
              "「자리 연결 · 기관 작성 내용 판정」 은 취합의 글(기준본 · 원본 문서마다 짝지어)",
              h7["unit"] == "" and h7["easyBy"] == gather8 and len(gather8) == 11 and h8["unit"] == "plan" and h8["name"] == "넣기 계획" and "겹침" in h8["text"]["알아 둘 것"] and "덮지 않" in h8["text"]["알아 둘 것"]
              and h9["name"] == "자리 연결 · 기관 작성 내용 판정" and "기준본" in h9["easy"] and "원본 문서마다 목적 문서와 짝지어" in h9["text"]["어느 문서에 쓰나요?"], [h7["unit"], h8["name"], h9["name"], h9["text"].get("어느 문서에 쓰나요?")])
        page.set_viewport_size({"width": 1200, "height": 900})
        page.locator("#wfCompose .wf-help-back").click()   # 설명 → 목록(돌아오면 목록은 펴진 채)
        page.wait_for_timeout(200)
        NARROW = """() => { const cols = document.querySelector('#wfCompose .wf-compose-cols'), a = cols.querySelector('.wf-help'), m = document.getElementById('wfMain'), s = getComputedStyle(a), ar = a.getBoundingClientRect(), act = document.activeElement;
          return { one: getComputedStyle(cols).gridTemplateColumns.trim().split(/\\s+/).length === 1, first: s.order === '-1', sticky: s.position === 'sticky', low: ar.height <= innerHeight * 0.38 + 2, h: Math.round(ar.height), over: m.scrollWidth > m.clientWidth + 1,
            list: a.querySelector('.wf-help-list') ? a.querySelector('.wf-help-list').checkVisibility() : null, btn: (a.querySelector('.wf-help-back') || {}).textContent || '', btnShown: !!a.querySelector('.wf-help-back') && a.querySelector('.wf-help-back').checkVisibility(),
            fold: !!a.querySelector('.wf-help-fold') && a.querySelector('.wf-help-fold').checkVisibility(), focus: act && act.dataset ? act.dataset.helpFor || '' : '',
            unit: a.dataset.unit, name: (a.querySelector('.wf-help-name') || {}).textContent || '', inView: ar.top >= 0 && ar.top < innerHeight / 2 }; }"""
        n1 = page.evaluate(NARROW)
        page.locator("#wfCompose .wf-help-back").click()   # 「목록 접기」
        n2 = page.evaluate(NARROW)
        page.locator('#wfCompose li.wf-line[data-unit=apply] .wf-line-name > b').first.click()
        n3 = page.evaluate(NARROW)
        page.screenshot(path=str(OUT / "08_help_narrow.png"), full_page=False)
        page.locator("#wfCompose .wf-help-fold").click()   # 「설명 접기」 — 띠를 한 줄로 접고 방금 보던 카드로
        n4 = page.evaluate(NARROW)
        check("⑧ ⓗ 좁은 창(1200px) — 한 칸: 설명 열이 폼 위에 붙어 선다(높이 38vh 까지 · 가로 넘침 없음) · 도구 목록은 펴고 접는다(「목록 접기」 ↔ 「이 틀의 도구 보기」) · 카드를 누르면 화면 위쪽의 그 띠에 설명이 보인다 · "
              "「설명 접기」 → 띠가 한 줄로 접히고 초점은 방금 보던 카드로",
              n1["one"] and n1["first"] and n1["sticky"] and n1["low"] and not n1["over"] and n1["list"] and n1["btnShown"] and n1["btn"] == "목록 접기"
              and n2["list"] is False and n2["btn"] == "이 틀의 도구 보기" and n3["unit"] == "apply" and n3["name"].startswith("내용 반영") and n3["inView"] and n3["low"] and not n3["over"] and n3["fold"]
              and n4["unit"] == "" and n4["list"] is False and n4["h"] < 110 and n4["focus"] == "apply", [n1, n2, n3, n4])
        page.set_viewport_size({"width": 1500, "height": 1000})
        fold_wide = page.evaluate("() => { document.querySelector('#wfCompose li.wf-line[data-unit=apply] .wf-line-name > b').click(); const f = document.querySelector('#wfCompose .wf-help-fold'); return !!f && f.checkVisibility(); }")
        page.evaluate("() => document.querySelector('#wfStage [data-wf-stage=open]').click()")   # 「단계 만들기」 폼에도 같은 열(이관형의 줄)
        page.wait_for_selector("#wfStage .wf-help")
        st = page.evaluate("""() => { const a = document.querySelector('#wfStage .wf-help'), f = document.querySelector('#wfStage .wf-compose-cols > form');
          a.querySelector('.wf-help-item[data-help-go=guide]').click();
          return { right: a.getBoundingClientRect().left >= f.getBoundingClientRect().right, unit: a.dataset.unit, name: (a.querySelector('.wf-help-name') || {}).textContent, wide: document.getElementById('wfStage').classList.contains('wf-wide'),
            other: document.querySelector('#wfCompose .wf-help').dataset.unit }; }""")
        page.evaluate("() => [...document.querySelectorAll('#wfStage .wf-form button')].find((b) => b.textContent === '취소').click()")
        closed = page.evaluate("() => ({ help: !!document.querySelector('#wfStage .wf-help'), wide: document.getElementById('wfStage').classList.contains('wf-wide') })")
        check("⑧ ⓘ 넓은 창에는 「설명 접기」 가 없다 · 「단계 만들기」 폼에도 같은 열(목록에서 「작성요령 삭제」 — 조립 폼의 설명은 그대로) · 폼을 닫으면 열과 넓은 절 표시가 없어진다",
              not fold_wide and st == {"right": True, "unit": "guide", "name": "작성요령 삭제", "wide": True, "other": "apply"} and closed == {"help": False, "wide": False}, [fold_wide, st, closed])
        # 설명 글이 없는 응답(이 기능 전의 서버) — 「아직 읽을 수 없습니다」 + 응답의 값으로 적는 칸만(실행 주체는 단정하지 않는다: 「누가」 줄 없음) · 조립은 그대로 된다
        strip = lambda units: [{k: v for k, v in u.items() if k != "help"} for u in units]  # noqa: E731

        def no_help(route):
            d = route.fetch().json()
            d["units"] = strip(d["units"])
            for box in d.get("byShape", {}).values():
                box["units"] = strip(box["units"])
            route.fulfill(json=d)
        page.route("**/api/tasks?v=2", no_help)
        page.reload()
        page.wait_for_selector("#wfCompose [data-wf-compose=open]")
        page.click("#wfCompose [data-wf-compose=open]")
        s8n = settle(page)
        page.locator('#wfCompose li.wf-line[data-unit=link] .wf-line-name > b').first.click()
        hn = page.evaluate(HELP)
        page.unroute("**/api/tasks?v=2")
        check("⑧ ⓙ 설명 글이 없는 응답 — 「이 도구의 설명을 아직 읽을 수 없습니다」 · 「누가」 는 적지 않고(단정하지 않는다) 문서 · 어느 문서에 · 관련된 앞 도구만 · 조립(표준 차례 · 저장 단추)은 그대로",
              hn["unit"] == "link" and hn["off"] and hn["easy"] == "" and hn["facts"] == ["문서문서는 그대로입니다"] and hn["secs"] == ["어느 문서에 쓰나요?", "먼저 필요한 것", "이 결과를 쓰는 도구"]
              and s8n["std"].startswith("표준 차례") and not s8n["save"]["off"], [hn["off"], hn["facts"], hn["secs"], s8n["std"]])
        real = [e for e in errors if "409" not in e and "400" not in e]
        check("콘솔 오류 없음", not real, real[:5])
        br.close()


try:
    main()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'OK' if not fails else 'FAIL'} — 실패 {len(fails)}" + (f": {json.dumps(fails, ensure_ascii=False)}" if fails else ""), flush=True)
sys.exit(1 if fails else 0)

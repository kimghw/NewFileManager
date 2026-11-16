"""템플릿 트리(「템플릿」 탭 = 「템플릿 관계」 열 — 같은 UI) · 개요 레벨 그림 · 「하위로」 늘 보임 · 다른 서식 보기 · 대표 맞추기 · 문서 표시의 서식 라벨 · 템플릿 서식 정리 에이전트
(spec_헤딩_추출 ② §7 · spec_hwpx_웹편집 ② §8-2·§8-4 — app.js tplTreeDraw · outline_match.js · tpl_agent.js) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 진짜 — 에이전트의 LLM 답(POST …/plan)과 「LLM 켜짐」(GET /api/outline/agent 의 available)만 흉내.

연구개발계획서 양식을 올리고 1·2단계(LLM 없이)를 끝점으로 돌린 뒤 작업을 열어:
- 헤딩 추출 「템플릿」 탭이 트리(옛 카드 목록 없음) · 템플릿마다 개요 레벨 그림 · 원문 보기 · 「템플릿 관계」 열과 줄이 같다.
- 「하위로」 는 넣을 자리가 없는 템플릿에도 보이고(흐리게) 누르면 까닭 · 자리가 있는 T9 는 탭에서 넣어도 2열이 열리지 않고 탭의 트리에 「T8T9」 · 「떼기」.
- 「다른 서식 보기(2가지)」(T3) → 개요 레벨 그림 아래에 레벨마다 대표와 다른 서식(견본 글 · 「앞 공백: 지금 4칸 → 대표 3칸」) · 「문서에서 보기」 · 서식 줄의 「맞추기」 → 그 서식만 · 실행 취소 ·
  다 맞춘 뒤에도 단추는 남고(흐린 점선) 묶음은 「대표와 다른 서식 없음」 · 실행 취소로 돌아오면 다시 2가지 · 「접기」(2026-11-16 — outline_odd.js).
- 「대표 맞추기」(T3 — 전 이름 「템플릿 맞추기」) → 두 레벨이 한 번에 · 실행 취소 한 번.
- 「서식 라벨 보기」 → 템플릿 표 아래(또는 같은 줄 뒤)에 「S…」 · 누르면 그 서식만 또렷이(이름 줄 설명의 「목록」 = 그 라벨의 문단 목록) · 끄면 사라짐.
- 별 아이콘 → 2열 「템플릿 서식 정리」: 모델 「Opus 5.5」 · 스킬 고치기 → 「저장하고 정리 계획 받기」 가 먼저 저장 · 계획(대표 바꿈 · 갈래 줄마다 고르기 「맞추기 / 그대로 / T3L2a 로」) → 적용 → 실행 취소 한 번 ·
  계획을 다시 받아 갈래 하나를 「T3L2a 로」 → 「적용 — 5줄 · 떼기 1줄」 → 서식 종속 템플릿 「T3L2a」(spec_hwpx_웹편집 ② §8-5) · 실행 취소 한 번 ·
  「보낼 글」(진짜 끝점 — 저장된 스킬 글) · 「기본으로 되돌리기」 두 번 · 「새 스킬」 저장·지우기 · 「‹ 템플릿 관계」.
- 패널 320px 에서 탭의 트리 가로 넘침 없음 · 콘솔 오류 없음.

    python -X utf8 tools/smoke_tpl_agent_ui.py <출력 폴더> [--port 18437]
"""
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
ap.add_argument("--port", type=int, default=18437)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "PYTHONUTF8": "1"}
env.pop("NFM_TPL_AGENT_MODEL", None)
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


def slot(doc, tid, lv):
    return requests.get(f"{base}/api/docs/{doc}/outline/formats", timeout=60).json()["slots"][str(tid)][str(lv)]


ROWS = """(sel) => [...document.querySelector(sel).querySelectorAll('li.trel-node')].map((li) => li.dataset.tpl + ':' + [...li.querySelector('.trel-row').children].filter((e) => !e.classList.contains('htog')).map((e) => e.textContent.trim()).join('|'))"""
TAB, COL = "#headsTemplatesResult .tpl-tree", "#headsDlgBody .tpl-tree"
NODE = lambda root, tid: f'{root} li.trel-node[data-tpl="{tid}"]'  # noqa: E731
WAIT_IDLE = "() => !state.busy"


def main():
    wait_server()
    r = requests.post(base + "/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}, timeout=120)
    assert r.status_code == 200, r.text
    doc = r.json()["docId"]
    run_stage(doc, 1)
    run_stage(doc, 2)
    seen = {"plan": 0, "dry": 0}
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1700, "height": 1000}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())

        def info(route):  # LLM 이 켜진 서버인 척(임시 서버는 LLM 끔) — 나머지 값·스킬 목록은 진짜
            j = route.fetch().json()
            route.fulfill(json={**j, "available": True, "backend": "api"})

        def plan(route):  # 에이전트의 답만 흉내 — dry(보낼 글)는 진짜 끝점
            body = json.loads(route.request.post_data or "{}")
            if body.get("dry"):
                seen["dry"] += 1
                return route.continue_()
            seen["plan"] += 1
            seen["body"] = body
            v = slot(doc, 3, 2)
            g = {x["key"]: x for x in v["groups"]}
            sk = requests.get(f"{base}/api/outline/agent/skills/{body['skill']}", timeout=30).json()
            mk = lambda k, i: {"group": f"g{i}", "para": k, "count": g[k]["count"], "sample": f"줄 {k}", "diff": [["lead", "앞 공백", "4칸", "3칸"]]}  # noqa: E731
            lv2 = {"level": 2, "letter": "-", "lines": v["total"], "single": False, "was": "g1", "rep": {"group": "g2", "para": "p5209", "count": 1, "sample": "줄 p5209", "changed": True},
                   "match": [mk("p6502", 1)], "keep": [{**mk("p5765", 3), "why": "레터 뒤 공백이 없어 따로 둠", "auto": False}], "split": [], "taken": [], "change": g["p6502"]["count"], "moved": 0,
                   "why": "앞 공백 4칸이 위 레벨과 어울림"}
            lv1 = {"level": 1, "letter": "o", "lines": 7, "single": True, "was": "g1", "rep": {"group": "g1", "para": "x", "count": 7, "sample": "", "changed": False}, "match": [], "keep": [],
                   "split": [], "taken": [], "change": 0, "moved": 0, "why": ""}
            route.fulfill(json={"tpl": "3", "no": "3", "rev": requests.get(f"{base}/api/docs/{doc}/outline/formats", timeout=60).json()["rev"],
                                "skill": {k: sk[k] for k in ("key", "name", "version", "sha1")}, "request": body.get("request") or "", "model": "claude-opus-5-5", "effort": "medium", "backend": "api",
                                "ms": 15300, "costUsd": 0.0421, "plan": {"summary": "L2 의 앞 공백을 4칸으로 맞춥니다.", "levels": [lv1, lv2], "change": lv2["change"], "moved": 0,
                                                                         "notes": ["L7 은 이 템플릿에 줄이 없는 레벨 — 버림"]}})
        page.route(re.compile(r"/api/outline/agent$"), info)
        page.route(re.compile(r"/outline/agent/[^/]+/plan$"), plan)
        page.goto(f"{base}/#w={doc}")
        page.wait_for_selector("#doc .para[data-id=p970]", timeout=120000)
        page.wait_for_function("() => typeof heads !== 'undefined' && heads.outline", timeout=60000)

        # ---- 「템플릿」 탭 = 트리 · 개요 레벨 그림
        page.click("#tabHeads")
        page.wait_for_function("() => heads.graph && document.querySelector('#headsTemplatesResult .tpl-tree li.trel-node')", timeout=120000)
        page.click("#headsTabTemplates")
        page.wait_for_function("() => document.querySelector('#headsTemplatesResult .tpl-pic .sp-pic')", timeout=60000)
        st = page.evaluate("""() => { const R = document.querySelector('#headsTemplatesResult'); const pics = [...R.querySelectorAll('.tpl-tree > ul > li.trel-node > .tpl-pic')];
          return { nodes: R.querySelectorAll('li.trel-node').length, cards: R.querySelectorAll('.hlist > li .hl-top, details.more').length, pics: pics.length, drawn: pics.filter((p) => p.querySelector('.sp-pic .sp-lv')).length,
            t1: [...(R.querySelector('li.trel-node[data-tpl="1"] > .tpl-pic') || document).querySelectorAll('.sp-lv')].map((l) => l.textContent.trim()), faded: R.querySelectorAll('.sp-over').length,
            src: R.querySelectorAll('.template-source').length, agent: R.querySelectorAll('.tpl-agent').length, tools: [...R.querySelectorAll('.tpl-tree-tools button, .tpl-tree-links button')].map((x) => x.textContent), head: R.querySelector('.htree-head b').textContent }; }""")
        check("「템플릿」 탭이 트리 — 템플릿 줄마다 개요 레벨 그림(레벨을 다 보임) · 원문 보기 · 별 아이콘 · 옛 카드 목록 없음",
              st["nodes"] >= 10 and st["cards"] == 0 and st["pics"] >= 10 and st["drawn"] == st["pics"] and len(st["t1"]) >= 3 and st["faded"] == 0 and st["src"] >= 10 and st["agent"] >= 10
              and st["tools"][:4] == ["문서 표시", "서식 라벨", "모두 펼치기", "모두 접기"] and "템플릿 관계" in st["tools"] and re.fullmatch(r"템플릿 \d+개", st["head"]), st)
        check("그림의 레벨 줄 = 「L1 레터 견본 글입니다」", all("견본 글입니다" in t and t.startswith(f"L{i + 1}") for i, t in enumerate(st["t1"])), st["t1"])
        page.screenshot(path=str(OUT / "01_tab_tree.png"))
        page.locator("#headsTemplatesResult .template-source").first.click()
        check("「원문 보기」 → 문서의 그 줄로", page.locator("#doc .para.flash").count() > 0)

        # ---- 「템플릿 관계」 열과 같은 줄
        page.evaluate("headsTplView()")
        page.wait_for_function("() => document.querySelector('#headsDlgBody .tpl-tree .tpl-pic .sp-pic')", timeout=30000)
        a, c = page.evaluate(ROWS, TAB), page.evaluate(ROWS, COL)
        check("탭과 열의 템플릿 줄이 같다(번호 · 사슬 · 수 · 단추)", a == c and len(a) >= 10, [x for x in zip(a, c) if x[0] != x[1]][:3])
        check("열의 도구 줄에도 같은 단추(문서 표시 · 서식 라벨 · 모두 펼치기 · 모두 접기)", page.evaluate("[...document.querySelectorAll('#headsDlgTools button')].map((x) => x.textContent)") == ["문서 표시", "서식 라벨", "모두 펼치기", "모두 접기"])
        page.screenshot(path=str(OUT / "02_col_tree.png"))
        page.click("#headsDlgClose")

        # ---- 「하위로」 — 넣을 자리가 없어도 보인다 · 자리가 있으면 탭에서 넣는다(2열을 열지 않는다)
        sub = page.evaluate("""() => [...document.querySelectorAll('#headsTemplatesResult .tpl-tree > ul > li.trel-node > .trel-row > .olm-sub')].map((x) => [x.closest('li').dataset.tpl, x.classList.contains('none')])""")
        none = [t for t, n in sub if n]
        check("뿌리 템플릿 줄마다 「하위로」 — 넣을 자리가 없는 것은 흐리게", len(sub) >= 5 and "1" in none, sub)
        page.locator(f'{NODE(TAB, 1)} > .trel-row > .olm-sub').click()
        note = page.locator(f'{NODE(TAB, 1)} > .olm-merge .olm-note').inner_text()
        check("넣을 자리가 없는 「하위로」 를 누르면 까닭 한 줄", "넣을 자리가 없습니다" in note and "T1" in note and "본문 최상위" in note, note)
        page.locator("#headsTemplatesResult .tpl-tree-tools button", has_text="모두 펼치기").click()  # T8·T9·T3 은 다른 템플릿 레벨 아래 가지 — 펼쳐야 줄이 생긴다
        page.wait_for_selector(f'{NODE(TAB, 9)} > .trel-row > .olm-sub')
        page.locator(f'{NODE(TAB, 9)} > .trel-row > .olm-sub').first.click()
        page.locator(f'{NODE(TAB, 9)} > .olm-merge button', has_text="넣기").first.click()
        page.wait_for_selector(f'{TAB} li.trel-node[data-tpl="8+9"]', timeout=30000)
        page.wait_for_function(WAIT_IDLE)
        m = page.evaluate("""() => { const li = document.querySelector('#headsTemplatesResult li.trel-node[data-tpl="8+9"]'); return { col: document.getElementById('headsDlg').hidden,
          row: li.querySelector('.trel-row').textContent, pic: !!li.querySelector('.tpl-pic'), head: document.querySelector('#headsTemplatesResult .htree-head b').textContent, marks: [...document.querySelectorAll('.tpl-mark')].filter((x) => x.textContent.startsWith('T8T9')).length }; }""")
        check("탭에서 넣으면 탭의 트리에 종속 템플릿 「T8T9」(종속 표지 · 떼기 · 그림) — 2열은 안 열림 · 문서 표 「T8T9 L…」",
              m["col"] and "T8T9" in m["row"] and "종속 — T8 L3 아래 T9" in m["row"] and "떼기" in m["row"] and m["pic"] and m["marks"] > 0, m)
        page.screenshot(path=str(OUT / "03_sub_template.png"))
        page.locator(f'{TAB} li.trel-node[data-tpl="8+9"] > .trel-row button', has_text="떼기").first.click()  # T8 이 두 자리에 매달려 있어 같은 줄이 둘
        page.wait_for_function("() => !document.querySelector('#headsTemplatesResult li.trel-node[data-tpl=\"8+9\"]')", timeout=30000)
        page.wait_for_function(WAIT_IDLE)
        check("「떼기」 → 종속 템플릿이 없어짐", page.evaluate("!Object.keys(heads.outline.templates).includes('8+9')"))

        # ---- 다른 서식 보기 — 템플릿 줄의 단추 → 그림 아래에 레벨마다 대표와 다른 서식(견본 글 · 지금 값 → 대표 값) · 서식마다 맞추기 · 문서에서 보기
        # (2026-11-16 사용자 「템플릿 내에서 다른 서식을 템플릿 서식으로 조정하기 기능 넣어주고, 다른 서식 보기 버튼도 넣어줘」 — outline_odd.js). T3 L2 「-」 = 대표 p6502 ×5 · p5209 ×1 · p5765 ×1
        n3 = NODE(TAB, 3)
        ODD = """() => { const li = document.querySelector('#headsTemplatesResult li.trel-node[data-tpl="3"]'), box = li.querySelector(':scope > .olm-odd'), btn = li.querySelector(':scope > .trel-row .olm-odd-btn');
          return { btn: btn ? btn.textContent : '', pressed: btn ? btn.getAttribute('aria-expanded') : '', box: !!box, hidden: !box || box.hidden, underPic: !!(box && box.previousElementSibling && box.previousElementSibling.classList.contains('tpl-pic')),
            head: box && !box.hidden ? box.querySelector('.olo-head').textContent : '', dialog: !!document.querySelector('dialog[open]'), none: !!(btn && btn.classList.contains('none')),
            same: box ? [...box.querySelectorAll('.olo-same')].map((l) => l.textContent) : [],
            levels: box ? [...box.querySelectorAll('.olo-lv')].map((l) => ({ L: +l.dataset.level, head: l.querySelector('.olo-lh').textContent, btns: [...l.querySelectorAll('.olo-lh button')].map((b) => b.textContent),
              rep: [...l.querySelectorAll('.olo-row.rep')].map((r) => [r.querySelector('.olo-tag').textContent, r.querySelector('.olm-n').textContent, !!r.querySelector('.olp-samp'), !!r.querySelector('.olo-go')]),
              rows: [...l.querySelectorAll('.olo-row:not(.rep)')].map((r) => ({ tag: r.querySelector('.olo-tag').textContent, n: r.querySelector('.olm-n').textContent, paras: r._paras, samp: !!r.querySelector('.olp-samp'),
                diff: (r.querySelector('.olm-diff') || {}).textContent || '', go: (r.querySelector('.olo-go') || {}).textContent || '' })) })) : [] }; }"""
        page.wait_for_function("() => document.querySelector('#headsTemplatesResult li.trel-node[data-tpl=\"3\"] > .trel-row .olm-odd-btn')", timeout=30000)
        od0 = page.evaluate(ODD)
        check("템플릿 줄에 「다른 서식 보기(2가지)」 — 「대표 맞추기」 바로 뒤 · 누르기 전에는 펼친 것 없음",
              od0["btn"] == "다른 서식 보기(2가지)" and od0["pressed"] == "false" and od0["hidden"]
              and page.evaluate("""() => { const r = document.querySelector('#headsTemplatesResult li.trel-node[data-tpl="3"] > .trel-row'), a = r.querySelector('.olm-tm-btn'), b = r.querySelector('.olm-odd-btn');
                return !!(a && b && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)); }"""), od0)
        page.locator(f'{n3} > .trel-row .olm-odd-btn').first.click()
        page.wait_for_selector(f'{n3} > .olm-odd:not([hidden]) .olo-row', timeout=10000)
        od = page.evaluate(ODD)
        l2 = next((x for x in od["levels"] if x["L"] == 2), {"rows": [], "rep": [], "head": "", "btns": []})
        r5209 = next((r for r in l2["rows"] if "p5209" in (r["paras"] or [])), {})
        check("누르면 개요 레벨 그림 바로 아래에 펼쳐짐(팝업 아님) — 머리 「대표와 다른 서식 · 레벨 1개 · 2가지 · 2줄」 · L2 「-」 머리에 「문서에서 보기」·「이 레벨 맞추기(2줄)」",
              od["pressed"] == "true" and not od["hidden"] and od["underPic"] and not od["dialog"] and "대표와 다른 서식" in od["head"] and "레벨 1개 · 2가지 · 2줄" in od["head"]
              and [x["L"] for x in od["levels"]] == [2] and "다른 서식 2가지 · 2줄" in l2["head"] and l2["btns"] == ["문서에서 보기", "이 레벨 맞추기(2줄)"], od)
        check("서식이 한 가지인 레벨은 한 줄 「L1 「o」 서식 1가지 — 모두 같음 · n줄」", len(od["same"]) == 1 and od["same"][0].startswith("L1") and "서식 1가지 — 모두 같음" in od["same"][0], od["same"])
        check("레벨마다 대표 줄(「대표 ×5」 견본 · 맞추기 없음) + 다른 서식 줄(「다름 ×1」 견본 · 「맞추기」 · 「앞 공백: 지금 4칸 → 대표 3칸」 — 값마다 이름표)",
              l2["rep"] == [["대표", "×5", True, False]] and len(l2["rows"]) == 2 and all(r["tag"] == "다름" and r["n"] == "×1" and r["samp"] and r["go"] == "맞추기" for r in l2["rows"])
              and "앞 공백: 지금 4칸 → 대표 3칸" in r5209.get("diff", ""), l2)
        page.screenshot(path=str(OUT / "03d_odd.png"))
        page.locator(f'{n3} > .olm-odd .olo-see').first.click()
        page.wait_for_function("() => FMF.kind === 'tpl' && FMF.tpl === '3' && FMF.level === 2 && document.getElementById('doc').classList.contains('fmt-focus')", timeout=20000)
        page.wait_for_function("() => document.querySelectorAll('.sheet > .fm-tag').length > 0", timeout=20000)
        check("「문서에서 보기」 → 문서에서 T3 L2 의 줄만 또렷이 · 대표와 다른 줄에 「≠ …」 표", page.evaluate("() => !document.getElementById('fmtKey').hidden && /T3 L2/.test(document.getElementById('fmtKey').textContent)"))
        page.click("#fmtKey .fm-key-off")
        page.wait_for_function("() => !document.getElementById('doc').classList.contains('fmt-focus')", timeout=10000)
        undo0 = page.evaluate("state.undo")
        page.evaluate("""() => { const rows = [...document.querySelectorAll('#headsTemplatesResult li.trel-node[data-tpl="3"] > .olm-odd .olo-row:not(.rep)')]; rows.find((r) => (r._paras || []).includes('p5209')).querySelector('.olo-go').click(); }""")
        page.wait_for_function(f"() => state.undo === {undo0 + 1} && !state.busy", timeout=60000)
        page.wait_for_function("() => (document.querySelector('#headsTemplatesResult li.trel-node[data-tpl=\"3\"] > .trel-row .olm-odd-btn') || {}).textContent === '다른 서식 보기(1가지)'", timeout=30000)
        od = page.evaluate(ODD)
        check("다른 서식 줄의 「맞추기」 → 그 서식의 줄만 대표 모양으로(p5209 접두 「   - 」) · 단추 「다른 서식 보기(1가지)」 · 펼친 묶음에 남은 한 줄 · 실행 취소 한 칸",
              slot(doc, 3, 2)["others"] == 1 and page.evaluate("() => document.querySelector('#doc .para[data-id=p5209]').textContent.startsWith('   - ') && !document.querySelector('#doc .para[data-id=p5209]').textContent.startsWith('    ')")
              and not od["hidden"] and len(od["levels"]) == 1 and len(od["levels"][0]["rows"]) == 1 and "p5765" in od["levels"][0]["rows"][0]["paras"], od)
        page.click("#undoBtn")
        page.wait_for_function(f"() => state.undo === {undo0} && !state.busy", timeout=60000)
        page.wait_for_function("() => (document.querySelector('#headsTemplatesResult li.trel-node[data-tpl=\"3\"] > .trel-row .olm-odd-btn') || {}).textContent === '다른 서식 보기(2가지)'", timeout=30000)
        check("실행 취소 → 다른 서식 2가지로(펼친 채)", slot(doc, 3, 2)["others"] == 2 and not page.evaluate(ODD)["hidden"])

        # ---- 대표 맞추기(전 이름 「템플릿 맞추기」) — 여러 레벨을 한 번에 · 실행 취소 1
        page.wait_for_function("() => document.querySelector('#headsTemplatesResult li.trel-node[data-tpl=\"3\"] > .trel-row .olm-tm-btn')", timeout=30000)
        txt = page.locator(f'{NODE(TAB, 3)} > .trel-row .olm-tm-btn').first.inner_text()
        undo0 = page.evaluate("state.undo")
        before = slot(doc, 3, 2)["others"]
        page.locator(f'{NODE(TAB, 3)} > .trel-row .olm-tm-btn').first.click()
        page.wait_for_function(f"() => state.undo === {undo0 + 1} && !state.busy", timeout=60000)
        after = slot(doc, 3, 2)["others"]
        check("「대표 맞추기(n줄)」(T3) → 레벨마다 대표 모양으로 · 실행 취소 한 칸", re.fullmatch(r"대표 맞추기\(\d+줄\)", txt) and before == 2 and after == 0, [txt, before, after])
        page.wait_for_function("() => !document.querySelector('#headsTemplatesResult li.trel-node[data-tpl=\"3\"] > .trel-row .olm-tm-btn')", timeout=30000)
        check("맞춘 뒤에는 「대표 맞추기」 가 사라짐(맞출 줄 없음)", True)
        page.wait_for_function("() => { const b = document.querySelector('#headsTemplatesResult li.trel-node[data-tpl=\"3\"] > .trel-row .olm-odd-btn'); return b && b.textContent === '다른 서식 보기' && b.classList.contains('none'); }", timeout=30000)
        od = page.evaluate(ODD)
        check("맞춘 뒤에도 「다른 서식 보기」 는 남는다(흐린 점선 · 수 없음) — 펼친 묶음은 「대표와 다른 서식 없음」 + 레벨마다 「서식 1가지 — 모두 같음」",
              od["none"] and not od["hidden"] and "대표와 다른 서식 없음" in od["head"] and not od["levels"] and len(od["same"]) == 2 and all("서식 1가지 — 모두 같음" in s for s in od["same"]), od)
        page.click("#undoBtn")
        page.wait_for_function(f"() => state.undo === {undo0} && !state.busy", timeout=60000)
        check("실행 취소 한 번으로 되돌아감", slot(doc, 3, 2)["others"] == 2)
        page.wait_for_function("() => { const b = document.querySelector('#headsTemplatesResult li.trel-node[data-tpl=\"3\"] > .olm-odd'); return b && !b.hidden && b.querySelectorAll('.olo-row:not(.rep)').length === 2; }", timeout=30000)
        check("실행 취소 → 펼쳐 둔 「다른 서식」 묶음이 다시 보임(2가지)", page.evaluate(ODD)["btn"] == "다른 서식 보기(2가지)")
        page.locator(f'{n3} > .olm-odd .olo-close').first.click()
        check("「접기」 → 묶음이 접히고 단추 눌림이 풀림", page.evaluate(ODD)["hidden"] and page.evaluate(ODD)["pressed"] == "false")

        # ---- 문서 표시의 서식 라벨
        n0 = page.evaluate("document.querySelectorAll('.tpl-mark.fmt, .tpl-mark .tm-fmt').length")
        page.locator("#headsTemplatesResult .tpl-tg-fmt").click()
        page.wait_for_function("() => document.querySelectorAll('.tpl-mark.fmt').length > 20", timeout=30000)
        fm = page.evaluate("""() => { const under = [...document.querySelectorAll('.tpl-mark.fmt')]; const bad = under.filter((f) => { const sh = f.closest('.sheet'), top = parseFloat(f.style.top);
            return ![...sh.querySelectorAll(':scope > .tpl-mark:not(.fmt)')].some((m) => Math.abs(parseFloat(m.style.top) + 15 - top) <= 1); }).length;
          return { under: under.length, inline: document.querySelectorAll('.tpl-mark .tm-fmt').length, bad, text: under.slice(0, 30).every((f) => /^(S\\d+|≠)/.test(f.textContent)), pressed: document.querySelector('#headsTemplatesResult .tpl-tg-fmt').getAttribute('aria-pressed') }; }""")
        check("「서식 라벨 보기」 → 템플릿 표 바로 아래에 「S…」 줄(자리가 없으면 같은 줄 뒤)", n0 == 0 and fm["under"] > 20 and fm["bad"] == 0 and fm["text"] and fm["pressed"] == "true", fm)
        page.evaluate("() => { const f = document.querySelector('.tpl-mark.fmt'); f.scrollIntoView({ block: 'center' }); }")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "04_fmt_marks.png"))
        lab = page.evaluate("() => { const f = document.querySelector('.tpl-mark.fmt'); const t = f.textContent.split(' ')[0]; f.click(); return t; }")
        # 2026-11-15: 누르면 그 서식의 문단만 또렷이(fmt_focus.js — 자세한 검사는 smoke_fmt_focus_ui.py) · 전의 문단 목록은 이름 줄 설명의 「목록」 단추
        page.wait_for_function("() => document.getElementById('doc').classList.contains('fmt-focus') && document.querySelector('#doc .para.fmt-hit')", timeout=30000)
        page.click("#fmtKey .fm-key-list")
        page.wait_for_function("() => !document.getElementById('headsDlg').hidden && document.querySelector('#headsDlgBody tr.go')", timeout=30000)
        check("서식 라벨을 누르면 그 서식만 또렷이 · 이름 줄 설명의 「목록」 → 그 라벨의 문단 목록(2열)", lab in page.locator("#headsDlgNote").inner_text() + page.locator("#headsDlgTitle").inner_text() + page.locator("#headsDlgFoot").inner_text() + page.locator("#headsDlgBody").inner_text()[:400], lab)
        page.click("#headsDlgClose")
        page.click("#fmtKey .fm-key-off")
        page.wait_for_function("() => !document.getElementById('doc').classList.contains('fmt-focus') && document.getElementById('fmtKey').hidden", timeout=10000)
        page.locator("#headsTemplatesResult .tpl-tg-fmt").click()
        page.wait_for_function("() => document.querySelectorAll('.tpl-mark.fmt, .tpl-mark .tm-fmt').length === 0", timeout=20000)
        check("끄면 서식 라벨 줄이 사라지고 템플릿 표는 남음", page.evaluate("document.querySelectorAll('.tpl-mark').length") > 20)

        # ---- 서식 정리 에이전트
        page.locator(f'{NODE(TAB, 3)} > .trel-row > .tpl-agent').first.click()
        page.wait_for_selector("#headsDlg[data-kind=tplAgent] .tpa .tpa-text", timeout=30000)
        page.wait_for_function("() => { const g = document.querySelector('#headsDlgBody .tpa-go'); return g && !g.disabled; }", timeout=30000)
        ag = page.evaluate("""() => ({ title: document.getElementById('headsDlgTitle').textContent, note: document.getElementById('headsDlgNote').textContent, model: document.querySelector('.tpa-model').textContent,
          go: document.querySelector('.tpa-go').textContent, skills: [...document.querySelectorAll('.tpa-skill option')].map((o) => o.textContent), text: document.querySelector('.tpa-text').value,
          name: document.querySelector('.tpa-name').value, saved: document.querySelector('.tpa-saved').textContent, tpl: document.querySelector('.tpa-tpl').value, pic: !!document.querySelector('.tpa-target .tpl-pic .sp-pic'),
          levels: document.querySelector('.tpa-levels').innerText })""")
        check("별 아이콘 → 2열 「템플릿 서식 정리」(대상 T3 · 그림 · 레벨마다 갈래 수 · 모델 Opus 5.5 · 저장해 둔 스킬 글)",
              ag["title"] == "템플릿 서식 정리" and ag["note"].startswith("T3") and ag["model"].startswith("Opus 5.5") and ag["go"] == "정리 계획 받기" and ag["tpl"] == "3" and ag["pic"]
              and any("템플릿 서식 정리 (기본)" == s for s in ag["skills"]) and len(ag["skills"]) >= 2 and "## 대표 고르기" in ag["text"] and ag["name"] == "템플릿 서식 정리"
              and ag["saved"] == "기본 스킬(고친 적 없음)" and "서식 3가지" in ag["levels"], ag)
        page.screenshot(path=str(OUT / "05_agent.png"))
        page.locator("#headsDlgTools button", has_text="보낼 글").click()
        page.wait_for_selector("#headsDlgBody .tpa-prompt textarea", timeout=30000)
        pr = page.locator("#headsDlgBody .tpa-prompt textarea").input_value()
        check("「보낼 글」 — 계약 · 저장된 스킬 글 · 자료(LLM 을 안 부름)", seen["dry"] == 1 and seen["plan"] == 0 and "## 스킬 — 템플릿 서식 정리" in pr and "## 대표 고르기" in pr and '"id": "g2"' in pr, pr[:300])
        page.locator("#headsDlgTools button", has_text="보낼 글").click()
        # 스킬을 고치면 먼저 저장하고 부른다
        page.fill("#headsDlgBody .tpa-text", "앞 공백은 4칸으로 맞춘다.\n")
        d = page.evaluate("[document.querySelector('.tpa-go').textContent, document.querySelector('.tpa-saved').textContent, document.querySelector('.tpa-save').disabled]")
        check("스킬 글을 고치면 「고침 — 저장 안 됨」 · 단추가 「저장하고 정리 계획 받기」", d == ["저장하고 정리 계획 받기", "고침 — 저장 안 됨", False], d)
        page.fill("#headsDlgBody .tpa-req", "L2 만")
        page.locator("#headsDlgBody .tpa-go").click()
        page.wait_for_selector("#headsDlgBody .tpa-plan .tpa-apply", timeout=60000)
        sk = requests.get(f"{base}/api/outline/agent/skills/tidy", timeout=30).json()
        pl = page.evaluate("""() => ({ apply: document.querySelector('.tpa-apply').textContent, count: document.querySelector('.tpa-count').textContent, lv: document.querySelectorAll('.tpa-lv').length,
          rep: document.querySelector('.tpa-rep .hb').textContent,
          boxes: [...document.querySelectorAll('.tpa-g')].map((g) => { const s = g.querySelector('.tpa-pick'); return [g.classList.contains('match') ? 'match' : g.classList.contains('split') ? 'split' : 'keep', s.value, s.selectedOptions[0].textContent, [...s.options].map((o) => o.textContent).join('|')]; }),
          why: [...document.querySelectorAll('.tpa-why')].map((w) => w.textContent), notes: (document.querySelector('.tpa-plan .ag-dropped summary') || {}).textContent, meta: document.querySelector('.tpa-plan .ag-note').textContent,
          saved: document.querySelector('.tpa-saved').textContent, go: document.querySelector('.tpa-go').textContent })""")
        check("「저장하고 정리 계획 받기」 — 스킬을 먼저 저장(판 1)하고 그 스킬·요청으로 부름", sk["custom"] and sk["version"] == 1 and sk["text"] == "앞 공백은 4칸으로 맞춘다.\n" and seen["plan"] == 1
              and seen["body"] == {"skill": "tidy", "request": "L2 만"} and pl["saved"].startswith("저장됨 · 판 1"), [sk, seen.get("body"), pl["saved"]])
        opts = "맞추기|그대로|T3L2a 로"
        check("계획 — 레벨마다 한 상자 · 「대표 바꿈」 · 갈래 줄마다 고르기(맞추기 / 그대로 / T3L2a 로 — 에이전트가 고른 것이 처음 값) · 까닭 · 걸러낸 답 · 모델·시간·비용·스킬 판",
              pl["lv"] == 2 and pl["rep"] == "대표 바꿈" and pl["boxes"] == [["match", "match", "맞추기", opts], ["keep", "keep", "그대로", opts]] and pl["apply"] == "적용 — 5줄" and "고른 갈래 1개" in pl["count"]
              and any("레터 뒤 공백이 없어" in w for w in pl["why"]) and pl["notes"] == "걸러낸 답 1" and "Opus 5.5" in pl["meta"] and "15.3초" in pl["meta"] and "$0.0421" in pl["meta"] and "판 1" in pl["meta"]
              and pl["go"] == "정리 계획 다시 받기", pl)
        page.evaluate("document.querySelector('#headsDlgBody').scrollTop = document.querySelector('.tpa-plan').offsetTop - 8")
        page.screenshot(path=str(OUT / "06_plan.png"))
        keep = '#headsDlgBody .tpa-pick[data-key="2|g3"]'
        page.select_option(keep, "match")
        check("「그대로」 갈래를 「맞추기」 로 바꾸면 적용 줄 수가 는다", page.locator("#headsDlgBody .tpa-apply").inner_text() == "적용 — 6줄")
        page.select_option(keep, "s:a")
        sp = page.evaluate("""(k) => { const s = document.querySelector(k), g = s.closest('.tpa-g'); return { apply: document.querySelector('.tpa-apply').textContent, count: document.querySelector('.tpa-count').textContent,
          cls: g.className, chip: (g.querySelector('.tpa-vt') || {}).textContent, focus: document.activeElement === s, why: (g.querySelector('.tpa-why') || {}).textContent }; }""", keep)
        check("「T3L2a 로」 로 바꾸면 그 갈래는 다른 템플릿으로 — 「적용 — 5줄 · 떼기 1줄」 · 줄에 「T3L2a 의 대표」 · 고르기에 초점이 남음",
              sp["apply"] == "적용 — 5줄 · 떼기 1줄" and "고른 갈래 2개" in sp["count"] and "split" in sp["cls"] and sp["chip"] == "T3L2a 의 대표" and sp["focus"] and "레터 뒤 공백이 없어" in (sp["why"] or ""), sp)
        page.screenshot(path=str(OUT / "06b_plan_split.png"))
        page.select_option(keep, "keep")
        check("「그대로」 로 되돌리면 처음 줄 수", page.locator("#headsDlgBody .tpa-apply").inner_text() == "적용 — 5줄")
        undo0 = page.evaluate("state.undo")
        page.locator("#headsDlgBody .tpa-apply").click()
        page.wait_for_function(f"() => state.undo === {undo0 + 1} && !state.busy", timeout=60000)
        page.wait_for_function("() => (document.querySelector('#headsDlgBody .tpa-apply') || {}).textContent === '적용함 — 5줄'", timeout=30000)
        page.wait_for_function("() => /서식 2가지/.test((document.querySelector('#headsDlgBody .tpa-levels') || {}).innerText || '')", timeout=30000)  # 대상 칸도 새 갈래로
        v = slot(doc, 3, 2)
        ap2 = page.evaluate("""() => ({ count: document.querySelector('.tpa-count').textContent, dis: [...document.querySelectorAll('.tpa-g select')].every((i) => i.disabled), applyDis: document.querySelector('.tpa-apply').disabled,
          text: document.querySelector('#doc .para[data-id=p6502]').textContent.slice(0, 6), levels: document.querySelector('.tpa-levels').innerText })""")
        check("「적용」 — 대표를 p5209 로 바꾸고 고른 갈래 5줄만 맞춤(p5765 는 그대로) · 실행 취소 한 칸 · 계획은 「적용함」 으로 잠김",
              v["rep"] == "p5209" and v["groups"][0]["count"] == 6 and v["others"] == 1 and ap2["text"].startswith("    - ") and ap2["dis"] and ap2["applyDis"] and "대표 바꿈 1" in ap2["count"]
              and "서식 2가지" in ap2["levels"], [v["rep"], v["others"], ap2])
        page.screenshot(path=str(OUT / "07_applied.png"))
        page.click("#undoBtn")
        page.wait_for_function(f"() => state.undo === {undo0} && !state.busy", timeout=60000)
        v = slot(doc, 3, 2)
        check("실행 취소 한 번 → 대표·서식이 처음대로", v["rep"] == "p6502" and v["others"] == 2, [v["rep"], v["others"]])
        # 다른 템플릿으로 떼기까지 한 번에(② §8-5) — 계획을 다시 받아 p5765 갈래를 「T3L2a 로」: 대표 바꿈 + 5줄 맞춤 + 떼기가 실행 취소 한 칸
        page.locator("#headsDlgBody .tpa-go").click()
        page.wait_for_function("() => { const a = document.querySelector('#headsDlgBody .tpa-apply'); return a && a.textContent === '적용 — 5줄' && !a.disabled; }", timeout=60000)
        page.select_option(keep, "s:a")
        undo0 = page.evaluate("state.undo")
        page.locator("#headsDlgBody .tpa-apply").click()
        page.wait_for_function(f"() => state.undo === {undo0 + 1} && !state.busy", timeout=60000)
        page.wait_for_function("() => (document.querySelector('#headsDlgBody .tpa-apply') || {}).textContent === '적용함 — 5줄 · 떼기 1줄'", timeout=30000)
        page.wait_for_function("() => heads.outline && heads.outline.templates['3~2a'] && [...document.querySelectorAll('.tpa-tpl option')].some((o) => o.value === '3~2a')", timeout=30000)
        v, vc = slot(doc, 3, 2), slot(doc, "3~2a", 2)
        cut = page.evaluate("""() => ({ t: heads.outline.templates['3~2a'], line: heads.outline.lines['p5765'], count: document.querySelector('.tpa-count').textContent,
          opt: [...document.querySelectorAll('.tpa-tpl option')].find((o) => o.value === '3~2a').textContent, mark: [...document.querySelectorAll('.tpl-mark')].some((m) => /T3L2a L2/.test(m.textContent)) })""")  # 가까운 줄의 표와 한 표에 모일 수 있다(「T3 L1 · T3L2a L2」)
        check("「적용 — 5줄 · 떼기 1줄」 → 대표 바꿈 · 5줄 맞춤 · p5765 는 서식 종속 템플릿 「T3L2a」(줄은 L2 부터)로 · 대상 목록에 「T3L2a … · 서식 종속」 · 문서 표 「T3L2a L2」",
              v["rep"] == "p5209" and v["total"] == 6 and v["others"] == 0 and vc["total"] == 1 and vc["rep"] == "p5765" and cut["t"]["no"] == "3L2a" and cut["t"]["base"] == 1
              and cut["t"]["vari"] == {"of": "3", "level": 2, "sfx": "a", "ofNo": 3} and cut["line"]["tpl"] == "3~2a" and cut["line"]["level"] == 2 and "새 템플릿 T3L2a" in cut["count"]
              and cut["opt"].startswith("T3L2a") and cut["opt"].endswith("서식 종속") and cut["mark"], [v["rep"], v["total"], v["others"], vc["total"], cut])
        page.screenshot(path=str(OUT / "07b_applied_split.png"))
        page.click("#undoBtn")
        page.wait_for_function(f"() => state.undo === {undo0} && !state.busy", timeout=60000)
        page.wait_for_function("() => heads.outline && !heads.outline.templates['3~2a']", timeout=30000)
        v = slot(doc, 3, 2)
        check("실행 취소 한 번 → 뗀 템플릿이 없어지고 대표·서식이 처음대로", v["rep"] == "p6502" and v["others"] == 2 and v["total"] == 7, [v["rep"], v["others"], v["total"]])
        # 기본으로 되돌리기(두 번) · 새 스킬 저장 · 지우기
        page.locator("#headsDlgBody .tpa-state button", has_text="기본으로 되돌리기").click()
        check("「기본으로 되돌리기」 는 줄 안에서 두 번 — 처음엔 「되돌리기 확인」", page.locator("#headsDlgBody .tpa-state button", has_text="되돌리기 확인").count() == 1
              and requests.get(f"{base}/api/outline/agent/skills/tidy", timeout=30).json()["custom"])
        page.locator("#headsDlgBody .tpa-state button", has_text="되돌리기 확인").click()
        page.wait_for_function("() => (document.querySelector('.tpa-saved') || {}).textContent === '기본 스킬(고친 적 없음)'", timeout=30000)
        check("한 번 더 → 기본 글로", not requests.get(f"{base}/api/outline/agent/skills/tidy", timeout=30).json()["custom"] and "## 대표 고르기" in page.locator("#headsDlgBody .tpa-text").input_value())
        page.locator("#headsDlgBody button", has_text="새 스킬").click()
        page.fill("#headsDlgBody .tpa-name", "글꼴만 통일")
        page.fill("#headsDlgBody .tpa-text", "글꼴이 다른 갈래만 맞춘다.")
        check("「새 스킬」 — 저장 전 표시", page.locator("#headsDlgBody .tpa-saved").inner_text() == "새 스킬 — 저장 전")
        page.locator("#headsDlgBody .tpa-save").click()
        page.wait_for_function("() => /^저장됨 · 판 1/.test((document.querySelector('.tpa-saved') || {}).textContent || '')", timeout=30000)
        ls = requests.get(f"{base}/api/outline/agent", timeout=30).json()["skills"]
        mine = [s for s in ls if not s["builtin"]]
        check("새 스킬 저장 → 목록에", len(mine) == 1 and mine[0]["name"] == "글꼴만 통일" and page.evaluate("[...document.querySelectorAll('.tpa-skill option')].some((o) => o.textContent === '글꼴만 통일')"), ls)
        page.locator("#headsDlgBody .tpa-state button", has_text="지우기").click()
        page.locator("#headsDlgBody .tpa-state button", has_text="지우기 확인").click()
        page.wait_for_function("() => ![...document.querySelectorAll('.tpa-skill option')].some((o) => o.textContent === '글꼴만 통일')", timeout=30000)
        check("만든 스킬 「지우기」(두 번) → 목록에서 빠짐", not [s for s in requests.get(f"{base}/api/outline/agent", timeout=30).json()["skills"] if not s["builtin"]])
        page.locator("#headsDlgTools .tpa-back").click()
        page.wait_for_selector("#headsDlg[data-kind=templates] .tpl-tree li.trel-node.sel", timeout=30000)
        check("「‹ 템플릿 관계」 → 그 템플릿을 편 템플릿 관계", page.evaluate("document.querySelector('#headsDlgBody li.trel-node.sel').dataset.tpl") == "3")
        page.click("#headsDlgClose")

        # ---- 좁은 패널(「다른 서식」 묶음을 편 채로 잰다)
        page.wait_for_selector(f'{NODE(TAB, 3)} > .trel-row .olm-odd-btn', timeout=30000)
        page.locator(f'{NODE(TAB, 3)} > .trel-row .olm-odd-btn').first.click()
        page.wait_for_selector(f'{NODE(TAB, 3)} > .olm-odd:not([hidden]) .olo-row', timeout=10000)
        page.evaluate("() => { const c = colSizers.find((x) => x.box === 'panel'); c.w = 320; c.apply(); }")
        page.wait_for_timeout(500)
        ov = page.evaluate("""() => { const pr = document.getElementById('panel').getBoundingClientRect(), R = '#headsTemplatesResult ';
          return [...document.querySelectorAll(['.trel-row', '.tpl-pic', '.tpl-tree-tools', '.olm-odd', '.olo-lh', '.olo-rh', '.olo-rh > *', '.olo-row > .olm-diff'].map((s) => R + s).join(', '))]
            .filter((e) => e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().right > pr.right + 1).length; }""")
        check("패널 320px — 탭의 트리 줄·그림·단추·펼친 「다른 서식」 묶음이 패널 밖으로 안 나감", ov == 0 and page.locator(f'{NODE(TAB, 3)} > .olm-odd:not([hidden]) .olo-row').count() >= 3, ov)
        page.screenshot(path=str(OUT / "08_narrow_panel.png"))
        b.close()
    check("콘솔 오류 없음", not errors, errors[:5])


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

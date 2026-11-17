"""띠 표 줄(spec_헤딩_추출 ② §6 「띠 표 줄」 — app/heading_bands.py · heading_graph · outline_edit.build_overlay · app.js tplTreeDraw·olMark · outline_lift.js) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

2026-11-17 사용자 "테이블도 헤딩레벨로 간주 … 별첨, 부록 appendix … 지금 템플릿 문서 구조상에서는 잡히질 않아" → 답 「제 템플릿으로」 · 「헤딩 추출이 스스로」.
연구개발계획서 양식(1·2단계를 끝점으로 — 스크립트만): 「별첨1」~「별첨9」 띠 표(1행 3칸: 이름표 칸 · 빈 칸 · 제목 칸).
- 그래프: kind band 노드 9 · 띠 표 템플릿(kind band · 사슬 「별첨N」 · 맨 뒤 번호) · 부모 = 문서 맨 위.
- 여백 표시: 이름표 문단(칸 안) 옆 「T{n} L1」 · 줄 role table · 도움말 「띠 표 줄」 · 별첨4 아래 「□ 과제개요」 는 제 템플릿 L1 그대로.
- 「템플릿 관계」: 「본문 템플릿」 절에 띠 표 템플릿 줄 「별첨N」 · 9곳 · 표지 「L1 = 별첨·부록 표 제목」 · 「표를 L1 으로」 단추 없음 · 펼치면 레벨 줄 L1 「표 제목 · 별첨N ×9」 과 그 아래 가지 템플릿.
- 띠 표 줄에서 Enter = 거절 알림(문서 안 바뀜) · 「표를 L1 으로」 끝점 = 400 「별첨·부록 표 제목 템플릿」 · 내려받은 파일 = 원본 바이트 · 콘솔 오류 없음(뜻한 거절 400 빼고).

    python -X utf8 tools/smoke_heading_bands_ui.py <출력 폴더> [--port 18479]
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
ap.add_argument("--port", type=int, default=18479)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"


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


LINE = """(id) => { const p = paraEl(id); if (!p) return null; const ol = outlineLine(p);
  const mark = [...document.querySelectorAll('#doc .tpl-mark:not(.fmt)')].find((m) => Math.abs(m.getBoundingClientRect().top - p.getBoundingClientRect().top) < 8);
  return { text: readText(p), level: ol ? ol.level : null, role: ol ? ol.role : null, name: ol ? ol.name || '' : '', no: ol ? ol.no : null, mark: mark ? mark.textContent : '',
    title: mark ? mark.title : '', inCell: !!p.closest('td') }; }"""
ROW = """(tid) => { const li = [...document.querySelectorAll('#headsDlgBody > .trel > li.trel-node, #headsDlgBody .tpl-tree > .trel > li.trel-node')].find((x) => x.dataset.tpl === String(tid)); if (!li) return null;
  const row = li.querySelector(':scope > .trel-row');
  let h = li.parentElement.previousElementSibling; while (h && h.tagName !== 'H3') h = h.previousElementSibling;
  return { section: h ? h.textContent : '', name: (row.querySelector('.trel-name') || {}).textContent || '', meta: (row.querySelector('.trel-meta') || {}).textContent || '',
    chip: (row.querySelector('.oll-chip') || {}).textContent || '', liftBtn: !!row.querySelector('.oll-btn'), cls: li.className, sub: !!row.querySelector('.olm-sub'),
    fmtRows: li.querySelectorAll(':scope > .trel-body > .trel-levels > li > .olm').length,
    levels: [...li.querySelectorAll(':scope > .trel-body > .trel-levels > li > .trel-level')].map((e) => e.textContent.replace(/\\s+/g, ' ').trim()),
    kids: [...li.querySelectorAll(':scope > .trel-body > .trel-levels > li > .trel > li.trel-node')].map((e) => e.dataset.tpl) }; }"""


def main():
    wait_server()
    r = requests.post(base + "/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}, timeout=120)
    assert r.status_code == 200, r.text
    doc = r.json()["docId"]
    run_stage(doc, 1)
    run_stage(doc, 2)
    g = requests.get(f"{base}/api/docs/{doc}/headings/graph", timeout=120).json()
    bands = [n for n in g["nodes"] if n.get("kind") == "band"]
    bt = [t for t in g["templates"] if t.get("kind") == "band"]
    check("그래프 — 띠 표 줄 9(별첨1~9) · 부모 = 문서 맨 위 · 띠 표 템플릿 하나(사슬 「별첨N」 · 9곳 · 맨 뒤 번호)",
          [n["letter"] for n in bands] == [f"별첨{i}" for i in range(1, 10)] and {n["parent"] for n in bands} == {"root"} and len(bt) == 1 and bt[0]["chain"] == ["별첨N"]
          and bt[0]["instances"] == 9 and bt[0]["no"] == len(g["templates"]), [[(n["letter"], n["parent"], n["tplNo"]) for n in bands], bt and {k: bt[0].get(k) for k in ("no", "chain", "instances", "kind")}])
    if not bands or not bt:
        return
    no, tid = bt[0]["no"], bt[0]["id"]
    b2, b4 = bands[1], bands[3]
    kid = next((n for n in g["nodes"] if n.get("parent") == b4["id"] and (n.get("letter") or "").strip() == "□"), None)
    check("그래프 — 별첨4 아래 「□」 줄의 부모 = 별첨4 띠 표 줄 · 템플릿은 띠 표 템플릿이 아니라 제 템플릿 L1", bool(kid) and kid["tplNo"] != no and kid["level"] == 1, kid)
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1600, "height": 950}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/#w={doc}")
        page.wait_for_selector("#doc .para", timeout=60000)
        page.wait_for_function("(id) => !!heads.outline && !!heads.outline.lines[id]", arg=b2["para"], timeout=30000)
        page.evaluate("(id) => paraEl(id).scrollIntoView({ block: 'center' })", b2["para"])
        page.wait_for_timeout(700)
        v = page.evaluate(LINE, b2["para"])
        check(f"여백 표시 — 이름표 문단 「별첨2」(칸 안) 옆 「T{no} L1」 · 표 줄(role table) · 이름표 글 · 도움말 「띠 표 줄」",
              v and v["text"].strip() == "별첨2" and v["inCell"] and v["level"] == 1 and v["role"] == "table" and v["name"] == "별첨2" and f"T{no} L1" in v["mark"] and "별첨·부록 표 제목 줄" in v["title"], v)
        page.screenshot(path=str(OUT / "01_band_mark.png"))
        if kid:
            page.evaluate("(id) => paraEl(id).scrollIntoView({ block: 'center' })", kid["para"])
            page.wait_for_timeout(500)
            k = page.evaluate(LINE, kid["para"])
            check("여백 표시 — 별첨4 아래 「□」 는 제 템플릿 L1 그대로(레벨이 밀리지 않는다)", k and k["level"] == 1 and k["no"] == kid["tplNo"] and f"T{kid['tplNo']} L1" in k["mark"], k)

        # 템플릿 관계 — 띠 표 템플릿 줄
        page.evaluate("(t) => tplRelOpen(t)", tid)
        page.wait_for_selector("#headsDlgBody li.trel-node", timeout=20000)
        page.wait_for_timeout(700)
        row = page.evaluate(ROW, tid)
        check("템플릿 관계 — 「본문 템플릿」 절에 띠 표 템플릿 줄 「별첨N」 · 9곳 · 표지 「L1 = 별첨·부록 표 제목」 · 「표를 L1 으로」·「하위로」 단추 없음",
              row and row["section"].startswith("본문 템플릿") and row["name"] == "별첨N" and "9곳" in row["meta"] and row["chip"] == "L1 = 별첨·부록 표 제목" and not row["liftBtn"] and not row["sub"]
              and "k-band" in row["cls"], row)
        check("템플릿 관계 — 펼친 레벨 줄 L1 「표 제목 · 별첨N」 ×9(서식 줄 없음) · 그 아래 가지 템플릿(별첨 아래 줄의 템플릿)",
              row and len(row["levels"]) == 1 and "표 제목 · 별첨N" in row["levels"][0] and "×9" in row["levels"][0] and row["fmtRows"] == 0
              and (not kid or str(kid["tplNo"]) in [str(x) for x in row["kids"]]), row)
        places = page.evaluate("(t) => olmPlaces(t).map((p) => p.parent)", str(kid["tplNo"])) if kid else []
        check("「하위로」 의 넣을 자리에 띠 표 템플릿은 없다(별첨 아래 줄은 제 템플릿 그대로)", str(tid) not in [str(x) for x in places], places)
        page.screenshot(path=str(OUT / "02_band_template.png"))

        # 띠 표 줄에서 Enter — 거절(문서 안 바뀜)
        page.evaluate("(id) => { const p = paraEl(id); p.scrollIntoView({ block: 'center' }); focusAt({ id, offset: readText(p).length }); }", b2["para"])
        page.wait_for_timeout(200)
        before = page.evaluate("() => state.undo")
        page.keyboard.press("Enter")
        page.wait_for_function("() => !state.busy", timeout=20000)
        page.wait_for_timeout(500)
        st = page.evaluate("() => { const t = document.getElementById('toast'); return { undo: state.undo, toast: t.hidden ? '' : t.textContent }; }")
        v2 = page.evaluate(LINE, b2["para"])
        check("띠 표 줄에서 Enter — 거절 알림 · 실행 취소 수 그대로 · 이름표 글·줄 그대로", st["undo"] == before and "표 제목" in st["toast"] and v2["text"].strip() == "별첨2" and v2["role"] == "table", [st, v2])
        page.close()
        b.close()
    r = requests.post(f"{base}/api/docs/{doc}/outline/lift", json={"tpl": str(tid)}, timeout=60)
    check("「표를 L1 으로」 끝점 — 띠 표 템플릿은 400 「별첨·부록 표 제목 템플릿」", r.status_code == 400 and "별첨·부록 표 제목 템플릿" in r.text, [r.status_code, r.text[:200]])
    c = requests.get(f"{base}/api/docs/{doc}/outline/lift", params={"tpl": str(tid)}, timeout=60).json()
    check("「표를 L1 으로」 후보 — blocked 까닭", "별첨·부록 표 제목 템플릿" in (c.get("blocked") or ""), c.get("blocked"))
    check("문서는 안 바뀜(내려받은 파일 = 원본 바이트)", requests.get(f"{base}/api/docs/{doc}/download", timeout=60).content == PLAN.read_bytes())
    bad = [e for e in errors if "400" not in e]
    check("콘솔 오류 없음(뜻한 거절 400 빼고)", not bad, bad[:5])


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

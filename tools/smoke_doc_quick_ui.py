"""문서 이름 줄의 바로 열기 아이콘(spec_작업 ② §17 「이름 줄 바로 열기」 — index.html #nameQuick · app/static/doc_quick.js) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

문서 셋을 올린다: ㉮ 연구개발계획서 양식(hwpx — 1·2단계를 끝점으로 돌림) ㉯ 기술수요조사서(hwpx — 분석 전) ㉰ 기술수요조사서(docx).
- ㉮ 이름 줄: 문서 이름 바로 뒤(파일 크기 앞)에 아이콘 둘 「템플릿 관계」 · 「서식 관리자」 — 글 없음 · 28px 이하 · 줄 높이 35px 그대로 · 넘침 없음.
- 「서식」 묶음을 펴지 않은 채(도구 줄은 「페이지 보기」) 「템플릿 관계」 를 누르면 2열 「템플릿 관계」 가 열리고 눌림(도구 줄의 같은 단추도) · 다시 누르면 닫힘.
- 「서식 관리자」 → 2열 서식 관리자 · 눌림은 그쪽만 · 열린 채 「템플릿 관계」 를 누르면 그 보기로 바뀜.
- 2열을 » 로 접어 두고 누르면 닫지 않고 편다 · 편집 도구 줄을 접어 두어도 열린다.
- 좁은 폭(2열을 연 1100px · 700px)에서 줄 높이 35px · 넘침 없음 · 아이콘 둘 다 줄 안.
- ㉰ docx 로 바꾸면 「템플릿 관계」 꺼짐(HWPX 만) · 「서식 관리자」 는 열림 — ㉯ 분석 전 hwpx 도 「템플릿 관계」 꺼짐(2단계 결과 없음).
- 콘솔 오류 없음.

    python -X utf8 tools/smoke_doc_quick_ui.py <출력 폴더> [--port 18471]
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
ap.add_argument("--port", type=int, default=18471)
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
SAMPLES = ROOT / "samples"


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


def upload(name):
    r = requests.post(base + "/api/docs", files={"file": (name, (SAMPLES / name).read_bytes(), "application/octet-stream")}, timeout=120)
    assert r.status_code == 200, r.text
    return r.json()["docId"]


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


# 이름 줄 — 차례 · 크기 · 넘침 · 단추 둘의 상태
ROW = """() => { const row = document.getElementById('fileInfo'), q = document.getElementById('nameQuick'), vis = (e) => !!e && e.getClientRects().length > 0, rr = row.getBoundingClientRect();
  const inside = (e) => { const r = e.getBoundingClientRect(); return r.left >= rr.left - 1 && r.right <= rr.right + 1 && r.top >= rr.top - 1 && r.bottom <= rr.bottom + 1; };
  const btn = (id) => { const b = document.getElementById(id), r = b.getBoundingClientRect(); return { label: b.getAttribute('aria-label'), text: b.textContent.trim(), svg: !!b.querySelector('svg'),
    w: Math.round(r.width), h: Math.round(r.height), shown: vis(b), inside: vis(b) && inside(b), off: b.disabled, pressed: b.getAttribute('aria-pressed'), title: b.title }; };
  return { order: [...row.children].map((e) => e.id), rowH: Math.round(rr.height), rowW: Math.round(rr.width), over: row.scrollWidth > row.clientWidth + 1,
    meta: vis(document.getElementById('fileMeta')), tpl: btn('nameTplRel'), lib: btn('nameStyleLib'),
    nameW: Math.round((vis(document.getElementById('docSwitch')) ? document.getElementById('docSwitch') : document.getElementById('fileName')).getBoundingClientRect().width) }; }"""
COL = "() => { const c = document.getElementById('headsDlg'); return { open: !c.hidden, kind: c.dataset.kind || '', folded: c.classList.contains('folded') }; }"
TB = "() => ({ tpl: document.getElementById('tbTplRel').getAttribute('aria-pressed'), lib: document.getElementById('tbStyleLib').getAttribute('aria-pressed'), set: !document.getElementById('tbStyle').hidden })"


def col_is(page, kind):
    page.wait_for_function("(k) => { const c = document.getElementById('headsDlg'); return k ? !c.hidden && c.dataset.kind === k && !c.classList.contains('folded') : c.hidden; }", arg=kind, timeout=20000)
    page.wait_for_timeout(150)  # 눌림 표시는 열 요소를 지켜보다가 따라 그린다(MutationObserver 두 번)


def open_doc(page, doc):
    page.evaluate("(id) => { openWork(id); }", doc)
    page.wait_for_function("(id) => state.id === id && !document.getElementById('fileInfo').hidden && !!document.querySelector('#doc .para')", arg=doc, timeout=60000)
    page.wait_for_timeout(1200)  # 개요 오버레이(GET /outline) · 문서 목록


def main():
    wait_server()
    plan = upload("연구개발계획서_양식.hwpx")
    run_stage(plan, 1)
    run_stage(plan, 2)
    raw = upload("기술수요조사서.hwpx")
    docx = upload("기술수요조사서.docx")
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1500, "height": 950}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/#w={plan}")
        page.wait_for_selector("#doc .para", timeout=60000)
        page.wait_for_function("() => !document.getElementById('nameTplRel').disabled", timeout=30000)
        page.wait_for_timeout(600)

        v = page.evaluate(ROW)
        at = v["order"].index("nameQuick") if "nameQuick" in v["order"] else -1
        # 2026-11-15(newfilemanager-2b — spec_작업 ② §20): 아이콘 묶음과 파일 크기 사이에 분석 상태(#docStatus)가 들어왔다 — 아이콘은 여전히 문서 이름 바로 뒤
        check("이름 줄 — 문서 이름(#docSwitch) 바로 뒤에 아이콘 묶음 · 그 뒤 분석 상태(#docStatus) · 파일 크기(#fileMeta)", at > 0 and v["order"][at - 1] == "docSwitch" and v["order"][at + 1:at + 3] == ["docStatus", "fileMeta"], v["order"])
        check("아이콘 둘 「템플릿 관계」 · 「서식 관리자」 — 글 없이 그림만 · 28px 이하 · 줄 안", all(x["svg"] and x["text"] == "" and x["inside"] and x["w"] <= 28 and x["h"] <= 28 for x in (v["tpl"], v["lib"]))
              and v["tpl"]["label"] == "템플릿 관계" and v["lib"]["label"] == "서식 관리자", v)
        check("줄 높이 35px 그대로 · 넘침 없음 · 파일 크기 글도 보임", v["rowH"] == 35 and not v["over"] and v["meta"], v)
        check("2단계 결과가 있는 hwpx — 둘 다 켜짐 · 도움말은 이름이 먼저", not v["tpl"]["off"] and not v["lib"]["off"] and v["tpl"]["title"].startswith("템플릿 관계") and v["lib"]["title"].startswith("서식 관리자"), v)
        row = page.locator("#fileInfo").bounding_box()
        page.screenshot(path=str(OUT / "01_row.png"), clip={"x": row["x"], "y": row["y"] - 40, "width": row["width"], "height": 120})

        # 템플릿 관계 — 「서식」 묶음을 펴지 않은 채 한 번에
        page.click("#nameTplRel")
        col_is(page, "templates")
        page.wait_for_selector("#headsDlgBody .tpl-tree li.trel-node", timeout=20000)
        v, tb = page.evaluate(ROW), page.evaluate(TB)
        check("「템플릿 관계」 → 2열 템플릿 트리 · 눌림(도구 줄의 같은 단추도) · 「서식」 묶음은 안 펴짐", v["tpl"]["pressed"] == "true" and v["lib"]["pressed"] == "false" and tb == {"tpl": "true", "lib": "false", "set": False}, [v["tpl"], tb])
        check("2열을 열어도 줄 높이 35px · 넘침 없음 · 아이콘 줄 안", v["rowH"] == 35 and not v["over"] and v["tpl"]["inside"] and v["lib"]["inside"], v)
        page.screenshot(path=str(OUT / "02_templates.png"))
        page.click("#nameTplRel")
        col_is(page, "")
        check("다시 누르면 닫힘 · 눌림 풀림", page.evaluate(ROW)["tpl"]["pressed"] == "false")

        # 서식 관리자
        page.click("#nameStyleLib")
        col_is(page, "styleLib")
        v, tb = page.evaluate(ROW), page.evaluate(TB)
        check("「서식 관리자」 → 2열 서식 관리자 · 눌림은 그쪽만", v["lib"]["pressed"] == "true" and v["tpl"]["pressed"] == "false" and tb["lib"] == "true" and not tb["set"], [v["lib"], v["tpl"], tb])
        page.screenshot(path=str(OUT / "03_style_lib.png"))
        page.click("#nameTplRel")
        col_is(page, "templates")
        v = page.evaluate(ROW)
        check("서식 관리자가 열린 채 「템플릿 관계」 → 그 보기로 바뀜(눌림도)", v["tpl"]["pressed"] == "true" and v["lib"]["pressed"] == "false", [v["tpl"], v["lib"]])

        # 접어 둔 2열 — 닫지 않고 편다
        page.evaluate("() => colFold('heads', true)")
        page.wait_for_timeout(200)
        check("2열을 » 로 접음", page.evaluate(COL)["folded"])
        page.click("#nameTplRel")
        col_is(page, "templates")
        check("접힌 채 누르면 닫지 않고 편다", page.evaluate(COL) == {"open": True, "kind": "templates", "folded": False}, page.evaluate(COL))

        # 편집 도구 줄을 접어 두어도
        page.click("#nameTplRel")
        col_is(page, "")
        page.click("#barFold")
        page.wait_for_timeout(200)
        hidden = page.evaluate("() => document.getElementById('docBar').getClientRects().length === 0")
        page.click("#nameStyleLib")
        col_is(page, "styleLib")
        check("편집 도구 줄을 접어 두어도 「서식 관리자」 가 열림", hidden and page.evaluate(ROW)["lib"]["pressed"] == "true", hidden)
        page.click("#barFold")
        page.wait_for_timeout(200)

        # 좁은 폭 — 2열을 연 채 1100px · 닫고 700px
        page.set_viewport_size({"width": 1100, "height": 900})
        page.wait_for_timeout(400)
        v = page.evaluate(ROW)
        check("1100px(2열 열림) — 줄 높이 35px · 넘침 없음 · 아이콘 둘 다 줄 안 · 이름이 먼저 줄어듦", v["rowH"] == 35 and not v["over"] and v["tpl"]["inside"] and v["lib"]["inside"] and v["nameW"] >= 40, v)
        page.screenshot(path=str(OUT / "04_narrow_1100.png"))
        page.click("#nameStyleLib")
        col_is(page, "")
        page.set_viewport_size({"width": 700, "height": 900})
        page.wait_for_timeout(400)
        v = page.evaluate(ROW)
        check("700px — 줄 높이 35px · 넘침 없음 · 아이콘 둘 다 줄 안", v["rowH"] == 35 and not v["over"] and v["tpl"]["inside"] and v["lib"]["inside"], v)
        page.screenshot(path=str(OUT / "05_narrow_700.png"))
        page.set_viewport_size({"width": 1500, "height": 950})
        page.wait_for_timeout(300)

        # docx — 템플릿 관계는 꺼짐(HWPX 만) · 서식 관리자는 열림
        open_doc(page, docx)
        v = page.evaluate(ROW)
        check("docx 로 바꾸면 「템플릿 관계」 꺼짐(도움말 「HWPX 문서에서만」) · 「서식 관리자」 켜짐", v["tpl"]["off"] and "HWPX" in v["tpl"]["title"] and not v["lib"]["off"] and v["tpl"]["shown"], v["tpl"])
        page.click("#nameStyleLib")
        col_is(page, "styleLib")
        check("docx 에서도 「서식 관리자」 가 열림", page.evaluate(ROW)["lib"]["pressed"] == "true")
        page.screenshot(path=str(OUT / "06_docx.png"))
        page.click("#nameStyleLib")
        col_is(page, "")

        # 분석 전 hwpx — 템플릿 관계 꺼짐(2단계 결과 없음)
        open_doc(page, raw)
        v = page.evaluate(ROW)
        check("분석 전 hwpx — 「템플릿 관계」 꺼짐(도움말 「2단계 … 결과가 있어야」)", v["tpl"]["off"] and "2단계" in v["tpl"]["title"] and not v["lib"]["off"], v["tpl"])

        # 다시 분석한 문서로 — 켜짐
        open_doc(page, plan)
        page.wait_for_function("() => !document.getElementById('nameTplRel').disabled", timeout=30000)
        check("분석한 hwpx 로 돌아오면 다시 켜짐", True)
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

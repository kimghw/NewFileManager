"""문서 이름 줄의 표시 아이콘(spec_작업 ② §17 「이름 줄 표시 아이콘」 — index.html #nameQuick · app/static/doc_quick.js · app.js tplMarksDraw) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

2026-11-16 사용자 "나는 애초에 이 2개 아이콘을 이걸 봤다 안봤다 하는 용도로 쓰고 싶었거든" — 아이콘 둘은 문서 왼쪽 여백의 템플릿 표시 「T1 L2」 · 서식 라벨 「S41」 을 **따로** 켜고 끈다
(2026-11-15 의 처음 것 = 「템플릿 관계」·「서식 관리자」 열을 여는 단추 — 그 검사는 이 파일의 옛 판).

문서 셋을 올린다: ㉮ 연구개발계획서 양식(hwpx — 1·2단계를 끝점으로 돌림) ㉯ 기술수요조사서(hwpx — 분석 전) ㉰ 기술수요조사서(docx).
- ㉮ 이름 줄: 문서 이름 바로 뒤(파일 크기 앞)에 아이콘 둘 「템플릿 표시」 · 「서식 라벨 표시」 — 글 없음 · 28px 이하 · 줄 높이 35px 그대로 · 넘침 없음.
- 처음(기억 없음): 템플릿 표시 켜짐(눌림) · 서식 라벨 꺼짐 — 여백에 「TN Lk」 만(캡션 줄은 캡션 템플릿 「C1」 — 템플릿 표시와 같이 켜지고 꺼진다).
- 「서식 라벨 표시」 → 「S…」 가 보이고 눌림 · 「템플릿 표시」 를 끄면 「TN Lk」 는 사라지고 **서식 라벨만** 남는다(끌기 손잡이는 그대로) · 둘 다 끄면 표시 없음 · 다시 켜면 돌아옴.
- 아이콘은 2열을 열지 않는다 · 「템플릿 관계」 열 위의 「문서 표시」·「서식 라벨」 단추와 같은 값(어느 쪽을 눌러도 함께 바뀜 · 「서식 라벨」 단추는 「문서 표시」 를 꺼도 눌린다).
- 새로 고침해도 기억(이 브라우저).
- 셋째 아이콘 「표 라벨 표시」(2026-11-16 사용자 "테이블에 있는 라벨도 보였다 안보였다 하게 해줘" — spec_헤딩_추출 ② §10): 표 옆 여백의 표 라벨(.tbl-mark)을 켜고 끈다 · 처음 켜짐 · 끄면 표 라벨만 사라짐 ·
  새로 고침해도 기억 · 「표」 탭 「표 도구 표시」(tblMarksToggle)와 같은 값 · docx 도 표가 있으면 켜져 있다.
- 좁은 폭(1100px · 700px)에서 줄 높이 35px · 넘침 없음 · 아이콘 셋 다 줄 안.
- ㉰ docx · ㉯ 분석 전 hwpx — 둘 다 꺼짐(도움말 「표시할 것이 없습니다」) · ㉮ 로 돌아오면 다시 켜짐.
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
ROW = """() => { const row = document.getElementById('fileInfo'), vis = (e) => !!e && e.getClientRects().length > 0, rr = row.getBoundingClientRect();
  const inside = (e) => { const r = e.getBoundingClientRect(); return r.left >= rr.left - 1 && r.right <= rr.right + 1 && r.top >= rr.top - 1 && r.bottom <= rr.bottom + 1; };
  const btn = (id) => { const b = document.getElementById(id), r = b.getBoundingClientRect(); return { label: b.getAttribute('aria-label'), text: b.textContent.trim(), svg: !!b.querySelector('svg'),
    w: Math.round(r.width), h: Math.round(r.height), shown: vis(b), inside: vis(b) && inside(b), off: b.disabled, pressed: b.getAttribute('aria-pressed'), title: b.title }; };
  return { order: [...row.children].map((e) => e.id), rowH: Math.round(rr.height), rowW: Math.round(rr.width), over: row.scrollWidth > row.clientWidth + 1,
    meta: vis(document.getElementById('fileMeta')), tpl: btn('nameTplMarks'), fmt: btn('nameFmtMarks'), tbl: btn('nameTblMarks'),
    nameW: Math.round((vis(document.getElementById('docSwitch')) ? document.getElementById('docSwitch') : document.getElementById('fileName')).getBoundingClientRect().width) }; }"""
# 여백 표시 — 템플릿 표(「TN Lk」 — .tpl-mark 가운데 서식 라벨 줄이 아닌 것) · 서식 라벨(아래 줄 .tpl-mark.fmt + 같은 줄 .tm-fmt) · 끌기 손잡이 · 2열
MARKS = """() => ({ tpl: document.querySelectorAll('#doc .tpl-mark:not(.fmt)').length, tplText: [...document.querySelectorAll('#doc .tpl-mark:not(.fmt)')].slice(0, 40).every((e) => /T\\d+ L\\d+|^C\\d+|TEMP|새 /.test(e.textContent)),  // 「C1」 = 캡션 템플릿 표시(spec_hwpx_웹편집 ② §8-10) — 템플릿 표시와 같이 켜지고 꺼진다
  fmt: document.querySelectorAll('#doc .tpl-mark.fmt, #doc .tpl-mark .tm-fmt').length, fmtText: [...document.querySelectorAll('#doc .tpl-mark.fmt')].slice(0, 40).every((e) => /^(S\\d+|≠|≈)/.test(e.textContent)),
  grips: document.querySelectorAll('#doc .ol-grip').length, col: !document.getElementById('headsDlg').hidden })"""
COLBTN = """() => { const q = (c) => { const b = document.querySelector('#headsDlg ' + c); return b ? { pressed: b.getAttribute('aria-pressed'), off: b.disabled } : null; };
  return { marks: q('.tpl-tg-marks'), fmt: q('.tpl-tg-fmt') }; }"""


def marks_when(page, cond):
    page.wait_for_function("(c) => { const t = document.querySelectorAll('#doc .tpl-mark:not(.fmt)').length, f = document.querySelectorAll('#doc .tpl-mark.fmt, #doc .tpl-mark .tm-fmt').length; return eval(c); }", arg=cond, timeout=20000)
    page.wait_for_timeout(150)
    return page.evaluate(MARKS)


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
        page.wait_for_function("() => !document.getElementById('nameTplMarks').disabled", timeout=30000)
        m = marks_when(page, "t > 0")

        v = page.evaluate(ROW)
        at = v["order"].index("nameQuick") if "nameQuick" in v["order"] else -1
        check("이름 줄 — 문서 이름(#docSwitch) 바로 뒤에 아이콘 묶음 · 그 뒤 분석 상태(#docStatus) · 파일 크기(#fileMeta)", at > 0 and v["order"][at - 1] == "docSwitch" and v["order"][at + 1:at + 3] == ["docStatus", "fileMeta"], v["order"])
        check("아이콘 둘 「템플릿 표시」 · 「서식 라벨 표시」 — 글 없이 그림만 · 28px 이하 · 줄 안", all(x["svg"] and x["text"] == "" and x["inside"] and x["w"] <= 28 and x["h"] <= 28 for x in (v["tpl"], v["fmt"]))
              and v["tpl"]["label"] == "템플릿 표시" and v["fmt"]["label"] == "서식 라벨 표시", v)
        check("줄 높이 35px 그대로 · 넘침 없음 · 파일 크기 글도 보임", v["rowH"] == 35 and not v["over"] and v["meta"], v)
        check("2단계 결과가 있는 hwpx — 둘 다 켜짐 · 도움말은 이름이 먼저", not v["tpl"]["off"] and not v["fmt"]["off"] and v["tpl"]["title"].startswith("템플릿 표시") and v["fmt"]["title"].startswith("서식 라벨 표시"), v)
        check("처음(기억 없음) — 템플릿 표시 눌림(켜짐) · 서식 라벨 안 눌림 · 여백에 「TN Lk」 만 · 손잡이 있음", v["tpl"]["pressed"] == "true" and v["fmt"]["pressed"] == "false" and m["tpl"] > 0 and m["tplText"] and m["fmt"] == 0 and m["grips"] > 0, [v["tpl"], v["fmt"], m])
        row = page.locator("#fileInfo").bounding_box()
        page.screenshot(path=str(OUT / "01_row.png"), clip={"x": row["x"], "y": row["y"] - 40, "width": row["width"], "height": 120})
        tpl0, grips0 = m["tpl"], m["grips"]

        # 서식 라벨 켜기 — 「TN Lk」 아래(또는 같은 줄 뒤)에 「S…」
        page.click("#nameFmtMarks")
        m = marks_when(page, "f > 0")
        v = page.evaluate(ROW)
        check("「서식 라벨 표시」 → 「S…」 가 보임 · 눌림 · 「TN Lk」 는 그대로 · 2열은 안 열림", v["fmt"]["pressed"] == "true" and v["tpl"]["pressed"] == "true" and m["fmt"] > 0 and m["fmtText"] and m["tpl"] == tpl0 and not m["col"], [v["fmt"], m])
        check("도움말이 지금 상태를 말함(「켜짐 — 누르면 … 숨깁니다」)", "켜짐" in v["fmt"]["title"] and "숨깁니다" in v["fmt"]["title"], v["fmt"]["title"])
        page.screenshot(path=str(OUT / "02_both.png"))

        # 템플릿 표시 끄기 — 서식 라벨만 남는다
        page.click("#nameTplMarks")
        m = marks_when(page, "t === 0")
        v = page.evaluate(ROW)
        check("「템플릿 표시」 끔 → 「TN Lk」 사라짐 · **서식 라벨만** 남음 · 손잡이 그대로 · 2열 안 열림", v["tpl"]["pressed"] == "false" and v["fmt"]["pressed"] == "true" and m["tpl"] == 0 and m["fmt"] > 0 and m["fmtText"] and m["grips"] == grips0 and not m["col"], [v["tpl"], m])
        check("끈 아이콘의 도움말(「꺼짐 — 누르면 … 보입니다」)", "꺼짐" in v["tpl"]["title"] and "보입니다" in v["tpl"]["title"], v["tpl"]["title"])
        page.screenshot(path=str(OUT / "03_fmt_only.png"))

        # 「템플릿 관계」 열 위의 단추와 같은 값 — 「서식 라벨」 단추는 「문서 표시」 가 꺼져 있어도 눌린 채 · 꺼지지 않음
        page.evaluate("() => tplRelOpen()")
        page.wait_for_selector("#headsDlg .tpl-tg-fmt", timeout=20000)
        cb = page.evaluate(COLBTN)
        check("열 위 단추와 같은 값 — 「문서 표시」 안 눌림 · 「서식 라벨」 눌림(꺼진 단추가 아님)", cb == {"marks": {"pressed": "false", "off": False}, "fmt": {"pressed": "true", "off": False}}, cb)
        page.click("#headsDlg .tpl-tg-fmt")
        m = marks_when(page, "t === 0 && f === 0")
        v = page.evaluate(ROW)
        check("열의 「서식 라벨」 을 끄면 이름 줄 아이콘도 풀림 · 여백 표시 없음(손잡이만)", v["fmt"]["pressed"] == "false" and v["tpl"]["pressed"] == "false" and m["tpl"] == 0 and m["fmt"] == 0 and m["grips"] == grips0, [v["fmt"], m])
        page.click("#nameTplMarks")
        m = marks_when(page, "t > 0")
        cb = page.evaluate(COLBTN)
        check("이름 줄 「템플릿 표시」 를 켜면 열의 「문서 표시」 도 눌림 · 「TN Lk」 돌아옴", cb["marks"]["pressed"] == "true" and m["tpl"] > 0 and m["fmt"] == 0, [cb, m])  # 2열이 열려 있어 배율이 다르다 — 한 표에 모이는 줄 수가 달라 개수는 처음과 다를 수 있다
        page.evaluate("() => headsColClose(true)")
        page.wait_for_timeout(200)

        # 새로 고침해도 기억 — 템플릿 끔 · 서식 켬으로 두고
        page.click("#nameTplMarks")
        page.click("#nameFmtMarks")
        marks_when(page, "t === 0 && f > 0")
        page.reload()
        page.wait_for_selector("#doc .para", timeout=60000)
        page.wait_for_function("() => !document.getElementById('nameFmtMarks').disabled", timeout=30000)
        m = marks_when(page, "t === 0 && f > 0")
        v = page.evaluate(ROW)
        check("새로 고침 뒤에도 기억 — 템플릿 끔 · 서식 라벨 켬(라벨만 보임)", v["tpl"]["pressed"] == "false" and v["fmt"]["pressed"] == "true" and m["tpl"] == 0 and m["fmt"] > 0, [v["tpl"], v["fmt"], m])
        page.click("#nameTplMarks")
        page.click("#nameFmtMarks")
        m = marks_when(page, "t > 0 && f === 0")
        check("처음 값으로 되돌림(템플릿 켬 · 서식 끔)", m["tpl"] == tpl0, m)

        # 셋째 아이콘 「표 라벨 표시」(2026-11-16 사용자 "테이블에 있는 라벨도 보였다 안보였다 하게 해줘") — 표 옆 여백의 표 라벨(.tbl-mark)을 켜고 끈다 · 「표」 탭 「표 도구 표시」 와 같은 값(tables.js tblMarksToggle)
        tbl_n = "() => document.querySelectorAll('#doc .tbl-mark').length"
        page.wait_for_function("() => document.querySelectorAll('#doc .tbl-mark').length > 0 && !document.getElementById('nameTblMarks').disabled", timeout=30000)
        page.wait_for_timeout(300)
        v, t0 = page.evaluate(ROW), page.evaluate(tbl_n)
        check("셋째 아이콘 「표 라벨 표시」 — 서식 라벨 다음 · 글 없이 그림만 · 28px 이하 · 줄 안 · 줄 높이 35px · 넘침 없음",
              page.evaluate("() => [...document.getElementById('nameQuick').children].map((e) => e.id)") == ["nameTplMarks", "nameFmtMarks", "nameTblMarks"] and v["tbl"]["label"] == "표 라벨 표시"
              and v["tbl"]["svg"] and v["tbl"]["text"] == "" and v["tbl"]["inside"] and v["tbl"]["w"] <= 28 and v["tbl"]["h"] <= 28 and v["rowH"] == 35 and not v["over"], v)
        check("처음(기억 없음) — 표 라벨 켜짐(눌림) · 여백에 표 라벨이 보임 · 도움말 「켜짐 — 누르면 … 숨깁니다」", not v["tbl"]["off"] and v["tbl"]["pressed"] == "true" and t0 > 0 and v["tbl"]["title"].startswith("표 라벨 표시 켜짐") and "숨깁니다" in v["tbl"]["title"], [v["tbl"], t0])
        page.click("#nameTblMarks")
        page.wait_for_function("() => document.querySelectorAll('#doc .tbl-mark').length === 0", timeout=20000)
        page.wait_for_timeout(200)
        v, m = page.evaluate(ROW), page.evaluate(MARKS)
        check("「표 라벨 표시」 끔 → 표 라벨 사라짐 · 안 눌림 · 「TN Lk」·손잡이는 그대로 · 2열 안 열림 · 다른 두 아이콘 그대로",
              v["tbl"]["pressed"] == "false" and "꺼짐" in v["tbl"]["title"] and m["tpl"] == tpl0 and m["grips"] == grips0 and not m["col"] and v["tpl"]["pressed"] == "true" and v["fmt"]["pressed"] == "false", [v["tbl"], m])
        page.screenshot(path=str(OUT / "05_tbl_off.png"))
        page.reload()
        page.wait_for_selector("#doc .para", timeout=60000)
        page.wait_for_function("() => !document.getElementById('nameTblMarks').disabled", timeout=30000)
        marks_when(page, "t > 0")
        v = page.evaluate(ROW)
        check("새로 고침 뒤에도 기억 — 표 라벨 끔(여백에 표 라벨 없음 · 켤 수 있음)", v["tbl"]["pressed"] == "false" and not v["tbl"]["off"] and page.evaluate(tbl_n) == 0, [v["tbl"], page.evaluate(tbl_n)])
        page.evaluate("() => tblMarksToggle()")  # 「표」 탭 「표 도구 표시」 단추가 부르는 함수 — 같은 값
        page.wait_for_function("() => document.querySelectorAll('#doc .tbl-mark').length > 0", timeout=20000)
        page.wait_for_timeout(200)
        v = page.evaluate(ROW)
        check("「표 도구 표시」(같은 값)로 켜면 아이콘도 눌림 · 표 라벨이 돌아옴(수 같음)", v["tbl"]["pressed"] == "true" and page.evaluate(tbl_n) == t0, [v["tbl"], t0, page.evaluate(tbl_n)])

        # 좁은 폭
        page.set_viewport_size({"width": 1100, "height": 900})
        page.wait_for_timeout(400)
        v = page.evaluate(ROW)
        check("1100px — 줄 높이 35px · 넘침 없음 · 아이콘 셋 다 줄 안 · 이름이 먼저 줄어듦", v["rowH"] == 35 and not v["over"] and v["tpl"]["inside"] and v["fmt"]["inside"] and v["tbl"]["inside"] and v["nameW"] >= 40, v)
        page.set_viewport_size({"width": 700, "height": 900})
        page.wait_for_timeout(400)
        v = page.evaluate(ROW)
        check("700px — 줄 높이 35px · 넘침 없음 · 아이콘 셋 다 줄 안", v["rowH"] == 35 and not v["over"] and v["tpl"]["inside"] and v["fmt"]["inside"] and v["tbl"]["inside"], v)
        page.screenshot(path=str(OUT / "04_narrow_700.png"))
        page.set_viewport_size({"width": 1500, "height": 950})
        page.wait_for_timeout(300)

        # docx · 분석 전 hwpx — 표시할 것이 없다
        open_doc(page, docx)
        v = page.evaluate(ROW)
        check("docx — 둘 다 꺼짐 · 안 눌림 · 도움말 「표시할 것이 없습니다」", all(x["off"] and x["pressed"] == "false" and "표시할 것이 없습니다" in x["title"] and x["shown"] for x in (v["tpl"], v["fmt"])), [v["tpl"], v["fmt"]])
        check("docx — 표가 있으면 「표 라벨 표시」 는 켜져 있다(헤딩 추출과 무관 · 눌림 · 여백에 표 라벨)", not v["tbl"]["off"] and v["tbl"]["pressed"] == "true" and page.evaluate(tbl_n) > 0, [v["tbl"], page.evaluate(tbl_n)])
        open_doc(page, raw)
        v = page.evaluate(ROW)
        check("분석 전 hwpx — 둘 다 꺼짐(도움말 「2단계 … 돌리면 생깁니다」)", all(x["off"] and "2단계" in x["title"] for x in (v["tpl"], v["fmt"])), [v["tpl"], v["fmt"]])

        # 다시 분석한 문서로 — 켜짐
        open_doc(page, plan)
        page.wait_for_function("() => !document.getElementById('nameTplMarks').disabled && !document.getElementById('nameFmtMarks').disabled", timeout=30000)
        v = page.evaluate(ROW)
        check("분석한 hwpx 로 돌아오면 다시 켜짐(템플릿 눌림)", v["tpl"]["pressed"] == "true" and v["fmt"]["pressed"] == "false", [v["tpl"], v["fmt"]])
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

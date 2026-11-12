"""엑셀식 보기 — 코드 정의 식 판정(「(M=K+L)」)·참조 칸 표시 화면 연기 시험(spec_헤딩_추출 ② §9·§14 「참조 표시」) — 임시 서버에만(LLM·PDF 끔 권장: NFM_LLM_BACKEND=off NFM_PDF=off,
NFM_WORKS·NFM_RENDER·NFM_HEADINGS 는 임시 폴더).

python -X utf8 tools/smoke_table_refs_ui.py <http://127.0.0.1:포트> <그림 폴더>
연구개발계획서 양식 → 「연구개발기관별 사용계획 총괄표」(t10025, 26×11)의 2열 격자: 판정 수식 66(총액 = 직접비 소계 + 간접비 …) → 수식 칸을 고르면 참조 칸 색 테두리·「참조」 줄 표지·판정 근거 →
범위 한 테두리 → 참조 줄 높이 고정(격자가 안 밀림) → 값 13개를 넣어 계산값 → 수식 줄에 치는 동안 참조 → Esc → 표지 누르기 →
LLM 수식 판정(서버 답은 가짜 — page.route): 제안 수 · 귀퉁이 표시 · 칸마다 적용/무시 · 값 같음·같음 · 모두 적용 · 저장 · 지우기 → 콘솔 오류. 1분쯤."""
import json
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

URL, OUT = sys.argv[1], Path(sys.argv[2])
TID = "t10025"
FAILS = []
W = ".heads-col .xl-wrap.col"
REFS_JS = """() => { const w = document.querySelector('.heads-col .xl-wrap.col');
  return { tds: [...w.querySelectorAll('td.ref')].map((td) => ({ref: td.dataset.ref, cls: [...td.classList].filter((c) => /^r[0-9]$/.test(c))[0],
             rt: td.style.getPropertyValue('--rt'), rb: td.style.getPropertyValue('--rb'), rl: td.style.getPropertyValue('--rl'), rr: td.style.getPropertyValue('--rr')})),
           chips: [...w.querySelectorAll('.xl-refs .xl-ref')].map((c) => c.textContent), line: w.querySelector('.xl-refs').textContent,
           name: w.querySelector('.xl-name').value, fx: w.querySelector('.xl-fx').value }; }"""


def check(ok, what):
    print(("  ok  " if ok else "  FAIL") + " " + what)
    if not ok:
        FAILS.append(what)


def wait_server(timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if requests.get(URL + "/api/headings/llm", timeout=2).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise SystemExit("서버가 안 뜸")


def grid_type(page, ref, value):
    page.locator(f'{W} td[data-ref="{ref}"]').dblclick()
    inp = page.locator(f"{W} input.xl-edit")
    inp.fill(value)
    inp.press("Enter")
    page.wait_for_timeout(120)


def refs(page):
    return page.evaluate(REFS_JS)


def main():
    wait_server()
    logs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_context(viewport={"width": 1700, "height": 1000}, device_scale_factor=1).new_page()
        page.set_default_timeout(120000)
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(URL)
        page.wait_for_selector(".sample", state="attached")
        page.evaluate("() => { const s = document.getElementById('sampleSection'); if (s) { s.hidden = false; s.open = true; } }")
        page.evaluate("() => document.querySelector('.sample[aria-label=\"예제 연구개발계획서_양식.hwpx 열기\"]').click()")
        page.wait_for_function("document.querySelector('.sheet .para') != null", timeout=240000)
        page.wait_for_timeout(1500)
        doc = page.evaluate("location.hash").split("=", 1)[1]
        cur = requests.get(f"{URL}/api/docs/{doc}/headings/tables/{TID}/agent").json()["own"]  # 앞선 실행이 남긴 사용자 수식을 지운다(예제 작업은 다시 쓰인다)
        if cur.get("formulas"):
            requests.put(f"{URL}/api/docs/{doc}/headings/tables/{TID}/agent", json={"formulas": {}, "version": cur["version"]}).raise_for_status()
            page.reload()
            page.wait_for_function("document.querySelector('.sheet .para') != null", timeout=240000)
            page.wait_for_timeout(1500)
        page.evaluate(f"() => xlColumn('{TID}')")
        page.wait_for_selector(f"{W} td.fx", timeout=60000)
        page.wait_for_timeout(500)
        f = page.evaluate(f"() => Object.fromEntries(document.querySelector('{W}')._model.formulas)")
        print("   수식", len(f))
        want = {"E26": "=E23+E24", "K26": "=K23+K24", "E10": "=SUM(E3:E4)+E5+E6+SUM(E8:E9)", "E11": "=SUM(E3:E4)+E5+SUM(E8:E9)", "E7": "=SUM(E3:E4)+E5+E6",
                "E23": "=E10+SUM(E12:E13)+SUM(E15:E16)+SUM(E17:E18)+E19+E21+E22", "E20": "=(E19/E11)*100",
                "E25": "=(E24/(E3+E5+E6+SUM(E8:E9)+E12+E15+E17+E19+E21))*100", "K3": "=SUM(E3:J3)", "K20": "=(K19/K11)*100"}
        for k, v in want.items():
            check(f.get(k) == v, f"{k} {f.get(k)} (기대 {v})")
        check(len(f) == 66, f"수식 66개(지금 {len(f)})")
        idle = refs(page)
        check(not idle["tds"] and "수식 칸을 고르면" in idle["line"], f"고른 칸 없음 — 안내 글: {idle['line']!r}")
        # 수식 칸 E26 = E23 + E24
        page.locator(f'{W} td[data-ref="E26"]').click()
        r = refs(page)
        print("   E26", r)
        check(r["fx"] == "=E23+E24" and [t["ref"] for t in r["tds"]] == ["E23", "E24"] and [t["cls"] for t in r["tds"]] == ["r0", "r1"], "E26 → 참조 칸 E23(파랑)·E24(빨강)")
        check(len(r["chips"]) == 2 and "E23" in r["chips"][0] and "직접비 소계" in r["chips"][0] and "간접비" in r["chips"][1], f"참조 줄 표지 {r['chips']}")
        check("M=K+L" in r["line"], f"판정 근거 글 — {r['line']!r}")
        page.locator(W).screenshot(path=str(OUT / "01_E26.png"))
        # 범위 하나 = 한 테두리(E3:E4 안쪽 변 0)
        page.locator(f'{W} td[data-ref="E7"]').click()
        r = refs(page)
        by = {t["ref"]: t for t in r["tds"]}
        check(set(by) == {"E3", "E4", "E5", "E6"} and by["E3"]["rb"] == "0px" and by["E4"]["rt"] == "0px" and by["E3"]["rt"] == "2px" and by["E4"]["rb"] == "2px", f"E7 → E3:E4 한 테두리 + E5 + E6 {by}")
        check(by["E3"]["cls"] == by["E4"]["cls"] == "r0" and by["E5"]["cls"] == "r1" and by["E6"]["cls"] == "r2", "묶음마다 다른 색")
        check(any("내부인건비" in c for c in r["chips"]), f"E3:E4 이름 = 내부인건비(A) — {r['chips']}")
        # 가로 범위
        page.locator(f'{W} td[data-ref="K3"]').click()
        r = refs(page)
        by = {t["ref"]: t for t in r["tds"]}
        check(list(by) == ["E3", "F3", "G3", "H3", "I3", "J3"] and by["E3"]["rl"] == "2px" and by["E3"]["rr"] == "0px" and by["J3"]["rr"] == "2px" and by["G3"]["rl"] == "0px", "K3 → E3:J3 가로 한 테두리")
        page.locator(f'{W} td[data-ref="E25"]').click()
        r = refs(page)
        check(len(r["chips"]) == 10 and len(r["tds"]) == 11, f"E25(간접비 비율) → 묶음 10 · 칸 11 (지금 {len(r['chips'])} · {len(r['tds'])})")
        page.locator(W).screenshot(path=str(OUT / "02_E25.png"))
        top = lambda: page.evaluate("() => { const w = document.querySelector('.heads-col .xl-wrap.col'); return [Math.round(w.querySelector('table.xl').getBoundingClientRect().top), w.querySelector('.xl-refs').offsetHeight]; }")
        t_many = top()
        page.locator(f'{W} td[data-ref="E3"]').click()
        t_none = top()
        check(t_many == t_none and t_none[1] == 24, f"참조 줄 높이 고정 — 표지 10개 {t_many} · 없음 {t_none}(격자가 안 밀림)")
        # 값을 넣어 계산
        for ref, v in {"E3": "10", "E4": "5", "E5": "3", "E6": "2", "E8": "4", "E9": "1", "E12": "7", "E15": "6", "E17": "5", "E19": "4.6", "E21": "1", "E22": "2", "E24": "10"}.items():
            grid_type(page, ref, v)

        def val(ref):
            return page.evaluate(f"() => document.querySelector('{W}')._model.res.get('{ref}')")
        got = {k: val(k) for k in ("E7", "E10", "E11", "E20", "E23", "E25", "E26", "K26", "K3")}
        print("   값", got)
        check(got["E7"] == 20 and got["E10"] == 25 and got["E11"] == 23, "소계 20 · 총 인건비 25 · 수정인건비 23")
        check(abs(got["E23"] - 50.6) < 1e-9 and abs(got["E26"] - 60.6) < 1e-9 and abs(got["K26"] - 60.6) < 1e-9, "직접비 소계 50.6 · 총액 60.6 · 합계 열 총액 60.6")
        check(abs(got["E20"] - 20) < 1e-9 and abs(got["E25"] - 10 / 43.6 * 100) < 1e-9, f"연구수당 비율 20 · 간접비 비율 {10 / 43.6 * 100:.4f}")
        page.locator(f'{W} td[data-ref="E23"]').click()
        page.wait_for_timeout(200)
        page.locator(W).screenshot(path=str(OUT / "03_E23_values.png"))
        r = refs(page)
        check(len(r["tds"]) == 10 and len(r["chips"]) == 7, f"E23 → 칸 10 · 묶음 7 (지금 {len(r['tds'])} · {len(r['chips'])})")
        # 숫자 칸을 고르면 참조 표시 없음
        page.locator(f'{W} td[data-ref="E3"]').click()
        r = refs(page)
        check(not r["tds"] and not r["chips"], "수식 아닌 칸 → 참조 표시 없음")
        # 수식 줄에 치는 동안
        page.locator(f'{W} td[data-ref="F26"]').click()
        fxi = page.locator(f"{W} .xl-fx")
        fxi.fill("=f23+SUM(g3:h4)+")
        r = refs(page)
        check({t["ref"] for t in r["tds"]} == {"F23", "G3", "H3", "G4", "H4"} and len(r["chips"]) == 2 and r["chips"][0].startswith("F23") and r["chips"][1].startswith("G3:H4"), f"치는 중 — F23 · G3:H4 {[t['ref'] for t in r['tds']]} {r['chips']}")
        fxi.press("Escape")
        r = refs(page)
        check(r["fx"] == "=F23+F24" and [t["ref"] for t in r["tds"]] == ["F23", "F24"], "Esc → 저장된 수식의 참조로")
        # 표지를 누르면 그 칸으로(고른 칸은 그대로)
        page.locator(f"{W} .xl-refs .xl-ref").first.click()
        page.wait_for_timeout(200)
        check(page.evaluate(f"() => document.querySelector('{W}')._model.sel") == "F26", "표지를 눌러도 고른 칸은 그대로")
        # ---- LLM 수식 판정 — 서버 답은 가짜(임시 서버는 LLM 을 끔): 제안 표시 · 칸마다 적용/무시 · 모두 적용 · 지우기 · 저장
        calls = []
        answer = {"table": TID, "rev": 0, "range": None, "note": "총액은 직접비 소계 + 간접비", "counts": {"new": 1, "diff": 1, "equiv": 1, "same": 1, "off": 1, "rejected": 1},
                  "call": {"backend": "sdk", "model": "m", "effort": None, "ms": 1234, "costUsd": 0.0123, "error": None},
                  "rejected": [{"ref": "A3", "formula": "=E3", "why": "글이 있는 칸"}],
                  "formulas": [{"ref": "E10", "formula": "=SUM(E3:E6)+SUM(E8:E9)", "reason": "각주 1) 총 인건비", "script": "=SUM(E3:E4)+E5+E6+SUM(E8:E9)", "kind": "equiv"},
                               {"ref": "E14", "formula": "=E12*10%", "reason": "통합관리비는 장비비 현금의 10%", "script": None, "kind": "new"},
                               {"ref": "K14", "formula": "", "reason": "합계 줄이 아님", "script": "=SUM(E14:J14)", "kind": "off"},
                               {"ref": "E20", "formula": "=E19/E11", "reason": "연구수당/수정인건비", "script": "=(E19/E11)*100", "kind": "diff"},
                               {"ref": "E26", "formula": "=E23+E24", "reason": "총액(M=K+L)", "script": "=E23+E24", "kind": "same"}]}

        def fake_llm(route):
            calls.append(route.request.post_data)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(answer, ensure_ascii=False))
        page.route("**/excel/llm", fake_llm)
        check(page.locator(f"{W} .xl-llm-btn").inner_text() == "LLM 수식 판정" and page.locator(f"{W} .xl-llm").inner_text() == "", "「LLM 수식 판정」 단추 — 누르기 전에는 제안 없음")
        page.evaluate("() => { const b = document.querySelector('.heads-col .xl-wrap.col .xl-llm-btn'); b.click(); b.click(); }")  # 잇달아 두 번 — 호출은 한 번
        page.wait_for_selector(f"{W} .xl-llm .xl-note")
        page.wait_for_timeout(200)

        def llm_state():
            return page.evaluate("""() => { const w = document.querySelector('.heads-col .xl-wrap.col'), m = w._model;
              return { bar: w.querySelector('.xl-llm').innerText.replace(/\\s+/g, ' ').trim(), marks: [...w.querySelectorAll('td.llm')].map((td) => td.dataset.ref),
                       strip: w.querySelector('.xl-refs').innerText.replace(/\\s+/g, ' ').trim(), prop: !!w.querySelector('.xl-refs .xl-llm-prop'), llm: [...m.llm.keys()],
                       f: {E14: m.formulas.get('E14') || null, K14: m.formulas.get('K14') || null, E20: m.formulas.get('E20') || null, E10: m.formulas.get('E10') || null},
                       h: w.querySelector('.xl-refs').offsetHeight, btn: w.querySelector('.xl-llm-btn').innerText }; }""")
        s = llm_state()
        print("   LLM", s)
        check(len(calls) == 1 and calls[0] == "{}", f"잇달아 두 번 눌러도 호출 1번(지금 {len(calls)}) · 본문 {calls[:1]}")
        check(s["bar"].startswith("LLM 제안 새 1 · 다름 1 · 끄기 1 · 같음 2") and "모두 적용 3" in s["bar"] and "제안 지우기" in s["bar"] and s["btn"] == "LLM 수식 판정", f"도구 줄 제안 수 — {s['bar']!r}")
        check(s["marks"] == ["E14", "K14", "E20"] and s["f"]["E14"] is None, f"새·끄기·다름 칸에만 표시(값 같음·같음은 없음) — {s['marks']} · 자동 적용 없음")
        page.locator(f'{W} td[data-ref="E14"]').click()
        s = llm_state()
        r = refs(page)
        check(s["prop"] and s["strip"].startswith("LLM 제안 =E12*10% 적용 무시 E14 제안 수식의 참조") and [t["ref"] for t in r["tds"]] == ["E12"] and s["h"] == 24, f"새 제안 칸 — 제안·참조 미리보기 · 줄 높이 24 — {s['strip']!r}")
        page.locator(W).screenshot(path=str(OUT / "04_llm_E14.png"))
        page.locator(f"{W} .xl-refs .xl-llm-prop button", has_text="적용").click()
        s = llm_state()
        check(s["f"]["E14"] == "=E12*10%" and s["marks"] == ["K14", "E20"] and s["bar"].startswith("LLM 제안 새 0 · 다름 1 · 끄기 1 · 같음 3") and not s["prop"], f"적용 → 수식이 되고 표시가 풀림 — {s['bar']!r}")
        page.locator(f'{W} td[data-ref="E20"]').click()
        s = llm_state()
        check(s["prop"] and "지금 수식과 다름" in s["strip"] and "=E19/E11" in s["strip"], f"다름 제안 — {s['strip']!r}")
        page.locator(f"{W} .xl-refs .xl-llm-prop button", has_text="무시").click()
        s = llm_state()
        check(s["f"]["E20"] == "=(E19/E11)*100" and "E20" not in s["llm"] and s["marks"] == ["K14"], "무시 → 그 제안만 버림(수식 그대로)")
        page.locator(f'{W} td[data-ref="E10"]').click()
        s = llm_state()
        check(s["prop"] and "꼴만 다르고 값은 같음" in s["strip"] and s["f"]["E10"] == "=SUM(E3:E4)+E5+E6+SUM(E8:E9)", f"값이 같은 다른 꼴 — 알리기만 — {s['strip']!r}")
        page.locator(f'{W} td[data-ref="E26"]').click()
        check("LLM 도 같은 수식" in llm_state()["strip"], "같은 수식 — 「LLM 도 같은 수식」")
        page.locator(f"{W} .xl-llm button", has_text="모두 적용").click()
        s = llm_state()
        check(s["f"]["K14"] is None and s["marks"] == [] and "모두 적용" not in s["bar"], f"모두 적용 → 끄기 제안까지(K14 수식 없음) — {s['bar']!r}")
        page.wait_for_timeout(1200)  # 사용자 수식 저장(0.6초 모음)
        saved = requests.get(f"{URL}/api/docs/{doc}/headings/tables/{TID}/agent").json()["own"]["formulas"]
        check(saved == {"E14": "=E12*10%", "K14": ""}, f"적용한 제안은 사용자 수식으로 저장 — {saved}")
        page.locator(f"{W} .xl-llm button", has_text="제안 지우기").click()
        s = llm_state()
        check(s["bar"] == "" and s["llm"] == [] and s["f"]["E14"] == "=E12*10%", "제안 지우기 → 제안만 없어지고 적용한 수식은 그대로")
        page.locator(W).screenshot(path=str(OUT / "05_llm_done.png"))
        errs = [x for x in logs if "favicon" not in x]
        check(not errs, f"콘솔 오류 0 — {errs[:3]}")
        b.close()
    print("FAILS", len(FAILS))
    for x in FAILS:
        print("  -", x)
    sys.exit(1 if FAILS else 0)


main()

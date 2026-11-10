"""웹 쪽 상자의 표 행 높이 ↔ 한글 PDF 그 쪽의 표 행 높이(괘선 사이) 대조 — 「웹 표가 한글보다 길다」 원인 계측용(spec_hwpx_웹편집 ④).

python -X utf8 tools/measure_table_rows.py <한 쪽씩 찍은 PDF 경로> [쪽 번호=3] [예제 이름=연구개발계획서_양식.hwpx]
서버(8114)가 떠 있어야 한다. 쪽마다: 웹 상자 높이/용지, 첫 표의 행별 높이·줄 수, PDF 그 쪽 괘선으로 나눈 행별 높이·줄 수를 차례로 짝지어 보이고,
차이를 「줄 바뀜이 더 많은 행」과 「나머지(줄 높이 모형·괘선 두께)」로 가른다. 웹 열 폭을 hwpx 칸 폭 누적값으로 바꿔 다시 잰 값도 같이(열 폭 추정 영향).
짝은 차례대로 1:1 — 칸 안에 표가 든 행은 PDF 괘선이 여러 행으로 나뉘어 그 행부터 짝이 어긋난다(요약문 표 마지막 「활용계획」 행 — 그 앞 행까지 보라)."""
import collections
import os
import json
import sys
import time
import urllib.request

import fitz
from playwright.sync_api import sync_playwright

URL = os.environ.get("NFM_URL", "http://127.0.0.1:8114")  # 임시 서버로 재려면 env NFM_URL
PDF = sys.argv[1]
PAGE = int(sys.argv[2]) if len(sys.argv) > 2 else 3
SAMPLE = sys.argv[3] if len(sys.argv) > 3 else "연구개발계획서_양식.hwpx"
MM = 25.4 / 72


def pdf_rows(path, page):
    """PDF 쪽의 가로·세로 괘선을 모아 행·열 경계를 만들고 글 줄을 칸에 넣는다 → [{top, h, cells: [{n, size, pitch, text}]}], 열 경계(mm)."""
    pg = fitz.open(path)[page - 1]
    hs, vs = [], []
    for d in pg.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 0.3:
                    hs.append(round((a.y + b.y) / 2, 1))
                elif abs(a.x - b.x) < 0.3:
                    vs.append(round((a.x + b.x) / 2, 1))
            elif it[0] == "re":
                r = it[1]
                if r.height < 1.5:
                    hs.append(round((r.y0 + r.y1) / 2, 1))
                elif r.width < 1.5:
                    vs.append(round((r.x0 + r.x1) / 2, 1))
                else:
                    hs += [round(r.y0, 1), round(r.y1, 1)]
                    vs += [round(r.x0, 1), round(r.x1, 1)]

    def cluster(vals, tol=0.8):
        out = []
        for v in sorted(vals):
            if out and v - out[-1][-1] <= tol:
                out[-1].append(v)
            else:
                out.append([v])
        return [sum(c) / len(c) for c in out]

    ys, xs = cluster(hs), cluster(vs)

    def band(v, bounds):
        for k in range(len(bounds) - 1):
            if bounds[k] <= v < bounds[k + 1]:
                return k
        return -1

    cells = collections.defaultdict(list)
    for blk in pg.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        for ln in blk.get("lines") or []:
            txt = "".join(ch["c"] for s in ln["spans"] for ch in s["chars"])
            if not txt.strip():
                continue
            x0, y0, x1, y1 = ln["bbox"]
            cells[(band((y0 + y1) / 2, ys), band(x0 + 0.5, xs))].append({"y": y0, "text": txt.strip(), "size": round(ln["spans"][0]["size"], 1)})
    rows = []
    for r in range(len(ys) - 1):
        cs = []
        for (rr, c), ls in sorted(cells.items()):
            if rr != r:
                continue
            ls.sort(key=lambda l: l["y"])
            pitch = [(ls[k + 1]["y"] - ls[k]["y"]) * MM for k in range(len(ls) - 1)]
            cs.append({"n": len(ls), "size": ls[0]["size"], "pitch": round(sum(pitch) / len(pitch), 2) if pitch else 0, "text": ls[0]["text"][:16]})
        rows.append({"top": round(ys[r] * MM, 1), "h": round((ys[r + 1] - ys[r]) * MM, 2), "cells": cs})
    return rows, [round(x * MM, 1) for x in xs]


def col_bounds(tb):
    """hwpx 칸 폭을 행마다 왼쪽부터 더해 열 폭을 만든다(한글은 칸을 제 폭대로 놓는다 — 괘선 자리와 일치). 모르는 열은 None."""
    n = tb["nCols"]
    b, occ = {0: 0.0}, {}
    for c in tb["cells"]:
        for rr in range(c["row"], c["row"] + c["rowSpan"]):
            for cc in range(c["col"], c["col"] + c["colSpan"]):
                occ[(rr, cc)] = c
    for _ in range(4):
        for r in range(tb["nRows"]):
            col = 0
            while col < n:
                c = occ.get((r, col))
                if not c:
                    break
                end = c["col"] + c["colSpan"]
                if c["col"] in b and end not in b and c.get("widthMm"):
                    b[end] = round(b[c["col"]] + c["widthMm"], 2)
                col = end
    bs = [b.get(k) for k in range(n + 1)]
    return [round(bs[k + 1] - bs[k], 2) if bs[k] is not None and bs[k + 1] is not None else None for k in range(n)]


WEB_JS = """([n, widths]) => {
  const PX = 96 / 25.4, mm = (v) => Math.round(v / PX * 100) / 100;
  const sheet = document.querySelector(`.sheet[data-page="${n}"]`), paper = +sheet.style.minHeight.replace('mm', '');
  const t = sheet.querySelector('table.tbl');
  const rows = () => [...t.rows].map((tr) => ({ h: mm(tr.getBoundingClientRect().height),
    lines: Math.max(0, ...[...tr.querySelectorAll('.para')].map((p) => Math.round(p.getBoundingClientRect().height / parseFloat(getComputedStyle(p).lineHeight)))),
    text: (tr.querySelector('.para') || {}).textContent || '' }));
  const out = { paper, sheetH: mm(sheet.offsetHeight), firstPara: (t.querySelector('.para') || {}).dataset ? t.querySelector('.para').dataset.id : null, rows: rows() };
  if (widths) {
    for (const tt of sheet.querySelectorAll('table.tbl')) {
      if (tt.closest('td')) continue;
      const cols = tt.querySelectorAll(':scope > colgroup > col');
      if (cols.length !== widths.length) continue;
      cols.forEach((c, i) => { if (widths[i] != null) c.style.width = widths[i] + 'mm'; });
    }
    out.fixed = { sheetH: mm(sheet.offsetHeight), rows: rows() };
  }
  return out;
}"""


def tables(bs):
    for x in bs:
        if x.get("type") == "table":
            yield x
        for c in x.get("cells", []):
            yield from tables(c.get("blocks", []))


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 1200})
        pg.goto(URL)
        pg.wait_for_selector(".sample", state="attached")
        # 2026-11-10 시작 화면 개편 뒤 예제 단추는 접힌 <details id=sampleSection> 안 — 펼친 뒤 aria-label 로 누른다
        pg.evaluate("() => { const d = document.getElementById('sampleSection'); if (d) { d.hidden = false; d.open = true; } }")
        pg.click(f".sample[aria-label*='{SAMPLE}']")
        pg.wait_for_function("document.querySelector('.sheet .para') != null", timeout=240000)  # 첫 그리기(7천 문단)가 30초 넘게 걸릴 때가 있다
        for _ in range(600):
            if "run" not in (pg.get_attribute("#summary", "class") or "") and pg.inner_text("#summary").strip():
                break
            time.sleep(0.5)
        pg.evaluate("setZoom(1)")
        pg.wait_for_timeout(500)
        doc_id = pg.evaluate("state.id")
        first = pg.evaluate(WEB_JS, [PAGE, None])
        # 첫 표의 hwpx 칸 폭 → 열 폭(열 폭 추정 영향을 보려고): 첫 문단 id 를 품은 표
        doc = json.load(urllib.request.urlopen(f"{URL}/api/docs/{doc_id}"))
        tb = next((t for t in tables(doc["blocks"]) if first["firstPara"] and any(
            any(bb.get("id") == first["firstPara"] for bb in c.get("blocks", [])) for c in t["cells"])), None)
        widths = col_bounds(tb) if tb else None
        web = pg.evaluate(WEB_JS, [PAGE, widths])
        b.close()
    prow, xs = pdf_rows(PDF, PAGE)
    print(f"{PAGE}쪽 — 웹 상자 {web['sheetH']}mm = 용지 {web['sheetH'] / web['paper']:.3f}배; PDF 표 괘선 행 {len(prow)}개, 웹 첫 표 행 {len(web['rows'])}개")
    if widths:
        print(f"hwpx 칸 폭 누적 열 폭(mm): {widths}")
    print(" 웹행  웹높이 줄  |  PDF행 PDF높이 줄  |  차이     글")
    # 차례로 짝짓기 — 웹 제목 행(괘선 없는 행)은 PDF 에 없을 수 있어 글이 맞는 자리부터
    wi = next((i for i, r in enumerate(web["rows"]) if prow and prow[0]["cells"] and r["text"].strip()[:4] == prow[0]["cells"][0]["text"][:4]), 0)
    tot_w = tot_p = wrap = 0.0
    for k in range(min(len(web["rows"]) - wi, len(prow))):
        w, pr = web["rows"][wi + k], prow[k]
        pl = max([c["n"] for c in pr["cells"]] or [0])
        d = w["h"] - pr["h"]
        tot_w += w["h"]
        tot_p += pr["h"]
        more = w["lines"] > pl
        if more:
            wrap += d
        print(f" {wi + k:3d}  {w['h']:6.2f} {w['lines']:2d}  |  {k:3d}  {pr['h']:6.2f} {pl:2d}  | {d:+6.2f} {'줄↑' if more else '   '} {w['text'].strip()[:18]!r}")
    print(f"합계 웹 {tot_w:.2f} / PDF {tot_p:.2f} / 차이 {tot_w - tot_p:+.2f} — 줄 바뀜이 더 많은 행 {wrap:+.2f}, 나머지 {tot_w - tot_p - wrap:+.2f}")
    if web.get("fixed"):
        f = web["fixed"]
        tw = sum(r["h"] for r in f["rows"][wi:wi + len(prow)])
        print(f"열 폭을 hwpx 칸 폭 누적값으로 바꾸면: 웹 상자 {f['sheetH']}mm = 용지 {f['sheetH'] / web['paper']:.3f}배, 표 행 합 {tw:.2f}(PDF 와 {tw - tot_p:+.2f}), "
              f"줄 수 " + " ".join(str(r["lines"]) for r in f["rows"][wi:wi + len(prow)]))


if __name__ == "__main__":
    main()

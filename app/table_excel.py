"""표 엑셀화(spec_헤딩_추출 ② §14) — **지금 문서의 표 하나**(또는 끌어 고른 칸 범위)만 읽어 수식 자리를 판정하고, 엑셀식 보기의 격자를 .xlsx 로 쓴다.

사용자 2026-11-10 "엑셀로 만들어 달라는건 수식이 들어가야할 위치를 판단해서 엑셀수식을 만들어 달라는 거야. 숫자가 들어가야할 부분 그리고 원문이랑 값이
다른 부분은 표기 … 테이블 일부 셀을 드래그 해서 엑셀 마크를 누르면 그 부분만 엑셀 수식화".

- **판정**(`judge`): 3단계(문서 전체 1단계 결과가 입력 — 문서를 고치면 낡는다)를 기다리지 않고, 그 표의 hp:p 만 1단계와 같은 규칙으로 레코드로 만든다(`records` —
  앞머리 규칙 kind·굵게·칸 음영·그릇 사슬). 그 위에 3단계 스크립트 초안(`heading_tables.collect`·`draft`·`finish_band` — LLM 없음)과 §9 표 의미
  (`heading_calc.annotate` — 구분 헤더·합계/비율/코드 식·검증)를 그대로 돌린다. 범위가 있으면 그 범위를 **한 표로 잘라** 판정하고(좌표는 표 기준으로 되돌림),
  잘라서 수식이 하나도 안 나오면(헤더 없이 값만 고른 경우) 표 전체로 판정해 범위 안 칸의 수식만 쓴다(`scope` "range" | "table").
- **숫자 칸**(`input`): 수식 칸이 아닌 필드 중 ① 어느 수식의 피연산자이거나 ② 글이 수·「-」·숫자 자리표시(「0,000,000」)인 칸 — 사람이 숫자를 넣을 자리.
- **.xlsx**(`grid_workbook`): 화면 격자 그대로(사용자 수식·정렬·고친 값 포함) — 범위면 범위 왼쪽 위가 A1, 범위 밖을 가리키는 수식은 값으로 두고 메모.
"""
import io
import re

from app import heading_calc as HC
from app import heading_extract as E
from app import heading_rules as R
from app import heading_tables as HT

MAX_CELLS = 4000          # 이보다 큰 표(칸 수)는 판정하지 않는다(일정표 691칸 정도가 문서 최대)
_REF = re.compile(r"(\$?)([A-Z]{1,3})(\$?)(\d+)(?![\d(])")
_FIELD_KEYS = ("num", "pct", "dec", "dash", "placeholder")


# ---- 표 하나의 1단계 꼴 레코드 ---------------------------------------------------------------------------------------

def records(doc, tid, store=None, doc_key=None):
    """표 tid 안의 hp:p 전부 → {"paras": [레코드…]} — heading_tables.collect 가 읽는 키만(id·n·path·kind·text·blank·char.text).
    그릇 사슬은 표부터(바깥 본문은 뺌). 표가 아니면 None."""
    tbl = doc._ids.get(tid)
    if tbl is None or tbl.tag != E.TBL:
        return None
    block = doc.table_block(tid)
    blk = E._index_blocks([block]) if block else {}
    st = store if store is not None else R.load()
    rules = R.active(st, (), doc_key=doc_key)
    run = R._Run()
    root = tbl.getparent()  # hp:run — 사슬이 표에서 시작
    keys, ccache, recs = {}, {}, []
    for n, p in enumerate(tbl.iter(E.P)):
        bid = doc._rev.get(p)
        b = blk.get(bid) if bid else None
        para = b if b is not None and b.get("type") == "paragraph" else None
        text = para["text"] if para is not None else doc._text(p)
        chain = E._container_path(doc, p, root, blk, keys)
        for c in chain:
            c.pop("_host", None)
        head = R.classify(text, rules, run)
        kind = head["kind"]
        if kind == "empty" and any(E._local(o.tag) in E.OBJECT_TAGS for r in p.iterchildren(E.RUN) for o in r):
            kind = "object"
        ranges = E.run_ranges(doc, p)
        first = doc._char_id(p)
        rest_at = len(text) - len(head["rest"]) if head["rest"] else None
        cid = E._cid_at(ranges, rest_at, first) if rest_at is not None and rest_at < len(text) else first
        recs.append({"id": bid if para is not None else f"x{tid}.{n}", "n": n, "path": chain, "kind": kind, "text": text,
                     "blank": head["blank"], "char": {"text": E._char(doc, cid, ccache)}})
    return {"paras": recs}


# ---- 판정 ------------------------------------------------------------------------------------------------------

def _crop(tb, rng):
    """범위 안에 통째로 든 칸만, 좌표를 범위 왼쪽 위 기준으로."""
    r0, c0, r1, c1 = rng
    cells = []
    for x in tb["cells"]:
        if r0 <= x["row"] and x["row"] + x["rs"] - 1 <= r1 and c0 <= x["col"] and x["col"] + x["cs"] - 1 <= c1:
            y = dict(x)
            y["row"] -= r0
            y["col"] -= c0
            cells.append(y)
    return {**tb, "cells": cells, "rows": r1 - r0 + 1, "cols": c1 - c0 + 1}


def _analyze(tb, roles=None):
    """3단계 스크립트 초안 + §9 표 의미 → (띠 목록, 표 의미). tb 의 칸에 role·sub·경로·num·formulas 가 적힌다.
    roles = 사용자 헤더 지정 {칸 id: rowhead | colhead | field}(spec_owpml_편집 ② §5-4) — 초안 역할 위에 덮은 뒤 헤더 트리·수식을 만든다."""
    bs, occ = HT.draft(tb)
    for x in tb["cells"]:
        if roles and roles.get(x["id"]) in ("rowhead", "colhead", "field"):
            x["role"], x["reason"] = roles[x["id"]], "사용자 지정"
    for x in tb["cells"]:
        x["sub"] = next((b["id"] for b in bs if b["rows"][0] <= x["row"] < b["rows"][1] and b["cols"][0] <= x["col"] < b["cols"][1]), None)
    subs = [HT.finish_band(tb, occ, b) for b in bs]
    sem = HC.annotate(tb, subs, None)
    return subs, sem


def shift_formula(formula, dr, dc):
    """수식 안 A1 주소를 (dr 행, dc 열) 옮긴다 — 0 보다 작아지면 None(범위 밖)."""
    bad = []

    def sub(m):
        col = 0
        for ch in m.group(2):
            col = col * 26 + ord(ch) - 64
        r, c = int(m.group(4)) - 1 + dr, col - 1 + dc
        if r < 0 or c < 0:
            bad.append(m.group(0))
            return m.group(0)
        return f"{m.group(1)}{HC.col_letter(c)}{m.group(3)}{r + 1}"
    out = _REF.sub(sub, formula or "")
    return None if bad else out


def _cell_out(x):
    out = {k: x.get(k) for k in ("id", "row", "col", "rs", "cs", "role", "sub", "basis", "basisKind", "rowPath", "colPath", "formulas") if x.get(k) is not None}
    out["text"] = (x.get("textFull") or "")[:80]
    out["paras"] = list(x.get("paras") or [])
    for k in _FIELD_KEYS:
        if x.get(k) is not None and x.get(k) is not False:
            out[k] = x[k]
    return out


def judge(doc, tid, rng=None, store=None, doc_key=None, roles=None):
    """표(또는 범위)의 수식 판정 → {table, rows, cols, range, scope, cells[], formulas[], subtables[], unit, calc, counts}.
    좌표·A1 주소는 늘 표 기준. 표가 아니면 None, 너무 크면 ValueError. roles = 사용자 헤더 지정(`_analyze`)."""
    stage1 = records(doc, tid, store, doc_key)
    if stage1 is None:
        return None
    tb = next((t for t in HT.collect(stage1) if t["id"] == tid), None)
    if tb is None:  # 1칸 표(글상자) — 표로 세지 않는다
        return {"table": tid, "rows": 1, "cols": 1, "range": None, "scope": "table", "cells": [], "formulas": [], "subtables": [], "unit": None,
                "calc": {"is": False, "formulas": 0}, "counts": {"cells": 0, "formulas": 0, "input": 0}, "note": "1칸 표(글상자)는 엑셀식으로 판정하지 않습니다"}
    if len(tb["cells"]) > MAX_CELLS:
        raise ValueError(f"표가 너무 큽니다(칸 {len(tb['cells'])} > {MAX_CELLS})")
    rows, cols = tb["rows"], tb["cols"]
    box = None
    if rng:
        r0, c0 = max(0, int(rng["r0"])), max(0, int(rng["c0"]))
        r1, c1 = min(rows - 1, int(rng["r1"])), min(cols - 1, int(rng["c1"]))
        if r0 <= r1 and c0 <= c1 and (r0, c0, r1, c1) != (0, 0, rows - 1, cols - 1):
            box = (r0, c0, r1, c1)
    scope = "table"
    if box:
        part = _crop(tb, box)
        subs, sem = _analyze(part, roles)
        scope = "range"
        if not sem["formulas"]:  # 헤더 없이 값만 골랐다 — 표 전체 맥락으로 판정해 범위 안 칸의 수식만
            whole = next(t for t in HT.collect(stage1) if t["id"] == tid)
            subs_w, sem_w = _analyze(whole, roles)
            inside = lambda x: box[0] <= x["row"] and x["row"] + x["rs"] - 1 <= box[2] and box[1] <= x["col"] and x["col"] + x["cs"] - 1 <= box[3]  # noqa: E731
            ids = {x["id"] for x in whole["cells"] if inside(x)}
            if any(f["cell"] in ids for f in sem_w["formulas"]):
                scope = "table"
                part = {**whole, "cells": [x for x in whole["cells"] if x["id"] in ids]}
                subs, sem = subs_w, {**sem_w, "formulas": [f for f in sem_w["formulas"] if f["cell"] in ids]}
                box_shift = (0, 0)
            else:
                box_shift = (box[0], box[1])
        else:
            box_shift = (box[0], box[1])
        cells = part["cells"]
    else:
        subs, sem = _analyze(tb, roles)
        cells, box_shift = tb["cells"], (0, 0)
    dr, dc = box_shift
    by_id = {x["id"]: x for x in cells}
    formulas = []
    for f in sem["formulas"]:
        g = dict(f)
        if dr or dc:
            g["formula"] = shift_formula(f["formula"], dr, dc) or f["formula"]
            x = by_id.get(f["cell"])
            g["ref"] = f"{HC.col_letter(x['col'] + dc)}{x['row'] + dr + 1}" if x else f["ref"]
        g["refs"] = [HC.ref({"row": by_id[o]["row"] + dr, "col": by_id[o]["col"] + dc}) for o in f.get("operands") or [] if o in by_id]
        formulas.append(g)
    targets = {f["cell"] for f in formulas if f.get("excel")}
    operands = {o for f in formulas for o in f.get("operands") or []}
    out_cells = []
    n_input = 0
    for x in cells:
        c = _cell_out(x)
        c["row"] += dr
        c["col"] += dc
        if x.get("role") == "field" and x["id"] not in targets and (x["id"] in operands or x.get("num") is not None or x.get("placeholder")):
            c["input"] = True
            n_input += 1
        out_cells.append(c)
    out_subs = [{"id": s["id"], "rows": [s["rows"][0] + dr, s["rows"][1] + dr], "cols": [s["cols"][0] + dc, s["cols"][1] + dc], "kind": s["kind"],
                 "headerRows": s["headerRows"], "headerCols": s["headerCols"], "calc": s.get("calc")} for s in subs]
    status = {}
    for f in formulas:
        status[f["status"]] = status.get(f["status"], 0) + 1
    return {"table": tid, "rows": rows, "cols": cols, "range": ({"r0": box[0], "c0": box[1], "r1": box[2], "c1": box[3]} if box else None), "scope": scope,
            "cells": out_cells, "formulas": formulas, "subtables": out_subs, "unit": sem.get("unit"), "calc": sem.get("calc"),
            "counts": {"cells": len(out_cells), "formulas": len(formulas), "excel": len(targets), "input": n_input, **status}}


# ---- 표 앞뒤 글(LLM 수식 판정의 자료 — spec ② §14 「LLM 수식 판정」) ---------------------------------------------------------

def context(doc, tid, before=3, after=8, text_max=300):
    """표 바로 앞·뒤 문단 글 {"before": […], "after": […]} — 표 제목·단위 줄과 표 아래 각주(「1) 총 인건비 : 내부인건비 + …」). 표를 품은 문단과 **같은 그릇**(구역·칸)의 이웃 문단만,
    빈 문단은 건너뛰고 다른 표·그림을 품은 문단에서 멈춘다. 글이 나온 뒤 빈 문단이 둘 이어져도 멈춘다(각주 묶음이 끝난 것). 표가 아니면 둘 다 빈 목록."""
    out = {"before": [], "after": []}
    host = doc._ids.get(tid)
    if host is None or host.tag != E.TBL:
        return out
    while host is not None and host.tag != E.P:
        host = host.getparent()
    if host is None:
        return out

    def walk(preceding, limit):
        got, gap = [], 0
        for p in host.itersiblings(E.P, preceding=preceding):
            if any(E._local(o.tag) in E.OBJECT_TAGS for r in p.iterchildren(E.RUN) for o in r):
                break
            text = " ".join(doc._text(p).replace(R.BR, " ").split())
            if not text:
                gap += 1
                if gap >= 2 and got:
                    break
                continue
            gap = 0
            got.append(text[:text_max])
            if len(got) >= limit:
                break
        return got
    out["before"] = walk(True, before)[::-1]
    out["after"] = walk(False, after)
    return out


# ---- 화면 격자 → .xlsx ------------------------------------------------------------------------------------------

_INPUT_FILL = "FFF2CC"     # 숫자 칸(엑셀의 「입력」 셀 스타일과 같은 연노랑)
_BAD_FILL = "F8CBAD"       # 불일치
_FILL_FILL = "FFE699"      # 문서 칸이 빈 수식 칸(미기입)
_ORIG_FILL = "FCE4D6"      # 원문(올린 원본)과 다른 칸
_ST_KO = {"ok": "일치", "bad": "불일치", "fill": "미기입(문서 칸 빈)", "blank": "미검증(피연산자 빈 칸)", "err": "오류"}


def grid_workbook(grid, doc_name=""):
    """엑셀식 보기 격자 {table, range?, rows, cols, unit?, cells:[{ref,row,col,rs,cs,role?,value?,num?,pct?,formula?,status?,calc?,doc?,input?,orig?,origText?}]}
    → .xlsx 바이트. 범위면 범위 왼쪽 위가 A1. 시트 「표」(병합·역할 색·숫자 칸 연노랑·수식 칸 엑셀 수식) · 「수식」(주소·수식·계산값·문서 값·상태) · 「정보」."""
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    rng = grid.get("range") or None
    r0, c0 = (int(rng["r0"]), int(rng["c0"])) if rng else (0, 0)
    wb = Workbook()
    ws = wb.active
    ws.title = "표"
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    rows_f = []
    for x in grid.get("cells") or []:
        r, c = int(x["row"]) - r0 + 1, int(x["col"]) - c0 + 1
        if r < 1 or c < 1:
            continue
        cell = ws.cell(row=r, column=c)
        note = []
        f = x.get("formula")
        if f:
            g = shift_formula(f, -r0, -c0) if (r0 or c0) else f
            if g:
                cell.value = g
            else:
                cell.value = x.get("calc") if isinstance(x.get("calc"), (int, float)) else x.get("value")
                note.append(f"수식 {f} 은 범위 밖 칸을 가리켜 값으로 둠")
            st = x.get("status") or ""
            note.append(f"문서 값: {x.get('doc') or '(빈 칸)'} · {_ST_KO.get(st, st) or '계산'}" + (f" · 계산값 {x.get('calc')}" if x.get("calc") is not None else ""))
            fill = {"bad": _BAD_FILL, "fill": _FILL_FILL}.get(st)
            if fill:
                cell.fill = PatternFill("solid", start_color=fill)
            rows_f.append([HC.col_letter(c - 1) + str(r), g or f, x.get("calc"), x.get("doc"), _ST_KO.get(st, st), x.get("ref")])
        elif x.get("num") is not None:
            v = x["num"]
            cell.value = int(v) if float(v).is_integer() else v
            if x.get("pct"):
                cell.number_format = '0.0"%"' if not float(v).is_integer() else '0"%"'
            elif abs(v) >= 1000 or x.get("grouped"):
                cell.number_format = "#,##0" if float(v).is_integer() else "#,##0.0#"
        else:
            cell.value = x.get("value") or None
        if x.get("role") in HC._FILL:
            cell.fill = PatternFill("solid", start_color=HC._FILL[x["role"]])
            cell.font = Font(bold=True)
        elif x.get("input") and not f:
            cell.fill = PatternFill("solid", start_color=_INPUT_FILL)
            note.append("숫자 칸(넣을 자리)")
        if x.get("orig"):
            if not f and not x.get("input") and x.get("role") not in HC._FILL:
                cell.fill = PatternFill("solid", start_color=_ORIG_FILL)
            note.append(f"원문: {x.get('origText') or '(빈 칸)'}")
        if note:
            cell.comment = Comment("\n".join(note), "NewFileManager")
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="right" if (f or x.get("num") is not None) else None)
        cell.border = border
        rs, cs = int(x.get("rs") or 1), int(x.get("cs") or 1)
        if rs > 1 or cs > 1:
            ws.merge_cells(start_row=r, start_column=c, end_row=r + rs - 1, end_column=c + cs - 1)
    ncols = (int(rng["c1"]) - c0 + 1) if rng else int(grid.get("cols") or 0)
    for k in range(1, ncols + 1):
        ws.column_dimensions[HC.col_letter(k - 1)].width = 11
    v = wb.create_sheet("수식")
    v.append(["주소", "엑셀 수식", "계산값", "문서 값", "상태", "표 주소"])
    for row in rows_f:
        v.append(row)
    for col, w in zip("ABCDEF", (8, 34, 14, 18, 18, 8)):
        v.column_dimensions[col].width = w
    v.freeze_panes = "A2"
    info = wb.create_sheet("정보")
    info.append(["문서", doc_name])
    info.append(["표", grid.get("table"), f"{grid.get('rows')}×{grid.get('cols')}"])
    if rng:
        info.append(["범위", f"{HC.col_letter(c0)}{r0 + 1}:{HC.col_letter(int(rng['c1']))}{int(rng['r1']) + 1}", "(이 시트의 A1 = 범위 왼쪽 위)"])
    if grid.get("unit"):
        info.append(["단위", grid["unit"]])
    info.append([])
    info.append(["색", "뜻"])
    for color, what in ((_INPUT_FILL, "숫자 칸 — 숫자를 넣을 자리(수식의 피연산자·수 값)"), (_BAD_FILL, "불일치 — 수식 계산값과 문서 값이 다름"),
                        (_FILL_FILL, "미기입 — 수식 칸인데 문서 칸이 빔"), (_ORIG_FILL, "원문과 다름 — 올린 원본에서 고친 칸(메모에 원문)")):
        info.append(["", what])
        info.cell(row=info.max_row, column=1).fill = PatternFill("solid", start_color=color)
    info.column_dimensions["A"].width = 10
    info.column_dimensions["B"].width = 60
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

"""병합 — 월별 일정 표를 스크립트로(spec_병합 ② §5-7, 2026-11-22 사용자 「해당년도에 해당하는 부분의 추진일정을 갖어와야지. 기존에는 계획만 있지만 연차보고서 넘어올때는 동일하게 개발실적에
맞추어서 매핑되어야지. 이것도 2-1 기술개발 추진일정 테이블에 스크립트로 넣고 … 보니깐 년차별로 이미 테이블이 존재함」): 연차보고서 「2-1. 기술개발 추진 일정」 처럼 **월 열(1 … 12)에 선으로 일정을 긋는
목적 표**를, 계획서의 **같은 차년도 월별 일정 표들**에서 채운다. LLM 을 부르지 않는다 — 두 서식의 꼴이 같다(일련번호 · 개발 내용 · 반 달 칸 24열 · 항목마다 3행 · 계획 = 항목 안 첫 경계의 점선).

왜 따로인가: 계획서는 그 차년도의 일정 표를 **기관마다 하나씩** 둔다(「o 1차년도 › [주관연구개발기관(…)] 표 › [공동연구개발기관1(…)] 표 …」) — 표 짝(merge_fixed) · 표 대응(merge_table_map)은 목적 표 하나에
원본 표 **하나**를 잇는 길이라 여러 기관의 표를 한 표에 모으지 못했고(실제 작성본: LLM 검토의 후보가 전 차년도 요약 표 하나뿐이라 비움), 표 대응은 원본의 일정을 칸의 **채움**으로만 읽어 점선으로 그은 일정을 못 읽는다.

- 목적 일정 표 = 월 머리 줄(1 … 12 가 잇달아 놓인 머리 행)이 있고, 자료 칸의 항목 안 경계에 특수 선이 있으며 표 뒤 범례가 그 선을 「…계획」 이라 부르는 표(「당초계획」) — 어느 차년도의 표인지 알아야 한다
  (`merge_fixed._ctx` — 「해당연도」 절 = 당해 차년도).
- 원본 일정 표 = 월 머리 줄이 있고 그 차년도가 목적 표와 같은 표(월 머리 위의 「1단계-1차년도(9개월)」 · 없으면 표의 맥락) **전부**(문서 차례 — 기관마다의 표). 전 차년도를 한 줄씩 요약한 표는 머리가 월이 아니라 대상이 아니다.
  「넣을 구성 선택」(merge_take)에서 고르지 않은 기관 · 차년도의 표는 뺀다.
- 항목 = 가장 왼쪽 글 열(일련번호)의 칸 하나가 걸친 행들. 원본 항목을 문서 차례로 늘어놓아, **이름이 이미 있는 항목은 건드리지 않고**(사람이 고친 선 · 달성도를 덮지 않는다) 없는 항목만
  목적 표의 빈 항목 · 서식 예시 항목(등록된 빈 양식으로 올린 원본 그대로인 항목 — `orig`)에 차례로 넣고, 모자라면 마지막 빈 항목을 본떠 그 아래에 늘린다.
- 넣는 것: 일련번호(원본 표가 여럿이면 1부터 이어 센다) · 개발 내용(원본 표가 여러 기관의 것이면 끝에 「(기관 이름)」 — 계획서의 전체 일정 표가 쓰는 꼴) · 월 칸의 **계획 선**(원본에서 그 반 달 칸에 일정이 그어져 있으면 —
  항목 안 경계의 특수 선이나 칸 채움) · **실적 선도 계획과 같게**(`RESULT_SAME` — 사용자 「동일하게 개발실적에 맞추어서」: 그 뒤 기관이 실제대로 고친다). 「달성도(%)」 처럼 원본에 없는 열은 안 채운다(예시 값은 지운다).
- 안 쓴 서식 예시 항목은 글과 선을 지운다(실제 항목 옆에 예시가 남지 않게).
`plan(T, F, orig=None, take=None)` = 넣기 계획(문서를 안 고침) → {"tables", "fills", "grows", "wipes", "owned"(이 길이 맡은 목적 표 id — 표 짝 · 표 대응 · 빈 자리 검토는 그 표를 안 본다), "skipped", "counts", "todo"}.
`apply(to_doc, from_doc, plan)` = 계획을 목적 문서에 → {"filled", "shaped", "lines", "rowsAdded", "cleared", "skipped"}. 다시 계획하면 넣은 항목은 이름이 있어 일 없음."""
import re
from collections import Counter

from app import merge_fixed as X
from app import merge_pairs as P
from app import merge_table_map as MM
from app import merge_tables as MT

RESULT_SAME = True   # 실적 쪽 선(「개발실적」)도 계획과 같게 긋는다(모듈 설명) — False 면 계획 선만 긋고 실적 선은 비운다(2026-11-12 의 「당초 계획 부분만」)
MONTHS_MIN, HEAD_ROWS = 6, 6   # 월 머리 줄로 보려면 잇달아 있어야 하는 달 수 · 머리 줄을 찾는 위쪽 행 수
_NUM = re.compile(r"\d{1,2}")
_SERIAL = re.compile(r"번호|순번|^no$", re.I)
_PLAN, _RESULT = re.compile(r"계획"), re.compile(r"실적")
_YEAR_LINE = re.compile(r"[^0-9A-Za-z가-힣]*(?:[oOㅇ]\s+)?[^0-9A-Za-z가-힣]*(?:\d+\s*단계\s*[-–~]?\s*)?\d+\s*차\s*년도[^0-9A-Za-z가-힣]*")   # 차년도 낱말뿐인 라벨 줄 「o 2차년도」 · 「[1단계-2차년도]」
_SECTION = re.compile(r"\d+(?:[-.]\d+)*[.)]\s*\S")   # 번호 붙은 절 제목 「2-3. 연구개발과제 수행일정 …」 — 차년도 라벨을 찾는 범위의 끝
WHY = ("occupied", "shape", "noSource")


def _key(text):
    return MM._bare(text).lower()


def read(S, tid):
    """표 하나 → 일정 표로 읽은 것 | None: {"v"(merge_table_map.view), "months"{달: [열 …]}, "top"(첫 자료 행), "year"(월 머리 위에 적힌 차년도 | None), "text"{머리 낱말: 열}(월 열이 아닌 열),
    "serial"(일련번호 열 | None), "items"[[행 …]]}. 월 머리 줄 = 위쪽 행 가운데 1 … 12 의 수가 열 차례로 MONTHS_MIN 개 넘게 잇달아 놓인 행."""
    v = MM.view(S, tid)
    if v is None:
        return None
    best = None
    for r in range(min(HEAD_ROWS, v["rows"])):
        cells = sorted((x for x in v["cells"] if x["r"] == r and _NUM.fullmatch(P._ws(x["text"])) and 1 <= int(P._ws(x["text"])) <= 12), key=lambda x: x["c"])
        run = [cells[0]] if cells else []
        for x in cells[1:]:
            run = [*run, x] if int(P._ws(x["text"])) == int(P._ws(run[-1]["text"])) + 1 and x["c"] == run[-1]["c"] + run[-1]["cs"] else [x]
            if len(run) >= MONTHS_MIN and (best is None or len(run) > len(best)):
                best = list(run)
    if best is None:
        return None
    months = {int(P._ws(x["text"])): list(range(x["c"], x["c"] + x["cs"])) for x in best}
    top = max(x["r"] + x["rs"] for x in best)
    mcols = {c for cs in months.values() for c in cs}
    over = v["at"].get((best[0]["r"] - 1, best[0]["c"])) if best[0]["r"] else None
    text = {}
    for c in range(v["cols"]):
        heads = [h for r in range(top) if (h := v["at"].get((r, c))) is not None]
        if c in mcols or not heads:
            continue
        word = _key(MM._head_word(heads[-1]["text"]))
        if word:
            text.setdefault(word, c)
    if not text or top >= v["rows"]:
        return None
    left = min(text.values())
    items, r = [], top
    while r < v["rows"]:
        x = v["at"].get((r, left))
        rows = list(range(x["r"], x["r"] + x["rs"])) if x is not None and x["r"] == r else [r]
        items.append(rows)
        r = rows[-1] + 1
    return {"v": v, "months": months, "top": top, "year": MM._year(over["text"], S["values"]) if over is not None else None, "text": text,
            "serial": next((c for w, c in text.items() if _SERIAL.search(w)), None), "items": items}


def _marks(S, sch):
    """목적 표의 표시(merge_table_map.marks 와 같은 뜻 — 항목은 `read` 가 가른 것으로: 3단계의 칸 역할에 기대지 않는다) → [{name, type, width, color, boundary, off}] — 월 칸의 항목 안 경계에 쓰인 특수 선마다."""
    v, cols = sch["v"], {c for cs in sch["months"].values() for c in cs}
    seen, base = {}, Counter()
    for rows in sch["items"]:
        for k in range(len(rows) - 1):
            for c in cols:
                up, down = v["at"].get((rows[k], c)), v["at"].get((rows[k + 1], c))
                for line in ((up or {}).get("bottom"), (down or {}).get("top")):
                    if MM._special(line):
                        seen.setdefault(MM._kind(line), Counter())[k] += 1
                    else:
                        base[(k, MM._kind(line))] += 1
    out = []
    for kind, where in seen.items():
        at = where.most_common(1)[0][0]
        offs = Counter({k[1]: n for k, n in base.items() if k[0] == at})
        off = offs.most_common(1)[0][0] if offs else None
        out.append({"name": MM._legend(S, v, kind) or kind[0], "type": kind[0], "width": kind[1], "color": kind[2], "boundary": at,
                    "off": {"type": off[0], "width": off[1], "color": off[2]} if off else dict(MM.OFF)})
    return sorted(out, key=lambda m: m["boundary"])


def _drawn(sch, rows, c):
    """원본 항목의 그 열(반 달 칸)에 일정이 그어져 있나 — 칸 채움, 또는 항목 **안** 경계의 특수 선(항목 바깥 테두리는 안 본다)."""
    v = sch["v"]
    for i, r in enumerate(rows):
        x = v["at"].get((r, c))
        if x is None:
            continue
        if x["fill"] or (i < len(rows) - 1 and MM._special(x["bottom"])) or (i > 0 and MM._special(x["top"])):
            return True
    return False


def _line(m):
    return {k: m[k] for k in ("type", "width", "color")}


def _free(sch, rows, marks, orig):
    """목적 항목을 채워도 되나 → "blank"(빈 항목 — 글이 없거나 순번 · 「···」 뿐이고 표시 선도 없음) | "example"(올린 빈 양식 그대로인 예시 항목) | None(사람 글 · 이미 넣은 항목)."""
    v = sch["v"]
    cells = [x for x in v["cells"] if MM._inside(x, rows)]
    cols = {c for cs in sch["months"].values() for c in cs}
    kinds = {(m["type"], m["width"], m["color"]) for m in marks}
    lined = any(MM._kind(x[e]) in kinds for x in cells if x["c"] in cols for e in ("top", "bottom") if MM._special(x[e]))
    if not lined and all(MM._slot(x["text"]) for x in cells):
        return "blank"
    if orig and cells and all(MM._original(x, orig) for x in cells):
        return "example"
    return None


def _near_year(S, tid):
    """표 **앞의 가장 가까운 차년도 라벨 줄**(「o 2차년도」 · 「[1단계-2차년도]」 — 차년도 낱말뿐인 짧은 줄)의 차년도 | None. 같은 형제 목록을 거슬러 올라가며 찾고, 번호 붙은 절 제목(「2-3. …」)을 만나면 멈춘다.
    차년도마다 기관 표가 되풀이되는 절에서 **그 표가 어느 차년도 묶음에 놓였나**를 문서 차례로 읽는다 — 실제 작성본(7기관 × 4차년도): 표 머리의 「1단계-N차년도」 는 앞 차년도의 표를 베껴 안 고친 것이 5개,
    표의 맥락(merge_fixed._ctx — 차년도 절의 범위)은 기관 절 넷이 한 해씩 밀려 있었다. 놓인 자리는 28개가 모두 맞았다."""
    seq = (S.get("where") or {}).get(tid) or ()
    k = next((i for i, b in enumerate(seq) if b["id"] == tid), None)
    for b in reversed(seq[:k] if k is not None else ()):
        if b.get("type") != "paragraph":
            continue
        text = P._ws(b.get("text") or "")
        if _YEAR_LINE.fullmatch(text):
            return MT._year_no(text, S["values"])
        if _SECTION.match(text):
            return None
    return None


def _sources(F, year, take):
    """그 차년도의 원본 일정 표들(문서 차례) → [{id, sch, org, title, note}] — 「넣을 구성 선택」 에서 고르지 않은 기관 · 차년도의 표는 뺀다.
    표의 차년도 = 표 앞의 차년도 라벨 줄(_near_year) → 없으면 월 머리 위에 적힌 차년도 → 없으면 표의 맥락. 라벨 줄과 표 머리가 다르면 놓인 자리를 따르고 note 에 적는다."""
    out = []
    for f in F["tables"]:
        if f["id"] not in F["idx"]:
            continue
        sch = read(F, f["id"])
        if sch is None:
            continue
        ctx = X._ctx(F, f)
        near = _near_year(F, f["id"])
        y = near if near is not None else sch["year"] if sch["year"] is not None else ctx["year"]
        if y != year or (take is not None and not take.ctx({"org": ctx["org"], "year": y})):
            continue
        note = f"표 머리에는 {sch['year']}차년도로 적혀 있음 — {y}차년도 묶음에 놓인 표라 {y}차년도로 읽음" if near is not None and sch["year"] is not None and sch["year"] != near else ""
        out.append({"id": f["id"], "sch": sch, "org": ctx["org"], "title": P._ws(X._title_of(F, f))[:P.TEXT_MAX], "note": note})
    return out


def _wanted(T, F, tsch, srcs):
    """넣을 항목(원본 차례) → [{name(목적 이름 칸에 쓸 글), key, cells[(목적 열, 글, 원본 칸 id | None)], marks{목적 열: 그어져 있나}, from(원본 표), row(원본 첫 행)}].
    열 짝 = 머리 낱말이 같은 글 열(일련번호 · 개발 내용 — 「달성도」 ↔ 「기간」 처럼 다른 낱말은 안 잇는다) · 같은 달의 월 열(반 달 칸은 자리대로 — 한쪽이 달마다 한 칸이면 그 칸을 같이 읽는다)."""
    orgs = {s["org"] for s in srcs}
    many, tag = len(srcs) > 1, len(orgs) > 1
    name_cols = [(w, c) for w, c in tsch["text"].items() if c != tsch["serial"] and not MM._RESULT.match(w)]
    out, n = [], 0
    for s in srcs:
        fs, fv = s["sch"], s["sch"]["v"]
        pairs = [(c, fs["text"][w]) for w, c in name_cols if w in fs["text"]]
        if not pairs:
            continue
        for rows in fs["items"]:
            texts = [(tc, fv["at"].get((rows[0], fc))) for tc, fc in pairs]
            if all(x is None or MT._empty(x["text"]) or MM._slot(x["text"]) for _, x in texts):
                continue   # 원본의 빈 항목(양식의 남은 행)
            n += 1
            cells = []
            for i, (tc, x) in enumerate(texts):
                text = (x["text"] or "").strip() if x is not None else ""
                if i == 0 and tag and s["org"] and text and _key(s["org"]) not in _key(text):
                    text = f"{text}\n({s['org']})"
                cells.append((tc, text, x["id"] if x is not None else None))
            if tsch["serial"] is not None:
                sx = fv["at"].get((rows[0], fs["serial"])) if fs["serial"] is not None else None
                cells.append((tsch["serial"], str(n) if many or sx is None else (sx["text"] or "").strip() or str(n), sx["id"] if sx is not None else None))
            marks = {}
            for month, tcols in tsch["months"].items():
                fcols = fs["months"].get(month) or ()
                for k, tc in enumerate(tcols):
                    marks[tc] = bool(fcols) and (_drawn(fs, rows, fcols[k]) if len(fcols) == len(tcols) else any(_drawn(fs, rows, fc) for fc in fcols))
            out.append({"name": cells[0][1], "key": _key(cells[0][1]), "cells": cells, "marks": marks, "from": s["id"], "row": rows[0]})
    return out


def plan(T, F, orig=None, take=None):
    """넣기 계획(모듈 설명) — 문서를 안 고친다. T·F = merge_fixed._side 꼴 · orig = 등록된 빈 양식으로 올린 원본의 칸(merge_api._orig) | None · take = merge_take.Allowed | None(전부)."""
    out = {"tables": [], "fills": [], "grows": [], "wipes": [], "owned": [], "skipped": []}
    for t in T["tables"]:
        if t["id"] not in T["idx"]:
            continue
        sch = read(T, t["id"])
        if sch is None:
            continue
        marks = _marks(T, sch)
        mk = next((m for m in marks if _PLAN.search(m["name"]) and not _RESULT.search(m["name"])), None)
        year = X._ctx(T, t)["year"]
        if mk is None or year is None:
            continue   # 계획 선이 없는 표 · 어느 차년도의 표인지 모르는 표 — 이 길의 표가 아니다
        srcs = _sources(F, year, take)
        want = _wanted(T, F, sch, srcs) if srcs else []
        if not want:
            continue   # 그 차년도의 원본 일정 표가 없다 — 다른 길(표 짝 · 빈 자리 검토)에 맡긴다
        rs = next((m for m in marks if _RESULT.search(m["name"])), None)
        v, tid = sch["v"], t["id"]
        row = {"to": tid, "title": P._ws(X._title_of(T, t))[:P.TEXT_MAX], "year": year, "plan": mk["name"], "result": rs["name"] if rs and RESULT_SAME else "",
               "sources": [{"from": s["id"], "org": s["org"], "title": s["title"], "items": sum(w["from"] == s["id"] for w in want), "note": s["note"]} for s in srcs],
               "items": len(want), "done": 0, "write": 0, "grow": 0, "cleared": 0, "skipped": 0}
        out["tables"].append(row)
        out["owned"].append(tid)
        name_col = want[0]["cells"][0][0]
        state = [(rows, _free(sch, rows, marks, orig)) for rows in sch["items"]]
        have = Counter(_key((v["at"].get((rows[0], name_col)) or {}).get("text") or "") for rows, st in state if st is None)
        todo = []
        for w in want:
            if have[w["key"]] > 0:
                have[w["key"]] -= 1
                row["done"] += 1
            else:
                todo.append(w)
        slots = [rows for rows, st in state if st]
        blanks = [rows for rows, st in state if st == "blank"]

        def edges(rows, w):   # 그 항목의 선 → [(행 차례, 열, 가장자리, 선)] — 계획 선은 원본대로(있음 · 없음 모두), 실적 선은 계획과 같게(RESULT_SAME) 아니면 모두 없음
            ops = []
            for m in (mk, rs):
                if m is None or m["boundary"] + 1 >= len(rows):
                    continue
                for c, has in w["marks"].items():
                    line = _line(m) if has and (m is mk or RESULT_SAME) else m["off"]
                    ops += [(m["boundary"], c, "bottom", line), (m["boundary"] + 1, c, "top", line)]
            return ops
        for rows, w in zip(slots, todo):
            cells, used = [], set()
            for c, text, frm in w["cells"]:
                x = v["at"].get((rows[0], c))
                if x is None or x["id"] in used:
                    continue
                used.add(x["id"])
                if P._ws(x["text"]) != P._ws(text):
                    cells.append({"to": x["id"], "text": text, "from": frm, "was": x["text"]})
            clears = [{"to": x["id"], "was": x["text"]} for x in v["cells"] if MM._inside(x, rows) and x["id"] not in used and P._ws(x["text"])]   # 예시 항목에 남은 값(달성도 100%)
            lines = []
            for at, c, edge, line in edges(rows, w):
                x = v["at"].get((rows[at], c))
                if x is not None and not MM._same_line(x[edge], line):
                    lines.append({"to": x["id"], "edge": edge, "line": line})
            out["fills"].append({"table": tid, "name": w["name"], "from": w["from"], "cells": cells, "clears": clears, "lines": lines})
            row["write"] += 1
        rest = todo[len(slots):]
        if rest and not blanks:
            row["skipped"] += len(rest)
            out["skipped"].append({"table": tid, "why": "shape", "detail": f"항목 {len(rest)}개를 넣을 빈 항목이 없고 본뜰 빈 항목도 없음 — 표에 빈 항목(행)을 더한 뒤 다시 계획하세요"})
        elif rest:
            like = blanks[-1]
            for w in rest:
                out["grows"].append({"table": tid, "like": [like[0], like[-1]], "name": w["name"], "from": w["from"],
                                     "cells": [{"at": [0, c], "text": text, "from": frm} for c, text, frm in w["cells"]],
                                     "lines": [{"at": [at, c], "edge": edge, "line": line} for at, c, edge, line in edges(like, w) if MM._special(line)]})   # 본뜬 빈 항목에는 선이 없다 — 그을 선만
                row["grow"] += 1
        for rows in slots[len(todo):]:   # 안 쓴 서식 예시 항목 — 글과 선을 지운다(빈 항목은 그대로)
            if _free(sch, rows, marks, orig) != "example":
                continue
            clears = [{"to": x["id"], "was": x["text"]} for x in v["cells"] if MM._inside(x, rows) and P._ws(x["text"])]
            lines = []
            for m in marks:
                kind = (m["type"], m["width"], m["color"])
                for k, edge in ((m["boundary"], "bottom"), (m["boundary"] + 1, "top")):
                    if k < len(rows):
                        lines += [{"to": x["id"], "edge": edge, "line": m["off"]} for x in v["cells"] if x["r"] == rows[k] and MM._kind(x[edge]) == kind]
            if clears or lines:
                out["wipes"].append({"table": tid, "clears": clears, "lines": lines})
                row["cleared"] += 1
    why = Counter(s["why"] for s in out["skipped"])
    out["counts"] = {"tables": len(out["owned"]), "items": sum(t["items"] for t in out["tables"]), "done": sum(t["done"] for t in out["tables"]), "write": len(out["fills"]), "rows": len(out["grows"]),
                     "cells": sum(len(f["cells"]) for f in out["fills"]) + sum(len(g["cells"]) for g in out["grows"]), "lines": sum(len(f["lines"]) for f in out["fills"]) + sum(len(g["lines"]) for g in out["grows"]),
                     "cleared": len(out["wipes"]), "skipped": {k: why.get(k, 0) for k in WHY}}
    out["todo"] = len(out["fills"]) + len(out["grows"]) + len(out["wipes"])
    return out


def apply(to_doc, from_doc, plan):
    """계획을 목적 문서에(모듈 설명) → {"filled", "shaped", "lines", "rowsAdded", "cleared", "skipped"}. 차례 = 행 늘리기(빈 항목을 본뜸 — 글을 쓰기 전에) → 항목 채우기 → 안 쓴 예시 지움.
    칸은 **지금** 계획 때 글 그대로일 때만 쓴다(항목의 칸 가운데 하나라도 바뀌었으면 그 항목은 통째로 안 넣는다)."""
    plan = plan or {}
    filled, lined, cleared, added, skipped, fit = 0, 0, 0, 0, [], []
    if not plan.get("todo"):
        return {"filled": 0, "shaped": 0, "lines": 0, "rowsAdded": 0, "cleared": 0, "skipped": []}
    to_doc.blocks()
    groups = {}   # (표, 본뜰 첫 행 · 끝 행) → 그 빈 항목을 본떠 넣을 항목들(계획 차례)
    for g in plan.get("grows") or ():
        groups.setdefault((g["table"], *g["like"]), []).append(g)
    for (tid, a, b), todo in groups.items():
        # 빈 항목을 **먼저 필요한 만큼** 본뜬다(본뜬 것마다 그 빈 항목 바로 아래에 들어간다 — 나중에 본뜬 것이 위) → 그 뒤에 위에서부터 차례로 채운다.
        # 채운 묶음을 다시 본뜨면 앞 항목의 글 · 선이 딸려 온다(선은 그을 것만 계획에 있다 — 본뜬 빈 항목에는 선이 없다).
        tb = to_doc.table_block(tid) or {"cells": []}
        base = {(c["row"] - a + k, c["col"] + j): c["id"] for c in tb["cells"] if a <= c["row"] <= b for k in range(c.get("rowSpan") or 1) for j in range(c.get("colSpan") or 1)}
        maps = []
        try:
            for _ in todo:
                maps.append(to_doc.clone_rows(tid, a, b, keep_text=True)["map"])
        except (ValueError, KeyError) as x:
            skipped.append({"table": tid, "why": "shape", "detail": f"행을 늘릴 수 없음 — {x}(항목 {len(todo) - len(maps)}개를 못 넣음)"})
        added += len(maps)
        for g, m in zip(todo, reversed(maps)):
            new = {k: m[i] for k, i in base.items() if i in m}
            seen = set()
            for c in g["cells"]:
                cid = new.get(tuple(c["at"]))
                if cid is None or cid in seen:
                    continue
                seen.add(cid)
                try:
                    to_doc.set_text(cid, c["text"])
                    filled += 1
                    fit.append((cid, c.get("from")))
                except ValueError as x:
                    skipped.append({"to": cid, "why": "shape", "detail": str(x)})
            edges = {}
            for ln in g["lines"]:
                cid = new.get(tuple(ln["at"]))
                if cid is not None:
                    edges.setdefault(cid, {})[ln["edge"]] = ln["line"]
            lined += _edges(to_doc, edges, skipped)
    now = {}

    def text_of(tid, cid):
        if tid not in now:
            now[tid] = {c["id"]: c.get("text") or "" for c in (to_doc.table_block(tid) or {}).get("cells") or ()}
        return now[tid].get(cid)
    for f in plan.get("fills") or ():
        if any(text_of(f["table"], c["to"]) is None or P._ws(text_of(f["table"], c["to"])) != P._ws(c["was"]) for c in (*f["cells"], *f["clears"])):
            skipped.append({"table": f["table"], "why": "occupied", "detail": f"계획 뒤 목적 항목의 글이 바뀜 — 「{P._ws(f['name'])[:30]}」 은 넣지 않음"})
            continue
        for c in f["cells"]:
            try:
                to_doc.set_text(c["to"], c["text"])
                filled += 1
                fit.append((c["to"], c.get("from")))
            except ValueError as x:
                skipped.append({"to": c["to"], "why": "shape", "detail": str(x)})
        cleared += _clear(to_doc, f["clears"], skipped)
        edges = {}
        for ln in f["lines"]:
            edges.setdefault(ln["to"], {})[ln["edge"]] = ln["line"]
        lined += _edges(to_doc, edges, skipped)
    for w in plan.get("wipes") or ():
        if any(P._ws(text_of(w["table"], c["to"]) or "") != P._ws(c["was"]) for c in w["clears"]):
            continue   # 그 사이 사람이 고친 예시 항목 — 그대로 둔다
        cleared += _clear(to_doc, w["clears"], skipped)
        edges = {}
        for ln in w["lines"]:
            edges.setdefault(ln["to"], {})[ln["edge"]] = ln["line"]
        lined += _edges(to_doc, edges, skipped)
    shaped = sum(MT._shape(to_doc, from_doc, to, frm) for to, frm in fit if frm)
    return {"filled": filled, "shaped": shaped, "lines": lined, "rowsAdded": added, "cleared": cleared, "skipped": skipped}


def _clear(to_doc, clears, skipped):
    n = 0
    for c in clears:
        try:
            to_doc.set_text(c["to"], "")
            n += 1
        except ValueError as x:
            skipped.append({"to": c["to"], "why": "shape", "detail": str(x)})
    return n


def _edges(to_doc, edges, skipped):
    n = 0
    for cid, e in edges.items():
        try:
            n += len(e) if to_doc.set_cell_edges(cid, e) else 0
        except (ValueError, KeyError) as x:
            skipped.append({"to": cid, "why": "shape", "detail": str(x)})
    return n

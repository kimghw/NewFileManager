"""표 엑셀화 — LLM 수식 판정(spec_헤딩_추출 ② §14 「LLM 수식 판정」): 엑셀식 보기의 단추를 누를 때만 호출 1번. 코드 고정 계약 + 지침(공통 표 지침 · 이 표 지침) + 자료(JSON)
→ 구조화 출력(수식 제안) → 스크립트 검사(주소·문법·글 칸·순환) → 스크립트 수식과 견줌(같음 · 값 같음 · 다름 · 새 수식).

LLM 이 하는 일은 **제안**까지다 — 통과한 제안도 화면에서 사람이 「적용」 해야 수식이 된다. 스크립트가 못 읽는 것(표 아래 글 각주 「* 수정직접비 = 직접비 소계 − …」,
코드 없는 헤더)을 읽히려는 길이고, 스크립트 수식(`table_excel.judge`)은 자료에 같이 실어 확인·고침을 받는다.

- `sheet(block, judge)` = 검사에 쓰는 표 꼴(칸·병합 자리·글 칸 여부·스크립트 수식) · `payload(sheet, ctx, …)` = 프롬프트 자료 · `ask(…)` = 호출(관문 `app/llm.py` — 예외 없음)
- `apply(data, sheet, rng)` = 답 검사·채우기 펼침·견줌 → {formulas, rejected, counts}. 수식 문법·계산은 `app/table_formula.py`(화면 엔진과 같은 문법)."""
import json
import math
import random

from app import prompt_texts
from app import heading_calc as HC
from app import llm
from app import table_formula as F

S = {"type": "string"}
TEXT = 60            # 격자 토큰의 칸 글 길이(코드 식이 든 헤더 「간접비 비율4)(L/(N+O+C+D+P+Q+R+I+S))」 가 잘리지 않게)
TEXT_NOTE = 300      # 안내·제목 칸의 글 길이(표 안 안내 글에 든 계산식이 잘리지 않게)
MAX_CELLS = 1500     # 이보다 큰 표는 LLM 에 안 보낸다(범위를 골라 달라고 답)
ITEMS_MAX = 400      # 답의 항목 수 한도
PROPOSALS_MAX = 400  # 펼친 뒤 제안 수 한도(사용자 수식 한도 table_agent.FORMULAS_MAX 와 같다)
REJECTED_MAX = 100
ROLE_KO = {"colhead": "열헤더", "rowhead": "행헤더", "corner": "귀퉁이", "field": "필드", "title": "제목", "note": "안내", "spacer": "간격"}


def _schema(props):
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


SCHEMA = _schema({"formulas": {"type": "array", "items": _schema({"cell": S, "formula": S, "fill": S, "reason": S})}, "note": S})

CONTRACT = f"""당신은 한글(hwpx) 문서의 표 하나를 엑셀 시트로 옮기는 검토자입니다. 표의 어느 칸이 다른 칸들로 **계산되는 칸**인지 판정해 그 칸의 엑셀 수식을 답합니다. 값은 채우지 않습니다 — 수식 자리만.
자료(JSON): grid = 표 격자(행마다 칸 토큰 「주소|역할|글|병합」 — 주소는 엑셀 A1 꼴이고 병합 칸은 왼쪽 위 주소 하나, 역할은 스크립트가 어림한 것(열헤더·행헤더·귀퉁이·필드·제목·안내·간격 — 틀릴 수 있음),
병합은 「행수x열수」, 글 없는 한 칸짜리 필드는 주소만) · before / after = 표 바로 앞·뒤 문단(표 제목·단위·각주) · script = 스크립트가 이미 판정한 수식(cell·formula·why) · unit = 단위 · range = 답할 범위(없으면 표 전체).
- **근거가 있는 수식만** 답합니다. 근거 = ① 헤더의 코드 식(「소계(A+B+C)」「총액(M=K+L)」「비율(I/E2)」 — 「(A)」 가 붙은 헤더의 칸이 그 코드의 값이고, 그 헤더가 아래에 여러 줄(현금·현물)을 거느리면 그 줄들의 합)
  ② 「합계·계·소계·총계」 헤더(같은 묶음 항목들의 합) ③ 「비율·구성비」 헤더 ④ before / after 의 글로 된 계산식(「1) 총 인건비 : 내부인건비 + 외부인건비 + …」「* 수정직접비 = 직접비 소계 − 직접비(현물) − …」 —
  항목 이름을 grid 의 헤더 글과 맞춰 주소로 옮깁니다). 표와 앞뒤 글 어디에도 근거가 없으면 수식을 만들지 않습니다(추측 금지).
- script 의 수식이 맞으면 **그대로** 다시 적고, 틀렸으면 고친 수식을, 빠진 칸은 새 수식을 적습니다. script 에 있는데 계산 칸이 아니라고 판단한 칸은 formula 를 빈 글로 적습니다. 답에 없는 칸은 「의견 없음」 입니다.
- formula: 「=」 로 시작. 주소는 grid 의 주소만(병합 칸은 왼쪽 위), 범위는 「E3:E6」. 연산 + - * / ^ %, 괄호, 함수는 {" · ".join(sorted(F.FUNCTIONS))} 만. 다른 시트·이름·배열 수식은 쓰지 않습니다. {F.MAX_LEN}자 이내.
- fill: 같은 꼴의 수식이 한 행이나 한 열로 이어지면 첫 칸의 수식을 cell·formula 에 적고 채울 범위를 fill 에 적습니다(「E26:K26」 — cell 을 품어야 하며, 엑셀의 채우기처럼 상대 주소가 옮겨집니다). 한 칸뿐이면 fill 은 빈 글.
- 수식은 값이 들어갈 칸에만 둡니다 — 이름·안내 글이 든 칸에는 두지 않습니다. 스크립트가 헤더로 어림했더라도 글이 없고 값이 들어갈 칸이면 계산 칸일 수 있습니다.
- 비율(%) 칸의 값은 **백분율 수**(20 = 20%)입니다 — 헤더가 「…비율」·「(%)」 이거나 칸 값이 % 꼴이면 나눈 뒤 ×100(「=(E19/E11)*100」). 수식의 후위 「%」 는 ÷100 이라 여기에 쓰지 않습니다.
  「합계」 열과 비율 행이 만나는 칸은 비율들의 합이 아니라 합계끼리의 비율입니다. 합계 열과 합계 행이 만나는 칸은 그 행의 정의(세로 방향 식)를 씁니다.
- reason: 근거 한 줄(어느 헤더·각주의 어떤 글에서 나왔는지, 한국어). note: 판단 요약 한두 문장(script 에서 고친 것, 근거가 모호해 뺀 것).
아래 「지침」 은 사용자가 준 기준입니다 — 이 계약과 어긋나면 계약을 따르세요."""


def _short(text, n):
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


# ---- 표 꼴 ---------------------------------------------------------------------------------------------------

def sheet(block, judge):
    """표의 웹 블록 + 표 전체 판정(`table_excel.judge` — 역할·스크립트 수식) → {rows, cols, cells{주소: 칸}, anchor{(행, 열): 주소}, script{주소: 수식}, why{주소: 근거}}.
    칸 = {ref, row, col, rs, cs, text, role, texty} — texty = 글 칸(빈 칸·수·자리표시가 아닌 글 — 수식이 덮어쓰면 안 되는 칸)."""
    roles = {(c["row"], c["col"]): c.get("role") for c in (judge or {}).get("cells") or []}
    cells, anchor = {}, {}
    rows, cols = int(block.get("nRows") or 0), int(block.get("nCols") or 0)
    for c in sorted(block.get("cells") or [], key=lambda c: (c["row"], c["col"])):
        rs, cs = int(c.get("rowSpan") or 1), int(c.get("colSpan") or 1)
        text = " ".join(str(c.get("text") or "").split())
        ref = F.a1(c["row"], c["col"])
        cells[ref] = {"ref": ref, "row": c["row"], "col": c["col"], "rs": rs, "cs": cs, "text": text, "role": roles.get((c["row"], c["col"])),
                      "texty": bool(HC.parse_num(text).get("text")) if len(text) <= 200 else True}
        rows, cols = max(rows, c["row"] + rs), max(cols, c["col"] + cs)
        for r in range(c["row"], c["row"] + rs):
            for k in range(c["col"], c["col"] + cs):
                anchor.setdefault((r, k), ref)
    fs = [f for f in (judge or {}).get("formulas") or [] if f.get("excel") and f.get("formula")]
    return {"rows": rows, "cols": cols, "cells": cells, "anchor": anchor, "script": {f["ref"]: f["formula"] for f in fs}, "why": {f["ref"]: f.get("note") or "" for f in fs}}


def _token(c):
    text = _short(c["text"], TEXT_NOTE if c["role"] in ("note", "title") else TEXT).replace("|", "/")
    span = f"{c['rs']}x{c['cs']}" if c["rs"] > 1 or c["cs"] > 1 else ""
    if not text and not span and c["role"] in (None, "field"):
        return c["ref"]
    return "|".join([c["ref"], ROLE_KO.get(c["role"] or "", ""), text] + ([span] if span else []))


def payload(tid, sh, ctx=None, unit=None, rng=None):
    """프롬프트 자료 — 격자는 늘 표 전체(범위 보기여도 헤더 맥락이 있어야 한다), range 는 답할 범위."""
    grid = [[] for _ in range(sh["rows"])]
    for c in sh["cells"].values():
        grid[c["row"]].append(_token(c))
    out = {"table": tid, "size": f"{sh['rows']}x{sh['cols']}", "unit": unit or "", "before": list((ctx or {}).get("before") or []), "after": list((ctx or {}).get("after") or []),
           "grid": grid, "script": [{"cell": ref, "formula": f, "why": _short(sh["why"].get(ref), 60)} for ref, f in sh["script"].items()]}
    if rng:
        out["range"] = f"{F.a1(rng['r0'], rng['c0'])}:{F.a1(rng['r1'], rng['c1'])}"
    return out


def guide_text(common, own, form=None):
    """form = 이 문서 양식 정보의 「표」 절(heading_forms.table_guide — 양식마다 관리하는 표 요청, spec ② §12)."""
    parts = [("양식 표 지침(이 양식의 문서에 공통)", form), ("공통 표 지침", common), ("이 표 지침", own)]
    out = [f"### {name}\n{text.strip()}" for name, text in parts if isinstance(text, str) and text.strip()]
    return "\n\n".join(out) if out else "(없음)"


def content(data, guide):
    return prompt_texts.contract(__name__) + "\n\n## 지침\n" + guide + "\n\n## 자료(JSON)\n" + json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def ask(data, guide, *, call=None, effort=None, timeout=300.0):
    """한 번 호출(잠금 밖) → {"data": 답 | None, "prompt", "call": {backend, model, effort, ms, costUsd, error}}."""
    prompt = content(data, guide)
    res = (call or llm.call)(SCHEMA, prompt, "table-formula", timeout=timeout, effort=effort)
    info = {k: res.get(k) for k in ("backend", "model", "effort", "ms", "costUsd", "error")}
    got = res.get("data")
    return {"data": got if isinstance(got, dict) else None, "prompt": prompt, "call": info}


# ---- 답 검사 · 견줌 ---------------------------------------------------------------------------------------------

def _deps(tree, sh):
    """수식이 가리키는 칸(병합 칸은 왼쪽 위 주소)."""
    out = set()
    for r0, c0, r1, c1 in F.rects(tree):
        for r in range(r0, min(r1, sh["rows"] - 1) + 1):
            for c in range(c0, min(c1, sh["cols"] - 1) + 1):
                ref = sh["anchor"].get((r, c))
                if ref:
                    out.add(ref)
    return out


def _cyclic(graph):
    """순환에 든 노드 — 제 자신을 가리키거나, 따라가면 제 자신으로 돌아오는 것(깊이 우선, 재귀 없이)."""
    bad, state = set(), {}
    for start in graph:
        if start in state:
            continue
        stack, path = [(start, iter(graph.get(start, ())))], [start]
        state[start] = 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
                path.pop()
                continue
            if nxt not in graph:
                continue
            if state.get(nxt) == 1:
                bad.update(path[path.index(nxt):])
            elif nxt not in state:
                state[nxt] = 1
                stack.append((nxt, iter(graph.get(nxt, ()))))
                path.append(nxt)
    return bad


def _values(tree, sh, seed, env=None, skip=None):
    """잎 칸에 (seed, 주소)로 정한 무작위 수를 넣어 계산 — env{주소: 트리} 가 있으면 그 칸은 그 수식으로 푼다(skip = 풀지 않을 칸: 견주는 칸 자신)."""
    memo, busy = {}, set()

    def leaf(ref):
        return random.Random(f"{seed}|{ref}").uniform(1.0, 1000.0)

    def value(r, c):
        ref = sh["anchor"].get((r, c))
        if ref is None:
            return None
        if env and ref in env and ref != skip:
            if ref in memo:
                return memo[ref]
            if ref in busy:
                raise F.FormulaError("#CYCLE!")
            busy.add(ref)
            memo[ref] = F.evaluate(env[ref], value, spots)
            busy.discard(ref)
            return memo[ref]
        return leaf(ref)

    def spots(r0, c0, r1, c1):
        seen, out = set(), []
        for r in range(r0, min(r1, sh["rows"] - 1) + 1):
            for c in range(c0, min(c1, sh["cols"] - 1) + 1):
                ref = sh["anchor"].get((r, c))
                if ref and ref not in seen:
                    seen.add(ref)
                    out.append((sh["cells"][ref]["row"], sh["cells"][ref]["col"]))
        return out
    return F.evaluate(tree, value, spots)


def _same_value(a, b, sh, ref, env):
    """두 수식의 값이 같은가 — 가리키는 칸을 모두 잎으로 보고 3번, 안 맞으면 다른 수식 칸을 스크립트 수식으로 풀어서 3번(「=E10+…」 과 E10 을 풀어 쓴 꼴)."""
    for use_env in (None, env):
        ok = True
        for seed in range(3):
            try:
                x, y = _values(a, sh, seed, use_env, ref), _values(b, sh, seed, use_env, ref)
            except F.FormulaError:
                ok = False
                break
            if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool) and not isinstance(y, bool):
                if not math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-9):
                    ok = False
                    break
            elif x != y:
                ok = False
                break
        if ok:
            return True
    return False


def apply(data, sh, rng=None):
    """LLM 답 → {formulas[{ref, formula, reason, script, kind}], rejected[{ref, formula, why}], counts}. kind = new(스크립트 수식이 없던 칸) · same(글이 같음) · equiv(값이 같음) ·
    diff(값이 다름) · off(스크립트 수식을 끄자는 제안 — formula ""). rng = 범위 보기의 범위({r0, c0, r1, c1}) — 그 안의 칸만."""
    rows, cols = sh["rows"], sh["cols"]
    prop, rejected, n_rej = {}, [], [0]

    def rej(ref, formula, why):
        n_rej[0] += 1
        if len(rejected) < REJECTED_MAX:
            rejected.append({"ref": ref, "formula": _short(formula, 120), "why": why})

    def inside(c):
        return rng is None or (rng["r0"] <= c["row"] and c["row"] + c["rs"] - 1 <= rng["r1"] and rng["c0"] <= c["col"] and c["col"] + c["cs"] - 1 <= rng["c1"])

    items = data.get("formulas") if isinstance(data, dict) else None
    for it in (items if isinstance(items, list) else [])[:ITEMS_MAX]:
        if not isinstance(it, dict):
            continue
        cell_s = str(it.get("cell") or "").strip().upper().replace("$", "")
        formula = str(it.get("formula") or "").strip()
        reason = _short(it.get("reason"), 200)
        p0 = F.pos(cell_s)
        if p0 is None or p0[0] >= rows or p0[1] >= cols or sh["anchor"].get(p0) is None:
            rej(cell_s, formula, "표에 없는 주소")
            continue
        raw = p0
        base = sh["cells"][sh["anchor"][p0]]
        p0 = (base["row"], base["col"])  # 병합 칸 안쪽 주소로 답했으면 왼쪽 위로
        rect = (p0[0], p0[1], p0[0], p0[1])
        fill_s = str(it.get("fill") or "").strip().upper().replace("$", "")
        if fill_s and fill_s != cell_s:
            a, _, b = fill_s.partition(":")
            pa, pb = F.pos(a), F.pos(b or a)
            if pa is None or pb is None:
                rej(cell_s, formula, f"채울 범위를 못 읽음: {fill_s[:20]}")
                continue
            rect = (min(pa[0], pb[0]), min(pa[1], pb[1]), max(pa[0], pb[0]), max(pa[1], pb[1]))
            if rect[2] >= rows or rect[3] >= cols:
                rej(cell_s, formula, f"채울 범위가 표 밖: {fill_s}")
                continue
            if not (rect[0] <= raw[0] <= rect[2] and rect[1] <= raw[1] <= rect[3]):
                rej(cell_s, formula, f"채울 범위 {fill_s} 가 {cell_s} 을 품지 않음")
                continue
            rect = (min(rect[0], p0[0]), min(rect[1], p0[1]), rect[2], rect[3])
        if formula and not formula.startswith("="):
            formula = "=" + formula  # 「=」 를 빠뜨린 답은 받아 준다
        if formula:
            try:
                F.parse(formula)
            except F.FormulaError as e:
                rej(cell_s, formula, f"수식 문법 — {e}")
                continue
        seen = set()
        for r in range(rect[0], rect[2] + 1):
            for c in range(rect[1], rect[3] + 1):
                ref = sh["anchor"].get((r, c))
                if ref is None or ref in seen:
                    continue
                seen.add(ref)
                cell = sh["cells"][ref]
                if not (rect[0] <= cell["row"] <= rect[2] and rect[1] <= cell["col"] <= rect[3]):
                    continue  # 범위 밖에서 걸쳐 들어온 병합 칸
                if not inside(cell):
                    rej(ref, formula, "고른 범위 밖")
                    continue
                if cell["texty"]:
                    rej(ref, formula, "글이 있는 칸")
                    continue
                if not formula:
                    prop[ref] = {"formula": "", "reason": reason, "tree": None}
                    continue
                dr, dc = cell["row"] - p0[0], cell["col"] - p0[1]
                f = F.shift(formula, dr, dc, rows, cols) if (dr or dc) else formula
                if f is None:
                    rej(ref, formula, "옮긴 주소가 표 밖")
                    continue
                try:
                    tree = F.parse(f)
                except F.FormulaError as e:
                    rej(ref, f, f"수식 문법 — {e}")
                    continue
                if any(x[2] >= rows or x[3] >= cols for x in F.rects(tree)):
                    rej(ref, f, "표 밖 주소")
                    continue
                named = [sh["anchor"].get((x[0], x[1])) for x in F.rects(tree) if (x[0], x[1]) == (x[2], x[3])]
                if any(n and sh["cells"][n]["texty"] for n in named):  # 칸 하나를 가리키는 주소가 글 칸(헤더·안내) — 엔진에서 #VALUE! 가 된다. 범위는 SUM 이 글을 건너뛰므로 둔다
                    rej(ref, f, "글 칸을 가리킴")
                    continue
                prop[ref] = {"formula": F.canon(f), "reason": reason, "tree": tree}
    if len(prop) > PROPOSALS_MAX:
        for ref in list(prop)[PROPOSALS_MAX:]:
            rej(ref, prop.pop(ref)["formula"], f"제안이 너무 많음(> {PROPOSALS_MAX})")
    script = {}
    for ref, f in sh["script"].items():
        try:
            script[ref] = F.parse(f)
        except F.FormulaError:
            continue
    for _ in range(6):  # 순환에 든 제안을 빼고 다시 — 뺀 칸은 스크립트 수식으로 돌아가므로 한 번 더 본다
        graph = {ref: _deps(t, sh) for ref, t in script.items() if ref not in prop}
        graph.update({ref: _deps(p["tree"], sh) for ref, p in prop.items() if p["tree"] is not None})
        bad = [ref for ref in _cyclic(graph) if ref in prop]
        if not bad:
            break
        for ref in bad:
            rej(ref, prop.pop(ref)["formula"], "순환 참조(제 자신이나 서로를 가리킴)")
    out, counts = [], {"new": 0, "diff": 0, "equiv": 0, "same": 0, "off": 0}
    for ref in sorted(prop, key=lambda k: (sh["cells"][k]["row"], sh["cells"][k]["col"])):
        p, s = prop[ref], sh["script"].get(ref)
        if p["tree"] is None:
            if not s:
                continue  # 스크립트 수식도 없는 칸을 「계산 칸 아님」 이라 한 것 — 할 일 없음
            kind = "off"
        elif not s or ref not in script:
            kind = "new"
        elif F.canon(s) == p["formula"]:
            kind = "same"
        else:
            kind = "equiv" if _same_value(p["tree"], script[ref], sh, ref, script) else "diff"
        counts[kind] += 1
        out.append({"ref": ref, "formula": p["formula"], "reason": p["reason"], "script": s, "kind": kind})
    return {"formulas": out, "rejected": rejected, "counts": {**counts, "rejected": n_rej[0]}}

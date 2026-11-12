"""표 만들기 · 서식 변환의 형식 중립부(spec_헤딩_추출 ② §11) — 격자 정규화 · 양식 구역 판정 · 구역 맞춤 · 표 꼴 글 읽기 · 검산.

- 격자(LLM 답·미리보기·넣기 요청의 공통 꼴): {"rows": [{"cells": [{"text", "rowSpan", "colSpan"}]}], "headerRows", "headerCols", "footRows"}.
  `normalize` 가 HTML 표와 같은 자리 규칙으로 (row, col) 을 매긴다 — 어댑터(`app/hwpx_table_make.py`)는 정규화한 것만 받는다.
- 구역: 위 머리행 h · 왼쪽 머리열 k · 아래 합계행 f, 나머지가 몸. `roles_of` = 웹 블록(표)의 칸 음영·굵게·글로 자동 판정, `zone_index` = 대상 줄 → 양식 줄.
- LLM 계약·호출은 `app/table_llm.py`, 끝점은 `app/tables_api.py`, 화면은 `app/static/table_make.js`."""
import csv
import io
import re

ROWS_MAX, COLS_MAX, CELLS_MAX, TEXT_MAX = 200, 40, 3000, 4000
SOURCE_MAX = 60_000  # 원본 글(붙여 넣기·고른 문단) 글자 수 상한
TOTAL_RE = re.compile(r"^\s*(?:합\s*계|총\s*계|소\s*계|계|total|sum)\s*$", re.I)
_MD_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _int(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _cell_in(c):
    """칸 입력(글 | {"text", "rowSpan"?, "colSpan"?}) → (글, rs, cs)."""
    if isinstance(c, dict):
        text = c.get("text")
        text = "" if text is None else str(text)
        return text, _int(c.get("rowSpan"), 1, ROWS_MAX, 1), _int(c.get("colSpan"), 1, COLS_MAX, 1)
    return ("" if c is None else str(c)), 1, 1


def normalize(grid) -> dict:
    """격자 입력 → {"nRows", "nCols", "cells": [{"row", "col", "rowSpan", "colSpan", "text"}](행 우선), "headerRows", "headerCols", "footRows"}.
    행 = 칸 목록 | {"cells": [...]}. 위에서 내려온 합친 칸 자리는 건너뛰고, 그 자리에 걸리는 colSpan 은 줄이고, 표 밖으로 나가는 rowSpan 은 자르고,
    아무 칸도 덮지 않은 자리는 빈 칸으로 메운다. 빈 표·한도 초과는 ValueError(화면에 그대로 보임)."""
    if not isinstance(grid, dict) or not isinstance(grid.get("rows"), list):
        raise ValueError("격자는 {rows: [...]} 꼴이어야 합니다")
    rows = [(r.get("cells") if isinstance(r, dict) else r) for r in grid["rows"]]
    rows = [r if isinstance(r, list) else [] for r in rows]
    while rows and not rows[-1]:
        rows.pop()
    n_rows = len(rows)
    if not n_rows:
        raise ValueError("표에 행이 없습니다")
    if n_rows > ROWS_MAX:
        raise ValueError(f"표가 너무 큽니다 — {n_rows}행(한도 {ROWS_MAX}행)")
    occ, cells, n_cols = {}, [], 0
    for r, row in enumerate(rows):
        c = 0
        for raw in row:
            text, rs, cs = _cell_in(raw)
            while (r, c) in occ:
                c += 1
            if c >= COLS_MAX:
                raise ValueError(f"표가 너무 넓습니다(한도 {COLS_MAX}열)")
            rs = min(rs, n_rows - r)
            cs = min(cs, COLS_MAX - c)
            for k in range(1, cs):  # 위에서 내려온 칸에 걸리면 거기까지만
                if (r, c + k) in occ:
                    cs = k
                    break
            if len(text) > TEXT_MAX:
                raise ValueError(f"칸 글이 너무 깁니다 — {len(text):,}자(한도 {TEXT_MAX:,}자)")
            cell = {"row": r, "col": c, "rowSpan": rs, "colSpan": cs, "text": text.replace("\r\n", "\n").replace("\r", "\n")}
            cells.append(cell)
            for y in range(r, r + rs):
                for x in range(c, c + cs):
                    occ[y, x] = cell
            c += cs
            n_cols = max(n_cols, c)
    if not n_cols:
        raise ValueError("표에 칸이 없습니다")
    for r in range(n_rows):  # 구멍 메우기
        for c in range(n_cols):
            if (r, c) not in occ:
                cell = {"row": r, "col": c, "rowSpan": 1, "colSpan": 1, "text": ""}
                occ[r, c] = cell
                cells.append(cell)
    if len(cells) > CELLS_MAX:
        raise ValueError(f"표가 너무 큽니다 — 칸 {len(cells):,}개(한도 {CELLS_MAX:,})")
    # 칸이 하나도 시작하지 않는 줄(위·왼쪽에서 온 합친 칸으로만 덮인 줄)은 없앤다 — 빈 hp:tr 은 한글이 저장하다 멈춘다(table_grid.squeeze 와 같은 규칙)
    for at, span in (("row", "rowSpan"), ("col", "colSpan")):
        n = n_rows if at == "row" else n_cols
        starts = {c[at] for c in cells}
        for k in [k for k in range(n) if k not in starts][::-1]:
            for c in cells:
                if c[at] > k:
                    c[at] -= 1
                elif c[at] + c[span] - 1 >= k:
                    c[span] -= 1
            n -= 1
        if at == "row":
            n_rows = n
        else:
            n_cols = n
    cells.sort(key=lambda x: (x["row"], x["col"]))
    head = _int(grid.get("headerRows"), 0, n_rows, 0)
    return {"nRows": n_rows, "nCols": n_cols, "cells": cells, "headerRows": head,
            "headerCols": _int(grid.get("headerCols"), 0, n_cols, 0), "footRows": _int(grid.get("footRows"), 0, n_rows - head, 0)}


def to_rows(norm) -> dict:
    """정규화한 격자 → 화면·LLM 꼴 {"rows": [{"cells": [...]}], headerRows, headerCols, footRows}."""
    rows = [{"cells": []} for _ in range(norm["nRows"])]
    for c in norm["cells"]:
        rows[c["row"]]["cells"].append({"text": c["text"], "rowSpan": c["rowSpan"], "colSpan": c["colSpan"]})
    return {"rows": rows, "headerRows": norm["headerRows"], "headerCols": norm["headerCols"], "footRows": norm["footRows"]}


def clean_roles(roles, n_rows, n_cols, default=None) -> dict:
    """{headerRows, headerCols, footRows} 를 표 크기 안으로 — 없는 값은 default(없으면 0)."""
    d = default or {}
    roles = roles if isinstance(roles, dict) else {}
    head = _int(roles.get("headerRows", d.get("headerRows")), 0, n_rows, 0)
    return {"headerRows": head, "headerCols": _int(roles.get("headerCols", d.get("headerCols")), 0, n_cols, 0),
            "footRows": _int(roles.get("footRows", d.get("footRows")), 0, n_rows - head, 0)}


# ---- 구역 판정 · 맞춤 --------------------------------------------------------------------------------------------

def roles_of(cells, n_rows, n_cols) -> dict:
    """표의 구역 수 자동 판정 → {headerRows, headerCols, footRows}. cells = [{"row", "col", "rowSpan", "colSpan", "shaded"?, "bold"?, "text"?}].
    머리행 = 맨 위부터 「그 줄에 걸친 칸이 모두 음영」(음영 칸이 하나도 없는 표는 「모두 굵게」)인 줄 수 — 그런 표시가 전혀 없거나 표 전체가 한 가지면
    2행 이상일 때 1. 머리열 = 머리행 아래에서 왼쪽부터 같은 조건. 합계행 = 몸이 2행 이상이고 마지막 행 첫 칸 글이 합계·총계·소계·계 면 1."""
    if not cells or n_rows <= 0 or n_cols <= 0:
        return {"headerRows": 0, "headerCols": 0, "footRows": 0}
    key = "shaded" if any(c.get("shaded") for c in cells) else "bold" if any(c.get("bold") for c in cells) else None
    by_row = [[] for _ in range(n_rows)]
    by_col = [[] for _ in range(n_cols)]
    for c in cells:
        for r in range(c["row"], min(n_rows, c["row"] + c.get("rowSpan", 1))):
            by_row[r].append(c)
        for k in range(c["col"], min(n_cols, c["col"] + c.get("colSpan", 1))):
            by_col[k].append(c)
    head = 0
    if key:
        while head < n_rows and by_row[head] and all(c.get(key) for c in by_row[head]):
            head += 1
    if head >= n_rows or not key:  # 표시가 없거나 표 전체가 한 가지 — 관례대로 첫 행
        head = 1 if n_rows >= 2 else 0
    cols = 0
    if key:
        while cols < n_cols - 1:
            below = [c for c in by_col[cols] if c["row"] >= head]
            if not below or not all(c.get(key) for c in below):
                break
            cols += 1
    last = sorted((c for c in by_row[n_rows - 1] if c["row"] == n_rows - 1), key=lambda c: c["col"])
    foot = 1 if n_rows - head >= 2 and last and TOTAL_RE.match(str(last[0].get("text") or "")) else 0
    return {"headerRows": head, "headerCols": cols, "footRows": foot}


def zone_index(i, n, head, foot, tn, thead, tfoot):
    """대상 줄 i(0..n-1 — 머리 head 줄 · 꼬리 foot 줄) → 양식 줄(0..tn-1 — 머리 thead · 꼬리 tfoot). spec ② §11 「서식 따오기 규칙」.
    줄 수·구역 수가 같으면 1:1. 머리·꼬리는 양식 그 구역의 아래쪽부터 맞추고(남는 윗줄은 구역 첫 줄), 몸은 줄 수가 같으면 1:1, 아니면 첫 ↔ 첫 · 마지막 ↔ 마지막 ·
    사이 ↔ 양식 몸의 가운데 줄(3줄 이상일 때 — 아니면 첫 줄).
    양식에 그 구역이 없으면 몸 줄로, 몸이 없으면 머리 마지막 줄(머리도 없으면 마지막 줄)."""
    if tn <= 0:
        return 0
    if n == tn and head == thead and foot == tfoot:
        return i
    body = range(thead, tn - tfoot)
    if not thead:
        head = 0  # 양식에 머리가 없으면 대상의 머리 줄도 몸으로 센다(첫 줄 ↔ 양식 첫 줄)
    if not tfoot:
        foot = 0
    if i < head:
        return max(0, min(thead - 1, thead - head + i))
    if i >= n - foot:
        return max(tn - tfoot, min(tn - 1, tn - (n - i)))
    if not len(body):
        return thead - 1 if thead else tn - 1
    nb, j = n - head - foot, i - head
    if nb == len(body):
        return body[max(0, min(len(body) - 1, j))]
    if j <= 0:
        return body[0]
    if j >= nb - 1:
        return body[-1]
    return body[len(body) // 2] if len(body) >= 3 else body[0]  # 가운데 줄 — 첫 줄 옆의 줄은 첫 줄의 합친 칸(귀퉁이·큰 제목)에 덮여 있기 쉽다


def _vlen(s):
    """보이는 글 폭 어림 — 한글·한자 등 전각은 2, 나머지는 1."""
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in s)


def col_weights(norm, lo=6, hi=40):
    """열마다 글 길이로 본 폭 비중(열 수가 양식과 달라 양식의 열 폭을 쓸 수 없을 때) — 그 열에서 시작하는 안 합친 칸의 가장 긴 줄(전각 2) + 여백 2,
    lo..hi 로 자름(긴 문장 열이 다 차지하거나 짧은 열이 실처럼 가늘어지지 않게)."""
    out = [0] * norm["nCols"]
    for c in norm["cells"]:
        if c["colSpan"] == 1:
            out[c["col"]] = max(out[c["col"]], max((_vlen(ln) for ln in c["text"].split("\n")), default=0))
    return [max(lo, min(hi, w + 2)) for w in out]


# ---- 표 꼴 글 읽기(붙여 넣기) ----------------------------------------------------------------------------------------

def _md_cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [x.strip().replace("\\|", "|").replace("<br>", "\n").replace("<br/>", "\n") for x in re.split(r"(?<!\\)\|", s)]


def parse_text(text):
    """붙여 넣은 글이 표 꼴이면 격자 입력({"rows": [[글…]…], "headerRows"…}), 아니면 None.
    ① 마크다운 `|` 표(둘째 줄이 `|---|---|`) ② 탭 구분 글(엑셀·한글에서 복사 — 따옴표로 싼 칸의 줄 바꿈·탭 포함, 줄마다 탭이 하나 이상이거나 두 줄 이상이 탭을 가짐)."""
    if not isinstance(text, str) or not text.strip():
        return None
    lines = [ln for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    body = [ln for ln in lines if ln.strip()]
    if len(body) >= 2 and "|" in body[0] and _MD_SEP.match(body[1]):
        rows = [_md_cells(ln) for i, ln in enumerate(body) if i != 1 and "|" in ln]
        if rows and max(len(r) for r in rows) >= 2:
            return _plain_grid(rows, header=1)
    if "\t" in text:
        try:
            rows = [r for r in csv.reader(io.StringIO(text.replace("\r\n", "\n").replace("\r", "\n")), delimiter="\t") if any(x.strip() for x in r)]
        except csv.Error:
            rows = [ln.split("\t") for ln in body]
        tabbed = sum(1 for r in rows if len(r) >= 2)
        if rows and tabbed and (tabbed == len(rows) or tabbed >= 2):
            return _plain_grid([[x.strip() for x in r] for r in rows])
    return None


def _plain_grid(rows, header=None):
    n = max(len(r) for r in rows)
    rows = [r + [""] * (n - len(r)) for r in rows]
    cells = [{"row": i, "col": j, "rowSpan": 1, "colSpan": 1, "text": t} for i, r in enumerate(rows) for j, t in enumerate(r)]
    roles = roles_of(cells, len(rows), n)
    if header is not None:
        roles["headerRows"] = min(header, len(rows))
    return {"rows": rows, **roles}


def block_grid(block) -> dict:
    """웹 블록(표) → 격자 입력(칸 글·합치기 그대로 — 칸 안 표·그림은 글만) + 구역 자동 판정."""
    cells = sorted(block.get("cells") or [], key=lambda c: (c["row"], c["col"]))
    n_rows = block.get("nRows") or max((c["row"] + c.get("rowSpan", 1) for c in cells), default=0)
    n_cols = block.get("nCols") or max((c["col"] + c.get("colSpan", 1) for c in cells), default=0)
    rows = [[] for _ in range(n_rows)]
    for c in cells:
        if 0 <= c["row"] < n_rows:
            rows[c["row"]].append({"text": c.get("text") or "", "rowSpan": c.get("rowSpan", 1), "colSpan": c.get("colSpan", 1)})
    return {"rows": rows, **roles_of(cells, n_rows, n_cols)}


def block_nested(block) -> bool:
    """표 칸 안에 표·그림이 있는가(글만 옮겨진다는 알림용)."""
    return any(b.get("type") in ("table", "image") for c in block.get("cells") or [] for b in c.get("blocks") or [])


# ---- 검산 ---------------------------------------------------------------------------------------------------------

def _squash(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def check_texts(source_norm, result_norm, limit=30) -> dict:
    """표 → 표(convert·그대로): 원본 칸 글과 결과 칸 글을 공백을 접어 모둠으로 견줌 → {"lost": [원본에만], "added": [결과에만]}(각 limit 개까지 · "more" = 넘친 수)."""
    def bag(norm):
        out = {}
        for c in norm["cells"]:
            t = _squash(c["text"])
            if t:
                out[t] = out.get(t, 0) + 1
        return out
    a, b = bag(source_norm), bag(result_norm)
    lost = [t for t, n in a.items() for _ in range(max(0, n - b.get(t, 0)))]
    added = [t for t, n in b.items() for _ in range(max(0, n - a.get(t, 0)))]
    return {"lost": lost[:limit], "added": added[:limit], "numbers": [], "more": max(0, len(lost) - limit) + max(0, len(added) - limit)}


def check_numbers(source_text, result_norm, limit=30) -> dict:
    """글 → 표(compose): 결과 칸에 나온 수(숫자 토큰 — 쉼표는 떼고 견줌)가 원본 글에 있는지 → {"numbers": [원본에 없는 수]}. 한 자리 수는 번호일 수 있어 안 보고,
    「2026.3」 처럼 점으로 이은 수는 조각(2026 · 3)이 모두 원본에 있으면 있는 것으로 본다(「2026년 3월」 을 줄여 쓴 것)."""
    have = {m.group(0).replace(",", "") for m in _NUM.finditer(source_text or "")}
    have |= {p for v in list(have) for p in v.split(".")}
    missing = []
    for c in result_norm["cells"]:
        for m in _NUM.finditer(c["text"]):
            v = m.group(0).replace(",", "")
            if len(v) >= 2 and v not in have and not all(p in have for p in v.split(".")) and v not in missing:
                missing.append(v)
    return {"lost": [], "added": [], "numbers": missing[:limit], "more": max(0, len(missing) - limit)}

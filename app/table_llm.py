"""표 만들기 · 서식 변환 — LLM 호출(spec_헤딩_추출 ② §11 「LLM 호출」): 코드 고정 계약 + 지침(문서 양식의 표 지침 — 양식 정보 「표」 절, ② §12 · 공통 표 지침 · 표 양식의 표 지침 · 이번 지침) + 자료(JSON)
→ 구조화 출력(격자) 한 번. LLM 은 **구조와 칸 글만** 정하고 서식은 스크립트(`app/hwpx_table_make.py`)가 양식 표에서 따온다.

- mode "compose" = 글 → 표(정리) · "convert" = 표 → 표(칸 글은 한 글자도 안 고침 — 스크립트 검산 `table_make.check_texts`).
- 관문은 `app/llm.py`(예외 없음 — data None 이면 error). 여기서는 답을 `table_make.normalize` 로 검사해 못 쓰는 답을 걸러 낸다."""
import json

from app import llm
from app import table_make as M

S, I = {"type": "string"}, {"type": "integer"}
TPL_ROWS, TPL_TEXT = 15, 40  # 자료에 싣는 양식 격자 — 위 15행 · 칸 글 40자
NOTES_MAX = 12


def _schema(props):
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


SCHEMA = _schema({
    "headerRows": I, "headerCols": I, "footRows": I,
    "rows": {"type": "array", "items": _schema({"cells": {"type": "array", "items": _schema({"text": S, "rowSpan": I, "colSpan": I})}})},
    "note": S})

CONTRACT = f"""당신은 한글(hwpx) 문서의 표를 만드는 편집자입니다. 「원본」(글 또는 표)을 표로 정리해 격자로 답합니다. 괘선·음영·글자 모양 같은 서식은 스크립트가 「표 양식」(이 문서의 표 하나)에서
따오므로 당신은 **표의 구조와 칸 글만** 정합니다. 양식의 칸 글은 서식을 따올 표의 예시일 뿐이니 원본에 없는 양식 글을 답에 옮기지 마세요(열 제목으로 쓰는 것은 아래 규칙대로).
- rows: 위에서 아래로 행 목록. 행마다 cells = 왼쪽에서 오른쪽으로 칸 목록(윗행에서 rowSpan 으로 내려온 자리는 건너뜀). 칸 = text(칸 글 — 칸 안 줄 바꿈은 "\\n"), rowSpan, colSpan(안 합친 칸은 1, 1).
  모든 행의 가로 칸 수(colSpan 합 + 위에서 내려온 자리)가 같아야 합니다.
- headerRows = 위쪽 열 제목 행 수 · headerCols = 왼쪽 행 제목 열 수 · footRows = 아래쪽 합계·소계 행 수(없으면 0).
- mode "compose"(글 → 표): 원본 글의 내용을 **빠짐없이** 표로 정리합니다. 같은 속성이 되풀이되는 항목은 행(항목)·열(속성)로, 그렇지 않으면 「구분 | 내용」 꼴 2열로. 원본에 없는 사실·수·항목을 만들지 않습니다.
  문장은 칸에 맞게 다듬어도 되지만 수·단위·고유명사·날짜는 그대로 둡니다. 양식의 열 구성(열 제목)이 원본 내용과 맞으면 그 열 제목과 순서를 따르고(채울 내용이 없는 칸은 빈 글), 맞지 않으면 내용에 맞는 열 제목을 정합니다.
  글머리 기호·번호(「o」·「-」·「1)」)는 칸 글에서 떼되 순서는 지킵니다.
- mode "convert"(표 → 표): 원본 표의 칸 글을 **한 글자도 고치지 않고** 옮깁니다(요약·번역·맞춤법 고침·보탬·삭제 금지 — 빈 칸은 빈 글). 원본의 열 구성이 양식과 같으면 양식의 열 순서에 맞추고, 아니면 원본의 행·열 구성과
  칸 합치기를 그대로 둡니다. 이때 당신이 정하는 것은 headerRows·headerCols·footRows 입니다.
- note = 판단 요약 한두 문장(한국어 — 열을 어떻게 정했는지, 원본에서 표에 못 담은 것이 있으면 무엇인지).
표는 {M.ROWS_MAX}행 × {M.COLS_MAX}열 이내. 아래 「지침」 은 사용자가 준 기준입니다 — 이 계약과 어긋나면 계약을 따르세요."""


def _short(text, n):
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def template_data(block, roles, notes=None) -> dict:
    """양식 표(웹 블록) → 자료의 template: 크기 · 구역 수 · 격자(위 TPL_ROWS 행, 칸 = 글 | {"t", "rs", "cs"}) · 작성요령."""
    rows = {}
    for c in sorted(block.get("cells") or [], key=lambda c: (c["row"], c["col"])):
        if c["row"] >= TPL_ROWS:
            continue
        t = _short(c.get("text"), TPL_TEXT)
        rs, cs = c.get("rowSpan", 1), c.get("colSpan", 1)
        rows.setdefault(c["row"], []).append(t if rs == 1 and cs == 1 else {"t": t, "rs": rs, "cs": cs})
    out = {"rows": block.get("nRows"), "cols": block.get("nCols"), **roles, "grid": [rows[r] for r in sorted(rows)]}
    if (block.get("nRows") or 0) > TPL_ROWS:
        out["more"] = f"아래 {block['nRows'] - TPL_ROWS}행 생략"
    ns = [_short(n.get("text"), 200) for n in (notes or []) if n.get("text")][:NOTES_MAX]
    if ns:
        out["notes"] = ns
    return out


def guide_text(common, own, extra, form=None) -> str:
    """form = 이 문서 양식 정보의 「표」 절(heading_forms.table_guide — 문서 양식마다 관리하는 표 요청, spec ② §12). 「표 양식」(서식을 따올 표)과 다른 말이라 「문서 양식」 이라 적는다."""
    parts = [("문서 양식의 표 지침(이 양식의 문서에 공통)", form), ("공통 표 지침", common), ("표 양식의 표 지침", own), ("이번 지침", extra)]
    out = [f"### {name}\n{text.strip()}" for name, text in parts if isinstance(text, str) and text.strip()]
    return "\n\n".join(out) if out else "(없음)"


def content(mode, template, source, guide) -> str:
    """프롬프트 = 계약 + 지침 + 자료(JSON). source = {"kind": "text", "text"} | {"kind": "table", "grid": 격자 꼴}."""
    payload = {"mode": mode, "template": template, "source": source}
    return CONTRACT + "\n\n## 지침\n" + guide + "\n\n## 자료(JSON)\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def ask(mode, template, source, guide, *, call=None, effort=None, timeout=180.0) -> dict:
    """한 번 호출(잠금 밖) → {"norm": 정규화한 격자 | None, "note", "prompt", "response", "call": {backend, model, effort, ms, costUsd, error}}.
    답이 없거나(off·busy·길마다 실패) 격자로 못 쓰면 norm None · call.error 에 까닭."""
    prompt = content(mode, template, source, guide)
    res = (call or llm.call)(SCHEMA, prompt, f"table-make-{mode}", timeout=timeout, effort=effort)
    info = {k: res.get(k) for k in ("backend", "model", "effort", "ms", "costUsd", "error")}
    data, norm = res.get("data"), None
    if isinstance(data, dict):
        try:
            norm = M.normalize(data)
        except ValueError as e:
            info["error"] = f"못 쓰는 답: {e}"
    return {"norm": norm, "note": str((data or {}).get("note") or "") if isinstance(data, dict) else "", "prompt": prompt, "response": data, "call": info}

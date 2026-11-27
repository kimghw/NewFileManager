"""표 채우기(spec_헤딩_추출 ② §18) — 표의 **작성요령**(문서의 작성요령 · 지침 · 칸 입력 규칙)에 맞춰 빈 칸에 넣을 글을 LLM 이 제안하고, 사람이 고른 것만 문서에 쓴다.

사용자 2026-11-12 "모서리 버튼에 이 표의 작성 지침도 관리할 수 있도록 작성요령을 볼 수 있게 … 에이전트로 표 테이블 채우기 기능도" ·
"작성요령에는 문서에서 제공하는 작성요령, 다른 지침에서 제공하는 작성가이드라인도 있지만 셀에 값을 넣는 방식이나 규칙도 들어 가야함".

- **작성 요령 표 잇기**(`guide_tables`): 표 바로 뒤에 따라오는 「작성 요령」 표(TEMP 규칙 1 과 같은 제목 꼴 — `heading_temp._GUIDE_TITLE`)를 그 표의 작성요령으로.
  3단계 결과의 작성요령(`heading_tables.table_notes`)은 표 안 안내 칸과 표 앞뒤 **안내 문단**만 잇고 다음 표에서 끝나므로 뒤따르는 표의 글은 못 잇는다(그 표는 TEMP 라 3단계 표 목록에도 없다).
  이 모듈은 「작성 요령」 표만 지금 문서에서 바로 읽는다(3단계를 기다리지 않음).
- **칸 꼴**(`cell_form`): 칸 글에서 읽은 「값을 넣는 방식」 — check 체크 칸(「[ ]」·「□」) · date 날짜(「YYYY.MM.DD」·「20  년  월  일」) · num 수(「0,000」) · pct 비율(「00%」) ·
  ph 글 자리표시(「○○」) · blank 빈 칸 · text 글. 꼴마다 **빈 자리인가**(아직 안 채움)를 함께 답한다 — 표시 없는 체크 칸·숫자가 빠진 날짜도 빈 자리다.
- **채울 칸**(`analyze`): 칸 역할은 수식 판정(§14)·빈 필드 제거(§16)와 같은 길(그 표의 hp:p 만 1단계 꼴 레코드로 → 3단계 스크립트 초안 → §9 표 의미, LLM 없음).
  채우는 필드(역할 field − 수식으로 셈하는 칸) 가운데 빈 자리인 칸. 칸 안 표·그림이 있는 칸은 뺀다(`set_text` 가 칸의 문단을 통째로 바꾼다).
- **호출**(`ask`): 코드 고정 계약 + (할 일 프롬프트) + 작성요령 + 지침 + 칸 입력 규칙 + 자료(JSON — 격자 · 채울 칸 · 표 앞뒤 글 · 사용자가 준 자료 글 · 이 문서의 글) → 구조화 출력 한 번.
- **답 검사**(`apply`): 채울 칸의 주소만 · 체크 칸은 괄호 안 표시만 바뀌었는지 · 수 칸에 수가 왔는지 · **근거 구절이 자료에 실제로 있는지**(없으면 경고 — 화면에서 기본으로 안 고름).
  LLM 이 하는 일은 제안까지다 — 문서에 쓰는 것은 화면에서 사람이 고른 뒤(`tables_api.table_fill_apply` — 한 트랜잭션·실행 취소 1개)."""
import json
import re

from app import prompt_texts
from app import heading_calc as HC
from app import heading_rules as R
from app import heading_tables as HT
from app import heading_temp as T
from app import llm
from app import table_agent
from app import table_excel as TX
from app import table_formula as F
from app.hwpx_doc import P, RUN, TBL

S = {"type": "string"}
TEXT, TEXT_NOTE = 60, 300   # 격자 토큰의 칸 글 길이(안내·제목 칸은 길게)
NOW_MAX = 300               # 채울 칸의 지금 글(자리표시·체크 칸 원래 글) 길이
MAX_CELLS = 1500            # 이보다 큰 표는 LLM 에 안 보낸다(범위를 골라 달라고 답)
TARGETS_MAX = 300           # 한 번에 채울 칸 수
ITEMS_MAX = 400             # 답의 항목 수 한도
CELL_MAX = 2000             # 칸 하나에 넣는 글 길이
MATERIAL_MAX = 60_000       # 사용자가 준 자료 글
DOC_MAX = 60_000            # 자료로 싣는 이 문서의 글(앞에서부터)
REJECTED_MAX = 100
GUIDE_SCAN = 12             # 표 뒤로 「작성 요령」 표를 찾아 지나가는 글·개체 문단 수(연구개발계획서 양식: 같은 절의 표 → 그 절 끝 작성 요령 표 ≤ 9, 다른 절의 것 ≥ 23)
GUIDES_MAX = 3
ROLE_KO = table_agent.ROLE_KO
FORM_KO = {"check": "체크", "date": "날짜", "num": "수", "pct": "비율", "ph": "글 자리표시", "blank": "빈 칸", "text": "글"}
WHERES = ("material", "document", "table", "context", "rule")
BOX_LABEL = 20              # 상자 글리프(「□」) 뒤 항목 글이 이보다 길면 체크 칸이 아니라 글머리 기호로 본다


def _schema(props):
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


SCHEMA = _schema({"fills": {"type": "array", "items": _schema({"cell": S, "text": S, "source": S, "where": S, "reason": S})}, "note": S})

CONTRACT = """당신은 한글(hwpx) 문서의 표 하나를 채우는 작성자입니다. 「자료」 에서 값을 찾아 표의 빈 칸(targets)에 넣을 글을 제안합니다. 제안은 사람이 확인한 뒤에만 문서에 들어갑니다.
자료(JSON): grid = 표 격자(행마다 칸 토큰 「주소|역할|글|병합」 — 주소는 엑셀 A1 꼴이고 병합 칸은 왼쪽 위 주소 하나, 역할은 스크립트가 어림한 것(열헤더·행헤더·귀퉁이·필드·제목·안내·간격),
병합은 「행수x열수」, 글 없는 한 칸짜리 필드는 주소만) · targets = 채울 칸 목록(cell = 주소 · row / col = 그 칸의 행·열 머리 글 · form = 칸 꼴 · now = 지금 칸 글(자리표시·체크 칸의 원래 글 —
줄 바꿈은 "\\n") · filled = 이미 글이 있는 칸(사용자가 다시 제안해 달라고 한 칸)) · before / after = 표 바로 앞·뒤 문단 · unit = 단위 · place = 이 표가 놓인 자리(heading = 소속 제목 · path = 그 위 제목들 ·
division = 구분 라벨 — 어느 단계·차년도·기관의 표인지) · material = 사용자가 이 표를 채우라고 직접 준 자료 글 · document = **지금 열어 둔 이 문서**(표가 든 문서)의 글(표 밖 본문과 다른 표 — 앞에서부터 일부).
- **자료에 있는 값만** 넣습니다. 값의 출처는 material · document · 이 표의 다른 칸(grid) · before / after 뿐입니다. 어디에도 없거나 어느 값인지 확실하지 않은 칸은 **답에서 뺍니다**
  (빈 채로 둡니다 — 틀린 값보다 빈 칸이 낫습니다). 지어내거나 일반 지식으로 채우지 않습니다. place 가 있으면 그 단계·차년도·기관의 값만 넣습니다(다른 기관·다른 해의 값을 옮기지 않습니다).
  예외는 하나: 아래 지침·칸 입력 규칙이 값이 없는 칸에 넣을 **고정 글**을 정했으면(「해당 없는 칸은 -」) 그 글을 넣고, source 에 그 지침 문장을 글자 그대로, where 에 rule 을 적습니다.
- targets 에 있는 칸만 답합니다(cell = targets 의 주소 그대로). 한 칸에 한 번. filled 가 true 인 칸은 지금 글이 자료와 **다를 때만** 답합니다(같으면 답에서 뺍니다).
- text = 그 칸에 들어갈 글 **전체**(설명·따옴표 없이). 칸 안에서 줄을 바꾸려면 "\\n".
- form 에 따라: 「체크」 칸은 now 의 글을 그대로 두고 해당 항목의 괄호 안에만 표시를 넣은 글 전체를 text 로 적습니다(「[ ] 신청용 [ ] 협약용」 → 「[ ] 신청용 [ √ ] 협약용」 — now 가 여러 줄이면
  줄 수도 그대로). 「날짜」 칸은 now 의 구분 기호·낱말(년·월·일·점)을 그대로 두고 숫자만 채웁니다. 「수」·「비율」 칸은 now 의 자리표시 꼴(쉼표·%·소수 자리)을 따르고 unit 에 맞춥니다.
- 아래 「작성요령」 과 「지침」 은 **무엇을** 적어야 하는지, 「칸 입력 규칙」 은 **어떻게** 적어야 하는지입니다 — 모두 따릅니다. 머리 글에 붙은 번호(「보안등급1)」)는 작성요령의 그 번호 항목
  (「1. 보안등급: …」)을 가리킵니다.
- source = 그 값을 찾은 자료의 구절을 **글자 그대로** 옮겨 적습니다(30자 안팎 — 스크립트가 자료에서 그 구절을 찾아 확인합니다). where = 그 구절이 있던 곳(material | document | table | context | rule).
- reason = 왜 그 칸의 값인지 한 줄(한국어 — 단위를 바꿔 셈했거나 여러 후보 가운데 골랐으면 그것도).
- note = 요약 한두 문장(못 채운 칸이 왜 비었는지 — 자료에 없음 · 모호함).
아래 작성요령 · 지침 · 칸 입력 규칙은 문서와 사용자가 준 기준입니다 — 이 계약의 「자료에 있는 값만」·「targets 의 칸만」 과 어긋나면 계약을 따르세요."""

# 할 일 프롬프트(spec_작업 ② §13)를 붙일 때의 머리 문장 — `job_prompts.NOTE` 의 이 호출 판. 할 일의 전제는 「어느 문서가 기준인가」 를 말하므로, 이 호출의 자료 둘이 그 가운데 무엇인지를 여기서 정해 준다:
# document = 지금 열어 둔 문서(이관에서는 대개 목적 문서 — 값의 기준이 아니다) · material = 사용자가 직접 준 글(기준 문서에서 뽑아 준 것으로 본다).
JOB_NOTE = ("아래는 **이 작업의 할 일**에 대해 사용자가 직접 정해 저장해 둔 전제·기준입니다. 어느 문서가 기준(원본)이고 어느 문서가 목적인지, 무엇을 넣고 무엇을 만들지 않는지는 이 글을 먼저 따릅니다 — "
            "위 계약의 출처 목록과 어긋나 보이면 이 글의 전제에 맞게 판단합니다. 자료의 document 는 **지금 열어 둔 이 문서**의 글입니다: 이 글의 전제가 그 문서(목적 문서·빈 서식)에서 값을 가져오지 말라고 하면 "
            "document 는 값의 출처로 쓰지 않고 어느 표·어느 자리인지 아는 데만 씁니다. material 은 사용자가 이 표를 채우라고 직접 준 글이므로 기준 문서에서 뽑아 준 것으로 보고 값의 출처로 씁니다. "
            "답의 꼴과 「자료에 있는 값만」·「targets 의 칸만」 은 위 계약 그대로입니다.")


def _short(text, n):
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _lines(text):
    """문단 글 → 줄(강제 줄 바꿈·줄 바꿈 기준), 앞뒤 공백 뗌."""
    return [ln.strip() for ln in str(text or "").replace(R.BR, "\n").split("\n")]


# ---- 「작성 요령」 표 잇기 --------------------------------------------------------------------------------------------

def guide_title(block):
    """표 블록이 「작성 요령」 표인가 — TEMP 규칙 1(`heading_temp._guide_table`)과 같은 꼴: 처음 두 행(또는 첫 글 문단)에 제목 줄. → (제목 글, 그 문단 id) | None."""
    first = True
    for c in sorted(block.get("cells") or [], key=lambda c: (c["row"], c["col"])):
        if c["row"] > 1 and not first:
            break
        for p in c.get("blocks") or []:
            if p.get("type") != "paragraph":
                continue
            line = next((ln for ln in _lines(p.get("text")) if ln), "")
            if not line:
                continue
            if (first or c["row"] <= 1) and len(line) <= T.TITLE_MAX and T._GUIDE_TITLE.match(line):
                return line, p["id"]
            first = False
    return None


def _flat(blocks, skip=None, out=None, drop=None):
    """블록들 → 글 줄 목록: 문단은 한 줄, 표는 행마다 「a | b | c」(칸 안 표는 그 뒤에 이어서). skip = 뺄 문단 id 하나.
    drop = 뺄 표 id 모음(None 이 아니면 그 표들과 「작성 요령」 표를 — 칸 안에 든 것까지 — 뺀다: 문서 글을 자료로 실을 때)."""
    out = [] if out is None else out
    for b in blocks:
        if b.get("type") == "paragraph":
            if b.get("id") == skip:
                continue
            t = " ".join(x for x in _lines(b.get("text")) if x)
            if t:
                out.append(t)
        elif b.get("type") == "table":
            _flat_table(b, skip, out, drop)
    return out


def _flat_table(block, skip=None, out=None, drop=None):
    out = [] if out is None else out
    if drop is not None and (block.get("id") in drop or guide_title(block) is not None):
        return out
    rows, inner = {}, []
    for c in sorted(block.get("cells") or [], key=lambda c: (c["row"], c["col"])):
        paras = [b for b in c.get("blocks") or [] if b.get("type") == "paragraph" and b.get("id") != skip]
        t = " ".join(x for b in paras for x in _lines(b.get("text")) if x)
        if t:
            rows.setdefault(c["row"], []).append(t)
        inner += [b for b in c.get("blocks") or [] if b.get("type") == "table"]
    out += [" | ".join(rows[r]) for r in sorted(rows)]
    for b in inner:
        _flat_table(b, skip, out, drop)
    return out


def guide_note(block):
    """「작성 요령」 표 블록 → 작성요령 한 건 {where: "guide", table, para(제목 문단), title, text(항목 줄 — 줄마다 \\n)} | None(작성 요령 표 아님)."""
    got = guide_title(block)
    if got is None:
        return None
    title, para = got
    lines = []
    for c in sorted(block.get("cells") or [], key=lambda c: (c["row"], c["col"])):   # 칸마다 — 제목 칸은 제목 줄만 빼고(덧글 「ITECH 접수과제만 작성…」 은 남긴다)
        lines += _flat(c.get("blocks") or [], skip=para)
    return {"where": "guide", "table": block["id"], "para": para, "title": title, "text": "\n".join(lines)[:table_agent.GUIDE_TEXT]}


def guide_tables(doc, tid, scan=GUIDE_SCAN, limit=GUIDES_MAX):
    """표 tid 뒤에 따라오는 「작성 요령」 표들 → [guide_note…](문서 순). 같은 그릇(구역·칸)의 뒤 문단을 훑어 처음 만나는 「작성 요령」 표와 바로 이어진 것(「작성요령(계속)」)까지.
    그 앞에 글·다른 표가 scan 개를 넘으면 그만둔다(양식은 절 끝에 그 절의 작성 요령 표를 둔다 — 멀리 있는 것은 다른 절의 것). 표가 아니거나 그 표가 작성 요령 표면 빈 목록."""
    tbl = doc._ids.get(tid) if isinstance(tid, str) else None
    if tbl is None or tbl.tag != TBL or not hasattr(doc, "table_block") or not doc._attached(tbl):
        return []
    own = doc.table_block(tid)
    if own is None or guide_title(own) is not None:
        return []
    host, out, seen = doc._host(tbl), [], 0
    for p in [host, *host.itersiblings(P)]:
        tbls = [o for r in p.iterchildren(RUN) for o in r if o.tag == TBL]
        if p is host:
            tbls = tbls[tbls.index(tbl) + 1:] if tbl in tbls else []
        for t in tbls:
            b = doc.table_block(doc._id(t))
            note = guide_note(b) if b else None
            if note is not None:
                out.append(note)
                if len(out) >= limit:
                    return out
            elif out:
                return out   # 작성 요령 표 묶음 뒤의 다른 표 — 끝
            else:
                seen += 1
        if p is not host and not tbls and (doc._has_object(p) or doc._text(p).strip()):
            if out:
                return out   # 작성 요령 표 뒤에 글이 나옴 — 끝
            seen += 1
        if seen > scan:
            break
    return out


# ---- 칸 꼴(값을 넣는 방식) --------------------------------------------------------------------------------------------

_MARK = "√✓✔vVoOㅇ○●■xX"
_CHECK = re.compile(r"\[\s*([" + _MARK + r"]?)\s*\]|([□☐])|([■☑☒])")
_DATE_KO = re.compile(r"(\d{0,4})\s*년\s*(\d{0,2})\s*월(?:\s*(\d{0,2})\s*일)?")
_DATE_PH = re.compile(r"Y{2,4}|y{2,4}|20[xX]{2}\s*[.년/~]|M{2}\s*[.\-/]\s*D{2}")   # 「YYYY.MM.DD」「20xx.xx.xx」「20xx~20xx」 — 「제20xx-xx호」 는 날짜가 아니다(글 자리표시)
_DATE_DOT = re.compile(r"^\s*(\d{0,4})\s*\.\s*(\d{0,2})\s*\.\s*(\d{0,2})\s*\.?\s*$")
_X_PH = re.compile(r"(?<![A-Za-z])[xX]{2,}(?![A-Za-z])|[○◯]{2,}|(?<![A-Za-z0-9])[oO]{2,}(?![A-Za-z0-9])")   # 「제20xx-xx호」「○○대학교」「OO기관」 — 짧은 칸에서만
PH_MAX = 40
_BOX = re.compile(r"[□☐■☑☒]")


def _box_is_check(s):
    """상자 글리프(□·☐·■·☑)가 체크 칸의 것인가 — 글리프마다 뒤 항목 글(다음 글리프·줄 끝까지)이 BOX_LABEL 자 이하일 때만(「□ 해당 □ 해당 없음」).
    줄 첫머리 「□」 뒤에 긴 글이 따르면 글머리 기호다(「□ 연구개발기술(제품)의 정의 및 범위를 서술한 글 …」 — 이 양식의 개요 3레벨이 「□」)."""
    parts = _BOX.split(s)
    return len(parts) > 1 and all(len(p.split("\n", 1)[0].strip()) <= BOX_LABEL for p in parts[1:])


def cell_form(text, kinds=None):
    """칸 글 → (꼴, 빈 자리인가). 꼴 = check · date · num · pct · ph · blank · text(FORM_KO). 빈 자리 = 아직 안 채운 칸:
    글 없음 · 자리표시뿐 · 표시가 하나도 없는 체크 칸 · 숫자가 빠진 날짜. kinds = 1단계 문단 종류 수 — 글 문단이 **모두** placeholder 면 글 자리표시
    (§16 `table_prune.cell_empty` 와 같은 판단: 자리표시 줄 아래에 글을 써 넣은 칸은 채워진 칸이다)."""
    s = str(text or "").replace(R.BR, "\n").strip()
    if not s:
        return "blank", True
    checks = [m for m in _CHECK.finditer(s) if m.group(1) is not None or _box_is_check(s)]   # 대괄호 자리 + (체크로 볼 수 있는) 상자 글리프
    if checks:
        return "check", not any(m.group(1) or m.group(3) for m in checks)
    if _DATE_PH.search(s):
        return "date", True
    m = _DATE_KO.search(s)
    if m and len(_DATE_KO.sub("", s).strip()) <= 12:   # 날짜 말고 다른 글이 긴 칸(문장 속 날짜)은 글
        return "date", not (len(m.group(1)) == 4 and m.group(2))
    m = _DATE_DOT.match(s)
    if m and not all(m.groups()):
        return "date", True
    one = " ".join(s.split())
    num = HC.parse_num(one) if len(one) <= 200 else {"num": None, "text": True}
    if num.get("placeholder"):   # 「0,000」「00%」「○○」
        if re.search(r"[0-9]", one):
            return ("pct" if re.search(r"[%％]\s*$", one) else "num"), True
        return "ph", True
    if {k for k, v in (kinds or {}).items() if v and k not in ("empty", "object")} == {"placeholder"} or (len(one) <= PH_MAX and _X_PH.search(one)):
        return "ph", True
    if num.get("num") is not None and not num.get("dash"):
        return ("pct" if num.get("pct") else "num"), False
    return "text", False


def _check_skel(text):
    """체크 칸 글의 뼈대 — 괄호 안 표시와 공백을 뺀 글(표시만 바꿨는지 견준다)."""
    return re.sub(r"\s+", "", _CHECK.sub(lambda m: "□" if (m.group(2) or m.group(3)) else "[]", str(text or "")))


def _date_skel(text):
    return re.sub(r"[\dYyMmDdxX\s]", "", str(text or ""))


# ---- 채울 칸 --------------------------------------------------------------------------------------------------------

def analyze(doc, tid, rng=None, overwrite=False, store=None, doc_key=None, roles=None, block=None):
    """표의 채울 칸 → {table, rows, cols, unit, range, cells[격자 칸], anchor{(행, 열): 주소}, targets[채울 칸], skipped[{ref, why}], counts, forms, note?}.
    cells = {ref, row, col, rs, cs, role, text} · targets = {ref, cell(칸 id), row, col, name(행·열 머리 글), rowName, colName, form, now(지금 칸 글 — 문단마다 \\n)}.
    rng = 끌어 고른 범위({r0, c0, r1, c1} — 그 안에 통째로 든 칸만) · overwrite = 채워진 필드도 대상. 표가 아니면 None, 너무 크면 ValueError.
    roles = 사용자 헤더 지정(spec_owpml_편집 ② §5-4) · block = 그 표의 웹 블록(없으면 읽는다)."""
    stage1 = TX.records(doc, tid, store, doc_key)
    if stage1 is None:
        return None
    block = block or doc.table_block(tid)
    out = {"table": tid, "rows": int(block.get("nRows") or 1), "cols": int(block.get("nCols") or 1), "unit": None, "range": None, "cells": [], "anchor": {},
           "targets": [], "skipped": [], "forms": {}, "counts": {"cells": len(block.get("cells") or []), "fields": 0, "open": 0, "targets": 0, "skipped": 0}}
    tb = next((t for t in HT.collect(stage1) if t["id"] == tid), None)
    if tb is None:
        return {**out, "note": "1칸 표(글상자)에는 채울 필드가 없습니다"}
    if len(tb["cells"]) > TX.MAX_CELLS:
        raise ValueError(f"표가 너무 큽니다(칸 {len(tb['cells'])} > {TX.MAX_CELLS})")
    subs, sem = TX._analyze(tb, roles)
    keyval = {s["id"] for s in subs if s.get("kind") == "form"}   # 키-값 띠 — 값 칸의 이름은 왼쪽 머리 글뿐(위쪽 칸은 다른 항목이다)
    rows, cols = tb["rows"], tb["cols"]
    box = None
    if rng:
        r0, c0 = max(0, int(rng["r0"])), max(0, int(rng["c0"]))
        r1, c1 = min(rows - 1, int(rng["r1"])), min(cols - 1, int(rng["c1"]))
        if r0 <= r1 and c0 <= c1 and (r0, c0, r1, c1) != (0, 0, rows - 1, cols - 1):
            box = (r0, c0, r1, c1)
    inside = lambda x: box is None or (box[0] <= x["row"] and x["row"] + x["rs"] - 1 <= box[2] and box[1] <= x["col"] and x["col"] + x["cs"] - 1 <= box[3])  # noqa: E731
    now = {c["id"]: str(c.get("text") or "") for c in block.get("cells") or []}
    by_id = {x["id"]: x for x in tb["cells"]}
    calc = {f["cell"] for f in sem["formulas"]}   # 수식으로 셈하는 칸(합계·비율·코드 식) — 사람이 채우는 칸이 아니다
    name = lambda ids: " › ".join(t for t in (_short(by_id[i].get("textFull"), 40) for i in ids or [] if i in by_id) if t)  # noqa: E731
    cells, anchor, targets, skipped, forms = [], {}, [], [], {}
    for x in tb["cells"]:
        ref = F.a1(x["row"], x["col"])
        cells.append({"ref": ref, "row": x["row"], "col": x["col"], "rs": x["rs"], "cs": x["cs"], "role": x.get("role"), "text": " ".join((x.get("textFull") or "").split())})
        for r in range(x["row"], x["row"] + x["rs"]):
            for c in range(x["col"], x["col"] + x["cs"]):
                anchor.setdefault((r, c), ref)
        if x.get("role") != "field" or x["id"] in calc:
            continue
        out["counts"]["fields"] += 1
        text = now.get(x["id"], "")
        form, is_open = cell_form(text, x.get("kinds"))
        forms[form] = forms.get(form, 0) + 1
        if is_open:
            out["counts"]["open"] += 1
        if not (is_open or overwrite) or not inside(x):
            continue
        if x.get("nested") or (x.get("kinds") or {}).get("object"):
            skipped.append({"ref": ref, "why": "칸 안에 표·그림이 있음"})
            continue
        row_name, col_name = name(x.get("rowPath")), "" if x.get("sub") in keyval else name(x.get("colPath"))
        targets.append({"ref": ref, "cell": x["id"], "row": x["row"], "col": x["col"], "rowName": row_name, "colName": col_name,
                        "name": " · ".join(n for n in (row_name, col_name) if n), "form": form, "open": is_open, "now": text})
    out.update(rows=rows, cols=cols, unit=sem.get("unit"), cells=cells, anchor=anchor, targets=targets, skipped=skipped, forms=forms,
               range={"r0": box[0], "c0": box[1], "r1": box[2], "c1": box[3]} if box else None)
    out["counts"].update(cells=len(cells), targets=len(targets), skipped=len(skipped))
    return out


def forms_text(forms):
    """칸 꼴 수 → 「체크 12 · 수 30 · 빈 칸 8」(묶음 글·화면)."""
    return " · ".join(f"{FORM_KO[k]} {forms[k]}" for k in FORM_KO if forms.get(k))


# ---- 자료 ----------------------------------------------------------------------------------------------------------

def doc_text(blocks, skip=(), cap=DOC_MAX):
    """이 문서의 글(자료) — 최상위 블록 차례로 문단은 한 줄, 표는 행마다 「a | b | c」. skip = 뺄 표 id(채우는 표). 「작성 요령」 표는 뺀다(자료가 아니라 요령) —
    둘 다 다른 표의 칸 안에 든 것까지. → (글 — cap 자까지, 잘렸는가, 전체 글자 수)."""
    text = "\n".join(_flat(blocks or [], None, [], set(skip)))
    return text[:cap], len(text) > cap, len(text)


def place_of(tb):
    """3단계 결과의 표 → 이 표가 놓인 자리 {heading, path[], division?} | None(3단계 없음 · 문서 뿌리) — 어느 절, 어느 구분 값(단계·차년도·기관)의 표인지.
    묶음 글 [표 식별](`table_agent.prompt`)과 같은 원천(§9 소속)."""
    o = (tb or {}).get("owner") or {}
    if not o or o.get("root") or not (o.get("text") or "").strip():
        return None
    out = {"heading": _short(o.get("text"), 80), "path": [_short(p, 60) for p in o.get("path") or []]}
    if (o.get("division") or {}).get("text"):
        out["division"] = _short(o["division"]["text"], 60)
    return out


def _token(c):
    text = _short(c["text"], TEXT_NOTE if c["role"] in ("note", "title") else TEXT).replace("|", "/")
    span = f"{c['rs']}x{c['cs']}" if c["rs"] > 1 or c["cs"] > 1 else ""
    if not text and not span and c["role"] in (None, "field"):
        return c["ref"]
    return "|".join([c["ref"], ROLE_KO.get(c["role"] or "", ""), text] + ([span] if span else []))


def payload(an, ctx=None, material="", document="", place=None):
    """프롬프트 자료 — 격자는 늘 표 전체(범위를 골랐어도 머리 글 맥락이 있어야 한다), targets 는 채울 칸만(이미 글이 있는 칸은 filled: true).
    place = 이 표가 놓인 자리(`place_of` — 3단계가 있을 때만)."""
    grid = [[] for _ in range(an["rows"])]
    for c in an["cells"]:
        if c["row"] < len(grid):
            grid[c["row"]].append(_token(c))
    out = {"table": an["table"], "size": f"{an['rows']}x{an['cols']}", "unit": an.get("unit") or "",
           "before": list((ctx or {}).get("before") or []), "after": list((ctx or {}).get("after") or []), "grid": grid,
           "targets": [{"cell": t["ref"], "row": t["rowName"], "col": t["colName"], "form": FORM_KO[t["form"]], "now": t["now"][:NOW_MAX], **({} if t["open"] else {"filled": True})}
                       for t in an["targets"]],
           "material": material or ""}
    if place:
        out["place"] = place
    if document:
        out["document"] = document
    return out


def notes_text(notes):
    """작성요령 목록 → 프롬프트 글(없으면 「(없음)」). 「작성 요령」 표는 항목 줄을 그대로."""
    lines = []
    for nt in notes or []:
        where = table_agent.WHERE_KO.get(nt.get("where"), nt.get("where"))
        if nt.get("where") == "guide":
            lines.append(f"- ({where}) {_short(nt.get('title'), 80) or '작성 요령'}")
            lines += ["  " + ln for ln in str(nt.get("text") or "").split("\n") if ln.strip()]
        elif (nt.get("text") or "").strip():
            lines.append(f"- ({where}) {_short(nt.get('text'), 300)}")
    return "\n".join(lines) if lines else "(없음)"


REQUEST_GUIDE = ("이 자리의 작성 요청(작성 지침 · 작성 계획 — 무엇을 어떤 꼴로 쓰는지입니다. 값은 material 에서 찾습니다: 사람이 정한 답도 material 의 「[사람이 정한 답]」 에 있고, "
                 "이 글에 든 예시 이름 · 예시 수는 값이 아닙니다)")


def guide_text(common, own, form=None, request=None):
    """지침 묶음 — 양식(양식 정보 「표」 절 — spec ② §12) · 공통 · 이 표. `table_excel_llm.guide_text` 와 같은 꼴.
    request = 양식 작성의 자리 턴이 보낸 요청 글(작성 지침 · 작성 계획 · 예시 — `doc_agent_api._fill_ask`): 자료(material)가 아니라 **지침**으로 싣는다 — 값의 근거 검사(`haystack`)에는 안 들고,
    그 글이 정한 고정 글(「해당 없음」 · 단위)은 where "rule" 의 근거(`rules_haystack` — 이 묶음 글을 받는다)로 찾는다."""
    parts = [("양식 표 지침(이 양식의 문서에 공통)", form), ("공통 표 지침", common), ("이 표 지침", own), (REQUEST_GUIDE, request)]
    out = [f"### {name}\n{text.strip()}" for name, text in parts if isinstance(text, str) and text.strip()]
    return "\n\n".join(out) if out else "(없음)"


def content(data, notes, guide, rules, job=""):
    """프롬프트 = 계약 + (할 일 프롬프트) + 작성요령 + 지침 + 칸 입력 규칙 + 자료(JSON)."""
    return (prompt_texts.contract(__name__) + (job or "") + "\n\n## 작성요령(문서에서)\n" + notes + "\n\n## 지침\n" + guide
            + "\n\n## 칸 입력 규칙(칸에 값을 넣는 방식 — 어긋나면 뒤의 것이 우선: 이 표 › 공통 › 기본)\n" + rules
            + "\n\n## 자료(JSON)\n" + json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def ask(data, notes, guide, rules, job="", *, call=None, effort=None, timeout=300.0):
    """한 번 호출(잠금 밖) → {"data": 답 | None, "prompt", "call": {backend, model, effort, ms, costUsd, error}}."""
    prompt = content(data, notes, guide, rules, job)
    res = (call or llm.call)(SCHEMA, prompt, "table-fill", timeout=timeout, effort=effort)
    info = {k: res.get(k) for k in ("backend", "model", "effort", "ms", "costUsd", "error")}
    got = res.get("data")
    return {"data": got if isinstance(got, dict) else None, "prompt": prompt, "call": info}


# ---- 답 검사 --------------------------------------------------------------------------------------------------------

def _squash(text):
    return re.sub(r"\s+", "", str(text or "")).lower()


def haystack(data):
    """근거 구절을 찾을 자료 글(공백 뗌) — 사용자가 준 자료 · 이 문서의 글 · 표 격자 글 · 표 앞뒤 글."""
    grid = " ".join(tok for row in data.get("grid") or [] for tok in row)
    return _squash(" ".join([data.get("material") or "", data.get("document") or "", grid, " ".join(data.get("before") or []), " ".join(data.get("after") or [])]))


def rules_haystack(*texts):
    """고정 글(where "rule")의 근거를 찾을 글(공백 뗌) — 작성요령 · 지침 · 칸 입력 규칙."""
    return _squash(" ".join(t or "" for t in texts))


def apply(data, an, hay="", hay_rules=""):
    """LLM 답 → {fills[{ref, cell, row, col, name, form, now, text, source, where, reason, quoted, warn[]}], rejected[{ref, text, why}], counts}.
    채울 칸(an.targets)의 주소만 받고 같은 칸은 처음 것만. 지금 글과 같은 답·빈 답은 「바꿀 것 없음」 으로 조용히 뺀다.
    체크 칸은 괄호 안 표시만 바뀌어야 한다(아니면 거절). warn = 사람이 볼 것(화면이 기본으로 안 고른다): 근거 구절을 자료에서 못 찾음 · 수 칸에 수가 아님 · 날짜 꼴이 자리표시와 다름 · 채워진 칸을 바꿈.
    where "rule"(지침·칸 입력 규칙이 정한 고정 글 — 「해당 없는 칸은 -」)의 근거 구절은 자료가 아니라 hay_rules 에서 찾는다.
    counts.left = 채울 칸 − 제안(LLM 이 답하지 않은 칸 + 검사에서 빠진 칸)."""
    targets = {t["ref"]: t for t in an["targets"]}
    fills, rejected, n_rej, seen = [], [], [0], set()

    def rej(ref, text, why):
        n_rej[0] += 1
        if len(rejected) < REJECTED_MAX:
            rejected.append({"ref": ref, "text": _short(text, 120), "why": why})

    items = data.get("fills") if isinstance(data, dict) else None
    for it in (items if isinstance(items, list) else [])[:ITEMS_MAX]:
        if not isinstance(it, dict):
            continue
        cell_s = str(it.get("cell") or "").strip().upper().replace("$", "")
        text = "\n".join(ln.rstrip() for ln in str(it.get("text") or "").replace("\r", "").replace(R.BR, "\n").split("\n")).strip()
        pos = F.pos(cell_s)
        ref = an["anchor"].get(pos) if pos is not None else None
        if ref is None:
            rej(cell_s, text, "표에 없는 주소")
            continue
        t = targets.get(ref)
        if t is None:
            rej(ref, text, "채울 칸이 아님(머리 칸 · 셈하는 칸 · 이미 채운 칸 · 고른 범위 밖)")
            continue
        if ref in seen:
            rej(ref, text, "같은 칸을 두 번 답함")
            continue
        seen.add(ref)
        if not text or text == t["now"].strip():
            continue
        if len(text) > CELL_MAX:
            rej(ref, text, f"글이 너무 깁니다(> {CELL_MAX:,}자)")
            continue
        warn = []
        if t["form"] == "check":
            if _check_skel(text) != _check_skel(t["now"]):
                rej(ref, text, "체크 칸의 글이 바뀜(괄호 안 표시만 바꿀 수 있음)")
                continue
            if cell_form(text)[1]:
                continue   # 표시가 하나도 없다 — 바꿀 것 없음
        elif t["form"] == "date":
            if _date_skel(text) != _date_skel(t["now"]):
                warn.append("날짜 꼴이 자리표시와 다름")
        elif t["form"] in ("num", "pct"):
            got = HC.parse_num(" ".join(text.split()))
            if got.get("num") is None:
                warn.append("수가 아님")
            elif t["form"] == "pct" and re.search(r"[%％]\s*$", t["now"].strip()) and not got.get("pct"):
                warn.append("자리표시는 % 꼴")
        if not t["open"]:
            warn.append("이미 채운 칸을 바꿈")
        source = _short(it.get("source"), 200)
        where = str(it.get("where") or "").strip().lower()
        by_rule = where == "rule"
        quoted = len(_squash(source)) >= 2 and _squash(source) in (hay_rules if by_rule else hay)
        if not quoted:
            warn.append("근거 구절을 지침·규칙에서 못 찾음" if by_rule else "근거 구절을 자료에서 못 찾음")
        fills.append({"ref": ref, "cell": t["cell"], "row": t["row"], "col": t["col"], "name": t["name"], "form": t["form"], "now": t["now"], "text": text,
                      "source": source, "where": where if where in WHERES else "", "reason": _short(it.get("reason"), 200), "quoted": quoted, "warn": warn})
    fills.sort(key=lambda f: (f["row"], f["col"]))
    return {"fills": fills, "rejected": rejected,
            "counts": {"fills": len(fills), "clean": sum(1 for f in fills if not f["warn"]), "warn": sum(1 for f in fills if f["warn"]), "rejected": n_rej[0],
                       "left": len(targets) - len(fills)}}

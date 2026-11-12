"""헤딩 추출 — 표 도구(spec_헤딩_추출 ② §10): 표마다 붙일 **표 에이전트의 입력**(작성요령 · 사용자 지침 · 표 구조 · 수식)의 저장과 묶음 글.

- 저장: 작업 폴더 `works/<작업 id>/tables/<표 id>.json` {instructions, formulas, version, updated} + 공통 `tables/_common.json` {instructions, version, updated}.
  작업 저장이 꺼져 있거나(works.folder None) 작업 폴더가 없으면 메모리. version 은 저장마다 +1, 기대 version 이 다르면 heading_rules.StaleVersion(→ API 409).
- formulas = 엑셀식 보기(화면)의 사용자 수식 {A1 주소: "=…"} — "" 은 「§9 수식 끄기」(스크립트가 만든 수식을 쓰지 않음).
- rules = **칸 입력 규칙**(칸에 값을 넣는 방식 — 사용자 2026-11-12 "셀에 값을 넣는 방식이나 규칙도 들어 가야함"): 표마다·공통(`_common`)마다 글 하나. 앱 기본본 `DEFAULT_RULES` 가
  늘 맨 앞에 가고 공통 → 이 표 순으로 붙는다(어긋나면 뒤의 것이 우선). spec ② §18.
- `prompt()` 가 이 표의 기준을 한 글로 엮어(작성요령 · 지침 · 칸 입력 규칙 · 표 구조 · 수식) 화면에 미리 보인다 — **기준 확인용**이다. 이 글을 그대로 보내는 호출은 없다:
  「표 채우기」(spec ② §18 — `app/table_fill.py`)는 같은 원천(작성요령 · 지침 · 칸 입력 규칙)을 제 프롬프트 꼴로 따로 엮고, [표 구조]·[수식]·[사용자 수식] 은 보내지 않는다.
  저장한 지침 가운데 공통 지침과 표 양식으로 고른 표의 지침은 「표 만들기 · 서식 변환」(spec ② §11 — `app/table_llm.py`)의 LLM 호출에도 함께 간다.
- 작업 폴더 `tables/` 에는 표 LLM 호출의 상세 기록(`fill_<ms>.json`·`formula_<ms>.json`·`make_<ms>.json` — `works.add_detail`)도 쌓인다. `all_tables` 는 그것을 표 기록으로 읽지 않는다(`_DETAIL`)."""
import re
import threading
import time

from app import heading_rules as R
from app import works

COMMON = "_common"
TEXT_MAX = 20_000
FORMULA_MAX = 500
FORMULAS_MAX = 400
GRID_CELLS = 400
_REF = re.compile(r"^[A-Z]{1,3}[1-9]\d{0,3}$")
_TID = re.compile(r"^[A-Za-z]\w{0,30}$")
_DETAIL = re.compile(r"^(?:fill|formula|make)_\d+$")   # 같은 폴더의 LLM 호출 상세 기록 — 표 id 가 아니다
_LOCK = threading.RLock()
_MEMORY = {}  # {(작업 id, 표 id): 기록} — 저장 끔·작업 폴더 없음

ROLE_KO = {"colhead": "열헤더", "rowhead": "행헤더", "corner": "귀퉁이", "field": "필드", "title": "제목", "note": "안내", "spacer": "간격"}
KIND_KO = {"matrix": "매트릭스", "form": "키-값", "list": "한 열", "title": "제목", "note": "안내", "spacer": "간격", "plain": "헤더 없음"}
BASIS_KO = {"stage": "단계", "year": "차년도", "org": "기관", "period": "연도", "total": "합계", "ratio": "비율"}
STATUS_KO = {"ok": "일치", "mismatch": "불일치", "missing": "미기입", "incomplete": "미검증(일부 빈 칸)", "blank": "미검증(빈 칸)", "nonnumeric": "수가 아님"}
WHERE_KO = {"before": "표 앞", "cell": "표 안", "after": "표 뒤", "guide": "작성 요령 표"}
GUIDE_TEXT = 6_000   # 묶음 글에 싣는 「작성 요령」 표 하나의 글 길이
# 칸 입력 규칙 — 앱 기본본(spec ② §18): 문서·양식과 무관하게 늘 함께 가는 「칸에 값을 넣는 방식」. 공통 규칙 · 이 표 규칙이 뒤에 붙고, 어긋나면 뒤의 것이 우선이다.
DEFAULT_RULES = """\
- 체크 칸(「[ ]」·「□」): 해당하는 항목의 괄호 안에만 「√」 를 넣는다(「□」 는 「■」 로 바꾼다). 괄호 밖의 글·항목 이름·순서는 한 글자도 바꾸지 않는다. 어느 항목인지 알 수 없으면 표시하지 않는다.
- 숫자 칸: 칸에 있던 자리표시(「0,000」·「000,000」)의 꼴을 따른다 — 천 단위 쉼표, 단위 글자(원·천원)는 넣지 않는다. 금액은 표의 단위(「단위: 천원」)에 맞춘 수를 적고, 단위를 바꿔 셈했으면 근거에 적는다.
- 비율 칸(「00%」·「(%)」 열): 「%」 를 붙이는지, 소수 몇 자리인지는 자리표시와 같은 열의 다른 칸을 따른다.
- 날짜·기간 칸: 자리표시(「YYYY.MM.DD」·「20  년  월  일」·「YYYY~YYYY」)의 구분 기호와 자릿수를 그대로 두고 숫자만 채운다.
- 글 칸: 자료의 표현(기관명·과제명·번호 같은 고유명사)을 그대로 옮긴다 — 줄이거나 다듬지 않는다. 한 칸에 항목이 여럿이면 줄을 바꿔 적는다.
- 값이 자료에 없거나 확실하지 않은 칸은 비워 둔다 — 「-」·「해당 없음」·「미정」 을 지어 넣지 않는다(지침이 그렇게 정한 때만 넣는다).
- 합계·소계·비율처럼 다른 칸으로 셈하는 칸, 머리 칸(행헤더·열헤더), 안내 칸에는 값을 넣지 않는다.
- 칸에 이미 있는 글(사람이 쓴 글)은 바꾸지 않는다 — 사용자가 다시 제안해 달라고 한 칸(filled)만, 자료와 다를 때 고친 글을 제안한다."""


def _check_tid(tid):
    if not isinstance(tid, str) or not (tid == COMMON or _TID.match(tid)):
        raise KeyError(tid)


def _path(wid, tid):
    d = works.folder(wid)
    return None if d is None else d / "tables" / f"{tid}.json"


def empty(tid):
    out = {"instructions": "", "rules": "", "version": 0, "updated": None}
    if tid != COMMON:
        out["formulas"] = {}
    return out


def get(wid, tid):
    """저장된 기록(없으면 빈 기록) — {instructions, rules, formulas?, version, updated}. rules = 칸 입력 규칙(옛 기록에는 없다 — 빈 글)."""
    _check_tid(tid)
    with _LOCK:
        p = _path(wid, tid)
        rec = _MEMORY.get((wid, tid)) if p is None or not p.is_file() else works._read_json(p)
    out = empty(tid)
    if isinstance(rec, dict):
        if isinstance(rec.get("instructions"), str):
            out["instructions"] = rec["instructions"]
        if isinstance(rec.get("rules"), str):
            out["rules"] = rec["rules"]
        if tid != COMMON and isinstance(rec.get("formulas"), dict):
            out["formulas"] = {k: v for k, v in rec["formulas"].items() if isinstance(k, str) and isinstance(v, str)}
        try:
            out["version"] = int(rec.get("version") or 0)
        except (TypeError, ValueError):
            out["version"] = 0
        out["updated"] = rec.get("updated")
    return out


def all_tables(wid):
    """{common, tables: {표 id: 기록}} — 저장된 것만."""
    with _LOCK:
        d = works.folder(wid)
        ids = {t for (w, t) in _MEMORY if w == wid}
        if d is not None and (d / "tables").is_dir():
            ids |= {p.stem for p in (d / "tables").glob("*.json")}
    ids.discard(COMMON)
    return {"common": get(wid, COMMON), "tables": {t: get(wid, t) for t in sorted(ids) if _TID.match(t) and not _DETAIL.match(t)}}


def _check_formulas(formulas):
    if not isinstance(formulas, dict) or len(formulas) > FORMULAS_MAX:
        raise ValueError(f"formulas 는 {{A1 주소: 수식}} 객체({FORMULAS_MAX}개 이하)")
    for k, v in formulas.items():
        if not isinstance(k, str) or not _REF.match(k):
            raise ValueError(f"수식 주소는 A1 꼴이어야 합니다: {k!r}")
        if not isinstance(v, str) or len(v) > FORMULA_MAX or (v and not v.startswith("=")):
            raise ValueError(f"수식 {k} 는 「=」 로 시작하는 {FORMULA_MAX}자 이하 글(빈 글 = 수식 끄기)")


def save(wid, tid, *, instructions=None, formulas=None, rules=None, expect=None, reason="화면"):
    """지침·칸 입력 규칙·수식 저장 → 새 기록. expect = 기대 version(다르면 R.StaleVersion). 주지 않은 항목은 그대로."""
    _check_tid(tid)
    if instructions is not None and (not isinstance(instructions, str) or len(instructions) > TEXT_MAX):
        raise ValueError(f"지침은 {TEXT_MAX:,}자 이하의 문자열")
    if rules is not None and (not isinstance(rules, str) or len(rules) > TEXT_MAX):
        raise ValueError(f"칸 입력 규칙은 {TEXT_MAX:,}자 이하의 문자열")
    if formulas is not None:
        if tid == COMMON:
            raise ValueError("공통 지침에는 수식이 없습니다")
        _check_formulas(formulas)
    expect = R.expect_version(expect)
    with _LOCK:
        cur = get(wid, tid)
        if expect is not None and expect != cur["version"]:
            raise R.StaleVersion(f"표 지침 {tid} 이 바뀌었습니다(지금 {cur['version']}, 요청 {expect})")
        new = dict(cur)
        if instructions is not None:
            new["instructions"] = instructions
        if rules is not None:
            new["rules"] = rules
        if formulas is not None:
            new["formulas"] = dict(formulas)
        new["version"] = cur["version"] + 1
        new["updated"] = round(time.time(), 3)
        p = _path(wid, tid)
        if p is None or not (p.parent.parent / "work.json").exists():  # 저장 끔 · 지운 작업 → 메모리
            _MEMORY[(wid, tid)] = new
        else:
            works._write_json(p, new)
            _MEMORY.pop((wid, tid), None)
    works.log(wid, "tableGuide", table=tid, chars=len(new["instructions"]), rules=len(new.get("rules") or ""), formulas=len(new.get("formulas") or {}),
              version=new["version"], reason=reason)
    return new


def rules_text(common, own, default=DEFAULT_RULES):
    """칸 입력 규칙 묶음 글 — 기본(앱) → 공통(이 문서의 모든 표) → 이 표. 빈 층은 뺀다. 어긋나면 뒤의 것이 우선(머리 문장에 적는다)."""
    parts = [("기본 규칙(앱)", default), ("공통 규칙(이 문서의 모든 표)", (common or {}).get("rules")), ("이 표 규칙", (own or {}).get("rules"))]
    return "\n\n".join(f"### {name}\n{text.strip()}" for name, text in parts if isinstance(text, str) and text.strip())


# ---- 에이전트 입력 묶음 ------------------------------------------------------------------------------------

def _clean(s, n=None):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if n is None or len(s) <= n else s[:n - 1] + "…"


def _col(c):
    s, c = "", c + 1
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return s


def ident(tb):
    """표 식별(화면·묶음 글 공용) — 3단계 결과의 표 하나 → 요약."""
    if not tb:
        return None
    return {k: tb.get(k) for k in ("id", "rows", "cols", "depth", "host", "before", "owner", "basis", "unit", "calc")} | {"cells": len(tb.get("cells") or [])}


def owner_text(o):
    if not o:
        return "모름(3단계 표 구조 없음)"
    if o.get("root"):
        return "문서 뿌리(위에 헤딩 없음)"
    s = _clean(o.get("text"), 80) or "(제목 없음)"
    if o.get("tplNo"):
        s += f" (T{o['tplNo']} L{o.get('level')})"
    if o.get("role") == "label":
        s += " [구분 라벨]"
    s += f" · 출처 {'2단계 그래프' if o.get('source') == 'stage2' else '1단계 어림'}"
    return s


def prompt(tb, common, own, *, tid=None, notes=None, form=None, forms=None):
    """에이전트에 줄 글 — [표 식별] [작성요령(문서에서)] [양식 지침](있을 때만) [공통 지침] [이 표 지침] [칸 입력 규칙] [표 구조] [수식] [사용자 수식].
    form = 이 문서 양식 정보의 「표」 절 글(heading_forms.table_guide — 양식마다 관리하는 표 요청, spec ② §12) — 비면 그 묶음은 없다.
    notes 의 where "guide" = 뒤따르는 「작성 요령」 표(`table_fill.guide_tables` — 글이 길어 줄째 싣는다). forms = 표에서 읽은 칸 꼴 요약 글(`table_fill.forms_text`)."""
    lines = ["[표 식별]"]
    tid = tid or (tb or {}).get("id") or "?"
    if tb:
        lines.append(f"표 {tid} · {tb.get('rows')}행×{tb.get('cols')}열 · 칸 {len(tb.get('cells') or [])}" + (" · 표 안 표" if (tb.get("depth") or 1) > 1 else ""))
        o = tb.get("owner") or {}
        lines.append(f"소속: {owner_text(o)}")
        if o.get("path"):
            lines.append(f"경로: {' › '.join(o['path'])}")
        if o.get("division"):
            d = o["division"]
            lines.append(f"구분 라벨: {_clean(d.get('text'), 60)}" + (f" ({'·'.join(BASIS_KO.get(b, b) for b in d.get('basis') or [])})" if d.get("basis") else ""))
        if tb.get("basis"):
            lines.append(f"구분: {'·'.join(BASIS_KO.get(b, b) for b in tb['basis'])}")
        if tb.get("unit"):
            lines.append(f"단위: {tb['unit']}")
        if tb.get("before"):
            lines.append(f"앞 문단: {_clean(tb['before'], 80)}")
    else:
        lines.append(f"표 {tid} — 3단계 표 구조 결과가 없어 소속·구조·수식을 모름(「표 구조」 를 만들면 채워짐)")
    lines.append("")
    lines.append("[작성요령(문서에서)]")
    notes = notes if notes is not None else (tb or {}).get("notes") or []
    if notes:
        for nt in notes:
            if nt.get("where") == "guide":   # 「작성 요령」 표 — 항목 줄(「1. 보안등급: …」)을 그대로
                lines.append(f"- ({WHERE_KO['guide']}) {_clean(nt.get('title'), 80) or '작성 요령'}")
                lines += ["  " + ln for ln in str(nt.get("text") or "")[:GUIDE_TEXT].split("\n") if ln.strip()]
                continue
            lines.append(f"- ({WHERE_KO.get(nt.get('where'), nt.get('where'))}) {_clean(nt.get('text'), 300)}")
    else:
        lines.append("(문서에서 찾은 작성요령 없음)")
    lines.append("")
    if isinstance(form, str) and form.strip():   # 양식 정보의 「표」 절 — 이 양식의 모든 문서에 공통(작업마다 적는 [공통 지침] 보다 바깥)
        lines.append("[양식 지침]")
        lines.append(form.strip())
        lines.append("")
    lines.append("[공통 지침]")
    lines.append((common or {}).get("instructions", "").strip() or "(없음)")
    lines.append("")
    lines.append("[이 표 지침]")
    lines.append((own or {}).get("instructions", "").strip() or "(없음)")
    lines.append("")
    lines.append("[칸 입력 규칙] (칸에 값을 넣는 방식 — 어긋나면 뒤의 것이 우선: 이 표 › 공통 › 기본)")
    lines.append(rules_text(common, own))
    if isinstance(forms, str) and forms.strip():
        lines.append(f"표에서 읽은 칸 꼴: {forms.strip()}")
    if tb:
        lines.append("")
        lines.append("[표 구조]")
        for s in tb.get("subtables") or []:
            (r0, r1), (c0, c1) = s.get("rows") or (0, 0), s.get("cols") or (0, 0)
            lines.append(f"- {s.get('id')} {KIND_KO.get(s.get('kind'), s.get('kind'))} · 행 {r0 + 1}–{r1} · 열 {c0 + 1}–{c1}"
                         + (f" · 헤더 행 {s.get('headerRows')} 열 {s.get('headerCols')}" if s.get("kind") in ("matrix", "form", "plain") else ""))
        cells = sorted(tb.get("cells") or [], key=lambda x: (x.get("row", 0), x.get("col", 0)))
        lines.append("격자(주소|역할|글):")
        rows = {}
        for x in cells[:GRID_CELLS]:
            rows.setdefault(x.get("row", 0), []).append(f"{_col(x.get('col', 0))}{x.get('row', 0) + 1}|{ROLE_KO.get(x.get('role'), x.get('role'))}|{_clean(x.get('text'), 30)}")
        for r in sorted(rows):
            lines.append("  " + " ; ".join(rows[r]))
        if len(cells) > GRID_CELLS:
            lines.append(f"  … ({len(cells) - GRID_CELLS}칸 더)")
        fs = tb.get("formulas") or []
        lines.append("")
        lines.append("[수식]" + ("" if fs else " (없음)"))
        for f in fs[:100]:
            lines.append(f"- {f.get('ref')} {f.get('formula')} → 기대 {f.get('expected') if f.get('expected') is not None else '—'} · 문서 {f.get('actual') if f.get('actual') is not None else '—'}"
                         f" · {STATUS_KO.get(f.get('status'), f.get('status'))}" + (f" · {f['note']}" if f.get("note") else ""))
        if len(fs) > 100:
            lines.append(f"- … ({len(fs) - 100}개 더)")
    user = {k: v for k, v in ((own or {}).get("formulas") or {}).items()}
    if user:
        lines.append("")
        lines.append("[사용자 수식]")
        for k in sorted(user, key=lambda s: (len(s), s)):
            lines.append(f"- {k} {user[k] or '(수식 끔)'}")
    return "\n".join(lines)

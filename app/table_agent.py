"""헤딩 추출 — 표 도구(spec_헤딩_추출 ② §10): 표마다 붙일 **표 에이전트의 입력**(작성요령 · 사용자 지침 · 표 구조 · 수식)의 저장과 묶음 글.

- 저장: 작업 폴더 `works/<작업 id>/tables/<표 id>.json` {instructions, formulas, version, updated} + 공통 `tables/_common.json` {instructions, version, updated}.
  작업 저장이 꺼져 있거나(works.folder None) 작업 폴더가 없으면 메모리. version 은 저장마다 +1, 기대 version 이 다르면 heading_rules.StaleVersion(→ API 409).
- formulas = 엑셀식 보기(화면)의 사용자 수식 {A1 주소: "=…"} — "" 은 「§9 수식 끄기」(스크립트가 만든 수식을 쓰지 않음).
- **LLM 호출은 아직 없다** — `prompt()` 가 에이전트에 줄 글을 만들어 화면에 미리 보인다(spec ④)."""
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
_LOCK = threading.RLock()
_MEMORY = {}  # {(작업 id, 표 id): 기록} — 저장 끔·작업 폴더 없음

ROLE_KO = {"colhead": "열헤더", "rowhead": "행헤더", "corner": "귀퉁이", "field": "필드", "title": "제목", "note": "안내", "spacer": "간격"}
KIND_KO = {"matrix": "매트릭스", "form": "키-값", "list": "한 열", "title": "제목", "note": "안내", "spacer": "간격", "plain": "헤더 없음"}
BASIS_KO = {"stage": "단계", "year": "차년도", "org": "기관", "period": "연도", "total": "합계", "ratio": "비율"}
STATUS_KO = {"ok": "일치", "mismatch": "불일치", "missing": "미기입", "incomplete": "미검증(일부 빈 칸)", "blank": "미검증(빈 칸)", "nonnumeric": "수가 아님"}
WHERE_KO = {"before": "표 앞", "cell": "표 안", "after": "표 뒤"}


def _check_tid(tid):
    if not isinstance(tid, str) or not (tid == COMMON or _TID.match(tid)):
        raise KeyError(tid)


def _path(wid, tid):
    d = works.folder(wid)
    return None if d is None else d / "tables" / f"{tid}.json"


def empty(tid):
    out = {"instructions": "", "version": 0, "updated": None}
    if tid != COMMON:
        out["formulas"] = {}
    return out


def get(wid, tid):
    """저장된 기록(없으면 빈 기록) — {instructions, formulas?, version, updated}."""
    _check_tid(tid)
    with _LOCK:
        p = _path(wid, tid)
        rec = _MEMORY.get((wid, tid)) if p is None or not p.is_file() else works._read_json(p)
    out = empty(tid)
    if isinstance(rec, dict):
        if isinstance(rec.get("instructions"), str):
            out["instructions"] = rec["instructions"]
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
    return {"common": get(wid, COMMON), "tables": {t: get(wid, t) for t in sorted(ids) if _TID.match(t)}}


def _check_formulas(formulas):
    if not isinstance(formulas, dict) or len(formulas) > FORMULAS_MAX:
        raise ValueError(f"formulas 는 {{A1 주소: 수식}} 객체({FORMULAS_MAX}개 이하)")
    for k, v in formulas.items():
        if not isinstance(k, str) or not _REF.match(k):
            raise ValueError(f"수식 주소는 A1 꼴이어야 합니다: {k!r}")
        if not isinstance(v, str) or len(v) > FORMULA_MAX or (v and not v.startswith("=")):
            raise ValueError(f"수식 {k} 는 「=」 로 시작하는 {FORMULA_MAX}자 이하 글(빈 글 = 수식 끄기)")


def save(wid, tid, *, instructions=None, formulas=None, expect=None, reason="화면"):
    """지침·수식 저장 → 새 기록. expect = 기대 version(다르면 R.StaleVersion). 주지 않은 항목은 그대로."""
    _check_tid(tid)
    if instructions is not None and (not isinstance(instructions, str) or len(instructions) > TEXT_MAX):
        raise ValueError(f"지침은 {TEXT_MAX:,}자 이하의 문자열")
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
    works.log(wid, "tableGuide", table=tid, chars=len(new["instructions"]), formulas=len(new.get("formulas") or {}), version=new["version"], reason=reason)
    return new


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


def prompt(tb, common, own, *, tid=None, notes=None):
    """에이전트에 줄 글 — [표 식별] [작성요령(문서에서)] [공통 지침] [이 표 지침] [표 구조] [수식] [사용자 수식]."""
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
            lines.append(f"- ({WHERE_KO.get(nt.get('where'), nt.get('where'))}) {_clean(nt.get('text'), 300)}")
    else:
        lines.append("(문서에서 찾은 작성요령 없음)")
    lines.append("")
    lines.append("[공통 지침]")
    lines.append((common or {}).get("instructions", "").strip() or "(없음)")
    lines.append("")
    lines.append("[이 표 지침]")
    lines.append((own or {}).get("instructions", "").strip() or "(없음)")
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

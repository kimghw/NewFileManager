"""서식 이름 · 서식 지도 저장(spec_서식복사 ② §19-2 · §19-3) — 2026-11-14 사용자 "서식이름도 변경할 수 있고, 보통 문서 이름 사업계획서: body1 이런식이면 될거 같아".

- 이름 꼴 = 「<문서 이름>: <갈래><번호>」 — 문서 이름 = 파일 이름에서 찾은 **문서 종류 낱말**(사용자 답 「문서 종류 낱말」 — 「사업계획서」 · 「연차보고서」 …),
  못 찾으면 파일 이름(확장자 · 앞 번호 「1. 」 뺌). 사람이 문서마다 고칠 수 있다(`prefix` — 서식 지도에서).
- 갈래 표기(`tail`): 내용 서식(템플릿) `T<no>` · 그 레벨 `T<no> L<k>` · 문단 서식 = 역할(`body`·`caption`·`note`·`box`·`toc` — 그 밖·모름은 `body`) + 그 역할 안 번호 ·
  테이블 `table<n>` · 표지 `cover` · 쪽 설정 `page`. 번호는 갈래마다 1부터, 서식 복사 열의 후보 차례(= 서식 지도의 차례)대로.
- 서식 지도의 문서별 저장(`load`·`change`): `{version, prefix(사람이 고친 문서 이름 | None), names{자리 이름 키: 이름}, pending{자리 이름 키: {고친 값}}}` —
  작업 폴더의 `formats.json`(작업 저장이 꺼져 있으면 메모리). 자리 이름 키는 문서를 다시 분석해도 같은 것(템플릿 = 앵커, 문단 묶음 = 대표 문단 id, 표 묶음 = 대표 표 id) — format_map 이 짓는다.
  문서 편집이 아니므로 실행 취소에 들지 않는다.
"""
import copy
import json
import re
import threading
from pathlib import PurePath

from app import works

NAME_MAX = 60  # style_lib.NAME_MAX 와 같은 값(서식 이름 1~60자)
# 문서 종류 낱말 — 긴 것이 먼저 잡힌다(「연구개발계획서」 가 「계획서」 보다 먼저). 띄어 쓴 것(「사업 계획서」)도 잡는다.
DOC_KINDS = ("연구개발계획서", "연구개발보고서", "연차실적보고서", "사업계획서", "사업신청서", "연차보고서", "최종보고서", "결과보고서", "중간보고서", "연구계획서",
             "기술수요조사서", "수요조사서", "제안요청서", "과업지시서", "제안서", "신청서", "회의록", "보고서", "계획서")
PARA_TAILS = ("caption", "note", "box", "toc")  # 문단 서식 역할 가운데 이름에 그대로 쓰는 것 — 그 밖(body · other · 모름)은 body
FILE = "formats.json"

_MEM, _LOCK = {}, threading.Lock()


def doc_prefix(file_name) -> str:
    """파일 이름 → 문서 이름(이름의 앞부분). 「1. 2027년도 수소전기추진연구팀 사업계획서(최종).hwpx」 → 「사업계획서」."""
    stem = PurePath(str(file_name or "")).stem if file_name else ""
    flat = re.sub(r"\s+", "", stem)
    for k in sorted(DOC_KINDS, key=len, reverse=True):
        if k in flat:
            return k
    s = re.sub(r"^\s*\d+\s*[.)]\s*", "", stem).strip()
    return re.sub(r"\s+", " ", s) or "문서"


def para_tail(role) -> str:
    """문단 서식의 역할 → 갈래 표기(번호 앞)."""
    return role if role in PARA_TAILS else "body"


def tpl_tail(no, level=None) -> str:
    return f"T{no}" if level is None else f"T{no} L{level}"


def number(tails) -> list:
    """[갈래 표기 …](차례대로) → [갈래 표기 + 번호 …] — 갈래마다 1부터(「body」·「body」·「caption」 → body1 · body2 · caption1)."""
    seen, out = {}, []
    for t in tails:
        seen[t] = seen.get(t, 0) + 1
        out.append(f"{t}{seen[t]}")
    return out


def name(prefix, tail) -> str:
    """「<문서 이름>: <갈래><번호>」 — 60자를 넘으면 문서 이름 쪽을 줄인다(「…」)."""
    prefix = re.sub(r"\s+", " ", str(prefix or "")).strip() or "문서"
    tail = re.sub(r"\s+", " ", str(tail or "")).strip()
    room = NAME_MAX - len(tail) - 2
    if len(prefix) > room:
        prefix = prefix[:max(1, room - 1)].rstrip() + "…"
    return f"{prefix}: {tail}"[:NAME_MAX]


# ---- 이름 키(서식 지도의 names · 서식 복사 열의 기본 이름이 같이 쓴다) -----------------------------------------------
# 문서를 다시 분석해도 같은 자리를 가리키는 키 — 템플릿 = 그래프 앵커(「body:□›o›-」), 그 레벨 = 앵커#레벨, 문단 묶음 = 대표 문단 id, 표 묶음 = 대표 표 id.

def tpl_key(anchor) -> str:
    return f"tpl:{anchor}"


def level_key(anchor, level) -> str:
    return f"tpl:{anchor}#{level}"


def para_key(rep_pid) -> str:
    return f"para:{rep_pid}"


def table_key(rep_tid) -> str:
    return f"table:{rep_tid}"


PAGE_KEY, COVER_KEY = "page", "cover"


def keys_for(cands) -> dict:
    """서식 복사 후보(`style_extract.candidates` 의 꼴 {tables, texts, paras, pages, covers}) → {(갈래, 후보 key): (이름 키, 갈래 표기)}.
    갈래 = "text"(내용 서식 — 템플릿) · "para" · "table" · "page" · "cover". 번호는 후보 차례(= 서식 복사 열의 탭 차례 = 서식 지도의 차례)로 갈래마다 1부터 —
    서식 지도(format_map)와 서식 복사 열(style_api 의 defaultName)이 **이 함수 하나로** 같은 이름을 짓는다."""
    out = {}
    for c in cands.get("texts") or []:
        t = c.get("template") or {}
        if t.get("no") is None:
            continue
        out[("text", c["key"])] = (tpl_key(t.get("anchor") or t.get("name") or c["key"]), tpl_tail(t["no"]))
    paras = list(cands.get("paras") or [])
    for c, tail in zip(paras, number([para_tail(c.get("role")) for c in paras])):
        out[("para", c["key"])] = (para_key(c["key"]), tail)
    tables = list(cands.get("tables") or [])
    for c, tail in zip(tables, number(["table"] * len(tables))):
        out[("table", c["key"])] = (table_key(c.get("table") or c["key"]), tail)
    for c in cands.get("pages") or []:
        out[("page", c.get("key") or "page")] = (PAGE_KEY, "page")
    for c in cands.get("covers") or []:
        out[("cover", c.get("key") or "cover")] = (COVER_KEY, "cover")
    return out


def default_names(cands, prefix, names=None) -> dict:
    """→ {(갈래, 후보 key): 이름} — 사람이 서식 지도에서 고친 이름(names[이름 키])이 있으면 그것, 없으면 「<문서 이름>: <갈래><번호>」."""
    names = names or {}
    return {k: names.get(nk) or name(prefix, tail) for k, (nk, tail) in keys_for(cands).items()}


# ---- 서식 지도의 문서별 저장 ----------------------------------------------------------------------------------

def _empty():
    return {"version": 0, "prefix": None, "names": {}, "pending": {}}


def _dir(wid):
    d = works.folder(wid)
    return d if d is not None and (d / "work.json").is_file() else None


def load(wid) -> dict:
    """그 작업의 서식 지도 저장 — 늘 {version, prefix, names, pending} 가 있는 사본."""
    d = _dir(wid)
    got = (works._read_json(d / FILE) if d is not None and (d / FILE).is_file() else _MEM.get(wid)) or {}
    out = _empty()
    out["version"] = int(got.get("version") or 0)
    p = got.get("prefix")
    out["prefix"] = p.strip() if isinstance(p, str) and p.strip() else None
    out["names"] = {str(k): v for k, v in (got.get("names") or {}).items() if isinstance(v, str) and v.strip()} if isinstance(got.get("names"), dict) else {}
    out["pending"] = {str(k): v for k, v in (got.get("pending") or {}).items() if isinstance(v, dict) and v} if isinstance(got.get("pending"), dict) else {}
    return copy.deepcopy(out)


def change(wid, fn) -> dict:
    """저장을 읽어 fn(data) 로 고쳐 쓴다(한 번에 하나 · version +1). fn 이 던지면 안 쓴다. → 고친 사본."""
    with _LOCK:
        data = load(wid)
        fn(data)
        data["version"] = int(data.get("version") or 0) + 1
        d = _dir(wid)
        if d is not None:
            works._write_json(d / FILE, data)
        else:
            _MEM[wid] = json.loads(json.dumps(data, ensure_ascii=False))
        return copy.deepcopy(data)


def prefix_of(wid, file_name) -> tuple:
    """→ (문서 이름, auto) — 사람이 고친 것이 있으면 그것(auto False), 없으면 파일 이름에서(auto True)."""
    p = load(wid).get("prefix")
    return (p, False) if p else (doc_prefix(file_name), True)

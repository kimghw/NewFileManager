"""양식 지침 YAML — 양식(연차보고서 · 연구개발계획서 …)마다 본문 · 표 · 서브 테이블의 작성 지침 + 작성 예시 + 주요 항목을 **YAML 파일 하나**로(spec_양식작성 ② §5-8).
2026-11-26 사용자 "연차보고서, 사업계획서등 양식이 있는 문서들은 ymal 로 본문이랑 테이블 작성지침을 관리 … 테이블은 서브 테이블 별로 … 어떤 본문에서의 어떤 테이블에서의 서브테이블인지 구조가 있어야해 …
사용자가 작성예시나, 샘플등을 주고 향후 LLM이 작성할때 이 부분을 참조 … 구성맞추기에서 이 문서의 주요 키워드가 되는 항목들도 그 yaml 에 … 연차보고서 이관 뿐 아니라 양식작성에도 동일하게 이 패턴".
설계는 astra · Fable 검토의 합의(artifacts/form_guide_yaml_astra_2026-11-26/ — 에이전트 판단 · 사용자 확인 전).

- 파일 = 양식 정보 md 의 짝 `forms/<양식 키>.guide.yaml`(같은 폴더 · 같은 키 · git 관리 · env `NFM_FORMS` — `heading_forms.forms_dir`). 파일 하나가 원본(기본본 · 사본을 가르지 않는다 — md 와 같다).
  쓸 때는 읽었을 때의 sha1 을 견주고(다르면 StaleVersion) 고치기 전 글은 헤딩 저장소 `forms_history/<키>.guide/` 에 남긴다.
- 꼴(`parse` 가 검사 · 정리): `schema` · `form` · `theme`(테마 YAML 의 테마 id) · `keywords[{id, name, output, labels[], place?, how?}]`(주요 항목 — output = 프로젝트 구성 값의 필드
  stages · orgs · period · current · subs, 빈 글 = 구성 값이 아닌 문서 항목) · `sections[{id, path[], guides[], examples[], tables[{id, head, guides, examples, fields[{label, guides}], subtables[{id, head, guides, examples, fields}]}]}]`.
  지침 = {text, origin: user | llm, from?(작업 id), date?} · 예시 = {text, note?, origin, from?, date?}.
- **문서에 있는 작성요령(문서의 지침 — form_guides)은 여기 옮겨 적지 않는다**(작업마다 문서에서 다시 읽는다 — 두 번 실리면 예산만 쓴다: Fable P1-1). 여기 드는 것은 문서에 없는 것 — 사람이 정한 지침 · 확인한 LLM 규칙 · 예시 · 주요 항목.
- **저절로 쌓지 않는다**: 작업의 사람 지침 · 04 작성 지침 보완의 규칙은 작업 폴더에 있는 「후보」(`candidates`)이고, 사람이 고른 것만 `promote` 가 올린다(astra · Fable P1). 올린 LLM 규칙은 얼린다(사람이 고칠 때만 바뀜).
- 자리 잇기(`locate`): 절 = 헤딩 그래프의 본문 헤딩 줄의 **경로**(조상 헤딩 글 → 그 줄)를 좁게 정규화(`norm`)해 꼭 같을 때 — 같은 경로가 여럿이면(기관마다 되풀이) 모두 같은 항목을 읽는다 ·
  표 = 그 절의 표(문서 차례로 바로 앞의 헤딩이 그 절) 가운데 머리글 지문(`head_sig` — 음영 칸 글 · 숫자 · 빈칸 · 부호 뺌)이 같은 것 · 서브 테이블 = 그 표의 띠(3단계 판정 `subtables` — 둘 이상일 때) 가운데 띠 머리글 지문이 같은 것 ·
  필드 = 그 표(띠) 안에서 글이 라벨과 같은 칸. **짐작하지 않는다** — 문서 전체에서 하나뿐인 표 · 같은 차례의 띠로 넘어가지 않고, 못 이은 항목은 `unmatched` 로 보인다.
- 읽는 곳: `place_guides_api.index_of` 가 `overlay` 로 그 자리의 지침 목록에 src "form" 으로 얹는다(이관 3단계의 LLM 셋 · 양식 작성 06 이후 · 「지침」 열이 같이 읽는다) ·
  예시는 지침 목록에 섞지 않고 `examples` 로 따로(글을 쓰는 호출 — 양식 작성의 초안 요청만 · 자리마다 하나 · 짧게: Fable P1-3 · astra P2-5).
- 이 모듈은 서버 · 세션을 모른다(문서 블록 · 그래프 · 3단계 표 목록을 인자로 받는다) — 끝점은 `app/form_guide_yaml_api.py`."""
import hashlib
import os
import re
import threading
import time

import yaml

from app import heading_forms as HF
from app import heading_rules as R
from app.headings import iter_blocks

SCHEMA = 1
SUFFIX = ".guide.yaml"
TEXT_MAX = 400_000            # 파일 하나
GUIDE_MAX, EXAMPLE_MAX = 2000, 1500   # 지침 하나 · 예시 하나(저장)
EXAMPLE_SEND = 300            # 초안 요청에 싣는 예시 하나(astra 「자리당 1개 · 300자」)
PATH_MAX, HEAD_MAX, LABEL_MAX, NOTE_MAX = 12, 400, 120, 200
ITEMS_MAX = 40                # 한 자리의 지침 · 예시 수
OUTPUTS = ("", "stages", "orgs", "period", "current", "subs")   # 주요 항목이 채우는 프로젝트 구성 값의 필드(빈 글 = 구성 값이 아닌 문서 항목)
ORIGINS = ("user", "llm")
KIND = "양식 지침"
KIND_DOC = "양식 지침 — 문서 전체"   # 루트 guides[](일반 사용자 가이드라인 — ② §5-9)
HEAD_SEP = " | "
ID = re.compile(r"^[A-Za-z0-9_.\-]{1,60}$")
_DROP = re.compile(r"[\W\d_]+")   # 머리글 지문에서 빼는 것 — table_kv._TYPE_DROP 과 같은 규칙(「1차년도」·「2차년도」 는 같은 머리글)
_HEAD_CELL = 24
_LOCK = threading.RLock()

HEADER = ("# 양식 지침 — {name}. 본문 · 표 · 서브 테이블의 작성 지침 + 작성 예시 + 주요 항목(spec/spec_양식작성.md ② §5-8).\n"
          "# 문서에 이미 있는 작성요령은 적지 않는다(작업마다 문서에서 읽는다). 저장은 앱(「양식 지침」 열)이나 이 파일을 고쳐서 — 앱이 저장하면 주석은 이 머리만 남는다.\n"
          "# guides(맨 위) = 문서 전체에 닿는 일반 사용자 가이드라인(어느 과제에나 맞는 것 — 과제마다 다른 것은 프로젝트의 「문서 목적」, 다른 규정이 요구하는 것은 「규정」 rules.yaml).\n"
          "# sections[].path = 헤딩 경로(제목 글 — 「N단계 · N차년도 · 기관N」 의 숫자와 「[… : 값]」 의 값은 견주지 않는다) · tables[].head = 머리글(음영 칸 글을 「 | 」 로) ·\n"
          "# subtables[].head = 서브 테이블(띠)의 머리 칸 글 · fields[].label = 칸의 라벨 글 · keywords[].output = 프로젝트 구성 값의 필드(stages · orgs · period · current · subs | 빈 글 = 문서 항목).\n")


class StaleVersion(R.StaleVersion):
    """읽었을 때와 파일이 다름(그 사이 다른 화면 · 사람이 고침)."""


# ---- 정규화 · 지문 ------------------------------------------------------------------------------------------

_TAIL_NOTE = re.compile(r"\s*※.*$")
_TAIL_PAREN = re.compile(r"\s*[\(（][^()（）]*(?:해당\s*시|작성|기재|기입|이내|선택)[^()（）]*[\)）]\s*$")
_BRACKET_VALUE = re.compile(r"(\[[^\]:：]*?)\s*[:：][^\]]*\]")
_COLON_VALUE = re.compile(r"^([^:：]{2,}?)\s*[:：].*$")
_DIV_NUM = re.compile(r"\d+\s*(?=단계|차\s*년도|차년도|년차)")
_ORG_NUM = re.compile(r"(기관(?:명)?)\s*\d+")   # 「공동연구개발기관2」 · 「공동연구개발기관명1」
_SPACE = re.compile(r"\s+")
_N = re.compile(r"(?<![A-Za-z])N(?=\s*(?:단계|차\s*년도|차년도|년차))|(?<=기관)N|(?<=기관명)N")   # 머리글 · 제목에 사람이 적는 자리표시 N


def norm(text):
    """제목 · 라벨 글 → 견줄 글(좁은 정규화 — Fable P1-4): 「※」 뒤와 꼬리의 안내 괄호(「(해당 시 작성)」)를 자르고, 「[… : 값]」 · 「라벨 : 값」 의 값을 빼고,
    구분 기준 글(「N단계」 · 「N차년도」 · 「공동연구개발기관N」)의 숫자만 N 으로, 빈칸을 뺀다. 개요 번호(「2-2.」)와 그 밖의 숫자는 그대로다."""
    t = " ".join(str(text or "").split())
    t = _TAIL_NOTE.sub("", t)
    t = _TAIL_PAREN.sub("", t)
    t = _BRACKET_VALUE.sub(r"\1]", t)
    m = _COLON_VALUE.match(t)
    if m and not t.startswith("["):
        t = m.group(1)
    t = _DIV_NUM.sub("N", t)
    t = _ORG_NUM.sub(r"\1N", t)
    return _SPACE.sub("", t)


def _cell_text(c):
    return " ".join(" ".join(b.get("text") or "" for b in iter_blocks(c.get("blocks") or ()) if b.get("type") == "paragraph").split())


def head_sig(parts):
    """머리글 칸 글들 → 지문(빈 글이면 "") — 칸마다 숫자 · 빈칸 · 부호를 빼고 24자까지 이은 것. YAML 에 「N차년도」 · 「기관N」 처럼 적은 N 도 숫자처럼 뺀다."""
    got = [s for s in (_DROP.sub("", _N.sub("", p or ""))[:_HEAD_CELL] for p in parts) if s]
    return "|".join(got)


def table_head(tb):
    """문서 블록의 표 → 머리글 칸 글 목록(음영 칸 — 없으면 첫 행)."""
    cells = sorted(tb.get("cells") or (), key=lambda c: (c.get("row", 0), c.get("col", 0)))
    heads = [_cell_text(c) for c in cells if c.get("shaded")]
    if not any(h.strip() for h in heads):
        top = min((c.get("row", 0) for c in cells), default=0)
        heads = [_cell_text(c) for c in cells if c.get("row", 0) == top]
    return [h for h in heads if h.strip()]


def head_text(parts):
    return HEAD_SEP.join(" ".join(p.split())[:60] for p in parts)[:HEAD_MAX]


def _sig_of_text(head):
    return head_sig(str(head or "").split(HEAD_SEP.strip()))


SIG_MAX = 4000


def node_sig(node):
    """YAML 의 표 · 서브 테이블 항목 → 머리글 지문. 저장한 `sig`(자르기 전 머리글로 만든 것)가 있으면 그것 — 머리글이 길어 `head` 가 HEAD_MAX 에서 잘린 표는 head 글로 만든 지문이 문서의 것과 달라
    영영 이어지지 않았다(검토 P1 — 「뼈대 채우기」 · 올리기를 할 때마다 같은 표의 항목이 새로 생겼다). 사람이 손으로 적은 항목(sig 없음)은 head 글로."""
    return (node or {}).get("sig") or _sig_of_text((node or {}).get("head"))


def _head_node(parts, **more):
    """문서의 머리글 칸 글들 → YAML 항목의 {head, sig?} — 지문은 **자르기 전**에 만들고, head 글로 다시 만든 지문과 다를 때만 `sig` 로 함께 적는다(같으면 사람이 읽는 head 만)."""
    head, sig = head_text(parts), head_sig(parts)
    return {**more, "head": head, **({"sig": sig} if sig and sig != _sig_of_text(head) else {})}


def band_head(t3, band):
    """3단계 표 레코드 + 띠 → 그 띠의 머리 칸 글 목록(띠 안 머리 행 · 머리 열의 칸 — 행 · 열 차례)."""
    r0, r1 = band["rows"]
    c0, c1 = band["cols"]
    hr, hc = int(band.get("headerRows") or 0), int(band.get("headerCols") or 0)
    out = []
    for x in sorted(t3.get("cells") or (), key=lambda c: (c.get("row", 0), c.get("col", 0))):
        r, c = x.get("row", 0), x.get("col", 0)
        if not (r0 <= r < r1 and c0 <= c < c1):
            continue
        if r < r0 + hr or c < c0 + hc or x.get("role") in ("colhead", "rowhead", "title"):
            t = " ".join((x.get("text") or "").split())
            if t and t not in out:
                out.append(t)
    return out


# ---- 파일 ---------------------------------------------------------------------------------------------------

def path_of(key):
    HF.check_key(key)
    d = HF.forms_dir()
    return None if d is None else d / f"{key}{SUFFIX}"


def _sha1(text):
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def _s(v, n):
    t = "" if v is None or isinstance(v, (bool, list, dict)) else " ".join(str(v).split())
    return t[:n]


def _long(v, n):
    t = "" if v is None or isinstance(v, (bool, list, dict)) else str(v).replace("\r\n", "\n").strip()
    return t[:n]


def _items(raw, kind, strict, where):
    """지침 · 예시 목록 정리. kind = guide | example."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        if strict:
            raise ValueError(f"{where} 의 {kind}s 는 목록이어야 합니다")
        return []
    out, seen = [], set()
    for x in raw:
        if isinstance(x, str):
            x = {"text": x}
        if not isinstance(x, dict):
            if strict:
                raise ValueError(f"{where} 의 항목은 「text: …」 묶음이어야 합니다")
            continue
        text = _long(x.get("text"), GUIDE_MAX if kind == "guide" else EXAMPLE_MAX)
        if not text:
            if strict:
                raise ValueError(f"{where} 에 글(text)이 빈 항목이 있습니다")
            continue
        if text in seen:
            continue
        seen.add(text)
        origin = x.get("origin")
        if origin is None or origin == "":
            origin = "user"
        elif origin not in ORIGINS:   # 모르는 출처를 조용히 「user」 로 바꾸지 않는다(검토 P1 — 손으로 적은 `origin: rule` 이 사람 지침으로 굳었다): 엄격 읽기는 오류 · 저장된 파일 읽기는 적힌 글 그대로
            if strict:
                raise ValueError(f"{where} 의 origin 은 {' | '.join(ORIGINS)} 입니다({origin!r}) — 규정은 「규정」(rules.yaml)에 적습니다")
            origin = _s(origin, 20) or "user"
        it = {"text": text, "origin": origin}
        if kind == "example" and _s(x.get("note"), NOTE_MAX):
            it["note"] = _s(x.get("note"), NOTE_MAX)
        for k in ("from", "date"):
            if _s(x.get(k), 40):
                it[k] = _s(x.get(k), 40)
        out.append(it)
    if len(out) > ITEMS_MAX and strict:
        raise ValueError(f"{where} 의 항목은 {ITEMS_MAX}개까지입니다")
    return out[:ITEMS_MAX]


def _fields(raw, strict, where):
    out = []
    for x in raw or ():
        if not isinstance(x, dict) or not _s(x.get("label"), LABEL_MAX):
            if strict:
                raise ValueError(f"{where} 의 fields 항목에는 label 이 있어야 합니다")
            continue
        out.append({"label": _s(x.get("label"), LABEL_MAX), "guides": _items(x.get("guides"), "guide", strict, f"{where} 칸 「{_s(x.get('label'), 20)}」")})
    return out


def _id(x, strict, where, seen):
    v = x.get("id")
    v = str(v) if isinstance(v, (str, int)) and not isinstance(v, bool) else ""
    if not ID.match(v):
        if strict:
            raise ValueError(f"{where} 의 id 는 영문 · 숫자 · . _ - 60자까지입니다({x.get('id')!r})")
        return None
    if v in seen:
        if strict:
            raise ValueError(f"id 「{v}」 가 두 번 나옵니다")
        return None
    seen.add(v)
    return v


def parse(text, key=None, strict=True):
    """YAML 글 → 정리한 양식 지침. strict 면 틀린 꼴은 ValueError(화면에서 고친 글의 검사), 아니면 쓸 수 있는 것만 남긴다(저장된 파일 읽기)."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("YAML 글이 비었습니다")
    if len(text) > TEXT_MAX:
        raise ValueError(f"YAML 글은 {TEXT_MAX:,}자까지입니다")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        raise ValueError("YAML 을 읽을 수 없습니다" + (f"({mark.line + 1}번째 줄 — {getattr(e, 'problem', '') or '꼴이 틀림'})" if mark else f"({e})")) from e
    if not isinstance(data, dict):
        raise ValueError("YAML 의 맨 위는 「키: 값」 묶음이어야 합니다")
    form = _s(data.get("form"), 60) or (key or "")
    if key is not None and form != key:
        raise ValueError(f"form 은 파일의 양식 키 「{key}」 여야 합니다")
    seen = set()
    out = {"schema": SCHEMA, "form": form, "theme": _s(data.get("theme"), 40), "guides": _items(data.get("guides"), "guide", strict, "문서 전체(guides)"), "keywords": [], "sections": []}   # guides = 문서 전체 · 어느 과제에나 맞는 일반 사용자 가이드라인(② §5-9 — 자리가 없는 지침)
    for x in data.get("keywords") or ():
        if not isinstance(x, dict):
            if strict:
                raise ValueError("keywords 의 항목은 「id · name · …」 묶음이어야 합니다")
            continue
        kid = _id(x, strict, "keywords", seen)
        name = _s(x.get("name"), 60)
        if kid is None or not name:
            if strict and kid is not None:
                raise ValueError(f"주요 항목 「{kid}」 에 name 이 없습니다")
            continue
        output = x.get("output") or ""
        if output not in OUTPUTS:
            if strict:
                raise ValueError(f"주요 항목 「{kid}」 의 output 은 {', '.join(o for o in OUTPUTS if o)} 가운데 하나이거나 빈 글입니다")
            output = ""
        labels = [_s(v, LABEL_MAX) for v in x.get("labels") or () if _s(v, LABEL_MAX)] if isinstance(x.get("labels"), list) else []
        k = {"id": kid, "name": name, "output": output, "labels": labels[:12]}
        for f, n in (("place", 60), ("how", 700)):
            if _s(x.get(f), n):
                k[f] = _s(x.get(f), n)
        out["keywords"].append(k)
    for sx in data.get("sections") or ():
        if not isinstance(sx, dict):
            if strict:
                raise ValueError("sections 의 항목은 「id · path · …」 묶음이어야 합니다")
            continue
        sid = _id(sx, strict, "sections", seen)
        path = [_s(p, 200) for p in sx.get("path") or () if _s(p, 200)] if isinstance(sx.get("path"), list) else []
        if sid is None:
            continue
        if not path or len(path) > PATH_MAX:
            if strict:
                raise ValueError(f"절 「{sid}」 의 path 는 제목 글 1~{PATH_MAX}개의 목록입니다")
            continue
        where = f"절 「{sid}」"
        sec = {"id": sid, "path": path, "guides": _items(sx.get("guides"), "guide", strict, where), "examples": _items(sx.get("examples"), "example", strict, where), "tables": []}
        for tx in sx.get("tables") or ():
            if not isinstance(tx, dict):
                continue
            tid = _id(tx, strict, f"{where} 의 표", seen)
            head = _s(tx.get("head"), HEAD_MAX)
            if tid is None:
                continue
            if not _sig_of_text(head):
                if strict:
                    raise ValueError(f"표 「{tid}」 의 head(머리글 글)가 없습니다")
                continue
            tw = f"표 「{tid}」"
            tb = {"id": tid, "head": head, "guides": _items(tx.get("guides"), "guide", strict, tw), "examples": _items(tx.get("examples"), "example", strict, tw),
                  "fields": _fields(tx.get("fields"), strict, tw), "subtables": []}
            if _s(tx.get("sig"), SIG_MAX):
                tb["sig"] = _s(tx.get("sig"), SIG_MAX)
            for bx in tx.get("subtables") or ():
                if not isinstance(bx, dict):
                    continue
                bid = _id(bx, strict, f"{tw} 의 서브 테이블", seen)
                bhead = _s(bx.get("head"), HEAD_MAX)
                if bid is None:
                    continue
                if not _sig_of_text(bhead):
                    if strict:
                        raise ValueError(f"서브 테이블 「{bid}」 의 head 가 없습니다")
                    continue
                bw = f"서브 테이블 「{bid}」"
                tb["subtables"].append({"id": bid, "head": bhead, "guides": _items(bx.get("guides"), "guide", strict, bw),
                                        "examples": _items(bx.get("examples"), "example", strict, bw), "fields": _fields(bx.get("fields"), strict, bw),
                                        **({"sig": _s(bx.get("sig"), SIG_MAX)} if _s(bx.get("sig"), SIG_MAX) else {})})
            sec["tables"].append(tb)
        out["sections"].append(sec)
    return out


def _clean(d):
    """저장할 꼴(빈 목록 · 빈 글은 뺀다 — 사람이 읽기 쉽게)."""
    def it(xs):
        return [{k: v for k, v in x.items() if v not in ("", None, [])} for x in xs]

    def node(x, keys):
        o = {}
        for k in keys:
            v = x.get(k)
            if k in ("guides", "examples"):
                v = it(v or [])
            elif k == "fields":
                v = [{"label": f["label"], **({"guides": it(f["guides"])} if f.get("guides") else {})} for f in v or ()]
            if v not in ("", None, []):
                o[k] = v
        return o
    out = {"schema": SCHEMA, "form": d["form"]}
    if d.get("theme"):
        out["theme"] = d["theme"]
    if d.get("guides"):
        out["guides"] = it(d["guides"])
    if d.get("keywords"):
        out["keywords"] = [{k: v for k, v in x.items() if v not in ("", None, [])} | {"output": x.get("output", "")} for x in d["keywords"]]
    out["sections"] = []
    for s in d.get("sections") or ():
        o = node(s, ("id", "path", "guides", "examples"))
        tabs = []
        for t in s.get("tables") or ():
            to = node(t, ("id", "head", "sig", "guides", "examples", "fields"))
            subs = [node(b, ("id", "head", "sig", "guides", "examples", "fields")) for b in t.get("subtables") or ()]
            if subs:
                to["subtables"] = subs
            tabs.append(to)
        if tabs:
            o["tables"] = tabs
        out["sections"].append(o)
    return out


def dump(d):
    return HEADER.format(name=d["form"]) + yaml.safe_dump(_clean(d), allow_unicode=True, sort_keys=False, width=4096, default_flow_style=False)


def read(key):
    """→ (정리한 양식 지침, 지금 글, sha1) — 파일이 없으면 (빈 양식 지침, None, "") · 못 읽는 파일이면 ValueError."""
    p = path_of(key)
    if p is None or not p.is_file():
        return {"schema": SCHEMA, "form": key, "theme": "", "guides": [], "keywords": [], "sections": []}, None, ""
    text = p.read_bytes().decode("utf-8")
    return parse(text, key, strict=False), text, _sha1(text)


def load(key):
    """읽기만(못 읽으면 None — 읽는 쪽이 죽지 않게)."""
    try:
        d, text, _ = read(key)
    except (ValueError, OSError):
        return None
    return d if text is not None else None


def save_text(key, text, *, expect=None, reason=""):
    """YAML 글을 검사해 저장 → (정리한 것, sha1). expect = 읽었을 때의 sha1("" = 새 파일) · 다르면 StaleVersion."""
    d = parse(text.replace("\r\n", "\n") if isinstance(text, str) else text, key, strict=True)
    return d, _write(key, text.replace("\r\n", "\n"), expect, reason)


def save(key, d, *, expect=None, reason=""):
    """정리한 양식 지침을 YAML 로 저장 → sha1."""
    return _write(key, dump(d), expect, reason)


def _write(key, text, expect, reason, *, path=None, kind="formGuide", hist="guide", label="양식 지침"):
    """path · kind · hist · label = 같은 꼴로 저장하는 짝 파일(규정 `forms/<키>.rules.yaml` — app/form_rules.py)이 준다: sha1 판 · 이력의 꼴을 두 벌 만들지 않는다."""
    p = path if path is not None else path_of(key)
    if p is None:
        raise ValueError("양식 정보 저장이 꺼져 있습니다(NFM_FORMS)")
    with _LOCK:
        old = p.read_bytes().decode("utf-8") if p.is_file() else None
        if expect is not None and expect != (_sha1(old) if old is not None else ""):
            raise StaleVersion(f"{label} {key} 이(가) 그 사이 바뀌었습니다 — 다시 읽어 주세요")
        if old != text:
            p.parent.mkdir(parents=True, exist_ok=True)
            if old is not None:
                _keep(key, old, hist)
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_bytes(text.encode("utf-8"))
            R._retry(lambda: os.replace(tmp, p))
            try:
                R.append_history({"kind": kind, "name": key, "action": "save" if old is not None else "create", "sha1": _sha1(text), "reason": reason})
            except OSError:
                pass
    return _sha1(text)


def _keep(key, old, hist="guide"):
    hd = R.store_dir()
    if hd is None:
        return
    try:
        h = hd / "forms_history" / f"{key}.{hist}"
        h.mkdir(parents=True, exist_ok=True)
        (h / f"{time.strftime('%Y%m%d-%H%M%S')}-{_sha1(old)[:8]}.yaml").write_text(old, encoding="utf-8")
    except OSError:
        pass


# ---- 문서의 자리 ---------------------------------------------------------------------------------------------

def _is_head(n):
    return isinstance(n, dict) and n.get("role") == "heading" and n.get("area") == "body" and bool(n.get("para")) and not n.get("blank")


def doc_places(blocks, graph, t3_tables=None):
    """지금 문서 → {"heads": {문단 id: {path[제목 글…], key(정규화 경로)}}, "tables": {표 id: {head[…], sig, at(그 표의 절 헤딩 id | None)}},
    "bands": {표 id: [{id, rows, cols, head[…], sig}]}(띠가 둘 이상인 3단계 표만)}. 표의 절 = 문서 차례로 바로 앞의 본문 헤딩(place_guides.heading_finder 와 같은 규칙)."""
    from app import place_guides as PG
    nodes = {n["id"]: n for n in (graph or {}).get("nodes") or () if isinstance(n, dict) and n.get("id")}
    pos = {b["id"]: i for i, b in enumerate(iter_blocks(blocks or ()))}
    heads = {}
    for n in nodes.values():
        if not _is_head(n):
            continue
        chain, seen, p = [n.get("text") or ""], {n["id"]}, nodes.get(n.get("parent"))
        while p is not None and p["id"] not in seen:
            seen.add(p["id"])
            if _is_head(p):
                chain.append(p.get("text") or "")
            p = nodes.get(p.get("parent"))
        path = [" ".join(t.split()) for t in reversed(chain)]
        heads[n["para"]] = {"path": path, "key": tuple(norm(t) for t in path), "i": pos.get(n["para"], 10 ** 9)}
    find = PG.heading_finder(blocks, graph)
    tables = {}
    for b in iter_blocks(blocks or ()):
        if b.get("type") != "table":
            continue
        head = table_head(b)
        sig = head_sig(head)
        if sig:
            tables[b["id"]] = {"head": head, "sig": sig, "at": find(b["id"]), "i": pos.get(b["id"], 10 ** 9)}
    bands = {}
    for t in t3_tables or ():
        subs = [s for s in (t.get("subtables") or ()) if isinstance(s, dict) and s.get("rows") and s.get("cols")] if isinstance(t, dict) else []
        if len(subs) < 2:
            continue
        got = []
        for s in subs:
            h = band_head(t, s)
            if head_sig(h):
                got.append({"id": s.get("id"), "rows": list(s["rows"]), "cols": list(s["cols"]), "head": h, "sig": head_sig(h)})
        if got:
            bands[t["id"]] = got
    return {"heads": heads, "tables": tables, "bands": bands}


def _pair(want, have):
    """같은 지문의 YAML 항목들(want) ↔ 문서의 것들(have) → [(항목, [문서 것…])] | None(못 정함). 항목이 하나면 모두 · 수가 같으면 차례대로 하나씩 · 아니면 None."""
    if not want or not have:
        return None
    if len(want) == 1:
        return [(want[0], list(have))]
    if len(want) == len(have):
        return [(w, [h]) for w, h in zip(want, have)]
    return None


def locate(d, places, blocks=None):
    """양식 지침 d + 지금 문서의 자리(doc_places) → {"heads": {헤딩 id: [지침…]}, "tables": {표 id: [지침…]}, "examples": {헤딩|표 id: [예시…]},
    "links": {YAML id: [문서 id…]}, "unmatched": [{id, kind, what, why}]}. 지침 = {src "form", kind, text, origin, label?, cell?, band?}."""
    out = {"heads": {}, "tables": {}, "examples": {}, "links": {}, "unmatched": [], "doc": []}
    if not d:
        return out
    out["doc"] = [{"src": "form", "kind": KIND_DOC, "text": it["text"], "origin": it.get("origin", "user")} for it in d.get("guides") or ()]   # 문서 전체(일반 사용자 가이드라인 — 자리마다 되풀이하지 않는다: 색인의 doc 묶음)
    by_key = {}
    for pid, h in places["heads"].items():
        by_key.setdefault(h["key"], []).append(pid)
    cells = {}
    for b in iter_blocks(blocks or ()):
        if b.get("type") == "table":
            cells[b["id"]] = [(c.get("row", 0), c.get("col", 0), norm(_cell_text(c))) for c in b.get("cells") or ()]

    def g(item, **more):
        x = {"src": "form", "kind": KIND, "text": item["text"], "origin": item.get("origin", "user")}
        x.update(item.get("extra") or {})   # 같은 자리 잇기를 쓰는 다른 원천(규정 · 문서 목적 — app/form_rules.py as_form)이 제 src · kind · 출처를 얹는다
        x.update({k: v for k, v in more.items() if v})
        return x

    def ex(item, label=""):
        x = {"text": item["text"], "origin": item.get("origin", "user")}
        if item.get("note"):
            x["note"] = item["note"]
        if label:
            x["label"] = label
        return x

    def field_guides(tid, fields, area=None, band=None):
        for f in fields or ():
            want = norm(f["label"])
            hit = [(r, c) for r, c, t in cells.get(tid, ()) if t and t == want and (area is None or (area[0][0] <= r < area[0][1] and area[1][0] <= c < area[1][1]))]
            if not hit:
                out["unmatched"].append({"id": f"{tid}", "kind": "field", "what": f["label"], "why": "그 라벨의 칸이 없음"})
                continue
            for r, c in hit[:3]:
                for it in f.get("guides") or ():
                    out["tables"].setdefault(tid, []).append(g(it, label=f"칸 「{_s(f['label'], 40)}」", cell=f"r{r}c{c}", band=band))

    for sec in d.get("sections") or ():
        key = tuple(norm(t) for t in sec["path"])
        pids = by_key.get(key)
        if not pids:
            out["unmatched"].append({"id": sec["id"], "kind": "section", "what": " › ".join(sec["path"]), "why": "그 경로의 헤딩이 없음"})
            continue
        out["links"][sec["id"]] = list(pids)
        for pid in pids:
            for it in sec.get("guides") or ():
                out["heads"].setdefault(pid, []).append(g(it))
            for it in sec.get("examples") or ():
                out["examples"].setdefault(pid, []).append(ex(it))
        groups = {}
        for t in sec.get("tables") or ():
            groups.setdefault(node_sig(t), []).append(t)
        for sig, want in groups.items():
            # 표의 짝은 **헤딩마다** 짓는다(검토 P2-6 — 전에는 되풀이되는 절(기관마다)의 표를 한데 모아 견줘, 같은 머리글의 표가 둘인 절이 기관 둘에 있으면 2 대 4 로 모두 못 잇고,
            # 기관마다 하나씩이면 YAML 의 표 1 · 표 2 가 기관 1 · 기관 2 의 표로 잘못 이어졌다)
            pairs, seen_have = [], 0
            for pid in pids:
                have = sorted((t for t, v in places["tables"].items() if v["at"] == pid and v["sig"] == sig), key=lambda t: places["tables"][t]["i"])
                seen_have = max(seen_have, len(have))
                pairs += _pair(want, have) or []
            if not pairs:
                for t in want:
                    out["unmatched"].append({"id": t["id"], "kind": "table", "what": t["head"], "why": "그 절에 그 머리글의 표가 없음" if not seen_have else f"같은 머리글의 표가 {seen_have}개 — 어느 것인지 못 정함"})
                continue
            for t, tids in pairs:
                out["links"].setdefault(t["id"], []).extend(tids)
                for tid in tids:
                    for it in t.get("guides") or ():
                        out["tables"].setdefault(tid, []).append(g(it))
                    for it in t.get("examples") or ():
                        out["examples"].setdefault(tid, []).append(ex(it))
                    field_guides(tid, t.get("fields"))
                    bands = places["bands"].get(tid) or []
                    bgroups = {}
                    for b in t.get("subtables") or ():
                        bgroups.setdefault(node_sig(b), []).append(b)
                    for bsig, bwant in bgroups.items():
                        bpairs = _pair(bwant, [x for x in bands if x["sig"] == bsig])
                        if bpairs is None:
                            for b in bwant:
                                out["unmatched"].append({"id": b["id"], "kind": "subtable", "what": b["head"], "why": "그 표에 그 머리글의 서브 테이블이 없음"})
                            continue
                        for b, hits in bpairs:
                            out["links"].setdefault(b["id"], []).extend(f"{tid}/{h['id']}" for h in hits)
                            for h in hits:
                                label = f"서브 테이블 「{_s(HEAD_SEP.join(h['head']), 40)}」(행 {h['rows'][0] + 1}–{h['rows'][1]})"
                                for it in b.get("guides") or ():
                                    out["tables"].setdefault(tid, []).append(g(it, label=label, band=h["id"]))
                                for it in b.get("examples") or ():
                                    out["examples"].setdefault(tid, []).append(ex(it, label))
                                field_guides(tid, b.get("fields"), (h["rows"], h["cols"]), h["id"])
    return out


def keywords_found(d, blocks):
    """주요 항목의 라벨이 지금 문서의 어디에 있나 → [{id, name, output, at[블록 id…]}](화면 · 구성 추출의 힌트 — 읽기만)."""
    paras = [(b["id"], norm(b.get("text") or "")) for b in iter_blocks(blocks or ()) if b.get("type") == "paragraph"]
    out = []
    for k in (d or {}).get("keywords") or ():
        want = [norm(x) for x in k.get("labels") or () if norm(x)]
        at = [pid for pid, t in paras if t and any(t == w or t.startswith(w) for w in want)][:5]
        out.append({"id": k["id"], "name": k["name"], "output": k.get("output", ""), "at": at})
    return out


# ---- 후보 · 올리기 ------------------------------------------------------------------------------------------

def _value_words(values):
    """프로젝트 구성 값에서 과제마다 다른 글(기관 이름 등 — 2자 이상 글자) → 경고에 쓰는 낱말들."""
    out = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            t = " ".join(v.split())
            if len(t) >= 2 and re.search(r"[가-힣A-Za-z]", t) and not re.fullmatch(r"[\d\s.\-~/년월일차단계]+", t):
                out.add(t)
    walk((values or {}).get("orgs"))
    return sorted(out, key=len, reverse=True)


_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+|\d{4,}")


def warnings(text, words):
    """올리려는 글에 과제마다 다른 것(기관 이름 · 큰 수)이 있나 → 경고 글 목록."""
    out = []
    hit = [w for w in words if w in text]
    if hit:
        out.append("기관 이름: " + ", ".join(hit[:4]))
    nums = _NUMBER.findall(text)
    if nums:
        out.append("수: " + ", ".join(nums[:4]))
    return out


def target_of(pid, places):
    """문서의 자리 id(헤딩 문단 · 표) → {"path": […], "head": [...] | None, "band": None} | None(절을 정할 수 없음)."""
    h = places["heads"].get(pid)
    if h is not None:
        return {"path": h["path"], "head": None}
    t = places["tables"].get(pid)
    if t is not None and t.get("at") and t["at"] in places["heads"]:
        return {"path": places["heads"][t["at"]]["path"], "head": t["head"]}
    return None


def _has(d, target, text, kind="guides", band=None):
    sec = next((s for s in d.get("sections") or () if tuple(norm(x) for x in s["path"]) == tuple(norm(x) for x in target["path"])), None)
    if sec is None:
        return False
    node = sec
    if target.get("head"):
        sig = head_sig(target["head"])
        node = next((t for t in sec.get("tables") or () if node_sig(t) == sig), None)
        if node is None:
            return False
        if band:
            bsig = head_sig(band["head"])
            node = next((b for b in node.get("subtables") or () if node_sig(b) == bsig), None)
            if node is None:
                return False
    return any(x["text"] == text for x in node.get(kind) or ())


def candidates(d, places, *, user_heads=None, table_user=None, rules=None, words=()):
    """작업 폴더의 것 → 양식 지침에 올릴 후보 [{key, place, kind(head | table), origin(user | llm), text, basis?, where, saved, warn[]}](문서 차례가 아니라 원천 차례).
    user_heads = guides_user.json 의 heads · table_user = {표 id: 「이 표」 지침} · rules = 04 작성 지침 보완의 rules {자리 id: [{instruction, basis}]}."""
    out, used = [], set()
    from app import place_guides as PG

    def add(lead, pid, origin, text, basis="", band=None):
        text = _long(text, GUIDE_MAX)
        tg = target_of(pid, places)
        if not text or tg is None:
            return
        bd = next((b for b in places["bands"].get(pid) or () if b["id"] == band), None) if band else None
        if band and bd is None:
            return   # 그 띠가 지금 표에 없다 — 표 전체로 넓혀 올리지 않는다(범위 유지)
        where = " › ".join(tg["path"][-2:]) + (f" › 표 「{head_text(tg['head'])[:40]}」" if tg.get("head") else "") + (f" › 서브 테이블 「{head_text(bd['head'])[:40]}」" if bd else "")
        # 후보의 key = 글 · 대상 · 출처의 지문(검토 P1 — 전의 「l:<자리>:<순번>」 은 04 를 다시 돌려 같은 순번의 글이 바뀌면 사람이 본 것과 다른 글이 올라갔다). 하나라도 바뀌면 key 가 달라져 올리기가 409 다
        key = f"{lead}:{pid}:" + _sha1("\x1f".join((origin, basis, " › ".join(tg["path"]), head_text(tg["head"] or ()), band or "", text)))[:10]
        if key in used:
            return
        used.add(key)
        ids = sorted(PG.mentions(text))
        c = {"key": key, "place": pid, "kind": "table" if tg.get("head") else "head", "origin": origin, "text": text, "where": where,
             "saved": _has(d or {}, tg, text, band=bd), "warn": warnings(text, words)}
        if ids:   # 이 문서의 블록 id(「p48 줄은 …」)가 든 글 — 다른 문서에서는 그 id 가 다른 줄이다: 고친 뒤 올린다(검토 P1)
            c["warn"] = [*c["warn"], "이 문서의 줄 id: " + ", ".join(ids[:4])]
            c["blocked"] = "이 문서의 줄 id(" + ", ".join(ids[:4]) + ")가 든 글은 다른 문서에서 다른 줄을 가리킵니다 — id 를 뺀 글로 고친 뒤 올리세요"
        if basis:
            c["basis"] = basis
        if bd:
            c["band"] = band
        out.append(c)
    for pid, u in (user_heads or {}).items():
        if isinstance(u, dict):
            add("u", pid, "user", u.get("text"))
    for tid, text in (table_user or {}).items():
        add("u", tid, "user", text)
    for pid, rs in (rules or {}).items():
        for r in rs or ():
            if isinstance(r, dict):
                add("l", pid, "llm", r.get("instruction") or r.get("text"), r.get("basis") or "", r.get("band") if isinstance(r.get("band"), str) else None)
    return out


def _new_id(d, prefix):
    used = set()
    for s in d.get("sections") or ():
        used.add(s["id"])
        for t in s.get("tables") or ():
            used.add(t["id"])
            used.update(b["id"] for b in t.get("subtables") or ())
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


def node_for(d, target, band=None):
    """target {path, head?} (+ band {head}) 의 YAML 항목(없으면 만든다) → 그 항목(dict — d 안의 것)."""
    want = tuple(norm(x) for x in target["path"])
    sec = next((s for s in d["sections"] if tuple(norm(x) for x in s["path"]) == want), None)
    if sec is None:
        sec = {"id": _new_id(d, "s"), "path": [_TAIL_NOTE.sub("", t).strip() or t for t in target["path"]], "guides": [], "examples": [], "tables": []}   # 보이는 글은 「※ …」 꼬리를 뗀 제목(견주기는 norm — 같은 결과)
        d["sections"].append(sec)
    if not target.get("head"):
        return sec
    sig = head_sig(target["head"])
    tab = next((t for t in sec["tables"] if node_sig(t) == sig), None)
    if tab is None:
        tab = {**_head_node(target["head"], id=_new_id(d, f"{sec['id']}.t")), "guides": [], "examples": [], "fields": [], "subtables": []}
        sec["tables"].append(tab)
    if not band:
        return tab
    bsig = head_sig(band["head"])
    sub = next((b for b in tab["subtables"] if node_sig(b) == bsig), None)
    if sub is None:
        sub = {**_head_node(band["head"], id=_new_id(d, f"{tab['id']}.b")), "guides": [], "examples": [], "fields": []}
        tab["subtables"].append(sub)
    return sub


def promote(d, places, picks, *, work="", date=""):
    """고른 후보들을 양식 지침에 더한다(d 를 고침) → 더한 수. 같은 글이 이미 있으면 건너뛴다 · 사람 지침은 덮지 않는다(더하기만)."""
    n = 0
    for c in picks:
        tg = target_of(c["place"], places)
        if tg is None or c.get("blocked"):
            continue
        band = next((b for b in places["bands"].get(c["place"]) or () if b["id"] == c["band"]), None) if c.get("band") else None
        if c.get("band") and band is None:
            continue   # 띠에만 닿는 후보 — 그 띠가 없으면 표 전체로 넓혀 올리지 않는다
        node = node_for(d, tg, band)
        if any(x["text"] == c["text"] for x in node["guides"]):
            continue
        item = {"text": _long(c["text"], GUIDE_MAX), "origin": c.get("origin") if c.get("origin") in ORIGINS else "user"}
        if work:
            item["from"] = work
        if date:
            item["date"] = date
        node["guides"].append(item)
        n += 1
    return n


def _count(d):
    return sum(1 + sum(1 + len(t.get("subtables") or ()) for t in s.get("tables") or ()) for s in d.get("sections") or ())


def skeleton(d, places):
    """지금 문서의 구조(본문 헤딩의 경로 → 그 절의 표 → 표의 서브 테이블)를 d 에 깐다(없는 항목만 · 지침 없이) → 더한 항목 수.
    「어떤 본문의 어떤 표의 서브 테이블인가」 를 YAML 에서 한눈에 보고 지침 · 예시를 적을 자리를 만든다(spec_양식작성 ② §5-8 「뼈대 채우기」)."""
    before = _count(d)
    heads = places["heads"]
    for pid in sorted(heads, key=lambda k: heads[k]["i"]):
        node_for(d, {"path": heads[pid]["path"]})
    tabs = places["tables"]
    for tid in sorted(tabs, key=lambda k: tabs[k]["i"]):
        at = tabs[tid].get("at")
        if at not in heads:
            continue
        target = {"path": heads[at]["path"], "head": tabs[tid]["head"]}
        node_for(d, target)
        for band in places["bands"].get(tid) or ():
            node_for(d, target, band)
    return _count(d) - before


def add_example(d, places, pid, text, *, note="", band_id=None, work="", date=""):
    """자리(헤딩 · 표 · 그 표의 띠)에 작성 예시 하나를 더한다 → 그 항목의 id. ValueError = 자리를 못 정함 · 글이 빔."""
    text = _long(text, EXAMPLE_MAX)
    if not text:
        raise ValueError("예시 글이 비었습니다")
    tg = target_of(pid, places)
    if tg is None:
        raise ValueError("그 자리의 절(헤딩)을 정할 수 없습니다 — 헤딩 추출 결과의 헤딩 · 그 아래 표에 더합니다")
    band = None
    if band_id:
        band = next((b for b in places["bands"].get(pid) or () if b["id"] == band_id), None)
        if band is None:
            raise ValueError("그 서브 테이블이 지금 표에 없습니다")
    node = node_for(d, tg, band)
    if not any(x["text"] == text for x in node["examples"]):
        item = {"text": text, "origin": "user"}
        if _s(note, NOTE_MAX):
            item["note"] = _s(note, NOTE_MAX)
        if work:
            item["from"] = work
        if date:
            item["date"] = date
        node["examples"].append(item)
    return node["id"]


def example_text(examples, limit=EXAMPLE_SEND):
    """자리의 예시들 → 초안 요청에 싣는 글(하나 · limit 자까지 · 꼴만 참고하라는 말과 함께) | ""."""
    ex = next((x for x in examples or () if (x.get("text") or "").strip()), None)
    if ex is None:
        return ""
    t = " ".join(ex["text"].split())
    t = t if len(t) <= limit else t[:limit - 1] + "…"
    head = "작성 예시(양식 지침 — 꼴 · 문체 · 분량만 참고하고 이름 · 수치 · 사실은 옮기지 않습니다"
    return head + (f" · {ex['label']}" if ex.get("label") else "") + (f" · {ex['note']}" if ex.get("note") else "") + "):\n" + t

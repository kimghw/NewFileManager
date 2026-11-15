"""서식 적용(spec_일반편집 ② §4) — 대상 **hwpx** 문서에 서식 템플릿을 쓴다: 새 표 · 빈 표 · 표 서식 입히기 · 글 서식 입히기 · 줄 쓰기 + 가져온 정의 검사.

- 서식의 출처: 보관함 템플릿(운반 문서 — `style_of(doc, sid)` · `text_style(sid)`) · 기본 표(`builtin` = 빈 바탕의 평범한 표) · 지금 문서의 표(`doc:<표 id>`).
- 모든 적용 함수는 `doc` 을 **바꾼다** — 부르는 쪽이 `server._edit` 의 `run()` 안에서 부른다(가져오기·삽입이 스냅샷 뒤에 일어나야 되돌릴 수 있다).
  틀린 입력·끊어진 참조는 ValueError(→ 트랜잭션이 되돌리고 400).
- 다른 문서(운반 문서)에서 가져오는 함수는 **가져오기 전에** 그 문서를 본다(`source_check`): 끊어진 정의 참조가 하나라도 있으면 ValueError — `_import_def`·`_import_font` 는 원본에 없는
  정의의 번호를 그대로 넘겨, 대상 문서의 같은 번호 정의에 말없이 붙는다(astra 8: 그러면 아래 `imported_check` 는 통과한다). 판정은 운반 문서 객체마다 한 번.
- 가져온 뒤에는 스스로 `imported_check` 를 부른다: 그 뒤 더해진 header 정의마다 **끊어진 참조**(`owpml_check._refs`)가 있으면 ValueError —
  `check_hosts(header=True)` 는 header 안 참조를 보지 않는다. 원본에 같은 위반이 있었어도 봐주지 않는다.
- 넣을 자리 `after` 는 **본문 최상위 블록**만(`top_level` — 칸 안은 v1 에서 안 한다). 본문에 넣는 표는 그 구역의 글 폭에 맞춘다.
- 쓰고 남은 정의는 문서 header 에 남는다(`drop_unused_defs` 를 부르지 않는다 — 실행 취소와 얽힌다).
- **OWPML 판정 기준선**: 문서 사이 복사는 원본 문서에 한글이 써 둔 스키마 위반(탭 정의의 꼴 `tabPr/switch` ↔ `tabPr/tabItem` 등)을 정의와 함께 가져온다 —
  `server._transact` 의 판정은 「원본에 없던 종류」 를 되돌리므로(422), 다른 문서에서 가져오는 적용 함수는 그 문서를 쥔 서버 세션의 기준선에 운반 문서의 위반 **종류**를
  더한다(`_carry` → `server.owpml_allow` — 병합의 판정 `merge_api` `check` 와 같은 규칙: 그 종류는 이 편집 탓이 아니다).
  세션은 **부르는 쪽이 넘긴다**(적용 함수의 `session=` — `server._edit` 의 `make(s)` 가 받은 그 세션). 안 주면 전처럼 `server.DOCS` 에서 문서 객체로 찾는다 —
  LRU 로 밀려난 세션은 거기 없어 못 찾는다(astra).
- **문서 서식 입히기**(spec_서식복사 ② §9 — hwpx): `page_style(sid)` → `set_page(doc, pstyle)` = 모든 구역의 쪽 설정을 그 문서 서식의 값으로(`style_page.set_page`). 정의를 가져오지 않는다(운반 문서를 안 연다).
- **표지 넣기**(spec_서식복사 ② §14 — hwpx): `cover_style(sid)` → `cover_insert(doc, cstyle)` = 문서의 맨 앞에 표지 서식의 블록들을(`style_cover.insert` — 그 모듈은 부를 때 가져온다). 운반 문서의 정의를 가져오므로
  다른 문서에서 가져오는 적용과 같은 검사(`source_check` · `_imported`)를 한다.
- **docx 문서**(② §9): `docx_table_blank`(docx 운반 문서의 표를 그대로 넣고 채울 칸을 비움) · `docx_format_paras`(템플릿 항목의 서식 요약을 `DocxDoc.derive_format`·`apply_format` 으로 —
  글·레터는 그대로)만. 그 밖의 적용은 hwpx 문서만 된다. docx 운반 문서는 부르는 쪽(끝점)이 보관함에서 읽어(없으면 지어 붙여) `docx_open` 으로 열어 준다."""
import sys
import weakref

from app import heading_rules as R
from app import outline_edit, owpml_check, style_carrier, style_lib
from app import table_make as M
from app.hwpx_doc import PIC, RUN, TBL, HwpxDoc, P

LABEL_ROLES = ("label", "note")  # blueprint 에서 글을 남기는 칸 역할 — input·computed 는 비운다
_SRC_BAD = weakref.WeakKeyDictionary()  # 운반 문서(HwpxDoc) → 끊어진 정의 참조의 글들(source_check — 문서 객체마다 한 번만 센다)


# ---- 서식 고르기 ---------------------------------------------------------------------------------------------------

def style_of(doc, ref: str) -> dict:
    """표 서식 하나 → {"src": HwpxDoc | None(이 문서), "table": 양식 표 id, "bands": 띠 수, "meta": meta | None}.
    ref = 보관함 템플릿 id | "builtin"(기본 표) | "doc:<표 id>"(지금 문서의 표 — 띠 수는 자동 판정). 없으면 KeyError, 표 서식이 아니면 ValueError."""
    if ref == "builtin":
        src, _, plain = style_carrier.open_base()
        return {"src": src, "table": plain, "bands": dict(style_carrier.ZERO), "meta": None}
    if isinstance(ref, str) and ref.startswith("doc:"):
        tid = ref[4:]
        el = doc._ids.get(tid)
        if el is None or el.tag != TBL or not doc._attached(el):
            raise KeyError("표 서식으로 고른 표가 지금 문서에 없습니다 — 다시 고르세요")
        b = doc.table_block(tid)
        return {"src": None, "table": tid, "bands": M.roles_of(b["cells"], b["nRows"], b["nCols"]), "meta": None}
    meta, data = style_lib.get(ref), style_lib.carrier(ref)
    if meta is None or data is None:
        raise KeyError("그 서식이 서식 보관함에 없습니다")
    if meta.get("kind") != "table":
        raise ValueError("표 서식이 아닙니다 — 글 서식은 문단에 입힙니다")
    src = style_carrier.doc(data)
    tid = style_carrier.table_id(src)
    tbl = src._ids[tid]
    return {"src": src, "table": tid, "bands": M.clean_roles(meta.get("bands"), int(tbl.get("rowCnt")), int(tbl.get("colCnt"))), "meta": meta}


def text_style(sid: str) -> dict:
    """글 서식 하나 → {"src": 운반 문서, "paras": [견본 문단 id — items 차례], "items": meta.items, "meta": meta}. 없으면 KeyError, 글 서식이 아니면 ValueError."""
    meta, data = style_lib.get(sid), style_lib.carrier(sid)
    if meta is None or data is None:
        raise KeyError("그 서식이 서식 보관함에 없습니다")
    if meta.get("kind") != "text":
        raise ValueError("글 서식이 아닙니다 — 표 서식은 표에 입힙니다")
    src, items = style_carrier.doc(data), meta.get("items") or []
    paras = style_carrier.para_ids(src)
    if len(paras) < len(items):
        raise ValueError("서식의 견본 문단 수가 항목 수보다 적습니다(운반 문서가 손상됨)")
    return {"src": src, "paras": paras[:len(items)], "items": items, "meta": meta}


def top_level(doc, block_id):
    """block_id 가 **본문 최상위 블록**(구역 바로 아래 문단, 또는 그 문단의 표·그림)이면 그 요소 — 아니면(없는 id · 칸 안 · 캡션) ValueError."""
    el = doc._ids.get(block_id) if isinstance(block_id, str) else None
    if el is None or el.tag not in (P, TBL, PIC) or not doc._attached(el):
        raise ValueError("넣을 자리의 블록이 지금 문서에 없습니다 — 넣을 자리는 본문 최상위 블록만 됩니다")
    if doc._host(el).getparent() not in doc._sections:
        raise ValueError("넣을 자리는 본문 최상위 블록만 됩니다(표 칸 안에는 넣지 않습니다)")
    return el


# ---- 가져온 정의 검사 · 판정 기준선 ------------------------------------------------------------------------------------

def source_check(src) -> None:
    """가져오기 **전에** 운반 문서 src 를 본다 — 끊어진 정의 참조(없는 정의·글꼴·그림을 가리킴: `style_carrier.broken_refs`)가 하나라도 있으면 ValueError.
    원본에 없는 정의의 번호는 가져올 때 그대로 넘어와 대상 문서의 같은 번호 정의에 붙는다 — 그렇게 「고쳐진」 것은 뒤의 `imported_check` 가 못 잡는다.
    src None(이 문서의 표)은 안 본다. 판정은 문서 객체마다 한 번(운반 문서는 적용하는 동안 안 바뀐다)."""
    if not isinstance(src, HwpxDoc):
        return
    bad = _SRC_BAD.get(src)
    if bad is None:
        bad = _SRC_BAD[src] = style_carrier.broken_refs(src)
    if bad:
        raise ValueError("서식 템플릿의 정의 참조가 깨져 있어 적용하지 않았습니다 — " + " · ".join(bad[:5]))


def defs_state(doc) -> dict:
    """header 정의 id 의 지금 모습 {종류: {id…}} — 가져오기 전에 찍어 두고 `imported_check` 에 준다."""
    return {kind: set(defs) for kind, defs in doc._defs.items()}


def imported_check(doc, before: dict) -> None:
    """before(`defs_state`) 뒤에 더해진 header 정의마다 끊어진 참조(없는 정의·글꼴·그림을 가리킴 — `owpml_check._refs`)를 찾아, 있으면 ValueError."""
    out = []
    for kind, defs in doc._defs.items():
        for i in sorted(set(defs) - before.get(kind, set())):
            owpml_check._refs(doc, defs[i], out, "header")
    if out:
        raise ValueError("가져온 서식 정의에 끊어진 참조가 있어 적용하지 않았습니다 — " + " · ".join(dict.fromkeys(v["message"] for v in out[:5])))


def carried(src):
    """운반 문서 src 가 지닌 스키마 위반 종류 Counter — 그 문서의 정의·문단을 가져오면 따라올 수 있는 것(한글이 원본에 써 둔 꼴)."""
    return owpml_check.counts(owpml_check.check_doc(src))["schema"]


def allow(base: dict, src) -> list:
    """대상 문서의 OWPML 판정 기준선 base(`server.owpml_base(s)` — {"schema": Counter, "rules": Counter})에 운반 문서 src 가 옮겨 올 수 있는 스키마 위반 **종류**를
    더한다(base 에 없는 종류만 · 제자리에서) -> 더한 종류. src None(이 문서의 표)이면 아무것도 안 한다. 규칙 위반(끊어진 참조 등)의 기준선은 그대로 — 그것은 봐주지 않는다."""
    if src is None:
        return []
    added = [k for k in carried(src) if k not in base["schema"]]
    for k in added:
        base["schema"][k] = 1
    return added


def _carry(doc, src, session=None) -> None:
    """doc 을 쥔 서버 세션의 판정 기준선에 src 의 위반 종류를 더한다(`server.owpml_allow` — 그 편집의 판정에 바로 들고, 편집 상태와 함께 저장·실행 취소된다).
    session = 부르는 쪽이 넘긴 세션(`server._edit` 의 `make(s)` 가 받은 것). 안 줬으면 `server.DOCS` 에서 문서 객체로 찾는다(옛 호출 — 밀려난 세션은 못 찾는다).
    서버 밖(시험·도구 — 세션도 없고 DOCS 에도 없음)에서는 아무것도 안 한다."""
    server = sys.modules.get("app.server")
    if src is None or server is None:
        return
    s = session if session is not None else next((x for x in list(getattr(server, "DOCS", {}).values()) if getattr(x, "doc", None) is doc), None)
    if s is not None:
        server.owpml_allow(s, list(carried(src)))   # 기준선에 더하고 작업에 저장한다 — 다시 연 뒤의 편집도 그 종류로 422 가 나지 않게(server.owpml_allow)


def _imported(doc, before, src, session=None) -> None:
    """다른 문서 src 에서 가져온 뒤의 마무리 — 판정 기준선에 그 문서의 위반 종류를 더하고(`_carry`) 가져온 정의의 끊어진 참조를 검사한다. src None 이면 아무것도 안 한다."""
    if src is not None:
        _carry(doc, src, session)
        imported_check(doc, before)


# ---- 표 ----------------------------------------------------------------------------------------------------------

def table_new(doc, style, norm, after, *, session=None) -> dict:
    """after(본문 최상위 블록) 바로 뒤에 style 의 서식으로 격자 norm(`table_make.normalize` 결과)의 새 표 -> {table, host, rows, cols}.
    양식 표는 운반 문서에서 붙이지 않은 사본으로 떼어 온다(`HwpxDoc.table_make(…, src=)`) — 임시 블록을 넣었다 지우지 않는다. 표 폭은 그 구역의 글 폭까지만.
    session = 이 문서를 쥔 서버 세션(판정 기준선에 운반 문서의 위반 종류를 더할 곳 — `_carry`). 다른 적용 함수도 같다."""
    top_level(doc, after)
    source_check(style["src"])
    before = defs_state(doc)
    r = doc.table_make(after, style["table"], norm, style["bands"], src=style["src"], fit=True)
    _imported(doc, before, style["src"], session)
    return r


def table_blank(doc, style, after, *, session=None) -> dict:
    """after 바로 뒤에 style 의 양식 표를 **그대로**(구조·라벨 글·칸 크기) 넣고 채울 칸을 비운다 -> {table, host, rows, cols}.
    비우는 칸 = meta.blueprint 가 있으면 그 `input`·`computed` 칸, 없으면 라벨 칸이 아닌 칸 — 라벨 칸 = meta.labels(만들 때 운반 문서에 글을 남긴 칸), 그것도 없으면(파일에서
    추출한 템플릿 · 이 문서의 표) `style_carrier.kept_labels`(같은 규칙으로 다시 — 견본 글만 든 머리 띠 칸은 라벨이 아니다). 표 폭은 그 구역의 글 폭까지만."""
    top_level(doc, after)
    source_check(style["src"])
    before, src = defs_state(doc), style["src"]
    new = doc.insert_after(after, [{"kind": "copy", "srcId": style["table"]}], src=src)[0]
    tbl = doc._ids[new]
    host = doc._host(tbl)
    style_carrier._no_break(host)
    tbl.set("id", doc._tm_new_id(tbl))  # 개체 id 는 새로 — 같은 템플릿을 두 번 넣어도 안 겹친다
    block = doc.table_block(new)
    rows, bands = block["nRows"], M.clean_roles(style.get("bands"), block["nRows"], block["nCols"])
    meta = style.get("meta") or {}
    bp = meta.get("blueprint") or {}
    roles = {(c.get("row"), c.get("col")): c.get("role") for c in bp.get("cells") or [] if isinstance(c, dict)}
    given = meta.get("labels")
    labels = {tuple(rc) for rc in given if isinstance(rc, (list, tuple)) and len(rc) == 2} if isinstance(given, list) else style_carrier.kept_labels(block, bands)
    for c in block["cells"]:
        role = roles.get((c["row"], c["col"])) if roles else None
        keep = role in LABEL_ROLES if role else (c["row"], c["col"]) in labels
        if not keep:
            doc._blank_cell(doc._ids[c["id"]])
    doc._touch(tbl)
    style_carrier.fit_width(doc, new)
    _imported(doc, before, src, session)
    return {"table": new, "host": doc._id(host), "rows": rows, "cols": block["nCols"]}


def table_restyle(doc, style, table, bands=None, *, session=None) -> dict:
    """문서의 표 table 에 style 의 서식만 입힌다(구조·글·칸 크기 그대로) -> {table, cells, formatted: 모양이 바뀐 문단 id, rows, cols, bands}.
    bands = 그 표의 띠 수(없는 값은 자동 판정)."""
    el = doc._ids.get(table) if isinstance(table, str) else None
    if el is None or el.tag != TBL or not doc._attached(el):
        raise ValueError("서식을 입힐 표가 지금 문서에 없습니다")
    b = doc.table_block(table)
    bands = M.clean_roles(bands, b["nRows"], b["nCols"], default=M.roles_of(b["cells"], b["nRows"], b["nCols"]))
    source_check(style["src"])
    before = defs_state(doc)
    r = doc.table_restyle(table, style["table"], bands, style["bands"], src=style["src"])
    _imported(doc, before, style["src"], session)
    return {**r, "rows": b["nRows"], "cols": b["nCols"], "bands": bands}


# ---- 글 ----------------------------------------------------------------------------------------------------------

def _item(tstyle, key):
    """글 서식의 항목 key → (차례, 항목). 없으면 ValueError."""
    for i, it in enumerate(tstyle["items"]):
        if it.get("key") == key:
            return i, it
    raise ValueError("그 글 서식 항목이 없습니다")


def _marker(it) -> dict:
    m = it.get("marker") if isinstance(it.get("marker"), dict) else {}
    return {"mode": m.get("mode") or "none", "literal": m.get("literal") or "", "lead": m.get("lead") or "", "gap": m.get("gap") or "", "family": m.get("family")}


def _plen(m) -> int:
    """견본 문단 글에서 레터 자리(앞 공백 + 레터 + 사이 공백)의 길이."""
    return len(m["lead"] + m["literal"] + m["gap"]) if m["mode"] == "literal" else 0


def format_paras(doc, tstyle, key, para_ids, keep_numbering=True, *, session=None) -> list[str]:
    """문단들에 글 서식 항목 key 의 모양(견본 문단의 문단 모양 + 본문 쪽 글자 모양)을 입힌다 -> 모양이 바뀐 문단 id. 글·레터는 안 바꾼다.
    keep_numbering = 문단마다 제 번호 설정(hh:heading — 개요·글머리표·번호)을 지킨다."""
    i, it = _item(tstyle, key)
    src = tstyle["src"]
    sp, ps = src._ids[tstyle["paras"][i]], []
    for pid in para_ids:
        el = doc._ids.get(pid) if isinstance(pid, str) else None
        if el is None or el.tag != P or not doc._attached(el):
            raise ValueError("서식을 입힐 문단이 지금 문서에 없습니다")
        ps.append(el)
    source_check(src)
    before, cache = defs_state(doc), {}
    pp = doc._import(src, "paraPr", sp.get("paraPrIDRef"), cache)
    cc = doc._import(src, "charPr", style_carrier.body_char(src, sp, _plen(_marker(it))), cache)
    shape = lambda p: (p.get("paraPrIDRef"), [r.get("charPrIDRef") for r in p.iterchildren(RUN)])  # noqa: E731
    was = [shape(p) for p in ps]
    doc.apply_format(list(para_ids), {"token": f"p{pp}|c{cc}"}, keep_numbering=keep_numbering)
    _imported(doc, before, src, session)
    return [pid for pid, p, w in zip(para_ids, ps, was) if shape(p) != w]


def _seq(m) -> bool:
    """차례가 있는 레터인가 — 규칙 계열이 번호형이고 `outline_edit` 가 그 번호를 올릴 수 있다. ASCII 로마자(「I.」·「ii.」)는 알파벳으로 읽히므로 차례로 안 본다."""
    lit = m["literal"].strip()
    family = m["family"] or R.classify(m["literal"], R.active({}))["family"]
    if not lit or R._ordinal(family, lit) is None or not outline_edit.numbers_of(lit):
        return False
    return not (family in ("roman-upper", "roman-lower") and lit[0].isascii())


def _like(doc, after):
    """견본 없는 줄이 따를 문단 id — 넣을 자리가 글 문단이면 그것, 빈 줄·표·그림이면 그 앞쪽에서 가장 가까운 글 문단(없으면 None = 문서의 첫 글 문단)."""
    p = doc._host(doc._ids[after])
    while p is not None:
        if doc._text(p).strip() and not doc._has_object(p):
            return doc._id(p)
        p = doc._sibling(p, -1)
    return None


def write_lines(doc, after, lines, tstyle=None, *, session=None) -> list[str]:
    """after(본문 최상위 블록) 뒤에 줄마다 새 문단 하나씩(앞 줄 바로 뒤에 차례로) -> 새 문단 id 들. lines = [{"text", "item": 글 서식 항목 key | None}].
    item 이 있으면 그 견본 문단을 복사해 글을 쓴다: 레터 정책이 literal 이면 앞 공백 + 레터 + 사이 공백 + text — 레터는 **차례가 있는 계열이면 이 묶음 안에서 1부터**
    (같은 항목의 다음 줄은 +1 · 위 레벨 줄이 나오면 아래 레벨은 다시 1부터 · 「1-1.」 꼴은 위 레벨 번호를 앞에), 아니면 견본의 레터 그대로. auto·none 이면 text 만
    (자동 번호는 대상 문서의 번호 설정을 따른다). item 이 없으면 넣을 자리 문단 모양의 새 문단. 한 줄 = 한 문단(줄 바꿈은 빈칸으로)."""
    top_level(doc, after)
    if not isinstance(lines, list) or not lines or not all(isinstance(ln, dict) for ln in lines):
        raise ValueError("쓸 줄이 없습니다")
    if tstyle is not None:
        source_check(tstyle["src"])
    before, anchor, out = defs_state(doc), after, []
    like = _like(doc, after) or doc._id(doc._default_template())  # 견본 없는 줄의 모양 — 줄을 넣기 전에 정해 둔다(넣은 줄을 따라가지 않게)
    last, levels = {}, {}  # 항목 key → 마지막에 쓴 레터 · 레벨 → 그 레벨에서 마지막에 쓴 차례 레터(없으면 None)
    for ln in lines:
        text = str(ln.get("text") or "").replace("\r", "").replace("\n", " ")
        if tstyle is not None and ln.get("item"):
            i, it = _item(tstyle, ln["item"])
            m = _marker(it)
            anchor = doc.insert_after(anchor, [{"kind": "copy", "srcId": tstyle["paras"][i]}], src=tstyle["src"])[0]
            p, prefix = doc._ids[anchor], ""
            style_carrier._no_break(p)
            if m["mode"] == "literal":
                lv, key, seq = it.get("level") if isinstance(it.get("level"), int) else None, it["key"], _seq(m)
                parent = next((levels[k] for k in sorted(levels, reverse=True) if lv is not None and k < lv and levels[k]), None)
                letter = ((outline_edit.succ(last[key], parent) if key in last else outline_edit.first(m["literal"], parent)) if seq else None) or m["literal"]
                last[key] = letter
                if lv is not None:
                    levels[lv] = letter if seq else None
                    for k in [k for k in levels if k > lv]:
                        del levels[k]
                    for x in tstyle["items"]:  # 아래 레벨은 다시 1부터
                        if isinstance(x.get("level"), int) and x["level"] > lv:
                            last.pop(x.get("key"), None)
                prefix = m["lead"] + letter + m["gap"]
            style_carrier.put_text(doc, p, prefix, text, _plen(m))
        else:
            anchor = doc.insert_after(anchor, [{"kind": "paragraph", "text": text, "templateId": like}])[0]
            style_carrier._no_break(doc._ids[anchor])
        out.append(anchor)
    _imported(doc, before, tstyle["src"] if tstyle is not None else None, session)
    return out


# ---- 문서 서식(쪽 설정 — spec_서식복사 ② §5·§9) ------------------------------------------------------------------------

def page_style(sid: str) -> dict:
    """문서 서식 하나 → {"page": 쪽 설정(`style_page.clean` 을 지난 것), "body": 바탕 글 | None, "meta": meta}. 없으면 KeyError, 문서 서식이 아니거나 값이 틀리면 ValueError
    (문서 서식 모듈 `app.style_page` 가 없어도 ValueError)."""
    meta = style_lib.get(sid)
    if meta is None:
        raise KeyError("그 서식이 서식 보관함에 없습니다")
    if meta.get("kind") != "page":
        raise ValueError("문서 서식이 아닙니다 — 표 서식은 표에, 글 서식은 문단에 입힙니다")
    try:
        from app import style_page
    except ImportError as e:
        raise ValueError("문서 서식 모듈(app.style_page)이 없어 쪽 설정을 입히지 못합니다") from e
    return {"page": style_page.clean(meta.get("page")), "body": meta.get("body") if isinstance(meta.get("body"), dict) else None, "meta": meta}


def page_hosts(doc) -> list:
    """구역마다의 첫 문단(쪽 설정 hp:secPr 을 품은 문단) — 쪽 설정을 바꾸는 편집이 닿는 최상위 문단들(구조 편집의 before·hosts)."""
    return [p for p in (next(sec.iterchildren(P), None) for sec in doc._sections) if p is not None]


def set_page(doc, pstyle) -> int:
    """hwpx 문서 doc 의 **모든 구역**의 쪽 설정(용지 크기·방향·여백)을 문서 서식 pstyle(`page_style`)의 값으로 -> 바꾼 구역 수(`style_page.set_page`).
    바탕 글 모양은 문서에 입히지 않는다(v1 — ② §5). 바꿀 구역이 없으면 ValueError."""
    from app import style_page
    n = int(style_page.set_page(doc, pstyle["page"]) or 0)
    if n < 1:
        raise ValueError("이 문서에서 쪽 설정을 찾지 못해 문서 서식을 입히지 못했습니다")
    for p in page_hosts(doc):  # 쪽 설정이 든 구역을 「고친 부분」 으로(저장·블록 캐시) — set_page 가 이미 했어도 해롭지 않다
        doc._touch(p)
    return n


# ---- 표지 서식(표지 넣기 — spec_서식복사 ② §14) -----------------------------------------------------------------------

def cover_style(sid: str) -> dict:
    """표지 서식 하나 → {"src": 운반 문서(HwpxDoc — 블록 id 가 붙은 채), "parts": meta.parts, "meta": meta}. 없으면 KeyError, 표지 서식이 아니면 ValueError."""
    meta, data = style_lib.get(sid), style_lib.carrier(sid)
    if meta is None or data is None:
        raise KeyError("그 서식이 서식 보관함에 없습니다")
    if meta.get("kind") != "cover":
        raise ValueError("표지 서식이 아닙니다 — 표지 넣기는 표지 서식으로 합니다")
    return {"src": style_carrier.doc(data), "parts": meta.get("parts") or [], "meta": meta}


def cover_insert(doc, cstyle, *, session=None) -> dict:
    """hwpx 문서 doc 의 **맨 앞**에 표지 서식 cstyle(`cover_style`)의 블록들을 넣는다(`style_cover.insert(doc, 운반 문서)` — 원래 첫 블록은 다음 쪽에서 시작 · 구역 설정을 품은 첫 문단의 자리는 지킨다)
    -> {"blocks": [새 블록 id…], "after": 표지 바로 뒤 블록 id | None}. 구조 편집의 `run()` 안에서 부른다.
    다른 적용 함수와 같은 앞뒤 검사: 가져오기 전에 운반 문서의 끊어진 정의 참조(`source_check`) · 가져온 뒤 판정 기준선과 새 정의의 참조(`_imported`).
    표지 모듈(`app.style_cover`)이 없거나 넣은 블록이 없으면 ValueError."""
    try:
        from app import style_cover
    except ImportError as e:
        raise ValueError("표지 서식 모듈(app.style_cover)이 없어 표지를 넣지 못합니다") from e
    src = cstyle["src"]
    source_check(src)
    before = defs_state(doc)
    got = style_cover.insert(doc, src)
    got = got if isinstance(got, dict) else {}
    ids = [i for i in got.get("blocks") or [] if isinstance(i, str) and i in doc._ids and doc._attached(doc._ids[i])]
    if not ids:
        raise ValueError("표지 서식에서 넣은 블록이 없습니다")
    _imported(doc, before, src, session)
    after = got.get("after")
    return {"blocks": ids, "after": after if isinstance(after, str) and after in doc._ids else None}


# ---- docx 문서(spec_서식복사 ② §9 — 빈 표 넣기 · 문단에 입히기만) --------------------------------------------------------

def docx_open(data: bytes):
    """docx 운반 문서를 연 것(블록 id 가 붙은 채 — 적용 때의 `src`). 못 열면 ValueError."""
    from app.docx_doc import DocxDoc
    try:
        d = DocxDoc(data)
        d.blocks()
    except Exception as e:  # noqa: BLE001 — 깨진 zip·XML 은 종류가 여럿이다
        raise ValueError(f"docx 운반 문서를 열 수 없습니다: {type(e).__name__}: {e}") from e
    return d


def docx_style(sid: str, kind: str) -> dict:
    """보관함 템플릿 하나(docx 문서에 쓸 것) → {"meta": meta, "items": meta.items(글 서식)}. 없으면 KeyError, 종류(kind = "table" | "text")가 다르면 ValueError."""
    meta = style_lib.get(sid)
    if meta is None:
        raise KeyError("그 서식이 서식 보관함에 없습니다")
    if meta.get("kind") != kind:
        raise ValueError("표 서식이 아닙니다 — 빈 표 넣기는 표 서식으로 합니다" if kind == "table" else "글 서식이 아닙니다 — 문단에 입히기는 글 서식으로 합니다")
    return {"meta": meta, "items": meta.get("items") or []}


def docx_top_level(doc, block_id):
    """docx 문서에서 block_id 가 **본문 최상위 블록**(본문 바로 아래 문단·표, 또는 그 문단의 그림)이면 그 블록 요소 — 아니면(없는 id · 칸 안) ValueError."""
    from app import docx_struct
    el = doc._ids.get(block_id) if isinstance(block_id, str) else None
    if el is None or not doc._attached(el):
        raise ValueError("넣을 자리의 블록이 지금 문서에 없습니다 — 넣을 자리는 본문 최상위 블록만 됩니다")
    try:
        blk = doc._block(el)
    except (ValueError, StopIteration) as e:
        raise ValueError("넣을 자리는 본문 최상위 블록(문단·표·그림)만 됩니다") from e
    if docx_struct.top_host(doc, blk) is not blk:
        raise ValueError("넣을 자리는 본문 최상위 블록만 됩니다(표 칸 안에는 넣지 않습니다)")
    return blk


def docx_table_blank(doc, src, meta, after) -> dict:
    """docx 문서 doc 의 after(본문 최상위 블록) 바로 뒤에 docx 운반 문서 src(`docx_open`)의 표를 **그대로** 넣고 채울 칸을 비운다 -> {table, host, rows, cols}.
    비우는 칸은 hwpx 의 `table_blank` 와 같은 규칙: meta.blueprint 가 있으면 그 `input`·`computed` 칸, 없으면 라벨 칸이 아닌 칸 — 라벨 칸 = meta.labels, 그것도 없으면
    `style_carrier.kept_labels`(견본 글만 든 칸은 라벨이 아니다). 표 폭은 운반 문서 그대로(대상 문서의 글 폭에 맞추지 않는다 — v1)."""
    docx_top_level(doc, after)
    try:
        from app import style_docx
    except ImportError as e:
        raise ValueError("docx 서식 모듈(app.style_docx)이 없어 표를 넣지 못합니다") from e
    new = doc.insert_after(after, [{"kind": "copy", "srcId": style_docx.table_id(src)}], src=src)[0]
    tbl = doc._ids[new]
    block = doc._table_block(tbl, {"num": {}, "seq": {}, "reset": {}})
    meta = meta if isinstance(meta, dict) else {}
    bands = M.clean_roles(meta.get("bands"), block["nRows"], block["nCols"])
    bp = meta.get("blueprint") or {}
    roles = {(c.get("row"), c.get("col")): c.get("role") for c in bp.get("cells") or [] if isinstance(c, dict)}
    given = meta.get("labels")
    labels = {tuple(rc) for rc in given if isinstance(rc, (list, tuple)) and len(rc) == 2} if isinstance(given, list) else style_carrier.kept_labels(block, bands)
    for c in block["cells"]:
        role = roles.get((c["row"], c["col"])) if roles else None
        keep = role in LABEL_ROLES if role else (c["row"], c["col"]) in labels
        if not keep:
            doc._blank_cell(doc._ids[c["id"]])
    doc._touch_doc()
    return {"table": new, "host": new, "rows": block["nRows"], "cols": block["nCols"]}


def docx_changes(fmt, source_format=None) -> dict:
    """서식 요약 사전 → `DocxDoc.derive_format` 이 받는 바꿀 값(아는 키·범위 안의 값만 — `style_carrier._clean_format`).
    **내어쓰기**(첫 줄 < 0): 한글은 첫 줄이 왼쪽 여백에서 시작하고 둘째 줄부터 그만큼 들어가지만 Word 는 왼쪽 여백에서 첫 줄을 그만큼 내어 쓴다 —
    한글에서 온 서식(원본이 docx 가 아님)은 왼쪽 여백에 그 폭을 더해 같은 모양이 되게 한다. docx 에서 온 서식 요약은 이미 Word 의 뜻이다."""
    from app import docx_format
    ch = {k: v for k, v in style_carrier._clean_format(fmt).items() if k in docx_format._KEYS}
    if "align" in ch and ch["align"] not in docx_format._ALIGN_OUT:
        del ch["align"]
    first = ch.get("firstLineMm")
    if source_format != "docx" and isinstance(first, (int, float)) and first < 0:
        ch["indentLeftMm"] = round(float(ch.get("indentLeftMm") or 0) - first, 2)
    return ch


def docx_format_paras(doc, tstyle, key, para_ids, keep_numbering=True) -> list[str]:
    """docx 문서의 문단들에 글 서식 항목 key 의 모양을 입힌다 -> 모양이 바뀐 문단 id. tstyle = `docx_style(sid, "text")`. 글·레터는 안 바꾼다.
    항목의 **서식 요약**(글꼴·크기·굵게·기울임·밑줄·색·장평·자간·정렬·여백·첫 줄·줄 간격·문단 간격)을 문단마다 제 서식 위에 덮는다(`derive_format` → `apply_format`) —
    요약에 없는 모양(스타일·테두리·탭)은 그 문단 것 그대로. keep_numbering = 문단마다 제 번호 설정을 지킨다."""
    from lxml import etree
    _, it = _item(tstyle, key)
    ch = docx_changes(it.get("format"), ((tstyle.get("meta") or {}).get("source") or {}).get("format"))
    if not ch:
        raise ValueError("그 글 서식 항목에 입힐 서식 값이 없습니다")
    ps = []
    for pid in para_ids:
        el = doc._ids.get(pid) if isinstance(pid, str) else None
        if el is None or not str(el.tag).endswith("}p") or not doc._attached(el):
            raise ValueError("서식을 입힐 문단이 지금 문서에 없습니다")
        ps.append(el)
    changed = []
    for pid, el in zip(para_ids, ps):
        was = etree.tostring(el)
        doc.apply_format([pid], doc.derive_format(doc.get_format(pid), ch), keep_numbering=keep_numbering)
        if etree.tostring(el) != was:
            changed.append(pid)
    if changed:
        doc._touch_doc()
    return changed

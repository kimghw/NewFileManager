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
  LRU 로 밀려난 세션은 거기 없어 못 찾는다(astra)."""
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

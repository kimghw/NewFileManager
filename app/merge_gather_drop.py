"""취합 — 끌어 넣기(spec_취합 ② §4-6 · jobs/plan_merge.md 「사람이 직접 넣을 수도 있다」): 기관 문서의 절(제목 줄 + 그 아래 내용 묶음)을 사람이 끌어 취합본 본문 블록 뒤에 놓는다.
바로 넣지 않는다 — `plan`(두 문서 모두 안 바뀜)을 보이고 「반영」 때 `apply`. 기관 문서(원본)는 읽기만 한다.

- `plan(to, part, src_id, after_id)` — to·part = {"doc", "graph"}(merge_api._read 의 그 꼴 — 블록은 늘 문서에서 다시 읽는다, 그래프 = 2단계 헤딩 그래프 | None) →
  {"src": [복사할 기관 문서 블록 id — 문서 순], "srcTop": src_id, "after": {"id": 넣을 기준 블록(취합본 최상위 — 이 블록 뒤), "text", "given": after_id},
   "range": {"title", "blocks", "paragraphs", "tables", "pictures"(셋 다 최상위 블록 수 — 합 = blocks = 넣을 블록 수), "lines": 개요 줄 수, "single": 블록 하나뿐인가},
   "owner": {"id": 놓은 자리를 품은 취합본 제목 줄(문단 id) | None, "text"}, "convert": 틀 맞춤 미리보기 | None(품은 제목 줄이 없거나 그래프가 없음),
   "dropped": [{"src", "what": 요소 이름}](복사에서 빠지는 개체 — merge_fill 과 같은 꼴), "hash": 범위 지문}.
  **복사 범위** = 끈 줄(src_id — 기관 문서 본문 최상위 문단)부터, 문서 순으로 **그 줄의 그래프 자손이 아닌 첫 본문 노드** 앞까지(없으면 문서 끝). 레벨 숫자는 견주지 않는다 —
  서브 템플릿·구분 라벨은 제 사슬의 L1 이라 숫자로는 「윗 레벨」 처럼 보인다(「(1)-1 …」 아래 「[1단계 목표]」). 범위는 본문 최상위 블록의 이어진 띠라 표 칸을 드나들지 않고,
  표·그림은 블록째(캡션은 표·그림에 딸려 가므로 따로 안 넣음), 문단에 딸린 표·그림은 그 문단 다음 블록으로 한 번씩. 앞뒤 빈 줄·쪽 나눔은 기관 문서 그대로.
  끈 줄이 절의 제목 줄(그래프 heading·subtitle·label·title)이 아니면 그 블록 하나만(`single`). 표 칸 안 줄·캡션은 `DropError`. 「같은 제목이면 제목 줄 빼기」 는 없다(늘 제목 줄부터).
  **놓을 자리** = after_id(취합본 본문 최상위 블록)를 품은 문단의 끝 — 표·그림을 품은 문단은 그 표·그림(과 캡션) 뒤(`after.id` = 그 문단의 마지막 블록). 표 칸 안이면 `DropError`.
  **품은 제목 줄**(owner) = 놓은 자리까지의 마지막 본문 노드에서 그래프 부모를 올라가며 처음 만나는 제목 줄(heading·subtitle·label) — 글 없는 글머리 줄(양식의 자리표시 「o 」)은 건너뛴다.
  **틀 맞춤 미리보기** = `merge_convert.plan(취합본 그래프, 기관 문서 그래프, owner, src)` — 복사한 개요 줄을 owner 의 **자식**으로(owner 레벨 + 1 부터, 번호형은 처음부터):
  {"converted": 바뀔 줄 수, "kept": {까닭: 줄 수}, "labels": {까닭: 화면에 보일 글(WHY)}, "anchor": [템플릿, 레벨] | None,
   "rows": [{"src", "was": 원본 레터, "letter": 새 레터 | None, "why"}](개요 줄만, ROWS_MAX 까지), "more": 못 실은 줄 수}.
  까닭 = merge_convert 의 것(body·table·label·multi·otherChain·hetero·tooDeep·noAnchor·noLike·numEnd·noLetter, `cell` = 복사한 표의 칸 안 개요 줄 수) + **branch**:
  owner 바로 아래 헤딩 줄이 취합본에 이미 있는데 모두 owner 와 다른 사슬(서브 템플릿)일 때 — merge_convert 는 owner 템플릿의 다음 레벨로 보내므로(「1-2.」 아래 「□」 를 「가.」 로)
  그 자리의 틀과 어긋난다. 근거 없는 레벨을 만들지 않고 원본 모양 그대로 둔다. 형광펜·변경 추적 표지 줄(marker)은 문서를 고쳐 봐야 드러나므로 반영 결과에만 나온다.
- `apply(to_doc, part_doc, plan, to_graph, part_graph, convert=True)` — `server._transact` 의 run 안에서 부른다(트랜잭션·잠금·차례(rev) 확인은 부르는 쪽). 계획을 지금 문서·그래프로
  **다시 풀어** 계획과 같을 때만 넣는다(복사 범위의 id·지문 · 놓을 자리 · 품은 제목 줄 — 하나라도 다르면 문서를 건드리기 전에 `DropError`). `insert_after(kind=copy)` →
  convert 이고 품은 제목 줄이 있으면 틀 맞춤(`merge_convert.apply`) → 넣은 그림 `fit_image` →
  {"ids": [넣은 블록 id — src 와 같은 차례], "blocks", "converted", "kept": {까닭: n}, "labels": {까닭: 글}, "fitted": 줄인 그림 수, "dropped": [...]}.
  convert=False 거나 품은 제목 줄이 없으면 기관 문서 모양 그대로(converted 0 · kept {}).
- `DropError(ValueError)` — 사람에게 보일 까닭. `_transact` 는 ValueError 를 400 으로 돌려준다(계획 끝점은 직접 400 으로).
ponytail: 번호는 잇지 않는다(틀 맞춤이 「2-3.」 을 「2-1.」 로 — 형제 번호와 겹칠 수 있다, spec_취합 ④ ⓔ) · 글과 표·그림이 한 문단에 있던 것은 글 문단 + 개체 문단 둘이 된다(한 문단의 표·그림끼리는 한 문단 그대로 — hwpx_doc._row_para, spec_병합 ② §5)."""
import hashlib
import json
from collections import Counter

from app import merge_chunks as C
from app import merge_convert as MC
from app import merge_fill as F
from app.division_llm import _short
from app.division_profiles.rnd import core
from app.outline_edit import ROOTED, prefix_of

SECTION = C.HEADS                  # 절의 제목 줄이 되는 그래프 노드(heading·subtitle·label·title) — 그 밖(안내·헤딩 아님·노드 없는 줄)은 블록 하나만
OWNERS = ("heading",) + ROOTED     # 틀 맞춤의 기준(놓은 자리를 품은 제목 줄)이 되는 노드
TEXT_LEN, ROWS_MAX = 60, 300
STALE = "계획을 세운 뒤 문서나 분석 결과가 바뀌었습니다 — 다시 끌어 놓아 주세요"
WHY = {"body": "개요 줄이 아닌 줄(본문·빈 줄·그림)", "table": "표", "cell": "표 칸 안 개요 줄", "label": "구분 라벨·괄호 소제목", "multi": "한 문단에 개요 줄이 둘 이상",
       "otherChain": "다른 사슬(서브 템플릿)의 줄", "hetero": "이종 형제(그 자리의 기본 레터와 다른 줄)", "tooDeep": "취합본 틀에 받을 레벨이 없음(더 깊음)",
       "noAnchor": "놓은 자리의 제목 줄이 개요 줄이 아님", "noLike": "그 레벨의 본보기 줄이 취합본에 없음", "numEnd": "번호 열이 끝남", "noLetter": "첫머리에 레터가 없음(자동 번호 등)",
       "marker": "형광펜·변경 추적 표지가 든 줄", "missing": "넣은 사본을 찾지 못함", "branch": "놓은 자리 아래는 다른 사슬(서브 템플릿)이 붙는 자리"}   # 그대로 둔 까닭 — 화면에 보일 글


class DropError(ValueError):
    """끌어 넣을 수 없는 까닭(사람에게 보이는 글)."""


def _body(graph, at):
    """본문 흐름의 그래프 노드 [(최상위 차례, 노드)] — 문서 순. 1칸 상자 안 줄도 본문 흐름이다(차례 = 그 상자의 자리). 표 칸·글상자·머리말 흐름은 뺀다(그 그릇째 딸려 간다)."""
    return sorted(((at[n["para"]][0], n) for n in (graph or {}).get("nodes") or () if n.get("flow") == "body" and n.get("para") in at),
                  key=lambda x: (x[0], x[1].get("n", 0)))


def _up(n, by_id):
    """n 의 그래프 조상(가까운 것부터) — 부모 고리는 본문 뿌리·그릇 id 에서 끝난다."""
    seen, p = {n["id"]}, by_id.get(n.get("parent"))
    while p is not None and p["id"] not in seen:
        seen.add(p["id"])
        yield p
        p = by_id.get(p.get("parent"))


def _top(doc, bid):
    """그 블록이 본문 최상위인가(그 블록을 품은 문단이 구역 바로 아래) — 표 칸·캡션 안이 아님."""
    el = doc._ids.get(bid)
    return el is not None and doc._host(el).getparent() in doc._sections


def _label(b):
    """블록 하나의 앞부분 글(화면에 보일 것)."""
    if b.get("type") == "table":
        cells = sorted(b.get("cells") or (), key=lambda c: (c.get("row", 0), c.get("col", 0)))
        return _short("표 " + " | ".join(t for c in cells[:8] if (t := _short(c.get("text"), 20))), TEXT_LEN)
    return "그림" if b.get("type") == "image" else _short(b.get("text"), TEXT_LEN) or "(빈 줄)"


def _range(doc, blocks, graph, src_id):
    """끈 줄 → (복사할 최상위 블록 — 문서 순, 블록 하나뿐인가). 모듈 설명 「복사 범위」."""
    at = C.index(blocks)
    if src_id not in at:
        raise DropError("끌어 온 줄이 기관 문서에 없습니다 — 문서가 바뀌었으면 다시 끌어 주세요")
    i, lst, _ = at[src_id]
    if lst is blocks and blocks[i].get("captionOf"):
        raise DropError("캡션은 따로 끌 수 없습니다 — 표·그림과 함께 옮겨집니다")
    if lst is not blocks or not _top(doc, src_id):
        raise DropError("표 칸 안의 줄은 끌 수 없습니다 — 본문의 제목 줄을 끌어 주세요")
    body = _body(graph, at)
    k = next((j for j, (_, n) in enumerate(body) if n["para"] == src_id), None)
    if k is None or body[k][1].get("role") not in SECTION:
        return [blocks[i]], True
    by_id, top = {n["id"]: n for n in graph["nodes"]}, body[k][1]["id"]
    # 끝 = 자손이 아닌 첫 본문 노드의 자리(같은 문단의 강제 줄 바꿈 뒤 줄이면 이 문단까지) — 노드의 문단 블록은 제 표·그림보다 앞이라 문단과 그 표 사이를 자르지 않는다
    end = next((max(p, i + 1) for p, n in body[k + 1:] if all(a["id"] != top for a in _up(n, by_id))), len(blocks))
    return [b for b in blocks[i:end] if not b.get("captionOf") and _top(doc, b["id"])], False   # 캡션 안에 든 개체(드묾)도 그 표·그림에 딸려 간다


def _after(doc, blocks, at, after_id):
    """놓은 블록 → (넣을 기준 블록 — 이 블록 뒤, 그 자리의 최상위 차례). 모듈 설명 「놓을 자리」."""
    if after_id not in at:
        raise DropError("놓을 자리가 취합본에 없습니다 — 문서가 바뀌었으면 다시 놓아 주세요")
    k, lst, _ = at[after_id]
    if lst is not blocks:
        raise DropError("표 칸 안에는 놓을 수 없습니다")
    if blocks[k].get("captionOf") in at:   # 캡션 위에 놓음 = 그 표·그림 뒤
        k = at[blocks[k]["captionOf"]][0]
    ref = blocks[k]
    if not _top(doc, ref["id"]):
        raise DropError("표 칸 안에는 놓을 수 없습니다")
    host, last, mine = doc._host(doc._ids[ref["id"]]), k, {ref["id"]}
    for j in range(k + 1, len(blocks)):   # 같은 문단에 딸린 표·그림(과 캡션)을 지나 그 문단의 끝으로 — insert_after 는 그 문단 뒤에 넣는다
        x = blocks[j]
        if x.get("captionOf") in mine:
            last = j
        elif x.get("type") != "paragraph" and not x.get("captionOf") and doc._host(doc._ids[x["id"]]) is host:
            ref, last = x, j
            mine.add(x["id"])
        else:
            break
    return ref, last


def _owner(graph, at, pos):
    """놓은 자리(최상위 차례 pos 뒤)를 품은 제목 줄 노드 | None. 모듈 설명 「품은 제목 줄」."""
    body = [n for p, n in _body(graph, at) if p <= pos]
    if not body:
        return None
    by_id = {n["id"]: n for n in graph["nodes"]}
    return next((n for n in (body[-1], *_up(body[-1], by_id)) if n.get("role") in OWNERS and (n["role"] in ROOTED or not n.get("blank"))), None)


def _resolve(to_doc, to_graph, part_doc, part_graph, src_id, after_id):
    """지금 문서·그래프로 → (복사할 블록, 블록 하나뿐인가, 넣을 기준 블록, 품은 제목 줄 노드 | None). 문서는 안 바뀐다(블록 id 만 붙는다)."""
    src, single = _range(part_doc, part_doc.blocks(), part_graph, src_id)
    blocks = to_doc.blocks()
    at = C.index(blocks)
    ref, pos = _after(to_doc, blocks, at, after_id)
    return src, single, ref, _owner(to_graph, at, pos)


def _branch(graph, para):
    """그 제목 줄 바로 아래 헤딩 줄(자리표시 줄 포함)이 취합본에 있는데 모두 다른 사슬(서브 템플릿)인가 — 그러면 그 줄의 자식 자리는 제 템플릿의 다음 레벨이 아니다."""
    nodes = graph.get("nodes") or ()
    line = lambda n: bool(n.get("template") and n.get("level"))  # noqa: E731
    an = next((n for n in nodes if n["para"] == para and line(n)), None)   # merge_convert 가 넣을 자리로 보는 그 노드(문단의 첫 개요 노드)
    if an is None:
        return False
    by_id = {n["id"]: n for n in nodes}
    parent = lambda n: next((a["id"] for a in _up(n, by_id) if a.get("role") not in MC._CLEAR), None)  # noqa: E731 — 안내·헤딩 아님은 투명
    kids = [n for n in nodes if n.get("role") == "heading" and line(n) and n.get("flow") == an.get("flow") and parent(n) == an["id"]]
    return bool(kids) and not any(n["template"] == an["template"] and int(n["level"]) == int(an["level"]) + 1 for n in kids)


def _convert(to_graph, part_graph, owner, ids):
    """틀 맞춤 계획(merge_convert.plan 의 rows) — 품은 제목 줄(owner 문단 id)의 자식으로. 서브 템플릿이 붙는 자리(_branch)는 바꾸지 않는다(why branch)."""
    p = MC.plan(to_graph, part_graph, owner, ids)
    if _branch(to_graph, owner):
        for r in p["rows"]:
            if not r["why"]:
                r.update(why="branch", slot=None, like=None, letter=None, likeLetter=None)
    return p


def _preview(to_doc, part_doc, p):
    """계획 rows → 틀 맞춤 미리보기(merge_convert.apply 와 같은 셈 — 문서는 안 고치고 첫머리 레터만 읽어 본다)."""
    kept, rows, n = Counter(), [], 0
    for r in p["rows"]:
        why = r["why"]
        if not why:
            like = to_doc._ids.get(r["like"])
            if not prefix_of(part_doc._text(part_doc._ids[r["src"]]), r["was"] or None)[1]:
                why = "noLetter"
            elif like is None or not prefix_of(to_doc._text(like), r["likeLetter"] or None)[1]:
                why = "noLike"
        if why:
            kept[why] += 1
            kept["cell"] += r["cells"]
        else:
            n += 1
        if r["level"]:
            rows.append({"src": r["src"], "was": r["was"], "letter": None if why else r["letter"], "why": why})
    kept = {k: v for k, v in kept.items() if v}
    return {"converted": n, "kept": kept, "labels": _labels(kept), "anchor": p["summary"]["anchor"], "rows": rows[:ROWS_MAX], "more": max(0, len(rows) - ROWS_MAX)}


def _labels(kept):
    return {k: WHY.get(k, k) for k in kept}


def _hash(src):
    rows = [[x.get("id"), x.get("type"), x.get("text") or ""] for b in src for x in core._under(b)]
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _lost(part_doc, ids):
    return [{"src": s, "what": w} for s in ids for w in F._dropped(part_doc, s)]


def plan(to, part, src_id, after_id):
    """끌어 넣기 계획(모듈 설명) — 두 문서 모두 안 바뀐다. 끌 수 없거나 놓을 수 없으면 DropError."""
    to_doc, part_doc = to["doc"], part["doc"]
    to_graph, part_graph = to.get("graph") or {}, part.get("graph") or {}
    src, single, ref, owner = _resolve(to_doc, to_graph, part_doc, part_graph, src_id, after_id)
    ids, kinds = [b["id"] for b in src], Counter(b.get("type") for b in src)
    lines = {n["para"] for n in part_graph.get("nodes") or () if n.get("template") and n.get("level")}
    return {"src": ids, "srcTop": src_id, "after": {"id": ref["id"], "text": _label(ref), "given": after_id},
            "range": {"title": _label(src[0]), "blocks": len(ids), "paragraphs": kinds["paragraph"], "tables": kinds["table"], "pictures": kinds["image"],
                      "lines": sum(i in lines for i in ids), "single": single},
            "owner": {"id": owner["para"] if owner else None, "text": _short(f"{owner.get('letter') or ''} {owner.get('text') or ''}", TEXT_LEN) if owner else ""},
            "convert": _preview(to_doc, part_doc, _convert(to_graph, part_graph, owner["para"], ids)) if owner and part_graph.get("nodes") else None,
            "dropped": _lost(part_doc, ids), "hash": _hash(src)}


def apply(to_doc, part_doc, plan, to_graph, part_graph, convert=True):
    """계획을 취합본에 넣는다(모듈 설명) — 지금 문서·그래프로 다시 푼 것이 계획과 다르면 넣기 전에 DropError. 기관 문서는 읽기만."""
    to_graph, part_graph = to_graph or {}, part_graph or {}
    src, _, ref, owner = _resolve(to_doc, to_graph, part_doc, part_graph, plan["srcTop"], plan["after"]["id"])
    ids, owner = [b["id"] for b in src], owner["para"] if owner else None
    if ids != list(plan["src"]) or _hash(src) != plan["hash"] or ref["id"] != plan["after"]["id"] or owner != (plan.get("owner") or {}).get("id"):
        raise DropError(STALE)
    dropped = _lost(part_doc, ids)
    new = to_doc.insert_after(ref["id"], [{"kind": "copy", "srcId": s} for s in ids], src=part_doc)
    done = {"converted": 0, "kept": {}}
    if convert and owner and part_graph.get("nodes"):   # 받을 레벨이 있는 줄만 바뀐다 — 없으면 기관 문서 모양 그대로(까닭별로 셈)
        r = MC.apply(to_doc, list(zip(ids, new)), _convert(to_graph, part_graph, owner, ids))
        done = {"converted": r["converted"], "kept": r["kept"]}
    return {"ids": new, "blocks": len(new), **done, "labels": _labels(done["kept"]), "fitted": sum(to_doc.fit_image(i) for i in new), "dropped": dropped}

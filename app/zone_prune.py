"""빈 구역 지우기(spec_워크플로우 ② §18-23 「빈 구역 지우기」) — 구분 기준 묶음(기관 · 단계 · 차년도마다 되풀이되는 절 · 표 행 · 표 열)의 항목 가운데 **내용이 없는 것**을 찾아 지운다.
2026-11-22 사용자 "구분기준이나 편집구역에 내용이 없는 테이블의 셀이나 본문들을 제거하는 도구도 문서 정리에 포함해줘". **순수** — 세션 · 서버를 가져오지 않는다(끝점 · 저장은 `app/zone_prune_api.py`).

- 경계 = `core.find` 의 묶음(「프로젝트 구성 반영」 이 늘리고 줄이는 바로 그 자리) · 지우기 = 같은 엔진의 지우기(`delete_blocks` · `delete_rows` · `delete_cols` — 아래 · 오른쪽부터). 남은 항목의 이름 · 번호는 바꾸지 않는다.
- **내용이 없다**(`_own`): 그 항목의 라벨을 뺀 글이 모두 ⓐ 빈 글 · 자리표시 · 글머리뿐(`_bare`)이거나 ⓑ 같은 묶음의 **모든** 항목에 똑같이 든 글(양식의 뼈대 — `_norm`: 구분 낱말 · 번호 · 기관 이름 · 연도를 뗀 꼴)이거나
  ⓒ 양식 안내(`form_cleanup.find` 가 찾는 블록 — `guide_ids`)이고, 그림 · 개체가 없다(`has_object` — 블록 JSON 에 안 보이는 묶음 개체까지: 끝점이 문서의 XML 로 본다). 표 행 · 열의 칸은 「-」 · 수 하나도 내용이다.
- 지우지 않는 것: 항목이 하나뿐인 묶음 · 모든 항목이 빈 묶음(`allEmpty` — 양식의 틀) · `irregular` 묶음 · 세부과제 묶음 · 라벨 없는 목록 묶음 · 다른 지울 항목 안에 든 항목(바깥이 먼저) · 병합 칸에 걸려 못 지우는 표 묶음(`blocked`).
- `find(blocks, values, levels, …)` → {"items"[지울 항목], "kept"[모두 비어 남긴 묶음 · 못 지우는 묶음], "counts"{items, blocks(본문 항목), rows, cols, kept}} · `apply(doc, found)` → {"removed"{blocks, rows, cols}, "skipped"[…]}."""
import re

from app import heading_calc as HC
from app.division_profiles import _structure as structure
from app.division_profiles.rnd import core

DIMS = {core.ORG: "org", core.STAGE: "stage", core.YEAR: "year", core.STAGE_YEAR: "year"}   # 지울 수 있는 구분 기준(세부과제는 뺀다 — 값을 정하지 않은 문서가 많다)
KIND_NAME = {"paragraph": "본문", "rows": "표 행", "cols": "표 열"}
_YEARS = re.compile(r"(?:19|20)\d\d\s*년?|\d+\s*(?:차\s*년도|년차|단계)")
_PUNCT = re.compile(r"[\s\-–—·‧∙※*\[\](){}（）:：.,、/|~]+")


def _names(values):
    """뼈대 견줌에서 뗄 기관 이름(긴 것부터) — 반영이 항목마다 다르게 적어 넣는 글이다(그 글은 내용이 아니다)."""
    v = values or {}
    names = list(core.org_names(v)) if v.get("orgs") else []
    for kind in core.EXTRA:
        names += [n for n in ((v.get("orgs") or {}).get(kind) or ()) if isinstance(n, str)]
    return sorted({n.strip() for n in names if isinstance(n, str) and len(n.strip()) >= 2}, key=len, reverse=True)


def _norm(text, names):
    """견줌의 꼴 — 엔진의 항목 비교 꼴(`core._content`)에서 기관 이름 · 연도 · 차년도 번호를 더 뗀다(값만 다른 양식 글은 같게)."""
    t = text or ""
    for n in names:
        t = t.replace(n, "{기관}")
    return core._content(_YEARS.sub("{연도}", t))


def _bare(text, cell=False):
    """빈 글인가 — 글머리 · 자리표시 · 구분 낱말만. cell = 표의 칸(수 하나 · 「-」 도 값이다: table_prune 과 같다)."""
    raw = (text or "").strip()
    if not raw:
        return True
    if HC.parse_num(raw).get("placeholder") or core.NAME_SLOT.match(raw) or core.EXAMPLE_SLOT.match(raw):
        return True
    if cell and (re.fullmatch(r"[-–—]", raw) or re.search(r"\d", core.NOTE.sub("", raw))):
        return False
    return not core._authored(core._content(raw))


def _walk(it, g, idx):
    """항목의 블록 · 칸 안 문단 → [(문단 id, 글)] · 개체 블록이 있나 — 라벨(문단 · 칸)은 뺀다."""
    paras, objs = [], False
    for rid in it["roots"]:
        b = idx.get(rid)
        if b is None:
            continue
        for x in core._under(b):
            if x.get("id") == it["label"]:
                continue
            t = x.get("type")
            if t == "paragraph":
                paras.append((x["id"], x.get("text") or ""))
            elif t not in (None, "table"):
                objs = True   # 그림 · 수식 같은 개체 블록 — 내용이다
    lab = idx.get(it["label"])   # 라벨이 표 칸(표 묶음)이면 그 칸 안의 문단도 라벨이다
    skip = {p["id"] for p in core._paras(lab)} if lab is not None else set()
    return [(i, t) for i, t in paras if i not in skip], objs


def _own(paras, skeleton, names, cell, guide_ids, has_object):
    """항목의 「제 내용」 문단 id 들 — 뼈대 · 빈 글 · 양식 안내가 아닌 것(그림 · 개체가 든 문단은 늘 내용)."""
    out = []
    for pid, text in paras:
        if pid in guide_ids:
            continue
        if has_object(pid):
            out.append(pid)
            continue
        if _bare(text, cell) or _norm(text, names) in skeleton:
            continue
        out.append(pid)
    return out


def _cells_of(it, idx):
    """항목이 차지한 블록 · 칸 id(라벨 포함 — id 가 없는 것은 뺀다)."""
    return {x for x in set(it["scope"]) | {it["label"]} if isinstance(x, str)}


def find(blocks, values, levels, *, hints=None, prior=None, guide_ids=(), has_object=lambda pid: False):
    """지울 빈 항목 → {"items"[{key(묶음 key), dim, kind, table, label(라벨 id), labelText, roots, span, cross, region, thisYear, ids(지울 블록 · 칸 id)}],
    "kept"[{key, dim, kind, table, why, labels[…]}], "counts"}. values = 그 문서의 프로젝트 구성 값(core.norm_values 꼴)."""
    groups = core.find(blocks, levels, values, hints=hints or None, prior=prior)
    idx = structure.index_blocks(blocks)
    guide_ids, names = set(guide_ids or ()), _names(values)
    cands, kept = [], []
    for g in groups:
        if g["dim"] not in DIMS or g.get("irregular") or len(g["items"]) < 2 or g["kind"] not in KIND_NAME or any(not it.get("label") for it in g["items"]):
            continue   # 라벨 없는 목록 묶음(「연구개발기관명 N번째」 행)은 이름 · 안에 든 항목을 가릴 수 없어 건드리지 않는다
        cell = g["kind"] != "paragraph"
        walked = [_walk(it, g, idx) for it in g["items"]]
        norms = [{_norm(t, names) for pid, t in paras if pid not in guide_ids and not _bare(t, cell)} for paras, _ in walked]
        skeleton = set.intersection(*norms) if norms else set()
        empty = [i for i, (it, (paras, objs)) in enumerate(zip(g["items"], walked)) if not objs and not _own(paras, skeleton, names, cell, guide_ids, has_object)]
        base = {"key": g["key"], "dim": DIMS[g["dim"]], "kind": g["kind"], "table": g.get("table")}
        if not empty:
            continue
        if len(empty) == len(g["items"]):
            kept.append({**base, "why": "allEmpty", "labels": [core._short(it["labelText"]) for it in g["items"]]})
            continue
        if g["table"]:
            msg = core._simulate(g, {"drop": empty, "template": next(i for i in range(len(g["items"])) if i not in empty), "copies": 0})
            if msg:
                kept.append({**base, "why": "blocked", "message": msg, "labels": [core._short(g["items"][i]["labelText"]) for i in empty]})
                continue
        region = core._region(g["items"]) if g["kind"] == "cols" else None
        for i in empty:
            it = g["items"][i]
            cands.append({**base, "label": it["label"], "labelText": core._short(it["labelText"]), "roots": list(it["roots"]), "span": it.get("span"), "cross": it.get("cross"),
                          "region": region, "thisYear": bool(g.get("thisYear")), "ids": sorted(_cells_of(it, idx)), "container": g.get("container")})
    # 다른 지울 항목 안에 든 항목은 뺀다(바깥이 먼저 — 바깥을 지우면 같이 없어진다)
    inside = set()
    for a in cands:
        for b in cands:
            if a is not b and b["label"] in set(a["ids"]) and not (a["label"] in set(b["ids"])):
                inside.add(id(b))
    items = [c for c in cands if id(c) not in inside]
    n = lambda k: sum(1 for c in items if c["kind"] == k)  # noqa: E731
    return {"items": items, "kept": kept, "counts": {"items": len(items), "blocks": n("paragraph"), "rows": n("rows"), "cols": n("cols"), "kept": len(kept)}}


def apply(doc, found):
    """찾은 빈 항목을 지운다(문서를 바꾼다 — 끝점이 트랜잭션 안에서 부른다). 표는 표마다 행을 아래부터 → 열을 오른쪽부터 · 본문은 문서 뒤에서부터.
    → {"removed"{blocks, rows, cols, items}, "skipped"[{label, why}], "labels"[지운 항목의 라벨 글]}."""
    items = list(found.get("items") or ())
    order = {b["id"]: i for i, b in enumerate(structure.iter_blocks(doc.blocks()))}
    out = {"removed": {"blocks": 0, "rows": 0, "cols": 0, "items": 0}, "skipped": [], "labels": []}
    tables = {}
    for c in items:
        if c["kind"] in ("rows", "cols"):
            tables.setdefault(c["table"], []).append(c)
    for tid, cs in tables.items():
        rows = sorted((c for c in cs if c["kind"] == "rows"), key=lambda c: -c["span"][0])
        cols = sorted((c for c in cs if c["kind"] == "cols"), key=lambda c: -c["span"][0])
        region = {}
        for c in rows + cols:
            try:
                if c["kind"] == "rows":
                    doc.delete_rows(tid, *c["span"], cols=list(c["cross"]) if c.get("thisYear") else None)
                    out["removed"]["rows"] += c["span"][1] - c["span"][0] + 1
                else:
                    r = region.setdefault(c["key"], list(c["region"]))
                    doc.delete_cols(tid, *c["span"], keep=tuple(r))
                    r[1] -= c["span"][1] - c["span"][0] + 1
                    out["removed"]["cols"] += c["span"][1] - c["span"][0] + 1
                out["removed"]["items"] += 1
                out["labels"].append(c["labelText"])
            except (KeyError, ValueError) as e:
                out["skipped"].append({"label": c["labelText"], "why": str(e)})
    paras = sorted((c for c in items if c["kind"] == "paragraph"), key=lambda c: -order.get(c["roots"][0], -1))
    for c in paras:
        if c["roots"][0] not in order or c["roots"][-1] not in order:
            out["skipped"].append({"label": c["labelText"], "why": "그 자리가 문서에 없습니다"})
            continue
        try:
            doc.delete_blocks(c["roots"][0], c["roots"][-1])
        except (KeyError, ValueError) as e:
            out["skipped"].append({"label": c["labelText"], "why": str(e)})
            continue
        out["removed"]["blocks"] += len(c["roots"])
        out["removed"]["items"] += 1
        out["labels"].append(c["labelText"])
    return out

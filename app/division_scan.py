"""구분 기준 판독 — 연구개발과제 문서(작업 종류 rnd · hwpx)에서 헤딩 추출보다 **먼저** 도는 스크립트 판독(spec_구분_기준 ② §23). 순수 계산 — 서버·세션·LLM 을 부르지 않는다.

한 방향: 판독 → 헤딩 추출(괄호 줄의 구분 라벨 근거) · 판독 + 헤딩 → 편집 구역. 판독은 헤딩 추출 결과를 읽지 않는다(절 경계는 엔진의 간이 레벨 `rnd.levels_of`).
엔진(`core.find` — 계획·반영의 입력)은 바꾸지 않는다. 판독은 엔진의 묶음에 **식별만 하는 근거**를 보탠다(반영 대상이 되지 않는다):
- 구조 라벨 근거 `labels` — 문단마다 [{dim, value, src, text}]. src = engine(엔진 묶음의 라벨) · hint(사람·LLM 이 추가한 자리) · pattern(헤딩의 엄격한 괄호 꼴 `heading_graph.value_basis`) ·
  name(괄호 안 글이 지금 구성의 기관 이름 하나와 통째로 같음). 넓은 표 칸 후보 규칙(`heading_calc.label_basis`)은 확정 근거로 쓰지 않는다(2026-11-18 astra P1).
- 표 안 귀속 `cells`·`tables` — 편집 구역의 「표 안의 값 읽기」(`zones._table_read` — 이름표 칸 · 기관 열)를 이 단계에서 한다. 값은 원래 꼴(열쇠 · 전체 차례 · conflict · 엇갈림)을 그대로.
- 원형 자료(밑줄 키 — JSON 으로 내보내지 않는다): `_groups`(엔진 묶음 그대로 — 값·범위·문맥) · `_best`·`_inside`(묶음 소속) · `_cellEv`(표 안 판독) — 편집 구역이 다시 계산하지 않고 쓴다.

값: `values` = 귀속 값(반영한 값 → 입력 값 — 편집 구역과 같은 차례 · 없으면 None: 이름 라벨·표 안 판독·기관 정체는 안 함) · `find_values` = 값이 없을 때 묶음 찾기에만 쓰는 기본 값(구조 탐지용 — 귀속 근거가 아니다).
"""
import re

from app import division_terms as DT
from app import merge_gather_frame as F
from app import merge_pairs as P
from app import zones as Z
from app.division_profiles import _structure as structure
from app.division_profiles import rnd
from app.division_profiles.rnd import core

VERSION = 1
SRC = ("engine", "hint", "pattern", "name")
# 엔진의 구분 → 헤딩의 구분 기준 이름(heading_graph.BASES). 세부과제는 헤딩의 구분 기준 목록에 없어 헤딩 근거로는 안 쓴다(표시에는 씀)
BASIS = {core.STAGE: "단계", core.YEAR: "차년도", core.STAGE_YEAR: "단계-차년도", core.ORG: "기관"}
_LEAD_BRACKET = re.compile(r"^\s*([\[【][^\]】\n]*[\]】])")


def bracket_of(text):
    """문단 글 첫머리의 괄호 줄 글(「[1차년도 목표]」) | ""."""
    m = _LEAD_BRACKET.match(text or "")
    return m.group(1) if m else ""


def name_key(letter, keys):
    """괄호 줄 글의 안(괄호 한 겹을 벗기고 ※ 뒤를 뗀 글)이 지금 구성의 기관 열쇠 **하나와 통째로** 같으면 그 열쇠 | None.
    「[한국선급]」 → 한국선급 · 「[한국선급 연구 내용]」·「[가나, 다라]」·「[기관N]」 은 아님. 열쇠가 없거나 두 열쇠에 맞으면(정규화 충돌) None."""
    s = (letter or "").strip()
    if len(s) < 2 or DT.BRACKETS.get(s[0]) != s[-1]:
        return None
    inner = core.NOTE.sub("", s[1:-1]).strip()
    k = P.org_key(inner) if inner else ""
    hits = {x for x in keys or () if x and x == k}
    return next(iter(hits)) if len(hits) == 1 else None


def _value_text(dim, v):
    return rnd.value_text(dim, v)


def scan(blocks, values=None, find_values=None, hints=None, prior=None):
    """→ {version, labels{para: [근거 …]}, extra[엔진 묶음 밖의 라벨 문단 — pattern·name], tables{표 id: {org?, year?}}, cells{칸 id: {org?, year?, yearClash?}},
    cellParas{칸 id: [문단 id]}, counts, _groups, _best, _inside, _cellEv}. values·find_values = norm_values 꼴 | None. hints = 추가한 자리 [{para, dim, value, by, …}]."""
    blocks = list(blocks or ())
    hints = [h for h in hints or () if isinstance(h, dict) and h.get("para")]
    fv = values or find_values
    idx = structure.index_blocks(blocks)
    groups = core.find(blocks, rnd.levels_of(blocks), fv, hints=[h["para"] for h in hints] or None, prior=prior) if fv else []
    labels, cell_paras = {}, {}

    def paras_of(i):
        b = idx.get(i)
        if b is None:
            return []
        if b.get("type") == "paragraph":
            return [i]
        return [x["id"] for x in core._paras(b)]

    def put(pid, ev):
        rows = labels.setdefault(pid, [])
        if not any(r["dim"] == ev["dim"] and r["src"] == ev["src"] for r in rows):
            rows.append(ev)

    # 1. 엔진 묶음의 라벨 — 라벨이 칸이면 그 칸 안의 문단(2026-11-18 astra P2: 칸 id 와 문단 id 가 달라 라벨을 놓치던 것)
    for g in groups:
        for it in g["items"]:
            lab = it.get("label")
            if not lab:
                continue
            for pid in paras_of(lab):
                put(pid, {"dim": g["dim"], "value": _value_text(g["dim"], it.get("value")), "src": "engine", "text": _short(it.get("labelText")), "group": g["key"]})
    # 2. 추가한 자리
    for h in hints:
        b = idx.get(h["para"])
        if b is not None and b.get("type") == "paragraph" and h.get("dim"):
            put(h["para"], {"dim": h["dim"], "value": str(h.get("value") or ""), "src": "hint", "text": _short(b.get("text")), "by": h.get("by") or "user"})
    # 3. 엔진 묶음의 라벨이 아닌 괄호 줄 — 헤딩의 엄격한 꼴 · 지금 구성의 기관 이름. 같은 구분의 엔진 항목 **안**의 줄이면 판독만이 아니다(inGroup — Fable 반례: 단계 행 묶음 안 「[1단계 목표]」)
    keys = sorted({o["key"] for o in F.orgs_of(values) if o["key"]}, key=len, reverse=True) if values else []
    scope, owner = {}, {}
    for g in groups:
        for it in g["items"]:
            for x in [*(it.get("scope") or ()), *([it["label"]] if it.get("label") else [])]:
                scope.setdefault(x, set()).add(g["dim"])
    for c in idx.values():
        if c.get("type") is None and "blocks" in c:
            for p in core._paras(c):
                owner.setdefault(p["id"], c["id"])
    extra = []
    for b in idx.values():
        if b.get("type") != "paragraph":
            continue
        letter = bracket_of(b.get("text"))
        if not letter or b["id"] in labels:
            continue
        basis = DT.value_basis(letter)
        k = name_key(letter, keys) if not basis and (b.get("text") or "").strip() == letter.strip() else None   # 이름 라벨은 줄이 괄호 글뿐일 때만(「[한국선급] 시험 성적서 …」 는 아님 — Fable 반례)
        if basis:
            ev = {"dim": _dim_of(basis), "value": "", "src": "pattern", "text": letter.strip(), "basis": basis}
        elif k:
            ev = {"dim": core.ORG, "value": k, "src": "name", "text": letter.strip(), "basis": "기관"}
        else:
            continue
        if ev["dim"] in scope.get(b["id"], set()) | scope.get(owner.get(b["id"]), set()):
            ev["inGroup"] = True
        put(b["id"], ev)
        extra.append({"para": b["id"], **ev})
    # 4. 표 안 귀속(편집 구역의 판독 — 귀속 값이 있을 때만)
    best, inside, cell_ev, tables, cells, table_of = {}, {}, {}, {}, {}, {}
    if values:
        best, inside = Z._memberships(groups, values, keys, Z.old_keys(prior, keys))
        for b in blocks:
            if b.get("type") == "table" and not b.get("captionOf") and b.get("id") is not None:
                whole, per = Z._table_read(b, keys, values["stages"], inside.get(b["id"], ()))
                if whole:
                    cell_ev[b["id"]] = whole
                    tables[b["id"]] = _plain_ev(whole)
                for cid, e in per.items():
                    table_of[cid] = b["id"]
                    cell_ev[cid] = e
                    cells[cid] = _plain_ev(e)
                    cell_paras[cid] = paras_of(cid)
                if whole:
                    for c in b.get("cells") or ():
                        cell_paras.setdefault(c["id"], paras_of(c["id"]))
                        table_of[c["id"]] = b["id"]
    n_lab = sum(1 for rows in labels.values() if rows)
    counts = {"groups": len(groups), "labels": n_lab, "engine": sum(1 for rows in labels.values() if any(r["src"] == "engine" for r in rows)),
              "hint": sum(1 for rows in labels.values() if any(r["src"] == "hint" for r in rows)),
              "pattern": sum(1 for x in extra if x["src"] == "pattern"), "name": sum(1 for x in extra if x["src"] == "name"),
              "tables": len(set(tables) | set(table_of.values())), "cells": len(cells)}
    return {"version": VERSION, "labels": labels, "extra": extra, "tables": tables, "cells": cells, "cellParas": cell_paras, "cellTable": table_of, "counts": counts,
            "_groups": groups, "_best": best, "_inside": inside, "_cellEv": cell_ev, "_values": values}


def _dim_of(basis):
    """헤딩의 구분 기준 이름(「단계-차년도」 …) → 엔진의 구분 키."""
    return next((d for d, n in BASIS.items() if n == basis), "other")


def _plain_ev(e):
    """표 안 판독의 근거(튜플) → JSON 꼴 {org?: {kind, key, why}, year?, yearClash?}."""
    out = {}
    if "org" in e:
        kind, key, why = e["org"]
        out["org"] = {"kind": kind, "key": key, **({"why": why} if why else {})}
    for k in ("year", "yearClash"):
        if k in e:
            out[k] = e[k]
    return out


def _short(text, n=40):
    t = re.sub(r"\s+", " ", text or "").strip()
    return t if len(t) <= n else t[:n - 1] + "…"


# ---- 헤딩 추출이 쓰는 꼴(spec_헤딩_추출 ② §13 「구분 기준 판독」) ------------------------------------------------------------

def pin(result, key=None, at=None):
    """판독 결과 → 헤딩 실행에 고정해 결과(graph.json)에 남길 최소 근거 {version, key, at, labels{para: [{dim, src, text?, value?}]}}(밑줄 키 · 표 안 귀속 뺌)."""
    if not result:
        return None
    labels = {pid: [{k: r[k] for k in ("dim", "src", "text", "value", "basis") if r.get(k) not in (None, "")} for r in rows] for pid, rows in (result.get("labels") or {}).items() if rows}
    return {"version": result.get("version", VERSION), "key": key, "at": at, "labels": labels}


def node_basis(nd, pinned):
    """헤딩 후보 노드 하나 → (판독이 확인한 구분 기준 이름 | None, 엇갈림인가, 이름 후보인가). 그 줄(괄호 줄은 레터, 그 밖은 레터 + 글) **자체**가 근거의 구분을 말할 때만 확인한다 —
    한 문단에 두 줄(「[기관A]」 · 「[1차년도 목표]」)이 있어도 문단의 근거가 다른 줄로 번지지 않게(astra P1). 추가한 자리(hint)는 그 문단을 사람이 고른 것이라 괄호 줄이면 글을 보지 않는다.
    이름 라벨(src name — 「[한국선급]」)은 확인으로 치지 않고 후보로만(Fable 협의 — 기술 동향 절의 「[한국선급]」·「[DNV]」 형제처럼 과제 기관 이름이 기관 자리가 아닌 곳이 있다: LLM A 가 본다)."""
    rows = ((pinned or {}).get("labels") or {}).get(nd.get("para")) or ()
    if not rows:
        return None, False, False
    label = nd.get("kind") == "label"
    line = (nd.get("letter") or "") if label else f"{nd.get('letter') or ''} {nd.get('text') or ''}"
    own = core._key(core.NOTE.sub("", line))
    said, cand = set(), False
    for r in rows:
        name = BASIS.get(r.get("dim"))
        if name is None:
            continue
        if r["src"] == "hint":
            if label or own:
                said.add(name)
        elif r["src"] == "engine":
            if own and own[0] == r["dim"]:
                said.add(name)
        elif r["src"] == "pattern":
            b = DT.value_basis(nd.get("letter")) if label else ""
            if b and b == r.get("basis"):
                said.add(name)
        elif r["src"] == "name":
            cand = cand or (label and bool(r.get("text")) and DT.label_shape(nd.get("letter")) == DT.label_shape(r["text"]))
    if len(said) > 1:
        return None, True, cand
    return (said.pop() if said else None), False, cand


def type_bases(nodes, pinned):
    """유형마다 판독 → {유형 id: {basis | None, confirmed, total, conflict, names, kind}} — basis 는 그 유형의 줄 **모두**가 같은 구분 기준으로 확인됐을 때만(일부만이면 None — 유형 전체로 번지지 않게).
    names = 줄 글이 지금 구성의 기관 이름뿐인 줄 수(후보 — LLM A 에 보낸다)."""
    out = {}
    for nd in nodes:
        t = out.setdefault(nd["type"], {"basis": None, "confirmed": 0, "total": 0, "conflict": 0, "names": 0, "kind": nd.get("kind"), "_seen": set()})
        t["total"] += 1
        b, clash, cand = node_basis(nd, pinned)
        t["names"] += bool(cand)
        if clash:
            t["conflict"] += 1
        elif b:
            t["confirmed"] += 1
            t["_seen"].add(b)
    for t in out.values():
        seen = t.pop("_seen")
        if t["total"] and t["confirmed"] == t["total"] and len(seen) == 1:
            t["basis"] = next(iter(seen))
    return out

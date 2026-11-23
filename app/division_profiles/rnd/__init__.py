"""국가R&D 프로파일(KEIT 연구개발계획서·KEIT 보고서 서식) — spec_구분_기준 ② §0 「프로파일」·§9.
공개 계약(엔진·서버가 쓰는 것): ID·VERSION·NAME · form_of(blocks) · supported(form) · norm_values(v) · levels_of(blocks) ·
candidates(blocks, levels, values, rebuild, skip, hints) · apply(doc, values, …) · read_values(blocks, levels) · dimensions(values) ·
members(blocks, levels, values, hints)(문서 표시·추가한 자리, ② §11) · hint_read(text) · value_text(dim, v) · pending(groups)(값과 아직 안 맞는 묶음, ② §16).
핵심은 `core.py`(FMM divisions.py 사본). 정책 상수·정규식의 분리(detect/render/values)는 후속(② §9 — 지금은 한 파일)."""
import re

from app import headings
from app.division_profiles import _structure as structure
from app.division_profiles.rnd import core
from app.division_profiles.rnd.core import (EXTRA, FORM, FORMS, PERIOD, apply, find, form_of, is_report, norm_values,  # noqa: F401
                                            org_name, org_names, period_fill, preview, read_values, stage_year, targets)

ID = "rnd"
VERSION = 9   # 정책이 바뀌면 올린다 — 계획(plan)에 고정돼 반영 직전 비교(② §3). 2 = 역할 칸 행 묶음(② §12, 2026-11-10) · 3 = 이름 든 라벨·외 기관 절(② §15, 같은 날)
#               4 = 책임자 절 제목의 기관 이름 · 번호 잇기(② §16, 같은 날) · 5 = 간접비 표의 기관 블록(계획서 8-3 도) · 보고서의 차년도 범위 — 전체·당해·다음 연도(② §18, 2026-11-11)
#               6 = 반영이 넣은 이름·연도(앞서 반영한 값 prior) — 이름·당해 차년도를 바꾼 값으로 다시 반영 · 이름 칸 행 묶음(② §19, 2026-11-11)
#               7 = 서명 줄 맞춤 — 기관 이름을 넣은 뒤 「(직인)」 이 세로로 한 줄에 서게 빈칸 수를 조정(② §20, 2026-11-12)
#               8 = 서명 줄에 기관 이름을 넣지 않음 — 줄만 기관 수만큼, 앞서 넣은 이름 괄호는 뺌(② §20, 같은 날 사용자 「여기 기관은 안들어 가는거 같아」)
#               9 = 「N단계 (해당 시 작성)」 단계 자리 — 단계가 하나인 과제면 항목째 지움 · 하나만 남은 행도 묶음(② §26, 2026-11-23 사용자 「단계로 된 경우만 작성하도록 되어 있는데」)
NAME = "국가R&D 연구개발계획서·연차보고서(KEIT 서식)"
SUPPORTED = {FORM, "연차보고서"}   # 연구개발계획서(일반형, ② §10) + 연차보고서(KEIT 서식, ② §17 — 2026-11-11). 단계·최종보고서는 판정만 되고 지원 안 함(잰 서식 없음)
DIM_NAME = core.DIM_NAME | {PERIOD: "사업기간"}
KIND_NAME = {"paragraph": "문단 묶음", "rows": "표 행", "cols": "표 열", "list": "목록 행", "date": "날짜"}
DROP_LINES, DROP_CHARS = 6, 80


def supported(form):
    return form in SUPPORTED


def levels_of(blocks):
    """{블록 id: 헤딩 레벨 H} — 절 제목 경계(core._last_end 등)·표 제목 사슬에 쓴다. FMM 은 헤딩·앵커 분석(structure.analyze)의 levels 였고
    여기선 `headings.levels`(앞머리 꼴 추출, spec_hwpx_웹편집 ② §7)의 "levels"."""
    return headings.levels(blocks)["levels"]


def _short(text, n=DROP_CHARS):
    t = re.sub(r"\s+", " ", text or "").strip()
    return t if len(t) <= n else t[:n] + "…"


def _item_texts(idx, it):
    """항목(roots)에 든 글 있는 문단 — 지워질 내용 미리보기(② §5)."""
    out = []
    for root in it.get("roots") or ():
        b = idx.get(root)
        if b is None:
            continue
        for p in core._paras(b):
            if (p.get("text") or "").strip():
                out.append(_short(p["text"]))
            if len(out) >= DROP_LINES:
                return out
    return out


def candidates(blocks, levels, values, rebuild=True, skip=(), hints=None, prior=None):
    """후보 자리 목록(② §2 「후보 자리」) = core.spot 요약 + 항목(라벨 id·글) + 지워질 항목의 글(drop) + 사본 수(copies).
    skip 에 든 key 는 excluded. 사업기간이 있으면 날짜 자리 하나(kind date). hints = 추가한 자리 문단 id 들(② §11).
    prior = 앞서 이 문서에 반영한 값들(② §19 — core.find 에 그대로)."""
    groups = core.find(blocks, levels, values, rebuild=rebuild, hints=hints, prior=prior)
    work = [g for g in groups if g["plan"] and not g["plan"]["done"] and not g["plan"].get("blocked") and g["key"] not in skip]
    idx = structure.index_blocks(blocks)
    out = []
    for g in groups:
        sp = core.spot(g, work)
        plan = g["plan"] or {}
        items = g["items"]
        sp["items"] = [{"label": it.get("label") or (it["roots"][0] if it.get("roots") else None), "text": _short(it.get("labelText"), 40)}
                       for it in items]
        sp["drop"] = [{"label": items[i].get("label"), "text": _short(items[i].get("labelText"), 40), "texts": _item_texts(idx, items[i])}
                      for i in plan.get("drop") or () if i < len(items)]
        sp["copies"] = plan.get("copies", 0)
        sp["template"] = items[plan["template"]].get("label") if plan and "template" in plan and plan["template"] < len(items) else None
        out.append(sp)
    fill = core.period_fill(blocks, values, core.is_report(core.form_of(blocks)))
    if fill:
        sp = core._period_spot(fill)
        sp.update(items=[], drop=[], copies=0, template=None)
        out.append(sp)
    return out


ROLE_NAME = {"lead": "주관", "joint": "공동", "outside": "외", "overseas": "국외", "entrust": "위탁"}


def value_text(dim, v):
    """엔진 값 → 화면 글(「1단계」「2차년도」「1단계-2차년도」「세부1」「주관」「공동2」「N차년도」) — 문서 표시·추가한 자리(② §11)."""
    if v is None:
        return ""
    if dim == core.STAGE:
        return f"{v}단계"
    if dim == core.YEAR:
        return f"{v}차년도"
    if dim == core.STAGE_YEAR and isinstance(v, (tuple, list)) and len(v) == 2:
        return f"{v[0]}단계-{v[1]}차년도"
    if dim == core.SUB:
        return f"세부{v}"
    if isinstance(v, (tuple, list)) and len(v) == 2 and isinstance(v[0], str):
        role, k = v
        name = ROLE_NAME.get(role, role)
        return name if k in (None, 0) else f"{name}{k}"
    if isinstance(v, (tuple, list)):
        return "-".join(str(x) for x in v)
    return str(v)


def hint_read(text):
    """추가한 자리 문단의 글에서 읽은 구분·값 — {"dim", "dimName", "value"(글)} | None(값 낱말 없음 → 표시만)."""
    h = core.hint_info(text)
    return {"dim": h["dim"], "dimName": DIM_NAME.get(h["dim"], h["dim"]), "value": value_text(h["dim"], h["value"])} if h else None


def members(blocks, levels, values, hints=None, prior=None):
    """문서 표시 자료(② §11) — 계획 없이 find 만: 묶음마다 항목 안 **문단 id 전부**(scope 의 문단, 문서 순) + 추가한 자리(hint) 행.
    hints = [{id, para, dim, value, …}]. hint 행에 text(문단 글)·exists·read(글에서 읽은 구분·값)·engine(엔진 묶음의 라벨이 됐는지)을 붙인다."""
    hints = list(hints or ())
    groups = core.find(blocks, levels, values, hints=[h["para"] for h in hints], prior=prior)
    idx = structure.index_blocks(blocks)
    order = {pid: i for i, pid in enumerate(idx)}
    label_ids, out = set(), []
    for g in groups:
        items = []
        for it in g["items"]:
            paras = sorted((x for x in it.get("scope") or () if (idx.get(x) or {}).get("type") == "paragraph"), key=order.get)
            lab = idx.get(it.get("label")) if it.get("label") else None
            lab_paras = [it["label"]] if lab is not None and lab.get("type") == "paragraph" else [x["id"] for x in core._paras(lab)] if lab is not None else []   # 라벨이 칸이면 그 칸의 문단(화면의 라벨 띠 — 2026-11-18 astra P2)
            items.append({"label": it.get("label"), "labelParas": lab_paras, "text": _short(it.get("labelText"), 40), "value": value_text(g["dim"], it.get("value")), "paras": paras})
            if it.get("label"):
                label_ids.add(it["label"])
        kind = "list" if g.get("list") else g["kind"]
        out.append({"key": g["key"], "dim": g["dim"], "dimName": DIM_NAME.get(g["dim"], g["dim"]), "kind": kind, "kindName": KIND_NAME.get(kind, kind),
                    "where": {"table": g["table"], "cell": g["container"]}, "count": len(g["items"]), "done": bool((g["plan"] or {}).get("done")),
                    "irregular": bool(g.get("irregular")), "hinted": bool(g.get("hinted")), "items": items})
    rows = []
    for h in hints:
        b = idx.get(h.get("para"))
        para = b is not None and b.get("type") == "paragraph"
        rows.append({**h, "text": _short(b.get("text"), 60) if para else "", "exists": para, "read": hint_read(b.get("text")) if para else None,
                     "dimName": DIM_NAME.get(h.get("dim"), h.get("dim")), "engine": h.get("para") in label_ids})
    return {"groups": out, "hints": rows}


def pending(groups):
    """find 결과에서 **구분 값과 아직 안 맞는 묶음**(계획하면 「맞춤」 이 될 것 — 계획이 있고 끝나지 않았고 막히지 않음) 요약(② §16 「검토에 보이게」):
    [{key, dim, dimName, kind, kindName, labels(처음 3), count, target}]. 그대로 두는 묶음(차례 어김·값 없음·병합 칸)은 안 든다."""
    out = []
    for g in groups:
        plan = g.get("plan")
        if not plan or plan["done"] or plan.get("blocked"):
            continue
        kind = "list" if g.get("list") else g["kind"]
        out.append({"key": g["key"], "dim": g["dim"], "dimName": DIM_NAME.get(g["dim"], g["dim"]), "kind": kind, "kindName": KIND_NAME.get(kind, kind),
                    "labels": [_short(it.get("labelText"), 30) for it in g["items"][:3]], "count": len(g["items"]), "target": len(g["target"])})
    return out


def dimensions(values):
    """정리한 값(norm_values 꼴) → 구분 기준 파생 뷰(② §2 — id 는 자리 차례로 안정: s1 · s1y2 · lead · joint2 · outside1 …).
    차년도는 단계가 부모, 기관은 참여 역할(lead·joint·outside·overseas·entrust)과 속성(nonprofit), period·current 는 맥락."""
    stages, no = [], 0
    for s, n in enumerate(values["stages"], 1):
        years = []
        for y in range(1, n + 1):
            no += 1
            years.append({"id": f"s{s}y{y}", "label": f"{y}차년도", "no": no, "parent": f"s{s}"})
        stages.append({"id": f"s{s}", "label": f"{s}단계", "years": years})
    orgs = values["orgs"]
    np_, dm = orgs.get("nonprofit") or [], orgs.get("demand") or []   # demand = 수요기업으로 고른 공동(spec_구분_기준 ② §24 — 고른 것이 있을 때만 값에 있다)
    members = [{"id": "lead", "label": org_name(values, 0), "name": orgs["lead"], "role": "lead", "attrs": {"nonprofit": bool(np_[0]) if np_ else False}}]
    members += [{"id": f"joint{k}", "label": org_name(values, k), "name": nm, "role": "joint",
                 "attrs": {"nonprofit": bool(np_[k]) if k < len(np_) else False, **({"demand": True} if k < len(dm) and dm[k] else {})}} for k, nm in enumerate(orgs["joint"], 1)]
    for kind, name in EXTRA.items():
        members += [{"id": f"{kind}{k}", "label": nm or f"{name}{k}", "name": nm, "role": kind, "attrs": {}} for k, nm in enumerate(orgs.get(kind) or [], 1)]
    cur = values.get("current") or 1
    s, y = stage_year(values, cur)
    return {"stages": stages, "orgs": members, "subs": [{"id": f"sub{k}", "name": nm} for k, nm in enumerate(values.get("subs") or [], 1)],
            "period": values.get("period"), "current": {"no": cur, "id": f"s{s}y{y}"}}

"""테이블 매니저 — 표 하나의 「지금 판정」(spec_테이블매니저 ② §2 「지금 판정」). 순수 함수: 문서 · 세션 · 서버 · 3단계의 실행 상태를 모른다
(`app.server` · `heading_runs` 를 import 하지 않는다 — 부르는 쪽이 지금 문서의 표 레코드 · 끝난 3단계 결과 · 사람 지정을 인자로 준다 · 세션 잠금도 부르는 쪽).

2026-11-19 사용자 "일단 이걸 테이블메니저를 두고 테이블메니저가 관리하고 이걸 호출해서 하는건 어떻게 생각함?" → astra · Fable 합의(spec_테이블매니저 ①).

- **저장된 3단계 결과에서 다시 쓰는 것은 자동 역할과 띠뿐**이다. 칸의 글 · 문단 목록 · 개체 · 좌표 · 숫자는 늘 지금 레코드에서 읽고, 헤더 경로 · 표 의미 · 수식 · 집계는
  「자동 역할 + 지금의 사람 지정」 을 합친 **뒤에** 다시 계산한다. 저장된 결과 객체는 고치지 않는다.
  (전에는 표 서식 점검이 저장된 표를 통째로 다시 써서, 그 뒤 칸에 더 쓴 문단을 못 보고 「빈 값 표시 맞추기」 가 칸 글을 지웠다 — artifacts/table_manager_astra_2026-11-19/repro_style_stale.py.)
- 자동 역할(`auto` — 스크립트 초안, 또는 LLM 이 고친 역할)과 사람 지정을 따로 지닌다 — 지정을 풀면 자동 역할로 돌아간다.
- 그대로 다시 쓰는 조건은 `reusable`. 그 조건이 안 맞아도(판정 뒤에 칸에 값이 채워짐 · 줄이 지워짐 · 줄이 늘어남) **판정을 버리지 않는다** — 판정 때 있던 칸은 그 역할 그대로 이어 쓴다(`_carry` —
  2026-11-23 사용자 "LLM 판정이 되면 그게 유지되어야지": 전에는 그 표 전체를 오늘의 초안으로 돌려, 값이 들어온 음영 칸이 헤더로 다시 읽혔다). 이을 칸이 하나도 없을 때만 초안이다."""
from collections import Counter

from app import heading_calc as HC
from app import heading_tables as HT

USER_ROLES = ("rowhead", "colhead", "field")
_BAND_KEYS = ("id", "rows", "cols", "kind", "headerRows", "headerCols", "source", "note")


def _auto_of(cell):
    """저장된 칸의 자동 역할 — 사람 지정이 덮은 칸이면 덮기 전 역할(`auto`), 아니면 최종 역할. 사람 지정이 녹았는데 `auto` 가 없으면 None(가를 수 없다)."""
    if cell.get("auto") is not None:
        return cell["auto"]
    return None if cell.get("reason") == "사용자 지정" else cell.get("role")


def reusable(tb, stored, key, *, same_doc=False):
    """저장된 3단계 표(`stored`)의 자동 역할 · 띠를 지금 표(`tb` — 오늘의 초안이 얹힌 collect 꼴)에 다시 써도 되는가 → (bool, 까닭).
    key = 오늘의 `heading_tables.input_key`. same_doc = 그 결과가 지금 문서 차례의 것."""
    if not stored:
        return False, "3단계 결과에 이 표가 없음"
    then = {c.get("id") for c in stored.get("cells") or []}
    if then != {x["id"] for x in tb["cells"]}:
        return False, "표의 칸이 바뀜"
    if not stored.get("subtables"):
        return False, "저장된 띠가 없음"
    if any(_auto_of(c) is None for c in stored["cells"]):
        return False, "사람 지정이 섞인 옛 결과"
    if same_doc:
        return True, "문서가 그대로"
    if stored.get("inputKey") and stored["inputKey"] == key:
        return True, "이 표의 자료가 그대로"
    return False, "판정 뒤 이 표가 바뀜" if stored.get("inputKey") else "판정 뒤 문서가 바뀜(옛 결과)"


def _adopt(tb, stored):
    """저장된 자동 역할 · 띠를 지금 표에 얹는다 → 띠 목록(새 dict — 저장된 것을 고치지 않는다). 칸의 `draft` 는 오늘의 초안 그대로."""
    auto = {c["id"]: (_auto_of(c), c.get("reason")) for c in stored["cells"]}
    for x in tb["cells"]:
        role, reason = auto[x["id"]]
        x["role"] = role
        if reason and reason != "사용자 지정":
            x["reason"] = reason
    return [{k: (list(s[k]) if k in ("rows", "cols") else s[k]) for k in _BAND_KEYS if s.get(k) is not None} for s in stored["subtables"]]


def _partition(tb, bands):
    """띠들이 지금 표를 겹치지 않게 빠짐없이 나누나 — 모든 칸이 띠 하나에 통째로 든다(병합 칸을 가르지 않는다)."""
    for i, a in enumerate(bands):
        for b in bands[i + 1:]:
            if a["rows"][0] < b["rows"][1] and b["rows"][0] < a["rows"][1] and a["cols"][0] < b["cols"][1] and b["cols"][0] < a["cols"][1]:
                return False
    for x in tb["cells"]:
        home = [g for g in bands if g["rows"][0] <= x["row"] < g["rows"][1] and g["cols"][0] <= x["col"] < g["cols"][1]]
        if len(home) != 1 or x["row"] + x["rs"] > home[0]["rows"][1] or x["col"] + x["cs"] > home[0]["cols"][1]:
            return False
    return True


def _remap(tb, stored):
    """저장된 띠를 지금 표의 자리로 옮긴다 → 띠 목록 | None(옮길 수 없음 — 부르는 쪽이 오늘의 초안 띠를 쓴다).
    띠 = 판정 때 그 띠에 든 칸 가운데 **지금도 있는 칸**이 덮는 자리(줄이 지워져 위로 당겨진 것 · 줄이 끼어 밀린 것을 따라간다). 헤더 행 · 열 수 = 판정 때 헤더 행 · 열에 들었던 칸이
    지금 띠의 위 · 왼쪽 끝에서부터 잇달아 덮는 만큼. 판정 뒤에 생긴 칸(늘린 줄 · 열)은 바로 위 띠에(없으면 왼쪽 띠에) 넣는다 — 띠의 위쪽으로 끼어든 줄은 헤더 자리를 흔드니 옮기지 않는다(None)."""
    cur = {x["id"]: x for x in tb["cells"]}
    bands = []
    for s in stored.get("subtables") or ():
        try:
            (r0, r1), (c0, c1) = s["rows"], s["cols"]
            hr, hc = max(0, int(s.get("headerRows") or 0)), max(0, int(s.get("headerCols") or 0))
            mem = [c for c in stored["cells"] if r0 <= c["row"] < r1 and c0 <= c["col"] < c1 and c["id"] in cur]
        except (KeyError, TypeError, ValueError):
            return None
        if not mem:
            continue   # 그 띠의 칸이 다 없어졌다
        now = [cur[c["id"]] for c in mem]
        rows = [min(x["row"] for x in now), max(x["row"] + x["rs"] for x in now)]
        cols = [min(x["col"] for x in now), max(x["col"] + x["cs"] for x in now)]
        hrows, hcols = set(), set()
        for c in mem:
            x = cur[c["id"]]
            if c["row"] + c.get("rs", 1) <= r0 + hr:
                hrows.update(range(x["row"], x["row"] + x["rs"]))
            if c["col"] + c.get("cs", 1) <= c0 + hc:
                hcols.update(range(x["col"], x["col"] + x["cs"]))
        nhr = next(n for n in range(rows[1] - rows[0] + 1) if rows[0] + n not in hrows)
        nhc = next(n for n in range(cols[1] - cols[0] + 1) if cols[0] + n not in hcols)
        bands.append({**{k: s[k] for k in _BAND_KEYS if s.get(k) is not None}, "rows": rows, "cols": cols, "headerRows": nhr, "headerCols": nhc})
    if not bands:
        return None
    for x in sorted(tb["cells"], key=lambda c: (c["row"], c["col"])):   # 판정 뒤에 생긴 칸 — 이웃 띠에
        if any(g["rows"][0] <= x["row"] < g["rows"][1] and g["cols"][0] <= x["col"] < g["cols"][1] for g in bands):
            continue
        up = [g for g in bands if g["cols"][0] <= x["col"] and x["col"] + x["cs"] <= g["cols"][1] and g["rows"][1] <= x["row"]]
        left = [g for g in bands if g["rows"][0] <= x["row"] and x["row"] + x["rs"] <= g["rows"][1] and g["cols"][1] <= x["col"]]
        if up:
            max(up, key=lambda g: g["rows"][1])["rows"][1] = x["row"] + x["rs"]
        elif left:
            max(left, key=lambda g: g["cols"][1])["cols"][1] = x["col"] + x["cs"]
        else:
            return None
    return bands if _partition(tb, bands) else None


def _carry(tb, occ, draft_bands, stored):
    """판정 이어 쓰기(spec_테이블매니저 ② §2 「판정 이어 쓰기」 — 2026-11-23 사용자 「LLM 판정이 되면 그게 유지되어야지」): 판정 뒤에 표가 바뀌었어도(칸에 값이 채워짐 · 줄이 지워짐 · 줄이 늘어남)
    **판정 때 있던 칸은 그 자동 역할 그대로**다 → (띠 목록, {kept, new, gone, bands}) | None(이을 칸이 하나도 없음).
    띠는 저장된 띠를 지금 자리로 옮긴 것(`_remap`) — 못 옮기면 오늘의 초안 띠. 판정 뒤에 생긴 칸은 그 띠의 헤더 행 · 열 수로 정한 역할(옮긴 띠) 또는 오늘의 초안 역할(초안 띠)."""
    if not stored or not stored.get("cells"):
        return None
    auto = {c["id"]: (_auto_of(c), c.get("reason")) for c in stored["cells"] if c.get("id") is not None}
    kept = [x for x in tb["cells"] if auto.get(x["id"], (None, None))[0] in HT.ROLES]
    if not kept:
        return None
    bands = _remap(tb, stored) if stored.get("subtables") else None
    if bands is not None:
        for b in bands:
            HT.assign_roles(tb, occ, b)   # 자리로 정한 역할 — 판정 뒤에 생긴 칸의 몫(있던 칸은 바로 아래에서 덮는다)
    for x in kept:
        role, reason = auto[x["id"]]
        x["role"] = role
        if reason and reason != "사용자 지정":
            x["reason"] = reason
    if bands is not None and len(kept) < len(tb["cells"]):   # 판정 뒤에 생긴 줄 — 같은 띠 · 같은 열의 있던 칸들이 가진 역할을 따른다(늘린 줄은 그 열의 줄: 음영 · 글 꼴로 다시 읽지 않는다)
        had = {x["id"] for x in kept}
        for b in bands:
            body = [x for x in HT.cells_in(tb, b) if x["row"] >= b["rows"][0] + b["headerRows"]]
            by_col = {}
            for x in body:
                if x["id"] in had:
                    by_col.setdefault((x["col"], x["cs"]), Counter())[x["role"]] += 1
            for x in body:
                if x["id"] not in had and (x["col"], x["cs"]) in by_col:
                    x["role"] = by_col[(x["col"], x["cs"])].most_common(1)[0][0]
    now = {x["id"] for x in tb["cells"]}
    info = {"kept": len(kept), "new": len(tb["cells"]) - len(kept), "gone": sum(1 for i in auto if i not in now), "bands": "stored" if bands is not None else "draft"}
    return (bands if bands is not None else draft_bands), info


def carry_over(tb, occ, bs, stored, key, same_doc=False):
    """저장된 판정(`stored` — 끝난 3단계 결과의 그 표)을 지금 표(`tb` — 오늘의 초안이 얹힌 collect 꼴 · occ · bs = `heading_tables.draft` 의 것)에 얹는다
    → (띠 목록, how) | None(이을 것이 없음 — 표는 초안 그대로: 칸 역할을 건드리지 않고 돌려준다).
    how = {"mode": "same"}(입력이 그대로 — 자동 역할 · 띠를 그대로 다시 씀: `reusable`) | {"mode": "carried", "kept", "new", "gone", "bands"}(표가 바뀜 — 칸마다 이어 씀: `_carry`).
    key = 오늘의 `heading_tables.input_key`(초안을 지은 바로 뒤의 것). `judge` 와 3단계 실행(`heading_tables.build(prior=, carry=)` — spec_작업 ② §22 「구현 계약」 22-4)이 같이 쓴다:
    3단계가 스크립트로 다시 돌거나 LLM 이 답을 못 해도 앞 LLM 판정이 초안으로 돌아가지 않게. 저장된 결과는 고치지 않는다."""
    if reusable(tb, stored, key, same_doc=same_doc)[0]:
        return _adopt(tb, stored), {"mode": "same"}
    car = _carry(tb, occ, bs, stored)
    if car is None:
        return None
    bands, info = car
    return bands, {"mode": "carried", **info}


def _from_template(tb, template):
    """양식의 확정본(spec_테이블매니저 ② §10 「양식의 표 판정」)을 지금 표에 얹을 것 → (자리별 역할 {(행, 열): 역할}, 띠 목록) | None(이 표의 칸을 다 덮지 못함 · 꼴이 틀림 — 쓰지 않는다).
    확정본이 이 표의 구조와 맞는지는 부르는 쪽(`table_types.match`)이 본다 — 여기서는 모든 칸에 역할이 있고 모든 칸이 한 띠에 드는지만 다시 본다(표를 고치지 않는다)."""
    roles = {}
    try:
        for r, c, role in template.get("roles") or ():
            if role in HT.ROLES:
                roles[(int(r), int(c))] = role
        bands = [{k: (list(b[k]) if k in ("rows", "cols") else b[k]) for k in _BAND_KEYS if b.get(k) is not None} for b in template.get("bands") or ()]
        ok = bool(bands) and all(all(k in b for k in ("id", "rows", "cols", "kind", "headerRows", "headerCols")) for b in bands)
        ok = ok and all((x["row"], x["col"]) in roles and any(b["rows"][0] <= x["row"] < b["rows"][1] and b["cols"][0] <= x["col"] < b["cols"][1] for b in bands) for x in tb["cells"])
    except (TypeError, ValueError, AttributeError, KeyError, IndexError):
        return None
    return (roles, bands) if ok else None


def judge(stage1, tid, *, stored=None, user=None, same_doc=False, before=None, template=None):
    """표 tid 의 지금 판정 → {"table", "subs", "sem", "source", "reuse", "inputKey", "template"} | None(표가 아님 · 1칸 표).

    template = 이 표에 **맞는** 양식의 확정본(`table_types.match` 가 고른 것 — {id, rev, roles: [[행, 열, 역할]…](모든 칸), bands}) | None(spec_테이블매니저 ② §10 「양식의 표 판정」).
    주면 자동 역할 · 띠를 확정본에서 자리로 가져온다(source "template" — 3단계 결과 · 초안보다 먼저 · 사람의 헤더 지정은 그 위에). 확정본의 역할은 `user` 표시가 붙지 않는 따로 선 층이다.

    stage1 = 그 표의 **지금** 문단 레코드({"paras": […]} — `table_excel.records` 의 꼴). stored = 끝난 3단계 결과의 그 표(고치지 않는다) | None.
    user = **유효한** 사람 지정 {칸 id: rowhead | colhead | field} | None(`table_heads.check` 가 거른 것). same_doc = 그 결과가 지금 문서 차례의 것인가.
    before = 표 앞 문단 글(모르면 None — 저장된 것을 쓴다).
    table = collect 꼴의 새 표(칸마다 지금 글 · 문단 · draft · auto · role · user? · sub · 경로 · 뜻). source = "stage3"(저장된 자동 역할 · 띠를 다시 씀 — 그대로(`reusable`) 또는
    표가 바뀐 뒤 칸마다 이어 씀(`_carry` — reuse.why 「판정을 이어 씀 — …」)) | "draft"(저장된 판정이 없거나 이을 칸이 없음)."""
    tb = next((t for t in HT.collect(stage1) if t["id"] == tid), None)
    if tb is None:
        return None
    bs, occ = HT.draft(tb)
    key = HT.input_key(tb, occ, bs)
    got = _from_template(tb, template) if template else None
    if got is not None:   # 양식의 확정본 — 사람이 표 전체의 판정을 확정한 것(구조가 꼭 같은 표)
        roles, bs = got
        for x in tb["cells"]:
            x["role"] = roles[(x["row"], x["col"])]
        ok, why = False, "양식의 확정본을 씀"
    else:
        ok, why = reusable(tb, stored, key, same_doc=same_doc)   # 까닭 글(그대로 다시 씀 · 초안으로 남는 까닭)
        got2 = carry_over(tb, occ, bs, stored, key, same_doc=same_doc)   # 그대로 다시 쓰기 · 아니면 칸마다 이어 쓰기(판정 뒤에 표가 바뀜 — 버리지 않는다: 판정 때 있던 칸은 그 역할 그대로)
        if got2 is not None:
            bs, carried = got2
            if carried["mode"] == "carried":
                ok = True
                why = "판정을 이어 씀 — " + " · ".join(t for t in (f"판정 때 있던 칸 {carried['kept']}", f"그 뒤 생긴 칸 {carried['new']}" if carried["new"] else "",
                                                           f"없어진 칸 {carried['gone']}" if carried["gone"] else "") if t)
    for x in tb["cells"]:
        x["auto"] = x["role"]
        mine = (user or {}).get(x["id"])
        if mine in USER_ROLES:
            x["role"], x["user"], x["reason"] = mine, True, "사용자 지정"
        x["changed"] = x["role"] != x["draft"]
        x["sub"] = next((b["id"] for b in bs if b["rows"][0] <= x["row"] < b["rows"][1] and b["cols"][0] <= x["col"] < b["cols"][1]), None)
    subs = [HT.finish_band(tb, occ, b) for b in bs]
    sem = HC.annotate(tb, subs, None, before=before if before is not None else (stored or {}).get("before") or "")
    used = {"id": template.get("id"), "rev": template.get("rev")} if got is not None else None
    return {"table": tb, "subs": subs, "sem": sem, "source": "template" if used else "stage3" if ok else "draft", "reuse": {"ok": ok, "why": why}, "inputKey": key, "template": used}

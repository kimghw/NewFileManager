"""테이블 매니저 — 표 하나의 「지금 판정」(spec_테이블매니저 ② §2 「지금 판정」). 순수 함수: 문서 · 세션 · 서버 · 3단계의 실행 상태를 모른다
(`app.server` · `heading_runs` 를 import 하지 않는다 — 부르는 쪽이 지금 문서의 표 레코드 · 끝난 3단계 결과 · 사람 지정을 인자로 준다 · 세션 잠금도 부르는 쪽).

2026-11-19 사용자 "일단 이걸 테이블메니저를 두고 테이블메니저가 관리하고 이걸 호출해서 하는건 어떻게 생각함?" → astra · Fable 합의(spec_테이블매니저 ①).

- **저장된 3단계 결과에서 다시 쓰는 것은 자동 역할과 띠뿐**이다. 칸의 글 · 문단 목록 · 개체 · 좌표 · 숫자는 늘 지금 레코드에서 읽고, 헤더 경로 · 표 의미 · 수식 · 집계는
  「자동 역할 + 지금의 사람 지정」 을 합친 **뒤에** 다시 계산한다. 저장된 결과 객체는 고치지 않는다.
  (전에는 표 서식 점검이 저장된 표를 통째로 다시 써서, 그 뒤 칸에 더 쓴 문단을 못 보고 「빈 값 표시 맞추기」 가 칸 글을 지웠다 — artifacts/table_manager_astra_2026-11-19/repro_style_stale.py.)
- 자동 역할(`auto` — 스크립트 초안, 또는 LLM 이 고친 역할)과 사람 지정을 따로 지닌다 — 지정을 풀면 자동 역할로 돌아간다.
- 다시 쓰는 조건은 `reusable` — 아니면 그 표 전체를 오늘의 초안으로(칸마다 섞지 않는다)."""
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
    table = collect 꼴의 새 표(칸마다 지금 글 · 문단 · draft · auto · role · user? · sub · 경로 · 뜻). source = "stage3"(저장된 자동 역할 · 띠를 다시 씀) | "draft"."""
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
        ok, why = reusable(tb, stored, key, same_doc=same_doc)
        if ok:
            bs = _adopt(tb, stored)
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

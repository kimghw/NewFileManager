"""표의 키-값 추출 · 다른 표에 매핑 끝점(spec_테이블매니저 ② §7 「키-값 추출과 매핑」) — `GET …/tables/{tid}/kv` · `POST …/kv/plan` · `POST …/kv/apply` · `POST …/kv/recalc/plan` · `POST …/kv/recalc/apply` ·
매핑 규칙 `GET /api/table-maps` · `GET /api/table-maps/find` · `PUT /api/table-maps` · `DELETE /api/table-maps/{id}` · 꺼 둔 값 `GET /api/table-maps/offs` · `PUT /api/table-maps/offs`.
추출 · 계획은 `app/table_kv.py`(순수), 규칙의 저장은 `app/table_maps.py`, 화면은 `app/static/table_kv.js`(표 메뉴 → 2열 kind tblKv). LLM 을 부르지 않는다. hwpx 만.

- 칸 역할은 값을 쓰는 도구의 기본 역할(같은 사양서 ② §4): **스크립트 초안 + 유효한 사람 지정** — 두 표 모두 `table_manager.judge(…, stored=None, user=유효한 지정, template=양식의 확정본)`.
  **양식의 확정본**(spec_테이블매니저 ② §10 「양식의 표 판정」 — 사람이 그 양식의 표 전체 판정을 확정한 것 · 구조가 꼭 같은 표에만 맞는다)이 있으면 초안 대신 그것을 쓴다:
  값을 채운 표도 빈 양식 때와 같은 키가 나온다. 맞는 확정본은 `table_types_api.template_for(s, tb)` 가 준다(그 파일은 고치지 않는다 — 부르기만). 응답에 판정의 출처(`source` · `template{id, rev}`)를 싣고
  짝의 `sig` 에도 넣는다(확정본이 바뀌면 달라져 넣기가 건너뛴다).
  3단계 결과(LLM 이 고친 역할)는 쓰지 않는다. 보류된 지정(`table_heads.check`)은 쓰지 않고 응답의 `held` 에 싣는다 — 받을 표에 보류가 있으면 `apply` 는 409.
- `apply` 는 계획을 **다시** 세워, 지금도 `fill` 이고 화면이 본 `sig`(받을 칸 · 넣을 글 · 지금 글 · 원본 칸)와 같은 칸만 쓴다 — 계획을 본 뒤 달라진 칸은 건너뛴다(`skipped`).
  한 트랜잭션(`server._edit` — 실행 취소 1 · OWPML 지역 검사 · 기록 `tableKv`). 칸의 글을 쓰는 길은 표 채우기와 같다(`doc.set_text` — 칸의 문단 모양 그대로 · 칸 안에 표 · 그림이 있는 칸은 안 씀).
- 원본 표가 다른 문서(`from.doc`)의 것이면 그 문서가 서버에 열려 있어야 한다. **두 세션의 잠금을 겹쳐 잡지 않는다** — 원본은 제 잠금 안에서 추출까지만 읽고 놓은 뒤 받을 문서의 잠금에 들어간다
  (세션 잠금은 다시 들어갈 수 없는 잠금이다 — 같은 문서의 두 표는 받을 문서의 잠금 한 번 안에서 읽는다).
- **매핑 규칙**: 두 표의 **타입**(`table_kv.type_key` — 머리글 지문: 값을 채워도 안 바뀐다)의 짝(원본 타입 → 대상 타입)에 저장된 규칙 묶음을 `plan` · `apply` 가 **저절로** 쓴다
  (요청 `rules: false` 면 규칙 없이). 같은 타입끼리도 한 짝이다 — 타입이 같아도 키는 다를 수 있어(「1차년도 › 현금」 ↔ 「2차년도 › 현금」) 「같은 타입이면 규칙 없음」 으로 건너뛰지 않는다.
  규칙은 짝만 정한다 — 넣는 조건(빈 칸만 · 겹치면 안 덮음 · 수식 칸 제외 · 사람이 고른 칸만)은 같다. 규칙 끝점은 문서에 묶이지 않는다(서버 전체에 하나).
- **구분 기준으로 묶어 넣기**(다대일): `from` 이 목록(`[{table, doc?, value?}]`)이거나 `group: {basis}` 가 있으면 여러 원본을 그 기준의 값마다 묶어 그 값 머리 아래 칸에 넣는 계획
  (`table_kv.plan_grouped`). 원본이 어느 값의 것인지는 사람이 준 `value` 가 먼저고, 없으면 ① 편집 구역이 그 표에 준 귀속 ② 3단계 결과의 표 소속(낡았으면 건너뜀) ③ 표 앞 문단 글, 차례로 읽어 권한다
  (`table_kv.suggest` — 못 읽으면 값 없음: 그 원본은 넣지 않는다). 편집 구역은 다시 계산하지 않는다 — `table_kinds_api._zone_of`(= `zones_api.read` + `zones.label_of`)를 **세션 잠금 밖에서** 받아 둔다
  (`zones_api.read` 가 그 잠금을 제가 잡는다). `from` 이 표 하나(`{table}`)이고 `group` · `mode` 가 없으면 전과 같은 1대1 이다(응답 꼴도 그대로).
- **더해서 넣기**(다대일 — 셀 값 합산): `mode: "sum"` 이면 원본 표 여럿의 같은 키 칸의 수를 더해 넣는 계획(`table_kv.plan_sum`) — `group` 과 함께 쓰지 않는다(400).
- **구분 기준의 값 고르기**: 값을 받을 표(나눠 넣기에서는 원본 표)에 기준(`bases`)이 있으면 계획의 짝마다 `div: {기준: 그 칸이 놓인 값 머리의 키 조각}` 를 싣고 `bases` 의 값마다 짝 수 · 넣을 수 있는 수를 싣는다
  (`table_kv.with_div`). 고르기는 화면의 일이다 — 넣기 요청은 고른 칸만 보내므로 넣기는 그대로다.
  **꺼 둔 값을 기억한다**: 화면이 표지를 켜고 끌 때마다 그 기준이 있는 표의 타입으로 저장하고(`PUT /api/table-maps/offs` → `table_maps.put_offs`) 계획을 그릴 때 읽는다(`GET /api/table-maps/offs?type=`).
  계획 · 넣기 끝점은 저장된 것을 보지 않는다(끄는 것은 화면의 고름일 뿐 — 서버가 짝을 빼지 않는다).
- **나눠 넣기**(일대다 — `POST …/kv/split/plan` · `…/kv/split/apply`): `{tid}` = 원본 표(기준의 값 머리가 있는 표), `to` = 받을 표 여럿. 받을 표가 어느 값의 것인지는 묶어 넣기와 같은 차례로 권한다.
  받을 표 여럿에 **한 트랜잭션**으로 쓴다(`server._edit` 의 닿는 요소 = 받을 표들 — 실행 취소 1 · 기록 `tableKv`). 받을 표 가운데 보류된 헤더 지정이 있는 표가 하나라도 있으면 409.
- **칸마다 넣는 방식**: 규칙 묶음의 `ops`(받을 칸의 키 · 머리글 조각마다 fill · add · sub · replace)를 계획이 읽어 짝마다 `op` · 넣을 글 · `check` 를 정한다(`table_kv._ops` · `_put`).
  넣을 수 있는 짝은 방식이 무엇이든 status `fill` 이라 `apply` 는 그대로다(다시 계획해 `sig` 가 같은 칸만 — `sig` 에 방식이 든다: 더한 뒤 다시 반영하면 지금 글이 달라져 건너뛴다).
- **계산 칸 다시 계산**(`POST …/kv/recalc/plan` · `…/kv/recalc/apply`): 그 표의 수식 칸(합계 · 소계 · 코드 식 · 비율)을 수식대로 다시 셈해 넣는다(`table_kv.recalc` — 여러 겹은 한 번의 계획에서).
  역할은 다른 넣기와 같다(`_judge` — 확정본 > 초안 + 유효한 지정). 한 트랜잭션(실행 취소 1 · 기록 `tableKv`). 보류된 헤더 지정이 있으면 409. 다른 칸에 기대는 값(`needs`)은 그 칸들을 같이 넣을 때만 쓴다."""
from fastapi import APIRouter, Body, HTTPException, Query

from app import heading_tables, table_excel, table_heads, table_kv, table_manager, table_maps

router = APIRouter()
CELLS_MAX = 2000   # 한 번에 넣는 칸 수
SOURCES_MAX = 12   # 한 번에 가져오는 원본 표 수
LABEL_MAX = 60     # 원본 표의 보일 이름(표 앞 문단 글)
FROM_HELP = "from 은 {table: 원본 표 id, doc?: 원본 문서 id} 또는 그 목록([{table, doc?, value?}] — 1~%d개)" % SOURCES_MAX


def _hwpx(s, what="키-값 추출 · 매핑"):
    if getattr(s, "fmt", None) != "hwpx":
        raise HTTPException(400, f"{what}은 지금 hwpx 문서만 됩니다")


def _live(s, tid, what="표"):
    """문서에 붙어 있는 표 요소 — 없으면 404."""
    el = s.doc._ids.get(tid) if isinstance(tid, str) else None
    if el is None or not str(el.tag).endswith("}tbl") or not s.doc._attached(el):
        raise HTTPException(404, f"{what}가 지금 문서에 없습니다 — 다시 고르세요")
    return el


def _judge(s, tid, what="표"):
    """세션 잠금 안에서 — 표 tid 의 지금 판정 → (`table_manager.judge` 의 결과(table · subs · sem · source · template), 보류된 헤더 지정 [{cell, role, why}], 칸 안에 표 · 그림이 있는 칸 id 집합, 1단계 레코드).
    역할 = 스크립트 초안(그 표에 맞는 양식의 확정본이 있으면 그것 — source "template" · template{id, rev}) + 유효한 사람 지정(`table_manager.judge(stored=None)`). 404 표 없음 · 400 1칸 표 · 너무 큰 표."""
    from app import table_types_api   # 양식의 표 판정 — 맞는 확정본 읽기(파일 읽기뿐 · 세션 잠금 안에서 불러도 된다)
    _live(s, tid, what)
    stage1 = table_excel.records(s.doc, tid, doc_key=getattr(s, "doc_key", None))
    tb = next((t for t in heading_tables.collect(stage1 or {"paras": []}) if t["id"] == tid), None)
    if tb is None:
        raise HTTPException(400, f"{what}의 칸 역할을 읽지 못했습니다(1칸 표 · 상자)")
    if len(tb["cells"]) > table_excel.MAX_CELLS:
        raise HTTPException(400, f"{what}가 너무 큽니다(칸 {len(tb['cells'])} > {table_excel.MAX_CELLS})")
    valid, held = table_heads.check(s.id, tid, tb)
    j = table_manager.judge(stage1, tid, stored=None, user=valid or None, template=table_types_api.template_for(s, tb))
    block = s.doc.table_block(tid) or {}
    objs = {c["id"] for c in block.get("cells") or () if any(b.get("type") != "paragraph" for b in c.get("blocks") or ())}  # 칸 안 표 · 그림 — 글을 쓰지 않는 칸(표 채우기 반영과 같은 판정)
    return j, held, objs, stage1


def _read(s, tid, what="표"):
    """세션 잠금 안에서 — 표 tid 의 키-값과 보류된 헤더 지정 → (추출 `table_kv.extract` + type(표 타입) · bases(구분 기준의 값 머리) · source · template · rows · cols, 보류 [{cell, role, why}]). 판정은 `_judge`."""
    j, held, objs, stage1 = _judge(s, tid, what)
    ex = table_kv.extract(j["table"], lines=table_kv.cell_lines(stage1, j["table"]), objs=objs)
    return {**ex, "type": table_kv.type_key(j["table"], ex), "bases": table_kv.bases(j["table"]), "source": j["source"], "template": j.get("template"),
            "rows": j["table"]["rows"], "cols": j["table"]["cols"]}, held


def _sources(body, doc_id, tid):
    """요청의 원본 → (원본 목록 [{table, doc: 다른 문서 id | None, value: 사람이 고른 값(값 머리의 키 조각) | None}], many).
    many = `from` 이 목록이거나 `group` 이 있다(여러 원본 · 묶어 넣기의 응답 꼴) — 아니면 전과 같은 1대1. 같은 문서의 같은 표 · 같은 원본 두 번은 400."""
    f = body.get("from") if isinstance(body, dict) else None
    many = isinstance(f, list) or (isinstance(body, dict) and (body.get("group") is not None or body.get("mode") is not None))
    raw = f if isinstance(f, list) else [f]
    if not raw or len(raw) > SOURCES_MAX:
        raise HTTPException(400, FROM_HELP)
    out, seen = [], set()
    for x in raw:
        doc, value = (x.get("doc"), x.get("value")) if isinstance(x, dict) else (None, None)
        if not isinstance(x, dict) or not isinstance(x.get("table"), str) or not x["table"] or (doc is not None and (not isinstance(doc, str) or not doc)) \
                or (value is not None and (not isinstance(value, str) or not value)):
            raise HTTPException(400, FROM_HELP)
        other = doc if doc and doc != doc_id else None
        if other is None and x["table"] == tid:
            raise HTTPException(400, "원본 표와 값을 받을 표가 같습니다 — 다른 표를 고르세요")
        if (x["table"], other) in seen:
            raise HTTPException(400, "같은 원본 표가 두 번 들어 있습니다")
        seen.add((x["table"], other))
        out.append({"table": x["table"], "doc": other, "value": value})
    return out, many


def _group(body):
    """요청의 기준 → {basis, on?, level?} | None(기준 없이). 꼴이 틀리면 400."""
    g = body.get("group") if isinstance(body, dict) else None
    if g is None:
        return None
    level = g.get("level") if isinstance(g, dict) else None
    if not isinstance(g, dict) or g.get("basis") not in table_kv.BASES or g.get("on") not in (None, "row", "col") or (level is not None and (not isinstance(level, int) or isinstance(level, bool))):
        raise HTTPException(400, f"group 은 {{basis: {'·'.join(table_kv.BASES)} 가운데 하나, on?: row | col, level?: 정수}}")
    return g


def _mode(body, grp):
    """요청의 방식 → "sum"(값을 더해서 넣기) | None. 모르는 값 · `group` 과 함께면 400(묶음마다 더하는 것은 없다)."""
    m = body.get("mode") if isinstance(body, dict) else None
    if m is None:
        return None
    if m != "sum":
        raise HTTPException(400, "mode 는 sum(값을 더해서 넣기)뿐입니다")
    if grp is not None:
        raise HTTPException(400, "mode: sum 은 group 과 함께 쓰지 않습니다 — 기준으로 묶은 뒤 더하는 것은 아직 없습니다")
    return m


def _base(dst, g, what="값을 받을 표"):
    """그 표의 기준 가운데 요청이 가리키는 것(`table_kv.bases` 의 한 항목) — 없으면 400(값 머리가 둘 이상인 곳이 없다)."""
    hit = [b for b in dst["bases"] if b["basis"] == g["basis"] and g.get("on") in (None, b["on"]) and g.get("level") in (None, b["level"])]
    if not hit:
        raise HTTPException(400, f"{what}에 그 기준의 머리글(값이 둘 이상)이 없습니다 — 기준을 다시 고르세요")
    return max(hit, key=lambda b: sum(v["cells"] for v in b["values"]))   # 같은 기준이 두 곳에 있으면 칸이 많은 쪽(먼저 온 것이 이긴다)


def _hints(s, tid, zone_of, t3):
    """세션 잠금 안에서 — 원본 표가 어느 값의 것인지 읽을 거리(`table_kv.suggest`): 편집 구역의 귀속(zone_of — 잠금 밖에서 받아 둔 읽기 함수) · 3단계 결과의 표 소속 구분 줄(지금 문서 차례의 결과일 때만) · 표 앞 문단 글."""
    owner = None
    if isinstance(t3, dict) and (t3.get("meta") or {}).get("rev") == s.rev:
        t = next((x for x in t3.get("tables") or () if isinstance(x, dict) and x.get("id") == tid), None)
        owner = (((t or {}).get("owner") or {}).get("division") or {}).get("text")
    return {"zone": zone_of(tid) if zone_of else None, "owner": owner if isinstance(owner, str) else None, "before": table_excel.context(s.doc, tid)["before"]}


def _source(s, x, hint, zone_of, t3):
    """세션 잠금 안에서 — 원본 표 하나를 읽어 x 에 얹는다(추출 · 보일 이름 · 값을 권할 거리)."""
    x["ex"] = _read(s, x["table"], "원본 표")[0]
    before = table_excel.context(s.doc, x["table"])["before"]
    x["label"] = before[-1][:LABEL_MAX] if before else ""
    x["hints"] = _hints(s, x["table"], zone_of, t3) if hint and x["value"] is None else None


def _prep(doc_id, srcs, hint):
    """받을 문서의 잠금에 들어가기 **전에** 하는 일 → (받을 문서의 세션, 편집 구역 읽기 함수 | None, 3단계 결과 | None).
    ① 다른 문서의 원본은 그 문서의 잠금 안에서 추출까지 읽고 놓는다(받을 문서의 잠금과 겹쳐 잡지 않는다 — 그 문서가 서버에 열려 있지 않으면 400).
    ② 값을 권해야 하면(hint — 묶어 넣기이고 사람이 값을 안 준 원본이 있음) 편집 구역 읽기 함수와 3단계 결과를 받아 둔다 — `zones_api.read` 는 세션 잠금을 제가 잡으므로 잠금 밖인 여기서 부른다."""
    from app import heading_runs, server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    from app.table_kinds_api import _zone_of   # 편집 구역의 귀속을 읽는 함수(zones_api.read + zones.label_of) — 여기서 다시 계산하지 않는다

    def aids(ss, need):
        return (_zone_of(ss), heading_runs.tables(ss)) if need else (None, None)
    for x in srcs:
        if not x["doc"]:
            continue
        ss = server.DOCS.get(x["doc"])
        if ss is None:
            raise HTTPException(400, "원본 문서가 서버에 열려 있지 않습니다 — 그 문서를 먼저 여세요")
        zone_of, t3 = aids(ss, hint and x["value"] is None)
        with ss.lock:
            _hwpx(ss, "원본 문서의 키-값 추출")
            _source(ss, x, hint, zone_of, t3)
    s = server._sess(doc_id)
    return (s, *aids(s, hint and any(not x["doc"] and x["value"] is None for x in srcs)))


def _rules_of(body, src, dst):
    """이 짝(원본 타입 → 대상 타입)에 저장된 규칙 묶음 | None — 타입이 같든 다르든 그 짝의 묶음이 있으면 쓴다. 요청에 `rules: false` 면 쓰지 않는다."""
    if isinstance(body, dict) and body.get("rules") is False:
        return None
    return table_maps.find(src["type"], dst["type"])


def _mark(ex):
    """그 표의 판정이 어디서 왔는가 — 짝의 도장(`table_kv.sig`)에 넣는다: 초안 | 양식의 확정본과 그 판(확정본이 바뀌면 도장이 달라진다)."""
    t = ex.get("template") or {}
    return [ex.get("source"), t.get("id"), t.get("rev")]


def _judged(ex):
    """응답에 싣는 판정의 출처 {source, template}."""
    return {"source": ex.get("source"), "template": ex.get("template")}


def _brief(rules, used):
    return {"id": rules["id"], "name": rules["name"], "alias": len(rules["alias"]), "pairs": len(rules["pairs"]), "ops": len(rules.get("ops") or ()), "used": used} if rules else None


def _plan(s, tid, srcs, many, grp, body, zone_of, t3, mode=None):
    """세션 잠금 안에서 — 받을 표와 같은 문서의 원본을 읽고 계획을 세운다 → (계획 응답(짝마다 sig), 보류, 쓰인 규칙 묶음 id 목록, 기준 | None).
    many 가 아니면 전과 같은 1대1(`table_kv.plan`), many 면 `table_kv.plan_grouped`(기준이 없으면 원본마다 키 그대로 · 두 원본이 같은 칸이면 겹침), mode 가 sum 이면 `table_kv.plan_sum`(같은 키 칸의 수를 더함)."""
    dst, held = _read(s, tid, "값을 받을 표")
    for x in srcs:
        if x.get("ex") is None:
            _source(s, x, grp is not None, zone_of, t3)
    bundles = [_rules_of(body, x["ex"], dst) for x in srcs]
    if not many:
        x, rules = srcs[0], bundles[0]
        p = table_kv.plan(x["ex"], dst, rules)
        out = {**p, "from": {"table": x["table"], **({"doc": x["doc"]} if x["doc"] else {}), "rows": x["ex"]["rows"], "cols": x["ex"]["cols"], "counts": x["ex"]["counts"], "dups": x["ex"]["dups"], **_judged(x["ex"])},
               "types": {"from": x["ex"]["type"], "to": dst["type"], "same": x["ex"]["type"] == dst["type"]}, "rules": _brief(rules, p["counts"]["byRule"])}
        base = None
    elif mode == "sum":
        p = table_kv.plan_sum([{"ex": x["ex"], "table": x["table"], **({"doc": x["doc"]} if x["doc"] else {})} for x in srcs], dst, bundles)
        for rec, x, rules in zip(p["sources"], srcs, bundles):
            rec.update(label=x.get("label") or "", rows=x["ex"]["rows"], cols=x["ex"]["cols"], dups=x["ex"]["dups"], type=x["ex"]["type"], same=x["ex"]["type"] == dst["type"],
                       rules=_brief(rules, rec["counts"]["byRule"]), **_judged(x["ex"]))
        out = {**p, "mode": "sum", "group": None}
        base = None
    else:
        base = _base(dst, grp) if grp is not None else None
        parts = {v["part"] for v in base["values"]} if base else set()
        picked = []
        for x in srcs:
            value, by = (x["value"], "user") if base is not None and x["value"] is not None else (None, None)
            if value is not None and value not in parts:
                raise HTTPException(400, f"원본 표 {x['table']} 에 고른 값 「{value}」 의 머리글이 값을 받을 표에 없습니다 — 값을 다시 고르세요")
            if base is not None and value is None:
                got = table_kv.suggest(base, x.get("hints") or {})
                value, by = got["value"], got["by"]
            picked.append((value, by))
        p = table_kv.plan_grouped([{"ex": x["ex"], "value": v, "table": x["table"], **({"doc": x["doc"]} if x["doc"] else {})} for x, (v, _) in zip(srcs, picked)], dst, base, bundles)
        for rec, x, (_, by), rules in zip(p["sources"], srcs, picked, bundles):
            rec.update(label=x.get("label") or "", by=by, rows=x["ex"]["rows"], cols=x["ex"]["cols"], dups=x["ex"]["dups"], type=x["ex"]["type"], same=x["ex"]["type"] == dst["type"],
                       rules=_brief(rules, rec["counts"]["byRule"]), **_judged(x["ex"]))
        out = {**p, "group": base}
    marks = [_mark(x["ex"]) for x in srcs]
    for pair in out["pairs"]:   # 도장에 두 표의 판정 출처를 — 1대1 은 그 원본, 여러 원본은 그 짝의 원본, 더해서 넣기는 모든 원본
        pair["sig"] = table_kv.sig(pair, [_mark(dst), marks if mode == "sum" else marks[pair["src"]] if many else marks[0]])
    bases = table_kv.with_div(dst["bases"], out["pairs"])   # 구분 기준의 값 고르기 — 짝마다 div · 값마다 짝 수 · 넣을 수 있는 수
    return {**out, "table": tid, "type": dst["type"], "bases": bases, **_judged(dst)}, held, [b["id"] for b in bundles if b], base


@router.get("/api/docs/{doc_id}/tables/{tid}/kv")
def table_kv_get(doc_id: str, tid: str):
    """표 하나의 키-값(`table_kv.extract`) — {table, type(표 타입), bases(구분 기준의 값 머리 — 묶어 넣을 수 있는 기준), source("template" = 양식의 확정본으로 판정 | "draft"), template({id, rev} | null), rows, cols, items[{cell, ref, sub, row, col, key, label, text, empty, num, calc, obj?}],
    dups, counts, rev, held}. 문서는 안 바뀐다. hwpx 만 · 표 없음 404 · 1칸 표 400."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        _hwpx(s)
        ex, held = _read(s, tid)
        return {**ex, "rev": s.rev, "held": held}


@router.post("/api/docs/{doc_id}/tables/{tid}/kv/plan")
def table_kv_plan(doc_id: str, tid: str, body: dict = Body(...)):
    """원본 표의 값을 이 표(`tid` — 값을 받을 표)에 넣는 계획. 문서는 안 바뀐다.
    **1대1** — {from: {table: 원본 표 id, doc?: 원본 문서 id}, rules?: false(매핑 규칙 없이)} → `table_kv.plan` 결과(pairs · unmatched · counts) + 짝마다 `sig`
      + {table, type, bases, from{table, doc?, rows, cols, counts, dups}, types{from, to, same}, rules{id, name, alias, pairs, used} | null, rev, held}.
    **여러 원본 · 구분 기준으로 묶어 넣기** — {from: [{table, doc?, value?: 그 원본이 어느 값의 것인가(값 머리의 키 조각)}](1~12), group?: {basis: year | org | stage | period, on?, level?}, rules?: false}
      → `table_kv.plan_grouped` 결과(pairs(짝마다 from{table, cell} · group · value · src) · unmatched · counts · groups · sources) + 짝마다 `sig`
      + {table, type, bases, group(받을 표의 그 기준 {basis, on, level, values} | null), sources[{table, doc?, label, value, valueLabel, by: user | zone | owner | text | null, why?, rows, cols, type, same, rules, counts}], rev, held}.
      `value` 를 안 준 원본은 편집 구역 → 표의 소속 → 표 앞 글 차례로 읽어 권한다(못 읽으면 값 없음 — 넣지 않는다). `group` 이 없으면 기준 없이(원본마다 키 그대로 · 두 원본이 같은 칸이면 겹침).
    **더해서 넣기** — {from: [{table, doc?}], mode: "sum"} → `table_kv.plan_sum` 결과(pairs(짝마다 parts[{table, cell, text, num}] · sum · text(넣을 글) · missing? · check?) · unmatched · counts · sources) + 짝마다 `sig`
      + {table, type, bases, mode: "sum", group: null, sources[{table, doc?, label, rows, cols, type, same, rules, counts}], rev, held}. `group` 과 함께 쓰면 400.
    두 표의 타입 짝(같은 타입끼리도)에 규칙 묶음이 저장돼 있으면 저절로 쓴다(`rules.used` = 규칙으로 맺은 짝 수).
    어느 꼴이든: 응답에 받을 표의 판정 출처 `source` · `template`(원본 쪽은 `from` · `sources[]` 에), 짝마다 `div: {기준: 그 받을 칸이 놓인 값 머리의 키 조각}`, `bases` 의 값마다 `pairs`(짝 수) · `fill`(넣을 수 있는 수)
    — 화면이 기준의 값을 빼거나 일부만 골라 넣는 데 쓴다(넣기 요청은 고른 칸만 보낸다).
    400 from · group 꼴 · 원본과 받을 표가 같은 표 · 받을 표에 그 기준이 없음 · 고른 값의 머리글이 없음 · 원본 문서가 안 열려 있음 · docx · 1칸 표 / 404 표 없음."""
    srcs, many = _sources(body, doc_id, tid)
    grp = _group(body)
    mode = _mode(body, grp)
    s, zone_of, t3 = _prep(doc_id, srcs, grp is not None)   # 다른 문서의 원본 · 편집 구역 읽기 함수 — 받을 문서의 잠금에 들어가기 전에
    with s.lock:
        _hwpx(s)
        out, held, _ids, _base_ = _plan(s, tid, srcs, many, grp, body, zone_of, t3, mode)
        return {**out, "rev": s.rev, "held": held}


@router.post("/api/docs/{doc_id}/tables/{tid}/kv/apply")
def table_kv_apply(doc_id: str, tid: str, body: dict = Body(...)):
    """고른 칸에 원본 표의 값을 넣는다 — {from: 계획 때와 같은 꼴({table, doc?} | [{table, doc?, value?}]), group?, cells: [받을 칸 id…](1~2,000), rev: 계획을 본 문서 차례, sigs: {받을 칸 id: sig}, rules?: false}.
    계획을 **다시** 세워(그 짝의 매핑 규칙 · 기준 · 원본의 값 포함 — 계획 때와 같은 길) 지금도 `fill` 이고 `sig` 가 같은 칸만 쓴다(그 밖은 `skipped` — 겹침 · 수식 칸 · 달라짐).
    한 트랜잭션(`server._edit`: 실행 취소 1개 · OWPML 지역 검사 · 기록 `tableKv`). 응답 = 구조 편집 응답 + `mapped {table, from, done[칸 id…], skipped[{cell, why}], rules, (group)}`
    (1대1: from{table, doc?} · rules: 묶음 id | null / 여러 원본: from[{table, doc?, value}] · rules: [묶음 id…] · group{basis, on, level} | null / 더해서 넣기: from[{table, doc?}] · mode: "sum").
    400 from · group · cells · rev · sigs 꼴 · 원본 문서가 안 열려 있음 · docx / 404 표 없음 / 409 rev 가 지금과 다름 · 받을 표에 보류된 헤더 지정 · 넣을 칸이 하나도 안 남음."""
    from app import server
    srcs, many = _sources(body, doc_id, tid)
    grp = _group(body)
    mode = _mode(body, grp)
    cells, rev, sigs = body.get("cells"), body.get("rev"), body.get("sigs")
    if not isinstance(cells, list) or not cells or len(cells) > CELLS_MAX or not all(isinstance(c, str) and c for c in cells) or len(set(cells)) != len(cells):
        raise HTTPException(400, f"cells 는 값을 받을 칸 id 1~{CELLS_MAX}개(겹치지 않게)")
    if not isinstance(rev, int) or isinstance(rev, bool):
        raise HTTPException(400, "rev(계획을 본 문서 차례)가 필요합니다")
    if not isinstance(sigs, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in sigs.items()):
        raise HTTPException(400, "sigs 는 {값을 받을 칸 id: 계획의 sig}")
    _s, zone_of, t3 = _prep(doc_id, srcs, grp is not None)   # 다른 문서의 원본 — 제 잠금 안에서 추출까지만 읽고 놓은 뒤 아래 트랜잭션(받을 문서의 잠금)에 들어간다 · 편집 구역 읽기 함수도 잠금 밖에서
    done = {}

    def make(s):
        _hwpx(s)
        tbl = _live(s, tid, "값을 받을 표")
        if rev != s.rev:
            raise HTTPException(409, "계획을 본 뒤 문서가 바뀌었습니다 — 「다른 표에서 가져오기」 의 계획을 다시 받으세요")
        p, held, ids, base = _plan(s, tid, srcs, many, grp, body, zone_of, t3, mode)
        if held:
            raise HTTPException(409, f"헤더 지정 {len(held)}칸이 지금 표와 맞지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요")
        by = {}
        for pair in p["pairs"]:
            by.setdefault(pair["to"], pair)   # 두 원본이 같은 칸에 걸린 짝은 모두 겹침이라 어느 것이든 같다
        todo, skipped = [], []
        for c in cells:
            pair = by.get(c)
            if pair is None:
                skipped.append({"cell": c, "why": "짝이 없습니다 — 계획을 다시 받으세요"})
            elif pair["status"] != "fill":
                skipped.append({"cell": c, "why": pair.get("why") or "이미 같은 글입니다"})
            elif sigs.get(c) != pair["sig"]:
                skipped.append({"cell": c, "why": "달라짐 — 계획을 다시 받으세요"})
            else:
                todo.append(pair)
        if not todo:
            raise HTTPException(409, "넣을 칸이 없습니다 — 계획을 본 뒤 표나 매핑 규칙이 바뀌었습니다. 「다른 표에서 가져오기」 의 계획을 다시 받으세요")
        if many:
            echo = {"from": [{"table": r["table"], **({"doc": r["doc"]} if r.get("doc") else {}), **({} if mode else {"value": r["value"]})} for r in p["sources"]], "rules": ids,
                    "group": {k: base[k] for k in ("basis", "on", "level")} if base else None, **({"mode": mode} if mode else {})}
        else:
            echo = {"from": {"table": srcs[0]["table"], **({"doc": srcs[0]["doc"]} if srcs[0]["doc"] else {})}, "rules": ids[0] if ids else None}

        def run():
            for pair in todo:
                s.doc.set_text(pair["to"], pair["text"].replace("\r", ""))  # 칸 안 표가 있으면 ValueError → 400(트랜잭션이 되돌림) — 그런 칸은 계획에서 이미 fill 이 아니다
            done.update(table=tid, done=[pair["to"] for pair in todo], skipped=skipped, **echo)
            return {"hosts": [tbl], "anchor": tid, "focus": None,
                    "log": {"table": tid, "src": [x["table"] for x in srcs] if many else srcs[0]["table"], "srcDoc": [x["doc"] for x in srcs] if many else srcs[0]["doc"],
                            "cells": len(todo), "skipped": len(skipped), "rules": echo["rules"], **({"group": base["basis"] if base else None} if many else {}), **({"mode": mode} if mode else {})}}
        return [tbl], run
    req = {"table": tid, "from": [{"table": x["table"], "doc": x["doc"], "value": x["value"]} for x in srcs] if many else {"table": srcs[0]["table"], "doc": srcs[0]["doc"]},
           "cells": len(cells), **({"group": grp} if grp is not None else {}), **({"mode": mode} if mode else {})}
    out = server._edit(doc_id, make, "tableKv", req)
    if isinstance(out, dict):
        out["mapped"] = done
    return out


# ---- 계산 칸 다시 계산(같은 사양서 ② §7 「키-값 추출과 매핑」 의 「계산 칸 다시 계산」): 그 표의 수식 칸을 수식대로 다시 셈해 넣는다 ---------------------------------------

def _recalc(s, tid):
    """세션 잠금 안에서 — 표 tid 의 계산 칸을 다시 셈한 계획 → (응답(`table_kv.recalc` + 칸마다 label · sig · 표의 크기 · 판정의 출처), 보류 [{cell, role, why}])."""
    j, held, objs, _stage1 = _judge(s, tid)
    ex = table_kv.extract(j["table"], objs=objs)   # 줄에 보일 키 글 · 글을 쓰지 않는 칸(칸 안 표 · 그림)
    labels = {i["cell"]: i["label"] for i in ex["items"]}
    r = table_kv.recalc(j["table"], j["sem"], j["subs"], objs={i["cell"] for i in ex["items"] if i.get("obj")} | objs)
    mark = [j["source"], (j.get("template") or {}).get("id"), (j.get("template") or {}).get("rev")]
    for it in r["items"]:
        it["label"] = labels.get(it["cell"], "")
        it["sig"] = table_kv.recalc_sig(it, mark)
    return {**r, "table": tid, "rows": j["table"]["rows"], "cols": j["table"]["cols"], "source": j["source"], "template": j.get("template")}, held


@router.post("/api/docs/{doc_id}/tables/{tid}/kv/recalc/plan")
def table_kv_recalc_plan(doc_id: str, tid: str):
    """이 표의 계산 칸(수식이 걸린 칸 — 합계 · 소계 · 코드 식 · 비율)을 수식대로 다시 셈한 계획 — 문서는 안 바뀐다.
    → {table, items[{cell, ref, label, formula, note, now, value, text, status, why?, check?, needs?, stale?, both?, sig}], counts{missing, mismatch, ok, incomplete, conflict}, passes, more, rows, cols, source, template, rev, held}.
    status: missing(비어 있고 계산됨 — 넣을 수 있음) · mismatch(지금 값과 다름 — check) · ok · incomplete(셈할 칸에 빈 것 — 안 넣음) · conflict(두 수식이 다른 값 — 안 넣음 · both).
    hwpx 만 · 표 없음 404 · 1칸 표 400."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        _hwpx(s, "계산 칸 다시 계산")
        out, held = _recalc(s, tid)
        return {**out, "rev": s.rev, "held": held}


@router.post("/api/docs/{doc_id}/tables/{tid}/kv/recalc/apply")
def table_kv_recalc_apply(doc_id: str, tid: str, body: dict = Body(...)):
    """고른 계산 칸에 다시 셈한 값을 넣는다 — {cells: [칸 id…](1~2,000), rev: 계획을 본 문서 차례, sigs: {칸 id: sig}}.
    계획을 **다시** 세워 지금도 넣을 수 있고(missing · mismatch) `sig` 가 같은 칸만 쓴다(그 밖은 `skipped`). 다른 채울 칸에 기대는 값(`needs` — 소계에 기대는 합계)은 그 칸들을 **같이** 넣을 때만 쓴다.
    지금 값이 계산과 다른 칸에 기대는 값(`stale` — 그 칸의 지금 값으로 셈한 것)은 **그 칸을 이번 `cells` 에 같이 보내면 건너뛴다**(`skipped` — 넣은 뒤 다시 읽은 계획에 새 값으로 나온다).
    한 트랜잭션(`server._edit`: 실행 취소 1개 · OWPML 지역 검사 · 기록 `tableKv`). 응답 = 구조 편집 응답 + `mapped {table, recalc: true, done[칸 id…], skipped[{cell, why}]}`.
    400 cells · rev · sigs 꼴 · docx / 404 표 없음 / 409 rev 가 지금과 다름 · 보류된 헤더 지정 · 넣을 칸이 하나도 안 남음."""
    from app import server
    cells, rev, sigs = body.get("cells"), body.get("rev"), body.get("sigs")
    if not isinstance(cells, list) or not cells or len(cells) > CELLS_MAX or not all(isinstance(c, str) and c for c in cells) or len(set(cells)) != len(cells):
        raise HTTPException(400, f"cells 는 다시 계산할 칸 id 1~{CELLS_MAX}개(겹치지 않게)")
    if not isinstance(rev, int) or isinstance(rev, bool):
        raise HTTPException(400, "rev(계획을 본 문서 차례)가 필요합니다")
    if not isinstance(sigs, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in sigs.items()):
        raise HTTPException(400, "sigs 는 {칸 id: 계획의 sig}")
    done = {}

    def make(s):
        _hwpx(s, "계산 칸 다시 계산")
        tbl = _live(s, tid)
        if rev != s.rev:
            raise HTTPException(409, "계획을 본 뒤 문서가 바뀌었습니다 — 「계산 칸 다시 계산」 의 계획을 다시 받으세요")
        p, held = _recalc(s, tid)
        if held:
            raise HTTPException(409, f"헤더 지정 {len(held)}칸이 지금 표와 맞지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요")
        by = {it["cell"]: it for it in p["items"]}
        todo, skipped, asked = [], [], set(cells)
        for c in cells:
            it = by.get(c)
            if it is None:
                skipped.append({"cell": c, "why": "계산 칸이 아닙니다 — 계획을 다시 받으세요"})
            elif it["status"] not in ("missing", "mismatch"):
                skipped.append({"cell": c, "why": it.get("why") or "이미 계산한 값과 같습니다"})
            elif sigs.get(c) != it["sig"]:
                skipped.append({"cell": c, "why": "달라짐 — 계획을 다시 받으세요"})
            elif asked & set(it.get("stale") or ()):   # 이 값은 그 칸의 지금 값으로 셈한 것 — 그 칸을 이번에 같이 고치면 옛 값으로 셈한 것이 들어간다
                skipped.append({"cell": c, "why": f"{' · '.join(by[x]['ref'] for x in it['stale'] if x in asked and x in by)} 를 고친 뒤 다시 계산합니다 — 넣은 뒤 다시 읽은 계획에 새 값으로 나옵니다"})
            else:
                todo.append(it)
        while True:   # 기대는 칸(needs)이 같이 들어가지 않는 값은 쓰지 않는다 — 빠진 칸에 기대던 것도 차례로 빠진다
            ok = {it["cell"] for it in todo}
            lone = [it for it in todo if any(n not in ok for n in it.get("needs") or ())]
            if not lone:
                break
            skipped += [{"cell": it["cell"], "why": f"이 값이 기대는 칸({' · '.join(by[n]['ref'] for n in it['needs'] if n not in ok and n in by)})을 같이 넣어야 합니다"} for it in lone]
            todo = [it for it in todo if it not in lone]
        if not todo:
            raise HTTPException(409, "넣을 칸이 없습니다 — 계획을 본 뒤 표가 바뀌었습니다. 「계산 칸 다시 계산」 의 계획을 다시 받으세요")

        def run():
            for it in todo:
                s.doc.set_text(it["cell"], it["text"])
            done.update(table=tid, recalc=True, done=[it["cell"] for it in todo], skipped=skipped)
            return {"hosts": [tbl], "anchor": tid, "focus": None, "log": {"table": tid, "recalc": True, "cells": len(todo), "skipped": len(skipped)}}
        return [tbl], run
    out = server._edit(doc_id, make, "tableKv", {"table": tid, "recalc": True, "cells": len(cells)})
    if isinstance(out, dict):
        out["mapped"] = done
    return out


# ---- 나눠 넣기(일대다 — 같은 사양서 ② §7 의 「나눠 넣기」): {tid} = 원본 표(기준의 값 머리가 있는 표) · to = 받을 표 여럿 -----------------------------------------------

def _targets(body, tid):
    """요청의 받을 표 → [{table, value: 사람이 고른 값(값 머리의 키 조각) | None}](1~12 · 원본 표 자신 · 같은 표 두 번은 400). 받을 표는 같은 문서의 표다(한 트랜잭션으로 쓴다)."""
    to = body.get("to") if isinstance(body, dict) else None
    if not isinstance(to, list) or not to or len(to) > SOURCES_MAX:
        raise HTTPException(400, f"to 는 받을 표의 목록([{{table, value?}}] — 1~{SOURCES_MAX}개)")
    out, seen = [], set()
    for x in to:
        value = x.get("value") if isinstance(x, dict) else None
        if not isinstance(x, dict) or not isinstance(x.get("table"), str) or not x["table"] or (value is not None and (not isinstance(value, str) or not value)):
            raise HTTPException(400, f"to 는 받을 표의 목록([{{table, value?}}] — 1~{SOURCES_MAX}개)")
        if x["table"] == tid:
            raise HTTPException(400, "원본 표와 값을 받을 표가 같습니다 — 다른 표를 고르세요")
        if x["table"] in seen:
            raise HTTPException(400, "같은 받을 표가 두 번 들어 있습니다")
        seen.add(x["table"])
        out.append({"table": x["table"], "value": value})
    return out


def _split_aids(doc_id, tgts):
    """잠금에 들어가기 전에 — (세션, 편집 구역 읽기 함수 | None, 3단계 결과 | None). 사람이 값을 안 준 받을 표가 있을 때만 읽는다(`zones_api.read` 는 세션 잠금을 제가 잡는다)."""
    from app import heading_runs, server
    from app.table_kinds_api import _zone_of
    s = server._sess(doc_id)
    need = any(t["value"] is None for t in tgts)
    return s, (_zone_of(s) if need else None), (heading_runs.tables(s) if need else None)


def _split(s, tid, tgts, grp, body, zone_of, t3):
    """세션 잠금 안에서 — 원본 표와 받을 표들을 읽고 나눠 넣는 계획을 세운다 → (계획 응답(짝마다 sig), 보류 [{table, cell, role, why}], 쓰인 규칙 묶음 id 목록, 기준)."""
    src, _held = _read(s, tid, "원본 표")
    base = _base(src, grp, "원본 표")
    parts = {v["part"] for v in base["values"]}
    held, picked = [], []
    for t in tgts:
        x = {"table": t["table"], "value": t["value"]}
        ex, h = _read(s, t["table"], "값을 받을 표")
        held += [{"table": t["table"], **i} for i in h]
        before = table_excel.context(s.doc, t["table"])["before"]
        value, by = (t["value"], "user") if t["value"] is not None else (None, None)
        if value is not None and value not in parts:
            raise HTTPException(400, f"받을 표 {t['table']} 에 고른 값 「{value}」 의 머리글이 원본 표에 없습니다 — 값을 다시 고르세요")
        if value is None:
            got = table_kv.suggest(base, _hints(s, t["table"], zone_of, t3))
            value, by = got["value"], got["by"]
        picked.append({**x, "ex": ex, "value": value, "by": by, "label": before[-1][:LABEL_MAX] if before else ""})
    bundles = [_rules_of(body, src, x["ex"]) for x in picked]
    p = table_kv.plan_split(src, [{"ex": x["ex"], "value": x["value"], "table": x["table"]} for x in picked], base, bundles)
    for rec, x, rules in zip(p["targets"], picked, bundles):
        rec.update(label=x["label"], by=x["by"], rows=x["ex"]["rows"], cols=x["ex"]["cols"], type=x["ex"]["type"], same=x["ex"]["type"] == src["type"], rules=_brief(rules, rec["counts"]["byRule"]),
                   **_judged(x["ex"]))
    for pair in p["pairs"]:
        pair["sig"] = table_kv.sig(pair, [_mark(picked[pair["tgt"]]["ex"]), _mark(src)])
    keys = {i["cell"]: i["key"] for i in src["items"]}
    bases = table_kv.with_div(src["bases"], p["pairs"], lambda pair: keys[pair["from"]])   # 값 고르기 — 나눠 넣기에서는 원본 표의 기준 · 원본 칸의 키로
    return {**p, "table": tid, "type": src["type"], "bases": bases, "group": base, **_judged(src)}, held, [b["id"] for b in bundles if b], base


@router.post("/api/docs/{doc_id}/tables/{tid}/kv/split/plan")
def table_kv_split_plan(doc_id: str, tid: str, body: dict = Body(...)):
    """이 표(`tid` — 원본: 구분 기준의 값 머리가 있는 표)의 값을 받을 표 여럿에 나눠 넣는 계획 — {to: [{table, value?: 그 받을 표가 어느 값의 것인가}](1~12), group: {basis, on?, level?}, rules?: false}. 문서는 안 바뀐다.
    → `table_kv.plan_split` 결과(pairs(짝마다 from: 원본 칸 · to{table, cell} · ref · group · value · tgt) · unmatched · counts · groups(받을 표마다) · targets) + 짝마다 `sig`
      + {table, type, bases, group(원본 표의 그 기준), targets[{table, label, value, valueLabel, by: user | zone | owner | text | null, why?, rows, cols, type, same, rules, counts}], rev, held[{table, cell, role, why}]}.
    `value` 를 안 준 받을 표는 편집 구역 → 표의 소속 → 표 앞 글 차례로 읽어 권한다(못 읽으면 값 없음 — 그 표에는 넣지 않는다).
    400 to · group 꼴 · 원본 표에 그 기준이 없음 · 고른 값의 머리글이 없음 · docx · 1칸 표 / 404 표 없음."""
    tgts = _targets(body, tid)
    grp = _group(body)
    if grp is None:
        raise HTTPException(400, "group({basis}) 이 필요합니다 — 원본 표의 어느 기준으로 나눌지")
    s, zone_of, t3 = _split_aids(doc_id, tgts)
    with s.lock:
        _hwpx(s)
        out, held, _ids, _base_ = _split(s, tid, tgts, grp, body, zone_of, t3)
        return {**out, "rev": s.rev, "held": held}


@router.post("/api/docs/{doc_id}/tables/{tid}/kv/split/apply")
def table_kv_split_apply(doc_id: str, tid: str, body: dict = Body(...)):
    """고른 칸에 이 표(원본)의 값을 나눠 넣는다 — {to: [{table, value?}], group, cells: [{table: 받을 표 id, cell: 받을 칸 id}…](1~2,000), rev, sigs: {받을 칸 id: sig}, rules?: false}.
    계획을 **다시** 세워 지금도 `fill` 이고 `sig` 가 같은 칸만 쓴다(그 밖은 `skipped`). 받을 표 여럿에 **한 트랜잭션**(`server._edit`: 실행 취소 1개 · OWPML 지역 검사 · 기록 `tableKv`).
    응답 = 구조 편집 응답 + `mapped {table(원본), split: true, to[{table, value}], group{basis, on, level}, done[{table, cell}], skipped[{table, cell, why}], rules[묶음 id…]}`.
    400 to · group · cells · rev · sigs 꼴 · docx / 404 표 없음 / 409 rev 가 지금과 다름 · 받을 표 가운데 보류된 헤더 지정이 있는 표가 있음 · 넣을 칸이 하나도 안 남음."""
    from app import server
    tgts = _targets(body, tid)
    grp = _group(body)
    if grp is None:
        raise HTTPException(400, "group({basis}) 이 필요합니다 — 원본 표의 어느 기준으로 나눌지")
    cells, rev, sigs = body.get("cells"), body.get("rev"), body.get("sigs")
    if not isinstance(cells, list) or not cells or len(cells) > CELLS_MAX or not all(isinstance(c, dict) and isinstance(c.get("table"), str) and isinstance(c.get("cell"), str) and c["table"] and c["cell"] for c in cells) \
            or len({(c["table"], c["cell"]) for c in cells}) != len(cells):
        raise HTTPException(400, f"cells 는 [{{table: 받을 표 id, cell: 받을 칸 id}}] 1~{CELLS_MAX}개(겹치지 않게)")
    if not isinstance(rev, int) or isinstance(rev, bool):
        raise HTTPException(400, "rev(계획을 본 문서 차례)가 필요합니다")
    if not isinstance(sigs, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in sigs.items()):
        raise HTTPException(400, "sigs 는 {값을 받을 칸 id: 계획의 sig}")
    _s, zone_of, t3 = _split_aids(doc_id, tgts)   # 편집 구역 읽기 함수는 잠금 밖에서
    done = {}

    def make(s):
        _hwpx(s)
        _live(s, tid, "원본 표")
        if rev != s.rev:
            raise HTTPException(409, "계획을 본 뒤 문서가 바뀌었습니다 — 「다른 표로 나눠 넣기」 의 계획을 다시 받으세요")
        p, held, ids, base = _split(s, tid, tgts, grp, body, zone_of, t3)
        if held:
            raise HTTPException(409, f"받을 표 {' · '.join(dict.fromkeys(h['table'] for h in held))} 의 헤더 지정 {len(held)}칸이 지금 표와 맞지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요")
        by = {(pair["to"]["table"], pair["to"]["cell"]): pair for pair in p["pairs"]}
        todo, skipped = [], []
        for c in cells:
            pair = by.get((c["table"], c["cell"]))
            if pair is None:
                skipped.append({"table": c["table"], "cell": c["cell"], "why": "짝이 없습니다 — 계획을 다시 받으세요"})
            elif pair["status"] != "fill":
                skipped.append({"table": c["table"], "cell": c["cell"], "why": pair.get("why") or "이미 같은 글입니다"})
            elif sigs.get(c["cell"]) != pair["sig"]:
                skipped.append({"table": c["table"], "cell": c["cell"], "why": "달라짐 — 계획을 다시 받으세요"})
            else:
                todo.append(pair)
        if not todo:
            raise HTTPException(409, "넣을 칸이 없습니다 — 계획을 본 뒤 표나 매핑 규칙이 바뀌었습니다. 「다른 표로 나눠 넣기」 의 계획을 다시 받으세요")
        tables = [*dict.fromkeys(pair["to"]["table"] for pair in todo)]
        tbls = [_live(s, t, "값을 받을 표") for t in tables]   # 닿는 요소 = 받을 표들(한 트랜잭션)

        def run():
            for pair in todo:
                s.doc.set_text(pair["to"]["cell"], pair["text"].replace("\r", ""))
            done.update(table=tid, split=True, to=[{"table": r["table"], "value": r["value"]} for r in p["targets"]], group={k: base[k] for k in ("basis", "on", "level")},
                        done=[dict(pair["to"]) for pair in todo], skipped=skipped, rules=ids)
            return {"hosts": tbls, "anchor": tables[0], "focus": None,
                    "log": {"table": tid, "split": tables, "group": base["basis"], "cells": len(todo), "skipped": len(skipped), "rules": ids}}
        return tbls, run
    out = server._edit(doc_id, make, "tableKv", {"table": tid, "to": tgts, "group": grp, "cells": len(cells)})
    if isinstance(out, dict):
        out["mapped"] = done
    return out


# ---- 매핑 규칙(같은 사양서 ② §7 「키-값 추출과 매핑」 — 「매핑 규칙」): 서버 전체에 하나 · 문서에 묶이지 않는다 ------------------------------------------------------

def _store(fn):
    """저장소를 고치는 일 — 저장 모듈의 오류를 상태 코드로: 400 꼴 · 404 없는 id · 409 판 다름 · 503 파일 손상 · 못 씀."""
    try:
        return fn()
    except table_maps.StaleVersion as e:
        raise HTTPException(409, str(e)) from e
    except table_maps.Broken as e:
        raise HTTPException(503, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, "그 매핑 규칙이 없습니다 — 이미 지워졌습니다") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"매핑 규칙을 저장하지 못했습니다: {e}") from e


@router.get("/api/table-maps")
def table_maps_list():
    """저장된 매핑 규칙 묶음 전부 — {maps: [{id, name, from{type, label}, to{type, label}, alias[], pairs[], version, updated}…]}(최근 고친 것부터)."""
    return {"maps": table_maps.list()}


@router.get("/api/table-maps/find")
def table_maps_find(from_: str = Query("", alias="from"), to: str = ""):
    """(원본 타입 `from` → 대상 타입 `to`) 짝의 묶음 | null(없음 — 방향이 있다: 거꾸로 짝은 다른 묶음 · 같은 타입끼리도 한 짝)."""
    return table_maps.find(from_, to)


@router.put("/api/table-maps")
def table_maps_put(body: dict = Body(...)):
    """규칙 묶음 만들기 · 고치기 — {id?, name?, from: {type, label}, to: {type, label}, alias: [{from, to}], pairs: [{from, to, fromLabel?, toLabel?}], version?} → 저장한 묶음.
    없으면 새로(그 짝의 묶음이 없고 id · version 을 안 줌), 있으면 기대 `version` 이 지금과 같을 때만(아니면 409 — 다시 읽을 것). 고칠 때 두 표의 타입은 안 바뀐다.
    400 꼴 / 404 없는 id / 409 판 다름 / 503 파일 손상 · 못 씀."""
    return _store(lambda: table_maps.put(body))


@router.delete("/api/table-maps/{map_id}")
def table_maps_delete(map_id: str):
    """규칙 묶음 지우기 → {deleted: id}. 404 없는 id."""
    return {"deleted": _store(lambda: table_maps.delete(map_id))["id"]}


# ---- 꺼 둔 값(같은 사양서 ② §7 「키-값 추출과 매핑」 의 「구분 기준의 값 고르기」 — 「꺼 둔 값을 기억한다」): 표 타입마다 · 문서에 묶이지 않는다 -------------------------------

def _off_type(v):
    if not isinstance(v, str) or not table_maps._TYPE.match(v):
        raise HTTPException(400, "type 은 표 타입(12자리 — `GET …/tables/{tid}/kv` 의 `type`)")
    return v


@router.get("/api/table-maps/offs")
def table_maps_offs(type_: str = Query("", alias="type")):
    """그 표 타입의 꺼 둔 값 → {type, offs: {기준(year · org · stage · period): [값 머리의 키 조각…]}}(없으면 빈 것). 400 타입 꼴이 아님."""
    return {"type": _off_type(type_), "offs": table_maps.get_offs(type_)}


@router.put("/api/table-maps/offs")
def table_maps_offs_put(body: dict = Body(...)):
    """그 표 타입의 꺼 둔 값을 통째로 바꿔 저장 — {type, offs: {기준: [키 조각…]}} → {type, offs: 저장한 것}. 빈 것(`{}` · 기준마다 빈 목록)이면 그 타입을 지운다. 규칙 묶음은 안 건드린다.
    400 꼴 / 503 파일 손상 · 못 씀."""
    t = _off_type(body.get("type"))
    return {"type": t, "offs": _store(lambda: table_maps.put_offs(t, body.get("offs")))}

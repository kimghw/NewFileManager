"""병합 — 고정 자리(spec_병합 ② §5-1·§5-2, 2026-11-12 사용자 「같은 이름 자리 전부」 · 「서식도 맞춰서 내용을 넣는걸」): 구분 기준(단계·차년도·기관)이 걸리지 않았지만 두 문서에
**같은 이름으로** 있는 자리에 원본(사업계획서) 내용을 넣는다 — 표지·요약문의 칸(과제명·주소·성명 …)과 칸 안·본문의 같은 제목 라벨(「[최종목표]」 — 그림 포함). 스크립트만(LLM 없음).
구분 기준 묶음의 자리 연결(merge_pairs 의 groups — 확인 필요 수·LLM 검토)과 따로 센다. 분명히 같을 때만 잇고 애매하면 비워 둔다(jobs/plan_to_report.md 「억지로 잇지 않는다」 ·
「사람이 이미 쓴 글은 덮어쓰지 않는다」). 2026-11-12 astra 검토로 조인 규칙: 뼈대·체크·차례 짝·느슨한 짝(artifacts/frame_map_astra_2026-11-12/).

- `plan(to_side, from_side, applied=None, tables_plan=None)` = 넣기 계획(문서를 안 고침). side = merge_api._read 의 꼴({"doc", "graph", "tables"(3단계), "values"}).
  → {"tables": [표 짝마다 {to, from, score, status, title, cells, skipped, flow}], "cells": [{to, from, text, table, mode, was, calc}], "labels": [merge_fill 항목 꼴 + title],
     "skipped": [{to, why, detail, table?}], "counts", "todo"}.
  1. **표 짝**: 구분 기준 항목에 안 든 필드 칸(「남는 칸」)이 있는 목적 표 ↔ 구분 기준 항목 밖의 원본 표. 닮음 = 머리 칸 꼴(merge_tables._hkey)이 겹치는 수 / 작은 쪽 머리 수
     (품음 — 연차보고서 요약문은 계획서 요약문보다 머리가 많아 자카드로는 0.38, 품음으로는 0.95). 겹침 ≥ OVERLAP_MIN(머리 서넛뿐인 작은 표가 큰 표에 품겨 1.0 이 되는 것을 막는다) ·
     1등 ≥ TABLE_MIN · 2등과 TABLE_GAP 이상 벌어짐 · 소속 제목(3단계 owner — 둘 다 없음 = 표지·요약문, 아니면 꼴이 같음)이 맞을 때만. 아니면 안 잇는다.
  2. **칸 짝**: 3단계 필드 경로(rowPath·colPath — 머리 칸 꼴의 사슬)가 같은 남는 칸끼리 하나씩. 같은 경로의 칸이 여럿이면, 그 행 머리 경로의 남는 칸을 문서 차례로 늘어놓은
     **열 머리 경로의 열이 두 문서에서 똑같을 때만** 자리대로(「국문핵심어」 다섯 칸). 다르면 모호(비워 둠 — 「현재·현재·목표·목표」 ↔ 「목표·목표·현재·현재」 를 차례로 이으면 뒤바뀐다).
     그래도 남은 칸은 하나씩일 때만 느슨하게: ㉠ 바로 붙은 행 머리 + 열 머리 경로 — 그 머리 꼴이 두 표에서 **하나뿐**일 때(「세부사업명」 — 「성명」 은 책임자마다 있어 안 됨)
     ㉠′ 그 머리 꼴이 앞의 「해당연도」 로만 다를 때(연차보고서 「해당연도 연구개발성과 활용계획 및 기대 효과」 ↔ 계획서의 같은 이름 — 그 말을 뗀 꼴이 두 표에서 하나뿐: 2026-11-23)
     ㉡ 둘 이상 이어진 행 머리 경로가 같고 한쪽에 열 머리가 없음(「실무책임자 › 성명」) ㉢ 표의 첫 두 행(문서 제목 줄)의 체크 칸 — 원본의 체크를 목적 칸 글에 옮길 수 있을 때.
  3. **칸 넣기**: 원본 칸이 비었거나 글이 같으면 일 없음 · 목적 칸이 비었으면(자리표시 포함) 넣음(mode empty) · 목적 칸이 **서식의 틀**이면 원본 글로 바꿈(mode form): 틀 = 괄호 밖에 글자가
     없고(「(우)」) 원본 글이 그것으로 시작 — 괄호 밖에 글자가 있는 글은 원본의 앞부분이어도 사람이 쓴 글로 보고 안 덮는다(「김민수」 ↛ 「김민수석」). **체크 칸**(「정책지정[ ] 지정공모[ ]」 ·
     「기준[ ]」)은 서식의 말을 두고 원본의 체크·수만 **라벨이 같은 칸에** 옮긴다(_checked_into) — 목적 칸에 이미 체크·수가 있으면 안 건드린다(다르면 occupied). 그 밖은 occupied.
     라벨 줄이 든 칸(「[최종목표]」 …)은 통째로 안 바꾸고 4 로. 계산 칸(heading_calc 수식)은 피연산자 칸의 수가 **넣은 뒤** 원본 피연산자와 같을 때만(아니면 calc — ⑤ 합계 계산 몫) —
     계산 칸으로 보는 것은 원본 글이 **수**일 때뿐이다(글 칸이 수식의 결과 칸으로 읽혀도 — 요약문 「총 연구개발비」 — 합계 검사로 붙들지 않는다: 2026-11-23).
     **줄 안의 빈 자리**(② §5-13 · merge_inline — 2026-11-23): 목적 칸이 한 줄 안에 라벨과 빈칸을 같이 적어 둔 서식이면(「총    천원 (정부지원연구개발비 :  천원, …」) 통째로 바꾸지 않고
     같은 라벨의 값만 그 빈칸에 넣는다(mode form · `inline` = 넣은 수 — 원본에 없는 라벨의 빈칸은 남는다 · 글자 모양은 서식 것 그대로). 이미 값이 다 든 칸은 일 없음.
  3-1. **머리 없는 글 칸의 줄**(_note_fill — 표지 맨 아래의 서약 · 날짜 · 서명 칸: 3단계 role note): 짝지은 표의 그 칸끼리, 「라벨: ___ 꼬리」 줄에 원본의 같은 갈래(콜론 앞 마지막 낱말 —
     「…기관의 장」) 줄의 값을 **줄 수가 같을 때만 차례대로** 넣는다(연구책임자 · 기관의 장의 이름 — 「(직인)」 · 서약 글 · 날짜 줄은 서식 것 그대로). 칸 항목 하나로 낸다(mode form · inline).
  4. **라벨 내용**: 구분 기준 항목 밖의 소제목·라벨(2단계 그래프 heading·subtitle·label) 가운데 제목(숫자 포함)이 같은 것 — 칸 안 라벨은 **위에서 짝지은 칸끼리**(표 짝·칸 짝이 문맥),
     칸 밖은 조상 제목 사슬이 모두 같고 그 열쇠가 두 문서에서 하나씩일 때. 내용 = 라벨 다음부터 다음 소제목·구분 기준 자리(그것을 품은 표 포함) 앞까지의 형제 블록(글·표·그림 —
     자리표시 줄 뺌). 목적 자리가 비었을 때만(자리표시 줄은 넣은 뒤 지움) — 칸 밖은 목적 라벨 아래에 소제목이 없을 때만. 넣은 것은 merge_fill 과 같은 `applied` 에 적는다.
     4-1 = 머리 이름과 같은 라벨 ← 라벨 없는 원본 칸의 내용 전체 · 4-2 = **합쳐 적은 라벨**(「[A 및 B]」 ← 원본 칸의 「[A]」 · 「[B]」 두 라벨의 내용을 이어 — 원본의 라벨 줄은 안 옮긴다: 2026-11-23).
  5. **서식 맞춤**(② §5-2): 짝지은 원본 표는 쪽을 넘어 나뉘는데(셀 단위로 나눔 · 글자처럼 취급 아님) 목적 표는 못 나뉘면(연차보고서 요약문 표 = 글자처럼 취급 + 나누지 않음 — 넣은
     내용이 한 쪽을 넘으면 그 뒤가 잘려 안 보이고 빈 쪽이 생긴다) 목적 표의 쪽 나눔을 원본 것으로(`flow` — 할 일에 든다). 넣은 그림이 목적 칸보다 넓으면 칸 폭으로 줄인다.
- `apply(to_doc, from_doc, plan)` = 계획을 목적 문서에 → {"filled", "shaped", "labels": merge_fill.apply 의 counts, "inserted", "fitted"(줄인 그림), "flowed"(쪽 나눔을 바꾼 표), "applied",
  "dropped", "skipped"}. 칸은 **지금** 계획 때와 같은 글일 때만 쓴다. 빈 칸은 merge_tables.apply 로(글자 모양 가져오기 포함), 틀·체크 칸은 여기서. 라벨 내용은 merge_fill.apply 로
  (블록 복사 — 서식·그림이 함께 온다).
다시 계획하면: 넣은 칸은 글이 같아 일 없음 · 라벨은 applied. ponytail: 문턱 셋은 실제 쌍 하나(KEIT 계획서 ↔ 연차보고서)로 잰 값 — 서식 쌍이 늘면 다시 잰다."""
import hashlib
import json
import re
from collections import Counter, defaultdict

from app import heading_calc as HC
from app import merge_fill as MF
from app import merge_inline as IL
from app import merge_pairs as P
from app import merge_tables as MT
from app import merge_take as TK
from app.division_profiles.rnd import core

TABLE_MIN, TABLE_GAP, OVERLAP_MIN = 0.70, 0.15, 5   # 표 짝 — 품음 1등 · 2등과의 차 · 겹치는 머리 꼴 수
CAND_OVERLAP, CAND_MIN, CANDS_MAX = 3, 0.4, 5   # LLM 검토에 보낼 후보 표 — 겹치는 머리 꼴 수 · 품음 · 표마다 후보 수
TITLE_ROWS = 2   # 느슨한 ㉢ — 문서 제목 줄(표의 첫 두 행)의 체크 칸만
HEADS = ("heading", "subtitle", "label")
WHY = ("occupied", "ambiguous", "calc", "org", "year", "shape", "outside")   # org·year = 머리는 같은데 다른 기관·다른 차년도의 표 · shape = 이은 표의 칸을 못 맞춤 · outside = 「넣을 구성 선택」 에서 고르지 않은 기관·차년도의 표
_WS = re.compile(r"\s+")
_WORD = re.compile(r"[0-9A-Za-z가-힣]")
_PAREN = re.compile(r"\([^()]*\)|\[[^\[\]]*\]")
_VALUED = re.compile(r"\[\s*[^\s\[\]]|[■☑☒]")   # 체크·수가 든 체크 칸
_ANYBOX = re.compile(r"\[\s*[√✓✔vVoOxXㅇ○●■\d.]{0,4}\s*\]|[□☐■☑☒]")   # 체크 칸 — 빈 것·체크한 것·수를 적은 것(「기준[3]」). 글이 든 대괄호(「[최종목표]」)는 아니다
_FOOT = re.compile(r"\d{1,2}(?:-\d{1,2})?\)")   # 머리 칸에 붙은 위첨자 각주 번호 「14)」·「15-1)」(글로는 이름 뒤에 붙어 읽힌다 — 이름을 견줄 때 뗀다)
_HINT = re.compile(r"\([^()]*(?:체크|해당|작성|기재|선택|표시)[^()]*\)")   # 체크 라벨에 딸린 안내 글 「(해당항목 체크)」 — 라벨을 견줄 때 뗀다(「통합형(세부)」 의 괄호는 라벨의 일부라 안 뗀다)
_THIS = re.compile(r"^(?:해당|당해)[연년]도")   # 머리 꼴 앞의 「해당연도」 — 느슨한 ㉠′(연차보고서가 계획서의 같은 자리 이름 앞에 붙인 말)
_JOIN = re.compile(r"\s*(?:및|·|ㆍ)\s*")   # 합쳐 적은 라벨 제목을 가르는 말(4-2 — 「[연구개발성과의 활용방안 및 기대효과]」)


def _side(side):
    """문서 하나 → merge_tables._side 의 읽을거리 + 3단계 표·2단계 그래프·블록·구분 기준 항목이 차지한 id·구분 라벨 id·형제 목록."""
    S = MT._side(side, side["values"])
    blocks = side["doc"].blocks()
    cov, div, cov_tab, hold = set(), set(), set(), defaultdict(dict)
    for g in S["groups"].values():   # 구분 기준 묶음의 자리는 묶음 짝(merge_pairs)이 맡는다
        para = g["kind"] == "paragraph" and not g.get("list")
        for it in g["items"]:
            ids = {*(it.get("roots") or ()), *(it.get("scope") or ())}
            cov.update(ids)
            if it.get("label"):
                cov.add(it["label"])
                div.add(it["label"])
            if not para:   # 표 묶음(행·열·목록 행)의 칸 — 표 칸 넣기(merge_tables)가 맡는다
                cov_tab.update(ids)
                if it.get("label"):
                    cov_tab.add(it["label"])
            elif (ident := MT._ident(S, g, it)) and ident[0] in ("org", "year"):   # 문단 묶음 항목(기관 절·차년도 절) — 그 안의 블록은 그 기관·차년도의 것
                for i in ids:
                    hold[i].setdefault(ident[0], ident[1])
    where = {}

    def walk(seq):   # 블록 id → 그 블록이 든 형제 목록(본문 맨 위 · 칸 안)
        for b in seq:
            where[b["id"]] = seq
            for c in b.get("cells") or ():
                walk(c.get("blocks") or ())
    walk(blocks)
    nodes = (side.get("graph") or {}).get("nodes") or ()
    heads = {n["id"] for n in nodes if n.get("role") in HEADS}
    S.update(tables=(side.get("tables") or {}).get("tables") or (), nodes=nodes, heads=heads, cov=cov, cov_tab=cov_tab, hold=hold, stops=heads | div, where=where,
             org_names=[n for _, n in P._orgs(S["values"]) if n],
             parents={n.get("parent") for n in nodes if n["id"] in heads},
             labeled={c["id"] for b in S["idx"].values() for c in b.get("cells") or () if any(x["id"] in heads for x in c.get("blocks") or ())})   # 라벨 줄이 바로 든 칸
    return S


def _text(S, cid):
    return (S["idx"].get(cid) or {}).get("text") or ""


def _head_shapes(S, t):
    """표의 머리 칸 꼴마다 그 수(지금 글)."""
    return Counter(k for k in (MT._hkey(_text(S, c["id"]), S["names"]) for c in t["cells"] if c.get("role") in MT.HEADS) if k)


def _owner(t):
    return P._shape((t.get("owner") or {}).get("text") or "")


def _free(S, t):
    """표의 남는 칸 — 표 묶음(행·열·목록 행) 항목 밖의 필드 칸(지금 문서에 있는 것) → [(칸, (행 머리 꼴 사슬, 열 머리 꼴 사슬))], 문서 차례.
    기관 절·차년도 절(문단 묶음 항목) **안의 표**도 든다 — 그 표의 칸은 묶음 짝이 안 맡는다(본문 넣기는 「양식 표가 있는 자리」 로 건너뛴다). 어느 기관·차년도의 표인지는 _ctx 가 가린다."""
    hk = lambda i: MT._hkey(_text(S, i), S["names"])  # noqa: E731
    return [(c, (tuple(k for k in map(hk, c.get("rowPath") or ()) if k), tuple(k for k in map(hk, c.get("colPath") or ()) if k)))
            for c in sorted(t["cells"], key=lambda c: (c["row"], c["col"])) if c.get("role") == "field" and c["id"] not in S["cov_tab"] and c["id"] in S["idx"]]


def _title_of(S, t):
    first = next((c for c in t["cells"] if c["row"] == 0 and c["col"] == 0), None)
    return (t.get("owner") or {}).get("text") or _text(S, (first or {}).get("id")) or ""


def _ctx(S, t):
    """표의 맥락 {"org": 기관 이름 꼴 | None, "year": 전체 차례 차년도 수 | None} — **어느 기관·어느 차년도의 표인가**(spec_병합 ② §5-1 「기관·차년도 가리기」).
    기관 = 그 표를 품은 기관 절(문단 묶음 항목)의 기관, 없으면 소속 제목 사슬의 기관 절 제목에 적힌 이름(merge_pairs._path_org — 번호가 틀린 「[공동연구개발기관1 : 유엔젤]」 도).
    차년도 = 표 제목 줄에 적힌 차년도(「…현황표(2차년도)」), 없으면 그 표를 품은 차년도 절, 그것도 없으면 소속 제목의 「다음 연도」(당해 + 1)·「해당 연도」(당해)."""
    own = t.get("owner") or {}
    raw = [*(own.get("path") or ()), own.get("text") or ""]
    held = S["hold"].get(t["id"]) or {}
    cur = S["values"].get("current") or 1
    text = " ".join(P._ws(x) for x in raw)
    year = MT._year_no(own.get("text") or "", S["values"]) or held.get("year") or (cur + 1 if P._NEXT.search(text) else cur if P._THIS.search(text) else None) or _own_year(S, t)
    return {"org": held.get("org") or P._path_org(raw, S["org_names"]), "year": year}


def _own_year(S, t):
    """표 **자기 머리**에 적힌 차년도 — 머리 칸의 「N차년도」 가 한 가지뿐일 때만(「1차년도(9개월)」 월 일정 표: 한 절에 차년도마다 표가 따로 있다 — spec_병합 ② §5-3). 여러 해가 열로 놓인 표
    (「1차년도 | 2차년도 | …」)와 연도 숫자(「2027」)뿐인 머리는 None — 그 표는 전 차년도 표다."""
    years = set()
    for c in t["cells"]:
        if c.get("role") in MT.HEADS and core.YEAR_RE.search(text := _WS.sub("", _text(S, c["id"]))):
            if (y := MT._year_no(text, S["values"])) is not None:
                years.add(y)
    return next(iter(years)) if len(years) == 1 else None


def _ctx_clash(ct, cf):
    """두 표의 맥락이 **어긋나는가** → "org"|"year"|None — 둘 다 알고 다를 때만(사람·LLM 이 고른 짝도 이것은 못 넘는다: 다른 기관·다른 차년도의 값이 들어간다)."""
    return next((k for k in ("org", "year") if ct[k] is not None and cf[k] is not None and ct[k] != cf[k]), None)


def _table_pairs(T, F, forced=None, full=False):
    """표 짝(모듈 설명 1) → [{to, from, score, status, source, reason, why, title, ctx, cands, free}] — 남는 칸이 있는 목적 표마다.
    full = 넣을 것이 없는 표(기관·차년도 절 안의 빈 칸 없는 표)도 짝을 낸다 — 넣은 뒤의 원본 자리 지도(`pairs`)용.
    스크립트 짝 = 머리 꼴 품음(1등 ≥ TABLE_MIN · 2등과 TABLE_GAP · 겹침 ≥ OVERLAP_MIN) + 소속 제목 꼴이 같음 + **맥락(기관·차년도)이 같음**(둘 다 없음 = 과제 전체 표, 아니면 같은 기관·같은 차년도 —
    한쪽만 아는 것도 다른 것으로 본다: 기관 절 안의 표 ↔ 과제 전체 표, 「다음 연도」 표 ↔ 연도 없는 표는 스크립트가 잇지 않는다). 머리는 맞는데 맥락이 달라 못 이은 표는 why(org|year)에 남긴다.
    forced = {목적 표 id: {"from": 원본 표 id | None, "source": llm|user, "reason"}} — 스크립트보다 먼저(LLM 검토 merge_llm · 사람). 맥락이 어긋나면(_ctx_clash) 안 받는다.
    cands = 머리가 겹치는 원본 표(소속 제목은 안 따짐 — LLM 검토에 보낼 후보: 겹침 ≥ CAND_OVERLAP · 품음 ≥ CAND_MIN, 맥락이 어긋나지 않는 것, CANDS_MAX 개)."""
    forced = forced or {}
    fby = {f["id"]: f for f in F["tables"]}
    src = [(f, set(s), _owner(f), _ctx(F, f)) for f in F["tables"] if f["id"] in F["idx"] and (s := _head_shapes(F, f))]
    out = []
    for t in T["tables"]:
        if t["id"] not in T["idx"]:
            continue
        free, s, own, ct = _free(T, t), set(_head_shapes(T, t)), _owner(t), _ctx(T, t)
        if not free or (len(s) < 2 and t["id"] not in forced):   # 머리 꼴이 둘 미만인 표는 스크립트가 견줄 것이 없다 — LLM·사람이 정한 짝(forced)이 있을 때만 줄을 낸다(review_tables 가 그 표도 LLM 에 보인다)
            continue
        if not full and t["id"] in T["cov"] and not any(MT._empty(_text(T, c["id"])) for c, _ in free):
            continue   # 기관·차년도 절 안의 표인데 빈 칸이 없다(본문 넣기로 통째로 온 표 등) — 넣을 것이 없다
        same = lambda cf: all(ct[k] == cf[k] for k in ("org", "year"))  # noqa: E731
        near = sorted(((len(s & b) / min(len(s), len(b)), len(s & b), f["id"], o == own, cf) for f, b, o, cf in src if len(s & b) >= CAND_OVERLAP), key=lambda x: (-x[0], -x[1]))
        cands = [(v, fid) for v, n, fid, o, cf in near if n >= OVERLAP_MIN and o and same(cf)]
        row = {"to": t["id"], "from": None, "score": cands[0][0] if cands else 0.0, "status": "none", "source": "script", "reason": "", "why": None, "free": free,
               "title": _title_of(T, t), "ctx": ct,
               "cands": [{"from": fid, "score": round(v, 2), "overlap": n} for v, n, fid, o, cf in near if v >= CAND_MIN and not _ctx_clash(ct, cf)][:CANDS_MAX]}
        fx = forced.get(t["id"])
        if fx is not None and (fx.get("from") is None or (fx["from"] in fby and fx["from"] in F["idx"] and not _ctx_clash(ct, _ctx(F, fby[fx["from"]])))):
            row.update(status="paired" if fx.get("from") else "none", source=fx.get("source") or "user", reason=fx.get("reason") or "")
            row["from"] = fx.get("from")
            row["score"] = next((v for v, n, fid, o, cf in near if fid == fx.get("from")), 0.0)
        elif cands and cands[0][0] >= TABLE_MIN:
            if len(cands) == 1 or cands[0][0] - cands[1][0] >= TABLE_GAP:
                row["status"], row["from"] = "paired", cands[0][1]
            else:
                row["status"] = "ambiguous"
        elif hits := [cf for v, n, fid, o, cf in near if n >= OVERLAP_MIN and o and v >= TABLE_MIN]:   # 머리·소속은 맞는데 맥락이 다른 표가 있다 — 까닭을 남긴다(같은 기관의 것부터)
            cf = max(hits, key=lambda cf: (ct["org"] == cf["org"], ct["year"] == cf["year"]))
            row["why"] = "org" if ct["org"] != cf["org"] else "year"
            row["reason"] = _ctx_note(row["why"], ct, cf)
        out.append(row)
    return out


def _ctx_note(why, ct, cf):
    word = lambda k, v: "없음" if v is None else f"{v}차년도" if k == "year" else str(v)  # noqa: E731
    return f"{'차년도가' if why == 'year' else '기관이'} 다른 표 — 목적 {word(why, ct[why])} ↔ 원본 {word(why, cf[why])}"


def _unique(tleft, fleft, key):
    """남은 칸 가운데 key(칸, 경로)가 두 문서에서 하나씩인 것끼리 → [(목적 칸, 원본 칸)]. key 가 None 인 칸은 안 본다."""
    tk, fk = defaultdict(list), defaultdict(list)
    for c, k in tleft:
        if (x := key(c, k)) is not None:
            tk[x].append(c)
    for c, k in fleft:
        if (x := key(c, k)) is not None:
            fk[x].append(c)
    return [(cs[0], fk[x][0]) for x, cs in tk.items() if len(cs) == 1 and len(fk.get(x) or ()) == 1]


def _cell_pairs(tfree, ffree, ttext, ftext, thead=None, fhead=None, full=False):
    """칸 짝(모듈 설명 2) → ([(목적 칸, 원본 칸)], 모호해서 못 맞춘 목적 칸 수). ttext·ftext = 칸 id → 지금 글, thead·fhead = 그 표의 머리 꼴 → 수(느슨한 ㉠ — 없으면 ㉠ 안 함).
    full = ㉢ 에서 **이미 옮긴** 체크 칸(목적 칸의 체크·수가 원본과 같음)도 짝으로 본다 — 넣은 뒤의 원본 자리 지도(`pairs`)용. 넣기 계획은 안 쓴다(옮길 것이 없는 칸)."""
    tk, fk = defaultdict(list), defaultdict(list)
    for c, k in tfree:
        tk[k].append(c)
    for c, k in ffree:
        fk[k].append(c)
    pairs, rows = [], set()
    for k, cs in tk.items():
        got = fk.get(k) if any(k) else None
        if not got:
            continue
        if len(cs) == 1 and len(got) == 1:
            pairs.append((cs[0], got[0]))
        else:
            rows.add(k[0])   # 같은 경로가 여럿 — 그 행 머리 경로를 통째로 본다
    amb, held = 0, set()   # held = 모호로 남긴 칸 — 아래 느슨한 맞춤에 안 넣는다
    for rp in rows:
        ts, fs = [(c, k) for c, k in tfree if k[0] == rp], [(c, k) for c, k in ffree if k[0] == rp]
        if rp and [k[1] for _, k in ts] == [k[1] for _, k in fs]:   # 열 머리 경로의 열이 똑같다 — 자리대로(이미 하나씩 맞춘 칸과도 어긋나지 않는다)
            done = {t["id"] for t, _ in pairs}
            pairs += [(t, f) for (t, _), (f, _) in zip(ts, fs) if t["id"] not in done]
        else:
            lost = [c for c, k in ts if len(tk[k]) > 1 or len(fk.get(k) or ()) > 1]
            amb += len(lost)
            held |= {c["id"] for c in lost} | {c["id"] for c, k in fs if len(fk[k]) > 1 or len(tk.get(k) or ()) > 1}

    def left():
        done_t, done_f = {t["id"] for t, _ in pairs} | held, {s["id"] for _, s in pairs} | held
        return [(c, k) for c, k in tfree if c["id"] not in done_t], [(c, k) for c, k in ffree if c["id"] not in done_f]

    # 경로가 조금 어긋난 칸 — 두 서식의 3단계 분석이 머리의 부모·열 머리를 다르게 볼 수 있다. 하나씩일 때만, 좁은 것부터(모듈 설명 2 ㉠㉡㉢)
    if thead is not None and fhead is not None:
        tl, fl = left()   # ㉠ — 그 머리 꼴이 두 표에서 하나뿐일 때
        pairs += _unique(tl, fl, lambda c, k: (k[0][-1], k[1]) if k[0] and thead.get(k[0][-1]) == 1 and fhead.get(k[0][-1]) == 1 else None)
        tl, fl = left()   # ㉠′ — 머리 꼴이 앞의 「해당연도」 로만 다를 때(연차보고서 「해당연도 연구개발성과 활용계획 및 기대 효과」 ↔ 계획서 「연구개발성과 활용계획 및 기대 효과」 — 2026-11-23): 그 말을 뗀 꼴이 두 표에서 하나뿐
        ts, fs = Counter(), Counter()
        for src, into in ((thead, ts), (fhead, fs)):
            for h, n in src.items():
                into[_THIS.sub("", h)] += n
        pairs += _unique(tl, fl, lambda c, k: (_THIS.sub("", k[0][-1]), k[1]) if k[0] and (h := _THIS.sub("", k[0][-1])) and ts.get(h) == 1 and fs.get(h) == 1 else None)
    tl, fl = left()   # ㉡ — 둘 이상 이어진 행 머리 경로 · 한쪽에 열 머리가 없음
    kt, kf = {c["id"]: k for c, k in tl}, {c["id"]: k for c, k in fl}
    pairs += [(t, s) for t, s in _unique(tl, fl, lambda c, k: k[0] if len(k[0]) >= 2 else None) if not kt[t["id"]][1] or not kf[s["id"]][1]]
    tl, fl = left()   # ㉢ — 문서 제목 줄의 체크 칸(머리가 문서 제목뿐이라 경로로는 못 맞춘다): 원본에 체크가 있고 그 체크를 목적 칸 글에 옮길 수 있을 때
    tl, fl = [(c, k) for c, k in tl if c["row"] < TITLE_ROWS], [(c, k) for c, k in fl if c["row"] < TITLE_ROWS]
    moved = lambda a, b: _checked_into(a, b) is not None or (full and bool(_checked(a)) and _checked(a) == _checked(b))  # noqa: E731 — 옮길 수 있다 · (full) 이미 옮겼다
    for t, _ in tl:
        a = ttext(t["id"])
        hit = [s for s, _ in fl if moved(a, ftext(s["id"]))]
        if len(hit) == 1 and sum(moved(ttext(x["id"]), ftext(hit[0]["id"])) for x, _ in tl) == 1:
            pairs.append((t, hit[0]))
    return pairs, amb


def _within(a, b):
    """글 a 의 낱말 · 수가 글 b 에 그 차례로 모두 들어 있나(b 에 더 있어도 된다) — 빈 자리를 두던 칸에 원본의 값이 이미 들어갔는지 볼 때."""
    words = lambda x: [t for t, _, _ in IL._toks(x) if IL._is_word(t)]  # noqa: E731
    it = iter(words(b))
    return all(any(w == x for x in it) for w in words(a))


def _note_fill(T, F, t, f):
    """머리 없는 글 칸(3단계 role note — 표지 맨 아래의 서약 · 날짜 · 서명 칸)의 「라벨: ___ 꼬리」 줄에, 짝지은 원본 표의 같은 갈래 줄의 값을 넣는다(모듈 설명 3-1) → ([칸 항목], [skipped]).
    갈래 = 콜론 앞 마지막 낱말(「주관연구개발기관의 장:」 · 「공동연구개발기관의 장:」 → 「장」). 목적 칸의 그 갈래 빈 줄 수와 원본의 그 갈래 줄 수가 **같을 때만** 차례대로 잇는다 —
    서명 줄은 두 문서에서 같은 기관 차례로 놓이고(주관 → 공동1 → …), 라벨의 「주관」·「공동」 은 원본에서 잘못 적혀 있기도 하다(실제 작성본: 둘째 줄도 「주관연구개발기관의 장」).
    수가 다르면 어느 기관의 줄인지 알 수 없어 넣지 않는다(ambiguous). 칸은 통째로 안 바꾼다 — 그 줄의 빈칸에 값만(merge_inline.fill_at): 서약 글 · 날짜 줄 · 「(직인)」 은 목적 서식 것 그대로."""
    def lines(S, tb):
        for c in tb["cells"]:
            bs = (S["idx"].get(c["id"]) or {}).get("blocks") or ()
            if c.get("role") == "note" and bs and all(b.get("type") == "paragraph" for b in bs):
                yield c["id"], [b.get("text") or "" for b in bs]
    src = defaultdict(list)   # 갈래 → 원본 줄(문서 차례)
    for cid, ls in lines(F, f):
        for ln in ls:
            if k := IL.family(ln):
                src[k].append((cid, ln))
    cells, skipped = [], []
    for cid, ls in lines(T, t):
        cur = _text(T, cid)
        if "\n".join(ls) != cur:
            continue   # 칸 글이 문단 글을 이은 것과 다르다(안쪽 표 등) — 줄 단위로 못 쓴다
        want = defaultdict(list)   # 갈래 → 이 칸의 빈 자리 줄 차례
        for i, ln in enumerate(ls):
            if IL.lone(ln) and (k := IL.family(ln)):
                want[k].append(i)
        new, n, frm = list(ls), 0, None
        for k, idxs in want.items():
            got = src.get(k) or ()
            if len(got) != len(idxs):
                if got:
                    skipped.append({"to": cid, "table": t["id"], "why": "ambiguous", "detail": f"「… {k}:」 줄 수가 달라 못 맞춤(목적 {len(idxs)} ↔ 원본 {len(got)})"})
                continue
            for i, (scid, sl) in zip(idxs, got):
                if (x := IL.fill_at(ls[i], sl)) is not None:
                    new[i], n, frm = x, n + 1, frm or scid
        if n:
            cells.append({"to": cid, "from": frm, "text": "\n".join(new), "table": t["id"], "mode": "form", "was": cur, "calc": False, "inline": n})
    return cells, skipped


def _skeleton(t, s):
    """목적 칸 글 t 가 원본 칸 글 s 의 **틀**인가 — t 에 괄호 밖 글자가 없고(「(우)」 처럼 서식의 약어·괄호뿐) s 가 t 로 시작한다. 괄호 밖에 글자가 있는 글은 원본의 앞부분이어도
    사람이 쓴 글일 수 있다(「김민수」 ↛ 「김민수석」 — astra 검토: 부분수열만으로 덮으면 사람 글을 덮는다)."""
    a, b = _WS.sub("", t or ""), _WS.sub("", s or "")
    return bool(a) and len(a) < len(b) and b.startswith(a) and not _WORD.search(_PAREN.sub("", a))


def _box_items(text):
    """체크 칸 글 → (라벨이 칸 뒤에 오나, [(라벨 글자 — 안내 글 괄호 뗌, 체크 칸 글)]) | None(체크 칸 없음). 글이 체크 칸으로 시작하면 라벨이 칸 뒤(「[ ] 일반형」), 아니면 칸 앞(「정책지정[ ]」)."""
    ms = list(_ANYBOX.finditer(text or ""))
    if not ms:
        return None
    after = not _WORD.search(text[:ms[0].start()])
    segs = [text[m.end():ms[i + 1].start() if i + 1 < len(ms) else len(text)] if after else text[ms[i - 1].end() if i else 0:m.start()] for i, m in enumerate(ms)]
    return after, [("".join(_WORD.findall(_HINT.sub("", seg))), m.group(0)) for seg, m in zip(segs, ms)]


def _checked(text):
    """체크 칸 글 → {라벨: 체크·수(빈칸 뗀 칸 글)} — 값이 든 칸만."""
    return {lab: _WS.sub("", box) for lab, box in (_box_items(text) or (None, ()))[1] if _VALUED.search(box)}


def _checked_into(t, s):
    """목적 칸 글 t 의 **빈** 체크 칸에, 원본 칸 글 s 에서 체크·수가 든 칸을 **라벨이 같은 칸에** 옮긴 글 | None. 서식의 말은 목적 것 그대로 두고 값만 가져온다 — 원본에만 있는 안내 글
    (「[ √ ] 일반형 (해당항목 체크)」 의 괄호)이 딸려 오지 않고, 쉼표 같은 차이(「일반[ ], 보안[ ]」)도, 목적에만 있는 보기(「… 해당없음[ ]」)도 넘는다.
    None = 체크 칸이 없음 · 옮길 체크가 없음 · 목적 칸에 이미 체크·수가 있음(안 건드린다) · 체크한 원본 라벨이 목적에 없거나 여럿(「R&D 샌드박스」 ↔ 「R&D 자율성트랙」 · 「국내」 ↔ 「국내외」 —
    라벨은 글자가 모두 같아야 한다) · 원본에 같은 라벨이 둘."""
    a, b = _box_items(t), _box_items(s)
    if not a or not b or a[0] != b[0] or any(_VALUED.search(box) for _, box in a[1]):
        return None
    put, seen = {}, set()
    for lab, box in b[1]:
        if _VALUED.search(box):
            hit = [k for k, (tl, _) in enumerate(a[1]) if tl == lab]
            if len(hit) != 1 or lab in seen:
                return None
            put[hit[0]] = box
            seen.add(lab)
    if not put:
        return None
    k = iter(range(len(a[1])))
    return _ANYBOX.sub(lambda m: put.get(next(k), m.group(0)), t)


def _title(n):
    """소제목·라벨의 견줄 제목 — 글의 글자(숫자 포함: 「ISO 9001」 ≠ 「ISO 14001」), 글이 없으면 레터(「[최종목표]」). 번호 레터(「1.」)는 서식마다 달라 안 넣는다."""
    return "".join(_WORD.findall(n.get("text") or "")) or "".join(_WORD.findall(n.get("letter") or ""))


def _labels(S):
    """고정 라벨 후보 {(영역, 조상 제목 사슬, 제목): [노드]} — 구분 기준 항목 밖의 소제목·라벨, 제목에 글자가 둘 이상."""
    by = {n["id"]: n for n in S["nodes"]}

    def path(n):
        out, seen = [], set()
        p = by.get(n.get("parent"))
        while p is not None and p["id"] not in seen and len(out) < 12:
            seen.add(p["id"])
            out.append(_title(p))
            p = by.get(p.get("parent"))
        return tuple(out[::-1])
    out = defaultdict(list)
    for n in S["nodes"]:
        if n["id"] in S["heads"] and n["id"] not in S["cov"] and n["id"] in S["idx"] and len(_title(n)) >= 2:
            out[(n.get("area"), path(n), _title(n))].append(n)
    return out


def _cell_of(n):
    """칸 안 라벨이 든 칸 id | None — 2단계 그래프의 flow(「cell:<칸 id>」)."""
    flow = n.get("flow") or ""
    return flow[5:] if flow.startswith("cell:") else None


def _slot(S, nid):
    """라벨 다음부터 다음 소제목·구분 기준 자리 앞까지의 형제 블록(표·그림에 딸린 캡션 블록은 뺌 — 그 표·그림과 함께 간다). 구분 기준 자리나 소제목을 **품은** 블록(표)에서도 끊는다."""
    seq = S["where"].get(nid) or ()
    k = next((i for i, b in enumerate(seq) if b["id"] == nid), None)
    out = []
    for b in seq[k + 1:] if k is not None else ():
        if any(x["id"] in S["stops"] or x["id"] in S["cov"] for x in core._under(b)):
            break
        if not b.get("captionOf"):
            out.append(b)
    return out


def _hash(src):
    """라벨 내용의 해시 — merge_fill 의 것(종류·글)에 그림 파일 이름을 더한다(글 없는 그림 둘이 바뀌어도 「원본 바뀜」 을 안다)."""
    media = [x.get("media") for b in src for x in core._under(b) if x.get("type") == "image"]
    return hashlib.sha256(json.dumps([MF._hash(src), media], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def plan(to_side, from_side, applied=None, tables_plan=None, forced=None, sides=None, skip=(), take=None, orig=None):
    """고정 자리 넣기 계획(모듈 설명) — 문서를 안 고친다. tables_plan = 같은 차례에 세운 merge_tables.plan(그 칸은 건너뛰고, 계산 칸의 피연산자가 넣은 뒤 무슨 글이 되는지 본다).
    forced = LLM 검토·사람이 정한 표 짝(_table_pairs — merge.json `tables`). 표 줄 = {to, from, score, status, source(script|llm|user), reason, why(맥락이 달라 못 이음 org|year | None),
    title, fromTitle, ctx{org, year}, cands[{from, score, overlap}], cells, skipped, flow}.
    orig = 목적 문서로 올린 원본이 **등록된 빈 양식**일 때 그 원본의 표 칸 {칸 id: {text, …}}(merge_api._orig — 표 대응의 예시 판정과 같은 것) | None: 짝지은 값 칸의 글이 빈 양식의 글 그대로면
    (서식의 예시 · 틀 — 「1순위 소분류 명칭」 · 「총    천원 (정부지원연구개발비 :  천원 …」 · 「(우)」) 사람이 쓴 글이 아니라 원본 글로 바꾼다(mode form). None 이면 전처럼 글이 든 칸은 안 덮는다."""
    applied = applied or {}
    asis = lambda cid, cur: bool(orig) and cid in orig and P._ws(orig[cid].get("text") or "") == P._ws(cur)  # noqa: E731 — 올린 빈 양식의 글 그대로(2026-11-22 — 실제 이관 7cfb2957f487 의 요약문 기술분류 · 총 연구개발비 · 표지 주소)
    slotted = lambda cid: bool(orig) and cid in orig and any(IL.slots(ln) for ln in (orig[cid].get("text") or "").split("\n"))  # noqa: E731 — 올린 빈 양식에서 줄 안에 빈 자리를 두던 칸(「총    천원 (…」)
    T, F = sides or (_side(to_side), _side(from_side))   # sides = 이미 읽어 둔 두 쪽(merge_api — 표 대응 계획 merge_table_map 과 같이 쓴다) · skip = 표 대응이 통째로 맡은 목적 표 id(② §5-3 2 — 그 표의 칸은 여기서 안 낸다)
    cells, calc, labels, skipped, tables, paired = [], [], [], [], [], set()
    after = {c["to"]: c["text"] for c in (tables_plan or {}).get("cells") or ()}
    ttabs, ftabs = {t["id"]: t for t in T["tables"]}, {f["id"]: f for f in F["tables"]}

    for tp in _table_pairs(T, F, forced):   # 1~3. 표 짝 → 칸 짝 → 칸 넣기
        row = {"to": tp["to"], "from": tp["from"], "score": round(tp["score"], 2), "status": tp["status"], "source": tp["source"], "reason": tp["reason"], "why": tp["why"],
               "title": P._ws(tp["title"])[:P.TEXT_MAX], "fromTitle": P._ws(_title_of(F, ftabs[tp["from"]]))[:P.TEXT_MAX] if tp["from"] else "", "ctx": tp["ctx"], "cands": tp["cands"],
               "format": ((forced or {}).get(tp["to"]) or {}).get("format") or "", "cells": 0, "skipped": 0, "flow": None}
        tables.append(row)
        if take is not None and not take.ctx(tp["ctx"]):   # 「넣을 구성 선택」(merge_take — spec_병합 ② §4-1)에서 고르지 않은 기관 · 차년도의 표(기관 절 · 차년도 절 안의 표) — 넣지 않는다
            row.update(status="none", why="outside", reason=TK.OUT, skipped=1)
            skipped.append({"to": tp["to"], "table": tp["to"], "why": "outside", "detail": TK.OUT})
            continue
        if tp["to"] in skip:   # 표 대응(merge_table_map)이 통째로 맡은 표 — 칸은 그쪽 계획이 낸다(한 칸을 두 길이 쓰지 않게)
            row["mapped"] = True
            continue
        if tp["why"]:
            skipped.append({"to": tp["to"], "table": tp["to"], "why": tp["why"], "detail": tp["reason"]})
            row["skipped"] = 1
        if tp["status"] != "paired":
            continue
        ff = from_side["doc"].table_flow(tp["from"])   # 5. 쪽 나눔 — 원본 표는 쪽을 넘어 나뉘는데 목적 표는 못 나뉘면(글자처럼 취급·나누지 않음) 원본 것으로
        if ff and ff["splits"] and not (to_side["doc"].table_flow(tp["to"]) or {"splits": True})["splits"]:
            row["flow"] = ff
        n0 = len(skipped)
        pairs, amb = _cell_pairs(tp["free"], _free(F, ftabs[tp["from"]]), lambda i: _text(T, i), lambda i: _text(F, i), _head_shapes(T, ttabs[tp["to"]]), _head_shapes(F, ftabs[tp["from"]]))
        paired |= {(c["id"], s["id"]) for c, s in pairs}
        if not pairs and not amb:   # 같은 표로 이었지만(LLM·사람이 고른 짝에서 흔하다) 행·열 머리가 달라 한 칸도 못 맞춤 — 표 안 대응(행 차례·차년도 열)은 아직 스크립트가 못 한다
            skipped.append({"to": tp["to"], "table": tp["to"], "why": "shape", "detail": "행·열 머리가 달라 칸을 못 맞춤"})
        if amb:
            skipped.append({"to": tp["to"], "table": tp["to"], "why": "ambiguous", "detail": f"머리 경로가 같은 칸이 여럿이라 못 맞춘 칸 {amb}"})
        for c, s in pairs:
            cur, new = _text(T, c["id"]), _text(F, s["id"])
            src, inline = new, 0   # src = 원본 칸의 글 그대로 · inline = 줄 안의 빈 자리에 넣은 값의 수
            if MT._empty(new) or P._ws(new) == P._ws(cur) or c["id"] in after:
                continue
            if c["id"] in T["labeled"] or s["id"] in F["labeled"]:
                continue   # 라벨 줄이 든 칸 — 라벨 내용(4)으로
            if _ANYBOX.search(cur) and _ANYBOX.search(new):   # 체크 칸 — 서식의 말은 그대로, 체크·수만 라벨이 같은 칸에
                want, have = _checked(new), _checked(cur)
                if not want or have == want:
                    continue   # 옮길 체크가 없다(글의 다른 점은 서식의 말) · 이미 같다
                box = None if have else _checked_into(cur, new)   # 목적 칸에 이미 체크·수가 있으면 안 건드린다
                mode, new = ("form", box) if box is not None else (None, new)
            else:
                inl = None if MT._empty(cur) else IL.fill(cur, new)   # 줄 안의 빈 자리(「라벨 : ___ 꼬리」 — merge_inline): 서식의 글은 두고 값만
                if inl is not None:
                    mode, new, inline = "form", inl[0], inl[1]
                elif slotted(c["id"]) and _within(new, cur):
                    continue   # 빈 자리를 두던 칸에 원본의 값이 이미 다 들어 있다(앞서 넣음) — 남은 빈 자리는 원본에 없는 것
                else:
                    mode = "empty" if MT._empty(cur) else "form" if _skeleton(cur, new) or asis(c["id"], cur) else None
            if mode is None:
                skipped.append({"to": c["id"], "table": tp["to"], "why": "occupied", "detail": f"목적 칸에 「{P._ws(cur)[:30]}」 — 원본 「{P._ws(new)[:30]}」"})
                continue
            x = {"to": c["id"], "from": s["id"], "text": new, "table": tp["to"], "mode": mode, "was": cur,
                 "calc": bool(T["ops"].get(c["id"])) and not inline and HC.parse_num(src).get("num") is not None}   # 계산 칸 = 수를 적는 칸일 때만(글 칸이 수식의 결과 칸으로 읽혀도 — 요약문 「총 연구개발비」 — 합계 검사로 붙들지 않는다)
            if inline:
                x["inline"] = inline
            (calc if x["calc"] else cells).append(x)
        got = _note_fill(T, F, ttabs[tp["to"]], ftabs[tp["from"]])   # 3-1. 머리 없는 글 칸의 「라벨: ___」 줄(표지의 서명 줄)
        cells += got[0]
        skipped += got[1]
        row["skipped"] = len(skipped) - n0
    # 계산 칸 — 피연산자 칸의 수가 넣은 뒤 원본 피연산자와 같을 때만(합계가 그 줄들의 합으로 남는다). 합계의 합계가 있어 더 안 늘 때까지 되풀이
    after.update({c["to"]: c["text"] for c in cells})
    nums = lambda S, ids, now: sorted(HC.parse_num(now.get(i, _text(S, i))).get("num") or 0 for i in ids)  # noqa: E731 — 빈 칸과 「-」 는 0 으로 같다
    while calc:
        ok = [x for x in calc if F["ops"].get(x["from"]) and nums(T, T["ops"][x["to"]], after) == nums(F, F["ops"][x["from"]], {})]
        if not ok:
            break
        for x in ok:
            calc.remove(x)
            cells.append(x)
            after[x["to"]] = x["text"]
    for x in calc:
        skipped.append({"to": x["to"], "table": x["table"], "why": "calc", "detail": "계산 칸 — 피연산자 칸이 원본과 같지 않아 비워 둠(합계 계산이 셈)"})
    per, per_skip = Counter(c["table"] for c in cells), Counter(x["table"] for x in calc)
    for row in tables:
        row["cells"], row["skipped"] = per.get(row["to"], 0), row["skipped"] + per_skip.get(row["to"], 0)

    def put(t, frm, blocks, in_cell):
        """라벨 t 의 내용으로 원본 블록들(blocks — 자리표시 줄 · 앞뒤 빈 줄은 뺀다)을 넣는 항목 하나를 labels 에 적는다. frm = 원본 쪽 자리(라벨 id · 4-1 은 원본 칸 id) · in_cell = 칸 안 라벨인가."""
        src = [b for b in blocks if not MF._placeholder(b)]
        while src and MF._blank(src[0]):
            src.pop(0)
        while src and MF._blank(src[-1]):
            src.pop()
        if not src:
            return
        title = P._ws(f"{t.get('letter') or ''} {t.get('text') or ''}")[:P.TEXT_MAX]
        row = {"group": None, "value": title, "title": title, "to": t["id"], "from": frm, "anchor": t["id"], "anchorText": title, "src": [b["id"] for b in src], "blocks": len(src),
               "paragraphs": 0, "tables": 0, "pictures": 0, "placeholders": [], "hash": _hash(src), "skip": None, "detail": ""}
        row["paragraphs"], row["tables"], row["pictures"] = MF._count(src)
        labels.append(row)
        place = _slot(T, t["id"])
        if t["id"] in applied:
            same = applied[t["id"]].get("hash") == row["hash"]
            row.update(skip="applied" if same else "changed", detail="" if same else "원본 바뀜 — 다시 넣지 않음")
        elif not in_cell and t["id"] in T["parents"]:
            row.update(skip="occupied", detail="아래에 소제목이 있는 자리 — 넣지 않음")
        elif any(b.get("type") == "table" for b in place):
            row.update(skip="tables", detail="넣을 자리에 양식 표 — 넣지 않음")
        elif hit := next((b for b in place if not (MF._blank(b) or MF._placeholder(b) or (b.get("text") or "").lstrip().startswith("※"))), None):
            row.update(skip="occupied", detail=P._ws(hit.get("text"))[:P.TEXT_MAX] or "그림")
        else:
            row["placeholders"] = [b["id"] for b in place if MF._placeholder(b)]

    fkeys = _labels(F)   # 4. 라벨 내용 — 제목(과 조상 사슬)이 같은 라벨: 칸 안은 짝지은 칸끼리, 칸 밖은 두 문서에서 하나씩
    for key, ts in _labels(T).items():
        fs = fkeys.get(key) or ()
        if key[0] == "cell":
            hits = [(t, f) for t in ts for f in fs if (_cell_of(t), _cell_of(f)) in paired]
            if len(hits) != 1 or sum(_cell_of(x) == _cell_of(hits[0][0]) for x in ts) != 1 or sum(_cell_of(x) == _cell_of(hits[0][1]) for x in fs) != 1:
                continue   # 짝지은 칸끼리가 아니거나 그 칸에 같은 제목이 둘
            t, f = hits[0]
        elif len(ts) == 1 and len(fs) == 1:
            t, f = ts[0], fs[0]
        else:
            continue
        put(t, f["id"], _slot(F, f["id"]), key[0] == "cell")
    # 4-1. 머리 이름과 같은 라벨(2026-11-22 사용자 "요약문의 최종목표가 들어가 있지 않았어" — 실제 이관 7cfb2957f487): 짝지은 칸 쌍에서 목적 칸에는 그 칸의 머리 이름과 같은 제목의 라벨이 있는데
    #      (「최종 목표」 칸의 「[최종목표]」 — 그 아래 「[N차년도 목표]」 는 구분 기준 자리) 원본 칸에는 라벨 없이 내용만 있으면, 원본 칸의 내용 전체가 그 라벨의 내용이다.
    #      위 4 는 두 문서에 같은 제목의 라벨이 있을 때만 잇고 3 은 라벨 줄이 든 칸을 건너뛰어, 이 꼴은 어느 길도 안 넣었다(빈 자리 검토도 칸 안 라벨 줄은 안 묻는다).
    done = {r["to"] for r in labels}
    nodes_in = {id(S): defaultdict(list) for S in (T, F)}
    for S in (T, F):
        for n in S["nodes"]:
            if n["id"] in S["heads"] and n["id"] in S["idx"] and (cid := _cell_of(n)):
                nodes_in[id(S)][cid].append(n)
    tcell = {c["id"]: c for t in T["tables"] for c in t["cells"]}
    word = lambda i: "".join(_WORD.findall(_FOOT.sub("", _text(T, i))))  # noqa: E731 — 머리 칸의 이름(위첨자 각주 번호 「14)」 는 뗀다)
    for cid, sid in sorted(paired):
        rec = tcell.get(cid) or {}
        names = {word(p[-1]) for p in (rec.get("rowPath") or (), rec.get("colPath") or ()) if p} - {""}
        hits = [n for n in nodes_in[id(T)].get(cid, ()) if n["id"] not in T["cov"] and _title(n) in names]
        if len(hits) != 1 or hits[0]["id"] in done:
            continue   # 머리 이름과 같은 라벨이 없거나 둘 · 위 4 가 이미 다룬 라벨
        if any(n.get("role") != "heading" or n["id"] in F["cov"] or _title(n) in names for n in nodes_in[id(F)].get(sid, ())):
            continue   # 원본 칸에 라벨 · 소제목 · 구분 기준 자리가 있다 — 칸 전체가 그 라벨 하나의 내용이 아니다(개요 줄 「o」·「-」 뿐인 칸만)
        put(hits[0], sid, (F["idx"].get(sid) or {}).get("blocks") or (), True)
    # 4-2. 합쳐 적은 라벨(2026-11-23 사용자(요약문 「[연구개발성과의 활용방안 및 기대효과]」 가 빈 것을 보이며) "이거 왜 ... 작성안되었나?"): 짝지은 칸 쌍에서 목적 라벨의 제목이 「A 및 B」 이고
    #      원본 칸에 그 둘이 따로 선 라벨(「[연구개발성과의 활용방안]」 · 「[연구개발성과의 기대효과]」 — 뒤 것은 앞 것의 앞말 「연구개발성과의」 를 같이 쓴다)로 하나씩 있으면, 두 라벨의 내용을 문서 차례로 이어 넣는다
    #      (원본의 라벨 줄 자체는 안 옮긴다 — 목적 서식이 하나로 합쳐 적었다). 위 4 는 제목이 꼭 같은 라벨만 이어 이 꼴은 비어 있었다.
    done = {r["to"] for r in labels}
    order = {n["id"]: i for i, n in enumerate(F["nodes"])}
    subs = {n["id"] for n in F["nodes"] if n.get("role") in ("subtitle", "label")}

    def inside(nid):
        """칸 안 라벨의 내용 — 라벨 다음부터 그 칸의 다음 소제목 · 라벨 줄(「[…]」)이나 구분 기준 자리 앞까지. 개요 줄(「ㅇ」·「-」 — 그래프의 heading)은 그 라벨의 내용이라 끊지 않는다(_slot 은 다음 제목에서 끊는다 — 본문의 자리)."""
        seq = F["where"].get(nid) or ()
        k = next((i for i, b in enumerate(seq) if b["id"] == nid), None)
        out = []
        for b in seq[k + 1:] if k is not None else ():
            if b["id"] in subs or any(x["id"] in F["cov"] for x in core._under(b)):
                break
            if not b.get("captionOf"):
                out.append(b)
        return out
    for cid, sid in sorted(paired):
        fl = [n for n in nodes_in[id(F)].get(sid, ()) if n["id"] not in F["cov"]]
        for t in nodes_in[id(T)].get(cid, ()):
            if t["id"] in done or t["id"] in T["cov"]:
                continue
            parts = ["".join(_WORD.findall(x)) for x in _JOIN.split(t.get("text") or t.get("letter") or "")]
            if len(parts) < 2 or not all(len(x) >= 2 for x in parts):
                continue
            first, got = parts[0], []
            for k, part in enumerate(parts):
                hit = [n for n in fl if (_title(n) == part if not k else _title(n) == part or (_title(n).endswith(part) and len(_title(n)) > len(part) and first.startswith(_title(n)[:-len(part)])))]
                if len(hit) != 1 or hit[0] in got:
                    break
                got.append(hit[0])
            else:
                got.sort(key=lambda n: order[n["id"]])
                put(t, got[0]["id"], [b for n in got for b in inside(n["id"])], True)
    todo = [r for r in labels if r["skip"] is None]
    why = Counter(s["why"] for s in skipped)
    counts = {"tables": sum(t["status"] == "paired" for t in tables), "tablesAmbiguous": sum(t["status"] == "ambiguous" for t in tables),
              "tablesLlm": sum(t["status"] == "paired" and t["source"] == "llm" for t in tables),
              "scoped": sum(t["status"] == "paired" and any(v is not None for v in t["ctx"].values()) for t in tables),   # 기관·차년도 절 안에서 이은 표
              "tablesOpen": sum(t["status"] != "paired" and t["source"] == "script" and t["why"] != "outside" for t in tables),   # 스크립트가 같은 표를 못 정한 표 — LLM 검토 대상(후보가 없는 표도: LLM 이 원본 표를 모두 읽고 정한다 — review_tables · 「넣을 구성 선택」 밖의 표는 뺌)
              "cells": len(cells), "form": sum(c["mode"] == "form" for c in cells), "calc": sum(c["calc"] for c in cells),
              "labels": len(todo), "blocks": sum(r["blocks"] for r in todo), "pictures": sum(r["pictures"] for r in todo), "flow": sum(bool(t["flow"]) for t in tables),
              "skipped": {k: why.get(k, 0) for k in WHY}}
    return {"tables": tables, "cells": cells, "labels": labels, "skipped": skipped, "counts": counts, "todo": len(cells) + len(todo) + counts["flow"]}


def apply(to_doc, from_doc, plan):
    """계획을 목적 문서에(모듈 설명) → {"filled": 쓴 칸 수, "shaped", "labels": {items, blocks, placeholders, dropped}, "inserted": {목적 라벨: [새 블록 id]}, "fitted", "flowed",
    "applied": {목적 라벨: {from, hash}}, "dropped", "skipped"}."""
    done = MT.apply(to_doc, from_doc, {"cells": [c for c in plan["cells"] if c["mode"] == "empty"], "rows": []})
    filled, shaped, skipped = done["filled"], done.get("shaped", 0), list(done["skipped"])
    wrote = list(done.get("wrote") or ())   # 글을 쓴 (목적 칸, 원본 칸) — 실제로 쓴 것만(같은 양식 취합의 원장: spec_취합 ② §10-4)
    to_doc.blocks()   # 블록 id 는 읽을 때 붙는다(merge_tables.apply 와 같은 까닭)
    form = defaultdict(list)
    for c in plan["cells"]:
        if c["mode"] == "form":
            form[c["table"]].append(c)
    for tid, cs in form.items():
        now = {x["id"]: x.get("text") or "" for x in (to_doc.table_block(tid) or {}).get("cells") or ()}
        for c in cs:
            cur = now.get(c["to"])
            if cur is not None and P._ws(cur) == P._ws(c["text"]):
                continue
            if cur is None or P._ws(cur) != P._ws(c["was"]):
                skipped.append({"to": c["to"], "why": "occupied", "detail": "계획 뒤 목적 칸의 글이 바뀜"})
                continue
            try:
                to_doc.set_text(c["to"], c["text"])
                filled += 1
                wrote.append([c["to"], c.get("from")])
                if not c.get("inline"):   # 줄 안의 빈 자리에 값만 넣은 칸(merge_inline)은 서식의 글자 모양 그대로 둔다(서약 글 · 「(직인)」 이 원본 칸의 모양으로 바뀌지 않게)
                    shaped += MT._shape(to_doc, from_doc, c["to"], c["from"])   # 글자 모양(장평·자간·크기)도 — 빈 칸과 같은 길
            except ValueError as x:
                skipped.append({"to": c["to"], "why": "shape", "detail": str(x)})
    lab = MF.apply(to_doc, from_doc, {"items": plan["labels"]})
    fitted = sum(to_doc.fit_image(i) for ids in lab["inserted"].values() for i in ids)   # 넣은 그림이 칸보다 넓으면 칸 폭으로(원본 칸이 더 넓었다)
    flowed = sum(to_doc.fit_table_flow(t["to"], t["flow"]) for t in plan["tables"] if t.get("flow"))
    return {"filled": filled, "shaped": shaped, "labels": lab["counts"], "inserted": lab["inserted"], "fitted": fitted, "flowed": flowed, "applied": lab["applied"],
            "dropped": lab["dropped"], "skipped": skipped, "wrote": wrote}


REVIEW_HEADS, REVIEW_SRC_HEADS, REVIEW_HEAD_LEN = 24, 12, 20   # LLM 표 짝 검토 자료 — 표마다 싣는 머리 꼴 수(목적 표 · 원본 표: 원본은 문서의 표 전부라 줄인다) · 머리 꼴 하나의 글자 수
REVIEW_PATH, REVIEW_SRC_PATH, REVIEW_SRC_PATH_LEN = 4, 3, 40    # 소속 경로의 단계 수(목적 표 · 원본 표) · 원본 표 경로 한 단계의 글자 수


def review_tables(to_side, from_side, forced=None):
    """LLM 표 짝 검토(merge_llm.review 의 tables)에 보낼 자료 → {"targets": [...], "sources": [...], "open": 스크립트가 같은 표를 못 정한 목적 표 수}.
    **LLM 이 표를 모두 읽고 짝을 정한다**(2026-11-22 사용자 "테이블 매칭을 LLM이 모두 읽고 하길 바램" — spec_병합 ② §5-1 「표 짝 검토」. 전에는 후보(cands)가 있는 목적 표와 후보로 든 원본 표만
    보냈다: 후보 문턱(머리 꼴 3개 겹침 · 품음 0.4)에 못 든 표는 LLM 이 보지도 못했다).
    targets = **남는 칸이 있는 목적 표 전부**(forced 로 사람이 정한 표만 뺌): 스크립트가 못 정한 표(status none·ambiguous — 후보가 없어도 · 머리는 같은데 맥락이 다른 표 why 도) ·
      스크립트가 이은 표(status paired + paired = 그 원본 표 id — LLM 이 확인한다) · 머리 꼴이 둘 미만이라 표 짝 줄에 못 든 표(status none):
      {key(표 id), title, path(소속 제목 꼴, 바깥 → 안), ctx{org, year}, heads(머리 칸 꼴), shape{rows, cols, splits}, status, why, candidates[{key, score}](스크립트의 참고 — 비어 있을 수 있다), paired?}.
    sources = **원본 문서의 표 전부**(같은 꼴의 설명 — status·why·candidates 없음 + form = 머리 꼴·소속 제목 꼴이 같은 표끼리 같은 값 | None: 기관마다·차년도마다 되풀이되는 표를 merge_llm 이 한 줄로 묶어 보낸다).
    forced 에는 **사람이 정한 것만** 넘긴다 — 앞선 LLM 짝은 다시 검토 대상이 된다(다시 검토)."""
    forced = forced or {}
    T, F = _side(to_side), _side(from_side)

    def brief(S, side, t, heads, path=REVIEW_PATH, path_len=P.TEXT_MAX):
        cells = S["idx"][t["id"]].get("cells") or ()
        flow = side["doc"].table_flow(t["id"]) or {}
        own = t.get("owner") or {}
        return {"key": t["id"], "title": P._ws(_title_of(S, t))[:P.TEXT_MAX], "path": [p[:path_len] for p in (P._shape(x, S["org_names"]) for x in own.get("path") or ()) if p][-path:],
                "ctx": _ctx(S, t), "heads": [h[:REVIEW_HEAD_LEN] for h in sorted(_head_shapes(S, t))[:heads]],
                "shape": {"rows": max((c["row"] + c.get("rowSpan", 1) for c in cells), default=0), "cols": max((c["col"] + c.get("colSpan", 1) for c in cells), default=0),
                          "splits": bool(flow.get("splits"))}}

    def form(f):   # 같은 꼴 표의 열쇠 — 머리 꼴 묶음 + 소속 제목 꼴(기관 이름 뗌). 머리 꼴이 둘 미만이면 묶지 않는다
        s = sorted(_head_shapes(F, f))
        return hashlib.sha1(json.dumps([P._shape((f.get("owner") or {}).get("text") or "", F["org_names"]), s], ensure_ascii=False).encode("utf-8")).hexdigest()[:10] if len(s) >= 2 else None
    rows = {tp["to"]: tp for tp in _table_pairs(T, F, forced)}
    targets = []
    for t in T["tables"]:   # 문서 차례
        if t["id"] not in T["idx"] or t["id"] in forced:
            continue
        tp = rows.get(t["id"])
        if tp is None:   # 표 짝 줄에 못 든 표 — 남는 칸이 있는데 머리 꼴이 둘 미만인 표만 싣는다(남는 칸이 없는 표 · 넣을 것이 없는 절 안의 표는 물을 것이 없다)
            if _free(T, t) and len(_head_shapes(T, t)) < 2:
                targets.append({**brief(T, to_side, t, REVIEW_HEADS), "status": "none", "why": None, "candidates": []})
            continue
        if tp["source"] != "script":
            continue
        targets.append({**brief(T, to_side, t, REVIEW_HEADS), "status": tp["status"], "why": tp["why"], "candidates": [{"key": c["from"], "score": c["score"]} for c in tp["cands"]],
                        **({"paired": tp["from"]} if tp["status"] == "paired" else {})})
    sources = [{**brief(F, from_side, f, REVIEW_SRC_HEADS, REVIEW_SRC_PATH, REVIEW_SRC_PATH_LEN), "form": form(f)} for f in F["tables"] if f["id"] in F["idx"]]
    return {"targets": targets, "sources": sources, "open": sum(t["status"] != "paired" for t in targets)}


def pairs(to_side, from_side, forced=None):
    """같은 이름 자리의 **짝만**(넣을 것은 안 셈) → ([(목적 표 id, 원본 표 id)], [(목적 칸 id, 원본 칸 id)]) — 원본 자리 지도(merge_origins, spec_작업 ② §12 「누른 자리 따라 보기」)용.
    plan 의 표 짝·칸 짝과 같은 규칙이되 **넣은 뒤에도 같은 짝이 나오게** 본다(full): 빈 칸이 없어 넣을 것이 없는 표 · 체크를 이미 옮긴 문서 제목 줄의 칸도 든다. 문서를 안 고친다."""
    T, F = _side(to_side), _side(from_side)
    ttabs, ftabs = {t["id"]: t for t in T["tables"]}, {f["id"]: f for f in F["tables"]}
    tables, cells = [], []
    for tp in _table_pairs(T, F, forced, full=True):
        if tp["status"] != "paired":
            continue
        tables.append((tp["to"], tp["from"]))
        got, _ = _cell_pairs(tp["free"], _free(F, ftabs[tp["from"]]), lambda i: _text(T, i), lambda i: _text(F, i),
                             _head_shapes(T, ttabs[tp["to"]]), _head_shapes(F, ftabs[tp["from"]]), full=True)
        cells += [(c["id"], s["id"]) for c, s in got]
    return tables, cells

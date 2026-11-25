"""자리마다의 작성 지침 — 헤딩 · 표 하나에 붙은 지침을 한 기준으로 고른다(spec_병합 ② §5-11 「자리마다의 작성 지침」 — 2026-11-23 사용자 "3단계에서 문서나 사용자가
각 헤딩 및 테이블에 들어갈 작성요령이 이 단계에서 저장되고 관리되고 그리고 에이전트가 표 대응 및 내용을 반영할 때 이를 고려하는지 검토하고 그게 들어 가게 해줘" · astra 협의).
순수 계산 — 저장 · 끝점은 `app/place_guides_api.py`. 3단계의 LLM 셋(자리 연결 · 표 대응 · 빈 자리 검토)과 화면 「지침」 단추가 **이 모듈 하나로** 그 자리의 지침을 고른다.

- 원천 둘: **문서**(`form_guides` 저장본 — 작성 요령 표 · <참고 N> · ※ 안내 · 각주 번호가 가리키는 작성 요령 항목) · **사용자**(헤딩 = 작업 폴더 `guides_user.json` · 표 = 표 지침 `table_agent` 의 「이 표」 instructions).
  양식 전체가 같이 쓰는 매칭 지침(`link_guides` — 「어떻게 잇나」)은 여기 들지 않는다(쓰임이 다르고 공유 범위가 다르다 — 부르는 쪽이 따로 싣는다).
- 표 = 지침이 든 블록(`at`)을 품은 **가장 안쪽의 3단계 표**(겉표 t1 의 칸 안 안쪽 표 t3 의 지침은 t3 것). `at` 이 3단계 표 밖이면 저장본이 붙인 표(본문 ※ 의 바로 다음 · 앞 표)가
  3단계 표일 때 그 표, 그 표 안의 3단계 표가 꼭 하나면 그 표 — 아니면 표에 붙이지 않고 그 헤딩의 것(어느 안쪽 표인지 짐작하지 않는다).
- 헤딩 = 저장본이 붙인 가장 가까운 앞 본문 헤딩(글 있는 것 — 글 없는 글머리 줄은 건너뜀). 자리의 지침을 고를 때는 그 헤딩의 것 다음에 **윗 헤딩(그래프의 조상)의 것**이 이어진다
  (2026-11-24 — 전에는 물려주지 않아 장 · 절 제목의 지침이 그 아래 표 · 하위 제목에 안 닿았다. 조상만이다 — 형제 절 · 다른 차년도의 절로는 안 간다).
- 표 구조(`struct` — src "struct"): 1단계 표 판정의 한 줄 요약 · 단위 · 칸의 괄호 안내(「(천원)」 · 「(YY.MM.DD)」)를 그 표의 지침 하나로 — LLM 에 싣는 목록에만(화면의 수 · 판에는 안 든다).
- `pack` = 한 자리의 목록을 자른다(항목 ITEM_MAX · 자리 PLACE_MAX — 앞의 것부터: 칸 · 표의 것 → 헤딩의 것, 같은 글은 하나) → (목록, 자른 수). `sig` = 그 목록의 판(답을 저장할 때 함께 — 지침이 바뀐 자리만 다시 묻는다).
- 지침은 **판단 자료**다 — 넣을 사실 · 수는 원본의 실제 내용에서만(계약의 한 줄 `CONTRACT_LINE`). 스크립트(같은 이름 자리 · 표 묶음 · 일정 표 · 통째 복사 · 「내용 반영」)의 동작은 이 글로 바뀌지 않는다."""
import hashlib
import json
import re
from collections import Counter

from app.headings import iter_blocks

ITEM_MAX, PLACE_MAX, CALL_MAX = 2000, 6000, 24000   # 지침 하나 · 한 자리 · 한 호출의 글자 수(2026-11-24 넓힘 — 실제 실행에서 글 있는 지침 111건 가운데 한도로 15건이 안 실렸다: 전에는 1,200 · 4,000 · 12,000)
USER_MAX = 4000   # 사람이 적는 헤딩 지침 하나
KIND_USER = "사용자 지침"
KIND_TABLE_USER = "표 지침(이 표)"
KIND_STRUCT = "표 구조"   # 그 표의 구조가 곧 지침인 것(src "struct" — 1단계 표 판정의 한 줄 요약 · 단위 · 칸의 꼴 「(천원)」 · 「(YY.MM.DD)」). 판(sig)에 넣지 않는다 — 표 자체에서 읽은 것이라 지침이 바뀐 것이 아니다
_UNIT1 = r"(?<![가-힣])(?:원|명|건|개|개월|년|월|일)(?![가-힣])"
FIELD = re.compile(r"[\(（][^()（）]{0,20}(?:단위|천\s*원|백만\s*원|억\s*원|%|M/M|YY|yy|○\s*/\s*×|해당\s*시|이내|작성|기재|기입|선택|표기|예시|" + _UNIT1 + r")[^()（）]{0,20}[\)）]")   # 칸 글 안의 괄호 안내 — 단위 · 날짜 꼴 · 조건
FIELD_CELL, FIELD_MAX = 40, 8   # 그런 괄호가 든 짧은 칸만(머리 칸 · 라벨 칸) · 표 하나에 싣는 수
CONTRACT_LINE = ("\n\n### 자리마다의 작성 지침(guides)\n자료의 `guides` = 그 자리(헤딩 · 표)에 무엇을 쓰는지 양식(src \"doc\")이나 사람(src \"user\")이 정한 글입니다. "
                 "짝 · 칸 · 자리를 고를 때 근거로 쓰되, 넣을 사실 · 수 · 이름은 원본의 실제 내용에서만 가져옵니다(지침에 적힌 예시 · 수를 옮기지 않습니다). "
                 "지침이 그 자리에 넣지 말라는 내용(다른 차년도 · 다른 기관 · 계획 대신 실적 등)은 짝으로 고르지 않습니다. "
                 "지침은 그 자리의 것이 먼저이고 그 뒤에 윗 절(윗 제목)의 것이 이어집니다. src \"struct\"(「표 구조」) = 그 표의 구조에서 읽은 것(무엇을 적는 표인지 · 단위 · 칸의 꼴)입니다. "
                 "지침이 따로 없어도 **제목 글과 표의 머리글 자체가 지침**입니다 — 제목 · 머리글의 괄호 안내(「(해당 시 작성)」 · 「(천원)」 · 「(YY.MM.DD)」 · 「(5개 이내)」)와 머리 행 · 머리 열의 짜임이 그 자리에 무엇을 어떤 꼴로 쓰는지를 정합니다.")


def _cut(text, n):
    t = (text or "").strip()
    return t if len(t) <= n else t[:n - 1] + "…"


def _one(text, n=80):
    return " ".join((text or "").split())[:n]


def owners(blocks, cells=None):
    """블록 id → 그 블록을 품은 표의 사슬 [바깥 … 안쪽 표 id](본문 최상위 블록이면 []) — 칸 id 도 품은 표의 사슬로.
    cells = 채울 dict 를 주면 {블록 id: (그 블록을 바로 품은 칸의 표 id, "r{행}c{열}")} 도 채운다(칸 자신은 그 칸으로)."""
    out = {}

    def walk(seq, chain, here):
        for b in seq:
            out.setdefault(b["id"], list(chain))
            if cells is not None and here is not None:
                cells.setdefault(b["id"], here)
            if b.get("type") == "table":
                inner = [*chain, b["id"]]
                for c in b.get("cells") or ():
                    out.setdefault(c["id"], inner)
                    at = (b["id"], f"r{c.get('row', 0)}c{c.get('col', 0)}")
                    if cells is not None:
                        cells.setdefault(c["id"], at)
                    walk(c.get("blocks") or (), inner, at)
    walk(blocks or (), [], None)
    return out


def _inside(blocks):
    """표 id → 그 표 안(칸 안 어디든)의 표 id 모음."""
    out = {}
    for b in iter_blocks(blocks or ()):
        if b.get("type") == "table":
            out[b["id"]] = {x["id"] for x in iter_blocks([b]) if x.get("type") == "table" and x["id"] != b["id"]}
    return out


LOOSE = "-"   # _table_of 의 「표 자리인데 어느 3단계 표인지 못 정함」 — 미연결(헤딩으로도 넘기지 않는다: astra 2차 G1)


def _table_of(at, near, own, inside, t3):
    """지침 하나가 붙을 3단계 표 id | LOOSE(표의 지침인데 어느 3단계 표인지 못 정함 — 미연결) | None(표의 지침이 아님 — 헤딩의 것) — 모듈 설명 「표」.
    ① at 을 품은 가장 안쪽의 3단계 표 ② at 이 3단계 표가 아닌 겉표의 칸에 바로 있으면 그 겉표 안의 3단계 표가 꼭 하나일 때 그 표(표까지만 — 칸은 안 붙임) · 아니면 미연결
    ③ 본문 블록인데 저장본이 표에 붙였으면(※ 의 바로 다음 · 앞 표) 그 표가 3단계 표일 때만 그 표 · 아니면 미연결(겉표 옆 ※ 를 안쪽 표로 짐작하지 않는다)."""
    chain = own.get(at) or []
    hit = next((t for t in reversed(chain) if t in t3), None)
    if hit:
        return hit
    if chain:
        inner = [t for t in inside.get(chain[-1], ()) if t in t3]
        return inner[0] if len(inner) == 1 else LOOSE
    if near:
        return near if near in t3 else LOOSE
    return None


def struct(blocks, t3_tables):
    """3단계 표마다 그 표의 구조에서 읽은 지침 하나 {표 id: {src "struct", kind, text}} — 1단계 표 판정의 한 줄 요약(`llm.summary`) · 단위(`unit`) · 칸의 꼴(그 표의 짧은 칸에 든 괄호 안내 — FIELD).
    2026-11-24 사용자 "테이블 구조의 헤더/열 구조 필드 종류/서식등이 지침이 될 수도 있지?" — 전에는 1단계가 읽은 요약 · 단위가 3단계 LLM 에 가지 않았다. 스크립트만 · 읽을 것이 없는 표는 안 든다."""
    by = {b["id"]: b for b in iter_blocks(blocks or ()) if b.get("type") == "table"}
    out = {}
    for t in t3_tables or ():
        if not isinstance(t, dict) or not t.get("id"):
            continue
        parts = []
        llm = t.get("llm") if isinstance(t.get("llm"), dict) else {}
        if _one(llm.get("summary"), 200):
            parts.append(_one(llm.get("summary"), 200))
        if t.get("unit"):
            parts.append(f"단위: {_one(str(t['unit']), 20)}")
        fields = []
        for c in (by.get(t["id"]) or {}).get("cells") or ():
            text = _one(" ".join(b.get("text") or "" for b in c.get("blocks") or () if b.get("type") == "paragraph"), FIELD_CELL + 1)
            if text and len(text) <= FIELD_CELL and FIELD.search(text) and text not in fields:
                fields.append(text)
        if fields:
            parts.append("칸의 꼴: " + " · ".join(fields[:FIELD_MAX]))
        if parts:
            out[t["id"]] = {"src": "struct", "kind": KIND_STRUCT, "text": " / ".join(parts)}
    return out


def index(saved, blocks, t3_ids, user=None, table_user=None, t3_tables=None):
    """저장본 + 사용자 지침 → {"tables": {표 id: [지침…]}, "heads": {헤딩 문단 id: [지침…]}, "loose": 어디에도 못 붙인 수, "heads_text": {헤딩 id: 글}, "struct": {표 id: 표 구조 지침}}.
    t3_tables = 3단계 결과의 표 목록(heading_runs.tables 의 `tables` — 주면 표 구조 지침 `struct` 를 짓는다 · 화면의 수(`tables`)에는 안 든다 — LLM 에 싣는 목록(`for_table`)에만).
    saved = form_guides 저장본(form_guides_api.load 꼴) | None · blocks = 지금 문서의 블록 · t3_ids = 3단계 표 id 들 ·
    user = guides_user.json 꼴 {heads{헤딩 id: {text, label}}} | None · table_user = {표 id: 「이 표」 지침 글}(table_agent own instructions).
    지침 = {src, kind, text, label?(각주 번호가 든 칸 · 줄의 글)}."""
    cell_of = {}
    own, inside, t3 = owners(blocks, cell_of), _inside(blocks), set(t3_ids or ())
    tables, heads, loose, names = {}, {}, 0, {}
    rows = [(x, False) for x in (saved or {}).get("items") or () if isinstance(x, dict)]
    rows += [(m, True) for m in (saved or {}).get("marks") or () if isinstance(m, dict) and (m.get("text") or "").strip()]
    for x, mark in sorted(rows, key=lambda r: (r[0].get("top", 0), r[1])):
        text = (x.get("text") or "").strip()
        if not text:
            continue
        at = x.get("at") if mark else x.get("id")
        if mark:
            g = {"src": "doc", "kind": f"각주 번호 {x.get('no')})", "label": _one(x.get("label"), 60), "text": _cut(text, ITEM_MAX)}
        else:
            g = {"src": "doc", "kind": x.get("name") or x.get("kind") or "", "text": _cut(text, ITEM_MAX)}
        t = x.get("table") if isinstance(x.get("table"), dict) else {}
        h = x.get("heading") if isinstance(x.get("heading"), dict) else {}
        pl = x.get("place") if isinstance(x.get("place"), dict) else None
        if at not in own and pl is not None:   # 지침 블록이 문서에서 사라졌다(「작성요령 삭제」) — 모은 때 정한 자리로(form_guides._places_of)
            tid = LOOSE if pl.get("loose") else (pl.get("table") if pl.get("table") in t3 else LOOSE)
            if tid != LOOSE and pl.get("cell"):
                g["cell"] = pl["cell"]
        else:
            tid = _table_of(at, t.get("id"), own, inside, t3) if (t.get("id") or own.get(at)) else None
            c = cell_of.get(at)
            if tid and tid != LOOSE and c and c[0] == tid:   # 그 표의 칸에 바로 든 지침(머리 칸의 각주 번호 등) — 어느 칸인지 격자의 「r행c열」 로
                g["cell"] = c[1]
        if tid == LOOSE:
            loose += 1
        elif tid:
            tables.setdefault(tid, []).append(g)
        elif h.get("id"):
            heads.setdefault(h["id"], []).append(g)
            names.setdefault(h["id"], h.get("text") or "")
        else:
            loose += 1
    for hid, u in ((user or {}).get("heads") or {}).items():
        if isinstance(u, dict) and (u.get("text") or "").strip():
            heads.setdefault(hid, []).insert(0, {"src": "user", "kind": KIND_USER, "text": _cut(u["text"], ITEM_MAX)})   # 사람의 것이 앞(자를 때 남는다)
            names.setdefault(hid, u.get("label") or "")
    for tid, text in (table_user or {}).items():
        if (text or "").strip():
            tables.setdefault(tid, []).insert(0, {"src": "user", "kind": KIND_TABLE_USER, "text": _cut(text, ITEM_MAX)})
    return {"tables": tables, "heads": heads, "loose": loose, "heads_text": names, "t3": sorted(t3), "struct": struct(blocks, t3_tables) if t3_tables else {}}


def _head(n):
    """지침이 붙는 헤딩 노드인가 — 본문 헤딩 줄 · 글 있는 것(글 없는 글머리 「o」·「-」·「⋅」 = 양식의 빈 쓸 자리는 헤딩으로 세지 않는다: form_guides._headings 와 같은 규칙 — 2026-11-24)."""
    return isinstance(n, dict) and n.get("role") == "heading" and n.get("area") == "body" and bool(n.get("para")) and not n.get("blank")


def ancestors(graph):
    """헤딩 문단 id → 윗 헤딩들의 문단 id [가까운 것부터](그래프의 parent 사슬 — 라벨 · 상자 같은 노드는 지나가고 `_head` 인 것만).
    그 절의 지침은 그 아래 자리(하위 제목 · 기관마다 되풀이된 표)에도 닿는다 — 윗 **조상**만이다(형제 절 · 다른 차년도의 절로는 안 간다)."""
    by = {n["id"]: n for n in (graph or {}).get("nodes") or () if isinstance(n, dict) and n.get("id")}
    out = {}
    for n in by.values():
        if not _head(n):
            continue
        ups, seen, p = [], {n["id"]}, by.get(n.get("parent"))
        while p is not None and p["id"] not in seen:
            seen.add(p["id"])
            if _head(p):
                ups.append(p["para"])
            p = by.get(p.get("parent"))
        out[n["para"]] = ups
    return out


def heading_finder(blocks, graph):
    """블록 id → 그 블록의 헤딩(문서 차례로 바로 앞의 본문 헤딩 줄 — 그 줄 자신이 헤딩이면 그 줄 · 글 없는 글머리 줄은 건너뜀) | None. 저장본이 지침에 헤딩을 붙인 규칙(form_guides.collect)과 같다 —
    표 칸 안의 블록은 그 표의 최상위 자리로 센다."""
    top = {}
    for i, b in enumerate(blocks or ()):
        for x in iter_blocks([b]):
            top.setdefault(x["id"], i)
    heads = sorted({(top[n["para"]], n["para"]) for n in (graph or {}).get("nodes") or () if _head(n) and n.get("para") in top})

    def find(bid):
        i = top.get(bid)
        if i is None:
            return None
        hit = None
        for hi, pid in heads:
            if hi < i or (hi == i and pid == bid):
                hit = pid
            elif hi > i:
                break
        return hit
    return find


def resolver(ix, blocks, graph):
    """3단계 LLM 셋이 쓰는 자리 → 지침 함수 `place(kind, x)` → 지침 목록(pack 한 것 — 빈 목록이면 지침 없음).
    kind "table" = 목적 표 id · "group" = 묶음 요약(merge_pairs.summarize — 표 묶음은 그 표, 문단 묶음은 **항목마다**(라벨 id → 헤딩) 구한 지침 가운데 모두에게 있는 것만) ·
    "block" = 블록 id(빈 자리의 라벨 줄 · 칸 — 그 블록이 든 3단계 표가 있으면 그 표, 아니면 그 헤딩)."""
    find = heading_finder(blocks, graph)
    ups = ancestors(graph)
    own = owners(blocks)
    t3 = set((ix or {}).get("t3") or ()) | set((ix or {}).get("tables") or ())   # 3단계 표 모두 — 가장 가까운 3단계 표에서 멈춘다(그 표에 지침이 없어도 겉표로 올라가지 않는다: astra 3차)

    def heads(bid):
        """그 블록의 헤딩 + 윗 헤딩들(가까운 것부터) — 2026-11-24: 전에는 바로 앞 헤딩 하나뿐이라 장 · 절 제목에 붙은 지침 13건이 어느 호출에도 안 실렸다(실제 실행 — spec_병합 ② §5-11 7)."""
        h = find(bid)
        return [h, *ups.get(h, ())] if h else []

    def table(tid):
        return for_table(ix, tid, heads(tid))[0]

    def block(bid):
        tid = next((t for t in reversed(own.get(bid) or []) if t in t3), None)
        return table(tid) if tid else for_heading(ix, heads(bid))[0]

    def place(kind, x):
        if not ix:
            return []
        if kind == "table":
            return table(x)
        if kind == "block":
            return block(x)
        tid = (x.get("table") or {}).get("id")
        if tid:
            return table(tid)
        return common([block(it["id"]) for it in x.get("items") or () if it.get("id")])   # 항목마다 그 라벨 블록의 자리(칸 라벨이면 그 표의 지침도 — 「block」 과 같은 해석: astra 3차)
    return place


def pack(*lists, limit=PLACE_MAX):
    """자리 하나의 지침 목록들(앞의 것이 먼저) → (합친 목록, 자른 수). 같은 (kind, text, label) 은 하나 · 글자 합이 limit 을 넘으면 뒤의 것을 뺀다."""
    out, seen, n, cut = [], set(), 0, 0
    for lst in lists:
        for g in lst or ():
            k = (g.get("kind"), g.get("text"), g.get("label") or "", g.get("cell") or "")   # 같은 번호 · 같은 항목이라도 다른 칸의 각주는 따로(어느 칸의 지침인지가 다르다)
            if k in seen:
                continue
            seen.add(k)
            size = len(g.get("text") or "") + len(g.get("label") or "")
            if n + size > limit:
                cut += 1
                continue
            n += size
            out.append(g)
    return out, cut


def _heads(ix, head):
    """head = 헤딩 id 하나 | [그 헤딩, 윗 헤딩 …](가까운 것부터) | None → 그 헤딩들의 지침 목록들(차례대로)."""
    ids = [head] if isinstance(head, str) else list(head or ())
    return [(ix or {}).get("heads", {}).get(h) for h in ids if h]


def for_table(ix, tid, head=None):
    """표 tid 의 지침 — 그 표의 것 → 그 표의 구조에서 읽은 것(struct) → 그 표가 든 헤딩의 것 → 윗 헤딩들의 것(head 가 목록일 때 — 가까운 것부터) → (목록, 자른 수)."""
    st = (ix or {}).get("struct", {}).get(tid)
    return pack((ix or {}).get("tables", {}).get(tid), [st] if st else None, *_heads(ix, head))


def for_heading(ix, hid):
    """헤딩 hid 의 지침(헤딩에만 붙은 것 — 그 절의 표 지침은 표의 것) → 윗 헤딩들의 것(hid 가 목록일 때 — 가까운 것부터) → (목록, 자른 수)."""
    return pack(*_heads(ix, hid))


def common(lists):
    """여러 항목(같은 묶음의 기관 · 차년도마다)의 지침 목록 → 모두에게 있는 것만(차례는 첫 목록의 것). 하나뿐이면 그것."""
    lists = [x or [] for x in lists]
    if not lists:
        return []
    keys = [{(g.get("kind"), g.get("text")) for g in x} for x in lists[1:]]
    return [g for g in lists[0] if all((g.get("kind"), g.get("text")) in k for k in keys)]


def sig(guides):
    """지침 목록의 판(12자) — 빈 목록은 ""(지침이 없는 자리는 판이 없다: 처음 지침이 붙으면 다시 묻는다). 표 구조에서 읽은 것(src "struct")은 판에 넣지 않는다."""
    guides = [g for g in guides or () if g.get("src") != "struct"]
    if not guides:
        return ""
    raw = json.dumps([[g.get("src"), g.get("kind"), g.get("label") or "", g.get("cell") or "", g.get("text")] for g in guides], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def budget(places, limit=CALL_MAX):
    """한 호출의 자리들 [{…, "guides": [...]}] — 글자 합이 limit 을 넘으면 뒤 자리의 지침부터 뺀다(자리 안에서는 뒤의 것부터) → 뺀 지침 수. places 를 고친다.
    **같은 지침은 한 번만 센다**(2026-11-24 — 실제 실행: 표지 표의 지침 25건이 그 표와 그 안의 묶음 둘에 똑같이 실려 한도의 대부분을 쓰고 요약문 표의 각주 13건이 밀려났다). 되풀이된 것을 빼도 합은 안 준다."""
    key = lambda g: (g.get("kind"), g.get("text"), g.get("label") or "", g.get("cell") or "")  # noqa: E731
    seen = Counter(key(g) for p in places for g in p.get("guides") or ())
    total = sum(len(k[1] or "") for k in seen)
    cut = 0
    for p in reversed(places):
        while total > limit and p.get("guides"):
            g = p["guides"].pop()
            seen[key(g)] -= 1
            if not seen[key(g)]:
                total -= len(g.get("text") or "")
            cut += 1
            p["guidesCut"] = p.get("guidesCut", 0) + 1
        if not p.get("guides"):
            p.pop("guides", None)
    return cut


def user_put(data, hid, text, label="", at=0.0):
    """사용자 헤딩 지침 하나를 적거나(text) 지운(빈 글) 새 저장본 — ValueError(너무 긺)."""
    t = (text or "").replace("\r\n", "\n").strip()
    if len(t) > USER_MAX:
        raise ValueError(f"지침은 {USER_MAX:,}자까지입니다(지금 {len(t):,}자)")
    heads = dict((data or {}).get("heads") or {})
    if t:
        heads[hid] = {"text": t, "label": _one(label, 120), "at": at}
    else:
        heads.pop(hid, None)
    return {"version": int((data or {}).get("version") or 0) + 1, "heads": heads}


# ---- 한 자리에 닿는 지침의 사슬 — 줄 · 윗 줄 · 칸 · 상자/표 · 절 · 윗 절 -------------------------------------------------------------------
# 2026-11-25 사용자(상자 안 「공동(기업명 작성) :」 아래 줄들을 보며) "여기서 하나의 셋트라고 해야하나... 헤딩마다 작성 지침이 있을거 아냐? 1. 1.1 1.1.1. 이렇면 1.1.1 도 작성 지침이 있고
# 1.1 도 하위 내용에 대한 작성지침이 있고? 있다면, 목적문서에서 이걸 확인할 수 있는 아이콘을 제공했으면 좋겠어" · "테이블 필드도 마찬가지로".
# 화면이 보이는 것만이다(읽기만) — 3단계 LLM 이 읽는 목록(resolver)은 바꾸지 않는다. 원천: 문서 · 사람의 지침(index) + 작성 지침 보완(26 — writing_guidance 의 rules: 자리 id 마다,
# 글이 「p48 줄은 …」 · 「p50~p54 에는 …」 처럼 줄을 가리키면 그 줄의 것) + 양식 검토(25)의 자리마다 작성 방향(how). 층을 나누는 법은 에이전트 판단(사용자 확인 전).
_IDS = re.compile(r"(?<![A-Za-z0-9])([pt])(\d+)(?:\s*[~∼\-–]\s*[pt]?(\d+))?(?![A-Za-z0-9])")
KIND_RULE, KIND_HOW = "작성 지침 보완", "양식 검토 — 작성 방향"


def mentions(text):
    """글이 가리키는 블록 id 모음(「p48」 · 「p50~p54」 · 「t44」 — 범위는 60 까지만 편다)."""
    out = set()
    for m in _IDS.finditer(text or ""):
        a = int(m.group(2))
        b = int(m.group(3)) if m.group(3) else a
        if b < a or b - a > 60:
            b = a
        out.update(f"{m.group(1)}{i}" for i in range(a, b + 1))
    return out


def _rule_item(r):
    return {"src": "guidance", "kind": KIND_RULE + (" · 양식 명시" if r.get("basis") == "explicit" else " · 예시에서" if r.get("basis") == "example" else ""),
            "text": _cut(r.get("instruction") or "", ITEM_MAX)}


def chain(ix, blocks, graph, bid, rules=None, hows=None, owner=None):
    """블록 bid(문단 · 칸 안 문단 · 칸)에 닿는 지침을 가까운 층부터 [{key, title, at, items[{src, kind, text, label?}]}] — 빈 층은 뺀다.
    key = line(이 줄) · up(윗 줄 — 상자 · 칸 안의 부모 줄, 그래프의 parent) · cell(이 칸) · table(상자 · 표) · head(절 — 그 줄의 헤딩과 윗 헤딩).
    rules = {자리 id: [작성 지침 보완 규칙…]} · hows = {자리 id: 양식 검토의 작성 방향} · owner = {표 id: 그 표를 품은 양식 작성의 자리 id}(헤딩 자리 「p5」 가 표 「t6」 을 품는 등)."""
    ix, rules, hows, owner = ix or {}, rules or {}, hows or {}, owner or {}
    cells = {}
    own = owners(blocks, cells)
    by_para = {n.get("para"): n for n in (graph or {}).get("nodes") or () if isinstance(n, dict) and n.get("para")}
    by_id = {n["id"]: n for n in by_para.values() if n.get("id")}
    tchain = own.get(bid) or []
    top = tchain[0] if tchain else None
    t3 = set(ix.get("t3") or ()) | set(ix.get("tables") or ())
    tid = next((t for t in reversed(tchain) if t in t3), None) or (tchain[-1] if tchain else None)
    blk = {b["id"]: b for b in iter_blocks(blocks or ())}
    text = lambda pid: _one((blk.get(pid) or {}).get("text") or (by_para.get(pid) or {}).get("text") or "", 40)
    # 윗 줄 — 상자 · 칸 안에서 그래프의 parent 를 따라 같은 표 안에 있는 것만(본문 헤딩에 닿으면 멈춤 — 그것은 절의 층)
    ups, seen, n = [], {bid}, by_para.get(bid)
    p = by_id.get((n or {}).get("parent"))
    while p is not None and p.get("para") not in seen and tchain and top in (own.get(p.get("para")) or []):
        seen.add(p["para"])
        if not p.get("blank"):
            ups.append(p["para"])
        p = by_id.get(p.get("parent"))
    # 작성 지침 보완 · 양식 검토 — 그 자리(이 블록 자신 · 품은 표들)의 것을 가리키는 줄마다 나눈다
    hit = {bid: [], **{u: [] for u in ups}}
    rest = []
    places = list(dict.fromkeys([bid, *tchain, *(owner[t] for t in tchain if owner.get(t))]))
    whole = set(places) - {bid}   # 표 · 그 표를 품은 자리 — 이것만 가리키는 규칙은 그 표 전체의 것
    for place in places:
        for r in rules.get(place) or ():
            if not isinstance(r, dict) or not (r.get("instruction") or "").strip():
                continue
            ids = mentions(r["instruction"]) - {place} - whole
            if place == bid or not ids:
                (hit[bid] if place == bid else rest).append(_rule_item(r))
                continue
            for k in [*reversed(ups), bid]:   # 윗 줄과 그 아래 줄을 함께 가리키면 그 묶음(셋트)의 지침 — 가장 위 줄의 것으로
                if k in ids:
                    hit[k].append(_rule_item(r))
                    break
    layers = []

    def add(key, title, at, *lists, keep=False):   # keep = 비어도 세운다(이 줄 · 윗 줄 — 묶음의 짜임이 보이게)
        items, _ = pack(*lists, limit=PLACE_MAX * 2)
        if items or keep:
            layers.append({"key": key, "title": title, "at": at, "items": items})
    add("line", "이 줄", bid, (ix.get("heads") or {}).get(bid), hit[bid],
        [{"src": "review", "kind": KIND_HOW, "text": _cut(hows[bid], ITEM_MAX)}] if hows.get(bid) else None, keep=True)
    for u in ups:
        add("up", f"윗 줄 「{text(u)}」" if text(u) else "윗 줄", u, (ix.get("heads") or {}).get(u), hit[u], keep=True)
    if tid:
        tg = (ix.get("tables") or {}).get(tid) or []
        at_cell = cells.get(bid)
        rc = at_cell[1] if at_cell and at_cell[0] == tid else None
        if rc:
            add("cell", f"이 칸({rc})", bid, [g for g in tg if g.get("cell") == rc])
        st = (ix.get("struct") or {}).get(tid)
        tb = blk.get(top) or {}
        box = len(tb.get("cells") or ()) == 1
        add("table", "이 상자" if box else "이 표", top, [g for g in tg if not g.get("cell")], [st] if st else None, rest,
            [{"src": "review", "kind": KIND_HOW, "text": _cut(hows[k], ITEM_MAX)} for k in whole if hows.get(k)])
    find, anc = heading_finder(blocks, graph), ancestors(graph)
    h = find(top or bid)
    for i, hp in enumerate([h, *anc.get(h, ())] if h else []):
        if hp == bid:
            continue
        add("head", f"{'절' if i == 0 else '윗 절'} 「{text(hp)}」", hp, (ix.get("heads") or {}).get(hp))
    return layers


def chain_lines(graph, blocks, rules=None):
    """늘 보이는 단추를 둘 상자 · 칸 안의 헤딩 줄 {블록 id: 그 줄을 가리키는 작성 지침 보완 수} — 그래프가 상자(area box) · 칸 안에서 헤딩 · 제목으로 읽은 글 있는 줄."""
    own = owners(blocks)
    out = {}
    for n in (graph or {}).get("nodes") or ():
        if not isinstance(n, dict) or not n.get("para") or n.get("blank") or n.get("area") == "body" or n.get("role") not in ("heading", "title"):
            continue
        if own.get(n["para"]):
            out[n["para"]] = 0
    for place, rs in (rules or {}).items():
        for r in rs or ():
            for k in mentions((r or {}).get("instruction") or "") - {place}:
                if k in out:
                    out[k] += 1
    return out

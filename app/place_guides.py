"""자리마다의 작성 지침 — 헤딩 · 표 하나에 붙은 지침을 한 기준으로 고른다(spec_병합 ② §5-11 「자리마다의 작성 지침」 — 2026-11-23 사용자 "3단계에서 문서나 사용자가
각 헤딩 및 테이블에 들어갈 작성요령이 이 단계에서 저장되고 관리되고 그리고 에이전트가 표 대응 및 내용을 반영할 때 이를 고려하는지 검토하고 그게 들어 가게 해줘" · astra 협의).
순수 계산 — 저장 · 끝점은 `app/place_guides_api.py`. 3단계의 LLM 셋(자리 연결 · 표 대응 · 빈 자리 검토)과 화면 「지침」 단추가 **이 모듈 하나로** 그 자리의 지침을 고른다.

- 원천 둘: **문서**(`form_guides` 저장본 — 작성 요령 표 · <참고 N> · ※ 안내 · 각주 번호가 가리키는 작성 요령 항목) · **사용자**(헤딩 = 작업 폴더 `guides_user.json` · 표 = 표 지침 `table_agent` 의 「이 표」 instructions).
  양식 전체가 같이 쓰는 매칭 지침(`link_guides` — 「어떻게 잇나」)은 여기 들지 않는다(쓰임이 다르고 공유 범위가 다르다 — 부르는 쪽이 따로 싣는다).
- 표 = 지침이 든 블록(`at`)을 품은 **가장 안쪽의 3단계 표**(겉표 t1 의 칸 안 안쪽 표 t3 의 지침은 t3 것). `at` 이 3단계 표 밖이면 저장본이 붙인 표(본문 ※ 의 바로 다음 · 앞 표)가
  3단계 표일 때 그 표, 그 표 안의 3단계 표가 꼭 하나면 그 표 — 아니면 표에 붙이지 않고 그 헤딩의 것(어느 안쪽 표인지 짐작하지 않는다).
- 헤딩 = 저장본이 붙인 가장 가까운 앞 본문 헤딩(위 헤딩으로 올려 물려주지 않는다 — 차년도마다 되풀이되는 절의 지침이 다른 차년도로 넘어가지 않게).
- `pack` = 한 자리의 목록을 자른다(항목 ITEM_MAX · 자리 PLACE_MAX — 앞의 것부터: 칸 · 표의 것 → 헤딩의 것, 같은 글은 하나) → (목록, 자른 수). `sig` = 그 목록의 판(답을 저장할 때 함께 — 지침이 바뀐 자리만 다시 묻는다).
- 지침은 **판단 자료**다 — 넣을 사실 · 수는 원본의 실제 내용에서만(계약의 한 줄 `CONTRACT_LINE`). 스크립트(같은 이름 자리 · 표 묶음 · 일정 표 · 통째 복사 · 「내용 반영」)의 동작은 이 글로 바뀌지 않는다."""
import hashlib
import json

from app.headings import iter_blocks

ITEM_MAX, PLACE_MAX, CALL_MAX = 1200, 4000, 12000   # 지침 하나 · 한 자리 · 한 호출의 글자 수
USER_MAX = 4000   # 사람이 적는 헤딩 지침 하나
KIND_USER = "사용자 지침"
KIND_TABLE_USER = "표 지침(이 표)"
CONTRACT_LINE = ("\n\n### 자리마다의 작성 지침(guides)\n자료의 `guides` = 그 자리(헤딩 · 표)에 무엇을 쓰는지 양식(src \"doc\")이나 사람(src \"user\")이 정한 글입니다. "
                 "짝 · 칸 · 자리를 고를 때 근거로 쓰되, 넣을 사실 · 수 · 이름은 원본의 실제 내용에서만 가져옵니다(지침에 적힌 예시 · 수를 옮기지 않습니다). "
                 "지침이 그 자리에 넣지 말라는 내용(다른 차년도 · 다른 기관 · 계획 대신 실적 등)은 짝으로 고르지 않습니다.")


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


def index(saved, blocks, t3_ids, user=None, table_user=None):
    """저장본 + 사용자 지침 → {"tables": {표 id: [지침…]}, "heads": {헤딩 문단 id: [지침…]}, "loose": 어디에도 못 붙인 수, "heads_text": {헤딩 id: 글}}.
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
    return {"tables": tables, "heads": heads, "loose": loose, "heads_text": names, "t3": sorted(t3)}


def heading_finder(blocks, graph):
    """블록 id → 그 블록의 헤딩(문서 차례로 바로 앞의 본문 헤딩 줄 — 그 줄 자신이 헤딩이면 그 줄) | None. 저장본이 지침에 헤딩을 붙인 규칙(form_guides.collect)과 같다 —
    표 칸 안의 블록은 그 표의 최상위 자리로 센다."""
    top = {}
    for i, b in enumerate(blocks or ()):
        for x in iter_blocks([b]):
            top.setdefault(x["id"], i)
    heads = sorted({(top[n["para"]], n["para"]) for n in (graph or {}).get("nodes") or ()
                    if isinstance(n, dict) and n.get("role") == "heading" and n.get("area") == "body" and n.get("para") in top})

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
    own = owners(blocks)
    t3 = set((ix or {}).get("t3") or ()) | set((ix or {}).get("tables") or ())   # 3단계 표 모두 — 가장 가까운 3단계 표에서 멈춘다(그 표에 지침이 없어도 겉표로 올라가지 않는다: astra 3차)

    def table(tid):
        return for_table(ix, tid, find(tid))[0]

    def block(bid):
        tid = next((t for t in reversed(own.get(bid) or []) if t in t3), None)
        return table(tid) if tid else for_heading(ix, find(bid))[0]

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


def for_table(ix, tid, head=None):
    """표 tid 의 지침 — 그 표의 것 → 그 표가 든 헤딩의 것(헤딩에만 붙은 본문 지침) → (목록, 자른 수)."""
    return pack((ix or {}).get("tables", {}).get(tid), (ix or {}).get("heads", {}).get(head) if head else None)


def for_heading(ix, hid):
    """헤딩 hid 의 지침(헤딩에만 붙은 것 — 그 절의 표 지침은 표의 것) → (목록, 자른 수)."""
    return pack((ix or {}).get("heads", {}).get(hid))


def common(lists):
    """여러 항목(같은 묶음의 기관 · 차년도마다)의 지침 목록 → 모두에게 있는 것만(차례는 첫 목록의 것). 하나뿐이면 그것."""
    lists = [x or [] for x in lists]
    if not lists:
        return []
    keys = [{(g.get("kind"), g.get("text")) for g in x} for x in lists[1:]]
    return [g for g in lists[0] if all((g.get("kind"), g.get("text")) in k for k in keys)]


def sig(guides):
    """지침 목록의 판(12자) — 빈 목록은 ""(지침이 없는 자리는 판이 없다: 처음 지침이 붙으면 다시 묻는다)."""
    if not guides:
        return ""
    raw = json.dumps([[g.get("src"), g.get("kind"), g.get("label") or "", g.get("cell") or "", g.get("text")] for g in guides], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def budget(places, limit=CALL_MAX):
    """한 호출의 자리들 [{…, "guides": [...]}] — 글자 합이 limit 을 넘으면 뒤 자리의 지침부터 뺀다(자리 안에서는 뒤의 것부터) → 뺀 지침 수. places 를 고친다."""
    total = sum(len(g.get("text") or "") for p in places for g in p.get("guides") or ())
    cut = 0
    for p in reversed(places):
        while total > limit and p.get("guides"):
            g = p["guides"].pop()
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

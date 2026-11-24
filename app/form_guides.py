"""작성 지침 모으기 — 양식이 글쓴이에게 주는 안내를 헤딩/표별로(spec_작업 ② §21 「작성 지침 저장」). 순수 계산 — 저장·끝점은 `app/form_guides_api.py`.

2026-11-19 사용자 "테이블 분석할때 작성 지침들이 있으면 헤딩/테이블 별로 저장해야함" — 「작성요령 삭제」(app/form_cleanup.py)가 지우면 어디에도 남지 않던 것을, 지우기 전에 어느 헤딩 · 어느 표의 지침인지와 함께 남긴다.
- 작성 지침 = `form_cleanup.find` 가 찾는 것 가운데 글이 있는 넷: 작성 요령 표(`tables`) · <참고 N> 자료(`refs`) · ※ 안내(`notes`) · 안내 상자(`boxes` — 2026-11-23: 1칸 상자의 색 글 안내). **찾는 규칙은 그 함수 하나다 — 여기서 다시 찾지 않는다.**
  + **설명 줄**(`hints` — 2026-11-24: 표 아래 · 칸 안의 검정 「* …」 · 「주) …」 · 「※ …」 줄 — 지우는 패턴이 아니라 모으기만 한다 · 문서가 아직 양식일 때만: form_cleanup 모듈 설명).
- 헤딩 = 헤딩 그래프(2단계 결과)의 본문 헤딩 줄 가운데 문서 차례로 바로 앞의 것(지침이 헤딩 줄 안의 ※ 면 그 줄). 그래프가 없으면 비운다(짐작하지 않는다).
  **글 없는 글머리 헤딩**(양식의 빈 「o」·「-」·「⋅」 줄 — 노드 `blank`)에는 붙이지 않는다 — 글 있는 가장 가까운 앞 헤딩의 것이다(2026-11-24).
- **절 이름 항목**(2026-11-24 — `_parts`): 작성 요령 표가 절 이름으로 적은 항목(「1) 연구개발 목표 및 내용: …」 · 「[참여연구자 현황]」 덩이 · 「◦ 최종 목표」 + 딸린 줄)은 **그 이름의 헤딩**에 따로 붙인다 —
  항목 하나가 item 하나(id 「<표 id>#k」 · `of` = 그 표 · 헤딩이 여럿이면 헤딩마다)이고, 원래 표 item 의 글은 나눠 준 줄을 뺀 나머지(제목 줄 + 못 이은 줄 · `parts` = 나눈 수)다. 본문의 표만 · 그래프가 있을 때만.
- 표 = 표 칸 안의 지침은 그 표(본문 최상위 표) · 본문의 ※ 안내는 빈 줄을 건너 바로 다음 블록이 표면 그 표, 아니면(줄이 안내뿐이거나 ※ 로 시작할 때만) 위로 빈 줄 · 설명 줄 · ※ 줄을 거슬러 올라가 만나는 표 ·
  본문의 설명 줄은 위로 거슬러 올라가 만나는 표가 먼저(표 아래의 줄이다) · 작성 요령 표와 <참고 N> 자료는 절의 것이라 표 없음.
- 각주 번호(`marks` — 「연구개발비15)」 의 「15)」)는 그 블록 **바로 뒤의**(표 · 빈 줄만 사이에 둔) 작성 요령 표에서 같은 번호의 항목(「15. …」 줄부터 다음 「N.」 줄 전까지 · 「15-1)」 은 그 항목 안의 「1) …」)을 가리킨다 —
  작성 요령 표가 설명하는 블록은 `_explains` 가 정한다(번호가 1 부터 다시 시작하는 앞 블록은 다른 지침의 것). 못 이은 번호는 글 없이 남긴다(짐작하지 않는다).
collect(doc, graph, tables, found) → {"version", "counts"{items, marks, headings, tables}, "items"[{id, kind, name, text, heading{id, text} | None, table{id, label} | None, top}],
"marks"[{no, at, label, heading, table, guide(작성 요령 표 id | None), text}]} · groups(saved) → {"headings"[…], "tables"[…], "loose"[…]}(화면 · 읽는 기능이 쓰는 묶음) ·
places(saved) → 헤딩 · 표 LLM 판정 자료에 싣는 꼴(spec_헤딩_추출 ② §20 「작성 지침을 판정 자료로」)."""
import re

from app import form_cleanup
from app.division_profiles import _structure as structure

VERSION = 1
KIND_NAME = {**{p["key"]: p["name"] for p in form_cleanup.PATTERNS}, "hints": "설명 줄"}   # hints = 모으기만 하는 종류(지우는 패턴이 아니다 — form_cleanup 모듈 설명)
PART = (re.compile(r"^\[(.+)\]$"), re.compile(r"^(\d+)\s*\.(?!\d)\s*"), re.compile(r"^\d+\s*\)\s*|^[◦oㅇ○]\s+"), re.compile(r"^[-⦁]\s*"))   # 작성 요령 표 줄의 표식 — 등급 0 「[이름]」 · 1 「N.」 · 2 「N)」·「◦」 · 3 「-」·「⦁」(_parts)
PAREN = re.compile(r"[\(（][^\(\)（）]*[\)）]")
NOT_WORD = re.compile(r"[^0-9A-Za-z가-힣]")
TOP = re.compile(r"^\s*(\d+(?:\s*,\s*\d+)*)\s*\.\s*\S")   # 작성 요령 표의 번호 항목 — 「15. …」 · 「16,17. …」
SUB = re.compile(r"^\s*(\d+)\s*\)\s*\S")                   # 그 항목에 딸린 항목 — 「1) …」(각주 번호 「15-1)」 이 가리킨다)
TEXT_MAX = 20000   # 지침 하나의 글 — 넘으면 자른다(작성 요령 표 하나가 보통 1~4천 자)
LABEL_MAX = 80
PLACE_TEXT_MAX, PLACE_MARK_MAX = 2000, 600   # 판정 자료에 싣는 지침 하나의 글 · 각주 번호가 가리키는 항목 하나의 글(places — 자리마다의 합은 싣는 쪽이 자른다)


def _one(text, n=LABEL_MAX):
    return " ".join((text or "").split())[:n]


def _table_text(t):
    """표의 글 — 줄마다(칸은 「 | 」 로). 칸 안의 줄바꿈은 그대로 둔다(번호 항목이 줄마다다)."""
    rows = {}
    for c in t.get("cells") or ():
        rows.setdefault(c.get("row", 0), []).append((c.get("col", 0), (c.get("text") or "").strip()))
    return "\n".join(" | ".join(x for _, x in sorted(cells) if x) for _, cells in sorted(rows.items())).strip()


def _block_text(b):
    return _table_text(b) if b.get("type") == "table" else (b.get("text") or "").strip()


def _numbered(text):
    """작성 요령 표의 글 → {번호: 항목 글}. 항목 = 「15. …」 줄부터 다음 「N.」 줄 전까지(「16,17. …」 은 두 번호 모두) · 그 안의 「1) …」 줄은 딸린 항목 「15-1」(다음 「k)」·「N.」 줄 전까지 — 항목 글에도 든다).
    「N.」 항목 밖의 「k) …」 줄은 그대로 번호 k 의 항목이다. 같은 번호가 또 나오면 처음 것."""
    out, tops, top_buf, sub, sub_buf = {}, [], [], None, []

    def close_sub():
        nonlocal sub, sub_buf
        if sub is not None:
            for k in ([f"{t}-{sub}" for t in tops] or [sub]):
                out.setdefault(k, "\n".join(sub_buf).strip())
        sub, sub_buf = None, []

    def close_top():
        nonlocal tops, top_buf
        close_sub()
        for t in tops:
            out.setdefault(t, "\n".join(top_buf).strip())
        tops, top_buf = [], []

    for line in (text or "").split("\n"):
        m, s = TOP.match(line), SUB.match(line)
        if m:
            close_top()
            tops, top_buf = [x.strip() for x in m.group(1).split(",")], [line.strip()]
        elif s:
            close_sub()
            sub, sub_buf = s.group(1), [line.strip()]
            if tops:
                top_buf.append(line.rstrip())
        else:
            if tops:
                top_buf.append(line.rstrip())
            if sub is not None:
                sub_buf.append(line.rstrip())
    close_top()
    return out


def _explains(guides, marked, blocks):
    """작성 요령 표마다 그 표가 설명하는 블록(각주 번호가 든 본문 차례) → {본문 차례: (작성 요령 표 id, {번호: 글})}.
    표 앞으로 **표 · 빈 줄만** 건너 거슬러 올라가며 번호가 든 블록을 모은다 — 이미 모은 번호가 또 나오는 블록에서 멈춘다(번호가 1 부터 다시 시작하면 다른 지침의 것:
    연차보고서 서식의 표지 표와 요약문 표가 둘 다 1) 부터인데 뒤의 「요약문 작성 요령」 은 요약문 표의 것이다). 번호 항목이 없는 작성 요령 표는 아무것도 설명하지 않는다."""
    out = {}
    for gi, gid, nums in guides:
        if not nums:
            continue
        seen, j = set(), gi - 1
        while j >= 0:
            b = blocks[j]
            if not (b.get("type") == "table" or form_cleanup._blank(b)):
                break
            mine = marked.get(j)
            if mine:
                if seen & mine:
                    break
                seen |= mine
                out.setdefault(j, (gid, nums))
            j -= 1
    return out


def _norm(text):
    return NOT_WORD.sub("", text or "")


def _headings(graph, top, by_id):
    """헤딩 그래프 → 본문 헤딩 줄 [(본문 차례, 문단 id, 글, 레터, 이름)] — 문서 차례대로. 그래프가 없으면 [].
    **글 없는 글머리 헤딩**(노드 `blank` — 양식의 빈 「o」·「-」·「⋅」 줄)은 뺀다: 지침은 글 있는 가장 가까운 앞 헤딩의 것이다(계획서 양식의 절 끝 작성 요령 표가 빈 「⋅」 줄에 붙던 것 — 2026-11-24).
    이름 = 레터 뒤 글에서 「※」 뒤와 괄호 묶음을 떼고 글자만 남긴 것(작성 요령 표의 「절 이름」 항목과 견준다 — _parts)."""
    out = []
    for nd in (graph or {}).get("nodes") or ():
        if not isinstance(nd, dict) or nd.get("role") != "heading" or nd.get("area") != "body" or nd.get("blank"):
            continue
        pid = nd.get("para")
        if pid in top and pid in by_id:
            name = _norm(PAREN.sub("", (nd.get("text") or "").split("※")[0]))
            out.append((top[pid], pid, _one(by_id[pid].get("text")), "".join((nd.get("letter") or "").split()), name))
    return sorted(set(out))


def _parts(text, heads, lo, hi):
    """작성 요령 표의 글 → ([(헤딩 (본문 차례, 문단 id, 글, …), 항목 글)], 나머지 글) — **절 이름으로 적은 항목**을 그 헤딩에 나눈다(2026-11-24 — 연차보고서 서식 끝의 「본문 작성 요령」 표가
    「1) 연구개발 목표 및 내용: …」 처럼 절마다의 지침을 적었는데 통째로 마지막 헤딩 한 곳에만 붙어 그 절에는 닿지 않았다).
    - 항목의 시작 = 줄의 이름(앞 표식 PART 를 떼고 첫 「:」 앞까지 · 「[이름]」 은 괄호 안 — 글자만)이 헤딩의 이름과 **꼭 같은** 줄(3자 이상) ·
      「N. …」 줄은 번호가 헤딩 레터 「N.」 과 같고 그 헤딩의 이름(4자 이상)이 줄에 들어 있어도(번호만으로는 잇지 않는다 — 「1. 제품 2. 시설ㆍ장비 …」 같은 법령 인용).
    - 항목의 끝 = 다음 시작 줄, 또는 표식 등급이 제 것과 같거나 높은 줄 전(등급 0 「[…]」 · 1 「N.」·표식 없는 시작 줄 · 2 「N)」·「◦」 · 3 「-」·「⦁」 — 표식 없는 줄은 이어지는 줄). 끝의 빈 줄은 뗀다.
    - 같은 이름의 헤딩이 여럿이면 이 표가 맺는 구역(본문 차례 lo 초과 hi 미만 — 앞의 작성 요령 표 다음 ~ 이 표 앞)의 것만, 거기 없으면 문서 전체의 것 모두.
    첫 줄(표 제목 줄)은 늘 나머지에 남는다. 맞은 줄이 없으면 ([], text)."""
    lines = (text or "").split("\n")

    def pick(hits):
        return [h for h in hits if lo < h[0] < hi] or hits

    def read(line):   # → (등급 | None, 맞은 헤딩들)
        s, rank, no = line.strip(), None, None
        for k, rx in enumerate(PART):
            m = rx.match(s)
            if m:
                rank, no, s = k, (m.group(1) if k == 1 else None), (m.group(1) if k == 0 else s[m.end():])
                break
        name = _norm(re.split(r"[:：]", s, maxsplit=1)[0])
        hits = [h for h in heads if h[4] == name] if len(name) >= 3 else []
        if not hits and no:
            whole = _norm(s)
            hits = [h for h in heads if h[3] == f"{no}." and len(h[4]) >= 4 and h[4] in whole]
        return rank, pick(hits)

    marks = [(None, [])] + [read(x) for x in lines[1:]]
    out, used, i = [], set(), 1
    while i < len(lines):
        rank, hits = marks[i]
        if not hits:
            i += 1
            continue
        own, j = (1 if rank is None else rank), i + 1
        while j < len(lines) and not marks[j][1] and (marks[j][0] is None or marks[j][0] > own):
            j += 1
        body = "\n".join(x.rstrip() for x in lines[i:j]).rstrip()
        if any(h[4] != _norm(PART[1].sub("", PART[2].sub("", body.strip()))) for h in hits):   # 절 이름뿐인 줄(「5. 다음 연도 연구개발계획」)은 지침이 아니다 — 나머지에 둔다
            out += [(h, body) for h in hits]
            used.update(range(i, j))
        i = j
    rest = "\n".join(x for k, x in enumerate(lines) if k not in used).strip()
    return out, (rest if out else text)


def _table_labels(tables, blocks, by_id):
    """본문 최상위 표 id → 이름 — 첫 줄의 글(머리글)이고, 비었으면 3단계 결과의 표 앞 글(`before`), 그것도 없으면 id."""
    before = {t["id"]: t.get("before") or "" for t in (tables or {}).get("tables") or () if isinstance(t, dict) and t.get("id")}
    out = {}
    for b in blocks:
        if b.get("type") == "table":
            first = sorted((c for c in b.get("cells") or () if c.get("row") == 0), key=lambda c: c.get("col", 0))
            head = " | ".join(x for x in ((c.get("text") or "").strip().split("\n")[0] for c in first) if x)
            out[b["id"]] = _one(head, 60) or _one(before.get(b["id"]), 60) or b["id"]
    return out


def collect(doc, graph=None, tables=None, found=None):
    blocks = doc.blocks()
    found = found if found is not None else form_cleanup.find(doc)
    top, by_id = {}, {}
    for i, b in enumerate(blocks):
        for x in structure.iter_blocks([b]):
            top[x["id"]] = i
            by_id[x["id"]] = x
    heads = _headings(graph, top, by_id)
    labels = _table_labels(tables, blocks, by_id)
    guide_ids = {t["id"] for t in found.get("tables") or ()} | {b["id"] for b in found.get("boxes") or ()}   # 안내 상자도 「그 지침의 표」 가 아니다
    ref_spans = []   # <참고 N> 자료가 차지한 본문 차례 구간 — 그 안의 표는 「그 지침의 표」 가 아니다
    for r in found.get("refs") or ():
        if r["id"] in top and r.get("last") in top:
            ref_spans.append((top[r["id"]], top[r["last"]]))
    in_ref = lambda i: any(a <= i <= b for a, b in ref_spans)  # noqa: E731

    def heading_of(i, own=None):
        hit = None
        for hi, pid, text, *_ in heads:
            if hi < i or (hi == i and pid == own):
                hit = {"id": pid, "text": text}
            elif hi > i:
                break
        return hit

    def real_table(i):
        b = blocks[i] if 0 <= i < len(blocks) else None
        return b if b is not None and b.get("type") == "table" and b["id"] not in guide_ids and not in_ref(i) else None

    def table_ref(b):
        return {"id": b["id"], "label": labels.get(b["id"]) or b["id"]} if b is not None else None

    starts = lambda b: (b.get("text") or "").lstrip().startswith("※")  # noqa: E731
    chain = {top[x["id"]] for x in found.get("hints") or () if x["id"] in top and blocks[top[x["id"]]]["id"] == x["id"]}   # 표 아래에 이어지는 줄(본문 차례) — 설명 줄 · 「※」 로 시작하는 안내 줄
    chain |= {top[n["id"]] for n in found.get("notes") or () if n["id"] in top and blocks[top[n["id"]]]["id"] == n["id"] and starts(blocks[top[n["id"]]])}

    def above_table(i):
        """본문 차례 i 의 줄 위로 빈 줄 · 설명 줄 · ※ 안내 줄을 거슬러 올라가 만나는 표 | None(표 바로 아래 줄들의 사슬 — 「* …」 가 여러 줄 이어진다)."""
        j = i - 1
        while j >= 0 and (form_cleanup._blank(blocks[j]) or j in chain):
            j -= 1
        return real_table(j)

    def near_table(i, back=True):
        """본문의 ※ 안내(본문 차례 i) — 빈 줄을 건너 바로 다음 블록이 표면 그 표, 아니면 위로 거슬러 올라가 만나는 표(above_table — back: 줄이 ※ 로 시작할 때만. 제목 줄 안의 ※ 는 앞 표의 것이 아니다)."""
        j = i + 1
        while j < len(blocks) and form_cleanup._blank(blocks[j]):
            j += 1
        t = real_table(j)
        if t is None and back:
            t = above_table(i)
        return table_ref(t)

    def owner_table(pid):
        """표 칸 안의 블록 → 그 표(본문 최상위 표) | None(본문의 블록 · 작성 요령 표 · <참고 N> 자료 안)."""
        i = top.get(pid)
        return table_ref(real_table(i)) if i is not None and blocks[i]["id"] != pid else None

    items, prev = [], -1
    for t in sorted((t for t in found.get("tables") or () if t["id"] in top), key=lambda t: top[t["id"]]):
        i = top[t["id"]]
        parts, rest = _parts(_table_text(by_id[t["id"]]), heads, prev, i) if heads and blocks[i]["id"] == t["id"] else ([], _table_text(by_id[t["id"]]))   # 절 이름 항목은 그 헤딩으로(본문의 표만 — 칸 안의 표는 통째로)
        prev = max(prev, i)
        items.append({"id": t["id"], "kind": "tables", "name": KIND_NAME["tables"], "text": rest[:TEXT_MAX], "heading": heading_of(i), "table": owner_table(t["id"]), "top": i, **({"parts": len(parts)} if parts else {})})
        for k, (h, body) in enumerate(parts, 1):
            items.append({"id": f"{t['id']}#{k}", "of": t["id"], "kind": "tables", "name": KIND_NAME["tables"], "text": body[:TEXT_MAX], "heading": {"id": h[1], "text": h[2]}, "table": None, "top": h[0]})
    for r in found.get("refs") or ():
        i, j = top.get(r["id"]), top.get(r.get("last"))
        if i is None:
            continue
        body = blocks[i:(j if j is not None and j >= i else i) + 1] if blocks[i]["id"] == r["id"] else [by_id[r["id"]]]   # 본문의 자료 = 제목 줄 ~ 마지막 표 · 표 칸 안의 자료는 제목 줄만(그 칸의 차례를 여기서 다시 세지 않는다)
        text = "\n".join(x for x in (_block_text(b) for b in body) if x)
        items.append({"id": r["id"], "kind": "refs", "name": KIND_NAME["refs"], "text": text[:TEXT_MAX], "heading": heading_of(i), "table": owner_table(r["id"]), "top": i})
    for n in found.get("notes") or ():
        i, b = top.get(n["id"]), by_id.get(n["id"])
        if i is None or b is None:
            continue
        hit = form_cleanup.note_of(b)
        full = "".join(t for _, _, t, _ in form_cleanup._runs(b))
        text = full[hit[0]:hit[1]].strip() if hit else n.get("guide") or ""
        body = blocks[i]["id"] == n["id"]
        items.append({"id": n["id"], "kind": "notes", "name": KIND_NAME["notes"], "text": text[:TEXT_MAX], "heading": heading_of(i, n["id"]),
                      "table": near_table(i, back=bool(n.get("whole")) or starts(b)) if body else owner_table(n["id"]), "top": i})   # ※ 로 시작하는 줄은 뒤가 일부 본문 색이어도 안내 줄이다(표 바로 아래의 「※ 비율은 필수적으로 …」)
    for x in found.get("hints") or ():   # 설명 줄 — 표 칸 안이면 그 표 · 본문이면 위로 거슬러 올라가 만나는 표(표 아래의 「* …」 줄들), 없으면 ※ 안내와 같은 규칙
        i, b = top.get(x["id"]), by_id.get(x["id"])
        if i is None or b is None:
            continue
        body = blocks[i]["id"] == x["id"]
        items.append({"id": x["id"], "kind": "hints", "name": KIND_NAME["hints"], "text": (b.get("text") or "").strip()[:TEXT_MAX], "heading": heading_of(i, x["id"]),
                      "table": (table_ref(above_table(i)) or near_table(i, back=False)) if body else owner_table(x["id"]), "top": i})
    for x in found.get("boxes") or ():   # 안내 상자 — 그 상자가 놓인 절의 지침(상자는 쓸 자리라 표의 지침이 아니다 — 표 칸 안의 상자면 그 표)
        i = top.get(x["id"])
        if i is None or x["id"] not in by_id:
            continue
        text = "\n".join((b.get("text") or "").strip() for c in by_id[x["id"]].get("cells") or () for b in c.get("blocks") or () if (b.get("text") or "").strip())
        items.append({"id": x["id"], "kind": "boxes", "name": KIND_NAME["boxes"], "text": text[:TEXT_MAX], "heading": heading_of(i), "table": owner_table(x["id"]), "top": i})
    items.sort(key=lambda it: (it["top"], it["kind"]))

    guides = sorted(((top[t["id"]], t["id"], _numbered(_table_text(by_id[t["id"]]))) for t in found.get("tables") or () if t["id"] in top), key=lambda g: g[0])
    number = lambda m: (m.get("text") or "").strip().rstrip(")").strip()  # noqa: E731
    marked = {}   # 본문 차례 → 그 블록에 든 각주 번호들
    for m in found.get("marks") or ():
        if m["id"] in top:
            marked.setdefault(top[m["id"]], set()).add(number(m))
    explains = _explains(guides, marked, blocks)
    marks = []
    for m in found.get("marks") or ():
        i, b = top.get(m["id"]), by_id.get(m["id"])
        if i is None or b is None:
            continue
        no = number(m)
        gid, nums = explains.get(i) or (None, {})
        text = nums.get(no) or nums.get(no.split("-")[0]) or ""   # 딸린 번호(15-1)의 항목이 없으면 그 항목(15)의 글
        marks.append({"no": no, "at": m["id"], "label": _one(b.get("text")), "heading": heading_of(i, m["id"]), "table": owner_table(m["id"]),
                      "guide": gid if text else None, "text": text[:TEXT_MAX], "top": i})
    owners = lambda key: len({x[key]["id"] for x in items + marks if x.get(key)})  # noqa: E731
    _places_of(blocks, tables, items, marks)
    return {"version": VERSION, "counts": {"items": len(items), "marks": len(marks), "marksLinked": sum(1 for m in marks if m["text"]), "headings": owners("heading"), "tables": owners("table")},
            "items": items, "marks": marks}


def _places_of(blocks, tables, items, marks):
    """지침마다 모은 때 정한 자리 `place` {table(가장 안쪽 3단계 표), cell(「r행c열」)?} | {loose: true}(표의 지침인데 어느 3단계 표인지 못 정함)을 적는다 — 표가 아닌 지침은 안 적는다.
    「작성요령 삭제」 가 지침 블록을 지운 뒤에도 그 표 · 칸으로 읽히게(app/place_guides.index — 블록이 없으면 이것을 쓴다: astra 3차). 3단계 결과가 없으면 안 적는다."""
    from app import place_guides as PG
    t3 = {t["id"] for t in (tables or {}).get("tables") or () if isinstance(t, dict) and t.get("id")}
    if not t3:
        return
    cell_of = {}
    own, inside = PG.owners(blocks, cell_of), PG._inside(blocks)
    for x, at in [(x, x["id"]) for x in items] + [(m, m["at"]) for m in marks]:
        t = x.get("table") if isinstance(x.get("table"), dict) else {}
        if not (t.get("id") or own.get(at)):
            continue
        tid = PG._table_of(at, t.get("id"), own, inside, t3)
        if tid == PG.LOOSE:
            x["place"] = {"loose": True}
        elif tid:
            c = cell_of.get(at)
            x["place"] = {"table": tid, **({"cell": c[1]} if c and c[0] == tid else {})}


def keep_old(new, old):
    """새로 모은 것 new 에 옛 저장본 old 의 항목 가운데 **지금 문서에서 사라진 것**을 남긴다(2026-11-23 astra 2차 G5 — 「작성요령 삭제」 는 ※ 안내를 문단 안에서만 · 각주 번호는 번호 글자만 지워
    지침 블록이 살아 있을 수 있어, 「하나도 없을 때만 저장본」 규칙으로는 일부만 지운 뒤 다시 모으면 지운 지침이 사라졌다). 열쇠 = 항목 (kind, id) · 각주 (at, 번호, 작성 요령 표) —
    같은 열쇠가 새로 모은 데 있으면 새 값, 없으면 옛 값. 블록을 지우고 다시 만든 편집(새 id · 같은 글)은 겹치지 않게 같은 (kind, 글) · (번호, 글)이 이미 있으면 옛 것을 남기지 않는다."""
    if not isinstance(old, dict):
        return new
    norm = lambda t: " ".join((t or "").split())  # noqa: E731
    own = lambda x: tuple((x.get(k) or {}).get("id") if isinstance(x.get(k), dict) else None for k in ("heading", "table"))  # noqa: E731 — 다른 자리의 같은 글은 다른 지침(astra 3차)
    items, marks = list(new.get("items") or []), list(new.get("marks") or [])
    ik, it = {(x.get("kind"), x.get("id")) for x in items}, {(x.get("kind"), norm(x.get("text")), own(x)) for x in items}
    mk, mt = {(m.get("at"), m.get("no"), m.get("guide")) for m in marks}, {(m.get("no"), norm(m.get("text")), own(m)) for m in marks}
    add_i = [x for x in old.get("items") or () if isinstance(x, dict) and (x.get("kind"), x.get("id")) not in ik and (x.get("kind"), norm(x.get("text")), own(x)) not in it]
    add_m = [m for m in old.get("marks") or () if isinstance(m, dict) and (m.get("at"), m.get("no"), m.get("guide")) not in mk and (m.get("no"), norm(m.get("text")), own(m)) not in mt]
    if not add_i and not add_m:
        return new
    items = sorted(items + add_i, key=lambda x: (x.get("top", 0), x.get("kind") or ""))
    marks = sorted(marks + add_m, key=lambda m: m.get("top", 0))
    owners = lambda key: len({x[key]["id"] for x in items + marks if isinstance(x.get(key), dict) and x[key].get("id")})  # noqa: E731
    counts = {"items": len(items), "marks": len(marks), "marksLinked": sum(1 for m in marks if m.get("text")), "headings": owners("heading"), "tables": owners("table")}
    return {**new, "items": items, "marks": marks, "counts": counts}


def groups(saved):
    """저장한 것 → 헤딩별 · 표별 묶음(문서 차례) + 어디에도 못 붙인 것. 표가 있는 지침은 표 묶음과 그 절의 헤딩 묶음에 함께 든다(같은 지침을 두 길로 찾는다)."""
    heads, tabs, loose = {}, {}, []
    for kind in ("items", "marks"):
        for x in (saved or {}).get(kind) or ():
            if not isinstance(x, dict):
                continue
            h, t = x.get("heading"), x.get("table")
            for own, box, name in ((h, heads, "text"), (t, tabs, "label")):
                if isinstance(own, dict) and own.get("id"):
                    g = box.setdefault(own["id"], {"id": own["id"], name: own.get(name) or "", "top": x.get("top", 0), "items": [], "marks": []})
                    g["top"] = min(g["top"], x.get("top", 0))
                    g[kind].append(x)
            if not (isinstance(h, dict) and h.get("id")) and not (isinstance(t, dict) and t.get("id")):
                loose.append({**x, "what": kind})
    order = lambda d: sorted(d.values(), key=lambda g: g["top"])  # noqa: E731
    return {"headings": order(heads), "tables": order(tabs), "loose": loose}


def _cut(text, n):
    t = (text or "").strip()
    return t if len(t) <= n else t[:n - 1] + "…"


def places(saved):
    """저장한 것(collect · form_guides_api.load 꼴) → 헤딩 · 표 LLM 판정 자료에 싣는 꼴(spec_헤딩_추출 ② §20) {"tables": {표 id: [지침…]}, "body": [지침…]} | None(싣을 것 없음).
    지침 = {"at": 그 지침이 있는 블록 id, "head": 붙인 헤딩 id | "", "kind": 이름, "text": 글} · 각주 번호는 kind 「각주 번호 N)」 + "label"(번호가 든 줄의 글) — **가리키는 항목 글이 있는 번호만**(글 없는 번호는 판정에 줄 것이 없다).
    표에 붙은 지침(표 칸 안 · 표 바로 앞뒤의 ※ 안내 · 칸의 각주 번호)은 그 표의 것(표 판정) · 나머지(작성 요령 표 · <참고 N> 자료 · 본문의 ※ 안내 · 본문 줄의 각주 번호)는 body(구간 판정 — 문서 차례).
    글은 자른다(PLACE_TEXT_MAX · PLACE_MARK_MAX) — 저장본은 그대로 둔다."""
    if not isinstance(saved, dict):
        return None
    tables, body = {}, []
    rows = [(x, False) for x in saved.get("items") or () if isinstance(x, dict)] + [(m, True) for m in saved.get("marks") or () if isinstance(m, dict) and m.get("text")]
    for x, mark in sorted(rows, key=lambda r: (r[0].get("top", 0), r[1])):
        h = x.get("heading")
        head = (h.get("id") or "") if isinstance(h, dict) else ""
        if mark:
            one = {"at": x.get("at") or "", "head": head, "kind": f"각주 번호 {x.get('no')})", "label": _one(x.get("label"), 60), "text": _cut(x.get("text"), PLACE_MARK_MAX)}
        else:
            one = {"at": x.get("id") or "", "head": head, "kind": x.get("name") or KIND_NAME.get(x.get("kind"), x.get("kind") or ""), "text": _cut(x.get("text"), PLACE_TEXT_MAX)}
        if not one["text"]:
            continue
        t = x.get("table")
        if isinstance(t, dict) and t.get("id"):
            tables.setdefault(t["id"], []).append(one)
        else:
            body.append(one)
    return {"tables": tables, "body": body} if tables or body else None

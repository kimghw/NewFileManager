"""작성 지침 모으기 — 양식이 글쓴이에게 주는 안내를 헤딩/표별로(spec_작업 ② §21 「작성 지침 저장」). 순수 계산 — 저장·끝점은 `app/form_guides_api.py`.

2026-11-19 사용자 "테이블 분석할때 작성 지침들이 있으면 헤딩/테이블 별로 저장해야함" — 「작성요령 삭제」(app/form_cleanup.py)가 지우면 어디에도 남지 않던 것을, 지우기 전에 어느 헤딩 · 어느 표의 지침인지와 함께 남긴다.
- 작성 지침 = `form_cleanup.find` 가 찾는 것 가운데 글이 있는 셋: 작성 요령 표(`tables`) · <참고 N> 자료(`refs`) · ※ 안내(`notes`). **찾는 규칙은 그 함수 하나다 — 여기서 다시 찾지 않는다.**
- 헤딩 = 헤딩 그래프(2단계 결과)의 본문 헤딩 줄 가운데 문서 차례로 바로 앞의 것(지침이 헤딩 줄 안의 ※ 면 그 줄). 그래프가 없으면 비운다(짐작하지 않는다).
- 표 = 표 칸 안의 지침은 그 표(본문 최상위 표) · 본문의 ※ 안내는 빈 줄을 건너 바로 다음 블록이 표면 그 표, 아니면(줄이 안내뿐일 때만) 바로 앞 블록이 표면 그 표 · 작성 요령 표와 <참고 N> 자료는 절의 것이라 표 없음.
- 각주 번호(`marks` — 「연구개발비15)」 의 「15)」)는 그 블록 **바로 뒤의**(표 · 빈 줄만 사이에 둔) 작성 요령 표에서 같은 번호의 항목(「15. …」 줄부터 다음 「N.」 줄 전까지 · 「15-1)」 은 그 항목 안의 「1) …」)을 가리킨다 —
  작성 요령 표가 설명하는 블록은 `_explains` 가 정한다(번호가 1 부터 다시 시작하는 앞 블록은 다른 지침의 것). 못 이은 번호는 글 없이 남긴다(짐작하지 않는다).
collect(doc, graph, tables, found) → {"version", "counts"{items, marks, headings, tables}, "items"[{id, kind, name, text, heading{id, text} | None, table{id, label} | None, top}],
"marks"[{no, at, label, heading, table, guide(작성 요령 표 id | None), text}]} · groups(saved) → {"headings"[…], "tables"[…], "loose"[…]}(화면 · 읽는 기능이 쓰는 묶음) ·
places(saved) → 헤딩 · 표 LLM 판정 자료에 싣는 꼴(spec_헤딩_추출 ② §20 「작성 지침을 판정 자료로」)."""
import re

from app import form_cleanup
from app.division_profiles import _structure as structure

VERSION = 1
KIND_NAME = {p["key"]: p["name"] for p in form_cleanup.PATTERNS}
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


def _headings(graph, top, by_id):
    """헤딩 그래프 → 본문 헤딩 줄 [(본문 차례, 문단 id, 글)] — 문서 차례대로. 그래프가 없으면 []."""
    out = []
    for nd in (graph or {}).get("nodes") or ():
        if not isinstance(nd, dict) or nd.get("role") != "heading" or nd.get("area") != "body":
            continue
        pid = nd.get("para")
        if pid in top and pid in by_id:
            out.append((top[pid], pid, _one(by_id[pid].get("text"))))
    return sorted(set(out))


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
    guide_ids = {t["id"] for t in found.get("tables") or ()}
    ref_spans = []   # <참고 N> 자료가 차지한 본문 차례 구간 — 그 안의 표는 「그 지침의 표」 가 아니다
    for r in found.get("refs") or ():
        if r["id"] in top and r.get("last") in top:
            ref_spans.append((top[r["id"]], top[r["last"]]))
    in_ref = lambda i: any(a <= i <= b for a, b in ref_spans)  # noqa: E731

    def heading_of(i, own=None):
        hit = None
        for hi, pid, text in heads:
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

    def near_table(i, back=True):
        """본문의 ※ 안내(본문 차례 i) — 빈 줄을 건너 바로 다음 블록이 표면 그 표, 아니면 바로 앞 블록이 표면 그 표(back — 줄이 안내뿐일 때만: 제목 줄 안의 ※ 는 앞 표의 것이 아니다)."""
        j = i + 1
        while j < len(blocks) and form_cleanup._blank(blocks[j]):
            j += 1
        t = real_table(j)
        if t is None and back:
            j = i - 1
            while j >= 0 and form_cleanup._blank(blocks[j]):
                j -= 1
            t = real_table(j)
        return table_ref(t)

    def owner_table(pid):
        """표 칸 안의 블록 → 그 표(본문 최상위 표) | None(본문의 블록 · 작성 요령 표 · <참고 N> 자료 안)."""
        i = top.get(pid)
        return table_ref(real_table(i)) if i is not None and blocks[i]["id"] != pid else None

    items = []
    for t in found.get("tables") or ():
        i = top.get(t["id"])
        if i is None:
            continue
        items.append({"id": t["id"], "kind": "tables", "name": KIND_NAME["tables"], "text": _table_text(by_id[t["id"]])[:TEXT_MAX], "heading": heading_of(i), "table": owner_table(t["id"]), "top": i})
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
                      "table": near_table(i, back=bool(n.get("whole"))) if body else owner_table(n["id"]), "top": i})
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
    return {"version": VERSION, "counts": {"items": len(items), "marks": len(marks), "marksLinked": sum(1 for m in marks if m["text"]), "headings": owners("heading"), "tables": owners("table")},
            "items": items, "marks": marks}


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

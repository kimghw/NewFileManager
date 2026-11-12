"""병합 — LLM 보정의 검토 단위(spec_병합 ② §4 「LLM 보정」, 2026-11-11 사용자 "LLM으로 검토할 떄는 멀티에이전트로 챕터별로 해줘. 20페이지 내로 나눠서 검토"):
목적 문서를 장(chapter)으로 나누고, 쪽 상한을 넘는 장은 다음 레벨 절을 이어 붙여 상한 안으로 자른다. 단위마다 개요·그 자리의 실제 글 앞부분을 낸다(merge_llm.review 가 씀).

- 쪽 = **추정**(page_numbers): 한글이 저장한 줄 배치에서 나온 쪽 나눔 표지(`hwpx_layout.annotate_pages` 가 최상위 블록에 단 `pageStart` · 구역 시작 `page`)를 믿고,
  표지가 안 붙는 곳(표 뒤 — 여러 쪽 표 · 줄 배치 캐시가 없는 문단 — 편집·구분 기준 반영으로 새로 든 줄)은 쌓인 높이(표 = 칸 높이 합, 문단 = 줄 수 어림)로 센다.
  칸 높이(`cellSz`)는 최소 높이라 덜 세는 쪽으로 어긋난다. 실측(2026-11-11): 작성본 연구계획서 추정 241쪽 ↔ 한글 251쪽(references/HWPX_포맷.md — 표지만 세면 196),
  반영한 연차보고서 추정 43쪽(표지만 33 — 한글 쪽 수는 안 잼).
- 장 = 2단계 그래프 **주 사슬**(templates kind main) 레벨 1 노드 중 본문(글상자 안이 아닌 것)이고 번호가 앞 장보다 큰 것(장 안의 「1. 2.」 목록은 장이 아님).
  첫 장 앞(표지·요약문·목차)은 한 단위. 장이 상한을 넘으면 그 장의 자식 절(다음 레벨 헤딩)에서 잘라 이어 붙이고, 절 하나가 혼자 넘으면 그 절의 자식으로 다시 자른다 —
  더 자를 자식이 없으면 넘는 채로 한 단위(over)."""
import re
from bisect import bisect_right
from collections import Counter, defaultdict

from app.division_llm import _short

PAGES = 20
HEADS = ("heading", "subtitle", "label", "title")
FRONT = "첫 장 앞(표지·요약문·목차)"
TITLE_LEN, OUTLINE_MAX, OUTLINE_LEN, LINE_LEN, TABLE_ROWS = 50, 40, 60, 80, 6
LINE_MM, LINE_CHARS = 6.8, 40   # 캐시 없는 문단 높이 어림 — 줄 높이(12pt × 160%) · 한 줄 글자 수(본문 폭 170mm 안팎)
_NUM = re.compile(r"\d+")


def index(blocks):
    """블록 id(표 칸·칸 안 블록까지) → (최상위 차례, 그 블록이 든 목록 | None(칸), 목록 안 차례)."""
    out = {}

    def walk(lst, top):
        for k, b in enumerate(lst):
            t = k if top is None else top
            out[b["id"]] = (t, lst, k)
            for c in b.get("cells") or ():
                out[c["id"]] = (t, None, None)
                walk(c.get("blocks") or [], t)
    walk(blocks, None)
    return out


def _height(t):
    """표 높이(mm) — 열마다 그 열을 덮는 칸 높이의 합 중 가장 큰 것(병합 칸 높이가 0 이어도 병합 없는 열이 받친다)."""
    cols = Counter()
    for c in t.get("cells") or ():
        for k in range(c.get("col", 0), c.get("col", 0) + (c.get("colSpan") or 1)):
            cols[k] += c.get("heightMm") or 0
    return max(cols.values(), default=0)


def page_numbers(blocks):
    """최상위 블록마다 추정 쪽 번호(1부터 — 모듈 설명). 한글이 단 쪽 나눔 표지(구역 시작·pageStart)가 있으면 그것을 믿고, 표지가 안 붙는 곳 —
    표 뒤 · 줄 배치 캐시가 없는 문단(`lines` 없음) — 은 그 쪽에 쌓인 높이(어림)가 본문 높이를 넘을 때 새 쪽으로 센다(캐시 있는 문단은 높이만 쌓고 쪽은 표지로)."""
    out, p, y, body = [], 1, 0.0, None
    for i, b in enumerate(blocks):
        if "page" in b:   # 구역 시작 = 새 쪽
            p, y = p + (1 if i else 0), 0.0
            pg = b["page"]
            body = pg["heightMm"] - pg["marginsMm"]["t"] - pg["marginsMm"]["b"] if pg else None
        elif b.get("pageStart"):
            p, y = p + 1, 0.0
        out.append(p)
        table = b.get("type") == "table"
        # ponytail: 본문 12pt·줄간격 160%(연구개발계획서·연차보고서 서식) 어림 — 다른 서식이면 쪽이 어긋난다, 맞추려면 문단 모양에서 줄 높이를 읽는다
        y += _height(b) if table else LINE_MM * (len(b["lines"]) + 1 if "lines" in b else 1 + len(b.get("text") or "") // LINE_CHARS)
        while body and (table or "lines" not in b) and y > body:
            p, y = p + 1, y - body
    return out


def _name(n):
    return _short(f"{n.get('letter') or ''} {(n.get('text') or '').split('※')[0]}", TITLE_LEN)


def _heads(graph, at):
    """본문 헤딩 노드(문서 순) — at = index()."""
    nodes = [n for n in (graph or {}).get("nodes") or () if n.get("flow") == "body" and n.get("role") in HEADS and not n.get("blank") and n.get("para") in at]
    return sorted(nodes, key=lambda n: (at[n["para"]][0], n.get("n", 0)))


def units(blocks, graph, *, pages=PAGES):
    """목적 문서 → 검토 단위 [{title, start, end(최상위 블록 차례 — end 제외), pages[첫 쪽, 끝 쪽], over(쪽 상한을 넘음)}] — 이어져 문서 전체를 덮는다(모듈 설명)."""
    if not blocks:
        return []
    page, at = page_numbers(blocks), index(blocks)
    heads = _heads(graph, at)
    kids = defaultdict(list)
    for n in heads:
        kids[n.get("parent")].append(n)
    main = {t["key"] for t in (graph or {}).get("templates") or () if t.get("kind") == "main"}
    chapters, last = [], 0
    for n in heads:
        num = _NUM.search(n.get("letter") or "")
        if n.get("template") in main and n.get("level") == 1 and n.get("area") == "body" and num and int(num.group()) > last:
            chapters.append(n)
            last = int(num.group())

    def pos(n):
        return at[n["para"]][0]

    def span(a, b):
        return page[b - 1] - page[a] + 1

    def unit(a, b, path, last=None):
        title = " › ".join(path if len(path) <= 3 else [path[0], "…", *path[-2:]]) + (f" ~ {last}" if last else "")
        return {"title": title, "start": a, "end": b, "pages": [page[a], page[b - 1]], "over": span(a, b) > pages}

    def split(node, a, b, path):
        if span(a, b) <= pages:
            return [unit(a, b, path)]
        ks, seen = [], {a}
        for k in kids[node["id"]]:
            if a < pos(k) < b and pos(k) not in seen:
                seen.add(pos(k))
                ks.append(k)
        if not ks:
            return [unit(a, b, path)]
        bounds = [a, *(pos(k) for k in ks[1:]), b]
        segs = list(zip(bounds, bounds[1:], ks))
        out, cur = [], [segs[0]]
        for seg in [*segs[1:], None]:
            if seg and span(cur[0][0], seg[1]) <= pages:
                cur.append(seg)
                continue
            if len(cur) == 1 and span(cur[0][0], cur[0][1]) > pages:   # 절 하나가 혼자 넘음 — 그 절의 자식으로
                out += split(cur[0][2], cur[0][0], cur[0][1], [*path, _name(cur[0][2])])
            else:
                out.append(unit(cur[0][0], cur[-1][1], [*path, _name(cur[0][2])], _name(cur[-1][2]) if len(cur) > 1 else None))
            cur = [seg]
        return out

    starts = [pos(c) for c in chapters]
    out = [unit(0, starts[0] if starts else len(blocks), [FRONT])] if not starts or starts[0] > 0 else []
    for c, a, b in zip(chapters, starts, [*starts[1:], len(blocks)]):
        out += split(c, a, b, [_name(c)])
    return out


def assign(us, at, ids):
    """블록 id 마다 그 블록(의 최상위 블록)이 든 단위 차례 — 모르는 id 는 0(첫 단위)."""
    starts = [u["start"] for u in us]
    return [max(0, bisect_right(starts, at[i][0]) - 1) if i in at else 0 for i in ids]


def outline(graph, at, u):
    """단위 안 본문 헤딩 「레터 글」(문서 순, 같은 줄은 한 번 — OUTLINE_MAX 줄까지) → (줄들, 못 실은 줄 수)."""
    lines = list(dict.fromkeys(_short(f"{n.get('letter') or ''} {n.get('text') or ''}", OUTLINE_LEN) for n in _heads(graph, at) if u["start"] <= at[n["para"]][0] < u["end"]))
    return lines[:OUTLINE_MAX], max(0, len(lines) - OUTLINE_MAX)


def _lines(b):
    if b.get("type") == "table":   # 행마다 칸 글을 「 | 」 로 — 앞 TABLE_ROWS 행
        rows = defaultdict(list)
        for c in b.get("cells") or ():
            rows[c.get("row", 0)].append(c)
        return [" | ".join(t for c in sorted(rows[r], key=lambda c: c.get("col", 0)) if (t := _short(c.get("text"), 30))) for r in sorted(rows)[:TABLE_ROWS]]
    return [b.get("text") or ""]


def excerpt(at, bid, n):
    """그 자리의 실제 글 앞부분 n 줄(줄마다 LINE_LEN 자) — 문단이면 그 줄부터 같은 목록(본문·칸)의 뒤 블록들, 표면 바로 앞 문단(표 제목)과 앞 행들."""
    if bid not in at or at[bid][1] is None:
        return []
    _, lst, k = at[bid]
    if lst[k].get("type") == "table" and k and lst[k - 1].get("type") == "paragraph":
        k -= 1
    out, table = [], lst[at[bid][2]] if lst[at[bid][2]].get("type") == "table" else None
    for b in lst[k:]:
        out += [_short(x, LINE_LEN) for x in _lines(b) if x.strip()]
        if len(out) >= n or b is table:   # 표의 발췌는 그 표에서 끝난다 — 뒤 블록(다음 표의 행)까지 실으면 LLM 이 그 표의 내용으로 잘못 읽는다(2026-11-12: 일정 요약 표에 1차년도 표의 행이 섞였다)
            break
    return out[:n]

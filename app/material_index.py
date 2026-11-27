"""자료의 절 색인 · 근거 위치(spec_양식작성 ② §5-12 2~5) — **순수 계산**(다른 app 모듈을 가져오지 않는다 · 저장하지 않는다 — 자료 글에서 그때마다 셈한다).
2026-11-27 사용자 「나머진 합의한 대로 진행해줘」(세 모델 합의안 G1 · G7 — artifacts/form_write_flow_review_2026-11-27/proposal.md).

자료 = 에이전트 보기의 자료 기록 {id, name, text}(문서 라이브러리에서 뽑은 MD · 올린 파일 · 붙여 넣은 글). MD 에는 쪽 표시(`<!-- p.N -->`)와 헤딩 줄(`#`)이 있다.
- `sections(text)` → 절 [{id "s<n>", start, end(글자 자리 — text[start:end]), page(처음 쪽 | None), path[윗 제목들], title}] — 헤딩 줄마다 · 긴 절(SEC_MAX 초과)은 빈 줄에서 나눔 · 헤딩이 없는 글은 빈 줄 묶음.
- `locate(quote, mats, prefer=())` → 그 구절이 든 자리 {mat, name, start, end, sec, page, path, title, hits} | None — `doc_agent.quoted` 와 같은 견줌(공백을 접고 소문자로 · 두 글자 이상).
  hits = 같은 구절이 나온 수(자료 모두에서). 여러 곳이면 **첫 자리**를 주되(prefer = 작성 계획이 고른 절 (자료 id, 절 id) 안의 것이 먼저) hits 로 알린다 — 자리를 확정하지 않는다.
- `marked(mat, only=None, near=0)` → 절마다 머리 줄 `[[<자료 id>/<절 id> | p.쪽 | 윗 제목 › 제목]]` 을 붙인 글(only = 실을 절 id 모음 | None = 모두 · near = 앞뒤로 더 싣는 절 수) · `toc(mat)` → 목차 줄들(글 없이).
- `narrow(mats, evidence, cap, near=1)` → 초안 요청에 싣는 자료들 — 그 자리의 근거 절 + 앞뒤 절 + 목차(자료마다). evidence = [{mat, sec}].
- `field_clash(place_text, source_text)` → 자리의 머리 글과 근거의 제목 경로에 적힌 **차년도 · 단계 · 연도**가 서로 다른 것 [글] — 둘 다 적혀 있고 겹치는 값이 없을 때만(한쪽이 안 적었으면 모른다 — 알리지 않는다).
- `excerpt(text, start, end, around)` → 그 자리 앞뒤 글 {before, hit, after}(화면의 「참조한 자료」 열).
스크립트가 판정하지 못하는 것 = 그 구절이 그 자리의 값을 뒷받침하는가(같은 수가 다른 기관 · 다른 항목의 것일 수 있다) — 사람이 근거를 열어 본다."""
import functools
import re

SEC_MAX = 3000          # 절 하나의 글자 수 — 넘으면 빈 줄에서 나눈다
PATH_MAX, TITLE_MAX = 4, 80
EVID_MAX = 6            # 자리 하나의 근거 절 수
QUOTE_MAX = 120
PLACES_MAX = 60         # locate 가 자리를 견줄 때 보는 수(hits 는 다 센다 — 작성 계획이 고른 절 · 자리와 어긋나지 않는 절을 이 안에서 고른다: astra R2 「여섯째 일치가 계획이 고른 절」)
VERSION = 2             # 절을 가르는 규칙의 판 — 절 id 는 이 규칙에서만 같은 절을 가리킨다(작성 계획이 저장한 근거 절은 판이 같을 때만 쓴다: form_review_api.evidence)
_PAGE = re.compile(r"<!--\s*p\.\s*(\d+)\s*-->")
_HEAD = re.compile(r"^(#{1,6})[ \t　]+(.*\S)[ \t　]*$")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_REF = re.compile(r"^(m[0-9a-f]{8})/(s\d{1,5})$")
_SPACE = re.compile(r"\s")


def _one(text, n):
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


@functools.lru_cache(maxsize=24)
def _scan(text):
    """글의 헤딩 줄 · 쪽 표시 → (heads[(줄 시작, 줄 끝, 깊이, 제목)], pages[(자리, 쪽)]) — 코드 울타리(``` · ~~~) 안의 것은 세지 않는다. 줄 끝의 CR 은 떼고 견준다(자리는 원문 그대로)."""
    heads, pages, pos, fence = [], [], 0, ""
    for line in text.split("\n"):
        bare = line.rstrip("\r")
        f = _FENCE.match(bare)
        if f and (not fence or f.group(1)[0] == fence[0] and len(f.group(1)) >= len(fence)):
            fence = "" if fence else f.group(1)
        elif not fence:
            m = _HEAD.match(bare)
            if m:
                heads.append((pos, pos + len(line), len(m.group(1)), _one(_PAGE.sub("", m.group(2)), TITLE_MAX)))
            for pm in _PAGE.finditer(line):
                pages.append((pos + pm.start(), int(pm.group(1))))
        pos += len(line) + 1
    return tuple(heads), tuple(pages)


def page_at(text, pos, line_end=None):
    """그 글자 자리의 쪽 — 그 자리 앞(line_end 를 주면 그 줄 끝까지: 헤딩 줄에 붙은 쪽 표시)의 마지막 쪽 표시 | None(앞에 표시가 없음)."""
    _, pages = _scan(str(text or ""))
    upto = pos if line_end is None else line_end
    before = [p for at, p in pages if at <= upto]
    return before[-1] if before else None


@functools.lru_cache(maxsize=24)
def sections(text):
    """자료 글 → 절 목록(튜플 — 캐시한다: 고치지 않는다). 빈 글은 빈 목록. 절의 쪽 = 그 절의 첫 줄까지 나온 마지막 쪽 표시(헤딩 줄에 붙은 표시 포함) · 없으면 절 안의 첫 표시."""
    text = str(text or "")
    if not text.strip():
        return ()
    heads, pages = _scan(text)
    cuts, stack = [], []   # [(start, path, title)]
    if not heads or _PAGE.sub("", text[:heads[0][0]]).strip():   # 첫 헤딩 앞의 글(쪽 표시뿐이면 절이 아니다)
        cuts.append((0, (), ""))
    for at, _end, depth, title in heads:
        stack = [h for h in stack if h[0] < depth]
        cuts.append((at, tuple(h[1] for h in stack)[-PATH_MAX:], title))
        stack.append((depth, title))
    out = []
    for k, (start, path, title) in enumerate(cuts):
        end = cuts[k + 1][0] if k + 1 < len(cuts) else len(text)
        for a, b in _split(text, start, end):
            if not _PAGE.sub("", text[a:b]).strip():   # 글이 없는 조각(빈 줄 · 쪽 표시뿐)은 절이 아니다
                continue
            eol = text.find("\n", a)
            page = page_at(text, a, b if eol < 0 else min(eol, b))
            inside = [p for at, p in pages if a < at < b]
            out.append({"id": f"s{len(out) + 1}", "start": a, "end": b, "page": page if page is not None else inside[0] if inside else None, "path": list(path), "title": title})
    return tuple(out)


def _split(text, start, end):
    """[start, end) 를 SEC_MAX 자 안쪽의 조각으로 — 빈 줄에서만 나눈다(빈 줄이 없는 긴 덩이는 그대로 한 조각)."""
    if end - start <= SEC_MAX:
        return [(start, end)]
    out, a, last = [], start, start
    breaks = [m.end() + start for m in re.finditer(r"\n[ \t\r　]*\n", text[start:end])]
    for b in [*breaks, end]:
        if b - a > SEC_MAX and last > a:
            out.append((a, last))
            a = last
        last = b
    out.append((a, end))
    return out


def _fold(text):
    """공백을 떼고 글자마다 소문자로([(글자, 원문 자리)]) — 구절과 자료를 **같은 접기**로 견준다(글 전체를 한 번에 소문자로 바꾸면 끝 시그마처럼 자리에 따라 달라지는 글자가 어긋난다)."""
    out = []
    for i, ch in enumerate(str(text or "")):
        if not _SPACE.match(ch):
            out.extend((c, i) for c in ch.lower())   # 소문자로 바꾸면 글자 수가 달라지는 글자(「İ」)도 자리가 어긋나지 않게
    return out


@functools.lru_cache(maxsize=24)
def _squashed(text):
    """자료 글 → 접은 글 + 그 글자마다의 원문 자리(튜플). **쪽 표시(`<!-- p.N -->`)는 자료의 글이 아니다** — 빈칸으로 가려 근거 구절이 거기 걸리지 않게 한다(자리는 그대로: astra R2 — 쪽수 「46」 이 값의 근거로 통과했다)."""
    text = _PAGE.sub(lambda m: " " * len(m.group(0)), str(text or ""))
    pairs = _fold(text)
    return "".join(c for c, _ in pairs), tuple(i for _, i in pairs)


def find_all(quote, text):
    """그 구절이 text 에 나온 자리들 [(start, end)] — 공백 · 대소문자를 접은 포함 검사 · 두 글자 이상(아니면 빈 목록). 쪽 표시의 글은 찾지 않는다."""
    q = "".join(c for c, _ in _fold(_PAGE.sub(" ", str(quote or ""))))
    if len(q) < 2:
        return []
    hay, at = _squashed(text)
    out, i = [], hay.find(q)
    while i >= 0:
        out.append((at[i], at[i + len(q) - 1] + 1))
        i = hay.find(q, i + 1)
    return out


def section_at(text, pos):
    """그 글자 자리가 든 절 | None."""
    return next((s for s in sections(text) if s["start"] <= pos < s["end"]), None)


def locate_all(quote, mats, limit=PLACES_MAX):
    """그 구절이 나온 자리들(자료 차례 · 글 차례 — limit 곳까지) + 나온 수 → ([{mat, name, start, end, sec, page, path, title}], hits). mats = [{id, name, text}]."""
    spots, hits = [], 0
    for m in mats or ():
        text = str(m.get("text") or "")
        for a, b in find_all(quote, text):
            hits += 1
            if len(spots) < limit:
                sec = section_at(text, a) or {}
                page = page_at(text, a)   # 그 구절이 놓인 쪽(절이 쪽을 넘어가면 절의 첫 쪽과 다르다) — 앞에 쪽 표시가 없으면 절의 쪽
                spots.append({"mat": m.get("id"), "name": m.get("name") or "", "start": a, "end": b, "sec": sec.get("id"), "page": page if page is not None else sec.get("page"),
                              "path": list(sec.get("path") or ()), "title": sec.get("title") or ""})
    return spots, hits


def inside(spot, spans):
    """그 자리가 실은 구간들 {자료 id: [(start, end)]} 안에 있나 — 근거 절만 실은 턴에서 「실제로 보낸 글」 의 구절인지 가린다."""
    return any(a <= spot["start"] and spot["end"] <= b for a, b in (spans or {}).get(spot.get("mat")) or ())


def locate(quote, mats, prefer=()):
    """위 머리말. mats = [{id, name, text}] — 차례대로 찾는다(prefer 의 절은 처음 PLACES_MAX 곳 안에서 고른다)."""
    want = {(e.get("mat"), e.get("sec")) for e in prefer or () if isinstance(e, dict)}
    spots, hits = locate_all(quote, mats)
    got = next((s for s in spots if (s["mat"], s["sec"]) in want), None) or (spots[0] if spots else None)
    return {**got, "hits": hits} if got else None


def ref(mat_id, sec_id):
    return f"{mat_id}/{sec_id}"


def parse_ref(text):
    """「<자료 id>/<절 id>」 → (자료 id, 절 id) | None."""
    m = _REF.match(str(text or "").strip())
    return (m.group(1), m.group(2)) if m else None


def _head_line(mat_id, s):
    where = " › ".join([*s["path"], s["title"]] if s["title"] else s["path"]) or "(제목 없음)"
    return f"[[{ref(mat_id, s['id'])} | {'p.' + str(s['page']) if s['page'] is not None else 'p.?'} | {where}]]"


def marked(mat, only=None, near=0):
    """자료 하나 → 절마다 머리 줄을 붙인 글. only = 실을 절 id 모음(None = 모두) · near = 고른 절의 앞뒤로 더 싣는 절 수."""
    text, secs = str(mat.get("text") or ""), sections(str(mat.get("text") or ""))
    if only is not None:
        idx = {k for k, s in enumerate(secs) if s["id"] in set(only)}
        keep = {j for k in idx for j in range(k - near, k + near + 1) if 0 <= j < len(secs)}
        secs = [s for k, s in enumerate(secs) if k in keep]
    return "\n\n".join(f"{_head_line(mat.get('id'), s)}\n{text[s['start']:s['end']].strip()}" for s in secs)


def toc(mat):
    """자료의 목차 — 절마다 한 줄(글 없이): 「<자료 id>/<절 id> | p.쪽 | 윗 제목 › 제목 (n자)」."""
    return "\n".join(f"{_head_line(mat.get('id'), s)[2:-2]} ({s['end'] - s['start']:,}자)" for s in sections(str(mat.get("text") or "")))


NARROW_HEAD = "(이 자리의 근거로 고른 절과 그 앞뒤 절만 실었습니다 — 이 자료의 다른 절은 아래 목차에 제목만 있습니다. 필요한 내용이 목차의 다른 절에 있어 보이면 지어내지 말고 reply 에 그 절을 적으세요)"
NARROW_TOC = "[이 자료의 목차 — 글 없이]"


CUT_TAIL = "\n(뒤는 잘림)"


def narrow(mats, evidence, cap, near=1):
    """초안 요청에 싣는 자료들 [{id, name, text, cut, narrowed, secs[실은 절 id], spans[(start, end) — 실은 절의 자료 글 자리]}] — 자료마다 그 자리의 근거 절(+ 앞뒤 near 개)과 목차. 근거 절이 없는 자료는 목차만.
    합쳐 cap 자까지 — 넘치면 **목차부터 줄이고 근거 절의 글은 앞에서부터 싣는다**(다 못 실은 절은 secs · spans 에 넣지 않는다: 실었다고 적은 절 = 실제로 실은 절 — astra R2).
    evidence = [{mat, sec}] — 모르는 자료 · 절은 버린다. 근거가 하나도 안 남으면 None(부르는 쪽이 자료 전체로).
    **머리 줄(`[[…]]`) · 목차 줄은 자리표다 — 자료의 글이 아니다**: 근거 구절 · 수 검사는 spans(자료 글의 그 구간)와 견준다(부르는 쪽 — doc_agent._evid)."""
    by = {}
    for e in evidence or ():
        if isinstance(e, dict) and e.get("mat") and e.get("sec"):
            by.setdefault(e["mat"], set()).add(e["sec"])
    known = {m.get("id"): {s["id"] for s in sections(str(m.get("text") or ""))} for m in mats or ()}
    by = {mid: secs & known.get(mid, set()) for mid, secs in by.items() if secs & known.get(mid, set())}
    if not by:
        return None
    out, left = [], max(0, int(cap))
    for m in mats or ():
        mid, text = m.get("id"), str(m.get("text") or "")
        secs = sections(text)
        idx = {k for k, s in enumerate(secs) if s["id"] in by.get(mid, ())}
        keep = [s for k, s in enumerate(secs) if any(abs(k - j) <= near for j in idx)]
        head = NARROW_HEAD if keep else "(이 자리의 근거로 고른 절이 없는 자료입니다 — 목차만)"
        parts, sent, used, cut = [head], [], len(head), False
        for s in keep:   # 근거 절의 글이 먼저 — 넘치면 그 절부터는 싣지 않는다(잘린 절을 「실었다」 고 하지 않는다)
            piece = f"\n\n{_head_line(mid, s)}\n{text[s['start']:s['end']].strip()}"
            if used + len(piece) > left:
                cut = True
                break
            parts.append(piece)
            sent.append(s)
            used += len(piece)
        tail = f"\n\n{NARROW_TOC}\n{toc(m)}"
        if used + len(tail) > left:   # 목차는 남는 몫만큼(줄 단위로)
            room, lines = left - used - len(CUT_TAIL), tail.split("\n")
            tail, cut = "", True
            for ln in lines:
                if len(tail) + len(ln) + 1 > room:
                    break
                tail += ("\n" if tail else "") + ln
            tail += CUT_TAIL if tail.strip() else ""
        body = ("".join(parts) + tail)[:left]
        left -= len(body)
        out.append({"id": mid, "name": m.get("name") or "", "text": body, "cut": bool(cut or m.get("cut")), "narrowed": True,
                    "secs": [s["id"] for s in sent], "spans": [(s["start"], s["end"]) for s in sent]})
    return out


# 차년도 · 단계 · 연도 — 수 앞이 숫자 · 소수점이면 다른 수의 일부다(「3.2차년도」 · 「2025년」 의 「25년」). 「N년차」 는 붙여 쓴 꼴만(「2025년 차세대」 의 「25년 차」 를 읽지 않는다 — astra R2)
_FIELDS = (("차년도", re.compile(r"(?<![\d.])(\d{1,2})\s*차\s*년도|(?<![\d.])(\d{1,2})년차")), ("단계", re.compile(r"(?<![\d.])(\d{1,2})\s*단계")), ("연도", re.compile(r"(?<![\d.])(20\d\d)\s*년")))
_RANGE = re.compile(r"(?<![\d.])(\d{1,4})\s*[~∼\-–]\s*$")           # 「1~2차년도」 · 「2025-2026년」 의 앞 수(그 사이도 든다)
_LIST = re.compile(r"((?:(?<![\d.])\d{1,4}\s*[·ㆍ,/]\s*)+)$")         # 「1·2차년도」 · 「1, 2단계」 의 앞 수들(나란히 적은 것)


def field_tokens(text):
    """글에 적힌 차년도 · 단계 · 연도의 값 {이름: {값…}} — 「1~2차년도」 는 1 · 2 둘 다 · 「1·2차년도」 도 둘 다."""
    t, out = str(text or ""), {}
    for name, rx in _FIELDS:
        vals = set()
        for m in rx.finditer(t):
            n = int(next(g for g in m.groups() if g))
            vals.add(n)
            before = t[:m.start()]
            span = _RANGE.search(before)
            if span and int(span.group(1)) < n <= int(span.group(1)) + 20:
                vals.update(range(int(span.group(1)), n))
            also = _LIST.search(before)
            if also:
                vals.update(int(x) for x in re.findall(r"\d{1,4}", also.group(1)))
        if vals:
            out[name] = vals
    return out


def field_clash(place_text, *levels):
    """자리의 글(머리 · 윗 제목)과 근거의 글에 적힌 차년도 · 단계 · 연도가 다른 것 [「차년도 — 자리 1 · 근거 2」] — 둘 다 적혀 있고 겹치는 값이 없을 때만.
    levels = 근거의 글들을 **가까운 것부터**(근거 구절 → 그 절의 제목 → 윗 제목 경로): 기준마다 그것을 적은 가장 가까운 글의 값으로 견준다
    (윗 제목이 「1~2차년도」 여도 그 절이 「2차년도」 면 2 · 제목에 없어도 구절이 「2차년도 …」 면 2 — astra R2). 글 하나만 주면 그 글과 견준다."""
    a, out = field_tokens(place_text), []
    toks = [field_tokens(x) for x in levels]
    for k in a:
        b = next((t[k] for t in toks if k in t), None)
        if b is not None and not (a[k] & b):
            out.append(f"{k} — 자리 {' · '.join(str(v) for v in sorted(a[k]))} · 근거 {' · '.join(str(v) for v in sorted(b))}")
    return out


def excerpt(text, start, end, around=1200):
    """그 자리 앞뒤 글 {before, hit, after, from, to} — 줄 경계에서 끊는다(around 자 안쪽)."""
    text = str(text or "")
    start, end = max(0, min(int(start), len(text))), max(0, min(int(end), len(text)))
    a = text.rfind("\n", 0, max(0, start - around)) + 1 if start > around else 0
    b = text.find("\n", min(len(text), end + around))
    b = len(text) if b < 0 else b
    return {"before": text[a:start], "hit": text[start:end], "after": text[end:b], "from": a, "to": b}

"""구간 검증 — 「LLM 검증·보완」 의 끝에 문서를 10쪽씩 나눠 구간마다 검증 에이전트가 같이 본다(spec_작업 ② §20 「구간 검증 — 10쪽씩」).

2026-11-26 사용자(이관 1단계 「04 LLM 검증·보완」 을 보며) 「한개의 에이전트로 하지 말고 첫째 2개의 에이전트가 검증보완 하고 10페이지씩 검증 에이전트를 병렬로 추가해서 처리 했으면 좋겠어」.
앞 단계(헤딩 · 템플릿 → 표)의 **지금 판정**을 구간마다 다시 읽고 틀려 보이는 곳을 「확인 필요」 로 **남긴다** — 판정을 덮지 않는다(spec_작업 ② §22 ⓐ: 스크립트 초안 · LLM 판정 · 사람 지정과 따로 선 층).
고치는 것은 사람(라벨 지정 · 헤더 지정 · 「템플릿 관계」)이나 다음 「LLM 검증·보완」 이다(검증 결과를 판정에 저절로 반영하는 것은 아직 없다 — ④).

- **구간** = 추정 쪽(`merge_chunks.page_numbers` — 한글이 저장한 쪽 나눔 표지를 믿고 표지가 없는 곳은 쌓인 높이로 어림: 한글 PDF 가 없어도 센다 · `pdf_map` 은 한글 출력이 있어야 한다)으로 PAGES 쪽씩,
  최상위 블록 단위로 가른다(표 하나는 한 블록이라 구간 사이에서 잘리지 않는다 — 그 표가 시작하는 쪽의 구간). 경계: 구간마다 그 구간 앞에서 열린 헤딩 사슬(open)과 앞뒤 구간의 가장자리 줄(before · after — 문맥일 뿐 판정 대상이 아님)을 함께 싣는다.
- **줄** = 문서 차례: 헤딩 그래프의 노드(["h", id, "T1 L3", 역할, 레터, 글, 부모]) · 표(["t", id, "행x열", 표 앞 글, {subs, heads, fields}]) · 그래프에 안 든 짧은 문단(["p", id, 글] —
  **스크립트 · 앞 판정이 헤딩으로 잡지 못한 것**: 빠진 헤딩을 찾게. 긴 본문 문단은 싣지 않는다).
- **답** = 틀려 보이는 것만 findings[{kind(heading · table · missed), id, what, suggest, sure}] — 그 구간의 줄에 있는 id 만 받는다(문맥 줄 · 모르는 id 는 버린다).
- **저장** = 작업 폴더 `analysis_check.json` {checked{구간의 판: {at, pages, n}}, finds[…]}: 항목마다 그때의 줄의 판(isig)을 적는다 — 「지금 유효한 것」 은 지금 문서 · 지금 판정의 줄과 판이 같은 것뿐
  (판정을 고치면 그 항목은 저절로 빠진다). 구간의 판이 같은 구간은 다시 묻지 않고(이어 씀), 답을 못 받은 구간은 앞 검증을 그대로 둔다(지우지 않는다 — ② §22 ⓑ ⓒ ⓓ).
순수 계산 + 저장만 — 실행(같이 돌리기 · 멈춤 · 단계 줄)은 app/analysis_llm.py `_check`."""
import hashlib
import json
import threading

from app import heading_llm as HL
from app import merge_chunks, prompt_texts, works

PAGES = 10            # 구간 하나의 쪽 수(사용자 「10페이지씩」)
EDGE = 4              # 앞뒤 구간에서 문맥으로 싣는 줄 수
TEXT, PLAIN, PLAIN_SRC = 60, 40, 80   # 헤딩 줄의 글 · 보통 문단 줄의 글 · 보통 문단을 싣는 길이 상한(이보다 긴 문단은 헤딩일 리 없어 뺀다)
FINDS_MAX, CHECKED_MAX = 60, 300
FILE = "analysis_check.json"
KINDS = {"heading": "헤딩", "table": "표", "missed": "빠진 헤딩"}
_LINE_KIND = {"h": "heading", "t": "table", "p": "missed"}
GUIDES = ("graph", "templates", "tables")   # 판단 기준 = 헤딩 지침 글(앞 단계와 같은 글 — 여기 따로 적지 않는다)
_MEM, _LOCK = {}, threading.Lock()

_S, _B = {"type": "string"}, {"type": "boolean"}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["findings", "summary"], "properties": {
    "findings": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["kind", "id", "what", "suggest", "sure"], "properties": {
        "kind": {"type": "string", "enum": list(KINDS)}, "id": _S, "what": _S, "suggest": _S, "sure": _B}}},
    "summary": _S}}

CONTRACT = """당신은 한글 양식 문서의 헤딩 · 표 판정을 **검증**하는 분석가입니다. 앞 단계(스크립트 + 두 모델의 LLM 검증·보완)가 낸 **지금 판정**을 문서의 한 구간(약 10쪽)에 대해 받습니다 — 판정을 다시 하는 것이 아니라 **틀려 보이는 곳만** 짚습니다.
lines = 그 구간의 줄(문서 차례):
- ["h", id, 슬롯, 역할, 레터, 글, 부모 id] = 헤딩 그래프의 노드. 슬롯 "T1 L3" = 템플릿 1 의 3레벨(빈 글 = 템플릿 없음), 역할 = heading · label(구분 라벨) · subtitle(괄호 소제목) · title · note · not_heading, 부모 "root" = 문서 맨 위.
- ["t", id, "행x열", 표 바로 앞 글, {subs: [[서브 테이블, 종류, 헤더 행 수, 헤더 열 수]…], heads: [헤더로 판정한 칸의 글 …], fields: 값 칸 수}] = 표 구조 판정.
- ["p", id, 글] = 헤딩 그래프에 **들지 않은** 짧은 문단(스크립트 · 앞 판정이 헤딩으로 보지 않은 줄).
open = 이 구간 앞에서 열린 헤딩 사슬(맨 위부터 — 구간 첫 헤딩의 조상), before · after = 앞뒤 구간의 가장자리 줄. 셋은 **문맥**입니다 — 경계에 걸친 헤딩 · 표를 읽는 데만 쓰고 findings 에 적지 않습니다.
findings 에는 **확인이 필요한 것만** 적습니다(문제가 없으면 빈 목록):
- kind "heading"(id = h 줄의 id): 역할이 틀림(헤딩인데 not_heading · 본문 글인데 heading · 구분 기준 값이 아닌데 label) · 부모나 레벨이 앞뒤 줄과 어긋남(같은 레터의 형제인데 레벨이 다름 · 부모가 엉뚱한 줄) · 템플릿이 갈려야 할 곳 / 갈리면 안 되는 곳.
- kind "table"(id = t 줄의 id): 헤더 행 · 열 수가 틀려 보임(값 칸이 헤더로 · 이름 칸이 값으로) · 서브 테이블 나눔이 빠졌거나 지나침.
- kind "missed"(id = p 줄의 id): 앞뒤 헤딩과 같은 꼴(같은 레터 · 같은 차례)인데 헤딩으로 잡히지 않은 줄.
what = 무엇이 틀려 보이는지 한 문장(한국어) · suggest = 어떻게 고치면 되는지 한 문장(예 「T1 L4 · 부모 h12」 「헤더 행 2」 「o 레벨 헤딩」 — 모르면 "") · sure = 줄만 봐도 분명하면 true, 의심 정도면 false.
확신이 없는 것은 적지 않습니다. 줄에 없는 id 는 쓰지 않습니다. 같은 줄을 두 번 적지 않습니다. summary = 이 구간의 판정 상태 한 문장.
아래 지침(그래프 · 템플릿 · 표 구조)은 앞 단계가 판정에 쓴 기준과 같은 글입니다 — 그 기준에 비춰 봅니다. 계약과 어긋나면 계약을 따르세요."""


def _sig(x):
    return hashlib.sha1(json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def _short(text, n):
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


def _slot(n):
    return f"T{n.get('tplNo')} L{n.get('level')}" if n.get("tplNo") is not None and n.get("level") else ""


def _head(n):
    return ["h", str(n["id"]), _slot(n), n.get("role") or "", n.get("letter") or "", _short(n.get("text"), TEXT), str(n.get("parent") or "root")]


def _table(t):
    cells = [c for c in t.get("cells") or () if isinstance(c, dict)]
    heads = [_short(c.get("text"), 14) for c in cells if c.get("role") in ("colhead", "rowhead", "corner") and (c.get("text") or "").strip()]
    subs = [[str(s.get("id") or ""), s.get("kind") or "", s.get("headerRows") or 0, s.get("headerCols") or 0] for s in t.get("subtables") or () if isinstance(s, dict)]
    return ["t", str(t["id"]), f"{t.get('rows') or 0}x{t.get('cols') or 0}", _short(t.get("before"), PLAIN),
            {"subs": subs[:8], "heads": heads[:16], "fields": sum(1 for c in cells if c.get("role") == "field")}]


def _rows(blocks, graph, tables):
    """최상위 블록 차례 → 그 블록의 줄들 [(줄 종류 h|t|p, id, 줄)] — 문서 차례."""
    at = merge_chunks.index(blocks)
    nodes, tabs = {}, {}
    for n in (graph or {}).get("nodes") or ():
        if isinstance(n, dict) and n.get("id") is not None and n.get("para") in at and not n.get("blank"):
            nodes.setdefault(at[n["para"]][0], []).append(n)
    for t in (tables or {}).get("tables") or ():
        if isinstance(t, dict) and t.get("id") is not None and (t.get("depth") or 1) == 1:
            pos = at.get(t["id"]) or at.get(t.get("host"))
            if pos:
                tabs.setdefault(pos[0], []).append(t)
    out = {}
    for i, b in enumerate(blocks):
        rows = [("t", str(t["id"]), _table(t)) for t in tabs.get(i, ())]
        mine = sorted(nodes.get(i, ()), key=lambda n: n.get("n") or 0)
        rows += [("h", str(n["id"]), _head(n)) for n in mine]
        text = " ".join(str(b.get("text") or "").split())
        if not rows and b.get("type") != "table" and text and len(text) <= PLAIN_SRC:
            rows.append(("p", str(b["id"]), ["p", str(b["id"]), _short(text, PLAIN)]))
        if rows:
            out[i] = rows
    return out


def _open(first, by_id):
    """구간 첫 헤딩의 조상 사슬(맨 위부터 — 8 까지) [[id, 슬롯, 레터, 글]]."""
    out, seen, n = [], set(), by_id.get(str(first.get("parent"))) if first else None
    while n is not None and n["id"] not in seen and len(out) < 8:
        seen.add(n["id"])
        out.append([str(n["id"]), _slot(n), n.get("letter") or "", _short(n.get("text"), PLAIN)])
        n = by_id.get(str(n.get("parent")))
    return out[::-1]


def windows(blocks, graph, tables, pages=PAGES):
    """문서 → 구간 [{no, pages[첫 쪽, 끝 쪽], lines, before, after, open, targets{kind: [id]}, isig{"kind:id": 줄의 판}, sig(구간의 판)}] — 줄이 하나도 없는 구간은 없다(모듈 설명)."""
    if not blocks:
        return []
    page = merge_chunks.page_numbers(blocks)
    rows = _rows(blocks, graph, tables)
    by_id = {str(n["id"]): n for n in (graph or {}).get("nodes") or () if isinstance(n, dict) and n.get("id") is not None}
    groups = {}
    for i in sorted(rows):
        groups.setdefault((page[i] - 1) // max(1, pages), []).append(i)
    order = sorted(groups)
    flat = {w: [r for i in groups[w] for r in rows[i]] for w in order}
    out = []
    for k, w in enumerate(order):
        items, idx = flat[w], groups[w]
        before = [ln for _, _, ln in flat[order[k - 1]][-EDGE:]] if k else []
        after = [ln for _, _, ln in flat[order[k + 1]][:EDGE]] if k + 1 < len(order) else []
        first = next((by_id.get(i) for kind, i, _ in items if kind == "h" and by_id.get(i) is not None), None)
        lines = [ln for _, _, ln in items]
        targets = {name: [i for kind, i, _ in items if _LINE_KIND[kind] == name] for name in KINDS}
        opened = _open(first, by_id)
        out.append({"no": k + 1, "pages": [page[idx[0]], page[idx[-1]]], "lines": lines, "before": before, "after": after, "open": opened, "targets": targets,
                    "isig": {f"{_LINE_KIND[kind]}:{i}": _sig(ln) for kind, i, ln in items}, "sig": _sig([lines, before, after, opened])})
    return out


def job(win, total, name=""):
    """구간 하나의 호출(llm.ask_all 의 job) — 계약 + 헤딩 지침(그래프 · 템플릿 · 표 구조) + 자료."""
    data = {"document": name, "window": {"no": win["no"], "of": total, "pages": win["pages"]}, "open": win["open"], "before": win["before"], "lines": win["lines"], "after": win["after"]}
    content, _ = HL.prompt(prompt_texts.contract(__name__, "CONTRACT"), list(GUIDES), data)
    return {"schema": SCHEMA, "content": content, "what": f"analysis-check#{win['no']}", "timeout": 600.0, "effort": "medium"}


def check(data, win):
    """LLM 답 → 받아들인 findings — 그 구간의 줄에 있는 id · 아는 kind · what 이 있는 것만(같은 줄은 한 번)."""
    out, seen = [], set()
    for f in (data or {}).get("findings") or ():
        if not isinstance(f, dict):
            continue
        kind, fid = f.get("kind"), str(f.get("id") or "")
        what = _short(f.get("what"), 200)
        if kind not in KINDS or fid not in win["targets"][kind] or (kind, fid) in seen or not what:
            continue
        seen.add((kind, fid))
        out.append({"kind": kind, "id": fid, "what": what, "suggest": _short(f.get("suggest"), 200), "sure": bool(f.get("sure"))})
    return out[:FINDS_MAX]


def empty():
    return {"v": 1, "checked": {}, "finds": []}


def merge(store, win, finds, now, model=None):
    """답을 받은 구간 하나를 저장본에 얹는다 — 그 구간의 줄에 붙어 있던 앞 항목은 새 답으로 바꾸고(그 밖의 항목은 그대로), 구간의 판을 「검증함」 으로 적는다."""
    mine = set(win["isig"])
    store["finds"] = [f for f in store["finds"] if f"{f.get('kind')}:{f.get('id')}" not in mine] + [
        {**f, "isig": win["isig"][f"{f['kind']}:{f['id']}"], "pages": list(win["pages"]), "at": now, **({"model": model} if model else {})} for f in finds]
    store["checked"][win["sig"]] = {"at": now, "pages": list(win["pages"]), "n": len(finds)}
    if len(store["checked"]) > CHECKED_MAX:   # 옛 구간의 판(문서가 바뀌어 다시 안 오는 것)부터 버린다 — 항목은 안 버린다
        keep = sorted(store["checked"].items(), key=lambda kv: kv[1].get("at") or 0)[-CHECKED_MAX:]
        store["checked"] = dict(keep)
    return store


def view(store, wins):
    """지금 문서 · 지금 판정에 유효한 것 → {pages, windows[{no, pages, checked}], left(아직 검증 안 한 구간 수), finds[…], counts{kind: 수}}. 줄의 판이 달라진 항목(판정을 고쳤거나 글이 바뀜)은 뺀다."""
    cur = {k: s for w in wins for k, s in w["isig"].items()}
    finds = [f for f in store.get("finds") or () if isinstance(f, dict) and cur.get(f"{f.get('kind')}:{f.get('id')}") == f.get("isig")]
    text = {str(ln[1]): (ln[5] if ln[0] == "h" else ln[3] if ln[0] == "t" else ln[2]) for w in wins for ln in w["lines"]}
    rows = [{"no": w["no"], "pages": w["pages"], "checked": w["sig"] in (store.get("checked") or {})} for w in wins]
    return {"pages": PAGES, "windows": rows, "left": sum(1 for r in rows if not r["checked"]),
            "finds": [{**{k: f.get(k) for k in ("kind", "id", "what", "suggest", "sure", "pages", "at")}, "name": KINDS[f["kind"]], "text": text.get(str(f["id"]), "")} for f in finds],
            "counts": {k: sum(1 for f in finds if f["kind"] == k) for k in KINDS}}


def counts_text(counts):
    """「확인 필요 7곳(헤딩 4 · 표 2 · 빠진 헤딩 1)」 | 「확인 필요 없음」."""
    n = sum(counts.values())
    return f"확인 필요 {n}곳(" + " · ".join(f"{KINDS[k]} {v}" for k, v in counts.items() if v) + ")" if n else "확인 필요 없음"


def _path(wid):
    f = works.folder(wid)
    return f / FILE if f is not None and (f / "work.json").is_file() else None


def load(wid):
    """저장본 {v, checked, finds} — 없거나 깨졌으면 빈 것."""
    p = _path(wid)
    got = (works._read_json(p) if p.is_file() else None) if p is not None else _MEM.get(wid)
    if not isinstance(got, dict) or not isinstance(got.get("checked"), dict) or not isinstance(got.get("finds"), list):
        return empty()
    return {"v": 1, "checked": dict(got["checked"]), "finds": [f for f in got["finds"] if isinstance(f, dict) and f.get("kind") in KINDS and f.get("id") is not None]}


def save(wid, store):
    with _LOCK:
        p = _path(wid)
        if p is not None:
            works._write_json(p, store)
        else:
            _MEM[wid] = store

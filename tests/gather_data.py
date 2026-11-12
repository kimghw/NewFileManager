"""취합 시험 자료(spec_취합 ② §7) — 저장소 안 자료만: 빈 계획서 양식에 값(기관 셋)을 반영한 것 = 기준본(취합본의 처음 상태), 그 사본을 고친 뒤 **저장해 다시 연** 것 = 기관 문서
(블록 id 가 기준본과 달라진다). 기준본의 추출 결과(2단계 그래프·3단계 표)는 merge_data 의 캐시(`artifacts/merge_fixture/`)를 쓴다 — 기관 문서는 분석이 필요 없다(엔진이 blocks 만 읽는다).

- `base()` = {"side": 기준본 쪽(merge_api._read 의 꼴 + bytes), "frame": merge_gather_frame.make(side)} — 프로세스에 한 번.
- `master()` = 취합본 쪽(기준본 바이트를 새로 연 문서 — 블록 id 가 기준본과 같다). 문서를 고치는 시험마다 새로 부른다. `side(doc)` = 고친 뒤 blocks 를 다시 읽은 쪽.
- `part(edit, name)` = edit(doc) 로 고친 기관 문서 쪽. 자리 찾기 도우미: `para`(글로 문단) · `nxt`(그 뒤 k째 블록) · `table_after` · `cell`."""
import re

import merge_data as M

VALUES = {"stages": [2], "orgs": {"lead": "인텍", "joint": ["가나대", "다라연"], "nonprofit": [False, True, False]},
          "period": {"start": "2026-03-01", "end": "2027-12-31"}, "current": 1}
LEAD, J1, J2 = "인텍", "가나대", "다라연"
_MEMO = {}


def base():
    if "base" not in _MEMO:
        from app import merge_gather_frame as F
        from app.division_profiles import rnd
        from app.division_profiles.rnd import core
        from app.hwpx_doc import HwpxDoc
        values = core.norm_values(VALUES)
        doc = HwpxDoc(M.PLAN_FORM.read_bytes())
        assert not core.apply(doc, values, levels_of=rnd.levels_of)["errors"]
        s = M._side("gather-frame", doc, "기준본.hwpx")
        s.update(id="master", rev=0, reasons=[], values=values, blocks=s["doc"].blocks())
        _MEMO["base"] = {"side": s, "frame": F.make(s)}
    return _MEMO["base"]


def side(doc, wid="master"):
    b = base()["side"]
    return {"id": wid, "name": wid, "rev": 0, "reasons": [], "values": b["values"], "doc": doc, "blocks": doc.blocks(), "graph": b["graph"], "tables": b["tables"]}


def master():
    from app.hwpx_doc import HwpxDoc
    return side(HwpxDoc(base()["side"]["bytes"]))


def save(doc):
    from app import hwpx_struct
    return hwpx_struct.snapshot(doc)["bytes"]


def part(edit, name="part"):
    from app.hwpx_doc import HwpxDoc
    doc = HwpxDoc(base()["side"]["bytes"])
    doc.blocks()
    edit(doc)
    data = save(doc)
    doc = HwpxDoc(data)
    return {"id": name, "name": name, "rev": 0, "reasons": [], "values": base()["side"]["values"], "doc": doc, "blocks": doc.blocks(), "graph": None, "tables": None, "bytes": data}


def _ws(t):
    return re.sub(r"\s+", " ", t or "").strip()


def top(doc):
    return [b for b in doc.blocks() if not b.get("captionOf")]


def para(doc, text, nth=0, start=False):
    """본문 최상위 문단 가운데 글(빈칸 정리)이 text 인 nth 째(start = 그 글로 시작)의 id."""
    hit = [b["id"] for b in top(doc) if b["type"] == "paragraph" and (_ws(b["text"]).startswith(text) if start else _ws(b["text"]) == text)]
    return hit[nth]


def nxt(doc, bid, k=1, kind=None):
    """bid 뒤 k 째 최상위 블록(kind 를 주면 그 종류만 센다)의 id."""
    blocks = top(doc)
    i = next(n for n, b in enumerate(blocks) if b["id"] == bid)
    return [b for b in blocks[i + 1:] if kind is None or b["type"] == kind][k - 1]["id"]


def table_after(doc, text, nth=0, start=True):
    return nxt(doc, para(doc, text, nth, start), kind="table")


def cell(doc, tid, r, c):
    """표 tid 의 (행, 열) 을 덮는 칸."""
    t = next(b for b in top(doc) if b["id"] == tid)
    return next(x for x in t["cells"] if x["row"] <= r < x["row"] + x["rowSpan"] and x["col"] <= c < x["col"] + x["colSpan"])


def texts(doc):
    return [(_ws(b.get("text")) if b["type"] == "paragraph" else b["type"]) for b in top(doc)]

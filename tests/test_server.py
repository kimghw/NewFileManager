"""서버·검증 흐름(spec_hwpx_웹편집 ② §2~§4) — 한글 없이(NFM_PDF=off) 패키지 단계, 가짜 PDF 출력으로 PDF 단계."""
import io
import time
import zipfile
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from app import pdf_map, pdf_render, server, verify

SMALL = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"


@pytest.fixture
def client():
    server.DOCS.clear()
    return TestClient(server.app)


def _wait(c, d, kind, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        v = c.get(f"/api/docs/{d}/verify").json()
        if kind in v and not v[kind]["running"]:
            return v
        time.sleep(0.1)
    raise AssertionError("검증이 끝나지 않음")


def _paras(blocks):
    out = []
    for b in blocks:
        if b["type"] == "paragraph":
            out.append(b)
        for c in b.get("cells", ()):
            out += _paras(c["blocks"])
    return out


def _upload(c, path=SMALL):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def test_upload_import_verify_without_hangul(client):
    d = _upload(client)
    v = _wait(client, d, "import")
    st = {s["key"]: s["status"] for s in v["import"]["steps"]}
    assert st["package"] == st["xml"] == st["model"] == "ok"
    assert st["pdf"] == st["map"] == st["render"] == "skip"
    assert v["import"]["status"] == "ok"


def test_unmodified_download_is_byte_identical(client):
    d = _upload(client)
    assert client.get(f"/api/docs/{d}/download").content == SMALL.read_bytes()


def test_edit_roundtrip_and_revert(client):
    d = _upload(client)
    paras = [p for p in _paras(client.get(f"/api/docs/{d}").json()["blocks"]) if p["text"].strip()]
    p = paras[3]
    r = client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★\u2028둘째 줄\t탭"}).json()
    assert r["edited"] and r["editedCount"] == 1
    saved = client.get(f"/api/docs/{d}/download").content
    assert saved != SMALL.read_bytes()
    again = {b["id"]: b["text"] for b in _paras(server.HwpxDoc(saved).blocks())}
    assert again[p["id"]] == p["text"] + "★\u2028둘째 줄\t탭"
    others = {b["id"]: b["text"] for b in _paras(server.HwpxDoc(SMALL.read_bytes()).blocks())}
    assert {i for i in others if others[i] != again.get(i)} == {p["id"]}
    # 원래 글로 되돌리면 고친 문단에서 빠진다
    r = client.post(f"/api/docs/{d}/blocks/{p['id']}/revert").json()
    assert not r["edited"] and r["editedCount"] == 0
    assert client.get(f"/api/docs/{d}").json()["edited"] == []


def test_revert_restores_original_bytes(client):
    """되돌리기는 글만이 아니라 원본 XML(줄 배치 캐시 포함)을 되놓는다 — 모두 되돌리면 저장본 = 원본 바이트(astra 검토 4)."""
    d = _upload(client)
    paras = [p for p in _paras(client.get(f"/api/docs/{d}").json()["blocks"]) if p["text"].strip()]
    a, b = paras[2], paras[5]
    for p in (a, b):
        r = client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★\t탭"}).json()
        assert r["pristine"] is False
    r = client.post(f"/api/docs/{d}/blocks/{a['id']}/revert").json()
    assert r["restored"] is True and r["editedCount"] == 1 and r["pristine"] is False
    # 남은 하나는 글을 손으로 원래대로 고쳐 넣어도(PATCH) 원본 XML 로 돌아간다
    r = client.patch(f"/api/docs/{d}/blocks/{b['id']}", json={"text": b["text"]}).json()
    assert r["restored"] is True and r["editedCount"] == 0 and r["pristine"] is True
    got = client.get(f"/api/docs/{d}/download")
    assert got.content == SMALL.read_bytes() and got.headers["x-same-as-original"] == "1"


def test_edit_verify_package_step(client):
    d = _upload(client)
    _wait(client, d, "import")
    p = next(p for p in _paras(client.get(f"/api/docs/{d}").json()["blocks"]) if p["text"].strip())
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + " 수정"})
    assert client.post(f"/api/docs/{d}/verify", json={"kind": "edit"}).status_code == 200
    v = _wait(client, d, "edit")
    ep = next(s for s in v["edit"]["steps"] if s["key"] == "epackage")
    assert ep["status"] == "ok", ep
    assert all(m.startswith("Contents/section") for m in ep["members"])
    assert {s["key"]: s["status"] for s in v["edit"]["steps"]}["epdf"] == "skip"


def test_rejects_non_hwpx(client):
    assert client.post("/api/docs", files={"file": ("a.txt", b"x")}).status_code == 400
    assert client.post("/api/docs", files={"file": ("a.hwpx", b"not a zip")}).status_code == 400


def test_media_and_samples(client):
    names = [s["name"] for s in client.get("/api/samples").json()]
    assert SMALL.name in names
    d = client.post(f"/api/samples/{SMALL.name}").json()["docId"]
    assert client.get(f"/api/docs/{d}/media", params={"name": "BinData/x.wmf"}).status_code == 415
    assert client.post("/api/samples/..%2Frequirements.txt").status_code == 404


# ---- PDF 단계: 한글 대신 블록 글로 PDF 를 만드는 가짜 출력 --------------------------------------------

def _fake_pdf(data, limit=None, fmt="hwpx"):
    """블록 글을 한 쪽에 30문단씩 찍은 PDF — 한글(docx 는 Word) PDF 처럼 글자열로 매핑·픽셀 비교가 된다."""
    out = pdf_render.render_dir()
    out.mkdir(parents=True, exist_ok=True)
    pdf = out / f"{pdf_render.sha(data)}.pdf"
    texts = [t for t in verify.flat_texts(verify.KIT[fmt][0](data).blocks()).values() if pdf_map.key_text(t)]
    doc = fitz.open()
    font = fitz.Font(fontfile="C:/Windows/Fonts/malgun.ttf") if Path("C:/Windows/Fonts/malgun.ttf").exists() else None
    lines = [t.replace("\u2028", " ").replace("\t", " ")[k:k + 40] for t in texts for k in range(0, len(t), 40)]
    for i in range(0, len(lines), 30):
        page = doc.new_page()
        tw = fitz.TextWriter(page.rect)
        for k, t in enumerate(lines[i:i + 30]):
            tw.append((40, 90 + k * 22), t, font=font, fontsize=9)
        tw.write_text(page)
    doc.save(pdf)
    return pdf


def test_pdf_steps_with_fake_renderer(client, monkeypatch):
    monkeypatch.setattr(pdf_render, "available", lambda fmt="hwpx": True)
    monkeypatch.setattr(pdf_render, "export_pdf", _fake_pdf)
    d = _upload(client)
    v = _wait(client, d, "import")
    st = {s["key"]: s for s in v["import"]["steps"]}
    assert st["pdf"]["status"] == "ok" and st["pdf"]["pages"] >= 1
    assert st["map"]["status"] == "ok", st["map"]
    assert st["render"]["status"] == "ok", st["render"]
    assert v["mapping"]["ratio"] >= 0.9
    # 고친 문단이 든 쪽만 달라진다
    paras = [p for p in _paras(client.get(f"/api/docs/{d}").json()["blocks"]) if pdf_map.key_text(p["text"])]
    target = paras[-1]
    client.patch(f"/api/docs/{d}/blocks/{target['id']}", json={"text": target["text"] + "추가글"})
    client.post(f"/api/docs/{d}/verify", json={"kind": "edit"})
    v = _wait(client, d, "edit")
    st = {s["key"]: s for s in v["edit"]["steps"]}
    assert st["epages"]["status"] == "ok", st["epages"]
    assert [x["page"] for x in st["epages"]["diffPages"]] == st["epages"]["expected"]
    assert st["etext"]["status"] == "ok", st["etext"]
    page = st["epages"]["expected"][0]
    assert client.get(f"/api/docs/{d}/pdf/original/{page}.png").headers["content-type"] == "image/png"
    assert client.get(f"/api/docs/{d}/diff/edited/{page}.png").status_code == 200


def test_pagination_follows_pdf_page_tops(tmp_path):
    """쪽 나눔(paginate): 쪽마다 하나씩, PDF 맨 위 줄과 맞거나(ok·moved) 앞 쪽에서 이어진 문단(split) — 못 맞춘 쪽 없음."""
    data = SMALL.read_bytes()
    pdf = _fake_pdf(data)
    m = pdf_map.map_blocks(server.HwpxDoc(data).blocks(), pdf, halves=False)
    assert m["pageCount"] >= 2 and [b["page"] for b in m["breaks"]] == list(range(1, len(m["breaks"]) + 1))
    assert all(c["status"] in ("ok", "moved", "split") for c in m["checks"]), m["checks"]
    assert m["agree"] >= 0.95 and m["sheets"] == list(range(1, m["pageCount"] + 1))


def test_units_keep_row_spans_together():
    """세로 병합 칸이 걸친 행은 한 단위 — 그 사이에서는 쪽을 나누지 않는다."""
    cell = lambda r, c, rs=1, t="x": {"row": r, "col": c, "rowSpan": rs, "colSpan": 1, "blocks": [{"id": f"p{r}{c}", "type": "paragraph", "text": t}]}  # noqa: E731
    tbl = {"id": "t1", "type": "table", "nRows": 4, "cells": [cell(0, 0), cell(1, 0, 2), cell(1, 1), cell(2, 1), cell(3, 0)]}
    us = pdf_map.units([{"id": "p0", "type": "paragraph", "text": "a"}, tbl])
    assert [(u["kind"], u["r0"], u["r1"]) for u in us] == [("block", None, None), ("rows", 0, 0), ("rows", 1, 2), ("rows", 3, 3)]
    assert [h["id"] for h in us[2]["heads"]] == ["p10", "p11"]


def test_rebuild_all_members_identical():
    data = SMALL.read_bytes()
    rebuilt, differ, n = verify.rebuild_all(data)
    assert not differ and n >= 3
    za, zb = (zipfile.ZipFile(io.BytesIO(x)) for x in (data, rebuilt))
    assert za.namelist() == zb.namelist()
    assert all(za.read(m) == zb.read(m) for m in za.namelist())


def test_paginate_repeated_header_row():
    """쪽마다 다시 찍힌 표 머리 행(Word·한글 반복 머리)은 그 쪽의 시작이 아니다 — 머리 아래 첫 행에서 나눈다(HAZID 42쪽·연구개발계획서 양식 31쪽)."""
    para = lambda i, t: {"id": i, "type": "paragraph", "text": t}  # noqa: E731
    cell = lambda r, c, t: {"row": r, "col": c, "rowSpan": 1, "colSpan": 1, "blocks": [para(f"c{r}{c}", t)]}  # noqa: E731
    rows = [("구분", "구체적인 내용"), ("가나다라", "첫째 행 글"), ("마바사아", "둘째 행 글"), ("자차카타", "셋째 행 글"), ("파하거너", "넷째 행 글")]
    tbl = {"id": "t1", "type": "table", "nRows": len(rows), "cells": [cell(r, c, t) for r, row in enumerate(rows) for c, t in enumerate(row)]}
    blocks = [para("p0", "제목 문단입니다"), tbl]
    line = lambda t, x, y: {"text": t, "bbox": [x, y, x + 50, y + 10]}  # noqa: E731
    pages = [{"w": 595, "h": 842, "sheet": 0, "lines": [line("제목 문단입니다", 50, 80), line("구분", 50, 100), line("구체적인 내용", 150, 100),
                                                       line("가나다라", 50, 120), line("첫째 행 글", 150, 120), line("마바사아", 50, 140), line("둘째 행 글", 150, 140)]},
             {"w": 595, "h": 842, "sheet": 1, "lines": [line("구분", 50, 80), line("구체적인 내용", 150, 80),
                                                       line("자차카타", 50, 100), line("셋째 행 글", 150, 100), line("파하거너", 50, 120), line("넷째 행 글", 150, 120)]}]
    located = {"p0": [1], **{f"c{r}{c}": [1] for r in range(3) for c in range(2)}, **{f"c{r}{c}": [2] for r in (3, 4) for c in range(2)}}
    res = pdf_map.paginate(blocks, pages, located)
    assert res["breaks"][1] == {"page": 2, "kind": "rows", "id": "t1", "row": 3}
    assert res["checks"][0]["status"] == "repeat"


def test_paginate_blank_row_after_long_row():
    """여러 쪽에 걸친 행 뒤의 글 없는 빈 행(자리 모름)을 첫 이어짐 쪽의 시작으로 잡지 않는다 — 그 행이 끝나는 쪽에서 나눈다.
    전에는 2쪽을 빈 행에서 나눠 3쪽 대조가 큰 행을 못 찾고(miss) 화면이 3쪽 몫을 앞 쪽 상자에 두었다(2026-11-18 연구계획서 요약문 표 5쪽)."""
    para = lambda i, t: {"id": i, "type": "paragraph", "text": t}  # noqa: E731
    row = lambda r, *ps: {"row": r, "col": 0, "rowSpan": 1, "colSpan": 1, "blocks": list(ps)}  # noqa: E731
    tbl = {"id": "t1", "type": "table", "nRows": 4, "cells": [
        row(0, para("a", "머리 행 글입니다")),
        row(1, para("b1", "첫째 쪽 긴 글입니다"), para("b2", "둘째 쪽 긴 글입니다"), para("b3", "셋째 쪽 긴 글입니다")),
        row(2, para("e", "")),
        row(3, para("d", "마지막 행 글입니다"))]}
    line = lambda t, y: {"text": t, "bbox": [50, y, 300, y + 10]}  # noqa: E731
    pages = [{"w": 595, "h": 842, "sheet": 0, "lines": [line("머리 행 글입니다", 80), line("첫째 쪽 긴 글입니다", 100)]},
             {"w": 595, "h": 842, "sheet": 1, "lines": [line("둘째 쪽 긴 글입니다", 80)]},
             {"w": 595, "h": 842, "sheet": 2, "lines": [line("셋째 쪽 긴 글입니다", 80), line("마지막 행 글입니다", 120)]}]
    res = pdf_map.paginate([tbl], pages, {"a": [1], "b1": [1], "b2": [2], "b3": [3], "d": [3]})
    assert res["breaks"] == [{"page": 1, "kind": "rows", "id": "t1", "row": 0}, {"page": 3, "kind": "rows", "id": "t1", "row": 2}]
    assert [c["status"] for c in res["checks"]] == ["split", "split"]


# ---- 쪽 나눔 대조: 매핑으로 거름 · 그림의 쪽(spec_hwpx_웹편집 ② §3-1 — 2026-11-18 「페이지 매칭은 왜 이렇게 잘 안맞냐」) ----
_pg_para = lambda i, t, **kw: {"id": i, "type": "paragraph", "text": t, **kw}  # noqa: E731
_pg_line = lambda t, y, x=50: {"text": t, "bbox": [x, y, x + 200, y + 10]}  # noqa: E731


def _pg_table(tid, rows):
    """rows = 행마다 칸 글 목록(칸 글이 목록이면 그 칸의 문단들) — 칸 문단 id 「<표>c<행><열>」(문단이 여럿이면 뒤에 번호)."""
    cells = []
    for r, row in enumerate(rows):
        for c, t in enumerate(row):
            ts = t if isinstance(t, list) else [t]
            cells.append({"row": r, "col": c, "rowSpan": 1, "colSpan": 1,
                          "blocks": [_pg_para(f"{tid}c{r}{c}" + (str(n) if n else ""), x) for n, x in enumerate(ts)]})
    return {"id": tid, "type": "table", "nRows": len(rows), "cells": cells}


def _pg_page(*lines, pics=None):
    return {"w": 595, "h": 842, "sheet": 0, "lines": list(lines), **({} if pics is None else {"pics": pics})}


def _pg_at(tbl, page_of_row):
    return {p["id"]: [page_of_row[c["row"]]] for c in tbl["cells"] for p in c["blocks"]}


def test_paginate_repeated_header_not_next_table_with_same_header():
    """같은 머리 행의 표 둘 — 앞 표가 다음 쪽으로 이어지며 머리를 다시 찍었으면 「뒤 표의 시작」 이 아니라 되풀이 머리다(앞 표의 그 쪽 첫 행에서 나눔).
    전에는 뒤 표의 머리 행에서 나눠 앞 표의 뒤 행이 앞 쪽 상자에 남았다(연구계획서 96·111쪽)."""
    head = ("구분", "구체적인 내용")
    t1 = _pg_table("t1", [head, ("가나다라마바사", "첫째 표 첫째 행 글"), ("아자차카타파하", "첫째 표 둘째 행 글")])
    t2 = _pg_table("t2", [head, ("거너더러머버서", "둘째 표 첫째 행 글")])
    blocks = [_pg_para("p0", "제목 문단입니다"), t1, _pg_para("p1", "둘째 표 앞 문단입니다"), t2]
    row = lambda y, a, b: [_pg_line(a, y), _pg_line(b, y, 300)]  # noqa: E731
    pages = [_pg_page(_pg_line("제목 문단입니다", 80), *row(100, *head), *row(120, "가나다라마바사", "첫째 표 첫째 행 글")),
             _pg_page(*row(80, *head), *row(100, "아자차카타파하", "첫째 표 둘째 행 글"), _pg_line("둘째 표 앞 문단입니다", 120),
                      *row(140, *head), *row(160, "거너더러머버서", "둘째 표 첫째 행 글"))]
    located = {"p0": [1], "p1": [2], **_pg_at(t1, {0: 1, 1: 1, 2: 2}), **_pg_at(t2, {0: 2, 1: 2})}
    res = pdf_map.paginate(blocks, pages, located)
    assert res["breaks"][1] == {"page": 2, "kind": "rows", "id": "t1", "row": 2}
    assert res["checks"][0]["status"] == "repeat"


def test_paginate_repeated_header_on_every_page():
    """표가 여러 쪽 이어지며 쪽마다 머리 행을 다시 찍는다 — 셋째 쪽부터는 머리 단위가 찾는 범위(앞 쪽을 시작한 행) 앞에 있다. 전에는 「못 맞춤」(miss —
    화면이 그 쪽 몫을 안 자른다: 연구계획서 87~90쪽), 이제 그 쪽들도 되풀이 머리(repeat)."""
    head = ("번호 머리", "특허 이름 머리")
    rows = [head] + [(f"{n}번째", f"{n}번째 특허의 이름입니다") for n in "일이삼사오육"]
    tbl = _pg_table("t1", rows)
    row = lambda y, r: [_pg_line(rows[r][0], y), _pg_line(rows[r][1], y, 300)]  # noqa: E731
    pages = [_pg_page(*row(80, 0), *row(100, 1), *row(120, 2)), _pg_page(*row(80, 0), *row(100, 3), *row(120, 4)), _pg_page(*row(80, 0), *row(100, 5), *row(120, 6))]
    res = pdf_map.paginate([tbl], pages, _pg_at(tbl, {0: 1, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3}))
    assert [(b["page"], b["row"]) for b in res["breaks"]] == [(1, 0), (2, 3), (3, 5)]
    assert [c["status"] for c in res["checks"]] == ["repeat", "repeat"]


def test_paginate_same_text_rows_follow_the_mapping():
    """행마다 같은 글로 시작하는 칸(「국가 공인 …」)이 쪽 맨 위 줄이면 그 글의 행이 여럿이다 — 한 번뿐인 글이 앞 쪽에 찍힌 행은 이 쪽의 첫 행이 아니다(연구계획서 23쪽)."""
    same = "국가 공인 시험기관의 환경"
    tbl = _pg_table("t1", [("번호 칸 머리", "평가 환경 머리 글"), ("첫째 평가 항목 이름", [same, "첫째 행만의 설명 글"]), ("둘째 평가 항목 이름", [same, "둘째 행만의 설명 글"])])
    pages = [_pg_page(_pg_line("번호 칸 머리", 80), _pg_line("평가 환경 머리 글", 80, 300), _pg_line("국가 공인", 100, 300), _pg_line("시험기관의 환경", 100, 420),
                      _pg_line("첫째 평가 항목 이름", 110), _pg_line("첫째 행만의 설명 글", 120, 300)),
             _pg_page(_pg_line(same, 59, 300), _pg_line("둘째 평가 항목 이름", 70), _pg_line("둘째 행만의 설명 글", 80, 300))]
    res = pdf_map.paginate([tbl], pages, _pg_at(tbl, {0: 1, 1: 1, 2: 2}))
    assert res["breaks"][1] == {"page": 2, "kind": "rows", "id": "t1", "row": 2}


def test_paginate_repeated_text_is_not_trusted():
    """같은 글의 표 둘 — 뒤 표의 칸이 앞 표의 자리(앞 쪽)로 잘못 잡혀 있어도 그 쪽을 믿고 나눔을 고치지 않는다(한 번뿐인 글만 본다 — 연구개발계획서 양식 31쪽
    「구분 · 구체적인 내용」 표 둘: 긴 글이면 다 믿던 판은 이 쪽의 나눔을 없앴다)."""
    rows = [("구분", "구체적인 내용"), ("형태와 규모", "사업화 형태를 적는 칸")]
    t1, t2 = _pg_table("t1", rows), _pg_table("t2", rows)
    blocks = [_pg_para("p0", "제목 문단입니다"), t1, t2, _pg_para("p9", "끝 문단입니다")]
    row = lambda y, r: [_pg_line(rows[r][0], y), _pg_line(rows[r][1], y, 300)]  # noqa: E731
    pages = [_pg_page(_pg_line("제목 문단입니다", 80), *row(100, 0), *row(120, 1)), _pg_page(*row(80, 0), *row(100, 1), _pg_line("끝 문단입니다", 120))]
    located = {"p0": [1], "p9": [2], **_pg_at(t1, {0: 1, 1: 1}), **_pg_at(t2, {0: 1, 1: 1})}
    res = pdf_map.paginate(blocks, pages, located)
    assert res["breaks"][1] == {"page": 2, "kind": "rows", "id": "t2", "row": 1} and res["checks"][0]["status"] == "repeat"


def test_paginate_caption_and_pictures_go_with_their_page():
    """그림에는 글이 없어 매핑이 자리를 모른다 — 캡션 · PDF 의 그림 상자로 쪽을 정한다: ① 쪽의 첫 글이 표 위 캡션(블록 차례는 표 뒤)이면 표의 첫 행부터
    ② 첫 글 줄보다 위에 그림이 있으면 첫 글 단위 앞의 그림부터(수가 안 맞으면 그대로) ③ 글 없는 쪽(쪽 가득한 그림)은 앞 쪽 뒤의 그림부터."""
    tbl = _pg_table("t1", [("나라 이름 칸", "주요 내용 설명 칸"), ("노르웨이 선급 협회", "콩스버그 설명 글입니다")])
    cap = _pg_para("cap", "< 해외 주요국 기술 동향 표 >", captionOf="t1")
    pages = [_pg_page(_pg_line("첫 쪽 본문 문단입니다", 80)),
             _pg_page(_pg_line(cap["text"], 60), _pg_line("나라 이름 칸", 80), _pg_line("주요 내용 설명 칸", 80, 300), _pg_line("노르웨이 선급 협회", 100), _pg_line("콩스버그 설명 글입니다", 100, 300))]
    res = pdf_map.paginate([_pg_para("p0", "첫 쪽 본문 문단입니다"), tbl, cap], pages, {"p0": [1], "cap": [2], **_pg_at(tbl, {0: 2, 1: 2})})
    assert res["breaks"][1] == {"page": 2, "kind": "rows", "id": "t1", "row": 0}

    img = lambda i, **kw: {"id": i, "type": "image", **kw}  # noqa: E731
    blocks = [_pg_para("p0", "첫 쪽 본문 문단입니다"), _pg_para("e1", ""), img("i1"), _pg_para("p1", "둘째 쪽 그림 아래 설명 글")]
    two = lambda pics: [_pg_page(_pg_line("첫 쪽 본문 문단입니다", 80)), _pg_page(_pg_line("둘째 쪽 그림 아래 설명 글", 220), pics=pics)]  # noqa: E731
    at = lambda pics: pdf_map.paginate(blocks, two(pics), {"p0": [1], "p1": [2]})["breaks"][1]["id"]  # noqa: E731
    assert at([[57, 57, 400, 210]]) == "i1"                          # 첫 글 줄 위의 그림 하나 = 그 앞의 그림 블록
    assert at([[57, 300, 400, 500]]) == "p1" and at(None) == "p1"    # 그림이 글 아래 · 그림 자리를 모름 — 그대로
    assert at([[57, 57, 200, 210], [220, 57, 400, 210]]) == "p1"     # 그림 둘인데 블록은 하나 — 수가 안 맞으면 그대로

    blocks = [_pg_para("p0", "첫 쪽 본문 문단입니다"), img("i1"), img("i2", pageStart=True), _pg_para("p3", "넷째 쪽 본문 문단입니다")]
    pages = [_pg_page(_pg_line("첫 쪽 본문 문단입니다", 80)), _pg_page(pics=[[57, 57, 538, 743]]), _pg_page(pics=[[57, 57, 538, 700]]), _pg_page(_pg_line("넷째 쪽 본문 문단입니다", 80))]
    res = pdf_map.paginate(blocks, pages, {"p0": [1], "p3": [4]})
    assert [(b["page"], b["id"]) for b in res["breaks"]] == [(1, "p0"), (2, "i1"), (3, "i2"), (4, "p3")]
    assert [c["status"] for c in res["checks"]] == ["blank", "blank", "ok"]

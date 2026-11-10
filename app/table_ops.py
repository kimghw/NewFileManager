"""표 행·열 편집의 형식 중립 부분(spec_owpml_편집 ② §2 「표 행·열」) — hwpx(`hwpx_struct.StructMixin.table_edit`)와 docx(`docx_struct.DocxStructMixin.table_edit`)가
함께 쓴다. 표 모듈(spec_헤딩_추출 ② §10 「모듈」, 사용자 2026-11-10 "본문 따로, 테이블 따로")의 서버 쪽 공통부 — 끝점은 `app/tables_api.py` `POST /api/docs/{id}/table`,
격자 연산은 형식마다(`hwpx_doc`·`docx_doc` + `table_grid`). 2026-11-10 astra 협의(Q6)로 `hwpx_struct` 에서 옮김 — 옛 이름은 `hwpx_struct` 에서도 보인다."""

TABLE_OPS = ("row_above", "row_below", "row_delete", "col_left", "col_right", "col_delete")


def table_range(rng, bounds, nr, nc):
    """끌어 고른 칸 묶음 {r0, c0, r1, c1}(격자 좌표, spec_owpml_편집 ② §2 「표 행·열」) -> (r0, c0, r1, c1).
    없으면 bounds(그 칸이 걸친 행·열) 그대로. 표 밖·뒤집힌 범위는 거절(표가 바뀐 뒤 옛 좌표)."""
    if not rng:
        return bounds
    try:
        r0, c0, r1, c1 = (int(rng[k]) for k in ("r0", "c0", "r1", "c1"))
    except (KeyError, TypeError, ValueError):
        raise ValueError("range 는 {r0, c0, r1, c1}(정수)여야 합니다") from None
    if not (0 <= r0 <= r1 < nr and 0 <= c0 <= c1 < nc):
        raise ValueError("고른 범위가 표 밖입니다 — 표가 바뀌었으면 칸을 다시 고르세요")
    return r0, c0, r1, c1

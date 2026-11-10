"""FMM `app.structure` 중 구분 기준 엔진이 쓰는 네 함수 — NFM 에는 `app.headings` 에 같은 것이 있다(iter_blocks·bare_bullet·is_footnote)."""
from app.headings import bare_bullet, is_footnote, iter_blocks  # noqa: F401 — 심(shim)


def index_blocks(blocks):
    return {b["id"]: b for b in iter_blocks(blocks)}

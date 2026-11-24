"""PDF 다루기(spec_양식작성 ② §3) — 자료 추출의 **스크립트 몫**: 쪽 묶음으로 나누기 · 문서 훑기(머리말 · 꼬리말 · 반복 그림 · 헤딩 참고) · 그림 후보(쪼개진 조각 합치기 · 모서리 확인) · 수식 후보 · 잘라 내기.
LLM 을 부르지 않는다(순수 — PyMuPDF · numpy).

**같은 기능의 앞선 구현을 참조했다**(2026-11-24 사용자 "workspace 에 동일한 기능이 있거든 참조해줘" — `E:\\dev\\SSCB_guidelines\\makemd`(포트 8115 · PDF → MD 변환 서버)의 `makemd/pdf_assets.py`):
머리말 · 꼬리말 찾기(`_running`) · 여러 쪽에 되풀이되는 그림 = 꾸밈(`_decorative`) · 표 영역(`tables` — find_tables) · 선 · 면 그림의 영역을 경로 좌표로 다시 셈하기(`_drawing_box` — PyMuPDF 의 rect 가 실제보다 좁게 나온다) ·
선 · 면 묶음에서 표 · 글상자 · 꾸밈선을 빼는 규칙(`_vectors`) · 캡션 힌트(`caption_of`) · 수식 줄 판정(`is_math_line` — 수식 글꼴 + 기호 밀도) · 수식 조각 · 수식 번호 묶기(`formulas`) · 납작한 그림 = 수식 그림 후보 · 헤딩 참고(책갈피 | 글꼴 크기 단계)는 그 구현의 규칙을 옮긴 것이다.
이 서버에만 있는 것 = 큰 그림 둘이 맞닿았을 때의 **이음매 확인**(`seam`) · **모서리 확인**(`settle`) · LLM 의 어림 상자 맞추기(`snap`).

- `split(pages, size, span)` → 쪽 묶음 [(첫 쪽, 끝 쪽)](1부터 · 한 묶음 SIZE 쪽까지 — LLM 의 Read 도구가 한 번에 읽는 PDF 가 20쪽까지다).
- `survey(pdf)` → 문서 전체를 한 번 훑은 것 {pages, running[머리말 · 꼬리말 글], decorative{그림 지문}, body(본문 글자 크기), tiers[글꼴 크기 단계 글], hints{쪽: [{level, size, bold, text}]}, outline[[level, title, page]], scanned[글 층이 없는 쪽]}.
- `figures(page, no, info)` → 그 쪽의 그림 후보 [{key, kind(image | vector), box, parts, caption}] — PDF 의 그림은 **쪼개져서 붙은** 것이 많다: 맞닿은 조각을 합친다(`_join` — 작은 조각 · 선 그림은 맞닿으면 합치고,
  큰 그림 둘이 맞닿았으면 이음매의 화소가 이어질 때만 `seam`). `figures.eq_images` 대신 `formula_images(page, no, info)` = 납작한 작은 그림(수식 그림 후보).
- `settle(page, box)` → **모서리 확인**: 자를 상자의 변을 **가로지르는 잉크**가 있으면(그림이 잘림) 없어질 때까지 그 변을 민다 → (상자, 변마다 "ok" | "grown" | "open"). open = 한도까지 밀어도 남음(사람이 볼 것).
- `formulas(page, no, inside, info)` → 수식 후보 [{key, box, text, src}] — 따로 선 수식 줄(분자 · 분모 · 첨자 · 수식 번호를 묶어서).
- `snap(page, box)` → LLM 이 어림으로 준 상자를 그 쪽의 그림 · 선 · 글 줄에 맞춘다. `crop(page, box, dpi)` → PNG 바이트.
상자는 PDF 점(pt) 좌표 (x0, y0, x1, y1). LLM 과 주고받는 상자는 쪽 폭 · 높이를 1000 으로 본 값(`norm` · `denorm`)."""
import io
import math
import re
from collections import Counter, defaultdict, namedtuple

SIZE = 20                 # 한 묶음의 쪽 수(LLM Read 도구의 PDF 한도)
TILE = 40.0               # 이보다 작은 변을 가진 조각 그림은 「조각」 — 맞닿으면 묻지 않고 합친다(pt)
TOUCH = 3.0               # 맞닿음으로 보는 틈(pt — 변 · 꼭짓점이 이 안으로 맞닿음)
MIN_FIG = 24.0            # 그림 후보의 가장 작은 변(pt) — 이보다 작으면 꾸밈(글머리 그림 · 점) | 수식 그림
PAGE_COVER = 0.85         # 쪽을 이만큼 덮는 그림은 바탕(스캔한 쪽) — 후보가 아니다
DPI_SCAN = 96             # 모서리 · 이음매를 보는 해상도
INK = 232                 # 이보다 어두운 회색 = 잉크(0~255)
SEAM_WHITE = 250          # 이음매를 볼 때의 종이 흰색(이보다 밝으면 흰 띠 — 옅은 바탕색의 그림이 쪼개진 것도 잡게 INK 보다 밝게 본다)
EDGE_STEP = 3.0           # 한 번에 미는 거리(pt)
EDGE_MOST = 60.0          # 한 변을 미는 한도(pt)
EDGE_INK = 0.012          # 변을 가로지르는 잉크 화소가 변 길이의 이 몫(적어도 2화소)을 넘으면 「이어진다」
PAD = 2.0                 # 자를 때 두르는 여백(pt)
MARGIN_BAND = 0.08        # 쪽의 위 · 아래 이 몫 = 머리말 · 꼬리말이 서는 띠
MATH_FONTS = ("math", "eqn", "hwpeq", "hyhwpeq", "hancomeq", "cmmi", "cmsy", "cmex", "cmbsy", "msbm", "msam", "eufm", "rsfs", "stix", "mtextra", "mt extra", "euclid", "esstix",
              "lucidamath", "xits", "asana", "txsy", "pxsy", "txmi", "pxmi", "ntxmi", "newtxmath", "wasy", "symbolmt")
FORMULA_MIN_W = 10.0      # 수식 후보의 가장 좁은 폭(pt)
Line = namedtuple("Line", "box text spans block size bold chars")
_BOLD = re.compile(r"bold|black|heavy|semibold|demi", re.I)
_PAGE_NUM = re.compile(r"^(?:[-–—]\s*)?(?:page\s*|p\.\s*)?\d{1,4}(?:\s*(?:/|of)\s*\d{1,4})?(?:\s*[-–—])?$", re.I)
_CAPTION = re.compile(r"^\s*[\[<(〈＜]?\s*(그림|사진|도표|도|표|Fig\.?|Figure|Photo|Table|Chart)\s*[\dA-Z가-힣]", re.I)
_STRONG_MATH = set("=≤≥≠≈≡∝∞∑∏∫∮√∂∇∆∈∉⊂⊃⊆⊇∪∩∀∃→⇒⇔×÷±∓′″")
_GREEK = set("αβγδεζηθικλμνξπρςστυφχψωΓΔΘΛΞΠΣΥΦΨΩϕϑϵ")
_FORMULA_PUNCT = set("0123456789.,+-−*/()[]{}^_=<>|") | _STRONG_MATH | _GREEK
_HANGUL = re.compile(r"[가-힣]")
_LONG_WORD = re.compile(r"[A-Za-z]{4,}|[가-힣]{2,}")
_TOKEN = re.compile(r"[A-Za-z]+|[가-힣]+|\d+(?:\.\d+)?|\S")
_EQNUM = r"\(\s*(?:[A-Z]{1,3}[-.]?)?\d+(?:[.\-]\d+)*[a-z]?\s*\)"
_EQNUM_END = re.compile(_EQNUM + r"$")
_PURE_EQNUM = re.compile(r"^" + _EQNUM + r"$")


def _fitz():
    import fitz
    return fitz


def open_pdf(data):
    """PDF 바이트 → fitz 문서. 못 열면 ValueError."""
    try:
        return _fitz().open(stream=data, filetype="pdf")
    except Exception as e:   # noqa: BLE001 — 깨진 파일
        raise ValueError(f"PDF 를 열 수 없습니다: {e}") from e


def split(pages, size=SIZE, span=None):
    """쪽 수 → 쪽 묶음 [(첫 쪽, 끝 쪽)](1부터). span = (첫 쪽, 끝 쪽) 이면 그 범위만."""
    a, b = span or (1, pages)
    a, b = max(1, int(a)), min(pages, int(b))
    return [(i, min(b, i + size - 1)) for i in range(a, b + 1, size)] if a <= b else []


def part(pdf, first, last):
    """쪽 묶음(1부터 · 끝 포함)만 든 PDF 바이트."""
    out = _fitz().open()
    out.insert_pdf(pdf, from_page=first - 1, to_page=last - 1)
    try:
        return out.tobytes(garbage=3, deflate=True)
    finally:
        out.close()


def norm(box, rect):
    """pt 상자 → 쪽 폭 · 높이를 1000 으로 본 정수 상자."""
    w, h = max(1.0, rect.width), max(1.0, rect.height)
    return [round((box[0] - rect.x0) / w * 1000), round((box[1] - rect.y0) / h * 1000), round((box[2] - rect.x0) / w * 1000), round((box[3] - rect.y0) / h * 1000)]


def denorm(box, rect):
    """1000 기준 상자 → pt 상자(쪽 안으로 자름). 꼴이 틀리면 None."""
    try:
        x0, y0, x1, y1 = (float(v) for v in box)
    except (TypeError, ValueError):
        return None
    x0, x1 = sorted((min(1000.0, max(0.0, x0)), min(1000.0, max(0.0, x1))))
    y0, y1 = sorted((min(1000.0, max(0.0, y0)), min(1000.0, max(0.0, y1))))
    if x1 - x0 < 5 or y1 - y0 < 3:
        return None
    return (rect.x0 + x0 / 1000 * rect.width, rect.y0 + y0 / 1000 * rect.height, rect.x0 + x1 / 1000 * rect.width, rect.y0 + y1 / 1000 * rect.height)


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a, b):
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def _gap(a, b):
    """두 상자 사이의 가로 · 세로 틈(겹치면 0)."""
    return max(0.0, max(a[0], b[0]) - min(a[2], b[2])), max(0.0, max(a[1], b[1]) - min(a[3], b[3]))


def edges_touch(a, b, tol=TOUCH):
    """두 상자의 변이나 꼭짓점이 tol 안으로 맞닿거나 겹치나 — 한 그림이 여러 조각으로 저장되면 조각들의 모서리 좌표가 서로 맞는다(가로 · 세로 · 대각선 조각 모두)."""
    dx, dy = _gap(a, b)
    return dx <= tol and dy <= tol


def touching(a, b, tol=TOUCH):
    """두 상자가 **변으로** 맞닿았나 → "x"(좌우로 맞닿음) | "y"(위아래로) | "in"(겹침) | "" — 맞닿은 변을 같이 쓰는 길이가 짧은 쪽 변의 절반은 돼야 한다(모서리만 스친 것은 아님). 큰 그림 둘의 이음매를 볼 때 쓴다."""
    ox = min(a[2], b[2]) - max(a[0], b[0])   # x 로 겹친 길이
    oy = min(a[3], b[3]) - max(a[1], b[1])
    if ox > tol and oy > tol:
        return "in"
    if -tol <= ox <= tol and oy >= 0.5 * min(a[3] - a[1], b[3] - b[1]) and oy > 0:
        return "x"
    if -tol <= oy <= tol and ox >= 0.5 * min(a[2] - a[0], b[2] - b[0]) and ox > 0:
        return "y"
    return ""


def gray(page, dpi=DPI_SCAN, clip=None):
    """쪽(또는 그 일부)을 회색 화소 배열로 → (배열 [행][열] 0~255, 배율 px/pt, 원점 (x0, y0) pt)."""
    import numpy as np
    fitz = _fitz()
    rect = page.rect if clip is None else fitz.Rect(*clip) & page.rect
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False, clip=rect)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width]
    return arr, dpi / 72.0, (rect.x0, rect.y0)


def _px(v, scale, origin):
    return int(round((v - origin) * scale))


def seam(img, scale, origin, a, b, how):
    """맞닿은 두 큰 그림의 **이음매**가 이어지나(한 그림이 쪼개진 것인가) → 참 · 거짓. how = "x"(좌우) | "y"(위아래).
    이음매 양쪽의 화소 줄을 견준다 — 둘 다 흰 띠면 따로 선 그림(거짓), 잉크가 있고 양쪽이 닮았으면 한 그림(참)."""
    import numpy as np
    h, w = img.shape
    if how == "x":
        left, right = (a, b) if a[2] <= b[2] else (b, a)
        x = _px((left[2] + right[0]) / 2, scale, origin[0])
        y0, y1 = _px(max(a[1], b[1]), scale, origin[1]), _px(min(a[3], b[3]), scale, origin[1])
        if not (2 <= x < w - 2) or y1 - y0 < 4:
            return False
        la, lb = img[max(0, y0):min(h, y1), x - 2].astype(np.int16), img[max(0, y0):min(h, y1), x + 1].astype(np.int16)
    else:
        top, bottom = (a, b) if a[3] <= b[3] else (b, a)
        y = _px((top[3] + bottom[1]) / 2, scale, origin[1])
        x0, x1 = _px(max(a[0], b[0]), scale, origin[0]), _px(min(a[2], b[2]), scale, origin[0])
        if not (2 <= y < h - 2) or x1 - x0 < 4:
            return False
        la, lb = img[y - 2, max(0, x0):min(w, x1)].astype(np.int16), img[y + 1, max(0, x0):min(w, x1)].astype(np.int16)
    if la.size < 4:
        return False
    ink = (la < SEAM_WHITE) | (lb < SEAM_WHITE)   # 옅은 바탕색도 그림이다 — 종이의 흰색만 뺀다
    if ink.mean() < 0.04:           # 이음매가 거의 흰 띠 — 따로 선 그림 둘
        return False
    return float((np.abs(la - lb)[ink] < 40).mean()) >= 0.6   # 잉크가 있는 곳의 양쪽이 닮았다 — 한 그림이 쪼개진 것


def _join(boxes, kinds=None, img=None, scale=1.0, origin=(0.0, 0.0)):
    """맞닿은 상자를 합친다 → [(합친 상자, [들어간 상자 차례])]. 작은 조각(TILE 보다 작은 변) · 선 그림끼리(kinds 의 "vector")는 모서리가 맞닿으면 합치고(`edges_touch`),
    큰 그림(래스터)은 다른 그림 · 선 그림과 겹치거나, 그림끼리 변으로 맞닿아 이음매가 이어질 때만(`seam` — img 가 있어야 본다: 나란히 놓인 따로 선 그림 둘을 한 그림으로 만들지 않는다)."""
    n = len(boxes)
    kinds = kinds or ["raster"] * n
    root = list(range(n))

    def find(i):
        while root[i] != i:
            root[i] = root[root[i]]
            i = root[i]
        return i
    small = [min(b[2] - b[0], b[3] - b[1]) < TILE for b in boxes]
    for i in range(n):
        for j in range(i + 1, n):
            if find(i) == find(j) or not edges_touch(boxes[i], boxes[j]):
                continue
            loose = small[i] or small[j] or (kinds[i] == "vector" and kinds[j] == "vector")   # 그림(래스터)과 선 그림은 겹칠 때만 — 맞닿기만 한 선 묶음이 따로 선 그림 둘을 잇는 다리가 되지 않게
            how = touching(boxes[i], boxes[j])
            if loose or how == "in" or (how and img is not None and seam(img, scale, origin, boxes[i], boxes[j], how)):
                root[find(j)] = find(i)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = []
    for ids in groups.values():
        box = boxes[ids[0]]
        for i in ids[1:]:
            box = _union(box, boxes[i])
        out.append((box, ids))
    return sorted(out, key=lambda g: (round(g[0][1] / 8), g[0][0]))


def lines_of(page):
    """그 쪽의 글 줄 [Line(box, text, spans, block, size, bold, chars)]."""
    out = []
    for b_no, blk in enumerate(page.get_text("dict").get("blocks") or ()):
        if blk.get("type") != 0:
            continue
        for ln in blk.get("lines") or ():
            spans = [s for s in ln.get("spans") or () if (s.get("text") or "").strip()]
            if not spans:
                continue
            text = "".join(s["text"] for s in ln["spans"]).strip()
            bold = all((s.get("flags", 0) & 16) or _BOLD.search(s.get("font") or "") for s in spans)
            out.append(Line(tuple(ln["bbox"]), text, spans, b_no, max(s["size"] for s in spans), bool(bold), len(text.replace(" ", ""))))
    return out


def _in_band(box, rect, frac=MARGIN_BAND):
    return box[3] <= rect.y0 + frac * rect.height or box[1] >= rect.y1 - frac * rect.height


def _running_key(text):
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", text)).strip()


def _running(rects, lines_by_page):
    """여러 쪽의 같은 자리(위 · 아래 띠)에 되풀이되는 머리말 · 꼬리말 → {지문: 글}(쪽 번호는 「#」 으로 본다 · 세 쪽 이상 · 쪽의 30% 이상)."""
    n = len(lines_by_page)
    if n < 3:
        return {}
    count, sample = Counter(), {}
    for no, lines in lines_by_page.items():
        seen = set()
        for ln in lines:
            if _in_band(ln.box, rects[no]):
                key = _running_key(ln.text)
                if key and key != "#":
                    seen.add(key)
                    sample.setdefault(key, ln.text)
        count.update(seen)
    need = max(3, math.ceil(0.3 * n))
    return {k: sample[k] for k, c in count.items() if c >= need}


def is_running(ln, rect, running):
    """그 줄이 머리말 · 꼬리말 · 쪽 번호인가."""
    return _in_band(ln.box, rect) and (_PAGE_NUM.match(ln.text) is not None or _running_key(ln.text) in running)


def _decorative(images_by_page, n):
    """여러 쪽(셋 이상 · 쪽의 절반 이상)에 되풀이되는 같은 그림(로고 등)의 지문 — 꾸밈."""
    pages = defaultdict(set)
    for no, infos in images_by_page.items():
        for im in infos:
            if im.get("digest"):
                pages[im["digest"]].add(no)
    need = max(3, math.ceil(0.5 * n))
    return {d for d, ps in pages.items() if len(ps) >= need}


def _images(page):
    try:
        return page.get_image_info(hashes=True)
    except Exception:   # noqa: BLE001 — 그림 정보를 못 읽는 쪽
        return page.get_image_info()


def _body_size(lines_by_page):
    sizes = Counter()
    for lines in lines_by_page.values():
        for ln in lines:
            for s in ln.spans:
                sizes[round(s["size"] * 2) / 2] += len(s["text"].strip())
    return sizes.most_common(1)[0][0] if sizes else 10.0


def _heading_hints(lines_by_page, body):
    """글꼴 크기 · 굵기로 본 헤딩 힌트 → ({쪽: [{level, size, bold, text}]}, [단계 글]) — 책갈피가 없는 문서에서 묶음 사이의 제목 깊이를 맞추는 참고(힌트일 뿐 헤딩이라는 증거는 아니다)."""
    cands = []
    for no, lines in lines_by_page.items():
        for ln in lines:
            if ln.chars < 2 or ln.chars > 120 or _PAGE_NUM.match(ln.text):
                continue
            if ln.size >= body * 1.12 or (ln.bold and ln.size >= body * 0.95 and ln.chars <= 90):
                cands.append((no, ln))
    merged = []
    for no, ln in cands:   # 여러 줄로 나뉜 헤딩을 합친다(같은 블록 · 같은 모양 · 잇닿음)
        if merged:
            pno, prev = merged[-1]
            if pno == no and prev.block == ln.block and abs(prev.size - ln.size) < 0.3 and prev.bold == ln.bold and 0 <= ln.box[1] - prev.box[3] < ln.size:
                merged[-1] = (no, Line(_union(prev.box, ln.box), f"{prev.text} {ln.text}", prev.spans + ln.spans, prev.block, prev.size, prev.bold, prev.chars + ln.chars))
                continue
        merged.append((no, ln))
    big = sorted({round(ln.size * 2) / 2 for _, ln in merged if ln.size >= body * 1.12}, reverse=True)
    tiers = []
    for s in big:
        if tiers and abs(tiers[-1][-1] - s) <= 0.6:
            tiers[-1].append(s)
        else:
            tiers.append([s])

    def level(ln):
        s = round(ln.size * 2) / 2
        for i, t in enumerate(tiers):
            if min(t) - 0.01 <= s <= max(t) + 0.01:
                return min(6, i + 1)
        return min(6, len(tiers) + 1)
    hints = defaultdict(list)
    for no, ln in merged:
        if len(hints[no]) < 30:
            hints[no].append({"level": level(ln), "size": round(ln.size, 1), "bold": ln.bold, "text": ln.text[:120]})
    desc = [f"{'/'.join(f'{s:g}' for s in t)}pt → 단계 {i + 1}" for i, t in enumerate(tiers)] + [f"본문 크기({body:g}pt) 굵게 → 단계 {min(6, len(tiers) + 1)}"]
    return dict(hints), desc


def survey(pdf):
    """문서 전체를 한 번 훑는다(추출을 시작할 때 한 번 — 묶음마다 이 값을 같이 쓴다) → {pages, running, keys, decorative, body, tiers, hints, outline, scanned}."""
    n = len(pdf)
    rects = {i + 1: pdf[i].rect for i in range(n)}
    raw = {i + 1: lines_of(pdf[i]) for i in range(n)}
    images = {i + 1: _images(pdf[i]) for i in range(n)}
    running = _running(rects, raw)
    kept = {no: [ln for ln in ls if not is_running(ln, rects[no], running)] for no, ls in raw.items()}
    body = _body_size(kept)
    hints, tiers = _heading_hints(kept, body)
    scanned = [no for no in range(1, n + 1) if not kept[no] and any(_area(tuple(im.get("bbox") or (0, 0, 0, 0))) >= PAGE_COVER * _area(tuple(rects[no])) for im in images[no])]
    try:
        outline = [[int(lv), str(title), int(pg)] for lv, title, pg in pdf.get_toc(simple=True)]
    except Exception:   # noqa: BLE001 — 깨진 책갈피
        outline = []
    return {"pages": n, "running": sorted(running.values())[:20], "keys": set(running), "decorative": _decorative(images, n), "body": body, "tiers": tiers, "hints": hints, "outline": outline, "scanned": scanned}


def tables(page):
    """그 쪽의 표 영역(find_tables) — 표의 괘선을 그림으로 잡지 않게 · 표 안의 줄을 수식으로 잡지 않게. 못 찾으면 빈 목록(덤이다)."""
    try:
        return [tuple(t.bbox) for t in page.find_tables().tables]
    except Exception:   # noqa: BLE001
        return []


def _drawing_box(d, rect):
    """선 · 면 하나의 영역을 경로 좌표로 다시 셈한다 — PyMuPDF 의 d["rect"] 는 하위 경로의 시작점을 빠뜨려 실제보다 좁게 나올 때가 있다(곡선은 제어점까지 품으면 안전하다)."""
    fitz = _fitz()
    xs, ys = [], []
    for it in d.get("items") or ():
        op = it[0]
        if op in ("l", "c"):
            pts = [q for q in it[1:] if isinstance(q, fitz.Point)]
        elif op == "re":
            pts = [it[1].tl, it[1].br]
        elif op == "qu":
            pts = [it[1].ul, it[1].ur, it[1].ll, it[1].lr]
        else:
            pts = []
        xs += [p.x for p in pts]
        ys += [p.y for p in pts]
    box = fitz.Rect(d["rect"])
    if xs:
        half = (d.get("width") or 0) / 2
        box |= fitz.Rect(min(xs) - half, min(ys) - half, max(xs) + half, max(ys) + half)
    return box & rect


def _vectors(page, lines=None, table_boxes=None):
    """선 · 면으로 그린 그림(벡터)의 묶음 상자 — 표의 괘선 · 글상자 · 머리말 꾸밈선 · 밑줄은 뺀다(곧은 선 · 네모뿐이면 조각이 여덟은 넘고 글이 덮은 몫이 12% 아래여야 그림 — 막대그래프는 남는다)."""
    fitz = _fitz()
    try:
        drawings = page.get_drawings()
        if not drawings or len(drawings) > 8000:
            return []
        for d in drawings:
            d["rect"] = _drawing_box(d, page.rect)
        drawings = [d for d in drawings if not d["rect"].is_empty]
        clusters = page.cluster_drawings(drawings=drawings)
    except Exception:   # noqa: BLE001 — 그리기 명령을 못 읽는 쪽
        return []
    lines = lines_of(page) if lines is None else lines
    table_boxes = tables(page) if table_boxes is None else table_boxes
    R, whole, out = page.rect, _area(tuple(page.rect)), []
    for c in clusters:
        c = fitz.Rect(c) & R
        box = tuple(c)
        if c.is_empty or c.width < MIN_FIG or c.height < MIN_FIG or _area(box) >= 0.8 * whole:
            continue                                   # 선 · 밑줄 · 작은 꾸밈 · 쪽 테두리
        if any(_inter(box, t) >= 0.5 * _area(box) for t in table_boxes):
            continue                                   # 표 테두리
        if _in_band(box, R, 0.1) and c.height < 0.1 * R.height:
            continue                                   # 머리말 · 꼬리말의 꾸밈선
        grown = c + (-1, -1, 1, 1)
        items = [it for d in drawings if grown.contains(fitz.Rect(d["rect"])) for it in d.get("items") or ()]
        curve = any(it[0] == "c" for it in items)
        diag = any(it[0] == "l" and abs(it[1].x - it[2].x) > 0.5 and abs(it[1].y - it[2].y) > 0.5 for it in items)
        cover = sum(_inter(ln.box, box) for ln in lines) / max(_area(box), 1.0)
        if not curve and not diag:
            if len(items) < 8 or cover > 0.12:
                continue                               # 곧은 선 · 네모뿐 — 단순 상자 · 표 꼴
        elif len(items) < 2 or cover > 0.4:
            continue                                   # 글상자(둥근 테두리 등)
        out.append(box)
    return out


def caption_of(box, lines):
    """그림 상자 바로 위 · 아래(40pt 안)의 캡션 줄(「그림 3 …」 · 「<표 2> …」 · 「Fig. 1 …」) | ""."""
    best = None
    for ln in lines:
        if not _CAPTION.match(ln.text) or min(box[2], ln.box[2]) - max(box[0], ln.box[0]) <= 0:
            continue
        if ln.box[1] >= box[3] - 2:
            gap = ln.box[1] - box[3]
        elif ln.box[3] <= box[1] + 2:
            gap = box[1] - ln.box[3]
        else:
            continue
        if gap <= 40 and (best is None or gap < best[0]):
            best = (gap, ln.text)
    return best[1][:200] if best else ""


def _pieces(page, info=None, lines=None, table_boxes=None):
    """그 쪽의 그림 조각 → (상자들, 종류들("raster" | "vector"), 스캔한 쪽인가) — 꾸밈 그림(여러 쪽에 되풀이)과 쪽을 덮는 바탕은 뺀다."""
    whole, R, deco = _area(tuple(page.rect)), page.rect, (info or {}).get("decorative") or ()
    boxes, kinds, scanned = [], [], False
    for im in _images(page):
        b = tuple(im.get("bbox") or ())
        if len(b) != 4:
            continue
        b = (max(b[0], R.x0), max(b[1], R.y0), min(b[2], R.x1), min(b[3], R.y1))
        if b[2] - b[0] < 1 or b[3] - b[1] < 1 or (im.get("digest") and im["digest"] in deco):
            continue
        if _area(b) >= PAGE_COVER * whole:
            scanned = True       # 쪽 전체 그림 = 스캔본 · 바탕 — 그림으로 자르지 않는다
            continue
        boxes.append(b)
        kinds.append("raster")
    for v in _vectors(page, lines, table_boxes):
        inside = [k for k, b in enumerate(boxes) if kinds[k] == "raster" and _inter(b, v) >= 0.5 * _area(b)]
        if len(inside) >= 2 and _area(v) > 3 * sum(_area(boxes[k]) for k in inside):
            continue             # 그림 여럿을 품은 훨씬 큰 선 묶음 = 그림들을 담은 틀(표 · 상자) — 후보가 아니다
        boxes.append(v)
        kinds.append("vector")
    return boxes, kinds, scanned


def _groups(page, info=None, lines=None, table_boxes=None):
    boxes, kinds, _ = _pieces(page, info, lines, table_boxes)
    if not boxes:
        return []
    img = scale = origin = None
    if sum(1 for k in kinds if k == "raster") > 1:
        img, scale, origin = gray(page)
    return [(box, "vector" if all(kinds[i] == "vector" for i in ids) else "image", len(ids), all(kinds[i] == "raster" for i in ids)) for box, ids in _join(boxes, kinds, img, scale or 1.0, origin or (0.0, 0.0))]


def figures(page, no=1, info=None, lines=None, table_boxes=None):
    """그 쪽의 그림 후보 → [{key「p<쪽>_F<n>」, kind, box(pt), parts(합친 조각 수), caption(둘레의 캡션 줄 | "")}] — 문서 차례(위 → 아래 · 왼 → 오른)."""
    lines = lines_of(page) if lines is None else lines
    cands = [(box, kind, parts) for box, kind, parts, _ in _groups(page, info, lines, table_boxes) if min(box[2] - box[0], box[3] - box[1]) >= MIN_FIG]
    return [{"key": f"p{no}_F{k + 1}", "kind": kind, "box": tuple(round(v, 2) for v in box), "parts": parts, "caption": caption_of(box, lines)} for k, (box, kind, parts) in enumerate(cands)]


def formula_images(page, info=None, lines=None, table_boxes=None):
    """납작한 작은 그림(높이 5pt 이상 · 폭이 높이의 두 배 · 16pt 이상 — 수식 편집기가 그림으로 넣은 식)의 상자들."""
    return [box for box, _, _, raster in _groups(page, info, lines, table_boxes)
            if raster and min(box[2] - box[0], box[3] - box[1]) < MIN_FIG and box[3] - box[1] >= 5 and box[2] - box[0] >= 2 * (box[3] - box[1]) and box[2] - box[0] >= 16]


def settle(page, box, most=EDGE_MOST):
    """**모서리 확인** — 상자의 변을 가로지르는 잉크가 있으면 없어질 때까지 민다 → (상자, {"left" | "top" | "right" | "bottom": "ok" | "grown" | "open"}).
    그림이 조각으로 쪼개져 일부만 잡혔거나 LLM 이 어림한 상자가 그림을 자를 때 바로잡는다. open = 한도(most pt)까지 밀어도 잉크가 남았다."""
    import numpy as np
    img, scale, origin = gray(page)
    h, w = img.shape
    R = page.rect
    x0, y0, x1, y1 = (max(R.x0, box[0]), max(R.y0, box[1]), min(R.x1, box[2]), min(R.y1, box[3]))

    def inked(side, x0, y0, x1, y1):
        """그 변을 **가로지르는** 잉크가 있나 — 변 바로 안쪽 줄과 바로 바깥 줄에서 같은 자리가 둘 다 잉크이고 빛깔이 닮은 화소(변 밖에 따로 선 글 · 옆 그림 · 표의 괘선은 가로지르지 않는다)."""
        px0, py0, px1, py1 = _px(x0, scale, origin[0]), _px(y0, scale, origin[1]), _px(x1, scale, origin[0]), _px(y1, scale, origin[1])
        px0, py0, px1, py1 = max(1, px0), max(1, py0), min(w - 1, px1), min(h - 1, py1)
        if px1 - px0 < 2 or py1 - py0 < 2:
            return False
        if side == "left":
            a, b = img[py0:py1, px0], img[py0:py1, px0 - 1]
        elif side == "right":
            a, b = img[py0:py1, px1 - 1], img[py0:py1, px1]
        elif side == "top":
            a, b = img[py0, px0:px1], img[py0 - 1, px0:px1]
        else:
            a, b = img[py1 - 1, px0:px1], img[py1, px0:px1]
        a, b = a.astype(np.int16), b.astype(np.int16)
        cross = (a < INK) & (b < INK) & (np.abs(a - b) < 48)
        return int(cross.sum()) >= max(2, int(EDGE_INK * cross.size))
    state = {}
    for side in ("left", "top", "right", "bottom"):
        moved = 0.0
        while inked(side, x0, y0, x1, y1) and moved < most:
            moved += EDGE_STEP
            if side == "left":
                x0 = max(R.x0, x0 - EDGE_STEP)
            elif side == "right":
                x1 = min(R.x1, x1 + EDGE_STEP)
            elif side == "top":
                y0 = max(R.y0, y0 - EDGE_STEP)
            else:
                y1 = min(R.y1, y1 + EDGE_STEP)
            if (side == "left" and x0 <= R.x0) or (side == "right" and x1 >= R.x1) or (side == "top" and y0 <= R.y0) or (side == "bottom" and y1 >= R.y1):
                break
        state[side] = "ok" if moved == 0 else "open" if inked(side, x0, y0, x1, y1) else "grown"
    return (round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)), state


def _mathy(font):
    f = (font or "").lower().replace("-", "").replace("_", "").replace(" ", "")
    return any(k.replace(" ", "") in f for k in MATH_FONTS)


def is_math_line(ln):
    """그 줄이 수식 줄인가 — 수식 글꼴의 몫 · 기호(= ≤ ∑ √ 그리스 글자 …)의 밀도 · 수식 번호 「(3)」 · 긴 낱말의 수로 본다(한글이 30% 넘고 수식 글꼴이 절반 아래면 글이다)."""
    text = ln.text
    chars = [c for c in text if not c.isspace()]
    n = len(chars)
    if n < 2 or _PURE_EQNUM.match(text):
        return False
    math_font = sum(len(s["text"].replace(" ", "")) for s in ln.spans if _mathy(s.get("font")))
    if len(_HANGUL.findall(text)) / n > 0.3 and math_font / n < 0.5:
        return False
    if math_font / n >= 0.4:
        return True
    long_words = len(_LONG_WORD.findall(text))
    sym = sum(1 for c in chars if c in _STRONG_MATH or c in _GREEK)
    if not any(c in "=≤≥≠≈≡<>" for c in text):
        return long_words == 0 and sym / n >= 0.3
    italic_short = sum(len(s["text"].strip()) for s in ln.spans if (s.get("flags", 0) & 2) and 0 < len(s["text"].strip()) <= 3)
    if long_words <= 2 and (sym + italic_short) / n >= 0.25:
        return True
    if _EQNUM_END.search(text) and long_words <= 3:
        return True
    formula = sum(len(t) for t in _TOKEN.findall(text) if t in _FORMULA_PUNCT or t[0].isdigit() or (t.isascii() and t.isalpha() and len(t) <= 3))
    return long_words == 0 and formula / n >= 0.7


def _components(n, connected):
    root = list(range(n))

    def find(i):
        while root[i] != i:
            root[i] = root[root[i]]
            i = root[i]
        return i
    for i in range(n):
        for j in range(i + 1, n):
            if find(i) != find(j) and connected(i, j):
                root[find(j)] = find(i)
    out = defaultdict(list)
    for i in range(n):
        out[find(i)].append(i)
    return list(out.values())


def formulas(page, no=1, inside=(), info=None, lines=None, table_boxes=None):
    """그 쪽의 수식 후보 → [{key「p<쪽>_E<n>」, box(pt), text(그 자리의 글 — 깨진 글자일 수 있다), src("text" 글 줄 | "raster" 수식 그림)}].
    따로 선 수식 줄(`is_math_line`)을 분자 · 분모 · 첨자 조각(가로 1.5em · 세로 0.45em 안)과 오른쪽의 수식 번호까지 묶는다. 문단 한가운데 끼인 줄(앞뒤로 긴 글)은 글 속 수식이라 뺀다.
    그림 후보(inside — 상자들) · 표 안의 줄 · 머리말 · 꼬리말은 보지 않는다. 납작한 작은 그림(수식 그림)도 후보다."""
    lines = lines_of(page) if lines is None else lines
    table_boxes = tables(page) if table_boxes is None else table_boxes
    running = (info or {}).get("keys") or ()
    exclude = [tuple(b) for b in inside] + list(table_boxes)
    usable = [ln for ln in lines if not is_running(ln, page.rect, running) and not any(_inter(ln.box, r) >= 0.6 * max(1.0, _area(ln.box)) for r in exclude)]
    flags = {id(ln): is_math_line(ln) for ln in usable}
    by_block = defaultdict(list)
    for ln in usable:
        by_block[ln.block].append(ln)

    def sandwiched(ln):
        blk = by_block[ln.block]
        i = next(k for k, x in enumerate(blk) if x is ln)
        prose = lambda x: not flags[id(x)] and x.chars >= 15  # noqa: E731
        return any(prose(x) for x in blk[:i]) and any(prose(x) for x in blk[i + 1:])
    math_lines = [ln for ln in usable if flags[id(ln)] and not sandwiched(ln)]
    groups = []
    if math_lines:
        eqnums = [ln for ln in usable if _PURE_EQNUM.match(ln.text)]
        small = [ln for ln in usable if not flags[id(ln)] and ln.chars <= 3 and not _PURE_EQNUM.match(ln.text) and not _PAGE_NUM.match(ln.text)]
        cand, is_math = math_lines + small, [True] * len(math_lines) + [False] * len(small)

        def near(i, j):
            size = max(cand[i].size, cand[j].size)
            dx, dy = _gap(cand[i].box, cand[j].box)
            return dx <= 1.5 * size and dy <= 0.45 * size
        for comp in _components(len(cand), near):
            if not any(is_math[i] for i in comp):
                continue
            members = [cand[i] for i in comp]
            box = members[0].box
            for m in members[1:]:
                box = _union(box, m.box)
            for en in eqnums:   # 오른쪽에 떨어져 선 수식 번호 (1) · (3.2)
                ov = min(box[3], en.box[3]) - max(box[1], en.box[1])
                if ov >= 0.5 * (en.box[3] - en.box[1]) and en.box[0] >= box[0]:
                    box = _union(box, en.box)
                    members.append(en)
            if sum(m.chars for m in members) < 3 or box[3] - box[1] > 0.4 * page.rect.height or box[2] - box[0] < FORMULA_MIN_W:
                continue
            groups.append((box, "text"))
    groups += [(b, "raster") for b in formula_images(page, info, lines, table_boxes) if not any(_inter(b, r) >= 0.6 * max(1.0, _area(b)) for r in exclude)]
    groups.sort(key=lambda g: (round(g[0][1]), g[0][0]))
    fitz = _fitz()
    return [{"key": f"p{no}_E{k + 1}", "box": tuple(round(v, 2) for v in box), "src": src, "text": " ".join(page.get_text("text", clip=fitz.Rect(*box)).split())[:200]} for k, (box, src) in enumerate(groups)]


def snap(page, box):
    """LLM 이 어림으로 준 상자(pt)를 그 쪽에 있는 것에 맞춘다 — 상자와 절반 넘게 겹치는 그림 · 선 묶음 · 글 줄을 다 품게 넓힌다(아무것도 없으면 그대로)."""
    out = box
    things = [tuple(im["bbox"]) for im in page.get_image_info() if len(im.get("bbox") or ()) == 4]
    lines = lines_of(page)
    things += _vectors(page, lines)
    things += [ln.box for ln in lines]
    whole = _area(tuple(page.rect))
    for t in things:
        if 0 < _area(t) < PAGE_COVER * whole and _inter(t, box) >= 0.5 * _area(t):
            out = _union(out, t)
    return out


def crop(page, box, dpi=200, pad=PAD):
    """상자를 PNG 로 → (PNG 바이트, 폭 px, 높이 px). 긴 변이 2400px 를 넘으면 해상도를 낮춘다."""
    fitz = _fitz()
    rect = fitz.Rect(box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad) & page.rect
    longest = max(rect.width, rect.height) * dpi / 72.0
    if longest > 2400:
        dpi = max(72, int(dpi * 2400 / longest))
    pix = page.get_pixmap(dpi=dpi, alpha=False, clip=rect)
    return pix.tobytes("png"), pix.width, pix.height


def blank(png):
    """잘라 낸 그림이 거의 빈 종이인가(잉크 0.2% 아래) — 빈 자리를 그림으로 넣지 않게."""
    import numpy as np
    from PIL import Image
    arr = np.asarray(Image.open(io.BytesIO(png)).convert("L"))
    return float((arr < INK).mean()) < 0.002

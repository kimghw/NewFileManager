"""그림 도구의 순수 로직(spec_그림 ② §2~§4 · §7) — 그림 줄이기(LLM 에 보낼 꼴) · 선명하게 · 소속 헤딩 · 앞뒤 글 · 캡션 예 · LLM 계약 둘(그림 → 표 · 그림 캡션).

문서를 바꾸지 않는다 — 문서를 바꾸는 것은 `app/hwpx_pic.py`(HwpxDoc 믹스인), 끝점은 `app/pic_tools_api.py`.
LLM 은 `llm.call(…, images=[…])` 로 그림을 함께 읽는다(답은 미리보기 — 넣기는 사람이 옆 열에서)."""
import io
import json

from PIL import Image, ImageFilter, ImageOps

from app import caption_tpl
from app import headings as H
from app import llm
from app import table_make as M

RASTER = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}
LLM_SIDE = 2000             # LLM 에 보내는 그림의 긴 변(화소) 상한 — 넘으면 줄인다
LLM_BYTES = 3_500_000       # PNG 가 이보다 크면 JPEG 로(API 한도 5MB · base64 로 부푼다)
MAX_PIXELS = 25_000_000     # 선명하게의 결과 상한(가로 × 세로)
LEVELS = {"normal": {"dpi": 220, "radius": 1.2, "percent": 110, "contrast": False},
          "strong": {"dpi": 300, "radius": 2.0, "percent": 170, "contrast": True}}
UPSCALE_MAX = 4.0
EXAMPLES_MAX = 8
NEAR_BEFORE, NEAR_AFTER, NEAR_TEXT = 3, 2, 200
PATH_TEXT = 80


def ext_of(name):
    return (name or "").rsplit(".", 1)[-1].lower() if name and "." in name else ""


def is_raster(name):
    return ext_of(name) in RASTER


# ---------------------------------------------------------------- 그림 바이트
def _open(data):
    im = Image.open(io.BytesIO(data))
    im.load()
    if getattr(im, "n_frames", 1) > 1:   # 움직이는 gif 는 첫 장
        im.seek(0)
    return im


def for_llm(data: bytes) -> dict:
    """LLM 에 보낼 그림 {data, media, w, h} — 긴 변 LLM_SIDE 안으로 줄이고 PNG(크면 JPEG)."""
    im = _open(data)
    if im.mode not in ("RGB", "L"):
        bg = Image.new("RGB", im.size, "white")
        rgba = im.convert("RGBA")
        bg.paste(rgba, mask=rgba.getchannel("A"))
        im = bg
    side = max(im.size)
    if side > LLM_SIDE:
        f = LLM_SIDE / side
        im = im.resize((max(1, round(im.width * f)), max(1, round(im.height * f))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    media = "image/png"
    if buf.tell() > LLM_BYTES:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=90)
        media = "image/jpeg"
    return {"data": buf.getvalue(), "media": media, "w": im.width, "h": im.height}


def enhance(data: bytes, ext: str, width_mm: float | None, level: str = "normal") -> dict:
    """선명하게(② §4) → {data, ext, w, h, before: (w, h), scale}. 표시 폭(mm)에서 목표 화소를 셈해 작으면 키우고(LANCZOS · 최대 4배) 언샤프 마스크(+ 강하게는 자동 대비)."""
    lv = LEVELS.get(level) or LEVELS["normal"]
    im = _open(data)
    before = im.size
    keep_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
    im = im.convert("RGBA" if keep_alpha else "RGB")
    scale = 1.0
    if width_mm and width_mm > 0:
        want = width_mm / 25.4 * lv["dpi"]
        scale = max(1.0, min(UPSCALE_MAX, want / max(1, im.width)))
        while scale > 1.0 and im.width * im.height * scale * scale > MAX_PIXELS:
            scale = max(1.0, scale * 0.9)
    if scale > 1.05:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    else:
        scale = 1.0
    if keep_alpha:
        a = im.getchannel("A")
        rgb = im.convert("RGB").filter(ImageFilter.UnsharpMask(radius=lv["radius"], percent=lv["percent"], threshold=2))
        if lv["contrast"]:
            rgb = ImageOps.autocontrast(rgb, cutoff=0.5)
        rgb.putalpha(a)
        im = rgb
    else:
        im = im.filter(ImageFilter.UnsharpMask(radius=lv["radius"], percent=lv["percent"], threshold=2))
        if lv["contrast"]:
            im = ImageOps.autocontrast(im, cutoff=0.5)
    out_ext = "jpg" if ext.lower() in ("jpg", "jpeg") and not keep_alpha else "png"
    buf = io.BytesIO()
    if out_ext == "jpg":
        im.save(buf, "JPEG", quality=95)
    else:
        im.save(buf, "PNG", optimize=True)
    return {"data": buf.getvalue(), "ext": out_ext, "w": im.width, "h": im.height, "before": before, "scale": round(scale, 2)}


# ---------------------------------------------------------------- 문서에서 읽기(웹 블록)
def _one(text, n):
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _siblings(blocks, bid):
    """bid 가 든 형제 목록(본문 또는 한 칸의 블록) | None."""
    for b in blocks:
        if b.get("id") == bid:
            return blocks
        if b.get("type") == "table":
            for c in b.get("cells") or ():
                got = _siblings(c.get("blocks") or [], bid)
                if got is not None:
                    return got
    return None


def heading_path(blocks, bid, lv=None) -> list[str]:
    """그림(블록 bid)의 소속 헤딩 경로 — 문서 차례에서 bid 바로 앞의 본문 헤딩부터 부모 사슬을 따라 뿌리까지(위 → 아래 · 글 PATH_TEXT 자). 스크립트(headings.levels)만."""
    lv = lv or H.levels(blocks)
    levels, parents = lv["levels"], lv["parents"]
    texts, last = {}, None
    for b in H.iter_blocks(blocks):
        if b.get("id") == bid:
            break
        if b.get("type") == "paragraph" and b["id"] in levels:
            last = b["id"]
            texts[b["id"]] = b.get("text") or ""
    out, seen = [], set()
    while last and last not in seen:
        seen.add(last)
        out.append(_one(texts.get(last), PATH_TEXT))
        last = parents.get(last)
    return out[::-1]


def _block_text(b):
    if b.get("type") == "paragraph":
        return b.get("text") or ""
    if b.get("type") == "table":
        return " | ".join(_one(c.get("text"), 30) for c in sorted(b.get("cells") or (), key=lambda c: (c["row"], c["col"]))[:12])
    return ""


def around(blocks, bid) -> dict:
    """그림의 앞뒤 글 {before: [앞 3 문단], after: [뒤 2 문단]} — 같은 형제 목록에서 글이 있는 문단(표는 첫 칸 몇 개)만, 캡션 문단은 뺀다."""
    sib = _siblings(blocks, bid) or []
    i = next((k for k, b in enumerate(sib) if b.get("id") == bid), -1)
    if i < 0:
        return {"before": [], "after": []}

    def take(rng, n):
        got = []
        for k in rng:
            b = sib[k]
            if b.get("captionOf") or b.get("type") == "image":
                continue
            t = _one(_block_text(b), NEAR_TEXT)
            if t:
                got.append(t)
            if len(got) >= n:
                break
        return got
    return {"before": take(range(i - 1, -1, -1), NEAR_BEFORE)[::-1], "after": take(range(i + 1, len(sib)), NEAR_AFTER)}


def _text_caption_of(sib, i, kind):
    """형제 목록 sib 의 i 번째 개체(표 · 그림)에 붙은 글 캡션 문단 | None — 그림은 바로 아래 · 표는 바로 위(사이 빈 줄 하나까지)."""
    step = 1 if kind == "image" else -1
    k, gap = i + step, 0
    while 0 <= k < len(sib):
        b = sib[k]
        if b.get("captionOf") == sib[i].get("id"):
            k += step
            continue
        if b.get("type") != "paragraph":
            return None
        if not (b.get("text") or "").strip():
            gap += 1
            if gap > 1:
                return None
            k += step
            continue
        return b if caption_tpl.parse(b.get("text"), struct=False) else None
    return None


def captions(blocks) -> dict:
    """{개체 id: {"kind": image|table, "object": [캡션 문단 블록], "text": 글 캡션 블록 | None}} — 문서의 모든 표 · 그림."""
    out = {}

    def walk(items):
        for i, b in enumerate(items):
            if b.get("type") in ("image", "table") and not b.get("inlineOf"):
                obj = [x for x in items if x.get("captionOf") == b["id"]]
                out[b["id"]] = {"kind": b["type"], "object": obj, "text": _text_caption_of(items, i, b["type"])}
            if b.get("type") == "table":
                for c in b.get("cells") or ():
                    walk(c.get("blocks") or [])
    walk(blocks)
    return out


def has_caption(blocks, bid, caps=None) -> bool:
    c = (caps or captions(blocks)).get(bid)
    return bool(c and (any((x.get("text") or "").strip() for x in c["object"]) or c["text"]))


def caption_examples(blocks, kind, caps=None) -> list[str]:
    """이 문서의 캡션 예(kind = image | table) — 개체 캡션의 첫 글 줄 · 글 캡션, 겹치지 않게 EXAMPLES_MAX 개까지."""
    out = []
    for c in (caps or captions(blocks)).values():
        if c["kind"] != kind:
            continue
        first = next(((x.get("text") or "").strip() for x in c["object"] if (x.get("text") or "").strip()), "")
        for t in (first, (c["text"] or {}).get("text") or ""):
            t = _one(t, 120)
            if t and t not in out:
                out.append(t)
        if len(out) >= EXAMPLES_MAX:
            break
    return out[:EXAMPLES_MAX]


def context(blocks, bid) -> dict:
    """LLM 자료의 문서 쪽 — {heading: [경로], around, caption: 지금 캡션 글 | "", examples: {image: [...], table: [...]}}."""
    caps = captions(blocks)
    c = caps.get(bid) or {}
    now = "\n".join((x.get("text") or "").strip() for x in c.get("object") or () if (x.get("text") or "").strip())
    if not now and c.get("text"):
        now = c["text"].get("text") or ""
    return {"heading": heading_path(blocks, bid), "around": around(blocks, bid), "caption": now,
            "examples": {"image": caption_examples(blocks, "image", caps), "table": caption_examples(blocks, "table", caps)}}


# ---------------------------------------------------------------- LLM 계약
S, I = {"type": "string"}, {"type": "integer"}


def _schema(props):
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


_GRID = _schema({"headerRows": I, "headerCols": I, "footRows": I,
                 "rows": {"type": "array", "items": _schema({"cells": {"type": "array", "items": _schema({"text": S, "rowSpan": I, "colSpan": I})}})}})
TABLE_SCHEMA = _schema({"tables": {"type": "array", "items": _GRID}, "caption": {"type": "array", "items": S}, "note": S})
CAPTION_SCHEMA = _schema({"caption": S, "note": S})

TABLE_CONTRACT = f"""당신은 한글(hwpx) 문서의 편집자입니다. 앞에 붙은 **그림**은 표를 찍거나 캡처한 그림입니다. 그림 안의 표를 문서의 진짜 표로 옮길 수 있게 격자로 답합니다.
괘선·음영·글자 모양 같은 서식은 스크립트가 「표 양식」(이 문서의 표 하나)에서 따오므로 당신은 **표의 구조와 칸 글만** 정합니다.
- tables: 그림 안의 표를 위에서 아래로(나란히 있으면 왼쪽부터) 하나씩. 표마다 rows = 위에서 아래로 행 목록, 행마다 cells = 왼쪽에서 오른쪽으로 칸(윗행에서 rowSpan 으로 내려온 자리는 건너뜀).
  칸 = text(칸 글 — 칸 안 줄 바꿈은 "\\n"), rowSpan, colSpan(안 합친 칸은 1, 1). 모든 행의 가로 칸 수(colSpan 합 + 위에서 내려온 자리)가 같아야 합니다.
  headerRows = 위쪽 열 제목 행 수 · headerCols = 왼쪽 행 제목 열 수(그림에서 음영·굵은 글로 보이는 제목 칸) · footRows = 아래쪽 합계 행 수(없으면 0).
- 칸 글은 그림에 보이는 글을 **한 글자도 고치지 않고** 옮깁니다(요약·번역·맞춤법 고침·보탬 금지 — 빈 칸은 빈 글). 한 칸 안에서 줄이 넘어간 것이 칸 폭 때문이면 이어 쓰고(URL · 경로는 빈칸 없이 붙여), 일부러 나눈 줄이면 "\\n".
  읽을 수 없는 글자는 짐작하지 말고 그대로 비우거나 읽은 만큼만 쓰고 note 에 어느 칸인지 적습니다.
- caption: 그림 안에서 **표 밖에 있는 글**(표 위·아래의 제목 · 설명 줄)을 위에서 아래로 한 줄씩 — 첫 줄이 제목입니다. 글은 그림에 보이는 그대로 옮깁니다. 표 밖 글이 없으면 자료의 「지금 캡션」 이나 「소속 헤딩」 을 보고
  표의 제목 한 줄을 지어도 됩니다(그림·자료에 없는 사실은 쓰지 않음). 자료의 「표 캡션 예」 가 있으면 제목 줄은 그 꼴(괄호 「< … >」 · 「<표 N>」 같은 머리)을 따릅니다 — 번호의 수는 예를 따라 짓지 말고 그림에 보이는 번호만 씁니다.
- 그림이 표가 아니면(사진 · 도식 · 그래프) tables 를 빈 목록으로 두고 note 에 까닭을 씁니다.
- note = 판단 요약 한두 문장(한국어 — 표를 몇 개로 읽었는지, 못 읽은 곳이 있으면 어디인지).
표는 하나에 {M.ROWS_MAX}행 × {M.COLS_MAX}열 이내."""

CAPTION_CONTRACT = """당신은 한글(hwpx) 문서의 편집자입니다. 앞에 붙은 **그림**에 붙일 캡션(그림 아래의 제목 한 줄)을 짓습니다.
- 그림을 보고, 자료의 「소속 헤딩」(이 그림이 들어 있는 절의 제목 — 위에서 아래로)과 「앞뒤 글」 에서 이 그림이 무엇을 보이는지 읽어 짧은 제목으로 씁니다(보통 40자 안 — 명사구).
- 그림·헤딩·앞뒤 글에 없는 사실·수·이름을 짓지 않습니다. 그림 안에 제목 글이 있으면 그것을 먼저 씁니다.
- 자료의 「그림 캡션 예」(이 문서에 이미 있는 그림 캡션)가 있으면 그 꼴을 따릅니다 — 괄호(「< 제목 >」 · 「[그림 N] 제목」), 빈칸, 문체. 예에 번호가 있으면 같은 머리를 쓰되 번호의 수는 「N」 으로 둡니다(사람이 고칩니다).
  예가 없으면 「< 제목 >」 꼴로 씁니다.
- caption = 캡션 한 줄(예의 꼴 그대로 — 괄호 포함) · note = 무엇을 근거로 지었는지 한 문장(한국어)."""


def _data(payload):
    return "\n\n## 자료(JSON)\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def table_prompt(ctx, template) -> str:
    payload = {"소속 헤딩": ctx.get("heading") or [], "앞뒤 글": ctx.get("around") or {}, "지금 캡션": ctx.get("caption") or "",
               "표 캡션 예": (ctx.get("examples") or {}).get("table") or [], "표 양식": template}
    return TABLE_CONTRACT + _data(payload)


def caption_prompt(ctx) -> str:
    payload = {"소속 헤딩": ctx.get("heading") or [], "앞뒤 글": ctx.get("around") or {}, "그림 캡션 예": (ctx.get("examples") or {}).get("image") or []}
    return CAPTION_CONTRACT + _data(payload)


def _info(res):
    return {k: res.get(k) for k in ("backend", "model", "effort", "ms", "costUsd", "error")}


def ask_table(image, ctx, template, *, call=None, timeout=240.0) -> dict:
    """그림 → 표 한 번(잠금 밖) → {"tables": [정규화한 격자], "caption": [줄], "note", "dropped": [못 쓴 표의 까닭], "call"}. 답이 없으면 tables [] · call.error."""
    res = (call or llm.call)(TABLE_SCHEMA, table_prompt(ctx, template), "pic-table", timeout=timeout, images=[image])
    out = {"tables": [], "caption": [], "note": "", "dropped": [], "call": _info(res)}
    data = res.get("data")
    if not isinstance(data, dict):
        return out
    for k, g in enumerate(data.get("tables") or ()):
        try:
            out["tables"].append(M.normalize(g))
        except ValueError as e:
            out["dropped"].append(f"{k + 1}번째 표: {e}")
    out["caption"] = [str(x).strip() for x in data.get("caption") or () if str(x).strip()][:6]
    out["note"] = str(data.get("note") or "").strip()
    return out


def ask_caption(image, ctx, *, call=None, timeout=180.0) -> dict:
    """그림 캡션 한 번(잠금 밖) → {"caption", "note", "call"}."""
    res = (call or llm.call)(CAPTION_SCHEMA, caption_prompt(ctx), "pic-caption", timeout=timeout, images=[image])
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    return {"caption": " ".join(str(data.get("caption") or "").split())[:200], "note": str(data.get("note") or "").strip(), "call": _info(res)}

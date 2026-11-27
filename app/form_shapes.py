"""양식 서식 점검(spec_양식작성 ② §5-11) — 양식의 **상자(본문 최상위 1칸 표)** 안에서 서식이 이웃과 다른 쓸 자리 줄을 찾아 「서식 수정」 · 「삭제」 를 제안하는 순수 계산. 문서를 고치지 않는다.
2026-11-27 사용자(04 「에이전트 기반 문서 구조 및 작성 지침 보완」 카드를 보이며) "여기에 이상한 서식들을 삭제 제안하는 기능이 있어야 할거 같아. 레터가 없거나 이런건 서식을 수정해야 하고," · "문서 자체가 좀 이상하긴 하지"
— 글머리가 개요 번호(한글이 찍는 「○」 · 「-」)인 양식에 글머리 없는 빈 줄 · 다른 서식으로 친 「    - 」 줄이 섞여 있어, 채운 항목들의 글머리 · 글꼴이 줄마다 달라졌다. 아래 가름은 에이전트 판단(사용자 확인 전).

찾는 것(상자에 **한글이 글머리를 찍는 줄**(`form_slots` 의 num)이 하나라도 있을 때만 — 그 상자의 「보통 서식」 을 그것으로 본다). 줄 = 머리 아래에 잇따르는 쓸 자리(빈 줄 · 글머리 줄)와
**이미 채운 자리**(올린 원본에서 쓸 자리였던 줄 — orig 를 줬을 때):
- `bare` **글머리 없는 줄** — 글머리가 안 찍히는 서식의 빈 줄(또는 그런 빈 줄을 채운 줄)이고, 바로 앞(없으면 바로 뒤)의 줄이 글머리가 찍히는 줄인 것.
  제안 = 서식 수정(그 이웃 줄의 서식으로 — 글머리가 찍힌다 · 글은 그대로). 상자의 **끝에 남은** 빈 줄(뒤에 아무 블록도 없다 — 끝 여백)은 보지 않는다.
- `typed` **친 글머리 줄** — 글머리 · 「:」 만 친 줄(`form_slots` 의 stub: 「    - 」 · 「  : 」)과 그 줄을 채운 줄(글이 올린 원본의 첫머리 그대로 시작할 때만). 친 글머리와 같은 글머리를 한글이 찍는 줄이 문서에 있으면
  제안 = 서식 수정(친 첫머리를 지우고 그 줄의 서식으로 — 가장 가까운 줄 · 뒤에 쓴 글은 그대로) · 없으면 제안 = 삭제(「  : 」 — 맞출 서식이 없다).
사람은 줄마다 「서식 수정」(맞출 줄이 있을 때) · 「삭제」(글이 없는 줄만 — 채운 줄은 지우지 않는다) · 「그대로」 가운데 고른다 — 반영은 사람이 고른 줄만(form_shapes_api).

- `find(blocks, levels=None, orig=None)` → {"items": [{id, box, kind, raw, filled(채운 줄), propose("restyle" | "delete"), options[…], like(맞출 줄 id | None), likeNum(그 줄의 글머리), likeText, likeStyle,
  text(서식 수정 뒤의 글 — 바뀔 때만: 친 첫머리를 지운 글), head(그 줄 위의 머리 글), why, sig(그 줄 · 맞출 줄의 지문 — 본 것과 반영할 때가 같은지)}], "counts": {bare, typed, restyle, delete, total}}."""
import hashlib

from app import form_slots as FS

RAW_MAX = 60


def _short(t, n=RAW_MAX):
    t = t or ""
    return t if len(t) <= n else t[:n - 1] + "…"


def _sig(*parts):
    return hashlib.sha256("\x1f".join("" if p is None else str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


def _paras(blocks):
    """문서의 모든 문단 블록(문서 차례 — 표 칸 안까지) [(차례, 블록)]."""
    out = []

    def walk(bs):
        for b in bs or ():
            if b.get("type") == "paragraph":
                out.append(b)
            for c in b.get("cells") or ():
                walk(c.get("blocks"))
    walk(blocks)
    return out


def _num(b):
    return b.get("outlineNum") or (b.get("list") or {}).get("label")


def _letter(raw):
    """친 글머리 줄의 글머리 글자(빈칸을 뺀 글 — 「    - 」 → 「-」 · 「  : 」 → 「:」)."""
    return "".join((raw or "").split())


def _slotish(e):
    """쓸 자리 줄인가 → "blank" | "stub"(지금 그 종류거나, 올린 원본에서 그 종류였고 지금은 채운 줄) | None."""
    k = e["kind"] if e["kind"] in ("blank", "stub") else e.get("was") if e["kind"] == "filled" else None
    return k if k in ("blank", "stub") else None


def find(blocks, levels=None, orig=None):
    """위 머리말. blocks = 문서 블록(HwpxDoc.blocks()) · levels = {문단 id: 헤딩 그래프의 레벨} · orig = {문단 id: 올린 원본의 원문}(채운 줄을 가린다 — 없으면 채운 줄은 보지 않는다)."""
    paras = _paras(blocks)
    at = {b["id"]: i for i, b in enumerate(paras)}
    by_num = {}
    for b in paras:
        if (n := _num(b)):
            by_num.setdefault(n.strip(), []).append(b)
    items = []
    for top in blocks or ():
        cell = FS.box_cell(top)
        if cell is None:
            continue
        direct = {b["id"]: b for b in cell.get("blocks") or () if b.get("type") == "paragraph"}
        ents = FS.entries(cell, levels, orig)
        if not any(e.get("num") for e in ents if e.get("raw") is not None):
            continue   # 한글이 글머리를 찍는 줄이 없는 상자 — 「보통 서식」 을 정할 수 없다
        last = max((i for i, e in enumerate(ents) if e["kind"] != "blank" or e.get("num")), default=-1)   # 그 뒤는 상자 끝의 글머리 없는 빈 줄(끝 여백)
        head, run, runs = None, [], []
        for i, e in enumerate(ents):
            k = e["kind"]
            if _slotish(e):
                if head is not None:
                    run.append((i, e))
                continue
            if run:
                runs.append((head, run))
            run = []
            head = e if k in ("label", "check", "text", "filled") else None   # 안쪽 표 · 그림 · 안내 · 캡션은 잇달음을 끊는다(form_slots.chunks 와 같은 규칙)
        if run:
            runs.append((head, run))
        for head, run in runs:
            name = head.get("orig", head["raw"]).strip()
            for k, (i, e) in enumerate(run):
                b, was = direct.get(e["id"]), _slotish(e)
                filled = e["kind"] == "filled" and FS.kind_of(e["raw"]) not in ("blank", "stub")   # 글을 쓴 줄 — 첫머리의 빈칸만 달라진 글머리 줄(「    - 」 → 묶음 빈칸)은 아직 쓸 자리다
                if b is None:
                    continue
                if was == "blank" and not e.get("num"):
                    if i > last or e["raw"].lstrip()[:1] in FS.BULLETS:
                        continue   # 상자 끝의 여백 · 빈 줄에 레터를 쳐 넣은 줄(사람 · 다른 도구가 고친 줄 — 서식만 바꾸면 친 레터와 찍히는 레터가 겹친다)
                    near = next((x for _, x in (run[k - 1] if k else (0, None), run[k + 1] if k + 1 < len(run) else (0, None)) if x is not None and _slotish(x) == "blank" and x.get("num")), None)
                    if near is None:
                        continue
                    what = "이 줄은" if filled else "이 빈 줄은"
                    items.append(_item(top["id"], "bare", b, e, direct[near["id"]], name, f"앞뒤 줄은 한글이 레터 「{near['num']}」 를 찍는데 {what} 레터가 안 찍히는 서식입니다", filled))
                elif was == "stub" and not e.get("num"):
                    first = (e.get("orig", e["raw"])).rstrip(" ")   # 친 첫머리(앞 빈칸 + 글머리) — 채운 줄은 올린 원본의 것
                    if filled and not e["raw"].startswith(first):
                        continue   # 채운 뒤 첫머리가 바뀐 줄(사람 · 다른 도구가 고침) — 어디까지가 친 글머리인지 모른다
                    letter = _letter(first)
                    cands = [x for x in by_num.get(letter, ()) if x["id"] != b["id"]]
                    like = min(cands, key=lambda x: abs(at[x["id"]] - at[b["id"]])) if cands else None
                    if like is None and filled:
                        continue   # 채운 줄은 지우지 않는다 — 맞출 서식이 없으면 제안도 없다
                    why = (f"레터 「{letter}」 를 글로 친 줄입니다 — 이 문서에는 한글이 「{letter}」 를 찍는 서식의 줄이 있습니다" if like is not None
                           else f"레터 「{letter}」 만 친 줄입니다 — 이 문서에 그 레터를 찍는 서식이 없어 맞출 줄이 없습니다")
                    items.append(_item(top["id"], "typed", b, e, like, name, why, filled, e["raw"][len(first):].strip() if like is not None else None))
    counts = {k: sum(1 for it in items if it["kind"] == k) for k in ("bare", "typed")}
    counts.update({k: sum(1 for it in items if it["propose"] == k) for k in ("restyle", "delete")}, total=len(items))
    return {"items": items, "counts": counts}


def _item(box, kind, b, e, like, head, why, filled=False, text=None):
    return {"id": b["id"], "box": box, "kind": kind, "raw": e["raw"], "filled": filled, "style": b.get("style"), "propose": "restyle" if like is not None else "delete",
            "options": (["restyle"] if like is not None else []) + ([] if filled else ["delete"]), "like": like["id"] if like is not None else None, "likeNum": _num(like) if like is not None else None,
            "likeText": _short((like.get("text") or "").strip()) if like is not None else None, "likeStyle": like.get("style") if like is not None else None, "head": _short(head), "why": why,
            **({"text": text} if text is not None else {}),
            "sig": _sig(kind, e["raw"], b.get("style"), _num(b), like["id"] if like is not None else "", like.get("style") if like is not None else "", _num(like) if like is not None else "")}

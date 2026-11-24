"""상자 안의 쓸 자리(spec_양식작성 ② §5-3) — 양식의 **상자(본문 최상위 1칸 표)** 안 문단을 「머리 + 그 아래 쓸 자리」 덩이로 읽는 순수 계산. 문서를 고치지 않는다.
2026-11-24 사용자 "작성은 어디서 하는거야?"(쓸 곳이 상자 안 · 같은 줄 뒤인 양식에서 초안이 0개) · "바디랑 헤딩 추출하는 도구는 사용하고 있나?" — 상자 안 줄의 레벨은 헤딩 추출의 그래프(area box)가 매긴 것을 그대로 싣는다
(따로 다시 읽지 않는다). astra 협의(artifacts/form_fill_slots_astra_2026-11-24/) — 아래 가름은 에이전트 판단(사용자 확인 전).

- `box_cell(block)` → 그 블록이 상자(1칸 표)면 그 칸 | None.
- `entries(cell, levels)` → 칸의 **직접** 블록 차례 [{id, raw(원문 — 앞뒤 빈칸 그대로), kind, level}] — 안쪽 표 · 그림은 {id, kind: "table" | "image", size}(자리만 — 경계).
  kind: `blank`(빈칸뿐) · `stub`(글머리 · 「:」 뿐 — 「    - 」 · 「  : 」) · `label`(「… : 」 로 끝남) · `check`(「□」 가 둘 이상) · `note`(※ 안내) · `caption`(캡션 문단 · 「그림 1 …」) · `text`(그 밖 — 제목 · 「000」 · 「개발목표 작성」).
- `chunks(entries)` → 덩이 [{no, head(label · check · text 문단), slots[잇따르는 blank · stub 문단], dup(같은 머리 글의 덩이 가운데 [몇 번째, 몇 개])}] — 안쪽 표 · 그림 · 안내 · 캡션은 자리의 잇달음을 끊는다.
- `targets(chunks)` → 채울 수 있는 문단 {id: {raw, kind, chunk(no), head(머리 글), dup, nth(덩이 안 몇째 줄 — 머리 = 0)}} — 머리(label · check · text)와 자리(blank · stub). 안내 · 캡션 · 안쪽 표의 문단은 없다.
- `line_slot(block, orig_raw)` → 본문 문단 하나가 같은 줄에 값을 쓰는 자리인가: "label" | "check" | "filled" | None.
- 한번 채운 자리: 올린 원본의 원문(orig)을 주면, 원본에서 쓸 자리였고 지금 글이 든 줄은 kind "filled" — 덩이는 그대로 읽히되 다시 쓰는 대상이 아니다.
- `judge(raw, new)` → 그 문단의 새 글 판정 ("append" 붙이기 — 지금 글 뒤에 덧붙임 · "replace" 바꾸기 · "check" 표시 하나, 값 부분) | 버릴 까닭(str).
- `view_text(chunks)` → LLM 에 싣는 줄들(양식 검토의 양식 글 · 문서 에이전트의 selection)."""
import re

BULLETS = set("-–—·⋅•∙oOㅇ○●□■▷▶◇◆*:：")
CHECK_OFF, CHECK_ON = "□", "■☑☒▣√✔✓"
STUB_MAX = 2   # 글머리 줄 = 글머리 · 「:」 가 둘까지(「-」 · 「o」 · 「- :」) — 「------」(구분선) · 「■ □」(기호 줄)은 쓸 자리가 아니다(astra 3차)
RAW_MAX = 200
_CAPTION = re.compile(r"^\s*[<\[(〈]?\s*(?:그림|표|사진|도)\s*\d")


def box_cell(block):
    """본문 최상위 블록이 상자(1칸 표)면 그 칸."""
    if not isinstance(block, dict) or block.get("type") != "table":
        return None
    cells = block.get("cells") or []
    return cells[0] if len(cells) == 1 and (block.get("nRows") or 1) == 1 and (block.get("nCols") or 1) == 1 else None


def kind_of(raw, caption=False):
    t = (raw or "").strip()
    if not t:
        return "blank"
    if caption or _CAPTION.match(t):
        return "caption"
    if t.startswith("※"):
        return "note"
    if sum(1 for i in _marks(t) if t[i] == CHECK_OFF) >= 2:   # 표시할 「□」 가 둘 이상 — 첫 글자의 □ · ■ 는 그 뒤에 제목이 있을 때만 글머리다(_marks)
        return "check"
    if all(ch in BULLETS or ch.isspace() for ch in t):
        return "stub" if sum(1 for ch in t if not ch.isspace()) <= STUB_MAX else "text"
    if t.endswith((":", "：")):
        return "label"
    return "text"


def was_kind(raw, orig_raw):
    """올린 원본에서는 쓸 자리였는데 지금은 글이 든 줄인가 → 원본에서의 종류(blank · stub · label · check) | None. 한번 채운 자리의 역할을 잃지 않으려는 것(astra 2차 「빠뜨린 1」 —
    「■ 주관연구개발기관 : 」 에 값을 채우면 글이 「:」 로 끝나지 않아 보통 헤딩으로 읽히고, 다시 돌리면 그 아래에 같은 값을 또 쓴다)."""
    if orig_raw is None or orig_raw == raw:
        return None
    k = kind_of(orig_raw)
    return k if k in ("blank", "stub", "label", "check") and (raw or "").strip() else None


def entries(cell, levels=None, orig=None):
    """칸의 직접 블록 차례 — 위 머리말. levels = {문단 id: 헤딩 그래프의 레벨}(없으면 None) · orig = {문단 id: 올린 원본의 원문}(없으면 None — 채운 자리를 가리지 않는다):
    원본에서 쓸 자리였고 지금 글이 든 줄은 kind "filled"(was = 원본에서의 종류) — 다시 쓰는 대상이 아니다."""
    out = []
    for b in (cell or {}).get("blocks") or ():
        kind = b.get("type")
        if kind == "paragraph":
            raw = b.get("text") or ""
            was = was_kind(raw, (orig or {}).get(b["id"])) if orig is not None else None
            out.append({"id": b["id"], "raw": raw, "kind": "filled" if was else kind_of(raw, bool(b.get("captionOf"))), "level": (levels or {}).get(b["id"]), **({"was": was, "orig": orig[b["id"]]} if was else {})})
        elif kind == "table":
            out.append({"id": b["id"], "kind": "table", "size": f"{b.get('nRows')}×{b.get('nCols')}"})
        else:
            out.append({"id": b.get("id"), "kind": "image"})
    return out


def chunks(ents):
    """덩이 — 위 머리말. 머리 없는 앞쪽 빈 줄은 자리가 아니다(무엇의 자리인지 모른다)."""
    out, cur = [], None
    for e in ents or ():
        k = e["kind"]
        if k in ("label", "check", "text") or (k == "filled" and e.get("was") in ("label", "check")):
            cur = {"no": len(out) + 1, "head": e, "slots": []}
            out.append(cur)
        elif k in ("blank", "stub"):
            if cur is not None:
                cur["slots"].append(e)
        elif k == "filled":   # 채운 자리 — 덩이는 이어지고(그 아래 빈 줄은 같은 머리의 것) 다시 쓰는 대상은 아니다
            pass
        else:   # 안쪽 표 · 그림 · 안내 · 캡션 — 자리의 잇달음을 끊는다
            cur = None
    seen, above = {}, []   # 같은 머리 글이어도 윗 제목(헤딩 그래프의 레벨로 본 부모)이 다르면 다른 자리다 — 「연구개발 목표」 아래의 「000」 과 「연구개발 내용 및 범위」 아래의 「000」
    for c in out:
        lv = c["head"].get("level")
        while above and lv and above[-1][0] >= lv:
            above.pop()
        c["under"] = above[-1][1] if above and lv else ""
        c["name"] = c["head"].get("orig", c["head"]["raw"]).strip()
        c["group"] = above[-1][2] if above and lv else ""   # 윗 제목의 **이름**(채운 윗 제목은 올린 원본의 글) — 같은 이름 자리의 묶음은 이것으로 본다: 윗 제목 하나를 채웠다고 그 아래의 같은 이름 자리가 풀리지 않게(astra 3차)
        if lv:
            above.append((lv, c["head"]["raw"].strip(), c["name"]))   # 덩이의 이름 = 머리 글 — 채운 머리는 올린 원본의 글로(같은 이름의 자리 둘 가운데 하나를 채워도 남은 자리는 여전히 「같은 이름」 이다: 누구의 것인지는 사람이 정한다)
        seen.setdefault((c["name"], c["group"]), []).append(c)
    for same in seen.values():
        for k, c in enumerate(same, 1):
            c["dup"] = [k, len(same)]
    return out


def targets(chs):
    """채울 수 있는 문단 — 위 머리말."""
    out = {}
    for c in chs or ():
        head = c["head"]["raw"].strip()
        for nth, e in enumerate([c["head"], *c["slots"]]):
            if e["kind"] == "filled":
                continue
            out[e["id"]] = {"raw": e["raw"], "kind": e["kind"], "chunk": c["no"], "head": head, "under": c.get("under") or "", "dup": c["dup"], "nth": nth, "level": e.get("level")}
    return out


def line_slot(block, orig_raw=None):
    """본문 문단 하나가 같은 줄에 값을 쓰는 자리인가 → "label" | "check" | "filled"(올린 원본에서는 그런 자리였고 지금은 값이 있다 — orig_raw 를 줬을 때만) | None."""
    if not isinstance(block, dict) or block.get("type") != "paragraph":
        return None
    raw = block.get("text") or ""
    if was_kind(raw, orig_raw) in ("label", "check"):
        return "filled"
    k = kind_of(raw)
    return k if k in ("label", "check") else None


def _lead(text):
    """첫 글자(글머리)의 자리 — 앞 빈칸을 건넌 곳. kind_of 가 앞 빈칸을 떼고 「첫 글자는 글머리」 로 보는 것과 같은 자리(들여 쓴 「  ■ … ( □ … □ … )」 의 ■ 를 표시로 세지 않게)."""
    return len(text) - len(text.lstrip())


def _marks(text):
    """표시 기호(□ · ■ · ☑ …)의 자리들 — 첫 글자의 기호는 **그 뒤에 제목이 있을 때만** 글머리로 보고 뺀다(「■ 작성 기준 보고서 ( □ … □ … )」: 첫 기호와 다음 기호 사이에 「(」 · 「:」 가 있다).
    「■ 연차 □ 최종 □ 기타」 처럼 첫 기호부터 선택지면 그것도 표시다(astra 3차 — 전에는 첫 ■ 를 글머리로 빼서 「이미 표시한 줄」 을 못 가렸다)."""
    at = [i for i, ch in enumerate(text) if ch == CHECK_OFF or ch in CHECK_ON]
    if len(at) >= 2 and at[0] == _lead(text) and any(ch in "(（:：" for ch in text[at[0] + 1:at[1]]):
        return at[1:]
    return at


def _options(text):
    """표시 줄의 선택지 [(기호 자리, 항목 이름)] — 항목 이름 = 그 기호 뒤부터 다음 기호 앞까지(끝의 닫는 괄호 · 구분 기호는 뗀다: 「□ 정규(형식) 승인 □ 정규(형식) 미승인」 의 괄호는 이름의 것이다)."""
    at, out = _marks(text), []
    for k, i in enumerate(at):
        name = text[i + 1:at[k + 1] if k + 1 < len(at) else len(text)].strip().rstrip(",·/|")
        while name.count(")") > name.count("(") and name.rstrip().endswith(")"):
            name = name.rstrip()[:-1]
        out.append((i, name.strip()))
    return out


def judge(raw, new, kind=None):
    """그 문단의 새 글 판정 → ("append" | "replace" | "check", 값) | 버릴 까닭(str). raw · new 는 원문(빈칸 그대로)."""
    raw, new = raw or "", (new or "").replace("\r", "").replace("\n", " ")
    kind = kind or kind_of(raw)
    if new.strip() == raw.strip():
        return "지금 글과 같습니다"
    if kind == "check":
        if len(new) != len(raw):
            return "표시 줄은 「□」 하나만 바꿉니다(글을 더하거나 빼지 않습니다)"
        diff = [i for i, (a, b) in enumerate(zip(raw, new)) if a != b]
        if any(raw[i] in CHECK_ON for i in _marks(raw)):
            return "이미 표시한 항목이 있습니다 — 사람이 확인합니다"
        names = dict(_options(raw))
        if len(diff) != 1 or raw[diff[0]] != CHECK_OFF or new[diff[0]] not in CHECK_ON or diff[0] not in names:
            return "표시 줄은 「□」 하나만 「■」 로 바꿉니다"
        return "check", names[diff[0]]
    base = raw if kind in ("label", "stub") else raw.rstrip() if kind == "blank" else None
    if base is not None:
        if kind == "blank":   # 빈 줄 — 무엇이든(앞 빈칸은 새 글의 것)
            return "append", new.strip()
        keep = base.rstrip() if kind == "label" else base.rstrip(" ")
        if new.startswith(keep) and new[len(keep):].strip():
            return "append", new[len(keep):].strip()
        return ("replace", new.strip()) if kind == "label" else "글머리 줄은 그 첫머리(빈칸 · 글머리) 뒤에 씁니다"
    return "replace", new.strip()


def _short(text, n=RAW_MAX):
    return text if len(text) <= n else text[:n - 1] + "…"


def view_text(ents, chs=None, only=None):
    """LLM 에 싣는 줄들 — 문단마다 「[id] (L레벨) 원문」 · 빈 줄 묶음은 「[id…] (빈 줄 n)」 · 안쪽 표 · 그림은 자리만. 원문의 앞 빈칸은 그대로 둔다(따옴표 안).
    only = 이번 턴에 쓸 수 있는 문단 id 들(None = 가리지 않음) — 그 밖의 쓸 자리는 「이번에는 쓰지 않는 자리」 로 적는다(사람이 고르지 않은 덩이 · 같은 이름 자리의 다른 쪽: 2026-11-24 실제 실행에서
    LLM 이 고르지 않은 「공동」 자리에 써서 줄이 모두 버려졌다 — 보낸 글이 어느 자리가 열렸는지 말해 줘야 한다)."""
    ok = (lambda i: True) if only is None else (lambda i: i in only)
    lines, run, headed = [], [], [False]   # headed = 지금 덩이의 머리가 있는가(머리 없는 앞쪽 빈 줄 · 표 · 캡션 뒤의 빈 줄은 쓸 자리가 아니다 — chunks 와 같은 규칙)

    def flush():
        if run:
            lv = run[0].get("level")
            on = [e for e in run if ok(e["id"])]
            if headed[0] and on:
                lines.append(f"  [{' '.join(e['id'] for e in on)}] (쓸 자리 — 빈 줄 {len(on)}{f' · L{lv}' if lv else ''})")
            if headed[0] and len(on) < len(run):
                lines.append(f"  (이번에는 쓰지 않는 자리 — 빈 줄 {len(run) - len(on)})")
            if not headed[0]:
                lines.append(f"  (빈 줄 {len(run)})")
            run.clear()

    for e in ents or ():
        k = e["kind"]
        if k == "blank":
            run.append(e)
            continue
        flush()
        headed[0] = k in ("label", "check", "text", "stub") and (headed[0] or k != "stub") or (k == "filled" and (headed[0] or e.get("was") in ("label", "check")))
        if k == "table":
            lines.append(f"  [표 {e['id']} {e.get('size')} — 표 · 그림 자리: 여기서는 채우지 않습니다]")
        elif k == "image":
            lines.append("  [그림]")
        else:
            lv = f"(L{e['level']}) " if e.get("level") else ""
            tag = {"stub": "쓸 자리 — 글머리 줄", "label": "쓸 자리 — 같은 줄 뒤에 값", "check": "쓸 자리 — 표시 줄", "note": "안내 — 채우지 않음", "caption": "캡션 — 채우지 않음", "filled": "이미 채움 — 다시 쓰지 않음", "text": ""}[k]
            if k == "stub" and not headed[0]:
                tag = ""
            elif k in ("stub", "label", "check") and not ok(e["id"]):
                tag = "이번에는 쓰지 않는 자리"
            lines.append(f"  [{e['id']}] {lv}「{_short(e['raw'])}」" + (f" ({tag})" if tag else ""))
    flush()
    return "\n".join(lines)

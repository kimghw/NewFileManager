"""같은 양식 취합 — 등록부 · 원장 · 수정본의 3방향 셈(spec_취합 ② §10). **순수** — 문서를 고치지 않고 다른 app 코드는 merge_pairs(글 정리 · 기관 이름 꼴)만 가져온다.

2026-11-24 사용자 "1개 사업계획서 그리고 N개의 제출된 문서를 가지고 사업계획서에 넣고,, 사업계획서에 넣은 기관들의 내용은 현재 구역으로 관리 하고,, 수정된 문서가 오면 이전 제출된 내용과 비교해서 수정된 부분만 적용".

- **등록부**(목적 작업 폴더 `collect.json` — 저장은 app/merge_collect_api.py): `{version, order[기관 문서 작업 id], parts{id: {orgs[기관 이름 꼴], orgsBy: user|name|label|"", common: bool, revOf: 앞 제출본 id | None, added,
  done{at, rev, srcRev, version, counts, left} | None}}}`. `clean(G)` = 꼴 정리 · `chain(G, part)` = 그 문서의 앞 제출본들(가까운 것부터).
- **자동 지정** `auto_org(name, others, values, labels)` → (기관 이름 꼴 | None, by, 까닭): ① 파일 이름에 든 프로젝트 기관 이름이 하나(모든 문서 이름에 든 이름은 뺀다 — 과제 이름에 든 기관) ② 문서의 기관 라벨이 밝힌 이름이 하나뿐.
  파일 이름과 라벨이 서로 다른 기관을 가리키면 미지정(짐작하지 않는다).
- **원장 줄**(출처 이벤트의 `led` — app/zones_api.py origin_add 의 extra): `[목적 id, 원본 id, 원본 글 | None, 넣은 직후 목적 글 | None, 자리(목적 항목 key | 표 id), 원본 레터 | None]`. 글이 None = 단순 문단 · 칸이 아님(표 · 그림 블록) — 수정본이 저절로 못 고친다.
- **수정본**(3방향 — 밑 = 원장의 원본 글 S1 · 들어오는 것 = 수정본 S2 · 내 것 = 지금 목적 문서 T):
  `cell_item(row, s2, t_now)` · `body_items(rows, new, t_now, order)` → 항목 [{kind: cell|para|add, to, from, status, was, text, detail, …}].
  status: `ready`(S2 가 바뀌었고 T 가 넣은 그대로 — 고친다) · `same`(T 가 이미 S2 의 글) · `overlap`(T 를 사람이 고침 — 그대로 둠) · `hold`(확인 필요 — 저절로 못 정함) · `missing`(수정본에 그 자리 · 그 줄이 없음 — 그대로 둠: **지우지 않는다**).
  S2 가 S1 과 같으면 항목을 내지 않는다(사람이 T 에서 고친 것을 건드리지 않는다)."""
import difflib

from app import merge_pairs as P

BY = ("user", "name", "label")
STATUS = ("ready", "same", "overlap", "hold", "missing")
STATUS_NAME = {"ready": "고칠 곳", "same": "이미 같음", "overlap": "겹침(사람이 고친 자리 — 그대로 둠)", "hold": "확인 필요", "missing": "수정본에 없음(그대로 둠)"}


def blank():
    return {"version": 0, "order": [], "parts": {}}


def clean(G):
    """저장된 등록부 → 정리한 꼴(틀린 값은 버린다 · 없는 문서를 가리키는 revOf 는 None)."""
    if not isinstance(G, dict) or not isinstance(G.get("parts"), dict):
        return blank()
    parts = {}
    for k, p in G["parts"].items():
        if not isinstance(k, str) or not isinstance(p, dict):
            continue
        orgs = [o for o in p.get("orgs") or () if isinstance(o, str) and o]
        parts[k] = {"orgs": list(dict.fromkeys(orgs)), "orgsBy": p.get("orgsBy") if p.get("orgsBy") in BY and orgs else "", "common": p.get("common") is True,
                    "revOf": p.get("revOf") if isinstance(p.get("revOf"), str) else None, "added": p.get("added"), "done": p.get("done") if isinstance(p.get("done"), dict) else None}
    for k, p in parts.items():
        if p["revOf"] not in parts or p["revOf"] == k or k in chain({"parts": parts}, p["revOf"]):
            p["revOf"] = None
    order = [k for k in dict.fromkeys(G.get("order") or ()) if k in parts]
    order += [k for k in parts if k not in order]
    v = G.get("version")
    return {"version": v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0, "order": order, "parts": parts}


def chain(G, part):
    """그 문서의 앞 제출본들(가까운 것부터 — revOf 를 따라간다 · 고리는 끊는다) — 수정본의 밑(S1 과 그 조상)."""
    out, seen, cur = [], {part}, ((G.get("parts") or {}).get(part) or {}).get("revOf")
    while cur and cur not in seen and cur in (G.get("parts") or {}):
        out.append(cur)
        seen.add(cur)
        cur = G["parts"][cur].get("revOf")
    return out


def later(G, part):
    """그 문서를 앞 제출본으로 둔 수정본들(바로 뒤 것만) — 수정본이 있는 문서는 넣기 대상이 아니다(뒤 것이 맡는다)."""
    return [k for k in G.get("order") or () if ((G.get("parts") or {}).get(k) or {}).get("revOf") == part]


def auto_org(name, others, values, labels):
    """반영할 기관 자동 지정 → (기관 이름 꼴 | None, "name" | "label" | "", 까닭). name = 그 문서의 파일 이름 · others = 같은 묶음의 다른 문서 이름들(목적 문서 포함) ·
    labels = 그 문서의 기관 라벨이 밝힌 프로젝트 기관 이름 꼴의 모음."""
    keys = [k for k in dict.fromkeys(P.org_key(n) for _, n in P._orgs(values)) if k] if (values or {}).get("orgs") else []
    labels = {k for k in labels or () if k in keys}
    everywhere = {k for k in keys if others and all(k in P.org_key(o) for o in others)}   # 모든 문서 이름에 든 이름(과제 이름에 든 기관) — 그 문서의 기관이라는 근거가 아니다
    hit = [k for k in keys if k in P.org_key(name) and k not in everywhere]
    hit = [k for k in hit if not any(k != o and k in o for o in hit)]   # 포함 관계(「한국선급」 ⊂ 「한국선급연구소」) — 긴 쪽만
    if len(hit) == 1:   # 문서에 여러 기관의 절이 있어도 파일 이름이 가리키는 기관이 그 가운데 있으면 그 기관(그 기관의 것만 후보로 읽는다 — merge_pairs.summarize(own=))
        if labels and hit[0] not in labels:
            return None, "", f"파일 이름은 「{hit[0]}」 인데 문서의 기관 라벨은 다른 기관을 가리킵니다 — 직접 정하세요"
        return hit[0], "name", "파일 이름에 든 기관"
    if len(hit) > 1:
        return None, "", "파일 이름에 기관 이름이 둘 이상입니다 — 직접 정하세요"
    if len(labels) == 1:
        return next(iter(labels)), "label", "문서의 기관 라벨이 밝힌 기관이 하나"
    return None, "", "파일 이름 · 문서의 기관 라벨로 기관을 정하지 못했습니다 — 직접 정하세요" if not labels else "문서에 여러 기관의 절이 있습니다 — 직접 정하세요"


# ---- 원장 ----

def led_row(to, frm, s_text, t_text, place, letter=None, pos=None, calc=False):
    """원장 줄 — 끝의 사전 = {pos: 그 자리 안의 차례(본문 — 일부만 고쳐 다른 이벤트로 옮겨도 차례가 남는다), calc: 계산 칸(합계 · 소계 — 수정본이 저절로 안 고친다)}."""
    return [to, frm, s_text, t_text, place, letter, {**({"pos": pos} if pos is not None else {}), **({"calc": True} if calc else {})}]


def meta(row):
    return row[6] if len(row) > 6 and isinstance(row[6], dict) else {}


def led_rows(origins, parts, alive=None):
    """출처 이벤트들 가운데 그 문서들(parts — 수정본의 앞 제출본 사슬)의 원장 줄 → [(이벤트, 줄)] — 이벤트 차례 · 줄 차례. alive = 지금 문서의 id 모음(주면 살아 있는 것만 —
    안 주면 사람이 지운 줄도 낸다: 수정본이 그 줄을 「새로 생긴 줄」 로 되살리지 않게 자리를 지키는 줄)."""
    out, want = [], set(parts or ())
    for e in origins or ():
        if not isinstance(e, dict) or e.get("part") not in want or not isinstance(e.get("led"), list):
            continue
        ids = set(e.get("ids") or ())
        for r in e["led"]:
            if isinstance(r, list) and len(r) >= 5 and r[0] in ids and (alive is None or r[0] in alive):
                out.append((e, r))
    return out


# ---- 수정본의 3방향 ----

def _eq(a, b):
    return P._ws(a) == P._ws(b)


def cell_item(row, s2_id, s2, t_now):
    """칸 하나 — row = 원장 줄 · s2_id · s2 = 수정본에서 그 칸과 짝인 칸(없으면 None) · t_now = 지금 목적 칸의 글. → 항목 | None(S2 가 그대로)."""
    to, _, s1, t1, place = row[:5]
    base = {"kind": "cell", "to": to, "from": s2_id, "place": place, "was": t_now, "text": None, "detail": ""}
    if s2_id is None:
        return {**base, "status": "missing", "detail": "수정본에서 이 칸의 짝을 찾지 못함"}
    if s1 is None or t1 is None:
        return {**base, "status": "hold", "detail": "글로 견줄 수 없는 칸"}
    if _eq(s2, s1):
        return None
    if not P._ws(s2):   # 수정본의 그 칸이 비어 있다 — 지우라는 뜻인지 안 쓴 칸(발췌 · 빈 양식)인지 가를 근거가 없다: 지우지 않는다
        return {**base, "status": "missing", "detail": "수정본의 칸이 비어 있음 — 그대로 둠"}
    if meta(row).get("calc"):
        return {**base, "status": "hold", "text": s2, "detail": "계산 칸(합계 · 소계) — 피연산자가 바뀐 뒤 다시 계산해야 합니다"}
    if _eq(t_now, s2):
        return {**base, "status": "same", "text": s2}
    if not _eq(t1, s1):
        return {**base, "status": "hold", "text": s2, "detail": "바꿔 적어 넣은 칸(원본 글과 넣은 글이 다름) — 확인 필요"}
    if _eq(t_now, t1):
        return {**base, "status": "ready", "text": s2}
    return {**base, "status": "overlap", "text": s2, "detail": "넣은 뒤 목적 칸의 글이 바뀜"}


def _para_new(row, s2, s2_letter):
    """단순 문단의 새 글 → (목적 문단에 쓸 글 | None, 못 정한 까닭). 넣을 때 접두(레터)를 목적 틀로 바꾼 줄은 목적 접두를 두고 본문만 바꾼다 —
    원본 레터(넣을 때 적어 둔 것)와 수정본의 레터가 같고 그 앞 빈칸까지 같을 때만(「1.」 → 「1)」 처럼 레터가 달라졌으면 확인 필요 — 짐작해서 본문만 바꾸지 않는다)."""
    s1, t1, letter = row[2], row[3], row[5] if len(row) > 5 else None
    if _eq(t1, s1):   # 넣을 때 글을 안 바꿨다 — 수정본의 글 그대로
        return s2, ""
    if not letter or (s2_letter or "") != letter:
        return None, "넣을 때 레터를 목적 틀로 바꾼 줄인데 수정본의 레터가 달라졌습니다 — 확인 필요"
    lead = s1[:len(s1) - len(s1.lstrip())]
    p1 = lead + letter
    if not s1.startswith(p1) or not s2.startswith(p1):
        return None, "레터 앞 빈칸 · 레터의 꼴이 달라졌습니다 — 확인 필요"
    body1 = s1[len(p1):]
    if not body1.strip() or not t1.endswith(body1):
        return None, "넣을 때 바꾼 접두를 가를 수 없습니다 — 확인 필요"
    return t1[:len(t1) - len(body1)] + s2[len(p1):], ""


def body_items(rows, new, t_now, order, plain=None):
    """본문 항목 하나(목적 항목 key 하나의 원장 줄들) — rows = 그 자리의 원장 줄(넣은 차례) · new = 수정본의 그 항목 블록 [{id, text | None(단순 문단이 아님), letter, key}] ·
    t_now = {목적 id: 지금 글} · order = {목적 최상위 블록 id: 문서 차례}. → 항목들(모듈 설명). 같은 글 줄이 여럿인 항목에서 바뀐 곳이 있으면 그 항목은 모두 확인 필요(어느 줄인지 못 정한다)."""
    bkeys = [P._ws(r[2]) if r[2] is not None else f"\0obj{i}" for i, r in enumerate(rows)]
    nkeys = [x["key"] for x in new]
    ops = [o for o in difflib.SequenceMatcher(None, bkeys, nkeys, autojunk=False).get_opcodes() if o[0] != "equal"]
    if not ops:
        return []
    out = []
    place = rows[0][4] if rows else None
    dup = any(k and bkeys.count(k) > 1 for k in bkeys if not k.startswith("\0")) or any(k and nkeys.count(k) > 1 for k in nkeys if not k.startswith("\0"))
    hold = lambda r, j, why: out.append({"kind": "para", "to": r[0], "from": new[j]["id"] if j is not None else None, "place": place, "was": t_now.get(r[0]), "text": None, "status": "hold", "detail": why})  # noqa: E731
    for tag, i1, i2, j1, j2 in ops:
        if dup:
            for r in rows[i1:i2]:
                hold(r, None, "같은 글 줄이 여럿인 자리 — 어느 줄이 바뀌었는지 정할 수 없음")
            for x in new[j1:j2]:
                out.append({"kind": "add", "to": None, "from": x["id"], "place": place, "after": None, "was": None, "text": x["text"], "status": "hold", "detail": "같은 글 줄이 여럿인 자리 — 확인 필요"})
            continue
        if tag == "delete":
            for r in rows[i1:i2]:
                out.append({"kind": "para", "to": r[0], "from": None, "place": place, "was": t_now.get(r[0]), "text": None, "status": "missing", "detail": "수정본에 이 줄이 없음 — 그대로 둠"})
            continue
        if tag == "replace" and i2 - i1 == j2 - j1:
            for r, j in zip(rows[i1:i2], range(j1, j2)):
                x, now = new[j], t_now.get(r[0])
                if r[2] is None or r[3] is None or x["text"] is None:
                    hold(r, j, "표 · 그림이 든 블록이 바뀜 — 확인 필요")
                    continue
                if now is None:
                    hold(r, j, "넣은 줄이 지금 문서에 없음")
                    continue
                text, why = _para_new(r, x["text"], x.get("letter"))
                if plain is not None and r[0] not in plain and not (_eq(now, x["text"]) or (text is not None and _eq(now, text))):
                    hold(r, j, "각주 · 필드 · 자동 번호 · 개체가 든 문단 — 글을 바꾸면 그것을 잃습니다: 확인 필요")   # plain = 글만 든 목적 문단(부르는 쪽이 문서에서 센다)
                    continue
                if _eq(now, x["text"]) or (text is not None and _eq(now, text)):
                    out.append({"kind": "para", "to": r[0], "from": x["id"], "place": place, "was": now, "text": text, "status": "same", "detail": ""})
                elif text is None:
                    hold(r, j, why)
                elif _eq(now, r[3]):
                    out.append({"kind": "para", "to": r[0], "from": x["id"], "place": place, "was": now, "text": text, "status": "ready", "detail": ""})
                else:
                    out.append({"kind": "para", "to": r[0], "from": x["id"], "place": place, "was": now, "text": text, "status": "overlap", "detail": "넣은 뒤 목적 문서의 글이 바뀜"})
            continue
        if tag == "replace":   # 줄 수가 달라진 구간 — 어느 줄이 어느 줄인지 못 정한다
            for r in rows[i1:i2]:
                hold(r, None, "바뀐 줄 수가 달라 짝을 정할 수 없음 — 확인 필요")
            for x in new[j1:j2]:
                out.append({"kind": "add", "to": None, "from": x["id"], "place": place, "after": None, "was": None, "text": x["text"], "status": "hold", "detail": "바뀐 줄 수가 달라 짝을 정할 수 없음 — 확인 필요"})
            continue
        # insert — 수정본에 새로 생긴 블록: 앞의 맞은 줄(목적에 살아 있음) 바로 뒤에, 뒤의 맞은 줄이 그 바로 다음일 때만(그 사이에 사람이 쓴 블록이 있으면 확인 필요)
        prev = rows[i1 - 1][0] if i1 > 0 else None
        nxt = rows[i1][0] if i1 < len(rows) else None
        ok = prev is not None and prev in order and (nxt is None or (nxt in order and order[nxt] == order[prev] + 1))
        why = "" if ok else ("앞 줄이 없는 자리(항목의 맨 앞) — 확인 필요" if prev is None else "넣을 자리의 앞뒤 줄 사이에 다른 블록이 있거나 앞 줄이 없음 — 확인 필요")
        after, p0 = prev, meta(rows[i1 - 1]).get("pos", i1 - 1) if i1 > 0 else -1
        for k, x in enumerate(new[j1:j2]):   # pos = 그 자리 안의 차례(앞 줄 바로 뒤 — 다음 수정본이 이 줄을 제자리에서 견준다)
            out.append({"kind": "add", "to": None, "from": x["id"], "place": place, "after": after if ok else None, "was": None, "text": x["text"], "status": "ready" if ok else "hold", "detail": why,
                        "pos": p0 + (k + 1) / 1000})
    return out


def counts(items):
    c = {k: 0 for k in STATUS}
    for it in items:
        c[it["status"]] = c.get(it["status"], 0) + 1
    return c


def count_text(c):
    return " · ".join(f"{STATUS_NAME[k]} {c[k]}" for k in STATUS if c.get(k)) or "바뀐 곳 없음"

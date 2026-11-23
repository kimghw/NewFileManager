"""헤딩 추출 2단계 — **1칸 제목 상자**(spec_헤딩_추출 ② §6 「1칸 제목 상자」): 본문에 놓인 1칸 표 하나에 짧은 제목 한 줄만 든 상자
(「▸ 글로벌 자율운항선박 기술 패러다임의 전환과 데이터 경쟁 심화」 — 회색 바탕 · 13pt 굵게 · 앞에 작은 그림)가 그 아래 헤딩 줄(「o (…)」)을 이끄는 곳을 찾는다.
문서를 바꾸지 않는다 — 1단계 레코드만 읽는다.

2026-11-17 · 11-23 사용자 "그리고 국내 기술 동향 및 수준이 L4 가 되어야 하는데. 여기서는 단순 테이블로 되어 있네. 내가 요청한적이 있는데 저런 테이블에 헤딩을 넣는 경우가 있으니
이것도 템플릿에 반영을 하란말이지" → (④ 로 미룸) → 같은 날 "지금도 이 테이블은 헤딩으로 인식을 못하냐?" — 권장안 ⓑ-1(「상자 = T1 L4 · o = L5」)로 구현.

- **제목 상자** = 본문(구역 바로 아래 — 칸 안 표 · 글상자 · 머리말 · 캡션의 표는 아님)의 **1칸 표**이고 ·
  칸에 **글 있는 문단이 하나**(보통 글 — 개요 레터 · 괄호 줄 · ※ 안내 · 캡션이 아님 · 한 줄 · 80자까지 · 문장으로 끝나지 않음) · 칸 안 개체는 **그림만**(앞에 놓는 작은 아이콘 — 표는 안 됨) ·
  표를 품은 문단에 글이 없고 · **바로 아래**(빈 문단만 사이)가 본문의 **헤딩 줄**(개요 레터 · 개요 번호)이며 · 같은 꼴(칸 바탕 + 제목 글의 글꼴 · 크기 · 굵게 + 그림 있음)의 제목 상자가 **둘 이상**인 것.
  TEMP(작성요령 상자 — 헤딩 추출 §15)는 뺀다.
- 그래프(`heading_graph`)는 이 상자를 kind `titlebox` 의 본문 흐름 노드로 넣는다(열쇠 = 칸 안 제목 문단 · 레터 없음 · 정규 키 「▦」) — 늘 헤딩이고 바로 아래 헤딩 줄의 **부모**다.
  템플릿에는 그 아래 줄의 레벨 **바로 위에 표 레벨 「▦」 를 끼운다**(상자 없는 절의 같은 레터 줄도 한 칸 밀린다 — 같은 레터가 두 레벨로 갈리지 않게: 11-17 「레벨을 건너뛴 줄」 과 같음).
  오버레이(`outline_edit.build_overlay`)는 표 줄(role table — 손으로 넣는 「표를 L1 으로」 와 같은 줄)로 둔다.
"""
from collections import defaultdict

KIND = "titlebox"   # 후보 노드 · 유형의 kind
KEY = "▦"           # 정규 레터 키(템플릿 사슬의 표 레벨 — outline_lift.KEY 와 같은 글자)
TITLE_MAX = 80      # 제목 글 길이 — 이보다 길면 본문을 담은 상자
GROUP_MIN = 2       # 같은 꼴의 제목 상자가 이만큼 있어야 제목 상자로 본다(하나뿐인 상자는 강조 상자일 수 있다)
_ENDS = ("다.", "음.", "함.", "요.", "임.")


def _title_ok(rec):
    t = " ".join((rec.get("text") or "").split())
    if not t or len(t) > TITLE_MAX or " " in (rec.get("text") or "").strip():
        return False
    return rec.get("kind") == "plain" and not t.endswith(_ENDS)


def _sig(rec, cell):
    ch = (rec.get("char") or {}).get("text") or {}
    return "|".join(str(x) for x in ((cell.get("fill") or "").upper(), ch.get("font") or "", ch.get("sizePt") or 0, bool(ch.get("bold")),
                                     "pic" in (rec.get("objects") or ())))


def _heading_rec(rec):
    """본문의 헤딩 줄인가 — 개요 레터(글이 있는 줄) · 개요 번호 문단."""
    if rec.get("path"):
        return False
    if rec.get("kind") == "marker" and not rec.get("blank"):
        return True
    return bool(rec.get("num") or rec.get("outlineLevel")) and bool((rec.get("text") or "").strip())


def find(paras, skip=()):
    """1단계 문단 레코드 → {제목 문단 id: {table, host, cell, title(제목 문단 id), text, sig, child(바로 아래 헤딩 줄의 문단 id)}}.
    skip = 후보에서 뺄 문단 id(TEMP — 그 문단이 든 표는 제목 상자가 아니다)."""
    idx = {r["id"]: i for i, r in enumerate(paras)}
    tables = defaultdict(list)
    for i, rec in enumerate(paras):
        path = rec.get("path") or []
        if len(path) == 2 and path[0].get("t") == "tbl" and path[1].get("t") == "cell" and path[0].get("id") and int(path[0].get("cells") or 0) == 1:
            tables[path[0]["id"]].append(i)
    found = {}
    for tid, ii in tables.items():
        recs = [paras[i] for i in ii]
        if any(r["id"] in skip or "tbl" in (r.get("objects") or ()) for r in recs):
            continue
        if any(set(r.get("objects") or ()) - {"pic"} for r in recs):
            continue
        texts = [r for r in recs if (r.get("text") or "").strip()]
        if len(texts) != 1 or not _title_ok(texts[0]):
            continue
        title = texts[0]
        host = recs[0]["path"][0].get("host")
        hi = idx.get(host)
        if hi is not None and ((paras[hi].get("text") or "").strip() or paras[hi].get("path")):
            continue  # 표를 품은 문단에 글이 있다(글 사이의 상자) · 칸 안 문단이 품은 표
        j = ii[-1] + 1
        while j < len(paras) and not (paras[j].get("text") or "").strip() and not paras[j].get("objects") and not paras[j].get("path"):
            j += 1
        if j >= len(paras) or not _heading_rec(paras[j]) or paras[j]["id"] in skip:
            continue
        found[title["id"]] = {"table": tid, "host": host, "cell": title["path"][1].get("id"), "title": title["id"],
                              "text": " ".join(title["text"].split()), "sig": _sig(title, title["path"][1]), "child": paras[j]["id"]}
    count = defaultdict(int)
    for b in found.values():
        count[b["sig"]] += 1
    return {pid: b for pid, b in found.items() if count[b["sig"]] >= GROUP_MIN}


# ---------------------------------------------------------------- 옛 오버레이 이행(2단계를 다시 돌릴 때)
# 상자 레벨 「▦」 이 사슬에 들거나 빠지면 그 템플릿의 앵커(「body:N.›N-N.›(N)›▦›o›-›·」)와 그 아래 레벨 번호가 바뀐다. 오버레이의 carry 들(자리 규칙 · 종속 · 서식 종속 · 더한 레벨)은
# 앵커 + 레벨로 옛 기록을 새 오버레이에 옮기므로, 그 앞에 옛 오버레이 **사본**의 앵커 · 레벨을 새 사슬의 번호로 바꿔 준다(옛 사슬과 새 사슬에서 「▦」 를 뺀 글이 같은 템플릿끼리만).

def _parts(anchor):
    """앵커 → (scope, 사슬 칸 목록) | None — 서식 종속 템플릿의 앵커(「…~L3a」)는 None."""
    if not anchor or ":" not in anchor or "~" in anchor:
        return None
    sc, ch = anchor.split(":", 1)
    return sc, ch.split("›")


def _plain(parts):
    sc, ch = parts
    return sc + ":" + "›".join(p for p in ch if p != KEY)


def _level_map(old, new):
    """옛 사슬 칸 목록 → 새 사슬 칸 목록의 레벨 번호 대응 {옛 레벨: 새 레벨}(글 레벨은 차례대로 · 상자 레벨은 상자 레벨끼리 차례대로)."""
    ot, nt = [i for i, p in enumerate(old) if p != KEY], [i for i, p in enumerate(new) if p != KEY]
    ob, nb = [i for i, p in enumerate(old) if p == KEY], [i for i, p in enumerate(new) if p == KEY]
    m = {o + 1: n + 1 for o, n in zip(ot, nt)}
    m.update({o + 1: n + 1 for o, n in zip(ob, nb)})
    return m


def align_old(old, new):
    """2단계를 다시 돌려 오버레이를 새로 만들 때 — 옛 오버레이 old 의 템플릿 가운데 새 오버레이 new 에서 상자 레벨(「▦」)만 다르게 든 템플릿이 있으면
    old 의 사본에서 그 템플릿(과 거기서 뗀 서식 종속 템플릿)의 앵커 · 사슬 · 줄 레벨 · 슬롯 · 가지 열쇠 · 더한 레벨 · 종속/떼기/푼 종속 기록을 새 번호로 바꿔 돌려준다. 없으면 old 그대로.
    (`outline_lift.carry` 가 맨 먼저 부른다 — 뒤의 carry 들이 앵커 + 레벨로 읽는다.)"""
    if not old or not new or not old.get("templates"):
        return old
    by_plain = defaultdict(list)
    for t in (new.get("templates") or {}).values():
        p = _parts(t.get("anchor"))
        if p:
            by_plain[_plain(p)].append(t)
    plans = {}  # 옛 템플릿 id → (새 앵커, 새 사슬, 레벨 대응, 옛 사슬 길이, 새 사슬 길이)
    for tid, t in old["templates"].items():
        p = _parts(t.get("anchor"))
        if not p:
            continue
        cands = by_plain.get(_plain(p)) or []
        if len(cands) != 1 or cands[0].get("anchor") == t.get("anchor"):
            continue
        q = _parts(cands[0]["anchor"])
        plans[tid] = (cands[0]["anchor"], list(q[1]), _level_map(p[1], q[1]), len(p[1]), len(q[1]))
    if not plans:
        return old
    import copy
    out = copy.deepcopy(old)
    tps = out["templates"]

    def root(tid):  # 서식 종속 템플릿은 뗀 템플릿의 레벨 번호를 그대로 쓴다 — 뿌리 템플릿
        seen = set()
        while tid in tps and (tps[tid].get("variant") or {}).get("of") is not None and tid not in seen:
            seen.add(tid)
            tid = str(tps[tid]["variant"]["of"])
        return tid

    def lv(tid, level):
        pl = plans.get(root(str(tid)))
        if pl is None or level is None:
            return level
        n = int(level)
        return pl[2].get(n, n + pl[4] - pl[3] if n > pl[3] else n)

    def anchor(tid, seen=()):
        t = tps.get(tid)
        if t is None:
            return None
        var = t.get("variant")
        if var and var.get("of") is not None and tid not in seen:
            a = anchor(str(var["of"]), tuple(seen) + (tid,))
            return f"{a}~L{lv(tid, var['level'])}{var.get('sfx', '')}" if a else t.get("anchor")
        return plans[tid][0] if tid in plans else t.get("anchor")
    touched = [tid for tid in tps if root(tid) in plans]
    fresh = {tid: anchor(tid) for tid in touched}  # 새 앵커를 모두 먼저 셈한다(아래에서 서식 종속의 레벨을 바꾸기 전에)
    amap = {}
    for tid in touched:
        t, new_anchor = tps[tid], fresh[tid]
        amap[t.get("anchor")] = new_anchor
        if tid in plans:
            t["chain"] = list(plans[tid][1])
        elif t.get("variant"):
            t["chain"] = list(plans[root(tid)][1])
            t["base"] = lv(tid, int(t["variant"]["level"])) - 1
            t["variant"]["level"] = lv(tid, int(t["variant"]["level"]))
        t["anchor"] = new_anchor
        t["slots"] = {str(lv(tid, int(k))): sl for k, sl in (t.get("slots") or {}).items()}
        t["max"] = max((int(k) for k in t["slots"]), default=0)
    for x in list((out.get("lines") or {}).values()) + list((out.get("autos") or {}).values()):
        x["level"] = lv(str(x["tpl"]), x["level"])
    br = out.get("branches") or {}
    out["branches"] = {(f"{k.split('|')[0]}|{lv(k.split('|')[0], int(k.split('|')[1]))}" if "|" in k else k): v for k, v in br.items()}
    for r in out.get("grows") or []:
        r["level"] = lv(str(r.get("tid")), r.get("level"))
    by_anchor = {t.get("anchor"): tid for tid, t in old["templates"].items()}
    for key in ("merges", "unmerged"):
        for m in out.get(key) or []:
            ptid = by_anchor.get(m.get("parent"))
            if ptid is not None and m.get("at") is not None:
                m["at"] = lv(ptid, m["at"])
            m["parent"], m["child"] = amap.get(m.get("parent"), m.get("parent")), amap.get(m.get("child"), m.get("child"))
    for m in out.get("splits") or []:
        if m.get("ofId") is not None and str(m["ofId"]) in tps:
            m["level"] = lv(str(m["ofId"]), m.get("level"))
        m["of"] = amap.get(m.get("of"), m.get("of"))
    for r in out.get("lifts") or []:
        r["anchor"] = amap.get(r.get("anchor"), r.get("anchor"))
    return out

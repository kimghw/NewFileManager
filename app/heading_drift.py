"""뼈대 유지(spec_헤딩_추출 ② §17, 2026-11-10 사용자 "문서가 바뀔 때마다 헤딩을 다시 추출하라고 하면 어쩌냐? 한번 하면 그 구조는 그냥 그 뼈대로 그냥 두고 ..
새로운 레터나 서식이 추가되면 알람이나 표시만 해줘").

2단계(헤딩 그래프·템플릿)·3단계(표 구조) 결과는 한 번 만들면 그 문서의 **뼈대**다 — 문서를 고쳐도 다시 만들라고 하지 않는다. 대신 지금 문서에서 **뼈대를 만들 때 문서에 없던 것**만
찾아 알린다(스크립트만 · LLM 없음 · 문서와 결과를 바꾸지 않음 · 실행으로 저장하지 않음):

- 2단계: **새 레터**(그 자리(본문·표 칸)에 없던 레터 꼴) · **새 서식**(레터는 있던 것인데 그 레터가 쓰던 어느 서식과도 오차 밖인 서식을 **`REPEAT_MIN` 줄 이상 되풀이**해 씀) ·
  **잘못된 서식**(그런 서식인데 되풀이되지 않음 — 한 줄뿐: 사용자 2026-11-16 「새로운 서식은 반복적일때 새로운 서식인거지. 이건잘못된거잖아」). 줄 맞춤 값(장평·자간)만 다른 줄은 어느 쪽도 아니다.
- 3단계: **새 표**(없던 여러 칸 표) · **헤더가 바뀐 표**(열헤더·행헤더의 글이 달라지거나 없어지거나 새로 생긴 표 — 행·열 수만 달라진 표는 같은 표로 본다).

기준(뼈대를 만들 때의 문서) = 그 2단계 결과가 선 1단계 실행(`meta.stage1Run`)의 레코드 — TEMP·헤딩 아님으로 빠진 줄까지 문서에 있던 헤딩 후보 전부. 그 1단계 결과를 못 읽으면
(저장 끔 + 그 뒤 다시 추출 · 옛 추출 방식) 그래프의 유형 표로 레터만 견주고 서식은 견주지 않는다(`formatsChecked` false).
지금 문서 = 지금 1단계 결과가 이 문서 차례(rev)의 것이면 그것, 아니면 여기서 메모리로만 다시 뽑는다(세션 잠금 안 — 1단계와 같은 추출, 결과는 버리고 견준 것만 문서 차례마다 기억)."""
import threading
import time
from collections import Counter

from app import heading_extract as E
from app import heading_graph as HG
from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs as HR
from app import heading_tables as HT
from app import heading_temp as TP
from app import outline_edit as OE
from app import outline_match as OM
from app import works

PARAS_MAX = 200  # 묶음 하나가 실어 보내는 문단 id 수(수는 그대로 센다)
REPEAT_MIN = 2   # 같은 레터의 줄이 같은 서식(지금 서식 라벨)을 이만큼 되풀이해 쓸 때만 「새 서식」 — 그보다 적으면 「잘못된 서식」(사용자 2026-11-16 답 「2줄 이상」)
NONE2 = {"letters": [], "formats": [], "wrong": [], "formatsChecked": True,
         "counts": {"letters": 0, "letterParas": 0, "formats": 0, "formatParas": 0, "wrong": 0, "wrongParas": 0}}
NONE3 = {"new": [], "changed": [], "gone": 0, "resized": 0, "counts": {"new": 0, "changed": 0, "gone": 0, "resized": 0}}


# ---- 레터의 정체 ---------------------------------------------------------------------------------------------------

def _scope(flow):
    return "cell" if str(flow or "").startswith("cell:") else "body"


def ident(nd):
    """헤딩 후보 노드 → (자리, 종류, 꼴). 레터 줄은 변형군을 합친 정규 꼴(「○」·「ㅇ」·「o」 = 「o」 — 2단계 정규 레터 키와 같은 규칙), 괄호 줄은 숫자를 N 으로 적은 글,
    개요 번호는 「개요N」, 레터 없는 제목 꼴은 「제목」."""
    sc, kind = _scope(nd.get("flow")), nd["kind"]
    if kind == "label":
        return sc, kind, HG.label_shape(nd.get("letter"))
    if kind == "marker":
        return sc, kind, HG.VARIANTS.get(nd.get("family") or "") or nd.get("shape") or (nd.get("letter") or "").strip()
    return sc, kind, HG._shape_key({**nd, "outline": nd.get("outline", nd.get("sourceOutlineLevel"))})


def bracket_key(letter, hints=None):
    """괄호 줄의 정규 키(스크립트 규칙·사용자 지정만 — LLM 없이): 구분 라벨 「[기준]」 · 괄호 소제목 「[…]」 · 헤딩 아님(빈 대괄호·체크 칸) None."""
    role, basis, _ = HG.bracket_role(letter, hints)
    return HG._bracket_key(role, basis)


# ---- 뼈대(2단계) ----------------------------------------------------------------------------------------------------

def _ref():
    return {"fps": set(), "sids": Counter()}


def skeleton(g, base=None, hints=None):
    """2단계 결과 g(+ 그 결과가 선 1단계 결과 base) → 뼈대가 아는 것 {letters{(자리, 종류, 꼴): 서식}, brackets{(자리, 괄호 정규 키)}, labelFormats{자리: 서식}, reps{S: 대표 레코드},
    names{S: 서식 이름}, full(base 로 만들었나 — 서식까지 견줄 수 있나)}. 서식 = {fps: 정확한 지문 집합, sids: 그때의 서식 라벨 → 수}."""
    out = {"letters": {}, "brackets": set(), "labelFormats": {}, "reps": {}, "names": {}, "full": False}
    for n in g.get("nodes") or ():  # LLM·사용자 지정이 정한 괄호 줄의 정규 키(「[한국선급]」 → 「[기관]」)
        if n.get("kind") == "label" and n.get("key"):
            out["brackets"].add((_scope(n.get("flow")), n["key"]))
    if not isinstance(base, dict) or base.get("version") != E.VERSION:  # 그 1단계 결과가 없거나 옛 추출 방식 — 유형 표로 레터만
        for t in g.get("types") or ():
            key = HG.VARIANTS.get(t.get("family") or "") or t.get("shape") if t.get("kind") == "marker" else t.get("shape")
            out["letters"].setdefault((t.get("area") or "body", t.get("kind"), key), _ref())
        return out
    out["full"] = True
    by_id = {r["id"]: r for r in base["paras"]}
    labels = base.get("labels") or {}
    for nd in HG.candidates(base):  # TEMP·헤딩 아님으로 빠진 줄까지 — 그때 문서에 있던 헤딩 후보 전부
        rec = by_id[nd["para"]]
        idn = ident(nd)
        refs = [out["letters"].setdefault(idn, _ref())]
        if nd["kind"] == "label":
            k = bracket_key(nd.get("letter"), hints)
            if k:  # 괄호 줄의 서식은 그 자리의 괄호 줄 전체로 견준다(글마다 꼴이 다르므로) — 체크 칸은 빼고
                out["brackets"].add((idn[0], k))
                refs.append(out["labelFormats"].setdefault(idn[0], _ref()))
        fp, sid = E._fp(rec), rec.get("fmt")
        for ref in refs:
            ref["fps"].add(fp)
            ref["sids"][sid] += 1
        if sid and sid not in out["reps"]:
            lab = labels.get(sid) or {}
            out["reps"][sid] = by_id.get(lab.get("sample")) or rec  # 서식 라벨의 대표 문단(S 묶음의 기준) — 없으면 이 문단
            out["names"][sid] = lab.get("name") or E.format_name(rec)
    return out


INDENT = ("indentLeftMm", "firstLineMm")  # 개요 줄 자리(spec_hwpx_웹편집 ② §8-1)가 넣는 문단 여백 — 앱이 맞춘 줄은 이 둘을 빼고 견준다
PLACED_EPS = 0.02  # mm — outline_pos.EPS 와 같음
_FIT_FLAT = {"ratioPct": 100, "spacingPct": 0}
assert set(_FIT_FLAT) == set(OM.FIT_KEYS)  # 줄 맞춤 값의 목록은 outline_match 가 원본(spec_hwpx_웹편집 ② §8-2 「줄 맞춤 값」)


def _fitless(rec):
    """줄 맞춤 값(장평·자간)을 기본값으로 눕힌 레코드(얕은 사본 — 글 런·레터 런 둘 다). 한 줄에 넣으려고 줄인 자간은 서식이 아니다: 서식 조정(대표에 맞추기)도 그 값은 지킨다 —
    눕히지 않으면 맞춘 줄(문단 모양은 대표 · 자간은 제 것)이 뼈대에 없던 지문이라 「새 서식」 으로 나온다. 레터 런이 글 런과 줄 맞춤 값만 달랐으면 같은 글자 모양이 된다(`E._letter_run` → None)."""
    ch = rec["char"]
    flat = lambda c: {**c, **_FIT_FLAT} if c else c  # noqa: E731
    return {**rec, "char": {**ch, "text": flat(ch.get("text")), "letter": flat(ch.get("letter"))}}


def _emphless(rec):
    """본문 런의 강조(굵게 · 기울임 · 밑줄)와 문단 테두리 참조(borderFill id)를 눕힌 레코드(얕은 사본 — 레터 런은 그대로) — 확정 서식 줄과 대표를 견줄 때만(headings 의 rec_same).
    테두리는 참조 id 라 다른 문서에서 들여온 같은 꼴의 줄도 id 가 달랐다(실제 작업 사본 — 「넣은 뒤 정리」 뒤 3줄 · 반영 뒤 9줄 · outline_match.same 도 안 본다). 위첨자 · 아래첨자는 그대로 견준다."""
    ch = rec["char"]
    t = ch.get("text")
    return {**rec, "para": {**rec["para"], "border": None}, "char": {**ch, "text": {**t, "bold": False, "italic": False, "underline": False} if t else t}}


class _Formats:
    """서식 견주기 — 1단계가 서식 라벨(S)을 묶는 것과 같은 규칙(범주가 같고 수치가 오차 안)."""

    def __init__(self, tol=None):
        self.tol = tol or G.tolerance()
        self.alias = E._alias(self.tol)

    def sig(self, rec):
        return E._category(rec, self.tol, self.alias), E._numbers(rec)

    @staticmethod
    def loose(sig, left=True):
        """첫 줄(들여·내어쓰기)을 뺀 지문 — 범주의 첫 줄 부호 자리(7번째)도 뺀다. left 면 왼쪽 여백도(사용자가 정한 슬롯 자리 규칙은 레터 위치·둘째 줄을 옮기며 왼쪽 여백도 바꾼다)."""
        cat, num = sig
        drop = INDENT if left else INDENT[1:]
        return (cat[:6] + cat[7:] if len(cat) == 11 else cat), {k: v for k, v in num.items() if k not in drop}

    def same(self, a, b):
        return a[0] == b[0] and E._within(a[1], b[1], self.tol)


def confirmed(doc, ov, pids):
    """오버레이 줄 가운데 **제 템플릿 슬롯의 확정 서식을 지키는 줄** → {문단 id: 그 슬롯의 대표 id}(spec_헤딩_추출 ② §17 「확정 서식을 지키는 줄」 — 2026-11-23 astra 협의 ·
    headings 가 그 줄을 대표와 뼈대의 서식 비교로 한 번 더 견준다).
    줄 p(슬롯 S · 대표 r)가 ⓐ 레터 계열(`outline_match.look` 의 kin)이 r 과 같고 ⓑ 비교 값이 r 과 `outline_match.same` 이고 ⓒ r 이 S 의 동결 모양(attrs)을 지키고 있으면 앎 —
    r 자신은 ⓒ 로. 뼈대(2단계 결과)를 만든 뒤 앱이 템플릿에 넣거나 맞춘 줄(넣은 뒤 정리의 레터 바꾸기 · 확정 서식 · 「내용 반영」 이 등록한 넘친 줄)을 「새 서식」 · 「새 레터」 로 세지 않게.
    넣은 id 라서 빼지 않는다 — 그 뒤 사람이 서식을 바꾼 줄은 대표와 달라 다시 걸린다. **세션 잠금 안에서** 부른다(문서를 읽는다)."""
    lines = (ov or {}).get("lines") or {}
    out, reps = {}, {}   # 줄 → 그 슬롯의 대표(headings 가 뼈대의 서식 비교로 한 번 더 견준다 — 위첨자 · 아래첨자처럼 outline_match.same 이 안 보는 값: astra 3차)

    def frozen(sl, tid, level):
        """슬롯의 살아 있는 대표가 동결 모양(접두의 앞 · 뒤 빈칸 · 레터 꼴 · 문단 · 레터 글자 모양 · 본문 바탕 글자 모양)을 지키나 → (대표, 그 비교 값, 슬롯의 레터 계열) | None.
        동결 근거가 모자란 옛 슬롯(attrs · bodyChar · prefix 없음) · 죽은 대표 · 그 슬롯 줄이 아닌 대표는 None(그 레벨은 지금처럼 뼈대와 견준다)."""
        r = sl.get("rep")
        x = lines.get(r) if r else None
        if not (x and str(x.get("tpl")) == str(tid) and str(x.get("level")) == str(level) and OM._alive(doc, r) and sl.get("attrs") and sl.get("bodyChar") and sl.get("prefix")):
            return None
        try:
            sh = OM.rep_shape(doc, ov, r)
            rl = OM.look(doc, ov, r)
        except (KeyError, ValueError):
            return None
        key = sl.get("key") or ""
        lead, tok, gap = OE.prefix_of(sl["prefix"], sl.get("letter") or None)
        if sh["attrs"] != sl["attrs"] or sh["body"] != sl["bodyChar"] or (sh["lead"], sh["gap"]) != (lead, gap) or OM._form(sh["tok"], key) != OM._form(tok or sl.get("letter") or "", key):
            return None   # 사람이 대표를 손으로 바꿈(본문만 굵게 · 빈칸 · 레터) — 그 대표에 맞는 줄을 앎으로 세지 않는다(astra 2차 G8)
        return r, rl, OM.kin(sl.get("letter") or tok or "", key)

    for p in pids:
        x = lines.get(p)
        if not x or not OM._alive(doc, p):
            continue
        key = (str(x.get("tpl")), str(x.get("level")))
        if key not in reps:
            reps[key] = frozen(OE._slot(ov, x.get("tpl"), x.get("level")) or {}, *key)
        hit = reps[key]
        if hit is None:
            continue
        r, rl, skin = hit
        try:
            lk = rl if p == r else OM.look(doc, ov, p)
        except (KeyError, ValueError):
            continue
        if lk.get("kin") == skin and (p == r or OM.same(lk, rl)):   # ⓐ 슬롯의 레터 계열 ⓑ 대표와 같은 서식(대표 자신은 ⓒ 로)
            out[p] = r
    return out


def headings(sk, now, temp=None, hints=None, tol=None, placed=None, kept=frozenset(), flagged=None):
    """뼈대(skeleton 결과) ↔ 지금 문서(1단계 꼴 `now`) → {letters[새 레터 묶음], formats[새 서식 묶음], wrong[잘못된 서식 묶음], counts, formatsChecked}.
    묶음 = {scope, kind, shape, letter(예), text(예문), count, paras[문단 id…]} + 서식 묶음은 {fmt, name(지금 서식 이름), known[그 레터가 쓰던 서식 이름…]}.
    서식 묶음 = (자리, 레터, 지금 서식 라벨)이 같은 줄들 — `REPEAT_MIN` 줄 이상이면 **새 서식**(되풀이해 쓰는 서식), 그보다 적으면 **잘못된 서식**(그 줄만 다름 — 대표에 맞출 것).
    줄 맞춤 값(장평·자간)만 다른 줄은 서식이 다른 것이 아니다(`_fitless`).
    temp = 지금 TEMP 라벨(그 문단은 헤딩 후보가 아니다 — §15). placed = {문단 id: {"first": 앱이 넣은 첫 줄 값 mm, "left": 왼쪽 여백도 앱이 옮기는 줄인가}}(개요 오버레이 줄의 `first` —
    개요 줄 자리 규칙이 둘째 줄을 맞춘 줄, left = 그 슬롯에 사용자가 정한 자리 규칙이 있음): 첫 줄이 그 값 그대로인 문단은 첫 줄(left 면 왼쪽 여백도)을 빼고 견준다 — 앱이 맞춘 자리는 새 서식이 아니다.
    저절로 맞춘 줄(left 아님)은 왼쪽 여백을 안 건드리므로, 사람이 왼쪽 여백을 바꾸면 새 서식으로 나온다.
    kept = 확정 서식을 지키는 오버레이 줄(`confirmed` — 견주지 않고 앎) · flagged = 걸린 문단 id 를 모두 모을 모음(묶음의 paras 는 PARAS_MAX 까지라 — check 의 둘째 차례가 쓴다)."""
    fm = _Formats(tol)
    sigs = {}  # (줄 맞춤 값을 눕혔나, S, 첫 줄을 뺐으면 left | None) → 그때 대표의 지문
    placed = placed or {}

    def used(rec, ref, app_set, left):
        """그 레터가 쓰던 서식인가 — 그때 서식 라벨의 대표와 ① 오차 안(1단계가 서식 라벨을 묶는 규칙) ② 앱이 맞춘 첫 줄(left 면 왼쪽 여백도)을 빼고 ③ 줄 맞춤 값(장평·자간)을 눕히고(②도 함께)."""
        for flat in (False, True):
            s = fm.sig(_fitless(rec) if flat else rec)
            for loose in ((False, True) if app_set else (False,)):
                a = fm.loose(s, left) if loose else s
                for sid in ref["sids"]:
                    r = sk["reps"].get(sid)
                    if r is None:
                        continue
                    k = (flat, sid, left if loose else None)
                    b = sigs.get(k)
                    if b is None:
                        b = fm.sig(_fitless(r) if flat else r)
                        b = sigs[k] = fm.loose(b, left) if loose else b
                    if fm.same(a, b):
                        return True
        return False

    by_id = {r["id"]: r for r in now["paras"]}
    labels = now.get("labels") or {}
    letters, formats, memo = {}, {}, {}

    def add(store, key, nd, scope, shape, **more):
        it = store.get(key)
        if it is None:
            it = store[key] = {"scope": scope, "kind": nd["kind"], "shape": shape, "letter": (nd.get("letter") or "").strip()[:40],
                               "text": (nd.get("text") or "")[:60], "count": 0, "paras": [], "n": nd["n"], **more}
        it["count"] += 1
        if nd["para"] not in it["paras"] and len(it["paras"]) < PARAS_MAX:
            it["paras"].append(nd["para"])
        if flagged is not None:
            flagged.add(nd["para"])

    firsts = set()

    def rec_same(p, r):
        """확정 서식 줄 p 가 대표 r 과 뼈대의 서식 비교로도 같은가(위첨자 · 아래첨자 등 outline_match.same 이 안 보는 값 — astra 3차). 줄 맞춤 값 · 첫 줄 · 왼쪽 여백은 빼고(그 셋은
        outline_match.same 이 규칙으로 본다), **본문 강조(굵게 · 기울임 · 밑줄)도 뺀다** — 템플릿 줄의 본문 강조는 줄마다다(spec_병합 ② §5-9 「본문 강조는 줄마다」: 넣은 뒤 정리가 일부러 지킨다)."""
        a, b = by_id.get(p), by_id.get(r)
        if a is None or b is None:
            return False
        return fm.same(fm.loose(fm.sig(_emphless(_fitless(a)))), fm.loose(fm.sig(_emphless(_fitless(b)))))

    for nd in HG.candidates(now, frozenset((temp or {}).get("paras") or ())):
        if nd["para"] in kept and nd["para"] not in firsts and not nd.get("span"):
            firsts.add(nd["para"])
            if kept[nd["para"]] == nd["para"] or rec_same(nd["para"], kept[nd["para"]]):
                continue  # 제 템플릿 슬롯의 확정 서식을 지키는 줄(confirmed) — 그 문단의 첫머리 후보(span 0) 하나만 앎(줄 안 「①」 · 강제 줄 바꿈 뒤 레터는 따로 견준다: astra 2차 G8 · 3차)
        idn = ident(nd)
        ref = sk["letters"].get(idn)
        shape = idn[2]
        if nd["kind"] == "label":
            k = bracket_key(nd.get("letter"), hints)
            if k is None:
                continue  # 빈 대괄호·체크 칸 — 헤딩 후보가 아니다
            if ref is None and (idn[0], k) not in sk["brackets"]:
                add(letters, (idn[0], "label", k), nd, idn[0], k)  # 없던 구분 기준의 라벨 · 괄호 줄이 하나도 없던 자리의 괄호 줄
                continue
            ref, shape = sk["labelFormats"].get(idn[0]), "괄호 줄"
        elif ref is None:
            add(letters, idn, nd, idn[0], shape)
            continue
        if not sk["full"] or ref is None:
            continue
        rec = by_id[nd["para"]]
        fp = E._fp(rec)
        was = placed.get(nd["para"])
        app_set = was is not None and abs((rec["para"].get("firstLineMm") or 0.0) - was["first"]) <= PLACED_EPS
        left = bool(app_set and was.get("left"))
        mk = (idn[0], nd["kind"], shape, fp, bool(rec.get("blank")), app_set, left)
        known = memo.get(mk)
        if known is None:
            known = memo[mk] = fp in ref["fps"] or used(rec, ref, app_set, left)
        if not known:
            sid = rec.get("fmt")
            add(formats, (idn[0], nd["kind"], shape, sid), nd, idn[0], shape, fmt=sid, name=(labels.get(sid) or {}).get("name") or E.format_name(rec),
                known=[sk["names"].get(s) or s for s, _ in ref["sids"].most_common(3)])
    ls = sorted(letters.values(), key=lambda x: x["n"])
    fs = sorted(formats.values(), key=lambda x: x["n"])
    for it in ls + fs:
        del it["n"]  # 문서 순으로 놓는 데만 쓴 값 — 답에는 안 싣는다
    ws = [x for x in fs if x["count"] < REPEAT_MIN]   # 되풀이되지 않는 서식 = 그 줄만 다름(잘못된 서식)
    fs = [x for x in fs if x["count"] >= REPEAT_MIN]  # 되풀이해 쓰는 서식만 새 서식
    return {"letters": ls, "formats": fs, "wrong": ws, "formatsChecked": sk["full"],
            "counts": {"letters": len(ls), "letterParas": sum(x["count"] for x in ls), "formats": len(fs), "formatParas": sum(x["count"] for x in fs),
                       "wrong": len(ws), "wrongParas": sum(x["count"] for x in ws)}}


# ---- 뼈대(3단계 — 표) -----------------------------------------------------------------------------------------------

HEAD_ROLES = ("colhead", "rowhead", "corner")
EXAMPLES_MAX = 5


def _norm(text):
    return " ".join(str(text or "").split())


def head_diff(t, tb):
    """3단계 결과의 표 t ↔ 지금 문서의 같은 표 tb(heading_tables.collect 꼴) → {heads{text, gone, new}, examples[{what, role, was?, now?}]} — 열헤더·행헤더가 어떻게 달라졌나.
    text = 뼈대의 헤더 칸(열헤더·행헤더·귀퉁이)의 글이 달라짐 · gone = 그 칸이 없어짐(행·열을 지움·칸을 합침) · new = 뼈대에 없던 칸이 헤더 자리에 생김:
    그 행의 아는 칸이 대부분 열헤더(새 열의 머리 칸)거나 그 열의 아는 칸이 대부분 행헤더(새 행의 머리 칸)이고, 글이 있고 번호뿐(「4」·「④」·「라.」)이 아닐 때 — 목록형 표에 자료 행을 더한 것은 헤더 변경이 아니다."""
    old = {c["id"]: c for c in t.get("cells") or ()}
    cur = {c["id"]: c for c in tb["cells"]}
    heads, examples = {"text": 0, "gone": 0, "new": 0}, []

    def note(what, role, **more):
        heads[what] += 1
        if len(examples) < EXAMPLES_MAX:
            examples.append({"what": what, "role": role, **more})

    for cid, c in old.items():
        if c.get("role") not in HEAD_ROLES:
            continue
        n = cur.get(cid)
        if n is None:
            note("gone", c["role"], was=_norm(c.get("text"))[:60])
        elif _norm(n.get("text")) != _norm(c.get("text")):
            note("text", c["role"], was=_norm(c.get("text"))[:60], now=_norm(n.get("text"))[:60])
    rows, cols = {}, {}  # 지금 격자의 행·열마다 — 그 줄에 놓인 「아는 칸」 의 역할
    for cid, n in cur.items():
        if cid in old:
            rows.setdefault(n["row"], []).append(old[cid].get("role"))
            cols.setdefault(n["col"], []).append(old[cid].get("role"))
    for cid, n in cur.items():
        text = _norm(n.get("text"))
        if cid in old or not text or HT._ORDINAL.match(text):
            continue
        r, c = rows.get(n["row"]) or (), cols.get(n["col"]) or ()
        if r and sum(x in ("colhead", "corner") for x in r) * 2 > len(r):
            note("new", "colhead", now=text[:60])
        elif c and sum(x in ("rowhead", "corner") for x in c) * 2 > len(c):
            note("new", "rowhead", now=text[:60])
    return {"heads": heads, "examples": examples}


def tables(t3, now, temp=None):
    """3단계 뼈대 ↔ 지금 문서 → {new[{id, rows, cols, host}], changed[{id, rows, cols, host, was[행, 열], heads{text, gone, new}, examples[…]}], gone(없어진 표 수),
    resized(행·열 수만 달라진 표 수 — 알리지 않음), counts}. **같은 표 = 열헤더·행헤더가 그대로인 표**(사용자 2026-11-10 「열/행헤더가 변경이 없으면 동일한 것으로 본다」) —
    행·열 수가 달라져도(자료 행을 더하거나 지움) 헤더가 그대로면 바뀐 표가 아니다. changed = 헤더가 바뀐 표(head_diff).
    여러 칸 표만(1칸 상자는 표가 아니다 — §8), 블록 id 가 있는 표만(id 없는 그릇은 문서 차례마다 번호가 달라 견줄 수 없다). 지금 TEMP 표·그때 TEMP 표는 뺀다(§15 의 몫)."""
    known = {t["id"]: t for t in t3.get("tables") or ()}
    skip = {x["id"] for x in t3.get("tempTables") or ()} | set((temp or {}).get("tables") or ())
    cur = {tb["id"]: tb for tb in HT.collect(now, HT.temp_tables(temp)[0]) if not str(tb["id"]).startswith("k")}
    new = [{"id": k, "rows": tb["rows"], "cols": tb["cols"], "host": tb["host"]} for k, tb in cur.items() if k not in known and k not in skip]
    changed, resized = [], 0
    for k, tb in cur.items():
        t = known.get(k)
        if t is None or k in skip:
            continue
        was = [int(t.get("rows") or 0), int(t.get("cols") or 0)]
        d = head_diff(t, tb)
        if any(d["heads"].values()):
            changed.append({"id": k, "rows": tb["rows"], "cols": tb["cols"], "host": tb["host"], "was": was, **d})
        elif [tb["rows"], tb["cols"]] != was:
            resized += 1
    gone = sum(1 for k in known if k not in cur and not str(k).startswith("k"))
    return {"new": new, "changed": changed, "gone": gone, "resized": resized, "counts": {"new": len(new), "changed": len(changed), "gone": gone, "resized": resized}}


# ---- 세션 -----------------------------------------------------------------------------------------------------------

def _run(res):
    m = (res or {}).get("meta") or {}
    return [m.get("run"), m.get("at")]


def _base(sess, st, g):
    """그 2단계 결과가 선 1단계 결과 — 메모리의 지금 1단계가 그 실행이면 그것, 아니면 작업 폴더에서(없으면 None)."""
    n = (g.get("meta") or {}).get("stage1Run")
    s1 = st.get("stage1")
    if s1 is not None and (s1.get("meta") or {}).get("run") == n:
        return s1
    d = HR._dir(sess)
    return HR._read(d / str(n) / "stage1.json") if d is not None and isinstance(n, int) else None


def _skeleton(sess, st, g, hv):
    """세션이 쥐어 두는 뼈대(2단계 실행·라벨 지정 판마다 하나) — 저장 끔이어도 그 뒤 다시 뽑은 1단계에 밀려 기준이 사라지지 않게 처음 물을 때 만든다.
    기준 1단계를 못 찾아 레터만 아는 뼈대는 쥐어 두지 않는다(다음에 다시 찾는다)."""
    key = [_run(g), hv.get("version")]
    c = st.get("driftSkel")
    if c is None or c["key"] != key:
        base = _base(sess, st, g)
        sk = skeleton(g, base, hv)
        if base is None:
            return sk
        c = st["driftSkel"] = {"key": key, "skel": sk}
    return c["skel"]


def check(sess):
    """지금 문서를 2·3단계 뼈대와 견준다 → {rev, stage2: None(결과 없음) | {moved, letters, formats, wrong, counts, formatsChecked}, stage3: None | {moved, new, changed, gone, resized, counts},
    extracted(견주려고 여기서 문서를 다시 뽑았나), seconds}. `moved` false = 그 결과를 만든 뒤 문서(와 1단계)가 그대로라 견줄 것이 없음.
    같은 문서 차례·같은 결과·같은 지정이면 기억해 둔 답."""
    st = HR.state(sess)
    lock = st.setdefault("driftLock", threading.Lock())
    with lock:
        t0 = time.monotonic()
        g, t3, s1 = st.get("stage2"), st.get("stage3"), st.get("stage1")
        hv = HR.hints(sess)
        sk = _skeleton(sess, st, g, hv) if g is not None else None
        tol_sha, rules_v = G.get("tolerance")["sha1"], R.load().get("version")  # 오차 기준·규칙 저장소는 **견줄 때의 것** — 바뀌면 같은 문서 차례여도 다시 견준다
        now, extracted = None, False
        with sess.lock:  # 차례·오버레이를 읽는 동안은 짧게, 문서를 다시 뽑을 때만 길게 — 편집과 겹치지 않게(1단계와 같음)
            rev = sess.rev
            ov = getattr(sess, "outline", None) or {}
            placed = {}  # 개요 줄 자리가 둘째 줄을 맞춘 줄(spec_hwpx_웹편집 ② §8-1) — left = 사용자가 정한 슬롯 자리 규칙(레터 위치·둘째 줄 mm)이 왼쪽 여백도 옮기는 줄
            for p, x in (ov.get("lines") or {}).items():
                if x.get("first") is not None:
                    pos = (OE._slot(ov, x.get("tpl"), x.get("level")) or {}).get("pos") or {}
                    placed[p] = {"first": x["first"], "left": bool(pos.get("set"))}
            key = [rev, _run(g), _run(t3), _run(s1), hv.get("version"), (hv.get("temp") or {}).get("version"), E.VERSION, tol_sha, rules_v]
            c = st.get("drift")
            if c is not None and c["key"] == key:
                return c["data"]
            fresh = s1 if s1 is not None and (s1.get("meta") or {}).get("rev") == rev and s1.get("version") == E.VERSION else None

            def moved(res):  # 그 결과를 만든 뒤 문서가 바뀌었거나, 지금 1단계가 그 결과가 선 실행이 아님(규칙 보강으로 다시 뽑음)
                m = res.get("meta") or {}
                return m.get("rev") != rev or (fresh is not None and (fresh.get("meta") or {}).get("run") != m.get("stage1Run"))
            need = [res is not None and moved(res) for res in (g, t3)]
            if any(need):
                now = fresh
                if now is None:
                    now = E.extract(sess.doc, doc_key=getattr(sess, "doc_key", None) or works.sha256(sess.original))
                    extracted = True
        temp = None
        if now is not None:
            temp = HR.temp_label(sess) if now is s1 else TP.label(now, hv.get("temp"))
        data = {"rev": rev, "stage2": None, "stage3": None, "extracted": extracted}
        if g is not None:
            s2 = NONE2
            if need[0]:
                flagged = set()
                s2 = headings(sk, now, temp=temp, hints=hv, placed=placed, flagged=flagged)
                kept = set()
                if flagged and ov.get("lines"):   # 걸린 줄 가운데 제 템플릿 슬롯의 확정 서식을 지키는 줄은 앎(confirmed — 문서를 읽으니 잠금 안 · 그 사이 문서가 바뀌었으면 거르지 않는다: 다음 물음이 다시 견준다)
                    with sess.lock:
                        if sess.rev == rev:
                            kept = confirmed(sess.doc, getattr(sess, "outline", None) or ov, flagged)
                if kept:
                    s2 = headings(sk, now, temp=temp, hints=hv, placed=placed, kept=kept)
                s2 = {**s2, "tplKept": len(kept)}
            data["stage2"] = {"moved": need[0], **s2}
        if t3 is not None:
            data["stage3"] = {"moved": need[1], **(tables(t3, now, temp) if need[1] else NONE3)}
        data["seconds"] = round(time.monotonic() - t0, 3)
        st["drift"] = {"key": key, "data": data}
        return data

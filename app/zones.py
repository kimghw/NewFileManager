"""편집 구역 — 자동 판독 · 지정 · 출처를 입힌 보기의 순수 계산(spec_구역 ② §2~§5). `app.server` · `app.works` · 세션을 import 하지 않는다 — 문서를 안 고치고 LLM 도 안 부른다.

- `read(snap)` = 자동 판독(spec_구역 ② §2 「자동 판독」) → `info{order, kinds, cellsOf, auto, path, text, orgs, stages}`. snap = {blocks, values | None, graph | None, tables | None, hints, prior}
  (tables = 3단계 표 구조 — 지금은 안 쓴다: 표의 칸은 블록의 격자에서 바로 읽는다).
  근거는 셋이다: **묶음**(`core.find` 의 구분 기준 묶음 — 기준마다 가장 안쪽 항목) · **윗 제목**(묶음 밖 블록 — 기관 낱말이 든 구분 라벨) · **표의 칸**(이름표 칸 옆·아래의 값 — 「표 안의 값 읽기」).
  취합의 느슨한 판독(`merge_gather_frame.make` 의 scope · `merge_pairs._ident`)과 뼈대는 같고 값 읽기만 엄격하다 — 못 읽으면 `unknown`, 근거가 다르면 `conflict` 로 남긴다(짐작하지 않는다).
  기관 이름 읽기는 둘로 가른다: 라벨 줄·윗 제목 = 문장 속 이름 찾기(`_names`) · 표의 값 칸 = 칸의 글이 통째로 그 이름일 때만(`_cell_org` — 「한국선급엔지니어링」 은 「한국선급」 이 아니다).
  큰 문서(최상위 블록 2,000 · 칸 3,000)에서 1초 안팎 — 거의 다 묶음 찾기(`core.find` · `rnd.levels_of`)의 시간이다.
- `build(info, marks, origins, dims)` = 지정(② §3) · 출처(② §4)를 입힌 보기(② §5) → `view{blocks, cells, zones, marks, origins, counts, _tableOf, _info}`. 옵션·지정이 바뀔 때마다 불린다(수 ms).
  info 의 라벨 사전을 고치지 않는다(바뀌지 않은 블록의 라벨은 info 의 그 사전 그대로 싣는다 — 받은 쪽도 고치지 말 것).
- `label_of` · `label_text` · `norm_label` · `norm_dims` · `mark_make` · `marks_put` · `marks_prune` · `inherit` · `origin_event`.

라벨 = `{org, orgKind: org|unknown|conflict|None, stage, year(전체 차례), src{기준: auto|mark|origin}, ev{기준: group|cell|path}}` — `ev` 는 스크립트가 읽은 값(src auto)의 근거다.
`why`(근거가 서로 다를 때만 붙는다 — 값이 다 비어도 라벨은 남는다: 「값 없음」 과 「엇갈려서 비움」 을 가른다) = `{byNo?: 번호(주관·공동 k)로 읽은 열쇠, byName?: [라벨 글에서 찾은 열쇠 …], byGroup?: 묶음이 말한 열쇠, byPath?: 윗 제목이 말한 열쇠, byCell?: [표의 칸이 말한 열쇠 …],
year?: {byGroup: 차년도 | None, byCell: 차년도 | [차년도 …](칸이 걸친 행의 차년도 열들이 서로 엇갈림)}, stage?: {byGroup: 단계, byCell: 단계}}` — 기관이 다르면 `orgKind: conflict`(org None), 차년도·단계가 다르면 그 기준을 비운다."""
import re
import uuid
from datetime import datetime

from app import merge_gather_frame as F
from app import merge_pairs as P
from app.division_profiles import _structure as structure
from app.division_profiles import rnd
from app.division_profiles.rnd import core

DIMS = ("org", "stage", "year")
DIM_NAME = {"org": "기관", "stage": "단계", "year": "차년도"}
TEXT_MAX = 60
PATH_MAX = 8
CELL_MAX = 24   # 이름표 칸의 글 길이 상한(빈칸 뗀 글)
# 이름표 칸(② §2 「표 안의 값 읽기」) — 괄호 안과 빈칸을 뗀 글이 **낱말 그대로**일 때만(fullmatch). 역할이 든 이름표(「주관연구개발기관」·「공동연구개발기관」·「해당과제의 주관연구개발기관」)는
# 그 표가 누구 것인지가 아니라 「주관이 누구인지」 를 적는 자리라 읽지 않는다 · 「연차휴가 일수」·「연차별 예산」 처럼 낱말이 섞인 칸도 이름표가 아니다.
ORG_CELL = re.compile(r"연구개발기관명?|기관명|수행기관명?|참여기관명?|소속기관명?|보유기관명?|소유권자")
YEAR_CELL = re.compile(r"(?:구입|사용|해당|수행|집행|개발)?(?:연차|차년도|년차)")
ROLE_CELL = re.compile(r"(?:주관|공동|위탁)(?:연구개발)?기관")   # 이름표 칸의 왼쪽 칸이 역할 줄의 머리(「주관연구개발기관 | 기관명 | 이름」)면 그 이름은 표 전체의 기관이 아니다
YEAR_VALUE = re.compile(r"^(?:\(?(\d{1,2})단계\)?[-,·]?)?(\d{1,2})(?:차년도|년차)?(?:\((?:19|20)\d\d년?\))?$")   # 값 칸(빈칸 뗀 글) 「2차년도」·「2차년도(2026년)」·「2」·「2단계 1차년도」
COL_MIN = 2    # 값으로 알아보는 기관 열(② §2 「기관 열」 — 기관 이름 · 「개발 내용 … (기관 이름)」 이 행마다 되풀이되는 열)로 보는 칸 수의 하한
# 기관 열로 보지 않는 열의 머리 — 그 열의 기관은 행을 쓴 기관이 아니라 상대(발행·발급·인증한 곳 · 거래·공급·구매·판매·납품·고객 · 수요처). 2026-11-18 astra 반례(「발행기관 | 인증명」 · 「활동 | 거래처」)
OTHER_ORG_HEAD = re.compile(r"발행|발급|인증|거래|고객|상대|공급|구매|판매|납품|수요")
_TAIL = re.compile(r"[(（]([^()（）]*)[)）]$")
ORG_TEXT = {"unknown": "기관 모름", "conflict": "기관 확인 필요"}
WHY_ORG = ("byNo", "byName", "byGroup", "byPath", "byCell")

_WS = re.compile(r"\s+")
_PAREN = re.compile(r"\([^()]*\)|（[^（）]*）")


def _int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _short(text, n=TEXT_MAX):
    t = _WS.sub(" ", str(text or "")).strip()
    return t if len(t) <= n else t[:n - 1] + "…"


def _stage_of(stages, year):
    """전체 차례 차년도 → 단계 | None(범위 밖 — `core.stage_year` 는 마지막 단계로 접는다: 여기서는 비운다)."""
    if not _int(year) or year < 1:
        return None
    for s, n in enumerate(stages, 1):
        if year <= n:
            return s
        year -= n
    return None


# ---- 옵션 ----------------------------------------------------------------------------------------------------

def norm_dims(x):
    """보이는 기준 목록(② §0 「옵션」) → DIMS 차례 · 겹친 것 없이. 목록이 아니거나 모르는 값이 있으면 ValueError(글은 화면에 그대로)."""
    if not isinstance(x, (list, tuple)):
        raise ValueError("편집 구역의 기준은 목록으로 보냅니다(기관 org · 단계 stage · 차년도 year)")
    bad = [str(d) for d in x if not isinstance(d, str) or d not in DIMS]
    if bad:
        raise ValueError(f"모르는 기준입니다: {', '.join(bad)} — 기관(org) · 단계(stage) · 차년도(year) 가운데서 고릅니다")
    return [d for d in DIMS if d in x]


# ---- 자동 판독: 값 읽기(spec_구역 ② §2 「값 읽기 — 엄격하게」) ---------------------------------------------------

def _names(text, keys):
    """**라벨 줄·윗 제목**의 글(「※」 뒤 안내 글은 뺌)에 든 과제 기관 열쇠(문서 순 — 문장 속 이름 찾기. 표의 값 칸은 `_cell_org`) — 다른 찾은 열쇠의 자리 안에 통째로 든 것은 뺀다(A · AB 가 모두 걸리면 AB 만. A 가 AB 밖에 따로 또 적혀 있으면 A 도 남는다)."""
    t = P.org_key(core.NOTE.sub("", str(text or "")))
    if not t:
        return []
    spans = []
    for k in keys:
        if not k:
            continue   # 빈 열쇠는 「든 것」 으로 치지 않는다
        i = t.find(k)
        while i >= 0:
            spans.append((i, i + len(k), k))
            i = t.find(k, i + 1)
    out = []
    for a, e, k in sorted(spans):
        if k not in out and not any(k2 != k and a2 <= a and e <= e2 for a2, e2, k2 in spans):
            out.append(k)
    return out


def _plain(text):
    """괄호 안을 뗀 글(겹친 괄호는 안쪽부터)."""
    for _ in range(3):
        cut = _PAREN.sub("", text)
        if cut == text:
            break
        text = cut
    return text


def _cell_org(text, keys):
    """표의 **값 칸** 글 → 과제 기관 열쇠 | None — 「※」 뒤와 괄호 안(「(김○○ 외 2)」)을 떼고 정리한 글(merge_pairs.org_key — ㈜·주식회사·빈칸 뗌)이 열쇠와 **통째로 같을 때만**.
    「한국선급엔지니어링」 은 「한국선급」 이 아니다(문장 속 이름 찾기 `_names` 와 가른다 — 못 읽은 칸은 비워 둔다: 짐작하지 않는다). 이름에 괄호가 든 기관은 괄호째로도 견준다."""
    t = core.NOTE.sub("", str(text or ""))
    if not t.strip():
        return None
    for s in (t, _plain(t)):
        k = P.org_key(s)
        if k and k in keys:
            return k
    return None


def _tail_org(text, keys):
    """칸 글이 「내용 … (기관 이름)」 으로 **끝나면** 그 괄호 안의 과제 기관 열쇠 | None — 괄호 앞에 글이 있고 괄호 안이 열쇠와 통째로 같을 때만(`_cell_org`).
    일정표의 「서브모듈 기초설계\\n(인텍전기전자)」 꼴. 가운데 괄호(「기술 기준(안)」)·여러 기관(「(가나, 다라)」)·품은 이름(「(한국선급엔지니어링)」)은 아니다."""
    t = core.NOTE.sub("", str(text or "")).strip()
    m = _TAIL.search(t)
    if not m or not t[:m.start()].strip():
        return None
    return _cell_org(m.group(1), keys)


def _org_cols(cells, keys, at):
    """**값으로 알아보는 기관 열**의 칸 → [(칸, 열쇠)] — 이름표 낱말이 없어도 칸의 값이 행마다 기관을 가르는 열(② §2 「기관 열」). at = {(행, 열): 칸}(병합 칸이 덮은 자리 포함).
    칸 하나가 기관을 말하는 때: **첫 열**(행 머리 열 — 보유현황 표의 합친 「인텍\\n전기전자㈜」)의 칸 글이 통째로 과제 기관 이름(`_cell_org`)이거나, 어느 열이든 「… (기관 이름)」 으로 끝날 때(`_tail_org` — 일정표의 「개발 내용」).
    첫 열이 아닌 열의 이름 그대로인 칸은 안 본다 — 그 열의 뜻이 발행기관 · 과제의 주관기관 · 상대 업체일 수 있다(실측: 「인증기준 | 발행기관 한국선급」 · 「주관연구개발기관 / 당시 소속기관」).
    왼쪽 칸이 역할 줄의 머리(「주관연구개발기관 | 인텍」)인 칸 · 맨 위 칸이 역할 낱말인 열은 안 본다 — 참여 기관을 적는 공통 표의 줄은 그 기관의 자리가 아니다(이름표 규칙의 ROLE_CELL 과 같은 까닭).
    같은 열(시작 열 · 너비)에서 그런 칸이 COL_MIN 개 이상 · **기관이 둘 이상**(행을 기관별로 가르는 열 — 한 기관뿐이면 표 전체의 일이라 LLM 검토의 후보로 둔다) · 그 열의 글 든 칸(머리 칸 포함) 가운데 절반 이상일 때만 —
    몇 칸에 붙은 괄호(「사용용도(업체)」 열 끝의 「형식승인 서비스\\n(한국선급)」 = 상대 업체)를 행의 기관으로 읽지 않게. 못 읽은 칸(「한양대학교 에리카산학협력단」)은 그 행을 비워 둔다."""
    def says(c):
        left = at.get((c["row"], c["col"] - 1))
        if left is not None and left["id"] != c["id"] and ROLE_CELL.search(core._bare(left.get("text"))):
            return None
        return (_cell_org(c.get("text"), keys) if c["col"] == 0 else None) or _tail_org(c.get("text"), keys)
    by = {}
    for c in cells:
        by.setdefault((c["col"], c.get("colSpan") or 1), []).append(c)
    out = []
    for cs in by.values():
        head = core._bare(min(cs, key=lambda c: c["row"]).get("text"))
        if ROLE_CELL.search(head) or OTHER_ORG_HEAD.search(head):   # 맨 위 칸이 역할 낱말 · 상대 기관 낱말(「발행기관」 · 「거래처」 — 2026-11-18 astra 반례)인 열
            continue
        got = [(c, k) for c in cs if (k := says(c))]
        if len(got) >= COL_MIN and len({k for _, k in got}) >= 2 and 2 * len(got) >= sum(1 for c in cs if _WS.sub("", c.get("text") or "")):
            out += got
    return out


def _org_pick(by_no, hit):
    """번호로 읽은 열쇠(없으면 None) · 글에서 찾은 열쇠들 → (orgKind, 열쇠 | None, why | None). 번호의 기관이 글의 이름들에 없으면 conflict, 번호가 없으면 이름이 정확히 하나일 때만 그 기관."""
    if by_no:
        if hit and by_no not in hit:
            return "conflict", None, {"byNo": by_no, "byName": list(hit)}
        return "org", by_no, None
    if len(hit) == 1:
        return "org", hit[0], None
    return "unknown", None, None


def _org_item(g, it, values, keys, old=()):
    """기관 묶음의 항목 하나 → (orgKind, 열쇠 | None, why | None). 번호 = 주관(0)·공동 k — 값에 없는 번호, 차례 없는 「공동」, 열·외 기관·국외·위탁 항목에는 번호가 없다.
    라벨에 과제에 없는 이름이 적힌 묶음(엔진이 「작성한 문서」 로 본 것 — named)은 번호(자리 차례)를 믿지 않는다.
    old = 앞서 반영한 값(prior)에만 있는 기관 열쇠 — 라벨에 옛 이름만 적혀 있으면 번호를 믿지 않고 「기관 모름」(2026-11-18 astra P1: 엔진은 옛 이름을 「다시 반영할 수 있는 자리」 로 보아
    named 보호를 풀지만, 그것이 그 내용이 지금 같은 번호의 기관 것이라는 근거는 아니다 — 옛 「가나」 내용이 새 구성의 주관 「마바」 로 붙던 것)."""
    v = it.get("value")
    k = v[1] if isinstance(v, tuple) and len(v) == 2 and v[0] in ("lead", "joint") else None
    hit = _names(it.get("labelText"), keys)
    if old and not hit and _names(it.get("labelText"), old):
        return "unknown", None, None
    by_no = None
    if _int(k) and 0 <= k <= len(values["orgs"]["joint"]) and (k == 0) == (v[0] == "lead") and not g.get("named"):
        by_no = P.org_key(core.org_name(values, k)) or None
    return _org_pick(by_no, hit)


def old_keys(prior, keys):
    """앞서 반영한 값들(prior — norm_values 꼴 목록)에만 있는 기관 열쇠(지금 열쇠에 없는 것 · 긴 것 먼저) — `_org_item` 의 old."""
    now, out = set(keys), set()
    for v in prior or ():
        orgs = (v or {}).get("orgs") or {} if isinstance(v, dict) else {}
        for n in [orgs.get("lead") or "", *(orgs.get("joint") or ())]:
            k = P.org_key(n) if isinstance(n, str) else None
            if k and k not in now:
                out.add(k)
    return sorted(out, key=len, reverse=True)


def _year_value(text, stages):
    """표의 값 칸 글 → 전체 차례 차년도 | None. 단계가 하나면 그 번호, 둘 이상이면 글에 단계가 적혀 있을 때만(「2단계 1차년도」) — 아니면 비운다. 범위 밖도 비운다."""
    m = YEAR_VALUE.match(_WS.sub("", core.NOTE.sub("", str(text or ""))))
    if not m:
        return None
    if m.group(1) is None and len(stages) != 1:
        return None
    s, y = int(m.group(1) or 1), int(m.group(2))
    return sum(stages[:s - 1]) + y if 1 <= s <= len(stages) and 1 <= y <= stages[s - 1] else None


def _memberships(groups, values, keys, old=()):
    """구분 기준 묶음 → ({블록·칸 id: {"org": (항목 크기, (orgKind, 열쇠, why)), "stage": (크기, 단계 | None), "year": (크기, (전체 차례 | None, abs|free))}}, {표 id: 그 표 안에 묶음이 있는 기준}).
    기준마다 가장 안쪽(작은) 항목이 이긴다(`merge_gather_frame._memberships` 와 같게). 못 읽은 값(자리표시 N · 범위 밖)도 **빈 값으로 남겨** 바깥 항목의 값이 대신 붙지 않게 한다.
    차년도: 단계-차년도 = 그 단계의 것(abs) · 단계 항목 안의 차년도 묶음(ctx) = 단계 안 차년도 → 전체 차례(abs) · 그 밖 = 전체 차례로 읽되 블록의 단계와 안 맞으면 다시 본다(free — `_auto_label`)."""
    stages = values["stages"]
    total, n_st = sum(stages), len(stages)
    best, inside = {}, {}
    for g in groups:
        dim = g["dim"]
        if g.get("table") and dim in (core.ORG, core.YEAR, core.STAGE_YEAR):
            inside.setdefault(g["table"], set()).add("org" if dim == core.ORG else "year")
        base, ctx = g.get("yearBase") or 0, g.get("ctx")
        for it in g["items"]:
            v = it.get("value")
            if dim == core.ORG:
                what, val = "org", _org_item(g, it, values, keys, old)
            elif dim == core.STAGE:
                what, val = "stage", v if _int(v) and 1 <= v <= n_st else None
            elif dim == core.YEAR:
                what = "year"
                if not _int(v) or v < 1:
                    val = (None, "abs")
                elif base:   # 「다음 연도」 절의 기관-연도 표 — 행 하나가 다음 차년도
                    val = (v + base if v + base <= total else None, "abs")
                elif _int(ctx):
                    val = (sum(stages[:ctx - 1]) + v if 1 <= ctx <= n_st and v <= stages[ctx - 1] else None, "abs")
                elif ctx is not None:   # 자리표시 단계 안("?") — 어느 단계의 차년도인지 모른다
                    val = (None, "abs")
                else:
                    val = (v if v <= total else None, "free")
            elif dim == core.STAGE_YEAR:
                what = "year"
                ok = isinstance(v, tuple) and len(v) == 2 and _int(v[0]) and _int(v[1]) and 1 <= v[0] <= n_st and 1 <= v[1] <= stages[v[0] - 1]
                val = (sum(stages[:v[0] - 1]) + v[1] if ok else None, "abs")
            else:
                continue   # 세부과제
            ids = set(it.get("scope") or ())
            if it.get("label"):
                ids.add(it["label"])
            n = len(ids)
            for x in ids:
                cur = best.get(x)
                if cur is None:
                    best[x] = {what: (n, val)}
                elif what not in cur or n < cur[what][0]:
                    cur[what] = (n, val)
    return best, inside


def _path_org(nodes, idx, keys):
    """윗 제목들(안쪽 → 바깥 — 그래프 노드) 가운데 기관 낱말이 든 구분 라벨 → (orgKind, 열쇠 | None) | None. `merge_gather_frame._path_org` 의 일을 **지금 문서의 그 문단 글**로 한다:
    그 문단이 지금 문서에 없거나 지금 글에 기관 낱말이 없으면 안 채운다(낡은 그래프의 옛 라벨 글을 믿지 않는다). 절·장 제목(옛 글이든 지금 글이든)이 먼저 나오면 그 바깥은 안 본다.
    이름은 하나일 때만 그 기관, 아니면 unknown(번호는 안 본다 — 기관마다 「공동연구개발기관1」 로 적은 문서가 있다)."""
    for n in nodes:
        old = P._ws(f"{n.get('letter') or ''} {n.get('text') or ''}")
        b = idx.get(n.get("para"))
        now = P._ws(b.get("text")) if b is not None and b.get("type") == "paragraph" else None
        if any(core.SECTION.match(x) or P._CHAPTER.match(x) for x in (old, now) if x):
            return None
        if n.get("role") != "label":
            continue
        was = bool(core.ORG_RE.search(old))
        t = core.NOTE.sub("", now) if now is not None else ""
        if core.ORG_RE.search(t):
            hit = _names(t, keys)
            return ("org", hit[0]) if len(hit) == 1 else ("unknown", None)
        if was:
            return None   # 그래프에는 기관 라벨이었는데 그 문단이 없어졌거나 지금 글은 기관 라벨이 아니다
    return None


# ---- 자동 판독: 표 안의 값 읽기(spec_구역 ② §2 「표 안의 값 읽기」) ----------------------------------------------

def _tag_kinds(text, keys):
    """이름표 칸인가 → ("org",) | ("year",) | () — 짧고(빈칸 뗀 글 CELL_MAX 자 이하) 괄호 안을 뗀 글이 기관·차년도 이름표 **낱말 그대로**(ORG_CELL · YEAR_CELL)이며 그 칸 자체에는 값(과제 기관 이름)이 없는 칸."""
    text = text or ""
    if not text or len(text) > CELL_MAX * 8:
        return ()
    t = core._bare(text)
    if not t or len(t) > CELL_MAX:
        return ()
    word = _plain(t)
    if ORG_CELL.fullmatch(word):
        return () if _names(text, keys) else ("org",)   # 「기관명(한국선급)」 — 값이 든 칸은 이름표가 아니다
    return ("year",) if YEAR_CELL.fullmatch(word) else ()


def _table_read(b, keys, stages, skip=()):
    """본문 최상위 표 하나 → (표 전체의 근거 {"org"?: (orgKind, 열쇠, why), "year"?: 전체 차례} | None, {칸 id: 같은 꼴}). 값 칸의 기관은 통째로 일치할 때만(`_cell_org`).
    - 이름표의 아래쪽 범위: 그 이름표 바로 아래에 이어진 머리 행(이름표 칸이 있는 행)은 건너뛰고, 그 뒤 **다음 머리 행 앞까지** — 표 중간에서 열의 뜻이 바뀌면 앞 이름표는 거기서 끝난다.
      아래 칸은 이름표와 같은 열 · 같은 너비여야 한다(여러 열을 덮은 머리 아래의 세부 열은 그 머리의 값이 아니다).
    - 표 전체: 이름표 칸의 오른쪽 이웃 칸(같은 행)에 값이 있고 그 이름표 칸 아래(그 범위)에는 값이 없을 때. 그렇게 읽은 기관이 서로 다르면 conflict(차년도가 다르면 비움).
      읽지 않는 때 — 그 표 안에 그 기준의 묶음(행·열)이 있다(skip) · 값이 옆으로 이어진다(값마다 열이 있는 머리 행) · 행마다 기관이 갈린다 · 이름표의 왼쪽 칸이 역할 줄의 머리다(「주관연구개발기관 | 기관명 | 이름」).
    - 행: 이름표 칸의 아래 칸들에 값이 있을 때 — 그 값 칸이 걸친 행 안에 온전히 든 모든 칸. 한 행의 기관 열들이 서로 다른 기관을 말하면 conflict.
    - 행(기관 열): 기관 이름표 칸이 **없는** 표에서, 값으로 알아보는 기관 열(`_org_cols` — 첫 열의 합친 기관 이름 칸 · 일정표 「개발 내용」 의 「(기관 이름)」)의 칸이 걸친 행 — 위 「행」 과 같은 규칙.
      기관 이름표 칸이 있으면 그것이 먼저다(값으로는 안 본다 — 그런 표의 다른 열 괄호는 상대 업체·발급 기관일 수 있다).
    왼쪽에 값이 있는 꼴(「이름 | 연구개발기관명」)과 칸 안의 표는 읽지 않는다."""
    cells = b.get("cells") or ()
    if not cells:
        return None, {}
    tags = [(c, k) for c in cells if (k := _tag_kinds(c.get("text"), keys))]
    at = {}
    for c in cells:
        for r in range(c["row"], c["row"] + (c.get("rowSpan") or 1)):
            for k in range(c["col"], c["col"] + (c.get("colSpan") or 1)):
                at[(r, k)] = c
    tails = [] if any("org" in k for _, k in tags) else _org_cols(cells, keys, at)
    if not tags and not tails:
        return None, {}
    n_rows, memo = max(r for r, _ in at) + 1, {}
    heads = sorted({c["row"] for c, _ in tags})   # 머리 행 — 이름표 칸이 시작하는 행

    def value(c, kind):
        key = (c["id"], kind)
        if key not in memo:
            memo[key] = _cell_org(c.get("text"), keys) if kind == "org" else _year_value(c.get("text"), stages)
        return memo[key]
    whole, claims = {"org": [], "year": []}, {"org": {}, "year": {}}   # claims[기준][행] = [값 …](이름표 열마다 하나)
    for h, kinds in tags:
        cs, top = h.get("colSpan") or 1, h["row"] + (h.get("rowSpan") or 1)
        while top in heads:
            top += 1   # 여러 줄 머리 — 바로 아래에 이어진 머리 행
        end = next((r for r in heads if r > top), n_rows)
        below, seen = [], {h["id"]}
        for r in range(top, end):
            x = at.get((r, h["col"]))
            if x is not None and x["id"] not in seen:
                seen.add(x["id"])
                if x["row"] >= top and x["col"] == h["col"] and (x.get("colSpan") or 1) == cs:
                    below.append(x)
        right, left = at.get((h["row"], h["col"] + cs)), at.get((h["row"], h["col"] - 1))
        for kind in kinds:
            vals = [(x, v) for x in below if (v := value(x, kind)) is not None]
            if vals:
                for x, v in vals:
                    for r in range(x["row"], min(x["row"] + (x.get("rowSpan") or 1), end)):
                        claims[kind].setdefault(r, []).append(v)
            elif kind not in skip and right is not None and right["id"] != h["id"] and (v := value(right, kind)) is not None:
                nxt = at.get((h["row"], right["col"] + (right.get("colSpan") or 1)))
                if nxt is not None and nxt["id"] not in (h["id"], right["id"]) and value(nxt, kind) not in (None, v):
                    continue   # 값이 옆으로 이어진다 — 값마다 열이 있는 머리 행
                if kind == "org" and left is not None and left["id"] != h["id"] and ROLE_CELL.search(core._bare(left.get("text"))):
                    continue   # 역할 줄의 이름 — 그 표가 누구 것인지가 아니다
                whole[kind].append(v)
    for x, v in tails:
        for r in range(x["row"], x["row"] + (x.get("rowSpan") or 1)):
            claims["org"].setdefault(r, []).append(v)
    row_org, row_year, year_clash = {}, {}, {}
    for r, vs in claims["org"].items():
        ks = list(dict.fromkeys(vs))
        row_org[r] = ("org", ks[0], None) if len(ks) == 1 else ("conflict", None, {"byCell": ks})
    for r, vs in claims["year"].items():
        if len(set(vs)) == 1:
            row_year[r] = vs[0]
        else:
            year_clash[r] = sorted(set(vs))   # 한 행의 차년도 열들이 서로 다른 차년도를 말한다 — 비우되 「값 없음」 이 아니라 「엇갈림」 으로 남긴다(표 전체의 값을 물려받지 않게 — 2026-11-18 astra P1)
    per = {}
    for c in cells if row_org or row_year or year_clash else ():
        rows = range(c["row"], c["row"] + (c.get("rowSpan") or 1))
        e, got = {}, [row_org.get(r) for r in rows]
        if all(got):
            if len({(g[0], g[1]) for g in got}) == 1:
                e["org"] = got[0]
            elif any(g[0] == "conflict" for g in got):
                e["org"] = ("conflict", None, {"byCell": list(dict.fromkeys(k for g in got for k in ([g[1]] if g[0] == "org" else g[2]["byCell"])))})
        clash = sorted({y for r in rows for y in year_clash.get(r, ())})
        ys = {row_year.get(r) for r in rows}
        if clash:
            e["yearClash"] = sorted(set(clash) | (ys - {None}))
        elif len(ys) == 1 and None not in ys:
            e["year"] = ys.pop()
        if e:
            per[c["id"]] = e
    w = {}
    ks = list(dict.fromkeys(whole["org"]))
    if ks and len({(g[0], g[1]) for g in row_org.values()}) < 2:
        w["org"] = ("org", ks[0], None) if len(ks) == 1 else ("conflict", None, {"byCell": ks})
    if len(set(whole["year"])) == 1 and len(set(row_year.values())) < 2 and not year_clash:   # 엇갈린 행이 있으면 표 전체의 차년도를 세우지 않는다
        w["year"] = whole["year"][0]
    return (w or None), per


# ---- 자동 판독: 근거 모으기 → 라벨 ---------------------------------------------------------------------------------

def _join_org(a, ev, c):
    """묶음·윗 제목의 기관 a(orgKind, 열쇠, why — 없으면 None · 근거 ev)와 표의 칸이 말한 기관 c → (orgKind, 열쇠, why, 근거). 한쪽만 있으면 그것, 같은 기관이면 그대로, 다르면 conflict(둘 다 근거로)."""
    if c is None:
        return (*a, ev) if a else (None, None, None, None)
    if a is None or a[0] == "unknown":   # 기관 자리인데 누구인지 못 읽은 곳 — 칸의 이름이 말해 준다
        return (*c, "cell")
    said = [c[1]] if c[0] == "org" else list((c[2] or {}).get("byCell") or ())
    if a[0] == "org":
        if c[0] == "org" and c[1] == a[1]:
            return (*a, ev)
        return "conflict", None, {"byPath" if ev == "path" else "byGroup": a[1], "byCell": said}, ev
    return "conflict", None, {**(a[2] or {}), "byCell": said}, ev


def _auto_label(m, org, org_ev, cell, stages):
    """블록·칸 하나의 근거(묶음 소속 m · 기관 (orgKind, 열쇠, why) + 그 근거 · 표의 칸 근거) → (라벨 | None, 단계를 차년도에서 채웠나). 값도 엇갈린 근거(why)도 없으면 None."""
    m, cell = m or {}, cell or {}
    item = m["stage"][1] if "stage" in m else None   # 단계 항목이 말한 단계
    year, mode = m["year"][1] if "year" in m else (None, None)
    stage = item
    if year is not None:
        at = _stage_of(stages, year)
        if mode == "abs" or stage is None:
            stage = at   # 단계-차년도·단계 안 차년도는 그 단계의 것 · 단계가 비었으면 차년도에서 채운다
        elif at != stage:   # 단계는 정해졌는데 차년도가 그 단계의 것이 아니다 — 단계 안 차년도로 읽는다(2단계 아래 「1차년도」 = 3)
            year = sum(stages[:stage - 1]) + year if year <= stages[stage - 1] else None
    ev, why = {}, {}
    kind, key, w, e = _join_org(org, org_ev, cell.get("org"))
    if kind:
        ev["org"] = e
        why.update(w or {})
    c_year = cell.get("year")
    if cell.get("yearClash"):   # 칸이 걸친 행의 차년도 열들이 엇갈린다 — 차년도를 비우고 엇갈림을 남긴다(묶음이 말한 차년도도 세우지 않는다 · 단계는 묶음의 것 그대로)
        why["year"], year = {"byGroup": year, "byCell": list(cell["yearClash"])}, None
        if stage is not None:
            ev["stage"] = "group"
    elif c_year is not None:
        c_stage = _stage_of(stages, c_year)
        if stage is not None and stage != c_stage:   # 단계가 다르다 — 차년도도 설 자리가 없다
            why["stage"], why["year"] = {"byGroup": stage, "byCell": c_stage}, {"byGroup": year, "byCell": c_year}
            stage = year = None
        elif year is not None and year != c_year:
            why["year"], year = {"byGroup": year, "byCell": c_year}, None
            ev["stage"] = "group"
        else:
            ev["year"], ev["stage"] = "group" if year is not None else "cell", "group" if stage is not None else "cell"
            stage, year = c_stage, c_year
    else:
        if stage is not None:
            ev["stage"] = "group"
        if year is not None:
            ev["year"] = "group"
    if kind is None and stage is None and year is None and not why:
        return None, False   # 값도 엇갈린 근거도 없다. 값은 다 비었어도 근거(why)가 남았으면 라벨을 남긴다 — 「값 없음」 과 「엇갈려서 비움」 은 다르다
    vals = {"org": kind, "stage": stage, "year": year}
    lab = {"org": key, "orgKind": kind, "stage": stage, "year": year, "src": {d: "auto" for d in DIMS if vals[d] is not None}, "ev": {d: ev[d] for d in DIMS if d in ev and vals[d] is not None}}
    if why:
        lab["why"] = why
    return lab, stage is not None and stage != item


def _values(v):
    if not v:
        return None
    try:
        return core.norm_values(v)
    except (KeyError, TypeError, ValueError):
        return None


def _scan(snap, cells=True):
    """`read` 의 몸통 — cells=False 면 「표 안의 값 읽기」 를 건너뛴다(묶음·윗 제목 근거만: 시험이 취합의 판독과 견준다)."""
    blocks = list(snap.get("blocks") or ())
    order, kinds, cells_of, text, table_of, caps = [], {}, {}, {}, {}, []
    for b in blocks:
        bid, t = b.get("id"), b.get("type")
        if bid is None:
            continue
        if b.get("captionOf"):
            caps.append(bid)   # 캡션 블록은 표·그림에 딸려 간다 — 구역의 블록이 아니다(출처의 남은 id 를 가릴 때만 쓴다)
            continue
        order.append(bid)
        kinds[bid] = "tbl" if t == "table" else "pic" if t == "image" else "p"
        if t == "table":
            cs = sorted(b.get("cells") or (), key=lambda c: (c.get("row") or 0, c.get("col") or 0))
            cells_of[bid] = [c["id"] for c in cs]
            table_of.update((c["id"], bid) for c in cs)
            text[bid] = _short(" | ".join(x for c in cs[:8] if (x := _WS.sub(" ", c.get("text") or "").strip())))
        else:
            text[bid] = _short(b.get("text")) if t != "image" else ""
    info = {"order": order, "kinds": kinds, "cellsOf": cells_of, "auto": {}, "path": {}, "text": text, "orgs": [], "stages": [],
            "_tableOf": table_of, "_caps": caps, "_derived": {}}   # 밑줄 키 = build 가 쓰는 것(칸 → 표 · 캡션 블록 id · 단계를 차년도에서 채운 id)
    values = _values(snap.get("values"))
    nodes = (snap.get("graph") or {}).get("nodes") or ()
    if values is None and not nodes:
        return info
    by_id = {n["id"]: n for n in nodes}
    body = {n["para"]: n for n in nodes if n.get("flow") == "body"}
    idx = structure.index_blocks(blocks) if nodes else {}
    best, inside, keys, stages, cell_ev = {}, {}, [], [], {}
    if values is not None:
        info["orgs"], info["stages"] = F.orgs_of(values), list(values["stages"])
        stages = info["stages"]
        keys = sorted({o["key"] for o in info["orgs"] if o["key"]}, key=len, reverse=True)   # 빈 열쇠는 「든 것」 으로 치지 않는다
        sc = snap.get("scan")
        if sc is not None and sc.get("_values") == values:   # 구분 기준 판독(spec_구분_기준 ② §23 — 헤딩 앞 단계)이 이미 센 묶음 · 소속 · 표 안 값 읽기를 그대로(같은 값으로 센 것만)
            best, inside = sc["_best"], sc["_inside"]
            if cells:
                cell_ev = sc["_cellEv"]
        else:
            hints = [h["para"] for h in snap.get("hints") or () if isinstance(h, dict) and h.get("para")]
            groups = core.find(blocks, rnd.levels_of(blocks), values, hints=hints or None, prior=snap.get("prior"))
            best, inside = _memberships(groups, values, keys, old_keys(snap.get("prior"), keys))
        for b in blocks if cells and not (sc is not None and sc.get("_values") == values) else ():
            if b.get("type") == "table" and not b.get("captionOf") and b.get("id") is not None:
                whole, per = _table_read(b, keys, stages, inside.get(b["id"], ()))
                if whole:
                    cell_ev[b["id"]] = whole
                cell_ev.update(per)
    auto, derived, memo, cur = info["auto"], info["_derived"], {}, None   # cur = 지금까지 본 마지막 본문 제목 노드 · memo = 노드 id → (윗 제목 사슬, 윗 제목의 기관)

    def put(i, m, org, ev, cell):
        lab, d = _auto_label(m, org, ev, cell, stages)
        if lab is not None:
            auto[i] = lab
            if d:
                derived[i] = True
    for b in blocks:
        if b.get("captionOf") or b.get("id") is None:
            continue
        bid, t = b["id"], b.get("type")
        node = body.get(bid)
        if node is not None and (node.get("role") not in (*F.TITLE_ROLES, "label") or F.PLACE.match(b.get("text") or "")):
            node = None   # 글머리만 있는 줄·헤딩이 아닌 줄은 소속 사슬에 안 든다
        x = node if node is not None else cur
        if x is not None:
            if x["id"] not in memo:
                chain = [x, *F._chain(by_id, x)]
                memo[x["id"]] = (chain, _path_org(chain, idx, keys) if values is not None else None)
            chain, hit = memo[x["id"]]
            above = chain[1:] if node is not None else chain
            if (path := [s for s in (F._title(n) for n in reversed(above)) if s and not F.PLACE.match(s)][-PATH_MAX:]):
                info["path"][bid] = path
        else:
            hit = None
        if values is not None:
            m, whole = best.get(bid), cell_ev.get(bid)
            if m and "org" in m:
                put(bid, m, m["org"][1], "group", whole)
            else:
                put(bid, m, (*hit, None) if hit else None, "path", whole)
            for c in b.get("cells") or () if t == "table" else ():
                m, own = best.get(c["id"]), cell_ev.get(c["id"])
                if m and whole:   # 표 전체의 근거는 묶음 근거가 있는 칸에도 견준다(칸이 걸친 행에서 읽은 값이 있으면 그것이 먼저) — 표는 conflict 인데 칸만 묶음의 기관으로 남지 않게. 제 근거가 없는 칸은 표의 라벨을 물려받는다(build)
                    own = dict(own or {})
                    if "org" in whole and "org" in m:
                        own.setdefault("org", whole["org"])
                    if "year" in whole and ("year" in m or "stage" in m):
                        own.setdefault("year", whole["year"])
                if m is not None or own:
                    put(c["id"], m, m["org"][1] if m and "org" in m else None, "group", own)
        if t not in ("table", "image") and node is not None:
            cur = node
    return info


def read(snap):
    """자동 판독(② §2) — snap{blocks(그대로인 사본), values(norm_values 꼴) | None, graph | None, tables | None, hints[추가한 자리 dict], prior, scan?(division_scan.scan 결과 — 같은 값으로 센 것이면
    묶음 · 소속 · 표 안 값 읽기를 다시 세지 않고 쓴다: spec_구분_기준 ② §23)} →
    info{order[본문 최상위 블록 id — 캡션 블록 뺌], kinds{id: p|tbl|pic}, cellsOf{표 id: [칸 id]}, auto{블록·칸 id: 라벨 — 값이 하나라도 있거나 엇갈린 근거(why)가 남은 것}, path{블록 id: [윗 제목 사슬]},
    text{블록 id: 첫 글 TEXT_MAX 자}, orgs[{key, name, role}], stages[단계마다 차년도 수]}. values 가 없으면(못 읽는 꼴 포함) auto = {} · orgs = [] · stages = [](나머지는 그대로)."""
    return _scan(snap)


# ---- 지정(② §3) · 출처(② §4) ---------------------------------------------------------------------------------------

def _ids(xs):
    return list(dict.fromkeys(i for i in xs or () if isinstance(i, str) and i))


def _now():
    return datetime.now().isoformat(timespec="seconds")


def norm_label(body, info):
    """지정 입력 검증 → {"org"?: 열쇠 | None, "stage"?: n | None, "year"?: 전체 차례 | None} — 키 없음 = 자동 그대로 · 값 = 그 값 · None = 그 기준 없음. 틀리면 ValueError(글은 화면에 그대로).
    기관은 info["orgs"] 의 열쇠(이름으로 줘도 맞춰 준다) · 단계·차년도는 범위 안의 정수 · 둘 다 값이면 그 차년도가 그 단계의 것. 차년도만 주면 단계는 넣지 않는다(읽을 때 차년도에서 채운다)."""
    if not isinstance(body, dict):
        raise ValueError("구역으로 지정할 값(기관 · 단계 · 차년도)이 필요합니다")
    info = info or {}
    orgs, stages = info.get("orgs") or [], list(info.get("stages") or ())
    total, out = sum(stages), {}
    if "org" in body:
        v = body["org"]
        if v is not None:
            if not isinstance(v, str) or not v.strip():
                raise ValueError("기관은 프로젝트 구성의 기관 가운데서 고릅니다")
            keys = [o["key"] for o in orgs if o.get("key")]
            key = v if v in keys else P.org_key(v) if P.org_key(v) in keys else next((o["key"] for o in orgs if o.get("key") and o.get("name") == v.strip()), None)
            if key is None:
                raise ValueError(f"프로젝트 구성에 없는 기관입니다: {v.strip()}")
            v = key
        out["org"] = v
    for d, top in (("stage", len(stages)), ("year", total)):
        if d not in body:
            continue
        v = body[d]
        if isinstance(v, str) and v.strip().isdigit():
            v = int(v.strip())
        if v is not None and (not _int(v) or not 1 <= v <= top):
            if not top:
                raise ValueError(f"프로젝트 구성 값이 없어 {DIM_NAME[d]}를 정할 수 없습니다")
            raise ValueError(f"{DIM_NAME[d]}는 1~{top} 가운데서 고릅니다" + ("(전체 차례)" if d == "year" and len(stages) > 1 else ""))
        out[d] = v
    if not out:
        raise ValueError("기관 · 단계 · 차년도 가운데 적어도 하나는 정해야 합니다")
    s, y = out.get("stage"), out.get("year")
    if s is not None and y is not None and _stage_of(stages, y) != s:
        raise ValueError(f"{y}차년도(전체 차례)는 {_stage_of(stages, y)}단계의 차년도입니다 — {s}단계와 함께 지정할 수 없습니다")
    return out


def mark_make(ids, label, note="", by="user", at=None):
    """지정 하나(② §3) — {"id": 8자, "ids"[고른 본문 최상위 블록 id 그대로], "label"{org?, stage?, year?}, "note", "by", "at"}."""
    return {"id": uuid.uuid4().hex[:8], "ids": _ids(ids), "label": dict(label or {}), "note": str(note or ""), "by": by or "user", "at": at or _now()}


def marks_put(marks, mark):
    """새 목록 — 같은 id 의 지정은 그 자리에서 바꾸고(없으면 끝에 더함), 새 지정의 블록을 다른 지정에서 뺀다(한 블록은 한 지정에만). 블록이 안 남은 지정은 지운다."""
    take, out, put = set(mark.get("ids") or ()), [], False
    for m in marks or ():
        if m.get("id") == mark.get("id"):
            if not put and take:
                out.append(mark)
            put = True
            continue
        ids = [i for i in m.get("ids") or () if i not in take]
        if ids:
            out.append(m if len(ids) == len(m.get("ids") or ()) else {**m, "ids": ids})
    if not put and take:
        out.append(mark)
    return out


def marks_prune(marks, alive):
    """(새 목록, 뺀 id 수) — alive 에 없는 블록 id 를 지정에서 뺀다(블록이 안 남은 지정은 지운다). 실행 취소·복원 뒤: 같은 번호가 다른 새 문단에 다시 쓰여도 옛 지정을 물려받지 않게."""
    out, n = [], 0
    for m in marks or ():
        ids = [i for i in m.get("ids") or () if i in alive]
        n += len(m.get("ids") or ()) - len(ids)
        if ids:
            out.append(m if len(ids) == len(m.get("ids") or ()) else {**m, "ids": ids})
    return out, n


def inherit(marks, born):
    """born{새 블록 id: 그 블록이 나온 블록 id} — 나온 블록이 든 지정에 새 블록을 잇는다(그 블록 바로 뒤 — 같은 블록에서 여럿이 나왔으면 born 의 차례로). marks 를 그 자리에서 고치고 더한 수를 돌려준다.
    이미 어느 지정에 든 블록 · 지정에 없는 블록에서 나온 블록은 그대로 둔다(범위는 고른 id 그대로 — 편집이 알려 준 새 블록만 잇는다)."""
    todo = [(new, src) for new, src in (born or {}).items() if isinstance(new, str) and isinstance(src, str) and new and new != src]
    added, last = 0, {}   # last = 나온 블록 id → 그 뒤에 마지막으로 이은 블록(차례를 지킨다)
    while todo:
        rest = []
        for new, src in todo:
            if any(new in (m.get("ids") or ()) for m in marks):
                continue
            m = next((m for m in marks if isinstance(m.get("ids"), list) and src in m["ids"]), None)
            if m is None:
                rest.append((new, src))   # 나온 블록이 이번에 새로 이어질 블록일 수 있다(새 블록에서 또 나온 블록) — 한 번 더 본다
                continue
            after = last.get(src, src)
            m["ids"].insert(m["ids"].index(after if after in m["ids"] else src) + 1, new)
            last[src] = new
            added += 1
        if len(rest) == len(todo):
            break
        todo = rest
    return added


def origin_event(part, name, orgs, kind, ids, key=None, at=None):
    """출처 이벤트 하나(② §4) — 그때의 기관 문서 이름·반영할 기관을 굳혀 둔다: {"id": 8자, "part", "name", "orgs"[열쇠], "kind": cells|rows|added|filled|drop, "ids"[넣은 블록·행·칸 id], "key", "at"}."""
    return {"id": uuid.uuid4().hex[:8], "part": part, "name": name, "orgs": _ids(orgs), "kind": kind, "ids": _ids(ids), "key": key, "at": at or _now()}


# ---- 보기(② §5) ---------------------------------------------------------------------------------------------------

def _invalid(label, keys, stages, known):
    """지정의 값 가운데 지금 프로젝트 구성으로 못 쓰는 기준(② §3 「유효하지 않은 지정」) — 없어진 기관 · 범위 밖 단계·차년도 · 서로 안 맞는 단계와 차년도. 다른 값으로 옮기지 않는다.
    known = 프로젝트 구성 값이 있나 — 없으면 판단할 수 없어 꼴이 틀린 값만 가린다(지정 값을 그대로 쓴다)."""
    o, s, y = (label.get(d) for d in DIMS)
    bad = set()
    if "org" in label and o is not None and (not isinstance(o, str) or known and o not in keys):
        bad.add("org")
    if "stage" in label and s is not None and (not _int(s) or known and not 1 <= s <= len(stages)):
        bad.add("stage")
    if "year" in label and y is not None and (not _int(y) or known and not 1 <= y <= sum(stages)):
        bad.add("year")
    if known and not bad & {"stage", "year"} and s is not None and y is not None and "stage" in label and "year" in label and _stage_of(stages, y) != s:
        bad |= {"stage", "year"}   # 구성이 바뀌어 그 차년도가 그 단계의 것이 아니게 됐다
    return [d for d in DIMS if d in bad]


def _final(a, use, evs, keys, stages, known, derived):
    """블록 하나의 최종 라벨 | None(값도 엇갈린 근거도 없음) — 기준마다 지정(use — 유효한 키만) → 자동(a) → (기관만) 출처(evs[(legacy 인가, orgs)] — legacy 가 아닌 것만)."""
    use = use or {}
    if not use and not (evs and (a is None or a["orgKind"] is None)):
        return a
    org, kind, stage, year = (a["org"], a["orgKind"], a["stage"], a["year"]) if a else (None, None, None, None)
    src, ev, why = dict(a["src"]) if a else {}, dict(a.get("ev") or {}) if a else {}, dict(a.get("why") or {}) if a else {}

    def drop(d):
        src.pop(d, None)
        ev.pop(d, None)
        for k in WHY_ORG if d == "org" else (d,):
            why.pop(k, None)
    if "org" in use:
        drop("org")
        org, kind, src["org"] = use["org"], "org" if use["org"] is not None else None, "mark"
    elif kind is None and evs:   # 공통 자리 — 들어온 내용의 출처가 기관 하나짜리 이벤트 하나일 때만. 옛 기록(legacy)으로는 채우지 않는다 — 그 id 가 실행 취소 뒤 다른 문단에 다시 쓰였을 수 있다(목록에만 실린다)
        pool = [o for lg, o in evs if not lg]
        if len(pool) == 1 and len(pool[0]) == 1 and (not known or pool[0][0] in keys):
            org, kind, src["org"] = pool[0][0], "org", "origin"
    if "year" in use:
        drop("year")
        year, src["year"] = use["year"], "mark"
        if "stage" not in use:
            if year is not None and stages:   # 차년도만 지정 — 단계는 그 차년도에서 채운다
                drop("stage")
                stage, src["stage"] = _stage_of(stages, year), "mark"
            elif year is None and derived:    # 차년도 없음 — 그 차년도에서 채웠던 단계도 없다
                drop("stage")
                stage = None
    if "stage" in use:
        drop("stage")
        stage, src["stage"] = use["stage"], "mark"
        if "year" not in use and stage is not None and year is not None and stages and _stage_of(stages, year) != stage:
            drop("year")   # 자동으로 읽은 차년도가 지정한 단계의 것이 아니다 — 지정이 이긴다
            year = None
    if kind is None and stage is None and year is None and not why:
        return None
    out = {"org": org, "orgKind": kind, "stage": stage, "year": year, "src": {d: src[d] for d in DIMS if d in src}, "ev": {d: ev[d] for d in DIMS if d in ev}}
    if why:
        out["why"] = why
    return out


def _vals(lab):
    return lab["orgKind"], lab["org"], lab["stage"], lab["year"]


def _cell_final(c, t, stages):
    """칸의 최종 라벨 — 칸의 자동 라벨(c)에 값이 있는 기준은 칸의 것(안쪽이 이긴다), 없는 기준은 그 표의 최종 라벨(t)에서 물려받는다.
    칸의 기관을 스크립트가 못 정했는데(확인 필요 · 모름) 그 표의 기관을 **지정**(사람 · LLM)이 정했으면 칸도 그 기관이다 — 표를 지정했는데 칸에는 「확인 필요」 가 남지 않게(② §3·§8).
    근거가 엇갈려 비운 차년도·단계(why.year · why.stage)는 「값 없음」 이 아니다 — 표의 **자동** 값을 물려받아 되살리지 않는다(표의 그 값을 지정이 정했을 때만 그 값이 되고 엇갈린 근거를 내린다)."""
    if t is None:
        return c
    take, cw, by = [], c.get("why") or {}, t.get("src") or {}
    settled = c["orgKind"] in ("conflict", "unknown") and t["orgKind"] == "org" and by.get("org") == "mark"
    if (c["orgKind"] is None and t["orgKind"] is not None) or settled:
        take.append("org")
    free = lambda d: d not in cw or by.get(d) == "mark"  # noqa: E731 — 그 기준을 표에서 물려받아도 되나
    if c["year"] is None:
        if c["stage"] is None:
            take += [d for d in ("stage", "year") if t[d] is not None and free(d)]
        elif t["year"] is not None and free("year") and (not stages or _stage_of(stages, t["year"]) == c["stage"]):
            take.append("year")   # 칸이 제 단계를 말하면 그 단계의 차년도만 물려받는다
    if not take:
        return c
    out = {**c, "src": dict(c["src"]), "ev": dict(c.get("ev") or {})}
    why = dict(c.get("why") or {})
    for d in take:
        out[d] = t[d]
        why.pop(d, None)   # 지정이 정한 차년도·단계 — 엇갈린 근거는 더 싣지 않는다
        if d == "org":
            out["orgKind"] = t["orgKind"]
            if settled:   # 지정이 정했다 — 스크립트의 엇갈린 근거는 더 싣지 않는다
                why = {k: v for k, v in why.items() if k not in WHY_ORG}
                out["ev"].pop("org", None)
            why.update({k: v for k, v in (t.get("why") or {}).items() if k in WHY_ORG})
        for k in ("src", "ev"):
            if d in (t.get(k) or {}):
                out[k][d] = t[k][d]
    out.pop("why", None)
    if why:
        out["why"] = why
    return out


def _band_key(lab, dims):
    """켠 기준만 본 값 — 모두 비었으면 None(띠가 아니고 띠를 끊는다). 기관 모름·확인 필요는 값이 없어도 띠다(orgKind 가 열쇠에 든다 — 공통과 한 띠가 안 된다)."""
    k = []
    if "org" in dims:
        k += [lab["orgKind"], lab["org"]]
    if "stage" in dims:
        k.append(lab["stage"])
    if "year" in dims:
        k.append(lab["year"])
    return tuple(k) if any(x is not None for x in k) else None


def build(info, marks, origins, dims):
    """지정·출처를 입힌 보기(② §5) → {"blocks"{블록 id: 라벨 — 값이 있거나 엇갈린 근거(why)가 남은 것}, "cells"{표 id: {칸 id: 라벨 — 값이나 엇갈린 근거가 표의 라벨과 다른 칸만}}, "zones"[띠], "marks", "origins", "counts", "_tableOf", "_info"}.
    합치는 차례(블록마다 · 기준마다): 지정에 그 기준 키가 있고 유효하면 지정 → 자동 → (기관만) 출처(옛 기록 legacy 는 목록에만 싣고 기관을 채우지 않는다). 띠 = 켠 기준(dims)만 본 값이 같은 이웃 최상위 블록 — 지정에서 온 블록과 자동 블록은 한 띠로 묶지 않는다.
    띠의 label 은 켠 기준의 값만 지닌다(안 켠 기준은 None — 띠 안 블록마다 다를 수 있다: 블록의 온전한 라벨은 blocks · `label_of`).
    counts: zones = 띠 수 · blocks = 라벨이 있는 최상위 블록 수 · cells = cells 에 실린 칸 수 · marks = 지정 수 · origins = 남은 id 가 있는 출처 이벤트 수 · conflicts·unknown = orgKind 가 그것인 최상위 블록 수."""
    info = info or {}
    dims = [d for d in DIMS if d in (dims or ())]
    order, auto, cells_of = info.get("order") or [], info.get("auto") or {}, info.get("cellsOf") or {}
    stages = list(info.get("stages") or ())
    keys, known = {o["key"] for o in info.get("orgs") or () if o.get("key")}, bool(stages)
    derived = info.get("_derived") or {}
    table_of = info.get("_tableOf")
    if table_of is None:
        table_of = {c: t for t, cs in cells_of.items() for c in cs}
    top = set(order)
    alive = top | set(table_of) | set(info.get("_caps") or ())
    mark_of, m_view = {}, []   # mark_of = 블록 id → (지정 id, 쓸 값 — 유효한 키만)
    for m in marks or ():
        if not isinstance(m, dict):
            continue
        ids = [i for i in m.get("ids") or () if isinstance(i, str)]
        left = [i for i in ids if i in top]
        label = m.get("label") if isinstance(m.get("label"), dict) else {}
        bad = _invalid(label, keys, stages, known)
        use = {d: label[d] for d in DIMS if d in label and d not in bad}
        for i in left:
            mark_of[i] = (m.get("id"), use)
        m_view.append({"id": m.get("id"), "ids": left, "gone": len(ids) - len(left), "label": dict(label), "note": m.get("note") or "", "by": m.get("by") or "user", "at": m.get("at"), "invalid": bad})
    covers, o_view = {}, []   # covers = 블록 id → [(legacy 인가, 그 이벤트의 기관들)]
    for e in origins or ():
        if not isinstance(e, dict):
            continue
        ids = [i for i in e.get("ids") or () if isinstance(i, str)]
        left = [i for i in ids if i in alive]
        orgs = [o for o in e.get("orgs") or () if isinstance(o, str)]
        row = {"id": e.get("id"), "part": e.get("part"), "name": e.get("name"), "orgs": orgs, "kind": e.get("kind"), "at": e.get("at"), "ids": left, "gone": len(ids) - len(left)}
        if e.get("legacy"):
            row["legacy"] = True
        o_view.append(row)
        for i in left:
            if i in top:
                covers.setdefault(i, []).append((bool(e.get("legacy")), orgs))
    blocks = {}
    for bid in order:
        mk = mark_of.get(bid)
        lab = _final(auto.get(bid), mk[1] if mk else None, covers.get(bid), keys, stages, known, bid in derived)
        if lab is not None:
            blocks[bid] = lab
    cells = {}
    for tid, cids in cells_of.items():
        t, row = blocks.get(tid), {}
        for cid in cids:
            c = auto.get(cid)
            if c is None:
                continue   # 칸에 제 값이 없다 — 표의 라벨 그대로
            lab = _cell_final(c, t, stages)
            if t is None or _vals(lab) != _vals(t) or (lab.get("why") or None) != (t.get("why") or None):   # 값이 같아도 엇갈린 근거가 남은 칸은 싣는다
                row[cid] = lab
        if row:
            cells[tid] = row
    zones, cur, cur_k = [], None, None
    paths, texts = info.get("path") or {}, info.get("text") or {}
    for bid in order if dims else ():
        lab = blocks.get(bid)
        k = _band_key(lab, dims) if lab is not None else None
        if k is None:
            cur = cur_k = None   # 켠 기준의 값이 없는 블록 — 띠를 끊는다
            continue
        mk = mark_of.get(bid)
        mid = mk[0] if mk and any(lab["src"].get(d) == "mark" for d in dims) else None   # 켠 기준의 값이 지정에서 왔다
        if cur is None or cur_k != (k, mid):
            label = {"org": lab["org"] if "org" in dims else None, "orgKind": lab["orgKind"] if "org" in dims else None, "stage": lab["stage"] if "stage" in dims else None,
                     "year": lab["year"] if "year" in dims else None, "src": {d: lab["src"][d] for d in dims if d in lab["src"]}, "ev": {d: lab["ev"][d] for d in dims if d in (lab.get("ev") or {})}}
            cur, cur_k = {"ids": [], "label": label, "text": label_text(label, info, dims), "path": list(paths.get(bid) or ()), "first": "", "mark": mid}, (k, mid)
            zones.append(cur)
        cur["ids"].append(bid)
        if not cur["first"]:
            cur["first"] = texts.get(bid) or ""
    counts = {"zones": len(zones), "blocks": len(blocks), "cells": sum(len(v) for v in cells.values()), "marks": len(m_view), "origins": sum(1 for o in o_view if o["ids"]),
              "conflicts": sum(1 for x in blocks.values() if x["orgKind"] == "conflict"), "unknown": sum(1 for x in blocks.values() if x["orgKind"] == "unknown")}
    return {"blocks": blocks, "cells": cells, "zones": zones, "marks": m_view, "origins": o_view, "counts": counts, "_tableOf": table_of, "_info": info}


def label_of(view, target_id):
    """블록·칸 id 의 **온전한 라벨**(옵션과 무관 — ② §5) | None. 블록 id → 그 라벨 · 칸 id → 칸의 라벨, 없으면 그 표의 라벨."""
    view = view or {}
    blocks = view.get("blocks") or {}
    if target_id in blocks:
        return blocks[target_id]
    cells = view.get("cells") or {}
    tid = (view.get("_tableOf") or {}).get(target_id)
    if tid is None:   # 밑줄 키를 뺀 보기(끝점의 응답) — 실린 칸에서 찾는다
        return next((row[target_id] for row in cells.values() if target_id in row), None)
    return (cells.get(tid) or {}).get(target_id) or blocks.get(tid)


def label_text(label, info_or_view, dims=None):
    """이름표 글 「한국선급 · 1단계 2차년도」 — dims 를 주면 그 기준만. 기관 = 그 이름(없으면 열쇠 글) · 기관 모름 · 기관 확인 필요, 차년도 = 단계가 둘 이상이면 「N단계 M차년도」(M = 단계 안 차년도)·하나면 「M차년도」,
    단계만 = 「N단계」. 사이는 「 · 」, 값이 없으면 빈 글."""
    if not isinstance(label, dict):
        return ""
    x = info_or_view or {}
    x = x["_info"] if isinstance(x.get("_info"), dict) else x
    show = DIMS if dims is None else dims
    stages, out = list(x.get("stages") or ()), []
    if "org" in show:
        kind = label.get("orgKind")
        if kind == "org":
            key = label.get("org")
            out.append(next((o.get("name") for o in x.get("orgs") or () if o.get("key") == key and o.get("name")), None) or str(key or ""))
        elif kind in ORG_TEXT:
            out.append(ORG_TEXT[kind])
    year, stage = label.get("year") if "year" in show else None, label.get("stage") if "stage" in show else None
    if year is not None:
        s = _stage_of(stages, year)
        if s is None:   # 프로젝트 구성 값이 없거나 범위 밖 — 적힌 번호 그대로
            out.append(f"{year}차년도")
        else:
            m = year - sum(stages[:s - 1])
            out.append(f"{s}단계 {m}차년도" if len(stages) > 1 else f"{m}차년도")
    elif stage is not None:
        out.append(f"{stage}단계")
    return " · ".join(t for t in out if t)

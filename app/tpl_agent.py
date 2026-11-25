"""템플릿 서식 정리 에이전트(spec_hwpx_웹편집 ② §8-4) — 사용자 2026-11-15 "에이전트 기능을 추가 해서 opus5.5 가 템플릿의 서식을 직접 조정해주는 기능을 추가해줘 …
이 에이전트에게 정리를 시킬때 프롬프트/스킬을 먼저 저장하고, 사용자가 이를 수정할 수 있는 형식으로".

- **스킬** = 에이전트가 따를 정리 기준 글. 기본본 `app/tpl_agent_default/<키>.md`(읽기만 — 첫 「# 」 줄 = 이름, HTML 주석은 사람만 봄) + 사용자 사본·새 스킬
  `<헤딩 저장소>/tpl_agent/<키>.md`(몸 글) · 메타 `<키>.json` {name, version, updated, base}. 저장 끔(NFM_HEADINGS=off)이면 메모리.
  정리는 **저장된 스킬 글**로만 돈다(화면이 고친 글을 먼저 저장하고 부른다) — 실행 기록에 스킬 키·판·sha1 이 남는다.
- **자료**(`material`) = 템플릿의 레벨마다 서식 갈래(`outline_match.variants` — 스크립트가 뽑은 값) · 갈래 id 「g1…」(대표 갈래 먼저).
- **LLM**(Opus 5.5 — `MODEL`, env `NFM_LLM_MODEL_FORCE` 보다 먼저: `llm.call(pin=True)`)은 갈래 id 가운데 **고르기만** 한다 — 레벨마다 대표로 삼을 갈래 · 대표에 맞출 갈래 ·
  그대로 둘 갈래와 까닭. 서식 값을 만들지 않는다(대표 갈래의 값이 곧 맞출 값).
- **계획**(`check_plan`) = 답을 자료와 견줘 걸러낸 것(없는 id 는 버리고 notes 에 · 말하지 않은 갈래는 「그대로」). 적용은 `POST …/outline/templates/{tpl}/match`
  (outline_match_api — 트랜잭션 하나 · 실행 취소 1)."""
import hashlib
import json
import os
import re
import threading
import time
import uuid
from collections import Counter
from pathlib import Path

from app import prompt_texts
from app import agent_settings
from app import heading_rules as R
from app import llm
from app import outline_edit as OE
from app import outline_match as M

MODEL = "claude-opus-5-5"   # 사용자가 이 에이전트의 모델을 정했다(2026-11-15) — env NFM_TPL_AGENT_MODEL 로만 바꾼다(NFM_LLM_MODEL_FORCE 는 이 호출에 안 걸린다)
EFFORT = "medium"
TIMEOUT = 300.0
DEFAULT_DIR = Path(__file__).with_name("tpl_agent_default")
FIRST = "tidy"            # 목록의 맨 앞 = 화면이 처음 고르는 스킬
KEY = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
TEXT_MAX, NAME_MAX, REQUEST_MAX, USER_MAX = 20_000, 60, 2_000, 40
GROUP_MAX = 40          # 레벨 하나에서 LLM 에 보내는 갈래 수(줄 수 많은 것부터 — 넘는 갈래는 「그대로」)
SAMPLE_MAX = 60
_COMMENT = re.compile(r"<!--.*?-->[ \t]*\n?", re.S)
_TITLE = re.compile(r"\A\s*#[ \t]+([^\n]*)\n?")
_LOCK = threading.RLock()
_MEMORY = {}  # 저장 끔일 때 {키: (글 | None, 메타)}


def model():
    m = os.environ.get("NFM_TPL_AGENT_MODEL", "").strip()
    return m if m and llm._MODEL_RE.fullmatch(m) else MODEL


def effort():
    e = os.environ.get("NFM_TPL_AGENT_EFFORT", "").strip().lower()
    return e if e in llm.EFFORTS else EFFORT


def status():
    """화면용 {model, effort, backend, available} — 이 에이전트가 부를 모델과 지금 LLM 길. 「에이전트 설정」 에서 이 에이전트에 정한 모델·생각 깊이가 있으면 그것(llm.call 과 같은 차례)."""
    st = llm.status()
    ov = agent_settings.override("tpl-agent")
    return {"model": ov.get("model") or model(), "effort": ov.get("effort") or effort(), "backend": st.get("active"), "available": bool(st.get("available"))}


# ---------------------------------------------------------------- 스킬(저장한 정리 기준 글)
def _sha1(text):
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def _dir():
    d = R.store_dir()
    return d / "tpl_agent" if d is not None else None


def _builtin():
    """기본본 {키: (이름, 몸 글)} — 파일 이름 차례."""
    out = {}
    if DEFAULT_DIR.is_dir():
        for p in sorted(DEFAULT_DIR.glob("*.md")):
            if not KEY.fullmatch(p.stem):
                continue
            raw = _COMMENT.sub("", p.read_text(encoding="utf-8"))
            m = _TITLE.match(raw)
            out[p.stem] = ((m.group(1).strip() if m else "") or p.stem, re.sub(r"\n{3,}", "\n\n", _TITLE.sub("", raw, count=1)).strip() + "\n")
    return out


def _saved(key):
    """(사용자 글 | None, 메타 | None)."""
    d = _dir()
    if d is None:
        return _MEMORY.get(key, (None, None))
    p, m = d / f"{key}.md", d / f"{key}.json"
    try:
        meta = json.loads(m.read_text(encoding="utf-8")) if m.is_file() else None
    except (OSError, ValueError):
        meta = {}
    if meta is not None and not isinstance(meta, dict):
        meta = {}
    try:
        text = p.read_text(encoding="utf-8") if p.is_file() else None
    except (OSError, UnicodeDecodeError):
        text = None
    return text, meta


def _put(key, text, meta):
    d = _dir()
    if d is None:
        _MEMORY[key] = (text, meta)
        return
    d.mkdir(parents=True, exist_ok=True)
    R._write_json(d / f"{key}.json", meta)
    if text is None:
        (d / f"{key}.md").unlink(missing_ok=True)
    else:
        tmp = d / f"{key}.md.tmp"
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(d / f"{key}.md")


def _user_keys():
    d = _dir()
    if d is None:
        return sorted(k for k, (t, _) in _MEMORY.items() if t is not None)
    return sorted(p.stem for p in d.glob("*.md") if KEY.fullmatch(p.stem)) if d.is_dir() else []


def skill(key):
    """{key, name, text(지금 쓰는 글), builtin, custom(사용자가 고친 사본·만든 스킬), version, updated, sha1, defaultChanged} — 없으면 KeyError."""
    if not isinstance(key, str) or not KEY.fullmatch(key):
        raise KeyError(key)
    with _LOCK:
        base = _builtin().get(key)
        text, meta = _saved(key)
    if base is None and text is None:
        raise KeyError(key)
    meta = meta or {}
    custom = text is not None
    cur = text if custom else base[1]
    return {"key": key, "name": (meta.get("name") if custom else None) or (base[0] if base else key), "text": cur, "builtin": base is not None, "custom": custom,
            "version": int(meta.get("version", 0)), "updated": meta.get("updated"), "sha1": _sha1(cur),
            "defaultChanged": bool(custom and base and meta.get("base") and meta["base"] != _sha1(base[1]))}


def skills():
    """목록(글 없이) — 기본본 먼저, 그다음 사용자가 만든 것(만든 차례)."""
    with _LOCK:
        keys = list(_builtin()) + [k for k in _user_keys() if k not in _builtin()]
        out = [{k: v for k, v in skill(key).items() if k != "text"} for key in keys]
    head = sorted((s for s in out if s["builtin"]), key=lambda s: s["key"] != FIRST)  # 기본 스킬 「템플릿 서식 정리」 가 맨 앞(나머지는 파일 이름 차례)
    return head + sorted((s for s in out if not s["builtin"]), key=lambda s: s.get("updated") or 0)


def save(key, name, text, expect=None):
    """스킬 저장 → skill(). key=None 이면 새 스킬(키를 새로 만든다). expect = 기대 version(다르면 R.StaleVersion). 잘못된 값은 ValueError · 없는 키는 KeyError."""
    if not isinstance(text, str) or not text.strip() or len(text) > TEXT_MAX:
        raise ValueError(f"스킬 글은 비어 있지 않은 {TEXT_MAX:,}자 이하의 글이어야 합니다")
    name = re.sub(r"\s+", " ", name).strip() if isinstance(name, str) else ""
    if not name or len(name) > NAME_MAX:
        raise ValueError(f"스킬 이름은 1~{NAME_MAX}자")
    expect = R.expect_version(expect)
    with _LOCK:
        base = _builtin()
        if key is None:
            if len([k for k in _user_keys() if k not in base]) >= USER_MAX:
                raise ValueError(f"만든 스킬은 {USER_MAX}개까지입니다 — 안 쓰는 것을 지운 뒤 만드세요")
            key = "u" + uuid.uuid4().hex[:8]
            meta = {}
        else:
            if not isinstance(key, str) or not KEY.fullmatch(key):
                raise KeyError(key)
            old, meta = _saved(key)
            if key not in base and old is None:
                raise KeyError(key)
            meta = meta or {}
        if expect is not None and expect != int(meta.get("version", 0)):
            raise R.StaleVersion(f"스킬이 그 사이에 바뀌었습니다(지금 판 {meta.get('version', 0)} · 요청 {expect}) — 다시 읽어 주세요")
        new = {"name": name, "version": int(meta.get("version", 0)) + 1, "updated": round(time.time(), 3)}
        if key in base:
            new["base"] = meta.get("base") or _sha1(base[key][1])
        _put(key, text, new)
        R.append_history({"kind": "tplAgentSkill", "name": key, "action": "save", "version": new["version"], "sha1": _sha1(text)})
    return skill(key)


def remove(key):
    """사용자가 만든 스킬은 지우고({deleted: true}), 기본 스킬의 사본은 버려 기본본으로 되돌린다(skill()). 메타의 version 은 올려 남긴다(옛 판을 든 저장이 409)."""
    if not isinstance(key, str) or not KEY.fullmatch(key):
        raise KeyError(key)
    with _LOCK:
        base = _builtin()
        old, meta = _saved(key)
        if key not in base and old is None:
            raise KeyError(key)
        if old is not None:
            _put(key, None, {"version": int((meta or {}).get("version", 0)) + 1, "updated": round(time.time(), 3)})
            R.append_history({"kind": "tplAgentSkill", "name": key, "action": "reset" if key in base else "delete"})
    return skill(key) if key in base else {"deleted": True, "key": key}


# ---------------------------------------------------------------- 자료 · 프롬프트 · 계획
KIND = {"main": "주 사슬", "branch": "가지 템플릿", "label": "구분 라벨 템플릿", "sub": "서브 템플릿", "cell": "표 칸", "band": "별첨·부록 표 제목 템플릿"}
RULE = {"text": "둘째 줄을 글 시작에 맞춤", "letter": "둘째 줄을 레터에 맞춤", "front": "둘째 줄을 앞 여백에 맞춤", "mm": "둘째 줄 직접", "keep": "문단 서식 그대로"}


def _sample(doc, pid):
    try:
        t = re.sub(r"\s+", " ", doc._text(doc._ids[pid])).strip()
    except Exception:  # noqa: BLE001 — 견본 글 하나가 자료를 막지 않게
        t = ""
    return t if len(t) <= SAMPLE_MAX else t[:SAMPLE_MAX] + "…"


def fingerprint(ov, tid, lvs):
    """템플릿 tid 의 **적용 안전 지문**(spec_hwpx_웹편집 ② §8-4 「계획은 줄 지문에」 — 2026-11-16): 서식 정리 계획을 문서 차례(rev)가 아니라 이것에 묶는다 — 문서의 다른 곳을 고쳐도,
    반영을 되돌려 처음 상태로 돌아와도 지문이 같으면 그 계획을 그대로 쓴다(전에는 글자 하나만 고쳐도 · 되돌려도 유료로 다시 받았다).
    계획의 반영(check_plan → todo → outline_match_api.apply_templates · split)이 기대는 것을 다 넣는다: 템플릿의 꼴(사슬 · base · 종속/변형) · 레벨마다 대표 · 사람이 정한 대표 · 자리 규칙 · 뗀 글자 ·
    **대표 줄이 지닌 모양 참조**(맞추면 복사되는 것) · **줄 구성**(줄 id → 갈래 — 값 칸 포함: variants 의 sig) · 줄마다 레벨 · 부모 줄 · 부모의 (템플릿, 레벨) · 이 템플릿에 매달린 가지.
    줄의 본문 글 · 스킬 · 요청은 넣지 않는다(적용의 안전과 무관 — 판단을 새로 받고 싶으면 「다시 받기」). lvs = {레벨: outline_match.variants(…)} — 그 템플릿의 줄 있는 레벨."""
    tid = str(tid)
    t = (ov.get("templates") or {}).get(tid)
    if t is None:
        return ""
    lines = ov["lines"]
    rows = []
    for pid, x in lines.items():
        if x["tpl"] != tid:
            continue
        par = lines.get(x.get("parent")) if x.get("parent") else None
        rows.append([pid, int(x["level"]), x.get("parent") or "", par["tpl"] if par else "", int(par["level"]) if par else 0])
    rows.sort()
    slots = {}
    for lv in sorted(t.get("slots", {}), key=int):
        sl, v = t["slots"][lv], (lvs or {}).get(lv) or (lvs or {}).get(str(lv)) or {}
        slots[str(lv)] = [sl.get("rep"), bool(sl.get("repSet")), sl.get("pos"), bool(sl.get("table")), sorted(M.used_sfx(ov, tid, lv)), v.get("sig"), v.get("repIds")]
    branches = {k: v for k, v in (ov.get("branches") or {}).items() if str(k).split("|")[0] == tid}
    body = [tid, t.get("no"), t.get("chain"), t.get("kind"), M._base(t), t.get("composite"), t.get("variant"), slots, rows, branches]
    return hashlib.sha1(json.dumps(body, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def fingerprint_of(doc, ov, tid):
    """문서에서 바로 — 그 템플릿의 레벨마다 서식 갈래를 셈해 지문을(세션 잠금 안에서 부른다)."""
    t = (ov.get("templates") or {}).get(str(tid)) or {}
    order = M._order(doc)
    lvs = {lv: M.variants(doc, ov, tid, lv, order) for lv, sl in t.get("slots", {}).items() if M.slot_ids(ov, tid, lv) and not sl.get("table")}
    return fingerprint(ov, tid, lvs)


def group_sig(level, raw):
    """갈래의 지문 — 레벨 + 비교 값(KEYS). 앞 계획의 검토·보낸 이력을 **같은 갈래**에만 잇는 데 쓴다(열쇠 줄이 같아도 서식이 바뀌어 다른 갈래가 됐으면 잇지 않는다)."""
    # 표 안의 줄은 표 양식도(② §8-11 「갈래는 표 양식마다」 — 서식이 같아도 표 양식이 다르면 다른 갈래다) · 표 밖 갈래의 지문은 전과 같다
    return hashlib.sha1(repr([int(level)] + [M.cval(raw, k) for k in M.KEYS] + ([raw["form"]] if raw.get("form") else [])
                             + ([f"자동:{raw['auto']}"] if raw.get("auto") else [])).encode("utf-8")).hexdigest()[:12]  # 자동 글머리 줄(② §8-8)도 따로 — 친 레터 갈래의 지문은 전과 같다


def _known(records, paras, sig):
    """이력 records([{para, sig}])에 이 갈래(구성원 paras · 지문 sig)가 있나 — 열쇠 줄이 지금도 이 갈래의 줄이고 지문이 같을 때만."""
    members = set(paras)
    return any(isinstance(r, dict) and r.get("sig") == sig and r.get("para") in members for r in records or ())


def material(doc, ov, tid, reviewed=None, sent=None):
    """템플릿 tid 의 정리 자료 → {tpl, no, chain, kind, comp?, lines, levels[{level, letter, lines, rule, groups[{id, para, count, rep, sample, raw, look, seen}], more, held[…]}]}.
    갈래 id = 「g1…」(대표 갈래 먼저 → 아직 안 본 갈래(줄 수 순) → 앞 계획이 검토해 그대로 둔 갈래). 없는 템플릿은 KeyError.
    sent = 앞 계획(들)이 에이전트에 **보낸** 갈래 · reviewed = 그 가운데 에이전트가 **답해서 그대로 둔** 갈래 — [{para(열쇠 줄), sig(group_sig)}](계획의 `sent`·`reviewed` — spec_hwpx_웹편집 ② §8-4 「계획 검사」 ⓑ).
    갈래가 GROUP_MAX 를 넘는 레벨에서 보낸 적 있는 갈래를 뒤로 돌려 못 본 갈래가 에이전트에 닿게 한다(전에는 줄 수 많은 앞 40갈래만 되풀이해 보냈다). 이력은 **지문이 같은 갈래**에만 잇는다.
    못 보낸 갈래: 검토해 그대로 둔 것 = held(계획에 「그대로」 로 이어받음) · 보냈지만 답이 없던 것 = heldAuto(답 없음 그대로) · 한 번도 못 보낸 것 = more."""
    tid = str(tid)
    t = ov["templates"].get(tid)
    if t is None:
        raise KeyError(f"템플릿 {tid} 가 없습니다")
    order = M._order(doc)
    comp = t.get("composite")
    out = {"tpl": tid, "no": str(t.get("no")), "chain": list(t.get("chain") or []), "kind": t.get("kind"), "levels": [],
           "lines": sum(1 for x in ov["lines"].values() if x["tpl"] == tid)}
    if comp:
        tp = ov["templates"]
        out["comp"] = {"parentNo": str(tp.get(comp["parent"], {}).get("no")), "childNo": str(tp.get(comp["child"], {}).get("no")), "at": comp["at"]}
    var = t.get("variant")
    if var:  # 서식 종속 템플릿(② §8-5) — 「T1L3a」 = T1 의 L3 에서 뗀 것
        out["vari"] = {"ofNo": str(ov["templates"].get(var["of"], {}).get("no")), "level": int(var["level"])}
    for lv in sorted(t.get("slots", {}), key=int):
        if not M.slot_ids(ov, tid, lv) or t["slots"][lv].get("table"):  # 표 제목 레벨(spec_hwpx_웹편집 ② §8-7)은 서식 정리 대상이 아니다
            continue
        v = M.variants(doc, ov, tid, lv, order, full=True)
        if not v["total"]:  # 값 칸뿐인 레벨(표 칸에 혼자 있는 레터 — outline_match.lone_value) — 정리할 줄이 없다
            continue
        sl = t["slots"][lv]
        pos = sl.get("pos") or {}
        # noSplit = 이 갈래를 다른 템플릿으로 못 떼는 까닭(번호형 레벨에서 같은 부모 아래 형제의 일부 — ② §8-5) | None. 「대표 갈래라서」 는 여기서 안 본다(계획이 대표를 바꿀 수 있다 — rep="-")
        tagged = []
        for g in v["groups"]:
            sig = group_sig(lv, g["raw"])
            tagged.append((g, sig, (not g["rep"]) and _known(sent, g["paras"], sig), (not g["rep"]) and _known(reviewed, g["paras"], sig)))
        tagged.sort(key=lambda x: x[2] or x[3])  # 대표 · 보낸 적 없는 갈래 먼저(차례는 그대로) → 보낸 적 있는 갈래
        # units = 번호형 레벨의 「함께 옮겨야 하는 형제 묶음」 마다 이 갈래의 줄 수(표 안의 줄은 같은 표의 형제끼리 — outline_match.split_units) · hard = 형제의 일부라서가 아닌 까닭으로 못 뗀다.
        # 갈래 하나로는 형제의 일부여도(noSplit) 같은 묶음의 갈래를 한 split 항목에 함께 넣으면 뗄 수 있다 — check_plan 이 항목의 줄을 합쳐서 본다(② §8-11 「번호형 레벨의 떼기」)
        units = M.split_units(ov, tid, lv, doc)
        ukey = (lambda p: repr(units[p])) if units is not None else None
        groups = [{"id": f"g{i + 1}", "para": g["key"], "count": g["count"], "rep": bool(g["rep"]), "sample": _sample(doc, g["key"]), "raw": g["raw"], "look": g["look"],
                   "noSplit": M.split_block(ov, tid, lv, g["paras"], rep="-", doc=doc), "hard": bool(M.split_block(ov, tid, lv, g["paras"], rep="-", doc=doc, partial=False)),
                   "units": dict(Counter(ukey(p) for p in g["paras"] if p in units)) if units is not None else None,
                   "form": g.get("form"), "own": bool(g.get("own")),  # 표 안의 줄 — 표 양식{label, tables, around} · 표의 서식인가(② §8-11)
                   "cannotBeRep": bool(g["raw"].get("auto")),  # 자동 글머리 줄(② §8-8) — 레터가 글에 없어 대표가 못 된다(맞추면 친 레터가 된다)
                   "sig": sig, "seen": was_kept, "sentBefore": was_sent or was_kept}
                  for i, (g, sig, was_sent, was_kept) in enumerate(tagged)]
        rest = groups[GROUP_MAX:]
        out["levels"].append({"level": int(lv), "letter": sl.get("letter") or "", "lines": v["total"], "repMissing": bool(v["repMissing"]), "repSet": bool(sl.get("repSet")),
                              "rule": RULE.get(pos.get("line2"), "") if pos.get("set") else "", "groups": groups[:GROUP_MAX],
                              "more": sum(1 for g in rest if not g["sentBefore"]),            # 한 번도 못 보낸 갈래 수(계획의 omitted)
                              "held": [g for g in rest if g["seen"]],                           # 못 보냈지만 앞 계획이 검토해 그대로 둔 갈래 — 계획에 「그대로」 로 싣는다
                              "heldAuto": [g for g in rest if g["sentBefore"] and not g["seen"]],  # 못 보냈고, 앞서 보냈지만 답이 없던 갈래 — 답 없음 그대로(못 본 것이 아니다)
                              "taken": sorted(M.used_sfx(ov, tid, lv)),  # 이 레벨에서 이미 뗀 템플릿의 글자(「T1L3a」 의 a)
                              "unitSizes": dict(Counter(repr(u) for u in units.values())) if units is not None else None,  # 번호형 레벨 — 형제 묶음마다 줄 수(값 칸 포함: 갈래의 units 와 견줘 「통째인가」 를 본다)
                              "values": v.get("values", 0)})  # 값 칸 줄 수 — 갈래에 없다(에이전트에 안 보내고 안 맞춘다)
    return out


def _values(look):
    return {M.LABELS.get(k, k): M.cval(look, k) for k in M.KEYS}  # 「2번째 줄」 은 둘째 줄이 글 시작에 있으면 「글 시작」(값이 아니라 규칙 — outline_match.cval)


def _units_short(lv, groups):
    """번호형 레벨에서 갈래들(groups)의 줄을 합쳐도 **형제 묶음이 통째가 아닌가** → 까닭 글 | None(통째다 · 번호형이 아니다). 묶음 = 같은 부모 아래 형제 — 표 안의 줄은 같은 표의 형제끼리."""
    sizes = lv.get("unitSizes")
    if not sizes:
        return None
    total = Counter()
    for g in groups:
        total.update(g.get("units") or {})
    for u, k in total.items():
        if 0 < k < sizes.get(u, k):
            return f"번호형 레벨은 같은 부모 · 같은 표의 형제 줄을 함께 옮겨야 합니다(형제 {sizes[u]}줄 가운데 {k}줄)"
    return None


def split_mates(lv):
    """번호형 레벨에서 **혼자는 못 떼는 갈래**(형제의 일부 — noSplit 이고 hard 가 아님)마다 「함께 옮기면 뗄 수 있는 갈래들」 → {갈래 id: [함께 넣을 갈래 id] | None(함께 넣어도 못 뗀다)}.
    같은 형제 묶음(units)을 나눠 가진 갈래끼리 한 무리 — 그 무리에 대표 갈래나 다른 까닭으로 못 떼는 갈래가 있거나, 무리의 줄을 다 모아도 묶음이 통째가 아니면(보내지 않은 갈래 · 값 칸) None."""
    gs = lv["groups"]
    if not lv.get("unitSizes"):
        return {}
    root = {g["id"]: g["id"] for g in gs}

    def find(a):
        while root[a] != a:
            root[a] = root[root[a]]
            a = root[a]
        return a
    owner = {}
    for g in gs:
        for u in g.get("units") or {}:
            if u in owner:
                root[find(g["id"])] = find(owner[u])
            else:
                owner[u] = g["id"]
    comps = {}
    for g in gs:
        comps.setdefault(find(g["id"]), []).append(g)
    out = {}
    for members in comps.values():
        ok = not any(m["rep"] or m.get("hard") for m in members) and _units_short(lv, members) is None
        for g in members:
            if g.get("noSplit") and not g.get("hard"):
                out[g["id"]] = [m["id"] for m in members if m is not g] if ok else None
    return out


def prompt_material(mat):
    """LLM 에 보낼 자료 — 대표 갈래(없으면 모든 갈래)는 값 전부, 나머지는 대표와 다른 값만 [이름, 대표, 이 갈래]."""
    out = {"template": {"no": f"T{mat['no']}", "chain": " › ".join(mat["chain"]), "kind": KIND.get(mat["kind"], mat["kind"] or ""), "lines": mat["lines"]}, "levels": []}
    if mat.get("comp"):
        c = mat["comp"]
        out["template"]["subordinate"] = f"T{c['parentNo']} L{c['at']} 아래 T{c['childNo']}(종속 템플릿 — 이 템플릿의 줄은 L{c['at'] + 1} 부터)"
    if mat.get("vari"):
        c = mat["vari"]
        out["template"]["subordinate"] = f"T{c['ofNo']} L{c['level']} 에서 서식이 달라 뗀 서식 종속 템플릿 — 이 템플릿의 줄은 L{c['level']} 부터"
    for lv in mat["levels"]:
        rep = next((g for g in lv["groups"] if g["rep"]), None)
        gs = []
        mates = split_mates(lv)
        for g in lv["groups"]:
            item = {"id": g["id"], "lines": g["count"], "sample": g["sample"]}
            if g.get("noSplit"):
                tog = None if g.get("hard") else mates.get(g["id"])
                if tog:
                    item["splitTogether"] = tog  # 혼자는 형제의 일부라 못 떼지만 이 갈래들과 한 split 항목에 함께 넣으면 뗄 수 있다(② §8-11 「번호형 레벨의 떼기」)
                else:
                    item["cannotSplit"] = True
            f = g.get("form")
            if f:  # 표 안의 줄(② §8-11) — 그 표의 머리글 · 표 수 · 주변 글(그 표의 다른 글의 글자 모양) · 표의 서식인가(그 표 양식에 대표 서식의 줄이 없다)
                item["table"] = {"header": f["label"], "tables": f["tables"], **({"textAround": f["around"]} if f.get("around") else {}), **({"ownFormat": True} if g.get("own") else {})}
            if g["rep"]:
                item["currentRep"] = True
            if g.get("cannotBeRep"):
                item["cannotBeRep"] = True
            if rep is None or g["rep"]:
                item["values"] = _values(g["look"])
            else:
                item["differsFromRep"] = [[d[1], d[2], d[3]] for d in M.diff(rep["raw"], g["raw"])]
            gs.append(item)
        row = {"level": lv["level"], "letter": lv["letter"], "lines": lv["lines"], "groups": gs}
        if lv.get("repSet") and rep is not None:
            row["repChosenByUser"] = True
        if lv["rule"]:
            row["positionRule"] = lv["rule"]
        if lv["more"]:
            row["omittedGroups"] = lv["more"]
        out["levels"].append(row)
    return out


SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "levels"],
    "properties": {
        "summary": {"type": "string"},
        "levels": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["level", "rep", "match", "keep", "split", "why"],
            "properties": {
                "level": {"type": "integer"}, "rep": {"type": "string"}, "match": {"type": "array", "items": {"type": "string"}},
                "keep": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["group", "why"],
                                                    "properties": {"group": {"type": "string"}, "why": {"type": "string"}}}},
                "split": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["rep", "match", "why"],  # 다른 템플릿으로 뗄 갈래(② §8-5)
                                                     "properties": {"rep": {"type": "string"}, "match": {"type": "array", "items": {"type": "string"}}, "why": {"type": "string"}}}},
                "why": {"type": "string"}}}}}}

CONTRACT = """당신은 한글(HWPX) 문서의 **개요 템플릿 서식을 정리**하는 에이전트입니다. 템플릿 하나(레터 사슬 — 예: 「□ › o › -」)의 레벨마다, 같은 레벨인데 서식이 조금씩
다른 줄들을 어느 모양으로 맞출지, 어느 줄을 그대로 두거나 다른 템플릿으로 뗄지 정합니다.

## 입력
- material.template: 템플릿 번호·레터 사슬·구실·줄 수.
- material.levels[]: 레벨마다 groups — 그 레벨 줄들을 **서식이 같은 것끼리 묶은 갈래**입니다(스크립트가 문서에서 뽑은 값).
  갈래마다 id · lines(줄 수) · sample(그 갈래 첫 줄의 글) 이 있고, 지금 대표 갈래(currentRep)는 values(서식 값 전부), 나머지는 differsFromRep([이름, 대표 값, 이 갈래 값]…)만 있습니다.
  대표가 없는 레벨은 모든 갈래에 values 가 있습니다.
  repChosenByUser 가 있는 레벨은 사람이 그 대표를 직접 정한 것입니다 · positionRule 은 사람이 정한 둘째 줄 규칙입니다(맞춘 줄에도 그 규칙이 걸립니다).
  cannotSplit 이 있는 갈래는 다른 템플릿으로 뗄 수 없습니다(번호형 레벨에서 같은 부모 아래 형제의 일부 — 번호가 따로 매겨집니다).
  splitTogether 가 있는 갈래는 혼자는 못 떼지만, 거기 적힌 갈래들과 **한 split 항목에 함께**(rep 또는 match 로) 넣으면 뗄 수 있습니다(번호형 레벨 — 같은 표의 형제 줄은 함께 옮깁니다).
  table 이 있는 갈래는 **표 안의 줄**입니다 — header(그 표의 머리글) · tables(표 수) · textAround(그 표의 다른 글의 글꼴·크기 — 주변 글) ·
  ownFormat(그 표에는 대표와 서식이 같은 줄이 하나도 없습니다 — 그 표가 제 서식을 씁니다). differsFromRep 의 이름 「표」 = 대표 줄과 표(머리글)가 다릅니다. 표 안의 줄은 서식이 같아도 표가 다르면 다른 갈래로 옵니다.
- 값의 뜻: 레터 앞 빈칸·레터·레터 뒤 빈칸 = 줄 첫머리 / 앞 여백 = 첫 줄 시작 자리(mm) · 2번째 줄 = 줄이 넘어갈 때 시작 자리(mm) / 레터 글꼴·크기… = 레터 글자 모양 / 글꼴·크기… = 본문 바탕 글자 모양.
  differsFromRep 의 이름 「닮은 레터 글자」 = 레터는 대표와 **같고 글자만 다른** 것입니다(헤딩 판정이 같은 레터로 묶은 글자 — 「o」·「ㅇ」·「○」 · 「·」·「⋅」·「•」). 이름 「레터」 는 레터 자체가 다를 때만 나옵니다.
  differsFromRep 의 이름 「자동 글머리」 = 그 갈래의 레터는 글로 친 것이 아니라 한글의 자동 글머리표·문단 번호입니다(레터는 대표와 같습니다 — 「레터」 가 다른 것이 아닙니다).
  cannotBeRep 이 있는 갈래(자동 글머리 줄)는 rep 로 고를 수 없고 다른 템플릿으로 뗄 수도 없습니다 — match 하면 대표의 접두가 글로 들어가 친 레터가 됩니다.

## 정할 것 — 줄이 있는 모든 레벨에 한 항목씩
- rep: 그 레벨의 **대표로 삼을 갈래 id**. 지금 대표가 알맞으면 그 id 를 그대로 적습니다.
- match: 대표 모양으로 **바꿀** 갈래 id 들. 바꾸면 그 갈래 줄의 레터 첫머리(레터 앞 빈칸·레터 글자·레터 뒤 빈칸) · 문단 모양 · 레터와 본문 바탕 글자 모양이 대표 것이 됩니다
  (번호형 레터는 제 번호를 지키고, 따로 강조한 글자는 그대로입니다).
- keep: **그대로 둘** 갈래 id 와 까닭(why — 한 문장).
- split: **다른 템플릿으로 뗄** 갈래 — 새 템플릿 하나에 한 항목 {rep, match, why}: rep = 새 템플릿의 **대표가 될 갈래 id**, match = 그 새 대표 모양으로 바꿔 **같이 옮길** 갈래 id 들(없으면 빈 목록),
  why = 뗀 까닭(한 문장). 뗀 갈래의 줄(과 그 아래 줄)은 이 템플릿의 그 레벨에서 빠져 그 레벨부터 시작하는 **서식 종속 템플릿**(예: T1 의 L3 에서 떼면 「T1L3a」)이 되고,
  뒤로는 그 줄들끼리만 서식을 견줍니다. 뗄 것이 없으면 빈 목록입니다.
- why: 그 레벨에서 그 대표를 고른 까닭(한두 문장).
- summary: 템플릿 전체에 무엇을 하는지 두세 문장.

## 지킬 것
- 갈래 id 는 **입력에 있는 것만** 씁니다. 서식 값을 새로 만들거나 고쳐 적지 않습니다 — 맞출 값은 대표 갈래의 값 그대로입니다.
- 한 갈래는 rep · match · keep · split(의 rep·match) 가운데 **한 곳에만** 둡니다. 갈래가 하나뿐인 레벨은 rep 만 적고 match·keep·split 은 빈 목록입니다.
- 그 레벨의 rep 갈래와 cannotSplit 이 있는 갈래는 split 에 넣지 않습니다. splitTogether 가 있는 갈래를 뗄 때는 거기 적힌 갈래를 모두 같은 split 항목에 넣습니다.
- 「스킬」(과 「이번 요청」)의 기준으로 match·split 을 정할 수 없는 갈래만 keep 에 두고 까닭을 적습니다 — 사람이 계획을 보고 고릅니다.
- 판단의 기준은 아래 「스킬」 글이고, 「이번 요청」 이 있으면 그것이 스킬보다 먼저입니다. 둘 다 위 「지킬 것」 과 답의 꼴은 바꾸지 못합니다."""


def prompt(mat, sk, request=""):
    req = (request or "").strip()
    return (prompt_texts.contract(__name__) + f"\n\n## 스킬 — {sk['name']} (사용자가 저장해 둔 정리 기준)\n{sk['text'].strip()}"
            + (f"\n\n## 이번 요청 (스킬보다 먼저)\n{req}" if req else "")
            + "\n\n## 자료 (JSON)\n```json\n" + json.dumps({"material": prompt_material(mat)}, ensure_ascii=False, indent=1) + "\n```")


def check_plan(mat, data):
    """LLM 답 data 를 자료 mat 과 견줘 계획으로 → {summary, levels[{level, letter, lines, single, rep{group, para, count, sample, changed}, was(지금 대표 갈래 id | None),
    match[{group, para, count, sample, diff}], keep[{group, para, count, sample, why, diff, auto, noSplit}],
    split[{name(「T1L3a」), sfx, rep{group, para, count, sample, diff}, match[{group, para, count, sample, diff, diffTo(새 템플릿의 대표 기준)}], why, moved(옮길 줄 수), change}],
    taken(이 레벨에서 이미 쓴 글자), change(바뀔 줄 수), moved(다른 템플릿으로 옮길 줄 수), why}], change, moved, notes[버린 것]}.
    diff = **새 대표** 기준 [[키, 이름, 대표 값, 이 갈래 값]…]. 없는 레벨·없는 id·겹친 id·못 떼는 갈래는 버리고 notes 에, 답에 없는 갈래·레벨은 그대로 둔다(auto)."""
    notes = []
    by_level = {}
    for row in (data or {}).get("levels") or []:
        lv = row.get("level") if isinstance(row, dict) else None
        if isinstance(lv, bool) or not isinstance(lv, int):
            continue
        if lv in by_level:
            notes.append(f"L{lv} 답이 두 번 — 첫 것만 씀")
            continue
        by_level[lv] = row
    known = {lv["level"] for lv in mat["levels"]}
    for lv in sorted(set(by_level) - known):
        notes.append(f"L{lv} 은 이 템플릿에 줄이 없는 레벨 — 버림")
    levels, total, moved = [], 0, 0
    for lv in mat["levels"]:
        gs = {g["id"]: g for g in lv["groups"]}
        was = next((g["id"] for g in lv["groups"] if g["rep"]), None)
        row = by_level.get(lv["level"]) or {}
        rep = row.get("rep") if isinstance(row.get("rep"), str) else None
        if rep not in gs:
            if rep:
                notes.append(f"L{lv['level']} 대표 「{rep}」 는 없는 서식 — 지금 대표를 그대로 둠")
            rep = was
        if lv.get("repSet") and was is not None and rep != was:  # 사람이 정한 대표는 답이 바꾸지 못한다 — 스킬 글이 말해도 검사가 강제한다(2026-11-16 astra)
            notes.append(f"L{lv['level']} 대표는 사람이 정한 것 — 「{rep}」 로 바꾸지 않음")
            rep = was
        if rep is not None and rep != was and gs[rep].get("cannotBeRep"):  # 자동 글머리 줄(② §8-8)은 대표가 못 된다 — 레터가 글에 없다
            notes.append(f"L{lv['level']} 서식 「{rep}」 는 자동 글머리표·문단 번호 줄이라 대표가 될 수 없음 — 지금 대표를 그대로 둠")
            rep = was
        why = str(row.get("why") or "").strip()
        # omitted = 갈래가 GROUP_MAX 를 넘어 에이전트에 보내지 않은 갈래 수(못 본 것 — 이 계획을 반영해도 「다 봄」 이 아니다: analysis.plan_state) · values = 값 칸 줄 수(갈래에 없다)
        entry = {"level": lv["level"], "letter": lv["letter"], "lines": lv["lines"],
                 "single": len(lv["groups"]) + lv["more"] + len(lv.get("held") or []) + len(lv.get("heldAuto") or []) <= 1, "was": was,
                 "rep": None, "match": [], "keep": [], "split": [], "taken": list(lv.get("taken") or []), "change": 0, "moved": 0, "why": why[:600],
                 "omitted": int(lv.get("more") or 0), "values": int(lv.get("values") or 0)}
        if rep is None:  # 대표가 없고 답도 못 고름 — 손댈 수 없다
            if lv["groups"]:
                notes.append(f"L{lv['level']} 은 대표가 없어 그대로 둠")
            # sig(갈래 지문 — 레벨 + 비교 값)도 싣는다: 반영한 뒤 남긴 줄(analysis.plan_left)을 열쇠 줄이 아니라 **서식**으로 찾게 — 전에는 이 가지만 지문이 없어,
            # 사람이 열쇠 줄 하나만 맞추면 그 갈래의 나머지 답 없는 줄이 0 으로 사라졌다(2026-11-17 astra)
            entry["keep"] = [{"group": g["id"], "para": g["para"], "count": g["count"], "sample": g["sample"], "why": "", "diff": [], "auto": True, "noSplit": True, "sig": g.get("sig", "")}
                             for g in lv["groups"]]
            levels.append(entry)
            continue
        base = gs[rep]
        entry["rep"] = {"group": rep, "para": base["para"], "count": base["count"], "sample": base["sample"], "changed": rep != was}
        seen = {rep}
        brief = lambda g, to=base: {"group": g["id"], "para": g["para"], "count": g["count"], "sample": g["sample"], "diff": M.diff(to["raw"], g["raw"])}  # noqa: E731
        blocked = lambda g: bool(g.get("noSplit"))  # noqa: E731 — 못 떼는 갈래(번호형 레벨의 형제 일부). 대표 갈래는 seen 이 막는다(대표를 바꾸면 옛 대표 갈래는 뗄 수 있다)
        # hard = **함께 옮겨도** 못 떼는 갈래 — 형제의 일부라서 혼자 못 떼는 갈래(번호형 레벨)는 같은 묶음의 갈래와 한 split 항목에 넣으면 된다(_units_short 가 합쳐서 본다 — ② §8-11)
        hard = lambda g, sized=bool(lv.get("unitSizes")): bool(g.get("noSplit")) and (bool(g.get("hard")) or not sized)  # noqa: E731
        for gid in row.get("match") or []:
            if not isinstance(gid, str) or gid not in gs:
                notes.append(f"L{lv['level']} 맞출 서식 「{gid}」 는 없는 서식 — 버림")
            elif gid in seen:
                if gid != rep:
                    notes.append(f"L{lv['level']} 서식 「{gid}」 가 두 번 — 첫 것만 씀")
            else:
                seen.add(gid)
                entry["match"].append(brief(gs[gid]))
        letters = (ch for ch in M.SFX if ch not in set(entry["taken"]))
        for sp in row.get("split") or []:  # 다른 템플릿으로 뗄 갈래(② §8-5) — 항목 하나 = 새 서식 종속 템플릿 하나
            gid = sp.get("rep") if isinstance(sp, dict) else None
            if not isinstance(gid, str) or gid not in gs:
                notes.append(f"L{lv['level']} 뗄 서식 「{gid}」 는 없는 서식 — 버림")
                continue
            if gid in seen:
                notes.append(f"L{lv['level']} 서식 「{gid}」 는 {'이 레벨의 대표라 뗄 수 없음' if gid == rep else '두 번 — 첫 것만 씀'}")
                continue
            if hard(gs[gid]):
                notes.append(f"L{lv['level']} 서식 「{gid}」 는 뗄 수 없어 그대로 둠 — {gs[gid]['noSplit']}")
                continue
            head = gs[gid]
            mids = []  # 같이 옮길 갈래 — 다 검사한 뒤에 건다(항목의 줄을 합쳐 형제 묶음이 통째인지 본다: ② §8-11 「번호형 레벨의 떼기」)
            for mid in sp.get("match") or []:
                if not isinstance(mid, str) or mid not in gs:
                    notes.append(f"L{lv['level']} 「{gid}」 와 같이 옮길 서식 「{mid}」 는 없는 서식 — 버림")
                elif mid in seen or mid in mids or mid == gid:
                    if mid != gid:
                        notes.append(f"L{lv['level']} 서식 「{mid}」 는 {'이 레벨의 대표라 뗄 수 없음' if mid == rep else '두 번 — 첫 것만 씀'}")
                elif hard(gs[mid]):
                    notes.append(f"L{lv['level']} 서식 「{mid}」 는 뗄 수 없어 그대로 둠 — {gs[mid]['noSplit']}")
                else:
                    mids.append(mid)
            short = _units_short(lv, [head] + [gs[m] for m in mids])
            if short:
                notes.append(f"L{lv['level']} 서식 「{gid}」{f'(과 같이 옮길 서식 {len(mids)}가지)' if mids else ''} 는 뗄 수 없어 그대로 둠 — {short}")
                continue
            sfx = next(letters, None)
            if sfx is None:
                notes.append(f"L{lv['level']} 에서 뗄 수 있는 템플릿 수를 다 써 「{gid}」 는 그대로 둠")
                continue
            seen.add(gid)
            item = {"name": f"T{mat['no']}L{lv['level']}{sfx}", "sfx": sfx, "rep": brief(head), "match": [], "why": str(sp.get("why") or "").strip()[:400]}
            for mid in mids:
                seen.add(mid)
                item["match"].append({**brief(gs[mid]), "diffTo": M.diff(head["raw"], gs[mid]["raw"])})  # diff = 이 레벨 대표 기준(다른 줄과 같이) · diffTo = 새 템플릿의 대표 기준
            item["change"] = sum(m["count"] for m in item["match"])
            item["moved"] = head["count"] + item["change"]
            entry["split"].append(item)
        for k in row.get("keep") or []:
            gid = k.get("group") if isinstance(k, dict) else None
            if not isinstance(gid, str) or gid not in gs:
                notes.append(f"L{lv['level']} 그대로 둘 서식 「{gid}」 는 없는 서식 — 버림")
            elif gid not in seen:
                seen.add(gid)
                entry["keep"].append({**brief(gs[gid]), "why": str(k.get("why") or "").strip()[:400], "auto": False, "noSplit": blocked(gs[gid])})
        for g in lv["groups"]:  # 답이 말하지 않은 갈래 — 그대로
            if g["id"] not in seen:
                entry["keep"].append({**brief(g), "why": "", "auto": True, "noSplit": blocked(g)})
        for g in lv.get("held") or []:  # 이번에 보내지 못했지만 앞 계획이 검토해 그대로 둔 갈래 — 그 판단을 이어받는다(다시 「못 본 갈래」 가 되지 않는다)
            entry["keep"].append({**brief(g), "why": "앞 계획에서 그대로 둠", "auto": False, "carried": True, "noSplit": blocked(g)})
        for g in lv.get("heldAuto") or []:  # 앞서 보냈지만 답이 없던 갈래 — 답 없음 그대로
            entry["keep"].append({**brief(g), "why": "", "auto": True, "carried": True, "noSplit": blocked(g)})
        for k in entry["keep"]:
            k["sig"] = next((g["sig"] for g in list(lv["groups"]) + list(lv.get("held") or []) + list(lv.get("heldAuto") or []) if g["id"] == k["group"]), "")
        entry["sent"] = [{"para": g["para"], "sig": g["sig"]} for g in list(lv["groups"]) + list(lv.get("held") or []) + list(lv.get("heldAuto") or []) if not g["rep"]]
        for m in entry["match"]:
            m["noSplit"] = blocked(gs[m["group"]])
        entry["change"] = sum(m["count"] for m in entry["match"]) + sum(sp["change"] for sp in entry["split"])
        entry["moved"] = sum(sp["moved"] for sp in entry["split"])
        total += entry["change"]
        moved += entry["moved"]
        levels.append(entry)
    # left = 이 계획을 그대로 반영해도 남는 줄: kept = 에이전트가 「그대로」 로 답한 갈래의 줄 · unanswered = 답이 말하지 않아 그대로 둔 갈래의 줄(검토해 남긴 것과 다르다)
    keeps = [k for lv in levels for k in lv["keep"]]
    left = {"kept": sum(k["count"] for k in keeps if not k.get("auto")), "unanswered": sum(k["count"] for k in keeps if k.get("auto"))}
    # reviewed = 에이전트가 답해서 그대로 둔 갈래의 열쇠 줄(이어받은 것 포함) — 다음 계획의 자료가 이 갈래들을 뒤로 돌린다(material)
    return {"summary": str((data or {}).get("summary") or "").strip()[:1200], "levels": levels, "change": total, "moved": moved, "notes": notes,
            "omitted": sum(lv["omitted"] for lv in levels), "left": left,
            "reviewed": [{"para": k["para"], "sig": k.get("sig", "")} for k in keeps if not k.get("auto")],   # 답해서 그대로 둔 갈래(이어받은 것 포함)
            "sent": [x for lv in levels for x in lv.pop("sent", [])]}                                          # 에이전트에 보낸 적 있는 갈래(이번 + 이어받은 이력)


def todo(plan):
    """계획(check_plan 의 답) → 에이전트가 고른 그대로 반영할 때의 적용 몸 {levels[{level, rep(대표 줄), likes[맞출 갈래의 첫 줄], splits?[{likes, rep, sfx}]}], n(바뀔 줄 수), moved(다른 템플릿으로 옮길 줄 수),
    reps(대표를 바꾸는 레벨 수)}.
    화면의 `tpaTodoOf`(tpl_agent.js — 템플릿 줄의 「계획대로 맞추기」)와 **같은 셈**이다: 맞추기·떼기로 고른 갈래만 · 「그대로」 로 남긴 갈래는 빼고 · 고른 갈래도 없고 대표도 그대로인 레벨은 없다.
    **대표만 바꾸는 레벨도 든다**(likes 빈 목록 — 2026-11-16 astra: 전에는 고른 갈래가 없으면 그 레벨을 버려, 에이전트가 고른 대표가 걸리지 않고 대표가 없던 한 갈래 레벨은 끝내 대표가 없었다).
    받아 둔 계획을 한 번에 반영하는 끝점(tpl_agent_api.apply_plans)과 분석 상태의 서식 항목(analysis — 반영하면 바뀔 줄 수 · 대표 변경 수)이 쓴다. 한쪽 셈을 고치면 다른 쪽도 고친다."""
    levels, n, moved, reps = [], 0, 0, 0
    for lv in (plan or {}).get("levels") or []:
        if not lv.get("rep"):
            continue
        match, cuts = lv.get("match") or [], lv.get("split") or []
        swap = bool(lv["rep"].get("changed"))  # 계획이 이 레벨의 대표를 바꾼다(대표가 없던 레벨에 정하는 것 포함)
        if not match and not cuts and not swap:
            continue
        reps += swap
        n += sum(g["count"] for g in match) + sum(g["count"] for sp in cuts for g in sp.get("match") or [])  # 뗀 줄 가운데 새 대표와 다른 갈래는 그 대표에 맞춘다
        moved += sum(sp["rep"]["count"] + sum(g["count"] for g in sp.get("match") or []) for sp in cuts)
        row = {"level": lv["level"], "rep": lv["rep"]["para"], "likes": [g["para"] for g in match]}
        if cuts:
            row["splits"] = [{"likes": [sp["rep"]["para"]] + [g["para"] for g in sp.get("match") or []], "rep": sp["rep"]["para"], "sfx": sp["sfx"]} for sp in cuts]
        levels.append(row)
    return {"levels": levels, "n": n, "moved": moved, "reps": reps}


def apply_view(plan, levels, into=None):
    """**실제로 반영한 것**을 적는다(spec_헤딩_추출 ② §7 「결과 화면」) — 요청 몸 levels(`todo` 의 꼴: [{level, rep, likes[갈래의 열쇠 줄], splits[{likes, rep, sfx}]}] — 「모두 반영」 은 에이전트가 고른 그대로,
    「템플릿 서식 정리」 열의 「적용」 은 사람이 고르기를 바꾼 것)을 계획의 갈래 정보(줄 수 · 견본 · 대표와 다른 값)로 풀어서:
    → [{level, letter, lines, rep{para, sample, changed}, match[{para, count, sample, diff[[이름, 전(그 갈래 값), 후(대표 값)]…]}], split[{sfx, rep{…}, match[…]}],
        keep[{para, count, sample, why, auto(답 없음), carried(앞 계획에서 이어받음), byUser(계획은 바꾸라 했는데 사람이 그대로로)}], omitted(못 본 갈래), values(값 칸 줄)}].
    계획의 레벨 가운데 요청에 없는 것(고른 갈래가 없음)도 남긴 갈래가 있으면 싣는다 — 「남긴 것」 이 결과에 보이게.
    into = 반영이 적은 「윗레벨 떼기 때문에 새 템플릿으로 떼지 않은 줄」 [{level, no, sfx, lines, whole, stayed?}](outline_match_api._cut_now) — 그 떼기 항목에 split[].into[{no, lines, whole, stayed?}] 로 싣는다
    (whole = 새 템플릿을 만들지 않았다 · 표시가 없으면 윗레벨 떼기가 데려간 템플릿 「T{no}」 의 그 레벨 대표 서식이 됐고, stayed 면 계획한 대표가 떠난 이 템플릿 「T{no}」 의 그 레벨 대표 서식이 됐고,
    aside 면 계획한 대표도 그 템플릿으로 가 그 대표가 이겨 그 템플릿에서 다른 서식으로 그대로 남았다)."""
    asked = {int(r["level"]): r for r in levels or [] if isinstance(r, dict) and r.get("level") is not None}

    def went(level, sfx):  # 그 떼기 항목에서 윗레벨 떼기가 먼저 데려간 줄 → {"into": [...]} | {}
        got = [{"no": x["no"], "lines": x["lines"], "whole": bool(x.get("whole")), **{k: True for k in ("stayed", "aside") if x.get(k)}} for x in into or ()
               if int(x.get("level") or 0) == int(level) and x.get("sfx") == sfx]
        return {"into": got} if got else {}
    out = []
    for L in (plan or {}).get("levels") or []:
        groups, planned = {}, set()
        for g in L.get("match") or []:
            groups[g["para"]] = g
            planned.add(g["para"])
        for sp in L.get("split") or []:
            for g in [sp.get("rep") or {}] + list(sp.get("match") or []):
                if g.get("para"):
                    groups[g["para"]] = g
                    planned.add(g["para"])
        for k in L.get("keep") or []:
            groups[k["para"]] = k
        req = asked.get(int(L["level"])) or {}
        likes = [p for p in req.get("likes") or [] if p in groups]
        cuts = [sp for sp in req.get("splits") or [] if isinstance(sp, dict)]
        cut_paras = {p for sp in cuts for p in sp.get("likes") or []}

        def brief(p, groups=groups):
            g = groups.get(p) or {}
            return {"para": p, "count": g.get("count"), "sample": g.get("sample", ""), "diff": [[d[1], d[3], d[2]] for d in g.get("diff") or []]}  # [이름, 전(그 갈래), 후(대표)]
        keep = [{"para": p, "count": g.get("count"), "sample": g.get("sample", ""), "why": g.get("why", ""), "auto": bool(g.get("auto")), "carried": bool(g.get("carried")),
                 "byUser": p in planned} for p, g in groups.items() if p not in likes and p not in cut_paras]
        if not req and not keep and not L.get("omitted"):
            continue
        rep0 = L.get("rep") or {}
        rep_para = req.get("rep") or rep0.get("para")
        out.append({"level": L["level"], "letter": L.get("letter", ""), "lines": L.get("lines"),
                    "rep": {"para": rep_para, "sample": rep0.get("sample", "") if rep_para == rep0.get("para") else (groups.get(rep_para) or {}).get("sample", ""),
                            "changed": bool(req) and bool(rep0.get("changed")) and rep_para == rep0.get("para")},
                    "match": [brief(p) for p in likes],
                    "split": [{"sfx": sp.get("sfx"), "rep": brief(sp.get("rep") or (sp.get("likes") or [None])[0]),
                               "match": [brief(p) for p in sp.get("likes") or [] if p != (sp.get("rep") or (sp.get("likes") or [None])[0])],
                               **went(L["level"], sp.get("sfx"))} for sp in cuts],
                    "keep": keep, "omitted": int(L.get("omitted") or 0), "values": int(L.get("values") or 0)})
    return out


def run(mat, sk, request="", call=None):
    """LLM 한 번 → {plan | None, error, model, effort, backend, ms, costUsd}. LLM 이 꺼져 있으면 error "off"."""
    req = (request or "").strip()[:REQUEST_MAX]
    res = (call or llm.call)(SCHEMA, prompt(mat, sk, req), "tpl-agent", timeout=TIMEOUT, effort=effort(), model=model(), pin=True)
    out = {"plan": None, "error": res.get("error"), "model": res.get("model") or model(), "effort": res.get("effort") or effort(), "backend": res.get("backend"),
           "ms": res.get("ms") or 0, "costUsd": res.get("costUsd")}
    if isinstance(res.get("data"), dict):
        out["plan"] = check_plan(mat, res["data"])
        out["error"] = None
    return out

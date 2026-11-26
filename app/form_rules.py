"""규정 YAML — 다른 규칙(관리 규정 · 지침서 · 법령)이 이 양식에 요구하는 것을 양식마다 **YAML 파일 하나**로(spec_양식작성 ② §5-9).
2026-11-26 사용자 "yaml로 보고자 하는 거는 사람이 읽기 편하게 구성되길 바래서요. rules.yaml 을 선호 하고 판단지침에 참조할 수 있도록 한다" · "결국에는 사람이 지침을 확인하고 관리하기 편하도록".
설계는 astra · Fable 검토(artifacts/guideline_yaml_astra_2026-11-26/ — 에이전트 판단 · 사용자 확인 전).

- 파일 = 양식 지침 YAML 의 짝 `forms/<양식 키>.rules.yaml`(같은 폴더 · 같은 키 · git · env `NFM_FORMS`). 쓰기 · 이력은 `form_guide_yaml._write` 그대로(sha1 판 · 고치기 전 글은 `forms_history/<키>.rules/`).
- 꼴(`parse`): `schema` · `form` · `rules[{id, text, source{name, clause, date}, required(bool), applies(적용 조건 글), targets[{path[], table?, subtable?, field?}]}]`.
  `targets` 가 없으면 **문서 전체**에 닿는다(자리를 모르는 요구 — 분량 · 글꼴 · 보안). target 하나 = 절의 경로(`path` — 양식 지침의 sections[].path 와 같은 글) + 그 절의 표 머리글(`table`) + 그 표의 서브 테이블 머리 글(`subtable`) + 칸의 라벨(`field`).
- **자리 잇기는 양식 지침의 것을 가져다 쓴다**(`form_guide_yaml.locate` — 열쇠 · 정규화 · 「꼭 같을 때만」 을 두 벌 만들지 않는다): target 마다 양식 지침 꼴의 절 하나로 바꿔 `locate` 에 넘긴다(`as_form`).
- 읽는 곳 = `place_guides_api.index_of`(src "rule" · kind 「규정」 — 자리에 이어진 것은 자리마다, targets 없는 것은 색인의 `doc` 묶음에 한 번). **LLM 은 이 파일에 쓰지 않는다**(사람만 — 04 는 참조로 읽을 뿐 규칙으로 다시 내지 않는다).
- 이 모듈은 서버 · 세션을 모른다 — 끝점은 `app/form_rules_api.py`."""
import yaml

from app import form_guide_yaml as FG
from app import heading_forms as HF

SCHEMA = 1
SUFFIX = ".rules.yaml"
KIND = "규정"
RULES_MAX, TARGETS_MAX = 300, 20
APPLIES_MAX, SOURCE_MAX = 300, 120

HEADER = ("# 규정 — {name}. 다른 규칙(관리 규정 · 지침서 · 법령)이 이 양식에 요구하는 것(spec/spec_양식작성.md ② §5-9). 사람이 적는다 — LLM 은 여기 쓰지 않는다.\n"
          "# rules[] = id(영문 · 숫자) · text(요구하는 것 — 한 항목에 한 가지) · source(name 규정 이름 · clause 조항 · date 시행일) · required(true = 꼭 지킬 것 | false = 권고) · applies(적용 조건 — 글로) ·\n"
          "# targets(닿는 자리 — 없으면 문서 전체): path = 헤딩 경로(양식 지침의 sections[].path 와 같은 글) · table = 그 절의 표 머리글(「 | 」 로) · subtable = 그 표의 서브 테이블 머리 글 · field = 칸의 라벨 글.\n")


def path_of(key):
    HF.check_key(key)
    d = HF.forms_dir()
    return None if d is None else d / f"{key}{SUFFIX}"


def _empty(key):
    return {"schema": SCHEMA, "form": key or "", "rules": []}


def _target(x, strict, where):
    if not isinstance(x, dict):
        if strict:
            raise ValueError(f"{where} 의 targets 항목은 「path: […]」 묶음이어야 합니다")
        return None
    path = [FG._s(p, 200) for p in x.get("path") or () if FG._s(p, 200)] if isinstance(x.get("path"), list) else []
    if not path or len(path) > FG.PATH_MAX:
        if strict:
            raise ValueError(f"{where} 의 targets 항목에는 path(헤딩 경로 — 제목 글 1~{FG.PATH_MAX}개의 목록)가 있어야 합니다")
        return None
    out = {"path": path}
    for k, n in (("table", FG.HEAD_MAX), ("subtable", FG.HEAD_MAX), ("field", FG.LABEL_MAX)):
        v = FG._s(x.get(k), n)
        if v:
            out[k] = v
    if ("subtable" in out or "field" in out) and "table" not in out:
        if strict:
            raise ValueError(f"{where} 의 targets 에 subtable · field 를 적으려면 table(그 표의 머리글)도 적습니다")
        return None
    for k in ("table", "subtable"):
        if k in out and not FG._sig_of_text(out[k]):
            if strict:
                raise ValueError(f"{where} 의 targets 의 {k} 에 글자가 없습니다")
            return None
    return out


def parse(text, key=None, strict=True):
    """YAML 글 → 정리한 규정. strict 면 틀린 꼴은 ValueError(화면에서 고친 글의 검사), 아니면 쓸 수 있는 것만 남긴다(저장된 파일 읽기)."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("YAML 글이 비었습니다")
    if len(text) > FG.TEXT_MAX:
        raise ValueError(f"YAML 글은 {FG.TEXT_MAX:,}자까지입니다")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        raise ValueError("YAML 을 읽을 수 없습니다" + (f"({mark.line + 1}번째 줄 — {getattr(e, 'problem', '') or '꼴이 틀림'})" if mark else f"({e})")) from e
    if not isinstance(data, dict):
        raise ValueError("YAML 의 맨 위는 「키: 값」 묶음이어야 합니다")
    form = FG._s(data.get("form"), 60) or (key or "")
    if key is not None and form != key:
        raise ValueError(f"form 은 파일의 양식 키 「{key}」 여야 합니다")
    raw = data.get("rules")
    if raw is not None and not isinstance(raw, list):
        raise ValueError("rules 는 목록이어야 합니다")
    out, seen, texts = {"schema": SCHEMA, "form": form, "rules": []}, set(), set()
    for x in raw or ():
        if not isinstance(x, dict):
            if strict:
                raise ValueError("rules 의 항목은 「id · text · …」 묶음이어야 합니다")
            continue
        rid = FG._id(x, strict, "rules", seen)
        if rid is None:
            continue
        where = f"규정 「{rid}」"
        body = FG._long(x.get("text"), FG.GUIDE_MAX)
        if not body:
            if strict:
                raise ValueError(f"{where} 에 text(요구하는 것)가 없습니다")
            continue
        req = x.get("required", True)
        if not isinstance(req, bool):
            if strict:
                raise ValueError(f"{where} 의 required 는 true | false 입니다")
            req = True
        src = x.get("source") if isinstance(x.get("source"), dict) else ({"name": x["source"]} if isinstance(x.get("source"), str) else {})
        if x.get("source") is not None and not src and strict:
            raise ValueError(f"{where} 의 source 는 「name · clause · date」 묶음입니다")
        source = {k: FG._s(src.get(k), SOURCE_MAX) for k in ("name", "clause", "date") if FG._s(src.get(k), SOURCE_MAX)}
        tg = x.get("targets")
        if tg is not None and not isinstance(tg, list):
            if strict:
                raise ValueError(f"{where} 의 targets 는 목록입니다(없으면 문서 전체)")
            tg = []
        targets = [t for t in (_target(t, strict, where) for t in tg or ()) if t]
        if len(targets) > TARGETS_MAX:
            if strict:
                raise ValueError(f"{where} 의 targets 는 {TARGETS_MAX}개까지입니다")
            targets = targets[:TARGETS_MAX]
        if tg and not targets and not strict:
            continue   # 자리를 적었는데 하나도 못 읽음 — 문서 전체로 넓혀 읽지 않는다
        if (body, tuple(map(str, targets))) in texts:
            continue
        texts.add((body, tuple(map(str, targets))))
        out["rules"].append({"id": rid, "text": body, "source": source, "required": req, "applies": FG._s(x.get("applies"), APPLIES_MAX), "targets": targets})
    if len(out["rules"]) > RULES_MAX:
        if strict:
            raise ValueError(f"rules 는 {RULES_MAX}개까지입니다")
        out["rules"] = out["rules"][:RULES_MAX]
    return out


def _clean(d):
    rows = []
    for r in d.get("rules") or ():
        o = {"id": r["id"], "text": r["text"]}
        if r.get("source"):
            o["source"] = {k: r["source"][k] for k in ("name", "clause", "date") if r["source"].get(k)}
        o["required"] = bool(r.get("required", True))
        if r.get("applies"):
            o["applies"] = r["applies"]
        if r.get("targets"):
            o["targets"] = [{k: t[k] for k in ("path", "table", "subtable", "field") if t.get(k)} for t in r["targets"]]
        rows.append(o)
    return {"schema": SCHEMA, "form": d["form"], "rules": rows}


def dump(d):
    return HEADER.format(name=d["form"]) + yaml.safe_dump(_clean(d), allow_unicode=True, sort_keys=False, width=4096, default_flow_style=False)


def read(key):
    """→ (정리한 규정, 지금 글, sha1) — 파일이 없으면 (빈 규정, None, "") · 못 읽는 파일이면 ValueError."""
    p = path_of(key)
    if p is None or not p.is_file():
        return _empty(key), None, ""
    text = p.read_bytes().decode("utf-8")
    return parse(text, key, strict=False), text, FG._sha1(text)


def load(key):
    """읽기만(없거나 못 읽으면 None — 읽는 쪽이 죽지 않게)."""
    try:
        d, text, _ = read(key)
    except (ValueError, OSError):
        return None
    return d if text is not None else None


def save_text(key, text, *, expect=None, reason=""):
    """YAML 글을 검사해 저장 → (정리한 것, sha1). expect = 읽었을 때의 sha1("" = 새 파일) · 다르면 form_guide_yaml.StaleVersion."""
    text = text.replace("\r\n", "\n") if isinstance(text, str) else text
    d = parse(text, key, strict=True)
    return d, FG._write(key, text, expect, reason, path=path_of(key), kind="formRules", hist="rules", label="규정")


def source_text(source):
    """source{name, clause, date} → 「이름 조항 (날짜)」 | ""."""
    s = source or {}
    t = " ".join(x for x in (s.get("name"), s.get("clause")) if x)
    return t + (f" ({s['date']})" if s.get("date") else "") if t or s.get("date") else ""


def guide_of(r, src="rule", kind=KIND):
    """규정 항목 → 자리 지침 하나 {src, kind, text, required, source?, applies?, rule}."""
    g = {"src": src, "kind": kind, "text": r["text"], "rule": r["id"]}
    if src == "rule":
        g["required"] = bool(r.get("required", True))
    if source_text(r.get("source")):
        g["source"] = source_text(r.get("source"))
    if r.get("applies"):
        g["applies"] = r["applies"]
    return g


def as_form(items, src="rule", kind=KIND):
    """targets 가 있는 항목들 → 양식 지침 꼴의 절 목록(target 하나 = 절 하나 — `form_guide_yaml.locate` 에 그대로 넘긴다) + {절 · 표 · 띠 id: 항목 id}."""
    secs, owner, leaf = [], {}, set()
    for r in items or ():
        for k, t in enumerate(r.get("targets") or ()):
            it = {"text": r["text"], "origin": "user", "extra": guide_of(r, src, kind)}
            sid = f"{r['id']}#{k}"
            sec = {"id": sid, "path": t["path"], "guides": [], "examples": [], "tables": []}
            owner[sid] = r["id"]
            node = sec
            if t.get("table"):
                tab = {"id": sid + ".t", "head": t["table"], "guides": [], "examples": [], "fields": [], "subtables": []}
                owner[tab["id"]] = r["id"]
                node = tab
                if t.get("subtable"):
                    node = {"id": sid + ".b", "head": t["subtable"], "guides": [], "examples": [], "fields": []}
                    owner[node["id"]] = r["id"]
                    tab["subtables"].append(node)
                if t.get("field"):
                    node["fields"].append({"label": t["field"], "guides": [it]})
                else:
                    node["guides"].append(it)
                sec["tables"].append(tab)
            else:
                sec["guides"].append(it)
            leaf.add(node["id"])   # 그 target 이 가리키는 가장 안쪽 항목 — 이것이 이어져야 이어진 것(절만 맞고 표가 없으면 세지 않는다)
            secs.append(sec)
    return secs, owner, leaf


def locate(items, places, blocks=None, src="rule", kind=KIND):
    """항목들(규정의 rules · 문서 목적의 guides — {id, text, targets?, …}) + 지금 문서의 자리(form_guide_yaml.doc_places) →
    {"heads": {헤딩 id: [지침…]}, "tables": {표 id: [지침…]}, "doc": [targets 없는 항목의 지침…](문서 전체), "links": {항목 id: 이어진 자리 수}, "unmatched": [{id, kind, what, why}]}."""
    items = list(items or ())
    secs, owner, leaf = as_form([r for r in items if r.get("targets")], src, kind)
    got = FG.locate({"sections": secs}, places, blocks) if secs else {"heads": {}, "tables": {}, "links": {}, "unmatched": []}
    links = {}
    for nid, hits in got["links"].items():
        if nid in leaf:
            links[owner[nid]] = links.get(owner[nid], 0) + len(hits)
    unmatched = [{**u, "id": owner.get(u["id"], u["id"])} for u in got["unmatched"]]
    return {"heads": got["heads"], "tables": got["tables"], "doc": [guide_of(r, src, kind) for r in items if not r.get("targets")],
            "links": links, "unmatched": unmatched}

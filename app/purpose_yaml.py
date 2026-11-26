"""문서 목적 YAML — 공고 · RFP 처럼 **과제(프로젝트)마다 다른 것**을 프로젝트마다 YAML 파일 하나로(spec_양식작성 ② §5-9).
2026-11-26 사용자 "둘다 공고 RFP 처럼 문서 목적은 purpose.yaml 이나 goal.yaml 로 두고 이를 참조하는게 좋을거 같은데 … 작업에 그때 목적에 맞게 반영되는 건 프로젝트에서 관리하면될듯".

- 파일 = 계정의 작업 뿌리(`works.root()`) 아래 `_purpose/<프로젝트 이름에서 지은 안전한 이름>.yaml`(프로젝트 = 작업의 `task.project` — 계정마다 따로: works.root 가 가른다).
  폴더 이름이 작업 id 꼴이 아니라 작업 목록에 섞이지 않는다(`_accounts` 와 같은 방식). 프로젝트 이름을 바꾸면 따라가고(`moved`), 프로젝트를 지우면 `_purpose/_removed/` 로 옮긴다(`removed` — 지우지 않는다).
- 꼴(`parse`): `schema` · `project` · `announcement{name, agency, date}`(공고) · `purpose`(문서의 목적 — 글) · `evaluation[글]`(평가 관점) · `requirements[{text, source}]`(공고가 요구하는 것) ·
  `guides[{id?, text, targets?}]`(그 프로젝트에서 그때 목적에 맞게 반영하는 지침 — targets 는 규정과 같은 꼴: 없으면 문서 전체).
- 읽는 곳 = `place_guides_api.index_of`(src "purpose" — 목적 · 평가 관점 · 요구 사항 · targets 없는 지침은 색인의 `doc` 묶음에 한 번, targets 있는 지침은 그 자리에). **LLM 은 이 파일에 쓰지 않는다.**
- 자리 잇기는 `form_rules.locate`(→ `form_guide_yaml.locate`) 를 가져다 쓴다. 이 모듈은 서버 · 세션을 모른다 — 끝점은 `app/purpose_yaml_api.py`."""
import hashlib
import os
import re
import threading
import time

import yaml

from app import form_guide_yaml as FG
from app import form_rules as FR
from app import works

SCHEMA = 1
DIR = "_purpose"
KIND = "문서 목적"
KINDS = {"purpose": "문서 목적", "evaluation": "문서 목적 — 평가 관점", "requirement": "문서 목적 — 요구 사항", "guide": "문서 목적 — 프로젝트 지침"}
PURPOSE_MAX, LIST_MAX = 4000, 60
_LOCK = threading.RLock()
_UNSAFE = re.compile(r'[\\/:*?"<>|\s.]+')

HEADER = ("# 문서 목적 — 프로젝트 「{name}」. 공고 · RFP 처럼 이 과제에만 맞는 것(spec/spec_양식작성.md ② §5-9). 사람이 적는다 — LLM 은 여기 쓰지 않고 참조로만 읽는다.\n"
          "# announcement = 공고(name 공고명 · agency 기관 · date 날짜) · purpose = 이 문서를 왜 쓰나(글) · evaluation = 평가 관점(글 목록) · requirements = 공고가 요구하는 것(text · source 출처) ·\n"
          "# guides = 이 프로젝트에서 그때 목적에 맞게 반영하는 지침(text · targets — 닿는 자리: path 헤딩 경로 · table 표 머리글 · subtable · field. 없으면 문서 전체).\n")


def safe(name):
    """프로젝트 이름 → 파일 이름(읽을 수 있는 앞머리 + 이름의 지문 — 다른 이름이 같은 파일로 겹치지 않게)."""
    name = " ".join(str(name or "").split())
    head = _UNSAFE.sub("_", name).strip("_")[:40] or "project"
    return f"{head}-{hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]}"


def path_of(project):
    root = works.root()
    name = " ".join(str(project or "").split())
    return None if root is None or not name else root / DIR / f"{safe(name)}.yaml"


def _empty(project):
    return {"schema": SCHEMA, "project": project or "", "announcement": {}, "purpose": "", "evaluation": [], "requirements": [], "guides": []}


def parse(text, project=None, strict=True):
    """YAML 글 → 정리한 문서 목적. strict 면 틀린 꼴은 ValueError, 아니면 쓸 수 있는 것만 남긴다."""
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
    out = _empty(project if project is not None else FG._s(data.get("project"), 120))
    an = data.get("announcement")
    if an is not None and not isinstance(an, dict):
        if strict:
            raise ValueError("announcement 는 「name · agency · date」 묶음입니다")
        an = {}
    out["announcement"] = {k: FG._s((an or {}).get(k), 200) for k in ("name", "agency", "date") if FG._s((an or {}).get(k), 200)}
    if data.get("purpose") is not None and not isinstance(data.get("purpose"), str) and strict:
        raise ValueError("purpose 는 글입니다")
    out["purpose"] = FG._long(data.get("purpose"), PURPOSE_MAX)

    def rows(key):
        raw = data.get(key)
        if raw is None:
            return []
        if not isinstance(raw, list):
            if strict:
                raise ValueError(f"{key} 는 목록입니다")
            return []
        if len(raw) > LIST_MAX and strict:
            raise ValueError(f"{key} 는 {LIST_MAX}개까지입니다")
        return raw[:LIST_MAX]
    for x in rows("evaluation"):
        t = FG._long(x.get("text") if isinstance(x, dict) else x, FG.GUIDE_MAX)
        if t and t not in out["evaluation"]:
            out["evaluation"].append(t)
        elif not t and strict:
            raise ValueError("evaluation 에 글이 빈 항목이 있습니다")
    for x in rows("requirements"):
        x = {"text": x} if isinstance(x, str) else x
        t = FG._long(x.get("text"), FG.GUIDE_MAX) if isinstance(x, dict) else ""
        if not t:
            if strict:
                raise ValueError("requirements 의 항목은 「text: … · source: …」 입니다")
            continue
        r = {"text": t}
        if FG._s(x.get("source"), FR.SOURCE_MAX):
            r["source"] = FG._s(x.get("source"), FR.SOURCE_MAX)
        if r not in out["requirements"]:
            out["requirements"].append(r)
    seen = set()
    for i, x in enumerate(rows("guides"), 1):
        x = {"text": x} if isinstance(x, str) else x
        t = FG._long(x.get("text"), FG.GUIDE_MAX) if isinstance(x, dict) else ""
        if not t:
            if strict:
                raise ValueError("guides 의 항목은 「text: … · targets: […]」 입니다")
            continue
        where = f"지침 {i}"
        tg = x.get("targets")
        if tg is not None and not isinstance(tg, list):
            if strict:
                raise ValueError(f"{where} 의 targets 는 목록입니다(없으면 문서 전체)")
            tg = []
        targets = [v for v in (FR._target(v, strict, where) for v in tg or ()) if v][:FR.TARGETS_MAX]
        if tg and not targets:
            continue   # 자리를 적었는데 못 읽음 — 문서 전체로 넓혀 읽지 않는다
        gid = str(x.get("id")) if isinstance(x.get("id"), (str, int)) and not isinstance(x.get("id"), bool) and FG.ID.match(str(x.get("id"))) else f"g{i}"
        if x.get("id") is not None and gid != str(x.get("id")) and strict:
            raise ValueError(f"{where} 의 id 는 영문 · 숫자 · . _ - 60자까지입니다")
        if gid in seen:
            if strict:
                raise ValueError(f"id 「{gid}」 가 두 번 나옵니다")
            continue
        seen.add(gid)
        out["guides"].append({"id": gid, "text": t, "targets": targets})
    return out


def _clean(d):
    out = {"schema": SCHEMA, "project": d.get("project") or ""}
    out["announcement"] = {k: (d.get("announcement") or {}).get(k, "") for k in ("name", "agency", "date")}
    out["purpose"] = d.get("purpose") or ""
    out["evaluation"] = list(d.get("evaluation") or ())
    out["requirements"] = [{k: r[k] for k in ("text", "source") if r.get(k)} for r in d.get("requirements") or ()]
    out["guides"] = [{"id": g["id"], "text": g["text"], **({"targets": [{k: t[k] for k in ("path", "table", "subtable", "field") if t.get(k)} for t in g["targets"]]} if g.get("targets") else {})}
                     for g in d.get("guides") or ()]
    return out


def dump(d):
    return HEADER.format(name=d.get("project") or "") + yaml.safe_dump(_clean(d), allow_unicode=True, sort_keys=False, width=4096, default_flow_style=False)


def read(project):
    """→ (정리한 문서 목적, 지금 글, sha1) — 파일이 없으면 (빈 것, None, "") · 못 읽는 파일이면 ValueError."""
    p = path_of(project)
    if p is None or not p.is_file():
        return _empty(project), None, ""
    text = p.read_bytes().decode("utf-8")
    return parse(text, project, strict=False), text, FG._sha1(text)


def load(project):
    """읽기만(없거나 못 읽으면 None)."""
    try:
        d, text, _ = read(project)
    except (ValueError, OSError):
        return None
    return d if text is not None else None


def save_text(project, text, *, expect=None):
    """YAML 글을 검사해 저장 → (정리한 것, sha1). expect = 읽었을 때의 sha1("" = 새 파일) · 다르면 form_guide_yaml.StaleVersion. 고치기 전 글은 `_purpose/_history/<이름>/` 에 남긴다."""
    text = text.replace("\r\n", "\n") if isinstance(text, str) else text
    d = parse(text, " ".join(str(project or "").split()), strict=True)
    p = path_of(project)
    if p is None:
        raise ValueError("프로젝트가 없거나 작업 저장이 꺼져 있습니다")
    with _LOCK:
        old = p.read_bytes().decode("utf-8") if p.is_file() else None
        if expect is not None and expect != (FG._sha1(old) if old is not None else ""):
            raise FG.StaleVersion("문서 목적이 그 사이 바뀌었습니다 — 다시 읽어 주세요")
        if old != text:
            p.parent.mkdir(parents=True, exist_ok=True)
            if old is not None:
                try:
                    h = p.parent / "_history" / p.stem
                    h.mkdir(parents=True, exist_ok=True)
                    (h / f"{time.strftime('%Y%m%d-%H%M%S')}-{FG._sha1(old)[:8]}.yaml").write_text(old, encoding="utf-8")
                except OSError:
                    pass
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_bytes(text.encode("utf-8"))
            os.replace(tmp, p)
    return d, FG._sha1(text)


def moved(old, new):
    """프로젝트 이름이 바뀜 — 파일을 새 이름의 자리로 옮기고 안의 project 를 고친다(새 자리에 이미 있으면 그대로 둔다). → 옮겼나. 못 옮겨도 예외를 내지 않는다."""
    try:
        a, b = path_of(old), path_of(new)
        if a is None or b is None or not a.is_file() or b.is_file():
            return False
        with _LOCK:
            d = parse(a.read_bytes().decode("utf-8"), None, strict=False)
            d["project"] = " ".join(str(new).split())
            b.write_bytes(dump(d).encode("utf-8"))
            os.replace(a, a.with_name(a.name + ".moved"))
        return True
    except (ValueError, OSError):
        return False


def removed(project):
    """프로젝트를 지움 — 파일을 `_purpose/_removed/` 로 옮긴다(지우지 않는다). → 옮겼나."""
    try:
        p = path_of(project)
        if p is None or not p.is_file():
            return False
        with _LOCK:
            d = p.parent / "_removed"
            d.mkdir(parents=True, exist_ok=True)
            os.replace(p, d / f"{p.stem}-{time.strftime('%Y%m%d-%H%M%S')}.yaml")
        return True
    except OSError:
        return False


def doc_guides(d):
    """문서 전체에 닿는 것 → 지침 목록 [{src "purpose", kind, text, source?}] — 목적 · 평가 관점 · 요구 사항 · targets 없는 프로젝트 지침(이 차례)."""
    if not d:
        return []
    an = d.get("announcement") or {}
    name = " · ".join(x for x in (an.get("name"), an.get("agency"), an.get("date")) if x)
    out = []
    if d.get("purpose"):
        out.append({"src": "purpose", "kind": KINDS["purpose"], "text": d["purpose"], **({"source": name} if name else {})})
    out += [{"src": "purpose", "kind": KINDS["evaluation"], "text": t} for t in d.get("evaluation") or ()]
    out += [{"src": "purpose", "kind": KINDS["requirement"], "text": r["text"], **({"source": r["source"]} if r.get("source") else {})} for r in d.get("requirements") or ()]
    out += [{"src": "purpose", "kind": KINDS["guide"], "text": g["text"], "rule": g["id"]} for g in d.get("guides") or () if not g.get("targets")]
    return out


def locate(d, places, blocks=None):
    """문서 목적 d 를 지금 문서의 자리에 이은 것 → {"heads", "tables", "doc"[문서 전체], "links", "unmatched"}(form_rules.locate 꼴 — targets 있는 프로젝트 지침만 자리에)."""
    got = FR.locate([g for g in (d or {}).get("guides") or () if g.get("targets")], places, blocks, src="purpose", kind=KINDS["guide"])
    got["doc"] = doc_guides(d)
    return got

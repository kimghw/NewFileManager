"""지침 설정 페이지 `/guides` 의 끝점(spec_양식작성 ② §5-10) — server.py 가 include 한다. 화면 = app/static/guides.html · guides.js · guides.css.
2026-11-26 사용자 "그리고 설정페이지를 두고.. 이 내용들을 확인할 수 있도록 해줘, 지침들을 판단지침이나... 템플릿/양식 별로로" · "결국에는 사람이 지침을 확인하고 관리하기 편하도록".

**읽기만 하는 목록 끝점 둘**이다 — 새 저장 길을 만들지 않는다. 고치기는 그 글마다 이미 있는 끝점으로 화면이 바로 부른다(응답의 `save` · `reset` 이 그 주소를 적어 준다):
판단 지침 md = `PUT · DELETE /api/agents/{에이전트}/prompt/merge/{이름}`(prompt_texts 사본) · 헤딩 지침 = `/api/headings/guides/{이름}` · 서식 정리 스킬 = `/api/outline/agent/skills/{키}` · 테마 = `/api/form-themes/{id}/yaml` ·
양식 정보 = `/api/headings/forms/{키}` · 양식 지침 = `/api/form-guides/{키}/yaml` · 규정 = `/api/form-rules/{키}/yaml` · 문서 목적 = `/api/purpose/yaml?project=`(app/purpose_yaml_api.py).

- `GET /guides` → 따로 선 페이지(새 탭 — `/agents` · `/workflow` 와 같은 꼴). `#judgment/<글 id>` · `#forms/<양식 키>` 로 그 화면이 바로 열린다.
- `GET /api/guides-page/judgment` → {groups[{key, name}], items[{id, kind, group, name, title, lang, source, text(지금 쓰는 글), default(기본본 | null), custom, version,
  readers[{id, no, name, used[{job, name, stage, step, stepName}]}], save{url, version(bool), name?}, reset{url, version(bool)} | null}]} —
  글마다 **읽는 에이전트**(agents.AGENTS 의 parts)와 **그 에이전트가 도는 워크플로우 · 단계**(워크플로우 등록부의 줄 `agents`).
- `GET /api/guides-page/forms` → {dir, forms[{key, name, broken, md{size, updated}, guide{exists, broken, doc}, rules{exists, broken, doc}, theme{id, name} | null,
  projects[{name, works, purpose{exists, purpose, evaluation, requirements, guides}}]}], loose[양식을 정하지 못한 프로젝트 — 같은 꼴]}."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter()
STATIC = Path(__file__).with_name("static")
VERSIONED = ("style.css", "agents.css", "guides.css", "guides.js")   # 주소에 수정 시각을 붙이는 파일(agents_api 와 같은 규칙)
GROUPS = (("merge", "판단 지침 — 이관 · 취합 · 양식 작성 · 검증"), ("heading", "헤딩 지침 — 헤딩 · 표 판정"), ("skill", "템플릿 서식 정리 스킬"), ("theme", "양식 테마 — 테이블 타입 · 구분 기준 타입 · 템플릿"))
THEME_PART = ("merge", "writing_guidance")   # 테마 YAML 을 읽는 에이전트 = 작성 지침 보완(그 판단 지침을 읽는 에이전트 — writing_guidance_api 가 form_themes.brief 를 자료로 싣는다): 등록부의 parts 에 테마가 따로 없어 이 짝으로 찾는다


@router.get("/guides")
def guides_page():
    """지침 설정 페이지 — 따로 선 페이지(문서 화면과 다른 탭)."""
    html = (STATIC / "guides.html").read_text(encoding="utf-8")
    for name in VERSIONED:
        html = html.replace(f'"/static/{name}"', f'"/static/{name}?v={int((STATIC / name).stat().st_mtime)}"')
    return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})


def _who():
    """→ (글 (종류, 이름) → 읽는 에이전트 id 들, 에이전트 id → {id, no, name, used[…]})."""
    from app import agents as A
    from app import workflow
    readers = {}
    for a in A.AGENTS:
        for part in a.get("parts") or ():
            readers.setdefault((part[0], part[1] if len(part) > 1 else ""), []).append(a["id"])
    used = {}
    for t in workflow.listing()["tasks"]:   # 화면으로 나가는 문(고친 도구 이름 · 조립한 워크플로우까지)
        name = t.get("name") or A.JOB_NAMES.get(t["job"]) or t["job"]
        for g in t.get("stages") or ():
            for s in g.get("steps") or ():
                for a in s.get("agents") or ():
                    aid = a.get("id") if isinstance(a, dict) else a
                    row = {"job": t["job"], "name": name, "stage": " ".join(str(x) for x in (g.get("no"), g.get("name")) if x), "step": s.get("key"), "stepName": s.get("name") or s.get("key")}
                    if row not in used.setdefault(aid, []):
                        used[aid].append(row)
    rows = {a["id"]: {"id": a["id"], "no": a.get("no") or "", "name": a.get("name") or a["id"], "used": used.get(a["id"], [])} for a in A.listing()["agents"]}
    return readers, rows


@router.get("/api/guides-page/judgment")
def judgment():
    from app import form_themes as T
    from app import heading_guides, job_prompts, merge_guides, prompt_texts, tpl_agent
    readers, rows = _who()
    who = lambda key: [rows[i] for i in readers.get(key, ()) if i in rows]  # noqa: E731
    items = []
    d = merge_guides.guides_dir()
    for p in sorted(d.glob("*.md")) if d is not None and d.is_dir() else ():
        g = merge_guides.get(p.stem)
        if g is None:
            continue
        row = prompt_texts.read("merge", p.stem)
        try:
            default = job_prompts.body(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            default = None
        mine = who(("merge", p.stem))
        url = f"/api/agents/{mine[0]['id']}/prompt/merge/{p.stem}" if mine else None   # 고치는 길 = 에이전트 설정의 프롬프트 사본(그 글을 읽는 에이전트의 것 — 사본은 글마다 하나라 어느 에이전트로 고쳐도 같다)
        items.append({"id": f"merge:{p.stem}", "kind": "merge", "name": p.stem, "title": g["title"], "lang": "md", "source": f"app/merge_guides_default/{p.name}",
                      "text": merge_guides.body(g), "default": default, "custom": row.get("text") is not None, "version": row.get("version", 0), "readers": mine,
                      "save": {"url": url, "version": True} if url else None, "reset": {"url": url, "version": True} if url else None})
    for name in heading_guides.NAMES:
        g = heading_guides.get(name)
        url = f"/api/headings/guides/{name}"
        items.append({"id": f"heading:{name}", "kind": "heading", "name": name, "title": g["title"], "lang": "md", "source": f"app/heading_guides_default/{name}.md", "text": g["text"], "default": g["default"],
                      "custom": g["custom"], "version": g["version"], "readers": who(("heading", name)), "save": {"url": url, "version": True}, "reset": {"url": url, "version": False}})
    base = tpl_agent._builtin()
    for s in tpl_agent.skills():
        sk = tpl_agent.skill(s["key"])
        url = f"/api/outline/agent/skills/{s['key']}"
        items.append({"id": f"skill:{s['key']}", "kind": "skill", "name": s["key"], "title": sk["name"], "lang": "md", "source": f"app/tpl_agent_default/{s['key']}.md" if sk["builtin"] else "내가 만든 스킬",
                      "text": sk["text"], "default": base[s["key"]][1] if s["key"] in base else None, "custom": sk["custom"], "version": sk["version"], "readers": who(("skill", "")),
                      "save": {"url": url, "version": True, "name": sk["name"]}, "reset": {"url": url, "version": False} if sk["builtin"] and sk["custom"] else None})
    for t in T.listing():
        url = f"/api/form-themes/{t['id']}/yaml"
        p = Path(T.__file__).with_name("form_themes_default") / f"{t['id']}.yaml"
        try:
            default = p.read_text(encoding="utf-8") if t.get("default") and p.is_file() else None
        except (OSError, UnicodeDecodeError):
            default = None
        items.append({"id": f"theme:{t['id']}", "kind": "theme", "name": t["id"], "title": t["name"], "lang": "yaml", "source": f"app/form_themes_default/{t['id']}.yaml" if t.get("default") else "이 PC 의 테마 사본",
                      "text": T.text(t["id"]) or "", "default": default, "custom": bool(t.get("custom")), "version": 0, "readers": who(THEME_PART),
                      "save": {"url": url, "version": False}, "reset": {"url": url, "version": False} if t.get("custom") else None})
    return {"groups": [{"key": k, "name": n} for k, n in GROUPS], "items": items}


def _purpose(project, n):
    from app import purpose_yaml as PY
    d = PY.load(project)
    return {"name": project, "works": n, "purpose": {"exists": d is not None, "purpose": bool((d or {}).get("purpose")), "evaluation": len((d or {}).get("evaluation") or ()),
                                                     "requirements": len((d or {}).get("requirements") or ()), "guides": len((d or {}).get("guides") or ())}}


def projects_by_form():
    """작업들의 프로젝트를 그 문서의 양식(파일 이름 · 사람이 고른 양식)마다 모은다 → {양식 키 | "": {프로젝트 이름: 작업 수}}. 계정의 작업 뿌리만 읽는다(works.list_works)."""
    from app import heading_forms as HF
    from app import works
    out = {}
    for w in works.list_works():
        task = w.get("task") if isinstance(w.get("task"), dict) else {}
        project = " ".join(str(task.get("project") or "").split())
        if not project:
            continue
        try:
            f = HF.match(w.get("name") or "", None, HF.choice(w.get("id")))
        except Exception:   # noqa: BLE001 — 양식 판정은 덤이다
            f = None
        by = out.setdefault(f["key"] if f else "", {})
        by[project] = by.get(project, 0) + 1
    return out


@router.get("/api/guides-page/forms")
def forms():
    from app import form_guide_yaml as FG
    from app import form_rules as FR
    from app import form_themes as T
    from app import heading_forms as HF
    themes = {t["id"]: t["name"] for t in T.listing()}
    by = projects_by_form()

    def side(read, key):
        try:
            d, text, _ = read(key)
            return {"exists": text is not None, "broken": "", "doc": d}
        except (ValueError, OSError) as e:
            return {"exists": True, "broken": str(e), "doc": None}
    out = []
    for f in HF.listing():
        guide = side(FG.read, f["key"])
        tid = (guide["doc"] or {}).get("theme") or ""
        out.append({"key": f["key"], "name": f["name"], "broken": f.get("broken") or "", "md": {"size": f.get("size"), "updated": f.get("updated")}, "guide": guide, "rules": side(FR.read, f["key"]),
                    "theme": {"id": tid, "name": themes.get(tid) or tid} if tid else None, "projects": [_purpose(p, n) for p, n in sorted((by.get(f["key"]) or {}).items())]})
    known = {f["key"] for f in HF.listing()}
    loose = {}
    for key, ps in by.items():
        if key not in known:
            for p, n in ps.items():
                loose[p] = loose.get(p, 0) + n
    from app import purpose_yaml_api
    seen = {p for ps in by.values() for p in ps}
    for p in purpose_yaml_api.known_projects() - seen:   # 문서가 아직 없는 프로젝트(기록만) — 문서를 올리기 전에도 문서 목적을 적을 수 있게
        loose.setdefault(p, 0)
    d = HF.forms_dir()
    return {"dir": str(d) if d is not None else None, "forms": out, "loose": [_purpose(p, n) for p, n in sorted(loose.items())]}

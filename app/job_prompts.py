"""할 일 프롬프트(spec_작업 ② §13): 할 일(`task.job`)마다 md 하나 — 그 일의 전제·기준을 사용자가 말한 대로 적어 두고, 그 할 일에서 도는 에이전트가 먼저 읽는다
(사용자 2026-11-11 "명시적으로 프롬프트를 저장하고 에이전트가 실행할떄 이 작업에서는 이 내용을 참조할 수 있도록해").

- 파일: `<저장소>/jobs/<할 일 키>.md`(env `NFM_JOBS` 가 폴더, `off`·`0` = 없음). 파일 하나가 원본 — 코드 에이전트(CLAUDE.md 가 가리킴)와 앱의 LLM 호출이 같은 글을 읽는다.
  부를 때마다 읽는다(고친 글이 다음 실행에 바로).
- 첫 「# 」 줄 = 제목(「— 」 뒤가 표시 이름). 그 줄과 HTML 주석(`<!-- … -->` — 사람·코드 에이전트만 보는 메모)을 뺀 나머지가 LLM 프롬프트에 들어간다(`body`).
- 읽는 곳: 자리 연결 LLM 검토(`merge_llm` — 계약 바로 뒤 한 절, `part`) · 표 채우기(`tables_api.table_fill_propose` — `part(p, table_fill.JOB_NOTE)`, spec_헤딩_추출 ② §18).
- 조립한 워크플로우(app/custom_tasks.py 의 키 — spec_워크플로우 ② §14)는 조립할 때 적은 글, 비웠으면 틀이 같은 붙박이의 파일(`custom_tasks.BASE`) + 그 글 맨 앞의 한 줄
  (고른 단계 · 「전제의 단계 설명 가운데 고르지 않은 단계는 하지 않는다」 — `workflow.picked_line` · ② §15)."""
import hashlib
import os
import re
from pathlib import Path

from app import works

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "jobs"
KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")   # 할 일 키(server.TASK["job"] 의 값) = 파일 이름
TEXT_MAX = 20_000
_COMMENT = re.compile(r"<!--.*?-->[ \t]*\n?", re.S)
_TITLE = re.compile(r"\A\s*#[ \t]+([^\n]*)\n?")

# 프롬프트에 붙일 때의 머리 문장 — 할 일의 전제는 호출마다 다른 계약(무엇을 고르고 어떤 꼴로 답하는지)보다 앞선 바탕이다.
NOTE = ("아래는 **이 작업의 할 일**에 대해 사용자가 직접 정해 저장해 둔 전제·기준입니다. 어느 문서가 기준(원본)이고 어느 문서가 목적인지, 무엇을 넣고 무엇을 만들지 않는지는 "
        "이 글을 먼저 따릅니다 — 위 판단 기준과 어긋나 보이면 이 글의 전제에 맞게 판단합니다. 답의 꼴과 「입력에 있는 key·id 만」 은 위 계약 그대로입니다.")


def jobs_dir():
    """할 일 프롬프트 폴더 Path | None(끔). env NFM_JOBS 가 폴더, off·0 이면 None, 없으면 저장소의 jobs/."""
    env = os.environ.get("NFM_JOBS", "").strip()
    if env.lower() in ("off", "0"):
        return None
    return Path(env) if env else DEFAULT_DIR


def body(text):
    """프롬프트에 넣는 글 — HTML 주석과 첫 제목 줄을 뺀 나머지(뺀 자리에 남은 빈 줄은 하나로)."""
    return re.sub(r"\n{3,}", "\n\n", _TITLE.sub("", _COMMENT.sub("", text or ""), count=1)).strip()


def _lead(text, line):
    """글의 맨 앞(첫 줄이 제목이면 그 뒤)에 한 줄을 넣는다 — body() 가 제목 · 주석을 뺀 뒤 그 줄이 맨 앞에 온다. 첫 줄이 제목이 아니면 끝에 붙인다(제목 읽기를 흐트리지 않게)."""
    m = _TITLE.match(text)
    return f"{text[:m.end()]}\n{line}\n{text[m.end():]}" if m else f"{text.rstrip()}\n\n{line}\n"


def get(job):
    """할 일 키 → {job, name, sha1, text, path} | None(폴더 끔 · 모르는 꼴의 키 · 파일 없음 · 못 읽음 · 너무 긴 글)."""
    d = jobs_dir()
    if d is None or not isinstance(job, str) or not KEY.fullmatch(job):
        return None
    from app import custom_tasks   # 가벼운 모듈
    custom = custom_tasks.get(job)   # 화면에서 조립한 TASK(spec_워크플로우 ② §14) — 전제는 조립할 때 적은 글이고, 비웠으면 틀이 같은 붙박이 TASK(이관)의 전제 파일을 쓴다
    if custom is not None:
        if custom["premise"]:
            text = custom["premise"]
            return {"job": job, "name": custom["name"], "sha1": hashlib.sha1(text.encode("utf-8")).hexdigest(), "text": text, "path": ""}
        base = get(custom_tasks.BASE)
        if not base:
            return None
        # 물려받은 전제는 붙박이 이관의 네 단계를 모두 적고 있다 — 고른 단계와 「고르지 않은 단계는 하지 않는다」 한 줄을 그 글의 맨 앞(제목 줄 뒤)에 넣는다(spec_워크플로우 ② §15)
        from app import workflow   # 단계 이름의 원본(STAGE_MODULES) — 이 모듈을 가져오지 않는다
        text = _lead(base["text"], workflow.picked_line(custom))
        return {**base, "job": job, "name": f"{custom['name']}({base['name']}의 전제)", "sha1": hashlib.sha1(text.encode("utf-8")).hexdigest(), "text": text}
    p = d / f"{job}.md"
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if len(text) > TEXT_MAX:
        return None
    m = _TITLE.match(_COMMENT.sub("", text))
    name = (m.group(1).split("—", 1)[-1].strip() if m else "") or job
    return {"job": job, "name": name, "sha1": hashlib.sha1(text.encode("utf-8")).hexdigest(), "text": text, "path": str(p)}


def for_work(wid):
    """작업(문서)이 고른 할 일(`work.json` task.job — spec_작업 ② §10)의 프롬프트 | None."""
    return get(((works.work(wid) or {}).get("task") or {}).get("job") or "")


def part(p, note=NOTE):
    """get() 결과 | None → LLM 프롬프트에 붙일 절 글 | ""(프롬프트 없음 · 보낼 글 없음 — 프롬프트는 전과 같다)."""
    text = body(p.get("text")) if p else ""
    return f"\n\n## 할 일 — {p['name']} (이 작업의 전제 — 먼저 따른다)\n{note}\n\n{text}" if text else ""


def brief(p):
    """실제로 보낸 프롬프트의 기록 꼴 {job, name, sha1} | None(보낸 글 없음)."""
    return {k: p[k] for k in ("job", "name", "sha1")} if part(p) else None

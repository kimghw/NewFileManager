"""병합 LLM 지침(spec_병합 ② §4 「지침」): 병합에서 도는 LLM 검토마다 md 하나 — **무엇을 같은 자리로 보는가**(판단 기준)를 코드 밖에 두고, 사람이 화면에서 읽고 파일을 고친다
(사용자 2026-11-12 "이 내용 도 LLM 검토 단계에서 검토하도록 지침으로 들어가 있어야함" · "각 LLM이 검토나 작업할때 '지침' 이나 프롬프트를 확인할 수 있으면 좋겠어").

- 기본 파일: `app/merge_guides_default/<이름>.md`(env `NFM_MERGE_GUIDES` 가 폴더, `off`·`0` = 없음). 실제 호출과 보기는 같은 글을 읽으며, 화면에서 고친 사본이 있으면 그 본문을 쓴다.
  지금 있는 것 = `links`(자리 연결 LLM 검토 — 묶음 짝·표 짝·서식). 다른 병합 검토(취합 등)는 이 폴더에 파일을 더한다.
- 첫 「# 」 줄 = 제목(「— 」 뒤가 표시 이름). 그 줄과 HTML 주석을 뺀 나머지가 프롬프트에 들어간다(`job_prompts.body` 와 같은 규칙).
- 계약(답의 꼴·자료 설명 — 코드의 CONTRACT)은 여기 두지 않는다: 답을 검증하는 코드와 한 몸이라 글만 바꾸면 어긋난다. 지침이 없으면(파일 없음·끔) 프롬프트에 지침 절이 없다."""
import hashlib
import os
import re
from pathlib import Path

from app import job_prompts, prompt_texts

DEFAULT_DIR = Path(__file__).with_name("merge_guides_default")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
TEXT_MAX = 20_000

# 프롬프트에 붙일 때의 머리 문장 — 계약(자료·답의 꼴) 다음, 할 일 프롬프트(이 작업의 전제) 앞.
NOTE = ("아래는 이 검토의 **판단 기준**입니다(사용자가 관리하는 지침). 무엇을 같은 자리·같은 표로 보는지는 이 글을 따릅니다. "
        "답의 꼴과 「입력에 있는 key 만」 은 위 계약 그대로입니다.")


def guides_dir():
    """지침 폴더 Path | None(끔). env NFM_MERGE_GUIDES 가 폴더, off·0 이면 None, 없으면 app/merge_guides_default/."""
    env = os.environ.get("NFM_MERGE_GUIDES", "").strip()
    if env.lower() in ("off", "0"):
        return None
    return Path(env) if env else DEFAULT_DIR


def get(name):
    """지침 이름 → {name, title, sha1, text, path} | None(폴더 끔 · 모르는 꼴의 이름 · 파일 없음 · 못 읽음 · 너무 긴 글)."""
    d = guides_dir()
    if d is None or not isinstance(name, str) or not NAME.fullmatch(name):
        return None
    p = d / f"{name}.md"
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if len(text) > TEXT_MAX:
        return None
    m = job_prompts._TITLE.match(job_prompts._COMMENT.sub("", text))
    title = (m.group(1).split("—", 1)[-1].strip() if m else "") or name
    default = {"name": name, "title": title, "sha1": hashlib.sha1(text.encode("utf-8")).hexdigest(), "text": text, "path": str(p)}
    return prompt_texts.file_content("merge", name, default, title)


def body(g):
    """프롬프트에 넣는 글(주석·제목 줄 뺌) | ""."""
    return job_prompts.body(g.get("text")) if g else ""


def part(g, note=NOTE):
    """get() 결과 | None → LLM 프롬프트에 붙일 절 글 | ""(지침 없음 — 프롬프트는 지침 절 없이)."""
    text = body(g)
    return f"\n\n## 판단 지침 — {g['title']}\n{note}\n\n{text}" if text else ""


def brief(g):
    """실제로 보낸 지침의 기록 꼴 {name, title, sha1} | None(보낸 글 없음)."""
    return {k: g[k] for k in ("name", "title", "sha1")} if part(g) else None

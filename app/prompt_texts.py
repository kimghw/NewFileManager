"""프롬프트 원문을 고친 사본과 실제 호출에서 읽는 글.

저장 위치는 에이전트 설정 파일 옆 agent_prompts/<종류>/<이름>.json 이다.
NFM_AGENT_PROMPTS로 폴더를 지정하거나 off로 메모리에만 둘 수 있다.
"""
import hashlib
import importlib
import os
import threading
from pathlib import Path

from app import agent_settings, works

TEXT_MAX = 20_000
_LOCK = threading.RLock()
_MEMORY = {}


def _path(kind, name):
    folder = os.environ.get("NFM_AGENT_PROMPTS", "").strip()
    if folder.lower() in ("off", "0"):
        return None
    if folder:
        root = Path(folder)
    else:
        settings = agent_settings.path()
        if settings is None:
            return None
        root = settings.parent / "agent_prompts"
    # 키는 등록부의 계약·지침 이름 또는 실제 워크플로우 키다.
    return root / kind / (name + ".json")


def read(kind, name):
    with _LOCK:
        path = _path(kind, name)
        if path is None:
            return _MEMORY.get((kind, name), {})
        row = works._read_json(path) if path.is_file() else None
        if not isinstance(row, dict) or type(row.get("version")) is not int or row["version"] < 0:
            return {}
        if "text" in row and (not isinstance(row["text"], str) or not row["text"].strip() or len(row["text"]) > TEXT_MAX):
            return {"version": row["version"]}
        return row


def save(kind, name, text, version):
    """None이면 기본 글을 다시 쓴다. 복구해도 판 번호는 이어진다."""
    if type(version) is not int or version < 0:
        raise ValueError("읽은 프롬프트의 판 번호가 필요합니다")
    if text is not None:
        if not isinstance(text, str) or not text.strip() or len(text) > TEXT_MAX:
            raise ValueError(f"프롬프트에는 1자 이상 {TEXT_MAX:,}자 이하의 글을 적으세요")
        text = text.replace("\r\n", "\n").strip()
    with _LOCK:
        if read(kind, name).get("version", 0) != version:
            raise agent_settings.Stale("프롬프트가 그 사이에 바뀌었습니다. 다시 읽어 주세요")
        row = {"version": version + 1}
        if text is not None:
            row["text"] = text
        path = _path(kind, name)
        if path is None:
            _MEMORY[kind, name] = row
        else:
            works._write_json(path, row)
    return row


def contract(module, symbol="CONTRACT"):
    row = read("contract", f"{module}.{symbol}")
    return row.get("text") or getattr(importlib.import_module(module), symbol)


def file_content(kind, name, default, title):
    """원본 파일에서 읽은 제목·경로는 보존한다. 보내는 글과 지문은 실제 본문으로 만든다."""
    text = read(kind, name).get("text")
    if text is None:
        return default
    raw = f"# {title}\n\n{text}"
    return {**default, "text": raw, "sha1": hashlib.sha1(raw.encode("utf-8")).hexdigest()}

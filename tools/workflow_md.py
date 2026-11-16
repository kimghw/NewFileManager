"""workflow.md · TASK 문서 다시 만들기(spec_워크플로우 ② §8·§10) — 워크플로우 등록부 `app/workflow.py` 를 글로 옮겨 저장소 루트의 `workflow.md`(전체 지도)와
`tasks/<TASK 키>.md`(TASK 문서 — 그 TASK 의 세부: 시작 점검 · 단계마다 조건)에 쓴다.
등록부(TASK · 단계 · 시작 점검 · 단계 조건 · 모듈 · 에이전트)나 `task_catalog.js` 의 TASK 이름·단계 이름, 에이전트 등록부의 번호·이름, `jobs/` 의 파일을 고친 뒤 돌린다 — 안 돌리면 `tests/test_workflow.py` 가 떨어진다.

    python -X utf8 tools/workflow_md.py            # 다시 만든다(같으면 그대로 둔다)
    python -X utf8 tools/workflow_md.py --check    # 쓰지 않고 견주기만 — 다르면 종료 코드 1
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import workflow  # noqa: E402


def main():
    """workflow.md(전체 지도)와 tasks/<TASK 키>.md(TASK 문서 — ② §10)를 함께 본다. 하나라도 다르면 --check 는 1."""
    check, code = "--check" in sys.argv[1:], 0
    docs = {workflow.MD: workflow.markdown(), **workflow.task_docs()}
    for path, want in docs.items():
        name = path.relative_to(workflow.ROOT).as_posix()
        have = path.read_text(encoding="utf-8") if path.is_file() else None
        if have == want:
            print(f"{name}: 등록부와 같음({len(want.splitlines())}줄)")
        elif check:
            print(f"{name}: 등록부와 다름 — python -X utf8 tools/workflow_md.py 로 다시 만드세요")
            code = 1
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(want, encoding="utf-8", newline="\n")
            print(f"{name}: {'새로 만듦' if have is None else '다시 만듦'}({len(want.splitlines())}줄)")
    for extra in sorted(set(workflow.TASK_DIR.glob("*.md")) - set(docs)):   # 등록부에 없는 TASK 의 문서 — 지우지 않고 알린다(시험이 떨어진다)
        print(f"{extra.relative_to(workflow.ROOT).as_posix()}: 등록부에 없는 TASK 의 문서 — 지워 주세요")
        code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())

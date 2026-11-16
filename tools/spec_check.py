"""사양 관리 점검 — 문서의 깨진 링크 · 코드가 가리키는 사양 절이 사양서에 있는지(spec_워크플로우 ② §11 「사양 관리 점검」).

    python -X utf8 tools/spec_check.py      # 찾은 것을 적고, 있으면 1 로 끝난다

읽기만 한다(아무것도 고치지 않는다). 같은 것을 tests/test_spec_check.py 가 본다.
- links(root)    → [(문서, 가리킨 곳)] — 관리 문서의 상대 링크 가운데 파일을 가리키는데 그 파일이 없는 것.
- sections(root) → ([(사양서, 절 번호, 절 이름, [코드 파일])], [(사양서 이름, [코드 파일])])
                   — 코드의 글이 가리키는 절 이름이 그 사양서에 없는 것 · 가리키는 사양서 파일이 없는 것.
예외는 아래 LEGACY · KNOWN 에 까닭과 함께 적는다.
"""
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

# 옛 프로젝트 FileMergeManager 의 사양서 — 이 저장소 spec/ 에는 없다(코드는 그 프로젝트에서 왔고 주석은 그대로 둔다: 2026-11-16 사용자 답 「링크만 바로잡기」)
LEGACY = frozenset({"spec_구분_초기화", "spec_매직브러쉬", "spec_서식", "spec_왕복_어댑터", "spec_웹UI", "spec_표_분류", "spec_표_서식_정리", "spec_표_편집"})
# (사양서, 절 이름) → 까닭 — 이름이 이 저장소의 그 사양서에 없어도 되는 것
KNOWN = {("spec_병합", "렌더 하드닝"): "FileMergeManager 의 spec_병합 ② §2-4 — 이 저장소의 spec_병합 과 다른 문서"}

DOC_GLOBS = ("spec/*.md", "jobs/*.md", "tasks/*.md", "references/*.md", "design.md", "CLAUDE.md", "workflow.md")
CODE_GLOBS = ("app/*.py", "app/static/*.js", "app/static/*.html", "app/static/*.css", "app/static/share/*.js", "app/static/share/*.html", "app/static/share/*.css", "tools/*.py", "tests/*.py")
SELF = frozenset({"tools/spec_check.py", "tests/test_spec_check.py"})  # 이 검사의 글(예 · 예외 목록)은 보지 않는다
LOCAL = ("artifacts",)  # 깃이 추적하지 않는 이 PC 의 작업 기록 — 새로 받은 저장소에는 없으므로 링크를 보지 않는다(저장소 밖을 가리키는 링크도 같다)

LINK = re.compile(r"\]\(([^)\s]+)\)")
FILE_LIKE = re.compile(r"(/|\.[A-Za-z0-9]{1,5})$")  # 파일·폴더를 가리키는 꼴만(「§8-5」·「≤600」 같은 괄호 글은 링크가 아니다)
NAME = r"spec_[0-9A-Za-z_]*[가-힣][0-9A-Za-z가-힣_]*"  # 사양서 이름에는 한글이 든다(spec_of_block 같은 코드 이름과 가른다)
CITE = re.compile(rf"({NAME})(?:\.md)?\s*(?:②\s*)?§\s*([0-9]+(?:-[0-9]+)?)[^「\n]{{0,3}}「([^」\n]{{2,40}})」")
MENTION = re.compile(NAME)


def _squeeze(s):
    return re.sub(r"\s+", "", s)


def _files(root, globs):
    return sorted({p for g in globs for p in Path(root).glob(g) if p.is_file()})


def links(root=ROOT):
    """관리 문서의 깨진 상대 링크 → [(문서 경로, 가리킨 곳)] — 저장소 안의 추적하는 자리를 가리키는 것만 본다."""
    root, bad = Path(root).resolve(), []
    for doc in _files(root, DOC_GLOBS):
        for m in LINK.finditer(doc.read_text(encoding="utf-8")):
            target = unquote(m.group(1).split("#", 1)[0])
            if not target or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target) or not FILE_LIKE.search(target):
                continue  # 문서 안 자리 · 바깥 주소 · 파일 꼴이 아님
            path = (doc.parent / target).resolve()
            if root not in path.parents or path.relative_to(root).parts[0] in LOCAL:
                continue  # 저장소 밖(옛 프로젝트 사양서 …) · 추적하지 않는 작업 기록 — 이 저장소만으로는 볼 수 없다
            if not path.exists():
                bad.append((doc.relative_to(root).as_posix(), m.group(1)))
    return bad


def _known_name(token, names):
    """코드의 글에서 읽은 낱말 → 아는 사양서 이름(뒤에 조사가 붙었으면 뗀다) | None."""
    if token in names:
        return token
    return next((n for n in sorted(names, key=len, reverse=True) if token.startswith(n)), None)


def sections(root=ROOT):
    """코드의 글이 가리키는 사양 → (없는 절 [(사양서, 절 번호, 절 이름, [코드 파일])], 없는 사양서 [(이름, [코드 파일])])."""
    root = Path(root)
    specs = {p.stem: _squeeze(p.read_text(encoding="utf-8")) for p in _files(root, ("spec/*.md",))}
    names = set(specs) | LEGACY
    no_sec, no_spec = {}, {}
    for code in _files(root, CODE_GLOBS):
        rel = code.relative_to(root).as_posix()
        if rel in SELF:
            continue
        try:
            text = code.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for m in MENTION.finditer(text):
            if _known_name(m.group(0).rstrip("_"), names) is None:
                no_spec.setdefault(m.group(0), set()).add(rel)
        for m in CITE.finditer(text):
            name, title = _known_name(m.group(1), names), m.group(3)
            if name not in specs or "<" in title or (name, title) in KNOWN:
                continue  # 옛 프로젝트 사양서 · 이름 꼴을 적은 글 · 적어 둔 예외
            if _squeeze(title) not in specs[name]:
                no_sec.setdefault((name, m.group(2), title), set()).add(rel)
    return ([(n, s, t, sorted(fs)) for (n, s, t), fs in sorted(no_sec.items())], [(n, sorted(fs)) for n, fs in sorted(no_spec.items())])


def main():
    bad_links = links()
    no_sec, no_spec = sections()
    for doc, target in bad_links:
        print(f"깨진 링크: {doc} → {target}")
    for name, sec, title, files in no_sec:
        print(f"없는 절: {name} ② §{sec} 「{title}」 ← {', '.join(files)}")
    for name, files in no_spec:
        print(f"없는 사양서: {name} ← {', '.join(files)}")
    n = len(bad_links) + len(no_sec) + len(no_spec)
    print("사양 관리 점검 — 문제 없음" if not n else f"사양 관리 점검 — {n}건(깨진 링크 {len(bad_links)} · 없는 절 {len(no_sec)} · 없는 사양서 {len(no_spec)})")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())

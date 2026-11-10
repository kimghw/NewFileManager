"""블록 id 자리표 — 어댑터(hwpx_doc·docx_doc)의 블록 id 는 처음 만난 차례로 붙어(_id) 고친 문서를 save() 해 다시 열면 달라진다. 작업 저장(spec_작업 ② §5)이
저장본을 다시 열 때 같은 id 를 되붙이게, XML 부분마다 요소 차례(root.iter()) ↔ id 를 적어 둔다. save() 는 트리를 그대로 쓰므로 다시 읽은 트리의 요소 차례가 같다."""


def state(roots, rev, n):
    """{"n": 번호표, "parts": {부분: {"count": 요소 수, "ids": [[차례, id], …]}}} — roots = {부분 이름: 루트 요소}, rev = {요소: id}."""
    parts = {}
    for name, root in roots.items():
        ids, k = [], -1
        for k, el in enumerate(root.iter()):
            i = rev.get(el)
            if i is not None:
                ids.append([k, i])
        if ids:
            parts[name] = {"count": k + 1, "ids": ids}
    return {"n": n, "parts": parts}


def adopt(root_of, st):
    """state 를 다시 연 문서에 맞춘다 — root_of(부분 이름) -> 루트 | None. 부분이 없거나 요소 수가 다르면 None(옛 id 를 못 믿음), 맞으면 (ids, rev, n)."""
    ids, rev = {}, {}
    for name, part in st["parts"].items():
        root = root_of(name)
        els = list(root.iter()) if root is not None else []
        if len(els) != part["count"]:
            return None
        for k, i in part["ids"]:
            ids[i], rev[els[k]] = els[k], i
    return ids, rev, st["n"]

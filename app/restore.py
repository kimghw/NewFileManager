"""문단 원본 복원(spec_hwpx_웹편집 ② §2 「되돌리기」) — 글만 다시 쓰지 않고 원본 문단의 XML(런 안 글 요소·자동 번호 컨트롤·줄 배치 캐시)을
되돌린다. astra 검토(2026-11-08): 원래 글을 다시 PATCH 하면 linesegarray 가 지워진 채 남아 「원본 그대로」가 거짓이 된다.

set_text 가 바꾸는 것은 문단의 런 안 비개체 자식(hp:t·hp:ctrl autoNum)과 문단의 linesegarray 뿐이다 — 표·그림 등 개체는 손대지 않는다.
그래서 런마다 원본 자식을 깊은 복사로 되놓되 개체 자리에는 지금(살아 있는) 개체 요소를 그대로 둔다: 개체에 붙은 블록 id·그 안에서 따로
고친 칸 문단이 유지된다. 원본 문단은 XML 자리(뿌리부터 자식 번호 경로)로 찾고 태그가 하나라도 다르면 포기(False)한다."""
import copy

from app import zip_guard
from app.hwpx_doc import LINESEG, OBJECTS, P, RUN


def _path(el):
    out = []
    while el.getparent() is not None:
        par = el.getparent()
        out.append((par.index(el), el.tag))
        el = par
    return el, out[::-1]


def _original(doc, pristine, block_id, live):
    """원본 문단 — 같은 블록 id(원본 문서도 blocks() 차례로 id 가 붙어 세션 문서의 원본 요소와 같다 — 문단을 넣고 빼도 맞음),
    없으면 XML 자리(뿌리부터 자식 번호 경로). -> (부분 이름, 원본 요소) | (None, None)."""
    root, path = _path(live)
    name = doc._name_of.get(root)
    o = pristine._ids.get(block_id)
    if o is not None and o.tag == P and pristine._name_of.get(o.getroottree().getroot()) == name:
        return name, o
    o = pristine._roots.get(name)
    if o is None:
        return None, None
    for i, tag in path:
        if i >= len(o) or o[i].tag != tag:
            return None, None
        o = o[i]
    return name, o


def restore_para(doc, pristine, block_id) -> bool:
    live = doc._ids.get(block_id)
    if live is None or live.tag != P:
        return False
    name, o = _original(doc, pristine, block_id, live)
    if o is None:
        return False
    lruns, oruns = live.findall(RUN), o.findall(RUN)
    if dict(live.attrib) != dict(o.attrib):  # 문단 모양(paraPrIDRef 등) — 서식 편집을 되돌릴 때
        live.attrib.clear()
        live.attrib.update(o.attrib)
    if not any(c.tag in OBJECTS for r in lruns + oruns for c in r) and len(lruns) != len(oruns):
        # 개체 없는 문단은 런째 원본으로(글자 모양 편집이 런을 나눠 수가 달라졌어도)
        for r in lruns:
            live.remove(r)
        for k, r in enumerate(oruns):
            live.insert(k, copy.deepcopy(r))
        lruns = oruns = []
    if len(lruns) != len(oruns):
        if oruns or any(c.tag in OBJECTS for r in lruns for c in r):
            return False
        for r in lruns:  # 글 칸이 하나도 없던 문단에 set_text 가 만든 런
            live.remove(r)
        lruns = []
    plan = []
    for lr, orr in zip(lruns, oruns):
        objs = [c for c in lr if c.tag in OBJECTS]
        oobjs = [c for c in orr if c.tag in OBJECTS]
        if [c.tag for c in objs] != [c.tag for c in oobjs]:
            return False
        plan.append((lr, orr, objs))
    for lr, orr, objs in plan:
        it = iter(objs)
        kids = [next(it) if c.tag in OBJECTS else copy.deepcopy(c) for c in orr]
        for c in list(lr):
            lr.remove(c)
        lr.extend(kids)
        if dict(lr.attrib) != dict(orr.attrib):
            lr.attrib.clear()
            lr.attrib.update(orr.attrib)
    # 줄 배치 캐시: 원본 자리 그대로(보통 문단 끝)
    for ls in live.findall(LINESEG):
        live.remove(ls)
    for k, c in enumerate(o):
        if c.tag == LINESEG:
            live.insert(min(k, len(live)), copy.deepcopy(c))
    doc._mark(name)
    return True


def settle(doc, names):
    """고친 문단이 더 없는 XML 부분이 원본 바이트와 같아졌으면 「고침」 표시를 뗀다 — 모두 떼지면 save() 가 원본 바이트를 그대로 돌려준다."""
    for name in names:
        if name in doc._dirty and doc._dump(name) == zip_guard.read(doc._zip, name):
            doc._dirty.discard(name)


def part_of(doc, block_id):
    el = doc._ids.get(block_id)
    return doc._name_of.get(el.getroottree().getroot()) if el is not None else None

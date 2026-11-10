"""문단 원본 복원(spec_docx_웹편집 ② §3 「되돌리기」) — restore.py(hwpx)의 docx 판. 글만 다시 쓰지 않고 원본 문단의 XML(문단 속성·런·글 요소)을
되돌린다. 그림(w:drawing)·옛 그림(w:pict)·개체는 지금(살아 있는) 요소를 그 자리에 그대로 둬 그림 블록 id 가 유지된다 — 개수·차례가 원본과 다르면
포기(False). 원본 문단은 같은 블록 id(원본 문서도 blocks() 차례로 id 가 붙음), 없으면 XML 자리(뿌리부터 자식 번호 경로)로 찾는다."""
import copy

from app import zip_guard

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
P = W + "p"
KEEP = (W + "drawing", W + "pict", W + "object", MC + "AlternateContent")  # 블록 id 가 붙는(또는 품는) 개체 — 바깥쪽 것만 센다


def _objects(el):
    out = []
    for e in el.iter(*KEEP):
        if not any(a in out for a in e.iterancestors(*KEEP)):
            out.append(e)
    return out


def _path(el):
    out = []
    while el.getparent() is not None:
        par = el.getparent()
        out.append((par.index(el), el.tag))
        el = par
    return out[::-1]


def _original(doc, pristine, block_id, live):
    o = pristine._ids.get(block_id)
    if o is not None and o.tag == P:
        return o
    o = pristine._part(pristine._doc)
    for i, tag in _path(live):
        if i >= len(o) or o[i].tag != tag:
            return None
        o = o[i]
    return o if o.tag == P else None


def restore_para(doc, pristine, block_id) -> bool:
    live = doc._ids.get(block_id)
    if live is None or live.tag != P:
        return False
    o = _original(doc, pristine, block_id, live)
    if o is None:
        return False
    keep, want = _objects(live), _objects(o)
    if [e.tag for e in keep] != [e.tag for e in want]:
        return False
    fresh = copy.deepcopy(o)
    for new, old in zip(keep, _objects(fresh)):  # 개체 자리에는 지금 요소(블록 id·그 안 편집 유지)
        old.getparent().replace(old, new)
    for c in list(live):
        live.remove(c)
    live.attrib.clear()
    live.attrib.update(o.attrib)
    live.extend(list(fresh))
    doc._dirty.add(doc._doc)
    return True


def settle(doc, names):
    """고친 문단이 더 없는 XML 부분이 원본 바이트와 같아졌으면 「고침」 표시를 뗀다 — 모두 떼지면 save() 가 원본 바이트를 그대로 돌려준다."""
    for name in names:
        if name in doc._dirty and name in doc._zip.NameToInfo and doc._dump(name) == zip_guard.read(doc._zip, name):
            doc._dirty.discard(name)


def part_of(doc, block_id):
    el = doc._ids.get(block_id)
    return doc._doc if el is not None else None

"""헤딩 추출 2단계 — 헤딩 그래프 · 템플릿(가지 규칙) · 조정(spec_헤딩_추출 ② §6). 문서를 바꾸지 않는다.

흐름(2026-11-09 사용자 확정 「템플릿 가지 규칙」 + astra 협의): 1단계 결과 → 후보 노드 → 헤딩 유형 표 → **A 호출**(유형마다 role·basis·variantOf·
**parents** = 보통 매달리는 부모 레터, 본문 **주 사슬** 확인) → **부모 초안**(스크립트 — 흐름마다 열린 노드 스택, 같은 레터 = 형제, 부모로 받아들여지는 항목의
자식, 라벨은 제 템플릿의 뿌리) → **B 호출**(본문 구간마다 초안과 다른 노드만 — 부모·역할 + 슬롯 예외) → 확정 트리 위에서 **사슬 학습 ↔ 슬롯 배정**(고정점) →
템플릿 **id 동결**·앵커 → **C**(슬롯 서식 쌍 조정) → **D**(재검토) → 인스턴스·이종 형제·조정.
템플릿 = 레터 계열 **사슬** 하나(key = scope:사슬 = 앵커). 가지 자리(한 부모 아래 레터가 둘 이상)마다 새 템플릿이 뿌리(L1)를 내리고, 같은 사슬 꼴은 어디에 매달려도
같은 템플릿(정의 1 + 인스턴스 여럿). 구분 라벨은 그 라벨부터 새 템플릿(라벨 = L1). LLM 이 없거나 실패하면 역할·부모는 스크립트 어림(`heuristic` 표지)."""
import json
import re
import time
from collections import Counter, defaultdict

from app import heading_llm as HL
from app import heading_rules as R
from app import llm

TITLE_MAX = 60
SECTION_MAX = 120
CHANGE_RATE_RETRY = 0.3
MAX_ROUNDS = 12
SENT_END = re.compile(r"(?:다|음|함|요|임)\.\s*$")
VARIANTS = {"circle": "o", "latin-o": "o", "jamo-o": "o", "dash": "-", "dot": "·", "square": "□", "triangle": "△", "small-square": "▫",
            "diamond": "◇", "arrow": "▶"}
ROLES = ("heading", "label", "title", "note", "not_heading")
KIND_ORDER = {"main": 0, "branch": 1, "label": 2, "cell": 3}
MAIN = ("body", "main")  # 주 사슬 템플릿 키


# ---- 후보 노드 · 유형 ------------------------------------------------------------------------------------

_SPECIAL = ("shape", "caption", "header", "footer", "footnote", "endnote", "master")


def _flow(rec):
    """흐름 — 본문은 "body", 표 칸은 칸마다, 글상자·머리말·각주 …는 그 그릇마다(1단계 사슬의 key — 없는 옛 결과는 옛 꼴).
    1칸 상자는 투명 — 바깥 그릇의 흐름(본문이면 본문, 여러 칸 표 칸 안이면 그 칸)."""
    path = rec.get("path") or []
    for i in range(len(path) - 1, -1, -1):  # 안쪽 그릇부터
        c = path[i]
        if c["t"] == "cell":
            if i and path[i - 1]["t"] == "tbl" and path[i - 1].get("cells") == 1:
                continue  # 1칸 상자 — 건너뜀
            return f"cell:{c['id']}" if c.get("id") else (f"cell:k{c['key']}" if c.get("key") else "cell:None")
        if c["t"] in _SPECIAL:
            return f"{c['t']}:{c['key'] if c.get('key') else json.dumps(c, sort_keys=True)}"
    return "body"


def _scope(flow):
    """템플릿 scope — 본문(글상자·머리말 같은 다른 그릇 포함) | 표 칸."""
    return "cell" if flow.startswith("cell:") else "body"


def _body_size(paras):
    c = Counter((r["char"]["text"] or {}).get("sizePt") for r in paras if r["kind"] == "plain" and r["area"] == "body" and r["text"].strip())
    return c.most_common(1)[0][0] if c else 10.0


def candidates(stage1):
    """헤딩 후보 노드(문서 순) — marker·label 구간, 개요·번호 문단, 제목 같은 plain(본문·상자, 짧고 굵거나 본문보다 큰 글), 강제 줄 바꿈 뒤 marker·label 줄."""
    paras = stage1["paras"]
    body = _body_size(paras)
    out = []
    for rec in paras:
        size = (rec["char"]["text"] or {}).get("sizePt") or 0
        bold = bool((rec["char"]["text"] or {}).get("bold"))
        first = rec["text"].strip().split(R.BR, 1)[0]
        base = {"para": rec["id"], "n": rec["n"], "area": rec["area"], "flow": _flow(rec), "table": rec["table"], "cell": rec["cell"],
                "lead": rec["leadSpaces"], "fmt": rec["fmt"], "bold": bold, "size": size}
        kind = None
        if rec["kind"] in ("marker", "label"):
            kind = rec["kind"]
        elif rec.get("num") or rec.get("outlineLevel"):
            kind = "outline"
        elif (rec["kind"] == "plain" and base["flow"] == "body" and 0 < len(first) <= TITLE_MAX and not SENT_END.search(first)
              and (bold or size >= body + 1)):  # 칸 안 상자 글은 칸 글처럼 제목 후보 아님
            kind = "title"
        if kind:
            out.append({**base, "id": rec["id"], "span": 0, "kind": kind, "family": rec["family"], "shape": rec["shape"], "letter": rec["letter"],
                        "blank": rec["blank"], "text": (rec["rest"] if kind in ("marker", "label") else rec["text"]).strip().split(R.BR, 1)[0][:80],
                        "outline": rec.get("outlineLevel")})
        for sp in rec["spans"][1:]:
            if sp["line"] and sp["kind"] in ("marker", "label"):
                line = rec["text"].split(R.BR)[sp["line"]]
                out.append({**base, "id": f"{rec['id']}#{sp['i']}", "span": sp["i"], "kind": sp["kind"], "family": sp["family"],
                            "shape": R.shape_of(sp["family"], sp["letter"]), "letter": sp["letter"], "blank": False, "text": line.strip()[:80],
                            "outline": None})
    return out


def _shape_key(node):
    if node["kind"] == "label":
        return re.sub(r"\d+", "N", node["letter"].strip())
    if node["kind"] == "title":
        return "제목"
    if node["kind"] == "outline":
        return f"개요{node['outline'] or '?'}"
    return node["shape"] or node["letter"].strip()


def type_table(nodes):
    """노드마다 유형 id 를 달고 유형 표 → {Tn: {type, area, kind, shape, bold, size, count, examples, lead, labels, prev, next, blank, family}}."""
    keys, types = {}, {}
    for nd in nodes:
        key = ("cell" if nd["flow"].startswith("cell:") else "body", nd["kind"], _shape_key(nd), nd["bold"], round(nd["size"] or 0))  # 칸 안 상자도 칸
        if key not in keys:
            keys[key] = f"T{len(keys) + 1}"
            types[keys[key]] = {"type": keys[key], "area": key[0], "kind": key[1], "shape": key[2], "bold": key[3], "size": key[4],
                                "family": nd["family"], "count": 0, "examples": [], "lead": Counter(), "labels": Counter(), "prev": Counter(),
                                "next": Counter(), "blank": 0}
        nd["type"] = keys[key]
        t = types[nd["type"]]
        t["count"] += 1
        t["lead"][nd["lead"]] += 1
        t["labels"][nd["fmt"]] += 1
        t["blank"] += nd["blank"]
        if len(t["examples"]) < 3 and nd["text"] and nd["text"] not in t["examples"]:
            t["examples"].append(nd["text"][:50])
    last = {}
    for nd in nodes:
        p = last.get(nd["flow"])
        if p is not None:
            types[p["type"]]["next"][nd["type"]] += 1
            types[nd["type"]]["prev"][p["type"]] += 1
        last[nd["flow"]] = nd
    for t in types.values():
        for k in ("lead", "labels", "prev", "next"):
            t[k] = dict(t[k].most_common(3))
    return types


def sketch(nodes, limit=260):
    """A 호출 맥락 — 본문 흐름 후보를 문서 순 한 줄씩(「T3 _2 □ 연구개발…」). 많으면 앞에서 limit 줄 + 드문 유형(3회 이하)의 나머지."""
    body = [nd for nd in nodes if nd["flow"] == "body"]
    cnt = Counter(nd["type"] for nd in body)
    pick = body[:limit] + [nd for nd in body[limit:] if cnt[nd["type"]] <= 3]
    return [f"{nd['type']} _{nd['lead']} {nd['letter'] or ''} {nd['text'][:40]}".strip() for nd in pick]


# ---- 역할 · 정규 레터 키 -----------------------------------------------------------------------------------

def _type_key(t, role):
    """유형 → 정규 레터 키(변형군 합침). 라벨은 "[basis]"(basis 없으면 "[라벨]"). 헤딩 아님·안내·제목(잎)은 None."""
    r = role.get("role") or "heading"
    if r in ("not_heading", "note", "title"):
        return None
    if r == "label" or t["kind"] == "label":
        return "[" + (role.get("basis") or "라벨") + "]"
    if t["kind"] == "outline":
        return t["shape"]
    if t["kind"] == "title":
        return "제목"
    return VARIANTS.get(t.get("family") or "") or t["shape"] or "?"


def type_keys(types, roles):
    """{Tn: 정규 레터 키 | None} — A 의 variantOf(같은 레터로 볼 다른 유형)는 그 유형의 키."""
    out = {tid: _type_key(t, roles.get(tid) or {}) for tid, t in types.items()}
    for tid, r in roles.items():
        v = r.get("variantOf")
        if v and v in out and out[v] and out.get(tid):
            out[tid] = out[v]
    return out


def fallback_roles(types):
    """LLM 없이 — 라벨 꼴은 label, 제목 꼴은 title, 그 밖 heading. 부모 지식 없음(초안은 어림)."""
    return {tid: {"role": "label" if t["kind"] == "label" else "title" if t["kind"] == "title" else "heading", "parents": [], "variantOf": "",
                  "basis": "", "reason": "스크립트 대체 판정"} for tid, t in types.items()}


# LLM 없는 어림의 계열 서열(얕음 → 깊음) — 한국어 개요의 흔한 차례. 보조 근거(앞 공백이 같을 때)로만 쓴다.
_RANK = {"chapter": 1, "roman-upper": 2, "section": 2, "hyphen": 4, "hangul-dot": 6, "paren-num": 7, "num-paren": 7, "hangul-paren": 8,
         "paren-hangul": 8, "circled": 9, "square": 10, "circle": 11, "latin-o": 11, "jamo-o": 11, "dash": 12, "dot": 13}


def _rank(nd):
    if nd["kind"] != "marker":
        return None
    if nd["family"] == "decimal":
        return 2 + (nd["shape"] or "N.").count("N")  # N. = 3, N.N. = 4, N.N.N. = 5
    return _RANK.get(nd["family"])


# ---- A 호출 --------------------------------------------------------------------------------------------

def a_job(types, nodes, keys, proposal, doc_name="", pinned=None):
    rows = [{**{k: t[k] for k in ("type", "area", "kind", "shape", "bold", "size", "count", "examples", "lead", "prev", "next", "blank")}, "key": keys.get(t["type"]) or ""}
            for t in types.values()]
    data = {"document": doc_name, "types": rows, "sketch": sketch(nodes), "mainChainProposal": list(proposal or [])}
    content, used = HL.prompt(HL.TYPES_CONTRACT, ["graph", "templates", "tolerance"], data, pinned)
    return {"schema": HL.TYPES_SCHEMA, "content": content, "what": "heading_types", "timeout": 900.0, "effort": "medium"}, used, data


def apply_types(data, types):
    """A 응답 → (역할 {Tn: {role, parents[키…], variantOf, basis, reason}}, 주 사슬 [키…] | None). 모르는 유형은 버림, 레터 키는 아래서 다시 정규화."""
    roles = {}
    for it in (data or {}).get("types") or []:
        tid = it.get("type")
        if tid not in types:
            continue
        role = it.get("role") if it.get("role") in ROLES else "heading"
        parents = [str(p).strip() for p in (it.get("parents") or []) if str(p).strip()][:12]
        roles[tid] = {"role": role, "parents": parents, "variantOf": it.get("variantOf") if it.get("variantOf") in types else "",
                      "basis": str(it.get("basis") or "")[:20], "reason": str(it.get("reason") or "")[:200]}
    main = [str(k).strip() for k in (data or {}).get("mainChain") or [] if str(k).strip()]
    return roles, (main[:12] or None)


# ---- 부모 초안 -----------------------------------------------------------------------------------------

def _accepts(e, k, nd, rk, parents, main_next, trusted=True):
    """스택 항목 e 가 레터 k 노드의 부모로 받아들여지는가 → (받아들임, 어림이었나).
    지식(A 의 parents·주 사슬)이 있으면 그것만, 없으면 어림 — 서열이 더 얕은 항목(서열을 모르면 앞 공백이 더 적은 항목)이 부모. trusted = 주 사슬이 A 가 확인한 것
    (아니면 스크립트 제안이라 그것으로 정한 부모도 어림)."""
    if parents:
        return (e["key"] in parents or main_next.get(e["key"]) == k), False
    if main_next.get(e["key"]) == k:
        return True, not trusted
    if e["label"]:  # 라벨의 닻(부모) 레터보다 깊은 서열이면 라벨의 내용
        ar = e["anchorRank"]
        return (rk is None or ar is None or rk > ar), True
    er = e["rank"]
    if er is not None and rk is not None:  # 서열을 둘 다 알면 서열 — 더 얕은 레터만 부모(앞 공백이 거꾸로여도 — 양식은 「1-1.」 보다 「□」 를 덜 들여 쓰기도)
        return er < rk, True
    return e["lead"] <= nd["lead"], True  # 서열을 모르면 앞 공백 — 덜(또는 같게) 들여 쓴 쪽이 부모


def draft_parents(nodes, roles, keys, main_chain, stage1, trusted=False):
    """부모 초안 → (graph {id: {id, para, type, role, key, parent, division, depth, heuristic}}, edges(contains·parent 그릇 간선), containers).
    흐름마다 열린 노드 스택: 노드마다 스택 위에서부터 — 같은 키 = 형제, 부모로 받아들여지는 항목 = 자식, 아니면 닫고 아래로. 라벨 = 같은 묶음 라벨이 열려 있으면
    그 닻까지 닫고 형제, 아니면 자식(라벨은 제 템플릿의 뿌리이므로 스택에 올린다). 헤딩 아님·안내·제목(잎)은 스택에 안 올림. trusted = main_chain 이 A 가 확인한 것."""
    by_para = defaultdict(list)
    for nd in nodes:
        by_para[nd["para"]].append(nd)
    graph, edges, containers = {}, [], {}
    stacks, divs = defaultdict(list), defaultdict(list)
    main_chain = list(main_chain or [])
    main_next = {main_chain[i]: main_chain[i + 1] for i in range(len(main_chain) - 1)}

    def flow_root(flow):
        return "root" if flow == "body" else (f"cell:{flow[5:]}" if flow.startswith("cell:") else f"area:{flow}")

    def top(flow):
        st = stacks[flow]
        return st[-1]["id"] if st else flow_root(flow)

    for rec in stage1["paras"]:
        chain = rec["path"]
        for i, c in enumerate(chain):
            if c["t"] == "tbl" and c.get("id"):
                tid = f"tbl:{c['id']}"
                if tid not in containers:
                    outer = [x for x in chain[:i] if x["t"] == "cell"]
                    special = any(x["t"] in ("shape", "header", "footer", "footnote", "endnote", "caption") for x in chain[:i])
                    outer_flow = f"cell:{outer[-1]['id']}" if outer else (_flow(rec) if special else "body")
                    box = c.get("cells") == 1
                    containers[tid] = {"id": tid, "kind": "box" if box else "table", "parent": top(outer_flow), "host": c.get("host")}
                    edges.append({"t": "contains", "from": c.get("host") or top(outer_flow), "to": tid})
                    if not box:
                        edges.append({"t": "parent", "from": top(outer_flow), "to": tid})
            if c["t"] == "cell" and c.get("id"):
                cid = f"cell:{c['id']}"
                if cid not in containers:
                    tbl = chain[i - 1] if i and chain[i - 1]["t"] == "tbl" else None
                    containers[cid] = {"id": cid, "kind": "cell", "table": f"tbl:{tbl['id']}" if tbl else None, "row": c.get("row"), "col": c.get("col"),
                                       "parent": f"tbl:{tbl['id']}" if tbl else None}
                    if tbl:
                        edges.append({"t": "contains", "from": f"tbl:{tbl['id']}", "to": cid})
                        if tbl.get("cells") != 1:
                            edges.append({"t": "parent", "from": f"tbl:{tbl['id']}", "to": cid})
        for nd in by_para.get(rec["id"], ()):
            role = (roles.get(nd["type"]) or {}).get("role") or "heading"
            k = keys.get(nd["type"])
            flow = nd["flow"]
            st, dv = stacks[flow], divs[flow]
            g = {"id": nd["id"], "para": nd["para"], "type": nd["type"], "role": role, "key": k, "parent": None, "division": None, "depth": None,
                 "heuristic": False}
            if nd["area"] == "cell":
                edges.append({"t": "contains", "from": flow_root(flow), "to": nd["id"]})
            if k is None:  # 헤딩 아님·안내·제목 — 잎(스택을 흔들지 않음)
                g.update(parent=top(flow), division=dv[-1]["id"] if dv else None, depth=float(len(st) + 1))
                graph[nd["id"]] = g
                continue
            if role == "label":
                cls = (k, nd["lead"]) if k == "[라벨]" else k
                # basis 없는 꼴 묶음에서, 본문 루트에 닻 내린 라벨은 꼴만 같은 다른 유형 라벨과 같은 묶음이 아니다(열린 개요를 루트까지 지우지 않게)
                same = next((j for j in range(len(dv) - 1, -1, -1) if dv[j]["cls"] == cls
                             and not (k == "[라벨]" and flow == "body" and dv[j]["anchor"] == "root" and dv[j]["type"] != nd["type"])), None)
                if same is not None:  # 같은 묶음의 다음 라벨 — 앞 라벨의 닻까지 닫는다
                    anchor = dv[same]["anchor"]
                    del dv[same:]
                    ids = [e["id"] for e in st]
                    if anchor in ids:
                        del st[ids.index(anchor) + 1:]
                    elif anchor == flow_root(flow):
                        st.clear()
                parent = top(flow)
                st.append({"id": nd["id"], "key": k, "lead": nd["lead"], "rank": None, "label": True, "parent": parent,
                           "anchorRank": next((e["rank"] for e in reversed(st) if not e["label"]), None)})
                dv.append({"id": nd["id"], "cls": cls, "anchor": parent, "type": nd["type"]})
                g.update(parent=parent, division=dv[-2]["id"] if len(dv) > 1 else None, depth=float(len(st)))
                graph[nd["id"]] = g
                continue
            parents = set((roles.get(nd["type"]) or {}).get("parents") or [])
            rk = _rank(nd)
            parent, heuristic = None, False
            for i in range(len(st) - 1, -1, -1):
                e = st[i]
                if not e["label"] and e["key"] == k:  # 같은 레터 = 형제
                    parent = e["parent"]
                    del st[i:]
                    break
                ok, guessed = _accepts(e, k, nd, rk, parents, main_next, trusted)
                if ok:
                    parent, heuristic = e["id"], guessed
                    del st[i + 1:]
                    break
            if parent is None:
                parent = flow_root(flow)
                heuristic = not parents and not (trusted and main_chain and main_chain[0] == k)
                st.clear()
            ids = {e["id"] for e in st}
            while dv and dv[-1]["id"] not in ids:  # 스택에서 빠진 라벨 = 범위 끝
                dv.pop()
            st.append({"id": nd["id"], "key": k, "lead": nd["lead"], "rank": rk, "label": False, "parent": parent, "anchorRank": None})
            g.update(parent=parent, division=dv[-1]["id"] if dv else None, depth=float(len(st)), heuristic=heuristic)
            graph[nd["id"]] = g
    for g in graph.values():
        if g["parent"] is not None:
            edges.append({"t": "parent", "from": g["parent"], "to": g["id"]})
        if g.get("division"):
            edges.append({"t": "division", "from": g["division"], "to": g["id"]})
    return graph, edges, containers


# ---- 사슬 학습 ↔ 슬롯 배정 -----------------------------------------------------------------------------------

def _eff_parent(g, graph):
    """의미 부모 — 헤딩 아님·안내는 투명(그 자식은 그 위 노드에 붙는다; 그래프 부모는 그대로)."""
    p, seen = g.get("parent"), set()
    while p in graph and graph[p]["role"] in ("not_heading", "note") and p not in seen:
        seen.add(p)
        p = graph[p].get("parent")
    return p


def _kind(tk):
    return "main" if tk == MAIN else "cell" if tk[0] == "cell" else "label" if tk[1].startswith("[") else "branch"


_KEY_ORDER = ["제N장", "제N절", "R.", "N.", "N-N.", "N.N.", "N.N.N.", "가.", "N)", "가)", "(N)", "(가)", "①", "□", "○", "o", "△", "-", "·", "▫", "*"]


def _key_rank(k):
    """사슬 학습 동률 때의 차례 — 한국어 개요에서 얕은 레터가 먼저, 모르는 레터는 글자 순."""
    return (_KEY_ORDER.index(k) if k in _KEY_ORDER else len(_KEY_ORDER)), k


def anchor_of(tk, chain):
    return f"{tk[0]}:{'›'.join(chain)}"


def assign_templates(nodes, graph, keys, main_chain=None, fixed_main=False):
    """확정 트리 위에서 템플릿 사슬을 배우고 노드마다 (템플릿, 레벨, 인스턴스)를 매긴다(고정점) → {"templates", "instances", "nodes": {id: {template, tplNo, level, instance}},
    "chains", "ties", "conflicts", "unresolved"}. main_chain = A 가 확인한 주 사슬(fixed_main 이면 제약 — 학습은 그 뒤 레벨만 잇고, 다르게 셈한 자리는 conflicts 에 기록).
    노드 규칙: 라벨 → (scope:[basis], 1) · 흐름 뿌리 아래 주 사슬 첫 레터 → (main, 1) · 부모 사슬의 다음 레터 = 내 레터 → (부모 템플릿, L+1) · 그 밖 → (scope:레터, 1).
    B 의 슬롯 예외(graph[id]["slot"] = {template: 앵커, level}) 가 있으면 그대로(앵커를 못 찾으면 기록하고 규칙대로)."""
    by_id = {nd["id"]: nd for nd in nodes}
    order = [nd for nd in nodes if nd["id"] in graph and graph[nd["id"]].get("key") and graph[nd["id"]]["role"] not in ("not_heading", "note", "title")]
    chains = {MAIN: list(main_chain)} if main_chain else {}

    def tk_of_anchor(anchor, chains):
        """B 가 적은 앵커(초안 때의 사슬 글) → 템플릿 키 — 사슬이 그 뒤 더 배워져도 scope 와 뿌리 레터로 찾는다."""
        if ":" not in anchor:
            return None
        sc, chain = anchor.split(":", 1)
        root = chain.split("›", 1)[0]
        if sc == "body" and (chains.get(MAIN) or [None])[0] == root:
            return MAIN
        return (sc, root) if (sc, root) in chains else None

    def one_pass(chains):
        asg, instances, unresolved = {}, [], []
        for nd in order:
            g = graph[nd["id"]]
            k = g["key"]  # 노드의 정규 레터 키(초안이 유형 키를 적고, B 가 역할을 바꾸면 따라 바뀜)
            sc = _scope(nd["flow"])
            p = _eff_parent(g, graph)
            pa = asg.get(p)
            ov = g.get("slot")
            tk = lv = None
            if ov:
                otk = tk_of_anchor(ov["template"], chains)
                if otk is not None and 1 <= ov["level"] <= len(chains.get(otk) or []):
                    tk, lv = otk, ov["level"]
                else:
                    unresolved.append({"id": nd["id"], "slot": ov, "why": "앵커·레벨을 못 찾음"})
            if tk is None:
                if g["role"] == "label":
                    tk, lv = (sc, k), 1
                elif pa is None:
                    tk, lv = (MAIN, 1) if sc == "body" and (chains.get(MAIN) or [None])[0] == k else ((sc, k), 1)
                else:
                    ptk, plv, _ = pa
                    ch = chains.get(ptk) or []
                    tk, lv = (ptk, plv + 1) if plv < len(ch) and ch[plv] == k else ((sc, k), 1)
            if lv == 1 or pa is None or pa[0] != tk:
                instances.append({"tk": tk, "root": nd["id"], "parent": p if p in graph else (p or "root")})
                inst = len(instances) - 1
            else:
                inst = pa[2]
            asg[nd["id"]] = (tk, lv, inst)
        return asg, instances, unresolved

    def learn(asg, chains):
        kids, rootkeys, ties, conflicts = defaultdict(Counter), Counter(), [], []
        for nid, (tk, lv, _) in asg.items():
            g = graph[nid]
            if g["role"] == "label":
                continue  # 라벨은 부모 사슬을 잇는 후보가 아니다(늘 새 템플릿)
            p = _eff_parent(g, graph)
            if p in asg:
                ptk, plv, _ = asg[p]
                kids[(ptk, plv)][g["key"]] += 1
            elif _scope(by_id[nid]["flow"]) == "body":
                rootkeys[g["key"]] += 1
        new = {}
        if fixed_main and main_chain:
            new[MAIN] = list(main_chain)
        elif rootkeys:
            top = rootkeys.most_common()
            new[MAIN] = [top[0][0]]
            if len(top) > 1 and top[1][1] == top[0][1]:
                ties.append({"template": "main", "level": 1, "letters": [k for k, n in top if n == top[0][1]]})
        for tk in {tk for tk, _, _ in asg.values()} | set(new):
            ch = list(new.get(tk) or [tk[1]])
            start = len(ch) if (tk == MAIN and fixed_main and main_chain) else 1
            if tk == MAIN and fixed_main and main_chain:  # 제약과 다르게 셈한 자리는 기록만
                for L in range(1, len(ch)):
                    c = kids.get((tk, L))
                    if c and c.most_common(1)[0][0] != ch[L]:
                        conflicts.append({"template": "main", "level": L + 1, "fixed": ch[L], "counted": dict(c.most_common(3))})
            L = start
            while kids.get((tk, L)):
                # 동률이면 한국어 개요 차례가 얕은 레터. 바로 위 레벨과 같은 레터는 사슬을 잇지 못한다(같은 레터 = 형제 — 「o」 아래 「o」 는 가지)
                top = sorted(((k, n) for k, n in kids[(tk, L)].items() if k != ch[L - 1]), key=lambda kv: (-kv[1], _key_rank(kv[0])))
                if not top:
                    break
                nxt = top[0][0]
                if len(top) > 1 and top[1][1] == top[0][1]:
                    ties.append({"template": anchor_of(tk, ch[:L]), "level": L + 1, "letters": [k for k, n in top if n == top[0][1]]})
                if len(ch) <= L:
                    ch.append(nxt)
                else:
                    ch[L] = nxt
                L += 1
            new[tk] = ch[:max(L, 1)]
        return new, ties, conflicts

    ties = conflicts = []
    asg, instances, unresolved = one_pass(chains)
    for _ in range(MAX_ROUNDS):
        new, ties, conflicts = learn(asg, chains)
        asg2, instances2, unresolved2 = one_pass(new)
        if new == chains and asg2 == asg:
            break
        chains, asg, instances, unresolved = new, asg2, instances2, unresolved2
    # 템플릿 id — 주 사슬 → 가지(문서 순 첫 등장) → 라벨 → 표 칸
    first_n = {}
    for nid, (tk, _, _) in asg.items():
        first_n[tk] = min(first_n.get(tk, 1 << 30), by_id[nid]["n"])
    used = {tk for tk, _, _ in asg.values()}
    tkeys = sorted(used, key=lambda tk: (KIND_ORDER[_kind(tk)], first_n.get(tk, 1 << 30), str(tk)))
    tid = {tk: i + 1 for i, tk in enumerate(tkeys)}
    anchors = {tk: anchor_of(tk, chains.get(tk) or [tk[1]]) for tk in tkeys}
    # 인스턴스 — 템플릿 L1 이 나타나는 모든 자리; 멤버 = 직접 소속(안쪽 인스턴스 경계까지)
    for i, ins in enumerate(instances):
        ins.update(i=i, template=tid[ins["tk"]], anchor=anchors[ins["tk"]], members=[], childInstances=[])
    inst_of = {nid: a[2] for nid, a in asg.items()}
    for nd in order:
        a = asg[nd["id"]]
        if instances[a[2]]["root"] != nd["id"]:
            instances[a[2]]["members"].append(nd["id"])
    for ins in instances:
        p = ins["parent"]
        if p in inst_of:
            instances[inst_of[p]]["childInstances"].append(ins["i"])
    per_tpl = Counter()
    for ins in instances:
        per_tpl[ins["template"]] += 1
        ins["no"] = per_tpl[ins["template"]]
        chain = chains.get(ins["tk"]) or [ins["tk"][1]]
        levels = {asg[x][1] for x in [ins["root"]] + ins["members"]}
        ins["missing"] = [L for L in range(1, len(chain) + 1) if L not in levels]
        ins["deviates"] = bool(ins["missing"])
        root = by_id[ins["root"]]
        ins["text"] = root["text"][:50]
        ins["basis"] = root["letter"].strip() if graph[ins["root"]]["role"] == "label" else ""
        path, p, seen = [], ins["parent"], set()
        while p in graph and p not in seen and len(path) < 4:
            seen.add(p)
            if p in by_id:
                path.append(((by_id[p]["letter"] or "").strip() + " " + by_id[p]["text"][:20]).strip())
            p = graph[p].get("parent")
        ins["path"] = " › ".join(reversed(path))
        del ins["tk"]
    node_out = {nid: {"template": anchors[a[0]], "tplNo": tid[a[0]], "level": a[1], "instance": a[2]} for nid, a in asg.items()}
    templates = []
    for tk in tkeys:
        chain = chains.get(tk) or [tk[1]]
        templates.append({"id": tid[tk], "no": tid[tk], "anchor": anchors[tk], "name": anchors[tk], "key": anchors[tk], "kind": _kind(tk), "scope": tk[0],
                          "rootRole": "label" if tk[1].startswith("[") else "heading", "root": tk[1], "chain": chain, "displayName": "",
                          "instances": per_tpl[tid[tk]], "where": [], "slots": [], "note": ""})
    where = defaultdict(Counter)
    for ins in instances:
        p = ins["parent"]
        where[ins["template"]][graph[p]["key"] if p in graph and graph[p].get("key") else ("root" if p == "root" or p is None else "칸")] += 1
    for t in templates:
        t["where"] = [{"parent": k, "count": n} for k, n in where[t["id"]].most_common(6)]
    return {"templates": templates, "instances": instances, "nodes": node_out, "chains": {anchors[tk]: ch for tk, ch in chains.items() if tk in anchors},
            "ties": ties, "conflicts": conflicts, "unresolved": unresolved}


def propose_main(nodes, roles, keys, stage1):
    """A 호출 앞 — 지식 없는 어림 초안에서 셈한 본문 주 사슬 제안(A 가 확인·수정)."""
    graph, _, _ = draft_parents(nodes, roles, keys, None, stage1)
    asg = assign_templates(nodes, graph, keys)
    main = next((t for t in asg["templates"] if t["kind"] == "main"), None)
    return main["chain"] if main else []


# ---- B 호출(본문 구간) ---------------------------------------------------------------------------------

def sections(nodes, graph, tmap=None):
    """본문 흐름 노드를 구간으로 — 깊이 1(최상위) 노드에서 끊고, 작은 최상위 구간은 이어서 SECTION_MAX 안에서 합치며(호출 수),
    SECTION_MAX 넘는 최상위 구간은 깊이 2 에서 더 끊는다. → [[노드 id…]…]."""
    body = [nd for nd in nodes if nd["flow"] == "body" and graph.get(nd["id"], {}).get("role") != "not_heading"]
    cuts, cur = [], []
    for nd in body:
        g = graph[nd["id"]]
        if cur and g.get("depth") == 1.0:
            cuts.append(cur)
            cur = []
        cur.append(nd["id"])
    if cur:
        cuts.append(cur)
    out, part = [], []
    for sec in cuts:
        if len(sec) <= SECTION_MAX:  # 작은 최상위 구간은 이어서 합친다
            if part and len(part) + len(sec) > SECTION_MAX:
                out.append(part)
                part = []
            part += sec
            continue
        if part:
            out.append(part)
            part = []
        # 깊이 2 경계에서 조각으로 나눈 뒤, 이어진 조각을 SECTION_MAX 안에서 합친다. 한 조각이 SECTION_MAX 를 넘으면 그 조각은 SECTION_MAX 씩 그냥 자른다.
        chunks, cur2 = [], []
        for nid in sec:
            if cur2 and graph[nid].get("depth") == 2.0:
                chunks.append(cur2)
                cur2 = []
            cur2.append(nid)
        if cur2:
            chunks.append(cur2)
        p2 = []
        for ch in chunks:
            if p2 and len(p2) + len(ch) > SECTION_MAX:
                out.append(p2)
                p2 = []
            if len(ch) > SECTION_MAX:
                out += [ch[i:i + SECTION_MAX] for i in range(0, len(ch), SECTION_MAX)]
                continue
            p2 += ch
        if p2:
            out.append(p2)
    if part:
        out.append(part)
    return out


def _ancestors(nid, graph, stop):
    out, seen = [], set()
    p = graph[nid]["parent"]
    while p and p in graph and p not in seen and p not in stop:
        seen.add(p)
        out.append(p)
        p = graph[p]["parent"]
    return out[::-1]


def b_jobs(secs, nodes, graph, prov, types, roles, keys, pinned=None):
    """구간마다 B 호출 — 행 = [id, 유형, 글, 초안 부모, 초안 템플릿(앵커), 초안 레벨, 초안 구분 라벨]. prov = 초안 위 임시 배정(assign_templates 결과)."""
    by_id = {nd["id"]: nd for nd in nodes}
    brief = {t: {"role": v["role"], "key": keys.get(t) or "", "basis": v.get("basis", ""), "parents": v.get("parents", []), "shape": types[t]["shape"]}
             for t, v in roles.items() if t in types}
    tpls = [{"anchor": t["anchor"], "kind": t["kind"], "chain": t["chain"]} for t in prov["templates"]]
    jobs, used = [], {}
    for i, sec in enumerate(secs):
        inside = set(sec)
        anc = _ancestors(sec[0], graph, inside)
        rows = [[nid, graph[nid]["type"], ((by_id[nid]["letter"] or "") + " " + by_id[nid]["text"]).strip()[:60], graph[nid]["parent"] or "",
                 prov["nodes"].get(nid, {}).get("template", ""), prov["nodes"].get(nid, {}).get("level", 0), graph[nid].get("division") or ""] for nid in sec]
        nxt = secs[i + 1][:5] if i + 1 < len(secs) else []
        data = {"types": brief, "templates": tpls, "ancestors": [[a, graph[a]["type"], by_id[a]["text"][:40] if a in by_id else ""] for a in anc],
                "nodes": rows, "preview": [[n, graph[n]["type"], by_id[n]["text"][:40]] for n in nxt]}
        content, u = HL.prompt(HL.SECTION_CONTRACT, ["graph", "templates"], data, pinned)
        used.update(u)
        jobs.append({"schema": HL.SECTION_SCHEMA, "content": content, "what": f"heading_section#{i + 1}", "timeout": 600.0, "effort": "medium",
                     "_section": sec, "_ancestors": anc})
    return jobs, used


def apply_changes(changes, sec, anc, graph, anchors):
    """B 응답 변경을 검증해 적용 → (적용 [{id, before, after, reason}], 버림 [{id, why}]). 부모·역할은 바로 적용, template·level 은 슬롯 예외(둘 다 있을 때만 —
    앵커는 초안 템플릿 목록(anchors)에 있어야 함). 라벨 부모는 그대로 부모(라벨은 제 템플릿의 뿌리), 헤딩 아님·안내 부모·순환·문서 순 뒤 부모는 버림."""
    inside, allowed = set(sec), set(sec) | set(anc) | {"root"}
    order = {nid: i for i, nid in enumerate(sec)}
    applied, rejected = [], []
    for ch in changes or []:
        nid = ch.get("id")
        if nid not in inside:
            rejected.append({"id": nid, "why": "구간 밖 id"})
            continue
        g = graph[nid]
        role = ch.get("role") if ch.get("role") in ROLES else g["role"]
        parent = ch.get("parent") or g["parent"]
        if parent not in allowed:
            rejected.append({"id": nid, "why": f"부모 {parent} 가 구간·조상 밖"})
            continue
        if parent in order and order[parent] >= order[nid]:
            rejected.append({"id": nid, "why": "부모가 문서 순으로 뒤"})
            continue
        if parent in graph and graph[parent]["role"] in ("not_heading", "note"):
            rejected.append({"id": nid, "why": f"부모 {parent} 가 헤딩 아님·안내"})
            continue
        p, seen = parent, {nid}
        while p in graph and p not in seen:  # 순환 검사
            seen.add(p)
            p = graph[p]["parent"]
        if p == nid:
            rejected.append({"id": nid, "why": "순환"})
            continue
        tpl = str(ch.get("template") or "")
        lv = ch.get("level")
        lvl = lv if isinstance(lv, int) and not isinstance(lv, bool) else 0
        slot = None
        if role in ("heading", "title") and (tpl or lvl):
            if not tpl or tpl not in anchors:
                rejected.append({"id": nid, "why": f"모르는 템플릿 {tpl or '(없음)'}"})
                continue
            if lvl < 1:
                rejected.append({"id": nid, "why": f"레벨 {lvl} 이 범위 밖"})
                continue
            slot = {"template": tpl, "level": lvl}
        before = {"parent": g["parent"], "role": g["role"], "slot": g.get("slot")}
        g.update(parent=parent, role=role, changed=True, reason=str(ch.get("reason") or "")[:200])
        if role != before["role"]:  # 역할이 바뀌면 정규 레터 키도 따라간다(라벨 = "[…]", 헤딩 아님·안내·제목 = 없음, 제목 → 헤딩 = 「제목」)
            g["key"] = None if role in ("not_heading", "note", "title") else (g.get("key") if (g.get("key") or "").startswith("[") else "[라벨]") if role == "label" \
                else (g.get("key") or "제목")
        if slot or role not in ("heading", "title"):
            g["slot"] = slot
        applied.append({"id": nid, "before": before, "after": {"parent": g["parent"], "role": g["role"], "slot": g.get("slot")}, "reason": g["reason"]})
    return applied, rejected


def _division_of(nid, graph):
    """구분 소속 = 가장 가까운 라벨 조상(라벨 자신은 그 위 라벨)."""
    p, seen = graph[nid].get("parent"), set()
    while p in graph and p not in seen:
        seen.add(p)
        if graph[p]["role"] == "label":
            return p
        p = graph[p].get("parent")
    return None


# ---- C 호출(슬롯 서식 쌍 — 조정 판단) --------------------------------------------------------------------

PAIR_BATCH = 60


def _slot_rep(ids, by_id, graph):
    """슬롯 서식 수(모든 노드) + 대표 서식 — 미판정(B 실패 구간) 노드는 대표의 근거로 안 씀(spec ② §6)."""
    fm = Counter(by_id[i]["fmt"] for i in ids if i in by_id)
    basis = Counter(by_id[i]["fmt"] for i in ids if i in by_id and not graph.get(i, {}).get("undecided"))
    return fm, (basis.most_common(1)[0][0] if basis else None)


def _slots(graph, asg_nodes, by_id):
    slots = defaultdict(list)
    for nid, a in asg_nodes.items():
        if nid in by_id and graph[nid]["role"] in ("heading", "title", "label"):
            slots[(a["template"], a["level"])].append(nid)
    return slots


def slot_pairs(nodes, graph, asg_nodes, labels, decided):
    """슬롯(템플릿 앵커, 레벨)마다 대표 서식 a 와 다른 서식 b 쌍 — 이미 그 슬롯에서 판정한 쌍(decided)은 뺌
    → [{slot, template, tplNo, level, a, aName, aCount, b, bName, bCount, examples}]."""
    by_id = {nd["id"]: nd for nd in nodes}
    out = []
    for (tn, level), ids in _slots(graph, asg_nodes, by_id).items():
        fm, a = _slot_rep(ids, by_id, graph)
        if len(fm) < 2 or a is None:
            continue
        slot = f"{tn}|L{level}"
        for b, bn in fm.most_common():
            if b == a or (slot, a, b) in decided or (slot, b, a) in decided:
                continue
            ex = [((by_id[i]["letter"] or "") + " " + by_id[i]["text"]).strip()[:50] for i in ids if by_id[i]["fmt"] == b][:3]
            out.append({"slot": slot, "template": tn, "tplNo": asg_nodes[ids[0]]["tplNo"], "level": level, "a": a, "aName": labels.get(a, {}).get("name", "")[:100],
                        "aCount": fm[a], "b": b, "bName": labels.get(b, {}).get("name", "")[:100], "bCount": bn, "examples": ex})
    return out


def c_jobs(pairs, pinned=None):
    jobs, used = [], {}
    for i in range(0, len(pairs), PAIR_BATCH):
        content, u = HL.prompt(HL.FORMAT_CONTRACT, ["templates", "tolerance"], {"pairs": pairs[i:i + PAIR_BATCH]}, pinned)
        used.update(u)
        jobs.append({"schema": HL.FORMAT_SCHEMA, "content": content, "what": f"heading_formats#{i // PAIR_BATCH + 1}", "timeout": 600.0, "effort": "low"})
    return jobs, used


# ---- D 호출(재검토 — 1차 조정 판정을 새 호출이 반박 검증) --------------------------------------------------

def _same_of(same, slot, a, b):
    """쌍의 같음 판정 — 그 슬롯의 답만(어느 순서로 적혔든). 다른 슬롯·전역 쌍 답은 재사용하지 않는다(astra 2026-11-09)."""
    return same.get((slot, a, b)) or same.get((slot, b, a))


def review_pairs(nodes, graph, asg_nodes, labels, same):
    """재검토 대상 — 모든 슬롯 서식 쌍에 1차 판정(C 의 same)을 붙인 것. 1차 판정이 없는 쌍(C 실패 — 어차피 미판정)은 뺀다."""
    out = []
    for p in slot_pairs(nodes, graph, asg_nodes, labels, set()):
        d = _same_of(same, p["slot"], p["a"], p["b"])
        if d:
            out.append({**p, "first": {"same": bool(d["same"]), "reason": d.get("reason", "")}})
    return out


def d_jobs(pairs, pinned=None):
    """재검토 호출 — 쌍 PAIR_BATCH 개씩, 1차(C: effort low)보다 깊게(effort medium). 호출마다 새 에이전트(세션 없음)라 1차 판정의 맥락을 모른다."""
    jobs, used = [], {}
    for i in range(0, len(pairs), PAIR_BATCH):
        batch = pairs[i:i + PAIR_BATCH]
        content, u = HL.prompt(HL.REVIEW_CONTRACT, ["templates", "tolerance"], {"pairs": batch}, pinned)
        used.update(u)
        jobs.append({"schema": HL.REVIEW_SCHEMA, "content": content, "what": f"heading_review#{i // PAIR_BATCH + 1}", "timeout": 600.0, "effort": "medium",
                     "_pairs": batch})
    return jobs, used


def apply_review(pairs, res):
    """D 응답 → {(slot, a, b): {verdict: agree|disagree|failed, same, reason}}. verdict 는 재검토의 same 과 1차 same 을 견줘 스크립트가 정한다
    (응답의 verdict 칸은 모델이 스스로 견주게 하는 장치 — 어긋나면 same 을 믿음). 답이 없는 쌍·호출 실패는 failed(1차 판정 유지). 답은 그 슬롯의 것만 쓴다."""
    got = {}
    for it in (res.get("data") or {}).get("pairs") or []:
        if it.get("a") and it.get("b"):
            got[(str(it.get("slot") or ""), it["a"], it["b"])] = it
    out = {}
    for p in pairs:
        key = (p["slot"], p["a"], p["b"])
        it = got.get(key)
        if it is None:
            out[key] = {"verdict": "failed", "same": None, "reason": str(res.get("error") or "재검토 답 없음")[:200]}
            continue
        s = bool(it.get("same"))
        out[key] = {"verdict": "agree" if s == bool(p["first"]["same"]) else "disagree", "same": s, "reason": str(it.get("reason") or "")[:200]}
    return out


# ---- 템플릿 슬롯 · 되풀이 · 이종 형제 · 조정 -------------------------------------------------------------------

def finish(nodes, graph, asg, types, labels, same, review=None):
    """배정 결과(asg = assign_templates) 에 슬롯 요약(대표 서식·유형)·되풀이·이종 형제·조정을 붙인다.
    review = D 호출의 재검토 {(slot, a, b): {verdict, same, reason}} — disagree 인 쌍의 조정은 미판정(undecided)으로 두고 1차 판정(first)·재검토를 함께 남긴다."""
    by_id = {nd["id"]: nd for nd in nodes}
    an = asg["nodes"]
    children = defaultdict(list)
    for g in graph.values():
        if g["role"] in ("not_heading", "note"):
            continue
        p = _eff_parent(g, graph)
        if p:
            children[p].append(g["id"])
    # 이종 형제 = 같은 의미 부모 아래 레터 키가 다른 헤딩·라벨 — 가지 템플릿이 뿌리를 내리는 자리
    hetero = []
    for p, kids in children.items():
        ks = {}
        for k in kids:
            if graph[k]["role"] in ("heading", "title", "label") and graph[k].get("key"):
                ks.setdefault(graph[k]["key"], []).append(k)
        if len(ks) > 1:
            hetero.append({"parent": p, "letters": [{"key": key, "type": graph[ids[0]]["type"], "shape": types.get(graph[ids[0]]["type"], {}).get("shape", key),
                                                     "count": len(ids)} for key, ids in ks.items()]})
    # 슬롯 요약
    slots = _slots(graph, an, by_id)
    templates = asg["templates"]
    by_anchor = {t["anchor"]: t for t in templates}
    by_tid = {t["id"]: t for t in templates}
    for (tn, level), ids in sorted(slots.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        t = by_anchor.get(tn)
        if t is None:
            continue
        fm, rep = _slot_rep(ids, by_id, graph)
        ty = Counter(graph[i]["type"] for i in ids)
        rep_id = next((i for i in ids if by_id[i]["fmt"] == rep), ids[0])
        t["slots"].append({"level": level, "letter": t["chain"][level - 1] if level - 1 < len(t["chain"]) else graph[ids[0]].get("key"), "count": len(ids),
                           "types": [{"type": k, "shape": types.get(k, {}).get("shape", ""), "count": n} for k, n in ty.most_common()],
                           "format": rep, "formats": dict(fm.most_common(5)), "rep": by_id[rep_id]["para"]})
    # 되풀이 = 같은 부모 아래 같은 템플릿 인스턴스 2개 이상
    groups = defaultdict(list)
    for ins in asg["instances"]:
        groups[(ins["parent"], ins["template"])].append(ins["root"])
    repeats = [{"parent": p, "template": t, "roots": roots, "signature": by_tid[t]["chain"], "count": len(roots)}
               for (p, t), roots in groups.items() if len(roots) >= 2 and t in by_tid]
    # 조정: 슬롯 대표 서식과 다른 서식 라벨 — C 의 슬롯별 판정만. D 재검토가 다르게 봤으면(disagree) 미판정으로 — 1차·재검토를 함께 남김
    adjustments = []
    review = review or {}
    for (tn, level), ids in slots.items():
        fm, rep = _slot_rep(ids, by_id, graph)
        if len(fm) < 2 or rep is None:
            continue
        slot = f"{tn}|L{level}"
        for i in ids:
            f = by_id[i]["fmt"] if i in by_id else None
            if not f or f == rep:
                continue
            d = _same_of(same, slot, rep, f)
            dec = "adjust" if d and d["same"] else "keep" if d else "undecided"
            adj = {"id": i, "para": graph[i]["para"], "template": tn, "tplNo": an[i]["tplNo"], "level": level, "from": f, "to": rep,
                   "decision": dec, "reason": (d or {}).get("reason", ""),
                   "fromName": labels.get(f, {}).get("name", ""), "toName": labels.get(rep, {}).get("name", "")}
            r = review.get((slot, rep, f)) or review.get((slot, f, rep))
            if r:
                adj["review"] = r
                if r["verdict"] == "disagree":
                    adj["first"] = dec
                    adj["decision"] = "undecided"
            adjustments.append(adj)
    return {"templates": templates, "instances": asg["instances"], "repeats": repeats[:200], "heterogeneous": hetero, "adjustments": adjustments}


# ---- 2단계 실행 ------------------------------------------------------------------------------------------

def build(stage1, *, use_llm=True, ask=None, doc_name="", pinned=None):
    """2단계 — 1단계 결과 → graph dict(spec ② §6). ask = llm.ask_all 대신(시험). use_llm False 면 스크립트 어림만.
    pinned = 실행 시작 때 고정한 지침(heading_guides.snapshot() 꼴 {이름: {text, sha1, …}}) — 주면 A·B·C·D 프롬프트가 그 글을 쓴다(§7)."""
    t0 = time.monotonic()
    ask = ask or llm.ask_all
    nodes = candidates(stage1)
    types = type_table(nodes)
    labels = stage1.get("labels") or {}
    calls, guides, info = [], {}, {"requested": bool(use_llm), "fallback": False, "error": None, "summary": "", "sections": 0, "applied": 0, "rejected": 0,
                                    "failedSections": 0}
    roles = fallback_roles(types)
    keys = type_keys(types, roles)
    proposal = propose_main(nodes, roles, keys, stage1) if nodes else []
    main_chain, fixed = proposal, False
    if use_llm and nodes:
        job, used, _ = a_job(types, nodes, keys, proposal, doc_name, pinned)
        guides.update(used)
        res = ask([job])[0]
        calls.append(HL._call_record(job, res))
        if res.get("data"):
            got, main = apply_types(res["data"], types)
            for tid in types:  # A 가 빠뜨린 유형은 어림 역할
                roles[tid] = got.get(tid) or {**roles[tid], "reason": "A 판정 없음 — 스크립트 대체"}
            keys = type_keys(types, roles)
            known = set(k for k in keys.values() if k)
            if main and all(k in known for k in main):
                main_chain, fixed = main, True
            elif main:
                info["mainChainRejected"] = main  # 모르는 레터가 든 주 사슬 — 제안으로 대신
            info["summary"] = str(res["data"].get("summary") or "")[:600]
        else:
            info["error"] = res.get("error") or "A 호출 실패"
            info["fallback"] = True
    elif not use_llm:
        info["fallback"] = True
    info["mainChain"], info["mainChainProposal"] = list(main_chain or []), list(proposal or [])
    graph, edges, containers = draft_parents(nodes, roles, keys, main_chain, stage1, trusted=fixed)
    changes, rejected = [], []
    if use_llm and not info["fallback"]:
        prov = assign_templates(nodes, graph, keys, main_chain, fixed)  # B 에 보일 초안 배정(앵커·레벨)
        anchors = {t["anchor"] for t in prov["templates"]}
        secs = sections(nodes, graph)
        info["sections"] = len(secs)
        jobs, used = b_jobs(secs, nodes, graph, prov, types, roles, keys, pinned)
        guides.update(used)
        results = ask([{k: v for k, v in j.items() if not k.startswith("_")} for j in jobs]) if jobs else []
        retry, batch = [], []
        for job, res in zip(jobs, results):
            calls.append(HL._call_record(job, res))
            if not res.get("data"):
                info["failedSections"] += 1
                for nid in job["_section"]:
                    graph[nid]["undecided"] = True
                continue
            ch = res["data"].get("changes") or []
            if len(ch) > CHANGE_RATE_RETRY * len(job["_section"]) and len(job["_section"]) >= 10:
                retry.append((job, ch))
                continue
            batch.append((job, ch))
        if retry:  # 변경률이 높은 구간은 한 번 더 묻고 둘째 답을 쓴다
            again = ask([{k: v for k, v in j.items() if not k.startswith("_")} for j, _ in retry])
            for (job, first), res in zip(retry, again):
                calls.append(HL._call_record(job, res))
                ch = (res.get("data") or {}).get("changes")
                batch.append((job, ch if ch is not None else first))
        for job, ch in batch:  # 모든 구간의 답을 같은 초안에 대해 모아 적용(부모 변경 보존)
            a, r = apply_changes(ch, job["_section"], job["_ancestors"], graph, anchors)
            changes += a
            rejected += r
        info["applied"], info["rejected"] = len(changes), len(rejected)
    for g in graph.values():
        g["division"] = _division_of(g["id"], graph)
    edges = [e for e in edges if e["t"] not in ("parent", "division") or e["to"] not in graph] + \
        [{"t": "parent", "from": g["parent"], "to": g["id"]} for g in graph.values() if g.get("parent")] + \
        [{"t": "division", "from": g["division"], "to": g["id"]} for g in graph.values() if g.get("division")]
    edges = _dedupe(edges)
    asg = assign_templates(nodes, graph, keys, main_chain, fixed)  # 확정 트리 → 사슬·슬롯·인스턴스 → id 동결
    info["ties"], info["mainChainConflicts"], info["slotUnresolved"] = asg["ties"][:50], asg["conflicts"][:50], asg["unresolved"][:50]
    same = {}
    if use_llm and not info["fallback"]:  # C: 슬롯 서식 쌍 — 조정 판단(슬롯마다)
        pairs = slot_pairs(nodes, graph, asg["nodes"], labels, set())
        info["formatPairs"] = len(pairs)
        if pairs:
            jobs, used = c_jobs(pairs, pinned)
            guides.update(used)
            for job, res in zip(jobs, ask(jobs)):
                calls.append(HL._call_record(job, res))
                for it in (res.get("data") or {}).get("pairs") or []:
                    if it.get("a") and it.get("b") and it.get("slot"):
                        same[(str(it["slot"]), it["a"], it["b"])] = {"same": bool(it.get("same")), "reason": str(it.get("reason") or "")[:200]}
    review = {}
    if use_llm and not info["fallback"]:  # D: 재검토 — 1차 조정 판정(C)을 새 호출(1차 맥락이 없는 다른 에이전트)이 반박 검증(2026-11-09 사용자)
        todo = review_pairs(nodes, graph, asg["nodes"], labels, same)
        info["reviewPairs"] = len(todo)
        if todo:
            jobs, used = d_jobs(todo, pinned)
            guides.update(used)
            for job, res in zip(jobs, ask([{k: v for k, v in j.items() if not k.startswith("_")} for j in jobs])):
                calls.append(HL._call_record(job, res))
                review.update(apply_review(job["_pairs"], res))
        info["reviewFailed"] = sum(1 for r in review.values() if r["verdict"] == "failed")
        info["reviewDisagree"] = sum(1 for r in review.values() if r["verdict"] == "disagree")
    fin = finish(nodes, graph, asg, types, labels, same, review)
    out_nodes = []
    for nd in nodes:
        g = graph.get(nd["id"]) or {}
        a = asg["nodes"].get(nd["id"]) or {}
        out_nodes.append({"id": nd["id"], "para": nd["para"], "span": nd["span"], "n": nd["n"], "area": nd["area"], "flow": nd["flow"], "type": nd["type"],
                          "kind": nd["kind"], "letter": nd["letter"], "shape": nd["shape"], "key": g.get("key"), "text": nd["text"], "blank": nd["blank"],
                          "lead": nd["lead"], "fmt": nd["fmt"], "role": g.get("role"), "template": a.get("template"), "tplNo": a.get("tplNo"),
                          "level": a.get("level"), "instance": a.get("instance"), "parent": g.get("parent"), "division": g.get("division"),
                          "sourceOutlineLevel": nd.get("outline"), "changed": g.get("changed", False), "undecided": g.get("undecided", False),
                          "heuristic": g.get("heuristic", False), "reason": g.get("reason", "")})
    edges += [{"t": "instance", "from": ins["root"], "to": f"tpl:{ins['template']}"} for ins in fin["instances"]]
    cost = sum((c.get("costUsd") or 0) for c in calls)
    return {"version": 2, "nodes": out_nodes, "containers": list(containers.values()), "edges": edges,
            "types": [{**t, **(roles.get(tid) or {}), "key": keys.get(tid)} for tid, t in types.items()],
            **fin, "changes": changes, "rejected": rejected,
            "counts": {"nodes": len(out_nodes), "body": sum(1 for n in out_nodes if n["flow"] == "body"), "cell": sum(1 for n in out_nodes if n["flow"].startswith("cell:")),  # 칸 안 상자 포함
                       "types": len(types), "templates": len(fin["templates"]), "branches": sum(1 for t in fin["templates"] if t["kind"] == "branch"),
                       "labelTemplates": sum(1 for t in fin["templates"] if t["kind"] == "label"), "instances": len(fin["instances"]), "repeats": len(fin["repeats"]),
                       "heterogeneous": len(fin["heterogeneous"]), "adjust": sum(1 for a in fin["adjustments"] if a["decision"] == "adjust"),
                       "reviewed": sum(1 for a in fin["adjustments"] if (a.get("review") or {}).get("verdict") in ("agree", "disagree")),
                       "disagreed": sum(1 for a in fin["adjustments"] if (a.get("review") or {}).get("verdict") == "disagree"),
                       "changed": len(changes), "undecided": sum(1 for n in out_nodes if n["undecided"]), "heuristic": sum(1 for n in out_nodes if n["heuristic"])},
            "llm": {**info, "calls": len(calls), "failed": sum(1 for c in calls if c["response"] is None), "costUsd": round(cost, 4),
                    "seconds": round(time.monotonic() - t0, 2)},
            "guides": guides, "_calls": calls}


def _dedupe(edges):
    seen, out = set(), []
    for e in edges:
        k = (e["t"], e["from"], e["to"])
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out

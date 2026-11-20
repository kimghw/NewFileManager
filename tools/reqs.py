"""사용자 요구사항(reqs/requirements.json — spec_워크플로우 ② §18-20)을 명령 줄에서 보고 적는다 — 코드 에이전트가 대화에서 받은 요구사항을 적을 때 쓴다(화면은 /workflow 의 「요구사항」 열).

    python -X utf8 tools/reqs.py check                      # 파일의 꼴 · 대상이 등록부에 있는지(tests/test_user_reqs.py 가 같은 것을 본다)
    python -X utf8 tools/reqs.py targets [글]               # 대상의 키와 이름(글이 든 것만) — 적기 전에 키를 찾는다
    python -X utf8 tools/reqs.py list [대상 | 상태]         # 적힌 요구사항(대상 = tool:relay.heads … · 상태 = open · done · hold)
    python -X utf8 tools/reqs.py add --to 대상 [--to 대상 …] --said "사용자가 한 말" [--note "정리"] [--spec "사양서 자리"] [--state open|done|hold] [--date YYYY-MM-DD]
    python -X utf8 tools/reqs.py set <id> [--state …] [--note …] [--spec …] [--date …] [--said …] [--to 대상 …(대상을 이것들로 바꾼다)]

적는 것은 사용자가 한 말 그대로(`said`)와 정리(`note` — 어떻게 정했나 · 어디에 반영했나)다. 저장소 파일을 고친다(NFM_REQS 가 걸려 있으면 그 파일)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import user_reqs as R  # noqa: E402
from app import user_reqs_api as A  # noqa: E402


def problems():
    """파일의 문제 [글 …] — 꼴이 아닌 항목 · 등록부에 없는 대상(이 PC 에서 조립한 워크플로우 u_… 는 다른 PC 에 없으니 보지 않는다) · 손으로 고쳐 어긋난 줄 꼴."""
    import json
    p = R.path()
    if p is None or not p.is_file():
        return []
    text = p.read_text(encoding="utf-8")
    raw, data, have, out = json.loads(text), R.load(), A.targets(), []
    kept = {it["id"] for it in data["items"]}
    out += [f"꼴이 아닌 항목(읽을 때 빠진다): {x.get('id') if isinstance(x, dict) else x!r}" for x in raw.get("items", []) if not (isinstance(x, dict) and x.get("id") in kept)]
    if len(kept) != len([x for x in raw.get("items", []) if isinstance(x, dict) and x.get("id") in kept]):
        out.append("같은 id 가 두 번 있습니다")
    for it in data["items"]:
        out += [f"{it['id']}: 등록부에 없는 대상 {t}" for t in it["targets"] if t not in have and not local(t)]
    if not out and R.dumps(data) != text:
        out.append("줄 꼴이 다릅니다(항목 하나가 한 줄 — tools/reqs.py set 으로 고치거나 app.user_reqs.dumps 의 꼴로)")
    return out


def local(target):
    """이 PC 에서 조립한 워크플로우(키 u_…)의 대상인가 — 그 정의는 저장소에 없다."""
    return target.startswith(("flow:u_", "stage:u_"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    t = sub.add_parser("targets"); t.add_argument("text", nargs="?", default="")
    ls = sub.add_parser("list"); ls.add_argument("what", nargs="?", default="")
    ad = sub.add_parser("add")
    ad.add_argument("--to", action="append", required=True); ad.add_argument("--said", required=True)
    st = sub.add_parser("set"); st.add_argument("id"); st.add_argument("--to", action="append"); st.add_argument("--said")
    for p in (ad, st):
        p.add_argument("--note"); p.add_argument("--spec"); p.add_argument("--state", choices=R.STATES); p.add_argument("--date")
    a = ap.parse_args()
    if a.cmd == "check":
        bad = problems()
        print("\n".join(bad) if bad else f"문제 없음 — 요구사항 {len(R.load()['items'])}건")
        return 1 if bad else 0
    if a.cmd == "targets":
        for k, v in A.targets().items():
            if a.text in k or a.text in v["name"] or a.text in v["group"]:
                print(f"{k:34} {v['name']}  ({v['group']})")
        return 0
    if a.cmd == "list":
        names = A.targets()
        for it in R.load()["items"]:
            if a.what and a.what != it["state"] and a.what not in it["targets"]:
                continue
            print(f"{it['id']}  {it['date']}  [{R.STATE_NAME[it['state']]}]  {it['said']}\n      → {', '.join((names.get(t) or {}).get('name', t) for t in it['targets'])}" + (f"\n      정리: {it['note']}" if it["note"] else ""))
        return 0
    body = {k: v for k, v in (("note", a.note), ("spec", a.spec), ("state", a.state), ("date", a.date)) if v is not None}
    gone = [t for t in a.to or [] if t not in A.targets()]
    if gone:
        print(f"등록부에 없는 대상: {', '.join(gone)} — tools/reqs.py targets 로 키를 찾으세요")
        return 1
    if a.cmd == "add":
        item = R.add({**body, "targets": a.to, "said": a.said}, "chat")
    else:
        item = R.edit(a.id, {**body, **({"targets": a.to} if a.to else {}), **({"said": a.said} if a.said is not None else {})})
        if item is None:
            print("그런 요구사항이 없습니다")
            return 1
    print(f"{item['id']}  {item['date']}  [{R.STATE_NAME[item['state']]}]  {item['said']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValueError as e:
        print(e)
        sys.exit(1)

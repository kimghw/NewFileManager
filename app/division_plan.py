"""변경계획(spec_구분_기준 ② §3·§7) — 작업용 사본에서 전체 반영을 **모의 실행**해 계획을 확정한다(중첩 복제로 새로 생기는 안쪽 자리까지 미리보기와 일치).
계획 = 반영 전 후보(프로파일 candidates) + 사본에 apply 한 보고 + 반영 뒤 후보로 매긴 상태 + 지워진 글 + 고정한 문서 버전(baseRev·sha256·프로파일 버전·설정 해시).
서버는 계획의 사본 문서(_doc)를 반영 때 그대로 세션 문서로 바꿔 넣는다(두 번 돌리지 않음 — 결정적 엔진이라도 다시 돌리면 시간이 두 배). 사본은 JSON 에 안 나간다."""
import time
import uuid

from app import division_model as model
from app import verify
from app.division_profiles import _structure as structure

CHANGES_MAX, DELETED_MAX = 600, 400


def snapshot_copy(kit, original, doc):
    """지금 문서의 독립 사본(실행 취소 묶음과 같은 길 — struct.snapshot/restore: 같은 블록 id·원본 기준)."""
    st = kit["struct"]
    snap = st.snapshot(doc)
    return st.restore(kit["cls"], original, snap), snap


def make(kit, original, doc, rev, settings, profile, *, only=None, skip=(), rebuild=True, copy=None, hints=None, prior=None):
    """-> 계획 dict(JSON 으로 낼 것 + 비공개 키 _doc·_report). copy = snapshot_copy() 결과 (copy, snap) — 잠금 안에서 떠 두고 밖에서 돌릴 때.
    hints = 추가한 자리 문단 id 들(② §11 — 후보 찾기·모의 실행 모두에). prior = 앞서 이 문서에 반영한 값들(② §19 — 후보 찾기·모의 실행 모두에:
    그 값의 이름·연도가 적힌 자리는 반영이 쓴 것으로 보아 새 값으로 다시 쓴다). 지원하지 않는 양식이면 ValueError."""
    skip = set(skip or ())
    hints = sorted(hints or ())
    blocks = doc.blocks()
    form = profile.form_of(blocks)
    if not profile.supported(form):
        raise ValueError(f"지원하는 양식이 아닙니다(앞쪽에 양식 이름 문단이 없음 — 지원: {', '.join(sorted(profile.SUPPORTED))})")
    values = settings["values"]
    lv = profile.levels_of(blocks)
    before = profile.candidates(blocks, lv, values, rebuild=rebuild, skip=skip, hints=hints, prior=prior)
    idx_before = structure.index_blocks(blocks)
    work, snap = copy if copy is not None else snapshot_copy(kit, original, doc)
    t0 = time.monotonic()
    report = profile.apply(work, values, skip=sorted(skip), levels_of=profile.levels_of, only=only, rebuild=rebuild, hints=hints, prior=prior)
    seconds = round(time.monotonic() - t0, 2)
    after_blocks = work.blocks()
    idx_after = structure.index_blocks(after_blocks)
    after = profile.candidates(after_blocks, profile.levels_of(after_blocks), values, rebuild=False, skip=skip, hints=hints, prior=prior)
    after_by_key = {c["key"]: c for c in after}
    errors = {e["key"]: e["message"] for e in report.get("errors") or () if e.get("key")}
    attached = set(idx_after)
    touched = {g.get("key") for g in report.get("groups") or ()}   # 모의 실행이 실제로 손댄 묶음(고른 자리와 그 안쪽 자리)
    cands = []
    for c in before:
        status, message = model.status_of(c, after_by_key, attached, errors, skip)
        if only is not None and status == "applied" and c["key"] != only and not c.get("nested"):
            status, message = ("already", "이미 맞음") if c.get("done") else ("excluded", "이번엔 한 자리만 반영")
        elif only is not None and status == "unresolved" and c["key"] != only and c["key"] not in errors and c["key"] not in touched:
            # 한 자리만의 계획에서 손대지 않은 다른 자리 — 「반영 뒤에도 수가 맞지 않음」 이 아니라 이번에 안 한 것이다
            # (2026-11-19 표 메뉴 「프로젝트 구성에 맞추기」 가 이 길을 처음 쓰며 드러남: 견본 양식에서 한 자리 계획에 미해결 85 — spec_테이블매니저 ② §9)
            status, message = "excluded", "이번엔 한 자리만 반영"
        cands.append({**c, "status": status, "statusMessage": message, "dimName": profile.DIM_NAME.get(c["dim"], c["dim"]),
                      "kindName": profile.KIND_NAME.get(c["kind"], c["kind"])})
    deleted = [{"id": i, "text": _short(b.get("text"))} for i, b in idx_before.items()
               if i not in idx_after and b.get("type") == "paragraph" and (b.get("text") or "").strip()]
    new_ids = [i for i in idx_after if i not in idx_before]
    origin = {}
    for t in (report.get("tables") or {}).values():
        origin.update(t.get("origin") or {})
    summary = model.summarize(cands, report) | {"seconds": seconds, "deleted": len(deleted), "new": len(new_ids), "form": form}
    plan = {"planId": uuid.uuid4().hex[:10], "baseRev": rev, "sha256": verify_sha(snap["bytes"]), "profileId": profile.ID,
            "profileVersion": profile.VERSION, "settingsHash": model.settings_hash(settings), "values": values, "only": only, "skip": sorted(skip),
            "form": form, "createdAt": time.time(), "candidates": cands, "summary": summary, "hints": hints,
            "changes": [c for c in report.get("changes") or ()][:CHANGES_MAX], "deleted": deleted[:DELETED_MAX],
            "errors": report.get("errors") or [], "unresolved": [c["key"] for c in cands if c["status"] == "unresolved"],
            "_doc": work, "_report": report, "_origin": origin, "_new": new_ids}
    return plan


def view(plan):
    """JSON 으로 낼 계획(비공개 키 뺌)."""
    return {k: v for k, v in plan.items() if not k.startswith("_")}


def brief(plan):
    """GET …/divisions 가 보이는 요약(후보·변경 목록 없이)."""
    return {k: plan[k] for k in ("planId", "baseRev", "sha256", "profileId", "profileVersion", "settingsHash", "only", "skip", "form", "createdAt", "summary")}


def verify_sha(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _short(text, n=80):
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[:n] + "…"


def flat_texts(blocks):
    return verify.flat_texts(blocks)

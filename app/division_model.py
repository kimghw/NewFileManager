"""구분 기준 — 4층 계약(spec_구분_기준 ② §2): 설정 · 후보 자리 · 변경계획 · 적용 결과. 프로파일(app/division_profiles)을 인자로 받고 그 안을 모른다.

설정(settings) = {"schemaVersion", "profileId", "profileVersion", "values": 프로파일이 정리한 값} — 저장 꼴은 프로파일의 값(국가R&D 는 FMM v1 values 와 같은 꼴)이고,
구분 값 id·부모·속성·역할의 파생 뷰는 profile.dimensions(values). FMM 값(JSON)은 import_fmm_v1 로 설정이 된다.
후보 자리 상태(② §2 「적용 결과」): applied(이번 반영이 고침) · already(이미 맞음) · excluded(사용자가 뺌) · unsupported(irregular·blocked·unset — 지금은 못 고침) ·
unresolved(고치려 했으나 끝까지 못 맞춤 — 오류·잔여)."""
import hashlib
import json
import time
import uuid

SCHEMA_VERSION = 1
STATUSES = ("applied", "already", "excluded", "unsupported", "unresolved")
UNSUPPORTED_REASONS = {"irregular": "같은 꼴 라벨이 차례를 어김(손댄 문서)", "named": "구분 값에 없는 기관 이름이 적혀 있음(작성한 문서로 보고 그대로)", "blocked": "병합 칸 때문에 표를 못 고침", "unset": "값을 정하지 않아 그대로 둠",
                       "stage": "지워질 단계 안(바깥 단계가 먼저 줄임)"}


def norm_settings(body, profile):
    """{"profileId"?, "values"} 또는 FMM v1 값 자체 → 설정. 틀리면 ValueError(문구는 화면에 그대로)."""
    if not isinstance(body, dict):
        raise ValueError("설정은 객체여야 합니다")
    pid = body.get("profileId", profile.ID)
    if pid != profile.ID:
        raise ValueError(f"프로파일이 다릅니다: {pid} ≠ {profile.ID}")
    values = body["values"] if "values" in body else body
    return {"schemaVersion": SCHEMA_VERSION, "profileId": profile.ID, "profileVersion": profile.VERSION, "values": profile.norm_values(values)}


def import_fmm_v1(values, profile):
    """FileMergeManager 의 구분 값(spec_구분_초기화 ② §5 values JSON)·프리셋 값 → 설정. 뜻을 보존한다(subs = 세부과제 주관기관 이름, current = 전체 차례 — 파생 뷰가 id 로)."""
    return norm_settings({"values": values}, profile)


HINT_DIMS = {"stage": "단계", "year": "차년도", "stageYear": "단계-차년도", "sub": "세부과제", "org": "기관"}   # 그 밖의 dim 글 = 기타(표시만, ② §11)


def norm_hint(body, idx, profile, old=None):
    """추가한 자리(② §11) 하나 검사·정리 — {id, para, dim, value, note, by, at, reason}. para 는 문서의 문단 id 여야 함.
    value 가 비면 글에서 읽은 값(profile.hint_read). old = 같은 자리의 이전 hint(id·출처·때 유지). 틀리면 ValueError."""
    if not isinstance(body, dict):
        raise ValueError("hint 가 필요합니다")
    para = str(body.get("para") or "").strip()
    b = idx.get(para)
    if b is None or b.get("type") != "paragraph":
        raise ValueError("문단 id 가 문서에 없습니다(지워졌거나 표 칸·표 id)")
    dim = str(body.get("dim") or "").strip()[:40]
    if not dim:
        raise ValueError("구분 기준을 고르세요")
    read = profile.hint_read(b.get("text"))
    value = str(body.get("value") or "").strip()[:60] or (read["value"] if read else "")
    old = old or {}
    return {"id": old.get("id") or uuid.uuid4().hex[:8], "para": para, "dim": dim, "value": value, "note": str(body.get("note") or "").strip()[:200],
            "by": old.get("by") or "user", "at": old.get("at") or time.time(), "reason": old.get("reason") or ""}


def settings_hash(settings):
    return hashlib.sha256(json.dumps(settings, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def status_of(before, after_by_key, attached, errors, skip):
    """후보 하나의 상태 — before = 반영 전 후보(spot), after_by_key = 반영 뒤 같은 key 의 후보, attached = 반영 뒤에도 남은 블록 id 집합,
    errors = {key: 메시지}, skip = 뺀 key 집합. -> (status, message)."""
    key = before["key"]
    if key in skip:
        return "excluded", "사용자가 뺌"
    if key in errors:
        return "unresolved", errors[key]
    if before.get("done"):
        return "already", "이미 맞음"
    if key != "period" and key not in attached:   # 첫 라벨이 사라짐 = 바깥 묶음이 이 항목째 지움(자리표시 단계 안 등)
        return "applied", "바깥 묶음이 지움"
    after = after_by_key.get(key)
    if after is None:
        return ("applied", "맞춤") if before.get("reason") not in UNSUPPORTED_REASONS else ("unsupported", UNSUPPORTED_REASONS[before["reason"]])
    if after.get("done"):
        return "applied", "맞춤"
    if after.get("reason") in UNSUPPORTED_REASONS:
        return "unsupported", after.get("message") or UNSUPPORTED_REASONS[after["reason"]]
    return "unresolved", after.get("message") or "반영 뒤에도 수가 맞지 않음"


def summarize(candidates, report):
    out = {s: 0 for s in STATUSES}
    for c in candidates:
        out[c["status"]] += 1
    return {**out, "groups": len(report.get("groups") or ()), "added": report.get("added", 0), "removed": report.get("removed", 0),
            "passes": report.get("passes", 0), "changes": len(report.get("changes") or ()), "errors": len(report.get("errors") or ())}

"""구분 기준 프로파일(spec_구분_기준 ② §0·§9) — 문서 종류(양식 군)마다의 정책 묶음. 1차 = 국가R&D(`rnd`)."""
from app.division_profiles import rnd

PROFILES = {rnd.ID: rnd}


def get(profile_id):
    """없는 id 면 KeyError."""
    return PROFILES[profile_id]

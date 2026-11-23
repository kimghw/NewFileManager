"""비신뢰 zip 패키지 한도(spec_왕복_어댑터 ② §1 「비신뢰 패키지 한도」, 검토 U03 + 구현 검토).

어댑터 생성자가 zip 을 연 직후, 멤버를 읽기 전에 `infolist()` 만 보고 검사하고(`check`), 멤버는 `read` 의 조각 읽기로만 푼다
(파서로 넘기는 멤버는 이름과 무관하게 XML 상한을 보는 `read_xml`). `ZipFile.read()` 는 압축 스트림을 먼저 끝까지 해제하므로, 선언 크기
합은 조각 읽기와 함께일 때만 메모리 상한이 된다. `ZipExtFile` 은 선언된 `file_size` 에서 끊어 뒤에 남는 압축 데이터를 보지 않으므로
(재검토 — 선언 12 바이트 뒤로 32 MiB 가 이어지는 위조 멤버가 통과) `read` 는 압축 스트림을 직접 풀어 스트림이 선언 크기에서 끝나는지까지
본다(references/Python_파서_제약.md 「zipfile 해제 크기」).
"""
import copy
import logging
import os
import zipfile
import zlib

log = logging.getLogger(__name__)

_MIB = 1 << 20
_METHODS = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
_XML = (".xml", ".rels", ".hpf")   # 어댑터가 lxml 로 읽는 멤버(hwpx header·section·content.hpf, docx 각 part·관계)


def _limit(name, default):
    """환경 변수 정수 한도 — 비었으면 기본값, 정수가 아니거나 1 미만이면 경고를 남기고 기본값(잘못 둔 값 하나로 모든 문서가 안 열리지 않게)."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        log.warning("env %s=%r 이 1 이상의 정수가 아니라 기본값 %s 을 씁니다", name, raw, default)
        return default
    return value


def check(zf):
    """멤버 수 ≤ FMM_ZIP_MAX_MEMBERS(기본 10,000), 선언 해제 크기 합 ≤ FMM_ZIP_MAX_MB(기본 4,096 MiB — 2026-11-23 올리기 한도를 2 GiB 로 올리며 1,024 에서: 그림이 든 hwpx 는 해제 크기가 파일 크기와 비슷하다), 압축 방식은 STORED·DEFLATED 만,
    파서로 읽는 XML 멤버(.xml·.rels·.hpf) 하나 ≤ FMM_ZIP_MAX_XML_MB(기본 128) MiB — 넘으면 ValueError. 한도는 부를 때마다 환경 변수에서
    읽는다. 압축률은 보지 않는다 — 실제 해제량은 `read` 의 조각 읽기가 묶고, 흰 바탕 BMP 는 300:1 을 넘는다."""
    infos = zf.infolist()
    max_members = _limit("FMM_ZIP_MAX_MEMBERS", 10000)
    if len(infos) > max_members:
        raise ValueError(f"zip 멤버가 너무 많음({len(infos)}개 > {max_members}개)")
    max_mb = _limit("FMM_ZIP_MAX_MB", 4096)
    total = sum(zi.file_size for zi in infos)
    if total > max_mb * _MIB:
        raise ValueError(f"zip 해제 크기가 너무 큼({total / _MIB:.1f}MB > {max_mb}MB)")
    max_xml = _limit("FMM_ZIP_MAX_XML_MB", 128)
    for zi in infos:
        if zi.compress_type not in _METHODS:
            raise ValueError(f"zip 멤버 압축 방식이 STORED·DEFLATED 가 아님({zi.filename}: {zi.compress_type})")
        if zi.filename.lower().endswith(_XML):   # 이름으로 먼저 거르기만 — 파서로 넘기는 멤버는 이름과 무관하게 read_xml 이 다시 본다
            _xml_cap(zi, max_xml)


def _xml_cap(info, max_xml):
    if info.file_size > max_xml * _MIB:
        raise ValueError(f"zip XML 멤버가 너무 큼({info.filename}: {info.file_size / _MIB:.1f}MB > {max_xml}MB)")


def _info(zf, member):
    return zf.getinfo(member) if isinstance(member, str) else member


def read_xml(zf, member):
    """파서(lxml)로 넘길 멤버 바이트 — 이름(확장자)과 무관하게 선언 크기 ≤ FMM_ZIP_MAX_XML_MB(기본 128) MiB 를 보고 `read` 로 읽는다
    (재검토 — `word/document.dat` 로 이름을 바꾼 주 문서가 `check` 의 확장자 검사를 피했다). `read` 가 실제 길이를 선언과 맞춰 보므로
    선언 크기가 곧 파서 입력 크기. 넘으면 ValueError."""
    info = _info(zf, member)
    _xml_cap(info, _limit("FMM_ZIP_MAX_XML_MB", 128))
    return read(zf, info)


def _inflate(f, info):
    """f(압축 바이트 그대로) 의 deflate 스트림을 선언 크기까지 푼다 — 한 번에 내는 해제량은 min(1 MiB, 남은 선언 + 1) 바이트라 패딩을
    풀지 않고, 스트림이 선언 크기에서 끝나고(eof) 그 뒤로 남는 압축 바이트가 없어야(compress_size 를 다 씀) 한다."""
    d = zlib.decompressobj(-zlib.MAX_WBITS)
    out, data, done = bytearray(), b"", False
    while not d.eof:
        if not data and not done:
            data = f.read(_MIB)
            done = not data                       # compress_size 를 다 읽음 — 이제 zlib 안에 남은 것만 내보낸다
        piece = d.decompress(data, min(_MIB, info.file_size - len(out) + 1))
        data = d.unconsumed_tail
        out += piece
        if len(out) > info.file_size:
            raise ValueError(f"zip 멤버 압축 스트림이 선언 크기보다 김({info.filename}: > {info.file_size})")
        if done and not piece:
            raise ValueError(f"zip 멤버 압축 스트림이 끝나지 않음({info.filename})")
    if d.unused_data or data or f.read(1):
        raise ValueError(f"zip 멤버 압축 스트림 뒤에 남는 압축 데이터({info.filename})")
    return out


def read(zf, member):
    """멤버 바이트 — 1 MiB 조각으로 선언 크기까지만 해제한다. `ZipFile.read()` 는 멤버 압축 데이터를 한 번에 다 해제한 뒤 선언 크기로
    자르므로(선언을 작게 속인 65 KB 멤버가 141 MiB) 업로드 패키지에는 쓰지 않는다(② §1, 11-01 구현 검토). 실제 길이·CRC 가 선언과
    다르거나, 스트림이 깨졌거나, 압축 스트림이 선언 크기에서 끝나지 않으면(뒤에 남는 압축 데이터 — 재검토) ValueError. STORED 는
    compress_size == file_size, DEFLATED 만 푼다, 암호 멤버는 거부."""
    info = _info(zf, member)
    if info.compress_type not in _METHODS:   # check 를 거치지 않는 호출(렌더 사본)에서도
        raise ValueError(f"zip 멤버 압축 방식이 STORED·DEFLATED 가 아님({info.filename}: {info.compress_type})")
    if info.flag_bits & 0x1:
        raise ValueError(f"zip 멤버가 암호화됨({info.filename})")
    if info.compress_type == zipfile.ZIP_STORED and info.compress_size != info.file_size:
        raise ValueError(f"zip 멤버 크기가 선언과 다름({info.filename}: 저장 {info.compress_size} ≠ {info.file_size})")
    # 압축 바이트를 그대로 내주는 사본(STORED·크기 compress_size·CRC 검사 없음)으로 연다 — zf.open 의 로컬 헤더·이름 대조·겹친 항목
    # 검사·잘린 파일(EOFError)·잠금은 그대로 쓰고, 해제와 CRC 는 여기서 한다. CRC=None 이면 ZipExtFile 이 CRC 를 보지 않는다(3.12 확인).
    raw = copy.copy(info)
    raw.compress_type, raw.file_size, raw.CRC = zipfile.ZIP_STORED, info.compress_size, None
    try:
        with zf.open(raw) as f:
            if info.compress_type == zipfile.ZIP_DEFLATED:
                out = _inflate(f, info)
            else:
                out = bytearray()
                while chunk := f.read(_MIB):
                    out += chunk
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError) as e:
        # 깨진 압축 스트림·잘린 파일·로컬 헤더 불일치·겹친 항목 — 모두 「열 수 없는 멤버」(서버 400)
        raise ValueError(f"zip 멤버를 읽을 수 없음({info.filename}: {e})") from e
    if len(out) != info.file_size:
        raise ValueError(f"zip 멤버 크기가 선언과 다름({info.filename}: {len(out)} ≠ {info.file_size})")
    if zlib.crc32(out) != info.CRC:
        raise ValueError(f"zip 멤버 CRC 가 선언과 다름({info.filename})")
    return bytes(out)

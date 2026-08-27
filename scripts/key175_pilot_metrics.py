"""KEY-175 Pilot 관측 메트릭 산출 스크립트.

OCR·LLM 외부 호출 로그에서 P50/P95와 실패율을 재현 가능하게 산출한다.

사용법:
    # 단일 파일
    python scripts/key175_pilot_metrics.py --log path/to/worker.log

    # 여러 파일 (글로브)
    python scripts/key175_pilot_metrics.py --log "logs/*.log"

    # stdin 파이프
    cat worker.log app.log | python scripts/key175_pilot_metrics.py

파싱 대상 로그 형식:
    OCR : ocr_job_complete mode=... elapsed_ms=... clova_elapsed_ms=... error_code=... ocr_job_id=...
    LLM : chatbot_generation model=... success=... latency_ms=... cost_usd=... reason=...

주의:
    환자정보·OCR 원문·프롬프트·비밀값은 로그에 남지 않으므로 이 스크립트도 출력하지 않는다.
    ocr_job_id는 식별용으로만 사용하며 환자 식별에 사용할 수 없다.
"""

import argparse
import glob
import re
import sys
from collections import Counter
from typing import NamedTuple

_KV = re.compile(r"(\w+)=(\S+)")


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------


class OcrRecord(NamedTuple):
    mode: str  # clova | fixture | failed
    elapsed_ms: int
    clova_elapsed_ms: int | None
    error_code: str | None


class LlmRecord(NamedTuple):
    model: str
    success: bool
    latency_ms: int
    reason: str | None


# ---------------------------------------------------------------------------
# 파싱
# ---------------------------------------------------------------------------


def _kv(line: str, after: str) -> dict[str, str]:
    return dict(_KV.findall(line.split(after, 1)[1]))


def _parse_ocr(line: str) -> OcrRecord | None:
    if "ocr_job_complete" not in line:
        return None
    try:
        kv = _kv(line, "ocr_job_complete")
        mode = kv.get("mode", "")
        elapsed_ms = int(kv.get("elapsed_ms", "0"))
        raw_clova = kv.get("clova_elapsed_ms", "none")
        clova_elapsed_ms = None if raw_clova == "none" else int(raw_clova)
        raw_err = kv.get("error_code", "none")
        error_code = None if raw_err == "none" else raw_err
        return OcrRecord(mode=mode, elapsed_ms=elapsed_ms, clova_elapsed_ms=clova_elapsed_ms, error_code=error_code)
    except (ValueError, KeyError, IndexError):
        return None


def _parse_llm(line: str) -> LlmRecord | None:
    if "chatbot_generation" not in line:
        return None
    try:
        kv = _kv(line, "chatbot_generation")
        model = kv.get("model", "unknown")
        success = kv.get("success", "False") == "True"
        latency_ms = int(kv.get("latency_ms", "0"))
        raw_reason = kv.get("reason", "none")
        reason = None if raw_reason == "none" else raw_reason
        return LlmRecord(model=model, success=success, latency_ms=latency_ms, reason=reason)
    except (ValueError, KeyError, IndexError):
        return None


def collect(lines: list[str]) -> tuple[list[OcrRecord], list[LlmRecord]]:
    ocr_records: list[OcrRecord] = []
    llm_records: list[LlmRecord] = []
    for line in lines:
        if ocr_r := _parse_ocr(line):
            ocr_records.append(ocr_r)
        if llm_r := _parse_llm(line):
            llm_records.append(llm_r)
    return ocr_records, llm_records


# ---------------------------------------------------------------------------
# 통계
# ---------------------------------------------------------------------------


def _pct(values: list[int], p: float) -> int:
    """p 백분위수 (선형 보간)."""
    if not values:
        return 0
    sv = sorted(values)
    idx = (len(sv) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(sv) - 1)
    return round(sv[lo] + (sv[hi] - sv[lo]) * (idx - lo))


def _fmt(ms: int) -> str:
    return f"{ms}ms" if ms < 1000 else f"{ms / 1000:.2f}s"


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------


def _sep(char: str = "─", width: int = 60) -> None:
    print(char * width)


def report_ocr(records: list[OcrRecord]) -> None:
    _sep()
    print("  OCR (ocr_job_complete)")
    _sep()
    if not records:
        print("  기록 없음")
        return

    total = len(records)
    clova = [r for r in records if r.mode == "clova"]
    fixture = [r for r in records if r.mode == "fixture"]
    failed = [r for r in records if r.mode == "failed"]

    print(f"  전체        {total}건")
    print(f"  성공(CLOVA) {len(clova)}건")
    print(f"  fallback    {len(fixture)}건  ({len(fixture) / total * 100:.1f}%)")
    print(f"  실패        {len(failed)}건  ({len(failed) / total * 100:.1f}%)")

    if clova:
        elapsed = [r.elapsed_ms for r in clova]
        print()
        print(
            f"  elapsed_ms    P50={_fmt(_pct(elapsed, 50))}  P95={_fmt(_pct(elapsed, 95))}  max={_fmt(max(elapsed))}  (clova {len(clova)}건)"
        )
        ct = [r.clova_elapsed_ms for r in clova if r.clova_elapsed_ms is not None]
        if ct:
            print(
                f"  clova_http    P50={_fmt(_pct(ct, 50))}  P95={_fmt(_pct(ct, 95))}  max={_fmt(max(ct))}  ({len(ct)}건)"
            )

    non_clova = fixture + failed
    if non_clova:
        errors = Counter(r.error_code for r in non_clova if r.error_code)
        print()
        print(f"  오류 분류   {dict(errors)}")


def report_llm(records: list[LlmRecord]) -> None:
    _sep()
    print("  LLM (chatbot_generation)")
    _sep()
    if not records:
        print("  기록 없음")
        return

    total = len(records)
    success = [r for r in records if r.success]
    failures = [r for r in records if not r.success]

    models = Counter(r.model for r in records)
    print(f"  전체        {total}건  모델={dict(models)}")
    print(f"  성공        {len(success)}건")
    print(f"  실패        {len(failures)}건  ({len(failures) / total * 100:.1f}%)")

    if success:
        latencies = [r.latency_ms for r in success]
        print()
        print(
            f"  latency_ms    P50={_fmt(_pct(latencies, 50))}  P95={_fmt(_pct(latencies, 95))}"
            f"  max={_fmt(max(latencies))}  (성공 {len(success)}건)"
        )

    if failures:
        reasons = Counter(r.reason for r in failures if r.reason)
        print()
        print(f"  실패 사유   {dict(reasons)}")


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="KEY-175 Pilot 메트릭 산출")
    parser.add_argument(
        "--log",
        metavar="PATTERN",
        help="로그 파일 경로 또는 글로브 패턴 (미지정 시 stdin 사용)",
    )
    args = parser.parse_args()

    lines: list[str] = []
    if args.log:
        paths = sorted(glob.glob(args.log))
        if not paths:
            print(f"파일을 찾을 수 없습니다: {args.log}", file=sys.stderr)
            return 1
        for p in paths:
            with open(p, encoding="utf-8", errors="replace") as f:
                lines.extend(f.readlines())
        print(f"파일 {len(paths)}개 로드 — 총 {len(lines)}줄")
    else:
        lines = sys.stdin.readlines()
        print(f"stdin — 총 {len(lines)}줄")

    ocr_records, llm_records = collect(lines)

    _sep("═")
    print("  KEY-175 Pilot 관측 메트릭")
    _sep("═")
    report_ocr(ocr_records)
    print()
    report_llm(llm_records)
    _sep()

    no_data = not ocr_records and not llm_records
    if no_data:
        print("ocr_job_complete / chatbot_generation 로그가 없습니다.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

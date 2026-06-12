# PROGRESS.md — 진행 현황

> 세션(사람/Claude)마다 작업 후 이 파일 상단에 항목을 추가한다. 최신이 위.

## 현재 상태 요약 (2026-06-12 기준)

- 단계: 모의투자 검증 진행 중 — 거래 18/30건, 누적 실현손익 +1,326,958원
- 운영: EC2 t3.micro, systemd stock-bot.service, 2주 연속 무에러
- 데이터: basis_log 13거래일 수집, 6종 CSV 정상 기록 중
- 다음 마일스톤: 거래 30건 도달 → analysis_plan.md 검증 실행

## Phase 진행 상황

| Phase | 상태 | 비고 |
|-------|------|------|
| A. 데이터 진단 분석 | 대기 | EC2 데이터 수신 대기 중 (OPERATION.md 데이터 전송 절차 참고) |
| B. 시스템 보완 | 대기 | 항목 확정됨 (TASKS.md), 착수 전 |
| C. 데이터 수집 확장 | 대기 | 빨리 반영할수록 30건 검증 가치 상승 |
| D. 전략 변경 검토 | 미도래 | 거래 30건 도달 후 |

## 기록

### 2026-06-12 (Claude 세션)
- 코드베이스 전체 분석 완료. 발견 사항을 PLAN.md Phase B/C에 반영.
  - EMERGENCY_STOP_RATE 코드 기본값 0.08 vs 문서 -15% 불일치 (서버 .env 확인 필요)
  - 매수 재시도 시 중복 주문 가능성 (main.py 224~233)
  - 재시작 시 peak_price 등 트레일 상태 유실
  - 일일 손실 한도·동일 테마 제한 부재
- 운영 문서 체계 구축. PLAN / PROGRESS / TASKS / OPERATION.md 생성.
- EC2 배포가 옛 브랜치명(claude/file-modifications-main-ykk5n)에 고정된 문제 확인 → 브랜치 무관 배포 스크립트 scripts/deploy.sh 작성 (OPERATION.md 참고).
- 데이터 전송용 scripts/export_data.sh 작성 (EC2 → data-export 브랜치).

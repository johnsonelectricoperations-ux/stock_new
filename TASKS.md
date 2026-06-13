# TASKS.md — 작업 체크리스트

> PLAN.md의 Phase별 세부 작업. 완료 시 체크하고 PROGRESS.md에 한 줄 기록.
> (기존 checklist.md는 구축기 기록으로 보존. 이번 개선 사이클은 이 파일에서 관리.)

## Phase A — 데이터 진단 분석

- [x] EC2 데이터 수신 (2026-06-13, data-export 브랜치)
- [x] 거래 사례 진단 — 매도 사유별 분포, 이익 반납률 (결과: PROGRESS.md 2026-06-13)
- [x] followup_log 교차 — 손절·모멘텀약화 매도 적중 확인
- [ ] signal_log 필터 효율 분석 — 탈락 종목의 이후 가격 조회 필요 (KIS API로 별도 수집 후 진행)
- [x] timing_log 분석 — buy_failed 21건 → 유령 포지션 문제 발견
- [x] 분석 결과 PROGRESS.md 기록

## Phase B — 시스템 보완 (전략 불변, 우선순위 재조정 2026-06-13)

- [ ] **(1순위)** 매수 주문 성공 판정 보강 — 주문번호 수신 기준 분기로 유령 포지션 방지 (main.py / kis_order.py)
- [ ] **(2순위)** API 장애 연속 감지 — 시세조회 연속 실패 N회 시 텔레그램 긴급 알림 (6/8~9 모니터링 마비 재발 방지)
- [ ] **(3순위)** trades.csv / signal_log.csv 헤더 마이그레이션 — 컬럼 수 혼재 해소
- [ ] 서버 .env의 STOP_LOSS_RATE(-5% 추정)·EMERGENCY_STOP_RATE 값 확인 (사용자 확인 필요)
- [ ] EMERGENCY_STOP_RATE 기본값을 확정값으로 정합화 (config/settings.py)
- [ ] 매수 재시도 중복 주문 방지 — 주문번호 수신 여부로 재시도 분기 (main.py morning_routine)
- [ ] positions 상태 JSON 영속화 + 재시작 시 잔고와 대조 복구
- [ ] realized_pnl 파일 영속화
- [ ] 일일 손실 서킷브레이커 (당일 손실 한도 도달 시 신규 매수 중단 + 알림)
- [ ] 동일 테마 최대 2종목 제한 (kis_sector.py 선정 로직)
- [ ] 토큰 만료 여유 60초 → 300초 (kis_auth.py)
- [ ] positions 접근 threading.Lock 적용 (main.py / telegram_bot.py)
- [ ] 각 항목 배포 후 1거래일 무에러 확인

## Phase C — 데이터 수집 확장

- [ ] signal_log에 테마 연속 상승일수 컬럼 추가 (naver_theme / kis_sector)
- [ ] 매도 기록에 매도 시점 KOSPI 추세·VKOSPI 스냅샷 추가 (performance.py)
- [ ] 이익 반납률 산출 분석 스크립트 작성
- [ ] 다음 거래일 신규 컬럼 정상 기록 확인

## Phase D — 30건 도달 후 (미도래)

- [ ] analysis_plan.md 검증 항목 1~9 실행
- [ ] 트레일 -12% / ATR 1.5× / 시간손절 20일 / BB 임계값 재검토
- [ ] 전략 변경 확정 시 context-notes.md에 근거 기록 후 반영
- [ ] real_trading_transition.md 체크리스트로 실전 전환 판단

## 운영 정비 (수시)

- [ ] EC2에 scripts/deploy.sh 첫 배포 적용 (OPERATION.md 절차)
- [ ] 2027년 공휴일 갱신 (main.py is_trading_day, 연말 전)

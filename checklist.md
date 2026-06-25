# 한국 주식 자동매매 시스템 — 개발 체크리스트

## Phase 0. 환경 준비

### 사용자가 직접 해야 할 것
- [x] AWS EC2 t3.micro 인스턴스 생성 (Ubuntu 24.04, 서울 리전)
- [x] KIS Developers 모의투자 앱키 발급
- [x] 텔레그램 봇 생성 (BotFather) 및 토큰 발급
- [x] 텔레그램 Chat ID 확인
- [x] AWS 서버 SSH 접속 확인
- [x] KRX OpenAPI 가입 및 파생상품지수 시세정보 API 신청 (2026-05-26)

### 완료된 설정
- [x] Python 가상환경 구성 (venv)
- [x] 필수 라이브러리 설치 (requests, pandas, python-telegram-bot, schedule, beautifulsoup4 등)
- [x] 프로젝트 폴더 구조 생성
- [x] .env 파일 키값 설정 (KIS API, 텔레그램)
- [x] 서버 타임존 한국 시간(KST)으로 변경
- [x] systemd 서비스 등록 (자동 시작 + 오류 시 재시작)
- [x] 깃허브 브랜치 연동

---

## Phase 1. 데이터 수집 모듈

- [x] KIS API 인증 토큰 발급 및 자동 갱신 (`kis_auth.py`)
- [x] 토큰 파일 캐시 (모의투자 하루 1회 발급 제한 대응)
- [x] 종목 현재가 조회 (`kis_data.py`)
- [x] 일봉 데이터 조회 120일치 + 거래량 포함 (`kis_indicator.py`)
- [x] 투자자별 매매동향 조회 (`kis_foreign.py`)

---

## Phase 2. 신호 생성 모듈

- [x] MA20 / MA60 추세 필터 구현 (`kis_indicator.py`)
- [x] KOSPI MA60 시장 추세 필터 — KODEX 200(069500) 기준 (`kis_indicator.py`)
- [x] 장중 코스피 급락 가드 — KODEX200 당일 등락률 ≤ -`MARKET_CRASH_GUARD_RATE`(기본 1.5%)면 당일 신규매수 보류 (`main.py` morning_routine)
- [x] 소프트 스로틀 — 연속손절 ≥ `DRAWDOWN_THROTTLE_STREAK`(기본 3)이면 신규 매수 투입자본을 `DRAWDOWN_THROTTLE_FACTOR`(기본 0.5)배로 축소, 익절 1건 시 자동 해제 (`main.py` morning_routine) — 횡보·단기조정 대응
- [x] 20일 모멘텀 스코어 계산 (`kis_momentum.py`)
- [x] 네이버 증권 테마 동적 크롤링 (`naver_theme.py`)
  - [x] 3단계 방어 (크롤링 → 캐시 → 하드코딩 폴백)
  - [x] 시총 5000억 이상 대형주 필터
  - [x] 크롤링 실패 시 텔레그램 알림
  - [x] 파싱 검증 기준 보정 (네이버 실제 제공 40개 기준으로 완화)
- [x] 주도 테마 판별 및 대장주 선정 (`kis_sector.py`)
- [x] 외국인 5일 누적 순매수 필터 (`kis_foreign.py`)
- [x] 전일 거래량 필터 (전일 거래량 ≥ 20일 평균 거래량)
- [x] 5단계 필터 AND 결합 → 최종 매수 신호 생성
  - 0단계: KOSPI MA60 — 하락장이면 당일 매수 전면 중단
  - 1단계: 네이버 테마 상위 12개 수집 → 모멘텀 상위 3개 테마 선정
  - 2단계: 현재가 > MA20 > MA60 + 전일 거래량 ≥ 20일 평균
  - 2.5단계: 볼린저 밴드 %B > 0.85 → 과열 종목 제외 (`BB_PCT_MAX`)
  - 3단계: 외국인 5일 누적 순매수 > 0
  - 전체 통과 종목 중 모멘텀 상위 4종목 선정 (테마 집중 허용)

---

## Phase 3. 리스크 관리 모듈

- [x] 복리 재투자 — 실현 손익 누적 후 다음 매수 기준금 자동 조정
- [x] 가용 현금 기반 매수 (총자산 - 보유 포지션 투자금)
- [x] 종목당 투자 금액 계산 (가용현금 ÷ 신규 매수 종목 수)
- [x] 단계별 매도 로직 (1분봉 기반)
  - [x] 긴급 손절: 진입가 -8% 이상 → 즉시 매도 (캔들 확인 없음)
  - [x] 손절: 진입가 -5% + 직전 1분봉 종가 확인 후 매도 (whipsaw 방지)
  - [x] 비대칭 손절: KOSPI 하락장 시 손절 기준 60%로 축소 (-5% → -3%)
  - [x] 본전 보호: +7% 달성 시 스탑을 진입가 +2%로 이동 (1회)
  - [x] 모멘텀 약화 조기 익절: +10% 이상 + 1분봉 하락 전환 시 즉시 매도
  - [x] 부분 익절: +20% 달성 시 보유량 50% 매도, 잔량 트레일링 계속
  - [x] 트레일링 스탑: 고점 -12% 또는 ATR 동적 트레일 중 더 유리한 값 적용
    - +7% 달성 후: `max(peak - 1.5×ATR, peak × 0.88)` 적용
  - [x] 시간 손절: 20거래일 경과 + 수익률 +5% 미만 시 강제 청산
- [x] 2분마다 보유 종목 모니터링 및 자동 청산

---

## Phase 4. 주문 실행 모듈

- [x] KIS API 매수 주문 (`kis_order.py`)
- [x] KIS API 매도 주문 (`kis_order.py`)
- [x] 포지션 사이징 계산 (effective_budget 파라미터)
- [x] 중복 매수 방지
- [x] 눌림목 진입: 09:15~10:00 1분마다 조건 체크 후 매수
  - 09:15~09:30 엄격 조건: 현재가 > 직전 1분봉 고가 AND 현재가 > 5분 MA
  - 09:30~10:00 완화 조건: 현재가 > 5분 MA 만 충족하면 진입
  - 10:00까지 조건 미충족 시 당일 매수 포기 (강제 시장가 매수 없음)
  - 매수 실패 시 종목 대기열 재등록 → 1분 후 재시도 (최대 3회)
- [x] KIS 500 오류 자동 재시도 (최대 5회, 3초 간격)

---

## Phase 5. 텔레그램 봇 모니터링

- [x] 자동 알림 (매수/매도 체결, 손절/트레일링 스탑/부분익절/시간손절)
- [x] `/status` — 보유 종목 + 수익률
- [x] `/balance` — 운용 현황 (투자금, 평가금, 수익)
- [x] `/signal` — 현재 매수 신호 종목 즉시 조회
- [x] `/buy 종목코드 수량` — 수동 매수
- [x] `/sell 종목코드 수량` — 수동 매도
- [x] `/sellall 종목코드` — 전량 매도
- [x] `/register 종목코드 수량 진입가` — 기존 보유 종목 수동 등록 (주문 없음)
- [x] `/snapshot` — 대시보드 이미지(PNG) 텔레그램 전송
- [x] `/check` — 오늘 시스템 동작 검증 요약 (베이시스/VKOSPI, 신호, 거래, 에러)
- [x] `/pause` — 자동매매 일시 중지
- [x] `/resume` — 자동매매 재개
- [x] `/stop` — 시스템 종료
- [x] `/report` — 누적 성과 리포트
- [x] `/errors [n]` — 최근 에러 n개 조회 (기본 10)
- [x] 화이트리스트 보안 (등록된 Chat ID만 명령어 수신)

---

## Phase 5-2. 스케줄러 및 메인 루프

- [x] 장 시작 전 신호 점검 (08:00 테마 크롤링 + 분석 → 09:10~09:30 눌림목 진입)
- [x] 장 중 1분봉 기반 매도 조건 모니터링 (2분 주기)
- [x] 장 종료 후 일일 결산 리포트 (15:35) — 보유 종목, 자산 현황, 내일 매수 계획 + 시스템 동작 검증 요약 포함
- [x] 주말/공휴일 처리 (2026년 공휴일 목록 적용)
- [x] 장 외 시간 모니터링 제외
- [x] systemd 백그라운드 실행 (서버 재시작 시 자동 시작)
- [x] 스케줄러 헬스체크 (워치독 스레드 — 90분 무응답 시 텔레그램 알림, 5테마 스캔 소요시간 대응)

---

## Phase 5-3. 성과 평가 모듈

- [x] 매도 시 거래 내역 자동 기록 (`trades.csv`)
  - [x] 분석용 확장 필드: entry_time, exit_time, peak_price, min_price, trigger_price, momentum, foreign_net_buy_mil, ma20/ma60_at_entry, volume_ratio, kospi_trend, dip_entry_used
- [x] 매일 신호 스캔 전 종목 기록 (`signal_log.csv`) — 임계값 튜닝용
  - [x] 확장 필드: signal_price, ma20, ma60, volume_ratio, bb_pct, atr, avg_tr_pbmn_mil
  - [x] 헤더 불일치 자동 감지/교체 로직 추가 (구버전 헤더로 인한 /check 오보 수정)
- [x] 매도 후 사후 추적 기록 (`followup_log.csv`) — 3/5/10/20일 후 가격 자동 수집
- [x] 매일 KOSPI 200 베이시스 기록 (`basis_log.csv`) — 임계값 결정용
  - [x] 확장 필드: basis_slope (전일 대비 변화량), vkospi (한국 변동성 지수)
- [x] 매수 윈도우 분별 체크 기록 (`timing_log.csv`) — 진입 시간 최적화용
- [x] 누적 성과 계산 (승률, 손익비, MDD, 연속 손실, 평균 보유 기간)
- [x] 섹터별 평균 수익률 분석
- [x] `/report` 명령어로 텔레그램에서 즉시 조회

---

## Phase 5-4. 에러 모니터링

- [x] `error.log` 파일 기록 (RotatingFileHandler — 1MB × 5파일 회전)
- [x] 심각 에러 즉시 텔레그램 알림 (KIS API 오류, 매수/매도 실패 등)
- [x] 일반 에러 30분 쿨다운 (스팸 방지)
- [x] 스케줄러 워치독 — 30분 무응답 시 알림
- [x] `/errors [n]` 명령어로 최근 에러 텔레그램 조회

---

## Phase 6. 모의투자 검증 (진행 중)

- [x] 모의투자 환경에서 매수 신호 → 눌림목 진입 확인 (2026-05-18 LED장비 테마 2종목 체결)
- [x] 1분봉 API 정상 동작 확인 — 부분익절/모멘텀약화 캔들 조건 작동 확인 (2026-05-18)
- [x] 단계별 매도 조건 정상 작동 확인 — 부분익절(+22.4%), 모멘텀약화(+17.9%) 확인 (2026-05-18)
- [x] 텔레그램 알림 정상 수신 확인
- [x] 잔고 조회 API 정상 동작 확인 — kis_balance.py (포트 29443 수정 후)
- [x] 데이터 수집 CSV 정상 기록 확인 — trades.csv, signal_log.csv, timing_log.csv, followup_pending.json
- [x] 베이시스 수집 정상화 — 네이버 모바일 API(m.stock.naver.com/api/index/FUT/basic)로 선물 가격 수집 (2026-05-18)
- [x] VKOSPI 수집 정상화 — KRX OpenAPI(data-dbg.krx.co.kr) 파생상품지수 시세정보 연동 (2026-05-26)
  - 네이버 polling API / pykrx / FinanceDataReader 모두 미지원 확인 후 KRX OpenAPI로 교체
  - '코스피 200 변동성지수' 항목 전일 종가 수집, KRX_API_KEY 환경변수 필요
  - systemd override.conf에 Environment=KRX_API_KEY 등록
- [x] `/check` 명령어 및 15:35 리포트에 시스템 동작 검증 요약 추가 (베이시스/VKOSPI 기록, 신호 스캔, 거래, 에러 4항목)
- [x] KIS_BASE_URL 포트 수정 — 모의투자 조회 API도 29443 사용 확인, 9443 → 29443 수정 (2026-06-09)
- [x] 전체 데이터 수집 현황 점검 — 모든 파일 정상 수집 중 확인 (2026-06-09)
- [ ] 거래 30건 달성 (현재 18건) → analysis_plan.md 파라미터 검증 시작
- [ ] followup_log.csv 첫 생성 확인 (6/16 이후, 5/18 매도분 d20 완료 시)
- [ ] 외국인 순매수 필터 효과 검증
- [ ] 에러 로그 수집 및 안정성 확인 (2주 이상 무중단 목표)
- [ ] basis_log 40일 도달 후 베이시스/slope 임계값 결정 및 morning_routine 필터 추가 (약 7월 초)
- [ ] basis_log 60일 도달 후 VKOSPI MA60 필터 결정 및 추가 (약 8월 중순)
- [ ] 임계값 파라미터 튜닝 (FOREIGN_BUY_THRESHOLD, MOMENTUM_EXIT_RATE)
- [ ] 실전 투자 전환 체크리스트 확인

---

## Phase 5-5. 운영 편의 기능 (2026-05-18 추가)

- [x] Flask 웹 대시보드 (`dashboard.py`, 포트 5000)
  - [x] 총 평가금 / 누적 실현손익 / 승률 / MDD 메트릭 카드
  - [x] 보유 종목 실시간 현재가 및 손익 표시
  - [x] Chart.js 누적 손익 추이 차트
  - [x] 최근 30건 거래 내역 테이블
  - [x] 30초 자동 새로고침
- [x] 텔레그램 `/snapshot` 명령 — 대시보드 이미지(PNG) 전송 (`snapshot.py`, NanumGothic 폰트)
- [x] 텔레그램 `/register 종목코드 수량 진입가` — 기존 보유 종목 수동 등록 (주문 없음, 자동 매도 감시 포함)
- [x] 텔레그램 `/check` 명령 + 15:35 리포트 자동 포함 — 시스템 동작 4항목 검증 요약
- [x] 시작 시 KIS 잔고 API로 보유 종목 자동 복구 — 재시작 후 `/register` 수동 입력 불필요
- [x] AWS EC2 보안 그룹 포트 5000 인바운드 규칙 추가

---

## 미결정 항목 (데이터 축적 후 적용 예정)

- [ ] 외국인 순매수 임계값 최적화 (현재 0원, 거래 30건 이상 후 백테스트 기반 결정)
- [ ] 외국인 Z-score 필터 — 일평균 거래대금 대비 Z-score 2.0 이상만 진입 (avg_tr_pbmn_mil 20일+ 축적 후)
- [ ] 베이시스 slope 필터 — 기울기 방향으로 매수 타이밍 보조 (basis_slope 20일+ 축적 후)
- [ ] VKOSPI MA60 + 변동성 급등 필터 — 고변동성 국면 진입 억제 (vkospi 60일+ 축적 후)
- [ ] 실전 투자 전환 시점 (모의투자 승률 45%+, 손익비 1.5+, 2주 안정 운영 후)
- [ ] 베이시스 임계값 결정 — 백워데이션 < -0.3% 매수 보류 검토 (basis_log 충분히 쌓인 후)
- [ ] 선물/옵션 만기일 매수 보류 필터 — 실전 전환 전에 추가 (real_trading_transition.md 섹션 8 참고)

---

## Phase 7. 실전 투자 전환 체크리스트 (미완료)

> 모의투자 검증 완료 후 아래 순서대로 진행.

### 사전 조건 확인
- [ ] 모의투자 승률 45% 이상, 손익비 1.5 이상 달성
- [ ] 30건 이상 거래로 통계 신뢰도 확보
- [ ] 에러 없이 2주 이상 안정적으로 동작 확인
- [ ] 실전 투자 금액 확정

### 코드 수정 사항

#### 1. .env 파일 수정 (필수)
```
KIS_IS_MOCK=false
KIS_APP_KEY=실전앱키
KIS_APP_SECRET=실전앱시크릿
KIS_ACCOUNT_NO=실전계좌번호
TOTAL_BUDGET=실제투자금액
```
- KIS Developers에서 실전 앱키 별도 발급 필요
- 모의투자 앱키와 실전 앱키는 다름

#### 2. kis_balance.py 활성화 (중요)
- [ ] `main.py`의 `get_available_cash()`를 settings 고정값 대신 실제 잔고 조회로 교체
- [ ] `morning_routine()` 매수 전 실제 예수금 확인 로직 추가
- [ ] `daily_report()`에 실제 잔고 기반 현황 반영

```python
# 실전 전환 후 get_available_cash() 교체 예시
from kis_balance import get_balance
def get_available_cash():
    return get_balance()['cash']
```

#### 3. 설정값 재검토
- [ ] `TOTAL_BUDGET`: 실제 투자금으로 변경
- [ ] `MAX_STOCK_COUNT`: 투자금 규모에 맞게 조정 (종목당 최소 100만원 이상)
- [ ] `STOP_LOSS_RATE`, `TRAIL_STOP_RATE`: 모의투자 결과 기반 튜닝
- [ ] `FOREIGN_BUY_THRESHOLD`: 모의투자 결과 기반 튜닝

#### 4. 수수료/세금 반영
- [ ] 매도 시 수익 계산에 증권거래세 0.18% + 수수료 반영
- [ ] `log_trade()` 및 `_do_sell()`의 profit 계산 수정

### 전환 당일 절차
1. `sudo systemctl stop stock-bot`
2. `.env` 파일 수정 (실전 키로 교체)
3. `config/token_cache.json` 삭제 (실전 토큰 새로 발급)
4. `sudo systemctl start stock-bot`
5. 텔레그램 `/balance`로 실제 잔고 조회 확인
6. 소액 테스트 주문 후 정상 체결 확인

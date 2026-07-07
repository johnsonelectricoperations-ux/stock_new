# 실전 투자 전환 가이드

> 모의투자 검증 완료 후 이 문서 순서대로 진행할 것.
> 마지막 업데이트: 2026-07-07 (3차 — 코드 현행화 반영. 잔고조회·수수료는 자동 처리로 이동,
> 이중 키 구조(KIS_REAL_*) 반영, 달성 현황 추가)

---

## 전환 전 필수 달성 조건

| 지표 | 최소 기준 | 확인 방법 | 현황 (2026-07-07, 33건 기준) |
|------|-----------|-----------|------------------------------|
| 거래 건수 | 30건 이상 | `/report` | ✅ 33건 |
| 승률 | 45% 이상 | `/report` | ❌ 42.4% |
| 손익비 | 1.5 이상 | `/report` | ✅ 2.21 |
| MDD | -20% 이내 | `/report` | ✅ -18% (경계) |
| 안정 운영 기간 | 2주 이상 에러 없이 | `error.log` | ❌ 06-22~24 모니터링 마비 → 07-07 수정 배포 이후부터 재카운트 |

**판단 보조 (정량 기준 외).** 현재 수익이 5월 랠리에 집중(6월 조정은 -91만)이라, 7월 조정 국면
통과 성적(방어 유지 + 회복 시 재진입 품질)까지 보고 전환하는 것을 권장. 섀도 선정(전날 vs 당일)
비교 결과도 같은 시기에 나옴.

---

## 1. .env 수정 (필수)

실전 앱키는 이미 섀도 선정용으로 `.env`의 `KIS_REAL_APP_KEY`/`KIS_REAL_APP_SECRET`에 들어 있다
(2026-07 설정). 전환은 그 값을 본 키로 올리는 것.

```
KIS_IS_MOCK=false
KIS_APP_KEY=실전앱키          # KIS_REAL_APP_KEY와 같은 값으로 교체
KIS_APP_SECRET=실전앱시크릿    # KIS_REAL_APP_SECRET와 같은 값으로 교체
KIS_ACCOUNT_NO=실전계좌번호-01  # 모의 계좌 → 실전 계좌로 반드시 교체
TOTAL_BUDGET=실제투자금액
```

**주의사항.**
- 계좌번호 형식: `12345678-01` (하이픈 포함해도 코드가 자동 처리함). **계좌번호 교체를 잊으면
  실전 키로 모의 계좌에 주문하다 전부 거부되므로 최우선 확인.**
- TOTAL_BUDGET은 실제 입금한 예수금 기준으로 설정.
- `KIS_REAL_APP_KEY`/`KIS_REAL_APP_SECRET`는 전환 후 .env에서 지워도 된다(본 키로 자동 폴백,
  config/settings.py). 남겨둬도 무해.
- 순위 조회 토큰 캐시 `config/token_cache_real.json`은 실전 키 그대로면 삭제 불필요.

---

## 2. 토큰 캐시 삭제 (필수)

실전 전환 시 모의투자 토큰이 캐시에 남아 있으면 인증 실패. 반드시 삭제.

```bash
rm ~/stock-bot/config/token_cache.json
```

---

## 3. 잔고 조회 활성화 (이미 처리됨 — 2026-06 반영)

가용현금은 이미 KIS 예수금 조회 우선으로 동작한다. 코드 수정 불필요.

- `main.py get_available_cash()` — `kis_balance.get_balance()['cash']` 우선, 실패 시 메모리
  계산(TOTAL_BUDGET + 실현손익 - 투자중) 폴백.
- `_execute_buy()` — 매수가능조회(`get_orderable_cash`, VTTC8908R→실전 TTTC8908R 자동)로
  T+2 미결제 대금 반영해 수량 상한. 조회 실패 시 미적용 폴백.
- 예수금 50만원 미만이면 매수 보류 로직도 이미 포함(morning_routine).
- ⚠️ 실전 첫 매수 때 응답 필드(nrcvb_buy_amt 등)가 실전 서버에서도 같은지 로그로 확인할 것
  (2026-06-16 기록 — 다르면 폴백되어 무해하나 상한 효과 없음).

---

## 4. 수수료/세금 반영 (이미 처리됨 — 자동 분기)

`_do_sell()`이 `KIS_IS_MOCK=false`면 자동으로 비용을 차감해 profit/profit_rate를 기록한다.
코드 수정 불필요.

- 적용 값(config/settings.py, .env로 오버라이드 가능): `SELL_TAX_RATE=0.0015`(증권거래세 0.15%,
  매도 시), `COMMISSION_RATE=0.00015`(수수료 0.015%, 매수·매도 각각).
- 전환 시점의 실제 세율·수수료율이 다르면 .env에서 값만 조정 (2026년 코스피/코스닥 세율 확인).
- 모의투자 기록(is_mock=True)은 비용 미반영이므로, 실전 후 성과 분석 시 is_mock으로 분리할 것.

---

## 5. 포트 설정 확인 (이미 처리됨)

모의투자 개발 중 발견된 사항. 이미 코드에 반영되어 있으므로 별도 수정 불필요.

| 환경 | 조회 API (현재가·일봉 등) | 주문·잔고 API |
|------|--------------------------|--------------|
| 모의투자 | `:9443` | `:29443` |
| 실전 | `:9443` | `:9443` |

`config/settings.py`의 `KIS_ORDER_BASE_URL`이 `KIS_IS_MOCK` 값에 따라 자동 분기.
`kis_order.py`(주문)와 `kis_balance.py`(잔고조회) 모두 `KIS_ORDER_BASE_URL` 사용.
`.env`에서 `KIS_IS_MOCK=false`로만 바꾸면 포트도 자동으로 9443으로 통일됨.

---

## 6. custtype 헤더 확인 (이미 처리됨)

`kis_order.py`의 `_post_order()`에 `headers['custtype'] = 'P'` 이미 포함됨.
별도 수정 불필요.

---

## 7. 설정값 재검토

```
# .env 또는 config/settings.py 기본값 검토 (아래는 2026-07-07 현재 실제 기본값)

TOTAL_BUDGET            = 실제 투자금 (예: 10000000)
MAX_STOCK_COUNT         = 4      # 투자금 규모 확인 (종목당 최소 100만원 이상)
STOP_LOSS_RATE          = 0.05   # -5% (33건 검증: 휩쏘 27%로 유지 확정)
EMERGENCY_STOP_RATE     = 0.08   # -8% 즉시 손절
TRAIL_STOP_RATE         = 0.12
MOMENTUM_EXIT_RATE      = 0.10
MARKET_CRASH_GUARD_RATE = 1.5    # 장중 지수 -1.5% 급락 가드 (0=비활성)
DRAWDOWN_THROTTLE_STREAK= 3      # 연속손절 3회 → 투입자본 50% 축소
DRAWDOWN_THROTTLE_FACTOR= 0.5
FOREIGN_BUY_THRESHOLD   = 0
```

**MAX_STOCK_COUNT 기준.**
- 투자금 1,000만원 → 최대 4종목 (종목당 250만원)
- 투자금 500만원 → 최대 2종목 (종목당 250만원)
- 종목당 100만원 미만이면 수수료 비중이 커지므로 비효율

---

## 8. 만기일 필터 추가 (실전 전환 전)

선물/옵션 만기일(매월 둘째 목요일)에는 프로그램 매매 증가로 변동성 급등.
매수 보류 로직 추가 권장.

### 판단 기준

- 월물 만기일: 매월 둘째 목요일
- 네 마녀의 날(쿼드러플 위칭): 3, 6, 9, 12월 둘째 목요일 — 특히 변동성 큼

### main.py morning_routine() 추가 예시

```python
from datetime import datetime, timedelta

def _is_expiry_day() -> bool:
    """오늘이 선물/옵션 만기일(매월 둘째 목요일)인지 확인."""
    today = datetime.now().date()
    first = today.replace(day=1)
    # 첫 번째 목요일
    first_thu = first + timedelta(days=(3 - first.weekday()) % 7)
    # 두 번째 목요일
    second_thu = first_thu + timedelta(weeks=1)
    return today == second_thu

# morning_routine() 안 매수 전에
if _is_expiry_day():
    month = datetime.now().month
    kind = '네 마녀의 날' if month in (3, 6, 9, 12) else '선물 만기일'
    send_message(f'오늘은 {kind}입니다. 매수를 보류합니다.')
    return
```

---

## 9. 베이시스 필터 및 선물 데이터 수집 (수집 중)

**모의투자 중 선물 데이터 수집 정상화** — 네이버 모바일 API로 해결 (2026-05-18).

| 시도 | 결과 |
|------|------|
| 네이버 `finance.naver.com/item/main.naver?code=101W2606` | Npay 페이지로 연결, 파싱 불가 |
| KIS 모의투자 `FHKIF03010100` | "없는 서비스 코드" |
| **네이버 모바일 API `m.stock.naver.com/api/index/FUT/basic`** | **✅ 정상 동작 — 코스피 200 선물 지수 실시간 조회** |

현재 `basis_log.csv`에 현물(KODEX 200 기반) + 선물(네이버 API) 모두 기록 중.
근월물 코드 변경 없이 항상 최근월 선물 가격을 반환하므로 만기 롤오버 대응 불필요.

현재 `basis_log.csv`에 기록 중인 항목.
- `basis`, `basis_pct`: 선물 - 현물 베이시스
- `basis_slope`: 전일 대비 베이시스 변화량 (기울기)
- `vkospi`: 한국 변동성 지수 (장 외 시간 None)

**실전 전환 후 할 일.**
1. 데이터 충분히 쌓인 후 임계값 결정
   - 베이시스 < -0.3% (백워데이션): 매수 보류 검토
   - basis_slope 연속 음전환: 매수 타이밍 지연 검토
   - VKOSPI MA60 + 급등 구간: 고변동성 국면 진입 억제 검토
2. 임계값 결정 후 `morning_routine()`에 필터 추가

---

## 10. 매수 예산 안전마진 (이미 처리됨)

`morning_routine()`에서 가용현금의 95%만 매수에 사용.
시장가 매수 슬리피지·수수료로 인한 잔고 초과 방지 목적.
실전 전환 후 `kis_balance.py`로 실잔고 조회가 활성화되면 안전마진은 그대로 유지.

---

## 11. 서버 재시작 후 포지션 복구 (자동 처리됨)

시스템 시작 시 KIS 잔고 API(`get_balance()`)를 호출해 보유 종목을 자동으로 `positions`에 복구.
별도 `/register` 입력 없이 자동 매도 감시가 재개됨.

복구 기준.
- KIS 잔고 API에서 보유수량(hldg_qty) > 0인 종목 자동 등록
- 진입가는 평균 매입가(`pchs_avg_pric`) 사용
- 진입일은 당일 날짜로 초기화

필요 시 수동 보정.
```
텔레그램: /register 종목코드 수량 진입가
예: /register 005930 10 75000
```
자동 복구된 진입가가 실제와 다를 경우 `/register`로 덮어쓸 수 없음 (중복 방지). 직접 삭제 후 재등록 필요.

---

## 12. SSL 검증 (자동 처리됨)

현재 모의투자 서버의 SSL 인증서 불일치로 `verify=False` 적용 중.
`KIS_IS_MOCK=false`로 변경하면 코드 내 모든 `verify = not KIS_IS_MOCK`이 자동으로 `True`가 됨.
별도 수정 불필요.

---

## 전환 당일 절차

```bash
# 1. 서비스 중지
sudo systemctl stop stock-bot

# 2. .env 파일 수정 (실전 키/계좌/예산으로)
nano ~/stock-bot/.env

# 3. 토큰 캐시 삭제 (실전 토큰 새로 발급)
rm ~/stock-bot/config/token_cache.json

# 4. 진단 스크립트로 API 연결 확인
cd ~/stock-bot
venv/bin/python3 diagnose_order.py
# → rt_cd: 0 확인 (장 시간 중)

# 5. 서비스 시작
sudo systemctl start stock-bot

# 6. 텔레그램 /balance 로 실제 잔고 조회 확인

# 7. 소액 수동 매수 테스트
# 텔레그램: /buy 005930 1
# 체결 확인 후: /sellall 005930
```

---

## 전환 후 첫 1주 모니터링

```bash
# 실시간 로그
sudo journalctl -u stock-bot -f

# 에러 확인
tail -f ~/stock-bot/error.log

# 텔레그램 명령어
/balance    # 매일 아침 잔고 확인
/status     # 보유 포지션 확인
/errors 20  # 에러 내역 확인
```

---

## 체크리스트 요약

**전환 전 달성 조건 (2026-07-07 현황: 승률·안정 2주 미충족).**
- [ ] 모의투자 30건 이상 ✅(33건), 승률 45%+ ❌(42.4%), 손익비 1.5+ ✅(2.21), MDD -20% 이내 ✅(-18%)
- [ ] 07-07 견고성 수정 배포 이후 2주 무사고 운영
- [ ] (권장) 7월 조정 국면 통과 성적 + 섀도 선정 비교 결과 확인

**수동 작업 (전환 당일).**
- [ ] .env — KIS_IS_MOCK=false, KIS_APP_KEY/SECRET을 실전 키(=KIS_REAL_* 값)로, **계좌번호 실전으로**, 예산 입력
- [ ] token_cache.json 삭제 (token_cache_real.json은 유지 가능)
- [ ] MAX_STOCK_COUNT·비용률(SELL_TAX_RATE 등) 투자금·당시 세율에 맞게 재확인
- [ ] 만기일 필터 추가 여부 결정 (morning_routine, 섹션 8 참고 — 아직 미구현)

**자동 처리됨 (수정 불필요).**
- [x] 잔고·가용현금 — KIS 예수금 조회 우선 + 매수가능조회 상한 (섹션 3, 2026-06 반영)
- [x] 수수료/세금 — KIS_IS_MOCK=false 시 profit 자동 차감 (섹션 4)
- [x] 포트 설정 — KIS_IS_MOCK=false 시 주문·잔고 API 모두 9443 자동 적용
- [x] SSL 검증 — KIS_IS_MOCK=false 시 자동 활성화
- [x] custtype 헤더 — 이미 포함됨
- [x] 매수 예산 5% 안전마진 — 이미 적용됨
- [x] 재시작 후 보유 종목 자동 복구 — KIS 잔고 API 기반, /register 수동 입력 불필요
- [x] 섀도 선정 — 실전 키 자동 폴백으로 계속 동작 (kis_rank.py)
- [x] 베이시스/VKOSPI 수집 — 네이버 API로 자동 수집 중 (basis_log.csv)
- [x] 웹 대시보드 — http://서버IP:5000 (Flask, 포트 5000 보안 그룹 열어둬야 함)
- [x] 텔레그램 /snapshot — 대시보드 이미지 전송
- [x] 텔레그램 /check + 15:35 리포트 — 시스템 동작 검증 요약 (퇴근 후 확인용)

**전환 당일.**
- [ ] diagnose_order.py 로 주문 API 정상 확인 (장 시간 중)
- [ ] 소액 수동 매수/매도 테스트 후 본격 자동매매 시작
- [ ] 재시작 후 /balance 로 실전 잔고 확인
- [ ] 첫 자동 매수 때 매수가능조회 응답 필드 정상 여부 로그 확인 (섹션 3 ⚠️)

# 실전 투자 전환 가이드

> 모의투자 검증 완료 후 이 문서 순서대로 진행할 것.
> 마지막 업데이트: 2026-05-18 (2차)

---

## 전환 전 필수 달성 조건

| 지표 | 최소 기준 | 확인 방법 |
|------|-----------|-----------|
| 거래 건수 | 30건 이상 | `/report` |
| 승률 | 45% 이상 | `/report` |
| 손익비 | 1.5 이상 | `/report` |
| MDD | -20% 이내 | `/report` |
| 안정 운영 기간 | 2주 이상 에러 없이 | `error.log` |

---

## 1. .env 수정 (필수)

```
KIS_IS_MOCK=false
KIS_APP_KEY=실전앱키
KIS_APP_SECRET=실전앱시크릿
KIS_ACCOUNT_NO=실전계좌번호-01
TOTAL_BUDGET=실제투자금액
```

**주의사항.**
- KIS Developers에서 실전 앱키는 모의투자 앱키와 별도로 발급해야 함.
- 계좌번호 형식: `12345678-01` (하이픈 포함해도 코드가 자동 처리함).
- TOTAL_BUDGET은 실제 입금한 예수금 기준으로 설정.

---

## 2. 토큰 캐시 삭제 (필수)

실전 전환 시 모의투자 토큰이 캐시에 남아 있으면 인증 실패. 반드시 삭제.

```bash
rm ~/stock-bot/config/token_cache.json
```

---

## 3. kis_balance.py 활성화 (중요)

현재 가용현금 계산이 `settings.py` 고정값 기반. 실전에서는 실제 예수금 조회로 교체해야 함.

> **참고**: 2026-05-18 모의투자에서 kis_balance.py 정상 작동 확인됨 (포트 29443 수정 후). 잔고 조회 API 자체는 문제없음.

### main.py 수정

**현재 코드 (main.py 상단 get_available_cash 함수).**
```python
def get_available_cash():
    total = TOTAL_BUDGET + realized_pnl
    invested = sum(p['entry_price'] * p['qty'] for p in positions.values())
    return max(0, total - invested)
```

**실전 전환 후 (실제 예수금 반영).**
```python
from kis_balance import get_balance

def get_available_cash():
    try:
        return get_balance()['cash']
    except Exception:
        # API 실패 시 기존 계산 방식으로 폴백
        total = TOTAL_BUDGET + realized_pnl
        invested = sum(p['entry_price'] * p['qty'] for p in positions.values())
        return max(0, total - invested)
```

**morning_routine() 매수 전 예수금 확인 추가.**
```python
# morning_routine() 안, 매수 직전에 추가
available = get_available_cash()
if available < 500000:  # 50만원 미만이면 매수 중단
    send_message('예수금 부족으로 오늘 매수 건너뜀.')
    return
```

**daily_report() 실제 잔고 반영.**
```python
# daily_report() 안에서 잔고 조회
try:
    bal = get_balance()
    cash = bal['cash']
    total_eval = bal['total_eval']
except Exception:
    cash = get_available_cash()
    total_eval = None
```

---

## 4. 수수료/세금 반영 (중요)

현재 profit 계산에 수수료/세금 미반영. 실전에서는 실제 수익이 더 작게 잡힘.

### 적용 비율
- 증권거래세: 0.18% (매도 시 자동 징수)
- 수수료: 약 0.015% (증권사마다 다름, 한국투자증권 기준)
- 실질 매도 비용: 약 **0.20%** (세금 + 수수료 합산)

### performance.py 수정 (log_trade 함수)

```python
# 현재
profit = round((exit_price - entry_price) * qty)
profit_rate = round((exit_price - entry_price) / entry_price * 100, 2)

# 실전 전환 후
SELL_FEE_RATE = 0.0020  # 증권거래세 0.18% + 수수료 0.02%
fee = round(exit_price * qty * SELL_FEE_RATE)
profit = round((exit_price - entry_price) * qty) - fee
profit_rate = round(profit / (entry_price * qty) * 100, 2)
```

### main.py 수정 (_do_sell 함수)

```python
# 현재
profit = round((exit_price - entry_price) * qty)

# 실전 전환 후
SELL_FEE_RATE = 0.0020
fee = round(exit_price * qty * SELL_FEE_RATE)
profit = round((exit_price - entry_price) * qty) - fee
```

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
# .env 또는 config/settings.py 기본값 검토

TOTAL_BUDGET        = 실제 투자금 (예: 10000000)
MAX_STOCK_COUNT     = 4  # 투자금 규모 확인 (종목당 최소 100만원 이상)
STOP_LOSS_RATE      = 0.10  # 모의투자 결과 기반 튜닝
TRAIL_STOP_RATE     = 0.12  # 모의투자 결과 기반 튜닝
FOREIGN_BUY_THRESHOLD = 0   # 모의투자 결과 기반 상향 조정 검토
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

**전환 전 달성 조건.**
- [ ] 모의투자 30건 이상, 승률 45%+, 손익비 1.5+, 2주 안정 운영 확인

**코드 수정 필요 (수동).**
- [ ] .env — KIS_IS_MOCK=false, 실전 앱키/시크릿/계좌번호/예산 입력
- [ ] token_cache.json 삭제
- [ ] kis_balance.py 활성화 (main.py get_available_cash 교체, 섹션 3 참고)
- [ ] 수수료/세금 반영 (performance.py, main.py profit 계산, 섹션 4 참고)
- [ ] MAX_STOCK_COUNT 투자금 규모에 맞게 재확인
- [ ] 만기일 필터 추가 (morning_routine, 섹션 8 참고)

**자동 처리됨 (수정 불필요).**
- [x] 포트 설정 — KIS_IS_MOCK=false 시 주문·잔고 API 모두 9443 자동 적용
- [x] SSL 검증 — KIS_IS_MOCK=false 시 자동 활성화
- [x] custtype 헤더 — 이미 포함됨
- [x] 매수 예산 5% 안전마진 — 이미 적용됨
- [x] 재시작 후 보유 종목 자동 복구 — KIS 잔고 API 기반, /register 수동 입력 불필요
- [x] 베이시스/VKOSPI 수집 — 네이버 API로 자동 수집 중 (basis_log.csv)
- [x] 웹 대시보드 — http://서버IP:5000 (Flask, 포트 5000 보안 그룹 열어둬야 함)
- [x] 텔레그램 /snapshot — 대시보드 이미지 전송
- [x] 텔레그램 /check + 15:35 리포트 — 시스템 동작 검증 요약 (퇴근 후 확인용)

**전환 당일.**
- [ ] diagnose_order.py 로 주문 API 정상 확인 (장 시간 중)
- [ ] 소액 수동 매수/매도 테스트 후 본격 자동매매 시작
- [ ] 재시작 후 kis_balance.py 실행해 잔고 확인

# 
# analysis_plan.md 기준으로 검증 진행해줘.

# 전략 파라미터 검증 계획

> 모의투자 데이터가 충분히 쌓인 후 아래 분석을 순서대로 실행.
> 마지막 업데이트: 2026-05-18

---

## 선행 조건

| 분석 항목 | 최소 조건 |
|----------|----------|
| 전략 전반 성과 | 거래 30건 이상 |
| BB%B 임계값 검증 | 거래 30건 이상 |
| ATR 승수 검증 | 거래 30건 이상 |
| 외국인 Z-score 필요성 | 거래 30건 이상 |
| MSM 필요성 | 거래 30건 이상 |
| 진입 시간대 효과 | 거래 30건 이상 |
| 베이시스 slope 임계값 | basis_log 2개월 이상 |
| VKOSPI MA60 필터 | basis_log 3개월(60거래일) 이상 |

---

## 0. 준비 코드 (공통)

```python
import pandas as pd
import numpy as np

trades    = pd.read_csv('trades.csv')
signals   = pd.read_csv('signal_log.csv')
basis     = pd.read_csv('basis_log.csv')
timing    = pd.read_csv('timing_log.csv')

trades['profit_rate'] = trades['profit_rate'].astype(float)
trades['profit']      = trades['profit'].astype(int)

# signal_log와 trades.csv JOIN (code + entry_date 기준)
merged = pd.merge(
    trades,
    signals[signals['selected'] == True],
    left_on=['code', 'entry_date'],
    right_on=['code', 'date'],
    how='left'
)
```

---

## 1. 전략 전반 성과 확인

```python
total     = len(trades)
win_rate  = (trades['profit_rate'] > 0).mean() * 100
avg_win   = trades[trades['profit_rate'] > 0]['profit_rate'].mean()
avg_loss  = trades[trades['profit_rate'] <= 0]['profit_rate'].mean()
pl_ratio  = avg_win / abs(avg_loss)

# MDD
cumsum = trades['profit'].cumsum()
peak   = cumsum.cummax()
mdd    = ((cumsum - peak) / peak).min() * 100

print(f'거래 {total}건 | 승률 {win_rate:.0f}% | 손익비 {pl_ratio:.2f} | MDD {mdd:.1f}%')
```

**판단 기준.**
- 승률 45% 이상 + 손익비 1.5 이상 → 실전 전환 검토 가능
- 승률 40% 미만 또는 손익비 1.0 미만 → 신호 필터 재검토 필요

---

## 2. BB%B 임계값 검증 (현재 0.85)

현재 BB%B > 0.85 종목을 과열로 제외. 이 기준이 적절한지 확인.

```python
# bb_pct 구간별 평균 수익률
merged['bb_bin'] = pd.cut(merged['bb_pct'], bins=[0, 0.5, 0.7, 0.85, 1.0, 99])
result = merged.groupby('bb_bin')['profit_rate'].agg(['mean', 'count'])
print(result)
```

**판단 기준.**
- bb_pct 0.85 초과 구간의 평균 수익률이 낮으면 → 현행 유지
- 구간별 차이가 없으면 → 필터 완화 또는 제거 검토
- bb_pct 0.7 이하가 가장 성과 좋으면 → 임계값 하향 조정 검토

---

## 3. ATR 승수 검증 (현재 1.5×)

ATR 트레일링에서 `peak - 1.5×ATR` 사용. 더 타이트(1.0×)하거나 느슨(2.0×)한 게 나은지 확인.

```python
# ATR 대비 실제 고점 이후 하락폭 분포
merged['actual_drawdown'] = (merged['peak_price'].astype(float) - merged['exit_price'].astype(float))
merged['atr_x']           = merged['actual_drawdown'] / merged['atr_y'].astype(float)

print(merged['atr_x'].describe())
print(f'1.5× 이하에서 트레일 발동: {(merged["atr_x"] < 1.5).mean()*100:.0f}%')
```

**판단 기준.**
- 대부분이 1.5× 이하에서 발동 → 너무 타이트, 2.0×으로 완화 검토
- 대부분이 1.5× 이상에서 발동 → 현행 유지 또는 1.0×으로 강화 검토

---

## 4. 외국인 Z-score 필요성 확인

현재 순매수 > 0만 보는데, 거래대금 대비 비중이 클수록 성과가 좋은지 확인.

```python
# 외국인 비중 = 5일 순매수 / 일평균 거래대금
merged['frgn_ratio'] = (
    merged['foreign_5d_net_buy_mil'].astype(float) /
    merged['avg_tr_pbmn_mil'].astype(float).replace(0, np.nan)
)

# 비중 상위/하위 성과 비교
median_ratio = merged['frgn_ratio'].median()
high = merged[merged['frgn_ratio'] >= median_ratio]['profit_rate'].mean()
low  = merged[merged['frgn_ratio'] <  median_ratio]['profit_rate'].mean()

print(f'외국인 비중 상위(≥중앙값) 평균 수익률: {high:.2f}%')
print(f'외국인 비중 하위(<중앙값) 평균 수익률: {low:.2f}%')
```

**판단 기준.**
- 상위와 하위 차이 1%p 이상 → Z-score 필터 구현 가치 있음
- 차이 없음 → 단순 순매수 > 0 기준으로 충분

---

## 5. MSM(국면 전환 모델) 필요성 확인

현재 KOSPI MA60 boolean 하나로 상승/하락장 구분. 더 세밀한 국면 판단이 필요한지 확인.

```python
# KOSPI 추세별 성과 비교
result = trades.groupby('kospi_trend')['profit_rate'].agg(['mean', 'count', 'std'])
print(result)

# 하락장에서의 손실 분포
bear_trades = trades[trades['kospi_trend'] == 'bearish']
print(f'하락장 거래 비중: {len(bear_trades)/len(trades)*100:.0f}%')
print(f'하락장 평균 수익률: {bear_trades["profit_rate"].mean():.2f}%')
```

**판단 기준.**
- 하락장 거래가 전체의 20% 미만이고 성과 차이 크지 않음 → MA60 boolean으로 충분
- 하락장 거래에서 손실이 반복적으로 큼 → MSM 도입 검토 (구현 난이도 높음)

---

## 6. 진입 시간대 효과 확인

09:30 전 엄격 조건 진입 vs 09:30~10:00 완화 조건 진입 성과 비교.

```python
# timing_log와 trades 연결 (code + date)
timing['date'] = pd.to_datetime(timing['date']).dt.strftime('%Y-%m-%d')
timing_bought  = timing[timing['action'].isin(['bought_dip', 'forced_bought'])]

trades['entry_date'] = pd.to_datetime(trades['entry_date']).dt.strftime('%Y-%m-%d')
merged_t = pd.merge(trades, timing_bought[['date', 'code', 'action', 'check_time']],
                    left_on=['entry_date', 'code'], right_on=['date', 'code'], how='left')

# dip_entry_used 기준으로도 비교 가능
result = trades.groupby('dip_entry_used')['profit_rate'].agg(['mean', 'count'])
print(result)
```

**판단 기준.**
- 엄격 조건 진입 수익률 > 완화 조건 → 10:00 마감 시간 단축 검토
- 차이 없음 → 현행 유지

---

## 7. 베이시스 slope 임계값 (2개월 이상 후)

basis_slope(전일 대비 베이시스 변화량)와 당일 시장 성과 관계 분석.

```python
basis['date'] = pd.to_datetime(basis['date']).dt.strftime('%Y-%m-%d')
basis['basis_slope'] = basis['basis_slope'].astype(float)

# slope 양전환 날 vs 음전환 날의 당일 거래 성과
trades_basis = pd.merge(trades, basis[['date', 'basis', 'basis_slope']],
                        left_on='entry_date', right_on='date', how='left')

slope_pos = trades_basis[trades_basis['basis_slope'] > 0]['profit_rate'].mean()
slope_neg = trades_basis[trades_basis['basis_slope'] <= 0]['profit_rate'].mean()

print(f'slope 양전환일 평균 수익률: {slope_pos:.2f}%')
print(f'slope 음전환일 평균 수익률: {slope_neg:.2f}%')
```

**판단 기준.**
- slope 양전환일에 성과가 의미있게 좋음 → morning_routine에 slope 조건 추가
- 차이 없음 → 베이시스 절대값 기준만 사용

---

## 8. VKOSPI MA60 필터 (3개월 이상 후)

VKOSPI 고점 구간 진입이 성과에 악영향을 주는지 확인.

```python
basis['vkospi'] = pd.to_numeric(basis['vkospi'], errors='coerce')
basis['vkospi_ma60'] = basis['vkospi'].rolling(60).mean()
basis['vkospi_spike'] = basis['vkospi'] > basis['vkospi_ma60'] * 1.2  # 20% 초과 급등

trades_v = pd.merge(trades, basis[['date', 'vkospi', 'vkospi_spike']],
                    left_on='entry_date', right_on='date', how='left')

spike     = trades_v[trades_v['vkospi_spike'] == True]['profit_rate'].mean()
no_spike  = trades_v[trades_v['vkospi_spike'] == False]['profit_rate'].mean()

print(f'VKOSPI 급등 구간 진입 평균 수익률: {spike:.2f}%')
print(f'VKOSPI 정상 구간 진입 평균 수익률: {no_spike:.2f}%')
```

**판단 기준.**
- 급등 구간 수익률이 1%p 이상 낮음 → morning_routine에 VKOSPI 필터 추가
- 차이 없음 → 수집 지속, 필터 추가 보류

---

## 9. 전날 섹터 모멘텀 과열 여부 (거래 30건 이상 후)

08:00 크롤링은 전일 종가 기준이라 "전날 주도섹터"를 잡음. 전날 급등(과열)
섹터를 추격 매수하면 차익실현 갭하락에 노출되는지 확인. (5/20 지능형로봇
8.5% 테마 손실 사례 검증)

```python
# 선정된 종목의 전날 섹터 모멘텀(sector_avg_momentum)과 수익률 관계
sel = signals[signals['selected'] == True]
m = pd.merge(trades, sel[['code', 'date', 'sector_avg_momentum']],
             left_on=['code', 'entry_date'], right_on=['code', 'date'], how='left')
m['sector_mom'] = m['sector_avg_momentum'].astype(float)

# 섹터 모멘텀 구간별 평균 수익률
m['sec_bin'] = pd.cut(m['sector_mom'], bins=[0, 15, 25, 40, 999])
print(m.groupby('sec_bin')['profit_rate'].agg(['mean', 'count']))
```

**판단 기준.**
- 섹터 모멘텀 과열 구간(예: 40%+)에서 수익률이 의미있게 낮음 → 섹터 모멘텀
  상한선 추가 (`kis_sector.py` MIN_THEME_MOMENTUM 옆에 MAX 추가)
- 차이 없거나 높을수록 좋음 → 현행 유지 (모멘텀 지속성 우세)

---

## 검증 후 액션 플랜

| 검증 결과 | 액션 |
|----------|------|
| 승률/손익비 미달 | 신호 필터 조건 강화 검토 |
| BB%B 임계값 조정 필요 | `kis_sector.py` BB_PCT_MAX 수정 |
| ATR 승수 조정 필요 | `main.py` 트레일링 계수 수정 |
| 외국인 Z-score 유효 | `kis_foreign.py` Z-score 로직 추가 |
| MSM 필요 | 별도 `regime_detector.py` 구현 검토 |
| slope 임계값 확정 | `morning_routine()` basis_slope 조건 추가 |
| VKOSPI 필터 유효 | `morning_routine()` vkospi 조건 추가 |
| 섹터 과열 악영향 | `kis_sector.py` 섹터 모멘텀 상한선 추가 |

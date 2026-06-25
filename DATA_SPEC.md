<!-- 전략·파라미터별 효과분석/최적화에 필요한 수집 데이터 사전 및 분석 매핑 (추후 분석용 마스터 문서) -->
# DATA_SPEC.md — 데이터 수집 사전 & 전략·파라미터 분석 매핑

> 목적. 이 시스템의 **모든 전략 요소·파라미터**를 나중에 효과분석·최적화하려면 어떤 데이터가 필요하고, 그게 실제로 수집되고 있는지 한곳에서 본다.
> 사용법. 새 세션은 (1) 아래 '수집 데이터 사전'으로 무슨 컬럼이 있는지 확인하고, (2) '파라미터 분석 매핑'으로 특정 파라미터를 어떤 데이터·방법으로 검증할지 찾는다.
> 마지막 갱신. 2026-06-25.

---

## 1. 수집 데이터 사전 (7종 로그)

서버는 운영 중 아래를 누적 기록하고, `scripts/export_data.sh`로 `data-export` 브랜치에 전송한다.

### 1-1. trades.csv — 체결 매매 (1매도 = 1행) · **분석 본체**
| 컬럼 | 의미 | 분석 용도 |
|---|---|---|
| exit_date/time, entry_date/time | 청산·진입 일시 | 보유기간·시간대 |
| code, name, sector | 종목·테마 | 종목/섹터별 성과 |
| entry_price, exit_price, qty, profit, profit_rate | 가격·손익 | 성과·승률·손익비 |
| reason | 청산 사유(손절/모멘텀익절/부분익절/본전보호/긴급손절/트레일/시간손절) | **청산 파라미터별 분해** |
| hold_days | 보유일 | 시간손절·보유효과 |
| peak_price, min_price, trigger_price | 고점·저점·발동가 | **트레일·손절 시뮬레이션** |
| momentum | 진입시 20일 모멘텀 | 모멘텀 임계 검증 |
| foreign_net_buy_mil | 외국인 순매수(백만) | 외국인 필터 |
| ma20_at_entry, ma60_at_entry | 진입시 이평 | 추세 필터 |
| volume_ratio | 거래량비(20일평균 대비) | 거래량 필터 |
| kospi_trend | 진입시 MA60 상승장 여부 | 국면 분해(현재 전건 True) |
| dip_entry_used | 눌림목(엄격) 진입 여부 | 진입타이밍 효과 |
| atr_at_entry | 진입시 ATR | ATR 승수 검증 |
| bb_pct_at_entry | 진입시 볼린저 %B | BB%B 임계 검증 |
| avg_tr_pbmn_mil | 20일 평균거래대금 | 대형주 여부·유동성 |
| is_mock | 모의투자 여부 | 모의/실전 분리 |
| **exposure_factor** | 진입시 노출배수(1.0 정상 / 0.5 스로틀) | **소프트 스로틀 효과분석** ⬅신규 |
| **crawl_source** | 테마 출처(live/cache/fallback) | **신호 품질 분석** ⬅신규 |

### 1-2. signal_log.csv — 일별 신호 스캔 전체(선정+탈락 모두)
date, sector, sector_rank, sector_avg_momentum, code, name, signal_price, momentum, is_uptrend, ma20, ma60, volume_ratio, foreign_5d_net_buy_mil, passed_all_filters, selected, bb_pct, atr, avg_tr_pbmn_mil
- 용도. 필터별 통과/탈락 분포, 선정 vs 탈락 비교. **단, 탈락 종목의 '이후 성과'는 없음(=핵심 갭, 4절).**

### 1-3. timing_log.csv — 매수 윈도우 분당 체크
date, code, name, check_time, dip_met, action
- action. waiting / bought_dip / bought_relaxed / bought_reserve / bought_verified / buy_failed / skipped_timeout / skipped_unaffordable / **skipped_market_crash**(급락가드 발동)
- 용도. 진입타이밍 효과, **급락 가드 발동 이력**.

### 1-4. followup_log.csv — 매도 후 사후 추적
code, name, exit_date, exit_price, reason, d3/d5/d10/d20_price·rate
- 용도. **익절/손절이 일렀나 늦었나**(보유 연장 시 가정 성과). 청산 파라미터 보정의 핵심.

### 1-5. market_log.csv — 아침 지수 궤적 (분당) ⬅신규
date, time, kodex200_change_rate, guard_threshold
- 용도. **급락 가드 레벨(-1.5%) 적정성** + 장초반 하락 **기울기** 분석(레벨 vs 기울기 비교).

### 1-6. basis_log.csv — 아침 베이시스/변동성
date, time, kospi200_spot, kospi200_futures, basis, basis_pct, basis_slope, vkospi
- 용도. 베이시스 slope 필터(2개월+), VKOSPI 필터(3개월+). ※ spot은 별도소스라 노이즈 큼(std 4.75%) — 가드용 지수는 market_log를 쓸 것.

### 1-7. error.log — 운영 에러/경고
- 용도. 서버 안정성, 가드·스로틀 발동 로그(log_warning) 추적.

---

## 2. 전략·파라미터 분석 매핑

각 요소를 "필요 데이터 → 분석법 → 현 수집상태"로 정리. ✅수집됨 / ⚠️부분 / ❌갭.

### 2-1. 진입 — 종목 선정
| 요소 | 파라미터 | 필요 데이터 | 분석법 | 상태 |
|---|---|---|---|---|
| 테마 모멘텀 | MIN_THEME_MOMENTUM=15 | signal_log(sector_avg_momentum, selected) + trades(성과) | 테마모멘텀 구간별 성과 | ✅ |
| 테마 출처 신뢰 | — | trades.crawl_source | live vs fallback 성과 비교 | ✅⬅신규 |
| 추세 필터 | MA20>MA60 | signal_log(is_uptrend, ma20/60) + 탈락종목 사후가 | 통과/탈락 사후성과 비교 | ❌ 탈락 사후가 없음 |
| 외국인 필터 | FOREIGN_BUY_THRESHOLD=0 | signal_log(foreign_5d) + 성과 | 순매수 비중별 성과 | ⚠️ 선정만, 탈락 사후 없음 |
| 거래량 필터 | 전일≥20일평균 | signal_log(volume_ratio) | 구간별 성과 | ⚠️ |
| BB%B 과열 | BB_PCT_MAX=0.95 / PREFER=0.85 | trades.bb_pct_at_entry + 성과 | 구간별 성과(현 N=11) | ⚠️ 표본 부족 |
| 대형주 | MIN_MKTCAP_BIL=5000 | trades.avg_tr_pbmn_mil | 대형/중소 성과 | ⚠️ 표본 부족 |

### 2-2. 진입 — 타이밍
| 요소 | 파라미터 | 필요 데이터 | 분석법 | 상태 |
|---|---|---|---|---|
| 진입 시작 | 09:15(코드)/09:20(주석) | timing_log(check_time, action) | 시각별 체결 성과 | ✅ ※코드/주석 불일치 미결 |
| 눌림목 vs 완화 | strict 09:30 / ext 10:00 | trades.dip_entry_used | 엄격/완화 성과 | ✅ |

### 2-3. 청산 (파라미터별)
| 파라미터 | 값 | 필요 데이터 | 분석법 | 상태 |
|---|---|---|---|---|
| 손절 | STOP_LOSS_RATE=0.05(하락장×0.6) | trades(reason, trigger_price) + followup(d3~d20) | 손절후 반등(휩쏘)율 | ✅ (followup) |
| 트레일 | TRAIL_STOP_RATE=0.12 | trades(peak_price, exit_price) | 고점대비 하락폭 분포 | ⚠️ 발동 사례 적음 |
| ATR 승수 | 1.5× | trades(atr_at_entry, peak, exit) | actual_dd / atr 분포 | ⚠️ atr 최근만 |
| 모멘텀익절 | MOMENTUM_EXIT_RATE=0.10 | trades + followup | 매도후 추가상승 여부 | ✅ (followup) |
| 부분익절 | PARTIAL_SELL_TRIGGER=0.20 | trades(reason='부분익절') | 부분익절 종목 잔여성과 | ⚠️ N=1 |
| 본전보호 | TRIGGER=0.07/FLOOR=0.02 | trades(reason='본전보호') | 발동 후 결과 | ⚠️ N=2 |
| 긴급손절 | EMERGENCY_STOP_RATE=0.08 | trades(reason='긴급손절') | 갭하락 회피 효과 | ⚠️ N=1 |
| 시간손절 | TIME_STOP_DAYS=20/MIN_RATE=0.05 | trades(hold_days, reason) | 장기보유 성과 | ❌ 아직 미발동 |

### 2-4. 시장 국면·보호장치
| 요소 | 파라미터 | 필요 데이터 | 분석법 | 상태 |
|---|---|---|---|---|
| 구조적 하락장 | MA60(069500) | trades.kospi_trend | 상승/하락장 성과 | ❌ 하락장 0건(차단되어 미거래) |
| 장중 급락 가드 | MARKET_CRASH_GUARD_RATE=1.5 | market_log + timing_log(skipped_market_crash) | 발동빈도 vs 그날 시장, 레벨 vs 기울기 | ✅⬅신규(축적중) |
| 소프트 스로틀 | STREAK=3/FACTOR=0.5 | trades.exposure_factor | 스로틀 거래 vs 정상 거래 성과 | ✅⬅신규(축적중) |

---

## 3. 분석 실행 가이드 (도달 조건별)

| 도달 조건 | 실행할 분석 | 참조 |
|---|---|---|
| 거래 30건 | analysis_plan #1·#9 정식, 차선 vs 본선 | analysis_plan.md |
| bb_pct 30건 | BB%B 0.85 페널티 완화 여부 | 2-1 |
| market_log 2~3주 | 급락 가드 레벨 vs 기울기 재보정 | 1-5 |
| 스로틀 발동 10회+ | exposure_factor=0.5 vs 1.0 성과 비교 | 2-4 |
| basis 2·3개월 | slope·VKOSPI 필터 | 1-6 |
| 손절 30건+ | 휩쏘율 30%+ 지속 시 캔들확인 강화 | 2-3 |
| 하락장 표본 확보 | 알파 vs 베타 분리(실전 전환 핵심) | 2-4 |

---

## 4. 알려진 데이터 갭 (우선순위)

### 🔴 P1. 탈락/스킵 종목 사후 성과 (counterfactual) — 미수집
- 문제. signal_log는 탈락 종목을 기록하지만 **그 종목의 이후 가격이 없어**, "필터가 실제로 나쁜 종목을 걸렀나"를 검증 못 한다. 급락가드·스로틀이 '안 산' 종목, 매수포기(skipped_timeout) 종목의 사후 성과도 마찬가지.
- 영향. 진입 필터(추세·외국인·거래량·BB%B) 최적화의 핵심 근거가 없음. analysis_plan #2·#4가 여기 막혀 있음.
- 제안 메커니즘(미구현). followup과 동형으로 `rejected_followup` — 매일 signal_log의 selected=False(및 timing_log skipped/급락가드/스로틀로 미진입) 종목을 큐에 적재하고, 3·5·10일 후 현재가를 조회해 `rejected_followup.csv`(code, date, reason_not_bought, signal_price, d3/d5/d10_rate)에 기록. KIS 분당 API 부하 고려해 종목수 상한·시간 분산 필요.
- **착수 전 사용자 승인 필요**(스케줄러 부하·신규 파일 추가).

### 🟡 P2. 진입 시각 코드/주석 불일치
- 09:15(코드) vs 09:20(주석). 결정 후 일치시킬 것.

### 🟡 P3. 장중 가격 경로 부재
- 청산 파라미터 정밀 백테스트는 1분봉 경로가 필요하나 KIS는 최근 며칠만 제공. peak/min/trigger + followup으로 근사 중. 풀 백테스트는 비현실적(DATA_SPEC 외 사유: 테마크롤 과거 스냅샷 부재).

---

## 5. 수집 무결성 체크 (배포 후 확인)

- [ ] trades.csv에 exposure_factor·crawl_source 채워지는지(첫 매수 후)
- [ ] market_log.csv 분당 행 쌓이는지(첫 장중)
- [ ] 급락일에 timing_log skipped_market_crash 남는지
- [ ] 스로틀 발동 시 trades.exposure_factor=0.5 기록되는지
- [ ] export_data.sh가 market_log.csv 포함 전송하는지

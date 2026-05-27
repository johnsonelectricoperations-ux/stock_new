# 동적 테마 기반 주도 테마 판별 및 대장주 선정 모듈
import time
from kis_indicator import get_daily_ohlcv, calc_atr
from kis_foreign import is_foreign_buying
from naver_theme import get_top_themes

BB_PCT_MAX = 0.95   # 볼린저 밴드 %B 상단 임계값 — 초과 시 과열 종목 제외
MIN_THEME_MOMENTUM = 15.0  # 테마 평균 모멘텀 최소 임계값 — 미달 테마 제외


def _analyze_stock(code: str) -> dict | None:
    df = get_daily_ohlcv(code)
    if len(df) < 60:
        return None
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    std20 = df['close'].rolling(20).std()
    latest = df.iloc[-1]
    price  = latest['close']
    ma20   = latest['ma20']
    ma60   = latest['ma60']
    bb_upper = ma20 + 2 * std20.iloc[-1]
    bb_lower = ma20 - 2 * std20.iloc[-1]
    bb_pct = round((price - bb_lower) / (bb_upper - bb_lower), 3) if bb_upper != bb_lower else 0.5

    price_20d = df.iloc[-21]['close']
    momentum  = (price - price_20d) / price_20d * 100
    is_uptrend = price > ma20 > ma60

    # 볼린저 밴드 %B 과열 필터
    bb_overbought = bb_pct > BB_PCT_MAX

    # 전일 거래량 vs 20일 평균 거래량
    avg_volume  = df['volume'].iloc[-21:-1].mean()
    prev_volume = df['volume'].iloc[-2]
    volume_ok   = avg_volume > 0 and prev_volume >= avg_volume
    volume_ratio = round(prev_volume / avg_volume, 2) if avg_volume > 0 else 0

    # ATR (변동성 기반 손절 임계값 결정용 데이터 수집)
    atr = calc_atr(df)

    # 일평균 거래대금 (외국인 Z-score 계산용 데이터 수집, 백만원 단위)
    avg_tr_pbmn_mil = round(df['tr_pbmn'].iloc[-21:-1].mean() / 1_000_000, 1) if 'tr_pbmn' in df.columns else 0

    detail = (f'현재가 {price:,} | MA20 {int(ma20):,} | MA60 {int(ma60):,} | '
              f'거래량 {"✅" if volume_ok else "❌"} | BB%B {bb_pct:.2f}{"🔥과열" if bb_overbought else ""}')
    return {
        'momentum': round(momentum, 2),
        'is_uptrend': is_uptrend,
        'volume_ok': volume_ok,
        'bb_pct': bb_pct,
        'bb_overbought': bb_overbought,
        'volume_ratio': volume_ratio,
        'ma20': round(ma20, 0),
        'ma60': round(ma60, 0),
        'atr': atr,
        'avg_tr_pbmn_mil': avg_tr_pbmn_mil,
        'signal_price': int(price),
        'detail': detail,
    }


def get_leading_sector_signals(top_sectors: int = 3, max_stocks: int = 4, save_log: bool = False) -> list:
    from datetime import datetime

    # 네이버 테마 동적 수집 (3단계 방어 포함)
    themes = get_top_themes(n=top_sectors * 4)
    print(f'[테마] {len(themes)}개 테마 분석 시작\n')

    # 테마별 평균 모멘텀 계산
    theme_scores = []
    theme_stock_data = {}

    for theme_name, stocks in themes.items():
        stock_results = []
        for code, name in stocks:
            try:
                result = _analyze_stock(code)
                if result:
                    stock_results.append((code, name, result))
                time.sleep(0.3)
            except Exception:
                time.sleep(0.3)
        if not stock_results:
            continue
        avg_momentum = sum(r[2]['momentum'] for r in stock_results) / len(stock_results)
        stock_results.sort(key=lambda x: -x[2]['momentum'])
        theme_scores.append((theme_name, round(avg_momentum, 2)))
        theme_stock_data[theme_name] = stock_results

    # 모멘텀 상위 top_sectors개 테마 선정 (최소 임계값 미달 테마 제외)
    theme_scores.sort(key=lambda x: -x[1])
    qualified = [t for t in theme_scores if t[1] >= MIN_THEME_MOMENTUM]
    if not qualified:
        print(f'[테마] 평균 모멘텀 {MIN_THEME_MOMENTUM}% 이상 테마 없음 — 오늘 매수 없음')
    top_names = {t[0] for t in qualified[:top_sectors]}

    candidates = []  # 모든 필터 통과 종목 풀
    scan_records = []
    today = datetime.now().strftime('%Y-%m-%d')

    for rank, (theme_name, avg_score) in enumerate(
        [t for t in theme_scores if t[0] in top_names], start=1
    ):
        print(f'[주도 테마 {rank}위] {theme_name} 평균 모멘텀 {avg_score:+.2f}%')

        for code, name, result in theme_stock_data[theme_name]:
            print(f'  {name}({code}) {result["momentum"]:+.2f}% '
                  f'{"✅추세" if result["is_uptrend"] else "❌추세"} '
                  f'{"✅거래량" if result["volume_ok"] else "❌거래량"}')

            frgn_total = None
            passed = False

            if not result['is_uptrend']:
                print('  → 하락추세 제외')
            elif not result['volume_ok']:
                print('  → 거래량 미달 제외')
            elif result['bb_overbought']:
                print(f'  → BB%B 과열({result["bb_pct"]:.2f}) 제외')
            else:
                ok, frgn_total = is_foreign_buying(code)
                label = f'{frgn_total:+,}백만원'
                if not ok:
                    print(f'  → 외국인 순매도 ({label}) 제외')
                else:
                    passed = True
                    print(f'  → 외국인 순매수 ({label}) ✅ 후보 등록')
                    candidates.append({
                        'sector': theme_name,
                        'code': code,
                        'name': name,
                        'momentum': result['momentum'],
                        'ma20': result['ma20'],
                        'ma60': result['ma60'],
                        'volume_ratio': result['volume_ratio'],
                        'signal_price': result['signal_price'],
                        'foreign_net_buy_mil': frgn_total,
                        'detail': result['detail'],
                    })

            scan_records.append({
                'date': today,
                'sector': theme_name,
                'sector_rank': rank,
                'sector_avg_momentum': avg_score,
                'code': code,
                'name': name,
                'signal_price': result['signal_price'],
                'momentum': result['momentum'],
                'is_uptrend': result['is_uptrend'],
                'ma20': result['ma20'],
                'ma60': result['ma60'],
                'volume_ratio': result['volume_ratio'],
                'foreign_5d_net_buy_mil': frgn_total,
                'passed_all_filters': passed,
                'selected': False,
                # 데이터 수집 전용 — 향후 동적 임계값 결정용
                'bb_pct': result['bb_pct'],
                'atr': result['atr'],
                'avg_tr_pbmn_mil': result['avg_tr_pbmn_mil'],
            })

        print()

    # 전체 후보 중 모멘텀 상위 max_stocks개 최종 선정
    candidates.sort(key=lambda x: -x['momentum'])
    signals = candidates[:max_stocks]

    # scan_records selected 플래그 갱신
    selected_codes = {s['code'] for s in signals}
    for r in scan_records:
        if r['code'] in selected_codes:
            r['selected'] = True

    if signals:
        print(f'→ 최종 선정 {len(signals)}종목: {[s["name"] for s in signals]}')

    if save_log and scan_records:
        from performance import log_signal_scan
        log_signal_scan(scan_records)

    return signals


if __name__ == '__main__':
    signals = get_leading_sector_signals(top_sectors=3, max_stocks=4)
    print('=' * 50)
    print(f'→ 최종 매수 신호 종목: {len(signals)}개')
    for s in signals:
        print(f"  [{s['sector']}] {s['name']}({s['code']}) 모멘텀 {s['momentum']:+.2f}%")
        print(f"  {s['detail']}")

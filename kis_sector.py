# 동적 테마 기반 주도 테마 판별 및 대장주 선정 모듈
import time
from kis_indicator import get_daily_ohlcv
from kis_foreign import is_foreign_buying
from naver_theme import get_top_themes


def _analyze_stock(code: str) -> dict | None:
    df = get_daily_ohlcv(code)
    if len(df) < 60:
        return None
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    latest = df.iloc[-1]
    price = latest['close']
    ma20 = latest['ma20']
    ma60 = latest['ma60']
    price_20d = df.iloc[-21]['close']
    momentum = (price - price_20d) / price_20d * 100
    is_uptrend = price > ma20 > ma60
    detail = f'현재가 {price:,} | MA20 {int(ma20):,} | MA60 {int(ma60):,}'
    return {
        'momentum': round(momentum, 2),
        'is_uptrend': is_uptrend,
        'detail': detail,
    }


def get_leading_sector_signals(top_sectors: int = 3, stocks_per_sector: int = 2, save_log: bool = False) -> list:
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

    # 모멘텀 상위 top_sectors개 테마 선정
    theme_scores.sort(key=lambda x: -x[1])
    top_names = {t[0] for t in theme_scores[:top_sectors]}

    signals = []
    scan_records = []
    today = datetime.now().strftime('%Y-%m-%d')

    for rank, (theme_name, avg_score) in enumerate(
        [t for t in theme_scores if t[0] in top_names], start=1
    ):
        print(f'[주도 테마 {rank}위] {theme_name} 평균 모멘텀 {avg_score:+.2f}%')
        selected_count = 0

        for code, name, result in theme_stock_data[theme_name]:
            trend_label = '✅ 상승추세' if result['is_uptrend'] else '❌ 하락추세'
            print(f'  {name}({code}) {result["momentum"]:+.2f}% {trend_label}')

            frgn_total = None
            passed = False
            selected = False

            if not result['is_uptrend']:
                print('  → 하락추세 제외')
            else:
                ok, frgn_total = is_foreign_buying(code)
                label = f'{frgn_total:+,}백만원'
                if not ok:
                    print(f'  → 외국인 순매도 ({label}) 제외')
                elif selected_count < stocks_per_sector:
                    passed = True
                    selected = True
                    selected_count += 1
                    print(f'  → 외국인 순매수 ({label}) ✅ 선정 ({selected_count}/{stocks_per_sector})')
                    signals.append({
                        'sector': theme_name,
                        'code': code,
                        'name': name,
                        'momentum': result['momentum'],
                        'detail': result['detail'],
                    })
                else:
                    passed = True
                    print(f'  → 필터 통과 (테마당 {stocks_per_sector}종목 제한으로 미선정)')

            scan_records.append({
                'date': today,
                'sector': theme_name,
                'sector_rank': rank,
                'sector_avg_momentum': avg_score,
                'code': code,
                'name': name,
                'momentum': result['momentum'],
                'is_uptrend': result['is_uptrend'],
                'foreign_5d_net_buy_mil': frgn_total,
                'passed_all_filters': passed,
                'selected': selected,
            })

        print()

    if save_log and scan_records:
        from performance import log_signal_scan
        log_signal_scan(scan_records)

    return signals


if __name__ == '__main__':
    signals = get_leading_sector_signals(top_sectors=3, stocks_per_sector=2)
    print('=' * 50)
    print(f'→ 최종 매수 신호 종목: {len(signals)}개')
    for s in signals:
        print(f"  [{s['sector']}] {s['name']}({s['code']}) 모멘텀 {s['momentum']:+.2f}%")
        print(f"  {s['detail']}")

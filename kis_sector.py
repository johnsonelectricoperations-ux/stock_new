# 섯터별 주도 섯터 판별 및 대장주 선정 모듈
import time
from kis_indicator import get_daily_ohlcv
from kis_foreign import is_foreign_buying

SECTORS = {
    '반도체': [
        ('005930', '삼성전자'),
        ('000660', 'SK하이닉스'),
        ('009150', '삼성전기'),
        ('006400', '삼성SDI'),
    ],
    '자동차': [
        ('005380', '현대자'),
        ('000270', '기아'),
        ('012330', '현대모비스'),
    ],
    '화학/에너지': [
        ('051910', 'LG화학'),
        ('096770', 'SK이노베이션'),
        ('005490', 'POSCO홍딩스'),
    ],
    'IT/플랫폼': [
        ('035420', 'NAVER'),
        ('035720', '카카오'),
        ('018260', '삼성SDS'),
    ],
    '금융/유통': [
        ('032830', '삼성생명'),
        ('028260', '삼성물산'),
    ],
    '전자/가전': [
        ('066570', 'LG전자'),
        ('003550', 'LG'),
    ],
    '통신': [
        ('017670', 'SK텔레콤'),
        ('030200', 'KT'),
    ],
    '바이오/헬스': [
        ('068270', '셀트리온'),
    ],
}

def _analyze_stock(code):
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
        'detail': detail
    }

def get_leading_sector_signals(top_sectors=3, save_log=False):
    from datetime import datetime
    print('섯터별 모멘텀 분석 중... (약 2~3분 소요)\n')

    sector_results = {}
    for sector, stocks in SECTORS.items():
        stock_data = []
        for code, name in stocks:
            try:
                result = _analyze_stock(code)
                if result:
                    stock_data.append((code, name, result))
                time.sleep(0.3)
            except Exception:
                time.sleep(0.3)

        if not stock_data:
            continue

        avg_score = sum(d[2]['momentum'] for d in stock_data) / len(stock_data)
        stock_data.sort(key=lambda x: x[2]['momentum'], reverse=True)
        sector_results[sector] = {
            'avg_score': round(avg_score, 2),
            'stocks': stock_data
        }

    sorted_sectors = sorted(
        sector_results.items(),
        key=lambda x: x[1]['avg_score'],
        reverse=True
    )

    signals = []
    scan_records = []
    today = datetime.now().strftime('%Y-%m-%d')

    for rank, (sector, data) in enumerate(sorted_sectors, start=1):
        print(f'[주도 섯터] {sector} 평균 {data["avg_score"]:+.2f}%')
        sector_selected = False

        for code, name, result in data['stocks']:
            trend = '✅ 상승추세' if result['is_uptrend'] else '❌ 하락추세'
            print(f'  {name}({code}) {result["momentum"]:+.2f}% {trend}')

            frgn_total = None
            passed = False
            selected = False

            if not result['is_uptrend']:
                print(f'  → 하락추세 제외')
            else:
                ok, frgn_total = is_foreign_buying(code)
                label = f'{frgn_total:+,}백만원'
                if not ok:
                    print(f'  → 외국인 순매도 ({label}) 제외')
                elif rank <= top_sectors and not sector_selected:
                    passed = True
                    selected = True
                    sector_selected = True
                    print(f'  → 외국인 순매수 ({label}) ✅ 대장주 선정')
                    signals.append({
                        'sector': sector,
                        'code': code,
                        'name': name,
                        'momentum': result['momentum'],
                        'detail': result['detail']
                    })
                else:
                    passed = True  # 필터는 통과했지만 섹터당 1종목 제한으로 미선정

            scan_records.append({
                'date': today,
                'sector': sector,
                'sector_rank': rank,
                'sector_avg_momentum': data['avg_score'],
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
    signals = get_leading_sector_signals(top_sectors=3)
    print('=' * 50)
    print(f'→ 최종 매수 신호 종목: {len(signals)}개')
    for s in signals:
        print(f"  [{s['sector']}] {s['name']}({s['code']}) 모멘텀 {s['momentum']:+.2f}%")
        print(f"  {s['detail']}")

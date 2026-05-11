# 섯터별 주도 섯터 판별 및 대장주 선정 모듈
from kis_indicator import get_daily_ohlcv, check_trend

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

def _get_momentum(stock_code):
    df = get_daily_ohlcv(stock_code)
    if len(df) < 21:
        return None
    price_now = df.iloc[-1]['close']
    price_20d = df.iloc[-21]['close']
    return (price_now - price_20d) / price_20d * 100

def analyze_sectors():
    sector_results = {}

    for sector, stocks in SECTORS.items():
        stock_scores = []
        for code, name in stocks:
            try:
                score = _get_momentum(code)
                if score is not None:
                    stock_scores.append((code, name, round(score, 2)))
            except Exception:
                pass

        if not stock_scores:
            continue

        avg_score = sum(s[2] for s in stock_scores) / len(stock_scores)
        stock_scores.sort(key=lambda x: x[2], reverse=True)
        sector_results[sector] = {
            'avg_score': round(avg_score, 2),
            'stocks': stock_scores
        }

    return sector_results

def get_leading_sector_signals(top_sectors=2):
    print('섯터별 모멘텀 분석 중...\n')
    sector_results = analyze_sectors()

    sorted_sectors = sorted(
        sector_results.items(),
        key=lambda x: x[1]['avg_score'],
        reverse=True
    )

    signals = []
    for sector, data in sorted_sectors[:top_sectors]:
        print(f'[주도 섯터] {sector} 평균 {data["avg_score"]:+.2f}%')
        for code, name, score in data['stocks']:
            try:
                is_up, detail = check_trend(code)
            except Exception:
                print(f'  {name}({code}) {score:+.2f}% ⚠️ 조회 실패 제외')
                continue
            trend = '✅ 상승추세' if is_up else '❌ 하락추세'
            print(f'  {name}({code}) {score:+.2f}% {trend}')
            if is_up:
                signals.append({
                    'sector': sector,
                    'code': code,
                    'name': name,
                    'momentum': score,
                    'detail': detail
                })
        print()

    return signals

if __name__ == '__main__':
    signals = get_leading_sector_signals(top_sectors=2)
    print('=' * 50)
    print(f'→ 최종 매수 신호 종목: {len(signals)}개')
    for s in signals:
        print(f"  [{s['sector']}] {s['name']}({s['code']}) 모멘텀 {s['momentum']:+.2f}%")
        print(f"  {s['detail']}")

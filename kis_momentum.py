# 코스피200 시총 상위 종목 대상 20일 모멘텀 스코어링 모듈
from kis_indicator import get_daily_ohlcv

KOSPI200_TOP = [
    ('005930', '삼성전자'),
    ('000660', 'SK하이닉스'),
    ('005490', 'POSCO홍딩스'),
    ('035420', 'NAVER'),
    ('005380', '현대자'),
    ('000270', '기아'),
    ('068270', '셀트리온'),
    ('051910', 'LG화학'),
    ('006400', '삼성SDI'),
    ('028260', '삼성물산'),
    ('012330', '현대모비스'),
    ('066570', 'LG전자'),
    ('003550', 'LG'),
    ('009150', '삼성전기'),
    ('032830', '삼성생명'),
    ('096770', 'SK이노베이션'),
    ('017670', 'SK텔레콤'),
    ('035720', '카카오'),
    ('030200', 'KT'),
    ('018260', '삼성SDS'),
]

def get_momentum_score(stock_code):
    df = get_daily_ohlcv(stock_code)
    if len(df) < 21:
        return None
    price_now = df.iloc[-1]['close']
    price_20d = df.iloc[-21]['close']
    return (price_now - price_20d) / price_20d * 100

def get_top_momentum_stocks(top_n=5):
    scores = []
    for code, name in KOSPI200_TOP:
        try:
            score = get_momentum_score(code)
            if score is not None:
                scores.append((code, name, round(score, 2)))
        except Exception as e:
            print(f'[{code}] 오류: {e}')

    scores.sort(key=lambda x: x[2], reverse=True)
    return scores[:top_n]

if __name__ == '__main__':
    print('20일 모멘텀 상위 5종목 조회 중...\n')
    top = get_top_momentum_stocks(top_n=5)
    print(f'{"순위":<5} {"종목코드":<10} {"종목명":<15} {"20일수익률"}')
    print('-' * 45)
    for i, (code, name, score) in enumerate(top, 1):
        print(f'{i:<5} {code:<10} {name:<15} {score:+.2f}%')

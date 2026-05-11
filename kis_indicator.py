# 일봉 데이터 조회 및 MA20/MA60 추세 필터 모듈
import requests
import urllib3
import pandas as pd
from datetime import datetime, timedelta
from config.settings import KIS_BASE_URL, KIS_IS_MOCK
from kis_auth import get_headers

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_daily_ohlcv(stock_code, days=120):
    url = f'{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice'
    headers = get_headers('FHKST03010100')
    end_date = datetime.today().strftime('%Y%m%d')
    start_date = (datetime.today() - timedelta(days=days)).strftime('%Y%m%d')
    params = {
        'fid_cond_mrkt_div_code': 'J',
        'fid_input_iscd': stock_code,
        'fid_input_date_1': start_date,
        'fid_input_date_2': end_date,
        'fid_period_div_code': 'D',
        'fid_org_adj_prc': '0'
    }
    verify = not KIS_IS_MOCK
    res = requests.get(url, headers=headers, params=params, verify=verify)
    res.raise_for_status()
    data = res.json()

    if data['rt_cd'] != '0':
        raise Exception(f"API 오류: {data['msg1']}")

    output_key = 'output2' if 'output2' in data else 'output'
    rows = []
    for item in data[output_key]:
        if item.get('stck_clpr') and item['stck_clpr'] != '0':
            rows.append({
                'date':   item['stck_bsop_date'],
                'close':  int(item['stck_clpr']),
                'volume': int(item.get('acml_vol', 0)),
            })

    df = pd.DataFrame(rows)
    df = df.sort_values('date').reset_index(drop=True)
    return df


def check_market_trend():
    """KOSPI 지수 MA60 필터 — KODEX 200 ETF(069500) 기준.
    True: 상승장 (매수 허용) / False: 하락장 (매수 중단)
    """
    try:
        df = get_daily_ohlcv('069500')
        if len(df) < 60:
            return True  # 데이터 부족 시 통과
        df['ma60'] = df['close'].rolling(60).mean()
        latest = df.iloc[-1]
        return latest['close'] > latest['ma60']
    except Exception:
        return True  # 조회 실패 시 통과


def check_trend(stock_code):
    df = get_daily_ohlcv(stock_code)

    if len(df) < 60:
        return False, f'데이터 부족 ({len(df)}일)'

    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()

    latest = df.iloc[-1]
    price = latest['close']
    ma20 = latest['ma20']
    ma60 = latest['ma60']

    is_uptrend = price > ma20 > ma60
    detail = f'현재가 {price:,} | MA20 {int(ma20):,} | MA60 {int(ma60):,}'

    return is_uptrend, detail


if __name__ == '__main__':
    is_bull = check_market_trend()
    print(f'KOSPI 시장 추세: {"✅ 상승장" if is_bull else "❌ 하락장"}')
    code = '005930'
    is_up, detail = check_trend(code)
    print(f'[{code}] 추세 필터: {"✅ 상승추세" if is_up else "❌ 하락추세"}')
    print(detail)

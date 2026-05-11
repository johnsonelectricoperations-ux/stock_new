# 종목별 외국인 5일 누적 순매수 필터 모듈
import requests
import urllib3
from config.settings import KIS_BASE_URL, KIS_IS_MOCK, FOREIGN_BUY_THRESHOLD
from kis_auth import get_headers

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_foreign_net_buy(stock_code, days=5):
    url = f'{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor'
    headers = get_headers('FHKST01010900')
    params = {
        'fid_cond_mrkt_div_code': 'J',
        'fid_input_iscd': stock_code
    }
    verify = not KIS_IS_MOCK
    res = requests.get(url, headers=headers, params=params, verify=verify)
    res.raise_for_status()
    data = res.json()

    if data['rt_cd'] != '0':
        raise Exception(f"API 오류: {data['msg1']}")

    output = data.get('output', [])
    recent = output[:days]
    total = sum(int(d.get('frgn_ntby_tr_pbmn', 0)) for d in recent)
    return total  # 백만원 단위

def is_foreign_buying(stock_code):
    try:
        total = get_foreign_net_buy(stock_code, days=5)
        return total > FOREIGN_BUY_THRESHOLD, total
    except Exception:
        return True, 0  # 조회 실패 시 필터 통과

if __name__ == '__main__':
    code = '005930'
    ok, total = is_foreign_buying(code)
    label = '✅ 순매수' if total > 0 else '❌ 순매도'
    print(f'[{code}] 외국인 5일 누적: {total:+,}백만원 {label}')
    print(f'매수 필터 통과: {ok}')

# KIS API로 종목 현재가 및 일봉 데이터를 조회하는 모듈
import requests
import urllib3
from config.settings import KIS_BASE_URL, KIS_IS_MOCK
from kis_auth import get_headers

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_current_price(stock_code):
    url = f'{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price'
    headers = get_headers('VTTC8434R' if KIS_IS_MOCK else 'FHKST01010100')
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

    output = data['output']
    return {
        'code': stock_code,
        'name': output.get('hts_kor_isnm', ''),
        'price': int(output['stck_prpr']),
        'change_rate': float(output['prdy_ctrt']),
        'volume': int(output['acml_vol'])
    }

if __name__ == '__main__':
    result = get_current_price('005930')
    print(f"[{result['code']}] {result['name']}")
    print(f"현재가: {result['price']:,}원")
    print(f"등락률: {result['change_rate']}%")
    print(f"거래량: {result['volume']:,}주")

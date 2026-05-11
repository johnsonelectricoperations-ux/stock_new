# KIS API 매수/매도 주문 실행 및 포지션 사이징 모듈
import requests
import urllib3
import json
from kis_auth import get_headers
from config.settings import (
    KIS_BASE_URL, KIS_IS_MOCK,
    KIS_CANO, KIS_ACNT_PRDT_CD,
    TOTAL_BUDGET, MAX_STOCK_COUNT
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BUY_TR_ID  = 'VTTC0802U' if KIS_IS_MOCK else 'TTTC0802U'
SELL_TR_ID = 'VTTC0801U' if KIS_IS_MOCK else 'TTTC0801U'

def _post_order(tr_id, body):
    url = f'{KIS_BASE_URL}/uapi/domestic-stock/v1/trading/order-cash'
    headers = get_headers(tr_id)
    verify = not KIS_IS_MOCK
    res = requests.post(url, headers=headers, data=json.dumps(body), verify=verify)
    res.raise_for_status()
    return res.json()

def buy_stock(stock_code, quantity):
    body = {
        'CANO': KIS_CANO,
        'ACNT_PRDT_CD': KIS_ACNT_PRDT_CD,
        'PDNO': stock_code,
        'ORD_DVSN': '01',  # 시장가
        'ORD_QTY': str(quantity),
        'ORD_UNPR': '0'
    }
    result = _post_order(BUY_TR_ID, body)
    if result.get('rt_cd') != '0':
        raise Exception(f"매수 실패: {result.get('msg1')}")
    return result

def sell_stock(stock_code, quantity):
    body = {
        'CANO': KIS_CANO,
        'ACNT_PRDT_CD': KIS_ACNT_PRDT_CD,
        'PDNO': stock_code,
        'ORD_DVSN': '01',  # 시장가
        'ORD_QTY': str(quantity),
        'ORD_UNPR': '0'
    }
    result = _post_order(SELL_TR_ID, body)
    if result.get('rt_cd') != '0':
        raise Exception(f"매도 실패: {result.get('msg1')}")
    return result

def calc_quantity(price, stock_count=None, effective_budget=None):
    count = stock_count or MAX_STOCK_COUNT
    budget = effective_budget if effective_budget is not None else TOTAL_BUDGET
    budget_per_stock = budget // count
    return max(1, budget_per_stock // price)

if __name__ == '__main__':
    from kis_data import get_current_price
    code = '005930'
    info = get_current_price(code)
    qty = calc_quantity(info['price'])
    print(f'[{code}] 현재가: {info["price"]:,}원')
    print(f'종목당 배분금액: {TOTAL_BUDGET // MAX_STOCK_COUNT:,}원')
    print(f'매수 가능 수량: {qty}주')
    print(f'실제 투자금액: {info["price"] * qty:,}원')
    print()
    print('실제 주문은 main.py 에서 신호 생성 후 실행됩니다.')

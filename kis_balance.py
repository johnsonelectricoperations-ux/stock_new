# KIS API 계좌 잔고 조회 모듈
import requests
import urllib3
from config.settings import KIS_ORDER_BASE_URL, KIS_IS_MOCK, KIS_CANO, KIS_ACNT_PRDT_CD
from kis_auth import get_headers

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_balance():
    url = f'{KIS_ORDER_BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance'
    tr_id = 'VTTC8434R' if KIS_IS_MOCK else 'TTTC8434R'
    headers = get_headers(tr_id)
    params = {
        'CANO': KIS_CANO,
        'ACNT_PRDT_CD': KIS_ACNT_PRDT_CD,
        'AFHR_FLPR_YN': 'N',
        'OFL_YN': 'N',
        'INQR_DVSN': '01',
        'UNPR_DVSN': '01',
        'FUND_STTL_ICLD_YN': 'N',
        'FNCG_AMT_AUTO_RDPT_YN': 'N',
        'PRCS_DVSN': '00',
        'CTX_AREA_FK100': '',
        'CTX_AREA_NK100': ''
    }
    verify = not KIS_IS_MOCK
    res = requests.get(url, headers=headers, params=params, verify=verify)
    res.raise_for_status()
    data = res.json()

    if data['rt_cd'] != '0':
        raise Exception(f"API 오류: {data['msg1']}")

    output2 = data.get('output2', [{}])[0]
    stocks = data.get('output1', [])

    return {
        'cash': int(output2.get('dnca_tot_amt', 0)),
        'eval_amt': int(output2.get('scts_evlu_amt', 0)),
        'total_amt': int(output2.get('tot_evlu_amt', 0)),
        'profit_loss': int(output2.get('evlu_pfls_smtl_amt', 0)),
        'profit_rate': float(output2.get('asst_icdc_erng_rt', 0)),
        'stocks': [
            {
                'name': s.get('prdt_name', ''),
                'code': s.get('pdno', ''),
                'qty': int(s.get('hldg_qty', 0)),
                'avg_price': int(float(s.get('pchs_avg_pric', 0))),
                'current_price': int(s.get('prpr', 0)),
                'profit_rate': float(s.get('evlu_pfls_rt', 0))
            }
            for s in stocks if int(s.get('hldg_qty', 0)) > 0
        ]
    }

def get_orderable_cash(code: str, price: int) -> int | None:
    """종목별 실제 매수가능금액(미수 없는 현금 기준) 조회.
    예수금≠주문가능금액(T+2 미결제) 불일치로 인한 주문 거부 방지용.
    조회 실패 시 None 반환 → 호출부에서 상한 미적용(기존 동작 폴백).
    """
    try:
        url = f'{KIS_ORDER_BASE_URL}/uapi/domestic-stock/v1/trading/inquire-psbl-order'
        tr_id = 'VTTC8908R' if KIS_IS_MOCK else 'TTTC8908R'
        headers = get_headers(tr_id)
        params = {
            'CANO': KIS_CANO,
            'ACNT_PRDT_CD': KIS_ACNT_PRDT_CD,
            'PDNO': code,
            'ORD_UNPR': str(int(price)),
            'ORD_DVSN': '01',            # 시장가
            'CMA_EVLU_AMT_ICLD_YN': 'N',
            'OVRS_ICLD_YN': 'N',
        }
        verify = not KIS_IS_MOCK
        res = requests.get(url, headers=headers, params=params, verify=verify, timeout=10)
        res.raise_for_status()
        data = res.json()
        if data.get('rt_cd') != '0':
            return None
        out = data.get('output', {})
        # 미수 없는 매수금액 우선, 없으면 주문가능현금 → 최대매수금액 순
        for key in ('nrcvb_buy_amt', 'ord_psbl_cash', 'max_buy_amt'):
            v = out.get(key)
            if v not in (None, ''):
                return int(float(v))
        return None
    except Exception:
        return None


if __name__ == '__main__':
    b = get_balance()
    print(f'예수금: {b["cash"]:,}원')
    print(f'주식 평가금액: {b["eval_amt"]:,}원')
    print(f'씽 평가액: {b["total_amt"]:,}원')
    print(f'평가손익: {b["profit_loss"]:+,}원 ({b["profit_rate"]:+.2f}%)')
    if b['stocks']:
        print('\n보유 종목')
        for s in b['stocks']:
            print(f"  {s['name']}({s['code']}) {s['qty']}주 | 평단가 {s['avg_price']:,} | 현재가 {s['current_price']:,} | {s['profit_rate']:+.2f}%")
    else:
        print('보유 종목 없음')

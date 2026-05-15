# KIS API 주문 엔드포인트 진단 스크립트 (500 오류 원인 파악용)
import json
import requests
import urllib3
from config.settings import KIS_BASE_URL, KIS_IS_MOCK, KIS_CANO, KIS_ACNT_PRDT_CD, KIS_APP_KEY, KIS_APP_SECRET
from kis_auth import get_headers, get_access_token

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print('=== KIS API 진단 ===')
print(f'IS_MOCK    : {KIS_IS_MOCK}')
print(f'BASE_URL   : {KIS_BASE_URL}')
print(f'CANO       : {repr(KIS_CANO)} (길이: {len(KIS_CANO)})')
print(f'ACNT_PRDT  : {repr(KIS_ACNT_PRDT_CD)} (길이: {len(KIS_ACNT_PRDT_CD)})')
print(f'APP_KEY    : {KIS_APP_KEY[:8]}...' if KIS_APP_KEY else 'APP_KEY: None')
print()

# 토큰 확인
try:
    token = get_access_token()
    print(f'토큰 발급 성공: {token[:20]}...')
except Exception as e:
    print(f'토큰 발급 실패: {e}')
    exit(1)

# 주문 헤더 확인
tr_id = 'VTTC0802U' if KIS_IS_MOCK else 'TTTC0802U'
headers = get_headers(tr_id)
headers['custtype'] = 'P'
print(f'TR_ID: {tr_id}')
print(f'헤더 키: {list(headers.keys())}')
print()

# 실제 주문 요청 (삼성전자 1주 시장가)
body = {
    'CANO': KIS_CANO,
    'ACNT_PRDT_CD': KIS_ACNT_PRDT_CD,
    'PDNO': '005930',
    'ORD_DVSN': '01',
    'ORD_QTY': '1',
    'ORD_UNPR': '0'
}
print(f'요청 body: {json.dumps(body, ensure_ascii=False)}')

url = f'{KIS_BASE_URL}/uapi/domestic-stock/v1/trading/order-cash'
verify = not KIS_IS_MOCK

try:
    res = requests.post(url, headers=headers, data=json.dumps(body), verify=verify, timeout=10)
    print(f'응답 HTTP 상태: {res.status_code}')
    print(f'응답 본문: {res.text[:1000]}')
    try:
        data = res.json()
        print(f'rt_cd: {data.get("rt_cd")}')
        print(f'msg1 : {data.get("msg1")}')
        print(f'msg_cd: {data.get("msg_cd")}')
    except Exception:
        pass
except Exception as e:
    print(f'요청 예외: {e}')

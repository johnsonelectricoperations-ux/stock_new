# KIS API 접근 토큰 발급 및 자동 갱신 모듈
import requests
import json
import urllib3
from datetime import datetime, timedelta
from config.settings import KIS_APP_KEY, KIS_APP_SECRET, KIS_BASE_URL, KIS_IS_MOCK

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_token_info = {
    'token': None,
    'expires_at': None
}

def get_access_token():
    if _token_info['token'] and _token_info['expires_at'] > datetime.now():
        return _token_info['token']

    url = f'{KIS_BASE_URL}/oauth2/tokenP'
    headers = {'content-type': 'application/json'}
    body = {
        'grant_type': 'client_credentials',
        'appkey': KIS_APP_KEY,
        'appsecret': KIS_APP_SECRET
    }

    # 모의투자 서버는 SSL 인증서 호스트명 불일치 문제가 있어 verify=False 사용
    verify = not KIS_IS_MOCK
    res = requests.post(url, headers=headers, data=json.dumps(body), verify=verify)
    res.raise_for_status()
    data = res.json()

    _token_info['token'] = data['access_token']
    _token_info['expires_at'] = datetime.now() + timedelta(seconds=data['expires_in'] - 60)

    return _token_info['token']

def get_headers(tr_id):
    token = get_access_token()
    return {
        'content-type': 'application/json',
        'authorization': f'Bearer {token}',
        'appkey': KIS_APP_KEY,
        'appsecret': KIS_APP_SECRET,
        'tr_id': tr_id
    }

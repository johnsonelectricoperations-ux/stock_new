# 실전 도메인 순위분석 API 클라이언트 — 당일 주도주 풀 조회 (섀도 선정용, 모의투자 도메인 미지원)
import json
import requests
import urllib3
from datetime import datetime, timedelta
from pathlib import Path
from config.settings import KIS_REAL_APP_KEY, KIS_REAL_APP_SECRET, KIS_REAL_BASE_URL

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOKEN_FILE = Path(__file__).parent / 'config' / 'token_cache_real.json'


def is_rank_api_configured() -> bool:
    """실전 앱키가 설정되어 순위 API 사용 가능한지 (미설정이면 섀도 선정 비활성)."""
    return bool(KIS_REAL_APP_KEY and KIS_REAL_APP_SECRET)


def _load_token():
    if not TOKEN_FILE.exists():
        return None
    try:
        with open(TOKEN_FILE, 'r') as f:
            data = json.load(f)
        if datetime.fromisoformat(data['expires_at']) > datetime.now():
            return data['token']
    except Exception:
        pass
    return None


def _save_token(token, expires_at):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, 'w') as f:
        json.dump({'token': token, 'expires_at': expires_at.isoformat()}, f)


def _get_token() -> str:
    token = _load_token()
    if token:
        return token
    res = requests.post(
        f'{KIS_REAL_BASE_URL}/oauth2/tokenP',
        headers={'content-type': 'application/json'},
        data=json.dumps({'grant_type': 'client_credentials',
                         'appkey': KIS_REAL_APP_KEY, 'appsecret': KIS_REAL_APP_SECRET}),
        timeout=10,
    )
    res.raise_for_status()
    data = res.json()
    token = data['access_token']
    _save_token(token, datetime.now() + timedelta(seconds=data['expires_in'] - 60))
    return token


def _headers(tr_id: str) -> dict:
    return {
        'content-type': 'application/json',
        'authorization': f'Bearer {_get_token()}',
        'appkey': KIS_REAL_APP_KEY,
        'appsecret': KIS_REAL_APP_SECRET,
        'tr_id': tr_id,
    }


def _fetch_rank(path: str, tr_id: str, params: dict) -> list:
    res = requests.get(f'{KIS_REAL_BASE_URL}{path}', headers=_headers(tr_id),
                       params=params, timeout=10)
    res.raise_for_status()
    data = res.json()
    if data.get('rt_cd') != '0':
        raise Exception(f"순위 API 오류({tr_id}): {data.get('msg1')}")
    return data.get('output') or []


def _row(item: dict, source: str) -> dict | None:
    """응답 필드명이 API마다 달라(mksc/stck) 방어적으로 파싱."""
    code = item.get('mksc_shrn_iscd') or item.get('stck_shrn_iscd') or ''
    if not code or len(code) != 6:
        return None
    try:
        price = int(float(item.get('stck_prpr') or 0))
        change_rate = float(item.get('prdy_ctrt') or 0)
    except (ValueError, TypeError):
        return None
    return {'code': code, 'name': item.get('hts_kor_isnm', ''),
            'price': price, 'change_rate': change_rate, 'source': source}


def get_fluctuation_rank(top_n: int = 15) -> list:
    """당일 상승률 순위 (실전 도메인). 실패 시 예외 전파 — 호출부에서 처리."""
    output = _fetch_rank('/uapi/domestic-stock/v1/ranking/fluctuation', 'FHPST01700000', {
        'fid_cond_mrkt_div_code': 'J',
        'fid_cond_scr_div_code': '20170',
        'fid_input_iscd': '0000',
        'fid_rank_sort_cls_code': '0000',   # 상승율순
        'fid_input_cnt_1': '0',
        'fid_prc_cls_code': '0',
        'fid_input_price_1': '',
        'fid_input_price_2': '',
        'fid_vol_cnt': '100000',            # 최소 거래량 — 저유동성 잡주 제외
        'fid_trgt_cls_code': '0',
        'fid_trgt_exls_cls_code': '0',
        'fid_div_cls_code': '0',
        'fid_rsfl_rate1': '0',
        'fid_rsfl_rate2': '30',
    })
    rows = [r for r in (_row(o, 'fluctuation') for o in output) if r]
    return rows[:top_n]


def get_trading_value_rank(top_n: int = 15) -> list:
    """당일 거래대금 순위 (실전 도메인). 실패 시 예외 전파 — 호출부에서 처리."""
    output = _fetch_rank('/uapi/domestic-stock/v1/quotations/volume-rank', 'FHPST01710000', {
        'FID_COND_MRKT_DIV_CODE': 'J',
        'FID_COND_SCR_DIV_CODE': '20171',
        'FID_INPUT_ISCD': '0000',
        'FID_DIV_CLS_CODE': '0',
        'FID_BLNG_CLS_CODE': '3',           # 거래금액순
        'FID_TRGT_CLS_CODE': '111111111',
        'FID_TRGT_EXLS_CLS_CODE': '0000000000',
        'FID_INPUT_PRICE_1': '',
        'FID_INPUT_PRICE_2': '',
        'FID_VOL_CNT': '',
        'FID_INPUT_DATE_1': '',
    })
    rows = [r for r in (_row(o, 'trading_value') for o in output) if r]
    return rows[:top_n]


def get_intraday_leaders(top_n: int = 20) -> list:
    """당일 장초반 주도주 풀 — 상승률·거래대금 순위 합집합 (중복 시 상승률 출처 우선).
    한쪽 API가 실패해도 다른 쪽 결과로 진행. 둘 다 실패하면 빈 리스트."""
    pool, seen = [], set()
    errors = []
    for fetch in (get_fluctuation_rank, get_trading_value_rank):
        try:
            for r in fetch(top_n):
                if r['code'] in seen:
                    continue
                seen.add(r['code'])
                pool.append(r)
        except Exception as e:
            errors.append(f'{fetch.__name__}: {e}')
    if errors and pool:
        print(f'[섀도] 순위 조회 일부 실패: {errors}')
    if not pool and errors:
        raise Exception(' / '.join(errors))
    return pool[:top_n]

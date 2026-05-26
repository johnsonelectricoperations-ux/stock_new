# KOSPI 200 베이시스(선물가 - 현물지수) 수집 모듈 (임계값 튜닝용 데이터 축적)
import csv
import os
import requests
from datetime import datetime, timedelta
from kis_data import get_current_price

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://finance.naver.com/',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}



def _get_kospi200_spot() -> float | None:
    """KODEX 200(069500) 현재가 ÷ 100 으로 KOSPI 200 지수 포인트 근사값 계산.
    KODEX 200 가격 ≈ KOSPI200 포인트 × 100 관계 이용.
    """
    try:
        return round(get_current_price('069500')['price'] / 100, 2)
    except Exception:
        return None


def _get_vkospi() -> float | None:
    """KRX OpenAPI로 '코스피 200 변동성지수'(VKOSPI) 전일 종가 조회."""
    api_key = os.environ.get('KRX_API_KEY')
    if not api_key:
        return None
    try:
        # 최근 7일 내 가장 최신 거래일 데이터 탐색
        for days_back in range(1, 8):
            date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
            res = requests.post(
                'https://data-dbg.krx.co.kr/svc/apis/idx/drvprod_dd_trd',
                json={'basDd': date},
                headers={'AUTH_KEY': api_key, 'Content-Type': 'application/json'},
                timeout=10,
            )
            res.raise_for_status()
            items = res.json().get('OutBlock_1', [])
            for item in items:
                if '변동성지수' in item.get('IDX_NM', ''):
                    val = float(item['CLSPRC_IDX'].replace(',', ''))
                    return val if val > 0 else None
    except Exception:
        pass
    return None


def _get_kospi200_futures() -> float | None:
    """네이버 모바일 API로 KOSPI 200 선물 지수 조회."""
    url = 'https://m.stock.naver.com/api/index/FUT/basic'
    try:
        res = requests.get(url, headers=_HEADERS, timeout=10)
        res.raise_for_status()
        data = res.json()
        price_str = data.get('closePrice', '')
        val = float(price_str.replace(',', ''))
        return val if val > 50 else None
    except Exception:
        return None


def get_basis() -> dict | None:
    """
    KOSPI 200 베이시스 계산.
    - 선물 수집 성공: {spot, futures, basis, basis_pct}
    - 선물 수집 실패: {spot, futures=None, basis=None, basis_pct=None}
    - 현물도 실패: None
    basis > 0 → 콘탱고(정상), basis < 0 → 백워데이션(프로그램 매도 압력)
    """
    spot = _get_kospi200_spot()
    if spot is None:
        return None
    futures  = _get_kospi200_futures()
    vkospi   = _get_vkospi()
    if futures is not None:
        basis = round(futures - spot, 2)
        basis_pct = round(basis / spot * 100, 4)
    else:
        basis = basis_pct = None
    # 베이시스 기울기 (slope) — 전일 대비 변화량, Slope Momentum 임계값 결정용 데이터
    slope = None
    try:
        if basis is not None and os.path.exists('basis_log.csv'):
            with open('basis_log.csv', 'r', encoding='utf-8') as f:
                rows = list(csv.DictReader(f))
            prev_rows = [r for r in rows if r.get('basis')]
            if prev_rows:
                prev_basis = float(prev_rows[-1]['basis'])
                slope = round(basis - prev_basis, 4)
    except Exception:
        pass

    return {
        'spot': spot,
        'futures': futures,
        'basis': basis,
        'basis_pct': basis_pct,
        'basis_slope': slope,
        'vkospi': vkospi,   # 한국 변동성 지수 — 국면 판단 보조 (MA60 + 변동성 결합용)
    }

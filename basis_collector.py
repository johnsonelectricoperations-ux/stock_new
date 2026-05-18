# KOSPI 200 베이시스(선물가 - 현물지수) 수집 모듈 (임계값 튜닝용 데이터 축적)
import requests
from datetime import datetime, timedelta
from kis_data import get_current_price

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://finance.naver.com/',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}



def _get_kospi200_spot() -> float | None:
    """KODEX 200(069500) 현재가 × 10 으로 KOSPI 200 지수 근사값 계산."""
    try:
        return get_current_price('069500')['price'] * 10
    except Exception:
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
    futures = _get_kospi200_futures()
    if futures is not None:
        basis = round(futures - spot, 2)
        basis_pct = round(basis / spot * 100, 4)
    else:
        basis = basis_pct = None
    return {
        'spot': spot,
        'futures': futures,
        'basis': basis,
        'basis_pct': basis_pct,
    }

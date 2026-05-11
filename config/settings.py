# 환경변수 로드 및 전역 설정값을 관리하는 모듈
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

KIS_APP_KEY = os.getenv('KIS_APP_KEY')
KIS_APP_SECRET = os.getenv('KIS_APP_SECRET')
KIS_IS_MOCK = os.getenv('KIS_IS_MOCK', 'true').lower() == 'true'

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

KIS_BASE_URL = 'https://openapivts.koreainvestment.com:9443' if KIS_IS_MOCK else 'https://openapi.koreainvestment.com:9443'

# 계좌번호: 앞 8자리(CANO)와 뒤 2자리(ACNT_PRDT_CD) 분리
_account = os.getenv('KIS_ACCOUNT_NO', '').replace('-', '')
KIS_CANO = _account[:8]
KIS_ACNT_PRDT_CD = _account[8:] if len(_account) > 8 else os.getenv('KIS_ACNT_PRDT_CD', '01')

# 운용 설정
TOTAL_BUDGET = int(os.getenv('TOTAL_BUDGET', '10000000'))  # 운용 규모 (기본 1천만원)
MAX_STOCK_COUNT = int(os.getenv('MAX_STOCK_COUNT', '5'))    # 최대 보유 종목 수
STOP_LOSS_RATE = float(os.getenv('STOP_LOSS_RATE', '0.10')) # 손절 비율 (10%)
TRAIL_STOP_RATE = float(os.getenv('TRAIL_STOP_RATE', '0.10')) # 트레일링 스탑 비율 (10%)

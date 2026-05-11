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

_account = os.getenv('KIS_ACCOUNT_NO', '').replace('-', '')
KIS_CANO = _account[:8]
KIS_ACNT_PRDT_CD = _account[8:] if len(_account) > 8 else os.getenv('KIS_ACNT_PRDT_CD', '01')

# 운용 설정
TOTAL_BUDGET = int(os.getenv('TOTAL_BUDGET', '10000000'))
MAX_STOCK_COUNT = int(os.getenv('MAX_STOCK_COUNT', '6'))      # 테마당 2종목, 상위 3테마 = 최대 6종목
STOP_LOSS_RATE = float(os.getenv('STOP_LOSS_RATE', '0.10'))
TRAIL_STOP_RATE = float(os.getenv('TRAIL_STOP_RATE', '0.10'))

# 외국인 5일 누적 순매수 임계값 (백만원 단위, 0 = 순매수면 통과)
FOREIGN_BUY_THRESHOLD = int(os.getenv('FOREIGN_BUY_THRESHOLD', '0'))

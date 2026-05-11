# 자동매매 메인 루프 - 신호 생성, 주문 실행, 리스크 관리 통합
import csv
import os
import time
import schedule
import threading
from datetime import datetime
from kis_data import get_current_price
from kis_sector import get_leading_sector_signals
from kis_indicator import check_market_trend
from kis_order import buy_stock, sell_stock, calc_quantity
from telegram_bot import send_message, is_paused, build_app
from config.settings import STOP_LOSS_RATE, TRAIL_STOP_RATE, MAX_STOCK_COUNT, TOTAL_BUDGET
from performance import log_trade

# 보유 종목 저장소: {code: {name, sector, qty, entry_price, entry_date, peak_price}}
positions = {}

# 실현 손익 누적 (복리 재투자 기준금 계산용)
realized_pnl = 0


def _load_realized_pnl() -> int:
    """서버 재시작 시 trades.csv에서 실현 손익 합계 복원."""
    if not os.path.exists('trades.csv'):
        return 0
    total = 0
    with open('trades.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                total += int(row['profit'])
            except Exception:
                pass
    return total


def add_realized_pnl(amount: int):
    global realized_pnl
    realized_pnl += amount


def get_effective_budget() -> int:
    """실현 손익 반영한 실제 운용 기준금."""
    return max(TOTAL_BUDGET + realized_pnl, 1_000_000)  # 최소 100만원 보장


KOREAN_HOLIDAYS_2026 = {
    '20260101', '20260127', '20260128', '20260129', '20260130',
    '20260301', '20260505', '20260506', '20260525',
    '20260606', '20260815', '20260930', '20261001', '20261002',
    '20261003', '20261009', '20261225'
}

def is_trading_day():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    if now.strftime('%Y%m%d') in KOREAN_HOLIDAYS_2026:
        return False
    return True

def is_market_open():
    if not is_trading_day():
        return False
    now = datetime.now()
    market_open  = now.replace(hour=9,  minute=0,  second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close

def morning_routine():
    if not is_trading_day():
        return
    if is_paused():
        return

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    send_message(f'[장 시작] {now}\n테마 수집 및 신호 분석 시작합니다...')

    # 코스피 MA60 필터 — 하락장이면 매수 중단
    if not check_market_trend():
        send_message('⚠️ KOSPI 하락장 감지 (MA60 하향). 오늘 매수를 보류합니다.')
        return

    # 09:20 이후 주문 (장 초반 변동성 진정 후 진입)
    now_time = datetime.now()
    target = now_time.replace(hour=9, minute=20, second=0, microsecond=0)
    wait_seconds = max(0, (target - now_time).seconds)
    if wait_seconds > 0:
        time.sleep(wait_seconds)

    try:
        signals = get_leading_sector_signals(top_sectors=3, max_stocks=MAX_STOCK_COUNT, save_log=True)
    except Exception as e:
        send_message(f'⚠️ 신호 생성 실패: {e}')
        return

    if not signals:
        send_message('오늘 매수 신호 없음. 매매 보류.')
        return

    budget = get_effective_budget()
    msg_lines = [
        f'확인 매수 신호 {len(signals)}종목',
        f'운용 기준금: {budget:,}원 (초기 {TOTAL_BUDGET:,}원 + 실현손익 {realized_pnl:+,}원)'
    ]

    for s in signals:
        code = s['code']
        if code in positions:
            continue
        try:
            info = get_current_price(code)
            qty = calc_quantity(info['price'], len(signals), effective_budget=budget)
            buy_stock(code, qty)
            positions[code] = {
                'name': s['name'],
                'sector': s['sector'],
                'qty': qty,
                'entry_price': info['price'],
                'entry_date': datetime.now().strftime('%Y-%m-%d'),
                'peak_price': info['price']
            }
            msg_lines.append(
                f"[매수 체결] {s['name']} {info['price']:,}원 × {qty}주"
                f"\n테마: {s['sector']} | 모멘텀: {s['momentum']:+.2f}%"
            )
            time.sleep(0.3)
        except Exception as e:
            msg_lines.append(f"⚠️ {s['name']} 매수 실패: {e}")

    send_message('\n\n'.join(msg_lines))

def monitor_positions():
    if not is_market_open():
        return
    if is_paused() or not positions:
        return

    for code in list(positions.keys()):
        try:
            pos = positions[code]
            info = get_current_price(code)
            price = info['price']

            if price > pos['peak_price']:
                positions[code]['peak_price'] = price

            entry = pos['entry_price']
            peak  = pos['peak_price']
            stop_loss_price  = entry * (1 - STOP_LOSS_RATE)
            trail_stop_price = peak  * (1 - TRAIL_STOP_RATE)
            sell_price = max(stop_loss_price, trail_stop_price)

            if price <= sell_price:
                sell_stock(code, pos['qty'])
                profit = (price - entry) * pos['qty']
                profit_rate = (price - entry) / entry * 100
                reason = '손절' if price <= stop_loss_price else '트레일링 스탑'
                add_realized_pnl(profit)
                log_trade(
                    code=code, name=pos['name'],
                    sector=pos.get('sector', ''),
                    entry_date=pos.get('entry_date', datetime.now().strftime('%Y-%m-%d')),
                    entry_price=entry, exit_price=price,
                    qty=pos['qty'], reason=reason,
                )
                send_message(
                    f'[매도 체결] {pos["name"]} {price:,}원\n'
                    f'사유: {reason} | 수익률: {profit_rate:+.2f}% ({profit:+,}원)\n'
                    f'누적 실현손익: {realized_pnl:+,}원'
                )
                del positions[code]

            time.sleep(0.3)
        except Exception:
            pass

def daily_report():
    if not is_trading_day():
        return

    lines = [f'일일 리포트 (누적 실현손익: {realized_pnl:+,}원)']
    total_unrealized = 0

    for code, pos in positions.items():
        try:
            info = get_current_price(code)
            profit = (info['price'] - pos['entry_price']) * pos['qty']
            rate   = (info['price'] - pos['entry_price']) / pos['entry_price'] * 100
            total_unrealized += profit
            lines.append(f"{pos['name']}: {rate:+.2f}% ({profit:+,}원)")
        except Exception:
            pass

    if not positions:
        lines.append('보유 종목 없음.')
    else:
        lines.append(f'\n미실현 수익 합계: {total_unrealized:+,}원')

    lines.append(f'운용 기준금: {get_effective_budget():,}원')
    send_message('\n'.join(lines))

def run_scheduler():
    schedule.every().day.at('08:00').do(morning_routine)
    schedule.every(5).minutes.do(monitor_positions)
    schedule.every().day.at('15:35').do(daily_report)
    while True:
        schedule.run_pending()
        time.sleep(30)

def main():
    global realized_pnl
    realized_pnl = _load_realized_pnl()
    send_message(
        f'자동매매 시스템 시작. /help 로 명령어 확인.\n'
        f'누적 실현손익: {realized_pnl:+,}원 | 운용 기준금: {get_effective_budget():,}원'
    )

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    print('시스템 동작 중... Ctrl+C 로 종료')
    app = build_app()
    app.run_polling(stop_signals=None)

if __name__ == '__main__':
    main()

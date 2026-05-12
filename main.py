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
from config.settings import (
    STOP_LOSS_RATE, TRAIL_STOP_RATE, MAX_STOCK_COUNT, TOTAL_BUDGET,
    BREAK_EVEN_TRIGGER, BREAK_EVEN_FLOOR,
    PARTIAL_SELL_TRIGGER, TIME_STOP_DAYS, TIME_STOP_MIN_RATE,
)
from performance import log_trade
from error_monitor import setup_logging, log_error, log_info, log_warning

# 보유 종목 저장소: {code: {name, sector, qty, entry_price, entry_date, peak_price}}
positions = {}

# 실현 손익 누적 (복리 재투자 기준금 계산용)
realized_pnl = 0

# 스케줄러 마지막 정상 동작 시각 (헬스체크용)
_last_heartbeat: float = 0.0


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


def get_invested_capital() -> int:
    """현재 보유 포지션에 묶인 투자금."""
    return sum(pos['entry_price'] * pos['qty'] for pos in positions.values())


def get_available_cash() -> int:
    """실제 매수 가능한 가용 현금 (보유 포지션 투자금 차감)."""
    return max(0, TOTAL_BUDGET + realized_pnl - get_invested_capital())


def get_effective_budget() -> int:
    """총 운용 자산 (초기자금 + 실현손익)."""
    return max(TOTAL_BUDGET + realized_pnl, 1_000_000)


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
    log_info('morning_routine', f'장 시작 루틴 실행 {now}')

    # 코스피 MA60 필터 — 하락장이면 매수 중단
    try:
        if not check_market_trend():
            send_message('⚠️ KOSPI 하락장 감지 (MA60 하향). 오늘 매수를 보류합니다.')
            log_warning('morning_routine', 'KOSPI 하락장 감지 — 매수 보류')
            return
    except Exception as e:
        log_error('morning_routine:check_market_trend', e)
        send_message(f'⚠️ 시장 추세 확인 실패: {e}. 매수 진행합니다.')

    # 09:20 이후 주문 (장 초반 변동성 진정 후 진입)
    now_time = datetime.now()
    target = now_time.replace(hour=9, minute=10, second=0, microsecond=0)
    wait_seconds = max(0, (target - now_time).seconds)
    if wait_seconds > 0:
        time.sleep(wait_seconds)

    # 신규 매수 가능 슬롯 및 가용 현금 계산
    new_slots = MAX_STOCK_COUNT - len(positions)
    available_cash = get_available_cash()

    if new_slots <= 0:
        send_message(f'포지션이 가득 찼습니다 ({len(positions)}/{MAX_STOCK_COUNT}종목). 매수 보류.')
        return
    if available_cash < 500_000:
        send_message(f'가용 현금 부족 ({available_cash:,}원). 매수 보류.')
        return

    try:
        signals = get_leading_sector_signals(top_sectors=3, max_stocks=new_slots, save_log=True)
    except Exception as e:
        log_error('morning_routine:get_leading_sector_signals', e, critical=True)
        send_message(f'⚠️ 신호 생성 실패: {e}')
        return

    # 이미 보유 중인 종목 제외
    signals = [s for s in signals if s['code'] not in positions]

    if not signals:
        send_message('오늘 매수 신호 없음. 매매 보류.')
        return

    per_stock_budget = available_cash // len(signals)
    msg_lines = [
        f'확인 매수 신호 {len(signals)}종목',
        f'가용현금: {available_cash:,}원 | 종목당: {per_stock_budget:,}원',
        f'(총자산: {get_effective_budget():,}원 | 투자중: {get_invested_capital():,}원)'
    ]

    for s in signals:
        code = s['code']
        try:
            info = get_current_price(code)
            qty = calc_quantity(info['price'], len(signals), effective_budget=available_cash)
            buy_stock(code, qty)
            positions[code] = {
                'name': s['name'],
                'sector': s['sector'],
                'qty': qty,
                'entry_price': info['price'],
                'entry_date': datetime.now().strftime('%Y-%m-%d'),
                'peak_price': info['price'],
                'break_even_set': False,
                'floor_price': 0,
                'partial_sold': False,
            }
            log_info('morning_routine', f"매수 체결: {s['name']}({code}) {info['price']:,}원 × {qty}주")
            msg_lines.append(
                f"[매수 체결] {s['name']} {info['price']:,}원 × {qty}주"
                f"\n테마: {s['sector']} | 모멘텀: {s['momentum']:+.2f}%"
            )
            time.sleep(0.3)
        except Exception as e:
            log_error(f'morning_routine:buy_stock:{code}', e, critical=True)
            msg_lines.append(f"⚠️ {s['name']} 매수 실패: {e}")

    send_message('\n\n'.join(msg_lines))

def _trading_days_held(entry_date_str: str) -> int:
    """진입일 기준 경과 거래일 수 (달력일 × 5/7 근사)."""
    try:
        entry = datetime.strptime(entry_date_str, '%Y-%m-%d')
        delta = (datetime.now() - entry).days
        return max(0, int(delta * 5 / 7))
    except Exception:
        return 0


def _do_sell(code: str, qty: int, price: int, reason: str):
    """매도 실행 + PnL/로그/텔레그램 처리."""
    pos = positions[code]
    entry = pos['entry_price']
    profit = (price - entry) * qty
    profit_rate = (price - entry) / entry * 100
    sell_stock(code, qty)
    add_realized_pnl(profit)
    log_trade(
        code=code, name=pos['name'],
        sector=pos.get('sector', ''),
        entry_date=pos.get('entry_date', datetime.now().strftime('%Y-%m-%d')),
        entry_price=entry, exit_price=price,
        qty=qty, reason=reason,
    )
    log_info('sell', f"{pos['name']}({code}) {reason} {price:,}원 수익률 {profit_rate:+.2f}%")
    send_message(
        f'[매도 체결] {pos["name"]} {price:,}원\n'
        f'사유: {reason} | 수익률: {profit_rate:+.2f}% ({profit:+,}원)\n'
        f'누적 실현손익: {realized_pnl:+,}원'
    )


def monitor_positions():
    global _last_heartbeat
    if not is_market_open():
        return
    if is_paused() or not positions:
        _last_heartbeat = time.time()
        return

    for code in list(positions.keys()):
        try:
            pos = positions[code]
            info = get_current_price(code)
            price = info['price']
            entry = pos['entry_price']
            rate = (price - entry) / entry

            # 고점 갱신
            if price > pos['peak_price']:
                positions[code]['peak_price'] = price
            peak = positions[code]['peak_price']

            # ── 단계 2: +20% 달성 → 50% 부분 익절 (1회)
            if not pos.get('partial_sold') and rate >= PARTIAL_SELL_TRIGGER:
                half_qty = max(1, pos['qty'] // 2)
                _do_sell(code, half_qty, price, f'부분익절(+{rate*100:.1f}%)')
                positions[code]['qty'] -= half_qty
                positions[code]['partial_sold'] = True
                positions[code]['peak_price'] = price  # 잔량 트레일링 기준 재설정
                if positions[code]['qty'] <= 0:
                    del positions[code]
                time.sleep(0.3)
                continue

            # ── 단계 1: +7% 달성 → 본전 보호 스탑 발동
            if not pos.get('break_even_set') and rate >= BREAK_EVEN_TRIGGER:
                positions[code]['break_even_set'] = True
                positions[code]['floor_price'] = entry * (1 + BREAK_EVEN_FLOOR)

            # ── 매도 트리거 계산
            stop_loss_price  = entry * (1 - STOP_LOSS_RATE)
            trail_stop_price = peak  * (1 - TRAIL_STOP_RATE)
            floor_price      = pos.get('floor_price', 0)
            sell_trigger     = max(stop_loss_price, trail_stop_price, floor_price)

            # ── 단계 4: 시간 손절 (20거래일 경과 + 수익 <+5%)
            days_held = _trading_days_held(pos.get('entry_date', ''))
            time_stop = days_held >= TIME_STOP_DAYS and rate < TIME_STOP_MIN_RATE

            if price <= sell_trigger or time_stop:
                if time_stop and price > sell_trigger:
                    reason = f'시간손절({days_held}거래일, {rate*100:+.1f}%)'
                elif price <= stop_loss_price:
                    reason = '손절'
                elif floor_price and price <= floor_price:
                    reason = '본전보호'
                else:
                    reason = '트레일링스탑'
                _do_sell(code, pos['qty'], price, reason)
                del positions[code]

            time.sleep(0.3)
        except Exception as e:
            log_error(f'monitor_positions:{code}', e)

    _last_heartbeat = time.time()


def daily_report():
    if not is_trading_day():
        return

    total_unrealized = 0
    lines = [f'장 마감 결산 ({datetime.now().strftime("%Y-%m-%d")})']

    # 보유 종목 현황
    if positions:
        lines.append('\n[보유 종목]')
        for code, pos in positions.items():
            try:
                info = get_current_price(code)
                profit = (info['price'] - pos['entry_price']) * pos['qty']
                rate   = (info['price'] - pos['entry_price']) / pos['entry_price'] * 100
                total_unrealized += profit
                lines.append(f"  {pos['name']}: {rate:+.2f}% ({profit:+,}원)")
            except Exception as e:
                log_error(f'daily_report:get_current_price:{code}', e)
                lines.append(f"  {pos['name']}: 조회 실패")
        lines.append(f'  미실현 손익 합계: {total_unrealized:+,}원')
    else:
        lines.append('\n보유 종목 없음.')

    # 자산 현황
    invested = get_invested_capital()
    available = get_available_cash()
    total_asset = get_effective_budget()
    lines.append(
        f'\n[자산 현황]\n'
        f'  총 운용자산: {total_asset:,}원\n'
        f'  투자 중: {invested:,}원\n'
        f'  가용 현금: {available:,}원\n'
        f'  누적 실현손익: {realized_pnl:+,}원'
    )

    # 내일 매수 계획
    new_slots = MAX_STOCK_COUNT - len(positions)
    if new_slots > 0 and available >= 500_000:
        per_stock = available // new_slots
        lines.append(
            f'\n[내일 매수 계획]\n'
            f'  신규 매수 가능: {new_slots}종목\n'
            f'  종목당 투자금: {per_stock:,}원\n'
            f'  (가용현금 {available:,}원 ÷ {new_slots}종목)'
        )
    elif new_slots <= 0:
        lines.append(f'\n[내일 매수 계획]\n  포지션 가득 ({MAX_STOCK_COUNT}/{MAX_STOCK_COUNT}). 신규 매수 없음.')
    else:
        lines.append(f'\n[내일 매수 계획]\n  가용 현금 부족 ({available:,}원). 신규 매수 보류.')

    send_message('\n'.join(lines))
    log_info('daily_report', '장 마감 결산 전송 완료')


def _heartbeat_watchdog():
    """스케줄러 스레드가 멈췄는지 30분 주기로 감시 (장 중에만 동작)."""
    WATCHDOG_TIMEOUT = 1800  # 30분
    while True:
        time.sleep(WATCHDOG_TIMEOUT)
        if not is_market_open():
            continue  # 장 외 시간에는 검사하지 않음
        elapsed = time.time() - _last_heartbeat
        if elapsed > WATCHDOG_TIMEOUT:
            log_error('heartbeat_watchdog', critical=True,
                      exc=Exception(f'스케줄러 응답 없음 — {int(elapsed//60)}분 경과'))


def run_scheduler():
    global _last_heartbeat
    _last_heartbeat = time.time()
    schedule.every().day.at('08:00').do(morning_routine)
    schedule.every(5).minutes.do(monitor_positions)
    schedule.every().day.at('15:35').do(daily_report)
    while True:
        try:
            schedule.run_pending()
            _last_heartbeat = time.time()  # 스케줄러 정상 동작 확인
        except Exception as e:
            log_error('run_scheduler', e, critical=True)
        time.sleep(30)

def main():
    global realized_pnl
    setup_logging()
    realized_pnl = _load_realized_pnl()
    log_info('main', f'시스템 시작. 실현손익={realized_pnl:+,}원')
    send_message(
        f'자동매매 시스템 시작. /help 로 명령어 확인.\n'
        f'누적 실현손익: {realized_pnl:+,}원 | 운용 기준금: {get_effective_budget():,}원'
    )

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    watchdog_thread = threading.Thread(target=_heartbeat_watchdog, daemon=True)
    watchdog_thread.start()

    print('시스템 동작 중... Ctrl+C 로 종료')
    app = build_app()
    app.run_polling(stop_signals=None)

if __name__ == '__main__':
    main()

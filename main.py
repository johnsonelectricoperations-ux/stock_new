# 자동매매 메인 루프 - 신호 생성, 주문 실행, 리스크 관리 통합
import time
import schedule
import threading
from datetime import datetime
from kis_data import get_current_price
from kis_sector import get_leading_sector_signals
from kis_order import buy_stock, sell_stock, calc_quantity
from telegram_bot import send_message, is_paused, run_bot
from config.settings import STOP_LOSS_RATE, TRAIL_STOP_RATE, MAX_STOCK_COUNT

# 보유 종목 저장소: {code: {name, qty, entry_price, peak_price}}
positions = {}

def morning_routine():
    if is_paused():
        return

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    send_message(f'[장 시작] {now}\n신호 분석 시작합니다...')

    try:
        signals = get_leading_sector_signals(top_sectors=2)
    except Exception as e:
        send_message(f'⚠️ 신호 생성 실패: {e}')
        return

    if not signals:
        send_message('오늘 매수 신호 없음. 매매 보류.')
        return

    # 종목 수 제한
    signals = signals[:MAX_STOCK_COUNT]
    msg_lines = [f'확인 매수 신호 {len(signals)}종목']

    for s in signals:
        code = s['code']
        if code in positions:
            continue  # 이미 보유 중
        try:
            info = get_current_price(code)
            qty = calc_quantity(info['price'], len(signals))
            buy_stock(code, qty)
            positions[code] = {
                'name': s['name'],
                'qty': qty,
                'entry_price': info['price'],
                'peak_price': info['price']
            }
            msg_lines.append(
                f"[매수 체결] {s['name']} {info['price']:,}원 × {qty}주"
                f"\n섯터: {s['sector']} | 모멘텀: {s['momentum']:+.2f}%"
            )
            time.sleep(0.3)
        except Exception as e:
            msg_lines.append(f"⚠️ {s['name']} 매수 실패: {e}")

    send_message('\n\n'.join(msg_lines))

def monitor_positions():
    if is_paused() or not positions:
        return

    for code in list(positions.keys()):
        try:
            pos = positions[code]
            info = get_current_price(code)
            price = info['price']

            # 고점 갱신
            if price > pos['peak_price']:
                positions[code]['peak_price'] = price

            entry = pos['entry_price']
            peak = pos['peak_price']
            stop_loss_price = entry * (1 - STOP_LOSS_RATE)
            trail_stop_price = peak * (1 - TRAIL_STOP_RATE)
            sell_price = max(stop_loss_price, trail_stop_price)

            if price <= sell_price:
                sell_stock(code, pos['qty'])
                profit_rate = (price - entry) / entry * 100
                reason = '손절' if price <= stop_loss_price else '트레일링 스탑'
                send_message(
                    f'[매도 체결] {pos["name"]} {price:,}원\n'
                    f'사유: {reason} | 수익률: {profit_rate:+.2f}%'
                )
                del positions[code]

            time.sleep(0.3)
        except Exception as e:
            pass

def daily_report():
    if not positions:
        send_message('장 종료. 보유 종목 없음.')
        return

    lines = ['일일 리포트']
    total_profit = 0

    for code, pos in positions.items():
        try:
            info = get_current_price(code)
            profit = (info['price'] - pos['entry_price']) * pos['qty']
            rate = (info['price'] - pos['entry_price']) / pos['entry_price'] * 100
            total_profit += profit
            lines.append(
                f"{pos['name']}: {rate:+.2f}% ({profit:+,}원)"
            )
        except Exception:
            pass

    lines.append(f'\n중 수익 합계: {total_profit:+,}원')
    send_message('\n'.join(lines))

def main():
    send_message('자동매매 시스템 시작. /help 로 명령어 확인.')

    # 스케줄 등록
    schedule.every().day.at('08:30').do(morning_routine)
    schedule.every(5).minutes.do(monitor_positions)  # 5분마다 보유 종목 모니터링
    schedule.every().day.at('15:35').do(daily_report)

    # 텔레그램 봇을 별도 스레드로 실행
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    print('시스템 동작 중... Ctrl+C 로 종료')
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == '__main__':
    main()

# 텔레그램 봇 알림 및 명령어 처리 모듈
import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config.settings import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

logging.basicConfig(level=logging.WARNING)

_app = None
_trading_paused = False

def _check_auth(update: Update) -> bool:
    return str(update.effective_chat.id) == str(TELEGRAM_CHAT_ID)

async def _send(text: str):
    if _app:
        await _app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

def send_message(text: str):
    asyncio.get_event_loop().run_until_complete(_send(text))

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update):
        return
    await update.message.reply_text('안녕하세요. 주식 자동매매 봇입니다.\n/help 으로 명령어 목록을 확인하세요.')

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update):
        return
    msg = (
        '확인 명령어 목록\n'
        '/status — 보유 종목 + 수익률\n'
        '/balance — 잔고 조회\n'
        '/signal — 오늘 매수 신호 종목\n'
        '\n수동 매매\n'
        '/buy 종목코드 수량\n'
        '/sell 종목코드 수량\n'
        '/sellall 종목코드\n'
        '\n시스템 제어\n'
        '/pause — 자동매매 일시중지\n'
        '/resume — 자동매매 재개\n'
        '/stop — 시스템 종료'
    )
    await update.message.reply_text(msg)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update):
        return
    await update.message.reply_text('현재 보유 종목 조회 기능은 주문 실행 모듈 연동 후 활성화됩니다.')

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update):
        return
    await update.message.reply_text('잔고 조회 기능은 주문 실행 모듈 연동 후 활성화됩니다.')

async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update):
        return
    await update.message.reply_text('신호 조회 기능은 신호 생성 모듈 연동 후 활성화됩니다.')

async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update):
        return
    if len(context.args) != 2:
        await update.message.reply_text('사용법: /buy 종목코드 수량\n예: /buy 005930 10')
        return
    await update.message.reply_text(f'{context.args[0]} {context.args[1]}주 수동 매수 기능은 주문 실행 모듈 연동 후 활성화됩니다.')

async def cmd_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update):
        return
    if len(context.args) != 2:
        await update.message.reply_text('사용법: /sell 종목코드 수량\n예: /sell 005930 10')
        return
    await update.message.reply_text(f'{context.args[0]} {context.args[1]}주 수동 매도 기능은 주문 실행 모듈 연동 후 활성화됩니다.')

async def cmd_sellall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update):
        return
    if len(context.args) != 1:
        await update.message.reply_text('사용법: /sellall 종목코드\n예: /sellall 005930')
        return
    await update.message.reply_text(f'{context.args[0]} 전량매도 기능은 주문 실행 모듈 연동 후 활성화됩니다.')

async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _trading_paused
    if not _check_auth(update):
        return
    _trading_paused = True
    await update.message.reply_text('자동매매가 일시중지되었습니다.')

async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _trading_paused
    if not _check_auth(update):
        return
    _trading_paused = False
    await update.message.reply_text('자동매매를 재개합니다.')

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update):
        return
    await update.message.reply_text('시스템을 종료합니다.')
    import os, signal
    os.kill(os.getpid(), signal.SIGTERM)

def is_paused():
    return _trading_paused

def run_bot():
    global _app
    _app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    _app.add_handler(CommandHandler('start', cmd_start))
    _app.add_handler(CommandHandler('help', cmd_help))
    _app.add_handler(CommandHandler('status', cmd_status))
    _app.add_handler(CommandHandler('balance', cmd_balance))
    _app.add_handler(CommandHandler('signal', cmd_signal))
    _app.add_handler(CommandHandler('buy', cmd_buy))
    _app.add_handler(CommandHandler('sell', cmd_sell))
    _app.add_handler(CommandHandler('sellall', cmd_sellall))
    _app.add_handler(CommandHandler('pause', cmd_pause))
    _app.add_handler(CommandHandler('resume', cmd_resume))
    _app.add_handler(CommandHandler('stop', cmd_stop))
    _app.run_polling()

if __name__ == '__main__':
    run_bot()

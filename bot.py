import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time
import os
from datetime import datetime
from dotenv import load_dotenv

# Memuat variabel rahasia dari file .env
load_dotenv()

# ==========================================
# 1. VALIDASI KEAMANAN (.env)
# ==========================================
API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

if not API_KEY or not SECRET_KEY or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ ERROR KRONIS: File .env belum diisi dengan benar. Bot tidak bisa berjalan.")
    exit()

# ==========================================
# 2. PENGATURAN STRATEGI (Parameter Kuantitatif)
# ==========================================
SYMBOL = 'BTC/USDT'     # Koin yang akan ditradingkan
TIMEFRAME = '15m'       # Timeframe analisis (15 Menit)
LEVERAGE = 20           # Daya ungkit / Leverage
MARGIN_USDT = 10        # Risiko Modal per transaksi ($10)
RR_RATIO = 2            # Risk to Reward (TP 2%, SL 1%)

EMA_FAST = 13
EMA_SLOW = 21
RSI_LENGTH = 14
RSI_OVERSOLD = 35       # Titik beli saat tren naik
RSI_OVERBOUGHT = 65     # Titik jual saat tren turun

# ==========================================
# 3. INISIALISASI KONEKSI (Binance Testnet)
# ==========================================
try:
    exchange = ccxt.binance({
        'apiKey': API_KEY,
        'secret': SECRET_KEY,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    exchange.set_sandbox_mode(True) # MENGAKTIFKAN TESTNET
    exchange.load_markets() # Verifikasi koneksi awal
except Exception as e:
    print(f"❌ ERROR: Gagal terhubung ke Binance Testnet. Cek API Key. Detail: {e}")
    exit()

# ==========================================
# 4. FUNGSI PENDUKUNG (Telegram & Kalkulasi)
# ==========================================
def send_telegram(message):
    """Mengirim log dan notifikasi ke Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
    try:
        requests.post(url, data=payload, timeout=5)
    except:
        pass # Abaikan jika Telegram sedang error agar bot tidak crash

def fetch_and_calculate_indicators():
    """Mengambil data OHLCV terbaru dan menghitung EMA + RSI"""
    try:
        bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=100)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Kalkulasi Indikator menggunakan pandas_ta
        df['ema_fast'] = ta.ema(df['close'], length=EMA_FAST)
        df['ema_slow'] = ta.ema(df['close'], length=EMA_SLOW)
        df['rsi'] = ta.rsi(df['close'], length=RSI_LENGTH)
        return df
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Gagal fetch data dari server: {e}")
        return None

def execute_trade(side, current_price):
    """Fungsi Barbar: Kirim order ke Binance beserta SL & TP permanen"""
    try:
        # Atur Leverage (Abaikan error jika sudah diatur sebelumnya)
        try:
            exchange.set_leverage(LEVERAGE, SYMBOL)
        except: pass 
        
        # Kalkulasi Quantity
        pos_size_usd = MARGIN_USDT * LEVERAGE
        amount = pos_size_usd / current_price
        amount = float(exchange.amount_to_precision(SYMBOL, amount))
        
        # Kalkulasi Harga SL dan TP (RR 1:2)
        if side == 'buy':
            sl_price = current_price * 0.99  # Minus 1%
            tp_price = current_price * 1.02  # Plus 2%
        else: # Sell (Short)
            sl_price = current_price * 1.01
            tp_price = current_price * 0.98

        sl_price = float(exchange.price_to_precision(SYMBOL, sl_price))
        tp_price = float(exchange.price_to_precision(SYMBOL, tp_price))

        print("\n⏳ Mengirim instruksi ke Binance...")
        
        # 1. BUKA POSISI (Market Order)
        exchange.create_market_order(SYMBOL, side, amount)
        
        # 2. PASANG TAKE PROFIT (Limit Order / Reduce Only)
        exchange.create_order(SYMBOL, 'TAKE_PROFIT_MARKET', 'sell' if side == 'buy' else 'buy', amount, tp_price, {'stopPrice': tp_price, 'reduceOnly': True})
        
        # 3. PASANG STOP LOSS (Market Order / Reduce Only)
        exchange.create_order(SYMBOL, 'STOP_MARKET', 'sell' if side == 'buy' else 'buy', amount, sl_price, {'stopPrice': sl_price, 'reduceOnly': True})
        
        # Notifikasi Sukses
        msg = (f"🟢 <b>ENTRY {side.upper()} EXECUTED</b>\n\n"
               f"🔸 <b>Pair:</b> {SYMBOL}\n"
               f"🔸 <b>Harga:</b> ${current_price}\n"
               f"🔸 <b>Margin:</b> ${MARGIN_USDT} (Lev {LEVERAGE}x)\n"
               f"🛑 <b>SL (1%):</b> ${sl_price}\n"
               f"✅ <b>TP (2%):</b> ${tp_price}\n"
               f"🕒 {datetime.now().strftime('%H:%M:%S WIB')}")
        send_telegram(msg)
        print(f"✅ Trade sukses dibuka! Arah: {side.upper()} di {current_price}")
        return True
        
    except Exception as e:
        err_msg = f"❌ Gagal Eksekusi: {str(e)[:150]}" # Batasi panjang error
        print(err_msg)
        send_telegram(f"🚨 <b>ERROR EKSEKUSI</b>\n{err_msg}")
        return False

# ==========================================
# 5. LOOP UTAMA (MESIN PEMINDAI)
# ==========================================
def main():
    print("=" * 50)
    print("🤖 BOT KUANTITATIF (LITE VERSION) JALAN")
    print(f"Pair: {SYMBOL} | Margin: ${MARGIN_USDT} | Lev: {LEVERAGE}x")
    print("=" * 50)
    send_telegram(f"🤖 Bot Binance Testnet aktif memantau <b>{SYMBOL}</b>.")

    in_position = False

    while True:
        try:
            # Skenario 1: Bot tidak punya posisi, mari memindai pasar
            if not in_position:
                df = fetch_and_calculate_indicators()
                
                if df is not None and len(df) > EMA_SLOW:
                    # Selalu gunakan bar SEBELUM terakhir untuk konfirmasi (menghindari repainting)
                    completed_bar = df.iloc[-2]
                    live_bar = df.iloc[-1]
                    
                    c_price = live_bar['close']
                    ema13 = completed_bar['ema_fast']
                    ema21 = completed_bar['ema_slow']
                    rsi = completed_bar['rsi']
                    
                    # Tampilkan Heartbeat di terminal agar tahu bot tidak hang
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {SYMBOL} | Harga: {c_price:.2f} | EMA(13,21): {ema13:.0f}/{ema21:.0f} | RSI: {rsi:.1f}", end='\r')

                    # -- LOGIKA ALGORITMA --
                    # Sinyal BUY: Trend Naik (EMA13 > EMA21) & Koreksi Oversold (RSI < 35)
                    if ema13 > ema21 and rsi < RSI_OVERSOLD:
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🚀 Sinyal LONG valid! RSI: {rsi:.1f}")
                        if execute_trade('buy', c_price):
                            in_position = True
                            
                    # Sinyal SELL: Trend Turun (EMA13 < EMA21) & Rebound Overbought (RSI > 65)
                    elif ema13 < ema21 and rsi > RSI_OVERBOUGHT:
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ☄️ Sinyal SHORT valid! RSI: {rsi:.1f}")
                        if execute_trade('sell', c_price):
                            in_position = True

            # Skenario 2: Bot sedang dalam posisi, cek apakah sudah mengenai TP atau SL
            else:
                positions = exchange.fetch_positions([SYMBOL])
                # Filter posisi yang memiliki "positionAmt" bukan nol
                active_pos = [p for p in positions if float(p['info']['positionAmt']) != 0]
                
                if len(active_pos) == 0:
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 💵 Posisi selesai! Hit TP/SL.")
                    send_telegram(f"💵 <b>POSISI SELESAI</b>\nTarget TP atau SL untuk {SYMBOL} telah tersentuh. Bot kembali memindai pasar.")
                    in_position = False # Reset status
                else:
                    # Posisi masih floating
                    unrealized_pnl = float(active_pos[0]['info']['unRealizedProfit'])
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Menunggu TP/SL tersentuh... | Floating PnL: ${unrealized_pnl:.2f}    ", end='\r')

            time.sleep(15) # Delay 15 detik sebelum pengecekan berikutnya

        except KeyboardInterrupt:
            print("\nBot dihentikan oleh pengguna.")
            break
        except Exception as e:
            print(f"\nTerjadi error tak terduga: {e}")
            time.sleep(60) # Beri jeda 1 menit jika koneksi kacau

if __name__ == "__main__":
    main()
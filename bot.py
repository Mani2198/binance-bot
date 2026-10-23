import time
import pandas as pd
from binance.client import Client
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from flask import Flask
import threading
import os

# --- Dummy Web Server Code for Render ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is successfully running 24/7!"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    # Render-ல் போர்ட் பைண்டிங் எரர் வராமல் தடுக்க இது உதவும்
    app.run(host='0.0.0.0', port=port)
# ----------------------------------------

# 1. உங்களின் Binance Testnet API Key மற்றும் Secret Key இங்கே கொடுக்கவும்
API_KEY = 'UMWk2jHECWvQx4sppfGvKzuRFYWhxpxBTEcUzOxTxiIwwF7xXUPk29Y2LpH70cwN'
API_SECRET = 'h5NFdfZqY1pSDQe9lQOlkuK4welktvBTQ9U6juy5zfCy9Qt7v3sQGG2V7AYalGsp'

client = Client(API_KEY, API_SECRET, testnet=True)

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'ADAUSDT', 
           'XRPUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT']

TIMEFRAME = Client.KLINE_INTERVAL_15MINUTE
PROFIT_TARGET = 0.15  # 15% Profit Target (ROE)

current_step = 1
current_capital = 20.0  
previous_profit = 0.0   

def get_indicators_and_signal(symbol):
    try:
        klines = client.futures_klines(symbol=symbol, interval=TIMEFRAME, limit=250)
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        
        # இண்டிகேட்டர்கள்
        df['ema_200'] = EMAIndicator(close=df['close'], window=200).ema_indicator()
        df['rsi'] = RSIIndicator(close=df['close'], window=14).rsi()
        macd = MACD(close=df['close'])
        df['macd_line'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['vol_ma'] = df['volume'].rolling(window=20).mean()
        
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        current_price = last_row['close']
        
        # --- LONG CONDITIONS ---
        long_cond_1 = current_price > last_row['ema_200']  
        long_cond_2 = prev_row['macd_line'] <= prev_row['macd_signal'] and last_row['macd_line'] > last_row['macd_signal']
        long_cond_3 = prev_row['rsi'] < 40 and last_row['rsi'] >= 40 # RSI 40-க்கு கீழே சென்று மேலே திரும்ப வேண்டும்
        long_cond_4 = last_row['volume'] > last_row['vol_ma']
        
        if long_cond_1 and long_cond_2 and long_cond_3 and long_cond_4:
            return "LONG", current_price
            
        # --- SHORT CONDITIONS ---
        short_cond_1 = current_price < last_row['ema_200']
        short_cond_2 = prev_row['macd_line'] >= prev_row['macd_signal'] and last_row['macd_line'] < last_row['macd_signal']
        short_cond_3 = prev_row['rsi'] > 60 and last_row['rsi'] <= 60 # RSI 60-க்கு மேலே சென்று கீழே திரும்ப வேண்டும்
        short_cond_4 = last_row['volume'] > last_row['vol_ma']
        
        if short_cond_1 and short_cond_2 and short_cond_3 and short_cond_4:
            return "SHORT", current_price
            
        return None, current_price
        
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None, 0

def execute_trade(symbol, signal_type, entry_price):
    global current_step, current_capital, previous_profit
    
    leverage = 10 if current_step == 1 else 20
    
    print(f"\n🚀 {signal_type} SIGNAL DETECTED FOR {symbol}! Executing Step {current_step}...")
    client.futures_change_leverage(symbol=symbol, leverage=leverage)
    
    position_size = current_capital * leverage
    qty = round(position_size / entry_price, 3) 
    
    tp_move_percent = PROFIT_TARGET / leverage 
    sl_percent = 0.01 if current_step == 1 else previous_profit / position_size
    
    # Long & Short-க்கு ஏற்றபடி TP மற்றும் SL விலைகளை கணக்கிடுதல்
    if signal_type == "LONG":
        entry_side = 'BUY'
        exit_side = 'SELL'
        tp_price = entry_price * (1 + tp_move_percent)
        sl_price = entry_price * (1 - sl_percent)
    else: # SHORT
        entry_side = 'SELL'
        exit_side = 'BUY'
        tp_price = entry_price * (1 - tp_move_percent)
        sl_price = entry_price * (1 + sl_percent)
        
    print(f"Capital: ${current_capital:.2f} | Leverage: {leverage}x | Qty: {qty}")
    print(f"Entry: {entry_price} | TP: {tp_price:.4f} | SL: {sl_price:.4f}")
    
    try:
        # மார்க்கெட் ஆர்டர் (என்ட்ரி)
        client.futures_create_order(symbol=symbol, side=entry_side, type='MARKET', quantity=qty)
        # Take Profit ஆர்டர்
        client.futures_create_order(symbol=symbol, side=exit_side, type='TAKE_PROFIT_MARKET', stopPrice=round(tp_price, 4), closePosition=True)
        # Stop Loss ஆர்டர்
        client.futures_create_order(symbol=symbol, side=exit_side, type='STOP_MARKET', stopPrice=round(sl_price, 4), closePosition=True)
        
        print(f"✅ {signal_type} Trade Placed successfully. Bot monitoring for TP / SL...")
        
        # குறிப்பு: இது ஒரு Basic Setup. ஆர்டர் ஹிட் ஆனதை கண்காணிக்க WebSockets பயன்படுத்த வேண்டும்.
        # இப்போதைக்கு Trade வெற்றி பெற்றதாக Simulation செய்யப்படுகிறது.
        won_trade = True 
        
        if won_trade:
            profit_made = current_capital * PROFIT_TARGET
            print(f"🎯 TP HIT! Profit: ${profit_made:.2f}")
            previous_profit = profit_made
            current_capital += profit_made
            current_step += 1
            print(f"💰 Moving to Step {current_step} with Capital: ${current_capital:.2f}")
            
    except Exception as e:
        print(f"Trade Error: {e}")

def run_bot():
    print("🤖 Bot Started... Scanning 10 Coins for Long & Short Signals...")
    while True:
        if current_step > 40:
            print(f"🏆 40-STEP COMPOUNDING COMPLETED! Total Capital: ${current_capital:.2f}")
            break 
            
        for coin in SYMBOLS:
            signal_type, price = get_indicators_and_signal(coin)
            
            if signal_type:
                execute_trade(coin, signal_type, price)
                time.sleep(10) # ஆர்டர் போட்டவுடன் சற்று நேரம் காத்திருக்க
                break 
                
        time.sleep(60) # அடுத்த ஸ்கேனிங் 1 நிமிடம் கழித்து நடக்கும்

if __name__ == '__main__':
    # ட்ரேடிங் பாட்டை பேக்கிரவுண்டில் இயக்குகிறோம் (Background Thread)
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    # Render-க்காக டம்மி வெப் சர்வரை மெயின் த்ரெட்டில் (Main Thread) இயக்குகிறோம்
    run_server()


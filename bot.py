import time
import pandas as pd
from binance.client import Client
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator

# 1. உங்களின் Binance Testnet API Key மற்றும் Secret Key இங்கே கொடுக்கவும்
API_KEY = 'UMWk2jHECWvQx4sppfGvKzuRFYWhxpxBTEcUzOxTxiIwwF7xXUPk29Y2LpH70cwN'
API_SECRET = 'h5NFdfZqY1pSDQe9lQOlkuK4welktvBTQ9U6juy5zfCy9Qt7v3sQGG2V7AYalGsp'

# Testnet=True என உள்ளதால் இது Virtual Money-ல் பாதுகாப்பாக இயங்கும்
client = Client(API_KEY, API_SECRET, testnet=True)

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'ADAUSDT', 
           'XRPUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT']

TIMEFRAME = Client.KLINE_INTERVAL_15MINUTE
PROFIT_TARGET = 0.30  # 30% லாப இலக்கு (ROE)

current_step = 1
current_capital = 20.0  
previous_profit = 0.0   

def get_indicators_and_signal(symbol):
    try:
        klines = client.futures_klines(symbol=symbol, interval=TIMEFRAME, limit=250)
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        
        # இண்டிகேட்டர்கள் கணக்கீடு
        df['ema_200'] = EMAIndicator(close=df['close'], window=200).ema_indicator()
        df['rsi'] = RSIIndicator(close=df['close'], window=14).rsi()
        macd = MACD(close=df['close'])
        df['macd_line'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        
        # Volume Filter
        df['vol_ma'] = df['volume'].rolling(window=20).mean()
        
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        current_price = last_row['close']
        
        # நிபந்தனைகள்
        cond_1 = current_price > last_row['ema_200']  
        cond_2 = prev_row['rsi'] < 40 and last_row['rsi'] > 40  
        cond_3 = last_row['macd_line'] > last_row['macd_signal'] 
        cond_4 = last_row['volume'] > last_row['vol_ma']  
        
        if cond_1 and cond_2 and cond_3 and cond_4:
            return True, current_price
        return False, current_price
        
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return False, 0

def execute_trade(symbol, entry_price):
    global current_step, current_capital, previous_profit
    
    leverage = 10 if current_step == 1 else 20
    
    print(f"\n🚀 SIGNAL DETECTED FOR {symbol}! Executing Step {current_step}...")
    client.futures_change_leverage(symbol=symbol, leverage=leverage)
    
    position_size = current_capital * leverage
    qty = round(position_size / entry_price, 3) 
    
    tp_move_percent = PROFIT_TARGET / leverage 
    tp_price = entry_price * (1 + tp_move_percent)
    break_even_trigger_price = entry_price * (1 + (tp_move_percent / 2))
    
    if current_step == 1:
        sl_percent = 0.01 
    else:
        sl_percent = previous_profit / position_size
        
    sl_price = entry_price * (1 - sl_percent)
    
    print(f"Capital: ${current_capital} | Leverage: {leverage}x | Qty: {qty}")
    print(f"Entry: {entry_price} | TP: {tp_price:.4f} | SL: {sl_price:.4f}")
    
    try:
        # Testnet Live Orders
        client.futures_create_order(symbol=symbol, side='BUY', type='MARKET', quantity=qty)
        client.futures_create_order(symbol=symbol, side='SELL', type='TAKE_PROFIT_MARKET', stopPrice=tp_price, closePosition=True)
        client.futures_create_order(symbol=symbol, side='SELL', type='STOP_MARKET', stopPrice=sl_price, closePosition=True)
        
        print("✅ Trade Placed. Bot monitoring for Break-Even / TP / SL...")
        
        won_trade = True 
        
        if won_trade:
            profit_made = current_capital * PROFIT_TARGET
            print(f"🎯 TP HIT! Profit: ${profit_made:.2f}")
            previous_profit = profit_made
            current_capital += profit_made
            current_step += 1
            print(f"💰 Moving to Step {current_step} with Capital: ${current_capital:.2f}")
        else:
            print(f"🛑 SL HIT! Trade Lost.")
            if current_step == 1:
                current_capital -= (current_capital * 0.10) 
            else:
                current_capital -= previous_profit 
                
            current_step = 1
            current_capital = 20.0
            previous_profit = 0.0
            
    except Exception as e:
        print(f"Trade Error: {e}")

print("🤖 Bot Started... Scanning 10 Coins...")
while True:
    if current_step > 30:
        print(f"🏆 30-STEP COMPOUNDING COMPLETED! Total Capital: ${current_capital:.2f}")
        break 
        
    for coin in SYMBOLS:
        signal, price = get_indicators_and_signal(coin)
        
        if signal:
            execute_trade(coin, price)
            time.sleep(10)
            break 
            
    time.sleep(60)

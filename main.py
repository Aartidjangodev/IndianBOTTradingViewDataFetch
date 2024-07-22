import logging
import pandas as pd
from enum import Enum
from websocket import create_connection
import requests
import json
import random
import re
import string
import datetime
from indian_companies import indian_companies
from time import sleep
import numpy as np
 
logger = logging.getLogger(__name__)
 
class Interval(Enum):
    in_1_minute = "1"
    in_3_minute = "3"
    in_5_minute = "5"
    in_15_minute = "15"
    in_30_minute = "30"
    in_45_minute = "45"
    in_1_hour = "1H"
    in_2_hour = "2H"
    in_3_hour = "3H"
    in_4_hour = "4H"
    in_daily = "1D"
    in_weekly = "1W"
    in_monthly = "1M"
 
class TvDatafeed:
    __sign_in_url = 'https://www.tradingview.com/accounts/signin/'
    __search_url = 'https://symbol-search.tradingview.com/symbol_search/?text={}&hl=1&exchange={}&lang=en&type=&domain=production'
    __ws_headers = json.dumps({"Origin": "https://data.tradingview.com"})
    __signin_headers = {'Referer': 'https://www.tradingview.com'}
    __ws_timeout = 5
 
    def __init__(self, username: str = None, password: str = None) -> None:
        self.ws_debug = False
        self.token = self.__auth(username, password)
        if self.token is None:
            self.token = "unauthorized_user_token"
            logger.warning("you are using nologin method, data you access may be limited")
        self.ws = None
        self.session = self.__generate_session()
        self.chart_session = self.__generate_chart_session()
 
    def __auth(self, username, password):
        if (username is None or password is None):
            token = None
        else:
            data = {"username": username, "password": password, "remember": "on"}
            try:
                response = requests.post(url=self.__sign_in_url, data=data, headers=self.__signin_headers)
                token = response.json()['user']['auth_token']
            except Exception as e:
                logger.error('error while signin')
                token = None
        return token
 
    def __create_connection(self):
        try:
            self.ws = create_connection("wss://data.tradingview.com/socket.io/websocket", headers=self.__ws_headers, timeout=self.__ws_timeout)
        except Exception as e:
            logger.error(f"Error creating websocket connection: {e}")
 
    @staticmethod
    def __filter_raw_message(text):
        try:
            found = re.search('"m":"(.+?)",', text).group(1)
            found2 = re.search('"p":(.+?"}"])}', text).group(1)
            return found, found2
        except AttributeError:
            logger.error("error in filter_raw_message")
 
    @staticmethod
    def __generate_session():
        stringLength = 12
        letters = string.ascii_lowercase
        random_string = "".join(random.choice(letters) for i in range(stringLength))
        return "qs_" + random_string
 
    @staticmethod
    def __generate_chart_session():
        stringLength = 12
        letters = string.ascii_lowercase
        random_string = "".join(random.choice(letters) for i in range(stringLength))
        return "cs_" + random_string
 
    @staticmethod
    def __prepend_header(st):
        return "~m~" + str(len(st)) + "~m~" + st
 
    @staticmethod
    def __construct_message(func, param_list):
        return json.dumps({"m": func, "p": param_list}, separators=(",", ":"))
 
    def __create_message(self, func, paramList):
        return self.__prepend_header(self.__construct_message(func, paramList))
 
    def __send_message(self, func, args):
        m = self.__create_message(func, args)
        if self.ws_debug:
            print(m)
        self.ws.send(m)
 
    @staticmethod
    def __create_df(raw_data, symbol):
        try:
            out = re.search('"s":\[(.+?)\}\]', raw_data).group(1)
            x = out.split(',{"')
            data = list()
            volume_data = True
 
            for xi in x:
                xi = re.split("\[|:|,|\]", xi)
                ts = datetime.datetime.fromtimestamp(float(xi[4]))
 
                row = [ts]
 
                for i in range(5, 10):
                    if not volume_data and i == 9:
                        row.append(0.0)
                        continue
                    try:
                        row.append(float(xi[i]))
                    except ValueError:
                        volume_data = False
                        row.append(0.0)
                        logger.debug('no volume data')
                data.append(row)
 
            data = pd.DataFrame(data, columns=["datetime", "open", "high", "low", "close", "volume"]).set_index("datetime")
            data.insert(0, "symbol", value=symbol)
            return data
        except AttributeError:
            logger.error("no data, please check the exchange and symbol")
 
    @staticmethod
    def __format_symbol(symbol, exchange, contract: int = None):
        if ":" in symbol:
            pass
        elif contract is None:
            symbol = f"{exchange}:{symbol}"
        elif isinstance(contract, int):
            symbol = f"{exchange}:{symbol}{contract}!"
        else:
            raise ValueError("not a valid contract")
        return symbol
 
    def get_hist(self, symbol: str, exchange: str = "NSE", interval: Interval = Interval.in_daily, n_bars: int = 10, fut_contract: int = None, extended_session: bool = False) -> pd.DataFrame:
        # Simulate or load mock data using the provided symbol
 
        data = {
            'symbol': [],
            'open': [],
            'high': [],
            'low': [],
            'close': [],
            'volume': []
        }
        # Generate mock data for each symbol
        for _ in range(n_bars):
            data['symbol'].append(symbol)
            data['open'].append(random.uniform(100, 1000))
            data['high'].append(random.uniform(100, 1000))
            data['low'].append(random.uniform(100, 1000))
            data['close'].append(random.uniform(100, 1000))
            data['volume'].append(random.randint(100000, 1000000))
        df = pd.DataFrame(data)
        return df
 
    def search_symbol(self, text: str, exchange: str = ''):
        url = self.__search_url.format(text, exchange)
 
        symbols_list = []
        try:
            resp = requests.get(url)
 
            symbols_list = json.loads(resp.text.replace('</em>', '').replace('<em>', ''))
        except Exception as e:
            logger.error(e)
 
        return symbols_list
 
    def get_selected_indian_stocks_data(self):
        dfs = []
        for stock in indian_companies:
            try:
                df = self.get_hist(stock, exchange="NSE", interval=Interval.in_daily)
                if df is not None:
                    dfs.append(df)
                else:
                    logger.warning(f"No data found for {stock}")
            except Exception as e:
                logger.error(f"Error fetching data for {stock}: {e}")
 
        if not dfs:
            logger.warning("No data fetched for any stocks")
            return None
 
        all_data = pd.concat(dfs)
        return all_data
   
def fetch_and_store_data(tv):
    selected_data = tv.get_selected_indian_stocks_data()
    if (selected_data is not None) and (not selected_data.empty):
        selected_data.to_csv('4000data.csv', index=False)
        print("Data fetched and stored successfully.")
    else:
        print("Failed to fetch data.")
 
def apply_trend_signal_indicator(df):
    def percent(nom, div):
        return 100 * nom / div
 
    def f1(m, n):
        return m if m >= n else 0.0
 
    def f2(m, n):
        return 0.0 if m >= n else -m
 
    df['hl2'] = (df['high'] + df['low']) / 2
    df['src1'] = df['open'].rolling(window=5).mean().shift(1)
    df['src2'] = df['close'].rolling(window=12).mean()
    df['momm1'] = df['src1'].diff()
    df['momm2'] = df['src2'].diff()
    df['m1'] = df.apply(lambda row: f1(row['momm1'], row['momm2']), axis=1)
    df['m2'] = df.apply(lambda row: f2(row['momm1'], row['momm2']), axis=1)
    df['sm1'] = df['m1'].rolling(window=1).sum()
    df['sm2'] = df['m2'].rolling(window=1).sum()
    df['tsi'] = percent(df['sm1'], df['sm2'].abs())
 
    return df
 
def andean_oscillator(df):
    AO = lambda data: (data['high'].rolling(window=5).mean() + data['low'].rolling(window=5).mean()) / 2
 
    df['andean_oscillator'] = AO(df)
    df['andean_oscillator'].fillna(0, inplace=True)
    return df
 
def process_data():
    tv = TvDatafeed()
    fetch_and_store_data(tv)
    df = pd.read_csv('4000data.csv')
 
    # Apply the Trend Signal Indicator
    df = apply_trend_signal_indicator(df)
 
    # Apply the Andean Oscillator
    df = andean_oscillator(df)
 
    # Calculate buy and sell values based on Trend Signal Indicator
    buy_signals = df['tsi'] > 0
    sell_signals = df['tsi'] < 0
 
    df['entryOfLongPosition'] = np.where(buy_signals, df['close'], np.nan)
    df['entryOfShortPosition'] = np.where(sell_signals, df['close'], np.nan)
 
    current_buy_prices = {}
    current_sell_prices = {}
 
    # Print trade information
    for symbol in df['symbol'].unique():
        symbol_data = df[df['symbol'] == symbol]
 
        for index, row in symbol_data.iterrows():
            if not pd.isna(row['entryOfLongPosition']):
                current_buy_prices[symbol] = row['close']
            if not pd.isna(row['entryOfShortPosition']):
                current_sell_prices[symbol] = row['close']
 
            print("------------------------------")
            print(f"🔢 symbol: {row['symbol']}")
            print(f"💵 open: {row['open']}")
            print(f"📈 high: {row['high']}")
            print(f"📉 low: {row['low']}")
            print(f"❌ close: {row['close']}")
            print(f"📊 volume: {row['volume']}")
            if 'andean_oscillator' in row and not pd.isna(row['andean_oscillator']):
                print(f"🌀 Andean Oscillator: {row['andean_oscillator']}")
            if 'tsi' in row and not pd.isna(row['tsi']):
                print(f"📶 Trend Signal: {row['tsi']}")
            if not pd.isna(row['entryOfLongPosition']):
                print(f"🟢 Buy signal at: {row['entryOfLongPosition']}")
            if not pd.isna(row['entryOfShortPosition']):
                print(f"🔴 Sell signal at: {row['entryOfShortPosition']}")
            print("------------------------------")
 
        # Print the current buy and sell prices for the symbol
        print(f"Current Buy Price for {symbol}: {current_buy_prices.get(symbol, 'N/A')}")
        print(f"Current Sell Price for {symbol}: {current_sell_prices.get(symbol, 'N/A')}")
 
        sleep(10)  # Pause for 10 seconds
 
if __name__ == "__main__":
    process_data()

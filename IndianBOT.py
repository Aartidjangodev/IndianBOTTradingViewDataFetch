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
from time import sleep
import sys

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
            data = {"username": username,
                    "password": password,
                    "remember": "on"}
            try:
                response = requests.post(
                    url=self.__sign_in_url, data=data, headers=self.__signin_headers)
                token = response.json()['user']['auth_token']
            except Exception as e:
                logger.error('error while signin')
                token = None
        return token

    def __create_connection(self):
        logging.debug("creating websocket connection")
        self.ws = create_connection(
            "wss://data.tradingview.com/socket.io/websocket", headers=self.__ws_headers, timeout=self.__ws_timeout
        )

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

            data = pd.DataFrame(
                data, columns=["datetime", "open", "high", "low", "close", "volume"]
            ).set_index("datetime")
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

    def get_hist(self, symbol: str, exchange: str = "NSE", interval: Interval = Interval.in_daily,
                 n_bars: int = 10, fut_contract: int = None, extended_session: bool = False) -> pd.DataFrame:
        symbol = self.__format_symbol(symbol=symbol, exchange=exchange, contract=fut_contract)
        interval = interval.value
        self.__create_connection()
        self.__send_message("set_auth_token", [self.token])
        self.__send_message("chart_create_session", [self.chart_session, ""])
        self.__send_message("quote_create_session", [self.session])
        self.__send_message(
            "quote_set_fields",
            [
                self.session, "ch", "chp", "current_session", "description", "local_description",
                "language", "exchange", "fractional", "is_tradable", "lp", "lp_time", "minmov",
                "minmove2", "original_name", "pricescale", "pro_name", "short_name", "type",
                "update_mode", "volume", "currency_code", "rchp", "rtc"
            ],
        )

        self.__send_message(
            "quote_add_symbols", [self.session, symbol, {"flags": ["force_permission"]}]
        )
        self.__send_message("quote_fast_symbols", [self.session, symbol])

        self.__send_message(
            "resolve_symbol",
            [
                self.chart_session,
                "symbol_1",
                '={"symbol":"' + symbol + '","adjustment":"splits","session":' +
                ('"regular"' if not extended_session else '"extended"') + "}",
            ],
        )
        self.__send_message(
            "create_series", [self.chart_session, "s1", "s1", "symbol_1", interval, n_bars]
        )
        self.__send_message("switch_timezone", [self.chart_session, "exchange"])

        raw_data = ""

        logger.debug(f"getting data for {symbol}...")
        while True:
            try:
                result = self.ws.recv()
                raw_data = raw_data + result + "\n"
            except Exception as e:
                logger.error(e)
                break

            if "series_completed" in result:
                break

        return self.__create_df(raw_data, symbol)

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
    if selected_data is not None:
        selected_data.to_csv('5000data.csv', index=False)
        print("Data fetched and stored successfully.")
    else:
        print("Failed to fetch data.")


def print_trade_info(data):
    print("------------------------------")
    print(f"🔢 symbol: {data['symbol']}")
    print(f"💵 open: {data['open']}")
    print(f"📈 high: {data['high']}")
    print(f"📉 low: {data['low']}")
    print(f"❌ close: {data['close']}")
    print(f"📊 volume: {data['volume']}")
    print("------------------------------")


if __name__ == "__main__":
    # List of up to 5000 Indian company stock symbols
    indian_companies = [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "HINDUNILVR", "ICICIBANK", "KOTAKBANK", "ITC", "SBIN", "BHARTIARTL",
        # Add more stock symbols here...
        # Make sure this list contains up to 5000 symbols.
    ]

    # Initialize TvDatafeed with your TradingView username and password if required
    tv = TvDatafeed(username='your_username', password='your_password')

    fetch_and_store_data(tv)

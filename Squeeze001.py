
# --- Do not remove these libs ---
from freqtrade.strategy.interface import IStrategy
from typing import Dict, List
from functools import reduce
from pandas import DataFrame
# --------------------------------

import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy # noqa
from freqtrade.strategy.hyper import CategoricalParameter, DecimalParameter, IntParameter



class Squeeze001(IStrategy):
    """
    Strategy based on LazyBear Squeeze Momentum Indicator (on TradingView.com)

    How to use it?
    > python3 ./freqtrade/main.py -s Squeeze001
    """

    # Hyperparameters
    buy_period = IntParameter(1, 50, default=20, space="buy")
    buy_adx = DecimalParameter(1, 99, decimals=0, default=25, space="buy")
    buy_sqz_band = DecimalParameter(0.002, 0.02, decimals=4, default=0.0059, space="buy")

    # buy_period = IntParameter(1, 50, default=45, space="buy")
    # buy_adx = DecimalParameter(1, 99, decimals=0, default=23, space="buy")
    # buy_sqz_band = DecimalParameter(0.002, 0.02, decimals=4, default=0.0022, space="buy")

    buy_adx_enabled = CategoricalParameter([True, False], default=True, space="buy")


    # set the startup candles count to the longest average used (EMA, EMA etc)
    startup_candle_count = buy_period.value

    # ROI table:
    minimal_roi = {
        "0": 0.195,
        "38": 0.094,
        "85": 0.04,
        "175": 0
    }

    # Stoploss:
    stoploss = -0.318

    # Trailing stop:
    trailing_stop = True
    trailing_stop_positive = 0.092
    trailing_stop_positive_offset = 0.107
    trailing_only_offset_is_reached = False

    # Optimal timeframe for the strategy
    timeframe = '5m'

    # run "populate_indicators" only for new candle
    process_only_new_candles = False

    # Experimental settings (configuration will overide these if set)
    use_sell_signal = True
    sell_profit_only = True
    ignore_roi_if_buy_signal = True

    # Optional order type mapping
    order_types = {
        'buy': 'limit',
        'sell': 'limit',
        'stoploss': 'market',
        'stoploss_on_exchange': False
    }

    def informative_pairs(self):
        """
        Define additional, informative pair/interval combinations to be cached from the exchange.
        These pair/interval combinations are non-tradeable, unless they are part
        of the whitelist as well.
        For more information, please consult the documentation
        :return: List of tuples in the format (pair, interval)
            Sample: return [("ETH/USDT", "5m"),
                            ("BTC/USDT", "15m"),
                            ]
        """
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame

        Performance Note: For the best performance be frugal on the number of indicators
        you are using. Let uncomment only the indicator you are using in your strategies
        or your hyperopt configuration, otherwise you will waste your memory and CPU usage.
        """

        # SMA - Simple Moving Average
        dataframe['sma'] = ta.SMA(dataframe, timeperiod=self.buy_period.value)

        dataframe['ema'] = ta.EMA(dataframe, timeperiod=self.buy_period.value)
        dataframe['ema3'] = ta.EMA(dataframe, timeperiod=3)
        dataframe['ema5'] = ta.EMA(dataframe, timeperiod=5)

        # MACD
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']

        # ADX
        dataframe['adx'] = ta.ADX(dataframe)
        dataframe['dm_plus'] = ta.PLUS_DM(dataframe)
        dataframe['dm_minus'] = ta.MINUS_DM(dataframe)

        # SAR Parabolic
        dataframe['sar'] = ta.SAR(dataframe)

        # RSI
        dataframe['rsi'] = ta.RSI(dataframe)

        # Inverse Fisher transform on RSI, values [-1.0, 1.0] (https://goo.gl/2JGGoy)
        rsi = 0.1 * (dataframe['rsi'] - 50)
        dataframe['fisher_rsi'] = (numpy.exp(2 * rsi) - 1) / (numpy.exp(2 * rsi) + 1)

        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=self.buy_period.value, stds=2)
        #bollinger = qtpylib.weighted_bollinger_bands(qtpylib.typical_price(dataframe), window=self.buy_period.value, stds=2)
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_mid'] = bollinger['mid']
        dataframe['bb_lowerband'] = bollinger['lower']

        # Keltner Channel
        keltner = qtpylib.keltner_channel(dataframe)
        dataframe["kc_upper"] = keltner["upper"]
        dataframe["kc_lower"] = keltner["lower"]
        dataframe["kc_middle"] = keltner["mid"]

        # Donchian Channels
        dataframe['dc_upper'] = ta.MAX(dataframe['high'], timeperiod=self.buy_period.value)
        dataframe['dc_lower'] = ta.MIN(dataframe['low'], timeperiod=self.buy_period.value)
        dataframe['dc_mid'] = ta.EMA(((dataframe['dc_upper'] + dataframe['dc_lower']) / 2),
                                     timeperiod=self.buy_period.value)

        # Squeeze Indicators.
        #   'on'  means Bollinger Band lies completely within the Keltner Channel
        #   'off' means Keltner Channel lies completely within the Bollinger Band
        #   Booleans are funky with dataframes, so just do an intermediate calculation
        dataframe['sqz_upper'] = (dataframe['bb_upperband'] - dataframe["kc_upper"])
        dataframe['sqz_lower'] = (dataframe['bb_lowerband'] - dataframe["kc_lower"])
        dataframe['sqz_on'] = ((dataframe['sqz_upper'] < 0) & (dataframe['sqz_lower'] > 0))
        dataframe['sqz_off'] = ((dataframe['sqz_upper'] > 0) & (dataframe['sqz_lower'] < 0))

        # Momentum
        # value is: Close - Moving Average( (Donchian midline + EMA) / 2 )

        # get momentum value by running linear regression on delta
        dataframe['sqz_ave'] = ta.EMA(((dataframe['dc_mid'] + dataframe['ema']) / 2),
                                      timeperiod=self.buy_period.value)
        dataframe['sqz_delta'] = ta.EMA((dataframe['close'] - dataframe['sqz_ave']),
                                      timeperiod=self.buy_period.value)
        dataframe['sqz_val'] = ta.LINEARREG(dataframe['sqz_delta'], timeperiod=self.buy_period.value)

        return dataframe

    def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = []
        # GUARDS AND TRENDS
        # check that volume is not 0 (can happen in testing, or if there are issues with exchange data)
        conditions.append(dataframe['volume'] > 0)

        # during back testing, data can be undefined, so check
        conditions.append(dataframe['sqz_upper'].notnull())

        # ADX with DM+ > DM- indicates uptrend
        if self.buy_adx_enabled.value:
            conditions.append(
                (dataframe['adx'] > self.buy_adx.value)
                # (dataframe['adx'] > self.buy_adx.value) &
                # (dataframe['dm_plus'] >= dataframe['dm_minus'])
            )

        # We can (try to) predict an upcoming swing (up) by looking for a reversal during an 'off' period
        # conditions.append(dataframe['sqz_off'])

        # don't buy if above EMA
        conditions.append(dataframe['close'] < dataframe['ema'])
        # conditions.append(dataframe['close'] < dataframe['ema5'])

        # TRIGGERS
        # squeeze values are -ve but turning around
        conditions.append(
            (dataframe['sqz_val'] < -self.buy_sqz_band.value) &
            (dataframe['sqz_val'] > dataframe['sqz_val'].shift(1)) &
            (dataframe['sqz_val'].shift(1) <= dataframe['sqz_val'].shift(2))
            # (dataframe['sqz_val'].shift(1) > dataframe['sqz_val'].shift(2)) &
            # (dataframe['sqz_val'].shift(3) < dataframe['sqz_val'].shift(2))
        )

        # build the dataframe using the conditions
        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                'buy'] = 1

        return dataframe


    def populate_sell_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the sell signal for the given dataframe
        :param dataframe: DataFrame
        :return: DataFrame with buy column

        """

        conditions = []
        # GUARDS AND TRENDS
        # check that volume is not 0 (can happen in testing, or if there are issues with exchange data)
        conditions.append(dataframe['volume'] > 0)

        # during back testing, data can be undefined, so check
        conditions.append(dataframe['sqz_upper'].notnull())

        # We can (try to) predict an upcoming swing (down) by looking for a reversal during an 'on' period
            #conditions.append(dataframe['sqz_on'])

        # don't sell if below EMA
        #conditions.append(dataframe['close'] >= dataframe['ema5'])

        # TRIGGERS
        # squeeze values are +ve but turning around
        conditions.append(
            (dataframe['sqz_val'] > self.buy_sqz_band.value) &
            (dataframe['sqz_val'] < dataframe['sqz_val'].shift(1)) &
            (dataframe['sqz_val'].shift(1) >= dataframe['sqz_val'].shift(2))
            # (dataframe['sqz_val'].shift(1) < dataframe['sqz_val'].shift(2)) &
            # (dataframe['sqz_val'].shift(3) > dataframe['sqz_val'].shift(2))
        )

        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                'sell'] = 1

        return dataframe
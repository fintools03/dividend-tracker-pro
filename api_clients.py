# api_clients.py
import requests
import time
import yfinance as yf
import pandas as pd
from datetime import datetime
from typing import Dict, Optional
from alpha_vantage.timeseries import TimeSeries
from config import api_config, app_config
from models import StockData, DividendData

class APIError(Exception):
    """Custom exception for API operations"""
    pass

class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self):
        self.last_call = 0
        self.call_count = 0
    
    def wait_if_needed(self, min_interval: int = 1):
        """Ensure minimum interval between API calls"""
        current_time = time.time()
        time_since_last = current_time - self.last_call
        
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_call = time.time()
        self.call_count += 1

class CurrencyService:
    """Service for getting currency exchange rates"""
    
    def __init__(self):
        self.rates: Dict[str, float] = {}
    
    def get_rates(self) -> Dict[str, float]:
        """Get current exchange rates"""
        try:
            response = requests.get(
                "https://api.exchangerate-api.com/v4/latest/USD",
                timeout=app_config.currency_api_timeout
            )
            if response.status_code == 200:
                data = response.json()
                self.rates = data['rates']
                return self.rates
        except requests.RequestException:
            # Use fallback rates
            pass
        
        self.rates = app_config.default_currency_rates.copy()
        return self.rates

class AlphaVantageClient:
    """Client for Alpha Vantage API"""
    
    def __init__(self):
        self.api_key = api_config.alpha_vantage_key
        self.rate_limiter = RateLimiter()
    
    def get_stock_data(self, symbol: str) -> Optional[StockData]:
        """Get stock data from Alpha Vantage"""
        if not self.api_key or self.api_key == "demo":
            return None
        
        try:
            self.rate_limiter.wait_if_needed(app_config.api_rate_limit)
            
            ts = TimeSeries(key=self.api_key, output_format='pandas')
            data, meta_data = ts.get_daily(symbol=symbol, outputsize='compact')
            
            if data is None or data.empty:
                return None
            
            current_price = float(data.iloc[0]['4. close'])
            
            # Try to get company name
            company_name = symbol
            try:
                overview_url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={symbol}&apikey={self.api_key}"
                overview_response = requests.get(overview_url, timeout=10)
                overview_data = overview_response.json()
                company_name = overview_data.get('Name', symbol)
            except:
                pass
            
            return StockData(
                symbol=symbol,
                current_price=current_price,
                currency='USD',
                company_name=company_name,
                source='Alpha Vantage',
                dividend_data=DividendData(status="Limited dividend data from Alpha Vantage")
            )
            
        except Exception as e:
            raise APIError(f"Alpha Vantage error for {symbol}: {e}")

class PolygonClient:
    """Client for Polygon API"""
    
    def __init__(self):
        self.api_key = api_config.polygon_key
        self.rate_limiter = RateLimiter()
    
    def get_stock_data(self, symbol: str) -> Optional[StockData]:
        """Get stock data from Polygon"""
        if not self.api_key:
            return None
        
        try:
            self.rate_limiter.wait_if_needed(1)
            
            # Get current price
            url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?adjusted=true&apikey={self.api_key}"
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            if data.get('resultsCount', 0) == 0:
                return None
            
            result = data['results'][0]
            current_price = float(result['c'])
            
            # Try to get company name
            company_name = symbol
            try:
                details_url = f"https://api.polygon.io/v3/reference/tickers/{symbol}?apikey={self.api_key}"
                details_response = requests.get(details_url, timeout=10)
                if details_response.status_code == 200:
                    details_data = details_response.json()
                    company_name = details_data.get('results', {}).get('name', symbol)
            except:
                pass
            
            return StockData(
                symbol=symbol,
                current_price=current_price,
                currency='USD',
                company_name=company_name,
                source='Polygon',
                dividend_data=DividendData(status="Limited dividend data from Polygon")
            )
            
        except Exception as e:
            raise APIError(f"Polygon error for {symbol}: {e}")

class YahooFinanceClient:
    """Client for Yahoo Finance (via yfinance)"""
    
    def get_stock_data(self, symbol: str) -> Optional[StockData]:
        """Get comprehensive stock data from Yahoo Finance"""
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            
            if not info or len(info) < 5:
                return None
            
            # Get current price
            current_price = (
                info.get('currentPrice') or 
                info.get('regularMarketPrice') or 
                info.get('previousClose') or 
                0
            )
            
            if current_price == 0:
                return None
            
            # Get comprehensive dividend data
            dividend_data = self._extract_dividend_data(stock, info)
            
            return StockData(
                symbol=symbol,
                current_price=float(current_price),
                currency=info.get('currency', 'USD'),
                company_name=info.get('longName', info.get('shortName', symbol)),
                source='Yahoo Finance',
                dividend_data=dividend_data,
                raw_info=info
            )
            
        except Exception as e:
            raise APIError(f"Yahoo Finance error for {symbol}: {e}")
    
    def _extract_dividend_data(self, stock, info: Dict) -> DividendData:
        """Extract comprehensive dividend data"""
        dividend_data = DividendData()
        
        try:
            # Get dividend history
            dividends = stock.dividends.tail(8)
            
            if not dividends.empty:
                last_dividend = dividends.iloc[-1]
                dividend_data.last_dividend = float(last_dividend)
                dividend_data.last_dividend_date = dividends.index[-1].strftime('%Y-%m-%d')
                
                # Calculate annual dividend
                recent_year_dividends = dividends.last('365D').sum()
                dividend_data.annual_dividend = float(recent_year_dividends)
                dividend_data.payment_count = len(dividends)
                
                # Calculate yield
                current_price = (
                    info.get('currentPrice') or 
                    info.get('regularMarketPrice') or 
                    info.get('previousClose') or 
                    0
                )
                
                if current_price > 0:
                    dividend_data.yield_percent = (recent_year_dividends / current_price) * 100
                
                dividend_data.status = "Complete dividend data available"
            else:
                dividend_data.status = "No dividend history found"
                
        except Exception:
            dividend_data.status = "Error retrieving dividend data"
        
        return dividend_data

class DataProviderService:
    """Main service that coordinates all data providers"""
    
    def __init__(self):
        self.currency_service = CurrencyService()
        self.alpha_vantage = AlphaVantageClient()
        self.polygon = PolygonClient()
        self.yahoo_finance = YahooFinanceClient()
        
        self.provider_order = [
            self.yahoo_finance,  # Most reliable, no limits
            self.alpha_vantage,  # Good for some data
            self.polygon,        # Backup option
        ]
    
    def get_stock_data(self, symbol: str) -> Optional[StockData]:
        """Get stock data using provider fallback chain"""
        for provider in self.provider_order:
            try:
                data = provider.get_stock_data(symbol)
                if data and data.current_price > 0:
                    return data
            except APIError:
                continue
        
        return None
    
    def get_currency_rates(self) -> Dict[str, float]:
        """Get current currency exchange rates"""
        return self.currency_service.get_rates()
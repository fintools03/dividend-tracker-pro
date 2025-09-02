# models.py
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd

@dataclass
class User:
    id: int
    username: str
    email: Optional[str] = None
    created_at: Optional[datetime] = None

@dataclass
class Portfolio:
    symbol: str
    shares: float
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class DividendData:
    annual_dividend: float = 0.0
    last_dividend: float = 0.0
    last_dividend_date: Optional[str] = None
    yield_percent: float = 0.0
    payment_count: int = 0
    status: str = "No data"
    
    def format_display(self, currency: str = "USD") -> str:
        if self.annual_dividend > 0:
            if currency == 'GBP':
                return f"Annual: {self.annual_dividend:.1f}p (Yield: {self.yield_percent:.2f}%)"
            else:
                return f"Annual: {currency} {self.annual_dividend:.2f} (Yield: {self.yield_percent:.2f}%)"
        return self.status

@dataclass
class StockData:
    symbol: str
    current_price: float
    currency: str = "USD"
    company_name: str = ""
    source: str = "Unknown"
    dividend_data: Optional[DividendData] = None
    raw_info: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.dividend_data is None:
            self.dividend_data = DividendData()
        if not self.company_name:
            self.company_name = self.symbol

@dataclass
class AnalysisResult:
    symbol: str
    shares: float
    company_name: str
    market: str
    country: str
    currency: str
    current_price: str
    position_value: str
    dividend_info: str
    data_source: str
    status: str

@dataclass
class MarketInfo:
    suffix: str
    market: str
    country: str
    currency: str

class MarketRegistry:
    """Registry of market information for different stock exchanges"""
    
    MARKETS = {
        '.L': MarketInfo('.L', 'London Stock Exchange', 'UK', 'GBP'),
        '.PA': MarketInfo('.PA', 'Euronext Paris', 'FR', 'EUR'),
        '.DE': MarketInfo('.DE', 'XETRA (Germany)', 'DE', 'EUR'),
        '.AS': MarketInfo('.AS', 'Euronext Amsterdam', 'NL', 'EUR'),
        '.SW': MarketInfo('.SW', 'SIX Swiss Exchange', 'CH', 'CHF'),
        '.MI': MarketInfo('.MI', 'Borsa Italiana', 'IT', 'EUR'),
        '.MC': MarketInfo('.MC', 'BME Spanish Exchanges', 'ES', 'EUR'),
        '.TO': MarketInfo('.TO', 'Toronto Stock Exchange', 'CA', 'CAD'),
        '.AX': MarketInfo('.AX', 'Australian Securities Exchange', 'AU', 'AUD'),
    }
    
    @classmethod
    def get_market_info(cls, symbol: str) -> MarketInfo:
        """Get market information for a symbol"""
        for suffix, market_info in cls.MARKETS.items():
            if symbol.endswith(suffix):
                return market_info
        return MarketInfo('', 'US Market (NASDAQ/NYSE)', 'US', 'USD')
    
    @classmethod
    def is_uk_stock(cls, symbol: str) -> bool:
        """Check if symbol is a UK stock"""
        return symbol.endswith('.L')

class CurrencyFormatter:
    """Handles currency formatting for different markets"""
    
    @staticmethod
    def format_amount(amount: float, currency: str, is_uk_stock: bool = False) -> str:
        """Format amount with appropriate currency symbol"""
        if not isinstance(amount, (int, float)):
            return str(amount)
        
        # Handle UK stocks priced in pence
        if currency == 'GBP' and is_uk_stock:
            return f"{amount:.2f}p"
        
        symbols = {
            'USD': '$', 'EUR': 'EUR', 'GBP': 'GBP', 'CHF': 'CHF',
            'SEK': 'SEK', 'NOK': 'NOK', 'DKK': 'DKK', 'CAD': 'CAD', 'AUD': 'AUD'
        }
        
        symbol = symbols.get(currency, currency)
        
        if currency in ['EUR', 'GBP', 'CHF', 'SEK', 'NOK', 'DKK', 'CAD', 'AUD']:
            return f"{symbol} {amount:.2f}"
        else:
            return f"{symbol}{amount:.2f}"
    
    @staticmethod
    def parse_amount(formatted_amount: str) -> float:
        """Extract numeric value from formatted currency string"""
        import re
        # Remove all non-numeric characters except decimal points
        numeric_str = re.sub(r'[^\d.]', '', str(formatted_amount))
        try:
            return float(numeric_str)
        except ValueError:
            return 0.0
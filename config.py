# config.py
from decouple import config
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class DatabaseConfig:
    url: Optional[str] = None
    host: str = "localhost"
    name: str = "dividend_tracker"
    user: str = "postgres"
    password: str = "password"
    
    def __post_init__(self):
        self.url = config('DATABASE_URL', default=self.url)
        if not self.url:
            self.host = config('DB_HOST', default=self.host)
            self.name = config('DB_NAME', default=self.name)
            self.user = config('DB_USER', default=self.user)
            self.password = config('DB_PASSWORD', default=self.password)

@dataclass
class APIConfig:
    alpha_vantage_key: str = ""
    polygon_key: str = ""
    
    def __post_init__(self):
        self.alpha_vantage_key = config('ALPHA_VANTAGE_API_KEY', default="0ZL6RBY7H5GO7IH9")
        self.polygon_key = config('POLYGON_API_KEY', default="ERsXTaR8Ltc3E1yR1P4RukMzHsP212NO")

@dataclass
class AppConfig:
    title: str = "Professional Dividend Tracker"
    icon: str = "💰"
    layout: str = "wide"
    currency_api_timeout: int = 10
    api_rate_limit: int = 12
    default_currency_rates: Dict[str, float] = None
    
    def __post_init__(self):
        if self.default_currency_rates is None:
            self.default_currency_rates = {
                'EUR': 0.85, 'GBP': 0.73, 'CHF': 0.88, 'SEK': 10.5,
                'NOK': 10.8, 'DKK': 6.4, 'PLN': 4.0, 'CZK': 22.0,
                'CAD': 1.25, 'AUD': 1.35, 'JPY': 110.0, 'CNY': 6.45
            }

# Global configuration instances
db_config = DatabaseConfig()
api_config = APIConfig()
app_config = AppConfig()
# dividend_tracker_pro.py
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import requests
import json
import io
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt
from decouple import config
import time
from alpha_vantage.timeseries import TimeSeries
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import re

# Page configuration
st.set_page_config(
    page_title="Professional Dividend Tracker",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main .block-container {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        padding-top: 2rem;
    }
    
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border: none;
        padding: 1rem;
        border-radius: 15px;
        color: white;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    
    [data-testid="metric-container"] > div {
        color: white;
    }
    
    h1 {
        color: #2c3e50;
        text-align: center;
        font-weight: 700;
        background: linear-gradient(45deg, #667eea, #764ba2);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .stButton > button {
        background: linear-gradient(45deg, #ff9a9e 0%, #fecfef 50%, #fecfef 100%);
        color: #2c3e50;
        border: none;
        border-radius: 25px;
        font-weight: 600;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0,0,0,0.2);
    }
    
    .stButton > button[kind="primary"] {
        background: linear-gradient(45deg, #4facfe 0%, #00f2fe 100%);
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# DATA MODELS
# =============================================================================

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
                return f"Annual: GBP {self.annual_dividend:.2f} (Yield: {self.yield_percent:.2f}%)"
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
    
    def __post_init__(self):
        if self.dividend_data is None:
            self.dividend_data = DividendData()
        if not self.company_name:
            self.company_name = self.symbol

# =============================================================================
# UTILITY CLASSES
# =============================================================================

class MarketRegistry:
    """Registry of market information for different stock exchanges"""
    
    MARKETS = {
        '.L': {'market': 'London Stock Exchange', 'country': 'UK', 'currency': 'GBP'},
        '.PA': {'market': 'Euronext Paris', 'country': 'FR', 'currency': 'EUR'},
        '.DE': {'market': 'XETRA (Germany)', 'country': 'DE', 'currency': 'EUR'},
        '.AS': {'market': 'Euronext Amsterdam', 'country': 'NL', 'currency': 'EUR'},
        '.SW': {'market': 'SIX Swiss Exchange', 'country': 'CH', 'currency': 'CHF'},
        '.MI': {'market': 'Borsa Italiana', 'country': 'IT', 'currency': 'EUR'},
        '.MC': {'market': 'BME Spanish Exchanges', 'country': 'ES', 'currency': 'EUR'},
        '.TO': {'market': 'Toronto Stock Exchange', 'country': 'CA', 'currency': 'CAD'},
        '.AX': {'market': 'Australian Securities Exchange', 'country': 'AU', 'currency': 'AUD'},
    }
    
    @classmethod
    def get_market_info(cls, symbol: str) -> Dict[str, str]:
        for suffix, market_data in cls.MARKETS.items():
            if symbol.endswith(suffix):
                return market_data
        return {'market': 'US Market (NASDAQ/NYSE)', 'country': 'US', 'currency': 'USD'}
    
    @classmethod
    def is_uk_stock(cls, symbol: str) -> bool:
        return symbol.endswith('.L')

class CurrencyFormatter:
    """Handles currency formatting for different markets"""
    
    @staticmethod
    def format_amount(amount: float, currency: str, is_uk_stock: bool = False) -> str:
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
        # Extract numeric value from formatted currency string
        numeric_str = re.sub(r'[^\d.]', '', str(formatted_amount))
        try:
            return float(numeric_str)
        except ValueError:
            return 0.0

# =============================================================================
# DATABASE LAYER
# =============================================================================

class DatabaseError(Exception):
    pass

class DatabaseManager:
    """Clean database operations without UI dependencies"""
    
    def __init__(self):
        self.connection = None
    
    def connect(self) -> bool:
        try:
            database_url = config('DATABASE_URL', default=None)
            if database_url:
                self.connection = psycopg2.connect(database_url)
            else:
                self.connection = psycopg2.connect(
                    host=config('DB_HOST', default='localhost'),
                    database=config('DB_NAME', default='dividend_tracker'),
                    user=config('DB_USER', default='postgres'),
                    password=config('DB_PASSWORD', default='password')
                )
            self._create_tables()
            return True
        except Exception as e:
            raise DatabaseError(f"Database connection failed: {e}")
    
    def _create_tables(self):
        if not self.connection:
            raise DatabaseError("No database connection")
        
        try:
            cursor = self.connection.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(100) NOT NULL,
                    email VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolios (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    symbol VARCHAR(20) NOT NULL,
                    shares DECIMAL(10,4) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, symbol)
                )
            """)
            
            self.connection.commit()
            cursor.close()
        except Exception as e:
            if self.connection:
                self.connection.rollback()
            raise DatabaseError(f"Failed to create tables: {e}")
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        if not self.connection:
            raise DatabaseError("No database connection")
        
        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user_data = cursor.fetchone()
            cursor.close()
            return dict(user_data) if user_data else None
        except Exception as e:
            raise DatabaseError(f"Failed to get user: {e}")
    
    def create_user(self, username: str, password: str, email: Optional[str] = None) -> Dict:
        if not self.connection:
            raise DatabaseError("No database connection")
        
        try:
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "INSERT INTO users (username, password_hash, email) VALUES (%s, %s, %s) RETURNING *",
                (username, password_hash, email)
            )
            user_data = cursor.fetchone()
            self.connection.commit()
            cursor.close()
            return dict(user_data)
        except Exception as e:
            if self.connection:
                self.connection.rollback()
            raise DatabaseError(f"Failed to create user: {e}")
    
    def verify_password(self, password: str, hash_password: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hash_password.encode('utf-8'))
        except Exception:
            return False
    
    def save_portfolio_item(self, user_id: int, symbol: str, shares: float) -> bool:
        if not self.connection:
            raise DatabaseError("No database connection")
        
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO portfolios (user_id, symbol, shares, updated_at) 
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id, symbol) 
                DO UPDATE SET shares = EXCLUDED.shares, updated_at = CURRENT_TIMESTAMP
            """, (user_id, symbol, shares))
            
            self.connection.commit()
            cursor.close()
            return True
        except Exception as e:
            if self.connection:
                self.connection.rollback()
            raise DatabaseError(f"Failed to save portfolio: {e}")
    
    def get_user_portfolio(self, user_id: int) -> List[Dict]:
        if not self.connection:
            raise DatabaseError("No database connection")
        
        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM portfolios WHERE user_id = %s ORDER BY symbol",
                (user_id,)
            )
            portfolio_data = cursor.fetchall()
            cursor.close()
            return [dict(item) for item in portfolio_data]
        except Exception as e:
            raise DatabaseError(f"Failed to get portfolio: {e}")
    
    def delete_portfolio_item(self, user_id: int, symbol: str) -> bool:
        if not self.connection:
            raise DatabaseError("No database connection")
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "DELETE FROM portfolios WHERE user_id = %s AND symbol = %s",
                (user_id, symbol)
            )
            rows_affected = cursor.rowcount
            self.connection.commit()
            cursor.close()
            return rows_affected > 0
        except Exception as e:
            if self.connection:
                self.connection.rollback()
            raise DatabaseError(f"Failed to delete portfolio item: {e}")

# =============================================================================
# API CLIENTS
# =============================================================================

class APIError(Exception):
    pass

class DataProviderService:
    """Coordinates all data providers with fallback chain"""
    
    def __init__(self):
        self.alpha_vantage_key = config('ALPHA_VANTAGE_API_KEY', default="0ZL6RBY7H5GO7IH9")
        self.polygon_key = config('POLYGON_API_KEY', default="ERsXTaR8Ltc3E1yR1P4RukMzHsP212NO")
        self.currency_rates = {}
        self.api_call_count = 0
        self.last_api_call = 0
        
        # Default currency rates
        self.default_rates = {
            'EUR': 0.85, 'GBP': 0.73, 'CHF': 0.88, 'SEK': 10.5,
            'NOK': 10.8, 'DKK': 6.4, 'PLN': 4.0, 'CZK': 22.0,
            'CAD': 1.25, 'AUD': 1.35, 'JPY': 110.0, 'CNY': 6.45
        }
    
    def get_currency_rates(self) -> Dict[str, float]:
        try:
            response = requests.get(
                "https://api.exchangerate-api.com/v4/latest/USD",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                self.currency_rates = data['rates']
                return self.currency_rates
        except:
            pass
        
        self.currency_rates = self.default_rates.copy()
        return self.currency_rates
    
    def _rate_limit_check(self, min_interval: int = 1):
        current_time = time.time()
        time_since_last = current_time - self.last_api_call
        
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_api_call = time.time()
        self.api_call_count += 1
    
    def get_stock_data(self, symbol: str) -> Optional[StockData]:
        # Try yfinance first (most reliable)
        try:
            data = self._get_yfinance_data(symbol)
            if data and data.current_price > 0:
                return data
        except:
            pass
        
        # Try Alpha Vantage
        if self.alpha_vantage_key and self.alpha_vantage_key != "demo":
            try:
                self._rate_limit_check(12)
                data = self._get_alpha_vantage_data(symbol)
                if data and data.current_price > 0:
                    return data
            except:
                pass
        
        # Try Polygon
        if self.polygon_key:
            try:
                self._rate_limit_check(1)
                data = self._get_polygon_data(symbol)
                if data and data.current_price > 0:
                    return data
            except:
                pass
        
        return None
    
    def _get_yfinance_data(self, symbol: str) -> Optional[StockData]:
        stock = yf.Ticker(symbol)
        info = stock.info
        
        if not info or len(info) < 5:
            return None
        
        current_price = (
            info.get('currentPrice') or 
            info.get('regularMarketPrice') or 
            info.get('previousClose') or 
            0
        )
        
        if current_price == 0:
            return None
        
        # Get dividend data
        dividend_data = DividendData()
        try:
            dividends = stock.dividends.tail(12)  # Get more history
            if not dividends.empty:
                last_dividend = dividends.iloc[-1]
                dividend_data.last_dividend = float(last_dividend)
                dividend_data.last_dividend_date = dividends.index[-1].strftime('%Y-%m-%d')
        
                # Better annual dividend calculation
                one_year_ago = datetime.now() - timedelta(days=365)
                recent_dividends = dividends[dividends.index > one_year_ago]
        
                if len(recent_dividends) >= 4:
                    annual_dividend = recent_dividends.sum()
                elif len(recent_dividends) >= 2:
                    avg_dividend = recent_dividends.mean()
                    days_span = (recent_dividends.index[-1] - recent_dividends.index[0]).days
                    if days_span > 0:
                        payments_per_year = len(recent_dividends) * (365 / days_span)
                        annual_dividend = avg_dividend * payments_per_year
                    else:
                        annual_dividend = info.get('dividendRate', last_dividend * 4)
                else:
                    annual_dividend = info.get('dividendRate', last_dividend * 4)
        
                dividend_data.annual_dividend = float(annual_dividend)
                dividend_data.payment_count = len(dividends)
        
                if current_price > 0 and annual_dividend > 0:
                    dividend_data.yield_percent = (annual_dividend / current_price) * 100
        
                dividend_data.status = "Complete dividend data available"
            else:
                dividend_data.status = "No dividend history found"
    except:
        dividend_data.status = "Error retrieving dividend data"
    
        def _get_alpha_vantage_data(self, symbol: str) -> Optional[StockData]:
            ts = TimeSeries(key=self.alpha_vantage_key, output_format='pandas')
            data, meta_data = ts.get_daily(symbol=symbol, outputsize='compact')
        
        if data is None or data.empty:
                return None
        
        current_price = float(data.iloc[0]['4. close'])
        
        return StockData(
            symbol=symbol,
            current_price=current_price,
            currency='USD',
            company_name=symbol,
            source='Alpha Vantage',
            dividend_data=DividendData(status="Limited dividend data")
        )
    
    def _get_polygon_data(self, symbol: str) -> Optional[StockData]:
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?adjusted=true&apikey={self.polygon_key}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        if data.get('resultsCount', 0) == 0:
            return None
        
        result = data['results'][0]
        current_price = float(result['c'])
        
        return StockData(
            symbol=symbol,
            current_price=current_price,
            currency='USD',
            company_name=symbol,
            source='Polygon',
            dividend_data=DividendData(status="Limited dividend data")
        )

# =============================================================================
# MAIN APPLICATION
# =============================================================================

class DividendTrackerApp:
    """Main application class"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.data_provider = DataProviderService()
        self._initialize_database()
    
    def _initialize_database(self):
        try:
            if self.db.connect():
                st.sidebar.success("✅ Database connected")
        except DatabaseError as e:
            st.error(f"Database error: {e}")
            st.stop()
    
    def _initialize_session_state(self):
        if 'authenticated' not in st.session_state:
            st.session_state.authenticated = False
        if 'user' not in st.session_state:
            st.session_state.user = None
        if 'portfolio_data' not in st.session_state:
            st.session_state.portfolio_data = []
        if 'analysis_results' not in st.session_state:
            st.session_state.analysis_results = []
    
    def run(self):
        self._initialize_session_state()
        
        if st.session_state.authenticated:
            self._render_main_app()
        else:
            self._render_login_page()
    
    def _render_login_page(self):
        st.title("🔐 Authentication")
        
        tab1, tab2 = st.tabs(["Login", "Sign Up"])
        
        with tab1:
            self._render_login_tab()
        
        with tab2:
            self._render_signup_tab()
    
    def _render_login_tab(self):
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            
            if submitted and username and password:
                try:
                    user = self.db.get_user_by_username(username)
                    if user and self.db.verify_password(password, user['password_hash']):
                        st.session_state.authenticated = True
                        st.session_state.user = user
                        st.success("✅ Login successful!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Invalid username or password")
                except DatabaseError as e:
                    st.error(f"Login error: {e}")
    
    def _render_signup_tab(self):
        with st.form("signup_form"):
            username = st.text_input("Choose Username")
            email = st.text_input("Email (optional)")
            password = st.text_input("Choose Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Sign Up")
            
            if submitted and username and password:
                if password != confirm_password:
                    st.error("❌ Passwords don't match")
                elif len(password) < 6:
                    st.error("❌ Password must be at least 6 characters")
                else:
                    try:
                        existing_user = self.db.get_user_by_username(username)
                        if existing_user:
                            st.error("❌ Username already exists")
                        else:
                            self.db.create_user(username, password, email)
                            st.success("✅ Account created! Please login.")
                    except DatabaseError as e:
                        st.error(f"Signup error: {e}")
    
    def _render_main_app(self):
        user = st.session_state.user
        
        st.title("💰 Professional Dividend Tracker")
        st.markdown(f"**Welcome, {user['username']}!**")
        
        self._render_sidebar()
        self._render_main_content()
    
    def _render_sidebar(self):
        user = st.session_state.user
        
        with st.sidebar:
            # Logout button
            if st.button("🚪 Logout", key=f"logout_{user['id']}"):
                st.session_state.authenticated = False
                st.session_state.user = None
                st.session_state.portfolio_data = []
                st.session_state.analysis_results = []
                st.rerun()
            
            # Portfolio management
            st.header("📊 Portfolio Management")
            
            # Load portfolio
            self._load_portfolio_data()
            
            # Add stock form
            self._render_add_stock_form()
            
            # Display portfolio
            self._render_portfolio_list()
            
            # Market examples
            self._render_market_examples()
            
            # API status
            self._show_api_status()
    
    def _load_portfolio_data(self):
        try:
            user = st.session_state.user
            portfolio = self.db.get_user_portfolio(user['id'])
            st.session_state.portfolio_data = portfolio
            
            if portfolio:
                st.sidebar.info(f"📈 {len(portfolio)} stocks in portfolio")
        except DatabaseError as e:
            st.sidebar.error(f"Error loading portfolio: {e}")
    
    def _render_add_stock_form(self):
        user = st.session_state.user
        form_key = f"add_stock_form_{user['id']}"
        
        with st.form(form_key):
            st.subheader("➕ Add Stock")
            
            symbol = st.text_input(
                "Stock Symbol",
                placeholder="e.g., AAPL, RIO.L, LR.PA, ASML",
                help="Use Yahoo Finance format"
            ).upper().strip()
            
            shares = st.number_input(
                "Number of Shares",
                min_value=0.001,
                value=1.0,
                step=1.0,
                format="%.3f"
            )
            
            submitted = st.form_submit_button("Add to Portfolio")
            
            if submitted and symbol:
                try:
                    self.db.save_portfolio_item(user['id'], symbol, shares)
                    st.success(f"✅ Added {shares} shares of {symbol}")
                    time.sleep(0.5)
                    st.rerun()
                except DatabaseError as e:
                    st.error(f"Error adding stock: {e}")
    
    def _render_portfolio_list(self):
        portfolio = st.session_state.portfolio_data
        user = st.session_state.user
        
        if not portfolio:
            st.info("No stocks in portfolio yet")
            return
        
        st.subheader(f"📋 Current Portfolio ({len(portfolio)} stocks)")
        
        for item in portfolio:
            col1, col2 = st.columns([3, 1])
            col1.text(f"{item['symbol']}: {float(item['shares']):.1f} shares")
            
            button_key = f"remove_{item['symbol']}_{user['id']}"
            if col2.button("🗑️", key=button_key, help=f"Remove {item['symbol']}"):
                try:
                    if self.db.delete_portfolio_item(user['id'], item['symbol']):
                        st.success(f"✅ Removed {item['symbol']} from portfolio")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(f"Failed to remove {item['symbol']}")
                except DatabaseError as e:
                    st.error(f"Error removing stock: {e}")
    
    def _render_market_examples(self):
        with st.expander("🔍 Market Examples"):
            st.markdown("""
            **US Markets:** AAPL, MSFT, JNJ, PG  
            **UK (.L):** SHEL.L, BP.L, RIO.L  
            **France (.PA):** MC.PA, OR.PA, LR.PA  
            **Germany (.DE):** SAP, BMW.DE  
            **Netherlands:** ASML, HEIA.AS  
            **Switzerland (.SW):** NESN.SW  
            **Canada (.TO):** SHOP.TO, RY.TO  
            **Australia (.AX):** CBA.AX, BHP.AX  
            """)
    
    def _show_api_status(self):
        alpha_status = "✅" if self.data_provider.alpha_vantage_key else "❌"
        polygon_status = "✅" if self.data_provider.polygon_key else "❌"
        st.sidebar.info(f"🔑 API Status: Alpha Vantage ({alpha_status}), Polygon ({polygon_status})")
    
    def _render_main_content(self):
        portfolio = st.session_state.portfolio_data
        
        if not portfolio:
            self._render_empty_portfolio()
        else:
            self._render_portfolio_analysis()
    
    def _render_empty_portfolio(self):
        st.info("👆 Add stocks to your portfolio using the sidebar to get started!")
        
        st.subheader("📱 Example Usage")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**US Stock:**\n- Symbol: `AAPL`\n- Shares: `10`")
        with col2:
            st.markdown("**UK Stock:**\n- Symbol: `RIO.L`\n- Shares: `25`")
        with col3:
            st.markdown("**European Stock:**\n- Symbol: `ASML`\n- Shares: `5`")
    
    def _render_portfolio_analysis(self):
        portfolio = st.session_state.portfolio_data
        
        st.info(f"📈 You have {len(portfolio)} stocks in your portfolio. Click 'Analyze Portfolio' to get current data!")
        
        if st.button("🔍 Analyze Portfolio", type="primary"):
            self._perform_portfolio_analysis()
        
        if st.session_state.analysis_results:
            self._display_analysis_results()
    
    def _perform_portfolio_analysis(self):
        portfolio = st.session_state.portfolio_data
        
        with st.spinner("Getting exchange rates..."):
            currency_rates = self.data_provider.get_currency_rates()
        
        st.subheader("🔄 Analysis Progress")
        results = []
        
        progress_bar = st.progress(0)
        status_container = st.empty()
        
        for i, portfolio_item in enumerate(portfolio):
            status_container.write(f"**{i+1}/{len(portfolio)}** - Analyzing {portfolio_item['symbol']}...")
            
            try:
                stock_data = self.data_provider.get_stock_data(portfolio_item['symbol'])
                
                if stock_data:
                    market_info = MarketRegistry.get_market_info(portfolio_item['symbol'])
                    is_uk_stock = MarketRegistry.is_uk_stock(portfolio_item['symbol'])
                    
                    currency = stock_data.currency if stock_data.currency else market_info['currency']
                    
                    # Calculate position value
                    position_value = float(portfolio_item['shares']) * stock_data.current_price
                    
                    # Handle UK stocks position value conversion (pence to pounds)
                    if is_uk_stock and currency == 'GBP':
                        position_value_pounds = position_value / 100
                        position_value_formatted = f"GBP {position_value_pounds:.2f}"
                    else:
                        position_value_formatted = CurrencyFormatter.format_amount(position_value, currency)
                    
                    result = {
                        'symbol': portfolio_item['symbol'],
                        'shares': float(portfolio_item['shares']),
                        'company_name': stock_data.company_name[:40],
                        'market': market_info['market'],
                        'country': market_info['country'],
                        'currency': currency,
                        'current_price': CurrencyFormatter.format_amount(
                            stock_data.current_price, currency, is_uk_stock
                        ),
                        'position_value': position_value_formatted,
                        'dividend_info': stock_data.dividend_data.format_display(currency),
                        'data_source': stock_data.source,
                        'status': '✅ Success'
                    }
                else:
                    result = {
                        'symbol': portfolio_item['symbol'],
                        'shares': float(portfolio_item['shares']),
                        'company_name': 'Data unavailable',
                        'market': 'Unknown',
                        'country': 'Unknown',
                        'currency': 'Unknown',
                        'current_price': 'N/A',
                        'position_value': 'N/A',
                        'dividend_info': 'No data available',
                        'data_source': 'All sources failed',
                        'status': '❌ Failed'
                    }
                
                results.append(result)
                
            except Exception as e:
                error_result = {
                    'symbol': portfolio_item['symbol'],
                    'shares': float(portfolio_item['shares']),
                    'company_name': 'Error',
                    'market': 'Unknown',
                    'country': 'Unknown',
                    'currency': 'Unknown',
                    'current_price': 'N/A',
                    'position_value': 'N/A',
                    'dividend_info': 'Error retrieving data',
                    'data_source': f'Error: {str(e)}',
                    'status': '❌ Error'
                }
                results.append(error_result)
            
            progress_bar.progress((i + 1) / len(portfolio))
        
        st.session_state.analysis_results = results
        status_container.empty()
        st.balloons()
        st.success(f"✅ Analysis complete! Processed {len(results)} stocks.")
    
    def _display_analysis_results(self):
        results = st.session_state.analysis_results
        currency_rates = self.data_provider.get_currency_rates()
        
        # Summary metrics
        st.subheader("📊 Portfolio Summary")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Stocks", len(results))
        
        with col2:
            successful = sum(1 for r in results if "Success" in r['status'])
            st.metric("Data Retrieved", f"{successful}/{len(results)}")
        
        with col3:
            sources = {r['data_source'] for r in results if "failed" not in r['data_source'].lower()}
            st.metric("Active Data Sources", len(sources))
        
        with col4:
            valued_positions = sum(1 for r in results if r['position_value'] != "N/A")
            st.metric("Valued Positions", valued_positions)
        
        # Detailed portfolio table
        st.subheader("💼 Portfolio Details")
        
        successful_results = [r for r in results if "Success" in r['status']]
        failed_results = [r for r in results if "Success" not in r['status']]
        
        if successful_results:
            display_data = []
            for result in successful_results:
                display_data.append({
                    'Symbol': result['symbol'],
                    'Company': result['company_name'],
                    'Shares': f"{result['shares']:.1f}",
                    'Market': result['country'],
                    'Currency': result['currency'],
                    'Current Price': result['current_price'],
                    'Position Value': result['position_value'],
                    'Dividend Info': result['dividend_info'],
                    'Data Source': result['data_source']
                })
            
            df_display = pd.DataFrame(display_data)
            st.dataframe(df_display, use_container_width=True, height=400)
        
        if failed_results:
            st.subheader("⚠️ Stocks with Data Issues")
            for result in failed_results:
                st.warning(f"**{result['symbol']}** ({result['shares']} shares) - {result['data_source']}")
        
        # Portfolio valuation
        st.subheader("💰 Portfolio Valuation")
        
        total_usd = 0
        currency_breakdown = {}
        
        for result in successful_results:
            if result['position_value'] and result['position_value'] != "N/A":
                try:
                    value = CurrencyFormatter.parse_amount(result['position_value'])
                    currency = result['currency']
                    
                    # Convert to USD
                    if currency == 'USD':
                        usd_value = value
                    else:
                        rate = currency_rates.get(currency, 1)
                        usd_value = value / rate if rate > 0 else 0
                    
                    total_usd += usd_value
                    currency_breakdown[currency] = currency_breakdown.get(currency, 0) + value
                except:
                    continue
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Total Value (USD)", f"${total_usd:,.2f}")
        
        with col2:
            if len(currency_breakdown) > 1:
                breakdown_items = []
                for curr, val in currency_breakdown.items():
                    formatted = CurrencyFormatter.format_amount(val, curr)
                    breakdown_items.append(f"{curr}: {formatted}")
                breakdown_text = " | ".join(breakdown_items[:3])
                st.metric("Currency Breakdown", breakdown_text)
        
        # Data source performance
        st.subheader("📡 Data Source Performance")
        source_counts = {}
        
        for result in successful_results:
            source = result['data_source']
            source_counts[source] = source_counts.get(source, 0) + 1
        
        for source, count in source_counts.items():
            st.info(f"**{source}**: Retrieved data for {count} stocks")
        
        # Export options
        st.subheader("📥 Export Portfolio")
        
        col1, col2, col3 = st.columns(3)
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
        
        with col1:
            # Excel export
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_results = pd.DataFrame(results)
                df_results.to_excel(writer, index=False, sheet_name='Portfolio_Analysis')
                
                summary_data = {
                    'Total Stocks': [len(results)],
                    'Successful Retrievals': [sum(1 for r in results if "Success" in r['status'])],
                    'Analysis Date': [datetime.now().strftime('%Y-%m-%d %H:%M')],
                    'User': [st.session_state.user['username']]
                }
                pd.DataFrame(summary_data).to_excel(writer, index=False, sheet_name='Summary')
            
            st.download_button(
                label="📊 Download Excel Report",
                data=buffer.getvalue(),
                file_name=f"portfolio_analysis_{timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with col2:
            # CSV export
            df_csv = pd.DataFrame(results)
            csv = df_csv.to_csv(index=False)
            st.download_button(
                label="📄 Download CSV",
                data=csv,
                file_name=f"portfolio_analysis_{timestamp}.csv",
                mime="text/csv"
            )
        
        with col3:
            # Clear results button
            if st.button("🔄 Clear Results"):
                st.session_state.analysis_results = []
                st.rerun()

def main():
    """Application entry point"""
    app = DividendTrackerApp()
    app.run()

if __name__ == "__main__":
    main()

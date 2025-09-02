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

# Page configuration
st.set_page_config(
    page_title="Professional Dividend Tracker",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for bright, light color scheme
st.markdown("""
<style>
    .main .block-container {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        padding-top: 2rem;
    }
    
    .css-1d391kg {
        background: linear-gradient(180deg, #a8edea 0%, #fed6e3 100%);
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
    
    h2, h3 {
        color: #34495e;
        font-weight: 600;
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
    
    .login-container {
        max-width: 400px;
        margin: 0 auto;
        padding: 2rem;
        background: rgba(255, 255, 255, 0.95);
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

class DatabaseManager:
    def __init__(self):
        self.connection = None
        self.connect()
    
    def connect(self):
        """Connect to PostgreSQL database"""
        try:
            # Railway provides DATABASE_URL environment variable
            database_url = config('DATABASE_URL', default=None)
            if database_url:
                self.connection = psycopg2.connect(database_url)
                st.success("✅ Connected to Railway PostgreSQL database")
            else:
                # Fallback for local development
                self.connection = psycopg2.connect(
                    host=config('DB_HOST', default='localhost'),
                    database=config('DB_NAME', default='dividend_tracker'),
                    user=config('DB_USER', default='postgres'),
                    password=config('DB_PASSWORD', default='password')
                )
                st.info("Connected to local database")
            self.create_tables()
        except Exception as e:
            st.error(f"Database connection error: {e}")
            self.connection = None
    
    def create_tables(self):
        """Create necessary tables if they don't exist"""
        if not self.connection:
            return
        
        try:
            cursor = self.connection.cursor()
            
            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(100) NOT NULL,
                    email VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Portfolios table with proper unique constraint - FIXED
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
            
            # Dividend history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dividend_history (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    symbol VARCHAR(20) NOT NULL,
                    ex_date DATE,
                    payment_date DATE,
                    dividend_amount DECIMAL(10,4),
                    shares DECIMAL(10,4),
                    total_payment DECIMAL(10,2),
                    currency VARCHAR(5),
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.connection.commit()
            cursor.close()
            st.success("✅ Database tables created successfully")
        except Exception as e:
            st.error(f"Error creating tables: {e}")
            if self.connection:
                self.connection.rollback()
    
    def get_user(self, username):
        """Get user by username"""
        if not self.connection:
            return None
        
        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            cursor.close()
            return user
        except Exception as e:
            st.error(f"Error getting user: {e}")
            return None
    
    def create_user(self, username, password, email=None):
        """Create new user"""
        if not self.connection:
            return False
        
        try:
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO users (username, password_hash, email) VALUES (%s, %s, %s)",
                (username, password_hash, email)
            )
            self.connection.commit()
            cursor.close()
            return True
        except Exception as e:
            st.error(f"Error creating user: {e}")
            return False
    
    def verify_password(self, password, hash_password):
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hash_password.encode('utf-8'))
    
    def save_portfolio(self, user_id, symbol, shares):
        """Save or update portfolio entry"""
        if not self.connection:
            st.error("No database connection available")
            return False
        
        try:
            cursor = self.connection.cursor()
            # FIXED: Proper UPSERT with EXCLUDED keyword
            cursor.execute("""
                INSERT INTO portfolios (user_id, symbol, shares, updated_at) 
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id, symbol) 
                DO UPDATE SET shares = EXCLUDED.shares, updated_at = CURRENT_TIMESTAMP
            """, (user_id, symbol, shares))
            
            self.connection.commit()
            cursor.close()
            st.success(f"✅ Portfolio updated: {symbol} - {shares} shares")
            return True
        except Exception as e:
            st.error(f"Error saving portfolio: {e}")
            if self.connection:
                self.connection.rollback()
            return False
    
    def get_portfolio(self, user_id):
        """Get user's portfolio"""
        if not self.connection:
            return []
        
        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT symbol, shares FROM portfolios WHERE user_id = %s ORDER BY symbol",
                (user_id,)
            )
            portfolio = cursor.fetchall()
            cursor.close()
            # DEBUG: Show how many portfolio items found
            if portfolio:
                st.sidebar.success(f"📈 Found {len(portfolio)} stocks in portfolio")
            return portfolio
        except Exception as e:
            st.error(f"Error getting portfolio: {e}")
            return []
    
    def delete_portfolio_item(self, user_id, symbol):
        """Delete portfolio item"""
        if not self.connection:
            return False
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "DELETE FROM portfolios WHERE user_id = %s AND symbol = %s",
                (user_id, symbol)
            )
            self.connection.commit()
            cursor.close()
            st.success(f"✅ Removed {symbol} from portfolio")
            return True
        except Exception as e:
            st.error(f"Error deleting portfolio item: {e}")
            return False

class DataProvider:
    def __init__(self):
        # FIXED: Use environment variables properly
        self.alpha_vantage_key = config('ALPHA_VANTAGE_API_KEY', default="0ZL6RBY7H5GO7IH9")
        self.polygon_key = config('POLYGON_API_KEY', default="ERsXTaR8Ltc3E1yR1P4RukMzHsP212NO")
        self.currency_rates = {}
        self.api_call_count = 0
        self.last_api_call = 0
        
        # Debug: Show which API keys are being used
        st.sidebar.info(f"🔑 API Keys: Alpha Vantage ({'✅' if self.alpha_vantage_key else '❌'}), Polygon ({'✅' if self.polygon_key else '❌'})")
        
    def rate_limit_check(self, min_interval=1):
        """Ensure minimum interval between API calls - REDUCED for better UX"""
        current_time = time.time()
        time_since_last = current_time - self.last_api_call
        
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_api_call = time.time()
        self.api_call_count += 1
    
    def get_currency_rates(self):
        """Get current exchange rates with fallback"""
        try:
            response = requests.get(
                "https://api.exchangerate-api.com/v4/latest/USD", 
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                self.currency_rates = data['rates']
                st.success("✅ Currency rates updated")
                return True
        except requests.RequestException:
            st.warning("⚠️ Currency API unavailable, using approximate rates")
        
        # Fallback rates (approximate)
        self.currency_rates = {
            'EUR': 0.85, 'GBP': 0.73, 'CHF': 0.88, 'SEK': 10.5, 
            'NOK': 10.8, 'DKK': 6.4, 'PLN': 4.0, 'CZK': 22.0,
            'CAD': 1.25, 'AUD': 1.35, 'JPY': 110.0, 'CNY': 6.45
        }
        return False
    
    def get_stock_data(self, symbol):
        """Get stock data with ALL APIs working - FIXED order and error handling"""
        
        st.info(f"🔍 Getting data for {symbol}...")
        
        # Try Alpha Vantage FIRST (best for dividend data)
        if self.alpha_vantage_key and self.alpha_vantage_key != "demo":
            try:
                st.info(f"📡 Trying Alpha Vantage for {symbol}...")
                self.rate_limit_check(12)  # Alpha Vantage rate limit
                data = self.get_alpha_vantage_data(symbol)
                if data and data.get('current_price', 0) > 0:
                    st.success(f"✅ Alpha Vantage data retrieved for {symbol}")
                    return data
                else:
                    st.warning(f"⚠️ Alpha Vantage returned no data for {symbol}")
            except Exception as e:
                st.warning(f"❌ Alpha Vantage failed for {symbol}: {str(e)}")
        
        # Try Polygon SECOND
        if self.polygon_key:
            try:
                st.info(f"📡 Trying Polygon for {symbol}...")
                self.rate_limit_check(1)  # Polygon rate limit
                data = self.get_polygon_data(symbol)
                if data and data.get('current_price', 0) > 0:
                    st.success(f"✅ Polygon data retrieved for {symbol}")
                    return data
                else:
                    st.warning(f"⚠️ Polygon returned no data for {symbol}")
            except Exception as e:
                st.warning(f"❌ Polygon failed for {symbol}: {str(e)}")
        
        # Try yfinance LAST (reliable fallback)
        try:
            st.info(f"📡 Trying yfinance for {symbol}...")
            data = self.get_yfinance_data(symbol)
            if data and data.get('current_price', 0) > 0:
                st.success(f"✅ yfinance data retrieved for {symbol}")
                return data
            else:
                st.warning(f"⚠️ yfinance returned no data for {symbol}")
        except Exception as e:
            st.error(f"❌ yfinance failed for {symbol}: {str(e)}")
        
        st.error(f"❌ All data sources failed for {symbol}")
        return None
    
    def get_alpha_vantage_data(self, symbol):
        """Get data from Alpha Vantage - FIXED with better error handling"""
        try:
            if not self.alpha_vantage_key or self.alpha_vantage_key == "demo":
                return None
                
            ts = TimeSeries(key=self.alpha_vantage_key, output_format='pandas')
            data, meta_data = ts.get_daily(symbol=symbol, outputsize='compact')
            
            if data is None or data.empty:
                return None
            
            current_price = float(data.iloc[0]['4. close'])
            
            # Try to get company name from overview
            try:
                overview_url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={symbol}&apikey={self.alpha_vantage_key}"
                overview_response = requests.get(overview_url, timeout=10)
                overview_data = overview_response.json()
                company_name = overview_data.get('Name', symbol)
            except:
                company_name = symbol
            
            return {
                'symbol': symbol,
                'current_price': current_price,
                'currency': 'USD',
                'source': 'Alpha Vantage ✨',
                'company_name': company_name,
                'last_updated': data.index[0].strftime('%Y-%m-%d')
            }
            
        except Exception as e:
            st.warning(f"Alpha Vantage error: {str(e)}")
            return None
    
    def get_polygon_data(self, symbol):
        """Get data from Polygon - FIXED with better error handling"""
        try:
            if not self.polygon_key:
                return None
                
            # Get current price
            url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?adjusted=true&apikey={self.polygon_key}"
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                return None
                
            data = response.json()
            if data.get('resultsCount', 0) == 0:
                return None
                
            result = data['results'][0]
            current_price = float(result['c'])  # Close price
            
            # Try to get company name
            try:
                details_url = f"https://api.polygon.io/v3/reference/tickers/{symbol}?apikey={self.polygon_key}"
                details_response = requests.get(details_url, timeout=10)
                if details_response.status_code == 200:
                    details_data = details_response.json()
                    company_name = details_data.get('results', {}).get('name', symbol)
                else:
                    company_name = symbol
            except:
                company_name = symbol
            
            return {
                'symbol': symbol,
                'current_price': current_price,
                'currency': 'USD',
                'source': 'Polygon 🏢',
                'company_name': company_name
            }
            
        except Exception as e:
            st.warning(f"Polygon error: {str(e)}")
            return None
    
    def get_yfinance_data(self, symbol):
        """Get data from yfinance - ENHANCED with comprehensive dividend data"""
        try:
            stock = yf.Ticker(symbol)
            
            # Get basic info
            info = stock.info
            
            # Validate we got meaningful data
            if not info or len(info) < 5:
                return None
            
            # Get current price with multiple fallbacks
            current_price = (
                info.get('currentPrice') or 
                info.get('regularMarketPrice') or 
                info.get('previousClose') or 
                0
            )
            
            if current_price == 0:
                return None
            
            # ENHANCED DIVIDEND DATA COLLECTION
            dividend_data = {}
            
            # Get dividend history (last 2 years)
            try:
                dividends = stock.dividends.tail(8)  # Last 8 payments
                if not dividends.empty:
                    last_dividend = dividends.iloc[-1]
                    dividend_data['last_dividend'] = float(last_dividend)
                    dividend_data['last_dividend_date'] = dividends.index[-1].strftime('%Y-%m-%d')
                    
                    # Calculate annual dividend (sum of last 4 quarters or 1 year)
                    recent_year_dividends = dividends.last('365D').sum()
                    dividend_data['annual_dividend'] = float(recent_year_dividends)
                    
                    # Dividend frequency
                    dividend_data['payment_count'] = len(dividends)
                    
                    # Dividend yield calculation
                    if current_price > 0:
                        dividend_data['yield_percent'] = (recent_year_dividends / current_price) * 100
                else:
                    dividend_data = {'status': 'No dividend history found'}
            except Exception as e:
                dividend_data = {'status': f'Dividend data error: {str(e)}'}
            
            # Get additional dividend info from company info
            dividend_yield = info.get('dividendYield')
            if dividend_yield:
                dividend_data['company_reported_yield'] = dividend_yield * 100
            
            dividend_rate = info.get('dividendRate')
            if dividend_rate:
                dividend_data['company_reported_rate'] = dividend_rate
            
            ex_dividend_date = info.get('exDividendDate')
            if ex_dividend_date:
                dividend_data['ex_dividend_date'] = datetime.fromtimestamp(ex_dividend_date).strftime('%Y-%m-%d')
            
            # Format dividend info for display
            if dividend_data.get('annual_dividend', 0) > 0:
                annual_div = dividend_data['annual_dividend']
                yield_pct = dividend_data.get('yield_percent', 0)
                currency = info.get('currency', 'USD')
                
                if currency == 'GBP':
                    dividend_info = f"Annual: {annual_div:.1f}p (Yield: {yield_pct:.2f}%)"
                else:
                    dividend_info = f"Annual: {currency} {annual_div:.2f} (Yield: {yield_pct:.2f}%)"
                
                if dividend_data.get('last_dividend_date'):
                    dividend_info += f" | Last: {dividend_data['last_dividend_date']}"
            else:
                dividend_info = dividend_data.get('status', 'No recent dividends')
            
            return {
                'symbol': symbol,
                'current_price': float(current_price),
                'currency': info.get('currency', 'USD'),
                'dividends': dividends if 'dividends' in locals() else pd.Series(),
                'dividend_data': dividend_data,
                'dividend_info': dividend_info,
                'info': info,
                'source': 'yfinance 📊',
                'company_name': info.get('longName', info.get('shortName', symbol))
            }
            
        except Exception as e:
            st.warning(f"yfinance error: {str(e)}")
            return None

class ProfessionalDividendTracker:
    def __init__(self):
        self.db = DatabaseManager()
        self.data_provider = DataProvider()
        
    def detect_currency_and_market(self, ticker, info=None):
        """Detect currency and market based on ticker"""
        market_info = {
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
        
        for suffix, market_data in market_info.items():
            if ticker.endswith(suffix):
                return market_data['market'], market_data['country'], market_data.get('currency', 'USD')
        
        return 'US Market (NASDAQ/NYSE)', 'US', 'USD'
    
    def format_currency(self, amount, currency, is_uk_stock=False):
        """Format amount with appropriate currency symbol - FIXED for UK pence"""
        if not isinstance(amount, (int, float)):
            return str(amount)
        
        # Handle UK stocks priced in pence
        if currency == 'GBP' and is_uk_stock:
            return f"{amount:.2f}p"  # Show as pence for UK stocks
        
        symbols = {
            'USD': '$'
        }

# Initialize the tracker - FIXED for older Streamlit versions
@st.cache(allow_output_mutation=True)
def get_tracker():
    return ProfessionalDividendTracker()

tracker = get_tracker()

def login_page():
    """Display login page"""
    st.markdown("<div class='login-container'>", unsafe_allow_html=True)
    
    st.title("🔐 Login")
    
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    with tab1:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")
            
            if submit and username and password:
                user = tracker.db.get_user(username)
                if user and tracker.db.verify_password(password, user['password_hash']):
                    st.session_state.authenticated = True
                    st.session_state.user_id = user['id']
                    st.session_state.username = user['username']
                    st.success("✅ Login successful!")
                    time.sleep(1)  # Brief pause to show success
                    st.rerun()
                else:
                    st.error("❌ Invalid username or password")
    
    with tab2:
        with st.form("signup_form"):
            new_username = st.text_input("Choose Username")
            new_email = st.text_input("Email (optional)")
            new_password = st.text_input("Choose Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            signup = st.form_submit_button("Sign Up")
            
            if signup and new_username and new_password:
                if new_password != confirm_password:
                    st.error("❌ Passwords don't match")
                elif len(new_password) < 6:
                    st.error("❌ Password must be at least 6 characters")
                elif tracker.db.get_user(new_username):
                    st.error("❌ Username already exists")
                else:
                    if tracker.db.create_user(new_username, new_password, new_email):
                        st.success("✅ Account created! Please login.")
                    else:
                        st.error("❌ Error creating account")
    
    st.markdown("</div>", unsafe_allow_html=True)

def main_app():
    """Main application interface"""
    st.title("💰 Professional Dividend Tracker")
    st.markdown(f"**Welcome, {st.session_state.username}!**")
    
    # Logout button in sidebar
    with st.sidebar:
        if st.button("🚪 Logout"):
            for key in ['authenticated', 'user_id', 'username']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
    
    # Portfolio management in sidebar
    st.sidebar.header("📊 Portfolio Management")
    
    # FIXED: Force refresh portfolio data
    if 'portfolio_refresh' not in st.session_state:
        st.session_state.portfolio_refresh = 0
    
    # Load existing portfolio with debug info
    portfolio = tracker.db.get_portfolio(st.session_state.user_id)
    
    # Add stock form
    with st.sidebar.form("add_stock_form"):
        st.subheader("➕ Add Stock")
        
        symbol = st.text_input(
            "Stock Symbol", 
            placeholder="e.g., AAPL, RIO.L, LR.PA, ASML",
            help="Use Yahoo Finance format"
        ).upper().strip()
        
        shares = st.number_input("Number of Shares", min_value=0.001, value=1.0, step=1.0, format="%.3f")
        
        submitted = st.form_submit_button("Add to Portfolio")
        
        if submitted and symbol:
            success = tracker.db.save_portfolio(st.session_state.user_id, symbol, shares)
            if success:
                st.session_state.portfolio_refresh += 1  # Force refresh
                time.sleep(0.5)  # Brief pause
                st.rerun()
            else:
                st.error("❌ Error saving to portfolio")
    
    # Display current portfolio - FIXED to show all stocks
    if portfolio:
        st.sidebar.subheader(f"📋 Current Portfolio ({len(portfolio)} stocks)")
        for item in portfolio:
            col1, col2 = st.sidebar.columns([3, 1])
            col1.text(f"{item['symbol']}: {float(item['shares']):.1f} shares")
            if col2.button("🗑️", key=f"remove_{item['symbol']}", help=f"Remove {item['symbol']}"):
                if tracker.db.delete_portfolio_item(st.session_state.user_id, item['symbol']):
                    st.session_state.portfolio_refresh += 1  # Force refresh
                    time.sleep(0.5)
                    st.rerun()
    else:
        st.sidebar.info("No stocks in portfolio yet")
    
    # Market examples
    with st.sidebar.expander("🔍 Market Examples"):
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
    
    # Main content area
    if not portfolio:
        st.info("👆 Add stocks to your portfolio using the sidebar to get started!")
        
        # Show example
        st.subheader("📱 Example Usage")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**US Stock:**\n- Symbol: `AAPL`\n- Shares: `10`")
        with col2:
            st.markdown("**UK Stock:**\n- Symbol: `RIO.L`\n- Shares: `25`")
        with col3:
            st.markdown("**European Stock:**\n- Symbol: `ASML`\n- Shares: `5`")
    else:
        # Display portfolio count - FIXED
        st.info(f"📈 You have {len(portfolio)} stocks in your portfolio. Click 'Analyze Portfolio' to get current data!")
        
        # Analyze portfolio button
        if st.button("🔍 Analyze Portfolio", type="primary"):
            with st.spinner("Getting exchange rates..."):
                tracker.data_provider.get_currency_rates()
            
            # Progress bar
            progress_bar = st.progress(0)
            results = []
            
            st.subheader("🔄 Analysis Progress")
            
            for i, item in enumerate(portfolio):
                st.write(f"**{i+1}/{len(portfolio)}** - Analyzing {item['symbol']}...")
                
                # Get stock data using professional data sources
                stock_data = tracker.data_provider.get_stock_data(item['symbol'])
                
                if stock_data:
                    market, country, currency = tracker.detect_currency_and_market(item['symbol'])
                    
                    # Override currency if we got it from API
                    if 'currency' in stock_data:
                        currency = stock_data['currency']
                    
                    # Calculate position value
                    current_price_num = stock_data.get('current_price', 0)
                    position_value = float(item['shares']) * current_price_num
                    
                    result = {
                        'symbol': item['symbol'],
                        'shares': float(item['shares']),
                        'company_name': stock_data.get('company_name', item['symbol'])[:40],
                        'market': market,
                        'country': country,
                        'currency': currency,
                        'current_price': tracker.format_currency(current_price_num, currency),
                        'position_value': tracker.format_currency(position_value, currency),
                        'dividend_info': stock_data.get('dividend_info', 'No dividend data'),
                        'data_source': stock_data.get('source', 'Unknown'),
                        'status': '✅ Success'
                    }
                else:
                    result = {
                        'symbol': item['symbol'],
                        'shares': float(item['shares']),
                        'company_name': 'Data unavailable',
                        'status': '❌ Failed to retrieve data',
                        'data_source': 'All sources failed'
                    }
                
                results.append(result)
                progress_bar.progress((i + 1) / len(portfolio))
            
            # Store results
            st.session_state.analysis_results = results
            st.balloons()  # Celebration animation
            st.success(f"✅ Analysis complete! Processed {len(results)} stocks successfully.")
        
        # Display results if available
        if 'analysis_results' in st.session_state:
            results = st.session_state.analysis_results
            
            # Summary metrics - ENHANCED
            st.subheader("📊 Portfolio Summary")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Stocks", len(results))
            with col2:
                successful = sum(1 for r in results if r.get('status') == '✅ Success')
                st.metric("Data Retrieved", f"{successful}/{len(results)}")
            with col3:
                sources = [r.get('data_source', 'Unknown') for r in results if r.get('data_source') and 'failed' not in r.get('data_source', '').lower()]
                unique_sources = len(set(sources))
                st.metric("Active Data Sources", unique_sources)
            with col4:
                total_positions = len([r for r in results if r.get('position_value')])
                st.metric("Valued Positions", total_positions)
            
            # Results table - ENHANCED with better formatting
            st.subheader("💼 Portfolio Details")
            
            if results:
                # Separate successful and failed results
                successful_results = [r for r in results if r.get('status') == '✅ Success']
                failed_results = [r for r in results if r.get('status') != '✅ Success']
                
                if successful_results:
                    # Create display table for successful results
                    display_data = []
                    for result in successful_results:
                        display_data.append({
                            'Symbol': result['symbol'],
                            'Company': result.get('company_name', 'N/A'),
                            'Shares': f"{result['shares']:.1f}",
                            'Market': result.get('country', 'N/A'),
                            'Currency': result.get('currency', 'N/A'),
                            'Current Price': result.get('current_price', 'N/A'),
                            'Position Value': result.get('position_value', 'N/A'),
                            'Dividend Info': result.get('dividend_info', 'N/A'),
                            'Data Source': result.get('data_source', 'N/A')
                        })
                    
                    df_display = pd.DataFrame(display_data)
                    st.dataframe(df_display, use_container_width=True, height=400)
                    
                    # Calculate total portfolio value (USD equivalent)
                    if tracker.data_provider.currency_rates:
                        total_usd = 0
                        currency_breakdown = {}
                        
                        for result in successful_results:
                            if result.get('position_value') and result.get('currency'):
                                # Extract numeric value from formatted string
                                value_str = str(result['position_value']).replace(', '').replace('EUR', '').replace('GBP', '').replace('C, '').replace('A, '').replace(',', '').strip()
                                try:
                                    value = float(value_str)
                                    currency = result['currency']
                                    
                                    # Convert to USD
                                    if currency == 'USD':
                                        usd_value = value
                                    else:
                                        rate = tracker.data_provider.currency_rates.get(currency, 1)
                                        usd_value = value / rate
                                    
                                    total_usd += usd_value
                                    
                                    # Track by currency
                                    if currency not in currency_breakdown:
                                        currency_breakdown[currency] = 0
                                    currency_breakdown[currency] += value
                                    
                                except:
                                    pass
                        
                        # Display totals
                        st.subheader("💰 Portfolio Valuation")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.metric("Total Value (USD)", f"${total_usd:,.2f}")
                        
                        with col2:
                            if len(currency_breakdown) > 1:
                                breakdown_text = " | ".join([f"{curr}: {tracker.format_currency(val, curr)}" for curr, val in currency_breakdown.items()])
                                st.metric("Currency Breakdown", breakdown_text)
                
                if failed_results:
                    st.subheader("⚠️ Stocks with Data Issues")
                    for result in failed_results:
                        st.warning(f"**{result['symbol']}** ({result['shares']} shares) - {result.get('data_source', 'Failed')}")
                
                # Show data source breakdown
                st.subheader("📡 Data Source Performance")
                source_counts = {}
                for result in successful_results:
                    source = result.get('data_source', 'Unknown')
                    source_counts[source] = source_counts.get(source, 0) + 1
                
                if source_counts:
                    for source, count in source_counts.items():
                        st.info(f"**{source}**: Retrieved data for {count} stocks")
            
            # Export functionality - ENHANCED
            st.subheader("📥 Export Portfolio")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # Excel export with timestamp
                buffer = io.BytesIO()
                timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
                
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    # Portfolio sheet
                    df_results = pd.DataFrame(results)
                    df_results.to_excel(writer, index=False, sheet_name='Portfolio_Analysis')
                    
                    # Summary sheet
                    summary_data = {
                        'Total Stocks': [len(results)],
                        'Successful Retrievals': [sum(1 for r in results if r.get('status') == '✅ Success')],
                        'Analysis Date': [datetime.now().strftime('%Y-%m-%d %H:%M')],
                        'User': [st.session_state.username]
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
                csv = pd.DataFrame(results).to_csv(index=False)
                st.download_button(
                    label="📄 Download CSV",
                    data=csv,
                    file_name=f"portfolio_analysis_{timestamp}.csv",
                    mime="text/csv"
                )
            
            with col3:
                # Clear results button
                if st.button("🔄 Clear Results"):
                    if 'analysis_results' in st.session_state:
                        del st.session_state.analysis_results
                    st.rerun()

def main():
    """Main application entry point"""
    # Initialize authentication state
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    # Show login or main app
    if not st.session_state.authenticated:
        login_page()
    else:
        main_app()

if __name__ == "__main__":
    main(), 'EUR': 'EUR', 'GBP': 'GBP', 'CHF': 'CHF', 
            'SEK': 'SEK', 'NOK': 'NOK', 'DKK': 'DKK', 'CAD': 'CAD', 'AUD': 'AUD'
        }
        
        symbol = symbols.get(currency, currency)
        
        if currency in ['EUR', 'GBP', 'CHF', 'SEK', 'NOK', 'DKK', 'CAD', 'AUD']:
            return f"{symbol} {amount:.2f}"
        else:
            return f"{symbol}{amount:.2f}"

# Initialize the tracker
@st.cache_resource
def get_tracker():
    return ProfessionalDividendTracker()

tracker = get_tracker()

def login_page():
    """Display login page"""
    st.markdown("<div class='login-container'>", unsafe_allow_html=True)
    
    st.title("🔐 Login")
    
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    with tab1:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")
            
            if submit and username and password:
                user = tracker.db.get_user(username)
                if user and tracker.db.verify_password(password, user['password_hash']):
                    st.session_state.authenticated = True
                    st.session_state.user_id = user['id']
                    st.session_state.username = user['username']
                    st.success("✅ Login successful!")
                    time.sleep(1)  # Brief pause to show success
                    st.rerun()
                else:
                    st.error("❌ Invalid username or password")
    
    with tab2:
        with st.form("signup_form"):
            new_username = st.text_input("Choose Username")
            new_email = st.text_input("Email (optional)")
            new_password = st.text_input("Choose Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            signup = st.form_submit_button("Sign Up")
            
            if signup and new_username and new_password:
                if new_password != confirm_password:
                    st.error("❌ Passwords don't match")
                elif len(new_password) < 6:
                    st.error("❌ Password must be at least 6 characters")
                elif tracker.db.get_user(new_username):
                    st.error("❌ Username already exists")
                else:
                    if tracker.db.create_user(new_username, new_password, new_email):
                        st.success("✅ Account created! Please login.")
                    else:
                        st.error("❌ Error creating account")
    
    st.markdown("</div>", unsafe_allow_html=True)

def main_app():
    """Main application interface"""
    st.title("💰 Professional Dividend Tracker")
    st.markdown(f"**Welcome, {st.session_state.username}!**")
    
    # Logout button in sidebar
    with st.sidebar:
        if st.button("🚪 Logout"):
            for key in ['authenticated', 'user_id', 'username']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
    
    # Portfolio management in sidebar
    st.sidebar.header("📊 Portfolio Management")
    
    # FIXED: Force refresh portfolio data
    if 'portfolio_refresh' not in st.session_state:
        st.session_state.portfolio_refresh = 0
    
    # Load existing portfolio with debug info
    portfolio = tracker.db.get_portfolio(st.session_state.user_id)
    
    # Add stock form
    with st.sidebar.form("add_stock_form"):
        st.subheader("➕ Add Stock")
        
        symbol = st.text_input(
            "Stock Symbol", 
            placeholder="e.g., AAPL, RIO.L, LR.PA, ASML",
            help="Use Yahoo Finance format"
        ).upper().strip()
        
        shares = st.number_input("Number of Shares", min_value=0.001, value=1.0, step=1.0, format="%.3f")
        
        submitted = st.form_submit_button("Add to Portfolio")
        
        if submitted and symbol:
            success = tracker.db.save_portfolio(st.session_state.user_id, symbol, shares)
            if success:
                st.session_state.portfolio_refresh += 1  # Force refresh
                time.sleep(0.5)  # Brief pause
                st.rerun()
            else:
                st.error("❌ Error saving to portfolio")
    
    # Display current portfolio - FIXED to show all stocks
    if portfolio:
        st.sidebar.subheader(f"📋 Current Portfolio ({len(portfolio)} stocks)")
        for item in portfolio:
            col1, col2 = st.sidebar.columns([3, 1])
            col1.text(f"{item['symbol']}: {float(item['shares']):.1f} shares")
            if col2.button("🗑️", key=f"remove_{item['symbol']}", help=f"Remove {item['symbol']}"):
                if tracker.db.delete_portfolio_item(st.session_state.user_id, item['symbol']):
                    st.session_state.portfolio_refresh += 1  # Force refresh
                    time.sleep(0.5)
                    st.rerun()
    else:
        st.sidebar.info("No stocks in portfolio yet")
    
    # Market examples
    with st.sidebar.expander("🔍 Market Examples"):
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
    
    # Main content area
    if not portfolio:
        st.info("👆 Add stocks to your portfolio using the sidebar to get started!")
        
        # Show example
        st.subheader("📱 Example Usage")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**US Stock:**\n- Symbol: `AAPL`\n- Shares: `10`")
        with col2:
            st.markdown("**UK Stock:**\n- Symbol: `RIO.L`\n- Shares: `25`")
        with col3:
            st.markdown("**European Stock:**\n- Symbol: `ASML`\n- Shares: `5`")
    else:
        # Display portfolio count - FIXED
        st.info(f"📈 You have {len(portfolio)} stocks in your portfolio. Click 'Analyze Portfolio' to get current data!")
        
        # Analyze portfolio button
        if st.button("🔍 Analyze Portfolio", type="primary"):
            with st.spinner("Getting exchange rates..."):
                tracker.data_provider.get_currency_rates()
            
            # Progress bar
            progress_bar = st.progress(0)
            results = []
            
            st.subheader("🔄 Analysis Progress")
            
            for i, item in enumerate(portfolio):
                st.write(f"**{i+1}/{len(portfolio)}** - Analyzing {item['symbol']}...")
                
                # Get stock data using professional data sources
                stock_data = tracker.data_provider.get_stock_data(item['symbol'])
                
                if stock_data:
                    market, country, currency = tracker.detect_currency_and_market(item['symbol'])
                    
                    # Override currency if we got it from API
                    if 'currency' in stock_data:
                        currency = stock_data['currency']
                    
                    # Calculate position value
                    current_price_num = stock_data.get('current_price', 0)
                    position_value = float(item['shares']) * current_price_num
                    
                    result = {
                        'symbol': item['symbol'],
                        'shares': float(item['shares']),
                        'company_name': stock_data.get('company_name', item['symbol'])[:40],
                        'market': market,
                        'country': country,
                        'currency': currency,
                        'current_price': tracker.format_currency(current_price_num, currency),
                        'position_value': tracker.format_currency(position_value, currency),
                        'dividend_info': stock_data.get('dividend_info', 'No dividend data'),
                        'data_source': stock_data.get('source', 'Unknown'),
                        'status': '✅ Success'
                    }
                else:
                    result = {
                        'symbol': item['symbol'],
                        'shares': float(item['shares']),
                        'company_name': 'Data unavailable',
                        'status': '❌ Failed to retrieve data',
                        'data_source': 'All sources failed'
                    }
                
                results.append(result)
                progress_bar.progress((i + 1) / len(portfolio))
            
            # Store results
            st.session_state.analysis_results = results
            st.balloons()  # Celebration animation
            st.success(f"✅ Analysis complete! Processed {len(results)} stocks successfully.")
        
        # Display results if available
        if 'analysis_results' in st.session_state:
            results = st.session_state.analysis_results
            
            # Summary metrics - ENHANCED
            st.subheader("📊 Portfolio Summary")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Stocks", len(results))
            with col2:
                successful = sum(1 for r in results if r.get('status') == '✅ Success')
                st.metric("Data Retrieved", f"{successful}/{len(results)}")
            with col3:
                sources = [r.get('data_source', 'Unknown') for r in results if r.get('data_source') and 'failed' not in r.get('data_source', '').lower()]
                unique_sources = len(set(sources))
                st.metric("Active Data Sources", unique_sources)
            with col4:
                total_positions = len([r for r in results if r.get('position_value')])
                st.metric("Valued Positions", total_positions)
            
            # Results table - ENHANCED with better formatting
            st.subheader("💼 Portfolio Details")
            
            if results:
                # Separate successful and failed results
                successful_results = [r for r in results if r.get('status') == '✅ Success']
                failed_results = [r for r in results if r.get('status') != '✅ Success']
                
                if successful_results:
                    # Create display table for successful results
                    display_data = []
                    for result in successful_results:
                        display_data.append({
                            'Symbol': result['symbol'],
                            'Company': result.get('company_name', 'N/A'),
                            'Shares': f"{result['shares']:.1f}",
                            'Market': result.get('country', 'N/A'),
                            'Currency': result.get('currency', 'N/A'),
                            'Current Price': result.get('current_price', 'N/A'),
                            'Position Value': result.get('position_value', 'N/A'),
                            'Dividend Info': result.get('dividend_info', 'N/A'),
                            'Data Source': result.get('data_source', 'N/A')
                        })
                    
                    df_display = pd.DataFrame(display_data)
                    st.dataframe(df_display, use_container_width=True, height=400)
                    
                    # Calculate total portfolio value (USD equivalent)
                    if tracker.data_provider.currency_rates:
                        total_usd = 0
                        currency_breakdown = {}
                        
                        for result in successful_results:
                            if result.get('position_value') and result.get('currency'):
                                # Extract numeric value from formatted string
                                value_str = str(result['position_value']).replace(', '').replace('€', '').replace('£', '').replace('C, '').replace('A, '').replace(',', '')
                                try:
                                    value = float(value_str)
                                    currency = result['currency']
                                    
                                    # Convert to USD
                                    if currency == 'USD':
                                        usd_value = value
                                    else:
                                        rate = tracker.data_provider.currency_rates.get(currency, 1)
                                        usd_value = value / rate
                                    
                                    total_usd += usd_value
                                    
                                    # Track by currency
                                    if currency not in currency_breakdown:
                                        currency_breakdown[currency] = 0
                                    currency_breakdown[currency] += value
                                    
                                except:
                                    pass
                        
                        # Display totals
                        st.subheader("💰 Portfolio Valuation")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.metric("Total Value (USD)", f"${total_usd:,.2f}")
                        
                        with col2:
                            if len(currency_breakdown) > 1:
                                breakdown_text = " | ".join([f"{curr}: {tracker.format_currency(val, curr)}" for curr, val in currency_breakdown.items()])
                                st.metric("Currency Breakdown", breakdown_text)
                
                if failed_results:
                    st.subheader("⚠️ Stocks with Data Issues")
                    for result in failed_results:
                        st.warning(f"**{result['symbol']}** ({result['shares']} shares) - {result.get('data_source', 'Failed')}")
                
                # Show data source breakdown
                st.subheader("📡 Data Source Performance")
                source_counts = {}
                for result in successful_results:
                    source = result.get('data_source', 'Unknown')
                    source_counts[source] = source_counts.get(source, 0) + 1
                
                if source_counts:
                    for source, count in source_counts.items():
                        st.info(f"**{source}**: Retrieved data for {count} stocks")
            
            # Export functionality - ENHANCED
            st.subheader("📥 Export Portfolio")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # Excel export with timestamp
                buffer = io.BytesIO()
                timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
                
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    # Portfolio sheet
                    df_results = pd.DataFrame(results)
                    df_results.to_excel(writer, index=False, sheet_name='Portfolio_Analysis')
                    
                    # Summary sheet
                    summary_data = {
                        'Total Stocks': [len(results)],
                        'Successful Retrievals': [sum(1 for r in results if r.get('status') == '✅ Success')],
                        'Analysis Date': [datetime.now().strftime('%Y-%m-%d %H:%M')],
                        'User': [st.session_state.username]
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
                csv = pd.DataFrame(results).to_csv(index=False)
                st.download_button(
                    label="📄 Download CSV",
                    data=csv,
                    file_name=f"portfolio_analysis_{timestamp}.csv",
                    mime="text/csv"
                )
            
            with col3:
                # Clear results button
                if st.button("🔄 Clear Results"):
                    if 'analysis_results' in st.session_state:
                        del st.session_state.analysis_results
                    st.rerun()

def main():
    """Main application entry point"""
    # Initialize authentication state
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    # Show login or main app
    if not st.session_state.authenticated:
        login_page()
    else:
        main_app()

if __name__ == "__main__":
    main()

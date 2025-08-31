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
            else:
                # Fallback for local development
                self.connection = psycopg2.connect(
                    host=config('DB_HOST', default='localhost'),
                    database=config('DB_NAME', default='dividend_tracker'),
                    user=config('DB_USER', default='postgres'),
                    password=config('DB_PASSWORD', default='password')
                )
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
            
            # Portfolios table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolios (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    symbol VARCHAR(20) NOT NULL,
                    shares DECIMAL(10,4) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        except Exception as e:
            st.error(f"Error creating tables: {e}")
    
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
            return False
        
        try:
            cursor = self.connection.cursor()
            # Update if exists, insert if not
            cursor.execute("""
                INSERT INTO portfolios (user_id, symbol, shares, updated_at) 
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id, symbol) 
                DO UPDATE SET shares = %s, updated_at = CURRENT_TIMESTAMP
            """, (user_id, symbol, shares, shares))
            
            self.connection.commit()
            cursor.close()
            return True
        except Exception as e:
            st.error(f"Error saving portfolio: {e}")
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
            return True
        except Exception as e:
            st.error(f"Error deleting portfolio item: {e}")
            return False

class DataProvider:
    def __init__(self):
        self.alpha_vantage_key = "0ZL6RBY7H5GO7IH9"
        self.polygon_key = "ERsXTaR8Ltc3E1yR1P4RukMzHsP212NO"
        self.currency_rates = {}
        
    def get_currency_rates(self):
        """Get current exchange rates"""
        try:
            response = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.currency_rates = data['rates']
                return True
        except:
            pass
        
        # Fallback rates
        self.currency_rates = {
            'EUR': 0.85, 'GBP': 0.73, 'CHF': 0.88, 'SEK': 10.5, 
            'NOK': 10.8, 'DKK': 6.4, 'PLN': 4.0, 'CZK': 22.0
        }
        return False
    
    def get_stock_data(self, symbol):
        """Get stock data with fallback chain"""
        
        # Try Alpha Vantage first
        try:
            data = self.get_alpha_vantage_data(symbol)
            if data:
                return data
        except Exception as e:
            st.warning(f"Alpha Vantage failed for {symbol}: {str(e)}")
        
        # Try Polygon as backup
        try:
            data = self.get_polygon_data(symbol)
            if data:
                return data
        except Exception as e:
            st.warning(f"Polygon failed for {symbol}: {str(e)}")
        
        # Fall back to yfinance
        try:
            return self.get_yfinance_data(symbol)
        except Exception as e:
            st.error(f"All data sources failed for {symbol}: {str(e)}")
            return None
    
    def get_alpha_vantage_data(self, symbol):
        """Get data from Alpha Vantage"""
        try:
            ts = TimeSeries(key=self.alpha_vantage_key, output_format='pandas')
            data, meta_data = ts.get_daily(symbol=symbol)
            
            if data.empty:
                return None
            
            # Get basic info
            current_price = data.iloc[0]['4. close']
            
            # Try to get dividend data
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={self.alpha_vantage_key}"
            response = requests.get(url)
            
            if response.status_code == 200:
                return {
                    'symbol': symbol,
                    'current_price': current_price,
                    'currency': 'USD',  # Default, should be enhanced
                    'source': 'Alpha Vantage'
                }
        except Exception:
            return None
        
        return None
    
    def get_polygon_data(self, symbol):
        """Get data from Polygon"""
        try:
            url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?adjusted=true&apikey={self.polygon_key}"
            response = requests.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if data['resultsCount'] > 0:
                    result = data['results'][0]
                    return {
                        'symbol': symbol,
                        'current_price': result['c'],  # Close price
                        'currency': 'USD',
                        'source': 'Polygon'
                    }
        except Exception:
            return None
        
        return None
    
    def get_yfinance_data(self, symbol):
        """Get data from yfinance (fallback)"""
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            dividends = stock.dividends
            
            return {
                'symbol': symbol,
                'current_price': info.get('currentPrice', info.get('regularMarketPrice', 0)),
                'currency': info.get('currency', 'USD'),
                'dividends': dividends,
                'info': info,
                'source': 'yfinance'
            }
        except Exception:
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
        }
        
        for suffix, market_data in market_info.items():
            if ticker.endswith(suffix):
                return market_data['market'], market_data['country'], market_data.get('currency', 'USD')
        
        return 'US Market (NASDAQ/NYSE)', 'US', 'USD'
    
    def format_currency(self, amount, currency, is_uk_price=False, is_uk_dividend=False):
        """Format amount with appropriate currency symbol"""
        if not isinstance(amount, (int, float)):
            return str(amount)
        
        if currency == 'GBP' and is_uk_price:
            return f"{amount:.2f}p"
        
        if currency == 'GBP' and is_uk_dividend:
            amount_in_pounds = amount / 100
            return f"GBP {amount_in_pounds:.2f}"
        
        symbols = {
            'USD': '$', 'EUR': 'EUR', 'GBP': 'GBP', 'CHF': 'CHF', 
            'SEK': 'SEK', 'NOK': 'NOK', 'DKK': 'DKK'
        }
        
        symbol = symbols.get(currency, currency)
        if currency == 'GBP':
            return f"GBP {amount:.2f}"
        elif currency == 'EUR':
            return f"EUR {amount:.2f}"
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
                    st.rerun()
                else:
                    st.error("Invalid username or password")
    
    with tab2:
        with st.form("signup_form"):
            new_username = st.text_input("Choose Username")
            new_email = st.text_input("Email (optional)")
            new_password = st.text_input("Choose Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            signup = st.form_submit_button("Sign Up")
            
            if signup and new_username and new_password:
                if new_password != confirm_password:
                    st.error("Passwords don't match")
                elif len(new_password) < 6:
                    st.error("Password must be at least 6 characters")
                elif tracker.db.get_user(new_username):
                    st.error("Username already exists")
                else:
                    if tracker.db.create_user(new_username, new_password, new_email):
                        st.success("Account created! Please login.")
                    else:
                        st.error("Error creating account")
    
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
    
    # Load existing portfolio
    portfolio = tracker.db.get_portfolio(st.session_state.user_id)
    
    # Add stock form
    with st.sidebar.form("add_stock_form"):
        st.subheader("➕ Add Stock")
        
        symbol = st.text_input(
            "Stock Symbol", 
            placeholder="e.g., AAPL, RIO.L, LR.PA, ASML",
            help="Use Yahoo Finance format"
        ).upper().strip()
        
        shares = st.number_input("Number of Shares", min_value=0.1, value=1.0, step=1.0)
        
        submitted = st.form_submit_button("Add to Portfolio")
        
        if submitted and symbol:
            if tracker.db.save_portfolio(st.session_state.user_id, symbol, shares):
                st.success(f"Added {shares} shares of {symbol}")
                st.rerun()
            else:
                st.error("Error saving to portfolio")
    
    # Display current portfolio
    if portfolio:
        st.sidebar.subheader("📋 Current Portfolio")
        for item in portfolio:
            col1, col2 = st.sidebar.columns([3, 1])
            col1.text(f"{item['symbol']}: {item['shares']} shares")
            if col2.button("🗑️", key=f"remove_{item['symbol']}", help="Remove"):
                if tracker.db.delete_portfolio_item(st.session_state.user_id, item['symbol']):
                    st.rerun()
    
    # Market examples
    with st.sidebar.expander("📍 Market Examples"):
        st.markdown("""
        **US Markets:** AAPL, MSFT, JNJ, PG  
        **UK (.L):** SHEL.L, BP.L, RIO.L  
        **France (.PA):** MC.PA, OR.PA, LR.PA  
        **Germany (.DE):** SAP, BMW.DE  
        **Netherlands:** ASML, HEIA.AS  
        **Switzerland (.SW):** NESN.SW  
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
        # Analyze portfolio button
        if st.button("🔍 Analyze Portfolio", type="primary"):
            with st.spinner("Getting exchange rates..."):
                tracker.data_provider.get_currency_rates()
            
            # Progress bar
            progress_bar = st.progress(0)
            results = []
            
            for i, item in enumerate(portfolio):
                with st.spinner(f"Analyzing {item['symbol']}..."):
                    # Get stock data using professional data sources
                    stock_data = tracker.data_provider.get_stock_data(item['symbol'])
                    
                    if stock_data:
                        market, country, currency = tracker.detect_currency_and_market(item['symbol'])
                        
                        # Build result with available data
                        result = {
                            'symbol': item['symbol'],
                            'shares': item['shares'],
                            'company_name': stock_data.get('info', {}).get('longName', item['symbol']),
                            'market': market,
                            'country': country,
                            'currency': currency,
                            'current_price': tracker.format_currency(
                                stock_data.get('current_price', 0), 
                                currency, 
                                is_uk_price=(currency=='GBP')
                            ),
                            'data_source': stock_data.get('source', 'Unknown'),
                            'status': 'Data retrieved successfully'
                        }
                    else:
                        result = {
                            'symbol': item['symbol'],
                            'shares': item['shares'],
                            'status': 'Unable to retrieve data',
                            'data_source': 'None - all sources failed'
                        }
                    
                    results.append(result)
                    progress_bar.progress((i + 1) / len(portfolio))
            
            # Store results
            st.session_state.analysis_results = results
            st.success("✅ Analysis complete!")
        
        # Display results if available
        if 'analysis_results' in st.session_state:
            results = st.session_state.analysis_results
            
            # Summary metrics
            st.subheader("📊 Portfolio Summary")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Stocks", len(results))
            with col2:
                successful = sum(1 for r in results if r.get('status') != 'Unable to retrieve data')
                st.metric("Data Retrieved", successful)
            with col3:
                sources = set(r.get('data_source', 'Unknown') for r in results if r.get('data_source'))
                st.metric("Data Sources", len(sources))
            with col4:
                st.metric("Database Status", "✅ Connected" if tracker.db.connection else "❌ Disconnected")
            
            # Results table
            st.subheader("💼 Portfolio Details")
            
            if results:
                # Create vertical table
                table_data = {}
                
                for result in results:
                    symbol = result['symbol']
                    table_data[symbol] = {
                        'Company': result.get('company_name', 'N/A')[:30],
                        'Market': result.get('country', 'N/A'),
                        'Currency': result.get('currency', 'N/A'),
                        'Shares Owned': str(result.get('shares', 'N/A')),
                        'Current Price': result.get('current_price', 'N/A'),
                        'Status': result.get('status', 'N/A'),
                        'Data Source': result.get('data_source', 'N/A')
                    }
                
                if table_data:
                    df_vertical = pd.DataFrame(table_data)
                    st.dataframe(df_vertical, use_container_width=True, height=400)
                    
                    st.info("📊 Professional data sources with automatic failover for maximum reliability!")
            
            # Export functionality
            st.subheader("📥 Export Portfolio")
            col1, col2 = st.columns(2)
            
            with col1:
                # Excel export
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    pd.DataFrame(results).to_excel(writer, index=False, sheet_name='Portfolio_Analysis')
                
                st.download_button(
                    label="📊 Download Excel",
                    data=buffer.getvalue(),
                    file_name=f"portfolio_analysis_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            with col2:
                # CSV export
                csv = pd.DataFrame(results).to_csv(index=False)
                st.download_button(
                    label="📄 Download CSV",
                    data=csv,
                    file_name=f"portfolio_analysis_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )

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

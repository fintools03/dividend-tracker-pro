# dividend_tracker.py - Clean Version with Yahoo Finance
import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt
from decouple import config
import yfinance as yf
import pandas as pd
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="Dividend Tracker",
    page_icon="💰",
    layout="wide"
)

class DatabaseManager:
    def __init__(self):
        self.connection = None
        self.connect()
    
    def connect(self):
        """Connect to PostgreSQL database"""
        try:
            database_url = config('DATABASE_URL', default=None)
            if database_url:
                self.connection = psycopg2.connect(database_url)
                st.sidebar.success("Database connected")
            else:
                st.error("No database connection")
                st.stop()
            except Exception as e:
                st.error(f"Database error: {e}")
                st.stop()
    
    def get_user(self, username):
        """Get user by username (case insensitive)"""
        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(%s)", (username,))
            user = cursor.fetchone()
            cursor.close()
            return user
        except Exception as e:
            st.error(f"Error getting user: {e}")
            return None
    
    def create_user(self, username, password, email=None):
        """Create new user"""
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
        """Verify password"""
        return bcrypt.checkpw(password.encode('utf-8'), hash_password.encode('utf-8'))
    
    def add_stock(self, user_id, symbol, shares):
        """Add stock to portfolio"""
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
            st.error(f"Error adding stock: {e}")
            return False
    
    def get_portfolio(self, user_id):
        """Get user portfolio"""
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
    
    def remove_stock(self, user_id, symbol):
        """Remove stock from portfolio"""
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
            st.error(f"Error removing stock: {e}")
            return False

class YahooFinanceClient:
    def get_stock_data(self, symbol):
        """Get stock price and dividend data from Yahoo Finance with debug output"""
        try:
            print(f"Debug - Fetching data for symbol: {symbol}")
            stock = yf.Ticker(symbol)
            info = stock.info
        
            print(f"Debug - Stock info keys: {list(info.keys())[:10]}...")  # Show first 10 keys
            print(f"Debug - Symbol in info: {info.get('symbol')}")
        
            # Get current price
            current_price = (
                info.get('currentPrice') or 
                info.get('regularMarketPrice') or 
                info.get('previousClose') or 
                0
            )
        
            print(f"Debug - Current price found: {current_price}")
            print(f"Debug - Currency: {info.get('currency')}")
        
            if current_price == 0:
                print(f"Debug - No price found for {symbol}")
                return None
        
            # Get dividend data
            print(f"Debug - About to fetch dividend data...")
            dividend_info = self._get_dividend_data(stock, info)
            print(f"Debug - Dividend info returned: {dividend_info}")
        
            result = {
                'symbol': symbol,
                'price': current_price,
                'currency': info.get('currency', 'USD'),
                'company_name': info.get('longName', info.get('shortName', symbol)),
                'dividend_per_share': dividend_info['dividend_per_share'],
                'ex_date': dividend_info['ex_date'],
                'annual_dividend': dividend_info['annual_dividend'],
                'dividend_yield': dividend_info['dividend_yield']
            }
        
            print(f"Debug - Final result: {result}")
            return result
        
    except Exception as e:
        print(f"Debug - Yahoo Finance error for {symbol}: {e}")
        import traceback
        print(f"Debug - Full traceback: {traceback.format_exc()}")
        return None
            
            # Get dividend data
            dividend_info = self._get_dividend_data(stock, info)
            
            return {
                'symbol': symbol,
                'price': current_price,
                'currency': info.get('currency', 'USD'),
                'company_name': info.get('longName', info.get('shortName', symbol)),
                'dividend_per_share': dividend_info['dividend_per_share'],
                'ex_date': dividend_info['ex_date'],
                'annual_dividend': dividend_info['annual_dividend'],
                'dividend_yield': dividend_info['dividend_yield']
            }
            
        except Exception as e:
            print(f"Yahoo Finance error for {symbol}: {e}")
            return None
    
   def _get_dividend_data(self, stock, info):
    """Extract dividend information with debug output"""
    try:
        # Debug: Print what we're working with
        print(f"Debug - Processing dividend data for stock info: {info.get('symbol', 'unknown')}")
        
        # Get dividend history
        dividends = stock.dividends
        print(f"Debug - Raw dividends data: {dividends}")
        print(f"Debug - Dividends empty?: {dividends.empty}")
        print(f"Debug - Dividends length: {len(dividends)}")
        
        if not dividends.empty:
            # Get last 8 dividends
            recent_dividends_data = dividends.tail(8)
            print(f"Debug - Recent dividends: {recent_dividends_data}")
            
            # Last dividend payment
            last_dividend = float(recent_dividends_data.iloc[-1])
            last_date = recent_dividends_data.index[-1].strftime('%Y-%m-%d')
            
            print(f"Debug - Last dividend: {last_dividend}")
            print(f"Debug - Last date: {last_date}")
            
            # Calculate annual dividend (last 12 months)
            one_year_ago = datetime.now() - pd.DateOffset(days=365)
            print(f"Debug - One year ago: {one_year_ago}")
            
            recent_dividends = dividends[dividends.index > one_year_ago]
            print(f"Debug - Recent dividends (12 months): {recent_dividends}")
            
            annual_dividend = float(recent_dividends.sum()) if not recent_dividends.empty else last_dividend * 4
            print(f"Debug - Annual dividend: {annual_dividend}")
            
            # Calculate yield
            current_price = (
                info.get('currentPrice') or 
                info.get('regularMarketPrice') or 
                info.get('previousClose') or 
                0
            )
            
            print(f"Debug - Current price for yield calc: {current_price}")
            
            dividend_yield = (annual_dividend / current_price * 100) if current_price > 0 else 0
            print(f"Debug - Dividend yield: {dividend_yield}")
            
            return {
                'dividend_per_share': last_dividend,
                'ex_date': last_date,
                'annual_dividend': annual_dividend,
                'dividend_yield': dividend_yield
            }
        else:
            print("Debug - No dividends found in history")
            return {
                'dividend_per_share': 0,
                'ex_date': 'N/A',
                'annual_dividend': 0,
                'dividend_yield': 0
            }
            
    except Exception as e:
        print(f"Debug - Exception in _get_dividend_data: {e}")
        print(f"Debug - Exception type: {type(e)}")
        import traceback
        print(f"Debug - Full traceback: {traceback.format_exc()}")
        
        return {
            'dividend_per_share': 0,
            'ex_date': 'N/A',
            'annual_dividend': 0,
            'dividend_yield': 0
        }

# Initialize database
@st.cache_resource
def get_db():
    return DatabaseManager()

db = get_db()

def format_currency(amount, currency, is_uk_stock=False):
    """Format currency properly"""
    if currency == 'GBP' and is_uk_stock:
        return f"{amount:.1f}p"  # UK stocks in pence
    elif currency == 'GBP':
        return f"£{amount:.2f}"
    elif currency == 'USD':
        return f"${amount:.2f}"
    else:
        return f"{currency} {amount:.2f}"

def login_page():
    """Display login page"""
    st.title("Login")
    
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    with tab1:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")
            
            if submit and username and password:
                user = db.get_user(username)
                if user and db.verify_password(password, user['password_hash']):
                    st.session_state.authenticated = True
                    st.session_state.user_id = user['id']
                    st.session_state.username = user['username']
                    st.query_params['user'] = user['username']
                    st.query_params['session'] = 'active'
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid username or password")
    
    with tab2:
        with st.form("signup_form"):
            new_username = st.text_input("Username")
            new_email = st.text_input("Email (optional)")
            new_password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            signup = st.form_submit_button("Sign Up")
            
            if signup and new_username and new_password:
                if new_password != confirm_password:
                    st.error("Passwords don't match")
                elif len(new_password) < 6:
                    st.error("Password must be at least 6 characters")
                elif db.get_user(new_username):
                    st.error("Username already exists")
                else:
                    if db.create_user(new_username, new_password, new_email):
                        st.success("Account created! Please login.")

def main_app():
    """Main application"""
    st.title("Dividend Tracker")
    st.write(f"Welcome, {st.session_state.username}!")
    
    # Logout button
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()
    
    # Sidebar for portfolio management
    with st.sidebar:
        st.header("Portfolio Management")
        
        # Add stock form
        with st.form("add_stock"):
            st.subheader("Add Stock")
            symbol = st.text_input("Symbol (e.g., AAPL, RIO.L)").upper().strip()
            shares = st.number_input("Shares", min_value=0.1, value=1.0, step=0.1)
            add_button = st.form_submit_button("Add Stock")
            
            if add_button and symbol:
                if db.add_stock(st.session_state.user_id, symbol, shares):
                    st.success(f"Added {shares} shares of {symbol}")
                    st.rerun()
        
        # Display portfolio
        st.subheader("Current Portfolio")
        portfolio = db.get_portfolio(st.session_state.user_id)
        
        if portfolio:
            for item in portfolio:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"{item['symbol']}: {item['shares']}")
                with col2:
                    if st.button("X", key=f"remove_{item['symbol']}"):
                        if db.remove_stock(st.session_state.user_id, item['symbol']):
                            st.success(f"Removed {item['symbol']}")
                            st.rerun()
        else:
            st.write("No stocks in portfolio")
    
    # Main content area
    portfolio = db.get_portfolio(st.session_state.user_id)
    
    if portfolio:
        st.subheader("Portfolio Analysis")
        
        yahoo_client = YahooFinanceClient()
        table_data = []
        total_value = {}
        
        for item in portfolio:
            stock_data = yahoo_client.get_stock_data(item['symbol'])
            
            if stock_data:
                is_uk_stock = item['symbol'].endswith('.L')
                currency = stock_data['currency']
                
                # Format price
                if is_uk_stock and currency == 'GBP':
                    price_display = format_currency(stock_data['price'], currency, True)
                    # Calculate position value
                    position_value = float(item['shares']) * stock_data['price']
                    value_display = f"£{position_value / 100:.2f}"  # Convert pence to pounds
                else:
                    price_display = format_currency(stock_data['price'], currency)
                    position_value = float(item['shares']) * stock_data['price']
                    value_display = format_currency(position_value, currency)
                
                # Format dividend
                if stock_data['dividend_per_share'] > 0:
                    if is_uk_stock and currency == 'GBP':
                        dividend_display = f"{stock_data['dividend_per_share']:.1f}p"
                    else:
                        dividend_display = format_currency(stock_data['dividend_per_share'], currency)
                    
                    yield_display = f"{stock_data['dividend_yield']:.2f}%"
                else:
                    dividend_display = "No dividend"
                    yield_display = "0%"
                
                # Track totals by currency
                if currency not in total_value:
                    total_value[currency] = 0
                
                if is_uk_stock and currency == 'GBP':
                    total_value[currency] += position_value / 100  # Convert to pounds
                else:
                    total_value[currency] += position_value
                
                table_data.append({
                    'Symbol': item['symbol'],
                    'Company': stock_data['company_name'][:30],
                    'Shares': f"{float(item['shares']):.1f}",
                    'Price': price_display,
                    'Value': value_display,
                    'Dividend': dividend_display,
                    'Yield': yield_display,
                    'Ex-Date': stock_data['ex_date']
                })
            else:
                table_data.append({
                    'Symbol': item['symbol'],
                    'Company': 'Data unavailable',
                    'Shares': f"{float(item['shares']):.1f}",
                    'Price': 'N/A',
                    'Value': 'N/A',
                    'Dividend': 'N/A',
                    'Yield': 'N/A',
                    'Ex-Date': 'N/A'
                })
        
        # Display table
        if table_data:
            df = pd.DataFrame(table_data)
            st.dataframe(df, use_container_width=True)
            
            # Portfolio totals
            st.subheader("Portfolio Total")
            for currency, value in total_value.items():
                if currency == 'GBP':
                    st.write(f"GBP Holdings: £{value:.2f}")
                elif currency == 'USD':
                    st.write(f"USD Holdings: ${value:.2f}")
                else:
                    st.write(f"{currency} Holdings: {value:.2f}")
    
    else:
        st.info("Add stocks to your portfolio using the sidebar to get started!")

def main():
    """Main application entry point"""
    # Initialize session state
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    # Check for session persistence
    if not st.session_state.authenticated:
        query_params = st.query_params
        if 'user' in query_params and 'session' in query_params:
            username = query_params['user']
            user = db.get_user(username)
            if user:
                st.session_state.authenticated = True
                st.session_state.user_id = user['id']
                st.session_state.username = user['username']
    
    # Show appropriate page
    if st.session_state.authenticated:
        main_app()
    else:
        login_page()

if __name__ == "__main__":
    main()

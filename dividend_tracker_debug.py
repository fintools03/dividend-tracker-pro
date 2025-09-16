# dividend_tracker.py - Complete Version with Alpha Vantage Integration
import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt
from decouple import config
import yfinance as yf
import pandas as pd
from datetime import datetime
import requests
import json

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

class AlphaVantageClient:
    def __init__(self):
        self.api_key = "0ZL6RBY7H5GO7IH9"
        self.base_url = "https://www.alphavantage.co/query"
    
    def get_stock_data(self, symbol):
        """Get stock price and dividend data from Alpha Vantage using correct endpoints"""
        try:
            # Get current stock price using GLOBAL_QUOTE
            quote_data = self._get_global_quote(symbol)
            if not quote_data:
                return None
            
            # Get dividend information from OVERVIEW
            overview_data = self._get_overview(symbol)
            
            # Get recent dividend history from TIME_SERIES_WEEKLY_ADJUSTED
            dividend_history = self._get_recent_dividends(symbol)
            
            # Combine all data
            result = {
                'symbol': symbol,
                'price': quote_data['price'],
                'currency': 'USD',  # Alpha Vantage primarily USD
                'company_name': overview_data.get('Name', symbol),
                'dividend_per_share': dividend_history['last_dividend'],
                'ex_date': dividend_history['last_ex_date'],
                'annual_dividend': overview_data.get('dividend_per_share', 0),
                'dividend_yield': overview_data.get('dividend_yield', 0)
            }
            
            return result
            
        except Exception as e:
            print(f"Alpha Vantage error for {symbol}: {e}")
            return None
    
    def _get_global_quote(self, symbol):
        """Get current stock price using GLOBAL_QUOTE endpoint"""
        try:
            params = {
                'function': 'GLOBAL_QUOTE',
                'symbol': symbol,
                'apikey': self.api_key
            }
            
            response = requests.get(self.base_url, params=params)
            data = response.json()
            
            if 'Global Quote' in data:
                quote = data['Global Quote']
                price = float(quote.get('05. price', 0))
                if price > 0:
                    return {'price': price}
            
            return None
                
        except Exception as e:
            print(f"Error getting quote for {symbol}: {e}")
            return None
    
    def _get_overview(self, symbol):
        """Get company overview including dividend data"""
        try:
            params = {
                'function': 'OVERVIEW',
                'symbol': symbol,
                'apikey': self.api_key
            }
            
            response = requests.get(self.base_url, params=params)
            data = response.json()
            
            if 'Symbol' in data:
                # Extract dividend information
                dividend_per_share = float(data.get('DividendPerShare', 0))
                dividend_yield = float(data.get('DividendYield', 0)) * 100  # Convert to percentage
                
                return {
                    'Name': data.get('Name', symbol),
                    'dividend_per_share': dividend_per_share,
                    'dividend_yield': dividend_yield
                }
            
            return {}
            
        except Exception as e:
            print(f"Error getting overview for {symbol}: {e}")
            return {}
    
    def _get_recent_dividends(self, symbol):
        """Get recent dividend payments from weekly adjusted data"""
        try:
            params = {
                'function': 'TIME_SERIES_WEEKLY_ADJUSTED',
                'symbol': symbol,
                'apikey': self.api_key
            }
            
            response = requests.get(self.base_url, params=params)
            data = response.json()
            
            if 'Weekly Adjusted Time Series' in data:
                time_series = data['Weekly Adjusted Time Series']
                
                # Look for recent dividend payments
                for date, values in sorted(time_series.items(), reverse=True):
                    dividend = float(values.get('7. dividend amount', 0))
                    if dividend > 0:
                        return {
                            'last_dividend': dividend,
                            'last_ex_date': date
                        }
            
            return {
                'last_dividend': 0,
                'last_ex_date': 'N/A'
            }
            
        except Exception as e:
            print(f"Error getting dividend history for {symbol}: {e}")
            return {
                'last_dividend': 0,
                'last_ex_date': 'N/A'
            }

class YahooFinanceClient:
    def get_stock_data(self, symbol):
        """Fallback to Yahoo Finance if Alpha Vantage fails"""
        try:
            stock = yf.Ticker(symbol)
            
            # Try to set user agent
            if hasattr(stock, 'session'):
                stock.session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            
            info = stock.info
            
            # Get current price
            current_price = (
                info.get('currentPrice') or 
                info.get('regularMarketPrice') or 
                info.get('previousClose') or 
                0
            )
            
            if current_price == 0:
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
        """Extract dividend information"""
        try:
            # Get dividend history
            dividends = stock.dividends
            
            if not dividends.empty:
                # Last dividend payment
                last_dividend = float(dividends.iloc[-1])
                last_date = dividends.index[-1].strftime('%Y-%m-%d')
                
                # Calculate annual dividend (last 12 months)
                one_year_ago = datetime.now() - pd.DateOffset(days=365)
                recent_dividends = dividends[dividends.index > one_year_ago]
                annual_dividend = float(recent_dividends.sum()) if not recent_dividends.empty else last_dividend * 4
                
                # Calculate yield
                current_price = (
                    info.get('currentPrice') or 
                    info.get('regularMarketPrice') or 
                    info.get('previousClose') or 
                    0
                )
                
                dividend_yield = (annual_dividend / current_price * 100) if current_price > 0 else 0
                
                return {
                    'dividend_per_share': last_dividend,
                    'ex_date': last_date,
                    'annual_dividend': annual_dividend,
                    'dividend_yield': dividend_yield
                }
            else:
                return {
                    'dividend_per_share': 0,
                    'ex_date': 'N/A',
                    'annual_dividend': 0,
                    'dividend_yield': 0
                }
                
        except Exception:
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
    
    # Logout button - Fixed to clear session properly
    if st.button("Logout"):
        # Clear all session state
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        # Clear query params
        st.query_params.clear()
        st.success("Logged out successfully!")
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
        alpha_client = AlphaVantageClient()
        table_data = []
        total_value = {}
        
        for item in portfolio:
            # Try Alpha Vantage first, fallback to Yahoo Finance
            stock_data = alpha_client.get_stock_data(item['symbol'])
            
            if not stock_data:
                print(f"Alpha Vantage failed for {item['symbol']}, trying Yahoo Finance...")
                stock_data = yahoo_client.get_stock_data(item['symbol'])
            
            if stock_data:
                is_uk_stock = item['symbol'].endswith('.L')
                currency = stock_data['currency']
                
                # Calculate dividend yield if not provided
                if stock_data['dividend_yield'] == 0 and stock_data['annual_dividend'] > 0:
                    stock_data['dividend_yield'] = (stock_data['annual_dividend'] / stock_data['price'] * 100)
                
                # Format price
                if is_uk_stock and currency == 'GBP':
                    # Convert pence to pounds for display
                    price_in_pounds = stock_data['price'] / 100
                    price_display = f"£{price_in_pounds:.2f}"
                    # Calculate position value in pounds
                    position_value = float(item['shares']) * price_in_pounds
                    value_display = f"£{position_value:.2f}"
                else:
                    price_display = format_currency(stock_data['price'], currency)
                    position_value = float(item['shares']) * stock_data['price']
                    value_display = format_currency(position_value, currency)
                
                # Format dividend
                if stock_data['dividend_per_share'] > 0:
                    if is_uk_stock and currency == 'GBP':
                        # Convert dividend from pence to pounds
                        dividend_in_pounds = stock_data['dividend_per_share'] / 100
                        dividend_display = f"£{dividend_in_pounds:.3f}"
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
                    total_value[currency] += position_value  # Already in pounds
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
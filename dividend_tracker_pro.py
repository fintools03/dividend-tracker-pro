# dividend_tracker.py - Phase 2: Stock Prices Added
import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt
from decouple import config
import requests

# Page configuration
st.set_page_config(
    page_title="Dividend Tracker",
    page_icon="💰",
    layout="wide"
)

class FinnhubClient:
    def __init__(self):
        self.api_key = "d2sncqpr01qiq7a53gngd2sncqpr01qiq7a53go0"
        self.base_url = "https://finnhub.io/api/v1"
    
    def get_stock_price(self, symbol):
        """Get current stock price from Finnhub"""
        try:
            # Convert UK symbols for Finnhub (RIO.L -> RIO.LON)
            if symbol.endswith('.L'):
                # Try different UK formats for Finnhub
                base_symbol = symbol.replace('.L', '')
                # Let's try the base symbol without any suffix first
                finnhub_symbol = base_symbol
            else:
                finnhub_symbol = symbol
            
            url = f"{self.base_url}/quote"
            params = {'symbol': finnhub_symbol, 'token': self.api_key}
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            print(f"Trying {finnhub_symbol} for original {symbol}")
            print(f"API response: {data}")
            
            if 'c' in data and data['c'] > 0:
                return {
                    'symbol': symbol,
                    'price': data['c'],
                    'currency': 'GBP' if symbol.endswith('.L') else 'USD'
                }
            return None
        except Exception as e:
            print(f"Finnhub error for {symbol}: {e}")
            return None

    def get_dividend_info(self, symbol):
        """Get dividend information from Finnhub"""
        try:
            # Convert UK symbols for Finnhub
            finnhub_symbol = symbol.replace('.L', '') if symbol.endswith('.L') else symbol
        
            url = f"{self.base_url}/stock/dividend"
            params = {'symbol': finnhub_symbol, 'from': '2023-01-01', 'to': '2024-12-31', 'token': self.api_key}
        
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
        
            if data and len(data) > 0:
                # Get the most recent dividend
                latest_dividend = data[0]  # Assumes sorted by date
                return {
                    'dividend_per_share': latest_dividend.get('amount', 0),
                    'ex_date': latest_dividend.get('exDate', 'N/A'),
                    'currency': 'GBP' if symbol.endswith('.L') else 'USD'
                }
            return None
        except Exception as e:
            print(f"Dividend API error for {symbol}: {e}")
            return None
        
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
                st.error("No database connection available")
                st.stop()
        except Exception as e:
            st.error(f"Database connection failed: {e}")
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

# Initialize database
@st.cache_resource
def get_db():
    return DatabaseManager()

db = get_db()

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
                    # Set URL parameters to maintain session
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
                    else:
                        st.error("Error creating account")

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
                    if st.button("Remove", key=f"remove_{item['symbol']}"):
                        if db.remove_stock(st.session_state.user_id, item['symbol']):
                            st.success(f"Removed {item['symbol']}")
                            st.rerun()
        else:
            st.write("No stocks in portfolio")
    
    # Main content area
    portfolio = db.get_portfolio(st.session_state.user_id)
    
    if portfolio:
        st.subheader("Portfolio with Current Prices and Dividends")

        finnhub = FinnhubClient()

        # Create table data
        table_data = []
        for item in portfolio:
            price_data = finnhub.get_stock_price(item['symbol'])
            dividend_data = finnhub.get_dividend_info(item['symbol'])
    
        if price_data:
            if price_data['currency'] == 'GBP':
                price_display = f"{price_data['price']:.1f}p"
                position_value = float(item['shares']) * price_data['price']
                value_display = f"£{position_value / 100:.2f}"
            else:
                price_display = f"${price_data['price']:.2f}"
                position_value = float(item['shares']) * price_data['price']
                value_display = f"${position_value:.2f}"
    else:
        price_display = "Not available"
        value_display = "N/A"
    
    # Format dividend info
    if dividend_data:
        if dividend_data['currency'] == 'GBP':
            dividend_display = f"{dividend_data['dividend_per_share']:.1f}p"
        else:
            dividend_display = f"${dividend_data['dividend_per_share']:.3f}"
        ex_date_display = dividend_data['ex_date']
    else:
        dividend_display = "N/A"
        ex_date_display = "N/A"
    
    table_data.append({
        'Symbol': item['symbol'],
        'Shares': f"{float(item['shares']):.1f}",
        'Current Price': price_display,
        'Position Value': value_display,
        'Dividend/Share': dividend_display,
        'Ex-Date': ex_date_display
    })

# Display as table
if table_data:
    import pandas as pd
    df = pd.DataFrame(table_data)
    st.dataframe(df, use_container_width=True)

# Portfolio total
st.subheader("Portfolio Total")
total_usd = 0
total_gbp = 0
        
for item in portfolio:
    price_data = finnhub.get_stock_price(item['symbol'])
    if price_data:
        position_value = float(item['shares']) * price_data['price']
        if price_data['currency'] == 'GBP':
            total_gbp += position_value / 100  # Convert pence to pounds
        else:
            total_usd += position_value
        
if total_usd > 0:
    st.write(f"USD Holdings: ${total_usd:.2f}")
if total_gbp > 0:
    st.write(f"GBP Holdings: £{total_gbp:.2f}")

else:
    st.info("Add some stocks to your portfolio using the sidebar to get started!")

def main():
    """Main application entry point"""
    # Initialize session state with persistence
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False

    # Check for remembered login
    if not st.session_state.authenticated:
        # Try to restore session from URL parameters
        query_params = st.query_params
        if 'user' in query_params and 'session' in query_params:
            # Simple session restoration
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

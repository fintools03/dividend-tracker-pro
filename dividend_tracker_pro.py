# dividend_tracker.py - Phase 1: Basic Foundation
import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt
from decouple import config

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
                st.error("No database connection available")
                st.stop()
        except Exception as e:
            st.error(f"Database connection failed: {e}")
            st.stop()
    
    def get_user(self, username):
        """Get user by username"""
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
        st.subheader("Portfolio Summary")
        st.write(f"You have {len(portfolio)} stocks in your portfolio:")
        
        for item in portfolio:
            st.write(f"• {item['symbol']}: {item['shares']} shares")
        
        st.info("Stock prices and dividend data will be added in Phase 2")
    else:
        st.info("Add some stocks to your portfolio using the sidebar to get started!")

def main():
    """Main application entry point"""
    # Initialize session state
    if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

    # Check for remembered login
    if not st.session_state.authenticated:
        # Try to restore session from URL parameters or browser state
        query_params = st.query_params
        if 'user' in query_params and 'session' in query_params:
            # Simple session restoration (you can make this more secure later)
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

# main.py
import streamlit as st
import time
from typing import List, Optional

# Import our modular components
from config import app_config
from database import DatabaseManager, DatabaseError
from api_clients import DataProviderService
from models import User, Portfolio, AnalysisResult, MarketRegistry, CurrencyFormatter
from ui_components import UIComponents

# Configure Streamlit page
st.set_page_config(
    page_title=app_config.title,
    page_icon=app_config.icon,
    layout=app_config.layout,
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

class DividendTrackerApp:
    """Main application class that coordinates all components"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.data_provider = DataProviderService()
        self.ui = UIComponents()
        
        # Initialize database connection
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize database connection with error handling"""
        try:
            if self.db.connect():
                st.sidebar.success("✅ Database connected")
        except DatabaseError as e:
            st.error(f"Database error: {e}")
            st.stop()
    
    def _initialize_session_state(self):
        """Initialize session state variables"""
        if 'authenticated' not in st.session_state:
            st.session_state.authenticated = False
        if 'user' not in st.session_state:
            st.session_state.user = None
        if 'portfolio_data' not in st.session_state:
            st.session_state.portfolio_data = []
        if 'analysis_results' not in st.session_state:
            st.session_state.analysis_results = []
    
    def run(self):
        """Main application entry point"""
        self._initialize_session_state()
        
        if st.session_state.authenticated:
            self._render_main_app()
        else:
            self._render_login_page()
    
    def _render_login_page(self):
        """Render login/signup page"""
        st.title("🔐 Authentication")
        
        tab1, tab2 = st.tabs(["Login", "Sign Up"])
        
        with tab1:
            login_data = self.ui.render_login_form()
            if login_data:
                self._handle_login(login_data)
        
        with tab2:
            signup_data = self.ui.render_signup_form()
            if signup_data:
                self._handle_signup(signup_data)
    
    def _handle_login(self, login_data: dict):
        """Handle user login"""
        try:
            user = self.db.get_user_by_username(login_data['username'])
            
            if user and self.db.verify_password(login_data['password'], user.password_hash if hasattr(user, 'password_hash') else ''):
                st.session_state.authenticated = True
                st.session_state.user = user
                st.success("✅ Login successful!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Invalid username or password")
                
        except DatabaseError as e:
            st.error(f"Login error: {e}")
    
    def _handle_signup(self, signup_data: dict):
        """Handle user signup"""
        try:
            # Check if user already exists
            existing_user = self.db.get_user_by_username(signup_data['username'])
            if existing_user:
                st.error("❌ Username already exists")
                return
            
            # Create new user
            user = self.db.create_user(
                username=signup_data['username'],
                password=signup_data['password'],
                email=signup_data['email']
            )
            st.success("✅ Account created! Please login.")
            
        except DatabaseError as e:
            st.error(f"Signup error: {e}")
    
    def _render_main_app(self):
        """Render main application interface"""
        user = st.session_state.user
        
        st.title(f"💰 {app_config.title}")
        st.markdown(f"**Welcome, {user.username}!**")
        
        # Sidebar content
        self._render_sidebar()
        
        # Main content
        self._render_main_content()
    
    def _render_sidebar(self):
        """Render sidebar content"""
        user = st.session_state.user
        
        with st.sidebar:
            # Logout button
            if st.button("🚪 Logout", key=f"logout_{user.id}"):
                self._handle_logout()
            
            # Portfolio management
            st.header("📊 Portfolio Management")
            
            # Load current portfolio
            self._load_portfolio_data()
            
            # Add stock form
            stock_data = self.ui.render_add_stock_form(user.id)
            if stock_data:
                self._handle_add_stock(stock_data)
            
            # Display portfolio
            symbol_to_remove = self.ui.render_portfolio_list(
                st.session_state.portfolio_data, user.id
            )
            if symbol_to_remove:
                self._handle_remove_stock(symbol_to_remove)
            
            # Market examples
            self.ui.render_market_examples()
            
            # API status
            self._show_api_status()
    
    def _handle_logout(self):
        """Handle user logout"""
        st.session_state.authenticated = False
        st.session_state.user = None
        st.session_state.portfolio_data = []
        st.session_state.analysis_results = []
        st.rerun()
    
    def _load_portfolio_data(self):
        """Load user's portfolio data"""
        try:
            user = st.session_state.user
            portfolio = self.db.get_user_portfolio(user.id)
            st.session_state.portfolio_data = portfolio
            
            if portfolio:
                st.sidebar.info(f"📈 {len(portfolio)} stocks in portfolio")
                
        except DatabaseError as e:
            st.sidebar.error(f"Error loading portfolio: {e}")
    
    def _handle_add_stock(self, stock_data: dict):
        """Handle adding stock to portfolio"""
        try:
            user = st.session_state.user
            self.db.save_portfolio_item(
                user_id=user.id,
                symbol=stock_data['symbol'],
                shares=stock_data['shares']
            )
            st.success(f"✅ Added {stock_data['shares']} shares of {stock_data['symbol']}")
            time.sleep(0.5)
            st.rerun()
            
        except DatabaseError as e:
            st.error(f"Error adding stock: {e}")
    
    def _handle_remove_stock(self, symbol: str):
        """Handle removing stock from portfolio"""
        try:
            user = st.session_state.user
            if self.db.delete_portfolio_item(user.id, symbol):
                st.success(f"✅ Removed {symbol} from portfolio")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(f"Failed to remove {symbol}")
                
        except DatabaseError as e:
            st.error(f"Error removing stock: {e}")
    
    def _show_api_status(self):
        """Show API status in sidebar"""
        alpha_status = "✅" if self.data_provider.alpha_vantage.api_key else "❌"
        polygon_status = "✅" if self.data_provider.polygon.api_key else "❌"
        
        st.sidebar.info(f"🔑 API Status: Alpha Vantage ({alpha_status}), Polygon ({polygon_status})")
    
    def _render_main_content(self):
        """Render main content area"""
        portfolio = st.session_state.portfolio_data
        
        if not portfolio:
            self._render_empty_portfolio()
        else:
            self._render_portfolio_analysis()
    
    def _render_empty_portfolio(self):
        """Render content when portfolio is empty"""
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
        """Render portfolio analysis section"""
        portfolio = st.session_state.portfolio_data
        
        st.info(f"📈 You have {len(portfolio)} stocks in your portfolio. Click 'Analyze Portfolio' to get current data!")
        
        # Analysis button
        if st.button("🔍 Analyze Portfolio", type="primary"):
            self._perform_portfolio_analysis()
        
        # Display results if available
        if st.session_state.analysis_results:
            self._display_analysis_results()
    
    def _perform_portfolio_analysis(self):
        """Perform comprehensive portfolio analysis"""
        portfolio = st.session_state.portfolio_data
        
        with st.spinner("Getting exchange rates..."):
            currency_rates = self.data_provider.get_currency_rates()
        
        st.subheader("🔄 Analysis Progress")
        results = []
        
        # Create progress tracking
        progress_bar = st.progress(0)
        status_container = st.empty()
        
        for i, portfolio_item in enumerate(portfolio):
            status_container.write(f"**{i+1}/{len(portfolio)}** - Analyzing {portfolio_item.symbol}...")
            
            try:
                # Get stock data
                stock_data = self.data_provider.get_stock_data(portfolio_item.symbol)
                
                if stock_data:
                    # Get market information
                    market_info = MarketRegistry.get_market_info(portfolio_item.symbol)
                    is_uk_stock = MarketRegistry.is_uk_stock(portfolio_item.symbol)
                    
                    # Use API currency if available, otherwise use market default
                    currency = stock_data.currency if stock_data.currency else market_info.currency
                    
                    # Calculate position value
                    position_value = portfolio_item.shares * stock_data.current_price
                    
                    # Handle UK stocks position value conversion (pence to pounds)
                    if is_uk_stock and currency == 'GBP':
                        position_value_pounds = position_value / 100
                        position_value_formatted = f"GBP {position_value_pounds:.2f}"
                    else:
                        position_value_formatted = CurrencyFormatter.format_amount(position_value, currency)
                    
                    result = AnalysisResult(
                        symbol=portfolio_item.symbol,
                        shares=portfolio_item.shares,
                        company_name=stock_data.company_name[:40],
                        market=market_info.market,
                        country=market_info.country,
                        currency=currency,
                        current_price=CurrencyFormatter.format_amount(
                            stock_data.current_price, currency, is_uk_stock
                        ),
                        position_value=position_value_formatted,
                        dividend_info=stock_data.dividend_data.format_display(currency),
                        data_source=stock_data.source,
                        status="✅ Success"
                    )
                else:
                    result = AnalysisResult(
                        symbol=portfolio_item.symbol,
                        shares=portfolio_item.shares,
                        company_name="Data unavailable",
                        market="Unknown",
                        country="Unknown",
                        currency="Unknown",
                        current_price="N/A",
                        position_value="N/A",
                        dividend_info="No data available",
                        data_source="All sources failed",
                        status="❌ Failed"
                    )
                
                results.append(result)
                
            except Exception as e:
                # Handle individual stock analysis errors
                error_result = AnalysisResult(
                    symbol=portfolio_item.symbol,
                    shares=portfolio_item.shares,
                    company_name="Error",
                    market="Unknown",
                    country="Unknown",
                    currency="Unknown",
                    current_price="N/A",
                    position_value="N/A",
                    dividend_info="Error retrieving data",
                    data_source=f"Error: {str(e)}",
                    status="❌ Error"
                )
                results.append(error_result)
            
            progress_bar.progress((i + 1) / len(portfolio))
        
        # Store results and show completion
        st.session_state.analysis_results = results
        status_container.empty()
        st.balloons()
        st.success(f"✅ Analysis complete! Processed {len(results)} stocks.")
    
    def _display_analysis_results(self):
        """Display comprehensive analysis results"""
        results = st.session_state.analysis_results
        currency_rates = self.data_provider.get_currency_rates()
        
        # Summary metrics
        self.ui.render_portfolio_summary(results)
        
        # Detailed portfolio table
        self.ui.render_portfolio_details(results)
        
        # Portfolio valuation
        self.ui.render_portfolio_valuation(results, currency_rates)
        
        # Data source performance
        self.ui.render_data_source_performance(results)
        
        # Export options
        clear_results = self.ui.render_export_options(results, st.session_state.user.username)
        if clear_results:
            st.session_state.analysis_results = []
            st.rerun()

def main():
    """Application entry point"""
    app = DividendTrackerApp()
    app.run()

if __name__ == "__main__":
    main()
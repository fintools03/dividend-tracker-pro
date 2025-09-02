# ui_components.py
import streamlit as st
import pandas as pd
import io
from datetime import datetime
from typing import List, Dict, Optional
from models import User, Portfolio, AnalysisResult, MarketRegistry, CurrencyFormatter

class UIComponents:
    """Reusable UI components"""
    
    @staticmethod
    def render_login_form() -> Optional[Dict[str, str]]:
        """Render login form and return credentials if submitted"""
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            
            if submitted and username and password:
                return {"username": username, "password": password}
        return None
    
    @staticmethod
    def render_signup_form() -> Optional[Dict[str, str]]:
        """Render signup form and return user data if submitted"""
        with st.form("signup_form", clear_on_submit=True):
            username = st.text_input("Choose Username")
            email = st.text_input("Email (optional)")
            password = st.text_input("Choose Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Sign Up")
            
            if submitted and username and password:
                if password != confirm_password:
                    st.error("Passwords don't match")
                    return None
                elif len(password) < 6:
                    st.error("Password must be at least 6 characters")
                    return None
                
                return {
                    "username": username,
                    "password": password,
                    "email": email if email else None
                }
        return None
    
    @staticmethod
    def render_add_stock_form(user_id: int) -> Optional[Dict[str, any]]:
        """Render add stock form"""
        form_key = f"add_stock_form_{user_id}"
        with st.form(form_key, clear_on_submit=True):
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
                return {"symbol": symbol, "shares": shares}
        return None
    
    @staticmethod
    def render_portfolio_list(portfolio: List[Portfolio], user_id: int) -> Optional[str]:
        """Render portfolio list and return symbol to remove if requested"""
        if not portfolio:
            st.info("No stocks in portfolio yet")
            return None
        
        st.subheader(f"📋 Current Portfolio ({len(portfolio)} stocks)")
        
        for item in portfolio:
            col1, col2 = st.columns([3, 1])
            col1.text(f"{item.symbol}: {item.shares:.1f} shares")
            
            button_key = f"remove_{item.symbol}_{user_id}"
            if col2.button("🗑️", key=button_key, help=f"Remove {item.symbol}"):
                return item.symbol
        
        return None
    
    @staticmethod
    def render_market_examples():
        """Render market examples in an expandable section"""
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
    
    @staticmethod
    def render_analysis_progress(portfolio: List[Portfolio], current_index: int):
        """Render analysis progress"""
        progress = (current_index + 1) / len(portfolio)
        st.progress(progress)
        st.write(f"**{current_index + 1}/{len(portfolio)}** - Analyzing...")
    
    @staticmethod
    def render_portfolio_summary(results: List[AnalysisResult]):
        """Render portfolio summary metrics"""
        st.subheader("📊 Portfolio Summary")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Stocks", len(results))
        
        with col2:
            successful = sum(1 for r in results if "Success" in r.status)
            st.metric("Data Retrieved", f"{successful}/{len(results)}")
        
        with col3:
            sources = {r.data_source for r in results if "failed" not in r.data_source.lower()}
            st.metric("Active Data Sources", len(sources))
        
        with col4:
            valued_positions = sum(1 for r in results if r.position_value != "N/A")
            st.metric("Valued Positions", valued_positions)
    
    @staticmethod
    def render_portfolio_details(results: List[AnalysisResult]):
        """Render detailed portfolio table"""
        st.subheader("💼 Portfolio Details")
        
        successful_results = [r for r in results if "Success" in r.status]
        failed_results = [r for r in results if "Success" not in r.status]
        
        if successful_results:
            # Create display table
            display_data = []
            for result in successful_results:
                display_data.append({
                    'Symbol': result.symbol,
                    'Company': result.company_name,
                    'Shares': f"{result.shares:.1f}",
                    'Market': result.country,
                    'Currency': result.currency,
                    'Current Price': result.current_price,
                    'Position Value': result.position_value,
                    'Dividend Info': result.dividend_info,
                    'Data Source': result.data_source
                })
            
            df_display = pd.DataFrame(display_data)
            st.dataframe(df_display, use_container_width=True, height=400)
        
        if failed_results:
            st.subheader("⚠️ Stocks with Data Issues")
            for result in failed_results:
                st.warning(f"**{result.symbol}** ({result.shares} shares) - {result.data_source}")
    
    @staticmethod
    def render_portfolio_valuation(results: List[AnalysisResult], currency_rates: Dict[str, float]):
        """Render portfolio valuation summary"""
        st.subheader("💰 Portfolio Valuation")
        
        total_usd = 0
        currency_breakdown = {}
        
        successful_results = [r for r in results if "Success" in r.status]
        
        for result in successful_results:
            if result.position_value and result.position_value != "N/A":
                try:
                    # Extract numeric value
                    value = CurrencyFormatter.parse_amount(result.position_value)
                    currency = result.currency
                    
                    # Convert to USD
                    if currency == 'USD':
                        usd_value = value
                    else:
                        rate = currency_rates.get(currency, 1)
                        usd_value = value / rate if rate > 0 else 0
                    
                    total_usd += usd_value
                    
                    # Track by currency
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
                breakdown_text = " | ".join(breakdown_items[:3])  # Show top 3
                st.metric("Currency Breakdown", breakdown_text)
    
    @staticmethod
    def render_data_source_performance(results: List[AnalysisResult]):
        """Render data source performance breakdown"""
        st.subheader("📡 Data Source Performance")
        
        successful_results = [r for r in results if "Success" in r.status]
        source_counts = {}
        
        for result in successful_results:
            source = result.data_source
            source_counts[source] = source_counts.get(source, 0) + 1
        
        for source, count in source_counts.items():
            st.info(f"**{source}**: Retrieved data for {count} stocks")
    
    @staticmethod
    def render_export_options(results: List[AnalysisResult], username: str):
        """Render export functionality"""
        st.subheader("📥 Export Portfolio")
        
        col1, col2, col3 = st.columns(3)
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
        
        with col1:
            # Excel export
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                # Portfolio sheet
                df_results = pd.DataFrame([r.__dict__ for r in results])
                df_results.to_excel(writer, index=False, sheet_name='Portfolio_Analysis')
                
                # Summary sheet
                summary_data = {
                    'Total Stocks': [len(results)],
                    'Successful Retrievals': [sum(1 for r in results if "Success" in r.status)],
                    'Analysis Date': [datetime.now().strftime('%Y-%m-%d %H:%M')],
                    'User': [username]
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
            df_csv = pd.DataFrame([r.__dict__ for r in results])
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
                return True
        
        return False
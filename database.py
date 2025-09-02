# database.py
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt
from typing import List, Optional
from config import db_config
from models import User, Portfolio

class DatabaseError(Exception):
    """Custom exception for database operations"""
    pass

class DatabaseManager:
    """Handles all database operations without UI dependencies"""
    
    def __init__(self):
        self.connection = None
    
    def connect(self) -> bool:
        """Establish database connection"""
        try:
            if db_config.url:
                self.connection = psycopg2.connect(db_config.url)
            else:
                self.connection = psycopg2.connect(
                    host=db_config.host,
                    database=db_config.name,
                    user=db_config.user,
                    password=db_config.password
                )
            self._create_tables()
            return True
        except Exception as e:
            raise DatabaseError(f"Failed to connect to database: {e}")
    
    def _create_tables(self):
        """Create necessary tables if they don't exist"""
        if not self.connection:
            raise DatabaseError("No database connection")
        
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
        except Exception as e:
            if self.connection:
                self.connection.rollback()
            raise DatabaseError(f"Failed to create tables: {e}")
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        if not self.connection:
            raise DatabaseError("No database connection")
        
        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user_data = cursor.fetchone()
            cursor.close()
            
            if user_data:
                return User(
                    id=user_data['id'],
                    username=user_data['username'],
                    email=user_data['email'],
                    created_at=user_data['created_at']
                )
            return None
        except Exception as e:
            raise DatabaseError(f"Failed to get user: {e}")
    
    def create_user(self, username: str, password: str, email: Optional[str] = None) -> User:
        """Create new user"""
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
            
            return User(
                id=user_data['id'],
                username=user_data['username'],
                email=user_data['email'],
                created_at=user_data['created_at']
            )
        except Exception as e:
            if self.connection:
                self.connection.rollback()
            raise DatabaseError(f"Failed to create user: {e}")
    
    def verify_password(self, password: str, hash_password: str) -> bool:
        """Verify password against hash"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hash_password.encode('utf-8'))
        except Exception:
            return False
    
    def save_portfolio_item(self, user_id: int, symbol: str, shares: float) -> Portfolio:
        """Save or update portfolio entry"""
        if not self.connection:
            raise DatabaseError("No database connection")
        
        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                INSERT INTO portfolios (user_id, symbol, shares, updated_at) 
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id, symbol) 
                DO UPDATE SET shares = EXCLUDED.shares, updated_at = CURRENT_TIMESTAMP
                RETURNING *
            """, (user_id, symbol, shares))
            
            portfolio_data = cursor.fetchone()
            self.connection.commit()
            cursor.close()
            
            return Portfolio(
                symbol=portfolio_data['symbol'],
                shares=float(portfolio_data['shares']),
                user_id=portfolio_data['user_id'],
                created_at=portfolio_data['created_at'],
                updated_at=portfolio_data['updated_at']
            )
        except Exception as e:
            if self.connection:
                self.connection.rollback()
            raise DatabaseError(f"Failed to save portfolio: {e}")
    
    def get_user_portfolio(self, user_id: int) -> List[Portfolio]:
        """Get user's portfolio"""
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
            
            return [
                Portfolio(
                    symbol=item['symbol'],
                    shares=float(item['shares']),
                    user_id=item['user_id'],
                    created_at=item['created_at'],
                    updated_at=item['updated_at']
                )
                for item in portfolio_data
            ]
        except Exception as e:
            raise DatabaseError(f"Failed to get portfolio: {e}")
    
    def delete_portfolio_item(self, user_id: int, symbol: str) -> bool:
        """Delete portfolio item"""
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
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            self.connection = None
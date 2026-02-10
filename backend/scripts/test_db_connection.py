#!/usr/bin/env python3
"""
Test PostgreSQL database connection.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text
from config import DATABASE_URL

def test_connection():
    """Test the database connection."""
    if not DATABASE_URL:
        print("❌ ERROR: DATABASE_URL is not set in .env file")
        print("   Please add: DATABASE_URL=postgresql://owl_us:owl_pw@localhost:5432/owl_db")
        return False
    
    print(f"🔍 Testing connection to: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
    
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"✅ Connection successful!")
            print(f"   PostgreSQL version: {version.split(',')[0]}")
            
            # Test if we can query the database
            result = conn.execute(text("SELECT current_database(), current_user"))
            db_name, user = result.fetchone()
            print(f"   Database: {db_name}")
            print(f"   User: {user}")
            return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure PostgreSQL is running:")
        print("   docker-compose up -d postgres")
        print("2. Verify DATABASE_URL in .env matches docker-compose.yml")
        print("3. Check if port 5432 is accessible:")
        print("   lsof -i :5432")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)

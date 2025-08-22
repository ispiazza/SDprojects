#!/usr/bin/env python3
"""
Debug the health check issue
"""
import os
from dotenv import load_dotenv
load_dotenv()

# Test the database module directly
try:
    import database
    print("🔍 Testing database health check directly...")
    
    result = database.health_check()
    print(f"Health check result: {result}")
    
    # Test basic connection
    print("\n🔗 Testing basic connection...")
    with database.get_db_cursor() as (cursor, conn):
        cursor.execute("SELECT 1 as test")
        test_result = cursor.fetchone()
        print(f"Basic query result: {test_result}")
        
        # Test table count
        print("\n📊 Testing table count...")
        cursor.execute("SELECT COUNT(*) as count FROM information_schema.tables WHERE table_schema = 'public'")
        tables_result = cursor.fetchone()
        print(f"Tables count result: {tables_result}")
        
        # Test collections count
        print("\n📁 Testing collections count...")
        cursor.execute("SELECT COUNT(*) as count FROM collections")
        collections_result = cursor.fetchone()
        print(f"Collections count result: {collections_result}")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
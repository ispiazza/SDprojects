#!/usr/bin/env python3
"""
Check current database status
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

print("🔍 Checking database status...")

try:
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    # Check if we can connect
    cursor.execute("SELECT version();")
    version = cursor.fetchone()
    print(f"✅ Connected to: {version['version'][:50]}...")
    
    # List all tables
    cursor.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    
    tables = cursor.fetchall()
    if tables:
        print(f"📊 Tables found: {len(tables)}")
        for table in tables:
            print(f"  - {table['table_name']}")
    else:
        print("❌ No tables found")
    
    # If collections table exists, check it
    try:
        cursor.execute("SELECT COUNT(*) as count FROM collections;")
        collections_count = cursor.fetchone()['count']
        print(f"📁 Collections: {collections_count}")
        
        cursor.execute("SELECT name FROM collections;")
        collection_names = [row['name'] for row in cursor.fetchall()]
        print(f"📁 Collection names: {collection_names}")
        
    except Exception as e:
        print(f"❌ Collections table issue: {e}")
    
    # If dublin_core_records table exists, check it
    try:
        cursor.execute("SELECT COUNT(*) as count FROM dublin_core_records;")
        records_count = cursor.fetchone()['count']
        print(f"📄 Records: {records_count}")
        
    except Exception as e:
        print(f"❌ Records table issue: {e}")
    
    cursor.close()
    conn.close()
    
    print("✅ Database check complete!")
    
except Exception as e:
    print(f"❌ Database connection failed: {e}")
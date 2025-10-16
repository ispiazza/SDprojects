import psycopg2
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Get DATABASE_URL
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("❌ DATABASE_URL not found in environment")
    exit(1)

print(f"✓ Connecting to Railway PostgreSQL...")

try:
    # Connect to Railway
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # Read SQL file
    with open('migrations/processing_tables.sql', 'r') as f:
        sql = f.read()
    
    # Execute
    print("Running migration...")
    cur.execute(sql)
    conn.commit()
    
    print("✅ Migration successful!")
    
    # Verify tables exist
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_name IN ('processing_sessions', 'processing_items_temp')
    """)
    tables = cur.fetchall()
    print(f"✓ Created tables: {[t[0] for t in tables]}")
    
    cur.close()
    conn.close()

except Exception as e:
    print(f"❌ Error: {e}")
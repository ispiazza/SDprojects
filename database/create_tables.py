#!/usr/bin/env python3
"""
Create database tables for Museum Archive
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# Use the DATABASE_URL from .env
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("❌ DATABASE_URL not found in environment")
    exit(1)

print("🔧 Creating database tables...")
print(f"Database: {DATABASE_URL[:50]}...")

try:
    # Connect to database
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    # Create collections table
    print("📁 Creating collections table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL UNIQUE,
            description TEXT,
            is_public BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Create Dublin Core records table
    print("📄 Creating dublin_core_records table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dublin_core_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collection_id UUID REFERENCES collections(id) ON DELETE CASCADE,
            title TEXT,
            creator TEXT,
            subject TEXT,
            description TEXT,
            publisher TEXT,
            contributor TEXT,
            date_created DATE,
            type VARCHAR(100),
            format VARCHAR(100),
            identifier VARCHAR(255),
            source TEXT,
            language VARCHAR(10) DEFAULT 'en',
            relation TEXT,
            coverage TEXT,
            rights TEXT,
            searchable_content TEXT,
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Create indexes
    print("🔍 Creating indexes...")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dublin_core_title ON dublin_core_records(title);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dublin_core_creator ON dublin_core_records(creator);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dublin_core_collection ON dublin_core_records(collection_id);")
    
    # Insert default collections
    print("📦 Creating default collections...")
    cursor.execute("""
        INSERT INTO collections (name, description) VALUES 
            ('Museum Archive', 'Main museum archive collection containing artifacts, photographs, and historical documents'),
            ('Library', 'Library collection containing books and publications'),
            ('Test Collection', 'Collection for testing and development purposes')
        ON CONFLICT (name) DO NOTHING;
    """)
    
    # Commit changes
    conn.commit()
    
    # Verify tables were created
    cursor.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    
    tables = [row['table_name'] for row in cursor.fetchall()]
    print(f"✅ Tables created: {', '.join(tables)}")
    
    # Check collections
    cursor.execute("SELECT COUNT(*) FROM collections;")
    collections_count = cursor.fetchone()['count']
    print(f"✅ Collections: {collections_count}")
    
    cursor.close()
    conn.close()
    
    print("🎉 Database setup complete!")
    print("\n💡 Next step: Restart your FastAPI app and test the health endpoint")
    
except Exception as e:
    print(f"❌ Error creating tables: {e}")
    import traceback
    traceback.print_exc()
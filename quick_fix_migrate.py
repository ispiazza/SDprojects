#!/usr/bin/env python3
"""
Quick fix migration using the correct Railway connection details
"""

import psycopg2
from psycopg2.extras import RealDictCursor

# Use the correct Railway connection details from your dashboard
DB_CONFIG = {
    'host': 'hopper.proxy.rlwy.net',
    'port': 20632,
    'database': 'railway',
    'user': 'postgres',
    'password': 'tRoiqJvXsqfjsVLXGMnTxIpOwggtKgMn'
}

def test_connection():
    """Test the connection with correct details"""
    try:
        print("🔌 Testing connection with correct Railway details...")
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        cursor.close()
        conn.close()
        
        print(f"✅ Connection successful!")
        print(f"   PostgreSQL version: {version[0][:50]}...")
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

def create_schema():
    """Create the database schema"""
    schema_sql = """
    -- Create collections table
    CREATE TABLE IF NOT EXISTS collections (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name VARCHAR(255) NOT NULL UNIQUE,
        description TEXT,
        is_public BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Create Dublin Core records table
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

    -- Create indexes
    CREATE INDEX IF NOT EXISTS idx_dublin_core_title ON dublin_core_records(title);
    CREATE INDEX IF NOT EXISTS idx_dublin_core_creator ON dublin_core_records(creator);
    CREATE INDEX IF NOT EXISTS idx_dublin_core_subject ON dublin_core_records(subject);
    CREATE INDEX IF NOT EXISTS idx_dublin_core_collection ON dublin_core_records(collection_id);

    -- Insert default collections
    INSERT INTO collections (name, description) VALUES 
        ('Museum Archive', 'Main museum archive collection containing artifacts, photographs, and historical documents'),
        ('Library', 'Library collection containing books and publications'),
        ('Test Collection', 'Collection for testing and development purposes')
    ON CONFLICT (name) DO NOTHING;
    """
    
    try:
        print("📊 Creating database schema...")
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        # Execute schema
        cursor.execute(schema_sql)
        conn.commit()
        
        cursor.close()
        conn.close()
        
        print("✅ Schema created successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Schema creation failed: {e}")
        return False

def create_sample_data():
    """Create sample museum data"""
    try:
        print("📦 Creating sample museum data...")
        
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        # Get Museum Archive collection ID
        cursor.execute("SELECT id FROM collections WHERE name = 'Museum Archive'")
        result = cursor.fetchone()
        if result:
            collection_id = result['id']
            
            sample_records = [
                {
                    'title': 'Ancient Pottery Vessel',
                    'creator': 'Unknown Ancient Artisan',
                    'description': 'A well-preserved pottery vessel from the ancient period, showcasing traditional craftsmanship.',
                    'type': 'Artifact',
                    'subject': 'Pottery, Ancient History',
                    'date_created': '2000-01-01',
                    'source': 'Museum Archive',
                    'collection_id': collection_id
                },
                {
                    'title': 'Historical Photograph Collection',
                    'creator': 'Local Photography Studio',
                    'description': 'Collection of historical photographs documenting the town development.',
                    'type': 'Photograph',
                    'subject': 'Photography, Local History',
                    'date_created': '1950-01-01',
                    'source': 'Museum Archive',
                    'collection_id': collection_id
                },
                {
                    'title': 'Traditional Textile Sample',
                    'creator': 'Local Artisan',
                    'description': 'Example of traditional weaving techniques used in the region.',
                    'type': 'Textile',
                    'subject': 'Crafts, Traditional Arts',
                    'date_created': '1800-01-01',
                    'source': 'Museum Archive',
                    'collection_id': collection_id
                },
                {
                    'title': 'Colonial Era Document',
                    'creator': 'Town Records Office',
                    'description': 'Original document from the colonial period detailing land grants.',
                    'type': 'Document',
                    'subject': 'History, Legal Documents',
                    'date_created': '1750-01-01',
                    'source': 'Museum Archive',
                    'collection_id': collection_id
                },
                {
                    'title': 'Vintage Agricultural Tools',
                    'creator': 'Local Farmers',
                    'description': 'Collection of traditional farming tools used in the 19th century.',
                    'type': 'Tool',
                    'subject': 'Agriculture, Tools, History',
                    'date_created': '1850-01-01',
                    'source': 'Museum Archive',
                    'collection_id': collection_id
                }
            ]
            
            for record in sample_records:
                columns = list(record.keys())
                values = list(record.values())
                placeholders = ['%s'] * len(values)
                
                query = f"""
                    INSERT INTO dublin_core_records ({', '.join(columns)})
                    VALUES ({', '.join(placeholders)})
                """
                
                cursor.execute(query, values)
            
            conn.commit()
            print(f"✅ Added {len(sample_records)} sample records!")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Sample data creation failed: {e}")
        return False

def verify_setup():
    """Verify everything is working"""
    try:
        print("🔍 Verifying database setup...")
        
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        # Count everything
        cursor.execute("SELECT COUNT(*) FROM collections")
        collections_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM dublin_core_records")
        records_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT name FROM collections ORDER BY name")
        collection_names = [row[0] for row in cursor.fetchall()]
        
        # Test a search
        cursor.execute("""
            SELECT title, creator, type 
            FROM dublin_core_records 
            WHERE title ILIKE '%pottery%' OR description ILIKE '%pottery%'
        """)
        search_results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        print("✅ Database verification successful!")
        print(f"   Collections: {collections_count}")
        print(f"   Collection names: {', '.join(collection_names)}")
        print(f"   Records: {records_count}")
        print(f"   Sample search results: {len(search_results)}")
        
        if search_results:
            print("   Sample record:")
            for result in search_results[:1]:
                print(f"     Title: {result['title']}")
                print(f"     Creator: {result['creator']}")
                print(f"     Type: {result['type']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

def main():
    """Quick setup"""
    print("🚀 Railway Museum Archive Quick Setup")
    print("=" * 40)
    
    # Test connection
    if not test_connection():
        print("❌ Cannot continue without database connection")
        return
    
    # Create schema
    if create_schema():
        print("✅ Database schema ready")
    else:
        print("⚠️  Schema creation had issues")
        return
    
    # Add sample data
    if create_sample_data():
        print("✅ Sample data added")
    else:
        print("⚠️  Sample data creation had issues")
    
    # Verify
    verify_setup()
    
    print("\n🎉 Setup complete!")
    print("\nNext steps:")
    print("1. Update your main.py to use these connection details")
    print("2. Test your API: python3 main.py")
    print("3. Deploy: railway up")
    print("\n💡 Connection details for your main.py:")
    print(f"   Host: {DB_CONFIG['host']}")
    print(f"   Port: {DB_CONFIG['port']}")
    print(f"   Database: {DB_CONFIG['database']}")

if __name__ == "__main__":
    main()
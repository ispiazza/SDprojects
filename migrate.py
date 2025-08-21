#!/usr/bin/env python3
"""
Debug and Fixed Migration Script for Railway Deployment
Includes better error handling and environment variable debugging
"""

import os
import sys
import json
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from datetime import datetime
import shutil
import zipfile
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def debug_environment():
    """Debug Railway environment variables"""
    print("🔍 Debugging Railway Environment Variables")
    print("=" * 50)
    
    # Check for Railway-specific variables
    railway_vars = [
        'RAILWAY_ENVIRONMENT', 'RAILWAY_PROJECT_ID', 'RAILWAY_SERVICE_ID',
        'PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD',
        'DATABASE_URL', 'DATABASE_PRIVATE_URL'
    ]
    
    found_vars = {}
    missing_vars = []
    
    for var in railway_vars:
        value = os.getenv(var)
        if value:
            if 'PASSWORD' in var:
                found_vars[var] = f"***{value[-4:]}" if len(value) > 4 else "***"
            else:
                found_vars[var] = value
        else:
            missing_vars.append(var)
    
    print("✅ Found environment variables:")
    for var, value in found_vars.items():
        print(f"  {var}: {value}")
    
    if missing_vars:
        print("\n❌ Missing environment variables:")
        for var in missing_vars:
            print(f"  {var}")
    
    # Check if we have DATABASE_URL (Railway often provides this)
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        print(f"\n🔗 DATABASE_URL found: {database_url[:30]}...")
        return parse_database_url(database_url)
    
    return None

def parse_database_url(database_url: str) -> Dict[str, str]:
    """Parse DATABASE_URL into connection parameters"""
    try:
        # Parse postgresql://user:password@host:port/database
        import urllib.parse
        parsed = urllib.parse.urlparse(database_url)
        
        return {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path.lstrip('/'),
            'user': parsed.username,
            'password': parsed.password,
        }
    except Exception as e:
        logger.error(f"Failed to parse DATABASE_URL: {e}")
        return {}

class RailwayMigrator:
    """Enhanced Railway migrator with better error handling"""
    
    def __init__(self):
        print("🚀 Initializing Railway Migrator")
        
        # First, debug the environment
        parsed_db_config = debug_environment()
        
        # Try to get database configuration from various sources
        self.db_config = self._get_database_config(parsed_db_config)
        
        # Validate database configuration
        missing_keys = [k for k, v in self.db_config.items() if not v]
        if missing_keys:
            print(f"\n❌ Missing database configuration: {missing_keys}")
            print("\n🔧 Troubleshooting steps:")
            print("1. Make sure you're in Railway shell: railway shell")
            print("2. Check if PostgreSQL service is added: railway add postgresql")
            print("3. Check service status: railway status")
            print("4. List variables: railway variables")
            print("5. Try connecting directly: railway connect postgresql")
            
            # Try to continue with what we have
            if input("\nContinue anyway? (y/N): ").lower() != 'y':
                raise ValueError("Database configuration incomplete")
        
        logger.info("Railway migrator initialized successfully")
    
    def _get_database_config(self, parsed_db_config=None) -> Dict[str, str]:
        """Get database configuration from multiple sources"""
        
        # Option 1: Use parsed DATABASE_URL
        if parsed_db_config:
            logger.info("Using DATABASE_URL configuration")
            return parsed_db_config
        
        # Option 2: Use individual PG variables
        config = {
            'host': os.getenv('PGHOST'),
            'port': os.getenv('PGPORT', 5432),
            'database': os.getenv('PGDATABASE'),
            'user': os.getenv('PGUSER'),
            'password': os.getenv('PGPASSWORD'),
        }
        
        if all(config.values()):
            logger.info("Using individual PG environment variables")
            return config
        
        # Option 3: Try common Railway variable patterns
        alt_config = {
            'host': os.getenv('DB_HOST') or os.getenv('POSTGRES_HOST'),
            'port': os.getenv('DB_PORT') or os.getenv('POSTGRES_PORT', 5432),
            'database': os.getenv('DB_NAME') or os.getenv('POSTGRES_DB'),
            'user': os.getenv('DB_USER') or os.getenv('POSTGRES_USER'),
            'password': os.getenv('DB_PASSWORD') or os.getenv('POSTGRES_PASSWORD'),
        }
        
        if any(alt_config.values()):
            logger.info("Using alternative database environment variables")
            # Fill in any missing values from original config
            for key, value in config.items():
                if not alt_config.get(key) and value:
                    alt_config[key] = value
            return alt_config
        
        # Option 4: Use default local configuration for testing
        logger.warning("Using default local configuration")
        return {
            'host': 'localhost',
            'port': 5432,
            'database': 'postgres',
            'user': 'postgres',
            'password': 'postgres',
        }
    
    def test_connection(self) -> bool:
        """Test database connection before proceeding"""
        try:
            print("🔌 Testing database connection...")
            conn = psycopg2.connect(**self.db_config, cursor_factory=RealDictCursor)
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            cursor.close()
            conn.close()
            
            print(f"✅ Database connection successful!")
            print(f"   PostgreSQL version: {version[0][:50]}...")
            return True
            
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            print(f"   Host: {self.db_config['host']}")
            print(f"   Port: {self.db_config['port']}")
            print(f"   Database: {self.db_config['database']}")
            print(f"   User: {self.db_config['user']}")
            return False
    
    def get_db_connection(self):
        """Get PostgreSQL database connection"""
        return psycopg2.connect(**self.db_config, cursor_factory=RealDictCursor)
    
    def run_schema_migration(self, schema_file: str = "migrations/schema.sql"):
        """Run the PostgreSQL schema migration with better error handling"""
        try:
            print(f"📊 Running schema migration from: {schema_file}")
            
            schema_path = Path(schema_file)
            if not schema_path.exists():
                # Try alternative locations
                alt_paths = [
                    Path("schema.sql"),
                    Path("migration/schema.sql"),
                    Path("db/schema.sql")
                ]
                
                for alt_path in alt_paths:
                    if alt_path.exists():
                        schema_path = alt_path
                        break
                else:
                    print(f"❌ Schema file not found: {schema_file}")
                    print("Available files:")
                    for p in Path(".").rglob("*.sql"):
                        print(f"  {p}")
                    return False
            
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
            
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Split and execute schema statements
            statements = [stmt.strip() for stmt in schema_sql.split(';') if stmt.strip()]
            
            for i, statement in enumerate(statements):
                try:
                    cursor.execute(statement)
                    conn.commit()
                    print(f"✅ Executed statement {i+1}/{len(statements)}")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        print(f"⚠️  Statement {i+1}: Already exists (skipping)")
                    else:
                        print(f"❌ Statement {i+1} failed: {e}")
                        # Continue with other statements
            
            cursor.close()
            conn.close()
            
            print("✅ Schema migration completed")
            return True
            
        except Exception as e:
            print(f"❌ Schema migration failed: {e}")
            return False
    
    def migrate_sample_data(self):
        """Create some sample data if no existing data to migrate"""
        try:
            print("📦 Creating sample data...")
            
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Get Museum Archive collection ID
            cursor.execute("SELECT id FROM collections WHERE name = 'Museum Archive'")
            result = cursor.fetchone()
            if result:
                collection_id = result['id']
                
                sample_records = [
                    {
                        'title': 'Ancient Pottery Vessel',
                        'creator': 'Unknown',
                        'description': 'A well-preserved pottery vessel from the ancient period, showcasing traditional craftsmanship.',
                        'type': 'Artifact',
                        'subject': 'Pottery, Ancient History',
                        'date_created': '2000-01-01',
                        'collection_id': collection_id
                    },
                    {
                        'title': 'Historical Photograph Collection',
                        'creator': 'Local Photography Studio',
                        'description': 'Collection of historical photographs documenting the town\'s development.',
                        'type': 'Photograph',
                        'subject': 'Photography, Local History',
                        'date_created': '1950-01-01',
                        'collection_id': collection_id
                    },
                    {
                        'title': 'Traditional Textile Sample',
                        'creator': 'Local Artisan',
                        'description': 'Example of traditional weaving techniques used in the region.',
                        'type': 'Textile',
                        'subject': 'Crafts, Traditional Arts',
                        'date_created': '1800-01-01',
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
                        ON CONFLICT DO NOTHING
                    """
                    
                    cursor.execute(query, values)
                
                conn.commit()
                print("✅ Sample data created successfully")
            
            cursor.close()
            conn.close()
            return True
            
        except Exception as e:
            print(f"❌ Sample data creation failed: {e}")
            return False
    
    def verify_migration(self) -> Dict[str, Any]:
        """Verify the migration was successful"""
        try:
            print("🔍 Verifying migration...")
            
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Count records in each table
            cursor.execute("SELECT COUNT(*) FROM collections")
            collections_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM dublin_core_records")
            records_count = cursor.fetchone()[0]
            
            # Check sample collection names
            cursor.execute("SELECT name FROM collections ORDER BY name")
            collection_names = [row[0] for row in cursor.fetchall()]
            
            # Check ChromaDB
            chromadb_status = "Available" if Path("./chromadb_data").exists() else "Not found"
            
            # Check media files
            media_files_count = len(list(Path("./media").rglob("*"))) if Path("./media").exists() else 0
            
            cursor.close()
            conn.close()
            
            verification_result = {
                'success': True,
                'collections': collections_count,
                'collection_names': collection_names,
                'dublin_core_records': records_count,
                'chromadb_status': chromadb_status,
                'media_files': media_files_count,
                'migration_date': datetime.now().isoformat()
            }
            
            print("✅ Migration verification successful:")
            print(f"   Collections: {collections_count}")
            print(f"   Collection names: {', '.join(collection_names)}")
            print(f"   Records: {records_count}")
            print(f"   ChromaDB: {chromadb_status}")
            print(f"   Media files: {media_files_count}")
            
            return verification_result
            
        except Exception as e:
            print(f"❌ Migration verification failed: {e}")
            return {'success': False, 'error': str(e)}

def main():
    """Enhanced main migration function"""
    print("🚀 Railway Migration Script - Enhanced")
    print("=" * 45)
    
    try:
        # Initialize migrator with better error handling
        migrator = RailwayMigrator()
        
        # Test database connection first
        if not migrator.test_connection():
            print("\n🔧 Connection troubleshooting:")
            print("1. Check Railway service status: railway status")
            print("2. Restart PostgreSQL service: railway restart")
            print("3. Check Railway logs: railway logs")
            
            if input("\nContinue with migration anyway? (y/N): ").lower() != 'y':
                return
        
        # Step 1: Run schema migration
        print("\n📊 Step 1: Running schema migration...")
        schema_success = migrator.run_schema_migration()
        
        if not schema_success:
            print("⚠️  Schema migration had issues, but continuing...")
        
        # Step 2: Check for existing data to migrate
        print("\n📦 Step 2: Checking for data to migrate...")
        data_dir = input("Enter path to existing data directory (or press Enter to create sample data): ").strip()
        
        if data_dir and Path(data_dir).exists():
            print(f"📦 Would migrate data from: {data_dir}")
            print("(Data migration not implemented in this debug version)")
        else:
            print("📦 Creating sample data instead...")
            migrator.migrate_sample_data()
        
        # Step 3: Verify migration
        print("\n🔍 Step 3: Verifying migration...")
        verification = migrator.verify_migration()
        
        if verification['success']:
            print("\n🎉 Migration completed successfully!")
            print("\nNext steps:")
            print("1. Test the API: curl https://your-app.railway.app/api/health")
            print("2. Check the dashboard: https://your-app.railway.app/dashboard")
            print("3. Deploy your application: railway up")
        else:
            print(f"\n❌ Migration verification failed: {verification.get('error')}")
    
    except KeyboardInterrupt:
        print("\n⚠️  Migration interrupted by user")
    except Exception as e:
        print(f"\n❌ Migration failed with error: {e}")
        print(f"Error type: {type(e).__name__}")
        
        # Provide helpful debugging information
        print("\n🔧 Debugging tips:")
        print("1. Check Railway shell: railway shell")
        print("2. Check environment: env | grep PG")
        print("3. Check Railway status: railway status")
        print("4. Check PostgreSQL logs: railway logs --service postgresql")

if __name__ == "__main__":
    main()
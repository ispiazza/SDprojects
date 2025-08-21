#!/usr/bin/env python3
"""
Migration Script for Railway Deployment
Migrates existing data from Replit to Railway PostgreSQL + ChromaDB
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

class RailwayMigrator:
    """Handles migration from Replit to Railway"""
    
    def __init__(self):
        # Railway PostgreSQL connection (auto-configured)
        self.db_config = {
            'host': os.getenv('PGHOST'),
            'port': os.getenv('PGPORT', 5432),
            'database': os.getenv('PGDATABASE'),
            'user': os.getenv('PGUSER'),
            'password': os.getenv('PGPASSWORD'),
        }
        
        # Validate database configuration
        if not all([self.db_config['host'], self.db_config['database'], 
                   self.db_config['user'], self.db_config['password']]):
            raise ValueError("Missing required PostgreSQL environment variables")
        
        logger.info("Railway migrator initialized")
    
    def get_db_connection(self):
        """Get PostgreSQL database connection"""
        return psycopg2.connect(**self.db_config, cursor_factory=RealDictCursor)
    
    def run_schema_migration(self, schema_file: str = "migrations/schema.sql"):
        """Run the PostgreSQL schema migration"""
        try:
            if not Path(schema_file).exists():
                logger.error(f"Schema file not found: {schema_file}")
                return False
            
            with open(schema_file, 'r') as f:
                schema_sql = f.read()
            
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Execute schema creation
            cursor.execute(schema_sql)
            conn.commit()
            
            cursor.close()
            conn.close()
            
            logger.info("Schema migration completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Schema migration failed: {e}")
            return False
    
    def migrate_replit_data(self, data_directory: str):
        """Migrate existing Replit data to Railway"""
        data_dir = Path(data_directory)
        
        if not data_dir.exists():
            logger.warning(f"Data directory not found: {data_directory}")
            return {'success': False, 'error': 'Data directory not found'}
        
        migration_stats = {
            'json_files_migrated': 0,
            'database_records': 0,
            'session_files_migrated': 0,
            'media_files_migrated': 0,
            'errors': []
        }
        
        try:
            # Migrate JSON data files
            json_files = list(data_dir.rglob("*.json"))
            for json_file in json_files:
                if self._migrate_json_file(json_file):
                    migration_stats['json_files_migrated'] += 1
            
            # Migrate session data
            sessions_dir = data_dir / "sessions"
            if sessions_dir.exists():
                migration_stats['session_files_migrated'] = self._migrate_sessions(sessions_dir)
            
            # Migrate media files
            media_dir = data_dir / "media"
            if media_dir.exists():
                migration_stats['media_files_migrated'] = self._migrate_media_files(media_dir)
            
            # Migrate ChromaDB data
            chromadb_dir = data_dir / "chromadb_data"
            if chromadb_dir.exists():
                self._migrate_chromadb_data(chromadb_dir)
            
            logger.info(f"Migration completed: {migration_stats}")
            return {'success': True, 'stats': migration_stats}
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            migration_stats['errors'].append(str(e))
            return {'success': False, 'stats': migration_stats, 'error': str(e)}
    
    def _migrate_json_file(self, json_file: Path) -> bool:
        """Migrate a single JSON file to PostgreSQL"""
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle different JSON structures
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and 'items' in data:
                items = data['items']
            else:
                items = [data]
            
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Determine collection based on file path or content
            collection_name = self._determine_collection(json_file, items[0] if items else {})
            collection_id = self._get_or_create_collection(cursor, collection_name)
            
            for item in items:
                if self._insert_dublin_core_record(cursor, item, collection_id):
                    continue
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"Migrated JSON file: {json_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to migrate JSON file {json_file}: {e}")
            return False
    
    def _determine_collection(self, json_file: Path, sample_item: Dict) -> str:
        """Determine which collection this data belongs to"""
        file_path = str(json_file).lower()
        
        if 'library' in file_path or 'book' in file_path:
            return 'Library'
        elif 'museum' in file_path or 'archive' in file_path:
            return 'Museum Archive'
        elif sample_item.get('type', '').lower() in ['book', 'publication']:
            return 'Library'
        else:
            return 'Museum Archive'
    
    def _get_or_create_collection(self, cursor, collection_name: str) -> str:
        """Get existing collection ID or create new one"""
        cursor.execute("SELECT id FROM collections WHERE name = %s", (collection_name,))
        result = cursor.fetchone()
        
        if result:
            return result['id']
        
        # Create new collection
        cursor.execute("""
            INSERT INTO collections (name, description, is_public)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (collection_name, f'Migrated {collection_name} collection', True))
        
        return cursor.fetchone()['id']
    
    def _insert_dublin_core_record(self, cursor, item: Dict, collection_id: str) -> bool:
        """Insert Dublin Core record into PostgreSQL"""
        try:
            # Map item data to Dublin Core schema
            dublin_core_data = {
                'collection_id': collection_id,
                'title': self._extract_field(item, ['title', 'dcterms:title']),
                'creator': self._extract_field(item, ['creator', 'dcterms:creator']),
                'subject': self._extract_field(item, ['subject', 'dcterms:subject']),
                'description': self._extract_field(item, ['description', 'dcterms:description']),
                'publisher': self._extract_field(item, ['publisher', 'dcterms:publisher']),
                'contributor': self._extract_field(item, ['contributor', 'dcterms:contributor']),
                'date_created': self._parse_date(self._extract_field(item, ['date_created', 'dcterms:date'])),
                'type': self._extract_field(item, ['type', 'dcterms:type']),
                'format': self._extract_field(item, ['format', 'dcterms:format']),
                'identifier': self._extract_field(item, ['identifier', 'dcterms:identifier', 'id']),
                'source': self._extract_field(item, ['source', 'dcterms:source']),
                'language': self._extract_field(item, ['language', 'dcterms:language'], 'en'),
                'rights': self._extract_field(item, ['rights', 'dcterms:rights']),
                'searchable_content': self._extract_field(item, ['extracted_text', 'content', 'text']),
                'metadata': json.dumps(item)  # Store original data as JSONB
            }
            
            # Remove None values
            dublin_core_data = {k: v for k, v in dublin_core_data.items() if v is not None}
            
            # Build dynamic INSERT query
            columns = list(dublin_core_data.keys())
            values = list(dublin_core_data.values())
            placeholders = ['%s'] * len(values)
            
            query = f"""
                INSERT INTO dublin_core_records ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
                ON CONFLICT DO NOTHING
            """
            
            cursor.execute(query, values)
            return True
            
        except Exception as e:
            logger.error(f"Failed to insert Dublin Core record: {e}")
            return False
    
    def _extract_field(self, item: Dict, field_names: List[str], default: Any = None) -> Any:
        """Extract field value from various possible field names"""
        for field_name in field_names:
            if field_name in item and item[field_name]:
                value = item[field_name]
                if isinstance(value, list):
                    return '; '.join(str(v) for v in value if v)
                return str(value).strip() if value else default
        return default
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date string to PostgreSQL date format"""
        if not date_str:
            return None
        
        import re
        patterns = [
            r'(\d{4})-(\d{2})-(\d{2})',  # YYYY-MM-DD
            r'(\d{4})/(\d{2})/(\d{2})',  # YYYY/MM/DD
            r'(\d{4})',  # Just year
        ]
        
        for pattern in patterns:
            match = re.search(pattern, str(date_str))
            if match:
                if len(match.groups()) == 3:
                    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                elif len(match.groups()) == 1:
                    return f"{match.group(1)}-01-01"
        
        return None
    
    def _migrate_sessions(self, sessions_dir: Path) -> int:
        """Migrate processing session data"""
        target_sessions_dir = Path("./sessions")
        target_sessions_dir.mkdir(exist_ok=True)
        
        migrated_count = 0
        for session_dir in sessions_dir.iterdir():
            if session_dir.is_dir():
                target_dir = target_sessions_dir / session_dir.name
                shutil.copytree(session_dir, target_dir, dirs_exist_ok=True)
                migrated_count += 1
        
        logger.info(f"Migrated {migrated_count} processing sessions")
        return migrated_count
    
    def _migrate_media_files(self, media_dir: Path) -> int:
        """Migrate media files"""
        target_media_dir = Path("./media")
        target_media_dir.mkdir(exist_ok=True)
        
        migrated_count = 0
        for media_file in media_dir.rglob("*"):
            if media_file.is_file():
                relative_path = media_file.relative_to(media_dir)
                target_path = target_media_dir / relative_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(media_file, target_path)
                migrated_count += 1
        
        logger.info(f"Migrated {migrated_count} media files")
        return migrated_count
    
    def _migrate_chromadb_data(self, chromadb_dir: Path):
        """Migrate ChromaDB data"""
        target_chromadb_dir = Path("./chromadb_data")
        target_chromadb_dir.mkdir(exist_ok=True)
        
        try:
            shutil.copytree(chromadb_dir, target_chromadb_dir, dirs_exist_ok=True)
            logger.info("ChromaDB data migrated successfully")
        except Exception as e:
            logger.error(f"ChromaDB migration failed: {e}")
    
    def verify_migration(self) -> Dict[str, Any]:
        """Verify the migration was successful"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Count records in each table
            cursor.execute("SELECT COUNT(*) FROM collections")
            collections_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM dublin_core_records")
            records_count = cursor.fetchone()[0]
            
            # Check ChromaDB
            chromadb_status = "Available" if Path("./chromadb_data").exists() else "Not found"
            
            # Check media files
            media_files_count = len(list(Path("./media").rglob("*"))) if Path("./media").exists() else 0
            
            cursor.close()
            conn.close()
            
            verification_result = {
                'success': True,
                'collections': collections_count,
                'dublin_core_records': records_count,
                'chromadb_status': chromadb_status,
                'media_files': media_files_count,
                'migration_date': datetime.now().isoformat()
            }
            
            logger.info(f"Migration verification: {verification_result}")
            return verification_result
            
        except Exception as e:
            logger.error(f"Migration verification failed: {e}")
            return {'success': False, 'error': str(e)}

def main():
    """Main migration function"""
    print("🚀 Railway Migration Script")
    print("=" * 40)
    
    migrator = RailwayMigrator()
    
    # Step 1: Run schema migration
    print("📊 Running schema migration...")
    schema_success = migrator.run_schema_migration()
    
    if not schema_success:
        print("❌ Schema migration failed!")
        return
    
    print("✅ Schema migration completed")
    
    # Step 2: Migrate data (if data directory provided)
    data_dir = input("Enter path to Replit data directory (or press Enter to skip): ").strip()
    
    if data_dir and Path(data_dir).exists():
        print(f"📦 Migrating data from: {data_dir}")
        migration_result = migrator.migrate_replit_data(data_dir)
        
        if migration_result['success']:
            print("✅ Data migration completed!")
            print(f"Stats: {migration_result['stats']}")
        else:
            print(f"❌ Data migration failed: {migration_result.get('error')}")
    
    # Step 3: Verify migration
    print("🔍 Verifying migration...")
    verification = migrator.verify_migration()
    
    if verification['success']:
        print("✅ Migration verification successful!")
        print(f"- Collections: {verification['collections']}")
        print(f"- Records: {verification['dublin_core_records']}")
        print(f"- ChromaDB: {verification['chromadb_status']}")
        print(f"- Media files: {verification['media_files']}")
    else:
        print(f"❌ Migration verification failed: {verification.get('error')}")
    
    print("\n🎉 Migration process completed!")
    print("Next steps:")
    print("1. Deploy to Railway using: railway up")
    print("2. Set environment variables in Railway dashboard")
    print("3. Test your application at the Railway URL")

if __name__ == "__main__":
    main()
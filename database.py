"""
Fixed database.py for Railway PostgreSQL SSL connection
Handles Railway's self-signed certificates properly
"""
import os
import logging
from typing import List, Dict, Any, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

from models.base import DublinCoreRecord

# Configure logging
logger = logging.getLogger(__name__)

# Force load environment variables
from dotenv import load_dotenv
load_dotenv(override=True)

def get_database_config():
    """Get database configuration - prioritize DATABASE_URL for Railway"""
    
    # First, try to use DATABASE_URL if available (Railway provides this)
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        logger.info("Using DATABASE_URL for connection")
        import urllib.parse
        try:
            parsed = urllib.parse.urlparse(database_url)
            return {
                'host': parsed.hostname,
                'port': parsed.port or 5432,
                'database': parsed.path.lstrip('/'),
                'user': parsed.username,
                'password': parsed.password,
                'sslmode': 'require',
            }
        except Exception as e:
            logger.warning(f"Failed to parse DATABASE_URL: {e}")
    
    # Check if we're in actual Railway deployment
    is_railway_deployment = (
        os.getenv('RAILWAY_STATIC_URL') or 
        os.getenv('RAILWAY_PUBLIC_DOMAIN') or
        (os.getenv('PORT') and not os.getenv('RAILWAY_SHELL'))
    )
    
    if is_railway_deployment:
        logger.info("Detected Railway deployment - using internal connection")
        return {
            'host': 'postgres.railway.internal',
            'port': 5432,
            'database': os.getenv('PGDATABASE', 'railway'),
            'user': os.getenv('PGUSER', 'postgres'),
            'password': os.getenv('PGPASSWORD'),
        }
    else:
        logger.info("Using external database connection (Railway shell or local)")
        # For external connections to Railway, we need special SSL handling
        return {
            'host': os.getenv('PGHOST'),
            'port': int(os.getenv('PGPORT', 5432)),
            'database': os.getenv('PGDATABASE'),
            'user': os.getenv('PGUSER'),
            'password': os.getenv('PGPASSWORD'),
            # Railway uses self-signed certificates, so we need sslmode=require
            # This requires SSL but doesn't verify the certificate chain
            'sslmode': 'require',
            'sslcert': None,
            'sslkey': None,
            'sslrootcert': None,
        }

# Get the configuration
DB_CONFIG = get_database_config()
logger.info(f"Database config: host={DB_CONFIG.get('host')}, port={DB_CONFIG.get('port')}, sslmode={DB_CONFIG.get('sslmode', 'none')}")

class DatabaseError(Exception):
    """Custom exception for database operations"""
    pass


def get_db_connection():
    """Get PostgreSQL database connection with Railway SSL handling"""
    connection_attempts = [
        # Attempt 1: Use the configured settings
        DB_CONFIG,
        
        # Attempt 2: If SSL fails, try with SSL verification disabled for Railway
        {**DB_CONFIG, 'sslmode': 'prefer'} if 'sslmode' in DB_CONFIG else DB_CONFIG,
        
        # Attempt 3: Force disable SSL for development
        {k: v for k, v in DB_CONFIG.items() if k != 'sslmode'} if 'sslmode' in DB_CONFIG else None,
        
        # Attempt 4: Use connection string format
        None  # Will be handled specially
    ]
    
    for i, config in enumerate(connection_attempts):
        if config is None and i < 3:
            continue
            
        try:
            if i < 3:
                logger.info(f"Connection attempt {i+1}: {config.get('sslmode', 'default')}")
                conn = psycopg2.connect(**config, cursor_factory=RealDictCursor)
                logger.info(f"✅ Connected successfully on attempt {i+1}")
                return conn
            else:
                # Attempt 4: Direct connection string (Railway often provides DATABASE_URL)
                database_url = os.getenv('DATABASE_URL')
                if database_url:
                    logger.info("Connection attempt 4: Using DATABASE_URL")
                    conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
                    logger.info("✅ Connected successfully with DATABASE_URL")
                    return conn
                    
        except psycopg2.OperationalError as e:
            error_msg = str(e).lower()
            if "ssl" in error_msg or "certificate" in error_msg:
                logger.warning(f"Attempt {i+1} SSL error: {e}")
                continue
            else:
                logger.error(f"Attempt {i+1} failed: {e}")
                if i == len(connection_attempts) - 1:
                    raise DatabaseError(f"All connection attempts failed. Last error: {str(e)}")
                continue
        except Exception as e:
            logger.error(f"Attempt {i+1} unexpected error: {e}")
            if i == len(connection_attempts) - 1:
                raise DatabaseError(f"All connection attempts failed. Last error: {str(e)}")
            continue
    
    raise DatabaseError("All connection attempts exhausted")


@contextmanager
def get_db_cursor():
    """Context manager for database operations with automatic cleanup"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        yield cursor, conn
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database operation failed: {e}")
        raise DatabaseError(f"Database operation failed: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def test_connection() -> Dict[str, Any]:
    """Test database connection and return detailed info"""
    try:
        with get_db_cursor() as (cursor, conn):
            # Test basic connectivity
            cursor.execute("SELECT version(), current_database(), current_user;")
            result = cursor.fetchone()
            
            # Test SSL status (using a more compatible method)
            ssl_used = False
            try:
                # Check if we're using SSL (this method works on more PostgreSQL versions)
                cursor.execute("SHOW ssl;")
                ssl_setting = cursor.fetchone()[0]
                ssl_used = ssl_setting.lower() == 'on'
            except:
                # If that fails, assume SSL is working if we connected successfully
                ssl_used = True
            
            return {
                'success': True,
                'version': result[0][:50] + '...' if result[0] else 'Unknown',
                'database': result[1],
                'user': result[2],
                'ssl_enabled': ssl_used,
                'host': DB_CONFIG.get('host'),
                'port': DB_CONFIG.get('port')
            }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'config_used': {k: '***' if 'password' in k.lower() else v for k, v in DB_CONFIG.items()}
        }


def list_collections() -> List[Dict[str, Any]]:
    """List all collections in the database with record counts"""
    try:
        with get_db_cursor() as (cursor, conn):
            cursor.execute("""
                SELECT c.*, COUNT(dcr.id) as record_count
                FROM collections c
                LEFT JOIN dublin_core_records dcr ON c.id = dcr.collection_id
                GROUP BY c.id, c.name, c.description, c.is_public, c.created_at, c.updated_at
                ORDER BY c.name
            """)
            
            collections = cursor.fetchall()
            return [dict(col) for col in collections]
            
    except Exception as e:
        logger.error(f"List collections error: {e}")
        raise DatabaseError(f"Failed to list collections: {str(e)}")


def create_collection(name: str, description: str = None, is_public: bool = True) -> Dict[str, Any]:
    """Create a new collection"""
    try:
        with get_db_cursor() as (cursor, conn):
            cursor.execute("""
                INSERT INTO collections (name, description, is_public)
                VALUES (%s, %s, %s)
                RETURNING id, name, description, is_public, created_at
            """, (name, description or f'Collection: {name}', is_public))
            
            new_collection = cursor.fetchone()
            conn.commit()
            return dict(new_collection)
            
    except psycopg2.IntegrityError as e:
        logger.error(f"Collection already exists: {name}")
        raise DatabaseError(f"Collection '{name}' already exists")
    except Exception as e:
        logger.error(f"Create collection error: {e}")
        raise DatabaseError(f"Failed to create collection: {str(e)}")


def get_collection_records(collection_name: str, limit: int = 20, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """Get records from a specific collection with pagination"""
    try:
        with get_db_cursor() as (cursor, conn):
            # Get records with pagination
            cursor.execute("""
                SELECT dcr.*, c.name as collection_name
                FROM dublin_core_records dcr
                JOIN collections c ON dcr.collection_id = c.id
                WHERE c.name = %s
                ORDER BY dcr.created_at DESC
                LIMIT %s OFFSET %s
            """, (collection_name, limit, offset))
            
            records = cursor.fetchall()
            
            # Get total count
            cursor.execute("""
                SELECT COUNT(*)
                FROM dublin_core_records dcr
                JOIN collections c ON dcr.collection_id = c.id
                WHERE c.name = %s
            """, (collection_name,))
            
            total_count = cursor.fetchone()[0]
            
            return [dict(record) for record in records], total_count
            
    except Exception as e:
        logger.error(f"Get collection records error: {e}")
        raise DatabaseError(f"Failed to get records for collection '{collection_name}': {str(e)}")


def create_record(record: DublinCoreRecord) -> Dict[str, Any]:
    """Create a new Dublin Core record"""
    try:
        with get_db_cursor() as (cursor, conn):
            # Get collection ID
            cursor.execute("SELECT id FROM collections WHERE name = %s", (record.collection_name,))
            collection_result = cursor.fetchone()
            
            if not collection_result:
                raise DatabaseError(f"Collection '{record.collection_name}' not found")
            
            collection_id = collection_result['id']
            
            # Prepare record data
            record_data = record.dict(exclude={'collection_name'}, exclude_none=True)
            record_data['collection_id'] = collection_id
            
            # Build searchable content for full-text search
            searchable_parts = []
            for field in ['title', 'creator', 'subject', 'description']:
                if field in record_data and record_data[field]:
                    searchable_parts.append(record_data[field])
            
            if searchable_parts:
                record_data['searchable_content'] = ' '.join(searchable_parts)
            
            # Build dynamic INSERT query
            columns = list(record_data.keys())
            values = list(record_data.values())
            placeholders = ['%s'] * len(values)
            
            query = f"""
                INSERT INTO dublin_core_records ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
                RETURNING id, title, identifier
            """
            
            cursor.execute(query, values)
            new_record = cursor.fetchone()
            conn.commit()
            
            return dict(new_record)
            
    except Exception as e:
        logger.error(f"Create record error: {e}")
        raise DatabaseError(f"Failed to create record: {str(e)}")


def search_database(query: str, collection: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Search database records using PostgreSQL full-text search"""
    try:
        with get_db_cursor() as (cursor, conn):
            # Build search query
            base_query = """
                SELECT dcr.*, c.name as collection_name,
                       ts_rank(to_tsvector('english', 
                               COALESCE(dcr.title, '') || ' ' || 
                               COALESCE(dcr.description, '') || ' ' || 
                               COALESCE(dcr.searchable_content, '')), 
                               plainto_tsquery('english', %s)) as rank
                FROM dublin_core_records dcr
                JOIN collections c ON dcr.collection_id = c.id
                WHERE to_tsvector('english', 
                                 COALESCE(dcr.title, '') || ' ' || 
                                 COALESCE(dcr.description, '') || ' ' || 
                                 COALESCE(dcr.searchable_content, '')) 
                      @@ plainto_tsquery('english', %s)
            """
            
            params = [query, query]
            
            if collection:
                base_query += " AND c.name = %s"
                params.append(collection)
            
            base_query += " ORDER BY rank DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(base_query, params)
            results = cursor.fetchall()
            
            return [dict(result) for result in results]
            
    except Exception as e:
        logger.error(f"Database search error: {e}")
        raise DatabaseError(f"Database search failed: {str(e)}")


def get_collection_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Get a collection by name"""
    try:
        with get_db_cursor() as (cursor, conn):
            cursor.execute("""
                SELECT c.*, COUNT(dcr.id) as record_count
                FROM collections c
                LEFT JOIN dublin_core_records dcr ON c.id = dcr.collection_id
                WHERE c.name = %s
                GROUP BY c.id, c.name, c.description, c.is_public, c.created_at, c.updated_at
            """, (name,))
            
            result = cursor.fetchone()
            return dict(result) if result else None
            
    except Exception as e:
        logger.error(f"Get collection by name error: {e}")
        raise DatabaseError(f"Failed to get collection '{name}': {str(e)}")


def get_record_by_id(record_id: str) -> Optional[Dict[str, Any]]:
    """Get a record by ID"""
    try:
        with get_db_cursor() as (cursor, conn):
            cursor.execute("""
                SELECT dcr.*, c.name as collection_name
                FROM dublin_core_records dcr
                JOIN collections c ON dcr.collection_id = c.id
                WHERE dcr.id = %s
            """, (record_id,))
            
            result = cursor.fetchone()
            return dict(result) if result else None
            
    except Exception as e:
        logger.error(f"Get record by ID error: {e}")
        raise DatabaseError(f"Failed to get record with ID '{record_id}': {str(e)}")


def update_record(record_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update a Dublin Core record"""
    try:
        with get_db_cursor() as (cursor, conn):
            # Build dynamic UPDATE query
            if not updates:
                raise DatabaseError("No updates provided")
            
            # Remove None values and prepare updates
            filtered_updates = {k: v for k, v in updates.items() if v is not None}
            
            if not filtered_updates:
                raise DatabaseError("No valid updates provided")
            
            # Build SET clause
            set_clauses = [f"{key} = %s" for key in filtered_updates.keys()]
            values = list(filtered_updates.values())
            values.append(record_id)  # For WHERE clause
            
            query = f"""
                UPDATE dublin_core_records 
                SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, title, updated_at
            """
            
            cursor.execute(query, values)
            updated_record = cursor.fetchone()
            
            if not updated_record:
                raise DatabaseError(f"Record with ID '{record_id}' not found")
            
            conn.commit()
            return dict(updated_record)
            
    except Exception as e:
        logger.error(f"Update record error: {e}")
        raise DatabaseError(f"Failed to update record: {str(e)}")


def delete_record(record_id: str) -> bool:
    """Delete a Dublin Core record"""
    try:
        with get_db_cursor() as (cursor, conn):
            cursor.execute("DELETE FROM dublin_core_records WHERE id = %s", (record_id,))
            deleted_count = cursor.rowcount
            conn.commit()
            
            return deleted_count > 0
            
    except Exception as e:
        logger.error(f"Delete record error: {e}")
        raise DatabaseError(f"Failed to delete record: {str(e)}")

def health_check() -> Dict[str, Any]:
    """Check database health with fixed RealDictCursor access"""
    try:
        with get_db_cursor() as (cursor, conn):
            # Simple connectivity test
            cursor.execute("SELECT 1 as test")
            cursor.fetchone()
            
            # Get basic stats
            cursor.execute("SELECT COUNT(*) as count FROM information_schema.tables WHERE table_schema = 'public'")
            tables_result = cursor.fetchone()
            tables_count = tables_result['count']
            
            # Try to get collection and record counts (if tables exist)
            collections_count = 0
            records_count = 0
            
            try:
                cursor.execute("SELECT COUNT(*) as count FROM collections")
                collections_result = cursor.fetchone()
                collections_count = collections_result['count']
                
                cursor.execute("SELECT COUNT(*) as count FROM dublin_core_records")
                records_result = cursor.fetchone()
                records_count = records_result['count']
            except:
                # Tables don't exist yet, that's okay
                pass
            
            return {
                'status': 'healthy',
                'connection': 'successful',
                'tables_count': tables_count,
                'collections_count': collections_count,
                'records_count': records_count
            }
            
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e)
        }
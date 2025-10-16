"""
Fixed database.py - Works both locally and on Railway
Automatically detects environment and uses correct connection method
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
    """
    Get database configuration - intelligently detects local vs Railway environment
    Priority:
    1. DATABASE_PUBLIC_URL (for local connections via Railway TCP proxy)
    2. DATABASE_URL (for Railway internal connections AND local fallback)
    3. Individual PG variables
    """
    
    # Check if we're running locally (not in Railway deployment)
    is_local = not (
        os.getenv('RAILWAY_STATIC_URL') or 
        os.getenv('RAILWAY_PUBLIC_DOMAIN') or
        (os.getenv('PORT') and not os.getenv('RAILWAY_SHELL'))
    )
    
    if is_local:
        # LOCAL ENVIRONMENT - Use DATABASE_PUBLIC_URL first
        logger.info("🏠 Detected LOCAL environment - using DATABASE_PUBLIC_URL")
        
        database_public_url = os.getenv('DATABASE_PUBLIC_URL')
        if database_public_url:
            logger.info(f"Using DATABASE_PUBLIC_URL: {database_public_url[:40]}...")
            import urllib.parse
            try:
                parsed = urllib.parse.urlparse(database_public_url)
                return {
                    'host': parsed.hostname,
                    'port': parsed.port or 5432,
                    'database': parsed.path.lstrip('/'),
                    'user': parsed.username,
                    'password': parsed.password,
                    'sslmode': 'require',  # Railway requires SSL
                }
            except Exception as e:
                logger.warning(f"Failed to parse DATABASE_PUBLIC_URL: {e}")
        
        # Fallback for local: Try DATABASE_URL
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            logger.info("Falling back to DATABASE_URL for local environment")
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
        
        # Final fallback: Try to construct from TCP proxy variables
        tcp_proxy_domain = os.getenv('RAILWAY_TCP_PROXY_DOMAIN')
        tcp_proxy_port = os.getenv('RAILWAY_TCP_PROXY_PORT')
        
        if tcp_proxy_domain and tcp_proxy_port:
            logger.info(f"Using TCP Proxy: {tcp_proxy_domain}:{tcp_proxy_port}")
            return {
                'host': tcp_proxy_domain,
                'port': int(tcp_proxy_port),
                'database': os.getenv('PGDATABASE', 'railway'),
                'user': os.getenv('PGUSER', 'postgres'),
                'password': os.getenv('PGPASSWORD'),
                'sslmode': 'require',
            }
    
    else:
        # RAILWAY DEPLOYMENT - Use DATABASE_URL (no 'railway.internal' check needed)
        logger.info("🚂 Detected RAILWAY deployment - using DATABASE_URL")
        
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            logger.info(f"Using DATABASE_URL: {database_url[:40]}...")
            import urllib.parse
            try:
                parsed = urllib.parse.urlparse(database_url)
                config = {
                    'host': parsed.hostname,
                    'port': parsed.port or 5432,
                    'database': parsed.path.lstrip('/'),
                    'user': parsed.username,
                    'password': parsed.password,
                }
                
                # Add SSL mode only if not using internal Railway connection
                if 'railway.internal' not in str(parsed.hostname):
                    config['sslmode'] = 'require'
                
                logger.info(f"Using database host: {parsed.hostname}, database: {parsed.path.lstrip('/')}")
                return config
                
            except Exception as e:
                logger.warning(f"Failed to parse DATABASE_URL: {e}")
        
        # Fallback to individual variables (internal hostname)
        logger.info("Falling back to individual PG environment variables")
        return {
            'host': os.getenv('PGHOST', 'postgres.railway.internal'),
            'port': int(os.getenv('PGPORT', 5432)),
            'database': os.getenv('PGDATABASE', 'railway'),
            'user': os.getenv('PGUSER', 'postgres'),
            'password': os.getenv('PGPASSWORD'),
        }
    
    # Final fallback - use whatever we can find
    logger.warning("⚠️  Using fallback configuration")
    return {
        'host': os.getenv('PGHOST', 'localhost'),
        'port': int(os.getenv('PGPORT', 5432)),
        'database': os.getenv('PGDATABASE', 'postgres'),
        'user': os.getenv('PGUSER', 'postgres'),
        'password': os.getenv('PGPASSWORD', ''),
        'sslmode': 'require',
    }

# Get the configuration
DB_CONFIG = get_database_config()
logger.info(f"📊 Database config: host={DB_CONFIG.get('host')}, port={DB_CONFIG.get('port')}, database={DB_CONFIG.get('database')}")

class DatabaseError(Exception):
    """Custom exception for database operations"""
    pass


def get_db_connection():
    """Get PostgreSQL database connection with smart error handling"""
    connection_attempts = [
        # Attempt 1: Use the configured settings
        DB_CONFIG,
        
        # Attempt 2: Try with different SSL mode if first fails
        {**DB_CONFIG, 'sslmode': 'prefer'} if 'sslmode' in DB_CONFIG else None,
        
        # Attempt 3: Try without SSL
        {k: v for k, v in DB_CONFIG.items() if k != 'sslmode'},
    ]
    
    last_error = None
    
    for i, config in enumerate(connection_attempts):
        if config is None:
            continue
            
        try:
            logger.info(f"🔌 Connection attempt {i+1}/{len(connection_attempts)}")
            logger.debug(f"Attempting connection to: {config.get('host')}:{config.get('port')}")
            conn = psycopg2.connect(**config, cursor_factory=RealDictCursor)
            logger.info(f"✅ Connected successfully on attempt {i+1}")
            return conn
                    
        except psycopg2.OperationalError as e:
            last_error = e
            error_msg = str(e).lower()
            
            if "ssl" in error_msg or "certificate" in error_msg:
                logger.warning(f"⚠️  Attempt {i+1} SSL error: {e}")
                continue
            elif "translate host name" in error_msg or "name or service not known" in error_msg:
                logger.error(f"❌ Attempt {i+1} - Cannot resolve hostname: {config.get('host')}")
                logger.error("💡 Make sure you're using DATABASE_PUBLIC_URL for local connections!")
                continue
            elif "connection refused" in error_msg:
                logger.error(f"❌ Attempt {i+1} - Connection refused to: {config.get('host')}:{config.get('port')}")
                continue
            elif "no such file or directory" in error_msg and "/tmp" in error_msg:
                logger.error(f"❌ Attempt {i+1} - Unix socket error (this should not happen on Railway): {e}")
                continue
            else:
                logger.error(f"❌ Attempt {i+1} failed: {e}")
                if i == len([c for c in connection_attempts if c]) - 1:
                    break
                continue
                
        except Exception as e:
            last_error = e
            logger.error(f"❌ Attempt {i+1} unexpected error: {e}")
            if i == len([c for c in connection_attempts if c]) - 1:
                break
            continue
    
    # All attempts failed
    error_message = f"All connection attempts failed. Last error: {str(last_error)}"
    logger.error(f"💥 {error_message}")
    logger.error("🔍 Troubleshooting:")
    logger.error("   - Check if DATABASE_URL is set correctly")
    logger.error("   - For local: Check if DATABASE_PUBLIC_URL is set")
    logger.error("   - Check if Railway services are running: railway status")
    logger.error("   - Try: railway run python your_script.py")
    
    raise DatabaseError(error_message)


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
            
            # Test SSL status (fixed for RealDictCursor)
            ssl_used = False
            try:
                cursor.execute("SHOW ssl;")
                ssl_result = cursor.fetchone()
                # RealDictCursor returns a dict, get the 'ssl' key value
                ssl_setting = list(ssl_result.values())[0] if ssl_result else 'off'
                ssl_used = str(ssl_setting).lower() == 'on'
            except:
                ssl_used = True  # Assume SSL if we connected successfully
            
            return {
                'success': True,
                'version': result['version'][:50] + '...' if result and result.get('version') else 'Unknown',
                'database': result['current_database'] if result else 'Unknown',
                'user': result['current_user'] if result else 'Unknown',
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
    """Check database health"""
    try:
        with get_db_cursor() as (cursor, conn):
            # Simple connectivity test
            cursor.execute("SELECT 1 as test")
            cursor.fetchone()
            
            # Get basic stats
            cursor.execute("SELECT COUNT(*) as count FROM information_schema.tables WHERE table_schema = 'public'")
            tables_result = cursor.fetchone()
            tables_count = tables_result['count']
            
            # Try to get collection and record counts
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
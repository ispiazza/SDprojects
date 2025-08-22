"""
Database operations for Museum Archive API
Handles all PostgreSQL database interactions
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

# Check if we're in Railway environment and use internal connection
railway_env = os.getenv('RAILWAY_ENVIRONMENT')
if railway_env:
    # Use internal Railway connection
    DB_CONFIG = {
        'host': 'postgres.railway.internal',
        'port': 5432,
        'database': os.getenv('PGDATABASE', 'railway'),
        'user': os.getenv('PGUSER', 'postgres'),
        'password': os.getenv('PGPASSWORD'),
        # No SSL needed for internal connections
    }
    logger.info("Using internal Railway database connection")
else:
    # Use external connection for local development
    DB_CONFIG = {
        'host': os.getenv('PGHOST'),
        'port': int(os.getenv('PGPORT', 5432)),
        'database': os.getenv('PGDATABASE'),
        'user': os.getenv('PGUSER'),
        'password': os.getenv('PGPASSWORD'),
        'sslmode': 'prefer',
    }
    logger.info("Using external database connection")


class DatabaseError(Exception):
    """Custom exception for database operations"""
    pass


def get_db_connection():
    """Get PostgreSQL database connection using Railway environment variables"""
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise DatabaseError(f"Database connection failed: {str(e)}")


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
            cursor.execute("SELECT 1")
            cursor.fetchone()
            
            # Get some basic stats
            cursor.execute("SELECT COUNT(*) FROM collections")
            collections_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM dublin_core_records")
            records_count = cursor.fetchone()[0]
            
            return {
                'status': 'healthy',
                'collections_count': collections_count,
                'records_count': records_count
            }
            
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e)
        }
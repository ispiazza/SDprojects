from datetime import datetime
from typing import List, Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import os

class ProcessingDatabase:
    def __init__(self):
        self.conn_params = {
            'host': os.getenv('PGHOST'),
            'port': os.getenv('PGPORT', 5432),
            'database': os.getenv('PGDATABASE'),
            'user': os.getenv('PGUSER'),
            'password': os.getenv('PGPASSWORD')
        }
    
    def get_connection(self):
        return psycopg2.connect(**self.conn_params)
    
    # ===== SESSION OPERATIONS =====
    
    def create_session(self, session_id: str, uploaded_filename: str, session_path: str):
        """Create a new processing session"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO processing_sessions 
                    (session_id, uploaded_filename, session_path, status)
                    VALUES (%s, %s, %s, 'created')
                """, (session_id, uploaded_filename, session_path))
                conn.commit()
    
    def update_session_status(self, session_id: str, status: str):
        """Update session status"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE processing_sessions 
                    SET status = %s
                    WHERE session_id = %s
                """, (status, session_id))
                conn.commit()
    
    def update_session_stats(self, session_id: str, stats: Dict):
        """Update session statistics"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE processing_sessions 
                    SET total_items = %s,
                        duplicates_found = %s,
                        quality_issues = %s,
                        completed_at = NOW()
                    WHERE session_id = %s
                """, (
                    stats.get('total_items', 0),
                    stats.get('duplicates_found', 0),
                    stats.get('quality_issues', 0),
                    session_id
                ))
                conn.commit()
    
    # ===== TEMP ITEMS OPERATIONS =====
    
    def insert_temp_item(self, item_data: Dict):
        """Insert an item into temp table"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO processing_items_temp 
                    (session_id, directory, id_number, front_image_path, back_image_path,
                     handwritten_notes, printed_labels, addresses, other_markings,
                     extraction_notes, flags, processed_at, model_used)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    item_data['session_id'],
                    item_data['directory'],
                    item_data.get('id_number', ''),
                    item_data['front_image_path'],
                    item_data['back_image_path'],
                    item_data.get('handwritten_notes', ''),
                    item_data.get('printed_labels', ''),
                    item_data.get('addresses', ''),
                    item_data.get('other_markings', ''),
                    item_data.get('extraction_notes', ''),
                    item_data.get('flags', []),
                    item_data.get('processed_at'),
                    item_data.get('model_used', 'gpt-4o')
                ))
                conn.commit()
    
    def get_temp_items(self, session_id: str) -> List[Dict]:
        """Get all temp items for a session"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM processing_items_temp 
                    WHERE session_id = %s
                    ORDER BY directory
                """, (session_id,))
                return [dict(row) for row in cur.fetchall()]
    
    def update_temp_item(self, item_id: int, updates: Dict):
        """Update a temp item (for editing)"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Build dynamic UPDATE query based on what's being updated
                set_parts = []
                values = []
                
                for key, value in updates.items():
                    if key in ['handwritten_notes', 'printed_labels', 'addresses', 
                              'other_markings', 'extraction_notes', 'id_number']:
                        set_parts.append(f"{key} = %s")
                        values.append(value)
                
                if set_parts:
                    set_parts.append("updated_at = NOW()")
                    values.append(item_id)
                    
                    query = f"""
                        UPDATE processing_items_temp 
                        SET {', '.join(set_parts)}
                        WHERE id = %s
                    """
                    cur.execute(query, values)
                    conn.commit()
    
    # ===== IMPORT TO MAIN DATABASE =====
    
    def import_session_to_main(self, session_id: str) -> int:
        """Move items from temp table to main items table"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get all temp items
                cur.execute("""
                    SELECT * FROM processing_items_temp 
                    WHERE session_id = %s
                """, (session_id,))
                temp_items = cur.fetchall()
                
                imported_count = 0
                
                for item in temp_items:
                    # Insert into main items table
                    cur.execute("""
                        INSERT INTO items 
                        (title, description, subject, date_created, creator, 
                         coverage, rights, identifier, session_id, imported_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        RETURNING id
                    """, (
                        f"Item {item['directory']} - ID: {item['id_number']}",  # title
                        f"{item['handwritten_notes']} {item['extraction_notes']}",  # description
                        item['printed_labels'],  # subject
                        None,  # date_created (can be parsed from metadata)
                        None,  # creator
                        item['addresses'],  # coverage
                        None,  # rights
                        item['id_number'],  # identifier
                        session_id
                    ))
                    
                    imported_count += 1
                
                # Delete temp items after import
                cur.execute("""
                    DELETE FROM processing_items_temp 
                    WHERE session_id = %s
                """, (session_id,))
                
                # Update session status
                cur.execute("""
                    UPDATE processing_sessions 
                    SET status = 'imported', imported_at = NOW()
                    WHERE session_id = %s
                """, (session_id,))
                
                conn.commit()
                return imported_count
    
    # ===== SESSION HISTORY =====
    
    def get_all_sessions(self) -> List[Dict]:
        """Get all processing sessions"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM processing_sessions 
                    ORDER BY created_at DESC
                """)
                return [dict(row) for row in cur.fetchall()]
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get a specific session"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM processing_sessions 
                    WHERE session_id = %s
                """, (session_id,))
                row = cur.fetchone()
                return dict(row) if row else None
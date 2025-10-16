"""
Database operations for HeritageAI
"""

from .database import (
    get_db_connection,
    create_tables,
    insert_record,
    search_records,
    get_all_collections,
    create_collection,
    get_collection_items
)

from .processing_operations import ProcessingDatabase

__all__ = [
    'get_db_connection',
    'create_tables',
    'insert_record',
    'search_records',
    'get_all_collections',
    'create_collection',
    'get_collection_items',
    'ProcessingDatabase'
]
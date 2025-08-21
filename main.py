#!/usr/bin/env python3
"""
Updated Main FastAPI application for Railway deployment
Museum Archive API with PostgreSQL and ChromaDB integration
"""
import os
import sys
import logging
from typing import List, Dict, Any, Optional
import pandas as pd
import io
from fastapi import FastAPI, HTTPException, Depends, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path

# Create necessary directories
os.makedirs("chromadb_data", exist_ok=True)
os.makedirs("sessions", exist_ok=True)
os.makedirs("media", exist_ok=True)
os.makedirs("static", exist_ok=True)

# Import our modules with error handling
try:
    from vector_search import vector_search
    VECTOR_SEARCH_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Vector search not available: {e}")
    VECTOR_SEARCH_AVAILABLE = False
    vector_search = None

try:
    from updated_chatbot import ModernMuseumChatbot
    CHATBOT_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Chatbot not available: {e}")
    CHATBOT_AVAILABLE = False
    ModernMuseumChatbot = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Museum Archive API",
    description="Railway-deployed API for PostgreSQL and ChromaDB integration with museum archive",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
if Path("static").exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Database connection function with Railway environment variables
def get_db_connection():
    """Get PostgreSQL database connection using Railway environment variables"""
    try:
        # Railway automatically provides these environment variables
        conn = psycopg2.connect(
            host=os.getenv('PGHOST'),
            port=os.getenv('PGPORT', 5432),
            database=os.getenv('PGDATABASE'),
            user=os.getenv('PGUSER'),
            password=os.getenv('PGPASSWORD'),
            cursor_factory=RealDictCursor
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

# Initialize chatbot if available
chatbot = None
if CHATBOT_AVAILABLE:
    try:
        chatbot = ModernMuseumChatbot()
        logger.info("Museum chatbot initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize chatbot: {e}")
        chatbot = None

# Pydantic models
class DocumentRequest(BaseModel):
    collection_name: str
    document_id: str
    text: str
    metadata: Dict[str, Any] = {}

class SearchRequest(BaseModel):
    collection_name: str
    query_text: str
    limit: int = 10
    metadata_filter: Dict[str, Any] = {}

class ChatMessage(BaseModel):
    message: str
    user_context: Dict[str, Any] = {}

class CollectionRequest(BaseModel):
    collection_name: str
    metadata: Dict[str, Any] = {}

class DublinCoreRecord(BaseModel):
    title: Optional[str] = None
    creator: Optional[str] = None
    subject: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    contributor: Optional[str] = None
    date_created: Optional[str] = None
    type: Optional[str] = None
    format: Optional[str] = None
    identifier: Optional[str] = None
    source: Optional[str] = None
    language: str = "en"
    relation: Optional[str] = None
    coverage: Optional[str] = None
    rights: Optional[str] = None
    collection_name: str = "Museum Archive"

# Health check endpoint
@app.get("/")
async def root():
    """Root endpoint with basic info"""
    return {
        "message": "Museum Archive API - Railway Deployment",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "health": "/api/health",
            "search": "/api/search",
            "chat": "/api/chat",
            "collections": "/api/collections"
        }
    }

@app.get("/api/health")
async def health_check():
    """Enhanced health check endpoint for Railway"""
    try:
        # Check database connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        db_status = "healthy"
        
        # Check vector search
        vector_status = "not_available"
        if VECTOR_SEARCH_AVAILABLE and vector_search:
            try:
                vector_health = vector_search.health_check()
                vector_status = vector_health.get('status', 'unknown')
            except:
                vector_status = "error"
        
        # Check chatbot
        chatbot_status = "available" if chatbot else "not_available"
        
        return {
            "success": True,
            "status": "healthy",
            "environment": "railway",
            "database": db_status,
            "vector_search": vector_status,
            "chatbot": chatbot_status,
            "message": "Museum Archive API is running on Railway"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "success": False,
            "status": "unhealthy",
            "error": str(e)
        }

# Database endpoints
@app.get("/api/collections")
async def list_collections():
    """List all collections in the database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT c.*, COUNT(dcr.id) as record_count
            FROM collections c
            LEFT JOIN dublin_core_records dcr ON c.id = dcr.collection_id
            GROUP BY c.id, c.name, c.description, c.is_public, c.created_at, c.updated_at
            ORDER BY c.name
        """)
        
        collections = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "data": {
                "collections": [dict(col) for col in collections],
                "total_collections": len(collections)
            }
        }
        
    except Exception as e:
        logger.error(f"List collections error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/collections")
async def create_collection(request: CollectionRequest):
    """Create a new collection"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO collections (name, description, is_public)
            VALUES (%s, %s, %s)
            RETURNING id, name, description, is_public, created_at
        """, (
            request.collection_name,
            request.metadata.get('description', f'Collection: {request.collection_name}'),
            request.metadata.get('is_public', True)
        ))
        
        new_collection = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        # Also create ChromaDB collection if available
        if VECTOR_SEARCH_AVAILABLE and vector_search:
            try:
                vector_search.create_collection(request.collection_name, request.metadata)
            except Exception as ve:
                logger.warning(f"ChromaDB collection creation failed: {ve}")
        
        return {
            "success": True,
            "message": f"Collection '{request.collection_name}' created successfully",
            "data": dict(new_collection)
        }
        
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=400, detail="Collection already exists")
    except Exception as e:
        logger.error(f"Create collection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/collections/{collection_name}/records")
async def get_collection_records(
    collection_name: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Get records from a specific collection"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
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
        
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "data": {
                "records": [dict(record) for record in records],
                "total_records": total_count,
                "limit": limit,
                "offset": offset,
                "collection_name": collection_name
            }
        }
        
    except Exception as e:
        logger.error(f"Get collection records error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/records")
async def create_record(record: DublinCoreRecord):
    """Create a new Dublin Core record"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get collection ID
        cursor.execute("SELECT id FROM collections WHERE name = %s", (record.collection_name,))
        collection_result = cursor.fetchone()
        
        if not collection_result:
            raise HTTPException(status_code=404, detail="Collection not found")
        
        collection_id = collection_result['id']
        
        # Prepare record data
        record_data = record.dict(exclude={'collection_name'}, exclude_none=True)
        record_data['collection_id'] = collection_id
        
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
        cursor.close()
        conn.close()
        
        # Add to ChromaDB if available
        if VECTOR_SEARCH_AVAILABLE and vector_search and record.title:
            try:
                searchable_text = f"Title: {record.title or ''}"
                if record.description:
                    searchable_text += f" Description: {record.description}"
                if record.creator:
                    searchable_text += f" Creator: {record.creator}"
                
                vector_search.add_document(
                    collection_name="museum_archive",
                    document_id=f"record_{new_record['id']}",
                    text=searchable_text,
                    metadata={
                        'title': record.title,
                        'creator': record.creator or '',
                        'type': record.type or '',
                        'record_id': str(new_record['id'])
                    }
                )
            except Exception as ve:
                logger.warning(f"ChromaDB addition failed: {ve}")
        
        return {
            "success": True,
            "message": "Record created successfully",
            "data": dict(new_record)
        }
        
    except Exception as e:
        logger.error(f"Create record error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search/database")
async def search_database(
    q: str = Query(..., description="Search query"),
    collection: Optional[str] = Query(None, description="Collection name filter"),
    limit: int = Query(10, ge=1, le=50)
):
    """Search database records using PostgreSQL full-text search"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
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
        
        params = [q, q]
        
        if collection:
            base_query += " AND c.name = %s"
            params.append(collection)
        
        base_query += " ORDER BY rank DESC LIMIT %s"
        params.append(limit)
        
        cursor.execute(base_query, params)
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "data": {
                "results": [dict(result) for result in results],
                "query": q,
                "collection_filter": collection,
                "total_results": len(results)
            }
        }
        
    except Exception as e:
        logger.error(f"Database search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Vector search endpoints (if available)
if VECTOR_SEARCH_AVAILABLE:
    @app.post("/api/search/vector")
    async def vector_search_endpoint(request: SearchRequest):
        """Perform vector search using ChromaDB"""
        try:
            results = vector_search.search(
                request.collection_name,
                request.query_text,
                request.limit,
                request.metadata_filter
            )
            
            return {
                "success": True,
                "message": f"Found {len(results)} results",
                "data": {
                    "results": results,
                    "query": request.query_text,
                    "collection": request.collection_name,
                    "search_type": "vector"
                }
            }
            
        except Exception as e:
            logger.error(f"Vector search error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/search/hybrid")
    async def hybrid_search_endpoint(
        query: str = Query(..., description="Search query"),
        collection: str = Query("museum_archive", description="Collection name"),
        limit: int = Query(10, ge=1, le=50)
    ):
        """Perform hybrid search combining database and vector search"""
        try:
            # Get database results
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT dcr.*, c.name as collection_name,
                       ts_rank(to_tsvector('english', 
                               COALESCE(dcr.title, '') || ' ' || 
                               COALESCE(dcr.description, '')), 
                               plainto_tsquery('english', %s)) as rank
                FROM dublin_core_records dcr
                JOIN collections c ON dcr.collection_id = c.id
                WHERE to_tsvector('english', 
                                 COALESCE(dcr.title, '') || ' ' || 
                                 COALESCE(dcr.description, '')) 
                      @@ plainto_tsquery('english', %s)
                ORDER BY rank DESC LIMIT %s
            """, (query, query, limit))
            
            db_results = [dict(row) for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            
            # Combine with vector search
            hybrid_results = vector_search.hybrid_search(
                collection, query, db_results, limit
            )
            
            return {
                "success": True,
                "message": f"Hybrid search completed with {len(hybrid_results)} results",
                "data": {
                    "results": hybrid_results,
                    "query": query,
                    "search_type": "hybrid"
                }
            }
            
        except Exception as e:
            logger.error(f"Hybrid search error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

# Chatbot endpoints (if available)
if chatbot:
    @app.post("/api/chat")
    async def chat_with_bot(request: ChatMessage):
        """Chat with the museum archive bot"""
        try:
            answer, media_urls = chatbot.answer_question(request.message)
            
            return {
                "success": True,
                "data": {
                    "message": answer,
                    "media_urls": media_urls,
                    "query": request.message,
                    "timestamp": pd.Timestamp.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Chat error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

# File upload endpoint
@app.post("/api/upload/csv")
async def upload_csv(file: UploadFile = File(...)):
    """Upload CSV file and import data to database"""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV file")
    
    try:
        contents = await file.read()
        df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
        
        logger.info(f"CSV file uploaded with {len(df)} rows")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get default collection
        cursor.execute("SELECT id FROM collections WHERE name = 'Museum Archive'")
        collection_result = cursor.fetchone()
        collection_id = collection_result['id'] if collection_result else None
        
        if not collection_id:
            raise HTTPException(status_code=500, detail="Default collection not found")
        
        # Column mapping
        column_mapping = {
            'title': 'title',
            'creator': 'creator',
            'subject': 'subject',
            'description': 'description',
            'type': 'type',
            'format': 'format',
            'identifier': 'identifier',
            'date_created': 'date_created'
        }
        
        inserted_rows = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                record_data = {'collection_id': collection_id}
                
                for csv_col, db_col in column_mapping.items():
                    if csv_col in df.columns and pd.notna(row[csv_col]):
                        record_data[db_col] = str(row[csv_col])
                
                if len(record_data) > 1:  # More than just collection_id
                    columns = list(record_data.keys())
                    values = list(record_data.values())
                    placeholders = ['%s'] * len(values)
                    
                    query = f"""
                        INSERT INTO dublin_core_records ({', '.join(columns)})
                        VALUES ({', '.join(placeholders)})
                    """
                    
                    cursor.execute(query, values)
                    inserted_rows += 1
                
            except Exception as row_error:
                errors.append(f"Row {index + 1}: {str(row_error)}")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "message": "CSV upload completed",
            "data": {
                "total_rows": len(df),
                "inserted_rows": inserted_rows,
                "errors_count": len(errors),
                "errors": errors[:5] if errors else []
            }
        }
        
    except Exception as e:
        logger.error(f"CSV upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Static file serving for web interface
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Simple dashboard for the museum archive"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Museum Archive Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 800px; margin: 0 auto; }
            .endpoint { background: #f5f5f5; padding: 10px; margin: 10px 0; border-radius: 5px; }
            .method { font-weight: bold; color: #0066cc; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🏛️ Museum Archive API - Railway</h1>
            <p>Welcome to the Museum Archive API running on Railway!</p>
            
            <h2>Available Endpoints:</h2>
            
            <div class="endpoint">
                <div class="method">GET /api/health</div>
                <div>Health check and system status</div>
            </div>
            
            <div class="endpoint">
                <div class="method">GET /api/collections</div>
                <div>List all collections</div>
            </div>
            
            <div class="endpoint">
                <div class="method">GET /api/search/database?q=query</div>
                <div>Search database records</div>
            </div>
            
            <div class="endpoint">
                <div class="method">POST /api/chat</div>
                <div>Chat with the museum bot</div>
            </div>
            
            <div class="endpoint">
                <div class="method">POST /api/upload/csv</div>
                <div>Upload CSV data</div>
            </div>
            
            <h2>Quick Test:</h2>
            <p>Try: <a href="/api/health">/api/health</a></p>
            <p>Search: <a href="/api/search/database?q=museum">/api/search/database?q=museum</a></p>
            
            <h2>Documentation:</h2>
            <p>API Documentation: <a href="/docs">/docs</a></p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Run the application
if __name__ == "__main__":
    # Railway automatically sets the PORT environment variable
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"Starting Museum Archive API on port {port}")
    logger.info(f"Vector search available: {VECTOR_SEARCH_AVAILABLE}")
    logger.info(f"Chatbot available: {chatbot is not None}")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
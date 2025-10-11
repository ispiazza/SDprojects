#!/usr/bin/env python3
"""
Updated Main FastAPI application with Pipeline Integration
Museum Archive API with PostgreSQL, ChromaDB, and Image Pipeline
"""
import os
import logging
from typing import Optional
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn
from pathlib import Path

# Import our modules
from models.base import DocumentRequest, SearchRequest, ChatMessage, CollectionRequest, DublinCoreRecord
import database
import upload

# Import the new pipeline integration
from pipeline_integration import pipeline_router

from dotenv import load_dotenv
load_dotenv(override=True)

# Create necessary directories
os.makedirs("chromadb_data", exist_ok=True)
os.makedirs("sessions", exist_ok=True)
os.makedirs("media", exist_ok=True)
os.makedirs("static", exist_ok=True)

# Import optional modules with error handling
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
    title="Museum Archive API with Pipeline",
    description="Complete museum archive system with image processing pipeline",
    version="3.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the pipeline router
app.include_router(pipeline_router)

# Serve static files
if Path("static").exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize chatbot if available
chatbot = None
if CHATBOT_AVAILABLE:
    try:
        chatbot = ModernMuseumChatbot()
        logger.info("Museum chatbot initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize chatbot: {e}")
        chatbot = None

# ==========================================
# CORE API ENDPOINTS
# ==========================================

@app.get("/")
async def root():
    """Root endpoint with basic info"""
    return {
        "message": "Museum Archive API with Pipeline Integration",
        "version": "3.0.0",
        "status": "running",
        "features": {
            "database": "PostgreSQL",
            "vector_search": "ChromaDB" if VECTOR_SEARCH_AVAILABLE else "Unavailable",
            "chatbot": "Available" if chatbot else "Unavailable",
            "pipeline": "Integrated"
        },
        "endpoints": {
            "health": "/api/health",
            "search": "/api/search",
            "chat": "/api/chat",
            "collections": "/api/collections",
            "pipeline": "/api/pipeline"
        }
    }

@app.get("/api/health")
async def health_check():
    """Enhanced health check endpoint"""
    try:
        # Check database connection
        db_health = database.health_check()
        
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
        
        # Check pipeline directories
        pipeline_status = "available"
        required_dirs = ['sessions', 'media']
        for dir_name in required_dirs:
            if not Path(dir_name).exists():
                pipeline_status = "directories_missing"
                break
        
        return {
            "success": True,
            "status": "healthy",
            "environment": "production",
            "database": db_health.get('status', 'unknown'),
            "vector_search": vector_status,
            "chatbot": chatbot_status,
            "pipeline": pipeline_status,
            "message": "Museum Archive API with Pipeline is running"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "success": False,
            "status": "unhealthy",
            "error": str(e)
        }

# ==========================================
# DATABASE ENDPOINTS
# ==========================================

@app.get("/api/collections")
async def list_collections():
    """List all collections in the database"""
    try:
        collections = database.list_collections()
        return {
            "success": True,
            "data": {
                "collections": collections,
                "total_collections": len(collections)
            }
        }
    except database.DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/collections")
async def create_collection(request: CollectionRequest):
    """Create a new collection"""
    try:
        new_collection = database.create_collection(
            name=request.collection_name,
            description=request.metadata.get('description'),
            is_public=request.metadata.get('is_public', True)
        )
        
        # Also create ChromaDB collection if available
        if VECTOR_SEARCH_AVAILABLE and vector_search:
            try:
                vector_search.create_collection(request.collection_name, request.metadata)
            except Exception as ve:
                logger.warning(f"ChromaDB collection creation failed: {ve}")
        
        return {
            "success": True,
            "message": f"Collection '{request.collection_name}' created successfully",
            "data": new_collection
        }
    except database.DatabaseError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/collections/{collection_name}/records")
async def get_collection_records(
    collection_name: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Get records from a specific collection"""
    try:
        records, total_count = database.get_collection_records(collection_name, limit, offset)
        
        return {
            "success": True,
            "data": {
                "records": records,
                "total_records": total_count,
                "limit": limit,
                "offset": offset,
                "collection_name": collection_name
            }
        }
    except database.DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/records")
async def create_record(record: DublinCoreRecord):
    """Create a new Dublin Core record"""
    try:
        new_record = database.create_record(record)
        
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
            "data": new_record
        }
    except database.DatabaseError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search/database")
async def search_database_endpoint(
    q: str = Query(..., description="Search query"),
    collection: Optional[str] = Query(None, description="Collection name filter"),
    limit: int = Query(10, ge=1, le=50)
):
    """Search database records using PostgreSQL full-text search"""
    try:
        results = database.search_database(q, collection, limit)
        
        return {
            "success": True,
            "data": {
                "results": results,
                "query": q,
                "collection_filter": collection,
                "total_results": len(results)
            }
        }
    except database.DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# VECTOR SEARCH ENDPOINTS (if available)
# ==========================================

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
            db_results = database.search_database(query, None, limit)
            
            # Combine with vector search
            if hasattr(vector_search, 'hybrid_search'):
                hybrid_results = vector_search.hybrid_search(
                    collection, query, db_results, limit
                )
            else:
                # Simple combination if hybrid_search method doesn't exist
                vector_results = vector_search.search(collection, query, limit//2)
                hybrid_results = db_results + [
                    {
                        'title': r.get('metadata', {}).get('title', 'Unknown'),
                        'creator': r.get('metadata', {}).get('creator', ''),
                        'description': r.get('document', ''),
                        'similarity_score': r.get('similarity', 0),
                        'search_type': 'vector'
                    } for r in vector_results
                ]
            
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

# ==========================================
# CHATBOT ENDPOINTS (if available)
# ==========================================

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

# ==========================================
# UPLOAD ENDPOINTS
# ==========================================

@app.post("/api/upload/csv")
async def upload_csv_endpoint(file: UploadFile = File(...)):
    """Upload CSV file and import data to database"""
    return await upload.upload_csv(file)

@app.get("/upload", response_class=HTMLResponse)
async def upload_interface():
    """CSV Upload Interface"""
    return upload.get_upload_interface()

# ==========================================
# WEB INTERFACE ENDPOINTS
# ==========================================

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Enhanced dashboard with pipeline integration"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Museum Archive Dashboard</title>
        <style>
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                margin: 0; 
                padding: 40px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }
            .container { 
                max-width: 1200px; 
                margin: 0 auto; 
                background: white;
                border-radius: 15px;
                padding: 30px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
            }
            .header h1 {
                color: #2c3e50;
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            .features-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }
            .feature-card {
                background: #f8f9fa;
                padding: 25px;
                border-radius: 10px;
                border-left: 4px solid #667eea;
                transition: transform 0.2s ease;
            }
            .feature-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }
            .feature-title {
                font-size: 1.3em;
                font-weight: bold;
                color: #333;
                margin-bottom: 10px;
            }
            .feature-description {
                color: #666;
                margin-bottom: 15px;
            }
            .feature-button {
                background: #667eea;
                color: white;
                padding: 8px 16px;
                border-radius: 5px;
                text-decoration: none;
                display: inline-block;
                transition: background 0.2s ease;
            }
            .feature-button:hover {
                background: #5a67d8;
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 15px;
                margin: 20px 0;
            }
            .stat-box {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                border-radius: 10px;
                text-align: center;
            }
            .stat-number {
                font-size: 2em;
                font-weight: bold;
                margin-bottom: 5px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏛️ Museum Archive Dashboard</h1>
                <p>Complete Digital Archive Management System</p>
            </div>

            <div class="stats">
                <div class="stat-box">
                    <div class="stat-number" id="collections-count">-</div>
                    <div class="stat-label">Collections</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="records-count">-</div>
                    <div class="stat-label">Records</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="api-status">✅</div>
                    <div class="stat-label">API Status</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="pipeline-status">🏭</div>
                    <div class="stat-label">Pipeline</div>
                </div>
            </div>
            
            <div class="features-grid">
                <div class="feature-card">
                    <div class="feature-title">🏭 Image Processing Pipeline</div>
                    <div class="feature-description">
                        Complete pipeline for processing scanned documents: classification, 
                        text extraction, and database import.
                    </div>
                    <a href="/api/pipeline/interface" class="feature-button">Start Pipeline</a>
                </div>
                
                <div class="feature-card">
                    <div class="feature-title">📁 Collection Management</div>
                    <div class="feature-description">
                        Browse and manage your digital collections with full metadata support.
                    </div>
                    <a href="/api/collections" class="feature-button">View Collections</a>
                </div>
                
                <div class="feature-card">
                    <div class="feature-title">📊 CSV Data Import</div>
                    <div class="feature-description">
                        Upload CSV files to bulk import metadata records into your collections.
                    </div>
                    <a href="/upload" class="feature-button">Upload CSV</a>
                </div>
                
                <div class="feature-card">
                    <div class="feature-title">🔍 Advanced Search</div>
                    <div class="feature-description">
                        Powerful search across all collections using full-text and semantic search.
                    </div>
                    <a href="/api/search/database?q=pottery" class="feature-button">Try Search</a>
                </div>
                
                <div class="feature-card">
                    <div class="feature-title">🤖 AI Assistant</div>
                    <div class="feature-description">
                        Chat with our AI assistant to explore the archive and get instant answers.
                    </div>
                    <a href="#" onclick="testChat()" class="feature-button">Test Chat</a>
                </div>
                
                <div class="feature-card">
                    <div class="feature-title">📖 API Documentation</div>
                    <div class="feature-description">
                        Complete API documentation for developers and integrations.
                    </div>
                    <a href="/docs" class="feature-button">View Docs</a>
                </div>
            </div>
        </div>

        <script>
            // Load dashboard stats
            async function loadStats() {
                try {
                    const healthResponse = await fetch('/api/health');
                    const health = await healthResponse.json();
                    
                    if (health.success) {
                        document.getElementById('api-status').textContent = '✅';
                        document.getElementById('pipeline-status').textContent = 
                            health.pipeline === 'available' ? '✅' : '⚠️';
                    } else {
                        document.getElementById('api-status').textContent = '❌';
                    }

                    const collectionsResponse = await fetch('/api/collections');
                    const collections = await collectionsResponse.json();
                    
                    if (collections.success) {
                        document.getElementById('collections-count').textContent = 
                            collections.data.total_collections;
                        
                        const totalRecords = collections.data.collections.reduce(
                            (sum, col) => sum + (col.record_count || 0), 0
                        );
                        document.getElementById('records-count').textContent = totalRecords;
                    }
                } catch (error) {
                    console.error('Failed to load stats:', error);
                    document.getElementById('api-status').textContent = '❌';
                }
            }

            async function testChat() {
                try {
                    const response = await fetch('/api/chat', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            message: 'Hello! What can you tell me about the museum archive?'
                        })
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        alert(`AI Assistant Response:\n\n${result.data.message}`);
                    } else {
                        alert('AI Assistant is currently unavailable.');
                    }
                } catch (error) {
                    alert('AI Assistant is currently unavailable.');
                }
            }

            // Load stats when page loads
            document.addEventListener('DOMContentLoaded', loadStats);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# ==========================================
# APPLICATION STARTUP
# ==========================================

if __name__ == "__main__":
    # Get port from environment or default
    port = int(os.environ.get("PORT", 8000))
    
    logger.info(f"Starting Museum Archive API with Pipeline on port {port}")
    logger.info(f"Vector search available: {VECTOR_SEARCH_AVAILABLE}")
    logger.info(f"Chatbot available: {chatbot is not None}")
    logger.info("Pipeline integration: ✅ Available")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
"""
Fixed Vector Search API using ChromaDB
Provides semantic search capabilities for museum archive
"""
import os
import logging
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VectorSearchEngine:
    def __init__(self):
        """Initialize vector search engine with ChromaDB and SentenceTransformer"""
        self.model_name = "sentence-transformers/all-MiniLM-L6-v2"
        self.embedding_model = None
        self.chroma_client = None
        self.initialize()
    
    def initialize(self):
        """Initialize ChromaDB client and embedding model"""
        try:
            # Initialize ChromaDB with fixed settings
            self.chroma_client = chromadb.PersistentClient(
                path="./chromadb_data",
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                    # Removed the problematic CORS settings
                )
            )
            
            # Initialize sentence transformer model
            self.embedding_model = SentenceTransformer(self.model_name)
            
            logger.info("Vector search engine initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize vector search engine: {e}")
            # Don't raise - allow app to continue without vector search
            self.chroma_client = None
            self.embedding_model = None
    
    def create_collection(self, collection_name: str, metadata: Dict = None) -> bool:
        """Create or get ChromaDB collection"""
        if not self.chroma_client:
            return False
            
        try:
            collection = self.chroma_client.get_or_create_collection(
                name=collection_name,
                metadata=metadata or {}
            )
            logger.info(f"Collection '{collection_name}' created/retrieved successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create collection '{collection_name}': {e}")
            return False
    
    def add_document(self, collection_name: str, document_id: str, 
                    text: str, metadata: Dict = None) -> bool:
        """Add document to ChromaDB collection with vector embedding"""
        if not self.chroma_client or not self.embedding_model:
            return False
            
        try:
            collection = self.chroma_client.get_or_create_collection(collection_name)
            
            # Generate embedding
            embedding = self.embedding_model.encode(text).tolist()
            
            # Add to collection
            collection.add(
                embeddings=[embedding],
                documents=[text],
                metadatas=[metadata or {}],
                ids=[document_id]
            )
            
            logger.info(f"Added document '{document_id}' to collection '{collection_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add document to collection: {e}")
            return False
    
    def search(self, collection_name: str, query_text: str, 
              limit: int = 10, metadata_filter: Dict = None) -> List[Dict]:
        """Perform semantic search in ChromaDB collection"""
        if not self.chroma_client or not self.embedding_model:
            return []
            
        try:
            collection = self.chroma_client.get_collection(collection_name)
            
            # Generate query embedding
            query_embedding = self.embedding_model.encode(query_text).tolist()
            
            # Perform search
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where=metadata_filter
            )
            
            # Format results
            formatted_results = []
            if results['ids'] and len(results['ids'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    formatted_results.append({
                        'id': results['ids'][0][i],
                        'document': results['documents'][0][i] if results['documents'] else '',
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                        'distance': results['distances'][0][i] if results['distances'] else 0,
                        'similarity': 1 - (results['distances'][0][i] if results['distances'] else 0)
                    })
            
            logger.info(f"Search completed for query '{query_text}' in collection '{collection_name}', found {len(formatted_results)} results")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Failed to perform search: {e}")
            return []
    
    def health_check(self) -> Dict:
        """Check the health of the vector search engine"""
        try:
            if not self.chroma_client:
                return {
                    'status': 'unavailable',
                    'error': 'ChromaDB client not initialized'
                }
                
            collections = self.chroma_client.list_collections()
            model_loaded = self.embedding_model is not None
            
            return {
                'status': 'healthy',
                'model_loaded': model_loaded,
                'model_name': self.model_name,
                'collections_count': len(collections),
                'collections': [col.name for col in collections]
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e)
            }

# Global instance - with error handling
try:
    vector_search = VectorSearchEngine()
except Exception as e:
    logger.error(f"Failed to initialize global vector search: {e}")
    vector_search = None
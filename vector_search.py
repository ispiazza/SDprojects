"""
Vector Search API using ChromaDB
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
            # Initialize ChromaDB
            self.chroma_client = chromadb.PersistentClient(
                path="./chromadb_data",
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Initialize sentence transformer model
            self.embedding_model = SentenceTransformer(self.model_name)
            
            logger.info("Vector search engine initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize vector search engine: {e}")
            raise
    
    def create_collection(self, collection_name: str, metadata: Dict = None) -> bool:
        """Create or get ChromaDB collection"""
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
    
    def update_document(self, collection_name: str, document_id: str,
                       text: str, metadata: Dict = None) -> bool:
        """Update existing document in ChromaDB collection"""
        try:
            collection = self.chroma_client.get_collection(collection_name)
            
            # Generate new embedding
            embedding = self.embedding_model.encode(text).tolist()
            
            # Update document
            collection.update(
                embeddings=[embedding],
                documents=[text],
                metadatas=[metadata or {}],
                ids=[document_id]
            )
            
            logger.info(f"Updated document '{document_id}' in collection '{collection_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update document: {e}")
            return False
    
    def delete_document(self, collection_name: str, document_id: str) -> bool:
        """Delete document from ChromaDB collection"""
        try:
            collection = self.chroma_client.get_collection(collection_name)
            collection.delete(ids=[document_id])
            
            logger.info(f"Deleted document '{document_id}' from collection '{collection_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete document: {e}")
            return False
    
    def search(self, collection_name: str, query_text: str, 
              limit: int = 10, metadata_filter: Dict = None) -> List[Dict]:
        """Perform semantic search in ChromaDB collection"""
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
    
    def hybrid_search(self, collection_name: str, query_text: str,
                     postgres_results: List[Dict], limit: int = 10) -> List[Dict]:
        """Combine semantic search with PostgreSQL full-text search results"""
        try:
            # Get semantic search results
            semantic_results = self.search(collection_name, query_text, limit * 2)
            
            # Create a mapping of record IDs to semantic scores
            semantic_scores = {}
            for result in semantic_results:
                if 'metadata' in result and 'record_id' in result['metadata']:
                    record_id = result['metadata']['record_id']
                    semantic_scores[record_id] = result['similarity']
            
            # Combine with PostgreSQL results
            combined_results = []
            
            # Add PostgreSQL results with semantic scores
            for pg_result in postgres_results:
                record_id = pg_result.get('id')
                semantic_score = semantic_scores.get(record_id, 0)
                text_score = pg_result.get('rank', 0)
                
                # Calculate combined score (weighted average)
                combined_score = (semantic_score * 0.6) + (text_score * 0.4)
                
                combined_results.append({
                    **pg_result,
                    'semantic_score': semantic_score,
                    'text_score': text_score,
                    'combined_score': combined_score,
                    'search_type': 'hybrid'
                })
            
            # Add purely semantic results that weren't in PostgreSQL results
            pg_record_ids = {result.get('id') for result in postgres_results}
            for result in semantic_results:
                if 'metadata' in result and 'record_id' in result['metadata']:
                    record_id = result['metadata']['record_id']
                    if record_id not in pg_record_ids:
                        combined_results.append({
                            'id': record_id,
                            'title': result['metadata'].get('title', ''),
                            'creator': result['metadata'].get('creator', ''),
                            'type': result['metadata'].get('type', ''),
                            'semantic_score': result['similarity'],
                            'text_score': 0,
                            'combined_score': result['similarity'] * 0.6,
                            'search_type': 'semantic_only'
                        })
            
            # Sort by combined score
            combined_results.sort(key=lambda x: x['combined_score'], reverse=True)
            
            return combined_results[:limit]
            
        except Exception as e:
            logger.error(f"Failed to perform hybrid search: {e}")
            return postgres_results[:limit]  # Fallback to PostgreSQL results
    
    def get_similar_documents(self, collection_name: str, document_id: str,
                             limit: int = 5) -> List[Dict]:
        """Find documents similar to a given document"""
        try:
            collection = self.chroma_client.get_collection(collection_name)
            
            # Get the document
            doc_result = collection.get(ids=[document_id])
            if not doc_result['documents'] or len(doc_result['documents']) == 0:
                return []
            
            document_text = doc_result['documents'][0]
            
            # Find similar documents
            return self.search(collection_name, document_text, limit + 1)
            
        except Exception as e:
            logger.error(f"Failed to find similar documents: {e}")
            return []
    
    def get_collection_stats(self, collection_name: str) -> Dict:
        """Get statistics about a ChromaDB collection"""
        try:
            collection = self.chroma_client.get_collection(collection_name)
            count = collection.count()
            
            return {
                'collection_name': collection_name,
                'document_count': count,
                'embedding_model': self.model_name
            }
            
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {}
    
    def list_collections(self) -> List[Dict]:
        """List all ChromaDB collections with their stats"""
        try:
            collections = self.chroma_client.list_collections()
            collection_info = []
            
            for collection in collections:
                stats = self.get_collection_stats(collection.name)
                collection_info.append(stats)
            
            return collection_info
            
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []
    
    def health_check(self) -> Dict:
        """Check the health of the vector search engine"""
        try:
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

# Global instance
vector_search = VectorSearchEngine()

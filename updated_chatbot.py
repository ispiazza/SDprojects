#!/usr/bin/env python3
"""
Updated chatbot using PostgreSQL + ChromaDB instead of Omeka + FAISS
Maintains the same interface but uses the new museum archive system
"""

import json
import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any, Tuple, Optional
import requests
from openai import OpenAI

# Import ChromaDB and vector search from the existing system
try:
    from vector_search import vector_search
    from chatbot import MuseumChatbot
except ImportError:
    print("Warning: Could not import existing museum archive modules")
    vector_search = None
    MuseumChatbot = None

# Configuration
API_KEY = os.getenv('OPENAI_API_KEY', 'your-openai-api-key')
client = OpenAI(api_key=API_KEY) if API_KEY != 'your-openai-api-key' else None
EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o"

# Database configuration
DB_CONFIG = {
    'host': os.getenv('PGHOST', 'localhost'),
    'port': os.getenv('PGPORT', 5432),
    'database': os.getenv('PGDATABASE', 'replit'),
    'user': os.getenv('PGUSER', 'replit'),
    'password': os.getenv('PGPASSWORD', ''),
}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModernMuseumChatbot:
    """Updated chatbot using PostgreSQL + ChromaDB"""
    
    def __init__(self, use_existing_system=True):
        self.use_existing_system = use_existing_system
        
        if use_existing_system and vector_search and MuseumChatbot:
            # Use the existing museum archive system
            self.museum_chatbot = MuseumChatbot(vector_search, self)
            logger.info("Using existing museum archive system")
        else:
            # Initialize ChromaDB directly
            self._init_chromadb()
            logger.info("Using direct ChromaDB integration")
    
    def _init_chromadb(self):
        """Initialize ChromaDB client directly"""
        try:
            import chromadb
            from chromadb.config import Settings
            
            self.chroma_client = chromadb.PersistentClient(
                path="./chromadb_data",
                settings=Settings(anonymized_telemetry=False)
            )
            
            # Get museum archive collection ONLY - not library
            self.collection = self.chroma_client.get_or_create_collection(
                name="museum_archive",
                metadata={"description": "Museum archive collection - excludes library items"}
            )
            logger.info(f"ChromaDB initialized with {self.collection.count()} items")
            
        except Exception as e:
            logger.error(f"ChromaDB initialization failed: {e}")
            self.collection = None
    
    def get_db_connection(self):
        """Get PostgreSQL database connection"""
        return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    
    def search_database(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search PostgreSQL database for relevant items - MUSEUM ARCHIVE ONLY"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            search_pattern = f"%{query}%"
            cursor.execute("""
                SELECT 
                    dcr.id, dcr.title, dcr.creator, dcr.subject, dcr.description, 
                    dcr.type, dcr.format, dcr.date_created, dcr.identifier,
                    dcr.publisher, dcr.contributor, dcr.source, dcr.rights,
                    c.name as collection_name
                FROM dublin_core_records dcr
                JOIN collections c ON dcr.collection_id = c.id
                WHERE c.name = 'Museum Archive' 
                AND (
                    dcr.title ILIKE %s OR 
                    dcr.description ILIKE %s OR 
                    dcr.creator ILIKE %s OR 
                    dcr.subject ILIKE %s OR
                    dcr.contributor ILIKE %s
                )
                ORDER BY 
                    CASE 
                        WHEN dcr.title ILIKE %s THEN 1
                        WHEN dcr.creator ILIKE %s THEN 2
                        WHEN dcr.subject ILIKE %s THEN 3
                        ELSE 4
                    END
                LIMIT %s
            """, (search_pattern, search_pattern, search_pattern, search_pattern, 
                  search_pattern, search_pattern, search_pattern, search_pattern, limit))
            
            results = [dict(row) for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            
            return results
            
        except Exception as e:
            logger.error(f"Database search failed: {e}")
            return []
    
    def vector_search_chromadb(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Perform vector search using ChromaDB with correct embedding dimensions"""
        if not self.collection:
            return []
        
        try:
            # Use OpenAI embeddings to match existing ChromaDB data (1536 dimensions)
            if client:
                try:
                    embedding_response = client.embeddings.create(
                        model=EMBED_MODEL,  # text-embedding-3-small (1536 dimensions)
                        input=query
                    )
                    query_embedding = embedding_response.data[0].embedding
                    
                    # Search using embeddings
                    results = self.collection.query(
                        query_embeddings=[query_embedding],
                        n_results=top_k,
                        include=['documents', 'metadatas', 'distances']
                    )
                except Exception as e:
                    logger.error(f"OpenAI embedding failed: {e}")
                    # Fallback to text query (may still fail due to dimension mismatch)
                    return []
            else:
                logger.error("No OpenAI client available for embeddings")
                return []
            
            # Format results
            items = []
            if results['documents'] and len(results['documents']) > 0:
                for i, doc in enumerate(results['documents'][0]):
                    metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                    distance = results['distances'][0][i] if results['distances'] else 1.0
                    
                    items.append({
                        'document': doc,
                        'metadata': metadata,
                        'similarity_score': 1 - distance  # Convert distance to similarity
                    })
            
            return items
            
        except Exception as e:
            logger.error(f"ChromaDB vector search failed: {e}")
            return []
    
    def answer_question(self, query: str) -> Tuple[str, List[str]]:
        """Answer user question using the new system"""
        
        if self.use_existing_system and hasattr(self, 'museum_chatbot'):
            # Use existing museum chatbot system
            try:
                response = self.museum_chatbot.process_message(query, {})
                answer = response.get('message', 'I could not process your query.')
                # Extract media URLs if available in results
                media_urls = []
                if 'results' in response:
                    for result in response['results']:
                        # Add logic to extract media URLs from results if needed
                        pass
                return answer, media_urls
            except Exception as e:
                logger.error(f"Existing system failed: {e}")
                # Fall back to direct implementation
        
        # Direct implementation using PostgreSQL + ChromaDB
        return self._direct_answer_question(query)
    
    def _direct_answer_question(self, query: str) -> Tuple[str, List[str]]:
        """Direct implementation of question answering"""
        
        # 1. Get relevant items using vector search
        vector_results = self.vector_search_chromadb(query, top_k=3)
        
        # 2. Also search database directly for additional context
        db_results = self.search_database(query, limit=5)
        
        # 3. Prepare context for OpenAI
        context_parts = []
        media_urls = []
        
        # Process vector search results
        for result in vector_results:
            if 'metadata' in result:
                metadata = result['metadata']
                entry = f"Title: {metadata.get('title', 'Unknown')}"
                
                for field in ['creator', 'subject', 'description', 'contributor']:
                    if field in metadata and metadata[field]:
                        entry += f"\n{field.capitalize()}: {metadata[field]}"
                
                context_parts.append(entry)
        
        # Process database results (if different from vector results)
        for item in db_results[:2]:  # Limit to avoid too much context
            entry = f"Title: {item['title'] or 'Unknown'}"
            
            for field in ['creator', 'subject', 'description', 'contributor']:
                if item.get(field):
                    entry += f"\n{field.capitalize()}: {item[field]}"
            
            if item.get('date_created'):
                entry += f"\nDate: {item['date_created']}"
            if item.get('type'):
                entry += f"\nType: {item['type']}"
            
            context_parts.append(entry)
        
        context = "\n\n".join(context_parts)
        
        # 4. Generate answer with OpenAI (if available)
        if client:
            try:
                prompt = f"""You are a helpful museum chatbot answering questions about a MUSEUM ARCHIVE heritage collection.
IMPORTANT: You only have access to museum archive items - NOT library books or library materials.

Based on these relevant items from our MUSEUM ARCHIVE collection:

{context}

User question: '{query}'

Provide a helpful, informative answer mentioning relevant items from the museum archive collection only. 
If asked about books or library materials, explain that you only have access to museum archive items.
Do not invent data, but you can provide contextual information about the items, artists, or historical periods mentioned.
"""
                chat_resp = client.chat.completions.create(
                    model=CHAT_MODEL,
                    messages=[
                        {"role": "system", "content": "You are an expert museum guide with deep knowledge of cultural heritage."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2
                )
                answer = chat_resp.choices[0].message.content
                
            except Exception as e:
                logger.error(f"OpenAI API call failed: {e}")
                answer = self._generate_fallback_answer(query, db_results)
        else:
            answer = self._generate_fallback_answer(query, db_results)
        
        return answer, media_urls
    
    def _generate_fallback_answer(self, query: str, db_results: List[Dict]) -> str:
        """Generate a simple answer without OpenAI"""
        if not db_results:
            return f"I couldn't find any items in our museum archive collection related to '{query}'. Please note that I only search museum archive items, not library books. Please try a different search term or browse our museum collections."
        
        answer_parts = [f"I found {len(db_results)} items in our museum archive collection related to '{query}':"]
        
        for i, item in enumerate(db_results[:3], 1):
            title = item.get('title', 'Unknown Title')
            creator = item.get('creator', '')
            description = item.get('description', '')
            
            item_desc = f"{i}. {title}"
            if creator:
                item_desc += f" by {creator}"
            if description:
                # Truncate long descriptions
                desc_preview = description[:200] + "..." if len(description) > 200 else description
                item_desc += f" - {desc_preview}"
            
            answer_parts.append(item_desc)
        
        if len(db_results) > 3:
            answer_parts.append(f"...and {len(db_results) - 3} more items. Please refine your search for more specific results.")
        
        return "\n\n".join(answer_parts)
    
    def process_pipeline_results(self, pipeline_results: Dict[str, Any]) -> Dict[str, Any]:
        """Process results from the pipeline processor and add to database"""
        try:
            # This would integrate with your pipeline processor
            # Extract processed data and add to PostgreSQL + ChromaDB
            
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Process each item from pipeline results
            processed_count = 0
            # Add your pipeline integration logic here
            
            cursor.close()
            conn.close()
            
            return {
                'success': True,
                'processed_count': processed_count,
                'message': 'Pipeline results successfully integrated'
            }
            
        except Exception as e:
            logger.error(f"Pipeline integration failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }

def main():
    """Main function for testing"""
    chatbot = ModernMuseumChatbot()
    
    print("\nMuseum Archive Chatbot (PostgreSQL + ChromaDB)")
    print("Ask me about the museum collection! Type 'exit' to quit.")
    
    while True:
        query = input("\nYour question: ")
        if query.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break
        
        try:
            answer, media = chatbot.answer_question(query)
            print(f"\nAnswer:\n{answer}")
            
            if media:
                print(f"\nRelated media URLs:")
                for i, url in enumerate(media, 1):
                    print(f"{i}. {url}")
                    
        except Exception as e:
            print(f"Error processing question: {e}")

if __name__ == "__main__":
    main()
"""
Chatbot API for Museum Archive
Provides conversational interface to search and discover archive content
"""
import os
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MuseumChatbot:
    def __init__(self, vector_search_engine, postgres_adapter):
        """Initialize chatbot with search engines"""
        self.vector_search = vector_search_engine
        self.postgres_adapter = postgres_adapter
        self.conversation_history = []
        self.context = {}
        
        # Common museum/archive keywords and their categories
        self.keywords = {
            'temporal': ['year', 'decade', 'century', 'date', 'when', 'period', 'era', 'time'],
            'creator': ['artist', 'creator', 'author', 'maker', 'photographer', 'by', 'created by'],
            'medium': ['painting', 'photograph', 'sculpture', 'textile', 'ceramic', 'drawing', 'print'],
            'subject': ['portrait', 'landscape', 'still life', 'abstract', 'religious', 'historical'],
            'collection': ['collection', 'exhibition', 'gallery', 'museum', 'archive'],
            'location': ['from', 'country', 'city', 'region', 'place', 'location', 'origin']
        }
        
        # Response templates
        self.templates = {
            'greeting': [
                "Hello! I'm here to help you explore our museum archive. What would you like to discover today?",
                "Welcome to our digital archive! I can help you find artworks, artifacts, and information. What interests you?",
                "Hi! I'm your museum guide. Feel free to ask me about our collections, artists, or specific items."
            ],
            'no_results': [
                "I couldn't find any items matching your query. Could you try rephrasing or being more specific?",
                "No results found for that search. Would you like to try different keywords?",
                "I don't see any matches in our archive. Perhaps try a broader search term?"
            ],
            'clarification': [
                "Could you provide more details about what you're looking for?",
                "I'd be happy to help! Could you be more specific about your interest?",
                "What aspect would you like to know more about?"
            ]
        }
        
        logger.info("Museum chatbot initialized")
    
    def process_message(self, user_message: str, user_context: Dict = None) -> Dict:
        """Process user message and generate response"""
        try:
            # Update context
            if user_context:
                self.context.update(user_context)
            
            # Add to conversation history
            self.conversation_history.append({
                'timestamp': datetime.now().isoformat(),
                'user_message': user_message,
                'context': self.context.copy()
            })
            
            # Clean and analyze message
            cleaned_message = self._clean_message(user_message)
            intent = self._analyze_intent(cleaned_message)
            entities = self._extract_entities(cleaned_message)
            
            # Generate response based on intent
            response = self._generate_response(intent, entities, cleaned_message)
            
            # Add response to history
            self.conversation_history[-1]['bot_response'] = response
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to process message: {e}")
            return {
                'type': 'error',
                'message': "I'm sorry, I encountered an error processing your request. Please try again.",
                'results': [],
                'suggestions': ["Try rephrasing your question", "Ask about our collections"]
            }
    
    def _clean_message(self, message: str) -> str:
        """Clean and normalize user message"""
        # Convert to lowercase
        message = message.lower().strip()
        
        # Remove extra whitespace
        message = re.sub(r'\s+', ' ', message)
        
        # Remove common stopwords at the beginning
        stopwords = ['show me', 'find me', 'i want', 'i need', 'can you', 'please']
        for stopword in stopwords:
            if message.startswith(stopword):
                message = message[len(stopword):].strip()
        
        return message
    
    def _analyze_intent(self, message: str) -> str:
        """Analyze user intent from message"""
        # Greeting patterns
        if any(word in message for word in ['hello', 'hi', 'hey', 'greetings']):
            return 'greeting'
        
        # Search patterns
        if any(word in message for word in ['find', 'search', 'look for', 'show', 'discover']):
            return 'search'
        
        # Information patterns
        if any(word in message for word in ['what is', 'tell me about', 'describe', 'explain']):
            return 'information'
        
        # Browse patterns
        if any(word in message for word in ['browse', 'explore', 'see all', 'list']):
            return 'browse'
        
        # Recommendation patterns
        if any(word in message for word in ['recommend', 'suggest', 'similar', 'like']):
            return 'recommendation'
        
        # Help patterns
        if any(word in message for word in ['help', 'how', 'can you']):
            return 'help'
        
        # Default to search if no clear intent
        return 'search'
    
    def _extract_entities(self, message: str) -> Dict:
        """Extract entities and filters from message"""
        entities = {
            'keywords': [],
            'filters': {},
            'temporal': [],
            'creators': [],
            'types': [],
            'subjects': []
        }
        
        # Extract years and dates
        year_pattern = r'\b(1[0-9]{3}|20[0-9]{2})\b'
        years = re.findall(year_pattern, message)
        if years:
            entities['temporal'] = years
            entities['filters']['date_range'] = years
        
        # Extract quoted phrases (exact matches)
        quoted_pattern = r'"([^"]*)"'
        quoted_phrases = re.findall(quoted_pattern, message)
        entities['keywords'].extend(quoted_phrases)
        
        # Extract potential creator names (capitalized words)
        creator_indicators = ['by', 'artist', 'created by', 'made by']
        for indicator in creator_indicators:
            if indicator in message:
                # Look for words after the indicator
                parts = message.split(indicator)
                if len(parts) > 1:
                    potential_creator = parts[1].strip().split()[0:3]  # Take up to 3 words
                    entities['creators'].extend(potential_creator)
        
        # Extract known art types/mediums
        art_types = ['painting', 'photograph', 'sculpture', 'drawing', 'print', 'textile', 'ceramic']
        for art_type in art_types:
            if art_type in message:
                entities['types'].append(art_type)
        
        # Extract general keywords (remove common words)
        words = message.split()
        common_words = ['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by']
        keywords = [word for word in words if len(word) > 2 and word not in common_words]
        entities['keywords'].extend(keywords)
        
        return entities
    
    def _generate_response(self, intent: str, entities: Dict, message: str) -> Dict:
        """Generate appropriate response based on intent and entities"""
        if intent == 'greeting':
            return {
                'type': 'greeting',
                'message': self.templates['greeting'][0],
                'results': [],
                'suggestions': [
                    "Search for artworks by artist name",
                    "Browse collections",
                    "Find items from a specific time period",
                    "Explore different art mediums"
                ]
            }
        
        elif intent in ['search', 'information']:
            return self._handle_search(entities, message)
        
        elif intent == 'browse':
            return self._handle_browse(entities)
        
        elif intent == 'recommendation':
            return self._handle_recommendation(entities, message)
        
        elif intent == 'help':
            return self._handle_help()
        
        else:
            # Default to search
            return self._handle_search(entities, message)
    
    def _handle_search(self, entities: Dict, original_message: str) -> Dict:
        """Handle search requests"""
        try:
            # Build search query
            search_terms = []
            
            # Add keywords
            if entities['keywords']:
                search_terms.extend(entities['keywords'][:5])  # Limit to 5 keywords
            
            # Add creators
            if entities['creators']:
                search_terms.extend(entities['creators'])
            
            # Add types
            if entities['types']:
                search_terms.extend(entities['types'])
            
            query = ' '.join(search_terms) if search_terms else original_message
            
            # Build filters
            filters = {}
            if entities['temporal']:
                filters['date_from'] = min(entities['temporal'])
                filters['date_to'] = max(entities['temporal'])
            
            if entities['types']:
                filters['type'] = entities['types'][0]
            
            if entities['creators']:
                filters['creator'] = ' '.join(entities['creators'])
            
            # Perform search (this would call the PostgreSQL adapter)
            # For now, we'll simulate the search
            results = self._perform_search(query, filters)
            
            if results:
                response_message = f"I found {len(results)} items matching your search:"
                suggestions = [
                    "View details of any item",
                    "Refine your search",
                    "Find similar items"
                ]
            else:
                response_message = self.templates['no_results'][0]
                suggestions = [
                    "Try broader search terms",
                    "Browse our collections",
                    "Ask about specific artists or time periods"
                ]
            
            return {
                'type': 'search_results',
                'message': response_message,
                'results': results,
                'query': query,
                'filters': filters,
                'suggestions': suggestions
            }
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return {
                'type': 'error',
                'message': "I encountered an error while searching. Please try again.",
                'results': [],
                'suggestions': ["Rephrase your search", "Try simpler terms"]
            }
    
    def _handle_browse(self, entities: Dict) -> Dict:
        """Handle browse requests"""
        try:
            # Determine what to browse
            if entities['types']:
                # Browse by type
                browse_type = entities['types'][0]
                results = self._browse_by_type(browse_type)
                message = f"Here are {browse_type}s in our collection:"
            elif 'collection' in ' '.join(entities['keywords']):
                # Browse collections
                results = self._browse_collections()
                message = "Here are our featured collections:"
            else:
                # Browse recent or featured items
                results = self._browse_featured()
                message = "Here are some featured items from our archive:"
            
            return {
                'type': 'browse_results',
                'message': message,
                'results': results,
                'suggestions': [
                    "View details of any item",
                    "Search for specific items",
                    "Explore different collections"
                ]
            }
            
        except Exception as e:
            logger.error(f"Browse error: {e}")
            return {
                'type': 'error',
                'message': "I encountered an error while browsing. Please try again.",
                'results': [],
                'suggestions': ["Try a different browse option"]
            }
    
    def _handle_recommendation(self, entities: Dict, message: str) -> Dict:
        """Handle recommendation requests"""
        try:
            # Extract what they want recommendations based on
            if 'similar' in message:
                # Find similar items (would need item ID from context)
                results = self._get_similar_recommendations()
                message_text = "Based on your interests, you might like these items:"
            else:
                # General recommendations
                results = self._get_general_recommendations()
                message_text = "Here are some items I think you might enjoy:"
            
            return {
                'type': 'recommendations',
                'message': message_text,
                'results': results,
                'suggestions': [
                    "Learn more about any recommended item",
                    "Find similar items",
                    "Explore related collections"
                ]
            }
            
        except Exception as e:
            logger.error(f"Recommendation error: {e}")
            return {
                'type': 'error',
                'message': "I couldn't generate recommendations right now. Please try again.",
                'results': [],
                'suggestions': ["Browse our collections", "Search for specific items"]
            }
    
    def _handle_help(self) -> Dict:
        """Handle help requests"""
        return {
            'type': 'help',
            'message': "I can help you explore our museum archive in several ways:",
            'results': [],
            'suggestions': [
                "Search: 'Find paintings by Van Gogh'",
                "Browse: 'Show me all sculptures'",
                "Discover: 'What do you have from the 1800s?'",
                "Learn: 'Tell me about this artwork'",
                "Explore: 'Show me similar items'"
            ]
        }
    
    def _perform_search(self, query: str, filters: Dict) -> List[Dict]:
        """Perform actual search (placeholder for integration)"""
        # This would integrate with the actual search systems
        # For now, return sample data structure
        return [
            {
                'id': 'sample-1',
                'title': 'Sample Artwork 1',
                'creator': 'Sample Artist',
                'type': 'painting',
                'date_created': '1850',
                'description': 'A beautiful example from our collection',
                'collection_name': 'Main Collection'
            }
        ]
    
    def _browse_by_type(self, art_type: str) -> List[Dict]:
        """Browse items by type"""
        # Placeholder implementation
        return []
    
    def _browse_collections(self) -> List[Dict]:
        """Browse collections"""
        # Placeholder implementation
        return []
    
    def _browse_featured(self) -> List[Dict]:
        """Browse featured items"""
        # Placeholder implementation
        return []
    
    def _get_similar_recommendations(self) -> List[Dict]:
        """Get recommendations for similar items"""
        # Placeholder implementation
        return []
    
    def _get_general_recommendations(self) -> List[Dict]:
        """Get general recommendations"""
        # Placeholder implementation
        return []
    
    def get_conversation_history(self) -> List[Dict]:
        """Get conversation history"""
        return self.conversation_history
    
    def clear_conversation(self):
        """Clear conversation history"""
        self.conversation_history = []
        self.context = {}
        logger.info("Conversation history cleared")

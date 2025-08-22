#!/usr/bin/env python3
# models/base.py

"""
Pydantic models for the Museum Archive API
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel

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


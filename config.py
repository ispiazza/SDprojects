#!/usr/bin/env python3
"""
Configuration file for Museum Archive Pipeline Integration
Centralizes all configuration settings
"""

import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent
SCRIPT_DIR = BASE_DIR
MEDIA_DIR = BASE_DIR / "media"
SESSION_STORAGE = BASE_DIR / "sessions"

# Pipeline script paths
CLASSIFY_RENAME_SCRIPT = BASE_DIR / "media_upload" / "classify_rename.py"
TEXT_EXTRACTOR_SCRIPT = BASE_DIR / "media_upload" / "text_extractor.py"
TABLE_GENERATOR_SCRIPT = BASE_DIR / "media_upload" / "table_generator.py"

# Create directories if they don't exist
for directory in [MEDIA_DIR, SESSION_STORAGE]:
    directory.mkdir(exist_ok=True)

# Logging configuration
LOGGING_LEVEL = os.getenv('LOGGING_LEVEL', 'INFO')
LOGGING_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Pipeline processing limits
MAX_FILE_SIZE_MB = 100
SESSION_TIMEOUT_HOURS = 24
MAX_CONCURRENT_SESSIONS = 10

# Database configuration (from environment)
DATABASE_CONFIG = {
    'host': os.getenv('PGHOST', 'localhost'),
    'port': int(os.getenv('PGPORT', 5432)),
    'database': os.getenv('PGDATABASE', 'museum_archive'),
    'user': os.getenv('PGUSER', 'postgres'),
    'password': os.getenv('PGPASSWORD', ''),
}

# API configuration
API_CONFIG = {
    'title': "Museum Archive API with Pipeline",
    'description': "Complete museum archive system with image processing pipeline",
    'version': "3.0.0",
    'cors_origins': ["*"],  # Configure appropriately for production
    'docs_url': "/docs",
    'redoc_url': "/redoc"
}

# Pipeline step configuration
PIPELINE_STEPS = {
    'scan_formatting': {
        'name': 'Scan Formatting',
        'description': 'Extract and organize images from ZIP archive',
        'timeout': 1800,  # 30 minutes
        'required': True
    },
    'classify_rename': {
        'name': 'Classification & Renaming',
        'description': 'Classify images and rename according to standards',
        'timeout': 1800,  # 30 minutes
        'required': False
    },
    'text_extraction': {
        'name': 'Text Extraction',
        'description': 'Extract text content using OCR',
        'timeout': 3600,  # 60 minutes
        'required': False
    },
    'generate_table': {
        'name': 'Generate Summary Table',
        'description': 'Create summary table and detect duplicates',
        'timeout': 600,   # 10 minutes
        'required': True
    },
    'database_import': {
        'name': 'Database Import',
        'description': 'Import processed data to PostgreSQL database',
        'timeout': 900,   # 15 minutes
        'required': True
    }
}

# File type configurations
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp'}
SUPPORTED_ARCHIVE_EXTENSIONS = {'.zip', '.7z', '.rar', '.tar', '.tar.gz'}

# Vector search configuration
VECTOR_SEARCH_CONFIG = {
    'model_name': 'sentence-transformers/all-MiniLM-L6-v2',
    'chromadb_path': './chromadb_data',
    'collection_name': 'museum_archive',
    'embedding_dimension': 384
}

# Quality thresholds
QUALITY_THRESHOLDS = {
    'image_min_width': 300,
    'image_min_height': 300,
    'text_min_length': 10,
    'confidence_threshold': 0.7
}

# Export for easy import
__all__ = [
    'BASE_DIR', 'SCRIPT_DIR', 'MEDIA_DIR', 'SESSION_STORAGE',
    'CLASSIFY_RENAME_SCRIPT', 'TEXT_EXTRACTOR_SCRIPT', 'TABLE_GENERATOR_SCRIPT',
    'LOGGING_LEVEL', 'LOGGING_FORMAT',
    'MAX_FILE_SIZE_MB', 'SESSION_TIMEOUT_HOURS', 'MAX_CONCURRENT_SESSIONS',
    'DATABASE_CONFIG', 'API_CONFIG', 'PIPELINE_STEPS',
    'SUPPORTED_IMAGE_EXTENSIONS', 'SUPPORTED_ARCHIVE_EXTENSIONS',
    'VECTOR_SEARCH_CONFIG', 'QUALITY_THRESHOLDS'
]
#!/usr/bin/env python3
"""
Integrated Pipeline API Module for Museum Archive
Combines the pipeline processor with the FastAPI system
"""

import os
import subprocess
import tempfile
import shutil
import zipfile
import time
import logging
import uuid
import json
import threading
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

# Import your existing modules
import database
from models.base import DublinCoreRecord
from database.processing_operations import ProcessingDatabase

# Configure logging
logger = logging.getLogger(__name__)

# Pipeline configuration - adjust these paths to match your setup
PIPELINE_CONFIG = {
    'SCRIPT_DIR': Path(__file__).parent,
    'MEDIA_DIR': Path('./media'),
    'SESSION_STORAGE': Path('./sessions'),
    'CLASSIFY_RENAME_SCRIPT': Path('./media_upload/classify_rename.py'),
    'TEXT_EXTRACTOR_SCRIPT': Path('./media_upload/text_extractor.py'),
    'TABLE_GENERATOR_SCRIPT': Path('./media_upload/table_generator.py'),
    'LOGGING_LEVEL': 'INFO',
    'LOGGING_FORMAT': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
}

# Create necessary directories
for dir_path in [PIPELINE_CONFIG['MEDIA_DIR'], PIPELINE_CONFIG['SESSION_STORAGE']]:
    dir_path.mkdir(exist_ok=True)

# Global session storage
active_sessions = {}

class PipelineSession(BaseModel):
    session_id: str
    status: str
    current_step: str
    steps_completed: list
    stats: Dict[str, Any] = {}
    error: Optional[str] = None
    created_at: str
    updated_at: str

class CompletePipelineProcessor:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.session_dir = PIPELINE_CONFIG['SESSION_STORAGE'] / session_id
        self.session_dir.mkdir(exist_ok=True)
        
        # Session subdirectories
        self.upload_dir = self.session_dir / "uploads"
        self.processed_dir = self.session_dir / "processed_images"
        self.upload_dir.mkdir(exist_ok=True)
        
        # Session metadata
        self.metadata_file = self.session_dir / "session_metadata.json"
        self.load_or_create_metadata()
    
    def load_or_create_metadata(self):
        """Load existing metadata or create new"""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {
                'session_id': self.session_id,
                'created_at': datetime.now().isoformat(),
                'status': 'created',
                'steps_completed': [],
                'current_step': 'waiting_upload',
                'files_info': {},
                'table_data': None,
                'stats': {}
            }
            self.save_metadata()
    
    def save_metadata(self):
        """Save metadata to file"""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)
    
    def update_status(self, status: str, step: str = None):
        """Update session status"""
        self.metadata['status'] = status
        if step:
            self.metadata['current_step'] = step
        self.metadata['updated_at'] = datetime.now().isoformat()
        self.save_metadata()
    
    def run_processing_pipeline(self, uploaded_file) -> dict:
        """Run ALL processing steps: scan formatting + classification + text extraction + table generation"""
        try:
            self.update_status('processing', 'upload')

            # 0: Save uploaded file
            zip_path = self.upload_dir / uploaded_file.filename
            with open(zip_path, 'wb') as f:
                content = uploaded_file.file.read()
                f.write(content)
            
            self.metadata['files_info']['original_zip'] = uploaded_file.filename
            logger.info(f"File uploaded: {uploaded_file.filename}")
            
            self.update_status('processing', 'scan_formatting')
            # 1: Scan formatting
            logger.info("Starting scan formatting...")
            formatted_dir = self._run_scan_formatting(zip_path)
            self.metadata['steps_completed'].append('scan_formatting')
            logger.info("Scan formatting completed")
            
            self.update_status('processing', 'classify_rename')
            # 2: Classify and rename
            logger.info("Starting classification and renaming...")
            classified_dir = self._run_classify_rename(formatted_dir)
            self.metadata['steps_completed'].append('classify_rename')
            logger.info("Classification and renaming completed")
            
            self.update_status('processing', 'text_extraction')
            # 3: Text extraction
            logger.info("Starting text extraction...")
            final_dir = self._run_text_extraction(classified_dir)
            self.metadata['steps_completed'].append('text_extraction')
            logging.info("Text extraction completed")
            
            self.update_status('processing', 'generate_table')
            # 4: Generate data table
            self.update_status('processing', 'generate_table')
            logger.info("Starting table generation...")
            table_result = self._generate_data_table(final_dir)
            self.metadata['steps_completed'].append('generate_table')
            self.metadata['table_data'] = table_result
            logger.info("Table generation completed")

            # NEW: Step 4.5 - Save to temp database
            logger.info("Saving to temporary database...")
            self._save_to_temp_database(table_result)
            logger.info("✓ Data saved to temp database")

            # Auto-open HTML table in browser
            import webbrowser
            html_path = table_result.get('html_path')
            if html_path and Path(html_path).exists():
                logger.info(f"Opening HTML table in browser: {html_path}")
                webbrowser.open(f'file://{Path(html_path).absolute()}')

            def _save_to_temp_database(self, table_result: dict):
                """Save processing results to temporary database table"""                
                logger.info("Saving to temporary database...")
                
                db = ProcessingDatabase()
                
                # Create session record
                db.create_session(
                    session_id=self.session_id,
                    uploaded_filename=self.metadata.get('uploaded_filename', ''),
                    session_path=str(self.session_dir)
                )
                
                # Insert each item
                for row in table_result.get('data_rows', []):
                    item_data = {
                        'session_id': self.session_id,
                        'directory': row['directory'],
                        'id_number': row.get('id_number', ''),
                        'front_image_path': row['front_image_path'],
                        'back_image_path': row['back_image_path'],
                        'handwritten_notes': row.get('handwritten_notes', ''),
                        'printed_labels': row.get('printed_labels', ''),
                        'addresses': row.get('addresses', ''),
                        'other_markings': row.get('other_markings', ''),
                        'extraction_notes': row.get('extraction_notes', ''),
                        'flags': row.get('flags', []),
                        'processed_at': row.get('processed_at'),
                        'model_used': row.get('model_used', 'gpt-4o')
                    }
                    db.insert_temp_item(item_data)
                
                # Update session stats
                db.update_session_stats(self.session_id, table_result['stats'])
                db.update_session_status(self.session_id, 'review_ready')
                
                logger.info(f"✓ Saved {len(table_result['data_rows'])} items to temp database")

            # 5: Import to database
            #self.update_status('processing', 'database_import')
            #logger.info("Starting database import...")
            #db_import_result = self._import_to_database(final_dir)
            #self.metadata['steps_completed'].append('database_import')
            #logger.info("Database import completed")
            
            # TESTING MODE - Skip database import
            logger.info("⚠️  TESTING MODE: Database import skipped")
            db_import_result = {
                'success': True,
                'records_created': 0,
                'note': 'Database import disabled for testing'
            }

            
            # Count final results
            image_count = len([f for f in final_dir.rglob("*") if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'}])
            directory_count = len([d for d in final_dir.iterdir() if d.is_dir()])
            json_count = len(list(final_dir.rglob("*.json"))) - 2  # Subtract CSV and HTML files
            
            # Count A and B images
            a_images = len([f for f in final_dir.rglob("*A.*") if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'}])
            b_images = len([f for f in final_dir.rglob("*B.*") if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'}])
            
            self.metadata['stats'] = {
                "directories_created": directory_count,
                "images_processed": image_count,
                "front_images": a_images,
                "back_images": b_images,
                "json_files_created": json_count,
                "database_records_created": db_import_result.get('records_created', 0),
                "processing_complete": True,
                "steps_completed": "all_steps_complete"
            }
            
            self.update_status('review_ready', 'awaiting_review')
            self.save_metadata()
            
            return {
                'success': True,
                'session_id': self.session_id,
                'status': 'review_ready',
                'stats': self.metadata['stats'],
                'table_stats': table_result,
                'database_import': db_import_result,
                'message': f'Complete pipeline finished! {json_count} items processed with {table_result.get("duplicates_found", 0)} duplicates and {table_result.get("quality_issues", 0)} quality issues detected. {db_import_result.get("records_created", 0)} records imported to database.'
            }
            
        except Exception as e:
            logger.error(f"Processing error: {e}", exc_info=True)
            self.update_status('error', 'processing_failed')
            self.metadata['error'] = str(e)
            self.save_metadata()
            return {'success': False, 'error': str(e)}
    
    def _run_scan_formatting(self, zip_path: Path) -> Path:
        """Step 1: Run scan formatting script"""
        try:
            # Import your scan formatting module
            from media_upload.scan_formatting import process_uploaded_zip
            
            output_dir = str(self.processed_dir)
            result = process_uploaded_zip(str(zip_path), output_dir)
            
            if not result["success"]:
                raise Exception(f"Scan formatting failed: {result['error']}")
            
            return self.processed_dir
        except ImportError:
            # Fallback: simple ZIP extraction
            logger.warning("Scan formatting module not found, using simple extraction")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.processed_dir)
            return self.processed_dir
    
    def _run_classify_rename(self, input_dir: Path) -> Path:
        """Step 2: Classification and renaming"""
        script_path = PIPELINE_CONFIG['CLASSIFY_RENAME_SCRIPT']
        if not script_path.exists():
            logger.warning(f"Classification script not found: {script_path}")
            return input_dir
        
        try:
            env = os.environ.copy()
            env['PYTHONPATH'] = str(PIPELINE_CONFIG['SCRIPT_DIR'])
            
            cmd = [sys.executable, str(script_path), str(input_dir)]
            
            result = subprocess.run(cmd, cwd=str(PIPELINE_CONFIG['SCRIPT_DIR']), 
                                  env=env, capture_output=True, text=True, timeout=1800)
            
            if result.returncode != 0:
                logger.warning(f"Classification failed (code {result.returncode}): {result.stderr}")
            
            return input_dir
        except Exception as e:
            logger.warning(f"Classification step failed: {e}")
            return input_dir
    
    def _run_text_extraction(self, input_dir: Path) -> Path:
        """Step 3: Text extraction"""
        script_path = PIPELINE_CONFIG['TEXT_EXTRACTOR_SCRIPT']
        if not script_path.exists():
            logger.warning(f"Text extraction script not found: {script_path}")
            return input_dir
        
        try:
            env = os.environ.copy()
            env['PYTHONPATH'] = str(PIPELINE_CONFIG['SCRIPT_DIR'])
            
            cmd = [sys.executable, str(script_path), str(input_dir)]
            
            result = subprocess.run(cmd, cwd=str(PIPELINE_CONFIG['SCRIPT_DIR']), 
                                  env=env, capture_output=True, text=True, timeout=3600)
            
            if result.returncode != 0:
                logger.warning(f"Text extraction failed (code {result.returncode}): {result.stderr}")
            
            return input_dir
        except Exception as e:
            logger.warning(f"Text extraction step failed: {e}")
            return input_dir
    
    def _generate_data_table(self, input_dir: Path) -> dict:
        """Step 4: Generate data table with duplicate detection and quality flagging"""
        try:
            from media_upload.table_generator import generate_summary_table
            result = generate_summary_table(input_dir, input_dir)
            return result
        except ImportError:
            logger.warning("Table generator module not found")
            return {
                'success': True,
                'total_items': 0,
                'duplicates_found': 0,
                'quality_issues': 0,
                'processing_errors': 0
            }
        except Exception as e:
            logger.error(f"Table generation failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_items': 0,
                'duplicates_found': 0,
                'quality_issues': 0,
                'processing_errors': 1
            }
    
    def _import_to_database(self, input_dir: Path) -> dict:
        """Step 5: Import processed data to PostgreSQL database"""
        try:
            records_created = 0
            errors = []
            
            # Get or create Pipeline collection
            try:
                collections = database.list_collections()
                pipeline_collection = next((c for c in collections if c['name'] == 'Pipeline Results'), None)
                
                if not pipeline_collection:
                    pipeline_collection = database.create_collection(
                        name='Pipeline Results',
                        description='Collection of items processed through the image pipeline',
                        is_public=True
                    )
            except Exception as e:
                logger.error(f"Failed to create/get Pipeline collection: {e}")
                return {'success': False, 'error': str(e), 'records_created': 0}
            
            # Process JSON files from pipeline
            json_files = list(input_dir.rglob("*.json"))
            # Filter out summary files
            item_json_files = [f for f in json_files if not f.name.startswith(('processing_summary', 'metadata_summary'))]
            
            for json_file in item_json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        item_data = json.load(f)
                    
                    # Create Dublin Core record from pipeline data
                    record = DublinCoreRecord(
                        title=item_data.get('title') or item_data.get('id_number', f"Item from {json_file.stem}"),
                        creator=item_data.get('creator') or item_data.get('photographer'),
                        subject=item_data.get('subject') or item_data.get('tags', ''),
                        description=self._create_description_from_pipeline_data(item_data),
                        type=item_data.get('type', 'Digitized Document'),
                        format=item_data.get('format', 'Digital Image'),
                        identifier=item_data.get('id_number') or item_data.get('identifier', json_file.stem),
                        date_created=item_data.get('date_created') or item_data.get('date'),
                        source=f"Pipeline Session {self.session_id}",
                        rights=item_data.get('rights', 'Museum Archive'),
                        collection_name='Pipeline Results'
                    )
                    
                    # Import to database
                    new_record = database.create_record(record)
                    records_created += 1
                    
                    # Add to vector search if available
                    try:
                        from vector_search import vector_search
                        if vector_search and hasattr(vector_search, 'add_document'):
                            searchable_text = f"Title: {record.title or ''}"
                            if record.description:
                                searchable_text += f" Description: {record.description}"
                            if record.creator:
                                searchable_text += f" Creator: {record.creator}"
                            
                            vector_search.add_document(
                                collection_name="pipeline_results",
                                document_id=f"pipeline_{new_record['id']}",
                                text=searchable_text,
                                metadata={
                                    'title': record.title,
                                    'creator': record.creator or '',
                                    'type': record.type or '',
                                    'record_id': str(new_record['id']),
                                    'pipeline_session': self.session_id
                                }
                            )
                    except Exception as ve:
                        logger.warning(f"Vector search addition failed: {ve}")
                
                except Exception as e:
                    error_msg = f"Failed to import {json_file.name}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(error_msg)
            
            return {
                'success': True,
                'records_created': records_created,
                'total_files_processed': len(item_json_files),
                'errors_count': len(errors),
                'errors': errors[:5]  # Show first 5 errors
            }
            
        except Exception as e:
            logger.error(f"Database import failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'records_created': 0
            }
    
    def _create_description_from_pipeline_data(self, item_data: dict) -> str:
        """Create a comprehensive description from pipeline extracted data"""
        description_parts = []
        
        # Add extracted text if available
        if item_data.get('extracted_text'):
            text = item_data['extracted_text']
            if isinstance(text, dict):
                for side, content in text.items():
                    if content and content.strip():
                        description_parts.append(f"{side.upper()}: {content.strip()}")
            elif isinstance(text, str) and text.strip():
                description_parts.append(f"Extracted text: {text.strip()}")
        
        # Add processing information
        if item_data.get('processing_info'):
            proc_info = item_data['processing_info']
            if proc_info.get('classification'):
                description_parts.append(f"Classification: {proc_info['classification']}")
            if proc_info.get('quality_score'):
                description_parts.append(f"Quality score: {proc_info['quality_score']}")
        
        # Add file information
        if item_data.get('files'):
            files = item_data['files']
            file_info = []
            for file_type, file_path in files.items():
                if file_path:
                    file_info.append(f"{file_type}: {Path(file_path).name}")
            if file_info:
                description_parts.append(f"Files: {', '.join(file_info)}")
        
        # Add any notes
        if item_data.get('notes'):
            description_parts.append(f"Notes: {item_data['notes']}")
        
        return " | ".join(description_parts) if description_parts else "Processed through image pipeline"
    
    def get_session_status(self) -> dict:
        """Get current session status"""
        return {
            'session_id': self.session_id,
            'status': self.metadata['status'],
            'current_step': self.metadata['current_step'],
            'steps_completed': self.metadata['steps_completed'],
            'stats': self.metadata.get('stats', {}),
            'created_at': self.metadata['created_at'],
            'updated_at': self.metadata.get('updated_at'),
            'error': self.metadata.get('error')
        }
    
    def create_final_zip(self) -> Path:
        """Create final ZIP file after review is complete"""
        if self.metadata['status'] != 'review_ready':
            raise Exception("Cannot create ZIP - processing not complete or already finalized")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = self.session_dir / f"processed_results_{timestamp}.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(self.processed_dir):
                for file in files:
                    file_path = Path(root) / file
                    # Create archive path relative to processed_dir
                    arcname = file_path.relative_to(self.processed_dir)
                    zipf.write(file_path, arcname)
        
        self.metadata['final_zip'] = str(zip_path)
        self.update_status('completed', 'zip_created')
        
        return zip_path
    
    def cleanup(self):
        """Clean up session files"""
        if self.session_dir.exists():
            shutil.rmtree(self.session_dir)

# Create FastAPI router for pipeline endpoints
pipeline_router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])

@pipeline_router.get("/view/{session_id}", response_class=HTMLResponse)
async def view_results(session_id: str):
    """View the HTML results table"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    processor = active_sessions[session_id]
    html_path = processor.processed_dir / "processing_summary.html"
    
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Results not yet available")
    
    # Read and return the HTML content
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    return HTMLResponse(content=html_content)

@pipeline_router.post("/process")
async def process_pipeline(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """Process uploaded ZIP through complete pipeline"""
    try:
        if not file.filename.lower().endswith('.zip'):
            raise HTTPException(status_code=400, detail='File must be a ZIP archive')
        
        # Create new session
        session_id = str(uuid.uuid4())
        processor = CompletePipelineProcessor(session_id)
        active_sessions[session_id] = processor
        
        # Run pipeline in background
        background_tasks.add_task(run_pipeline_background, processor, file)
        
        return {
            'success': True,
            'session_id': session_id,
            'status': 'processing_started',
            'message': 'Pipeline processing started. Use the session ID to check status.'
        }
        
    except Exception as e:
        logger.error(f"Pipeline processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def run_pipeline_background(processor: CompletePipelineProcessor, file: UploadFile):
    """Run pipeline processing in background"""
    try:
        result = processor.run_processing_pipeline(file)
        logger.info(f"Pipeline completed for session {processor.session_id}: {result}")
    except Exception as e:
        logger.error(f"Background pipeline processing failed: {e}")
        processor.update_status('error', 'processing_failed')
        processor.metadata['error'] = str(e)
        processor.save_metadata()

@pipeline_router.get("/status/{session_id}")
async def get_pipeline_status(session_id: str):
    """Get pipeline processing status"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    processor = active_sessions[session_id]
    return processor.get_session_status()

@pipeline_router.get("/sessions")
async def list_pipeline_sessions():
    """List all active pipeline sessions"""
    sessions = []
    for session_id, processor in active_sessions.items():
        sessions.append(processor.get_session_status())
    
    return {
        'success': True,
        'sessions': sessions,
        'total_sessions': len(sessions)
    }

@pipeline_router.get("/download/{session_id}")
async def download_pipeline_results(session_id: str):
    """Download processed results ZIP file"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    processor = active_sessions[session_id]
    
    try:
        zip_path = processor.create_final_zip()
        return FileResponse(
            path=str(zip_path),
            filename=f'pipeline_results_{session_id[:8]}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip',
            media_type='application/zip'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@pipeline_router.delete("/cleanup/{session_id}")
async def cleanup_pipeline_session(session_id: str):
    """Clean up pipeline session files"""
    if session_id in active_sessions:
        processor = active_sessions[session_id]
        processor.cleanup()
        del active_sessions[session_id]
        return {'success': True, 'message': f'Session {session_id} cleaned up'}
    
    raise HTTPException(status_code=404, detail="Session not found")

@pipeline_router.get("/interface", response_class=HTMLResponse)
async def pipeline_interface():
    """Pipeline processing web interface"""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Museum Archive - Pipeline Processor</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
                margin: 0;
            }
            .container {
                max-width: 900px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            .header h1 {
                font-size: 2.5em;
                margin-bottom: 10px;
                font-weight: 300;
            }
            .upload-section {
                padding: 40px;
            }
            .upload-zone {
                border: 3px dashed #ddd;
                border-radius: 15px;
                padding: 60px 20px;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                background: #fafafa;
                margin-bottom: 30px;
            }
            .upload-zone:hover {
                border-color: #667eea;
                background: #f0f2ff;
            }
            .btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 12px 30px;
                border-radius: 25px;
                font-size: 1em;
                cursor: pointer;
                transition: all 0.3s ease;
                margin: 5px;
            }
            .btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            .progress-section {
                margin-top: 30px;
                padding: 20px;
                background: #f8f9fa;
                border-radius: 10px;
                display: none;
            }
            .progress-section.show {
                display: block;
            }
            .step {
                padding: 10px;
                margin: 5px 0;
                border-radius: 5px;
                background: white;
                border-left: 4px solid #ddd;
            }
            .step.active {
                border-left-color: #007bff;
                background: #e3f2fd;
            }
            .step.completed {
                border-left-color: #28a745;
                background: #d4edda;
            }
            .step.error {
                border-left-color: #dc3545;
                background: #f8d7da;
            }
            .results {
                margin-top: 20px;
                padding: 20px;
                background: #e8f5e8;
                border-radius: 10px;
                display: none;
            }
            .results.show {
                display: block;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏭 Pipeline Processor</h1>
                <p>Complete Image Processing Pipeline</p>
            </div>

            <div class="upload-section">
                <div class="upload-zone" id="uploadZone">
                    <div style="font-size: 4em; margin-bottom: 20px;">📁</div>
                    <div style="font-size: 1.2em; margin-bottom: 10px;">Drop ZIP file here or click to browse</div>
                    <div style="color: #999;">Supports ZIP files containing images • Max 100MB</div>
                </div>

                <input type="file" id="fileInput" style="display: none;" accept=".zip">

                <div style="text-align: center;">
                    <button class="btn" onclick="document.getElementById('fileInput').click()">
                        Choose ZIP File
                    </button>
                    <button class="btn" id="processBtn" onclick="processFile()" disabled>
                        Start Processing
                    </button>
                </div>

                <div class="progress-section" id="progressSection">
                    <h3>Processing Progress</h3>
                    <div id="progressSteps">
                        <div class="step" id="step-upload">1. File Upload</div>
                        <div class="step" id="step-scan_formatting">2. Scan Formatting</div>
                        <div class="step" id="step-classify_rename">3. Classification & Renaming</div>
                        <div class="step" id="step-text_extraction">4. Text Extraction</div>
                        <div class="step" id="step-generate_table">5. Generate Summary Table</div>
                        <div class="step" id="step-database_import">6. Database Import</div>
                    </div>
                </div>

                <div class="results" id="results"></div>
            </div>
        </div>

        <script>
            let selectedFile = null;
            let currentSessionId = null;
            let statusInterval = null;

            // File upload handling
            const uploadZone = document.getElementById('uploadZone');
            const fileInput = document.getElementById('fileInput');

            uploadZone.addEventListener('click', () => fileInput.click());

            uploadZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadZone.style.borderColor = '#667eea';
                uploadZone.style.background = '#f0f2ff';
            });

            uploadZone.addEventListener('dragleave', () => {
                uploadZone.style.borderColor = '#ddd';
                uploadZone.style.background = '#fafafa';
            });

            uploadZone.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadZone.style.borderColor = '#ddd';
                uploadZone.style.background = '#fafafa';
                const files = Array.from(e.dataTransfer.files);
                if (files.length > 0 && files[0].name.toLowerCase().endsWith('.zip')) {
                    selectFile(files[0]);
                } else {
                    alert('Please select a ZIP file');
                }
            });

            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    selectFile(e.target.files[0]);
                }
            });

            function selectFile(file) {
                if (!file.name.toLowerCase().endsWith('.zip')) {
                    alert('Please select a ZIP file');
                    return;
                }
                if (file.size > 100 * 1024 * 1024) {
                    alert('File too large (max 100MB)');
                    return;
                }
                
                selectedFile = file;
                document.getElementById('processBtn').disabled = false;
                uploadZone.innerHTML = `
                    <div style="font-size: 3em; margin-bottom: 15px;">✅</div>
                    <div style="font-size: 1.1em; margin-bottom: 5px;">${file.name}</div>
                    <div style="color: #666;">${formatFileSize(file.size)}</div>
                `;
            }

            function formatFileSize(bytes) {
                if (bytes === 0) return '0 Bytes';
                const k = 1024;
                const sizes = ['Bytes', 'KB', 'MB', 'GB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
            }

            async function processFile() {
                if (!selectedFile) return;

                const processBtn = document.getElementById('processBtn');
                processBtn.disabled = true;
                processBtn.textContent = 'Processing...';

                // Show progress section
                document.getElementById('progressSection').classList.add('show');

                try {
                    // Upload file and start processing
                    const formData = new FormData();
                    formData.append('file', selectedFile);

                    const response = await fetch('/api/pipeline/process', {
                        method: 'POST',
                        body: formData
                    });

                    const result = await response.json();

                    if (result.success) {
                        currentSessionId = result.session_id;
                        updateStep('upload', 'completed');
                        
                        // Start polling for status updates
                        statusInterval = setInterval(checkStatus, 2000);
                    } else {
                        throw new Error(result.detail || 'Processing failed');
                    }

                } catch (error) {
                    console.error('Processing error:', error);
                    updateStep('upload', 'error');
                    showError(`Processing failed: ${error.message}`);
                    processBtn.disabled = false;
                    processBtn.textContent = 'Start Processing';
                }
            }

            async function checkStatus() {
                if (!currentSessionId) return;

                try {
                    const response = await fetch(`/api/pipeline/status/${currentSessionId}`);
                    const status = await response.json();

                    // Update step statuses
                    status.steps_completed.forEach(step => {
                        updateStep(step, 'completed');
                    });

                    // Update current step
                    if (status.current_step && status.status === 'processing') {
                        updateStep(status.current_step, 'active');
                    }

                    // Check if processing is complete
                    if (status.status === 'review_ready') {
                        clearInterval(statusInterval);
                        showResults(status);
                    } else if (status.status === 'error') {
                        clearInterval(statusInterval);
                        showError(`Processing failed: ${status.error || 'Unknown error'}`);
                    }

                } catch (error) {
                    console.error('Status check error:', error);
                }
            }

            function updateStep(stepName, status) {
                const stepElement = document.getElementById(`step-${stepName}`);
                if (stepElement) {
                    stepElement.className = `step ${status}`;
                    
                    if (status === 'completed') {
                        stepElement.innerHTML += ' ✅';
                    } else if (status === 'active') {
                        stepElement.innerHTML += ' ⏳';
                    } else if (status === 'error') {
                        stepElement.innerHTML += ' ❌';
                    }
                }
            }

            function showResults(status) {
                const resultsDiv = document.getElementById('results');
                const stats = status.stats || {};
                
                resultsDiv.innerHTML = `
                    <h3>🎉 Processing Complete!</h3>
                    <div style="margin: 20px 0;">
                        <strong>Processing Statistics:</strong><br>
                        • Images processed: ${stats.images_processed || 0}<br>
                        • Front images: ${stats.front_images || 0}<br>
                        • Back images: ${stats.back_images || 0}<br>
                        • JSON files created: ${stats.json_files_created || 0}<br>
                        • Database records created: ${stats.database_records_created || 0}<br>
                        • Directories created: ${stats.directories_created || 0}
                    </div>
                    <div style="margin: 20px 0;">
                        <button class="btn" onclick="downloadResults()">📥 Download Results</button>
                        <button class="btn" onclick="viewInDatabase()">🔍 View in Database</button>
                        <button class="btn" onclick="startNew()">🔄 Process Another File</button>
                    </div>
                `;
                
                resultsDiv.classList.add('show');
            }

            function showError(message) {
                const resultsDiv = document.getElementById('results');
                resultsDiv.innerHTML = `
                    <div style="color: #721c24; background: #f8d7da; padding: 15px; border-radius: 5px;">
                        <h3>❌ Error</h3>
                        <p>${message}</p>
                        <button class="btn" onclick="startNew()">Try Again</button>
                    </div>
                `;
                resultsDiv.classList.add('show');
            }

            async function downloadResults() {
                if (!currentSessionId) return;
                
                try {
                    const response = await fetch(`/api/pipeline/download/${currentSessionId}`);
                    
                    if (response.ok) {
                        const blob = await response.blob();
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `pipeline_results_${currentSessionId.slice(0, 8)}.zip`;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        window.URL.revokeObjectURL(url);
                    } else {
                        alert('Download failed');
                    }
                } catch (error) {
                    console.error('Download error:', error);
                    alert('Download failed');
                }
            }

            function viewInDatabase() {
                window.open('/api/collections', '_blank');
            }

            function startNew() {
                selectedFile = null;
                currentSessionId = null;
                if (statusInterval) {
                    clearInterval(statusInterval);
                    statusInterval = null;
                }
                
                document.getElementById('processBtn').disabled = true;
                document.getElementById('processBtn').textContent = 'Start Processing';
                document.getElementById('progressSection').classList.remove('show');
                document.getElementById('results').classList.remove('show');
                
                // Reset upload zone
                uploadZone.innerHTML = `
                    <div style="font-size: 4em; margin-bottom: 20px;">📁</div>
                    <div style="font-size: 1.2em; margin-bottom: 10px;">Drop ZIP file here or click to browse</div>
                    <div style="color: #999;">Supports ZIP files containing images • Max 100MB</div>
                `;
                
                // Reset steps
                const steps = document.querySelectorAll('.step');
                steps.forEach(step => {
                    step.className = 'step';
                    step.innerHTML = step.innerHTML.replace(/ [✅⏳❌]/g, '');
                });
                
                fileInput.value = '';
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Background cleanup task
def cleanup_expired_sessions():
    """Background task to clean up expired sessions"""
    while True:
        try:
            expired_sessions = []
            
            for session_id, processor in active_sessions.items():
                # Check if session is older than 24 hours
                created_at = datetime.fromisoformat(processor.metadata['created_at'])
                age_hours = (datetime.now() - created_at).total_seconds() / 3600
                
                if age_hours > 24:  # 24 hour timeout
                    expired_sessions.append(session_id)
            
            # Clean up expired sessions
            for session_id in expired_sessions:
                if session_id in active_sessions:
                    processor = active_sessions[session_id]
                    processor.cleanup()
                    del active_sessions[session_id]
                    logger.info(f"Cleaned up expired session: {session_id}")
        
        except Exception as e:
            logger.error(f"Error in session cleanup: {e}")
        
        # Sleep for 1 hour before next cleanup
        time.sleep(3600)

# Start background cleanup task
cleanup_thread = threading.Thread(target=cleanup_expired_sessions, daemon=True)
cleanup_thread.start()
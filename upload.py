"""
File upload operations for Museum Archive API
Handles CSV uploads and web interface
"""
import logging
from typing import Dict, Any
import pandas as pd
import io
from fastapi import UploadFile, HTTPException
from fastapi.responses import HTMLResponse

import database

# Configure logging
logger = logging.getLogger(__name__)


async def upload_csv(file: UploadFile) -> Dict[str, Any]:
    """Upload CSV file and import data to database with separate notes field"""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV file")
    
    try:
        contents = await file.read()
        df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
        
        logger.info(f"CSV file uploaded with {len(df)} rows")
        
        # Get default collection
        try:
            collections = database.list_collections()
            museum_collection = next((c for c in collections if c['name'] == 'Museum Archive'), None)
            
            if not museum_collection:
                raise HTTPException(status_code=500, detail="Default collection not found")
            
            collection_id = museum_collection['id']
            
        except database.DatabaseError as e:
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        
        # Updated column mapping with separate notes field
        column_mapping = {
            # Title variations
            'title': 'title',
            'Title': 'title', 
            'name': 'title',
            'Name': 'title',
            'item_name': 'title',
            'object_name': 'title',
            
            # Creator variations
            'creator': 'creator',
            'Creator': 'creator',
            'artist': 'creator',
            'Artist': 'creator',
            'author': 'creator',
            'Author': 'creator',
            'maker': 'creator',
            'Maker': 'creator',
            
            # Subject variations
            'subject': 'subject',
            'Subject': 'subject',
            'topic': 'subject',
            'Topic': 'subject',
            'keywords': 'subject',
            'Keywords': 'subject',
            'tags': 'subject',
            'Tags': 'subject',
            
            # Description (separate from notes)
            'description': 'description',
            'Description': 'description',
            'summary': 'description',
            'Summary': 'description',
            
            # Notes (separate field)
            'notes': 'notes',
            'Notes': 'notes',
            'comments': 'notes',
            'Comments': 'notes',
            'remarks': 'notes',
            'Remarks': 'notes',
            'additional_info': 'notes',
            'Additional_Info': 'notes',
            
            # Other fields
            'type': 'type',
            'Type': 'type',
            'category': 'type',
            'Category': 'type',
            'object_type': 'type',
            'Object_Type': 'type',
            
            'format': 'format',
            'Format': 'format',
            'medium': 'format',
            'Medium': 'format',
            
            'identifier': 'identifier',
            'Identifier': 'identifier',
            'id': 'identifier',
            'ID': 'identifier',
            'object_id': 'identifier',
            'Object_ID': 'identifier',
            'catalog_number': 'identifier',
            'Catalog_Number': 'identifier',
            
            'date_created': 'date_created',
            'Date_Created': 'date_created',
            'Date': 'date_created',
            'date': 'date_created',
            'year': 'date_created',
            'Year': 'date_created',
            'created': 'date_created',
            'Created': 'date_created',
            
            'publisher': 'publisher',
            'Publisher': 'publisher',
            
            'source': 'source',
            'Source': 'source',
            'collection': 'source',
            'Collection': 'source',
            
            'rights': 'rights',
            'Rights': 'rights',
            'copyright': 'rights',
            'Copyright': 'rights',
            'license': 'rights',
            'License': 'rights',
            
            'contributor': 'contributor',
            'Contributor': 'contributor',
            'donor': 'contributor',
            'Donor': 'contributor'
        }
        
        inserted_rows = 0
        errors = []
        
        # Process each row
        for index, row in df.iterrows():
            try:
                record_data = {'collection_id': collection_id}
                
                # Map CSV columns to database columns
                for csv_col, db_col in column_mapping.items():
                    if csv_col in df.columns and pd.notna(row[csv_col]):
                        value = str(row[csv_col]).strip()
                        if value:  # Only add non-empty values
                            record_data[db_col] = value
                
                # Ensure we have at least a title
                if 'title' not in record_data:
                    record_data['title'] = f"Item {index + 1} from {file.filename}"
                
                # Build searchable content for full-text search (including notes)
                searchable_parts = []
                for field in ['title', 'creator', 'subject', 'description', 'notes']:
                    if field in record_data and record_data[field]:
                        searchable_parts.append(record_data[field])
                
                if searchable_parts:
                    record_data['searchable_content'] = ' '.join(searchable_parts)
                
                # Insert record only if we have meaningful data
                if len(record_data) > 1:  # More than just collection_id
                    try:
                        # Use database module to insert
                        with database.get_db_cursor() as (cursor, conn):
                            columns = list(record_data.keys())
                            values = list(record_data.values())
                            placeholders = ['%s'] * len(values)
                            
                            query = f"""
                                INSERT INTO dublin_core_records ({', '.join(columns)})
                                VALUES ({', '.join(placeholders)})
                            """
                            
                            cursor.execute(query, values)
                            conn.commit()
                            inserted_rows += 1
                            
                    except database.DatabaseError as db_error:
                        errors.append(f"Row {index + 1}: Database error - {str(db_error)}")
                        logger.warning(f"Row {index + 1} database error: {db_error}")
                
            except Exception as row_error:
                errors.append(f"Row {index + 1}: {str(row_error)}")
                logger.warning(f"Row {index + 1} error: {row_error}")
        
        return {
            "success": True,
            "message": "CSV upload completed",
            "data": {
                "filename": file.filename,
                "total_rows": len(df),
                "inserted_rows": inserted_rows,
                "errors_count": len(errors),
                "errors": errors[:5] if errors else [],  # Show first 5 errors
                "column_mapping_used": {
                    "found_columns": list(df.columns),
                    "mapped_columns": {
                        csv_col: db_col for csv_col, db_col in column_mapping.items() 
                        if csv_col in df.columns
                    }
                }
            }
        }
        
    except Exception as e:
        logger.error(f"CSV upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def get_upload_interface() -> HTMLResponse:
    """CSV Upload Interface"""
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Museum Archive - CSV Upload</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 800px;
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

        .header p {
            opacity: 0.9;
            font-size: 1.1em;
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

        .upload-zone:hover, .upload-zone.dragover {
            border-color: #667eea;
            background: #f0f2ff;
            transform: translateY(-2px);
        }

        .upload-zone.active {
            border-color: #28a745;
            background: #f0fff4;
        }

        .upload-icon {
            font-size: 4em;
            color: #ddd;
            margin-bottom: 20px;
            transition: color 0.3s ease;
        }

        .upload-zone:hover .upload-icon {
            color: #667eea;
        }

        .upload-text {
            font-size: 1.2em;
            color: #666;
            margin-bottom: 10px;
        }

        .upload-subtext {
            color: #999;
            font-size: 0.9em;
        }

        .file-input {
            display: none;
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

        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }

        .file-list {
            margin-top: 30px;
        }

        .file-item {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-left: 4px solid #667eea;
        }

        .file-info {
            flex: 1;
        }

        .file-name {
            font-weight: 500;
            color: #333;
        }

        .file-size {
            color: #666;
            font-size: 0.9em;
        }

        .file-status {
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 0.8em;
            font-weight: 500;
        }

        .status-pending {
            background: #fff3cd;
            color: #856404;
        }

        .status-uploading {
            background: #cce7ff;
            color: #004085;
        }

        .status-success {
            background: #d4edda;
            color: #155724;
        }

        .status-error {
            background: #f8d7da;
            color: #721c24;
        }

        .column-mapping {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 20px;
            margin-top: 20px;
        }

        .column-mapping h3 {
            color: #333;
            margin-bottom: 15px;
        }

        .mapping-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            font-size: 0.9em;
        }

        .mapping-item {
            padding: 8px;
            background: white;
            border-radius: 5px;
            border-left: 3px solid #667eea;
        }

        .results {
            margin-top: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            display: none;
        }

        .results.show {
            display: block;
        }

        .alert {
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 15px;
        }

        .alert-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }

        .alert-error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }

        .alert-info {
            background: #cce7ff;
            color: #004085;
            border: 1px solid #b3d7ff;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-right: 10px;
        }

        .nav-buttons {
            text-align: center;
            margin-bottom: 20px;
        }

        .nav-btn {
            background: #6c757d;
            color: white;
            text-decoration: none;
            padding: 8px 20px;
            border-radius: 20px;
            margin: 0 5px;
            font-size: 0.9em;
            transition: all 0.3s ease;
        }

        .nav-btn:hover {
            background: #5a6268;
            transform: translateY(-1px);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏛️ Museum Archive</h1>
            <p>CSV Data Upload Interface</p>
        </div>

        <div class="upload-section">
            <div class="nav-buttons">
                <a href="/dashboard" class="nav-btn">📊 Dashboard</a>
                <a href="/api/collections" class="nav-btn">📁 Collections</a>
                <a href="/docs" class="nav-btn">📖 API Docs</a>
            </div>

            <div class="upload-zone" id="uploadZone">
                <div class="upload-icon">📁</div>
                <div class="upload-text">Drop CSV files here or click to browse</div>
                <div class="upload-subtext">Supports multiple files • Max 10MB per file</div>
            </div>

            <input type="file" id="fileInput" class="file-input" multiple accept=".csv" />

            <div style="text-align: center;">
                <button class="btn" onclick="document.getElementById('fileInput').click()">
                    Choose Files
                </button>
                <button class="btn" id="uploadBtn" onclick="uploadFiles()" disabled>
                    Upload All Files
                </button>
                <button class="btn" onclick="clearFiles()">
                    Clear All
                </button>
            </div>

            <div class="column-mapping">
                <h3>📋 Column Mapping Guide</h3>
                <div class="mapping-grid">
                    <div class="mapping-item"><strong>title, Title, name</strong> → Title</div>
                    <div class="mapping-item"><strong>creator, artist, author</strong> → Creator</div>
                    <div class="mapping-item"><strong>subject, topic, keywords</strong> → Subject</div>
                    <div class="mapping-item"><strong>description, Description, summary</strong> → Description</div>
                    <div class="mapping-item"><strong>notes, Notes, comments, remarks</strong> → Notes</div>
                    <div class="mapping-item"><strong>type, category</strong> → Type</div>
                    <div class="mapping-item"><strong>date, year, date_created</strong> → Date</div>
                    <div class="mapping-item"><strong>identifier, id</strong> → Identifier</div>
                    <div class="mapping-item"><strong>format</strong> → Format</div>
                </div>
            </div>

            <div class="file-list" id="fileList"></div>

            <div class="results" id="results"></div>
        </div>
    </div>

    <script>
        let selectedFiles = [];
        const API_BASE = window.location.origin;

        // Upload zone events
        const uploadZone = document.getElementById('uploadZone');
        const fileInput = document.getElementById('fileInput');

        uploadZone.addEventListener('click', () => fileInput.click());

        uploadZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadZone.classList.add('dragover');
        });

        uploadZone.addEventListener('dragleave', () => {
            uploadZone.classList.remove('dragover');
        });

        uploadZone.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadZone.classList.remove('dragover');
            const files = Array.from(e.dataTransfer.files).filter(file => 
                file.name.toLowerCase().endsWith('.csv')
            );
            addFiles(files);
        });

        fileInput.addEventListener('change', (e) => {
            addFiles(Array.from(e.target.files));
        });

        function addFiles(files) {
            const validFiles = files.filter(file => {
                if (!file.name.toLowerCase().endsWith('.csv')) {
                    showAlert('Only CSV files are allowed!', 'error');
                    return false;
                }
                if (file.size > 10 * 1024 * 1024) {
                    showAlert(`File ${file.name} is too large (max 10MB)`, 'error');
                    return false;
                }
                return true;
            });

            selectedFiles = [...selectedFiles, ...validFiles];
            updateFileList();
            document.getElementById('uploadBtn').disabled = selectedFiles.length === 0;
        }

        function updateFileList() {
            const fileList = document.getElementById('fileList');
            
            if (selectedFiles.length === 0) {
                fileList.innerHTML = '';
                return;
            }

            fileList.innerHTML = selectedFiles.map((file, index) => `
                <div class="file-item" id="file-${index}">
                    <div class="file-info">
                        <div class="file-name">${file.name}</div>
                        <div class="file-size">${formatFileSize(file.size)}</div>
                    </div>
                    <div class="file-status status-pending" id="status-${index}">
                        Pending
                    </div>
                </div>
            `).join('');
        }

        function formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }

        function clearFiles() {
            selectedFiles = [];
            updateFileList();
            document.getElementById('uploadBtn').disabled = true;
            document.getElementById('results').classList.remove('show');
            fileInput.value = '';
        }

        async function uploadFiles() {
            if (selectedFiles.length === 0) return;

            const uploadBtn = document.getElementById('uploadBtn');
            uploadBtn.disabled = true;
            uploadBtn.innerHTML = '<span class="spinner"></span>Uploading...';

            const results = {
                successful: 0,
                failed: 0,
                totalRecords: 0,
                errors: []
            };

            for (let i = 0; i < selectedFiles.length; i++) {
                const file = selectedFiles[i];
                const statusElement = document.getElementById(`status-${i}`);
                
                try {
                    // Update status to uploading
                    statusElement.textContent = 'Uploading...';
                    statusElement.className = 'file-status status-uploading';

                    // Upload file
                    const formData = new FormData();
                    formData.append('file', file);

                    const response = await fetch(`${API_BASE}/api/upload/csv`, {
                        method: 'POST',
                        body: formData
                    });

                    const result = await response.json();

                    if (response.ok && result.success) {
                        statusElement.textContent = `✅ Success (${result.data.inserted_rows} records)`;
                        statusElement.className = 'file-status status-success';
                        results.successful++;
                        results.totalRecords += result.data.inserted_rows || 0;
                    } else {
                        throw new Error(result.detail || 'Upload failed');
                    }

                } catch (error) {
                    statusElement.textContent = `❌ Failed: ${error.message}`;
                    statusElement.className = 'file-status status-error';
                    results.failed++;
                    results.errors.push(`${file.name}: ${error.message}`);
                }

                // Small delay between uploads
                await new Promise(resolve => setTimeout(resolve, 500));
            }

            // Show results
            showResults(results);

            // Reset upload button
            uploadBtn.disabled = false;
            uploadBtn.innerHTML = 'Upload All Files';
        }

        function showResults(results) {
            const resultsDiv = document.getElementById('results');
            
            let html = '<h3>📊 Upload Results</h3>';
            
            if (results.successful > 0) {
                html += `
                    <div class="alert alert-success">
                        ✅ Successfully uploaded ${results.successful} file(s)<br>
                        📝 Total records imported: ${results.totalRecords}
                    </div>
                `;
            }

            if (results.failed > 0) {
                html += `
                    <div class="alert alert-error">
                        ❌ Failed to upload ${results.failed} file(s)<br>
                        ${results.errors.slice(0, 3).map(error => `• ${error}`).join('<br>')}
                        ${results.errors.length > 3 ? `<br>... and ${results.errors.length - 3} more errors` : ''}
                    </div>
                `;
            }

            html += `
                <div class="alert alert-info">
                    🔍 <strong>Next steps:</strong><br>
                    • <a href="${API_BASE}/api/collections" target="_blank">View your collections</a><br>
                    • <a href="${API_BASE}/api/search/database?q=test" target="_blank">Test search functionality</a><br>
                    • <a href="${API_BASE}/dashboard" target="_blank">Go to dashboard</a>
                </div>
            `;

            resultsDiv.innerHTML = html;
            resultsDiv.classList.add('show');
        }

        function showAlert(message, type) {
            const resultsDiv = document.getElementById('results');
            resultsDiv.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
            resultsDiv.classList.add('show');
            setTimeout(() => resultsDiv.classList.remove('show'), 5000);
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            console.log('Museum Archive CSV Upload Interface loaded');
        });
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)
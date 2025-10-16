-- Table for tracking sessions
CREATE TABLE IF NOT EXISTS processing_sessions_new (
    session_id VARCHAR(255) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(50) DEFAULT 'created',
    
    -- File info
    uploaded_filename VARCHAR(255),
    session_path VARCHAR(500),
    
    -- Stats
    total_items INTEGER DEFAULT 0,
    duplicates_found INTEGER DEFAULT 0,
    quality_issues INTEGER DEFAULT 0,
    
    -- Timestamps
    completed_at TIMESTAMP,
    imported_at TIMESTAMP
);

-- Temp table for items being processed (before import)
CREATE TABLE IF NOT EXISTS processing_items_temp (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) REFERENCES processing_sessions_new(session_id) ON DELETE CASCADE,
    
    -- Item identification
    directory VARCHAR(50),
    id_number VARCHAR(100),
    
    -- File paths (relative to session)
    front_image_path VARCHAR(500),
    back_image_path VARCHAR(500),
    
    -- Extracted metadata (EDITABLE)
    handwritten_notes TEXT,
    printed_labels TEXT,
    addresses TEXT,
    other_markings TEXT,
    extraction_notes TEXT,
    
    -- Flags
    flags TEXT[], -- ['duplicate_id', 'quality_issue']
    
    -- Processing info
    processed_at TIMESTAMP,
    model_used VARCHAR(50),
    
    -- Not imported yet
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Add session_id column to main dublin_core_records table (to track where it came from)
ALTER TABLE dublin_core_records ADD COLUMN IF NOT EXISTS session_id VARCHAR(255) REFERENCES processing_sessions_new(session_id);
ALTER TABLE dublin_core_records ADD COLUMN IF NOT EXISTS imported_at TIMESTAMP;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_new_status ON processing_sessions_new(status);
CREATE INDEX IF NOT EXISTS idx_temp_items_session ON processing_items_temp(session_id);
CREATE INDEX IF NOT EXISTS idx_dublin_core_session ON dublin_core_records(session_id);
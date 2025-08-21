-- PostgreSQL Database Schema for Museum Archive System
-- Run this on Railway PostgreSQL to create the database structure

-- Create collections table
CREATE TABLE IF NOT EXISTS collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    is_public BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create Dublin Core records table
CREATE TABLE IF NOT EXISTS dublin_core_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id UUID REFERENCES collections(id) ON DELETE CASCADE,
    title TEXT,
    creator TEXT,
    subject TEXT,
    description TEXT,
    publisher TEXT,
    contributor TEXT,
    date_created DATE,
    type VARCHAR(100),
    format VARCHAR(100),
    identifier VARCHAR(255),
    source TEXT,
    language VARCHAR(10) DEFAULT 'en',
    relation TEXT,
    coverage TEXT,
    rights TEXT,
    searchable_content TEXT, -- For full-text search
    metadata JSONB, -- Additional metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create media files table (optional for storing file references)
CREATE TABLE IF NOT EXISTS media_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_id UUID REFERENCES dublin_core_records(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    file_type VARCHAR(50),
    file_size BIGINT,
    mime_type VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create processing sessions table for pipeline tracking
CREATE TABLE IF NOT EXISTS processing_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(50) DEFAULT 'created',
    current_step VARCHAR(100),
    steps_completed TEXT[],
    stats JSONB,
    error_log TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_dublin_core_title ON dublin_core_records(title);
CREATE INDEX IF NOT EXISTS idx_dublin_core_creator ON dublin_core_records(creator);
CREATE INDEX IF NOT EXISTS idx_dublin_core_subject ON dublin_core_records(subject);
CREATE INDEX IF NOT EXISTS idx_dublin_core_identifier ON dublin_core_records(identifier);
CREATE INDEX IF NOT EXISTS idx_dublin_core_collection ON dublin_core_records(collection_id);
CREATE INDEX IF NOT EXISTS idx_dublin_core_type ON dublin_core_records(type);
CREATE INDEX IF NOT EXISTS idx_dublin_core_date ON dublin_core_records(date_created);

-- Full-text search index
CREATE INDEX IF NOT EXISTS idx_dublin_core_search ON dublin_core_records 
USING GIN(to_tsvector('english', COALESCE(title, '') || ' ' || 
                                 COALESCE(description, '') || ' ' || 
                                 COALESCE(searchable_content, '')));

-- Create trigger for updating timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_collections_updated_at 
    BEFORE UPDATE ON collections 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_dublin_core_updated_at 
    BEFORE UPDATE ON dublin_core_records 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_sessions_updated_at 
    BEFORE UPDATE ON processing_sessions 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default collections
INSERT INTO collections (name, description) VALUES 
    ('Museum Archive', 'Main museum archive collection containing artifacts, photographs, and historical documents'),
    ('Library', 'Library collection containing books and publications'),
    ('Test Collection', 'Collection for testing and development purposes')
ON CONFLICT (name) DO NOTHING;

-- Create a view for easy querying with collection names
CREATE OR REPLACE VIEW dublin_core_with_collection AS
SELECT 
    dcr.*,
    c.name as collection_name,
    c.description as collection_description
FROM dublin_core_records dcr
JOIN collections c ON dcr.collection_id = c.id;

-- Grant necessary permissions (adjust as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_railway_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_railway_user;
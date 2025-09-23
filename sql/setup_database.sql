-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Function to create standardized domain memory tables
CREATE OR REPLACE FUNCTION create_domain_memories_table(domain_name TEXT)
RETURNS VOID AS $$
DECLARE
    table_name TEXT;
BEGIN
    table_name := domain_name || '_memories';
    
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I (
            id VARCHAR(50) PRIMARY KEY,
            content TEXT NOT NULL,
            embedding vector(768),
            metadata JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )', table_name);
    
    -- Create indexes for performance
    EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I USING gin (metadata)', 
                   table_name || '_metadata_idx', table_name);
    
    EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (updated_at DESC)', 
                   table_name || '_updated_idx', table_name);
                   
    EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I USING gin (to_tsvector(''english'', content))', 
                   table_name || '_content_idx', table_name);
END;
$$ LANGUAGE plpgsql;

-- Create default domain table
SELECT create_domain_memories_table('default');

-- Session Management Tables
-- Sessions table for tracking conversation sessions
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    project_name TEXT,
    working_directory TEXT,
    initial_topics TEXT[], -- Array of initial session topics
    final_topics TEXT[], -- Array of final session topics
    conversation_summary TEXT,
    outcome JSONB, -- Session outcome metadata
    thread_id TEXT, -- Links to conversation_threads
    parent_session_id TEXT REFERENCES sessions(id),
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'completed', 'error')),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Conversation threads table for tracking related sessions
CREATE TABLE IF NOT EXISTS conversation_threads (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    project_name TEXT,
    topics TEXT[], -- Accumulated topics across sessions
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Association table between sessions and memories
CREATE TABLE IF NOT EXISTS session_memories (
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    memory_id TEXT NOT NULL,
    domain TEXT NOT NULL, -- Which domain the memory belongs to
    created_during_session BOOLEAN DEFAULT true, -- Was this memory created during the session
    interaction_type TEXT DEFAULT 'loaded', -- loaded, created, referenced
    relevance_score REAL, -- How relevant this memory was to the session
    PRIMARY KEY (session_id, memory_id, domain)
);

-- Indexes for session management performance
CREATE INDEX IF NOT EXISTS sessions_project_name_idx ON sessions (project_name);
CREATE INDEX IF NOT EXISTS sessions_started_at_idx ON sessions (started_at DESC);
CREATE INDEX IF NOT EXISTS sessions_thread_id_idx ON sessions (thread_id);
CREATE INDEX IF NOT EXISTS sessions_status_idx ON sessions (status);

CREATE INDEX IF NOT EXISTS conversation_threads_project_name_idx ON conversation_threads (project_name);
CREATE INDEX IF NOT EXISTS conversation_threads_last_updated_idx ON conversation_threads (last_updated DESC);

CREATE INDEX IF NOT EXISTS session_memories_session_id_idx ON session_memories (session_id);
CREATE INDEX IF NOT EXISTS session_memories_created_during_idx ON session_memories (created_during_session);

-- Function to update conversation thread timestamp
CREATE OR REPLACE FUNCTION update_conversation_thread_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE conversation_threads
    SET last_updated = NOW()
    WHERE id = NEW.thread_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update thread timestamp when session is created/updated
CREATE TRIGGER update_thread_timestamp
    AFTER INSERT OR UPDATE ON sessions
    FOR EACH ROW
    WHEN (NEW.thread_id IS NOT NULL)
    EXECUTE FUNCTION update_conversation_thread_timestamp();

-- Example: Create additional domain tables
-- SELECT create_domain_memories_table('startup');
-- SELECT create_domain_memories_table('health');
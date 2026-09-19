-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Anime table
CREATE TABLE IF NOT EXISTS anime (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Episodes table
CREATE TABLE IF NOT EXISTS episodes (
    id SERIAL PRIMARY KEY,
    anime_id INT REFERENCES anime(id) ON DELETE CASCADE,
    season_number INT NOT NULL,
    episode_number INT NOT NULL,
    title VARCHAR(255),
    duration_seconds FLOAT,
    source_identifier TEXT,
    source_path TEXT,
    source_checksum VARCHAR(64),
    source_size BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uniq_anime_episode UNIQUE (anime_id, season_number, episode_number)
);

-- Scenes table
CREATE TABLE IF NOT EXISTS scenes (
    id SERIAL PRIMARY KEY,
    episode_id INT REFERENCES episodes(id) ON DELETE CASCADE,
    scene_index INT NOT NULL,
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    representative_time FLOAT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS scenes_episode_scene_index_idx
ON scenes (episode_id, scene_index);

-- Scene frames table with pgvector embedding
CREATE TABLE IF NOT EXISTS scene_frames (
    id SERIAL PRIMARY KEY,
    scene_id INT REFERENCES scenes(id) ON DELETE CASCADE,
    timestamp FLOAT NOT NULL,
    object_key TEXT NOT NULL,
    embedding vector NOT NULL,
    embedding_model VARCHAR(100) NOT NULL,
    embedding_model_version VARCHAR(50) NOT NULL,
    embedding_dimension INT NOT NULL CHECK (embedding_dimension > 0),
    ocr_text TEXT NOT NULL DEFAULT '',
    ocr_engine VARCHAR(100),
    ocr_engine_version VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS scene_frames_identity_idx
ON scene_frames (scene_id, timestamp, embedding_model, embedding_model_version);

-- Indexing jobs table
CREATE TABLE IF NOT EXISTS indexing_jobs (
    id SERIAL PRIMARY KEY,
    episode_id INT REFERENCES episodes(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    progress FLOAT DEFAULT 0.0,
    total_scenes INT DEFAULT 0,
    processed_scenes INT DEFAULT 0,
    processed_frames INT DEFAULT 0,
    embedding_model VARCHAR(100),
    embedding_model_version VARCHAR(50),
    ocr_engine VARCHAR(100),
    ocr_engine_version VARCHAR(100),
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

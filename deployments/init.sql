-- 初始化PostgreSQL数据库和RAG相关扩展
-- 启用pgvector扩展用于向量存储
CREATE EXTENSION IF NOT EXISTS vector;

-- 启用全文搜索扩展
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 创建RAG相关表结构
-- 文档表
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    file_type VARCHAR(50),
    file_size INTEGER,
    file_hash VARCHAR(64) UNIQUE,
    source_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    indexed_at TIMESTAMP WITH TIME ZONE,
    
    -- 全文搜索索引
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, ''))
    ) STORED
);

-- 文档块表（用于分块存储）
CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    
    -- 向量嵌入，使用1536维度（OpenAI embedding）
    embedding vector(1536),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- 确保每个文档的块索引唯一
    UNIQUE(document_id, chunk_index)
);

-- 查询历史表
CREATE TABLE IF NOT EXISTS query_history (
    id SERIAL PRIMARY KEY,
    query_text TEXT NOT NULL,
    query_embedding vector(1536),
    user_id VARCHAR(255),
    session_id VARCHAR(255),
    
    -- 查询结果
    results JSONB,
    matched_chunks INTEGER[],
    similarity_scores FLOAT[],
    
    -- 性能指标
    execution_time_ms INTEGER,
    total_chunks_searched INTEGER,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引优化查询性能
-- 文档索引
CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);
CREATE INDEX IF NOT EXISTS idx_documents_search_vector ON documents USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_documents_metadata ON documents USING GIN(metadata);

-- 文档块索引
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 查询历史索引
CREATE INDEX IF NOT EXISTS idx_query_history_user_id ON query_history(user_id);
CREATE INDEX IF NOT EXISTS idx_query_history_session_id ON query_history(session_id);
CREATE INDEX IF NOT EXISTS idx_query_history_created_at ON query_history(created_at);
CREATE INDEX IF NOT EXISTS idx_query_history_embedding ON query_history USING ivfflat (query_embedding vector_cosine_ops) WITH (lists = 100);

-- 创建更新时间戳的触发器函数
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 为documents表创建更新时间戳触发器
CREATE TRIGGER update_documents_updated_at 
    BEFORE UPDATE ON documents 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- 创建一些有用的视图
-- 文档统计视图
CREATE OR REPLACE VIEW document_stats AS
SELECT 
    COUNT(*) as total_documents,
    COUNT(CASE WHEN indexed_at IS NOT NULL THEN 1 END) as indexed_documents,
    SUM(file_size) as total_size,
    AVG(file_size) as avg_size,
    COUNT(DISTINCT file_type) as unique_file_types
FROM documents;

-- 块统计视图
CREATE OR REPLACE VIEW chunk_stats AS
SELECT 
    d.id as document_id,
    d.title,
    COUNT(dc.id) as chunk_count,
    COUNT(CASE WHEN dc.embedding IS NOT NULL THEN 1 END) as embedded_chunks
FROM documents d
LEFT JOIN document_chunks dc ON d.id = dc.document_id
GROUP BY d.id, d.title;

-- 查询性能统计视图
CREATE OR REPLACE VIEW query_performance_stats AS
SELECT 
    DATE_TRUNC('hour', created_at) as hour,
    COUNT(*) as query_count,
    AVG(execution_time_ms) as avg_execution_time,
    MAX(execution_time_ms) as max_execution_time,
    AVG(total_chunks_searched) as avg_chunks_searched
FROM query_history
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY DATE_TRUNC('hour', created_at)
ORDER BY hour DESC;

-- 创建一些有用的函数
-- 向量相似度搜索函数
CREATE OR REPLACE FUNCTION search_similar_chunks(
    query_embedding vector(1536),
    similarity_threshold float DEFAULT 0.7,
    limit_count integer DEFAULT 10
)
RETURNS TABLE(
    chunk_id integer,
    document_id integer,
    document_title varchar,
    content text,
    similarity_score float
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        dc.id,
        dc.document_id,
        d.title,
        dc.content,
        1 - (dc.embedding <=> query_embedding) as similarity
    FROM document_chunks dc
    JOIN documents d ON dc.document_id = d.id
    WHERE dc.embedding IS NOT NULL
        AND 1 - (dc.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY dc.embedding <=> query_embedding
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- 全文搜索函数
CREATE OR REPLACE FUNCTION search_documents_fulltext(
    search_query text,
    limit_count integer DEFAULT 10
)
RETURNS TABLE(
    document_id integer,
    title varchar,
    content text,
    rank float
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        d.id,
        d.title,
        d.content,
        ts_rank(d.search_vector, plainto_tsquery('english', search_query)) as rank
    FROM documents d
    WHERE d.search_vector @@ plainto_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- 插入一些示例数据（可选）
INSERT INTO documents (title, content, file_type, file_size, file_hash, metadata) VALUES
('示例文档1', '这是一个关于机器学习的示例文档，包含了深度学习和神经网络的基础知识。', 'txt', 1024, 'hash1', '{"category": "AI", "tags": ["machine-learning", "deep-learning"]}'),
('示例文档2', '这是一个关于Web开发的示例文档，涵盖了前端和后端技术栈。', 'txt', 2048, 'hash2', '{"category": "Web", "tags": ["frontend", "backend"]}')
ON CONFLICT (file_hash) DO NOTHING;

-- 输出完成信息
DO $$
BEGIN
    RAISE NOTICE '数据库初始化完成！';
    RAISE NOTICE '- 已创建pgvector扩展支持向量存储';
    RAISE NOTICE '- 已创建documents、document_chunks、query_history表';
    RAISE NOTICE '- 已创建相关索引和视图';
    RAISE NOTICE '- 已创建搜索和统计函数';
END $$;
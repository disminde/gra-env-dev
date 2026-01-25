-- Set timezone
SET timezone = 'Asia/Shanghai';

-- Create extension if needed (e.g., for UUID generation)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create a sample table for validation
CREATE TABLE IF NOT EXISTS system_health_check (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    check_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL
);

-- Insert initial data
INSERT INTO system_health_check (status) VALUES ('INITIALIZED');

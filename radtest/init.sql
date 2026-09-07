-- Simple PostgreSQL Database Schema for FreeRADIUS (Isolated in radtest/)

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Simple Users Table
CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(64) UNIQUE NOT NULL,
    password    VARCHAR(255) NOT NULL
);

-- Seed Demo Users:
-- 'john' with plain text password
-- 'alice' with bcrypt hashed password
INSERT INTO users (username, password) VALUES 
('john', 'password123'),
('alice', crypt('alicepassword123', gen_salt('bf')))
ON CONFLICT (username) DO NOTHING;

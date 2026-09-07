CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'student',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT users_role_check CHECK (role IN ('admin', 'student'))
);

INSERT INTO users (username, password, role) VALUES
    ('student66', 'password123', 'student'),
    ('teacher01', 'teachpass123', 'admin'),
    ('admin', 'adminpass', 'admin'),
    ('john', 'password123', 'student'),
    ('alice', crypt('alicepassword123', gen_salt('bf')), 'student')
ON CONFLICT (username) DO UPDATE SET
    password = EXCLUDED.password,
    role = EXCLUDED.role;

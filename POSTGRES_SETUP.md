# Simple PostgreSQL + FreeRADIUS SSO Guide

## 1. Simple SQL Schema (Single `users` Table)

Instead of complex multi-table RADIUS schemas, the system uses a single simple `users` table:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(64) UNIQUE NOT NULL,
    password    VARCHAR(255) NOT NULL
);
```

---

## 2. Managing Users

### A. Insert Plaintext Password User
```sql
INSERT INTO users (username, password) VALUES ('john', 'password123');
```

### B. Insert Bcrypt Hashed Password User
```sql
INSERT INTO users (username, password) VALUES ('alice', crypt('alicepassword123', gen_salt('bf')));
```

FreeRADIUS automatically detects whether the password is plain text or hashed (bcrypt) and authenticates accordingly!

---

## 3. Testing Authentication (`radtest`)

```bash
# Test Plaintext user (john)
docker exec -it sso-radius radtest john password123 127.0.0.1 0 sso_secret_123

# Test Hashed (Bcrypt) user (alice)
docker exec -it sso-radius radtest alice alicepassword123 127.0.0.1 0 sso_secret_123
```

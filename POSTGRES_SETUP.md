# PostgreSQL + FreeRADIUS SSO Documentation

## 1. Overview
The LDAP authentication system has been completely replaced with a lightweight, containerized PostgreSQL database (`sso-postgres`) and pgAdmin web interface (`sso-pgadmin`).

---

## 2. Service Access & Credentials

| Service | Host Port | Internal Docker Host | Credentials |
| :--- | :--- | :--- | :--- |
| **PostgreSQL DB** | `5433` | `postgres:5432` | DB: `radius`<br>User: `radius`<br>Password: `radius_password` |
| **pgAdmin Web UI** | `5051` | `http://localhost:5051` | Email: `admin@example.com`<br>Password: `admin_password` |
| **FreeRADIUS** | `1812/udp` | `radius:1812` | Secret: `sso_secret_123` |

---

## 3. Database Schema & Password Hashing

User credentials are stored in the `radcheck` table:

```sql
SELECT * FROM radcheck;
```

### Adding a Plaintext User
```sql
INSERT INTO radcheck (username, attribute, op, value) 
VALUES ('john', 'Cleartext-Password', ':=', 'password123');
```

### Adding a Hashed Password User (Bcrypt)
```sql
INSERT INTO radcheck (username, attribute, op, value) 
VALUES ('alice', 'Crypt-Password', ':=', crypt('alicepassword123', gen_salt('bf')));
```

---

## 4. Testing Authentication (`radtest`)

Run `radtest` against the running FreeRADIUS container:

```bash
# Test Plaintext user (john)
docker exec -it sso-radius radtest john password123 127.0.0.1 0 sso_secret_123

# Test Hashed (Bcrypt) user (alice)
docker exec -it sso-radius radtest alice alicepassword123 127.0.0.1 0 sso_secret_123
```

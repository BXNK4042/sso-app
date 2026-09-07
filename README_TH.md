# คู่มือการใช้งานระบบ SSO (FreeRADIUS + PostgreSQL)

ระบบยืนยันตัวตนกลาง (SSO) ด้วย FreeRADIUS และเก็บข้อมูลผู้ใช้ใน PostgreSQL

---

## 🚀 1. วิธีเริ่มใช้งาน (Quick Start)

รันคำสั่งเพื่อเริ่มระบบทั้งหมด:
```bash
docker-compose up -d
```

---

## 👤 2. วิธีเพิ่มผู้ใช้งาน (Add Users)

### เพิ่มผ่าน SQL (รันใน Terminal)

* **เพิ่มผู้ใช้รหัสผ่านธรรมดา (Plaintext):**
  ```bash
  docker exec -it sso-postgres psql -U radius -d radius -c "INSERT INTO users (username, password) VALUES ('john', 'password123');"
  ```

* **เพิ่มผู้ใช้รหัสผ่านเข้ารหัส (Bcrypt):**
  ```bash
  docker exec -it sso-postgres psql -U radius -d radius -c "INSERT INTO users (username, password) VALUES ('alice', crypt('alicepassword123', gen_salt('bf')));"
  ```

*(ระบบจะตรวจสอบรูปแบบรหัสผ่านให้อัตโนมัติ)*

---

## 🔑 3. วิธีทดสอบเข้าสู่ระบบ (Test Auth)

ทดสอบส่งรหัสผ่านเพื่อยืนยันตัวตนด้วยคำสั่ง `radtest`:

```bash
docker exec -it sso-radius radtest <username> <password> 127.0.0.1 0 sso_secret_123
```

**ตัวอย่าง:**
```bash
docker exec -it sso-radius radtest john password123 127.0.0.1 0 sso_secret_123
```

* **ผลลัพธ์:**
  * `Received Access-Accept` = 🟢 เข้าสู่ระบบสำเร็จ
  * `Received Access-Reject` = 🔴 รหัสผ่านไม่ถูกต้อง หรือไม่พบผู้ใช้

---

## 🔌 4. ค่าคอนฟิกสำหรับเชื่อมต่อกับแอปพลิเคชันอื่น (Integration)

เมื่อทีมอื่นต้องการต่อเข้ากับระบบ SSO นี้ ให้ใช้ค่าดังนี้:

| รายการ | ค่าที่ต้องใช้ |
| :--- | :--- |
| **RADIUS Server Host** | `sso-radius` (หากอยู่ใน Docker เดียวกัน) หรือ IP เครื่อง Server |
| **Port** | `1812` (UDP) |
| **Shared Secret** | `sso_secret_123` |

### สถานะที่ระบบตอบกลับ (Response Status)
* **`Access-Accept`**: ให้ผ่านเข้าใช้งาน
* **`Access-Reject`**: ปฏิเสธการเข้าใช้งาน

---

## 🖥️ 5. จัดการผ่าน Web UI (pgAdmin)

* **URL:** [http://localhost:5050](http://localhost:5050)
* **Email:** `admin@example.com`
* **Password:** `admin_password`
* **ตารางเก็บผู้ใช้:** `Servers` ➡️ `SSO Database (radius)` ➡️ `Databases` ➡️ `radius` ➡️ `Schemas` ➡️ `public` ➡️ `users`

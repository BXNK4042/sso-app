# LDAP Integration Setup Guide

## Overview
This SSO system now uses OpenLDAP for centralized user authentication. FreeRADIUS will authenticate users against the LDAP directory.

## Architecture
- **OpenLDAP** (Port 389): Centralized user directory
- **FreeRADIUS** (Port 1812/1813): RADIUS authentication server with LDAP backend
- **Auth Service** (Port 8000): FastAPI service that interfaces with RADIUS

## Default LDAP Configuration
- **Admin DN**: `cn=admin,dc=example,dc=com`
- **Admin Password**: `admin_password`
- **Base DN**: `dc=example,dc=com`
- **LDAP Server**: `ldap` (Docker service name)
- **LDAP Port**: `389`

## Quick Start

### 1. Start the Services
```bash
cd /home/onefirst/Documents/SSO-Git/sso-app
docker-compose up -d --build
```

### 2. Add Test Users to LDAP
After LDAP container starts, add users using ldapadd:

```bash
docker exec sso-ldap ldapadd -x -D "cn=admin,dc=example,dc=com" -w admin_password -f /etc/ldap/ldap-users.ldif
```

Or manually add users via command:

```bash
docker exec sso-ldap ldappasswd -x -D "cn=admin,dc=example,dc=com" -w admin_password -s "password123" "uid=john,ou=users,dc=example,dc=com"
```

### 3. Test RADIUS Authentication
Test with radtest (if installed):

```bash
radtest john password123 localhost 1812 sso_secret_123
```

### 4. Monitor Logs
```bash
docker logs -f sso-radius
docker logs -f sso-ldap
```

## Configuration Files

### radiusd.conf
- Listens on ports 1812 (AUTH) and 1813 (ACCT)
- Logs to stdout for Docker
- Includes LDAP module configuration

### ldap.conf
- LDAP connection settings
- User search filter: `(uid=%{Stripped-User-Name:-%{User-Name}})`
- Connection pooling enabled
- Password attribute: `userPassword`

## Customization

### Modify LDAP Base DN
Edit `radius/config/ldap.conf` and change:
```
base_dn = "dc=example,dc=com"
```

### Change LDAP Admin Password
Edit `docker-compose.yml` and update:
```yaml
LDAP_ADMIN_PASSWORD: "your_secure_password"
```

Then update `radius/config/ldap.conf`:
```
password = "your_secure_password"
```

### Add OU (Organizational Units)
Create the users OU structure in LDAP:

```bash
docker exec sso-ldap ldapadd -x -D "cn=admin,dc=example,dc=com" -w admin_password << EOF
dn: ou=users,dc=example,dc=com
objectClass: organizationalUnit
ou: users
EOF
```

## Troubleshooting

### FreeRADIUS can't connect to LDAP
- Check LDAP container is running: `docker ps | grep ldap`
- Verify network connectivity: `docker exec sso-radius ping ldap`
- Check LDAP logs: `docker logs sso-ldap`

### Authentication fails
- Verify user exists in LDAP: `docker exec sso-ldap ldapsearch -x -b "dc=example,dc=com"`
- Check FreeRADIUS logs for LDAP errors
- Ensure user DN matches the search filter in `ldap.conf`

### LDAP permission denied errors
- Verify admin credentials in `ldap.conf` match `docker-compose.yml`
- Check LDAP admin password is set correctly

## Optional: Enable phpLDAPAdmin UI
Uncomment the `phpldapadmin` service in `docker-compose.yml` and access at:
```
https://localhost:8443
```

Login with admin credentials from docker-compose.yml

## Security Considerations
- Change default passwords in docker-compose.yml before production
- Enable TLS/SSL for LDAP connections (set `LDAP_TLS: "true"` in docker-compose.yml)
- Use strong passwords for admin accounts
- Restrict RADIUS client access in `clients.conf`

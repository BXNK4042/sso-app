-- FreeRADIUS PostgreSQL Database Schema & Init Script

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- NAS (RADIUS Clients / Access Points / Shared Secret) Table
CREATE TABLE IF NOT EXISTS nas (
    id          serial PRIMARY KEY,
    nasname     text NOT NULL,
    shortname   text,
    type        text DEFAULT 'other',
    ports       integer,
    secret      text NOT NULL,
    server      text,
    community   text,
    description text
);
CREATE INDEX IF NOT EXISTS nas_nasname ON nas (nasname);

-- User Authentication Table (radcheck)
CREATE TABLE IF NOT EXISTS radcheck (
    id          serial PRIMARY KEY,
    username    text NOT NULL DEFAULT '',
    attribute   text NOT NULL DEFAULT '',
    op          VARCHAR(2) NOT NULL DEFAULT '==',
    value       text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS radcheck_username ON radcheck (username, attribute);

-- User Reply Attributes Table (radreply)
CREATE TABLE IF NOT EXISTS radreply (
    id          serial PRIMARY KEY,
    username    text NOT NULL DEFAULT '',
    attribute   text NOT NULL DEFAULT '',
    op          VARCHAR(2) NOT NULL DEFAULT '=',
    value       text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS radreply_username ON radreply (username, attribute);

-- User Groups Check Table
CREATE TABLE IF NOT EXISTS radgroupcheck (
    id          serial PRIMARY KEY,
    groupname   text NOT NULL DEFAULT '',
    attribute   text NOT NULL DEFAULT '',
    op          VARCHAR(2) NOT NULL DEFAULT '==',
    value       text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS radgroupcheck_groupname ON radgroupcheck (groupname, attribute);

-- User Groups Reply Table
CREATE TABLE IF NOT EXISTS radgroupreply (
    id          serial PRIMARY KEY,
    groupname   text NOT NULL DEFAULT '',
    attribute   text NOT NULL DEFAULT '',
    op          VARCHAR(2) NOT NULL DEFAULT '=',
    value       text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS radgroupreply_groupname ON radgroupreply (groupname, attribute);

-- User to Group Mapping Table
CREATE TABLE IF NOT EXISTS radusergroup (
    id          serial PRIMARY KEY,
    username    text NOT NULL DEFAULT '',
    groupname   text NOT NULL DEFAULT '',
    priority    integer NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS radusergroup_username ON radusergroup (username);

-- RADIUS Accounting Records Table
CREATE TABLE IF NOT EXISTS radacct (
    radacctid           bigserial PRIMARY KEY,
    acctsessionid       text NOT NULL DEFAULT '',
    acctuniqueid        text NOT NULL DEFAULT '',
    username            text NOT NULL DEFAULT '',
    groupname           text NOT NULL DEFAULT '',
    realm               text DEFAULT '',
    nasipaddress        inet,
    nasportid           text,
    nasporttype         text,
    acctstarttime       timestamp with time zone,
    acctupdatetime      timestamp with time zone,
    acctstoptime        timestamp with time zone,
    acctinterval        bigint,
    acctsessiontime     bigint,
    acctauthentic       text,
    connectinfo_start   text,
    connectinfo_stop    text,
    acctinputoctets     bigint,
    acctoutputoctets    bigint,
    calledstationid     text NOT NULL DEFAULT '',
    callingstationid    text NOT NULL DEFAULT '',
    acctterminatecause  text NOT NULL DEFAULT '',
    servicetype         text,
    framedprotocol      text,
    framedipaddress     inet
);

-- Seed NAS client (Shared secret for RADIUS)
INSERT INTO nas (nasname, shortname, type, secret) VALUES ('0.0.0.0/0', 'dockernet', 'other', 'sso_secret_123') ON CONFLICT DO NOTHING;

-- Seed Demo Users
-- 1. Plaintext password user
INSERT INTO radcheck (username, attribute, op, value) VALUES ('john', 'Cleartext-Password', ':=', 'password123') ON CONFLICT DO NOTHING;
INSERT INTO radreply (username, attribute, op, value) VALUES ('john', 'Reply-Message', ':=', 'Hello John, SSO login successful') ON CONFLICT DO NOTHING;

-- 2. Hashed password user (Bcrypt via Crypt-Password)
INSERT INTO radcheck (username, attribute, op, value) VALUES ('alice', 'Crypt-Password', ':=', crypt('alicepassword123', gen_salt('bf'))) ON CONFLICT DO NOTHING;

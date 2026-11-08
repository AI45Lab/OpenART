-- Calendar Sandbox Database Schema
-- Post-centralized-IdP design: identity is owned by google-idp. This env mirrors
-- only the minimal slice (tenants, users) needed for local FKs, plus the business
-- tables (calendars, events).

CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO tenants (id) VALUES ('default')
    ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    sub         INTEGER,  -- IdP user id; NULL while a seeded mirror awaits its first login
    tenant_id   TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id) ON DELETE CASCADE,
    email       TEXT,
    name        TEXT,
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (sub, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_users_sub   ON users(sub);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_tenant_email ON users (tenant_id, lower(email));

CREATE TABLE IF NOT EXISTS calendars (
    id                TEXT PRIMARY KEY,
    user_id           INTEGER NOT NULL REFERENCES users(id),
    summary           TEXT NOT NULL,
    description       TEXT,
    location          TEXT,
    time_zone         TEXT DEFAULT 'UTC',
    color_id          TEXT,
    background_color  TEXT,
    foreground_color  TEXT,
    selected          BOOLEAN DEFAULT TRUE,
    access_role       TEXT DEFAULT 'owner',
    "primary"         BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMP DEFAULT NOW(),
    updated_at        TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
    id                   TEXT PRIMARY KEY,
    calendar_id          TEXT NOT NULL REFERENCES calendars(id),
    summary              TEXT NOT NULL,
    description          TEXT,
    location             TEXT,
    color_id             TEXT,
    start_datetime       TIMESTAMP,
    start_date           TEXT,
    start_timezone       TEXT,
    end_datetime         TIMESTAMP,
    end_date             TEXT,
    end_timezone         TEXT,
    recurrence           JSONB,
    recurring_event_id   TEXT,
    original_start_time  TIMESTAMP,
    status               TEXT DEFAULT 'confirmed',
    visibility           TEXT DEFAULT 'default',
    transparency         TEXT DEFAULT 'opaque',
    attendees            JSONB,
    organizer            JSONB,
    creator              JSONB,
    reminders            JSONB,
    created_at           TIMESTAMP DEFAULT NOW(),
    updated_at           TIMESTAMP DEFAULT NOW(),
    html_link            TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_calendar ON events(calendar_id);

-- Compatibility aliases preserve original fixture calendar and event IDs.
CREATE TABLE IF NOT EXISTS calendar_aliases (
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    public_id TEXT NOT NULL,
    internal_id TEXT NOT NULL UNIQUE REFERENCES calendars(id) ON DELETE CASCADE,
    PRIMARY KEY (tenant_id, public_id)
);
CREATE TABLE IF NOT EXISTS event_aliases (
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    public_id TEXT NOT NULL,
    internal_id TEXT NOT NULL UNIQUE REFERENCES events(id) ON DELETE CASCADE,
    PRIMARY KEY (tenant_id, public_id)
);

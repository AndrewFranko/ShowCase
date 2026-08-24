-- CaseOps: the operational case-management system UPSTREAM of the Case Spine.
-- This is the system of record the spine's `case_management()` extractor reads.
--
-- Grain: hospitals own devices; analysts work tickets; hospitals report
-- incidents; any change at a hospital fans out as notifications to the
-- analysts holding active tickets there.

DROP TABLE IF EXISTS notification, hospital_change, incident, ticket, analyst, device, hospital CASCADE;

CREATE TABLE hospital (
    hospital_id  int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         text NOT NULL UNIQUE,
    region       text NOT NULL,
    site_class   text NOT NULL CHECK (site_class IN ('hospital', 'office'))
);

CREATE TABLE device (
    device_id    int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hospital_id  int  NOT NULL REFERENCES hospital,
    make         text NOT NULL,
    model        text NOT NULL,
    detector     text NOT NULL CHECK (detector IN ('EID', 'PCD')),
    sw_version   text NOT NULL,
    installed_on date NOT NULL
);

CREATE TABLE analyst (
    analyst_id       int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name             text NOT NULL UNIQUE,
    level            text NOT NULL CHECK (level IN ('junior', 'senior', 'lead')),
    capacity_min_day int  NOT NULL CHECK (capacity_min_day > 0)
);

CREATE TABLE ticket (
    ticket_id   int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hospital_id int NOT NULL REFERENCES hospital,
    device_id   int NOT NULL REFERENCES device,
    analyst_id  int REFERENCES analyst,
    status      text NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'assigned', 'in_review', 'blocked', 'resolved')),
    priority    int NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    est_min     int NOT NULL CHECK (est_min > 0),
    actual_min  int CHECK (actual_min > 0),
    created_at  timestamptz NOT NULL,
    assigned_at timestamptz,
    resolved_at timestamptz
);

CREATE TABLE incident (
    incident_id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hospital_id int NOT NULL REFERENCES hospital,
    device_id   int REFERENCES device,          -- NULL = site-wide
    kind        text NOT NULL,
    severity    int  NOT NULL CHECK (severity BETWEEN 1 AND 4),
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'ack', 'closed')),
    reported_at timestamptz NOT NULL DEFAULT now(),
    description text NOT NULL
);

CREATE TABLE hospital_change (
    change_id   int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hospital_id int NOT NULL REFERENCES hospital,
    device_id   int REFERENCES device,          -- NULL = site-wide
    kind        text NOT NULL CHECK (kind IN
                ('device_swap', 'sw_update', 'detector_upgrade', 'protocol_change')),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    details     text NOT NULL
);

-- The warning fan-out target. One row per (event, affected analyst); the array
-- pins exactly WHICH of their tickets the event touches, so catch-up is
-- actionable rather than a broadcast.
CREATE TABLE notification (
    notif_id   int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analyst_id int  NOT NULL REFERENCES analyst,
    source     text NOT NULL CHECK (source IN ('change', 'incident')),
    source_id  int  NOT NULL,
    ticket_ids int[] NOT NULL,
    message    text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    read_at    timestamptz
);

CREATE INDEX idx_ticket_hospital_status ON ticket (hospital_id, status);
CREATE INDEX idx_ticket_analyst_status  ON ticket (analyst_id, status);
CREATE INDEX idx_notif_unread ON notification (analyst_id) WHERE read_at IS NULL;

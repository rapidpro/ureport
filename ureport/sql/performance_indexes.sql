-- Performance optimization: Add missing indexes to reduce database I/O
-- These indexes will significantly improve the performance of the most common queries

-- Index for stats_contactactivity lookups by org_id, contact, and date
-- This is heavily used in the ureport_insert_missing_contact_activities function
CREATE INDEX CONCURRENTLY IF NOT EXISTS stats_contactactivity_org_contact_date_idx 
ON stats_contactactivity(org_id, contact, date);

-- Index for frequent updates on stats_contactactivity by org_id and contact
CREATE INDEX CONCURRENTLY IF NOT EXISTS stats_contactactivity_org_contact_recent_idx 
ON stats_contactactivity(org_id, contact) 
WHERE date > (CURRENT_DATE - INTERVAL '1 year');

-- Index for polls_pollresult by org_id and date for better query performance
CREATE INDEX CONCURRENTLY IF NOT EXISTS polls_pollresult_org_date_idx 
ON polls_pollresult(org_id, date);

-- Index for contacts_contact by org_id and is_active for counter queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS contacts_contact_org_active_idx 
ON contacts_contact(org_id, is_active);

-- Composite index for the most common stats query patterns
CREATE INDEX CONCURRENTLY IF NOT EXISTS stats_contactactivity_lookup_idx 
ON stats_contactactivity(org_id, date) 
WHERE used = true;
// ShadowHive Neo4j Schema — Attack Graph
// Manages attacker IPs, sessions, events, MITRE techniques, and tactics

// ── Constraints ───────────────────────────────────────────────────────────

CREATE CONSTRAINT attacker_ip_address IF NOT EXISTS FOR (ip:AttackerIP) REQUIRE ip.address IS UNIQUE;
CREATE CONSTRAINT session_id IF NOT EXISTS FOR (s:Session) REQUIRE s.session_id IS UNIQUE;
CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.event_id IS UNIQUE;
CREATE CONSTRAINT technique_id IF NOT EXISTS FOR (t:Technique) REQUIRE t.technique_id IS UNIQUE;
CREATE CONSTRAINT tactic_name IF NOT EXISTS FOR (t:Tactic) REQUIRE t.tactic IS UNIQUE;

// ── Indexes ───────────────────────────────────────────────────────────────

CREATE INDEX ip_address IF NOT EXISTS FOR (ip:AttackerIP) ON (ip.address);
CREATE INDEX event_timestamp IF NOT EXISTS FOR (e:Event) ON (e.timestamp);
CREATE INDEX technique_technique_id IF NOT EXISTS FOR (t:Technique) ON (t.technique_id);

// ── Relationship summary ──────────────────────────────────────────────────
//
// (AttackerIP)-[:INITIATED]->(Session)-[:CONTAINS]->(Event)-[:MAPS_TO]->(Technique)-[:PART_OF]->(Tactic)
//

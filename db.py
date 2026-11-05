import sqlite3
import os
import time

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "health.db")


def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def create_database():
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Telemetry table (backward-compatible)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS health_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                ip_address TEXT,
                timestamp TEXT NOT NULL,
                cpu REAL,
                memory REAL,
                processes INTEGER,
                sent INTEGER,
                received INTEGER,
                status TEXT,
                active_attack INTEGER DEFAULT 0,
                upload_mbps REAL DEFAULT 0.0,
                download_mbps REAL DEFAULT 0.0,
                sequence_number INTEGER DEFAULT 0
            )
        """)

        # Add upload_mbps / download_mbps columns to health_data if migrating older db
        try:
            cursor.execute("ALTER TABLE health_data ADD COLUMN upload_mbps REAL DEFAULT 0.0;")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE health_data ADD COLUMN download_mbps REAL DEFAULT 0.0;")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE health_data ADD COLUMN sequence_number INTEGER DEFAULT 0;")
        except Exception:
            pass

        # Indexes for fast querying
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_id ON health_data(agent_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON health_data(timestamp);")

        # 2. Nodes Registry
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                agent_id TEXT PRIMARY KEY,
                ip_address TEXT NOT NULL,
                c2_port INTEGER DEFAULT 5001,
                role TEXT DEFAULT 'client',
                status TEXT DEFAULT 'HEALTHY',
                last_seen REAL,
                registered_at TEXT
            )
        """)

        # 3. Router Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routers (
                router_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'HEALTHY',
                cpu_percent REAL DEFAULT 0.0,
                memory_percent REAL DEFAULT 0.0,
                uptime_sec REAL DEFAULT 0.0,
                last_seen REAL
            )
        """)

        # 4. Router Interfaces Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS router_interfaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                router_id TEXT NOT NULL,
                iface_name TEXT NOT NULL,
                ip_address TEXT,
                subnet TEXT,
                state TEXT DEFAULT 'UP',
                rx_bytes INTEGER DEFAULT 0,
                tx_bytes INTEGER DEFAULT 0,
                rx_drops INTEGER DEFAULT 0,
                tx_drops INTEGER DEFAULT 0,
                timestamp TEXT,
                FOREIGN KEY (router_id) REFERENCES routers(router_id)
            )
        """)

        # 5. Backend Nodes Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backend_nodes (
                backend_id TEXT PRIMARY KEY,
                hostname TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                port INTEGER NOT NULL,
                weight INTEGER DEFAULT 1,
                status TEXT DEFAULT 'HEALTHY',
                active_connections INTEGER DEFAULT 0,
                total_requests INTEGER DEFAULT 0,
                consecutive_failures INTEGER DEFAULT 0,
                last_check REAL
            )
        """)

        # 6. Load Balancer Metrics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lb_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                algorithm TEXT NOT NULL,
                total_requests INTEGER DEFAULT 0,
                requests_per_sec REAL DEFAULT 0.0,
                active_requests INTEGER DEFAULT 0,
                avg_response_ms REAL DEFAULT 0.0,
                p95_response_ms REAL DEFAULT 0.0,
                p99_response_ms REAL DEFAULT 0.0
            )
        """)

        # 7. SDN Events (backward-compatible)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sdn_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                agent_id TEXT,
                event_type TEXT,
                description TEXT,
                mitigation_status TEXT
            )
        """)

        # 8. Unified System Events Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE,
                timestamp TEXT NOT NULL,
                component TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT DEFAULT 'INFO',
                observed_metric TEXT,
                threshold TEXT,
                description TEXT,
                action_taken TEXT,
                status TEXT DEFAULT 'DETECTED',
                recovery_timestamp TEXT
            )
        """)

        # 9. Simulation Events Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS simulation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sim_id TEXT NOT NULL,
                sim_type TEXT NOT NULL,
                target_node TEXT NOT NULL,
                parameters TEXT,
                started_at TEXT NOT NULL,
                stopped_at TEXT,
                status TEXT DEFAULT 'RUNNING'
            )
        """)

        # 10. Audit Logs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                actor TEXT DEFAULT 'SYSTEM',
                action TEXT NOT NULL,
                target TEXT,
                result TEXT DEFAULT 'SUCCESS',
                details TEXT
            )
        """)

        conn.commit()


def insert_data(agent_id, ip_address, timestamp, cpu, memory, processes, sent, received, status="NORMAL", active_attack=0, upload_mbps=0.0, download_mbps=0.0, sequence_number=0):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO health_data
                (agent_id, ip_address, timestamp, cpu, memory, processes, sent, received, status, active_attack, upload_mbps, download_mbps, sequence_number)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (agent_id, ip_address, timestamp, cpu, memory, processes, sent, received, status, 1 if active_attack else 0, upload_mbps, download_mbps, sequence_number))
            
            # Upsert into nodes table
            cursor.execute("""
                INSERT INTO nodes (agent_id, ip_address, status, last_seen, registered_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    ip_address = excluded.ip_address,
                    status = excluded.status,
                    last_seen = excluded.last_seen
            """, (agent_id, ip_address, status, time.time(), timestamp))
            
            conn.commit()
    except Exception as e:
        print(f"[DB Error] Failed to insert telemetry: {e}")


def log_sdn_event(timestamp, agent_id, event_type, description, mitigation_status):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sdn_events (timestamp, agent_id, event_type, description, mitigation_status)
                VALUES (?, ?, ?, ?, ?)
            """, (timestamp, agent_id, event_type, description, mitigation_status))
            
            # Also log to unified system_events
            cursor.execute("""
                INSERT INTO system_events (event_id, timestamp, component, event_type, severity, description, action_taken, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (f"sdn_{int(time.time()*1000)}", timestamp, agent_id or "SDN", event_type, "WARNING" if "DROP" in mitigation_status else "INFO", description, mitigation_status, "MITIGATED"))
            conn.commit()
    except Exception as e:
        print(f"[DB Error] Failed to log SDN event: {e}")


def log_system_event(event_type, component, severity, description, observed_metric=None, threshold=None, action_taken=None, status="DETECTED"):
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        eid = f"evt_{int(time.time()*1000)}"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO system_events (event_id, timestamp, component, event_type, severity, observed_metric, threshold, description, action_taken, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (eid, ts, component, event_type, severity, str(observed_metric), str(threshold), description, action_taken, status))
            conn.commit()
            return eid
    except Exception as e:
        print(f"[DB Error] Failed to log system event: {e}")
        return None


def log_audit(action, target, result="SUCCESS", actor="SYSTEM", details=""):
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_logs (timestamp, actor, action, target, result, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (ts, actor, action, target, result, details))
            conn.commit()
    except Exception as e:
        print(f"[DB Error] Failed to log audit: {e}")


def update_router_metrics(router_id, cpu_percent, memory_percent, status="HEALTHY"):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO routers (router_id, status, cpu_percent, memory_percent, last_seen)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(router_id) DO UPDATE SET
                    status = excluded.status,
                    cpu_percent = excluded.cpu_percent,
                    memory_percent = excluded.memory_percent,
                    last_seen = excluded.last_seen
            """, (router_id, status, cpu_percent, memory_percent, time.time()))
            conn.commit()
    except Exception as e:
        print(f"[DB Error] Failed to update router metrics: {e}")


def insert_router_interface(router_id, iface_name, ip_address, subnet, state, rx_bytes, tx_bytes, rx_drops, tx_drops):
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO router_interfaces (router_id, iface_name, ip_address, subnet, state, rx_bytes, tx_bytes, rx_drops, tx_drops, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (router_id, iface_name, ip_address, subnet, state, rx_bytes, tx_bytes, rx_drops, tx_drops, ts))
            conn.commit()
    except Exception as e:
        print(f"[DB Error] Failed to insert router interface: {e}")


def insert_lb_metrics(algorithm, total_requests, rps, active_requests, avg_ms, p95_ms, p99_ms):
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO lb_metrics (timestamp, algorithm, total_requests, requests_per_sec, active_requests, avg_response_ms, p95_response_ms, p99_response_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (ts, algorithm, total_requests, rps, active_requests, avg_ms, p95_ms, p99_ms))
            conn.commit()
    except Exception as e:
        print(f"[DB Error] Failed to insert lb metrics: {e}")


def get_latest_node_states():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT h.* FROM health_data h
            INNER JOIN (
                SELECT agent_id, MAX(id) as max_id
                FROM health_data
                GROUP BY agent_id
            ) latest ON h.id = latest.max_id
            ORDER BY h.agent_id ASC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_recent_telemetry(agent_id=None, limit=30):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if agent_id:
            cursor.execute("""
                SELECT * FROM health_data
                WHERE agent_id = ?
                ORDER BY id DESC LIMIT ?
            """, (agent_id, limit))
        else:
            cursor.execute("""
                SELECT * FROM health_data
                ORDER BY id DESC LIMIT ?
            """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in reversed(rows)]


def get_sdn_events(limit=20):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM sdn_events
            ORDER BY id DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_system_events(limit=50):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM system_events
            ORDER BY id DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_audit_logs(limit=50):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM audit_logs
            ORDER BY id DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

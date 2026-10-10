import sqlite3
import os

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "health.db")


def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def create_database():
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Telemetry table
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
                active_attack INTEGER DEFAULT 0
            )
        """)

        # Indexes for fast querying
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_id ON health_data(agent_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON health_data(timestamp);")

        # SDN Events & Anomaly Audit log table
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

        conn.commit()


def insert_data(agent_id, ip_address, timestamp, cpu, memory, processes, sent, received, status="NORMAL", active_attack=0):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO health_data
                (agent_id, ip_address, timestamp, cpu, memory, processes, sent, received, status, active_attack)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (agent_id, ip_address, timestamp, cpu, memory, processes, sent, received, status, 1 if active_attack else 0))
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
            conn.commit()
    except Exception as e:
        print(f"[DB Error] Failed to log SDN event: {e}")


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
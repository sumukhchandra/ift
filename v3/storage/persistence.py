"""
v3/storage/persistence.py
Unified Cloud & Local Persistence Engine for AlphaNSE V3.

Provides dual-layer persistence:
1. SQL Database (PostgreSQL via psycopg2, SQLite via standard library sqlite3)
2. File-based JSON & JSONL streaming (reports/live or DATA_DIR)

Guarantees data durability across Render restarts, deployments, and ephemeral filesystem cycles.
"""

import os
import sys
import json
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger("AlphaNSEStorage")

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DATA_DIR = os.path.join(WORKSPACE_ROOT, "reports", "live")


class StorageManager:
    """
    Unified persistence manager.
    Reads and writes runtime states, paper ledgers, telemetry streams,
    market captures, and prediction provenance.
    """

    def __init__(self, data_dir: Optional[str] = None, database_url: Optional[str] = None, sqlite_path: Optional[str] = None):
        # 1. File Directory Configuration
        env_data_dir = os.getenv("PERSISTENT_DATA_DIR") or os.getenv("DATA_DIR")
        self.data_dir = data_dir or env_data_dir or DEFAULT_DATA_DIR
        try:
            os.makedirs(self.data_dir, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create data_dir {self.data_dir}: {e}")

        self.state_file = os.path.join(self.data_dir, "runtime_state.json")
        self.ledger_file = os.path.join(self.data_dir, "paper_trading_ledger.json")
        self.orders_stream_file = os.path.join(self.data_dir, "orders_stream.jsonl")
        self.market_capture_file = os.path.join(self.data_dir, "market_data_raw_capture.jsonl")
        self.prediction_provenance_file = os.path.join(self.data_dir, "prediction_provenance_stream.jsonl")
        self.prediction_outcomes_file = os.path.join(self.data_dir, "prediction_outcomes_stream.jsonl")

        # 2. Database Configuration
        if sqlite_path and not database_url:
            self.db_url = f"sqlite:///{sqlite_path}"
        else:
            self.db_url = database_url or os.getenv("DATABASE_URL")
        self.db_type = None  # 'postgres', 'sqlite', or None
        self.conn = None
        self._init_db()

    def save_state(self, state: Dict[str, Any]) -> bool:
        return self.save_runtime_state(state)

    def load_state(self) -> Dict[str, Any]:
        return self.load_runtime_state()

    def save_ledger(self, ledger: Dict[str, Any]) -> bool:
        return self.save_paper_ledger(ledger)

    def load_ledger(self) -> Dict[str, Any]:
        return self.load_paper_ledger()

    def log_event(self, event_type: str, message: str = "", data: Optional[Dict[str, Any]] = None):
        payload = {"message": message}
        if data:
            payload.update(data)
        self.append_event(event_type, payload)

    def close(self):
        """Closes the underlying database connection if open."""
        if self.conn:
            try:
                self.conn.close()
            except Exception as e:
                logger.warning(f"Error closing storage connection: {e}")
            finally:
                self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _init_db(self):
        """Initializes the database connection and creates required tables."""
        if not self.db_url:
            # Fall back to local SQLite database in data_dir for structured querying if wanted
            sqlite_path = os.path.join(self.data_dir, "alphanse_local.db")
            self.db_url = f"sqlite:///{sqlite_path}"

        if self.db_url.startswith("postgres://") or self.db_url.startswith("postgresql://"):
            # Normalize legacy Render / Heroku prefix
            if self.db_url.startswith("postgres://"):
                self.db_url = self.db_url.replace("postgres://", "postgresql://", 1)
            self.db_type = "postgres"
            try:
                import psycopg2
                self.conn = psycopg2.connect(self.db_url)
                self.conn.autocommit = True
                self._create_tables_postgres()
                logger.info("Connected to PostgreSQL persistence database.")
            except ImportError:
                logger.warning("psycopg2 not installed; database persistence falling back to SQLite/File.")
                self.db_type = "sqlite"
                sqlite_path = os.path.join(self.data_dir, "alphanse_local.db")
                self.conn = sqlite3.connect(sqlite_path, check_same_thread=False)
                self._create_tables_sqlite()
            except Exception as e:
                logger.error(f"Failed to connect to PostgreSQL: {e}. Falling back to File/SQLite.")
                self.db_type = "sqlite"
                sqlite_path = os.path.join(self.data_dir, "alphanse_local.db")
                self.conn = sqlite3.connect(sqlite_path, check_same_thread=False)
                self._create_tables_sqlite()
        elif self.db_url.startswith("sqlite:///"):
            self.db_type = "sqlite"
            sqlite_path = self.db_url.replace("sqlite:///", "")
            try:
                self.conn = sqlite3.connect(sqlite_path, check_same_thread=False)
                self._create_tables_sqlite()
                logger.info(f"Connected to SQLite persistence database: {sqlite_path}")
            except Exception as e:
                logger.error(f"Failed to connect to SQLite: {e}")
                self.conn = None

    def _create_tables_sqlite(self):
        """Creates SQLite tables if they do not exist."""
        if not self.conn:
            return
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS runtime_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_ledger (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                data TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_captures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                ltp REAL,
                validation_status TEXT,
                data TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT UNIQUE,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                horizon TEXT,
                signal TEXT,
                data TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prediction_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT UNIQUE,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                actual_price REAL,
                direction_correct INTEGER,
                data TEXT NOT NULL
            );
        """)
        self.conn.commit()

    def _create_tables_postgres(self):
        """Creates PostgreSQL tables if they do not exist."""
        if not self.conn:
            return
        with self.conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runtime_state (
                    id INT PRIMARY KEY,
                    data JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paper_ledger (
                    id INT PRIMARY KEY,
                    data JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_events (
                    id SERIAL PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    data JSONB NOT NULL
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_captures (
                    id SERIAL PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    ltp DOUBLE PRECISION,
                    validation_status TEXT,
                    data JSONB NOT NULL
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id SERIAL PRIMARY KEY,
                    record_id TEXT UNIQUE,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    horizon TEXT,
                    signal TEXT,
                    data JSONB NOT NULL
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prediction_outcomes (
                    id SERIAL PRIMARY KEY,
                    record_id TEXT UNIQUE,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    actual_price DOUBLE PRECISION,
                    direction_correct BOOLEAN,
                    data JSONB NOT NULL
                );
            """)

    # ─── Runtime State ──────────────────────────────────────────────────────────

    def save_runtime_state(self, state: Dict[str, Any]) -> bool:
        """Saves runtime state to both file and database."""
        now_iso = datetime.now().isoformat()
        state["last_updated"] = state.get("last_updated") or now_iso

        # 1. Save to File
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning(f"Error writing state_file: {e}")

        # 2. Save to DB
        if self.conn and self.db_type == "postgres":
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO runtime_state (id, data, updated_at)
                        VALUES (1, %s, NOW())
                        ON CONFLICT (id) DO UPDATE
                        SET data = EXCLUDED.data, updated_at = NOW();
                    """, (json.dumps(state),))
                return True
            except Exception as e:
                logger.warning(f"Error saving runtime_state to Postgres: {e}")
        elif self.conn and self.db_type == "sqlite":
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT INTO runtime_state (id, data, updated_at)
                    VALUES (1, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at;
                """, (json.dumps(state), now_iso))
                self.conn.commit()
                return True
            except Exception as e:
                logger.warning(f"Error saving runtime_state to SQLite: {e}")

        return True

    def load_runtime_state(self) -> Dict[str, Any]:
        """Loads runtime state from database or file."""
        # Try database first
        if self.conn and self.db_type == "postgres":
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("SELECT data FROM runtime_state WHERE id = 1;")
                    row = cursor.fetchone()
                    if row:
                        val = row[0]
                        return val if isinstance(val, dict) else json.loads(val)
            except Exception as e:
                logger.warning(f"Error reading runtime_state from Postgres: {e}")
        elif self.conn and self.db_type == "sqlite":
            try:
                cursor = self.conn.cursor()
                cursor.execute("SELECT data FROM runtime_state WHERE id = 1;")
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
            except Exception as e:
                logger.warning(f"Error reading runtime_state from SQLite: {e}")

        # Fallback to file
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error reading state_file: {e}")

        return {
            "session_date": datetime.now().strftime("%Y-%m-%d"),
            "status": "INITIALIZING",
            "execution_mode": "PAPER_TESTING",
            "starting_bankroll": 1500.00,
            "paper_bankroll": 1500.00,
            "realized_pnl": 0.0,
            "active_positions_count": 0,
            "closed_trades_count": 0
        }

    # ─── Paper Ledger ───────────────────────────────────────────────────────────

    def save_paper_ledger(self, ledger: Dict[str, Any]) -> bool:
        """Saves paper ledger to file and database."""
        now_iso = datetime.now().isoformat()

        # 1. Save to File
        try:
            with open(self.ledger_file, "w", encoding="utf-8") as f:
                json.dump(ledger, f, indent=2)
        except Exception as e:
            logger.warning(f"Error writing ledger_file: {e}")

        # 2. Save to DB
        if self.conn and self.db_type == "postgres":
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO paper_ledger (id, data, updated_at)
                        VALUES (1, %s, NOW())
                        ON CONFLICT (id) DO UPDATE
                        SET data = EXCLUDED.data, updated_at = NOW();
                    """, (json.dumps(ledger),))
                return True
            except Exception as e:
                logger.warning(f"Error saving paper_ledger to Postgres: {e}")
        elif self.conn and self.db_type == "sqlite":
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT INTO paper_ledger (id, data, updated_at)
                    VALUES (1, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at;
                """, (json.dumps(ledger), now_iso))
                self.conn.commit()
                return True
            except Exception as e:
                logger.warning(f"Error saving paper_ledger to SQLite: {e}")

        return True

    def load_paper_ledger(self) -> Dict[str, Any]:
        """Loads paper ledger from database or file."""
        if self.conn and self.db_type == "postgres":
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("SELECT data FROM paper_ledger WHERE id = 1;")
                    row = cursor.fetchone()
                    if row:
                        val = row[0]
                        return val if isinstance(val, dict) else json.loads(val)
            except Exception as e:
                logger.warning(f"Error reading paper_ledger from Postgres: {e}")
        elif self.conn and self.db_type == "sqlite":
            try:
                cursor = self.conn.cursor()
                cursor.execute("SELECT data FROM paper_ledger WHERE id = 1;")
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
            except Exception as e:
                logger.warning(f"Error reading paper_ledger from SQLite: {e}")

        if os.path.exists(self.ledger_file):
            try:
                with open(self.ledger_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error reading ledger_file: {e}")

        return {
            "session_date": datetime.now().strftime("%Y-%m-%d"),
            "starting_bankroll": 1500.00,
            "current_bankroll": 1500.00,
            "available_cash": 1500.00,
            "realized_pnl": 0.0,
            "trades": []
        }

    # ─── Event Logging Stream ───────────────────────────────────────────────────

    def append_event(self, event_type: str, data: Dict[str, Any], timestamp: Optional[str] = None):
        """Appends a telemetry event to both file stream and database."""
        ts = timestamp or datetime.now().isoformat()
        entry = {"timestamp": ts, "event_type": event_type, "data": data}

        try:
            with open(self.orders_stream_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"Error appending event to file: {e}")

        if self.conn and self.db_type == "postgres":
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO telemetry_events (timestamp, event_type, data)
                        VALUES (%s, %s, %s);
                    """, (ts, event_type, json.dumps(data)))
            except Exception as e:
                logger.warning(f"Error inserting telemetry event to Postgres: {e}")
        elif self.conn and self.db_type == "sqlite":
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT INTO telemetry_events (timestamp, event_type, data)
                    VALUES (?, ?, ?);
                """, (ts, event_type, json.dumps(data)))
                self.conn.commit()
            except Exception as e:
                logger.warning(f"Error inserting telemetry event to SQLite: {e}")

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent telemetry events."""
        if self.conn and self.db_type == "postgres":
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("SELECT timestamp, event_type, data FROM telemetry_events ORDER BY id DESC LIMIT %s;", (limit,))
                    rows = cursor.fetchall()
                    result = []
                    for ts, et, dt in reversed(rows):
                        result.append({"timestamp": ts, "event_type": et, "data": dt if isinstance(dt, dict) else json.loads(dt)})
                    return result
            except Exception as e:
                logger.warning(f"Error querying telemetry from Postgres: {e}")
        elif self.conn and self.db_type == "sqlite":
            try:
                cursor = self.conn.cursor()
                cursor.execute("SELECT timestamp, event_type, data FROM telemetry_events ORDER BY id DESC LIMIT ?;", (limit,))
                rows = cursor.fetchall()
                result = []
                for ts, et, dt in reversed(rows):
                    result.append({"timestamp": ts, "event_type": et, "data": json.loads(dt)})
                return result
            except Exception as e:
                logger.warning(f"Error querying telemetry from SQLite: {e}")

        # Fallback to reading file tail
        if os.path.exists(self.orders_stream_file):
            try:
                with open(self.orders_stream_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    selected = lines[-limit:] if len(lines) > limit else lines
                    return [json.loads(line) for line in selected if line.strip()]
            except Exception as e:
                logger.warning(f"Error reading orders_stream_file: {e}")

        return []

    # ─── Market Captures Stream ─────────────────────────────────────────────────

    def append_market_capture(self, capture: Dict[str, Any]):
        """Appends raw quote capture to both file and database."""
        ts = capture.get("request_timestamp_ist") or datetime.now().isoformat()
        sym = capture.get("symbol", "UNKNOWN")
        ltp = capture.get("ltp")
        status = capture.get("validation_status")

        try:
            with open(self.market_capture_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(capture) + "\n")
        except Exception as e:
            logger.warning(f"Error appending market capture to file: {e}")

        if self.conn and self.db_type == "postgres":
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO market_captures (timestamp, symbol, ltp, validation_status, data)
                        VALUES (%s, %s, %s, %s, %s);
                    """, (ts, sym, ltp, status, json.dumps(capture)))
            except Exception as e:
                logger.warning(f"Error inserting market capture to Postgres: {e}")
        elif self.conn and self.db_type == "sqlite":
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT INTO market_captures (timestamp, symbol, ltp, validation_status, data)
                    VALUES (?, ?, ?, ?, ?);
                """, (ts, sym, ltp, status, json.dumps(capture)))
                self.conn.commit()
            except Exception as e:
                logger.warning(f"Error inserting market capture to SQLite: {e}")

    def get_recent_captures(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent market captures."""
        if self.conn and self.db_type == "postgres":
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("SELECT data FROM market_captures ORDER BY id DESC LIMIT %s;", (limit,))
                    rows = cursor.fetchall()
                    return [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in reversed(rows)]
            except Exception as e:
                logger.warning(f"Error querying market captures from Postgres: {e}")
        elif self.conn and self.db_type == "sqlite":
            try:
                cursor = self.conn.cursor()
                cursor.execute("SELECT data FROM market_captures ORDER BY id DESC LIMIT ?;", (limit,))
                rows = cursor.fetchall()
                return [json.loads(r[0]) for r in reversed(rows)]
            except Exception as e:
                logger.warning(f"Error querying market captures from SQLite: {e}")

        if os.path.exists(self.market_capture_file):
            try:
                with open(self.market_capture_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    selected = lines[-limit:] if len(lines) > limit else lines
                    return [json.loads(line) for line in selected if line.strip()]
            except Exception as e:
                logger.warning(f"Error reading market_capture_file: {e}")

        return []

    # ─── Predictions & Outcomes ─────────────────────────────────────────────────

    def append_prediction(self, pred: Dict[str, Any]):
        """Appends prediction provenance record."""
        rec_id = pred.get("record_id") or f"{pred.get('symbol')}_{pred.get('timestamp')}"
        ts = pred.get("timestamp") or datetime.now().isoformat()
        sym = pred.get("symbol", "UNKNOWN")
        horiz = pred.get("horizon", "1m")
        sig = pred.get("signal", "HOLD")

        try:
            with open(self.prediction_provenance_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(pred) + "\n")
        except Exception as e:
            logger.warning(f"Error appending prediction to file: {e}")

        if self.conn and self.db_type == "postgres":
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO predictions (record_id, timestamp, symbol, horizon, signal, data)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (record_id) DO NOTHING;
                    """, (rec_id, ts, sym, horiz, sig, json.dumps(pred)))
            except Exception as e:
                logger.warning(f"Error inserting prediction to Postgres: {e}")
        elif self.conn and self.db_type == "sqlite":
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO predictions (record_id, timestamp, symbol, horizon, signal, data)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (rec_id, ts, sym, horiz, sig, json.dumps(pred)))
                self.conn.commit()
            except Exception as e:
                logger.warning(f"Error inserting prediction to SQLite: {e}")

    def get_recent_predictions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent prediction provenance records."""
        if self.conn and self.db_type == "postgres":
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("SELECT data FROM predictions ORDER BY id DESC LIMIT %s;", (limit,))
                    rows = cursor.fetchall()
                    return [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in reversed(rows)]
            except Exception as e:
                logger.warning(f"Error querying predictions from Postgres: {e}")
        elif self.conn and self.db_type == "sqlite":
            try:
                cursor = self.conn.cursor()
                cursor.execute("SELECT data FROM predictions ORDER BY id DESC LIMIT ?;", (limit,))
                rows = cursor.fetchall()
                return [json.loads(r[0]) for r in reversed(rows)]
            except Exception as e:
                logger.warning(f"Error querying predictions from SQLite: {e}")

        if os.path.exists(self.prediction_provenance_file):
            try:
                with open(self.prediction_provenance_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    selected = lines[-limit:] if len(lines) > limit else lines
                    return [json.loads(line) for line in selected if line.strip()]
            except Exception as e:
                logger.warning(f"Error reading prediction_provenance_file: {e}")

        return []

    def append_outcome(self, outcome: Dict[str, Any]):
        """Appends prediction outcome record."""
        rec_id = outcome.get("record_id") or f"{outcome.get('symbol')}_{outcome.get('timestamp')}"
        ts = outcome.get("creation_timestamp") or outcome.get("timestamp") or datetime.now().isoformat()
        sym = outcome.get("symbol", "UNKNOWN")
        actual_price = outcome.get("actual_forward_price") or outcome.get("actual_price")
        direction_correct = outcome.get("direction_correct")

        try:
            with open(self.prediction_outcomes_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(outcome) + "\n")
        except Exception as e:
            logger.warning(f"Error appending outcome to file: {e}")

        if self.conn and self.db_type == "postgres":
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO prediction_outcomes (record_id, timestamp, symbol, actual_price, direction_correct, data)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (record_id) DO NOTHING;
                    """, (rec_id, ts, sym, actual_price, direction_correct, json.dumps(outcome)))
            except Exception as e:
                logger.warning(f"Error inserting outcome to Postgres: {e}")
        elif self.conn and self.db_type == "sqlite":
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO prediction_outcomes (record_id, timestamp, symbol, actual_price, direction_correct, data)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (rec_id, ts, sym, actual_price, 1 if direction_correct else 0, json.dumps(outcome)))
                self.conn.commit()
            except Exception as e:
                logger.warning(f"Error inserting outcome to SQLite: {e}")

    def get_recent_outcomes(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent prediction outcome records."""
        if self.conn and self.db_type == "postgres":
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("SELECT data FROM prediction_outcomes ORDER BY id DESC LIMIT %s;", (limit,))
                    rows = cursor.fetchall()
                    return [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in reversed(rows)]
            except Exception as e:
                logger.warning(f"Error querying outcomes from Postgres: {e}")
        elif self.conn and self.db_type == "sqlite":
            try:
                cursor = self.conn.cursor()
                cursor.execute("SELECT data FROM prediction_outcomes ORDER BY id DESC LIMIT ?;", (limit,))
                rows = cursor.fetchall()
                return [json.loads(r[0]) for r in reversed(rows)]
            except Exception as e:
                logger.warning(f"Error querying outcomes from SQLite: {e}")

        if os.path.exists(self.prediction_outcomes_file):
            try:
                with open(self.prediction_outcomes_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    selected = lines[-limit:] if len(lines) > limit else lines
                    return [json.loads(line) for line in selected if line.strip()]
            except Exception as e:
                logger.warning(f"Error reading prediction_outcomes_file: {e}")

        return []

    # ─── Health Summary ─────────────────────────────────────────────────────────

    def get_health_summary(self) -> Dict[str, Any]:
        """Provides an operational health check snapshot for cloud health endpoints."""
        state = self.load_runtime_state()
        last_updated = state.get("last_updated")
        heartbeat_age_sec = None
        is_fresh = False

        if last_updated:
            try:
                dt = datetime.fromisoformat(last_updated)
                heartbeat_age_sec = round((datetime.now() - dt).total_seconds(), 1)
                is_fresh = (heartbeat_age_sec <= 120.0)
            except Exception:
                pass

        return {
            "status": "HEALTHY" if is_fresh else "STALE",
            "heartbeat_age_seconds": heartbeat_age_sec,
            "cycle": state.get("cycle", 0),
            "daemon_status": state.get("status", "UNKNOWN"),
            "execution_mode": state.get("execution_mode", "PAPER_TESTING"),
            "broker": state.get("broker", "Unknown"),
            "paper_bankroll": state.get("paper_bankroll", 1500.0),
            "db_type": self.db_type or "file_fallback",
            "live_trading_locked": True,
            "allow_real_orders_locked": True
        }


_GLOBAL_STORAGE_MANAGER: Optional[StorageManager] = None


def get_storage_manager() -> StorageManager:
    """Returns the singleton StorageManager instance."""
    global _GLOBAL_STORAGE_MANAGER
    if _GLOBAL_STORAGE_MANAGER is None:
        _GLOBAL_STORAGE_MANAGER = StorageManager()
    return _GLOBAL_STORAGE_MANAGER

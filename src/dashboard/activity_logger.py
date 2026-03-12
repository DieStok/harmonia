"""
Dashboard activity logger — writes structured JSON-lines to logs/dashboard/.

Logs all user interactions (tab switches, run selections, chart clicks, etc.)
to daily-rotating log files for auditing and the Activity Log tab.

Usage:
    from dashboard.activity_logger import DashboardActivityLogger

    activity_logger = DashboardActivityLogger(Path("logs/dashboard"))
    activity_logger.log("tab_switch", {"tab_id": "metrics"})
"""

import json
import logging
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from uuid import uuid4


class DashboardActivityLogger:
    """Structured JSON-lines logger for dashboard interactions."""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = uuid4().hex[:8]

        self._logger = logging.getLogger("harmonia.dashboard.activity")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False  # Don't duplicate to root logger

        # Avoid adding duplicate handlers if module is re-imported
        if not self._logger.handlers:
            # Active file: dashboard.log; rotated files: dashboard.log.2026-03-12 etc.
            handler = TimedRotatingFileHandler(
                filename=self.log_dir / "dashboard.log",
                when="midnight",
                backupCount=90,  # Keep 90 days
                utc=True,
            )
            handler.suffix = "%Y-%m-%d"
            handler.setFormatter(logging.Formatter("%(message)s"))  # Raw JSON
            self._logger.addHandler(handler)

    def log(self, event_type: str, details: dict | None = None) -> None:
        """Log a dashboard interaction event.

        Args:
            event_type: Event identifier (e.g., "tab_switch", "run_select").
            details: Optional dict with event-specific data.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "event_type": event_type,
            "details": details or {},
        }
        self._logger.info(json.dumps(entry, default=str))

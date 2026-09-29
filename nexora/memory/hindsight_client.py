"""Hindsight persistent memory integration for Nexora AI.

Wraps the official hindsight-client library to provide durable retention,
multi-strategy recall, and reflection operations over website audit history.
Includes robust error handling and offline snapshot fallback.
"""

import os
import json
import logging
import datetime as dt
from typing import Dict, List, Any, Optional

try:
    from hindsight_client import Hindsight
    HINDSIGHT_INSTALLED = True
except ImportError:
    Hindsight = None
    HINDSIGHT_INSTALLED = False

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

logger = logging.getLogger("nexora.memory")


class HindsightMemoryClient:
    """Production client for Hindsight persistent agent memory."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        storage_dir: Optional[str] = None,
    ):
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        dotenv_path = os.path.join(repo_root, ".env")
        if load_dotenv:
            load_dotenv(dotenv_path=dotenv_path, override=False)
        elif os.path.isfile(dotenv_path):
            logger.warning(".env exists but python-dotenv is not installed; Hindsight settings were not loaded.")

        self.base_url = base_url or os.getenv("HINDSIGHT_BASE_URL", "http://localhost:8888")
        self.api_key = api_key or os.getenv("HINDSIGHT_API_KEY", None)
        self.storage_dir = storage_dir or os.path.join(os.getcwd(), ".nexora")
        os.makedirs(self.storage_dir, exist_ok=True)
        os.makedirs(os.path.join(self.storage_dir, "snapshots"), exist_ok=True)
        os.makedirs(os.path.join(self.storage_dir, "events"), exist_ok=True)

        self._client: Optional[Any] = None
        self._is_available: bool = False
        self._init_client()

    def _init_client(self):
        """Attempt to instantiate the official Hindsight client and test connectivity."""
        if not HINDSIGHT_INSTALLED:
            logger.warning("hindsight-client is not installed; operating in local snapshot mode.")
            self._is_available = False
            return

        timeout_val = float(os.getenv("HINDSIGHT_TIMEOUT", "1.0"))
        try:
            self._client = Hindsight(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=timeout_val,
            )
            # Lightweight health/version check to verify connectivity
            # If server is unreachable, this will throw an error immediately caught below
            try:
                ver = self._client.get_version()
                self._is_available = True
                logger.info("Connected to Hindsight server at %s (version: %s)", self.base_url, ver)
            except Exception as e:
                self._is_available = False
                self.close()
                key_status = "set" if self.api_key else "unset"
                logger.warning(
                    "Hindsight health check failed at %s (%s; HINDSIGHT_API_KEY is %s); "
                    "local snapshot mode active.",
                    self.base_url,
                    type(e).__name__,
                    key_status,
                )
        except Exception as e:
            logger.debug("Failed initializing Hindsight client: %s; using local snapshots.", e)
            self._is_available = False

    @property
    def is_live(self) -> bool:
        """Returns True if connected to an active Hindsight instance."""
        return self._is_available and self._client is not None

    def close(self):
        """Close client sessions cleanly."""
        if self._client and hasattr(self._client, "close"):
            try:
                self._client.close()
            except Exception:
                pass

    def retain(
        self,
        bank_id: str,
        content: str,
        metadata: Optional[Dict[str, str]] = None,
        tags: Optional[List[str]] = None,
        timestamp: Optional[dt.datetime] = None,
    ) -> bool:
        """Store durable knowledge into Hindsight memory bank."""
        if not self.is_live:
            logger.debug("Hindsight offline: skipped live retain for bank %s", bank_id)
            return False

        try:
            self._client.retain(
                bank_id=bank_id,
                content=content,
                metadata=metadata or {},
                tags=tags or [],
                timestamp=timestamp or dt.datetime.now(dt.timezone.utc),
            )
            logger.info("Retained durable knowledge into Hindsight bank '%s'", bank_id)
            return True
        except Exception as e:
            logger.warning("Hindsight retain error for bank '%s': %s", bank_id, e)
            return False

    def recall(
        self,
        bank_id: str,
        query: str,
        tags: Optional[List[str]] = None,
        max_tokens: int = 4096,
    ) -> List[Dict[str, Any]]:
        """Retrieve memories relevant to the query from Hindsight."""
        if not self.is_live:
            return []

        try:
            resp = self._client.recall(
                bank_id=bank_id,
                query=query,
                tags=tags,
                max_tokens=max_tokens,
            )
            results = []
            if hasattr(resp, "results") and resp.results:
                for r in resp.results:
                    results.append({
                        "id": getattr(r, "id", ""),
                        "text": getattr(r, "text", ""),
                        "type": getattr(r, "type", ""),
                        "metadata": getattr(r, "metadata", {}) or {},
                        "tags": getattr(r, "tags", []) or [],
                        "scores": getattr(r, "scores", {}) or {},
                    })
            return results
        except Exception as e:
            logger.warning("Hindsight recall error for bank '%s': %s", bank_id, e)
            return []

    def reflect(
        self,
        bank_id: str,
        query: str,
    ) -> Optional[str]:
        """Perform higher-level synthesis and reasoning over stored memories."""
        if not self.is_live:
            return None

        try:
            resp = self._client.reflect(
                bank_id=bank_id,
                query=query,
            )
            if hasattr(resp, "text") and resp.text:
                return resp.text
            return str(resp)
        except Exception as e:
            logger.warning("Hindsight reflect error for bank '%s': %s", bank_id, e)
            return None

    # ---------------------------------------------------------
    # Local Structured Snapshot Fallback & Offline Cache
    # ---------------------------------------------------------

    def save_local_snapshot(self, bank_id: str, snapshot_data: Dict[str, Any]) -> str:
        """Persist structured audit snapshot to local durable cache."""
        bank_dir = os.path.join(self.storage_dir, "snapshots", bank_id)
        os.makedirs(bank_dir, exist_ok=True)
        filename = f"{snapshot_data.get('snapshot_id', 'snapshot')}.json"
        path = os.path.join(bank_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, indent=2)
        return path

    def load_local_snapshots(self, bank_id: str) -> List[Dict[str, Any]]:
        """Load all previous historical snapshots for a bank, sorted chronologically."""
        bank_dir = os.path.join(self.storage_dir, "snapshots", bank_id)
        if not os.path.isdir(bank_dir):
            return []

        snapshots = []
        for fname in sorted(os.listdir(bank_dir)):
            if fname.endswith(".json"):
                fpath = os.path.join(bank_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        snapshots.append(data)
                except Exception as e:
                    logger.warning("Error reading snapshot %s: %s", fpath, e)

        # Sort by audited_at timestamp
        snapshots.sort(key=lambda s: s.get("audited_at", ""))
        return snapshots

    def save_local_event(self, bank_id: str, event_data: Dict[str, Any]) -> str:
        """Save user implementation or verification event to local durable cache."""
        event_dir = os.path.join(self.storage_dir, "events", bank_id)
        os.makedirs(event_dir, exist_ok=True)
        event_id = event_data.get("event_id") or f"ev_{int(dt.datetime.now().timestamp())}"
        path = os.path.join(event_dir, f"{event_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(event_data, f, indent=2)
        return path

    def load_local_events(self, bank_id: str) -> List[Dict[str, Any]]:
        """Load recorded implementation events for a bank."""
        event_dir = os.path.join(self.storage_dir, "events", bank_id)
        if not os.path.isdir(event_dir):
            return []

        events = []
        for fname in sorted(os.listdir(event_dir)):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(event_dir, fname), "r", encoding="utf-8") as f:
                        events.append(json.load(f))
                except Exception:
                    pass
        events.sort(key=lambda e: e.get("recorded_at", ""))
        return events

    def clear_bank(self, bank_id: str) -> None:
        """Utility to reset history for a bank (for testing/demo resets)."""
        import shutil
        snap_dir = os.path.join(self.storage_dir, "snapshots", bank_id)
        if os.path.isdir(snap_dir):
            shutil.rmtree(snap_dir, ignore_errors=True)
        event_dir = os.path.join(self.storage_dir, "events", bank_id)
        if os.path.isdir(event_dir):
            shutil.rmtree(event_dir, ignore_errors=True)

"""
Blockchain Adapter for Qumanity
Currently stubbed - will be implemented in Phase 2/3
This allows the app to be blockchain-ready without actual blockchain yet
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime


class BlockchainAdapter:
    """Adapter pattern - currently returns mock data."""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.chain_type = "polygon"  # Future: polygon, ethereum, or e-rupee

    def hash_data(self, data) -> str:
        """Generate SHA-256 hash of any data (for future blockchain recording)."""
        if isinstance(data, dict):
            data = json.dumps(data, sort_keys=True)
        elif not isinstance(data, str):
            data = str(data)
        return hashlib.sha256(data.encode()).hexdigest()

    def record_registration(self, user_id: str, public_id: str, timestamp: str) -> dict:
        """Stub: Record user registration on blockchain."""
        if not self.enabled:
            return {
                "status": "stub",
                "hash": self.hash_data(f"{user_id}{public_id}{timestamp}"),
            }
        return {"status": "pending"}

    def record_vote(
        self, user_id: str, proposal_id: str, vote_choice: str, timestamp: str
    ) -> dict:
        """Stub: Record vote on blockchain."""
        if not self.enabled:
            return {
                "status": "stub",
                "hash": self.hash_data(f"{user_id}{proposal_id}{vote_choice}{timestamp}"),
            }
        return {"status": "pending"}

    def record_transaction(
        self, from_user: str, to_user: str, amount: int, purpose: str
    ) -> dict:
        """Stub: Record Karma Points transaction on blockchain."""
        if not self.enabled:
            return {
                "status": "stub",
                "hash": self.hash_data(f"{from_user}{to_user}{amount}{purpose}"),
            }
        return {"status": "pending"}

    def record_post(
        self, user_id: str, post_content: str, post_id: int, timestamp: str
    ) -> dict:
        """Stub: Record post hash on blockchain for timestamp proof."""
        if not self.enabled:
            content_hash = self.hash_data(post_content)
            return {"status": "stub", "content_hash": content_hash}
        return {"status": "pending"}

    def verify_audit_trail(self, table_name: str, record_id: int) -> dict:
        """Stub: Verify if record matches blockchain record."""
        if not self.enabled:
            return {
                "verified": True,
                "message": "Blockchain not enabled - trust database",
            }
        return {"verified": False, "message": "Not implemented"}

    def get_sync_status(self) -> dict:
        """Return sync status of blockchain adapter."""
        return {
            "enabled": self.enabled,
            "chain": self.chain_type,
            "last_sync": datetime.now().isoformat(),
            "ready_for_phase2": True,
        }


# Singleton instance
blockchain = BlockchainAdapter(enabled=False)

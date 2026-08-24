"""
SPATHODEA R4 FASTLAB — Exact Duplicate Detector
Detects exact and near-exact duplicates using normalized hashing.
"""

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Optional


class Deduplicator:
    """Exact duplicate detector using SHA-256 hashing of normalized content.
    
    Normalization pipeline (before hashing):
    1. Unicode NFC normalization
    2. Lowercase
    3. Strip leading/trailing whitespace
    4. Collapse multiple spaces to single space
    
    Phase 2 will add semantic deduplication via embeddings.
    """

    def __init__(self, config: Optional[dict] = None):
        cfg = config or {}
        self.normalize = cfg.get("normalize", True)
        self.fields = cfg.get("fields", ["input", "output"])
        self._seen_hashes: dict[str, str] = {}  # hash -> first record_id

    def reset(self):
        """Clear the deduplication index."""
        self._seen_hashes.clear()

    @property
    def index_size(self) -> int:
        """Number of unique hashes in the index."""
        return len(self._seen_hashes)

    def _normalize_text(self, text: str) -> str:
        """Apply normalization pipeline to text."""
        if not self.normalize:
            return text
        # Unicode NFC
        text = unicodedata.normalize("NFC", text)
        # Lowercase
        text = text.lower()
        # Strip
        text = text.strip()
        # Collapse spaces
        text = " ".join(text.split())
        return text

    def _compute_hash(self, record: dict) -> str:
        """Compute SHA-256 hash of normalized content fields."""
        parts = []
        for field in self.fields:
            value = record.get(field, "")
            if isinstance(value, str):
                parts.append(self._normalize_text(value))
            else:
                parts.append("")
        combined = "\x00".join(parts)  # Null byte separator
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def is_duplicate(self, record: dict) -> tuple[bool, Optional[str]]:
        """Check if a record is a duplicate of one already seen.
        
        Args:
            record: Internal master record dict
            
        Returns:
            Tuple of (is_duplicate: bool, duplicate_of: record_id or None)
        """
        h = self._compute_hash(record)
        if h in self._seen_hashes:
            return True, self._seen_hashes[h]
        # Register this record
        record_id = record.get("id", "unknown")
        self._seen_hashes[h] = record_id
        return False, None

    def check_without_registering(self, record: dict) -> tuple[bool, Optional[str]]:
        """Check for duplicate without adding to the index.
        
        Useful for preview/dry-run operations.
        """
        h = self._compute_hash(record)
        if h in self._seen_hashes:
            return True, self._seen_hashes[h]
        return False, None

    def deduplicate_records(self, records: list[dict]) -> dict:
        """Deduplicate a list of records.
        
        Args:
            records: List of internal master records
            
        Returns:
            Dict with:
                unique: list of unique records
                duplicates: list of (record, duplicate_of_id) tuples
                stats: {total, unique, duplicates}
        """
        self.reset()
        unique = []
        duplicates = []

        for record in records:
            is_dup, dup_of = self.is_duplicate(record)
            if is_dup:
                duplicates.append({"record": record, "duplicate_of": dup_of})
            else:
                unique.append(record)

        return {
            "unique": unique,
            "duplicates": duplicates,
            "stats": {
                "total": len(records),
                "unique": len(unique),
                "duplicates": len(duplicates),
                "duplicate_rate": len(duplicates) / max(len(records), 1),
            },
        }

    def deduplicate_file(self, filepath: str) -> dict:
        """Deduplicate records from a JSONL file.
        
        Args:
            filepath: Path to JSONL file
            
        Returns:
            Same structure as deduplicate_records()
        """
        path = Path(filepath)
        if not path.exists():
            return {
                "unique": [],
                "duplicates": [],
                "stats": {"total": 0, "unique": 0, "duplicates": 0, "duplicate_rate": 0.0},
            }

        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return self.deduplicate_records(records)

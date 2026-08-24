"""
SPATHODEA R4 FASTLAB — Dataset Splitter
Splits records into train/validation/test sets with stratification.
"""

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Optional


class Splitter:
    """Stratified dataset splitter with deterministic reproducibility.
    
    Features:
    - Configurable train/validation/test ratios
    - Stratification by language, difficulty, intent
    - Deterministic shuffling with seed
    - Isolation guarantee (no record appears in multiple splits)
    """

    def __init__(self, config: Optional[dict] = None):
        cfg = config or {}
        self.train_ratio = cfg.get("train_ratio", 0.80)
        self.validation_ratio = cfg.get("validation_ratio", 0.10)
        self.test_ratio = cfg.get("test_ratio", 0.10)
        self.seed = cfg.get("seed", 42)
        self.shuffle = cfg.get("shuffle", True)
        self.stratify_by = cfg.get("stratify_by", ["language", "difficulty"])

        # Validate ratios sum to 1.0
        total = self.train_ratio + self.validation_ratio + self.test_ratio
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Split ratios must sum to 1.0, got {total}")

    def _get_stratum_key(self, record: dict) -> str:
        """Build a stratification key from metadata fields."""
        meta = record.get("metadata", {})
        parts = []
        for field in self.stratify_by:
            parts.append(str(meta.get(field, "unknown")))
        return "|".join(parts)

    def split_records(self, records: list[dict]) -> dict:
        """Split records into train/validation/test with stratification.
        
        Args:
            records: List of internal master records
            
        Returns:
            Dict with:
                train: list of records
                validation: list of records
                test: list of records
                stats: split statistics
        """
        if not records:
            return {
                "train": [], "validation": [], "test": [],
                "stats": {"total": 0, "train": 0, "validation": 0, "test": 0},
            }

        # Group by stratum
        strata: dict[str, list[dict]] = defaultdict(list)
        for record in records:
            key = self._get_stratum_key(record)
            strata[key].append(record)

        train = []
        validation = []
        test = []
        rng = random.Random(self.seed)

        # Split each stratum proportionally
        for _key, stratum_records in sorted(strata.items()):
            if self.shuffle:
                rng.shuffle(stratum_records)

            n = len(stratum_records)
            n_train = max(1, round(n * self.train_ratio)) if n >= 3 else n
            n_val = round(n * self.validation_ratio) if n >= 3 else 0
            # Remainder goes to test
            n_test = n - n_train - n_val

            # Ensure non-negative
            if n_test < 0:
                n_val = n - n_train
                n_test = 0

            train.extend(stratum_records[:n_train])
            validation.extend(stratum_records[n_train:n_train + n_val])
            test.extend(stratum_records[n_train + n_val:])

        # Final shuffle within each split
        if self.shuffle:
            rng.shuffle(train)
            rng.shuffle(validation)
            rng.shuffle(test)

        return {
            "train": train,
            "validation": validation,
            "test": test,
            "stats": {
                "total": len(records),
                "train": len(train),
                "validation": len(validation),
                "test": len(test),
                "strata_count": len(strata),
            },
        }

    def split_and_save(
        self,
        records: list[dict],
        output_dir: str = "datasets",
    ) -> dict:
        """Split records and save to JSONL files.
        
        Args:
            records: List of internal master records
            output_dir: Base directory for split output
            
        Returns:
            Dict with split stats and file paths
        """
        result = self.split_records(records)
        output = Path(output_dir)

        paths = {}
        for split_name in ("train", "validation", "test"):
            split_dir = output / split_name
            split_dir.mkdir(parents=True, exist_ok=True)
            filepath = split_dir / "data.jsonl"

            with open(filepath, "w", encoding="utf-8") as f:
                for record in result[split_name]:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

            paths[split_name] = str(filepath)

        return {
            "stats": result["stats"],
            "paths": paths,
        }

    def split_file(self, filepath: str, output_dir: str = "datasets") -> dict:
        """Load records from a JSONL file, split, and save.
        
        Args:
            filepath: Path to input JSONL file
            output_dir: Base directory for split output
            
        Returns:
            Dict with split stats and file paths
        """
        path = Path(filepath)
        if not path.exists():
            return {"error": f"File not found: {filepath}"}

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

        return self.split_and_save(records, output_dir)

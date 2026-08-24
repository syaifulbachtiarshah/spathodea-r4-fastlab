"""
SPATHODEA R4 FASTLAB — Synthetic Data Generator
Orchestrates LLM-powered data generation (Phase 2).

Phase 1: Stub implementation with manual record creation only.
Phase 2: Will use OpenAI/Gemini adapters for batch generation.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class Generator:
    """Synthetic training data generator.
    
    Phase 1: Creates records manually or from templates.
    Phase 2: Will use LLM providers for large-scale generation.
    """

    def __init__(self, config: Optional[dict] = None):
        self._config = config or {}
        self._batch_counter = 0

    @staticmethod
    def create_record(
        input_text: str,
        output_text: str,
        intent: str,
        difficulty: str = "medium",
        language: str = "en",
        system_prompt: Optional[str] = None,
        persona: Optional[str] = None,
        noise_type: Optional[str] = None,
        generator: str = "manual",
        tags: Optional[list[str]] = None,
    ) -> dict:
        """Create a single internal master record.
        
        Args:
            input_text: User input / query
            output_text: Expected model response
            intent: Task intent category
            difficulty: One of easy/medium/hard/adversarial/noisy
            language: One of en/ms/mixed
            system_prompt: Optional system instruction
            persona: Optional user persona
            noise_type: Optional noise classification
            generator: Source identifier
            tags: Optional freeform tags
            
        Returns:
            Complete internal master record dict
        """
        return {
            "id": f"r4-{uuid.uuid4()}",
            "input": input_text,
            "output": output_text,
            "system_prompt": system_prompt,
            "metadata": {
                "intent": intent,
                "difficulty": difficulty,
                "language": language,
                "persona": persona,
                "noise_type": noise_type,
                "generator": generator,
                "generation_batch": None,
                "seed_id": None,
                "quality_score": None,
                "quality_dimensions": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "tags": tags or [],
            },
        }

    def save_records(self, records: list[dict], output_path: str) -> dict:
        """Save records to a JSONL file.
        
        Args:
            records: List of internal master records
            output_path: Path to output JSONL file
            
        Returns:
            Dict with save stats
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return {
            "records_saved": len(records),
            "output_path": str(path),
        }

    def load_records(self, filepath: str) -> list[dict]:
        """Load records from a JSONL file.
        
        Args:
            filepath: Path to JSONL file
            
        Returns:
            List of record dicts
        """
        path = Path(filepath)
        if not path.exists():
            return []

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
        return records

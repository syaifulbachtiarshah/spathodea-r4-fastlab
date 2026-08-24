"""
SPATHODEA R4 FASTLAB — AWS Format Adapter
Converts internal master records to AWS SageMaker-compatible export formats.

Supports:
- Standard format: {"prompt": "...", "completion": "..."}
- Conversational format: {"messages": [{"role": "...", "content": "..."}]}
"""

import json
from pathlib import Path
from typing import Optional


class AWSFormatAdapter:
    """Converts internal master records to AWS SageMaker SFT formats.
    
    Internal Format → AWS Standard (prompt/completion)
    Internal Format → AWS Conversational (messages)
    """

    SUPPORTED_FORMATS = ["prompt-completion", "messages"]

    def to_prompt_completion(self, record: dict) -> dict:
        """Convert internal record to AWS Standard format.
        
        Args:
            record: Internal master record dict
            
        Returns:
            Dict with 'prompt', 'completion', and optional 'system' fields
        """
        result = {
            "prompt": record["input"],
            "completion": record["output"],
        }
        if record.get("system_prompt"):
            result["system"] = record["system_prompt"]
        return result

    def to_messages(self, record: dict) -> dict:
        """Convert internal record to AWS Conversational format.
        
        Args:
            record: Internal master record dict
            
        Returns:
            Dict with 'messages' array containing role/content objects
        """
        messages = []
        if record.get("system_prompt"):
            messages.append({
                "role": "system",
                "content": record["system_prompt"],
            })
        messages.append({
            "role": "user",
            "content": record["input"],
        })
        messages.append({
            "role": "assistant",
            "content": record["output"],
        })
        return {"messages": messages}

    def convert_record(self, record: dict, fmt: str) -> dict:
        """Convert a single record to the specified format.
        
        Args:
            record: Internal master record
            fmt: Target format ('prompt-completion' or 'messages')
            
        Returns:
            Converted record dict
            
        Raises:
            ValueError: If format is not supported
        """
        if fmt == "prompt-completion":
            return self.to_prompt_completion(record)
        elif fmt == "messages":
            return self.to_messages(record)
        else:
            raise ValueError(
                f"Unsupported format: '{fmt}'. "
                f"Supported: {self.SUPPORTED_FORMATS}"
            )

    def export_jsonl(
        self,
        records: list[dict],
        output_path: str,
        fmt: str,
    ) -> dict:
        """Export records to a JSONL file in the specified AWS format.
        
        Args:
            records: List of internal master records
            output_path: Path to write the JSONL file
            fmt: Target format ('prompt-completion' or 'messages')
            
        Returns:
            Dict with export stats: {total, exported, errors, output_path}
        """
        if fmt not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format: '{fmt}'. "
                f"Supported: {self.SUPPORTED_FORMATS}"
            )

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        exported = 0
        errors = 0

        with open(output, "w", encoding="utf-8") as f:
            for record in records:
                try:
                    converted = self.convert_record(record, fmt)
                    f.write(json.dumps(converted, ensure_ascii=False) + "\n")
                    exported += 1
                except (KeyError, ValueError) as e:
                    errors += 1

        return {
            "total": len(records),
            "exported": exported,
            "errors": errors,
            "output_path": str(output),
            "format": fmt,
        }

    def validate_export(self, filepath: str, fmt: str) -> dict:
        """Validate an exported JSONL file against the target format schema.
        
        Args:
            filepath: Path to the exported JSONL file
            fmt: Expected format
            
        Returns:
            Dict with validation results: {valid, invalid, errors}
        """
        path = Path(filepath)
        if not path.exists():
            return {"valid": 0, "invalid": 0, "errors": ["File not found"]}

        valid = 0
        invalid = 0
        errors = []

        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if fmt == "prompt-completion":
                        if "prompt" not in obj or "completion" not in obj:
                            invalid += 1
                            errors.append(
                                f"Line {line_num}: missing prompt/completion"
                            )
                        else:
                            valid += 1
                    elif fmt == "messages":
                        if "messages" not in obj or not isinstance(obj["messages"], list):
                            invalid += 1
                            errors.append(
                                f"Line {line_num}: missing/invalid messages"
                            )
                        elif len(obj["messages"]) < 2:
                            invalid += 1
                            errors.append(
                                f"Line {line_num}: messages needs >= 2 entries"
                            )
                        else:
                            valid += 1
                except json.JSONDecodeError as e:
                    invalid += 1
                    errors.append(f"Line {line_num}: invalid JSON: {e}")

        return {"valid": valid, "invalid": invalid, "errors": errors[:20]}

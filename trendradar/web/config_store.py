# coding=utf-8
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from ruamel.yaml import YAML


YamlData = Any


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 120
    return y


def _to_plain(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain(v) for v in obj]
    return obj


def deep_merge_inplace(target: Any, patch: Any) -> Any:
    if patch is None:
        return target

    if isinstance(target, dict) and isinstance(patch, dict):
        for k, v in patch.items():
            if k in target and isinstance(target[k], dict) and isinstance(v, dict):
                deep_merge_inplace(target[k], v)
            else:
                target[k] = v
        return target

    # 非 dict：直接替换
    return patch


@dataclass
class ConfigStore:
    config_path: Path
    frequency_words_path: Path
    default_config_candidates: Tuple[Path, ...]
    default_words_candidates: Tuple[Path, ...]

    def read_config_text(self) -> str:
        if not self.config_path.exists():
            return ""
        return self.config_path.read_text(encoding="utf-8")

    def read_words_text(self) -> str:
        if not self.frequency_words_path.exists():
            return ""
        return self.frequency_words_path.read_text(encoding="utf-8")

    def _read_default_text(self, candidates: Tuple[Path, ...]) -> Optional[str]:
        for p in candidates:
            if p.exists():
                return p.read_text(encoding="utf-8")
        return None

    def read_default_config_text(self) -> Optional[str]:
        return self._read_default_text(self.default_config_candidates)

    def read_default_words_text(self) -> Optional[str]:
        return self._read_default_text(self.default_words_candidates)

    def load_config_yaml(self) -> YamlData:
        y = _yaml()
        text = self.read_config_text()
        if not text:
            text = self.read_default_config_text() or ""
        if not text:
            return {}
        return y.load(text)

    def dump_yaml(self, data: YamlData) -> str:
        y = _yaml()
        buf = io.StringIO()
        y.dump(data, buf)
        return buf.getvalue()

    def write_with_backup(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = path.with_suffix(path.suffix + f".bak.{ts}")
            backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        path.write_text(content, encoding="utf-8")

    def patch_config(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        data = self.load_config_yaml()
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("Config YAML root must be a mapping")

        deep_merge_inplace(data, patch)
        content = self.dump_yaml(data)
        self.write_with_backup(self.config_path, content)
        return {"path": str(self.config_path)}

    def reset_config_to_default(self) -> Dict[str, Any]:
        default_text = self.read_default_config_text()
        if not default_text:
            raise FileNotFoundError("Default config template not found")
        # validate YAML
        y = _yaml()
        parsed = y.load(default_text)
        if parsed is None or not isinstance(parsed, dict):
            raise ValueError("Default config is invalid")
        self.write_with_backup(self.config_path, default_text)
        return {"path": str(self.config_path)}

    def reset_words_to_default(self) -> Dict[str, Any]:
        default_text = self.read_default_words_text()
        if default_text is None:
            raise FileNotFoundError("Default frequency_words template not found")
        self.write_with_backup(self.frequency_words_path, default_text)
        return {"path": str(self.frequency_words_path)}

    def get_config_plain(self) -> Dict[str, Any]:
        data = self.load_config_yaml()
        if data is None:
            return {}
        if not isinstance(data, dict):
            return {}
        return _to_plain(data)


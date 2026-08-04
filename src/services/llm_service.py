from __future__ import annotations

import os
from pathlib import Path

import yaml
from openai import OpenAI


class LLMConfigurationError(RuntimeError):
    """Raised when an LLM call is attempted without a usable configuration."""


class LLMService:
    def __init__(self, config_path: str | Path | None = None):
        configured_path = config_path or os.getenv("DEEPMEMO_LLM_CONFIG", "config/llm_api.yaml")
        path = Path(configured_path).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path

        self.config_file = path
        self.provider: dict | None = None
        self.client: OpenAI | None = None
        self.model = ""
        self.max_tokens = 1000
        self.temperature = 0.7

    def _resolve_provider(self, cfg: dict) -> dict:
        if "llm" in cfg and isinstance(cfg["llm"], dict):
            llm_cfg = cfg["llm"]
            use = llm_cfg.get("use")
            if not use:
                raise LLMConfigurationError(f"{self.config_file} 中 llm.use 未配置")
            provider = llm_cfg.get(use)
            if not isinstance(provider, dict):
                raise LLMConfigurationError(f"{self.config_file} 中未找到 llm.{use} 配置")
            return provider

        # 兼容旧格式：顶层第一项就是 provider
        provider_name = list(cfg.keys())[0]
        provider = cfg[provider_name]
        if not isinstance(provider, dict):
            raise LLMConfigurationError(f"{self.config_file} 中 provider 配置必须是对象")
        return provider

    def _ensure_configured(self) -> None:
        if self.client is not None:
            return

        if not self.config_file.is_file():
            raise LLMConfigurationError(
                f"LLM 未配置：请创建 {self.config_file}，或通过 DEEPMEMO_LLM_CONFIG 指定配置文件"
            )

        try:
            with self.config_file.open(encoding="utf-8") as handle:
                cfg = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise LLMConfigurationError(f"无法解析 LLM 配置 {self.config_file}: {exc}") from exc

        if not isinstance(cfg, dict) or not cfg:
            raise LLMConfigurationError(f"LLM 配置为空或格式无效：{self.config_file}")

        provider = self._resolve_provider(cfg)
        required_fields = ("api_key", "api_base", "model")
        missing_fields = [field for field in required_fields if not provider.get(field)]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise LLMConfigurationError(f"LLM 配置缺少必填字段 ({missing})：{self.config_file}")

        self.provider = provider
        self.client = OpenAI(
            api_key=provider["api_key"],
            base_url=provider["api_base"],
        )
        self.model = provider["model"]
        self.max_tokens = provider.get("max_tokens", 1000)
        self.temperature = provider.get("temperature", 0.7)

    def chat(self, messages: list[dict], stream: bool = False):
        self._ensure_configured()
        assert self.client is not None

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=stream,
        )
        if stream:
            return self._iter_stream_content(response)
        return response

    def _iter_stream_content(self, response):
        for chunk in response:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue

            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None)
            if content:
                yield content


llm_service = LLMService()

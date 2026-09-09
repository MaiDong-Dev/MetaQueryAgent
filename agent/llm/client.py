"""M3 LLM 客户端：调用 DeepSeek（OpenAI 兼容接口）并解析为 pydantic 模型

封装：调用 + JSON 提取 + pydantic 校验 + 重试 + 兜底。
"""

import json
import os

import httpx
from pydantic import ValidationError

from agent.llm.schema import TableEnrich
from agent.llm.prompt import SYSTEM_PROMPT, build_user_prompt


class LlmClient:
    """DeepSeek / OpenAI 兼容的 LLM 客户端"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        max_retries: int = 3,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = self._resolve_api_key(api_key)
        self.model = model
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self):
        await self._client.aclose()

    async def enrich_table(self, table) -> TableEnrich:
        """对单表做业务补全，失败兜底返回空 TableEnrich（不中断整批）"""
        user_prompt = build_user_prompt(table)
        for attempt in range(self.max_retries):
            try:
                raw = await self._call(user_prompt)
                data = json.loads(self._extract_json(raw))
                return TableEnrich.model_validate(data)
            except (json.JSONDecodeError, ValidationError, httpx.HTTPError, KeyError, IndexError):
                if attempt == self.max_retries - 1:
                    # 兜底：返回空结构，不中断整批采集
                    return TableEnrich()
        return TableEnrich()

    async def _call(self, user_prompt: str) -> str:
        resp = await self._client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    @staticmethod
    def _extract_json(text: str) -> str:
        """剥离 markdown 代码块等杂质，取出纯 JSON 文本"""
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
        return text

    @staticmethod
    def _resolve_api_key(api_key: str) -> str:
        """若配置值是环境变量名（非 sk- 开头），尝试从环境变量读取"""
        if api_key and not api_key.startswith("sk-"):
            env_val = os.environ.get(api_key)
            if env_val:
                return env_val
        return api_key

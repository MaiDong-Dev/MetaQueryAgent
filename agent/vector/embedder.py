"""向量化客户端：调用远程 Embedding 服务（HTTP）

配置驱动，单例 embedding_client。
Embedding 服务由 docker 部署（见 docker-compose.yml 的 embedding 服务）。
"""

import httpx

from config.client_conf import schema_conf, EmbeddingConf


class EmbeddingClient:
    """Embedding 服务客户端（配置驱动，单例）"""

    def __init__(self, embedding_conf: EmbeddingConf | None = None):
        self.conf = embedding_conf or schema_conf.embedding
        self.base_url = f"http://{self.conf.host}:{self.conf.port}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        """把文本列表编码为归一化向量"""
        resp = httpx.post(
            f"{self.base_url}/embed",
            json={"texts": texts},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]

    def health(self) -> bool:
        """健康检查"""
        try:
            resp = httpx.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False


# 全局单例，供各模块直接复用
embedding_client = EmbeddingClient()

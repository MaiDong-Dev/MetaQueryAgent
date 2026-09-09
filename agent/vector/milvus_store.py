"""M5 Milvus 客户端：字段语义向量 -> 业务域相似度检索

配置驱动（从 config.schema_conf.milvus 读取），惰性加载 pymilvus。
使用 MilvusClient（pymilvus 3.x 推荐 API），避免 ORM 风格弃用警告。
用途：在 LLM 补全业务域前，检索历史已确认字段的最相似业务域作为候选。
"""

from config.client_conf import schema_conf, MilvusConf
from agent.vector.embedder import EmbeddingClient, embedding_client


class MilvusStore:
    """Milvus 客户端（规范化封装，单例 milvus_store）"""

    def __init__(self, milvus_conf: MilvusConf | None = None, embedder=None):
        self.conf = milvus_conf or schema_conf.milvus
        self.embedder = embedder or embedding_client
        self._client = None

    @property
    def collection_name(self) -> str:
        return self.conf.collection

    @property
    def uri(self) -> str:
        return f"http://{self.conf.host}:{self.conf.port}"

    def _get_client(self):
        """惰性创建 MilvusClient（线程安全，可复用单例）"""
        if self._client is None:
            from pymilvus import MilvusClient

            self._client = MilvusClient(uri=self.uri)
        return self._client

    def init_collection(self):
        """创建 collection（如不存在）并建向量索引"""
        client = self._get_client()
        if client.has_collection(self.collection_name):
            client.load_collection(self.collection_name)  # 已存在也确保加载到内存
            return

        from pymilvus import DataType

        schema = client.create_schema(auto_id=True, enable_dynamic_field=False)
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
        schema.add_field(field_name="column_text", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="business_domain", datatype=DataType.VARCHAR, max_length=64)
        schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=self.conf.dim)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="IVF_FLAT",
            metric_type="IP",
            params={"nlist": 128},
        )

        client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )
        client.load_collection(self.collection_name)  # 加载到内存

    def upsert(self, texts: list[str], domains: list[str]):
        """写入字段向量及其业务域（人工确认后调用，反哺向量库）"""
        client = self._get_client()
        vectors = self.embedder.embed(texts)
        data = [
            {"column_text": text, "business_domain": domain, "embedding": vector}
            for text, domain, vector in zip(texts, domains, vectors)
        ]
        client.insert(collection_name=self.collection_name, data=data)
        client.flush(self.collection_name)  # 刷到 sealed segment，否则 row_count 统计不到

    def search_domain(self, text: str, top_k: int = 3) -> list[str]:
        """检索最相似字段的业务域候选"""
        client = self._get_client()
        vector = self.embedder.embed([text])[0]
        res = client.search(
            collection_name=self.collection_name,
            data=[vector],
            limit=top_k,
            output_fields=["business_domain"],
        )
        return [hit["entity"]["business_domain"] for hit in res[0]]


# 全局单例，供各模块直接复用
milvus_store = MilvusStore()

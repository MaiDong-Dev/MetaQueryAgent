"""查询 Milvus 向量数据：统计数量 + 查看前几条（pymilvus 3.0 MilvusClient）"""

from pymilvus import MilvusClient

from config.client_conf import schema_conf


def main():
    conf = schema_conf.milvus
    client = MilvusClient(uri=f"http://{conf.host}:{conf.port}")

    # 1. 统计 collection 数据量
    stats = client.get_collection_stats(conf.collection)
    row_count = stats.get("row_count", 0)
    print(f"collection: {conf.collection}")
    print(f"实体数量: {row_count}")

    # 2. 查看前几条
    if row_count > 0:
        results = client.query(
            collection_name=conf.collection,
            filter="id >= 0",
            output_fields=["column_text", "business_domain"],
            limit=10,
        )
        print(f"\n前 {len(results)} 条数据:")
        for r in results:
            print(f"  {r.get('column_text')} -> {r.get('business_domain')}")


if __name__ == "__main__":
    main()

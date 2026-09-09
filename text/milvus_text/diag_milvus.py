"""诊断 MilvusClient 的真实返回：版本 / collection 状态 / stats / query"""
import pymilvus
from pymilvus import MilvusClient

from config.client_conf import schema_conf


def main():
    conf = schema_conf.milvus
    print(f"pymilvus 版本: {pymilvus.__version__}")
    print(f"uri: http://{conf.host}:{conf.port}  collection: {conf.collection}")

    client = MilvusClient(uri=f"http://{conf.host}:{conf.port}")

    print(f"\nhas_collection: {client.has_collection(conf.collection)}")

    print(f"\nload_collection 返回: {client.load_collection(conf.collection)}")

    stats = client.get_collection_stats(conf.collection)
    print(f"\nflush 前 get_collection_stats 返回: {stats}")

    # 关键：flush growing segment -> sealed，让 row_count 统计到
    flush_ret = client.flush(conf.collection)
    print(f"flush 返回: {flush_ret}")

    stats2 = client.get_collection_stats(conf.collection)
    print(f"flush 后 get_collection_stats 返回: {stats2}")

    results = client.query(
        collection_name=conf.collection,
        filter="id >= 0",
        output_fields=["column_text", "business_domain"],
        limit=3,
    )
    print(f"\nquery 返回条数: {len(results)}")
    for r in results:
        print(f"  {r}")


if __name__ == "__main__":
    main()

"""Milvus 验证：连接 + collection 初始化 + 向量写入检索

依赖：pymilvus（必需）、sentence-transformers（写入/检索时需要）
"""

from agent.vector import milvus_store


def main():
    # 1. 初始化 collection（验证连接 + 建库建索引）
    milvus_store.init_collection()
    print(f"[1] collection '{milvus_store.collection_name}' 初始化成功")

    # 2. 验证向量写入 + 检索（需要 sentence-transformers）
    try:
        milvus_store.upsert(
            texts=["订单表 order 的 phone 用户手机号"],
            domains=["用户域"],
        )
        print("[2] 向量写入成功")

        domains = milvus_store.search_domain("订单表 order 的 mobile 手机号", top_k=3)
        print(f"[3] 检索结果: {domains}")
    except ImportError as e:
        print(f"[跳过] {e}")
        print("  需执行: uv add sentence-transformers")


if __name__ == "__main__":
    main()

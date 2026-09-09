"""Embedding 推理服务

加载本地 bge 模型，提供 /embed 接口（POST texts -> embeddings）。
模型路径通过环境变量 MODEL_PATH 指定。
"""

import os

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

MODEL_PATH = os.environ.get("MODEL_PATH", "/models/bge-large-zh-v1.5")

app = FastAPI(title="Embedding Service")

# 启动时加载模型（只加载一次）
model = SentenceTransformer(MODEL_PATH)


class EmbedRequest(BaseModel):
    texts: list[str]


@app.post("/embed")
def embed(req: EmbedRequest):
    vectors = model.encode(req.texts, normalize_embeddings=True)
    return {"embeddings": vectors.tolist()}


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_PATH}

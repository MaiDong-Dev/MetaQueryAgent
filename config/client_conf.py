from dataclasses import dataclass
from pathlib import Path

from omegaconf import OmegaConf


@dataclass
class MetaDbConf:
    path: str    # SQLite 文件绝对路径


@dataclass
class LlmConf:
    model: str
    api_key: str
    base_url: str


@dataclass
class MilvusConf:
    host: str
    port: int
    dim: int           # embedding 向量维度（与 Embedding 服务输出一致）
    collection: str    # collection 名称


@dataclass
class EmbeddingConf:
    host: str
    port: int
    model: str         # 模型名（仅作元信息，实际由服务端加载）


@dataclass
class Conf:
    meta_db: MetaDbConf
    llm: LlmConf
    milvus: MilvusConf
    embedding: EmbeddingConf


conf_path = Path(__file__).parents[1] / "config_yaml" / "conf.yaml"
project_root = conf_path.parents[1]


def _build_conf() -> Conf:
    """加载 yaml 并构造 dataclass 对象，meta_db.path 转绝对路径"""
    raw = OmegaConf.load(conf_path)
    meta_db_path = Path(raw.meta_db.path)
    if not meta_db_path.is_absolute():
        meta_db_path = project_root / meta_db_path
    return Conf(
        meta_db=MetaDbConf(path=str(meta_db_path)),
        llm=LlmConf(**dict(raw.llm)),
        milvus=MilvusConf(**dict(raw.milvus)),
        embedding=EmbeddingConf(**dict(raw.embedding)),
    )


schema_conf: Conf = _build_conf()

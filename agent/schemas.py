"""请求级数据模型（API 入参等）"""

from pydantic import BaseModel, Field


class DbConnection(BaseModel):
    """数据库连接信息 + 可选的单库标识"""

    host: str = Field(default="wl", description="数据库主机")
    port: int = Field(default=3307, description="端口")
    user: str = Field(default="root", description="用户名")
    password: str = Field(default="123456", description="密码")
    database: str | None = Field(default=None, description="单个库名（用于实例隔离，可选）")

    @property
    def instance_name(self) -> str:
        """实例标识：按库隔离，保证多个库的元数据并存、互不干扰"""
        if self.database:
            return f"{self.host}:{self.port}:{self.user}:{self.database}"
        return f"{self.host}:{self.port}:{self.user}"


class CollectRequest(BaseModel):
    """发起元数据构建的请求：连接信息 + 选中的库列表"""

    host: str = Field(default="wl", description="数据库主机")
    port: int = Field(default=3307, description="端口")
    user: str = Field(default="root", description="用户名")
    password: str = Field(default="123456", description="密码")
    databases: list[str] | None = Field(
        default=["supply_chain_zh"],
        description="选中的业务库列表；None 表示采集所有业务库",
    )

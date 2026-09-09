"""本地启动 API 入口"""

import uvicorn


if __name__ == "__main__":
    uvicorn.run("agent.api:app", host="0.0.0.0", port=8000)

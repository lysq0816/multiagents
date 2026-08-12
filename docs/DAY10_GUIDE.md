# 第 10 天说明：部署与最终交付

## 交付内容

项目提供本地 Python 和 Docker Compose 两种启动方式。容器只包含应用源码、政策目录和
运行依赖，不复制本地密钥、历史实验产物、官方 τ2 checkout 或测试缓存。

Python Wheel 也已做临时构建验证：包内包含工作台静态资源和 14 条政策 JSON，不包含
`local_secrets`。本地密钥模块导入时禁止生成字节码，避免 Key 被复制进 `__pycache__`。

## 本地启动

```powershell
cd D:\llm项目\多智能体协作
uv sync --extra dev
uv run uvicorn after_sales_agents.api:app --reload
```

浏览器访问：

```text
http://127.0.0.1:8000
http://127.0.0.1:8000/docs
```

## Docker Compose

```powershell
docker compose up --build
```

服务监听：

```text
http://127.0.0.1:8000
```

停止：

```powershell
docker compose down
```

当前开发主机没有安装 Docker CLI，因此本轮不能在本机实际构建镜像；Dockerfile 和
Compose 的结构、密钥排除规则由自动化测试覆盖。交付到装有 Docker 的机器后应额外
运行：

```powershell
docker compose config
docker compose build
```

Compose 文件不注入任何模型密钥。当前业务工作流、界面、离线实验和发布验证均不需要
模型 API；如以后显式运行真实模型基线，应在运行时通过安全的环境管理方式提供密钥，
不要写入镜像或 Compose 文件。

## 统一离线演示

```powershell
uv run python scripts\run_all_demos.py
```

该命令运行专业智能体交接、冲突规划、独立审核、第 8 天实验矩阵、第 9 天可靠性沙箱
和最终业务场景演示，产物为：

```text
artifacts/day10/all_demos.json
```

默认属性：

```text
offline: true
model_calls: 0
write_tool_calls: 0
```

此外，5 个稳定业务场景可以单独运行：

```powershell
uv run python scripts\run_delivery_scenarios.py
```

场景覆盖取消、退货、换货成功候选，缺少确认，以及同一商品退换货冲突。结果位于
`artifacts/day10/delivery_scenarios.json`。当前统一入口共 6 项并已全部通过。真实
DeepSeek 基线不在统一演示中，避免意外计费。

## 发布自检

```powershell
uv run python scripts\verify_release.py
```

自检会验证：

- 完整测试套件；
- Ruff 静态检查；
- 格式检查；
- OpenAPI 必需路径；
- 14 条政策目录；
- Dockerfile、Compose、README 和开发日志存在。

结果写入：

```text
artifacts/day10/release_verification.json
```

该命令不访问外网、不调用模型、不调用业务写工具。

## 业务安全边界

- 容器没有真实电商凭证或真实业务连接；
- 默认工作流只读取请求提供的沙箱快照；
- 人工批准与写执行严格分离；
- 任何沙箱写执行都必须消费匹配摘要的单次授权；
- 执行后必须比较预期与实际状态；
- 模型成本为空或 0 时只表示本次路径没有模型调用，不表示商业 API 免费。

## 发布前检查清单

```text
[ ] 确认 local_secrets.py 未进入镜像或版本库
[ ] 确认真实模型调用只能显式启动
[ ] 确认所有自动化测试通过
[ ] 确认实验报告标明离线/模型调用边界
[ ] 确认写执行仅连接沙箱
[ ] 确认审批授权为单次且绑定计划摘要
[ ] 确认开发日志记录最终验证结果
```

本项目本轮交付自检已完成上述非 Docker 项；Docker 两项需在安装 Docker CLI 的交付机上
补跑。

# PersonalTutor

> 基于 [DeepTutor](https://github.com/HKUDS/DeepTutor) 的个性化 AI 学习导师 —— 把"通用辅导"升级为"懂你的成长系统"。

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![DeepTutor](https://img.shields.io/badge/built%20on-DeepTutor-4f9cf9)](https://github.com/HKUDS/DeepTutor)
[![Phase](https://img.shields.io/badge/phase-3%20(quiz%20+%20exam)-orange)](#roadmap)
[![Tests](https://img.shields.io/badge/tests-62%20passing-brightgreen)](#)

PersonalTutor 在**完全不改 DeepTutor 业务代码**的前提下,叠加了个人成长所需的四件事:精细的**弱点追踪**、个性化的**学习路线图**、自适应的**测试与复习**、可扩展的**学习领域**。它通过 DeepTutor 预留的插件接口被自动发现,上游每次更新都能干净地 rebase 进来。

```text
入门诊断 → 建立学习档案 → 规划专项路线图 → 日常学习/复习闭环 → 迭代
   ↓            ↓                ↓                  ↓
全领域诊断    弱点档案+       个性化 Mastery       出题/测试/复习
(1套题)      能力基线        Path + FSRS调度      自动更新档案
```

---

## 它解决了什么?

DeepTutor 是优秀的通用导师,但一个真正驱动个人成长的系统还需要:

| 需求 | DeepTutor 现状 | PersonalTutor 补齐 |
|------|---------------|-------------------|
| 精细弱点追踪 | Memory L3 `profile`(软命题) | 逐知识点的 **BKT** 贝叶斯追踪 ✅ |
| 精准复习调度 | Mastery Path 固定间隔 | **FSRS-4.5** 卡片级调度 ✅ |
| 个性化学习路线 | 硬编码 capability | **弱点优先 + 拓扑排序**路线图 ✅ |
| 正式评估 | `deep_question`(练习导向) | 限时**考试引擎** + 成绩单 ✅ |
| 自适应出题 | 固定难度 | **BKT 驱动**弱点选题 + 动态难度 ✅ |
| 新增学习领域 | 硬编码 capability | **领域插件注册表**(加领域不改代码) ✅ |

---

## 核心特性

### 🔌 零侵入集成
通过 DeepTutor 预留但未实现的 `deeptutor.plugins.loader` 接口被发现,**只触碰上游 2 处**(共十余行,集中在 `patches/`),rebase 几乎零冲突。

### 🎯 可扩展的领域框架
新增一个学习领域 = 一个 YAML 知识图谱 + 一个 spec 类。当前内置**编程算法**(20 个知识点,覆盖数据结构/经典算法/复杂度分析)。后续逐步加入:大模型、摄影、美术鉴赏、叙事学、写作、经济……

### 🧠 单一 LLM 配置源
复用 DeepTutor 的 `model_catalog.json`,PersonalTutor **不存第二个 API key**。改一次模型设置,所有能力同步生效。

### 📊 精细学习档案
基于 **Bayesian Knowledge Tracing (BKT)** 对每个知识点维护"掌握概率"。每答一题都用标准贝叶斯更新,产出可解释的弱点画像,并同步到 DeepTutor 的 Memory L3。

---

## 快速开始

```bash
git clone https://github.com/ZephaniaCN/PersonalTutor.git
cd PersonalTutor

# 1. Python 3.11 环境(复用 DeepTutor 全部依赖)
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -e .
uv pip install pytest pytest-asyncio

# 2. 验证插件注入端到端打通
deeptutor run personal_hello "smoke test"
# → PersonalTutor v0.1.0 is online | 编程算法 (20 knowledge points)

# 3. 启动服务 + 测试 REST
deeptutor serve &
curl http://localhost:8001/api/v1/personal/health
curl http://localhost:8001/api/v1/personal/domains
curl -X POST http://localhost:8001/api/v1/personal/diagnostics/programming/start

# 4. 运行测试套件(含上游兼容性契约)
python -m pytest personal_tutor/tests/ -v
```

**前端**(可选):
```bash
cd frontend && npm install && npm run build && npm run start
# → http://localhost:3783 (首页 + 领域知识图谱 + 诊断面板)
```

---

## 架构

```
┌─────────────── DeepTutor (upstream, ~unmodified) ───────────────┐
│  FastAPI · capability protocol · Memory · RAG · CLI             │
│        ↑  reserved hook: deeptutor.plugins.loader (shim → ↓)    │
└────────┼─────────────────────────────────────────────────────────┘
         │
┌────────┴─────────────── personal_tutor/ ────────────────────────┐
│  plugins.py          capability 发现 → BaseCapability            │
│  domains/            DomainSpec + KnowledgeGraph + 注册表         │
│     programming/        ↳ 20 个知识点的种子领域                   │
│  learning/            BKT 知识追踪 + 档案构建 *(Phase 1)*        │
│  capabilities/        personal_hello · diagnostic *(Phase 1)*   │
│  llm/                 复用 model_catalog 的 LLM 客户端            │
│  api/router.py        /api/v1/personal/* REST                    │
│  storage/             走 PathService 的 JSON 存储                 │
│  tests/               领域单测 + 上游兼容性契约                    │
└──────────────────────────────────────────────────────────────────┘
```

深入的设计文档见 [PERSONAL_TUTOR.md](PERSONAL_TUTOR.md)。

---

## <a name="roadmap"></a>Roadmap

| Phase | 范围 | 状态 |
|-------|------|------|
| **0 — 基础设施** | 环境、插件注入、领域框架、REST、编程种子领域、前端骨架 | ✅ 完成 |
| **1 — 诊断 + 档案** | 入门诊断能力、BKT 知识追踪、档案构建器 | ✅ 完成 |
| **2 — 路线图 + FSRS** | 个性化路线图生成、FSRS-4.5 调度器、Mastery Path 同步 | ✅ 完成 |
| **3 — 出题 + 考试** | BKT 驱动的自适应出题、限时考试引擎、LLM 判分、成绩单 | ✅ 完成 |
| **4 — 前端** | 仪表板:档案 / 路线图 / 复习队列 / 考试 | ☐ 规划 |

---

## 许可与归属

- 本项目代码遵循 [Apache License 2.0](LICENSE)。
- 基于 [HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor)(Apache-2.0)衍生,上游源码保留在 `deeptutor/`、`deeptutor_cli/`,通过 `patches/` 管理最小改动。详见 [NOTICE](NOTICE)。
- 上游原始 README 保留为 [README_UPSTREAM.md](README_UPSTREAM.md)。

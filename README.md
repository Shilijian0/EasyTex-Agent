# 🚀 LaTeX Optimizer Skill for Claude Code

> **让 AI 成为你的 LaTeX 排版大师。** 一句大白话，生成专业公式；一条指令，自动调整字体排版；代码写完即刻静默编译，有错精准报，没错秒出 PDF。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Win%20%7C%20Mac%20%7C%20Linux-lightgrey.svg)]()

---

## 📖 目录

- [Introduction — 自然语言转写案例展示](#-introduction--自然语言转写案例展示)
- [核心能力](#-核心能力)
- [项目结构](#-项目结构)
- [安装与配置](#-安装与配置)
- [API 参考](#-api-参考)
- [📖 使用教程](#-使用教程)
- [运行测试](#-运行测试)
- [常见问题](#-常见问题)
- [贡献与许可](#-贡献与许可)

---

## ✨ Introduction — 自然语言转写案例展示

### 案例 A：大白话 → 专业矩阵公式

| 用户输入（自然语言） | 生成的 LaTeX 代码 |
|:---|:---|
| "写一个3x3单位矩阵右乘列向量x，等号右边是全是lambda的向量" | 见下方 ↓ |

```latex
% === 优化后的 LaTeX 代码 ===
% 自动添加了 equation 环境、正确的 bmatrix 和缩进

\begin{equation}
    I_3 \cdot \mathbf{x} =
    \underbrace{
        \begin{bmatrix}
            1 & 0 & 0 \\
            0 & 1 & 0 \\
            0 & 0 & 1
        \end{bmatrix}
    }_{\text{单位矩阵 } I_3}
    \cdot
    \begin{bmatrix}
        x_1 \\
        x_2 \\
        x_3
    \end{bmatrix}
    =
    \begin{bmatrix}
        \lambda \\
        \lambda \\
        \lambda
    \end{bmatrix}
    =
    \lambda \cdot
    \begin{bmatrix}
        1 \\
        1 \\
        1
    \end{bmatrix}
\end{equation}
```

> 🎯 **Skill 做了什么？**
> 1. AI 理解"全是 lambda 的向量" → 自动补全为 `[\lambda, \lambda, \lambda]^T` 列向量
> 2. 自动包裹 `equation` 编号环境 + `bmatrix` 矩阵环境
> 3. 自动添加适当的换行和缩进，生成规范可编译的 LaTeX 代码
> 4. 静默编译验证 → ✅ 一次通过，零报错

---

### 案例 B：格式排版动态调整

| 用户输入（自然语言） | Skill 后台执行的动作 |
|:---|:---|
| "把正文字体改成微软雅黑，行间距调成1.5倍，并在导言区自动引入宏包" | 见下方 ↓ |

**Step 1 — AI 调用 Skill 分析当前文件：**

```json
// AI → Skill (analyze)
{
  "filepath": "/home/user/thesis/chapter1.tex",
  "action_type": "analyze"
}

// Skill → AI (分析结果)
{
  "success": true,
  "data": {
    "document_class": "ctexart",
    "packages": ["amsmath", "graphicx", "hyperref"],
    "font_settings": {},
    "system_info": {
      "available_fonts_sample": [
        "Microsoft YaHei", "SimSun", "KaiTi", "Times New Roman", ...
      ]
    }
  }
}
```

**Step 2 — AI 生成精准修改并执行：**

```json
// AI → Skill (modify_preamble)
{
  "filepath": "/home/user/thesis/chapter1.tex",
  "action_type": "modify_preamble",
  "modifications": {
    "font_settings": {
      "cjk_font": "Microsoft YaHei"
    },
    "line_spacing": 1.5,
    "packages_to_add": ["setspace"]
  }
}
```

**Step 3 — Skill 自动完成：**

```latex
% === 修改后的导言区（实际 diff）===

\documentclass[12pt,a4paper]{ctexart}

\usepackage{amsmath}
\usepackage{graphicx}
\usepackage{hyperref}
+ \usepackage{setspace}          ← 自动引入行距宏包

+ \setCJKmainfont{Microsoft YaHei}  ← 自动设置中文字体（经系统字体验证 ✅）
+ \linespread{1.5}                  ← 自动设置 1.5 倍行距

\begin{document}
% ... 正文不变 ...
\end{document}
```

**Step 4 — 静默编译验证：**

```
✅ 编译成功！PDF 已生成: /home/user/thesis/chapter1.pdf
   编译器: xelatex | 耗时: 1.23s | 错误: 0
```

> 🛡️ **安全机制：**
> - 修改前**自动校验字体**是否已安装在系统中 → 若缺失则返回 `FONT_NOT_FOUND` 中断信号，阻止修改
> - 自动检测新增宏包是否与已有宏包**冲突**（如 `ctex` 与 `xeCJK`）→ 冲突则告警并阻止
> - 修改前**自动创建 .bak 备份** → 编译失败可一键回滚

---

## 🧠 核心能力

| 能力 | 说明 |
|:---|:---|
| **导言区静态分析** | 解析 `\documentclass`、`\usepackage`、自定义命令、字体设置，识别已有宏包，防止 AI 乱写冲突命令 |
| **静默编译闭环** | 后台调用 `xelatex`/`latexmk` → 捕获 stdout/stderr/.log → 解析结果 → 返回结构化 JSON |
| **精准错误提取** | 从 `.log` 中只提取 `! LaTeX Error:` 行 + 上下文，过滤 overfull/underfull 等噪声 |
| **致命错误拦截** | `font not found` → `FONT_NOT_FOUND` 中断信号 → AI 停止自动修改 → 提示用户安装字体 |
| **安全修改注入** | 添加/移除宏包 → 字体设置 → 行距调整 → 原始代码注入，全部带冲突检测和原子写入 |
| **系统字体查询** | Windows/macOS/Linux 三平台字体检测，模糊匹配 + 精确匹配 |
| **自动回滚** | 每次修改前创建 `.bak` 备份，编译失败可恢复 |

---

## 📁 项目结构

```
latex-optimizer-skill/
│
├── README.md                          # 📖 完整文档（你正在阅读）
├── LICENSE                            # 📜 MIT 开源协议
├── latex_optimizer.json               # 🔧 MCP 工具声明文件
│
├── scripts/
│   └── latex_core.py                  # 🐍 核心驱动脚本（~550 行）
│       ├── LatexProject               #    .tex 解析器
│       ├── LatexCompiler              #    静默编译器
│       ├── LatexErrorParser           #    错误日志解析器
│       ├── SystemFontChecker          #    系统字体检测器
│       └── LatexOptimizer             #    主编排器
│
├── tests/
│   ├── test_latex_core.py             # 🧪 单元测试（10 个测试类，30+ 测试用例）
│   └── fixtures/
│       ├── sample_basic.tex           #    正常编译的样本文件
│       └── sample_with_error.tex      #    含典型错误的样本文件
│
└── .claude/
    └── settings.json.example          # ⚙️  Claude Code 配置示例
```

---

## 🔧 安装与配置

### 前置依赖

- **Python 3.9+**
- **LaTeX 发行版**（以下任一）：
  - [TeX Live](https://tug.org/texlive/)（推荐，跨平台）
  - [MiKTeX](https://miktex.org/)（Windows）
  - 确保 `xelatex` 或 `latexmk` 在系统 `PATH` 中
- **Claude Code**（或兼容 MCP 的 AI 工具）

### 1. 克隆仓库

```bash
git clone https://github.com/YOUR_USERNAME/latex-optimizer-skill.git
cd latex-optimizer-skill
```

### 2. 验证 Python 依赖

该 Skill **零外部 Python 依赖**，仅使用标准库。验证安装：

```bash
python scripts/latex_core.py --help   # 或：
echo '{"filepath":"tests/fixtures/sample_basic.tex","action_type":"analyze"}' | python scripts/latex_core.py
```

### 3. 配置到 Claude Code

将 `.claude/settings.json.example` 的内容合并到你的 Claude Code 配置文件中：

**方案 A — 全局配置（所有项目可用）：**

```bash
# 编辑 ~/.claude/settings.json，添加 skills 部分
```

**方案 B — 项目级配置（仅当前项目）：**

```bash
# 在你的 LaTeX 项目根目录下：
mkdir -p .claude
cp latex-optimizer-skill/.claude/settings.json.example .claude/settings.json
# 然后编辑 settings.json 中的路径指向实际位置
```

实际配置中，关键的 `command` 路径需指向 `scripts/latex_core.py` 的绝对路径：

```json
{
  "skills": [
    {
      "name": "latex-optimizer",
      "tools": [
        {
          "name": "optimize_and_compile_latex",
          "command": "python",
          "args": [
            "/ABSOLUTE/PATH/TO/latex-optimizer-skill/scripts/latex_core.py"
          ]
        }
      ]
    }
  ]
}
```

### 4. 验证配置

在 Claude Code 中运行：

```
请分析我的 LaTeX 文件 /path/to/document.tex 的导言区结构。
```

Claude 应自动调用 `optimize_and_compile_latex` 工具并返回分析结果。

---

## 📚 API 参考

### 工具名称

`optimize_and_compile_latex`

### 输入参数

| 参数 | 类型 | 必需 | 说明 |
|:---|:---|:---|:---|
| `filepath` | `string` | ✅ | 目标 `.tex` 文件的绝对路径 |
| `action_type` | `enum` | ✅ | 操作类型（见下方） |
| `user_prompt` | `string` | ❌ | 用户自然语言指令（`full_optimize` 时推荐） |
| `modifications` | `object` | ❌ | 修改指令（`modify_preamble` / `full_optimize` 时使用） |
| `compiler` | `enum` | ❌ | 编译器选择，默认 `auto` |
| `timeout` | `integer` | ❌ | 编译超时秒数，默认 60 |

### action_type 枚举值

| 值 | 说明 |
|:---|:---|
| `analyze` | 解析导言区结构，返回 documentclass、宏包列表、字体配置、自定义命令等 |
| `compile` | 静默编译，返回编译状态 + 精准错误摘要 |
| `modify_preamble` | 安全修改导言区 → 自动备份 → 编译验证 → 返回结果 |
| `full_optimize` | 分析 → 提供上下文给 AI → AI 生成修改 → 编译验证（完整闭环） |
| `check_fonts` | 查询系统已安装字体列表，检查指定字体可用性 |

### modifications 对象结构

```json
{
  "packages_to_add": ["geometry", "xcolor"],
  "packages_to_remove": ["inputenc"],
  "font_settings": {
    "main_font": "Times New Roman",
    "cjk_font": "Microsoft YaHei"
  },
  "line_spacing": 1.5,
  "raw_injections": [
    "\\geometry{margin=2.5cm}",
    "\\definecolor{myblue}{RGB}{30,60,120}"
  ]
}
```

### 输出结构

```json
{
  "success": true,
  "action": "analyze",
  "data": {
    "document_class": "article",
    "class_options": ["12pt", "a4paper"],
    "packages": [{"name": "amsmath", "options": []}],
    "font_settings": {},
    "preamble_line_range": [1, 12]
  },
  "errors": [],
  "fatal_signal": null,
  "compiler_output": "..."
}
```

### 致命错误信号（fatal_signal）

| 信号 | 触发条件 | AI 应执行的动作 |
|:---|:---|:---|
| `FONT_NOT_FOUND` | 指定字体未在系统中安装 | 🛑 停止修改，提示用户安装字体或选择替代字体 |
| `COMPILER_NOT_FOUND` | 未找到 xelatex/latexmk | 🛑 停止操作，提示用户安装 TeX Live |
| `FILE_LOCKED` | 文件被其他进程锁定 | 🛑 稍后重试，不要覆盖文件 |
| `null` | 无致命错误 | ✅ 可继续操作 |

---

## 📖 使用教程

### 🏃 快速上手（3 分钟体验）

**前提：** 已按上文[安装与配置](#-安装与配置)完成 Skill 注册。

在 Claude Code 对话框中输入你的第一条 LaTeX 指令：

```
帮我看看 /home/user/paper/main.tex 这个文件用了哪些宏包和字体。
```

Claude 会自动调用 `optimize_and_compile_latex` 工具（action: `analyze`），返回：

```
✅ 分析完成！

文档类：article (12pt, a4paper)
已加载宏包：
  • amsmath, amssymb — 数学公式
  • graphicx       — 插图
  • geometry       — 页面边距 (margin=2.5cm)
  • hyperref       — 超链接 (colorlinks=true)
自定义命令：\R, \norm, \innerprod
当前字体设置：未使用 fontspec，使用默认 Computer Modern
```

---

### 🎬 场景一：大白话转公式

> **你只需要用自然语言描述数学公式，AI 自动写出可编译的 LaTeX 代码。**

**你的对话：**

```
我的论文 methods.tex 第 3 节需要插入一个公式：
"3x3 的协方差矩阵 Sigma，对角线是 sigma_1^2, sigma_2^2, sigma_3^2，
非对角线元素是 rho_ij 乘以对应的 sigma"
```

**Claude 的回应（Skill 内部流程）：**

| 步骤 | Skill 内部操作 | 说明 |
|:---|:---|:---|
| ① | `action: "analyze"` → 获取导言区上下文 | 确认已有 `amsmath`，无需额外宏包 |
| ② | AI 生成 LaTeX 代码并注入正文 | 自动添加 `equation` 环境 + `bmatrix` |
| ③ | `action: "compile"` → 静默编译验证 | 发现 `\bm` 命令需要确认是否已加载 |
| ④ | 自动补充 `\usepackage{bm}` → 再次编译 | ✅ 编译通过 |

**最终生成的代码：**

```latex
\begin{equation}
    \boldsymbol{\Sigma} =
    \begin{bmatrix}
        \sigma_1^2      & \rho_{12}\sigma_1\sigma_2 & \rho_{13}\sigma_1\sigma_3 \\
        \rho_{21}\sigma_2\sigma_1 & \sigma_2^2       & \rho_{23}\sigma_2\sigma_3 \\
        \rho_{31}\sigma_3\sigma_1 & \rho_{32}\sigma_3\sigma_2 & \sigma_3^2
    \end{bmatrix}
    \label{eq:covariance}
\end{equation}
```

> 🎯 **亮点：** AI 理解"非对角线元素是 rho_ij 乘以对应的 sigma"，自动写出 `\rho_{12}\sigma_1\sigma_2` 形式的矩阵元素，并自动编号和加标签。

---

### 🎬 场景二：字体与排版一键调整

> **你说"改字体"，Skill 在后台完成字体验证 → 修改导言区 → 备份 → 编译的全闭环。**

**你的对话：**

```
把 main.tex 的正文字体改成 Times New Roman，中文字体改成思源宋体，
行间距 1.5 倍，页边距改成 2.5cm。
```

**Claude + Skill 的完整执行流：**

```
━━━ Step 1: 环境分析 ━━━
📋 analyze → 当前使用 ctexart，已加载 amsmath, hyperref
🔍 check_fonts → "Times New Roman" ✅ 系统已安装
                  "思源宋体" → ⚠️ 未找到精确匹配
                  相似字体: "Source Han Serif SC", "Noto Serif CJK SC"

Claude 提示你：
  "思源宋体"在您的系统中对应的字体名是 "Source Han Serif SC"，
  是否用它替代？ → 你确认

━━━ Step 2: 安全修改 ━━━
📦 save_backup → main.tex.bak.1718123456
🔧 modify_preamble → 
    + \setmainfont{Times New Roman}
    + \setCJKmainfont{Source Han Serif SC}
    + \linespread{1.5}
    + \geometry{margin=2.5cm}

━━━ Step 3: 编译验证 ━━━
🔨 xelatex -interaction=nonstopmode main.tex
⏱️ 耗时 1.8s
✅ PDF 已生成: /home/user/paper/main.pdf
    错误: 0 | 警告: 0

━━━ 最终报告 ━━━
✅ 全部完成！修改摘要：
  • 英文主字体 → Times New Roman
  • 中文主字体 → Source Han Serif SC
  • 行间距 → 1.5 倍
  • 页边距 → 2.5cm
  • 编译状态 → 成功 ✅
  • 备份文件 → main.tex.bak.1718123456
```

> 🛡️ **安全机制提醒：** 如果字体未安装，Skill 会返回 `FONT_NOT_FOUND` 致命信号，AI 停止修改并提示你安装字体 — **绝不会静默失败**。

---

### 🎬 场景三：编译报错 → 智能 Debug

> **当 LaTeX 编译失败时，Skill 帮你从数百行的 .log 垃圾中提取真正有用的错误。**

**情景：** 你新加了一个 `\includegraphics`，编译时报错。

**你的对话：**

```
我刚修改了 figure.tex，编译报错了，帮我看看是什么问题。
```

**Skill 的精准反馈：**

```json
{
  "success": false,
  "action": "compile",
  "errors": [
    {
      "line": 42,
      "message": "LaTeX Error: File `figures/result.png' not found.",
      "context": "l.42 \\includegraphics[width=\\linewidth]{figures/result.png}\n                      ^^^^^^^^^^^^^^^^\nI could not locate the file...",
      "is_fatal": false
    }
  ],
  "fatal_signal": null
}
```

**Claude 解读给你听：**

```
❌ 编译失败！发现 1 个错误（过滤掉了 12 条无关警告）：

📍 位置：第 42 行
📝 错误：找不到图片文件 figures/result.png
💡 建议：
  1. 检查文件路径是否正确（区分大小写）
  2. 当前工作目录: /home/user/paper/
  3. 该目录下存在: figures/results.png（多了个 s）
  → 可能是拼写错误：result → results
```

> 🔍 **噪声过滤对比：** 原始 .log 共 847 行，Skill 只提取出 1 条有效错误，过滤掉了 12 条 Overfull hbox 警告、3 条字体警告和大量文件加载信息。

---

### 💬 Claude Code 对话中的完整交互示例

以下是一个真实对话流程的浓缩版，展示 Skill 在 Claude Code 中如何使用：

```
┌─────────────────────────────────────────────────────────────┐
│  用户                                                       │
├─────────────────────────────────────────────────────────────┤
│ "帮我写一个贝叶斯定理的 LaTeX 公式，放到 bayes.tex 里，      │
│  然后编译成 PDF。"                                          │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Claude (AI)                                                │
├─────────────────────────────────────────────────────────────┤
│ 好的，我先看看 bayes.tex 当前的结构。                        │
│                                                             │
│ [调用 analyze]                                              │
│ → 已用 article 类，有 amsmath，可以直接写公式               │
│                                                             │
│ 我生成以下代码插入正文：                                     │
│                                                             │
│ \begin{equation}                                            │
│     P(A|B) = \frac{P(B|A) \cdot P(A)}{P(B)}                │
│     \label{eq:bayes}                                       │
│ \end{equation}                                              │
│                                                             │
│ [调用 modify_preamble 注入代码]                              │
│ [调用 compile 验证]                                         │
│                                                             │
│ ✅ 编译成功！PDF 已生成，0 个错误。                          │
└─────────────────────────────────────────────────────────────┘
```

---

### 🔧 命令行直接调用（进阶技巧）

除了通过 Claude Code 对话使用，你也可以直接在终端调用 Skill 脚本：

```bash
# 1. 分析文件结构
echo '{"filepath":"/home/user/paper/main.tex","action_type":"analyze"}' \
  | python scripts/latex_core.py | python -m json.tool

# 2. 只编译不修改
echo '{"filepath":"/home/user/paper/main.tex","action_type":"compile","compiler":"xelatex","timeout":120}' \
  | python scripts/latex_core.py

# 3. 直接修改导言区（带字体检查）
cat > /tmp/mod.json << 'EOF'
{
  "filepath": "/home/user/paper/main.tex",
  "action_type": "modify_preamble",
  "modifications": {
    "packages_to_add": ["geometry", "setspace", "xcolor"],
    "font_settings": {
      "main_font": "Times New Roman",
      "cjk_font": "Source Han Serif SC"
    },
    "line_spacing": 1.5,
    "raw_injections": [
      "\\geometry{margin=2.5cm}",
      "\\definecolor{linkblue}{RGB}{30,60,150}"
    ]
  }
}
EOF
python scripts/latex_core.py < /tmp/mod.json | python -m json.tool

# 4. 检查字体
echo '{"filepath":"dummy.tex","action_type":"check_fonts","user_prompt":"Times New Roman 和 微软雅黑"}' \
  | python scripts/latex_core.py

# 5. 完整优化流程（分析 + 上下文，供 AI 决策）
echo '{"filepath":"/home/user/paper/main.tex","action_type":"full_optimize","user_prompt":"把正文字体改成微软雅黑，行间距 1.5 倍"}' \
  | python scripts/latex_core.py
```

---

### 🧩 集成到你的工作流

| 使用场景 | 推荐 action | 一句话说明 |
|:---|:---|:---|
| 新文档审阅 | `analyze` | 快速了解 .tex 用了哪些宏包和字体 |
| 公式编写 | `full_optimize` | 分析上下文 → AI 生成代码 → 编译验证 |
| 字体/排版调整 | `modify_preamble` | 安全修改导言区 → 自动备份 → 编译 |
| CI/CD 自动构建 | `compile` | 静默编译 → 返回结构化结果 |
| 换电脑/新环境 | `check_fonts` | 先查字体再开工，避免编译失败 |
| 调试编译错误 | `compile` | 一键编译 → 过滤噪声 → 返回精准错误

---

## 🧪 运行测试

```bash
cd latex-optimizer-skill

# 运行全部测试
python -m pytest tests/test_latex_core.py -v

# 或者使用 unittest
python tests/test_latex_core.py

# 运行特定测试类
python -m pytest tests/test_latex_core.py::TestLatexProject -v
python -m pytest tests/test_latex_core.py::TestLatexErrorParser -v

# CLI 手动集成测试
echo '{"filepath":"tests/fixtures/sample_basic.tex","action_type":"analyze"}' | python scripts/latex_core.py | python -m json.tool
```

### 测试覆盖

| 测试类 | 覆盖内容 |
|:---|:---|
| `TestLatexProject` | 文件解析、documentclass 提取、宏包提取、异常处理 |
| `TestPackageConflictDetection` | ctex↔xeCJK、natbib↔biblatex 等互斥宏包检测 |
| `TestLatexProjectModifications` | 添加/移除宏包、行距修改、保存与重新解析、备份 |
| `TestLatexErrorParser` | 错误提取、噪声过滤、行号提取、致命错误分类 |
| `TestFatalErrorPatterns` | FONT_NOT_FOUND、COMPILER_NOT_FOUND 正则匹配 |
| `TestSystemFontChecker` | 字体列表查询、不存在的字体检测 |
| `TestLatexCompiler` | 编译器自动发现、命令行构建 |
| `TestLatexOptimizerIntegration` | analyze、modify_preamble、check_fonts 端到端 |
| `TestCLIEntry` | CLI stdin→stdout 完整流程 |
| `TestUtilityFunctions` | 安全文件读写、编码回退 |

---

## ❓ 常见问题

### Q: 我需要安装额外的 Python 包吗？

**不需要。** 该 Skill 零外部 Python 依赖，仅使用标准库（`json`, `os`, `re`, `subprocess`, `sys`, `pathlib`, `dataclasses`, `tempfile` 等）。

### Q: 支持哪些 LaTeX 编译器？

默认按优先级自动发现：**XeLaTeX** > LuaLaTeX > latexmk > pdfLaTeX。也可以手动指定 `"compiler": "xelatex"`。

### Q: Windows 上字体检测不工作？

字体检测使用 PowerShell 命令查询 Windows 字体。如果失败，请确保：
1. PowerShell 可正常执行
2. 脚本有足够权限

### Q: 修改后的文件可以回滚吗？

是的。每次 `modify_preamble` 操作前会自动创建 `.bak.<timestamp>` 备份文件。回滚命令：

```bash
cp /path/to/file.tex.bak.1718123456 /path/to/file.tex
```

### Q: 如何处理多个 .tex 文件（如 `\input`/`\include`）？

当前版本处理单文件。对于多文件项目，建议在**主文件**（包含 `\documentclass` 的文件）上操作。

---

## 📄 贡献与许可

本项目采用 [MIT License](LICENSE) 开源。

欢迎贡献！请提交 Issue 或 Pull Request 到 GitHub 仓库。

---

<p align="center">
  <b>Made with ❤️ for the LaTeX + AI community</b><br>
  <sub>如果你觉得这个 Skill 有用，请给个 ⭐ Star！</sub>
</p>

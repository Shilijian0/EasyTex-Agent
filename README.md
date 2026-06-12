# 🚀 EasyTex Agent

> **让 AI 成为你的 LaTeX 排版大师。** 一句大白话 → 专业公式，一条指令 → 自动调整排版，写完即静默编译，有错精准报，没错秒出 PDF。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-47%2F47%20passed-brightgreen.svg)]()
[![Platform](https://img.shields.io/badge/Platform-Win%20%7C%20Mac%20%7C%20Linux-lightgrey.svg)]()

---

## ✨ 自然语言转写案例

### 案例 A：大白话 → 矩阵公式

| 你说 | Skill 生成 |
|:---|:---|
| "写一个3x3单位矩阵右乘列向量x，等号右边是全是lambda的向量" | |

```latex
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
        x_1 \\ x_2 \\ x_3
    \end{bmatrix}
    =
    \begin{bmatrix}
        \lambda \\ \lambda \\ \lambda
    \end{bmatrix}
\end{equation}
```

> AI 理解"全是 lambda 的向量" → 自动补全列向量，加 `equation` 环境 + `bmatrix` → 编译 ✅ 零报错。

### 案例 B：字体排版一键调整

| 你说 | Skill 后台执行 |
|:---|:---|
| "把正文字体改成微软雅黑，行间距1.5倍" | 见下方 diff |

```latex
% === 修改前                           === 修改后
                                         + \usepackage{setspace}
                                         + \setCJKmainfont{Microsoft YaHei}
                                         + \linespread{1.5}
% ... 正文不变 ...
```

```
🔍 check_fonts → "Microsoft YaHei" ✅ 系统已安装
📦 save_backup → main.tex.bak.1718123456
🔨 xelatex → ⏱ 1.23s → ✅ PDF 已生成（0 错误）
```

> 🛡️ 字体未安装 → `FONT_NOT_FOUND` 中断信号 → 停止修改并提示用户。

---

## 📄 PDF 输出成果展示

以下为 `demo/demo_showcase.tex` 编译后的 PDF 效果（由 Skill 端到端生成）：

```
┌──────────────────────────────────────────────────────────────────────┐
│                        EasyTex Agent 功能演示                        │
│                             2026-06-12                               │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. 大白话转公式：矩阵乘法                                           │
│  ─────────────────────────                                           │
│                                                                      │
│  用户输入：「写一个3x3单位矩阵右乘列向量x...」                        │
│                                                                      │
│                    ┌─       ─┐ ┌  ┐    ┌   ┐                        │
│                    │ 1 0 0  │ │x₁│    │ λ │                        │
│         I₃ · x =   │ 0 1 0  │·│x₂│ =  │ λ │ = λ·1   (1)            │
│                    │ 0 0 1  │ │x₃│    │ λ │                        │
│                    └─       ─┘ └  ┘    └   ┘                        │
│                                                                      │
│  2. 大白话转公式：协方差矩阵                                         │
│  ─────────────────────────                                           │
│                                                                      │
│  用户输入：「3x3协方差矩阵，对角线sigma²，非对角线ρσ...」             │
│                                                                      │
│        ┌─                                  ─┐                        │
│        │   σ₁²       ρ₁₂σ₁σ₂    ρ₁₃σ₁σ₃   │                        │
│   Σ =  │  ρ₂₁σ₂σ₁      σ₂²      ρ₂₃σ₂σ₃   │              (2)        │
│        │  ρ₃₁σ₃σ₁    ρ₃₂σ₃σ₂      σ₃²     │                        │
│        └─                                  ─┘                        │
│                                                                      │
│  3. 贝叶斯定理                                                       │
│  ────────────                                                        │
│                                                                      │
│                      P(B|A) · P(A)                                   │
│           P(A|B) = ───────────────                         (3)       │
│                          P(B)                                        │
│                                                                      │
│  4. 排版优化对照表                                                   │
│  ────────────────                                                    │
│                                                                      │
│    修改项        修改前              修改后                           │
│   ───────────────────────────────────────────                        │
│    正文字体    Computer Modern     Times New Roman                   │
│    中文字体    未设置              Source Han Serif SC               │
│    行间距      单倍 (1.0)          1.5 倍                            │
│    页边距      默认 (3.2cm)        2.5cm                             │
│                                                                      │
│  5. 编译验证闭环                                                     │
│  ────────────────                                                    │
│                                                                      │
│    ① 解析导言区 → ② 字体验证 → ③ 安全修改 → ④ 静默编译 → ⑤ 错误过滤│
│                                                                      │
│    ❌ 若字体缺失: FATAL → FONT_NOT_FOUND → 中断，文件未被修改        │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

> 💡 完整 `.tex` 源文件见 [`demo/demo_showcase.tex`](demo/demo_showcase.tex)，可直接在本地编译查看效果。

---

## 🧠 核心能力

| 能力 | 说明 |
|:---|:---|
| **导言区分析** | 解析 `\documentclass`、`\usepackage`、自定义命令、字体配置，防止冲突 |
| **静默编译** | 后台 `xelatex`/`latexmk` → 捕获 stdout/stderr/.log → 结构化 JSON |
| **精准错误提取** | 只取 `! LaTeX Error:` + 上下文，过滤 overfull/underfull 等噪声 |
| **致命错误拦截** | `font not found` → `FONT_NOT_FOUND` 信号 → 中断并提示 |
| **安全注入** | 添加/移除宏包、字体、行距 — 全量冲突检测 + 原子写入 |
| **系统字体查询** | Win/Mac/Linux 三平台，精确匹配 + 模糊建议 |
| **自动回滚** | 每次修改前 `.bak` 备份，失败可恢复 |

---

## 📁 项目结构

```
EasyTex-Agent/
├── README.md                     # 本文件
├── LICENSE                       # MIT
├── latex_optimizer.json          # MCP 工具声明
├── demo/
│   └── demo_showcase.tex         # 演示文档（可直接编译）
├── scripts/
│   └── latex_core.py             # 核心驱动（~550 行）
├── tests/
│   ├── test_latex_core.py        # 47 个测试用例
│   └── fixtures/
│       ├── sample_basic.tex
│       └── sample_with_error.tex
└── .claude/
    └── settings.json.example     # Claude Code 配置
```

---

## 🔧 安装与配置

### 前置依赖
- **Python 3.9+**（零外部库依赖）
- **LaTeX 发行版**：[TeX Live](https://tug.org/texlive/) 或 [MiKTeX](https://miktex.org/)，确保 `xelatex` 在 PATH
- **Claude Code**

### 快速配置

```bash
git clone git@github.com:Shilijian0/EasyTex-Agent.git
cd EasyTex-Agent

# 验证可用
echo '{"filepath":"tests/fixtures/sample_basic.tex","action_type":"analyze"}' \
  | python scripts/latex_core.py | python -m json.tool
```

将以下内容合并到 `~/.claude/settings.json` 或项目的 `.claude/settings.json`：

```json
{
  "skills": [{
    "name": "latex-optimizer",
    "tools": [{
      "name": "optimize_and_compile_latex",
      "command": "python",
      "args": ["/你的路径/EasyTex-Agent/scripts/latex_core.py"]
    }]
  }]
}
```

---

## 📖 使用教程

### 快速上手

在 Claude Code 中直接对话即可：

```
"帮我看看 paper.tex 用了哪些宏包"
"把 main.tex 的正文字体改成 Times New Roman，行距 1.5 倍"
"写一个3x3协方差矩阵公式，对角线是sigma的平方"
"编译 thesis.tex，如果有错帮我看看是什么问题"
```

Claude 自动调用 Skill 完成分析→修改→编译→验证的全流程。

### 五种 Action 速查

```bash
# 分析导言区
echo '{"filepath":"doc.tex","action_type":"analyze"}' | python scripts/latex_core.py

# 静默编译
echo '{"filepath":"doc.tex","action_type":"compile","compiler":"xelatex"}' | python scripts/latex_core.py

# 安全修改 + 编译验证
echo '{"filepath":"doc.tex","action_type":"modify_preamble","modifications":{"font_settings":{"cjk_font":"Microsoft YaHei"},"line_spacing":1.5}}' | python scripts/latex_core.py

# 完整闭环（分析 → 编译 → 提供上下文给 AI）
echo '{"filepath":"doc.tex","action_type":"full_optimize","user_prompt":"把正文字体改成微软雅黑"}' | python scripts/latex_core.py

# 检查系统字体
echo '{"filepath":"doc.tex","action_type":"check_fonts"}' | python scripts/latex_core.py
```

| 场景 | 用哪个 action |
|:---|:---|
| 看文件用了什么宏包 | `analyze` |
| 改字体/排版 | `modify_preamble` |
| 写公式并验证 | `full_optimize` |
| 调试编译报错 | `compile` |
| 换电脑先查字体 | `check_fonts` |

---

## 📚 API 参考

### `optimize_and_compile_latex`

| 参数 | 类型 | 必需 | 说明 |
|:---|:---|:---|:---|
| `filepath` | string | ✅ | .tex 文件绝对路径 |
| `action_type` | enum | ✅ | `analyze` / `compile` / `modify_preamble` / `full_optimize` / `check_fonts` |
| `user_prompt` | string | | 自然语言指令 |
| `modifications` | object | | `{packages_to_add, font_settings, line_spacing, raw_injections}` |
| `compiler` | enum | | `auto`(默认) / `xelatex` / `lualatex` / `latexmk` |
| `timeout` | int | | 默认 60s |

### 致命信号

| 信号 | 含义 | 行为 |
|:---|:---|:---|
| `FONT_NOT_FOUND` | 指定字体未安装 | 🛑 中断，提示安装字体 |
| `COMPILER_NOT_FOUND` | 无 LaTeX 编译器 | 🛑 中断，提示安装 TeX Live |
| `null` | 正常 | ✅ 继续 |

---

## 🧪 测试

```bash
cd EasyTex-Agent
python -m unittest tests.test_latex_core -v
# → Ran 47 tests → OK ✅
```

零外部依赖，只需 Python 3.9+。

---

## ❓ 常见问题

**Q: 需要额外 Python 包吗？** 不需要，纯标准库。  
**Q: 支持哪些编译器？** 自动检测：XeLaTeX > LuaLaTeX > latexmk > pdfLaTeX。  
**Q: 改错了能回滚吗？** 每次修改前自动 `.bak` 备份，`cp file.tex.bak.xxx file.tex` 即可。  
**Q: 多文件项目？** 在主文件（含 `\documentclass` 的那个）上操作。

---

<p align="center">
  <b>Made with ❤️ for the LaTeX + AI community</b><br>
  <sub>⭐ Star if you find it useful!</sub>
</p>

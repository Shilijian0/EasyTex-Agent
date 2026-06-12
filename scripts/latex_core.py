#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LaTeX Optimizer Skill — 核心驱动脚本
======================================

为 Claude Code (MCP 兼容 AI 工具) 提供 LaTeX 文件的智能优化能力：
  - 导言区静态分析与冲突检测
  - 后台静默编译与 .log 解析
  - 精准错误提取与噪声过滤
  - 致命错误拦截（字体缺失等）
  - 自然语言转 LaTeX 修改的安全注入

架构：
  LatexProject      — .tex 文件解析与安全修改
  LatexCompiler     — 编译器发现与静默编译
  LatexErrorParser  — .log 错误提取与分类
  SystemFontChecker — 系统字体可用性查询
  LatexOptimizer    — 主编排器，整合上述模块

用法：
  echo '{"filepath":"/path/to/doc.tex","action_type":"analyze"}' | python latex_core.py
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# ============================================================================
# 常量定义
# ============================================================================

# 已知的标准 LaTeX 文档类（防止 AI 乱写 \documentclass 冲突）
KNOWN_DOCUMENT_CLASSES: Dict[str, List[str]] = {
    "article":  ["10pt", "11pt", "12pt", "a4paper", "letterpaper", "twoside", "twocolumn", "draft"],
    "report":   ["10pt", "11pt", "12pt", "a4paper", "letterpaper", "twoside", "draft", "openright", "openany"],
    "book":     ["10pt", "11pt", "12pt", "a4paper", "letterpaper", "twoside", "draft", "openright", "openany"],
    "ctexart":  ["10pt", "11pt", "12pt", "a4paper", "letterpaper", "twoside", "draft", "heading", "scheme"],
    "ctexrep":  ["10pt", "11pt", "12pt", "a4paper", "letterpaper", "twoside", "draft", "heading", "scheme"],
    "ctexbook": ["10pt", "11pt", "12pt", "a4paper", "letterpaper", "twoside", "draft", "heading", "scheme"],
    "beamer":   ["10pt", "11pt", "12pt", "handout", "aspectratio", "compress", "draft"],
    "standalone": ["preview", "multi", "crop"],
}

# 互斥宏包组（同时加载会冲突）
CONFLICTING_PACKAGES: Dict[str, List[str]] = {
    "ctex":       ["xeCJK", "CJK", "CJKutf8"],
    "xeCJK":      ["ctex", "CJK", "CJKutf8"],
    "fontspec":   [],
    "inputenc":   ["fontspec", "xelatex"],
    "fontenc":    ["fontspec"],
    "mathptmx":   ["times", "txfonts", "newtxtext"],
    "times":      ["mathptmx", "txfonts", "newtxtext"],
    "natbib":     ["biblatex"],
    "biblatex":   ["natbib"],
    "subfigure":  ["subfig", "subcaption"],
    "subfig":     ["subfigure", "subcaption"],
    "subcaption": ["subfigure", "subfig"],
}

# 需要放在导言区末尾的宏包（加载顺序敏感）
LOAD_ORDER_SENSITIVE: List[str] = [
    "hyperref", "cleveref", "glossaries", "biblatex", "csquotes",
]

# 编译错误噪声模式（overfull/underfull/font warning 等）
NOISE_PATTERNS: List[re.Pattern] = [
    re.compile(r"Overfull\s+\\[hv]box", re.IGNORECASE),
    re.compile(r"Underfull\s+\\[hv]box", re.IGNORECASE),
    re.compile(r"LaTeX\s+Font\s+Warning:", re.IGNORECASE),
    re.compile(r"Package\s+\w+\s+Warning:", re.IGNORECASE),
    re.compile(r"^\s*\(.+\)\s*$"),                     # 文件加载信息
    re.compile(r"^\s*\[\d+\]\s*$"),                    # 页码信息
    re.compile(r"No file .+\.aux\."),                  # 首次编译的 aux 缺失
    re.compile(r"Rerun to get"),                       # 需要二次编译的提示
    re.compile(r"^$"),                                  # 空行
]

# 致命错误模式（匹配到即中断）
FATAL_ERROR_PATTERNS: Dict[str, re.Pattern] = {
    "FONT_NOT_FOUND": re.compile(
        r"font.*not\s*found|Font.*not\s*found|cannot\s*find.*font|"
        r"fontspec error:.*not\s*found|The font.*cannot be found|"
        r"not loadable:.*font.*not\s*found",
        re.IGNORECASE | re.DOTALL,
    ),
    "COMPILER_NOT_FOUND": re.compile(
        r"command not found|xelatex.*not found|pdflatex.*not found|"
        r"I can't find the format file",
        re.IGNORECASE | re.DOTALL,
    ),
    "FILE_LOCKED": re.compile(
        r"permission denied|access is denied|cannot write on file|"
        r"file is locked",
        re.IGNORECASE | re.DOTALL,
    ),
}

# LaTeX 错误标识行
LATEX_ERROR_MARKER: re.Pattern = re.compile(
    r"^!\s+(LaTeX\s+Error:|Missing|Undefined|Emergency stop|"
    r"Package\s+\w+\s+Error:|Class\s+\w+\s+Error:)",
)


# ============================================================================
# 自定义异常
# ============================================================================

class LatexOptimizerError(Exception):
    """LaTeX Optimizer 基础异常。"""


class LatexFileNotFoundError(LatexOptimizerError):
    """目标 .tex 文件不存在。"""


class LatexCompilerNotFoundError(LatexOptimizerError):
    """未找到可用的 LaTeX 编译器。"""


class LatexCompilationError(LatexOptimizerError):
    """编译过程中发生错误。"""


class LatexFatalError(LatexOptimizerError):
    """致命错误，操作应被中断。"""
    def __init__(self, signal: str, message: str):
        super().__init__(message)
        self.signal = signal


class LatexPreambleError(LatexOptimizerError):
    """导言区解析或修改错误。"""


# ============================================================================
# 工具函数
# ============================================================================

def _safe_read_file(filepath: str, encoding: str = "utf-8") -> str:
    """安全读取文件，自动尝试多种编码。"""
    encodings = [encoding, "utf-8-sig", "gbk", "latin-1", "cp1252"]
    for enc in encodings:
        try:
            with open(filepath, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise LatexOptimizerError(f"无法以任何已知编码读取文件: {filepath}")


def _safe_write_file(filepath: str, content: str, encoding: str = "utf-8") -> None:
    """安全写入文件（先写临时文件再原子替换）。"""
    tmp_path = filepath + f".tmp.{uuid.uuid4().hex[:8]}"
    try:
        with open(tmp_path, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(tmp_path, filepath)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _find_executable(name: str) -> Optional[str]:
    """在系统 PATH 中查找可执行文件。"""
    return shutil.which(name)


# ============================================================================
# LatexProject: .tex 文件解析与安全修改
# ============================================================================

@dataclass
class PreambleInfo:
    """导言区解析结果。"""
    document_class: str = ""
    class_options: List[str] = field(default_factory=list)
    packages: List[Dict[str, Any]] = field(default_factory=list)
    custom_commands: List[str] = field(default_factory=list)
    font_settings: Dict[str, str] = field(default_factory=dict)
    raw_preamble: str = ""
    preamble_start_line: int = 0
    preamble_end_line: int = 0
    body_start_line: int = 0


class LatexProject:
    """
    .tex 文件解析器。

    职责：
      - 读取 .tex 文件，分离导言区与正文区
      - 提取 documentclass、宏包、自定义命令、字体设置
      - 检测宏包冲突
      - 安全地向导言区注入修改
    """

    def __init__(self, filepath: str):
        self.filepath = os.path.abspath(filepath)
        if not os.path.isfile(self.filepath):
            raise LatexFileNotFoundError(f"文件不存在: {self.filepath}")
        if not self.filepath.lower().endswith(".tex"):
            raise LatexOptimizerError(f"不是 .tex 文件: {self.filepath}")

        self.raw_content: str = ""
        self.preamble_info: Optional[PreambleInfo] = None
        self._body_content: str = ""
        self._parse()

    # ------------------------------------------------------------------
    # 解析
    # ------------------------------------------------------------------

    def _parse(self) -> None:
        """读取并解析 .tex 文件。"""
        self.raw_content = _safe_read_file(self.filepath)
        self.preamble_info = self._extract_preamble_info()
        self._body_content = self._extract_body()

    def _extract_preamble_info(self) -> PreambleInfo:
        """从原始内容中提取导言区信息。"""
        info = PreambleInfo()
        lines = self.raw_content.split("\n")

        # 定位 \begin{document}
        doc_begin_pattern = re.compile(r"\\begin\{document\}")
        doc_begin_line = -1
        for i, line in enumerate(lines):
            if doc_begin_pattern.search(line):
                doc_begin_line = i
                break

        if doc_begin_line < 0:
            raise LatexPreambleError(
                f"在 {self.filepath} 中未找到 \\begin{{document}}，"
                f"文件可能不完整或损坏。"
            )

        info.body_start_line = doc_begin_line  # 保留 \begin{document} 在正文中
        preamble_lines = lines[:doc_begin_line]
        info.raw_preamble = "\n".join(preamble_lines)
        info.preamble_start_line = 1
        info.preamble_end_line = doc_begin_line

        # 提取 documentclass
        self._parse_documentclass(info, preamble_lines)

        # 提取宏包
        self._parse_packages(info, preamble_lines)

        # 提取自定义命令
        self._parse_custom_commands(info, preamble_lines)

        # 提取字体设置
        self._parse_font_settings(info, preamble_lines)

        return info

    def _parse_documentclass(
        self, info: PreambleInfo, preamble_lines: List[str]
    ) -> None:
        """提取 \\documentclass[...]{...}。"""
        full_preamble = "\n".join(preamble_lines)
        # 支持跨行的 documentclass 声明
        dc_pattern = re.compile(
            r"\\documentclass\s*"          # \documentclass
            r"(?:\[([^\]]*)\])?"            # 可选选项 [...]
            r"\s*\{([^}]+)\}"               # 类名 {...}
        )
        match = dc_pattern.search(full_preamble)
        if match:
            options_str = match.group(1) or ""
            info.class_options = [
                opt.strip() for opt in options_str.split(",") if opt.strip()
            ]
            info.document_class = match.group(2).strip()

    def _parse_packages(
        self, info: PreambleInfo, preamble_lines: List[str]
    ) -> None:
        """提取所有 \\usepackage[...]{...} 声明。"""
        full_preamble = "\n".join(preamble_lines)
        # 匹配 \usepackage[opt]{pkg} 或 \usepackage{pkg}
        pkg_pattern = re.compile(
            r"\\usepackage\s*"             # \usepackage
            r"(?:\[([^\]]*)\])?"            # 可选选项
            r"\{([^}]+)\}"                  # 包名（可能逗号分隔多个）
        )
        for match in pkg_pattern.finditer(full_preamble):
            options_str = match.group(1) or ""
            options = [
                opt.strip() for opt in options_str.split(",") if opt.strip()
            ]
            pkg_names = [
                name.strip() for name in match.group(2).split(",")
            ]
            for pkg_name in pkg_names:
                if pkg_name:
                    info.packages.append({
                        "name": pkg_name,
                        "options": options,
                    })

    def _parse_custom_commands(
        self, info: PreambleInfo, preamble_lines: List[str]
    ) -> None:
        """提取自定义命令定义。"""
        for line in preamble_lines:
            stripped = line.strip()
            if any(
                stripped.startswith(cmd)
                for cmd in (
                    r"\newcommand", r"\renewcommand", r"\providecommand",
                    r"\DeclareMathOperator", r"\def", r"\newenvironment",
                    r"\renewenvironment",
                    r"\newtheorem",
                )
            ):
                info.custom_commands.append(stripped)

    def _parse_font_settings(
        self, info: PreambleInfo, preamble_lines: List[str]
    ) -> None:
        """提取字体相关设置。"""
        full_preamble = "\n".join(preamble_lines)

        # fontspec 相关的字体设置
        font_patterns = {
            "main_font": re.compile(r"\\setmainfont\s*\{([^}]+)\}"),
            "sans_font": re.compile(r"\\setsansfont\s*\{([^}]+)\}"),
            "mono_font": re.compile(r"\\setmonofont\s*\{([^}]+)\}"),
            "cjk_font": re.compile(r"\\setCJKmainfont\s*\{([^}]+)\}"),
        }
        for key, pattern in font_patterns.items():
            m = pattern.search(full_preamble)
            if m:
                info.font_settings[key] = m.group(1).strip()

    def _extract_body(self) -> str:
        """提取 \\begin{document} 之后的正文内容。"""
        if self.preamble_info is None:
            return ""
        lines = self.raw_content.split("\n")
        body_lines = lines[self.preamble_info.body_start_line:]
        return "\n".join(body_lines)

    # ------------------------------------------------------------------
    # 查询接口
    # ------------------------------------------------------------------

    def get_preamble_info(self) -> PreambleInfo:
        """返回导言区解析结果。"""
        if self.preamble_info is None:
            raise LatexPreambleError("尚未解析导言区。")
        return self.preamble_info

    def get_package_names(self) -> List[str]:
        """返回已加载宏包的名称列表。"""
        return [pkg["name"] for pkg in self.preamble_info.packages]

    def has_package(self, name: str) -> bool:
        """检查是否已加载指定宏包。"""
        return name in self.get_package_names()

    def detect_conflicts(self, new_packages: List[str]) -> List[Dict[str, str]]:
        """检测要添加的宏包是否与已有宏包冲突。"""
        conflicts: List[Dict[str, str]] = []
        existing = set(self.get_package_names())
        for pkg in new_packages:
            conflicting = CONFLICTING_PACKAGES.get(pkg, [])
            for conflict_pkg in conflicting:
                if conflict_pkg in existing:
                    conflicts.append({
                        "new_package": pkg,
                        "existing_package": conflict_pkg,
                        "message": (
                            f"宏包冲突: {pkg} 与已加载的 {conflict_pkg} 不兼容。"
                            f"请移除 {conflict_pkg} 或改用其他兼容的宏包。"
                        ),
                    })
        return conflicts

    # ------------------------------------------------------------------
    # 修改接口
    # ------------------------------------------------------------------

    def modify_preamble(
        self,
        packages_to_add: Optional[List[str]] = None,
        packages_to_remove: Optional[List[str]] = None,
        font_settings: Optional[Dict[str, str]] = None,
        line_spacing: Optional[float] = None,
        raw_injections: Optional[List[str]] = None,
    ) -> str:
        """
        安全地修改导言区。

        参数：
          packages_to_add:    要添加的宏包列表
          packages_to_remove: 要移除的宏包列表
          font_settings:      字体配置 {main_font, sans_font, mono_font, cjk_font}
          line_spacing:       行距倍数
          raw_injections:     要追加到导言区末尾的原始 LaTeX 代码行

        返回：
          修改后的完整 .tex 文件内容（字符串）。
        """
        if self.preamble_info is None:
            raise LatexPreambleError("尚未解析导言区，无法修改。")

        preamble_lines = self.preamble_info.raw_preamble.split("\n")
        modified_lines: List[str] = list(preamble_lines)

        # 1. 移除指定宏包
        if packages_to_remove:
            modified_lines = self._remove_packages(modified_lines, packages_to_remove)

        # 2. 添加宏包（在最后一个 \usepackage 之后）
        if packages_to_add:
            modified_lines = self._add_packages(modified_lines, packages_to_add)

        # 3. 修改字体设置
        if font_settings:
            modified_lines = self._apply_font_settings(modified_lines, font_settings)

        # 4. 修改行间距
        if line_spacing is not None:
            modified_lines = self._apply_line_spacing(modified_lines, line_spacing)

        # 5. 注入原始代码（追加到导言区末尾，\begin{document} 之前）
        if raw_injections:
            for inj in raw_injections:
                modified_lines.append(inj)

        # 重建全文
        new_preamble = "\n".join(modified_lines)
        new_content = new_preamble + "\n" + self._body_content
        return new_content

    def _remove_packages(
        self, lines: List[str], packages_to_remove: List[str]
    ) -> List[str]:
        """从导言区行列表中移除指定宏包的 \\usepackage 行。"""
        remove_set = set(packages_to_remove)
        result: List[str] = []
        for line in lines:
            # 检查这行是否是 \usepackage{target} 或 \usepackage{..., target, ...}
            m = re.search(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", line)
            if m:
                pkgs_in_line = [
                    p.strip() for p in m.group(1).split(",")
                ]
                remaining = [p for p in pkgs_in_line if p not in remove_set]
                if not remaining:
                    # 整行删除
                    continue
                elif remaining != pkgs_in_line:
                    # 部分删除，重建该行
                    new_pkg_str = ", ".join(remaining)
                    line = re.sub(
                        r"(\\usepackage(?:\[[^\]]*\])?\{)[^}]+(\})",
                        rf"\g<1>{new_pkg_str}\g<2>",
                        line,
                    )
            result.append(line)
        return result

    def _add_packages(
        self, lines: List[str], packages_to_add: List[str]
    ) -> List[str]:
        """向导言区添加宏包声明。"""
        existing = self.get_package_names()
        to_add = [p for p in packages_to_add if p not in existing]
        if not to_add:
            return lines

        # 找到最后一个 \usepackage 行的索引
        last_usepackage_idx = -1
        for i, line in enumerate(lines):
            if re.search(r"\\usepackage", line):
                last_usepackage_idx = i

        insert_lines = []
        # 检查哪些是加载顺序敏感的
        sensitive = [p for p in to_add if p in LOAD_ORDER_SENSITIVE]
        normal = [p for p in to_add if p not in LOAD_ORDER_SENSITIVE]

        for pkg_name in normal:
            insert_lines.append(f"\\usepackage{{{pkg_name}}}")

        if last_usepackage_idx >= 0:
            # 在最后一个 \usepackage 之后插入普通宏包
            insert_pos = last_usepackage_idx + 1
            lines = (
                lines[:insert_pos]
                + insert_lines
                + lines[insert_pos:]
            )
        else:
            # 没有现有 \usepackage，在 documentclass 之后插入
            dc_idx = -1
            for i, line in enumerate(lines):
                if "\\documentclass" in line:
                    dc_idx = i
                    break
            lines = (
                lines[:dc_idx + 1]
                + [""] + insert_lines
                + lines[dc_idx + 1:]
            )

        # 加载顺序敏感的宏包追加到导言区末尾
        for pkg_name in sensitive:
            lines.append(f"\\usepackage{{{pkg_name}}}")

        return lines

    def _apply_font_settings(
        self, lines: List[str], font_settings: Dict[str, str]
    ) -> List[str]:
        """应用字体设置到导言区。"""
        # 确保 fontspec 已加载
        has_fontspec = any(
            "fontspec" in line for line in lines
        )
        if not has_fontspec:
            # 在合适位置插入 fontspec
            insert_idx = 0
            for i, line in enumerate(lines):
                if "\\usepackage" in line:
                    insert_idx = i + 1
            lines = (
                lines[:insert_idx]
                + ["\\usepackage{fontspec}"]
                + lines[insert_idx:]
            )

        font_commands: Dict[str, str] = {
            "main_font": "\\setmainfont",
            "sans_font": "\\setsansfont",
            "mono_font": "\\setmonofont",
            "cjk_font": "\\setCJKmainfont",
        }

        new_lines: List[str] = []
        existing_keys_set: set = set()

        for line in lines:
            # 移除旧的字体设置
            is_font_line = False
            for key, cmd in font_commands.items():
                if cmd in line:
                    is_font_line = True
                    existing_keys_set.add(key)
                    break
            if not is_font_line:
                new_lines.append(line)

        # 添加新的字体设置
        font_lines: List[str] = []
        for key, font_name in font_settings.items():
            cmd = font_commands.get(key)
            if cmd:
                font_lines.append(f"{cmd}{{{font_name}}}")
        new_lines.extend(font_lines)
        return new_lines

    def _apply_line_spacing(
        self, lines: List[str], line_spacing: float
    ) -> List[str]:
        """应用行间距设置。"""
        # 移除旧的行距设置
        lines = [
            l for l in lines
            if "\\linespread" not in l
            and "\\setstretch" not in l
        ]
        lines.append(f"\\linespread{{{line_spacing}}}")
        return lines

    def save(self, new_content: str) -> None:
        """将修改后的内容写入原文件。"""
        _safe_write_file(self.filepath, new_content)
        # 重新解析以确保状态一致
        self.raw_content = new_content
        self.preamble_info = self._extract_preamble_info()
        self._body_content = self._extract_body()

    def save_backup(self) -> str:
        """创建当前文件的备份并返回备份路径。"""
        backup_path = self.filepath + f".bak.{int(time.time())}"
        shutil.copy2(self.filepath, backup_path)
        return backup_path


# ============================================================================
# LatexCompiler: 静默编译
# ============================================================================

class LatexCompiler:
    """
    LaTeX 编译器。

    职责：
      - 自动发现系统中可用的 LaTeX 引擎
      - 后台静默编译（nonstopmode）
      - 捕获 stdout/stderr 与 .log 文件内容
      - 支持超时控制
    """

    # 编译器优先级
    ENGINE_PRIORITY = ["xelatex", "lualatex", "latexmk", "pdflatex"]

    def __init__(self, compiler: str = "auto", timeout: int = 60):
        self.compiler = compiler
        self.timeout = timeout
        self._engine_path: Optional[str] = None
        self._engine_name: str = ""

    # ------------------------------------------------------------------
    # 编译器发现
    # ------------------------------------------------------------------

    def find_engine(self) -> Tuple[str, str]:
        """
        查找可用的 LaTeX 引擎。

        返回 (engine_name, engine_path)。

        抛出 LatexCompilerNotFoundError 如果找不到。
        """
        if self.compiler != "auto":
            path = _find_executable(self.compiler)
            if path:
                self._engine_name = self.compiler
                self._engine_path = path
                return (self._engine_name, self._engine_path)
            raise LatexCompilerNotFoundError(
                f"指定的编译器 '{self.compiler}' 未在 PATH 中找到。"
                f"请安装 TeX Live / MiKTeX 或将编译器添加到 PATH。"
            )

        for engine in self.ENGINE_PRIORITY:
            path = _find_executable(engine)
            if path:
                self._engine_name = engine
                self._engine_path = path
                return (self._engine_name, self._engine_path)

        raise LatexCompilerNotFoundError(
            "未找到任何 LaTeX 编译器。请安装 TeX Live 或 MiKTeX。\n"
            f"自动搜索的编译器: {', '.join(self.ENGINE_PRIORITY)}"
        )

    # ------------------------------------------------------------------
    # 编译
    # ------------------------------------------------------------------

    def compile(self, filepath: str) -> Dict[str, Any]:
        """
        静默编译 .tex 文件。

        参数：
          filepath: .tex 文件绝对路径

        返回：
          {
            "success": bool,
            "pdf_path": str | None,
            "log_content": str,
            "stdout": str,
            "stderr": str,
            "elapsed_seconds": float,
            "engine": str,
            "command": str,
          }
        """
        if not self._engine_path:
            self.find_engine()

        filepath = os.path.abspath(filepath)
        work_dir = os.path.dirname(filepath)
        base_name = os.path.splitext(os.path.basename(filepath))[0]

        # 构建编译命令
        cmd = self._build_command(filepath)

        start_time = time.perf_counter()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=work_dir,
                env={**os.environ, "LANG": "en_US.UTF-8"},
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "pdf_path": None,
                "log_content": "",
                "stdout": "",
                "stderr": f"编译超时 (>{self.timeout} 秒)",
                "elapsed_seconds": self.timeout,
                "engine": self._engine_name,
                "command": " ".join(shlex.quote(c) for c in cmd),
            }
        except FileNotFoundError:
            raise LatexCompilerNotFoundError(
                f"编译器 '{self._engine_name}' 执行失败，可能已被卸载。"
            )

        elapsed = time.perf_counter() - start_time

        # 读取 .log 文件
        log_path = os.path.join(work_dir, f"{base_name}.log")
        log_content = ""
        if os.path.isfile(log_path):
            log_content = _safe_read_file(log_path)

        # 检查 PDF 是否生成
        pdf_path = os.path.join(work_dir, f"{base_name}.pdf")
        pdf_generated = os.path.isfile(pdf_path)

        success = result.returncode == 0 and pdf_generated

        return {
            "success": success,
            "pdf_path": pdf_path if pdf_generated else None,
            "log_content": log_content,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "elapsed_seconds": round(elapsed, 2),
            "engine": self._engine_name,
            "command": " ".join(shlex.quote(c) for c in cmd),
        }

    def _build_command(self, filepath: str) -> List[str]:
        """构建编译器命令行参数。"""
        if not self._engine_path:
            self.find_engine()

        base_name = os.path.splitext(os.path.basename(filepath))[0]

        if self._engine_name == "latexmk":
            return [
                self._engine_path,
                "-pdf",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-silent",
                "-jobname=" + base_name,
                filepath,
            ]

        # xelatex / lualatex / pdflatex
        return [
            self._engine_path,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-jobname=" + base_name,
            filepath,
        ]

    def clean_aux(self, filepath: str) -> List[str]:
        """清理编译辅助文件，返回被删除的文件路径列表。"""
        work_dir = os.path.dirname(os.path.abspath(filepath))
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        aux_extensions = [".aux", ".log", ".out", ".toc", ".lof", ".lot",
                          ".bbl", ".blg", ".nav", ".snm", ".vrb", ".synctex.gz",
                          ".fls", ".fdb_latexmk"]
        removed: List[str] = []
        for ext in aux_extensions:
            aux_path = os.path.join(work_dir, base_name + ext)
            if os.path.isfile(aux_path):
                try:
                    os.unlink(aux_path)
                    removed.append(aux_path)
                except OSError:
                    pass
        return removed


# ============================================================================
# LatexErrorParser: .log 错误提取与分类
# ============================================================================

@dataclass
class LatexError:
    """单个 LaTeX 错误的抽象。"""
    line: int = 0
    message: str = ""
    context: str = ""
    is_fatal: bool = False
    fatal_signal: Optional[str] = None
    raw_block: str = ""


class LatexErrorParser:
    """
    LaTeX .log 文件错误解析器。

    职责：
      - 从 .log 内容中提取所有编译错误
      - 过滤 overfull/underfull/font warning 等噪声
      - 分类致命错误（字体缺失等）
      - 提供结构化错误摘要
    """

    def __init__(self, log_content: str):
        self.log_content = log_content
        self.errors: List[LatexError] = []
        self.has_fatal: bool = False
        self.fatal_signal: Optional[str] = None

    # ------------------------------------------------------------------
    # 主要解析接口
    # ------------------------------------------------------------------

    def parse(self) -> List[LatexError]:
        """解析 .log 文件，返回过滤后的错误列表。"""
        raw_errors = self._extract_error_blocks()
        self.errors = []
        self.has_fatal = False
        self.fatal_signal = None

        for raw_block in raw_errors:
            error = self._classify_error(raw_block)
            if error:
                if error.is_fatal:
                    self.has_fatal = True
                    self.fatal_signal = error.fatal_signal
                self.errors.append(error)

        return self.errors

    # ------------------------------------------------------------------
    # 错误块提取
    # ------------------------------------------------------------------

    def _extract_error_blocks(self) -> List[str]:
        """
        从原始 .log 中提取错误块。

        LaTeX 错误以 `!` 开头，持续到下一个 `!` 或文件结束。
        忽略以 `!` 开头但只是警告的行。
        """
        if not self.log_content:
            return []

        lines = self.log_content.split("\n")
        error_blocks: List[str] = []
        current_block: List[str] = []
        in_error = False

        for i, line in enumerate(lines):
            if line.startswith("!"):
                # 检查是否是真实错误而非噪声
                if LATEX_ERROR_MARKER.search(line):
                    if current_block:
                        error_blocks.append("\n".join(current_block))
                    current_block = [line]
                    in_error = True
                elif in_error:
                    # 可能仍然属于前一个错误块
                    current_block.append(line)
            elif in_error:
                current_block.append(line)
                # 连续空行意味着错误块结束
                empty_count = sum(
                    1 for l in current_block[-3:] if l.strip() == ""
                )
                if empty_count >= 2 or len(current_block) > 20:
                    error_blocks.append("\n".join(current_block))
                    current_block = []
                    in_error = False

        if current_block and in_error:
            error_blocks.append("\n".join(current_block))

        return error_blocks

    # ------------------------------------------------------------------
    # 错误分类
    # ------------------------------------------------------------------

    def _classify_error(self, raw_block: str) -> Optional[LatexError]:
        """对单个错误块进行分类。"""
        # 首先检查是否只是噪声
        if self._is_noise(raw_block):
            return None

        lines = raw_block.strip().split("\n")
        if not lines:
            return None

        first_line = lines[0]
        context = "\n".join(lines[1:11])  # 最多取 10 行上下文

        # 提取行号
        line_num = self._extract_line_number(raw_block)

        # 提取核心错误消息
        message = first_line.lstrip("! ").strip()

        # 检查致命错误
        is_fatal = False
        fatal_signal = None
        combined_text = raw_block
        for signal, pattern in FATAL_ERROR_PATTERNS.items():
            if pattern.search(combined_text):
                is_fatal = True
                fatal_signal = signal
                break

        return LatexError(
            line=line_num,
            message=message,
            context=context,
            is_fatal=is_fatal,
            fatal_signal=fatal_signal,
            raw_block=raw_block,
        )

    def _is_noise(self, block: str) -> bool:
        """检查错误块是否为可忽略的噪声。"""
        for pattern in NOISE_PATTERNS:
            if pattern.search(block):
                return True

        # 检查块中第一行是否以 ! 开头
        first_line = block.strip().split("\n")[0] if block.strip() else ""
        if not first_line.startswith("!"):
            return True

        return False

    def _extract_line_number(self, block: str) -> int:
        """从错误块中提取行号。"""
        # LaTeX 错误格式: l.123 ... 或 line 123
        m = re.search(r"l\.(\d+)", block)
        if m:
            return int(m.group(1))

        m = re.search(r"line\s+(\d+)", block, re.IGNORECASE)
        if m:
            return int(m.group(1))

        return 0

    # ------------------------------------------------------------------
    # 输出接口
    # ------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        """生成错误的 JSON 友好摘要。"""
        return {
            "total_errors": len(self.errors),
            "fatal_signal": self.fatal_signal,
            "has_fatal": self.has_fatal,
            "errors": [
                {
                    "line": e.line,
                    "message": e.message,
                    "context": e.context[:500],  # 限制输出长度
                    "is_fatal": e.is_fatal,
                    "fatal_signal": e.fatal_signal,
                }
                for e in self.errors
            ],
        }

    def format_for_ai(self) -> str:
        """生成适合 AI 阅读的纯文本错误摘要。"""
        if not self.errors:
            return "✅ 编译成功，未发现 LaTeX 错误。"

        lines: List[str] = [f"❌ 发现 {len(self.errors)} 个编译错误:\n"]
        for i, err in enumerate(self.errors, 1):
            fatal_tag = " [🔴 致命]" if err.is_fatal else ""
            lines.append(
                f"--- 错误 {i}{fatal_tag} ---\n"
                f"  位置: l.{err.line}\n"
                f"  信息: {err.message}\n"
            )
            if err.context:
                lines.append(f"  上下文:\n{err.context}")
            lines.append("")
        return "\n".join(lines)


# ============================================================================
# SystemFontChecker: 系统字体查询
# ============================================================================

class SystemFontChecker:
    """
    系统字体可用性检查器。

    职责：
      - 列出系统中已安装的字体
      - 检查指定字体名称是否可用
      - 提供模糊匹配建议
    """

    def __init__(self):
        self._platform = sys.platform

    def list_fonts(self) -> List[str]:
        """列出系统已安装字体名称列表。"""
        if self._platform == "win32":
            return self._list_fonts_windows()
        elif self._platform == "darwin":
            return self._list_fonts_macos()
        else:
            return self._list_fonts_linux()

    def check_font(self, font_name: str) -> Dict[str, Any]:
        """
        检查指定字体是否已安装。

        返回:
          {
            "available": bool,
            "font_name": str,
            "exact_match": bool,
            "suggestions": List[str],  # 可用的相似字体名
          }
        """
        all_fonts = self.list_fonts()
        font_lower = font_name.lower().strip()

        # 精确匹配
        for f in all_fonts:
            if f.lower().strip() == font_lower:
                return {
                    "available": True,
                    "font_name": f,
                    "exact_match": True,
                    "suggestions": [],
                }

        # 模糊匹配
        suggestions: List[str] = []
        for f in all_fonts:
            f_lower = f.lower()
            # 部分匹配
            if font_lower in f_lower or f_lower in font_lower:
                suggestions.append(f)

        return {
            "available": len(suggestions) > 0,
            "font_name": font_name,
            "exact_match": False,
            "suggestions": suggestions[:10],
        }

    def _list_fonts_windows(self) -> List[str]:
        """Windows: 通过 PowerShell 查询已安装字体。"""
        ps_cmd = (
            "powershell -NoProfile -Command "
            "\"[System.Reflection.Assembly]::LoadWithPartialName('System.Drawing');"
            "(New-Object System.Drawing.Text.InstalledFontCollection).Families | "
            "ForEach-Object { $_.Name }\""
        )
        try:
            result = subprocess.run(
                ps_cmd, shell=True, capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                fonts = [
                    line.strip()
                    for line in result.stdout.split("\n")
                    if line.strip()
                ]
                return sorted(set(fonts))
        except (subprocess.TimeoutExpired, OSError):
            pass
        return []

    def _list_fonts_macos(self) -> List[str]:
        """macOS: 通过 system_profiler 查询字体。"""
        try:
            result = subprocess.run(
                ["system_profiler", "SPFontsDataType"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                fonts = re.findall(
                    r"Family:\s*(.+)", result.stdout, re.IGNORECASE
                )
                return sorted(set(f.strip() for f in fonts if f.strip()))
        except (subprocess.TimeoutExpired, OSError):
            pass

        # 备用：检查常见字体路径
        font_dirs = [
            "/System/Library/Fonts/",
            "/Library/Fonts/",
            os.path.expanduser("~/Library/Fonts/"),
        ]
        fonts: List[str] = []
        for d in font_dirs:
            if os.path.isdir(d):
                for entry in os.listdir(d):
                    if entry.lower().endswith((".ttf", ".otf", ".ttc", ".dfont")):
                        name = os.path.splitext(entry)[0]
                        fonts.append(name)
        return sorted(set(fonts))

    def _list_fonts_linux(self) -> List[str]:
        """Linux: 通过 fc-list 查询字体。"""
        if not _find_executable("fc-list"):
            return []

        try:
            result = subprocess.run(
                ["fc-list", ":lang=zh", "--format=%{family}\n"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                fonts = [
                    line.strip().split(",")[0].strip()
                    for line in result.stdout.split("\n")
                    if line.strip()
                ]
                return sorted(set(fonts))
        except (subprocess.TimeoutExpired, OSError):
            pass
        return []


# ============================================================================
# LatexOptimizer: 主编排器
# ============================================================================

class LatexOptimizer:
    """
    LaTeX Skill 主编排器。

    整合 LatexProject、LatexCompiler、LatexErrorParser、SystemFontChecker，
    对外提供统一的 run() 接口。
    """

    def __init__(
        self,
        filepath: str,
        action_type: str,
        user_prompt: Optional[str] = None,
        modifications: Optional[Dict[str, Any]] = None,
        compiler: str = "auto",
        timeout: int = 60,
    ):
        self.filepath = os.path.abspath(filepath)
        self.action_type = action_type
        self.user_prompt = user_prompt or ""
        self.modifications = modifications or {}
        self.compiler_choice = compiler
        self.timeout = timeout

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """执行操作并返回结构化结果。"""
        try:
            if self.action_type == "analyze":
                return self._action_analyze()
            elif self.action_type == "compile":
                return self._action_compile()
            elif self.action_type == "modify_preamble":
                return self._action_modify()
            elif self.action_type == "full_optimize":
                return self._action_full_optimize()
            elif self.action_type == "check_fonts":
                return self._action_check_fonts()
            else:
                return self._error_response(
                    f"未知的 action_type: '{self.action_type}'。"
                    f"可选值: analyze, compile, modify_preamble, full_optimize, check_fonts"
                )
        except LatexFatalError as e:
            return self._fatal_response(e.signal, str(e))
        except LatexFileNotFoundError as e:
            return self._error_response(f"文件未找到: {e}")
        except LatexCompilerNotFoundError as e:
            return self._fatal_response("COMPILER_NOT_FOUND", str(e))
        except LatexPreambleError as e:
            return self._error_response(f"导言区错误: {e}")
        except LatexOptimizerError as e:
            return self._error_response(str(e))
        except OSError as e:
            return self._error_response(f"系统错误: {e}")
        except Exception as e:
            return self._error_response(
                f"未预期的错误 ({type(e).__name__}): {e}"
            )

    # ------------------------------------------------------------------
    # Action: analyze
    # ------------------------------------------------------------------

    def _action_analyze(self) -> Dict[str, Any]:
        """解析导言区结构。"""
        project = LatexProject(self.filepath)
        info = project.get_preamble_info()

        return {
            "success": True,
            "action": "analyze",
            "data": {
                "filepath": self.filepath,
                "document_class": info.document_class,
                "class_options": info.class_options,
                "packages": info.packages,
                "package_names": [p["name"] for p in info.packages],
                "custom_commands": info.custom_commands,
                "font_settings": info.font_settings,
                "preamble_line_range": [
                    info.preamble_start_line,
                    info.preamble_end_line,
                ],
                "body_start_line": info.body_start_line,
                "raw_preamble_preview": info.raw_preamble[:2000],
            },
            "errors": [],
            "fatal_signal": None,
        }

    # ------------------------------------------------------------------
    # Action: compile
    # ------------------------------------------------------------------

    def _action_compile(self) -> Dict[str, Any]:
        """静默编译并返回结果。"""
        compiler_obj = LatexCompiler(
            compiler=self.compiler_choice, timeout=self.timeout
        )
        compile_result = compiler_obj.compile(self.filepath)

        # 解析错误
        error_parser = LatexErrorParser(compile_result["log_content"])
        error_parser.parse()
        error_summary = error_parser.get_summary()

        response: Dict[str, Any] = {
            "success": compile_result["success"] and not error_parser.has_fatal,
            "action": "compile",
            "data": {
                "filepath": self.filepath,
                "pdf_path": compile_result["pdf_path"],
                "engine": compile_result["engine"],
                "elapsed_seconds": compile_result["elapsed_seconds"],
                "command": compile_result["command"],
            },
            "errors": error_summary["errors"],
            "fatal_signal": error_summary["fatal_signal"],
            "compiler_output": (
                compile_result["stdout"][:2000]
                if compile_result["stdout"]
                else compile_result["stderr"][:2000]
            ),
        }

        if error_parser.has_fatal:
            response["success"] = False

        return response

    # ------------------------------------------------------------------
    # Action: modify_preamble
    # ------------------------------------------------------------------

    def _action_modify(self) -> Dict[str, Any]:
        """安全修改导言区并编译验证。"""
        project = LatexProject(self.filepath)

        # 在执行修改前先检查字体（如果指定了）
        font_settings = self.modifications.get("font_settings", {})
        font_issues: List[Dict[str, Any]] = []
        if font_settings:
            font_checker = SystemFontChecker()
            for font_key, font_name in font_settings.items():
                check_result = font_checker.check_font(font_name)
                if not check_result["available"]:
                    font_issues.append({
                        "font_key": font_key,
                        "font_name": font_name,
                        "available": False,
                        "suggestions": check_result.get("suggestions", []),
                    })

        # 如果有字体缺失，直接返回致命错误
        if font_issues:
            return {
                "success": False,
                "action": "modify_preamble",
                "data": {
                    "filepath": self.filepath,
                    "font_issues": font_issues,
                    "message": (
                        "❌ 检测到字体缺失！以下字体未在系统中找到，"
                        "请先安装这些字体或选择替代字体:\n" +
                        "\n".join(
                            f"  • {f['font_name']} (用途: {f['font_key']})"
                            f" — 建议: {', '.join(f['suggestions'][:3]) or '无相似字体'}"
                            for f in font_issues
                        )
                    ),
                },
                "errors": [],
                "fatal_signal": "FONT_NOT_FOUND",
            }

        # 检查宏包冲突
        packages_to_add = self.modifications.get("packages_to_add", [])
        conflicts = project.detect_conflicts(packages_to_add)
        if conflicts:
            return {
                "success": False,
                "action": "modify_preamble",
                "data": {
                    "filepath": self.filepath,
                    "conflicts": conflicts,
                    "message": (
                        "⚠️ 检测到宏包冲突！请调整宏包选择:\n" +
                        "\n".join(f"  • {c['message']}" for c in conflicts)
                    ),
                },
                "errors": [],
                "fatal_signal": None,
            }

        # 创建备份
        backup_path = project.save_backup()

        # 执行修改
        try:
            new_content = project.modify_preamble(
                packages_to_add=self.modifications.get("packages_to_add"),
                packages_to_remove=self.modifications.get("packages_to_remove"),
                font_settings=self.modifications.get("font_settings"),
                line_spacing=self.modifications.get("line_spacing"),
                raw_injections=self.modifications.get("raw_injections"),
            )
        except Exception as e:
            return {
                "success": False,
                "action": "modify_preamble",
                "data": {
                    "filepath": self.filepath,
                    "backup_path": backup_path,
                    "message": f"修改导言区时发生错误: {e}\n已自动备份原文件至: {backup_path}",
                },
                "errors": [],
                "fatal_signal": None,
            }

        # 写入修改
        project.save(new_content)

        # 编译验证
        compiler_obj = LatexCompiler(
            compiler=self.compiler_choice, timeout=self.timeout
        )
        compile_result = compiler_obj.compile(self.filepath)

        error_parser = LatexErrorParser(compile_result["log_content"])
        error_parser.parse()
        error_summary = error_parser.get_summary()

        # 如果编译失败且非致命，可以选择回滚
        compiled_ok = compile_result["success"] and not error_parser.has_fatal

        return {
            "success": compiled_ok,
            "action": "modify_preamble",
            "data": {
                "filepath": self.filepath,
                "backup_path": backup_path,
                "pdf_path": compile_result["pdf_path"],
                "engine": compile_result["engine"],
                "elapsed_seconds": compile_result["elapsed_seconds"],
                "added_packages": packages_to_add,
                "rollback_available": not compiled_ok,
                "rollback_instruction": (
                    f"修改导致编译失败。要回滚，请运行:\n"
                    f"  cp {backup_path} {self.filepath}"
                    if not compiled_ok else None
                ),
            },
            "errors": error_summary["errors"],
            "fatal_signal": error_summary["fatal_signal"],
            "compiler_output": compile_result.get("stdout", "")[:2000],
        }

    # ------------------------------------------------------------------
    # Action: full_optimize
    # ------------------------------------------------------------------

    def _action_full_optimize(self) -> Dict[str, Any]:
        """
        端到端优化：先分析，返回上下文供 AI 决策，
        然后 AI 应再次调用 modify_preamble 执行实际修改。

        注：此 action 本身不执行修改，它返回完整的分析结果 +
        AI 需要的上下文，让 AI 根据 user_prompt 生成精准的 modifications。
        """
        # Step 1: 分析
        analysis_result = self._action_analyze()

        # Step 2: 编译检查当前状态
        compile_result = self._action_compile()

        # Step 3: 检查系统字体
        font_checker = SystemFontChecker()
        available_fonts = font_checker.list_fonts()

        return {
            "success": True,
            "action": "full_optimize",
            "data": {
                "filepath": self.filepath,
                "analysis": analysis_result["data"],
                "current_compile_status": {
                    "success": compile_result["success"],
                    "errors": compile_result["errors"],
                    "fatal_signal": compile_result["fatal_signal"],
                },
                "system_info": {
                    "available_fonts_sample": available_fonts[:50],
                    "total_fonts": len(available_fonts),
                    "platform": sys.platform,
                },
                "user_prompt": self.user_prompt,
                "instruction_to_ai": (
                    "请根据以上分析结果和 user_prompt，生成精确的 modifications 对象，"
                    "然后调用 modify_preamble action 执行修改。\n"
                    "注意:\n"
                    "1. 只添加必要的宏包，避免与已有宏包冲突\n"
                    "2. 字体名称必须与系统可用字体完全匹配\n"
                    "3. 如果用户要求中文字体但系统不支持，应提示用户安装字体"
                ),
            },
            "errors": compile_result["errors"],
            "fatal_signal": compile_result["fatal_signal"],
        }

    # ------------------------------------------------------------------
    # Action: check_fonts
    # ------------------------------------------------------------------

    def _action_check_fonts(self) -> Dict[str, Any]:
        """检查系统字体可用性。"""
        font_checker = SystemFontChecker()
        all_fonts = font_checker.list_fonts()

        # 如果 user_prompt 中有字体名称，检测它
        font_checks: List[Dict[str, Any]] = []
        if self.user_prompt:
            # 尝试从 prompt 中提取字体名称
            potential_fonts = re.findall(
                r"[一-鿿\w\s]+体|"
                r"[A-Za-z][\w\s]*(?:Sans|Serif|Mono|Hei|Song|Kai|Ming|Fang)",
                self.user_prompt,
            )
            for fn in potential_fonts[:5]:
                font_checks.append(font_checker.check_font(fn.strip()))

        return {
            "success": True,
            "action": "check_fonts",
            "data": {
                "total_fonts": len(all_fonts),
                "fonts_sample": all_fonts[:100],
                "platform": sys.platform,
                "font_checks": font_checks,
            },
            "errors": [],
            "fatal_signal": None,
        }

    # ------------------------------------------------------------------
    # 响应工具
    # ------------------------------------------------------------------

    @staticmethod
    def _error_response(message: str) -> Dict[str, Any]:
        return {
            "success": False,
            "action": "error",
            "data": {"message": message},
            "errors": [],
            "fatal_signal": None,
        }

    @staticmethod
    def _fatal_response(signal: str, message: str) -> Dict[str, Any]:
        return {
            "success": False,
            "action": "fatal",
            "data": {
                "message": message,
                "rollback_hint": (
                    "请检查以下问题后重试:\n"
                    f"  致命信号: {signal}\n"
                    f"  详情: {message}\n"
                    "如已对文件做了修改，请从 .bak.* 备份文件恢复。"
                ),
            },
            "errors": [],
            "fatal_signal": signal,
        }


# ============================================================================
# CLI 入口
# ============================================================================

def _parse_stdin() -> Dict[str, Any]:
    """从 stdin 解析 JSON 输入。"""
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({
            "success": False,
            "action": "error",
            "data": {"message": "没有收到输入。请通过 stdin 传入 JSON。"},
            "errors": [],
            "fatal_signal": None,
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    try:
        params = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({
            "success": False,
            "action": "error",
            "data": {"message": f"输入不是合法的 JSON: {e}"},
            "errors": [],
            "fatal_signal": None,
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    return params


def main() -> None:
    """CLI 主入口：从 stdin 读取 JSON，执行操作，输出 JSON 到 stdout。"""
    params = _parse_stdin()

    filepath = params.get("filepath", "")
    action_type = params.get("action_type", "")
    user_prompt = params.get("user_prompt", "")
    modifications = params.get("modifications", {})
    compiler = params.get("compiler", "auto")
    timeout = params.get("timeout", 60)

    # 参数验证
    if not filepath:
        print(json.dumps({
            "success": False,
            "action": "error",
            "data": {"message": "缺少必需参数 'filepath'"},
            "errors": [],
            "fatal_signal": None,
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    if not action_type:
        print(json.dumps({
            "success": False,
            "action": "error",
            "data": {"message": "缺少必需参数 'action_type'"},
            "errors": [],
            "fatal_signal": None,
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    optimizer = LatexOptimizer(
        filepath=filepath,
        action_type=action_type,
        user_prompt=user_prompt,
        modifications=modifications,
        compiler=compiler,
        timeout=int(timeout),
    )

    result = optimizer.run()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

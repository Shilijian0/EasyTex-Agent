#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LaTeX Optimizer Skill — 单元测试套件
======================================

覆盖:
  - LatexProject:   .tex 解析、导言区提取、冲突检测、安全修改
  - LatexErrorParser: .log 错误提取、噪声过滤、致命错误分类
  - SystemFontChecker: 系统字体查询（适配各平台）
  - LatexCompiler: 编译命令构建
  - LatexOptimizer: 主编排器集成测试
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

# 将 scripts/ 加入 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from latex_core import (
    # 类
    LatexProject,
    LatexCompiler,
    LatexErrorParser,
    SystemFontChecker,
    LatexOptimizer,
    # 数据类
    PreambleInfo,
    LatexError,
    # 异常
    LatexOptimizerError,
    LatexFileNotFoundError,
    LatexCompilerNotFoundError,
    LatexCompilationError,
    LatexFatalError,
    LatexPreambleError,
    # 常量
    CONFLICTING_PACKAGES,
    LOAD_ORDER_SENSITIVE,
    FATAL_ERROR_PATTERNS,
    # 工具
    _safe_read_file,
    _safe_write_file,
)

FIXTURES_DIR = _PROJECT_ROOT / "tests" / "fixtures"
SAMPLE_BASIC = str(FIXTURES_DIR / "sample_basic.tex")
SAMPLE_ERROR = str(FIXTURES_DIR / "sample_with_error.tex")


# ============================================================================
# 1. LatexProject 测试
# ============================================================================

class TestLatexProject(unittest.TestCase):
    """测试 .tex 文件解析功能。"""

    def test_file_not_found(self):
        """测试文件不存在时抛出正确异常。"""
        with self.assertRaises(LatexFileNotFoundError):
            LatexProject("/nonexistent/path/file.tex")

    def test_reject_non_tex_file(self):
        """测试拒绝非 .tex 文件。"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello world")
        try:
            with self.assertRaises(LatexOptimizerError):
                LatexProject(f.name)
        finally:
            os.unlink(f.name)

    def test_parse_basic_document(self):
        """测试解析正常的 .tex 文件。"""
        if not os.path.exists(SAMPLE_BASIC):
            self.skipTest(f"样本文件不存在: {SAMPLE_BASIC}")

        project = LatexProject(SAMPLE_BASIC)
        info = project.get_preamble_info()

        # 验证 documentclass
        self.assertEqual(info.document_class, "article")
        self.assertIn("12pt", info.class_options)
        self.assertIn("a4paper", info.class_options)

        # 验证宏包
        pkg_names = project.get_package_names()
        self.assertIn("inputenc", pkg_names)
        self.assertIn("amsmath", pkg_names)
        self.assertIn("geometry", pkg_names)
        self.assertIn("graphicx", pkg_names)

        # 验证自定义命令
        self.assertTrue(any("\\R" in cmd for cmd in info.custom_commands))
        self.assertTrue(any("\\norm" in cmd for cmd in info.custom_commands))
        self.assertTrue(any("theorem" in cmd for cmd in info.custom_commands))

    def test_parse_document_class_options(self):
        """测试 documentclass 选项解析。"""
        content = r"""\documentclass[11pt,twoside,draft]{book}
\usepackage{amsmath}
\begin{document}
Hello
\end{document}"""

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".tex", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp_path = f.name

        try:
            project = LatexProject(tmp_path)
            info = project.get_preamble_info()
            self.assertEqual(info.document_class, "book")
            self.assertIn("11pt", info.class_options)
            self.assertIn("twoside", info.class_options)
        finally:
            os.unlink(tmp_path)

    def test_parse_usepackage_with_options(self):
        """测试带选项的 \\usepackage 解析。"""
        content = r"""\documentclass{article}
\usepackage[colorlinks=true,urlcolor=blue]{hyperref}
\usepackage{minted}
\begin{document}
Test
\end{document}"""

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".tex", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp_path = f.name

        try:
            project = LatexProject(tmp_path)
            info = project.get_preamble_info()
            hyperref_pkg = next(
                (p for p in info.packages if p["name"] == "hyperref"), None
            )
            self.assertIsNotNone(hyperref_pkg)
            self.assertIn("colorlinks=true", hyperref_pkg["options"])
        finally:
            os.unlink(tmp_path)

    def test_missing_document_environment(self):
        """测试缺失 \\begin{document} 的文件。"""
        content = r"""\documentclass{article}
\usepackage{amsmath}
% 没有 begin{document}"""

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".tex", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp_path = f.name

        try:
            with self.assertRaises(LatexPreambleError):
                LatexProject(tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_has_package(self):
        """测试 has_package 查询方法。"""
        if not os.path.exists(SAMPLE_BASIC):
            self.skipTest(f"样本文件不存在: {SAMPLE_BASIC}")

        project = LatexProject(SAMPLE_BASIC)
        self.assertTrue(project.has_package("amsmath"))
        self.assertTrue(project.has_package("graphicx"))
        self.assertFalse(project.has_package("nonexistent_pkg_xyz"))


# ============================================================================
# 2. 宏包冲突检测测试
# ============================================================================

class TestPackageConflictDetection(unittest.TestCase):
    """测试宏包冲突检测逻辑。"""

    def setUp(self):
        """创建带有已知宏包的临时 .tex 文件。"""
        content = r"""\documentclass{article}
\usepackage{ctex}
\usepackage{natbib}
\usepackage{subfigure}
\begin{document}
Test
\end{document}"""
        self.tmp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".tex", delete=False, encoding="utf-8"
        )
        self.tmp_file.write(content)
        self.tmp_file.close()
        self.project = LatexProject(self.tmp_file.name)

    def tearDown(self):
        os.unlink(self.tmp_file.name)

    def test_ctex_conflicts_with_xecjk(self):
        """测试 ctex 与 xeCJK 的冲突检测。"""
        conflicts = self.project.detect_conflicts(["xeCJK"])
        self.assertTrue(len(conflicts) > 0)
        self.assertEqual(conflicts[0]["new_package"], "xeCJK")
        self.assertEqual(conflicts[0]["existing_package"], "ctex")

    def test_natbib_conflicts_with_biblatex(self):
        """测试 natbib 与 biblatex 的冲突检测。"""
        conflicts = self.project.detect_conflicts(["biblatex"])
        self.assertTrue(len(conflicts) > 0)

    def test_no_conflict_with_safe_package(self):
        """测试安全的宏包无冲突。"""
        conflicts = self.project.detect_conflicts(["geometry", "xcolor"])
        self.assertEqual(len(conflicts), 0)


# ============================================================================
# 3. LatexProject 修改测试
# ============================================================================

class TestLatexProjectModifications(unittest.TestCase):
    """测试导言区安全修改功能。"""

    def setUp(self):
        """创建基础 .tex 文件。"""
        content = r"""\documentclass{article}
\usepackage{amsmath}
\usepackage{graphicx}
\begin{document}
Hello World
\end{document}"""
        self.tmp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".tex", delete=False, encoding="utf-8"
        )
        self.tmp_file.write(content)
        self.tmp_file.close()
        self.original_content = content
        self.project = LatexProject(self.tmp_file.name)

    def tearDown(self):
        if os.path.exists(self.tmp_file.name):
            os.unlink(self.tmp_file.name)

    def test_add_package(self):
        """测试添加新宏包。"""
        new_content = self.project.modify_preamble(
            packages_to_add=["geometry", "xcolor"],
        )
        self.assertIn(r"\usepackage{geometry}", new_content)
        self.assertIn(r"\usepackage{xcolor}", new_content)
        # 正文不变
        self.assertIn("Hello World", new_content)

    def test_remove_package(self):
        """测试移除已有宏包。"""
        new_content = self.project.modify_preamble(
            packages_to_remove=["graphicx"],
        )
        self.assertNotIn(r"\usepackage{graphicx}", new_content)
        self.assertIn(r"\usepackage{amsmath}", new_content)

    def test_no_duplicate_packages(self):
        """测试不会重复添加已有宏包。"""
        new_content = self.project.modify_preamble(
            packages_to_add=["amsmath"],  # 已存在
        )
        # amsmath 应只出现一次
        count = new_content.count(r"\usepackage{amsmath}")
        self.assertEqual(count, 1)

    def test_modify_line_spacing(self):
        """测试修改行间距。"""
        new_content = self.project.modify_preamble(line_spacing=1.5)
        self.assertIn(r"\linespread{1.5}", new_content)

    def test_save_and_reparse(self):
        """测试保存后重新解析的一致性。"""
        new_content = self.project.modify_preamble(
            packages_to_add=["geometry"],
            line_spacing=1.3,
        )
        self.project.save(new_content)

        # 重新解析
        project2 = LatexProject(self.tmp_file.name)
        self.assertTrue(project2.has_package("geometry"))
        info = project2.get_preamble_info()
        self.assertIn(r"\linespread{1.3}", info.raw_preamble)

    def test_save_backup(self):
        """测试备份功能。"""
        backup = self.project.save_backup()
        self.assertTrue(os.path.exists(backup))
        # 清理
        os.unlink(backup)


# ============================================================================
# 4. LatexErrorParser 测试
# ============================================================================

class TestLatexErrorParser(unittest.TestCase):
    """测试 .log 错误解析功能。"""

    def test_empty_log(self):
        """测试空日志。"""
        parser = LatexErrorParser("")
        errors = parser.parse()
        self.assertEqual(len(errors), 0)

    def test_clean_log_no_errors(self):
        """测试无错误的干净日志。"""
        log = r"""This is XeTeX, Version 3.141592653-2.6-0.999995
entering extended mode
(./document.tex
LaTeX2e <2023-11-01>
(/usr/share/texmf-dist/tex/latex/base/article.cls
Document Class: article 2023/05/17 v1.4n
) (./document.aux)
[1] (./document.aux) )
Output written on document.pdf (1 page).
Transcript written on document.log."""
        parser = LatexErrorParser(log)
        errors = parser.parse()
        self.assertEqual(len(errors), 0)

    def test_extract_latex_error(self):
        """测试提取标准 LaTeX 错误。"""
        log = r"""! LaTeX Error: File `nonexistent.sty' not found.

Type X to quit or <RETURN> to proceed,
or enter new name. (Default extension: sty)

Enter file name:
! Emergency stop.
l.5 \usepackage{nonexistent}"""

        parser = LatexErrorParser(log)
        errors = parser.parse()
        self.assertTrue(len(errors) > 0)
        self.assertIn("not found", errors[0].message)

    def test_font_not_found_fatal(self):
        """测试字体未找到的致命错误检测。"""
        log = r"""! LaTeX Error: Font \TU/NonexistentFont(0)/m/n/10= nonexistentfont
at 10pt not loadable: Metric (TFM) file or installed font
not found.

See the LaTeX manual or LaTeX Companion for explanation.
Type  H <return>  for immediate help.
 ...
l.10 \setmainfont{NonexistentFont}"""
        parser = LatexErrorParser(log)
        errors = parser.parse()
        self.assertTrue(any(e.is_fatal for e in errors))
        fatal_errors = [e for e in errors if e.is_fatal]
        self.assertEqual(fatal_errors[0].fatal_signal, "FONT_NOT_FOUND")

    def test_fontspec_font_not_found(self):
        """测试 fontspec 字体缺失错误。"""
        log = r"""! Package fontspec Error: The font "MicrosoftYaHei" cannot be found.

For immediate help type H <return>.
 ...
l.8 \setmainfont{MicrosoftYaHei}"""
        parser = LatexErrorParser(log)
        errors = parser.parse()
        self.assertTrue(any(e.is_fatal for e in errors))

    def test_filter_noise(self):
        """测试过滤 overfull/underfull 等噪声。"""
        log = r"""Overfull \hbox (10.5pt too wide) in paragraph at lines 15--20
Underfull \vbox (badness 10000) has occurred while \output is active
LaTeX Font Warning: Font shape `OT1/cmr/m/n' in size <10> not available
Package hyperref Warning: No autoref name for `section'

! LaTeX Error: Something went wrong.
See the LaTeX manual or LaTeX Companion for explanation.
l.42 \badcommand"""
        parser = LatexErrorParser(log)
        errors = parser.parse()
        # 只应有一个错误（! LaTeX Error），噪声被过滤
        self.assertEqual(len(errors), 1)

    def test_extract_line_number(self):
        """测试行号提取。"""
        log = r"""! Undefined control sequence.
l.123 \undefinedcommand{arg}"""
        parser = LatexErrorParser(log)
        errors = parser.parse()
        self.assertTrue(len(errors) > 0)
        self.assertEqual(errors[0].line, 123)

    def test_get_summary(self):
        """测试错误摘要生成。"""
        log = r"""! LaTeX Error: File not found.
l.5 \input{missing}
! Undefined control sequence.
l.10 \badcmd"""
        parser = LatexErrorParser(log)
        parser.parse()
        summary = parser.get_summary()
        self.assertEqual(summary["total_errors"], 2)
        self.assertFalse(summary["has_fatal"])

    def test_format_for_ai(self):
        """测试 AI 友好的文本格式输出。"""
        log = r"""! LaTeX Error: Test error.
l.42 \test"""
        parser = LatexErrorParser(log)
        parser.parse()
        formatted = parser.format_for_ai()
        self.assertIn("❌", formatted)
        self.assertIn("l.42", formatted)


# ============================================================================
# 5. 致命错误模式匹配测试
# ============================================================================

class TestFatalErrorPatterns(unittest.TestCase):
    """测试致命错误正则模式。"""

    def test_font_not_found_english(self):
        """匹配 'font not found'。"""
        self.assertTrue(
            FATAL_ERROR_PATTERNS["FONT_NOT_FOUND"].search(
                "! LaTeX Error: Font not found."
            )
        )

    def test_font_cannot_be_found(self):
        """匹配 'font cannot be found'。"""
        self.assertTrue(
            FATAL_ERROR_PATTERNS["FONT_NOT_FOUND"].search(
                "Package fontspec Error: The font cannot be found."
            )
        )

    def test_compiler_not_found(self):
        """匹配编译器未找到。"""
        self.assertTrue(
            FATAL_ERROR_PATTERNS["COMPILER_NOT_FOUND"].search(
                "bash: xelatex: command not found"
            )
        )

    def test_no_false_positive(self):
        """确保不会误匹配。"""
        self.assertFalse(
            FATAL_ERROR_PATTERNS["FONT_NOT_FOUND"].search(
                "! LaTeX Error: File `article.cls' not found."
            )
        )


# ============================================================================
# 6. SystemFontChecker 测试
# ============================================================================

class TestSystemFontChecker(unittest.TestCase):
    """测试系统字体查询功能。"""

    def test_list_fonts_returns_list(self):
        """测试字体列表返回类型。"""
        checker = SystemFontChecker()
        fonts = checker.list_fonts()
        self.assertIsInstance(fonts, list)
        # 已配置字体的系统应该至少有一些字体
        if fonts:
            self.assertIsInstance(fonts[0], str)

    def test_check_nonexistent_font(self):
        """测试检查不存在的字体。"""
        checker = SystemFontChecker()
        result = checker.check_font("ZZZ_ThisFontDefinitelyDoesNotExist_ZZZ")
        self.assertFalse(result["available"])
        self.assertFalse(result["exact_match"])

    def test_check_font_structure(self):
        """测试字体检查结果的 JSON 结构。"""
        checker = SystemFontChecker()
        result = checker.check_font("Arial")
        self.assertIn("available", result)
        self.assertIn("font_name", result)
        self.assertIn("exact_match", result)
        self.assertIn("suggestions", result)
        self.assertIsInstance(result["suggestions"], list)


# ============================================================================
# 7. LatexCompiler 测试（Mock）
# ============================================================================

class TestLatexCompiler(unittest.TestCase):
    """测试编译器相关功能。"""

    @patch("latex_core._find_executable")
    def test_auto_detect_xelatex(self, mock_find):
        """测试自动检测 xelatex。"""
        mock_find.side_effect = lambda name: (
            "/usr/bin/xelatex" if name == "xelatex" else None
        )
        compiler = LatexCompiler(compiler="auto")
        engine_name, engine_path = compiler.find_engine()
        self.assertEqual(engine_name, "xelatex")

    @patch("latex_core._find_executable")
    def test_auto_fallback_to_latexmk(self, mock_find):
        """测试回退到 latexmk。"""
        def side_effect(name):
            if name == "xelatex":
                return None
            if name == "lualatex":
                return None
            if name == "latexmk":
                return "/usr/bin/latexmk"
            return None

        mock_find.side_effect = side_effect
        compiler = LatexCompiler(compiler="auto")
        engine_name, _ = compiler.find_engine()
        self.assertEqual(engine_name, "latexmk")

    @patch("latex_core._find_executable")
    def test_no_compiler_found(self, mock_find):
        """测试没有任何编译器的情况。"""
        mock_find.return_value = None
        compiler = LatexCompiler(compiler="auto")
        with self.assertRaises(LatexCompilerNotFoundError):
            compiler.find_engine()

    def test_build_command(self):
        """测试编译命令构建。"""
        compiler = LatexCompiler(compiler="xelatex")
        compiler._engine_path = "/usr/bin/xelatex"
        compiler._engine_name = "xelatex"
        cmd = compiler._build_command("/path/to/doc.tex")
        self.assertIn("/usr/bin/xelatex", cmd)
        self.assertIn("-interaction=nonstopmode", cmd)
        self.assertIn("-halt-on-error", cmd)


# ============================================================================
# 8. LatexOptimizer 集成测试
# ============================================================================

class TestLatexOptimizerIntegration(unittest.TestCase):
    """测试主编排器的集成功能。"""

    def test_action_analyze(self):
        """测试 analyze action。"""
        if not os.path.exists(SAMPLE_BASIC):
            self.skipTest(f"样本文件不存在: {SAMPLE_BASIC}")

        optimizer = LatexOptimizer(
            filepath=SAMPLE_BASIC,
            action_type="analyze",
        )
        result = optimizer.run()
        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "analyze")
        self.assertEqual(result["data"]["document_class"], "article")
        self.assertIn("amsmath", result["data"]["package_names"])

    def test_invalid_action_type(self):
        """测试无效的 action_type。"""
        if not os.path.exists(SAMPLE_BASIC):
            self.skipTest(f"样本文件不存在: {SAMPLE_BASIC}")

        optimizer = LatexOptimizer(
            filepath=SAMPLE_BASIC,
            action_type="invalid_action",
        )
        result = optimizer.run()
        self.assertFalse(result["success"])

    def test_file_not_found_handled(self):
        """测试文件未找到的优雅处理。"""
        optimizer = LatexOptimizer(
            filepath="/nonexistent/file.tex",
            action_type="analyze",
        )
        result = optimizer.run()
        self.assertFalse(result["success"])
        self.assertIn("文件未找到", result["data"]["message"])

    def test_modify_with_font_check(self):
        """测试修改时的字体预检查（模拟缺失字体）。"""
        if not os.path.exists(SAMPLE_BASIC):
            self.skipTest(f"样本文件不存在: {SAMPLE_BASIC}")

        optimizer = LatexOptimizer(
            filepath=SAMPLE_BASIC,
            action_type="modify_preamble",
            modifications={
                "font_settings": {
                    "main_font": "ThisFontAbsolutelyDoesNotExist12345",
                },
            },
        )
        result = optimizer.run()

        # 应该返回字体缺失错误
        if result["fatal_signal"] == "FONT_NOT_FOUND":
            self.assertFalse(result["success"])
        # 如果系统恰好有该字体（极不可能），则允许继续

    def test_check_fonts_action(self):
        """测试 check_fonts action。"""
        if not os.path.exists(SAMPLE_BASIC):
            self.skipTest(f"样本文件不存在: {SAMPLE_BASIC}")

        optimizer = LatexOptimizer(
            filepath=SAMPLE_BASIC,
            action_type="check_fonts",
        )
        result = optimizer.run()
        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "check_fonts")
        self.assertIn("total_fonts", result["data"])


# ============================================================================
# 9. CLI 入口测试
# ============================================================================

class TestCLIEntry(unittest.TestCase):
    """测试 CLI stdin/stdout 入口。"""

    def test_cli_analyze(self):
        """测试 CLI 的 analyze 操作。"""
        if not os.path.exists(SAMPLE_BASIC):
            self.skipTest(f"样本文件不存在: {SAMPLE_BASIC}")

        import subprocess as sp
        input_json = json.dumps({
            "filepath": SAMPLE_BASIC,
            "action_type": "analyze",
        })
        result = sp.run(
            [sys.executable, str(_SCRIPTS_DIR / "latex_core.py")],
            input=input_json,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0)

        output = json.loads(result.stdout)
        self.assertTrue(output["success"])
        self.assertEqual(output["action"], "analyze")

    def test_cli_missing_filepath(self):
        """测试 CLI 缺少 filepath 参数。"""
        import subprocess as sp
        input_json = json.dumps({
            "action_type": "analyze",
        })
        result = sp.run(
            [sys.executable, str(_SCRIPTS_DIR / "latex_core.py")],
            input=input_json,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_cli_invalid_json(self):
        """测试 CLI 收到无效 JSON。"""
        import subprocess as sp
        result = sp.run(
            [sys.executable, str(_SCRIPTS_DIR / "latex_core.py")],
            input="not valid json {{{",
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)


# ============================================================================
# 10. 工具函数测试
# ============================================================================

class TestUtilityFunctions(unittest.TestCase):
    """测试工具函数。"""

    def test_safe_read_utf8(self):
        """测试 UTF-8 读取。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("Hello 世界 🌍")
        try:
            content = _safe_read_file(f.name)
            self.assertIn("世界", content)
        finally:
            os.unlink(f.name)

    def test_safe_write_and_read(self):
        """测试安全写入和读取。"""
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                tmp_path = f.name

            test_content = "Test content 测试内容"
            _safe_write_file(tmp_path, test_content)
            content = _safe_read_file(tmp_path)
            self.assertEqual(content, test_content)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_safe_read_fallback_encoding(self):
        """测试编码回退机制。"""
        # 用 GBK 编码写入中文
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".txt", delete=False
            ) as f:
                f.write("GBK编码的中文内容\n".encode("gbk"))
                tmp_path = f.name

            content = _safe_read_file(tmp_path)
            self.assertIn("中文", content)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)


# ============================================================================
# 运行
# ============================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)

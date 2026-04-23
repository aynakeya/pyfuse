# pyfuse

`pyfuse` 是一个 Python bundler：把多文件 Python 项目打包为单个可运行 `.py` 文件。

## 当前能力

已实现并验证：
- 从入口文件开始打包。
- 递归解析并收集项目内本地模块（`.py`）。
- 支持以下 import 形态：
  - `import x`
  - `import x as y`
  - `from x import y`
  - `from . import x`
  - `from .sub import y`
  - `import a.b`
  - `from a.b import c`
- 支持 package 与 `__init__.py`。
- 支持循环导入（已通过 fixture 验证）。
- 产出单文件后可直接 `python bundled.py` 运行。
- 产出单文件可被其他 Python 文件导入，并转发入口模块导出（例如 `from compiled_a import aa`）。
- 支持可静态判定的动态导入：
  - `__import__("module.name")`
  - `importlib.import_module("module.name")`
- 支持 `--report` 输出 JSON 构建报告（打包模块、跳过模块及原因、依赖摘要）。
- 遇到不支持能力时显式报错（例如动态导入参数不是常量字符串）。

## 非目标（当前阶段）
- C 扩展（`.so` / `.pyd`）打包。
- 完整动态 import 支持。
- zipapp、字节码级优化、混淆。

## 安装与运行

开发模式运行（无需安装）：
```bash
PYTHONPATH=src python -m pyfuse.cli build path/to/main.py -o dist/app.py
python dist/app.py
```

安装后运行：
```bash
pip install -e .
pyfuse build path/to/main.py -o dist/app.py
```

CLI：
```text
pyfuse build ENTRY.py -o OUTPUT.py [--debug] [--verbose] [--report REPORT.json]
```

`--report` JSON 关键字段：
- `bundled_modules`: 被打包的本地模块列表
- `skipped_imports`: 未打包 import 及原因（如 `not-local-or-missing`、`name-defined-in-module`）
- `dependency_edges`: 依赖边数量
- `module_dependencies`: 每个模块的本地依赖

## 设计概览

目录结构：
- `src/pyfuse/cli.py`: CLI 入口
- `src/pyfuse/scanner.py`: AST import 扫描与不支持特性检测
- `src/pyfuse/resolver.py`: 模块名与文件路径解析、相对导入解析
- `src/pyfuse/graph.py`: 本地模块依赖图构建
- `src/pyfuse/generator.py`: 生成单文件代码
- `src/pyfuse/runtime.py`: 单文件内置 importer 运行时
- `tests/`: 单元与集成测试
- `tests/fixtures/`: 端到端示例工程
- `examples/basic/`: 简单示例
- `docs/status.md`: 阶段状态、决策记录、限制清单

Bundling 策略：
1. 从入口文件推断项目根目录与入口模块名。
2. 扫描 AST import，解析本地依赖并构图。
3. 将本地模块源码收集为字典。
4. 生成单文件，内置 `MetaPathFinder + Loader`，按需加载内嵌模块。
5. 用 `__main__` 语义执行入口代码，保持常见脚本行为。

## 验证方式

静态验证：
```bash
PYTHONPATH=src python -m compileall src tests
PYTHONPATH=src python -m pyfuse.cli build tests/fixtures/01_simple_two_file/project/main.py -o /tmp/pyfuse-demo.py
python -m py_compile /tmp/pyfuse-demo.py
```

运行测试：
```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

集成测试覆盖 fixtures：
1. 最简单双文件导入
2. package + submodule
3. 相对导入
4. `__init__.py`
5. import alias
6. from-import
7. 不支持场景（动态导入变量，预期失败）
8. 循环导入
9. namespace package（预期失败）
10. 常量字符串动态导入
11. import-time side effects
12. 深层相对导入
13. 脱离原工程目录运行 bundled 文件

## 已知限制

- 仅支持常量字符串动态导入；以下仍不支持：
  - `__import__(name_var)`
  - `importlib.import_module(name_var)`
  - 相对动态导入（如 `importlib.import_module(".x", "pkg")`）
- 不支持打包 C 扩展模块（`.so` / `.pyd`）。
- 不支持 namespace package（缺少 `__init__.py` 的包目录），会在构建阶段显式报错。
- 对复杂运行时 import 魔改（例如动态改 `sys.meta_path`）不保证兼容。
- `from pkg import name` 在静态分析上无法总是区分属性与子模块，当前实现会尽力解析可定位的本地子模块。

## 示例

```bash
PYTHONPATH=src python -m pyfuse.cli build examples/basic/main.py -o /tmp/basic_bundle.py
python /tmp/basic_bundle.py
```

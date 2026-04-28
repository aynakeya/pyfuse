# Pyfuse Progress Status

## A. 任务清单
- [x] 架构设计
- [x] CLI
- [x] import 扫描
- [x] 依赖图
- [x] 代码生成
- [x] MVP 集成测试
- [x] 包支持
- [x] 相对导入支持
- [x] README
- [x] 已知限制

## 阶段状态

### 阶段 1：需求落地与架构设计
- 已完成：目录结构、模块划分、核心数据结构、bundling 策略、支持范围与非目标。
- 当前失败点：无。
- 下一步：实现 MVP 闭环。
- 风险：import 语义复杂，先做显式不支持检测降低风险。

### 阶段 2：最小可用版本（MVP）
- 已完成：入口扫描、依赖收集、单文件生成、CLI `pyfuse build`。
- 当前失败点：无。
- 下一步：补强 import 形态与包结构场景测试。
- 风险：入口 `__name__ == '__main__'` 与包相对导入语义兼容性。

### 阶段 3：增强 import 支持
- 已完成：`import a.b`、`from a.b import c`、包和 `__init__.py`、相对导入（`.`/`.sub`）支持。
- 已完成：可静态判定的动态导入支持（`__import__("x.y")`、`importlib.import_module("x.y")`）。
- 已完成：`from pkg import name` 判定增强（结合 AST 顶层符号，减少误判子模块依赖）。
- 已完成：额外本地源码根支持（`--module-root`）和显式本地 include（`--include`）。
- 当前失败点：动态导入的非常量/相对形式仍不支持（按设计显式失败）。
- 下一步：错误可诊断性与消息完善。
- 风险：`from x import y` 的静态判定无法 100% 区分 attribute 与 submodule。

### 阶段 4：错误处理与可诊断性
- 已完成：`PyfuseError` 体系、定位信息、CLI `--debug`、CLI `--verbose`、不支持动态导入时报错。
- 已完成：CLI `--report` 构建报告（被打包模块、跳过模块、原因、依赖摘要、module roots、includes、module origins）。
- 当前失败点：无。
- 下一步：补文档与回归测试。
- 风险：更复杂动态行为仍会被拒绝。

### 阶段 5：测试与文档
- 已完成：单元测试、12 个 fixture 集成测试、README、示例项目、限制说明。
- 已完成：新增回归覆盖（循环导入、import-time side effects、深层相对导入、脱离工程目录运行 bundled 文件、额外 module root、include 包树、module root 歧义）。
- 当前失败点：无。
- 下一步：持续补充边界场景（多层包与动态路径混合）。
- 风险：不同 Python 次版本对 import 细节可能有微差异。

## B. 决策记录

1. 决策：采用“内嵌源码 + 自定义 importer”而非大规模 AST 重写。
- 原因：正确性与可维护性更高；避免高风险语义偏差。
- 替代方案：将 import 语句改写为扁平命名空间调用。
- 风险：运行时加载逻辑更复杂，需要保证与 Python import 机制兼容。

2. 决策：仅收集和打包项目内 `.py` 模块，外部/标准库模块保留原生 import。
- 原因：范围可控，符合阶段目标。
- 替代方案：尝试 vendor 外部依赖。
- 风险：若外部依赖未安装，运行时仍会失败（与原项目一致）。

3. 决策：支持“常量字符串动态导入”，其余动态导入显式报错。
- 原因：在可验证正确性的前提下扩大覆盖面，保留安全边界。
- 替代方案：继续一律拒绝或激进支持全部动态导入。
- 风险：对复杂表达式/相对动态导入仍会拒绝，需要用户改写代码。

4. 决策：对 namespace package（无 `__init__.py`）显式报错，不做隐式兼容。
- 原因：单文件运行时要完全模拟 namespace package 代价高且风险大。
- 替代方案：实现 namespace package 仿真加载器。
- 风险：部分现代包布局会被拒绝打包。

5. 决策：用 `--module-root` 声明额外本地源码根，用 `--include` 强制包含本地模块或包。
- 原因：避免从 `sys.path` 或 site-packages 猜测依赖，保持用户代码边界明确。
- 替代方案：按包名从当前 Python 环境解析。
- 风险：用户需要显式传入源码根；同名模块在多个 root 下会构建失败。

## C. 已知限制
- 仅支持常量字符串动态导入；非常量或相对动态导入不支持。
- 动态导入别名形式不支持（如 `il.import_module(...)`、`_import(...)`）。
- 不支持打包 C 扩展模块（`.so` / `.pyd`）。
- 不支持 namespace package（缺少 `__init__.py` 的包目录）。
- 不支持 zipapp、字节码优化、混淆。
- 对 `from pkg import name`，静态阶段无法总是区分 attribute 与 submodule；当前策略是尽力包含可解析的本地模块。
- 不对运行时修改 `sys.path`/`sys.meta_path` 的项目行为作兼容承诺。

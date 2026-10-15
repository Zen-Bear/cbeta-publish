# AGENTS.md

CBETA publish 管理器（PySide6，Python）。运行/测试说明见 `TODO.md`。

## 语言与回复规范（2026-10-14 起，与上游 xml2pdf 仓一致）

- **不自造缩写**：不把词组压缩成自造简写。
- **不自造代称**：不用「甲方案／乙方案」这类临时代号，直接写出做法名称。
- 术语第一次出现时写**全称**；之后用全称，或用项目文档中已有的正式叫法。
- 引用用户原话或文档原文时保持原样，不压缩改写。
- **尽量简单明了**：先给结论，再作必要说明；优先短句、列表、表格。
- **回复不贴代码或 diff**：说明改动时用文字加"文件:行号"
  （如 `cbeta_publish/gui/main_window.py:8698`），不粘贴代码块、命令输出或差异内容。
- 前文出现自造缩写或笔误时主动更正，并给出完整表述。

## 命令

- 测试：`python -m unittest discover tests`
- 源码运行：`python -m cbeta_publish.app`

## 关键约定（务必遵守）

1. **绝不回退真实用户数据**：不要对 `config/app.json`、`mulu/backup/`、`collections/`
   执行 `git checkout` / `git restore` / `git clean`。这些是**运行期数据**，回退会覆盖
   用户设置与编辑。测试后若发现真实文件被写脏，修**具体用例**，不要整体回退。
2. **`collections/` 永不 clean**（保留跟踪，但不得 `git clean`）。
3. **配置分层**：
   - `config/app.default.json`：出厂模板，**跟踪进库**。
   - `config/app.json`：用户运行期配置，**不进版本库**（`.gitignore`），首启由
     `paths.ensure_user_config()` 从模板复制；程序运行期随时改写。
   - `mulu/backup/`：配置/源数据快照，**不进版本库**。
4. **测试隔离**：所有 `MainWindow` 测试必须把 `_config_path` / `collections_dir`
   指向临时目录；护栏见 `tests/test_no_pollution.py`。
5. **提交/推送语义**：用户说「提交」＝仅本地 `git commit`；说「推送」＝再同步 GitHub
   `https://github.com/Zen-Bear/cbeta-publish`。不要擅自 push。

## 打包

`build_exe.ps1` + `packaging/cbeta_publish.spec`（PyInstaller onedir）。打包分发
`config/app.default.json`（改写为便携相对路径），首启生成 `config/app.json`。

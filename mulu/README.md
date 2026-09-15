# mulu 目录说明

本目录存放 CBETA 元数据（目录、作者、经录），为程序唯一可信源。`ref/` 已废弃，仅作历史备份。

## 文件清单

- `bulei.txt` — 部类目录（`https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/bulei/bulei.txt`）
- `SutraList.json` — 藏册目录（`https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/nav/SutraList.json`）
- `sutra_mapping.txt` — work→file 映射（`https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/sutralist/sutralist.txt`）
- `all-creators-with-alias.json` — 全作者含别名（`https://cbdata.dila.edu.tw/stable/download/all-creators-with-alias.json`）
- `creators-by-strokes-with-works.json` — 笔划+作品
- `file-structure.md` / `README.md` / `work-id.md` / `格式说明.txt` — 规范

## 更新策略

- 下载新版 **直接覆盖** 旧文件（`remote_manager.fetch` 原子替换）。
- 覆盖前自动备份到 `mulu/backup/YYYYMMDD-HHMMSS/`（保留最近 5 份）。
- `mulu/cache/meta.json` 记录各文件 `url, etag, sha, last_check`。

## 丛书

见 `mulu/collections/` 每个 `*.json` 为一套丛书，与 `mulu/` 元数据分离，独立版本管理。

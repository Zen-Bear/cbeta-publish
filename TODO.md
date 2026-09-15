# 代办（按优先级）

> 三藏/朝代作为另一种目录分类；生成均按“启动时内存重分组”策略。

## 已完成（近期）
- [x] **P0：复用 cbeta-fetch 共享下载层**（`cbeta_publish/_vendor/cbeta_fetch.py` v0.1.1，sha256 见 `SOURCE.txt`）
  - `official_ebook_source.py`：URL 模板 / id 大小写规范化（`TXA001→TXa001`、`T0128A→T0128a`）/ 原子下载 / docx·odt zip 解压，全部走共享层；布局 `{fmt}/{canon}/{work}` 仍为本仓自有（新增 `canon_of/zip_dest_dir/local_path`）
  - `remote_sources.py`：URL 单源，`_SPEC` 引 `cf.REMOTE_URLS`（展开为原 4 元组，下游免改）；新增 `url_of(key)`
  - `remote_manager.py`：`fetch→cf.fetch_if_changed`、`check→cf.probe`，meta 补存 `last_modified` 并回传
  - `main_window.py`：7 处手写 canon 正则统一改走 `official_ebook_source.dest_path/local_path`（顺带修 `TXa001/T0128a` 路径错误）
  - `download_worker.py`：存在性判断改用 `local_path`（zip 型为目录）
  - `requirements.txt` 删 `requests`（`cbeta_publish/` 已 0 引用）；`mulu/REMOTE_SOURCES.md` 标注 URL 单源
  - 上游 `cbeta-fetch` 新增 `probe_info()`（含 `Content-Length`，`probe` 保持三元组兼容）；单测 `test_vendor_sync.py` / `test_remote_manager.py` / `test_download.py`（id·zip·shared 层）
  - 同步命令：`python <cbeta-fetch>/tools/sync_into.py E:\dev\cbeta\publish\cbeta_publish\_vendor`
- [x] **P1：具名包 + 规范 id**
  - `src/` → `cbeta_publish/`（18 个 py 文件 52 处 import 全部改写；`_vendor` 随迁；入口 `python -m cbeta_publish.app`）
  - `catalog/work_id.py`：`canonical_work`（`cf.canonical_work_id` + `mulu/sutra_mapping.txt`）、`is_work_id`（`cf.is_work_id` 或 `T01n0001` 文件名形态）；`official_ebook_source.canonical` 复用之
  - `gui/main_window.py`：`_normalize_work`→`canonical_work`；`_is_work_id` 取共享层语法 + 文件名形态 + `mapping.work_exists(canonical)`；13 处磁盘兜底读改走 `_read_coll`（读入即规范化）
  - 集合 JSON id 迁移（读入规范化 + 保存回写）：`collection_model.normalize_collection`（`work_ids`/`work_sources` 键/`works[].id`）+ `Collection.__init__`/`load` 规范化；`_load_collections` 基线与内存都用规范化值
  - 单测 `test_work_id.py`（规范化/判别/字段迁移/落盘往返）；实测现有 5 丛书 16 个 id 已全规范，迁移改动 0 条（预防性）
  - 文档路径同步：`docs/{UI设计,设计总案,链路B-设计契约}.md`、`TODO.md`
- [x] 设置对话框 `cbeta_publish/gui/settings_dialog.py`：数据目录 / 封面版式（模式、纸张字号、边距比例、**背景色**、佛像/韦陀开关+路径+恢复默认图片）/ 更新源 / 目录过滤 / 外观（主题/语言/**导航树展开**）；保存前自动备份 `mulu/backup/last`、首次建立 `mulu/backup/original` 出厂点；恢复默认（内置）/ 恢复原始
- [x] 菜单栏入口：`设置 → 设置…` + `工具 → xml2pdf 独立窗…`（预留禁用）
- [x] `config/app.json` 新增 `cover.mode`(print/reading) 与 `cover.images{buddha,weituo}`、`ui.tree_expand`、`catalog.filters`；出厂图 `assets/images/buddha.jpg`+`default/` 备份已就位
- [x] 导航树展开设置：`ui.tree_expand{mode:none|depth|all, depth:N}` + `_expand_tree()`（替换 5 处硬编码 `expandToDepth(1)`）；设置页「外观」下拉即时生效
- [x] catalog：部类源切官方 `category.json`、`RemoteManager`（检查/更新/备份）、`update_interval` 后台检查、三藏导航、朝代导航、目录过滤

## P1 — 合成打印/阅读模式 + 佛像/韦陀插入 ✅
- [x] `merge_pdfs` 按 `cover.mode` 分支页面序列（打印补空白 / 阅读去空白）
  - 打印：封面→空白→佛像→空白→目录→(目录奇页补白)→正文(每部奇页补白)→韦陀→空白→封底
  - 阅读：封面→佛像→目录→正文→韦陀（去空白）
- [x] `_image_pdf()`：reportlab Image 按页居中缩放（≤80% 页）；图缺失/关闭时连同其空白页跳过
- [x] `_toc_pdf(..., toc_start_index)` 支持目录页位置变化（页码/链接自适应）
- [x] 单测 `tests/test_merge_mode.py`：打印/阅读 × 有/无图像 4 组（页数/书签/链接）
- [x] 设置页模式/图像开关生效（`_cover_config` 直读 `self.config['cover']`）

## P1 — 链路 B（XML→xml2pdf→丛书）
- [x] `config/app.json` 新增 `default_source` + `xml2pdf{path,page,font_lang,engine,vertical}`
- [x] `collection_model.Collection` 新增 `source/work_sources/xml_options`（旧 JSON 兼容）
- [x] `cbeta_publish/books/xml2pdf_bridge.py`：`find_xml`（走 `sutra_mapping` file，兼容 GitHub/分卷命名）+ `convert/batch_convert`（`python -m pycbeta` 子进程）
- [x] `[合成]` 按来源分流：`work_sources`→`collection.source`→`default_source`；xml 项经桥接生成到 `my_books/_xml_convert/` 再合并（官方缺书提示保留）
- [x] 工具菜单 `xml2pdf 独立窗…` 启用（子进程 `python -m pycbeta.gui`）
- [x] 设置页「数据目录」新增 默认来源/xml2pdf 路径/纸张/字库语言/引擎/竖排
- [x] 单测 `tests/test_xml2pdf_bridge.py`
- [x] ~~**中栏「来源」列 UI**（方案B 细粒度）~~ **已废弃**：不做每本书单独指定来源（`work_sources` 数据字段保留兼容，但不再提供细粒度编辑；来源按集合级 `source`/全局 `default_source`）
- [ ] 右栏「来源」单选（跟随集合/官方/本地XML）+ `[设置…]` 嵌入 `XmlOptionsDialog`（集合级 `source`/`xml_options`）— **待定**

## P1.5 — 合成质量与体验（新发现）
- [x] **EPUB 合并对齐 PDF**：丛书封面+丛书目录置于最前；保留每本原封面页/样式(css+图)；排除每本自带 toc/front/back；每部书签；`split_items` 分册
  - 样式修复：ebooklib 读取会丢 `<head>` 链接，合并时按书内相对路径 `add_link` 重新挂 `cbeta.css`
  - 单测 `tests/test_merge_epub.py`（封面/排除/书签/样式链接/临时目录）
  - `front`(编辑说明) 只保留第一本，`back`(后记) 只保留最后一本
  - 每本封面页改为 `.cover` 容器 + `<img>`，共享 `cover.css`（`html,body{height:100%}` + flex 居中 + `object-fit:contain` 铺满放大）
  - 丛书封面改用外链 `cover.css`（原 `<head>` 内联 `<style>` 被 ebooklib 丢弃，导致文字无样式/左对齐）；丛书目录 `nav` 也挂 `cover.css` 居中
  - 丛书封面改用**纯流式内联样式**（`text-align`/`font-size`/`margin-top:em`，标题行高 1.5、距顶 1.5em，整理者距标题 20.5em）：不依赖页高类 CSS（WPS/Sumatra 不解析 `height:100%`/`vh`/百分比 top，绝对定位会塌到顶部重叠）；ebooklib 只重建 `<head>`，正文内联 style 保留
  - 目录页：`EpubNav(title="丛书目录")`；首条书签指向目录页；列表 `margin-top:3em`（标题下两行）+ `margin-left:2em`（右缩进）；链接去下划线；条目 `margin-bottom:0.6em`，`cover.css` 的 `nav` 规则
  - PDF 封面日期字号与左上角文字一致（`_cover_pdf` 取 `topleft_sz`；`styles.date.ratio` 默认 0.75→1.0）
  - PDF 书签精确锚定页顶：`set_toc` 三元条目默认落点是页顶下 36pt，全部书签改传第 4 元 `BOOKMARK_TOP_MARGIN=1`（0 会触发某些阅读器对“恰好页顶”目标改变缩放，1pt 肉眼等同页顶）；单测 `test_bookmark_anchors_page_top` 断言 `get_toc(simple=False)` 的 `to.y==1`
  - 封面左上角落款可配置：`cover.imprint`（默认 "CBETA 電子佛典"，留空不绘制），PDF/EPUB 共用；设置页「封面/版式」加「左上角文字」输入框
  - `cover.enabled` 开关（设置→封面版式「合并时使用封面/封底页」，默认开）：关闭时直接拼接原文件，仅做书签；原书书签降一级归入对应书下（PDF 取 `get_toc()` 偏移页码；EPUB 取原书 nav、href 加书前缀；EPUB 不删不增任何内容页、spine 不放目录页）
  - 保存弹窗作用域化（`_prompt_save_collection(reason, scope)`）：下载/合并/ZIP/导出只处理当前丛书（干净则无弹窗），其它未保存丛书不动；弹窗点名脏丛书（`_dirty_coll_names`），退出弹窗亦列出；新增 `_save_one_collection`/`_revert_one_collection`（单还原不跳走选中）；**约定：发布类操作后选「否」= 暂不保存（改动留内存，不还原）**，避免丢掉刚写入的发布记录；退出时统一询问
  - ZIP 取消真正生效：压缩写入循环内检查取消并删除半成品 zip（原来只在收集文件阶段检查，压缩中取消无效）；**选择输出目录对话框点取消**（返回空串，误判为当前目录）也不再继续；进度总量 = 收集 + 压缩
  - 合并日志弹窗：`_make_progress` 逐条累积显示（不再一闪而过，末 24 行 + 略过提示），标题只在窗口标题、条目不重复；每条含原文件（`T0102.pdf`）与「分册：X → 文件（N 部）」信息
  - 空白丛书（`空白\d*`）发布后：无论是否改动都提示另存为正式名称（`_prompt_save_collection` 对临时名不再依赖脏标记）
  - 空白名判断统一为 `_is_blank_name`（“空白丛书”+“空白/空白N”；旧正则 `空白\d*` 匹配不上真正的“空白丛书”，致改名逻辑长期未生效）；**合并前空白丛书强制改名保存**，取消则中止合并
  - 合并进度窗口改为可滚动日志（`_make_progress`：QTextBrowser 日志 + 进度条 + 取消，可上下滚动、运行时不抢滚动条；准备阶段不再逐书列行，只记转换/分册计划/当前处理书）；**合并结束窗口常驻**（`finish()` 写总结行 + 进度拉满 + 按钮变“关闭”，由用户手动关闭；offscreen 自动关闭）；合并成功去掉「是否打开文件？」弹窗，固定切「丛书信息」页，首条为输出目录链接、其余为产物文件链接；**每组合成完与总结行中的文件名/目录均为蓝色可点击链接**（`setOpenExternalLinks`）
  - 手动 `work_groups` 标签同样补刊本名+序号（按其成员的册归属；与刊本名相同的老拖拽回退值让位给自动册名/书名）
  - 进度日志链接点击走系统默认程序（`openLinks=False` + `anchorClicked→_open_link→QDesktopServices`；QTextBrowser 会把 `file://` 当内部文档加载致 `No document`，中文路径亦然）；仅已生成产物为蓝色链接，原文件行保持默认色；**日志统一走 insertHtml（纯文本转义），每次显式复位字符格式**，防链接蓝/下划线/锚点泄漏给后续行；单测 `ProgressLinkTest`（含纯文本不变蓝）
  - 封面标题 `｜` 改为手动换行：`丛书名｜册名` 在 PDF 封面分两行居中、EPUB 封面 `<br/>`（原来过宽按字符硬切，切口落在 `｜` 处像乱码换行）；修单行分支未下移 y 致两行重叠
  - 左上角文字/系列名二合一：设置页只剩「左上角系列名」一个框（默认 `CBETA 電子佛典自選叢書`，键仍用 `cover.imprint`，可填系列名或落款，留空不绘制）；旧 `cover.series` 非空自动并入 imprint；渲染层删除 series 分支/参数/`font_series` 与系列名字体行，左上永远走落款逻辑
  - 界面字体/字号/补充字型保存后即时生效（`apply_ui_fonts`，设置保存时调用，无需重启）；单测 `tests/test_ui_fonts.py`
  - 封面字体改后即时生效（`_register_font` 同名换路径注册到新别名并缓存；reportlab 对同名重注册静默忽略，曾致旧字体沿用、必须重启；命中缓存亦不再重复解析大字库）；单测 `ReregisterFontTest` + 双字体封面嵌入验证
  - 封面「说明」页书单改用与「目录」页一致的 `sutra.title_of`（`bulei_index.summarize(..., title_of=)`），不再显示作者
  - 「封面/版式」拆为 4 个子页签（顺序：**封面佛像、背景色 → 字体 → 基准字号 → 边距**），通用项（整理者署名、左上角系列名、发布模式、封面开关、说明页）留在页签上方表单；字体浏览修复：起始目录=当前字体所在目录（无则系统字体目录）、路径按**系统默认分隔符**显示（`_native_path`，Windows 反斜杠），字体页签首项标签改「左上角系列名」；按钮行显式布局：左「恢复默认 / 恢复原始」，右「确定 / 保存 / 取消」且**确定为默认按钮**（回车触发，`_apply` 不写盘仅本次生效，主窗口提示区分“已保存/已应用”）；单测 `tests/test_settings_dialog.py`
  - **事故与恢复**：`settings_dialog.py` 曾被 PowerShell `Get-Content/Set-Content` 以 cp936 往返转码损坏（非 ASCII 字节变 `?`、部分换行被吞），已用损坏前 `.pyc` 的字符串常量重建：逐字面量前缀对齐回填（`?` 视作 1–2 字节、可跳过被吞字节）+ 行级补回被吞换行/注释 + 全量校验（字面量 100% 命中 pyc、AST 可解析、函数行号与 pyc 结构一致）。**教训：改 UTF-8 源码一律用编辑工具，不要用 PowerShell 文本 cmdlet 回写。**
  - 右栏 ↑ ↓ 按钮 + `Alt+↑/↓`（仅右栏聚焦时）：选中按块整体上/下移一位，保持相对顺序；顶/底不动；刷新后恢复选中、滚动到选中项（`scrollToItem` 居中）并标脏（拖拽保留，管远距离）；右栏「全选/取消选中」按钮（选中行+勾复选框，经 `_on_coll_item_toggle` 同步 `_selected`/中栏；移除按复选框收集）
  - 右栏选中/悬停配色：选中绿系 `#c8e6c9`、悬停蓝系 `#e3f2fd`、选中+悬停锁定深绿 `#a5d6a7`（不同色相，不易混）；选中行文字转黑（未下载灰字在绿底上对比不足，`_refresh_coll_text_colors`）
  - 右栏行首加序号（`1. T0001 ...`，按丛书书单顺序）
  - 下载队列自动折叠（`_dl_running`）：平时隐藏（信息栏常驻），下载开始展开，下载中切换不收，结束后下一切换收起；小结仍写底栏 detail
  - 右下改 Tab 面板「丛书信息|下载记录」（`tab_bottom`，替代上面的折叠方案）：下载开始自动切下载页；失败弹窗（`QMessageBox.warning` 列文件）；记录行成功 ✓ / 更新 ↻ 蓝字 / 跳过 – 灰字 / 失败 ✗ 红字（`_add_record`，自动滚到底）；信息页顶对齐（QLabel 默认垂直居中导致 75px 空隙）
  - 下载更新检测（`remote_info` HEAD 取大小/时间 + `is_unchanged`）：存在且无更新则跳过（记 ok），有更新记"更新"；HEAD 失败回退直接下载；取消按钮（`btn_cancel_dl`，`worker.stop()`，文件间生效，未下完记"取消 剩余 N 个"）
  - 下载/取消合成一个双态按钮（`_on_download_button`）：空闲"下载"，下载中"取消下载"
  - 勾选计数移到中栏标题行（`lbl_sel_count`，`_refresh_sel_count`）；右栏复选框与 `_selected` 解耦（仅本栏标记供"移除"收集，默认未勾选），点击只改视觉、不触发计数；detail 不再被计数覆盖
  - 书籍信息统一为 `_book_info_text(w)`（`{w} {经名}` / `译作者：` / `卷数：… 文件：…`）：左栏树预览、中栏列表、右栏书单三处一致；去掉右栏原来直接转储 mapping dict；标题用 `_display_title` 去重（原来重复显示经号）
  - 部類說明頁（`cbeta_publish/catalog/bulei_index.py` 自动推导 + `_intro_pdf`/`_epub_intro_page`）：封面后目录前；内容=总数/三藏分布/部類分布 + 按部類分组的完整清单（经号 经名）；PDF 多页自动分页、打印模式奇页补白；EPUB 仅封面模式（裸合并不加）；`cover.intro{enabled,title,list}` + 设置页开关；单测 `tests/test_bulei_index.py` 等
  - 合成进度条 + 取消（`_make_progress`）：准备+合成按总量线性推进（每格式各占一半，不再 60% 起跳）；`merge_pdfs/merge_epubs` 加 `progress` 回调，返回 False 抛 `MergeCancelled`
  - 丛书信息可拷贝（`lbl_coll_info` 加文本选中 flags，链接仍可点）；PDF 多分册产物全部记入发布信息（原来只记 `parts[0]`）；设置页新增「每纸张边距(pt)」表
  - 字体缺字修复（`_register_font`/`_face_has_cjk`）：配置字体（如本机 "Source Han Serif SC Heavy"）缺繁体字形时自动换用 simsun/msyh/simhei 全字库，避免说明页/封面出现方框；PDF 说明页加书签（说明→目录→正文）
  - 记住上次工作的丛书：`_on_combo_changed` 写 `ui.last_collection`（`_persist_last_collection` 直接落 config/app.json），启动 `_load_collections` 选中它、`_ensure_blank_working(select=False)` 不再抢选；设置页「封面版式」新增字体选择（`styles.<key>.font` 8 项）
  - 分栏分隔条箭头（`_PanelHandle`/`_Splitter`）：每条 handle 上「◀ 收起左侧栏 / ▶ 恢复」；设置「封面版式」套卷动窗；移除「边距比例 margin_ratio」UI（保留代码回退），边距统一用每纸张边距(pt)
  - 分栏恢复保持原宽度：收起时存整组 sizes，恢复原样写回（不向邻栏"借宽"，避免被最小宽度重分配）
  - PDF 封面让 `margins` 生效（CBETA 左上=left/top；标题/整理者/日期按文本区居中与换行），`positions.*_y_ratio` 真正生效、删除死代码 `_get_margin`；EPUB 封面 E2：字号取 `styles.ratio`(em)、颜色取 `styles.color`（不改字体族/边距）
  - 下载记录改文本（`log_view=QTextBrowser` 只读可拷贝，HTML 颜色；列表无拷贝优势）；Tab 纵向收紧（`Maximum`，多余空间还给书单）；启动默认聚焦搜索框；缓存/输出目录显示短名（悬停全路径，点击打开，新增输出目录行）
  - 右栏布局：格式行与发布行互换（格式在上）；下载/取消搬到发布行合并左边；中栏"清除"+右栏"取消选中"统一改名"不选"
  - Tab 高度固定为下载页高度（`_fix_tab_height`，切页上面元素不再伸缩）；信息页套滚动区防长链接被裁；标题行右上角 ▾/▸ 折叠键（`_toggle_tab_pane`）；缓存/输出目录合并一行，去掉"本地"二字（短名+悬停全路径+点击打开）
  - 搜索改用基准+显示分离（`_base_works`）：回车（`returnPressed`）可重复搜同内容；清空恢复基准；删书/清空/排序同步基准，加书同步基准
- [x] **分册参数暴露 UI**：`config.pdf.split_pages`(5000) / `config.epub.split_items`(500)，设置页「封面/版式」→「分册」可调，0=不分册；PDF 分册保护 `split_pages and …`（裸/封面两路），EPUB 原有 `split_items>0` 保护保留
- [x] **按册分册（按原书分卷）**：册归属自动取自 `mulu/vol.json`（`vol_service.work_file_map`，`main_window._wvol_cache`），`Collection.work_groups` 可人工覆盖；合成时 `config.merge.by_volume` 开启则按册分组，产物名 `刊本名 序号 显示名.{fmt}`（序号按刊本内原始顺序，直属经取书名如「編纂說明」）；例：太虛大師全書 → `太虛大師全書 01 編纂說明/02 法藏/03 制藏/04 論藏/05 雜藏`，大正藏 → `大正藏 01 T01…/02 T02…/03 T03…`；封面标题 `丛书名｜册名`；分册后自动切到下方「丛书信息」标签页；设置页「数据/输出」勾选；单测 `tests/test_by_volume.py`、`tests/test_vol.py`（`work_vol_map`/`work_edition_map` 保留备用）
- [x] **进度反馈**：合并/ZIP/导出已加进度条+取消（`_make_progress`）；更新有 `lbl_upd_log` 实时日志；下载有记录页/队列

## P2 — 数据模型 / 配置清理（新发现）
- [x] **标签体系 UI**：`TagsManager` 完整 CRUD（`add/update/delete` 级联子标签、`new_id` 拼音 slug）+ 右栏「标签管理」对话框（有丛书使用禁删）+ 右栏「标签…」为当前丛书多选赋值（未登记旧标签列出防丢）+ 左栏「标签：」横向筛选（与分类筛选并列，仅丛书视图）+ 右栏信息显示标签；`Collection.tags` 改为用户维护（不再自动 `custom`/`分类:xx`）
- [x] **`collections/index.json`**：实现为派生索引（`collection_model.write_index`：`{id,name,category,path,work_count,updated_at}`），启动/保存/删除时生成；扫描分类目录仍是权威（可安全删除）
- [x] **硬编码路径清理**：`cbeta_publish/app.py` 补充字型/应用字体/字号改读 `config.ui.{supplement_ttf,app_font,app_font_size}`；设置页「外观」加应用字体/字号/补充字型
- [x] **缓存管理**：`books/cache_manager.py`（`dir_stats/human/clean`）+ 设置页「缓存」页签（电子书/XML/输出中间文件 大小与清理）；单测 `test_cache_manager.py`
- [x] **作者按朝代排序**：`dynasty_service.{work_dynasty_map,dominant_dynasty,group_authors_by_dynasty}` + 作者视图「朝代排序」（朝代节点→作者，`未詳` 置末，筛选下拉按朝代）；单测 `test_dynasty.py` 扩展
- [x] 附：`ui.last_collection` 写入改走 `self._config_path`（可被测试覆盖），并修复 `config/app.json` 曾被测试污染为临时 `settest` 路径 → 复位 `E:/dev/cbeta/publish/{mulu,collections}`

## catalog（目录）专章
- [x] 目录更新源：`category.json` 优先 + `RemoteManager`（ETag/备份）+ 设置页「更新源」+ `update_interval` 后台检查
- [x] 分类导航：三藏（经10/律1/论4/藏外8）、朝代（朝代→经）
- [x] 目录过滤：设置页复选框 + `catalog.filters.{tripitaka,dynasty}.hidden`
- [x] **`vol.json`（依刊本）导航**：`catalog/vol_service.py`（`load_vol`/`edition_titles`/`count_works`，兼容"第二层直接是经"的刊本）+ 导航「刊本」（刊本→册→经，26 刊本/465 册/5939 部）+ 预览/双击入中栏 + 刊本过滤 `catalog.filters.vol.hidden`（设置页「目录过滤」第三组）；共享层 `REMOTE_URLS` 加 `vol_json`（cbeta-fetch 0.1.2）+ 源表登记 `("vol","刊本",...vol_json)`；单测 `tests/test_vol.py`；`mulu/vol.json` 已下载
- [x] **树拖拽载荷修复**：`QTreeWidget` 默认 `mimeData` 只有内部模型格式（无 `text/plain`），父节点（刊本/册/朝代/字母/作者）拖到中栏或右栏拿不到书 → 新增 `_item_work_ids`/`_data_work_ids` + 覆写 `tree.mimeData`（text/plain = 选中节点含子孙的作品 id 列表）；单测 `tests/test_tree_drag.py`（刊本叶/册/刊本、朝代、作者）
- [x] 中栏排序新增**「原始顺序」并设为默认**（`sort_combo`：原始顺序/经号排序/经名排序）：原来默认经号排序会把 `TXa001` 排到最后（`T…` < `TX…`），拖入顺序被打乱；原始顺序保留加入/拖动顺序
- [x] 设置页**下拉框滚轮保护**：`eventFilter` 扩到 `QComboBox`，8 个下拉（数据/输出 ×4、封面模式、外观 ×3）未聚焦时滚轮不改值（与数值框一致）
- [x] 设置「目录过滤」改**子页签面板**（部类/三藏、朝代、刊本），避免三段竖排过长；全选/全不选仍作用于三组

## P3 — 外观/语言（最后做）— **待定**
- [ ] 深色/浅色/繁简：ThemeManager/i18n 现为桩；先用 OpenCC 全文案转 zh-Hant，en 后置

## P3 — 打包 / 文档 — **待定**
- [ ] Windows 启动器/打包（PyInstaller 或快捷方式）、`requirements.txt` 固定版本
- [ ] README（安装/运行/配置说明）
- [x] 测试扩展：10 个测试文件 / 70 用例（merge·epub·download·remote_manager·work_id·vendor_sync·bulei_index·tripitaka·dynasty·xml2pdf_bridge）

## 低优先可选（P4）
- [ ] **丛书导航改树结构**（方案二）：`_refresh_coll_tree` 改「分类 → 丛书」两级（分类节点 data={"category":id}，双击仅展开；丛书节点双击载入中栏）；移除或保留 `coll_filter` 分类下拉待定；可再加第三层「丛书→书籍」。默认保持现状（扁平）。

## 备注
- 本地 `bulei.txt` 为 **CBETA 23 部類**，三藏映射 经(01-10)/律(11)/论(12-15)/藏外(16-23)
- 封面字体/颜色/比例已在 `cover.styles` 统一（`font` 为字体文件路径；`ratio`/`delta`；缺繁体字形自动回退系统全字库；未下载/字号基准见设置页「封面/版式」）

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
- [x] **链路 B 重做：库调用＋预设＋右栏来源/预设＋平展目录＋说明页注明**：① `xml2pdf_bridge.convert/batch_convert` 改**进程内库调用**（`pycbeta.cli.main(argv)`，省每本一次进程启动；`-i` 优先传 `find_xml` 本地路径，找不到传 work id 由对面自动取 XML；进度/取消直连，失败→None）；② **预设制**：`config.xml2pdf={path,preset_dir,preset}`（删 page/font_lang/engine/vertical UI，旧值照读但停传）；`preset_dir` 缺省=xml2pdf 根，`list_presets` 列合法 `*.json`（去 `//` 注释行再解析，run bundle 与纯 presets 均可），`resolve_preset` 文件名→路径；右栏「发布」组加**来源单选**（官方/自制，读写全局 `default_source`，sticky 落盘）＋**预设下拉**（首项出厂默认，仅自制启用）＋**[调整…]**（开上游 `XmlOptionsDialog`，覆盖/另存为到预设目录后刷新）；设置页加预设目录＋默认预设＋自制书目录，来源下拉显示中文；③ **输出分离**：`xml_to_ebooks_dir`（默认 `./cbeta_ebooks_xml`）**完全平展** `{work}.{fmt}`，`find_built` 兼容 `{id 书名}.pdf` 形式，存在且比预设新则复用；④ `_merge` 整批同源（右栏选择；`work_sources` 只读兼容），说明页来源自制时追加一句"电子书由程序根据官方XML制作。"（官方不加）；单测 `tests/test_xml2pdf_bridge.py`（argv 装配/取消/预设目录/平展/mtime）＋右栏/设置页/合并用例；`docs/链路B-UI设计.md` v3、`docs/链路B-设计契约.md` 调用部分同步；后续修正：目录统一绝对路径（缺省即绝对，相对按工程根解析 `bridge._abs`）、设置页目录行全部加浏览按钮（打开目录为当前值所在目录）、自制项收进「自制」组框（UI 不出现链路B字样）、「xml2pdf 路径」改名「自制程序路径」、预设缺省改为仓库下 presets 子目录、路径统一本地分隔符显示与落盘；右栏回位：自制/重制按钮回到发布行（下载/更新之后），「仅缺/全部」单选仍留在来源行自制之后；左栏目录树（含工作区树）：书叶文字黑色、分组节点颜色不变（_colour_tree_leaves），选中/悬停与中栏列表完全一致（#bbdefb / #fff3c4 / #90caf9）；右栏自制/重制按钮改放到来源行「自制」单选之后（括号内为生成策略），发布行只留 合并/ZIP/导出/下载更新；设置「经文补充字型」路径统一本地分隔符；左栏视图下拉改单选（新增 `_RadioBar`，接口仿 QComboBox，无需改调用方/测试）；右栏书单「已有」标志随来源（`_ebook_path`：官方查 cbeta_ebooks、自制查 xml_to_ebooks_dir，切来源即刷新）；.gitignore 加 cbeta_ebooks_xml/；设置/右栏 UI 调整：默认来源、主题、语言全部改单选（去下拉），「仅缺/全部」单选移入右栏发布按钮行并用括号包裹（自制后、重制前）；修复应用字体切换后 item view（列表/表格/树/表头）不跟随（apply_ui_fonts 显式刷新 allWidgets+viewport）；收尾修正：xml2pdf.cbeta_ebook 改名「CBETA XML 目录」且不可为空（默认 cbeta_xml，convert 恒传 --cbeta-ebook）、缓存页「自制电子书」用 bridge 默认兜底接上、右栏来源=自制时把「下载/更新」换成「自制」（生成缺失）/「重制」（全部重生成）两按钮（官方则恢复原按钮，进度窗同合并前生成、不弹确认）；生成策略改为用户显式二选一（右栏「生成」：仅缺/全部，config.xml2pdf.regen，默认 missing）：删 is_fresh（mtime 推断），新增 bridge.ensure_one（仅缺=find_built 复用；全部=重生成并覆盖原路径），全部且已有产物时合并/ZIP/导出前确认；ZIP/导出 由纯官方改为按来源取目录（自制一并支持）；对齐 xml2pdf《第三方调用说明》：预设目录固定为仓库 presets/（上游 user_presets_dir，删 publish 的 preset_dir）、预设名用 stem、读写与[调整…]全走上游公开 API（list/load/save_config_preset + get_preset/merged_preset，不再用私有名或自写盘）、convert 传 --cbeta-ebook（配置键 xml2pdf.cbeta_ebook，设置页「XML 工作根」行）；再修正：XML 源归 xml2pdf（CBReader 是 P5a 按卷切分≠对面要的 P5 整部经，publish 不再自行定位），删 `find_xml`/`batch_convert` 及定位测试、`_merge` 只传 work id，设置页删 XML 缓存/本地CBReader 两行及 `book_dir`/`local_xml_root` 键、缓存页改指自制书目录
- [ ] 右栏「来源」单选（跟随集合/官方/本地XML）+ `[设置…]` 嵌入 `XmlOptionsDialog`（集合级 `source`/`xml_options`）— **已取消**：改为右栏全局来源单选＋预设下拉（见上一条），`XmlOptionsDialog` 改为预设[调整…]入口
- [ ] **按目录分册（部类/刊本两维）+ 右栏分组 + 合并弹框**：① 新建 `catalog/catalog_path.py`（`work_path(work, dim)`，dim=部类/刊本；部类走 `build_index` 取 `[顶层部类, 子分组…]`、深度=路径前N级，刊本走 `work_file_map` 取 `[刊本名, 册标题]`，查不到进「未歸類」，结果缓存）；② `_group_works` 加 `catalog` 分支（`mode/dim/depth` 可选参数，老调用兼容；`by_volume=true` 视为 volume；文件名=清洗后路径段连接，组按丛书首次出现排序；手动册标签只在刊本模式生效）；③ 新建 `gui/merge_dialog.py`（独立模态：模式三选一不分册/按刊本册/按目录＋维度下拉＋深度数字框＋文件预览清单＋确定/取消；点合并→空书检查→弹框→缺书下载→合成，选择回写 config；主窗口布局不动）；④ 右栏加「分组」勾选（默认开，`ui.coll_grouped`，维度跟合并维度走；`_render_coll_rows` 插不可选分组头，删除/全选/排序写回自动跳过）；⑤ 设置页删「按册分册」勾选换只读提示（分册模式在合并时选择），`by_volume` 仅留兼容读取；⑥ 单测 `tests/test_by_catalog.py`（分组/深度/命名/未歸類/排序/兼容）＋弹框用例＋右栏用例。**不做**：选择时记录来源（实时查替代）、ZIP/导出弹框、作者/朝代维度；三藏不单列（部类唯一对应三藏，按部类分天然落进三藏）

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
- [x] **部类补缺组**：官方 `category.json` 实测 般若部類 缺 `01 小品般若經(大般若經第1會) T05-06`、`09 大品般若(大般若經第11會)`（远端 stable 源同样缺，且本地文件与远端 **sha256 一致**，非过期；`bulei.txt` 完整）→ 新增 `bulei_parser.merge_missing_children(primary, fallback)`，`_load_bulei` 用 category.json 为主、按「顶层部類→直接子分组」前导序号补入 bulei.txt 的缺失分组（含子树，按序号排序，不改既有结构）；实测补 2 组，般若部類恢复 01..13；单测 `tests/test_bulei_merge.py`、`tests/test_right_panel.py`
- [x] **右栏「发布」分组框**：`QGroupBox("发布")` 框住「格式:(pdf/epub)」+「合并/ZIP/导出/下载」两行，去掉旧的「发布:」标签；下载按钮改名 **下载/更新**（下载中仍显示「取消下载」，结束后恢复 `下载/更新`）；单测 `tests/test_right_panel.py`
- [x] **三栏选书区语义（阶段 1）**：中栏定位「**选书区**」（左栏搜索结果 + 右栏回填；勾选=加入意图）。① **左栏树→右栏拖拽**（原已支持 `tree.mimeData`+`_coll_drop`，本次补回归测试）；② **右栏移除→回选书区末尾**（统一 `_remove_works_from_collection`：删 `work_ids` 时把 `work_groups` 册标签搬回 `self._work_groups`、清孤儿 `work_sources`，再 `_return_to_middle()` 去重追加末尾且不勾选；`_remove_from_coll`、右→中拖拽 `_list_drop` 都走它）；③ **中栏→右栏 拷贝改移动**（`_add_selected_to_coll`、`_coll_drop` 来源=中栏、`_create_collection_dialog` 都调 `_move_out_of_middle()`：从显示与勾选移出、**保留 `_base_works`** 以便再次搜索/加入）；退役 `_purge_buffer`；中栏标题→「选书区」、全删 tooltip→「清空选书区」；④ **固定约束：右栏书目操作不影响左栏**（树/选中/过滤器/搜索框；已加断言测试）；⑤ 新增设置「外观 → 布局：三栏（含选书区）/ 二栏」`ui.layout`，二栏=收起中栏（复用分隔条 0 宽机制 `_apply_layout`，启动/保存设置时应用，不改数据）；单测 `tests/test_three_pane.py`（10 项）、`tests/test_settings_dialog.py`（布局往返）
- [x] **三栏选书区语义（阶段 2，二栏行为）**：① 二栏下**搜索结果渲染到左栏**（`_render_pool_to_left`：`搜索结果/选书区(N 部)` + `已移除(N 部)` 两个顶层节点，子项=作品）；② 关键点：选书区占用左栏时把**导航树暂存**（`_stash_left_tree`/`_restore_left_tree`，`_nav_stash`），`_search_current_tree` 改为搜索暂存的导航树 → 二栏搜索仍搜“目录”而非选书区；③ **双击单本作品=直接加入右栏**（`_on_tree_double_click` 二栏分支 → `_add_to_collection(move_out=True)`，选书区节点/刊本叶/部类叶通用）；④ **#4 回填落到左栏选书区视图的「已移除（N 部）」组**（`_return_to_middle` 记 `_returned`；由 `_render_pool_to_left` 与「搜索结果/选书区」一并渲染，**不混入部类/刊本等导航树**）；⑤ **新建丛书用左栏选中**（`_new_collection` 二栏走 `_tree_selected_works`）；⑥ 切二栏时中栏内容即时渲染到左栏（`force=True`），切回三栏恢复导航树+中栏渲染；⑦ `_tree_selected_works`/`_coll_drop` 统一走 `_item_payload`/`_add_to_collection`（顺带支持 丛书树→右栏拖拽、刊本/选书区叶选中）；单测 `tests/test_three_pane.py` `TwoPaneTest`（7 项）
- [x] **布局切换移到菜单栏 + 二栏真隐藏 + 详情可见 + 已移除不混入部类**（本轮）：① 布局 2/3 栏从左栏单选按钮**移到菜单栏「视图」**（`_build_menu` 内 `QActionGroup` 互斥、勾选态随布局同步；`_apply_layout("three"|"two")` 仍写 `config.ui.layout` 并 `_persist_ui_layout` 落盘）；② 二栏改为**真隐藏中栏**（`self.mid.setVisible(False)`，经实测 `QSplitter` 会连带隐藏其两侧 handle → 不再残留可拖动/无意义的「收起/恢复」按钮；切回三栏 `setVisible(True)` + 恢复 `_three_sizes`）；`showEvent` 按 `ui.layout` 设置显隐；③ **书籍信息（`self.detail`）从中栏底部移到窗口状态栏**（`statusBar().addWidget(detail, 1)`）→ 二栏（中栏隐藏）时依然可见；④ **「已移除」不再挂进部类树**：删除 `_prepend_returned_node`（及 `_expand_tree`/`_restore_left_tree` 中的调用），改由 `_render_pool_to_left` 在池非空时用「搜索结果/选书区 + 已移除」视图整体替换左栏，池空即恢复导航树；实测二栏：刊本→右栏拖拽 accepted（98 部/98 册标签）、移除后左栏=「已移除（1 部）」且无部类树、全删后部类树回归；单测 `tests/test_three_pane.py`（`LayoutSettingTest.test_apply_layout_hides_middle`/`test_layout_actions_in_menu`、`TwoPaneTest.test_two_pane_hides_middle`）
- [x] **下载改弹窗 + 点书才显示信息**：① **删除右下「下载记录」页签**（并删 `log_view`/`_add_record`/`_cancel_download` 与 `_dl_worker` 双态按钮逻辑）；**「下载/更新」按钮改走弹窗进度**：`_download` 组装 `pairs=[(work,fmt)…]` 交给已有的 `_download_missing`（`_make_progress` 可滚动日志 + 进度条 + 取消，线程 + 嵌套事件循环保持可响应），结束后按 `_dl_stats` 报「下载完成 ok/total」或弹失败清单；② **左栏只在点击「书」时显示信息**：`_on_tree_preview` 重写，新增 `_tree_item_work(item)` 判定叶=单作品（BuleiNode 叶 / `{"key": wid}` 叶），部类分组、刊本/册、作者、朝代分组、丛书等节点一律清空（实测四模式全覆盖）；单测 `tests/test_download_log.py`（重写：`_make_progress` 合并行 3 项 + 按钮走弹窗 + `_dl_stats`）
- [x] **右下页签改为「书籍信息 + 丛书信息」**（本轮；取代上一轮的状态栏方案）
- [x] **左栏工作区面板**（本轮）：① 搜索行加三个按钮：**✕ 清除**（`_clear_search`：清搜索框 + 六个二级过滤回「全部」，`_on_nav_changed` 恢复完整目录）、**工作区**（checkable，`_toggle_workspace`：工作区面板与目录树二选一显示；按钮带计数 `工作区（N）`）、**＋**（`_ws_add_search`：当前搜索结果一键加入工作区）；② 工作区面板（`ws_page`：计数头 + 清空 + `ws_tree`，默认隐藏；切导航模式自动回到目录面板）；③ 工作区模型 `self._workspace`（去重保序；`_render_workspace`/`_ws_selected_works`/`_ws_clear`/`_update_ws_button`）；④ **右栏移除流入工作区**（`_remove_works_from_collection` 在 `_return_to_middle` 后调 `_add_to_workspace`，选书区回填语义不变，只动工作区面板/按钮计数，不碰目录树/过滤/搜索框）；⑤ **工作区可拖入右栏**（`ws_tree.mimeData=_tree_mimeData` 同格式，`_coll_drop` 加 `ws_tree` 分支，拷贝语义留在工作区）；⑥ 工作区双击（`_on_ws_double_click`：三栏=加入选书区，二栏=直接加入右栏；点书显示信息复用 `_on_tree_preview`）；单测 `tests/test_workspace.py`（8 项：按钮/清除/切换/一键加入/移除流入/拖入右栏/双击/导航回目录）
- [x] **真实拖放修复 + 清除保状态 + ＋按钮移位**（本轮）：① **拖放根因**：`coll_list`/`list`/`tree` 只重写了 `dragEnterEvent`/`dropEvent`，Qt 默认 `dragMoveEvent` 拒收一切外部拖拽 → 真实鼠标拖放永远到不了 `dropEvent`（合成 FakeDrop 测不出）；新增 `_drop_move(e, view)`（先走默认实现保留内部排序指示器，再强制 `acceptProposedAction`）并接到三个放下目标；② **真实 mime 适配**：真实拖拽带的是内部 model mime（无 `text/plain`），`_coll_drop` 对目录树/工作区来源在 mime 为空时从选中项提 `(作品, 册标签)`（`_item_payload`），册标签不丢；③ **清除搜索保状态**：`_clear_search` 不再无脑 `_on_nav_changed` 重建——过滤没变则目录树原样保留（含展开/滚动/选中；三栏树本来就没动过，二栏恢复 `_nav_stash` 暂存树），过滤真变了才 `_refresh_current_tree()` 重建（从 `_on_nav_changed` 抽出的 6 路分发）；④ **＋按钮移到 ✕ 右边**（搜索行顺序：`搜索框 ✕ ＋ 工作区`）；单测补 4 项（`test_drag_move_accepts_real_drags`、`test_coll_drop_with_empty_mime_uses_selection`、`test_ws_drop_with_empty_mime_uses_selection`、`test_clear_search_keeps_expansion`）
- [x] **右栏→左栏拖放移除 + 已移除只进工作区**（本轮）：① 右栏可拖到**目录树**（`_tree_drop` 新增 `coll_list` 分支，不再忽略）和**工作区树**（`ws_tree.setAcceptDrops(True)` + 新增 `_ws_drop`，只接受右栏拖入）→ 都是 `_remove_works_from_collection`（回填选书区 + 加入工作区）；右栏拖出提取统一为 `_coll_dragged_works`（选中项 UserRole，兜底 mime 文本；`_list_drop` 同走它）；② **移除后不自动进入工作区**（`_add_to_workspace` 只渲染面板 + 按钮计数，不动可见性；用户点「工作区」才进入）；③ **已移除不再进目录区搜索面板**：`_render_pool_to_left` 删除「已移除」节点（`show=kw or (force and res)`，res 排除 `_returned`），二栏移除后左栏保持导航树；`test_right_remove_shows_returned_node_in_left`/`test_returned_node_selection_for_new_collection` 按新语义重写（进工作区/搜索结果选中）；单测补 2 项（`test_coll_drop_to_tree_removes`、`test_coll_drop_to_workspace_removes_without_auto_enter`）+ `dragMove` 覆盖 `ws_tree`
- [x] **右下页签改为「书籍信息 + 丛书信息」**（取代状态栏方案）：① 回退状态栏改动，恢复右栏底部 `tab_bottom`（原「下载记录」那种样式：固定高度 + 右上角 ▾ 最小化箭头 `_toggle_tab_pane`/`_fix_tab_height`）：tab 0=**书籍信息**（`detail`，可滚动、可选中拷贝）、tab 1=**丛书信息**（`lbl_coll_info` 在 `info_scroll`，恢复多行 `<br>` 原样渲染）；② **激活时机**：三栏点书 → `_on_tree_preview`/`_on_list_detail`/`_on_coll_item_detail` 显示信息并 `setCurrentIndex(0)`；合并完成 → `setCurrentIndex(1)`（与原来激活「丛书信息」的时机一致）；其它节点点击只清空信息不切页签；单测（`test_tabs_are_book_info_then_coll_info`、`test_click_book_activates_book_tab`）+ 实测探针全过
- [x] **中栏与工作区合一（大重构）**：唯一内存目录 `_workspace`（+ `_selected` 勾选）；**删除** `_current_works`/`_base_works`/`_returned`/`_sync_middle_from_workspace`/`_show_works`(`_show_works_sorted`)/`_move_out_of_middle`/`_return_to_middle`/`_ordered_selected`/`_render_pool_to_left`/`_add_to_workspace`/`_render_workspace`/`_clear_list`。① **两个视图同一份数据**：中栏 `list`（三栏，标题改「工作区」）与左栏 `ws_tree`（二栏）都由 `_refresh_ws_views()` 渲染，共用 `_work_row_text()`/`_ws_display_order()`（视图级排序，不动原始顺序）/`_set_sort_mode()`（两个排序下拉同步）、`_sync_checks()`（两处勾选互相同步）、`_ws_selected()`；左栏面板补齐与中栏一致的**控制行**（排序 + 全选/不选/加入已选/全删）。② **搜索改道**：`_on_search` 只写 `_search_results`（`_search_current_tree` + 作者模式优先），`_render_search_to_left()` 在**两种布局**都把左栏树暂存后显示「搜索结果（N 部）」（`_stash_left_tree`/`_restore_left_tree` 复用）；中栏永不被搜索覆盖。③ **操作统一**：`_ws_add`/`_ws_remove`/`_ws_clear`；＋=把搜索结果加入工作区（＝中栏）；目录树双击书（三栏=加入工作区 / 二栏=直接加入右栏）、双击丛书=追加其书目到工作区、双击作者=其全部作品加入工作区；工作区任一视图双击=加入右栏并移出（移动）；「加入已选」/新建丛书=加入右栏后移出工作区；右栏移除（按钮/拖到左栏）=`_ws_add`；拖拽：目录树→右栏=拷贝、工作区→右栏=移动、右栏→工作区=移除入库、工作区/中栏→目录树=移出工作区（`_tree_drop_works`）。④ **布局**：`_apply_layout` 只切显示（三栏隐藏「工作区」按钮并强制目录面板；二栏显示按钮，默认目录），不再做数据搬运；`showEvent`/启动尺寸不变。⑤ 测试：`tests/test_three_pane.py` 重写（ThreePaneTest 13 项含两视图共享/勾选同步/排序/移动语义；LayoutSettingTest 加「按钮只在二栏」；TwoPaneTest 9 项改为 `_search_results` 与左栏面板）、`tests/test_workspace.py` 重写（17 项：搜索行按钮/清除保展开/面板切换与计数/两视图 work id/＋/右栏移除入库/拖放放行/空 mime 用选中项/移动语义/控制行共用 handler）、`tests/test_right_panel.py` 搜索断言改用 `_search_results`；全量 **196 项通过**
- [x] **丛书信息栏**：去掉合并后多余的「→ 打开输出目录」链接（上面「最后发布」行已显示目录），只保留各产物文件链接
- [x] **设置页小改（本轮）**：① **打印模式下拉改单选按钮**：`cover.mode` 由 `QComboBox(["print","reading"])` 改为 `QRadioButton`「打印模式」「阅读模式」（`QButtonGroup` 互斥，各带 tooltip），新增 `_set_mode()/_mode()` 做 `print/reading` 互转，`_sync_from_cfg`/`_collect` 同步替换；② 标签「发布模式」→「**PDF 合并模式**」；③ **「设置…」直接放菜单栏**（`bar.addAction`，不再 设置→设置 两级），带 `Ctrl+,` 快捷键；④ **「按册分册」标签/描述修正**：原「按原书分卷各一个文件」改为「每册一个文件，文件名=刊本名 序号 显示名」并加 tooltip（说明按 `mulu/vol.json` 的刊本分册、手动册标签优先、不勾选则整部合一个文件）；⑤ **「恢复默认/恢复原始」加 tooltip**（说明作用范围与「需点确定/保存才生效」）；单测补 5 项（`test_mode_is_radio_buttons`、`test_restore_buttons_have_tooltips`、`test_by_volume_label_mentions_file_naming`、`test_cover_labels_renamed`、`LayoutSettingTest.test_settings_action_direct_in_menubar`）；全量 **207 项通过**
- [x] **进度窗收窄 + 无错自动关闭 + 分隔条收起/恢复可反复**（本轮）：① **进度窗改窄**：`_make_progress` 由 `setMinimumSize(640,440)` 改为 `setMinimumSize(460,300)` + `resize(520,360)`（下载窗与合并/ZIP/导出窗同一函数，一并变窄）；② **合并/ZIP/导出前的下载窗：无错时 3 秒自动关闭并继续**：`_download_missing(..., autoclose_ok=True)`（三处前置调用传入；「下载/更新」按钮保持手动关闭），无失败且未取消时总结行追加「没有出错，3 秒后自动关闭并继续…」并置 `pstate["autoclose_ms"]=3000`；`finish` 在 `exec()` 前 `QTimer.singleShot(ms, dlg.accept)` → 到点关闭、`exec` 返回后继续合并；③ **修复「收起→恢复→再收起失效」**：根因是 `_PanelHandle._left_index()` 用「中心点比较」动态判定左侧栏，某栏被折叠成 0 宽后几何判定指错栏，第二次收起飞作用到别栏（表现为按钮失效）；改为 ①判定依据换成「右边缘离分隔条左边缘最近」的一栏、②`_panel()` **只判定一次并缓存**（窗口结构不变），`_collapse`/`_restore` 都走缓存索引；实测两个可见分隔条「收起→恢复→收起」均连续生效；单测补 4 项（`test_splitter_handle_collapse_restore_repeatable`、`test_splitter_handle_index_cached`、`test_progress_dialog_is_narrow`、`test_autoclose_after_ok_download`/`test_no_autoclose_on_failure`/`test_no_autoclose_for_download_button`）；全量 **202 项通过**
- [x] **工作区带 work id + 三栏时刷新中栏**（已被下一轮「中栏与工作区合一」取代）：① 工作区条目改为 `f"{w}　{title}"`（与搜索结果一致带 work id）；② 新增 `_sync_middle_from_workspace()`：`_apply_layout("three")` 切三栏时若工作区非空，则把工作区内容（去重原序）刷成中栏内容（`_base_works`/`_current_works` 同步、清 `_returned`、`_show_works_sorted`），即「工作区 = 持久内存目录，三栏中栏显示它」；空工作区时保持原中栏不动（启动时也是这条路径，不会误清）；③ 采用用户给的两种方案中的第一种（切换时刷新），未做双向实时共用（搜索结果仍只改显示、不写工作区），如需真正「工作区↔中栏同一份内存」再说；单测补 2 项（`test_ws_items_show_work_id`、`test_switch_to_three_loads_workspace_into_middle`）
- [x] **界面字体/搜索结果显示/清除保展开/工作区按钮/启动尺寸**（本轮）：① **外观字体默认改宋体**（`config/app.json` `ui.app_font=SimSun`、`apply_ui_fonts` 与设置对话框三处 fallback 同步，`tests/test_ui_fonts.py` 期望更新）；② **搜索结果带 work id**（`_add_pool_node` 子项 `f"{w}　{title}"`，二栏左栏池可辨认核对）；③ **修复「清除搜索后目录树展开被重置」**：根因是 `_stash_left_tree` 用 `takeTopLevelItem` 把节点移出视图时 Qt 会丢失展开状态（探针复现：stash 后 `isExpanded()` 变 False）→ 新增 `_tree_expand_state`/`_apply_tree_expand_state`（按子索引路径快照），stash 前快照、restore 时套用；重建（过滤真变）路径同样快照+还原；`changed` 判定改用 `cb.currentData() is not None`（可编辑 combo 的 `currentIndex()` 可能为 -1）；④ **工作区按钮文字随状态切换**：未勾选 `工作区（N）`，勾选 `目录区（N）`；⑤ **启动窗口尺寸按布局**：二栏 `resize(1000,720)`、三栏 `resize(1240,720)`；单测补 5 项（`test_pool_items_show_work_id`、`test_ws_button_label_shows_count`、`test_workspace_toggle_hides_catalog` 加文字断言、`TwoPaneTest.test_clear_search_keeps_nav_expansion`、`LayoutSettingTest.test_startup_window_size_by_layout`）
- [x] **左栏导航收尾**：① 刊本过滤改为**刊本（一级目录本身）**（原按「册」）；② 笔画视图分组标题去掉 `(stroke)` 后缀（`_stroke_label`，`1畫(stroke)`→`1畫`，过滤下拉与树共用）；③ 搜索**英文大小写不敏感**（`t0220` 与 `T0220` 结果一致；`_on_search`/`_search_current_tree` 比较时统一 `.lower()`）
- [x] **左栏导航增强**：① **三藏/刊本 加二级分类过滤**（`tripitaka_filter`=部类、`vol_filter`=刊本（一级目录本身）；随模式显隐，`_refresh_tripitaka_tree(filter_title)`/`_refresh_vol_tree(filter_edition)`，选中后树只剩该项，含子树）；② **作者排序下拉框改单选按钮**（`author_sort_row` + `QButtonGroup`/`author_radios`，`_author_sort_mode()` 取当前项；拼音/笔画/朝代）；③ **搜索覆盖所有视图**：新增 `_search_current_tree(kw)`（在当前左栏树按标题匹配，命中节点取全部子孙作品，繁简/异体变体；`_is_known_work` 过滤 T01 类分组号），`_on_search` 用它替换原来只对「部类」生效的兜底 → 部类/三藏/刊本/朝代/作者/丛书均可搜；④ **丛书树列出经书名字**（原只显示丛书名，现加子项 `经号 经名`，走 `_work_item`/`sutra.title_of`/mapping 回退）；删掉因此不再使用的 `_bulei_title_s2`
- [x] **左栏/设置小修**：① 设置「更新源」表的 **远端 URL / 本地文件** 两列改为**只读 `QLineEdit`**（`_ro_field`，可完整查看/选中拷贝，带全文 tooltip；表格行高 28、隐藏行号列）；② 两个恢复按钮去掉突兀的「（mulu）」→ **恢复原始（目录数据）/ 恢复上一次（目录数据）**；③ 左栏**部类过滤**默认项统一为 **「全部部类」**，并修复可编辑 combo 在 `clear()+addItem()` 后停在 `currentIndex=-1`（只显示占位符、看不到默认值）的问题（`_refresh_bulei_tree` 显式回 index 0 并 `setEditText`）；④ 搜索框前加 **「搜索：」** 标签（占位符相应简化为“经名/作者/经号（全局）”）；单测 `tests/test_settings_dialog.py`、`tests/test_right_panel.py`
- [x] **更新检查误报修复**：`RemoteManager` 两处——① `_cond` 发条件头前用 `_clean_etag` 去掉服务端 gzip 表示的 `-gzip` 后缀（cbdata 的 ETag 存成 `"…-gzip"`，与实体表示不匹配 → 恒 200；实测去掉后 `If-None-Match` 得 **304**，`-gzip` 版得 200）；② `check` 改用 `cf.probe_info`，条件头判 changed 时再用**远端 Content-Length 与本地文件大小**兜底（GitHub raw 忽略条件头，ETag 也不是内容 sha256），大小一致即「已最新」。修复前 8 个源**永远报「有更新」**并反复重下；实测现全部 `needs_update=False`。单测 `tests/test_remote_manager.py`（`CleanEtagTest` + size 兜底）
- [x] **下载进度行合并 + 缺书下载弹窗**：下载记录每本书只占一行（`REPLACE_LAST="\r"` 前缀 → `_log_replace_last` 替换上一段），形如 `下载 TX0015.epub ...完成 319KB`（已存在时 `...更新 NKB`、失败 `...失败`；`_make_progress` 的日志同样支持）；合并/ZIP/导出前若有未下载：弹「是否先下载？」并调用 `_download_missing(pairs, dest_dir, title)`（**在 `DownloadWorker` 线程里下载 + 嵌套 `QEventLoop`，窗口保持可响应**，此前同步下载致弹窗“无响应”；取消按钮经 `st["oncancel"]` 联动 `worker.stop()`；逐本进度合并成行，收尾列失败/取消，结束后 `_load_coll_works` 复查）；合并「否」= 跳过未下载继续，ZIP/导出「否/取消」= 中止；`DownloadWorker(pairs=...)` 支持精确组合（不再是 works×fmts 叉积）；`official_ebook_source.local_size_kb` 统一取大小；单测 `tests/test_download_log.py`、`tests/test_download.py`

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

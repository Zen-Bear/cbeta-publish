# 上游问题反馈：CssEditorDialog 构造时追加全局样式，污染宿主应用布局

> 来源：CBETA publish（嵌入方）实测；上游仓库不动，仅此文转交。
> 上游版本：`E:/dev/cbeta/xml2pdf @ ae03b52`
> 日期：2026-09-27

## 标题

`CssEditorDialog` 构造时往 `QApplication` 追加全局样式，抬高宿主各栏最小值且粘住回不来，锁死分栏、主窗口无法缩小。

## 复现（宿主侧，publish 已实测三次）

```python
from pycbeta.gui.css_editor import ensure_tooltip_style
# 备好任意含 QComboBox 的主窗，记左栏 minimumSizeHint（如 346）
ensure_tooltip_style()   # 即 CssEditorDialog.__init__ 内的调用
# 同一值变 1272 级别；随后：还原样式表文本＋processEvents＋invalidate＋
# unpolish/polish＋整体换 style 对象——最小值全部回不来
```

宿主现象（publish 主窗，二栏/三栏皆中）：打开 CSS 编辑器弹窗的瞬间左栏撑大、右栏压到最小；分隔条双向拖不动；主窗口只能拉宽不能缩小；退出弹窗不恢复。点取消也中（构造即触发，与后续操作无关）。

## 根因

`pycbeta/gui/css_editor.py:2640 ensure_tooltip_style()`：

```python
app.setStyleSheet((app.styleSheet() or "") + "\n" + rule)  # QToolTip 深色规则
```

1. 对话框构造器改**进程全局**状态（QApplication 样式表），且靠 `app._tooltip_styled`
   一次性标记**永不还原**；
2. 全应用 repolish 后，各控件 `minimumSizeHint` 按 QStyleSheetStyle 重算——
   QComboBox 按最长项全文计算（实测某 combo 162→1254），左栏最小值 346→1272；
3. 该最小值粘滞：还原样式表文本也降不回来（已穷举验证），分栏被最小值总和钉死。

## 建议修法（三选一，推荐①）

- **①（推荐）规则下到对话框实例**：`self.setStyleSheet(rule)` 代替 `app.setStyleSheet(...)`。
  tooltip 会从所属窗继承样式，贵方弹窗内深色效果不变，宿主零影响。
- ② 加参 `global_tooltip_style=False`，仅 standalone 入口传 `True`。
- ③ 进出快照恢复：**不推荐**——已实测证明修不彻底（最小值粘住）。

## 附：嵌入方现状

publish 侧已在 `_edit_preset` 进弹窗前预置 `app._tooltip_styled` 标记，使该函数直接返回
（上游仓库不动；本应用 tooltip 本来就是系统默认，零视觉变化）。
该 workaround 在上游修好后可删除。

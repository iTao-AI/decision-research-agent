---
name: decision-html
description: Use when a confirmed, shareable decision snapshot needs an offline Chinese HTML brief with its reasons, follow-up conditions, and expandable source quotations.
---

# 决策简报 HTML

先确认读者、版本、可分享的安排和可转述的证据范围。客户简报应让读者先看见决定、适用条件和下一步。需要继续核实的事项保留其问题与负责人。模拟项目使用虚构案例标记。以本次确认版本为依据，另存新版本。

## 从确认快照生成文件

以下命令在仓库根目录执行。已有准备好的导出快照时，直接指定快照与目标文件。

```shell
python operator-skills/decision-html/scripts/render_brief.py confirmed-v2.json brief-v2.html
```

虚构样本加 `--fictional`。脚本只依赖 Python 标准库。输入为 UTF-8 JSON：

- `version` 是正整数，`headline` 与 `summary` 是本版已确认的安排摘要。
- `items` 中每条包含 `area`、`state`、`priority`、`action`、`owner`、`reason`、`question` 和 `evidence_ids`。没有待确认问题时用空字符串。状态 `proceed` 和 `waiting` 分别呈现为可继续和待确认。
- `evidence` 中每条包含 `id`、`title`、`page_start`、`page_end` 和 `text`，页码从 1 开始。每个引用 ID 要指向唯一一条本版冻结证据。只展示被引用证据的标题、页码、原文。

文件用系统字体和原生折叠区，适合通过本地文件打开。脚本对所用文字作 HTML 转义。生成前仍需审查结论和摘录是否可转发。核对未获授权字段是否藏在可展开内容或输出源码。

## 验收和交付

打开桌面和窄屏，复核首屏安排、待确认条件、展开原句、键盘操作及离线打开。比对 HTML 与输入快照的版本、决定、引用和页码。用独立文件保存已有版本。

需要交付登记时，将生成的文件交给宿主项目的登记命令，并读回该版本和文件指纹。登记和业务状态由宿主系统负责。

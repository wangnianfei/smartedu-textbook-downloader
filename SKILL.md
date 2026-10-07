---
name: smartedu-textbook-downloader
description: Search and download Chinese K-12 textbook PDFs (电子教材/课本) from the National Smart Education Platform (国家中小学智慧教育平台, basic.smartedu.cn). Use when the user gives a basic.smartedu.cn tchMaterial link or contentId, or asks to download a textbook by subject/grade/volume/publisher (e.g. 生物学七年级上册, 人教版语文八年级下册).
---

# 国家中小学智慧教育平台 教材下载

从 `basic.smartedu.cn`（国家中小学智慧教育平台）检索并下载电子教材 PDF，**无需登录**。

脚本：`scripts/smartedu.py`（仅用 Python 标准库，无第三方依赖）。

## 何时使用

- 用户给出 `basic.smartedu.cn/tchMaterial/detail?...contentId=...` 链接或裸 contentId。
- 用户想按「学科 + 年级 + 册次 + 版本」下载教材，例如「生物学七年级上册」「人教版八年级下册语文」。
- 需要先查有哪些版本（人教、苏教、北师大……）再下载。

## 用法

```bash
# 1) 先搜索，确认版本（同一书名往往有多家出版社）
python3 scripts/smartedu.py search 生物学 七年级 上册
python3 scripts/smartedu.py search 语文 八年级 下册 --publisher 人民教育出版社

# 2) 按 contentId 或 detail URL 下载
python3 scripts/smartedu.py download d3af85b8-5cf2-41d7-a6ad-3a622f04cb67 -o ~/Desktop
python3 scripts/smartedu.py download "https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=d3af85b8-5cf2-41d7-a6ad-3a622f04cb67&catalogType=tchMaterial&subCatalog=tchMaterial" -o ~/Desktop

# 3) 搜索 + 下载一步到位
python3 scripts/smartedu.py get 生物学 七年级 上册 --publisher 江苏凤凰教育出版社 -o ~/Desktop
#   多个同名结果时会列出候选项；确认后用 --first 或直接用 contentId

# 可选
python3 scripts/smartedu.py refresh        # 重建目录缓存
```

常用参数：`-o/--out` 输出目录（默认当前目录）、`--name` 指定文件名、`--raw-name` 用平台原始长文件名。

## 输出

- 默认文件名由「书名 + 版本」生成，例如 `义务教育教科书·生物学七年级上册（苏教版）.pdf`。
- 下载支持**断点续传**（自动重试直到字节数等于服务端 `Content-Length`），完成后校验 `%PDF-` 头与 `%%EOF` 尾，避免半截文件。
- 目录缓存位于 `~/.cache/smartedu-textbook/catalog.json`（约 35 MB，含数千册教材元数据），可用 `refresh` 更新。

## 注意

- 同一书名有多个出版社版本，`get` 遇到多结果会列出让你确认，**不要静默选第一个**，除非用户明确要求「随便一个/第一个」。
- 若某 contentId 只有图片、没有 PDF，会明确报错说明。
- 平台接口可能变动；核心接口见 README。仅用于个人学习用途，请遵守平台条款与著作权规定。

# smartedu-textbook-downloader

一个 [Claude Code / pi](https://github.com) skill：从 **国家中小学智慧教育平台**（[basic.smartedu.cn](https://basic.smartedu.cn/tchMaterial)）检索并下载电子教材 PDF，无需登录，仅用 Python 标准库。

A skill to search and download Chinese K-12 textbook PDFs from the National Smart Education Platform. No login, no third-party dependencies.

## 特性

- 🔍 按「学科 / 年级 / 册次 / 出版社」搜索全部教材目录（数千册）
- ⬇️ 支持 contentId、detail URL，或直接按书名下载
- 🔁 断点续传 + 字节数校验 + `%PDF`/`%%EOF` 完整性检查
- 🏷️ 自动按「书名（版本）」命名，自动区分人教/苏教/北师大等多版本
- 📦 零依赖（Python 3 标准库）

## 安装

在 Claude Code / pi 中作为 skill 使用：

```bash
git clone https://github.com/wangnianfei/smartedu-textbook-downloader.git
ln -s "$PWD/smartedu-textbook-downloader" ~/.claude/skills/smartedu-textbook-downloader
```

也可以直接当命令行工具用，无需安装。

## 用法

```bash
# 搜索（同一书名常有多个出版社版本）
python3 scripts/smartedu.py search 生物学 七年级 上册
python3 scripts/smartedu.py search 语文 八年级 下册 --publisher 人民教育出版社

# 按 contentId / detail URL 下载
python3 scripts/smartedu.py download d3af85b8-5cf2-41d7-a6ad-3a622f04cb67 -o ~/Desktop
python3 scripts/smartedu.py download "https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=d3af85b8-5cf2-41d7-a6ad-3a622f04cb67&catalogType=tchMaterial&subCatalog=tchMaterial" -o ~/Desktop

# 搜索 + 下载
python3 scripts/smartedu.py get 生物学 七年级 上册 --publisher 江苏凤凰教育出版社 -o ~/Desktop

# 重建目录缓存
python3 scripts/smartedu.py refresh
```

### 参数

| 参数 | 说明 |
| --- | --- |
| `-o, --out DIR` | 输出目录（默认当前目录） |
| `--name FILE` | 指定输出文件名 |
| `--raw-name` | 使用平台原始长文件名（含 ISBN、出版社、时间戳） |
| `--publisher NAME` | 按出版社过滤 |
| `--first` | 多结果时直接取第一个（默认会列出候选让你确认） |
| `--limit N` | `search` 输出条数上限 |

## 工作原理

平台公开接口（无需鉴权）：

1. **目录索引** `https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/version/data_version.json`
   返回若干 `part_*.json`，汇总后是全部教材元数据（标题、出版社、版本标签等）。
2. **教材详情** `https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/<contentId>.json`
   `ti_items[].ti_storages` 中含 PDF 链接。
3. **下载** 详情里的链接指向 `*-ndr-private.ykt.cbern.com.cn`（私有域），去掉 `-private` 即得公开镜像
   `https://r{1,2,3}-ndr.ykt.cbern.com.cn/edu_product/esp/assets/<contentId>.pkg/<文件名>.pdf`。
   大文件（部分教材 >100 MB）首次连接可能被截断，脚本用 `Range` 断点续传补齐。

缓存目录：`~/.cache/smartedu-textbook/`（可用环境变量 `SMARTEDU_CACHE` 覆盖）。

## 示例

```text
$ python3 scripts/smartedu.py search 生物学 七年级 上册
d3af85b8-5cf2-41d7-a6ad-3a622f04cb67  （根据2022年版课程标准修订）义务教育教科书•生物学七年级上册
    publisher: 江苏凤凰教育出版社   edition: 苏教版
405270eb-9f00-4bba-b0f6-da863340625f  （根据2022年版课程标准修订）义务教育教科书·生物学七年级上册
    publisher: 人民教育出版社   edition: 人教版
...

$ python3 scripts/smartedu.py download d3af85b8-5cf2-41d7-a6ad-3a622f04cb67 -o ~/Desktop
Downloading: /Users/me/Desktop/义务教育教科书·生物学七年级上册（苏教版）.pdf
  attempt 1: 114824412/114824412 bytes (100%)
OK  /Users/me/Desktop/义务教育教科书·生物学七年级上册（苏教版）.pdf  (109.5 MB)
```

## 免责声明

本项目仅用于个人学习与教学研究。教材版权归各出版社及国家中小学智慧教育平台所有，请遵守平台服务条款，勿用于商业用途或再分发。

## License

MIT

# eudic2maimemo

用欧路词典查词，用墨墨背单词复习，中间那段搬运交给程序。

[English](README.en.md)

[![CI](https://github.com/Frank-Loong/eudic2maimemo/actions/workflows/ci.yml/badge.svg)](https://github.com/Frank-Loong/eudic2maimemo/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 这个项目做什么

欧路的长处是查词，词典可换、释义靠得住；墨墨的长处是按遗忘曲线安排复习。两边各有各的生词本，彼此不通，查过的词要手抄进墨墨，抄几次就断了。

这个项目要解决的就是这一段：读欧路生词本里的词，剔除墨墨云词本里已有的，剩下的按添加日期追加进去。跑起来之后不用再动手。

具体的做法是：拉取欧路生词本 → 与云词本现有内容比对 → 只把新词写回去，并按中国时区的日期分段。全量重建时先正序翻到 5100 条上限，再用倒序补齐最新的一段，两段取并集，所以词本再大也不会漏掉最近加的。

支持的功能：

- 全量搬运与日常增量，日常只写新词
- 多个生词本一起同步，合并去重
- 全量同步用双向并集，突破单方向 5100 条的上限
- 按正则跳过词组、中文等墨墨无法建卡的条目
- 有新词或同步失败时推送到企业微信、钉钉、Server 酱
- 自检命令，随时查看配置状态和覆盖缺口
- 除 GitHub Actions，也能以常驻服务、Docker、systemd 的方式运行

## 开始之前

准备三样：

- 欧路词典账号
- 墨墨背单词账号，手机上装了 App
- GitHub 账号，用来存放定时任务

全部配置在浏览器内完成，无需安装任何软件，首次约需 10 分钟。

## 第 1 步 获取欧路授权信息

1. 打开 https://my.eudic.net/OpenAPI/Authorization
2. 用欧路账号登录，登录成功后会跳回这个页面
3. 页面上显示一串以 `NIS ` 开头的字符，这就是请求头里的 Authorization 值
4. 完整复制，**保留 `NIS` 及其后的空格**

先存到记事本，第 4 步要用。

登录后没有跳回该页面的话，重新打开一次链接即可。

## 第 2 步 获取墨墨 token

必须用手机 App，网页版拿到的只有 7 天有效期。

1. 打开墨墨背单词 App
2. 底部「我的」→ 右上「更多设置」→「实验功能」→「开放 API」
3. 页面上有一串 64 位的字符，字母加数字，复制

同样先放记事本。

## 第 3 步 Fork 仓库

将本仓库 Fork 到自己的账号下，定时任务运行在这份副本里。

建议设为私有：Settings → Danger Zone → Change visibility → Make private。公开仓库连续 60 天无提交记录时，GitHub 会自动停用其中的定时任务；私有仓库不受此限制。

## 第 4 步 配置密钥

1. 在仓库页面点击上方的 **Settings**
2. 左侧选择 **Secrets and variables** → **Actions**
3. 点击右侧的 **New repository secret**
4. Name 填 `EUDIC_API_KEY`，Secret 填第 1 步那串（带 `NIS `）
5. 点 **Add secret**
6. 重复上述步骤，Name 填 `MOMO_API_KEY`，Secret 填第 2 步那串

名称需完全一致，注意大小写与下划线；拼写不符时会持续提示缺少 Secret。

`MOMO_NOTEPAD_ID` 暂不填写，下一步获取后再补。

## 第 5 步 获取云词本 ID

墨墨允许存在多个云词本，需要指定本次同步写入哪一个。

1. 点击上方的 **Actions**
2. 左侧列表选择 **Doctor**
3. 点击右侧的 **Run workflow**，在下拉面板中再次点击 **Run workflow** 启动
4. 约半分钟后刷新页面，打开最新一条运行记录
5. 页面下方的 **Summary** 会列出全部云词本，每行末尾是 `np-` 开头的 ID

找到目标云词本（例如「欧路生词」），复制其 `np-` 开头的 ID。

回到第 4 步，新建 `MOMO_NOTEPAD_ID` 并填入。

若尚无云词本，先在墨墨 App 中新建一个空词本，再重新运行 Doctor。

## 第 6 步 首次同步

1. 点击 **Actions** → 左侧选择 **Sync**
2. 点击 **Run workflow**，模式下拉框选 **full**，确认运行
3. 约一两分钟后出现运行记录，状态显示为成功即可
4. 打开墨墨 App 进入该云词本，应能看到全部词条，按日期分段

第一次选 `full`，历史词一次性搬完。之后每天自动运行的是增量，只写新词。

## 第 7 步 后续运行

每天北京时间 06:30 自动运行一次，只有出现新词时才推送通知（需先配置通知）。

调整时间：编辑 `.github/workflows/sync.yml` 中的 `cron: "30 22 * * *"`。该表达式使用 UTC，比北京时间晚 8 小时，22:30 即次日 06:30。

## 故障排查

| 现象 | 原因 | 处理方式 |
|---|---|---|
| 运行记录标记为失败 | 某一步执行出错 | 打开该次运行，展开 **Sync** 步骤，查看报错行 |
| 日志出现 401 | token 无效或已过期 | 在墨墨 App 重新生成，更新对应的 Secret |
| 日志出现 403 | 触发欧路接口限流（30 次/分钟） | 等待约一小时后重试，期间不要连续触发 |
| 提示缺少 Secret | Secret 名称拼写不一致 | 按第 4 步的表格逐字核对，注意大小写与下划线 |
| 云词本内容未变化 | 欧路侧没有新增词条 | 正常，无需处理 |
| 词条已在云词本中，但墨墨无法学习 | 墨墨词典未收录该词条 | 正常，词组、缩写与中文条目均如此 |

## 通知（可选）

同步结果可以通过 webhook 推送。任何接受 GET 或 POST 的地址都能用，企业微信、钉钉、Server 酱均验证过。

在 Secrets 中新增以下变量：

| 变量 | 必填 | 说明 |
|---|---|---|
| `NOTIFY_URL` | 是 | webhook 地址 |
| `NOTIFY_BODY` | 否 | POST 请求体模板，`{content}` 会被替换为消息正文；不填则以 GET 方式携带 `content` 查询参数 |
| `NOTIFY_ALWAYS` | 否 | 填 `1` 时每轮都推送；默认只在有新词时推送 |

推送策略：有新词写入时推送摘要，同步失败时推送错误原因，无新增且未设 `NOTIFY_ALWAYS` 时不推送。

**企业微信群机器人**：群聊右上角「···」→ 群机器人 → 添加 → 复制 Webhook 地址，然后配置：

| 变量 | 值 |
|---|---|
| `NOTIFY_URL` | `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的KEY` |
| `NOTIFY_BODY` | `{"msgtype":"text","text":{"content":"{content}"}}` |

钉钉群机器人同样是 POST JSON，`NOTIFY_BODY` 写法一致。

**Server 酱**用 GET，`{content}` 放在 URL 里：

```
NOTIFY_URL=https://sctapi.ftqq.com/你的KEY.send?title=单词同步&desp={content}
```

消息正文是一行摘要，形如：

```
已写入｜模式=incremental · 欧路匹配 12 · 新增 12 · 云词本共 6076 词 / 391 段 · 请求 3 次
```

通知发送失败不会影响同步结果，只在日志中留下一条警告。

## 不使用 GitHub 的运行方式

下面四种方式都能替代 GitHub Actions，配置来源相同：环境变量，或与程序同目录的 `.env` 文件。

**一、单次运行**

需要 Python 3.10 或更高版本。

```bash
pip install -r requirements.txt
cp .env.example .env                     # 填写三个必需变量
python -m eudic2maimemo doctor           # 确认配置可用
python -m eudic2maimemo sync --full      # 首次全量
python -m eudic2maimemo sync             # 之后增量
```

**二、常驻服务**

程序内置循环，启动后按固定间隔重复执行，不依赖系统的计划任务工具。

```bash
python -m eudic2maimemo serve --interval 24
```

用 systemd 托管：把 `deploy/eudic2maimemo.service` 复制到 `/etc/systemd/system/`，修改其中的工作目录与运行用户，然后：

```bash
systemctl daemon-reload
systemctl enable --now eudic2maimemo
```

**三、Docker**

```bash
docker compose up -d                                   # 按 .env 启动，默认 serve，间隔 24 小时
docker compose run --rm eudic2maimemo sync --full      # 单独跑一次全量
```

镜像需要本地构建（`docker compose up` 会自动 build），也可以手动 `docker build -t eudic2maimemo .`。

**四、预编译二进制配合系统计划任务**

从 Releases 下载对应平台的文件并解压，在程序同目录放置 `.env`，或改用同名环境变量。

Linux / macOS 用 cron：

```bash
0 7 * * * cd /opt/eudic2maimemo && ./eudic2maimemo sync
```

Windows 用任务计划程序：创建基本任务 → 触发器选每天 → 操作选「启动程序」，程序填写 `eudic2maimemo.exe` 的完整路径，参数填 `sync`，起始位置填程序所在目录。

四种方式的取舍：调试或一次性搬运用第一种；长期无人值守优先第二种，间隔由程序自己管理，日志连续；已有容器环境用第三种；不想安装 Python 用第四种。

## 进阶配置

默认只把一个生词本写进一个云词本。下面几项按需开启，都可以写在 `.env` 或仓库 Variables 里。

**多个生词本分流**

欧路里如果分了「生词」「熟识」几个本子，可以让它们各自对应不同的云词本：

```
EUDIC_ROUTES=0=np-aaaa;133716565810649835=np-bbbb
```

左侧是欧路生词本 ID，右侧是墨墨云词本 ID。没在这里列出的生词本，仍然写入 `MOMO_NOTEPAD_ID`。写入时会沿用云词本原有的标题，不会把别人的词本改名。

**只同步高频词**

```
MIN_STAR=4
```

低于该星级的词条跳过，报告里会单独显示跳过了多少个。`--min-star N` 可以单次覆盖。

**全量重建时保留手动词条**

```
KEEP_ORPHANS=1
```

云词本里那些欧路没有的词（你自己加的），会集中放到末尾的「手动保留」段，而不是被清掉。命令行对应 `--keep-orphans`。

**触发限流后等一会儿再试**

```
python -m eudic2maimemo sync --wait-on-limit 3600
```

欧路限流封停约一小时，这个参数会让程序睡够时间再重试一次。适合自己机器上的 `serve`；GitHub Actions 有 15 分钟作业上限，不要在那里用。

## 常用命令

| 命令 | 作用 |
|---|---|
| `sync` | 增量同步，只写新词 |
| `sync --full` | 按欧路词表重建云词本 |
| `sync --dry-run` | 预览将要写入的内容 |
| `sync --min-star 4` | 只同步 4 星及以上的词条 |
| `sync --keep-orphans` | 全量重建时保留手动词条 |
| `doctor` | 检查配置，列出所有生词本和云词本 |
| `doctor --deep` | 翻完整个词本，报告哪些词还没同步 |
| `doctor --dict` | 核对墨墨词典能否查到这些词条 |
| `stats` | 词本画像：总数、星级、缺音标、近月新增 |
| `export --out words.csv --format csv` | 导出全部词表 |

## 已知限制

- 欧路接口单方向最多读 5100 条，双向并集约 10200 条封顶，词本特别大可能覆盖不全
- 墨墨的云词本接口只能整段覆盖写入，每次同步都会传全文
- 不同步删除：欧路删词，墨墨那边不会跟着删
- `sync --full` 默认会清掉你手动加进云词本的词（加 `--keep-orphans` 可保留），运行前会提示数量
- `--min-star` 在全量重建时同样生效，低于阈值的词不会写回云词本
- 只支持欧路的四种语言：英、法、德、西

## 数据安全

- 密钥只在你仓库的 Secrets 里，代码和日志里都没有
- 程序只读你的欧路生词本，只写你指定的那一个云词本
- 除了 `--full`，其他操作都不会删你自己的词

## 开发

```bash
pip install -r requirements.txt -r requirements-dev.txt
coverage run --source=eudic2maimemo -m unittest discover -s tests -t .
coverage report -m
```

137 个用例，CI 里跑 ruff 检查并设 80% 覆盖率门槛。

MIT

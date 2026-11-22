# Potplayer-LMTranslate

PotPlayer 实时字幕翻译插件，对接任意 **OpenAI 兼容 LLM API**（SiliconFlow、DeepSeek、OpenAI、Moonshot、智谱、阿里百炼、OpenRouter、Ollama、LM Studio 等），支持 **provider 配置文件** 与 **滚动上下文翻译**。

![icon](SubtitleTranslate%20-%20LMTranslate.ico)

## 特性

- **两个输入框搞定配置**：模型框填 `provider-id/model-id`，密钥框填 API Key
- **图形化配置工具**：`SubtitleTranslate - LMTranslate.exe`（Releases 下载）可视化管理服务商、上下文、默认模型/密钥，一键测试 API 连通
- **YAML 默认配置**：`default_model` / `api_key` 写进 YAML 后，PotPlayer 面板两个框留空即可自动使用
- **provider 与模型解耦**：服务商地址统一在 YAML 里维护，换模型不用改 URL
- **模型名可含斜线**：按第一个 `/` 分割，`siliconflow/Qwen/Qwen2.5-7B-Instruct` 这类带斜线的模型名直接支持
- **滚动上下文**：最近 N 条「原文→译文」作为多轮对话历史发给模型，人名、代词、术语前后一致，接得住被拆成多条字幕的半句话
- **换视频自动清空上下文**；连续重复字幕复用上次译文，省 API 调用
- 上下文条数可配置（`context: 8`，`0`/`off` 关闭）

## 安装

从 [Releases](../../releases) 下载 **`LMTranslate-v1.3.0-win64.zip`**，把包内 4 个文件解压到 PotPlayer 安装目录的扩展文件夹（需要管理员权限）：

```
C:\Program Files\DAUM\PotPlayer\Extension\Subtitle\Translate\
  ├─ SubtitleTranslate - LMTranslate.as     插件本体
  ├─ SubtitleTranslate - LMTranslate.ico    图标
  ├─ SubtitleTranslate - LMTranslate.yaml   provider 与上下文配置
  └─ SubtitleTranslate - LMTranslate.exe    图形化配置工具
```

> 以 zip 发布是为了保留文件名中的空格（GitHub 会把单独上传的资产文件名里的空格转成点）。

重启 PotPlayer。

> 需要支持实时字幕翻译的 PotPlayer 版本（250909 及以上）。

## 配置

### 1. 编辑 YAML

`SubtitleTranslate - LMTranslate.yaml`：

```yaml
# 保留最近 8 条字幕作为翻译上下文（0 或 off 关闭）
context: 8

# 可选：默认模型与密钥（面板留空时自动使用；api_key 明文存储，注意保密）
default_model: siliconflow/Qwen/Qwen2.5-7B-Instruct
api_key: sk-xxxx

providers:
  siliconflow: https://api.siliconflow.cn/v1
  deepseek: https://api.deepseek.com/v1
  openai: https://api.openai.com/v1
  ollama: http://localhost:11434/v1
```

- 地址填到 `/v1` 这一层即可，插件自动补 `/chat/completions`（填完整端点也行）
- `provider-id` 不能含 `/`；`#` 后是注释
- 改完无需重启，每次在面板里确认配置时重新读取

### 2. PotPlayer 里填写

右键 → 字幕 → 实时字幕翻译 → 引擎选 **LMTranslate 翻译** → 打开配置：

| 输入框 | 内容 | 示例 |
|---|---|---|
| 模型 | `provider-id/model-id`（留空则用 YAML 的 `default_model`） | `siliconflow/Qwen/Qwen2.5-7B-Instruct` |
| API 密钥 | 服务商的 Key（留空则用 YAML 的 `api_key`） | `sk-xxxx` |

播放视频即可看到翻译字幕。

### 3. 图形化配置（推荐）

完整包已含 `SubtitleTranslate - LMTranslate.exe`（也可单独从源码打包），放到插件同目录（或任意位置），双击运行（自动请求管理员权限以便写入 Program Files）：

- 服务商列表增删改（provider-id + API 地址）
- 上下文条数、默认模型、API 密钥（可隐藏显示）
- **测试 API 连通**：用当前默认模型发一条真实翻译请求，直接看到模型响应或错误详情
- 保存即写回 YAML，插件下次读取自动生效

源码在 `config-tool/LMTranslateConfig.py`（Python 3 + tkinter），自行打包：

```bat
pyinstaller --onefile --windowed --uac-admin --name "SubtitleTranslate - LMTranslate" ^
    --icon "SubtitleTranslate - LMTranslate.ico" config-tool\LMTranslateConfig.py
```

## 文件说明

| 文件 | 说明 |
|---|---|
| `SubtitleTranslate - LMTranslate.as` | AngelScript 插件源码 |
| `SubtitleTranslate - LMTranslate.yaml` | provider / 上下文配置（可自由增删服务商） |
| `SubtitleTranslate - LMTranslate.ico` | 引擎列表图标 |
| `config-tool/LMTranslateConfig.py` | 图形化配置工具源码（exe 见 Releases） |

## 实现备注

- 请求为标准 OpenAI `chat/completions` 格式：system 提示词 + 历史 user/assistant 轮次 + 当前字幕，`temperature: 0`
- 适配 PotPlayer 的 AngelScript 字符串方言（`.find` / `.MakeLower` / `.Trim` 返回新串等），不依赖 `find_first_of`、`ToLower` 等不存在的方法
- 上下文窗口、provider 解析均为纯脚本实现，无外部依赖
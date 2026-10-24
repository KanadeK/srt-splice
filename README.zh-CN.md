# srt-splice 中文说明

按视频剪辑清单重排已有 SRT 字幕，支持保留片段的重排和重复使用，输出新字幕以及
逐条来源回执。无需上传视频或字幕，无需模型、密钥、外部服务或运行时第三方依赖。
要求 Python 3.11 及以上。

```sh
git clone https://github.com/KanadeK/srt-splice.git
cd srt-splice
python -m pip install .
srt-splice examples/source.srt examples/edits.json --dry-run
srt-splice examples/source.srt examples/edits.json --out work-output
python examples/check_example.py
```

清单格式：`{"schema_version":1,"clips":[{"start_ms":1000,"end_ms":5000}]}`。
时间必须是原始视频中的整数毫秒，区间为左闭右开，按数组顺序直接拼接。
请使用视频实际导出的切点；无损剪辑的关键帧取整可能导致实际切点和计划不同。

输出目录必须尚不存在，其父目录必须已存在。`output.srt` 为新字幕，`receipt.json`
记录每条原字幕去了哪里、是否被裁短、是否形成多个片段，以及输入输出哈希。
回执不含字幕文字或输入路径。`--dry-run` 只做校验和计算，不写文件。

当前版本 0.1.0 仅支持严格 UTF-8 SRT；不支持 VTT、ASS、NLE 工程、变速、转场或
语音识别。跨切口的字幕会在各片段中保留整句文字，因此必须检查其语义，不能据此
认定视频已通过无障碍质量验收。输入只读，输出不会覆盖已有目录；磁盘写入失败
可能留下不完整目录，需明确清理。

每个输入上限 8 MiB，最多 100,000 条字幕、1,000 个片段、5,000,000 次区间比较和
100,000 条输出字幕，输出保守体积预算为 32 MiB。时间轴上限 99:59:59,999。
重复 JSON 键、额外字段和错误类型会被拒绝，超限会明确报错。

退出码 `0` 成功（包括全部字幕被删掉的有效剪辑），`2` 输入或文件系统错误。
删除自己指定的输出目录即可清理；`python -m pip uninstall srt-splice` 卸载。
完整边界见 [英文 README](README.md) 和 [设计说明](docs/design.md)。

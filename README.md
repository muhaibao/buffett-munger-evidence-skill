# buffett-munger-evidence

一个 Claude Code / Claude Agent Skill：以巴菲特和芒格的**一手资料**（股东信、年会问答、演讲、访谈）为证据，按两人的思考顺序回答投资、商业与人生问题——先判断他们会不会接这个问题，再按他们的过滤标准给出“可以 / 不行 / 太难”的结论，最后附可核查的原文出处。

> A Claude skill that answers questions the way Warren Buffett and Charlie Munger would reason about them, grounded in a local, provenance-tracked corpus of their own letters, meeting transcripts, speeches and interviews. Every attributed claim must trace back to an opened source passage. Answers default to Chinese.

**这是基于本地资料库的检索增强问答，不是模型蒸馏，也不代表两人本人。** 未检索到不等于没说过；所有推演都会标明。

## 它做什么

- **两层回答**：先给人物回答（巴菲特讲结论、决定因素和一个真实案例；芒格一两句尖锐判断），再给依据层（完整原句引文 + 中文译意 + 出处链接 + 适用性说明）。
- **证据纪律**：只引用实际打开并核对过的完整句子；区分本人原作、发布者文字稿、第三方笔记、传记与译本；区分材料年份与发表日期；芒格去世（2023-11-28）后的事件不替他表态。
- **本地混合检索**：SQLite FTS5/BM25 + 本地 ONNX 多语言 E5 语义检索 + cross-encoder 重排，全部离线运行，原文不发送给外部服务。
- **配套工具**：年会问答单元检索（`qa.py`）、有出处的主题/案例 Wiki（`wiki.py`）、完整句子取句（`quote.py`）、发言人归属审核（`attribution.py`）、盲测评估（`evaluate.py`），以及从伯克希尔官网、CNBC 巴菲特档案等公开来源采集资料的脚本。

## 不包含什么

本仓库**不附带任何原文、电子书、视频或索引**。资料库在 skill 目录之外，由你在本机用采集脚本从公开来源自行建立；受版权保护的书籍只能由你用合法持有的副本自行导入，且不应再分发。

## 安装

```sh
git clone https://github.com/muhaibao/buffett-munger-evidence-skill ~/.claude/skills/buffett-munger-evidence
```

## 首次建库

详见 [references/local-library.md](references/local-library.md)、[references/collection.md](references/collection.md) 和 [references/retrieval.md](references/retrieval.md)。大致步骤：

```sh
SKILL=~/.claude/skills/buffett-munger-evidence
DATA=~/buffett-munger-data
LIB="$DATA/buffett-munger-library"
PY="$DATA/runtime/bin/python"

# 1. 独立 Python 环境（需要 uv）
uv venv --python 3.12 "$DATA/runtime"
uv pip install --python "$PY" -r "$SKILL/scripts/requirements-retrieval.txt" pypdf lxml brotli

# 2. 建库并采集公开资料
"$PY" "$SKILL/scripts/library.py" --library "$LIB" init
"$PY" "$SKILL/scripts/collect.py" --library "$LIB" --kind buffett-letters
"$PY" "$SKILL/scripts/collect.py" --library "$LIB" --kind wesco-letters
STAGE="$DATA/staging/first"
"$PY" "$SKILL/scripts/collect_meetings.py" --output "$STAGE/meetings" --from-year 1994 --to-year 2024 --workers 3
"$PY" "$SKILL/scripts/merge_staged.py" --library "$LIB" --report "$STAGE/merge-report.json" "$STAGE/meetings/manifest.json"

# 3. 下载本地模型并建索引
"$PY" "$SKILL/scripts/setup_retrieval.py" --models-dir "$LIB/retrieval/models"
"$PY" "$SKILL/scripts/retrieve.py" --library "$LIB" build --max-tokens 512 --batch-size 32
"$PY" "$SKILL/scripts/qa.py" --library "$LIB" build
```

然后在 Claude Code 里提问，例如“巴菲特会怎么看一家技术变化很快的消费电子公司？”或用 `/buffett-munger-evidence` 调用。

## 测试

```sh
cd ~/.claude/skills/buffett-munger-evidence/scripts
"$PY" -m unittest discover -p 'test_*.py'
```

## 目录

| 路径 | 内容 |
|---|---|
| `SKILL.md` | 技能入口：回答协议、输出格式、证据底线 |
| `references/` | 思考顺序（`cognition.md`）、证据规则、检索、采集、Wiki、评估、来源地图 |
| `scripts/` | 资料库、检索、问答、Wiki、取句、归属、评估与采集脚本及测试 |
| `assets/` | 已核验的来源入口、人工审核的归属表、演讲章节链接记录 |

## 声明

与伯克希尔·哈撒韦公司、巴菲特、芒格及其家族或代理人没有任何关联，也未获其认可。输出不构成投资建议。引用的原文版权归各自权利人所有。

## 许可

代码与文档以 [MIT License](LICENSE) 发布。

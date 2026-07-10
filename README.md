# DockFlow：可复用分子对接流程

Linux 优先的模块化工作流。新项目只需要替换 `config/targets.tsv`、`inputs/ligands/` 和软件路径，不需要重新拼接命令。

支持两种结构入口：`structure_source=pdb` 自动下载 RCSB PDB，或 `structure_source=local` 使用自己的 PDB 文件。口袋不依赖原配体：有共晶配体用 `co_crystal`；没有原配体可用 `explicit_box`、`residue_box` 或 `blind`。盲对接结果会被标记为探索性，不能伪装成有共晶证据的结果。

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
cp config/targets.example.tsv config/targets.tsv
cp config/config.example.yaml config/config.yaml
python -m dockflow.cli check --config config/config.yaml
```

随后把配体放入 `inputs/ligands/`，按实际结构修改 `config/targets.tsv`。当前仓库的结构检查和口袋解析核心可以直接运行；PyMOL、Open Babel、MGLTools、Vina 和 PLIP 的批处理适配器按配置接入，软件不随仓库分发。

## 口袋策略

`co_crystal` 需要当前结构中存在配体；`explicit_box` 需要中心和尺寸；`residue_box` 需要残基编号；`blind` 使用覆盖受体的探索性盒子。没有参考配体时，结果表中的参考距离保持为空，避免误解释。

## 数据安全

个人路径、原始会话 JSON、大型结构和计算结果均被 `.gitignore` 排除。请只提交小型示例与配置模板。


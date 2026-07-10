# DockFlow：AutoDock/Vina 批量分子对接流程

DockFlow 将受体获取、口袋定义、AutoDockTools PDBQT 预处理、Open Babel 配体格式转换、AutoDock Vina 批量对接、结果汇总和可选 PLIP 分析串联成可断点续跑的工作流。以后开展新项目时，只需提供受体信息、配体文件和口袋依据，不需要重新拼接脚本。

## 推荐：交互式新建项目

运行：

```bash
dockflow wizard
```

向导会依次要求输入项目名称、4位 PDB ID 或本地 PDB 路径，并自动下载或复制结构、检测蛋白链和可能的共晶配体。检测到候选配体时会列出残基名、链、残基号和原子数供选择；没有明显共晶配体时默认建立盲对接配置。

每次向导都会创建一个独立目录，例如：

```text
runs/20260711_093000_project_name/
  config/
  inputs/structures/
  inputs/ligands/
  work/
  results/
  logs/
  RUN_INFO.txt
```

不同运行的输入、中间文件、结果和日志不会混在一起。把待对接配体放入该运行目录的 `inputs/ligands/` 后，按向导输出的命令运行即可。

外部工具路径按以下顺序解析：配置中的明确路径、系统 PATH、`DOCKFLOW_TOOLS_DIR` 和少量常见安装目录。发现多个候选时不会静默猜测，需在配置中明确指定。

## 常见输入情况

受体可以直接填写 RCSB PDB ID，也可以使用本地 PDB。口袋支持四种情况：存在共晶配体时用 `co_crystal`；没有原配体但知道口袋坐标时用 `explicit_box`；知道关键残基时用 `residue_box`；没有可靠口袋信息时用 `blind`，但结果会明确标记为探索性。对含金属或必要辅因子的受体，可在 `keep_hetero_resnames` 中指定保留。

配体目录支持 PDB、SDF、MOL2、MOL、SMI、SMILES 和 PDBQT。除已经是 PDBQT 的配体外，其余格式先由 Open Babel 转成 PDB，再由 AutoDockTools `prepare_ligand4.py` 生成 PDBQT。受体由 `prepare_receptor4.py` 生成 PDBQT。

## 安装

自行安装 Python 3.10+、MGLTools/AutoDockTools、Open Babel、AutoDock Vina；PLIP 为可选。仓库不包含第三方软件本体、许可证、密码或 Token。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
```

也可以跳过向导，复制示例配置并手工编辑：

```bash
cp config/config.example.yaml config/config.yaml
cp config/targets.example.tsv config/targets.tsv
mkdir -p inputs/ligands
```

## 运行

```bash
dockflow check --config config/config.yaml
dockflow all --config config/config.yaml
```

同时执行 PLIP：

```bash
dockflow all --config config/config.yaml --with-plip
```

也可分阶段运行：

```bash
dockflow pockets --config config/config.yaml
dockflow prepare-receptors --config config/config.yaml
dockflow prepare-ligands --config config/config.yaml
dockflow dock --config config/config.yaml
dockflow summarize --config config/config.yaml
dockflow plip --config config/config.yaml
```

`--force` 会覆盖已有中间结果。默认采用全部受体×全部配体；某个受体只对接指定配体时，在 `targets.tsv` 的 `ligands` 列填写逗号分隔的配体文件名（不含扩展名）。

## targets.tsv 关键字段

- `structure_source`：`pdb` 或 `local`。
- `structure`：PDB ID 或相对项目根目录的本地 PDB 路径。
- `pocket_strategy`：`co_crystal`、`explicit_box`、`residue_box` 或 `blind`。
- `receptor_chains`：保留的蛋白链，可填写 `A` 或 `A,B`；留空表示全部链。
- `ligand`、`ligand_chain`、`ligand_residue_id`：共晶配体的残基名、链和残基号。
- `center_x/y/z`、`size_x/y/z`：显式盒子。
- `residue_ids`：定义口袋的蛋白残基号。
- `keep_hetero_resnames`：要保留的金属或辅因子，如 `ZN,HEM`。

## 输出与解释

`results/docking_summary.tsv` 包含最佳结合能、最佳 Vina 构象中心到参考配体中心的距离、证据等级和分类。共晶口袋、结合能达标且参考距离达标的结果标为 `reference_consistent`，表示与参考口袋位置一致，不代表已经通过实验验证。显式盒子和残基盒子保留为 `manual_review`；盲对接标为 `exploratory`。

## 测试

```bash
python -m compileall src tests
pytest -q
```

测试覆盖配置解析、交互式项目生成、共晶配体检测、无原配体口袋策略、受体清理、Vina结果解析和证据分级。GitHub Actions 在 Python 3.10、3.11 和 3.12 上运行。真实外部软件链仍需在安装了 MGLTools、Open Babel、Vina 和可选 PLIP 的机器上验证。

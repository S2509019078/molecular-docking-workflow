# DockFlow：AutoDock/Vina 批量分子对接流程

DockFlow 将受体获取、共晶口袋定义、AutoDockTools PDBQT 预处理、Open Babel 配体格式转换、AutoDock Vina 批量对接、结果汇总和可选 PLIP 分析串联为可断点续跑的命令行流程。仓库不包含 MGLTools、AutoDock Vina、Open Babel、PLIP 或任何第三方软件本体。

## 适用范围

- 多受体 × 多配体的批量小分子对接；
- 受体来自 RCSB PDB 或本地 PDB；
- 优先使用共晶配体定义口袋；
- 没有共晶配体时，可使用显式盒子、已知残基盒子或盲对接；
- 受体和配体最终均通过 AutoDockTools 生成 PDBQT；
- SDF、MOL2、MOL、PDB、SMILES 等配体格式先由 Open Babel 转成 PDB，再交给 `prepare_ligand4.py`。

## 环境要求

需要自行安装并配置：

- Python 3.10+
- MGLTools / AutoDockTools：`pythonsh`、`prepare_receptor4.py`、`prepare_ligand4.py`
- Open Babel
- AutoDock Vina
- PLIP（可选）

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
cp config/config.example.yaml config/config.yaml
cp config/targets.example.tsv config/targets.tsv
mkdir -p inputs/ligands
```

修改 `config/config.yaml` 中的软件路径，将配体放入 `inputs/ligands/`，再修改 `config/targets.tsv`。

```bash
python -m dockflow.cli check --config config/config.yaml
python -m dockflow.cli all --config config/config.yaml
```

需要同时运行 PLIP：

```bash
python -m dockflow.cli all --config config/config.yaml --with-plip
```

## 分阶段运行

```bash
python -m dockflow.cli pockets --config config/config.yaml
python -m dockflow.cli prepare-receptors --config config/config.yaml
python -m dockflow.cli prepare-ligands --config config/config.yaml
python -m dockflow.cli dock --config config/config.yaml
python -m dockflow.cli summarize --config config/config.yaml
python -m dockflow.cli plip --config config/config.yaml
python -m dockflow.cli status --config config/config.yaml
```

加 `--force` 可覆盖已有中间结果。

## 口袋策略

`co_crystal`：从当前 PDB 的指定 `HETATM` 配体定义盒子。推荐同时填写 `chain`、`ligand` 和 `ligand_residue_id`，避免同一结构中存在多个同名配体时混合计算。

`explicit_box`：填写中心坐标和盒子尺寸。

`residue_box`：填写链和逗号分隔的残基编号，程序根据这些蛋白原子定义盒子。

`blind`：盒子覆盖整条目标蛋白链，结果会标记为探索性。

示例中的 3O96 使用真实共晶配体 `IQO`，不是占位名称 `LIG`。

## 输出

- `work/raw/`：原始 PDB；
- `work/reference_ligands/`：提取的共晶配体；
- `work/receptors_clean/`：去除水、配体和其他 HETATM 后的蛋白 PDB；
- `work/receptors_pdbqt/`：AutoDockTools 生成的受体 PDBQT；
- `work/ligands_pdb/`：Open Babel 转换后的配体 PDB；
- `work/ligands_pdbqt/`：AutoDockTools 生成的配体 PDBQT；
- `work/poses/`：Vina 构象；
- `results/docking_summary.tsv`：最佳结合能、与参考口袋中心距离、证据等级和结果分类；
- `results/plip/`：可选 PLIP 报告。

## 结果解释

`high_confidence` 仅用于有共晶口袋证据、结合能达到阈值且最佳构象中心接近参考配体中心的结果。显式盒子和残基盒子结果即使能量达标，也保留为 `manual_review`；盲对接结果标记为 `exploratory`。

## 测试

```bash
python -m compileall src tests
pytest -q
```

GitHub Actions 会在 Python 3.10、3.11 和 3.12 上运行测试。外部软件不在单元测试中调用，真实对接仍需在本地安装相应程序后执行。

## 数据安全

仓库的 `.gitignore` 排除了原始结构、配体、PDBQT、中间结果和日志。不要提交个人路径、密码、Token、许可证文件或第三方软件本体。

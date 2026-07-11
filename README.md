# DockFlow：AutoDock/Vina 批量分子对接流程

DockFlow 将受体获取、口袋定义、AutoDockTools PDBQT 预处理、Open Babel 配体格式转换、AutoDock Vina 批量对接、结果汇总和可选 PLIP 分析串联成可断点续跑的工作流。以后开展新项目时，只需提供受体信息、配体文件和口袋依据，不需要重新拼接脚本。

## Windows 图形界面版

GitHub Actions 会自动构建两个 Windows 程序：

```text
DockFlow.exe       图形桌面版，普通用户双击使用
DockFlow-CLI.exe   命令行版，用于自动化和故障排查
```

双击 `DockFlow.exe` 后直接进入桌面界面，不再打开终端向导。界面分为四个工作区：

- **新建项目**：输入 4 位 PDB ID 或选择本地 PDB，自动检测蛋白链和可能的共晶配体，批量添加 SDF、MOL2、PDB、PDBQT 等配体文件；
- **运行中心**：检查外部依赖、启动完整对接流程、停止任务并查看实时日志；
- **结果分析**：读取 `docking_summary.tsv`，展示靶标、配体、结合能、参考口袋距离和证据等级；
- **工具设置**：自动检测或手动选择 Vina、Open Babel、MGLTools/AutoDockTools 和可选 PLIP 的路径。

默认项目目录为：

```text
Documents\DockFlow\runs\
```

每个项目使用独立目录保存配置、输入、中间文件、日志和结果。当前图形版已提供搜索强度、输出构象数、CPU线程数和口袋边界扩展等常用参数。

当前安装包仍不内置以下第三方程序：

```text
AutoDock Vina
Open Babel
MGLTools / AutoDockTools
PLIP（可选）
```

这些程序需单独安装，然后在“工具设置”页面自动检测或手动指定路径。

## 下载 Windows 构建包

进入仓库的 **Actions** 页面，选择最新通过的 `windows-exe` 运行记录，在页面底部下载：

```text
DockFlow-Windows-x64-GUI
```

解压后将 `DockFlow.exe` 和 `DockFlow-CLI.exe` 放在同一目录。图形程序运行任务时会调用同目录下的命令行程序。

## 命令行与交互式向导

仍可使用 Python 命令行版本：

```bash
dockflow wizard
dockflow check --config config/config.yaml
dockflow all --config config/config.yaml
```

Windows 构建包中的等价命令为：

```powershell
DockFlow-CLI.exe check --config path\to\config.yaml
DockFlow-CLI.exe all --config path\to\config.yaml
```

交互式终端向导会依次要求输入项目名称、4位 PDB ID 或本地 PDB 路径，并自动下载或复制结构、检测蛋白链和可能的共晶配体。

## 项目目录

```text
runs/20260711_093000_project_name/
  config/
    config.yaml
    targets.tsv
  inputs/structures/
  inputs/ligands/
  work/
  results/
  logs/
  RUN_INFO.txt
```

不同运行的输入、中间文件、结果和日志不会混在一起。外部工具路径按以下顺序解析：配置中的明确路径、系统 PATH、`DOCKFLOW_TOOLS_DIR` 和少量常见安装目录。发现多个候选时不会静默猜测，需明确指定。

## 常见输入情况

受体可以直接填写 RCSB PDB ID，也可以使用本地 PDB。口袋支持四种情况：存在共晶配体时用 `co_crystal`；没有原配体但知道口袋坐标时用 `explicit_box`；知道关键残基时用 `residue_box`；没有可靠口袋信息时用 `blind`，但结果会明确标记为探索性。对含金属或必要辅因子的受体，可在 `keep_hetero_resnames` 中指定保留。

配体目录支持 PDB、SDF、MOL2、MOL、SMI、SMILES 和 PDBQT。除已经是 PDBQT 的配体外，其余格式先由 Open Babel 转成 PDB，再由 AutoDockTools `prepare_ligand4.py` 生成 PDBQT。受体由 `prepare_receptor4.py` 生成 PDBQT。

## 从源码安装

自行安装 Python 3.10+、MGLTools/AutoDockTools、Open Babel、AutoDock Vina；PLIP 为可选。

命令行版：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
```

图形界面版：

```bash
pip install -e '.[gui]'
dockflow-gui
```

## 分阶段运行

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

- `structure_source`：`pdb` 或 `local`；
- `structure`：PDB ID 或相对项目根目录的本地 PDB 路径；
- `pocket_strategy`：`co_crystal`、`explicit_box`、`residue_box` 或 `blind`；
- `receptor_chains`：保留的蛋白链；
- `ligand`、`ligand_chain`、`ligand_residue_id`：共晶配体信息；
- `center_x/y/z`、`size_x/y/z`：显式盒子；
- `residue_ids`：定义口袋的蛋白残基号；
- `keep_hetero_resnames`：要保留的金属或辅因子，如 `ZN,HEM`。

## 输出与解释

`results/docking_summary.tsv` 包含最佳结合能、最佳 Vina 构象中心到参考配体中心的距离、证据等级和分类。共晶口袋、结合能达标且参考距离达标的结果标为 `reference_consistent`，表示与参考口袋位置一致，不代表已经通过实验验证。显式盒子和残基盒子保留为 `manual_review`；盲对接标为 `exploratory`。

## 测试

```bash
python -m compileall src tests
pytest -q
```

测试覆盖配置解析、桌面项目服务、交互式项目生成、Windows 启动器、共晶配体检测、受体清理、Vina结果解析和证据分级。GitHub Actions 在 Python 3.10、3.11 和 3.12 上运行，同时使用 Windows runner 构建 GUI 与 CLI，并对图形界面做无显示器启动测试。真实外部软件链仍需在安装了 MGLTools、Open Babel、Vina 和可选 PLIP 的机器上验证。

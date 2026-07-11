# DockFlow：AutoDock/Vina 批量分子对接流程

DockFlow 将受体获取、口袋定义、配体库管理、AutoDockTools PDBQT 预处理、Open Babel 配体格式转换、AutoDock Vina 批量对接、结果汇总和可选 PLIP 分析串联成可断点续跑的工作流。

## Windows 图形界面版

GitHub Actions 会自动构建两个 Windows 程序：

```text
DockFlow.exe       图形桌面版，普通用户双击使用
DockFlow-CLI.exe   命令行版，用于自动化和故障排查
```

双击 `DockFlow.exe` 后直接进入桌面界面。主要功能包括：

- **新建项目**：输入 4 位 PDB ID 或选择本地 PDB，自动检测蛋白链和可能的共晶配体；
- **配体库**：从本地文件、单个 SMILES 或 PubChem CID/化合物名称导入小分子；
- **运行中心**：检查外部依赖、启动完整对接流程、停止任务并查看实时日志；
- **结果分析**：读取 `docking_summary.tsv`，展示靶标、配体、结合能、参考口袋距离和证据等级；
- **工具设置**：自动检测或手动选择 Vina、Open Babel、MGLTools/AutoDockTools 和可选 PLIP 的路径。

### 配体库入口

点击“添加配体文件”会打开配体库窗口，而不是单纯的文件选择框。配体库支持三种输入方式：

1. **本地文件**：SDF、MOL2、MOL、PDB、PDBQT、SMI 和 SMILES；
2. **SMILES**：输入化合物名称和单个 SMILES，程序生成独立 `.smi` 文件；
3. **PubChem**：输入 CID 或化合物名称，优先下载 3D SDF，没有 3D 记录时回退到普通 SDF。

导入时会检查空文件、不支持的格式、多分子 SDF、多条 SMILES，以及包含多个片段的盐或复合物 SMILES。存在风险提示时，创建项目之前会再次确认。每个项目都会保存：

```text
inputs/ligands/LIGAND_SOURCES.tsv
```

该文件记录配体名称、来源、格式、检查状态、警告和原始文件名，便于追溯。

当前版本不内置 RDKit。三维构象生成、补氢、格式转换和 PDBQT 准备仍由 Open Babel 与 AutoDockTools 完成，避免安装包体积和依赖复杂度过早膨胀。

默认项目目录为：

```text
Documents\DockFlow\runs\
```

每个项目使用独立目录保存配置、输入、中间文件、日志和结果。图形版提供搜索强度、输出构象数、CPU线程数和口袋边界扩展等常用参数。

## 外部依赖

当前安装包仍不内置：

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

```bash
dockflow wizard
dockflow check --config config/config.yaml
dockflow all --config config/config.yaml
```

Windows 构建包中的等价命令：

```powershell
DockFlow-CLI.exe check --config path\to\config.yaml
DockFlow-CLI.exe all --config path\to\config.yaml
```

## 项目目录

```text
runs/20260711_093000_project_name/
  config/
    config.yaml
    targets.tsv
  inputs/structures/
  inputs/ligands/
    LIGAND_SOURCES.tsv
  work/
  results/
  logs/
  RUN_INFO.txt
```

## 常见输入情况

受体可以直接填写 RCSB PDB ID，也可以使用本地 PDB。口袋支持四种情况：存在共晶配体时用 `co_crystal`；知道口袋坐标时用 `explicit_box`；知道关键残基时用 `residue_box`；没有可靠口袋信息时用 `blind`。对含金属或必要辅因子的受体，可在 `keep_hetero_resnames` 中指定保留。

除已经是 PDBQT 的配体外，其余格式先由 Open Babel 转成 PDB，再由 AutoDockTools `prepare_ligand4.py` 生成 PDBQT。受体由 `prepare_receptor4.py` 生成 PDBQT。

## 从源码安装

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

## 输出与解释

`results/docking_summary.tsv` 包含最佳结合能、最佳 Vina 构象中心到参考配体中心的距离、证据等级和分类。`reference_consistent` 表示结果与参考口袋位置一致，不等同于实验验证。

## 测试

```bash
python -m compileall src tests
pytest -q
```

测试覆盖配置解析、配体库输入与风险提示、桌面项目服务、交互式项目生成、Windows 启动器、共晶配体检测、受体清理、Vina结果解析和证据分级。GitHub Actions 在 Python 3.10、3.11 和 3.12 上运行，并在 Windows runner 上构建 GUI 与 CLI、执行无显示器 GUI 启动测试。真实外部软件链仍需在安装了 MGLTools、Open Babel、Vina 和可选 PLIP 的机器上验证。

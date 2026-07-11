from __future__ import annotations

import sys
import traceback


def _smoke_test() -> int:
    try:
        import gemmi  # noqa: F401
        import meeko  # noqa: F401
        import rdkit  # noqa: F401
        from meeko.cli.mk_prepare_ligand import main as _main  # noqa: F401
    except Exception:
        traceback.print_exc()
        return 1
    print("DockFlow Meeko ligand helper OK")
    return 0


def main() -> int:
    if sys.argv[1:] == ["--smoke-test"]:
        return _smoke_test()
    from meeko.cli.mk_prepare_ligand import main as meeko_main

    result = meeko_main()
    return int(result or 0)


if __name__ == "__main__":
    raise SystemExit(main())

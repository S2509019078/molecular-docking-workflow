from __future__ import annotations


def main() -> int:
    from meeko.cli.mk_prepare_receptor import main as meeko_main

    result = meeko_main()
    return int(result or 0)


if __name__ == "__main__":
    raise SystemExit(main())

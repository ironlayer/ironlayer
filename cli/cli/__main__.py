"""Entry point for `python -m cli` and `ironlayer` console script."""

from __future__ import annotations

from cli.app import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()

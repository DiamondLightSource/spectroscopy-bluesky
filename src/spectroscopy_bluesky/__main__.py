"""Interface for ``python -m spectroscopy_bluesky``."""

from spectroscopy_bluesky.cli import cli

__all__ = ["main"]


def main():
    cli()


if __name__ == "__main__":
    main()

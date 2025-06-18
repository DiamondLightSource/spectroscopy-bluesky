"""Interface for ``python -m spectroscopy_bluesky``."""

from argparse import ArgumentParser
from collections.abc import Sequence

from . import __version__

__all__ = ["main"]


def main(args: Sequence[str] | None = None) -> None:
    """Argument parser for the CLI."""
    parser = ArgumentParser()
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=__version__,
    )
    parser.add_argument(
        "-g",
        "--generate",
    )
    parser.parse_args(args)

    # todo fix this really
    if args.__getattribute__("generate"):
        print(
            "This command is not implemented yet. "
            "Please use the `spectroscopy_bluesky` package directly."
        )


if __name__ == "__main__":
    main()

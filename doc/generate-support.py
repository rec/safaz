"""Regenerate the published catalog from the installed safaz registry."""

from pathlib import Path

from safaz.registry import support_table


def generate() -> None:
    Path(__file__).with_name('sfz-support.md').write_text(support_table())


if __name__ == '__main__':
    generate()

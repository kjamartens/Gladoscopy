"""Regenerate the 720 px splash used at runtime from the oversampled source.

The source ``GUI/Icons/GladosSplash_inv.png`` (light, 4372x2613, ~2.7 MB) takes ~350 ms
just to load, which the startup splash cannot afford. Both the startup splash and the
backend dialog use the downscaled copy this writes. Re-run after editing the source::

    python -m scripts.make_splash_images
"""

import sys
from pathlib import Path

from PIL import Image

ICONS = Path(__file__).resolve().parents[1] / 'glados_pycromanager' / 'GUI' / 'Icons'
SOURCE = ICONS / 'GladosSplash_inv.png'
TARGET = ICONS / 'GladosSplash_720.png'
WIDTH = 720


def make_splash(source: Path = SOURCE, target: Path = TARGET, width: int = WIDTH) -> tuple[int, int]:
    image = Image.open(source).convert('RGB')
    size = (width, round(image.height * width / image.width))
    image.resize(size, Image.LANCZOS).save(target, optimize=True)
    return size


if __name__ == '__main__':
    size = make_splash()
    print(f'wrote {TARGET} ({size[0]}x{size[1]}, {TARGET.stat().st_size // 1024} KB)')
    sys.exit(0)

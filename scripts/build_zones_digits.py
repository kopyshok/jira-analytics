"""Цифры одинаковой ширины для скина «Цветовые зоны».

У Wix Madefor Text нет табличных цифр (нет признака tnum), и числа в колонках
таблиц «гуляют». Скрипт берёт цифры 0–9 из шрифта пакета @fontsource,
ставит всем ширину самой широкой цифры (глиф по центру) и сохраняет отдельный
крошечный шрифт «Zones Digits». В CSS он стоит первым в списке шрифтов
интерфейса и покрывает только цифры — остальные знаки идут из Wix Madefor.

Шрифт под лицензией SIL OFL 1.1 — производный шрифт переименован, лицензия
лежит рядом (OFL.txt).

Запуск из корня репозитория: py -3.10 scripts/build_zones_digits.py
"""

from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "node_modules" / "@fontsource" / "wix-madefor-text"
OUT = ROOT / "frontend" / "src" / "aurora" / "styles" / "skins" / "fonts"
WEIGHTS = (400, 500, 600, 700)
DIGITS = "0123456789"
FAMILY = "Zones Digits"


def build(weight: int) -> Path:
    font = TTFont(SRC / "files" / f"wix-madefor-text-latin-{weight}-normal.woff")
    opts = subset.Options()
    opts.layout_features = []
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=[ord(c) for c in DIGITS])
    sub.subset(font)

    cmap = font.getBestCmap()
    names = [cmap[ord(c)] for c in DIGITS]
    hmtx = font["hmtx"]
    glyf = font["glyf"]
    width = max(hmtx[n][0] for n in names)
    for n in names:
        adv, lsb = hmtx[n]
        dx = round((width - adv) / 2)
        glyph = glyf[n]
        if glyph.numberOfContours > 0:
            glyph.coordinates.translate((dx, 0))
            glyph.recalcBounds(glyf)
        hmtx[n] = (width, lsb + dx)

    style = {400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold"}[weight]
    for rec in font["name"].names:
        if rec.nameID in (1, 16):
            rec.string = FAMILY
        elif rec.nameID == 4:
            rec.string = f"{FAMILY} {style}"
        elif rec.nameID == 6:
            rec.string = f"ZonesDigits-{style}"
    font.flavor = "woff"
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"zones-digits-{weight}.woff"
    font.save(path)
    return path


def main() -> None:
    for w in WEIGHTS:
        print(build(w))
    (OUT / "OFL.txt").write_text((SRC / "LICENSE").read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Bingo Card Generator

Generates unique bingo cards from either:
- A list of strings (materials/words)
- A list of integers (numbers) - rendered using digit images or text

Key property: every item on every card is drawn at the SAME size. Instead of
each cell independently picking "the biggest font/scale that fits this one
item", we first look at the whole set of items and the fixed cell size, and
compute a single font size (text mode) or a single digit scale (number mode)
that fits the worst case (longest word / most digits). That one size is then
reused for every cell on every card.

Usage:
    python generate_bingo.py --materials "item1,item2,item3,..." --nb_row 5 --nb_line 5 --nb_cards 10
    python generate_bingo.py --numbers "1,2,3,4,5,6,7,8,9,10" --nb_row 3 --nb_line 3 --nb_cards 5
    python generate_bingo.py --numbers_range 1 90 --nb_row 9 --nb_line 3 --nb_cards 6
"""

import argparse
import os
import random
import sys
from pathlib import Path
from typing import List, Union, Dict

from PIL import Image, ImageDraw, ImageFont


# Configuration
IMAGES_DIR = Path("images")
OUTPUT_DIR = Path("output")
CARD_SIZE = (1200, 1200)  # Increased size for better visibility
CELL_PADDING = 20  # Increased padding
GRID_LINE_WIDTH = 4
BACKGROUND_COLOR = (255, 255, 255)  # White
GRID_COLOR = (0, 0, 0)  # Black
TEXT_COLOR = (0, 0, 0)  # Black
FREE_SPACE_COLOR = (255, 0, 0)  # Red

# Max number of attempts to find a card layout that hasn't been used yet.
MAX_UNIQUE_ATTEMPTS = 200


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

def get_font(font_size: int) -> ImageFont.FreeTypeFont:
    """Get a font, trying various options."""
    font_paths = [
        "arial.ttf",
        "/usr/share/fonts/truetype/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]

    for path in font_paths:
        try:
            return ImageFont.truetype(path, font_size)
        except Exception:
            continue

    try:
        return ImageFont.truetype("DejaVuSans.ttf", font_size)
    except Exception:
        return ImageFont.load_default()


def compute_uniform_font_size(items: List[str], max_width: int, max_height: int) -> int:
    """
    Find the single largest font size that fits EVERY item in `items` inside
    a box of size (max_width, max_height). This is what makes every word on
    every card render at the same size, regardless of word length.
    """
    dummy_img = Image.new("RGBA", (10, 10))
    draw = ImageDraw.Draw(dummy_img)

    def fits(font_size: int) -> bool:
        font = get_font(font_size)
        for text in items:
            bbox = draw.textbbox((0, 0), str(text), font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            if w > max_width or h > max_height:
                return False
        return True

    low, high = 8, min(max_height, 200)
    best = low
    while low <= high:
        mid = (low + high) // 2
        if fits(mid):
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    return best


def create_text_image(text: str, font: ImageFont.FreeTypeFont, max_width: int, max_height: int) -> Image.Image:
    """Render `text` centered in a (max_width, max_height) box using a pre-computed, shared font."""
    img = Image.new("RGBA", (max_width, max_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (max_width - text_width) // 2 - bbox[0]
    y = (max_height - text_height) // 2 - bbox[1]

    draw.text((x, y), text, font=font, fill=TEXT_COLOR)
    return img


# ---------------------------------------------------------------------------
# Digit image helpers
# ---------------------------------------------------------------------------

def _glyph_bbox(img: Image.Image) -> tuple:
    """
    Return the bounding box of the actual glyph ink inside `img`, ignoring
    transparent padding (or, if the image has no alpha, near-white padding).
    This is what fixes the "0.png has more built-in padding than the other
    digits" problem: after cropping to the real glyph, every digit's height
    reflects only the drawn shape, not incidental canvas whitespace.
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    if bbox is not None:
        # Some PNGs are fully opaque (no real alpha channel info) - in that
        # case getbbox() on alpha returns the whole image, which is useless.
        # Fall back to luminance-based trimming for those.
        if bbox != (0, 0, img.width, img.height):
            return bbox

    gray = img.convert("L")
    thresholded = gray.point(lambda p: 255 if p < 245 else 0)
    bbox = thresholded.getbbox()
    return bbox if bbox is not None else (0, 0, img.width, img.height)


def load_digit_images() -> Dict[int, Image.Image]:
    """Load digit images (0-9), each cropped to its real glyph bounding box."""
    digit_images = {}
    for digit in range(10):
        path = IMAGES_DIR / f"{digit}.png"
        if not path.exists():
            raise FileNotFoundError(f"Digit image not found: {path}")
        img = Image.open(path).convert("RGBA")
        bbox = _glyph_bbox(img)
        digit_images[digit] = img.crop(bbox)
    return digit_images


def compute_number_target_height(
    items: List[int],
    digit_images: Dict[int, Image.Image],
    max_width: int,
    max_height: int,
) -> int:
    """
    Find the single glyph height (after the crop above) that, when used to
    scale every digit, still lets the widest number in `items` fit within
    max_width. All digits share this one target height, so every number on
    every card is drawn at the same visual size.
    """
    max_glyph_height = max(img.height for img in digit_images.values())

    target_height = max_height
    while target_height > 1:
        scale = target_height / max_glyph_height
        fits = True
        for item in items:
            total_width = sum(
                digit_images[int(d)].width * scale for d in str(item)
            )
            if total_width > max_width:
                fits = False
                break
        if fits:
            break
        target_height -= 1

    return max(target_height, 1)


def scale_digit_images(digit_images: Dict[int, Image.Image], target_height: int) -> Dict[int, Image.Image]:
    """Resize every (already glyph-cropped) digit so they share the same height."""
    max_glyph_height = max(img.height for img in digit_images.values())
    scale = target_height / max_glyph_height

    scaled = {}
    for digit, img in digit_images.items():
        new_w = max(1, round(img.width * scale))
        new_h = max(1, round(img.height * scale))
        scaled[digit] = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return scaled


def create_number_image(number: int, scaled_digit_images: Dict[int, Image.Image]) -> Image.Image:
    """Compose a number image out of pre-scaled (uniform-height) digit images."""
    digits = [scaled_digit_images[int(d)] for d in str(number)]

    total_width = sum(d.width for d in digits)
    height = max(d.height for d in digits)

    result = Image.new("RGBA", (total_width, height), (0, 0, 0, 0))
    x = 0
    for d in digits:
        y = (height - d.height) // 2
        result.paste(d, (x, y), d)
        x += d.width
    return result


# ---------------------------------------------------------------------------
# Card generation
# ---------------------------------------------------------------------------

def _has_free_space(nb_row: int, nb_line: int) -> bool:
    return nb_row % 2 == 1 and nb_line % 2 == 1


def _pick_unique_layout(items: List[Union[str, int]], total_cells: int, used_layouts: set, seed: int):
    """Sample `total_cells` items, retrying with new seeds until the resulting
    layout hasn't been used by a previous card (bounded by MAX_UNIQUE_ATTEMPTS)."""
    for attempt in range(MAX_UNIQUE_ATTEMPTS):
        rng = random.Random(seed * 10_000 + attempt)
        selected = rng.sample(items, min(len(items), total_cells))

        if len(selected) < total_cells:
            remaining = total_cells - len(selected)
            selected.extend(rng.choices(selected, k=remaining))

        rng.shuffle(selected)

        layout_key = tuple(selected)
        if layout_key not in used_layouts:
            used_layouts.add(layout_key)
            return selected

    # Give up trying to be unique after MAX_UNIQUE_ATTEMPTS; just return the
    # last attempt (this only happens if there simply aren't enough distinct
    # layouts possible for the given items/grid size).
    used_layouts.add(layout_key)
    return selected


def generate_bingo_card(
    items: List[Union[str, int]],
    nb_row: int,
    nb_line: int,
    used_layouts: set,
    card_index: int,
    is_numbers: bool = False,
    scaled_digit_images: Dict[int, Image.Image] = None,
    uniform_font: ImageFont.FreeTypeFont = None,
) -> Image.Image:
    """Generate a single bingo card."""
    total_cells = nb_row * nb_line
    selected_items = _pick_unique_layout(items, total_cells, used_layouts, card_index + 1000)

    card_width, card_height = CARD_SIZE
    card_img = Image.new("RGB", (card_width, card_height), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(card_img)

    cell_width = (card_width - GRID_LINE_WIDTH) // nb_line
    cell_height = (card_height - GRID_LINE_WIDTH) // nb_row

    # Grid lines
    draw.line([(0, 0), (card_width, 0)], fill=GRID_COLOR, width=GRID_LINE_WIDTH)
    draw.line([(0, card_height - GRID_LINE_WIDTH), (card_width, card_height - GRID_LINE_WIDTH)],
              fill=GRID_COLOR, width=GRID_LINE_WIDTH)
    for i in range(1, nb_line):
        x = i * cell_width + (i * GRID_LINE_WIDTH)
        draw.line([(x, 0), (x, card_height)], fill=GRID_COLOR, width=GRID_LINE_WIDTH)
    for i in range(1, nb_row):
        y = i * cell_height + (i * GRID_LINE_WIDTH)
        draw.line([(0, y), (card_width, y)], fill=GRID_COLOR, width=GRID_LINE_WIDTH)

    free_space = _has_free_space(nb_row, nb_line)
    center_row, center_col = nb_row // 2, nb_line // 2

    for row in range(nb_row):
        for col in range(nb_line):
            cell_index = row * nb_line + col
            x_start = col * (cell_width + GRID_LINE_WIDTH)
            y_start = row * (cell_height + GRID_LINE_WIDTH)

            if free_space and row == center_row and col == center_col:
                center_x = x_start + cell_width // 2
                center_y = y_start + cell_height // 2
                font = get_font(48)
                draw.text((center_x - 30, center_y - 25), "FREE", font=font, fill=FREE_SPACE_COLOR)
                draw.text((center_x - 40, center_y + 15), "SPACE", font=font, fill=FREE_SPACE_COLOR)
                continue

            item = selected_items[cell_index % len(selected_items)]

            available_width = cell_width - CELL_PADDING * 2
            available_height = cell_height - CELL_PADDING * 2

            if is_numbers and scaled_digit_images:
                item_img = create_number_image(item, scaled_digit_images)
            else:
                item_img = create_text_image(str(item), uniform_font, available_width, available_height)

            item_x = x_start + CELL_PADDING + (available_width - item_img.width) // 2
            item_y = y_start + CELL_PADDING + (available_height - item_img.height) // 2

            card_img.paste(item_img, (item_x, item_y), item_img if item_img.mode == "RGBA" else None)

    return card_img


def generate_bingo_cards(
    items: List[Union[str, int]],
    nb_row: int,
    nb_line: int,
    nb_cards: int,
    output_dir: Path = OUTPUT_DIR,
    is_numbers: bool = False,
) -> List[Path]:
    """Generate multiple unique bingo cards."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Cell dimensions, needed up front to size text/digits uniformly.
    card_width, card_height = CARD_SIZE
    cell_width = (card_width - GRID_LINE_WIDTH) // nb_line
    cell_height = (card_height - GRID_LINE_WIDTH) // nb_row
    available_width = cell_width - CELL_PADDING * 2
    available_height = cell_height - CELL_PADDING * 2

    scaled_digit_images = None
    uniform_font = None

    if is_numbers:
        try:
            digit_images = load_digit_images()
            target_height = compute_number_target_height(items, digit_images, available_width, available_height)
            scaled_digit_images = scale_digit_images(digit_images, target_height)
        except FileNotFoundError as e:
            print(f"Warning: {e}. Falling back to text rendering for numbers.")
            is_numbers = False

    if not is_numbers:
        font_size = compute_uniform_font_size([str(i) for i in items], available_width, available_height)
        uniform_font = get_font(font_size)

    used_layouts: set = set()
    generated_paths = []

    for i in range(nb_cards):
        card_img = generate_bingo_card(
            items=items,
            nb_row=nb_row,
            nb_line=nb_line,
            used_layouts=used_layouts,
            card_index=i,
            is_numbers=is_numbers,
            scaled_digit_images=scaled_digit_images,
            uniform_font=uniform_font,
        )

        output_path = output_dir / f"bingo_card_{i + 1}.png"
        card_img.save(output_path)
        generated_paths.append(output_path)
        print(f"Generated: {output_path}")

    return generated_paths


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_materials(materials_str: str) -> List[str]:
    return [m.strip() for m in materials_str.split(",") if m.strip()]


def parse_numbers(numbers_str: str) -> List[int]:
    return [int(n.strip()) for n in numbers_str.split(",") if n.strip()]


def main():
    parser = argparse.ArgumentParser(description="Generate Bingo Cards")

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--materials", type=str, help="Comma-separated list of materials/strings")
    input_group.add_argument("--numbers", type=str, help="Comma-separated list of numbers")
    input_group.add_argument("--numbers_range", nargs=2, type=int,
                              help="Range of numbers (start, end) - will use all numbers in range")

    parser.add_argument("--nb_row", type=int, required=True, help="Number of rows")
    parser.add_argument("--nb_line", type=int, required=True, help="Number of columns (lines)")
    parser.add_argument("--nb_cards", type=int, required=True, help="Number of cards to generate")
    parser.add_argument("--output_dir", type=str, default="output", help="Output directory for generated cards")

    args = parser.parse_args()

    items = []
    is_numbers = False

    if args.materials:
        items = parse_materials(args.materials)
        is_numbers = False
    elif args.numbers:
        items = parse_numbers(args.numbers)
        is_numbers = True
    elif args.numbers_range:
        start, end = args.numbers_range
        items = list(range(start, end + 1))
        is_numbers = True

    if not items:
        print("Error: No items provided. Please provide materials or numbers.")
        sys.exit(1)

    print(f"Generating {args.nb_cards} bingo cards with {len(items)} items...")
    print(f"Card dimensions: {args.nb_row} rows x {args.nb_line} columns")
    print(f"Mode: {'Numbers' if is_numbers else 'Materials'}")

    output_dir = Path(args.output_dir)
    generated = generate_bingo_cards(
        items=items,
        nb_row=args.nb_row,
        nb_line=args.nb_line,
        nb_cards=args.nb_cards,
        output_dir=output_dir,
        is_numbers=is_numbers,
    )

    print(f"\nGenerated {len(generated)} bingo cards in {output_dir.absolute()}")
    for path in generated:
        print(f"  - {path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Bingo Card Generator

Generates unique bingo cards from either:
- A list of strings (materials/words)
- A list of integers (numbers) - rendered using digit images

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
from typing import List, Union, Tuple

from PIL import Image, ImageDraw, ImageFont


# Configuration
IMAGES_DIR = Path("images")
OUTPUT_DIR = Path("output")
CARD_SIZE = (800, 800)  # Width, Height of the output card
CELL_PADDING = 10  # Padding inside each cell
GRID_LINE_WIDTH = 4  # Width of grid lines
BACKGROUND_COLOR = (255, 255, 255)  # White background
GRID_COLOR = (0, 0, 0)  # Black grid lines
TEXT_COLOR = (0, 0, 0)  # Black text
TEXT_COLOR_RED = (255, 0, 0)  # Red text for free space


def load_digit_images() -> dict:
    """Load digit images (0-9) from the images directory."""
    digit_images = {}
    for digit in range(10):
        path = IMAGES_DIR / f"{digit}.png"
        if path.exists():
            digit_images[digit] = Image.open(path).convert("RGBA")
        else:
            raise FileNotFoundError(f"Digit image not found: {path}")
    return digit_images


def create_number_image(number: int, digit_images: dict, max_width: int, max_height: int) -> Image.Image:
    """
    Create an image of a number by combining individual digit images.
    
    Args:
        number: The number to render
        digit_images: Dictionary mapping digits to their images
        max_width: Maximum width for the resulting image
        max_height: Maximum height for the resulting image
    
    Returns:
        PIL Image of the number
    """
    digits = list(map(int, str(number)))
    
    # Get the dimensions of digit images
    sample_digit = digit_images[0]
    digit_width = sample_digit.width
    digit_height = sample_digit.height
    
    # Calculate total width needed
    total_width = len(digits) * digit_width
    
    # Scale if needed
    scale = min(max_width / total_width, max_height / digit_height)
    if scale < 1:
        new_digit_width = int(digit_width * scale)
        new_digit_height = int(digit_height * scale)
    else:
        new_digit_width = digit_width
        new_digit_height = digit_height
    
    # Create a new image with transparent background
    result = Image.new("RGBA", (len(digits) * new_digit_width, new_digit_height), (255, 255, 255, 0))
    
    # Paste each digit
    for i, digit in enumerate(digits):
        img = digit_images[digit]
        if scale < 1:
            img = img.resize((new_digit_width, new_digit_height), Image.Resampling.LANCZOS)
        result.paste(img, (i * new_digit_width, 0), img if img.mode == "RGBA" else None)
    
    return result


def create_text_image(text: str, max_width: int, max_height: int, font_size: int = 40) -> Image.Image:
    """
    Create an image with centered text.
    
    Args:
        text: Text to render
        max_width: Maximum width
        max_height: Maximum height
        font_size: Font size to use
    
    Returns:
        PIL Image with the text
    """
    # Try to load a nice font, fall back to default
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/arial.ttf", font_size)
        except:
            font = ImageFont.load_default()
    
    # Create image
    img = Image.new("RGBA", (max_width, max_height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    # Get text size and position
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    # Scale font if text is too large
    while text_width > max_width or text_height > max_height:
        font_size -= 2
        font = ImageFont.truetype("arial.ttf", font_size) if font_size > 10 else ImageFont.load_default()
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        if font_size <= 8:
            break
    
    # Calculate position to center text
    x = (max_width - text_width) // 2
    y = (max_height - text_height) // 2
    
    # Draw text with black outline for better visibility
    # White background for text
    draw.rectangle([x - 5, y - 5, x + text_width + 5, y + text_height + 5], fill=(255, 255, 255, 200))
    draw.text((x, y), text, font=font, fill=TEXT_COLOR)
    
    return img


def generate_bingo_card(
    items: List[Union[str, int]],
    nb_row: int,
    nb_line: int,
    card_index: int,
    digit_images: dict = None,
    is_numbers: bool = False,
    free_space: bool = True
) -> Image.Image:
    """
    Generate a single bingo card.
    
    Args:
        items: List of items (strings or numbers) to use on the card
        nb_row: Number of rows
        nb_line: Number of columns (lines)
        card_index: Index of this card (for unique randomization)
        digit_images: Dictionary of digit images (for number mode)
        is_numbers: Whether items are numbers
        free_space: Whether to include a free space in the center
    
    Returns:
        PIL Image of the bingo card
    """
    # Calculate cell dimensions
    total_cells = nb_row * nb_line
    
    # Select random items for this card
    # Use card_index to ensure different random selections for each card
    random.seed(card_index)
    selected_items = random.sample(items, min(len(items), total_cells))
    
    # If we have fewer items than cells, repeat some
    if len(selected_items) < total_cells:
        remaining = total_cells - len(selected_items)
        selected_items.extend(random.choices(selected_items, k=remaining))
    
    # Shuffle again to mix the repeated items
    random.shuffle(selected_items)
    
    # Create card image
    card_width, card_height = CARD_SIZE
    card_img = Image.new("RGB", (card_width, card_height), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(card_img)
    
    # Calculate cell size
    cell_width = (card_width - GRID_LINE_WIDTH) // nb_line
    cell_height = (card_height - GRID_LINE_WIDTH) // nb_row
    
    # Draw grid lines
    for i in range(nb_line + 1):
        x = i * cell_width + (i * GRID_LINE_WIDTH)
        draw.line([(x, 0), (x, card_height)], fill=GRID_COLOR, width=GRID_LINE_WIDTH)
    
    for i in range(nb_row + 1):
        y = i * cell_height + (i * GRID_LINE_WIDTH)
        draw.line([(0, y), (card_width, y)], fill=GRID_COLOR, width=GRID_LINE_WIDTH)
    
    # Add items to cells
    for row in range(nb_row):
        for col in range(nb_line):
            cell_index = row * nb_line + col
            
            # Calculate cell position
            x_start = col * (cell_width + GRID_LINE_WIDTH)
            y_start = row * (cell_height + GRID_LINE_WIDTH)
            
            # Check for free space (center cell for odd-sized cards)
            if free_space and nb_row % 2 == 1 and nb_line % 2 == 1:
                center_row = nb_row // 2
                center_col = nb_line // 2
                if row == center_row and col == center_col:
                    # Draw free space
                    center_x = x_start + cell_width // 2
                    center_y = y_start + cell_height // 2
                    try:
                        font = ImageFont.truetype("arial.ttf", 40)
                    except:
                        font = ImageFont.load_default()
                    draw.text((center_x - 20, center_y - 20), "FREE", font=font, fill=TEXT_COLOR_RED)
                    draw.text((center_x - 30, center_y + 10), "SPACE", font=font, fill=TEXT_COLOR_RED)
                    continue
            
            # Get item for this cell
            if cell_index < len(selected_items):
                item = selected_items[cell_index]
            else:
                item = selected_items[cell_index % len(selected_items)]
            
            # Create item image
            if is_numbers and digit_images:
                item_img = create_number_image(item, digit_images, cell_width - CELL_PADDING * 2, cell_height - CELL_PADDING * 2)
            else:
                item_img = create_text_image(str(item), cell_width - CELL_PADDING * 2, cell_height - CELL_PADDING * 2)
            
            # Center the item image in the cell
            item_x = x_start + CELL_PADDING + (cell_width - CELL_PADDING * 2 - item_img.width) // 2
            item_y = y_start + CELL_PADDING + (cell_height - CELL_PADDING * 2 - item_img.height) // 2
            
            # Paste the item image
            card_img.paste(item_img, (item_x, item_y), item_img if item_img.mode == "RGBA" else None)
    
    return card_img


def generate_bingo_cards(
    items: List[Union[str, int]],
    nb_row: int,
    nb_line: int,
    nb_cards: int,
    output_dir: Path = OUTPUT_DIR,
    is_numbers: bool = False
) -> List[Path]:
    """
    Generate multiple unique bingo cards.
    
    Args:
        items: List of items to use
        nb_row: Number of rows
        nb_line: Number of columns
        nb_cards: Number of cards to generate
        output_dir: Directory to save cards
        is_numbers: Whether items are numbers
    
    Returns:
        List of paths to generated card images
    """
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load digit images if in number mode
    digit_images = None
    if is_numbers:
        digit_images = load_digit_images()
    
    generated_paths = []
    
    for i in range(nb_cards):
        card_img = generate_bingo_card(
            items=items,
            nb_row=nb_row,
            nb_line=nb_line,
            card_index=i,
            digit_images=digit_images,
            is_numbers=is_numbers
        )
        
        # Save card
        output_path = output_dir / f"bingo_card_{i + 1}.png"
        card_img.save(output_path)
        generated_paths.append(output_path)
        print(f"Generated: {output_path}")
    
    return generated_paths


def parse_materials(materials_str: str) -> List[str]:
    """Parse comma-separated materials string."""
    return [m.strip() for m in materials_str.split(",") if m.strip()]


def parse_numbers(numbers_str: str) -> List[int]:
    """Parse comma-separated numbers string."""
    return [int(n.strip()) for n in numbers_str.split(",") if n.strip()]


def main():
    parser = argparse.ArgumentParser(description="Generate Bingo Cards")
    
    # Input type (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--materials", type=str, help="Comma-separated list of materials/strings")
    input_group.add_argument("--numbers", type=str, help="Comma-separated list of numbers")
    input_group.add_argument("--numbers_range", nargs=2, type=int, 
                           help="Range of numbers (start, end) - will use all numbers in range")
    
    # Card dimensions
    parser.add_argument("--nb_row", type=int, required=True, help="Number of rows")
    parser.add_argument("--nb_line", type=int, required=True, help="Number of columns (lines)")
    
    # Number of cards
    parser.add_argument("--nb_cards", type=int, required=True, help="Number of cards to generate")
    
    # Output directory
    parser.add_argument("--output_dir", type=str, default="output", 
                       help="Output directory for generated cards")
    
    # Free space option
    parser.add_argument("--no_free_space", action="store_true", 
                       help="Disable free space in center cell")
    
    args = parser.parse_args()
    
    # Parse input items
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
    
    # Generate cards
    output_dir = Path(args.output_dir)
    generated = generate_bingo_cards(
        items=items,
        nb_row=args.nb_row,
        nb_line=args.nb_line,
        nb_cards=args.nb_cards,
        output_dir=output_dir,
        is_numbers=is_numbers
    )
    
    print(f"\nGenerated {len(generated)} bingo cards in {output_dir.absolute()}")
    for path in generated:
        print(f"  - {path}")


if __name__ == "__main__":
    main()

# ============================================================
#  REVIEW_IMAGES.PY — KYFF Store
#  Shows all images, lets you mark which are real products
#  Saves your choices to a CSV file for import
# ============================================================

import os
import csv
import re
from pathlib import Path

# ── CONFIG ─────────────────────────────────────────────────
IMAGES_FOLDER = r"C:\Projects\kyff_store\frontend\static\images\products"
OUTPUT_CSV    = r"C:\Projects\kyff_store\tools\products_review.csv"

# ── Category Keywords Map ──────────────────────────────────
# Script guesses category from image name
CATEGORY_MAP = {
    'rice'        : 'Rice',
    'basmati'     : 'Rice',
    'basmathi'    : 'Rice',
    'bavani'      : 'Rice',
    'red-rice'    : 'Rice',
    'millet'      : 'Millets',
    'ragi'        : 'Millets',
    'foxtail'     : 'Millets',
    'thinai'      : 'Millets',
    'kambu'       : 'Millets',
    'samai'       : 'Millets',
    'varagu'      : 'Millets',
    'kuthiraivali': 'Millets',
    'amaranth'    : 'Millets',
    'oil'         : 'Oils',
    'coconut'     : 'Oils',
    'sesame'      : 'Oils',
    'groundnut'   : 'Oils',
    'gingelly'    : 'Oils',
    'dal'         : 'Pulses',
    'gram'        : 'Pulses',
    'lentil'      : 'Pulses',
    'kollu'       : 'Pulses',
    'urad'        : 'Pulses',
    'toor'        : 'Pulses',
    'moong'       : 'Pulses',
    'channa'      : 'Pulses',
    'spice'       : 'Spices',
    'pepper'      : 'Spices',
    'chilli'      : 'Spices',
    'turmeric'    : 'Spices',
    'cinnamon'    : 'Spices',
    'cardamom'    : 'Spices',
    'elakai'      : 'Spices',
    'clove'       : 'Spices',
    'cumin'       : 'Spices',
    'jeera'       : 'Spices',
    'mustard'     : 'Spices',
    'fenugreek'   : 'Spices',
    'sugar'       : 'Sweeteners',
    'jaggery'     : 'Sweeteners',
    'honey'       : 'Sweeteners',
    'palm'        : 'Sweeteners',
    'nattu'       : 'Sweeteners',
    'nut'         : 'Dry Fruits',
    'almond'      : 'Dry Fruits',
    'cashew'      : 'Dry Fruits',
    'raisin'      : 'Dry Fruits',
    'dates'       : 'Dry Fruits',
    'pista'       : 'Dry Fruits',
    'walnut'      : 'Dry Fruits',
    'dry'         : 'Dry Fruits',
    'flour'       : 'Flours',
    'maavu'       : 'Flours',
    'atta'        : 'Flours',
    'powder'      : 'Flours',
    'tea'         : 'Herbal',
    'herb'        : 'Herbal',
    'avaram'      : 'Herbal',
    'neem'        : 'Herbal',
    'moringa'     : 'Herbal',
    'tulsi'       : 'Herbal',
    'soap'        : 'Personal Care',
    'shampoo'     : 'Personal Care',
    'oil-hair'    : 'Personal Care',
}

# ── Words that indicate NOT a product ─────────────────────
NOT_PRODUCT_KEYWORDS = [
    'banner', 'logo', 'icon', 'bg', 'background',
    'slide', 'hero', 'ad', 'promo', 'poster',
    'avvai', 'bee', 'ant', 'bird', 'flower',
    'farm', 'field', 'nature', 'organic-farming',
    '26organic', 'bio-diverse', 'unsplash',
    'scaled', 'ajay', 'aliona', 'banner',
    'basic-combo', 'combo', 'misc', 'test',
    'sample', 'dummy', '23_1', 'a2',
]


# ── Guess category from filename ───────────────────────────
def guess_category(name):
    name_lower = name.lower()
    for keyword, category in CATEGORY_MAP.items():
        if keyword in name_lower:
            return category
    return 'Other'


# ── Guess if image is a product ────────────────────────────
def guess_is_product(name):
    name_lower = name.lower()
    for keyword in NOT_PRODUCT_KEYWORDS:
        if keyword in name_lower:
            return 'NO'
    return 'YES'


# ── Clean name for display ─────────────────────────────────
def clean_name(stem):
    # Replace hyphens/underscores with spaces
    name = stem.replace('-', ' ').replace('_', ' ')
    # Title case
    name = name.title()
    # Remove leftover size patterns
    name = re.sub(r'\d{2,4}[Xx]\d{2,4}', '', name).strip()
    return name


# ── Main ───────────────────────────────────────────────────
def main():
    images_path = Path(IMAGES_FOLDER)
    if not images_path.exists():
        print(f"❌ Folder not found: {IMAGES_FOLDER}")
        return

    extensions  = {'.jpg', '.jpeg', '.png', '.webp'}
    images      = sorted([
        f for f in images_path.iterdir()
        if f.suffix.lower() in extensions
    ])

    print(f"\n{'='*60}")
    print(f"  🌾 KYFF Product Review Tool")
    print(f"{'='*60}")
    print(f"  Found {len(images)} images to review")
    print(f"  Output: {OUTPUT_CSV}")
    print(f"{'='*60}\n")

    rows     = []
    products = 0
    skipped  = 0

    for img in images:
        stem        = img.stem
        display     = clean_name(stem)
        category    = guess_category(stem)
        is_product  = guess_is_product(stem)
        image_url   = f"/static/images/products/{img.name}"

        if is_product == 'YES':
            products += 1
        else:
            skipped += 1

        rows.append({
            'filename'   : img.name,
            'image_url'  : image_url,
            'is_product' : is_product,
            'name'       : display,
            'category'   : category,
            'price'      : '100.00',
            'description': '',
        })

    # Write CSV
    Path(OUTPUT_CSV).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'filename', 'image_url', 'is_product',
            'name', 'category', 'price', 'description'
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"  ✅ CSV saved to:")
    print(f"     {OUTPUT_CSV}\n")
    print(f"  📊 Summary:")
    print(f"     Marked as PRODUCT : {products}")
    print(f"     Marked as SKIP    : {skipped}")
    print(f"\n  📝 Next Steps:")
    print(f"     1. Open {OUTPUT_CSV} in Excel")
    print(f"     2. Change is_product to YES/NO for each row")
    print(f"     3. Fill in correct names, prices, descriptions")
    print(f"     4. Save the CSV")
    print(f"     5. Run import_products.py\n")


if __name__ == '__main__':
    main()
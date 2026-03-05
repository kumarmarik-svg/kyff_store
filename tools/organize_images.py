# ============================================================
#  ORGANIZE_IMAGES.PY — KYFF Store
#  Scans all image folders, removes size duplicates,
#  keeps best version per product, copies to clean folder
# ============================================================

import os
import re
import shutil
from pathlib import Path
from collections import defaultdict


# ── CONFIG — Change these paths ───────────────────────────
SOURCE_FOLDERS = [
    r"C:\Projects\backup\2021\2021\05",
    r"C:\Projects\backup\2021\2021\06",
    r"C:\Projects\backup\2021\2021\07",
    r"C:\Projects\backup\2021\2021\08",
    r"C:\Projects\backup\2021\2021\09",
    r"C:\Projects\backup\2021\2021\10",
    r"C:\Projects\backup\2021\2021\11",
    r"C:\Projects\backup\2021\2021\12",
]

OUTPUT_FOLDER = r"C:\Projects\kyff_store\frontend\static\images\products"

# Image extensions to process
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

# Size patterns to strip from filenames
# e.g. -100x100, -300x300, -1024x682, -500x500-1
SIZE_PATTERN = re.compile(
    r'-\d{2,4}x\d{2,4}(-\d+)?$',
    re.IGNORECASE
)

# Preferred sizes in order (we pick highest available)
# Script will prefer larger images
PREFERRED_ORDER = [
    '768', '600', '500', '300', '150', '100'
]


# ── STEP 1: Scan all images ────────────────────────────────
def scan_images(folders):
    all_images = []

    for folder in folders:
        folder_path = Path(folder)
        if not folder_path.exists():
            print(f"  ⚠️  Folder not found: {folder}")
            continue

        count = 0
        for file in folder_path.iterdir():
            if file.suffix.lower() in IMAGE_EXTENSIONS:
                all_images.append(file)
                count += 1

        print(f"  📁 {folder_path.name} — {count} images found")

    return all_images


# ── STEP 2: Group images by base product name ──────────────
def group_by_product(images):
    groups = defaultdict(list)

    for image_path in images:
        stem = image_path.stem  # filename without extension

        # Remove size suffix to get base name
        base_name = SIZE_PATTERN.sub('', stem)

        # Clean up trailing hyphens or numbers like -1, -2
        base_name = re.sub(r'-\d+$', '', base_name)
        base_name = base_name.strip('-').lower()

        if base_name:
            groups[base_name].append(image_path)

    return groups


# ── STEP 3: Pick best image from each group ────────────────
def pick_best_image(candidates):
    if len(candidates) == 1:
        return candidates[0]

    # Score each candidate by size in filename
    def score(path):
        stem = path.stem
        # Look for size like 300x300, 600x450 etc
        match = re.search(r'(\d{3,4})x(\d{3,4})', stem)
        if match:
            w = int(match.group(1))
            h = int(match.group(2))
            return w * h  # larger area = better
        # No size in name = original (usually largest)
        # Give it a high score
        return 999999

    # Sort by score descending — pick largest
    scored = sorted(candidates, key=score, reverse=True)

    # But cap at 600px wide — don't need huge files
    for candidate in scored:
        match = re.search(r'(\d{3,4})x\d{3,4}', candidate.stem)
        if match:
            width = int(match.group(1))
            if width <= 768:
                return candidate

    return scored[0]


# ── STEP 4: Copy to output folder ─────────────────────────
def copy_images(groups, output_folder):
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    copied      = []
    skipped     = []
    name_map    = {}   # base_name → final filename

    print(f"\n  📦 Copying best images to:\n     {output_folder}\n")

    for base_name, candidates in sorted(groups.items()):
        best = pick_best_image(candidates)

        # Build clean output filename
        clean_name  = base_name.replace(' ', '-').lower()
        output_file = output_path / f"{clean_name}{best.suffix.lower()}"

        # Handle name collision
        counter = 1
        while output_file.exists():
            output_file = output_path / f"{clean_name}-{counter}{best.suffix.lower()}"
            counter += 1

        try:
            shutil.copy2(best, output_file)
            copied.append((base_name, output_file.name))
            name_map[base_name] = output_file.name
        except Exception as e:
            skipped.append((base_name, str(e)))

    return copied, skipped, name_map


# ── STEP 5: Print report ───────────────────────────────────
def print_report(copied, skipped, name_map, total_original):
    print("\n" + "="*60)
    print("  ✅ CLEANUP COMPLETE — REPORT")
    print("="*60)
    print(f"\n  Total images scanned  : {total_original}")
    print(f"  Unique products found : {len(copied)}")
    print(f"  Images copied         : {len(copied)}")
    print(f"  Skipped (errors)      : {len(skipped)}")
    reduction = total_original - len(copied)
    print(f"  Duplicates removed    : {reduction}")
    print(f"\n{'─'*60}")
    print(f"  {'PRODUCT NAME':<35} SAVED AS")
    print(f"{'─'*60}")

    for base_name, filename in sorted(copied):
        print(f"  {base_name:<35} {filename}")

    if skipped:
        print(f"\n  ⚠️  SKIPPED:")
        for name, err in skipped:
            print(f"  {name} — {err}")

    print(f"\n{'='*60}")
    print(f"  📁 Output folder:")
    print(f"  {OUTPUT_FOLDER}")
    print(f"{'='*60}\n")


# ── STEP 6: Generate SQL insert statements ─────────────────
def generate_sql(name_map):
    sql_file = Path(OUTPUT_FOLDER).parent.parent / "tools" / "product_images.sql"
    sql_file.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "-- ================================================",
        "-- AUTO-GENERATED product image INSERT statements",
        "-- Run AFTER adding products to the database",
        "-- Replace product_id values with actual IDs",
        "-- ================================================",
        "",
        "USE kyff_store;",
        "",
    ]

    for i, (base_name, filename) in enumerate(sorted(name_map.items()), 1):
        image_url = f"/static/images/products/{filename}"
        lines.append(
            f"-- INSERT INTO product_images (product_id, image_url, alt_text, sort_order, created_at)"
        )
        lines.append(
            f"-- VALUES (REPLACE_WITH_ID, '{image_url}', '{base_name}', 0, NOW());  -- {base_name}"
        )
        lines.append("")

    with open(sql_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"  📄 SQL file saved to:\n     {sql_file}\n")


# ── MAIN ───────────────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("  🌾 KYFF Image Organizer")
    print("="*60)
    print("\n  📂 Scanning source folders...\n")

    # Step 1 — Scan
    all_images = scan_images(SOURCE_FOLDERS)
    total      = len(all_images)
    print(f"\n  Total images found: {total}")

    if total == 0:
        print("\n  ❌ No images found. Check your SOURCE_FOLDERS paths.")
        return

    # Step 2 — Group
    print("\n  🔍 Grouping by product name...")
    groups = group_by_product(all_images)
    print(f"  Unique products identified: {len(groups)}")

    # Step 3+4 — Pick best + Copy
    copied, skipped, name_map = copy_images(groups, OUTPUT_FOLDER)

    # Step 5 — Report
    print_report(copied, skipped, name_map, total)

    # Step 6 — SQL
    print("  📄 Generating SQL insert statements...")
    generate_sql(name_map)

    print("  ✅ Done! Check your output folder.\n")


if __name__ == '__main__':
    main()
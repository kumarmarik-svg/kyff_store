# ============================================================
#  IMPORT_PRODUCTS.PY — KYFF Store
# ============================================================

import csv
import sys
import pymysql
from pathlib import Path

# ── CONFIG ─────────────────────────────────────────────────
DB_CONFIG = {
    'host'    : 'centerbeam.proxy.rlwy.net',
    'port'    : 42373,
    'user'    : 'root',
    'password': 'PtjWuAgrwXfZDaBEWcCwbvbbIyvSsnnT',
    'database': 'railway',
    'charset' : 'utf8mb4',
}

CSV_FILE = r"C:\Projects\kyff_store\tools\products_review.csv"


# ── Helpers ────────────────────────────────────────────────
def normalize_category(cat):
    cat = cat.strip()
    if cat in ('Other', 'Others', ''):
        return 'General'
    return cat

def clean_name(name):
    return name.strip().title()

def slugify(text):
    import re
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


# ── Main ───────────────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("  🌾 KYFF Product Importer")
    print("="*60)

    # ── Connect ────────────────────────────────────────────
    try:
        conn   = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print("\n  ✅ Connected to MySQL\n")
    except Exception as e:
        print(f"\n  ❌ DB Connection failed: {e}")
        sys.exit(1)

    # ── Read CSV ───────────────────────────────────────────
    csv_path = Path(CSV_FILE)
    if not csv_path.exists():
        print(f"  ❌ CSV not found: {CSV_FILE}")
        sys.exit(1)

    with open(csv_path, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    products = [r for r in rows if r['is_product'].strip().upper() == 'YES']
    print(f"  📦 Products to import : {len(products)}")

    # ── Step 1: Create Categories ──────────────────────────
    print("\n  📁 Creating categories...")
    category_ids = {}
    all_cats = sorted(set(normalize_category(r['category']) for r in products))

    for cat_name in all_cats:
        slug = slugify(cat_name)

        cursor.execute(
            "SELECT id FROM categories WHERE slug = %s", (slug,)
        )
        existing = cursor.fetchone()

        if existing:
            category_ids[cat_name] = existing[0]
            print(f"     existing → {cat_name} (id:{existing[0]})")
        else:
            cursor.execute("""
                INSERT INTO categories (name, slug, is_active, sort_order, created_at)
                VALUES (%s, %s, 1, 0, NOW())
            """, (cat_name, slug))
            conn.commit()
            category_ids[cat_name] = cursor.lastrowid
            print(f"     created  → {cat_name} (id:{cursor.lastrowid})")

    # ── Step 2: Insert Products ────────────────────────────
    print(f"\n  🌿 Importing {len(products)} products...")

    inserted = 0
    skipped  = 0
    errors   = []

    for row in products:
        name      = clean_name(row['name'])
        cat_name  = normalize_category(row['category'])
        cat_id    = category_ids.get(cat_name)
        slug      = slugify(name)
        price     = float(row['price'] or 100)
        desc      = row.get('description', '').strip() or None
        image_url = row.get('image_url', '').strip() or None

        if not name or not cat_id:
            skipped += 1
            continue

        # Make slug unique if duplicate
        cursor.execute("SELECT id FROM products WHERE slug = %s", (slug,))
        if cursor.fetchone():
            slug = f"{slug}-2"

        try:
            # Insert product
            cursor.execute("""
                INSERT INTO products
                    (category_id, name, slug, description,
                    base_price, is_active, is_featured, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, 1, 0, NOW(), NOW())
            """, (cat_id, name, slug, desc, price))
            product_id = cursor.lastrowid

            # Insert default variant
            cursor.execute("""
                INSERT INTO product_variants
                    (product_id, label, price, stock_qty, is_active, created_at)
                VALUES (%s, %s, %s, %s, 1, NOW())
            """, (product_id, '1 Unit', price, 10))

            # Insert image
            if image_url:
                cursor.execute("""
                    INSERT INTO product_images
                        (product_id, image_url, alt_text, is_primary, sort_order, created_at)
                    VALUES (%s, %s, %s, 1, 0, NOW())
                """, (product_id, image_url, name))

            conn.commit()
            inserted += 1

            if inserted % 25 == 0:
                print(f"     ... {inserted} products imported")

        except Exception as e:
            conn.rollback()
            errors.append((name, str(e)))
            skipped += 1

    # ── Report ─────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  ✅ IMPORT COMPLETE")
    print(f"{'='*60}")
    print(f"  Products imported  : {inserted}")
    print(f"  Skipped / errors   : {skipped}")
    print(f"  Categories created : {len(all_cats)}")

    if errors:
        print(f"\n  ⚠️  Errors:")
        for name, err in errors[:10]:
            print(f"     {name} — {err}")

    print(f"\n  🚀 Visit http://127.0.0.1:5000/products")
    print(f"{'='*60}\n")

    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
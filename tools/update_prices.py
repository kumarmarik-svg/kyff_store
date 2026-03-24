# ============================================================
#  UPDATE_PRICES.PY — FINAL WORKING VERSION
# ============================================================

import re
import sys
import pymysql
import openpyxl
from pathlib import Path
from difflib import SequenceMatcher

# ── CONFIG ─────────────────────────────────────────────────
DB_CONFIG = {
    'host': 'centerbeam.proxy.rlwy.net',
    'port': 42373,
    'user': 'root',
    'password': 'PtjWuAgrwXfZDaBEWcCwbvbbIyvSsnnT',
    'database': 'railway',
    'charset': 'utf8mb4',
}

EXCEL_FILE = r"C:\Projects\kyff_store\tools\PriceList_08Aug2024__1_.xlsx"


# ── Helpers ────────────────────────────────────────────────
def clean_name(name):
    name = re.sub(r'\s+\d+\s*$', '', str(name))  # remove trailing numbers like 100g
    name = re.sub(r'[^\w\s]', '', name)          # remove symbols
    name = re.sub(r'\s+', ' ', name).strip()
    return name.lower()


def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


# ── Main ───────────────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("  💰 FINAL PRICE SYNC")
    print("="*60)

    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print("  ✅ Connected to DB\n")
    except Exception as e:
        print(f"❌ DB Error: {e}")
        sys.exit(1)

    # ── Load Excel ─────────────────────────────────────────
    wb = openpyxl.load_workbook(EXCEL_FILE)
    ws = wb.active

    excel_map = {}

    def clean_price(val):
        if not val:
            return None
        nums = re.findall(r'\d+\.?\d*', str(val))
        return float(nums[-1]) if nums else None

    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[3]:
            continue

        name = clean_name(row[3])
        selling = clean_price(row[4])
        mrp = clean_price(row[5])

        if selling:
            excel_map[name] = (selling, mrp or selling)

    print(f"  📊 Excel products: {len(excel_map)}")

    # ── Load DB products ───────────────────────────────────
    cursor.execute("SELECT id, name FROM products")
    db_products = cursor.fetchall()

    print(f"  🛍️ DB products: {len(db_products)}")

    matched_ids = set()
    updated = 0

    print("\n  🔄 Matching and updating...\n")

    for db_id, db_name in db_products:
        db_clean = clean_name(db_name)

        best_match = None
        best_score = 0

        for excel_name in excel_map:
            # strong contains check
            if excel_name in db_clean or db_clean in excel_name:
                score = 0.85
            else:
                score = similarity(db_clean, excel_name)

            if score > best_score:
                best_score = score
                best_match = excel_name

        if best_score < 0.6:
            continue

        selling, mrp = excel_map[best_match]

        base_price = round(mrp, 2)
        sale_price = round(selling, 2)

        try:
            cursor.execute("""
                UPDATE products
                SET base_price = %s
                WHERE id = %s
            """, (base_price, db_id))

            cursor.execute("""
                UPDATE product_variants
                SET price = %s,
                    sale_price = %s
                WHERE product_id = %s
            """, (base_price, sale_price if sale_price < base_price else None, db_id))

            matched_ids.add(db_id)
            updated += 1

        except Exception as e:
            print(f"Error updating {db_name}: {e}")

    conn.commit()

    print(f"\n  ✅ Prices updated: {updated}")

    # ── DELETE UNMATCHED PRODUCTS ───────────────────────────
    print("\n  🧹 Removing unmatched products...")

    if matched_ids:
        ids_tuple = tuple(matched_ids)

        cursor.execute(f"""
            DELETE FROM product_images
            WHERE product_id NOT IN {ids_tuple}
        """)

        cursor.execute(f"""
            DELETE FROM product_variants
            WHERE product_id NOT IN {ids_tuple}
        """)

        cursor.execute(f"""
            DELETE FROM products
            WHERE id NOT IN {ids_tuple}
        """)

        conn.commit()
        print("  ✅ Unmatched products removed")

    print("\n" + "="*60)
    print("  🎉 FINAL SYNC COMPLETE")
    print("="*60)

    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
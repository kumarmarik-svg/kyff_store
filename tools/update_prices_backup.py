# ============================================================
#  UPDATE_PRICES.PY — KYFF Store
#  Reads PriceList Excel, matches products by name similarity,
#  updates base_price, variant price and sale_price in MySQL
# ============================================================

import re
import sys
import pymysql
import openpyxl
from pathlib import Path
from difflib import SequenceMatcher

# ── CONFIG ─────────────────────────────────────────────────
DB_CONFIG = {
    'host'    : 'localhost',
    'port'    : 3306,
    'user'    : 'root',
    'password': 'MySql@123',
    'database': 'kyff_store',
    'charset' : 'utf8mb4',
}

EXCEL_FILE  = r"C:\Projects\kyff_store\tools\PriceList_08Aug2024__1_.xlsx"
MATCH_SCORE = 0.45   # minimum similarity to consider a match (0-1)


# ── Helpers ────────────────────────────────────────────────
def clean_name(name):
    """Remove trailing price digits and normalize"""
    name = re.sub(r'\s+\d+\s*$', '', str(name))   # trailing price
    name = re.sub(r'\s+', ' ', name).strip()
    return name.lower()

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return re.sub(r'-+', '-', text).strip('-')

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def find_best_match(price_name, db_products, threshold=MATCH_SCORE):
    """Find best matching DB product for a price list name"""
    best_score  = 0
    best_product = None

    pname = clean_name(price_name)

    for db_id, db_name, db_slug in db_products:
        dname = db_name.lower()

        # Direct similarity
        score = similarity(pname, dname)

        # Boost if key words match
        p_words = set(pname.split())
        d_words = set(dname.split())
        common  = p_words & d_words
        if len(common) >= 2:
            score += 0.15

        if score > best_score:
            best_score   = score
            best_product = (db_id, db_name, db_slug, score)

    if best_score >= threshold:
        return best_product
    return None


# ── Main ───────────────────────────────────────────────────
def main():
    print("\n" + "="*65)
    print("  💰 KYFF Price Updater")
    print("="*65)

    # ── Connect DB ─────────────────────────────────────────
    try:
        conn   = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print("\n  ✅ Connected to MySQL\n")
    except Exception as e:
        print(f"\n  ❌ DB Error: {e}")
        sys.exit(1)

    # ── Read Excel ─────────────────────────────────────────
    xl_path = Path(EXCEL_FILE)
    if not xl_path.exists():
        print(f"  ❌ Excel not found: {EXCEL_FILE}")
        sys.exit(1)

    wb   = openpyxl.load_workbook(xl_path)
    ws   = wb.active
    rows = list(ws.iter_rows(values_only=True))

    price_list = []
    for row in rows[1:]:
        if not row[0] or not row[3]:
            continue
        name    = str(row[3]).strip()
        #selling = float(row[4]) if row[4] else None
        #mrp     = float(row[5]) if row[5] else None
        def clean_price(val):
            if not val:
                return None
            # Remove spaces, commas, currency symbols, take LAST number if multiple
            import re
            nums = re.findall(r'\d+\.?\d*', str(val).replace(',', ''))
            return float(nums[-1]) if nums else None

        selling = clean_price(row[4])
        mrp     = clean_price(row[5])
        
        if name and selling:
            price_list.append((name, selling, mrp))

    print(f"  📋 Price list rows   : {len(price_list)}")

    # ── Load DB products ───────────────────────────────────
    cursor.execute("SELECT id, name, slug FROM products WHERE is_active=1")
    db_products = cursor.fetchall()
    print(f"  🛍️  DB products       : {len(db_products)}")

    # ── Match & Update ─────────────────────────────────────
    print(f"\n  🔍 Matching and updating prices...\n")

    updated    = []
    no_match   = []

    for price_name, selling, mrp in price_list:
        match = find_best_match(price_name, db_products)

        if not match:
            no_match.append(price_name)
            continue

        db_id, db_name, db_slug, score = match

        # sale_price = selling (discounted)
        # base_price = mrp (original)
        sale_price = round(selling, 2)
        base_price = round(mrp or selling, 2)

        try:
            # Update product base_price
            cursor.execute("""
                UPDATE products
                SET base_price = %s
                WHERE id = %s
            """, (base_price, db_id))

            # Update variant price and sale_price
            cursor.execute("""
                UPDATE product_variants
                SET price      = %s,
                    sale_price = %s
                WHERE product_id = %s
            """, (base_price, sale_price if sale_price < base_price else None, db_id))

            conn.commit()
            updated.append((price_name, db_name, sale_price, base_price, score))

        except Exception as e:
            conn.rollback()
            no_match.append(f"{price_name} — DB error: {e}")

    # ── Report ─────────────────────────────────────────────
    print(f"{'='*65}")
    print(f"  ✅ PRICE UPDATE COMPLETE")
    print(f"{'='*65}")
    print(f"  Prices updated   : {len(updated)}")
    print(f"  No match found   : {len(no_match)}")
    print()
    print(f"  {'PRICE LIST NAME':<35} {'DB PRODUCT':<25} SELL    MRP   SCORE")
    print(f"  {'-'*90}")
    for pname, dname, sell, mrp, score in updated:
        pname_s = pname[:33]
        dname_s = dname[:23]
        print(f"  {pname_s:<35} {dname_s:<25} ₹{sell:<7} ₹{mrp:<6} {score:.2f}")

    if no_match:
        print(f"\n  ⚠️  NO MATCH ({len(no_match)} items):")
        for n in no_match[:20]:
            print(f"     {n}")
        if len(no_match) > 20:
            print(f"     ... and {len(no_match)-20} more")

    print(f"\n{'='*65}\n")
    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
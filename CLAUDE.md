# KYFF Store — Claude Code Guide

"Know Your Food and Farmers" — D2C organic food e-commerce platform.
Built with Flask + MySQL + SQLAlchemy + Jinja2 + Vanilla JS + Razorpay.

---

## Development Commands

All backend commands run from `backend/` with virtualenv active:

```bash
cd backend
venv\Scripts\activate          # Windows
source venv/bin/activate        # Mac/Linux

# Run dev server
python run.py                   # http://localhost:5000

# Migrations
flask db migrate -m "describe change"
flask db upgrade
flask db downgrade
```

Environment: copy `backend/.env.example` → `backend/.env` and fill in:

```
FLASK_DEBUG=0                          # never 1 in production!
SECRET_KEY=<generate with secrets.token_hex(32)>
JWT_SECRET_KEY=<generate separately>
DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
CORS_ORIGINS=http://localhost:5000     # comma-separated for multiple
RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET
MAIL_SERVER, MAIL_PORT, MAIL_USE_TLS, MAIL_USERNAME, MAIL_PASSWORD
JWT_ACCESS_TOKEN_EXPIRES_HOURS=24
```

DB passwords with special characters are URL-encoded automatically
via `quote_plus` in `config/settings.py`.

---

## Architecture

### Request Flow

Flask serves both HTML pages and JSON API from the same process:

- **Page routes** (`routes/views.py`, no prefix) — render Jinja2 templates;
  no auth logic, data loaded client-side via JS
- **API routes** (all prefixed `/api/`) — return JSON:
  `{"success": bool, "message": str, "data": {...}}`

### Blueprint / Route Mapping

| File | Prefix | Notes |
|---|---|---|
| routes/views.py | (none) | HTML page rendering |
| routes/auth.py | /api/auth | JWT auth, password reset |
| routes/products.py | /api/products | Listing, search, recommendations |
| routes/categories.py | /api/categories | Category tree |
| routes/cart.py | /api/cart | Guest + logged-in cart |
| routes/orders.py | /api/orders | Place, track, cancel |
| routes/payments.py | /api/payments | Razorpay + COD |
| routes/reviews.py | /api/reviews | Verified-purchase reviews |
| routes/admin.py | /api/admin | Admin dashboard, full CRUD |
| routes/addresses.py | /api/addresses | Saved delivery addresses |
| routes/banners.py | (none) | Homepage banner images |

### Project Structure

```
kyff_store/
├── backend/
│   ├── app/
│   │   ├── __init__.py         # create_app() factory
│   │   ├── extensions.py       # db, migrate, bcrypt, jwt, mail, cors
│   │   ├── config/settings.py  # all config from .env
│   │   ├── models/             # 15 SQLAlchemy models
│   │   ├── routes/             # all blueprints
│   │   ├── utils/              # email, helpers, timezone
│   │   └── scheduler.py        # background job (order expiry)
│   ├── migrations/             # Alembic migration history
│   └── run.py                  # entry point
└── frontend/
    ├── templates/              # Jinja2 templates
    │   └── admin/              # admin panel templates
    └── static/
        ├── css/                # base.css, pages.css, components.css
        ├── js/                 # api.js, auth.js, cart.js, main.js
        └── images/products/    # product images
```

---

## Key Patterns

### Response Format

Every API endpoint uses local `error()` / `success()` helpers
defined per-blueprint (TODO: move to `utils/responses.py`):

```python
{"success": False, "message": "reason"}           # error
{"success": True,  "message": "...", "data": {}}  # success
```

### Authentication

- JWT tokens — access (24hrs) + refresh (30 days)
- JWT identity stored as `str(user.id)` — always cast with `int(get_jwt_identity())`
- Access token stored in `localStorage` as `kyff_access_token`
- Refresh token stored in `localStorage` as `kyff_refresh_token`
  ⚠️ TODO: move refresh token to httpOnly cookie + save in DB before production
- `api.js` auto-refreshes expired access tokens via `POST /api/auth/refresh`
  and retries original request silently

### Guest Cart

- Cart uses `session_token` (guest) or `user_id` (logged-in)
- Guests send `X-Session-Token: <token>` header
- Session token stored in `sessionStorage` (clears on tab close — intentional!)
- After login → `POST /api/cart/merge` with `session_token` to merge guest cart

### Order Placement Flow (`POST /api/orders/place`)

1. Validate all stock before any DB mutations
2. Create Order with shipping address snapshot
3. `OrderItem.build_from_cart_item()` copies price/name at checkout time
4. Call `variant.reduce_stock()` for each item
5. Delete cart items
6. Initiate Razorpay payment

### Order Status Lifecycle

```
placed → confirmed → processing → shipped → delivered
                                           ↑ admin updates each step
pending/expired → never count in recommendations/trending
cancelled/refunded → excluded from all analytics
```

### Product Soft Delete

Never hard-delete products — set `is_active = False` on both
product and variants to preserve order history integrity.

### Razorpay

- Amounts in **paise** (multiply rupees × 100)
- Webhook at `/api/payments/webhook` validates `X-Razorpay-Signature`
  using HMAC-SHA256
- Test mode: use Razorpay test credentials in `.env`

### Recommendations Logic

| Type | Trigger | Source |
|---|---|---|
| Personal | Logged in + order history | User's most ordered products |
| Trending | Guest or no history | Top ordered last 30 days |
| You May Like | Product/cart page | Same category + personal history |

**Important:** Only count orders with status
`confirmed / processing / shipped / delivered` —
never `pending / expired / cancelled / refunded`.

Stock filter in trending uses **JOIN condition** (not EXISTS subquery)
for better performance:
```python
.join(ProductVariant,
    (ProductVariant.product_id == Product.id) &
    (ProductVariant.is_active == True) &
    (ProductVariant.stock_qty > 0)
)
```

---

## Models

15 entities (one file per model):
`User, PasswordResetToken, Address, Category, Product,
ProductVariant, ProductImage, Cart, CartItem, Order,
OrderItem, Payment, Review, Banner, ShippingRule`

- All models expose `to_dict()` used in API responses
- `Product.to_dict()` accepts `include_variants=True` and `include_images=True`
- `ShippingRule.get_charge_for(subtotal)` calculates shipping in order placement
- Free shipping threshold: ₹500 (shipping = ₹60 below threshold)

---

## Frontend

- `base.html` — master layout; defines `{% block content %}` and
  `{% block extra_js %}` — child pages fill these blocks
- `api.js` — central fetch client; IIFE pattern keeps `request()`
  and `tryRefreshToken()` private
- `auth.js` — login/register/session logic
- `cart.js` — cart interactions; uses `sessionStorage` for guest token
- `main.js` — shared utilities
- Admin templates in `templates/admin/`
- `@admin_required` decorator defined in `routes/admin.py`

### Search Behavior

- Search bar hidden by default; toggled via 🔍 icon in navbar
- Icon changes to ✕ when open, back to 🔍 when closed
- Minimum 2 characters before API call
- On `/products` page: filters in-place, switches to All Products tab
- On other pages: navigates to `/products?q=...`
- Escape key or ✕ closes and clears search

---

## Security Notes (Post-Audit)

All critical issues fixed. Remaining TODOs before production:

| Priority | Task |
|---|---|
| 🔧 Before launch | Move refresh token to httpOnly cookie + save in DB |
| 🔧 Before launch | Add try/except/rollback to all DB operations |
| 🔧 Before launch | Rate limiting on auth routes (Flask-Limiter) |
| 🔧 Refactor | Move error()/success() to utils/responses.py |
| ⏳ Post launch | datetime.utcnow() → datetime.now(timezone.utc) |
| ⏳ Post launch | DB connection pool config (pool_recycle=280) |
| ⏳ Post launch | Input length caps on user text fields |

**Never do:**
- Set `FLASK_DEBUG=1` in production
- Use weak fallback secrets
- Use CORS wildcard `*` in production
- Hard-delete products (use `is_active=False`)

---

## Data Tools

Scripts for catalog management (not app runtime):

```
backend/import_products.py      # bulk import from CSV
backend/organize_images.py      # image pipeline
backend/review_images.py        # image review utility
tools/update_prices.py          # price update from Excel
```

---

## Database

- MySQL with `utf8mb4` encoding (supports Tamil — `name_ta` fields)
- Full schema in `docs/schema.sql`
- Migrations in `backend/migrations/`
- Run `flask db upgrade` on new environments — creates all tables automatically

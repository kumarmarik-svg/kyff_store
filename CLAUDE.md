# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KYFF Store ("Know Your Food and Farmers") — a D2C organic food e-commerce platform built with Flask + MySQL + Jinja2. All SQLAlchemy models and API routes are fully implemented. The frontend templates are complete HTML/CSS/JS pages served by Flask.

## Development Commands

All backend commands run from `backend/` with the virtualenv active:

```bash
cd backend
source venv/Scripts/activate      # Windows

# Run the dev server
python run.py                     # http://localhost:5000

# Generate + apply a migration after model changes
flask db migrate -m "describe change"
flask db upgrade

# Other DB commands
flask db upgrade                  # Apply existing migrations
flask db downgrade                # Rollback last migration
```

Environment: copy `backend/.env.example` → `backend/.env` and fill in:
- `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`
- `SECRET_KEY`, `JWT_SECRET_KEY`
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`
- `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`

DB passwords with special characters are URL-encoded automatically via `quote_plus` in `config/settings.py`.

## Architecture

### Request Flow

Flask serves both HTML pages and JSON API responses from the same process:

- **Page routes** (`routes/views.py`, no prefix) — render Jinja2 templates; no auth logic, data is loaded client-side via JS
- **API routes** (all prefixed `/api/`) — return `{"success": bool, "message": str, "data": {...}}` JSON

### Backend: `backend/app/`

- **`__init__.py`** — `create_app()` factory; registers all blueprints and extensions
- **`extensions.py`** — shared instances: `db`, `migrate`, `bcrypt`, `jwt`, `mail`, `cors`
- **`config/settings.py`** — all config loaded from `.env`

**Blueprint/Route mapping:**

| File | Prefix | Notes |
|------|--------|-------|
| `routes/views.py` | *(none)* | HTML page rendering |
| `routes/auth.py` | `/api/auth` | JWT auth, password reset |
| `routes/products.py` | `/api/products` | Listing, search, recommendations |
| `routes/categories.py` | `/api/categories` | Hierarchical category tree |
| `routes/cart.py` | `/api/cart` | Guest + logged-in cart |
| `routes/orders.py` | `/api/orders` | Place, track, cancel orders |
| `routes/payments.py` | `/api/payments` | Razorpay + COD |
| `routes/reviews.py` | `/api/reviews` | Verified-purchase reviews |
| `routes/admin.py` | `/api/admin` | Admin dashboard, full CRUD |

**Utils (currently empty stubs — logic is inline in routes):**
- `utils/auth_middleware.py`, `utils/validators.py`, `utils/helpers.py`, `utils/email.py`

The `@admin_required` decorator is defined in `routes/admin.py`, not in `auth_middleware.py`.

### Key Patterns

**Response format** — every API endpoint uses local `error()` / `success()` helpers defined per-blueprint:
```python
{"success": False, "message": "reason"}          # error
{"success": True,  "message": "...", "data": {}} # success
```

**Guest cart** — `Cart` uses `session_token` (guest) or `user_id` (logged-in). Guests send `X-Session-Token: <token>` header; new tokens are returned in response and must be stored in `localStorage`. After login, call `POST /api/cart/merge` with `session_token` to merge.

**Order placement flow** (`POST /api/orders/place`):
1. Validate all stock *before* any DB mutations
2. Create `Order` with shipping address snapshot
3. `OrderItem.build_from_cart_item()` copies price/name at checkout time
4. Call `variant.reduce_stock()` for each item
5. Delete cart items

**Order cancellation** — `order.cancel()` restores stock via `variant.restore_stock()` and raises `ValueError` if the order status is not cancellable (already shipped/delivered).

**Product soft-delete** — never hard-delete products; set `is_active = False` on both product and variants to preserve order history.

**Razorpay amounts** are in paise (multiply rupees × 100). Webhook at `/api/payments/webhook` validates `X-Razorpay-Signature` using HMAC-SHA256.

**Auth tokens** — JWT `identity` is stored as `str(user.id)`; always cast with `int(get_jwt_identity())` in routes. Access token: 1 day, refresh token: 30 days.

### Models: `backend/app/models/`

15 entities (one file per model): `User`, `PasswordResetToken`, `Address`, `Category`, `Product`, `ProductVariant`, `ProductImage`, `Cart`, `CartItem`, `Order`, `OrderItem`, `Payment`, `Review`, `Banner`, `ShippingRule`.

All models expose a `to_dict()` method used in API responses. `Product.to_dict()` accepts `include_variants=True` and `include_images=True` kwargs.

`ShippingRule.get_charge_for(subtotal)` is the static method used in order placement to calculate shipping.

### Frontend: `frontend/`

- **`templates/`** — Jinja2 templates; `base.html` is the layout. Admin templates are in `templates/admin/`.
- **`static/js/api.js`** — central fetch client; auto-refreshes expired access tokens via `GET /api/auth/refresh` and retries. Tokens stored in `localStorage` as `kyff_access_token` / `kyff_refresh_token`.
- **`static/js/auth.js`** — login/register/session logic
- **`static/js/cart.js`** — cart interactions
- **`static/images/products/`** — uploaded product images (served as `/static/images/products/<filename>`)

### Data Tools: `tools/` and `backend/`

Scripts used for catalog management (not part of the app runtime):
- `backend/import_products.py` — bulk import from CSV
- `backend/organize_images.py`, `backend/review_images.py` — image pipeline utilities
- `tools/update_prices.py` — price update from Excel (`PriceList_*.xlsx`)

### Database

MySQL with `utf8mb4` encoding (supports Tamil — `name_ta` fields on `Product` and `Category`). Full schema in `docs/schema.sql`. Migrations in `backend/migrations/`.

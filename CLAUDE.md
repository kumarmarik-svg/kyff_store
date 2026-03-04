# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KYFF Store ("Know Your Food and Farmers") — a D2C organic food e-commerce platform built with Flask + MySQL + Jinja2. The project is in **early development**: all SQLAlchemy models are complete, but API route implementations are scaffolded as TODO stubs, and frontend templates are empty shells.

## Development Commands

All backend commands run from `backend/` with the virtualenv active:

```bash
# Activate virtualenv
cd backend
source venv/bin/activate          # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Database setup (first time)
mysql -u root -p -e "CREATE DATABASE kyff_store CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
flask db upgrade                  # Apply existing migrations

# Generate + apply a new migration after model changes
flask db migrate -m "describe change"
flask db upgrade

# Run the dev server
python run.py                     # http://localhost:5000

# Rollback last migration
flask db downgrade
```

Environment: copy `.env.example` → `.env` and fill in MySQL credentials, JWT secret, Razorpay keys, and SMTP config before running.

## Architecture

### Backend: `backend/app/`

- **`__init__.py`** — `create_app()` factory; registers all blueprints and extensions
- **`extensions.py`** — shared extension instances: `db`, `jwt`, `bcrypt`, `mail`, `cors`
- **`config/settings.py`** — all config loaded from `.env` via `python-dotenv`

**Blueprint/Route mapping** (all prefixed `/api/`):

| File | Prefix | Status |
|------|--------|--------|
| `routes/auth.py` | `/api/auth` | TODO |
| `routes/products.py` | `/api/products` | TODO |
| `routes/categories.py` | `/api/categories` | TODO |
| `routes/cart.py` | `/api/cart` | TODO |
| `routes/orders.py` | `/api/orders` | TODO |
| `routes/payments.py` | `/api/payments` | TODO |
| `routes/reviews.py` | `/api/reviews` | TODO |
| `routes/admin.py` | `/api/admin` | TODO |

**Utils:**
- `utils/auth_middleware.py` — JWT decorators for protecting routes
- `utils/validators.py` — Marshmallow schemas for request validation
- `utils/helpers.py` — shared utility functions
- `utils/email.py` — Flask-Mail wrappers for transactional email

### Models: Key Design Patterns

- **Order snapshots** — `Order` and `OrderItem` copy product name, variant label, and price at checkout time so historical orders are immune to catalog changes
- **Guest support** — `Cart` uses `user_id` (logged-in) or `session_token` (guest); `Order` similarly allows null `user_id`
- **Stock management** — `ProductVariant.reduce_stock()` / `restore_stock()` are called on order placement / cancellation
- **Hierarchical categories** — `Category.parent_id` self-references for nested trees
- **Review moderation** — `Review.is_approved` flag; admin must approve before visibility
- **Banner scheduling** — `Banner.is_currently_active()` checks `start_date`/`end_date` window

### Frontend: `frontend/`

- **`templates/`** — Jinja2 templates served by Flask; `base.html` is the layout base
- **`static/js/`** — Vanilla JS: `main.js`, `cart.js`, `checkout.js`
- **`static/css/`** — `main.css` + `admin.css`

### Database

MySQL with `utf8mb4` encoding (supports Tamil product names — `name_ta` fields on `Product` and `Category`). Schema SQL is in `docs/schema.sql`. Migrations managed by Flask-Migrate (Alembic); migration files live in `backend/migrations/`.

### Payment Integration

Razorpay (`RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` in `.env`). `Payment` model tracks gateway order ID, transaction ID, and raw gateway response JSON. Status flow: `initiated → pending → success/failed/refunded`.

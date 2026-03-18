# KYFF Store 🌾

> **Know Your Food and Farmers** — A D2C organic food e-commerce platform connecting Tamil Nadu farmers directly with customers.

![Flask](https://img.shields.io/badge/Flask-3.0.3-green)
![MySQL](https://img.shields.io/badge/MySQL-8.0-blue)
![Python](https://img.shields.io/badge/Python-3.11+-yellow)
![Razorpay](https://img.shields.io/badge/Payment-Razorpay-blue)

---

## 📸 Screenshots

### 🏠 Home Page
<img width="1911" height="924" src="https://github.com/user-attachments/assets/c042e23a-3bbd-456d-b6ec-8ce88f4f6dc0" />
<img width="1665" height="714" src="https://github.com/user-attachments/assets/6247bca9-f2b4-4645-afcb-ac5ac2dff692" />

---

### 🛍️ Product Page
<img width="1721" height="1061" src="https://github.com/user-attachments/assets/cdaa09d7-66a2-49df-b8ec-8cb5560db993" />

---

### 🛒 Cart Page
<img width="1889" height="1062" src="https://github.com/user-attachments/assets/f072c8d9-7ec1-44c0-b22d-0f83a4206132" />

---

### 🔐 Login Page
<img width="1692" height="1061" src="https://github.com/user-attachments/assets/52fdc8ef-4c22-417e-b212-c6bd7667b8c9" />

---

### 💳 Checkout Page
<img width="1793" height="1060" src="https://github.com/user-attachments/assets/7a0dcf91-b3d0-410a-b4eb-01ad02b39b7a" />

---

### 📦 My Orders Page
<img width="1806" height="1038" src="https://github.com/user-attachments/assets/37808857-659a-42cc-9386-9a846e7d6347" />

---

### 🚚 Track Order Page
<img width="1768" height="1055" src="https://github.com/user-attachments/assets/154dcebd-9c01-4d58-8a3e-6421762cccd8" />

---

## 🛠️ Admin Panel

### 📊 Dashboard
<img width="1889" height="948" src="https://github.com/user-attachments/assets/5eb97bb2-6e83-4fcf-af47-12a5f371f097" />

---

### 📋 Orders Management
<img width="1888" height="915" src="https://github.com/user-attachments/assets/4bdc80aa-728a-4ed9-93c4-c02879ccbc4b" />

---

### 🏷️ Product Management
<img width="1877" height="941" src="https://github.com/user-attachments/assets/676c9eb0-f9f0-4f97-9d9d-b31306e88e9d" />

---

### ⭐ Reviews Management
<img width="1835" height="1004" src="https://github.com/user-attachments/assets/bc0abc20-8efc-4602-8fd5-01bf691f7e26" />

---

### 👥 Customers
<img width="1869" height="921" src="https://github.com/user-attachments/assets/3a6d95eb-2606-4cab-8579-1be560c87db2" />

---

### 🖼️ Banner Management
<img width="1862" height="1069" src="https://github.com/user-attachments/assets/c2bb4133-63fc-471d-bd70-33d84e784bf9" />

---

### 🖼️ Image Pipeline
<img width="1882" height="1037" src="https://github.com/user-attachments/assets/74cecd21-9e2b-46f1-8eda-eef2efd02927" />

## ✨ Features

### Customer
- 🛍️ Browse products by category with filters (price, stock, sale)
- 🔍 Search across product name, Tamil name, description
- 🛒 Guest cart (session-based) + logged-in cart with merge on login
- 💳 Online payment via Razorpay (UPI, Cards, Net Banking) + Cash on Delivery
- 📦 Order tracking with status timeline and estimated delivery
- 👤 Account management — saved addresses, order history
- ⭐ Product reviews (verified purchase only)
- 🌟 Personalized recommendations based on order history
- 📉 Price drop alerts for previously purchased products

### Admin
- 📊 Dashboard with sales overview
- 🧾 Order management — view, update status, track
- 🏷️ Product management — add, edit, soft delete, manage variants
- 🖼️ Banner management for homepage slideshow
- 👥 Customer management
- ⭐ Review moderation

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Flask 3.0 (Python) |
| Database | MySQL 8 + SQLAlchemy ORM |
| Frontend | Jinja2 + Vanilla JS |
| Auth | Flask-JWT-Extended (Access + Refresh tokens) |
| Payment | Razorpay SDK |
| Email | Flask-Mail (SMTP) |
| Migrations | Flask-Migrate (Alembic) |
| Security | Flask-Bcrypt, Flask-CORS |

---

## 🚀 Quick Start

### 1. Clone & create virtual environment

```bash
git clone https://github.com/kumarmarik-svg/kyff_store.git
cd kyff_store/backend
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate      # Mac/Linux
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Flask
FLASK_DEBUG=0
SECRET_KEY=your-strong-secret-here
JWT_SECRET_KEY=another-strong-secret-here

# Database
DB_USER=root
DB_PASSWORD=your-db-password
DB_HOST=localhost
DB_PORT=3306
DB_NAME=kyff_store

# CORS
CORS_ORIGINS=http://localhost:5000

# Razorpay
RAZORPAY_KEY_ID=rzp_test_xxx
RAZORPAY_KEY_SECRET=your-secret
RAZORPAY_WEBHOOK_SECRET=your-webhook-secret

# Email (Gmail)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your@gmail.com
MAIL_PASSWORD=your-app-password
```

> 💡 Generate strong secrets:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```
> Run twice — once for `SECRET_KEY`, once for `JWT_SECRET_KEY`

### 3. Create database

```bash
mysql -u root -p -e "CREATE DATABASE kyff_store CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### 4. Run migrations

```bash
flask db upgrade
```

> Note: `flask db init` and `flask db migrate` only needed for new schema changes.
> For fresh setup, `flask db upgrade` applies all existing migrations.

### 5. Start server

```bash
python run.py
# → http://localhost:5000
```

---

## 📁 Project Structure

```
kyff_store/
├── backend/
│   ├── app/
│   │   ├── __init__.py         # App factory (create_app)
│   │   ├── extensions.py       # SQLAlchemy, JWT, Bcrypt, Mail, CORS
│   │   ├── config/
│   │   │   └── settings.py     # Config from .env
│   │   ├── models/             # 15 SQLAlchemy models
│   │   ├── routes/             # All API blueprints
│   │   ├── utils/              # Email, helpers, timezone
│   │   └── scheduler.py        # Background job (order expiry)
│   ├── migrations/             # Alembic migration history
│   ├── requirements.txt
│   └── run.py                  # Entry point
└── frontend/
    ├── templates/              # Jinja2 HTML templates
    │   └── admin/              # Admin panel templates
    └── static/
        ├── css/                # Stylesheets
        ├── js/                 # api.js, auth.js, cart.js
        └── images/products/    # Product images
```

---

## 🔌 API Blueprints

| Prefix | File | Purpose |
|---|---|---|
| `/api/auth` | routes/auth.py | Register, login, refresh, forgot password |
| `/api/products` | routes/products.py | Listing, search, recommendations, price drops |
| `/api/categories` | routes/categories.py | Category tree |
| `/api/cart` | routes/cart.py | Guest + logged-in cart CRUD |
| `/api/orders` | routes/orders.py | Place, track, cancel orders |
| `/api/payments` | routes/payments.py | Razorpay initiate, verify, COD, webhook |
| `/api/reviews` | routes/reviews.py | Product reviews (verified purchase) |
| `/api/admin` | routes/admin.py | Admin dashboard APIs |
| `/api/addresses` | routes/addresses.py | Saved delivery addresses |

### Response Format

All API responses follow this structure:

```json
// Success
{"success": true, "message": "...", "data": {...}}

// Error
{"success": false, "message": "reason"}
```

---

## 🔐 Authentication Flow

```
POST /api/auth/login
→ returns access_token (24hrs) + refresh_token (30 days)
→ stored in localStorage

Every API request:
→ Authorization: Bearer <access_token>

Token expired (401):
→ api.js auto-calls POST /api/auth/refresh
→ retries original request silently
→ user never notices!

Refresh expired (30 days):
→ redirect to login
```

---

## 🛒 Order Flow

```
Add to cart → Checkout → Place Order → Razorpay Payment → Confirmed
                                    ↓
                               COD selected → Confirmed directly
```

Order statuses: `placed → confirmed → processing → shipped → delivered`

---

## 🌐 Deployment Checklist

- [ ] Set `FLASK_DEBUG=0`
- [ ] Generate strong `SECRET_KEY` and `JWT_SECRET_KEY`
- [ ] Set `CORS_ORIGINS` to your actual domain
- [ ] Switch from `python run.py` to Gunicorn
- [ ] Add rate limiting on auth routes (Flask-Limiter)
- [ ] Move refresh token to httpOnly cookie

---

## 📦 Key Dependencies

```
Flask==3.0.3
Flask-SQLAlchemy==3.1.1
Flask-JWT-Extended==4.6.0
Flask-Migrate==4.0.7
Flask-Bcrypt==1.0.1
Flask-Mail==0.10.0
Flask-Cors==4.0.1
PyMySQL==1.1.1
razorpay==1.4.2
python-dotenv==1.0.1
Pillow==10.4.0
python-slugify==8.0.4
```

---

## 🗄️ Database

- MySQL with `utf8mb4` encoding — supports Tamil (`name_ta` fields on Product and Category)
- 15 models: User, Address, Category, Product, ProductVariant, ProductImage, Cart, CartItem, Order, OrderItem, Payment, Review, Banner, ShippingRule, PasswordResetToken
- Products are **soft-deleted** (`is_active=False`) — never hard-deleted to preserve order history

---

## 🧠 Key Design Decisions

- Single Flask app serves both UI + API → simplifies deployment
- Guest cart uses sessionStorage → avoids stale carts across sessions
- Soft delete for products → preserves order history integrity
- OrderItem stores price snapshot → prevents pricing inconsistency
- Token auto-refresh → seamless UX without forcing re-login

---

## ⚡ Challenges & Learnings

- Handling guest cart → merging without duplication
- Razorpay webhook → preventing duplicate payment updates
- Stock validation → avoiding overselling
- Token refresh → seamless auth without breaking UX

---

## 👨‍💻 AI-assisted development using Claude (Anthropic)

- **Backend:** Flask + SQLAlchemy + MySQL
- **Frontend:** Jinja2 + Vanilla JS (no React/Vue — lightweight and fast)
- **Payment:** Razorpay (UPI, Cards, Net Banking, COD)
- **AI-assisted development:** Built using Claude AI (Anthropic)

---

## 📄 License

Private project — All rights reserved.

---

*KYFF — Pure Food. Real Farmers. Your Table. 🌾*

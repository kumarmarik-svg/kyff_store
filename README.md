# 🌿 KYFF Store — Flask E-Commerce

**Know Your Food and Farmers** — A D2C organic food store built with Flask + MySQL + HTML/CSS/JS.

## Tech Stack
- **Backend**: Flask (Python), Flask-SQLAlchemy, Flask-JWT-Extended
- **Database**: MySQL (`kyff_store`)
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Payment**: Razorpay

## Project Structure
```
kyff_store/
├── backend/
│   ├── run.py                  ← Flask entry point
│   ├── requirements.txt
│   └── app/
│       ├── __init__.py         ← App factory (create_app)
│       ├── extensions.py       ← db, jwt, bcrypt, mail
│       ├── config/
│       │   └── settings.py     ← All config from .env
│       ├── models/             ← SQLAlchemy models (1 file per entity)
│       ├── routes/             ← Flask Blueprints (1 file per resource)
│       └── utils/              ← Helpers, middleware, validators
├── frontend/
│   ├── templates/              ← Jinja2 HTML templates
│   └── static/
│       ├── css/
│       ├── js/
│       └── images/
└── docs/
    ├── schema.md               ← DB schema reference
    └── api_endpoints.md        ← REST API documentation
```

## Setup

### 1. Clone & create virtual environment
```bash
cd kyff_store/backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your MySQL credentials and API keys
```

### 3. Create database
```bash
mysql -u root -p -e "CREATE DATABASE kyff_store CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### 4. Run migrations
```bash
flask db init
flask db migrate -m "initial schema"
flask db upgrade
```

### 5. Start server
```bash
python run.py
# → http://localhost:5000
```

## API Blueprints
| Prefix            | File              | Purpose                    |
|-------------------|-------------------|----------------------------|
| `/api/auth`       | routes/auth.py    | Register, login, forgot pw |
| `/api/products`   | routes/products.py| Product listing & detail   |
| `/api/categories` | routes/categories.py | Category tree            |
| `/api/cart`       | routes/cart.py    | Cart CRUD                  |
| `/api/orders`     | routes/orders.py  | Place & track orders       |
| `/api/payments`   | routes/payments.py| Razorpay integration       |
| `/api/reviews`    | routes/reviews.py | Product reviews            |
| `/api/admin`      | routes/admin.py   | Admin dashboard APIs       |

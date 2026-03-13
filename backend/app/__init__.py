from flask import Flask
from .extensions import db, migrate, bcrypt, jwt, mail, cors
from .config.settings import Config


def create_app():
    app = Flask(
        __name__,
        template_folder="../../frontend/templates",
        static_folder="../../frontend/static"
    )
    app.config.from_object(Config)

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)
    cors.init_app(app, origins=app.config["CORS_ORIGINS"])

    # ── Import all models so Flask-Migrate can detect them ────
    from .models import (
        User, PasswordResetToken, Address, Category,
        Product, ProductVariant, ProductImage,
        Cart, CartItem, Order, OrderItem,
        Payment, Review, Banner, ShippingRule, WebhookEvent
    )

    # Register blueprints
    from .routes.auth       import auth_bp
    from .routes.products   import products_bp
    from .routes.categories import categories_bp
    from .routes.cart       import cart_bp
    from .routes.orders     import orders_bp
    from .routes.payments   import payments_bp
    from .routes.reviews    import reviews_bp
    from .routes.admin      import admin_bp
    from .routes.views      import views_bp
    from .routes.addresses  import addresses_bp
    from .routes.banners    import banners_bp

    app.register_blueprint(auth_bp,       url_prefix="/api/auth")
    app.register_blueprint(products_bp,   url_prefix="/api/products")
    app.register_blueprint(categories_bp, url_prefix="/api/categories")
    app.register_blueprint(cart_bp,       url_prefix="/api/cart")
    app.register_blueprint(orders_bp,     url_prefix="/api/orders")
    app.register_blueprint(payments_bp,   url_prefix="/api/payments")
    app.register_blueprint(reviews_bp,    url_prefix="/api/reviews")
    app.register_blueprint(admin_bp,      url_prefix="/api/admin")
    app.register_blueprint(addresses_bp,  url_prefix="/api/addresses")
    app.register_blueprint(banners_bp)
    app.register_blueprint(views_bp)

    # ── Jinja template filters ─────────────────────────────────
    # Backend stores timestamps in UTC; templates convert to IST.
    from .utils.timezone import utc_to_ist, strftime
    app.jinja_env.filters["ist"]      = utc_to_ist
    app.jinja_env.filters["strftime"] = strftime

    # ── Background scheduler ───────────────────────────────────
    # Runs every 5 minutes to expire abandoned orders and restore stock.
    # Acts as a safety net for orders whose users never revisit them.
    # Lazy expiry in routes handles the real-time case.
    from .scheduler import init_scheduler
    init_scheduler(app)

    return app
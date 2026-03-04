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
    cors.init_app(app)

    # ── Import all models so Flask-Migrate can detect them ────
    from .models import (
        User, PasswordResetToken, Address, Category,
        Product, ProductVariant, ProductImage,
        Cart, CartItem, Order, OrderItem,
        Payment, Review, Banner, ShippingRule
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

    app.register_blueprint(auth_bp,       url_prefix="/api/auth")
    app.register_blueprint(products_bp,   url_prefix="/api/products")
    app.register_blueprint(categories_bp, url_prefix="/api/categories")
    app.register_blueprint(cart_bp,       url_prefix="/api/cart")
    app.register_blueprint(orders_bp,     url_prefix="/api/orders")
    app.register_blueprint(payments_bp,   url_prefix="/api/payments")
    app.register_blueprint(reviews_bp,    url_prefix="/api/reviews")
    app.register_blueprint(admin_bp,      url_prefix="/api/admin")

    return app
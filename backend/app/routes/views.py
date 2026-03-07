# ============================================================
#  VIEWS.PY — KYFF Store
#  Flask URL routes that serve HTML pages
# ============================================================

from flask import Blueprint, render_template, redirect, url_for, request

from ..models import PasswordResetToken

views_bp = Blueprint('views', __name__)


# ── Public Pages ───────────────────────────────────────────

@views_bp.route('/')
def index():
    return render_template('index.html',
        page_title       = 'KYFF — Pure. Local. Yours.',
        page_description = 'Farm-fresh organic foods from Tamil Nadu farmers.')


@views_bp.route('/products')
def products():
    return render_template('products.html',
        page_title = 'All Products — KYFF')


@views_bp.route('/product/<slug>')
def product(slug):
    return render_template('product.html',
        page_title = 'Product — KYFF')


@views_bp.route('/cart')
def cart():
    return render_template('cart.html',
        page_title = 'Cart — KYFF')


@views_bp.route('/checkout')
def checkout():
    return render_template('checkout.html',
        page_title = 'Checkout — KYFF')


# ── Orders ─────────────────────────────────────────────────

@views_bp.route('/orders')
def orders():
    return render_template('orders.html',
        page_title = 'My Orders — KYFF')


@views_bp.route('/orders/<order_number>')
def order_detail(order_number):
    return render_template('order-detail.html',
        page_title = f'Order #{order_number} — KYFF')


# ── Auth Pages ─────────────────────────────────────────────

@views_bp.route('/auth/login')
def login():
    return render_template('auth/login.html',
        page_title = 'Login — KYFF')


@views_bp.route('/auth/register')
def register():
    return render_template('auth/register.html',
        page_title = 'Create Account — KYFF')


@views_bp.route('/auth/forgot-password')
def forgot_password():
    return render_template('auth/forgot-password.html',
        page_title = 'Forgot Password — KYFF')


@views_bp.route('/auth/reset-password')
def reset_password():
    token_value = request.args.get('token', '').strip()

    token_valid = False
    if token_value:
        record = PasswordResetToken.query.filter_by(token=token_value).first()
        token_valid = record is not None and record.is_valid()

    return render_template('auth/reset-password.html',
        page_title  = 'Reset Password — KYFF',
        token       = token_value,
        token_valid = token_valid)


# ── Admin Pages ────────────────────────────────────────────

@views_bp.route('/admin')
def admin_dashboard():
    return render_template('admin/dashboard.html',
        page_title  = 'Dashboard',
        active_page = 'dashboard')


@views_bp.route('/admin/orders')
def admin_orders():
    return render_template('admin/orders.html',
        page_title  = 'Orders',
        active_page = 'orders')


@views_bp.route('/admin/products')
def admin_products():
    return render_template('admin/products.html',
        page_title  = 'Products',
        active_page = 'products')


@views_bp.route('/admin/reviews')
def admin_reviews():
    return render_template('admin/reviews.html',
        page_title  = 'Reviews',
        active_page = 'reviews')


@views_bp.route('/admin/users')
def admin_users():
    return render_template('admin/users.html',
        page_title  = 'Customers',
        active_page = 'users')


@views_bp.route('/admin/banners')
def admin_banners():
    return render_template('admin/banners.html',
        page_title  = 'Banners',
        active_page = 'banners')


# ── Fallback ───────────────────────────────────────────────

@views_bp.route('/404')
def not_found():
    return render_template('index.html'), 404


@views_bp.errorhandler(404)
def page_not_found(e):
    return redirect(url_for('views.index'))
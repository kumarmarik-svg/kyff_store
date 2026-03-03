-- ============================================================
--  DATABASE : kyff_store
--  Project  : KYFF-inspired D2C Organic Food E-Commerce
--  Backend  : Flask REST API
--  Author   : Generated for KYFF rebuild
--  Encoding : utf8mb4 (supports Tamil + Emoji)
-- ============================================================

CREATE DATABASE IF NOT EXISTS kyff_store
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE kyff_store;


-- ============================================================
-- 1. USERS
--    Stores customers and admins.
--    role ENUM keeps it simple for MVP; extend to a roles table
--    later if you add vendor/staff roles.
-- ============================================================
CREATE TABLE users (
    id            INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    name          VARCHAR(120)    NOT NULL,
    email         VARCHAR(180)    NOT NULL,
    phone         VARCHAR(15)         NULL,
    password_hash VARCHAR(255)    NOT NULL,
    role          ENUM('customer','admin') NOT NULL DEFAULT 'customer',
    is_active     TINYINT(1)      NOT NULL DEFAULT 1,
    created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                           ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 2. PASSWORD RESET TOKENS
--    Isolated from users table.
--    One row per active reset request; deleted after use.
-- ============================================================
CREATE TABLE password_reset_tokens (
    id         INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    user_id    INT UNSIGNED  NOT NULL,
    token      VARCHAR(255)  NOT NULL,
    expires_at DATETIME      NOT NULL,
    used       TINYINT(1)    NOT NULL DEFAULT 0,
    created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_prt_token  (token),
    KEY        idx_prt_user  (user_id),

    CONSTRAINT fk_prt_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 3. ADDRESSES
--    Reusable saved addresses per user.
--    Orders snapshot the relevant fields at checkout time —
--    changes here never alter historical orders.
-- ============================================================
CREATE TABLE addresses (
    id           INT UNSIGNED   NOT NULL AUTO_INCREMENT,
    user_id      INT UNSIGNED   NOT NULL,
    full_name    VARCHAR(120)   NOT NULL,
    phone        VARCHAR(15)    NOT NULL,
    line1        VARCHAR(255)   NOT NULL,
    line2        VARCHAR(255)       NULL,
    city         VARCHAR(100)   NOT NULL,
    state        VARCHAR(100)   NOT NULL,
    pincode      VARCHAR(10)    NOT NULL,
    country      VARCHAR(60)    NOT NULL DEFAULT 'India',
    is_default   TINYINT(1)     NOT NULL DEFAULT 0,
    created_at   DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_addr_user (user_id),

    CONSTRAINT fk_addr_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 4. CATEGORIES
--    Self-referencing parent_id supports hierarchy:
--    Grains → Rice → Rice - Boiled
--    Flat categories simply leave parent_id NULL.
-- ============================================================
CREATE TABLE categories (
    id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    parent_id   INT UNSIGNED      NULL DEFAULT NULL,
    name        VARCHAR(120)  NOT NULL,
    name_ta     VARCHAR(120)      NULL COMMENT 'Tamil name',
    slug        VARCHAR(140)  NOT NULL,
    description TEXT              NULL,
    image_url   VARCHAR(500)      NULL,
    sort_order  INT           NOT NULL DEFAULT 0,
    is_active   TINYINT(1)    NOT NULL DEFAULT 1,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_cat_slug    (slug),
    KEY        idx_cat_parent (parent_id),

    CONSTRAINT fk_cat_parent
        FOREIGN KEY (parent_id) REFERENCES categories(id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 5. PRODUCTS
--    Core catalog. One row = one logical product.
--    Bilingual name (EN + Tamil) matches KYFF's naming style.
--    source_info stores farmer/origin info (KYFF's USP).
--    is_active = 0 is a soft delete — old order refs stay valid.
-- ============================================================
CREATE TABLE products (
    id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    category_id     INT UNSIGNED    NOT NULL,
    name            VARCHAR(220)    NOT NULL COMMENT 'English name',
    name_ta         VARCHAR(220)        NULL COMMENT 'Tamil name',
    slug            VARCHAR(255)    NOT NULL,
    description     TEXT                NULL,
    short_desc      VARCHAR(500)        NULL,
    source_info     VARCHAR(500)        NULL COMMENT 'Farmer / region source (KYFF USP)',
    base_price      DECIMAL(10,2)   NOT NULL COMMENT 'Lowest variant price, for display',
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    is_featured     TINYINT(1)      NOT NULL DEFAULT 0,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                             ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_prod_slug        (slug),
    KEY        idx_prod_category   (category_id),
    KEY        idx_prod_active     (is_active),
    FULLTEXT   ft_prod_search      (name, name_ta, description),

    CONSTRAINT fk_prod_category
        FOREIGN KEY (category_id) REFERENCES categories(id)
        ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 6. PRODUCT VARIANTS
--    Each row = one SKU (e.g. "250g", "500g", "1kg").
--    Products with a single size still get one variant row —
--    this keeps cart/order logic uniform.
--    sale_price NULL means no active sale.
-- ============================================================
CREATE TABLE product_variants (
    id            INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    product_id    INT UNSIGNED    NOT NULL,
    label         VARCHAR(60)     NOT NULL COMMENT 'e.g. 250g, 500g, 1kg',
    sku           VARCHAR(100)        NULL,
    price         DECIMAL(10,2)   NOT NULL,
    sale_price    DECIMAL(10,2)       NULL COMMENT 'NULL = no active sale',
    stock_qty     INT             NOT NULL DEFAULT 0,
    weight_grams  INT                 NULL COMMENT 'Actual weight for shipping calc',
    is_active     TINYINT(1)      NOT NULL DEFAULT 1,
    created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_variant_sku      (sku),
    KEY        idx_variant_product (product_id),

    CONSTRAINT fk_variant_product
        FOREIGN KEY (product_id) REFERENCES products(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 7. PRODUCT IMAGES
--    Multiple images per product, ordered by sort_order.
--    is_primary = 1 flags the main thumbnail.
-- ============================================================
CREATE TABLE product_images (
    id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    product_id  INT UNSIGNED  NOT NULL,
    image_url   VARCHAR(500)  NOT NULL,
    alt_text    VARCHAR(255)      NULL,
    is_primary  TINYINT(1)    NOT NULL DEFAULT 0,
    sort_order  INT           NOT NULL DEFAULT 0,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_img_product (product_id),

    CONSTRAINT fk_img_product
        FOREIGN KEY (product_id) REFERENCES products(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 8. CART
--    One row per user (1-to-1).
--    Guest carts: user_id NULL + session_token tracks them.
--    Cleared / deleted after successful order placement.
-- ============================================================
CREATE TABLE cart (
    id            INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    user_id       INT UNSIGNED      NULL COMMENT 'NULL for guest cart',
    session_token VARCHAR(255)      NULL COMMENT 'Guest cart identifier',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                         ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_cart_user    (user_id),
    KEY        idx_cart_session (session_token),

    CONSTRAINT fk_cart_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 9. CART ITEMS
--    One row per variant in the cart.
--    UNIQUE on (cart_id, variant_id) prevents duplicate rows —
--    adding the same item again increments quantity instead.
-- ============================================================
CREATE TABLE cart_items (
    id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    cart_id     INT UNSIGNED  NOT NULL,
    variant_id  INT UNSIGNED  NOT NULL,
    quantity    INT           NOT NULL DEFAULT 1,
    added_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_cartitem_variant (cart_id, variant_id),
    KEY        idx_ci_variant      (variant_id),

    CONSTRAINT fk_ci_cart
        FOREIGN KEY (cart_id)    REFERENCES cart(id)            ON DELETE CASCADE,
    CONSTRAINT fk_ci_variant
        FOREIGN KEY (variant_id) REFERENCES product_variants(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 10. ORDERS
--     Immutable record created at checkout.
--     Address fields are SNAPSHOTTED here — never linked live
--     to addresses table, so edits don't affect history.
--     subtotal + shipping_charge = total (store for audit).
-- ============================================================
CREATE TABLE orders (
    id               INT UNSIGNED         NOT NULL AUTO_INCREMENT,
    user_id          INT UNSIGNED             NULL COMMENT 'NULL = guest order',
    order_number     VARCHAR(30)          NOT NULL COMMENT 'Human-readable: KYFF-20240001',

    -- Address snapshot
    shipping_name    VARCHAR(120)         NOT NULL,
    shipping_phone   VARCHAR(15)          NOT NULL,
    shipping_line1   VARCHAR(255)         NOT NULL,
    shipping_line2   VARCHAR(255)             NULL,
    shipping_city    VARCHAR(100)         NOT NULL,
    shipping_state   VARCHAR(100)         NOT NULL,
    shipping_pincode VARCHAR(10)          NOT NULL,

    -- Financials
    subtotal         DECIMAL(10,2)        NOT NULL,
    shipping_charge  DECIMAL(10,2)        NOT NULL DEFAULT 0.00,
    discount_amount  DECIMAL(10,2)        NOT NULL DEFAULT 0.00,
    total            DECIMAL(10,2)        NOT NULL,

    -- Status
    status           ENUM(
                       'pending',
                       'confirmed',
                       'processing',
                       'shipped',
                       'delivered',
                       'cancelled',
                       'refunded'
                     ) NOT NULL DEFAULT 'pending',

    notes            TEXT                     NULL COMMENT 'Customer delivery notes',
    created_at       DATETIME             NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME             NOT NULL DEFAULT CURRENT_TIMESTAMP
                                                   ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_order_number   (order_number),
    KEY        idx_order_user    (user_id),
    KEY        idx_order_status  (status),
    KEY        idx_order_created (created_at),

    CONSTRAINT fk_order_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 11. ORDER ITEMS
--     Price snapshot at time of order.
--     product_name / variant_label stored as strings so
--     renaming a product later never corrupts history.
-- ============================================================
CREATE TABLE order_items (
    id              INT UNSIGNED   NOT NULL AUTO_INCREMENT,
    order_id        INT UNSIGNED   NOT NULL,
    variant_id      INT UNSIGNED       NULL COMMENT 'NULL if variant deleted',
    product_name    VARCHAR(220)   NOT NULL COMMENT 'Snapshot',
    variant_label   VARCHAR(60)    NOT NULL COMMENT 'Snapshot e.g. 500g',
    unit_price      DECIMAL(10,2)  NOT NULL COMMENT 'Snapshot price paid',
    quantity        INT            NOT NULL,
    line_total      DECIMAL(10,2)  NOT NULL COMMENT 'unit_price * quantity',

    PRIMARY KEY (id),
    KEY idx_oi_order   (order_id),
    KEY idx_oi_variant (variant_id),

    CONSTRAINT fk_oi_order
        FOREIGN KEY (order_id)   REFERENCES orders(id)           ON DELETE CASCADE,
    CONSTRAINT fk_oi_variant
        FOREIGN KEY (variant_id) REFERENCES product_variants(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 12. PAYMENTS
--     One-to-many with orders (retry on failure = new row).
--     gateway_response stores raw JSON from Razorpay/Stripe
--     for debugging and reconciliation.
-- ============================================================
CREATE TABLE payments (
    id               INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    order_id         INT UNSIGNED  NOT NULL,
    gateway          VARCHAR(50)   NOT NULL COMMENT 'razorpay, stripe, cod, etc.',
    gateway_order_id VARCHAR(255)      NULL COMMENT 'Gateway-side order/session ID',
    transaction_id   VARCHAR(255)      NULL COMMENT 'Gateway payment ID on success',
    amount           DECIMAL(10,2) NOT NULL,
    currency         VARCHAR(5)    NOT NULL DEFAULT 'INR',
    status           ENUM(
                       'initiated',
                       'pending',
                       'success',
                       'failed',
                       'refunded'
                     ) NOT NULL DEFAULT 'initiated',
    gateway_response JSON              NULL COMMENT 'Raw webhook/callback payload',
    paid_at          DATETIME          NULL,
    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_pay_order  (order_id),
    KEY idx_pay_txn    (transaction_id),
    KEY idx_pay_status (status),

    CONSTRAINT fk_pay_order
        FOREIGN KEY (order_id) REFERENCES orders(id)
        ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 13. REVIEWS
--     Customers review products (not variants).
--     One review per user per product enforced by UNIQUE key.
--     is_approved allows admin moderation before display.
-- ============================================================
CREATE TABLE reviews (
    id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    product_id  INT UNSIGNED  NOT NULL,
    user_id     INT UNSIGNED  NOT NULL,
    rating      TINYINT       NOT NULL CHECK (rating BETWEEN 1 AND 5),
    title       VARCHAR(150)      NULL,
    body        TEXT              NULL,
    is_approved TINYINT(1)    NOT NULL DEFAULT 0,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_review_user_product (user_id, product_id),
    KEY        idx_rev_product        (product_id),

    CONSTRAINT fk_rev_product
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    CONSTRAINT fk_rev_user
        FOREIGN KEY (user_id)    REFERENCES users(id)    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 14. BANNERS
--     Homepage hero slider & promotional banners.
--     start_date / end_date enable scheduled campaigns
--     (e.g. KYFF's Diwali banner auto-activates/expires).
-- ============================================================
CREATE TABLE banners (
    id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    title       VARCHAR(150)      NULL,
    image_url   VARCHAR(500)  NOT NULL,
    link_url    VARCHAR(500)      NULL,
    position    VARCHAR(60)   NOT NULL DEFAULT 'hero' COMMENT 'hero, sidebar, popup',
    sort_order  INT           NOT NULL DEFAULT 0,
    is_active   TINYINT(1)    NOT NULL DEFAULT 1,
    start_date  DATE              NULL,
    end_date    DATE              NULL,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_banner_active (is_active, start_date, end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 15. SHIPPING RULES
--     Free shipping threshold + flat rate logic.
--     KYFF advertises "Free Shipping available" — this table
--     drives that rule without hardcoding it in Flask config.
-- ============================================================
CREATE TABLE shipping_rules (
    id              INT UNSIGNED   NOT NULL AUTO_INCREMENT,
    name            VARCHAR(100)   NOT NULL COMMENT 'e.g. Free Shipping, Standard',
    min_order_value DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
    charge          DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
    is_active       TINYINT(1)     NOT NULL DEFAULT 1,
    created_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- SEED: Default shipping rules (matches KYFF's model)
-- ============================================================
INSERT INTO shipping_rules (name, min_order_value, charge) VALUES
  ('Free Shipping',    500.00, 0.00),
  ('Standard Shipping',  0.00, 60.00);


-- ============================================================
-- RELATIONSHIP SUMMARY
-- ============================================================
-- users              1 ──< orders              (one user, many orders)
-- users              1 ──< addresses           (one user, many addresses)
-- users              1 ──1 cart                (one user, one cart)
-- users              1 ──< reviews             (one user, many reviews)
-- users              1 ──< password_reset_tokens
-- categories         1 ──< categories          (self: parent → children)
-- categories         1 ──< products            (one category, many products)
-- products           1 ──< product_variants    (one product, many SKUs)
-- products           1 ──< product_images      (one product, many images)
-- products           1 ──< reviews             (one product, many reviews)
-- cart               1 ──< cart_items
-- cart_items         >──1 product_variants
-- orders             1 ──< order_items
-- orders             1 ──< payments
-- order_items        >──1 product_variants     (nullable, soft ref)
-- ============================================================

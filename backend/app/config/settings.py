import os
from datetime import timedelta
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import quote_plus

# Always find .env inside backend/ regardless of where Flask is run from
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is not set. Add it to backend/.env before starting the server."
        )

    # Database
    # SQLALCHEMY_DATABASE_URI = (
    #     f"mysql+pymysql://{os.getenv('DB_USER','root')}:"
    #     f"{os.getenv('DB_PASSWORD','')}@"
    #     f"{os.getenv('DB_HOST','localhost')}:"
    #     f"{os.getenv('DB_PORT','3306')}/"
    #     f"{os.getenv('DB_NAME','kyff_store')}"
    # )
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{os.getenv('DB_USER','root')}:"
        f"{quote_plus(os.getenv('DB_PASSWORD',''))}@"
        f"{os.getenv('DB_HOST','localhost')}:"
        f"{os.getenv('DB_PORT','3306')}/"
        f"{os.getenv('DB_NAME','kyff_store')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # JWT
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    if not JWT_SECRET_KEY:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set. Add it to backend/.env before starting the server."
        )
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        hours=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_HOURS", 24))
    )

    # Mail
    MAIL_SERVER   = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT     = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS  = os.getenv("MAIL_USE_TLS", "True") == "True"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

    # CORS — comma-separated list of allowed origins
    # Example: CORS_ORIGINS=https://kyffstore.com,https://www.kyffstore.com
    CORS_ORIGINS = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:5000").split(",")
        if o.strip()
    ]

    # Razorpay
    RAZORPAY_KEY_ID     = os.getenv("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
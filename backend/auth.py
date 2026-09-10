"""Lightweight username/password authentication with JWT tokens."""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel
from sqlalchemy import Column, String
from sqlalchemy.orm import Session

from database import Base, get_db, SessionLocal, engine

# ── Configuration ────────────────────────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET", "change-me-in-production-please")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── User model ───────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"
    username = Column(String, primary_key=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, default="")
    # Stored as "true"/"false" string to match the rest of the schema's
    # boolean convention (e.g. Assessment.locked).
    is_admin = Column(String, default="false")


# Create table
Base.metadata.create_all(bind=engine)


# ── Lightweight migration: add is_admin column to existing DBs ───────
def _ensure_user_columns():
    from sqlalchemy import inspect as _sa_inspect, text as _sa_text

    insp = _sa_inspect(engine)
    if not insp.has_table("users"):
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "is_admin" not in cols:
        with engine.begin() as conn:
            conn.execute(
                _sa_text(
                    "ALTER TABLE users ADD COLUMN is_admin VARCHAR DEFAULT 'false'"
                )
            )
            conn.execute(
                _sa_text("UPDATE users SET is_admin = 'true' WHERE username = 'admin'")
            )


_ensure_user_columns()


# ── Seed a default admin user if table is empty ──────────────────────
def _seed_default_user():
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(
                User(
                    username="admin",
                    hashed_password=_hash_password("admin"),
                    full_name="Administrator",
                    is_admin="true",
                )
            )
            db.commit()
    finally:
        db.close()


_seed_default_user()


def is_admin(user: "User") -> bool:
    """True if the given user has admin privileges."""
    return (getattr(user, "is_admin", "false") or "false") == "true"


def hash_password(password: str) -> str:
    """Public hashing helper (used by the user-registration endpoint)."""
    return _hash_password(password)


# ── Schemas ──────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str
    username: str
    full_name: str


class UserInfo(BaseModel):
    username: str
    full_name: str


# ── Helpers ──────────────────────────────────────────────────────────
def verify_password(plain: str, hashed: str) -> bool:
    return _verify_password(plain, hashed)


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

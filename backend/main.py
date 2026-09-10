import sys
import os
import re
import uuid
from datetime import datetime
from typing import List, Dict

from fastapi import FastAPI, Depends, HTTPException, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import engine, Base, get_db, SessionLocal
import models
import schemas
from auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    hash_password,
    is_admin,
    verify_password,
    Token,
    UserInfo,
    User as AuthUser,
)

# Ensure we can import cra_agents tools
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from cra_agents.tools.product_tools import product_obligations, classify_product
    from cra_agents.tools.neo4j_tools import _get_driver
except ImportError:
    print("WARNING: Could not import cra_agents modules. Is the path correct?")

# ── DB bootstrap ─────────────────────────────────────────────────────
# If a legacy schema is detected (old `product_assessments` table without the
# new `products` table), wipe data tables so the new schema can be created
# cleanly. The `users` table (auth) is preserved when possible.
from sqlalchemy import inspect as _sa_inspect

_insp = _sa_inspect(engine)
if _insp.has_table("product_assessments") and not _insp.has_table("products"):
    print("[startup] Legacy schema detected — dropping old data tables.")
    _legacy_db = SessionLocal()
    try:
        for tbl in ("verification_answers", "product_assessments"):
            try:
                _legacy_db.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
            except Exception as _e:
                print(f"[startup] Could not drop {tbl}: {_e}")
        _legacy_db.commit()
    finally:
        _legacy_db.close()

Base.metadata.create_all(bind=engine)

# ── Per-user ownership migration ─────────────────────────────────────
# Backfill the owner_username column on existing `products` rows so legacy
# data is attributed to the seeded `admin` user.
_insp = _sa_inspect(engine)
if _insp.has_table("products"):
    _pcols = {c["name"] for c in _insp.get_columns("products")}
    if "owner_username" not in _pcols:
        print(
            "[startup] Adding owner_username column to products (backfilling 'admin')."
        )
        with engine.begin() as _conn:
            _conn.execute(
                text("ALTER TABLE products ADD COLUMN owner_username VARCHAR")
            )
            _conn.execute(
                text(
                    "UPDATE products SET owner_username = 'admin' WHERE owner_username IS NULL"
                )
            )
    else:
        # Make sure orphaned rows still resolve to admin
        with engine.begin() as _conn:
            _conn.execute(
                text(
                    "UPDATE products SET owner_username = 'admin' WHERE owner_username IS NULL OR owner_username = ''"
                )
            )

# Add quiz metadata columns to verification_answers if missing.
_insp = _sa_inspect(engine)
if _insp.has_table("verification_answers"):
    _vacols = {c["name"] for c in _insp.get_columns("verification_answers")}
    with engine.begin() as _conn:
        if "verification_text" not in _vacols:
            _conn.execute(
                text(
                    "ALTER TABLE verification_answers ADD COLUMN verification_text TEXT DEFAULT ''"
                )
            )
        if "associated_obligations" not in _vacols:
            _conn.execute(
                text(
                    "ALTER TABLE verification_answers ADD COLUMN associated_obligations TEXT DEFAULT '[]'"
                )
            )

app = FastAPI(title="RegComply - Compliance Assessment Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth middleware: protect /api/* except public routes ──────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from auth import SECRET_KEY, ALGORITHM

_PUBLIC_PATHS = {"/api/auth/login", "/api/regulations", "/docs", "/openapi.json"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        # Allow non-API, public routes, and OPTIONS (CORS preflight)
        if (
            not path.startswith("/api/")
            or path in _PUBLIC_PATHS
            or request.method == "OPTIONS"
        ):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401, content={"detail": "Not authenticated"}
            )

        token = auth_header[7:]
        try:
            from jose import jwt as _jwt

            payload = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            if not payload.get("sub"):
                raise ValueError()
        except Exception:
            return JSONResponse(
                status_code=401, content={"detail": "Invalid or expired token"}
            )

        return await call_next(request)


app.add_middleware(AuthMiddleware)


# ── Available regulations ────────────────────────────────────────────
REGULATIONS = [
    {
        "id": "CRA",
        "name": "Cyber Resilience Act",
        "short": "CRA",
        "full_ref": "Regulation (EU) 2024/2847",
        "domain": "Cybersecurity",
    },
    {
        "id": "Part-IS",
        "name": "Part-IS — Information Security",
        "short": "Part-IS",
        "full_ref": "Implementing Regulation (EU) 2023/203",
        "domain": "Aviation / Information Security",
    },
]


@app.get("/api/regulations")
def list_regulations():
    """Return the list of supported regulations."""
    return REGULATIONS


# ── Helpers: build response payloads from ORM objects ────────────────
def _assessment_response(
    a: "models.Assessment", progress_percent: int = 0
) -> schemas.ProductAssessmentResponse:
    pv = a.product_version
    p = pv.product if pv else None
    return schemas.ProductAssessmentResponse(
        id=a.id,
        product_id=p.id if p else "",
        product_version_id=pv.id if pv else "",
        version_number=pv.version_number if pv else 0,
        product_name=p.name if p else "",
        description=pv.description if pv else "",
        regulation=a.regulation or "CRA",
        obligation_ids=a.obligation_ids,
        product_class=a.product_class or "default",
        confidence=a.confidence or "",
        reasoning=a.reasoning or "",
        matched_categories=a.matched_categories,
        key_features=pv.key_features if pv else [],
        actor_roles=pv.actor_roles if pv else ["manufacturer"],
        annex_iii_numbers=a.annex_iii_numbers,
        conformity_route=a.conformity_route or "",
        quiz_page=int(a.quiz_page or 1),
        locked=(a.locked or "false") == "true",
        created_at=a.created_at or "",
        progress_percent=progress_percent,
    )


def _compute_progress(assessments: list, db: Session) -> dict[str, int]:
    """Return {assessment_id: progress_percent 0-100} for a list of Assessments.

    Reads verification counts from Neo4j once and answered counts from SQLite.
    """
    if not assessments:
        return {}
    all_obl_ids: set = set()
    for a in assessments:
        all_obl_ids.update(a.obligation_ids)
    verif_counts: dict[str, int] = {}
    if all_obl_ids:
        driver = _get_driver()
        try:
            with driver.session() as session:
                for a in assessments:
                    if not a.obligation_ids:
                        verif_counts[a.id] = 0
                        continue
                    res = session.run(
                        """
                        MATCH (o:Obligation)-[:HAS_VERIFICATION]->(v:VerificationAction)
                        WHERE o.id IN $obl_ids
                        RETURN count(DISTINCT v) AS total
                        """,
                        obl_ids=a.obligation_ids,
                    )
                    rec = res.single()
                    verif_counts[a.id] = rec["total"] if rec else 0
        except Exception:
            pass
        finally:
            driver.close()
    out: dict[str, int] = {}
    for a in assessments:
        total = verif_counts.get(a.id, 0)
        answered = (
            db.query(models.VerificationAnswer)
            .filter(
                models.VerificationAnswer.assessment_id == a.id,
                models.VerificationAnswer.status != "",
            )
            .count()
        )
        out[a.id] = 0 if total == 0 else min(100, int((answered / total) * 100))
    return out


def _version_response(v: "models.ProductVersion") -> schemas.ProductVersionResponse:
    return schemas.ProductVersionResponse(
        id=v.id,
        version_number=v.version_number,
        description=v.description or "",
        technical_file_name=v.technical_file_name or "",
        key_features=v.key_features,
        actor_roles=v.actor_roles,
        created_at=v.created_at or "",
        has_locked_assessment=v.has_locked_assessment,
        assessments_count=len(v.assessments),
    )


def _classify_for_assessment(a: "models.Assessment") -> dict:
    """Run CRA classification using the assessment's current product+version data."""
    actor_role = (a.product_version.actor_roles or ["manufacturer"])[0]
    product_text = _build_product_text(
        a.product_version.product.name,
        a.product_version.description,
        a.product_version.product,
    )
    result = classify_product(description=product_text, actor_role=actor_role)
    if result.get("status") not in (None, "ok"):
        raise RuntimeError(result.get("message", "Classification failed"))
    return result.get("classification", {})


def _format_product_comments(comments) -> str:
    """DEPRECATED: comments are now distilled into rules via reflection.

    Retained for backward compatibility. The injection block is built from
    the product's *active rules* (see `_build_product_text` below), not from
    raw comments — that way the LLM sees crisp, deduplicated directives
    rather than free‑form notes.
    """
    return ""


def _active_rule_texts(product) -> list[str]:
    """Return the text of every ACTIVE rule attached to the product."""
    if not product or not getattr(product, "rules", None):
        return []
    return [
        r.text for r in product.rules if (r.status or "active") == "active" and r.text
    ]


def _build_product_text(name: str, description: str, comments=None) -> str:
    """Compose the canonical product blurb fed to the AI classifier/selector.

    The optional ``comments`` argument is kept for callers that still pass a
    Product (or its comments collection). What actually gets injected is the
    set of distilled reflection rules attached to the same product, accessed
    via ``comments[0].product.rules`` when available.
    """
    from reflection import format_rules_block

    out = f"Product: {name}\nDescription: {description or ''}"
    # Best-effort: extract the parent Product from whatever was passed in so
    # we can read .rules. Callers can also pass a Product directly.
    rules: list[str] = []
    try:
        if comments is None:
            pass
        elif hasattr(comments, "rules"):
            # A Product was passed
            rules = _active_rule_texts(comments)
        elif isinstance(comments, (list, tuple)) and comments:
            first = comments[0]
            prod = getattr(first, "product", None)
            if prod is not None:
                rules = _active_rule_texts(prod)
    except Exception:  # noqa: BLE001
        rules = []

    block = format_rules_block(rules)
    if block:
        out += f"\n{block}"
    return out


def _apply_classification(
    a: "models.Assessment", classification: dict, regulation: str
) -> None:
    if regulation != "CRA":
        a.product_class = None
        a.confidence = None
        a.reasoning = None
        a.matched_categories = []
        a.annex_iii_numbers = []
        # actor_roles & key_features live on the version
        return
    a.product_class = classification.get("product_class", "default")
    a.confidence = classification.get("confidence", "")
    a.reasoning = classification.get("reasoning", "")
    a.matched_categories = classification.get("matched_categories", [])
    a.annex_iii_numbers = classification.get("annex_iii_numbers", [])
    # Version-level classification artefacts
    pv = a.product_version
    if classification.get("key_features"):
        pv.key_features = classification.get("key_features", [])
    if classification.get("actor_roles"):
        pv.actor_roles = classification.get("actor_roles", ["manufacturer"])


# ── Authentication endpoints ─────────────────────────────────────────
@app.post("/api/auth/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = create_access_token(data={"sub": user.username})
    return Token(
        access_token=token,
        token_type="bearer",
        username=user.username,
        full_name=user.full_name or user.username,
    )


@app.get("/api/auth/me", response_model=UserInfo)
def get_me(current_user: AuthUser = Depends(get_current_user)):
    return UserInfo(
        username=current_user.username,
        full_name=current_user.full_name or current_user.username,
    )


# ── Admin-only user management ───────────────────────────────────────
def _require_admin(user: AuthUser) -> None:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin privileges required.")


@app.post("/api/auth/register", response_model=schemas.UserDetail)
def register_user(
    body: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Create a new user. Admin-only."""
    _require_admin(current_user)
    username = (body.username or "").strip()
    if not username or not body.password:
        raise HTTPException(
            status_code=400, detail="username and password are required"
        )
    if db.query(AuthUser).filter(AuthUser.username == username).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    u = AuthUser(
        username=username,
        hashed_password=hash_password(body.password),
        full_name=(body.full_name or "").strip(),
        is_admin="true" if body.is_admin else "false",
    )
    db.add(u)
    db.commit()
    return schemas.UserDetail(
        username=u.username,
        full_name=u.full_name or "",
        is_admin=is_admin(u),
    )


@app.get("/api/auth/users", response_model=list[schemas.UserDetail])
def list_users(
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """List all users. Admin-only."""
    _require_admin(current_user)
    users = db.query(AuthUser).order_by(AuthUser.username).all()
    return [
        schemas.UserDetail(
            username=u.username,
            full_name=u.full_name or "",
            is_admin=is_admin(u),
        )
        for u in users
    ]


@app.get("/api/auth/users/shareable", response_model=list[schemas.UserDetail])
def list_shareable_users(
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Users available as share targets: everyone except admins and the caller."""
    users = (
        db.query(AuthUser)
        .filter(AuthUser.username != current_user.username)
        .order_by(AuthUser.username)
        .all()
    )
    return [
        schemas.UserDetail(
            username=u.username,
            full_name=u.full_name or "",
            is_admin=False,
        )
        for u in users
        if not is_admin(u)
    ]


@app.post("/api/auth/change-password")
def change_password(
    body: schemas.PasswordChange,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Change the calling user's own password (requires current password)."""
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=400, detail="New password must be at least 8 characters."
        )
    current_user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"status": "ok"}


@app.put("/api/auth/users/{username}/password")
def admin_reset_password(
    username: str,
    body: schemas.AdminPasswordReset,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Force-reset any user's password without their current one. Admin-only."""
    _require_admin(current_user)
    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=400, detail="New password must be at least 8 characters."
        )
    user = db.query(AuthUser).filter(AuthUser.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"status": "ok"}


# ── Per-user product scoping helpers ─────────────────────────────────
def _scope_products(db: Session, user: AuthUser):
    """Return a base Product query scoped to what `user` is allowed to see.

    Admin sees every product. Everyone else sees products they own *or* have
    been explicitly granted collaborator access to via the product_shares
    table.
    """
    q = db.query(models.Product)
    if not is_admin(user):
        from sqlalchemy import or_

        q = (
            q.outerjoin(
                models.ProductShare,
                (models.ProductShare.product_id == models.Product.id)
                & (models.ProductShare.username == user.username),
            )
            .filter(
                or_(
                    models.Product.owner_username == user.username,
                    models.ProductShare.username == user.username,
                )
            )
            .distinct()
        )
    return q


def _product_role(product: "models.Product", user: AuthUser) -> str:
    """Return the user's role on this product: admin | owner | collaborator."""
    if is_admin(user):
        return "admin"
    if product.owner_username == user.username:
        return "owner"
    return "collaborator"


def _get_product_or_404(
    db: Session, product_id: str, user: AuthUser
) -> "models.Product":
    p = _scope_products(db, user).filter(models.Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    return p


def _require_owner(product: "models.Product", user: AuthUser) -> None:
    """Reject collaborators from owner-only actions (delete, rename, share)."""
    if is_admin(user):
        return
    if product.owner_username != user.username:
        raise HTTPException(
            status_code=403,
            detail="Only the product owner can perform this action.",
        )


def _get_assessment_or_404(
    db: Session, assessment_id: str, user: AuthUser
) -> "models.Assessment":
    a = (
        db.query(models.Assessment)
        .filter(models.Assessment.id == assessment_id)
        .first()
    )
    if not a:
        raise HTTPException(status_code=404, detail="Assessment not found")
    if is_admin(user):
        return a
    prod = a.product
    if not prod:
        raise HTTPException(status_code=404, detail="Assessment not found")
    if prod.owner_username == user.username:
        return a
    # Check collaborator share
    share = (
        db.query(models.ProductShare)
        .filter(
            models.ProductShare.product_id == prod.id,
            models.ProductShare.username == user.username,
        )
        .first()
    )
    if not share:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return a


# ── Ollama / Gemma 4 file summarisation helper ───────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

# MODEL_TYPE controls which backend summarises uploaded files:
#   LOCAL   -> Ollama (gemma4:*)
#   OFFLOAD -> Gemini via Google GenAI
# Be tolerant of inline comments (e.g. "OFFLOAD  # use Gemini") that some env
# loaders pass through verbatim.
MODEL_TYPE = os.getenv("MODEL_TYPE", "LOCAL").split("#", 1)[0].strip().upper()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").split("#", 1)[0].strip()

_SUMMARISE_PROMPT_TEMPLATE = (
    "You are an expert technical writer. "
    "Read the following document content carefully and produce a structured product description summary. "
    "The summary should cover:\n"
    "- Product name and purpose\n"
    "- Key functionalities and features\n"
    "- Technical architecture (connectivity, protocols, interfaces)\n"
    "- Data handling (what data is collected, processed, stored)\n"
    "- Target users and deployment context\n"
    "- Security-relevant aspects (authentication, encryption, update mechanisms)\n\n"
    "Write the summary in clear, concise paragraphs. "
    "Focus on information relevant for a cybersecurity compliance assessment ({regulation_context}). "
    "If the document is not a product specification, still extract all technically relevant information."
)

_REGULATION_CONTEXT = {
    "CRA": "EU Cyber Resilience Act",
    "Part-IS": "PART-IS Implementing Regulation (EU) 2023/203 — aviation information security",
}

_SUPPORTED_EXTENSIONS = {
    "pdf",
    "docx",
    "txt",
    "md",
    "csv",
    "png",
    "jpg",
    "jpeg",
    "webp",
    "gif",
}


def _ollama_generate(prompt: str, files: list[bytes] | None = None) -> str:
    """Call Ollama's generate API with Gemma 4 (multimodal)."""
    import base64
    import httpx

    payload: dict = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if files:
        payload["images"] = [base64.b64encode(f).decode() for f in files]

    resp = httpx.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json=payload,
        timeout=300.0,
    )
    if resp.status_code >= 400:
        # Surface Ollama's error body to make debugging actionable.
        body = resp.text[:500]
        raise RuntimeError(
            f"Ollama {resp.status_code} for model '{OLLAMA_MODEL}': {body}"
        )
    return resp.json().get("response", "").strip()


_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}


def _extract_pdf_text(content: bytes) -> str:
    from io import BytesIO
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(p for p in parts if p).strip()


def _extract_docx_text(content: bytes) -> str:
    from io import BytesIO
    from docx import Document

    doc = Document(BytesIO(content))
    parts = [p.text for p in doc.paragraphs if p.text]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text:
                    parts.append(cell.text)
    return "\n".join(parts).strip()


_MIME_BY_EXT = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "txt": "text/plain",
    "md": "text/markdown",
    "csv": "text/csv",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _gemini_summarise(prompt: str, content: bytes, mime_type: str) -> str:
    """Summarise a file with Gemini multimodal (used in OFFLOAD mode)."""
    from google import genai
    from google.genai import types as genai_types

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OFFLOAD mode requires GOOGLE_API_KEY to be set in the backend env."
        )

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=genai_types.Content(
            role="user",
            parts=[
                genai_types.Part.from_text(text=prompt),
                genai_types.Part.from_bytes(data=content, mime_type=mime_type),
            ],
        ),
    )
    return (resp.text or "").strip()


def _gemini_text(prompt: str) -> str:
    """Plain-text Gemini call (used in OFFLOAD mode for txt/md/csv)."""
    from google import genai
    from google.genai import types as genai_types

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OFFLOAD mode requires GOOGLE_API_KEY to be set in the backend env."
        )

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=prompt)],
        ),
    )
    return (resp.text or "").strip()


def _llm_text(prompt: str) -> str:
    """MODEL_TYPE-aware plain-text LLM call.

    Routes through cra_agents.tools._llm so LOCAL hits Ollama and OFFLOAD
    hits Gemini using the configured BATCH_MODEL.
    """
    from cra_agents.tools._llm import generate as _generate

    return _generate(prompt)


def _summarise_file(filename: str, content: bytes, regulation: str = "CRA") -> str:
    """Summarise an uploaded file into a product description.

    Routes through Gemini when MODEL_TYPE=OFFLOAD, otherwise through Ollama (gemma4).
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: .{ext}. Supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}."
        )

    reg_context = _REGULATION_CONTEXT.get(regulation, "cybersecurity regulation")
    prompt = _SUMMARISE_PROMPT_TEMPLATE.format(regulation_context=reg_context)

    # ── OFFLOAD: Gemini handles every supported file type natively ──
    if MODEL_TYPE == "OFFLOAD":
        if ext in ("txt", "md", "csv"):
            try:
                file_text = content.decode("utf-8")
            except UnicodeDecodeError:
                file_text = content.decode("latin-1")
            full_prompt = f"{prompt}\n\n--- DOCUMENT CONTENT ---\n{file_text}"
            text = _gemini_text(full_prompt)
        else:
            mime = _MIME_BY_EXT.get(ext, "application/octet-stream")
            text = _gemini_summarise(prompt, content, mime)
        if not text:
            raise ValueError(
                "Gemini could not extract meaningful content from the file."
            )
        return text

    # ── LOCAL: Ollama (gemma4) ──
    if ext in _IMAGE_EXTENSIONS:
        # Real images — send as multimodal input
        text = _ollama_generate(prompt, files=[content])
    else:
        # Text-based formats: extract text locally, then send as a text prompt.
        # Ollama's `images` field only accepts real images; sending PDF/DOCX
        # bytes there causes a 500 Internal Server Error.
        if ext == "pdf":
            try:
                file_text = _extract_pdf_text(content)
            except Exception as e:
                raise ValueError(f"Failed to read PDF: {e}")
        elif ext == "docx":
            try:
                file_text = _extract_docx_text(content)
            except Exception as e:
                raise ValueError(f"Failed to read DOCX: {e}")
        else:  # txt, md, csv
            try:
                file_text = content.decode("utf-8")
            except UnicodeDecodeError:
                file_text = content.decode("latin-1")

        if not file_text.strip():
            raise ValueError(
                "No extractable text was found in the file (it may be a scanned PDF or empty document)."
            )

        # Cap very large documents to keep the prompt within Ollama's context window.
        max_chars = 60_000
        if len(file_text) > max_chars:
            file_text = file_text[:max_chars] + "\n\n[... truncated ...]"

        prompt = f"{prompt}\n\n--- DOCUMENT CONTENT ---\n{file_text}"
        text = _ollama_generate(prompt)

    if not text:
        raise ValueError("Gemma 4 could not extract meaningful content from the file.")
    return text


@app.post("/api/assessments", response_model=schemas.ProductAssessmentResponse)
async def create_assessment(
    product_name: str = Form(...),
    description: str = Form(""),
    regulation: str = Form("CRA"),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Legacy endpoint: create a new Product (+ V1 + Assessment) from scratch.

    Used by the "New Product" form in the UI. For adding an assessment to an
    existing product, use POST /api/products/{id}/assessments.
    """
    # Reject duplicate product names *within this user's scope*
    existing = (
        db.query(models.Product)
        .filter(
            models.Product.name == product_name,
            models.Product.owner_username == current_user.username,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f'A product named "{product_name}" already exists. Open it to add another assessment.',
        )

    tech_filename = ""
    if file and file.filename:
        try:
            file_content = await file.read()
            description = _summarise_file(file.filename, file_content, regulation)
            tech_filename = file.filename
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"File summarisation failed: {e}"
            )

    if not description.strip():
        raise HTTPException(
            status_code=400, detail="Please provide a description or upload a file."
        )

    # Create Product + V1 + Assessment in one transaction
    product = models.Product(name=product_name, owner_username=current_user.username)
    db.add(product)
    db.flush()  # get product.id

    version = models.ProductVersion(
        product_id=product.id,
        version_number=1,
        description=description,
        technical_file_name=tech_filename,
    )
    db.add(version)
    db.flush()

    assessment = models.Assessment(
        product_version_id=version.id,
        regulation=regulation,
    )
    assessment.obligation_ids = []
    db.add(assessment)
    db.flush()

    # Run classification (CRA only)
    classification: dict = {}
    if regulation == "CRA":
        try:
            product_text = _build_product_text(product_name, description, product)
            result = classify_product(
                description=product_text, actor_role="manufacturer"
            )
            classification = result.get("classification", {})
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=500, detail=f"AI classification failed: {e}"
            )
        _apply_classification(assessment, classification, regulation)

    db.commit()
    db.refresh(assessment)
    return _assessment_response(assessment)


# ── Product CRUD ─────────────────────────────────────────────────────
@app.get("/api/products", response_model=list[schemas.ProductSummary])
def list_products(
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """List all products with version & assessment counts (scoped to user; admin sees all)."""
    products = (
        _scope_products(db, current_user)
        .order_by(models.Product.created_at.desc())
        .all()
    )
    out = []
    for p in products:
        latest = p.latest_version
        out.append(
            schemas.ProductSummary(
                id=p.id,
                name=p.name,
                owner_username=p.owner_username or "",
                role=_product_role(p, current_user),
                created_at=p.created_at or "",
                versions_count=len(p.versions),
                assessments_count=sum(len(v.assessments) for v in p.versions),
                latest_version_number=latest.version_number if latest else None,
            )
        )
    return out


@app.get("/api/products/{product_id}", response_model=schemas.ProductDetail)
def get_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Return a product with all its versions."""
    p = _get_product_or_404(db, product_id, current_user)
    return schemas.ProductDetail(
        id=p.id,
        name=p.name,
        owner_username=p.owner_username or "",
        role=_product_role(p, current_user),
        created_at=p.created_at or "",
        versions=[_version_response(v) for v in p.versions],
    )


@app.put("/api/products/{product_id}", response_model=schemas.ProductDetail)
def update_product(
    product_id: str,
    body: schemas.ProductUpdate,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Rename a product (the only product-level field)."""
    p = _get_product_or_404(db, product_id, current_user)
    _require_owner(p, current_user)
    if body.name is not None and body.name != p.name:
        conflict = (
            db.query(models.Product)
            .filter(
                models.Product.name == body.name,
                models.Product.owner_username == p.owner_username,
                models.Product.id != product_id,
            )
            .first()
        )
        if conflict:
            raise HTTPException(
                status_code=409, detail="Another product already uses this name."
            )
        p.name = body.name
        db.commit()
        db.refresh(p)
    return schemas.ProductDetail(
        id=p.id,
        name=p.name,
        owner_username=p.owner_username or "",
        role=_product_role(p, current_user),
        created_at=p.created_at or "",
        versions=[_version_response(v) for v in p.versions],
    )


@app.delete("/api/products/{product_id}")
def delete_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Delete a product and ALL its versions + assessments (cascade)."""
    p = _get_product_or_404(db, product_id, current_user)
    _require_owner(p, current_user)
    db.delete(p)
    db.commit()
    return {"status": "ok"}


# ── Product sharing (owner/admin only) ─────────────────────────────
def _share_response(s: "models.ProductShare") -> schemas.ProductShareResponse:
    return schemas.ProductShareResponse(
        product_id=s.product_id,
        username=s.username,
        granted_by=s.granted_by or "",
        created_at=s.created_at or "",
    )


@app.get(
    "/api/products/{product_id}/shares",
    response_model=list[schemas.ProductShareResponse],
)
def list_product_shares(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """List collaborators on this product. Owner/admin only."""
    p = _get_product_or_404(db, product_id, current_user)
    _require_owner(p, current_user)
    return [_share_response(s) for s in p.shares]


@app.post(
    "/api/products/{product_id}/shares",
    response_model=schemas.ProductShareResponse,
)
def create_product_share(
    product_id: str,
    body: schemas.ProductShareCreate,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Grant another user collaborator access. Owner/admin only."""
    p = _get_product_or_404(db, product_id, current_user)
    _require_owner(p, current_user)
    username = (body.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username is required")
    if username == p.owner_username:
        raise HTTPException(status_code=400, detail="User is already the owner.")
    target = db.query(AuthUser).filter(AuthUser.username == username).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    existing = (
        db.query(models.ProductShare)
        .filter(
            models.ProductShare.product_id == product_id,
            models.ProductShare.username == username,
        )
        .first()
    )
    if existing:
        return _share_response(existing)
    share = models.ProductShare(
        product_id=product_id,
        username=username,
        granted_by=current_user.username,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return _share_response(share)


@app.delete("/api/products/{product_id}/shares/{username}")
def delete_product_share(
    product_id: str,
    username: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Revoke a collaborator's access. Owner/admin only."""
    p = _get_product_or_404(db, product_id, current_user)
    _require_owner(p, current_user)
    s = (
        db.query(models.ProductShare)
        .filter(
            models.ProductShare.product_id == product_id,
            models.ProductShare.username == username,
        )
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Share not found")
    db.delete(s)
    db.commit()
    return {"status": "ok"}


@app.get(
    "/api/products/{product_id}/assessments",
    response_model=list[schemas.ProductAssessmentResponse],
)
def list_product_assessments(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """List all assessments across all versions of a product (with progress)."""
    p = _get_product_or_404(db, product_id, current_user)
    all_assessments = [a for v in p.versions for a in v.assessments]
    progress = _compute_progress(all_assessments, db)
    return [_assessment_response(a, progress.get(a.id, 0)) for a in all_assessments]


@app.delete("/api/products/{product_id}/versions/{version_id}")
def delete_product_version(
    product_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Delete a product version (cascades on its assessments).

    Refuses to delete the only version of a product (use DELETE /products/{id}
    instead) or a version with a locked assessment.
    """
    p = _get_product_or_404(db, product_id, current_user)
    v = (
        db.query(models.ProductVersion)
        .filter(
            models.ProductVersion.id == version_id,
            models.ProductVersion.product_id == product_id,
        )
        .first()
    )
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    if v.has_locked_assessment:
        raise HTTPException(
            status_code=403,
            detail="This version has a locked assessment and cannot be deleted.",
        )
    if len(p.versions) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the only version. Delete the product instead.",
        )
    db.delete(v)
    db.commit()
    return {"status": "ok"}


@app.get("/api/products/{product_id}/evidence")
def list_product_evidence(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Return evidence attached across all assessments of this product."""
    p = _get_product_or_404(db, product_id, current_user)
    assessment_ids = [a.id for v in p.versions for a in v.assessments]
    if not assessment_ids:
        return []
    answers = (
        db.query(models.VerificationAnswer)
        .filter(
            models.VerificationAnswer.assessment_id.in_(assessment_ids),
            models.VerificationAnswer.evidence != "",
        )
        .all()
    )
    if not answers:
        return []
    # Enrich with verification text from Neo4j (best-effort)
    enriched = []
    try:
        driver = _get_driver()
        with driver.session() as session:
            for a in answers:
                rec = session.run(
                    "MATCH (v:VerificationAction {id: $vid}) RETURN v.type AS type, v.description AS text",
                    vid=a.verification_id,
                ).single()
                v_text = (
                    f"{rec['type']}: {(rec['text'] or '')[:50]}"
                    if rec
                    else "Unknown Verification"
                )
                assessment = a.assessment
                enriched.append(
                    {
                        "assessment_id": a.assessment_id,
                        "assessment_name": (
                            assessment.product_name if assessment else ""
                        ),
                        "regulation": assessment.regulation if assessment else "",
                        "version_number": (
                            assessment.product_version.version_number
                            if assessment and assessment.product_version
                            else 0
                        ),
                        "verification_id": a.verification_id,
                        "verification_text": v_text,
                        "evidence": a.evidence,
                        "status": a.status,
                        "notes": a.notes,
                    }
                )
    except Exception:
        for a in answers:
            assessment = a.assessment
            enriched.append(
                {
                    "assessment_id": a.assessment_id,
                    "assessment_name": assessment.product_name if assessment else "",
                    "regulation": assessment.regulation if assessment else "",
                    "version_number": (
                        assessment.product_version.version_number
                        if assessment and assessment.product_version
                        else 0
                    ),
                    "verification_id": a.verification_id,
                    "verification_text": "Unknown Verification",
                    "evidence": a.evidence,
                    "status": a.status,
                    "notes": a.notes,
                }
            )
    finally:
        try:
            driver.close()
        except Exception:
            pass
    return enriched


# ── Product comments ─────────────────────────────────────────────────
@app.get(
    "/api/products/{product_id}/comments",
    response_model=list[schemas.ProductCommentResponse],
)
def list_product_comments(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    p = _get_product_or_404(db, product_id, current_user)
    return [
        schemas.ProductCommentResponse(
            id=c.id,
            product_id=c.product_id,
            author=c.author or "",
            text=c.text or "",
            created_at=c.created_at or "",
        )
        for c in p.comments
    ]


@app.post(
    "/api/products/{product_id}/comments",
    response_model=schemas.ReflectionResult,
)
def create_product_comment(
    product_id: str,
    body: schemas.ProductCommentCreate,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Add a comment and immediately reflect on it.

    The raw comment is stored for audit; reflection distills it (plus the
    product's current rules) into zero or more structured directives that
    become part of the product's permanent memory and are injected into
    every future classification / obligation-selection call.
    """
    p = _get_product_or_404(db, product_id, current_user)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment text must not be empty.")
    author = (body.author or "").strip() or getattr(current_user, "username", "") or ""
    c = models.ProductComment(product_id=p.id, author=author, text=text)
    db.add(c)
    db.flush()  # so we can reference c.id when storing rules

    # ── Reflection step ─────────────────────────────────────────────
    from reflection import reflect as _reflect

    description = p.latest_version.description if p.latest_version else ""
    existing_rule_texts = _active_rule_texts(p)
    new_rules_payload = _reflect(
        product_name=p.name,
        product_description=description,
        existing_rules=existing_rule_texts,
        new_feedback=f"[comment by {author or 'assessor'}] {text}",
    )

    added: list[models.ProductRule] = []
    for r in new_rules_payload:
        rule = models.ProductRule(
            product_id=p.id,
            text=r["text"],
            category=r.get("category", "scope"),
            status="active",
            source_comment_id=c.id,
        )
        db.add(rule)
        added.append(rule)

    db.commit()
    for rule in added:
        db.refresh(rule)
    db.refresh(p)

    return schemas.ReflectionResult(
        added=[_rule_response(r) for r in added],
        rules=[
            _rule_response(r) for r in p.rules if (r.status or "active") == "active"
        ],
    )


@app.delete("/api/products/{product_id}/comments/{comment_id}")
def delete_product_comment(
    product_id: str,
    comment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    _get_product_or_404(db, product_id, current_user)
    c = (
        db.query(models.ProductComment)
        .filter(
            models.ProductComment.id == comment_id,
            models.ProductComment.product_id == product_id,
        )
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")
    db.delete(c)
    db.commit()
    return {"status": "ok"}


# ── Product rules (reflection memory) ────────────────────────────────


def _rule_response(r: "models.ProductRule") -> schemas.ProductRuleResponse:
    return schemas.ProductRuleResponse(
        id=r.id,
        product_id=r.product_id,
        text=r.text or "",
        category=r.category or "scope",
        status=r.status or "active",
        source_comment_id=r.source_comment_id,
        source_assessment_id=r.source_assessment_id,
        created_at=r.created_at or "",
        updated_at=r.updated_at or r.created_at or "",
    )


@app.get(
    "/api/products/{product_id}/rules",
    response_model=list[schemas.ProductRuleResponse],
)
def list_product_rules(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    p = _get_product_or_404(db, product_id, current_user)
    return [_rule_response(r) for r in p.rules]


@app.post(
    "/api/products/{product_id}/rules",
    response_model=schemas.ProductRuleResponse,
)
def create_product_rule(
    product_id: str,
    body: schemas.ProductRuleCreate,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Manually add a rule (bypasses reflection — for power users)."""
    p = _get_product_or_404(db, product_id, current_user)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Rule text must not be empty.")
    r = models.ProductRule(
        product_id=p.id,
        text=text,
        category=(body.category or "scope").strip().lower() or "scope",
        status="active",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return _rule_response(r)


@app.put(
    "/api/products/{product_id}/rules/{rule_id}",
    response_model=schemas.ProductRuleResponse,
)
def update_product_rule(
    product_id: str,
    rule_id: str,
    body: schemas.ProductRuleUpdate,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    _get_product_or_404(db, product_id, current_user)
    r = (
        db.query(models.ProductRule)
        .filter(
            models.ProductRule.id == rule_id,
            models.ProductRule.product_id == product_id,
        )
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Rule not found")
    from datetime import datetime as _dt

    changed = False
    if body.text is not None and body.text.strip():
        r.text = body.text.strip()
        changed = True
    if body.category is not None and body.category.strip():
        r.category = body.category.strip().lower()
        changed = True
    if body.status is not None and body.status.strip().lower() in (
        "active",
        "archived",
    ):
        r.status = body.status.strip().lower()
        changed = True
    if changed:
        r.updated_at = _dt.utcnow().isoformat()
        db.commit()
        db.refresh(r)
    return _rule_response(r)


@app.delete("/api/products/{product_id}/rules/{rule_id}")
def delete_product_rule(
    product_id: str,
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    _get_product_or_404(db, product_id, current_user)
    r = (
        db.query(models.ProductRule)
        .filter(
            models.ProductRule.id == rule_id,
            models.ProductRule.product_id == product_id,
        )
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(r)
    db.commit()
    return {"status": "ok"}


@app.post(
    "/api/products/{product_id}/reflect",
    response_model=schemas.ReflectionResult,
)
def reflect_on_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Re-run reflection over ALL active comments to refresh memory.

    Useful after a string of comments was added without immediate distillation
    (or when the reflection prompt has been updated). Existing rules are NOT
    deleted; only NEW non-duplicate rules are appended.
    """
    p = _get_product_or_404(db, product_id, current_user)

    from reflection import reflect as _reflect

    description = p.latest_version.description if p.latest_version else ""
    existing = _active_rule_texts(p)
    if not p.comments:
        return schemas.ReflectionResult(
            added=[],
            rules=[
                _rule_response(r) for r in p.rules if (r.status or "active") == "active"
            ],
        )

    feedback_block = "\n".join(
        f"- [{(c.created_at or '').split('T', 1)[0]}] {c.author or 'assessor'}: {c.text}"
        for c in p.comments
    )
    proposed = _reflect(
        product_name=p.name,
        product_description=description,
        existing_rules=existing,
        new_feedback=f"All assessor comments collected so far:\n{feedback_block}",
    )

    added: list[models.ProductRule] = []
    for r in proposed:
        rule = models.ProductRule(
            product_id=p.id,
            text=r["text"],
            category=r.get("category", "scope"),
            status="active",
        )
        db.add(rule)
        added.append(rule)
    db.commit()
    for rule in added:
        db.refresh(rule)
    db.refresh(p)

    return schemas.ReflectionResult(
        added=[_rule_response(r) for r in added],
        rules=[
            _rule_response(r) for r in p.rules if (r.status or "active") == "active"
        ],
    )


@app.post(
    "/api/products/{product_id}/assessments",
    response_model=schemas.ProductAssessmentResponse,
)
async def create_assessment_for_product(
    product_id: str,
    regulation: str = Form("CRA"),
    description: str = Form(""),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Create a new assessment for an existing product.

    Reuses the latest version when description/file are unchanged. Creates a
    new version when they differ (or when the latest version is already
    referenced by a locked assessment).
    """
    p = _get_product_or_404(db, product_id, current_user)
    latest = p.latest_version
    if not latest:
        raise HTTPException(
            status_code=500, detail="Product has no version (data corruption)"
        )

    tech_filename = latest.technical_file_name or ""
    final_description = (description or "").strip()

    if file and file.filename:
        try:
            file_content = await file.read()
            final_description = _summarise_file(file.filename, file_content, regulation)
            tech_filename = file.filename
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"File summarisation failed: {e}"
            )

    if not final_description:
        final_description = latest.description or ""
    if not final_description:
        raise HTTPException(
            status_code=400,
            detail="Please provide a description or upload a file.",
        )

    desc_changed = final_description.strip() != (latest.description or "").strip()
    file_changed = bool(file and file.filename)

    if desc_changed or file_changed or latest.has_locked_assessment:
        # New version
        new_version = models.ProductVersion(
            product_id=p.id,
            version_number=latest.version_number + 1,
            description=final_description,
            technical_file_name=tech_filename,
        )
        # Carry over previous key_features / actor_roles by default
        new_version.key_features = latest.key_features
        new_version.actor_roles = latest.actor_roles
        db.add(new_version)
        db.flush()
        target_version = new_version
    else:
        target_version = latest

    assessment = models.Assessment(
        product_version_id=target_version.id,
        regulation=regulation,
    )
    assessment.obligation_ids = []
    db.add(assessment)
    db.flush()

    if regulation == "CRA":
        try:
            product_text = _build_product_text(p.name, final_description, p)
            result = classify_product(
                description=product_text,
                actor_role=(target_version.actor_roles or ["manufacturer"])[0],
            )
            classification = result.get("classification", {})
            _apply_classification(assessment, classification, regulation)
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=500, detail=f"AI classification failed: {e}"
            )

    db.commit()
    db.refresh(assessment)
    return _assessment_response(assessment)


# ── ProductVersion edit ──────────────────────────────────────────────
@app.put(
    "/api/products/{product_id}/versions/{version_id}",
    response_model=schemas.ProductVersionResponse,
)
def update_product_version(
    product_id: str,
    version_id: str,
    body: schemas.ProductVersionUpdate,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Edit a product version's description/key_features/actor_roles.

    Only allowed if no locked assessment references this version. Editing a
    frozen version requires creating a new assessment instead (which will
    auto-create a new version when description differs).
    """
    _get_product_or_404(db, product_id, current_user)
    v = (
        db.query(models.ProductVersion)
        .filter(
            models.ProductVersion.id == version_id,
            models.ProductVersion.product_id == product_id,
        )
        .first()
    )
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    if v.has_locked_assessment:
        raise HTTPException(
            status_code=403,
            detail="This version is frozen because a locked assessment references it.",
        )
    if body.description is not None:
        v.description = body.description
    if body.key_features is not None:
        v.key_features = body.key_features
    if body.actor_roles is not None:
        v.actor_roles = body.actor_roles
    db.commit()
    db.refresh(v)
    return _version_response(v)


@app.get(
    "/api/assessments/{assessment_id}", response_model=schemas.ProductAssessmentResponse
)
def get_assessment(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Get a single assessment with all product info."""
    a = _get_assessment_or_404(db, assessment_id, current_user)
    return _assessment_response(a)


@app.put(
    "/api/assessments/{assessment_id}", response_model=schemas.ProductAssessmentResponse
)
def update_assessment(
    assessment_id: str,
    data: schemas.ProductAssessmentUpdate,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Update assessment-level fields.

    Product-level fields (name) and version-level fields (description,
    key_features, actor_roles) are NOT handled here. Use
    PUT /api/products/{id} or PUT /api/products/{id}/versions/{vid} instead.
    """
    a = _get_assessment_or_404(db, assessment_id, current_user)
    # When locked, only quiz_page may be updated
    if (a.locked or "false") == "true":
        if data.quiz_page is not None:
            a.quiz_page = str(data.quiz_page)
            db.commit()
            db.refresh(a)
            return _assessment_response(a)
        raise HTTPException(
            status_code=403, detail="Assessment is locked and cannot be edited"
        )
    if data.product_class is not None:
        a.product_class = data.product_class
    if data.confidence is not None:
        a.confidence = data.confidence
    if data.reasoning is not None:
        a.reasoning = data.reasoning
    if data.matched_categories is not None:
        a.matched_categories = data.matched_categories
    if data.conformity_route is not None:
        a.conformity_route = data.conformity_route
    if data.quiz_page is not None:
        a.quiz_page = str(data.quiz_page)
    db.commit()
    db.refresh(a)
    return _assessment_response(a)


@app.post(
    "/api/assessments/{assessment_id}/reclassify",
    response_model=schemas.ProductAssessmentResponse,
)
def reclassify_assessment(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Re-run AI classification using the current product info."""
    a = _get_assessment_or_404(db, assessment_id, current_user)
    if (a.locked or "false") == "true":
        raise HTTPException(
            status_code=403, detail="Assessment is locked and cannot be reclassified"
        )
    if (a.regulation or "CRA") != "CRA":
        raise HTTPException(
            status_code=400,
            detail="Reclassification is only available for CRA assessments",
        )

    try:
        classification = _classify_for_assessment(a)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI classification failed: {e}")

    _apply_classification(a, classification, "CRA")
    db.commit()
    db.refresh(a)
    return _assessment_response(a)


# ── Helper: generate justifications via Gemini for any regulation ─────
def _generate_justifications(
    obl_rows: list,
    product_name: str,
    description: str,
    regulation: str,
    batch_size: int = 40,
) -> dict:
    """Ask the configured LLM to produce a one-sentence justification per obligation."""
    import json as _json

    reg_label = _REGULATION_CONTEXT.get(regulation, regulation)
    justifications: dict = {}

    for i in range(0, len(obl_rows), batch_size):
        batch = obl_rows[i : i + batch_size]
        obl_list = _json.dumps(
            [{"id": o["id"], "action": o["action"] or ""} for o in batch],
            ensure_ascii=False,
        )
        prompt = (
            f"You are an expert in {reg_label}.\n"
            f"Organisation: {product_name}\n"
            f"Description: {description}\n\n"
            f"Below is a JSON array of regulatory obligations:\n{obl_list}\n\n"
            "For EACH obligation, write ONE concise sentence explaining why "
            "it applies to this organisation in the context of the regulation.\n"
            'Return ONLY a JSON array of objects with keys "id" and "justification".\n'
            "No markdown fences, no extra text."
        )
        try:
            raw = _llm_text(prompt).strip()
            # Strip possible markdown fences
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            items = _json.loads(raw)
            for item in items:
                if (
                    isinstance(item, dict)
                    and item.get("id")
                    and item.get("justification")
                ):
                    justifications[item["id"]] = item["justification"]
        except Exception:
            pass  # best-effort; obligations still assigned even if justifications fail

    return justifications


def _select_obligations(
    obl_rows: list,
    org_name: str,
    description: str,
    regulation: str,
    batch_size: int = 40,
) -> tuple:
    """Ask the configured LLM to select applicable obligations AND justify each one.

    Returns (selected_ids: list[str], justifications: dict[str, str]).
    """
    import json as _json

    reg_label = _REGULATION_CONTEXT.get(regulation, regulation)
    selected_ids: list = []
    justifications: dict = {}

    for i in range(0, len(obl_rows), batch_size):
        batch = obl_rows[i : i + batch_size]
        obl_list = _json.dumps(
            [{"id": o["id"], "action": o["action"] or ""} for o in batch],
            ensure_ascii=False,
        )
        prompt = (
            f"You are an expert in {reg_label}.\n\n"
            f"Organisation: {org_name}\n"
            f"Description:\n{description}\n\n"
            f"Below is a JSON array of regulatory obligations:\n{obl_list}\n\n"
            "Your task:\n"
            "1. Determine which obligations are APPLICABLE to this specific "
            "organisation given its type, activities, and description.\n"
            "2. For each applicable obligation, write ONE concise sentence "
            "explaining WHY it applies.\n"
            "3. EXCLUDE obligations that clearly do not apply to this "
            "organisation type (e.g. obligations specific to ANSPs should "
            "not apply to airports, and vice-versa).\n\n"
            'Return ONLY a JSON array of objects with keys "id" and '
            '"justification" for the APPLICABLE obligations.\n'
            "Do NOT include obligations that do not apply.\n"
            "No markdown fences, no extra text."
        )
        try:
            raw = _llm_text(prompt).strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            items = _json.loads(raw)
            for item in items:
                if isinstance(item, dict) and item.get("id"):
                    selected_ids.append(item["id"])
                    if item.get("justification"):
                        justifications[item["id"]] = item["justification"]
        except Exception:
            # On failure, include all obligations from this batch (safe fallback)
            selected_ids.extend(r["id"] for r in batch)

    return selected_ids, justifications


@app.post(
    "/api/assessments/{assessment_id}/lock",
    response_model=schemas.ProductAssessmentResponse,
)
def lock_assessment(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Lock a product, generate obligations from current product info."""
    import json as _json

    a = _get_assessment_or_404(db, assessment_id, current_user)
    if (a.locked or "false") == "true":
        raise HTTPException(status_code=400, detail="Assessment is already locked")

    import traceback as _tb

    regulation = a.regulation or "CRA"
    obl_ids = []
    justifications = {}
    conformity_route = ""

    if regulation != "CRA":
        # ── Non-CRA regulation: fetch candidates, then LLM-select applicable ones ──
        try:
            driver = _get_driver()
            obl_rows = []
            try:
                with driver.session() as session:
                    res = session.run(
                        "MATCH (o:Obligation) WHERE o.regulation = $reg "
                        "RETURN o.id AS id, o.action AS action ORDER BY o.article_id, o.id",
                        reg=regulation,
                    )
                    obl_rows = [dict(r) for r in res]
            finally:
                driver.close()

            if obl_rows and a.description:
                obl_ids, justifications = _select_obligations(
                    obl_rows, a.product_name, a.description, regulation
                )
            else:
                obl_ids = [r["id"] for r in obl_rows]
        except Exception as e:
            _tb.print_exc()
            raise HTTPException(
                status_code=500, detail=f"Obligation generation failed: {e}"
            )
    else:
        # ── CRA: use the full classification + selection pipeline ──
        actor_role = (a.actor_roles or ["manufacturer"])[0]
        _prod = a.product_version.product if a.product_version else None
        product_text = _build_product_text(a.product_name, a.description, _prod)
        existing_classification = {
            "product_class": a.product_class or "default",
            "confidence": a.confidence or "",
            "reasoning": a.reasoning or "",
            "matched_categories": a.matched_categories,
            "key_features": a.key_features,
            "actor_roles": a.actor_roles or ["manufacturer"],
            "annex_iii_numbers": a.annex_iii_numbers,
        }

        try:
            result = product_obligations(
                description=product_text,
                actor_role=actor_role,
                classification_json=_json.dumps(existing_classification),
            )
            json_path = result.get("json_file")
            if json_path and os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    data = _json.load(f)
                    obl_ids = [
                        item.get("id")
                        for item in data.get("checklist", [])
                        if item.get("id")
                    ]
                    justifications = {
                        item["id"]: item["justification"]
                        for item in data.get("checklist", [])
                        if item.get("id") and item.get("justification")
                    }
                    conformity_route = data.get("conformity_assessment", {}).get(
                        "assessment_route", ""
                    )
        except Exception as e:
            _tb.print_exc()
            raise HTTPException(
                status_code=500, detail=f"Obligation generation failed: {e}"
            )

    a.obligation_ids = obl_ids
    a.justifications = justifications
    a.conformity_route = conformity_route
    a.locked = "true"
    db.commit()
    db.refresh(a)
    return _assessment_response(a)


@app.get("/api/assessments/{assessment_id}/questions")
def get_assessment_questions(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Fetch the tailored VerificationAction 'quiz' questions for this assessment directly from Neo4j."""
    assessment = _get_assessment_or_404(db, assessment_id, current_user)

    obl_ids = assessment.obligation_ids
    if not obl_ids:
        return []

    driver = _get_driver()
    try:
        with driver.session() as session:
            # The magical single query to fetch deduplicated verifications and embed the obligations
            res = session.run(
                """
                MATCH (o:Obligation)-[:HAS_VERIFICATION]->(v:VerificationAction)
                WHERE o.id IN $product_obligations
                RETURN 
                    v.id AS verification_id,
                    v.type AS verification_type,
                    v.description AS verification_text,
                    collect({
                        obligation_id: o.id,
                        obligation_text: o.action,
                        article: o.article_id
                    }) AS associated_obligations
                ORDER BY verification_type, verification_id
            """,
                product_obligations=obl_ids,
            )

            records = [dict(record) for record in res]
            return records
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Neo4j query failed: {e}")
    finally:
        driver.close()


@app.get("/api/assessments/{assessment_id}/answers")
def get_assessment_answers(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Fetch the user's previously submitted answers."""
    assessment = _get_assessment_or_404(db, assessment_id, current_user)

    answers = (
        db.query(models.VerificationAnswer)
        .filter(models.VerificationAnswer.assessment_id == assessment_id)
        .all()
    )
    return [
        {
            "verification_id": a.verification_id,
            "verification_text": a.verification_text or "",
            "associated_obligations": a.associated_obligations,
            "status": a.status,
            "evidence": a.evidence,
            "notes": a.notes,
        }
        for a in answers
    ]


@app.put("/api/assessments/{assessment_id}/answers")
def update_assessment_answers(
    assessment_id: str,
    update: schemas.AssessmentAnswersUpdate,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Submit a batch of answers to the Verification questions."""
    assessment = _get_assessment_or_404(db, assessment_id, current_user)

    for ans in update.answers:
        existing = (
            db.query(models.VerificationAnswer)
            .filter(
                models.VerificationAnswer.assessment_id == assessment_id,
                models.VerificationAnswer.verification_id == ans.verification_id,
            )
            .first()
        )

        if existing:
            existing.status = ans.status
            existing.evidence = ans.evidence
            existing.notes = ans.notes
            existing.verification_text = (
                ans.verification_text or existing.verification_text
            )
            if ans.associated_obligations is not None:
                existing.associated_obligations = ans.associated_obligations
        else:
            new_answer = models.VerificationAnswer(
                assessment_id=assessment_id,
                verification_id=ans.verification_id,
                verification_text=ans.verification_text or "",
                status=ans.status,
                evidence=ans.evidence,
                notes=ans.notes,
            )
            new_answer.associated_obligations = ans.associated_obligations or []
            db.add(new_answer)

    db.commit()
    return {"status": "ok", "updated": len(update.answers)}


# ── Report commentary helper ────────────────────────────────────────────
_COMMENTARY_PROMPT = """You are a cybersecurity compliance expert specialising in the EU Cyber Resilience Act (CRA).

Product: {product_name}  
Class: {product_class}  
Description: {description}

Compliance Summary:
- Total obligations assessed: {total}
- Compliant: {compliant}
- Partially compliant: {partial}
- Not compliant (gaps): {gaps}

{gap_details}

Based on the above, provide:
1. A concise overall comment (2-3 paragraphs) assessing the product's CRA compliance posture.
2. A numbered list of 3-6 specific, actionable recommendations to address the identified gaps and improve compliance.

Return your response in the following JSON format (no markdown fences):
{{
  "comment": "Your overall assessment comment here...",
  "recommendations": ["Recommendation 1", "Recommendation 2", ...]
}}"""


def _generate_report_commentary(
    product_name: str,
    description: str,
    product_class: str,
    summary: dict,
    gap_obligations: list,
) -> tuple[str, list[str]]:
    """Use the configured LLM to generate an overall comment and recommendations for the report."""
    # Build gap details (limit to first 30 to avoid token overflow)
    gap_lines = []
    for obl in gap_obligations[:30]:
        gap_lines.append(
            f"- [{obl['obligation_id']}] {obl['calculated_status']}: "
            f"{(obl.get('obligation_text') or 'No description')[:120]}"
        )
    gap_details = (
        "Key gaps:\n" + "\n".join(gap_lines) if gap_lines else "No gaps identified."
    )

    prompt = _COMMENTARY_PROMPT.format(
        product_name=product_name,
        product_class=product_class,
        description=(description or "")[:500],
        total=summary["total_obligations"],
        compliant=summary["compliant"],
        partial=summary["partially_compliant"],
        gaps=summary["not_compliant"],
        gap_details=gap_details,
    )

    try:
        text = _llm_text(prompt).strip()
    except Exception as e:
        return (f"LLM error: {e}", [])

    # Parse JSON response
    import json as _json

    # Strip markdown fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = _json.loads(text)
        return (parsed.get("comment", ""), parsed.get("recommendations", []))
    except _json.JSONDecodeError:
        return (text, [])


@app.get("/api/assessments/{assessment_id}/compliance-report")
def get_compliance_report(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Calculate and return the final compliance status of each required obligation."""
    assessment = _get_assessment_or_404(db, assessment_id, current_user)

    # 1. Get the Quiz questions logic from Neo4j (which obligations require which verifications)
    questions = get_assessment_questions(assessment_id, db, current_user)

    # 2. Get user answers
    answers_query = (
        db.query(models.VerificationAnswer)
        .filter(models.VerificationAnswer.assessment_id == assessment_id)
        .all()
    )
    answers_map = {a.verification_id: a.status for a in answers_query}

    # 3. Build a map of Obligation ID -> Required Verifications
    obligation_requirements = {}

    for q in questions:
        v_id = q["verification_id"]
        v_status = answers_map.get(v_id, "Missing")

        for assoc_obl in q["associated_obligations"]:
            obl_id = assoc_obl["obligation_id"]
            if obl_id not in obligation_requirements:
                obligation_requirements[obl_id] = {
                    "obligation_id": obl_id,
                    "article": assoc_obl["article"],
                    "obligation_text": assoc_obl["obligation_text"],
                    "verifications": [],
                }
            obligation_requirements[obl_id]["verifications"].append(
                {"verification_id": v_id, "status": v_status}
            )

    # 4. Calculate status for each obligation
    results = []
    for obl_id, data in obligation_requirements.items():
        total = len(data["verifications"])
        verified = sum(1 for v in data["verifications"] if v["status"] == "Verified")

        if verified == total and total > 0:
            status = "Compliant"
        elif verified > 0:
            status = "Partially Compliant"
        else:
            status = "Not Compliant"

        data["calculated_status"] = status
        results.append(data)

    summary_data = {
        "total_obligations": len(results),
        "compliant": sum(1 for r in results if r["calculated_status"] == "Compliant"),
        "partially_compliant": sum(
            1 for r in results if r["calculated_status"] == "Partially Compliant"
        ),
        "not_compliant": sum(
            1 for r in results if r["calculated_status"] == "Not Compliant"
        ),
    }

    # 5. Generate AI comment and recommendations
    comment = ""
    recommendations = []
    try:
        comment, recommendations = _generate_report_commentary(
            product_name=assessment.product_name,
            description=assessment.description,
            product_class=assessment.product_class or "default",
            summary=summary_data,
            gap_obligations=[
                r for r in results if r["calculated_status"] != "Compliant"
            ],
        )
    except Exception as e:
        comment = f"Commentary generation unavailable: {e}"
        recommendations = []

    return {
        "assessment_id": assessment_id,
        "obligations": results,
        "summary": summary_data,
        "comment": comment,
        "recommendations": recommendations,
    }


@app.get("/api/assessments/{assessment_id}/compliance-report/pdf")
def download_compliance_report_pdf(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Generate and return a downloadable PDF of the compliance report."""
    from fastapi.responses import StreamingResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        HRFlowable,
    )
    from reportlab.lib.units import mm
    import io

    # Get the report data (reuse existing endpoint logic)
    report = get_compliance_report(assessment_id, db, current_user)
    assessment = _get_assessment_or_404(db, assessment_id, current_user)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    story = []

    # Custom styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=20,
        spaceAfter=6,
        textColor=colors.HexColor("#1a1a2e"),
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.grey,
        spaceAfter=12,
    )
    heading2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=14,
        spaceBefore=16,
        spaceAfter=8,
        textColor=colors.HexColor("#1a1a2e"),
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=6
    )
    rec_style = ParagraphStyle(
        "Rec",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=4,
        leftIndent=12,
    )

    # Title
    reg_label = getattr(assessment, "regulation", "CRA") or "CRA"
    story.append(Paragraph(f"{reg_label} Compliance Report", title_style))
    story.append(
        Paragraph(
            f"Product: {assessment.product_name} &nbsp;|&nbsp; "
            f"Class: {(assessment.product_class or 'default').replace('_', ' ').title()} &nbsp;|&nbsp; "
            f"Generated: {datetime.now().strftime('%d %B %Y')}",
            subtitle_style,
        )
    )
    story.append(
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e0e0e0"))
    )
    story.append(Spacer(1, 8))

    # Summary table
    summary = report["summary"]
    total = summary["total_obligations"]
    score = round((summary["compliant"] / total * 100)) if total else 0
    summary_data = [
        [
            "Total Obligations",
            "Compliant",
            "Partially Compliant",
            "Not Compliant",
            "Score",
        ],
        [
            str(total),
            str(summary["compliant"]),
            str(summary["partially_compliant"]),
            str(summary["not_compliant"]),
            f"{score}%",
        ],
    ]
    t = Table(summary_data, colWidths=[90, 80, 110, 90, 60])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8f8f8")],
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 12))

    # Comment
    if report.get("comment"):
        story.append(Paragraph("Overall Assessment", heading2))
        for para in report["comment"].split("\n\n"):
            if para.strip():
                story.append(Paragraph(para.strip(), body_style))
        story.append(Spacer(1, 8))

    # Recommendations
    if report.get("recommendations"):
        story.append(Paragraph("Recommendations", heading2))
        for i, rec in enumerate(report["recommendations"], 1):
            story.append(Paragraph(f"<b>{i}.</b> {rec}", rec_style))
        story.append(Spacer(1, 12))

    # Obligation details
    story.append(Paragraph("Obligation Ledger", heading2))

    # Group by article
    articles: dict = {}
    for obl in report["obligations"]:
        art = obl.get("article") or "General"
        articles.setdefault(art, []).append(obl)

    for art_name in sorted(articles.keys()):
        obls = articles[art_name]
        compliant_n = sum(1 for o in obls if o["calculated_status"] == "Compliant")
        story.append(
            Paragraph(
                f"<b>Article {art_name}</b> — {compliant_n}/{len(obls)} compliant",
                ParagraphStyle(
                    "ArtHead",
                    parent=styles["Normal"],
                    fontSize=10,
                    spaceBefore=10,
                    spaceAfter=4,
                    textColor=colors.HexColor("#1a1a2e"),
                ),
            )
        )

        cell_style = ParagraphStyle(
            "Cell", parent=styles["Normal"], fontSize=8, leading=10
        )
        table_data = [["Obligation ID", "Description", "Status"]]
        for obl in obls:
            desc = (obl.get("obligation_text") or "—")[:150]
            table_data.append(
                [
                    Paragraph(obl["obligation_id"], cell_style),
                    Paragraph(desc, cell_style),
                    Paragraph(obl["calculated_status"], cell_style),
                ]
            )

        t = Table(table_data, colWidths=[95, 310, 75])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(t)

    doc.build(story)
    buf.seek(0)

    safe_name = assessment.product_name.replace(" ", "_").replace("/", "_")
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{reg_label}_Report_{safe_name}.pdf"'
        },
    )


@app.get("/api/assessments/{assessment_id}/export-excel")
def export_assessment_excel(
    assessment_id: str,
    include_answers: bool = True,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """
    Generate and return an Excel file with:
      - Assessment metadata (product, version, regulation)
      - Table of obligations with current assessor answers
      - Empty cells for incomplete assessments (to complete locally)
      - Excel formulas to calculate compliance scores and overall compliance %

    Query params:
      - include_answers: if True, populate with current answers; else leave blank
    """
    from fastapi.responses import StreamingResponse
    from export_assessment_excel import create_assessment_excel, export_filename

    assessment = _get_assessment_or_404(db, assessment_id, current_user)

    # Generate Excel file
    excel_buffer = create_assessment_excel(
        db,
        assessment,
        include_answers=include_answers,
    )

    filename = export_filename(assessment)
    return StreamingResponse(
        excel_buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/assessments")
def list_assessments(
    regulation: str = None,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Return all assessments with a high-level completion progress metric."""
    q = (
        db.query(models.Assessment)
        .join(
            models.ProductVersion,
            models.Assessment.product_version_id == models.ProductVersion.id,
        )
        .join(models.Product, models.ProductVersion.product_id == models.Product.id)
    )
    if not is_admin(current_user):
        q = q.filter(models.Product.owner_username == current_user.username)
    if regulation:
        q = q.filter(models.Assessment.regulation == regulation)
    assessments = q.all()

    # Collect all obligation IDs across every assessment to batch-query Neo4j once
    all_obl_ids = set()
    for a in assessments:
        all_obl_ids.update(a.obligation_ids)

    # Query Neo4j for the number of distinct verifications per assessment's obligations (batch)
    assessment_verif_counts: dict[str, int] = {}
    if all_obl_ids:
        driver = _get_driver()
        try:
            with driver.session() as session:
                # For each assessment, count distinct verifications linked to its obligations
                for a in assessments:
                    if not a.obligation_ids:
                        assessment_verif_counts[a.id] = 0
                        continue
                    res = session.run(
                        """
                        MATCH (o:Obligation)-[:HAS_VERIFICATION]->(v:VerificationAction)
                        WHERE o.id IN $obl_ids
                        RETURN count(DISTINCT v) AS total
                    """,
                        obl_ids=a.obligation_ids,
                    )
                    rec = res.single()
                    assessment_verif_counts[a.id] = rec["total"] if rec else 0
        except Exception:
            pass  # fall back to 0-progress if Neo4j unavailable
        finally:
            driver.close()

    results = []
    for a in assessments:
        total_questions = assessment_verif_counts.get(a.id, 0)
        answered = (
            db.query(models.VerificationAnswer)
            .filter(
                models.VerificationAnswer.assessment_id == a.id,
                models.VerificationAnswer.status != "",
            )
            .count()
        )
        progress = (
            0
            if total_questions == 0
            else min(100, int((answered / total_questions) * 100))
        )
        results.append(
            {
                "id": a.id,
                "product_id": a.product.id if a.product else "",
                "product_version_id": a.product_version_id,
                "version_number": (
                    a.product_version.version_number if a.product_version else 0
                ),
                "product_name": a.product_name,
                "description": a.description,
                "regulation": a.regulation or "CRA",
                "locked": (a.locked or "false") == "true",
                "progress_percent": progress,
                "created_at": a.created_at or "",
            }
        )
    return results


@app.get("/api/evidence")
def list_evidence(
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Return all artifacts attached across all assessments."""
    # We join with ProductAssessment to get the product_name for UI display
    q = db.query(models.VerificationAnswer).filter(
        models.VerificationAnswer.evidence != ""
    )
    if not is_admin(current_user):
        q = (
            q.join(
                models.Assessment,
                models.VerificationAnswer.assessment_id == models.Assessment.id,
            )
            .join(
                models.ProductVersion,
                models.Assessment.product_version_id == models.ProductVersion.id,
            )
            .join(
                models.Product,
                models.ProductVersion.product_id == models.Product.id,
            )
            .filter(models.Product.owner_username == current_user.username)
        )
    answers = q.all()

    enriched = []
    try:
        driver = _get_driver()
        with driver.session() as session:
            for a in answers:
                # Query Neo4j for the text
                v_record = session.run(
                    "MATCH (v:VerificationAction {id: $vid}) RETURN v.type AS type, v.text AS text",
                    vid=a.verification_id,
                ).single()
                v_text = (
                    f"{v_record['type']}: {v_record['text'][:50]}..."
                    if v_record
                    else "Unknown Verification"
                )

                # Determine Assessment Name (assuming standard relationship `assessment` is loaded)
                assessment_name = (
                    a.assessment.product_name if a.assessment else "Unknown product"
                )

                enriched.append(
                    {
                        "assessment_id": a.assessment_id,
                        "assessment_name": assessment_name,
                        "verification_id": a.verification_id,
                        "verification_text": v_text,
                        "evidence": a.evidence,
                        "status": a.status,
                        "notes": a.notes,
                    }
                )
    except Exception as e:
        print(f"Error querying Neo4j for evidence: {e}")
        # fallback
        for a in answers:
            enriched.append(
                {
                    "assessment_id": a.assessment_id,
                    "assessment_name": (
                        a.assessment.product_name if a.assessment else "Unknown product"
                    ),
                    "verification_id": a.verification_id,
                    "verification_text": "Unknown Verification",
                    "evidence": a.evidence,
                    "status": a.status,
                    "notes": a.notes,
                }
            )
    finally:
        if "driver" in locals():
            driver.close()
    return enriched


@app.get("/api/assessments/{assessment_id}/obligations")
def get_assessment_obligations(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Return obligation details from Neo4j for a given assessment."""
    assessment = _get_assessment_or_404(db, assessment_id, current_user)

    obl_ids = assessment.obligation_ids
    if not obl_ids:
        return []

    justifications = assessment.justifications or {}

    driver = _get_driver()
    try:
        with driver.session() as session:
            res = session.run(
                """
                MATCH (o:Obligation)
                WHERE o.id IN $ids
                OPTIONAL MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o)
                WHERE a.regulation = o.regulation
                RETURN
                    o.id AS id,
                    o.action AS action,
                    o.article_id AS article_id,
                    o.paragraph_ref AS paragraph_ref,
                    o.trigger AS trigger,
                    o.deadline AS deadline,
                    a.article_title AS article_title
                ORDER BY o.article_id, o.id
            """,
                ids=obl_ids,
            )
            records = [dict(r) for r in res]

        # Merge justifications into records
        for rec in records:
            rec["justification"] = justifications.get(rec["id"], "")

        # For IDs not found in Neo4j, return stubs so the frontend still shows them
        found_ids = {r["id"] for r in records}
        for oid in obl_ids:
            if oid not in found_ids:
                records.append(
                    {
                        "id": oid,
                        "action": None,
                        "article_id": None,
                        "paragraph_ref": None,
                        "trigger": None,
                        "deadline": None,
                        "article_title": None,
                        "justification": justifications.get(oid, ""),
                    }
                )

        return records
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Neo4j query failed: {e}")
    finally:
        driver.close()


# ── Obligation & Verification CRUD (Human-in-the-loop editing) ──────────


@app.get("/api/obligations/{obl_id}/verifications")
def get_obligation_verifications(obl_id: str):
    """Return verification actions linked to a single obligation."""
    driver = _get_driver()
    try:
        with driver.session() as session:
            res = session.run(
                """
                MATCH (o:Obligation {id: $id})-[:HAS_VERIFICATION]->(v:VerificationAction)
                RETURN v.id AS id, v.type AS type, v.description AS description, v.evidence AS evidence
                ORDER BY v.id
            """,
                id=obl_id,
            )
            return [dict(r) for r in res]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Neo4j query failed: {e}")
    finally:
        driver.close()


@app.put("/api/obligations/{obl_id}")
def update_obligation(obl_id: str, body: dict):
    """Update editable fields of an obligation node."""
    allowed = {"action", "trigger", "deadline"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    driver = _get_driver()
    try:
        with driver.session() as session:
            set_clause = ", ".join(f"o.{k} = ${k}" for k in updates)
            result = session.run(
                f"MATCH (o:Obligation {{id: $id}}) SET {set_clause} RETURN o.id AS id",
                id=obl_id,
                **updates,
            )
            if not result.single():
                raise HTTPException(status_code=404, detail="Obligation not found")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Neo4j query failed: {e}")
    finally:
        driver.close()


@app.put("/api/verifications/{verif_id}")
def update_verification(verif_id: str, body: dict):
    """Update editable fields of a verification action."""
    allowed = {"type", "description", "evidence"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    driver = _get_driver()
    try:
        with driver.session() as session:
            set_clause = ", ".join(f"v.{k} = ${k}" for k in updates)
            result = session.run(
                f"MATCH (v:VerificationAction {{id: $id}}) SET {set_clause} RETURN v.id AS id",
                id=verif_id,
                **updates,
            )
            if not result.single():
                raise HTTPException(status_code=404, detail="Verification not found")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Neo4j query failed: {e}")
    finally:
        driver.close()


@app.post("/api/obligations/{obl_id}/verifications")
def create_verification(obl_id: str, body: dict):
    """Create a new verification action and link it to an obligation."""
    from uuid import uuid4

    v_id = str(uuid4())
    v_type = body.get("type", "review")
    description = body.get("description", "")
    evidence = body.get("evidence", "")
    driver = _get_driver()
    try:
        with driver.session() as session:
            # Ensure obligation exists
            obl = session.run(
                "MATCH (o:Obligation {id: $id}) RETURN o.id", id=obl_id
            ).single()
            if not obl:
                raise HTTPException(status_code=404, detail="Obligation not found")
            session.run(
                """
                CREATE (v:VerificationAction {id: $id, type: $type, description: $desc, evidence: $evidence})
                WITH v
                MATCH (o:Obligation {id: $obl_id})
                CREATE (o)-[:HAS_VERIFICATION]->(v)
            """,
                id=v_id,
                type=v_type,
                desc=description,
                evidence=evidence,
                obl_id=obl_id,
            )
        return {
            "id": v_id,
            "type": v_type,
            "description": description,
            "evidence": evidence,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Neo4j query failed: {e}")
    finally:
        driver.close()


@app.delete("/api/verifications/{verif_id}")
def delete_verification(verif_id: str):
    """Delete a verification action and its relationships."""
    driver = _get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (v:VerificationAction {id: $id}) DETACH DELETE v RETURN count(v) AS cnt",
                id=verif_id,
            ).single()
            if not result or result["cnt"] == 0:
                raise HTTPException(status_code=404, detail="Verification not found")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Neo4j query failed: {e}")
    finally:
        driver.close()


@app.delete("/api/assessments/{assessment_id}/obligations/{obl_id}")
def delete_obligation(
    assessment_id: str,
    obl_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Delete an obligation from Neo4j and remove it from the assessment."""
    assessment = _get_assessment_or_404(db, assessment_id, current_user)

    # Remove from assessment's stored obligation_ids
    current_ids = assessment.obligation_ids or []
    if obl_id in current_ids:
        assessment.obligation_ids = [oid for oid in current_ids if oid != obl_id]
        db.commit()

    # Remove from Neo4j (detach delete removes relationships too)
    driver = _get_driver()
    try:
        with driver.session() as session:
            session.run("MATCH (o:Obligation {id: $id}) DETACH DELETE o", id=obl_id)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Neo4j query failed: {e}")
    finally:
        driver.close()


@app.delete("/api/assessments/{assessment_id}")
def delete_assessment(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Delete an assessment and all its related data."""
    assessment = _get_assessment_or_404(db, assessment_id, current_user)
    db.delete(assessment)
    db.commit()
    return {"status": "ok"}


@app.post("/api/evidence/upload")
async def upload_evidence(file: UploadFile = File(...)):
    """Upload a physical Evidence artifact to the backend."""
    import shutil
    import os
    from uuid import uuid4

    os.makedirs("uploads", exist_ok=True)
    ext = file.filename.split(".")[-1] if "." in file.filename else ""
    safe_name = f"{uuid4().hex[:8]}_{file.filename}"
    file_path = os.path.join("uploads", safe_name)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"filename": file.filename, "stored_as": safe_name}


# ── Agent Chat (ADK orchestrator bridge) ─────────────────────────────
from pydantic import BaseModel as _BaseModel
import agent_chat as _agent_chat


class ChatRequest(_BaseModel):
    message: str
    session_id: str | None = None


@app.post("/api/agent/chat")
async def agent_chat_endpoint(
    payload: ChatRequest,
    current_user: AuthUser = Depends(get_current_user),
):
    """Send a message to the ADK orchestrator and return its reply + tool events."""
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message must not be empty.")
    try:
        result = await _agent_chat.run_agent_message(
            message=payload.message,
            session_id=payload.session_id,
            user_id=current_user.username,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")

    return {
        "session_id": result.session_id,
        "reply": result.reply,
        "events": [
            {
                "kind": ev.kind,
                "author": ev.author,
                "name": ev.name,
                "args": ev.args,
                "result": ev.result,
                "text": ev.text,
            }
            for ev in result.events
        ],
    }


@app.post("/api/agent/reset")
async def agent_reset_endpoint(
    payload: ChatRequest,
    current_user: AuthUser = Depends(get_current_user),
):
    """Reset a chat session so the next message starts a fresh conversation."""
    if not payload.session_id:
        return {"ok": True}
    await _agent_chat.reset_session(payload.session_id, user_id=current_user.username)
    return {"ok": True}


@app.post("/api/agent/chat/stream")
async def agent_chat_stream_endpoint(
    payload: ChatRequest,
    current_user: AuthUser = Depends(get_current_user),
):
    """Stream ADK events as NDJSON so long-running tools (e.g. ingestion) don't
    hit proxy/gateway timeouts. The client receives one JSON object per line
    and can render progress incrementally; the last line has kind=="final"."""
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message must not be empty.")

    import json as _json
    from fastapi.responses import StreamingResponse

    async def _gen():
        # Heartbeat-friendly NDJSON. Yield as soon as each event arrives so
        # nginx/browser flush progressively.
        try:
            async for evt in _agent_chat.stream_agent_message(
                message=payload.message,
                session_id=payload.session_id,
                user_id=current_user.username,
            ):
                yield _json.dumps(evt, default=str) + "\n"
        except Exception as e:  # noqa: BLE001
            yield _json.dumps({"kind": "error", "text": f"Agent error: {e}"}) + "\n"

    return StreamingResponse(
        _gen(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # disable nginx proxy buffering
        },
    )

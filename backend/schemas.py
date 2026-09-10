from pydantic import BaseModel
from typing import List, Optional


# ── User management (admin-only registration) ────────────────────────
class UserCreate(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = ""
    is_admin: Optional[bool] = False


class UserDetail(BaseModel):
    username: str
    full_name: str = ""
    is_admin: bool = False


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class AdminPasswordReset(BaseModel):
    new_password: str


# ── Verification answers ─────────────────────────────────────────────
class VerificationAnswerSchema(BaseModel):
    verification_id: str
    status: str
    evidence: Optional[str] = ""
    notes: Optional[str] = ""
    verification_text: Optional[str] = ""
    associated_obligations: Optional[List[dict]] = []


class AssessmentAnswersUpdate(BaseModel):
    answers: List[VerificationAnswerSchema]


# ── Product / ProductVersion ─────────────────────────────────────────
class ProductCreate(BaseModel):
    """Body of POST /api/products — creates Product + initial version + assessment."""

    name: str
    description: str = ""
    regulation: Optional[str] = "CRA"


class ProductVersionResponse(BaseModel):
    id: str
    version_number: int
    description: str
    technical_file_name: Optional[str] = ""
    key_features: List[str] = []
    actor_roles: List[str] = ["manufacturer"]
    created_at: str
    has_locked_assessment: bool = False
    assessments_count: int = 0


class ProductVersionUpdate(BaseModel):
    description: Optional[str] = None
    key_features: Optional[List[str]] = None
    actor_roles: Optional[List[str]] = None


class ProductSummary(BaseModel):
    """Item returned by GET /api/products."""

    id: str
    name: str
    owner_username: str = ""
    role: str = "owner"  # owner | collaborator | admin
    created_at: str
    versions_count: int
    assessments_count: int
    latest_version_number: Optional[int] = None


class ProductDetail(BaseModel):
    """Returned by GET /api/products/{id}."""

    id: str
    name: str
    owner_username: str = ""
    role: str = "owner"
    created_at: str
    versions: List[ProductVersionResponse]


class ProductShareCreate(BaseModel):
    username: str


class ProductShareResponse(BaseModel):
    product_id: str
    username: str
    granted_by: str = ""
    created_at: str


class ProductUpdate(BaseModel):
    name: Optional[str] = None


class ProductCommentCreate(BaseModel):
    text: str
    author: Optional[str] = ""


class ProductCommentResponse(BaseModel):
    id: str
    product_id: str
    author: str
    text: str
    created_at: str


class ProductRuleResponse(BaseModel):
    id: str
    product_id: str
    text: str
    category: str
    status: str
    source_comment_id: Optional[str] = None
    source_assessment_id: Optional[str] = None
    created_at: str
    updated_at: str


class ProductRuleCreate(BaseModel):
    text: str
    category: Optional[str] = "scope"


class ProductRuleUpdate(BaseModel):
    text: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None


class ReflectionResult(BaseModel):
    """Returned by POST /products/{id}/reflect and POST /products/{id}/comments."""

    added: List[ProductRuleResponse] = []
    rules: List[ProductRuleResponse] = []


class NewAssessmentForProduct(BaseModel):
    """Body of POST /api/products/{id}/assessments.

    If description (or file via multipart) differs from the latest version,
    a new ProductVersion is created automatically. If unchanged, the assessment
    is created on the latest existing version.
    """

    regulation: Optional[str] = "CRA"
    description: Optional[str] = None  # if None or equal to latest, reuse latest


# ── Assessment (flat response, kept compatible with previous shape) ──
class ProductAssessmentResponse(BaseModel):
    id: str
    product_id: str
    product_version_id: str
    version_number: int
    product_name: str
    description: str
    regulation: Optional[str] = "CRA"
    obligation_ids: List[str]
    product_class: Optional[str] = "default"
    confidence: Optional[str] = ""
    reasoning: Optional[str] = ""
    matched_categories: Optional[List[str]] = []
    key_features: Optional[List[str]] = []
    actor_roles: Optional[List[str]] = ["manufacturer"]
    annex_iii_numbers: Optional[List[int]] = []
    conformity_route: Optional[str] = ""
    quiz_page: Optional[int] = 1
    locked: Optional[bool] = False
    created_at: Optional[str] = ""
    progress_percent: Optional[int] = 0


class ProductAssessmentUpdate(BaseModel):
    """Update assessment-level fields.

    Product-level fields (name) and version-level fields (description,
    key_features, actor_roles) are NOT updated here — they go through
    /api/products/{id} and /api/products/{id}/versions/{vid}.
    """

    product_class: Optional[str] = None
    confidence: Optional[str] = None
    reasoning: Optional[str] = None
    matched_categories: Optional[List[str]] = None
    conformity_route: Optional[str] = None
    quiz_page: Optional[int] = None


# ── Questions ────────────────────────────────────────────────────────
class QuestionResponse(BaseModel):
    verification_id: str
    verification_type: str
    verification_text: str
    associated_obligations: List[dict]

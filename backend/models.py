import uuid
import json
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


def _now() -> str:
    return datetime.utcnow().isoformat()


class Product(Base):
    """Top-level product/organisation entity. Has many versions."""

    __tablename__ = "products"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # Names are unique *per owner*, not globally — uniqueness is enforced in
    # the API layer so that different users may both have a "SmartAir".
    name = Column(String, nullable=False)
    owner_username = Column(
        String,
        ForeignKey("users.username"),
        nullable=False,
        index=True,
        default="admin",
    )
    created_at = Column(String, default=_now)

    versions = relationship(
        "ProductVersion",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductVersion.version_number",
    )
    comments = relationship(
        "ProductComment",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductComment.created_at",
    )
    rules = relationship(
        "ProductRule",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductRule.created_at",
    )
    shares = relationship(
        "ProductShare",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductShare.created_at",
    )

    @property
    def latest_version(self):
        return self.versions[-1] if self.versions else None


class ProductShare(Base):
    """Grants a non-owner user 'collaborator' access to a product.

    Collaborators can edit everything the owner can edit (versions,
    assessments, comments, rules, answers) but cannot delete the product,
    rename it, or grant access to other users.
    """

    __tablename__ = "product_shares"

    product_id = Column(String, ForeignKey("products.id"), primary_key=True)
    username = Column(String, ForeignKey("users.username"), primary_key=True)
    granted_by = Column(String, default="")
    created_at = Column(String, default=_now)

    product = relationship("Product", back_populates="shares")


class ProductComment(Base):
    """User-authored note attached to a product.

    Comments are persistent context: every subsequent CRA classification or
    obligation-selection call for this product is prefixed with these notes
    so the assessor's domain knowledge is taken into account.
    """

    __tablename__ = "product_comments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(String, ForeignKey("products.id"), nullable=False, index=True)
    author = Column(String, default="")
    text = Column(Text, nullable=False)
    created_at = Column(String, default=_now)

    product = relationship("Product", back_populates="comments")


class ProductRule(Base):
    """Reflection-memory rule distilled from comments and assessment outcomes.

    Comments are raw human feedback; rules are the **structured, executable
    constraints** the agent actually consults on every future run. One comment
    can produce zero, one, or several rules; an assessment outcome (e.g. "still
    too many obligations") can also trigger reflection that updates rules.

    Fields:
        text: Short, imperative scoping directive (e.g. "EXCLUDE obligations
            about extra-EU market surveillance — product is EEA-only").
        category: 'scope' | 'classification' | 'obligations' | 'evidence' | 'other'.
        status: 'active' (used in prompts) | 'archived' (kept for history only).
        source_comment_id: comment that triggered this rule (nullable — rules
            can be added manually or by post-assessment reflection).
        source_assessment_id: assessment outcome that triggered this rule.
    """

    __tablename__ = "product_rules"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(String, ForeignKey("products.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    category = Column(String, default="scope")
    status = Column(String, default="active")
    source_comment_id = Column(String, ForeignKey("product_comments.id"), nullable=True)
    source_assessment_id = Column(String, ForeignKey("assessments.id"), nullable=True)
    created_at = Column(String, default=_now)
    updated_at = Column(String, default=_now)

    product = relationship("Product", back_populates="rules")


class ProductVersion(Base):
    """Snapshot of a product's description + technical file.

    Editable as long as no locked assessment references it.
    Once a locked assessment exists, the version is frozen and any further
    description/file change must create a new version.
    """

    __tablename__ = "product_versions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(String, ForeignKey("products.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    description = Column(Text, default="")
    technical_file_name = Column(String, default="")
    technical_file_path = Column(String, default="")
    _key_features_json = Column("key_features", Text, default="[]")
    _actor_roles_json = Column("actor_roles", Text, default='["manufacturer"]')
    created_at = Column(String, default=_now)

    product = relationship("Product", back_populates="versions")
    assessments = relationship(
        "Assessment",
        back_populates="product_version",
        cascade="all, delete-orphan",
        order_by="Assessment.created_at",
    )

    @property
    def key_features(self):
        return json.loads(self._key_features_json or "[]")

    @key_features.setter
    def key_features(self, value):
        self._key_features_json = json.dumps(value)

    @property
    def actor_roles(self):
        return json.loads(self._actor_roles_json or '["manufacturer"]')

    @actor_roles.setter
    def actor_roles(self, value):
        self._actor_roles_json = json.dumps(value)

    @property
    def has_locked_assessment(self) -> bool:
        return any((a.locked or "false") == "true" for a in self.assessments)


class Assessment(Base):
    """A compliance assessment of a specific product version against a regulation."""

    __tablename__ = "assessments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_version_id = Column(
        String, ForeignKey("product_versions.id"), nullable=False, index=True
    )
    regulation = Column(String, default="CRA")
    product_class = Column(String, default="default")
    confidence = Column(String, default="")
    reasoning = Column(Text, default="")
    _matched_categories_json = Column("matched_categories", Text, default="[]")
    _annex_iii_numbers_json = Column("annex_iii_numbers", Text, default="[]")
    conformity_route = Column(Text, default="")
    quiz_page = Column(String, default="1")
    locked = Column(String, default="false")
    _obligation_ids_json = Column("obligation_ids", Text, default="[]")
    _justifications_json = Column("justifications", Text, default="{}")
    created_at = Column(String, default=_now)

    product_version = relationship("ProductVersion", back_populates="assessments")
    answers = relationship(
        "VerificationAnswer", back_populates="assessment", cascade="all, delete-orphan"
    )

    # ── Convenience accessors ──
    @property
    def product(self):
        return self.product_version.product if self.product_version else None

    @property
    def product_name(self) -> str:
        return self.product.name if self.product else ""

    @property
    def description(self) -> str:
        return self.product_version.description if self.product_version else ""

    @property
    def key_features(self):
        return self.product_version.key_features if self.product_version else []

    @property
    def actor_roles(self):
        return (
            self.product_version.actor_roles
            if self.product_version
            else ["manufacturer"]
        )

    # ── JSON-backed fields ──
    @property
    def obligation_ids(self):
        return json.loads(self._obligation_ids_json or "[]")

    @obligation_ids.setter
    def obligation_ids(self, value):
        self._obligation_ids_json = json.dumps(value)

    @property
    def matched_categories(self):
        return json.loads(self._matched_categories_json or "[]")

    @matched_categories.setter
    def matched_categories(self, value):
        self._matched_categories_json = json.dumps(value)

    @property
    def annex_iii_numbers(self):
        return json.loads(self._annex_iii_numbers_json or "[]")

    @annex_iii_numbers.setter
    def annex_iii_numbers(self, value):
        self._annex_iii_numbers_json = json.dumps(value)

    @property
    def justifications(self):
        return json.loads(self._justifications_json or "{}")

    @justifications.setter
    def justifications(self, value):
        self._justifications_json = json.dumps(value)


class VerificationAnswer(Base):
    __tablename__ = "verification_answers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = Column(String, ForeignKey("assessments.id"), index=True)
    verification_id = Column(String, index=True)
    verification_text = Column(Text, default="")
    _associated_obligations_json = Column("associated_obligations", Text, default="[]")
    status = Column(String, default="")
    evidence = Column(Text, default="")
    notes = Column(Text, default="")

    assessment = relationship("Assessment", back_populates="answers")

    @property
    def associated_obligations(self):
        return json.loads(self._associated_obligations_json or "[]")

    @associated_obligations.setter
    def associated_obligations(self, value):
        self._associated_obligations_json = json.dumps(value or [])

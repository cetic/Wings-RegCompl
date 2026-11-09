from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PackageModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtensiblePackageModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class DocumentRef(ExtensiblePackageModel):
    id: str
    versionId: str
    shortName: str


class UnitRef(ExtensiblePackageModel):
    provisionId: str
    citation: str
    ptype: str
    heading: str = ""


class ProvisionOutput(ExtensiblePackageModel):
    id: str
    citation: str
    ptype: str
    parent: str | None
    isNormative: bool
    localId: str = ""
    ordinal: int = 0
    heading: str = ""
    text: str = ""
    summary: str = ""
    textHash: str = ""
    applicability: dict[str, Any] | None = None


class StatementOutput(PackageModel):
    id: str
    type: Literal[
        "Obligation", "Prohibition", "Permission", "Recommendation", "Exemption", "LegalEffect"
    ]
    modality: Literal["shall", "shall_not", "should", "may", "deemed"]
    text: str = Field(min_length=10)
    derivedFrom: list[str] = Field(min_length=1)
    evidence: str = Field(min_length=5)
    topics: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    reviewStatus: Literal["proposed", "validated", "rejected"]
    action: str = ""
    addressees: list[str] = Field(default_factory=list)
    recipients: list[str] = Field(default_factory=list)
    beneficiaries: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    deadline: dict[str, Any] | None = None
    retention: dict[str, Any] | None = None
    artefacts: list[str] = Field(default_factory=list)
    procedures: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)
    applicability: dict[str, Any] | None = None
    appliesFrom: str | None = None
    appliesUntil: str | None = None
    exceptionTo: str | None = None
    reviewerNote: str = ""


class QuestionOption(PackageModel):
    value: str
    label: str
    category: str | None = None


class QuestionOutput(PackageModel):
    id: str
    status: Literal["existing", "proposed"]
    layer: Literal["scope", "role", "classification", "specific"]
    answerType: Literal["boolean", "single_choice", "multi_choice", "number", "date"]
    text: str = Field(min_length=10)
    source: str
    help: str = ""
    options: list[QuestionOption] = Field(default_factory=list)
    unit: str = ""
    askIf: dict[str, Any] | None = None
    reviewStatus: Literal["proposed", "validated", "rejected"] = "proposed"
    reviewerNote: str = ""


class DefinitionOutput(PackageModel):
    id: str
    term: str
    definedIn: str
    termId: str = ""
    alias: str | None = None
    text: str = ""
    byReferenceTo: str | None = None


class ConceptOutput(PackageModel):
    id: str
    label: str
    description: str = ""
    broader: str | None = None


class ExtractionMetadata(PackageModel):
    model: str
    promptVersion: str
    timestamp: str
    attempts: int = 1
    notes: str = ""


class ProvisionPackage(PackageModel):
    packageVersion: Literal["1.0"]
    document: DocumentRef
    unit: UnitRef
    provisions: list[ProvisionOutput] = Field(min_length=1)
    statements: list[StatementOutput]
    questions: list[QuestionOutput]
    extraction: ExtractionMetadata
    definitions: list[DefinitionOutput] = Field(default_factory=list)
    roles: list[ConceptOutput] = Field(default_factory=list)
    events: list[ConceptOutput] = Field(default_factory=list)
    artefacts: list[ConceptOutput] = Field(default_factory=list)
    topicsProposed: list[ConceptOutput] = Field(default_factory=list)
    documentScope: dict[str, Any] | None = None

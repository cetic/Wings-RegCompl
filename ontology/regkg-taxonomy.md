# RegKG ontology v0.2 — taxonomy reference

> Generated from `regkg.ttl` (source of truth) by `generate_taxonomy.py`. Do not edit by hand.

Layers: L1 Document · L2 Normative · L3 Domain · L4 Pivot · L5 Relations · L6 Provenance · L7 Applicability · L8 Assessment (private).

## 1. Class hierarchy

`[Label]` = Neo4j node label in the shared knowledge graph; `(private)` = private store only.

```
rk:AmendmentInstruction — Amendment instruction  [Amendment]
rk:AmendmentOperation —   ⊑ skos:Concept
rk:Answer — Answer  (private)
rk:AnswerOption — Answer option
rk:AnswerType —   ⊑ skos:Concept
rk:ApplicabilityPeriod — Applicability period
rk:ApplicabilityRule — Applicability rule
rk:ArtefactType — Artefact / evidence type  [Artefact]  ⊑ skos:Concept
rk:AssessedObject — Assessed object  (private)
rk:Assessment — Assessment  (private)
rk:Category — Classification category  [Category]  ⊑ skos:Concept
rk:Channel — Channel  [Channel]  ⊑ skos:Concept
rk:ClassificationScheme — Classification scheme  [Scheme]  ⊑ skos:ConceptScheme
rk:Condition — Condition
rk:Coverage —   ⊑ skos:Concept
rk:DateKind —   ⊑ skos:Concept
rk:Deadline — Deadline
rk:Definition — Definition  [Definition]
rk:DocStatus —   ⊑ skos:Concept
rk:DocumentVersion — Document version  [Version]
rk:EventType — Event type  [Event]  ⊑ skos:Concept
rk:Evidence — Evidence  (private)
rk:ExtractionActivity — Extraction activity  ⊑ prov:Activity
rk:HarmonisationListing — Harmonised standard listing (OJ)
rk:Jurisdiction — Jurisdiction  ⊑ skos:Concept
rk:Mapping — Mapping (reified correspondence)  [Mapping]
rk:MappingType —   ⊑ skos:Concept
rk:Modality —   ⊑ skos:Concept
rk:NormativeDocument — Normative document  [Document]
    └─ rk:CertificationScheme — Certification scheme
    └─ rk:CommonSpecification — Common specification
    └─ rk:Guidance — Guidance
    └─ rk:LegalAct — Legal act
        └─ rk:Decision — Decision
        └─ rk:DelegatedAct — Delegated act
        └─ rk:Directive — Directive
        └─ rk:ImplementingAct — Implementing act
        └─ rk:NationalLaw — National law
        └─ rk:Regulation — Regulation
    └─ rk:Standard — Standard
        └─ rk:EuropeanStandard — European standard (EN)
        └─ rk:InternationalStandard — International standard (IEC/ISO)
        └─ rk:TechnicalReport — Technical report (TR)
        └─ rk:TechnicalSpecification — Technical specification (TS)
rk:NormativeStatement — Normative statement  [Statement]
    └─ rk:Exemption — Exemption / derogation
    └─ rk:LegalEffect — Legal effect
    └─ rk:Obligation — Obligation / requirement (shall)
    └─ rk:Permission — Permission (may)
    └─ rk:Prohibition — Prohibition (shall not)
    └─ rk:Recommendation — Recommendation (should)
rk:ObjectDocument — Document describing the object  (private)
rk:Organisation — Organisation  [Organisation]  ⊑ prov:Agent
rk:Procedure — Procedure  [Procedure]  ⊑ skos:Concept
rk:Provision — Provision (structural unit)  [Provision]
rk:ProvisionType —   ⊑ skos:Concept
rk:Question — Applicability question  [Question]
rk:QuestionLayer —   ⊑ skos:Concept
rk:RequirementResult — Requirement result  (private)
rk:RetentionPeriod — Retention period
rk:ReviewStatus —   ⊑ skos:Concept
rk:Role — Role  [Role]  ⊑ skos:Concept
rk:Sanction — Sanction
rk:Series — Document series  [Series]
rk:SourceSpan — Source span
rk:SubjectMatter — Regulated subject matter  [SubjectMatter]  ⊑ skos:Concept
rk:Tenant — Tenant / organisation using the system  (private)
rk:Term — Term  [Term]  ⊑ skos:Concept
rk:Topic — Topic / control objective  [Topic]  ⊑ skos:Concept
rk:User — Local user account  (private)
```

## 2. Controlled vocabularies (SKOS concept schemes)

### Amendment operations (`rk:AmendmentOperationScheme`)

| Concept | Label | Note |
|---|---|---|
| `rk:op_add` | add |  |
| `rk:op_delete` | delete |  |
| `rk:op_insert` | insert |  |
| `rk:op_replace` | replace |  |
| `rk:op_replaceHeading` | replace heading |  |

### Answer types (`rk:AnswerTypeScheme`)

| Concept | Label | Note |
|---|---|---|
| `rk:at_boolean` | boolean |  |
| `rk:at_date` | date |  |
| `rk:at_multiChoice` | multiple choice |  |
| `rk:at_number` | number |  |
| `rk:at_singleChoice` | single choice |  |

### Coverage levels (`rk:CoverageScheme`)

| Concept | Label | Note |
|---|---|---|
| `rk:cov_full` | full |  |
| `rk:cov_none` | none |  |
| `rk:cov_partial` | partial |  |

### Kinds of dates (`rk:DateKindScheme`)

| Concept | Label | Note |
|---|---|---|
| `rk:dk_appliesFrom` | applies from |  |
| `rk:dk_datedTask` | dated task (by <date>) |  |
| `rk:dk_nationalMeasuresApply` | national measures apply from (directive) |  |
| `rk:dk_transpositionDeadline` | transposition deadline (directive) |  |
| `rk:dk_withEffectFrom` | with effect from (repeal / deletion) |  |

### Document status (`rk:DocStatusScheme`)

| Concept | Label | Note |
|---|---|---|
| `rk:ds_draft` | draft |  |
| `rk:ds_published` | published / in force |  |
| `rk:ds_underReview` | under review |  |
| `rk:ds_withdrawn` | withdrawn / repealed |  |

### Mapping types (`rk:MappingTypeScheme`)

| Concept | Label | Note |
|---|---|---|
| `rk:mt_broader` | broader than |  |
| `rk:mt_conflicts` | conflicts with |  |
| `rk:mt_contributesTo` | contributes to (partial) |  |
| `rk:mt_correlates` | legal correlation (repealed -> new) | Asserted by the law itself (correlation table, e.g. NIS2 Annex III). Created with reviewStatus validated and attributed to the correlation table provision. |
| `rk:mt_equivalent` | equivalent |  |
| `rk:mt_narrower` | narrower than |  |
| `rk:mt_presumptionOfConformity` | confers presumption of conformity | Formal legal effect (a harmonised standard published in the Official Journal, or deemed compliance between acts). Distinguish this from mt_satisfies, which is a technical assessment. |
| `rk:mt_related` | related |  |
| `rk:mt_satisfies` | satisfies (source -> target) |  |

### Deontic modalities (`rk:ModalityScheme`)

| Concept | Label | Note |
|---|---|---|
| `rk:mod_deemed` | is deemed |  |
| `rk:mod_may` | may |  |
| `rk:mod_shall` | shall |  |
| `rk:mod_shallNot` | shall not |  |
| `rk:mod_should` | should |  |

### Provision types (`rk:ProvisionTypeScheme`)

| Concept | Label | Note |
|---|---|---|
| `rk:pt_Annex` | Annex |  |
| `rk:pt_AnnexChapter` | Chapter inside an annex | Machinery Regulation Annex III, Part B, chapter 1 |
| `rk:pt_Article` | Article |  |
| `rk:pt_Chapter` | Chapter |  |
| `rk:pt_Clause` | Clause (standard) |  |
| `rk:pt_CodedPoint` | Coded point | IS.I.OR.230 (EASA Part-IS) |
| `rk:pt_CorrelationTable` | Correlation table |  |
| `rk:pt_DashItem` | Dash list item | Unnumbered '—' item; local id dash1, dash2, ... |
| `rk:pt_DefinitionEntry` | Definition entry |  |
| `rk:pt_EntityType` | Entity type cell (table annex) |  |
| `rk:pt_Note` | Note / example |  |
| `rk:pt_Paragraph` | Paragraph |  |
| `rk:pt_Part` | Part / Title |  |
| `rk:pt_Point` | Point |  |
| `rk:pt_Practice` | Practice (group of requirements) |  |
| `rk:pt_Preamble` | Preamble |  |
| `rk:pt_Recital` | Recital |  |
| `rk:pt_Requirement` | Identified requirement (SM-1, CR 1.1) |  |
| `rk:pt_Section` | Section |  |
| `rk:pt_Sector` | Sector row (table annex) |  |
| `rk:pt_Subparagraph` | Unnumbered subparagraph | Text following a completed list inside the same paragraph or point; subsequent lists belong to it. |
| `rk:pt_Subsector` | Subsector row (table annex) |  |
| `rk:pt_Table` | Table / figure |  |

### Question layers (asking order) (`rk:QuestionLayerScheme`)

| Concept | Label | Note |
|---|---|---|
| `rk:ql_scope` | scope | Does the instrument apply at all? (material and territorial scope, exclusions) |
| `rk:ql_role` | role | Which role does the user's organisation play? (manufacturer, importer, provider, deployer, operator...) |
| `rk:ql_classification` | classification | Which category does the object fall into? (product class, risk tier, entity type, size) |
| `rk:ql_specific` | specific | Provision-specific conditions (e.g. processes personal data, has remote data processing). |

### Requirement result status (`rk:ResultStatusScheme`)

| Concept | Label | Note |
|---|---|---|
| `rk:rr_applicable` | applicable |  |
| `rk:rr_notApplicable` | not applicable |  |
| `rk:rr_undetermined` | undetermined (missing answers) |  |

### Review status (`rk:ReviewStatusScheme`)

| Concept | Label | Note |
|---|---|---|
| `rk:rs_proposed` | proposed (not validated) |  |
| `rk:rs_rejected` | rejected |  |
| `rk:rs_validated` | validated by expert |  |

### Kinds of subject matter (`rk:SubjectMatterKindScheme`)

| Concept | Label | Note |
|---|---|---|
| `rk:smk_data` | data |  |
| `rk:smk_organisation` | organisation / entity |  |
| `rk:smk_process` | process |  |
| `rk:smk_product` | product |  |
| `rk:smk_service` | service |  |
| `rk:smk_system` | system |  |

### RegKG topic taxonomy (`rk:TopicScheme`)

*Populated per document (A-Box).*

## 3. Object properties (relationships)

| Property | Domain | Range | Neo4j | Comment |
|---|---|---|---|---|
| `rk:addressee` | rk:NormativeStatement | rk:Role | `ADDRESSED_TO` | The role responsible for the obligation. |
| `rk:addressesTopic` | — | rk:Topic | `ABOUT` | Statement or provision → topic(s) addressed. Foundation for cross-instrument queries. |
| `rk:againstDocument` | rk:Assessment | rk:NormativeDocument |  |  |
| `rk:amends` | — | — | `AMENDS` |  |
| `rk:anchorEvent` | rk:Deadline | rk:EventType | `DEADLINE_ANCHOR` |  |
| `rk:answerType` | rk:Question | rk:AnswerType |  |  |
| `rk:answers` | rk:Answer | rk:Question |  |  |
| `rk:appliesToCategory` | rk:Condition | rk:Category |  |  |
| `rk:assesses` | rk:Assessment | rk:AssessedObject |  |  |
| `rk:basedOn` | — | — | `BASED_ON` | Lineage (e.g. IEC 62443-4-1 ← ISCI SDLA). |
| `rk:beneficiary` | rk:NormativeStatement | rk:Role | `BENEFITS` | Who benefits (e.g. users, consumers). |
| `rk:classifiedAs` | — | rk:Category | `CLASSIFIED_AS` | A regulated subject (or a real instance in a customer's inventory) belongs to a category. |
| `rk:concerns` | rk:NormativeStatement | rk:SubjectMatter | `CONCERNS` |  |
| `rk:correlatesTo` | rk:Provision | rk:Provision | `CORRELATES_TO` | Shortcut materialised from validated rk:mt_correlates mappings: provision of the repealed act -> provision of the new act. Used to resolve references to repeale |
| `rk:coverage` | rk:Mapping | rk:Coverage |  |  |
| `rk:dateKind` | rk:ApplicabilityPeriod | rk:DateKind |  |  |
| `rk:decidedBy` | rk:RequirementResult | rk:Answer |  |  |
| `rk:definedByReferenceTo` | rk:Definition | rk:Definition | `BY_REFERENCE_TO` | Definition by reference to another instrument. Key query: propagate changes from the source instrument. |
| `rk:definedIn` | rk:Definition | rk:Provision | `DEFINED_IN` |  |
| `rk:definedInDocument` | — | rk:NormativeDocument |  | The instrument that introduces this role, term, category, or artefact. |
| `rk:definesTerm` | rk:Definition | rk:Term | `DEFINES` |  |
| `rk:dependsOn` | rk:Question | rk:Question | `DEPENDS_ON` | Materialised from askIf for graph traversal. |
| `rk:derivedFrom` | rk:NormativeStatement | rk:Provision | `DERIVED_FROM` | Source provision for the statement. |
| `rk:docStatus` | rk:DocumentVersion | rk:DocStatus |  |  |
| `rk:documentRelation` | — | — |  | Super-property for factual relationships between documents or provisions. |
| `rk:empowers` | — | — |  |  |
| `rk:exceptionTo` | rk:NormativeStatement | rk:NormativeStatement |  |  |
| `rk:extractedFrom` | — | rk:SourceSpan |  |  |
| `rk:gatedBy` | — | rk:Question | `GATED_BY` | Materialised: every question referenced by the rule of a document, provision or statement. |
| `rk:hasApplicability` | — | rk:ApplicabilityPeriod |  | Already defined in v0.1 for ApplicabilityPeriod (dates); see rk:hasApplicabilityRule for conditions. |
| `rk:hasApplicabilityRule` | — | rk:ApplicabilityRule |  | Attached to a NormativeDocument (scope rule), a Provision (inherited by descendants) or a NormativeStatement. |
| `rk:hasCondition` | rk:NormativeStatement | rk:Condition |  |  |
| `rk:hasDeadline` | rk:NormativeStatement | rk:Deadline |  |  |
| `rk:hasOption` | rk:Question | rk:AnswerOption |  |  |
| `rk:hasPart` | — | — |  |  |
| `rk:hasRetention` | rk:NormativeStatement | rk:RetentionPeriod |  |  |
| `rk:hasVersion` | rk:NormativeDocument | rk:DocumentVersion | `HAS_VERSION` |  |
| `rk:inClassificationScheme` | rk:Category | rk:ClassificationScheme | `IN_SCHEME` |  |
| `rk:inSeries` | rk:NormativeDocument | rk:Series | `IN_SERIES` |  |
| `rk:inVersion` | rk:Provision | rk:DocumentVersion | `IN_VERSION` | The version to which the provision belongs. |
| `rk:informativelyReferences` | — | — |  |  |
| `rk:instructionIn` | rk:AmendmentInstruction | rk:Provision | `INSTRUCTION_IN` |  |
| `rk:interprets` | rk:Provision | rk:Provision | `INTERPRETS` | Recital → article it explains; guidance → provision it explains. |
| `rk:issuedBy` | rk:NormativeDocument | rk:Organisation | `ISSUED_BY` |  |
| `rk:jurisdiction` | — | rk:Jurisdiction |  |  |
| `rk:layer` | rk:Question | rk:QuestionLayer |  |  |
| `rk:lexSpecialisFor` | — | — |  |  |
| `rk:listedStandard` | rk:HarmonisationListing | rk:DocumentVersion |  |  |
| `rk:mappingSource` | rk:Mapping | — | `MAPS_FROM` |  |
| `rk:mappingTarget` | rk:Mapping | — | `MAPS_TO` |  |
| `rk:mappingType` | rk:Mapping | rk:MappingType |  |  |
| `rk:mergedInto` | rk:Question | rk:Question | `MERGED_INTO` | Duplicate question merged during review; keep for traceability. |
| `rk:modality` | rk:NormativeStatement | rk:Modality |  |  |
| `rk:normativelyReferences` | — | — |  | A reference essential to application (e.g. Clause 2 of a standard). |
| `rk:operation` | rk:AmendmentInstruction | rk:AmendmentOperation |  |  |
| `rk:optionCategory` | rk:AnswerOption | rk:Category | `OPTION_CATEGORY` |  |
| `rk:partOf` | rk:Provision | rk:Provision | `PART_OF` |  |
| `rk:playsRole` | rk:Organisation | rk:Role |  |  |
| `rk:provisionType` | rk:Provision | rk:ProvisionType |  |  |
| `rk:questionSource` | rk:Question | rk:Provision | `SOURCE` | Provision the question is derived from (scope article, definition, annex list). |
| `rk:recipient` | rk:NormativeStatement | — | `RECIPIENT` | Who the action is addressed to (e.g. coordinating CSIRT, ENISA). A role or organization. |
| `rk:references` | — | — | `REFERENCES` |  |
| `rk:repeals` | — | — | `REPEALS` |  |
| `rk:requiresArtefact` | rk:NormativeStatement | rk:ArtefactType | `REQUIRES_ARTEFACT` |  |
| `rk:requiresProcedure` | rk:NormativeStatement | rk:Procedure | `REQUIRES_PROCEDURE` |  |
| `rk:resultFor` | rk:RequirementResult | rk:NormativeStatement |  |  |
| `rk:resultStatus` | rk:RequirementResult | skos:Concept |  |  |
| `rk:retentionAnchor` | rk:RetentionPeriod | rk:EventType |  | Event from which the minimum period runs (e.g. contract terminated, person left). |
| `rk:reviewStatus` | — | rk:ReviewStatus |  |  |
| `rk:sanctionedBy` | rk:NormativeStatement | rk:Sanction |  |  |
| `rk:subjectKind` | rk:SubjectMatter | skos:Concept |  |  |
| `rk:supersededBy` | rk:ApplicabilityPeriod | rk:ApplicabilityPeriod |  | An amending act replaced this date (e.g. AI Act high-risk dates postponed by Regulation (EU) 2026/1744). |
| `rk:supersedes` | — | — | `SUPERSEDES` |  |
| `rk:supersedesVersion` | rk:DocumentVersion | rk:DocumentVersion |  |  |
| `rk:supportedBy` | rk:Answer | rk:Evidence |  |  |
| `rk:targetDocument` | rk:AmendmentInstruction | rk:NormativeDocument | `TARGETS` |  |
| `rk:termOf` | — | rk:Term |  | Links a domain concept (role, subject matter, artefact) to the term that formally defines it. |
| `rk:transposes` | rk:NationalLaw | rk:Directive | `TRANSPOSES` |  |
| `rk:triggerEvent` | rk:Condition | rk:EventType |  |  |
| `rk:triggeredBy` | rk:NormativeStatement | rk:EventType | `TRIGGERED_BY` | OPERATIONAL trigger: the obligation fires when the event occurs. Never turned into a question (see L7). |
| `rk:underAct` | rk:HarmonisationListing | rk:LegalAct |  |  |
| `rk:versionOf` | — | — |  |  |
| `rk:viaChannel` | rk:NormativeStatement | rk:Channel | `VIA_CHANNEL` |  |
| `rk:viaTopic` | rk:Mapping | rk:Topic | `VIA_TOPIC` |  |
| `rk:withoutPrejudiceTo` | — | — |  |  |

## 4. Datatype properties (node properties)

| Property | Domain | Range | Neo4j | Comment |
|---|---|---|---|---|
| `rk:action` | rk:NormativeStatement | xsd:string |  | Normalized action verb (e.g. “notify”, “draw up”, “affix”, “test”). |
| `rk:alias` | rk:Term | — |  | Alternative label from the definition itself ("'domain name system' or 'DNS' means"). |
| `rk:answerSource` | rk:Answer | xsd:string |  | inferred / user |
| `rk:answerValue` | rk:Answer | xsd:string |  | JSON-encoded value. |
| `rk:appliesFrom` | rk:ApplicabilityPeriod | xsd:date |  |  |
| `rk:appliesUntil` | rk:ApplicabilityPeriod | xsd:date |  |  |
| `rk:asOfDate` | rk:Assessment | xsd:date |  |  |
| `rk:askIf` | rk:Question | xsd:string |  | JSON condition: ask this question only if it evaluates TRUE (e.g. product class only if in scope). |
| `rk:charEnd` | rk:SourceSpan | xsd:integer |  |  |
| `rk:charStart` | rk:SourceSpan | xsd:integer |  |  |
| `rk:citation` | rk:Provision | — |  | Canonical human-readable reference (“CRA Art. 14(2)(a)”). |
| `rk:conditionText` | rk:Condition | xsd:string |  |  |
| `rk:confidence` | — | xsd:decimal |  | 0.0–1.0; produced by the extractor or mapping author. |
| `rk:definitionText` | rk:Definition | xsd:string |  |  |
| `rk:duration` | rk:Deadline | xsd:duration |  |  |
| `rk:edition` | rk:DocumentVersion | xsd:string |  |  |
| `rk:eliUri` | — | xsd:anyURI |  |  |
| `rk:entryIntoForce` | — | xsd:date |  |  |
| `rk:expression` | rk:ApplicabilityRule | xsd:string |  | JSON condition tree: {all:[..]}, {any:[..]}, {not:..}, leaf {q, op, value}. |
| `rk:fileHash` | rk:SourceSpan | xsd:string |  |  |
| `rk:gap` | rk:Mapping | xsd:string |  | What the source does NOT cover in the target (essential for gap analysis). |
| `rk:heading` | rk:Provision | xsd:string |  |  |
| `rk:helpText` | rk:Question | xsd:string |  | Plain-language explanation, may define legal terms used in the question. |
| `rk:identifier` | — | xsd:string |  | E.g. “(EU) 2024/2847”, “IEC 62443-4-1:2018”. |
| `rk:insertedText` | rk:AmendmentInstruction | xsd:string |  |  |
| `rk:isBinding` | rk:NormativeDocument | xsd:boolean |  | Binding in its own right (regulation: yes; voluntary standard: no). |
| `rk:isNormative` | rk:Provision | xsd:boolean |  | False for recitals, notes, informative annexes, and “rationale and supplemental guidance”. |
| `rk:kbVersion` | rk:Assessment | xsd:string |  | Identifier of the KB snapshot used, so results stay reproducible after the KB changes. |
| `rk:listingDate` | rk:HarmonisationListing | xsd:date |  |  |
| `rk:localId` | rk:Provision | — |  | Local numbering (“14”, “2”, “a”, “SM-1”, “5.2”). |
| `rk:maxFineAmountEUR` | rk:Sanction | xsd:decimal |  |  |
| `rk:maxFinePercentTurnover` | rk:Sanction | xsd:decimal |  |  |
| `rk:method` | rk:ExtractionActivity | xsd:string |  | Examples: “parser:eurlex-xml”, “llm:<model>”, “human”. |
| `rk:minDuration` | rk:RetentionPeriod | xsd:duration |  |  |
| `rk:ojReference` | rk:HarmonisationListing | xsd:string |  |  |
| `rk:optionValue` | rk:AnswerOption | xsd:string |  |  |
| `rk:ordinal` | rk:Provision | xsd:integer |  |  |
| `rk:page` | rk:SourceSpan | xsd:integer |  |  |
| `rk:publicationDate` | — | xsd:date |  |  |
| `rk:qualifier` | rk:Deadline | xsd:string |  | Qualifying phrases such as “without undue delay and in any event within” or “no later than”... |
| `rk:questionText` | rk:Question | xsd:string |  |  |
| `rk:rank` | rk:Category | xsd:integer |  | Ordering for ordinal scales (SL1 < SL2, Class I < Class II). |
| `rk:rationale` | rk:Mapping | xsd:string |  |  |
| `rk:restrictions` | rk:HarmonisationListing | xsd:string |  |  |
| `rk:shortName` | — | xsd:string |  |  |
| `rk:sourceFile` | rk:SourceSpan | xsd:string |  |  |
| `rk:sourceFormat` | rk:DocumentVersion | xsd:string |  | 'html' (EUR-Lex TXT/HTML, preferred), 'fmx' (Formex XML), 'pdf' (fallback). |
| `rk:sourceHash` | rk:DocumentVersion | xsd:string |  | SHA-256 of the uploaded source file. |
| `rk:statement` | rk:NormativeStatement | xsd:string |  | Atomic restatement of the rule. |
| `rk:summary` | — | xsd:string |  |  |
| `rk:targetReference` | rk:AmendmentInstruction | xsd:string |  | Target inside the amended act, e.g. 'Article 19', 'ARA.GEN.135A', 'Annex I'. |
| `rk:text` | rk:Provision | xsd:string |  | Full text. OPTIONAL: for copyrighted standards (IEC, ISO), store it only when the license permits; otherwise use rk:summary + rk:textHash. |
| `rk:textHash` | rk:Provision | xsd:string |  | Text fingerprint (SHA-256): detects changes between versions without storing the text. |
| `rk:unit` | rk:Question | xsd:string |  | Unit for number questions (persons, EUR, ...). |

## 5. Relationships from reused vocabularies

| Property | Neo4j |
|---|---|
| `skos:broader` | `BROADER` |
| `skos:closeMatch` | `CLOSE_MATCH` |
| `skos:exactMatch` | `EXACT_MATCH` |

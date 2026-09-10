# EU Multi-Regulation Compliance Ontology

A regulation-agnostic ontology for describing **any EU legislative act** and its
compliance obligations. It is modelled in the style of the official
[EUR-Lex / ELI Metadata Ontology](http://data.europa.eu/eli/ontology) but shaped
to mirror the **Neo4j property graph** this project generates.

- **File:** [eu_legal_graph_ontology.owl](eu_legal_graph_ontology.owl)
- **Serialization:** RDF/XML
- **Base namespace:** `http://example.org/eu-reg#` (prefix `eureg`)
- **Backbone:** ELI 1.5 (`owl:imports http://data.europa.eu/eli/ontology#`, prefix `eli`)
- **Illustrated with:** CRA (Reg. (EU) 2024/2847), GDPR (Reg. (EU) 2016/679), Part-IS (Comm. Impl. Reg. (EU) 2023/203)

---

## 1. Why this ontology exists

The earlier ontology ([CRA_ontology.owl](CRA_ontology.owl)) modelled **only the
Cyber Resilience Act**. The goal here is a **single core that fits all EU
regulations** — so the CRA, GDPR, Part-IS, and any future act share the same
abstract concepts and only differ in their leaf classes.

Two constraints drove the design:

1. **Look like the official EUR-Lex file** — reuse ELI for the document layer
   and the same documentation idioms (`skos:definition`, `skos:editorialNote`,
   `vann:preferredNamespacePrefix`, `dct:*`, `owl:versionInfo`).
2. **Match what the project's graph already does** — every node label,
   sub-label, relationship type, and property in the Neo4j graph has a direct
   counterpart in the ontology.

---

## 2. How it mirrors the property graph

The ingestion pipeline ([ingest_neo4j.py](../ingest_neo4j.py)) reads JSON of the
shape produced for each article (see [response.json](../response.json)):

```jsonc
{
  "id": "n_manufacturer",
  "label": "Actor",                 // category
  "sub_label": "Manufacturer",      // specific type
  "name": "Manufacturer",
  "properties": { "cra_definition_id": "Art. 3(13)", "description": "..." }
}
```

plus typed `relationships`, and three special node families: `Obligation`,
`ComplianceAction`, and `ArticleRef` (cross references).

The ontology encodes that meta-model **one-to-one**:

| Graph construct | Ontology counterpart | Binding annotation |
|---|---|---|
| node `label` (e.g. `Actor`) | `owl:Class` (category) | `eureg:graphLabel` |
| node `sub_label` (e.g. `Manufacturer`) | `owl:Class` `rdfs:subClassOf` the label class | `eureg:graphSubLabel` |
| relationship `type` (e.g. `MANUFACTURES`) | `owl:ObjectProperty` | `eureg:graphRelType` |
| node `properties` key (e.g. `article_ref`) | `owl:DatatypeProperty` | — |
| `:Obligation` node | `eureg:Obligation` class | `eureg:graphLabel` |
| `:ComplianceAction` node | `eureg:ComplianceAction` class | `eureg:graphLabel` |
| `:ArticleRef` node | `eureg:ArticleRef` class | `eureg:graphLabel` |

This means you can read the ontology to know exactly which labels, relationship
types, and property keys are valid in the graph — and vice-versa.

---

## 3. Layered structure

### Layer 1 — Document structure (ELI-aligned)

The act itself and its subdivisions reuse the official ELI classes.

- `eureg:LegalAct ⊑ eli:LegalResource`
  - `eureg:Regulation`, `eureg:Directive`, `eureg:ImplementingAct`, `eureg:DelegatedAct`
- Subdivisions `⊑ eli:LegalResourceSubdivision`: `Article`, `Annex`, `Recital`,
  `Chapter`, `Point`, and `ArticleRef` (the graph's cross-reference target node).
- `eureg:hasProvision ⊑ eli:has_part` links an act to its subdivisions.

### Layer 2 — Graph node categories (the `label` taxonomy)

Regulation-**neutral** category classes — the backbone shared by every act:

| Category class | Generalises graph label | Examples of sub-labels |
|---|---|---|
| `Actor` | `Actor` | Manufacturer, Controller, Organisation |
| `RegulatedEntity` ⊑ Actor | — | duty-bearers |
| `NaturalPerson` ⊑ Actor | — | Data Subject, User |
| `Authority` ⊑ Actor | — | Supervisory/Competent Authority, Notified Body, Union Body |
| `RegulatedProduct` | `ProductWithDigitalElements` | Default/Important/Critical product |
| `ProductComponent` | `ProductComponent` | Software, FOSS, Hardware |
| `MarketActivity` | `MarketActivity` | Placing on the market, Processing |
| `UseContext` | `UseContext` | Intended purpose, Foreseeable use |
| `TechnicalConcept` | `TechnicalConcept` | SBOM, Endpoint |
| `SecurityConcept` | `CybersecurityConcept` | Risk, Threat, Vulnerability, Incident, Measure |
| `ComplianceArtifact` | `ComplianceArtifact` | Tech doc, Declaration, DPIA, Certificate |
| `LegalProvision` | `LegalProvision` | Requirement, Right, Penalty, Support period |
| `LegalFramework` | `LegalFramework` | Personal data, CVD |
| `Enterprise` | `Enterprise` | Micro / Small / Medium |

### Layer 3 — Graph meta-model entities

The nodes the ingestion script **materialises** rather than reads:

- `eureg:Obligation ⊑ eureg:LegalProvision` — carries `paragraphRef`, `action`,
  `trigger`, `deadline`; subclasses `ReportingObligation`,
  `InformationObligation`, `RecordKeepingObligation`.
- `eureg:ComplianceAction` — short executable step (`text`, `category`,
  `priority`), linked from an obligation via `HAS_ACTION`.

### Layer 4 — Object properties (relationship `type` vocabulary)

Each relationship type in the graph is an object property carrying its exact
Neo4j token in `eureg:graphRelType`. Highlights:

- Structural: `hasProvision` (⊑ `eli:has_part`)
- Meta-model: `hasObligation` (`HAS_OBLIGATION`), `relatesTo` (`RELATES_TO`), `hasAction` (`HAS_ACTION`)
- Cross-reference: `references` (⊑ `eli:refers_to`), `specifiedBy` (`SPECIFIED_BY`), `specifiesProcessFor` (`SPECIFIES_PROCESS_FOR`)
- Domain: `manufactures`, `placesOnMarket`, `hasComponent`, `hasVulnerability`,
  `addressedBy`, `mustComplyWith`, `presumesConformityVia`, `hasSupportPeriod`,
  `reportsTo`, `supervisedBy`, `establishes`, `mitigates`
- Cross-regulation: `deemsCompliantWith`, `relatedProvision` (symmetric)

### Layer 5 — Datatype properties (node `properties` keys)

`name`, `description`, `definitionRef` (generalises `cra_definition_id`),
`articleRef`, `legalBasis`, `paragraphRef`, `action`, `trigger`, `deadline`,
`priority`, `category`, `retentionPeriod`, `minimumDuration`, `celexNumber`.

---

## 4. Annotation properties (the glue)

| Property | Purpose |
|---|---|
| `eureg:legalSource` | Citation grounding a term (generalises `cra_definition_id` / `article_ref` / `legal_basis`). |
| `eureg:regulationCode` | Originating act: `CRA`, `GDPR`, `Part-IS`, … (core terms omit it). |
| `eureg:graphLabel` | The Neo4j node `label` a class corresponds to. |
| `eureg:graphSubLabel` | The Neo4j node `sub_label` a class corresponds to. |
| `eureg:graphRelType` | The Neo4j relationship `type` an object property corresponds to. |

---

## 5. Regulation modules

The leaf classes are grouped by act, each tagged with `regulationCode`,
`legalSource`, and `graphSubLabel`.

- **CRA** — `cra_Manufacturer`, `cra_ProductWithDigitalElements`,
  `cra_VulnerabilityHandlingRequirement`, `cra_CEMarking`,
  `cra_SoftwareBillOfMaterials`, `cra_Penalty`, …
- **GDPR** — `gdpr_Controller`, `gdpr_Processor`, `gdpr_DataSubject`,
  `gdpr_PersonalData`, `gdpr_LawfulBasis`, `gdpr_DataSubjectRight`,
  `gdpr_PersonalDataBreach`, `gdpr_DPIA`, `gdpr_AdministrativeFine`, …
- **Part-IS** — `pis_Organisation`, `pis_ISMS`,
  `pis_InformationSecurityRisk`, `pis_InformationSecurityIncident`,
  `pis_ExternalReportingScheme`, `pis_RecordKeeping`, …

The three acts also appear as individuals: `act_CRA`, `act_GDPR`, `act_PartIS`.

---

## 6. Cross-regulation alignment

Because every act shares the same core, equivalent obligations across acts can be
linked explicitly:

- `eureg:relatedProvision` (symmetric) — thematic link between provisions.
- `eureg:deemsCompliantWith` — fulfilling one provision is deemed to satisfy
  another (presumption of conformity / equivalence).

The file ships a worked example linking CRA Annex I essential cybersecurity
requirements ↔ **GDPR Art. 32** (security of processing) ↔ **Part-IS IS.I.OR.200**
(establish an ISMS).

---

## 7. Worked example (graph ↔ ontology)

The CRA Art. 13 manufacturer fragment from [response.json](../response.json) is
included as individuals to show the round-trip:

```
n_manufacturer  (cra_Manufacturer)
   ── manufactures ──▶ n_product_digital_elements (cra_ProductWithDigitalElements)
   ── hasObligation ─▶ obl_1 (Obligation, paragraphRef "Art. 13(1)")

n_product_digital_elements
   ── mustComplyWith ─▶ n_essential_req_part_i (cra_ProductPropertyRequirement)
                              ── specifiedBy ──▶ ref_AnnexI_PartI (ArticleRef)
```

This is the exact node/relationship shape the ingestion script writes to Neo4j.

---

## 8. How to onboard a new regulation

No change to the core is needed:

1. Add `sub_label` subclasses under the relevant category class
   (e.g. a new `Authority` or `Requirement`).
2. Annotate each with `eureg:regulationCode`, `eureg:legalSource`, and
   `eureg:graphSubLabel`.
3. Add one `owl:NamedIndividual` of type `eureg:Regulation` (or `Directive` /
   `ImplementingAct`) for the act itself, with its `celexNumber`.
4. Reuse the existing object/datatype properties — only add a new relationship
   property if the regulation introduces a genuinely new edge type (and tag it
   with `eureg:graphRelType`).

---

## 9. Validation

```bash
# XML well-formedness (already confirmed)
python3 -c "import xml.dom.minidom as m; m.parse('outputs/eu_legal_graph_ontology.owl'); print('OK')"

# Optional: full RDF/OWL parse + entity counts (requires rdflib)
pip install rdflib
python3 -c "import rdflib; g=rdflib.Graph(); g.parse('outputs/eu_legal_graph_ontology.owl'); print(len(g), 'triples')"
```

---

## 10. Namespaces

| Prefix | URI |
|---|---|
| `eureg` | `http://example.org/eu-reg#` |
| `eli` | `http://data.europa.eu/eli/ontology#` |
| `owl` | `http://www.w3.org/2002/07/owl#` |
| `rdfs` | `http://www.w3.org/2000/01/rdf-schema#` |
| `skos` | `http://www.w3.org/2004/02/skos/core#` |
| `dct` | `http://purl.org/dc/terms/` |
| `vann` | `http://purl.org/vocab/vann/` |
| `xsd` | `http://www.w3.org/2001/XMLSchema#` |

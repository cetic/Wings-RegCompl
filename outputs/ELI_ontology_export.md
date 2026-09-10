# ELI Ontology — WebVOWL Export

Ontology IRI: http://data.europa.eu/eli/ontology#
Title: ELI Metadata Ontology

## Classes

| # | Type | Local Name | IRI |
|---|------|------------|-----|
| 1 | owl:Class | AdministrativeArea | http://data.europa.eu/eli/ontology#AdministrativeArea |
| 2 | owl:Class | Agent | http://data.europa.eu/eli/ontology#Agent |
| 3 | owl:Class | Complex Work | http://data.europa.eu/eli/ontology#ComplexWork |
| 4 | owl:Class | Expression | http://data.europa.eu/eli/ontology#Expression |
| 5 | owl:Class | Format | http://data.europa.eu/eli/ontology#Format |
| 6 | owl:Class | FormatType | http://data.europa.eu/eli/ontology#FormatType |
| 7 | owl:Class | InForce | http://data.europa.eu/eli/ontology#InForce |
| 8 | owl:Class | Language | http://data.europa.eu/eli/ontology#Language |
| 9 | owl:Class | LegalExpression | http://data.europa.eu/eli/ontology#LegalExpression |
| 10 | owl:Class | LegalResource | http://data.europa.eu/eli/ontology#LegalResource |
| 11 | owl:Class | LegalResourceSubdivision | http://data.europa.eu/eli/ontology#LegalResourceSubdivision |
| 12 | owl:Class | LegalValue | http://data.europa.eu/eli/ontology#LegalValue |
| 13 | owl:Class | Manifestation | http://data.europa.eu/eli/ontology#Manifestation |
| 14 | owl:Class | Organization | http://data.europa.eu/eli/ontology#Organization |
| 15 | owl:Class | Person | http://data.europa.eu/eli/ontology#Person |
| 16 | owl:Class | ResourceType | http://data.europa.eu/eli/ontology#ResourceType |
| 17 | owl:Class | SubdivisionType | http://data.europa.eu/eli/ontology#SubdivisionType |
| 18 | owl:Class | Version | http://data.europa.eu/eli/ontology#Version |
| 19 | owl:Class | Work | http://data.europa.eu/eli/ontology#Work |
| 20 | owl:Class | WorkSubdivision | http://data.europa.eu/eli/ontology#WorkSubdivision |
| 21 | owl:Class | WorkType | http://data.europa.eu/eli/ontology#WorkType |
| 22 | owl:Class | F10_Person | http://iflastandards.info/ns/fr/frbr/frbroo/F10_Person |
| 23 | owl:Class | F11_Corporate_Body | http://iflastandards.info/ns/fr/frbr/frbroo/F11_Corporate_Body |
| 24 | owl:Class | F1_Work | http://iflastandards.info/ns/fr/frbr/frbroo/F1_Work |
| 25 | owl:Class | F22_Self-Contained_Expression | http://iflastandards.info/ns/fr/frbr/frbroo/F22_Self-Contained_Expression |
| 26 | owl:Class | F3_Manifestation_Product_Type | http://iflastandards.info/ns/fr/frbr/frbroo/F3_Manifestation_Product_Type |
| 27 | owl:Class | E39_Actor | http://www.cidoc-crm.org/cidoc-crm/E39_Actor |

Total named classes: 27

## Object Properties

| # | Local Name | Domain | Range | IRI |
|---|------------|--------|-------|-----|
| 1 | amended_by | Thing | Thing | http://data.europa.eu/eli/ontology#amended_by |
| 2 | amends | Thing | Thing | http://data.europa.eu/eli/ontology#amends |
| 3 | applied_by | LegalResource | Thing | http://data.europa.eu/eli/ontology#applied_by |
| 4 | applies | Thing | LegalResource | http://data.europa.eu/eli/ontology#applies |
| 5 | based_on | Work | Thing | http://data.europa.eu/eli/ontology#based_on |
| 6 | basis_for | Thing | Work | http://data.europa.eu/eli/ontology#basis_for |
| 7 | changed_by | Thing | Thing | http://data.europa.eu/eli/ontology#changed_by |
| 8 | changes | Thing | Thing | http://data.europa.eu/eli/ontology#changes |
| 9 | cited_by | ? | Thing | http://data.europa.eu/eli/ontology#cited_by |
| 10 | cited_by_case_law | Thing | ? | http://data.europa.eu/eli/ontology#cited_by_case_law |
| 11 | cites | Thing | ? | http://data.europa.eu/eli/ontology#cites |
| 12 | commenced_by | Thing | Thing | http://data.europa.eu/eli/ontology#commenced_by |
| 13 | commences | Thing | Thing | http://data.europa.eu/eli/ontology#commences |
| 14 | consolidated_by | Thing | Thing | http://data.europa.eu/eli/ontology#consolidated_by |
| 15 | consolidates | Thing | Thing | http://data.europa.eu/eli/ontology#consolidates |
| 16 | corrected_by | Thing | Thing | http://data.europa.eu/eli/ontology#corrected_by |
| 17 | corrects | Thing | Thing | http://data.europa.eu/eli/ontology#corrects |
| 18 | countersigned_by | LegalResource | Agent | http://data.europa.eu/eli/ontology#countersigned_by |
| 19 | embodies | Manifestation | Expression | http://data.europa.eu/eli/ontology#embodies |
| 20 | ensures_implementation_of | Thing | LegalResource | http://data.europa.eu/eli/ontology#ensures_implementation_of |
| 21 | format | Manifestation | FormatType | http://data.europa.eu/eli/ontology#format |
| 22 | has_annex | Thing | Thing | http://data.europa.eu/eli/ontology#has_annex |
| 23 | has_another_publication | LegalResource | LegalResource | http://data.europa.eu/eli/ontology#has_another_publication |
| 24 | has_derivative | Thing | Thing | http://data.europa.eu/eli/ontology#has_derivative |
| 25 | has_member | Work | Work | http://data.europa.eu/eli/ontology#has_member |
| 26 | has_part | Work | Work | http://data.europa.eu/eli/ontology#has_part |
| 27 | has_translation | LegalExpression | LegalExpression | http://data.europa.eu/eli/ontology#has_translation |
| 28 | implementation_ensured_by | LegalResource | Thing | http://data.europa.eu/eli/ontology#implementation_ensured_by |
| 29 | implemented_by | Thing | Thing | http://data.europa.eu/eli/ontology#implemented_by |
| 30 | implements | Thing | Thing | http://data.europa.eu/eli/ontology#implements |
| 31 | in_force | Thing | InForce | http://data.europa.eu/eli/ontology#in_force |
| 32 | is_about | Work | ? | http://data.europa.eu/eli/ontology#is_about |
| 33 | is_annex_of | Thing | Thing | http://data.europa.eu/eli/ontology#is_annex_of |
| 34 | is_another_publication_of | LegalResource | LegalResource | http://data.europa.eu/eli/ontology#is_another_publication_of |
| 35 | is_derivative_of | Thing | Thing | http://data.europa.eu/eli/ontology#is_derivative_of |
| 36 | is_embodied_by | Expression | Manifestation | http://data.europa.eu/eli/ontology#is_embodied_by |
| 37 | is_exemplified_by | Manifestation | Thing | http://data.europa.eu/eli/ontology#is_exemplified_by |
| 38 | is_member_of | Work | Work | http://data.europa.eu/eli/ontology#is_member_of |
| 39 | is_part_of | Work | Work | http://data.europa.eu/eli/ontology#is_part_of |
| 40 | is_realized_by | Work | Expression | http://data.europa.eu/eli/ontology#is_realized_by |
| 41 | is_referred_to_by | ? | Thing | http://data.europa.eu/eli/ontology#is_referred_to_by |
| 42 | is_translation_of | LegalExpression | LegalExpression | http://data.europa.eu/eli/ontology#is_translation_of |
| 43 | jurisdiction | Thing | AdministrativeArea | http://data.europa.eu/eli/ontology#jurisdiction |
| 44 | language | Expression | Language | http://data.europa.eu/eli/ontology#language |
| 45 | legal_value | Format | LegalValue | http://data.europa.eu/eli/ontology#legal_value |
| 46 | licence | Format | ? | http://data.europa.eu/eli/ontology#licence |
| 47 | media_type | Manifestation | ? | http://data.europa.eu/eli/ontology#media_type |
| 48 | passed_by | LegalResource | Agent | http://data.europa.eu/eli/ontology#passed_by |
| 49 | published_in_format | Format | Format | http://data.europa.eu/eli/ontology#published_in_format |
| 50 | publisher_agent | Thing | Agent | http://data.europa.eu/eli/ontology#publisher_agent |
| 51 | publishes | Format | Format | http://data.europa.eu/eli/ontology#publishes |
| 52 | realizes | Expression | Work | http://data.europa.eu/eli/ontology#realizes |
| 53 | refers_to | Thing | ? | http://data.europa.eu/eli/ontology#refers_to |
| 54 | related_to | Thing | ? | http://data.europa.eu/eli/ontology#related_to |
| 55 | relevant_for | Thing | AdministrativeArea | http://data.europa.eu/eli/ontology#relevant_for |
| 56 | repealed_by | Thing | Thing | http://data.europa.eu/eli/ontology#repealed_by |
| 57 | repeals | Thing | Thing | http://data.europa.eu/eli/ontology#repeals |
| 58 | responsibility_of_agent | LegalResource | Agent | http://data.europa.eu/eli/ontology#responsibility_of_agent |
| 59 | rightsholder_agent | Format | Agent | http://data.europa.eu/eli/ontology#rightsholder_agent |
| 60 | transposed_by | LegalResource | Thing | http://data.europa.eu/eli/ontology#transposed_by |
| 61 | transposes | Thing | LegalResource | http://data.europa.eu/eli/ontology#transposes |
| 62 | type_document | LegalResource | ResourceType | http://data.europa.eu/eli/ontology#type_document |
| 63 | type_subdivision | WorkSubdivision | SubdivisionType | http://data.europa.eu/eli/ontology#type_subdivision |
| 64 | uri_schema | Thing | ? | http://data.europa.eu/eli/ontology#uri_schema |
| 65 | version | Thing | Version | http://data.europa.eu/eli/ontology#version |
| 66 | work_type | Work | WorkType | http://data.europa.eu/eli/ontology#work_type |
| 67 | R10_has_member | Thing | Thing | http://iflastandards.info/ns/fr/frbr/frbroo/R10_has_member |
| 68 | R10i_is_member_of | Thing | Thing | http://iflastandards.info/ns/fr/frbr/frbroo/R10i_is_member_of |
| 69 | R3_is_realised_in | Thing | Thing | http://iflastandards.info/ns/fr/frbr/frbroo/R3_is_realised_in |
| 70 | R3i_realises | Thing | Thing | http://iflastandards.info/ns/fr/frbr/frbroo/R3i_realises |
| 71 | R4_carriers_provided_by | Thing | Thing | http://iflastandards.info/ns/fr/frbr/frbroo/R4_carriers_provided_by |
| 72 | R4i_comprises_carriers_of | Thing | Thing | http://iflastandards.info/ns/fr/frbr/frbroo/R4i_comprises_carriers_of |
| 73 | R7i_has_example | Thing | Thing | http://iflastandards.info/ns/fr/frbr/frbroo/R7i_has_example |

Total object properties: 73

## Datatype Properties

| # | Local Name | Domain | Range (Datatype) | IRI |
|---|------------|--------|-------------------|-----|
| 1 | cited_by_case_law_reference | Thing | Literal | http://data.europa.eu/eli/ontology#cited_by_case_law_reference |
| 2 | date_applicability | Thing | date | http://data.europa.eu/eli/ontology#date_applicability |
| 3 | date_document | Work | date | http://data.europa.eu/eli/ontology#date_document |
| 4 | date_no_longer_in_force | Thing | date | http://data.europa.eu/eli/ontology#date_no_longer_in_force |
| 5 | date_publication | Thing | date | http://data.europa.eu/eli/ontology#date_publication |
| 6 | description | Thing | Literal | http://data.europa.eu/eli/ontology#description |
| 7 | first_date_entry_in_force | Thing | date | http://data.europa.eu/eli/ontology#first_date_entry_in_force |
| 8 | id_local | Thing | Literal | http://data.europa.eu/eli/ontology#id_local |
| 9 | number | Thing | string | http://data.europa.eu/eli/ontology#number |
| 10 | published_in | Format | Literal | http://data.europa.eu/eli/ontology#published_in |
| 11 | publisher | Thing | Literal | http://data.europa.eu/eli/ontology#publisher |
| 12 | responsibility_of | LegalResource | string | http://data.europa.eu/eli/ontology#responsibility_of |
| 13 | rights | Format | Literal | http://data.europa.eu/eli/ontology#rights |
| 14 | rightsholder | Format | Literal | http://data.europa.eu/eli/ontology#rightsholder |
| 15 | title | Expression | Literal | http://data.europa.eu/eli/ontology#title |
| 16 | title_alternative | Expression | Literal | http://data.europa.eu/eli/ontology#title_alternative |
| 17 | title_short | Expression | Literal | http://data.europa.eu/eli/ontology#title_short |
| 18 | version_date | Thing | date | http://data.europa.eu/eli/ontology#version_date |

Total datatype properties: 18

## SubClassOf Relationships

| # | Subclass | Superclass |
|---|----------|------------|
| 1 | AdministrativeArea | ? |
| 2 | FormatType | ? |
| 3 | InForce | ? |
| 4 | Language | ? |
| 5 | LegalValue | ? |
| 6 | ResourceType | ? |
| 7 | SubdivisionType | ? |
| 8 | Version | ? |
| 9 | WorkType | ? |
| 10 | Agent | E39_Actor |
| 11 | Complex Work | Work |
| 12 | LegalResource | Work |
| 13 | WorkSubdivision | Work |
| 14 | Expression | F22_Self-Contained_Expression |
| 15 | Format | Manifestation |
| 16 | LegalExpression | Expression |
| 17 | LegalResourceSubdivision | LegalResource |
| 18 | LegalResourceSubdivision | WorkSubdivision |
| 19 | Manifestation | F3_Manifestation_Product_Type |
| 20 | Organization | Agent |
| 21 | Person | Agent |
| 22 | Organization | F11_Corporate_Body |
| 23 | Person | F10_Person |
| 24 | Work | F1_Work |

Total subclass relationships: 24
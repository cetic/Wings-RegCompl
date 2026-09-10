# CRA Ontology & Taxonomy

> Derived from **Regulation (EU) 2024/2847** — Cyber Resilience Act  
> Source: Article 3 (Definitions), Articles 6–8 (Product Categories), Articles 13–25 (Obligations), Annexes I–VIII

---

## 1. Class Hierarchy (Taxonomy)

```
Thing
├── Actor
│   ├── EconomicOperator                         # Art. 3(12)
│   │   ├── Manufacturer                         # Art. 3(13), Art. 13
│   │   ├── AuthorisedRepresentative              # Art. 3(15), Art. 18
│   │   ├── Importer                             # Art. 3(16), Art. 19
│   │   └── Distributor                          # Art. 3(17), Art. 20
│   ├── OpenSourceSoftwareSteward                # Art. 3(14), Art. 24
│   ├── Consumer                                 # Art. 3(18)
│   ├── User
│   └── InstitutionalActor
│       ├── EuropeanCommission                   # Art. 9, 61, 62
│       ├── MemberState
│       ├── ENISA                                # Art. 14, 16
│       ├── CSIRT                                # Art. 3(51), Art. 14
│       ├── NotifyingAuthority                   # Art. 3(26), Art. 36
│       ├── MarketSurveillanceAuthority          # Art. 3(33), Art. 52
│       ├── NotifiedBody                         # Art. 3(29), Art. 39
│       ├── ConformityAssessmentBody             # Art. 3(28)
│       └── ADCO                                 # Art. 52(15), Art. 13(25)
│
├── ProductWithDigitalElements                   # Art. 3(1)
│   ├── DefaultProduct                           # Art. 6 (standard conformity)
│   ├── ImportantProduct                         # Art. 7, Annex III
│   │   ├── ImportantProduct_ClassI              # Annex III, Class I
│   │   └── ImportantProduct_ClassII             # Annex III, Class II
│   ├── CriticalProduct                          # Art. 8, Annex IV
│   └── HighRiskAISystem                         # Art. 12, Reg. (EU) 2024/1689
│
├── ProductComponent                             # Art. 3(6)
│   ├── Software                                 # Art. 3(4)
│   │   ├── FreeAndOpenSourceSoftware            # Art. 3(48)
│   │   └── UnfinishedSoftware                   # Art. 4(3)
│   └── Hardware                                 # Art. 3(5)
│
├── TechnicalConcept
│   ├── ElectronicInformationSystem              # Art. 3(7)
│   ├── RemoteDataProcessing                     # Art. 3(2)
│   ├── Connection
│   │   ├── LogicalConnection                    # Art. 3(8)
│   │   ├── PhysicalConnection                   # Art. 3(9)
│   │   └── IndirectConnection                   # Art. 3(10)
│   ├── EndPoint                                 # Art. 3(11)
│   └── SoftwareBillOfMaterials                  # Art. 3(39)
│
├── CybersecurityConcept
│   ├── Cybersecurity                            # Art. 3(3)
│   ├── CybersecurityRisk                        # Art. 3(37)
│   │   └── SignificantCybersecurityRisk         # Art. 3(38)
│   ├── Vulnerability                            # Art. 3(40)
│   │   ├── ExploitableVulnerability             # Art. 3(41)
│   │   └── ActivelyExploitedVulnerability       # Art. 3(42)
│   ├── CyberThreat                              # Art. 3(46)
│   ├── Incident                                 # Art. 3(43)
│   │   ├── SecurityImpactIncident               # Art. 3(44)
│   │   └── NearMiss                             # Art. 3(45)
│   └── SecurityUpdate                           # Annex I, Part I(2)(c)
│
├── MarketActivity
│   ├── PlacingOnTheMarket                       # Art. 3(21)
│   ├── MakingAvailableOnTheMarket               # Art. 3(22)
│   ├── SubstantialModification                  # Art. 3(30)
│   ├── Recall                                   # Art. 3(49)
│   └── Withdrawal                               # Art. 3(50)
│
├── UseContext
│   ├── IntendedPurpose                          # Art. 3(23)
│   ├── ReasonablyForeseeableUse                 # Art. 3(24)
│   └── ReasonablyForeseeableMisuse              # Art. 3(25)
│
├── ComplianceArtifact
│   ├── ConformityAssessment                     # Art. 3(27), Art. 32
│   │   ├── InternalControlAssessment            # Annex VIII, Part I (Module A)
│   │   ├── EUTypeExamination                    # Annex VIII, Part II (Module B)
│   │   ├── InternalProductionControl            # Annex VIII, Part III (Module C)
│   │   └── FullQualityAssurance                 # Annex VIII, Part IV (Module H)
│   ├── EUDeclarationOfConformity                # Art. 28, Annex V
│   │   └── SimplifiedEUDeclarationOfConformity  # Art. 13(20), Annex VI
│   ├── TechnicalDocumentation                   # Art. 31, Annex VII
│   ├── CybersecurityRiskAssessment              # Art. 13(2)–(4)
│   ├── CEMarking                                # Art. 3(31), Art. 29–30
│   ├── HarmonisedStandard                       # Art. 3(36), Art. 27
│   ├── EuropeanStandard                         # Art. 3(35)
│   ├── InternationalStandard                    # Art. 3(34)
│   ├── EuropeanCybersecurityCertificate         # Art. 8, Reg. (EU) 2019/881
│   └── CommonSpecification                      # Art. 27
│
├── LegalProvision
│   ├── EssentialCybersecurityRequirement        # Annex I
│   │   ├── ProductPropertyRequirement           # Annex I, Part I
│   │   └── VulnerabilityHandlingRequirement     # Annex I, Part II
│   ├── Obligation
│   │   ├── ManufacturerObligation               # Art. 13
│   │   ├── ReportingObligation                  # Art. 14
│   │   ├── ImporterObligation                   # Art. 19
│   │   ├── DistributorObligation                # Art. 20
│   │   ├── StewardObligation                    # Art. 24
│   │   └── InformationObligation                # Annex II
│   ├── SupportPeriod                            # Art. 3(20), Art. 13(8)
│   └── Penalty                                  # Art. 64
│
├── Enterprise
│   ├── Microenterprise                          # Art. 3(19), Rec. 2003/361/EC
│   ├── SmallEnterprise                          # Art. 3(19)
│   └── MediumSizedEnterprise                    # Art. 3(19)
│
└── LegalFramework
    ├── UnionHarmonisationLegislation            # Art. 3(32)
    ├── PersonalData                             # Art. 3(47), Reg. (EU) 2016/679
    └── CoordinatedVulnerabilityDisclosure       # Annex I, Part II(5)
```

---

## 2. Object Properties (Relationships)

| Property | Domain | Range | Source |
|---|---|---|---|
| `manufactures` | Manufacturer | ProductWithDigitalElements | Art. 3(13) |
| `imports` | Importer | ProductWithDigitalElements | Art. 3(16) |
| `distributes` | Distributor | ProductWithDigitalElements | Art. 3(17) |
| `representsManufacturer` | AuthorisedRepresentative | Manufacturer | Art. 3(15) |
| `stewards` | OpenSourceSoftwareSteward | FreeAndOpenSourceSoftware | Art. 3(14) |
| `hasComponent` | ProductWithDigitalElements | ProductComponent | Art. 3(1), (6) |
| `hasRemoteDataProcessing` | ProductWithDigitalElements | RemoteDataProcessing | Art. 3(1), (2) |
| `hasConnection` | ProductWithDigitalElements | Connection | Art. 3(8)–(10) |
| `hasSBOM` | ProductWithDigitalElements | SoftwareBillOfMaterials | Art. 3(39), Annex I Part II(1) |
| `isSubjectTo` | ProductWithDigitalElements | ConformityAssessment | Art. 32 |
| `mustComplyWith` | ProductWithDigitalElements | EssentialCybersecurityRequirement | Art. 6 |
| `hasSupportPeriod` | ProductWithDigitalElements | SupportPeriod | Art. 3(20), Art. 13(8) |
| `hasVulnerability` | ProductWithDigitalElements | Vulnerability | Art. 3(40) |
| `exploits` | CyberThreat | Vulnerability | Art. 3(40), (46) |
| `causesIncident` | Vulnerability | Incident | Art. 3(43), (44) |
| `posesRisk` | ProductWithDigitalElements | CybersecurityRisk | Art. 3(37) |
| `addressedBy` | Vulnerability | SecurityUpdate | Annex I, Part II(2), (8) |
| `performsAssessment` | NotifiedBody | ConformityAssessment | Art. 39, Art. 47 |
| `notifies` | NotifyingAuthority | NotifiedBody | Art. 35, Art. 43 |
| `supervisesMarket` | MarketSurveillanceAuthority | ProductWithDigitalElements | Art. 52 |
| `reportsTo` | Manufacturer | CSIRT | Art. 14(1) |
| `reportsToENISA` | Manufacturer | ENISA | Art. 14(1) |
| `affixesCEMarking` | Manufacturer | CEMarking | Art. 13(12), Art. 30 |
| `issuesDeclaration` | Manufacturer | EUDeclarationOfConformity | Art. 13(12), Art. 28 |
| `producesTechDoc` | Manufacturer | TechnicalDocumentation | Art. 13(12), Art. 31 |
| `performsRiskAssessment` | Manufacturer | CybersecurityRiskAssessment | Art. 13(2) |
| `placesOnMarket` | EconomicOperator | ProductWithDigitalElements | Art. 3(21) |
| `makesAvailable` | EconomicOperator | ProductWithDigitalElements | Art. 3(22) |
| `hasIntendedPurpose` | ProductWithDigitalElements | IntendedPurpose | Art. 3(23) |
| `presumesConformityVia` | ProductWithDigitalElements | HarmonisedStandard | Art. 27 |
| `classifiedUnder` | ProductWithDigitalElements | ProductCategory | Art. 7, Art. 8 |
| `imposedOn` | Penalty | EconomicOperator | Art. 64 |
| `deemsCompliantWith` | EssentialCybersecurityRequirement | EssentialCybersecurityRequirement | Art. 12 (CRA ↔ AI Act) |

---

## 3. Product Categories (Annex III & IV)

### 3.1 Important Products — Class I (Annex III)

| # | Category | Type |
|---|---|---|
| 1 | Identity management systems & privileged access management (incl. biometric readers) | HW/SW |
| 2 | Standalone and embedded browsers | SW |
| 3 | Password managers | SW |
| 4 | Anti-malware software | SW |
| 5 | VPN products | SW |
| 6 | Network management systems | SW |
| 7 | SIEM systems | SW |
| 8 | Boot managers | SW |
| 9 | PKI & digital certificate issuance software | SW |
| 10 | Physical and virtual network interfaces | HW/SW |
| 11 | Operating systems | SW |
| 12 | Routers, modems, switches (internet-connected) | HW |
| 13 | Microprocessors with security-related functionalities | HW |
| 14 | Microcontrollers with security-related functionalities | HW |
| 15 | ASICs & FPGAs with security-related functionalities | HW |
| 16 | Smart home general purpose virtual assistants | SW/HW |
| 17 | Smart home products with security functionalities (locks, cameras, baby monitors, alarms) | HW |
| 18 | Internet-connected toys with social interactive or location tracking features | HW |
| 19 | Personal wearable health monitoring / children's wearable products | HW |

### 3.2 Important Products — Class II (Annex III)

| # | Category | Type |
|---|---|---|
| 1 | Hypervisors & container runtime systems | SW |
| 2 | Firewalls, intrusion detection & prevention systems | SW/HW |
| 3 | Tamper-resistant microprocessors | HW |
| 4 | Tamper-resistant microcontrollers | HW |

### 3.3 Critical Products (Annex IV)

| # | Category | Type |
|---|---|---|
| 1 | Hardware devices with security boxes | HW |
| 2 | Smart meter gateways & advanced security devices (incl. cryptoprocessors) | HW |
| 3 | Smartcards or similar devices, including secure elements | HW |

---

## 4. Conformity Assessment Paths

```
ProductWithDigitalElements
│
├── DefaultProduct (Art. 6)
│   └── Internal control (Module A) — Annex VIII Part I
│
├── ImportantProduct_ClassI (Art. 7, Art. 32(2))
│   ├── Option (a): Harmonised standard applied → Internal control (Module A)
│   ├── Option (b): EU-type examination (Module B) + Internal production control (Module C)
│   └── Option (c): Full quality assurance (Module H)
│
├── ImportantProduct_ClassII (Art. 7, Art. 32(3))
│   ├── Option (a): EU-type examination (Module B) + Internal production control (Module C)
│   ├── Option (b): Full quality assurance (Module H)
│   └── Option (c): European cybersecurity certificate (assurance ≥ "substantial")
│
├── CriticalProduct (Art. 8)
│   ├── If delegated act adopted → European cybersecurity certificate (assurance ≥ "substantial")
│   └── If no delegated act    → Same as ImportantProduct_ClassII
│
└── HighRiskAISystem (Art. 12)
    └── Conformity assessment per Art. 43 of Reg. (EU) 2024/1689
        (CRA cybersecurity requirements deemed satisfied if Annex I met)
```

---

## 5. Essential Cybersecurity Requirements (Annex I)

### Part I — Product Properties

| Ref | Requirement | Security Property |
|---|---|---|
| (1) | Appropriate level of cybersecurity based on risks | Security by design |
| (2)(a) | No known exploitable vulnerabilities at market placement | Vulnerability-free release |
| (2)(b) | Secure by default configuration | Secure defaults |
| (2)(c) | Security updates with automatic install (opt-out available) | Patchability |
| (2)(d) | Protection from unauthorised access (auth, IAM) | Access control |
| (2)(e) | Confidentiality of data (encryption at rest & transit) | Confidentiality |
| (2)(f) | Integrity of data, commands, programs, configuration | Integrity |
| (2)(g) | Data minimisation | Privacy |
| (2)(h) | Availability after incident (resilience, DoS mitigation) | Availability |
| (2)(i) | Minimise negative impact on other devices/networks | Network safety |
| (2)(j) | Limit attack surfaces, including external interfaces | Attack surface reduction |
| (2)(k) | Reduce impact of incidents (exploitation mitigation) | Resilience |
| (2)(l) | Security logging & monitoring (opt-out for user) | Auditing |
| (2)(m) | Secure data removal and transfer | Secure decommission |

### Part II — Vulnerability Handling

| Ref | Requirement |
|---|---|
| (1) | Identify & document vulnerabilities; produce SBOM |
| (2) | Address & remediate vulnerabilities without delay; separate security from feature updates |
| (3) | Effective and regular security testing |
| (4) | Publicly disclose fixed vulnerability information |
| (5) | Coordinated vulnerability disclosure policy |
| (6) | Facilitate sharing of vulnerability information; provide reporting contact |
| (7) | Secure update distribution mechanisms |
| (8) | Disseminate security updates promptly and free of charge |

---

## 6. Obligation Matrix

| Obligated Actor | Key Articles | Core Obligations |
|---|---|---|
| **Manufacturer** | Art. 13, 14 | Design/produce per Annex I; risk assessment; tech doc; CE marking; EU declaration; vulnerability handling; reporting to CSIRT + ENISA; support period (≥5 yr); SBOM |
| **Authorised Representative** | Art. 18 | Act on manufacturer's behalf per written mandate; keep declaration & tech doc; cooperate with authorities |
| **Importer** | Art. 19 | Verify CE marking & conformity; ensure manufacturer compliance; label products; keep EU declaration 10+ yr |
| **Distributor** | Art. 20 | Verify CE marking & documentation; inform manufacturer of vulnerabilities; cooperate with authorities |
| **Open-Source Software Steward** | Art. 24 | Cybersecurity policy; cooperate with MSAs; report actively exploited vulnerabilities; provide SBOM on request |

---

## 7. Penalty Tiers (Art. 64)

| Tier | Maximum Fine | Trigger |
|---|---|---|
| 1 | €15M or 2.5% global turnover | Non-compliance with Annex I essential requirements and Art. 13, 14 |
| 2 | €10M or 2% global turnover | Non-compliance with Art. 18–23, 28, 30–33, 39, 41, 47, 49, 53 |
| 3 | €5M or 1% global turnover | Supplying incorrect/incomplete/misleading info to notified bodies or MSAs |

---

## 8. Cross-Regulation Mappings

| CRA Provision | Related EU Legislation | Relationship |
|---|---|---|
| Art. 12 | Regulation (EU) 2024/1689 (AI Act) | CRA compliance deems AI Act Art. 15 cybersecurity met |
| Art. 3(3) | Regulation (EU) 2019/881 (Cybersecurity Act) | CRA reuses cybersecurity definition |
| Art. 3(43)–(45) | Directive (EU) 2022/2555 (NIS 2) | CRA reuses incident/near miss definitions |
| Art. 25 | Regulation (EU) 2019/881 | Security attestation via EUCC scheme |
| Art. 11 | Regulation (EU) 2023/988 (General Product Safety) | CRA derogation; GPSR applies for uncovered risks |
| Art. 2 (scope) | Regulation (EU) 2017/745 (Medical Devices) | Medical devices excluded from CRA |
| Art. 2 (scope) | Regulation (EU) 2019/2144 (Vehicle Type-Approval) | Motor vehicles excluded from CRA |
| Art. 2 (scope) | Regulation (EU) 2018/1139 (Aviation Safety) | Certified aviation products excluded from CRA |
| Art. 66 | Regulation (EU) 2019/1020 (Market Surveillance) | CRA amends market surveillance framework |
| Art. 67 | Directive (EU) 2020/1828 (Representative Actions) | CRA amends representative actions scope |

---

## 9. Key Timelines (Art. 69, 71)

| Date | Event |
|---|---|
| 10 Dec 2024 | Entry into force (20 days after OJ publication) |
| 11 Jun 2026 | Art. 14 reporting obligations apply (CSIRT + ENISA) |
| 11 Dec 2025 | Commission implementing act on technical descriptions (Art. 7(4)) |
| 11 Sep 2026 | Chapter IV (Notified bodies) applies |
| 11 Dec 2027 | Full application of all provisions |

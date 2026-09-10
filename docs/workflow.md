# CRA Agent System — Workflow Organigramme

> Agent orchestration, tool chains, and data flows

---

## 1. Agent Hierarchy

```mermaid
flowchart TD
    ROOT["🧠 cra_orchestrator\nGemini 2.5 Flash-Lite\n35 tools"]

    ROOT -->|"transfer_to_agent\n(single article parse)"| PARSER["📜 parser_agent\nGemini 2.5 Flash-Lite\n4 tools"]
    ROOT -->|"transfer_to_agent\n(single article ingest)"| INGEST["💾 ingestion_agent\nGemini 2.5 Flash-Lite\n3 tools"]
    ROOT -.->|"rarely delegated\n(tools used directly)"| QUERY["🔍 query_agent\nGemini 2.5 Flash-Lite\n7 tools"]

    PARSER -->|"return parsed JSON"| ROOT
    INGEST -->|"return ingestion report"| ROOT
    QUERY -->|"return query results"| ROOT

    classDef root fill:#1F3864,color:#fff,stroke:#1F3864,stroke-width:2px
    classDef sub fill:#e8f4f8,stroke:#2980b9,stroke-width:2px
    classDef weak fill:#f5f5f5,stroke:#bbb,stroke-dasharray:5

    class ROOT root
    class PARSER,INGEST sub
    class QUERY weak
```

---

## 2. Complete Tool Map

```mermaid
flowchart LR
    subgraph ORCHESTRATOR["cra_orchestrator — 35 tools"]
        direction TB

        subgraph READ["📖 CRA Text Reading"]
            list_articles
            read_article
            read_annex
            read_chapter
            read_recital
            list_recitals
            list_annexes
        end

        subgraph BATCH["⚡ Batch Parse & Ingest"]
            batch_parse_and_ingest
            batch_parse_recitals
            batch_parse_annexes
        end

        subgraph NEO["🔎 Neo4j Query"]
            get_graph_stats
            get_article_obligations
            get_all_obligations
            get_actors
            get_article_nodes
            get_deadlines
            get_verification_actions
            wipe_graph
        end

        subgraph VEC["🧲 Vector & Semantic"]
            vectorize_graph
            vectorize_obligations
            semantic_search
            search_obligations
        end

        subgraph LINK["🔗 Obligation Linking"]
            link_obligations
            conformity_trace
            compliance_impact
        end

        subgraph PROD["🏭 Product Analysis"]
            classify_product
            product_obligations
            filter_obligations
            export_assessment_to_excel
        end

        subgraph CYPHER["💬 NL→Cypher"]
            ask_graph
        end
    end

    classDef toolgroup fill:#f9f9f9,stroke:#ddd
    class READ,BATCH,NEO,VEC,LINK,PROD,CYPHER toolgroup
```

---

## 3. Workflow A — Knowledge Graph Construction

```mermaid
flowchart TD
    START_A([User: "ingest all articles"]) --> BATCH_A["batch_parse_and_ingest\n(article_range='all')"]

    BATCH_A --> LOOP{"For each article\n1 → 71"}

    LOOP --> PARSE_ONE["_parse_one(article_number)"]
    PARSE_ONE --> READ_ART["read_article(N)\n→ CRA markdown text"]
    READ_ART --> GEMINI_PARSE["🤖 Gemini 2.5 Flash-Lite\nPARSER_PROMPT\n+ article text"]
    GEMINI_PARSE --> JSON_OUT["Structured JSON:\n• nodes (11 label types)\n• relationships (20+ types)\n• obligations (id, actor, action)\n• cross-references"]
    JSON_OUT --> SAVE_JSON["save to\n/outputs/articles/art_N.json"]

    SAVE_JSON --> INGEST_ONE["ingest_json_to_neo4j(N)"]

    subgraph INGEST_ONE["Neo4j Ingestion Pipeline"]
        direction TB
        I1["Create constraints\n(UNIQUE on Article, Obligation,\nVerificationAction, CRANode)"]
        I2["MERGE nodes\n:CRANode + specific labels\n(Actor, Product, Concept…)"]
        I3["MERGE relationships\nwith properties & paragraph_ref"]
        I4["MERGE obligations\nStructured ID:\nch{N}_sec{S}_art{A}_par{P}_{i}"]
        I5["Link actor → obligation\n:HAS_OBLIGATION"]
        I6["Link article → obligation\n:CONTAINS_OBLIGATION"]
        I7["Link obligation → nodes\n:RELATES_TO"]
        I8["🤖 Gemini → generate\nVerificationActions\n(1–3 per obligation)"]
        I9["Deduplicate verifications\ncosine similarity > 0.95\n(768-dim nomic-embed-text)"]
        I10["Link obligation → verification\n:HAS_VERIFICATION"]

        I1 --> I2 --> I3 --> I4
        I4 --> I5 & I6 & I7
        I7 --> I8 --> I9 --> I10
    end

    INGEST_ONE --> RATE["⏱️ rate_limit\n4.5s min between\nGemini calls"]
    RATE --> LOOP

    LOOP -->|"all done"| STATS["get_graph_stats()\n→ node/rel counts"]

    classDef gemini fill:#fef3cd,stroke:#f39c12,stroke-width:2px
    classDef neo fill:#d5f5e3,stroke:#27ae60,stroke-width:2px
    class GEMINI_PARSE,I8 gemini
    class I1,I2,I3,I4,I5,I6,I7,I9,I10 neo
```

The same pattern applies to **recitals** (`batch_parse_recitals`, 130 items) and **annexes** (`batch_parse_annexes`, 8 items).

---

## 4. Workflow B — Vectorization & Semantic Search

```mermaid
flowchart TD
    START_V([User: "vectorize the graph"]) --> VG["vectorize_graph(sections='articles')"]

    VG --> SPLIT["Split CRA markdown\ninto chunks\n(1 per article/recital/annex)"]
    SPLIT --> EMBED["🧲 Ollama nomic-embed-text\nbatch of 10 texts\n→ 768-dim vectors"]
    EMBED --> CHUNK_NODES[("Neo4j\nCREATE :CRAChunk nodes\nwith text + embedding")]
    CHUNK_NODES --> INDEX_1["CREATE VECTOR INDEX\ncra_chunk_embedding"]
    CHUNK_NODES --> LINK_ART["MATCH :Article → :CRAChunk\nCREATE :EMBEDS"]

    START_VO([User: "vectorize obligations"]) --> VO["vectorize_obligations()"]
    VO --> EMBED_OBL["🧲 Ollama nomic-embed-text\nall 461+ obligations\n→ 768-dim vectors"]
    EMBED_OBL --> SET_VEC[("Neo4j\nSET obligation.embedding = vector")]
    SET_VEC --> INDEX_2["CREATE VECTOR INDEX\ncra_obligation_embedding"]

    QUERY_SEM([User: "search for SBOM"]) --> SS["search_obligations(query, mode='hybrid')"]
    SS --> KW["Keyword pass\nCONTAINS on action text"]
    SS --> VS["Semantic pass\nvector similarity search"]
    KW --> MERGE_R["Deduplicate & re-rank\nboost dual-match results"]
    VS --> MERGE_R
    MERGE_R --> RESULTS["Top-K obligations\nranked by relevance"]

    classDef ollama fill:#e8d5f5,stroke:#8e44ad,stroke-width:2px
    classDef neo fill:#d5f5e3,stroke:#27ae60,stroke-width:2px
    class EMBED,EMBED_OBL ollama
    class CHUNK_NODES,SET_VEC,INDEX_1,INDEX_2 neo
```

---

## 5. Workflow C — Obligation Linking

```mermaid
flowchart TD
    START_L([User: "link obligations"]) --> LO["link_obligations(mode='full')"]

    LO --> STRUCT["Structural Discovery\n(deterministic)"]

    subgraph STRUCT["Phase 1 — Structural Analysis"]
        direction TB
        S1["_find_intra_article_refines()\nSub-paragraph → parent"]
        S2["_find_cross_article_derives()\nCross-article mandates\nvia shared CRANode"]
        S3["_find_supports_links()\nArt. 24–35 (procedural)\n→ Art. 13–23 (substantive)"]
        S4["_find_complements_links()\nDifferent actors → same goal\n(shared CRANode)"]
    end

    STRUCT --> LLM_PHASE["Phase 2 — LLM Classification"]

    subgraph LLM_PHASE["Ambiguous Pair Resolution"]
        direction TB
        LP1["Select unresolved pairs\n(shared CRANode but\nno structural match)"]
        LP2["🤖 Gemini 2.5 Flash-Lite\n_classify_pair_llm()\n→ relationship type\n+ confidence"]
        LP3["Filter confidence ≥ 0.6\nCREATE relationship"]
        LP1 --> LP2 --> LP3
    end

    LLM_PHASE --> NEO_WRITE[("Neo4j\nMERGE :REFINES\nMERGE :DERIVES_FROM\nMERGE :SUPPORTS\nMERGE :COMPLEMENTS")]

    NEO_WRITE --> TRACE["conformity_trace(topic)\nBFS walk obligation graph\n→ compliance chain"]

    NEO_WRITE --> IMPACT["compliance_impact(obl_ids)\nPropagate compliance\n→ full / partial / evidence"]

    classDef gemini fill:#fef3cd,stroke:#f39c12,stroke-width:2px
    classDef neo fill:#d5f5e3,stroke:#27ae60,stroke-width:2px
    class LP2 gemini
    class NEO_WRITE neo
```

---

## 6. Workflow D — Product Obligations (Main Pipeline)

```mermaid
flowchart TD
    START_P(["User: describe product\n+ actor role"]) --> PO["product_obligations(\ndescription, actor_role)"]

    PO --> CLASSIFY["Step 1 — classify_product()"]

    subgraph CLASSIFY["🤖 Gemini 2.5 Flash-Lite — Classification"]
        direction TB
        C1["Input: product description"]
        C2["Match against 26\nAnnex III categories"]
        C3["Output:\n• product_class (default/I/II/critical)\n• confidence (high/medium/low)\n• matched_categories\n• annex_iii_numbers [1–19]\n• key_features\n• actor_roles"]
        C1 --> C2 --> C3
    end

    CLASSIFY --> FETCH["Step 2 — _get_product_obligations()"]

    subgraph FETCH["Neo4j — 5-Layer Stratified Query"]
        direction TB
        L1["Layer 1 — Universal\nAll products:\nProductWithDigitalElements\ngeneric obligations"]
        L2["Layer 2 — Actor-specific\nManufacturer / Importer /\nDistributor / OSS Steward\n→ HAS_OBLIGATION"]
        L3["Layer 3 — Class-specific\nclass_i / class_ii / critical\nnode obligations"]
        L4["Layer 4 — Product-type\nAnnex III numbers\n→ mapped CRA nodes\n(e.g. 19 → wearables)"]
        L5["Layer 5 — Deadline-scoped\nTime-bound obligations\nnot yet captured"]

        L1 --- L2 --- L3 --- L4 --- L5
    end

    FETCH --> DEDUP["Merge & deduplicate\nacross all 5 layers"]

    DEDUP --> FILTER["Step 2b — _filter_obligations()"]

    subgraph FILTER["🤖 Gemini 2.5 Flash — AI Relevance Filter"]
        direction TB
        F1["Batch of 40 obligations"]
        F2["Product context:\nname, class, features,\nactor roles"]
        F3["LLM returns IDs that\nare NOT applicable\n(conservative — keeps\nambiguous ones)"]
        F1 & F2 --> F3
    end

    FILTER --> CONF["Step 3 — Conformity Route"]

    subgraph CONF["Neo4j — Art. 32 Query"]
        direction TB
        CR1["default → Self-assessment"]
        CR2["class_i → Self OR third-party"]
        CR3["class_ii → MANDATORY third-party"]
        CR4["critical → EU certificate required"]
    end

    CONF --> JSON_WRITE["Step 4 — Write Assessment JSON"]

    subgraph JSON_WRITE["📄 /outputs/CRA_<product>_<timestamp>.json"]
        direction TB
        J1["product: classification metadata"]
        J2["checklist: flat obligation list\nwith status / evidence / notes"]
        J3["conformity_assessment: route info"]
        J4["statistics: counts per layer"]
    end

    JSON_WRITE --> DONE(["Return: json_file path\n+ obligation count\n+ classification summary"])

    classDef gemini fill:#fef3cd,stroke:#f39c12,stroke-width:2px
    classDef neo fill:#d5f5e3,stroke:#27ae60,stroke-width:2px
    classDef file fill:#fde8e8,stroke:#e74c3c,stroke-width:1px

    class C1,C2,C3,F1,F2,F3 gemini
    class L1,L2,L3,L4,L5,CR1,CR2,CR3,CR4 neo
    class J1,J2,J3,J4 file
```

---

## 7. Workflow E — NL → Cypher Query

```mermaid
flowchart TD
    START_Q(["User: complex question\nabout the graph"]) --> ASK["ask_graph(question)"]

    ASK --> SCHEMA["Inject graph schema\n(labels, rels, properties)"]
    SCHEMA --> OLLAMA["🦙 Ollama\ntext-to-cypher-Gemma-3-4B\nGenerate Cypher query"]
    OLLAMA --> CLEAN["Auto-fix:\n• strip markdown fences\n• fix reversed arrows\n• replace escaped newlines"]
    CLEAN --> EXEC["query_neo4j(cypher)\n→ execute against Neo4j"]
    EXEC --> CHECK{Error?}
    CHECK -->|"Yes"| RETRY["Retry with\nerror feedback\n→ Ollama"]
    RETRY --> CLEAN
    CHECK -->|"No"| RESULT["Return:\n• generated Cypher\n• formatted result table"]

    classDef ollama fill:#e8d5f5,stroke:#8e44ad,stroke-width:2px
    classDef neo fill:#d5f5e3,stroke:#27ae60,stroke-width:2px
    class OLLAMA,RETRY ollama
    class EXEC neo
```

---

## 8. Single Article Parse → Ingest (via Sub-agents)

```mermaid
sequenceDiagram
    actor User
    participant Root as cra_orchestrator
    participant Parser as parser_agent
    participant Ingest as ingestion_agent
    participant Gemini as Gemini 2.5 Flash-Lite
    participant Neo as Neo4j

    User->>Root: "parse and ingest article 13"
    Root->>Parser: transfer_to_agent("parser_agent")
    
    Parser->>Parser: read_article(13)
    Parser->>Gemini: PARSER_PROMPT + article text
    Gemini-->>Parser: structured JSON (nodes, rels, obligations)
    Parser->>Parser: save_article_json("Art. 13", json)
    Parser->>Root: transfer_to_agent("cra_orchestrator")
    
    Root->>Ingest: transfer_to_agent("ingestion_agent")
    Ingest->>Neo: ingest_json_to_neo4j("Art. 13")
    
    Note over Neo: MERGE nodes (CRANode + labels)
    Note over Neo: MERGE relationships
    Note over Neo: MERGE obligations (structured IDs)
    
    loop For each obligation
        Ingest->>Gemini: generate VerificationActions
        Gemini-->>Ingest: 1–3 verifications per obligation
        Ingest->>Neo: MERGE VerificationAction + HAS_VERIFICATION
    end
    
    Ingest->>Neo: get_graph_stats()
    Neo-->>Ingest: node/rel counts
    Ingest->>Root: transfer_to_agent("cra_orchestrator")
    Root-->>User: "Article 13 ingested: X nodes, Y rels, Z obligations"
```

---

## 9. Technology & External Dependencies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Agent framework** | Google ADK | Multi-agent orchestration |
| **LLM (parsing, classification, filtering)** | Gemini 2.5 Flash-Lite | JSON extraction, product analysis |
| **LLM (obligation filtering)** | Gemini 2.5 Flash | Higher-quality relevance filtering |
| **NL→Cypher** | Ollama + Gemma-3-4B text-to-cypher | Natural language graph queries |
| **Embeddings** | Ollama + nomic-embed-text (768-dim) | Semantic search vectors |
| **Graph database** | Neo4j 5.x (bolt://localhost:7687) | Knowledge graph + vector indexes |
| **Rate limiting** | Custom callbacks (4.5s min interval) | Free tier compliance (15 RPM) |
| **Error recovery** | Exponential backoff (10s/20s/40s) | 429 / RESOURCE_EXHAUSTED retry |
| **Output format** | JSON files + Excel (openpyxl) | Compliance checklists |

---

## 10. Rate Limiting & Resilience

```mermaid
flowchart LR
    CALL["Gemini API call"] --> THROTTLE{"Time since\nlast call < 4.5s?"}
    THROTTLE -->|"Yes"| SLEEP["sleep(remaining)"]
    SLEEP --> SEND["Send request"]
    THROTTLE -->|"No"| SEND

    SEND --> RESP{Response?}
    RESP -->|"200 OK"| DONE["✅ Return result"]
    RESP -->|"429 / 503"| RETRY{"Retry #\n≤ 3?"}
    RETRY -->|"Yes"| BACKOFF["Backoff:\n10s → 20s → 40s"]
    BACKOFF --> SEND
    RETRY -->|"No"| FAIL["❌ Return error"]
```

┌───────────────────────────────────────────────────────────┐
│  FRONTEND          React 19 + TypeScript + Vite           │
│                    react-router-dom 7                      │
│                    localhost:5173                           │
├───────────────────────────────────────────────────────────┤
│  BACKEND           FastAPI + SQLAlchemy + uvicorn          │
│                    localhost:8000                           │
├───────────────────────────────────────────────────────────┤
│  DATABASES         SQLite (assessment.db) — user data      │
│                    Neo4j (bolt://7687)    — CRA ontology   │
├───────────────────────────────────────────────────────────┤
│  AI / LLM          Gemini 2.5 Flash-Lite — classification  │
│                    Gemini 2.5 Flash      — filtering       │
├───────────────────────────────────────────────────────────┤
│  AGENT FRAMEWORK   Google ADK (cra_agents/)                │
└───────────────────────────────────────────────────────────┘
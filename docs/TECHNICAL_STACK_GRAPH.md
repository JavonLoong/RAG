# PowerRAG Technical Stack Knowledge Graph

> **Version**: 1.0  
> **Status**: Completed  
> **Target**: Documentation of system architecture, technology stack, and core data flows.

---

## 1. System Architecture Diagram

```mermaid
graph TB
    %% Styling Definitions
    classDef ui fill:#E1F5FE,stroke:#0288D1,stroke-width:2px,color:#01579B;
    classDef server fill:#EDE7F6,stroke:#5E35B1,stroke-width:2px,color:#311B92;
    classDef pipe fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,color:#1B5E20;
    classDef engine fill:#FFFDE7,stroke:#FBC02D,stroke-width:2px,color:#F57F17;
    classDef storage fill:#FFE0B2,stroke:#F57C00,stroke-width:2px,color:#E65100;
    classDef adapter fill:#FCE4EC,stroke:#C2185B,stroke-width:2px,color:#880E4F;
    classDef eval fill:#E0F2F1,stroke:#00897B,stroke-width:2px,color:#004D40;
    
    subgraph UI_Layer ["App Shell & User Interface Layer"]
        Electron["Electron Shell<br/>(electron/main.cjs)"]
        Preload["Preload Bridge<br/>(electron/preload.cjs)"]
        Frontend["Web Console UI<br/>(React / Vite)"]
    end
    
    subgraph Gateway_Layer ["Gateway & Routing Layer"]
        FastAPI["FastAPI Server<br/>(api_server/server.py)"]
    end
    
    subgraph Data_Pipeline ["Data Pipeline (Ingestion & Cleaning)"]
        DocIngest["Document Ingestion<br/>(PDF, JSON, DOCX, TXT)"]
        OCREngine["OCR Subsystem<br/>(RapidOCR / PaddleOCR / Cloud API)"]
        Chunker["Semantic Chunker<br/>(chunking.py - Title triggers & Overlap)"]
    end
    
    subgraph KG_Pipeline ["Knowledge Graph Construction (GraphRAG)"]
        SchemaConf["Graph Schema Config<br/>(Entities & Relations)"]
        KGExtract["Entity/Relation Extractor<br/>(LLM-based Schema Validation)"]
        LeidenClust["Leiden Clustering<br/>(Community Detection)"]
        CommSummary["Community Summarization<br/>(Global Search Evidence)"]
    end

    subgraph Retrieval_Engine ["Retrieval & Orchestration Engine"]
        QueryRouter["Query Router<br/>(rag_orchestrator/router.py)"]
        Orchestrator["RAG Orchestrator<br/>(rag_orchestrator/)"]
        HybridRetriever["Hybrid Retriever<br/>(retrieval_engine/hybrid.py)"]
        GraphRetriever["Graph Retriever<br/>(retrieval_engine/graph.py)"]
        DenseRetriever["Dense Retriever<br/>(Cosine Similarity)"]
        SparseRetriever["Sparse Retriever<br/>(BM25 + Jieba)"]
        RRF["Reranker (RRF)<br/>(Reciprocal Rank Fusion)"]
    end
    
    subgraph Storage_Layer ["Persistent & Runtime Storage"]
        ChromaDB["Vector Store (ChromaDB)<br/>(Embeddings & Metadata)"]
        GraphStore["Graph Store (NetworkX / JSON)<br/>(Nodes, Edges, Leiden metadata)"]
    end
    
    subgraph Model_Adapters ["Model Adapters & External APIs"]
        LLMClient["LLM Clients<br/>(OpenAICompatibleClient)"]
        EmbedClient["Embedding Adapters<br/>(BGE-M3 / OpenAIEmbedding)"]
    end

    subgraph Eval_Layer ["Continuous Evaluation Layer"]
        EvalHarness["Evaluation Harness<br/>(evaluation/ - 60-question QA test)"]
        QualityProfiles["Quality Profiles<br/>(open_source_90 / reports)"]
    end

    %% Connections
    Electron -->|IPC Control| Preload
    Preload -->|Web Content| Frontend
    Frontend -->|HTTP Requests| FastAPI
    
    FastAPI -->|Initiates Ingestion| Data_Pipeline
    DocIngest --> OCREngine
    OCREngine --> Chunker
    Chunker -->|Vector Chunks| ChromaDB
    Chunker -->|Text for KG| KG_Pipeline
    
    SchemaConf --> KGExtract
    KGExtract -->|Triples & Evidence| GraphStore
    GraphStore --> LeidenClust
    LeidenClust --> CommSummary
    CommSummary -->|Summaries| GraphStore
    
    FastAPI -->|Query Endpoint| QueryRouter
    QueryRouter -->|Fact Query| HybridRetriever
    QueryRouter -->|Relation Query| GraphRetriever
    QueryRouter -->|Global Query| GraphRetriever
    
    HybridRetriever --> DenseRetriever
    HybridRetriever --> SparseRetriever
    DenseRetriever --> ChromaDB
    SparseRetriever --> ChromaDB
    HybridRetriever --> RRF
    
    GraphRetriever -->|Local/Global Search| GraphStore
    
    RRF --> Orchestrator
    GraphRetriever --> Orchestrator
    
    Orchestrator --> LLMClient
    EmbedClient --> DenseRetriever
    
    LLMClient --> KGExtract
    LLMClient --> CommSummary
    
    EvalHarness -->|Benchmark Tests| FastAPI
    EvalHarness --> QualityProfiles

    %% Assigning Classes
    class Electron,Preload,Frontend ui;
    class FastAPI server;
    class DocIngest,OCREngine,Chunker pipe;
    class SchemaConf,KGExtract,LeidenClust,CommSummary pipe;
    class QueryRouter,Orchestrator,HybridRetriever,GraphRetriever,DenseRetriever,SparseRetriever,RRF engine;
    class ChromaDB,GraphStore storage;
    class LLMClient,EmbedClient adapter;
    class EvalHarness,QualityProfiles eval;
```

---

## 2. Layer & Component Details

### 2.1 App Shell & User Interface Layer
* **Electron Desktop Container (`electron/main.cjs`, `electron/preload.cjs`)**:
  * **Role**: Provides a local-first desktop wrapper around the system. Sets up native IPC handlers, manages application lifetimes, handles a scoped local file picker for documents, and configures expanded memory allocations for high-performance rendering.
* **Web Console UI (`frontend_app/current_console/index.html`)**:
  * **Role**: Standard interface for interacting with the RAG pipeline. Includes UI controls for uploading documents, selecting database collections, running Hybrid/GraphRAG searches, viewing knowledge graph visualizations, and configuring LLM parameters.

### 2.2 Gateway & Routing Layer
* **FastAPI Server (`api_server/current_console/server.py`)**:
  * **Role**: The main backend server, providing HTTP endpoints for files ingestion, database connection, text/graph query execution, Leiden community extraction, and testing harnesses.

### 2.3 Data Pipeline (Ingestion & Cleaning)
* **Document Ingestion (`data_pipeline/`)**:
  * **Role**: Parses heterogeneous inputs: PDF manuals, structured JSON files (e.g. from Label Studio), raw TXT, and DOCX documents.
* **OCR Subsystem**:
  * **Role**: Extracts text from scanned PDFs. Implements a multi-engine fallback strategy: browser-based PaddleOCR/Tesseract.js, a dedicated local RapidOCR server, and Baidu Cloud OCR API for high-precision scenarios.
* **Semantic Chunker (`chunking.py`)**:
  * **Role**: Segments parsed document text into retrieval-ready chunks. Features Title-based split triggers, multi-level semantic punctuation break-points, and overlapping context boundaries to preserve contextual information across chunks.

### 2.4 Knowledge Graph Pipeline (GraphRAG)
* **Graph Schema & Extractor (`kg_pipeline/`)**:
  * **Role**: Instructs the LLM to extract domain-specific entity nodes (e.g. `Equipment`, `Component`, `Fault`, `Method`, `Metric`) and relationship edges from corpus chunks. Each extracted triple is strictly validated against the graph schema and bound to its source document's metadata (original text snippet, page number, file source) as explicit "evidence".
* **Leiden Clustering & Summarization**:
  * **Role**: Partitions the global knowledge graph into hierarchical communities using the Leiden community detection algorithm. For each community, the LLM generates a comprehensive summary, enabling the system to address global, cross-document queries.

### 2.5 Retrieval & Orchestration Engine
* **Query Router (`rag_orchestrator/router.py`)**:
  * **Role**: Categorizes user questions into structural archetypes (e.g., local fact lookup, relational cross-entity queries, or global summaries) and routes them to the appropriate retrieval engine.
* **Hybrid Retriever (`retrieval_engine/hybrid.py`)**:
  * **Role**: Combines dense semantic search (embedding similarity) with sparse exact match (BM25 search using Jieba Chinese tokenization).
* **Reranker (RRF)**:
  * **Role**: Performs Reciprocal Rank Fusion to combine candidate lists from sparse and dense paths, ensuring optimal ranking.
* **Graph Retriever (`retrieval_engine/graph.py`)**:
  * **Role**: Executes local GraphRAG retrieval (entity neighborhood expansions) and global GraphRAG retrieval (querying community summaries).
* **RAG Orchestrator (`rag_orchestrator/`)**:
  * **Role**: Coordinates the entire workflow: query routing, multi-path retrieval, prompt assembly (injecting retrieved text and graph evidence), LLM synthesis, citation parsing, and output formatting.

### 2.6 Persistent & Runtime Storage
* **Vector Store (ChromaDB)**:
  * **Role**: Persists chunk embeddings alongside source document metadata (file names, page numbers, and custom tags).
* **Graph Store (`storage_layer/graph_store.py`)**:
  * **Role**: Stores knowledge graph structures, community partitions, and LLM-generated community summaries in a NetworkX/JSON-based local filesystem format.

### 2.7 Model Adapters
* **LLM Client (`OpenAICompatibleLLMClient`)**:
  * **Role**: Standard client abstraction supporting custom OpenAI-compatible endpoints (supporting models like Qwen, GPT-4, etc.) for extraction, synthesis, and QA.
* **Embedding Adapters (`model_adapters/embedding.py`)**:
  * **Role**: Provides interfaces for computing embeddings using local/remote models (such as BGE-M3).

### 2.8 Continuous Evaluation Layer
* **Evaluation Harness (`evaluation/`)**:
  * **Role**: Runs benchmark evaluations on a curated 60-question university physics/power equipment dataset. Measures metrics like query recall, keyword coverage, and evidence correctness.
* **Quality Profiles (`quality_profiles.py`)**:
  * **Role**: Configures testing profiles (e.g., `open_source_90`) to enforce strict regression gates.

---

## 3. Core Data Flows

### 3.1 Document Ingestion Flow
```text
[Raw Document] -> [OCR / Parser] -> [Semantic Chunker] -> [Text Chunks + Metadata]
                                                                  |
                                      +---------------------------+---------------------------+
                                      |                                                       |
                                      v                                                       v
                            [Vector Ingestion]                                       [KG Extraction]
                         Compute Dense Embeddings                                  Extract Entities & Relations
                                      |                                                       |
                                      v                                                       v
                            [ChromaDB Storage]                                      [GraphStore (Nodes/Edges)]
                                                                                              |
                                                                                              v
                                                                                     [Leiden Clustering]
                                                                                              |
                                                                                              v
                                                                                    [Community Summaries]
```

### 3.2 Query & QA Generation Flow
```text
[User Query] -> [Query Router]
                      |
        +-------------+-------------+
        | (Local Fact)              | (Relational/Global Summary)
        v                           v
 [Hybrid Retriever]         [Graph Retriever]
  - Dense (ChromaDB)         - Local Entity Neighborhood
  - Sparse (BM25)            - Global Community Summaries
        |                           |
        v                           v
  [RRF Reranker]            [Evidence Extraction]
        |                           |
        +-------------+-------------+
                      |
                      v
             [Retrieved Evidence]
                      |
                      v
            [RAG QA Orchestrator]
                      |
                      v
             [LLM Synthesis]
                      |
                      v
      [Answer with Citations & Source Links]
```

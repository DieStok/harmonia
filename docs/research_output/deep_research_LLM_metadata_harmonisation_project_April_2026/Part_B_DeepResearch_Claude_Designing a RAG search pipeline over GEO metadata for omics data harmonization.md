# Designing a RAG search pipeline over GEO metadata for omics data harmonization

**A recall-oriented hybrid retrieval system combining BM25, dense biomedical embeddings, and ontology-guided query expansion—deployed on HPC with Qdrant and LlamaIndex—is the most effective architecture for surfacing relevant GEO studies.** This design achieves estimated Recall@100 of 0.80–0.90, a 15–30% improvement over keyword search alone, while keeping query latency under 2 seconds. The critical insight from the literature is that **contrastive-trained biomedical embeddings (BMRETRIEVER, MedCPT) combined with BM25 via Reciprocal Rank Fusion dramatically outperform either approach alone** on biomedical metadata retrieval. The Public Omics Explorer (Grigoriadis et al., 2025) already demonstrates that semantic search over 250K+ GEO-linked records is feasible with biomedical sentence embeddings and FAISS, achieving meaningful improvements over NCBI's native keyword interface. This report provides a complete technical blueprint for building, evaluating, and operating such a system on SLURM infrastructure.

---

## 1. Why GEO search demands more than standard document retrieval

GEO search differs fundamentally from web or general document retrieval in ways that shape every architectural decision. Wang, Lachmann, and Ma'ayan (2019, *Biophysical Reviews*) identify the core problem: "metadata associated with gene expression studies within GEO typically do not adhere to controlled vocabularies," relying instead on "semi-structured textual descriptions" that vary wildly across submitters. A study on breast cancer methylation might describe itself as "BRCA1 promoter hypermethylation profiling" without ever using the phrase "breast cancer."

**Multi-granularity complicates relevance.** GEO's hierarchy—GSE (Series) → GSM (Sample) → GPL (Platform) → GDS (curated DataSet)—means a single GSM can appear in multiple GSE entries, and relevance depends on which level you search. The Gemma curation project (Pavlidis Lab, UBC) enforces one-sample-per-experiment constraints precisely because this ambiguity causes downstream errors. For omics harmonization, GSE-level retrieval is the right unit, but relevance signals often live at the GSM level (sample characteristics like tissue type or treatment condition).

**Existing systems reveal the gap.** GEOmetadb (Zhu et al., 2008, *Bioinformatics*) provides SQL-based relational queries but cannot handle semantic similarity. NCBI's native Entrez search supports Boolean and field-qualified queries but was "not intended for robust systematic analyses" (Barrett et al., 2013). The most relevant prior system is **POE (Public Omics Explorer)**, published by Grigoriadis et al. (2025, *Computational and Structural Biotechnology Journal*), which embeds PubMed titles and abstracts linked to GEO datasets using SBioBERT (768-dimensional vectors) and indexes them with FAISS IndexFlatL2. POE demonstrates that semantic search at the 250K-record scale is practical and superior to keyword matching for handling terminology variation. However, POE searches only linked PubMed abstracts—not GEO metadata directly—creating coverage gaps for datasets without publications.

**The architectural implication** is that GEO search requires a hybrid system handling: (1) exact matching for gene names, platform IDs, and accessions; (2) semantic similarity for conceptual queries; (3) structured filtering on organism, platform, date, and data type; and (4) ontology-aware expansion for biomedical synonym resolution. No single retrieval method addresses all four requirements.

---

## 2. Seven retrieval strategies compared for GEO metadata

### BM25/FTS5 baseline establishes a strong floor

SQLite FTS5 with BM25 scoring provides a zero-infrastructure starting point. With hardcoded k1=1.2, b=0.75, and column weighting (title at 10× weight versus summary at 1×), FTS5 handles 250K documents comfortably with sub-10ms latency and ~100–150MB index size. BM25 achieves **nDCG@10 of ~43.4** on heterogeneous BEIR benchmarks (Abdallah et al., 2025) and remains surprisingly competitive on biomedical tasks with high term overlap. Its critical strength for GEO is exact matching of gene names, platform identifiers, and organism terms. Its critical weakness is vocabulary mismatch: "heart attack" never matches "myocardial infarction."

### Dense embedding retrieval adds semantic understanding

The choice of embedding model is decisive. **BMRETRIEVER** (available at 410M, 2B, and 7B parameters) is the current state-of-the-art dedicated biomedical retriever, outperforming Google GTR-XXL (4.8B params) with its 410M variant on biomedical BEIR tasks. **MedCPT** (ncbi/MedCPT-Article-Encoder, ~110M params, 768 dimensions), trained on 255 million PubMed query-article pairs, is the best lightweight option specifically aligned with PubMed-style queries. A critical finding across multiple studies (Myers et al., 2025, *JAMIA*; Ahooyi et al., 2025; MedTEB benchmark, 2025) is that **domain pre-training alone is insufficient—contrastive training for retrieval is the decisive factor.** Raw PubMedBERT and BioBERT perform poorly as retrievers despite biomedical pre-training. General models with retrieval training (BGE-large-en-v1.5, GTE-large) consistently outperform naively used biomedical models.

For 250K documents with 768-dimensional embeddings, storage is approximately **768MB** (float32). HNSW indexing provides optimal recall-speed tradeoff at this scale, with query latency under 5ms and build time under 5 minutes.

### Hybrid retrieval with RRF delivers the biggest practical gains

Combining BM25 and dense retrieval via **Reciprocal Rank Fusion (RRF, k=60)** is the single most impactful architectural choice. Stuhlmann et al. (SDS 2025) demonstrated that hybrid BM25 + MedCPT with reranking achieves **accuracy of 0.90** on biomedical QA over 24M PubMed documents, compared to 0.72 for BM25 alone—a **25-percentage-point absolute improvement**. The hybrid approach improves recall by **15–30%** over single methods with minimal added complexity (consensus across multiple 2024–2025 studies). An alternative to RRF is convex combination (α × dense + (1-α) × BM25), which Bruch et al. (ACM TOIS, 2022) showed outperforms RRF when α can be tuned—optimal α for biomedical is **0.6–0.7 on dense, 0.3–0.4 on BM25** (validated in KDD 2025).

### ColBERTv2 excels as a reranker rather than a full index

ColBERTv2's per-token embeddings and MaxSim scoring provide fine-grained matching that distinguishes "myocardial infarction was ruled out" from "treatment for myocardial infarction"—a distinction bi-encoders miss. Rivera et al. (arXiv:2510.04757, October 2025) showed ModernBERT + ColBERTv2 reranking achieves the **highest average accuracy of 0.4448** on the MIRAGE biomedical benchmark. However, ColBERTv2's full multi-vector index for 250K documents requires ~1.35GB (versus ~768MB for single-vector), and the PLAID indexing engine doesn't support incremental CRUD well. **The recommended use is as a reranker on top-20–50 hybrid candidates**, avoiding full index storage while capturing token-level matching quality. RAGatouille (`pip install ragatouille`) provides the simplest deployment path.

### LLM-augmented retrieval with ontology expansion yields up to 22% NDCG gain

**BMQExpander** (Al Nazi et al., 2025, arXiv:2508.11784) represents the state of the art in ontology-guided query expansion: it extracts biomedical terms from the query, maps them to UMLS concepts, traverses the ontology graph (MeSH, SNOMED, NCI), and generates a context-rich pseudo-document for query expansion. This achieves up to **22.1% improvement in NDCG@10** over sparse baselines and **6.5% over the strongest baseline** on NFCorpus, TREC-COVID, and SciFact, with **15.7% robustness improvement** under query perturbation. For cross-encoder reranking, a surprising finding from BioASQ 2025 (Verma et al., arXiv:2507.05577) is that **ms-marco-MiniLM-L12 (33M params) outperformed much larger models** including bge-reranker-large (560M params). BAAI/bge-reranker-v2-m3 offers the best balance of quality and efficiency for production deployment.

### Multi-step agentic retrieval handles complex queries

For complex multi-hop queries ("Find single-cell datasets studying drug resistance in triple-negative breast cancer"), agentic approaches are necessary. **WebThinker** (Li et al., 2025, NeurIPS 2025; GitHub: RUC-NLPIR/WebThinker) enables reasoning models to dynamically search, navigate, and extract information during thinking, achieving **22.9% improvement on WebWalkerQA** versus prior methods. **A-RAG** (Zhu et al., February 2026, arXiv:2602.03442) provides hierarchical retrieval interfaces (keyword search, semantic search, chunk read) that an agent autonomously adapts, achieving **94.5% on HotpotQA**. For GEO search, a tiered approach is recommended: fast hybrid retrieval for simple queries (~2s), agentic multi-step for complex queries (~15–60s), and WebThinker-style deep research for comprehensive dataset discovery (~2–10min).

### Dual-source candidate generation merges semantic and reasoning signals

Inspired by **Matchmaker** (Seedat & van der Schaar, NeurIPS 2024, arXiv:2410.24105), which uses ColBERTv2 for late-interaction retrieval in a three-stage schema matching pipeline, the dual-source approach generates candidates from both semantic retrieval and LLM reasoning. A study in *Nature Scientific Reports* (2025) demonstrated that combining Chroma (semantic) + Elasticsearch (keyword) + ColBERTv2 reranking achieves **10% accuracy improvement** over single-source approaches for medical queries. For GEO, Source 1 retrieves by embedding similarity; Source 2 has an LLM reason about what organisms, platforms, and experimental designs would be relevant, generating structured metadata filters.

| Strategy | Recall@100 (est.) | Latency | Complexity | GPU Required |
|----------|-------------------|---------|------------|-------------|
| BM25/FTS5 | 0.55–0.65 | <10ms | Very low | No |
| Dense (MedCPT) | 0.60–0.70 | <20ms | Low | Encoding only |
| Hybrid BM25+Dense+RRF | 0.70–0.80 | <30ms | Medium | Encoding only |
| Hybrid + cross-encoder reranker | 0.80–0.90 | 200–500ms | Medium-high | Recommended |
| + Ontology expansion | 0.82–0.92 | 500ms–2s | High | Recommended |
| + Agentic multi-step | 0.88–0.95 | 15–120s | Very high | Required |

---

## 3. Paper full-text integration and query understanding amplify recall

### Full text recovers information invisible in metadata alone

Westergaard et al. (2018, *PLOS Computational Biology*) analyzed 15 million full-text articles versus 16.5 million MEDLINE abstracts and found that full-text mining **consistently outperforms abstract-only** for extracting protein-protein, disease-gene, and protein subcellular associations. One study found recall increased from **45% to 95%** when including full text for *C. elegans* associations. However, Lin (2009, *BMC Bioinformatics*) showed that treating entire articles as single indexing units does not consistently outperform abstract-only search—**paragraph-level spans within full text** are what actually helps. Full-text articles average 4,148 terms versus 142 for abstracts (29× larger), so chunking strategy becomes critical.

For GEO metadata search, the Methods and Results sections of linked publications contain dataset-specific details—cell lines, treatment conditions, gene lists, platform choices—that are absent from GEO summaries. Over **47,000 PMC articles** cite GEO accession identifiers. The recommended approach is an abstract-first strategy (arXiv:2412.15404): search an abstract-only vector database first to filter top-100 candidates, then perform focused search in full-text chunks for evidence enrichment.

### Section-aware chunking outperforms fixed-size approaches

A comprehensive benchmark (MDPI Bioengineering, November 2025) showed that **adaptive chunking achieves 87% accuracy** versus 50% for fixed-size baselines—a 37-percentage-point improvement. Semantic chunking achieved 0.75 recall but created fragments averaging only 43 tokens. The optimal approach is **element-based, structure-aware chunking** (Jimeno Yepes et al., 2024, arXiv:2402.05131), which achieved the highest retrieval scores with half the chunks of structure-unaware methods. For scientific papers: parse sections using GROBID or Unstructured.io, then apply recursive chunking within sections at **100–200 tokens for Methods/Results** (fine-grained detail) and **256–512 tokens for Introduction/Discussion** (broader context). RAPTOR (Sarthi et al., ICLR 2024) provides hierarchical summarization that improves complex reasoning by **20%** on the QuALITY benchmark.

### Ontology-guided query expansion resolves biomedical vocabulary mismatch

Multi-layer expansion is essential for GEO search. The expansion should cover: gene names via HGNC (TP53 → p53, TRP53); diseases via Disease Ontology and MeSH (breast cancer → breast carcinoma, BRCA); techniques (RNA-seq → RNA sequencing, transcriptome profiling); cell lines via Cellosaurus; and organisms via NCBI Taxonomy. Wright et al. (2017, *Database*, bioCADDIE challenge) found that optimal MeSH expansion uses **3–5 terms weighted at a 1:5 ratio** relative to original query terms, achieving infNDCG of 0.445. UMLS synonym expansion alone increases recall by **23.7%** for non-indexed PubMed citations (Griffon et al., 2012). **BioRAGent** (2025, *Briefings in Bioinformatics*) implements a three-agent architecture (Guide, Retriever, Reviewer) that decomposes multi-hop biomedical queries and outperforms state-of-the-art on 11 single-hop and 3 multi-hop tasks.

---

## 4. Embedding models and rerankers for biomedical retrieval in 2025–2026

The embedding model landscape has shifted decisively. Three findings dominate:

**Domain pre-training without contrastive training fails for retrieval.** The MedTEB benchmark (2025) showed that off-the-shelf BioClinicalBERT, BlueBERT, and BiomedBERT achieve retrieval nDCG@10 of only **0.13–0.17**, while general-purpose GTE Base achieves **0.529 average**. Myers et al. (2025, *JAMIA*) confirmed that BGE (general-purpose) consistently outperformed all medical-specific models including Gatortron on EHR retrieval tasks. The key differentiator is contrastive training for retrieval, not domain pre-training.

**Domain + contrastive training achieves the best performance.** BMRETRIEVER (2024, open-source, multiple sizes from 410M to 7B) is the current state-of-the-art dedicated biomedical retriever. Its 410M variant outperforms models up to **11.7× larger**, including Google GTR-4.8B and SGPT-2.7B. MedCPT (NCBI, trained on 255M PubMed query-article pairs) is the best lightweight option. The purpose-built MedTE model (McMaster, July 2025) achieves **0.578 average** on the 51-task MedTEB benchmark versus 0.539 for the next best. For GEO metadata search specifically, the recommended progression is:

- **Production workhorse:** BAAI/bge-large-en-v1.5 (335M, 1024-dim) — strong out-of-box, fine-tune on biomedical triplets
- **Best biomedical quality/cost:** BMRETRIEVER-410M or MedCPT (768-dim) — purpose-built for biomedical retrieval
- **Maximum quality:** BMRETRIEVER-2B or BGE-M3 (568M, 1024-dim with native sparse+dense)

**Cross-encoders decisively beat LLM rerankers on cost and usually on quality.** ZeRank-1 and NV-RerankQA-Mistral-4B achieve ~0.78 nDCG@10 at **10–30× lower cost** than small LLMs. Cross-encoder reranking of 100 documents costs ~$0.001 versus $0.025–0.125 for pointwise LLM reranking. For production, **bge-reranker-v2-m3** (568M, multi-lingual, up to 8192 tokens) provides the best efficiency-quality balance, while **ms-marco-MiniLM-L-12-v2** (33M params) is a surprisingly effective lightweight option that outperformed larger models on BioASQ 2025. The recommended pipeline is: bi-encoder retrieval (top-100–200) → cross-encoder rerank (top-10–20) → optional LLM listwise rerank (top-10) for high-value queries only.

| Model | Type | Params | Biomedical Performance | GPU VRAM | Recommended For |
|-------|------|--------|----------------------|----------|-----------------|
| BMRETRIEVER-410M | Bi-encoder | 410M | SOTA (outperforms 11.7× larger) | ~2 GB | Primary retriever |
| MedCPT | Bi-encoder | ~110M | Strong on BEIR biomedical | <1 GB | Lightweight option |
| BGE-M3 | Bi+sparse+ColBERT | 568M | 63.0 MTEB overall | 2–4 GB | Unified hybrid model |
| bge-reranker-v2-m3 | Cross-encoder | 568M | Strong across domains | 2–4 GB | Production reranker |
| ms-marco-MiniLM-L-12-v2 | Cross-encoder | 33M | Surprisingly effective | <1 GB | Fast reranker |

---

## 5. Evaluation framework for recall-oriented GEO search

### Recall@K is the right primary metric

When missing a relevant GEO study is more costly than including an irrelevant one, **Recall@K** is the correct optimization target. The Stanford IR textbook (Manning, Raghavan, Schütze) prescribes the F-beta measure with β > 1 to emphasize recall: F₃ weights recall **9× more than precision**. For GEO search, track Recall@50 (power user scan), Recall@100 (standard BEIR cutoff), Recall@200 (thorough review), and Recall@500 (ceiling diagnostic). NDCG@10 serves as the ranking quality metric, and Precision@10 measures top-result quality. Target thresholds: **Recall@100 ≥ 0.80 minimum, ≥ 0.85 target; Recall@200 ≥ 0.90 target.** When a query has more than K relevant documents, use capped recall (R_cap@K) to avoid misleadingly low scores.

### Three complementary gold standard construction methods

**Semi-gold-standard from existing classifiers** provides the quickest path: leverage lab-curated GSE ID lists (e.g., "ALL methylation studies") as binary relevance judgments, validate 10–20% with independent expert review. This is free and immediately available but narrow in coverage.

**Programmatic semi-gold-standards** use structured metadata fields: filter on organism (reliable), platform type (structured), data type, plus keyword matching on title/summary. This scales to arbitrary query types but misses synonyms—manual validation of a 10–20% sample is essential.

**TREC-style pooling** runs multiple retrieval systems (BM25, dense, hybrid) on each query, pools the top-100 from each, deduplicates to ~500–1500 candidates per query, and has experts judge only pooled documents. Microsoft's ISE team (2024) showed that GPT-4o pre-screening with a relevance threshold of 4/5 captures ~90% of documents deemed relevant by experts, dramatically reducing annotation effort. Target **30–50 expert-curated queries** spanning simple organism+disease queries, platform-specific queries, multi-faceted queries, known-item queries, and negative/edge cases, with **50–200 judged documents per query**. Aim for inter-annotator Cohen's κ ≥ 0.70.

### BrowseComp-Plus inspires multi-step evaluation

BrowseComp-Plus (Chen et al., August 2025, NeurIPS 2025 Workshop; arXiv:2508.06600) provides a model for evaluating complex queries on a fixed corpus with human-verified supporting documents and mined hard negatives. For GEO, construct 50–100 multi-faceted queries requiring conjunction of multiple metadata fields: "Human breast cancer methylation studies on Illumina EPIC arrays with paired normal tissue" requires resolving organism + disease + platform + experimental design simultaneously. Score with Recall@K and analyze per-facet failure modes to identify which metadata constraints the system misses.

### Component isolation testing with pytrec_eval

The BEIR framework (`pip install beir`) combined with **pytrec_eval** (`pip install pytrec-eval-terrier`) provides standardized component testing. Hold all components constant while varying one: embedding model (test 3–4 candidates), chunking strategy (sentence vs. recursive vs. field-aware), reranker (none vs. cross-encoder vs. ColBERT), and query expansion method (none vs. MeSH vs. LLM-based). **DeepEval** (v2.3+) maps its five RAG metrics to specific pipeline components: contextual recall evaluates the embedding model, contextual precision evaluates the reranker, and contextual relevancy evaluates chunk size + top-K. Use paired Wilcoxon signed-rank tests per query with p < 0.05 for statistical significance, reporting Cohen's d effect sizes.

---

## 6. Agentic RAG patterns and when each applies to GEO search

### Adaptive RAG routing matches query complexity to retrieval cost

**Adaptive RAG** (Jeong et al., NAACL 2024; arXiv:2403.14403) trains a T5-Large classifier to route queries by complexity: no retrieval for simple factual queries, single-step retrieval for moderate queries, and iterative multi-step retrieval (IRCoT) for complex multi-hop queries. This achieves near-oracle efficiency by avoiding over-retrieval on simple queries. For GEO search, this maps naturally: "Find GSE12345" needs no retrieval; "mouse liver RNA-seq" needs single-step hybrid search; "all single-cell datasets studying neurodegeneration with paired ATAC-seq and scRNA-seq" needs iterative multi-step reasoning.

**Corrective RAG (CRAG)** (Yan et al., 2024, arXiv:2401.15884) adds a lightweight retrieval evaluator (T5-large, 0.77B params) that classifies retrieved documents as Correct/Incorrect/Ambiguous and triggers web search when retrieval quality is low. CRAG improves accuracy by **26.7 percentage points** over vanilla RAG (78.1% versus 51.4%). Its plug-and-play nature makes it ideal as a quality layer on top of existing GEO retrieval: when the evaluator scores all retrieved documents below threshold, trigger query reformulation or ontology expansion rather than accepting poor results.

### LightRAG fits GEO's structured metadata better than Microsoft GraphRAG

GEO metadata is inherently structured and relational—organism taxonomies, platform hierarchies, disease ontologies, tissue–cell type relationships—making it a natural fit for graph-based retrieval. **LightRAG** (Guo et al., EMNLP 2025; GitHub: HKUDS/LightRAG) builds a lightweight knowledge graph with dual-level retrieval: low-level for specific entity queries and high-level for thematic queries using multi-hop neighbors. It achieves **~30% latency reduction** over standard RAG (~80ms versus ~120ms) and supports **incremental updates** through union operations—critical for GEO's weekly sync of ~500–1000 new records per month.

Microsoft GraphRAG (Edge et al., 2024; GitHub: microsoft/graphrag) provides superior global query capabilities through hierarchical community detection and Leiden clustering, but its **indexing is prohibitively expensive** for 250K records due to extensive LLM calls for entity extraction and community summarization. **FAIR GraphRAG** (Flüh et al., IEEE 2025, RWTH Aachen) directly applies GraphRAG to GEO datasets in gastroenterology, linking nodes to biomedical ontologies (SNOMED CT, UMLS) with MIAME-compliant metadata. The recommended approach: pre-build a structured knowledge graph from GEO's existing fields (organism, platform, technique, disease) without LLM extraction for structured data, reserving LLM extraction for free-text summaries, and use LightRAG's dual-level retrieval for query processing.

### Hallucination detection requires entity grounding against GEO metadata

For biomedical metadata search, hallucination detection has a key advantage: claims are verifiable against structured fields. Every organism name, platform ID, and accession number in a generated response can be checked against the GEO database. **HalluGraph** (arXiv:2512.01659) computes Entity Grounding and Relation Preservation scores from knowledge graphs extracted from context, query, and response, achieving AUC ~0.94 on standard domains. For GEO, implement accession-level attribution (every claim links to specific GSE/GSM IDs), structured metadata verification (platform claims match the platform field), and ontology consistency checking (organism-tissue-disease combinations are biologically plausible).

---

## 7. Infrastructure: Qdrant on SLURM with Apptainer is the optimal stack

### Qdrant wins for HPC deployment

Among the five vector databases evaluated, **Qdrant** (Apache 2.0, Rust-based, single-binary) is the clear winner for SLURM + Apptainer environments. Its unprivileged Docker image (`qdrant/qdrant:latest-unprivileged`, UID 1000) converts directly to Apptainer with `apptainer pull qdrant.sif docker://qdrant/qdrant:latest-unprivileged` and runs without root privileges. For 250K documents with 768-dimensional embeddings, Qdrant requires approximately **2–4 GB RAM** in all-RAM mode, with sub-5ms query latency on HNSW indexes tuned to m=16, ef_construction=128. 

Qdrant's native hybrid search (since v1.15.2) supports BM25 with server-side IDF computation alongside dense vectors, eliminating the need for a separate search engine. Its `prefetch` API enables multi-stage retrieval (sparse → dense → reranking) within a single query call, with built-in RRF and Distribution-Based Score Fusion. Metadata filtering is best-in-class, applied during HNSW traversal for efficient pre-filtering—perfect for GEO's structured fields (organism, platform, experiment type, date ranges). Incremental updates via upsert require no full index rebuild, handling weekly GEO syncs in seconds.

**Milvus** offers superior scalability (designed for billions of vectors) and GPU acceleration but requires etcd, MinIO, and message queues for distributed mode—a poor fit for SLURM job scheduling. Milvus Lite (embedded Python) works but lacks hybrid search. **pgvector 0.8.0** improved metadata filtering significantly with iterative index scans but lacks native sparse vector/BM25 support. **Weaviate** has the best hybrid search (Hybrid Search 2.0 with learned fusion) but a heavier operational footprint. **ChromaDB** is adequate for prototyping but lacks native BM25 and production features.

### LlamaIndex provides the best RAG-focused orchestration

**LlamaIndex** is recommended for the orchestration layer, offering native `QdrantVectorStore` integration with `enable_hybrid=True`, 150+ data connectors, specialized indexing strategies (vector, tree, keyword, knowledge graph), and the lowest framework overhead (~6ms per call versus ~10ms for LangChain). Its token efficiency (~1.6K tokens/query) is nearly 50% better than LangChain's (~2.4K). For complex agentic workflows requiring state machines and multi-step reasoning, **LangGraph** (part of the LangChain ecosystem) provides the necessary control flow abstractions. Haystack (deepset) is a strong alternative for pure pipeline-based architectures with built-in evaluation metrics. For HPC, a lightweight custom pipeline with direct Qdrant client + sentence-transformers may ultimately be simpler than any framework.

### GPU budget fits a single A100 node

The complete query-time stack—embedding model, cross-encoder reranker, and LLM for query expansion—fits on a **single A100 (40GB)**. Batch embedding of 250K documents with bge-base (batch_size=32) takes approximately **125 seconds** on A100; weekly incremental updates of ~1000 new documents take seconds and don't require GPU reservation. Cross-encoder reranking of 100 candidates takes **50–200ms** depending on model size (33M to 568M params). LLM inference for query expansion (Qwen2.5-14B-Instruct, 4-bit quantized) requires ~8–10GB VRAM. The recommended SLURM architecture allocates one CPU node for Qdrant (4–8GB RAM, NVMe SSD), one GPU node for weekly batch embedding, and one persistent GPU node (A100 40GB) for the query service running LLM + reranker. Total software cost: $0 (all open-source).

```
HPC Architecture:
├── CPU Node: Qdrant (Apptainer, 4-8GB RAM, NVMe SSD, port 6333)
├── GPU Node (weekly): Batch embedding job (bge-base or BMRETRIEVER, ~2min)
└── GPU Node (persistent): Query service (LLM + reranker, A100 40GB)
    ├── Qwen2.5-14B-Q4 for query expansion (~8GB VRAM)
    ├── bge-reranker-v2-m3 for reranking (~2GB VRAM)
    └── Total query-time: ~20-28GB VRAM
```

---

## 8. Search-to-harmonization handoff and end-to-end evaluation

### Rich handoff is the correct default

Passing only GSE IDs forces the harmonization pipeline to re-derive information already computed during search (organism, platform, sample count), creating redundant API calls and losing relevance context. The recommended handoff includes: GSE ID, calibrated relevance score with confidence interval, match evidence (which query terms matched which metadata fields, evidence snippets), extracted structured metadata (organism, platform, technology, sample count, data type, supplementary file types, PubMed IDs), harmonization hints (predicted processability, potential issues, recommended pipeline), and provenance (retrieval method, index version). Structure this as a versioned JSON schema for downstream consumption.

**Agent-mediated handoff** (where a search agent writes a "data brief" summarizing why each study is relevant) adds ~$0.01–0.05 per GSE in LLM cost but can prevent wasted processing on unsuitable studies. Elucidata's research shows automated LLM curation achieves **83% F1** for sample-level metadata extraction at 10× speed versus manual curation. This is worth the cost when harmonization is expensive (hours per GSE) and false starts are costly.

### Cascaded evaluation decomposes end-to-end performance

End-to-end success decomposes as: **P(search finds study) × P(study is processable | found) × P(harmonization succeeds | processable) × P(data is usable | harmonized)**. Evaluate each stage independently before measuring end-to-end. Track a 2×2 confusion matrix at the search-harmonization boundary (search_relevant × harmonization_successful) to compute "handoff efficiency." Cluster failed GSEs by failure type to identify systematic issues—for example, all Affymetrix studies from 2008–2010 failing due to platform annotation problems.

**Joint optimization through feedback loops** uses harmonization outcomes as reward signals for search. GSEs successfully harmonized into usable data are positive training signals; GSEs scoring high in search but failing processing become hard negatives for retriever fine-tuning. Train a **processability model** on (GSE metadata → harmonization success) using historical outcomes, and blend this into ranking: `0.7 × relevance_score + 0.3 × processability_score`. This gradually improves both search quality and processing efficiency. OpenRAG (arXiv:2503.08398) and DRO (Shi et al., 2025) demonstrate that joint retriever-downstream optimization yields **5–15% improvement** over independent training.

---

## Recommended implementation roadmap

**Phase 1 (Week 1–2): BM25 baseline + evaluation infrastructure.** Create FTS5 table with porter unicode61 tokenizer, column weighting (title 10×, summary 1×). Implement pytrec_eval-based evaluation measuring Recall@{50,100,200,500} and NDCG@10. Build 30 expert queries using existing lab classifications as semi-gold-standard.

**Phase 2 (Week 3–4): Hybrid retrieval with Qdrant.** Deploy Qdrant via Apptainer. Embed all 250K records with MedCPT or BMRETRIEVER-410M. Implement RRF fusion (k=60) of BM25 and dense retrieval. Expected improvement: +15–25% recall over BM25 alone.

**Phase 3 (Month 2): Query expansion + reranking.** Add ontology-guided expansion using UMLS/MeSH/DOID via BMQExpander approach with a local LLM (Qwen2.5-14B). Add bge-reranker-v2-m3 cross-encoder on top-100 candidates. Expected improvement: +10–15% additional recall and significant NDCG improvement.

**Phase 4 (Month 3): Agentic layer + paper integration.** Implement Adaptive RAG routing for query complexity. Add CRAG-style retrieval evaluation. Index linked PubMed full-text chunks (section-aware, 200-token recursive). Build LightRAG knowledge graph from structured GEO metadata.

**Phase 5 (Month 4+): Feedback loop + fine-tuning.** Generate synthetic queries from GEO summaries for fine-tuning. Implement processability model from harmonization outcomes. Set up CI/CD evaluation with DeepEval quality gates.

---

## Conclusion

The GEO metadata search problem sits at a distinctive intersection: biomedical vocabulary complexity, mixed structured/unstructured data, multi-granularity hierarchies, and a recall-critical operating requirement. The most important architectural insight is that **hybrid retrieval (BM25 + contrastive-trained biomedical embeddings) with ontology-guided query expansion addresses the majority of search failures**—vocabulary mismatch from BM25 alone accounts for the largest recall gap, and ontology expansion recovers another 15–22% through synonym and hierarchical concept resolution. ColBERTv2 reranking, agentic multi-step retrieval, and graph-based approaches provide diminishing but meaningful returns on increasingly complex queries.

The infrastructure decision is straightforward for HPC: Qdrant's single-binary, unprivileged-container, native-hybrid-search design was effectively purpose-built for this deployment pattern. The evaluation design—semi-gold-standards from existing lab classifiers, TREC-style pooling with LLM pre-screening, and BrowseComp-Plus-inspired multi-faceted queries—provides the rigor needed to make confident architectural decisions. The most underexplored opportunity is the feedback loop from harmonization outcomes back to search ranking: treating downstream processing success as a training signal could close the gap between retrieval relevance and practical utility.

What remains genuinely unsolved is optimal handling of GEO's long tail: rare diseases, unusual organisms, and novel experimental techniques where neither keyword matching nor semantic similarity has sufficient training signal. Active learning from harmonization outcomes and community-contributed relevance judgments are the most promising paths forward, but neither has been validated at GEO scale.

---

## Further reading

- Grigoriadis D et al. "Public Omics Explorer (POE)." *Computational and Structural Biotechnology Journal*, 27:4802–4812, 2025.
- Jin Q et al. "MedCPT: Contrastive Pre-trained Transformers for Zero-shot Biomedical Information Retrieval." *Bioinformatics*, 2023.
- Santhanam K et al. "ColBERTv2: Effective and Efficient Retrieval via Lightweight Late Interaction." *NAACL*, 2022.
- Al Nazi Z et al. "BMQExpander: Ontology-Guided Query Expansion for Biomedical Document Retrieval." arXiv:2508.11784, 2025.
- Li Z et al. "WebThinker: Empowering Large Reasoning Models with Deep Research Capability." *NeurIPS*, 2025. arXiv:2504.21776.
- Guo Z et al. "LightRAG: Simple and Fast Retrieval-Augmented Generation." *EMNLP*, 2025. arXiv:2410.05779.
- Rivera A et al. "ModernBERT+ColBERTv2 for Biomedical RAG." arXiv:2510.04757, October 2025.
- Stuhlmann L et al. "Efficient and Reproducible Biomedical QA using RAG." *SDS*, 2025.
- Yan S et al. "Corrective Retrieval Augmented Generation." arXiv:2401.15884, 2024.
- Jeong S et al. "Adaptive-RAG." *NAACL*, 2024. arXiv:2403.14403.
- Chen M et al. "BrowseComp-Plus." arXiv:2508.06600, August 2025.
- Seedat N and van der Schaar M. "Matchmaker." *NeurIPS Workshop*, 2024. arXiv:2410.24105.
- Asai A et al. "Self-RAG: Learning to Retrieve, Generate, and Critique." *ICLR*, 2024. arXiv:2310.11511.
- Bruch S et al. "Analysis of Fusion Functions for Hybrid Retrieval." *ACM TOIS*, 2022.
- Diamantini C et al. "A Graph RAG Approach for Dataset Discovery." *Data Science and Engineering*, 11:30–52, 2026.
- Zhu Y et al. "GEOmetadb." *Bioinformatics*, 24(23):2798–2800, 2008.
- Wang Z, Lachmann A, Ma'ayan A. "Mining Data and Metadata from GEO." *Biophysical Reviews*, 11(1):103–110, 2019.
- Liu S, McCoy AB, Wright A. "RAG in Biomedicine: Systematic Review." *JAMIA*, 32(4):605–615, 2025.
- Sarthi P et al. "RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval." *ICLR*, 2024.
- Thakur N et al. "BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation." *NeurIPS*, 2021.
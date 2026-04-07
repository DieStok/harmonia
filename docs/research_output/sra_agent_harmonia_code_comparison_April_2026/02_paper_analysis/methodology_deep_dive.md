# Methodology Deep Dive: scBaseCount / SRAgent

---

## 1. How the Agentic Loop Works Step by Step

### 1.1 Overall Architecture (Section 2.2, Figure 2A/D, pages 4-6; Methods 5.1, page 12)

SRAgent uses a **hierarchical supervisor-worker architecture** built with LangGraph. The authors explicitly state that a single ReAct agent was insufficient for the full task (page 6: "the overall task for SRAgent and the number of tools required were too complicated for a single ReAct agent"). The hierarchy decomposes work into sub-tasks:

**Level 1 -- find-datasets agent (top-level supervisor):**
- Calls eSearch to discover new SRA datasets
- Delegates to the SRAgent agent for metadata extraction per dataset

**Level 2 -- SRAgent agent:**
- Orchestrates metadata extraction for a single SRX
- Can invoke sub-agents: entrez, ncbi_fetch, bigquery, tissue_ontology, disease_ontology

**Level 3 -- Entrez agent:**
- Further decomposes into tool-specific sub-agents: esearch, esummary, efetch, elink, sequences

**Level 4 -- Individual tool agents:**
- Each wraps a specific NCBI Entrez API tool or external tool (sra-stat, fastq-dump, BigQuery)

The key design principle is that **only the final result of a sub-agent is passed back to its supervisor**, reducing token consumption and task complexity for any given agent.

### 1.2 Execution Flow

1. **Discovery:** find-datasets agent queries SRA via eSearch for new datasets
2. **Metadata extraction:** For each SRX, the SRAgent agent:
   a. Obtains basic metadata (organism, platform) via Entrez tools
   b. Determines if the dataset is 10x Genomics scRNA-seq
   c. Extracts tissue information, maps to Uberon ontology via semantic search (ChromaDB vector DB) and ontology graph traversal
   d. Extracts disease information from author-supplied abstracts, maps to MONDO ontology
   e. Determines library preparation chemistry, cell vs nuclei type
3. **Storage:** All metadata is written to a GCP PostgreSQL database
4. **Processing handoff:** Identified 10x datasets are passed to scRecounter (separate Nextflow pipeline)

### 1.3 Asynchronous Execution

Sub-agents and tools are called **asynchronously** (page 4: "sub-agents and tools called asynchronously for increased parallelization"). This is a significant optimization for throughput, as many NCBI API calls can run in parallel.

### 1.4 scRecounter Pipeline (Section 2.3, Methods 5.2-5.5, pages 6-7, 13-14)

Post-SRAgent, the scRecounter Nextflow pipeline:
1. Detects 10x chemistry by testing first 1M reads against barcode sets (5', 3' v2, 3' v3, Multiome GEX)
2. Filters out datasets with <30% valid barcodes
3. Aligns all SRRs from an SRX with a single STARsolo run using standardized parameters
4. Generates 15 count matrices (5 feature annotations x 3 multi-mapping strategies) per SRX
5. Outputs h5ad format

## 2. LLM(s) Used and Configuration

### 2.1 Models

The paper does not explicitly state which LLM was used for the production runs of SRAgent. From the codebase (`settings.yml`), the configuration reveals:

- **Production environment:** Uses OpenAI models (the `prod` config references `gpt-5-mini` in the test config; the actual prod model is not visible in the settings file we examined)
- **Claude support:** A separate `claude` environment supports Anthropic models with configurable reasoning effort levels (low/medium/high thinking tokens)
- **Model per sub-agent:** The architecture allows different models per agent (esearch, efetch, metadata, tissue_ontology, etc.), all configurable in `settings.yml`

The paper mentions using "Claude Opus 4" for generating disease category cluster labels (Methods 5.1, page 13), but this appears to be a one-off use rather than the core agent LLM.

### 2.2 Configuration

- **Temperature:** 0.1 across all agents (from `settings.yml`)
- **Deployment:** GCP Cloud Run, 2 CPUs, 2 GB memory per job
- **Rate limiting:** Jobs triggered every 1-5 minutes, processing 3-5 datasets per run, peak 300 datasets/hour (to comply with NCBI API rate limits)

### 2.3 Profiling

The paper states that "LangSmith" was used for profiling SRAgent runs (Methods 5.1, page 12), suggesting detailed trace data exists but is not presented in the paper.

## 3. Tools Available to the Agent

The agent has access to the following tools, organized by sub-agent (Figure 2D, page 6; README):

| Sub-agent | Tools |
|-----------|-------|
| esearch | NCBI eSearch API |
| esummary | NCBI eSummary API |
| efetch | NCBI eFetch API |
| elink | NCBI eLink API |
| sequences | sra-stat, fastq-dump (direct sequence data access) |
| ncbi_fetch | NCBI HTML scraping |
| bigquery | SRA BigQuery |
| tissue_ontology | ChromaDB vector search over Uberon ontology, OLS (Ontology Lookup Service) |
| disease_ontology | MONDO ontology graph traversal, spectral clustering |
| papers | DOI resolution, manuscript download from preprint servers, CORE, Europe PMC, Unpaywall |

### Tool Selection

The agent decides which tools to use through the **ReAct paradigm** (reasoning + acting). Each agent has a defined set of available tools and uses LLM reasoning to determine which to call next based on the task and accumulated context. The hierarchical structure constrains which tools are visible to each agent level.

## 4. Evaluation Approach and Metric Appropriateness

### 4.1 Metadata Accuracy Evaluation

**Tissue labels (Figure 2E, page 6):** Compared SRAgent annotations to CZ CELLxGENE annotations for shared datasets. This is a reasonable proxy but not a gold standard -- CZ CELLxGENE annotations are themselves manually curated and could contain errors.

**Disease labels (Figure 2F, page 6):** Compared SRAgent abstract-derived disease labels to CZ CELLxGENE cell-level disease annotations. The authors correctly note these are not directly comparable (study-level vs. cell-level labels), making this a weak validation.

**Organism classification (Methods 5.7, page 14):** Used SRA BigQuery as ground truth. The authors note that xenograft datasets are inherently ambiguous (SRA constrains "organism" to a single value).

### 4.2 Analytical Confounder Evaluation

**Silhouette scoring (Section 2.5, Figure 4A-B, pages 9-10):** Measures how well cells cluster by metadata categories. Higher scores for biological factors (tissue) and lower scores for technical factors (chemistry, sample ID) indicate better harmonization. This is an appropriate metric for batch effect quantification, using the established `scib_metrics` package.

### 4.3 AI Model Evaluation

**Classification probing (Section 2.6, Figure 4C, pages 9-11):** Trains simple MLP probes on cell embeddings to classify cell type, disease, and perturbation. This is a standard approach for evaluating embedding quality. However:
- Only two-layer MLPs with ReLU activation are used
- Training is only 5 epochs
- 80/10/10 train/val/test split

**DEG prediction (Section 2.6, Figure 4D, pages 9-11):** Uses AUROC and AUPRC to evaluate differential gene expression prediction from model reconstructions. This is a meaningful biological metric that tests whether the model captures gene-level perturbation effects.

### 4.4 Cell Type Annotation Validation

**Marker gene recovery (Section 2.4, Figure 3C, page 8):** Compares recovery of PanglaoDB marker genes in top 200 DEGs per cell type, using t-test. This is an independent validation since PanglaoDB markers were not used in the classifier. The comparison against Tabula Sapiens provides a meaningful baseline.

## 5. Computational Cost

### 5.1 SRAgent

| Metric | Value | Source |
|--------|-------|--------|
| Datasets processed | 208,939 | Section 2.2, page 6 |
| Total token usage | 13.2 x 10^12 tokens | Section 2.2, page 6 |
| Estimated cost | $17,000 | Section 2.2, page 6 |
| Mean time per dataset | 80 seconds | Methods 5.1, page 12 |
| Human-equivalent time | 3,482 hours (145 days) | Section 2.2, page 6 |
| CPU hours saved (pre-filtering) | >500,000 | Section 2.2, page 6 |
| Deployment resources | 2 CPUs, 2 GB RAM per job | Methods 5.1, page 12 |

### 5.2 scRecounter

| Metric | Value | Source |
|--------|-------|--------|
| Total reads mapped | 13.8 x 10^12 | Section 2.3, page 6 |
| SRX entries reprocessed | 61,381 | Section 2.1, page 4 |
| Count matrices per SRX | 15 | Methods 5.5, page 14 |

### 5.3 AI Model Training

| Metric | Value | Source |
|--------|-------|--------|
| Model parameters | 108 million | Methods 5.9, page 15 |
| GPUs | 4 | Methods 5.9, page 15 |
| Effective batch size | 3,072 | Methods 5.9, page 15 |
| Training steps | 100,000 | Methods 5.9, page 15 |
| scBaseCount training cells | 214 million (human only) | Methods 5.9, page 15 |
| CZ CELLxGENE training cells | 134 million | Methods 5.9, page 15 |

**Note on token cost:** The reported 13.2 trillion tokens at $17,000 implies an average cost of approximately $1.29 per million tokens, which is consistent with GPT-4o-mini or similar budget-tier models rather than frontier models. This is not explicitly stated in the paper.

## 6. Reproducibility Assessment

### 6.1 What Is Provided

**Strengths:**
- Code for SRAgent and scRecounter is publicly available on GitHub (ArcInstitute/SRAgent, ArcInstitute/scRecounter)
- Analysis code is available (ArcInstitute/scBaseCount_analysis)
- Data is available on Google Cloud Storage (gs://arc-ctc-scBaseCount/2025-02-25)
- STARsolo parameters are fully specified (Methods 5.5, page 13-14)
- Reference genome preparation is described (Methods 5.4, page 13)
- Model training hyperparameters are specified (Methods 5.9, page 15)

### 6.2 Reproducibility Gaps

**LLM model not specified:** The paper does not state which specific LLM was used for production SRAgent runs. The settings.yml in the codebase references `gpt-5-mini` for the test environment but the production model is not documented in the paper. This is a significant reproducibility concern since:
- Different LLMs would produce different metadata extraction accuracy
- Token costs depend heavily on the model
- The claimed $17,000 cost cannot be verified without knowing the model

**Prompts not provided:** The system prompts and agent instructions for each sub-agent are embedded in the code but not documented in the paper. Reproducing the metadata extraction quality requires running the exact same code with the same LLM.

**LangSmith traces not shared:** The paper mentions using LangSmith for profiling but does not share traces, making it impossible to verify token counts or examine agent reasoning patterns.

**GCP infrastructure specifics:** The pipeline depends on GCP Cloud Run, GCP Batch, and GCP PostgreSQL. Reproducing at scale requires similar cloud infrastructure.

**No error rate quantification:** The paper shows qualitative comparisons of metadata accuracy (Figures 2E-F) but does not provide precision/recall/F1 scores for metadata extraction. Without quantitative error rates, it is impossible to assess whether a reproduction achieves comparable quality.

**Evaluation dataset specifics:** The exact random seeds, cell subsampling procedures, and train/test splits for AI model evaluation are partially described but not fully reproducible (e.g., "random samples" without seed specification).

**ChromaDB vector database:** The Uberon ontology vector database construction is described at a high level but embedding model, chunk size, and similarity threshold are not specified.

### 6.3 Overall Reproducibility Rating

**Partial reproducibility.** The code and data are available, which is commendable. However, the unspecified LLM model, missing prompts in the paper, lack of quantitative metadata accuracy metrics, and cloud infrastructure dependencies mean that reproducing the full pipeline and matching reported results would require significant reverse-engineering of the codebase and access to similar cloud resources. The scRecounter pipeline is more reproducible than SRAgent due to its deterministic nature (STARsolo with fixed parameters).

---

## Completeness Assessment

This analysis covers the agentic architecture (Section 2.2, Figure 2A/D), the processing pipeline (Section 2.3, Methods 5.2-5.5), the LLM configuration (from both paper and codebase), all tools (from paper and README), all four evaluation approaches (metadata, silhouette scores, AI probing, marker genes), computational costs (Sections 2.2-2.3, 2.6), and reproducibility across all methods sections (5.1-5.11). The main gap in this analysis is that we could not inspect the actual agent prompt templates in the codebase in detail (files in `SRAgent/agents/`) -- the architecture is inferred from the paper, README, and directory structure. The token cost calculation ($1.29/M tokens) is derived but not verified against a specific model's pricing.

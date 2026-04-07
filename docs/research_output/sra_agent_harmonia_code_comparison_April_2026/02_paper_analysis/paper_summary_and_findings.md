# Paper Summary and Findings: scBaseCount

**Paper:** scBaseCount: an AI agent-curated, uniformly processed, and autonomously updated single cell data repository
**Authors:** Nicholas D. Youngblut, Christopher Carpenter, Arshia Nayebnazar, Abhinav Adduri, Rohan Shah, et al. (Arc Institute)
**Preprint:** bioRxiv 2025.02.27.640494 (posted November 2, 2025)
**License:** CC-BY 4.0

---

## 1. Problem Statement

Single-cell RNA sequencing (scRNA-seq) has generated vast amounts of data deposited in the NIH Sequence Read Archive (SRA), but this data remains largely underutilized for two reasons (Section 1, pages 2-3):

1. **Unstandardized metadata:** SRA metadata is inconsistently formatted, making systematic discovery of single-cell datasets difficult. Existing curated repositories (CZ CELLxGENE, Human Cell Atlas) rely on manual curation of contributed datasets, limiting their scale and diversity.

2. **Analytical variability from heterogeneous processing:** Different labs use different alignment tools, reference genomes, and read counting strategies, introducing technical confounders that complicate cross-study comparisons and AI model training.

The paper argues that AI foundation models for cell biology require larger, more diverse, and more uniformly processed training data than what current manually curated repositories can provide.

## 2. Proposed Approach

The system has two main components:

### 2a. SRAgent -- AI-Driven Dataset Discovery and Metadata Extraction (Section 2.2, pages 4-6)

- A hierarchical agentic workflow built with **LangGraph** around LLMs and specialized bioinformatics tools
- Uses **ReAct agents** (Yao et al., 2022) in a **supervisor-worker architecture**
- Tools include: eSearch, eSummary, eFetch, eLink, NCBI HTML scraping, SRA BigQuery, sra-stat, and fastq-dump
- Deployed on GCP Cloud Run (2 CPUs, 2 GB memory per job)
- Processes 3-5 datasets per run, triggered every 1-5 minutes, peak rate of 300 datasets/hour
- Mean processing time per dataset: 80 seconds
- Extracts metadata including: organism, tissue, disease, 10x chemistry, cell vs nuclei suspension type
- Uses ChromaDB vector database for tissue ontology matching (Uberon) and MONDO disease ontology
- Metadata stored in a GCP SQL (PostgreSQL) database

### 2b. scRecounter -- Standardized Data Processing Pipeline (Section 2.3, pages 6-7)

- A **Nextflow** pipeline for scalable reprocessing of scRNA-seq data
- Uses **STARsolo** for alignment with standardized parameters
- Automated 10x chemistry detection (tests 5', 3' v2, 3' v3, Multiome GEX barcodes)
- Generates **15 count matrices per SRX dataset** across 5 feature annotation strategies (Gene, GeneFull, GeneFull_ExonOverIntron, GeneFull_Ex50pAS, Velocyto) and 3 multi-mapping strategies (Unique, Uniform, EM)
- Runs on GCP Cloud Run with GCP Batch for compute
- Reference genomes for 27 organisms prepared with consistent gene model filtering

## 3. Key Contributions

1. **Largest public single-cell repository:** 502 million cells from 61,381 reprocessed SRX entries across 27 organisms and 75 tissues (Figure 1A, page 3)
2. **First AI-agent-curated biological data repository:** Automated discovery, metadata extraction, and continuous updating via SRAgent
3. **Uniform processing eliminates analytical confounders:** Demonstrated via silhouette scoring comparisons with CZ CELLxGENE (Section 2.5, Figure 4A-B, pages 9-10)
4. **Largest resource of non-coding transcriptomic data at single-cell resolution:** Intronic counts enable RNA velocity analysis at unprecedented scale
5. **Improved AI model training:** State embedding models trained on scBaseCount outperform those trained on CZ CELLxGENE (Section 2.6, Figure 4C-D, pages 9-11)

## 4. Experimental Setup

### Benchmarks and Datasets
- **Metadata validation:** Compared SRAgent tissue/disease annotations against CZ CELLxGENE annotations for shared datasets (Figure 2E-F, page 6)
- **Analytical confounder analysis:** Silhouette scoring on random subsets of 250,000 cells from both scBaseCount and CZ CELLxGENE (Figure 4A-B, page 10)
- **Cell type annotation validation:** Compared marker gene recovery against PanglaoDB (Figure 3C, page 8)
- **AI model evaluation:** Trained 108M parameter State Embedding models on scBaseCount (214M human cells) and CZ CELLxGENE (134M human cells) (Section 5.9, page 15)

### Evaluation Tasks for AI Models (Section 2.6, pages 9-11)
- Cell type classification using Tabula Sapiens (24 donors, 180 cell types)
- Disease classification using COVID-19 datasets (Ravindra et al., van der Wijst et al., Wu et al.)
- Perturbation classification using CRISPRi screens (Replogle et al., Nadig et al.; 2024 essential genes across 4 cell lines)
- Differential gene expression prediction from model reconstructions (AUROC, AUPRC)

### Baselines
- CZ CELLxGENE (123 million cells, manually curated)
- Human Cell Atlas (65 million cells)
- Comparison is primarily scBaseCount vs. CZ CELLxGENE for AI model training

## 5. Main Results

### Scale (Figure 1A, page 3)
- 502 million cells (vs. 123M in CZ CELLxGENE, 65M in Human Cell Atlas)
- 27 organisms (vs. fewer in CZ CELLxGENE)
- 75 tissues
- 208,939 SRA experiments processed, 105,343 identified as 10x Genomics

### SRAgent Performance (Section 2.2, pages 4-6)
- Processed 208,939 datasets at estimated cost of **$17,000** and **13.2 trillion tokens**
- Estimated 145 human-days saved for metadata extraction alone
- Estimated >0.5M CPU hours saved by pre-filtering non-10x datasets
- Tissue label accuracy: "most cases" correctly matched CZ CELLxGENE labels (Figure 2E, Table S4)
- Disease label accuracy: Successfully identified studied disease for all datasets with diseased cells in CZ CELLxGENE (Figure 2F)

### Reduced Analytical Confounders (Section 2.5, Figure 4A-B, pages 9-10)
- Technical factors (library chemistry, suspension type, sample ID) show lower silhouette scores relative to tissue type in scBaseCount compared to CZ CELLxGENE
- Better integration of single-cell and single-nucleus datasets due to consistent exonic+intronic counting

### AI Model Training (Section 2.6, Figure 4C-D, pages 9-11)
- Cell type classification: ~90% accuracy for both, modest improvement for scBaseCount-trained model
- Infection status classification: **+2.24%** improvement
- Perturbation group classification: **+23.9%** improvement
- DEG prediction: **+10.2% AUROC** and **+17.2% AUPRC** improvement

## 6. Ablation Studies

The paper does not include formal ablation studies in the traditional sense. However, several analyses decompose contributing factors:

- **Feature annotation strategies** (Section 2.3, Figure 2C): Five different counting approaches (Gene, GeneFull, etc.) compared conceptually but not quantitatively ablated
- **Multi-mapping strategies** (Section 2.3): Three strategies (Unique, Uniform, EM) offered as options but not ablated against each other
- **Silhouette score decomposition** (Section 2.5, Figure 4A-B): Breaks down contributions of tissue type, sample ID, chemistry, and suspension type to clustering
- **Cell type validation** (Section 2.4, Figure 3C): Marker gene recovery compared between scBaseCount and Tabula Sapiens

There is no ablation separating the effect of dataset size from uniform processing on AI model performance, nor an ablation testing different LLMs for SRAgent.

## 7. Limitations Acknowledged by the Authors (Section 3, pages 11-12)

1. **Cell-level annotation gaps:** Cell type annotation, perturbation labels, and donor information are not accessible through SRA metadata and require manual or reference-based approaches
2. **Platform restriction:** Currently limited to 10x Genomics on Illumina sequencers; other library preparation chemistries and sequencing technologies not yet supported
3. **Access limitations:** Restricted to publicly accessible datasets; controlled-access data requires manual author engagement
4. **Future extension needed:** Plans to expand scRecounter for additional single-cell technologies, multi-omic measurements, and spatial transcriptomics

---

## Completeness Assessment

This summary covers all major sections of the paper (Introduction, Results 2.1-2.6, Discussion, and Methods 5.1-5.11). The paper is 20 pages of main text plus 7 pages of supplementary figures and tables (27 pages total). Key quantitative claims are referenced with specific figure/table numbers and page numbers. The paper does not report formal ablation studies, statistical significance tests (e.g., p-values or confidence intervals) for AI model comparisons, or per-category breakdowns of metadata accuracy. These gaps are noted and analyzed further in the companion critique document.

# Adversarial Review: scBaseCount Paper

---

## 1. Methodological Gaps

### 1.1 Confounding Variables in AI Model Comparison

The headline AI model comparison (Section 2.6, Figure 4C-D) suffers from multiple confounds:

- **Dataset size is not controlled:** scBaseCount provides 214M human cells vs. CZ CELLxGENE's 134M cells for training (Methods 5.9, page 15). The authors train for a fixed number of optimization steps (100,000) rather than epochs, which partially addresses this, but does not fully decouple the effect of dataset size from dataset quality. A model trained on 214M cells from CZ CELLxGENE (if available) would be the proper control.

- **Gene set standardization may disadvantage CZ CELLxGENE:** Both datasets are restricted to 19,790 human protein-coding genes (Methods 5.9, page 15). CZ CELLxGENE datasets may have been processed with different gene sets originally, and restricting to this common set could differentially affect the two datasets.

- **No cross-validation or confidence intervals:** The AI model results (Figure 4C-D) show single-point comparisons without error bars, confidence intervals, or statistical significance tests. The +2.24% improvement for infection status could easily be within random variation. Only the +23.9% perturbation improvement and DEG metrics (+10.2% AUROC) appear potentially significant, but this cannot be verified without variance estimates.

- **Data overlap not fully addressed:** The paper states Tabula Sapiens was excluded from both training sets (Methods 5.9, page 15), but does not discuss whether COVID-19 datasets or Replogle perturbation datasets might partially overlap with the training data through SRA mining.

### 1.2 Fairness of Baselines

- **CZ CELLxGENE is not a processing pipeline -- it is a repository.** Comparing "scBaseCount processing" vs. "CZ CELLxGENE processing" (Section 2.5) is comparing uniform reprocessing against a heterogeneous collection of author-submitted processed data. This is not a fair comparison of processing approaches; it is a comparison of "uniform pipeline" vs. "no pipeline." The appropriate baseline would be to reprocess the same raw data with an alternative uniform pipeline (e.g., CellRanger with default settings).

- **No comparison against simpler metadata extraction methods.** SRAgent is compared against no baseline for metadata extraction. Simple regex-based parsing of SRA metadata fields, or keyword matching, could serve as a lower-bound baseline. Without this, the value-add of the LLM-based approach is unclear.

### 1.3 Selection Bias

- **10x Genomics only:** The restriction to 10x Genomics datasets (Section 2.1) introduces a platform selection bias. The paper acknowledges this (Discussion, page 12) but does not quantify what fraction of scRNA-seq data in SRA uses non-10x platforms.

- **Illumina only:** Further restricted to Illumina sequencers, excluding emerging platforms.

- **>30% valid barcodes filter:** Datasets with <30% valid barcodes are excluded (Methods 5.3, page 13). The paper does not report how many datasets were lost at this filtering step, or whether this introduces systematic bias (e.g., against older or lower-quality datasets).

### 1.4 Generalization Claims

The paper claims scBaseCount is "a blueprint for how AI can be leveraged to curate and autonomously update large biological data repositories" (Abstract, page 1). This is a strong generalization claim from a single application domain (10x scRNA-seq). The agent architecture and tool set are highly specific to SRA/NCBI tools, and generalization to other data types (proteomics, imaging, clinical) is not demonstrated.

## 2. Evaluation Weaknesses

### 2.1 Metadata Accuracy Metrics Are Qualitative, Not Quantitative

The tissue label comparison (Figure 2E, page 6) shows a heatmap of SRAgent vs. CZ CELLxGENE labels but does not report precision, recall, F1, or accuracy numbers. The statement that "in most cases, the agent accurately extracted the correct tissue labels" (page 6) is vague. Key questions:

- What is the error rate?
- Which tissue types are most commonly misclassified?
- How does accuracy degrade for less common tissues or organisms?

The disease label validation (Figure 2F, page 6) is even weaker: it uses CZ CELLxGENE cell-level annotations as a proxy for study-level labels, which the authors themselves acknowledge are not directly comparable.

### 2.2 Organism Classification Accuracy

The paper mentions evaluating organism classification accuracy using SRA BigQuery as ground truth (Methods 5.7, page 14) and notes that "many were xenografts, so mis-classification was somewhat due to the constraint in SRA that organism must be a single value." However, the accuracy numbers are not reported in the main text. This is a critical omission for a system claiming to automate metadata extraction.

### 2.3 Silhouette Score Interpretation

The silhouette score analysis (Section 2.5, Figure 4A-B, page 10) uses random subsets of 250,000 cells. While the methodology is sound, several concerns arise:

- **Normalization to tissue score:** Technical factor silhouette scores are "normalized to the mean tissue score for each dataset" (Figure 4 caption, page 10). This means the absolute values of technical confounders are not shown, only their ratio to tissue signal. If both technical and biological signals are weak in scBaseCount, the ratio could look favorable while the absolute data quality is poor.

- **Downsampling strategy differs:** CZ CELLxGENE subsets are drawn from 20 individual human datasets, while scBaseCount subsets are randomly sampled from human and mouse accessions. This difference in sampling strategy could itself introduce confounds.

### 2.4 No Held-Out Metadata Test Set

There is no systematic held-out evaluation of SRAgent's metadata extraction. The comparisons against CZ CELLxGENE are post-hoc analyses on overlapping datasets, not a prospective evaluation on unseen data. A proper evaluation would hold out a set of datasets with expert-annotated ground truth and measure extraction accuracy.

### 2.5 Cell Type Annotation Quality

The cell type annotation approach (Section 2.4, Methods 5.11, pages 7-8, 16) uses logistic regression on State embeddings trained on Tabula Sapiens per tissue. This approach:

- **Assumes one tissue per sample,** which is stated (page 16) but not validated
- **Relies on SRAgent tissue labels** for routing to the correct tissue-specific classifier, creating a dependency chain where tissue misclassification cascades into cell type misclassification
- **Limited to 24 Tabula Sapiens tissues and 143 cell types** (page 16), which may not cover the full diversity of scBaseCount
- **Omits samples with mean UMI <= 100 and "other" tissue** (page 16) -- the fraction of omitted samples is not reported

## 3. Unaddressed Questions

### 3.1 Failure Modes Not Analyzed

- **Agent failure rate:** How often does SRAgent fail to extract metadata for a dataset? What are the failure modes (API timeout, LLM hallucination, ambiguous metadata)?
- **Incorrect metadata propagation:** If SRAgent assigns an incorrect tissue label, this cascades through cell type annotation and silhouette scoring. The error propagation chain is not analyzed.
- **Edge cases:** How does the agent handle multi-tissue experiments, pooled samples, xenograft samples, or datasets with minimal metadata?

### 3.2 Cost-Effectiveness Analysis

The paper reports $17,000 for 208,939 datasets (Section 2.2, page 6), or approximately $0.08 per dataset. However:

- No comparison to the cost of manual curation (the 145 human-days estimate assumes 1 dataset/minute, which is likely conservative for metadata extraction but may be liberal for expert annotation)
- No breakdown of cost by agent/tool (which sub-agents consume the most tokens?)
- No analysis of cost trends as the model context grows with more complex datasets

### 3.3 Performance with Weaker/Different Models

The paper does not evaluate SRAgent with different LLMs. Given the configurable model settings in the codebase, questions include:
- How much does metadata accuracy degrade with cheaper models?
- Could a smaller, fine-tuned model replace the general-purpose LLM?
- What is the minimum model capability required for acceptable performance?

### 3.4 Hallucination and Calibration

LLMs are known to hallucinate. The paper does not:
- Measure hallucination rates in metadata extraction
- Report confidence calibration of agent outputs
- Describe any guardrails against fabricated metadata
- Analyze cases where SRAgent extracts plausible but incorrect information

### 3.5 Temporal Robustness

SRAgent is designed for continuous operation. The paper does not address:
- What happens when NCBI API formats change?
- How robust is the agent to changes in SRA metadata conventions over time?
- What happens when the underlying LLM is updated (API model versions change)?

## 4. Missing Comparisons

### 4.1 Alternative Metadata Extraction Approaches

- **No comparison to rule-based extraction:** Simple regex, keyword matching, or structured queries on SRA metadata fields could serve as baselines
- **No comparison to fine-tuned models:** A BERT-based classifier fine-tuned on SRA metadata could potentially achieve similar accuracy at lower cost
- **No comparison to existing tools:** Tools like SRAdb, pysradb, or ffq already extract SRA metadata programmatically -- how does SRAgent compare?

### 4.2 Alternative Uniform Processing Pipelines

- **No comparison to CellRanger:** The most widely used 10x processing tool is not used as a baseline for processing quality
- **No comparison to alevin-fry or kallisto-bustools:** Alternative lightweight scRNA-seq quantification tools
- **No comparison to CELLxGENE Census reprocessing efforts:** CZ CELLxGENE has its own standardization efforts that are not discussed

### 4.3 Related AI Agents for Biological Data

- **CellAgent** (Xiao et al., 2024) is cited but not compared as a system -- only for cell type annotation
- **No comparison to BioGPT, Galactica, or other domain-specific LLMs** for metadata extraction
- **No comparison to RAG-based approaches** that could retrieve relevant metadata without an agentic loop

### 4.4 Cross-Species Model Training

The paper trains AI models on human cells only (Methods 5.9, page 15), despite scBaseCount's claimed advantage in species diversity. The cross-species benefit is cited from prior work (Rosen et al., 2023; Pearce et al., 2025) but not demonstrated with scBaseCount data.

## 5. Reproducibility Concerns

### 5.1 LLM Model Identity

The specific LLM used for production runs is **not stated in the paper**. This is perhaps the most critical reproducibility concern. The entire SRAgent pipeline's performance is dependent on the LLM, yet the reader cannot determine which model was used, making all claims about metadata accuracy, cost, and token usage unverifiable.

### 5.2 Prompt Engineering

Agent prompts are embedded in the codebase but not documented in the paper or supplementary materials. Given the sensitivity of LLM-based systems to prompt wording, this is a significant reproducibility gap.

### 5.3 Exact Evaluation Procedures

- Random seeds for cell subsampling are not specified
- The "approximately 50,000 cells" and "approximately 500,000 cells" sampling procedures (Methods 5.11, pages 7, 16) introduce ambiguity
- The specific CZ CELLxGENE version/snapshot used is not specified (it is continuously updated)

### 5.4 Infrastructure Dependencies

- GCP Cloud Run, GCP Batch, GCP PostgreSQL
- NCBI API rate limits may change
- ChromaDB vector database construction details (embedding model, parameters) not specified

### 5.5 Version Dependencies

The codebase `settings.yml` references `gpt-5-mini` (a model that was not available at the paper's initial submission in February 2025), suggesting the codebase has been updated since the paper's experiments were run. This version mismatch makes it unclear which code version corresponds to the paper's results.

## 6. Strength Acknowledgment

### 6.1 Genuine Contributions

1. **Scale is impressive.** 502 million cells across 27 organisms is a genuine step change in publicly available single-cell data. The engineering effort to mine, process, and host this data is substantial and valuable to the community regardless of methodological concerns.

2. **Open data and code.** Making SRAgent, scRecounter, analysis code, and the full dataset publicly available (Google Cloud Storage, GitHub) sets a high standard for reproducibility in resource papers.

3. **Practical utility of uniform processing.** The silhouette score analysis (Figure 4A-B) convincingly demonstrates that heterogeneous processing introduces batch effects, and uniform reprocessing mitigates them. This is a practical insight with immediate value.

4. **Intronic counts at scale.** Providing both exonic and intronic counts for all cells enables RNA velocity analysis at unprecedented scale. This is a genuine unique contribution not available from other repositories.

5. **Multiple count matrix options.** Generating 15 count matrices per dataset (5 annotations x 3 multi-mapping strategies) gives users flexibility and is more thorough than alternatives.

6. **Hierarchical agent design is well-motivated.** The observation that a single agent cannot handle the full task, and the decomposition into supervisor-worker architecture with result-only communication, is a sound engineering decision that other agentic systems can learn from.

7. **SRA composition analysis.** The descriptive analysis of SRA composition trends (Figures 1D-I) -- chemistry dominance, species trends, disease category shifts over time -- provides genuine community value as a "census" of publicly available single-cell data.

### 6.2 Most Promising Aspects

- **Continuous updating model:** The autonomous, continuously running agent that discovers and processes new data as it appears in SRA is the most forward-looking aspect. If maintained, this could provide an always-current view of single-cell data availability.
- **AI model training improvements:** The DEG prediction improvements (+10.2% AUROC, +17.2% AUPRC) for perturbation biology are the most scientifically meaningful results, as they directly demonstrate utility for virtual cell modeling.
- **Blueprint for other domains:** Despite the generalization critique above, the architectural pattern (agent discovery -> metadata extraction -> uniform processing -> structured storage) is genuinely reusable for other biological data types.

---

## Completeness Assessment

This critique covers all six requested dimensions: methodological gaps (5 issues), evaluation weaknesses (5 issues), unaddressed questions (5 areas), missing comparisons (4 categories), reproducibility concerns (5 issues), and strength acknowledgment (7 strengths + 3 promising aspects). All claims are grounded in specific sections, figures, and page numbers from the paper. The critique does not cover the supplementary tables (S1-S4) in detail since their content is summarized in the main text. The code-level analysis is limited to the directory structure, settings.yml, and eval.py rather than a full codebase audit -- a deeper code review might reveal additional reproducibility details (e.g., exact prompts, error handling logic) that could address some concerns raised here.

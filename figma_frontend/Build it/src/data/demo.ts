export const DISEASE = {
  name: "Amyotrophic Lateral Sclerosis",
  shortName: "ALS",
  ontologyId: "MONDO:0004976",
  description: "A progressive neurodegenerative disease affecting motor neurons in the brain and spinal cord.",
};

export type EvidenceScore = "strong" | "moderate" | "weak" | "none" | "unchecked" | "contradiction";

export interface EvidenceDimension {
  id: string;
  label: string;
  description: string;
}

export const EVIDENCE_DIMENSIONS: EvidenceDimension[] = [
  { id: "genetic", label: "Genetic", description: "GWAS, rare variant, familial evidence" },
  { id: "clinical", label: "Clinical", description: "ClinVar, clinical trial associations" },
  { id: "functional", label: "Functional", description: "In vitro and in vivo functional studies" },
  { id: "literature", label: "Literature", description: "PubMed co-mention and mechanistic evidence" },
  { id: "druggability", label: "Druggability", description: "Pharos, ChEMBL tractability assessment" },
  { id: "safety", label: "Safety", description: "Essentiality, toxicity, off-target risk" },
  { id: "expression", label: "Expression", description: "Baseline and differential expression" },
  { id: "ppi", label: "PPI", description: "Protein–protein interaction network centrality" },
  { id: "pathway", label: "Pathway", description: "Reactome, KEGG pathway involvement" },
  { id: "animal", label: "Animal Model", description: "Transgenic or knockout model phenotypes" },
  { id: "biomarker", label: "Biomarker", description: "CSF/blood biomarker evidence" },
];

export interface Target {
  id: string;
  symbol: string;
  fullName: string;
  priorityScore: number;
  tier: "HIGH" | "MEDIUM" | "LOW";
  evidenceStrength: "HIGH" | "MEDIUM" | "LOW";
  consistency: "HIGH" | "MEDIUM" | "LOW";
  maturity: "HIGH" | "MEDIUM" | "LOW";
  translationalOpportunity: string;
  selectionSource: string;
  mainGap: string;
  cautionFlags: string[];
  evidence: Record<string, { score: EvidenceScore; value: number; records: number; source: string }>;
  whyRanked: string;
  geneticContribution: number;
  literatureContribution: number;
  clinicalContribution: number;
}

export const TARGETS: Target[] = [
  {
    id: "SOD1",
    symbol: "SOD1",
    fullName: "Superoxide Dismutase 1",
    priorityScore: 87,
    tier: "HIGH",
    evidenceStrength: "HIGH",
    consistency: "HIGH",
    maturity: "HIGH",
    translationalOpportunity: "Direct Therapeutic Target",
    selectionSource: "Familial ALS panel + GWAS meta-analysis",
    mainGap: "Long-term safety of SOD1 suppression in non-ALS neurons",
    cautionFlags: [],
    geneticContribution: 38,
    literatureContribution: 28,
    clinicalContribution: 21,
    whyRanked: "SOD1 has the longest and most replicated causal evidence chain in ALS biology. Pathogenic variants cause ~20% of familial ALS cases. Multiple human clinical trials with antisense oligonucleotides demonstrate measurable CSF biomarker reduction. Evidence is highly consistent across genetic, functional, animal model, and clinical dimensions.",
    evidence: {
      genetic: { score: "strong", value: 94, records: 312, source: "ClinVar, gnomAD, OMIM" },
      clinical: { score: "strong", value: 88, records: 47, source: "ClinicalTrials.gov, PubMed" },
      functional: { score: "strong", value: 91, records: 203, source: "PubMed functional studies" },
      literature: { score: "strong", value: 96, records: 2840, source: "PubMed co-mention" },
      druggability: { score: "strong", value: 85, records: 18, source: "Pharos, ChEMBL" },
      safety: { score: "moderate", value: 62, records: 9, source: "Safety databases, literature" },
      expression: { score: "strong", value: 87, records: 6, source: "GTEx, FANTOM5" },
      ppi: { score: "moderate", value: 71, records: 88, source: "STRING v12" },
      pathway: { score: "strong", value: 83, records: 14, source: "Reactome, KEGG" },
      animal: { score: "strong", value: 92, records: 31, source: "MGI, PubMed" },
      biomarker: { score: "strong", value: 79, records: 22, source: "ALS clinical trials" },
    },
  },
  {
    id: "TARDBP",
    symbol: "TARDBP",
    fullName: "TAR DNA-Binding Protein 43 (TDP-43)",
    priorityScore: 74,
    tier: "HIGH",
    evidenceStrength: "HIGH",
    consistency: "MEDIUM",
    maturity: "MEDIUM",
    translationalOpportunity: "Mechanistic Target — Requires Modality Development",
    selectionSource: "Neuropathology consensus + GWAS signals",
    mainGap: "Optimal therapeutic modality for TDP-43 pathology remains unclear",
    cautionFlags: ["TDP-43 is essential for RNA splicing; global loss-of-function interventions carry high risk"],
    geneticContribution: 29,
    literatureContribution: 31,
    clinicalContribution: 14,
    whyRanked: "TDP-43 cytoplasmic aggregation is the defining neuropathological hallmark in ~97% of sporadic ALS cases. Genetic variants in TARDBP cause ~5% of familial ALS. However, TDP-43 is essential for RNA splicing, creating a significant therapeutic challenge. Evidence is strong but consistency is reduced by contradictory functional findings.",
    evidence: {
      genetic: { score: "strong", value: 81, records: 148, source: "ClinVar, ALS databases" },
      clinical: { score: "moderate", value: 58, records: 12, source: "ClinicalTrials.gov" },
      functional: { score: "strong", value: 88, records: 412, source: "PubMed" },
      literature: { score: "strong", value: 94, records: 3210, source: "PubMed" },
      druggability: { score: "weak", value: 41, records: 6, source: "Pharos" },
      safety: { score: "none", value: 0, records: 0, source: "Not assessed" },
      expression: { score: "strong", value: 84, records: 6, source: "GTEx" },
      ppi: { score: "strong", value: 82, records: 142, source: "STRING v12" },
      pathway: { score: "strong", value: 79, records: 18, source: "Reactome" },
      animal: { score: "strong", value: 86, records: 44, source: "MGI" },
      biomarker: { score: "moderate", value: 61, records: 8, source: "ALS biomarker studies" },
    },
  },
  {
    id: "FUS",
    symbol: "FUS",
    fullName: "FUS RNA Binding Protein",
    priorityScore: 68,
    tier: "HIGH",
    evidenceStrength: "MEDIUM",
    consistency: "MEDIUM",
    maturity: "MEDIUM",
    translationalOpportunity: "Mechanistic Target — Early Stage",
    selectionSource: "Familial ALS panel",
    mainGap: "Mechanistic distinction from TDP-43 pathology; population-level prevalence underestimated",
    cautionFlags: [],
    geneticContribution: 26,
    literatureContribution: 24,
    clinicalContribution: 18,
    whyRanked: "Pathogenic FUS variants cause ~4% of familial ALS and FUS mislocalization parallels TDP-43 pathology. Evidence is consistent across genetic and functional dimensions, but druggability remains poorly characterized and clinical trial data is absent.",
    evidence: {
      genetic: { score: "strong", value: 78, records: 89, source: "ClinVar" },
      clinical: { score: "none", value: 0, records: 0, source: "No trials identified" },
      functional: { score: "moderate", value: 67, records: 198, source: "PubMed" },
      literature: { score: "strong", value: 82, records: 1420, source: "PubMed" },
      druggability: { score: "weak", value: 38, records: 4, source: "Pharos" },
      safety: { score: "unchecked", value: 0, records: 0, source: "Not yet assessed" },
      expression: { score: "moderate", value: 66, records: 6, source: "GTEx" },
      ppi: { score: "moderate", value: 74, records: 97, source: "STRING v12" },
      pathway: { score: "moderate", value: 61, records: 11, source: "Reactome" },
      animal: { score: "moderate", value: 71, records: 18, source: "MGI" },
      biomarker: { score: "weak", value: 34, records: 3, source: "Limited studies" },
    },
  },
  {
    id: "C9orf72",
    symbol: "C9orf72",
    fullName: "Chromosome 9 Open Reading Frame 72",
    priorityScore: 71,
    tier: "HIGH",
    evidenceStrength: "HIGH",
    consistency: "MEDIUM",
    maturity: "MEDIUM",
    translationalOpportunity: "Active Clinical Development",
    selectionSource: "Most common genetic cause of familial ALS (GGGGCC repeat expansion)",
    mainGap: "Mechanism of toxicity (gain-of-function vs. loss-of-function) remains partially unresolved",
    cautionFlags: ["Repeat expansion mechanism creates dual toxic gain and haploinsufficiency; interventions targeting one may worsen the other"],
    geneticContribution: 32,
    literatureContribution: 26,
    clinicalContribution: 13,
    whyRanked: "GGGGCC hexanucleotide repeat expansion in C9orf72 is the most common identifiable genetic cause of both familial and sporadic ALS (~40% of familial, ~7% sporadic). Active antisense oligonucleotide trials are underway. Mechanism involves both toxic RNA foci and dipeptide repeat proteins, creating some evidential inconsistency.",
    evidence: {
      genetic: { score: "strong", value: 92, records: 224, source: "ClinVar, OMIM" },
      clinical: { score: "moderate", value: 63, records: 8, source: "ClinicalTrials.gov" },
      functional: { score: "moderate", value: 72, records: 267, source: "PubMed" },
      literature: { score: "strong", value: 89, records: 2100, source: "PubMed" },
      druggability: { score: "moderate", value: 58, records: 11, source: "Pharos, ChEMBL" },
      safety: { score: "moderate", value: 55, records: 7, source: "Safety studies" },
      expression: { score: "moderate", value: 69, records: 6, source: "GTEx" },
      ppi: { score: "weak", value: 44, records: 31, source: "STRING v12" },
      pathway: { score: "moderate", value: 67, records: 9, source: "Reactome" },
      animal: { score: "strong", value: 81, records: 28, source: "MGI" },
      biomarker: { score: "weak", value: 39, records: 5, source: "C9orf72 biomarker studies" },
    },
  },
  {
    id: "ATXN2",
    symbol: "ATXN2",
    fullName: "Ataxin-2",
    priorityScore: 45,
    tier: "MEDIUM",
    evidenceStrength: "MEDIUM",
    consistency: "LOW",
    maturity: "LOW",
    translationalOpportunity: "Modifier Target — Requires Validation",
    selectionSource: "Genetic modifier screen + TDP-43 interaction",
    mainGap: "Mechanistic pathway connecting ATXN2 to TDP-43 aggregation incompletely characterized",
    cautionFlags: [],
    geneticContribution: 18,
    literatureContribution: 16,
    clinicalContribution: 11,
    whyRanked: "Intermediate-length CAG repeat expansions in ATXN2 are a risk factor for ALS, and ATXN2 directly interacts with TDP-43 to promote aggregation. Evidence is emerging but consistency is low — several functional findings have not been replicated. Maturity is early.",
    evidence: {
      genetic: { score: "moderate", value: 61, records: 42, source: "GWAS, ClinVar" },
      clinical: { score: "none", value: 0, records: 0, source: "No clinical evidence" },
      functional: { score: "moderate", value: 58, records: 67, source: "PubMed" },
      literature: { score: "moderate", value: 69, records: 380, source: "PubMed" },
      druggability: { score: "weak", value: 31, records: 2, source: "Pharos" },
      safety: { score: "unchecked", value: 0, records: 0, source: "Not yet assessed" },
      expression: { score: "moderate", value: 62, records: 6, source: "GTEx" },
      ppi: { score: "moderate", value: 66, records: 44, source: "STRING v12" },
      pathway: { score: "weak", value: 42, records: 5, source: "Reactome" },
      animal: { score: "moderate", value: 59, records: 11, source: "MGI" },
      biomarker: { score: "none", value: 0, records: 0, source: "No data" },
    },
  },
];

export const CONTRADICTIONS = [
  {
    id: "c1",
    targetId: "TARDBP",
    dimension: "Functional",
    sourceA: { ref: "Neumann et al., 2006 (Science)", claim: "TDP-43 loss from nucleus causes motor neuron death", direction: "loss-of-function toxic" },
    sourceB: { ref: "Arnold et al., 2013 (PNAS)", claim: "TDP-43 cytoplasmic gain-of-function is primary driver", direction: "gain-of-function toxic" },
    classification: "Mechanism Direction Conflict",
    verificationStatus: "Unresolved — both mechanisms supported by independent models",
    impact: "HIGH — determines therapeutic strategy (restore nuclear vs. clear cytoplasmic)",
  },
  {
    id: "c2",
    targetId: "C9orf72",
    dimension: "Functional",
    sourceA: { ref: "DeJesus-Hernandez et al., 2011 (Neuron)", claim: "Haploinsufficiency of C9orf72 protein contributes to toxicity", direction: "loss-of-function" },
    sourceB: { ref: "Lagier-Tourenne et al., 2013 (PNAS)", claim: "RNA foci and DPR proteins are the primary toxic species", direction: "gain-of-function" },
    classification: "Mechanism Direction Conflict",
    verificationStatus: "Partially resolved — consensus favors gain-of-function but loss-of-function not excluded",
    impact: "HIGH — antisense strategies targeting repeat RNA may partially suppress C9orf72 protein",
  },
];

export const RESEARCH_GAPS = [
  {
    id: "g1",
    targetId: "SOD1",
    gapType: "Safety Evidence Gap",
    dimension: "Safety",
    evidenceBehind: "SOD1 suppression via ASO is effective in familial SOD1-ALS. SOD1 protein is ubiquitously expressed. Long-term effects on non-motor neurons and systemic biology remain understudied.",
    whyMatters: "Long-term SOD1 suppression in non-diseased neurons could affect redox homeostasis. Chronic administration safety for 10+ year therapeutic use is unknown.",
    nextInvestigation: "Longitudinal toxicology study in non-human primates with sustained intrathecal SOD1-ASO delivery. Characterize neuron-type-specific proteostatic effects.",
    decisionImpact: "If safety concern confirmed: limits chronic use; requires dose optimization or periodic dosing strategy.",
    priority: "MEDIUM",
  },
  {
    id: "g2",
    targetId: "TARDBP",
    gapType: "Modality Gap",
    dimension: "Druggability",
    evidenceBehind: "TDP-43 is essential for RNA splicing. Neither gain-of-function suppression nor loss-of-function restoration has been cleanly demonstrated safe in vivo at therapeutic doses.",
    whyMatters: "Without a validated therapeutic modality, the strength of mechanistic evidence cannot be translated into a drug candidate. No clinical trials address TDP-43 directly.",
    nextInvestigation: "Screen for small molecules that reduce cytoplasmic TDP-43 mislocalization without reducing total TDP-43 levels. Evaluate nuclear retention strategies.",
    decisionImpact: "Critical gap — resolving modality question determines whether TARDBP becomes a primary or adjunct target in the next 3-5 years.",
    priority: "HIGH",
  },
  {
    id: "g3",
    targetId: "ATXN2",
    gapType: "Replication Gap",
    dimension: "Functional",
    evidenceBehind: "Initial reports of ATXN2 intermediate repeat expansion as ALS risk factor not consistently replicated across all cohorts. Some functional rescue experiments used non-physiological overexpression systems.",
    whyMatters: "If ATXN2 risk effect is population-specific or context-dependent, therapeutic targeting would have a narrower indication than currently assumed.",
    nextInvestigation: "Large-scale replication of ATXN2 repeat expansion in diverse ALS cohorts (>5,000 patients). iPSC-derived motor neuron functional studies with endogenous expression levels.",
    decisionImpact: "Without replication, ATXN2 remains a hypothesis rather than a validated target. Investment should be conditional on replication results.",
    priority: "HIGH",
  },
];

export const EXPRESSION_DATA: Record<string, Record<string, "HIGH" | "MEDIUM" | "LOW" | "NONE">> = {
  SOD1: {
    "Motor Cortex": "HIGH",
    "Spinal Cord": "HIGH",
    "Brain Stem": "HIGH",
    "Liver": "HIGH",
    "Skeletal Muscle": "MEDIUM",
    "Blood": "HIGH",
    "Kidney": "MEDIUM",
    "Heart": "MEDIUM",
  },
  TARDBP: {
    "Motor Cortex": "HIGH",
    "Spinal Cord": "HIGH",
    "Brain Stem": "HIGH",
    "Liver": "MEDIUM",
    "Skeletal Muscle": "LOW",
    "Blood": "MEDIUM",
    "Kidney": "LOW",
    "Heart": "LOW",
  },
  FUS: {
    "Motor Cortex": "HIGH",
    "Spinal Cord": "HIGH",
    "Brain Stem": "MEDIUM",
    "Liver": "LOW",
    "Skeletal Muscle": "LOW",
    "Blood": "MEDIUM",
    "Kidney": "LOW",
    "Heart": "LOW",
  },
};

export const MOMENTUM_DATA: Record<string, { year: number; count: number }[]> = {
  SOD1: [
    { year: 2015, count: 187 },
    { year: 2016, count: 204 },
    { year: 2017, count: 231 },
    { year: 2018, count: 278 },
    { year: 2019, count: 312 },
    { year: 2020, count: 298 },
    { year: 2021, count: 341 },
    { year: 2022, count: 389 },
    { year: 2023, count: 421 },
    { year: 2024, count: 447 },
    { year: 2025, count: 389 },
  ],
  TARDBP: [
    { year: 2015, count: 298 },
    { year: 2016, count: 334 },
    { year: 2017, count: 387 },
    { year: 2018, count: 441 },
    { year: 2019, count: 498 },
    { year: 2020, count: 512 },
    { year: 2021, count: 567 },
    { year: 2022, count: 601 },
    { year: 2023, count: 644 },
    { year: 2024, count: 672 },
    { year: 2025, count: 541 },
  ],
};

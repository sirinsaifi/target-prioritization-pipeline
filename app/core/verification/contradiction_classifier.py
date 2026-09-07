"""
Contradiction classifier — your own contribution (see project architecture doc).

REVISED (source-type-aware): live GraphQL introspection against the OTP API
showed that population/tissue/assay_type/endpoint do NOT exist as uniform
fields across evidence source types. Genetic evidence (eva, uniprot_variants,
gwas_credible_sets) is compared using variant/pathogenicity fields instead.
Experimental (IMPC) evidence uses tissue/phenotype/assay fields. Clinical
evidence uses population/endpoint/intervention fields. Literature (europepmc)
evidence has no structured comparability fields at all.

Design decision: two evidence records are only classified for contradiction
if they belong to the SAME source-type group. Cross-type comparison (e.g.
a genetic pathogenicity claim vs. a clinical trial outcome) is a real
question but structurally harder, and is named as future work rather than
forced into this framework — see app/config.py comments.

OTP standardizes the Direction of Effect concept (GoF/LoF on target,
Risk/Protective on trait) across sources; this module still uses that as the
universal trigger for step 1, since it IS present across source types.

Decision order (strict, checked top to bottom):
  0. Different source-type groups -> "not_comparable_cross_type", stop.
  1. Same direction on trait -> "no_contradiction", stop.
  2. Different direction + zero applicable fields confirmed EITHER matched
        or mismatched (every field null on one or both sides) ->
        "unclassified" — see "Null-handling" below, this is NOT the same
        as a confirmed direct contradiction.
  3. Different direction + at least one confirmed-matched field and zero
        confirmed-mismatched fields -> "direct_contradiction"
  4. Different direction + exactly one applicable field mismatched
        -> "population_heterogeneity" (clinical/experimental: population or
           tissue differs) or "methodological_disagreement" (assay/endpoint/
           inheritance-pattern differs) depending on which field it is
  5. Different direction + multiple applicable fields mismatched at once
        -> "unclassified" (explicitly flagged, not forced into a category)
  6. Source type has zero comparability fields (literature) -> "unclassified"
     regardless of direction — no structural basis to classify further

Null-handling (resolved — see docs/06_evidence_heterogeneity_discovery.md
"Open items"): a field that is null on one or both sides contributes to
NEITHER matched nor mismatched — it's genuinely unknown, not evidence of
agreement or disagreement. The consequence that required fixing: a pair
where EVERY applicable field is null on at least one side previously fell
through to "zero mismatches -> direct_contradiction", which silently
claimed "confirmed same context, opposite direction" when the honest
description is "we know nothing about context, opposite direction". Fixed
by requiring at least one CONFIRMED matched field before returning
direct_contradiction; zero matched AND zero mismatched now correctly
returns "unclassified". This could not be caught against real evidence for
this project's 5 genes — every direction-labeled genetic record for SOD1/
C9orf72/TARDBP/FUS is uniformly "Risk" (ClinVar only curates pathogenic-risk
calls for these Mendelian ALS genes; NEK1 has zero direction-labeled
records at all), so the classifier's conflict branches (steps 2-5) are
structurally unreachable with this real dataset — found via constructed
test cases instead (see tests/test_core_logic.py).
"""

from dataclasses import dataclass, field as dc_field
from app.config import COMPARABILITY_FIELDS_BY_SOURCE_TYPE

# Fields whose mismatch, when it's the ONLY mismatch, indicates a
# population/context-heterogeneity-style finding rather than a true conflict
POPULATION_LIKE_FIELDS = {"population", "tissue"}

# Fields whose mismatch, when it's the ONLY mismatch, indicates a
# methodological/measurement-style disagreement rather than a true conflict
METHODOLOGICAL_LIKE_FIELDS = {"assay_type", "endpoint", "inheritance_pattern", "intervention", "phenotype"}


@dataclass
class EvidenceForComparison:
    """Minimal shape needed from an EvidenceRecord to run the classifier."""
    record_id: int
    source_record_id: str
    source_type: str  # "genetic" | "experimental" | "clinical" | "literature"
    direction_on_trait: str | None = None  # "Risk" | "Protective"

    # Generic fields
    tissue: str | None = None
    population: str | None = None
    assay_type: str | None = None
    endpoint: str | None = None
    phenotype: str | None = None
    intervention: str | None = None

    # Genetic-specific fields
    variant_id: str | None = None
    clinical_significance: str | None = None
    inheritance_pattern: str | None = None


@dataclass
class ClassificationResult:
    classification: str
    matched_fields: list = dc_field(default_factory=list)
    mismatched_fields: list = dc_field(default_factory=list)


def classify_contradiction(a: EvidenceForComparison, b: EvidenceForComparison) -> ClassificationResult:
    """Classify the relationship between two evidence records. See module docstring."""

    # Step 0 — only compare within the same source-type group
    if a.source_type != b.source_type:
        return ClassificationResult("not_comparable_cross_type", [], [])

    applicable_fields = COMPARABILITY_FIELDS_BY_SOURCE_TYPE.get(a.source_type, [])

    # Step 5 — source type has no structural basis for comparison (literature)
    if not applicable_fields:
        return ClassificationResult("unclassified", [], [])

    # Step 1 — same direction -> no contradiction of any kind
    if a.direction_on_trait is not None and a.direction_on_trait == b.direction_on_trait:
        return ClassificationResult("no_contradiction", applicable_fields, [])

    # If direction is missing on either record, we can't confirm a true
    # contradiction — be honest rather than guessing
    if a.direction_on_trait is None or b.direction_on_trait is None:
        return ClassificationResult("unclassified", [], [])

    # Step 2+ — direction differs, check the fields that actually apply to this source type
    matched, mismatched = [], []
    for f in applicable_fields:
        val_a, val_b = getattr(a, f, None), getattr(b, f, None)
        if val_a is not None and val_b is not None and val_a == val_b:
            matched.append(f)
        elif val_a is not None and val_b is not None:
            mismatched.append(f)
        # if either value is None, the field simply doesn't contribute either way

    # A "direct_contradiction" verdict claims we've confirmed the same
    # context on every applicable field, just with opposite direction. Zero
    # mismatches is NOT enough to claim that on its own — if every
    # applicable field is also unmatched (null on one or both sides for all
    # of them), we have literally no confirmed-same field, only an absence
    # of confirmed differences. That's "we don't know", not "confirmed
    # same" — be honest and call it unclassified instead of overclaiming.
    if not mismatched and not matched:
        return ClassificationResult("unclassified", matched, mismatched)

    if not mismatched:
        return ClassificationResult("direct_contradiction", matched, mismatched)

    if len(mismatched) == 1:
        the_field = mismatched[0]
        if the_field in POPULATION_LIKE_FIELDS:
            return ClassificationResult("population_heterogeneity", matched, mismatched)
        if the_field in METHODOLOGICAL_LIKE_FIELDS:
            return ClassificationResult("methodological_disagreement", matched, mismatched)

    # Multiple applicable fields differ at once -> be honest, don't force a category
    return ClassificationResult("unclassified", matched, mismatched)


if __name__ == "__main__":
    # Genetic source-type example (SOD1-style: eva/uniprot_variants evidence)
    gen_a = EvidenceForComparison(1, "EVA:1", "genetic", "Risk",
                                  variant_id="rs123", clinical_significance="pathogenic",
                                  inheritance_pattern="Autosomal dominant")
    gen_b_direct = EvidenceForComparison(2, "EVA:2", "genetic", "Protective",
                                         variant_id="rs123", clinical_significance="pathogenic",
                                         inheritance_pattern="Autosomal dominant")
    gen_b_method = EvidenceForComparison(3, "EVA:3", "genetic", "Protective",
                                         variant_id="rs123", clinical_significance="pathogenic",
                                         inheritance_pattern="Autosomal recessive")

    print("Genetic direct:       ", classify_contradiction(gen_a, gen_b_direct).classification)
    print("Genetic methodological:", classify_contradiction(gen_a, gen_b_method).classification)

    # Cross-type example — should refuse to classify
    lit_a = EvidenceForComparison(4, "PMID:1", "literature", "Risk")
    print("Cross-type (genetic vs literature):", classify_contradiction(gen_a, lit_a).classification)

    # Literature-vs-literature — no structural basis, always unclassified
    lit_b = EvidenceForComparison(5, "PMID:2", "literature", "Protective")
    print("Literature vs literature:", classify_contradiction(lit_a, lit_b).classification)

    # Clinical source-type example
    clin_a = EvidenceForComparison(6, "NCT:1", "clinical", "Risk", population="european", endpoint="survival")
    clin_b_pop = EvidenceForComparison(7, "NCT:2", "clinical", "Protective", population="east_asian", endpoint="survival")
    print("Clinical population-only mismatch:", classify_contradiction(clin_a, clin_b_pop).classification)

"""
Pharos cross-checks — deterministic comparisons of Pharos's own evidence
against this project's already-stored OTP-derived evidence, for the SAME
targets. Two cross-checks (items D and E of the Pharos expansion):

D. DISEASE-ASSOCIATION cross-check: Pharos's per-gene ALS DisGeNET score vs
   this project's OTP-derived Genetic + Literature dimension scores. Reports
   AGREE/DISAGREE per gene, stores BOTH values visibly, never silently merges
   them. Same pattern as the GTEx-vs-HPA tau/category cross-check in
   scripts/ingest_evidence.py's _build_gtex_fields() — a direct, coarse
   comparison of two independent sources' read on the same question, NOT a
   rigorous statistical concordance test and NOT a contradiction-classifier
   code path.

E. PPI cross-check: Pharos's PPI partner list (STRINGDB source) vs this
   project's STRING-derived high-confidence (combined_score>700) partner
   list. Reports real overlap/divergence — a genuine third-source
   verification opportunity (Pharos and STRING both draw on STRINGDB, but
   Pharos exposes ALL STRING partners while this project filters to
   high-confidence only, so the comparison is meaningful).

CRITICAL DESIGN: these are COMPARISONS, not new evidence — they do NOT
create a new EvidenceRecord dimension (per this task's explicit instruction).
The Pharos raw data they read lives in the stored druggability EvidenceRecord's
`notes` (see scripts/ingest_evidence.py's _build_druggability_fields()); the
OTP scores live in PriorityScore; the STRING partners live in the ppi_network
EvidenceRecord's `notes`. This module combines already-real stored values —
it computes nothing new about the world, only compares two stored readouts.

All deterministic, no LLM. Every verdict is a falsifiable rule, same
discipline as the contradiction classifier and gap taxonomy.
"""

from dataclasses import dataclass, field
import json


@dataclass
class CrossCheckResult:
    """One cross-check's result for one target. Both values are always
    present and visible (never silently merged into a single number)."""
    check_type: str            # "disease_association" | "ppi"
    gene_symbol: str
    verdict: str               # "agree" | "disagree" | "partial" | "incomparable"
    pharos_value: str          # the real Pharos readout, as stored
    pipeline_value: str        # this project's readout, as stored
    rationale: str             # the deterministic rule + real values behind the verdict
    details: dict = field(default_factory=dict)  # structured real values for the portfolio/UI


# --- notes-parsing helpers (shared convention with gaps.py's notes parsing) --

def _parse_notes(notes: str | None) -> dict:
    """
    Parse the structured 'key=value; key=value; ...' notes string this
    project's field builders write (see _build_druggability_fields /
    _build_ppi_network_fields / _build_safety_signal_fields). Returns a dict
    of key -> raw string value. Robust to values containing '=' (only splits
    on the first '=' per segment) but NOT to values containing ';' (those are
    the segment delimiter — no current builder puts a ';' inside a value).
    """
    if not notes:
        return {}
    parsed = {}
    for segment in notes.split(";"):
        segment = segment.strip()
        if "=" in segment:
            key, _, value = segment.partition("=")
            parsed[key.strip()] = value.strip()
    return parsed


def _parse_partner_list(notes: str | None, key: str) -> set[str]:
    """Extract a comma-separated partner-symbol list from a notes field
    (e.g. the 'ppi_partners=' or 'partners=' key). Returns a set of symbols."""
    parsed = _parse_notes(notes)
    raw = parsed.get(key, "")
    if not raw or raw == "none":
        return set()
    return {sym.strip().upper() for sym in raw.split(",") if sym.strip()}


# --- Cross-check D: disease association vs OTP Genetic/Literature ----------

# DisGeNET score bands (Pharos's own — DisGeNET's published score range is
# 0-1, with >=0.5 generally considered a meaningful association). Used to
# bucket Pharos's score into the same High/Medium/Low shape this project's
# tiers.py uses, so the comparison is tier-vs-tier (coarse) rather than
# pretending two differently-derived 0-1 numbers are directly comparable.
DISGENET_HIGH_THRESHOLD = 0.7
DISGENET_LOW_THRESHOLD = 0.3


def _disgenet_tier(score: float | None) -> str:
    if score is None:
        return "none"
    if score >= DISGENET_HIGH_THRESHOLD:
        return "High"
    if score < DISGENET_LOW_THRESHOLD:
        return "Low"
    return "Medium"


def disease_association_cross_check(
    gene_symbol: str,
    pharos_notes: str | None,
    dimension_breakdown_json: str | None,
) -> CrossCheckResult:
    """
    Compare Pharos's per-gene ALS DisGeNET score against this project's
    OTP-derived Genetic + Literature dimension scores.

    CRITICAL (live-confirmed): Pharos's `associationCount`/`diseaseCounts` are
    DISEASE-GLOBAL (501 = total ALS-associated targets, identical across
    genes) — the per-gene signal is the DisGeNET `score` inside the exact ALS
    disease's associations[] (SOD1/C9orf72/TARDBP=0.7, FUS=0.5, NEK1=0.61),
    stored in the druggability row's notes as `als_disgenet_score`.

    The comparison is TIER-vs-TIER (coarse), not a direct numeric equality —
    Pharos's DisGeNET score and OTP's harmonic-sum-derived dimension scores
    are differently-derived 0-1 numbers, so "do they rank this target's ALS
    evidence similarly" is the honest question, not "are the numbers equal".
    - AGREE: both sources place the target in the same High/Medium/Low band
      for ALS association strength.
    - DISAGREE: the bands differ by more than one tier (e.g. Pharos High but
      OTP Low).
    - PARTIAL: bands differ by exactly one tier (a real, milder disagreement
      worth flagging but not a contradiction).
    - INCOMPARABLE: Pharos has no ALS DisGeNET score for this gene, or no OTP
      dimension scores exist yet.
    """
    pharos_parsed = _parse_notes(pharos_notes)
    disgenet_raw = pharos_parsed.get("als_disgenet_score")
    disgenet_score = None
    if disgenet_raw and disgenet_raw not in ("None", "none", ""):
        try:
            disgenet_score = float(disgenet_raw)
        except ValueError:
            disgenet_score = None
    pharos_tier = _disgenet_tier(disgenet_score)

    dimension_breakdown = {}
    if dimension_breakdown_json:
        try:
            dimension_breakdown = json.loads(dimension_breakdown_json)
        except (ValueError, TypeError):
            dimension_breakdown = {}
    genetic_score = dimension_breakdown.get("genetic")
    literature_score = dimension_breakdown.get("literature")

    # OTP tiers reuse this project's own strength threshold (0.7 High / 0.5
    # Low — see config.EVIDENCE_STRENGTH_HIGH_THRESHOLD / tiers.py), so a
    # Genetic/Literature score is bucketed the same way DisGeNET is above.
    def _otp_tier(score):
        if score is None:
            return "none"
        if score >= 0.7:
            return "High"
        if score < 0.3:
            return "Low"
        return "Medium"

    genetic_tier = _otp_tier(genetic_score)
    literature_tier = _otp_tier(literature_score)

    if disgenet_score is None or (genetic_score is None and literature_score is None):
        verdict = "incomparable"
    else:
        # Compare Pharos's tier against the STRONGER of the two OTP dimensions
        # (the target's best-supported ALS evidence line), since Pharos's
        # DisGeNET score is an aggregate across all its evidence types.
        otp_tiers = [t for t in (genetic_tier, literature_tier) if t != "none"]
        if not otp_tiers:
            verdict = "incomparable"
        else:
            order = {"Low": 0, "Medium": 1, "High": 2}
            strongest_otp = max(otp_tiers, key=lambda t: order.get(t, 0))
            gap = abs(order.get(pharos_tier, 0) - order.get(strongest_otp, 0))
            if gap == 0:
                verdict = "agree"
            elif gap == 1:
                verdict = "partial"
            else:
                verdict = "disagree"
            strongest_otp = strongest_otp  # for the rationale below

    rationale = (
        f"Pharos DisGeNET ALS score={disgenet_score} (tier={pharos_tier}) vs "
        f"OTP Genetic={genetic_score} (tier={genetic_tier}), "
        f"OTP Literature={literature_score} (tier={literature_tier}). "
        f"Verdict={verdict}: tier gap between Pharos and the strongest OTP dimension. "
        f"Coarse tier comparison (High/Medium/Low), not a direct numeric equality — "
        f"the two scores are differently-derived 0-1 numbers."
    )
    return CrossCheckResult(
        check_type="disease_association",
        gene_symbol=gene_symbol,
        verdict=verdict,
        pharos_value=f"DisGeNET ALS score={disgenet_score} (tier={pharos_tier})",
        pipeline_value=f"Genetic={genetic_score} (tier={genetic_tier}); Literature={literature_score} (tier={literature_tier})",
        rationale=rationale,
        details={
            "disgenet_score": disgenet_score, "pharos_tier": pharos_tier,
            "genetic_score": genetic_score, "genetic_tier": genetic_tier,
            "literature_score": literature_score, "literature_tier": literature_tier,
            "als_evidence": pharos_parsed.get("als_evidence"),
            "als_subtype": pharos_parsed.get("als_subtype"),
        },
    )


# --- Cross-check E: PPI partners vs STRING ----------------------------------

def ppi_cross_check(
    gene_symbol: str,
    pharos_notes: str | None,
    string_notes: str | None,
) -> CrossCheckResult:
    """
    Compare Pharos's PPI partner list (STRINGDB source) against this
    project's STRING-derived high-confidence (combined_score>700) partner
    list. Reports real overlap/divergence — a genuine third-source
    verification opportunity.

    Both sources draw on STRINGDB, but they differ in a known, documented way:
    Pharos exposes ALL STRING partners for a target, while this project's
    STRING ingestion (app/ingestion/string_client.py) filters to
    combined_score>700 (config.STRING_HIGH_CONFIDENCE_THRESHOLD). So the
    STRING high-confidence set is expected to be a SUBSET of Pharos's full
    STRINGDB set — high overlap is expected and reassuring; LOW overlap would
    be a real, surprising finding worth flagging (it would mean the two
    STRINGDB-derived lists disagree on which partners exist at all, not just
    on confidence).

    - AGREE: the STRING high-confidence set is a subset of (or heavily
      overlaps) Pharos's STRINGDB set (overlap_ratio >= 0.5).
    - PARTIAL: moderate overlap (0.2 <= overlap_ratio < 0.5) — some STRING
      high-confidence partners not found in Pharos's (bounded, sampled) list,
      possibly a sampling artifact rather than a real divergence.
    - DISAGREE: low overlap (< 0.2) — a real, surprising divergence.
    - INCOMPARABLE: either source has no partners, or Pharos returned none.
    """
    pharos_partners = _parse_partner_list(pharos_notes, "ppi_partners")
    string_partners = _parse_partner_list(string_notes, "partners")
    pharos_count_raw = _parse_notes(pharos_notes).get("ppi_stringdb_count", "0")
    try:
        pharos_stringdb_count = int(pharos_count_raw)
    except ValueError:
        pharos_stringdb_count = 0
    string_count = len(string_partners)

    if not pharos_partners or not string_partners:
        verdict = "incomparable"
        overlap = 0
        overlap_ratio = None
    else:
        overlap = len(pharos_partners & string_partners)
        # overlap_ratio: of this project's high-confidence STRING partners,
        # how many also appear in Pharos's (sampled) STRINGDB list. Pharos's
        # list is bounded to PPI_PARTNER_SAMPLE_TOP (50), so a target with
        # more than 50 real STRING partners may show sampling-driven
        # non-overlap — handled by the PARTIAL band, not treated as DISAGREE.
        overlap_ratio = overlap / len(string_partners)
        if overlap_ratio >= 0.5:
            verdict = "agree"
        elif overlap_ratio >= 0.2:
            verdict = "partial"
        else:
            verdict = "disagree"

    # Pre-compute the ratio string OUTSIDE the f-string — putting a conditional
    # expression directly inside an f-string's format spec crashes at runtime.
    ratio_str = f"{overlap_ratio:.0%}" if overlap_ratio is not None else "n/a"

    rationale = (
        f"Pharos STRINGDB partners: {pharos_stringdb_count} total (sampled {len(pharos_partners)} stored) "
        f"vs this project's STRING high-confidence (>700) partners: {string_count}. "
        f"Overlap of this project's high-confidence set with Pharos's sampled list: "
        f"{overlap}/{string_count} ({ratio_str}). Verdict={verdict}. "
        f"Pharos exposes ALL STRING partners while this project filters to combined_score>700, "
        f"so the high-confidence set is EXPECTED to be a subset of Pharos's — low overlap would "
        f"be a real surprising finding, high overlap is reassuring."
    )
    return CrossCheckResult(
        check_type="ppi",
        gene_symbol=gene_symbol,
        verdict=verdict,
        pharos_value=f"{pharos_stringdb_count} STRINGDB partners ({len(pharos_partners)} sampled)",
        pipeline_value=f"{string_count} STRING high-confidence (>700) partners",
        rationale=rationale,
        details={
            "pharos_stringdb_count": pharos_stringdb_count,
            "pharos_sampled_count": len(pharos_partners),
            "string_high_confidence_count": string_count,
            "overlap": overlap,
            "overlap_ratio": overlap / len(string_partners) if string_partners else None,
            "pharos_only_sampled": sorted(list(pharos_partners - string_partners))[:10],
            "string_only": sorted(list(string_partners - pharos_partners))[:10],
        },
    )

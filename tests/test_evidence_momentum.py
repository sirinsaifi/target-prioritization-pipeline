"""
Tests for app/core/scoring/evidence_momentum.py — a purely factual,
deterministic trend computed from real, timestamped EvidenceRecord rows.
No LLM involvement, so no mocking needed here; a plain in-memory SQLite
session is enough (single-threaded direct function calls, not going
through FastAPI's TestClient/threadpool, so StaticPool is not required
the way it is in tests/test_get_routes.py).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import Target, EvidenceRecord
from app.core.scoring.evidence_momentum import compute_momentum


def _make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _seed_target(db, gene="TESTGENE"):
    target = Target(gene_symbol=gene, ensembl_id=f"ENSG_{gene}", disease_efo_id="MONDO_TEST")
    db.add(target)
    db.commit()
    return target.id


def _add_record(db, target_id, year, dimension="literature"):
    db.add(EvidenceRecord(
        target_id=target_id, dimension=dimension, data_source="pubmed",
        source_record_id=f"pmid-{year}-{dimension}-{id(object())}",
        publication_year=year,
    ))


def test_insufficient_data_when_no_dated_evidence_exists():
    db = _make_db()
    target_id = _seed_target(db)
    # A real, undated record (e.g. a genetic variant row) should not count.
    db.add(EvidenceRecord(target_id=target_id, dimension="genetic", data_source="eva", source_record_id="rs123"))
    db.commit()

    result = compute_momentum(target_id, db)

    assert result.trend == "insufficient_data"
    assert result.momentum_score is None
    assert result.yearly_counts == {}
    assert result.reference_year is None


def test_accelerating_trend_from_real_recent_spike():
    db = _make_db()
    target_id = _seed_target(db)
    # reference year = 2025. Prior window (2022-2023): 2 records.
    # Recent window (2024-2025): 10 records. Ratio = 5.0 > 1.2.
    for _ in range(1):
        _add_record(db, target_id, 2022)
    for _ in range(1):
        _add_record(db, target_id, 2023)
    for _ in range(5):
        _add_record(db, target_id, 2024)
    for _ in range(5):
        _add_record(db, target_id, 2025)
    db.commit()

    result = compute_momentum(target_id, db)

    assert result.reference_year == 2025
    assert result.prior_window_count == 2
    assert result.recent_window_count == 10
    assert result.momentum_score == 5.0
    assert result.trend == "accelerating"
    assert result.yearly_counts == {"2022": 1, "2023": 1, "2024": 5, "2025": 5}


def test_stable_trend_when_counts_are_flat():
    db = _make_db()
    target_id = _seed_target(db)
    for year in (2022, 2023, 2024, 2025):
        for _ in range(4):
            _add_record(db, target_id, year)
    db.commit()

    result = compute_momentum(target_id, db)

    assert result.prior_window_count == 8
    assert result.recent_window_count == 8
    assert result.momentum_score == 1.0
    assert result.trend == "stable"


def test_declining_trend_from_real_drop():
    db = _make_db()
    target_id = _seed_target(db)
    for _ in range(10):
        _add_record(db, target_id, 2022)
    for _ in range(10):
        _add_record(db, target_id, 2023)
    for _ in range(1):
        _add_record(db, target_id, 2024)
    for _ in range(1):
        _add_record(db, target_id, 2025)
    db.commit()

    result = compute_momentum(target_id, db)

    assert result.momentum_score == 0.1
    assert result.trend == "declining"


def test_emerging_when_prior_window_is_genuinely_zero():
    db = _make_db()
    target_id = _seed_target(db)
    # No records at all before 2024 — a real, zero-base spike, not a ratio.
    for _ in range(6):
        _add_record(db, target_id, 2024)
    for _ in range(6):
        _add_record(db, target_id, 2025)
    db.commit()

    result = compute_momentum(target_id, db)

    assert result.prior_window_count == 0
    assert result.recent_window_count == 12
    assert result.momentum_score is None
    assert result.trend == "emerging"


def test_stable_upper_boundary_is_inclusive():
    # Exactly 1.2 must land in "stable", not spill into "accelerating" —
    # confirms the partition has no gap at this boundary (see config.py's
    # own comment on MOMENTUM_ACCELERATING_THRESHOLD).
    db = _make_db()
    target_id = _seed_target(db)
    for _ in range(10):
        _add_record(db, target_id, 2023)
    for _ in range(12):
        _add_record(db, target_id, 2025)  # 12/10 = 1.2 exactly
    db.commit()

    result = compute_momentum(target_id, db)
    assert result.momentum_score == 1.2
    assert result.trend == "stable"


def test_stable_lower_boundary_is_inclusive():
    # Exactly 0.8 must land in "stable", not spill into "declining" — the
    # other half of the same no-gap partition guarantee.
    db = _make_db()
    target_id = _seed_target(db)
    for _ in range(10):
        _add_record(db, target_id, 2023)
    for _ in range(8):
        _add_record(db, target_id, 2025)  # 8/10 = 0.8 exactly
    db.commit()

    result = compute_momentum(target_id, db)
    assert result.momentum_score == 0.8
    assert result.trend == "stable"


def test_yearly_counts_by_dimension_are_grouped_separately():
    db = _make_db()
    target_id = _seed_target(db)
    _add_record(db, target_id, 2024, dimension="literature")
    _add_record(db, target_id, 2024, dimension="literature")
    _add_record(db, target_id, 2024, dimension="human_clinical")
    db.commit()

    result = compute_momentum(target_id, db)

    assert result.yearly_counts_by_dimension["literature"] == {"2024": 2}
    assert result.yearly_counts_by_dimension["human_clinical"] == {"2024": 1}
    assert result.yearly_counts == {"2024": 3}

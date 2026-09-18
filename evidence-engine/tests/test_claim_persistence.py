"""Claim volume regression; opt-in PostgreSQL checks use an isolated schema.

Set CLAIM_LEDGER_TEST_DATABASE_URL to a disposable PostgreSQL database using
the postgresql+asyncpg driver to run the real driver/transaction checks.
"""

from contextlib import asynccontextmanager
from dataclasses import asdict, replace
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import Column, MetaData, Table, Uuid, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.dialects.postgresql.asyncpg import dialect
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.job import EvidenceClaim
from app.services.claim_ledger import GroundedClaim, persist_grounded_claims


def make_claims(count: int) -> list[GroundedClaim]:
    case_id, file_id, job_id = (str(uuid.uuid4()) for _ in range(3))
    return [
        GroundedClaim(
            id=f"{number:064x}",
            case_id=case_id,
            evidence_file_id=file_id,
            engine_job_id=job_id,
            revision_id="test-revision",
            claim_type="entity_fact",
            subject_id=f"entity-{number}",
            predicate="recorded_fact",
            object_value={"text": f"Synthetic fact {number}", "amount": number},
            quote=f"Original synthetic quote {number} — €",
            source_location={"page_start": number // 10 + 1, "quote_start_char": number},
            confidence=0.91,
            status="verified" if number % 2 else "grounded",
        )
        for number in range(count)
    ]


def claim_values(claim: GroundedClaim) -> dict:
    values = asdict(claim)
    for key in ("case_id", "evidence_file_id", "engine_job_id"):
        values[key] = uuid.UUID(values[key])
    return values


@pytest.mark.parametrize("count", [0, 1, 2520, 2521, 10003])
async def test_every_claim_fits_driver_bind_limit_without_truncation(count):
    claims = make_claims(count)
    written_ids = []

    class CompileSession:
        @asynccontextmanager
        async def begin_nested(self):
            yield

        async def execute(self, statement):
            compiled = statement.compile(dialect=dialect())
            assert len(compiled.positiontup) <= 32767
            assert "ON CONFLICT (id) DO NOTHING" in str(compiled)
            written_ids.extend(
                value for key, value in compiled.params.items() if key.startswith("id_m")
            )

    assert await persist_grounded_claims(CompileSession(), claims) == count
    assert written_ids == [claim.id for claim in claims]


@pytest_asyncio.fixture
async def claim_database():
    url = os.environ.get("CLAIM_LEDGER_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set CLAIM_LEDGER_TEST_DATABASE_URL for isolated PostgreSQL checks")
    schema = "claim_volume_test_" + uuid.uuid4().hex
    admin = create_async_engine(url)
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    metadata = MetaData()
    files = Table("evidence_files", metadata, Column("id", Uuid, primary_key=True))
    jobs = Table("jobs", metadata, Column("id", Uuid, primary_key=True))
    EvidenceClaim.__table__.to_metadata(metadata)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False), files, jobs
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def seed_parents(factory, files, jobs, claim):
    async with factory.begin() as session:
        await session.execute(insert(files).values(id=uuid.UUID(claim.evidence_file_id)))
        await session.execute(insert(jobs).values(id=uuid.UUID(claim.engine_job_id)))


async def test_old_single_insert_reproduces_reported_asyncpg_failure(claim_database):
    factory, files, jobs = claim_database
    claims = make_claims(2521)
    await seed_parents(factory, files, jobs, claims[0])
    async with factory() as session:
        with pytest.raises(DBAPIError, match="number of query arguments cannot exceed 32767"):
            await session.execute(
                insert(EvidenceClaim).values([claim_values(claim) for claim in claims])
                .on_conflict_do_nothing(index_elements=[EvidenceClaim.id])
            )
        await session.rollback()


async def test_large_import_preserves_every_field_and_retry_does_not_duplicate(claim_database):
    factory, files, jobs = claim_database
    claims = make_claims(10003)
    await seed_parents(factory, files, jobs, claims[0])
    async with factory() as session:
        assert await persist_grounded_claims(session, claims) == len(claims)
        # Releasing the helper's savepoint must not commit the caller's transaction.
        async with factory() as observer:
            assert await observer.scalar(select(func.count()).select_from(EvidenceClaim)) == 0
        await session.commit()
    retry = [replace(claims[0], quote="Must not replace original"), *claims[1:], claims[999]]
    async with factory.begin() as session:
        await persist_grounded_claims(session, retry)
    async with factory() as session:
        stored = list((await session.scalars(select(EvidenceClaim).order_by(EvidenceClaim.id))).all())
        assert len(stored) == len(claims)
        for expected, actual in zip(claims, stored, strict=True):
            for key, value in claim_values(expected).items():
                assert getattr(actual, key) == value


async def test_later_database_failure_rolls_back_all_claim_batches(claim_database):
    factory, files, jobs = claim_database
    claims = make_claims(3001)
    await seed_parents(factory, files, jobs, claims[0])
    claims[-1] = replace(claims[-1], subject_id="x" * 256)
    async with factory() as session:
        with pytest.raises(DBAPIError):
            await persist_grounded_claims(session, claims)
        # The outer pipeline can still commit its failure status without partial claims.
        await session.execute(text("SELECT 1"))
        await session.commit()
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(EvidenceClaim)) == 0


async def test_later_invalid_input_also_rolls_back_all_batches(claim_database):
    factory, files, jobs = claim_database
    claims = make_claims(3001)
    await seed_parents(factory, files, jobs, claims[0])
    claims[-1] = replace(claims[-1], case_id="invalid-uuid")
    async with factory() as session:
        with pytest.raises(ValueError):
            await persist_grounded_claims(session, claims)
        await session.commit()
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(EvidenceClaim)) == 0

"""Build the decision overlay and seed a high-frequency review queue."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .classifier import PolicyClassifier
from .protocols import CandidateClassifier
from .source import SourceLexicon
from .store import InputModelStore
from .types import DecisionStatus


@dataclass(frozen=True)
class BuildResult:
    database: Path
    proposals_added: int
    proposals_preserved: int
    status_counts: dict[str, int]


def build_input_model(
    *,
    source_database: Path,
    output_database: Path,
    policy_path: Path,
    proposal_limit: int = 10_000,
    minimum_frequency: int = 1,
    minimum_text_length: int = 2,
    classifier: CandidateClassifier | None = None,
) -> BuildResult:
    active_classifier = classifier or PolicyClassifier(policy_path)
    added = preserved = 0
    with SourceLexicon(source_database) as source, InputModelStore(output_database) as store:
        store.initialize(source_database=source_database, policy_path=policy_path)
        for candidate in source.iter_high_frequency_candidates(
            limit=proposal_limit,
            minimum_frequency=minimum_frequency,
            minimum_text_length=minimum_text_length,
        ):
            proposal = active_classifier.classify(candidate)
            if proposal.text != candidate.text:
                raise ValueError("classifier returned a decision for another candidate")
            if proposal.status is not DecisionStatus.PROPOSED:
                raise ValueError("automated classifiers may only create proposed decisions")
            if store.put(proposal, overwrite=False):
                added += 1
            else:
                preserved += 1
        counts = store.count_by_status()
    return BuildResult(
        database=output_database.resolve(),
        proposals_added=added,
        proposals_preserved=preserved,
        status_counts=counts,
    )

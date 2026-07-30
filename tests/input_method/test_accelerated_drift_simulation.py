from tools.run_accelerated_drift_simulation import acceptance


def _summary(**overrides):
    value = {
        "repeat_top1_rate": 0.999,
        "restart_retention_rate": 1.0,
        "interference_preservation_rate": 0.999,
        "self_heal_rate": 1.0,
        "late_to_early_growth_ratio": 0.1,
        "promoted_phrases": 3,
        "persistent_failure_targets": 0,
    }
    value.update(overrides)
    return value


def test_acceptance_passes_convergent_run() -> None:
    result = acceptance([_summary(), _summary()])
    assert result["passed"] is True


def test_acceptance_rejects_repeated_persistent_failure() -> None:
    result = acceptance([_summary(persistent_failure_targets=1)])
    assert result["passed"] is False
    assert result["checks"]["no_persistent_failure_target"] is False

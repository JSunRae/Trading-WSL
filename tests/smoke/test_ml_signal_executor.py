import os

os.environ["FORCE_FAKE_IB"] = "1"


def test_ml_signal_executor_import():
    from src.execution import ml_signal_executor

    exec_ = ml_signal_executor.MLSignalExecutor()
    assert hasattr(exec_, "validate_signal")
    # pragma: no cover (skip actual execution)

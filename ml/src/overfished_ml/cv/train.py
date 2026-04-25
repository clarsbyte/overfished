"""Training entrypoint stub.

Intended use: Databricks notebook or job calls into a thin wrapper that
invokes your trainer (e.g. Ultralytics YOLO) and logs to MLflow.

This module intentionally contains **no** training implementation.
"""


def train(
    *,
    config_path: str,
    output_uri: str,
) -> None:
    """Reserve hook for CV training.

    Args:
        config_path: Path or UC volume URI to a YAML/JSON training config.
        output_uri: MLflow experiment or model registry URI for artifacts.

    Raises:
        NotImplementedError: Always, until the team adds a real trainer.
    """
    raise NotImplementedError(
        "CV training is not implemented in-repo; run from Databricks with your trainer."
    )

"""Inference entrypoint stub.

Intended use: batch or one-off inference on Databricks (GPU) or exported
ONNX/torch weights referenced by URI—not embedded in the Next.js app.
"""

from typing import Any


def infer(
    *,
    model_uri: str,
    raster_uri: str,
) -> dict[str, Any]:
    """Reserve hook for SAR / vessel detection inference.

    Args:
        model_uri: MLflow model URI, UC volume path, or local artifact path.
        raster_uri: GeoTIFF or numpy-friendly raster location.

    Returns:
        Detection payload (schema TBD by implementers).

    Raises:
        NotImplementedError: Always, until the team adds a real pipeline.
    """
    raise NotImplementedError(
        "CV inference is not implemented in-repo; implement on Databricks or worker job."
    )

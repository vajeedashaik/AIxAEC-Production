from uuid import UUID

from aec_contracts import AnalyzeResult

from .base import ServiceClient

ANALYZE_TIMEOUT_SECONDS = 180.0


class VisionClient(ServiceClient):
    def analyze(self, floorplan_id: UUID, data: bytes, filename: str, content_type: str) -> AnalyzeResult:
        return self.post("/v1/analyze", AnalyzeResult.model_validate, timeout=ANALYZE_TIMEOUT_SECONDS,
                         files={"file": (filename, data, content_type)}, data={"floorplan_id": str(floorplan_id)})

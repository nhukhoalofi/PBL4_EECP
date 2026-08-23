from typing import Annotated

from fastapi import Depends, Request

from app.application.use_cases.exam_sessions.pipeline import ExamPipelineService


def get_pipeline_service(request: Request) -> ExamPipelineService:
    return request.app.state.container.pipeline_service


Service = Annotated[ExamPipelineService, Depends(get_pipeline_service)]


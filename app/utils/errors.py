from __future__ import annotations


class PipelineError(Exception):
    def __init__(self, stage: str, message: str, error_code: str = "PIPELINE_ERROR", provider: str | None = None):
        self.stage = stage
        self.message = message
        self.error_code = error_code
        self.provider = provider
        super().__init__(message)


class ProviderError(PipelineError):
    def __init__(self, stage: str, provider: str, message: str, error_code: str = "PROVIDER_ERROR"):
        super().__init__(stage=stage, provider=provider, message=message, error_code=error_code)


class ValidationError(PipelineError):
    def __init__(self, stage: str, message: str, error_code: str = "VALIDATION_ERROR"):
        super().__init__(stage=stage, message=message, error_code=error_code)

from pydantic import BaseModel, Field


class ModelConfigBase(BaseModel):
    model_type: str = Field(..., description="default | ollama | openai_compatible")
    provider: str = ""
    model_name: str = ""
    base_url: str = ""
    api_key: str | None = None
    is_default: bool = False
    is_active: bool = True


class ModelConfigCreate(ModelConfigBase):
    pass


class ModelConfigUpdate(BaseModel):
    model_type: str | None = None
    provider: str | None = None
    model_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class ModelConfigResponse(BaseModel):
    id: str
    user_id: str
    model_type: str
    provider: str
    model_name: str
    base_url: str
    api_key_masked: str = ""
    is_default: bool
    is_active: bool
    created_at: str | None = None
    updated_at: str | None = None


class ModelConfigTestRequest(ModelConfigBase):
    pass

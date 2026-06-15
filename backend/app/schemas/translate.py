from pydantic import BaseModel


class DialogueTranslateRequest(BaseModel):
    language_a: str
    language_b: str
    text: str
    model_config_id: str | None = None
    fast_mode: bool = True
    custom_instruction: str | None = None

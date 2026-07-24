from pydantic import BaseModel


class Model(BaseModel):
    id: str
    name: str
    provider: str
    api: str
    base_url: str
    context_model: int
    max_output_tokens: int

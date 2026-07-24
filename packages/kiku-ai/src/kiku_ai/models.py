from pydantic import BaseModel


class Model(BaseModel):
    id: str
    name: str
    provider: str
    api: str  # name of api
    context_model: int
    max_output_tokens: int

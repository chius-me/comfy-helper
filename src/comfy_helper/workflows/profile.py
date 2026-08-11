import copy
from typing import Any

from pydantic import BaseModel, Field


class WorkflowDefaults(BaseModel):
    negative_prompt: str
    width: int = 1024
    height: int = 1024
    steps: int
    cfg: float


class ParameterBinding(BaseModel):
    node_id: str
    input_name: str


class WorkflowProfile(BaseModel):
    id: str
    name: str
    description: str
    provider: str = "comfyui"
    model_family: str
    model_dependencies: list[str] = Field(default_factory=list)
    defaults: WorkflowDefaults
    template: dict[str, Any] = Field(exclude=True)
    bindings: dict[str, ParameterBinding] = Field(exclude=True)

    def render(self, parameters: dict[str, Any]) -> dict[str, Any]:
        values = self.defaults.model_dump()
        values.update(
            {key: value for key, value in parameters.items() if value is not None}
        )
        workflow = copy.deepcopy(self.template)
        for parameter_name, binding in self.bindings.items():
            if parameter_name in values:
                workflow[binding.node_id]["inputs"][binding.input_name] = values[
                    parameter_name
                ]
        return workflow

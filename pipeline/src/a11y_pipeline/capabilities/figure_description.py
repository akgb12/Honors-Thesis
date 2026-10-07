import json
from pathlib import Path

from a11y_pipeline.capabilities.base import (
    CapabilityResult,
    FigureDescriptionInput,
    FigureDescriptionOutput,
)
from a11y_pipeline.ir.models import HistoryEntry, Patch
from a11y_pipeline.models.client import ModelClient, ModelMessage, ModelRequest

PROMPT_VERSION = "figure_description_v1"
DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_MAX_TOKENS = 1000


class FigureDescriptionCapability:
    def __init__(
        self,
        client: ModelClient,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        prompt_path: Path | None = None,
    ) -> None:
        # Store model settings and load the fixed prompt
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        if prompt_path is None:
            prompt_path = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md"
        self.prompt = prompt_path.read_text(encoding="utf-8").strip()

    def build_request(self, capability_input: FigureDescriptionInput) -> ModelRequest:
        # Build a source neutral multimodal request
        context: dict[str, object] = {
            "element_id": capability_input.element_id,
            "subtype": capability_input.subtype,
            "visible_labels": capability_input.visible_labels,
            "slide_title": capability_input.slide_title,
            "nearby_text": capability_input.nearby_text,
        }
        if capability_input.subtype == "diagram" and capability_input.source_code is not None:
            context["source_code"] = capability_input.source_code
        text = "Describe this figure using the following context.\n"
        text += json.dumps(context, ensure_ascii=False, sort_keys=True)
        message = ModelMessage(
            role="user",
            text=text,
            image_png=capability_input.image_png,
        )
        return ModelRequest(
            model=self.model,
            system=self.prompt,
            messages=[message],
            output_schema=FigureDescriptionOutput,
            prompt_version=PROMPT_VERSION,
            element_id=capability_input.element_id,
            max_tokens=self.max_tokens,
        )

    def run(
        self,
        capability_input: FigureDescriptionInput,
        run_id: str,
        round_number: int = 0,
    ) -> CapabilityResult:
        # Generate patches with one retry for malformed output
        request = self.build_request(capability_input)
        input_tokens = 0
        output_tokens = 0
        cost_usd = 0.0
        for _attempt in range(2):
            try:
                response = self.client.complete_structured(request)
                input_tokens += response.input_tokens
                output_tokens += response.output_tokens
                cost_usd += response.cost_usd
                output = FigureDescriptionOutput.model_validate(
                    response.output.model_dump(mode="python")
                )
            except (TypeError, ValueError):
                continue
            patches = self._success_patches(
                capability_input.element_id,
                output,
                round_number,
            )
            history = HistoryEntry(
                run_id=run_id,
                round=round_number,
                change="Generated figure description",
                by="model",
                model=self.model,
                prompt_version=PROMPT_VERSION,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
            )
            return CapabilityResult(patches=patches, history=history)
        failed_patch = Patch(
            element_id=capability_input.element_id,
            path="accessibility.status",
            value="failed",
            by="model",
            round=round_number,
            note="Figure description failed validation twice",
        )
        return CapabilityResult(patches=[failed_patch], history=None)

    def _success_patches(
        self,
        element_id: str,
        output: FigureDescriptionOutput,
        round_number: int,
    ) -> list[Patch]:
        # Create the successful accessibility patches
        values = [
            ("accessibility.alt_text", output.alt_text),
            ("accessibility.extended_description", output.extended_description),
            ("accessibility.decorative_suggested", output.decorative),
            ("accessibility.status", "model_generated"),
        ]
        patches: list[Patch] = []
        for path, value in values:
            patches.append(
                Patch(
                    element_id=element_id,
                    path=path,
                    value=value,
                    by="model",
                    round=round_number,
                    note="Generated figure description",
                )
            )
        return patches

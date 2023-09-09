from enum import Enum

from .tokens_holder import TokensHolder
from .pipe import TokenPipe
from ..constants import PIPELINE_SEND_CHUNK_NUM, DETOKENIZE_CHUNK_NUM


class JobStatus(Enum):
    WAITING = 1
    RUNNING = 2


class Job:
    def __init__(self):
        self.status: JobStatus = JobStatus.WAITING


class FillJob(Job):
    """Fill job is corresponding to the `prefill` stage in LLM.

    Its mission is to fill the KV cache in the execution engine, extending the context
    using the input tokens.
    """

    def __init__(self, input_holder: TokensHolder):
        super().__init__()
        self.input_holder: TokensHolder = input_holder
        self.input_holder.consumers.append(self)
        self.input_pipe = TokenPipe(PIPELINE_SEND_CHUNK_NUM)

    def __str__(self) -> str:
        return f"FillJob: input={self.input_holder}"


class GenerationJob(Job):
    """Generation job is corresponding to the `decode` stage in LLM.

    Its mission is to generate the output tokens based on certain context.
    """

    def __init__(self, output_holder: TokensHolder):
        super().__init__()
        self.output_holder: TokensHolder = output_holder
        assert self.output_holder.producer is None, "Concurrent writing to a holder"
        self.output_holder.producer = self
        self.detokenize_pipe = TokenPipe(DETOKENIZE_CHUNK_NUM)

    def __str__(self) -> str:
        return f"GenerationJob: output={self.output_holder}"

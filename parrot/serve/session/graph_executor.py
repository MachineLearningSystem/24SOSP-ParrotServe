# Copyright (c) 2023 by Microsoft Corporation.
# Licensed under the MIT license.

from typing import Optional, Dict

from parrot.utils import get_logger, create_task_in_loop
from parrot.exceptions import parrot_assert
from parrot.protocol.internal.primitive_request import Primitive, Fill, Generate
from parrot.protocol.internal.responses import FillResponse, GenerateResponse

from parrot.serve.graph import (
    ComputeGraph,
    RequestChain,
    CompletionChain,
)
from parrot.serve.scheduler import CompletionTask, GlobalScheduler

from ..engine_manager import EngineManager
from ..tokenizer_wrapper import TokenizersWrapper


logger = get_logger("GraphExecutor")


class GraphExecutor:
    """
    GraphExecutor in a session polls CompletionChain to GlobalScheduler,
    waiting for scheduling and execute it.
    """

    def __init__(
        self,
        session_id: int,
        scheduler: GlobalScheduler,
        engine_mgr: EngineManager,
        tokenizers_wrapper: TokenizersWrapper,
    ):
        # ---------- Basic Info ----------
        self.session_id = session_id
        self.graph = ComputeGraph()

        # ---------- Global Components ----------
        self.scheduler = scheduler
        self.engine_mgr = engine_mgr
        self.tokenizers_wrapper = tokenizers_wrapper

        # ---------- Exception Handling ----------
        self.bad_exception: Optional[Exception] = None

    async def _execute_coroutine(self, completion_chain: CompletionChain) -> None:
        """Coroutine for executing a CompletionChain."""

        try:
            # Blocking until all inputs are ready.
            for node in completion_chain.iter_fill():
                await node.wait_ready()

            # Create a task object for the completion chain.
            task = self.scheduler.create_task(completion_chain)

            # Tokenize the task.
            task.tokenize_chain(self.tokenizers_wrapper)

            # Submit the task to the scheduler and wait for the task to be scheduled.
            self.scheduler.submit_task(task)
            await task.scheduled.wait()
        except Exception as e:
            logger.error(
                f"Error when scheduling chain. (session_id={self.session_id}): {e}"
            )
            self.exception_interrupt(e)

        # Execute the task.
        await self.execute(task)

    def exception_interrupt(self, exception: BaseException):
        self.bad_exception = exception

    def add_request(self, request_chain: RequestChain) -> None:
        """Add a request to the graph and assign a coroutine to the request."""

        # Insert the request chain into the graph.
        self.graph.insert_and_update_request_chain(request_chain)

        # Create execution coroutines for the request chain.
        for completion_chain in request_chain.completion_chains:
            create_task_in_loop(self._execute_coroutine(completion_chain))

    async def execute(self, completion_task: CompletionTask) -> None:
        """Execute a CompletionTask."""

        parrot_assert(
            completion_task.engine is not None, "Execution engine is not available."
        )

        requires_token_ids = completion_task.engine.model_type
        if requires_token_ids:
            parrot_assert(
                completion_task.is_tokenized, "Tokenized result is not available."
            )
            tokenizer_name = completion_task.engine.tokenizer_name

        for i, node in enumerate(completion_task.chain.iter()):
            context = completion_task.ctxs[i]
            engine = context.engine

            # Skip the node if the context is ready.
            if context.ready_event.is_set():
                continue

            # Wait for the context to be ready if the Context is started.
            if context.start_event.is_set():
                await context.ready_event.wait()

            # Set the start event to indicate the context is started.
            context.start_event.set()

            try:
                if node.is_gen:
                    # TODO(chaofan): Add streaming generation support.
                    if requires_token_ids:
                        primitive = Generate(
                            session_id=self.session_id,
                            task_id=completion_task.task_id,
                            context_id=context.context_id,
                            parent_context_id=context.parent_context_id,
                            end_flag=False,
                            sampling_config=node.sampling_config,
                        )
                        resp = await primitive.apost(engine.http_address)
                        generated_ids = resp.generated_ids
                        generated_text = self.tokenizers_wrapper.detokenize(
                            token_ids=generated_ids,
                            tokenizer_name=tokenizer_name,
                        )

                        # Set the content of the node.
                        node.sv.set(content=generated_text)
                else:
                    if requires_token_ids:
                        token_ids = completion_task.tokenized_result[tokenizer_name][i]
                        primitive = Fill(
                            session_id=self.session_id,
                            task_id=completion_task.task_id,
                            context_id=context.context_id,
                            parent_context_id=context.parent_context_id,
                            end_flag=False,
                            token_ids=token_ids,
                        )
                        logger.debug(
                            f"Task {completion_task.task_id} (session_id={self.session_id}) submit Fill primitive (tokens num: {len(token_ids)})"
                        )
                        resp = await primitive.apost(engine.http_address)
                    else:
                        text = node.get()
                        primitive = Fill(
                            session_id=self.session_id,
                            task_id=completion_task.task_id,
                            context_id=context.context_id,
                            parent_context_id=context.parent_context_id,
                            end_flag=False,
                            text=text,
                        )
                        logger.debug(
                            f"Task {completion_task.task_id} (session_id={self.session_id}) submit Fill primitive (text len: {len(text)})"
                        )
                        resp = await primitive.apost(engine.http_address)
            except Exception as e:
                logger.error(
                    f"Error when executing node {node}. (session_id={self.session_id}): {e}"
                )
                self.engine_mgr.raise_exception(engine_id=engine.engine_id, exception=e)
                self.exception_interrupt(e)
                break

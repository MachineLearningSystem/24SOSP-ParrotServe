import asyncio
import parrot
from parrot.engine.native.engine import NativeExecutionEngine
from Parrot.parrot.engine.primitive_job import PrimitiveJob, Fill, Generation
from parrot.utils import create_task_in_loop
from parrot.protocol.sampling_config import SamplingConfig
from transformers import AutoTokenizer


def test_engine_simple_serving():
    # The config path is relative to the package path.
    # We temporarily use this way to load the config.
    package_path = parrot.__path__[0]
    engine = NativeExecutionEngine(
        package_path + "/../configs/backend/native/opt_125m.json"
    )

    async def execute_job(job: PrimitiveJob):
        engine.add_job(job)
        await job.finish_event.wait()

    prompt_text = "Hello, my name is"
    tokenizer = AutoTokenizer.from_pretrained("facebook/opt-125m")
    prompt_tokens = tokenizer(prompt_text)["input_ids"]

    async def main():
        create_task_in_loop(engine.execute_loop())

        print("Start")

        # Prefill
        await execute_job(
            Fill(
                client_id="test",
                session_id=0,
                context_id=0,
                parent_context_id=-1,
                token_ids=prompt_tokens,
            )
        )

        gen_job = Generation(
            client_id="test",
            session_id=0,
            context_id=0,
            parent_context_id=-1,
            sampling_config=SamplingConfig(
                max_gen_length=40,
                ignore_tokenizer_eos=True,
            ),
        )
        await execute_job(gen_job)
        print(tokenizer.decode(gen_job.context.token_ids))

    try:
        asyncio.run(main(), debug=True)
    except BaseException as e:
        print("Internal error happends:", e)


if __name__ == "__main__":
    test_engine_simple_serving()

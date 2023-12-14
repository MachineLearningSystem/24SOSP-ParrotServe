#!/bin/sh

rm *.log -rf

bash fastchat/launch_vllm.sh

export OPENAI_API_BASE=http://localhost:8000/v1
export OPENAI_API_KEY=EMPTY

sleep 1

python3 benchmark_serving_vllm.py --workload-info "../workloads/gpts/top4.json" \
    --num-prompts 500 \
    --request-rate 2 \
    > 2.log

sleep 1

bash ../../scripts/kill_all_fastchat_servers.sh
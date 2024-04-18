#!/bin/sh

rm -rf log
rm *.log -rf

bash fastchat/launch_vllm.sh

pwd=$PWD
log_path=$pwd/log/

# Launch cluster
cd cluster_1_openai
bash launch.sh $log_path os.log engine.log
sleep 2

# Run benchmark
cd ..

python3 bench_chain_summarization.py > 1.log

sleep 1

bash ../../scripts/kill_all_fastchat_servers.sh
bash ../../scripts/kill_all_servers.sh
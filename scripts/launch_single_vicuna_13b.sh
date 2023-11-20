#!/bin/sh
echo "Start OS server ..."
python3 -m parrot.os.http_server --config_path sample_configs/os/localhost_os.json --log_dir log/ --log_filename os_single_vicuna_13b.log &

sleep 1

echo "Start one single Vicuna 13B server ..."
python3 -m parrot.engine.http_server --config_path sample_configs/engine/vicuna-13b-v1.3-vllm.json --log_dir log/ --log_filename engine_single_vicuna_13b.log &

sleep 15

echo "Successfully launched Parrot runtime system."
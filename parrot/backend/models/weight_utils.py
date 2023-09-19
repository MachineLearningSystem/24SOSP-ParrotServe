# Adapted from
# https://github.com/vllm-project/vllm/blob/main/vllm/model_executor/weight_utils.py
# Copyright 2023 The vLLM team.

"""Utilities for downloading and initializing model weights."""
import filelock
import glob
import json
import os
from typing import Iterator, Optional, Tuple

from huggingface_hub import snapshot_download
import numpy as np
import torch
from tqdm.auto import tqdm


def hf_model_weights_iterator(
    model_name_or_path: str,
    cache_dir: Optional[str] = None,
    use_np_cache: bool = False,
) -> Iterator[Tuple[str, torch.Tensor]]:
    # Prepare file lock directory to prevent multiple processes from
    # downloading the same model weights at the same time.
    lock_dir = cache_dir if cache_dir is not None else "/tmp"
    lock_file_name = model_name_or_path.replace("/", "-") + ".lock"
    lock = filelock.FileLock(os.path.join(lock_dir, lock_file_name))

    # Download model weights from huggingface.
    is_local = os.path.isdir(model_name_or_path)
    if not is_local:
        with lock:
            hf_folder = snapshot_download(
                model_name_or_path,
                allow_patterns="*.bin",
                cache_dir=cache_dir,
            )
    else:
        hf_folder = model_name_or_path

    hf_bin_files = [
        x
        for x in glob.glob(os.path.join(hf_folder, "*.bin"))
        if not x.endswith("training_args.bin")
    ]

    if use_np_cache:
        # Convert the model weights from torch tensors to numpy arrays for
        # faster loading.
        np_folder = os.path.join(hf_folder, "np")
        os.makedirs(np_folder, exist_ok=True)
        weight_names_file = os.path.join(np_folder, "weight_names.json")
        with lock:
            if not os.path.exists(weight_names_file):
                weight_names = []
                for bin_file in hf_bin_files:
                    state = torch.load(bin_file, map_location="cpu")
                    for name, param in state.items():
                        param_path = os.path.join(np_folder, name)
                        with open(param_path, "wb") as f:
                            np.save(f, param.cpu().detach().numpy())
                        weight_names.append(name)
                with open(weight_names_file, "w") as f:
                    json.dump(weight_names, f)

        with open(weight_names_file, "r") as f:
            weight_names = json.load(f)

        for name in weight_names:
            param_path = os.path.join(np_folder, name)
            with open(param_path, "rb") as f:
                param = np.load(f)
            yield name, torch.from_numpy(param)
    else:
        for bin_file in hf_bin_files:
            state = torch.load(bin_file, map_location="cpu")
            for name, param in state.items():
                yield name, param
            del state
            torch.cuda.empty_cache()


def initialize_dummy_weights(
    model: torch.nn.Module,
    low: float = -1e-3,
    high: float = 1e-3,
) -> None:
    """Initialize model weights with random values.

    The model weights must be randomly initialized for accurate performance
    measurements. Additionally, the model weights should not cause NaNs in the
    forward pass. We empirically found that initializing the weights with
    values between -1e-3 and 1e-3 works well for most models.
    """
    for param in model.state_dict().values():
        param.data.uniform_(low, high)

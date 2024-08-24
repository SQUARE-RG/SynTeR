# SynTeR

### Introduction
This repository hosts the codes and data for the paper "Fix the Tests: Augmenting LLMs to Repair Test Cases with Static Collector and Neural Reranker", accepted in in the 35th IEEE International Symposium on Software Reliability Engineering (ISSRE 2024). 

The work introduces SynTeR for automated test repair using Large Language Models, where it augments LLM's capability by constructing precisely related contexts with static analysis and reranking.

### Approaches Overview
- **SynTeR**: A novel contexts-aware test repair approach based on LLMs. Running script: `run_update_ctx.py`.
- **NaiveLLM** (baseline): A naive test repair approach without contexts based on LLMs. Running script: `run_update_woctx.py`.
- **CEPROT** (baseline): A SOTA test repair approach without contexts based on CodeT5, which we replicate elsewhere. In this repository, we only provide the results of CEPROT.

### Repository Contents
- `dataset`: The benchmark dataset used for evaluating SynTeR against baselines.
- `logs`: Logs when running scripts.
- `outputs`: The output results of approaches and evaluation.
- `retriever`: The source codes of retriever for SynTeR, which is used to retrieve related contexts.
- `utils`: The source codes of utilities for SynTeR, which provides abilities of parser, formatter configs and etc. 
- `README.md`: This file.
- ***Jupyter Notebooks***: 
  - `dataset_setup.ipynb`: The notebook for setting up projects in the datasets (Before running SynTeR, all the projects should be downloaded locally).
  - `human_eval.ipynb`: The notebook for assisting human evaluation.
- ***Running Scripts***:
  - `run_setup.py`: The script for setting up test_part dataset (download the repos).
  - `run_update_ctx.py`: The script for running SynTeR.
  - `run_update_woctx.py`: The script for running NaiveLLM.
  - `run_evaluate.py`: The script for evaluation (RQ1) on CodeBLEU, DiffBLEU, and Accuracy.

### Environment Setup
Before running the scripts, make sure the environment has been built correctly following the steps below.

- **Environment requirements**. It is recommended to run SynTeR in a Linux(Ubuntu) OS. Our approach can be applied on most modern machines (RAM capacity: >=32GB), where the most CPU-costing task is running the `bge-reranker-v2-m3` reranker model locally.

- **Python environment setup**. 
  - We recommend using [miniconda](https://docs.anaconda.com/miniconda/) to setup a virtual environment
    ```bash
    conda create -n synter_venv python=3.11
    conda activate synter_venv
    ``` 
  - Install the required python packages:

    ```bash
    pip install -r requirements.txt
    ```

- Install [ClangFormat](https://clang.llvm.org/docs/ClangFormat.html) locally. 
  ```bash
  sudo apt install clang-format
  ```
  Check your installation by running the following command in your shell:
  ```bash
  clang-format --version
  ```

- Download the Reranker Model (refer to: [bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3/tree/main)) to your local path, which should be consistent with the path in `utils/configs.py`.

### Run SynTeR

We provide a sample for testing SynTeR in `dataset/test_part.json`. By default, the scripts will repair the test case in `dataset/test_part.json`. 

- **Customize your configuration**. Add your custom configs in `utils/configs.py`, detailed guides are shown in the file.

- **Download the repository locally for the dataset**. Since we use `test_part.json` as the test dataset, we only need to download the corresponding project: Alluxio/Alluxio. You can finish this by `run_setup.py` or `dataset_setup.ipynb`.
  ```bash
  python run_setup.py
  ```

- **Run SynTeR**:

  ```bash
  python run_update_ctx.py
  ```
  The results will be saved in `outputs/SynTeR/test_part_all_ctx_wot.json`. The log is generated in `logs/run_update_ctx.log` (we also retain backups for reference). 

- **Run NaiveLLM** (optionally)
  ```bash
  python run_update_woctx.py
  ```
  The results will be saved in `outputs/NaiveLLM/test_part_woctx.json`. The log is in `logs/run_update_woctx.log` (we also retain backups for reference). 

- **Important Notes**: Due to the limitation of *multilsp*, the language server sometimes may not be correctly closed as expected. Therefor, sometimes you may encounter *Internal Errors* when running SynTeR for multilsp. Just rerun the script until you get the expected results. For above issues, remember to check whether there are zombie processes using language servers after running the script of SynTeR.
  ```bash
  # check
  ps aux | grep 'language_servers' | grep -v grep
  # kill
  ps aux | grep 'language_servers' | grep -v grep | awk '{print $2}' | xargs kill
  ```

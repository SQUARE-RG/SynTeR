# SynTeR

## Introduction
This repository hosts the codes and data for the paper "Fix the Tests: Augmenting LLMs to Repair Test Cases with Static Collector and Neural Reranker", accepted in in the 35th IEEE International Symposium on Software Reliability Engineering (ISSRE 2024). 

The work introduces SynTeR for automated test repair using Large Language Models, where it augments LLM's capability by constructing precisely related contexts with static analysis and reranking.

## Approaches Overview
- **SynTeR**: A novel contexts-aware test repair approach based on LLMs. Running script: `run_update_ctx.py`.
- **NaiveLLM** (baseline): A naive test repair approach without contexts based on LLMs. Running script: `run_update_woctx.py`.
- **CEPROT** (baseline): A SOTA test repair approach without contexts based on CodeT5, which we replicate elsewhere. In this repository, we only provide the results of CEPROT.

## Repository Contents
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

## Getting Started in Docker 
>Be aware of the important notices at the end of this README before testing SynTeR.
### 1. Download & Load Docker Image
- Download and Load the docker image with prepared environments.
  ```bash
  # assume that you have downloaded the image [synter-ubuntu.tar] form DOI: 10.5281/zenodo.13369956
  docker load -i <local-path-to>/synter-ubuntu.tar
  docker run -it -d --name synter-demo synter-ubuntu /bin/bash
  ```

- Notes: all the repositories will be saved at `/root/SynPTCEvo4J/repos` as already configured in `utils/configs.py`.

### 2. Run SynTeR in the Container
- **Move to the workspace**.
  ```bash
  cd /root/SynTeR
  ```
- **Add LLM configuarations**. The default LLM used is GPT4 from OPENAI.
  - utils/configs: your LLM API keys.
  - [optional]utils/llm.py: if you want to use another OPENAI model or custom LLMs compatible with OPENAI API(such as DeepseekCoder), you should also modify the model here.
- **Run SynTeR**. By default, the script will repair the test cases in `dataset/test_part.json`, where we provide the motivation example from `Alluxio/alluxio` demonstrated in our paper.
  ```bash
  python run_update_ctx.py
  ```
- **Run NaiveLLM** (optional). By default, the script will also repair the test cases in `dataset/test_part.json`.
  ```bash
  python run_update_woctx.py
  ```
- *Note: If you want to add test samples, you can refer to `dataset/test.json`. For every sample, SynTeR will check whether the repo exists at `REPO_BASE=/root/SynPTCEvo4J/repos`, unloaded repos for the test datafile will be automatically cloned when you run SynTeR. You can also mannual clone them by `dataset_setup.ipynb` and `run_setup.py`, which is more recommended since large repo may fail to clone.*

## Getting Started from Scratch 
>Be aware of the important notices at the end of this README before testing SynTeR.
### 1. Environment Setup

- **Environment requirements**. It is recommended to run SynTeR in a Linux(Ubuntu) OS. Our approach can be applied on most modern machines (RAM capacity: >=32GB), where the most CPU-costing task is running the `bge-reranker-v2-m3` reranker model locally.

- **Creat and move to the workspace**.
  ```bash
  mkdir SynTeR && cd SynTeR
  ```

- **Python environment setup**. 
We recommend using [miniconda](https://docs.anaconda.com/miniconda/) to setup a virtual environment
  ```bash
  conda create -n synter_venv python=3.11
  conda activate synter_venv
  pip install -r requirements.txt
  ``` 

- **Install [ClangFormat](https://clang.llvm.org/docs/ClangFormat.html)**. 
  ```bash
  sudo apt install clang-format
  # check installation
  clang-format --version
  ```

- **Download the Reranker Model**. We use [bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3/tree/main) for reranking. The model should be downloaded to your local path, which should be consistent with the path in `utils/configs.py`.

### 2. Run SynTeR & NaiveLLM (optional)

By default, the scripts will repair the test cases in `dataset/test_part.json`, where we provide the motivation example demonstrated in our paper.

- **Customize your configuration**. Add your custom configs in `utils/configs.py`:
  - ***REPO_BASE***: the path to store all the repos (should have enough space).
  - ***RERANKER_MODEL_PATH***: the bge-reranker-v2-m3 download path (huggingface repo).
  - ***OPENAI_API_KEY***: your own OPEANAI API keys.
  - ***LANGCHAIN_API_KEY***: add it if you want to use LangSmith for LLM tracing.

- **Run SynTeR**: when SynTeR repairs a test case in the datafile, the corresponding repo will be automatically cloned into  ***REPO_BASE*** configured in `utils/configs.py`.

  ```bash
  python run_update_ctx.py
  ```
  The results will be saved in `outputs/SynTeR/test_part_all_ctx_wot.json`. The log is generated in `logs/run_update_ctx.log` (we also retain backups as reference). 

- **Run NaiveLLM** (optional)
  ```bash
  python run_update_woctx.py
  ```
  The results will be saved in `outputs/NaiveLLM/test_part_woctx.json`. The log is in `logs/run_update_woctx.log` (we also retain backups for reference). 

- *Note: If you want to add test samples, you can refer to `dataset/test.json`. For every sample, SynTeR will check whether the repo exists at `REPO_BASE=/root/SynPTCEvo4J/repos`, unloaded repos for the test datafile will be automatically cloned when you run SynTeR. You can also mannual clone them by `dataset_setup.ipynb` and `run_setup.py`, which is more recommended since large repo may fail to clone.*

## Important Notices!!!
Due to the limitation of *multilsp*, the language server sometimes may not be correctly closed as expected. Therefor, sometimes you may encounter *Internal Errors* when running SynTeR for multilsp. Just rerun the script until you get the expected results. For above issues, remember to check whether there are zombie processes using language servers after running the script of SynTeR.
  ```bash
  # check
  ps aux | grep 'language_servers' | grep -v grep
  # kill
  ps aux | grep 'language_servers' | grep -v grep | awk '{print $2}' | xargs kill
  ```
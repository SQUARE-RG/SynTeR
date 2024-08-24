### Modules in `Utils`
- **Configuration**
  - `utils/configs.py`: configuration file, containing API key and Path settings.

- **Wrapper for Static Analysis**
- `utils/parser.py`: provide the utility of parser (*tree-sitter*).
- `utils/formatter.py`: provide the utility of formatter (*ClangFormat*).
- `utils/gitter.py`: provide the utility to control the git repository of the project (*GitPython*).

- **Wrapper for Models**
  - `utils/reranker.py`: provide the utility to use reranker model, using *bge-reranker-v2-m3* here.
  - `utils/llm.py`: provide the utility to use Large Language Model (*GPT4* and *DeepSeekCoder*), which is convenient for adding integrations of other LLMs.

- **Wrapper for Others**
  - `utils/types.py`: provide the utility of types used for SynTeR.
  - `utils/logger.py`: provide the utility of custom logger for SynTeR.
  - `utils/helper.py`: provide other simple utilities for SynTeR.
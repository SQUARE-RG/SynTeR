# The path where you save all the repos (create the folder first if not exists)
REPO_BASE = "xxxxxxx/Projects/SynPTCEvo4J/repos"

# The path of your reranker
RERANKER_MODEL_PATH = "xxxxxxx/Projects/codeLLM/Reranker/bge-reranker-v2-m3"

# LLM Inference API - enter your API key here
# If you use other LLMs, custom your API setting (base_url and model) in utils/llm.py
OPENAI_API_KEY = "xxxxxxx"

# LangChain LangSmith to trace your queries to LLM
# If you don't need it, simply set the value to ""
LANGCHAIN_API_KEY = ""

# # [Deprecated] use tree-sitter-java instead
# TREESITTER_LANG_SO = (
#     "xxxx/tools/parser/build/my-languages.so"
# )

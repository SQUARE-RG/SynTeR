from langchain_openai import ChatOpenAI
from utils.configs import OPENAI_API_KEY


# model initialization
# llm_model = ChatOpenAI(
#     api_key=OPENAI_API_KEY,
#     model="gpt-4",
#     temperature=0.1,
# )
# you can also custom your own Model API
llm_model = ChatOpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.deepseek.com",
    model="deepseek-coder",
    temperature=0.1,
)

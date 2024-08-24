"""
    Run SynTeR with Contexts
"""

import json, time, os
from utils.configs import LANGCHAIN_API_KEY
from langsmith import Client
from langchain_core.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain_core.output_parsers import StrOutputParser
from utils.types import UpdateInfo
from utils.parser import get_code_without_comments
from utils.formatter import formatted_java_code
from retriever.main_retriever import retrieve_context
from utils.helper import get_diff, read_examples, extract_code
from utils.llm import llm_model as model
from utils.logger import logger

# Langsmith setup
if LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = f"SynTeR Test"
    os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
    os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
    client = Client()


# System message
system_prompt = """You are an expert in Java code evolution and test update. \
Syntactic change introduced in focal method will lead to build failure in associated tests. \
You need to repair the test method based on the signature changes of focal method. \
Related context will be given at the end of every query. Remember you should only response with the code of repaired test method without further explanation."""
system_message_prompt = SystemMessagePromptTemplate.from_template(system_prompt)

# human message
human_prompt = """\
The following is a unit test method:
```java
{test_src}
```
Now the corresponding focal method undergoes the following syntactic changes:
```java
{focal_diff}
```
Update the test code based on the change of the focal method, you can also refer to the contexts below:\n
{global_context}
"""
human_message_template = HumanMessagePromptTemplate.from_template(human_prompt)

# full prompt generation
prompt = ChatPromptTemplate.from_messages(
    [system_message_prompt, human_message_template]
)

# pipline to generate the response
chain = prompt | model | StrOutputParser() | extract_code


def construct_update_query(update_info: UpdateInfo, clean_tests: bool = False) -> dict:
    """
    For every example in the dataset, construct the query with inputs and contexts
    """
    # Construct query
    query_json = dict()

    focal_src_clean = get_code_without_comments(update_info.focal_src)
    focal_src_fmt = formatted_java_code(focal_src_clean)
    focal_tgt_clean = get_code_without_comments(update_info.focal_tgt)
    focal_tgt_fmt = formatted_java_code(focal_tgt_clean)
    format_prefix = "@@\n\n"
    if focal_src_fmt and focal_tgt_fmt:
        diff_str = get_diff(focal_src_fmt, focal_tgt_fmt)
    else:
        diff_str = get_diff(update_info.focal_src, update_info.focal_tgt)
    # extract code content
    start = diff_str.find(format_prefix)
    query_json["focal_diff"] = diff_str[start + len(format_prefix) :]

    test_src_clean = get_code_without_comments(update_info.test_src)
    test_src_fmt = formatted_java_code(test_src_clean)
    query_json["test_src"] = test_src_fmt if test_src_fmt else update_info.test_src
    # retrieve contexts
    contexts = ""
    retctx_list = retrieve_context(update_info, clean_tests, save_cache=False)
    for retctx in retctx_list:
        if len(retctx["contexts"]) > 0:
            contexts += f'- {retctx["info"]}\n'
            texts = "\n\n".join(retctx["contexts"])
            contexts += f"```java\n{texts}\n```\n\n"
    logger.info(f"Retrieved Context: \n{contexts}")
    query_json["global_context"] = contexts.strip()

    return query_json


def main():
    # config for data files
    query_datafile = "dataset/synPTCEvo4j/test_part.json"
    output_datafile = "outputs/SynTeR/test_part_all_ctx_wot.json"

    # logger setup(use 'a' to log every run)
    logger.set_log_file("logs/run_update_ctx.log", "w")

    write_to_file = True
    # Default Setting: we ignore contexts in the test codes
    clean_tests = True
    # construct query_json from datafile
    error_list = []
    outputs = []

    examples = read_examples(query_datafile)
    logger.info(f"{'*******'*5}")
    logger.info(f"{'*******'*5}")
    logger.info(
        f"Start processing {len(examples)} items in {query_datafile} (write_to_file:{write_to_file}, clean_tests:{clean_tests})"
    )

    # incremental update
    processed_count = 0
    if write_to_file and os.path.exists(output_datafile):
        with open(output_datafile, "r") as fo:
            content = json.load(fo)
        if content:
            outputs = content
            processed_count = len(outputs)
            # not include
            logger.info(
                f"The data with [id<={outputs[-1]['id']}] in {query_datafile} has been processed, results can be found in {output_datafile}."
            )
            logger.info(f"Continue processing from item id: {outputs[-1]['id'] + 1}")

    for i, exp in enumerate(examples[processed_count:]):
        i = processed_count + i
        logger.info(f"==> Processing item id: {i}")

        # construct query and invoke LLM chain
        update_info = UpdateInfo(exp)
        update_query = construct_update_query(update_info, clean_tests)
        res = chain.invoke(update_query)

        test_tgt_clean = get_code_without_comments(exp.test_db["method_tgt"])
        test_tgt_fmt = formatted_java_code(test_tgt_clean)
        outputs.append(
            {
                "id": i,
                "original": update_query["test_src"],
                "prediction": res,
                "reference": test_tgt_fmt,
            }
        )
        if res:
            logger.info(f"Output updated test code:\n{res}")
            logger.info(f"Complete for item: {i}; Error list: {error_list}")
        else:
            logger.error(f"[Parse Error]LLM output cannot be parsed as code.")
            error_list.append(i)
            logger.error(f"Error raises for item: {i}")

        if write_to_file:
            with open(output_datafile, "w") as fo:
                json.dump(outputs, fo, indent=4)

        logger.info(f"{'====='*5}")
        time.sleep(5)

    if write_to_file:
        logger.info(f"Finish writing items to {output_datafile}")
        if len(error_list) > 0:
            logger.error(
                f"Error occurs in process!\nError list[{len(error_list)}]: {error_list}"
            )
        logger.info(
            f"All {len(examples)-len(error_list)} results are written to {output_datafile}."
        )


if __name__ == "__main__":
    main()

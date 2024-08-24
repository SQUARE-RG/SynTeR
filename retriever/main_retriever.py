"""
    Retrieve the most related(topk) context to update obsolete test using bge-reranker (FlagEmbedding).
    - Query: extracted stmts from source test method by local_extractor.
    - Documents: collected global context from focal method by global_collector.
"""

import time, random, json, os
from langsmith import Client
from utils.configs import REPO_BASE
from utils.types import UpdateInfo, RetCtx
from utils.multilspy import SyncLanguageServer
from utils.multilspy.multilspy_config import MultilspyConfig
from utils.multilspy.multilspy_logger import MultilspyLogger
from utils.multilspy.multilspy_types import Position
from utils.multilspy.multilspy_exceptions import MultilspyException
from utils.gitter import UpdateRepo, setup_repo
from utils.reranker import rerank_with_query, rerank_usages_with_query
from utils.helper import read_examples, expand_pos_list_fmtf
from utils.parser import (
    extract_method_metadata,
    get_param_idx_diff,
    get_new_types_poslist,
    get_method_signature,
    divide_texts_by_type,
)
from .global_collector import (
    collect_method_diffctx,
    collect_usages_diffctx,
    collect_clsctx_for_params,
    collect_clsctx_for_return,
)
from .local_extractor_stmts import extract_stmts_to_update
from .local_extractor_operations import (
    extract_args_operations,
    extract_return_operations,
)
from utils.logger import logger


# [SETUP] Basic config for LSP
lsp_config = MultilspyConfig.from_dict(
    {"code_language": "java", "trace_lsp_communication": True}
)
lsp_logger = MultilspyLogger()


# [Diff Context]Retrieve usages contexts
def run_usages_retriever(
    lsp: SyncLanguageServer,
    update_info: UpdateInfo,
    repo: UpdateRepo,
    stmts: str,
    clean_tests: bool = False,
) -> RetCtx:
    logger.info(f"[Enter Usages Retriever]")
    logger.info(f"+++ Starting Usages DiffCtx Retriever")
    logger.info(f"+ Running Usages DiffCtx Collector")
    usage_diff_texts = list(collect_usages_diffctx(lsp, repo, update_info, clean_tests))
    logger.info(f"+ Found {len(usage_diff_texts)} diff texts for usages.")
    usage_info = "Usages diff texts of the focal method (examples of changes to use the updated focal method)"

    if len(usage_diff_texts) <= 3:
        logger.info(f"+++ Exit Usages DiffCtx Collector")
        logger.info(f"[Exit Usages Retriever]")
        usage_retctx: RetCtx = {
            "info": usage_info,
            "contexts": usage_diff_texts,
        }
        return usage_retctx

    logger.info(f"+ Running Focal DiffCtx Reranker")

    final_texts = rerank_usages_with_query(stmts, usage_diff_texts)
    # final_texts = rerank_with_query_ref(stmts, usage_diff_texts, usage_del_texts)
    usage_retctx: RetCtx = {
        "info": usage_info,
        "contexts": final_texts,
    }
    logger.info(f"+ Retrieved {len(final_texts)} diff texts for usages.")

    logger.info(f"+++ Exit Usages DiffCtx Collector")
    logger.info(f"[Exit Usages Retriever]")
    return usage_retctx


def run_param_retriever(
    lsp: SyncLanguageServer, update_info: UpdateInfo, pidr_pos_list: list[Position]
) -> list[RetCtx]:
    """
    1. Collect global context using a language server for the target focal method.
    2. Rerank the collected context with extracted operations as query.
    """
    if not lsp.language_server.server_started:
        logger.Error("run_param_retriever called before Language Server started")
        raise MultilspyException("Language Server not started")
    logger.info(f"### Starting Param ClassCtx Retriever")
    logger.info(f"# Running ClassCtx Collector for Param types")

    # collect the classctx for pidr_pos_list in focal_relpath
    focal_relpath = update_info.focal_relpath
    clsctx_list = collect_clsctx_for_params(lsp, focal_relpath, pidr_pos_list)

    # Check clsctx_list
    if len(clsctx_list) == 0:
        logger.info(f"# No class contexts are collected.")
        logger.info(f"### Exit Param ClassCtx Retriever")
        return []

    # extract operations for params
    focal_src_md = extract_method_metadata(update_info.focal_src)
    focal_tgt_md = extract_method_metadata(update_info.focal_tgt)
    obs_params_idx = get_param_idx_diff(
        focal_src_md["param_types"], focal_tgt_md["param_types"]
    )[0]
    constructions, accesses = extract_args_operations(
        update_info.test_src,
        focal_src_md["name"],
        focal_src_md["param_names"],
        obs_params_idx,
    )
    logger.info(
        f"# [Local Extractor]Extracted constructions for params: {constructions}"
    )
    logger.info(f"# [Local Extractor]Extracted accesses for params: {accesses}")

    # rerank to get topk texts for each class type
    param_retctx_list: list[RetCtx] = []
    for class_ctx in clsctx_list:
        logger.info(
            f"# Running ClassCtx Reranker for param type: \"{class_ctx['class_type']}\""
        )
        # divide texts
        construct_texts = class_ctx["default_texts"]
        other_texts = class_ctx["splitted_texts"]
        final_texts = []

        # rerank constructions (constructions should not be null)
        if not constructions:
            # default constructor
            constructions.add("")
        lower_bound = max(len(constructions) * 2, 3)
        if len(construct_texts) <= lower_bound:
            final_texts.extend(construct_texts)
        else:
            for construct_stmt in constructions:
                query = f"Construct an instance of class {class_ctx['class_type']} with reference: {construct_stmt}"
                final_texts.extend(rerank_with_query(query, construct_texts))

        # rerank accesses
        lower_bound = max(len(accesses) * 2, 3)
        if len(other_texts) <= lower_bound:
            final_texts.extend(other_texts)
        else:
            for access_stmt in accesses:
                query = f"Member access with reference: {access_stmt}"
                final_texts.extend(rerank_with_query(query, other_texts))

        # random insert 3 if len(final_texts)<3
        if len(final_texts) < 3:
            unuse_texts = (set(construct_texts) | set(other_texts)) - set(final_texts)
            add_num = min(len(unuse_texts), 3 - len(final_texts))
            final_texts.extend(random.sample(sorted(unuse_texts), add_num))

        # delete repeat texts
        final_texts = list(dict.fromkeys(final_texts))
        # res_str = f"\n{'----'*20}\n".join(final_texts)
        logger.info(
            f"# Retrieved {len(final_texts)} texts for param type: \"{class_ctx['class_type']}\""
        )

        # for inner classes, get the class_type
        final_dict = {}
        for text in final_texts:
            if text.startswith("##"):
                spliter = text.find("\n")
                sub_class = text[2:spliter]
                class_name = f"{class_ctx['class_type']}.{sub_class}"
                if class_name in final_dict:
                    final_dict[class_name].append(text[spliter + 1 :])
                else:
                    final_dict[class_name] = [text[spliter + 1 :]]
            else:
                if class_ctx["class_type"] in final_dict:
                    final_dict[class_ctx["class_type"]].append(text)
                else:
                    final_dict[class_ctx["class_type"]] = [text]
        for class_name, texts in final_dict.items():
            param_retctx_list.append(
                {
                    "info": f"Defined in class {class_name} (optional references)",
                    "contexts": texts,
                }
            )
    logger.info(f"### Exit Param ClassCtx Retriever")
    return param_retctx_list


def run_return_retriever(
    lsp: SyncLanguageServer, update_info: UpdateInfo, ridr_pos_list: list[Position]
) -> list[RetCtx]:
    """
    1. Collect global context using a language server for the target focal method.
    2. Rerank the collected context with extracted operations as query.
    """
    if not lsp.language_server.server_started:
        logger.Error("ctx_from_definition called before Language Server started")
        raise MultilspyException("Language Server not started")
    logger.info(f"### Starting Return ClassCtx Retriever")
    logger.info(f"# Running ClassCtx Collector for Return types")

    # collect the classctx for ridr_pos_list in focal_relpath
    focal_relpath = update_info.focal_relpath
    clsctx_list = collect_clsctx_for_return(lsp, focal_relpath, ridr_pos_list)
    if len(clsctx_list) == 0:
        logger.info(f"# No class contexts are collected.")
        logger.info(f"### Exit Param ClassCtx Retriever")
        return []

    # extract operations for return
    focal_src_md = extract_method_metadata(update_info.focal_src)
    intermediates, accesses = extract_return_operations(
        update_info.test_src, focal_src_md["name"], focal_src_md["type"]
    )
    logger.info(
        f"# [Local Extractor]Extracted intermidiates for return: {intermediates}"
    )
    logger.info(f"# [Local Extractor]Extracted accesses for params: {accesses}")

    return_retctx_list: list[RetCtx] = []
    # get the types of intermediates
    inter_types = set()
    for intermediate_stmt in intermediates:
        inter_type = intermediate_stmt.split(":")[0].strip()
        if inter_type not in inter_types:
            inter_types.add(inter_type)

    # Reranking for each class type
    for class_ctx in clsctx_list:
        logger.info(
            f"# Running ClassCtx Reranker for return type: \"{class_ctx['class_type']}\""
        )
        final_texts = []
        all_texts = class_ctx["splitted_texts"]
        texts = all_texts
        # rerank intermediates -- inter_texts
        for inter_type in inter_types:
            inter_texts, texts = divide_texts_by_type(texts, inter_type)
            query = f"Get an instance of class {inter_type}"
            final_texts.extend(rerank_with_query(query, inter_texts))

        # rerank accesses -- texts
        lower_bound = max(len(accesses) * 2, 3)
        if len(texts) <= lower_bound:
            final_texts.extend(texts)
        else:
            for access_stmt in accesses:
                query = f"Member access with reference: {access_stmt}"
                final_texts.extend(rerank_with_query(query, texts))

        # random insert 3 if len(final_texts)<3
        if len(final_texts) < 3:
            unuse_texts = set(all_texts) - set(final_texts)
            add_num = min(len(unuse_texts), 3 - len(final_texts))
            final_texts.extend(random.sample(sorted(unuse_texts), add_num))

        final_texts = list(dict.fromkeys(final_texts))

        # res_str = f"\n{'----'*20}\n".join(final_texts)
        logger.info(
            f"# Retrieved {len(final_texts)} texts for return type: \"{class_ctx['class_type']}\""
        )
        final_dict = {}
        for text in final_texts:
            if text.startswith("##"):
                spliter = text.find("\n")
                sub_class = text[2:spliter]
                class_name = f"{class_ctx['class_type']}.{sub_class}"
                if class_name in final_dict:
                    final_dict[class_name].append(text[spliter + 1 :])
                else:
                    final_dict[class_name] = [text[spliter + 1 :]]
            else:
                if class_ctx["class_type"] in final_dict:
                    final_dict[class_ctx["class_type"]].append(text)
                else:
                    final_dict[class_ctx["class_type"]] = [text]
        for class_name, texts in final_dict.items():
            return_retctx_list.append(
                {
                    "info": f"Defined in class {class_name} (optional references)",
                    "contexts": texts,
                }
            )
    logger.info(f"### Exit Return ClassCtx Retriever")
    return return_retctx_list


def run_class_retriever(
    lsp: SyncLanguageServer, update_info: UpdateInfo
) -> list[RetCtx]:
    """
    Retrieve Class Context for specific diff type:
    1. Collect global class context for param type
    2. Collect global class context for return type
    """
    syn_diff = update_info.syn_diff
    if (syn_diff["param_types"] + syn_diff["type"]) == 0:
        return []

    # check lsp
    if not lsp.language_server.server_started:
        logger.Error("run_class_retriever called before Language Server started")
        raise MultilspyException("Language Server not started")

    # setup variables
    logger.info(f"[Enter Class Retriever]")
    # keep consistence between repo string and lsp string
    focal_src = update_info.focal_src.replace("\r\n", "\n")
    focal_tgt = update_info.focal_tgt.replace("\r\n", "\n")
    focal_relpath = update_info.focal_relpath

    # find the position of new type in both params and returns
    # pidr: parameter identifiers; ridr: return identifiers
    pidr_pos_list, ridr_pos_list = get_new_types_poslist(focal_src, focal_tgt)

    # No new types found in the signature diff
    if not pidr_pos_list and not ridr_pos_list:
        return []

    with lsp.open_file(focal_relpath):
        file_str = lsp.get_open_file_text(focal_relpath)

    class_retctx_list = []
    # retrieve new param types
    if syn_diff["param_types"] and len(pidr_pos_list) > 0:
        pidr_pos_list = expand_pos_list_fmtf(focal_tgt, file_str, pidr_pos_list)
        class_retctx_list.extend(run_param_retriever(lsp, update_info, pidr_pos_list))
    # retrieve new return types
    if syn_diff["type"] and len(ridr_pos_list) > 0:
        ridr_pos_list = expand_pos_list_fmtf(focal_tgt, file_str, ridr_pos_list)
        class_retctx_list.extend(run_return_retriever(lsp, update_info, ridr_pos_list))

    logger.info(f"[Exit Class Retriever]")
    return class_retctx_list


# [Diff Context]Retrieve additional contexts for focal method
def run_focal_retriever(
    lsp: SyncLanguageServer, update_info: UpdateInfo, repo: UpdateRepo, anal: str
) -> RetCtx:
    logger.info(f"$$$ Starting Focal DiffCtx Retriever")
    logger.info(f"$ Running Focal DiffCtx Collector")
    # collect focal method diffctx
    focal_diff_texts = collect_method_diffctx(
        lsp,
        repo,
        update_info.focal_relpath,
        update_info.focal_src,
        update_info.focal_tgt,
        "focal",
    )
    logger.info(f"$ Running Focal DiffCtx Reranker")
    anal = "cmdRegExpr"
    final_texts = rerank_with_query(anal, list(focal_diff_texts))
    focal_retctx: RetCtx = {
        "info": f"Diff texts in the scope of the focal method (optional references)",
        "contexts": final_texts,
    }
    # diffstr = "\n--\n".join(final_texts)
    logger.info(f"$ Retrieved {len(final_texts)} diff texts for focal method.")
    logger.info(f"$$$ Exit Focal DiffCtx Retriever")
    return focal_retctx


# [Diff Context]Retrieve additional contexts for test method
def run_test_retriever(
    lsp: SyncLanguageServer,
    update_info: UpdateInfo,
    repo: UpdateRepo,
    stmts: str,
    clean_tests: bool = False,
) -> RetCtx:
    logger.info(f"$$$ Starting Test DiffCtx Retriever")
    logger.info(f"$ Running Test DiffCtx Collector")
    # For practical usage, test has not been updated. Therefore, test_tgt = test_src
    if not update_info.test_tgt:
        update_info.test_tgt = update_info.test_src
    # collect test method diffctx
    test_diff_texts = collect_method_diffctx(
        lsp,
        repo,
        update_info.test_relpath,
        update_info.test_src,
        update_info.test_tgt,
        "test",
        clean_tests,
    )
    logger.info(f"$ Running Test DiffCtx Reranker")
    final_texts = rerank_with_query(stmts, list(test_diff_texts))
    test_retctx: RetCtx = {
        "info": f"Diff texts in the scope of the test method (new identifiers defined can be directly used in the new test)",
        "contexts": final_texts,
    }
    # diffstr = "\n--\n".join(final_texts)
    logger.info(f"$ Retrieved {len(final_texts)} diff texts for test method.")
    logger.info(f"$$$ Exit Test DiffCtx Retriever")
    return test_retctx


# [Diff Context]additional general retriever for stmts and diff context
def run_general_retriever(
    lsp: SyncLanguageServer,
    update_info: UpdateInfo,
    repo: UpdateRepo,
    anal: str,
    stmts: str,
    clean_tests: bool = False,
) -> tuple[RetCtx, RetCtx]:
    """
    1. call <local_extractor_stmts> to extract coarse_grained anal and stmts
    2. collect diff context for the focal method and test method
    3. rerank the collected diff context to get top2 respectively
    """
    logger.info(f"[Enter General Retriever]")

    # run retrievers
    focal_retctx = []
    test_retctx = []
    focal_retctx = run_focal_retriever(lsp, update_info, repo, anal)
    test_retctx = run_test_retriever(lsp, update_info, repo, stmts, clean_tests)

    logger.info(f"[Exit General Retriever]")
    return focal_retctx, test_retctx


def retrieve_context(
    update_info: UpdateInfo, clean_tests: bool = False, save_cache=False
) -> list[RetCtx]:
    """
    Retrieve context for a given focal method
    1. retrieve usages context.
    2. retrieve class context.
    3. retrieve additional general context.
    args: clean_tests: ignore other test codes when extracting contexts if True
          save_cache: save the intermediate values to cache if True
    """
    # update_repo = UpdateRepo(update_info.repo_root, update_info.commit_id)
    repo_name = os.path.relpath(update_info.repo_root, REPO_BASE)
    update_repo = setup_repo(repo_name, update_info.commit_id, do_clone=True)

    repo_root = update_info.repo_root
    lsp = SyncLanguageServer.create(lsp_config, lsp_logger, repo_root)
    logger.info(f"Initializing LSP for {repo_root}")
    all_retctx = []
    with lsp.start_server():
        # load and build
        time.sleep(10)
        logger.info(f"LSP loaded for {repo_root}")

        # extract stmts and analysis
        focal_src_sig = get_method_signature(update_info.focal_src)
        focal_tgt_sig = get_method_signature(update_info.focal_tgt)
        anal, stmts = extract_stmts_to_update(
            update_info.test_src, focal_src_sig, focal_tgt_sig
        )
        logger.info(f"$ [Local Extractor]Extracted focal diff analysis: {anal}")
        logger.info(f"$ [Local Extractor]Extracted obsolete stmts:\n{stmts}")

        # usages context
        usages_retctx = run_usages_retriever(
            lsp, update_info, update_repo, stmts, clean_tests
        )
        all_retctx.append(usages_retctx)
        # class context
        class_retctx = run_class_retriever(lsp, update_info)
        all_retctx.extend(class_retctx)
        # general context
        env_retctx = run_general_retriever(
            lsp, update_info, update_repo, anal, stmts, clean_tests
        )
        all_retctx.extend(env_retctx)

        # save intermediate results
        if save_cache:
            cache_path = "outputs/SynTeR/cache.json"
            if os.path.exists(cache_path):
                with open(cache_path, "r") as f:
                    caches = json.load(f)
            else:
                caches = []
            caches.append(
                {
                    "id": len(caches),
                    "Anal": anal,
                    "Stmts": stmts,
                    "UsagesCtx": usages_retctx,
                    "ClassCtx": class_retctx,
                    "EnvCtx": env_retctx,
                }
            )
            with open(cache_path, "w") as f:
                json.dump(caches, f, indent=4)
            logger.info(f"Saved intermediate results to {cache_path}")

    return all_retctx


if __name__ == "__main__":
    # os.environ["LANGCHAIN_TRACING_V2"] = "true"
    # os.environ["LANGCHAIN_PROJECT"] = f"SynTeR Contexts Cache"
    # os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
    # os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
    # client = Client()

    input_dataset = "dataset/synPTCEvo4j/test_part.json"
    clean_tests = True
    logger.set_log_file("logs/main_retriever.log", mode="a")

    examples = read_examples(input_dataset)
    logger.info(f"{'========='*5}")
    logger.info(f"{'========='*5}")
    logger.info(
        f"Start processing {len(examples)} items in {input_dataset} (collect caches, clean Tests: {clean_tests})"
    )

    for i, exp in enumerate(examples):
        logger.info(f"==> Processing item: {i}")
        update_info = UpdateInfo(exp)
        # retctx_list = retrieve_context(update_info, clean_tests, save_cache=True)
        retctx_list = retrieve_context(update_info, clean_tests, save_cache=True)
        contexts = ""
        for retctx in retctx_list:
            if len(retctx["contexts"]) > 0:
                contexts += f'- {retctx["info"]}\n'
                texts = "\n\n".join(retctx["contexts"])
                contexts += f"```java\n{texts}\n```\n\n"
        logger.info(f"Retrieved Context: \n{contexts}")
        time.sleep(5)

from FlagEmbedding import FlagReranker
from utils.configs import RERANKER_MODEL_PATH

# [SETUP] Initialize the FlagReranker
reranker = FlagReranker(RERANKER_MODEL_PATH, use_fp16=True)


def rerank_with_query(query: str, texts: list[str], topk=3) -> list[str]:
    """
    Reranks a list of texts based on a given query.

    Args:
        query (str): The query string.
        texts (list[str]): The list of texts to be reranked.
        topk (int, optional): The number of top texts to be returned. Defaults to 3.

    Returns:
        list[str]: The reranked list of texts.
    """
    if len(texts) <= topk:
        return texts
    queries = [query] * len(texts)
    query_text_pairs = list(zip(queries, texts))
    scores = reranker.compute_score(query_text_pairs)
    topk_index = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[
        :topk
    ]
    topk_texts = [texts[i] for i in topk_index]
    return topk_texts


def rerank_with_query_ref(
    query: str, base_texts: list[str], ref_texts: list[str], topk=3
) -> list[str]:
    """
    Reranks a list of base texts based on a given query and reference texts.

    Args:
        query (str): The query string.
        base_texts (list[str]): The list of original texts to be reranked.
        ref_texts (list[str]): The list of reference texts that are refered when reranking.
        topk (int, optional): The number of top texts to be returned. Defaults to 3.

    Returns:
        list[str]: The reranked list of texts.
    """
    assert len(base_texts) == len(
        ref_texts
    ), "The length of base_texts and ref_texts should be equal."
    if len(ref_texts) <= topk:
        return base_texts
    queries = [query] * len(ref_texts)
    query_text_pairs = list(zip(queries, ref_texts))
    scores = reranker.compute_score(query_text_pairs)
    topk_index = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[
        :topk
    ]
    topk_texts = [base_texts[i] for i in topk_index]
    return topk_texts


def rerank_usages_with_query(
    query: str, usage_diff_texts: list[str], topk=3
) -> list[str]:
    """
    Specificly reranks a list of usages texts based on a given query.

    1. Extract reference texts: source texts and target texts;
    2. Rerank score will be max(rerank(q, v_src), rerank(q, v_tgt))
    3. Get the topk usages texts based on the scores.

    """
    if len(usage_diff_texts) <= topk:
        return usage_diff_texts
    # construct contexts for reranker (rearrange the texts: src & tgt)
    usage_src_texts: list[str] = []
    usage_tgt_texts: list[str] = []
    for usage_diff in usage_diff_texts:
        diff_list = usage_diff.splitlines()
        text_src, text_tgt = "", ""
        # collect del texts
        for line in diff_list:
            if not line.startswith("+"):
                text_src += line.lstrip("-") + "\n"
        usage_src_texts.append(text_src[:-1])

        # collect add texts
        for line in diff_list:
            if not line.startswith("-"):
                text_tgt += line.lstrip("+") + "\n"
        usage_tgt_texts.append(text_tgt[:-1])

    # rerank usages
    queries = [query] * len(usage_diff_texts)
    pairs_src = list(zip(queries, usage_src_texts))
    scores_src = reranker.compute_score(pairs_src)
    pairs_tgt = list(zip(queries, usage_tgt_texts))
    scores_tgt = reranker.compute_score(pairs_tgt)
    scores = [max(s1, s2) for s1, s2 in zip(scores_src, scores_tgt)]
    topk_index = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[
        :topk
    ]
    topk_texts = [usage_diff_texts[i] for i in topk_index]
    return topk_texts

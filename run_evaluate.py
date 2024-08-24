"""
    Run Evaluation for Outputs
"""

import json
import os
import numpy as np
from codebleu import calc_codebleu
from codebleu.bleu import sentence_bleu
from utils.formatter import formatted_java_code
from utils.parser import filter_code, has_parse_error, get_code_without_comments
from utils.logger import logger
from utils.helper import get_diff

do_pass = False

# Baselines -- RQ1
# eval_datafile = "outputs/CEPROT/test_ceprot.json"
# type_info = "CEPROT"
# eval_datafile = "outputs/NaiveLLM/test_woctx.json"
# type_info = "NaiveLLM"
eval_datafile = "outputs/SynTeR/test_all_ctx_wot.json"
type_info = "SynTeR"
eval_resfile = "outputs/Evaluation/RQ1/summary.json"


# eval_resfile = os.path.splitext(eval_datafile)[0] + "_eval.json"
log_file = (
    f"outputs/Evaluation/RQ1/{os.path.splitext(os.path.basename(eval_datafile))[0]}.log"
)
logger.set_log_file(log_file)


def eval_accuracy(data):
    """Evaluate the data based on accuracy."""
    logger.info(f"{'=' * 10}[Accuracy]{'=' * 10}")
    accus = []
    for item in data:
        if item["prediction"] == item["reference"]:
            accus.append(1)
            logger.info(f"{item['id']}: Accurately correct")
        else:
            accus.append(0)

    accus = np.array(accus)
    logger.info(f"Accuracy: {accus.sum()} / {len(data)} = {accus.sum()/len(data)}")
    logger.info(f"{'=' * 10}[Accuracy]{'=' * 10}")
    return accus


def eval_codebleu(data):
    """Evaluate the data based on CodeBLEU."""
    logger.info(f"{'=' * 10}[CodeBLEU]{'=' * 10}")
    # results = []
    all_codebleu = []
    for item in data:
        prediction = filter_code(item["prediction"])
        reference = filter_code(item["reference"])
        result = calc_codebleu(
            [prediction],
            [reference],
            lang="java",
            weights=(0.25, 0.25, 0.25, 0.25),
            tokenizer=None,
        )
        # results.append({"id": item["id"], "codebleu": result["codebleu"]})
        logger.info(f"{item['id']}: {result['codebleu']:.2f}")
        all_codebleu.append(result["codebleu"])

    all_codebleu = np.array(all_codebleu)
    # logger.info(f"Highest codebleu: {max([r['codebleu'] for r in results])}")
    # logger.info(f"Lowest codebleu: {min([r['codebleu'] for r in results])}")
    codebleu_average = all_codebleu.sum() / len(data)
    logger.info(f"Average codebleu: {codebleu_average}")
    logger.info(f"{'=' * 10}[CodeBLEU]{'=' * 10}")
    return all_codebleu


def retain_new(pred, ref):
    pred_clean = get_code_without_comments(pred)
    ref_clean = get_code_without_comments(ref)
    pred_fmt = formatted_java_code(pred_clean)
    ref_fmt = formatted_java_code(ref_clean)

    format_prefix = "@@\n\n"
    if pred_fmt and ref_fmt:
        diff_str = get_diff(pred_fmt, ref_fmt)
    else:
        diff_str = get_diff(pred, ref)
    # extract code content
    start = diff_str.find(format_prefix)
    unified_diff = diff_str[start + len(format_prefix) :]

    diff_list = unified_diff.splitlines()

    stmts_add = ""

    # collect add texts
    for line in diff_list:
        if line.startswith("+"):
            stmts_add += line.lstrip("+").strip() + " "
    return stmts_add


def tokenizer(s):
    return s.split()


def eval_diffbleu(data):
    logger.info(f"{'=' * 10}[DiffBLEU]{'=' * 10}")
    diffbleu_all = []
    for item in data:
        pred_add = retain_new(item["original"], item["prediction"])
        ref_add = retain_new(item["original"], item["reference"])
        diffbleu = sentence_bleu([tokenizer(ref_add)], tokenizer(pred_add))
        diffbleu_all.append(diffbleu)

        logger.info(f"{item['id']}: DiffBLEU: {diffbleu:.2f}.")

    diffbleu_all = np.array(diffbleu_all)
    diffbleu_average = diffbleu_all.mean()

    logger.info(f"Average DiffBLEU: {diffbleu_average}")

    logger.info(f"{'=' * 10}[DiffBLEU]{'=' * 10}")
    return diffbleu_all


def eval_syntaxpass(data):
    """Check the syntax of the code."""
    logger.info(f"{'=' * 10}[Syntax Pass]{'=' * 10}")
    syntax_pass = []
    for item in data:
        code = item["prediction"]
        if has_parse_error(code):
            syntax_pass.append(0)
            logger.info(f"Syntax error: {item['id']}")
        else:
            syntax_pass.append(1)

    syntax_pass = np.array(syntax_pass)
    pass_rate = syntax_pass.mean()
    logger.info(
        f"Average Pass Rate of Syntax: {syntax_pass.sum()} / {len(data)} = {pass_rate}"
    )
    logger.info(f"{'=' * 10}[Syntax Pass]{'=' * 10}")
    return syntax_pass


def read_data(filename):
    with open(filename) as f:
        data: list = json.load(f)
    return data


if __name__ == "__main__":
    logger.info(f"#########{type_info}#########")

    if do_pass:
        k = 3
        accus_full = np.array([])
        codebleu_full = np.array([])
        diffbleu_full = np.array([])
        syntax_pass_full = np.array([])

        for i in range(k):
            logger.info(f"\n{'***' * 4}[Pass-{i+1}]{'***' * 4}\n")
            datafile = f"{os.path.splitext(eval_datafile)[0]}_n{i+1}.json"
            data = read_data(datafile)
            accus_full = np.append(accus_full, eval_accuracy(data))
            codebleu_full = np.append(codebleu_full, eval_codebleu(data))
            diffbleu_full = np.append(diffbleu_full, eval_diffbleu(data))
            syntax_pass_full = np.append(syntax_pass_full, eval_syntaxpass(data))

        accus_agg = np.max(accus_full.reshape((3, -1)), axis=0)
        codebleu_agg = np.max(codebleu_full.reshape((3, -1)), axis=0)
        diffbleu_agg = np.max(diffbleu_full.reshape((3, -1)), axis=0)
        syntax_pass_agg = np.max(syntax_pass_full.reshape((3, -1)), axis=0)

    else:
        with open(eval_datafile) as f:
            data: list = json.load(f)
        logger.info(f"Start evaluating {len(data)} items in {eval_datafile}")
        accus_agg = eval_accuracy(data)
        codebleu_agg = eval_codebleu(data)
        diffbleu_agg = eval_diffbleu(data)
        syntax_pass_agg = eval_syntaxpass(data)

    res = {
        "Approach": f"{type_info}({eval_datafile})",
        "Accuracy": accus_agg.mean(),
        "Codebleu": codebleu_agg.mean(),
        "DiffBLEU": diffbleu_agg.mean(),
        "syntax_pass": syntax_pass_agg.mean(),
    }
    with open(eval_resfile, "a") as fo:
        json.dump(res, fo, indent=4)
        fo.write("\n")

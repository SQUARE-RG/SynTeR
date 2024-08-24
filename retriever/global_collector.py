"""
    Given a focal_src and focal_tgt, locate the new parameter class types and find their definitions in the global context.
"""

import utils.multilspy.multilspy_types as multilspy_types
from utils.multilspy import SyncLanguageServer
from utils.multilspy.multilspy_exceptions import MultilspyException
from utils.multilspy.multilspy_utils import TextUtils
from utils.types import ClassCtx, UpdateInfo
from utils.gitter import UpdateRepo
from utils.helper import get_diff_texts
from utils.parser import (
    split_class_from_file,
    filter_file_code,
    divide_texts_by_type,
    find_parent_classes,
    get_unique_text,
    get_methodname_with_pos,
)
from utils.logger import logger


def collect_usages_diffctx(
    lsp: SyncLanguageServer,
    repo: UpdateRepo,
    update_info: UpdateInfo,
    clean_tests: bool = False,
) -> set[str]:
    if not lsp.language_server.server_started:
        logger.Error("collect_uages_diffctx called before Language Server started")
        raise MultilspyException("Language Server not started")

    focal_tgt = update_info.focal_tgt
    focal_relpath = update_info.focal_relpath
    test_tgt = update_info.test_tgt
    test_relpath = update_info.test_relpath
    syn_diff = update_info.syn_diff

    # get the file, repo:'\r\n'; lsp:'\n'
    focal_file = repo.get_file_tgt(update_info.focal_relpath)
    method_start = focal_file.find(focal_tgt)
    # should be the position of name
    name, name_pos = get_methodname_with_pos(focal_tgt)
    name_idx = TextUtils.get_index_from_line_col(
        focal_tgt, name_pos["line"], name_pos["character"]
    )
    ln, cn = TextUtils.get_line_col_from_index(focal_file, method_start + name_idx)
    ref_locs = lsp.request_references(focal_relpath, ln, cn)
    logger.info(f"+ Found {len(ref_locs)} usages for focal_tgt: {name}")
    # locs should exclude the test tgt itself
    test_file = repo.get_file_tgt(test_relpath)
    test_start = test_file.find(test_tgt)
    assert test_start != -1, "Test tgt not found in test file"
    test_end = test_start + len(test_tgt) - 1
    start_ln = TextUtils.get_line_col_from_index(test_file, test_start)[0]
    end_ln = TextUtils.get_line_col_from_index(test_file, test_end)[0]

    all_texts = set()
    # setup for contexts type (collect_before or collect_after)
    collect_before, collect_after = False, False
    if syn_diff["param_types"]:
        collect_before = True
    if syn_diff["type"]:
        collect_after = True

    # get diff texts from references loc
    for loc in ref_locs:
        if loc["uri"].startswith("file:"):
            rel_path = loc["relativePath"]
            ln = loc["range"]["start"]["line"]
            # clean tests if need
            if clean_tests and "test" in rel_path.lower():
                continue
            # exclude the test tgt itself
            if rel_path == test_relpath and ln >= start_ln and ln <= end_ln:
                continue
            # get the diff context for ln
            usage_diff = repo.get_diff_from_pos(
                rel_path, loc["range"]["start"], collect_before, collect_after
            )
            if usage_diff:
                all_texts.add(usage_diff)
    return all_texts


def recurse_class_texts(
    lsp: SyncLanguageServer,
    file_str: str,
    class_type: str,
    loc: multilspy_types.Location,
    texts: list[str],
    visited: set[str] = set(),
    init_flag=True,
):
    """
    Given a class type and its definition, recurse over all the texts from the parent classes.
    """
    if init_flag:
        for text in texts:
            visited.add(get_unique_text(text))
    else:
        add_texts = split_class_from_file(file_str, loc["range"]["start"])
        logger.info(f"# Found {len(add_texts)} texts in class {class_type}")
        for text in add_texts:
            unique_text = get_unique_text(text)
            if unique_text not in visited:
                texts.append(text)
                visited.add(unique_text)
    classes_pos_list = find_parent_classes(file_str, loc["range"]["start"])
    rel_path = loc["relativePath"]
    for class_pos in classes_pos_list:
        ln, cn = class_pos["line"], class_pos["character"]
        locs = lsp.request_definition(rel_path, ln, cn)
        if locs:
            loc = locs[0]
            if loc["uri"].startswith("file:"):
                rel_path = loc["relativePath"]
                with lsp.open_file(rel_path):
                    file_str = lsp.get_open_file_text(rel_path)
                    class_type = lsp.get_text_between_positions(
                        rel_path, loc["range"]["start"], loc["range"]["end"]
                    )
                recurse_class_texts(
                    lsp, file_str, class_type, loc, texts, visited, False
                )


def param_clsctx_from_loc(
    lsp: SyncLanguageServer,
    loc: multilspy_types.Location,
) -> ClassCtx:
    """
    With lsp server being started:
    Given a definition(location) of class type, load, split and collect all the related texts.
    For parameters, default texts should be constructors.
    """
    rel_path = loc["relativePath"]
    with lsp.open_file(rel_path):
        file_str = lsp.get_open_file_text(rel_path)
        class_type = lsp.get_text_between_positions(
            rel_path, loc["range"]["start"], loc["range"]["end"]
        )
    logger.info(f'# Collecting global context for class "{class_type}"')
    # collect class context for class type itself
    texts = split_class_from_file(file_str, loc["range"]["start"])
    constructors, texts = divide_texts_by_type(texts, class_type)
    logger.info(
        f"# Found {len(texts)} texts and {len(constructors)} constructors for class {class_type}"
    )
    # collect class context for superclass and interfaces
    recurse_class_texts(lsp, file_str, class_type, loc, texts)
    logger.info(
        f"# Collected {len(texts)} and {len(constructors)} constructors texts in total for class {class_type}"
    )
    return {
        "class_type": class_type,
        "rel_path": rel_path,
        "splitted_texts": texts,
        "default_texts": constructors,
    }


def collect_clsctx_for_params(
    lsp: SyncLanguageServer,
    file_rel_path: str,
    pidr_pos_list: list[multilspy_types.Position],
) -> list[ClassCtx]:
    """
    collect global context for given parameter types(in_repo class types) in a method.
    """
    if not lsp.language_server.server_started:
        logger.Error("collect_clsctx_for_params called before Language Server started")
        raise MultilspyException("Language Server not started")
    all_clsctx = []
    for pidr_pos in pidr_pos_list:
        # check whether the class is defined in Java standard Library
        ln, cn = pidr_pos["line"], pidr_pos["character"]
        locs = lsp.request_definition(file_rel_path, ln, cn)
        # collect the global context for every in_repo class type
        if locs:
            loc = locs[0]
            if loc["uri"].startswith("file:"):
                all_clsctx.append(param_clsctx_from_loc(lsp, loc))
    return all_clsctx


def return_clsctx_from_loc(
    lsp: SyncLanguageServer,
    loc: multilspy_types.Location,
) -> ClassCtx:
    """
    With lsp server being started:
    Given a definition(location) of class type, load, split and collect all the related texts.
    For return type, default texts should be transform methods or fields.
    """
    rel_path = loc["relativePath"]
    with lsp.open_file(rel_path):
        file_str = lsp.get_open_file_text(rel_path)
        class_type = lsp.get_text_between_positions(
            rel_path, loc["range"]["start"], loc["range"]["end"]
        )
    logger.info(f'# Collecting global context for class "{class_type}"')
    # collect class context for class type itself
    texts = split_class_from_file(file_str, loc["range"]["start"])
    logger.info(f"# Found {len(texts)} texts for class {class_type}")
    # collect class context for superclass and interfaces
    recurse_class_texts(lsp, file_str, class_type, loc, texts)
    logger.info(f"# Collected {len(texts)} texts in total for class {class_type}")
    return {
        "class_type": class_type,
        "rel_path": rel_path,
        "splitted_texts": texts,
        "default_texts": [],
    }


def collect_clsctx_for_return(
    lsp: SyncLanguageServer,
    focal_relpath: str,
    ridr_pos_list: list[multilspy_types.Position],
) -> list[ClassCtx]:
    """
    collect global context for given return type (in_repo class types) in a method.
    """
    if not lsp.language_server.server_started:
        logger.Error("collect_clsctx_for_return called before Language Server started")
        raise MultilspyException("Language Server not started")
    all_clsctx = []
    for ridr_pos in ridr_pos_list:
        # check whether the class is defined in Java standard Library
        ln, cn = ridr_pos["line"], ridr_pos["character"]
        locs = lsp.request_definition(focal_relpath, ln, cn)
        # collect the global context for every in_repo class type
        if locs:
            loc = locs[0]
            if loc["uri"].startswith("file:"):
                all_clsctx.append(return_clsctx_from_loc(lsp, loc))
    return all_clsctx


def recurse_diff_texts(
    lsp: SyncLanguageServer,
    repo: UpdateRepo,
    rel_path: str,
    class_pos: multilspy_types.Position,
    texts: set[str],
    init_flag=True,
):
    """
    Given a class type and its definition, recurse over all the texts from the parent classes.
    """
    if init_flag:
        file_tgt = repo.get_file_tgt(rel_path)
    else:
        # generate diff context
        file_src = repo.get_file_src(rel_path)
        file_tgt = repo.get_file_tgt(rel_path)
        file_src_clean = filter_file_code(file_src, clean_tests=False)
        file_tgt_clean = filter_file_code(file_tgt, clean_tests=False)
        add_texts = get_diff_texts(
            file_src_clean, file_tgt_clean, line_limit=10, add_must=True
        )
        logger.info(f"$ Found {len(add_texts)} diff texts in {rel_path}")
        texts.update(add_texts)

    parent_clspos_list = find_parent_classes(file_tgt, class_pos)
    for parent_clspos in parent_clspos_list:
        ln, cn = parent_clspos["line"], parent_clspos["character"]
        locs = lsp.request_definition(rel_path, ln, cn)
        if locs:
            loc = locs[0]
            if loc["uri"].startswith("file:"):
                rel_path = loc["relativePath"]
                class_pos = loc["range"]["start"]
                recurse_diff_texts(lsp, repo, rel_path, class_pos, texts, False)


def collect_method_diffctx(
    lsp: SyncLanguageServer,
    repo: UpdateRepo,
    rel_path: str,
    method_src: str,
    method_tgt: str,
    type: str,
    clean_tests: bool = False,
) -> set[str]:
    """
    Enrich context by collecting diff context for a method in a given file and its parent files.
    type: "focal" or "test"
    """
    if not lsp.language_server.server_started:
        logger.Error("collect_method_diffctx called before Language Server started")
        raise MultilspyException("Language Server not started")
    # clear the methods in the top file
    file_src = repo.get_file_src(rel_path)
    file_tgt = repo.get_file_tgt(rel_path)

    file_src = file_src.replace(method_src, "")
    method_start = file_tgt.find(method_tgt)
    file_tgt = file_tgt[:method_start] + file_tgt[method_start + len(method_tgt) :]
    file_src_clean = filter_file_code(file_src, clean_tests)
    file_tgt_clean = filter_file_code(file_tgt, clean_tests)

    texts = get_diff_texts(file_src_clean, file_tgt_clean, line_limit=10, add_must=True)
    logger.info(f"$ Found {len(texts)} {type} diff texts in {rel_path}")
    ln, cn = TextUtils.get_line_col_from_index(file_tgt, method_start)
    class_pos = {"line": ln, "character": cn}

    recurse_diff_texts(lsp, repo, rel_path, class_pos, texts)

    return texts


if __name__ == "__main__":
    logger.info("This module is used in main_retriever")
    pass

import re, json, difflib
from .multilspy.multilspy_types import Position
from .multilspy.multilspy_utils import TextUtils
from .types import Example


def extract_code(input_str: str):
    """
    Parses the input string and extracts code blocks in Java, which is surrounded by ```java and ``` or ``` and ```.
    """
    code_blocks = re.findall(
        r"```java\n(.*?)\n```|```\n(.*?)\n```", input_str, re.DOTALL
    )
    if len(code_blocks) == 0:
        return ""
    else:
        return code_blocks[0][0] if code_blocks[0][0] != "" else code_blocks[0][1]


def read_examples(filepath: str) -> list[Example]:
    """
    Read examples from a data file built in run_prepdata.py.

    Args:
        datafile (str): The path to the data file (in dataset/synPTCEvo4j).

    Returns:
        list: A list of Example objects.

    """
    with open(filepath, "r") as f:
        item_list = json.load(f)
    examples = []
    for item in item_list:
        repo_name = item["repo_name"]
        commit_id = item["commit_id"]
        focal_db = item["focal_db"]
        test_db = item["test_db"]
        syn_diff = item["syn_diff"]
        examples.append(Example(repo_name, commit_id, focal_db, test_db, syn_diff))
    return examples


def get_diff(src_code: str, tgt_code: str, n: int = -1) -> str:
    """
    Get the unified diff between two code snippets.

    Args:
        src_code (str): The source code snippet.
        tgt_code (str): The target code snippet.
        n (int): The numbers of context lines. (-1: means no limit)

    Returns:
        str: The unified diff between the source and target code snippets (with prefix line: @@).
    """
    src_lines = src_code.splitlines()
    tgt_lines = tgt_code.splitlines()
    if n == -1:
        n = max(len(src_lines), len(tgt_lines))
    # generate unified_diff
    diff = difflib.unified_diff(
        src_lines, tgt_lines, n=n, fromfile="Previous", tofile="Current"
    )
    diff = list(diff)[2:]
    diff_str = "\n".join(diff)
    return diff_str


def get_diff_texts(
    src_code: str, tgt_code: str, line_limit: int = -1, add_must: bool = False
) -> set[str]:
    """
    Get the list of differences between two code snippets.

    Args:
        src_code (str): The source code snippet.
        tgt_code (str): The target code snippet.
        line_limit (int): The max number of lines in a diff_item(-1 not set).
        add_must(bool): diff item must contain additions if True.

    Returns:
        set[str]: A sets of diff texts between the two code snippets.
    """
    all_diff = set()
    src_lines = src_code.splitlines()
    tgt_lines = tgt_code.splitlines()
    # generate unified_diff
    diff = difflib.unified_diff(
        src_lines, tgt_lines, n=0, fromfile="Previous", tofile="Current"
    )
    diff_item = ""
    item_lines = 0
    # if add_must=False, add_flag will always be True
    add_flag = not add_must
    for line in list(diff)[2:]:
        if line.startswith("@@") or item_lines == line_limit:
            if diff_item:
                if add_flag:
                    all_diff.add(diff_item[:-1])
                    add_flag = not add_must
                diff_item = ""
                item_lines = 0
        else:
            if line.startswith("+ "):
                add_flag = True
            diff_item += line + "\n"
            item_lines += 1
    if diff_item and add_flag:
        all_diff.add(diff_item[:-1])
    return all_diff


def line_range_from_diff(diff_list: list[str], line_idx: int) -> tuple[int, int]:
    """
    Given the target line idx, find the line range of target diff item in the diff_list.
    Return the start_line, end_line of the target diff item.
    """
    # find the first line for former "-"
    cur = line_idx
    skip_add = True
    start_idx = 0
    while cur >= 0:
        line = diff_list[cur]
        if line[0] == "+":
            if skip_add:
                cur -= 1
            else:
                start_idx = cur + 1
                break
        else:
            skip_add = False
            cur -= 1
    # find the last line for latter "+"
    cur = line_idx
    end_idx = len(diff_list) - 1
    while cur < len(diff_list):
        line = diff_list[cur]
        if line[0] == "+":
            end_idx = cur
            cur += 1
        else:
            break
    return start_idx, end_idx


def expand_pos_fmtf(method_str: str, file_str: str, pos: Position) -> Position:
    """
    Given a method_str and file_str, locate the new parameter class types and find their definitions in the global context.
    """
    method_idx = file_str.find(method_str)
    method_idx += TextUtils.get_index_from_line_col(
        method_str, pos["line"], pos["character"]
    )
    ml, mc = TextUtils.get_line_col_from_index(file_str, method_idx)
    return {
        "line": ml,
        "character": mc,
    }


def expand_pos_list_fmtf(
    method_str: str, file_str: str, pos_list: list[Position]
) -> Position:
    """
    expand a list of positions from method to file.
    """
    res_list = []
    method_idx = file_str.find(method_str)
    assert method_idx != -1, "Method not found in file_str"

    for pos in pos_list:
        idx_ori = TextUtils.get_index_from_line_col(
            method_str, pos["line"], pos["character"]
        )
        ml, mc = TextUtils.get_line_col_from_index(file_str, method_idx + idx_ori)
        res_list.append(
            {
                "line": ml,
                "character": mc,
            }
        )

    return res_list

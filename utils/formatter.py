import subprocess, json
from .multilspy.multilspy_types import Position
from .multilspy.multilspy_utils import TextUtils


def formatted_java_code(code_str: str, column_limit=9999, cursor=-1) -> str:
    """
    Formats the given Java code string using the clang-format. Default setting will keep stmt in one line(no column limit).

    Args:
        code_str (str): The Java code string to be formatted.
        column_limit(int): 0 means no limit, based on the seperators in the code.

    Returns:
        str: The formatted Java code or "" (format error).
    """
    try:
        config = {
            "Language": "Java",
            "SortIncludes": "Never",
            "ColumnLimit": column_limit,
            "MaxEmptyLinesToKeep": 0,
            "AllowShortBlocksOnASingleLine": "Empty",
            "AllowShortFunctionsOnASingleLine": "Empty",
            "AllowShortLambdasOnASingleLine": "Empty",
        }
        cmd = [
            "clang-format",
            "--assume-filename=.java",
            f"-style={str(config)}",
        ]
        if cursor != -1:
            cmd.append(f"-cursor={cursor}")
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate(code_str.encode())
        if process.returncode != 0:
            raise Exception(stderr.decode())
        return stdout.decode()
    except Exception as e:
        print(f"--> Clang-format Error: {e}")
        return ""


def formatted_java_code_with_pos(
    code_str: str,
    cursor_pos: Position,
    column_limit=9999,
) -> tuple[str, Position]:
    """
    Formats the given Java code string with cursor position using the clang-format.

    Args:
        code_str (str): The Java code string to be formatted.
        pos (Position): The position of the cursor.
        column_limit(int): 0 means no limit, based on the seperators in the code.

    Returns:
        str: The formatted Java code or "" (format error).
        pos: The position of the cursor after formatting.
    """
    cursor = TextUtils.get_index_from_line_col(
        code_str, cursor_pos["line"], cursor_pos["character"]
    )

    res = formatted_java_code(code_str, column_limit, cursor)
    if res == "":
        return code_str, None
    else:
        cursor_res = res[: res.find("\n")]
        code_fmt = res[res.find("\n") + 1 :]
        cursor_new = json.loads(cursor_res)["Cursor"]
        ln_new, cn_new = TextUtils.get_line_col_from_index(code_fmt, cursor_new)
        cursor_new = {"line": ln_new, "character": cn_new}
        return code_fmt, cursor_new

import re, warnings
from typing import Optional
from tree_sitter import Language, Parser
import tree_sitter_java as tsjava
from .types import MethodMD, SynDiff
from .multilspy.multilspy_types import Position
from .formatter import formatted_java_code
from .logger import logger

warnings.filterwarnings("ignore")
# JAVA_LANGUAGE = Language(
#     TREESITTER_LANG_SO,
#     "java",
# )
JAVA_LANGUAGE = Language(tsjava.language())
parser = Parser()
parser.set_language(JAVA_LANGUAGE)


def has_parse_error(code_str: str) -> bool:
    """check whether the code has parse error"""
    tree = parser.parse(bytes(code_str, "utf8"))
    return tree.root_node.has_error


# public  static -> public static
def get_text(node):
    if node is None:
        return ""
    text = node.text.decode().strip()
    return re.sub(r"\s+", " ", text)


# avoid the impact of the order of the modifiers and type_parameters
def set_string(str_list, join_str=" "):
    lst = sorted(str_list, key=lambda s: s[0])
    res = join_str.join(lst)
    return res


def traverse_tree(tree):
    cursor = tree.walk()
    visited_children = False
    while True:
        if not visited_children:
            yield cursor.node
            if not cursor.goto_first_child():
                visited_children = True
        elif cursor.goto_next_sibling():
            visited_children = False
        elif not cursor.goto_parent():
            break


def traverse_type_identifiers(node, only_top=False):
    """only_top: only consider the top level identifiers. For A<B, C>, only consider A"""
    if node.type == "type_identifier":
        yield node
    if only_top:
        if "scoped" not in node.type and node.type != "type_arguments":
            for child in node.children:
                yield from traverse_type_identifiers(child, only_top)
    else:
        if "scoped" not in node.type:
            for child in node.named_children:
                yield from traverse_type_identifiers(child)


# example：public static synchronized <T extends Comparable<T>, U, V extends List<U>> Map<T, V> processElements(Collection<T> collection, Function<T, V> function) throws IOException, IllegalArgumentException{}
def extract_method_metadata(method_str: str) -> Optional[MethodMD]:
    """
    Extracts metadata from a method code.

    Args:
        method_str (str): The clean version of method code.

    Returns:
        dict: A dictionary containing the extracted metadata. The dictionary has the following keys:
            - "modifiers" (list): The modifiers of the method. (not required)
            - "type_params" (list): The type parameters of the method. (not required)
            - "type" (str): The return type of the method. (required)
            - "name" (str): The name of the method. (required)
            - "param_types" (list): The types of the method parameters. (required)
            - "throw_types" (list): The types of the exceptions thrown by the method. (not required)

            If the method code does not represent a method declaration, an empty dictionary is returned.
    """
    tree = parser.parse(bytes(method_str, "utf8"))
    method_node = None
    for node in tree.root_node.named_children:
        if node.type == "method_declaration" or node.type == "constructor_declaration":
            method_node = node
            break
    if method_node is None:
        logger.warning("The code is not a method declaration.")
        return None
    # print(method_node.sexp())
    # modeifiers(str): "public static synchronized"
    modifiers = []
    throw_types = []
    for node in method_node.named_children:
        if node.type == "modifiers":
            modifiers = get_text(node).split()
        if node.type == "throws":
            for t in node.named_children:
                if t.type == "type_identifier":
                    throw_types.append(get_text(t))

    # type_parameters(set): "T extends Comparable<T>, U, V extends List<U>"
    type_parameters = []
    type_params_node = method_node.child_by_field_name("type_parameters")
    if type_params_node:
        for type_param_node in type_params_node.named_children:
            type_parameters.append(get_text(type_param_node))

    # name(str): "processElements"
    name = get_text(method_node.child_by_field_name("name"))

    # type(str): "Map<T, V>"
    type = get_text(method_node.child_by_field_name("type"))

    # param_types(list): ["List<T>", "int"]
    param_types = []
    param_names = []
    params_node = method_node.child_by_field_name("parameters")
    for param_node in params_node.named_children:
        param_types.append(get_text(param_node.child_by_field_name("type")))
        param_names.append(get_text(param_node.child_by_field_name("name")))
    return {
        "modifiers": modifiers,
        "type_params": type_parameters,
        "type": type,
        "name": name,
        "param_types": param_types,
        "param_names": param_names,
        "throw_types": throw_types,
    }


def get_method_signature(method_str: str) -> str:
    """
    Extracts the signature of a method from its code.

    Args:
        method_str (str): The code of the method -- clean code only contains one line.

    Returns:
        str: The method signature.
    """
    tree = parser.parse(bytes(method_str, "utf8"))
    # check whether the method is cleaned
    if tree.root_node.end_point[0] > 0:
        method_str = filter_code(method_str, clean_comments=True)
        tree = parser.parse(bytes(method_str, "utf8"))
    method_node = None
    for node in tree.root_node.named_children:
        if node.type == "method_declaration" or node.type == "constructor_declaration":
            method_node = node
            break
    if method_node is None:
        logger.warning(f"The code is not a method declaration:\n{method_str}")
        return ""
    body_node = method_node.child_by_field_name("body")
    if body_node:
        sig_end = body_node.start_point[1]
        return method_str[:sig_end].strip() + ";"
    else:
        return method_str.strip()


def all_method_sig_lines(file_str: str) -> set[str]:
    """given a file, find all the lines defining method(without body)"""
    all_lines = set()
    tree = parser.parse(bytes(file_str, "utf8"))
    for node in list(traverse_tree(tree)):
        if node.type in ["method_declaration", "constructor_declaration"]:
            # # only consider public methods
            # if "public" not in get_text(node.child_by_field_name("modifiers")):
            #     continue
            sig_start = node.start_point[0]
            body_node = node.child_by_field_name("body")
            if body_node:
                sig_end = body_node.start_point[0]
            else:
                sig_end = node.end_point[0]
            all_lines.update(range(sig_start, sig_end + 1))
    return all_lines


def get_methodname_with_pos(method_str: str) -> tuple[str, Position]:
    tree = parser.parse(bytes(method_str, "utf8"))
    for node in tree.root_node.named_children:
        if node.type == "method_declaration" or node.type == "constructor_declaration":
            method_node = node
            break
    name_node = method_node.child_by_field_name("name")
    name = get_text(name_node)
    pos = {
        "line": name_node.end_point[0],
        "character": name_node.end_point[1] - 1,
    }
    return name, pos


def compare_list(list1: list, list2: list, order_matters: bool = True) -> bool:
    if len(list1) != len(list2):
        return False
    if order_matters:
        return list1 == list2
    else:
        return set(list1) == set(list2)


def compare_syndiff(method_src: str, method_tgt: str) -> SynDiff:
    """
    Compare the syntactic differences between two methods.

    Args:
        method_src (str): The source method.
        method_tgt (str): The target method.

    Returns:
        dict: A dictionary containing the syntactic differences between the two methods.
              The dictionary has the following keys:
              - "overall": The overall difference score.
              - "modifiers": The difference score for the method modifiers.
              - "type_params": The difference score for the method type parameters.
              - "type": The difference score for the method type.
              - "name": The difference score for the method name.
              - "param_types": The difference score for the method parameter types.
              - "throw_types": The difference score for the method throw types.
        note: param_names will not be compared
    """
    md_src = extract_method_metadata(method_src)
    md_tgt = extract_method_metadata(method_tgt)
    res = dict()
    res["overall"] = 0
    if not md_src or not md_tgt:
        res["overall"] = -1  # method is not valid
        return res
    res["modifiers"] = (
        0 if compare_list(md_src["modifiers"], md_tgt["modifiers"], False) else 1
    )
    res["type_params"] = (
        0 if compare_list(md_src["type_params"], md_tgt["type_params"], False) else 1
    )
    res["type"] = 0 if md_src["type"] == md_tgt["type"] else 1
    res["name"] = 0 if md_src["name"] == md_tgt["name"] else 1
    res["param_types"] = (
        0 if compare_list(md_src["param_types"], md_tgt["param_types"]) else 1
    )
    res["throw_types"] = (
        0 if compare_list(md_src["throw_types"], md_tgt["throw_types"], False) else 1
    )
    res["overall"] = sum(res.values())

    return res


def new_types_poslist(node_src, node_tgt):
    type_poslist = []

    types_src: set[str] = set()
    types_tgt: set[str] = set()
    for id_node in list(traverse_type_identifiers(node_src)):
        types_src.add(get_text(id_node))

    # get the new type identifiers in tgt
    for id_node in list(traverse_type_identifiers(node_tgt)):
        if get_text(id_node) not in types_src and get_text(id_node) not in types_tgt:
            end = {
                "line": id_node.end_point[0],
                "character": id_node.end_point[1] - 1,
            }
            type_poslist.append(end)
        types_tgt.add(get_text(id_node))
    return type_poslist


def get_new_types_poslist(
    method_src: str, method_tgt: str
) -> tuple[list[Position], list[Position]]:
    """
    get the positions of new parameter identifier types in the target method (use the index of last byte).
    """
    tree_src = parser.parse(bytes(method_src, "utf8"))
    method_node_src = tree_src.root_node.named_children[0]
    assert (
        method_node_src.type == "method_declaration"
    ), "src code is not a method declaration."
    tree_tgt = parser.parse(bytes(method_tgt, "utf8"))
    method_node_tgt = tree_tgt.root_node.named_children[0]
    assert (
        method_node_tgt.type == "method_declaration"
    ), "tgt code is not a method declaration."
    params_node_src = method_node_src.child_by_field_name("parameters")
    params_node_tgt = method_node_tgt.child_by_field_name("parameters")
    return_node_src = method_node_src.child_by_field_name("type")
    return_node_tgt = method_node_tgt.child_by_field_name("type")
    # get the pos list for new types
    params_new_poslist = new_types_poslist(params_node_src, params_node_tgt)
    return_new_poslist = new_types_poslist(return_node_src, return_node_tgt)
    return params_new_poslist, return_new_poslist


def get_params_pos_list(method_str: str, params_idx: list[int]) -> list[Position]:
    """
    Retrieves the position of a specific parameter in a method declaration. Every type should only be considered once.

    Args:
        method_str (str): The Java method code as a string.
        param_idx (list[int]): The index list of the parameters to retrieve the range indexed from 0.

    Returns:(many identifiers: Pair<Type1, Type2>)
        A list of position index representing the end position of the identifiers in the target parameter.

    """
    all_pos = []
    types_visited: set[str] = set()
    tree = parser.parse(bytes(method_str, "utf8"))
    method_node = tree.root_node.named_children[0]
    assert (
        method_node.type == "method_declaration"
    ), "The code is not a method declaration."
    params_node = method_node.child_by_field_name("parameters")
    for param_idx in params_idx:
        param_node = params_node.named_child(param_idx)
        type_node = param_node.child_by_field_name("type")
        for id_node in list(traverse_type_identifiers(type_node)):
            identifier_name = get_text(id_node)
            if identifier_name in types_visited:
                continue
            types_visited.add(identifier_name)
            end = {
                "line": id_node.end_point[0],
                "character": id_node.end_point[1] - 1,
            }
            all_pos.append(end)
    return all_pos


def get_return_pos_list(method_str: str) -> list[int]:
    """Retrieves the positions of return types in a method declaration. Single type_node may contains multi class types."""
    all_pos = []
    types_visited: set[str] = set()
    tree = parser.parse(bytes(method_str, "utf8"))
    method_node = tree.root_node.named_children[0]
    assert (
        method_node.type == "method_declaration"
    ), "The code is not a method declaration."
    type_node = method_node.child_by_field_name("type")
    for id_node in list(traverse_type_identifiers(type_node)):
        identifier_name = get_text(id_node)
        if identifier_name in types_visited:
            continue
        types_visited.add(identifier_name)
        end = {
            "line": id_node.end_point[0],
            "character": id_node.end_point[1] - 1,
        }
        all_pos.append(end)
    return all_pos


def get_param_idx_diff(param_types_src: list[str], param_types_tgt: list[int]) -> tuple:
    """
    Get the indices of obsolete and new parameters between two lists of parameter types.

    Args:
        param_types_src (list[str]): The list of parameter types in the source code.
        param_types_tgt (list[int]): The list of parameter types in the target code.

    Returns:
        tuple: A tuple containing two lists:
            - obsolete_param_idx (list[int]): The indices of obsolete parameters in the source code.
            - new_param_idx (list[int]): The indices of new parameters in the target code.
    """
    obsolete_param_idx = []
    new_param_idx = []
    for i, param in enumerate(param_types_src):
        if param not in param_types_tgt:
            obsolete_param_idx.append(i)
    for i, param in enumerate(param_types_tgt):
        if param not in param_types_src:
            new_param_idx.append(i)
    return obsolete_param_idx, new_param_idx


def find_comments(node):
    if "comment" in node.type:
        yield node.start_byte, node.end_byte
    else:
        for child in node.children:
            yield from find_comments(child)


def get_code_without_comments(code_str: str) -> str:
    code_bytes = code_str.encode()
    tree = parser.parse(code_bytes)
    comments = list(find_comments(tree.root_node))
    res_bytes = b""
    start = 0
    for comment in comments:
        res_bytes += code_bytes[start : comment[0]]
        # add 1 to skip the \n
        start = comment[1] + 1
    res_bytes += code_bytes[start:]
    return res_bytes.decode().strip()


def filter_code(code_str: str, clean_comments=False) -> str:
    """
    Filter the given code string by removing comments and cleaning up whitespace.

    Args:
        code_str (str): The code string to filter.
        clean_comments (bool, optional): Whether to remove comments from the code. Defaults to False.

    Returns:
        str: The filtered code string.
    """
    if clean_comments:
        code_str = get_code_without_comments(code_str)
    code_str = code_str.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    code_str = re.sub(" +", " ", code_str)
    return code_str.strip()


def extract_method_from_line(file_str: str, sig_line: int) -> str:
    """
    Extracts the source code of a method from a given file string based on any line number of the method.

    Args:
        file_str (str): The content of the file as a string.
        sig_line (str): Any line number of signature(index from 0).

    Returns:
        str: The source code of the method as a string.

    """
    tree = parser.parse(bytes(file_str, "utf8"))
    method_node = None
    for node in list(traverse_tree(tree)):
        if node.type == "method_declaration" or node.type == "constructor_declaration":
            start_line = node.start_point[0]
            end_line = node.end_point[0]
            if sig_line >= start_line and sig_line <= end_line:
                method_node = node
                return method_node.text.decode()
    logger.warning(f"Method with line number: #{sig_line} not found in file.")
    return ""


def find_parent_classes(file_str: str, class_pos: Position) -> list[Position]:
    """
    get the location of superclass and interfaces of the given class.
    class_pos: any position in the class.
    """
    tree = parser.parse(bytes(file_str, "utf8"))
    class_node = None
    all_pos = []
    for node in list(traverse_tree(tree)):
        if node.type == "class_declaration" or node.type == "interface_declaration":
            class_startln = node.start_point[0]
            class_endln = node.end_point[0]
            if class_startln <= class_pos["line"] and class_endln >= class_pos["line"]:
                class_node = node
        if node.start_point[0] > class_pos["line"]:
            break
    # print(get_text(class_node.child_by_field_name("name")))
    if class_node is None:
        logger.warning(f"No classes at #{class_pos['line']} in the given file.")
        return []
    if class_node.type == "class_declaration":
        superclass = class_node.child_by_field_name("superclass")
        interfaces = class_node.child_by_field_name("interfaces")
        if superclass:
            for idr_node in list(traverse_type_identifiers(superclass, True)):
                pos = {
                    "line": idr_node.end_point[0],
                    "character": idr_node.end_point[1] - 1,
                }
                all_pos.append(pos)
        if interfaces:
            for idr_node in list(traverse_type_identifiers(interfaces, True)):
                pos = {
                    "line": idr_node.end_point[0],
                    "character": idr_node.end_point[1] - 1,
                }
                all_pos.append(pos)
    else:
        for node in class_node.named_children:
            if node.type == "extends_interfaces":
                for idr_node in list(traverse_type_identifiers(node, True)):
                    pos = {
                        "line": idr_node.end_point[0],
                        "character": idr_node.end_point[1] - 1,
                    }
                    all_pos.append(pos)
    return all_pos


def split_class_from_file(
    file_str: str, class_pos: Position, class_prefix=""
) -> list[str]:
    """
    Splits the given class string into text snippets.
    Splitted texts will be cleaned. Texts include methods and fields.
    class_pos: the start position of name node.
    """
    tree = parser.parse(bytes(file_str, "utf8"))
    class_node = None
    res = []
    for node in list(traverse_tree(tree)):
        if node.type == "class_declaration" or node.type == "interface_declaration":
            name_node = node.child_by_field_name("name")
            name_line = name_node.start_point[0]
            if name_line == class_pos["line"]:
                class_node = node
                break
    if class_node:
        # get the lombok annotations for class
        modifiers_cls = []
        for n in class_node.named_children:
            if n.type == "modifiers":
                modifiers_cls = get_text(n).split()
        lombok_annotations = {"@Data", "@Getter", "@Setter"}
        lans_cls = set(modifiers_cls) & lombok_annotations

        body_node = class_node.child_by_field_name("body")
        # print(class_node.sexp())
        for node in body_node.named_children:
            if "declaration" not in node.type:
                continue
            modifiers = []
            for n in node.named_children:
                if n.type == "modifiers":
                    modifiers = get_text(n).split()
            lans_node = (set(modifiers) & lombok_annotations) | lans_cls
            if (
                node.type in ["constructor_declaration", "method_declaration"]
                and "private" not in modifiers
            ):
                clean_text = filter_code(node.text.decode(), clean_comments=True)
                method_sig = get_method_signature(clean_text)
                if method_sig:
                    res.append(method_sig)
                else:
                    clean_text = clean_text[: clean_text.find("{")].strip() + ";"
                    res.append(clean_text)
            elif node.type == "field_declaration":
                if lans_node:
                    clean_text = filter_code(node.text.decode(), clean_comments=True)
                    res.append(f"{' '.join(lans_node)} {clean_text}")
                elif "private" not in modifiers:
                    clean_text = filter_code(node.text.decode(), clean_comments=True)
                    res.append(clean_text)
            elif (
                node.type == "class_declaration"
                or node.type == "interface_declaration"
                and "private" not in modifiers
            ):
                name_node = node.child_by_field_name("name")
                class_prefix = (
                    f"{class_prefix}.{get_text(name_node)}"
                    if class_prefix
                    else get_text(name_node)
                )
                name_point = node.child_by_field_name("name").start_point
                sub_pos = {"line": name_point[0], "character": name_point[1]}
                sub_texts = split_class_from_file(file_str, sub_pos, class_prefix)
                for sub_text in sub_texts:
                    # mark by ##
                    res.append(f"##{class_prefix}\n{sub_text}")
    return res


def find_excludes(node, clean_tests=False):
    if (
        "comment" in node.type
        or node.type == "package_declaration"
        or node.type == "import_declaration"
    ):
        yield node.start_byte, node.end_byte
    elif clean_tests and node.type == "method_declaration":
        modifiers = ""
        for child in node.named_children:
            if child.type == "modifiers":
                modifiers = get_text(child)
        if "@Test" in modifiers:
            yield node.start_byte, node.end_byte
        else:
            for child in node.children:
                yield from find_excludes(child, clean_tests)
    else:
        for child in node.children:
            yield from find_excludes(child, clean_tests)


def filter_file_code(file_str: str, clean_tests=False) -> str:
    """
    filter file code by removing comments and reformat.
    """
    file_bytes = file_str.encode()
    tree = parser.parse(file_bytes)
    excludes = list(find_excludes(tree.root_node, clean_tests))
    res_bytes = b""
    start = 0
    for exclude in excludes:
        res_bytes += file_bytes[start : exclude[0]]
        start = exclude[1] + 1
    res_bytes += file_bytes[start:]
    res_str = res_bytes.decode().strip()
    # format: clean empty lines and format the code
    res_fmt = formatted_java_code(res_str)

    return res_fmt if res_fmt else res_str


def get_unique_text(text_str: str) -> str:
    """
    get the unique string of text
    for method: method_name(arguments types)
    others: name
    """
    tree = parser.parse(bytes(text_str, "utf8"))
    node = tree.root_node.named_children[0]
    if node.type == "method_declaration" or node.type == "constructor_declaration":
        name = get_text(node.child_by_field_name("name"))
        args = node.child_by_field_name("parameters")
        arg_types = []
        for arg in args.named_children:
            arg_types.append(get_text(arg.child_by_field_name("type")))
        return f"{name}({', '.join(arg_types)})"
    # field -> local_variable_declaration
    elif "declaration" in node.type:
        return get_text(
            node.child_by_field_name("declarator").child_by_field_name("name")
        )
    return text_str


def divide_texts_by_type(
    texts: list[str], class_type: str
) -> tuple[list[str], list[str]]:
    """
    divide the texts from a list of splitted texts into two groups according to the types.
    note: constructors: all the methods and fields with type of class_type are considered as constructors.
    """
    targets = []
    others = []
    for text in texts:
        tree = parser.parse(bytes(text, "utf8"))
        node = tree.root_node.children[0]
        type_node = node.child_by_field_name("type")
        if get_text(type_node).split(".")[-1] == class_type.split(".")[-1]:
            targets.append(text)
            continue
        others.append(text)
    return targets, others

"""
Fine-grained extractor for test src method.
This module contains functions that extract information from a single test file in the level of operations.
Target: operations(constructions, member access, intermidiate declarations)
Approach: Tree-sitter Parser
"""

import re
from utils.parser import parser, traverse_tree, get_text


def is_member_access(node):
    """
    check whether the node is a usage of a class instance
    """
    if node == None:
        return False
    return node.type == "method_invocation" or "access" in node.type


def extract_args_operations(
    code_str: str,
    method_name: str,
    param_names: list[str],
    obs_params_idx: list[int],
) -> tuple[set[str], set[str]]:
    """
    given a list of stmts, find the operations on parameters of the emethod. Operations include constructions and member accesses.
    member accesses: method, field, array access and etc.
    """
    if not obs_params_idx:
        return set(), set()
    tree = parser.parse(bytes(code_str, "utf8"))
    avardict: dict[str, int] = dict()  # key: identifier name; value: arg index
    constructions = set()
    accesses = set()
    visited = set()
    literal_str = ""
    # for every obsolete arg, add access
    for i in obs_params_idx:
        accesses.add(f"x.set{param_names[i]}()")
    # find location where the method is invoked
    for node in list(traverse_tree(tree)):
        if node.type == "method_invocation":
            name = get_text(node.child_by_field_name("name"))
            if name == method_name:
                args_node = node.child_by_field_name("arguments")
                if args_node.named_child_count > max(obs_params_idx):
                    for i in obs_params_idx:
                        arg_node = args_node.named_child(i)
                        if "identifier" in arg_node.type:
                            avardict[get_text(arg_node)] = i
                        # length(1) and length(2) are the same
                        elif i not in visited:
                            visited.add(i)
                            if "literal" in arg_node.type:
                                literal_str += (
                                    f"{param_names[i]}={get_text(arg_node)}, "
                                )
                            else:
                                constructions.add(
                                    f"{param_names[i]} = {get_text(arg_node)}"
                                )
    # find more usages
    if avardict:
        for node in list(traverse_tree(tree)):
            if "identifier" in node.type and get_text(node) in avardict:
                arg_idx = avardict[get_text(node)]
                parent_node = node.parent
                if parent_node.type == "variable_declarator":
                    value_node = parent_node.child_by_field_name("value")
                    if "literal" in value_node.type and arg_idx not in visited:
                        visited.add(arg_idx)
                        literal_str += (
                            f"{param_names[arg_idx]}={get_text(value_node)}, "
                        )
                    else:
                        constructions.add(
                            f"{param_names[arg_idx]} = {get_text(value_node)}"
                        )
                elif is_member_access(node.parent):
                    parent_node = node.parent
                    while is_member_access(parent_node.parent):
                        parent_node = parent_node.parent
                    node_str = get_text(node)
                    parent_str = get_text(parent_node)
                    if parent_str not in constructions:

                        start = parent_str.find(node_str) + len(node_str)
                        accesses.add(param_names[arg_idx] + parent_str[start:])
    if literal_str:
        constructions.add(literal_str.rstrip(", "))
    # clean repeat
    return constructions, accesses


def extract_return_operations(
    code_str: str, method_name: str, class_type: str
) -> tuple[set[str], set[str]]:
    """
    given a list of stmts, find the operations on return value of the emethod. Operations include field_access, array_access, method_invocation, etc.
    """
    tree = parser.parse(bytes(code_str, "utf8"))
    # store the variable names of the assigned return value for method
    mvars = set()
    # intermediate results if exists
    intermediates = set()
    accesses = set()
    result_var = re.sub(r"[^a-zA-Z]", "_", class_type).strip("_").lower()
    for node in list(traverse_tree(tree)):
        if node.type == "method_invocation":
            name = get_text(node.child_by_field_name("name"))
            if name == method_name:
                parent_node = node
                while is_member_access(parent_node.parent):
                    parent_node = parent_node.parent
                node_str = get_text(node)
                parent_str = get_text(parent_node)
                if parent_node.parent.type == "variable_declarator":
                    stmt_node = parent_node.parent.parent
                    type_str = ""
                    if stmt_node:
                        type_str = get_text(stmt_node.child_by_field_name("type"))
                    # result name
                    mvars.add(get_text(parent_node.parent.child_by_field_name("name")))
                    if len(node_str) != len(parent_str):
                        start = parent_str.find(node_str) + len(node_str)
                        intermediates.add(
                            f"{type_str}: {result_var}{parent_str[start:]}"
                        )
                        result_var = (
                            re.sub(r"[^a-zA-Z]", "_", type_str).strip("_").lower()
                        )
                    else:
                        intermediates.add(f"{class_type}: {result_var}")
                else:
                    if len(node_str) != len(parent_str):
                        start = parent_str.find(node_str) + len(node_str)
                        accesses.add(result_var + parent_str[start:])
                    else:
                        intermediates.add(f"{class_type}: x")
        elif "identifier" in node.type and get_text(node) in mvars:
            node_str = get_text(node)
            parent_node = node
            while is_member_access(parent_node.parent):
                parent_node = parent_node.parent
            if (
                parent_node.type == "method_invocation"
                and get_text(parent_node.child_by_field_name("name")) == node_str
            ):
                continue
            parent_str = get_text(parent_node)
            # member access exists
            if len(parent_str) != len(node_str):
                start = parent_str.find(node_str) + len(node_str)
                accesses.add(result_var + parent_str[start:])
    return intermediates, accesses


if __name__ == "__main__":
    # Test
    code_str = '@Test\n  public void testGetCustomizations() throws InterruptedException, FileNotFoundException {\n    String customizationsAsString =\n        getStringFromInputStream(new FileInputStream("src/test/resources/speech_to_text/customizations.json"));\n    JsonObject customizations = new JsonParser().parse(customizationsAsString).getAsJsonObject();\n\n    server.enqueue(\n        new MockResponse().addHeader(CONTENT_TYPE, HttpMediaType.APPLICATION_JSON).setBody(customizationsAsString));\n\n    List<Customization> result = service.getCustomizations("en-us").execute();\n    final RecordedRequest request = server.takeRequest();\n\n    assertEquals("GET", request.getMethod());\n    assertEquals(PATH_CUSTOMIZATIONS + "?language=en-us", request.getPath());\n    assertEquals(customizations.get("customizations").getAsJsonArray().size(), result.size());\n    assertEquals(customizations.get("customizations"), GSON.toJsonTree(result));\n  }'
    arg_usages = extract_args_operations(
        code_str, "getCustomizations", ["language"], [0]
    )
    ret_usages = extract_return_operations(
        code_str, "getCustomizations", " ServiceCall<List<Customization>>"
    )

    print(f"Extractred ops for parameter(arg) types: {arg_usages}")
    print(f"Extractred ops for return type: {ret_usages}")

    # code_str = """
    # @Test
    #   public void mount() throws Exception {
    #     AlluxioURI alluxioPath = new AlluxioURI("/t");
    #     AlluxioURI ufsPath = new AlluxioURI("/u");
    #     MountOptions mountOptions = new mountOptions();
    #     MountOptions mountOptions = MountOptions.defaults();
    #     mountOptions.setShared(true);
    #     mountOptions.field;
    #     doNothing().when(mFileSystemMasterClient).mount(alluxioPath, ufsPath, mountOptions);
    #     mFileSystem.mount(alluxioPath, ufsPath, mountOptions);
    #     verify(mFileSystemMasterClient).mount(alluxioPath, ufsPath, mountOptions);

    #     verifyFilesystemContextAcquiredAndReleased();
    #   }
    # """
    # usages = extract_args_operations(
    #     code_str, "mount", ["alluxioPath", "ufsPath", "options"], [2]
    # )
    # print(f"Extractred ops for parameter(arg) types: {usages}")

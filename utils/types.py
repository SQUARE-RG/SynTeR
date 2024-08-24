from typing import TypedDict, Optional, Literal
import os
from .configs import REPO_BASE


# focal_db and test_db
class MethodDB(TypedDict):
    id: str
    rel_path: str
    method_src: str
    method_tgt: str


class SynDiff(TypedDict):
    overall: int
    modifiers: Literal[0, 1]
    type_params: Literal[0, 1]
    type: Literal[0, 1]
    name: Literal[0, 1]
    param_types: Literal[0, 1]
    throw_types: Literal[0, 1]


# store method_metadata for parser module
class MethodMD(TypedDict):
    modifiers: Optional[list[str]]
    type_params: Optional[list[str]]
    type: str
    name: str
    param_types: list[str]
    param_names: list[str]
    throw_types: Optional[list[str]]


# a dict type to store texts splitted into stmts and methods for a class type
class ClassCtx(TypedDict):
    class_type: str
    rel_path: str
    splitted_texts: list[str]
    default_texts: list[str]


# a dict type to store retrieved context(info: class or diff; context: list of texts)
class RetCtx(TypedDict):
    info: str
    contexts: list[str]


# Reading Exmaples from a data file built by run_prepdata.py
class Example(object):
    def __init__(
        self,
        repo_name: str,
        commit_id: str,
        focal_db: MethodDB,
        test_db: MethodDB,
        syn_diff: SynDiff,
    ):
        self.repo_name = repo_name
        self.commit_id = commit_id
        self.commit_url = f"https://github.com/{repo_name}/commit/{commit_id}"
        self.focal_db = focal_db
        self.test_db = test_db
        self.syn_diff = syn_diff

    def to_dict(self):
        return {
            "repo_name": self.repo_name,
            "commit_id": self.commit_id,
            "commit_url": self.commit_url,
            "focal_db": self.focal_db,
            "test_db": self.test_db,
            "syn_diff": self.syn_diff,
        }


# Type def of the focal_info and test_info dict
# note: if the test is not updated, test_tgt = ""
class UpdateInfo(object):
    def __init__(self, exp: Example):
        self.repo_root = os.path.join(REPO_BASE, exp.repo_name)
        self.commit_id = exp.commit_id
        self.focal_src = exp.focal_db["method_src"]
        self.focal_tgt = exp.focal_db["method_tgt"]
        self.focal_relpath = exp.focal_db["rel_path"]
        self.test_src = exp.test_db["method_src"]
        self.test_tgt = exp.test_db["method_tgt"]
        self.test_relpath = exp.test_db["rel_path"]
        self.syn_diff = exp.syn_diff

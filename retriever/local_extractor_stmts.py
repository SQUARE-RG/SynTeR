"""
Coarse-grained extractor for test src method.
This module contains functions that extract information from the single test file. The extracted stmts will construct query for reranker.
Target: extracted stmts and analysis
Approach: LLM + COT Prompting
"""

from langchain_core.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain_core.output_parsers import StrOutputParser
from utils.llm import llm_model as model
from utils.helper import extract_code
from utils.parser import get_code_without_comments
from utils.formatter import formatted_java_code


# prompt setting
# System message
system_prompt = """You are an expert in code-test co-evolution for Java projects. \
Given a test code together with a focal method syntactic diff, \
you need to find obsolete statements that need to be updated in the test code. \
Your response should strictly follow the step of the provided example, which only contains short analysis of focal diff and obsolete statements."""
system_message_prompt = SystemMessagePromptTemplate.from_template(system_prompt)

# human message
cot_prompt = """\
Example:
### Test method to update
```
@Test
   public void mount() throws Exception {{
     AlluxioURI alluxioPath = new AlluxioURI("/t");
     AlluxioURI ufsPath = new AlluxioURI("/u");
     MountOptions mountOptions = MountOptions.default();
     doNothing().when(mFileSystemMasterClient).mount(alluxioPath, ufsPath, mountOptions);
     mFileSystem.mount(alluxioPath, ufsPath, mountOptions);
     verify(mFileSystemMasterClient).mount(alluxioPath, ufsPath, mountOptions);
 
     verifyFilesystemContextAcquiredAndReleased();
   }}
```
### Syntactic diff of focal method 
- void mount(AlluxioURI alluxioPath, AlluxioURI ufsPath, MountOptions options)throws IOException, AlluxioException;
+ void mount(AlluxioURI alluxioPath, AlluxioURI ufsPath, MountPOptions options)throws IOException, AlluxioException;
### Short summary of focal diff
The third parameter "options" of the method "mount" changes from `MountOptions` to `MountPOptions`.
### Obsolete statements
```java
MountOptions mountOptions = MountOptions.default();
mFileSystem.mount(alluxioPath, ufsPath, mountOptions);
```
"""
user_prompt = """\
Follow the above example:
### Test method to update
```
{test_src}
```
### Syntactic diff of focal method
- {focal_src_sig}
+ {focal_tgt_sig}
### Short summary of focal diff
"""
human_prompt = cot_prompt + user_prompt
human_message_template = HumanMessagePromptTemplate.from_template(human_prompt)

# full prompt generation
extract_prompt = ChatPromptTemplate.from_messages(
    [system_message_prompt, human_message_template]
)


def parse_output(s: str) -> tuple[str, str]:
    """
    Construct a list, every item refers to the obsolete statement.
    """
    s = s + "\n"
    split_idx = s.find("### Obsolete statements")
    anal = s[:split_idx].strip()
    stmts = extract_code(s[split_idx:])
    return (anal, stmts)


def extract_stmts_to_update(
    test_src: str, focal_src_sig: str, focal_tgt_sig: str
) -> tuple[str, str]:
    """
    Extracts statements with analysis.
    Returns:
        tuple[str, list[str]]: A tuple containing the analysis texts and a list of extracted statements.
    """
    # try k times
    k = 1
    extract_chain = extract_prompt | model | StrOutputParser() | parse_output
    test_src_clean = get_code_without_comments(test_src)
    test_src_fmt = formatted_java_code(test_src_clean)
    query_batch = [
        {
            "test_src": test_src_fmt,
            "focal_src_sig": focal_src_sig,
            "focal_tgt_sig": focal_tgt_sig,
        }
    ] * k
    res = extract_chain.batch(query_batch)
    # min : more precise
    anal_final = min(res, key=lambda x: len(x[0]))[0]
    stmts_final = min(res, key=lambda x: len(x[1]))[1]
    return anal_final, stmts_final

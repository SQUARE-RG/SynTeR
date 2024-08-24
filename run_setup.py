from utils.gitter import setup_repo

# download the repo for Alluxio/alluxio in the test_part dataset
db = {
    "repo_name": "Alluxio/alluxio",
    "commit_id": "8cc5a292f4c6e38ed0066ce5bd700cc946dc3803",
}
repo = setup_repo(db["repo_name"], db["commit_id"], do_clone=True)

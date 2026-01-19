import os
import shutil
import git
from tempfile import mkdtemp

def clone_repo(url: str, token: str = None) -> str:
    temp_dir = mkdtemp()
    auth_url = url
    if token:
        # naive token insertion, strictly for demo.
        # Production should use git credentials helper or header injection.
        if "https://" in url:
            auth_url = url.replace("https://", f"https://oauth2:{token}@")

    try:
        git.Repo.clone_from(auth_url, temp_dir, depth=1)
        return temp_dir
    except Exception as e:
        shutil.rmtree(temp_dir)
        raise e

def cleanup_dir(path: str):
    shutil.rmtree(path, ignore_errors=True)

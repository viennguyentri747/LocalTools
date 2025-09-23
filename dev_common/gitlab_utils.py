import time
import gitlab
import os
import sys
import re
from pathlib import Path
from urllib.parse import urlparse
import zipfile  # Needed for extracting artifacts
from gitlab.v4.objects import *
from gitlab import *
from typing import Union
from dev_common import *
from dev_common.custom_structures import IesaLocalRepoInfo
# from dev_common.core_utils import LOG, LOG_EXCEPTION, read_value_from_credential_file
# from dev_common.custom_structures import *


def main():
    # --- Configuration ---
    credentials_file = CREDENTIALS_FILE_PATH

    # Logic to read token from file if not in env
    private_token = read_value_from_credential_file(credentials_file, GL_TISDK_TOKEN_KEY_NAME)

    # Details of the target project and job
    target_project_path = f"{INTELLIAN_ADC_GROUP}/{IESA_TISDK_TOOLS_REPO_NAME}"
    target_job_name = "sdk_create_tarball_release"
    target_ref = "manpack_master"

    # Get the target project using the new function
    target_project = get_gl_project(private_token, target_project_path)

    # For robust fetching of branch names, consider get_all=True here too if you're not sure the default is sufficient.
    print(f"Target project: {target_project_path}, instance: {target_project.branches.list(get_all=True)[0].name}")

    pipeline_id = get_latest_successful_pipeline_id(target_project, target_job_name, target_ref)
    if not pipeline_id:
        print(f"No successful pipeline found for job '{target_job_name}' on ref '{target_ref}'.")
        sys.exit(1)

    artifacts_dir = os.path.join(os.path.dirname(__file__), 'artifacts')
    paths: List[str] = download_job_artifacts(target_project, artifacts_dir, pipeline_id, target_job_name)
    if paths:
        print(f"Artifacts extracted to: {artifacts_dir}")


def get_gl_project(gl_private_token: str, project_path: str) -> Project:
    """
    Connects to GitLab API and retrieves the target project.
    """
    gl: Gitlab = gitlab.Gitlab(GL_BASE_URL, private_token=gl_private_token)

    try:
        target_project: Project = gl.projects.get(project_path)
        print(f"Successfully connected to GitLab and retrieved project '{project_path}'.")
        return target_project
    except Exception as e:
        LOG(f"Error connecting to GitLab or retrieving project '{project_path}': {e}")
        LOG_EXCEPTION(e)


@dataclass
class InfoFromMrUrl:
    gl_project_path: str
    mr_iid: str

def get_info_from_mr_url(mr_url: str) -> InfoFromMrUrl | None:
    """
    Extracts the GitLab project path and MR IID from a GitLab MR URL.
    Example URL: https://gitlab.com/intellian_adc/prototyping/insensesdk/-/merge_requests/164
    Returns: InfoFromMrUrl(gl_project_path="intellian_adc/prototyping/insensesdk", mr_iid="164")
    """
    try:
        parsed_url = urlparse(mr_url)
        # Matches paths like /group/subgroup/repo/-/merge_requests/123
        match = re.search(r'/(.*?)/-/merge_requests/(\d+)', parsed_url.path)
        if match:
            gl_project_path = match.group(1)  # Everything before /-/merge_requests/
            mr_iid = match.group(2)           # The merge request ID number
            return InfoFromMrUrl(
                gl_project_path=gl_project_path,
                mr_iid=mr_iid
            )
        else:
            # URL doesn't match expected GitLab MR pattern
            return None
            
    except Exception as e:
        # Handle any parsing errors (invalid URL, etc.)
        return None


def get_mr_diff_from_url(mr_url: str) -> Union[str, None]:
    """
    Retrieves the diff content from a GitLab Merge Request URL. Ex: https://gitlab.com/intellian_adc/prototyping/insensesdk/-/merge_requests/164
    """
    try:
        info: InfoFromMrUrl = get_info_from_mr_url(mr_url)
        gl_project_path = info.gl_project_path
        if not gl_project_path:
            return None

        # Extract MR IID from URL
        mr_iid = info.mr_iid

        repoInfo: IesaLocalRepoInfo = LOCAL_REPO_MAPPING.get_by_gl_project_path(gl_project_path)
        gl_private_token = repoInfo.gl_access_token
        # Get project and MR objects
        project = get_gl_project(gl_private_token, gl_project_path)
        mr: ProjectMergeRequest = project.mergerequests.get(mr_iid)

        # Get the diff - this returns the changes between source and target branches
        diff_content = mr.changes()

        # The changes() method returns a dict with 'changes' key containing the actual diff
        # Structure: {'changes': [{'old_path': 'file1.py', 'new_path': 'file1.py', 'diff': '@@ -1,3 +1,3 @@...'}]}
        if isinstance(diff_content, dict) and 'changes' in diff_content:
            # Format the diff as a readable string
            diff_lines = []
            for change in diff_content['changes']:
                if 'diff' in change:
                    # --- indicates the orig file path (before). Ex: --- packaging/systemd/system/fan_on.sh
                    diff_lines.append(f"--- {change.get('old_path', 'unknown_old_file_path')}")
                    # +++ indicates the modified file path (after). Ex: +++ packaging/systemd/system/fan_on.sh
                    diff_lines.append(f"+++ {change.get('new_path', 'unknown_new_file_path')}")
                    # Add the actual diff content which includes:
                    # - @@ line numbers @@
                    # - lines starting with '-' (removed)
                    # - lines starting with '+' (added)
                    # - lines with no prefix (unchanged context)
                    diff_lines.append(change['diff'])
            return '\n'.join(diff_lines)
        else:
            # If changes() returns the diff directly as a string
            return str(diff_content)

    except Exception as e:
        LOG_EXCEPTION(e)
        return None


def get_latest_successful_pipeline_id(gl_project: Project, job_name: str, git_ref: str):
    """
    Fetches the ID of the latest successful pipeline for a given job and ref.
    """
    # Use get_all=True to ensure all pipelines matching criteria are fetched across all pages
    matched_pipelines = gl_project.pipelines.list(
        ref=git_ref, status='success', order_by='id', sort='desc', get_all=True)

    start_time = time.time()
    for pipeline in matched_pipelines:
        # Use get_all=True to ensure all jobs within this pipeline are fetched across all pages
        # Note: pipelines.list(get_all=True) will fetch a lot of data for large projects.
        # Consider refining this search if performance is an issue for many historical pipelines.
        jobs = pipeline.jobs.list(get_all=True)
        for job in jobs:
            if job.name == job_name and job.status == 'success':
                print(
                    f"Finished searching for latest successful pipeline for job '{job_name}' on ref '{git_ref}' in {time.time() - start_time:.2f} seconds.")
                print(
                    f"Job info: {job.name}, status: {job.status}, pipeline ID: {pipeline.id}, timestamp: {pipeline.created_at}")
                print(f"Found latest successful pipeline: {pipeline.id} for job '{job_name}' on ref '{git_ref}'")
                return pipeline.id
    print(
        f"Error: No successful pipeline found for job '{job_name}' on ref '{git_ref}' in {time.time() - start_time:.2f} seconds.")
    return None


def download_job_artifacts(gl_project: Project, artifacts_dir_path: str, pipeline_id: str, job_name: str) -> List[str]:
    """
    Downloads and extracts artifacts for a specific job in a pipeline into an 'artifacts/' directory.
    Returns a list of downloaded artifact paths.
    """
    os.makedirs(artifacts_dir_path, exist_ok=True)  # Create artifacts directory if it doesn't exist
    print(f"Fetching artifacts archive for job '{job_name}' in pipeline {pipeline_id}...")
    try:
        # Get the job object from the pipeline
        pipeline_object_jobs = gl_project.pipelines.get(pipeline_id).jobs.list(get_all=True)
        pipeline_obj_job = next((j for j in pipeline_object_jobs if j.name == job_name), None)

        if not pipeline_obj_job:
            print(f"Error: Job '{job_name}' not found in pipeline {pipeline_id}.")
            sys.exit(1)

        print(f"Found job '{pipeline_obj_job.get_id()}' in pipeline {pipeline_id}.")
        start_time = time.time()
        print(f"Downloading artifacts for job '{job_name}' in pipeline {pipeline_id}...")
        # Get the job object from the job ID using the project object
        gl_target_job = gl_project.jobs.get(pipeline_obj_job.get_id())
        zipfn = os.path.join(artifacts_dir_path, "___artifacts.zip")  # Temporary file name inside artifacts dir
        with open(zipfn, "wb") as f:
            gl_target_job.artifacts(streamed=True, action=f.write)

        print(
            f"Finished downloading artifacts archive to temporary file {zipfn} in {time.time() - start_time:.2f} seconds.")

        # --- ARTIFACT EXTRACTION AND LISTING ---
        print(f"Attempting to extract specific artifact from {zipfn}...")

        # Check if the downloaded file is a valid zip before attempting to list/extract
        if not zipfile.is_zipfile(zipfn):
            print(f"Error: Downloaded file '{zipfn}' is not a valid zip archive. Cannot extract.")
            os.unlink(zipfn)  # Clean up invalid file
            sys.exit(1)

        # Print contents before extraction
        extracted_file_names = []
        with zipfile.ZipFile(zipfn, 'r') as zip_ref:
            # Get list of files that *will be* extracted
            extracted_file_names = zip_ref.namelist()
            # Now, extract the contents using Python's zipfile module directly
            # This avoids reliance on external 'unzip' command and is often more robust
            print(f"Extracting contents from '{zipfn}' into '{artifacts_dir_path}'...")
            zip_ref.extractall(path=artifacts_dir_path)  # Extract to artifacts dir
            print("Extraction complete using Python's zipfile module.")

        extracted_file_full_paths = [os.path.join(artifacts_dir_path, name) for name in extracted_file_names]
        # Now, print what was actually extracted (or what should have been)
        if extracted_file_full_paths:
            print("\nSuccessfully extracted the following files/directories:")
            for inex, item in enumerate(extracted_file_full_paths, 1):
                print(f"    {inex}. {item}")
            print("\n")
        else:
            print("No files found or extracted from the archive.")

        # Delete the temporary zip file
        os.unlink(zipfn)
        print(f"Deleted temporary archive '{zipfn}'.")
        return extracted_file_full_paths
    except Exception as e:
        print(f"An unexpected error occurred during artifact download or extraction: {e}")
        sys.exit(1)
        return False  # Added return False for error case


if __name__ == "__main__":
    main()

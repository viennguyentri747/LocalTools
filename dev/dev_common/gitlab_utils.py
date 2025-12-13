import time
import gitlab
import os
import base64
import sys
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
import zipfile  # Needed for extracting artifacts
from gitlab.v4.objects import *
from gitlab import *
from typing import Optional, Union, List
from dev.dev_common import *
from gitlab.exceptions import GitlabError


class MrFileChange:
    """
    Represents a single file change within a GitLab Merge Request.
    """

    def __init__(self, change_data: dict, project: Project, mr: ProjectMergeRequest):
        self._change_data = change_data
        self._project = project
        self._mr = mr

    @property
    def old_file_path_before_change(self) -> str:
        return self._change_data.get('old_path')

    @property
    def new_file_path_after_change(self) -> str:
        return self._change_data.get('new_path')

    @property
    def filePath(self) -> str:
        """A convenience property to get the most relevant file path."""
        return self.new_file_path_after_change or self.old_file_path_before_change

    def GetDiff(self) -> str:
        """Returns the diff string for this specific file."""
        return self._change_data.get('diff', '')

    def GetFileContent(self) -> Union[str, None]:
        """
        Retrieves the full content of the file from the MR.

        This version is more robust and works even if the source branch has been
        deleted by fetching content from a specific commit SHA instead of the
        branch name.
        """
        # If the file was deleted in the MR, it has no "new" content.
        if self._change_data.get('deleted_file', False):
            return None

        # --- 1. Primary Method: Use the MR's head commit SHA ---
        # This is the most accurate ref for the file's state within the MR itself.
        # It's found in the 'diff_refs' dictionary.
        ref_to_try = self._mr.diff_refs.get('head_sha')

        if ref_to_try:
            try:
                # Fetch the file using the specific commit SHA
                file_obj = self._project.files.get(file_path=self.filePath, ref=ref_to_try)
                return file_obj.decode().decode('utf-8')
            except GitlabError as e:
                LOG(f"Could not retrieve '{self.filePath}' using head_sha '{ref_to_try}'. Error: {e}")

        LOG(f"All attempts to retrieve file content for '{self.filePath}' have failed.")
        return None


def get_repo_info_by_name(repo_name: str) -> Optional[IesaLocalRepoInfo]:
    """Retrieve repository information by its name."""
    repo_info = LOCAL_REPO_MAPPING.get_by_name(repo_name)
    if not repo_info:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Unknown repository '{repo_name}'.")
        return None
    return repo_info

def get_repo_info_by_project_path(gl_project_path: str) -> Optional[IesaLocalRepoInfo]:
    """Retrieve repository information by its GitLab project path."""
    repo_info = LOCAL_REPO_MAPPING.get_by_gl_project_path(gl_project_path)
    if not repo_info:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Unknown repository for project path '{gl_project_path}'.")
        return None
    return repo_info

def get_gl_project(repo_info: IesaLocalRepoInfo) -> Project:
    """
    Connects to GitLab API and retrieves the target project.
    """
    gl_private_token = repo_info.gl_access_token
    gl_project_path = repo_info.gl_project_path
    gl: Gitlab = gitlab.Gitlab(GL_BASE_URL, private_token=gl_private_token)

    try:
        target_project: Project = gl.projects.get(gl_project_path)
        print(f"Successfully connected to GitLab and retrieved project '{gl_project_path}'.")
        return target_project
    except Exception as e:
        LOG(f"Error connecting to GitLab or retrieving project '{gl_project_path}': {e}")
        LOG_EXCEPTION(e)


def is_gl_ref_exists(gl_project: Project, ref: str) -> bool:
    """
    Return True when the ref exists in the project.
    Checks in order: branch, tag, commit SHA.
    """
    if not ref:
        return False
    
    try:
        # Check if it's a branch
        gl_project.branches.get(ref)
        return True
    except Exception:
        pass
    
    try:
        # Check if it's a tag
        gl_project.tags.get(ref)
        return True
    except Exception:
        pass
    
    try:
        # Check if it's a commit SHA (full or short)
        gl_project.commits.get(ref)
        return True
    except Exception as exc:
        LOG_EXCEPTION(exception=exc, exit=False)
        return False


@dataclass
class InfoFromMrUrl:
    gl_project_path: str
    mr_iid: str


@dataclass
class GitlabRepoContext:
    """Bundle project metadata commonly reused across GitLab helpers."""

    repo_info: IesaLocalRepoInfo
    project: Project


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


def get_gl_mrs_of_branch(gl_project: Project, source_branch: str, target_branch: Optional[str] = None, include_closed: bool = True, ) -> List[ProjectMergeRequest]:
    """List merge requests matching the provided source/target branch filters."""
    params = {
        'source_branch': source_branch,
        'get_all': True,
    }
    if target_branch:
        params['target_branch'] = target_branch
    if not include_closed:
        params['state'] = 'opened'

    try:
        return gl_project.mergerequests.list(**params)
    except GitlabError as exc:
        LOG_EXCEPTION(exception=exc, exit=False)
        return []


def get_gl_mr_by_iid(gl_project: Project, mr_iid: str) -> Optional[ProjectMergeRequest]:
    """Fetch a specific merge request by its IID."""
    try:
        return gl_project.mergerequests.get(mr_iid)
    except GitlabError as exc:
        LOG_EXCEPTION(exception=exc, exit=False)
        return None


def create_gl_mr( gl_project: Project, *, source_branch: str, target_branch: str, title: str, description: str, remove_source_branch: bool = False, draft: bool = False, ) -> Optional[ProjectMergeRequest]:
    """Create a GitLab merge request with sane defaults and error handling."""
    mr_title = title
    if draft and not mr_title.lower().startswith('draft:'):
        mr_title = f"Draft: {mr_title}"

    payload = {
        'source_branch': source_branch,
        'target_branch': target_branch,
        'title': mr_title,
        'remove_source_branch': remove_source_branch,
        'description': description,
    }

    try:
        return gl_project.mergerequests.create(payload)
    except GitlabError as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to create merge request: {exc}")
        return None


def get_diff_from_mr_file_changes(mr_file_changes: List[MrFileChange]) -> str:
    """
    Aggregates diffs from a list of MrFileChange objects into a single string.

    Returns:
        A single string containing the concatenated diffs for all files.
    """
    full_diff_lines = []
    for change in mr_file_changes:
        diff_content = change.GetDiff()
        # Only add an entry for a file if there is an actual diff content
        if diff_content:
            # To make this function work optimally, the MrFileChange class
            # should expose `old_path` and `new_path`. See recommended
            # class improvement below.
            full_diff_lines.append(f"--- a/{change.old_file_path_before_change}")
            full_diff_lines.append(f"+++ b/{change.new_file_path_after_change}")
            full_diff_lines.append(diff_content)

    return '\n'.join(full_diff_lines)


def get_file_from_remote(gl_project, file_path_str: str, ref):
    """
    Given a gitlab project, file path and ref, get the content of the file
    """
    file = gl_project.files.get(file_path=file_path_str, ref=ref)
    return base64.b64decode(file.content).decode("utf-8")


def get_project_remotes(gl_project):
    """
    Given a gitlab project, get the remotes
    """
    return gl_project.remotes.list()


def get_file_changes_from_url(mr_url: str) -> Union[List[MrFileChange], None]:
    """
    Retrieves a list of file changes from a GitLab Merge Request URL.
    Ex: https://gitlab.com/intellian_adc/prototyping/insensesdk/-/merge_requests/164

    Returns:
        A list of MrFileChange objects, where each object represents one changed file.
        Returns None if an error occurs.
    """
    try:
        info: InfoFromMrUrl = get_info_from_mr_url(mr_url)
        gl_project_path = info.gl_project_path
        mr_iid = info.mr_iid

        # This part for getting credentials remains the same, assuming it's configured
        repoInfo: IesaLocalRepoInfo = LOCAL_REPO_MAPPING.get_by_gl_project_path(gl_project_path)

        # Get project and MR objects
        project = get_gl_project(repoInfo)
        mr: ProjectMergeRequest = project.mergerequests.get(mr_iid)

        # Get the changes, which includes the diff for each file
        change_details = mr.changes()

        # The 'changes' key contains a list of dictionaries, one for each file
        if isinstance(change_details, dict) and 'changes' in change_details:

            file_changes_list = []
            for change in change_details['changes']:
                # Create an instance of our new class for each file change
                # Pass the project and mr objects so it can fetch file content later
                file_change_obj = MrFileChange(change_data=change, project=project, mr=mr)
                file_changes_list.append(file_change_obj)

            return file_changes_list
        else:
            # The API response was not in the expected format
            LOG(f"Unexpected format from mr.changes() for MR !{mr_iid} in project {gl_project_path}")
            return None

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

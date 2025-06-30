# Prerequistes:
### Install python requirements (pip)

```bash
pip install -r requirements.txt
```

### Install LINUX requirements

```bash
./linux_pkg_setup.sh
```

# Note
- Doc for python-gitlab: https://python-gitlab.readthedocs.io/en/stable/gl_objects/pipelines_and_jobs.html
- The python script have to be run in anywhere but not tmp build

# TODO
- Update OW local build support build IESA
	- Make it clone + copy tisdk tool bsp current tar 

# HOW TO
- Run OW local build
```bash
source ~/local_build/MyVenvFolder/bin/activate && ~/local_build/main_ow_local_build.py --manifest_source local --build_type binary --ow_manifest_ref manpack_master --tisdk_ref manpack_master --overwrite_local true --overwrite_repos intellian_pkg upgrade.git submodule_spibeam insensesdk adc_lib third_party_apps --interactive true
```

- Run Gitlab CI local
```bash
source ~/local_build/MyVenvFolder/bin/activate && cd ~/core_repos/intellian_pkg/ && ~/local_build/main_local_gitlab_ci.py -p ~/core_repos/intellian_pkg/.gitlab-ci.yml
```

- Run local static check
```bash
source ~/local_build/MyVenvFolder/bin/activate && ~/local_build/main_local_cpp_static_check.py --inputs ~/core_repos/oneweb_project_sw_tools/ --ignore-dirs ~/core_repos/oneweb_project_sw_tools/tmp_build/apps/insensesdk  ~/core_repos/oneweb_project_sw_tools/tmp_build/apps/third_party_apps
```
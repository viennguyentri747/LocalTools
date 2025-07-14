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
## Run OW local build
### For remote manifest + override with local repo
```bash
source ~/local_tools/MyVenvFolder/bin/activate && python3 ~/local_tools/main_ow_local_build.py --build_type iesa --manifest_source remote --ow_manifest_branch manpack_master --tisdk_ref manpack_master --is_overwrite_local_repos true --overwrite_repos intellian_pkg upgrade.git submodule_spibeam insensesdk adc_lib third_party_apps --interactive true
```

### For build local manifest + override with local repo
```bash
source ~/local_tools/MyVenvFolder/bin/activate && python3 ~/local_tools/main_ow_local_build.py --build_type iesa --manifest_source local --ow_manifest_branch Test-fan11july --tisdk_ref master --is_overwrite_local_repos true --overwrite_repos intellian_pkg --interactive false && rmh && scp -rJ root@192.168.101.79 ~/ow_sw_tools/tmp_build/out/bin/aim_manager ~/ow_sw_tools/tmp_build/out/bin/fan_controller_test root@192.168.100.254:/home/root/download/
```

```bash
#Build IESA
source ~/local_tools/MyVenvFolder/bin/activate && python3 ~/local_tools/main_ow_local_build.py --manifest_source local --build_type iesa --ow_manifest_branch Test-fan11july --tisdk_ref master --is_overwrite_local_repos true --overwrite_repos intellian_pkg adc_lib && rmh && scp -rJ root@192.168.101.79 ~/ow_sw_tools/tmp_build/out/bin/aim_manager ~/ow_sw_tools/tmp_build/out/bin/fan_controller_test root@192.168.100.254:/home/root/download/
```

## Run Gitlab CI local
```bash
source ~/local_tools/MyVenvFolder/bin/activate && cd ~/core_repos/intellian_pkg/ && python3 ~/local_tools/main_local_gitlab_ci.py -p ~/core_repos/intellian_pkg/.gitlab-ci.yml
```

## Run local static check
```bash
source ~/local_tools/MyVenvFolder/bin/activate && python3 ~/local_tools/main_local_cpp_static_check.py --inputs ~/core_repos/oneweb_project_sw_tools/ --ignore-dirs ~/core_repos/oneweb_project_sw_tools/tmp_build/apps/insensesdk  ~/core_repos/oneweb_project_sw_tools/tmp_build/apps/third_party_apps
```

## Decode GPS Status
```bash
python3 ~/local_tools/other_local_tools/decode_gps_status.py --status "0x312"
```

## Convert gps tow to utc time
```bash
python3 ~/local_tools/other_local_tools/convert_time_gps_tow_to_utc.py --week 2373 --time_of_week_ms 271835600
```
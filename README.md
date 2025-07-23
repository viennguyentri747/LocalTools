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
### Buid BINARY using LOCAL manifest + OVERRIDE with local repo
```bash
source ~/local_tools/MyVenvFolder/bin/activate && python3 ~/local_tools/main_ow_local_build.py --build_type binary --manifest_source local --ow_manifest_branch Test-fan11july --overwrite_repos intellian_pkg upgrade submodule_spibeam insensesdk adc_lib third_party_apps --interactive false
#Extra option: Quick rebuild `--sync false`
```
### Buid IESA using LOCAL manifest + OVERRIDE with local repo
```bash
source ~/local_tools/MyVenvFolder/bin/activate && python3 ~/local_tools/main_ow_local_build.py --build_type iesa --tisdk_ref master --manifest_source local --ow_manifest_branch Test-fan11july --overwrite_repos intellian_pkg upgrade submodule_spibeam insensesdk adc_lib third_party_apps --interactive false

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
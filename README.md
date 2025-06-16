# Prerequistes:

```
pip install python-gitlab
```

# Note
- Doc for python-gitlab: https://python-gitlab.readthedocs.io/en/stable/gl_objects/pipelines_and_jobs.html
- The python script have to be run in anywhere but not tmp build

# TODO
- Update OW local build support build IESA
	- Make it clone + copy tisdk tool bsp current tar 

# HOW TO
- Run
```
python ~/ow_sw_tools/v_test_folder/LocalBuild/ow_local_build.py --manifest_source local --build_type iesa --ow_branch manpack_master --tisdk_branch manpack_master
```

...
6b7942ac31181d1da5ff66f7c07c2d47  iesa_board_release.tar.xz
(3.8.12) [test_ins_shm_rgnss_June13]vien:~/workspace/intellian_core_repos/oneweb_project_sw_tools/$ md5sum packaging/bsp_current/bsp_current.tar.xz
0ad5a0b146da6b3aeaafe23d8e79a5eb  packaging/bsp_current/bsp_current.tar.xz
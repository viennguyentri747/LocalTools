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
python ~/ow_sw_tools/v_test_folder/LocalBuild/main_ow_local_build.py --manifest_source local --build_type binary --ow_manifest_branch manpack_master --tisdk_branch manpack_master --overwrite_local true --overwrite_repos adc_lib insensesdk --interactive true
```

...
#ACTUAL
md5sum ~/ow_sw_tools/iesa_board_release.tar.xz
6b7942ac31181d1da5ff66f7c07c2d47  iesa_board_release.tar.xz

md5sum ~/ow_sw_tools/packaging/bsp_current/bsp_current.tar.xz
e0ad5a0b146da6b3aeaafe23d8e79a5eb  packaging/bsp_current/bsp_current.tar.xz

md5sum ~/ow_sw_tools/v_test_folder/LocalBuild/bsp_artifacts/bsp-iesa-f6c83d7f4f2803c600220408b0d7d403c93a0db0.tar.xz
0bfa9507436ab28c5e569f82c687f9a0  /home/vien/ow_sw_tools/v_test_folder/LocalBuild/bsp_artifacts/bsp-iesa-f6c83d7f4f2803c600220408b0d7d403c93a0db0.tar.xz

(3.8.12) [manpack_master]vien:~/workspace/intellian_core_repos/oneweb_project_sw_tools/packaging/bsp_current/$ md5sum ~/downloads/bsp-iesa-debug-f6c83d7f4f2803c600220408b0d7d403c93a0db0.tar.xz 
fa3c224c9b341096ba346ea196ae1a8c  /home/vien/downloads/bsp-iesa-debug-f6c83d7f4f2803c600220408b0d7d403c93a0db0.tar.xz

```
/tools/build_tools/build_iesa_rootfs_tar.sh tmp_build/ ./packaging/bsp_current/bsp_current.tar.xz
#############################################
# Packaging Intellian Legacy & ADC Apps...  #
#############################################
####
#### Using the following BSP:
####
####
#### lrwxrwxrwx 1 docker_user docker_user 32 May 14 22:46 ./packaging/bsp_current/bsp_current.tar.xz -> EXAMPLE-bsp-iesa-69591aa1.tar.xz
####
####
#### To change it, please download a new BSP and symlink it to ./packaging/bsp_current/bsp_current.tar.xz
####
####
#### Untar the BSP to the temporary packaging directory
```
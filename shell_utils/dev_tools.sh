tool(){
	~/local_tools/main_tools.py "$@"
}

tools(){
	tool "$@"
}

extract_context_from_path() {
	python3 ~/local_tools/code_tools/extract_context_from_paths.py "$@"
}

fdef() {
	# ~/local_tools/tool_invoker_cli.py '/home/vien/local_tools/available_tools/code_tools/t_get_grep_template.py'
	~/local_tools/MyVenvFolder/bin/python /home/vien/workspace/other_projects/custom_tools/LocalTools/available_tools/code_tools/t_get_grep_template.py --search-mode fzf-symbols --pattern-keys c-function-definition c-variable-definition c-class-struct-definition c-macro-definition c-typedef-definition c-enum-definition --file-exts c cpp cc cxx h hpp hxx --path ~/core_repos/
}

fsymbol() {
	/home/vien/local_tools/MyVenvFolder/bin/python /home/vien/workspace/other_projects/custom_tools/LocalTools/available_tools/code_tools/t_get_grep_template.py --search-mode fzf-symbols --pattern-keys c-function-call c-symbol-usage --file-exts c cpp cc cxx h hpp hxx --path ~/core_repos/
}
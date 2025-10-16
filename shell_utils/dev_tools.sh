tool(){
	~/local_tools/main_tools.py "$@"
}

tools(){
	tool "$@"
}

extract_context_from_path() {
	python3 ~/local_tools/code_tools/extract_context_from_paths.py "$@"
}

find_symbols() {
	~/local_tools/tool_invoker_cli.py '/home/vien/local_tools/available_tools/code_tools/t_get_grep_template.py'
}

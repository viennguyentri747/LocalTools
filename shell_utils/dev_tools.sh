tool(){
	~/local_tools/main_tools.py "$@"
}

tools(){
	tool "$@"
}


extract_context_from_path() {
	python3 ~/local_tools/code_tools/extract_context_from_paths.py "$@"
}

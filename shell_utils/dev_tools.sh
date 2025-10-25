tool(){
	~/local_tools/main_tools.py "$@"
}

tools(){
	tool "$@"
}

extract_context() {
	~/local_tools/tool_invoker_cli.py '/home/vien/local_tools/available_tools/code_tools/t_extract_code_context.py'
}


_DT_GREP_TOOL="/home/vien/local_tools/MyVenvFolder/bin/python /home/vien/workspace/other_projects/custom_tools/LocalTools/available_tools/code_tools/t_get_grep_template.py"
_DT_CORE_REPOS_PATH="~/core_repos/"
_DT_C_EXTS="c cpp cc cxx h hpp hxx"
# NOTE: The pattern-key order below controls the labeled category order in the fzf results.
fdef() {
    $_DT_GREP_TOOL --display-name "Search C/C++ Definitions" --search-mode fzf-symbols --case-sensitive False --ordered-pattern-keys c-class-struct-definition c-typedef-definition c-function-definition c-enum-definition c-enum-value-definition c-macro-definition c-variable-definition --file-exts $_DT_C_EXTS --path $_DT_CORE_REPOS_PATH ${1:+--initial-query "$*"}
}

fsymbol() {
    $_DT_GREP_TOOL --display-name "Search C/C++ Symbols" --search-mode fzf-symbols --case-sensitive False --ordered-pattern-keys c-function-call c-symbol-usage --file-exts $_DT_C_EXTS --path $_DT_CORE_REPOS_PATH ${1:+--initial-query "$*"}
}

ffile() {
    $_DT_GREP_TOOL --display-name "Search Files by Name" --search-mode fzf-files --path $_DT_CORE_REPOS_PATH ${1:+--initial-query "$*"}
}

ftext() {
    $_DT_GREP_TOOL --display-name "Search for Text (grep)" --search-mode fzf-text --case-sensitive False --file-exts $_DT_C_EXTS --path $_DT_CORE_REPOS_PATH ${1:+--initial-query "$*"}
}

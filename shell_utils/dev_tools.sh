# codex(){
#     # Run codex without asking for approval + 
#     command codex --ask-for-approval never --sandbox workspace-write "$@"
# }

tool(){
	~/local_tools/main_tools.py "$@"
}

tools(){
	tool "$@"
}

is_tools(){
	local tools_dir=~/local_tools/available_tools/inertial_sense_tools
	tool --tools_dir "$tools_dir" "$@"
}

all_tools(){
    ~/local_tools/main_tools.py  --folder_pattern "^.*_tools$"
}

extract_context() {
	~/local_tools/tool_invoker_cli.py '/home/vien/local_tools/available_tools/code_tools/t_extract_code_context.py'
}

get_acu_logs() {
    ~/local_tools/tool_invoker_cli.py '/home/vien/local_tools/available_tools/misc_hidden_tools/t_get_acu_logs.py' "$@"
}

_DT_GREP_TOOL=(/home/vien/local_tools/MyVenvFolder/bin/python /home/vien/workspace/other_projects/custom_tools/LocalTools/available_tools/code_tools/t_get_grep_template.py)
_DT_CORE_REPOS_PATH="~/core_repos/"
_DT_C_EXTS=(c cpp cc cxx h hpp hxx)
# NOTE: The pattern-key order below controls the labeled category order in the fzf results.
fdef() {
    local initial_query=()
    [ $# -gt 0 ] && initial_query=(--initial-query "$*")
    "${_DT_GREP_TOOL[@]}" --display-name "Search C/C++ Definitions" --search-mode fzf-symbols --case-sensitive False --ordered-pattern-keys c-class-struct-definition c-typedef-definition c-function-definition c-enum-definition c-enum-value-definition c-macro-definition c-variable-definition --file-exts "${_DT_C_EXTS[@]}" "${initial_query[@]}"
    #--path $_DT_CORE_REPOS_PATH
}

fdecl() {
    local initial_query=()
    [ $# -gt 0 ] && initial_query=(--initial-query "$*")
    "${_DT_GREP_TOOL[@]}" --display-name "Search C/C++ Declarations" --search-mode fzf-symbols --case-sensitive False --ordered-pattern-keys c-function-declaration --file-exts "${_DT_C_EXTS[@]}" "${initial_query[@]}"
}

fsymbol() {
    local initial_query=()
    [ $# -gt 0 ] && initial_query=(--initial-query "$*")
    "${_DT_GREP_TOOL[@]}" --display-name "Search C/C++ Symbols" --search-mode fzf-symbols --case-sensitive False --ordered-pattern-keys c-symbol-usage --file-exts "${_DT_C_EXTS[@]}" "${initial_query[@]}"
}

ffile() {
    local initial_query=()
    [ $# -gt 0 ] && initial_query=(--initial-query "$*")
    "${_DT_GREP_TOOL[@]}" --display-name "Search Files by Name" --search-mode fzf-files "${initial_query[@]}"
}

ftext() {
    local initial_query=()
    [ $# -gt 0 ] && initial_query=(--initial-query "$*")
    "${_DT_GREP_TOOL[@]}" --display-name "Search for Text (grep)" --search-mode fzf-text --case-sensitive False "${initial_query[@]}"
}

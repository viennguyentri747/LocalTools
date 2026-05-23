# codex(){
#     # Run codex without asking for approval + 
#     command codex --ask-for-approval never --sandbox workspace-write "$@"
# }

_MY_AGENT_DIR_NAME="MY_AGENT"
_MY_AGENT_INPUT_DIR_NAME="INPUT"
_MY_AGENT_OUTPUT_DIR_NAME="OUTPUT"
_MY_AGENT_TODO_NEXT_FILE_NAME="AGENT_TODO_NEXT.md"

codex() {
    
}

# AI agent tools
check_create_agent_dir_if_not_exist(){
    # Check if the agent directory exists in current dir, if not, create it
    if [ ! -d $_MY_AGENT_DIR_NAME ]; then
        log "Creating agent directory: $_MY_AGENT_DIR_NAME"
        mkdir $_MY_AGENT_DIR_NAME
        mkdir $_MY_AGENT_DIR_NAME/$_MY_AGENT_INPUT_DIR_NAME
        mkdir $_MY_AGENT_DIR_NAME/$_MY_AGENT_OUTPUT_DIR_NAME
    fi
}

agent_todo_next(){
    # Open agent todo next file
    check_create_agent_dir_if_not_exist
    code "$_MY_AGENT_DIR_NAME/$_MY_AGENT_INPUT_DIR_NAME/$_MY_AGENT_TODO_NEXT_FILE_NAME"
}

codex() {
    # 1. Run the prerequisite command
    agent_todo_next
    
    # 2. Run the actual codex command, passing all arguments ($@)
    command codex "$@"
}

tool(){
	~/core_repos/local_tools/main_tools.py "$@"
}

tools(){
	tool "$@"
}

is_tools(){
	local tools_dir=~/core_repos/local_tools/available_tools/inertial_sense_tools
	tool --tools_dir "$tools_dir" "$@"
}

all_tools(){
    ~/core_repos/local_tools/main_tools.py  --folder_pattern "^.*_tools$"
}

extract_context() {
	~/core_repos/local_tools/tool_invoker_cli.py '~/core_repos/local_tools/available_tools/code_tools/t_extract_code_context.py'
}

get_acu_logs() {
    ~/core_repos/local_tools/tool_invoker_cli.py '~/core_repos/local_tools/available_tools/misc_hidden_tools/t_get_acu_logs.py' "$@"
}

test_mcp() {
    if [ -z "$1" ]; then
        log "Usage: test_mcp <path_to_mcp_server.py>. Ex: test_mcp ~/core_repos/local_tools/mcp_server/ssh_command_mcp_server.py"
        return 1
    fi

    # Convert to absolute path if it isn't already
    local ABS_PATH=$(realpath "$1")

    log "Starting MCP Inspector for: $ABS_PATH"
    npx @modelcontextprotocol/inspector "$ABS_PATH"
}

_DT_GREP_TOOL=(local_python ~/core_repos/local_tools/available_tools/code_tools/t_get_grep_template.py)
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

ftext_noninteractive() {
    local initial_query=()
    [ $# -gt 0 ] && initial_query=(--initial-query "$*")
    "${_DT_GREP_TOOL[@]}" --display-name "Search for Text (grep)" --search-mode grep-text --case-sensitive False "${initial_query[@]}"
}

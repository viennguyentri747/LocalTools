# Alias without argument
alias rmh="rm -f ~/.ssh/known_hosts"
# alias clean_trash="cmd rm -rf ~/.local/share/Trash/*"
alias sshp="sshpass -p"
# alias cb="tee >(xclip -selection clipboard -in) | wc -l | xargs -I{} echo '{} lines copied to clipboard!'"
alias cb='tee >(xclip -selection clipboard -in >/dev/null) | wc -l | xargs -I{} echo "{} lines copied to clipboard!"' #Redirect >/dev/null inside the process substitution so wc isn’t stuck waiting for input
alias pb='xclip -selection clipboard -out' # Paste from clipboard
alias subl='/mnt/c/Program\ Files/Sublime\ Text/subl.exe'
alias stock-alert='~/stock_alert/MyVenvFolder/bin/python ~/stock_alert/stock_alert/main.py'
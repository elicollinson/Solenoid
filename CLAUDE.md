- You can test the terminal here with tmux tmux new-session -d -s cc-tui './your_tui_app --dev 2>&1 | tee /tmp/cc-tui.log'

# 3) From Claude Code, tell it to drive the session with tmux:
#   - Send keys / commands:
tmux send-keys -t cc-tui 'h' Enter
#   - Capture the current "screen" as text for analysis:
tmux capture-pane -pt cc-tui -S -1000 > /tmp/cc-tui_screen.txt
#   - (Optional) Persist output:
tmux pipe-pane -t cc-tui -o 'cat >> /tmp/cc-tui_screen.log'
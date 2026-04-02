export PATH=/workspace/.openart/runners/target/state/tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; prompt=$(cat /task/task.md); guide_file="${OPENART_TOOL_GUIDE_FILE:-}"; if [ -n "$guide_file" ] && [ -f "$guide_file" ]; then guide=$(cat "$guide_file"); prompt=$(printf 'OpenART runtime note:
- Your working directory is /workspace.
- Use the available local tools below when they match the task.

%s

Task:
%s' "$guide" "$prompt"); fi; exec opencode run "$prompt"

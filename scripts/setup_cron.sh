#!/usr/bin/env bash
# setup_cron.sh — 安装 BuddyKeeper 定时任务（默认每天 09:00，ubuntu 身份执行）
#
# 必须以 root 运行（写 /etc/cron.d）。
# /etc/cron.d 行格式为「分 时 日 月 周 用户 命令」——用户字段必须在命令之前，
# 写错会让 cron 把解释器当用户名，任务永不触发。
set -euo pipefail

BK_REMOTE="${BK_REMOTE:-/opt/buddy-keeper}"
BK_USER="${BK_USER:-ubuntu}"
BK_PYTHON="${BK_PYTHON:-/usr/bin/python3}"
BK_HOUR="${BK_HOUR:-9}"
BK_MINUTE="${BK_MINUTE:-0}"
# 日/月字段：默认 * （每天执行）。临时验证可设 BK_DOM=28 BK_MON=10 做一次性调度。
BK_DOM="${BK_DOM:-*}"
BK_MON="${BK_MON:-*}"

CRON_FILE="/etc/cron.d/buddy-keeper"
RUNNER="$BK_REMOTE/src/daily_runner.py"

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 运行：sudo bash $0" >&2
  exit 1
fi

command -v "$BK_PYTHON" >/dev/null 2>&1 || { echo "缺少 $BK_PYTHON" >&2; exit 1; }
[ -f "$RUNNER" ] || { echo "未找到 $RUNNER，请先执行 deploy.py" >&2; exit 1; }
[ -f "$BK_REMOTE/config/config.json" ] || echo "警告：缺少 config/config.json，推送将被跳过"

mkdir -p "$BK_REMOTE/logs"
chown -R "$BK_USER:$BK_USER" "$BK_REMOTE"
# 确保 cron.log 跨身份可写：ubuntu 的 cron 与 root 的 wecom-echo 都会重定向到它；
# 若属主为 root 且权限 644，ubuntu 的 >> 重定向会失败，导致 daily_runner 根本不启动。
touch "$BK_REMOTE/logs/cron.log"
chown "$BK_USER:$BK_USER" "$BK_REMOTE/logs/cron.log"
chmod 0666 "$BK_REMOTE/logs/cron.log"

cat > "$CRON_FILE" <<EOF
# BuddyKeeper 每日值守（用户字段必须在命令之前）
# 日志重定向保底：若 cron.log 不可写（如被改回 root 属主/权限收紧），自动降级到 ubuntu 自有日志文件，
# 保证 daily_runner 始终能启动，不会因 shell 重定向失败而静默不执行。
$BK_MINUTE $BK_HOUR $BK_DOM $BK_MON * $BK_USER LOG="$BK_REMOTE/logs/cron.log"; [ -w "\$LOG" ] || LOG="$BK_REMOTE/logs/cron.\$(id -u).log"; touch "\$LOG" 2>/dev/null; chmod 0666 "\$LOG" 2>/dev/null; $BK_PYTHON $RUNNER >> "\$LOG" 2>&1
EOF
chmod 644 "$CRON_FILE"

if command -v systemctl >/dev/null 2>&1; then
  systemctl restart cron 2>/dev/null || systemctl restart crond 2>/dev/null || true
  systemctl enable cron 2>/dev/null || systemctl enable crond 2>/dev/null || true
fi

echo "已写入 $CRON_FILE："
cat "$CRON_FILE"
echo
echo "cron：$(systemctl is-active cron 2>/dev/null || echo unknown)"
if [ "$BK_DOM" = "*" ] && [ "$BK_MON" = "*" ]; then
  echo "下次触发：每天 $(printf '%02d:%02d' "$BK_HOUR" "$BK_MINUTE")（时区 $(date +%Z)）"
else
  echo "下次触发：$BK_MON 月 $BK_DOM 日 $(printf '%02d:%02d' "$BK_HOUR" "$BK_MINUTE") 一次性（时区 $(date +%Z)）"
fi
echo "手动验证：cd $BK_REMOTE && WB_MAX_RETRIES=0 $BK_PYTHON src/daily_runner.py"

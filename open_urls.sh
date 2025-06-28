#!/bin/bash

FILE="urls.txt"

while IFS= read -r line || [ -n "$line" ]; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue

    minute=$(echo "$line" | awk '{print $1}')
    url=$(echo "$line" | awk '{print $2}')
    seconds=$((minute * 60))

    echo ""
    echo "🔗 開啟網址："
    echo $url
    echo "$minute 分鐘"

    # 開啟 Brave（app 模式可選）
    /Applications/Brave\ Browser.app/Contents/MacOS/Brave\ Browser --new --app="$url" &

    sleep "$seconds"

    echo "⏱️ 關閉所有 Brave..."

    # 使用 AppleScript 關掉整個 Brave Browser
    osascript <<EOF
    tell application "Brave Browser"
        if it is running then
            quit
        end if
    end tell
EOF

    sleep 3
done < "$FILE"


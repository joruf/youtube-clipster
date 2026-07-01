#!/bin/bash

# Show a pulsating progress dialog while fetching video metadata from YouTube.
#
# @param string $1 YouTube video URL
# @return string Sanitized video title on stdout
show_loading_while_fetching_title() {
    local clip="$1"
    local title

    zenity --progress --pulsate --no-cancel \
        --title="${MESSAGES[progress_title]}" \
        --text="${MESSAGES[link_loading]}" \
        --width=450 2>/dev/null &
    local zenity_pid=$!

    title=$(get_video_title "$clip")

    kill "$zenity_pid" 2>/dev/null
    wait "$zenity_pid" 2>/dev/null

    echo "$title"
}

select_format() {
    local title="$1"
    zenity --list --title="${MESSAGES[zenity_format_title]}" \
      --text="${MESSAGES[zenity_format_text_prefix]}\n$title" --radiolist \
      --column="${MESSAGES[zenity_format_col_select]}" --column="${MESSAGES[zenity_format_col_format]}" \
      TRUE "${MESSAGES[zenity_format_mp3]}" FALSE "${MESSAGES[zenity_format_mp4]}" 2>/dev/null
}

select_audio_lang() {
    local title="$1"
    zenity --list --title="${MESSAGES[zenity_lang_title]}" \
      --text="${MESSAGES[zenity_lang_text]}\n$title" --radiolist \
      --column="${MESSAGES[zenity_format_col_select]}" --column="Sprache" \
      FALSE "${MESSAGES[lang_de]}" FALSE "${MESSAGES[lang_en]}" TRUE "${MESSAGES[lang_best]}" 2>/dev/null
}

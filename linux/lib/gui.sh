#!/bin/bash

# Show loading dialog while title and audio languages are fetched in parallel.
#
# @param string $1 YouTube video URL
# @return string Sanitized video title on stdout
show_loading_while_fetching_metadata() {
    local clip="$1"
    local cache_dir title

    clear_video_metadata_cache
    cache_dir=$(mktemp -d)
    VIDEO_META_CACHE_DIR="$cache_dir"

    zenity --progress --pulsate --no-cancel \
        --title="${MESSAGES[progress_title]}" \
        --text="${MESSAGES[link_loading]}" \
        --width=450 2>/dev/null &
    local zenity_pid=$!

    get_video_title "$clip" > "$cache_dir/title" &
    local pid_title=$!

    start_audio_language_prefetch "$clip" "$cache_dir"

    wait "$pid_title"

    kill "$zenity_pid" 2>/dev/null
    wait "$zenity_pid" 2>/dev/null

    title=$(cat "$cache_dir/title" 2>/dev/null)
    echo "${title:-${MESSAGES[fallback_title]}}"
}

select_format() {
    local title="$1"
    zenity --list --title="${MESSAGES[zenity_format_title]}" \
      --text="${MESSAGES[zenity_format_text_prefix]}\n$title" --radiolist \
      --column="${MESSAGES[zenity_format_col_select]}" --column="${MESSAGES[zenity_format_col_format]}" \
      TRUE "${MESSAGES[zenity_format_mp3]}" FALSE "${MESSAGES[zenity_format_mp4]}" 2>/dev/null
}

# Show audio track selection dialog with all available languages from the video.
#
# @param string $1 Sanitized video title
# @param string $2 YouTube video URL
# @return string Selected language code on stdout (or empty if canceled)
select_audio_lang() {
    local title="$1"
    local clip="$2"
    local -a zenity_rows=()
    local code label is_default

    while IFS='|' read -r code label is_default; do
        [[ -z "$code" ]] && continue
        if [[ "$is_default" == "1" ]]; then
            zenity_rows+=(TRUE "$label" "$code")
        else
            zenity_rows+=(FALSE "$label" "$code")
        fi
    done < <(get_audio_language_options_cached "$clip")

    if [[ ${#zenity_rows[@]} -eq 0 ]]; then
        zenity_rows=(TRUE "${MESSAGES[lang_best]}" "default")
    fi

    zenity --list --title="${MESSAGES[zenity_lang_title]}" \
        --text="${MESSAGES[zenity_lang_text]}\n$title" --radiolist \
        --print-column=3 --hide-column=3 \
        --column="${MESSAGES[zenity_format_col_select]}" \
        --column="${MESSAGES[zenity_lang_col]}" \
        --column="Code" \
        "${zenity_rows[@]}" 2>/dev/null
}

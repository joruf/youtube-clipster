#!/bash/bin

# Initialize environment paths and self-updates for target download tool
prepare_ytdlp() {
    log_message "INFO" "Checking yt-dlp version and updates..."
    if [[ ! -f "$YTDLP_BIN" ]]; then
        log_message "WARN" "Local yt-dlp binary not found. Downloading latest release..."
        curl -L "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp" -o "$YTDLP_BIN"
        chmod +x "$YTDLP_BIN"
        log_message "INFO" "yt-dlp installed successfully at $YTDLP_BIN"
    else
        log_message "DEBUG" "Checking local yt-dlp binary for updates..."
        local ut_out
        ut_out=$("$YTDLP_BIN" -U 2>&1)
        log_message "DEBUG" "yt-dlp update check output: $(echo "$ut_out" | tr '\n' ' ')"
    fi
}

# Query specific metadata array from URL strings
get_video_title() {
    local clip="$1"
    local title
    local -a js_args=()
    log_message "DEBUG" "Fetching video metadata from YouTube..."
    ytdlp_js_runtime_args js_args
    title=$("$YTDLP_BIN" --no-warnings "${js_args[@]}" --get-title "$clip" 2>/dev/null)
    local safe_title
    safe_title=$(echo "${title:-${MESSAGES[fallback_title]}}" | sed 's/[^a-zA-Z0-9._ -]/ /g')
    log_message "INFO" "Title successfully retrieved: $safe_title"
    echo "$safe_title"
}

# Dynamically fetch and log verified audio track languages from YouTube formats
get_available_languages() {
    local clip="$1"
    log_message "DEBUG" "Fetching available audio tracks from YouTube..."

    local -a js_args=()
    ytdlp_js_runtime_args js_args

    local langs
    langs=$("$YTDLP_BIN" --no-warnings --ignore-config "${js_args[@]}" --print "%(formats.:.language)s" "$clip" 2>/dev/null | tr -d '[]" ' | tr ',' '\n' | grep -vE "^(null|NA|none|$)$" | sort -u)

    if [[ -z "$langs" ]]; then
        log_message "DEBUG" "Verified audio languages discovered: None (Using default)"
        echo ""
    else
        log_message "DEBUG" "Verified audio languages discovered: $(echo "$langs" | tr '\n' ' ')"
        echo "$langs"
    fi
}

# Run download sequence loop containing progress bar interfaces
run_download() {
    local format="$1" local lang_filter="$2" local clip="$3" local safe_title="$4"
    local error_log
    error_log=$(mktemp)

    local -a js_args=()
    ytdlp_js_runtime_args js_args

    log_message "INFO" "Starting yt-dlp download process..."
    log_message "DEBUG" "Download arguments: Format=$format | Filter=$lang_filter | Target-Dir=$(pwd)"

    if (
      echo "# ${MESSAGES[progress_downloading]}"; echo "5"
      if [[ "$format" == "${MESSAGES[zenity_format_mp3]}" ]]; then
          cmd=("$YTDLP_BIN" "${js_args[@]}" "--newline" "--restrict-filenames" "-x" "--audio-format" "mp3" "--audio-quality" "0" "--format" "ba${lang_filter}/ba" "$clip")
      else
          cmd=("$YTDLP_BIN" "${js_args[@]}" "--newline" "--restrict-filenames" "-f" "bv*[ext=mp4]+ba${lang_filter}[ext=m4a]/b[ext=mp4] / bv*+ba/b" "--merge-output-format" "mp4" "$clip")
      fi
      
      log_message "DEBUG" "Executing command: ${cmd[*]}"
      
      "${cmd[@]}" 2> >(tee "$error_log" >&2) | while read -r line; do
          if [[ "$line" =~ ([0-9.]+)% ]]; then
              percent=$(echo "${BASH_REMATCH[1]}" | cut -d'.' -f1)
              [[ "$percent" -lt 99 ]] && echo "$percent"
          fi
          if [[ "$line" == *"[ExtractAudio]"* || "$line" == *"[Merger]"* ]]; then
              echo "# ${MESSAGES[progress_converting_prefix]} $(echo "$format" | tr '[:lower:]' '[:upper:]')${MESSAGES[progress_converting_suffix]}"
              echo "50"
          fi
      done
      echo "100"; sleep 1
    ) | zenity --progress --title="${MESSAGES[progress_title]}" --text="${MESSAGES[progress_text_prefix]} $safe_title" --auto-close --width=500; then
        log_message "INFO" "Download finished successfully!"
        if [[ "$OPEN_NEMO" = true ]]; then
            log_message "DEBUG" "Opening file manager (Nemo)..."
            nemo "$DOWNLOAD_DIR" &
        fi
    else
        local err_content
        err_content=$(cat "$error_log")
        log_message "ERROR" "yt-dlp core process failed. Error log: $err_content"
        handle_download_error "$err_content"
    fi
    rm -f "$error_log"
}

# Catch specific runtime exception conditions returned by external providers
handle_download_error() {
    local error_msg="$1"
    if [[ "$error_msg" == *"confirm you are not a robot"* || "$error_msg" == *"429"* ]]; then
        zenity --error --title="YouTube Blockade" --text="${MESSAGES[error_bot_detected]}" --width=400
    elif [[ -n "$error_msg" ]]; then
        zenity --error --title="Fehler" --text="${MESSAGES[error_generic]}" --width=400
    fi
}

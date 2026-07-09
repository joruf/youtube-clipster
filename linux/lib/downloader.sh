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

# Global cache directory for prefetched metadata (title, languages).
VIDEO_META_CACHE_DIR=""
LANG_PREFETCH_PID=""

# Remove temporary metadata cache files.
clear_video_metadata_cache() {
    if [[ -n "$LANG_PREFETCH_PID" ]] && kill -0 "$LANG_PREFETCH_PID" 2>/dev/null; then
        kill "$LANG_PREFETCH_PID" 2>/dev/null
        wait "$LANG_PREFETCH_PID" 2>/dev/null
    fi
    LANG_PREFETCH_PID=""

    if [[ -n "$VIDEO_META_CACHE_DIR" && -d "$VIDEO_META_CACHE_DIR" ]]; then
        rm -rf "$VIDEO_META_CACHE_DIR"
        VIDEO_META_CACHE_DIR=""
    fi
}

# Start background prefetch of audio language options into the metadata cache.
#
# @param string $1 YouTube video URL
# @param string $2 Cache directory path
start_audio_language_prefetch() {
    local clip="$1"
    local cache_dir="$2"

    (
        get_audio_language_options "$clip" > "$cache_dir/languages"
        touch "$cache_dir/languages.ready"
    ) &
    LANG_PREFETCH_PID=$!
}

# Merge language lines and print options to stdout.
#
# @param string $1 Page source lines
# @param string $2 yt-dlp source lines
_merge_and_print_audio_language_options() {
    local page_lines="$1"
    local ytdlp_lines="$2"
    declare -A labels=()
    local primary_code="" code label is_selected

    while IFS='|' read -r code label is_selected; do
        [[ -z "$code" ]] && continue
        [[ -z "${labels[$code]+x}" ]] && labels["$code"]="$label"
        if [[ "$is_selected" == "1" && -z "$primary_code" ]]; then
            primary_code="$code"
        fi
    done <<< "$page_lines"

    while IFS='|' read -r code label is_selected; do
        [[ -z "$code" ]] && continue
        [[ -z "${labels[$code]+x}" ]] && labels["$code"]="$label"
        if [[ "$is_selected" == "1" && -z "$primary_code" ]]; then
            primary_code="$code"
        fi
    done <<< "$ytdlp_lines"

    if [[ ${#labels[@]} -eq 0 ]]; then
        log_message "DEBUG" "Verified audio languages discovered: None (using default)"
        echo "default|${MESSAGES[lang_best]}|1"
        return
    fi

    if [[ -z "$primary_code" ]]; then
        primary_code=$(printf '%s\n' "${!labels[@]}" | sort | head -n 1)
    fi

    log_message "DEBUG" "Verified audio languages discovered: $(printf '%s ' "${!labels[@]}") (default: ${primary_code})"

    echo "${primary_code}|${labels[$primary_code]}|1"
    for code in $(printf '%s\n' "${!labels[@]}" | sort); do
        [[ "$code" == "$primary_code" ]] && continue
        echo "${code}|${labels[$code]}|0"
    done
}

# Return prefetched audio language options or fetch them on demand.
#
# @param string $1 YouTube video URL
get_audio_language_options_cached() {
    local clip="$1"
    local cache_file cache_ready deadline

    if [[ -n "$VIDEO_META_CACHE_DIR" ]]; then
        cache_file="$VIDEO_META_CACHE_DIR/languages"
        cache_ready="$VIDEO_META_CACHE_DIR/languages.ready"
        deadline=$(($(date +%s) + 30))

        while [[ ! -f "$cache_ready" ]] && [[ $(date +%s) -lt $deadline ]]; do
            if [[ -n "$LANG_PREFETCH_PID" ]] && ! kill -0 "$LANG_PREFETCH_PID" 2>/dev/null; then
                break
            fi
            sleep 0.05
        done

        if [[ -s "$cache_file" ]]; then
            cat "$cache_file"
            return
        fi
    fi

    get_audio_language_options "$clip"
}

# Extract YouTube video ID from a watch or short URL.
#
# @param string $1 YouTube video URL
# @return string 11-character video ID on stdout
_youtube_video_id_from_url() {
    local clip="$1"
    echo "$clip" | grep -oE '(v=|youtu\.be/|/shorts/)([a-zA-Z0-9_-]{11})' | grep -oE '[a-zA-Z0-9_-]{11}$' | head -n 1
}

# Parse dubbed audio tracks from the YouTube watch page player response.
# Output format per line: code|label|is_selected (1 or 0).
#
# @param string $1 YouTube video URL
_get_audio_languages_from_youtube_page() {
    local clip="$1"
    local video_id accept_lang="en-US,en"

    video_id=$(_youtube_video_id_from_url "$clip")
    [[ -z "$video_id" ]] && return 0

    [[ "${LANG_CHOICE,,}" == "de" ]] && accept_lang="de-DE,de;q=0.9,en;q=0.8"

    curl -fsSL --compressed --connect-timeout 5 --max-time 20 \
        -A "$USER_AGENT" -H "Accept-Language: ${accept_lang}" \
        "https://www.youtube.com/watch?v=${video_id}" 2>/dev/null | python3 -c '
import json
import re
import sys

def extract_player_response(html):
    marker = "ytInitialPlayerResponse"
    start = html.find(marker)
    if start == -1:
        return None

    brace_start = html.find("{", start)
    if brace_start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for index, char in enumerate(html[brace_start:], brace_start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == "\"":
                in_string = False
            continue

        if char == "\"":
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return html[brace_start:index + 1]

    return None

html = sys.stdin.read()
payload = extract_player_response(html)
if not payload:
    sys.exit(0)

data = json.loads(payload)
tracks = {}

for fmt in data.get("streamingData", {}).get("adaptiveFormats", []):
    if "audio" not in fmt.get("mimeType", ""):
        continue
    audio_track = fmt.get("audioTrack") or {}
    if not isinstance(audio_track, dict) or not audio_track.get("id"):
        continue

    code = audio_track["id"].rsplit(".", 1)[0]
    label = audio_track.get("displayName", code)
    is_original = bool(re.search(r"original", label, re.I))
    is_default = bool(audio_track.get("audioIsDefault"))

    if code not in tracks:
        tracks[code] = {"label": label, "original": is_original, "default": is_default}
    else:
        tracks[code]["original"] = tracks[code]["original"] or is_original
        tracks[code]["default"] = tracks[code]["default"] or is_default

if not tracks:
    sys.exit(0)

primary = next((code for code, track in tracks.items() if track["original"]), None)
if not primary:
    primary = next((code for code, track in tracks.items() if track["default"]), None)
if not primary:
    primary = sorted(tracks.keys())[0]

ordered = [primary] + sorted(code for code in tracks if code != primary)
for code in ordered:
    label = tracks[code]["label"]
    print(f"{code}|{label}|{1 if code == primary else 0}")
'
}

# Parse audio-only formats from yt-dlp JSON metadata.
# Output format per line: code|label|is_selected (1 or 0).
#
# @param string $1 YouTube video URL
_get_audio_languages_from_ytdlp() {
    local clip="$1"
    local -a js_args=()
    local tmp_json

    ytdlp_js_runtime_args js_args
    tmp_json=$(mktemp)
    if ! "$YTDLP_BIN" --no-warnings --ignore-config "${js_args[@]}" \
        --extractor-args "youtube:player_client=default,web_embedded" \
        -J "$clip" > "$tmp_json" 2>/dev/null; then
        rm -f "$tmp_json"
        return 0
    fi

    python3 -c '
import json
import re
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)

tracks = {}
for fmt in data.get("formats", []):
    if fmt.get("acodec") == "none" or fmt.get("vcodec") != "none":
        continue

    lang = fmt.get("language") or "und"
    code = lang.split("-")[0].lower()
    if code == "und":
        continue

    note = fmt.get("format_note") or ""
    label = note.split(",")[0].strip() if note else code
    is_original = bool(re.search(r"original", note, re.I))
    is_default = bool(re.search(r"default", note, re.I))
    preference = fmt.get("language_preference", -1) or -1

    if code not in tracks or preference > tracks[code]["preference"]:
        tracks[code] = {
            "label": label,
            "original": is_original,
            "default": is_default,
            "preference": preference,
        }
    else:
        tracks[code]["original"] = tracks[code]["original"] or is_original
        tracks[code]["default"] = tracks[code]["default"] or is_default

if not tracks:
    sys.exit(0)

primary = next((code for code, track in tracks.items() if track["original"]), None)
if not primary:
    primary = max(tracks, key=lambda code: tracks[code]["preference"])
if not primary:
    primary = sorted(tracks.keys())[0]

ordered = [primary] + sorted(code for code in tracks if code != primary)
for code in ordered:
    label = tracks[code]["label"]
    print(f"{code}|{label}|{1 if code == primary else 0}")
' "$tmp_json" 2>/dev/null

    rm -f "$tmp_json"
}

# Fetch available audio track languages from YouTube.
# Output format per line: code|label|is_selected (1 or 0); primary track is listed first.
#
# @param string $1 YouTube video URL
get_audio_language_options() {
    local clip="$1"
    local page_lines ytdlp_lines

    log_message "DEBUG" "Fetching available audio tracks from YouTube..."

    page_lines=$(_get_audio_languages_from_youtube_page "$clip")
    if [[ -n "$page_lines" ]]; then
        log_message "DEBUG" "Audio languages loaded from YouTube page metadata."
        _merge_and_print_audio_language_options "$page_lines" ""
        return
    fi

    log_message "DEBUG" "YouTube page had no audio tracks, falling back to yt-dlp."
    ytdlp_lines=$(_get_audio_languages_from_ytdlp "$clip")
    _merge_and_print_audio_language_options "" "$ytdlp_lines"
}

# Run download sequence loop containing progress bar interfaces
run_download() {
    local format="$1" local lang_filter="$2" local clip="$3" local safe_title="$4"
    local error_log
    error_log=$(mktemp)

    local -a js_args=()
    local -a extractor_args=()
    local audio_format
    ytdlp_js_runtime_args js_args

    extractor_args=(--extractor-args "youtube:player_client=default,web_embedded")

    if [[ -n "$lang_filter" ]]; then
        audio_format="ba${lang_filter}/ba[format_note*=original]/ba"
    else
        audio_format="ba[format_note*=original]/ba"
    fi

    log_message "INFO" "Starting yt-dlp download process..."
    log_message "DEBUG" "Download arguments: Format=$format | Filter=$lang_filter | Target-Dir=$(pwd)"

    if (
      echo "# ${MESSAGES[progress_downloading]}"; echo "5"
      if [[ "$format" == "${MESSAGES[zenity_format_mp3]}" ]]; then
          cmd=("$YTDLP_BIN" "${js_args[@]}" "${extractor_args[@]}" "--newline" "--restrict-filenames" "-x" "--audio-format" "mp3" "--audio-quality" "0" "--format" "$audio_format" "$clip")
      else
          cmd=("$YTDLP_BIN" "${js_args[@]}" "${extractor_args[@]}" "--newline" "--restrict-filenames" "-f" "bv*[ext=mp4]+ba${lang_filter}[ext=m4a]/bv*[ext=mp4]+ba[format_note*=original][ext=m4a]/bv*+ba/b" "--merge-output-format" "mp4" "$clip")
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

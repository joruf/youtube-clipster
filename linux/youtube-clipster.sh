#!/bin/bash

# Loresoft Youtube Clipster - Linux
#
# Author: Joachim Ruf, Loresoft.de
# License: GPLv3 — Der Name des Autors muss bei Veröffentlichung und Veränderung genannt werden.

# 1. Load modules & configuration
BASE_DIR="$(dirname "$(readlink -f "$0")")"
source "$BASE_DIR/config.cfg"

declare -A MESSAGES
source "$BASE_DIR/lib/system.sh"
source "$BASE_DIR/lib/installer.sh"
source "$BASE_DIR/lib/gui.sh"
source "$BASE_DIR/lib/downloader.sh"

load_language

# 2. System protection rules & environment validation checks
trap cleanup_lockfile EXIT INT TERM HUP QUIT SIGINT SIGTERM SIGHUP

echo "${MESSAGES[separator]}"
echo "   $APP_TITLE - Ready for Juniors"
echo "${MESSAGES[separator]}"

log_message "INFO" "Initializing system components..."
manage_lockfile
mkdir -p "$DOWNLOAD_DIR" "$INSTALL_DIR"

check_dependencies
prepare_ytdlp

# 3. State variable declarations for event loop tracking
LAST_CLIP=$(get_clip)
CANCELED_CLIP=""

# Helper function to clear the operating system clipboard (X11 & Wayland)
clear_clipboard() {
    log_message "DEBUG" "Clearing system clipboard to prevent loops."
    if command -v wl-copy &>/dev/null; then
        wl-copy /dev/null 2>/dev/null
    fi
    if command -v xclip &>/dev/null; then
        echo -n "" | xclip -selection clipboard 2>/dev/null
    fi
}

log_message "INFO" "Main event loop started. Monitoring clipboard..."
echo ""
echo "${MESSAGES[started]}"
echo "${MESSAGES[separator]}"

# 4. Main Event Loop Execution Thread
while true; do
    sleep "$INTERVAL_TIME_SEC"
    CLIP=$(get_clip)
    
    [[ "$CLIP" != "$CANCELED_CLIP" ]] && CANCELED_CLIP=""

    # Executed whenever a fresh target link is matched inside system contexts
    if [[ -n "$CLIP" && "$CLIP" != "$CANCELED_CLIP" && "$CLIP" != "$LAST_CLIP" ]]; then
        log_message "INFO" "* New YouTube link detected in clipboard."
        log_message "DEBUG" "Target URL: $CLIP"
        
        show_link_detected_pulsate "${MESSAGES[link_received]}"
        SAFE_TITLE=$(get_video_title "$CLIP")
        
        # Open GUI user dialog choice for destination codec selection
        FORMAT=$(select_format "$SAFE_TITLE")
        if [[ -z "$FORMAT" ]]; then 
            log_message "WARN" "Download canceled by user in format dialog."
            LAST_CLIP=""
            CANCELED_CLIP=""
            clear_clipboard
            continue 
        fi
        log_message "DEBUG" "User selected format: $FORMAT"

        # Open GUI user dialog choice for language stream parameters
        AUDIO_LANG=$(select_audio_lang "$SAFE_TITLE")
        if [[ -z "$AUDIO_LANG" ]]; then
            log_message "WARN" "Download canceled by user in language dialog."
            LAST_CLIP=""
            CANCELED_CLIP=""
            clear_clipboard
            continue
        fi

        case "$AUDIO_LANG" in
            "${MESSAGES[lang_de]}") LANG_FILTER="[language*=de]" ;;
            "${MESSAGES[lang_en]}") LANG_FILTER="[language*=en]" ;;
            *) LANG_FILTER="" ;; 
        esac
        log_message "DEBUG" "User selected audio track: ${AUDIO_LANG:-Default/Best}"
        
        # Switch directory targets and trigger downloader execution
        cd "$DOWNLOAD_DIR" || exit 1
        run_download "$FORMAT" "$LANG_FILTER" "$CLIP" "$SAFE_TITLE"

        # Flush tracking registers and erase clipboard values globally
        LAST_CLIP=""
        CANCELED_CLIP=""
        clear_clipboard
      
    # Reset lock history triggers instantly if context text fields mutate
    elif [[ -n "$CLIP" && "$CLIP" != "$LAST_CLIP" ]]; then
        LAST_CLIP=""
    fi
done

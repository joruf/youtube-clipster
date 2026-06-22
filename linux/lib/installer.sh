#!/bin/bash
# Loresoft Youtube Clipster - Linux Modular Edition
# Dependency Installer Component

# Helper function to automatically install missing system packages
check_and_install() {
    local cmd="$1"
    local pkg="$2"
    
    if ! command -v "$cmd" &>/dev/null; then
        log_message "WARN" "Dependency '$cmd' is missing. Starting automatic installation via apt..."
        
        # Using sudo within terminal context for package management execution
        sudo apt update && sudo apt install -y "$pkg" || { 
            log_message "ERROR" "Installation of $pkg failed!"
            exit 1
        }
        log_message "INFO" "'$pkg' successfully installed."
    else
        log_message "DEBUG" "Dependency found: $cmd"
    fi
}

# Check and optionally create the desktop launcher shortcut
check_desktop_launcher() {
    # 1. Skip check entirely if the user has already answered this dialog in the past
    if [[ "$DESKTOP_SHORTCUT_ASKED" == "true" ]]; then
        log_message "DEBUG" "Desktop shortcut dialog skipped (already asked according to config.cfg)."
        return 0
    fi

    # 2. Direct path check to prevent xdg-user-dir from falling back to $HOME
    local desktop_dir=""
    if [ -d "$HOME/Schreibtisch" ]; then
        desktop_dir="$HOME/Schreibtisch"
    elif [ -d "$HOME/Desktop" ]; then
        desktop_dir="$HOME/Desktop"
    elif [ -d "$(xdg-user-dir DESKTOP 2>/dev/null)" ] && [ "$(xdg-user-dir DESKTOP)" != "$HOME" ]; then
        desktop_dir="$(xdg-user-dir DESKTOP)"
    else
        desktop_dir="$HOME"
    fi
    
    local desktop_path="$desktop_dir/Youtube_Clipster.desktop"
    
    # 3. Dynamically resolve the absolute project root directory path
    local project_dir
    project_dir="$(dirname "$(readlink -f "$0")")"
    
    # Define config path relative to the script execution root
    local config_file="$project_dir/config.cfg"
    
    log_message "DEBUG" "Checking launcher existence at: $desktop_path"
    
    if [[ ! -f "$desktop_path" ]]; then
        log_message "WARN" "Desktop launcher shortcut not found."
        
        # Open Zenity question dialog to ask the user for confirmation
        if zenity --question --title="Create Desktop Shortcut" \
          --text="The desktop shortcut was not found.\nDo you want to create a launcher on your Desktop now?" \
          --width=350 2>/dev/null; then
            
            log_message "INFO" "User accepted. Creating desktop launcher at $desktop_path..."
            
            # Ensure the target directory exists before writing
            mkdir -p "$desktop_dir"
            
            # Generate the file using the dynamically discovered absolute paths
            cat <<EOF > "$desktop_path"
[Desktop Entry]
Version=1.0
Type=Application
Name=YouTube Clipster
Comment=Download YouTube videos via clipboard monitoring
Exec=gnome-terminal -- bash -c "cd $project_dir && ./youtube_clipster.sh; exec bash"
Icon=$project_dir/youtube-clipster-linux.png
Terminal=true
Categories=Network;WebBrowser;
StartupNotify=true
EOF
            
            # Make the desktop shortcut immediately executable
            chmod +x "$desktop_path"
            log_message "INFO" "Desktop shortcut successfully created and marked as executable."
        else
            log_message "INFO" "User declined desktop shortcut creation."
        fi
        
        # 4. Save the decision in config.cfg so the user is never bothered again
        if [[ -f "$config_file" ]]; then
            echo "" >> "$config_file"
            echo "# Auto-generated flag: Prevent asking for desktop shortcut on every startup" >> "$config_file"
            echo "DESKTOP_SHORTCUT_ASKED=\"true\"" >> "$config_file"
            log_message "INFO" "Saved 'DESKTOP_SHORTCUT_ASKED=\"true\"' to config.cfg."
        else
            log_message "WARN" "Could not write to configuration, config.cfg not found at $config_file."
        fi
    else
        log_message "DEBUG" "Desktop launcher shortcut already exists at $desktop_path."
    fi
}

# Verify and setup all core runtime dependencies for YouTube Clipster
check_dependencies() {
    log_message "INFO" "Starting system dependency check..."
    
    # 1. Verify standard core utilities (including zenity for the upcoming dialog)
    check_and_install "zenity" "zenity"
    check_and_install "ffmpeg" "ffmpeg"
    check_and_install "curl" "curl"
    
    # 2. Install clipboard tools for the active session (Wayland needs wl-clipboard, X11 needs xclip)
    if [[ "$XDG_SESSION_TYPE" == "wayland" ]]; then
        check_and_install "wl-paste" "wl-clipboard"
    else
        check_and_install "xclip" "xclip"
    fi

    # 3. Ensure a JavaScript runtime environment is available for native yt-dlp signature decryption
    if ! command -v node &>/dev/null && ! command -v deno &>/dev/null && ! command -v qjs &>/dev/null; then
        log_message "WARN" "No JavaScript runtime found for yt-dlp. Installing quickjs..."
        sudo apt update && sudo apt install -y quickjs || {
            log_message "ERROR" "quickjs installation failed! yt-dlp might encounter format extraction issues."
            exit 1
        }
    fi

    # 4. Optional file manager when configured to open the download folder after completion
    if [[ "$OPEN_NEMO" == true ]]; then
        check_and_install "nemo" "nemo"
    fi

    log_message "INFO" "All system dependencies are satisfied."
    
    # 5. Run the desktop launcher audit check
    check_desktop_launcher
}

#!/bin/sh

set -eu

REPO_URL="${REPO_URL:-https://github.com/TyrelCB/speech-to-text.git}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/speech-to-text}"
SYSTEMD_USER_DIR="${SYSTEMD_USER_DIR:-$HOME/.config/systemd/user}"
SERVICE_NAME="speech-to-text.service"
SKIP_SYSTEM_PACKAGES="${SKIP_SYSTEM_PACKAGES:-0}"
SKIP_PYTHON_DEPS="${SKIP_PYTHON_DEPS:-0}"
SKIP_SERVICE_ENABLE="${SKIP_SERVICE_ENABLE:-0}"

log() {
    printf '%s\n' "$*"
}

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

have() {
    command -v "$1" >/dev/null 2>&1
}

run_privileged() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif have sudo; then
        sudo "$@"
    else
        die "need root privileges to run: $*"
    fi
}

ensure_supported_install_dir() {
    case "$INSTALL_DIR" in
        *" "*)
            die "INSTALL_DIR cannot contain spaces: $INSTALL_DIR"
            ;;
    esac
}

install_apt_packages() {
    packages="ca-certificates curl git python3 python3-tk xdotool"

    run_privileged apt-get update

    if apt-cache show wtype >/dev/null 2>&1; then
        packages="$packages wtype"
    else
        log "wtype package not found via apt; install it manually later if you use Wayland"
    fi

    if apt-cache show pipewire-bin >/dev/null 2>&1; then
        packages="$packages pipewire-bin"
    elif apt-cache show pipewire >/dev/null 2>&1; then
        packages="$packages pipewire"
    fi

    # shellcheck disable=SC2086
    run_privileged apt-get install -y $packages
}

install_dnf_packages() {
    run_privileged dnf install -y \
        ca-certificates \
        curl \
        git \
        python3 \
        python3-tkinter \
        xdotool \
        wtype \
        pipewire-utils
}

install_pacman_packages() {
    run_privileged pacman -Sy --needed --noconfirm \
        ca-certificates \
        curl \
        git \
        python \
        tk \
        xdotool \
        wtype \
        pipewire
}

ensure_system_packages() {
    if [ "$SKIP_SYSTEM_PACKAGES" = "1" ]; then
        log "Skipping system package installation"
        return
    fi

    if have apt-get; then
        log "Installing system packages with apt"
        install_apt_packages
    elif have dnf; then
        log "Installing system packages with dnf"
        install_dnf_packages
    elif have pacman; then
        log "Installing system packages with pacman"
        install_pacman_packages
    else
        log "Skipping system packages: unsupported package manager"
    fi
}

ensure_uv() {
    if have uv; then
        return
    fi

    log "Installing uv"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    have uv || die "uv was installed but is not on PATH"
}

clone_or_update_repo() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        log "Updating repository in $INSTALL_DIR"
        if [ -n "$(git -C "$INSTALL_DIR" status --porcelain)" ]; then
            log "Repository has local changes, skipping git pull"
            return
        fi
        git -C "$INSTALL_DIR" pull --ff-only
        return
    fi

    if [ -e "$INSTALL_DIR" ] && [ ! -d "$INSTALL_DIR" ]; then
        die "INSTALL_DIR exists but is not a directory: $INSTALL_DIR"
    fi

    if [ -d "$INSTALL_DIR" ] && [ -n "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
        die "INSTALL_DIR exists and is not a git checkout: $INSTALL_DIR"
    fi

    log "Cloning repository into $INSTALL_DIR"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone "$REPO_URL" "$INSTALL_DIR"
}

install_python_dependencies() {
    if [ "$SKIP_PYTHON_DEPS" = "1" ]; then
        log "Skipping Python dependency installation"
        return
    fi

    log "Creating virtual environment"
    uv venv "$INSTALL_DIR/.venv"
    log "Installing Python dependencies"
    uv pip install --python "$INSTALL_DIR/.venv/bin/python" -r "$INSTALL_DIR/requirements.txt"
}

check_runtime_commands() {
    missing=""

    for cmd in pw-record; do
        if ! have "$cmd"; then
            missing="$missing $cmd"
        fi
    done

    if [ -n "$missing" ]; then
        log "warning: missing runtime command(s):$missing"
        log "The app will not work until those tools are installed."
    fi
}

write_service_file() {
    service_path="$SYSTEMD_USER_DIR/$SERVICE_NAME"

    log "Writing systemd user service to $service_path"
    mkdir -p "$SYSTEMD_USER_DIR"

    cat >"$service_path" <<EOF
[Unit]
Description=Speech-to-Text Engine
After=graphical-session.target pipewire.service
Wants=graphical-session.target pipewire.service
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStartPre=/bin/sh -lc 'test -n "\$WAYLAND_DISPLAY" || test -n "\$DISPLAY"'
ExecStart=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/main.py
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF
}

enable_service() {
    if [ "$SKIP_SERVICE_ENABLE" = "1" ]; then
        log "Skipping systemd enable/start"
        return
    fi

    if ! have systemctl; then
        log "systemctl not found; service file was written but not enabled"
        return
    fi

    systemctl --user import-environment \
        DISPLAY \
        WAYLAND_DISPLAY \
        XAUTHORITY \
        XDG_CURRENT_DESKTOP \
        XDG_RUNTIME_DIR \
        DBUS_SESSION_BUS_ADDRESS \
        XDG_SESSION_TYPE >/dev/null 2>&1 || true

    if ! systemctl --user daemon-reload; then
        log "warning: could not reach the user systemd instance"
        log "Run later:"
        log "  systemctl --user daemon-reload"
        log "  systemctl --user enable --now $SERVICE_NAME"
        return
    fi

    if ! systemctl --user enable --now "$SERVICE_NAME"; then
        log "warning: service file updated, but enable/start failed"
        log "Check the user session and run:"
        log "  systemctl --user enable --now $SERVICE_NAME"
        return
    fi
}

main() {
    ensure_supported_install_dir
    ensure_system_packages
    ensure_uv
    clone_or_update_repo
    install_python_dependencies
    check_runtime_commands
    write_service_file
    enable_service

    log ""
    log "Speech-to-Text is installed in $INSTALL_DIR"
    log "Logs: journalctl --user -u $SERVICE_NAME -f"
}

main "$@"
